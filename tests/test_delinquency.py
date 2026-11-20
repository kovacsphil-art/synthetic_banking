from dataclasses import replace
import ast
import json
from pathlib import Path
import runpy
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

import numpy as np

from synthetic_banking.rules import (
    RuleProposal,
    apply_balance_rules,
    apply_delinquency_rule,
    delinquency_by_utilization,
    partition_rule_proposals,
)


SOURCE = "fabricated-source"
APPROVED = RuleProposal(
    proposal_id="fabricated-delinquency", source_run_id=SOURCE,
    target_table="TKQ_ACCOUNT", target_column="PAST_DUE_INDICATO_CD",
    rule_type="CONDITIONAL", parent_columns=("TKQ_ACCOUNT.UTILIZATION_RATE",),
    approval_status="APPROVED", batch_id="fabricated-batch", has_review_provenance=True,
)


def profile():
    return [
        {"run_id": SOURCE, "entity_name": "ACCOUNT", "condition_variable": "UTILIZATION_RATE",
         "outcome_variable": "PAST_DUE_INDICATO_CD", "condition_bucket": bucket,
         "record_count": 100, "outcome_rate": rate}
        for bucket, rate in zip(
            ("0-30%", "30-60%", "60-80%", "80-100%", "100%+"), (0, 1, .25, .5, .9)
        )
    ]


