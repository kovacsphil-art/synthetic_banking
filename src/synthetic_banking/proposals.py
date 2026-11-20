"""Aggregate-only LLM proposal batches. Model text is stored for review, never executed."""

import json
from synthetic_banking.config import CATALOG, PROFILE_SCHEMA, MODEL_ENDPOINT, configured_sql
from synthetic_banking.profiles import select_source_run

def prepare_proposal_tables(spark):
    proposals_table = configured_sql("workspace.synthetic_profile.ai_rule_proposals")
    batches_table = configured_sql("workspace.synthetic_profile.ai_rule_batches")

    spark.sql(configured_sql("""
CREATE TABLE IF NOT EXISTS workspace.synthetic_profile.ai_rule_batches (
    batch_id STRING,
    source_run_id STRING,
    created_at TIMESTAMP,
    scope_name STRING,
    model_endpoint STRING,
    prompt_sha256 STRING,
    response STRING
) USING DELTA
"""))
    spark.sql(configured_sql("""
CREATE TABLE IF NOT EXISTS workspace.synthetic_profile.ai_rule_proposals (

    proposal_id STRING,
    created_at TIMESTAMP,
    source_run_id STRING,

    target_table STRING,
    target_column STRING,

    rule_type STRING,

    parent_columns ARRAY<STRING>,

    confidence STRING,
    evidence_type STRING,

    statistical_evidence STRING,
    rationale STRING,
    proposed_rule STRING,

    requires_sme_review BOOLEAN,
    approval_status STRING,
    batch_id STRING,
    reviewed_by STRING,
    reviewed_at TIMESTAMP,
    legacy_approval_status STRING

)
USING DELTA
"""))

    # Migrate the original table in place. Rows without a batch predate verifiable provenance.
    provenance_columns = {
        "batch_id": "STRING",
        "reviewed_by": "STRING",
        "reviewed_at": "TIMESTAMP",
        "legacy_approval_status": "STRING",
    }
    existing_columns = set(spark.table(proposals_table).columns)
    missing_columns = [
        f"{name} {data_type}"
        for name, data_type in provenance_columns.items()
        if name not in existing_columns
    ]
    if missing_columns:
        spark.sql(configured_sql(f"ALTER TABLE {proposals_table} ADD COLUMNS ({', '.join(missing_columns)})"))

    spark.sql(configured_sql("""
UPDATE workspace.synthetic_profile.ai_rule_proposals
SET legacy_approval_status = 'APPROVED', approval_status = 'PENDING'
WHERE batch_id IS NULL AND approval_status = 'APPROVED'
"""))


def start_proposal_batch(spark, requested_source_run_id="", *, balance_pilot=False, delinquency_pilot=False):
    from uuid import uuid4
    if balance_pilot and delinquency_pilot:
        raise ValueError("Choose one proposal scope by enabling only one pilot widget.")
    if (balance_pilot or delinquency_pilot) and not requested_source_run_id:
        raise ValueError("Set source_run_id before creating a pilot proposal batch.")

    if delinquency_pilot:
        scope_name = "DELINQUENCY_PILOT"
    else:
        scope_name = "BALANCE_PILOT" if balance_pilot else "ACCOUNT_CORE"

    source_run_id = select_source_run(spark, requested_source_run_id, no_source_message="Complete a SOURCE profile in Notebook 01 before proposing rules.")
    batch_id = str(uuid4())
    spark.createDataFrame(
        [(source_run_id, batch_id, scope_name)],
        "source_run_id STRING, batch_id STRING, scope_name STRING",
    ).createOrReplaceTempView("ai_batch_context")
    return source_run_id, batch_id, scope_name


