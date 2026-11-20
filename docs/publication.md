# Automated showcase publication

The static site is published by `.github/workflows/publish-showcase.yml`. GitHub checks Databricks every 15 minutes (at minutes 7, 22, 37 and 52 UTC) and can also be triggered manually. GitHub schedules can be delayed; this is polling, not an immediate callback. This workflow does not start the banking pipeline or approve proposals.

```text
Databricks generation → privacy screen → GENERATED profile → validation PASS
  → reporting succeeds: run-specific sanitized JSON + private path receipt
  → GitHub Actions verifies completed job and every expected task succeeded
  → download that run's JSON → validate public schema and browser contract
  → commit docs/latest-pipeline.json → upload public assets → GitHub Pages
```

## One-time setup

1. Merge these changes onto the repository's default branch. Deploy the updated Databricks bundle using [the workflow instructions](workflow.md). Its reporting task now receives `{{job.run_id}}` and writes `<report_output_dir>/runs/<job-run-id>/latest-pipeline.json`. The notebook returns a private receipt via `dbutils.notebook.exit`; the receipt is never committed or deployed. Interactive reporting without a job ID retains the original output location.
2. In Databricks, create a service principal and OAuth M2M secret. Assign it to the workspace, give it **CAN VIEW** on this job and the required **USE CATALOG**, **USE SCHEMA**, **READ VOLUME** permissions on the reporting Volume. Use a separate reporting-only Volume so this identity cannot read source or synthetic datasets. The pipeline identity needs writes there. The GitHub runner must be able to reach the workspace's API; private networking needs an appropriately secured runner.
3. Under GitHub **Settings → Secrets and variables → Actions**, add repository secrets `DATABRICKS_HOST` (workspace HTTPS URL), `DATABRICKS_CLIENT_ID` and `DATABRICKS_CLIENT_SECRET`. Add repository variables `DATABRICKS_JOB_ID` (the deployed job's numeric ID) and `REPORT_OUTPUT_DIR` (the same absolute `/Volumes/...` directory as the bundle variable). No GitHub credential is stored in Databricks. Rotate the OAuth secret through GitHub Secrets.
4. Under **Settings → Pages → Build and deployment**, choose **GitHub Actions**. Configure the `github-pages` environment to permit the default branch. Allow the workflow's built-in `GITHUB_TOKEN` to write repository contents. Branch rules must allow its single-file report commits; if policy forbids this, the workflow stops before deploying. No force pushes or protection bypass is implemented.
5. Run the updated Databricks pipeline successfully. A batch waiting for manual review is intentionally failed and cannot publish. Review and repair it using the existing procedure. No new proposal is automatically approved.

GitHub uses its short-lived `GITHUB_TOKEN` for the report commit and Pages OIDC for deployment. No personal GitHub token is needed. The reporting SDK and JSON Schema validator are pinned in the workflow. Credential values are scoped to the retrieval step, never passed in shell arguments, committed, or placed in a Pages artifact.

## Manual trigger

Open **Actions → Publish validated showcase → Run workflow**, choose the default branch, and optionally enter a successful Databricks **job run ID** (not a task ID or profile ID). Blank selects the newest-started successful run for the configured job. This also works after repairing an approval stop. Older validation timestamps cannot roll back the report already in Git. The manual trigger performs publication only; start the Databricks job separately using Jobs & Pipelines or the bundle CLI.

## Publication boundary and failure behavior

- Only the configured job with overall SUCCESS and all eight expected successful tasks qualifies. The downloader reads only the reporting task's receipt, then the exact run-specific Volume file. It never retrieves notebook logs, table rows, CSVs or other files. Older runs without a receipt must rerun reporting via Databricks repair after deploying this change.
- Payloads must pass the closed version-1 JSON Schema (no extra fields), size limit, timestamp validation and the existing browser contract. Fixed warning wording replaces incoming free text. Unknown contract changes stop publication. Only `docs/latest-pipeline.json` is staged for commit.
- The Pages artifact contains exactly `index.html`, `styles.css`, `results.js`, `latest-pipeline.json` and `.nojekyll`. The repository, notebooks, source code, internal reports and documentation examples are never copied into it. Add future public assets explicitly to the copy list after review.
- Failed/cancelled/pending Databricks runs cannot replace a report. A failed JSON build leaves prior reports intact; missing/invalid downloads or failed Git pushes stop deployment. Pages keeps its existing deployment if preparation or deployment fails. If a commit succeeds but Pages deployment fails, rerun the workflow: unchanged reports still deploy, which repairs that partial failure.
- A schedule may republish the same valid report, including reviewed website asset changes on the default branch. Successful runs are selected by start order; the completion timestamp guard refuses a regression (for example after repairing an older run). A specific successful run can be selected manually to resolve this situation. Concurrency serializes publication; competing human pushes cause a safe push failure and require a retry.
- Privacy findings may block row distribution while the aggregate site still publishes. Public integrity PASS is not privacy clearance. No dataset download or row publication is enabled here.

GitHub may disable scheduled workflows in inactive public repositories; re-enable the workflow or trigger it manually. Changes committed with `GITHUB_TOKEN` do not need to trigger another workflow: the same run builds and deploys Pages. Investigate failures in Actions; rejected payloads and SDK exception details are deliberately omitted from logs.

## Checks and operating limits

Run `python -m pip install jsonschema==4.23.0` for local publication tests, then the normal Python suite with the repository root and `src` on `PYTHONPATH`. The new tests use fabricated metadata and the documented example. No live workspace or deployment is needed for them.

This change prepares automation; it does not create secrets, change repository settings, deploy the bundle, push commits or perform a live Pages deployment. Complete the setup above and smoke-test a successful run, a failed validation and a repaired run before enabling unattended use. Retain the per-run Volume artifacts while GitHub needs them; use your normal retention policy afterwards.

References: [GitHub Pages custom workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages), [Databricks OAuth M2M](https://docs.databricks.com/aws/en/dev-tools/auth/oauth-m2m), [Jobs SDK](https://databricks-sdk-py.readthedocs.io/en/stable/workspace/jobs/jobs.html), [Volume Files SDK](https://databricks-sdk-py.readthedocs.io/en/stable/workspace/files/files.html).
