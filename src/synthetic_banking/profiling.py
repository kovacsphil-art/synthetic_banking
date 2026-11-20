"""Bounded categorical dependency profiling and aggregate-only LLM evidence."""

from collections import defaultdict
import math


from synthetic_banking.config import PROFILE_SCHEMA
MAX_PAIRS = 12
MAX_CATEGORIES = 20
MAX_CELLS = 200
CATEGORICAL_PAIRS = (
    ("PERSON", "EMP_TYPE_CD", "OCCUP_CAT_CD"),
    ("PERSON", "OCCUP_CAT_CD", "OCCUP_DESC"),
    ("TKQ_ACCOUNT", "ACCOUNT_TYPE_CD", "CLIENT_PRODUCT_CD"),
    ("TKQ_ACCOUNT", "CLIENT_PRODUCT_CD", "TSYS_PRODUCT_CD"),
    ("TKQ_ACCOUNT", "AUTO_PAYMENT_METHOD_CD", "PAST_DUE_INDICATO_CD"),
    ("CUSTOMER_ACCOUNT_REL", "RELATN_TYPE_CD", "PRIMARY_OWNERSHIP_FLAG"),
    ("CUSTOMER_RELATIONSHIP", "FROM_TO_CUST_RELATN_CD", "TO_FROM_CUST_RELATN_CD"),
    ("TRADELINES", "account_type_code", "industry_code"),
    ("TRADELINES", "account_type_code", "current_manner_of_payment_code"),
    ("TRADELINES", "account_closed_indicator", "current_manner_of_payment_code"),
)

SUMMARY_SCHEMA = """
    run_id STRING, profile_type STRING, logical_table_name STRING,
    parent_column STRING, child_column STRING, profile_status STRING, skip_reason STRING,
    table_row_count BIGINT, sample_size BIGINT, excluded_null_count BIGINT, complete_case_fraction DOUBLE,
    parent_distinct_estimate BIGINT, child_distinct_estimate BIGINT,
    parent_cardinality INT, child_cardinality INT, observed_cell_count INT, cell_count INT,
    chi_square DOUBLE, degrees_of_freedom INT, cramers_v DOUBLE,
    min_expected_count DOUBLE, expected_cells_below_five INT, sparse_expected_cell_fraction DOUBLE,
    min_parent_count BIGINT, min_observed_cell_count BIGINT
"""
CELL_SCHEMA = """
    run_id STRING, profile_type STRING, logical_table_name STRING,
    parent_column STRING, child_column STRING, parent_value STRING, child_value STRING,
    record_count BIGINT, parent_count BIGINT, child_count BIGINT,
    joint_proportion DOUBLE, conditional_proportion DOUBLE, expected_count DOUBLE
"""


def categorical_statistics(observed, table_row_count, *, max_categories=MAX_CATEGORIES, max_cells=MAX_CELLS):
    """Calculate full-grid Pearson chi-square and uncorrected Cramér's V from grouped counts.

    Inputs contain only non-null aggregate cells. Conditional denominators are
    parent totals among complete cases, and absent cells have observed count zero.
    """
    counts = {}
    parent_totals, child_totals = defaultdict(int), defaultdict(int)
    for row in observed:
        parent, child, count = row["parent_value"], row["child_value"], row["record_count"]
        if parent is None or child is None or count <= 0 or int(count) != count:
            raise ValueError("Categorical cells must have non-null values and positive integer counts.")
        if (parent, child) in counts:
            raise ValueError("Duplicate categorical aggregate cell.")
        counts[parent, child] = int(count)
        parent_totals[parent] += int(count)
        child_totals[child] += int(count)
    n = sum(counts.values())
    if table_row_count < n or table_row_count < 0:
        raise ValueError("Categorical counts exceed the table count in this profiling run.")
    r, c = len(parent_totals), len(child_totals)
    summary = {
        "profile_status": "PROFILED", "skip_reason": None,
        "sample_size": n, "excluded_null_count": table_row_count - n,
        "complete_case_fraction": n / table_row_count if table_row_count else None,
        "parent_cardinality": r, "child_cardinality": c,
        "observed_cell_count": len(counts), "cell_count": r * c,
        "chi_square": None, "degrees_of_freedom": max(r - 1, 0) * max(c - 1, 0),
        "cramers_v": None, "min_expected_count": None, "expected_cells_below_five": None,
        "sparse_expected_cell_fraction": None,
        "min_parent_count": min(parent_totals.values()) if parent_totals else None,
        "min_observed_cell_count": min(counts.values()) if counts else None,
    }
    if r > max_categories or c > max_categories or r * c > max_cells:
        summary.update(profile_status="SKIPPED", skip_reason="exact_cardinality_limit")
        return summary, []
    if n == 0:
        summary.update(profile_status="EMPTY", skip_reason="no_complete_cases")
        return summary, []

    cells, chi_terms = [], []
    for parent in sorted(parent_totals):
        for child in sorted(child_totals):
            count = counts.get((parent, child), 0)
            expected = parent_totals[parent] * child_totals[child] / n
            chi_terms.append((count - expected) ** 2 / expected)
            cells.append({
                "parent_value": parent, "child_value": child, "record_count": count,
                "parent_count": parent_totals[parent], "child_count": child_totals[child],
                "joint_proportion": count / n, "conditional_proportion": count / parent_totals[parent],
                "expected_count": expected,
            })
    chi_square = math.fsum(chi_terms)
    below_five = sum(cell["expected_count"] < 5 for cell in cells)
    summary.update(
        chi_square=chi_square,
        min_expected_count=min(cell["expected_count"] for cell in cells),
        expected_cells_below_five=below_five,
        sparse_expected_cell_fraction=below_five / len(cells),
    )
    if min(r, c) < 2:
        summary.update(profile_status="CONSTANT", skip_reason="constant_categorical_variable")
    else:
        summary["cramers_v"] = min(1.0, math.sqrt(chi_square / (n * min(r - 1, c - 1))))
    return summary, cells


