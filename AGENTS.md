# Synthetic banking pipeline

Read [README.md](README.md) for the pipeline and table map, [docs/setup.md](docs/setup.md) for first-time setup, and [docs/workflow.md](docs/workflow.md) for task handoffs and repair. Reusable Python code lives in `src/synthetic_banking/`; notebooks coordinate parameters, reads/writes and important outputs.

## Pipeline and configuration

- One-time fabricated input setup: `notebooks/00_Create_Fabricated_SOURCE.py`. Upload the bundled schema-only `schemas/RCAR_source_column_list.xlsx` to the configured input Volume first. Keep the reviewed `scripts/Scotia Fake Records.py` unchanged; demo replay pins its fingerprint.
- Main job: SOURCE profiling (01) → LLM proposals (02) → approval check (04) → generation (03) → privacy screening (07) → GENERATED profiling (01) → comparison (05) → optional demo verification (10) → sanitized reporting (06).
- Notebooks 08 and 09 support standalone demo export/download preparation. They are not substitutes for main-job lineage or public-release verification.
- Central defaults are in `src/synthetic_banking/config.py`; compute/report destinations are bundle variables. Credentials belong in Databricks/GitHub secret mechanisms, never source files. Keep `notebooks/`, `src/`, `scripts/`, `schemas/` and supporting workflow files together.

## Working on the pipeline

- Use one explicitly pinned, completed SOURCE profile run for every generation input and its proposals. `current_run` and convenience views can point to GENERATED profiles. Preserve exact SOURCE, batch, generation, GENERATED and privacy-assessment IDs across task handoffs; fail on mismatched provenance.
- Keep row-level SOURCE records out of LLM prompts and Git. Use fabricated fixtures for tests; prompts receive aggregate profiles only. Keep notebook outputs clear of records, credentials and environment metadata before committing.
- Use individually reviewed approvals with valid batch/reviewer provenance to select predefined Python implementations. Never execute proposal text as Python, SQL or another language. A fresh batch intentionally stops at `APPROVAL_REQUIRED`; review it and repair from the approval check without reloading SOURCE or creating a new batch.
- Preserve existing behavior when no eligible supported approval applies. SOURCE measurements supply probabilities; keep deterministic formulas, random-seed behavior, structural constraints and regression baselines intact. Audit applied/skipped rules and legacy fallback execution separately from approval status.
- SOURCE mode reloads development tables/aliases under `workspace.default`; generation overwrites all six output tables and audits under `workspace.synthetic_generated`. Only one writer may use those destinations. Use isolated test destinations for Databricks smoke tests; a bundle target name alone does not isolate data.
- Keep integrity validation, statistical fidelity and privacy screening separate. Integrity PASS/COMPLETED is not statistical acceptance or privacy clearance. Do not override REVIEW_REQUIRED or weaken provenance, replay, privacy or release gates.
- Public reporting uses sanitized aggregate JSON. Bounded previews and CSV/ZIP downloads require their separate explicitly authorized, verified fabricated DEMO_ONLY path. Keep full row exports out of Git/Pages assets; approved downloads use versioned Release assets. Website changes must not fabricate results or silently change thresholds.

## Local checks

Use Python 3.10+ (3.12 matches CI), SQLite 3.39+ for SQL-adapter tests, and Node.js 18+ (22 matches CI). `requirements-dev.txt` supplies NumPy, pandas, openpyxl, PyArrow and jsonschema for local checks. Do not install that file over Databricks' managed runtime.

From the repository root in PowerShell, create the local environment once, then run:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -B scripts/check_setup.py
$env:PYTHONPATH = (Resolve-Path -LiteralPath src).Path
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
node --test tests/*.cjs
```

Use `.venv/bin/python` and `export PYTHONPATH="$PWD/src"` on macOS/Linux. Do not silently accept skipped dependency-dependent tests as a complete verification.

The suites cover fabricated setup inputs, profiling, sampling/regression behavior, approval/provenance, rule audits, six-table integrity, temporal constraints, fidelity/privacy, demo export gates, reporting/publication and frontend interactions. Tests use temporary fabricated fixtures and in-memory adapters; they do not authenticate or run the live Databricks workflow.

Run changed-code checks first, then the applicable regression suites. Notebook/Spark execution, Delta/Volume writes, model access, task values and job repair require authenticated Databricks checks in an isolated destination. Report those limits without substituting local tests for a live run.
