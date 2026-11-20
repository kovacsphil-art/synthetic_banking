"""Existing table-wise marginal profilers, retaining their original Spark aggregations."""

from synthetic_banking.config import CATALOG, PROFILE_SCHEMA, GENERATED_SCHEMA, SOURCE_DIR, SOURCE_ALIASES, configured_sql
from synthetic_banking.profiling_sql import run_profile_sql

def profile_column_quality(spark):
    run_profile_sql(spark, 'quality_table')
    run_profile_sql(spark, 'clear_quality')
    from collections import defaultdict
    from pyspark.sql import functions as F

    # Get current profiling run

    run_id = (
        spark.table("active_profile_run")
        .select("run_id")
        .first()["run_id"]
    )

    # Read column inventory

    inventory = (
        spark.table("active_column_inventory")
        .select(
            "logical_table_name",
            "source_schema",
            "source_table",
            "column_name",
            "data_type"
        )
        .collect()
    )

    # Group columns by source table
    tables = defaultdict(list)

    for row in inventory:
        key = (
            row["logical_table_name"],
            row["source_schema"],
            row["source_table"]
        )

        tables[key].append(
            (
                row["column_name"],
                row["data_type"]
            )
        )

    # Profile one table at a time

    profile_rows = []

    for (
        logical_table_name,
        source_schema,
        source_table
    ), columns in tables.items():

        full_table_name = (
            f"{CATALOG}.{source_schema}.{source_table}"
        )

        print(f"Profiling {full_table_name}")

        df = spark.table(full_table_name)

        # Total number of rows once per table
        row_count = df.count()

        aggregation_expressions = []

        for column_name, data_type in columns:

            c = F.col(column_name)

            aggregation_expressions.extend([
                F.count(c).alias(
                    f"{column_name}__non_null"
                ),

                # Much faster than exact COUNT(DISTINCT)
                F.approx_count_distinct(c).alias(
                    f"{column_name}__distinct"
                )
            ])

        # ONE aggregation query for the entire table
        stats = df.agg(
            *aggregation_expressions
        ).first()

        # Convert wide aggregation results into profiling rows
        for column_name, data_type in columns:

            non_null_count = stats[
                f"{column_name}__non_null"
            ]

            distinct_count = stats[
                f"{column_name}__distinct"
            ]

            null_count = row_count - non_null_count

            null_pct = (
                (null_count / row_count) * 100
                if row_count > 0
                else None
            )

            distinct_pct = (
                (distinct_count / row_count) * 100
                if row_count > 0
                else None
            )

            profile_rows.append({
                "run_id": run_id,
                "logical_table_name": logical_table_name,
                "column_name": column_name,
                "data_type": data_type,
                "row_count": row_count,
                "non_null_count": non_null_count,
                "null_count": null_count,
                "null_pct": null_pct,
                "distinct_count": distinct_count,
                "distinct_pct": distinct_pct
            })

    # Save profiling results

    profile_df = spark.createDataFrame(profile_rows)

    profile_df.write \
        .format("delta") \
        .mode("append") \
        .saveAsTable(
            configured_sql("workspace.synthetic_profile.column_quality")
        )


