"""Bounded numeric dependency evidence; advisory aggregates, never generator code."""

from dataclasses import dataclass
import math

from synthetic_banking.profiling import PROFILE_SCHEMA, _active_run, _identifier, _replace_run, _rows


MAX_PAIRS = 12
MAX_SEGMENTS = 6
TABLE = "numeric_dependency_profile"


@dataclass(frozen=True)
class NumericPair:
    entity_name: str
    variable_1: str
    variable_2: str
    segment_column: str


NUMERIC_PAIRS = (
    NumericPair("ACCOUNT", "TKQ_ACCOUNT.CREDIT_LIMIT_AMT", "TKQ_ACCOUNT_BALANCE.CURRENT_BALANCE_AMT", "TKQ_ACCOUNT.CLIENT_PRODUCT_CD"),
    NumericPair("ACCOUNT", "TKQ_ACCOUNT.CREDIT_LIMIT_AMT", "TKQ_ACCOUNT.ORIGINAL_CREDIT_LIMIT_AMT", "TKQ_ACCOUNT.CLIENT_PRODUCT_CD"),
    NumericPair("ACCOUNT", "TKQ_ACCOUNT_BALANCE.CURRENT_BALANCE_AMT", "TKQ_ACCOUNT.MINIMUM_PAYMENT_DUE_AMT", "TKQ_ACCOUNT.CLIENT_PRODUCT_CD"),
    NumericPair("ACCOUNT", "TKQ_ACCOUNT_BALANCE.CURRENT_BALANCE_AMT", "TKQ_ACCOUNT_BALANCE.PAYMENT_YTD_AMT", "TKQ_ACCOUNT.CLIENT_PRODUCT_CD"),
    NumericPair("ACCOUNT", "TKQ_ACCOUNT_BALANCE.PURCHASE_YTD_AMT", "TKQ_ACCOUNT_BALANCE.PAYMENT_YTD_AMT", "TKQ_ACCOUNT.CLIENT_PRODUCT_CD"),
    NumericPair("ACCOUNT", "TKQ_ACCOUNT_BALANCE.CURRENT_BALANCE_AMT", "TKQ_ACCOUNT.CURRENT_CREDIT_SCORE", "TKQ_ACCOUNT.CLIENT_PRODUCT_CD"),
    NumericPair("ACCOUNT", "TKQ_ACCOUNT_BALANCE.CURRENT_BALANCE_AMT", "TKQ_ACCOUNT_BALANCE.AVAILABLE_TO_BUY_AMT", "TKQ_ACCOUNT.CLIENT_PRODUCT_CD"),
    NumericPair("TRADELINES", "TRADELINES.credit_limit_amount", "TRADELINES.current_balance_amount", "TRADELINES.account_type_code"),
    NumericPair("TRADELINES", "TRADELINES.credit_limit_amount", "TRADELINES.high_credit_amount", "TRADELINES.account_type_code"),
    NumericPair("TRADELINES", "TRADELINES.current_balance_amount", "TRADELINES.payment_amount", "TRADELINES.account_type_code"),
)
_INPUTS = {
    "ACCOUNT": ("active_account_features", {"TKQ_ACCOUNT", "TKQ_ACCOUNT_BALANCE"}),
    "TRADELINES": ("active_tradeline_features", {"TRADELINES"}),
}
_NUMERIC_TYPES = {"byte", "tinyint", "short", "smallint", "int", "integer", "long", "bigint", "float", "real", "double", "decimal", "numeric"}
SCHEMA = """
    run_id STRING, profile_type STRING, entity_name STRING, variable_1 STRING, variable_2 STRING,
    scope STRING, segment_column STRING, segment_value STRING, segment_is_null BOOLEAN,
    lower_bound DOUBLE, upper_bound DOUBLE, segment_count INT,
    population_count BIGINT, non_null_pair_count BIGINT, pair_count BIGINT,
    excluded_null_count BIGINT, excluded_nonfinite_count BIGINT, pair_fraction DOUBLE,
    profile_status STRING, skip_reason STRING, pearson_correlation DOUBLE,
    x_mean DOUBLE, y_mean DOUBLE, x_stddev DOUBLE, y_stddev DOUBLE,
    x_min DOUBLE, x_max DOUBLE, y_min DOUBLE, y_max DOUBLE,
    x_p25 DOUBLE, x_p50 DOUBLE, x_p75 DOUBLE, y_p25 DOUBLE, y_p50 DOUBLE, y_p75 DOUBLE
"""
_STATS = ("pearson_correlation", "x_mean", "y_mean", "x_stddev", "y_stddev", "x_min", "x_max", "y_min", "y_max",
          "x_p25", "x_p50", "x_p75", "y_p25", "y_p50", "y_p75")
