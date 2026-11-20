# Databricks notebook source
# Stop before generation until every proposal has an explicit review decision.
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
from synthetic_banking.workflow import check_approvals, enforce_approval, publish_values

dbutils.widgets.text("source_run_id", "")
dbutils.widgets.text("batch_id", "")
source_run_id = dbutils.widgets.get("source_run_id").strip()
batch_id = dbutils.widgets.get("batch_id").strip()
decision = check_approvals(spark, source_run_id, batch_id)
publish_values(dbutils, source_run_id=source_run_id, batch_id=batch_id,
               approval_status=decision.status, approval_fingerprint=decision.fingerprint,
               proposed_rules=decision.proposed, approved_rules=decision.approved,
               pending_rules=decision.pending)
print(f"{decision.status}: {decision.proposed} proposed; {decision.approved} reviewed approvals; {decision.pending} pending.")
enforce_approval(decision)
