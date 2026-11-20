# Databricks notebook source
# Validate one exact SOURCE -> batch -> generation -> GENERATED profile chain.
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
from synthetic_banking.workflow import validate_execution, required_id, publish_values, utc_now

for name in ("source_run_id", "batch_id", "generation_id", "generated_run_id"):
    dbutils.widgets.text(name, "")
ids = {name: required_id(dbutils.widgets.get(name).strip(), name)
       for name in ("source_run_id", "batch_id", "generation_id", "generated_run_id")}
from synthetic_banking.fidelity import METRIC_SCHEMA

report = validate_execution(spark, **ids)
display(spark.createDataFrame(report["metrics"], METRIC_SCHEMA))
publish_values(dbutils, **ids, validation_status="PASS", validated_at=utc_now())
print("PASS: saved generation versions, explicit profile lineage and generated integrity checks.")
print("Statistical differences remain visible; no new fidelity thresholds or overall score were introduced.")
