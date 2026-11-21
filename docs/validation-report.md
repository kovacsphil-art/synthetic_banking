# Validation Report — Original vs Synthetic Data

`index.html` presents SAGE's methodology; `validation.html` assesses the statistical and structural similarity of the **final synthetic cohort** to its pinned SOURCE baseline. Both read the same sanitized `latest-pipeline.json`. The validation page does not assess the isolated contribution of AI, display rule-application counts, or introduce control groups. Pipeline review/application auditing remains unchanged and separate.

The current SOURCE reference is the repository's **fake development baseline**, not real production banking data. Reproducing that baseline does not establish production representativeness. The public JSON does not independently certify the origin of a future replacement baseline; the page's baseline disclosure must be reviewed before changing the reference population.

The executive views require version 2; a legacy version-1 artifact remains valid for the publisher and older summary loader but cannot populate these richer views. Missing/invalid files and unavailable evidence never produce fabricated strengths. Optional, backward-compatible post-pilot fields extend the version-2 schema; the active generation path is unchanged.

The distribution comparison joins only the published P25/P50/P75/P95 values: it is a percentile profile, not an estimated density. Categorical bars share a 0–100% scale. The conditional chart leaves gaps for missing rates and uses hollow markers for insufficient comparison evidence; its accessible values table preserves raw rates. Original series are solid charcoal and synthetic series dashed red in line charts, so colour is not the only signifier.

There is **no headline accuracy percentage or combined score**. The summary leads with three **variable-level** outcomes: within all core tolerances, needing review, and incomplete evidence. A small count-based bar represents only that selected variable population, not dataset-wide accuracy. The broader core check counts and dimension table are in a native disclosure. Supplementary checks and full-dataset missingness have separately labelled scopes and denominators; they are never added to the variable count. Structural join coverage remains separate from statistical resemblance. The first three evidence-qualified strengths and review findings are visible, with remaining findings expandable. Headline eligibility is a presentation layer over the unchanged screening grades.

Findings lead with a business interpretation, then display SOURCE and synthetic measurements and a potential consequence for test scenarios. Their scope is labelled Core evidence, Additional statistical check or Full-dataset missingness. Measurement definitions and grades remain expandable. Unpublished values (for example raw monthly date bins) are explicitly unavailable, not inferred. Interpretations do not change measurements, thresholds, backend grades, stored selections or privacy decisions. The browser qualifies and reselects headline strengths from the measured evidence; the original classifications remain visible in the audit and detailed results.

Missingness summaries prioritize nontrivial comparisons. Zero-to-zero observations, entirely-null context and full count reconciliation remain in expandable scope details; the table initially hides trivial rows and its existing checkbox restores them. No observation is deleted or reclassified by this presentation update. The privacy status has its own labelled strip and link, outside the fidelity outcome counts.

For the current reporting artifact, the three scopes reconcile as follows: core variables **4 + 3 + 1 = 8**; core evidence **35 measured + 5 not comparable = 40 checks**; additional screens **9 within tolerance + 3 needing review + 1 not comparable = 13**; missingness **49 preserved + 5 requiring review = 54 nontrivial comparisons**, and **54 + 165 trivial + 1 unavailable = 220 fields**. These are a dated snapshot of the reporting JSON, not hard-coded UI values. The interface derives every displayed count from that artifact and supports explicit unavailable states.

Missingness and dates are primary sections. Calendar-month distance bars and date-boundary shifts expose temporal differences without inventing monthly bins. Relationship cardinalities include a selector for the six published display bins; unprofiled relationships show an explicit unavailable state without a substitute chart. All comparison tables have labelled horizontal scroll regions for smaller screens.

## Inputs and public boundary

Notebook 06 still calls `reporting.load_public_report` after successful validation. It rechecks the exact SOURCE/batch/generation/GENERATED lineage and saved Delta versions, then reads that pair's saved `workspace.synthetic_profile.fidelity_metrics` and the generation-time `rule_execution_log`. `validation_reporting.py` projects a fixed list of public fields from those aggregates. It does not query SOURCE or generated records, change generation, re-profile data or execute proposal text.

