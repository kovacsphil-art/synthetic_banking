"""Validate persisted generation outputs before publishing them for profiling."""

from synthetic_banking.temporal import temporal_checks
import json

from synthetic_banking.customer_relationships import AUDIT_TABLE as RELATIONSHIP_AUDIT_TABLE, IMPLEMENTATION_VERSION as RELATIONSHIP_VERSION

from synthetic_banking.config import PROFILE_SCHEMA, GENERATED_SCHEMA
AUDIT_TABLE = "rule_execution_log"

_KEYS = {
    "PERSON": ("PARTY_ID", "P", 8),
    "CUSTOMER_ACCOUNT_REL": ("ACCT_ID", "A", 9),
    "TKQ_ACCOUNT": ("ACCOUNT_ID", "A", 9),
    "TKQ_ACCOUNT_BALANCE": ("ACCOUNT_ID", "A", 9),
    "TRADELINES": ("account_number", "TL", 10),
}
GENERATED_TABLES = (*_KEYS, "CUSTOMER_RELATIONSHIP")

_REQUIRED_TYPES = {
    "PERSON": {"PARTY_ID": "string", "BIRTH_DT": "date", "SINCE_DT": "date"},
    "CUSTOMER_ACCOUNT_REL": {"PARTY_ID": "string", "ACCT_ID": "string"},
    "CUSTOMER_RELATIONSHIP": {"FROM_PARTY_ID": "string", "TO_PARTY_ID": "string",
                              "FROM_TO_CUST_RELATN_CD": "string", "TO_FROM_CUST_RELATN_CD": "string"},
    "TKQ_ACCOUNT": {
        "ACCOUNT_ID": "string", "BUSINESSEFFECTIVEDATE": "timestamp",
        "CREDIT_LIMIT_AMT": "double", "_UTILIZATION_RATE": "double",
        "PAST_DUE_INDICATO_CD": "string", "DELINQUENCY_CNT": "bigint",
    },
    "TKQ_ACCOUNT_BALANCE": {
        "ACCOUNT_ID": "string", "BUSINESSEFFECTIVEDATE": "timestamp",
        "CURRENT_BALANCE_AMT": "double", "AVAILABLE_TO_BUY_AMT": "double", "OVERLIMIT_AMT": "double",
    },
    "TRADELINES": {
        "account_number": "string", "REQ-CIF-KEY": "string", "REQ-CIF-TIE-BREAKER": "bigint",
    },
}

_TYPE_FAMILIES = {
    "numeric": {"byte", "tinyint", "short", "smallint", "int", "integer",
                "long", "bigint", "float", "real", "double", "decimal", "numeric"},
    "text": {"string", "varchar", "char"},
    "temporal": {"date", "timestamp", "timestamp_ntz", "timestamp_ltz"},
}


class GeneratedValidationError(ValueError):
    """The saved batch cannot be used for generated-data profiling."""


def expected_generated_schema(column_quality):
    """Use the pinned SOURCE inventory, with explicit types for generated keys and rules."""
    expected = {name: {} for name in GENERATED_TABLES}
    for row in column_quality.itertuples(index=False):
        if row.logical_table_name in expected:
            expected[row.logical_table_name][row.column_name] = row.data_type

    for name, columns in expected.items():
        if not columns:
            raise GeneratedValidationError(f"The pinned SOURCE profile has no schema for {name}.")
        # Keep the SOURCE spelling when a fixed field is already present.
        existing = {column.upper(): column for column in columns}
        for column, data_type in _REQUIRED_TYPES[name].items():
            columns[existing.get(column.upper(), column)] = data_type
    return expected


def _type_family(data_type):
    base = data_type.lower().split("(", 1)[0].split("<", 1)[0]
    return next((family for family, names in _TYPE_FAMILIES.items() if base in names), base)


def null_padding_type(expected_type, source_type):
    """Preserve full SOURCE types where compatible with the generated schema."""
    if source_type is not None and _type_family(source_type.simpleString()) == _type_family(expected_type):
        return source_type
    return "string" if _type_family(expected_type) == "text" else expected_type


def _check_schema(actual, expected, table):
    by_name = {name.upper(): data_type for name, data_type in actual}
    if len(by_name) != len(actual):
        raise GeneratedValidationError(f"{table}: duplicate column names.")
    issues = []
    for name, expected_type in expected.items():
        actual_type = by_name.get(name.upper())
        if actual_type is None:
            issues.append(f"missing {name}")
        elif _type_family(actual_type) != _type_family(expected_type):
            issues.append(f"{name} has type {actual_type}; expected compatible {expected_type}")
    if issues:
        raise GeneratedValidationError(f"{table}: " + ", ".join(issues))
    return by_name


