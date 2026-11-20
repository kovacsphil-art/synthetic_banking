from contextlib import redirect_stdout
from datetime import date, datetime
from io import StringIO
import json
from pathlib import Path
import re
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from synthetic_banking.fidelity import (
    compare_profiles, create_fidelity_report, export_fidelity_report, profile_fidelity_inputs,
)
from test_categorical_profiling import CategoricalSpark


def profiles_fixture():
    """Fabricated aggregate measurements; never source banking records."""
    profiles = {name: [] for name in (
        "column_quality", "numeric_profile", "category_profile", "date_profile", "date_distribution_profile",
        "cardinality_profile", "relationship_profile", "conditional_profile", "integrity_profile",
        "categorical_relationship_profile",
    )}
    for run, n in (("source-A", 100), ("generated-B", 200)):
        source = run == "source-A"
        profiles["column_quality"].extend([
            {"run_id": run, "logical_table_name": "TKQ_ACCOUNT", "column_name": "FLAG", "row_count": n, "null_count": 10 if source else 0},
            {"run_id": run, "logical_table_name": "TKQ_ACCOUNT", "column_name": "AMOUNT", "row_count": n, "null_count": 0},
        ])
        profiles["numeric_profile"].append({"run_id": run, "logical_table_name": "TKQ_ACCOUNT", "column_name": "AMOUNT",
            "non_null_count": n, "mean_value": 10 if source else 15, "p01": 0, "p05": 1, "p25": 5,
            "p50": 10 if source else 15, "p75": 15, "p95": 19, "p99": 20, "min_value": 0, "max_value": 20, "stddev_value": 4})
        for category, count in (("Y", 40), ("N", 50), (None, 10)) if source else (("Y", 120), ("N", 80)):
            profiles["category_profile"].append({"run_id": run, "logical_table_name": "TKQ_ACCOUNT", "column_name": "FLAG",
                "category_value": category, "record_count": count, "proportion": count / n})
        profiles["date_profile"].append({"run_id": run, "logical_table_name": "TKQ_ACCOUNT", "column_name": "OPEN_DT",
            "non_null_count": n, "earliest_date": date(2020, 1, 1) if source else date(2020, 1, 4),
            "latest_date": date(2020, 3, 1) if source else date(2020, 4, 1)})
        for month, count in (("2020-01", 20), ("2020-02", 80)) if source else (("2020-01", 80), ("2020-02", 100), ("2020-03", 20)):
            profiles["date_distribution_profile"].append({"run_id": run, "logical_table_name": "TKQ_ACCOUNT", "column_name": "OPEN_DT",
                "month_bucket": month, "record_count": count, "non_null_count": n, "proportion": count / n})
        for cardinality, count in ((1, 80), (2, 20)) if source else ((1, 20), (2, 80)):
            profiles["cardinality_profile"].append({"run_id": run, "relationship_name": "ACCOUNTS_PER_PARTY", "cardinality": cardinality,
                "entity_count": count, "proportion": count / 100})
        profiles["relationship_profile"].append({"run_id": run, "entity_name": "ACCOUNT", "variable_1": "LIMIT", "variable_2": "BALANCE",
            "metric_type": "PEARSON_CORRELATION", "metric_value": .8 if source else .5})
        profiles["conditional_profile"].append({"run_id": run, "entity_name": "ACCOUNT", "condition_variable": "UTILIZATION_RATE",
            "outcome_variable": "PAST_DUE_INDICATO_CD", "condition_bucket": "0-30%", "record_count": 40 if source else 80,
            "outcome_rate": .1 if source else .25})
        profiles["categorical_relationship_profile"].append({"run_id": run, "logical_table_name": "TKQ_ACCOUNT", "parent_column": "PRODUCT",
            "child_column": "FLAG", "profile_status": "PROFILED", "sample_size": n, "cramers_v": .5 if source else .25,
            "sparse_expected_cell_fraction": 0})
        for family, metric, numerator in (("JOIN_COVERAGE", "snapshot_join_coverage", 90 if source else n),
                                          ("BUSINESS_RULE", "available_to_buy_formula", 5 if source else 0)):
            profiles["integrity_profile"].append({"run_id": run, "family": family, "logical_table_name": "TKQ_ACCOUNT_BALANCE",
                "metric": metric, "numerator": numerator, "denominator": n, "profile_status": "MEASURED", "reason": None})
        profiles["integrity_profile"].append({"run_id": run, "family": "BUSINESS_RULE", "logical_table_name": "TKQ_ACCOUNT",
            "metric": "utilization_formula", "numerator": None if source else 0, "denominator": None if source else n,
            "profile_status": "UNAVAILABLE" if source else "MEASURED", "reason": "missing_required_columns" if source else None})
    return profiles


