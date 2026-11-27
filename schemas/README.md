# Fabricated development schema

`RCAR_source_column_list.xlsx` contains schema metadata only: six table sheets and 219 field-name/type pairs. It contains no customer records, formulas, macros or external links.

The workbook is reconstructed from the existing reviewed [demo policy](../src/synthetic_banking/demo_export_policy.json), preserving each table's field order. The generated-only `_UTILIZATION_RATE` helper is excluded from the SOURCE schema. This is a supplied development schema, not a claim to reproduce an independently supplied original workbook byte for byte.

Upload the workbook to the directory configured by `SOURCE_DIR` before running Notebook 00. The default destination is:

```text
/Volumes/workspace/default/scotia/RCAR_source_column_list.xlsx
```

Each sheet starts at A1 with exactly `Source Column` and `Data type`. Keep the six sheet names and these headers unchanged. Do not add instruction sheets or customer records: the existing loader treats every sheet as a schema.

For a new installation, run Notebook 00 and then start a fresh SOURCE pipeline run as described in [setup](../docs/setup.md#2-establish-the-fabricated-source-baseline). Supplying this workbook does not approve proposals, establish privacy clearance or authorize public exports. Existing pinned SOURCE runs must still pass the unchanged exact-replay gates; do not replace inputs during an active run.
