"""Export a completed profile comparison into the static project showcase."""

from datetime import datetime, timezone
from html import escape
import math
import os
from pathlib import Path
import shutil
from tempfile import NamedTemporaryFile

from synthetic_banking.validation import GENERATED_SCHEMA, GENERATED_TABLES, check_validated_versions


_PROFILE = "workspace.synthetic_profile"
_FIELDS = (
    ("TKQ_ACCOUNT", "CREDIT_LIMIT_AMT"),
    ("TKQ_ACCOUNT_BALANCE", "CURRENT_BALANCE_AMT"),
    ("TKQ_ACCOUNT_BALANCE", "AVAILABLE_TO_BUY_AMT"),
    ("TKQ_ACCOUNT_BALANCE", "OVERLIMIT_AMT"),
)
_STATISTICS = ("mean_value", "p25", "p50", "p75", "p95")
_BUCKETS = ("0-30%", "30-60%", "60-80%", "80-100%", "100%+", "NULL")
_START = "<!-- SHOWCASE RESULTS START -->"
_END = "<!-- SHOWCASE RESULTS END -->"


def _rows(spark, query, args=None):
    return [row.asDict() for row in spark.sql(query, args=args).collect()]


def _validated_generation(spark, active):
    states = _rows(spark, f"SELECT * FROM {GENERATED_SCHEMA}.generation_state")
    if len(states) != 1:
        raise ValueError("Showcase export requires one completed generation state.")
    state = states[0]
    if (
        state["status"] != "COMPLETED"
        or state["generation_id"] != active["generation_id"]
        or state["source_run_id"] != active["source_run_id"]
    ):
        raise ValueError("The active profile and completed generation have different lineage.")
    check_validated_versions(spark, state.get("validated_versions"))
    return state["validated_versions"]


