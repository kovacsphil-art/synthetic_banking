"""Profiling input selection and lifecycle. SOURCE and GENERATED remain explicit."""

from dataclasses import dataclass
from synthetic_banking.config import CATALOG, PROFILE_SCHEMA, GENERATED_SCHEMA, STAGING_SCHEMA, SOURCE_DIR, SOURCE_ALIASES, configured_sql
from synthetic_banking.profiling_sql import run_profile_sql, FEATURE_QUERIES

@dataclass
class ProfilingInputs:
    profile_type: str
    generation_id: str | None
    baseline_source_run_id: str | None
    profile_inputs: dict


def load_source_inputs(spark, dbutils, profile_type, source_dir=SOURCE_DIR):
    if profile_type not in ("SOURCE", "GENERATED"):
        raise ValueError("Set the profile_type widget to SOURCE or GENERATED and run the notebook from the top.")

    source_aliases = SOURCE_ALIASES

    if profile_type == "SOURCE":
        # Check all required inputs before writing any staging tables.
        source_files = {name: f"RCAR_synthetic_{name}.parquet" for name in source_aliases}
        try:
            available_files = {entry.name.rstrip("/") for entry in dbutils.fs.ls(source_dir)}
        except Exception as error:
            raise RuntimeError(
                f"SOURCE preflight could not list {source_dir}. Check source_dir and volume read access."
            ) from error

        missing_paths = [
            f"{source_dir.rstrip('/')}/{name}" for name in source_files.values() if name not in available_files
        ]
        if missing_paths:
            raise FileNotFoundError(
                "SOURCE preflight is missing required Parquet inputs. Add the inputs or update source_dir.\n"
                + "\n".join(missing_paths)
            )

        for logical_name, filename in source_files.items():
            path = f"{source_dir.rstrip('/')}/{filename}"
            spark.read.parquet(path).write.format("delta").mode("overwrite").option(
                "overwriteSchema", "true"
            ).saveAsTable(f"{STAGING_SCHEMA}.{logical_name}")


def create_source_aliases(spark, profile_type):
    source_aliases = SOURCE_ALIASES
    if profile_type == "SOURCE":
        for schema in ("bronze_cis_mdm", "bronze_tsys", "bronze_transunion"):
            spark.sql(configured_sql(f"CREATE SCHEMA IF NOT EXISTS workspace.{schema}"))

        for logical_name, alias in source_aliases.items():
            spark.sql(
                configured_sql(f"CREATE OR REPLACE VIEW workspace.{alias} AS "
            f"SELECT * FROM workspace.default.{logical_name}")
            )

def completed_generation(spark):
    from synthetic_banking.validation import check_validated_versions
    generation_state_table = f"{GENERATED_SCHEMA}.generation_state"
    if not spark.catalog.tableExists(generation_state_table):
        raise RuntimeError("Run Notebook 03 through the Delta save cell before profiling GENERATED data.")

    state = spark.table(generation_state_table).take(2)
    if (
        len(state) != 1
        or state[0]["status"] != "COMPLETED"
        or not state[0]["generation_id"]
        or not state[0]["source_run_id"]
    ):
        raise RuntimeError("There is no completed generation batch. Run Notebook 03 through the Delta save cell.")
    check_validated_versions(spark, state[0].asDict().get("validated_versions"))
    return state[0]



def configure_profile_inputs(spark, profile_type, expected_generation_id=""):
    from pyspark.sql import functions as F
    source_aliases = SOURCE_ALIASES
    generation_id = None
    baseline_source_run_id = None
    if profile_type == "SOURCE":
        input_objects = source_aliases
    else:
        generation = completed_generation(spark)
        generation_id = generation["generation_id"]
        if expected_generation_id and generation_id != expected_generation_id:
            raise RuntimeError(f"Expected generation {expected_generation_id}, but the current batch is {generation_id}.")
        baseline_source_run_id = generation["source_run_id"]
        baseline = (
            spark.table(configured_sql("workspace.synthetic_profile.profile_runs"))
            .filter(
                (F.col("run_id") == baseline_source_run_id)
                & (F.col("profile_type") == "SOURCE")
                & (F.col("status") == "COMPLETED")
                & F.col("completed_at").isNotNull()
            )
            .first()
        )
        if baseline is None:
            raise RuntimeError(f"Generation references an unavailable SOURCE profile: {baseline_source_run_id}.")

        # Notebook 03 writes all six logical tables, including CUSTOMER_RELATIONSHIP.
        input_objects = {
            name: f"{GENERATED_SCHEMA.split('.', 1)[1]}.{name}"
            for name in source_aliases
        }

    profile_inputs = {name: f"{CATALOG}.{obj}" for name, obj in input_objects.items()}
    missing_inputs = [obj for obj in profile_inputs.values() if not spark.catalog.tableExists(obj)]
    if missing_inputs:
        raise RuntimeError(f"Missing {profile_type} profiling inputs: {', '.join(missing_inputs)}")

    for name, obj in profile_inputs.items():
        spark.table(obj).createOrReplaceTempView(f"profile_input_{name.lower()}")

    input_config = spark.createDataFrame(
        [(name, *obj.split("."), obj) for name, obj in input_objects.items()],
        "logical_table_name STRING, source_schema STRING, source_table STRING, source_object STRING",
    )
    input_config.createOrReplaceTempView("active_profile_inputs")
    if profile_type == "SOURCE":
        input_config.write.format("delta").mode("overwrite").saveAsTable(
            configured_sql("workspace.synthetic_profile.source_config")
        )

    print(f"{profile_type} inputs: {', '.join(profile_inputs.values())}")

    return ProfilingInputs(profile_type, generation_id, baseline_source_run_id, profile_inputs)


