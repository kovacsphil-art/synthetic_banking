# Databricks controlled pipeline

The bundle defines one serial job. It calls the existing notebooks; `workflow.py` supplies only handoff and provenance checks. Profiling, prompts, distributions, formulas and the controlled rule registry retain their existing behavior. No task approves a rule or executes proposal text.

```text
source_profile (01, SOURCE)
  → llm_proposal (02)
  → approval_check (04) ── PENDING → APPROVAL_REQUIRED: stop, review, repair
  → synthetic_generation (03)
  → privacy_check (07; row-release decision)
  → generated_profile (01, GENERATED)
  → validate (05)
  → demo_export_verification (10; opt-in DEMO_ONLY or DISABLED)
  → reporting (06, aggregate JSON + optional public demo reference)
```

## Tasks and handoffs

| Task | Existing logic used | Outputs passed as job task values |
| --- | --- | --- |
| `source_profile` | Notebook 01; profiling lifecycle, marginal/dependency/relationship/fidelity evidence modules | Exact completed `source_run_id` |
| `llm_proposal` | Notebook 02; `proposals.py`; aggregate metadata for that SOURCE only | Same `source_run_id`, exact `batch_id` |
| `approval_check` | Notebook 04; `workflow.check_approvals`, existing `rules.load_rule_proposals` | IDs, review counts/status, SHA-256 approval fingerprint |
| `synthetic_generation` | Notebook 03; `profiles.py`, `generation.py`, `rules.py`, `storage.py`, existing validation | Same SOURCE/batch, validated `generation_id` |
| `privacy_check` | Notebook 07; `privacy.py`, `privacy_checks.py`, SOURCE snapshots and validated Delta versions | SOURCE/batch/generation, `privacy_assessment_id`, `privacy_status`, technical `row_level_release_allowed` |
| `generated_profile` | Notebook 01 in GENERATED mode; same profiler modules | Same SOURCE/batch/generation, completed `generated_run_id` |
| `validate` | Notebook 05; saved Delta-version checks and `fidelity.create_fidelity_report` | All four exact IDs, `validation_status=PASS`, UTC `validated_at` |
| `demo_export_verification` | Notebook 10; existing demo exporter and download verification modules | Eligibility status and opaque dataset version; private readiness receipt binds all five IDs and artifact hashes |
| `reporting` | Notebook 06; `reporting.py`; numeric `workflow_run_id={{job.run_id}}` | Per-execution public report path, schema version, `pipeline_status=COMPLETED`; notebook-exit receipt for GitHub |

