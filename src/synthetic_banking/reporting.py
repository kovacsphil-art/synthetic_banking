"""Public aggregate JSON contract. Internal execution IDs never enter the payload."""

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

from synthetic_banking.config import PROFILE_SCHEMA, GENERATED_SCHEMA
from synthetic_banking.validation import GENERATED_TABLES
from synthetic_banking.workflow import require_profile_pair, utc_now
from synthetic_banking.validation_reporting import build_validation_report

SCHEMA_VERSION = "2.0"
REPORT_FILENAME = "latest-pipeline.json"
NUMERIC_FIELDS = (
    ("TKQ_ACCOUNT", "CREDIT_LIMIT_AMT"),
    ("TKQ_ACCOUNT_BALANCE", "CURRENT_BALANCE_AMT"),
    ("TKQ_ACCOUNT_BALANCE", "AVAILABLE_TO_BUY_AMT"),
    ("TKQ_ACCOUNT_BALANCE", "OVERLIMIT_AMT"),
)
BUCKETS = ("0-30%", "30-60%", "60-80%", "80-100%", "100%+")


def _completion_time(value):
    if value is None:
        value = utc_now()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError("Use a timezone-aware ISO 8601 completion timestamp.") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Use a timezone-aware ISO 8601 completion timestamp.")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value) if math.isfinite(float(value)) else None
    except (ValueError, TypeError, OverflowError):
        return None


def _count(value):
    number = _number(value)
    valid = number is not None and number >= 0 and number.is_integer()
    return {"status": "AVAILABLE" if valid else "UNAVAILABLE", "value": int(number) if valid else None,
            "reason": None if valid else "missing_aggregate"}


def _comparison(row, unit="value"):
    row = row or {}
    source, generated = _number(row.get("source_value")), _number(row.get("generated_value"))
    difference = _number(row.get("difference"))
    valid = row.get("comparison_status") == "COMPARABLE" and None not in (source, generated, difference)
    return {"status": "AVAILABLE" if valid else "UNAVAILABLE", "source": source, "generated": generated,
            "difference": difference if valid else None, "difference_unit": unit,
            "reason": None if valid else "metric_unavailable"}


def _dimensions(row):
    try:
        value = json.loads(row.get("dimensions_json") or "{}")
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


def build_public_report(metrics, rule_counts, *, validation_passed=False, completed_at=None, rule_outcomes=()):
    """Project fixed allowlists only; never copy arbitrary text, categories, or dimensions."""
    if validation_passed is not True or any(row.get("generated_check_status") == "ISSUE" for row in metrics):
        raise ValueError("A public success report requires successful generation and integrity validation.")

    def find(family, entity, column=None, metric=None, **dimensions):
        matches = [row for row in metrics if row.get("family") == family and row.get("entity_name") == entity
                   and row.get("column_name") == column and (metric is None or row.get("metric") == metric)
                   and all(_dimensions(row).get(key) == value for key, value in dimensions.items())]
        if len(matches) > 1:
            raise ValueError("Duplicate reporting metrics in the selected profile pair.")
        return matches[0] if matches else None

    table_rows = []
    for table in GENERATED_TABLES:
        row = find("ROW_COUNT", table, metric="row_count")
        table_rows.append({"table": table, **_count((row or {}).get("generated_value"))})
    sizes = {row["table"]: row["value"] for row in table_rows}
    total = sum(sizes.values()) if all(value is not None for value in sizes.values()) else None
    numeric = [{"table": table, "column": column, "metric": metric,
                **_comparison(find("NUMERIC", table, column, metric))}
               for table, column in NUMERIC_FIELDS for metric in ("mean_value", "p50", "p95")]
    categorical = [{"table": "TKQ_ACCOUNT", "column": "PAST_DUE_INDICATO_CD", "category": category,
                    **_comparison(find("CATEGORICAL", "TKQ_ACCOUNT", "PAST_DUE_INDICATO_CD", "proportion",
                                       category_value=category), "percentage_points")}
                   for category in ("Y", "N")]
    conditional = [{"utilization_bucket": bucket,
                    **_comparison(find("CONDITIONAL", "ACCOUNT", "PAST_DUE_INDICATO_CD", "outcome_rate",
                                       parent_column="UTILIZATION_RATE", condition_bucket=bucket), "percentage_points")}
                   for bucket in BUCKETS]
    correlation = _comparison(find("CORRELATION", "ACCOUNT", "CREDIT_LIMIT_AMT", "PEARSON_CORRELATION",
                                   variable_2="CURRENT_BALANCE_AMT"), "correlation")
    coverage = {}
    for label, table in (("accounts_with_balance", "TKQ_ACCOUNT"), ("balances_with_account", "TKQ_ACCOUNT_BALANCE")):
        row = find("JOIN_COVERAGE", table, metric="snapshot_join_coverage")
        value = _number((row or {}).get("generated_value"))
        valid = value is not None and 0 <= value <= 1
        coverage[label] = {"status": "AVAILABLE" if valid else "UNAVAILABLE", "value": value if valid else None,
                           "reason": None if valid else "metric_unavailable"}
    warnings = [{"code": "FIDELITY_THRESHOLDS_NOT_CONFIGURED",
                 "message": "Integrity passed. Statistical differences are observations for review, without an overall acceptance score.", "count": None}]
    counts = {key: _count(rule_counts.get(key)) for key in ("proposed", "approved", "applied", "skipped", "approved_unimplemented")}
    for key, code, message in (
        ("approved_unimplemented", "APPROVED_RULES_NOT_IMPLEMENTED", "Some approved proposals have no matching implementation and were skipped."),
        ("skipped", "SKIPPED_PROPOSALS", "Some proposals did not affect this dataset; inspect the internal rule audit."),
    ):
        if counts[key]["value"]:
            warnings.append({"code": code, "message": message, "count": counts[key]["value"]})
    unavailable = sum(item["status"] == "UNAVAILABLE" for item in [
        *numeric, *categorical, *conditional, correlation, *coverage.values(), *table_rows, *counts.values(),
    ])
    if unavailable:
        warnings.append({"code": "UNAVAILABLE_METRICS", "message": "Some selected aggregate measurements are unavailable.", "count": unavailable})
    return {
        "schema_version": SCHEMA_VERSION,
        "pipeline_completed_at": _completion_time(completed_at),
        "generation": {"total_rows": _count(total), "customers": _count(sizes.get("PERSON")),
                       "accounts": _count(sizes.get("TKQ_ACCOUNT")), "table_rows": table_rows},
        "rules": counts,
        "validation": {"status": "PASS", "fidelity_acceptance": "NOT_CONFIGURED", "account_balance_join_coverage": coverage},
        "numeric_differences": numeric, "categorical_differences": categorical,
        "dependency_results": {"credit_limit_balance_pearson": correlation, "delinquency_by_utilization": conditional},
        "warnings": warnings,
        "validation_report": build_validation_report(metrics, rule_outcomes),
    }


