"""Trusted profiling SQL moved unchanged from Notebook 01. Never accept LLM text here."""

from synthetic_banking.config import CATALOG, PROFILE_SCHEMA, GENERATED_SCHEMA, SOURCE_DIR, SOURCE_ALIASES, configured_sql

QUERIES = {
    'metadata': (
        """-- Profiling metadata
USE CATALOG workspace""",
        """CREATE SCHEMA IF NOT EXISTS synthetic_profile""",
    ),
    'column_schema': (
        """CREATE OR REPLACE TEMP VIEW active_column_schema AS

SELECT
    s.logical_table_name,
    s.source_schema,
    s.source_table,
    c.column_name,
    c.ordinal_position,
    c.data_type,
    c.is_nullable

FROM active_profile_inputs s

JOIN workspace.information_schema.columns c
    ON lower(c.table_schema) = lower(s.source_schema)
   AND lower(c.table_name)   = lower(s.source_table)""",
    ),
    'ensure_schema': (
        """USE CATALOG workspace""",
        """CREATE SCHEMA IF NOT EXISTS synthetic_profile""",
    ),
    'quality_table': (
        """CREATE TABLE IF NOT EXISTS workspace.synthetic_profile.column_quality (
    run_id STRING,
    logical_table_name STRING,
    column_name STRING,
    data_type STRING,
    row_count BIGINT,
    non_null_count BIGINT,
    null_count BIGINT,
    null_pct DOUBLE,
    distinct_count BIGINT,
    distinct_pct DOUBLE
)
USING DELTA""",
    ),
    'clear_quality': (
        """DELETE FROM workspace.synthetic_profile.column_quality
WHERE run_id = (
    SELECT run_id
    FROM active_profile_run
)""",
    ),
    'numeric_table': (
        """CREATE TABLE IF NOT EXISTS synthetic_profile.numeric_profile (
    run_id              STRING,
    logical_table_name  STRING,
    column_name         STRING,

    non_null_count      BIGINT,

    min_value           DOUBLE,
    max_value           DOUBLE,
    mean_value          DOUBLE,
    stddev_value        DOUBLE,

    p01                 DOUBLE,
    p05                 DOUBLE,
    p25                 DOUBLE,
    p50                 DOUBLE,
    p75                 DOUBLE,
    p95                 DOUBLE,
    p99                 DOUBLE
)""",
    ),
    'category_table': (
        """CREATE TABLE IF NOT EXISTS synthetic_profile.category_profile (
    run_id              STRING,
    logical_table_name  STRING,
    column_name         STRING,
    category_value      STRING,
    record_count        BIGINT,
    proportion          DOUBLE
)""",
    ),
    'date_table': (
        """CREATE TABLE IF NOT EXISTS synthetic_profile.date_profile (
    run_id              STRING,
    logical_table_name  STRING,
    column_name         STRING,
    non_null_count      BIGINT,
    earliest_date       DATE,
    latest_date         DATE
)""",
    ),
    'relationship_table': (
        """CREATE TABLE IF NOT EXISTS synthetic_profile.relationship_profile (
    run_id            STRING,
    entity_name       STRING,
    variable_1        STRING,
    variable_2        STRING,
    metric_type       STRING,
    metric_value      DOUBLE
)""",
    ),
    'legacy_correlation': (
        """INSERT INTO workspace.synthetic_profile.relationship_profile

SELECT
    (
        SELECT run_id
        FROM active_profile_run
        LIMIT 1
    ) AS run_id,

    'ACCOUNT' AS entity_name,

    'CREDIT_LIMIT_AMT' AS variable_1,

    'CURRENT_BALANCE_AMT' AS variable_2,

    'PEARSON_CORRELATION' AS metric_type,

    corr(
        CREDIT_LIMIT_AMT,
        CURRENT_BALANCE_AMT
    ) AS metric_value

FROM active_account_features""",
    ),
    'conditional_table': (
        """CREATE TABLE IF NOT EXISTS synthetic_profile.conditional_profile (
    run_id             STRING,
    entity_name        STRING,
    condition_variable STRING,
    condition_bucket   STRING,
    outcome_variable   STRING,
    record_count       BIGINT,
    outcome_rate       DOUBLE
)""",
        """CREATE TABLE IF NOT EXISTS synthetic_profile.conditional_profile (
    run_id             STRING,
    entity_name        STRING,
    condition_variable STRING,
    condition_bucket   STRING,
    outcome_variable   STRING,
    record_count       BIGINT,
    outcome_rate       DOUBLE
)""",
    ),
    'conditional_insert': (
        """INSERT INTO synthetic_profile.conditional_profile

SELECT
    r.run_id,

    'ACCOUNT',

    'UTILIZATION_RATE',

    CASE
        WHEN UTILIZATION_RATE IS NULL
            THEN 'NULL'

        WHEN UTILIZATION_RATE < 0.30
            THEN '0-30%'

        WHEN UTILIZATION_RATE < 0.60
            THEN '30-60%'

        WHEN UTILIZATION_RATE < 0.80
            THEN '60-80%'

        WHEN UTILIZATION_RATE <= 1.00
            THEN '80-100%'

        ELSE '100%+'
    END,

    'PAST_DUE_INDICATO_CD',

    COUNT(*),

    AVG(
        CASE
            WHEN PAST_DUE_INDICATO_CD = 'Y'
            THEN 1.0
            ELSE 0.0
        END
    )

FROM active_account_features

CROSS JOIN active_profile_run r

GROUP BY
    r.run_id,

    CASE
        WHEN UTILIZATION_RATE IS NULL THEN 'NULL'
        WHEN UTILIZATION_RATE < 0.30 THEN '0-30%'
        WHEN UTILIZATION_RATE < 0.60 THEN '30-60%'
        WHEN UTILIZATION_RATE < 0.80 THEN '60-80%'
        WHEN UTILIZATION_RATE <= 1.00 THEN '80-100%'
        ELSE '100%+'
    END""",
    ),
    'cardinality_table': (
        """CREATE TABLE IF NOT EXISTS synthetic_profile.cardinality_profile (
    run_id             STRING,
    relationship_name  STRING,
    cardinality        INT,
    entity_count       BIGINT,
    proportion         DOUBLE
)""",
    ),
    'cardinality_insert': (
        """INSERT INTO synthetic_profile.cardinality_profile

SELECT
    r.run_id,

    'ACCOUNTS_PER_PARTY',

    ACCOUNT_COUNT,

    COUNT(*),

    COUNT(*) * 1.0 /
        SUM(COUNT(*)) OVER ()

FROM active_customer_account_features

CROSS JOIN active_profile_run r

GROUP BY
    r.run_id,
    ACCOUNT_COUNT""",
    ),
    'numeric_view': (
        """CREATE OR REPLACE VIEW workspace.synthetic_profile.v_numeric_statistics AS

SELECT
    n.logical_table_name,
    n.column_name,

    q.row_count,
    q.null_count,
    q.null_pct,
    q.distinct_count,

    n.min_value,
    n.p01,
    n.p05,
    n.p25,
    n.p50,
    n.mean_value,
    n.p75,
    n.p95,
    n.p99,
    n.max_value,
    n.stddev_value

FROM workspace.synthetic_profile.numeric_profile n

JOIN workspace.synthetic_profile.column_quality q
    ON n.run_id = q.run_id
   AND n.logical_table_name = q.logical_table_name
   AND n.column_name = q.column_name

WHERE n.run_id = (
    SELECT run_id
    FROM workspace.synthetic_profile.current_run
    LIMIT 1
)""",
    ),
    'category_view': (
        """CREATE OR REPLACE VIEW workspace.synthetic_profile.v_category_statistics AS

SELECT
    c.logical_table_name,
    c.column_name,
    c.category_value,
    c.record_count,
    c.proportion

FROM workspace.synthetic_profile.category_profile c

WHERE c.run_id = (
    SELECT run_id
    FROM workspace.synthetic_profile.current_run
    LIMIT 1
)""",
    ),
    'structural_view': (
        """CREATE OR REPLACE VIEW workspace.synthetic_profile.v_structural_statistics AS

SELECT
    c.relationship_name,
    c.cardinality,
    c.entity_count,
    c.proportion

FROM workspace.synthetic_profile.cardinality_profile c

WHERE c.run_id = (
    SELECT run_id
    FROM workspace.synthetic_profile.current_run
    LIMIT 1
)""",
    ),
    'dependency_view': (
        """CREATE OR REPLACE VIEW workspace.synthetic_profile.v_dependency_statistics AS

SELECT
    rp.entity_name AS relationship_name,
    rp.variable_1,
    rp.variable_2,
    rp.metric_type,
    rp.metric_value

FROM workspace.synthetic_profile.relationship_profile rp

WHERE rp.run_id = (
    SELECT run_id
    FROM workspace.synthetic_profile.current_run
    LIMIT 1
)""",
    ),
}

