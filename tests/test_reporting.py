"""The public contract exports fabricated aggregates and no execution identifiers."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from synthetic_banking.fidelity import compare_profiles
from synthetic_banking.reporting import build_public_report, load_public_report, export_public_report, REPORT_FILENAME
from test_fidelity import profiles_fixture
from test_workflow import WorkflowSpark


class ReportingTests(unittest.TestCase):
    def setUp(self):
        self.metrics = compare_profiles("source-A", "generated-B", "generation-C", profiles_fixture())["metrics"]
        self.counts = dict(proposed=3, approved=2, applied=1, skipped=2, approved_unimplemented=1)

    def test_sanitizes_identifiers_arbitrary_categories_and_freeform_text(self):
        for row in self.metrics:
            row["reason"] = "SECRET_TOKEN fabricated@example.invalid"
        self.metrics.append(dict(family="CATEGORICAL", entity_name="TKQ_ACCOUNT", column_name="PAST_DUE_INDICATO_CD",
                                 dimensions_json=json.dumps({"category_value": "PRIVATE_VALUE"}), metric="proportion",
                                 source_value=.1, generated_value=.2, difference=10, comparison_status="COMPARABLE"))
        report = build_public_report(self.metrics, self.counts, validation_passed=True, completed_at="2026-01-01T12:00:00Z")
        text = json.dumps(report, allow_nan=False)
        for forbidden in ("source-A", "generated-B", "generation-C", "SECRET_TOKEN", "fabricated@example", "PRIVATE_VALUE"):
            self.assertNotIn(forbidden, text)
        self.assertEqual(report["rules"]["applied"]["value"], 1)
        self.assertEqual(report["generation"]["accounts"]["value"], 200)
        self.assertEqual(report["dependency_results"]["delinquency_by_utilization"][0]["difference"], 15)
        self.assertTrue(any(w["code"] == "APPROVED_RULES_NOT_IMPLEMENTED" for w in report["warnings"]))

    def test_missing_optional_metrics_are_explicit_and_nonfinite_values_never_leak(self):
        report = build_public_report([], {}, validation_passed=True)
        self.assertIsNone(report["generation"]["total_rows"]["value"])
        self.assertIsNone(report["numeric_differences"][0]["source"])
        self.assertEqual(report["numeric_differences"][0]["status"], "UNAVAILABLE")
        self.assertEqual(len(report["numeric_differences"]), 12)
        self.assertEqual(len(report["categorical_differences"]), 2)
        self.assertEqual(len(report["dependency_results"]["delinquency_by_utilization"]), 5)
        row = dict(family="NUMERIC", entity_name="TKQ_ACCOUNT", column_name="CREDIT_LIMIT_AMT", metric="mean_value",
                   source_value=float("nan"), generated_value=float("inf"), difference=float("inf"), comparison_status="COMPARABLE")
        report = build_public_report([row], self.counts, validation_passed=True)
        json.dumps(report, allow_nan=False)
        self.assertIsNone(report["numeric_differences"][0]["source"])

    def test_failed_validation_never_builds_a_success_report(self):
        with self.assertRaises(ValueError): build_public_report(self.metrics, self.counts)
        self.metrics[0]["generated_check_status"] = "ISSUE"
        with self.assertRaises(ValueError): build_public_report(self.metrics, self.counts, validation_passed=True)

    def test_duplicate_selected_metrics_are_not_arbitrarily_chosen(self):
        row = dict(family="ROW_COUNT", entity_name="PERSON", column_name=None, metric="row_count", generated_value=100)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            build_public_report([row, row], self.counts, validation_passed=True)

    def test_loader_uses_exact_profile_pair_and_generation_time_audit_counts(self):
        spark = WorkflowSpark()
        self.addCleanup(spark.db.close)
        spark.db.execute("CREATE TABLE fidelity_metrics (source_run_id, generated_run_id, generation_id, family, entity_name, column_name, metric, generated_value)")
        spark.db.execute("INSERT INTO fidelity_metrics VALUES ('source-A','generated-B','generation-C','ROW_COUNT','PERSON',NULL,'row_count',100)")
        spark.db.executescript("""
            CREATE TABLE rule_execution_log (generation_id, source_run_id, batch_id, proposal_id, approved, implemented, applied, outcome, implementation_name);
            INSERT INTO rule_execution_log VALUES
              ('generation-C','source-A','batch-A','p1',TRUE,TRUE,TRUE,'APPLIED','available_to_buy'),
              ('generation-C','source-A','batch-A','p2',TRUE,FALSE,FALSE,'SKIPPED',NULL),
              ('generation-C','source-A',NULL,NULL,FALSE,TRUE,FALSE,'LEGACY_FALLBACK','overlimit_amount'),
              ('other-generation','other-source','other-batch','p3',TRUE,TRUE,TRUE,'APPLIED','available_to_buy');
        """)
        # SQLite encodes boolean columns as integers; adapt them like Spark BooleanType.
        original_sql = spark.sql
        def sql(query, args=None):
            result = original_sql(query, args)
            rows = result.collect()
            for row in rows:
                for key in ("approved", "implemented", "applied"):
                    if key in row and row[key] is not None: row[key] = bool(row[key])
            result.collect = lambda: rows
            return result
        spark.sql = sql
        with patch("synthetic_banking.reporting.require_profile_pair") as lineage:
            report = load_public_report(spark, "source-A", "batch-A", "generation-C", "generated-B", "PASS",
                                        validated_at="2026-01-01T12:00:00Z")
            lineage.assert_called_once_with(spark, "source-A", "batch-A", "generation-C", "generated-B")
            self.assertEqual(report["rules"]["proposed"]["value"], 2)
            self.assertEqual(report["rules"]["approved"]["value"], 2)
            self.assertEqual(report["rules"]["applied"]["value"], 1)
            self.assertEqual(report["pipeline_completed_at"], "2026-01-01T12:00:00Z")
            with self.assertRaises(ValueError):
                load_public_report(spark, "source-A", "batch-A", "generation-C", "generated-B", "FAIL")
            spark.db.execute("UPDATE rule_execution_log SET batch_id='wrong' WHERE proposal_id='p1'")
            with self.assertRaisesRegex(ValueError, "provenance"):
                load_public_report(spark, "source-A", "batch-A", "generation-C", "generated-B", "PASS")
        self.assertTrue(all("current_run" not in query for query, _ in spark.queries))

    def test_publication_preserves_last_success_on_validation_or_replace_failure(self):
        report = build_public_report([], {}, validation_passed=True)
        with TemporaryDirectory() as folder:
            target = Path(folder) / REPORT_FILENAME
            target.write_text("previous-success", encoding="utf-8")
            with patch("synthetic_banking.reporting.load_public_report", side_effect=ValueError("not validated")):
                with self.assertRaises(ValueError): export_public_report(None, folder)
            self.assertEqual(target.read_text(encoding="utf-8"), "previous-success")
            with patch("synthetic_banking.reporting.load_public_report", return_value=report), patch(
                    "synthetic_banking.reporting.os.replace", side_effect=OSError("fabricated write failure")):
                with self.assertRaises(OSError): export_public_report(None, folder)
            self.assertEqual(target.read_text(encoding="utf-8"), "previous-success")
            self.assertEqual(list(Path(folder).glob("*.tmp")), [])
            with patch("synthetic_banking.reporting.load_public_report", return_value=report):
                self.assertEqual(export_public_report(None, folder), target)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), report)

    def test_complete_example_and_formal_schema_match_contract_keys(self):
        folder = Path(__file__).resolve().parents[1] / "docs" / "reporting"
        example = json.loads((folder / "example.json").read_text())
        schema = json.loads((folder / "pipeline-report.schema.json").read_text())
        actual = build_public_report([], {}, validation_passed=True)
        self.assertEqual(set(example), set(schema["required"]))
        self.assertEqual(set(actual), set(schema["properties"]))
        self.assertEqual(set(example["generation"]), set(actual["generation"]))
        self.assertEqual(example["schema_version"], "2.0")
        for field in ("numeric_differences", "categorical_differences"):
            self.assertEqual(len(example[field]), len(actual[field]))
            self.assertEqual(set(example[field][0]), set(actual[field][0]))

    def test_completion_timestamp_is_utc_and_cannot_contain_arbitrary_text(self):
        report = build_public_report([], {}, validation_passed=True, completed_at="2026-01-01T14:00:00+02:00")
        self.assertEqual(report["pipeline_completed_at"], "2026-01-01T12:00:00Z")
        for invalid in ("", "SECRET_VALUE", "2026-01-01T12:00:00"):
            with self.subTest(value=invalid), self.assertRaisesRegex(ValueError, "timezone-aware ISO"):
                build_public_report([], {}, validation_passed=True, completed_at=invalid)

    def test_retrying_an_older_execution_cannot_replace_a_newer_success(self):
        newer = build_public_report([], {}, validation_passed=True, completed_at="2026-02-02T12:00:00Z")
        older = build_public_report([], {}, validation_passed=True, completed_at="2026-02-01T12:00:00Z")
        with TemporaryDirectory() as folder:
            with patch("synthetic_banking.reporting.load_public_report", return_value=newer):
                target = export_public_report(None, folder)
                original = target.read_bytes()
                export_public_report(None, folder)  # Retrying the same completion is safe.
                self.assertEqual(target.read_bytes(), original)
            with patch("synthetic_banking.reporting.load_public_report", return_value=older):
                with self.assertRaisesRegex(ValueError, "older validated execution"):
                    export_public_report(None, folder)
            self.assertEqual(target.read_bytes(), original)
            self.assertEqual(list(Path(folder).glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
