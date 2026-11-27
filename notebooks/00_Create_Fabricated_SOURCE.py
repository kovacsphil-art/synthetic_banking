# Databricks notebook source
# MAGIC %md
# MAGIC # Create the fabricated development baseline (one-time setup)
# MAGIC Run in a dedicated development Volume before the pipeline. This overwrites
# MAGIC the six RCAR_synthetic_*.parquet files in config.py's SOURCE_DIR. Upload the
# MAGIC schema-only schemas/RCAR_source_column_list.xlsx workbook there first.
# MAGIC The bundled workbook contains field names/types only, not customer records.
# MAGIC This calls the existing reviewed generator with its policy seed/population;
# MAGIC it does not profile data or authorize public distribution. See docs/setup.md.

# COMMAND ----------
# MAGIC %pip install openpyxl==3.1.5

# COMMAND ----------
import sys
from pathlib import Path
for repo_dir in (Path.cwd(), Path.cwd().parent, *(Path(p) for p in sys.path if p)):
    src_dir = repo_dir if repo_dir.name == "src" else repo_dir / "src"
    if (src_dir / "synthetic_banking" / "config.py").is_file():
        sys.path.insert(0, str(src_dir))
        break
else:
    raise RuntimeError("Keep notebooks/, src/ and scripts/ together in the project.")

# COMMAND ----------
import hashlib
import importlib.util
from synthetic_banking.config import SOURCE_DIR
from synthetic_banking.demo_export import load_policy

policy = load_policy()
script = src_dir.parent / "scripts" / "Scotia Fake Records.py"
workbook = Path(SOURCE_DIR) / "RCAR_source_column_list.xlsx"
if not workbook.is_file():
    raise FileNotFoundError("Upload RCAR_source_column_list.xlsx to config.py's SOURCE_DIR before creating fabricated inputs.")
if hashlib.sha256(script.read_text(encoding="utf-8").replace("\r\n", "\n").encode()).hexdigest() != policy["generator_sha256"]:
    raise RuntimeError("Restore the reviewed fake-record script; its fingerprint does not match demo policy.")

# Import only this fixed reviewed repository file; never model-proposed code.
spec = importlib.util.spec_from_file_location("sage_reviewed_fake_records", script)
fake_records = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fake_records)
tables = fake_records.generate_fake_banking_data(
    n_people=policy["source_people"], schema_path=str(workbook), seed=policy["source_seed"],
)
fake_records.validate_relationships(tables)
saved_paths = fake_records.save_tables_to_volume(tables, output_dir=SOURCE_DIR)
for name, frame in tables.items():
    print(f"{name}: {len(frame):,} fabricated rows; {len(frame.columns)} columns")
print("Six fabricated Parquet inputs saved. Run the pipeline's SOURCE profiling next.")