def build_column_context(spark):
    spark.sql(configured_sql("""
CREATE OR REPLACE TEMP VIEW ai_column_context
AS

WITH category_ranked AS (

    SELECT
        c.logical_table_name,
        c.column_name,
        c.category_value,
        c.proportion,

        ROW_NUMBER() OVER (
            PARTITION BY
                c.logical_table_name,
                c.column_name
            ORDER BY c.proportion DESC, c.category_value
        ) AS rn

    FROM workspace.synthetic_profile.category_profile c

    JOIN ai_batch_context b
        ON c.run_id = b.source_run_id
),

categories AS (

    SELECT
        logical_table_name,
        column_name,

        COLLECT_LIST(
            NAMED_STRUCT(
                'value', category_value,
                'proportion', proportion
            )
        ) AS top_categories

    FROM category_ranked

    WHERE rn <= 10

    GROUP BY
        logical_table_name,
        column_name
)

SELECT
    b.source_run_id,
    b.batch_id,
    b.scope_name,
    q.logical_table_name,
    q.column_name,
    q.data_type,
    CASE
        WHEN upper(q.column_name) IN (
            'PARTY_ID', 'FROM_PARTY_ID', 'TO_PARTY_ID', 'ACCT_ID', 'ACCOUNT_ID',
            'ACCOUNT_NUMBER', 'REQ-CIF-KEY', 'REQ-CIF-TIE-BREAKER'
        ) THEN 'IDENTIFIER'
        WHEN upper(q.data_type) IN (
            'BYTE', 'SHORT', 'INT', 'INTEGER', 'LONG', 'BIGINT',
            'FLOAT', 'DOUBLE', 'DECIMAL'
        ) THEN 'NUMERIC'
        WHEN upper(q.data_type) = 'DATE' THEN 'DATE'
        WHEN upper(q.data_type) IN ('TIMESTAMP', 'TIMESTAMP_NTZ') THEN 'TIMESTAMP'
        WHEN upper(q.data_type) IN ('STRING', 'VARCHAR', 'CHAR') THEN 'CATEGORICAL_CANDIDATE'
        ELSE 'OTHER'
    END AS column_role,

    q.null_pct,
    q.distinct_count,

    n.mean_value,
    n.p25,
    n.p50,
    n.p75,
    n.p95,
    n.stddev_value,

    c.top_categories

FROM workspace.synthetic_profile.column_quality q

JOIN ai_batch_context b
    ON q.run_id = b.source_run_id

LEFT JOIN workspace.synthetic_profile.numeric_profile n
    ON n.run_id = b.source_run_id
   AND n.logical_table_name = q.logical_table_name
   AND n.column_name = q.column_name

LEFT JOIN categories c
    ON c.logical_table_name = q.logical_table_name
   AND c.column_name = q.column_name

WHERE q.logical_table_name IN (
    'TKQ_ACCOUNT',
    'TKQ_ACCOUNT_BALANCE'
);
"""))
    spark.sql(configured_sql("""
CREATE OR REPLACE TEMP VIEW ai_account_rule_input AS

SELECT
    source_run_id,
    batch_id,
    scope_name,

    CONCAT_WS(
        '\n',
        COLLECT_LIST(
            TO_JSON(
                NAMED_STRUCT(
                    'table', logical_table_name,
                    'column', column_name,
                    'type', data_type,
                    'role', column_role,

                    'null_pct', null_pct,
                    'distinct_count', distinct_count,

                    'mean', mean_value,
                    'p25', p25,
                    'p50', p50,
                    'p75', p75,
                    'p95', p95,

                    'top_categories', top_categories
                )
            )
        )
    ) AS profile_summary

FROM ai_column_context
GROUP BY source_run_id, batch_id, scope_name
HAVING COUNT(DISTINCT logical_table_name) = 2;
"""))