def collect_measurements(spark):
    """Read the current session's explicit pair and return only allowlisted aggregates."""
    active_rows = _rows(spark, "SELECT * FROM active_profile_run")
    if len(active_rows) != 1 or active_rows[0]["profile_type"] != "GENERATED":
        raise ValueError("Run the export in Notebook 01's completed GENERATED session.")
    active = active_rows[0]
    source, generated = active["source_run_id"], active["run_id"]
    if not source or not generated or source == generated or not active["generation_id"]:
        raise ValueError("Showcase export requires distinct SOURCE and GENERATED profiles.")
    args = {"source": source, "generated": generated, "generation": active["generation_id"]}
    runs = _rows(spark, f"""
        SELECT run_id, profile_type, status, completed_at
        FROM {_PROFILE}.profile_runs WHERE run_id IN (:source, :generated)
    """, args)
    if (
        len(runs) != 2
        or {row["run_id"]: row["profile_type"] for row in runs}
        != {source: "SOURCE", generated: "GENERATED"}
        or any(row["status"] != "COMPLETED" or row["completed_at"] is None for row in runs)
    ):
        raise ValueError("Both selected profiling runs must be completed with the expected types.")
    versions = _validated_generation(spark, active)

    numeric_rows = _rows(spark, f"""
        SELECT run_id, logical_table_name, column_name, mean_value, p25, p50, p75, p95
        FROM {_PROFILE}.numeric_profile
        WHERE run_id IN (:source, :generated)
          AND ((logical_table_name = 'TKQ_ACCOUNT' AND column_name = 'CREDIT_LIMIT_AMT')
            OR (logical_table_name = 'TKQ_ACCOUNT_BALANCE'
                AND column_name IN ('CURRENT_BALANCE_AMT', 'AVAILABLE_TO_BUY_AMT', 'OVERLIMIT_AMT')))
    """, args)
    numeric = _index(numeric_rows, ("run_id", "logical_table_name", "column_name"))
    correlations = _rows(spark, f"""
        SELECT run_id, metric_value FROM {_PROFILE}.relationship_profile
        WHERE run_id IN (:source, :generated) AND entity_name = 'ACCOUNT'
          AND variable_1 = 'CREDIT_LIMIT_AMT' AND variable_2 = 'CURRENT_BALANCE_AMT'
          AND metric_type = 'PEARSON_CORRELATION'
    """, args)
    correlation = _index(correlations, ("run_id",))
    conditional_rows = _rows(spark, f"""
        SELECT run_id, condition_bucket, record_count, outcome_rate
        FROM {_PROFILE}.conditional_profile
        WHERE run_id IN (:source, :generated) AND entity_name = 'ACCOUNT'
          AND condition_variable = 'UTILIZATION_RATE' AND outcome_variable = 'PAST_DUE_INDICATO_CD'
    """, args)
    conditional = _index(conditional_rows, ("run_id", "condition_bucket"))
    quality_rows = _rows(spark, f"""
        SELECT run_id, logical_table_name, MIN(row_count) AS row_count, MAX(row_count) AS max_rows
        FROM {_PROFILE}.column_quality WHERE run_id IN (:source, :generated)
        GROUP BY run_id, logical_table_name
    """, args)
    quality = _index(quality_rows, ("run_id", "logical_table_name"))
    for name in GENERATED_TABLES:
        for selected in (source, generated):
            row = quality.get((selected, name))
            if row is None or row["row_count"] is None or row["row_count"] != row["max_rows"]:
                raise ValueError("Missing or inconsistent table counts in the pinned profiles.")

    # Spark returns counts only. No account or person records leave the workspace.
    coverage = _rows(spark, f"""
        SELECT COUNT(*) AS joined_rows,
               COUNT(DISTINCT a.ACCOUNT_ID) AS matched_accounts,
               COUNT(DISTINCT b.ACCOUNT_ID) AS matched_balances
        FROM {GENERATED_SCHEMA}.TKQ_ACCOUNT a
        JOIN {GENERATED_SCHEMA}.TKQ_ACCOUNT_BALANCE b
          ON a.ACCOUNT_ID = b.ACCOUNT_ID AND a.BUSINESSEFFECTIVEDATE = b.BUSINESSEFFECTIVEDATE
    """)[0]
    accounts = quality[(generated, "TKQ_ACCOUNT")]["row_count"]
    balances = quality[(generated, "TKQ_ACCOUNT_BALANCE")]["row_count"]
    if not accounts or not balances or not (
        coverage["joined_rows"] == coverage["matched_accounts"] == accounts
        and coverage["joined_rows"] == coverage["matched_balances"] == balances
    ):
        raise ValueError("The generated population does not have full one-to-one snapshot join coverage.")
    audit = _rows(spark, f"""
        SELECT COUNT(*) AS audit_rows,
            COUNT(CASE WHEN source_run_id <> :source OR source_run_id IS NULL THEN 1 END) AS wrong_source,
            COUNT(CASE WHEN proposed THEN 1 END) AS proposed,
            COUNT(CASE WHEN proposed AND approved THEN 1 END) AS approved,
            COUNT(CASE WHEN proposed AND implemented THEN 1 END) AS implemented,
            COUNT(CASE WHEN proposed AND applied AND outcome = 'APPLIED' AND rows_processed > 0 THEN 1 END) AS applied,
            COUNT(CASE WHEN proposed AND outcome = 'SKIPPED' THEN 1 END) AS skipped,
            COUNT(CASE WHEN proposed AND approved AND NOT implemented THEN 1 END) AS unimplemented,
            COUNT(CASE WHEN outcome = 'LEGACY_FALLBACK' THEN 1 END) AS fallback
        FROM {GENERATED_SCHEMA}.rule_execution_log WHERE generation_id = :generation
    """, args)[0]
    if not audit["audit_rows"] or audit["wrong_source"]:
        raise ValueError("The generation audit is missing or references a different SOURCE profile.")

    def pair(index, key, value):
        return {label: _number(index.get((selected, *key), {}).get(value))
                for label, selected in (("source", source), ("generated", generated))}

    report = {
        "numeric": [
            {"field": field, "statistic": statistic, **pair(numeric, (table, field), statistic)}
            for table, field in _FIELDS for statistic in _STATISTICS
        ],
        "correlation": pair(correlation, (), "metric_value"),
        "conditional": [
            {"bucket": bucket, "rate": pair(conditional, (bucket,), "outcome_rate"),
             "count": pair(conditional, (bucket,), "record_count")}
            for bucket in _BUCKETS
        ],
        "row_counts": [{"table": name, **pair(quality, (name,), "row_count")} for name in GENERATED_TABLES],
        "join_coverage": 100 * coverage["matched_accounts"] / accounts,
        "rules": {key: int(audit[key]) for key in (
            "proposed", "approved", "implemented", "applied", "skipped", "unimplemented", "fallback"
        )},
    }
    if _validated_generation(spark, active) != versions:
        raise ValueError("Generated table versions changed during showcase export.")
    return report


def _index(rows, keys):
    indexed = {tuple(row[key] for key in keys): row for row in rows}
    if len(indexed) != len(rows):
        raise ValueError("Duplicate aggregates found for a selected profile.")
    return indexed


def _number(value):
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _format(value, digits=2):
    number = _number(value)
    return "Unavailable" if number is None else f"{number:,.{digits}f}"


def _difference(source, generated):
    if source is None or generated is None:
        return "Unavailable"
    if source == 0:
        return f"{generated - source:+,.2f} absolute"
    return f"{100 * (generated - source) / abs(source):+,.2f}%"


def _table(headers, rows, label):
    head = "".join(f'<th scope="col">{escape(header)}</th>' for header in headers)
    body = []
    for row in rows:
        cells = f'<th scope="row">{escape(str(row[0]))}</th>'
        cells += "".join(f"<td>{escape(str(value))}</td>" for value in row[1:])
        body.append(f"<tr>{cells}</tr>")
    hint = ""
    if len(headers) > 3:
        hint = '<p class="table-hint">Scroll or use arrow keys to view all columns.</p>\n'
    return hint + (
        f'<div class="table-scroll" role="region" aria-label="{escape(label)}" tabindex="0">\n'
        f'<table><caption class="sr-only">{escape(label)}</caption>'
        f'<thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>\n</div>'
    )


