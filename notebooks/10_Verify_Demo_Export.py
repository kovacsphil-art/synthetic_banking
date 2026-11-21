# Databricks notebook source
# MAGIC %md
# MAGIC # Verify the exact validated cohort for optional fabricated demo distribution
# MAGIC DISABLED continues aggregate reporting. DEMO_ONLY must pass all existing
# MAGIC six-table replay, content and provenance checks. Privacy status is unchanged.

# COMMAND ----------
# MAGIC %pip install openpyxl==3.1.5

# COMMAND ----------
import sys
from pathlib import Path
for repo_dir in (Path.cwd(), Path.cwd().parent, *(Path(p) for p in sys.path if p)):
    src_dir = repo_dir if repo_dir.name == 'src' else repo_dir / 'src'
    if (src_dir / 'synthetic_banking' / 'demo_workflow.py').is_file():
        sys.path.insert(0, str(src_dir))
        break
else:
    raise RuntimeError('Keep notebooks/, src/ and scripts/ together.')

from synthetic_banking.demo_workflow import verify_demo_stage, IDS
from synthetic_banking.demo_export import DemoExportError
from synthetic_banking.workflow import publish_values
parameters = (*IDS, 'release_mode', 'report_output_dir', 'workflow_run_id', 'validation_status')
for name in parameters:
    dbutils.widgets.text(name, 'DISABLED' if name == 'release_mode' else '')
try:
    result = verify_demo_stage(spark, **{n: dbutils.widgets.get(n).strip() for n in parameters})
except Exception:
    raise DemoExportError('demo_export_verification_failed_no_publication') from None
publish_values(dbutils, demo_export_status=result['status'], demo_dataset_version=result['dataset_version'])
print('Demo export eligibility: ' + result['status'] + '. Privacy screening is unchanged.')
