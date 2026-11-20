"""Persist aggregate validation evidence and compare one explicit profile pair.

Generation is deliberately independent of this report. No acceptance score or
automatic threshold is inferred from statistical distance.
"""

from collections import defaultdict
from datetime import date, datetime, timezone
import json
import math
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from synthetic_banking.profiling import PROFILE_SCHEMA, _active_run, _identifier, _replace_run, _rows
from synthetic_banking.temporal import temporal_checks


DATE_SCHEMA = """
    run_id STRING, profile_type STRING, logical_table_name STRING, column_name STRING,
    month_bucket STRING, record_count BIGINT, non_null_count BIGINT, proportion DOUBLE
"""
INTEGRITY_SCHEMA = """
    run_id STRING, profile_type STRING, family STRING, logical_table_name STRING,
    metric STRING, numerator BIGINT, denominator BIGINT, profile_status STRING, reason STRING
"""
LINEAGE_SCHEMA = """
    run_id STRING, profile_type STRING, source_run_id STRING, generation_id STRING
"""
METRIC_SCHEMA = """
    comparison_id STRING, source_run_id STRING, generated_run_id STRING, generation_id STRING,
    created_at TIMESTAMP, family STRING, entity_name STRING, column_name STRING,
    metric STRING, dimensions_json STRING, source_value DOUBLE, generated_value DOUBLE,
    source_display STRING, generated_display STRING, difference DOUBLE, absolute_difference DOUBLE,
    relative_difference_pct DOUBLE, value_unit STRING, difference_unit STRING,
    source_sample_size BIGINT, generated_sample_size BIGINT, source_count BIGINT, generated_count BIGINT,
    comparison_status STRING, reason STRING, generated_check_status STRING,
    deviation_value DOUBLE, ranking_basis STRING, deviation_rank INT, highlight BOOLEAN
"""
PROFILE_TABLES = (
    "column_quality", "numeric_profile", "category_profile", "date_profile",
    "date_distribution_profile", "cardinality_profile", "relationship_profile",
    "conditional_profile", "categorical_relationship_profile", "categorical_conditional_profile", "integrity_profile",
    "numeric_dependency_profile",
    "customer_relationship_summary",
)
NUMERIC_METRICS = (
    "mean_value", "p01", "p05", "p25", "p50", "p75", "p95", "p99",
    "min_value", "max_value", "stddev_value",
)


def _table_name(value):
    return ".".join(_identifier(part) for part in value.split("."))


