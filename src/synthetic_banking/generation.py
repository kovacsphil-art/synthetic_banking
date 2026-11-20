"""Existing generation stages, called by the notebook with explicit inputs."""

from dataclasses import dataclass
import json
import numpy as np
import pandas as pd

from synthetic_banking.config import GenerationSettings
from synthetic_banking.generators import ProfileGenerators
from synthetic_banking.dates import load_date_sampler
from synthetic_banking.customer_relationships import generate_customer_relationships
from synthetic_banking.rules import (
    load_rule_proposals, partition_rule_proposals, apply_balance_rules, apply_delinquency_rule,
    partition_sampling_proposals, apply_categorical_dependency_rules, apply_numeric_dependency_rule,
)
from synthetic_banking.validation import expected_generated_schema


@dataclass
class GenerationResult:
    source_run_id: str
    settings: GenerationSettings
    tables: dict
    rule_events: tuple
    relationship_plan: dict
    expected_schema: dict
    expected_counts: dict
    date_null_counts: dict
    date_diagnostics: list
    rng_state: dict


def add_missing_columns(df, logical_table_name, expected_schema):
    existing = {column.upper() for column in df.columns}
    for column in expected_schema[logical_table_name]:
        if column.upper() not in existing:
            df[column] = None
    return df


complete_columns = add_missing_columns


