"""Regenerate the closed download-manifest schema; no dataset access."""
import json
from pathlib import Path
from synthetic_banking.demo_downloads import download_schema

(Path(__file__).resolve().parents[1]/'docs/reporting/dataset-downloads.schema.json').write_text(
    json.dumps(download_schema(),indent=2)+'\n',encoding='utf-8')
