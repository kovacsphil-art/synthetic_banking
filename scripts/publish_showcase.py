"""Retrieve one successful job's public report; never download tables or job logs."""

import json
import hashlib
import os
import re
from pathlib import Path, PurePosixPath
import sys
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
TASKS = {"source_profile", "llm_proposal", "approval_check", "synthetic_generation",
         "privacy_check", "generated_profile", "validate", "demo_export_verification", "reporting"}
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
    version = report.get("schema_version") if isinstance(report, dict) else None
    schemas = {"1.0": "pipeline-report-v1.schema.json", "2.0": "pipeline-report.schema.json"}
    if version not in schemas:
        raise ValueError("Unsupported public reporting version.")
    schema = json.loads((ROOT / "docs/reporting" / schemas[version]).read_text())
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
            or {t.get("task_key") for t in tasks} not in (TASKS, TASKS - {'demo_export_verification'})):
        raise ValueError("All expected pipeline tasks must have succeeded for this job.")
    latest = []
    for name in sorted({t['task_key'] for t in tasks}):
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
    if not isinstance(receipt, dict) or not isinstance(receipt.get("report_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", receipt["report_sha256"]):
        raise ValueError("A checksum-bound reporting receipt is required; repair reporting with the current notebook.")
    base = PurePosixPath(base_dir)
    if (not str(base).startswith("/Volumes/") or ".." in base.parts
            or len(base.parts) < 5 or receipt.get("schema_version") not in ("1.0", "2.0")):
        raise ValueError("Configure an absolute Unity Catalog reporting Volume directory.")
    expected = str(base / "runs" / str(run["run_id"]) / "latest-pipeline.json")
    if receipt.get("report_path") != expected:
        raise ValueError("Artifact path does not belong to this pipeline execution.")
    return expected


def latest_validated_run(client, job_id):
    """Select by final successful validation, including repairs of older jobs.

    List all retained completed summaries; retrieve metadata only for successes.
    No artifact/log/row reads occur until one complete pipeline is selected.
    """
    selected, selected_rank = None, None
    for candidate in client.jobs.list_runs(job_id=job_id, completed_only=True):
        summary = candidate.as_dict()
        if not successful(summary):
            continue
        run = client.jobs.get_run(run_id=candidate.run_id).as_dict()
        if run.get("job_id") != job_id or run.get("run_id") != candidate.run_id:
            raise ValueError("Run listing returned a different job.")
        try:
            tasks = validated_tasks(run, job_id)
        except ValueError:
            # A SUCCESS label alone does not make an incomplete/old task graph eligible.
            continue
        completed = next(t for t in tasks if t["task_key"] == "validate").get("end_time")
        if type(completed) is not int or completed <= 0 or type(run.get("run_id")) is not int or run["run_id"] <= 0:
            raise ValueError("Successful validation has no unambiguous completion metadata.")
        rank = (completed, run["run_id"])
        if selected_rank is None or rank > selected_rank:
            selected, selected_rank = run, rank
    return selected


def retrieve(client, job_id, base_dir, run_id=None, with_receipt=False):
    if type(job_id) is not int or job_id <= 0:
        raise ValueError("A positive configured job ID is required.")
    if run_id is not None:
        if type(run_id) is not int or run_id <= 0:
            raise ValueError("An explicit run ID must be a positive integer.")
        run = client.jobs.get_run(run_id=run_id).as_dict()
        if run.get("run_id") != run_id:
            raise ValueError("The returned run differs from the requested execution.")
    else:
        run = latest_validated_run(client, job_id)
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
    report = validate_report(raw)
    receipt = json.loads(output["notebook_output"]["result"])
    if report["schema_version"] != receipt["schema_version"]:
        raise ValueError("Report and execution receipt versions differ.")
    if hashlib.sha256(raw).hexdigest() != receipt['report_sha256']:
        raise ValueError('Report checksum differs from its execution receipt.')
    if 'demo_dataset' in report and (receipt.get('demo_export_status') != 'VERIFIED_DEMO_ONLY' or
            not receipt.get('report_sha256') or 'demo_export_verification' not in {t['task_key'] for t in tasks}):
        raise ValueError('Verified execution-bound demo receipt required.')
    return (report, run, receipt) if with_receipt else report


def retrieve_demo(client, report, run, receipt, base_dir, destination):
    """Only fixed filenames inside this successful execution's reporting folder.

    No SOURCE/Delta reads. Local files stay ignored and are never Git-staged.
    """
    from jsonschema import Draft202012Validator, FormatChecker
    reference = report.get('demo_dataset')
    if not reference or receipt.get('demo_export_status') != 'VERIFIED_DEMO_ONLY':
        raise ValueError('This execution has no eligible demo export.')
    folder = PurePosixPath(base_dir) / 'runs' / str(run['run_id']) / 'demo'
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)

    def read(name, maximum, expected=None):
        response = client.files.download(str(folder / name))
        target = destination / name
        size, digest = 0, hashlib.sha256()
        try:
            with target.open('wb') as stream:
                while True:
                    chunk = response.contents.read(min(1024*1024, maximum-size+1))
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > maximum:
                        raise ValueError('Demo artifact exceeds its limit.')
                    digest.update(chunk)
                    stream.write(chunk)
        finally:
            response.contents.close()
        if expected and (size != expected['bytes'] or digest.hexdigest() != expected['sha256']):
            raise ValueError('Demo artifact changed after verification.')
        return target

    manifest_path = read('dataset-downloads.json', 16*1024)
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != receipt.get('demo_manifest_sha256'):
        raise ValueError('Demo manifest differs from the reporting receipt.')
    manifest = json.loads(manifest_path.read_bytes())
    schema = json.loads((ROOT / 'docs/reporting/dataset-downloads.schema.json').read_text())
    if (not Draft202012Validator(schema, format_checker=FormatChecker()).is_valid(manifest) or
            manifest.get('publication_status') != 'UNPUBLISHED' or manifest.get('publication_checked_at') is not None or
            {k:manifest.get(k) for k in ('dataset_version','release_mode','preview_sha256')} != reference or
            manifest.get('privacy_status') != report.get('privacy',{}).get('status')):
        raise ValueError('Demo download metadata differs from the validated report.')
    counts = {r['table']:r['value'] if r['status']=='AVAILABLE' else None for r in report['generation']['table_rows']}
    if sum(a['bytes'] for a in manifest['assets'][2:]) > 512*1024*1024:
        raise ValueError('Demo package exceeds its reviewed byte budget.')
    if any(a['rows'] != counts.get(a['key']) for a in manifest['assets'][2:]):
        raise ValueError('Demo table counts differ from the report.')
    preview_path = read('demo-preview.json', 96*1024)
    if hashlib.sha256(preview_path.read_bytes()).hexdigest() != manifest['preview_sha256']:
        raise ValueError('Demo preview differs from this execution.')
    for asset in manifest['assets']:
        read(asset['file'], asset['bytes'], asset)
    if str(ROOT/'src') not in sys.path:
        sys.path.insert(0,str(ROOT/'src'))
    from synthetic_banking.demo_artifact_validation import verify_demo_package
    verify_demo_package(destination,manifest)
    return destination


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
    client = WorkspaceClient()
    result = retrieve(client, job_id, os.environ["REPORT_OUTPUT_DIR"], int(run_id) if run_id else None, with_receipt=True)
    if result is None:
        print("No successful pipeline execution is available; published site retained.")
        return
    report, run, receipt = result
    demo_ready = False
    if os.environ.get('SAGE_PUBLISH_DEMO_DATASETS') == 'true' and report.get('demo_dataset'):
        retrieve_demo(client, report, run, receipt, os.environ['REPORT_OUTPUT_DIR'], ROOT / '.databricks/publication/demo')
        demo_ready = True
    save_report(report, ROOT / "docs/latest-pipeline.json")
    print("Validated sanitized report ready for publication.")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write("ready=true\n")
        output.write('demo_ready=' + str(demo_ready).lower() + '\n')


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # No SDK errors, output receipts, tokens, paths or rejected payloads in logs.
        print("Publication stopped: verify job success, reporting receipt, public schema and access configuration.", file=sys.stderr)
        sys.exit(1)
