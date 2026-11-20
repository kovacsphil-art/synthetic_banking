# Validation Report — Original vs Synthetic Data

`validation.html` is the detailed results page; `index.html` retains static methodology and the existing short results panel. Both load the same sanitized `latest-pipeline.json`. Version 1 reports still work in the short panel; the detailed page says **Validation results pending** until a version 2 report is available. Missing/invalid files, unavailable evidence and failed fetches never produce fabricated strengths.

## Inputs and public boundary

Notebook 06 still calls `reporting.load_public_report` after successful validation. It rechecks the exact SOURCE/batch/generation/GENERATED lineage and saved Delta versions, then reads that pair's saved `workspace.synthetic_profile.fidelity_metrics` and the generation-time `rule_execution_log`. `validation_reporting.py` projects a fixed list of public fields from those aggregates. It does not query SOURCE or generated records, change generation, re-profile data or execute proposal text.

No PARTY_ID, ACCOUNT_ID, proposal IDs, internal run IDs, row records, raw category values, model text, credentials or free-form warnings are exported. Month/cardinality bins are used internally for distances; only bounded cardinality bins (0, 1, 2, 3, 4, 5+) and fixed Y/N categories are displayed. Date boundaries are exported as aggregate shifts in days, not original birth dates. The public output is a descriptive screen, not privacy clearance.

## Metrics and JSON mapping

All paths below are under `validation_report`, except the existing `rules` and `validation` fields.

| Report area | Saved evidence | Public JSON fields |
| --- | --- | --- |
| Executive summary | Deterministic classifications of the selected comparisons | `summary.comparison_status`, `variables_total`, `variables_evaluated`, `variables_within_tolerance`, `variables_requiring_review`, `variables_incomplete`, `checks_evaluated`, `strong`, `acceptable`, `needs_review`, `unavailable` |
| Join coverage / applied count | Generated snapshot join coverage and generation-time audit | Existing `validation.account_balance_join_coverage.*.{status,value}` and `rules.applied.value` |
| Numeric chart | NUMERIC P25/P50/P75/P95 | `numeric[].{key,label,average_difference_pct_iqr,max_difference_pct_iqr,status}` |
| Numeric table | The same paired quantiles and SOURCE IQR | `numeric[].source_iqr`, `percentiles[].{name,source,generated,difference}` plus chart fields |
| Categorical proportions | CATEGORICAL TKQ_ACCOUNT.PAST_DUE_INDICATO_CD, fixed Y/N only | `categorical[].{category,source,generated,absolute_difference_pp,status}` |
| Null-rate detail | NULL_RATE for the four numeric fields, past-due indicator and three date fields | `assessments[]` where `family = nulls`: paired rates, absolute pp score and status |
| Date distributions | Complete DATE_DISTRIBUTION calendar-month proportions and DATE_RANGE bounds | `dates[].{total_variation_pct,earliest_shift_days,latest_shift_days,status}` |
| Correlation | CORRELATION ACCOUNT credit-limit / current-balance Pearson metric | `assessments[]` key `correlation.balance_limit`: paired correlation, absolute difference score, status |
| Utilization / delinquency | CONDITIONAL outcome_rate and sample counts in five fixed utilization buckets | `assessments[]` family `conditional`: rates, `score` in pp, `source_n`, `generated_n`, status |
| Cardinality distributions | CARDINALITY for accounts per party, outgoing/incoming customer relationships, tradelines per CIF when available | `cardinality[].{key,label,total_variation_pct,source_mean,generated_mean,status,bins}`; bin fields are `bucket`, `source`, `generated`, `absolute_difference_pp` |
| Relationship directionality | CUSTOMER_RELATIONSHIP directed/reciprocal/self dyad proportions | `assessments[]` family `graph` |
| Structural populations | ROW_COUNT across all six tables | `populations[].{table,source,generated,difference}` |
| Population ratio | Account row count / PERSON row count, separately for each population | `accounts_per_person.{source,generated}`; distinct from profiled relationships per customer |
| Integrity / business rules | JOIN_COVERAGE, BUSINESS_RULE, TEMPORAL_RULE and invalid CUSTOMER_RELATIONSHIP endpoints | `assessments[]` family `integrity`: raw rates, `source_count`, `generated_count` (matched rows for coverage; violations otherwise), eligible `source_n`/`generated_n`, generated error score, status |
| Implemented rule outcomes | Known implementation names in generation-time audit, excluding legacy fallback rows with no proposal ID | `rule_outcomes[].{implementation,target,proposed,approved,applied,skipped}` |
| Strengths / weaknesses | Classified comparisons, ranked deterministically | `strengths[]` / `weaknesses[]` reference fixed keys in `assessments[]` |
| Policy and availability notes | Fixed configuration and reason codes | `policy_version`, `thresholds`, `min_conditional_rows`; per-assessment `reason` |

The numeric allowlist is CREDIT_LIMIT_AMT, CURRENT_BALANCE_AMT, AVAILABLE_TO_BUY_AMT and OVERLIMIT_AMT. Date selections are PERSON.BIRTH_DT, PERSON.SINCE_DT and TKQ_ACCOUNT.OPEN_DT. The full selection and labels live in `src/synthetic_banking/validation_reporting.py`.

## Formulas and centralized tolerances

