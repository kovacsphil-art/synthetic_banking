"""Exercise the exporter with fabricated profiles and an in-memory SQL adapter."""

import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from synthetic_banking.showcase import collect_measurements, export_showcase, render_measurements


class Result:
    def __init__(self, rows):
        self.rows = rows

    def collect(self):
        return self.rows


class Row(dict):
    def asDict(self):
        return dict(self)


class ProfileSpark:
    def __init__(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.queries = []
        self.state = {
            "status": "COMPLETED", "source_run_id": "private-source",
            "generation_id": "private-generation", "validated_versions": {"test": "private-version"},
        }
        self.connection.executescript("""
            CREATE TABLE active_profile_run (run_id, profile_type, source_run_id, generation_id);
            INSERT INTO active_profile_run VALUES ('private-generated', 'GENERATED', 'private-source', 'private-generation');
            CREATE TABLE profile_runs (run_id, profile_type, status, completed_at);
            INSERT INTO profile_runs VALUES ('private-source', 'SOURCE', 'COMPLETED', '2026-01-01');
            INSERT INTO profile_runs VALUES ('private-generated', 'GENERATED', 'COMPLETED', '2026-01-02');
            INSERT INTO profile_runs VALUES ('other-run', 'SOURCE', 'COMPLETED', '2026-01-03');
            CREATE TABLE numeric_profile (run_id, logical_table_name, column_name, mean_value, p25, p50, p75, p95);
            CREATE TABLE relationship_profile (run_id, entity_name, variable_1, variable_2, metric_type, metric_value);
            CREATE TABLE conditional_profile (run_id, entity_name, condition_variable, outcome_variable, condition_bucket, record_count, outcome_rate);
            CREATE TABLE column_quality (run_id, logical_table_name, row_count);
            CREATE TABLE TKQ_ACCOUNT (ACCOUNT_ID, BUSINESSEFFECTIVEDATE);
            CREATE TABLE TKQ_ACCOUNT_BALANCE (ACCOUNT_ID, BUSINESSEFFECTIVEDATE);
            INSERT INTO TKQ_ACCOUNT VALUES ('fabricated-A1', '2026-01-01'), ('fabricated-A2', '2026-01-01');
            INSERT INTO TKQ_ACCOUNT_BALANCE SELECT * FROM TKQ_ACCOUNT;
            CREATE TABLE rule_execution_log (source_run_id, generation_id, proposed, approved, implemented, applied, outcome, rows_processed);
            INSERT INTO rule_execution_log VALUES ('private-source', 'private-generation', 1, 1, 1, 1, 'APPLIED', 2);
            INSERT INTO rule_execution_log VALUES ('private-source', 'private-generation', 1, 0, 1, 0, 'SKIPPED', 0);
            INSERT INTO rule_execution_log VALUES ('private-source', 'private-generation', 1, 1, 0, 0, 'SKIPPED', 0);
            INSERT INTO rule_execution_log VALUES ('private-source', 'private-generation', 0, 0, 1, 0, 'LEGACY_FALLBACK', 2);
        """)
        for run in ("private-source", "private-generated", "other-run"):
            for field in ("CREDIT_LIMIT_AMT", "CURRENT_BALANCE_AMT", "AVAILABLE_TO_BUY_AMT", "OVERLIMIT_AMT"):
                table = "TKQ_ACCOUNT" if field == "CREDIT_LIMIT_AMT" else "TKQ_ACCOUNT_BALANCE"
                mean = 0 if field == "OVERLIMIT_AMT" else 100
                self.connection.execute(
                    "INSERT INTO numeric_profile VALUES (?, ?, ?, ?, 25, 50, 75, 95)",
                    (run, table, field, 999999 if run == "other-run" else mean),
                )
            self.connection.execute(
                "INSERT INTO relationship_profile VALUES (?, 'ACCOUNT', 'CREDIT_LIMIT_AMT', 'CURRENT_BALANCE_AMT', 'PEARSON_CORRELATION', .75)",
                (run,),
            )
            self.connection.execute(
                "INSERT INTO conditional_profile VALUES (?, 'ACCOUNT', 'UTILIZATION_RATE', 'PAST_DUE_INDICATO_CD', '0-30%', 2, .5)",
                (run,),
            )
            for table in ("PERSON", "CUSTOMER_ACCOUNT_REL", "TKQ_ACCOUNT", "TKQ_ACCOUNT_BALANCE", "TRADELINES"):
                self.connection.execute("INSERT INTO column_quality VALUES (?, ?, 2)", (run, table))

    def sql(self, query, args=None):
        self.queries.append(query)
        if "generation_state" in query:
            return Result([Row(self.state)])
        query = query.replace("workspace.synthetic_profile.", "").replace("workspace.synthetic_generated.", "")
        return Result([Row(row) for row in self.connection.execute(query, args or {})])


class ShowcaseTests(unittest.TestCase):
    def setUp(self):
        self.spark = ProfileSpark()
        self.addCleanup(self.spark.connection.close)
        self.versions = patch("synthetic_banking.showcase.check_validated_versions").start()
        self.addCleanup(patch.stopall)

    def test_exports_only_selected_aggregates_and_distinguishes_rule_outcomes(self):
        report = collect_measurements(self.spark)
        self.assertEqual(len(report["numeric"]), 20)
        self.assertEqual(report["join_coverage"], 100)
        self.assertEqual(report["rules"], {
            "proposed": 3, "approved": 2, "implemented": 2, "applied": 1,
            "skipped": 2, "unimplemented": 1, "fallback": 1,
        })
        text = json.dumps(report) + render_measurements(report)
        for private in ("private-source", "private-generated", "private-generation", "private-version", "fabricated-A1", "999999"):
            self.assertNotIn(private, text)
        self.assertNotIn("current_run", "\n".join(self.spark.queries))
        self.assertNotIn("ai_rule_proposals", "\n".join(self.spark.queries))
        self.assertEqual(self.versions.call_count, 2)

    def test_rejects_incomplete_or_wrong_profile_types(self):
        for statement in (
            "UPDATE profile_runs SET status = 'RUNNING' WHERE profile_type = 'GENERATED'",
            "UPDATE profile_runs SET profile_type = 'GENERATED' WHERE profile_type = 'SOURCE'",
            "UPDATE active_profile_run SET profile_type = 'SOURCE'",
        ):
            with self.subTest(statement=statement):
                spark = ProfileSpark()
                try:
                    spark.connection.execute(statement)
                    with self.assertRaises(ValueError):
                        collect_measurements(spark)
                finally:
                    spark.connection.close()

    def test_rejects_wrong_generation_and_failed_join_coverage(self):
        self.spark.state["generation_id"] = "other-generation"
        with self.assertRaisesRegex(ValueError, "lineage"):
            collect_measurements(self.spark)
        self.spark.state["generation_id"] = "private-generation"
        self.spark.connection.execute("UPDATE TKQ_ACCOUNT_BALANCE SET BUSINESSEFFECTIVEDATE = '2026-02-01'")
        with self.assertRaisesRegex(ValueError, "join coverage"):
            collect_measurements(self.spark)

    def test_missing_nonfinite_and_zero_baselines_are_honest(self):
        self.spark.connection.execute("DELETE FROM relationship_profile")
        report = collect_measurements(self.spark)
        report["numeric"][0]["source"] = float("nan")
        report["numeric"][0]["generated"] = None
        output = render_measurements(report)
        self.assertIn("Unavailable", output)
        self.assertIn("+0.00 absolute", output)
        self.assertNotIn(">nan<", output)
        self.assertNotIn(">0.0000<", output)

    def test_duplicate_profiles_and_mismatched_audit_are_rejected(self):
        self.spark.connection.execute("INSERT INTO numeric_profile SELECT * FROM numeric_profile LIMIT 1")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            collect_measurements(self.spark)
        self.spark.connection.execute("DELETE FROM numeric_profile WHERE rowid = (SELECT MAX(rowid) FROM numeric_profile)")
        self.spark.connection.execute("UPDATE rule_execution_log SET source_run_id = 'other-source'")
        with self.assertRaisesRegex(ValueError, "audit"):
            collect_measurements(self.spark)

    def test_refresh_preserves_template_and_previous_page_on_failure(self):
        template = Path(__file__).resolve().parents[1] / "docs"
        with TemporaryDirectory() as folder:
            output = export_showcase(self.spark, folder, template_dir=template)
            page = output.read_text(encoding="utf-8")
            self.assertIn("Measured results", page)
            self.assertIn('id="comparison-title"', page)
            self.assertIn('class="status-label status-measured"', page)
            self.assertNotIn("Results pending", page)
            self.assertTrue((Path(folder) / "styles.css").is_file())
            original = (template / "index.html").read_text(encoding="utf-8")
            start, end = "<!-- SHOWCASE RESULTS START -->", "<!-- SHOWCASE RESULTS END -->"
            self.assertEqual(page.split(start)[0], original.split(start)[0])
            self.assertEqual(page.split(end)[1], original.split(end)[1])
            # Refreshing an already exported folder must preserve markers and handle its own stylesheet.
            export_showcase(self.spark, folder, template_dir=folder)
            page = output.read_text(encoding="utf-8")
            self.versions.side_effect = [None, ValueError("Changed Delta versions")]
            with self.assertRaisesRegex(ValueError, "Changed Delta"):
                export_showcase(self.spark, folder, template_dir=template)
            self.assertEqual(output.read_text(encoding="utf-8"), page)


if __name__ == "__main__":
    unittest.main()
