# Databricks notebook source
# Aggregate disclosure screens. Findings block row release, not aggregate profiling/reporting.
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
from synthetic_banking.privacy import run_privacy_assessment
from synthetic_banking.workflow import required_id, publish_values

for name in ("source_run_id", "batch_id", "generation_id"):
    dbutils.widgets.text(name, "")
ids = {name: required_id(dbutils.widgets.get(name).strip(), name)
       for name in ("source_run_id", "batch_id", "generation_id")}
assessment = run_privacy_assessment(spark, ids["source_run_id"], ids["generation_id"], batch_id=ids["batch_id"])
publish_values(dbutils, **ids, privacy_assessment_id=assessment.assessment_id,
               privacy_status=assessment.status, row_level_release_allowed=assessment.status == "PASS")
print(f"Privacy screening: {assessment.status}. Aggregate-only profiling and reporting may continue.")
for metric in assessment.metrics:
    print(f"{metric.check_name}: {metric.status}; evaluated rows={metric.evaluated_rows}; flagged rows={metric.flagged_rows}")
print("Screening is not anonymization certification or authorization to distribute row-level data.")
