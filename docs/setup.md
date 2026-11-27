# First-time setup

SAGE is a Databricks prototype that measures a **fabricated development population**, proposes dependencies for human review, generates six linked tables, and compares them with the same SOURCE baseline. AI sees aggregate metadata; reviewed proposals select predefined Python implementations. Model text is never executed.

**Stakeholders:** start with the [showcase](https://kovacsphil-art.github.io/synthetic_banking/) and [Validation Report](https://kovacsphil-art.github.io/synthetic_banking/validation.html). No local installation, Git connection or Databricks account is needed to view the published site. Its measured fidelity, integrity and privacy status are distinct. Potential business applications are illustrative, not validated deployments.

**Developers:** follow steps 1–6 below. Use a dedicated development workspace/catalog first. SOURCE profiling overwrites staging tables and aliases; generation overwrites the six output tables. Only one writer may use those destinations at a time. A bundle target name does not isolate data destinations.

## 1. Prerequisites and configuration

Keep the complete project together: `notebooks/`, `src/`, `scripts/`, `schemas/`, `docs/`, `resources/` and `databricks.yml`. Git is optional for interactive notebooks; upload the same folder structure if needed. The bundle deploys workspace files and notebook/module discovery finds the sibling `src/` directory; no Python package build is required.

| Where | Required |
| --- | --- |
| Databricks | Unity Catalog, managed Delta storage, writable Volumes, Python/Spark SQL compute; serverless for target `free`, existing UC-compatible cluster for `dev` |
| Notebook libraries | Spark/`dbutils`, NumPy, pandas and PyArrow from the Databricks runtime. Setup/demo notebooks install `openpyxl==3.1.5`; compute must permit that install. Notebook 02 needs `ai_query()` and the configured model endpoint. |
| Local development | Python 3.10+ (3.12 matches publication CI), SQLite 3.39+ for all SQL-adapter tests, Node.js 18+ (22 matches CI), `requirements-dev.txt` |
| Deployment only | Current Databricks CLI with bundle support and workspace authentication. Python's legacy `databricks-cli` package is not the bundle CLI. |
| GitHub publisher | Actions installs `databricks-sdk==0.72.0`, `jsonschema==4.23.0` and Node 22 itself; these transport credentials/libraries are not needed by interactive notebooks. |
| Fabricated inputs | Bundled **schema-only** [RCAR_source_column_list.xlsx](../schemas/RCAR_source_column_list.xlsx), reconstructed from the reviewed demo policy. Upload it to the input Volume. Its six table sheets have the exact `Source Column` / `Data type` headings expected by the unchanged fake-record script. Do not add customer records or extra sheets. |

Configure once, before starting fresh notebook sessions:

| Setting | Authoritative location / current default |
| --- | --- |
| Catalog, staging/profile/generated schemas, SOURCE aliases | `src/synthetic_banking/config.py`: `workspace`, `workspace.default`, `workspace.synthetic_profile`, `workspace.synthetic_generated`; bronze view schemas listed below |
| Input Volume directory | `config.py`: `SOURCE_DIR=/Volumes/workspace/default/scotia`; workbook and all six inputs live here. Notebook 01's `source_dir` is a **Python variable**, not a widget. Use the shared default for automated/demo runs. |
| Model, generated population, seed | `config.py`: `system.ai.gpt-oss-20b`, 10,000 customers, seed 42 |
| Fabricated baseline population/seed | Reviewed `src/synthetic_banking/demo_export_policy.json`: 1,000 people, seed 42. Separate from generated population settings. Do not edit policy/hash to bypass failed provenance. |
| Compute/report directory | Bundle variables `cluster_id` and `report_output_dir`, set through `BUNDLE_VAR_*` environment variables or an ignored `.databricks/bundle/<target>/variable-overrides.json`. No credentials here. |
| Per-execution choices | Jobs parameters `rule_scope`, `reuse_source_run_id`, `reuse_batch_id`, `demo_release_mode`; downstream lineage IDs are task values, not user-supplied job parameters. |
| GitHub publication | Actions Secrets / Variables in step 6; `REPORT_OUTPUT_DIR` must exactly match the deployed bundle's reporting directory. |

Changing `CATALOG` alone does not rewrite `SOURCE_DIR`. Check both. `SOURCE_ALIASES` use schema/table names relative to that catalog. Admins must provision a new catalog and staging schema/Volumes; notebooks create their profiling/generated schemas, tables and views. Keep the reviewed fake-record script unchanged: the new setup notebook passes the centralized path to its existing functions. Demo replay also expects the workbook in `SOURCE_DIR`.

### Databricks permissions

Ask an administrator to scope these to development objects, for the **job run-as identity** as well as any interactive user. Workspace/compute permissions and Unity Catalog privileges are separate.

| Principal / activity | Required access |
| --- | --- |
| Pipeline runner | Workspace project access; permission to run the job and attach to chosen compute/use serverless; model endpoint query access (typically CAN QUERY; for applicable UC models, USE CATALOG/USE SCHEMA and EXECUTE). Confirm regional/model availability. |
| Catalog and schemas | USE CATALOG; CREATE SCHEMA if notebooks create schemas; USE SCHEMA and CREATE TABLE in staging, `synthetic_profile`, `synthetic_generated`, `bronze_cis_mdm`, `bronze_tsys`, `bronze_transunion`. CREATE TABLE also covers creating ordinary views. SELECT on inputs; MODIFY on writable tables; ownership or appropriate replacement rights on existing tables/views. Do not point aliases at production objects. |
| Input/private export Volume | USE CATALOG, USE SCHEMA, READ VOLUME; WRITE VOLUME for setup's six Parquet files and optional private demo exports. Admin creates the Volume with CREATE VOLUME first. |
| Separate reporting Volume | Pipeline: READ VOLUME and WRITE VOLUME plus catalog/schema usage. Provision it **before** running the job; `report_output_dir` does not create a Volume. |
| Human reviewer | SQL compute access, SELECT on the proposal/batch/evidence tables and MODIFY for individual decisions. Job CAN MANAGE RUN is needed to repair a run. |
| GitHub publisher identity | Separate workspace service principal with OAuth M2M, CAN VIEW on this one job, and USE CATALOG / USE SCHEMA / READ VOLUME only on its reporting Volume. No SOURCE/generated-table access. |

Grant details depend on ownership and workspace policy: [Unity Catalog privileges](https://docs.databricks.com/aws/en/data-governance/unity-catalog/access-control/privileges-reference). Do not use broad administrative grants as a substitute for configuring the run-as identity. With demo distribution enabled, the reporting Volume also holds independently verified fabricated CSV/ZIP copies; review its readers before enabling that branch.

## 2. Establish the fabricated SOURCE baseline

For the default configuration, an authorized administrator can provision the two managed Volumes in the existing development catalog/schema:

```sql
CREATE VOLUME IF NOT EXISTS workspace.default.scotia;
CREATE VOLUME IF NOT EXISTS workspace.default.showcase_reports;
```

Use your configured catalog/schema instead when different, and grant the scoped permissions above. These commands provision storage; they neither upload a workbook nor establish fabricated provenance.

1. Provision the development input Volume and upload the bundled [schemas/RCAR_source_column_list.xlsx](../schemas/RCAR_source_column_list.xlsx) to `SOURCE_DIR/RCAR_source_column_list.xlsx` (default `/Volumes/workspace/default/scotia/RCAR_source_column_list.xlsx`). It contains 219 field-name/type pairs across six sheets, with no customer records. The generated-only `_UTILIZATION_RATE` helper is omitted. See [schema provenance and format](../schemas/README.md). This supplies the development schema; existing SOURCE runs still require the unchanged exact-replay checks.
2. Open **`notebooks/00_Create_Fabricated_SOURCE.py` in Databricks** and run from the top. It calls the unchanged `scripts/Scotia Fake Records.py` with the policy's population/seed and config's directory, validates its links, and writes six Parquet files. It reports counts only. This replaces same-named files; keep the Volume dedicated to this baseline.
3. Confirm these files exist (Notebook 01 also fails early if any is missing):

```text
RCAR_synthetic_PERSON.parquet
RCAR_synthetic_CUSTOMER_ACCOUNT_REL.parquet
RCAR_synthetic_CUSTOMER_RELATIONSHIP.parquet
RCAR_synthetic_TKQ_ACCOUNT.parquet
RCAR_synthetic_TKQ_ACCOUNT_BALANCE.parquet
RCAR_synthetic_TRADELINES.parquet
```

These are the **initial fake development records**, not the new 10,000-customer cohort. No completed SOURCE profile exists until Notebook 01 runs. The automated job's first task runs it as SOURCE; do not create a separate baseline profile merely to start a fresh job. For interactive execution, run Notebook 01 with `profile_type=SOURCE` and confirm `profile_runs.status=COMPLETED` before Notebooks 02/03.

Label/path alone never proves fabricated origin. Optional demo export later requires exact six-table replay of the pinned script, workbook/schema, seed and population, plus replay of the generated cohort. Retain SOURCE tables and Delta history until privacy/export checks finish; do not reload or VACUUM them during the run.

## 3. Deploy and start the automated pipeline

From the repository root, authenticate using your own workspace URL (no token in source):

```powershell
databricks auth login --host https://YOUR-WORKSPACE.cloud.databricks.com --profile sage-dev
$env:BUNDLE_VAR_report_output_dir = "/Volumes/workspace/default/showcase_reports/pipeline_reporting"
databricks bundle validate -t free -p sage-dev
databricks bundle deploy -t free -p sage-dev
databricks bundle run -t free -p sage-dev synthetic_pipeline
```

`sage-dev` is an arbitrary local authentication profile name. For classic compute, set `$env:BUNDLE_VAR_cluster_id="YOUR_CLUSTER_ID"` and use **`-t dev`** on all three bundle commands. The separate private export job uses serverless even in the dev bundle. Validate/deploy do not prove compute, permissions, data or model calls will work. [CLI OAuth login](https://docs.databricks.com/aws/en/dev-tools/auth/oauth-u2m).

After deployment, **Jobs & Pipelines → synthetic-banking-controlled-pipeline → Run now with different parameters** is the simplest way to choose:

| Parameter | First-run choice |
| --- | --- |
| `rule_scope` | `BALANCE_PILOT` (default); `ACCOUNT_CORE` for the existing categorical/numeric candidates; `DELINQUENCY_PILOT` for measured utilization/outcome rates |
| `reuse_source_run_id`, `reuse_batch_id` | Leave both blank for fresh SOURCE/proposals. Later provide both exact reviewed IDs together to reuse them without SOURCE reload/model call. |
| `demo_release_mode` | `DISABLED` initially; only explicitly authorized fabricated exports use `DEMO_ONLY`. |

```text
01 SOURCE → 02 proposals → 04 approval check → 03 generation → 07 privacy
 → 01 GENERATED → 05 validation → 10 optional demo verification → 06 public report
```

The existing nine tasks pass one exact SOURCE ID, batch ID, generation ID, GENERATED profile ID and privacy assessment ID. Never add competing job parameters for those handoffs or substitute `current_run`. Only one writer may touch these schemas, including interactive sessions and the separate demo job. See the [task/identifier map](workflow.md#tasks-and-handoffs).

## 4. Review proposals and resume

A fresh run normally **fails intentionally** at `approval_check` with `APPROVAL_REQUIRED`; downstream tasks remain stopped.

1. Get the SOURCE and batch IDs from the successful `llm_proposal` task output. Inspect only that batch's saved proposals and aggregate evidence.
2. Use Notebook 02's **Review one proposal** SQL template in the Databricks SQL editor. Bind the exact SOURCE, batch and proposal IDs; choose APPROVED or REJECTED. The template records `current_user()` and review time. Decide each PENDING proposal individually, including any SME review; there is no blanket approval command.
3. In the **same job run**, choose **Repair run** from `approval_check` through downstream tasks. Do not rerun successful SOURCE/LLM tasks: that can reload tables or create another batch.
4. Read `rule_execution_log` afterwards: approval, known implementation and actual application are distinct. Unsupported approved proposals are logged/skipped; existing legacy behavior is audited separately. No proposal text runs as Python or SQL.

If review metadata changes, rerun the approval check to refresh its fingerprint before generation. [Detailed review/repair instructions](workflow.md#approval-stop-and-resume) and [interactive pilot](controlled-pilot.md).

## 5. Find outputs and judge the result

Defaults below follow `config.py`; query the exact IDs from the job, not the convenience views.

| Output | Location / meaning |
| --- | --- |
| SOURCE staging and aliases | `workspace.default` six logical tables; `workspace.bronze_cis_mdm`, `workspace.bronze_tsys`, `workspace.bronze_transunion` views |
| Profiles / lineage | `workspace.synthetic_profile.profile_runs`, `profile_run_lineage`, run-keyed marginal/dependency/cardinality/integrity profiles; SOURCE history retained after GENERATED |
| LLM proposals / review | `workspace.synthetic_profile.ai_rule_batches`, `ai_rule_proposals`; aggregate prompt provenance and manual decisions |
| Generated tables | All six in `workspace.synthetic_generated`: PERSON, CUSTOMER_ACCOUNT_REL, CUSTOMER_RELATIONSHIP, TKQ_ACCOUNT, TKQ_ACCOUNT_BALANCE, TRADELINES |
| Generation state / audits | Same generated schema: `generation_state`, `rule_execution_log`, `customer_relationship_generation_log`. COMPLETED requires validated saved Delta versions. |
| Statistical comparison | `workspace.synthetic_profile.fidelity_metrics`, keyed by SOURCE/GENERATED/generation; `validate` task displays metrics, including unavailable comparisons |
| Privacy | `workspace.synthetic_profile.privacy_source_snapshots`, `privacy_assessments`, `privacy_metrics`; aggregate findings, separate from fidelity |
| Public report | `<report_output_dir>/runs/<job-run-id>/latest-pipeline.json`; exact path/hash receipt in reporting task output. Only sanitized contract fields may reach the site. |
| Private demo export (opt-in) | `SOURCE_DIR/demo_dataset_exports/<version>/`, with CSVs/ZIP/dictionary/metadata/preview and final `_SUCCESS`; audit in `synthetic_profile.demo_dataset_exports` |

Validation PASS means configured integrity checks passed, **not** a statistical acceptance score or privacy clearance. Review numeric/tail, categorical, date, missingness, correlation and conditional discrepancies individually. REVIEW_REQUIRED remains a privacy review outcome; no setup step converts it to PASS.

## 6. Optional demo distribution and GitHub Pages

First get an aggregate-only run working. For demo export, explicitly authorize the fabricated release and run with `demo_release_mode=DEMO_ONLY`. Notebook 10 reuses existing export/verification modules for the **exact validated cohort**, verifies full SOURCE/generated replay and content checks, then stages a checksum-bound package for reporting. Missing/uncertain provenance stops export. General privacy findings remain unchanged.

Configure a new repository once:

| GitHub setting | Value / purpose |
| --- | --- |
| Actions Secrets | `DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET` for the restricted reporting identity; never commit values |
| Actions Variables | `DATABRICKS_JOB_ID` (deployed main job, not run/task ID); `REPORT_OUTPUT_DIR` (same directory as bundle) |
| Dataset publication switch | Leave `SAGE_PUBLISH_DEMO_DATASETS` unset/false for aggregates. Explicit `true` permits only verified DEMO_ONLY Release assets. |
| Pages | Source **GitHub Actions**; `github-pages` environment allows the default branch; workflow policy permits contents:write, pages:write and id-token:write. Branch rules must permit the metadata commit. |

**Actions → Publish validated showcase → Run workflow** publishes manually; blank run ID selects the latest eligible successful validation. Scheduled polling also runs every 15 minutes and may be delayed. It does not start Databricks or approve rules. Only successful pipeline/reporting executions qualify; invalid reports or failed deployments retain the previous site.

Pages receives static assets and one sanitized report; optional preview/manifest must match that same generation. Complete six-table CSVs/ZIP/dictionary use versioned GitHub Release assets, never large files committed to `docs/`. No HTML edits are needed for new metrics. To disable dataset publication without disabling SAGE, keep `demo_release_mode=DISABLED` and `SAGE_PUBLISH_DEMO_DATASETS=false`; this does not revoke historical Releases. See [publication setup](publication.md#one-time-setup) and [demo gates/failure recovery](automated-demo-publication.md).

## Local verification without Databricks

From a fresh checkout in PowerShell (no activation or PowerShell execution-policy change needed):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -B scripts/check_setup.py
$env:PYTHONPATH = (Resolve-Path -LiteralPath src).Path
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
node --test tests/test_results.cjs tests/test_validation_page.cjs tests/test_validation_explorer.cjs tests/test_executive_showcase.cjs tests/test_records.cjs tests/test_downloads.cjs tests/test_demo_release.cjs
```

On macOS/Linux use `.venv/bin/python` and `export PYTHONPATH="$PWD/src"`. Requirements describe the local test environment, not Databricks runtime upgrades; Spark/Java/Databricks Connect and a local model are unnecessary. The checker verifies dependencies, complete folder layout, notebook imports/syntax and the reviewed generator fingerprint. It reads no credentials, makes no network calls and does not certify fabricated dataset origin. Tests use fabricated fixtures and in-memory SQL adapters.

To preview the dynamic website locally, serve **only docs/**: `.\.venv\Scripts\python.exe -m http.server 8000 --bind 127.0.0.1 --directory docs`, then open `http://127.0.0.1:8000/`. A `file://` page can block JSON fetches. Missing results stay unavailable; examples are never live measurements.

## Troubleshooting

| Symptom | Check / remedy |
| --- | --- |
| Python opens Store / command missing | Install Python, reopen shell, or use `py -3.12 -m venv .venv`. Use the venv's explicit interpreter. |
| Missing numpy/pandas/jsonschema, skipped tests | Install `requirements-dev.txt` into that interpreter; run `pip check` and setup check. Node is separate. Do not install a local pyspark package to imitate Databricks. |
| `Keep notebooks/, src/ ... together` / ModuleNotFoundError | Upload/deploy the complete project, not isolated notebooks. Start from top after module/config edits; restart Python to clear cached imports. |
| SOURCE preflight missing files / cannot list directory | Check config's SOURCE_DIR, six exact filenames and run-as READ VOLUME. Create/upload fabricated inputs first; never substitute generated tables as SOURCE. |
| Workbook missing / sheet or column KeyError | Upload the bundled `schemas/RCAR_source_column_list.xlsx` to `SOURCE_DIR`; retain its six logical table sheets and `Source Column` / `Data type` headings. The local Git path is not the Databricks Volume path. |
| Permission denied / schema not found / replacement denied | Check job run-as identity, catalog managed storage, precreated staging schema/Volumes, USE privileges and object ownership. A CLI deployment grant does not grant data access. |
| `ai_query` unavailable / endpoint permission error | Check chosen compute, regional availability, MODEL_ENDPOINT and query/EXECUTE access with admin. Do not put row records in prompts as a workaround. |
| Bundle requires cluster_id | Use `-t free` for serverless or configure `BUNDLE_VAR_cluster_id` with `-t dev`. Never print authentication config. |
| `APPROVAL_REQUIRED` | Expected manual gate. Review all PENDING rows in the same batch, then repair approval check and descendants, not SOURCE/LLM. |
| Fingerprint/provenance mismatch | Confirm exact SOURCE/batch and review metadata; rerun approval check after review changes. Never edit IDs/hash/statuses to force a match. |
| No completed generation / changed Delta versions | Inspect generation validation errors. Rerun generation plus descendants with pinned lineage; prevent concurrent writers. Missing columns filled with nulls do not establish validity. |
| Demo replay fails / unsupported schema | Ensure unchanged pinned generator, approved workbook/population/seed and retained SOURCE snapshots. Demo gates are intentionally strict; do not relax policy to publish. |
| Privacy REVIEW_REQUIRED / BLOCKED | Inspect aggregate privacy metrics and limitations in [privacy.md](privacy.md). Aggregate reporting may continue; ordinary row release remains blocked. Demo eligibility is separate. |
| Pages pending/stale / download buttons disabled | Check Actions success, OAuth expiry, job ID/report directory, same-cohort receipt and separately enabled demo gates. Trigger manually after a successful report; `git push` alone is not a deployment. |

## Authenticated acceptance checklist

Local tests cannot establish these. In a dedicated Databricks test destination, verify: workbook/input creation; SOURCE completion with saved snapshots; actual model response/proposal storage; individual review and repair; same-ID handoffs; six Delta writes and audits; GENERATED completion; integrity/fidelity/privacy outputs; reporting Volume receipt; optional replay/ZIP/preview verification; and Pages retrieval/deployment with repository secrets. Confirm a rejected/incomplete run cannot replace the last public report. Do not start a smoke test against shared live output tables.

**Setup verification — November 21, 2026:** a fresh isolated Windows Python 3.12.14 environment installed the local requirements (NumPy 2.5.5, pandas 3.1.1, PyArrow 26.0.1, openpyxl 3.1.5, jsonschema 4.23.0). `pip check`, the setup checker, all 264 Python tests and 87 frontend tests passed with no skipped tests. A temporary schema-only fabricated workbook exercised the new setup wrapper and all six Parquet outputs, including link validation; temporary records were removed. Read-only bundle validation of target `free` also passed using existing authentication. No job was deployed/run and no live table or publication was changed during this setup review. A new installation still needs the authenticated acceptance checklist above.

**Bundled schema verification — November 27, 2026:** the supplied six-sheet workbook matches all 219 reviewed SOURCE field definitions and contains no formulas, macros or external links. The existing setup wrapper used that shipped workbook to create all six temporary fabricated Parquet inputs and validate their relationships. The setup checker, 273 Python tests and 101 frontend tests passed. This removes the separate workbook handoff; live Databricks/Volume execution was not rerun, and existing pinned generations still require exact replay.