FEATURE_QUERIES = {
    'account_features': """
SELECT
    a.ACCOUNT_ID,
    a.BUSINESSEFFECTIVEDATE,

    a.ACCOUNT_TYPE_CD,
    a.CLIENT_PRODUCT_CD,
    a.TSYS_PRODUCT_CD,

    a.OPEN_DT,
    a.CLOSE_DT,

    a.CREDIT_LIMIT_AMT,
    a.ORIGINAL_CREDIT_LIMIT_AMT,

    a.CURRENT_CREDIT_SCORE,

    a.DELINQUENCY_CNT,
    a.PAST_DUE_INDICATO_CD,

    a.MINIMUM_PAYMENT_DUE_AMT,

    b.CURRENT_BALANCE_AMT,
    b.AVAILABLE_TO_BUY_AMT,
    b.OVERLIMIT_AMT,

    b.PAYMENT_YTD_AMT,
    b.PURCHASE_YTD_AMT,


    -- Derived utilization


    CASE
        WHEN a.CREDIT_LIMIT_AMT > 0
        THEN b.CURRENT_BALANCE_AMT /
             a.CREDIT_LIMIT_AMT
    END AS UTILIZATION_RATE,

   
    -- Total amount past due
  

    COALESCE(b.AMT_PDUE_1_30, 0)
    + COALESCE(b.AMT_PDUE_31_60, 0)
    + COALESCE(b.AMT_PDUE_61_90, 0)
    + COALESCE(b.AMT_PDUE_91_120, 0)
    + COALESCE(b.AMT_PDUE_121_150, 0)
    + COALESCE(b.AMT_PDUE_151_180, 0)
    + COALESCE(b.AMT_PDUE_181_210, 0)
    + COALESCE(b.AMT_PDUE_211_240, 0)
    + COALESCE(b.AMT_PDUE_241_270, 0)
    + COALESCE(b.AMT_PDUE_271_UP, 0)

        AS TOTAL_PAST_DUE_AMT,

   
    -- Delinquency occurrences
   

    COALESCE(b.NUM_PDUE_1_30, 0)
    + COALESCE(b.NUM_PDUE_31_60, 0)
    + COALESCE(b.NUM_PDUE_61_90, 0)
    + COALESCE(b.NUM_PDUE_91_120, 0)
    + COALESCE(b.NUM_PDUE_121_150, 0)
    + COALESCE(b.NUM_PDUE_151_180, 0)
    + COALESCE(b.NUM_PDUE_181_210, 0)
    + COALESCE(b.NUM_PDUE_211_240, 0)
    + COALESCE(b.NUM_PDUE_241_270, 0)
    + COALESCE(b.NUM_PDUE_271_UP, 0)

        AS TOTAL_PAST_DUE_COUNT,

    -- Account age relative to snapshot
    datediff(
        COALESCE(a.CLOSE_DT, a.BUSINESSEFFECTIVEDATE),
        a.OPEN_DT
    ) AS ACCOUNT_AGE_DAYS,

    datediff(
        a.BUSINESSEFFECTIVEDATE,
        a.LAST_PAYMENT_DT
    ) AS DAYS_SINCE_LAST_PAYMENT,

    datediff(
        a.BUSINESSEFFECTIVEDATE,
        a.LAST_PURCHASE_DT
    ) AS DAYS_SINCE_LAST_PURCHASE

FROM {TKQ_ACCOUNT} a

LEFT JOIN {TKQ_ACCOUNT_BALANCE} b
    ON a.ACCOUNT_ID = b.ACCOUNT_ID
   AND a.BUSINESSEFFECTIVEDATE =
       b.BUSINESSEFFECTIVEDATE
""",
    'customer_account_features': """
SELECT
    PARTY_ID,

    COUNT(DISTINCT ACCT_ID)
        AS ACCOUNT_COUNT,

    SUM(
        CASE
            WHEN PRIMARY_OWNERSHIP_FLAG = 'Y'
            THEN 1
            ELSE 0
        END
    ) AS PRIMARY_ACCOUNT_COUNT

FROM {CUSTOMER_ACCOUNT_REL}

GROUP BY PARTY_ID
""",
    'person_features': """
SELECT
    PARTY_ID,

    CLIENT_STAT_CD,
    CUST_TYPE_CD,
    EMP_TYPE_CD,
    GENDER_CD,
    MARITAL_STAT_CD,
    OCCUP_CAT_CD,
    PREF_LANG_CD,

    BIRTH_DT,
    SINCE_DT,

    FLOOR(
        months_between(current_date(), BIRTH_DT) / 12
    ) AS AGE_YEARS,

    FLOOR(
        months_between(current_date(), SINCE_DT) / 12
    ) AS CUSTOMER_TENURE_YEARS,

    CASE
        WHEN BANKRUPTCY_DT IS NOT NULL
        THEN 1 ELSE 0
    END AS HAS_BANKRUPTCY,

    CASE
        WHEN DECEASED_DT IS NOT NULL
        THEN 1 ELSE 0
    END AS DECEASED_FLAG

FROM {PERSON}
""",
    'tradeline_features': """
SELECT
    `REQ-CIF-KEY`,
    `REQ-CIF-TIE-BREAKER`,

    account_number,
    snapshot_date,

    account_type_code,

    credit_limit_amount,
    current_balance_amount,
    high_credit_amount,
    payment_amount,

    times_30_days_late_count,
    times_60_days_late_count,
    times_90_days_late_count,

    CASE
        WHEN credit_limit_amount > 0
        THEN current_balance_amount /
             credit_limit_amount
    END AS TRADELINE_UTILIZATION_RATE,

    COALESCE(times_30_days_late_count, 0)
    + COALESCE(times_60_days_late_count, 0)
    + COALESCE(times_90_days_late_count, 0)
        AS TOTAL_LATE_COUNT,

    months_between(
        snapshot_date,
        account_open_date
    ) AS TRADELINE_AGE_MONTHS

FROM {TRADELINES}
""",
    'cif_tradeline_counts': """
SELECT
    `REQ-CIF-KEY`,
    `REQ-CIF-TIE-BREAKER`,

    COUNT(*) AS TRADELINE_COUNT,

    SUM(
        CASE
            WHEN account_closed_indicator = 'Y'
            THEN 1
            ELSE 0
        END
    ) AS CLOSED_TRADELINE_COUNT

FROM {TRADELINES}

GROUP BY
    `REQ-CIF-KEY`,
    `REQ-CIF-TIE-BREAKER`
""",
}

def run_profile_sql(spark, name):
    for query in QUERIES[name]:
        spark.sql(configured_sql(query))