_AGGREGATE = """
    COUNT(*) AS population_count,
    COUNT(CASE WHEN x_raw IS NOT NULL AND y_raw IS NOT NULL THEN 1 END) AS non_null_pair_count,
    COUNT(x) AS pair_count,
    CASE WHEN COUNT(x) >= 2 AND STDDEV_SAMP(x) > 0 AND STDDEV_SAMP(y) > 0
         THEN CORR(x, y) END AS pearson_correlation,
    AVG(x) AS x_mean, AVG(y) AS y_mean, STDDEV_SAMP(x) AS x_stddev, STDDEV_SAMP(y) AS y_stddev,
    MIN(x) AS x_min, MAX(x) AS x_max, MIN(y) AS y_min, MAX(y) AS y_max,
    PERCENTILE_APPROX(x, 0.25, 10000) AS x_p25, PERCENTILE_APPROX(x, 0.50, 10000) AS x_p50,
    PERCENTILE_APPROX(x, 0.75, 10000) AS x_p75, PERCENTILE_APPROX(y, 0.25, 10000) AS y_p25,
    PERCENTILE_APPROX(y, 0.50, 10000) AS y_p50, PERCENTILE_APPROX(y, 0.75, 10000) AS y_p75
"""


def _finite(value):
    return value is not None and math.isfinite(float(value))


def _row(identity, scope, raw=None, *, reason=None, segment_column=None, segment_value=None,
         lower=None, upper=None, segment_count=None):
    row = {field.strip().split()[0]: None for field in SCHEMA.split(",")}
    row.update(identity, scope=scope, segment_column=segment_column, segment_value=segment_value,
               segment_is_null=scope == "CATEGORY" and segment_value is None,
               lower_bound=lower, upper_bound=upper, segment_count=segment_count,
               profile_status="SKIPPED", skip_reason=reason)
    if raw is None:
        return row
    for field in ("population_count", "non_null_pair_count", "pair_count"):
        row[field] = int(raw.get(field) or 0)
    total, non_null, n = (row[field] for field in ("population_count", "non_null_pair_count", "pair_count"))
    if not 0 <= n <= non_null <= total:
        raise ValueError("Numeric pair counts are inconsistent.")
    row.update(excluded_null_count=total - non_null, excluded_nonfinite_count=non_null - n,
               pair_fraction=n / total if total else None)
    for field in _STATS:
        row[field] = float(raw[field]) if _finite(raw.get(field)) else None
    if not n:
        status, why = "EMPTY", "no_finite_pairs"
    elif n < 2:
        status, why = "INSUFFICIENT", "fewer_than_two_pairs"
    elif ((row["x_min"] is not None and row["x_min"] == row["x_max"])
          or (row["y_min"] is not None and row["y_min"] == row["y_max"])):
        status, why = "CONSTANT", "constant_variable"
    elif any(row[field] is None for field in _STATS) or abs(row["pearson_correlation"]) > 1 + 1e-8:
        status, why = "SKIPPED", "nonfinite_or_undefined_statistics"
    else:
        status, why = "PROFILED", None
    row.update(profile_status=status, skip_reason=why)
    if status != "PROFILED":
        row["pearson_correlation"] = None
    else:
        row["pearson_correlation"] = max(-1.0, min(1.0, row["pearson_correlation"]))
    return row


