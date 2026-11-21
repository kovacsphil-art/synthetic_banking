# Validation Report — Original vs Synthetic Data

`index.html` presents SAGE's methodology; `validation.html` assesses the statistical and structural similarity of the **final synthetic cohort** to its pinned SOURCE baseline. Both read the same sanitized `latest-pipeline.json`. The validation page does not assess the isolated contribution of AI, display rule-application counts, or introduce control groups. Pipeline review/application auditing remains unchanged and separate.

The current SOURCE reference is the repository's **fake development baseline**, not real production banking data. Reproducing that baseline does not establish production representativeness. The public JSON does not independently certify the origin of a future replacement baseline; the page's baseline disclosure must be reviewed before changing the reference population.

The executive views require version 2; a legacy version-1 artifact remains valid for the publisher and older summary loader but cannot populate these richer views. Missing/invalid files and unavailable evidence never produce fabricated strengths. Optional, backward-compatible post-pilot fields extend the version-2 schema; the active generation path is unchanged.

The distribution comparison joins only the published P25/P50/P75/P95 values: it is a percentile profile, not an estimated density. Categorical bars share a 0–100% scale. The conditional chart leaves gaps for missing rates and uses hollow markers for insufficient comparison evidence; its accessible values table preserves raw rates. Original series are solid charcoal and synthetic series dashed red in line charts, so colour is not the only signifier.

There is **no headline accuracy percentage or combined score**. Executive metrics show selected variables evaluated, checks with evidence, checks needing review and checks not comparable. A dimension table separates numeric, categorical, missingness, date, correlation, conditional, cardinality, graph and integrity results. Variable completeness counts remain contextual; unavailable checks are not counted as matches. Structural join coverage is shown in both directions in the evidence table, rather than presented as an accuracy score. The first three server-ranked strengths and gaps are visible, with remaining findings expandable.

Missingness and dates are primary sections. Calendar-month distance bars and date-boundary shifts expose temporal differences without inventing monthly bins. Relationship cardinalities include a selector for the six published display bins; unprofiled relationships show an explicit unavailable state without a substitute chart. All comparison tables have labelled horizontal scroll regions for smaller screens.

## Inputs and public boundary

Notebook 06 still calls `reporting.load_public_report` after successful validation. It rechecks the exact SOURCE/batch/generation/GENERATED lineage and saved Delta versions, then reads that pair's saved `workspace.synthetic_profile.fidelity_metrics` and the generation-time `rule_execution_log`. `validation_reporting.py` projects a fixed list of public fields from those aggregates. It does not query SOURCE or generated records, change generation, re-profile data or execute proposal text.

No PARTY_ID, ACCOUNT_ID, proposal IDs, internal run IDs, row records, raw category values, model text, credentials or free-form warnings are exported. Month/cardinality bins are used internally for distances; only bounded cardinality bins (0, 1, 2, 3, 4, 5+) and fixed Y/N categories are displayed. Date boundaries are exported as aggregate shifts in days, not original birth dates. The public output is a descriptive screen, not privacy clearance.

## Metrics and JSON mapping