def _profile_integrity(spark, inputs, inventory, run):
    """Measure coverage by input row; distinct key groups prevent join inflation."""
    columns = defaultdict(set)
    for row in inventory:
        columns[row["logical_table_name"]].add(row["column_name"].upper())
    results = []

    def available(requirements):
        return all(table in inputs and set(names) <= columns[table] for table, names in requirements.items())

    def save(family, table, metric, counts=None, reason=None):
        numerator, denominator = counts if counts is not None else (None, None)
        results.append({
            **run, "family": family, "logical_table_name": table, "metric": metric,
            "numerator": numerator, "denominator": denominator,
            "profile_status": "UNAVAILABLE" if reason else "MEASURED" if denominator else "EMPTY",
            "reason": reason or ("no_eligible_rows" if not denominator else None),
        })

    keys = ("ACCOUNT_ID", "BUSINESSEFFECTIVEDATE")
    join_requirements = {"TKQ_ACCOUNT": keys, "TKQ_ACCOUNT_BALANCE": keys}
    joined = None
    if available(join_requirements):
        account, balance = (_table_name(inputs[name]) for name in join_requirements)
        joined = (f"{account} a JOIN {balance} b ON a.ACCOUNT_ID = b.ACCOUNT_ID "
                  "AND a.BUSINESSEFFECTIVEDATE = b.BUSINESSEFFECTIVEDATE")
    for table, other in (("TKQ_ACCOUNT", "TKQ_ACCOUNT_BALANCE"), ("TKQ_ACCOUNT_BALANCE", "TKQ_ACCOUNT")):
        if joined is None:
            counts = None
        else:
            counts = _rows(spark, f"""
                WITH own_keys AS (
                    SELECT ACCOUNT_ID, BUSINESSEFFECTIVEDATE, COUNT(*) AS n
                    FROM {_table_name(inputs[table])} GROUP BY ACCOUNT_ID, BUSINESSEFFECTIVEDATE
                ), other_keys AS (
                    SELECT ACCOUNT_ID, BUSINESSEFFECTIVEDATE, COUNT(*) AS n
                    FROM {_table_name(inputs[other])} GROUP BY ACCOUNT_ID, BUSINESSEFFECTIVEDATE
                )
                SELECT COALESCE(SUM(o.n), 0) AS total,
                    COALESCE(SUM(CASE WHEN p.n IS NOT NULL THEN o.n ELSE 0 END), 0) AS matched,
                    COALESCE(SUM(o.n - 1), 0) AS duplicate_rows,
                    COALESCE(SUM(CASE WHEN o.ACCOUNT_ID IS NULL OR o.BUSINESSEFFECTIVEDATE IS NULL
                        THEN o.n ELSE 0 END), 0) AS null_keys
                FROM own_keys o LEFT JOIN other_keys p
                  ON o.ACCOUNT_ID = p.ACCOUNT_ID AND o.BUSINESSEFFECTIVEDATE = p.BUSINESSEFFECTIVEDATE
            """)[0]
        for family, metric, count_key in (
            ("JOIN_COVERAGE", "snapshot_join_coverage", "matched"),
            ("KEY_QUALITY", "duplicate_snapshot_rows", "duplicate_rows"),
            ("KEY_QUALITY", "null_snapshot_keys", "null_keys"),
        ):
            save(family, table, metric, (counts[count_key], counts["total"]) if counts else None,
                 None if counts else "missing_snapshot_tables_or_columns")

    # These are the existing generator invariants, not new banking formulas.
    amount_inputs = {**join_requirements, "TKQ_ACCOUNT": (*keys, "CREDIT_LIMIT_AMT"),
                     "TKQ_ACCOUNT_BALANCE": (*keys, "CURRENT_BALANCE_AMT")}
    rules = (
        ("TKQ_ACCOUNT_BALANCE", "negative_current_balance", amount_inputs,
         "b.CURRENT_BALANCE_AMT >= 0", joined, ""),
        ("TKQ_ACCOUNT_BALANCE", "balance_cap", amount_inputs,
         "a.CREDIT_LIMIT_AMT IS NULL OR b.CURRENT_BALANCE_AMT <= 1.25 * a.CREDIT_LIMIT_AMT + 1e-8", joined, ""),
        ("TKQ_ACCOUNT_BALANCE", "available_to_buy_formula",
         {**amount_inputs, "TKQ_ACCOUNT_BALANCE": (*keys, "CURRENT_BALANCE_AMT", "AVAILABLE_TO_BUY_AMT")},
         "ABS(b.AVAILABLE_TO_BUY_AMT - GREATEST(COALESCE(a.CREDIT_LIMIT_AMT, 0) - b.CURRENT_BALANCE_AMT, 0)) <= 1e-8", joined, ""),
        ("TKQ_ACCOUNT_BALANCE", "overlimit_formula",
         {**amount_inputs, "TKQ_ACCOUNT_BALANCE": (*keys, "CURRENT_BALANCE_AMT", "OVERLIMIT_AMT")},
         "ABS(b.OVERLIMIT_AMT - GREATEST(b.CURRENT_BALANCE_AMT - COALESCE(a.CREDIT_LIMIT_AMT, 0), 0)) <= 1e-8", joined, ""),
        ("TKQ_ACCOUNT", "utilization_formula",
         {**amount_inputs, "TKQ_ACCOUNT": (*keys, "CREDIT_LIMIT_AMT", "_UTILIZATION_RATE")},
         "ABS(a._UTILIZATION_RATE - CASE WHEN a.CREDIT_LIMIT_AMT > 0 THEN CAST(b.CURRENT_BALANCE_AMT AS DOUBLE) / a.CREDIT_LIMIT_AMT ELSE 0 END) <= 1e-8", joined, ""),
        ("TKQ_ACCOUNT", "delinquency_flag_count", {"TKQ_ACCOUNT": ("DELINQUENCY_CNT", "PAST_DUE_INDICATO_CD")},
         "a.DELINQUENCY_CNT = FLOOR(a.DELINQUENCY_CNT) AND ((a.PAST_DUE_INDICATO_CD = 'Y' AND a.DELINQUENCY_CNT >= 1) OR (a.PAST_DUE_INDICATO_CD = 'N' AND a.DELINQUENCY_CNT = 0))",
         f"{_table_name(inputs['TKQ_ACCOUNT'])} a" if "TKQ_ACCOUNT" in inputs else None, ""),
        ("PERSON", "since_before_birth", {"PERSON": ("SINCE_DT", "BIRTH_DT")},
         "p.SINCE_DT >= p.BIRTH_DT", f"{_table_name(inputs['PERSON'])} p" if "PERSON" in inputs else None,
         "WHERE p.SINCE_DT IS NOT NULL AND p.BIRTH_DT IS NOT NULL"),
    )
    for table, metric, requirements, valid, source, where in rules:
        if not available(requirements):
            save("BUSINESS_RULE", table, metric, reason="missing_required_table_or_columns")
            continue
        counts = _rows(spark, f"""
            SELECT COUNT(*) AS denominator,
                COUNT(CASE WHEN NOT COALESCE(({valid}), FALSE) THEN 1 END) AS numerator
            FROM {source} {where}
        """)[0]
        save("BUSINESS_RULE", table, metric, (counts["numerator"], counts["denominator"]))
    temporal_columns = defaultdict(list)
    for row in inventory:
        if row["column_role"] in ("DATE", "TIMESTAMP"):
            temporal_columns[row["logical_table_name"]].append(row["column_name"])
    results.extend({**run, "family": "TEMPORAL_RULE", **check}
                   for check in temporal_checks(spark, {table: _table_name(obj) for table, obj in inputs.items()}, temporal_columns))
    return results


