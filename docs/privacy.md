# Basic disclosure-risk gate

This is a lightweight, purpose-limited screening stage, **not anonymization certification, differential privacy, or permission to distribute data**. Synthetic data can still disclose non-public information; passing a few matching tests does not establish robust privacy guarantees. [NIST SP 800-226](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-226.pdf)

The stage does not change the generator, distributions, LLM prompts, fidelity metrics or public reporting contract. Source comparisons run inside Databricks using pinned Delta inputs. Only counts, rates, aggregate distances, configured column names, policy settings and execution provenance are persisted. No records, matched identifiers, category combinations, dates, row hashes or exception payloads are printed or exported.

## Execution order

```text
SOURCE profiling → LLM proposals → manual approval check → generation + saved-output validation
  → privacy_check → GENERATED profiling → fidelity validation → aggregate JSON → static showcase
                      │
                      └─ future row-level exporter: require_row_level_release(...) first
```

`notebooks/07_Privacy_Check.py` receives the exact SOURCE, proposal batch and generation IDs from the job. It uses `privacy.py`, `privacy_checks.py` and the existing validated-generation/version checks. A different SOURCE/generation/batch is rejected. The reusable assessment API also supports validated manual generations without an LLM batch.

Risk findings do **not** fail the notebook task: `privacy_status` is `PASS`, `REVIEW_REQUIRED` or `BLOCKED`; `privacy_assessment_id` and the technical `row_level_release_allowed` Boolean are task values. Aggregate profiling/reporting may continue even when row-level release is blocked. Missing provenance and infrastructure failures may still fail a task; these are not privacy clearance. No dataset download/publication task is enabled.

## Exact SOURCE and generated inputs

Notebook 01 records SOURCE staging-table Delta IDs and versions **before creating session-local input views**, then verifies the versions and SOURCE-alias definitions again before completing profiling. The supported aliases are the simple staging-table projections created by this repository. This preserves the current table/view architecture and detects source changes during profiling.

The references are saved by SOURCE `run_id` in `workspace.synthetic_profile.privacy_source_snapshots`. They contain metadata only. The privacy stage time-travels to these versions and to the validated generated versions; it never substitutes current staging rows or `current_run`.

