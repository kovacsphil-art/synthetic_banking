# Demo download verification

The public fabricated demo `sage-demo-v23531186251808934832001379991` was rechecked against its version-pinned manifest, current sanitized report and GitHub Release. This checks the delivered package; it does not replace the Databricks fabricated-origin replay, explicit release authorization or privacy screening.

| File | Records | Bytes | Download / SHA-256 |
| --- | ---: | ---: | --- |
| PERSON.csv | 10,000 | 1,236,687 | PASS |
| CUSTOMER_ACCOUNT_REL.csv | 17,313 | 695,302 | PASS |
| CUSTOMER_RELATIONSHIP.csv | 1,120 | 60,068 | PASS |
| TKQ_ACCOUNT.csv | 17,313 | 12,821,558 | PASS |
| TKQ_ACCOUNT_BALANCE.csv | 17,313 | 8,225,414 | PASS |
| TRADELINES.csv | 30,000 | 10,900,444 | PASS |
| SAGE_DEMO_ONLY.zip | 93,059 across six tables | 9,631,178 | PASS |
| data_dictionary.md | — | 23,580 | PASS |

Every public URL returned HTTP 200; downloaded bytes matched the manifest's sizes and hashes. The existing `verify_demo_package` validator confirmed:

- All six complete CSV row counts and synthetic identifier formats; zero orphan customer/account references.
- Exact account/balance snapshot-key alignment on `ACCOUNT_ID` plus `BUSINESSEFFECTIVEDATE`, with 100% join coverage.
- All 15 preview records per table match their CSV counterparts for every displayed field.
- ZIP CRC integrity and exactly eight members: six identical CSVs, the dictionary and `metadata.json`.
- Metadata version, generation date, table counts and privacy status agree with the manifest. Seed is 42. The dictionary describes all six tables and their relationship keys.

Only aggregate verification results were retained. Temporary downloaded records were removed from ignored local scratch; no CSV or ZIP was added to Git or Pages.

## Stakeholder experience

[Explore records](https://kovacsphil-art.github.io/synthetic_banking/#explore-records) loads only the small verified preview. Select a table, inspect its counts and column guide, then download the matching CSV or complete ZIP. [Downloads](https://kovacsphil-art.github.io/synthetic_banking/#download-dataset) shows six table counts/sizes, package dates, the dictionary and an expandable **Using the demo files** guide. `metadata.json` is inside the ZIP, not a separate Release asset; no new public-file contract is needed.

The guide explains identifier imports, the `\N` null marker and how tables connect. Unpublished, withdrawn, missing, mismatched or unverifiable exports retain disabled controls. The page still checks the current report, bounded preview fingerprint and canonical GitHub Release assets before enabling links. See [publication controls and disable instructions](automated-demo-publication.md).

## Release boundary and remaining limitations

This exact, already-authorized **DEMO_ONLY** fabricated package has no outstanding download/integrity blocker. Standard privacy screening remains **REVIEW_REQUIRED**, including 14 near matches and eight SOURCE-rare pattern matches. General dataset release and any production-derived distribution remain blocked. No privacy result was relabelled or waived.

The ZIP's `publication_authorized: false` records the original private export event. Its later explicit publication is recorded by the separate PUBLISHED manifest and immutable GitHub Release; the original ZIP is not rewritten. These are different lifecycle events.

The preview contains selected fields and 15 rows per table; linked records need not be present in those small samples. GitHub outages/rate limits may temporarily disable download checks. Already-public Release files cannot be recalled from people who downloaded them. A different cohort still requires its own exact provenance, validation, explicit DEMO_ONLY opt-in and publication checks.
