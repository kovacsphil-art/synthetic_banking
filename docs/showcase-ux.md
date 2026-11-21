# Showcase interaction review

This polish preserves the executive layout, red/charcoal palette, measured reporting JSON, preview records, validation calculations and privacy/download gates. Both pages remain static, without new libraries, external fonts or backend services.

| Change | Design principle applied |
| --- | --- |
| The same Overview / Pipeline / Validation Report / Synthetic Data Explorer / Downloads links on both pages, with page indicators and footer exits | Norman: mapping and conceptual model. Nielsen: consistency, recognition and user control. |
| Consistent focus outlines, touch targets, dropdown chevrons, restrained hover feedback and explicit selected/disabled states | Norman: signifiers and feedback. Nielsen: consistency and error prevention. |
| Visible sort direction and an adjacent explanation when a variable selector is disabled | Nielsen: system status and help in context. |
| Metric help opens on focus/click/tap as well as hover; Escape dismisses it, including hover-only previews | Norman: discoverability. Nielsen: user control and freedom. |
| Clear loading labels, retry actions and missing-data messages with no substitute records or statistics | Nielsen: visibility and recovery from errors. |
| More readable chart labels, SOURCE/Synthetic table headings, expandable chart values, scrollable wide tables and reduced-motion support | Nielsen: minimalist presentation and flexible access. |
| Purpose → pipeline and AI controls → measured findings, before detailed methodology and demo browsing | Norman: coherent conceptual model. Nielsen: natural reading order and minimalist design. |
| Three primary report destinations, with detailed evidence links in a native keyboard/touch disclosure | Nielsen: recognition and progressive disclosure. No horizontally hidden navigation links or new menu system. |
| Report section deep links restored after JSON renders, without taking focus back after interaction or refresh | Norman: mapping and feedback. Nielsen: user control and predictable navigation. |
| Plain-language SOURCE definition and distinct explanations of privacy review versus verified fabricated-demo availability | Nielsen: match with users’ language and error prevention. No release gate changes. |

Reference principles: [Don Norman, The Design of Everyday Things](https://jnd.org/books/the-design-of-everyday-things-revised-and-expanded-edition/) and [Nielsen Norman Group, 10 Usability Heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/). These are design guidelines, not a claim of usability certification.

## Verification

- JavaScript checks cover pipeline hover/focus/click/touch/reset, tabs and keyboard movement, variable/match selection, sorting, help dismissal, loading/retry and missing/sparse evidence.
- Additional checks lock the executive reading order, all evidence-link destinations, delayed report anchors, focus preservation, and the separate privacy/demo explanation.
- Existing tests retain malformed-metadata, withdrawn-export, preview/version/hash mismatch, missing Release assets and privacy/provenance rejection cases.
- Browser checks cover desktop and narrow mobile layouts, navigation between the three experiences, all six preview tables, expandable descriptions/chart values, keyboard table scrolling and missing-JSON states. Missing-data QA uses temporary copies of public UI assets without JSON; the saved reporting/preview artifacts are unchanged.
- Switching tables or validation variables reuses loaded data. Preview/Release verification remains bounded and shared between the two demo sections; full CSVs and ZIPs are never fetched for exploration. No background polling, new frameworks or external UI resources are added.

## Remaining limits

### Variable-first validation summary

The Validation Report now leads with selected-variable outcomes, with separate secondary scopes for additional statistical checks and all-field missingness. Core check counts, pass definitions, non-comparability explanations and trivial-zero exclusions use native disclosures. Privacy REVIEW_REQUIRED stays a separate assessment. Findings use interpretation → SOURCE/synthetic values → potential business consequence, with technical details available on demand. The overview reuses a compact version of the same variable-first component.

The three primary counts were checked within the initial viewport at desktop and 390 × 844 mobile dimensions. Native disclosures work with Enter, table filters remain reversible, and wide evidence tables remain keyboard-focusable scroll regions. Automated checks reconcile the current three scopes, verify data-driven rendering and confirm that rendering leaves the report unchanged. This is interface verification, not evidence from a stakeholder comprehension study.

Wide data tables intentionally need horizontal scrolling on phones. The explorer shows only 15 saved rows and selected columns per table; linked records may fall outside that preview. The public validation contract covers selected variables and measured points, rather than full distribution detail. Release API outages or rate limits can temporarily disable downloads. Testing here covers the available Chromium browser and automated interaction checks, not a full browser/device matrix, assistive-technology audit or stakeholder usability study.


## Interpretation and contextual help

The findings now separate evidence qualification from unchanged tolerance grades. Three plain-language strengths and three gaps are visible, with labeled SOURCE/synthetic values, signed differences and business implications; remaining findings and exclusion explanations are native disclosures. Shared help opens on hover, keyboard focus or tap, closes with Escape/blur/outside interaction, and expands in flow to avoid obscuring measured values. Primary counts keep separate denominators and privacy remains an independent assessment. No full distribution is implied by endpoints, constant values or selected percentiles.
