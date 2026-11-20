"""Retrieve one successful job's public report; never download tables or job logs."""

import json
import os
import re
from pathlib import Path, PurePosixPath
import sys
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
TASKS = {"source_profile", "llm_proposal", "approval_check", "synthetic_generation",
         "privacy_check", "generated_profile", "validate", "reporting"}
MAX_BYTES = 1024 * 1024
WARNINGS = {
    "FIDELITY_THRESHOLDS_NOT_CONFIGURED": "Integrity passed. Statistical differences are observations for review, without an overall acceptance score.",
    "APPROVED_RULES_NOT_IMPLEMENTED": "Some approved proposals have no matching implementation and were skipped.",
    "SKIPPED_PROPOSALS": "Some proposals did not affect this dataset; inspect the internal rule audit.",
    "UNAVAILABLE_METRICS": "Some selected aggregate measurements are unavailable.",
}


def validate_report(raw):
    from jsonschema import Draft202012Validator, FormatChecker
    if len(raw) > MAX_BYTES:
        raise ValueError("Report exceeds public artifact size limit.")
    def reject_constant(value):
        raise ValueError("Non-finite JSON value.")
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key.")
            result[key] = value
        return result
    report = json.loads(raw, parse_constant=reject_constant, object_pairs_hook=unique_object)
    schema = json.loads((ROOT / "docs/reporting/pipeline-report.schema.json").read_text())
    # Do not include validator errors: they may contain rejected private values.
    if not Draft202012Validator(schema, format_checker=FormatChecker()).is_valid(report):
        raise ValueError("Report does not match the public schema.")
    # date-time format support is optional in jsonschema installations.
    timestamp = report["pipeline_completed_at"]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", timestamp):
        raise ValueError("Invalid completion timestamp.")
    datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    # The schema allows message strings; replace them with fixed public wording.
    for warning in report["warnings"]:
        warning["message"] = WARNINGS[warning["code"]]
    return report


def successful(run):
    state = run.get("state") or {}
    return state.get("life_cycle_state") == "TERMINATED" and state.get("result_state") == "SUCCESS"


def validated_tasks(run, job_id):
    """Check final attempts, including API responses containing retry history."""
    tasks = run.get("tasks") or []
    if (run.get("job_id") != job_id or not successful(run)
            or {t.get("task_key") for t in tasks} != TASKS):
        raise ValueError("All expected pipeline tasks must have succeeded for this job.")
    latest = []
    for name in sorted(TASKS):
        attempts = [t for t in tasks if t["task_key"] == name]
        if len(attempts) > 1:
            # Repairs can reset attempt_number; start_time identifies chronology.
            ranks = []
            for task in attempts:
                start, attempt = task.get("start_time"), task.get("attempt_number", 0)
                if type(start) is not int or start <= 0 or type(attempt) is not int or attempt < 0:
                    raise ValueError("Task-attempt history lacks ordering evidence.")
                ranks.append((start, attempt))
            rank = max(ranks)
            if ranks.count(rank) != 1:
                raise ValueError("Task-attempt history is ambiguous.")
            task = attempts[ranks.index(rank)]
        else:
            task = attempts[0]
        if not successful(task):
            raise ValueError("The final attempt of every pipeline task must succeed.")
        latest.append(task)
    return latest


def report_path(run, output, job_id, base_dir):
    validated_tasks(run, job_id)
    if output.get("error") or not output.get("notebook_output") or output["notebook_output"].get("truncated"):
        raise ValueError("Reporting task has no complete success receipt.")
    receipt = json.loads(output["notebook_output"]["result"])
    base = PurePosixPath(base_dir)
    if (not str(base).startswith("/Volumes/") or ".." in base.parts
            or len(base.parts) < 5 or receipt.get("schema_version") != "1.0"):
        raise ValueError("Configure an absolute Unity Catalog reporting Volume directory.")
    expected = str(base / "runs" / str(run["run_id"]) / "latest-pipeline.json")
    if receipt.get("report_path") != expected:
        raise ValueError("Artifact path does not belong to this pipeline execution.")
    return expected


def retrieve(client, job_id, base_dir, run_id=None):
    if run_id:
        run = client.jobs.get_run(run_id=run_id).as_dict()
    else:
        # Newest-started successful execution; repaired failed runs appear here too.
        run = None
        for candidate in client.jobs.list_runs(job_id=job_id, completed_only=True):
            if successful(candidate.as_dict()):
                run = client.jobs.get_run(run_id=candidate.run_id).as_dict()
                break
        if run is None:
            return None
    # Validate before reading any notebook output or file.
    tasks = validated_tasks(run, job_id)
    task = next(t for t in tasks if t["task_key"] == "reporting")
    output = client.jobs.get_run_output(run_id=task["run_id"]).as_dict()
    path = report_path(run, output, job_id, base_dir)
    response = client.files.download(path)
    try:
        raw = response.contents.read(MAX_BYTES + 1)
    finally:
        response.contents.close()
    return validate_report(raw)


def save_report(report, target):
    if target.exists():
        previous = validate_report(target.read_bytes())
        timestamp = lambda r: datetime.fromisoformat(r["pipeline_completed_at"].replace("Z", "+00:00"))
        if timestamp(report) < timestamp(previous):
            raise ValueError("An older completion cannot replace the current public report.")
    data = json.dumps(report, indent=2, allow_nan=False) + "\n"
    temporary = target.with_suffix(".json.tmp")
    try:
        temporary.write_text(data, encoding="utf-8")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    from databricks.sdk import WorkspaceClient
    job_id = int(os.environ["DATABRICKS_JOB_ID"])
    run_id = os.environ.get("PIPELINE_RUN_ID", "").strip()
    report = retrieve(WorkspaceClient(), job_id, os.environ["REPORT_OUTPUT_DIR"], int(run_id) if run_id else None)
    if report is None:
        print("No successful pipeline execution is available; published site retained.")
        return
    save_report(report, ROOT / "docs/latest-pipeline.json")
    print("Validated sanitized report ready for publication.")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write("ready=true\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # No SDK errors, output receipts, tokens, paths or rejected payloads in logs.
        print("Publication stopped: verify job success, reporting receipt, public schema and access configuration.", file=sys.stderr)
        sys.exit(1)
