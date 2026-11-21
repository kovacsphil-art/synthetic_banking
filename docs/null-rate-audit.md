# Null-rate audit and reporting policy

The November 21, 2026 audit reads the **saved aggregate fidelity evidence** for the completed SOURCE/GENERATED pair associated with the current completed generation. Both profile types/completion and generation lineage were checked; neither `current_run` nor row-level tables supplied the comparisons. The cohort remains 10,000 fabricated customers and 17,313 accounts against the fabricated development baseline. No generation or profiling logic was changed.

## Measured findings

| Table | Variables | Exact zero → zero | Nonzero rate preserved | Discrepancies | Unavailable |
| --- | ---: | ---: | ---: | ---: | ---: |
| PERSON | 19 | 15 | 3 | 1 | 0 |
| CUSTOMER_ACCOUNT_REL | 6 | 6 | 0 | 0 | 0 |
| CUSTOMER_RELATIONSHIP | 9 | 7 | 2 | 0 | 0 |
| TKQ_ACCOUNT | 100 | 60 | 37 | 2 | 1 |
| TKQ_ACCOUNT_BALANCE | 48 | 47 | 1 | 0 | 0 |
| TRADELINES | 38 | 30 | 6 | 2 | 0 |
| **Total** | **220** | **165** | **49** | **5** | **1** |

219 variables have paired valid counts; 54 are eligible for nontrivial assessment after excluding the 165 zero-null observations. Of the 49 preserved nonzero rates, **37 fields are entirely null in both populations** and 12 contain both observed and missing values. Entirely-null agreement demonstrates missingness only; it does not validate any observed-value distribution. The largest absolute gap among the 49 matches is approximately **0.629 pp** (`TRADELINES.collateral_text`). These are observations against the fabricated baseline, not production representativeness or acceptance certification.

Pattern inventory: SOURCE zero / GENERATED nonzero = **5**; SOURCE nonzero / GENERATED zero = **0**; both nonzero = **49**. The one unavailable comparison is `TKQ_ACCOUNT._UTILIZATION_RATE`, a generated helper absent from the SOURCE column profile. Missing SOURCE evidence is not a zero rate.

| Newly visible weakness | SOURCE null / rows | GENERATED null / rows | Gap |
| --- | ---: | ---: | ---: |
| PERSON.DOMICILE_TRANSIT_NUM | 0 / 1,000 | 10,000 / 10,000 | +100 pp |
| TKQ_ACCOUNT.BRANCH_NUM | 0 / 1,552 | 17,313 / 17,313 | +100 pp |
| TKQ_ACCOUNT.OFFICER_NBR | 0 / 1,552 | 17,313 / 17,313 | +100 pp |
| TRADELINES.amount_past_due | 0 / 5,594 | 30,000 / 30,000 | +100 pp |
| TRADELINES.subscriber_code | 0 / 5,594 | 30,000 / 30,000 | +100 pp |

Saved SOURCE quality evidence identifies all five as STRING fields with approximate distinct counts above 100 and **no category-profile rows**. The existing categorical profiler excludes high-cardinality fields; the generator fills only profiled numeric/categorical fields and later pads unsupported columns with nulls. These measured omissions are consistent with that existing path. Schema completeness therefore did not imply missingness fidelity. A future fix should explicitly handle the measured formats/types of these fields and add regression checks; this audit does not change that behavior or invent a sampler.

## Policy `null_rates_v1`

- Compute rates from exact null counts and row counts, before display rounding. Counts must be nonnegative finite integers, within positive row totals; duplicate, absent, invalid or unpaired evidence is UNAVAILABLE. Rates without counts do not establish a strong match.
- **TRIVIAL:** both null counts are exactly zero. Keep the observations but exclude them from statistical strengths and strong-match counts.
- **MEANINGFUL_MATCH:** both rates are nonzero and absolute gap is at most 3 percentage points. The existing provisional cutoffs remain **STRONG ≤1 pp**, **ACCEPTABLE ≤3 pp**.
- **DISCREPANCY:** gap exceeds 3 pp, or missingness appears/disappears (one exact zero count and one positive count). The latter always requires review, even for a tiny rate: it is a qualitative safeguard, not a significance claim.
- Meaningful partial-missingness matches take priority over entirely-null fields in strengths. Only STRONG matches enter the strength list; acceptable preservation is still visible in detail. With no qualifying meaningful match, the null-strength panel says so.

No observations are deleted from `column_quality` or `fidelity_metrics`. Numeric, categorical, date, dependency and integrity classifications are unaffected by this null-only exclusion.

## Summary and website behavior

`validation_report.null_rate_audit` contains an exact-count row for each of the 220 reviewed public table/column names, its pattern/classification, rate gap, reason and eligibility. Only known column **names** and aggregates are exported; no identifier values, source records or run IDs are added. Newly introduced, unreviewed names are counted as additional unpublished variables and remain accessible internally in `fidelity_metrics` until the public metadata allowlist is reviewed.

The existing **eight-variable core selection stays eight**; its eight null checks become TRIVIAL. They remain part of measured-evidence totals, while the STRONG count falls by eight and a separate `summary.trivial_zero_null=8` explains why. The 220-variable audit has separate counts; it is not added to a denominator to manufacture an accuracy percentage. Overall review status also respects all-table null discrepancies/unavailable evidence. Core variable within-tolerance counts still require all nontrivial selected checks to be within tolerance.

Executive findings use meaningful full-audit missingness evidence with the existing per-family caps. Five weaknesses are listed explicitly in the missingness section. Every row remains in its scrollable detail table, including zero-null observations. Native table selection and **Hide trivial zero-null matches** alter display only and can be reversed. Small positive rates remain visible with significant-digit formatting and exact counts. Historical v2 reports remain readable: the browser corrects selected count-backed zero-null strengths without mutating the JSON, and shows the full audit as unavailable until reporting is refreshed.

## Reproduce / refresh

Run the normal Python/frontend suites, including `tests/test_null_rates.py` and `tests/test_validation_page.cjs`. Tests cover all requested patterns, rounded-to-zero positive rates, malformed/missing/duplicate counts, unchanged unrelated metrics, closed public metadata and reversible filters.

After changing policy, regenerate `docs/reporting/pipeline-report.schema.json` and `docs/validation-config.js` with `PYTHONPATH=src python scripts/build_validation_schema.py`. Deploy the updated modules and **repair only reporting** on the still-current successful Databricks execution. Notebook 06 rechecks the original profile pair, Delta versions, privacy assessment and demo receipt before rebuilding JSON. If those checks fail, retain the last report and investigate; never substitute fresh IDs or rerun generation just to refresh presentation. GitHub publication still verifies the successful task receipt/schema and preserves the existing site on failure.
