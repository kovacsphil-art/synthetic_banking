# Public reporting contract, version 2.0

Version 2 preserves the original summary fields and adds `validation_report`, a fixed aggregate-only projection for the dedicated [Validation Report](../validation.html). Its numeric chart, detailed tables, prototype tolerances, calculated strengths and ranked weaknesses are documented in [validation-report.md](../validation-report.md). Version-1 reports remain supported by the short showcase panel and publication workflow; the detailed page displays pending until version 2 is supplied. The old schema/example are retained with a `-v1` suffix.

The final `reporting` workflow task writes **one** `latest-pipeline.json` in `report_output_dir/runs/<job-run-id>/`. It runs only after `validate` succeeds. This per-execution path lets GitHub retrieve the exact successful run's artifact without racing a later run. Interactive calls without `workflow_run_id` retain the original root location. The exporter rechecks saved generation versions, the exact SOURCE/batch/generation/GENERATED correspondence, the saved fidelity metrics and the generation-time rule audit. It does not pick a latest profiling run or use `current_run`.

- [Formal JSON Schema](pipeline-report.schema.json)
- [Complete fabricated example](example.json): illustrative values only, not measurements from a real pilot
- [Workflow deployment and approval instructions](../workflow.md)

An abbreviated shape is:

```json
{
  "schema_version": "2.0",
  "pipeline_completed_at": "2026-01-01T12:00:00Z",
  "generation": {
    "total_rows": {"status": "AVAILABLE", "value": 8200, "reason": null},
    "customers": {"status": "AVAILABLE", "value": 1000, "reason": null},
    "accounts": {"status": "AVAILABLE", "value": 1400, "reason": null},
    "table_rows": []
  },
  "rules": {},
  "validation": {"status": "PASS", "fidelity_acceptance": "NOT_CONFIGURED"},
  "numeric_differences": [],
  "categorical_differences": [],
  "dependency_results": {},
  "warnings": [],
  "validation_report": {}
}
```

The abbreviated shape omits required members and array entries; use `example.json` for the complete contract.

## Field semantics

| Field | Meaning |
| --- | --- |
| `pipeline_completed_at` | UTC completion time passed by this execution's successful validation task; stable across reporting retries |
| `generation.total_rows` | Sum of rows across all six output tables; unavailable if any table count is missing |
| `generation.customers`, `accounts` | Generated PERSON and TKQ_ACCOUNT row counts, respectively |
| `generation.table_rows` | One fixed entry per generated table, including CUSTOMER_RELATIONSHIP |
| `rules` | Proposal, reviewed-approval, actual-application, skip and approved-without-implementation counts from this generation's audit; legacy fallback rows do not count as AI applications |
| `validation.status` | PASS means saved generation validation and generated integrity checks succeeded; failed runs do not replace the latest successful report |
| `validation.fidelity_acceptance` | NOT_CONFIGURED: no statistical acceptance score or new thresholds are inferred |
| `account_balance_join_coverage` | Generated account rows with a balance and balance rows with an account, using snapshot join keys; values are fractions in [0, 1] |
| `numeric_differences` | Mean/P50/P95 for credit limit, current balance, available-to-buy and overlimit; differences use native numeric units |
| `categorical_differences` | Y/N past-due proportions only; no arbitrary category labels are exported |
| `dependency_results` | Credit-limit/balance Pearson comparison and five utilization-bucket delinquency rate comparisons |
| `warnings` | Fixed, sanitized messages about unavailable metrics, skipped/unsupported rules and absent fidelity thresholds |

Comparisons use the pinned SOURCE and GENERATED profiles. Differences are **GENERATED minus SOURCE**. Proportion/rate differences use **percentage points**, while source/generated rates and join coverage remain fractions. Counts and individual metrics have explicit AVAILABLE/UNAVAILABLE states and null values/reasons when missing. Missing optional metrics do not crash reporting. Missing or inconsistent validation/provenance evidence does fail reporting.

Only allowlisted field names, Y/N categories, fixed utilization buckets, aggregate values and fixed warning messages are emitted. No run/batch/proposal IDs, reviewer identities, row records, raw model responses, free-form reasons, arbitrary category values, credentials or file paths appear in the JSON. Selected fidelity aggregates are not privacy clearance. The optional `privacy` section separately reports lightweight screening results, without a formal guarantee.

The exporter builds and serializes the payload before replacing the previous file. A validation/build/write failure preserves the existing successful artifact. An older validation completion timestamp cannot replace a newer report. Keep one workflow writer per destination and smoke-test file replacement on the intended Databricks Volume. The schema version changes when the public contract changes incompatibly. Rendering is separate from export; the post-pilot webpage consumes the documented optional extensions.

## Optional dependency-fidelity extension

Version 2.0 additionally permits `validation_report.dependency_fidelity`. Historical version-2 artifacts without it remain valid. It uses fixed relationship labels, never raw category values or run IDs:

| JSON member | Shape / units |
| --- | --- |
| `categorical[]` | Exactly two entries: `key` = `account_type_product` or `client_tsys_product`; fixed corresponding `label` |
| `categorical[].source_cramers_v`, `generated_cramers_v`, `absolute_association_gap` | Number in [0,1] or null |
| `categorical[].source_n`, `generated_n` | Nonnegative complete-case integer count or null |
| `categorical[].conditional_tvd_pct` | Number in [0,100] or null; per-parent total variation weighted by SOURCE parent counts |
| `categorical[].unsupported_combination_rate` | Fraction in [0,1] or null; generated complete cases with no positive SOURCE cross-tab count |
| `numeric_segments[]` | Exactly four entries with `bucket` = Q1/Q2/Q3/Q4, using the pinned SOURCE credit-limit intervals |
| `numeric_segments[].source_mean`, `generated_mean`, `mean_difference` | Balance means and GENERATED-minus-SOURCE difference in native units, or null; mismatched interval boundaries leave the difference null |
| `numeric_segments[].source_n`, `generated_n` | Nonnegative finite-pair integer count or null |

The object is omitted when neither selected evidence family is present. Unavailable measurements are null, not fabricated zeroes. Categorical distances appear in the dependencies section and receive supplemental provisional screening when `post_pilot` is present; they stay outside legacy headline counts. Numeric segments retain a detail disclosure. Top-level `rules` totals include new proposal applications; the existing three-entry `rule_outcomes` selection remains unchanged, and full per-target execution detail stays in the internal audit. Raw per-cell conditional comparisons and all numeric segment quantiles remain available internally in `fidelity_metrics`. See [method details and before/after limitations](../statistical-fidelity-phase1.md).

## Post-pilot public fields

Version 2.0 permits two optional, closed extensions. Historical artifacts without them remain valid. Missing metrics are null/UNAVAILABLE; examples are fabricated and never substituted for live results. [`example-postpilot.json`](example-postpilot.json) documents the full shape. The [post-pilot review](../post-pilot-review.md) documents interpretation and provisional thresholds.

| JSON path | Contract |
| --- | --- |
| `validation_report.post_pilot.policy_version`, `provisional` | `post_pilot_v1`, `true` |
| `…thresholds` | Fixed mean-relative, zero-mean-absolute, tail-IQR, conditional-TVD and date-bound policies; `strong` / `acceptable` numeric limits |
| `…integrity_requirements`, `min_conditional_rows` | Snapshot coverage 1, allowed violations 0, minimum conditional count 30 |
| `…assessments[]` | Exactly 13 fixed keys: four `mean.*`, four `tail.*`, three `date_bounds.*`, two `categorical_conditional.*`; fixed label/family/policy/status, nullable SOURCE/generated/difference/score/sample sizes |
| `…numeric_details[]` | Four fixed numeric variables: relative mean gap; SOURCE/generated minimum, maximum, stddev; `tail_points[]` P01/P05/P99 with nullable SOURCE/generated/signed difference |
| `…strengths`, `weaknesses`, `zero_reference_alerts` | Fixed assessment keys only; no editorial free text or combined score |
| `privacy.status` | PASS / REVIEW_REQUIRED / BLOCKED / UNAVAILABLE; independent of integrity and fidelity |
| `privacy.row_level_downloads_enabled`, `formal_anonymization_certified` | Always `false` |
| `privacy.policy_version`, `policy` | `basic_v1` and saved `rare_min_count`, `max_synthetic_rare_fraction`, `min_complete_fraction`, `near_date_days`, `max_similarity_candidates`; null when unavailable |
| `privacy.checks_recorded`, `checks_expected` | Nullable aggregate counts, not IDs |
| `privacy.identifier_overlap_rows`, `exact_source_row_matches` | Nullable aggregate flagged counts |
| `privacy.near_matches` | Fixed `variables` BIRTH_DT/SINCE_DT/GENDER_CD; nullable `evaluated_rows`, `flagged_rows`, `flagged_fraction`, `minimum_combined_distance_days`, `complete_case_coverage` |
| `privacy.categorical_patterns[]` | Exactly three fixed keys/labels: customer_category, employment, account_product; status, nullable evaluated rows, `synthetic_rare_rows`, `source_rare_match_rows`, complete-case coverage |

Counts and distances remain separate from risk conclusions. SOURCE-rare matches are not the same as patterns rare within the synthetic population. Fractions use [0,1], percentage scores use [0,100] where applicable, mean values use native units, and date distances use days. No matching values, raw category combinations, exact personal dates, IDs, policy hashes or record samples are public.

Notebook 06 receives `privacy_assessment_id` from the exact privacy task; workflow mode requires it. `privacy_reporting.py` verifies the assessment's SOURCE/generation, completion, saved policy and dataset snapshots before projecting allowlisted aggregates. The identifier is never exported. Incomplete evidence cannot turn a privacy assessment into clearance. This does not activate or bypass the row-release guard.

## Locate the result

Set bundle variable `report_output_dir` to an absolute writable Volume directory, for example `/Volumes/workspace/default/scotia/pipeline_reporting`. After the workflow's `reporting` task succeeds, the artifact is:

```text
/Volumes/workspace/default/scotia/pipeline_reporting/runs/<job-run-id>/latest-pipeline.json
```

The task returns that path as a notebook-exit receipt and task value. Download the JSON through Databricks Catalog Explorer when needed. A failed or approval-blocked execution leaves prior successful reports in place. The [GitHub publication workflow](../publication.md) verifies job success, retrieves this exact file, updates `docs/latest-pipeline.json` and deploys the static site. See [the webpage field reference and preview instructions](../results-data.md).
