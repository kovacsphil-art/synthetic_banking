# Post-pilot review

The first live workflow completed all eight tasks. The reporting-only follow-up refreshed the public artifact from the **same validated cohort**; it did not regenerate records, change approvals, or clear privacy findings. SOURCE is the fake development baseline (1,000 people and 1,552 account snapshots), not production banking data. Internal identifiers remain in Databricks; the public report contains aggregate evidence only.

## Confirmed results

| Measurement | Previous generator | Approved phase-one generator | SOURCE |
| --- | ---: | ---: | ---: |
| Credit-limit / balance Pearson correlation | 0.081 | 0.431 | 0.496 |
| Account-type / product conditional total variation | 49.63% | 0.20% | Reference |
| Product / TSYS product conditional total variation | 78.42% | 0.00% | Reference |
| Largest balance P25/P50/P75/P95 gap, as % of SOURCE IQR | 8.16% | 1.83% | Reference |
| Balance mean | 2,986.84 | 3,118.86 | 3,016.87 |
| Available-credit mean | 7,821.94 | 7,626.03 | 7,553.23 |
| Available-credit percentile gap, as % of SOURCE IQR | 46.21% | 21.38% | Reference |
| Account/balance coverage, both directions | 100% | 100% | 100% |

The cohort contains 10,000 customers, 17,313 accounts, and 93,059 rows across six tables. Three reviewed proposals were applied; none were skipped. Existing balance formulas and delinquency behavior remain separately audited as legacy implementations. No measured structural/business-rule issue was found. These checks do not establish complete fidelity or privacy clearance.

Birth and customer-since month-distribution distances remain 8.68% and 8.18%; account-open distance is 4.59%. Some utilization/delinquency gaps increased despite remaining small in adequately supported buckets. The 80–100% SOURCE bucket has only 15 observations; the >100% bucket has no comparable SOURCE evidence. Tradeline cardinality comparison remains unavailable. Zero SOURCE overlimit IQR prevents a normalized percentile comparison; the generated mean is 11.71 versus SOURCE zero and must remain visible in native units.

## Balance mean: explanation supported by decomposition

The existing inverse-CDF sampler linearly interpolates nine SOURCE quantile knots. Its implied population mean is **3,127.11**, above the measured SOURCE mean **3,016.87**. Quantiles alone do not specify the within-interval distribution. The current sampler therefore preserves selected quantiles without necessarily preserving the first moment.

Using the pinned SOURCE, 10,000 customers and seed 42, the approved rank coupling preserves the entire raw balance multiset. It changes which credit limit receives each balance. The unchanged cap `balance <= 1.25 * credit_limit` then clips fewer amounts:

| Decomposition, per account | Independent pairing | SOURCE-conditioned pairing |
| --- | ---: | ---: |
| Raw sampled balance mean | 3,145.92 | 3,145.92 |
| Cap loss from the mean | 159.09 | 27.06 |
| Accounts affected by cap | 1,107 | 343 |
| Final balance mean | 2,986.84 | 3,118.86 |

The **132.03** mean increase equals the reduction in cap loss. The older mean was close partly because upward interpolation bias and downward capping offset each other. This is not evidence of a newly invented extreme-value tail: the sampled maximum, 15,677.22, remains inside SOURCE's maximum, 15,677.34. The saved percentile improvement and correlation improvement are compatible with a worse mean.

This identifies the mean change for this baseline and seed. Finer SOURCE interval statistics would be needed to locate the precise density misspecification inside each quantile interval. Correlation remains association, not causation.

### Separate, inactive adjustment candidate

`dependency_sampling.mean_matched_quantile_candidate` is a tested diagnostic utility, **not registered or called by the live generator**. It warps values monotonically within existing quantile intervals, retains every knot and support bound, preserves missingness, and uses no random draws. An analytic exponent matches the implied inverse-CDF mean to the measured SOURCE mean; infeasible or malformed profiles fail explicitly. It adds no LLM formula or new dependency model.

An in-memory preview used the same SOURCE profiles, cohort settings and seeds, with no table writes or new approvals:

| Seed 42 result | Current method | Inactive candidate |
| --- | ---: | ---: |
| Balance mean gap | +101.99 | −5.45 |
| Credit-limit / balance correlation | 0.4309 | 0.4296 |
| Available-credit mean gap | +72.80 | +178.72 |
| Overlimit mean | 11.71 | 10.19 |
| Measured business-rule issues | 0 | 0 |

Seeds 19 and 2026 also reduced absolute balance mean gaps, with small correlation reductions. The candidate's worst selected balance percentile gap stayed below 5% of SOURCE IQR, but worsened for seed 19 (2.07% to 2.57%). Offline exact percentiles differ slightly from Databricks approximate-profile percentiles and must not replace live results.

**Do not activate the candidate yet.** Credit-limit mean is already 163.09 above SOURCE. Because `available = credit_limit − balance + overlimit`, reducing balance mean exposes more of that credit-limit bias and worsens available-credit mean. Review both marginal means and the derived available-credit distribution together before any generator change. Preserve the existing coupling and business cap while evaluating a minimal joint calibration in a test destination; require the same SOURCE, seed, sizes, approvals and full validation. No new live generation was performed for this review.

