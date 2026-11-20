"""Fabricated aggregate-only evidence for the public validation contract."""
import json
from synthetic_banking.validation_reporting import NUMERIC, DATES, FIELDS, CHECKS, CARDINALITIES, BUCKETS, GRAPH, TABLES


def validation_metrics():
    rows = []
    def add(family, entity, column, metric, s, g, **dims):
        row = dict(family=family, entity_name=entity, column_name=column, metric=metric,
                   source_value=s, generated_value=g, difference=(g-s)*(1 if family in ("NUMERIC", "CORRELATION", "DATE_RANGE", "ROW_COUNT") else 100) if s is not None and g is not None else None,
                   comparison_status="COMPARABLE" if s is not None and g is not None else "NOT_COMPARABLE",
                   source_sample_size=100, generated_sample_size=200, dimensions_json=json.dumps(dims))
        rows.append(row)
        return row
    for (key, table, column, _), shift in zip(NUMERIC, (1, 30, 50, 0)):
        for metric, source in (("p25", 100), ("p50", 200), ("p75", 300), ("p95", 400), ("mean_value", 230)):
            add("NUMERIC", table, column, metric, source if key != "overlimit" else 0, source+shift if key != "overlimit" else 0)
    for category, s, g in (("Y", .1, .11), ("N", .9, .89)):
        add("CATEGORICAL", "TKQ_ACCOUNT", "PAST_DUE_INDICATO_CD", "proportion", s, g, category_value=category)
    for _, table, column, _ in FIELDS:
        add("NULL_RATE", table, column, "null_rate", .02, .02)
    for key, table, column, _ in DATES:
        for month, s, g in (("2020-01", .5, .8 if key=="birth" else .51), ("2020-02", .5, .2 if key=="birth" else .49)):
            add("DATE_DISTRIBUTION", table, column, "proportion", s, g, month_bucket=month)
        for metric in ("earliest_date", "latest_date"):
            add("DATE_RANGE", table, column, metric, 18000, 18001)
    for _, entity, _ in CARDINALITIES[:-1]:
        for bin in (1, 2):
            add("CARDINALITY", entity, None, "proportion", .5, .5, cardinality=bin)
        add("CARDINALITY", entity, None, "mean_cardinality", 1.5, 1.5)
    add("CORRELATION", "ACCOUNT", "CREDIT_LIMIT_AMT", "PEARSON_CORRELATION", .8, .2, variable_2="CURRENT_BALANCE_AMT")
    for index, bucket in enumerate(BUCKETS):
        add("CONDITIONAL", "ACCOUNT", "PAST_DUE_INDICATO_CD", "outcome_rate", .1, .11 if index < 4 else .3,
            parent_column="UTILIZATION_RATE", condition_bucket=bucket)
    for _, family, table, metric, _ in CHECKS:
        row = add(family, table, None, metric, 1 if family=="JOIN_COVERAGE" else .01, 1 if family=="JOIN_COVERAGE" else 0)
        row["generated_check_status"]="PASS"
        row["source_count"]=100 if family=="JOIN_COVERAGE" else 1
        row["generated_count"]=200 if family=="JOIN_COVERAGE" else 0
    for metric, value in zip(GRAPH, (1, 0, 0)):
        add("CUSTOMER_RELATIONSHIP", "CUSTOMER_RELATIONSHIP", None, metric, value, value)
    for table in TABLES:
        add("ROW_COUNT", table, None, "row_count", 1000, 2000)
    return rows
