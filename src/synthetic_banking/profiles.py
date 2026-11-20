"""Explicit completed SOURCE selection and generation profile loading."""

from dataclasses import dataclass

from synthetic_banking.config import PROFILE_SCHEMA
from synthetic_banking.relationship_profiles import load_customer_relationship_profile


def select_source_run(spark, requested_source_run_id="", *, no_source_message=None):
    source = spark.sql(f"""
        SELECT run_id
        FROM {PROFILE_SCHEMA}.profile_runs
        WHERE profile_type = 'SOURCE'
          AND status = 'COMPLETED'
          AND completed_at IS NOT NULL
          AND run_id IS NOT NULL
          AND (:requested_source = '' OR run_id = :requested_source)
        ORDER BY completed_at DESC, started_at DESC, run_id DESC
        LIMIT 1
    """, args={"requested_source": requested_source_run_id}).first()
    if source is None:
        if requested_source_run_id:
            raise ValueError(f"Run {requested_source_run_id} is unavailable or is not a completed SOURCE profile.")
        raise RuntimeError(no_source_message or f"No completed SOURCE profiling run found in {PROFILE_SCHEMA}.profile_runs.")
    return source["run_id"]


def validate_pilot_selection(requested_source, batch_id, proposal_ids):
    if batch_id or proposal_ids:
        if (not requested_source or not batch_id or not 1 <= len(proposal_ids) <= 3
            or len(proposal_ids) != len(set(proposal_ids))):
            raise ValueError("Pilot runs require a SOURCE run ID, one batch ID, and one to three distinct proposal IDs.")


@dataclass
class GenerationProfiles:
    source_run_id: str
    column_quality: object
    numeric_stats: object
    category_stats: object
    date_stats: object
    dependency_stats: object
    structural_stats: object
    conditional_stats: object
    customer_relationship_profile: dict
    categorical_relationship_stats: tuple = ()
    categorical_conditional_stats: tuple = ()
    numeric_dependency_stats: tuple = ()


def load_generation_profiles(spark, requested_source_run_id="", *, pilot_batch_id="", pilot_proposal_ids=()):
    from pyspark.sql import functions as F
    validate_pilot_selection(requested_source_run_id, pilot_batch_id, pilot_proposal_ids)
    source_run_id = select_source_run(spark, requested_source_run_id)
    relationships = load_customer_relationship_profile(spark, source_run_id)

    def load(name):
        return spark.table(f"{PROFILE_SCHEMA}.{name}").filter(F.col("run_id") == source_run_id)

    quality = load("column_quality")
    column_quality = quality.toPandas()
    numeric = load("numeric_profile").join(quality, on=["run_id", "logical_table_name", "column_name"], how="inner").select(
        "logical_table_name", "column_name", "row_count", "null_count", "null_pct", "distinct_count",
        "min_value", "p01", "p05", "p25", "p50", "mean_value", "p75", "p95", "p99", "max_value", "stddev_value",
    ).toPandas()
    categories = load("category_profile").select("logical_table_name", "column_name", "category_value", "record_count", "proportion").toPandas()
    dates = load("date_profile").toPandas()
    dependencies = load("relationship_profile").select(F.col("entity_name").alias("relationship_name"), "variable_1", "variable_2", "metric_type", "metric_value").toPandas()
    structural = load("cardinality_profile").select("relationship_name", "cardinality", "entity_count", "proportion").toPandas()
    conditional = load("conditional_profile").toPandas()
    result = GenerationProfiles(source_run_id, column_quality, numeric, categories, dates, dependencies, structural, conditional, relationships)
    for field, table in (("categorical_relationship_stats", "categorical_relationship_profile"),
                         ("categorical_conditional_stats", "categorical_conditional_profile"),
                         ("numeric_dependency_stats", "numeric_dependency_profile")):
        if spark.catalog.tableExists(f"{PROFILE_SCHEMA}.{table}"):
            rows = load(table).filter(F.col("profile_type") == "SOURCE").toPandas().to_dict("records")
            setattr(result, field, tuple(rows))
    print(f"Profiles loaded for SOURCE run {source_run_id}.")
    for label, value in (("Numeric", numeric), ("Categorical", categories), ("Dates", dates), ("Quality", result.column_quality),
                         ("Dependencies", dependencies), ("Structural", structural), ("Conditional", conditional)):
        print(label + ":", len(value))
    return result
