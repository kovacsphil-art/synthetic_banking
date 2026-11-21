# Private demo dataset export

This opt-in stage packages existing, validated Delta snapshots. It does **not** change generation, create a new cohort, clear privacy findings, publish files, or enable a website download. The general row-release guard and the disabled arbitrary-CSV ZIP helper remain unchanged.

## Scope and gate

`DEMO_ONLY` is a distinct, narrow fabricated-origin workflow, not an alternative privacy PASS. The default mode is `DISABLED`. All five internal IDs must be explicit: completed SOURCE run, proposal batch, generation, completed GENERATED run and current privacy assessment. No `current_run` or latest-generation fallback is used. The exact profile pair, completed generation, saved Delta identities/versions, individually reviewed batch and privacy snapshots must agree. Missing, failed or incomplete privacy evidence stops export; complete REVIEW_REQUIRED findings remain recorded unchanged.

The current policy is intentionally limited to the reviewed development setup:

1. The pinned SOURCE snapshots must reproduce **exactly**, across all six tables and duplicate multiplicities, from `scripts/Scotia Fake Records.py`, seed 42 and 1,000 people. The script hash is pinned in `demo_export_policy.json`. Only its reviewed functions are imported; its notebook startup/main block does not run. The workbook supplies schema names/types, not customer records.
2. The saved generated snapshots must reproduce **exactly** using the existing `generate_dataset`, pinned aggregate profiles, saved seed/customer count, and reviewed batch. Rule execution events must also match the saved audit. Reproduction is in Databricks memory only, with no Delta generation writes and no new LLM calls or approvals.
3. Every output column/type must match the closed reviewed six-table policy. Added/unexpected contact, identity or credential columns fail. All saved values are scanned for recognizable credentials, private keys, contact data, suspicious long numeric identifiers, spreadsheet formulas, control characters and unsupported/non-finite values. No rejected value is logged. Payment-pattern digit strings are an explicit reviewed exception to the long-number screen.
4. Provenance, privacy and table versions are checked again before writing and before readiness. Any uncertainty or mismatch fails closed. Changing a Boolean, filename, review status or table comment cannot declare an actual banking baseline fabricated.

These checks trust reviewed repository code, the schema workbook and workspace access controls; they are not tamper-proof attestation or a comprehensive secret detector. An edited script, other baseline/seed/size, modified profiles, changed approvals, different generator/runtime behavior or nonreproducible ordering can fail the exact-replay gate. Investigate rather than weakening comparison tolerances. A new schema or fabricated input workflow requires explicit policy/code review and tests. Never add production data to this policy.

## Run in Databricks

Keep `notebooks/`, `src/` and `scripts/` together. Notebook 08 installs `openpyxl==3.1.5`; Databricks supplies Spark, NumPy, pandas and PyArrow. The pipeline identity needs read access to the pinned SOURCE/generated snapshots and profiles, access to the development schema workbook, write access to the private export directory, and permission to append the private export audit table.

Deploy the existing bundle with your normal target. `resources/demo_dataset_export.job.yml` adds the **separate, unscheduled** `sage-private-demo-dataset-export` job. This standalone private job remains available. The main pipeline now also calls the same implementations through its dedicated Notebook 10 verification task; see [automated export/publication](automated-demo-publication.md). Run it only after the original validation/reporting sequence succeeds, supplying:

| Parameter | Value |
| --- | --- |
| `release_mode` | `DEMO_ONLY` |
| `dataset_version` | New immutable version, e.g. `sage-demo-v1` or `sage-demo-v1.1` |
| `source_run_id` | Exact completed fabricated SOURCE run |
| `batch_id` | Same reviewed batch used by generation |
| `generation_id` | Exact validated generation |
| `generated_run_id` | Its completed GENERATED profile |
| `privacy_assessment_id` | Current completed assessment for those snapshots |

Alternatively, open `notebooks/08_Demo_Dataset_Export.py` and supply the same widgets. Never display exported rows in notebook outputs. A failure returns a fixed reason, not a rejected record. The maximum is 250,000 rows per table and 512 MiB total CSV bytes; larger exports need review.

After redeploying job settings, start a new export run with all parameters explicitly supplied rather than assuming a repaired task inherited them. The mode defaults to DISABLED and missing parameters stop before export. An unsuccessful attempt without a ready artifact can reuse its version; a successful version cannot be overwritten.

## Files and private location

The fixed destination is outside the publisher-readable reporting Volume:

