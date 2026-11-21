# SAGE Synthetic Data Generation

## Project Overview

This repository contains a Databricks-based prototype for profiling banking-style relational data and using those profiles to generate statistically similar synthetic records.

The orchestrated workflow keeps one SOURCE baseline through generation, validation and reporting:

```text
01 SOURCE profile → 02 LLM proposal batch → 04 Manual approval check
  → 03 Synthetic generation → 07 Privacy screening
  → 01 GENERATED profile → 05 SOURCE-vs-GENERATED validation
  → 10 Demo export verification (opt-in; otherwise DISABLED)
  → 06 Sanitized reporting JSON → optional verified GitHub Release → Static GitHub Pages site
```

Notebook 03 uses the selected SOURCE statistics and predefined Python implementations. Reviewed proposals can select two balance formulas, utilization-conditioned delinquency, two account-product categorical dependencies and credit-limit/balance rank coupling. Generation retains the previous path when a target has no unique eligible, sufficiently evidenced approval. See [phase-one methods and results](docs/statistical-fidelity-phase1.md) and [local checks](#local-checks).

**View the published project:** [Showcase](https://kovacsphil-art.github.io/synthetic_banking/) · [Validation Report — Original vs Synthetic Data](https://kovacsphil-art.github.io/synthetic_banking/validation.html#summary) · [Sanitized reporting JSON](https://kovacsphil-art.github.io/synthetic_banking/latest-pipeline.json).

**Post-pilot state:** all eight live tasks succeeded: 10,000 customers, 17,313 accounts, three reviewed rules applied, no skipped rules, and 100% account/balance coverage. Correlation and account-product fidelity improved, while balance mean fidelity worsened. Privacy remains **REVIEW_REQUIRED** (14 near matches and eight SOURCE-rare category matches); general privacy clearance remains blocked. Separately verified fabricated DEMO_ONLY downloads are now available. SOURCE is fabricated development data, not production banking data. The [post-pilot review](docs/post-pilot-review.md) explains the mean regression, the inactive calibration candidate and its trade-offs, privacy findings, and provisional validation criteria. The Validation Report loads the measured mean/tail and separate privacy summaries automatically; integrity PASS does not imply statistical acceptance or privacy clearance.

The [November 21 follow-up](docs/post-pilot-review.md#follow-up-review--november-21-2026) reproduces the mean/cap decomposition against the same SOURCE settings and checks the latest published aggregates. Rank coupling preserves raw balances, while reduced downstream clipping exposes an existing interpolation mean bias. Balance-only calibration remains inactive because it worsens available-credit mean fidelity. The report now explains this interaction and why rare near matches in fabricated data remain review signals rather than confirmed disclosures; no generator or privacy policy changed.

## How to Run

The [null-rate audit](docs/null-rate-audit.md) now separates trivial exact-zero missingness from meaningful preservation across all six tables. The measured cohort has 165 zero-null matches, 49 preserved nonzero rates, five 0%→100% discrepancies and one unavailable comparison. These counts are separate from the eight-variable core selection; zero-null observations remain visible but cannot inflate statistical strengths. Generation is unchanged.

**Start with the [first-time setup guide](docs/setup.md)** for prerequisites, scoped permissions, configuration, fabricated inputs, automated execution, review/repair, output locations and troubleshooting. Stakeholders can view the published showcase without installing anything.

1. Configure `src/synthetic_banking/config.py`, compute and development Volumes; keep the complete project folders together.
2. Supply the separate schema-only workbook; run [00_Create_Fabricated_SOURCE.py](notebooks/00_Create_Fabricated_SOURCE.py) once to create the six initial fake Parquet inputs.
3. Deploy the bundle and start `synthetic_pipeline`. Its first tasks run Notebook 01 as SOURCE, then Notebook 02 for that exact SOURCE run.
4. Review each proposal in the stopped batch. Approve or reject individually, then repair from `approval_check` through downstream tasks. No automatic approval.
5. The job generates six Delta tables, screens privacy, profiles GENERATED and validates against the pinned SOURCE. Inspect individual fidelity metrics and actual rule applications.
6. Reporting exports sanitized JSON; separately configured GitHub Actions updates Pages. Demo CSV/ZIP publication requires its own explicit verified DEMO_ONLY gates.

For manual notebook execution, follow the [controlled pilot](docs/controlled-pilot.md). For exact task values and repair behavior, use the [workflow runbook](docs/workflow.md). Never use `current_run` to select generation inputs.

Use bundle target `free` for serverless or configure `cluster_id` for `dev`. Provision the reporting Volume first. A fresh batch intentionally stops with a failed `APPROVAL_REQUIRED` gate until reviewed; this is expected, not a completed dataset.

### Shared code and configuration

Keep `notebooks/` and `src/` together, whether using Git or uploading the project to Databricks. Each notebook finds `src/` automatically; no package build or installation is needed. Run each notebook from the top after changing parameters or shared code. If discovery fails, add the absolute project `src/` path to `sys.path`.

[`config.py`](src/synthetic_banking/config.py) holds the catalog, profiling/generated/staging schemas, SOURCE aliases and Volume directory, model endpoint, default population, and seed. Defaults retain the existing `workspace` destinations and seed `42`. Notebook 01's `source_dir` is a Python variable, not a widget; use the shared default for automated/demo runs. Notebook 03 exposes `GenerationSettings` for population, seed, and pilot selection. SOURCE run, batch, proposal IDs, and profiling mode remain notebook widget choices. Change shared defaults before starting a fresh notebook session; SQL examples in this README use the default names. Bundle and publication settings are mapped in [one configuration table](docs/setup.md#1-prerequisites-and-configuration).

The notebooks now coordinate these reusable modules:

| Stage | Modules | Responsibility |
| --- | --- | --- |
| Profile inputs and lifecycle | `profiling_run.py`, `profiling_sql.py` | Explicit SOURCE/GENERATED inputs, preflight, run registration/completion, inventory, and existing feature/view SQL |
| Marginal profiling | `marginal_profiles.py` | Existing quality, numeric, categorical, and date aggregations |
| Select and load SOURCE | `profiles.py` | One completed SOURCE run and run-filtered aggregate profiles; shared by proposal and generation stages |
| Propose rules | `proposals.py` | Aggregate context, unchanged prompts, identifiable model batches, fixed-schema parsing, and PENDING proposal storage |
| Generate records | `generation.py`, `generators.py`, `dates.py`, `customer_relationships.py` | Existing entity assembly, numeric/categorical/null/cardinality sampling, dates, and relationship graph |
| Select/apply reviewed rules | `rules.py`, `dependency_sampling.py` | Provenance checks, predefined implementations, measured conditional sampling, legacy fallbacks, and application/skip events |
| Persist and validate | `storage.py`, `validation.py`, `temporal.py` | Six Delta tables, audits, validation gates, and completion only after validation |
| Compare and publish aggregates | `fidelity.py`, `showcase.py` | Pinned SOURCE-vs-GENERATED metrics and optional HTML export |
| Job handoffs and public report | `workflow.py`, `reporting.py` | Explicit provenance, manual approval gate, generation/version guards, and sanitized versioned JSON |
| Public validation interpretation | `validation_reporting.py`, `privacy_reporting.py` | Fixed aggregate selection, versioned provisional tolerances, measured strengths/weaknesses, and a separate snapshot-verified privacy summary |
| Privacy screening / row-release gate | `privacy.py`, `privacy_checks.py`, `privacy_sources.py` | Aggregate-only disclosure checks, SOURCE Delta snapshots, and fail-closed release clearance |

The orchestration refactor retains sampling formulas, RNG call order and table/view architecture. The subsequent [phase-one fidelity update](docs/statistical-fidelity-phase1.md) adds three approval-gated samplers; without eligible new approvals the existing cohort path and RNG state remain unchanged. Row-level release has a separate privacy gate. The legacy arbitrary-CSV ZIP utility in `artifacts.py` is now disabled because its files cannot be bound to an assessed generation; aggregate reporting is unaffected.

### Conditional sampling: first phase

Two measured categorical relationships are now supported: `ACCOUNT_TYPE_CD → CLIENT_PRODUCT_CD → TSYS_PRODUCT_CD`. A numeric implementation couples existing balance draws to measured SOURCE credit-limit quartile distributions before the unchanged caps and formulas. All three require individually reviewed same-SOURCE proposals; sparse, missing or unsupported evidence produces an audited skip. No new generation mode or AI/control comparison is added.

Use Notebook 02's `ACCOUNT_CORE` scope (both interactive pilot toggles OFF, or workflow `rule_scope=ACCOUNT_CORE`) to propose these candidates. The existing default `BALANCE_PILOT` remains narrowly scoped to its original formulas. The [phase-one runbook](docs/statistical-fidelity-phase1.md) documents matching metadata, support thresholds, ordering, local before/after previews, regressions and the remaining Databricks pilot. Preview results have not replaced published measurements.

The fidelity report now includes categorical conditional proportions and unsupported-combination rates. Sanitized optional dependency fields feed supplemental tables within the existing Validation Report, without changing its design or headline check counts. Numeric means and downstream delinquency can regress even when correlations and percentiles improve; review individual metrics before accepting a cohort.

The first live pilot completed after individual review, isolated validation and a successful main workflow. It generated 10,000 customers and 17,313 accounts; all three new proposals were applied, none skipped, and account/balance join coverage was 100%. The [live results and limitations](docs/statistical-fidelity-phase1.md#live-pilot-confirmation) distinguish successful structural validation from unresolved fidelity gaps and privacy `REVIEW_REQUIRED`. The showcase now publishes these measured results and separately verified fabricated demo downloads. The deployed nine-task integration run reused the reviewed SOURCE/batch and succeeded without changing generation or standard privacy checks.

### Privacy screening before row-level sharing

The job runs Notebook 07 after generation and saves separate aggregate privacy metrics: identifier-domain overlap, exact SOURCE-row matches, payload copying with regenerated IDs, curated rare categorical patterns and bounded PERSON date/gender similarity. SOURCE snapshots are recorded and verified by Notebook 01; older SOURCE runs without that evidence cannot clear row release. See [privacy checks, thresholds and limitations](docs/privacy.md).

`PASS`, `REVIEW_REQUIRED` and `BLOCKED` describe this basic screen, not anonymization certification. Unresolved findings, missing inputs, errors or resource limits block any future row exporter through `require_row_level_release`. The existing unbound-CSV ZIP helper is disabled. Aggregate fidelity JSON and the HTML showcase continue independently, and their validation PASS must not be read as privacy approval. General row-level publication remains blocked. The separately verified fabricated DEMO_ONLY downloads are published; they do not change standard privacy clearance.

### Private DEMO_ONLY dataset export

Notebook 08 and the separate unscheduled `demo_dataset_export` job package the six existing generated Delta tables into CSVs and one ZIP, with a data dictionary and versioned metadata. The stage requires exact reproduction of the pinned fabricated SOURCE and generated cohort, reviewed schema/content checks and matching validation/privacy provenance. `DEMO_ONLY` must be selected explicitly; uncertain origin stops export. Privacy REVIEW_REQUIRED is retained. The standalone export keeps files in the private development Volume. The opt-in automated verification task below can copy a fully verified package to its run-scoped reporting folder; publication remains separately controlled. See [parameters, safeguards and output format](docs/demo-dataset-export.md).

The export also creates a separate, sanitized `demo-preview.json`: the first 15 generated records per table with a small fixed column selection. The overview's **Synthetic Data Explorer** displays only this bounded preview, with six-table selection, full-table counts, an expandable column guide and highlighted synthetic identifiers. Selected CSV and complete ZIP links reuse the existing manifest/Release checks and match the displayed preview version; no full dataset is fetched for browsing. Missing, mismatched or withdrawn provenance hides the preview; unavailable downloads stay disabled. Privacy status and separate DEMO_ONLY eligibility remain explicit. See the [preview contract and safeguards](docs/records-preview.md). Preview preparation does not publish or deploy the website.

The download section shows verified generation/export dates, row counts and file sizes, with a **Using the demo files** guide for joins and CSV imports. The ZIP includes all six CSVs, `data_dictionary.md` and `metadata.json` (generation date, seed, version, counts, checksums and unchanged privacy findings). All eight public downloads, their preview values and complete-file relationships were [reverified](docs/demo-release-verification.md); standard privacy remains REVIEW_REQUIRED.

### Automated demo export and downloads — opt-in

The main job now includes `demo_export_verification` after validation (nine tasks). It reuses the existing exporter and verification modules for the exact validated cohort. Set job parameter `demo_release_mode=DEMO_ONLY` to opt in; DISABLED continues aggregate reporting. A full six-table replay must prove the approved fabricated SOURCE and generated origin. Privacy REVIEW_REQUIRED remains separate and unchanged.

Public dataset distribution additionally requires GitHub Actions variable `SAGE_PUBLISH_DEMO_DATASETS=true`. Actions uploads the eight verified assets to a draft versioned Release, publishes only a complete matching set, and updates the report, small preview and public download manifest together. The browser checks their common version/fingerprint/counts before enabling ZIP/CSV/dictionary links. Missing or mismatched evidence disables links. CSVs/ZIPs never enter Git or Pages assets. Failure retains previous valid downloads; an intentional disable omits demo metadata on subsequent site deployments. See [triggering, lineage, failure recovery and disable controls](docs/automated-demo-publication.md). The nine-task job is deployed, the verified demo Release and Pages site are live, and all public downloads/previews/references were checked. Future demo runs still require explicit `demo_release_mode=DEMO_ONLY`; the default remains DISABLED. No additional manual secret setup is needed for the existing repository.

### Optional setup for fake SOURCE inputs

Run [00_Create_Fabricated_SOURCE.py](notebooks/00_Create_Fabricated_SOURCE.py) once before SOURCE profiling to create the six input Parquet files. It calls the unchanged [Scotia Fake Records.py](scripts/Scotia%20Fake%20Records.py) using `config.py`'s `SOURCE_DIR` and the reviewed demo policy's population/seed. The schema-only workbook `RCAR_source_column_list.xlsx` is required separately in that directory; it is not in Git.

Use a dedicated writable development Volume: setup replaces same-named `RCAR_synthetic_*.parquet` files. The existing script uses NumPy, pandas, openpyxl and PyArrow. Keep its bytes unchanged because DEMO_ONLY replay verifies its fingerprint; do not edit hard-coded paths in the original script to configure a new installation. The setup wrapper supplies paths without changing its formulas or sampling.

### Project showcase and GitHub Pages

For a local preview, [serve only `docs/` over localhost](docs/setup.md#local-verification-without-databricks); double-clicking HTML can block the JSON-backed results. Automated publishing uses [Publish validated showcase](.github/workflows/publish-showcase.yml): GitHub polls for a successful Databricks job every 15 minutes, validates its run-specific sanitized JSON, commits the sanitized report (plus the matching bounded preview/download manifest when demo publication is enabled), and deploys an explicit list of static assets using GitHub Pages. Choose **Settings → Pages → GitHub Actions**, then configure the secrets and variables in the [publication runbook](docs/publication.md). Failed runs and invalid reports leave the published site intact. **Actions → Publish validated showcase → Run workflow** provides a manual trigger.

Automatic selection uses the latest final successful validation, including repaired jobs, and requires a matching SHA-256 receipt for every report. Publisher/staging safeguard tests, frontend tests and staged browser-contract checks run before deployment. The artifact builder excludes row files and checks any separately gated demo metadata against the same report. See [configuration, failure recovery and external setup](docs/publication.md#configuration-status-and-external-setup); the existing SAGE setup is reused and no modeling logic changes.

The SAGE showcase presents the process as an executive overview, with a shared stage briefing panel (purpose, inputs, outputs and business value), hover/focus previews, click/tap selection, arrow-key navigation and Escape/Back to stages controls and measured results separated from static methodology. `showcase.js` loads `docs/latest-pipeline.json`, reusing the existing report checks; `executive-viz.js` draws the published aggregates. Architecture, profiling methodology and review explanations remain static. Missing/invalid files show a professional unavailable state. The documentation example is never loaded as live results.

Both pages use consistent navigation between Pipeline, Validation Report and Synthetic Data Explorer. Shared control states, keyboard/touch interactions, visible sort direction, contextual help and retry feedback are documented in the [showcase UX review](docs/showcase-ux.md), including verification scope and remaining limitations. These presentation changes do not alter statistical claims or privacy/release controls.

The Validation Report now qualifies headline strengths using published variation and sample evidence, separating constructed patterns and date endpoints from statistical matches. Plain-language findings show direction and business implications; shared contextual help explains key terms. See the [interpretation audit and limits](docs/validation-report.md#evidence-qualified-executive-findings). No calculations, thresholds, generation or privacy controls changed.

The Validation Report leads with selected-variable outcomes, then separates additional statistical checks and the full-dataset missingness audit. Check counts, definitions and zero-null exclusions are expandable; findings explain potential business consequences alongside the measured SOURCE/synthetic values. Privacy remains a separate assessment. Counts come from the existing JSON, with calculations and thresholds unchanged.

The overview puts measured findings immediately after the pipeline, before detailed methodology and demo browsing. The full report prioritizes summary, findings and interactive exploration; **Evidence sections** expands its detailed links. Direct report-section links also work after JSON loads. Privacy review and separately verified fabricated-demo availability are explained distinctly.

The distribution visual connects four measured percentiles; it is not a density estimate. The validation report assesses the final cohort against the fake development SOURCE baseline, rather than attributing outcomes to AI. It uses per-dimension measurements and evidence counts without an overall accuracy percentage. Upper-tail comparisons show P95 and P95-minus-median spread; missingness, monthly date distances, conditional rates, cardinalities and structural checks are visible directly. Rule-application counts remain pipeline context, outside the validation report. No reporting schema, generation logic or tolerance was changed for this presentation update.

The dedicated [Validation Report — Original vs Synthetic Data](docs/validation.html) uses version-2 reporting aggregates for percentile and upper-tail comparisons, categorical/null/date fidelity, measured dependencies, relationship cardinalities and structural integrity. Strengths and priority gaps are calculated from centralized prototype tolerances; unavailable comparisons remain explicit. A compact explorer adds Numeric/Categorical/Dependency tabs, published-variable charts, keyboard/touch metric guides, sortable gap tables and strongest/weakest views using existing report classifications. Executive findings stay above the controls. See [metric mappings, thresholds, ranking and limitations](docs/validation-report.md). The current artifact does not publish extreme-tail percentiles beyond P95 or paired monthly bins. Generation behavior is unchanged.

Reporting is now **schema version 2.0**. The SAGE executive views require version 2; the publisher and legacy summary loader still accept version 1. Numeric fidelity bars use average absolute P25/P50/P75/P95 differences relative to SOURCE IQR, while classifications use the worst percentile difference. Categories/nulls use percentage points; date/cardinality distributions use total variation; correlations use absolute differences. The displayed tolerances are prototype screening settings, not an overall quality score or calibrated release criteria. Integrity PASS and privacy clearance remain separate from statistical similarity.

The reporting task writes `<report_output_dir>/runs/<job-run-id>/latest-pipeline.json`. GitHub retrieves that exact successful run's report and, only with the explicit demo-publication switch, its verified run-scoped demo assets. It validates the closed contracts, updates the public metadata and deploys the explicitly listed static website files. It does not start Databricks jobs or approve rules. Credentials belong in GitHub Actions Secrets (`DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET`); job/path settings are Actions variables (`DATABRICKS_JOB_ID`, `REPORT_OUTPUT_DIR`). The reporting identity has job CAN VIEW and read access to the dedicated report Volume. Rotate its OAuth secret before expiry; the current setup uses a 90-day lifetime. No credential values or row exports belong in Git.

The configured public repository uses GitHub Free for Pages; GitHub Pro is not needed for this public setup. Full configuration and failure/retry behavior are in the [publication runbook](docs/publication.md).

To refresh report calculations or the JSON schema from an existing validated dataset, deploy the updated bundle and repair **only `reporting`** in that successful run. Its original SOURCE/GENERATED lineage and saved output versions must still pass validation. Then trigger **Publish validated showcase**, or wait for the scheduled check. For HTML/CSS/JavaScript-only changes, push the website assets and trigger publication using the existing valid report; no Databricks rerun is needed. Use the existing full workflow when creating a new dataset. Failed exports or deployments preserve the last successful public report/site.

For local preview, run `python -m http.server 8000 --bind 127.0.0.1 --directory docs` from the repository root and open `http://127.0.0.1:8000/` or `http://127.0.0.1:8000/validation.html`. Opening `index.html` directly still shows the project, but browser `file://` restrictions can block JSON loading. See the [exact webpage JSON field reference](docs/results-data.md), [reporting schema](docs/reporting/pipeline-report.schema.json) and [fabricated example](docs/reporting/example.json). Examples are for documentation/tests; never replace the live report with fabricated results.

Notebook 01's older static-HTML export remains available in interactive mode for compatibility; it is not needed to publish JSON-backed results. It also copies `results.js` when present. Workflow mode skips that HTML export. Use the sanitized reporting artifact as the site's results source rather than exporting raw profiler tables or the internal `fidelity_report.json`.

### Published validation snapshot — November 20, 2026

The first completed controlled pilot generated **10,000 customers** and **17,313 accounts**, with both reviewed balance implementations applied. The saved report shows:

| Measurement | Result |
| --- | --- |
| Selected variables evaluated | 8 |
| Variables within prototype tolerance | 4 |
| Variables needing review | 3 |
| Variables incomplete | 1 |
| Checks evaluated | 35 |
| Account-to-balance / balance-to-account coverage | 100% / 100% |
| AI-proposed rules actually applied | 2 |

The largest classified gaps are available-credit percentiles, credit-limit/balance correlation, and birth/customer-since date distributions. Overlimit normalization is unavailable because SOURCE IQR is zero; its raw quantiles remain visible. Sparse conditional buckets, unprofiled tradelines-per-customer cardinality and some cross-table reference comparisons also remain pending. These findings do not change generation logic or establish external-release approval. This is a dated snapshot; the [live report](https://kovacsphil-art.github.io/synthetic_banking/validation.html#summary) and its completion timestamp are authoritative for subsequent runs.

---

## Primary Goal

Build a synthetic banking-data generator that:

1. Learns statistical properties from source data without copying source records.
2. Preserves important marginal distributions such as numeric quantiles, categorical proportions, date ranges, null rates, and relationship cardinalities.
3. Preserves selected cross-variable and cross-table relationships where appropriate.
4. Uses an LLM only as a **dependency and rule proposer**, based on aggregate profiler output.
5. Requires rules to be represented as explicit, reviewable metadata before they affect generation.
6. Generates new identifiers and new row-level records.
7. Can be re-profiled using the same profiling pipeline so source and generated statistics can be compared.
8. Remains auditable and understandable enough for a banking / governed-data context.

The LLM should **not** directly generate customer rows and should not be given row-level banking records in the current design.

---

# Current Notebooks

The project has three main Databricks notebooks, plus small approval, validation and reporting task notebooks for the [orchestrated workflow](docs/workflow.md).

## `01_Stat extraction _v1.ipynb`

### Purpose

Builds the statistical profiling layer used by the rest of the project.

### Current development-data setup

In `SOURCE` mode, the notebook loads development/test Parquet files from:

```text
/Volumes/workspace/default/scotia/
```

into Delta tables in:

```text
workspace.default
```

The logical tables are:

```text
PERSON
CUSTOMER_ACCOUNT_REL
CUSTOMER_RELATIONSHIP
TKQ_ACCOUNT
TKQ_ACCOUNT_BALANCE
TRADELINES
```

The notebook then creates aliases that resemble the intended production source locations:

```text
workspace.bronze_cis_mdm.TOS_PERSON
workspace.bronze_cis_mdm.TOS_CUSTOMER_ACCOUNT_RELATIONSHIP
workspace.bronze_cis_mdm.TOS_CUSTOMER_RELATIONSHIP
workspace.bronze_tsys.KQ_TKQ_ACCOUNT
workspace.bronze_tsys.KQ_TKQ_ACCOUNT_BALANCE
workspace.bronze_transunion.tradlines_file
```

The bronze views remain the SOURCE aliases. In `GENERATED` mode, Notebook 01 reads all six generated Delta tables from `workspace.synthetic_generated`, including `CUSTOMER_RELATIONSHIP`. It requires a completed generation record and validated versions for all six tables and both generation audits before starting a profiling run.

### Profiling schema

Profiler outputs are stored under:

```text
workspace.synthetic_profile
```

Important objects include:

```text
source_config
profile_runs
profile_run_lineage
privacy_source_snapshots
privacy_assessments
privacy_metrics
current_run
column_inventory
column_quality
numeric_profile
category_profile
categorical_relationship_profile
categorical_conditional_profile
date_profile
date_distribution_profile
relationship_profile
numeric_dependency_profile
customer_relationship_summary
customer_relationship_degree_profile
customer_relationship_dyad_profile
customer_relationship_type_profile
customer_relationship_ownership_profile
customer_relationship_field_profile
conditional_profile
cardinality_profile
integrity_profile
fidelity_metrics
```

### Run tracking

`profile_runs` tracks:

```text
run_id
started_at
completed_at
status
profile_type
```

The `profile_type` widget requires one of these values:

```text
SOURCE
GENERATED
```

The notebook records the chosen mode in `profile_runs` and writes each aggregate under a new run ID. `source_config` and `column_inventory` describe the SOURCE inputs. GENERATED profiling uses session-local input and inventory views, so the existing SOURCE metadata and aggregate runs remain available.

`profile_run_lineage` saves the profiling mode and, for GENERATED runs, the pinned SOURCE run and generation ID before the run completes. Historical fidelity reports use this saved correspondence, even after the generated tables have been overwritten by a later batch.

### Column profiling

The notebook creates a `column_inventory` and classifies columns into roles such as:

```text
IDENTIFIER
NUMERIC
DATE
TIMESTAMP
CATEGORICAL_CANDIDATE
OTHER
```

It then extracts:

#### Data quality

```text
row count
non-null count
null count
null percentage
approximate distinct count
distinct percentage
```

#### Numeric profiles

```text
minimum
P01
P05
P25
P50
mean
P75
P95
P99
maximum
standard deviation
```

#### Categorical profiles

Low-cardinality string columns are profiled when approximate distinct count is <= 100.

The profiler records:

```text
category value
record count
proportion
```

#### Categorical dependencies

Notebook 01 profiles ten curated within-table pairs from `CATEGORICAL_PAIRS` in [`profiling.py`](src/synthetic_banking/profiling.py). These cover employment/occupation, account/product codes, payment method/past-due status, account ownership flags, customer relationship direction codes, and tradeline categories. Both columns must be classified as `CATEGORICAL_CANDIDATE` in the active inventory. There is no automatic all-column pair search.

The defaults allow at most 12 configured pairs, 20 categories per column, and 200 cells per cross-tab. Approximate distinct counts provide an initial bound, followed by exact bounds on the grouped counts. Missing columns, identifiers, and high-cardinality pairs receive explicit skip reasons. Empty and constant relationships have separate statuses, with an undefined association metric represented as null.

`workspace.synthetic_profile.categorical_relationship_profile` stores one summary per configured pair and run, including `profile_type`, total rows, complete-case sample size, null exclusions, category counts, Pearson chi-square, degrees of freedom, Cramér's V, minimum expected count, fraction of expected cells below five, and minimum parent and observed-cell counts. V uses the standard uncorrected formula `sqrt(chi_square / (sample_size * min(parent_levels - 1, child_levels - 1)))`. It measures association symmetrically. Sample size and sparsity diagnostics help reviewers assess the evidence. [Cramér's V reference](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.contingency.association.html)

`workspace.synthetic_profile.categorical_conditional_profile` stores the full bounded cross-tab, including zero-count combinations, parent and child totals, joint proportions, conditional proportions, and expected counts. Rows with either value missing are excluded from this cross-tab. `conditional_proportion` estimates `P(child | parent, both observed)`. Existing null profiles retain the separate missingness measurements.

Both tables retain SOURCE and GENERATED histories under their exact run IDs. The categorical stage runs before the profiling run is completed and atomically replaces only the current run's rows in each table on retry. SOURCE history remains available after GENERATED profiling. [Delta selective overwrite](https://docs.databricks.com/aws/en/delta/selective-overwrite)

#### Date profiles

```text
non-null count
earliest date
latest date
calendar-month counts and proportions (YYYY-MM)
```

Monthly proportions in `date_distribution_profile` use non-null dates as their denominator. They measure calendar-month shape; date bounds retain day resolution. Time-of-day fidelity is not measured.

### Derived banking features

The notebook also builds derived feature views.

Examples include:

```text
UTILIZATION_RATE
TOTAL_PAST_DUE_AMT
TOTAL_PAST_DUE_COUNT
ACCOUNT_AGE_DAYS
DAYS_SINCE_LAST_PAYMENT
DAYS_SINCE_LAST_PURCHASE
AGE_YEARS
CUSTOMER_TENURE_YEARS
HAS_BANKRUPTCY
DECEASED_FLAG
TRADELINE_UTILIZATION_RATE
TOTAL_LATE_COUNT
TRADELINE_AGE_MONTHS
```

### Currently profiled dependencies

Dependency profiling combines the original banking-specific measurements with a bounded set of selected numeric and categorical pairs.

Examples currently implemented include:

```text
CREDIT_LIMIT_AMT <-> CURRENT_BALANCE_AMT
```

using Pearson correlation, and:

```text
UTILIZATION_RATE -> PAST_DUE_INDICATO_CD
```

using utilization buckets and observed delinquency rates.

Both calculations use the account feature view, which joins accounts and balances on `ACCOUNT_ID` and `BUSINESSEFFECTIVEDATE`. The [generated batch validator](#generated-batch-validation) checks one-to-one join coverage on those keys before Notebook 01 can profile the batch.

#### Selected numeric dependencies

[`numeric_dependencies.py`](src/synthetic_banking/numeric_dependencies.py) configures ten pairs through `NUMERIC_PAIRS`, with a hard limit of 12. Both raw fields must already be classified `NUMERIC` and have compatible numeric types in the active feature view. It does not search every numeric-column combination.

| Population | Selected pairs |
| --- | --- |
| Account snapshots | Credit limit / current balance; credit limit / original credit limit; current balance / minimum payment due; current balance / payment YTD; purchase YTD / payment YTD; current balance / current credit score; current balance / available-to-buy amount |
| Tradelines | Credit limit / current balance; credit limit / high credit; current balance / payment amount |

`workspace.synthetic_profile.numeric_dependency_profile` stores the exact `run_id` and `profile_type`, qualified column names, population count, non-null pair count, finite pair count, null/non-finite exclusions, pair coverage, Pearson correlation, paired means/sample standard deviations, min/max, and approximate P25/P50/P75 for both variables. All descriptive statistics use the **same complete finite-pair population**. Undefined correlation is null, with explicit `EMPTY`, `INSUFFICIENT`, `CONSTANT`, or `SKIPPED` statuses; it is not replaced by zero. Pearson measures linear association, not causation, independence, or a fitted generation formula. [Databricks Pearson correlation](https://docs.databricks.com/aws/en/sql/language-manual/functions/corr)

Each pair gets global evidence plus two bounded segment comparisons:

- **Product/type segments:** `CLIENT_PRODUCT_CD` for account features and `account_type_code` for tradelines. These must be categorical candidates. At most six distinct categories, including null, are allowed. Higher cardinality skips this segmentation with a reason while retaining global and quantile evidence. Null and the literal string `"NULL"` remain distinct.
- **X-quantile segments:** four intervals using measured complete-finite-pair SOURCE X quartiles: `(-∞, P25]`, `(P25, P50]`, `(P50, P75]`, `(P75, ∞)`. Means, spread, quantiles, and correlation within these intervals help expose nonlinear or mixed-population relationships. Cutpoints must be finite and strictly increasing; tied/missing cuts produce a skip status. Empty bins remain explicit. `percentile_approx` uses accuracy 10000, as in the marginal profiler.

SOURCE and GENERATED histories are retained separately, with only the active run's rows replaced on retry. GENERATED profiling reuses the exact pinned SOURCE pair's cutpoints, rather than defining new GENERATED quantile bins. If that SOURCE run predates numeric dependency profiling, quantile segmentation is unavailable; global/product evidence can still be recorded. The original `relationship_profile` measurement and convenience view remain unchanged.

Account evidence uses `active_account_features`, including its existing left snapshot join. Counts represent feature/join rows, which can be weighted by duplicate snapshot keys; they do not imply independent or unique accounts. Null balances and other incomplete/non-finite pairs are excluded and counted. SOURCE join/key diagnostics accompany account evidence when available. Tradeline evidence uses `active_tradeline_features`.

To propose broader numeric dependencies, run a fresh SOURCE profile, then run Notebook 02 against that completed SOURCE ID with both pilot widgets OFF. The default loader selects at most three pairs by their strongest supported absolute global **or segmented** Pearson coefficient, requiring at least 50 finite pairs globally and in each segment whose statistics are shown. Smaller segments retain counts/statuses but withhold their descriptive statistics. This is a bounded selection heuristic, not a significance test or confidence guarantee. A weak global association can still be included when a supported segment is strong. Missing evidence from older SOURCE runs produces an empty list.

Notebook 02 receives aggregate evidence only, frozen into the same SOURCE/batch prompt as the marginal and categorical context. It must cite support/coverage, compare global and segmented evidence, distinguish mathematical coupling and domain inference, and avoid claiming causation or inventing probabilities/formulas. Numeric proposals remain advisory and follow individual review; application still requires a predefined Python implementation. Profiling alone does not change generation. The later [phase-one implementation](docs/statistical-fidelity-phase1.md) keeps the selected credit-limit/balance global and quartile evidence visible in ACCOUNT_CORE context even when stronger unrelated pairs occupy the bounded advisory selection.

The profiler also records structural distributions such as:

```text
ACCOUNTS_PER_PARTY
```

### Published views

The convenience views follow `current_run`, which Notebook 01 publishes after it completes a profile:

```text
v_numeric_statistics
v_category_statistics
v_structural_statistics
v_dependency_statistics
```

The notebook retains its numeric and delinquency comparisons and adds the [consistent fidelity report](#source-vs-generated-fidelity-report) across profile families.

### Execution order

Run these steps serially on Databricks compute with Python and SQL support. The notebooks need access to the development Parquet files and permission to create or write the relevant schemas and tables.

Keep `notebooks/` and `src/` together in the Databricks project, using a Git checkout or uploaded workspace files. The notebooks collect parameters, call the [shared modules](#shared-code-and-configuration), display outputs, and coordinate Databricks reads/writes. Profiling uses Databricks-provided Spark; generation also uses NumPy and pandas. The optional fake-input script additionally needs openpyxl and PyArrow. [Databricks workspace module imports](https://docs.databricks.com/aws/en/files/workspace-modules)

1. **Profile SOURCE.** Run Notebook 01's widget cell, select `SOURCE` in `profile_type`, and run the notebook from the top. For a Databricks job, pass `profile_type=SOURCE`. Confirm that the run is `COMPLETED` in `workspace.synthetic_profile.profile_runs`.
2. **Generate synthetic data.** Run Notebook 03 through its Delta-save cell. It pins the latest completed SOURCE run, saves a new batch to `workspace.synthetic_generated`, and validates the saved outputs. The batch is ready when `generation_state` reports `COMPLETED` and contains the validated table versions.
3. **Profile GENERATED.** Rerun Notebook 01 from the top with `profile_type=GENERATED`. It checks the validation record against the current Delta tables, then records aggregates for all six generated tables under a separate run ID.
4. **Compare.** Review the fidelity report in the GENERATED run of Notebook 01: availability, largest deviations, unavailable comparisons/generated integrity issues, and the full metric list. It compares that profile with the exact SOURCE run used by Notebook 03.

To exercise the rule pilots, follow the [controlled pilot runbook](docs/controlled-pilot.md). It pins one SOURCE run, one proposal batch, manually reviewed proposal IDs, and the generated batch that Notebook 01 profiles.

Older run labels are retained as recorded. When migrating from the earlier notebooks, begin with a fresh SOURCE profile and regenerate the output tables in `workspace.synthetic_generated`.

---

## `02_LLM Rule Generation.ipynb`

### Purpose

Uses a Databricks-hosted LLM to propose candidate dependencies and generation rules based on **aggregate profiling data**.

The current model call is:

```text
system.ai.gpt-oss-20b
```

through Databricks `ai_query()`.

### Privacy / data boundary

The LLM is intentionally given profiler metadata rather than row-level source records.

The submitted prompt includes:

```text
table
column
data type
column role
null percentage
distinct count
mean
P25
P50
P75
P95
top categorical values and proportions
measured delinquency rates and sample counts by utilization bucket
bounded categorical cross-tabs, conditional proportions, Cramér's V, sample size, and sparsity diagnostics
selected global/segmented numeric correlations, paired sample counts, coverage, means, spread, and quantiles
```

The marginal column context is scoped to:

```text
TKQ_ACCOUNT
TKQ_ACCOUNT_BALANCE
```

Categorical evidence also covers the configured eligible pairs in PERSON, CUSTOMER_ACCOUNT_REL, CUSTOMER_RELATIONSHIP, TKQ_ACCOUNT, and TRADELINES. Numeric dependency evidence covers the selected account feature and tradeline pairs described above. These aggregates provide measured context beyond the marginal account-column profiles.

### Rule-proposal objective

The prompt asks the model to identify fields that should not necessarily be generated independently and to propose rule types such as:

```text
DERIVED
CONDITIONAL
CORRELATED
NO_RULE
```

Each proposal contains:

```text
target_table
target_column
rule_type
parent_columns
confidence
evidence_type
statistical_evidence
rationale
proposed_rule
requires_sme_review
```

Evidence is explicitly distinguished as:

```text
STATISTICAL
DOMAIN_INFERENCE
STATISTICAL_AND_DOMAIN
```

This distinction is important: an LLM recognizing a likely banking formula from a field name is not the same as the profiler proving that formula statistically.

### Proposal provenance

Notebook 02 pins the completed `source_run_id` supplied in its widget, or selects the latest completed SOURCE run when the widget is blank. It assigns a new `batch_id`, builds the prompt from that run's quality, numeric, categorical, and utilization/delinquency conditional profiles, and freezes the prompt and its IDs before calling the model. It requires aggregate column profiles for both account tables. Each run from the top creates a separate batch, even when the SOURCE run is the same.

For the conditional pilot, set `delinquency_pilot = ON` and `balance_pilot = OFF`, and supply an explicit SOURCE ID. The batch has scope `DELINQUENCY_PILOT` and asks for one `CONDITIONAL` proposal for `TKQ_ACCOUNT.PAST_DUE_INDICATO_CD` with parent `TKQ_ACCOUNT.UTILIZATION_RATE`. The prompt includes measured bucket rates and sample counts and requires probabilities to come from those measurements. Review and approve the proposal individually before supplying its batch and proposal IDs to Notebook 03.

For categorical proposals, run Notebook 01 as SOURCE with the new categorical stage, then run Notebook 02 against that completed SOURCE ID with both pilot widgets OFF. Its default context includes at most four profiled categorical relationships with at least 50 complete cases, ordered by descending V and sample size. The full cross-tab for each selected pair is included, with zero-count combinations and sample diagnostics. These prompt limits can be set explicitly through `load_categorical_evidence`. Missing categorical profiles produce an empty evidence list, supporting older completed SOURCE runs.

The evidence loader reads only the two aggregate tables and checks both the profile rows and `profile_runs` for the selected completed SOURCE run. Prompt instructions require categorical proposals to cite measured evidence, consider small samples and sparse cells, and treat parent/child direction as a review candidate. Proposed categorical dependencies pass through the existing PENDING/review workflow. Application requires a corresponding predefined generator implementation.

`workspace.synthetic_profile.ai_rule_batches` stores the batch ID, SOURCE run ID, model endpoint, scope, timestamp, SHA-256 of the submitted prompt, and raw JSON response. Previewing or parsing that batch reads the saved response. The notebook uses `FROM_JSON()` and explodes the response into rows in `workspace.synthetic_profile.ai_rule_proposals`, each with its own `proposal_id` and the same batch and SOURCE IDs. Rerunning the model and storage cells for a saved batch reuses its response and preserves its proposal rows.

### Review workflow

New proposals start as `PENDING`. Review the batch and an individual proposal and complete any required SME review. Run the separate SQL template in the Databricks SQL editor with `batch_id`, `proposal_id`, and a `review_decision` of `APPROVED` or `REJECTED`. The update records the reviewer and review time. The [generator's rule audit](#rule-execution-audit) records whether an approved proposal was applied.

The notebook setup adds provenance columns to an existing proposal table. It resets unbatched `APPROVED` rows to `PENDING` and retains their former status in `legacy_approval_status`. Legacy rows have no verified batch provenance and are ineligible for the review workflow. Generate a fresh batch to review those candidates again.

---

## `03_Synthetic_Gen_v1.ipynb`

### Purpose

Generates row-level synthetic records from the statistical profiles created by Notebook 01.

The current default is:

```python
N_CUSTOMERS = 10_000
SEED = 42
```

### Current profile loading

Notebook 03 pins the completed `source_run_id` supplied in its widget. With a blank widget, it selects the latest completion timestamp, breaking ties by start timestamp and then run ID. It prints the selected ID and stops if no eligible run exists. It uses that one `run_id` to load these base profile tables:

```text
numeric_profile
category_profile
date_profile
column_quality
relationship_profile
cardinality_profile
conditional_profile
```

### Numeric generation

Numeric columns are generated from profiler quantiles.

The generator approximates an inverse CDF using:

```text
min
P01
P05
P25
P50
P75
P95
P99
max
```

A uniform random percentile is drawn and interpolated between those percentile points.

This is an approximation of the source distribution, not an exact reconstruction.

### Categorical generation

Categorical values are sampled according to the source marginal category proportions.

Null categories are removed before category sampling because nulls are applied separately.

At present, most categorical variables are generated independently unless a relationship has been manually implemented elsewhere.

### Null generation

The existing non-date null-sampling pass uses the selected SOURCE run's `null_pct` where applied. Protected identifiers retain their generated values. Dates use a separate, single null mask based on the exact SOURCE `null_count / row_count`; their null count is rounded to the nearest whole generated row. Customer relationships instead supply their measured joint type/null-pattern mask to the date sampler. Dates are not passed through the generic null sampler a second time. Account/balance effective-date keys remain non-null for complete snapshot joins, even if their SOURCE profiles are nullable; diagnostics explicitly mark this exception.

### Date generation

[`dates.py`](src/synthetic_banking/dates.py) loads `date_profile`, `date_distribution_profile`, and `column_quality` for the exact completed SOURCE run used by Notebook 03. Only aggregates are read. It samples observed calendar months using their measured non-null counts, then samples a new day uniformly within that month's SOURCE bounds. No SOURCE rows or row-by-row dates are copied. Partial months and leap days are handled explicitly.

When ordering restricts a row to an interval, each month's weight is reduced by its feasible-day fraction and the remaining weights are renormalized. The planner propagates feasible intervals through the configured rules, including gaps between supported months, before sampling. This avoids replacing many invalid dates with a boundary date. Constraints can change marginal month proportions where independent SOURCE marginals cannot satisfy all ordering rules; the fidelity report exposes the resulting differences.

[`temporal.py`](src/synthetic_banking/temporal.py) defines the shared generation/validation ordering rules:

- `BIRTH_DT <= SINCE_DT` for PERSON.
- Account `OPEN_DT <= CLOSE_DT`, `OPEN_DT <= CLOSE_STATUS_DT`, and `OPEN_DT <= BUSINESSEFFECTIVEDATE`.
- Configured account activity dates, including first use, last payment/purchase, financial activity, high balance, delinquency and charge-off/revocation dates, fall between account open and the effective snapshot. First delinquency precedes last past due; last financial activity is no earlier than last payment/purchase.
- Tradeline open precedes close, paid-out, activity, payment-pattern start and snapshot dates; activity and payment-pattern start do not exceed the snapshot.

Ordering is **inclusive at day precision**: same-day opening/activity is allowed, and rules apply where both endpoints are present. Null dates remain null. The planner does not invent a missing parent date or add nulls to hide an infeasible non-null interval. If SOURCE support cannot satisfy an active constraint, generation stops before table writes with the affected column and a clear error. It does not manufacture a day outside observed SOURCE support.

Account/balance effective dates are sampled once per synthetic account and assigned by `ACCOUNT_ID`, including when balance rows are shuffled. The sampler prefers a measured balance monthly profile, then an account monthly profile, then available range-only profiles. When both have non-null support, their supported intervals are intersected. Disjoint supports or absent usable support fail clearly. The generated date is non-null on both sides.

Per-column random streams are derived deterministically from `SEED` and a stable hash of the table/column name. Date sampling does not use the numeric/categorical sampler's RNG. The same SOURCE profiles, seed and population reproduce the dates. Older-version datasets can differ because date-related RNG draws/null passes have changed; numeric/categorical generation formulas and sampling algorithms are retained.

Notebook 03 displays aggregate date diagnostics: SOURCE run, seed, method, SOURCE null rate, target/actual null counts, constrained-row counts and required non-null key flags. An older SOURCE run without monthly profiles uses an explicitly reported `RANGE_FALLBACK`; re-profile SOURCE with the updated Notebook 01 for measured month sampling and temporal validation history. All-null columns remain all-null. Any supplied monthly distribution must be complete and consistent with the SOURCE date/null counts and bounds.

### IDs

New identifiers are created rather than copied from the source.

Examples include:

```text
P00000001
A000000001
TL...
```

### Structural generation

The generator uses `cardinality_profile` to generate relationships such as:

```text
ACCOUNTS_PER_PARTY
```

and attempts to use:

```text
TRADELINES_PER_CIF
```

with a fallback of three tradelines per customer if no profile is available.

### Account balance generation

The generator uses predefined account dependencies.

For example:

```text
CURRENT_BALANCE_AMT
```

is initially sampled from its numeric profile and then constrained relative to:

```text
CREDIT_LIMIT_AMT
```

using an upper bound of approximately:

```text
1.25 * CREDIT_LIMIT_AMT
```

It then derives:

```text
AVAILABLE_TO_BUY_AMT
OVERLIMIT_AMT
_UTILIZATION_RATE
```

### Approval-controlled delinquency

The generator uses the SQL `conditional_profile` for:

```text
UTILIZATION_RATE -> PAST_DUE_INDICATO_CD
```

It maps utilization into buckets:

```text
0-30%
30-60%
60-80%
80-100%
100%+
```

and samples delinquency using the measured SOURCE outcome rate for the bucket. An approved `CONDITIONAL` proposal with verified review and batch provenance can select `delinquency_by_utilization` from the controlled registry. It runs after credit limit, current balance, and utilization are available.

`DELINQUENCY_CNT` is then conditioned on whether the synthetic account was sampled as delinquent.

The predefined implementation requires a unique, finite probability between 0 and 1 and a positive sample count for every bucket encountered in the generated population, all from the pinned SOURCE run. Missing, invalid, or duplicate evidence produces a logged skip. The implementation accepts the profiler parent `UTILIZATION_RATE` and its qualified name, plus the generator's corresponding `_UTILIZATION_RATE` aliases.

Legacy generation already used utilization buckets. Without an eligible approved proposal, its existing behavior remains the fallback, including 5% for an absent bucket. The controlled path uses the same random draws, preserving the downstream random-number state. In an explicitly selected pilot, any selected rule that fails to apply stops generation before table writes.

Notebook 01's GENERATED comparison pairs SOURCE and GENERATED delinquency rates by utilization bucket, reports both sample counts, and calculates differences in percentage points. The showcase also exports the paired aggregate rates.

### Remaining fields

`fill_profiled_fields()` fills remaining categorical/numeric fields and applies their existing null rates. The date sampler then supplies the table's dates together, with one SOURCE null mask and its ordering constraints.

### Current cross-table generation

Currently generated tables include:

```text
PERSON
CUSTOMER_ACCOUNT_REL
CUSTOMER_RELATIONSHIP
TKQ_ACCOUNT
TKQ_ACCOUNT_BALANCE
TRADELINES
```

`CUSTOMER_RELATIONSHIP` uses its aggregate-backed implementation described below and is saved through the normal Delta workflow, including when the measured SOURCE relationship population is empty.

Notebook 03 creates one account and one balance row per synthetic `ACCOUNT_ID`. The date sampler supplies their shared non-null `BUSINESSEFFECTIVEDATE` from the pinned SOURCE support and assigns it by account ID so both rows share the profiler's composite snapshot key.

### Customer-to-customer relationships

The development script/schema identifies `FROM_PARTY_ID`, `TO_PARTY_ID`, the directional code pair `FROM_TO_CUST_RELATN_CD` / `TO_FROM_CUST_RELATN_CD`, `ownership_percentage`, `OWNED_BUS_SINCE_DT`, and update metadata. Its example emits spouse pairs with null ownership/date fields. The generator uses measured SOURCE evidence rather than assuming every relationship is a spouse or using the script's fixed participation rate. Runtime profiling checks the actual active schema first; the external workbook/live Databricks schema remains authoritative.

[`relationship_profiles.py`](src/synthetic_banking/relationship_profiles.py) adds bounded aggregates under the same explicit SOURCE/GENERATED run:

- **Summary:** PERSON population, raw/valid rows, null/orphan endpoint exclusions, one-way/reciprocal/self dyads, and maximum repeated-row multiplicity. A dyad describes one pair of parties; reciprocal dyads contain records in both directions.
- **Joint degree histogram:** outgoing/incoming one-way neighbor counts, reciprocal neighbors, self-link presence, and raw outgoing/incoming row counts. All PERSON parties are included, even those with zero relationships.
- **Dyad histogram:** forward/reverse row multiplicities, preserving the distinction between one reciprocal pair and multiple rows for the same endpoints.
- **Type/null templates:** both directional codes together, coupled reverse codes for reciprocal pairs, and joint non-key null masks. SOURCE IDs remain inside Spark joins/grouping and are never collected into these profiles.
- **Ownership and field evidence:** ownership quantiles conditional on the directional code pair, null counts, and text-format aggregates for metadata. Existing numeric/category/monthly-date profiles supply other measured distributions.

These tables replace only the active run's rows on retry. Pattern histograms are capped at 4096 entries, the reviewed schema at 64 columns, and multiplicities at 1000 rows per directed pair. Four `CUSTOMER_RELATIONSHIP_*` distributions extend `cardinality_profile`: outgoing rows, incoming rows, reciprocal neighbors and self dyads. Account/tradeline cardinality rows are retained.

[`customer_relationships.py`](src/synthetic_banking/customer_relationships.py) loads only the exact completed SOURCE run and generates endpoints exclusively from the generated PERSON pool. It allocates joint degree patterns by measured proportions, matches reciprocal neighbors, and uses directed stub matching/swaps to avoid accidental self-links, duplicates, or reverse links in the one-way component. Repeated rows are then sampled from measured multiplicities. Self-links are generated only by the separately measured self component; no self-links are introduced when SOURCE has none.

Finite populations can require degree reconciliation. Every removed neighbor stub is logged; reductions above `max(2, ceil(5% of requested neighbor stubs))` fail rather than silently changing a large part of the structure. The default output budget is one million relationship rows. Tiny/dense populations may need a larger generated PERSON pool. Counts are statistical approximations, not an exact reconstruction of the SOURCE graph.

Type pairs/null masks are sampled jointly; reciprocal templates retain both observed directions. Ownership uses only measured conditional quantiles, is never rescaled between fractions and whole percentages, and must stay within `[0,100]`. All-null ownership fields remain null; no default ownership is invented. Dates use the existing SOURCE-month sampler with the relationship's joint null mask. Known update metadata uses measured non-null categories/quantiles; high-cardinality digit-only transit codes use their measured width and numeric range. Unsupported non-null schema fields fail with the column name, while all-null optional fields remain null.

Null/orphan SOURCE endpoint rows are counted but excluded from structural evidence. An entirely invalid nonempty SOURCE relationship table requires repair before generation. Generated endpoint keys are always non-null references to generated PERSON records, so invalid SOURCE key-null patterns are not reproduced. Other null patterns apply to the valid-link cohort. Existing marginals for metadata/dates can include the full SOURCE table; investigate fidelity differences when exclusions are substantial.

Notebook 03 displays and appends an aggregate plan to `workspace.synthetic_generated.customer_relationship_generation_log`: generation/SOURCE IDs, seed, implementation version, profile signature, population/row counts, self policy, dyad counts, degree adjustments and expected null counts. The audit is distinct from `rule_execution_log`; this base generator does not imply an AI proposal was approved or applied. Its committed Delta version is part of the validated batch.

**Execution/migration:** Run Notebook 01 as a fresh SOURCE profile with this stage, then follow the existing proposal/review/generation workflow using that exact SOURCE ID. Notebook 03 stops early if the selected SOURCE lacks graph profiles. Rerun Notebook 03 before profiling GENERATED: older five-table batches lack the new table/audit validation versions. Notebook 01 now profiles all six outputs. The fidelity report compares graph direction/self/endpoint rates, structural cardinalities, and the table's normal category, ownership, null and date profiles. The showcase includes its row count automatically.

Current limits: the model does not infer household semantics, party-demographic compatibility, ownership-total conservation, or complete event histories. Reciprocal rows use coupled templates; repeated reciprocal histories are approximated. Larger degree/type-conditioned or ownership-network models need separate measured evidence and explicit implementations.

### Schema completion

Before writing results, Notebook 03 takes expected columns from the pinned SOURCE run's quality profile and fills missing fields with typed nulls. This retains optional fields for profiling. The saved tables must independently pass schema, key, count, and invariant checks.

### Outputs

Generated DataFrames are written to Delta tables under:

```text
workspace.synthetic_generated
```

Notebook 03 records the generation ID and its SOURCE profile ID in `generation_state`. It sets the state to `RUNNING` before writing the tables and to `COMPLETED` after the saved data and audit pass validation.

The legacy CSV ZIP packaging step is disabled: existing files have no manifest binding them to the privacy-assessed generation. A future generation-bound row-level exporter must enforce the [privacy gate](docs/privacy.md) before any dataset download. The notebooks continue producing validated Delta tables and aggregate reports.

### Generated batch validation

[`validation.py`](src/synthetic_banking/validation.py) checks the saved Delta tables and rule audit:

- Required columns and compatible types for the pinned SOURCE schema and generated keys and rule fields. Account and balance snapshot dates must have the same type.
- Saved row counts against the generation plan. Generated person, account, and tradeline keys must match their assigned sequences. Links must reference the corresponding generated parent keys.
- CUSTOMER_RELATIONSHIP row/audit/null plans, FROM/TO membership in generated PERSON, SOURCE-supported self policy, and finite ownership percentages in `[0,100]`. All six tables and both audit tables must have committed Delta versions.
- Full one-to-one account and balance join coverage on `ACCOUNT_ID` and `BUSINESSEFFECTIVEDATE`.
- Existing derived rules for available credit, overlimit, the balance cap, utilization, delinquency flag and count, and PERSON date order.
- All available configured temporal ordering rules, evaluated at day precision on non-null pairs. Violations stop publication of the generated batch. Saved date null counts must also match the sampler's SOURCE-derived null plan.
- Saved audit rows for the generation and SOURCE run. Approved proposals without a matching implementation are reported with their proposal and batch IDs. Their skip is informational, and the legacy formula can still supply the target.

A validation failure leaves the batch `RUNNING`. After validation, Notebook 03 stores the table IDs and Delta versions in `generation_state`. Notebook 01 checks those versions before starting GENERATED profiling and again before marking that profile complete. Rerun Notebook 03 for a batch created before validation was added or for outputs whose Delta versions have changed. [Delta table details](https://docs.databricks.com/aws/en/delta/table-details) [Delta table history](https://docs.databricks.com/aws/en/tables/history)

---

# Controlled Balance-Rule Pilot

Notebook 03 snapshots proposal metadata from `workspace.synthetic_profile.ai_rule_proposals` for its pinned SOURCE run. Execution requires `approval_status = 'APPROVED'`, a reviewer and review timestamp, and a matching batch in `ai_rule_batches` for the same SOURCE run. Legacy approvals and pending or rejected proposals are tracked as skips. `proposed_rule` remains reviewer-facing text.

The pilot supports `DERIVED` proposals targeting `TKQ_ACCOUNT_BALANCE` with exactly two parents, `TKQ_ACCOUNT.CREDIT_LIMIT_AMT` and `TKQ_ACCOUNT_BALANCE.CURRENT_BALANCE_AMT`. The bare names `CREDIT_LIMIT_AMT` and `CURRENT_BALANCE_AMT` map to those same fixed inputs. Review a proposal against the formula below before approving it for the pilot.

| Target column | Python implementation | Existing formula |
| --- | --- | --- |
| `AVAILABLE_TO_BUY_AMT` | `available_to_buy` | `max(credit_limit - current_balance, 0)` |
| `OVERLIMIT_AMT` | `overlimit_amount` | `max(current_balance - credit_limit, 0)` |

The functions run in the order shown after the generator computes credit limit and bounded current balance and checks account ID alignment. An unsupported target, mismatched parents, missing credit-limit input, or conflicting approvals produces a skip reason. The existing formula supplies each target without a unique eligible approval.

The conditional registry adds `TKQ_ACCOUNT.PAST_DUE_INDICATO_CD` with rule type `CONDITIONAL` and one utilization parent. Its predefined `delinquency_by_utilization` implementation runs at execution order 3, after the balance rules and utilization calculation. Each proposal is routed to one phase and receives one proposal audit row. Missing or invalid evidence is recorded as `missing_conditional_profile` or `invalid_conditional_profile`, with `implemented = true` and `applied = false`. Existing legacy fallback executions are recorded separately.

### Shared dependency execution

There is one generation path. Reviewed proposal metadata selects an eligible predefined implementation; when none is eligible, the existing dependency still supplies its legacy values. No LLM-versus-no-LLM generation mode is needed.

| Dependency | Implementation ownership |
| --- | --- |
| Available credit and overlimit amounts | The existing functions in `rules.py` already serve approved proposals and legacy execution; their formulas are unchanged. |
| Utilization → past-due indicator | `rules.py` now owns bucket boundaries, measured-rate lookup, sampling and approval/skip decisions. Notebook 03's generator supplies the pinned profile and one set of random draws. The older scalar sampler delegates to the same lookup for compatibility. |
| Balance cap, utilization calculation and delinquency counts | Existing generation logic remains in place, in its original order. |
| Date constraints, entity references and snapshot alignment | Existing date/entity implementations and validation remain in place. |

Approved delinquency execution still requires valid, unique measured SOURCE probabilities and positive sample counts for every encountered bucket. It does not fill a missing bucket with an invented probability. If that proposal cannot apply, the preserved legacy lookup supplies the same SOURCE rates and existing 5% missing-bucket fallback. Legacy duplicate-rate handling remains last-row-wins; an approved proposal encountering duplicate evidence is skipped. Both use the same bucket lookup and outcome sampler, without drawing additional random numbers. The approved path avoids computing an unused legacy probability array.

Regression evidence was captured before this change from fabricated profiles only. `tests/test_dependency_regression.py` checks all six table hashes, numeric means/quantiles, utilization-bucket outcome counts and downstream RNG state against two fixed 512-customer baselines, including missing-bucket fallback. It also verifies approval states, conflicts, unsupported rules, exact bucket boundaries and one execution per dependency target. The earlier pre-refactor generation/audit snapshots remain unchanged.

## Rule execution audit

Notebook 03 appends one audit row per considered proposal and a separate row for each legacy formula used to fill a target. Rows in `workspace.synthetic_generated.rule_execution_log` include `generation_id`, `source_run_id`, `seed`, proposal `batch_id` and `proposal_id`, target table and column, rule type, parent columns, and the approval status read for that run.

| Field | Meaning |
| --- | --- |
| `proposed` | The row refers to an LLM proposal. |
| `approved` | The proposal was approved and has valid review and batch provenance. |
| `implemented` | A predefined implementation matches the rule metadata and parents. |
| `applied` | The proposal selected an implementation that generated values for at least one row. |

`outcome` distinguishes `APPLIED`, `SKIPPED`, and `LEGACY_FALLBACK`. Common skip reasons include `not_approved` for pending or rejected proposals, `unverified_approval` for an approval without valid provenance, and `no_implementation` for unsupported rule targets or types. The audit also records the implementation name, execution order, and rows processed where applicable. A legacy fallback can supply values for a target while its proposal is recorded as skipped.

`applied` specifically tracks approved-proposal application. A `LEGACY_FALLBACK` event with positive `rows_processed` means the dependency supplied values through existing behaviour; it intentionally has `applied = false` and is excluded from AI-applied counts. Historical implementation labels and the persisted audit schema are retained.

New writes add the tracking columns to the existing Delta table. Earlier rows retain their recorded outcomes and have nulls in the new columns.

To see which proposals affected the latest completed dataset, run:

```sql
SELECT l.generation_id, l.source_run_id, l.seed, l.batch_id, l.proposal_id,
       l.target_table, l.target_column, l.rule_type, l.parent_columns,
       l.implementation_name, l.rows_processed
FROM workspace.synthetic_generated.rule_execution_log l
JOIN workspace.synthetic_generated.generation_state s USING (generation_id)
WHERE s.status = 'COMPLETED'
  AND l.proposal_id IS NOT NULL
  AND COALESCE(l.applied, l.outcome = 'APPLIED' AND l.rows_processed > 0)
ORDER BY l.execution_order NULLS LAST, l.proposal_id;
```

For a full report on a batch, filter the audit table by its `generation_id` and inspect all outcomes.

---

# Generation Flow

```text
Latest completed SOURCE profile
            |
            v
Load univariate distributions
            |
            v
Load structural / conditional statistics
            |
            v
Generate base entities, credit limits, and bounded balances
            |
            v
Load explicitly reviewed proposals for the pinned SOURCE run
            |
            v
Controlled rule registry
            |
            v
Run the balance implementations and collect outcomes
            |
            v
Complete remaining fields
            |
            v
Complete the output schema
            |
            v
Write generated Delta tables and the rule audit, then validate the saved batch
            |
            v
Run profiler again as GENERATED
            |
            v
Compare SOURCE vs GENERATED
```

---

# Key Design Principles

## 1. The profiler is the statistical source of truth

The LLM may recommend *which* dependencies are important, but measured probabilities/distributions should come from profiler tables whenever available.

For example:

```text
LLM:
"PAST_DUE_INDICATO_CD should depend on utilization."

Profiler:
actual delinquency rate by utilization bucket.

Generator:
samples using those observed rates.
```

The LLM should not invent the underlying probability when a measured statistic is available.

## 2. LLM output is advisory

The LLM proposes:

```text
dependency structure
rule type
parent variables
rationale
confidence
```

It does not have unrestricted authority over generation.

## 3. Row-level source data should stay out of the LLM prompt

The current design uses aggregate statistics only.

Maintain that boundary unless the architecture is intentionally changed and appropriately reviewed.

## 4. New identifiers must remain synthetic

Do not reuse source:

```text
PARTY_ID
ACCOUNT_ID
ACCT_ID
account_number
```

values in generated records.

## 5. Preserve auditability

It should be possible to answer:

```text
Which source profile was used?
Which AI rules were proposed?
Which rules were approved?
Which rules were implemented?
Which rules were actually applied?
What random seed was used?
What validation results were produced?
```

## 6. Prefer explicit logic over hidden automation

For a banking-style synthetic-data pipeline, understandable and reviewable transformations are preferred over opaque automatic execution.

---

# Known Current Limitations

The current implementation is a prototype and intentionally incomplete.

Known limitations include:

- The controlled registry covers two balance formulas, utilization-to-delinquency, two account-product conditionals and one credit-limit/balance rank coupling. Other dependencies still use their existing generation paths; new implementations require individual same-SOURCE approvals and adequate measured support.
- The AI stage uses marginal profiles for the two account tables, bounded categorical evidence, and selected global/segmented numeric dependency evidence from the same completed SOURCE run.
- Most fields are still generated independently from marginal distributions.
- Numeric inverse-CDF generation is based on a limited set of percentile knots.
- Date generation preserves measured calendar-month shape within feasible ordering bounds, with uniform days inside each supported month. Detailed day-of-month/time-of-day patterns and measured joint date-lag models are not yet reproduced.
- Categorical-to-categorical generation is limited to two approved account-product relationships, with complete-case sampling and retained generated null masks. Missingness dependence and wider category networks are not modeled.
- Numeric dependency profiling covers selected account/tradeline pairs, product/type segments, and four SOURCE X-quantile intervals. The first numeric sampler uses those quartiles for approximate rank coupling, preserving raw marginal draws before existing caps. It does not exactly fit Pearson, nonlinear dependence or a copula, and final means/tails can still differ. Categorical profiling also covers a curated, bounded set of pairs.
- Customer relationships preserve measured degree/direction/type/null patterns approximately, with bounded logged reconciliation. Demographic compatibility, full reciprocal histories and ownership-total constraints are not modeled.
- Basic privacy screens are heuristic and limited to configured fields; no formal anonymity or disclosure guarantee is established. Row-level distribution remains gated, and the arbitrary-CSV ZIP helper is disabled.

---

# Suggested Near-Term Work

Prioritize work in roughly this order:

1. Investigate the [live phase-one pilot's](docs/statistical-fidelity-phase1.md#live-pilot-confirmation) remaining balance-mean, available-credit and utilization/delinquency discrepancies; review privacy findings before considering any row-level release.
2. Investigate remaining available-credit, tail and PERSON-date deviations using pinned SOURCE/GENERATED pairs before extending the registry further.
3. Calibrate the prototype report tolerances for the intended use case and expand coverage beyond the current public selection.
4. Investigate missing tradeline cardinality, sparse conditional buckets and unavailable cross-table reference comparisons; review customer-relationship degree adjustments.
5. Exercise privacy/release failures, expired credentials and report-write failures in a Databricks test destination; retain the successful approval-repair and publication checks as regression coverage.

---

# SOURCE-vs-GENERATED Fidelity Report

Notebook 01 uses [`fidelity.py`](src/synthetic_banking/fidelity.py) to save aggregate evidence in both profiling modes and produce a report after GENERATED profiling completes. Generation logic and its existing validation gate are unchanged.

| Metric family | Visible measurements / differences |
| --- | --- |
| Numeric | Mean, P01/P05/P25/P50/P75/P95/P99, min/max, standard deviation; signed/absolute differences and relative percent where defined |
| Categorical | Proportions over the union of categories, including the null category; differences in percentage points |
| Null rates | Null counts / table rows, denominators, and differences in percentage points |
| Dates | Earliest/latest shifts in days and calendar-month proportion differences |
| Cardinality | Each profiled cardinality's proportion, entity counts, and mean children per entity |
| Correlation / association | Pearson correlation and profiled categorical Cramér's V differences |
| Categorical dependencies | Per-parent conditional-proportion differences, parent sample counts and SOURCE-unsupported complete-case combination rates |
| Numeric dependencies | Selected global/segmented Pearson differences, paired counts, conditional Y means/quantiles, and explicit segmentation statuses; mismatched X-bin boundaries are unavailable |
| Conditional outcomes | Measured outcome rates and sample counts per utilization bucket; differences in percentage points |
| Snapshot joins / keys | Account and balance row coverage separately, duplicate composite-key excess rows, and null snapshot keys |
| Business rules | Violation counts, evaluated-row denominators, rates, and differences for existing balance, utilization, delinquency, and PERSON date-order invariants |
| Temporal rules | Configured PERSON/account/tradeline order violations, eligible non-null pair counts, rates and differences; absent columns/empty eligible populations are unavailable |
| Customer relationships | Invalid endpoint/self-row rates and one-way/reciprocal/self-dyad proportions; degree distributions are included under cardinalities |

`integrity_profile` records join/key checks, generator-invariant counts, and `TEMPORAL_RULE` counts at profiling time. Coverage counts each input row with a matching `ACCOUNT_ID` + `BUSINESSEFFECTIVEDATE`, using distinct key groups to prevent duplicate matches inflating coverage. Duplicate-key metrics expose one-to-many matches separately. Joined amount/utilization checks use matched join pairs as their evaluated population; delinquency uses account rows, and temporal ordering uses rows with both dates present. These are the prototype's configured generation constraints, not a claim that all SOURCE banking records must satisfy them. A missing private `_UTILIZATION_RATE` SOURCE field is explicitly unavailable for that invariant.

`workspace.synthetic_profile.fidelity_metrics` stores individual metric rows with `comparison_id`, `source_run_id`, `generated_run_id`, `generation_id`, timestamp, dimensions, values, differences/units, available counts/sample sizes, comparison status/reason, and generated-check status. Both profiles must be completed with the expected types, and the saved GENERATED lineage must reference the selected SOURCE. The report reads aggregate tables only and never substitutes `current_run`, convenience views, or current generated tables. Retrying a report replaces only that GENERATED run's metrics; other reports remain available.

The underlying fidelity report has **no overall score or calibrated statistical acceptance gate**. The public validation page separately classifies selected metrics using documented prototype display tolerances; these do not change pipeline validation. `highlight` marks the five largest nonzero deviations within each family and ranking basis. Numeric differences are ranked by `abs(GENERATED - SOURCE) / SOURCE IQR`, where IQR = P75 - P25; a zero/missing IQR leaves the raw difference visible without a normalized rank. Proportions are ranked by absolute percentage-point difference, date bounds by absolute days, correlations/associations by absolute difference, and counts/mean cardinality by absolute relative percent. Rates retain fraction-valued SOURCE/GENERATED values. Every signed difference is GENERATED minus SOURCE. Relative percent is `100 * (GENERATED - SOURCE) / abs(SOURCE)` and is null for a zero SOURCE value. Date bounds use day shifts without an epoch-dependent relative percentage.

Missing profiles or unsupported fields, empty populations, undefined associations, and non-finite values are marked `NOT_COMPARABLE` with reasons. The currently unprofiled `TRADELINES_PER_CIF` cardinality is explicitly unavailable; the generator's fallback remains unchanged. Missing category/month/cardinality bins become zero only when both complete distributions are available. Missing conditional buckets remain unavailable. Generated integrity statuses are separate: incomplete coverage or nonzero violations produce `ISSUE` even when a SOURCE comparison is unavailable. Statistical deviations are observations for review, not automatic pass/fail judgments.

For full coverage, start with a fresh SOURCE profile using the updated Notebook 01, then generate and profile GENERATED. Older SOURCE runs retain their existing measurements, with unrecorded monthly/integrity metrics shown as unavailable. Older GENERATED profiles without saved lineage must be re-profiled from the validated batch; the report will not infer historical correspondence from today's tables.

The GENERATED notebook displays all metrics, largest deviations, and unavailable comparisons/issues automatically. To recreate a historical report from saved aggregates:

```python
from synthetic_banking.fidelity import create_fidelity_report, export_fidelity_report

report = create_fidelity_report(spark, source_run_id="SOURCE_RUN_ID", generated_run_id="GENERATED_RUN_ID")
# Optional internal, machine-readable output:
export_fidelity_report(report, "/Volumes/workspace/default/scotia/fidelity_output")
```

The optional `fidelity_report.json` contains aggregate metrics and explicit lineage for internal analysis. The live HTML site consumes the separate sanitized `latest-pipeline.json`, built from the saved fidelity metrics and rule audit by Notebook 06. Keep internal exports in a private writable folder; publish only the closed public reporting contract, which omits internal run IDs and row records.

---

# Development / Codex Guidance

When modifying this repository:

- Preserve Databricks compatibility.
- Prefer small, testable Python functions over adding more logic directly into long notebook cells.
- Do not remove working profiling behavior unless replacing it with an equivalent tested implementation.
- Do not expose secrets, credentials, or row-level source data in Git.
- Do not assume LLM-proposed text is executable code.
- Keep source and generated profiling runs distinguishable.
- Keep generation reproducible through an explicit seed where possible.
- Avoid changing table names/catalog paths without documenting the migration.
- Add tests for rule implementations as logic is moved out of notebooks.
- Treat current hard-coded dependencies as candidates to refactor into the controlled rule registry rather than silently deleting them.

---

# Repository Layout and Local Checks

```text
synthetic_banking/
|-- AGENTS.md
|-- README.md
|-- requirements-dev.txt
|-- databricks.yml
|-- .github/workflows/
|   `-- publish-showcase.yml
|-- resources/
|   `-- synthetic_pipeline.job.yml
|-- scripts/
|   |-- Scotia Fake Records.py
|   |-- check_setup.py
|   |-- publish_showcase.py
|   `-- build_validation_schema.py
|-- docs/
|   |-- setup.md
|   |-- index.html
|   |-- styles.css
|   |-- results.js
|   |-- results-data.md
|   |-- validation.html
|   |-- validation.js
|   |-- validation-config.js
|   |-- validation-report.md
|   |-- latest-pipeline.json
|   |-- controlled-pilot.md
|   |-- workflow.md
|   |-- publication.md
|   |-- privacy.md
|   `-- reporting/
|-- notebooks/
|   |-- 00_Create_Fabricated_SOURCE.py
|   |-- 01_Stat extraction _v1.ipynb
|   |-- 02_LLM Rule Generation.ipynb
|   |-- 03_Synthetic_Gen_v1.ipynb
|   |-- 04_Approval_Check.py
|   |-- 05_Validate_Run.py
|   |-- 06_Export_Report.py
|   `-- 07_Privacy_Check.py
|-- src/
|   `-- synthetic_banking/
|       |-- __init__.py
|       |-- artifacts.py
|       |-- config.py
|       |-- customer_relationships.py
|       |-- dates.py
|       |-- dependency_sampling.py
|       |-- fidelity.py
|       |-- generation.py
|       |-- generators.py
|       |-- marginal_profiles.py
|       |-- numeric_dependencies.py
|       |-- privacy.py
|       |-- privacy_checks.py
|       |-- privacy_sources.py
|       |-- profiles.py
|       |-- profiling.py
|       |-- profiling_run.py
|       |-- profiling_sql.py
|       |-- proposals.py
|       |-- relationship_profiles.py
|       |-- reporting.py
|       |-- rules.py
|       |-- showcase.py
|       |-- storage.py
|       |-- temporal.py
|       |-- validation.py
|       |-- validation_reporting.py
|       `-- workflow.py
`-- tests/
    |-- test_categorical_profiling.py
    |-- test_customer_relationships.py
    |-- test_dates.py
    |-- test_delinquency.py
    |-- test_dependency_regression.py
    |-- test_fidelity.py
    |-- test_numeric_dependencies.py
    |-- test_privacy.py
    |-- test_publication.py
    |-- test_refactor.py
    |-- test_results.cjs
    |-- test_reporting.py
    |-- test_rules.py
    |-- test_showcase.py
    |-- test_validation.py
    |-- test_validation_page.cjs
    |-- test_validation_reporting.py
    |-- test_workflow_wiring.py
    `-- test_workflow.py
```

[`AGENTS.md`](AGENTS.md) records repository guidance for Codex. Notebook 03 calls [`profiles.py`](src/synthetic_banking/profiles.py), [`generation.py`](src/synthetic_banking/generation.py), and [`storage.py`](src/synthetic_banking/storage.py); generation continues to use the controlled registry in [`rules.py`](src/synthetic_banking/rules.py).

## Local checks

Use Python 3.10+ (3.12 matches CI) and Node.js (22 matches CI). From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -B scripts/check_setup.py
$env:PYTHONPATH = (Resolve-Path -LiteralPath src).Path
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

The local requirements include NumPy, pandas, openpyxl, PyArrow and the publication schema validator; missing optional libraries can otherwise silently skip tests. Do not install this file over Databricks' managed runtime. The static showcase's dependency-free JavaScript checks run with Node:

```powershell
node --check docs/results.js
node --check docs/validation.js
node --test tests/test_results.cjs tests/test_validation_page.cjs tests/test_validation_explorer.cjs tests/test_executive_showcase.cjs tests/test_records.cjs tests/test_downloads.cjs tests/test_demo_release.cjs
```

The tests use fabricated inputs to check date distributions/nulls/order/repeatability, categorical statistics and limits, aggregate-only prompt context, provenance filtering, rule dispatch, generated output validation, and fidelity metrics/history. Refactor checks cover SOURCE selection, preflight, proposal batches, unchanged profiler aggregations/SQL/prompts, and generator parity with two pre-refactor fabricated baselines (six tables, audits, graph plan, and RNG state). Workflow/report checks cover approval stops, changed review metadata, strict handoffs, sanitized output and preservation of the last successful export. Privacy checks execute against fabricated rows in an in-memory SQL adapter and exercise overlap, copying, rarity, similarity, snapshot and release-guard behavior. Install pandas alongside NumPy to run all generator integration checks locally; those checks skip when pandas is unavailable. Databricks provides these runtime libraries. Verify bundle deployment, task values/repair, notebook execution and Delta/Volume writes separately in a Databricks test destination.

---

# Showcase boundary

The implemented static showcase explains methodology in `docs/index.html` and presents measured results in `docs/validation.html`. Validation uses sanitized aggregate reporting data; the overview separately loads a bounded, verified fabricated demo preview. Neither page connects directly to Databricks. The overview separately offers version-pinned GitHub Release links only for a matching verified, published DEMO_ONLY export; the current verified fabricated package is published. Missing evidence remains visible as unavailable/pending, and strengths/weaknesses are computed from measured results rather than editorial claims.

The Pages deployment includes only explicitly listed public HTML/CSS/JavaScript, the sanitized report, and, when enabled and verified, matching small preview/download metadata. Full dataset files use versioned GitHub Releases. Notebook outputs, internal fidelity/privacy reports, source/generated tables, credentials and documentation fixtures are not website assets. See the [public report contract](docs/reporting/README.md) and [publication boundary](docs/publication.md).

---

## Current Summary

The project already has:

```text
[✓] multi-table statistical profiler
[✓] numeric distribution profiling
[✓] categorical distribution profiling
[✓] null / quality profiling
[✓] date profiling
[✓] basic structural profiling
[✓] basic dependency profiling
[✓] Databricks LLM connection
[✓] structured LLM rule proposals
[✓] proposal batch and SOURCE-run provenance
[✓] individual proposal review with reviewer and timestamp
[✓] row-level synthetic generator
[✓] explicit SOURCE and GENERATED profiling modes
[✓] explicit SOURCE-profile selection in generator
[✓] generated account/balance snapshot join validation
[✓] per-metric SOURCE-vs-GENERATED fidelity reporting
[✓] reviewed proposals connected to the predefined balance rules
[✓] per-generation balance-rule audit and local tests

[✓] first approval-gated categorical and multivariate numeric sampling implementations, verified in a completed live pilot
[✓] aggregate-backed CUSTOMER_RELATIONSHIP generation, persistence and referential validation
[ ] broader dependency modeling
[✓] public validation report with calculated strengths/gaps, charts and transparent prototype tolerances
[ ] broader validation coverage and calibrated acceptance criteria
[✓] reusable Python modules with notebook orchestration
[✓] aggregate-only privacy screening with a separate row-level release guard
[✓] static HTML showcase, aggregate reporting and verified fabricated DEMO_ONLY Release downloads
[✓] successful controlled pilot, manual approval repair and reporting-only refresh
```