class DelinquencyRuleTests(unittest.TestCase):
    def test_approved_rule_uses_measured_rates_and_exact_bucket_boundaries(self):
        utilization = [0, .2999, .30, .5999, .60, .7999, .80, 1, 1.0001]
        draws = [.1, 0, .99, 0, .25, .249, .5, .499, .8]
        flags, events = apply_delinquency_rule(
            SOURCE, [APPROVED], utilization, profile(), draws, np.zeros(len(draws)),
        )
        np.testing.assert_array_equal(flags, [False, False, True, True, False, True, False, True, True])
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual((event.proposal_id, event.batch_id), (APPROVED.proposal_id, APPROVED.batch_id))
        self.assertEqual((event.outcome, event.execution_order, event.rows_processed), ("APPLIED", 3, 9))
        self.assertTrue(event.proposed and event.approved and event.implemented and event.applied)
        self.assertEqual(event.implementation_name, "delinquency_by_utilization")

    def test_unapproved_path_preserves_legacy_values_and_rng_state(self):
        for status in (None, "PENDING", "REJECTED"):
            with self.subTest(status=status):
                original = np.random.default_rng(42)
                controlled = np.random.default_rng(42)
                legacy_rates = np.array([.05, .2, .05, .8, .9])
                expected = original.random(5) < legacy_rates
                proposals = [] if status is None else [replace(APPROVED, approval_status=status)]
                flags, events = apply_delinquency_rule(
                    SOURCE, proposals, [.1, .4, .7, .9, 1.2], None,
                    controlled.random(5), legacy_rates,
                )
                np.testing.assert_array_equal(flags, expected)
                np.testing.assert_array_equal(original.random(5), controlled.random(5))
                self.assertEqual(events[-1].outcome, "LEGACY_FALLBACK")
                self.assertFalse(any(event.applied for event in events))
                if status is not None:
                    self.assertEqual(events[0].reason, "not_approved")
                    self.assertTrue(events[0].implemented)

    def test_unsupported_metadata_and_unverified_approvals_are_skipped(self):
        cases = (
            ({"target_column": "OTHER_COLUMN"}, "no_implementation"),
            ({"rule_type": "DERIVED"}, "no_implementation"),
            ({"parent_columns": ("CURRENT_CREDIT_SCORE",)}, "parent_mismatch"),
            ({"parent_columns": (*APPROVED.parent_columns, *APPROVED.parent_columns)}, "parent_mismatch"),
            ({"source_run_id": "other-source"}, "source_run_mismatch"),
            ({"has_review_provenance": False}, "unverified_approval"),
            ({"batch_id": None}, "unverified_approval"),
        )
        for fields, reason in cases:
            with self.subTest(fields=fields):
                flags, events = apply_delinquency_rule(
                    SOURCE, [replace(APPROVED, **fields)], [.1], profile(), [.5], [1],
                )
                np.testing.assert_array_equal(flags, [True])
                self.assertEqual((events[0].outcome, events[0].reason), ("SKIPPED", reason))
                self.assertFalse(events[0].applied)

    def test_missing_profile_or_encountered_bucket_skips_controlled_application(self):
        for evidence in (None, [], profile()[:1], [dict(row, run_id="other-source") for row in profile()]):
            with self.subTest(evidence=evidence):
                flags, events = apply_delinquency_rule(
                    SOURCE, [APPROVED], [.4], evidence, [.5], [1],
                )
                np.testing.assert_array_equal(flags, [True])
                self.assertEqual(events[0].reason, "missing_conditional_profile")
                self.assertTrue(events[0].approved and events[0].implemented)
                self.assertFalse(events[0].applied)
                self.assertEqual(events[-1].outcome, "LEGACY_FALLBACK")

    def test_only_pinned_source_and_needed_buckets_supply_probabilities(self):
        evidence = [dict(profile()[0], run_id="GENERATED-profile", outcome_rate=1), profile()[0]]
        flags, events = apply_delinquency_rule(SOURCE, [APPROVED], [.1], evidence, [.5], [1])
        np.testing.assert_array_equal(flags, [False])
        self.assertTrue(events[0].applied)
        for alias in ("UTILIZATION_RATE", "_UTILIZATION_RATE", "TKQ_ACCOUNT._UTILIZATION_RATE"):
            _, events = apply_delinquency_rule(
                SOURCE, [replace(APPROVED, parent_columns=(alias,))], [.1], evidence, [.5], [1],
            )
            self.assertTrue(events[0].applied)

    def test_invalid_or_duplicate_profile_is_skipped(self):
        for changes in ({"outcome_rate": float("nan")}, {"outcome_rate": 1.1},
                        {"outcome_rate": -.1}, {"outcome_rate": None}, {"record_count": 0}):
            with self.subTest(changes=changes):
                evidence = profile()
                evidence[0].update(changes)
                _, events = apply_delinquency_rule(SOURCE, [APPROVED], [.1], evidence, [.5], [1])
                self.assertEqual(events[0].reason, "invalid_conditional_profile")
        _, events = apply_delinquency_rule(SOURCE, [APPROVED], [.1], profile() + profile(), [.5], [1])
        self.assertEqual(events[0].reason, "invalid_conditional_profile")

    def test_conflicting_approvals_and_empty_populations_are_not_applied(self):
        proposals = [APPROVED, replace(APPROVED, proposal_id="another-proposal")]
        _, events = apply_delinquency_rule(SOURCE, proposals, [.1], profile(), [.5], [1])
        self.assertEqual([event.reason for event in events[:2]], ["conflicting_approvals"] * 2)
        self.assertFalse(any(event.applied for event in events))
        flags, events = apply_delinquency_rule(SOURCE, [APPROVED], [], None, [], [])
        self.assertEqual(flags.size, 0)
        self.assertEqual((events[0].outcome, events[0].reason), ("SKIPPED", "no_rows"))

    def test_each_proposal_is_audited_once_after_dependency_ordering(self):
        balance = replace(
            APPROVED, proposal_id="balance", target_table="TKQ_ACCOUNT_BALANCE",
            target_column="AVAILABLE_TO_BUY_AMT", rule_type="DERIVED",
            parent_columns=("CREDIT_LIMIT_AMT", "CURRENT_BALANCE_AMT"),
        )
        unsupported = replace(APPROVED, proposal_id="unsupported", target_column="OTHER_COLUMN")
        balance_proposals, conditional_proposals = partition_rule_proposals([balance, APPROVED, unsupported])
        amounts, events = apply_balance_rules(SOURCE, balance_proposals, [100], [40])
        flags, conditional_events = apply_delinquency_rule(
            SOURCE, conditional_proposals, [.4], profile(), [.8], [0],
        )
        events += conditional_events
        self.assertEqual(sorted(event.proposal_id for event in events if event.proposed),
                         ["balance", "fabricated-delinquency", "unsupported"])
        self.assertEqual([event.execution_order for event in events if event.execution_order], [1, 2, 3])
        np.testing.assert_array_equal(amounts["AVAILABLE_TO_BUY_AMT"], [60])
        np.testing.assert_array_equal(flags, [True])

    def test_sampler_requires_pinned_source_and_aligned_inputs(self):
        with self.assertRaisesRegex(ValueError, "pinned SOURCE"):
            delinquency_by_utilization("", [.1], profile(), [.5])
        with self.assertRaisesRegex(ValueError, "aligned"):
            delinquency_by_utilization(SOURCE, [.1, .2], profile(), [.5])


