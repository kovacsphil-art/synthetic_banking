# Databricks notebook source
# Read-only preparation of public-safe download metadata. No uploads or publication.
import sys
from pathlib import Path
import json

for repo_dir in (Path.cwd(), Path.cwd().parent, *(Path(path) for path in sys.path if path)):
    src_dir = repo_dir if repo_dir.name == "src" else repo_dir / "src"
    if (src_dir / "synthetic_banking" / "demo_downloads.py").is_file():
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        break
else:
    raise RuntimeError("Keep notebooks/ and src/ together.")

from synthetic_banking.demo_downloads import prepare_download_manifest
from synthetic_banking.demo_export import DemoExportError

for name in ("export_id", "dataset_version"):
    dbutils.widgets.text(name, "")
try:
    result = prepare_download_manifest(spark, dbutils.widgets.get("export_id").strip(), dbutils.widgets.get("dataset_version").strip())
except Exception:
    raise DemoExportError("download_manifest_unavailable_no_publication") from None
print("Verified demo download metadata prepared. Assets remain unpublished.")
dbutils.notebook.exit(json.dumps(result, allow_nan=False))