def profile_numeric(spark):
    run_profile_sql(spark, 'numeric_table')
    from collections import defaultdict
    from pyspark.sql import functions as F

    # NUMERIC PROFILING
    # Profiles all numeric columns table-by-table

    # Current profiling run
    run_id = (
        spark.table("active_profile_run")
        .select("run_id")
        .first()["run_id"]
    )

    # Pull only numeric columns from the inventory
    inventory = (
        spark.table("active_column_inventory")
        .filter(F.col("column_role") == "NUMERIC")
        .select(
            "logical_table_name",
            "source_schema",
            "source_table",
            "column_name"
        )
        .collect()
    )

    # Group numeric columns by source table
    tables = defaultdict(list)

    for row in inventory:
        key = (
            row["logical_table_name"],
            row["source_schema"],
            row["source_table"]
        )

        tables[key].append(row["column_name"])

    # Final rows to write to numeric_profile
    profile_rows = []

    percentile_levels = [
        0.01,
        0.05,
        0.25,
        0.50,
        0.75,
        0.95,
        0.99
    ]

    for (
        logical_table_name,
        source_schema,
        source_table
    ), columns in tables.items():

        full_table_name = (
            f"{CATALOG}.{source_schema}.{source_table}"
        )

        print(
            f"Profiling {logical_table_name}: "
        f"{len(columns)} numeric columns"
        )

        df = spark.table(full_table_name)

        agg_expressions = []

        # Build ALL numeric statistics for this table together

        for i, column_name in enumerate(columns):

            # Escape backticks for unusual column names
            escaped_column = column_name.replace("`", "``")

            numeric_col = F.col(
                f"`{escaped_column}`"
            ).cast("double")

            agg_expressions.extend([

                F.count(numeric_col)
                    .alias(f"c{i}_count"),

                F.min(numeric_col)
                    .alias(f"c{i}_min"),

                F.max(numeric_col)
                    .alias(f"c{i}_max"),

                F.avg(numeric_col)
                    .alias(f"c{i}_mean"),

                F.stddev(numeric_col)
                    .alias(f"c{i}_stddev"),

                F.expr(
                    f"""
                percentile_approx(
                    CAST(`{escaped_column}` AS DOUBLE),
                    array(
                        0.01,
                        0.05,
                        0.25,
                        0.50,
                        0.75,
                        0.95,
                        0.99
                    ),
                    10000
                )
                """
                ).alias(f"c{i}_percentiles")
            ])

        # ONE aggregation job for the entire table
        stats = df.agg(*agg_expressions).first()

        # Convert wide Spark result into one row per variable

        for i, column_name in enumerate(columns):

            percentiles = stats[
                f"c{i}_percentiles"
            ]

            profile_rows.append({
                "run_id": run_id,
                "logical_table_name": logical_table_name,
                "column_name": column_name,

                "non_null_count": stats[
                    f"c{i}_count"
                ],

                "min_value": stats[
                    f"c{i}_min"
                ],

                "max_value": stats[
                    f"c{i}_max"
                ],

                "mean_value": stats[
                    f"c{i}_mean"
                ],

                "stddev_value": stats[
                    f"c{i}_stddev"
                ],

                "p01": (
                    percentiles[0]
                    if percentiles is not None
                    else None
                ),

                "p05": (
                    percentiles[1]
                    if percentiles is not None
                    else None
                ),

                "p25": (
                    percentiles[2]
                    if percentiles is not None
                    else None
                ),

                "p50": (
                    percentiles[3]
                    if percentiles is not None
                    else None
                ),

                "p75": (
                    percentiles[4]
                    if percentiles is not None
                    else None
                ),

                "p95": (
                    percentiles[5]
                    if percentiles is not None
                    else None
                ),

                "p99": (
                    percentiles[6]
                    if percentiles is not None
                    else None
                )
            })

    # Save results to Delta table

    numeric_profile_df = spark.createDataFrame(
        profile_rows
    )

    numeric_profile_df.write \
        .format("delta") \
        .mode("append") \
        .saveAsTable(
            configured_sql("workspace.synthetic_profile.numeric_profile")
        )

    print(
        f"Finished profiling "
    f"{len(profile_rows)} numeric variables."
    )