def _qualified(variable, tables):
    pieces = variable.split(".")
    if len(pieces) != 2 or pieces[0] not in tables or not pieces[1]:
        raise ValueError("Configure qualified columns from the entity's existing input tables.")
    return pieces[0], pieces[1]


def _source_boundaries(spark, source_run_id):
    if not spark.catalog.tableExists(f"{PROFILE_SCHEMA}.{TABLE}"):
        return {}
    rows = _rows(spark, f"""
        SELECT p.entity_name, p.variable_1, p.variable_2, p.x_p25, p.x_p50, p.x_p75
        FROM {PROFILE_SCHEMA}.{TABLE} p
        JOIN {PROFILE_SCHEMA}.profile_runs r ON r.run_id = p.run_id
        WHERE p.run_id = :source AND p.profile_type = 'SOURCE' AND p.scope = 'GLOBAL'
          AND r.profile_type = 'SOURCE' AND r.status = 'COMPLETED' AND r.completed_at IS NOT NULL
    """, {"source": source_run_id})
    keyed = {(row["entity_name"], row["variable_1"], row["variable_2"]): row for row in rows}
    if len(keyed) != len(rows):
        raise ValueError("Duplicate SOURCE numeric boundaries; re-profile SOURCE from the top.")
    return keyed


def profile_numeric_dependencies(spark, pairs=NUMERIC_PAIRS, *, max_segments=MAX_SEGMENTS):
    """Run only explicitly configured numeric pairs against existing feature views."""
    pairs = tuple(pairs)
    if not 1 <= len(pairs) <= MAX_PAIRS or not 1 <= max_segments <= MAX_SEGMENTS:
        raise ValueError("Numeric profiling permits 1–12 pairs and 1–6 categorical segments.")
    keys = [(pair.entity_name, frozenset((pair.variable_1.upper(), pair.variable_2.upper()))) for pair in pairs]
    if len(set(keys)) != len(keys) or any(len(variables) != 2 for _, variables in keys):
        raise ValueError("Configure distinct numeric pairs; reversed duplicates are not allowed.")
    run = _active_run(spark)
    active = _rows(spark, "SELECT * FROM active_profile_run")[0]
    source_boundaries = {}
    if run["profile_type"] == "GENERATED":
        source = active.get("source_run_id")
        baselines = _rows(spark, f"""
            SELECT run_id FROM {PROFILE_SCHEMA}.profile_runs
            WHERE run_id = :source AND profile_type = 'SOURCE'
              AND status = 'COMPLETED' AND completed_at IS NOT NULL
        """, {"source": source})
        if not source or len(baselines) != 1:
            raise ValueError("GENERATED numeric profiling requires its pinned completed SOURCE run.")
        source_boundaries = _source_boundaries(spark, source)
    inventory = _rows(spark, "SELECT logical_table_name, column_name, column_role FROM active_column_inventory")
    roles = {(r["logical_table_name"], r["column_name"].upper()): r["column_role"] for r in inventory}
    schemas = {}
    results = []
    for pair in pairs:
        if pair.entity_name not in _INPUTS:
            raise ValueError("Numeric pairs must use ACCOUNT or TRADELINES feature inputs.")
        view, tables = _INPUTS[pair.entity_name]
        first, second, segment = (_qualified(variable, tables) for variable in (pair.variable_1, pair.variable_2, pair.segment_column))
        identity = {**run, "entity_name": pair.entity_name, "variable_1": pair.variable_1, "variable_2": pair.variable_2}
        if view not in schemas:
            schemas[view] = {name.upper(): (name, data_type.lower().split("(", 1)[0]) for name, data_type in spark.table(view).dtypes} if spark.catalog.tableExists(view) else {}
        schema = schemas[view]
        if any(column.upper() not in schema for _, column in (first, second)):
            results.append(_row(identity, "GLOBAL", reason="missing_input_or_numeric_column"))
            continue
        if any(roles.get((table, column.upper())) != "NUMERIC" or schema[column.upper()][1] not in _NUMERIC_TYPES for table, column in (first, second)):
            results.append(_row(identity, "GLOBAL", reason="not_classified_numeric"))
            continue
        x, y = (_identifier(schema[column.upper()][0]) for _, column in (first, second))
        segment_ok = (segment[1].upper() in schema and roles.get((segment[0], segment[1].upper())) == "CATEGORICAL_CANDIDATE")
        segment_expr = _identifier(schema[segment[1].upper()][0]) if segment_ok else "NULL"
        cte = f"""
            WITH raw_pairs AS (
                SELECT CAST({x} AS DOUBLE) AS x_raw, CAST({y} AS DOUBLE) AS y_raw,
                       CAST({segment_expr} AS STRING) AS segment_value FROM {_identifier(view)}
            ), clean_pairs AS (
                SELECT *,
                    CASE WHEN x_raw IS NOT NULL AND y_raw IS NOT NULL AND NOT ISNAN(x_raw) AND NOT ISNAN(y_raw)
                         AND ABS(x_raw) <= 1.7976931348623157e308 AND ABS(y_raw) <= 1.7976931348623157e308 THEN x_raw END AS x,
                    CASE WHEN x_raw IS NOT NULL AND y_raw IS NOT NULL AND NOT ISNAN(x_raw) AND NOT ISNAN(y_raw)
                         AND ABS(x_raw) <= 1.7976931348623157e308 AND ABS(y_raw) <= 1.7976931348623157e308 THEN y_raw END AS y
                FROM raw_pairs
            )
        """
        global_raw = _rows(spark, cte + f"""
            SELECT {_AGGREGATE}, COUNT(DISTINCT segment_value) +
                CASE WHEN COUNT(*) > COUNT(segment_value) THEN 1 ELSE 0 END AS segment_count FROM clean_pairs
        """)[0]
        segment_count = int(global_raw["segment_count"]) if segment_ok else None
        global_row = _row(identity, "GLOBAL", global_raw, segment_count=segment_count)
        results.append(global_row)
        if not segment_ok or segment_count > max_segments:
            results.append(_row(identity, "CATEGORY_STATUS", segment_column=pair.segment_column,
                                segment_count=segment_count, reason="missing_or_non_categorical_segment" if not segment_ok else "segment_cardinality_limit"))
        else:
            segmented = _rows(spark, cte + f"SELECT segment_value, {_AGGREGATE} FROM clean_pairs GROUP BY segment_value LIMIT {MAX_SEGMENTS + 1}")
            if len(segmented) != segment_count:
                raise ValueError("Categorical segments changed while numeric profiling was running.")
            for row in sorted(segmented, key=lambda row: (row["segment_value"] is not None, row["segment_value"] or "")):
                results.append(_row(identity, "CATEGORY", row, segment_column=pair.segment_column, segment_value=row["segment_value"], segment_count=segment_count))

        boundary_row = global_row if run["profile_type"] == "SOURCE" else source_boundaries.get((pair.entity_name, pair.variable_1, pair.variable_2), {})
        boundaries = [boundary_row.get(field) for field in ("x_p25", "x_p50", "x_p75")]
        if not all(_finite(value) for value in boundaries) or not boundaries[0] < boundaries[1] < boundaries[2]:
            results.append(_row(identity, "X_QUARTILE_STATUS", segment_column=pair.variable_1,
                                reason="source_quantiles_missing_or_not_distinct"))
            continue
        args = {f"cut{i}": float(value) for i, value in enumerate(boundaries, 1)}
        quartiles = _rows(spark, cte + f"""
            , binned_pairs AS (
                SELECT *, CASE WHEN x <= :cut1 THEN 'Q1' WHEN x <= :cut2 THEN 'Q2'
                               WHEN x <= :cut3 THEN 'Q3' ELSE 'Q4' END AS bucket
                FROM clean_pairs WHERE x IS NOT NULL
            ) SELECT bucket, {_AGGREGATE} FROM binned_pairs GROUP BY bucket
        """, args)
        bins = {row["bucket"]: row for row in quartiles}
        for index in range(4):
            results.append(_row(identity, "X_QUARTILE", bins.get(f"Q{index + 1}", {}),
                                segment_column=pair.variable_1, segment_value=f"Q{index + 1}",
                                lower=boundaries[index - 1] if index else None,
                                upper=boundaries[index] if index < 3 else None, segment_count=4))
    if _active_run(spark) != run or _rows(spark, "SELECT * FROM active_profile_run") != [active]:
        raise ValueError("Active run changed while numeric dependencies were calculated.")
    _replace_run(spark, TABLE, SCHEMA, results, run["run_id"])
    print(f"Saved {len(results)} numeric dependency profiles for {len(pairs)} configured pairs ({run['profile_type']}).")
    return results