```text
/Volumes/workspace/default/scotia/demo_dataset_exports/<dataset_version>/
  PERSON.csv
  CUSTOMER_ACCOUNT_REL.csv
  CUSTOMER_RELATIONSHIP.csv
  TKQ_ACCOUNT.csv
  TKQ_ACCOUNT_BALANCE.csv
  TRADELINES.csv
  data_dictionary.md
  metadata.json
  SAGE_DEMO_ONLY.zip
  demo-preview.json
  _SUCCESS
```

The ZIP contains exactly six CSVs, the dictionary and metadata. CSVs retain every reviewed saved column and record; IDs, references, amounts, dates and null patterns are unchanged. CSV is UTF-8/comma-delimited; `\N` denotes NULL and empty text stays empty. Import identifiers as text. Dates/timestamps use ISO 8601; Spark timestamps use UTC and TIMESTAMP_NTZ values have no timezone.

New exports also write a separate [bounded preview JSON](records-preview.md): 15 selected records per table, six tables, at most 96 KiB, with a reviewed column subset and no personal date/gender combination. It is not added to the ZIP. Its hash is bound to metadata, the export audit and `_SUCCESS`; a failure prevents readiness. The preview can later populate the overview independently from the Validation Report. Existing `sage-demo-v1` files remain immutable.

ZIP assembly uses a temporary private Databricks driver directory, then sequentially copies the closed archive to the Volume and verifies its hash and contents. Direct ZIP construction on a Volume is unsupported because ZIP backpatches headers. Driver scratch is removed afterwards; no dataset is downloaded to a developer's computer.

The dictionary includes all columns/types, table purposes and relationship keys. In particular, account/balance snapshots join on **ACCOUNT_ID + BUSINESSEFFECTIVEDATE**; relationship endpoints and tradeline customer keys reference PERSON. TRADELINES account numbers do not reference internal account IDs.

Metadata contains dataset/schema version, generation date from the generation audit, export time, seed, table counts, CSV byte sizes/checksums, DEMO_ONLY scope and unchanged aggregate privacy findings. It omits internal run IDs, credentials and row examples. Private `workspace.synthetic_profile.demo_dataset_exports` retains exact IDs, versions and replay-proof metadata for audit.

Only a directory with the final `_SUCCESS` receipt is ready. Its ZIP hash must agree with that receipt. CSV hashes and ZIP member integrity are verified. Existing versions are never overwritten; failed writes remove only that attempt's new directory. Missing readiness is not a usable export, even if an audit record exists.

The GitHub Actions allowlist excludes the export folder, CSVs and ZIP. Do not copy that folder into `docs/`, the reporting Volume or Git. Only the separately bounded, verified preview JSON is prepared for the overview, under its [closed contract](records-preview.md). CSV/ZIP files are ignored locally, but that is not a distribution control. A future HTML dataset download needs a **separate explicit publication decision** for the specific artifact and its unchanged privacy disclosure. No publication is authorized by this export.

## Verification

Run the normal Python tests, including `tests/test_demo_export.py`. Fabricated tests cover explicit mode/version, missing provenance, exact multiset comparison, script hash, schema/secret/formula rejection, CSV/null/key preservation, budgets, six-table ZIP integrity and privacy-state retention. Databricks execution supplies the necessary live snapshot/replay/FUSE integration verification. At completion, Notebook 08 reports only counts, sizes and the private location.

### First private export verified

The live `sage-demo-v1` export completed successfully with seed 42 and 93,059 records. Exact SOURCE and generated reproduction passed for every table; schema/content screening, CSV manifests, ZIP integrity, saved audit and final `_SUCCESS` checksum were verified. The private metadata retains REVIEW_REQUIRED, 14 near matches and eight SOURCE-rare category matches. None of the 25 saved privacy checks was relabelled or overwritten.

| CSV | Rows | Bytes |
| --- | ---: | ---: |
| PERSON.csv | 10,000 | 1,236,687 |
| CUSTOMER_ACCOUNT_REL.csv | 17,313 | 695,302 |
| CUSTOMER_RELATIONSHIP.csv | 1,120 | 60,068 |
| TKQ_ACCOUNT.csv | 17,313 | 12,821,558 |
| TKQ_ACCOUNT_BALANCE.csv | 17,313 | 8,225,414 |
| TRADELINES.csv | 30,000 | 10,900,444 |

The ZIP is **9,631,069 bytes**, under `/Volumes/workspace/default/scotia/demo_dataset_exports/sage-demo-v1/`. Its eight members include the six CSVs, `data_dictionary.md` and `metadata.json`. The metadata records the original generation timestamp separately from export time. No CSV or ZIP was downloaded locally or published. The original ZIP-on-Volume failure was cleaned up; a fresh explicit-parameter run passed after the driver-scratch copy fix. Local verification passed **224 Python tests**, including the Volume-write regression. Main generation, privacy guard, website assets and public reporting JSON are unchanged.
