# Phase one: measured conditional sampling

This change adds three approval-gated implementations to the existing generator. It does not add generation modes, change approvals, execute proposal text, or compare AI with a control group. Unapproved, conflicting, unsupported or insufficiently evidenced proposals retain the previous sampling path and receive skip events.

## Review and selection

The review used one completed development SOURCE profile (completed November 20, 2026 at 14:13 UTC), with 1,000 PERSON records and 1,552 account snapshots. Only saved aggregate profiles were retrieved; no SOURCE records were read or committed. SOURCE is the fake development baseline, not production banking data.

| Measured candidate | Evidence | Decision |
| --- | --- | --- |
| Account type → client product | Cramér's V = 1; 1,552 complete pairs; smallest parent group 656 | Implement conditional categorical sampling |
| Client product → TSYS product | V = 1; 1,552 complete pairs; smallest parent group 107 | Implement after client product |
| Credit limit → current balance | Pearson = 0.4962; 1,552 finite pairs; four SOURCE credit-limit quartiles with 380–402 pairs each | Implement conditional rank coupling |
| Employment → occupation / occupation description | Measured associations, but some sparse cells and wider PERSON scope | Defer |
| Automatic payment → past due | V about 0.0135 | Insufficient association for this phase |
| Tradeline type → industry | Measured association | Defer to keep the pilot small |

These associations support distribution modeling, not causal conclusions. Parent direction comes from a fixed reviewed implementation.

## Implemented methods

`dependency_sampling.py` contains pure NumPy implementations. `rules.py` matches exact target/type/parent metadata and validates the existing review provenance. `generation.py` calls them while assembling the same six entities. Notebooks and workflow task handoffs are unchanged.

| Target table / column | Rule type | Required parent | Implementation / order |
| --- | --- | --- | --- |
| TKQ_ACCOUNT.CLIENT_PRODUCT_CD | CONDITIONAL | TKQ_ACCOUNT.ACCOUNT_TYPE_CD | conditional_categorical_v1 / -2 |
| TKQ_ACCOUNT.TSYS_PRODUCT_CD | CONDITIONAL | TKQ_ACCOUNT.CLIENT_PRODUCT_CD | conditional_categorical_v1 / -1 |
| TKQ_ACCOUNT_BALANCE.CURRENT_BALANCE_AMT | CORRELATED | TKQ_ACCOUNT.CREDIT_LIMIT_AMT | conditional_numeric_rank_v1 / 0 |

The qualified or corresponding bare parent name is accepted. Existing balance formulas retain orders 1/2 and delinquency order 3. Each considered proposal has one application/skip event in the existing audit, carrying SOURCE, batch, proposal, generation, seed, target, implementation and processed-row context. Approval does not imply application. No new dependencies run through a legacy fallback.

**Categorical:** Use the measured complete-case cross-tab `P(child | parent)`. Require one same-run SOURCE summary, at least 100 complete pairs, coverage ≥95%, V ≥0.1, a complete grid of at most 200 cells, and at least 30 observations per parent. Validate counts, cardinalities and probabilities. Sample only observed combinations; zero cells retain zero probability. No smoothing or borrowing probabilities from other groups occurs. Existing generated null masks are retained. An unknown non-null parent or incomplete/sparse evidence skips the proposal rather than extrapolating. Missingness dependence is not modeled, and existing account null-sampling limitations are not changed.

**Numeric:** Keep the existing nine-knot inverse-CDF balance draws. Generate ordering scores from the measured five conditional quantiles (min/P25/P50/P75/max) within each SOURCE credit-limit quartile. Reorder the existing finite balance values by those scores. This preserves the finite raw balance multiset exactly before the existing 125%-of-limit cap. Missing pairs retain their previous values. Require one same-run SOURCE global profile with at least 200 pairs, ≥95% coverage and absolute Pearson ≥0.1, plus all four matching quartile intervals with at least 30 pairs each. Incomplete bounds, invalid/nonfinite quantiles, insufficient observations or generated values outside measured SOURCE support cause a logged skip. No arbitrary winsorization, tail extrapolation or invented outlier distribution is added.