def build_model_request(spark):
    from synthetic_banking.profiling import load_categorical_evidence
    from synthetic_banking.numeric_dependencies import load_numeric_evidence

    request = spark.table("ai_account_rule_input").first()
    if request is None or not request["profile_summary"]:
        raise RuntimeError("The selected SOURCE run needs aggregate column profiles for both account tables.")

    # Aggregate evidence is read from the same pinned SOURCE run as the column context.
    conditional_evidence = spark.sql(configured_sql("""
    SELECT condition_bucket, record_count, outcome_rate
    FROM workspace.synthetic_profile.conditional_profile
    WHERE run_id = :source_run_id
      AND entity_name = 'ACCOUNT'
      AND condition_variable = 'UTILIZATION_RATE'
      AND outcome_variable = 'PAST_DUE_INDICATO_CD'
      AND record_count > 0
      AND outcome_rate >= 0 AND outcome_rate <= 1
    ORDER BY condition_bucket
"""), args={"source_run_id": request["source_run_id"]}).collect()
    conditional_evidence = [row.asDict() for row in conditional_evidence]
    if request["scope_name"] == "DELINQUENCY_PILOT":
        buckets = [row["condition_bucket"] for row in conditional_evidence]
        if not buckets or len(buckets) != len(set(buckets)):
            raise RuntimeError("The delinquency pilot requires measured, unique SOURCE utilization buckets.")
    conditional_context = json.dumps({
        "entity": "ACCOUNT",
        "condition_variable": "UTILIZATION_RATE",
        "outcome_variable": "PAST_DUE_INDICATO_CD",
        "buckets": conditional_evidence,
    }, allow_nan=False)

    categorical_evidence = load_categorical_evidence(spark, request["source_run_id"])
    print(f"Including {len(categorical_evidence)} measured categorical relationships from the selected SOURCE run.")
    categorical_context = json.dumps(categorical_evidence, allow_nan=False)

    numeric_evidence = load_numeric_evidence(spark, request["source_run_id"])
    # Keep the first implemented numeric group visible even when stronger unrelated
    # correlations occupy the default bounded advisory selection. All rows are aggregates.
    if request["scope_name"] == "ACCOUNT_CORE" and numeric_evidence:
        sampling_rows = spark.sql(configured_sql("""
            SELECT p.scope, p.segment_value, p.lower_bound, p.upper_bound,
                   p.pair_count, p.pair_fraction, p.profile_status, p.pearson_correlation,
                   p.x_min, p.x_max, p.x_p25, p.x_p50, p.x_p75,
                   p.y_min, p.y_p25, p.y_p50, p.y_p75, p.y_max, p.y_mean
            FROM workspace.synthetic_profile.numeric_dependency_profile p
            JOIN workspace.synthetic_profile.profile_runs r ON p.run_id = r.run_id
            WHERE p.run_id = :source_run_id AND p.profile_type = 'SOURCE'
              AND r.profile_type = 'SOURCE' AND r.status = 'COMPLETED' AND r.completed_at IS NOT NULL
              AND p.entity_name = 'ACCOUNT'
              AND p.variable_1 = 'TKQ_ACCOUNT.CREDIT_LIMIT_AMT'
              AND p.variable_2 = 'TKQ_ACCOUNT_BALANCE.CURRENT_BALANCE_AMT'
              AND p.scope IN ('GLOBAL', 'X_QUARTILE')
            ORDER BY p.scope, p.segment_value LIMIT 6
        """), args={"source_run_id": request["source_run_id"]}).collect()
        if len(sampling_rows) > 5:
            raise ValueError("Duplicate numeric sampling evidence; re-profile SOURCE.")
        if sampling_rows:
            numeric_evidence.append({"generation_candidate": "TKQ_ACCOUNT_BALANCE.CURRENT_BALANCE_AMT",
                "parent": "TKQ_ACCOUNT.CREDIT_LIMIT_AMT", "candidate_rule_type": "CORRELATED",
                "implementation": "conditional_numeric_rank_v1",
                "note": "Measured conditional quantiles guide rank ordering of existing marginal draws. Review is required.",
                "measured_profiles": [row.asDict() for row in sampling_rows]})
    print(f"Including {len(numeric_evidence)} measured numeric relationships from the selected SOURCE run.")
    numeric_context = json.dumps(numeric_evidence, allow_nan=False)

    pilot_instructions = ""
    if request["scope_name"] == "BALANCE_PILOT":
        pilot_instructions = (
            "\n\nBalance pilot scope:\n"
        "Propose at most one DERIVED rule for each of AVAILABLE_TO_BUY_AMT and OVERLIMIT_AMT "
        "on TKQ_ACCOUNT_BALANCE. The only eligible parents are TKQ_ACCOUNT.CREDIT_LIMIT_AMT "
        "and TKQ_ACCOUNT_BALANCE.CURRENT_BALANCE_AMT. The existing formulas are "
        "max(credit limit - current balance, 0) and max(current balance - credit limit, 0), respectively. "
        "Assess these existing dependencies and omit unsupported proposals. "
        "Keep domain inference distinct from statistical evidence and leave other dependencies out."
        )
    elif request["scope_name"] == "DELINQUENCY_PILOT":
        pilot_instructions = (
            "\n\nUtilization / delinquency pilot scope:\n"
        "Propose at most one CONDITIONAL rule for TKQ_ACCOUNT.PAST_DUE_INDICATO_CD, "
        "with exactly one parent, TKQ_ACCOUNT.UTILIZATION_RATE. "
        "Use only the supplied SOURCE conditional-profile outcome rates by utilization bucket. "
        "The implementation looks up the measured bucket rate and samples a Y/N outcome. "
        "Do not invent, smooth, extrapolate, or substitute probabilities. "
        "Omit the proposal when the supplied evidence is insufficient. Leave other dependencies out."
        )

    prompt = """You are assisting with a banking synthetic-data generation system.

You receive ONLY aggregate statistical profiles. You do not have row-level records.

Your task is to propose candidate generation dependencies and business rules.

A good candidate rule must:
1. improve logical or statistical consistency;
2. identify fields that should not be generated independently;
3. distinguish statistical evidence from domain inference;
4. avoid inventing relationships unsupported by the supplied evidence;
5. mark domain-inferred rules for SME review;
6. prefer deterministic DERIVED rules where a field is clearly derived from others;
7. use CONDITIONAL when a target distribution should depend on another variable;
8. use CORRELATED only when a numeric association should be preserved but no deterministic formula is supported;
9. use NO_RULE when independent generation is acceptable or evidence is insufficient.

Do NOT claim causation from correlation.
Conditional probabilities must come from the supplied SOURCE conditional-profile evidence.
Do not invent probabilities or use model estimates in place of measured bucket rates.
For categorical dependencies, use the supplied cross-tabs and conditional proportions.
Cramér's V is a symmetric measure of association, without a causal or directional interpretation.
The configured parent/child direction is a candidate for review. Cite sample size, null exclusions,
and sparse expected-cell diagnostics when judging the evidence. Small samples or sparse cells
require caution even when V is high. Do not infer dependencies from field names alone.
Categorical conditional proportions use complete cases, excluding rows with either value missing.
If categorical evidence is absent or insufficient, omit the dependency or use NO_RULE.

For numeric dependencies, use measured global, categorical-segment, and X-quantile evidence.
Pearson correlation measures linear association symmetrically. It does not establish causation,
a deterministic formula, direction of influence, or that a new generator implementation exists.
A near-zero global correlation does not demonstrate independence. Compare segment correlations,
means, spread and quantiles; flag sign changes, non-linear patterns, and possible mixed populations.
Cite paired sample counts, missing/non-finite exclusions, and pair coverage. Small-segment statistics
may be withheld; do not fill them in. Account counts refer to joined feature rows, not necessarily
unique accounts. Duplicate snapshot keys can weight the evidence; consider recorded join diagnostics.
X-quantile cuts were measured from SOURCE complete finite pairs. Segment summaries are descriptive,
not a fitted conditional sampling model. Do not invent probabilities, formulas, or transformations.
Distinguish mathematical coupling and domain inference from measured association. Proposals remain
advisory and require individual review plus a predefined Python implementation before application.

For each proposed rule identify:
- target table
- target column
- rule type
- parent columns
- confidence: HIGH, MEDIUM, or LOW
- evidence type: STATISTICAL, DOMAIN_INFERENCE, or STATISTICAL_AND_DOMAIN
- statistical evidence
- rationale
- proposed generation rule
- whether SME review is required""" + pilot_instructions + "\n\nHere are the profiler statistics:\n\n" + request["profile_summary"] + "\n\nMeasured conditional evidence:\n" + conditional_context + "\n\nMeasured categorical evidence:\n" + categorical_context + "\n\nMeasured numeric dependency evidence:\n" + numeric_context
    spark.createDataFrame(
        [(request["source_run_id"], request["batch_id"], request["scope_name"], prompt)],
        "source_run_id STRING, batch_id STRING, scope_name STRING, prompt STRING",
    ).createOrReplaceTempView("ai_model_request")
    return request