def _validate_group(group):
    """Do not present a partially deleted set of segments as complete evidence."""
    def invalid():
        raise ValueError("Numeric evidence has incomplete or excessive segmentation; re-profile SOURCE.")

    scopes = {"GLOBAL", "CATEGORY", "CATEGORY_STATUS", "X_QUARTILE", "X_QUARTILE_STATUS"}
    if any(row["scope"] not in scopes for row in group) or len(group) > 1 + MAX_SEGMENTS + 4:
        invalid()
    globals_ = [row for row in group if row["scope"] == "GLOBAL"]
    if len(globals_) != 1:
        invalid()
    global_row = globals_[0]
    if global_row["population_count"] is None:
        if len(group) != 1:
            invalid()
        return global_row
    for scope, status_scope in (("CATEGORY", "CATEGORY_STATUS"), ("X_QUARTILE", "X_QUARTILE_STATUS")):
        segments = [row for row in group if row["scope"] == scope]
        statuses = [row for row in group if row["scope"] == status_scope]
        if statuses:
            if len(statuses) != 1 or segments:
                invalid()
            continue
        if scope == "CATEGORY":
            if global_row["segment_count"] is None or len(segments) != global_row["segment_count"]:
                invalid()
            for field in ("population_count", "non_null_pair_count", "pair_count"):
                if sum(row[field] for row in segments) != global_row[field]:
                    invalid()
        else:
            if {row["segment_value"] for row in segments} != {"Q1", "Q2", "Q3", "Q4"}:
                invalid()
            if sum(row["pair_count"] for row in segments) != global_row["pair_count"]:
                invalid()
            cuts = [global_row[field] for field in ("x_p25", "x_p50", "x_p75")]
            for row in segments:
                index = int(row["segment_value"][1]) - 1
                if (row["lower_bound"] != (cuts[index - 1] if index else None)
                    or row["upper_bound"] != (cuts[index] if index < 3 else None)):
                    invalid()
    return global_row