def generated_table_versions(spark):
    """Return Delta table identity and commit version for each batch output and its audit."""
    versions = {}
    for name in (*GENERATED_TABLES, AUDIT_TABLE, RELATIONSHIP_AUDIT_TABLE):
        table = f"{GENERATED_SCHEMA}.{name}"
        if not spark.catalog.tableExists(table):
            raise GeneratedValidationError(f"Missing generated Delta table {table}.")
        detail = spark.sql(f"DESCRIBE DETAIL {table}").first()
        if detail is None or detail["format"] != "delta" or not detail["id"]:
            raise GeneratedValidationError(f"{table} is not a readable Delta table.")
        version = spark.sql(f"DESCRIBE HISTORY {table} LIMIT 1").first()
        if version is None:
            raise GeneratedValidationError(f"{table} has no committed Delta version.")
        versions[name] = f"{detail['id']}:{version['version']}"
    return versions


def check_validated_versions(spark, validated_versions):
    """Refuse earlier or changed outputs so only the validated batch is profiled."""
    if not validated_versions:
        raise GeneratedValidationError("The batch has no validation record. Rerun Notebook 03.")
    current = generated_table_versions(spark)
    changed = [name for name in current if current[name] != validated_versions.get(name)]
    if changed:
        raise GeneratedValidationError(
            "Generated tables changed since validation: " + ", ".join(changed) + ". Rerun Notebook 03."
        )