The optional phase-one `validation_report.dependency_fidelity` extension adds two fixed account-product association/conditional-distance rows and four SOURCE credit-limit interval balance-mean rows. Raw category values are never exported. Historical artifacts remain supported; missing metrics are unavailable. These observations stay outside the core headline counts; categorical distances receive supplemental provisional classifications when `post_pilot` is supplied. See the [exact field contract](reporting/README.md#optional-dependency-fidelity-extension) and [method evaluation](statistical-fidelity-phase1.md).

All paths below are under `validation_report`, except the existing completion timestamp and validation envelope. Rule metadata remains in the version-2 contract for compatibility and pipeline reporting; it is not consumed by the final-cohort validation renderer.

| Report area | Saved evidence | Public JSON fields |
| --- | --- | --- |
| Executive summary | Deterministic classifications of the selected comparisons | `summary.comparison_status`, `variables_total`, `variables_evaluated`, `variables_within_tolerance`, `variables_requiring_review`, `variables_incomplete`, `checks_evaluated`, `strong`, `acceptable`, `needs_review`, `unavailable` |
| Structural join coverage | Saved paired SOURCE/generated join coverage and row counts | `assessments[]` keys `integrity.account_coverage` and `integrity.balance_coverage` |
| Numeric chart | NUMERIC P25/P50/P75/P95 | `numeric[].{key,label,average_difference_pct_iqr,max_difference_pct_iqr,status}` |
| Numeric table | The same paired quantiles and SOURCE IQR | `numeric[].source_iqr`, `percentiles[].{name,source,generated,difference}` plus chart fields |
| Upper-tail comparison | Published P50/P95, without new model estimates | Raw P95 values and signed difference; each population's upper spread is derived as `P95 - P50` |
| Categorical proportions | CATEGORICAL TKQ_ACCOUNT.PAST_DUE_INDICATO_CD, fixed Y/N only | `categorical[].{category,source,generated,absolute_difference_pp,status}` |
| Null-rate detail | NULL_RATE for the four numeric fields, past-due indicator and three date fields | `assessments[]` where `family = nulls`: paired rates, absolute pp score and status |
| Date distributions | Complete DATE_DISTRIBUTION calendar-month proportions and DATE_RANGE bounds | `dates[].{total_variation_pct,earliest_shift_days,latest_shift_days,status}` |
| Correlation | CORRELATION ACCOUNT credit-limit / current-balance Pearson metric | `assessments[]` key `correlation.balance_limit`: paired correlation, absolute difference score, status |
| Utilization / delinquency | CONDITIONAL outcome_rate and sample counts in five fixed utilization buckets | `assessments[]` family `conditional`: rates, raw signed `difference` in fraction units (displayed as `100 × abs(difference)` pp), `score` in pp when classifiable, `source_n`, `generated_n`, status |
| Cardinality distributions | CARDINALITY for accounts per party, outgoing/incoming customer relationships, tradelines per CIF when available | `cardinality[].{key,label,total_variation_pct,source_mean,generated_mean,status,bins}`; bin fields are `bucket`, `source`, `generated`, `absolute_difference_pp` |
| Relationship directionality | CUSTOMER_RELATIONSHIP directed/reciprocal/self dyad proportions | `assessments[]` family `graph` |
| Structural populations | ROW_COUNT across all six tables | `populations[].{table,source,generated,difference}` |
| Population ratio | Account row count / PERSON row count, separately for each population | `accounts_per_person.{source,generated}`; distinct from profiled relationships per customer |
| Integrity / business rules | JOIN_COVERAGE, BUSINESS_RULE, TEMPORAL_RULE and invalid CUSTOMER_RELATIONSHIP endpoints | `assessments[]` family `integrity`: raw rates, `source_count`, `generated_count` (matched rows for coverage; violations otherwise), eligible `source_n`/`generated_n`, generated error score, status |
| Strengths / weaknesses | Classified comparisons, ranked deterministically | `strengths[]` / `weaknesses[]` reference fixed keys in `assessments[]` |
| Policy and availability notes | Fixed configuration and reason codes | `policy_version`, `thresholds`, `min_conditional_rows`; per-assessment `reason` |

The numeric allowlist is CREDIT_LIMIT_AMT, CURRENT_BALANCE_AMT, AVAILABLE_TO_BUY_AMT and OVERLIMIT_AMT. Date selections are PERSON.BIRTH_DT, PERSON.SINCE_DT and TKQ_ACCOUNT.OPEN_DT. The full selection and labels live in `src/synthetic_banking/validation_reporting.py`.

P01, P05, P99, minima/maxima and full numeric histogram bins are not present in this public extension. P95 comparisons describe the observed upper percentile and P95-minus-median spread; they do not establish extreme-tail fidelity beyond P95. A zero SOURCE IQR leaves normalization undefined, while raw upper-tail gaps remain visible. Calendar-month bin proportions are also not published: their saved total-variation distances are shown instead of fabricated paired monthly curves.

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

`ACCOUNTS_PER_PARTY` follows the existing customer-account feature population: parties represented in the customer-account relationship table. Its distribution does not measure the fraction of all PERSON records without an account. The separate account-rows/PERSON-rows ratio provides population context and can differ even when the profiled cardinality distribution matches.

## Summary, strengths and weaknesses

A variable is identified by its fixed table/column selection, counted once even if its distribution and null rate both appear. There are eight selected variables. `variables_evaluated` means at least one available check. The other variable counts partition the selection: any needs-review check → requires review; otherwise any missing check → incomplete; otherwise all checks within tolerance → within tolerance. A partially evaluated variable can therefore appear in both evaluated and incomplete counts. Relationships/integrity checks are additional checks, not additional variable counts. Population size differences alone are never fidelity failures.

Comparison status is PENDING with no evaluated checks; otherwise REVIEW_REQUIRED if any check needs review; otherwise PARTIAL if evidence is missing; otherwise WITHIN_TOLERANCE. This status must not be described as blanket data quality or external-release approval.

Strengths use only STRONG statistical comparisons, sorted by `score / acceptable_threshold`, then fixed public key. Selection first takes one per family, then fills remaining slots with at most two per family, up to six. Integrity passes are shown separately. No generic strength text or fixed winners are supplied.

Weaknesses use only NEEDS_REVIEW checks, sorted by descending `score / acceptable_threshold`, then fixed public key, up to six with at most two per family. For integrity issues the ranking denominator is 1 percentage point; any violation still fails its check. Each finding displays its measured departure and unit. Missing evidence is listed separately and never ranked as a measured deviation. There is no combined fidelity score.

## Post-pilot additions

The optional `validation_report.post_pilot` object adds 13 mean, tail, date-boundary and categorical-conditional screens, separately from the unchanged 40 core assessments. `post_pilot_v1` thresholds are provisional and configurable in `validation_reporting.py`; regenerate the schema/browser config after changes. Relative means use the absolute SOURCE mean, tails use SOURCE IQR, and zero denominators remain explicit. Zero-SOURCE-mean discrepancies use native units and a zero tolerance, and are kept out of cross-unit rankings. SOURCE/synthetic mean bars, a mean table, P01/P05/P99 tails, extrema/stddev, and measured conditional category distances remain individually visible. Combined findings use these additional measurements without changing legacy headline counts or claiming one accuracy score. See [criteria and limitations](post-pilot-review.md#provisional-acceptance-criteria).

Top-level `privacy` is independent of fidelity. It displays the exact workflow assessment's status, policy, completeness and aggregate flags. `REVIEW_REQUIRED` remains visible above the fold; dataset downloads are always disabled. A missing historical assessment is UNAVAILABLE, never inferred from integrity PASS. See the [field contract](reporting/README.md#post-pilot-public-fields).

## Current gaps

- Only the configured public variables/relationships are evaluated, not all profiler columns or categories.
- TRADELINES_PER_CIF cardinality is currently unprofiled and displays pending unless future saved evidence supplies it.
- Full cross-table referential-integrity counts are checked during generation but not all are retained in `fidelity_metrics`; the public comparison explicitly marks other references pending. CUSTOMER_RELATIONSHIP endpoint evidence is included when saved.
- Empty relationship populations, missing legacy monthly profiles, missing/zero SOURCE IQR and small conditional buckets remain pending.
- Calendar-month fidelity does not measure day-of-month or time-of-day similarity. No inferential confidence intervals, general nearest-neighbour quality test or privacy result is inferred.
- Rule application is audited independently in the pipeline; it is not a quality metric on this page.

## Update and publication

The version-1 schema/example are preserved as `pipeline-report-v1.schema.json` and `example-v1.json`; the primary schema/example now document version 2. Examples are fabricated and are never loaded as production results. The publication script accepts both contract versions, validates the closed schema, and stages the new HTML/JS/config files explicitly. No source code, internal reports or row exports are included in the Pages artifact.

For existing version-2 results, historical fields still render. To populate the new mean/tail and privacy sections, deploy the updated reporting bundle and repair **only reporting** in a still-current validated execution, or run the full workflow normally. The task must receive the exact `privacy_assessment_id` from `privacy_check`. Existing lineage/version checks must still pass. This reporting-only repair was verified against the completed pilot; it did not change generated tables or privacy status. Invalid exports preserve the previous report and site.

Local checks: run the Python suite with NumPy, pandas and jsonschema installed, then `node --test tests/test_results.cjs tests/test_validation_page.cjs tests/test_executive_showcase.cjs`. Browser review should confirm navigation, percentile/cardinality selectors, sort controls, scrolling tables, unavailable states and mobile layout. Tests also confirm that removing/changing rule-execution metadata does not change the quality report.

## Lightweight result exploration

The executive summary and headline strengths/gaps remain visible above the explorer. Numeric, Categorical and Dependency tabs reuse the already-normalized sanitized report, without extra requests or changes to validation calculations. Arrow keys and Home/End switch tabs; native selectors and sortable column buttons work by keyboard. Metric guides open on hover/focus or tap and close with Escape.

- Numeric charts use the four published P25/P50/P75/P95 values. Table SOURCE/Synthetic columns are medians (P50); the sortable gap is the existing worst-percentile gap relative to SOURCE IQR, not just the median difference.
- Categorical charts show the one published past-due variable. The table compares category shares and supplied absolute percentage-point gaps; other distributions are not inferred.
- Dependency selection switches between measured utilization-conditioned past-due rates and credit-limit/balance Pearson correlation. A fixed −1 to +1 correlation axis avoids implying a wider scale. Additional dependency evidence remains in the detailed tables below.
- Strongest means the existing STRONG classification; weakest means NEEDS_REVIEW. These apply to the displayed metric, not overall variable quality. No threshold, classification or overall score is recomputed.
- Sorting compares gaps only within one metric/unit. Missing or sparse comparisons stay last; raw rates can remain visible without being ranked. Filtering keeps all published chart points for the selected variable, including hollow sparse points, while narrowing the comparison table. Missing charts and empty match views show an explicit unavailable state.

The detailed report, date/missingness/structure/privacy evidence, backend reporting schema and generation process are unchanged. No row data, model attribution experiments or framework dependencies are added.