def load_numeric_evidence(spark, source_run_id, *, max_pairs=3, min_pair_count=50):
    """Read bounded aggregate evidence from exactly one completed SOURCE run."""
    if not source_run_id or not 1 <= max_pairs <= MAX_PAIRS or min_pair_count < 2:
        raise ValueError("Select a SOURCE run, 1–12 evidence pairs, and at least two paired observations.")
    table = f"{PROFILE_SCHEMA}.{TABLE}"
    if not spark.catalog.tableExists(table):
        return []
    rows = _rows(spark, f"""
        SELECT p.* FROM {table} p JOIN {PROFILE_SCHEMA}.profile_runs r ON p.run_id = r.run_id
        WHERE p.run_id = :source AND p.profile_type = 'SOURCE'
          AND r.profile_type = 'SOURCE' AND r.status = 'COMPLETED' AND r.completed_at IS NOT NULL
        LIMIT {MAX_PAIRS * (1 + MAX_SEGMENTS + 4) + 1}
    """, {"source": source_run_id})
    if len(rows) > MAX_PAIRS * (1 + MAX_SEGMENTS + 4):
        raise ValueError("Numeric evidence exceeds the configured row limit.")
    groups = {}
    seen = set()
    for row in rows:
        group = (row["entity_name"], row["variable_1"], row["variable_2"])
        key = (*group, row["scope"], row["segment_column"], row["segment_value"], row["segment_is_null"])
        if key in seen:
            raise ValueError("Duplicate numeric dependency evidence; re-profile SOURCE from the top.")
        seen.add(key)
        groups.setdefault(group, []).append(row)
    if len(groups) > MAX_PAIRS:
        raise ValueError("Numeric evidence exceeds the configured pair limit.")
    evidence = []
    fields = ("scope", "segment_column", "segment_value", "segment_is_null", "lower_bound", "upper_bound", "segment_count",
              "profile_status", "skip_reason", "population_count", "non_null_pair_count", "pair_count",
              "excluded_null_count", "excluded_nonfinite_count", "pair_fraction", *_STATS)
    for (entity, first, second), group in sorted(groups.items()):
        global_row = _validate_group(group)
        eligible = [row for row in group if row["profile_status"] == "PROFILED" and (row["pair_count"] or 0) >= min_pair_count and _finite(row["pearson_correlation"])]
        if not eligible or (global_row["pair_count"] or 0) < min_pair_count:
            continue
        profiles = []
        for row in sorted(group, key=lambda row: (row["scope"], row["segment_value"] or "")):
            item = {field: row[field] for field in fields}
            if row["scope"] in ("CATEGORY", "X_QUARTILE") and (row["pair_count"] or 0) < min_pair_count:
                item.update({field: None for field in _STATS})
                item["skip_reason"] = "below_prompt_min_pair_count"
                item["profile_status"] = "INSUFFICIENT_FOR_PROMPT"
            profiles.append(item)
        evidence.append({
            "entity_name": entity, "variable_1": first, "variable_2": second,
            "population_unit": "account_feature_join_rows" if entity == "ACCOUNT" else "tradeline_rows",
            "quartile_intervals": "SOURCE complete-finite-pair X cuts; lower exclusive, upper inclusive; unbounded tails",
            "max_supported_abs_pearson": max(abs(row["pearson_correlation"]) for row in eligible),
            "profiles": profiles,
        })
    evidence.sort(key=lambda item: (-item["max_supported_abs_pearson"], item["entity_name"], item["variable_1"], item["variable_2"]))
    selected = evidence[:max_pairs]
    integrity = f"{PROFILE_SCHEMA}.integrity_profile"
    if any(item["entity_name"] == "ACCOUNT" for item in selected) and spark.catalog.tableExists(integrity):
        diagnostics = _rows(spark, f"""
            SELECT family, logical_table_name, metric, numerator, denominator, profile_status, reason
            FROM {integrity}
            WHERE run_id = :source AND profile_type = 'SOURCE' AND family IN ('JOIN_COVERAGE', 'KEY_QUALITY')
              AND logical_table_name IN ('TKQ_ACCOUNT', 'TKQ_ACCOUNT_BALANCE')
            ORDER BY family, logical_table_name, metric LIMIT 7
        """, {"source": source_run_id})
        if len(diagnostics) > 6:
            raise ValueError("Duplicate or excessive account join diagnostics in SOURCE evidence.")
        for item in selected:
            if item["entity_name"] == "ACCOUNT":
                item["join_diagnostics"] = diagnostics
    return selected
