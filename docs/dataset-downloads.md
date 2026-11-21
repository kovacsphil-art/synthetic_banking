# Download Synthetic Dataset

The overview provides one complete-ZIP control, six individual CSV controls, and a dictionary control. File sizes, table descriptions and full record counts come from a **verified DEMO_ONLY export**, independently from the aggregate Validation Report. The disclaimer identifies illustrative synthetic records derived from fabricated development inputs, not actual customers or production-representative banking data.

**Current state: verified export, UNPUBLISHED.** The prepared manifest describes `sage-demo-v1.1`: 93,059 records, a 9,631,148-byte ZIP and a 23,548-byte dictionary. All buttons are disabled because no files have been published for this feature. No Release was created, no assets uploaded, and no Git push or Pages deployment performed. Privacy remains REVIEW_REQUIRED. General privacy clearance and production-data release guards are unchanged.

## Automated workflow

The main job can now prepare these same files automatically after validation, and GitHub Actions can publish a completely verified draft Release when both explicit opt-ins are enabled. The current local artifacts remain unpublished. See [enable/trigger, lineage and independent disable controls](automated-demo-publication.md). The manual preparation below remains available.

## How links are resolved

`downloads.js` reads the small same-origin `dataset-downloads.json` (maximum 16 KiB), then the existing bounded `demo-preview.json`. It verifies the closed manifest, explicit DEMO_ONLY/fabricated origin, version, exact preview SHA-256, table counts and unchanged privacy status. The current sanitized report must also contain matching `demo_dataset.dataset_version`, `release_mode` and `preview_sha256`, with matching table counts and privacy status. A historical report without this reference cannot enable downloads. The preview and download package must refer to the same immutable demo version; the latest aggregate report is not used to choose a dataset.

For a PUBLISHED manifest, the browser makes one credential-free public metadata request:

```text
https://api.github.com/repos/kovacsphil-art/synthetic_banking/releases/tags/<dataset_version>
```