def profile_fidelity_inputs(spark, profile_inputs):
    """Capture new aggregate evidence before Notebook 01 completes either run type."""
    run = _active_run(spark)
    active = _rows(spark, "SELECT * FROM active_profile_run")[0]
    source = run["run_id"] if run["profile_type"] == "SOURCE" else active.get("source_run_id")
    generation = active.get("generation_id") if run["profile_type"] == "GENERATED" else None
    if run["profile_type"] == "GENERATED":
        baseline = _rows(spark, f"""
            SELECT run_id FROM {PROFILE_SCHEMA}.profile_runs
            WHERE run_id = :source AND profile_type = 'SOURCE'
              AND status = 'COMPLETED' AND completed_at IS NOT NULL
        """, {"source": source})
        if not source or not generation or len(baseline) != 1:
            raise ValueError("GENERATED evidence requires the generation's pinned completed SOURCE run and generation ID.")
    inventory = _rows(spark, "SELECT logical_table_name, column_name, column_role FROM active_column_inventory")
    dates = []
    for column in inventory:
        if column["column_role"] not in ("DATE", "TIMESTAMP"):
            continue
        table, name = column["logical_table_name"], column["column_name"]
        value = f"CAST({_identifier(name)} AS DATE)"
        buckets = _rows(spark, f"""
            SELECT DATE_FORMAT({value}, 'yyyy-MM') AS month_bucket, COUNT(*) AS record_count
            FROM {_table_name(profile_inputs[table])} WHERE {value} IS NOT NULL
            GROUP BY DATE_FORMAT({value}, 'yyyy-MM')
        """)
        total = sum(row["record_count"] for row in buckets)
        dates.extend({**run, "logical_table_name": table, "column_name": name,
                      **row, "non_null_count": total, "proportion": row["record_count"] / total}
                     for row in buckets)
    integrity = _profile_integrity(spark, profile_inputs, inventory, run)
    if _active_run(spark) != run or _rows(spark, "SELECT * FROM active_profile_run") != [active]:
        raise ValueError("Active profiling run changed while validation evidence was calculated.")
    _replace_run(spark, "date_distribution_profile", DATE_SCHEMA, dates, run["run_id"])
    _replace_run(spark, "integrity_profile", INTEGRITY_SCHEMA, integrity, run["run_id"])
    _replace_run(spark, "profile_run_lineage", LINEAGE_SCHEMA, [{
        **run, "source_run_id": source, "generation_id": generation,
    }], run["run_id"])
    print(f"Saved monthly date distributions, {len(integrity)} integrity checks, and {run['profile_type']} lineage.")


def _number(value):
    if value is None:
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _index(rows, keys):
    result = {}
    for row in rows:
        key = tuple(row.get(name) for name in keys)
        if key in result:
            raise ValueError(f"Duplicate aggregate profile: {keys} = {key}.")
        result[key] = row
    return result


