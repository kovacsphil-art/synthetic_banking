# First controlled balance-rule pilot

Use the development Databricks Git checkout and its test output tables. Notebook 03 replaces the current generated tables in `workspace.synthetic_generated`. Run the notebooks serially so another generation does not replace the pilot batch during profiling.

## 1. Pin SOURCE run A

Pick one completed SOURCE run in the test workspace. Create it with Notebook 01 in `SOURCE` mode if the workspace has no eligible baseline.

```sql
SELECT run_id, started_at, completed_at
FROM workspace.synthetic_profile.profile_runs
WHERE profile_type = 'SOURCE'
  AND status = 'COMPLETED'
  AND completed_at IS NOT NULL
ORDER BY completed_at DESC, started_at DESC, run_id DESC;
```

Record the exact `run_id` as A. Keep the SOURCE staging tables and schema in place for this pilot.

## 2. Create one proposal batch and review one or two rules

In Notebook 02, run the widget setup cell if needed, then set `source_run_id` to A and `balance_pilot` to `ON`. Run the notebook once from the top. Record the persisted `batch_id` from the batch preview and confirm that its `source_run_id` is A and `scope_name` is `BALANCE_PILOT`. Keep this batch ID for review and generation. The model receives the pinned aggregate profile and a prompt scoped to the two existing balance dependencies.

Review the batch's proposals individually. A pilot candidate must target `TKQ_ACCOUNT_BALANCE`, have rule type `DERIVED`, and name exactly the two parents `TKQ_ACCOUNT.CREDIT_LIMIT_AMT` and `TKQ_ACCOUNT_BALANCE.CURRENT_BALANCE_AMT`. The registry accepts those qualified names and their corresponding bare column names.

| Eligible target | Existing implementation to review against |
| --- | --- |
| `AVAILABLE_TO_BUY_AMT` | `max(credit_limit - current_balance, 0)` |
| `OVERLIMIT_AMT` | `max(current_balance - credit_limit, 0)` |

Compare the actual proposal text and evidence with the implementation and complete any required SME review. Approve one proposal per target, up to two total. Use Notebook 02's separate SQL review statement with A, the batch ID, each selected `proposal_id`, and `review_decision = APPROVED`. Record the reviewer and time. If no proposal is suitable, pause the pilot at review.

## 3. Generate and validate

In Notebook 03, run the widget setup cell if needed. Set all three values before running the notebook through its Delta-save cell:

| Widget | Value |
| --- | --- |
| `source_run_id` | A |
| `pilot_batch_id` | The single reviewed batch ID |
| `pilot_proposal_ids` | The exact one or two approved proposal IDs, comma-separated |

Notebook 03 requires the batch's reviewed approvals to match the listed IDs exactly. It stops before writing if any selected proposal fails to apply. The pilot uses the existing generation seed, sample size, formulas, and profile-derived statistics. An unselected target is filled by its legacy formula.

Record the printed `generation_id`, then verify its persisted state and audit. Bind the query parameters to A, the batch ID, and the printed generation ID.

```sql
SELECT generation_id, source_run_id, proposal_batch_id, status, validated_versions
FROM workspace.synthetic_generated.generation_state
WHERE generation_id = :generation_id
  AND source_run_id = :source_run_id
  AND proposal_batch_id = :batch_id;

SELECT l.proposal_id, l.batch_id, l.target_table, l.target_column, l.rule_type, l.parent_columns,
       l.approval_status, l.approved, p.reviewed_by, p.reviewed_at, l.implemented,
       l.applied, l.outcome, l.reason, l.implementation_name, l.rows_processed, l.seed
FROM workspace.synthetic_generated.rule_execution_log l
LEFT JOIN workspace.synthetic_profile.ai_rule_proposals p
  ON p.source_run_id = l.source_run_id AND p.batch_id = l.batch_id AND p.proposal_id = l.proposal_id
WHERE l.generation_id = :generation_id AND l.source_run_id = :source_run_id
ORDER BY l.execution_order NULLS LAST, l.proposal_id;
```

For a successful pilot, state must be `COMPLETED` with populated `validated_versions`. The applied proposal IDs in the audit must equal the reviewed selection. Record the saved row counts, join coverage, any validation errors, and skipped proposal IDs and reasons from the notebook and audit. Report legacy fallback rows separately.

## 4. Profile GENERATED run B and compare directly with A

In Notebook 01, set `profile_type = GENERATED` and `generation_id` to the generation ID printed by Notebook 03. Run from the top. Record the printed GENERATED profile run ID as B. Before leaving the notebook session, capture the lineage:

```sql
SELECT run_id AS generated_profile_run_id, source_run_id, generation_id
FROM active_profile_run
WHERE profile_type = 'GENERATED';
```

Check that B is `COMPLETED` in `profile_runs` and that the recorded SOURCE and generation IDs match the pilot. Notebook 01's final comparison uses B and that exact SOURCE run. Capture mean and P25/P50/P75/P95 differences for the credit limit, current balance, available credit, and overlimit fields. Use absolute differences when the SOURCE value is zero. Also review the balance/limit correlation and past-due rates with their sample sizes:

```sql
SELECT run_id, metric_type, metric_value
FROM workspace.synthetic_profile.relationship_profile
WHERE run_id IN (:source_run_id, :generated_profile_run_id)
  AND entity_name = 'ACCOUNT'
  AND variable_1 = 'CREDIT_LIMIT_AMT'
  AND variable_2 = 'CURRENT_BALANCE_AMT'
  AND metric_type = 'PEARSON_CORRELATION';

SELECT run_id, condition_bucket, record_count, outcome_rate
FROM workspace.synthetic_profile.conditional_profile
WHERE run_id IN (:source_run_id, :generated_profile_run_id)
  AND entity_name = 'ACCOUNT'
  AND condition_variable = 'UTILIZATION_RATE'
  AND outcome_variable = 'PAST_DUE_INDICATO_CD'
ORDER BY condition_bucket, run_id;
```

This pilot verifies dispatch and traceability. The reviewed implementations use the same formulas as the legacy path. Investigate SOURCE-to-GENERATED differences as properties of the whole generator, including the 1.25× balance cap, marginal sampling, and small utilization buckets.

Notebook 01's final cell refreshes the project showcase with aggregate measurements from this exact comparison. Leave `showcase_output_dir` blank to update `docs/` in the Databricks checkout, or choose an absolute writable output folder for a separate HTML/CSS copy. The exporter checks completion, generation lineage, validated Delta versions, and snapshot join coverage before replacing the page's results block. The public page contains aggregate statistics and rule counts. Keep the run, batch, proposal, and reviewer evidence in the internal pilot report below. Commit and push the refreshed showcase files when publishing through GitHub Pages.

## Pilot report

| Evidence | Value to capture |
| --- | --- |
| SOURCE run A | Completed `run_id` and timestamp |
| Proposal batch | `batch_id`, prompt hash, model endpoint, and A |
| Approved rules | Proposal IDs, targets, reviewer, and review timestamp |
| Synthetic generation | `generation_id`, seed, and persisted status |
| Applied rules | Proposal IDs, implementation names, and rows processed |
| Skipped rules | Proposal IDs and skip reasons, with legacy fallbacks listed separately |
| Validation | Saved row counts, join coverage, invariant results, and validated versions |
| GENERATED run B | Completed `run_id`, generation ID, and A |
| Differences to investigate | Measured numeric differences, correlation, and supported bucket-rate changes |

## Utilization-to-delinquency pilot

1. Pin a completed SOURCE run with utilization/delinquency conditional profiles. In Notebook 02, set that `source_run_id`, `delinquency_pilot = ON`, and `balance_pilot = OFF`. Run from the top to create a fresh `DELINQUENCY_PILOT` batch.
2. Review the candidate against the measured bucket rates and sample counts included in the saved prompt. The target must be `TKQ_ACCOUNT.PAST_DUE_INDICATO_CD`, the type `CONDITIONAL`, and the single parent `TKQ_ACCOUNT.UTILIZATION_RATE`. Approve the individual proposal using the existing SQL review template.
3. In Notebook 03, supply the same SOURCE ID, the new `pilot_batch_id`, and that single `pilot_proposal_ids` value. The registered implementation samples from measured SOURCE rates after the balance rules and utilization calculation. Missing rates for an encountered bucket, invalid evidence, or conflicting approvals cause a logged skip. The selected pilot then stops before writes if its approval did not apply.
4. Inspect the existing rule execution audit for the generation, batch, and proposal. Confirm `implementation_name = 'delinquency_by_utilization'`, `execution_order = 3`, and `applied = true`. Balance targets can use their recorded legacy fallback paths.
5. Re-profile the completed generation as GENERATED in Notebook 01. Review the new paired delinquency comparison for source and generated sample counts, rates, and percentage-point differences in each utilization bucket. Its IDs come from `active_profile_run` and the pinned baseline. The showcase exports the same paired aggregate rates.

The dependency already existed in legacy generation. This extension adds approval-controlled dispatch and measured-evidence checks while preserving legacy values and random-number consumption when no eligible approval exists. Outside an explicitly selected pilot, a skipped conditional rule uses the existing legacy path, including its 5% fallback for an absent bucket. The controlled implementation requires measured evidence for every bucket it uses.

Notebook 03 accepts one to three reviewed proposal IDs from a single batch, allowing a combined ACCOUNT_CORE batch to include both balance proposals and the conditional proposal when all have been individually reviewed. The separate balance pilot continues to use its original one or two balance proposals.

## Before adding new dependencies

- Complete this workflow in Databricks and retain the pilot evidence from the versioned outputs.
- For each new dependency, collect SOURCE evidence at the right entity grain and obtain SME agreement on the exact formula, inputs, and fallback behavior. Marginal profiles alone cannot establish a new joint relationship.
- Implement the agreed dependency as a predefined, testable rule. Define its order relative to existing rules and use measured SOURCE statistics for any probabilities or distributions.
- Compare the new implementation against a legacy run with the same SOURCE profile, seed, and sample size, then assess the targeted dependency with suitable conditional counts and invariants.
