"""Explicit day-level temporal constraints shared by generation and validation."""


ACCOUNT_ACTIVITY_DATES = (
    "FIRST_USE_DT", "LAST_PAYMENT_DT", "LAST_PURCHASE_DT", "LAST_FINANCIAL_ACTIVITY_DT",
    "HIGH_BALANCE_DT", "LAST_CASH_ADVANCE_DT", "FIRST_DLQ_DATE", "LAST_PAST_DUE_DT",
    "CHARGE_OFF_DT", "CREDIT_REVOKE_DT", "CREDIT_REVOKE_STATUS_DT",
)
TEMPORAL_ORDER = {
    "PERSON": (("BIRTH_DT", "SINCE_DT"),),
    "CUSTOMER_RELATIONSHIP": (("START_DT", "END_DT"), ("EFFECTIVE_START_DT", "EFFECTIVE_END_DT")),
    "TKQ_ACCOUNT": (
        ("OPEN_DT", "CLOSE_DT"), ("OPEN_DT", "CLOSE_STATUS_DT"), ("OPEN_DT", "BUSINESSEFFECTIVEDATE"),
        *(("OPEN_DT", column) for column in ACCOUNT_ACTIVITY_DATES),
        *((column, "BUSINESSEFFECTIVEDATE") for column in ACCOUNT_ACTIVITY_DATES),
        ("FIRST_DLQ_DATE", "LAST_PAST_DUE_DT"),
        ("LAST_PAYMENT_DT", "LAST_FINANCIAL_ACTIVITY_DT"),
        ("LAST_PURCHASE_DT", "LAST_FINANCIAL_ACTIVITY_DT"),
    ),
    "TRADELINES": (
        ("account_open_date", "account_closed_date"),
        ("account_open_date", "account_paid_out_date"),
        ("account_open_date", "snapshot_date"),
        ("account_open_date", "last_activity_date"),
        ("account_open_date", "payment_pattern_start_date"),
        ("last_activity_date", "snapshot_date"),
        ("payment_pattern_start_date", "snapshot_date"),
    ),
}


def temporal_checks(spark, tables, temporal_columns):
    """Return aggregate violations; missing columns and empty eligible pairs are explicit.

    Null endpoints are not fabricated. Ordering applies where both dates exist.
    The schema/version and null-rate validators handle missing required data.
    """
    checks = []
    for table, rules in TEMPORAL_ORDER.items():
        names = {name.upper(): name for name in temporal_columns.get(table, ())}
        for parent, child in rules:
            metric = f"{parent}<={child}"
            row = {"logical_table_name": table, "metric": metric, "numerator": None,
                   "denominator": None, "profile_status": "UNAVAILABLE", "reason": "missing_temporal_columns"}
            if table in tables and parent.upper() in names and child.upper() in names:
                def quoted(name):
                    return "`" + names[name.upper()].replace("`", "``") + "`"
                first, second = (f"CAST({quoted(name)} AS DATE)" for name in (parent, child))
                result = spark.sql(f"""
                    SELECT COUNT(*) AS denominator,
                        COUNT(CASE WHEN {second} < {first} THEN 1 END) AS numerator
                    FROM {tables[table]}
                    WHERE {quoted(parent)} IS NOT NULL AND {quoted(child)} IS NOT NULL
                """).collect()[0]
                row.update(numerator=result["numerator"], denominator=result["denominator"],
                           profile_status="MEASURED" if result["denominator"] else "EMPTY",
                           reason=None if result["denominator"] else "no_non_null_date_pairs")
            checks.append(row)
    return checks