def generate_dataset(spark, profiles, settings=GenerationSettings(), *, date_sampler=None):
    source_run_id = profiles.source_run_id
    pilot_batch_id, pilot_proposal_ids = settings.pilot_batch_id, settings.pilot_proposal_ids
    if settings.proposal_batch_id and pilot_batch_id:
        raise ValueError("Choose workflow proposal_batch_id or manual pilot_batch_id, not both.")
    numeric_stats, category_stats = profiles.numeric_stats, profiles.category_stats
    column_quality, structural_stats = profiles.column_quality, profiles.structural_stats
    conditional_stats = profiles.conditional_stats
    customer_relationship_profile = profiles.customer_relationship_profile
    expected_schema = expected_generated_schema(column_quality)
    def add_missing_columns(df, logical_table_name):
        return complete_columns(df, logical_table_name, expected_schema)
    N_CUSTOMERS = settings.num_customers

    SEED = settings.seed

    rule_proposals = load_rule_proposals(spark, source_run_id, batch_id=settings.proposal_batch_id or pilot_batch_id)
    if pilot_batch_id:
        approved_ids = {proposal.proposal_id for proposal in rule_proposals if proposal.approved}
        if approved_ids != set(pilot_proposal_ids):
            raise ValueError(f"Pilot batch {pilot_batch_id} must contain exactly the selected reviewed approvals "
                             f"for SOURCE {source_run_id}. Found: {sorted(approved_ids)}.")
    print(f"Considering {len(rule_proposals)} proposals ({sum(p.approved for p in rule_proposals)} approved) for SOURCE run {source_run_id}.")
    categorical_proposals, numeric_proposals, existing_proposals = partition_sampling_proposals(rule_proposals)
    balance_proposals, delinquency_proposals = partition_rule_proposals(existing_proposals)

    rng = np.random.default_rng(SEED)

    print(f"Generating {N_CUSTOMERS:,} customers")
    samplers = ProfileGenerators(profiles, rng)
    apply_profiled_nulls = samplers.apply_profiled_nulls
    fill_profiled_fields = samplers.fill_profiled_fields
    generate_cardinality = samplers.generate_cardinality
    generate_categorical = samplers.generate_categorical
    generate_numeric = samplers.generate_numeric

    person_ids = [
        f"P{i:08d}"
        for i in range(1, N_CUSTOMERS + 1)
    ]

    person_df = pd.DataFrame({
        "PARTY_ID": person_ids
    })

    person_categorical_columns = (
        category_stats[
            category_stats["logical_table_name"] == "PERSON"
        ]["column_name"]
        .unique()
    )

    for column_name in person_categorical_columns:

        if column_name == "PARTY_ID":
            continue

        person_df[column_name] = generate_categorical(
            "PERSON",
            column_name,
            N_CUSTOMERS
        )

    person_numeric_columns = (
        numeric_stats[
            numeric_stats["logical_table_name"] == "PERSON"
        ]["column_name"]
        .unique()
    )

    for column_name in person_numeric_columns:

        if column_name in person_df.columns:
            continue

        person_df[column_name] = generate_numeric(
            "PERSON",
            column_name,
            N_CUSTOMERS
        )

    person_df = apply_profiled_nulls(
        person_df,
        "PERSON",
        protected_columns=["PARTY_ID"]
    )

    date_sampler = date_sampler or load_date_sampler(spark, source_run_id, SEED)

    for column_name, values in date_sampler.generate_table("PERSON", N_CUSTOMERS).items():
        person_df[column_name] = values

    # The date planner enforces ordering while sampling, without clamping dates.
    if "BIRTH_DT" in person_df and "SINCE_DT" in person_df:
        invalid = person_df["BIRTH_DT"].notna() & person_df["SINCE_DT"].notna() & (person_df["SINCE_DT"] < person_df["BIRTH_DT"])
        if invalid.any():
            raise ValueError("Generated PERSON dates violate BIRTH_DT <= SINCE_DT.")

    account_counts = generate_cardinality(
        "ACCOUNTS_PER_PARTY",
        N_CUSTOMERS,
        fallback=1
    )

    total_accounts = int(
        account_counts.sum()
    )

    print(
        f"{N_CUSTOMERS:,} customers"
    )

    print(
        f"{total_accounts:,} accounts"
    )

    account_ids = [
        f"A{i:09d}"
        for i in range(
            1,
            total_accounts + 1
        )
    ]

    account_party_ids = np.repeat(
        person_df["PARTY_ID"].to_numpy(),
        account_counts
    )

    customer_account_rel_df = pd.DataFrame({
        "PARTY_ID": account_party_ids,
        "ACCT_ID": account_ids
    })

    account_df = pd.DataFrame({
        "ACCOUNT_ID": account_ids
    })

    account_categorical_columns = (
        category_stats[
            category_stats["logical_table_name"]
            == "TKQ_ACCOUNT"
        ]["column_name"]
        .unique()
    )

    for column_name in account_categorical_columns:

        if column_name in ("ACCOUNT_ID", "BUSINESSEFFECTIVEDATE"):
            continue

        account_df[column_name] = (
            generate_categorical(
                "TKQ_ACCOUNT",
                column_name,
                total_accounts
            )
        )

    account_numeric_columns = (
        numeric_stats[
            numeric_stats["logical_table_name"]
            == "TKQ_ACCOUNT"
        ]["column_name"]
        .unique()
    )

    for column_name in account_numeric_columns:

        if column_name == "BUSINESSEFFECTIVEDATE" or column_name in account_df.columns:
            continue

        account_df[column_name] = (
            generate_numeric(
                "TKQ_ACCOUNT",
                column_name,
                total_accounts
            )
        )

    categorical_events = apply_categorical_dependency_rules(
        source_run_id, categorical_proposals, account_df, profiles, SEED,
    )

    account_balance_df = pd.DataFrame({
        "ACCOUNT_ID": account_ids
    })

    raw_balance = generate_numeric(
        "TKQ_ACCOUNT_BALANCE",
        "CURRENT_BALANCE_AMT",
        total_accounts
    )

    raw_balance = np.maximum(
        raw_balance,
        0
    )

    if "CREDIT_LIMIT_AMT" in account_df.columns:

        credit_limit = (
            pd.to_numeric(
                account_df["CREDIT_LIMIT_AMT"],
                errors="coerce"
            )
            .fillna(0)
            .to_numpy()
        )

        raw_balance, numeric_events = apply_numeric_dependency_rule(
            source_run_id, numeric_proposals, credit_limit, raw_balance, profiles, SEED,
        )

        # Allow some over-limit accounts,
        # but prevent absurd combinations
        current_balance = np.minimum(
            raw_balance,
            credit_limit * 1.25
        )

    else:

        raw_balance, numeric_events = apply_numeric_dependency_rule(
            source_run_id, numeric_proposals, None, raw_balance, profiles, SEED,
        )

        credit_limit = np.zeros(
            total_accounts
        )

        current_balance = raw_balance

    account_balance_df[
        "CURRENT_BALANCE_AMT"
    ] = current_balance

    if not account_df["ACCOUNT_ID"].equals(account_balance_df["ACCOUNT_ID"]):
        raise ValueError("Account and balance rows must align by ACCOUNT_ID before applying balance rules.")

    balance_amounts, balance_events = apply_balance_rules(
        source_run_id, balance_proposals, credit_limit, current_balance,
        has_credit_limit="CREDIT_LIMIT_AMT" in account_df.columns,
    )
    rule_events = (*categorical_events, *numeric_events, *balance_events)
    for target_column, values in balance_amounts.items():
        account_balance_df[target_column] = values

    account_df[
        "_UTILIZATION_RATE"
    ] = np.where(
        credit_limit > 0,
        current_balance / credit_limit,
        0
    )

    # The rule framework owns measured-rate lookup and preserved legacy fallback.
    # Draw once at the same point as before so downstream RNG state is preserved.
    is_delinquent, delinquency_events = apply_delinquency_rule(
        source_run_id,
        delinquency_proposals,
        account_df["_UTILIZATION_RATE"].to_numpy(),
        conditional_stats.to_dict("records"),
        rng.random(total_accounts),
    )
    rule_events = (*rule_events, *delinquency_events)

    account_df["PAST_DUE_INDICATO_CD"] = np.where(is_delinquent, "Y", "N")

    for event in rule_events:
        target = f"{event.target_table}.{event.target_column}"
        if event.proposal_id is not None:
            target += f" (proposal {event.proposal_id}, batch {event.batch_id})"
        print(f"{event.outcome} {target}: {event.reason or event.implementation_name}")

    if pilot_batch_id:
        applied_ids = {event.proposal_id for event in rule_events if event.applied}
        if applied_ids != set(pilot_proposal_ids):
            missed = sorted(set(pilot_proposal_ids) - applied_ids)
            raise RuntimeError(f"Pilot generation stopped before writes. Selected proposals did not apply: {missed}.")

    generated_dlq_count = generate_numeric(
        "TKQ_ACCOUNT",
        "DELINQUENCY_CNT",
        total_accounts
    )

    generated_dlq_count = np.nan_to_num(
        generated_dlq_count,
        nan=0
    )

    generated_dlq_count = np.maximum(
        np.round(
            generated_dlq_count
        ),
        1
    )

    account_df[
        "DELINQUENCY_CNT"
    ] = np.where(
        is_delinquent,
        generated_dlq_count,
        0
    ).astype(int)

    customer_account_rel_df = (
        fill_profiled_fields(
            customer_account_rel_df,
            "CUSTOMER_ACCOUNT_REL",
            protected_columns=[
                "PARTY_ID",
                "ACCT_ID"
            ]
        )
    )
    for column_name, values in date_sampler.generate_table("CUSTOMER_ACCOUNT_REL", len(customer_account_rel_df)).items():
        customer_account_rel_df[column_name] = values

    snapshot_date_column = "BUSINESSEFFECTIVEDATE"

    account_balance_df = (
        fill_profiled_fields(
            account_balance_df,
            "TKQ_ACCOUNT_BALANCE",
            protected_columns=[
                "ACCOUNT_ID",
                snapshot_date_column,
                "CURRENT_BALANCE_AMT",
                "AVAILABLE_TO_BUY_AMT",
                "OVERLIMIT_AMT"
            ]
        )
    )

    # All account dates use SOURCE month support and temporal bounds.
    # The effective date is sampled once and assigned by synthetic ACCOUNT_ID.
    account_dates, balance_dates = date_sampler.generate_accounts(
        account_df["ACCOUNT_ID"].to_numpy(), account_balance_df["ACCOUNT_ID"].to_numpy(),
    )
    for column_name, values in account_dates.items():
        account_df[column_name] = values
    for column_name, values in balance_dates.items():
        account_balance_df[column_name] = values

    tradeline_counts = generate_cardinality(
        "TRADELINES_PER_CIF",
        N_CUSTOMERS,
        fallback=3
    )

    total_tradelines = int(
        tradeline_counts.sum()
    )

    tradeline_party_ids = np.repeat(
        person_df["PARTY_ID"].to_numpy(),
        tradeline_counts
    )

    tradeline_ids = [
        f"TL{i:010d}"
        for i in range(
            1,
            total_tradelines + 1
        )
    ]

    tradelines_df = pd.DataFrame({
        "REQ-CIF-KEY":
            tradeline_party_ids,

        "REQ-CIF-TIE-BREAKER":
            1,

        "account_number":
            tradeline_ids
    })

    tradelines_df = fill_profiled_fields(
        tradelines_df,
        "TRADELINES",
        protected_columns=[
            "REQ-CIF-KEY",
            "REQ-CIF-TIE-BREAKER",
            "account_number"
        ]
    )
    for column_name, values in date_sampler.generate_table("TRADELINES", len(tradelines_df)).items():
        tradelines_df[column_name] = values

    print(f"Date generation used SOURCE {source_run_id}, seed {SEED} (day precision).")


    relationship_data, relationship_plan = generate_customer_relationships(
        person_df["PARTY_ID"].to_numpy(), customer_relationship_profile, SEED, date_sampler,
    )
    customer_relationship_df = pd.DataFrame(relationship_data)
    print("CUSTOMER_RELATIONSHIP generation plan (aggregate audit):")
    print(json.dumps(relationship_plan, sort_keys=True, indent=2))

    tables = {
        "PERSON":
            person_df,

        "CUSTOMER_ACCOUNT_REL":
            customer_account_rel_df,

        "CUSTOMER_RELATIONSHIP":
            customer_relationship_df,

        "TKQ_ACCOUNT":
            account_df,

        "TKQ_ACCOUNT_BALANCE":
            account_balance_df,

        "TRADELINES":
            tradelines_df
    }

    for table_name, df in tables.items():

        print(
            f"{table_name}: "
            f"{len(df):,} rows"
        )

    person_df = add_missing_columns(
        person_df,
        "PERSON"
    )

    account_df = add_missing_columns(
        account_df,
        "TKQ_ACCOUNT"
    )

    account_balance_df = add_missing_columns(
        account_balance_df,
        "TKQ_ACCOUNT_BALANCE"
    )

    customer_account_rel_df = add_missing_columns(
        customer_account_rel_df,
        "CUSTOMER_ACCOUNT_REL"
    )

    tradelines_df = add_missing_columns(
        tradelines_df,
        "TRADELINES"
    )
    customer_relationship_df = add_missing_columns(customer_relationship_df, "CUSTOMER_RELATIONSHIP")

    expected_counts = {"PERSON": N_CUSTOMERS, "CUSTOMER_ACCOUNT_REL": total_accounts,
                       "TKQ_ACCOUNT": total_accounts, "TKQ_ACCOUNT_BALANCE": total_accounts,
                       "TRADELINES": total_tradelines, "CUSTOMER_RELATIONSHIP": len(customer_relationship_df)}
    return GenerationResult(source_run_id, settings, tables, tuple(rule_events), relationship_plan,
                            expected_schema, expected_counts, date_sampler.expected_null_counts,
                            date_sampler.diagnostics, rng.bit_generator.state)