def profile_categories(spark):
    run_profile_sql(spark, 'category_table')
    from collections import defaultdict
    from pyspark.sql import functions as F
    from pyspark.sql.window import Window

    # CATEGORICAL PROFILING
    # Profiles all low-cardinality categorical columns
    # table-by-table

    # Current profiling run
    run_id = (
        spark.table("active_profile_run")
        .select("run_id")
        .first()["run_id"]
    )

    # ------------------------------------------------------------
    # Find eligible categorical variables
    # ------------------------------------------------------------

    inventory = (
        spark.table("active_column_inventory")
        .alias("i")
    )

    quality = (
        spark.table(configured_sql("workspace.synthetic_profile.column_quality"))
        .filter(F.col("run_id") == run_id)
        .alias("q")
    )

    eligible = (
        inventory
        .join(
            quality,
            (
                F.col("i.logical_table_name")
                == F.col("q.logical_table_name")
            )
            &
            (
                F.col("i.column_name")
                == F.col("q.column_name")
            ),
            "inner"
        )
        .filter(
            (F.col("i.column_role") == "CATEGORICAL_CANDIDATE")
            &
            (F.col("q.distinct_count") <= 100)
        )
        .select(
            F.col("i.logical_table_name"),
            F.col("i.source_schema"),
            F.col("i.source_table"),
            F.col("i.column_name")
        )
        .collect()
    )

    # Group columns by source table

    tables = defaultdict(list)

    for row in eligible:

        key = (
            row["logical_table_name"],
            row["source_schema"],
            row["source_table"]
        )

        tables[key].append(
            row["column_name"]
        )

    # Profile one table at a time

    for (
        logical_table_name,
        source_schema,
        source_table
    ), columns in tables.items():

        if not columns:
            continue

        full_table_name = (
            f"{CATALOG}.{source_schema}.{source_table}"
        )

        print(
            f"Profiling {logical_table_name}: "
        f"{len(columns)} categorical columns"
        )

        df = spark.table(full_table_name)

        # --------------------------------------------------------
        # Convert wide categorical columns into:
        #
        # column_name | category_value
        # ------------|---------------
        # GENDER_CD   | M
        # GENDER_CD   | F
        # EMP_TYPE_CD | FT
        # ...
        #
        # This allows ONE GROUP BY for all categorical columns
        # in this table.
        # --------------------------------------------------------

        category_structs = []

        for column_name in columns:

            escaped_column = (
                column_name.replace("`", "``")
            )

            category_structs.append(
                F.struct(
                    F.lit(column_name).alias(
                        "column_name"
                    ),
                    F.col(
                        f"`{escaped_column}`"
                    ).cast("string").alias(
                        "category_value"
                    )
                )
            )

        long_df = (
            df
            .select(
                F.explode(
                    F.array(*category_structs)
                ).alias("category")
            )
            .select(
                F.col(
                    "category.column_name"
                ).alias("column_name"),

                F.col(
                    "category.category_value"
                ).alias("category_value")
            )
        )

        # Count each category
        counts = (
            long_df
            .groupBy(
                "column_name",
                "category_value"
            )
            .agg(
                F.count("*").alias(
                    "record_count"
                )
            )
        )

        # Calculate proportion separately for each variable
        category_window = (
            Window.partitionBy("column_name")
        )

        results = (
            counts
            .withColumn(
                "proportion",
                F.col("record_count")
                /
                F.sum("record_count").over(
                    category_window
                )
            )
            .withColumn(
                "run_id",
                F.lit(run_id)
            )
            .withColumn(
                "logical_table_name",
                F.lit(logical_table_name)
            )
            .select(
                "run_id",
                "logical_table_name",
                "column_name",
                "category_value",
                "record_count",
                "proportion"
            )
        )

        # Write this table's results
        results.write \
            .format("delta") \
            .mode("append") \
            .saveAsTable(
                configured_sql("workspace.synthetic_profile.category_profile")
            )

    print("Categorical profiling complete.")


def profile_dates(spark):
    run_profile_sql(spark, 'date_table')
    from collections import defaultdict
    from pyspark.sql import functions as F

    # DATE / TIMESTAMP PROFILING

    # Current run
    run_id = (
        spark.table("active_profile_run")
        .select("run_id")
        .first()["run_id"]
    )

    # Pull date/timestamp columns
    inventory = (
        spark.table("active_column_inventory")
        .filter(
            F.col("column_role").isin("DATE", "TIMESTAMP")
        )
        .select(
            "logical_table_name",
            "source_schema",
            "source_table",
            "column_name"
        )
        .collect()
    )

    # Group columns by source table
    tables = defaultdict(list)

    for row in inventory:
        key = (
            row["logical_table_name"],
            row["source_schema"],
            row["source_table"]
        )

        tables[key].append(row["column_name"])

    profile_rows = []

    # Profile one table at a time

    for (
        logical_table_name,
        source_schema,
        source_table
    ), columns in tables.items():

        full_table_name = (
            f"{CATALOG}.{source_schema}.{source_table}"
        )

        print(
            f"Profiling {logical_table_name}: "
        f"{len(columns)} date/timestamp columns"
        )

        df = spark.table(full_table_name)

        agg_expressions = []

        for i, column_name in enumerate(columns):

            escaped_column = (
                column_name.replace("`", "``")
            )

            date_col = F.col(
                f"`{escaped_column}`"
            ).cast("date")

            agg_expressions.extend([
                F.count(
                    F.col(f"`{escaped_column}`")
                ).alias(f"c{i}_count"),

                F.min(date_col)
                    .alias(f"c{i}_min"),

                F.max(date_col)
                    .alias(f"c{i}_max")
            ])

        # ONE aggregation for all date columns in the table
        stats = df.agg(
            *agg_expressions
        ).first()

        for i, column_name in enumerate(columns):

            profile_rows.append({
                "run_id": run_id,
                "logical_table_name": logical_table_name,
                "column_name": column_name,

                "non_null_count":
                    stats[f"c{i}_count"],

                "earliest_date":
                    stats[f"c{i}_min"],

                "latest_date":
                    stats[f"c{i}_max"]
            })

    # Save results

    if profile_rows:

        date_profile_df = spark.createDataFrame(
            profile_rows
        )

        date_profile_df.write \
            .format("delta") \
            .mode("append") \
            .saveAsTable(
                configured_sql("workspace.synthetic_profile.date_profile")
            )

    print(
        f"Finished profiling "
    f"{len(profile_rows)} date/timestamp variables."
    )