def render_measurements(report):
    """Render aggregate measurements as escaped static HTML, suitable for offline viewing."""
    numeric = [
        (f"{row['field']} · {row['statistic'].replace('mean_value', 'Mean').upper()}",
         _format(row["source"]), _format(row["generated"]),
         _difference(row["source"], row["generated"]))
        for row in report["numeric"]
    ]
    comparison_headers = ("Measurement", "SOURCE", "GENERATED", "Difference")
    field_labels = {
        "CREDIT_LIMIT_AMT": "Credit limit",
        "CURRENT_BALANCE_AMT": "Current balance",
        "AVAILABLE_TO_BUY_AMT": "Available credit",
        "OVERLIMIT_AMT": "Overlimit amount",
    }
    mean_rows = [
        (field_labels[metric["field"]] + " · Mean", *row[1:])
        for row, metric in zip(numeric, report["numeric"]) if metric["statistic"] == "mean_value"
    ]
    correlation = report["correlation"]
    mean_rows.append(("Balance / limit correlation", _format(correlation["source"], 4),
                      _format(correlation["generated"], 4), "—"))
    rate_rows = []
    for row in report["conditional"]:
        rate, count = row["rate"], row["count"]
        source_rate = "Unavailable" if rate["source"] is None else f"{100 * rate['source']:.2f}%"
        generated_rate = "Unavailable" if rate["generated"] is None else f"{100 * rate['generated']:.2f}%"
        rate_rows.append((row["bucket"], source_rate, generated_rate,
                          _format(count["source"], 0), _format(count["generated"], 0)))
    counts = [(row["table"], _format(row["source"], 0), _format(row["generated"], 0))
              for row in report["row_counts"]]
    rules = report["rules"]
    exported = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return "\n".join((
        '<div class="panel-heading"><h3 id="comparison-title">SOURCE vs GENERATED</h3>'
        '<span class="status-label status-measured">Measured results</span></div>',
        f'<p id="results-description">Completed profile comparison. Exported {exported}.</p>',
        f'<p class="measurement-summary">Snapshot join coverage <strong>{report["join_coverage"]:.2f}%</strong>. '
        'Saved Delta versions match the validated generation.</p>',
        _table(comparison_headers, mean_rows, "Mean and correlation comparison"),
        '<p class="measurement-note">Difference compares GENERATED with SOURCE. A zero baseline uses '
        'an absolute difference. Unavailable marks a missing or undefined statistic.</p>',
        '<details><summary>Numeric quantiles</summary>',
        _table(comparison_headers, numeric, "Full numeric comparison"),
        '</details>',
        '<details><summary>Past-due rates by utilization</summary>',
        _table(("Utilization", "SOURCE rate", "GENERATED rate", "SOURCE count", "GENERATED count"),
               rate_rows, "Past-due rates and sample sizes"),
        '</details><details><summary>Table row counts</summary>',
        _table(("Table", "SOURCE", "GENERATED"), counts, "Profile population counts"),
        '</details><details><summary>Rule execution outcomes</summary>',
        _table(("Outcome", "Proposals"), (
            ("Proposed", rules["proposed"]), ("Approved with provenance", rules["approved"]),
            ("Matched to implementation", rules["implemented"]), ("Applied", rules["applied"]),
            ("Skipped", rules["skipped"]), ("Approved without implementation", rules["unimplemented"]),
        ), "Rule proposal outcomes"),
        f'<p class="measurement-note">Legacy fallback executions {rules["fallback"]}. '
        'Approval, implementation, and application counts describe separate checks.</p></details>',
        '<p class="panel-footnote">Aggregate measurements from one pinned SOURCE baseline and its completed '
        'GENERATED profile. Privacy testing remains future work.</p>',
    ))


def export_showcase(spark, output_dir, *, template_dir=None):
    """Refresh only the results block and write a standalone HTML/CSS showcase."""
    template_dir = Path(template_dir) if template_dir else Path(__file__).resolve().parents[2] / "docs"
    if not all((template_dir / name).is_file() for name in ("index.html", "styles.css")):
        raise FileNotFoundError("Include docs/index.html and docs/styles.css alongside src/ for showcase export.")
    template = (template_dir / "index.html").read_text(encoding="utf-8")
    if template.count(_START) != 1 or template.count(_END) != 1 or template.index(_START) >= template.index(_END):
        raise ValueError("The showcase template needs one ordered pair of results markers.")
    report = collect_measurements(spark)
    before, results = template.split(_START, 1)
    _, after = results.split(_END, 1)
    updated = before + _START + "\n" + render_measurements(report) + "\n" + _END + after
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    stylesheet = template_dir / "styles.css"
    if stylesheet.resolve() != output / "styles.css":
        shutil.copyfile(stylesheet, output / "styles.css")
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=output, suffix=".html", delete=False) as file:
            temporary = Path(file.name)
            file.write(updated)
        os.replace(temporary, output / "index.html")
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return output / "index.html"
