# Databricks notebook source
# Publish sanitized aggregates after this exact execution passes validation.
import sys
from pathlib import Path

for repo_dir in (Path.cwd(), Path.cwd().parent, *(Path(path) for path in sys.path if path)):
    src_dir = repo_dir if repo_dir.name == "src" else repo_dir / "src"
    if (src_dir / "synthetic_banking" / "workflow.py").is_file():
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        break
else:
    raise RuntimeError("Keep notebooks/ and src/ together in the deployed project.")

# COMMAND ----------
from synthetic_banking.reporting import export_public_report, SCHEMA_VERSION
from synthetic_banking.workflow import required_id, publish_values
from pathlib import PurePosixPath
import json

for name in ("source_run_id", "batch_id", "generation_id", "generated_run_id", "validation_status", "validated_at", "report_output_dir"):
    dbutils.widgets.text(name, "")
execution = {name: required_id(dbutils.widgets.get(name).strip(), name)
             for name in ("source_run_id", "batch_id", "generation_id", "generated_run_id", "validation_status", "validated_at")}
dbutils.widgets.text("workflow_run_id", "")
dbutils.widgets.text("privacy_assessment_id", "")
execution["privacy_assessment_id"] = dbutils.widgets.get("privacy_assessment_id").strip()
workflow_run_id = dbutils.widgets.get("workflow_run_id").strip()
output_dir = dbutils.widgets.get("report_output_dir").strip()
dbutils.widgets.text("demo_export_status", "DISABLED")
dbutils.widgets.text("demo_dataset_version", "")
from synthetic_banking.demo_workflow import reporting_demo_context, IDS
demo_status = dbutils.widgets.get("demo_export_status").strip()
demo_dataset, demo_manifest_sha256 = reporting_demo_context(output_dir, workflow_run_id, demo_status,
    dbutils.widgets.get("demo_dataset_version").strip(), {k: execution[k] for k in IDS}, include_manifest_hash=True)
if workflow_run_id:
    required_id(execution["privacy_assessment_id"], "privacy assessment_id")
    if not workflow_run_id.isascii() or not workflow_run_id.isdigit():
        raise ValueError("A numeric Databricks workflow run ID is required.")
    # Bind the downloaded artifact to this job execution, including repaired runs.
    output_dir = str(PurePosixPath(output_dir) / "runs" / workflow_run_id)
report_path = export_public_report(spark, output_dir, demo_dataset=demo_dataset, **execution)
publish_values(dbutils, report_path=str(report_path), report_schema_version=SCHEMA_VERSION, pipeline_status="COMPLETED")
from synthetic_banking.demo_export import digest_file
dbutils.notebook.exit(json.dumps({"report_path": str(report_path), "schema_version": SCHEMA_VERSION,
    "report_sha256": digest_file(report_path), "demo_export_status": demo_status,
    "demo_manifest_sha256": demo_manifest_sha256}))
