"""Job handoffs and provenance guards; no profiling or generation formulas."""

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json

from synthetic_banking.config import PROFILE_SCHEMA
from synthetic_banking.profiles import select_source_run
from synthetic_banking.rules import load_rule_proposals


class ApprovalRequired(RuntimeError):
    """An intentional job stop pending individual human review."""


def required_id(value, name):
    if not isinstance(value, str) or not value.strip() or "{{" in value or "}}" in value:
        raise ValueError(f"A resolved, explicit {name} is required.")
    return value.strip()


def _rows(spark, query, args):
    return [row.asDict() for row in spark.sql(query, args=args).collect()]


def require_source(spark, source_run_id):
    source = required_id(source_run_id, "SOURCE run_id")
    return select_source_run(spark, source)


def require_batch(spark, source_run_id, batch_id):
    source = require_source(spark, source_run_id)
    batch = required_id(batch_id, "proposal batch_id")
    rows = _rows(spark, f"""
        SELECT * FROM {PROFILE_SCHEMA}.ai_rule_batches WHERE batch_id = :batch
    """, {"batch": batch})
    if len(rows) != 1 or rows[0].get("source_run_id") != source:
        raise ValueError("Proposal batch must identify exactly this completed SOURCE run.")
    row = rows[0]
    if not row.get("prompt_sha256") or not row.get("model_endpoint"):
        raise ValueError("Proposal batch is missing model/prompt provenance.")
    try:
        response = json.loads(row["response"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Proposal batch has no valid stored JSON response.") from error
    if not isinstance(response, dict) or not isinstance(response.get("rules"), list):
        raise ValueError("Proposal batch has no stored rules array.")
    return row, len(response["rules"])


def validate_reuse(spark, source_run_id, batch_id):
    """Reuse is explicit and paired; never choose a previous batch implicitly."""
    if bool(source_run_id) != bool(batch_id):
        raise ValueError("Reuse requires both reuse_source_run_id and reuse_batch_id.")
    if source_run_id:
        require_batch(spark, source_run_id, batch_id)


def _json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"Unsupported provenance value: {type(value).__name__}")


@dataclass(frozen=True)
class ApprovalDecision:
    source_run_id: str
    batch_id: str
    status: str
    fingerprint: str
    proposed: int
    approved: int
    pending: int


def check_approvals(spark, source_run_id, batch_id):
    """Review only this exact batch; approval never implies implementation/application."""
    batch, expected_count = require_batch(spark, source_run_id, batch_id)
    rows = _rows(spark, f"""
        SELECT * FROM {PROFILE_SCHEMA}.ai_rule_proposals
        WHERE batch_id = :batch ORDER BY proposal_id
    """, {"batch": batch_id})
    ids = [row.get("proposal_id") for row in rows]
    if (len(rows) != expected_count or any(not isinstance(value, str) or not value.strip() for value in ids)
            or len(ids) != len(set(ids))
            or any(row.get("source_run_id") != source_run_id or row.get("batch_id") != batch_id for row in rows)):
        raise ValueError("Proposal rows are incomplete, duplicated, or inconsistent with batch/SOURCE provenance.")
    proposals = load_rule_proposals(spark, source_run_id, batch_id)
    if {p.proposal_id for p in proposals} != set(ids) or len(proposals) != len(rows):
        raise ValueError("Proposal review provenance is unavailable or inconsistent.")
    for proposal in proposals:
        if proposal.approval_status not in {"PENDING", "APPROVED", "REJECTED"}:
            raise ValueError("Unknown proposal review state; use PENDING, APPROVED, or REJECTED.")
        if proposal.approval_status != "PENDING" and not proposal.has_review_provenance:
            raise ValueError("Reviewed proposals require explicit reviewer/time and valid nonlegacy batch provenance.")
    fingerprint = hashlib.sha256(json.dumps(
        {"batch": batch, "proposals": rows}, sort_keys=True, default=_json_value,
        allow_nan=False, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    pending = sum(p.approval_status == "PENDING" for p in proposals)
    return ApprovalDecision(source_run_id, batch_id, "APPROVAL_REQUIRED" if pending else "READY",
                            fingerprint, len(rows), sum(p.approved for p in proposals), pending)


def enforce_approval(decision, expected_fingerprint=None):
    if expected_fingerprint is not None:
        required_id(expected_fingerprint, "approval fingerprint")
        if decision.fingerprint != expected_fingerprint:
            raise ValueError("Batch/proposal/review metadata changed after the approval check. Repair approval_check first.")
    if decision.status != "READY":
        raise ApprovalRequired(
            f"APPROVAL_REQUIRED: {decision.pending} proposals require individual review for SOURCE "
            f"{decision.source_run_id}, batch {decision.batch_id}. Approve/reject them in Notebook 02, "
            "then repair approval_check and its downstream tasks. No generation was started."
        )


def require_generation(spark, source_run_id, batch_id, generation_id):
    from synthetic_banking.profiling_run import completed_generation
    require_batch(spark, source_run_id, batch_id)
    generation = required_id(generation_id, "generation_id")
    state = completed_generation(spark)  # Includes all saved Delta version checks.
    if (state["generation_id"] != generation or state["source_run_id"] != source_run_id
            or state["proposal_batch_id"] != batch_id):
        raise ValueError("Validated generation does not match the explicit SOURCE, batch, and generation IDs.")
    return state


def require_profile_pair(spark, source_run_id, batch_id, generation_id, generated_run_id):
    require_generation(spark, source_run_id, batch_id, generation_id)
    generated = required_id(generated_run_id, "GENERATED run_id")
    runs = _rows(spark, f"""
        SELECT * FROM {PROFILE_SCHEMA}.profile_runs WHERE run_id = :generated
    """, {"generated": generated})
    if (len(runs) != 1 or runs[0].get("profile_type") != "GENERATED"
            or runs[0].get("status") != "COMPLETED" or runs[0].get("completed_at") is None):
        raise ValueError("The explicit GENERATED profiling run is not completed.")
    lineage = _rows(spark, f"""
        SELECT * FROM {PROFILE_SCHEMA}.profile_run_lineage WHERE run_id = :generated
    """, {"generated": generated})
    if (len(lineage) != 1 or lineage[0].get("profile_type") != "GENERATED"
            or lineage[0].get("source_run_id") != source_run_id or lineage[0].get("generation_id") != generation_id):
        raise ValueError("GENERATED profiling lineage does not match this SOURCE and generation.")


def validate_execution(spark, source_run_id, batch_id, generation_id, generated_run_id):
    from synthetic_banking.fidelity import create_fidelity_report
    require_profile_pair(spark, source_run_id, batch_id, generation_id, generated_run_id)
    report = create_fidelity_report(spark, source_run_id, generated_run_id)
    if report["generation_id"] != generation_id:
        raise ValueError("Fidelity report generation does not match this execution.")
    if any(row.get("generated_check_status") == "ISSUE" for row in report["metrics"]):
        raise ValueError("Generated integrity issues remain in the fidelity report; inspect fidelity_metrics.")
    return report


def publish_values(dbutils, **values):
    """No fallback/debug IDs: missing handoffs must fail visibly."""
    for key, value in values.items():
        dbutils.jobs.taskValues.set(key=key, value=value)


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
