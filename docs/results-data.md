# Showcase results: JSON field reference

The optional post-pilot fields populate measured mean bars, tail/conditional/boundary tables and a **separate privacy summary**. See the [exact field contract](reporting/README.md#post-pilot-public-fields) and [fabricated example](reporting/example-postpilot.json). Historical reports remain supported; absent fields are unavailable. The current privacy status is REVIEW_REQUIRED and row downloads remain disabled. No internal identifiers or matching records are rendered.

The SAGE static site loads **`latest-pipeline.json` beside `index.html`** using `showcase.js` and the shared checks in `results.js` / `validation.js`. Hero counts, distribution comparisons and executive findings are measured results; architecture, methodology and review explanations remain static. The dedicated validation page evaluates final-cohort statistical/structural similarity, independently of rule approvals or application counts. It displays no overall accuracy score. No browser connection to Databricks, credentials, framework or build step is required.

The executive pages require version 2.0, including `validation_report`; see [the field, chart and policy reference](validation-report.md). The legacy summary normalizer and publisher retain version-1 compatibility. Version 1 cannot populate the executive pages and produces an unavailable/pending state.

## Publish results

For automatic GitHub repository updates and Pages deployment after successful Databricks runs, configure the [publication workflow](publication.md). Manual copying remains available for local previews:

1. Complete the Databricks workflow through validation and reporting.
2. Download **only the sanitized** `latest-pipeline.json` from the reporting task's output path and copy it to `docs/latest-pipeline.json`. Automated runs use `report_output_dir/runs/<job-run-id>/latest-pipeline.json`. Do not use the internal `fidelity_report.json` or raw Delta exports.
3. Preview locally. The GitHub publication workflow handles repository updates and Pages after it is configured.
4. Refresh the page or choose **Refresh validation report** on the detailed page. The completion timestamp identifies the validated export being displayed.

The published report is the sanitized output of a completed validated execution. Missing/invalid files show unavailable states. The [fabricated contract example](reporting/example.json) is documentation; the page never loads it automatically.

For local preview from the repository root:

```powershell
python -m http.server 8000 --bind 127.0.0.1 --directory docs
```

Open `http://127.0.0.1:8000/#validation`. Double-clicking `index.html` still shows the methodology, but browsers generally restrict JSON fetching from `file://`; use the server to load results.

The default relative filename also works under a GitHub Pages project subpath. For a different same-origin relative location, update `data-report-url` on `#executive-results` in `index.html` and `#validation-report` in `validation.html`. Keep the report public and sanitized; cross-origin URLs, credential-bearing requests and redirects are not used. Responses are requested without cached data or cookies, with a 10-second timeout and a 1 MiB payload limit.

## Exact fields consumed

The summary fields below are shared by [version 1](reporting/pipeline-report-v1.schema.json) and [version 2](reporting/pipeline-report.schema.json). The required envelope is `schema_version = "1.0"` or `"2.0"`, a valid timezone-aware ISO timestamp in `pipeline_completed_at`, objects `generation`, `rules`, `validation`, and `validation.status = "PASS"`, `validation.fidelity_acceptance = "NOT_CONFIGURED"`. Version 2 additionally requires the documented `validation_report` extension. Unknown schema versions, failed validation, malformed envelopes/timestamps, duplicate selected measurements, and contradictory rule counts produce **Latest results unavailable**.

Individual missing or unusable metrics show **Unavailable**. Count/coverage objects use `status` and `value`. An AVAILABLE count must be a nonnegative safe integer; coverage must be a finite fraction between 0 and 1. The count objects' `reason` field is not displayed.

| JSON field | Display |
| --- | --- |
| `schema_version` | Compatibility check; `"1.0"` and `"2.0"` are supported |
| `pipeline_completed_at` | Validated completion date/time, formatted in UTC |
| `generation.customers.{status,value}` | Customers metric |
| `generation.accounts.{status,value}` | Accounts metric |
| `generation.total_rows.{status,value}` | Generated rows across the six tables |
| `generation.table_rows[].{table,status,value}` | Output-population row-count detail; fixed table labels below |
| `rules.proposed.{status,value}` | Rules proposed |
| `rules.approved.{status,value}` | Rules approved |
| `rules.applied.{status,value}` | Rules actually applied |
| `rules.skipped.{status,value}` | Skipped proposal count in rule details |
| `rules.approved_unimplemented.{status,value}` | Approved-without-implementation count in rule details |
| `validation.status` | Integrity-check status; must be `"PASS"` |
| `validation.fidelity_acceptance` | Must be `"NOT_CONFIGURED"`; never presented as statistical fidelity passing |
| `validation.account_balance_join_coverage.accounts_with_balance.{status,value}` | Account-to-balance coverage, displayed as a percentage |
| `validation.account_balance_join_coverage.balances_with_account.{status,value}` | Balance-to-account coverage, displayed as a percentage |
| `numeric_differences[].{table,column,metric,status,source,generated,difference,difference_unit}` | Four selected means and their P50/P95 detail |
| `categorical_differences[].{table,column,category,status,source,generated,difference,difference_unit}` | Selected Y/N past-due proportions |
| `dependency_results.credit_limit_balance_pearson.{status,source,generated,difference,difference_unit}` | Credit-limit/balance Pearson comparison |
| `dependency_results.delinquency_by_utilization[].{utilization_bucket,status,source,generated,difference,difference_unit}` | Conditional past-due rates by utilization bucket |
| `warnings[].code` | Fixed local warning text for the recognized codes below |

### Selected keys and units

- Row counts accept `table`: `PERSON`, `CUSTOMER_ACCOUNT_REL`, `TKQ_ACCOUNT`, `TKQ_ACCOUNT_BALANCE`, `TRADELINES`, `CUSTOMER_RELATIONSHIP`. The UI uses fixed human-readable labels.
- Numeric records accept `(table, column)` pairs: `TKQ_ACCOUNT / CREDIT_LIMIT_AMT`; `TKQ_ACCOUNT_BALANCE / CURRENT_BALANCE_AMT`, `/ AVAILABLE_TO_BUY_AMT`, `/ OVERLIMIT_AMT`. Each uses `metric`: `mean_value`, `p50`, `p95` and `difference_unit: "value"`.
- Categorical records accept `table: "TKQ_ACCOUNT"`, `column: "PAST_DUE_INDICATO_CD"`, `category: "Y"` or `"N"`, and `difference_unit: "percentage_points"`.
- The Pearson record uses `difference_unit: "correlation"`; SOURCE/GENERATED values must be between −1 and 1.
- Conditional records accept `utilization_bucket`: `0-30%`, `30-60%`, `60-80%`, `80-100%`, `100%+`, and `difference_unit: "percentage_points"`.
- Comparison `status` is `AVAILABLE` or `UNAVAILABLE`. SOURCE/GENERATED values and differences must be finite numbers or null. An unavailable comparison can still show an available side; its difference remains Unavailable. Rate values are fractions in [0, 1], displayed as percentages. Rate differences are already percentage points and are displayed with `pp`, without multiplying again. Differences always mean GENERATED minus SOURCE; no relative or overall score is calculated in the browser.

Recognized warning codes are `FIDELITY_THRESHOLDS_NOT_CONFIGURED`, `APPROVED_RULES_NOT_IMPLEMENTED`, `SKIPPED_PROPOSALS`, and `UNAVAILABLE_METRICS`. The fidelity-threshold explanation always appears. JSON warning `message`, `count`, free-form `reason`, arbitrary categories, unknown fields, IDs and row records are **not rendered**. Dynamic output uses text nodes only. Publish only the sanitized artifact: the browser cannot make an unsafe file safe to host publicly.

## States and checks

- No JavaScript: Results pending, with a plain explanation; all methodology remains available.
- Loading: accessible status feedback and a disabled refresh button.
- Valid export: completion timestamp, integrity status, counts, coverage and comparisons; optional measurements remain explicitly unavailable.
- Missing file, HTTP/network error, invalid JSON/schema or timeout: Latest results unavailable, with a retry button. A failed refresh clears old figures so they cannot masquerade as current results. Focus stays on the same refresh button.

Run the frontend checks without installing packages:

```powershell
node --check docs/results.js
node --test tests/test_results.cjs
```

They cover the contract, percentages, nulls, unsupported/invalid input, text-only rendering, failure/retry/timeout behavior and offline URLs. Browser checks should additionally confirm keyboard navigation, status announcements, table scrolling and mobile layout.
