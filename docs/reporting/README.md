# Public reporting contract, version 1.0

The final `reporting` workflow task writes **one** `latest-pipeline.json` in `report_output_dir/runs/<job-run-id>/`. It runs only after `validate` succeeds. This per-execution path lets GitHub retrieve the exact successful run's artifact without racing a later run. Interactive calls without `workflow_run_id` retain the original root location. The exporter rechecks saved generation versions, the exact SOURCE/batch/generation/GENERATED correspondence, the saved fidelity metrics and the generation-time rule audit. It does not pick a latest profiling run or use `current_run`.

- [Formal JSON Schema](pipeline-report.schema.json)
- [Complete fabricated example](example.json): illustrative values only, not measurements from a real pilot
- [Workflow deployment and approval instructions](../workflow.md)

An abbreviated shape is:

```json
{
  "schema_version": "1.0",
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
  "warnings": []
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

Only allowlisted field names, Y/N categories, fixed utilization buckets, aggregate values and fixed warning messages are emitted. No run/batch/proposal IDs, reviewer identities, row records, raw model responses, free-form reasons, arbitrary category values, credentials or file paths appear in the JSON. These are selected aggregates, not a formal privacy guarantee or a privacy-test result.

The exporter builds and serializes the payload before replacing the previous file. A validation/build/write failure preserves the existing successful artifact. An older validation completion timestamp cannot replace a newer report. Keep one workflow writer per destination and smoke-test file replacement on the intended Databricks Volume. The schema version changes when the public contract changes incompatibly. No website files or rendering logic are changed by this task.

## Locate the result

Set bundle variable `report_output_dir` to an absolute writable Volume directory, for example `/Volumes/workspace/default/scotia/pipeline_reporting`. After the workflow's `reporting` task succeeds, the artifact is:

```text
/Volumes/workspace/default/scotia/pipeline_reporting/runs/<job-run-id>/latest-pipeline.json
```

The task returns that path as a notebook-exit receipt and task value. Download the JSON through Databricks Catalog Explorer when needed. A failed or approval-blocked execution leaves prior successful reports in place. The [GitHub publication workflow](../publication.md) verifies job success, retrieves this exact file, updates `docs/latest-pipeline.json` and deploys the static site. See [the webpage field reference and preview instructions](../results-data.md).
