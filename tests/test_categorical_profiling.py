from collections import defaultdict
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import re
import runpy
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from synthetic_banking.profiling import (
    CATEGORICAL_PAIRS,
    categorical_statistics,
    load_categorical_evidence,
    profile_categorical_dependencies,
)


PAIR = (("PERSON", "EMP_TYPE_CD", "OCCUP_CAT_CD"),)


def cells(matrix):
    return [{"parent_value": f"parent-{i}", "child_value": f"child-{j}", "record_count": count}
            for i, row in enumerate(matrix) for j, count in enumerate(row) if count]


class CategoricalStatisticsTests(unittest.TestCase):
    def test_independence_and_perfect_association_include_zero_cells(self):
        independent, _ = categorical_statistics(cells([[25, 25], [25, 25]]), 100)
        self.assertAlmostEqual(independent["cramers_v"], 0)
        perfect, cross_tab = categorical_statistics(cells([[100, 0], [0, 100]]), 220)
        self.assertAlmostEqual(perfect["cramers_v"], 1)
        self.assertEqual(perfect["chi_square"], 200)
        self.assertEqual((perfect["sample_size"], perfect["excluded_null_count"]), (200, 20))
        self.assertAlmostEqual(perfect["complete_case_fraction"], 200 / 220)
        self.assertEqual(perfect["degrees_of_freedom"], 1)
        self.assertEqual(len(cross_tab), 4)
        self.assertEqual(sum(cell["record_count"] == 0 for cell in cross_tab), 2)
        totals = defaultdict(float)
        for cell in cross_tab:
            totals[cell["parent_value"]] += cell["conditional_proportion"]
        self.assertEqual(dict(totals), {"parent-0": 1, "parent-1": 1})

    def test_matches_scipy_documented_four_by_two_example(self):
        # Official scipy.stats.contingency.association example, without continuity correction.
        observed = cells([[100, 150], [203, 322], [420, 700], [320, 210]])
        result, _ = categorical_statistics(observed, 2425)
        self.assertAlmostEqual(result["cramers_v"], .18617813077483678, places=12)

    def test_sparse_constant_empty_and_bounded_profiles_are_explicit(self):
        sparse, _ = categorical_statistics(cells([[1, 0], [0, 1]]), 2)
        self.assertEqual(sparse["sample_size"], 2)
        self.assertEqual(sparse["min_expected_count"], .5)
        self.assertEqual(sparse["sparse_expected_cell_fraction"], 1)
        constant, _ = categorical_statistics(cells([[10, 20]]), 30)
        self.assertEqual(constant["profile_status"], "CONSTANT")
        self.assertIsNone(constant["cramers_v"])
        empty, _ = categorical_statistics([], 20)
        self.assertEqual((empty["profile_status"], empty["excluded_null_count"]), ("EMPTY", 20))
        bounded, cross_tab = categorical_statistics(cells([[10, 0, 5], [0, 10, 0]]), 25, max_cells=4)
        self.assertEqual(bounded["profile_status"], "SKIPPED")
        self.assertEqual(cross_tab, [])

    def test_rejects_invalid_counts_and_inconsistent_population(self):
        with self.assertRaisesRegex(ValueError, "exceed"):
            categorical_statistics(cells([[10, 20]]), 20)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            categorical_statistics(cells([[10]]) * 2, 20)
        with self.assertRaisesRegex(ValueError, "positive integer"):
            categorical_statistics([{"parent_value": "A", "child_value": "B", "record_count": -1}], 20)


class Row(dict):
    def asDict(self):
        return dict(self)


