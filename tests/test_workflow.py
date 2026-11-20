"""Fabricated metadata exercises task handoffs without Databricks or source rows."""

import json
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from synthetic_banking.workflow import (
    ApprovalRequired, check_approvals, enforce_approval, publish_values, required_id,
    require_batch, require_generation, require_profile_pair, validate_execution, validate_reuse,
)


class Row(dict):
    def asDict(self): return dict(self)


class WorkflowSpark:
    def __init__(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.catalog = SimpleNamespace(tableExists=lambda name: self.db.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE name=?", (name.rsplit(".", 1)[-1],)).fetchone()[0] > 0)
        self.queries = []
        self.db.executescript("""
            CREATE TABLE profile_runs(run_id, profile_type, status, started_at, completed_at);
            INSERT INTO profile_runs VALUES ('source-A','SOURCE','COMPLETED','2026-01-01','2026-01-02'),
                ('generated-B','GENERATED','COMPLETED','2026-02-01','2026-02-02');
            CREATE TABLE profile_run_lineage(run_id, profile_type, source_run_id, generation_id);
            INSERT INTO profile_run_lineage VALUES ('generated-B','GENERATED','source-A','generation-C');
            CREATE TABLE ai_rule_batches(batch_id, source_run_id, prompt_sha256, model_endpoint, response);
            INSERT INTO ai_rule_batches VALUES ('batch-A','source-A','fabricated-hash','fabricated-model','{"rules":[{}]}');
            CREATE TABLE ai_rule_proposals(proposal_id, source_run_id, batch_id, target_table, target_column,
                rule_type, parent_columns, approval_status, reviewed_by, reviewed_at, legacy_approval_status, proposed_rule);
            INSERT INTO ai_rule_proposals VALUES ('proposal-A','source-A','batch-A','TKQ_ACCOUNT_BALANCE',
                'AVAILABLE_TO_BUY_AMT','DERIVED','["CREDIT_LIMIT_AMT","CURRENT_BALANCE_AMT"]',
                'PENDING',NULL,NULL,NULL,'untrusted text; never run this');
        """)

    def table(self, name):
        return SimpleNamespace(columns=[row["name"] for row in self.db.execute(f"PRAGMA table_info({name.rsplit('.', 1)[-1]})")])

    def sql(self, query, args=None):
        self.queries.append((query, args))
        rows = []
        for raw in self.db.execute(query.replace("workspace.synthetic_profile.", "").replace("workspace.synthetic_generated.", ""), args or {}):
            row = Row(raw)
            if "parent_columns" in row:
                row["parent_columns"] = json.loads(row["parent_columns"])
            rows.append(row)
        return SimpleNamespace(collect=lambda: rows, first=lambda: rows[0] if rows else None)

    def review(self, status="APPROVED"):
        self.db.execute("UPDATE ai_rule_proposals SET approval_status=?, reviewed_by='fabricated-reviewer', reviewed_at='2026-02-03'", (status,))


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.spark = WorkflowSpark()
        self.addCleanup(self.spark.db.close)

    def test_pending_stops_cleanly_and_manual_review_resumes_same_ids(self):
        decision = check_approvals(self.spark, "source-A", "batch-A")
        self.assertEqual((decision.status, decision.proposed, decision.pending), ("APPROVAL_REQUIRED", 1, 1))
        with self.assertRaisesRegex(ApprovalRequired, "repair approval_check"):
            enforce_approval(decision)
        self.assertEqual(self.spark.db.execute("SELECT approval_status FROM ai_rule_proposals").fetchone()[0], "PENDING")
        self.spark.review()
        decision = check_approvals(self.spark, "source-A", "batch-A")
        enforce_approval(decision)
        self.assertEqual((decision.status, decision.approved), ("READY", 1))
        self.assertTrue(all("current_run" not in query for query, _ in self.spark.queries))

    def test_rejected_and_unsupported_reviewed_proposals_do_not_become_automatic_implementations(self):
        self.spark.review("REJECTED")
        decision = check_approvals(self.spark, "source-A", "batch-A")
        self.assertEqual((decision.status, decision.approved), ("READY", 0))
        self.spark.review()
        self.spark.db.execute("UPDATE ai_rule_proposals SET target_column='UNSUPPORTED'")
        self.assertEqual(check_approvals(self.spark, "source-A", "batch-A").status, "READY")
        # Dispatch and skip semantics remain the responsibility of the existing registry.

    def test_legacy_or_unverified_approvals_fail_early(self):
        self.spark.db.execute("UPDATE ai_rule_proposals SET approval_status='APPROVED'")
        with self.assertRaisesRegex(ValueError, "reviewer/time"):
            check_approvals(self.spark, "source-A", "batch-A")
        self.spark.review()
        self.spark.db.execute("UPDATE ai_rule_proposals SET legacy_approval_status='APPROVED'")
        with self.assertRaisesRegex(ValueError, "nonlegacy"):
            check_approvals(self.spark, "source-A", "batch-A")

    def test_review_or_text_changes_invalidate_pre_generation_fingerprint(self):
        self.spark.review()
        original = check_approvals(self.spark, "source-A", "batch-A")
        enforce_approval(original, original.fingerprint)
        self.spark.db.execute("UPDATE ai_rule_proposals SET proposed_rule='changed untrusted text'")
        changed = check_approvals(self.spark, "source-A", "batch-A")
        with self.assertRaisesRegex(ValueError, "changed after"):
            enforce_approval(changed, original.fingerprint)

    def test_wrong_source_batch_incomplete_rows_and_unresolved_handoffs_fail(self):
        for source, batch in (("generated-B", "batch-A"), ("source-A", "missing")):
            with self.subTest(source=source, batch=batch), self.assertRaises(ValueError):
                require_batch(self.spark, source, batch)
        with self.assertRaises(ValueError):
            validate_reuse(self.spark, "source-A", "")
        validate_reuse(self.spark, "source-A", "batch-A")
        for value in (None, "", "{{tasks.missing.values.id}}"):
            with self.assertRaises(ValueError): required_id(value, "run_id")
        self.spark.db.execute("UPDATE ai_rule_proposals SET source_run_id='other-source'")
        with self.assertRaisesRegex(ValueError, "provenance"):
            check_approvals(self.spark, "source-A", "batch-A")
        self.spark.db.execute("DELETE FROM ai_rule_proposals")
        with self.assertRaisesRegex(ValueError, "incomplete"):
            check_approvals(self.spark, "source-A", "batch-A")

    def test_duplicate_batches_and_proposals_are_rejected(self):
        self.spark.db.execute("INSERT INTO ai_rule_batches SELECT * FROM ai_rule_batches")
        with self.assertRaisesRegex(ValueError, "exactly"):
            require_batch(self.spark, "source-A", "batch-A")
        self.spark.db.execute("DELETE FROM ai_rule_batches WHERE rowid=2")
        self.spark.db.execute("INSERT INTO ai_rule_proposals SELECT * FROM ai_rule_proposals")
        with self.assertRaisesRegex(ValueError, "duplicated"):
            check_approvals(self.spark, "source-A", "batch-A")

    def test_no_rule_batch_can_continue_with_existing_legacy_generation(self):
        self.spark.db.execute("DELETE FROM ai_rule_proposals")
        self.spark.db.execute("UPDATE ai_rule_batches SET response='{\"rules\":[]}'")
        decision = check_approvals(self.spark, "source-A", "batch-A")
        self.assertEqual((decision.status, decision.proposed, decision.approved), ("READY", 0, 0))
        enforce_approval(decision)

    def test_validated_generation_and_profile_lineage_must_match_all_ids(self):
        state = {"generation_id": "generation-C", "source_run_id": "source-A", "proposal_batch_id": "batch-A"}
        with patch("synthetic_banking.profiling_run.completed_generation", return_value=state):
            require_profile_pair(self.spark, "source-A", "batch-A", "generation-C", "generated-B")
            with self.assertRaisesRegex(ValueError, "generation IDs"):
                require_generation(self.spark, "source-A", "batch-A", "other-generation")
            self.spark.db.execute("UPDATE profile_run_lineage SET generation_id='other-generation'")
            with self.assertRaisesRegex(ValueError, "lineage"):
                require_profile_pair(self.spark, "source-A", "batch-A", "generation-C", "generated-B")

    def test_validation_uses_existing_report_and_does_not_accept_integrity_issues(self):
        report = {"generation_id": "generation-C", "metrics": [{"generated_check_status": "PASS"}]}
        with patch("synthetic_banking.workflow.require_profile_pair") as pair, patch(
                "synthetic_banking.fidelity.create_fidelity_report", return_value=report) as compare:
            self.assertIs(validate_execution(self.spark, "source-A", "batch-A", "generation-C", "generated-B"), report)
            pair.assert_called_once_with(self.spark, "source-A", "batch-A", "generation-C", "generated-B")
            compare.assert_called_once_with(self.spark, "source-A", "generated-B")
            report["metrics"][0]["generated_check_status"] = "ISSUE"
            with self.assertRaisesRegex(ValueError, "integrity issues"):
                validate_execution(self.spark, "source-A", "batch-A", "generation-C", "generated-B")

    def test_task_values_have_no_default_fallback(self):
        dbutils = SimpleNamespace(jobs=SimpleNamespace(taskValues=SimpleNamespace(set=Mock())))
        publish_values(dbutils, source_run_id="source-A", batch_id="batch-A")
        self.assertEqual(dbutils.jobs.taskValues.set.call_count, 2)
        dbutils.jobs.taskValues.set.assert_any_call(key="source_run_id", value="source-A")


if __name__ == "__main__":
    unittest.main()
