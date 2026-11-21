"""Closed public projection of a pipeline-pinned privacy assessment, never rows."""
import json
import math
from dataclasses import asdict
from synthetic_banking.config import PROFILE_SCHEMA
from synthetic_banking.privacy_checks import PrivacyPolicy, POLICY_VERSION

PATTERNS = (
    ("customer_category", "Customer category pattern", "PERSON", ("GENDER_CD", "PREF_LANG_CD", "CUST_TYPE_CD")),
    ("employment", "Employment / occupation pattern", "PERSON", ("EMP_TYPE_CD", "OCCUP_CAT_CD")),
    ("account_product", "Account type / product pattern", "TKQ_ACCOUNT", ("ACCOUNT_TYPE_CD", "CLIENT_PRODUCT_CD")),
)
STATUSES = {"PASS", "INFO", "FAIL", "REVIEW_REQUIRED", "UNAVAILABLE", "ERROR"}


def _number(value):
    return value if type(value) in (int, float) and math.isfinite(value) else None


def _count(value):
    value = _number(value)
    return int(value) if value is not None and value >= 0 and value == int(value) else None


def _details(value):
    try:
        result = json.loads(value or "{}")
        return result if isinstance(result, dict) else {}
    except (TypeError, ValueError):
        return {}


def public_privacy_summary(assessment=None, metrics=()):
    """Missing evidence stays unavailable; no reviewer identity, pattern or ID escapes."""
    assessment = assessment or {}
    status = assessment.get("status")
    status = status if status in {"PASS", "REVIEW_REQUIRED", "BLOCKED"} else "UNAVAILABLE"
    policy = None
    try:
        configured = PrivacyPolicy(**json.loads(assessment["policy_json"]))
        if assessment.get("policy_version") != POLICY_VERSION or assessment.get("policy_sha256") != configured.fingerprint:
            raise ValueError("Privacy policy provenance mismatch.")
        policy = asdict(configured)
    except (KeyError, TypeError, ValueError):
        status = "UNAVAILABLE"
    complete = bool(metrics) and len(metrics) == _count(assessment.get("metric_count"))
    if complete:
        from synthetic_banking.privacy import _complete_checks
        complete = _complete_checks(metrics)
    if status == "PASS" and not complete:
        status = "BLOCKED"
    if status == "PASS" and any(r.get("status") not in {"PASS", "INFO"} for r in metrics):
        status = "BLOCKED" if any(r.get("status") in {"FAIL", "ERROR", "UNAVAILABLE"} for r in metrics) else "REVIEW_REQUIRED"

    def group(name):
        return [r for r in metrics if r.get("check_name") == name]

    def total(name, expected):
        rows = group(name)
        values = [_count(r.get("flagged_rows")) for r in rows]
        return sum(values) if complete and len(rows) == expected and all(v is not None for v in values) else None

    near = group("QUASI_SIMILARITY")
    near = near[0] if complete and len(near) == 1 else {}
    d = _details(near.get("details_json"))
    patterns = []
    for key, label, table, columns in PATTERNS:
        matches = [r for r in group("RARE_COMBINATION") if r.get("logical_table_name") == table and tuple(r.get("columns") or ()) == columns]
        row = matches[0] if complete and len(matches) == 1 else {}
        detail = _details(row.get("details_json"))
        coverage = _number(detail.get("complete_case_coverage"))
        patterns.append(dict(key=key, label=label,
            status=row.get("status") if row.get("status") in STATUSES else "UNAVAILABLE",
            evaluated_rows=_count(row.get("evaluated_rows")), synthetic_rare_rows=_count(detail.get("synthetic_rare")),
            source_rare_match_rows=_count(detail.get("source_rare")),
            complete_case_coverage=coverage if coverage is not None and 0 <= coverage <= 1 else None))
    coverage = _number(d.get("complete_case_coverage"))
    evaluated, flagged = _count(near.get("evaluated_rows")), _count(near.get("flagged_rows"))
    return dict(status=status, row_level_downloads_enabled=False, formal_anonymization_certified=False,
        policy_version=POLICY_VERSION if policy else None, policy=policy,
        checks_recorded=len(metrics) if assessment else None, checks_expected=_count(assessment.get("metric_count")),
        identifier_overlap_rows=total("IDENTIFIER_OVERLAP", 9), exact_source_row_matches=total("FULL_ROW_MATCH", 6),
        near_matches=dict(variables=["BIRTH_DT", "SINCE_DT", "GENDER_CD"],
            evaluated_rows=evaluated, flagged_rows=flagged,
            flagged_fraction=flagged/evaluated if flagged is not None and evaluated and flagged <= evaluated else None,
            minimum_combined_distance_days=_count(d.get("minimum_matched_distance_days")),
            complete_case_coverage=coverage if coverage is not None and 0 <= coverage <= 1 else None),
        categorical_patterns=patterns)


def load_public_privacy(spark, source, generation, batch, assessment_id):
    """Bind to the exact task handoff, not a latest assessment from another policy."""
    from synthetic_banking.privacy import _validated_generation, _complete_checks
    from synthetic_banking.privacy_sources import load_source_snapshots, snapshot_signature
    args = {"source": source, "generation": generation, "assessment": assessment_id}
    records = [r.asDict() for r in spark.sql(f"SELECT * FROM {PROFILE_SCHEMA}.privacy_assessments WHERE assessment_id=:assessment", args=args).collect()]
    if (len(records) != 1 or records[0].get("source_run_id") != source or records[0].get("generation_id") != generation
            or records[0].get("completed_at") is None):
        raise ValueError("The privacy assessment does not match this completed pipeline execution.")
    record = records[0]
    state = _validated_generation(spark, source, generation, batch)
    if (json.loads(record.get("generated_versions_json") or "null") != dict(state["validated_versions"])
            or record.get("source_snapshot_sha256") != snapshot_signature(load_source_snapshots(spark, source))):
        raise ValueError("Privacy and validated dataset snapshots do not match.")
    rows = [r.asDict() for r in spark.sql(f"""SELECT * FROM {PROFILE_SCHEMA}.privacy_metrics
        WHERE assessment_id=:assessment AND source_run_id=:source AND generation_id=:generation""", args=args).collect()]
    if record.get("status") == "PASS" and not _complete_checks(rows):
        record = dict(record, status="BLOCKED")
    return public_privacy_summary(record, rows)
