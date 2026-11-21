"""Regenerate the static preview catalog and closed schema; never reads data."""
import json
from pathlib import Path
from synthetic_banking.demo_preview import config, preview_schema

root = Path(__file__).resolve().parents[1] / "docs"
(root / "records-config.js").write_text(
    "/* Generated from demo_preview.py; no runtime or row data. */\n(() => { const config = " +
    json.dumps(config(), indent=2, ensure_ascii=False) +
    "; if(typeof module!==\"undefined\"&&module.exports)module.exports=config; else window.SageRecordsConfig=config; })();\n",
    encoding="utf-8")
(root / "reporting/demo-preview.schema.json").write_text(json.dumps(preview_schema(), indent=2)+"\n", encoding="utf-8")