class CategoricalSpark:
    """Run the profiler's aggregate SQL locally and emulate its run-scoped Delta writes."""

    def __init__(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.queries = []
        self.catalog = SimpleNamespace(tableExists=self.table_exists)
        self.db.executescript("""
            CREATE TABLE active_profile_run (run_id, profile_type);
            INSERT INTO active_profile_run VALUES ('source-A', 'SOURCE');
            CREATE TABLE profile_runs (run_id, profile_type, status, completed_at);
            INSERT INTO profile_runs VALUES ('source-A', 'SOURCE', 'RUNNING', NULL);
            CREATE TABLE active_column_inventory (logical_table_name, column_name, column_role);
            INSERT INTO active_column_inventory VALUES
              ('PERSON', 'EMP_TYPE_CD', 'CATEGORICAL_CANDIDATE'),
              ('PERSON', 'OCCUP_CAT_CD', 'CATEGORICAL_CANDIDATE'),
              ('PERSON', 'OCCUP_DESC', 'CATEGORICAL_CANDIDATE'),
              ('PERSON', 'PARTY_ID', 'IDENTIFIER');
            CREATE TABLE column_quality (run_id, logical_table_name, column_name, row_count, non_null_count, distinct_count);
            INSERT INTO column_quality VALUES
              ('source-A', 'PERSON', 'EMP_TYPE_CD', 220, 210, 2),
              ('source-A', 'PERSON', 'OCCUP_CAT_CD', 220, 210, 2),
              ('source-A', 'PERSON', 'OCCUP_DESC', 220, 220, 2),
              ('source-A', 'PERSON', 'PARTY_ID', 220, 220, 220);
            CREATE TABLE person_data (EMP_TYPE_CD TEXT, OCCUP_CAT_CD TEXT, OCCUP_DESC TEXT);
        """)
        self.db.executemany("INSERT INTO person_data VALUES (?, ?, ?)",
                            [("FT", "PRO", "Engineer")] * 100 + [("PT", "SRV", "Clerk")] * 100
                            + [(None, "PRO", "Engineer")] * 10 + [("FT", None, "Engineer")] * 10)

    def table_exists(self, name):
        return self.db.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (name.split(".")[-1],)).fetchone() is not None

    def sql(self, query, args=None):
        self.queries.append((query, args))
        query = query.replace("workspace.synthetic_profile.", "").replace("USING DELTA", "")
        query = re.sub(r"\bSTRING\b", "TEXT", query)
        normalized = " ".join(query.split())
        replacement = re.fullmatch(r"INSERT INTO (\w+) REPLACE WHERE run_id = :run_id SELECT \* FROM (\w+)", normalized)
        if replacement:
            table, view = replacement.groups()
            with self.db:
                self.db.execute(f"DELETE FROM {table} WHERE run_id = :run_id", args)
                self.db.execute(f"INSERT INTO {table} SELECT * FROM {view}")
            return SimpleNamespace(collect=lambda: [])
        cursor = self.db.execute(query, args or {})
        rows = [Row(row) for row in cursor.fetchall()]
        return SimpleNamespace(collect=lambda: rows)

    def createDataFrame(self, rows, schema):
        fields = [field.strip().split()[0] for field in schema.split(",")]
        schema = re.sub(r"\bSTRING\b", "TEXT", schema)
        def register(name):
            self.db.execute(f"DROP TABLE IF EXISTS {name}")
            self.db.execute(f"CREATE TEMP TABLE {name} ({schema})")
            self.db.executemany(f"INSERT INTO {name} VALUES ({','.join('?' for _ in fields)})",
                                [tuple(row.get(field) for field in fields) if isinstance(row, dict) else tuple(row)
                                 for row in rows])
        return SimpleNamespace(createOrReplaceTempView=register)


