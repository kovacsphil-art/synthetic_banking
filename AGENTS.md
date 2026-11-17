# Synthetic banking pipeline

Read [README.md](README.md) for the pipeline and table map. The three Databricks notebooks in `notebooks/` profile data, propose rules, and generate records, in that order. Reusable Python code lives in `src/synthetic_banking/`.

## Working on the pipeline

- Use one completed SOURCE profile run for all generation inputs. Load proposals for that same run. `current_run` and the convenience views can point to GENERATED profiles.
- Keep row-level source records out of LLM prompts, local fixtures, and Git. Use fabricated data for tests.
- Use explicitly reviewed approvals with valid batch provenance to select predefined Python implementations. Keep proposal text for review and audit. Never execute it as Python, SQL, or another language.
- Preserve current generation behavior when there is no eligible supported approval. Record whether a rule was applied, skipped, or supplied by the legacy path when wiring the pilot into the notebook.
- Follow the README execution order for Databricks checks. SOURCE mode reloads development tables in `workspace.default`. Notebook 03 overwrites its output tables in `workspace.synthetic_generated`. Use test destinations for smoke tests.

## Local checks

The rule pilot needs Python 3.10 or newer and NumPy. From the repository root in PowerShell, run:

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath src).Path
python -B -m unittest discover -s tests -v
```

These tests cover Python rule selection and formulas. Run notebook and Delta integration checks in Databricks against a test destination.
