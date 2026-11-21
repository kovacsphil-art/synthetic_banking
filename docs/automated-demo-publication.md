# Automated fabricated demo exports

**Live integration verified.** All nine Databricks tasks succeeded using the reviewed fabricated SOURCE/batch. [GitHub Actions publication](https://github.com/kovacsphil-art/synthetic_banking/actions/runs/44859302829) published the complete [versioned Release](https://github.com/kovacsphil-art/synthetic_banking/releases/tag/sage-demo-v23531186251808934832001379991) and deployed [Pages downloads](https://kovacsphil-art.github.io/synthetic_banking/#download-dataset).

- All six public CSVs, ZIP and dictionary returned successfully and matched checksums.
- Counts: PERSON 10,000; CUSTOMER_ACCOUNT_REL 17,313; CUSTOMER_RELATIONSHIP 1,120; TKQ_ACCOUNT 17,313; TKQ_ACCOUNT_BALANCE 17,313; TRADELINES 30,000.
- Every preview cell matched its CSV; all references were valid and account/balance snapshot coverage was 100%.
- Privacy remained REVIEW_REQUIRED. Generation and standard privacy/Validation Report code were unchanged.
- The [incomplete-run guard check](https://github.com/kovacsphil-art/synthetic_banking/actions/runs/44858023691) failed intentionally before publication and left the previous Pages deployment unchanged. A real draft-URL upload failure also skipped deployment; repair reused the same verified assets. No partial dataset became public.

The GitHub publication variable is enabled and existing secrets/permissions are sufficient. For future demo cohorts, select `demo_release_mode=DEMO_ONLY` and complete ordinary rule review; no manual Release upload is required. Keep DISABLED for aggregate-only runs. Rotate the existing Databricks OAuth secret before expiry.

The main job now has **nine tasks**. Existing modeling, approval, privacy and fidelity logic is unchanged:

```text
source_profile → llm_proposal → approval_check → synthetic_generation
  → privacy_check → generated_profile → validate
  → demo_export_verification → reporting
  → GitHub Actions: check report → optional verified Release → metadata commit → Pages
```

`demo_export_verification` runs Notebook 10, which calls the existing Notebook 08/09 implementations (`export_demo_dataset` and `prepare_download_manifest`). The standalone private export job and interactive notebooks remain available. No new statistical dependencies or LLM approvals are introduced.

## Enable and trigger

1. Deploy the updated bundle using the existing [workflow instructions](workflow.md). Use a test destination first. The pipeline identity needs its existing private export/source snapshot permissions and write access to the reporting Volume. Keep `notebooks/`, `scripts/` and `src/` together. Notebook 10 installs the exporter's existing `openpyxl==3.1.5` dependency.
2. Run **synthetic-banking-controlled-pipeline → Run now with different parameters**, setting **`demo_release_mode=DEMO_ONLY`**. The default is DISABLED. SOURCE profiling and proposals either run normally or reuse the existing explicitly paired `reuse_source_run_id` / `reuse_batch_id`; review stops work exactly as before. Every downstream generation/profile ID is passed automatically. Do not manually substitute a generation ID.
3. To allow future automatic public distribution, explicitly set the GitHub repository Actions variable **`SAGE_PUBLISH_DEMO_DATASETS=true`**. Until then no dataset files are retrieved by Actions, uploaded, or included in Pages. This is a public-data release decision: the enabled workflow uploads verified fabricated row records to GitHub Releases. It does not clear ordinary privacy findings or authorize any production-derived data.
4. After the nine-task run succeeds, the existing scheduled **Publish validated showcase** workflow retrieves it. To trigger immediately, use **Actions → Publish validated showcase → Run workflow** and optionally select that successful numeric pipeline run ID. No new GitHub secret is needed: the Release step uses the existing short-lived `GITHUB_TOKEN` with `contents: write`. Databricks secrets remain scoped to the retrieval step.

The existing reporting-only identity still has no SOURCE/generated-table access. Its reporting Volume now contains **verified fabricated demo rows as well as aggregates** when DEMO_ONLY is enabled. Review the Volume's readers and retention policy before enabling: copying files there makes them readable to principals already authorized for that Volume. The existing reporting identity and secrets are reused; no additional SOURCE/generated-table access is required.

## Exact lineage and eligibility

| Handoff | Producer → consumer | Verification |
| --- | --- | --- |
| SOURCE, batch, generation, GENERATED IDs | `validate` → demo task and reporting | Same completed profile pair and saved generated Delta versions |
| Privacy assessment ID | `privacy_check` → demo task and reporting | Current completed assessment for those exact snapshots; privacy findings retained |
| Mode | Job `demo_release_mode` → demo task `release_mode` | Only explicit DEMO_ONLY enables export; DISABLED is an inexpensive no-export success |
| Demo eligibility, version | Demo task → reporting | `VERIFIED_DEMO_ONLY` plus opaque immutable dataset version; otherwise DISABLED |
| Private readiness receipt | Demo task → reporting | All five IDs, manifest checksum, all asset/preview checksums and version must match |
| Public cohort reference | Reporting → Actions/browser | Optional `demo_dataset` contains only version, DEMO_ONLY mode and preview SHA-256 |

SOURCE origin is proven by **full six-table exact multiset replay** of the approved fake-record script, pinned script hash, schema, seed and population. Generated snapshots and rule audit must exactly replay the existing generator with pinned SOURCE statistics, seed, size and reviewed batch. Closed schema and full content/secret scans also apply. A path, catalog/table name, Boolean or label cannot establish origin. Missing, uncertain, production-derived, changed, nonreproducible or blocked evidence fails the task before a public-ready package exists. Privacy PASS/REVIEW_REQUIRED and demo eligibility are separate decisions; REVIEW_REQUIRED is never rewritten.

The dataset version is an opaque numeric digest of the five private handoff IDs, e.g. `sage-demo-v12345678901234567890`. No private UUID or workflow run ID is placed in public filenames or URLs. Repairs of the same generation reuse its immutable export only after audit, provenance and checksums pass again; unrelated exports cannot be substituted.

`.gitattributes` preserves LF bytes for the pinned fake-record script and preview JSON, keeping their fingerprints consistent between Windows, Databricks and GitHub Actions.

## Files and readiness

The exporter first writes its original immutable private version with six CSVs, ZIP, dictionary, metadata, bounded preview and `_SUCCESS`. After independent verification, the demo task copies **only** the eight public assets and bounded preview into:

```text
<report_output_dir>/runs/<job-run-id>/demo/
  SAGE_DEMO_ONLY.zip
  data_dictionary.md
  PERSON.csv, CUSTOMER_ACCOUNT_REL.csv, CUSTOMER_RELATIONSHIP.csv
  TKQ_ACCOUNT.csv, TKQ_ACCOUNT_BALANCE.csv, TRADELINES.csv
  demo-preview.json
  dataset-downloads.json
  _READY.json                 # private lineage receipt; never published
```

`_READY.json` is written last. Reporting reads it, checks all five IDs and file fingerprints, adds the public `demo_dataset` reference, and returns a private report checksum receipt. Without readiness the report cannot claim a demo cohort. The public manifest keeps its closed version-1 schema and starts UNPUBLISHED; no internal paths/IDs or credentials are copied to it.

The private reporting receipt also pins the exact download-manifest SHA-256; later changes to staged metadata cannot redirect the publisher to different bytes. ZIP metadata retains `publication_authorized: false` for the **initial private export event**. Later explicit publication is recorded by the separate PUBLISHED manifest and GitHub Release; it does not edit an immutable export or imply privacy clearance.

Actions downloads fixed filenames only from that successful run's folder, validates the closed schemas, report/preview/version/privacy/count bindings and every byte size/checksum. Both the Databricks stage and publisher parse all six CSVs, require valid synthetic IDs and customer/account references, verify exact account/balance snapshot coverage, compare every preview value with its CSV counterpart, and check all eight ZIP members. All bytes stay in ignored runner scratch. It creates/resumes a **draft** versioned GitHub Release and uploads all eight originals. Only a completely matching draft becomes public. It never replaces a conflicting existing asset or uses a moving `latest` link. Complete published matching Releases are reused on retries. See GitHub's [Release API](https://docs.github.com/en/rest/releases/releases) and [asset API](https://docs.github.com/en/rest/releases/assets).

After Release verification, Actions writes the eight canonical HTTPS asset links to optional `download_urls` (keys ZIP, DICTIONARY and the six table names), then marks the local manifest PUBLISHED and commits only `latest-pipeline.json`, `dataset-downloads.json` and the small `demo-preview.json`. Pages contains no complete CSV/ZIP files. The browser requires the same version/preview fingerprint/counts/privacy status in the current report, then rechecks the public Release sizes/digests before enabling downloads. Historical aggregate reports remain supported but cannot authorize downloads without this binding.

## Failure, repair and disable controls

- Failed validation, replay, export, copies or reporting leaves the job unsuccessful; Actions cannot select it. Existing public Downloads and Pages remain intact.
- Failed/partial uploads stay in a private draft; no new manifest is committed or site deployed. Retry resumes matching uploaded assets. GitHub may use private `untagged-…` URLs and omit drafts from lookup by tag until publication. The publisher finds the exact draft by repository listing and still verifies all names, sizes and SHA-256 digests; final public URLs must be canonical. A conflicting/starter/changed asset requires investigation; no automatic overwrite or deletion is attempted.
- A failure after a complete Release becomes public but before Git push/Pages can leave a **complete verified new Release** without a new site. The previous site remains intact; rerun Actions to reuse that Release and finish. Public Release creation and Pages deployment are not one atomic transaction.
- Set **`demo_release_mode=DISABLED`** to skip new export work while continuing profiling, generation, privacy, validation and reporting.
- Set **`SAGE_PUBLISH_DEMO_DATASETS=false`** (or remove it) to stop dataset retrieval/uploads and omit demo preview/download metadata from subsequent Pages builds. Aggregate reporting/publication continues. A successful aggregate-only run also omits these files. This intentional disable differs from a failed attempt, which leaves the prior deployment unchanged.
- These switches do not delete or revoke existing public Releases, tags or cached downloads. To withdraw already public files, manage those Releases explicitly and redeploy the disabled site. Public bytes already downloaded cannot be recalled.

Editing repository files alone does not deploy Databricks settings. The initial deployment and opt-in publication above are complete; redeploy explicitly after workflow/module changes and test both opt-in and disabled paths. Existing eight-task successful executions remain readable for aggregate publication during migration, but cannot qualify a demo export.

## Required GitHub permissions

The preparation job uses repository-scoped `contents: write` for the verified Release assets and metadata commit. The deployment job uses `pages: write` and `id-token: write` with the existing github-pages environment. No personal GitHub token is stored in Databricks or source files. Repository branch/environment rules must permit this workflow; no force push or protection bypass is implemented. Existing Databricks OAuth M2M values remain in Actions Secrets, with job/path/publication switches in Actions Variables.