class NotebookEvidenceTests(unittest.TestCase):
    def test_llm_request_uses_same_source_and_batch_as_measured_context(self):
        notebook = json.loads((Path(__file__).resolve().parents[1] / "notebooks/02_LLM Rule Generation.ipynb").read_text(encoding="utf-8"))
        source = "".join(notebook["cells"][8]["source"])
        request = {"source_run_id": SOURCE, "batch_id": "batch", "scope_name": "DELINQUENCY_PILOT", "profile_summary": "fabricated column aggregates"}
        created = []
        def sql(query, args):
            self.assertEqual(args, {"source_run_id": SOURCE})
            self.assertIn("run_id = :source_run_id", query)
            return SimpleNamespace(collect=lambda: [SimpleNamespace(asDict=lambda: {
                "condition_bucket": "0-30%", "record_count": 100, "outcome_rate": .25,
            })])
        def create_frame(values, schema):
            created.extend(values)
            return SimpleNamespace(createOrReplaceTempView=lambda name: self.assertEqual(name, "ai_model_request"))
        spark = SimpleNamespace(
            table=lambda name: SimpleNamespace(first=lambda: request), sql=sql, createDataFrame=create_frame,
            catalog=SimpleNamespace(tableExists=lambda name: False),
        )
        with TemporaryDirectory() as folder:
            script = Path(folder) / "prompt_cell.py"
            script.write_text(source, encoding="utf-8")
            runpy.run_path(str(script), init_globals={"spark": spark})
        self.assertEqual(created[0][:3], (SOURCE, "batch", "DELINQUENCY_PILOT"))
        self.assertIn('"outcome_rate": 0.25', created[0][3])
        self.assertIn('"record_count": 100', created[0][3])
        self.assertIn("Do not invent", created[0][3])

    @unittest.skipIf(sqlite3.sqlite_version_info < (3, 39), "The local SQLite adapter needs FULL OUTER JOIN support.")
    def test_comparison_uses_exact_completed_profile_pair(self):
        notebook = json.loads((Path(__file__).resolve().parents[1] / "notebooks/01_Stat extraction _v1.ipynb").read_text(encoding="utf-8"))
        query = next("".join(cell["source"]) for cell in notebook["cells"]
                     if "AS difference_percentage_points" in "".join(cell["source"]))
        if query.startswith("%python"):
            tree = ast.parse(query.removeprefix("%python\n"))
            query = next(node.value for node in ast.walk(tree)
                         if isinstance(node, ast.Constant) and isinstance(node.value, str)
                         and "AS difference_percentage_points" in node.value)
        query = query.removeprefix("%sql\n").replace("workspace.synthetic_profile.", "")
        with sqlite3.connect(":memory:") as db:
            db.row_factory = sqlite3.Row
            db.executescript("""
                CREATE TABLE active_profile_run (run_id, source_run_id, profile_type);
                INSERT INTO active_profile_run VALUES ('B', 'A', 'GENERATED');
                CREATE TABLE profile_runs (run_id, profile_type, status, completed_at);
                INSERT INTO profile_runs VALUES ('A', 'SOURCE', 'COMPLETED', '2026-01-01');
                INSERT INTO profile_runs VALUES ('B', 'GENERATED', 'COMPLETED', '2026-01-02');
                INSERT INTO profile_runs VALUES ('other', 'SOURCE', 'COMPLETED', '2026-01-03');
                CREATE TABLE conditional_profile (run_id, condition_bucket, record_count, outcome_rate, entity_name, condition_variable, outcome_variable);
            """)
            db.executemany("INSERT INTO conditional_profile VALUES (?, ?, ?, ?, 'ACCOUNT', 'UTILIZATION_RATE', 'PAST_DUE_INDICATO_CD')", (
                ('A', '0-30%', 100, .1), ('B', '0-30%', 200, .15), ('other', '0-30%', 500, .9),
                ('A', '80-100%', 10, .2), ('B', '100%+', 20, .3),
            ))
            rows = [dict(row) for row in db.execute(query)]
            self.assertEqual(rows[0]['source_delinquency_rate'], .1)
            self.assertEqual(rows[0]['generated_record_count'], 200)
            self.assertEqual(rows[0]['difference_percentage_points'], 5)
            self.assertIsNone(rows[1]['generated_delinquency_rate'])
            self.assertIsNone(rows[2]['source_delinquency_rate'])


if __name__ == "__main__":
    unittest.main()