def _rows(spark, query, args):
    return [row.asDict() for row in spark.sql(query, args=args).collect()]


def load_public_report(spark, source_run_id, batch_id, generation_id, generated_run_id, validation_status, validated_at=None):
    if validation_status != "PASS":
        raise ValueError("Reporting requires the successful validation task's PASS handoff.")
    require_profile_pair(spark, source_run_id, batch_id, generation_id, generated_run_id)
    args = {"source": source_run_id, "batch": batch_id, "generation": generation_id, "generated": generated_run_id}
    metrics = _rows(spark, f"""
        SELECT * FROM {PROFILE_SCHEMA}.fidelity_metrics
        WHERE source_run_id = :source AND generated_run_id = :generated AND generation_id = :generation
    """, args)
    if not metrics:
        raise ValueError("No saved validation report for this execution. Run the validation task first.")
    # Aggregate counts are taken from the generation-time audit, not today's approval status.
    audit = _rows(spark, f"""
        SELECT proposal_id, batch_id, source_run_id, approved, implemented, applied, outcome, implementation_name
        FROM {GENERATED_SCHEMA}.rule_execution_log WHERE generation_id = :generation
    """, args)
    proposals = [row for row in audit if row.get("proposal_id") is not None]
    if (any(row.get("source_run_id") != source_run_id for row in audit)
            or any(row.get("batch_id") != batch_id for row in proposals)
            or len({row["proposal_id"] for row in proposals}) != len(proposals)):
        raise ValueError("Rule audit is inconsistent with this execution's provenance.")
    if not audit:
        raise ValueError("The validated generation rule audit is missing.")
    counts = {"proposed": len(proposals), "approved": sum(row.get("approved") is True for row in proposals),
              "applied": sum(row.get("applied") is True for row in proposals),
              "skipped": sum(row.get("outcome") == "SKIPPED" for row in proposals),
              "approved_unimplemented": sum(row.get("approved") is True and row.get("implemented") is False for row in proposals)}
    return build_public_report(metrics, counts, validation_passed=True, completed_at=validated_at, rule_outcomes=audit)


def export_public_report(spark, output_dir, **execution):
    """Replace one latest-success artifact only after all validation/build steps succeed."""
    report = load_public_report(spark, **execution)
    destination = Path(output_dir)
    if not destination.is_absolute():
        raise ValueError("Use an absolute writable report directory, such as a Databricks Volume.")
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / REPORT_FILENAME
    if target.exists():
        try:
            previous = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(previous, dict) or not isinstance(previous.get("pipeline_completed_at"), str):
                raise ValueError("No prior completion timestamp.")
            previous_time = _completion_time(previous["pipeline_completed_at"])
        except (ValueError, TypeError, KeyError):
            # A malformed file is not a prior successful report.
            previous_time = None
        current_time = _completion_time(report["pipeline_completed_at"])
        if previous_time is not None and datetime.fromisoformat(previous_time.replace("Z", "+00:00")) > datetime.fromisoformat(current_time.replace("Z", "+00:00")):
            raise ValueError("An older validated execution cannot replace the latest successful report.")
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(report, stream, ensure_ascii=False, allow_nan=False, indent=2)
            stream.write("\n")
        os.replace(temporary, target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return target
