# RCAR Synthetic Data Generation

## Project Overview

This repository contains a Databricks-based prototype for profiling banking-style relational data and using those profiles to generate statistically similar synthetic records.

The workflow starts from a completed SOURCE profile:

```text
01  SOURCE profile
    ├─ 03  Synthetic generation → 01  GENERATED profile → SOURCE vs GENERATED comparison
    └─ 02  LLM proposal batch → Individual review → 03  Controlled balance-rule pilot
```

Notebook 03 uses the selected SOURCE statistics and predefined Python formulas. Reviewed proposals can select two existing balance rules, and generation falls back to the legacy path when a target has no unique eligible approval. See [local checks](#local-checks) for the Python pilot.

## How to Run

1. Open the repo in Databricks and configure compute, permissions, and source paths using the [Notebook 01 prerequisites](notebooks/01_Stat%20extraction%20_v1.ipynb).
2. Set `profile_type` to `SOURCE` in Notebook 01 and run it from the top. Record the completed SOURCE `run_id` from `workspace.synthetic_profile.profile_runs`.
3. Set Notebook 02's `source_run_id` to that ID and set `balance_pilot` to `ON` for the controlled pilot. Run the notebook and record the proposal `batch_id`.
4. Review the batch and approve individual proposals using the [controlled pilot runbook](docs/controlled-pilot.md).
5. Set Notebook 03's `source_run_id` to the same SOURCE ID. For the pilot, fill in `pilot_batch_id` and `pilot_proposal_ids`. Run through the Delta-save and validation cell and record the `generation_id`.
6. Rerun Notebook 01 with `profile_type` set to `GENERATED` and the recorded `generation_id`. Review the comparison against the original SOURCE run.

### Optional setup for fake SOURCE inputs

Run [Scotia Fake Records.py](scripts/Scotia%20Fake%20Records.py) as a Databricks notebook before step 2 if you need to create the six input Parquet files. It generates fake records from the column names and types in `RCAR_source_column_list.xlsx`. The workbook is required separately and defaults to `/Volumes/workspace/default/scotia/RCAR_source_column_list.xlsx`.

Set `SCHEMA_XLSX` and `OUTPUT_DIR` for your workspace. The output directory must be writable and should match Notebook 01's `source_dir`. The script replaces existing `RCAR_synthetic_*.parquet` files with the same names, so use a test Volume if those files need to be kept. The generator uses NumPy, pandas, openpyxl, and PyArrow.

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

The project currently consists of three main Databricks notebooks.

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

The bronze views remain the SOURCE aliases. In `GENERATED` mode, Notebook 01 reads the five generated Delta tables from `workspace.synthetic_generated`. It requires a completed generation record and all five tables before starting a profiling run.

### Profiling schema

Profiler outputs are stored under:

```text
workspace.synthetic_profile
```

Important objects include:

```text
source_config
profile_runs
current_run
column_inventory
column_quality
numeric_profile
category_profile
date_profile
relationship_profile
conditional_profile
cardinality_profile
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

#### Date profiles

```text
non-null count
earliest date
latest date
```

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

The current dependency profiling is intentionally limited.

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

The notebook also contains a SOURCE-vs-GENERATED numeric comparison using mean, P25, P50, P75, and P95 percentage differences.

### Execution order

Run these steps serially on Databricks compute with Python and SQL support. The notebooks need access to the development Parquet files and permission to create or write the relevant schemas and tables.

Run Notebook 03 and GENERATED mode of Notebook 01 from a Databricks Git folder containing `notebooks/` and `src/` in the same checkout. If a notebook cannot discover the Git root, add the absolute path to the checkout's `src/` directory to the Python path before running it. [Databricks workspace module imports](https://docs.databricks.com/aws/en/files/workspace-modules)

1. **Profile SOURCE.** Run Notebook 01's widget cell, select `SOURCE` in `profile_type`, and run the notebook from the top. For a Databricks job, pass `profile_type=SOURCE`. Confirm that the run is `COMPLETED` in `workspace.synthetic_profile.profile_runs`.
2. **Generate synthetic data.** Run Notebook 03 through its Delta-save cell. It pins the latest completed SOURCE run, saves a new batch to `workspace.synthetic_generated`, and validates the saved outputs. The batch is ready when `generation_state` reports `COMPLETED` and contains the validated table versions.
3. **Profile GENERATED.** Rerun Notebook 01 from the top with `profile_type=GENERATED`. It checks the validation record against the current Delta tables, then records aggregates for the five generated tables under a separate run ID. `CUSTOMER_RELATIONSHIP` is only profiled in SOURCE mode.
4. **Compare.** Review the final numeric comparison in the GENERATED run of Notebook 01. It compares that profile with the exact SOURCE run used by Notebook 03.

To exercise the rule pilot, follow the [controlled pilot runbook](docs/controlled-pilot.md). It pins one SOURCE run, one proposal batch, one or two manually reviewed approvals, and the generated batch that Notebook 01 profiles.

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
```

Currently the AI stage is scoped to:

```text
TKQ_ACCOUNT
TKQ_ACCOUNT_BALANCE
```

It does **not** yet analyze all six logical tables.

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

Notebook 02 pins the completed `source_run_id` supplied in its widget, or selects the latest completed SOURCE run when the widget is blank. It assigns a new `batch_id`, builds the prompt from that run's quality, numeric, and categorical profiles, and freezes the prompt and its IDs before calling the model. It requires aggregate column profiles for both account tables. Each run from the top creates a separate batch, even when the SOURCE run is the same.

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

The null-sampling pass uses the selected SOURCE run's `null_pct` where applied. Protected identifiers and account snapshot keys retain their generated values. PERSON dates are generated after its null-sampling pass, and TKQ_ACCOUNT has no generic null-sampling pass.

### Date generation

Dates are currently sampled uniformly between:

```text
earliest_date
latest_date
```

This preserves the observed range but does not reproduce the full source date distribution.

There is a basic PERSON constraint ensuring:

```text
SINCE_DT >= BIRTH_DT
```

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

### Delinquency logic currently hard-coded

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

and samples delinquency using the observed outcome rate for the bucket, with a 5% fallback for an absent bucket.

`DELINQUENCY_CNT` is then conditioned on whether the synthetic account was sampled as delinquent.

This logic existed before the LLM rule-proposal stage and is **not currently activated by an approved LLM rule**.

### Remaining fields

`fill_profiled_fields()` fills remaining categorical, numeric, and date fields using their univariate profiles and then applies profiled null rates.

### Current cross-table generation

Currently generated tables include:

```text
PERSON
CUSTOMER_ACCOUNT_REL
TKQ_ACCOUNT
TKQ_ACCOUNT_BALANCE
TRADELINES
```

A `CUSTOMER_RELATIONSHIP` DataFrame is created, but it is currently empty and relationship generation has not yet been implemented.

At the time of this README, the Delta save section also does not save `CUSTOMER_RELATIONSHIP`.

Notebook 03 creates one account and one balance row per synthetic `ACCOUNT_ID`. It samples a single non-null `BUSINESSEFFECTIVEDATE` per account from the selected SOURCE run's balance date bounds, with the account date bounds as a fallback. Generation requires usable bounds on at least one side. The date is copied by account ID so both rows share the profiler's composite snapshot key.

### Schema completion

Before writing results, Notebook 03 takes expected columns from the pinned SOURCE run's quality profile and fills missing fields with typed nulls. This retains optional fields for profiling. The saved tables must independently pass schema, key, count, and invariant checks.

### Outputs

Generated DataFrames are written to Delta tables under:

```text
workspace.synthetic_generated
```

Notebook 03 records the generation ID and its SOURCE profile ID in `generation_state`. It sets the state to `RUNNING` before writing the tables and to `COMPLETED` after the saved data and audit pass validation.

The notebook also contains ZIP logic for CSV outputs expected under:

```text
/Volumes/workspace/default/scotia/generated_row_level
```

The current ZIP cell assumes those CSV files already exist; the notebook itself does not currently contain the CSV export step.

### Generated batch validation

[`validation.py`](src/synthetic_banking/validation.py) checks the saved Delta tables and rule audit:

- Required columns and compatible types for the pinned SOURCE schema and generated keys and rule fields. Account and balance snapshot dates must have the same type.
- Saved row counts against the generation plan. Generated person, account, and tradeline keys must match their assigned sequences. Links must reference the corresponding generated parent keys.
- Full one-to-one account and balance join coverage on `ACCOUNT_ID` and `BUSINESSEFFECTIVEDATE`.
- Existing derived rules for available credit, overlimit, the balance cap, utilization, delinquency flag and count, and PERSON date order.
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

## Rule execution audit

Notebook 03 appends one audit row per considered proposal and a separate row for each legacy formula used to fill a target. Rows in `workspace.synthetic_generated.rule_execution_log` include `generation_id`, `source_run_id`, `seed`, proposal `batch_id` and `proposal_id`, target table and column, rule type, parent columns, and the approval status read for that run.

| Field | Meaning |
| --- | --- |
| `proposed` | The row refers to an LLM proposal. |
| `approved` | The proposal was approved and has valid review and batch provenance. |
| `implemented` | A predefined implementation matches the rule metadata and parents. |
| `applied` | The proposal selected an implementation that generated values for at least one row. |

`outcome` distinguishes `APPLIED`, `SKIPPED`, and `LEGACY_FALLBACK`. Common skip reasons include `not_approved` for pending or rejected proposals, `unverified_approval` for an approval without valid provenance, and `no_implementation` for unsupported rule targets or types. The audit also records the implementation name, execution order, and rows processed where applicable. A legacy fallback can supply values for a target while its proposal is recorded as skipped.

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

- The controlled registry covers the two balance formulas. Utilization and delinquency use their existing generation paths, with delinquency rates taken from the selected SOURCE profile.
- The AI stage currently examines only `TKQ_ACCOUNT` and `TKQ_ACCOUNT_BALANCE`.
- Most fields are still generated independently from marginal distributions.
- Numeric inverse-CDF generation is based on a limited set of percentile knots.
- Dates are generated uniformly between observed minimum and maximum dates.
- Categorical-to-categorical dependencies are not yet systematically modeled.
- Only a small number of numeric/conditional dependencies are profiled.
- `CUSTOMER_RELATIONSHIP` generation is not implemented.
- `CUSTOMER_RELATIONSHIP` is not currently saved in the Delta output section.
- The ZIP step assumes row-level CSV files already exist.

---

# Suggested Near-Term Work

Prioritize work in roughly this order:

1. Exercise the reviewed balance-rule pilot end to end in Databricks and compare its output with a legacy run.
2. Extend the registry to additional existing dependencies, starting with utilization and delinquency.
3. Expand SOURCE-vs-GENERATED validation beyond numeric quantiles.
4. Implement `CUSTOMER_RELATIONSHIP`.
5. Refactor reusable notebook logic into Python modules once behavior is stable.

---

# Validation Direction

The same profiler should be used for both source and generated records.

Validation should eventually compare:

```text
numeric distributions
categorical proportions
null rates
date ranges/distributions
cardinalities
correlations
conditional outcome rates
cross-table relationships
business-rule violations
```

The goal is not for every statistic to be exactly equal.

The goal is for the synthetic data to preserve the important statistical and structural properties required for the intended downstream use while remaining newly generated data.

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
|-- docs/
|   `-- controlled-pilot.md
|-- notebooks/
|   |-- 01_Stat extraction _v1.ipynb
|   |-- 02_LLM Rule Generation.ipynb
|   `-- 03_Synthetic_Gen_v1.ipynb
|-- src/
|   `-- synthetic_banking/
|       |-- __init__.py
|       |-- rules.py
|       `-- validation.py
`-- tests/
    |-- test_rules.py
    `-- test_validation.py
```

[`AGENTS.md`](AGENTS.md) records repository guidance for Codex. Notebook 03 imports the loader, registry, and predefined functions from [`rules.py`](src/synthetic_banking/rules.py).

## Local checks

With Python 3.10 or newer and NumPy installed, run from the repository root in PowerShell:

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath src).Path
python -B -m unittest discover -s tests -v
```

The tests use fabricated inputs to check provenance filtering, rule dispatch, and generated output validation. Verify notebook execution and Delta writes separately in a Databricks test destination.

---

# Intended Portfolio / HTML Showcase

The eventual HTML version should explain the project without publishing sensitive source records.

Potential sections:

```text
Problem / motivation
System architecture
Statistical profiler
AI-assisted dependency discovery
Controlled rule approval
Synthetic generation methodology
Relational structure
Source-vs-generated validation
Limitations
Future work
```

Public-facing outputs should use aggregate results, diagrams, code excerpts, and fabricated/example records rather than real row-level banking data.

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
[✓] basic source-vs-generated numeric validation
[✓] reviewed proposals connected to the predefined balance rules
[✓] per-generation balance-rule audit and local tests

[ ] controlled implementations for additional dependencies
[ ] CUSTOMER_RELATIONSHIP generation
[ ] broader dependency modeling
[ ] broader validation dashboard/report
[ ] modular Python package structure
[ ] HTML portfolio showcase
```