def _epoch_day(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        value = value.date()
    elif not isinstance(value, date):
        value = date.fromisoformat(str(value)[:10])
    return (value - date(1970, 1, 1)).days


def compare_profiles(source_run_id, generated_run_id, generation_id, profiles):
    """Pure aggregate comparison. The Spark entry point verifies durable lineage first."""
    if not source_run_id or not generated_run_id or source_run_id == generated_run_id or not generation_id:
        raise ValueError("Provide distinct SOURCE/GENERATED run IDs and their generation ID.")
    source, generated = source_run_id, generated_run_id
    prepared = {}
    for name, rows in profiles.items():
        prepared[name] = [dict(row) for row in rows]
        for row in prepared[name]:
            if row.get("run_id") not in (source, generated):
                raise ValueError("Aggregate rows must belong to the explicit comparison pair.")
            if row.get("profile_type") not in (None, "SOURCE" if row["run_id"] == source else "GENERATED"):
                raise ValueError("Aggregate row profile_type conflicts with the selected run.")
    profiles = prepared
    comparison_id = str(uuid5(NAMESPACE_URL, f"synthetic-banking:fidelity:v1:{source}:{generated}"))
    created = datetime.now(timezone.utc)
    metrics = []

    def add(family, entity, column, metric, s, g, *, dims=None, unit="value", reason=None,
            sn=None, gn=None, sc=None, gc=None, scale=None, check=False, display=None):
        sv, gv = _number(s), _number(g)
        if reason is None and (sv is None or gv is None):
            missing = "both_values" if sv is None and gv is None else "source_value" if sv is None else "generated_value"
            reason = f"missing_or_nonfinite_{missing}"
        comparable = reason is None
        delta = _number(gv - sv) if comparable else None
        if comparable and delta is None:
            comparable, reason = False, "nonfinite_difference"
        difference_unit = "percentage_points" if unit == "proportion" else unit
        if delta is not None and unit == "proportion":
            delta *= 100
        relative = _number(100 * ((gv - sv) / abs(sv))) if comparable and sv != 0 and unit != "days" else None
        deviation, basis = None, None
        if comparable:
            if unit == "proportion":
                deviation, basis = abs(delta), "absolute_percentage_points"
            elif family == "NUMERIC":
                if scale is not None and scale > 0:
                    deviation, basis = _number(abs(delta) / scale), "absolute_difference/source_IQR"
            elif unit in ("days", "correlation", "association"):
                deviation, basis = abs(delta), f"absolute_{unit}_difference"
            elif relative is not None:
                deviation, basis = abs(relative), "absolute_relative_percent"
        check_status = None
        if check:
            check_status = "UNAVAILABLE" if gv is None else "PASS" if (
                gv == 1 if family == "JOIN_COVERAGE" else gv == 0
            ) else "ISSUE"
        metrics.append({
            "comparison_id": comparison_id, "source_run_id": source, "generated_run_id": generated,
            "generation_id": generation_id, "created_at": created,
            "family": family, "entity_name": entity, "column_name": column, "metric": metric,
            "dimensions_json": json.dumps(dims or {}, sort_keys=True, ensure_ascii=False, allow_nan=False),
            "source_value": sv, "generated_value": gv,
            "source_display": display[0] if display else None, "generated_display": display[1] if display else None,
            "difference": delta, "absolute_difference": abs(delta) if delta is not None else None,
            "relative_difference_pct": relative, "value_unit": "epoch_days" if display else unit,
            "difference_unit": difference_unit, "source_sample_size": sn, "generated_sample_size": gn,
            "source_count": sc, "generated_count": gc,
            "comparison_status": "COMPARABLE" if comparable else "NOT_COMPARABLE", "reason": reason,
            "generated_check_status": check_status, "deviation_value": deviation, "ranking_basis": basis,
            "deviation_rank": None, "highlight": False,
        })

    def indexed(name, keys):
        return _index(profiles.get(name, []), ("run_id", *keys))

    def pairs(index):
        return sorted({key[1:] for key in index}, key=repr)

    quality = indexed("column_quality", ("logical_table_name", "column_name"))
    table_counts = {}
    for (run, table, _), row in quality.items():
        count = row.get("row_count")
        if count is None or count < 0 or ((run, table) in table_counts and table_counts[run, table] != count):
            raise ValueError("Missing or inconsistent table counts in the selected quality profiles.")
        if row.get("null_count") is not None and not 0 <= row["null_count"] <= count:
            raise ValueError("Null counts must fall between zero and the table row count.")
        table_counts[run, table] = count
    for (table,) in sorted({(table,) for _, table in table_counts}):
        add("ROW_COUNT", table, None, "row_count", table_counts.get((source, table)), table_counts.get((generated, table)), unit="rows")
    for table, column in pairs(quality):
        rows = [quality.get((run, table, column), {}) for run in (source, generated)]
        values = [row.get("null_count") / row["row_count"] if row.get("row_count") and row.get("null_count") is not None else None for row in rows]
        add("NULL_RATE", table, column, "null_rate", *values, unit="proportion",
            sn=rows[0].get("row_count"), gn=rows[1].get("row_count"), sc=rows[0].get("null_count"), gc=rows[1].get("null_count"))

    numeric = indexed("numeric_profile", ("logical_table_name", "column_name"))
    for table, column in pairs(numeric):
        s, g = (numeric.get((run, table, column), {}) for run in (source, generated))
        lo, hi = _number(s.get("p25")), _number(s.get("p75"))
        scale = _number(hi - lo) if hi is not None and lo is not None else None
        for metric in NUMERIC_METRICS:
            add("NUMERIC", table, column, metric, s.get(metric), g.get(metric),
                sn=s.get("non_null_count"), gn=g.get("non_null_count"), scale=scale)

    def distribution(name, family, group_keys, bucket, count_field, expected_total=None):
        index = indexed(name, (*group_keys, bucket))
        groups = defaultdict(dict)
        for (run, *key), row in index.items():
            group, value = tuple(key[:-1]), key[-1]
            groups[run, group][value] = row
        for group in sorted({group for _, group in groups}, key=repr):
            s, g = (groups.get((run, group), {}) for run in (source, generated))
            totals = [sum(row[count_field] for row in side.values()) for side in (s, g)]
            complete = []
            for run, side, total in zip((source, generated), (s, g), totals):
                if any(row[count_field] < 0 for row in side.values()):
                    raise ValueError("Distribution counts must be nonnegative.")
                expected = expected_total(run, group) if expected_total else total
                complete.append(bool(side) and total > 0 and expected == total)
                if side and total and any(_number(row.get("proportion")) is None or
                                          abs(row["proportion"] - row[count_field] / total) > 1e-8 for row in side.values()):
                    raise ValueError("Distribution proportions disagree with their counts.")
            reason = None if all(complete) else "missing_empty_or_incomplete_" + ("both_profiles" if not any(complete) else "source_profile" if not complete[0] else "generated_profile")
            for value in sorted(set(s) | set(g), key=repr):
                sr, gr = s.get(value), g.get(value)
                counts = [(row or {}).get(count_field, 0) if valid else (row or {}).get(count_field)
                          for row, valid in zip((sr, gr), complete)]
                values = [count / total if count is not None and valid else None
                          for count, total, valid in zip(counts, totals, complete)]
                add(family, group[0], group[1] if len(group) > 1 else None, "proportion", *values,
                    dims={bucket: value}, unit="proportion", reason=reason,
                    sn=totals[0] if s else None, gn=totals[1] if g else None, sc=counts[0], gc=counts[1])
            if family == "CARDINALITY":
                means = [sum(float(value) * row[count_field] for value, row in side.items()) / total if valid else None
                         for side, total, valid in zip((s, g), totals, complete)]
                add(family, group[0], None, "mean_cardinality", *means, unit="children_per_entity", reason=reason, sn=totals[0], gn=totals[1])

    distribution("category_profile", "CATEGORICAL", ("logical_table_name", "column_name"), "category_value", "record_count",
                 lambda run, group: table_counts.get((run, group[0])))
    dates = indexed("date_profile", ("logical_table_name", "column_name"))
    for table, column in pairs(dates):
        s, g = (dates.get((run, table, column), {}) for run in (source, generated))
        for metric in ("earliest_date", "latest_date"):
            raw = (s.get(metric), g.get(metric))
            add("DATE_RANGE", table, column, metric, *(_epoch_day(value) for value in raw), unit="days",
                sn=s.get("non_null_count"), gn=g.get("non_null_count"), display=tuple(str(value) if value is not None else None for value in raw))
    distribution("date_distribution_profile", "DATE_DISTRIBUTION", ("logical_table_name", "column_name"), "month_bucket", "record_count",
                 lambda run, group: dates.get((run, *group), {}).get("non_null_count"))
    # Old completed runs have date ranges but no monthly profiles. Say so per column.
    monthly = {(row["logical_table_name"], row["column_name"]) for row in profiles.get("date_distribution_profile", [])}
    for table, column in pairs(dates):
        if (table, column) not in monthly:
            add("DATE_DISTRIBUTION", table, column, "proportion", None, None, unit="proportion", reason="monthly_profiles_not_recorded_or_all_dates_null")
    distribution("cardinality_profile", "CARDINALITY", ("relationship_name",), "cardinality", "entity_count")
    measured_relationships = {row["relationship_name"] for row in profiles.get("cardinality_profile", [])}
    for relationship in ("ACCOUNTS_PER_PARTY", "TRADELINES_PER_CIF"):
        if relationship not in measured_relationships:
            add("CARDINALITY", relationship, None, "profile_available", None, None, reason="relationship_cardinality_not_profiled")

    correlations = indexed("relationship_profile", ("entity_name", "variable_1", "variable_2", "metric_type"))
    for entity, first, second, metric in pairs(correlations):
        s, g = (correlations.get((run, entity, first, second, metric), {}) for run in (source, generated))
        add("CORRELATION", entity, first, metric, s.get("metric_value"), g.get("metric_value"), dims={"variable_2": second}, unit="correlation")
    numeric_dependencies = indexed("numeric_dependency_profile", (
        "entity_name", "variable_1", "variable_2", "scope", "segment_column", "segment_value", "segment_is_null",
    ))
    for entity, first, second, scope, segment_column, segment_value, segment_is_null in pairs(numeric_dependencies):
        key = (entity, first, second, scope, segment_column, segment_value, segment_is_null)
        s, g = (numeric_dependencies.get((run, *key), {}) for run in (source, generated))
        dims = {"variable_1": first, "scope": scope, "segment_column": segment_column,
                "segment_value": segment_value, "segment_is_null": bool(segment_is_null),
                "source_profile_status": s.get("profile_status"), "generated_profile_status": g.get("profile_status"),
                "source_reason": s.get("skip_reason"), "generated_reason": g.get("skip_reason"),
                "source_lower_bound": s.get("lower_bound"), "source_upper_bound": s.get("upper_bound"),
                "generated_lower_bound": g.get("lower_bound"), "generated_upper_bound": g.get("upper_bound"),
                "source_population_count": s.get("population_count"), "generated_population_count": g.get("population_count"),
                "source_excluded_null_count": s.get("excluded_null_count"), "generated_excluded_null_count": g.get("excluded_null_count"),
                "source_excluded_nonfinite_count": s.get("excluded_nonfinite_count"), "generated_excluded_nonfinite_count": g.get("excluded_nonfinite_count")}
        bounds_match = scope != "X_QUARTILE" or all(s.get(field) == g.get(field) for field in ("lower_bound", "upper_bound"))
        if scope.endswith("STATUS"):
            add("NUMERIC_DEPENDENCY", entity, second, "profile_available", None, None,
                dims=dims, reason="segmentation_skipped_or_unavailable")
            continue
        for metric in ("pearson_correlation", "y_mean", "y_p25", "y_p50", "y_p75"):
            reason = None
            if not bounds_match:
                reason = "different_source_quantile_boundaries"
            elif metric == "pearson_correlation" and any(row.get("profile_status") != "PROFILED" for row in (s, g)):
                reason = "numeric_pair_missing_empty_constant_or_insufficient"
            add("NUMERIC_DEPENDENCY", entity, second, metric, s.get(metric), g.get(metric), dims=dims,
                unit="correlation" if metric == "pearson_correlation" else "value", reason=reason,
                sn=s.get("pair_count"), gn=g.get("pair_count"))
    conditional = indexed("conditional_profile", ("entity_name", "condition_variable", "outcome_variable", "condition_bucket"))
    for entity, parent, outcome, bucket in pairs(conditional):
        s, g = (conditional.get((run, entity, parent, outcome, bucket), {}) for run in (source, generated))
        valid = [bool((row.get("record_count") or 0) > 0) and _number(row.get("outcome_rate")) is not None
                 and 0 <= row["outcome_rate"] <= 1 for row in (s, g)]
        add("CONDITIONAL", entity, outcome, "outcome_rate", s.get("outcome_rate"), g.get("outcome_rate"),
            dims={"parent_column": parent, "condition_bucket": bucket}, unit="proportion",
            sn=s.get("record_count"), gn=g.get("record_count"), reason=None if all(valid) else "missing_empty_or_invalid_conditional_bucket")
    associations = indexed("categorical_relationship_profile", ("logical_table_name", "parent_column", "child_column"))
    # Complete-case categorical conditionals use their measured parent denominators.
    cat_cells = indexed("categorical_conditional_profile", (
        "logical_table_name", "parent_column", "child_column", "parent_value", "child_value"))
    cat_groups = defaultdict(dict)
    for (run, table, parent, child, p, c), row in cat_cells.items():
        cat_groups[run, table, parent, child][p, c] = row
    for table, parent, child in sorted({key[1:] for key in cat_groups}, key=repr):
        sides = [cat_groups.get((run, table, parent, child), {}) for run in (source, generated)]
        summaries = [associations.get((run, table, parent, child), {}) for run in (source, generated)]
        totals = []
        complete = []
        for side, summary in zip(sides, summaries):
            by_parent = defaultdict(int)
            for (p, _), row in side.items():
                count = row.get("record_count")
                if _number(count) is None or count < 0 or count != int(count):
                    raise ValueError("Categorical conditional counts must be finite nonnegative integers.")
                by_parent[p] += count
            totals.append(by_parent)
            parents = set(p for p, _ in side)
            children = set(c for _, c in side)
            complete.append(bool(side) and summary.get("profile_status") in ("PROFILED", "CONSTANT")
                            and len(side) == summary.get("cell_count") == len(parents)*len(children)
                            and len(parents) == summary.get("parent_cardinality")
                            and len(children) == summary.get("child_cardinality")
                            and sum(by_parent.values()) == summary.get("sample_size"))
        keys = sorted(set(sides[0]) | set(sides[1]), key=repr)
        unsupported = 0
        for p, c in keys:
            ns, ng = (total.get(p, 0) for total in totals)
            counts = [side.get((p, c), {}).get("record_count", 0) for side in sides]
            valid = all(complete) and ns > 0 and ng > 0
            add("CATEGORICAL_CONDITIONAL", table, child, "conditional_proportion",
                counts[0]/ns if valid else None, counts[1]/ng if valid else None,
                dims={"parent_column": parent, "parent_value": p, "child_value": c},
                unit="proportion", sn=ns, gn=ng, sc=counts[0], gc=counts[1],
                reason=None if valid else "missing_or_empty_categorical_parent")
            if counts[0] == 0:
                unsupported += counts[1]
        n_generated = sum(totals[1].values())
        add("CATEGORICAL_CONDITIONAL", table, child, "unsupported_combination_rate",
            0.0 if complete[0] else None,
            unsupported/n_generated if all(complete) and n_generated else None,
            dims={"parent_column": parent}, unit="proportion",
            sn=sum(totals[0].values()), gn=n_generated, sc=0, gc=unsupported)
    for table, parent, child in pairs(associations):
        s, g = (associations.get((run, table, parent, child), {}) for run in (source, generated))
        valid = all(row.get("profile_status") == "PROFILED" for row in (s, g))
        add("CATEGORICAL_ASSOCIATION", table, child, "cramers_v", s.get("cramers_v"), g.get("cramers_v"),
            dims={"parent_column": parent, "source_profile_status": s.get("profile_status"), "generated_profile_status": g.get("profile_status"),
                  "source_sparse_expected_cell_fraction": s.get("sparse_expected_cell_fraction"), "generated_sparse_expected_cell_fraction": g.get("sparse_expected_cell_fraction")},
            unit="association", sn=s.get("sample_size"), gn=g.get("sample_size"), reason=None if valid else "pair_missing_skipped_empty_or_constant")
    integrity = indexed("integrity_profile", ("family", "logical_table_name", "metric"))
    for family, table, metric in pairs(integrity):
        s, g = (integrity.get((run, family, table, metric), {}) for run in (source, generated))
        values = []
        for row in (s, g):
            numerator, denominator = row.get("numerator"), row.get("denominator")
            if row.get("profile_status") == "MEASURED" and denominator is not None and denominator > 0:
                if numerator is None or not 0 <= numerator <= denominator:
                    raise ValueError("Integrity counts must fall between zero and their evaluated-row denominator.")
                values.append(numerator / denominator)
            else:
                values.append(None)
        add(family, table, None, metric, *values, unit="proportion", check=True,
            sn=s.get("denominator"), gn=g.get("denominator"), sc=s.get("numerator"), gc=g.get("numerator"),
            dims={"source_profile_status": s.get("profile_status"), "generated_profile_status": g.get("profile_status"),
                  "source_reason": s.get("reason"), "generated_reason": g.get("reason")})

    customer_graph = indexed("customer_relationship_summary", ())
    if customer_graph:
        s, g = (customer_graph.get((run,), {}) for run in (source, generated))
        for metric, numerator, denominator in (
            ("invalid_endpoint_rate", "invalid_endpoint_rows", "raw_rows"),
            ("self_row_rate", "self_rows", "valid_rows"),
        ):
            values = [row.get(numerator, 0) / row[denominator] if row.get(denominator) else None for row in (s, g)]
            add("CUSTOMER_RELATIONSHIP", "CUSTOMER_RELATIONSHIP", None, metric, *values, unit="proportion",
                sn=s.get(denominator), gn=g.get(denominator), sc=s.get(numerator), gc=g.get(numerator),
                check=metric == "invalid_endpoint_rate")
        for field in ("directed_dyads", "reciprocal_dyads", "self_dyads"):
            totals = [sum(row.get(name, 0) for name in ("directed_dyads", "reciprocal_dyads", "self_dyads")) for row in (s, g)]
            values = [row.get(field, 0) / total if total else None for row, total in zip((s, g), totals)]
            add("CUSTOMER_RELATIONSHIP", "CUSTOMER_RELATIONSHIP", None, field + "_proportion", *values,
                unit="proportion", sn=totals[0], gn=totals[1], sc=s.get(field), gc=g.get(field))

    for family in ("NUMERIC", "CATEGORICAL", "CATEGORICAL_CONDITIONAL", "NULL_RATE", "DATE_RANGE", "DATE_DISTRIBUTION", "CARDINALITY", "CORRELATION", "NUMERIC_DEPENDENCY", "CONDITIONAL", "JOIN_COVERAGE", "BUSINESS_RULE", "TEMPORAL_RULE"):
        if not any(row["family"] == family for row in metrics):
            add(family, "ALL", None, "profile_available", None, None, reason="neither_run_has_profile_evidence")
    ranking = defaultdict(list)
    for row in metrics:
        if row["deviation_value"] is not None:
            ranking[row["family"], row["ranking_basis"]].append(row)
    for rows in ranking.values():
        rows.sort(key=lambda row: (-row["deviation_value"], row["entity_name"], row["column_name"] or "", row["metric"], row["dimensions_json"]))
        for rank, row in enumerate(rows, 1):
            row["deviation_rank"] = rank
            row["highlight"] = rank <= 5 and row["deviation_value"] > 0
    return {
        "schema_version": 1, "comparison_id": comparison_id, "source_run_id": source,
        "generated_run_id": generated, "generation_id": generation_id, "created_at": created,
        "metrics": metrics,
    }


def create_fidelity_report(spark, source_run_id, generated_run_id):
    """Validate completed runs and saved correspondence, then persist aggregate metrics."""
    if not source_run_id or not generated_run_id or source_run_id == generated_run_id:
        raise ValueError("Select distinct explicit SOURCE and GENERATED run IDs.")
    args = {"source": source_run_id, "generated": generated_run_id}
    runs = _rows(spark, f"""
        SELECT run_id, profile_type, status, completed_at FROM {PROFILE_SCHEMA}.profile_runs
        WHERE run_id IN (:source, :generated)
    """, args)
    if (len(runs) != 2
        or {r["run_id"]: r["profile_type"] for r in runs} != {source_run_id: "SOURCE", generated_run_id: "GENERATED"}
        or any(r["status"] != "COMPLETED" or r["completed_at"] is None for r in runs)):
        raise ValueError("Both explicit profiles must be completed with SOURCE and GENERATED types respectively.")
    lineage_table = f"{PROFILE_SCHEMA}.profile_run_lineage"
    if not spark.catalog.tableExists(lineage_table):
        raise ValueError("Saved GENERATED lineage is unavailable. Rerun Notebook 01 GENERATED with the updated profiling stage.")
    lineage = _rows(spark, f"SELECT * FROM {lineage_table} WHERE run_id = :generated", args)
    if len(lineage) != 1 or lineage[0]["profile_type"] != "GENERATED" or lineage[0]["source_run_id"] != source_run_id or not lineage[0]["generation_id"]:
        raise ValueError("The GENERATED profile is not linked to the selected SOURCE run and generation.")
    profiles = {}
    for name in PROFILE_TABLES:
        table = f"{PROFILE_SCHEMA}.{name}"
        profiles[name] = _rows(spark, f"SELECT * FROM {table} WHERE run_id IN (:source, :generated)", args) if spark.catalog.tableExists(table) else []
    report = compare_profiles(source_run_id, generated_run_id, lineage[0]["generation_id"], profiles)
    table = f"{PROFILE_SCHEMA}.fidelity_metrics"
    spark.sql(f"CREATE TABLE IF NOT EXISTS {table} ({METRIC_SCHEMA}) USING DELTA")
    spark.createDataFrame(report["metrics"], METRIC_SCHEMA).createOrReplaceTempView("fidelity_metrics_write")
    spark.sql(f"INSERT INTO {table} REPLACE WHERE generated_run_id = :generated SELECT * FROM fidelity_metrics_write", args=args)
    return report


def export_fidelity_report(report, output_dir):
    """Write an explicitly requested internal aggregate JSON report (including lineage)."""
    destination = Path(output_dir)
    if not destination.is_absolute():
        raise ValueError("Use an absolute fidelity output folder, for example a writable Volume directory.")
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / "fidelity_report.json"
    target.write_text(json.dumps(report, default=lambda value: value.isoformat() if isinstance(value, (date, datetime)) else str(value),
                                 ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")
    return target