def _rows(spark, query, args=None):
    return [row.asDict() for row in spark.sql(query, args=args).collect()]


def _active_run(spark):
    active = _rows(spark, "SELECT run_id, profile_type FROM active_profile_run")
    if len(active) != 1 or active[0]["profile_type"] not in ("SOURCE", "GENERATED"):
        raise ValueError("Categorical profiling requires one explicit SOURCE or GENERATED run.")
    run = active[0]
    registered = _rows(spark, f"""
        SELECT status, profile_type FROM {PROFILE_SCHEMA}.profile_runs WHERE run_id = :run_id
    """, {"run_id": run["run_id"]})
    if len(registered) != 1 or registered[0] != {"status": "RUNNING", "profile_type": run["profile_type"]}:
        raise ValueError("Profile categorical dependencies before completing this run. Start a new run to re-profile.")
    return run


def _identifier(value):
    return "`" + value.replace("`", "``") + "`"


def _replace_run(spark, name, schema, rows, run_id):
    table = f"{PROFILE_SCHEMA}.{name}"
    spark.sql(f"CREATE TABLE IF NOT EXISTS {table} ({schema}) USING DELTA")
    view = f"{name}_write"
    spark.createDataFrame(rows, schema).createOrReplaceTempView(view)
    spark.sql(f"""
        INSERT INTO {table} REPLACE WHERE run_id = :run_id SELECT * FROM {view}
    """, args={"run_id": run_id})


def profile_categorical_dependencies(
    spark, profile_inputs, pairs=CATEGORICAL_PAIRS, *, max_categories=MAX_CATEGORIES, max_cells=MAX_CELLS,
):
    """Profile only configured, low-cardinality categorical pairs in the active run."""
    pairs = tuple(pairs)
    if not 1 <= len(pairs) <= MAX_PAIRS or not 2 <= max_categories <= MAX_CATEGORIES or not 4 <= max_cells <= MAX_CELLS:
        raise ValueError("Categorical profiling limits allow 1–12 pairs, 2–20 categories, and 4–200 cells.")
    keys = [(table, frozenset((parent.upper(), child.upper()))) for table, parent, child in pairs]
    if len(set(keys)) != len(keys) or any(len(columns) != 2 for _, columns in keys):
        raise ValueError("Configure unique categorical pairs with two different columns.")
    run = _active_run(spark)
    inventory = _rows(spark, "SELECT logical_table_name, column_name, column_role FROM active_column_inventory")
    categorical = {
        (row["logical_table_name"], row["column_name"].upper()): row["column_name"]
        for row in inventory if row["column_role"] == "CATEGORICAL_CANDIDATE"
    }
    quality_rows = _rows(spark, f"""
        SELECT logical_table_name, column_name, row_count, distinct_count
        FROM {PROFILE_SCHEMA}.column_quality WHERE run_id = :run_id
    """, {"run_id": run["run_id"]})
    quality = {(row["logical_table_name"], row["column_name"].upper()): row for row in quality_rows}
    if len(quality) != len(quality_rows):
        raise ValueError("Duplicate column quality rows in the active run. Restart profiling from the top.")

    summaries, all_cells = [], []
    for table, parent, child in pairs:
        parent = categorical.get((table, parent.upper()), parent)
        child = categorical.get((table, child.upper()), child)
        identity = {**run, "logical_table_name": table, "parent_column": parent, "child_column": child}
        summary = {field.strip().split()[0]: None for field in SUMMARY_SCHEMA.split(",")}
        summary.update(identity, profile_status="SKIPPED", skip_reason="missing_or_non_categorical_column")
        parent_key, child_key = (table, parent.upper()), (table, child.upper())
        if table not in profile_inputs or parent_key not in categorical or child_key not in categorical:
            summaries.append(summary)
            continue
        if parent_key not in quality or child_key not in quality:
            raise ValueError("Missing column quality for an active categorical candidate.")
        parent_quality, child_quality = quality[parent_key], quality[child_key]
        total = parent_quality["row_count"]
        if total is None or total != child_quality["row_count"]:
            raise ValueError("Categorical parent and child have inconsistent table counts.")
        summary.update(
            table_row_count=total, parent_distinct_estimate=parent_quality["distinct_count"],
            child_distinct_estimate=child_quality["distinct_count"],
        )
        estimates = (parent_quality["distinct_count"], child_quality["distinct_count"])
        if any(estimate is None or estimate > max_categories for estimate in estimates):
            summary["skip_reason"] = "estimated_cardinality_limit"
            summaries.append(summary)
            continue
        source = ".".join(_identifier(part) for part in profile_inputs[table].split("."))
        parent_id, child_id = _identifier(parent), _identifier(child)
        observed = _rows(spark, f"""
            SELECT CAST({parent_id} AS STRING) AS parent_value,
                   CAST({child_id} AS STRING) AS child_value, COUNT(*) AS record_count
            FROM {source} WHERE {parent_id} IS NOT NULL AND {child_id} IS NOT NULL
            GROUP BY {parent_id}, {child_id} LIMIT {max_cells + 1}
        """)
        if len(observed) > max_cells:
            summary["skip_reason"] = "observed_cell_limit"
            summaries.append(summary)
            continue
        metrics, cells = categorical_statistics(observed, total, max_categories=max_categories, max_cells=max_cells)
        summary.update(metrics)
        summaries.append(summary)
        all_cells.extend({**identity, **cell} for cell in cells)

    if _active_run(spark) != run:
        raise ValueError("The active profiling run changed while categorical dependencies were calculated.")
    # Notebook 01 marks the run completed after all profiling stages finish.
    _replace_run(spark, "categorical_conditional_profile", CELL_SCHEMA, all_cells, run["run_id"])
    _replace_run(spark, "categorical_relationship_profile", SUMMARY_SCHEMA, summaries, run["run_id"])
    for summary in summaries:
        print(f"{summary['logical_table_name']}.{summary['parent_column']} -> {summary['child_column']}: "
              f"{summary['profile_status']} ({summary['skip_reason'] or 'measured'})")
    return summaries


