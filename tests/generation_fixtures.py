"""Fabricated profiles for extraction parity; never load real SOURCE rows."""

from contextlib import redirect_stdout
from io import StringIO
import hashlib
import json
from types import SimpleNamespace

import numpy as np


def fabricated_profiles():
    import pandas as pd
    from synthetic_banking.dates import DateSampler
    from synthetic_banking.relationship_profiles import profile_customer_relationships, load_customer_relationship_profile
    from test_customer_relationships import RelationshipSpark, edge
    spark = RelationshipSpark(["FAKE-SOURCE-A", "FAKE-SOURCE-B"], [edge("FAKE-SOURCE-A", "FAKE-SOURCE-B")])
    with redirect_stdout(StringIO()):
        profile_customer_relationships(spark, spark.inputs)
    spark.complete()
    relationship = load_customer_relationship_profile(spark, "source-A")
    spark.db.close()
    categories, numeric, quality, dates, months = [], [], list(relationship["column_quality"]), [], []

    def q(table, column, kind, null_pct=0):
        quality.append(dict(run_id="source-A", logical_table_name=table, column_name=column, data_type=kind,
                            row_count=100, null_count=int(null_pct), null_pct=null_pct))

    def cat(table, column, null_pct=0):
        for value, p in (("FAKE-A", .6), ("FAKE-B", .4)):
            categories.append(dict(logical_table_name=table, column_name=column, category_value=value, proportion=p))
        q(table, column, "STRING", null_pct)

    def num(table, column, a, b, null_pct=0):
        values = np.linspace(a, b, 9)
        row = dict(logical_table_name=table, column_name=column)
        row.update(zip(("min_value", "p01", "p05", "p25", "p50", "p75", "p95", "p99", "max_value"), values))
        numeric.append(row)
        q(table, column, "DOUBLE", null_pct)

    def dt(table, column, earliest, latest, bins, nulls=0):
        common = dict(run_id="source-A", logical_table_name=table, column_name=column)
        dates.append(dict(common, earliest_date=earliest, latest_date=latest, non_null_count=100 - nulls))
        for month, count in bins:
            months.append(dict(common, profile_type="SOURCE", month_bucket=month, record_count=count,
                               non_null_count=100 - nulls, proportion=count / (100 - nulls)))
        q(table, column, "DATE", nulls)

    q("PERSON", "PARTY_ID", "STRING")
    cat("PERSON", "TEST_CD", 10)
    num("PERSON", "INCOME_AMT", 100, 1000, 15)
    dt("PERSON", "BIRTH_DT", "1980-01-01", "2000-01-31", [("1980-01", 45), ("2000-01", 45)], 10)
    dt("PERSON", "SINCE_DT", "2000-01-01", "2020-01-31", [("2000-01", 40), ("2020-01", 40)], 20)
    q("TKQ_ACCOUNT", "ACCOUNT_ID", "STRING")
    cat("TKQ_ACCOUNT", "CLIENT_PRODUCT_CD")
    num("TKQ_ACCOUNT", "CREDIT_LIMIT_AMT", 500, 5000)
    num("TKQ_ACCOUNT", "CURRENT_CREDIT_SCORE", 500, 800)
    num("TKQ_ACCOUNT", "DELINQUENCY_CNT", 0, 5)
    q("TKQ_ACCOUNT", "PAST_DUE_INDICATO_CD", "STRING")
    q("TKQ_ACCOUNT", "_UTILIZATION_RATE", "DOUBLE")
    dt("TKQ_ACCOUNT", "OPEN_DT", "2020-01-01", "2025-01-31", [("2020-01", 50), ("2025-01", 50)])
    dt("TKQ_ACCOUNT", "CLOSE_DT", "2024-01-01", "2026-01-31", [("2024-01", 10), ("2026-01", 10)], 80)
    q("TKQ_ACCOUNT_BALANCE", "ACCOUNT_ID", "STRING")
    num("TKQ_ACCOUNT_BALANCE", "CURRENT_BALANCE_AMT", 100, 8000)
    num("TKQ_ACCOUNT_BALANCE", "PAYMENT_YTD_AMT", 50, 1000, 5)
    cat("TKQ_ACCOUNT_BALANCE", "TEST_CD", 20)
    for field in ("AVAILABLE_TO_BUY_AMT", "OVERLIMIT_AMT"):
        q("TKQ_ACCOUNT_BALANCE", field, "DOUBLE")
    for table in ("TKQ_ACCOUNT", "TKQ_ACCOUNT_BALANCE"):
        dt(table, "BUSINESSEFFECTIVEDATE", "2026-09-30", "2026-09-30", [("2026-09", 100)])
    q("CUSTOMER_ACCOUNT_REL", "PARTY_ID", "STRING")
    q("CUSTOMER_ACCOUNT_REL", "ACCT_ID", "STRING")
    cat("CUSTOMER_ACCOUNT_REL", "RELATN_TYPE_CD", 5)
    cat("TRADELINES", "account_type_code", 10)
    num("TRADELINES", "current_balance_amount", 1, 999, 12)
    for field, kind in (("account_number", "STRING"), ("REQ-CIF-KEY", "STRING"), ("REQ-CIF-TIE-BREAKER", "BIGINT")):
        q("TRADELINES", field, kind)
    dt("TRADELINES", "account_open_date", "2015-01-01", "2020-01-31", [("2015-01", 50), ("2020-01", 50)])
    dt("TRADELINES", "snapshot_date", "2026-09-30", "2026-09-30", [("2026-09", 100)])
    dates.append(dict(run_id="source-A", logical_table_name="CUSTOMER_RELATIONSHIP", column_name="OWNED_BUS_SINCE_DT",
                      earliest_date=None, latest_date=None, non_null_count=0))
    structural = pd.DataFrame([
        dict(relationship_name="ACCOUNTS_PER_PARTY", cardinality=1, proportion=.6),
        dict(relationship_name="ACCOUNTS_PER_PARTY", cardinality=2, proportion=.4),
    ])
    conditional = pd.DataFrame([dict(run_id="source-A", entity_name="ACCOUNT", condition_variable="UTILIZATION_RATE",
                                    outcome_variable="PAST_DUE_INDICATO_CD", condition_bucket=bucket, record_count=100, outcome_rate=rate)
                                for bucket, rate in (("0-30%", .1), ("30-60%", .2), ("60-80%", .3), ("80-100%", .4), ("100%+", .5))])
    profiles = SimpleNamespace(source_run_id="source-A", column_quality=pd.DataFrame(quality), numeric_stats=pd.DataFrame(numeric),
                               category_stats=pd.DataFrame(categories), date_stats=pd.DataFrame(dates),
                               dependency_stats=pd.DataFrame(), structural_stats=structural, conditional_stats=conditional,
                               customer_relationship_profile=relationship)
    def date_sampler(seed):
        return DateSampler("source-A", seed, dates, months, quality)
    return profiles, date_sampler


def fingerprint(tables, rule_events, rng_state, plan):
    import pandas as pd
    def scalar(value):
        if value is None or pd.isna(value): return None
        if hasattr(value, "isoformat"): return value.isoformat()
        if isinstance(value, (float, np.floating)): return float(value).hex()
        if isinstance(value, np.generic): return value.item()
        return value
    hashes = {}
    for name, frame in tables.items():
        rows = [[scalar(value) for value in row] for row in frame.itertuples(index=False, name=None)]
        text = json.dumps({"columns": list(frame.columns), "rows": rows}, sort_keys=True)
        hashes[name] = {"rows": len(frame), "sha256": hashlib.sha256(text.encode()).hexdigest()}
    from dataclasses import asdict
    return {"tables": hashes, "rule_events": [asdict(event) for event in rule_events], "rng_state": rng_state, "relationship_plan": plan}