## Privacy findings: aggregate investigation

Status remains **REVIEW_REQUIRED**. All 25 expected checks were recorded. Identifier overlap and full-row SOURCE matches were zero; these do not rule out disclosure through quasi-identifiers.

The near-match check uses `BIRTH_DT`, `SINCE_DT`, and normalized `GENDER_CD`: gender must agree and each date must be within **7 days**. A matching SOURCE quasi-identifier pattern with fewer than **5** occurrences requires review. The bounded search evaluated 9,767 candidate pairs for 10,000 generated people, with 100% complete-case coverage.

- Fourteen generated people (0.14%) matched a SOURCE candidate under those criteria.
- Each of the fourteen had exactly one candidate within the configured window; none had multiple candidates.
- None exactly matched the full three-variable tuple. The minimum sum of absolute date gaps was two days.
- A separate `GENDER_CD / PREF_LANG_CD / CUST_TYPE_CD` check found eight generated rows in SOURCE-rare combinations. Those combinations were not rare within the larger synthetic cohort. This check also had 100% coverage; the warning is **not missing evidence**.
- The previous generator had the same fourteen near matches and eight SOURCE-rare pattern matches. PERSON generation was unchanged by the three new account dependencies.

These findings are linkage-screening signals, not proof of copying, identity disclosure or membership inference. Since the current SOURCE is fabricated, no real-customer disclosure is demonstrated. Production use requires a review of attacker knowledge, sensitive attributes and release purpose. The fixed-variable, bounded-window screen is not a general nearest-neighbour attack or a formal guarantee. Synthetic datasets can retain disclosure risk; see [NIST SP 800-188](https://csrc.nist.gov/pubs/sp/800/188/final).

Before any general row release, review whether exact birth/customer-since dates and gender are needed; evaluate date coarsening/removal and SOURCE-supported aggregation or suppression of sparse category combinations. Re-screen the actual proposed release and assess utility loss. Do not simply relax thresholds or relabel this assessment. **General release remains blocked.** The later, separately authorized fabricated DEMO_ONLY package is available through its independent exact-origin, content and publication checks; it does not clear this assessment. See the [verified demo release](demo-release-verification.md).

## Follow-up review — November 21, 2026

The current published report completed at **2026-11-21 02:53:27 UTC** and matches the checked-in sanitized JSON. It contains 10,000 customers, 17,313 accounts, three applied proposals and 100% snapshot join coverage. The later demo-enabled execution reused the original SOURCE and reviewed batch with seed 42. Its statistical and privacy fields match the archived post-pilot report; the completion timestamp and separate demo-release context differ. These are separate executions, not interchangeable private generation IDs.

The aggregate-backed diagnostic was rerun against the same SOURCE profiles using the unchanged current generator, 10,000 customers and seeds 42, 19 and 2026. It reproduced the archived mean decomposition and candidate trade-offs. No SOURCE rows were retrieved, no Delta tables were written, no approvals were changed and no new live generation or privacy assessment was run. The additional candidate-count/tuple diagnostics above are archived aggregate SQL findings, corroborated by the current published privacy counts; they are not newly queried matching records.

**Confirmed cause for these settings:** rank coupling alone preserves the raw balance multiset and mean. Reassigning those values to limits changes the subsequent cap's effect. The raw sample mean 3,145.92 exceeds the measured SOURCE mean by 129.05; the coupled cap removes 27.06, leaving the published +101.99 gap (3.38%). The previous pairing removed 159.09, leaving a −30.03 gap. Its better mean was partly an offset between interpolation bias and clipping, not uniformly better distribution modeling. The raw sample also exceeds the linear sampler's implied population mean by 18.82 for seed 42, a finite-sample difference. All three tested seeds preserve raw values and reduce cap loss after coupling. SOURCE interval-level density remains unavailable, so the precise within-interval source of interpolation bias is not identified.

**Disclosure interpretation:** fourteen generated people meet the rare-pattern similarity rule; this is not fourteen disclosed SOURCE records or an estimated 0.14% re-identification probability. Normalized gender must match, both dates must independently lie within the inclusive seven-day window, and a matching SOURCE tuple must have support below five. The archived aggregate review found one qualifying SOURCE pattern per flagged generated person, no exact three-variable tuple matches and a minimum combined date distance of two days. Complete-case coverage is 100%; missing evidence did not cause this warning. The separate eight SOURCE-rare categorical matches remain relevant even though those combinations are not rare in the larger generated population.

**Suitability for DEMO_ONLY:** this screen is appropriate as a conservative supplementary diagnostic for the independently verified fabricated development workflow. Shared fabricated distributions can produce chance similarities; no actual-customer disclosure is demonstrated. The screen cannot establish origin, certify anonymity or authorize a real-data release. Demo eligibility instead depends on full six-table fabricated SOURCE/generated replay, the closed schema/content scan, exact version binding and explicit release authorization. Those conditions passed for the published demo; REVIEW_REQUIRED remains intact. No new exemption or threshold relaxation is proposed. Future cohorts must pass their own checks.

### Minimal corrective sequence

1. Keep the current approved coupling, business cap and formulas. Do not disable dependencies or remove the cap to improve a single metric.
2. Investigate **both** credit-limit and balance marginal means before activating the existing inactive calibration candidate. Credit-limit mean is +163.09 above SOURCE; changing balance alone exposes that bias in available credit. Use the same SOURCE, seed, size and approvals for any separately reviewed test, and retain percentiles/tails, correlations, conditional rates, derived means and integrity checks. Additional bounded interval counts/means would provide better evidence without a new model family.
3. Preserve the privacy assessment. For general sharing, first define necessary fields and plausible auxiliary knowledge; test omission/coarsening of exact dates and sparse category handling on a separate proposed release, then re-screen it and assess utility. Do not alter the immutable published fabricated demo or call such mitigation an improvement until measured.
4. Keep the report's live metrics separate from method explanations and archived diagnostics. The numeric section now explains the interpolation/cap interaction; the privacy section explains similarity signals, DEMO_ONLY suitability and unresolved general-release review. No offline candidate result is substituted for a live measurement.

Remaining statistical issues include available-credit percentiles, zero-SOURCE overlimit amounts, PERSON date shapes, sparse upper-utilization comparisons and missing tradeline/cardinality evidence. General distribution is still blocked pending privacy review and intended-use acceptance. There is no new blocker for the already authorized, independently verified fabricated demo; this conclusion does not permit production-derived data.

## Provisional acceptance criteria

The values below are configurable screening tolerances, not calibrated business acceptance or a combined accuracy score. At or below the first limit is STRONG; at or below the second is ACCEPTABLE; above it requires review. Missing/invalid/insufficient evidence is UNAVAILABLE, never a pass.

| Statistical screen | Strong ≤ | Acceptable ≤ |
| --- | ---: | ---: |
| Absolute mean difference / absolute SOURCE mean | 1% | 3% |
| Largest P25/P50/P75/P95 gap / SOURCE IQR | 5% | 15% |
| Largest P01/P05/P99 tail gap / SOURCE IQR | 5% | 15% |
| Category or null-rate gap | 1 percentage point | 3 percentage points |
| Absolute Pearson correlation gap | 0.05 | 0.15 |
| Conditional outcome-rate gap | 2 percentage points | 5 percentage points |
| Categorical conditional total variation | 2% | 5% |
| Calendar-month or cardinality total variation | 2% | 5% |
| Largest absolute date-boundary shift | 1 day | 7 days |

SOURCE mean zero uses an explicit zero native-unit tolerance rather than an invented relative denominator. SOURCE IQR zero makes normalized quantile/tail checks unavailable. Conditional rate comparisons require at least 30 complete observations on **both** sides. Supplemental mean/tail/boundary/category screens are shown separately from the unchanged 40 core assessments; no count is an overall quality percentage.

**Mandatory integrity:** required columns and compatible types, synthetic/non-null valid keys, expected row counts and references, successful writes with verified versions, 100% account/balance snapshot coverage in both directions, and zero measured business/temporal/reference violations. Statistical tolerances never override these requirements.

**Separate privacy policy:** zero identifier overlap and zero full-row matches; review SOURCE-rare support below 5, synthetic rare fraction above 1%, incomplete coverage below 90%, or any flagged rare near match within the 7-day window. Similarity has a two-million-candidate budget; insufficient evidence cannot clear release. These are prototype screens and do not authorize publication automatically.

Configure/version core and supplemental statistical thresholds in `src/synthetic_banking/validation_reporting.py`; regenerate the closed schema and browser configuration with `scripts/build_validation_schema.py`. Privacy settings live in `PrivacyPolicy` and are saved with the assessment. Recalibrate against intended analytical use and stakeholder expectations before defining a statistical acceptance gate. Validation integrity PASS currently remains distinct from fidelity screening and privacy review.

## Reporting and next steps

The reporting task now receives the exact privacy assessment task value, verifies its SOURCE/generation and captured snapshots, and emits a closed aggregate-only public projection. The HTML reads measured means, percentiles, tails, categorical dependencies, date shifts and privacy state automatically. Legacy artifacts remain supported; missing evidence is shown as unavailable.

Next: resolve the joint balance/limit mean trade-off, investigate PERSON date shapes, improve sparse-bucket and tradeline comparison coverage, complete privacy review for any proposed row release, and calibrate acceptance criteria. No new model, attribution experiment or row-publication workflow was introduced.

Verification: **210 Python tests and 32 JavaScript tests passed**, including closed-schema rejection, exact privacy/snapshot provenance, backward-compatible rendering, missing evidence and the inactive interpolation candidate. The updated bundle and reporting-only repair succeeded in Databricks. [GitHub Actions publication](https://github.com/kovacsphil-art/synthetic_banking/actions/runs/44848318450) succeeded; the public Validation Report was checked on desktop, with the local preview also checked at a 390px mobile width. Only allowlisted static assets and sanitized aggregate JSON were deployed. Remaining manual decisions are stakeholder calibration of statistical tolerances and contextual privacy review before any row distribution.