class CategoricalPipelineTests(unittest.TestCase):
    def setUp(self):
        self.spark = CategoricalSpark()
        self.addCleanup(self.spark.db.close)
        output = redirect_stdout(StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def test_curated_candidates_null_denominators_and_idempotent_run_writes(self):
        summaries = profile_categorical_dependencies(self.spark, {"PERSON": "person_data"})
        self.assertEqual(len(summaries), len(CATEGORICAL_PAIRS))
        measured = [row for row in summaries if row["profile_status"] == "PROFILED"]
        self.assertEqual(len(measured), 2)
        self.assertEqual(measured[0]["sample_size"], 200)
        self.assertEqual(measured[0]["excluded_null_count"], 20)
        again = profile_categorical_dependencies(self.spark, {"PERSON": "person_data"})
        self.assertEqual(summaries, again)
        self.assertEqual(self.spark.db.execute("SELECT COUNT(*) FROM categorical_relationship_profile").fetchone()[0], len(CATEGORICAL_PAIRS))
        self.assertEqual(self.spark.db.execute("SELECT COUNT(*) FROM categorical_conditional_profile").fetchone()[0], 8)
        aggregate_queries = [query for query, _ in self.spark.queries if "FROM `person_data`" in query]
        self.assertTrue(all("COUNT(*)" in query and "LIMIT 201" in query for query in aggregate_queries))

    def test_identifier_high_cardinality_and_pair_count_limits(self):
        result = profile_categorical_dependencies(self.spark, {"PERSON": "person_data"}, (("PERSON", "PARTY_ID", "OCCUP_CAT_CD"),))
        self.assertEqual(result[0]["skip_reason"], "missing_or_non_categorical_column")
        self.spark.db.execute("UPDATE column_quality SET distinct_count = 1000 WHERE column_name = 'EMP_TYPE_CD'")
        result = profile_categorical_dependencies(self.spark, {"PERSON": "person_data"}, PAIR)
        self.assertEqual(result[0]["skip_reason"], "estimated_cardinality_limit")
        self.assertFalse(any("FROM `person_data`" in query for query, _ in self.spark.queries))
        with self.assertRaisesRegex(ValueError, "limits"):
            profile_categorical_dependencies(self.spark, {}, PAIR * 13)

    def test_exact_cardinality_and_cell_caps_reject_underestimated_distinct_counts(self):
        self.spark.db.execute("DELETE FROM person_data")
        self.spark.db.executemany("INSERT INTO person_data VALUES (?, ?, NULL)",
                                 [(f"parent-{i}", "child") for i in range(21)])
        self.spark.db.execute("UPDATE column_quality SET row_count = 21, distinct_count = 20")
        result = profile_categorical_dependencies(self.spark, {"PERSON": "person_data"}, PAIR)
        self.assertEqual(result[0]["skip_reason"], "exact_cardinality_limit")
        self.assertEqual(result[0]["parent_cardinality"], 21)
        self.spark.db.execute("DELETE FROM person_data")
        self.spark.db.executemany("INSERT INTO person_data VALUES (?, ?, NULL)",
                                 [(f"parent-{i}", f"child-{j}") for i in range(3) for j in range(3)])
        self.spark.db.execute("UPDATE column_quality SET row_count = 9, distinct_count = 3")
        result = profile_categorical_dependencies(self.spark, {"PERSON": "person_data"}, PAIR, max_cells=4)
        self.assertEqual(result[0]["skip_reason"], "observed_cell_limit")
        self.assertEqual(self.spark.db.execute("SELECT COUNT(*) FROM categorical_conditional_profile").fetchone()[0], 0)

    def test_source_history_survives_generated_profiling_and_llm_selects_source_only(self):
        profile_categorical_dependencies(self.spark, {"PERSON": "person_data"}, PAIR)
        self.spark.db.execute("UPDATE profile_runs SET status = 'COMPLETED', completed_at = '2026-01-01'")
        with self.assertRaisesRegex(ValueError, "before completing"):
            profile_categorical_dependencies(self.spark, {"PERSON": "person_data"}, PAIR)
        self.spark.db.executescript("""
            UPDATE active_profile_run SET run_id = 'generated-B', profile_type = 'GENERATED';
            INSERT INTO profile_runs VALUES ('generated-B', 'GENERATED', 'RUNNING', NULL);
            INSERT INTO column_quality SELECT 'generated-B', logical_table_name, column_name, 200, 200, 2 FROM column_quality;
            CREATE TABLE generated_data (EMP_TYPE_CD TEXT, OCCUP_CAT_CD TEXT);
        """)
        self.spark.db.executemany("INSERT INTO generated_data VALUES (?, ?)",
                                 [(p, c) for p in ("gen-parent-A", "gen-parent-B") for c in ("gen-child-A", "gen-child-B")] * 50)
        generated = profile_categorical_dependencies(self.spark, {"PERSON": "generated_data"}, PAIR)
        self.assertEqual(generated[0]["profile_type"], "GENERATED")
        self.assertAlmostEqual(generated[0]["cramers_v"], 0)
        self.spark.db.execute("UPDATE profile_runs SET status = 'COMPLETED', completed_at = '2026-01-02' WHERE run_id = 'generated-B'")
        evidence = load_categorical_evidence(self.spark, "source-A")
        self.assertEqual(len(evidence), 1)
        self.assertAlmostEqual(evidence[0]["cramers_v"], 1)
        self.assertNotIn("gen-parent", json.dumps(evidence))
        self.assertEqual(load_categorical_evidence(self.spark, "generated-B"), [])
        self.assertEqual(self.spark.db.execute("SELECT COUNT(*) FROM categorical_relationship_profile WHERE run_id='source-A'").fetchone()[0], 1)

    def test_llm_context_is_bounded_complete_and_aggregate_only(self):
        profile_categorical_dependencies(self.spark, {"PERSON": "person_data"})
        self.assertEqual(load_categorical_evidence(self.spark, "source-A"), [])
        self.spark.db.execute("UPDATE profile_runs SET status = 'COMPLETED', completed_at = '2026-01-01'")
        self.spark.db.set_authorizer(lambda action, table, *_: sqlite3.SQLITE_DENY
                                     if action == sqlite3.SQLITE_READ and table == "person_data" else sqlite3.SQLITE_OK)
        evidence = load_categorical_evidence(self.spark, "source-A", max_pairs=1)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(sum(cell["record_count"] for cell in evidence[0]["cells"]), evidence[0]["sample_size"])
        self.assertEqual(load_categorical_evidence(self.spark, "source-A", min_sample_size=221), [])
        with self.assertRaises(ValueError):
            load_categorical_evidence(self.spark, "source-A", max_pairs=100)
        self.spark.db.execute("DELETE FROM categorical_conditional_profile WHERE rowid = (SELECT MIN(rowid) FROM categorical_conditional_profile)")
        with self.assertRaisesRegex(ValueError, "incomplete"):
            load_categorical_evidence(self.spark, "source-A")

    def test_actual_prompt_cell_includes_measured_categorical_evidence_from_same_run(self):
        profile_categorical_dependencies(self.spark, {"PERSON": "person_data"}, PAIR)
        self.spark.db.execute("UPDATE profile_runs SET status='COMPLETED', completed_at='2026-01-01'")
        request = {"source_run_id": "source-A", "batch_id": "batch-A", "scope_name": "ACCOUNT_CORE", "profile_summary": "fabricated aggregate column context"}
        self.spark.table = lambda name: SimpleNamespace(first=lambda: request)
        self.spark.db.execute("CREATE TABLE conditional_profile (run_id, entity_name, condition_variable, outcome_variable, condition_bucket, record_count, outcome_rate)")
        notebook = json.loads((Path(__file__).resolve().parents[1] / "notebooks/02_LLM Rule Generation.ipynb").read_text(encoding="utf-8"))
        source = "".join(notebook["cells"][8]["source"])
        with TemporaryDirectory() as folder:
            path = Path(folder) / "prompt_cell.py"
            path.write_text(source, encoding="utf-8")
            runpy.run_path(str(path), init_globals={"spark": self.spark})
        row = self.spark.db.execute("SELECT source_run_id, batch_id, prompt FROM ai_model_request").fetchone()
        self.assertEqual((row["source_run_id"], row["batch_id"]), ("source-A", "batch-A"))
        self.assertIn('"cramers_v": 1.0', row["prompt"])
        self.assertIn('"sample_size": 200', row["prompt"])
        self.assertIn('"conditional_proportion": 1.0', row["prompt"])
        self.assertIn("Do not infer dependencies from field names alone", row["prompt"])


if __name__ == "__main__":
    unittest.main()