def call_proposal_model(spark, request):
    from pyspark.sql import functions as F
    batches_table = f"{PROFILE_SCHEMA}.ai_rule_batches"
    if spark.table(batches_table).filter(F.col("batch_id") == request["batch_id"]).first() is None:
        spark.sql(configured_sql("""
    INSERT INTO workspace.synthetic_profile.ai_rule_batches
        (batch_id, source_run_id, created_at, scope_name, model_endpoint, prompt_sha256, response)
    SELECT
        batch_id,
        source_run_id,
        current_timestamp(),
        scope_name,
        :model_endpoint,
        sha2(prompt, 256),
        ai_query(
            :model_endpoint,
            prompt,
            responseFormat => '{
          "type": "json_schema",
          "json_schema": {
            "name": "banking_generation_rules",
            "schema": {
              "type": "object",
              "properties": {
                "rules": {
                  "type": "array",
                  "items": {
                    "type": "object",
                    "properties": {
                      "target_table": {
                        "type": "string"
                      },
                      "target_column": {
                        "type": "string"
                      },
                      "rule_type": {
                        "type": "string"
                      },
                      "parent_columns": {
                        "type": "array",
                        "items": {
                          "type": "string"
                        }
                      },
                      "confidence": {
                        "type": "string"
                      },
                      "evidence_type": {
                        "type": "string"
                      },
                      "statistical_evidence": {
                        "type": "string"
                      },
                      "rationale": {
                        "type": "string"
                      },
                      "proposed_rule": {
                        "type": "string"
                      },
                      "requires_sme_review": {
                        "type": "boolean"
                      }
                    },
                    "required": [
                      "target_table",
                      "target_column",
                      "rule_type",
                      "parent_columns",
                      "confidence",
                      "evidence_type",
                      "statistical_evidence",
                      "rationale",
                      "proposed_rule",
                      "requires_sme_review"
                    ],
                    "additionalProperties": false
                  }
                }
              },
              "required": [
                "rules"
              ],
              "additionalProperties": false
            },
            "strict": true
          }
        }'
        )
    FROM ai_model_request
    """), args={"model_endpoint": MODEL_ENDPOINT})
    else:
        print(f"Reusing the stored response for batch {request['batch_id']}. Run from the top to start a new batch.")


