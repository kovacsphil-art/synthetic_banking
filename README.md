# RCAR Synthetic Data Generation

## Project Overview

This repository contains a Databricks-based prototype for profiling banking-style relational data and using those profiles to generate statistically similar synthetic records.

The project is being developed as a controlled synthetic-data pipeline rather than a direct row-copying or record-memorization system. The intended architecture is:

```text
Source / development data
        |
        v
Statistical profiling
        |
        v
Aggregate metadata and relationships
        |
        v
LLM dependency + rule proposer
        |
        v
Reviewed / approved generation rules
        |
        v
Synthetic-data generator
        |
        v
Generated relational tables
        |
        v
Re-profile and compare against source
```

The long-term goal is to turn the work into a reproducible Git project and eventually create an HTML-based portfolio/demo that explains the architecture, methodology, AI component, generation process, and source-vs-generated validation results.

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

The notebook currently begins by loading development/test Parquet files from:

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

The purpose of these views is to let the profiling code remain stable when the underlying development source is later replaced.

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

The intended `profile_type` values are:

```text
SOURCE
GENERATED
```

This distinction is important because source profiles should be retained while later generated datasets are re-profiled for comparison.

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

The profiler also records structural distributions such as:

```text
ACCOUNTS_PER_PARTY
```

### Published views

Current-run convenience views include:

```text
v_numeric_statistics
v_category_statistics
v_structural_statistics
v_dependency_statistics
```

The notebook also contains a SOURCE-vs-GENERATED numeric comparison using mean, P25, P50, P75, and P95 percentage differences.

### Important run-management note

At the time this README was created, the notebook cell that starts a profiling run inserts:

```text
profile_type = 'GENERATED'
```

This is appropriate when profiling generated output, but the baseline source run must exist separately as `SOURCE`.

Do not assume `current_run` always represents the source dataset.

The LLM stage explicitly searches for the most recent completed `SOURCE` run.

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

The current AI context includes:

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
standard deviation
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

### Structured output

The LLM response is constrained using JSON Schema.

The JSON response is parsed with `FROM_JSON()` and exploded into individual rules.

Rules are stored in:

```text
workspace.synthetic_profile.ai_rule_proposals
```

with an additional:

```text
approval_status
```

field.

### Current approval behavior

The final active approval cell currently sets all proposals to:

```text
APPROVED
```

This is useful for development/testing, but approval should eventually be more selective if the pipeline is used in a governed environment.

### Important current limitation

**These approved LLM rules are not yet used by Notebook 03.**

The rule-proposal stage currently ends after storing/approving proposals.

There is no existing connection from:

```text
ai_rule_proposals
```

to:

```text
03_Synthetic_Gen_v1.ipynb
```

That is the primary next implementation goal.

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

The generator currently loads:

```text
v_numeric_statistics
v_category_statistics
date_profile
column_quality
v_dependency_statistics
v_structural_statistics
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

Each generated column receives nulls using the profiler's observed:

```text
null_pct
```

except protected identifier/key fields.

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

with a fallback if no profile is available.

### Account-generation logic currently hard-coded

The generator currently includes manually implemented account dependencies.

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

and samples delinquency using the observed outcome rate for the bucket.

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

### Schema completion

Before writing results, `add_missing_columns()` checks `column_inventory` and adds missing expected source columns as nulls.

This helps maintain schema compatibility with the profiler/source aliases.

### Outputs

Generated DataFrames are written to Delta tables under:

```text
workspace.default
```

The notebook also contains ZIP logic for CSV outputs expected under:

```text
/Volumes/workspace/default/scotia/generated_row_level
```

The current ZIP cell assumes those CSV files already exist; the notebook itself does not currently contain the CSV export step.

---

# Current End-to-End State

The project currently has three functioning conceptual stages:

```text
01 Statistical Profiler
        |
        v
02 LLM Rule Proposer
        |
        X   <-- connection not implemented yet
        |
        v