No identifier values, proposal IDs, internal run IDs, row records, raw category values, model text, credentials or free-form warnings are exported. The all-field missingness audit adds reviewed column names (including identifier column names) and counts only. Month/cardinality bins are used internally for distances; only bounded cardinality bins (0, 1, 2, 3, 4, 5+) and fixed Y/N categories are displayed. Date boundaries are exported as aggregate shifts in days, not original birth dates. The public output is a descriptive screen, not privacy clearance.

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

The following describes stored backend grades and capped selection arrays. The newer [evidence-qualified presentation](#evidence-qualified-executive-findings) reselects browser headlines from those same measurements, preserves original grades, and explains omissions. The two layers must not be confused.

The [null-rate audit policy](null-rate-audit.md) distinguishes exact 0→0 TRIVIAL observations from meaningful nonzero-rate preservation. Zero-null observations stay in detail and measured counts, with a separate exclusion count; they cannot populate strengths or strong-match totals. The all-six-table audit has its own denominator and contributes meaningful findings/review status without inflating the fixed core selection. A zero/nonzero transition requires review even below the ordinary pp tolerance. Missing counts remain unavailable; display rounding never establishes a zero rate. Unrelated metric families retain their existing treatment.

A variable is identified by its fixed table/column selection, counted once even if its distribution and null rate both appear. There are eight selected variables. `variables_evaluated` means at least one available check. The other variable counts partition the selection: any needs-review check → requires review; otherwise any missing check → incomplete; otherwise all checks within tolerance → within tolerance. A partially evaluated variable can therefore appear in both evaluated and incomplete counts. Relationships/integrity checks are additional checks, not additional variable counts. Population size differences alone are never fidelity failures.

Comparison status is PENDING with no evaluated checks; otherwise REVIEW_REQUIRED if any check needs review; otherwise PARTIAL if evidence is missing; otherwise WITHIN_TOLERANCE. This status must not be described as blanket data quality or external-release approval.

The stored backend `strengths` list uses STRONG comparisons, sorted by `score / acceptable_threshold`, then fixed public key. Selection first takes one per family, then fills remaining slots with at most two per family, up to six. Integrity passes are shown separately. No generic strength text or fixed winners are supplied.

The stored backend `weaknesses` list uses NEEDS_REVIEW checks, sorted by descending `score / acceptable_threshold`, then fixed public key, up to six with at most two per family. For integrity issues the ranking denominator is 1 percentage point; any violation still fails its check. Each finding displays its measured departure and unit. Missing evidence is listed separately and never ranked as a measured deviation. There is no combined fidelity score.

## Post-pilot additions

The optional `validation_report.post_pilot` object adds 13 mean, tail, date-boundary and categorical-conditional screens, separately from the unchanged 40 core assessments. `post_pilot_v1` thresholds are provisional and configurable in `validation_reporting.py`; regenerate the schema/browser config after changes. Relative means use the absolute SOURCE mean, tails use SOURCE IQR, and zero denominators remain explicit. Zero-SOURCE-mean discrepancies use native units and a zero tolerance, and are kept out of cross-unit rankings. SOURCE/synthetic mean bars, a mean table, P01/P05/P99 tails, extrema/stddev, and measured conditional category distances remain individually visible. Combined findings use these additional measurements without changing legacy headline counts or claiming one accuracy score. See [criteria and limitations](post-pilot-review.md#provisional-acceptance-criteria).

Top-level `privacy` is independent of fidelity. It displays the exact workflow assessment's status, policy, completeness and aggregate flags. `REVIEW_REQUIRED` remains visible above the fold; general release remains blocked. The overview separately offers only independently verified, explicitly authorized fabricated DEMO_ONLY downloads; demo availability does not clear privacy findings. A missing historical assessment is UNAVAILABLE, never inferred from integrity PASS. See the [field contract](reporting/README.md#post-pilot-public-fields).

The mean/tail section includes an expandable explanation of percentile interpolation, raw-value-preserving rank coupling and the downstream balance cap. Privacy includes an expandable explanation of similarity flags, fabricated-demo eligibility and review limitations. These are descriptions of the implemented methods, not new metrics or clearance decisions. Cohort-specific cap decompositions and inactive calibration previews remain in the [dated investigation](post-pilot-review.md#follow-up-review--november-21-2026), separate from live JSON. Counts, comparisons, thresholds and statuses continue to come from the current reporting artifact.

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

## Evidence-qualified executive findings

**What SAGE reproduced well** and **Where SAGE needs improvement** use deterministic interpretations of the existing JSON. There is no LLM-written narrative, new tolerance or combined score. The key-variable group is the fixed `FIELDS` selection in `validation_reporting.py`: four account amounts, past-due status and three dates. It is a developer-curated focus, not a statistically representative selection of the 220 audited fields.

Headline statistical strengths require the existing STRONG grade **and** public evidence of SOURCE variation, paired measurements and valid field/bucket counts. Existing conditional minimum support (30 per population) is reused, not changed. Numeric variation is evidenced by a positive SOURCE middle range and, when published, nonconstant extrema/spread. Categorical marginal counts use exact non-null counts for that same field, never whole-table row counts as a proxy. Conditional outcome rates must show both outcomes in SOURCE. Nontrivial zero-distance distributions can qualify; zero alone is insufficient. No new significance or confidence claim is made.

The reviewed generator explicitly allocates graph degrees/directions and rounded date null masks. These are constructed-pattern checks, kept outside headline statistical strengths. Date endpoint comparisons are range-only evidence. Constant missingness, zero-null agreement, missing measurements/counts and aggregate categorical conditional distances without per-group variation/support are retained with an explanatory classification. Overall table counts cannot establish the denominator of a linked-party cardinality profile. The audit **Why some matches are not headline strengths** preserves original grades and explains exclusions; structural constraint passes remain separate.

Eligible findings are ordered by measured departure divided by the existing acceptable tolerance, with one finding per family first, then two and the remaining findings. Public keys provide deterministic tie breaks. No sample-size weighting or new numerical cutoff is invented. All review findings remain expandable, including native-unit zero-reference alerts (which cannot be ranked against normalized gaps using an invented divisor). The original JSON selections are unchanged.

### Audit of the current published artifact — November 21, 2026

| Former headline strength | New presentation context |
| --- | --- |
| Incoming relationships per person | Constructed degree-pattern check; retained in structure and evidence audit |
| Client / TSYS product, zero conditional distance | Measured aggregate match retained in dependencies; category variation/per-group support unavailable for headline qualification |
| Account-opening date bounds | Earliest/latest endpoints only, not the full date distribution |
| Fully directed relationship proportion | Constructed graph pattern, not independent distributional fidelity |
| Bankruptcy-date missingness | Explicit SOURCE-derived rounded null-count target, not independent evidence |
| Past-due rate at 0–30% credit usage | Retained: both outcomes and adequate paired bucket counts are published |

The newly selected leading strengths include the nonconstant credit-payment missingness pattern, past-due rates in the lowest usage group, and measured balance percentiles. Balance mean still requires review; a percentile strength does not imply the entire variable passes every supplemental screen. Five fields remain entirely absent in the synthetic cohort despite fully populated SOURCE counts. The archived [null-rate audit](null-rate-audit.md) found high-cardinality STRING fields with no categorical-profile rows, consistent with the existing supported-field generation followed by null schema completion. New reports show that code-path explanation as context, not a per-run causal conclusion derived from an absolute gap. The report never silently reverses SOURCE/synthetic direction.

### Help, data contract and verification

One shared `metricGuide` utility handles key variables, within tolerance, needs review, not comparable, statistical fidelity, conditional dependencies, null-rate differences, total variation, correlation and explorer metric guides. Help opens on hover/focus/tap and closes on blur, outside pointer interaction or Escape. White, bordered panels expand in document flow, so they cannot cover a statistic or escape the viewport; mobile controls remain tappable. Screen-reader descriptions, expanded states and keyboard focus are explicit.

**No new reporting fields or Databricks refresh are required.** The public schema, JSON and raw observations are unchanged. To support broader future headline claims, the public contract would need reviewed per-group support/variation evidence for categorical dependencies, actual profiled-population counts for cardinalities and paired counts for correlations; monthly bin shares would permit directional date explanations. Missing fields remain unavailable now. The explicit constructed-field context should be reviewed if the generator's date/graph methods change.

Frontend regression tests cover zero and nontrivial exact matches, constants, deterministic formulas, endpoints, sparse/missing evidence, all five null omissions, signed comparisons, tiny nonzero rates, unchanged counts/input data and shared tooltip interactions. Browser checks cover desktop/mobile layout, keyboard dismissal, outside clicks, disclosures, existing selectors and chart controls. This is interface verification, not a stakeholder comprehension study or full assistive-technology certification.
