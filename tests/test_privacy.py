"""Disclosure screens use fabricated banking-style rows in an in-memory SQL adapter."""

from contextlib import redirect_stdout
from dataclasses import replace
from datetime import date, datetime, timezone
from io import StringIO
import json
import math
import re
import sqlite3
from tempfile import TemporaryDirectory
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from synthetic_banking.config import SOURCE_ALIASES, STAGING_SCHEMA, CATALOG
from synthetic_banking.privacy_checks import (
    SparkPrivacyChecks, PrivacyMetric, PrivacyPolicy, disclosure_status, IDENTIFIERS, RARE_PAIRS, QUASI,
)
from synthetic_banking.privacy_sources import capture_source_inputs, finalize_source_inputs, snapshot_signature
from synthetic_banking.privacy import run_privacy_assessment, require_row_level_release, PrivacyGateError
from synthetic_banking.validation import GENERATED_TABLES


class Row(dict):
    def asDict(self): return dict(self)


class PrivacySQL:
    """Translate only the SQL dialect differences needed by the production checks."""
    def __init__(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.create_function("TO_DATE", 1, lambda value: value[:10] if value else None)
        self.db.create_function("DATEDIFF", 2, lambda first, second: (date.fromisoformat(first[:10]) - date.fromisoformat(second[:10])).days if first and second else None)
        self.db.create_function("FLOOR", 1, lambda value: math.floor(value) if value is not None else None)
        self.queries = []

    def sql(self, query):
        self.queries.append(query)
        query = re.sub(r"\bAS STRING\b", "AS TEXT", query, flags=re.I)
        query = query.replace("<=>", "IS").replace("TRY_CAST(", "CAST(")
        query = re.sub(r"DATE ('[^']+')", r"\1", query)
        row = self.db.execute(query).fetchone()
        return SimpleNamespace(first=lambda: Row(row))

    def frame(self, name, schema, rows):
        columns = list(schema)
        self.db.execute(f"CREATE TABLE {name} ({', '.join('`'+c+'`' for c in columns)})")
        self.db.executemany(f"INSERT INTO {name} VALUES ({','.join('?' for _ in columns)})", rows)
        def create_view(alias):
            self.db.execute(f"DROP VIEW IF EXISTS {alias}")
            self.db.execute(f"CREATE TEMP VIEW {alias} AS SELECT * FROM {name}")
        return SimpleNamespace(schema=SimpleNamespace(fields=[
            SimpleNamespace(name=column, dataType=SimpleNamespace(simpleString=lambda t=kind: t)) for column, kind in schema.items()
        ]), createOrReplaceTempView=create_view)


def frames(spark):
    schemas = {
        "PERSON": dict(PARTY_ID="string", BIRTH_DT="date", SINCE_DT="date", GENDER_CD="string", PREF_LANG_CD="string",
                       CUST_TYPE_CD="string", EMP_TYPE_CD="string", OCCUP_CAT_CD="string"),
        "TKQ_ACCOUNT": dict(ACCOUNT_ID="string", ACCOUNT_TYPE_CD="string", CLIENT_PRODUCT_CD="string", OPEN_DT="date", CREDIT_LIMIT_AMT="double"),
        "TKQ_ACCOUNT_BALANCE": dict(ACCOUNT_ID="string", BUSINESSEFFECTIVEDATE="date", CURRENT_BALANCE_AMT="double"),
        "CUSTOMER_ACCOUNT_REL": dict(PARTY_ID="string", ACCT_ID="string", RELATN_TYPE_CD="string"),
        "CUSTOMER_RELATIONSHIP": dict(FROM_PARTY_ID="string", TO_PARTY_ID="string", FROM_TO_CUST_RELATN_CD="string", TO_FROM_CUST_RELATN_CD="string"),
        "TRADELINES": {"account_number": "string", "REQ-CIF-KEY": "string", "REQ-CIF-TIE-BREAKER": "bigint", "amount": "double"},
    }
    result = []
    for prefix in ("s", "g"):
        source = prefix == "s"
        party, account, trade = ("PRIVATE-P", "PRIVATE-A", "PRIVATE-T") if source else ("P", "A", "T")
        data = {
            "PERSON": [(f"{party}{i}", "1980-01-01" if source else "1981-01-01", "2000-01-01" if source else "2001-01-01", "F", "EN", "I", "E", "O") for i in range(10)],
            "TKQ_ACCOUNT": [(f"{account}{i}", "R", "C", "2020-01-01" if source else "2021-01-01", 1000 if source else 1200) for i in range(10)],
            "TKQ_ACCOUNT_BALANCE": [(f"{account}{i}", "2026-01-01", 100 if source else 120) for i in range(10)],
            "CUSTOMER_ACCOUNT_REL": [(f"{party}{i}", f"{account}{i}", "PRIMARY") for i in range(10)],
            "CUSTOMER_RELATIONSHIP": [(f"{party}{i}", f"{party}{(i+1)%10}", "FAMILY", "FAMILY") for i in range(10)],
            "TRADELINES": [(f"{trade}{i}", f"{party}{i}", 0, 10 if source else 20) for i in range(10)],
        }
        result.append({table: spark.frame(f"{prefix}_{table.lower()}", schemas[table], data[table]) for table in GENERATED_TABLES})
    return result


class PrivacyCheckTests(unittest.TestCase):
    def setUp(self):
        self.spark = PrivacySQL()
        self.addCleanup(self.spark.db.close)
        self.sources, self.generated = frames(self.spark)

    def checks(self, policy=PrivacyPolicy()):
        return SparkPrivacyChecks(self.spark, self.sources, self.generated, policy)

    def test_nonoverlapping_identifiers_and_common_patterns_can_pass(self):
        metrics = self.checks().run()
        self.assertEqual(len(metrics), 25)
        self.assertEqual(disclosure_status(metrics), "PASS")
        self.assertEqual(sum(m.flagged_rows or 0 for m in metrics), 0)
        self.assertTrue(all("PRIVATE-P0" not in json.dumps(m.record()) for m in metrics))

    def test_identifier_reuse_matches_reference_domains_and_normalization(self):
        self.spark.db.execute("UPDATE g_customer_account_rel SET PARTY_ID=' private-p0 ' WHERE PARTY_ID='P0'")
        matches = self.checks().identifier_checks()
        check = next(m for m in matches if m.logical_table_name == "CUSTOMER_ACCOUNT_REL" and m.columns == ("PARTY_ID",))
        self.assertEqual((check.status, check.flagged_rows), ("FAIL", 1))
        self.assertEqual(disclosure_status(matches), "BLOCKED")

    def test_exact_row_copy_is_detected_and_no_source_values_are_reported(self):
        self.spark.db.execute("DELETE FROM g_person WHERE PARTY_ID='P0'")
        self.spark.db.execute("INSERT INTO g_person SELECT * FROM s_person LIMIT 1")
        check = next(m for m in self.checks().row_checks() if m.check_name == "FULL_ROW_MATCH" and m.logical_table_name == "PERSON")
        self.assertEqual((check.status, check.flagged_rows), ("FAIL", 1))
        text = json.dumps(check.record())
        for private in ("PRIVATE-P0", "1980-01-01", "2000-01-01"): self.assertNotIn(private, text)

    def test_payload_copy_with_new_identifier_still_requires_review(self):
        self.spark.db.execute("UPDATE s_person SET BIRTH_DT='1979-01-01' WHERE PARTY_ID='PRIVATE-P0'")
        self.spark.db.execute("UPDATE g_person SET BIRTH_DT='1979-01-01', SINCE_DT='2000-01-01' WHERE PARTY_ID='P0'")
        rows = self.checks().row_checks()
        full = next(m for m in rows if m.check_name == "FULL_ROW_MATCH" and m.logical_table_name == "PERSON")
        payload = next(m for m in rows if m.check_name == "PAYLOAD_MATCH" and m.logical_table_name == "PERSON")
        self.assertEqual(full.flagged_rows, 0)
        self.assertEqual((payload.status, payload.flagged_rows), ("REVIEW_REQUIRED", 1))

    def test_rare_combinations_report_only_counts_and_exclusions(self):
        self.spark.db.execute("UPDATE s_person SET PREF_LANG_CD='PRIVATE_CATEGORY' WHERE PARTY_ID='PRIVATE-P0'")
        self.spark.db.execute("UPDATE g_person SET PREF_LANG_CD='PRIVATE_CATEGORY' WHERE PARTY_ID='P0'")
        checks = self.checks().rare_checks()
        metric = checks[0]
        self.assertEqual((metric.status, metric.flagged_rows, metric.details["source_rare"]), ("REVIEW_REQUIRED", 1, 1))
        self.assertNotIn("PRIVATE_CATEGORY", json.dumps(metric.record()))
        self.spark.db.execute("UPDATE g_person SET EMP_TYPE_CD=NULL WHERE PARTY_ID IN ('P0','P1')")
        metric = self.checks().rare_checks()[1]
        self.assertEqual(metric.evaluated_rows, 8)
        self.assertEqual(metric.status, "REVIEW_REQUIRED")

    def test_similarity_window_is_complete_and_does_not_multiply_generated_rows(self):
        self.spark.db.execute("UPDATE s_person SET SINCE_DT='1999-01-01' WHERE PARTY_ID='PRIVATE-P0'")
        self.spark.db.execute("UPDATE s_person SET SINCE_DT='1999-01-02' WHERE PARTY_ID='PRIVATE-P1'")
        self.spark.db.execute("UPDATE g_person SET BIRTH_DT='1980-01-08', SINCE_DT='1999-01-08' WHERE PARTY_ID IN ('P0','P1')")
        metric = self.checks().similarity_check()
        self.assertEqual((metric.status, metric.flagged_rows), ("REVIEW_REQUIRED", 2))
        self.assertEqual(metric.details["matched_rows"], 2)
        self.assertEqual(metric.details["minimum_matched_distance_days"], 13)
        self.assertNotIn("1999-01-01", json.dumps(metric.record()))

    def test_similarity_budget_or_missing_coverage_never_passes_silently(self):
        self.spark.db.execute("UPDATE s_person SET SINCE_DT='2000-01-02' WHERE PARTY_ID='PRIVATE-P0'")
        self.spark.db.execute("UPDATE g_person SET BIRTH_DT='1980-01-01'")
        metric = self.checks(replace(PrivacyPolicy(), max_similarity_candidates=1)).similarity_check()
        self.assertEqual(metric.status, "UNAVAILABLE")
        self.spark.db.execute("UPDATE g_person SET BIRTH_DT=NULL WHERE PARTY_ID IN ('P0','P1')")
        metric = self.checks().similarity_check()
        self.assertEqual(metric.status, "REVIEW_REQUIRED")
        self.assertEqual(metric.evaluated_rows, 8)

    def test_null_safe_full_rows_and_lossless_numeric_casts(self):
        self.spark.db.execute("UPDATE s_person SET OCCUP_CAT_CD=NULL WHERE PARTY_ID='PRIVATE-P0'")
        self.spark.db.execute("DELETE FROM g_person WHERE PARTY_ID='P0'")
        self.spark.db.execute("INSERT INTO g_person SELECT * FROM s_person WHERE PARTY_ID='PRIVATE-P0'")
        metric = next(m for m in self.checks().row_checks() if m.check_name == "FULL_ROW_MATCH" and m.logical_table_name == "PERSON")
        self.assertEqual(metric.flagged_rows, 1)
        self.sources["TKQ_ACCOUNT"].schema.fields[-1].dataType.simpleString = lambda: "int"
        self.spark.db.execute("UPDATE g_tkq_account SET OPEN_DT='2020-01-01', CREDIT_LIMIT_AMT=1000.5 WHERE ACCOUNT_ID='A0'")
        metric = next(m for m in self.checks().row_checks() if m.check_name == "PAYLOAD_MATCH" and m.logical_table_name == "TKQ_ACCOUNT")
        self.assertEqual(metric.details["matching_rows"], 0)

    def test_missing_columns_unsupported_types_and_nonaggregate_collection_block(self):
        self.generated["PERSON"].schema.fields = self.generated["PERSON"].schema.fields[:-1]
        self.assertEqual(disclosure_status(self.checks().run()), "BLOCKED")
        self.sources["TRADELINES"].schema.fields[-1].dataType.simpleString = lambda: "array<string>"
        checks = self.checks()
        metric = next(m for m in checks.row_checks() if m.check_name == "FULL_ROW_MATCH" and m.logical_table_name == "TRADELINES")
        self.assertEqual(metric.status, "UNAVAILABLE")
        with self.assertRaisesRegex(ValueError, "numeric privacy aggregates"):
            checks.scalar("SELECT PARTY_ID FROM privacy_src_person LIMIT 1")


def complete_metrics():
    return [*(PrivacyMetric("IDENTIFIER_OVERLAP", table, (col,), "PASS", 10, 0) for members in IDENTIFIERS.values() for table, col in members),
            *(PrivacyMetric(kind, table, ("FIELD",), "PASS", 10, 0) for kind in ("FULL_ROW_MATCH", "PAYLOAD_MATCH") for table in GENERATED_TABLES),
            *(PrivacyMetric("RARE_COMBINATION", table, columns, "PASS", 10, 0) for table, columns in RARE_PAIRS),
            PrivacyMetric("QUASI_SIMILARITY", "PERSON", QUASI, "PASS", 10, 0)]


class PrivacyGateTests(unittest.TestCase):
    def setUp(self):
        self.snapshots = {table: dict(source_object=f"{STAGING_SCHEMA}.{table}", table_id=f"src-{table}", delta_version=2) for table in GENERATED_TABLES}
        self.state = {"source_run_id": "source-A", "generation_id": "generation-B", "proposal_batch_id": "batch-A",
                      "validated_versions": {table: f"gen-{table}:3" for table in GENERATED_TABLES}}
        self.identity = patch("synthetic_banking.privacy._validated_generation", return_value=self.state).start()
        patch("synthetic_banking.privacy.load_source_snapshots", return_value=self.snapshots).start()
        patch("synthetic_banking.privacy._source_identity_unchanged").start()
        self.addCleanup(patch.stopall)

    def assessment(self, metrics=None):
        spark = SimpleNamespace(read=SimpleNamespace(option=Mock()))
        spark.read.option.return_value.table.return_value = object()
        self.saved = []
        with patch("synthetic_banking.privacy._save_assessment", side_effect=lambda spark, row: self.saved.append(dict(row))), patch(
                "synthetic_banking.privacy._save_metrics"), patch("synthetic_banking.privacy.SparkPrivacyChecks") as engine:
            engine.return_value.run.return_value = metrics or complete_metrics()
            result = run_privacy_assessment(spark, "source-A", "generation-B", batch_id="batch-A")
        return result, spark

    def test_assessment_reads_exact_versions_and_records_an_independent_decision(self):
        result, spark = self.assessment()
        self.assertEqual(result.status, "PASS")
        self.assertEqual([r["status"] for r in self.saved], ["RUNNING", "PASS"])
        self.assertEqual(spark.read.option.call_count, 12)
        spark.read.option.assert_any_call("versionAsOf", 2)
        spark.read.option.assert_any_call("versionAsOf", 3)
        failed = complete_metrics(); failed[0].status = "FAIL"
        result, _ = self.assessment(failed)
        self.assertEqual(result.status, "BLOCKED")  # No exception blocks aggregate reporting.
        result, _ = self.assessment([PrivacyMetric("INCOMPLETE", "PERSON", (), "PASS")])
        self.assertEqual(result.status, "BLOCKED")

    def test_unavailable_source_or_failed_check_blocks_without_logging_source_rows(self):
        spark = SimpleNamespace(read=SimpleNamespace(option=Mock()))
        with patch("synthetic_banking.privacy._save_assessment"), patch("synthetic_banking.privacy._save_metrics"), patch(
                "synthetic_banking.privacy.load_source_snapshots", side_effect=ValueError("PRIVATE_SOURCE_RECORD")), redirect_stdout(StringIO()) as output:
            result = run_privacy_assessment(spark, "source-A", "generation-B")
        self.assertEqual(result.status, "BLOCKED")
        self.assertNotIn("PRIVATE_SOURCE_RECORD", output.getvalue() + json.dumps(result.metrics[0].record()))

    def guard_spark(self, metrics=None):
        self.latest = dict(assessment_id="assessment-C", source_run_id="source-A", generation_id="generation-B", status="PASS",
            completed_at=datetime.now(timezone.utc), policy_sha256=PrivacyPolicy().fingerprint,
            generated_versions_json=json.dumps(self.state["validated_versions"]), source_snapshot_sha256=snapshot_signature(self.snapshots), metric_count=25)
        self.metric_rows = [m.record() for m in (metrics or complete_metrics())]
        def sql(query, args):
            rows = [Row(self.latest)] if "privacy_assessments" in query else [Row(row) for row in self.metric_rows]
            return SimpleNamespace(collect=lambda: rows)
        return SimpleNamespace(catalog=SimpleNamespace(tableExists=lambda _: True), sql=sql)

    def test_release_is_bound_to_current_assessment_policy_inputs_and_all_checks(self):
        spark = self.guard_spark()
        self.assertEqual(require_row_level_release(spark, "source-A", "generation-B", "assessment-C")["status"], "PASS")
        for change in ({"status": "BLOCKED"}, {"status": "REVIEW_REQUIRED"}, {"status": "RUNNING"},
                       {"assessment_id": "newer-assessment"}, {"policy_sha256": "old-policy"}, {"source_snapshot_sha256": "other"},
                       {"generated_versions_json": "{}"}, {"source_run_id": "wrong-source"}):
            with self.subTest(change=change):
                spark = self.guard_spark(); self.latest.update(change)
                with self.assertRaises(PrivacyGateError): require_row_level_release(spark, "source-A", "generation-B", "assessment-C")
        spark = self.guard_spark(); self.metric_rows.pop()
        with self.assertRaises(PrivacyGateError): require_row_level_release(spark, "source-A", "generation-B", "assessment-C")
        spark = self.guard_spark(); self.metric_rows[0]["status"] = "INFO"
        with self.assertRaises(PrivacyGateError): require_row_level_release(spark, "source-A", "generation-B", "assessment-C")

    def test_missing_assessment_and_unguarded_csv_archives_fail_closed(self):
        spark = self.guard_spark(); spark.catalog.tableExists = lambda _: False
        with self.assertRaises(PrivacyGateError): require_row_level_release(spark, "source-A", "generation-B", "assessment-C")
        with self.assertRaises(PrivacyGateError): require_row_level_release(spark, "source-A", "generation-B", "")
        from synthetic_banking.artifacts import zip_existing_csvs
        with TemporaryDirectory() as folder:
            target = Path(folder) / "rows.zip"
            with self.assertRaisesRegex(PrivacyGateError, "packaging is disabled"):
                zip_existing_csvs(folder, local_path=str(target))
            self.assertFalse(target.exists())

    def test_policy_threshold_changes_invalidate_a_prior_pass(self):
        self.assertNotEqual(PrivacyPolicy().fingerprint, replace(PrivacyPolicy(), rare_min_count=10).fingerprint)
        for settings in ({"rare_min_count": 0}, {"near_date_days": -1}, {"min_complete_fraction": 0}, {"max_similarity_candidates": 0}):
            with self.assertRaises(ValueError): PrivacyPolicy(**settings)
        for status in ("FAIL", "ERROR", "UNAVAILABLE"):
            self.assertEqual(disclosure_status([PrivacyMetric("X", "PERSON", (), status)]), "BLOCKED")
        self.assertEqual(disclosure_status([]), "BLOCKED")


class SourceSnapshotTests(unittest.TestCase):
    def test_source_version_or_alias_changes_cannot_silently_validate_a_snapshot(self):
        inputs = {name: f"{CATALOG}.{alias}" for name, alias in SOURCE_ALIASES.items()}
        def sql(query):
            if query.startswith("SHOW CREATE"):
                alias = query.removeprefix("SHOW CREATE TABLE ").replace("`", "")
                table = next(table for table, value in inputs.items() if value == alias)
                return SimpleNamespace(first=lambda: (f"CREATE VIEW {alias} AS SELECT * FROM {STAGING_SCHEMA}.{table}",))
            raise AssertionError("Unexpected query")
        spark = SimpleNamespace(sql=sql)
        with patch("synthetic_banking.privacy_sources.delta_identity", return_value=("table-id", 2)), patch(
                "synthetic_banking.privacy_sources._save") as save:
            rows = capture_source_inputs(spark, "source-A", inputs)
            self.assertTrue(all(r["status"] == "CAPTURED" for r in rows))
            finalize_source_inputs(spark, "source-A", inputs, rows)
            self.assertTrue(all(r["status"] == "VERIFIED" for r in save.call_args.args[2]))
            with patch("synthetic_banking.privacy_sources.delta_identity", return_value=("table-id", 3)):
                finalize_source_inputs(spark, "source-A", inputs, rows)
            self.assertTrue(all(r["status"] == "UNAVAILABLE" for r in save.call_args.args[2]))
            with patch("synthetic_banking.privacy_sources._alias_digest", side_effect=ValueError("PRIVATE_RECORD")), redirect_stdout(StringIO()) as output:
                rows = capture_source_inputs(spark, "source-A", inputs)
            self.assertTrue(all(r["status"] == "UNAVAILABLE" for r in rows))
            self.assertNotIn("PRIVATE_RECORD", output.getvalue())


if __name__ == "__main__":
    unittest.main()