`THRESHOLDS`, `MIN_CONDITIONAL_ROWS` and `POLICY_VERSION` in that module are the source of configuration. The emitted JSON includes the same thresholds. `scripts/build_validation_schema.py` generates the closed version-2 schema and the browser's fixed label/config allowlist from that configuration. Run it with `src` on `PYTHONPATH` after changing the policy, and bump the policy version when semantics change. Update the documented version if changing it incompatibly.

| Metric | Strong match | Acceptable | Needs review |
| --- | --- | --- | --- |
| Maximum absolute percentile difference / SOURCE IQR | ≤ 5% | ≤ 15% | > 15% |
| Absolute category, null-rate or dyad-proportion difference | ≤ 1 pp | ≤ 3 pp | > 3 pp |
| Absolute conditional outcome-rate difference | ≤ 2 pp | ≤ 5 pp | > 5 pp |
| Absolute Pearson difference | ≤ 0.05 | ≤ 0.15 | > 0.15 |
| Calendar-month / cardinality total variation | ≤ 2% | ≤ 5% | > 5% |
| Generated integrity checks | 100% join coverage; zero measured violations | No intermediate pass band | Any uncovered row / violation |

Threshold comparisons allow 1e-9 numerical roundoff. Integrity passes are labelled **Passed**, not statistical strong matches, and do not populate the strengths list. Display tolerances do not modify the pipeline's validation gate. `validation.status = PASS` still describes saved-output integrity; `fidelity_acceptance = NOT_CONFIGURED` still means no overall business acceptance criterion or fidelity score is defined.

Numeric chart: `100 × mean(abs(GENERATED Pq − SOURCE Pq)) / SOURCE IQR` for q = 25, 50, 75, 95. Status uses the **maximum**, not mean, of those normalized differences. Raw quantiles remain visible when IQR is zero/missing or any quantile is unavailable; no denominator fallback is invented.

Distribution total variation: `50 × sum(abs(generated_proportion − source_proportion))`, expressed on a 0–100% scale. Both complete distributions must sum to one; unavailable or inconsistent profiles remain pending. Cardinality TV uses the full distribution before display rebinning. Temporal shape uses calendar-month bins; boundary shifts use days. Raw signed differences are GENERATED minus SOURCE.

Conditional buckets require at least 30 rows on each side. Low-count buckets retain their raw rates/counts but are not classified or ranked as strong matches. This is a descriptive coverage safeguard, not a significance test. The legacy Pearson metric does not save paired sample counts, so missing sample sizes remain null; correlation is not causation.

## Summary, strengths and weaknesses

A variable is identified by its fixed table/column selection, counted once even if its distribution and null rate both appear. There are eight selected variables. `variables_evaluated` means at least one available check. The other variable counts partition the selection: any needs-review check → requires review; otherwise any missing check → incomplete; otherwise all checks within tolerance → within tolerance. A partially evaluated variable can therefore appear in both evaluated and incomplete counts. Relationships/integrity checks are additional checks, not additional variable counts. Population size differences alone are never fidelity failures.

Comparison status is PENDING with no evaluated checks; otherwise REVIEW_REQUIRED if any check needs review; otherwise PARTIAL if evidence is missing; otherwise WITHIN_TOLERANCE. This status must not be described as blanket data quality or external-release approval.

Strengths use only STRONG statistical comparisons, sorted by `score / acceptable_threshold`, then fixed public key. Selection first takes one per family, then fills remaining slots with at most two per family, up to six. Integrity passes are shown separately. No generic strength text or fixed winners are supplied.

Weaknesses use only NEEDS_REVIEW checks, sorted by descending `score / acceptable_threshold`, then fixed public key, up to six with at most two per family. For integrity issues the ranking denominator is 1 percentage point; any violation still fails its check. Each finding displays its measured departure and unit. Missing evidence is listed separately and never ranked as a measured deviation. There is no combined fidelity score.

## Current gaps

- Only the configured public variables/relationships are evaluated, not all profiler columns or categories.
- TRADELINES_PER_CIF cardinality is currently unprofiled and displays pending unless future saved evidence supplies it.
- Full cross-table referential-integrity counts are checked during generation but not all are retained in `fidelity_metrics`; the public comparison explicitly marks other references pending. CUSTOMER_RELATIONSHIP endpoint evidence is included when saved.
- Empty relationship populations, missing legacy monthly profiles, missing/zero SOURCE IQR and small conditional buckets remain pending.
- Calendar-month fidelity does not measure day-of-month or time-of-day similarity. No inferential confidence intervals, general nearest-neighbour quality test or privacy result is inferred.
- Application of an approved implementation is reported independently from measured relationship fidelity.

## Update and publication

The version-1 schema/example are preserved as `pipeline-report-v1.schema.json` and `example-v1.json`; the primary schema/example now document version 2. Examples are fabricated and are never loaded as production results. The publication script accepts both contract versions, validates the closed schema, and stages the new HTML/JS/config files explicitly. No source code, internal reports or row exports are included in the Pages artifact.

Deploy the updated bundle and rerun **only the reporting task** of a previously successful, still-current validated execution to populate version 2 from its saved evidence; or run the existing full workflow normally. Do not regenerate or re-profile merely to change this presentation. Existing lineage/version checks must still pass. Then run **Publish validated showcase** or wait for its scheduled check. Invalid exports preserve the previous report and site.

Local checks: run the Python suite with NumPy, pandas and jsonschema installed, then `node --test tests/test_results.cjs tests/test_validation_page.cjs`. Preview the static site with an HTTP server. Browser review should confirm keyboard navigation, sort controls, scrolling tables, missing-data states and mobile layout.
