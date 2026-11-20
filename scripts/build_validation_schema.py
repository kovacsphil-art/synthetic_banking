"""Maintain the closed public v2 schema from fixed report keys (no live inputs)."""

import json
from pathlib import Path
from synthetic_banking.validation_reporting import build_validation_report, NUMERIC, DATES, CARDINALITIES, RULES, TABLES, THRESHOLDS, POLICY_VERSION, MIN_CONDITIONAL_ROWS

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "docs/reporting"


def obj(properties):
    return dict(type="object", properties=properties, required=list(properties), additionalProperties=False)


def array(item, length):
    return dict(type="array", items=item, minItems=length, maxItems=length)


def enum(values):
    return {"enum": list(values)}


def build_schema():
    template = build_validation_report([])
    number = {"type": ["number", "null"]}
    integer = {"type": "integer", "minimum": 0}
    status = enum(("STRONG", "ACCEPTABLE", "NEEDS_REVIEW", "UNAVAILABLE"))
    assessment = obj(dict(
        key=enum(a["key"] for a in template["assessments"]), label=enum(a["label"] for a in template["assessments"]),
        family=enum(sorted({a["family"] for a in template["assessments"]})), status=status,
        source=number, generated=number, difference=number, score=number, policy=enum((*THRESHOLDS, None)),
        source_n=number, generated_n=number, source_count=number, generated_count=number,
        reason=enum((None, "metric_unavailable", "zero_or_missing_source_iqr", "insufficient_conditional_rows",
                     "source_comparison_unavailable", "not_in_saved_fidelity_report"))))
    report = obj(dict(
        status=enum(("AVAILABLE", "PENDING")), policy_version={"const": POLICY_VERSION},
        thresholds=obj({k: obj({name: {"const": value} for name, value in v.items()}) for k, v in THRESHOLDS.items()}),
        min_conditional_rows={"const": MIN_CONDITIONAL_ROWS},
        summary=obj({k: enum(("PENDING", "REVIEW_REQUIRED", "PARTIAL", "WITHIN_TOLERANCE")) if k == "comparison_status" else integer
                     for k in template["summary"]}),
        strengths={"type": "array", "items": assessment["properties"]["key"], "maxItems": 6, "uniqueItems": True},
        weaknesses={"type": "array", "items": assessment["properties"]["key"], "maxItems": 6, "uniqueItems": True},
        assessments=array(assessment, len(template["assessments"])),
        numeric=array(obj(dict(key=enum(r[0] for r in NUMERIC), label=enum(r[3] for r in NUMERIC), source_iqr=number,
            percentiles=array(obj(dict(name=enum(("P25", "P50", "P75", "P95")), source=number, generated=number, difference=number)), 4),
            average_difference_pct_iqr=number, max_difference_pct_iqr=number, status=status)), len(NUMERIC)),
        categorical=array(obj(dict(category=enum(("Y", "N")), source=number, generated=number, absolute_difference_pp=number, status=status)), 2),
        dates=array(obj(dict(key=enum(r[0] for r in DATES), label=enum(r[3] for r in DATES), total_variation_pct=number,
            earliest_shift_days=number, latest_shift_days=number, status=status)), len(DATES)),
        cardinality=array(obj(dict(key=enum(r[0] for r in CARDINALITIES), label=enum(r[2] for r in CARDINALITIES),
            total_variation_pct=number, source_mean=number, generated_mean=number, status=status,
            bins=array(obj(dict(bucket=enum(("0", "1", "2", "3", "4", "5+")), source=number, generated=number, absolute_difference_pp=number)), 6))), len(CARDINALITIES)),
        populations=array(obj(dict(table=enum(TABLES), source=number, generated=number, difference=number)), len(TABLES)),
        accounts_per_person=obj(dict(source=number, generated=number)),
        rule_outcomes=array(obj(dict(implementation=enum(r[0] for r in RULES), target=enum(r[1] for r in RULES),
            proposed=integer, approved=integer, applied=integer, skipped=integer)), len(RULES))))
    # Optional, aggregate-only addition: historical v2 artifacts remain valid.
    count = {"type": ["integer", "null"], "minimum": 0}
    rate = {"type": ["number", "null"], "minimum": 0, "maximum": 1}
    report["properties"]["dependency_fidelity"] = obj(dict(
        categorical=array(obj(dict(
            key=enum(("account_type_product", "client_tsys_product")),
            label=enum(("Account type / client product", "Client / TSYS product")),
            source_cramers_v=rate, generated_cramers_v=rate, absolute_association_gap=rate,
            source_n=count, generated_n=count, conditional_tvd_pct={"type": ["number", "null"], "minimum": 0, "maximum": 100},
            unsupported_combination_rate=rate)), 2),
        numeric_segments=array(obj(dict(bucket=enum(("Q1", "Q2", "Q3", "Q4")),
            source_mean=number, generated_mean=number, mean_difference=number,
            source_n=count, generated_n=count)), 4)))
    schema = json.loads((FOLDER / "pipeline-report-v1.schema.json").read_text())
    schema["title"] = "Synthetic banking public pipeline report, version 2.0"
    schema["description"] = "Sanitized aggregates and prototype validation screening; no execution IDs or row records."
    schema["properties"]["schema_version"] = {"const": "2.0"}
    schema["properties"]["validation_report"] = report
    schema["required"].append("validation_report")
    return schema


if __name__ == "__main__":
    (FOLDER / "pipeline-report.schema.json").write_text(json.dumps(build_schema(), indent=2)+"\n", encoding="utf-8")
    template = build_validation_report([])
    config = dict(assessments={a["key"]: {k: a[k] for k in ("label", "family", "policy")} for a in template["assessments"]},
                  thresholds=THRESHOLDS)
    code = "/* Generated from validation_reporting.py; run scripts/build_validation_schema.py. */\n"
    code += "(() => { const config = " + json.dumps(config, indent=2) + ";\n"
    code += "if (typeof module !== 'undefined' && module.exports) module.exports = config;\n"
    code += "if (typeof window !== 'undefined') window.ValidationConfig = config; })();\n"
    (ROOT / "docs/validation-config.js").write_text(code, encoding="utf-8")