def validate_generated_batch(
    spark, expected_schema, expected_counts, generation_id, source_run_id, expected_audit_rows,
    expected_date_null_counts=None,
):
    """Check saved tables and return the versions that passed validation."""
    versions = generated_table_versions(spark)
    tables = {name: f"{GENERATED_SCHEMA}.{name}" for name in GENERATED_TABLES}
    schemas = {}
    for name, table in tables.items():
        fields = [(field.name, field.dataType.simpleString()) for field in spark.table(table).schema.fields]
        schemas[name] = _check_schema(fields, expected_schema[name], name)

    if schemas["TKQ_ACCOUNT"]["BUSINESSEFFECTIVEDATE"] != schemas["TKQ_ACCOUNT_BALANCE"]["BUSINESSEFFECTIVEDATE"]:
        raise GeneratedValidationError("Account and balance snapshot dates must use the same type.")

    issues = []
    counts = {}
    for name, (key, prefix, width) in _KEYS.items():
        expected_count = expected_counts[name]
        # Compare to the canonical generated sequence, including its padding.
        suffix = f"TRY_CAST(SUBSTRING(`{key}`, {len(prefix) + 1}) AS BIGINT)"
        date_conflict = (
            ", COUNT(CASE WHEN SINCE_DT < BIRTH_DT THEN 1 END) AS invalid_dates"
            if name == "PERSON" else ""
        )
        result = spark.sql(f"""
            SELECT COUNT(*) AS row_count, COUNT(DISTINCT `{key}`) AS unique_keys,
                COUNT(CASE WHEN COALESCE(
                    `{key}` = format_string('{prefix}%0{width}d', {suffix})
                    AND {suffix} BETWEEN 1 AND :expected_count, FALSE
                ) = FALSE THEN 1 END) AS invalid_ids
                {date_conflict}
            FROM {tables[name]}
            """, args={"expected_count": expected_count}).first()
        counts[name] = result["row_count"]
        print(f"{name}: {result['row_count']:,}/{expected_count:,} rows written")
        if result["row_count"] != expected_count:
            issues.append(f"{name}: row count differs from the generation plan.")
        if result["unique_keys"] != result["row_count"] or result["invalid_ids"]:
            issues.append(f"{name}: duplicate, null, or out-of-sequence synthetic keys.")
        if name == "PERSON" and result["invalid_dates"]:
            issues.append(f"PERSON: {result['invalid_dates']} dates violate SINCE_DT >= BIRTH_DT.")

    if not counts["PERSON"] or not counts["TKQ_ACCOUNT"]:
        issues.append("PERSON and TKQ_ACCOUNT must contain generated records.")

    relationship_audit = spark.sql(f"""
        SELECT source_run_id, seed, implementation_version, plan_json FROM {GENERATED_SCHEMA}.{RELATIONSHIP_AUDIT_TABLE}
        WHERE generation_id = :generation
    """, args={"generation": generation_id}).collect()
    if len(relationship_audit) != 1 or relationship_audit[0]["source_run_id"] != source_run_id:
        raise GeneratedValidationError("Customer relationship audit must identify this generation and SOURCE run exactly once.")
    try:
        relationship_plan = json.loads(relationship_audit[0]["plan_json"])
    except (TypeError, ValueError) as error:
        raise GeneratedValidationError("Customer relationship audit plan is invalid JSON.") from error
    source_relationships = spark.sql(f"""
        SELECT p.self_rows FROM {PROFILE_SCHEMA}.customer_relationship_summary p
        JOIN {PROFILE_SCHEMA}.profile_runs r ON p.run_id = r.run_id
        WHERE p.run_id = :source AND p.profile_type = 'SOURCE' AND r.profile_type = 'SOURCE'
          AND r.status = 'COMPLETED' AND r.completed_at IS NOT NULL
    """, args={"source": source_run_id}).collect()
    if (not isinstance(relationship_plan, dict) or len(source_relationships) != 1 or relationship_plan.get("source_run_id") != source_run_id
        or relationship_plan.get("seed") != relationship_audit[0]["seed"]
        or relationship_plan.get("implementation_version") != RELATIONSHIP_VERSION
        or relationship_audit[0]["implementation_version"] != RELATIONSHIP_VERSION
        or not relationship_plan.get("profile_signature")
        or relationship_plan.get("generated_person_count") != counts["PERSON"]
        or bool(relationship_plan.get("self_allowed")) != bool(source_relationships[0]["self_rows"])):
        raise GeneratedValidationError("Customer relationship audit does not match the pinned completed SOURCE evidence.")
    if not isinstance(relationship_plan.get("null_counts"), dict):
        raise GeneratedValidationError("Customer relationship null plan must be a field/count mapping.")
    if set(relationship_plan["null_counts"]) != set(expected_schema["CUSTOMER_RELATIONSHIP"]) - {"FROM_PARTY_ID", "TO_PARTY_ID"}:
        # Preserve SOURCE spellings; endpoint spellings can differ only in case.
        expected_null_fields = {name.upper() for name in expected_schema["CUSTOMER_RELATIONSHIP"]} - {"FROM_PARTY_ID", "TO_PARTY_ID"}
        if {name.upper() for name in relationship_plan.get("null_counts", {})} != expected_null_fields:
            raise GeneratedValidationError("Customer relationship null plan must cover every non-key SOURCE column.")
    owned_column = next((name for name in schemas["CUSTOMER_RELATIONSHIP"] if name == "OWNERSHIP_PERCENTAGE"), None)
    ownership_check = (", COUNT(CASE WHEN r.ownership_percentage < 0 OR r.ownership_percentage > 100 "
                       "OR ISNAN(CAST(r.ownership_percentage AS DOUBLE)) THEN 1 END) AS invalid_ownership" if owned_column else "")
    relationships = spark.sql(f"""
        SELECT COUNT(*) AS row_count,
            COUNT(CASE WHEN f.PARTY_ID IS NULL OR t.PARTY_ID IS NULL THEN 1 END) AS orphan_rows,
            COUNT(CASE WHEN r.FROM_PARTY_ID = r.TO_PARTY_ID THEN 1 END) AS self_rows {ownership_check}
        FROM {tables['CUSTOMER_RELATIONSHIP']} r
        LEFT JOIN {tables['PERSON']} f ON r.FROM_PARTY_ID = f.PARTY_ID
        LEFT JOIN {tables['PERSON']} t ON r.TO_PARTY_ID = t.PARTY_ID
    """).first()
    counts["CUSTOMER_RELATIONSHIP"] = relationships["row_count"]
    print(f"CUSTOMER_RELATIONSHIP: {relationships['row_count']} rows, {relationships['orphan_rows']} invalid endpoints, {relationships['self_rows']} self rows")
    if relationships["row_count"] != expected_counts["CUSTOMER_RELATIONSHIP"] or relationships["row_count"] != relationship_plan.get("row_count"):
        issues.append("CUSTOMER_RELATIONSHIP row count differs from the generation/audit plan.")
    if relationships["orphan_rows"]:
        issues.append("CUSTOMER_RELATIONSHIP contains null or nonexistent FROM/TO_PARTY_ID references.")
    if relationships["self_rows"] != relationship_plan.get("self_rows") or (relationships["self_rows"] and not source_relationships[0]["self_rows"]):
        issues.append("CUSTOMER_RELATIONSHIP contains unsupported or unplanned self-relationships.")
    if owned_column and relationships["invalid_ownership"]:
        issues.append("CUSTOMER_RELATIONSHIP ownership percentages must be finite and between 0 and 100.")
    for column, expected_nulls in relationship_plan.get("null_counts", {}).items():
        if column.upper() not in schemas["CUSTOMER_RELATIONSHIP"]:
            raise GeneratedValidationError("Customer relationship null plan refers to an unknown column.")
        quoted = "`" + column.replace("`", "``") + "`"
        actual = spark.sql(f"SELECT COUNT(CASE WHEN {quoted} IS NULL THEN 1 END) AS n FROM {tables['CUSTOMER_RELATIONSHIP']}").first()["n"]
        if actual != expected_nulls:
            issues.append(f"CUSTOMER_RELATIONSHIP.{column}: saved null count differs from the profiled relationship null plan.")

    temporal_columns = {name: [column for column, kind in fields.items() if _type_family(kind) == "temporal"]
                        for name, fields in schemas.items()}
    for check in temporal_checks(spark, tables, temporal_columns):
        if check["profile_status"] == "UNAVAILABLE":
            continue
        print(f"Temporal {check['logical_table_name']}.{check['metric']}: "
              f"{check['numerator']} violations / {check['denominator']} non-null pairs")
        if check["numerator"]:
            issues.append(f"{check['logical_table_name']}: {check['numerator']} temporal violations of {check['metric']}.")
    for table, fields in (expected_date_null_counts or {}).items():
        if table not in schemas:
            raise GeneratedValidationError(f"Unknown table in date null plan: {table}.")
        for column, expected_nulls in fields.items():
            if column.upper() not in schemas[table] or _type_family(schemas[table][column.upper()]) != "temporal":
                raise GeneratedValidationError(f"{table}.{column}: date null plan requires a saved temporal column.")
            quoted = "`" + column.replace("`", "``") + "`"
            actual = spark.sql(f"SELECT COUNT(CASE WHEN {quoted} IS NULL THEN 1 END) AS null_count FROM {tables[table]}").first()["null_count"]
            if actual != expected_nulls:
                issues.append(f"{table}.{column}: {actual} saved date nulls; expected {expected_nulls} from the SOURCE null plan.")

    links = spark.sql(f"""
        SELECT
            (SELECT COUNT(*) FROM {tables['CUSTOMER_ACCOUNT_REL']} r
             LEFT JOIN {tables['PERSON']} p ON r.PARTY_ID = p.PARTY_ID
             LEFT JOIN {tables['TKQ_ACCOUNT']} a ON r.ACCT_ID = a.ACCOUNT_ID
             WHERE p.PARTY_ID IS NULL OR a.ACCOUNT_ID IS NULL) AS orphan_account_links,
            (SELECT COUNT(*) FROM {tables['TRADELINES']} t
             LEFT JOIN {tables['PERSON']} p ON t.`REQ-CIF-KEY` = p.PARTY_ID
             WHERE p.PARTY_ID IS NULL OR COALESCE(t.`REQ-CIF-TIE-BREAKER`, 0) <> 1) AS invalid_tradeline_links
        """).first()
    for check in ("orphan_account_links", "invalid_tradeline_links"):
        if links[check]:
            issues.append(f"{check}: {links[check]}.")

    joined = spark.sql(f"""
        SELECT COUNT(DISTINCT a.ACCOUNT_ID) AS matched_accounts,
            COUNT(DISTINCT b.ACCOUNT_ID) AS matched_balances,
            COUNT(CASE WHEN NOT COALESCE(
                b.CURRENT_BALANCE_AMT >= 0
                AND (a.CREDIT_LIMIT_AMT IS NULL OR b.CURRENT_BALANCE_AMT <= 1.25 * a.CREDIT_LIMIT_AMT + 1e-8)
                AND ABS(b.AVAILABLE_TO_BUY_AMT - GREATEST(COALESCE(a.CREDIT_LIMIT_AMT, 0) - b.CURRENT_BALANCE_AMT, 0)) <= 1e-8
                AND ABS(b.OVERLIMIT_AMT - GREATEST(b.CURRENT_BALANCE_AMT - COALESCE(a.CREDIT_LIMIT_AMT, 0), 0)) <= 1e-8,
                FALSE
            ) THEN 1 END) AS invalid_amounts,
            COUNT(CASE WHEN NOT COALESCE(
                ABS(a._UTILIZATION_RATE - CASE WHEN a.CREDIT_LIMIT_AMT > 0
                    THEN CAST(b.CURRENT_BALANCE_AMT AS DOUBLE) / a.CREDIT_LIMIT_AMT ELSE 0 END) <= 1e-8,
                FALSE
            ) THEN 1 END) AS invalid_utilization,
            COUNT(CASE WHEN NOT COALESCE(
                a.DELINQUENCY_CNT = FLOOR(a.DELINQUENCY_CNT)
                AND ((a.PAST_DUE_INDICATO_CD = 'Y' AND a.DELINQUENCY_CNT >= 1)
                     OR (a.PAST_DUE_INDICATO_CD = 'N' AND a.DELINQUENCY_CNT = 0)),
                FALSE
            ) THEN 1 END) AS invalid_delinquency
        FROM {tables['TKQ_ACCOUNT']} a
        JOIN {tables['TKQ_ACCOUNT_BALANCE']} b
            ON a.ACCOUNT_ID = b.ACCOUNT_ID AND a.BUSINESSEFFECTIVEDATE = b.BUSINESSEFFECTIVEDATE
        """).first()
    matched_accounts, matched_balances = joined["matched_accounts"], joined["matched_balances"]
    accounts, balances = counts["TKQ_ACCOUNT"], counts["TKQ_ACCOUNT_BALANCE"]
    print(
        f"Account snapshot join coverage: {matched_accounts:,}/{accounts:,} accounts, "
        f"{matched_balances:,}/{balances:,} balances"
    )
    if matched_accounts != accounts or matched_balances != balances:
        issues.append("Account/balance snapshot keys do not have full one-to-one join coverage.")
    for check in ("invalid_amounts", "invalid_utilization", "invalid_delinquency"):
        if joined[check]:
            issues.append(f"{check}: {joined[check]}.")

    audit = spark.sql(f"""
        SELECT *
        FROM {GENERATED_SCHEMA}.{AUDIT_TABLE}
        WHERE generation_id = :generation_id
        """, args={"generation_id": generation_id}).collect()
    if len(audit) != expected_audit_rows or any(row["source_run_id"] != source_run_id for row in audit):
        issues.append("The saved rule audit does not match this generation and SOURCE run.")
    unimplemented = [row for row in audit if row["approved"] and not row["implemented"]]
    # These identifiers come from the fixed registry, never model text.
    for row in audit:
        metadata = row.asDict() if hasattr(row, "asDict") else dict(row)
        if metadata.get("applied") and metadata.get("implementation_name") == "conditional_categorical_v1":
            target = metadata.get("target_column")
            parent = {"CLIENT_PRODUCT_CD": "ACCOUNT_TYPE_CD", "TSYS_PRODUCT_CD": "CLIENT_PRODUCT_CD"}.get(target)
            if metadata.get("target_table") != "TKQ_ACCOUNT" or parent is None:
                issues.append("Categorical rule audit refers to an unregistered target.")
                continue
            unsupported = spark.sql(f"""
                SELECT COUNT(*) AS n FROM {tables['TKQ_ACCOUNT']} g
                WHERE g.`{parent}` IS NOT NULL AND g.`{target}` IS NOT NULL AND NOT EXISTS (
                    SELECT 1 FROM {PROFILE_SCHEMA}.categorical_conditional_profile p
                    WHERE p.run_id = :source AND p.profile_type = 'SOURCE'
                      AND p.logical_table_name = 'TKQ_ACCOUNT'
                      AND p.parent_column = :parent AND p.child_column = :child
                      AND p.parent_value = CAST(g.`{parent}` AS STRING)
                      AND p.child_value = CAST(g.`{target}` AS STRING) AND p.record_count > 0
                )
            """, args={"source": source_run_id, "parent": parent, "child": target}).first()["n"]
            if unsupported:
                issues.append(f"{target}: {unsupported} SOURCE-unsupported conditional combinations.")
    print(f"Approved rules without a matching implementation: {len(unimplemented)}")
    for row in unimplemented:
        print(
            f"SKIPPED {row['target_table']}.{row['target_column']} "
            f"(proposal {row['proposal_id']}, batch {row['batch_id']}): {row['reason']}"
        )

    if issues:
        raise GeneratedValidationError("Generated batch failed validation:\n- " + "\n- ".join(issues))

    check_validated_versions(spark, versions)
    return versions
