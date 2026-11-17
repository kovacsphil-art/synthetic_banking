from dataclasses import replace
import json
import sqlite3
from types import SimpleNamespace
import unittest

import numpy as np

from synthetic_banking.rules import (
    RuleProposal,
    apply_balance_rules,
    load_rule_proposals,
    plan_balance_rules,
)


SOURCE_RUN_ID = "fabricated-source-run"
APPROVED = RuleProposal(
    proposal_id="fabricated-proposal",
    source_run_id=SOURCE_RUN_ID,
    target_table="TKQ_ACCOUNT_BALANCE",
    target_column="AVAILABLE_TO_BUY_AMT",
    rule_type="DERIVED",
    parent_columns=(
        "TKQ_ACCOUNT.CREDIT_LIMIT_AMT",
        "TKQ_ACCOUNT_BALANCE.CURRENT_BALANCE_AMT",
    ),
    approval_status="APPROVED",
    batch_id="fabricated-batch",
    has_review_provenance=True,
)


class BalanceRuleTests(unittest.TestCase):
    def test_without_proposals_uses_legacy_balance_formulas(self):
        selections, skipped = plan_balance_rules(SOURCE_RUN_ID, [])
        self.assertEqual(skipped, ())
        self.assertTrue(all(rule.approved_proposal_id is None for rule in selections))

        by_target = {rule.target_column: rule.implementation for rule in selections}
        credit_limits = np.array([100, 100, 100, 0, 50])
        balances = np.array([40, 100, 125, 0, np.nan])
        np.testing.assert_allclose(
            by_target["AVAILABLE_TO_BUY_AMT"](credit_limits, balances),
            [60, 0, 0, 0, np.nan],
        )
        np.testing.assert_allclose(
            by_target["OVERLIMIT_AMT"](credit_limits, balances),
            [0, 0, 25, 0, np.nan],
        )

    def test_matching_approval_is_selected_only_for_its_target(self):
        selections, skipped = plan_balance_rules(SOURCE_RUN_ID, [APPROVED])
        self.assertEqual(skipped, ())
        by_target = {rule.target_column: rule for rule in selections}
        selected = by_target["AVAILABLE_TO_BUY_AMT"]
        self.assertEqual(selected.approved_proposal_id, APPROVED.proposal_id)
        self.assertEqual(selected.implementation(100, 40), 60)
        self.assertIsNone(by_target["OVERLIMIT_AMT"].approved_proposal_id)

    def test_approvals_for_both_targets_are_selected_in_registry_order(self):
        overlimit = replace(
            APPROVED,
            proposal_id="fabricated-overlimit",
            target_column="OVERLIMIT_AMT",
            parent_columns=APPROVED.parent_columns[::-1],
        )
        selections, skipped = plan_balance_rules(SOURCE_RUN_ID, [overlimit, APPROVED])
        self.assertEqual(skipped, ())
        self.assertEqual(
            [rule.approved_proposal_id for rule in selections],
            [APPROVED.proposal_id, overlimit.proposal_id],
        )

    def test_pending_and_rejected_proposals_leave_legacy_path(self):
        proposals = [
            replace(APPROVED, proposal_id=status, approval_status=status)
            for status in ("PENDING", "REJECTED")
        ]
        selections, skipped = plan_balance_rules(SOURCE_RUN_ID, proposals)
        self.assertEqual([item.reason for item in skipped], ["not_approved", "not_approved"])
        self.assertTrue(all(rule.approved_proposal_id is None for rule in selections))

    def test_unusable_approvals_are_skipped_with_reasons(self):
        cases = [
            ({"source_run_id": "older-source-run"}, "source_run_mismatch"),
            ({"target_table": "TKQ_ACCOUNT"}, "no_implementation"),
            ({"target_column": "OTHER_AMT"}, "no_implementation"),
            ({"rule_type": "CORRELATED"}, "no_implementation"),
            ({"parent_columns": ("credit_limit",)}, "parent_mismatch"),
            (
                {"parent_columns": (*APPROVED.parent_columns, APPROVED.parent_columns[0])},
                "parent_mismatch",
            ),
        ]
        for fields, reason in cases:
            with self.subTest(fields=fields):
                proposal = replace(APPROVED, **fields)
                selections, skipped = plan_balance_rules(SOURCE_RUN_ID, [proposal])
                self.assertTrue(
                    all(rule.approved_proposal_id is None for rule in selections)
                )
                self.assertEqual(
                    [(item.proposal_id, item.reason) for item in skipped],
                    [(proposal.proposal_id, reason)],
                )

    def test_conflicting_approvals_leave_legacy_path(self):
        second = replace(APPROVED, proposal_id="second-approved-proposal")
        selections, skipped = plan_balance_rules(SOURCE_RUN_ID, [APPROVED, second])
        self.assertTrue(all(rule.approved_proposal_id is None for rule in selections))
        self.assertEqual(
            [(item.proposal_id, item.reason) for item in skipped],
            [
                (APPROVED.proposal_id, "conflicting_approvals"),
                (second.proposal_id, "conflicting_approvals"),
            ],
        )

    def test_requires_a_pinned_source_run(self):
        with self.assertRaisesRegex(ValueError, "pinned SOURCE run"):
            plan_balance_rules("", [])

    def test_missing_credit_limit_skips_approval_and_retains_legacy_values(self):
        results, events = apply_balance_rules(
            SOURCE_RUN_ID, [APPROVED], [0], [25], has_credit_limit=False
        )
        self.assertEqual([event.outcome for event in events], [
            "SKIPPED", "LEGACY_FALLBACK", "LEGACY_FALLBACK",
        ])
        self.assertEqual(events[0].reason, "missing_credit_limit")
        self.assertTrue(events[0].approved and events[0].implemented)
        self.assertFalse(events[0].applied)
        np.testing.assert_array_equal(results["AVAILABLE_TO_BUY_AMT"], [0])
        np.testing.assert_array_equal(results["OVERLIMIT_AMT"], [25])

    def test_approved_empty_result_does_not_count_as_applied(self):
        _, events = apply_balance_rules(SOURCE_RUN_ID, [APPROVED], [], [])
        candidate = next(event for event in events if event.proposed)
        self.assertEqual((candidate.outcome, candidate.reason, candidate.rows_processed), (
            "SKIPPED", "no_rows", 0,
        ))
        self.assertTrue(candidate.approved and candidate.implemented)
        self.assertFalse(candidate.applied)


class ProposalStoreTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.row_factory = sqlite3.Row
        self.spark = SimpleNamespace(
            catalog=SimpleNamespace(tableExists=self.table_exists),
            table=self.table,
            sql=self.sql,
        )

    def table_exists(self, name):
        (count,) = self.db.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE name = ?",
            (name.rsplit(".", 1)[-1],),
        ).fetchone()
        return count > 0

    def table(self, name):
        table = name.rsplit(".", 1)[-1]
        return SimpleNamespace(columns=[
            row["name"] for row in self.db.execute(f"PRAGMA table_info({table})")
        ])

    def sql(self, query, args):
        rows = self.db.execute(query.replace("workspace.synthetic_profile.", ""), args)
        return SimpleNamespace(collect=lambda: [
            dict(row) | {"parent_columns": json.loads(row["parent_columns"])}
            for row in rows
        ])

    def test_absent_or_legacy_tables_leave_generation_on_legacy_path(self):
        self.assertEqual(load_rule_proposals(self.spark, SOURCE_RUN_ID), ())
        self.db.execute("CREATE TABLE ai_rule_batches (batch_id, source_run_id)")
        self.db.execute("CREATE TABLE ai_rule_proposals (proposal_id, approval_status)")
        self.db.execute("INSERT INTO ai_rule_proposals VALUES ('legacy', 'APPROVED')")
        self.assertEqual(load_rule_proposals(self.spark, SOURCE_RUN_ID), ())

    def test_audit_distinguishes_proposals_approvals_implementation_and_execution(self):
        self.db.execute("CREATE TABLE ai_rule_batches (batch_id, source_run_id)")
        self.db.executemany("INSERT INTO ai_rule_batches VALUES (?, ?)", [
            ("batch-current", SOURCE_RUN_ID),
            ("another-batch", SOURCE_RUN_ID),
            ("batch-old", "other-source"),
        ])
        self.db.execute("""
            CREATE TABLE ai_rule_proposals (
                proposal_id, source_run_id, target_table, target_column, rule_type,
                parent_columns, approval_status, batch_id, reviewed_by, reviewed_at,
                legacy_approval_status, proposed_rule
            )
        """)
        base = {
            "proposal_id": "known",
            "source_run_id": SOURCE_RUN_ID,
            "target_table": "TKQ_ACCOUNT_BALANCE",
            "target_column": "AVAILABLE_TO_BUY_AMT",
            "rule_type": "DERIVED",
            "parent_columns": json.dumps(["CREDIT_LIMIT_AMT", "CURRENT_BALANCE_AMT"]),
            "approval_status": "APPROVED",
            "batch_id": "batch-current",
            "reviewed_by": "example-reviewer",
            "reviewed_at": "2026-11-16T12:00:00",
            "legacy_approval_status": None,
            "proposed_rule": "Synthetic fixture text that must stay out of generation.",
        }
        self.db.executemany(
            "INSERT INTO ai_rule_proposals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [tuple((base | changes).values()) for changes in (
                {},
                {"proposal_id": "unsupported", "target_column": "OTHER_AMT"},
                {"proposal_id": "pending", "approval_status": "PENDING"},
                {"proposal_id": "rejected", "approval_status": "REJECTED"},
                {"proposal_id": "other-current-batch", "batch_id": "another-batch"},
                {"proposal_id": "old-source", "batch_id": "batch-old", "source_run_id": "other-source"},
                {"proposal_id": "wrong-batch", "batch_id": "batch-old"},
                {"proposal_id": "unbatched", "batch_id": None},
                {"proposal_id": "missing-batch", "batch_id": "not-in-ledger"},
                {"proposal_id": "unreviewed", "reviewed_at": None},
                {"proposal_id": "blank-reviewer", "reviewed_by": " "},
                {"proposal_id": "legacy", "legacy_approval_status": "APPROVED"},
            )],
        )
        self.db.set_authorizer(
            lambda action, table, column, *_: sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_READ and column == "proposed_rule"
            else sqlite3.SQLITE_OK
        )

        all_proposals = load_rule_proposals(self.spark, SOURCE_RUN_ID)
        self.assertEqual({item.proposal_id for item in all_proposals if item.approved}, {
            "known", "unsupported", "other-current-batch",
        })
        proposals = load_rule_proposals(self.spark, SOURCE_RUN_ID, batch_id="batch-current")
        self.assertEqual([item.proposal_id for item in proposals if item.approved], [
            "known", "unsupported",
        ])
        amounts, events = apply_balance_rules(SOURCE_RUN_ID, proposals, [100, 100], [30, 125])
        np.testing.assert_array_equal(amounts["AVAILABLE_TO_BUY_AMT"], [70, 0])
        np.testing.assert_array_equal(amounts["OVERLIMIT_AMT"], [0, 25])
        audit = {event.proposal_id: event for event in events}
        self.assertNotIn("old-source", audit)
        self.assertEqual(len(audit), 8)
        skipped = audit["unsupported"]
        self.assertEqual((skipped.outcome, skipped.reason), (
            "SKIPPED", "no_implementation",
        ))
        self.assertTrue(skipped.proposed and skipped.approved)
        self.assertFalse(skipped.implemented or skipped.applied)
        for proposal_id, status in (("pending", "PENDING"), ("rejected", "REJECTED")):
            event = audit[proposal_id]
            self.assertEqual((event.outcome, event.reason, event.approval_status), (
                "SKIPPED", "not_approved", status,
            ))
            self.assertTrue(event.proposed and event.implemented)
            self.assertFalse(event.approved or event.applied)
        self.assertNotIn("other-current-batch", audit)
        for proposal_id in ("unreviewed", "blank-reviewer", "legacy"):
            self.assertEqual(audit[proposal_id].approval_status, "APPROVED")
            self.assertEqual(audit[proposal_id].reason, "unverified_approval")
            self.assertFalse(audit[proposal_id].approved or audit[proposal_id].applied)

        applied = audit["known"]
        self.assertEqual((applied.outcome, applied.proposal_id, applied.batch_id), (
            "APPLIED", "known", "batch-current",
        ))
        self.assertTrue(applied.proposed and applied.approved and applied.implemented and applied.applied)
        self.assertEqual(applied.parent_columns, ("CREDIT_LIMIT_AMT", "CURRENT_BALANCE_AMT"))
        self.assertEqual((applied.implementation_name, applied.rows_processed), ("available_to_buy", 2))
        legacy = audit[None]
        self.assertEqual((legacy.outcome, legacy.target_column, legacy.proposal_id), (
            "LEGACY_FALLBACK", "OVERLIMIT_AMT", None,
        ))
        self.assertTrue(legacy.implemented)
        self.assertFalse(legacy.proposed or legacy.approved or legacy.applied)