def load_categorical_evidence(spark, source_run_id, *, max_pairs=4, min_sample_size=50):
    """Load bounded complete cross-tabs from one completed SOURCE run for an LLM prompt."""
    if not source_run_id or not 1 <= max_pairs <= MAX_PAIRS or min_sample_size < 1:
        raise ValueError("Provide a SOURCE run and positive bounded categorical evidence limits.")
    tables = ("categorical_relationship_profile", "categorical_conditional_profile")
    if not all(spark.catalog.tableExists(f"{PROFILE_SCHEMA}.{name}") for name in tables):
        return []
    summaries = _rows(spark, f"""
        SELECT p.logical_table_name, p.parent_column, p.child_column, p.table_row_count,
               p.sample_size, p.excluded_null_count, p.complete_case_fraction,
               p.parent_cardinality, p.child_cardinality, p.cell_count,
               p.chi_square, p.degrees_of_freedom, p.cramers_v,
               p.min_expected_count, p.sparse_expected_cell_fraction,
               p.min_parent_count, p.min_observed_cell_count
        FROM {PROFILE_SCHEMA}.categorical_relationship_profile p
        JOIN {PROFILE_SCHEMA}.profile_runs r ON r.run_id = p.run_id
        WHERE p.run_id = :source_run_id AND p.profile_type = 'SOURCE'
          AND r.profile_type = 'SOURCE' AND r.status = 'COMPLETED' AND r.completed_at IS NOT NULL
          AND p.profile_status = 'PROFILED' AND p.sample_size >= :min_sample_size
          AND p.cell_count <= {MAX_CELLS}
        ORDER BY p.cramers_v DESC, p.sample_size DESC, p.logical_table_name, p.parent_column, p.child_column
        LIMIT :max_pairs
    """, {"source_run_id": source_run_id, "min_sample_size": min_sample_size, "max_pairs": max_pairs})
    evidence = []
    for summary in summaries:
        cells = _rows(spark, f"""
            SELECT parent_value, child_value, record_count, conditional_proportion
            FROM {PROFILE_SCHEMA}.categorical_conditional_profile
            WHERE run_id = :source_run_id AND profile_type = 'SOURCE'
              AND logical_table_name = :table AND parent_column = :parent AND child_column = :child
            ORDER BY parent_value, child_value LIMIT {MAX_CELLS + 1}
        """, {"source_run_id": source_run_id, "table": summary["logical_table_name"],
                "parent": summary["parent_column"], "child": summary["child_column"]})
        if len(cells) != summary["cell_count"] or sum(row["record_count"] for row in cells) != summary["sample_size"]:
            raise ValueError("Categorical evidence is incomplete. Re-profile SOURCE before proposing rules.")
        evidence.append({**summary, "cells": cells})
    return evidence
