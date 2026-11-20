"""Persist generation outputs and audits, then publish only the validated batch."""

import json
import pandas as pd
from types import SimpleNamespace

from synthetic_banking.config import CATALOG, PROFILE_SCHEMA, GENERATED_SCHEMA
from synthetic_banking.customer_relationships import AUDIT_TABLE as RELATIONSHIP_AUDIT_TABLE
from synthetic_banking.validation import null_padding_type, validate_generated_batch


def save_generation(spark, result):
    from pyspark.sql import functions as F
    source_run_id, SEED = result.source_run_id, result.settings.seed
    pilot_batch_id = result.settings.proposal_batch_id or result.settings.pilot_batch_id
    expected_schema, rule_events = result.expected_schema, result.rule_events
    relationship_plan = result.relationship_plan
    date_sampler = SimpleNamespace(expected_null_counts=result.date_null_counts)
    N_CUSTOMERS = result.expected_counts["PERSON"]
    total_accounts = result.expected_counts["TKQ_ACCOUNT"]
    total_tradelines = result.expected_counts["TRADELINES"]
    person_df = result.tables["PERSON"]
    customer_account_rel_df = result.tables["CUSTOMER_ACCOUNT_REL"]
    account_df = result.tables["TKQ_ACCOUNT"]
    account_balance_df = result.tables["TKQ_ACCOUNT_BALANCE"]
    tradelines_df = result.tables["TRADELINES"]
    customer_relationship_df = result.tables["CUSTOMER_RELATIONSHIP"]
    from dataclasses import asdict
    from uuid import uuid4

    generated_schema = GENERATED_SCHEMA
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {generated_schema}")
    generation_id = str(uuid4())


    def publish_generation_state(status, validated_versions=None):
        spark.createDataFrame(
            [(generation_id, source_run_id, status, validated_versions, pilot_batch_id or None)],
            """generation_id STRING, source_run_id STRING, status STRING,
               validated_versions MAP<STRING, STRING>, proposal_batch_id STRING""",
        ).write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
            f"{generated_schema}.generation_state"
        )


    publish_generation_state("RUNNING")


    source_objects = {
        row["logical_table_name"]: row["source_object"]
        for row in spark.table(f"{PROFILE_SCHEMA}.source_config").collect()
    }


    def save_generated_table(df, table_name):
        # Add typed NULLs after inference so ungenerated SOURCE columns survive Delta writes.
        null_columns = df.columns[df.isna().all()].tolist()
        populated = df.drop(columns=null_columns)
        if df.empty:
            output = spark.range(0)
        elif populated.shape[1] == 0:
            raise ValueError(f"{table_name} contains rows with no generated values.")
        else:
            output = spark.createDataFrame(populated)

        if null_columns:
            source_fields = {
                field.name.upper(): field.dataType
                for field in spark.table(f"{CATALOG}.{source_objects[table_name]}").schema.fields
            }
            expected_types = {
                column.upper(): data_type
                for column, data_type in expected_schema[table_name].items()
            }
            for column in null_columns:
                expected_type = expected_types.get(column.upper())
                if expected_type is None:
                    raise ValueError(f"{table_name}.{column} has no expected type for an all-null column.")
                data_type = null_padding_type(expected_type, source_fields.get(column.upper()))
                output = output.withColumn(column, F.lit(None).cast(data_type))

        (
            output.select(*(F.col("`" + column.replace("`", "``") + "`") for column in df.columns))
            .write.format("delta")
            .mode("overwrite")
            .option("overwriteSchema", "true")
            .saveAsTable(f"{generated_schema}.{table_name}")
        )


    save_generated_table(
        person_df,
        "PERSON"
    )

    save_generated_table(
        customer_account_rel_df,
        "CUSTOMER_ACCOUNT_REL"
    )

    save_generated_table(
        account_df,
        "TKQ_ACCOUNT"
    )

    save_generated_table(
        account_balance_df,
        "TKQ_ACCOUNT_BALANCE"
    )

    save_generated_table(
        tradelines_df,
        "TRADELINES"
    )

    save_generated_table(customer_relationship_df, "CUSTOMER_RELATIONSHIP")

    # Persist the exact aggregate graph plan; approval status does not describe this base generator.
    spark.createDataFrame(
        [(generation_id, source_run_id, SEED, relationship_plan["implementation_version"], json.dumps(relationship_plan, sort_keys=True))],
        "generation_id STRING, source_run_id STRING, seed BIGINT, implementation_version STRING, plan_json STRING",
    ).withColumn("logged_at", F.current_timestamp()).write.format("delta").mode("append").saveAsTable(
        f"{generated_schema}.{RELATIONSHIP_AUDIT_TABLE}"
    )

    # Publish the audit with the same generation ID before marking the batch completed.
    rule_log = spark.createDataFrame(
        [
            {
                **asdict(event),
                "generation_id": generation_id,
                "source_run_id": source_run_id,
                "seed": SEED,
                # Spark Connect requires a list for an ARRAY field in a local row.
                "parent_columns": list(event.parent_columns),
            }
            for event in rule_events
        ],
        """generation_id STRING, source_run_id STRING, seed BIGINT,
           proposal_id STRING, batch_id STRING, target_table STRING, target_column STRING,
           rule_type STRING, outcome STRING, reason STRING, implementation_name STRING,
           execution_order INT, rows_processed BIGINT, parent_columns ARRAY<STRING>,
           approval_status STRING, proposed BOOLEAN, approved BOOLEAN, implemented BOOLEAN, applied BOOLEAN""",
    ).withColumn("logged_at", F.current_timestamp())
    rule_log.write.format("delta").mode("append").option("mergeSchema", "true").saveAsTable(
        f"{generated_schema}.rule_execution_log"
    )

    expected_counts = {
        "PERSON": N_CUSTOMERS,
        "CUSTOMER_ACCOUNT_REL": total_accounts,
        "TKQ_ACCOUNT": total_accounts,
        "TKQ_ACCOUNT_BALANCE": total_accounts,
        "TRADELINES": total_tradelines,
        "CUSTOMER_RELATIONSHIP": len(customer_relationship_df),
    }
    validated_versions = validate_generated_batch(
        spark, expected_schema, expected_counts, generation_id, source_run_id, len(rule_events),
        expected_date_null_counts=date_sampler.expected_null_counts,
    )
    publish_generation_state("COMPLETED", validated_versions)
    print(f"Completed generation {generation_id}. Rule audit: {generated_schema}.rule_execution_log")
    return generation_id