def store_proposals(spark):
    spark.sql(configured_sql("""
CREATE OR REPLACE TEMP VIEW ai_parsed_rule_proposals AS

SELECT
    b.batch_id,
    b.source_run_id,

    FROM_JSON(
        b.response,

        'STRUCT<
            rules:ARRAY<
                STRUCT<
                    target_table:STRING,
                    target_column:STRING,
                    rule_type:STRING,
                    parent_columns:ARRAY<STRING>,
                    confidence:STRING,
                    evidence_type:STRING,
                    statistical_evidence:STRING,
                    rationale:STRING,
                    proposed_rule:STRING,
                    requires_sme_review:BOOLEAN
                >
            >
        >'
    ) AS parsed_response

FROM workspace.synthetic_profile.ai_rule_batches b
JOIN ai_model_request r
    ON b.batch_id = r.batch_id AND b.source_run_id = r.source_run_id;
"""))
    parsed = spark.table("ai_parsed_rule_proposals").selectExpr(
        "parsed_response.rules AS rules"
    ).first()
    if parsed is None or parsed["rules"] is None:
        raise RuntimeError("The stored batch did not return a valid rules array. Inspect its saved response.")

    spark.sql(configured_sql("""
INSERT INTO workspace.synthetic_profile.ai_rule_proposals (
    proposal_id, created_at, source_run_id, target_table, target_column,
    rule_type, parent_columns, confidence, evidence_type, statistical_evidence,
    rationale, proposed_rule, requires_sme_review, approval_status, batch_id
)
SELECT
    uuid(),
    current_timestamp(),
    p.source_run_id,
    rule.target_table,
    rule.target_column,
    rule.rule_type,
    rule.parent_columns,
    rule.confidence,
    rule.evidence_type,
    rule.statistical_evidence,
    rule.rationale,
    rule.proposed_rule,
    rule.requires_sme_review,
    'PENDING',
    p.batch_id
FROM (
    SELECT parsed.*
    FROM ai_parsed_rule_proposals parsed
    LEFT ANTI JOIN workspace.synthetic_profile.ai_rule_proposals stored
        ON parsed.batch_id = stored.batch_id
) p
LATERAL VIEW EXPLODE(p.parsed_response.rules) exploded AS rule
"""))

