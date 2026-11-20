from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
import json
import math
from pathlib import Path
import runpy
import statistics
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import sqlite3
import unittest

from synthetic_banking.fidelity import compare_profiles
from synthetic_banking.numeric_dependencies import NUMERIC_PAIRS, load_numeric_evidence, profile_numeric_dependencies
from test_categorical_profiling import CategoricalSpark


PAIR = (NUMERIC_PAIRS[0],)


class Stddev:
    def __init__(self):
        self.values = []

    def step(self, value):
        if value is not None:
            self.values.append(value)

    def finalize(self):
        return statistics.stdev(self.values) if len(self.values) >= 2 else None


class Pearson:
    def __init__(self):
        self.x, self.y = [], []

    def step(self, x, y):
        if x is not None and y is not None:
            self.x.append(x)
            self.y.append(y)

    def finalize(self):
        if len(self.x) < 2 or min(self.x) == max(self.x) or min(self.y) == max(self.y):
            return None
        return statistics.correlation(self.x, self.y)


class Percentile:
    """Exact nearest-rank fixture adapter; Databricks computes percentile_approx."""
    def __init__(self):
        self.values, self.p = [], None

    def step(self, value, percentile, accuracy):
        self.p = percentile
        if value is not None:
            self.values.append(value)

    def finalize(self):
        return sorted(self.values)[max(0, math.ceil(len(self.values) * self.p) - 1)] if self.values else None


class NumericSpark(CategoricalSpark):
    def __init__(self):
        super().__init__()
        self.db.create_aggregate("STDDEV_SAMP", 1, Stddev)
        self.db.create_aggregate("CORR", 2, Pearson)
        self.db.create_aggregate("PERCENTILE_APPROX", 3, Percentile)
        self.db.create_function("ISNAN", 1, lambda x: x is not None and math.isnan(x))
        self.db.executescript("""
            DELETE FROM active_column_inventory;
            ALTER TABLE active_profile_run ADD COLUMN source_run_id;
            ALTER TABLE active_profile_run ADD COLUMN generation_id;
        """)
        by_view, metadata = {}, {}
        for pair in NUMERIC_PAIRS:
            view = "active_account_features" if pair.entity_name == "ACCOUNT" else "active_tradeline_features"
            fields = by_view.setdefault(view, {})
            for qualified, role, sql_type in ((pair.variable_1, "NUMERIC", "REAL"), (pair.variable_2, "NUMERIC", "REAL"),
                                               (pair.segment_column, "CATEGORICAL_CANDIDATE", "TEXT")):
                table, column = qualified.split(".")
                metadata[table, column] = role
                fields[column] = sql_type
        self.dtypes = {}
        for view, fields in by_view.items():
            self.db.execute(f"CREATE TABLE {view} ({', '.join(name + ' ' + kind for name, kind in fields.items())})")
            self.dtypes[view] = [(name, "double" if kind == "REAL" else "string") for name, kind in fields.items()]
        self.db.executemany("INSERT INTO active_column_inventory VALUES (?, ?, ?)", [(table, column, role) for (table, column), role in metadata.items()])
        self.request = None
        self.table = lambda name: SimpleNamespace(first=lambda: self.request) if name == "ai_account_rule_input" else SimpleNamespace(dtypes=self.dtypes[name])

    def observations(self, rows):
        self.db.execute("DELETE FROM active_account_features")
        self.db.executemany("INSERT INTO active_account_features (CREDIT_LIMIT_AMT, CURRENT_BALANCE_AMT, CLIENT_PRODUCT_CD) VALUES (?, ?, ?)", rows)

    def mixed_populations(self):
        self.observations([(i, 100 - i, "FAKE-PRODUCT-A") for i in range(100)]
                          + [(i, 300 - i, "FAKE-PRODUCT-B") for i in range(100, 200)])

    def complete_source(self):
        self.db.execute("UPDATE profile_runs SET status='COMPLETED', completed_at='2026-01-01' WHERE run_id='source-A'")


