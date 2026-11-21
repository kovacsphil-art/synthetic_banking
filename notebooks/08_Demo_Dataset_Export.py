# Databricks notebook source
# MAGIC %md
# MAGIC # Private demo dataset export
# MAGIC Run only after a validated cohort and GENERATED profile exist. Explicit DEMO_ONLY
# MAGIC mode and exact IDs are required. Every SOURCE and generated row must pass exact
# MAGIC reviewed-code reproduction; no table is regenerated or overwritten. Privacy
# MAGIC REVIEW_REQUIRED remains intact. This task does not publish files or enable downloads.

# COMMAND ----------
# MAGIC %pip install openpyxl==3.1.5

# COMMAND ----------
import sys
from pathlib import Path

for repo_dir in (Path.cwd(), Path.cwd().parent, *(Path(path) for path in sys.path if path)):
    src_dir = repo_dir if repo_dir.name == "src" else repo_dir / "src"
    if (src_dir / "synthetic_banking" / "demo_export.py").is_file():
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        break
else:
    raise RuntimeError("Keep notebooks/, scripts/ and src/ together in the deployed project.")

# COMMAND ----------
import json
from synthetic_banking.demo_export import export_demo_dataset, DemoExportError

parameters = ("release_mode", "dataset_version", "source_run_id", "batch_id",
              "generation_id", "generated_run_id", "privacy_assessment_id")
for name in parameters:
    dbutils.widgets.text(name, "DISABLED" if name == "release_mode" else "")
values = {name: dbutils.widgets.get(name).strip() for name in parameters}
try:
    receipt = export_demo_dataset(spark, **values)
except DemoExportError:
    raise
except Exception:
    # Do not surface values from Spark/Arrow exceptions or rejected records.
    raise DemoExportError("demo_provenance_or_replay_unavailable_no_export") from None

print("Private DEMO_ONLY export completed. Nothing was published.")
print("Privacy status retained: " + receipt["privacy_status"])
for item in receipt["files"]:
    print(f"{item['file']}: {item['rows']:,} rows; {item['bytes']:,} bytes")
print("Export directory: " + receipt["location"])
print("Sanitized preview: " + str(receipt["preview"]["bytes"]) + " bytes; at most 15 selected records per table.")
dbutils.notebook.exit(json.dumps({key: receipt[key] for key in
    ("export_id", "release_mode", "dataset_version", "privacy_status", "location", "files", "archive", "preview")}))