def begin_profile_run(spark, inputs):
    profile_type = inputs.profile_type
    baseline_source_run_id = inputs.baseline_source_run_id
    generation_id = inputs.generation_id
    from datetime import datetime, timezone
    from uuid import uuid4

    spark.sql(configured_sql("""
CREATE TABLE IF NOT EXISTS workspace.synthetic_profile.profile_runs (
    run_id STRING,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    status STRING,
    profile_type STRING
) USING DELTA
"""))
    spark.sql(configured_sql("""
CREATE TABLE IF NOT EXISTS workspace.synthetic_profile.current_run (
    run_id STRING,
    started_at TIMESTAMP
) USING DELTA
"""))

    run_id = str(uuid4())
    spark.createDataFrame(
        [(run_id, datetime.now(timezone.utc), profile_type, baseline_source_run_id, generation_id)],
        "run_id STRING, started_at TIMESTAMP, profile_type STRING, source_run_id STRING, generation_id STRING",
    ).createOrReplaceTempView("active_profile_run")

    spark.sql(configured_sql("""
INSERT INTO workspace.synthetic_profile.profile_runs
    (run_id, started_at, completed_at, status, profile_type)
SELECT run_id, started_at, CAST(NULL AS TIMESTAMP), 'RUNNING', profile_type
FROM active_profile_run
"""))
    print(f"Started {profile_type} profile {run_id}.")
    if generation_id:
        print(f"Generation {generation_id} will be profiled against SOURCE run {baseline_source_run_id}.")
    return run_id


def prepare_column_inventory(spark, inputs):
    run_profile_sql(spark, "column_schema")
    profile_type = inputs.profile_type
    inventory_df = spark.sql(configured_sql("""
SELECT
    *,
    CASE

        WHEN upper(column_name) IN (
            'PARTY_ID',
            'FROM_PARTY_ID',
            'TO_PARTY_ID',
            'ACCT_ID',
            'ACCOUNT_ID',
            'ACCOUNT_NUMBER',
            'REQ-CIF-KEY',
            'REQ-CIF-TIE-BREAKER'
        )
        THEN 'IDENTIFIER'

        WHEN upper(data_type) IN (
            'BYTE', 'SHORT', 'INT', 'INTEGER',
            'LONG', 'BIGINT',
            'FLOAT', 'DOUBLE',
            'DECIMAL'
        )
        THEN 'NUMERIC'

        WHEN upper(data_type) IN ('DATE')
        THEN 'DATE'

        WHEN upper(data_type) IN (
            'TIMESTAMP',
            'TIMESTAMP_NTZ'
        )
        THEN 'TIMESTAMP'

        WHEN upper(data_type) IN ('STRING', 'VARCHAR', 'CHAR')
        THEN 'CATEGORICAL_CANDIDATE'

        ELSE 'OTHER'

    END AS column_role
FROM active_column_schema
"""))
    inventory_df.createOrReplaceTempView("active_column_inventory")
    if profile_type == "SOURCE":
        inventory_df.write.format("delta").mode("overwrite").option(
            "overwriteSchema", "true"
        ).saveAsTable(configured_sql("workspace.synthetic_profile.column_inventory"))


def create_profile_feature(spark, inputs, name):
    profile_type, profile_inputs = inputs.profile_type, inputs.profile_inputs
    query = FEATURE_QUERIES[name]
    # The source view definitions use only fully qualified, allowlisted objects.
    query = query.format(**profile_inputs)
    spark.sql(configured_sql(query)).createOrReplaceTempView(f"active_{name}")
    if profile_type == "SOURCE":
        spark.sql(configured_sql(f"CREATE OR REPLACE VIEW workspace.synthetic_profile.{name} AS {query}"))


def complete_profile_run(spark, inputs, run_id):
    profile_type, generation_id = inputs.profile_type, inputs.generation_id
    if profile_type == "GENERATED" and completed_generation(spark)["generation_id"] != generation_id:
        raise RuntimeError("Generated outputs changed during profiling. Rerun GENERATED profiling.")

    spark.sql(configured_sql("""
UPDATE workspace.synthetic_profile.profile_runs
SET
    completed_at = current_timestamp(),
    status = 'COMPLETED'
WHERE status = 'RUNNING'
  AND run_id = (SELECT run_id FROM active_profile_run)
"""))
    spark.sql(configured_sql("""
INSERT OVERWRITE workspace.synthetic_profile.current_run
SELECT run_id, started_at
FROM active_profile_run
"""))
    print(f"Completed {profile_type} profile {run_id}.")

