# Explore synthetic records

The overview's **Synthetic Data Explorer** displays only `docs/demo-preview.json`: at most 15 selected records per table. It reuses the existing download verification checks to match the preview fingerprint, DEMO_ONLY manifest and current reporting metadata. There is no browser connection to Databricks and no CSV/ZIP fetch until a visitor follows a download link. Selecting another table reuses the bounded JSON already verified; validation charts and calculations are unchanged.

Visitors can choose any of the six tables, see the first **15 records in export key order**, expand a column guide, and horizontally scroll the keyboard-focusable table. Selected columns make the preview readable; the full row count, full column count and number of columns shown are displayed separately. Customer birth date, customer-since date, gender, free-text descriptions and contact fields are not projected. Relationship guidance explains synthetic IDs and account/balance composite snapshot keys. A linked record can exist outside these first 15 rows; preview omission is not a broken reference in the full dataset.

Every view is labelled **Demo data — not actual customer records**. Missing values say Not recorded. Preview metadata identifies its demo dataset version and export date, separately from the statistical validation results. Privacy REVIEW_REQUIRED remains visible. Highlighted synthetic identifiers and per-table relationship notes explain how the records connect. Column descriptions are available in the expandable guide and table-header descriptions.

The selected table has two download controls: its full CSV and the complete six-table ZIP. Both reuse the [download section's](dataset-downloads.md) verified, published, version-pinned Release URLs and fail-closed checks; selecting a table never fetches either file. Unpublished exports or unavailable Release checks retain a fingerprint-verified preview with disabled download buttons. Missing, mismatched, unverified or withdrawn metadata hides the preview and disables its links, with Retry and no replacement records. The two sections share their initial in-flight checks; retries fetch fresh evidence. A preview is not a representative sample or a statistical validation chart.

## Producer and provenance

The existing private [demo exporter](demo-dataset-export.md) produces the preview **during** a successful DEMO_ONLY export, after exact fabricated SOURCE/generated reproduction, schema checks and the full content scan. It collects at most 15 selected rows per table, never complete tables for preview construction. The preview retains synthetic identifiers and saved values; it does not modify Delta records or generation behavior. Full-table counts come from the same pinned snapshots.

`src/synthetic_banking/demo_preview.py` owns the fixed table/column catalog and descriptions. `scripts/build_demo_preview_schema.py` generates the closed JSON Schema and static `records-config.js`; run it with `src` on PYTHONPATH after an approved catalog change. No build step is required to serve the checked-in website.

The new file sits beside the private export's CSVs, outside the ZIP. Its byte count and SHA-256 appear in export metadata and the private execution receipt; `_SUCCESS` includes `preview_sha256`. A preview-generation failure fails the whole new export attempt. Existing immutable exports remain unchanged; use a new version such as `sage-demo-v1.1`.

## JSON contract

See [`reporting/demo-preview.schema.json`](reporting/demo-preview.schema.json). The maximum is **96 KiB**, six tables and 15 rows per table (90 rows total). The browser and publication checks enforce the row cap and fixed column catalog as well as synthetic-key patterns.

| Field | Expected value |
| --- | --- |
| `schema_version` | `1.0` |
| `release_mode` | `DEMO_ONLY` |
| `baseline` | `FABRICATED_DEVELOPMENT` |
| `dataset_version` | Versioned `sage-demo-v…` label; no internal UUID |
| `generated_at` | UTC ISO 8601 preview export timestamp |
| `privacy_status` | Unchanged `PASS` or `REVIEW_REQUIRED` screening status; never a publication approval |
| `preview_row_limit` | `15` |
| `tables[]` | Exactly PERSON, CUSTOMER_ACCOUNT_REL, CUSTOMER_RELATIONSHIP, TKQ_ACCOUNT, TKQ_ACCOUNT_BALANCE and TRADELINES, in that order |
| `tables[].name` | Fixed physical table name |
| `tables[].total_rows` | Full saved table row count |
| `tables[].total_columns` | Full reviewed schema width, including columns not shown |
| `tables[].columns` | Fixed ordered subset of field names from the catalog |
| `tables[].rows` | Arrays aligned with those columns; exactly `min(15, total_rows)` records; only validated strings, finite numbers or null |

Descriptions and relationship explanations come from the fixed catalog, not incoming row text. No SOURCE rows, run/batch/proposal/assessment IDs, file paths, secrets or links are in the preview contract. Dates and amounts belong exclusively to the verified fabricated generated cohort. Values use textContent; unknown fields, malformed types, unexpected keys, secret-like codes, oversize files and unsupported origins are rejected. A missing/invalid artifact produces an unavailable state with Retry, never substitute records or a full-dataset request.

## Prepare for a later publication

1. Run the separate private demo export with explicit IDs and a new dataset version.
2. Require SUCCESS, `_SUCCESS`, matching dataset version and preview checksum. Validate the small JSON against the closed schema and `records.js.normalizePreview`.
3. Copy **only** that verified preview JSON to `docs/demo-preview.json`; never copy the export folder, CSVs or ZIP into the website or reporting Volume.
4. Test desktop/mobile and missing-file states. Publish only when separately authorized.

The GitHub Pages allowlist includes `records.js`, `records-config.js`, `downloads.js` and verified preview/download metadata when enabled. The existing publisher remains responsible for export verification and publication. The UI adds no credentials, dataset retrieval, generation or export changes. Missing evidence leaves the explorer unavailable while the rest of the site works.

Local checks: the usual Python suite, plus `node --test tests/test_records.cjs` and the existing website suites. Tests use fabricated records and exercise caps, projection, exact metadata, secret/schema rejection, selection, keyboard-scroll semantics, missing values, retries and fetch failure handling.

## Historical verified preview snapshot

`docs/demo-preview.json` was generated by the successful private **sage-demo-v1.1** export. It is **7,884 bytes**, with 90 selected fabricated records in total. Its checksum agrees with the export receipt, metadata and `_SUCCESS`; its schema and browser contract pass. All six CSV checksums are identical to the preceding demo export, so no generated records changed. Privacy remains REVIEW_REQUIRED. The website has not been pushed or deployed for this update.

Verification passed **228 Python tests and 41 JavaScript tests**. Browser checks covered all six selections, expandable descriptions, null values, desktop and 390px mobile layout, keyboard horizontal scrolling, and missing-preview/retry recovery while the aggregate results remained available. The dedicated Validation Report, main pipeline configuration, generation code and public reporting JSON are unchanged.

| Table | Full rows | Full columns | Preview columns | Preview rows |
| --- | ---: | ---: | ---: | ---: |
| PERSON | 10,000 | 19 | 6 | 15 |
| CUSTOMER_ACCOUNT_REL | 17,313 | 6 | 6 | 15 |
| CUSTOMER_RELATIONSHIP | 1,120 | 9 | 6 | 15 |
| TKQ_ACCOUNT | 17,313 | 100 | 8 | 15 |
| TKQ_ACCOUNT_BALANCE | 17,313 | 48 | 5 | 15 |
| TRADELINES | 30,000 | 38 | 7 | 15 |

## Automated refresh

The main workflow can now create the same preview through its dedicated verified demo task. With both export and publication explicitly enabled, Actions refreshes the preview, download manifest and sanitized report as one matched cohort. Disabled publication omits preview/download metadata from the next Pages build; missing metadata leaves the explorer unavailable. Failed runs leave the previously deployed cohort intact. See [the automated demo runbook](automated-demo-publication.md).