03 Synthetic Generator
```

The highest-priority development task is to connect stages 02 and 03 safely.

---

# Next Development Goal for Codex

## Implement approved AI rules in the synthetic generator

The generator should read:

```text
workspace.synthetic_profile.ai_rule_proposals
```

and use only rules where:

```text
approval_status = 'APPROVED'
```

However, **do not directly execute the `proposed_rule` text returned by the LLM.**

In particular:

- Do not use Python `eval()`.
- Do not use `exec()`.
- Do not dynamically execute arbitrary SQL or Python written by the model.
- Do not allow the LLM to directly mutate generated records.

Instead, implement a controlled rule registry.

Conceptually:

```python
RULE_IMPLEMENTATIONS = {
    ("TKQ_ACCOUNT_BALANCE", "AVAILABLE_TO_BUY_AMT", "DERIVED"):
        apply_available_to_buy_rule,

    ("TKQ_ACCOUNT_BALANCE", "OVERLIMIT_AMT", "DERIVED"):
        apply_overlimit_rule,

    ("TKQ_ACCOUNT", "PAST_DUE_INDICATO_CD", "CONDITIONAL"):
        apply_delinquency_rule,
}
```

The generation process should then:

1. Load approved rules.
2. Match approved proposals to supported rule implementations.
3. Generate parent/base variables first.
4. Apply supported approved rules in a deterministic order.
5. Log which approved rules were applied.
6. Log approved rules that do not yet have an implementation.
7. Never silently execute an unknown LLM rule.
8. Preserve the ability to generate without an LLM rule if the rule is not approved or not implemented.

A useful status model would be:

```text
APPROVED + IMPLEMENTED -> apply
APPROVED + NOT IMPLEMENTED -> log / skip
PENDING -> do not apply
REJECTED -> do not apply
```

---

# Important Profile-Run Issue to Address

Notebook 03 currently gets:

```python
run_id = spark.table(
    "workspace.synthetic_profile.current_run"
)
```

and loads several convenience views that are also filtered to `current_run`.

This is potentially fragile.

The generator should ideally be based on the **latest completed SOURCE run**, not simply whichever profiling run is currently active.

Codex should consider refactoring profile loading so generation explicitly identifies:

```text
latest completed SOURCE run_id
```

and loads all generation profiles for that run.

This prevents the generator from accidentally learning from a previously generated dataset.

---

# Desired Generation Architecture

The target flow is:

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
Load APPROVED AI rule proposals
            |
            v
Generate base entities and parent variables
            |
            v
Controlled rule registry
            |
            v
Apply supported dependency rules
            |
            v
Complete remaining fields
            |
            v
Schema validation
            |
            v
Write generated Delta tables
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

- `03_Synthetic_Gen_v1.ipynb` does not yet use `ai_rule_proposals`.
- The AI stage currently examines only `TKQ_ACCOUNT` and `TKQ_ACCOUNT_BALANCE`.
- Most fields are still generated independently from marginal distributions.
- Numeric inverse-CDF generation is based on a limited set of percentile knots.
- Dates are generated uniformly between observed minimum and maximum dates.
- Categorical-to-categorical dependencies are not yet systematically modeled.
- Only a small number of numeric/conditional dependencies are profiled.
- `CUSTOMER_RELATIONSHIP` generation is not implemented.
- `CUSTOMER_RELATIONSHIP` is not currently saved in the Delta output section.
- The ZIP step assumes row-level CSV files already exist.
- Run selection should be made explicitly SOURCE-aware before further automation.
- The current blanket `APPROVED` update in Notebook 02 is primarily a development convenience, not a final governance design.

---

# Suggested Near-Term Work

Prioritize work in roughly this order:

1. Make Notebook 03 explicitly load the latest completed `SOURCE` run.
2. Load approved AI rule proposals in Notebook 03.
3. Create the controlled rule registry.
4. Convert the existing manually coded balance and delinquency logic into named rule functions.
5. Apply those functions only when the corresponding rule is approved.
6. Add logging for applied/skipped/unimplemented rules.
7. Re-run the profiler on generated data as `GENERATED`.
8. Expand SOURCE-vs-GENERATED validation beyond numeric quantiles.
9. Implement `CUSTOMER_RELATIONSHIP`.
10. Refactor reusable notebook logic into Python modules once behavior is stable.

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

# Eventual Repository Direction

As the project stabilizes, reusable code should gradually move out of notebooks.

A possible future structure is:

```text
rcar-synthetic-data/
|
|-- README.md
|-- notebooks/
|   |-- 01_Stat extraction _v1.ipynb
|   |-- 02_LLM Rule Generation.ipynb
|   `-- 03_Synthetic_Gen_v1.ipynb
|
|-- src/
|   |-- profiling/
|   |-- generation/
|   |-- rules/
|   `-- validation/
|
|-- tests/
|
|-- config/
|
`-- docs/
    `-- eventual HTML project showcase
```

The notebooks can remain the Databricks orchestration layer while `src/` becomes the reusable/testable implementation layer.

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
[✓] rule approval table
[✓] row-level synthetic generator
[✓] source/generated run concept
[✓] basic source-vs-generated numeric validation

[ ] approved LLM rules connected to generator
[ ] controlled rule execution registry
[ ] robust explicit SOURCE-profile selection in generator
[ ] systematic AI rule application logging
[ ] CUSTOMER_RELATIONSHIP generation
[ ] broader dependency modeling
[ ] broader validation dashboard/report
[ ] modular Python package structure
[ ] HTML portfolio showcase
```

The immediate goal is therefore **not to redesign the pipeline**. It is to connect the existing LLM rule-proposal stage to the existing generator in a safe, explicit, auditable way.