def find(report, family, metric=None, **dims):
    rows = [row for row in report["metrics"] if row["family"] == family and (metric is None or row["metric"] == metric)
            and all(json.loads(row["dimensions_json"]).get(k) == v for k, v in dims.items())]
    if len(rows) != 1:
        raise AssertionError(f"Expected one metric, found {len(rows)}: {family} / {metric} / {dims}")
    return rows[0]


class FidelityComparisonTests(unittest.TestCase):
    def setUp(self):
        self.profiles = profiles_fixture()

    def report(self):
        return compare_profiles("source-A", "generated-B", "generation-1", self.profiles)

    def test_all_requested_families_and_explicit_provenance(self):
        report = self.report()
        required = {"NUMERIC", "CATEGORICAL", "NULL_RATE", "DATE_DISTRIBUTION", "CARDINALITY", "CORRELATION", "CONDITIONAL", "JOIN_COVERAGE", "BUSINESS_RULE"}
        self.assertTrue(required <= {row["family"] for row in report["metrics"]})
        self.assertTrue(all((row["source_run_id"], row["generated_run_id"], row["generation_id"]) ==
                            ("source-A", "generated-B", "generation-1") for row in report["metrics"]))
        self.assertNotIn("overall_score", report)
        self.assertTrue(any(row["entity_name"] == "TRADELINES_PER_CIF" and row["comparison_status"] == "NOT_COMPARABLE"
                            for row in report["metrics"]))
        mean = find(report, "NUMERIC", "mean_value")
        self.assertEqual((mean["source_value"], mean["generated_value"], mean["difference"], mean["relative_difference_pct"]), (10, 15, 5, 50))
        self.assertEqual((mean["deviation_value"], mean["ranking_basis"]), (.5, "absolute_difference/source_IQR"))
        self.assertEqual((mean["source_sample_size"], mean["generated_sample_size"]), (100, 200))

    def test_union_of_categories_null_category_and_zero_filling_only_complete_profiles(self):
        report = self.report()
        missing_level = find(report, "CATEGORICAL", category_value=None)
        self.assertEqual((missing_level["source_value"], missing_level["generated_value"], missing_level["difference"]), (.1, 0, -10))
        self.assertEqual(missing_level["comparison_status"], "COMPARABLE")
        self.profiles["category_profile"] = [r for r in self.profiles["category_profile"] if r["run_id"] == "source-A"]
        missing_profile = find(self.report(), "CATEGORICAL", category_value="Y")
        self.assertEqual(missing_profile["comparison_status"], "NOT_COMPARABLE")
        self.assertIsNone(missing_profile["generated_value"])
        self.assertIn("generated_profile", missing_profile["reason"])

    def test_incomplete_distribution_does_not_masquerade_as_absent_categories(self):
        self.profiles["category_profile"].pop()
        # The remaining generated counts/proportions are inconsistent, so refuse the corrupted profile.
        with self.assertRaisesRegex(ValueError, "proportions"):
            self.report()

    def test_null_dates_cardinalities_correlation_and_conditional_units(self):
        report = self.report()
        nulls = [r for r in report["metrics"] if r["family"] == "NULL_RATE" and r["column_name"] == "FLAG"][0]
        self.assertEqual((nulls["difference"], nulls["difference_unit"]), (-10, "percentage_points"))
        earliest = find(report, "DATE_RANGE", "earliest_date")
        self.assertEqual((earliest["source_display"], earliest["generated_display"], earliest["difference"], earliest["difference_unit"]), ("2020-01-01", "2020-01-04", 3, "days"))
        self.assertIsNone(earliest["relative_difference_pct"])
        month = find(report, "DATE_DISTRIBUTION", month_bucket="2020-03")
        self.assertEqual((month["source_value"], month["generated_value"], month["difference"]), (0, .1, 10))
        self.assertAlmostEqual(find(report, "CARDINALITY", "mean_cardinality")["difference"], .6)
        self.assertAlmostEqual(find(report, "CORRELATION")["difference"], -.3)
        conditional = find(report, "CONDITIONAL")
        self.assertAlmostEqual(conditional["difference"], 15)
        self.assertEqual((conditional["source_sample_size"], conditional["generated_sample_size"]), (40, 80))

    def test_missing_bucket_does_not_become_a_zero_probability(self):
        self.profiles["conditional_profile"][1]["condition_bucket"] = "30-60%"
        report = self.report()
        self.assertTrue(all(row["comparison_status"] == "NOT_COMPARABLE" and row["difference"] is None
                            for row in report["metrics"] if row["family"] == "CONDITIONAL"))

    def test_unknown_and_empty_sample_counts_remain_unavailable(self):
        self.profiles["conditional_profile"][0]["record_count"] = None
        self.profiles["integrity_profile"][0].update(denominator=0, numerator=0, profile_status="EMPTY")
        report = self.report()
        self.assertEqual(find(report, "CONDITIONAL")["comparison_status"], "NOT_COMPARABLE")
        self.assertEqual(find(report, "JOIN_COVERAGE")["comparison_status"], "NOT_COMPARABLE")
        self.assertEqual(find(report, "JOIN_COVERAGE")["generated_check_status"], "PASS")

    def test_old_date_profiles_explicitly_report_missing_distribution(self):
        self.profiles["date_distribution_profile"] = []
        report = self.report()
        self.assertEqual(find(report, "DATE_RANGE", "earliest_date")["comparison_status"], "COMPARABLE")
        self.assertEqual(find(report, "DATE_DISTRIBUTION")["comparison_status"], "NOT_COMPARABLE")

    def test_zero_baseline_and_constant_iqr_leave_raw_differences_visible(self):
        s = self.profiles["numeric_profile"][0]
        s.update(mean_value=0, p25=5, p75=5)
        mean = find(self.report(), "NUMERIC", "mean_value")
        self.assertEqual(mean["difference"], 15)
        self.assertIsNone(mean["relative_difference_pct"])
        self.assertIsNone(mean["deviation_rank"])
        self.assertEqual(mean["comparison_status"], "COMPARABLE")

    def test_generated_checks_distinct_from_fidelity_availability_and_source_violations(self):
        report = self.report()
        self.assertEqual(find(report, "JOIN_COVERAGE")["generated_check_status"], "PASS")
        rule = find(report, "BUSINESS_RULE", "available_to_buy_formula")
        self.assertEqual((rule["source_count"], rule["generated_count"], rule["difference"]), (5, 0, -5))
        utilization = find(report, "BUSINESS_RULE", "utilization_formula")
        self.assertEqual((utilization["comparison_status"], utilization["generated_check_status"]), ("NOT_COMPARABLE", "PASS"))
        next(r for r in self.profiles["integrity_profile"] if r["run_id"] == "generated-B" and r["family"] == "JOIN_COVERAGE")["numerator"] = 190
        self.assertEqual(find(self.report(), "JOIN_COVERAGE")["generated_check_status"], "ISSUE")

    def test_missing_families_nonfinite_values_and_largest_deviations_are_explicit(self):
        empty = compare_profiles("source-A", "generated-B", "generation-1", {})
        self.assertTrue(all(r["comparison_status"] == "NOT_COMPARABLE" for r in empty["metrics"]))
        self.profiles["numeric_profile"][1]["p99"] = float("nan")
        report = self.report()
        self.assertEqual(find(report, "NUMERIC", "p99")["comparison_status"], "NOT_COMPARABLE")
        largest = [r for r in report["metrics"] if r["family"] == "NUMERIC" and r["highlight"]]
        self.assertEqual({r["metric"] for r in largest}, {"mean_value", "p50"})
        self.assertTrue(all(r["deviation_rank"] <= 5 for r in largest))
        self.assertIsNotNone(find(report, "DATE_RANGE", "latest_date")["deviation_rank"])

    def test_duplicate_mixed_runs_wrong_types_and_inconsistent_counts_are_rejected(self):
        self.profiles["numeric_profile"].append(dict(self.profiles["numeric_profile"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.report()
        self.profiles["numeric_profile"].pop()
        self.profiles["numeric_profile"][0]["run_id"] = "wrong-run"
        with self.assertRaisesRegex(ValueError, "explicit comparison"):
            self.report()
        self.profiles = profiles_fixture()
        self.profiles["integrity_profile"][0]["profile_type"] = "GENERATED"
        with self.assertRaisesRegex(ValueError, "profile_type"):
            self.report()
        self.profiles = profiles_fixture()
        self.profiles["column_quality"][0]["row_count"] = 99
        with self.assertRaisesRegex(ValueError, "table counts"):
            self.report()

    def test_json_export_is_explicit_machine_readable_and_contains_lineage(self):
        with TemporaryDirectory() as folder:
            path = export_fidelity_report(self.report(), folder)
            document = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(document["source_run_id"], "source-A")
            self.assertEqual(document["generated_run_id"], "generated-B")
            self.assertIsInstance(document["created_at"], str)
            self.assertTrue(document["metrics"])
        with self.assertRaisesRegex(ValueError, "absolute"):
            export_fidelity_report(self.report(), "relative-output")

    def test_overflow_is_unavailable_and_invalid_null_and_integrity_counts_are_rejected(self):
        self.profiles["numeric_profile"][0]["mean_value"] = -1e308
        self.profiles["numeric_profile"][1]["mean_value"] = 1e308
        metric = find(self.report(), "NUMERIC", "mean_value")
        self.assertEqual((metric["comparison_status"], metric["reason"]), ("NOT_COMPARABLE", "nonfinite_difference"))
        with TemporaryDirectory() as folder:
            export_fidelity_report(self.report(), folder)
        self.profiles["column_quality"][0]["null_count"] = 101
        with self.assertRaisesRegex(ValueError, "Null counts"):
            self.report()
        self.profiles["column_quality"][0]["null_count"] = 10
        self.profiles["integrity_profile"][0]["numerator"] = 101
        with self.assertRaisesRegex(ValueError, "Integrity counts"):
            self.report()


class FidelitySpark(CategoricalSpark):
    def __init__(self):
        super().__init__()
        self.db.create_function("DATE_FORMAT", 2, lambda value, fmt: str(value)[:7] if value else None)
        self.db.create_function("GREATEST", -1, lambda *values: max([x for x in values if x is not None], default=None))
        self.db.executescript("""
            ALTER TABLE active_profile_run ADD COLUMN source_run_id;
            ALTER TABLE active_profile_run ADD COLUMN generation_id;
            DELETE FROM active_column_inventory;
            CREATE TABLE accounts (ACCOUNT_ID TEXT, BUSINESSEFFECTIVEDATE TEXT, CREDIT_LIMIT_AMT REAL,
                _UTILIZATION_RATE REAL, PAST_DUE_INDICATO_CD TEXT, DELINQUENCY_CNT INTEGER);
            CREATE TABLE balances (ACCOUNT_ID TEXT, BUSINESSEFFECTIVEDATE TEXT, CURRENT_BALANCE_AMT REAL,
                AVAILABLE_TO_BUY_AMT REAL, OVERLIMIT_AMT REAL);
            CREATE TABLE people (BIRTH_DT TEXT, SINCE_DT TEXT);
            INSERT INTO people VALUES ('2000-01-01', '2020-01-01'), ('2000-02-01', '1999-01-01');
        """)
        self.inputs = {"PERSON": "people", "TKQ_ACCOUNT": "accounts", "TKQ_ACCOUNT_BALANCE": "balances"}
        for table, obj in self.inputs.items():
            for row in self.db.execute(f"PRAGMA table_info({obj})"):
                name = row["name"]
                # The original source does not store the generator's private utilization field.
                if name == "_UTILIZATION_RATE":
                    continue
                role = "DATE" if name.endswith("_DT") or name == "BUSINESSEFFECTIVEDATE" else "OTHER"
                self.db.execute("INSERT INTO active_column_inventory VALUES (?, ?, ?)", (table, name, role))
        self.db.executemany("INSERT INTO accounts VALUES (?, ?, 100, .5, 'N', 0)",
                            [("FAKE-A", "2020-01-01"), ("FAKE-A", "2020-01-01"), ("FAKE-A", "2020-02-01"), ("FAKE-B", "2020-01-01")])
        self.db.executemany("INSERT INTO balances VALUES (?, ?, 50, 50, 0)",
                            [("FAKE-A", "2020-01-01")] * 3 + [("FAKE-B", "2020-02-01")])

    def createDataFrame(self, rows, schema):
        # Use an explicit local timestamp adapter; production keeps Spark TIMESTAMP values.
        rows = [{key: value.isoformat() if isinstance(value, (date, datetime)) else value
                 for key, value in row.items()} if isinstance(row, dict) else row for row in rows]
        return super().createDataFrame(rows, schema)

    def sql(self, query, args=None):
        query = re.sub(r"CAST\((`[^`]+`) AS DATE\)", r"\1", query)
        replacement = re.fullmatch(r"INSERT INTO ([\w.]+) REPLACE WHERE generated_run_id = :generated SELECT \* FROM (\w+)", " ".join(query.split()))
        if replacement:
            self.queries.append((query, args))
            table, view = replacement.groups()
            table = table.split(".")[-1]
            with self.db:
                self.db.execute(f"DELETE FROM {table} WHERE generated_run_id = :generated", args)
                self.db.execute(f"INSERT INTO {table} SELECT * FROM {view}")
            return SimpleNamespace(collect=lambda: [])
        return super().sql(query, args)


class FidelityPipelineTests(unittest.TestCase):
    def setUp(self):
        self.spark = FidelitySpark()
        self.addCleanup(self.spark.db.close)
        output = redirect_stdout(StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def profile_source(self):
        profile_fidelity_inputs(self.spark, self.spark.inputs)
        self.spark.db.execute("UPDATE profile_runs SET status='COMPLETED', completed_at='2026-01-01' WHERE run_id='source-A'")

    def profile_generated(self):
        self.spark.db.executescript("""
            UPDATE active_profile_run SET run_id='generated-B', profile_type='GENERATED', source_run_id='source-A', generation_id='generation-1';
            INSERT INTO profile_runs VALUES ('generated-B', 'GENERATED', 'RUNNING', NULL);
            INSERT INTO active_column_inventory VALUES ('TKQ_ACCOUNT', '_UTILIZATION_RATE', 'NUMERIC');
        """)
        profile_fidelity_inputs(self.spark, self.spark.inputs)
        self.spark.db.execute("UPDATE profile_runs SET status='COMPLETED', completed_at='2026-01-02' WHERE run_id='generated-B'")

    def test_saved_row_coverage_handles_duplicates_and_date_mismatches_without_inflation(self):
        profile_fidelity_inputs(self.spark, self.spark.inputs)
        values = {tuple(row[k] for k in ("logical_table_name", "metric")): dict(row)
                  for row in self.spark.db.execute("SELECT * FROM integrity_profile")}
        a = values["TKQ_ACCOUNT", "snapshot_join_coverage"]
        b = values["TKQ_ACCOUNT_BALANCE", "snapshot_join_coverage"]
        self.assertEqual((a["numerator"], a["denominator"]), (2, 4))
        self.assertEqual((b["numerator"], b["denominator"]), (3, 4))
        self.assertEqual(values["TKQ_ACCOUNT", "duplicate_snapshot_rows"]["numerator"], 1)
        self.assertEqual(values["TKQ_ACCOUNT_BALANCE", "duplicate_snapshot_rows"]["numerator"], 2)
        # Invariants use the actual join-pair population (2 * 3), explicitly recorded as denominator.
        self.assertEqual(values["TKQ_ACCOUNT_BALANCE", "available_to_buy_formula"]["denominator"], 6)
        self.assertEqual(values["PERSON", "since_before_birth"]["numerator"], 1)
        self.assertEqual(values["TKQ_ACCOUNT", "utilization_formula"]["profile_status"], "UNAVAILABLE")
        counts = self.spark.db.execute("SELECT record_count, non_null_count FROM date_distribution_profile WHERE logical_table_name='TKQ_ACCOUNT' ORDER BY month_bucket").fetchall()
        self.assertEqual([tuple(row) for row in counts], [(3, 4), (1, 4)])

    def test_business_rules_count_actual_violations_and_missing_keys_are_reported(self):
        self.spark.db.execute("INSERT INTO active_column_inventory VALUES ('TKQ_ACCOUNT', '_UTILIZATION_RATE', 'NUMERIC')")
        self.spark.db.execute("UPDATE balances SET CURRENT_BALANCE_AMT=150")
        self.spark.db.execute("UPDATE accounts SET PAST_DUE_INDICATO_CD='Y'")
        self.spark.db.execute("INSERT INTO accounts VALUES (NULL, '2020-01-01', 100, .5, 'N', 0)")
        profile_fidelity_inputs(self.spark, self.spark.inputs)
        counts = {r["metric"]: r["numerator"] for r in self.spark.db.execute("SELECT * FROM integrity_profile WHERE family='BUSINESS_RULE'")}
        for metric in ("balance_cap", "available_to_buy_formula", "overlimit_formula", "utilization_formula"):
            self.assertEqual(counts[metric], 6)
        self.assertEqual(counts["negative_current_balance"], 0)
        self.assertEqual(counts["delinquency_flag_count"], 4)
        nulls = self.spark.db.execute("SELECT numerator, denominator FROM integrity_profile WHERE logical_table_name='TKQ_ACCOUNT' AND metric='null_snapshot_keys'").fetchone()
        self.assertEqual(tuple(nulls), (1, 5))
        # A retry replaces this run's evidence, including updated violation counts.
        self.spark.db.execute("UPDATE balances SET CURRENT_BALANCE_AMT=-1")
        profile_fidelity_inputs(self.spark, self.spark.inputs)
        self.assertEqual(self.spark.db.execute("SELECT numerator FROM integrity_profile WHERE metric='negative_current_balance'").fetchone()[0], 6)

    def test_profiling_and_reports_preserve_history_and_use_only_saved_aggregates(self):
        self.profile_source()
        self.profile_generated()
        self.spark.db.set_authorizer(lambda action, table, *_: sqlite3.SQLITE_DENY
                                     if action == sqlite3.SQLITE_READ and table in ("accounts", "balances", "people") else sqlite3.SQLITE_OK)
        report = create_fidelity_report(self.spark, "source-A", "generated-B")
        self.assertEqual(report["generation_id"], "generation-1")
        rows = self.spark.db.execute("SELECT COUNT(*) FROM fidelity_metrics").fetchone()[0]
        self.assertEqual(len(report["metrics"]), rows)
        second = create_fidelity_report(self.spark, "source-A", "generated-B")
        self.assertEqual(second["comparison_id"], report["comparison_id"])
        self.assertEqual(self.spark.db.execute("SELECT COUNT(*) FROM fidelity_metrics").fetchone()[0], rows)
        self.assertEqual(self.spark.db.execute("SELECT COUNT(*) FROM profile_run_lineage").fetchone()[0], 2)
        self.assertGreater(self.spark.db.execute("SELECT COUNT(*) FROM integrity_profile WHERE run_id='source-A'").fetchone()[0], 0)
        self.assertFalse(any("current_run" in query or "generation_state" in query for query, _ in self.spark.queries))
        # A report for a previous pair survives scoped replacement of the current one.
        self.spark.db.execute("UPDATE fidelity_metrics SET generated_run_id='historical-B' WHERE rowid=(SELECT MIN(rowid) FROM fidelity_metrics)")
        create_fidelity_report(self.spark, "source-A", "generated-B")
        self.assertEqual(self.spark.db.execute("SELECT COUNT(*) FROM fidelity_metrics WHERE generated_run_id='historical-B'").fetchone()[0], 1)

    def test_wrong_pair_types_incomplete_runs_and_missing_lineage_cannot_be_compared(self):
        self.profile_source()
        self.profile_generated()
        self.spark.db.execute("UPDATE profile_runs SET status='RUNNING' WHERE run_id='generated-B'")
        with self.assertRaisesRegex(ValueError, "completed"):
            create_fidelity_report(self.spark, "source-A", "generated-B")
        self.spark.db.execute("UPDATE profile_runs SET status='COMPLETED' WHERE run_id='generated-B'")
        with self.assertRaisesRegex(ValueError, "types"):
            create_fidelity_report(self.spark, "generated-B", "source-A")
        self.spark.db.execute("UPDATE profile_run_lineage SET source_run_id='different-source' WHERE run_id='generated-B'")
        with self.assertRaisesRegex(ValueError, "not linked"):
            create_fidelity_report(self.spark, "source-A", "generated-B")
        self.spark.db.execute("DROP TABLE profile_run_lineage")
        with self.assertRaisesRegex(ValueError, "lineage is unavailable"):
            create_fidelity_report(self.spark, "source-A", "generated-B")

    def test_generated_profiling_needs_completed_source_and_generation_identity(self):
        self.spark.db.executescript("""
            UPDATE active_profile_run SET run_id='generated-B', profile_type='GENERATED', source_run_id='source-A', generation_id='generation-1';
            INSERT INTO profile_runs VALUES ('generated-B', 'GENERATED', 'RUNNING', NULL);
        """)
        with self.assertRaisesRegex(ValueError, "pinned completed SOURCE"):
            profile_fidelity_inputs(self.spark, self.spark.inputs)
        self.spark.db.execute("UPDATE profile_runs SET status='COMPLETED', completed_at='2026-01-01' WHERE run_id='source-A'")
        self.spark.db.execute("UPDATE active_profile_run SET generation_id=NULL")
        with self.assertRaisesRegex(ValueError, "generation ID"):
            profile_fidelity_inputs(self.spark, self.spark.inputs)

    def test_temporal_counts_are_saved_for_both_runs_and_compared_with_provenance(self):
        self.profile_source()
        self.spark.db.execute("UPDATE people SET SINCE_DT='2020-01-01'")
        self.profile_generated()
        report = create_fidelity_report(self.spark, "source-A", "generated-B")
        row = find(report, "TEMPORAL_RULE", "BIRTH_DT<=SINCE_DT")
        self.assertEqual((row["source_count"], row["generated_count"], row["difference"]), (1, 0, -50))
        self.assertEqual(row["generated_check_status"], "PASS")


if __name__ == "__main__":
    unittest.main()