class NumericProfilingTests(unittest.TestCase):
    def setUp(self):
        self.spark = NumericSpark()
        self.addCleanup(self.spark.db.close)
        output = redirect_stdout(StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def test_documented_pearson_and_complete_finite_pair_counts(self):
        # Databricks corr documentation's fabricated VALUES example.
        self.spark.observations([(3, 2, "FAKE"), (3, 3, "FAKE"), (3, 3, "FAKE"), (6, 4, "FAKE"),
                                 (None, 2, "FAKE"), (4, None, "FAKE"), (float("inf"), 2, "FAKE")])
        rows = profile_numeric_dependencies(self.spark, PAIR)
        global_row = next(row for row in rows if row["scope"] == "GLOBAL")
        self.assertAlmostEqual(global_row["pearson_correlation"], .816496580927726)
        self.assertEqual((global_row["population_count"], global_row["non_null_pair_count"], global_row["pair_count"]), (7, 5, 4))
        self.assertEqual((global_row["excluded_null_count"], global_row["excluded_nonfinite_count"]), (2, 1))
        self.assertEqual((global_row["x_mean"], global_row["y_mean"]), (3.75, 3))
        self.assertAlmostEqual(global_row["pair_fraction"], 4 / 7)
        self.assertTrue(any(row["skip_reason"] == "source_quantiles_missing_or_not_distinct" for row in rows))

    def test_global_sign_can_differ_from_segments_and_quantile_means_show_mixture(self):
        self.spark.mixed_populations()
        rows = profile_numeric_dependencies(self.spark, PAIR)
        global_row = next(row for row in rows if row["scope"] == "GLOBAL")
        categories = [row for row in rows if row["scope"] == "CATEGORY"]
        quartiles = [row for row in rows if row["scope"] == "X_QUARTILE"]
        self.assertGreater(global_row["pearson_correlation"], .49)
        self.assertTrue(all(row["pearson_correlation"] == -1 and row["pair_count"] == 100 for row in categories))
        self.assertEqual([row["pair_count"] for row in quartiles], [50, 50, 50, 50])
        self.assertGreater(quartiles[0]["y_mean"], quartiles[1]["y_mean"])
        self.assertGreater(quartiles[2]["y_mean"], quartiles[1]["y_mean"])
        self.assertEqual((quartiles[0]["lower_bound"], quartiles[0]["upper_bound"], quartiles[-1]["upper_bound"]), (None, 49, None))

    def test_default_pairs_are_bounded_and_reruns_replace_only_the_active_run(self):
        self.spark.mixed_populations()
        rows = profile_numeric_dependencies(self.spark)
        self.assertEqual(len([row for row in rows if row["scope"] == "GLOBAL"]), 10)
        self.assertLessEqual(len(rows), 12 * 11)
        again = profile_numeric_dependencies(self.spark)
        self.assertEqual(rows, again)
        self.assertEqual(self.spark.db.execute("SELECT COUNT(*) FROM numeric_dependency_profile").fetchone()[0], len(rows))
        self.assertTrue(all(row["profile_type"] == "SOURCE" and row["run_id"] == "source-A" for row in rows))

    def test_constant_empty_and_insufficient_cases_are_not_misreported_as_zero_correlation(self):
        for observations, expected in (([(3, i, "FAKE") for i in range(8)], "CONSTANT"), ([], "EMPTY"), ([(1, 2, "FAKE")], "INSUFFICIENT")):
            self.spark.observations(observations)
            rows = profile_numeric_dependencies(self.spark, PAIR)
            row = next(row for row in rows if row["scope"] == "GLOBAL")
            self.assertEqual(row["profile_status"], expected)
            self.assertIsNone(row["pearson_correlation"])

    def test_missing_numeric_classification_and_unbounded_pair_search_are_rejected(self):
        self.spark.mixed_populations()
        self.spark.db.execute("UPDATE active_column_inventory SET column_role='IDENTIFIER' WHERE column_name='CREDIT_LIMIT_AMT'")
        row = profile_numeric_dependencies(self.spark, PAIR)[0]
        self.assertEqual(row["skip_reason"], "not_classified_numeric")
        with self.assertRaisesRegex(ValueError, "1–12"):
            profile_numeric_dependencies(self.spark, PAIR * 13)
        reverse = replace(PAIR[0], variable_1=PAIR[0].variable_2, variable_2=PAIR[0].variable_1)
        with self.assertRaisesRegex(ValueError, "reversed duplicates"):
            profile_numeric_dependencies(self.spark, (*PAIR, reverse))
        with self.assertRaisesRegex(ValueError, "existing input tables"):
            profile_numeric_dependencies(self.spark, (replace(PAIR[0], variable_1="PERSON.PARTY_ID"),))

    def test_high_cardinality_segments_are_skipped_without_truncating_the_global_profile(self):
        self.spark.observations([(i, 2 * i, f"FAKE-{i % 7}") for i in range(140)])
        rows = profile_numeric_dependencies(self.spark, PAIR)
        self.assertEqual(next(row for row in rows if row["scope"] == "GLOBAL")["pair_count"], 140)
        self.assertFalse(any(row["scope"] == "CATEGORY" for row in rows))
        status = next(row for row in rows if row["scope"] == "CATEGORY_STATUS")
        self.assertEqual((status["segment_count"], status["skip_reason"]), (7, "segment_cardinality_limit"))
        self.assertEqual(len([row for row in rows if row["scope"] == "X_QUARTILE"]), 4)

    def test_null_segment_and_literal_null_label_are_distinct_groups(self):
        self.spark.observations([(i, i * 2, None if i < 100 else "NULL") for i in range(200)])
        rows = profile_numeric_dependencies(self.spark, PAIR)
        categories = [row for row in rows if row["scope"] == "CATEGORY"]
        self.assertEqual({(row["segment_value"], row["segment_is_null"]) for row in categories}, {(None, True), ("NULL", False)})

    def test_generated_profiles_reuse_pinned_source_cutpoints_and_preserve_source_history(self):
        self.spark.mixed_populations()
        source = profile_numeric_dependencies(self.spark, PAIR)
        self.spark.complete_source()
        self.spark.db.executescript("""
            UPDATE active_profile_run SET run_id='generated-B', profile_type='GENERATED', source_run_id='source-A', generation_id='generation-1';
            INSERT INTO profile_runs VALUES ('generated-B', 'GENERATED', 'RUNNING', NULL);
            UPDATE active_account_features SET CREDIT_LIMIT_AMT = 10 * CREDIT_LIMIT_AMT;
        """)
        generated = profile_numeric_dependencies(self.spark, PAIR)
        self.assertEqual(next(row for row in generated if row["scope"] == "GLOBAL")["x_p25"], 490)
        q1 = next(row for row in generated if row["scope"] == "X_QUARTILE" and row["segment_value"] == "Q1")
        self.assertEqual((q1["upper_bound"], q1["pair_count"]), (49, 5))
        self.assertEqual(self.spark.db.execute("SELECT COUNT(*) FROM numeric_dependency_profile WHERE run_id='source-A'").fetchone()[0], len(source))
        self.assertEqual(load_numeric_evidence(self.spark, "generated-B"), [])
        report = compare_profiles("source-A", "generated-B", "generation-1", {"numeric_dependency_profile": source + generated})
        quarter = [row for row in report["metrics"] if row["family"] == "NUMERIC_DEPENDENCY" and row["metric"] == "y_mean"
                   and json.loads(row["dimensions_json"])["scope"] == "X_QUARTILE" and json.loads(row["dimensions_json"])["segment_value"] == "Q1"][0]
        self.assertEqual((quarter["source_sample_size"], quarter["generated_sample_size"]), (50, 5))
        self.assertEqual(quarter["comparison_status"], "COMPARABLE")
        q1["upper_bound"] = 50
        report = compare_profiles("source-A", "generated-B", "generation-1", {"numeric_dependency_profile": source + generated})
        self.assertTrue(any(row["reason"] == "different_source_quantile_boundaries" for row in report["metrics"]))

    def test_older_source_without_numeric_boundaries_does_not_use_generated_quantiles(self):
        self.spark.mixed_populations()
        self.spark.complete_source()
        self.spark.db.executescript("""
            UPDATE active_profile_run SET run_id='generated-B', profile_type='GENERATED', source_run_id='source-A', generation_id='generation-1';
            INSERT INTO profile_runs VALUES ('generated-B', 'GENERATED', 'RUNNING', NULL);
        """)
        rows = profile_numeric_dependencies(self.spark, PAIR)
        self.assertFalse(any(row["scope"] == "X_QUARTILE" for row in rows))
        self.assertTrue(any(row["scope"] == "X_QUARTILE_STATUS" for row in rows))


class NumericEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.spark = NumericSpark()
        self.addCleanup(self.spark.db.close)
        output = redirect_stdout(StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)
        self.spark.mixed_populations()

    def test_only_completed_source_aggregates_enter_context_and_segments_expose_global_ambiguity(self):
        profile_numeric_dependencies(self.spark, PAIR)
        self.assertEqual(load_numeric_evidence(self.spark, "source-A"), [])
        self.spark.complete_source()
        self.spark.db.set_authorizer(lambda action, table, *_: sqlite3.SQLITE_DENY
                                     if action == sqlite3.SQLITE_READ and table.startswith("active_") else sqlite3.SQLITE_OK)
        context = load_numeric_evidence(self.spark, "source-A")
        self.assertEqual(len(context), 1)
        evidence = context[0]
        self.assertEqual(evidence["population_unit"], "account_feature_join_rows")
        self.assertEqual(evidence["max_supported_abs_pearson"], 1)
        self.assertTrue(any(row["scope"] == "CATEGORY" and row["pearson_correlation"] == -1 for row in evidence["profiles"]))
        self.assertEqual(load_numeric_evidence(self.spark, "source-A", min_pair_count=201), [])
        with self.assertRaises(ValueError):
            load_numeric_evidence(self.spark, "source-A", max_pairs=13)
        self.assertNotIn("source-A", json.dumps(context))
        self.assertTrue(all("current_run" not in query for query, _ in self.spark.queries))

    def test_small_segments_withhold_descriptive_statistics_and_recorded_join_diagnostics_are_included(self):
        profile_numeric_dependencies(self.spark, PAIR)
        self.spark.complete_source()
        self.spark.db.executescript("""
            CREATE TABLE integrity_profile (run_id, profile_type, family, logical_table_name, metric, numerator, denominator, profile_status, reason);
            INSERT INTO integrity_profile VALUES ('source-A','SOURCE','JOIN_COVERAGE','TKQ_ACCOUNT','snapshot_join_coverage',200,200,'MEASURED',NULL);
        """)
        context = load_numeric_evidence(self.spark, "source-A", min_pair_count=60)
        quarters = [row for row in context[0]["profiles"] if row["scope"] == "X_QUARTILE"]
        self.assertTrue(all(row["pearson_correlation"] is None and row["y_mean"] is None and row["pair_count"] == 50 for row in quarters))
        self.assertTrue(all(row["profile_status"] == "INSUFFICIENT_FOR_PROMPT" for row in quarters))
        self.assertEqual(context[0]["join_diagnostics"][0]["numerator"], 200)

    def test_context_is_bounded_and_deleted_or_duplicate_segments_are_rejected(self):
        profile_numeric_dependencies(self.spark)
        self.spark.complete_source()
        self.assertLessEqual(len(load_numeric_evidence(self.spark, "source-A", max_pairs=1)), 1)
        self.spark.db.execute("DELETE FROM numeric_dependency_profile WHERE scope='X_QUARTILE' AND segment_value='Q1' AND variable_1=? AND variable_2=?", (PAIR[0].variable_1, PAIR[0].variable_2))
        with self.assertRaisesRegex(ValueError, "incomplete"):
            load_numeric_evidence(self.spark, "source-A")
        self.spark.db.execute("INSERT INTO numeric_dependency_profile SELECT * FROM numeric_dependency_profile WHERE scope='GLOBAL' LIMIT 1")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            load_numeric_evidence(self.spark, "source-A")

    def test_actual_prompt_cell_freezes_numeric_evidence_with_the_same_source_and_batch(self):
        profile_numeric_dependencies(self.spark, PAIR)
        self.spark.complete_source()
        self.spark.request = {"source_run_id": "source-A", "batch_id": "batch-A", "scope_name": "ACCOUNT_CORE", "profile_summary": "Fabricated aggregate column context"}
        self.spark.db.execute("CREATE TABLE conditional_profile (run_id, entity_name, condition_variable, outcome_variable, condition_bucket, record_count, outcome_rate)")
        notebook = json.loads((Path(__file__).resolve().parents[1] / "notebooks/02_LLM Rule Generation.ipynb").read_text(encoding="utf-8"))
        with TemporaryDirectory() as folder:
            path = Path(folder) / "prompt.py"
            path.write_text("".join(notebook["cells"][8]["source"]), encoding="utf-8")
            runpy.run_path(str(path), init_globals={"spark": self.spark})
        row = self.spark.db.execute("SELECT source_run_id, batch_id, prompt FROM ai_model_request").fetchone()
        self.assertEqual((row["source_run_id"], row["batch_id"]), ("source-A", "batch-A"))
        self.assertIn("Measured numeric dependency evidence", row["prompt"])
        self.assertIn('"pair_count": 200', row["prompt"])
        self.assertIn('"pearson_correlation": -1.0', row["prompt"])
        self.assertIn("It does not establish causation", row["prompt"])
        self.assertIn("not a fitted conditional sampling model", row["prompt"])


if __name__ == "__main__":
    unittest.main()