The existing nonnegative floor, cap, available-credit/overlimit formulas, utilization, delinquency sampling/count consistency, synthetic IDs, cardinalities, relationship graph, dates and snapshot alignment remain in place. The cap can change the final marginal when the pairing changes; raw-multiset preservation is not a guarantee of identical saved balances.

Independent random streams derive from the configured seed plus fixed implementation/column identifiers. They do not consume the original generator's RNG stream or depend on proposal UUIDs. Same evidence, approvals, settings and code reproduce the result; categorical evidence row ordering does not matter.

## Numeric alternatives considered

Directly replacing balances with draws from the coarse five-knot conditional distributions inflated the upper tail in an initial aggregate-only 100,000-pair check (mean gap about +8.7%). Conditional rank coupling retained the richer marginal while improving the conditional ordering, so it was selected.

A Gaussian copula was considered but not fitted: saved raw Pearson coefficients are not latent Gaussian correlations or paired rank data. [statsmodels' copula fitting interface](https://www.statsmodels.org/stable/generated/statsmodels.distributions.copula.api.GaussianCopula.fit_corr_param.html) estimates its parameter from Kendall's tau; its [tau-to-correlation conversion](https://www.statsmodels.org/stable/generated/statsmodels.distributions.copula.api.GaussianCopula.corr_from_tau.html) makes that distinction explicit. Substituting the stored raw Pearson value would add an unsupported modeling assumption. This phase needs neither SciPy nor statsmodels. Rank coupling is an approximate conditional model, not an exact fitted copula or an exact Pearson calibration.

## Before / after method preview

Three offline, aggregate-backed previews requested 10,000 customers, using seeds 42, 19 and 2026. Both methods used identical SOURCE aggregates and the original main RNG stream. The previous method uses the unchanged marginal samplers; the updated preview directly exercises the new pure sampling functions. It does **not** create artificial reviewed proposals, live approvals, application audits or Databricks generation runs. Generated aggregates were compared using the existing `compare_profiles` and public validation projection. NumPy exact quantiles in this preview may differ slightly from Databricks approximate-percentile aggregation.

| Metric | Seed 42 previous → updated | Seed 19 | Seed 2026 |
| --- | --- | --- | --- |
| Limit/balance Pearson (SOURCE 0.4962) | 0.0809 → 0.4309 | 0.0924 → 0.4171 | 0.0874 → 0.4271 |
| Account type / client product conditional TVD | 49.634% → 0.198% | 47.928% → 0.315% | 48.699% → 0.814% |
| Client / TSYS product conditional TVD | 78.425% → 0% | 78.169% → 0% | 78.342% → 0% |
| Balance worst P25/P50/P75/P95 gap / SOURCE IQR | 8.212% → 1.748% | 7.519% → 2.065% | 8.010% → 1.730% |
| Available-credit worst percentile gap / IQR | 46.206% → 21.368% | 40.382% → 21.057% | 41.317% → 18.373% |
| Mean absolute balance-mean gap across SOURCE quartiles | 876.65 → 87.66 | 848.68 → 56.06 | 859.92 → 119.18 |
| Past-due marginal absolute gap (pp) | 0.754 → 0.817 | 0.900 → 1.083 | 1.130 → 1.182 |

Conditional TVD is `50 × sum(abs(GENERATED proportion − SOURCE proportion))` within each parent, averaged using SOURCE parent shares. Percentages are distances, not accuracy. Numeric percentile classifications continue using the existing transparent report tolerances; no new overall score or statistical acceptance gate is added.

**Regressions and remaining gaps:** balance mean moved from −30.03 to +101.99 relative to SOURCE for seed 42; the other seeds also worsened mean closeness despite improved percentile gaps. Product marginal gaps fluctuate: seed 2026's largest client-product gap increased from 0.495 to 0.800 pp. The seed-42 80–100% utilization bucket's past-due gap increased from 0.578 to 2.353 pp. Changed utilization alters downstream populations even with unchanged delinquency probabilities. The absent SOURCE >100% conditional rate remains unavailable; the existing legacy fallback still applies there. SOURCE overlimit mean is zero; generated overlimit mean improved from 75.58 to 11.71 for seed 42 but remains nonzero. Zero SOURCE IQR prevents a normalized overlimit score. Available-credit and correlation gaps remain; none of these improvements establishes production fitness.

**Integrity:** each method produced the same 17,313 / 17,486 / 17,389 accounts for the respective seeds, with 100% account/balance key coverage and zero measured cap, negative-balance, derived-formula or delinquency-count violations. Updated categorical sampling produced zero SOURCE-unsupported complete-case combinations. Unmeasured temporal/reference metrics remain unavailable in this offline preview; local full-generator regressions check unchanged other entities, dates/keys, formulas and RNG state. This is not a substitute for the saved Delta validation gate or privacy screening.

## Activate and validate in Databricks

1. Deploy the updated shared `src/` code to a **test destination**. Pin a completed SOURCE run containing the categorical and numeric dependency profiles. Older runs missing these profiles skip the new rules.
2. In Notebook 02 use that SOURCE ID and `ACCOUNT_CORE` scope (interactive: both `balance_pilot` and `delinquency_pilot` OFF; workflow: `rule_scope=ACCOUNT_CORE`). This exposes measured cross-tabs and the selected numeric group's global/quartile aggregates. The existing BALANCE_PILOT default remains limited to its original formulas.
3. Inspect the new batch and individually review proposals with the target/type/parent metadata above. Review other proposals APPROVED or REJECTED as appropriate; do not blanket-approve a batch or edit proposal text into code. If the LLM omits a dependency, it remains inactive.
4. Use the same SOURCE/batch in Notebook 03. An interactive narrow pilot can list the three reviewed proposal IDs; the existing pilot guard stops before writes if any selected rule cannot apply. The workflow retains its existing all-proposals-reviewed stop and metadata fingerprint.
5. Inspect `rule_execution_log` for actual APPLIED/SKIPPED events. Saved validation additionally rejects SOURCE-unsupported complete-case combinations for applied categorical implementations. Existing structural/business/date checks remain required.
6. Profile the validated batch as GENERATED, retaining its exact SOURCE lineage. Use the existing fidelity report for numeric means/tails, all category marginals, missingness, correlations, conditional rates, cardinalities and constraints. Before overwriting a prior generation, preserve its completed GENERATED profile and comparison; profile history remains available. Compare method revisions with identical SOURCE/population/seed and record the approved proposal set, without introducing AI/no-AI modes.
7. Export via the normal reporting task. The optional sanitized dependency fields documented below feed the existing Validation Report. Do not replace the live report with this offline preview.

A newly approved Databricks pilot and full saved-output integration check are still required. No new live rule approvals were made and no generated tables or published measurements were overwritten during this development review.

## Reporting and tests

`fidelity_metrics` now includes per-cell `CATEGORICAL_CONDITIONAL` proportions with parent counts, plus the fraction of generated complete cases absent from SOURCE support. Numeric segment means use the existing SOURCE cutpoints; mismatched boundaries remain not comparable. Public projection removes all raw category labels and IDs and adds optional `validation_report.dependency_fidelity`; see [contract](reporting/README.md). Existing report layout, charts and prototype classifications remain intact; supplemental tables use the existing dependencies disclosure and stay outside headline counts.

Fabricated tests cover support validation, sparse/zero cells, null masks, tails/out-of-support values, approved/rejected/unverified/conflicting proposals, missing profiles, parent-first order, one audit per proposal, exact raw numeric marginals, improved measured association, full-generator reproducibility, saved combination checks, SOURCE-scoped profile/context loading, public sanitization and schema/browser compatibility. Existing golden cohort tests continue checking the previous path when no eligible new rule is present.