The Release must be published, not draft or prerelease, and have the exact tag. All eight expected assets must have matching filenames, byte sizes, SHA-256 digests and canonical HTTPS download URLs. A missing digest also prevents activation. API response descriptions and unrelated metadata are never displayed. GitHub documents these asset fields in its [Release assets API](https://docs.github.com/en/rest/releases/assets).

Only after those checks does the page construct links:

```text
https://github.com/kovacsphil-art/synthetic_banking/releases/download/<dataset_version>/<filename>
```

Filenames are fixed: `SAGE_DEMO_ONLY.zip`, `data_dictionary.md`, and the six physical table names with `.csv`. A published manifest also records the eight verified links under `download_urls`. These are accepted only when they exactly match the fixed repository, displayed version and allowlisted filenames; arbitrary hosts, paths and workflow identifiers are rejected. Links are pinned to a specific version, never `latest`; see [GitHub Release links](https://docs.github.com/en/repositories/releasing-projects-on-github/linking-to-releases). The browser does not fetch CSV/ZIP contents to check availability; clicking a verified link starts the normal HTTPS asset download. Cross-origin download disposition is handled by GitHub's asset server.

## Preparation and later manual publication

1. Complete the existing private demo export. Keep the six original CSVs, ZIP, dictionary, metadata and readiness receipt in the private Volume. Do not commit large data files or copy them into `docs/`.
2. Run `notebooks/09_Prepare_Downloads.py` with the exact private `export_id` and `dataset_version`. It is a separate, read-only utility, not a new task in the generation pipeline. It checks the authoritative export audit, both six-table exact-replay proofs, current matching privacy evidence, `_SUCCESS`, all file checksums, and every ZIP member against the standalone files. It returns only the public-safe manifest and always sets UNPUBLISHED. Missing/uncertain/changed evidence fails closed. No customer records are returned.
3. Validate that result against [`reporting/dataset-downloads.schema.json`](reporting/dataset-downloads.schema.json) and `downloads.js.normalizeManifest`; save it as `docs/dataset-downloads.json`. It must match the local verified demo preview. The public manifest contains filenames, counts, sizes and checksums, not Databricks locations, credentials or internal run/export/assessment IDs.
4. **Only after a separate explicit publication decision**, manually create a GitHub Release tagged with that dataset version and attach the eight original files. Use the generated dataset ZIP, not GitHub's automatically generated source-code archive. Upload original bytes; re-saving CSVs in a spreadsheet changes their checksums. This manual preparation utility does not create Releases, upload files or store credentials. The separate opt-in automated branch creates verified Releases as described above.
5. Once the assets are public, run `node scripts/verify_dataset_downloads.cjs`. This read-only GitHub check verifies the local preview and all eight asset metadata digests. On success it changes only the local manifest to PUBLISHED and records `publication_checked_at`; on failure the prior manifest is retained. It will not reactivate a WITHDRAWN manifest. The script does not upload files, commit, push, or deploy.
6. Review the manifest and publish the prepared static-site changes only when authorized. The Pages workflow copies `downloads.js` and matching download/preview JSON only on its enabled verified demo branch; it never copies complete datasets. Manual metadata preparation alone does not enable that automated branch. Its existing successful-pipeline and public-report checks remain in place. The reporting-only Databricks service principal needs no new access or secrets.

Export metadata records its initial private packaging (`publication_authorized: false`). The later public manifest separately records Release availability following the manual publication decision; do not edit immutable CSVs/ZIPs or relabel privacy findings. DEMO_ONLY origin verification is limited to the approved fabricated workflow and is not a production-data privacy exception or anonymization certification. Trusted export preparation and publication access controls establish provenance; the static browser cannot independently rerun private Databricks lineage checks.

## Missing and outdated exports

| Condition | Website behavior |
| --- | --- |
| Manifest absent, invalid, oversized, or not verified DEMO_ONLY | Downloads unavailable; no active file links or invented sizes/counts |
| Preview absent or unverifiable | Downloads unavailable; current cohort identity cannot be confirmed |
| Report/preview version, checksum, counts or privacy status differ | Downloads out of date; no fallback to an older or latest Release |
| Verified export is UNPUBLISHED | Real verified file details shown; all eight controls disabled |
| WITHDRAWN | Explicit withdrawal state; all controls disabled |
| Release missing/draft/prerelease, missing asset, wrong size/digest/URL | Whole set disabled; partial or mixed datasets are not offered |
| GitHub offline/rate-limited or request times out | Temporarily unavailable; Recheck availability retries without exposing response bodies |
| Matching PUBLISHED export and all eight assets verified | ZIP, dictionary and six CSV links enabled |

Availability is checked on page load and Recheck availability. An already-open static page is not a real-time revocation service; if an asset disappears after checking, GitHub may return an error until the next recheck. To withdraw the package, set `publication_status` to WITHDRAWN, `publication_checked_at` to null and remove `download_urls`, deploy that manifest, and manage Release assets manually. Preparing a new preview disables old mismatched downloads until a newly verified manifest is supplied. Missing download metadata does not block the record explorer, methodology or Validation Report.

## Public manifest fields

| Field | Meaning |
| --- | --- |
| `schema_version`, `release_mode`, `baseline`, `verification` | `1.0`, `DEMO_ONLY`, `FABRICATED_DEVELOPMENT`, `VERIFIED_DEMO_ONLY` |
| `dataset_version` | Exact immutable export version and Release tag |
| `generation_date`, `exported_at`, `verified_at` | UTC timestamps for generation, export and private file verification |
| `privacy_status` | Unchanged PASS or REVIEW_REQUIRED screen, not release certification |
| `preview_sha256` | Exact companion preview fingerprint |
| `repository` | Fixed public Release repository; no arbitrary URL configuration |
| `publication_status`, `publication_checked_at` | UNPUBLISHED / PUBLISHED / WITHDRAWN and the later public metadata check time (null until PUBLISHED) |
| `download_urls` (optional, PUBLISHED only) | Eight canonical, verified HTTPS Release links keyed by ZIP, DICTIONARY and physical table name |
| `assets[]` | Exactly eight fixed keys/filenames with byte counts, SHA-256 digests and CSV row counts; ZIP/dictionary rows are null |

Regenerate the closed schema with `scripts/build_download_schema.py` after a reviewed contract change. Tests use fabricated files/API responses and cover provenance failures, changed files, URL constraints, stale previews, unavailable assets, privacy retention and both enabled/disabled controls.