The YAML uses `{{tasks.<task>.values.<key>}}` to pass outputs as notebook parameters. Missing/unresolved IDs fail instead of defaulting to a latest run. [Databricks task-value documentation](https://docs.databricks.com/aws/en/jobs/task-values)

Every batch must identify the selected completed SOURCE run, have saved model/prompt provenance and a valid stored response, and have its complete set of proposal rows. Reviewed decisions need a reviewer/time and nonlegacy provenance. Generation rechecks the full batch/proposal/review fingerprint before sampling and again before writes. A changed decision or proposal requires rerunning the approval check.

Workflow `proposal_batch_id` scopes proposals and generation-state metadata to one batch. This is separate from the interactive `pilot_batch_id`/`pilot_proposal_ids` controls; their existing stricter one-to-three-rule behavior remains available. Unsupported approved proposals are handled by the existing registry: logged and skipped. Approval never guarantees implementation or application. No statistical formulas are introduced by the workflow.

GENERATED profiling verifies the expected generation, batch and SOURCE before starting. The final validation checks the completed GENERATED run's saved `profile_run_lineage`, saved generation versions and generated integrity statuses. Fidelity differences remain individual observations; no new fidelity threshold or overall score is introduced. `current_run` is still maintained for interactive convenience but is not a workflow handoff or generation baseline.

## Privacy and aggregate-only results

After generation, `privacy_check` records aggregate overlap/copying/rarity/similarity checks separately from fidelity. Its risk status can be BLOCKED or REVIEW_REQUIRED while the task completes normally; GENERATED profiling, fidelity validation and the sanitized showcase report still run. This does not authorize row-level sharing. Any future row exporter must require the exact current passing assessment via `require_row_level_release`, then bind its files to those checked Delta versions. The legacy unbound-CSV ZIP helper is disabled. See [the privacy runbook](privacy.md) for defaults, limitations, SOURCE snapshot capture and required deployment checks.

Notebook 01 captures SOURCE snapshot metadata before creating profiling input views and verifies it before SOURCE completion. Reused older SOURCE runs without verified snapshots remain usable for aggregate generation/fidelity, but row-level release stays blocked. Missing or unsupported privacy comparisons never become a pass.

## Approval stop and resume

A fresh proposal batch normally contains PENDING proposals. The gate publishes `approval_status=APPROVAL_REQUIRED`, the SOURCE/batch IDs and counts, then raises the named `ApprovalRequired` exception. **Databricks displays the gate/run as Failed intentionally**, and downstream tasks do not run. This is a manual-review stop, not a successful completed dataset. Configured task retries are zero; the live serverless pilot nevertheless included platform-managed additional attempts. Inspect Jobs attempt/repair history and use the successful task's exact batch handoff. A retry can create a new proposal batch; it never approves proposals.

1. Open `llm_proposal`/`approval_check` task output and record the SOURCE and batch IDs.
2. Inspect the saved proposals and evidence. Use Notebook 02's individual review SQL template to record APPROVED or REJECTED with reviewer/time. Review **all** PENDING proposals in this batch; rejecting an unsuitable proposal is a valid decision. Do not rerun Notebook 02 from the top just to review, because that creates a new batch.
3. In the original job run, choose **Repair run**, rerun `approval_check` and its downstream tasks. Leave the successful SOURCE and LLM tasks out of the repair. Their original task values keep the exact IDs. [Databricks repair-run documentation](https://docs.databricks.com/aws/en/jobs/repair-job-failures)

Previously reviewed batches can run without a new review stop: start with **both** job parameters `reuse_source_run_id` and `reuse_batch_id`. SOURCE and LLM tasks validate those exact objects and return without reloading SOURCE or calling the model. Never reuse a batch against a different/new SOURCE run. A partially supplied pair, legacy blanket approval, malformed metadata, or provenance mismatch fails early.

## Deploy and start

1. Install/authenticate the current Databricks CLI for the intended workspace. Use a **test destination** first. Configure `config.py` and source paths; the existing SOURCE staging tables and generated tables are overwritten by their respective notebooks. Keep `notebooks/` and `src/` together.
2. Select an existing Unity Catalog-compatible cluster with NumPy/pandas/Spark and `ai_query()` access. The job's run-as identity needs source Volume reads, output Volume writes, schema/table/view permissions, and permission to use the cluster/model endpoint.
3. From the repository root, set bundle variables and deploy:

```powershell
$env:BUNDLE_VAR_cluster_id = "YOUR_CLUSTER_ID"
$env:BUNDLE_VAR_report_output_dir = "/Volumes/workspace/default/scotia/pipeline_reporting"
databricks bundle validate -t dev
databricks bundle deploy -t dev
databricks bundle run -t dev synthetic_pipeline
```

The bundle has no schedule. Alternatively open **Jobs & Pipelines → synthetic-banking-controlled-pipeline → Run now** after deployment. `rule_scope` defaults to `BALANCE_PILOT`; supported alternatives are `DELINQUENCY_PILOT` and `ACCOUNT_CORE`. Change those through **Run now with different parameters**. To reuse reviewed objects, supply the paired reuse parameters there as well.

### Databricks Free Edition

Use the `free` target for serverless compute. It keeps the nine-task graph and exact ID handoffs and removes existing-cluster selection; the `dev` target retains its existing cluster configuration. With an authenticated CLI profile, set only the reporting directory:

```powershell
$env:BUNDLE_VAR_report_output_dir = "/Volumes/workspace/default/showcase_reports/pipeline_reporting"
databricks bundle validate -t free -p synthetic-banking
databricks bundle deploy -t free -p synthetic-banking
databricks bundle run -t free -p synthetic-banking synthetic_pipeline
```

The example assumes the dedicated `workspace.default.showcase_reports` managed Volume exists. Create it and grant the required reporting permissions before running. `synthetic-banking` is the local CLI authentication profile name. Free Edition quotas and serverless limitations still apply; deployment validation alone does not prove the notebooks have executed successfully.

Job parameters intentionally avoid the handoff keys `source_run_id`, `batch_id`, `generation_id` and `generated_run_id`: Databricks job parameters can override same-named task parameters. Do not add competing job parameters for these IDs. [Job parameter precedence](https://docs.databricks.com/aws/en/jobs/job-parameters)

Run only one writer against these shared staging/generated schemas, including interactive notebook runs and other jobs. `max_concurrent_runs=1` protects this job, not unrelated writers. Version/identity guards stop later stages if another generation replaces the batch. Repair does not make non-idempotent tasks transactional; after a generation failure, inspect its state and rerun generation plus dependents rather than pretending partial outputs completed.

Workflow mode skips Notebook 01's HTML export and defers its automatic fidelity-report write to `validate`; the profiler still records all existing aggregate evidence. Interactive mode defaults to OFF and keeps its existing comparison/showcase behavior. The workflow leaves website source untouched. The static site can read a separately published sanitized report; see [the webpage JSON contract](results-data.md).

## Remaining manual work

The final `reporting` task also receives `privacy_assessment_id` directly from `privacy_check`. The identifier is private; reporting checks that assessment against the exact SOURCE/generation and saved snapshots, then exports only allowlisted aggregates. A privacy REVIEW_REQUIRED does not stop aggregate reporting or open row release. After deploying reporting changes, repair **only reporting** in a still-current successful run to refresh public fields without regenerating data. This was verified on the completed pilot; all eight task outcomes remained successful. Do not rerun SOURCE/LLM tasks merely to refresh presentation. See the [post-pilot review](post-pilot-review.md).

- Configure/authenticate the workspace, compute, permissions and input/output paths; deploy the bundle.
- Review proposals individually and repair the approval gate, or explicitly select a previously reviewed SOURCE/batch pair.
- Investigate validation failures and material statistical deviations; acceptance thresholds remain a human decision.
- Review privacy findings before planning any row-level sharing. Screening PASS is not certification or distribution approval; there is no enabled dataset download task.
- Configure the [GitHub publication workflow](publication.md) once to retrieve successful reports and deploy Pages automatically. Manual report downloads remain available; see [the reporting contract](reporting/README.md).

Local tests cover handoff/provenance/review behavior using fabricated metadata. The first pilot verified live bundle deployment, approval repair, Spark/Delta generation/profiling/validation and reporting-only repair. New configurations still need a Databricks test-destination smoke test; historical success is not evidence that a changed environment will pass.

## Optional automated demo distribution

The new verification task follows `validate` and precedes `reporting`. Default `demo_release_mode=DISABLED` permits ordinary aggregate-only execution. Explicit DEMO_ONLY runs the existing complete fabricated SOURCE/generated replay and content checks; it never uses catalog paths as origin evidence or overrides privacy status. GitHub separately requires `SAGE_PUBLISH_DEMO_DATASETS=true` for public Release uploads. See [the complete trigger, handoff, repair and disable runbook](automated-demo-publication.md). Existing eight-task live results above are historical evidence, not evidence that the new task has run.