- Older SOURCE runs without verified snapshot evidence cannot clear row-level release. Rerun SOURCE profiling, proposal review and generation; do not backfill an old run using whichever staging tables exist today.
- Table recreation, changed aliases during profiling, missing versions, retention/VACUUM loss and unsupported source layouts produce unavailable evidence and block release. Snapshot-capture limitations do not invalidate the ordinary aggregate SOURCE profile.
- Run one writer against shared staging/generated objects, including interactive sessions. Snapshot checks are not a distributed lock and cannot defend against administrators altering evidence. Historical Delta reads require the log and data files to remain available. [Databricks time travel and retention](https://docs.databricks.com/aws/en/delta/history)

## Checks and limitations

Defaults live in `PrivacyPolicy` in `privacy_checks.py`, with algorithm version `basic_v1`. They are conservative prototype screening settings, not calibrated release standards. Policy settings and their SHA-256 are saved with each assessment. Changing the policy invalidates an older clearance; bump the algorithm version when changing check semantics.

| Check | What is measured / default decision | Limitations |
| --- | --- | --- |
| Identifier overlap | Synthetic identifiers and references are compared against the full configured SOURCE identifier domain, after trimming, uppercasing and string conversion. Any overlap FAILS. | Checks configured entity keys/references, not every possible direct identifier or free-text field. Null/blank IDs are excluded and counted; existing generation validation separately checks required synthetic IDs. It does not normalize punctuation or numeric zero-padding. |
| Full SOURCE-row matches | Compare every original SOURCE column, including IDs, against the generated table; generated-only columns are ignored. Nulls match nulls. Any exact match FAILS. | Different IDs can make this zero even if all other values were copied. Numeric/temporal type differences use safe casts and lossless round-trip checks; complex/unsupported types and incomplete schemas are unavailable, not passing. Numeric equality is value equality at the SOURCE type, not equality of file bytes. |
| Payload matches with IDs removed | Count matches on all original non-ID columns. A payload with at least three columns and a non-text/non-Boolean field requires review if it matches a SOURCE pattern supported by fewer than 5 rows. | Common payloads can legitimately repeat. Low-information payloads are INFO, never evidence of anonymity; all categorical/constant or small link-table payloads may be uninformative. Quantile interpolation or shared dates can produce coincidences; a match is not proof of memorization. |
| Rare categorical combinations | Three curated patterns, below. Record complete-case coverage, generated rare rows/groups, rows matching SOURCE patterns with support below 5, and SOURCE-unseen rows. Review if any SOURCE-rare pattern is matched, more than 1% of eligible generated rows have generated support below 5, or either side has under 90% complete-case coverage. | A bounded field selection, not an all-column search, a k-anonymity guarantee or proof of re-identification. New SOURCE-unseen combinations do not by themselves establish disclosure. Missing values are excluded and measured, not filled. Categories are trimmed/uppercased. |
| Selected PERSON similarity | Exact gender agreement plus birth and customer-since dates each within 7 days. Report matched row count, rows close to SOURCE patterns with support below 5, complete-case counts/coverage and minimum distance among matched profiles. Any low-support near match or coverage below 90% requires review. | This is a thresholded similarity screen, **not global nearest-neighbour distance**. Other genders, unknown dates and variables outside this tuple are not compared. Unmatched rows have no inferred distance. Selection of quasi-identifiers and tolerances depends on plausible external knowledge and must be reviewed for the intended release. |

Identifier domains:

- Party: `PERSON.PARTY_ID`, `CUSTOMER_ACCOUNT_REL.PARTY_ID`, `CUSTOMER_RELATIONSHIP.FROM_PARTY_ID`, `.TO_PARTY_ID`, `TRADELINES.REQ-CIF-KEY`.
- Account: `TKQ_ACCOUNT.ACCOUNT_ID`, `TKQ_ACCOUNT_BALANCE.ACCOUNT_ID`, `CUSTOMER_ACCOUNT_REL.ACCT_ID`.
- Tradeline: `TRADELINES.account_number`. `REQ-CIF-TIE-BREAKER` is a shared structural value, not an independently unique identifier, and is excluded from payload comparisons.

Curated categorical patterns:

1. PERSON: `GENDER_CD`, `PREF_LANG_CD`, `CUST_TYPE_CD`.
2. PERSON: `EMP_TYPE_CD`, `OCCUP_CAT_CD`.
3. TKQ_ACCOUNT: `ACCOUNT_TYPE_CD`, `CLIENT_PRODUCT_CD`.

The similarity tuple is PERSON `BIRTH_DT`, `SINCE_DT`, `GENDER_CD`. SOURCE and generated records are grouped by that tuple inside Spark. Birth-date buckets and their two adjacent buckets cover the full ±7-day window without an indiscriminate cross join; customer-since distance is then filtered. Group weights preserve generated-row counts, and multiple SOURCE neighbors do not multiply flagged generated rows. The distance is the sum of absolute day differences on the two dates, only among candidates satisfying the window and gender agreement.

At most **2,000,000 candidate profile pairs** are permitted. A larger candidate set is UNAVAILABLE and blocks release; it is not silently sampled or reported as a pass. Missing columns, empty eligible populations, unsupported types and check errors also block release. Match/uniqueness screens require context-specific interpretation. [NIST synthetic-data apparent-match evaluation](https://pages.nist.gov/HLG-MOS_Synthetic_Data_Test_Drive/guide.html)

## Separate aggregate evidence

Two internal Delta tables under `workspace.synthetic_profile` keep privacy evidence separate from `fidelity_metrics`:

- `privacy_assessments`: assessment/SOURCE/generation IDs, start/completion time, overall status, policy version/settings/hash, SOURCE-snapshot signature, validated generated versions and metric count. RUNNING is saved before scanning and never grants clearance.
- `privacy_metrics`: check/table/column names, PASS/FAIL/REVIEW_REQUIRED/UNAVAILABLE/INFO, evaluated and flagged row counts, rates/thresholds, fixed reason codes and numeric aggregate detail. No matching values or row examples are stored.

Overall `PASS` requires every configured check to be present and successful, with INFO allowed only for low-information payload checks. Any FAIL or unavailable/error evidence is `BLOCKED`; unresolved heuristic findings are `REVIEW_REQUIRED`. A screening PASS only means this fixed set of tests passed on those versions.

Inspect aggregates privately, for example:

```sql
SELECT check_name, logical_table_name, columns, status,
       evaluated_rows, flagged_rows, metric_value, threshold, reason_code
FROM workspace.synthetic_profile.privacy_metrics
WHERE assessment_id = :assessment_id;
```

Version-1 artifacts remain supported. The optional version-2 `privacy` projection now publishes only the exact workflow assessment's allowlisted aggregate status, policy and check counts, independently from statistical fidelity. Reporting verifies saved SOURCE/generated snapshots and does not export assessment IDs, patterns, matching values or records. Validation PASS is **not privacy clearance**; dataset downloads remain disabled.

### First live pilot review

All 25 checks completed, but status remains **REVIEW_REQUIRED**. Fourteen of 10,000 generated people match a SOURCE person on gender with birth/customer-since dates each within seven days. Read-only aggregate investigation found one SOURCE candidate per flagged person, no exact full quasi-identifier tuple matches, and a minimum combined date gap of two days. A separate gender/language/customer-type check found eight rows matching SOURCE-rare patterns, with none rare in the larger generated cohort. Both checks had 100% complete-case coverage. Identifier overlaps and exact full-row matches were zero. The previous generator had the same findings.

SOURCE is fabricated development data. These signals do not prove real-customer disclosure or certify safety for a future production baseline. Review release purpose and attacker knowledge, evaluate removing/coarsening the selected quasi-identifiers and SOURCE-supported sparse-category aggregation, then rerun checks on the proposed release. No mitigation or status override was applied automatically. See the [aggregate investigation and limitations](post-pilot-review.md#privacy-findings-aggregate-investigation).

## Mandatory guard for future row-level publication

The optional [automated demo branch](automated-demo-publication.md) is limited to the separately proven fabricated workflow. It requires both Databricks `demo_release_mode=DEMO_ONLY` and GitHub `SAGE_PUBLISH_DEMO_DATASETS=true`; neither is enabled by this implementation. Complete six-table SOURCE/generated replay and full content checks precede transport to the reporting Volume, and a complete matching draft Release precedes publication. Privacy REVIEW_REQUIRED remains visible and unchanged. This branch cannot authorize uncertain or production-derived inputs. Disable both switches for ordinary aggregate-only operation; general row release still uses the mandatory guard below.

The separate [DEMO_ONLY exporter](demo-dataset-export.md) permits **private packaging only** after exact six-table reproduction proves the approved fabricated development origin. It does not call or weaken `require_row_level_release`, overwrite privacy status, grant production-data clearance, or publish rows. Complete REVIEW_REQUIRED findings remain in the demo metadata. Unknown/actual banking origins, incomplete checks or failed replay stop the demo export. General row-level publication still uses the guard below. The prepared website controls require a separately verified fabricated DEMO_ONLY export and a later explicit Release publication decision; they are currently disabled. See the [download contract](dataset-downloads.md).

Any general-purpose CSV/Parquet/ZIP release, download endpoint or publication task must call this immediately before emitting records. The explicitly scoped private fabricated-origin packaging above is not general release clearance:

```python
from synthetic_banking.privacy import require_row_level_release

clearance = require_row_level_release(
    spark, source_run_id, generation_id, privacy_assessment_id,
)
# A future exporter must read exactly the checked versions and bind its artifact
# manifest to those versions. Recheck immediately before publication.
```

The guard rejects missing/in-progress/failed/review-required assessments, a nonlatest assessment ID, changed policy, incomplete check coverage, altered SOURCE snapshot evidence, replaced source identities, or changed generated tables/audits. It verifies the explicit generation and all stored Delta versions, not a Boolean supplied by a caller. A later incomplete/blocked assessment cannot be bypassed with an older passing ID. The default policy must match the assessment; a deliberately configured alternative must be supplied consistently to both calls.

The old `zip_existing_csvs` utility is disabled: arbitrary existing CSVs have no manifest proving they came from the checked generation. Even a passing Delta assessment cannot authorize unrelated CSV files. No archive is created or copied by that helper. Notebook 08 is limited to the separately verified private DEMO_ONLY workflow; no automatic row-release/publication stage exists. Preparing download metadata does not publish files or clear privacy findings.

This gate is an application safeguard, not access-control enforcement against workspace owners or users who can directly copy tables. Restrict raw/generated-table access and independently review purpose, recipient, auxiliary-data risks, sensitive fields and any repeated releases before external sharing. These checks do not test membership inference, attribute inference, attacks using other tables/variables, or cumulative disclosure across releases; they neither implement nor certify formal anonymization.

## Local and Databricks verification

Run the existing Python suite. `tests/test_privacy.py` executes the screening SQL through an in-memory adapter using fabricated records. It covers overlaps, exact/null-safe copying, payload copying with new IDs, rare patterns, similarity bounds/weighting, null coverage, lossless numeric casts, resource limits, unavailable inputs, stale decisions and disabled CSV packaging. No real SOURCE fixtures are used.

Before relying on this gate, smoke-test Notebook 01 snapshot capture and Notebook 07 on a Databricks **test destination**, including numeric/decimal/timestamp casts, unsupported columns, table replacement, retention failures and the intended scale. Spark/Delta integration has not been executed locally. Do not label a test-only example or a missing assessment as clearance.
