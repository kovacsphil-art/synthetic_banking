from contextlib import redirect_stdout
from io import StringIO
import json
import math
import re
import sqlite3
from types import SimpleNamespace
import unittest

import numpy as np

from synthetic_banking.customer_relationships import generate_customer_relationships
from synthetic_banking.dates import DateSampler
from synthetic_banking.relationship_profiles import profile_customer_relationships, load_customer_relationship_profile
from test_categorical_profiling import CategoricalSpark
from test_numeric_dependencies import Percentile


FIELDS = {
    "FROM_PARTY_ID": "STRING", "TO_PARTY_ID": "STRING", "FROM_TO_CUST_RELATN_CD": "STRING",
    "TO_FROM_CUST_RELATN_CD": "STRING", "ownership_percentage": "DOUBLE", "OWNED_BUS_SINCE_DT": "DATE",
    "LAST_UPDT_CHANNEL_CD": "STRING", "LAST_UPDT_TRANSIT_NUM": "STRING", "ORIGINATING_APP_CD": "STRING",
}


class RelationshipSpark(CategoricalSpark):
    def __init__(self, people, edges):
        super().__init__()
        self.db.create_function("CONCAT_WS", -1, lambda separator, *values: separator.join(str(x) for x in values if x is not None))
        self.db.create_function("regexp", 2, lambda pattern, value: value is not None and re.fullmatch(pattern, str(value)) is not None)
        self.db.create_function("ISNAN", 1, lambda value: value is not None and math.isnan(value))
        self.db.create_aggregate("PERCENTILE_APPROX", 3, Percentile)
        self.db.executescript("""
            DELETE FROM active_column_inventory;
            ALTER TABLE active_column_inventory ADD COLUMN data_type;
            ALTER TABLE column_quality ADD COLUMN data_type;
            ALTER TABLE column_quality ADD COLUMN null_count;
            CREATE TABLE person_input (PARTY_ID TEXT);
            CREATE TABLE relationship_input (FROM_PARTY_ID TEXT, TO_PARTY_ID TEXT,
                FROM_TO_CUST_RELATN_CD TEXT, TO_FROM_CUST_RELATN_CD TEXT, ownership_percentage REAL,
                OWNED_BUS_SINCE_DT TEXT, LAST_UPDT_CHANNEL_CD TEXT, LAST_UPDT_TRANSIT_NUM TEXT, ORIGINATING_APP_CD TEXT);
            CREATE TABLE cardinality_profile (run_id, relationship_name, cardinality, entity_count, proportion);
            INSERT INTO cardinality_profile VALUES ('source-A','ACCOUNTS_PER_PARTY',1,100,1);
            CREATE TABLE category_profile (run_id, logical_table_name, column_name, category_value, record_count, proportion);
            CREATE TABLE numeric_profile (run_id, logical_table_name, column_name, min_value, p01, p05, p25, p50, p75, p95, p99, max_value);
        """)
        self.inputs = {"PERSON": "person_input", "CUSTOMER_RELATIONSHIP": "relationship_input"}
        self.db.executemany("INSERT INTO person_input VALUES (?)", [(p,) for p in people])
        self.db.executemany("INSERT INTO relationship_input VALUES (?,?,?,?,?,?,?,?,?)", edges)
        for name, kind in FIELDS.items():
            role = "IDENTIFIER" if name.endswith("PARTY_ID") else "DATE" if kind == "DATE" else "NUMERIC" if kind == "DOUBLE" else "CATEGORICAL_CANDIDATE"
            self.db.execute("INSERT INTO active_column_inventory VALUES ('CUSTOMER_RELATIONSHIP',?,?,?)", (name, role, kind))
            count = self.db.execute(f'SELECT COUNT("{name}") FROM relationship_input').fetchone()[0]
            self.db.execute("INSERT INTO column_quality VALUES ('source-A','CUSTOMER_RELATIONSHIP',?,?,?,?,?,?)", (name, len(edges), count, count, kind, len(edges) - count))
            if kind == "STRING" and not name.endswith("PARTY_ID") and name != "LAST_UPDT_TRANSIT_NUM":
                for row in self.db.execute(f'SELECT "{name}" AS v, COUNT(*) AS n FROM relationship_input GROUP BY "{name}"'):
                    self.db.execute("INSERT INTO category_profile VALUES ('source-A','CUSTOMER_RELATIONSHIP',?,?,?,?)", (name, row["v"], row["n"], row["n"] / len(edges)))

    def sql(self, query, args=None):
        query = query.replace(" RLIKE ", " REGEXP ").replace("TRY_CAST(", "CAST(")
        compact = " ".join(query.split())
        if compact.startswith("INSERT INTO workspace.synthetic_profile.cardinality_profile REPLACE WHERE run_id = :run AND"):
            self.queries.append((query, args))
            self.db.execute("DELETE FROM cardinality_profile WHERE run_id = :run AND relationship_name LIKE 'CUSTOMER_RELATIONSHIP_%'", args)
            self.db.execute("INSERT INTO cardinality_profile SELECT * FROM customer_relationship_cardinalities_write")
            return SimpleNamespace(collect=lambda: [])
        return super().sql(query, args)

    def complete(self):
        self.db.execute("UPDATE profile_runs SET status='COMPLETED', completed_at='2026-01-01' WHERE run_id='source-A'")

    def date_sampler(self, seed=42):
        rows = self.db.execute("SELECT OWNED_BUS_SINCE_DT FROM relationship_input").fetchall()
        present = [row[0] for row in rows if row[0] is not None]
        dates = [{"run_id": "source-A", "logical_table_name": "CUSTOMER_RELATIONSHIP", "column_name": "OWNED_BUS_SINCE_DT",
                  "earliest_date": min(present) if present else None, "latest_date": max(present) if present else None,
                  "non_null_count": len(present)}]
        counts = {}
        for value in present:
            counts[value[:7]] = counts.get(value[:7], 0) + 1
        months = [{**dates[0], "profile_type": "SOURCE", "month_bucket": key, "record_count": count, "proportion": count / len(present)} for key, count in counts.items()]
        quality = [{**dates[0], "row_count": len(rows), "null_count": len(rows) - len(present)}]
        return DateSampler("source-A", seed, dates, months, quality)


def edge(a, b, first="SPOUSE", second="SPOUSE", owned=None, since=None):
    return (a, b, first, second, owned, since, "FAKE-BR", "00123", "FAKE-APP")


class CustomerRelationshipTests(unittest.TestCase):
    def setUp(self):
        output = redirect_stdout(StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def fixture(self, people, edges):
        spark = RelationshipSpark(people, edges)
        self.addCleanup(spark.db.close)
        return spark

    def prepare(self, spark):
        summary = profile_customer_relationships(spark, spark.inputs)
        spark.complete()
        return summary, load_customer_relationship_profile(spark, "source-A")

    def test_profile_has_zero_degree_parties_direction_codes_ownership_and_no_source_ids(self):
        spark = self.fixture(["SOURCE-A", "SOURCE-B", "SOURCE-C", "SOURCE-D"],
                             [edge("SOURCE-A", "SOURCE-B", "PARENT", "CHILD", 25, "2000-01-01")])
        summary, profile = self.prepare(spark)
        self.assertEqual((summary["person_count"], summary["valid_rows"], summary["directed_dyads"]), (4, 1, 1))
        degrees = profile["customer_relationship_degree_profile"]
        self.assertEqual(sum(row["party_count"] for row in degrees), 4)
        isolated = [r for r in degrees if r["outgoing_count"] == r["incoming_count"] == r["reciprocal_count"] == 0]
        self.assertEqual(sum(row["party_count"] for row in isolated), 2)
        self.assertEqual(profile["customer_relationship_ownership_profile"][0]["p50"], 25)
        self.assertIn("ACCOUNTS_PER_PARTY", [row[0] for row in spark.db.execute("SELECT relationship_name FROM cardinality_profile")])
        self.assertNotIn("SOURCE-A", json.dumps(profile, default=str))
        self.assertNotIn("SOURCE-B", json.dumps(profile, default=str))

    def test_simple_relationships_use_only_generated_ids_preserve_null_patterns_and_are_repeatable(self):
        spark = self.fixture([f"SOURCE-{i}" for i in range(6)], [
            edge("SOURCE-0", "SOURCE-1", "PARENT", "CHILD", 25, "2000-01-01"), edge("SOURCE-2", "SOURCE-3"),
        ])
        summary, profile = self.prepare(spark)
        ids = [f"P{i:08d}" for i in range(1, 61)]
        dates = spark.date_sampler()
        data, plan = generate_customer_relationships(ids, profile, 42, dates)
        self.assertEqual(plan["row_count"], 20)
        self.assertEqual(plan["removed_neighbor_stubs"], 0)
        self.assertEqual(plan["self_rows"], 0)
        self.assertTrue(set(data["FROM_PARTY_ID"]) | set(data["TO_PARTY_ID"]) <= set(ids))
        parents = data["FROM_TO_CUST_RELATN_CD"] == "PARENT"
        self.assertEqual(int(parents.sum()), 10)
        self.assertTrue(all(value == 25 for value in data["ownership_percentage"][parents]))
        self.assertTrue(all(value is None for value in data["ownership_percentage"][~parents]))
        self.assertTrue(np.isnat(data["OWNED_BUS_SINCE_DT"][~parents]).all())
        self.assertFalse(np.isnat(data["OWNED_BUS_SINCE_DT"][parents]).any())
        self.assertEqual(plan["null_counts"]["OWNED_BUS_SINCE_DT"], 10)
        self.assertTrue(all(re.fullmatch(r"\d{5}", value) for value in data["LAST_UPDT_TRANSIT_NUM"]))
        again, again_plan = generate_customer_relationships(ids, profile, 42, dates)
        self.assertEqual(plan, again_plan)
        for column in data:
            np.testing.assert_array_equal(data[column], again[column])

    def test_reciprocal_edges_keep_both_directional_type_pairs_consistent(self):
        spark = self.fixture(["SOURCE-A", "SOURCE-B"], [
            edge("SOURCE-A", "SOURCE-B", "PARENT", "CHILD"), edge("SOURCE-B", "SOURCE-A", "CHILD", "PARENT"),
        ])
        summary, profile = self.prepare(spark)
        self.assertEqual(summary["reciprocal_dyads"], 1)
        ids = [f"P{i:08d}" for i in range(1, 21)]
        data, plan = generate_customer_relationships(ids, profile, 42, spark.date_sampler())
        self.assertEqual((plan["reciprocal_dyads"], plan["row_count"]), (10, 20))
        rows = {(a, b): (c, d) for a, b, c, d in zip(data["FROM_PARTY_ID"], data["TO_PARTY_ID"], data["FROM_TO_CUST_RELATN_CD"], data["TO_FROM_CUST_RELATN_CD"])}
        for (a, b), (c, d) in rows.items():
            self.assertEqual(rows[b, a], (d, c))
            self.assertNotEqual(a, b)

    def test_self_relationships_are_generated_only_when_measured_and_parallel_rows_are_preserved(self):
        spark = self.fixture(["SOURCE-A", "SOURCE-B"], [edge("SOURCE-A", "SOURCE-A"), edge("SOURCE-A", "SOURCE-A")])
        summary, profile = self.prepare(spark)
        data, plan = generate_customer_relationships([f"P{i:08d}" for i in range(1, 21)], profile, 42, spark.date_sampler())
        self.assertTrue(plan["self_allowed"])
        self.assertEqual((plan["self_dyads"], plan["self_rows"], plan["row_count"]), (10, 20, 20))
        self.assertTrue(np.all(data["FROM_PARTY_ID"] == data["TO_PARTY_ID"]))
        self.assertEqual(summary["max_multiplicity"], 2)

    def test_invalid_source_endpoints_are_counted_excluded_and_never_recreated(self):
        spark = self.fixture(["SOURCE-A", "SOURCE-B"], [edge("SOURCE-A", "SOURCE-B"), edge(None, "SOURCE-B"), edge("ABSENT", "SOURCE-B")])
        summary, profile = self.prepare(spark)
        self.assertEqual((summary["raw_rows"], summary["valid_rows"], summary["invalid_endpoint_rows"]), (3, 1, 2))
        data, plan = generate_customer_relationships([f"P{i:08d}" for i in range(1, 21)], profile, 42, spark.date_sampler())
        self.assertEqual(plan["source_excluded_endpoint_rows"], 2)
        self.assertEqual(plan["row_count"], 10)
        self.assertTrue(all(value not in (None, "ABSENT", "SOURCE-A", "SOURCE-B") for value in data["FROM_PARTY_ID"]))

    def test_empty_source_relationships_produce_a_valid_empty_table(self):
        spark = self.fixture(["SOURCE-A", "SOURCE-B"], [])
        summary, profile = self.prepare(spark)
        data, plan = generate_customer_relationships(["P00000001", "P00000002"], profile, 42, spark.date_sampler())
        self.assertEqual(plan["row_count"], 0)
        self.assertEqual(set(data), set(FIELDS))
        self.assertTrue(all(len(values) == 0 for values in data.values()))

    def test_profile_history_source_selection_and_idempotence(self):
        spark = self.fixture(["SOURCE-A", "SOURCE-B"], [edge("SOURCE-A", "SOURCE-B")])
        first = profile_customer_relationships(spark, spark.inputs)
        profile_customer_relationships(spark, spark.inputs)
        self.assertEqual(spark.db.execute("SELECT COUNT(*) FROM customer_relationship_summary").fetchone()[0], 1)
        with self.assertRaisesRegex(ValueError, "Notebook 01 SOURCE"):
            load_customer_relationship_profile(spark, "source-A")
        spark.complete()
        source = load_customer_relationship_profile(spark, "source-A")
        spark.db.executescript("""
            UPDATE active_profile_run SET run_id='generated-B', profile_type='GENERATED';
            INSERT INTO profile_runs VALUES ('generated-B','GENERATED','RUNNING',NULL);
        """)
        generated = profile_customer_relationships(spark, spark.inputs)
        self.assertEqual(generated["profile_type"], "GENERATED")
        self.assertEqual(spark.db.execute("SELECT COUNT(*) FROM customer_relationship_summary").fetchone()[0], 2)
        self.assertEqual(load_customer_relationship_profile(spark, "source-A")["profile_signature"], source["profile_signature"])
        with self.assertRaisesRegex(ValueError, "Notebook 01 SOURCE"):
            load_customer_relationship_profile(spark, "generated-B")

    def test_unsupported_profiles_percentages_and_non_synthetic_input_pool_fail_clearly(self):
        spark = self.fixture(["SOURCE-A", "SOURCE-B"], [edge("SOURCE-A", "SOURCE-B", "OWNER", "BUSINESS", 120)])
        summary, profile = self.prepare(spark)
        dates = spark.date_sampler()
        with self.assertRaisesRegex(ValueError, "outside"):
            generate_customer_relationships(["P00000001", "P00000002"], profile, 42, dates)
        with self.assertRaisesRegex(ValueError, "unique non-null"):
            generate_customer_relationships(["P1", "P1"], profile, 42, dates)
        with self.assertRaisesRegex(ValueError, "same SOURCE"):
            generate_customer_relationships(["P1", "P2"], profile, 43, dates)
        with self.assertRaisesRegex(ValueError, "row budget"):
            generate_customer_relationships(["P1", "P2"], profile, 42, dates, max_rows=0)

    def test_directed_configuration_repairs_collisions_without_changing_degrees(self):
        people = [f"SOURCE-{i}" for i in range(20)]
        rows = [edge(people[i], people[(i + offset) % 20]) for i in range(20) for offset in (1, 2)]
        spark = self.fixture(people, rows)
        summary, profile = self.prepare(spark)
        ids = [f"P{i:08d}" for i in range(1, 201)]
        data, plan = generate_customer_relationships(ids, profile, 42, spark.date_sampler())
        self.assertEqual((plan["row_count"], plan["removed_neighbor_stubs"]), (400, 0))
        from collections import Counter
        self.assertEqual(set(Counter(data["FROM_PARTY_ID"]).values()), {2})
        self.assertEqual(set(Counter(data["TO_PARTY_ID"]).values()), {2})
        pairs = set(zip(data["FROM_PARTY_ID"], data["TO_PARTY_ID"]))
        self.assertEqual(len(pairs), 400)
        self.assertFalse(any(a == b or (b, a) in pairs for a, b in pairs))

    def test_all_invalid_source_links_require_repair_and_missing_schema_is_explicit(self):
        spark = self.fixture(["SOURCE-A"], [edge("ABSENT", "SOURCE-A")])
        profile_customer_relationships(spark, spark.inputs)
        spark.complete()
        with self.assertRaisesRegex(ValueError, "repair SOURCE"):
            load_customer_relationship_profile(spark, "source-A")

    def test_generated_relationships_can_be_reprofiled_without_losing_source_evidence(self):
        spark = self.fixture(["SOURCE-A", "SOURCE-B"], [edge("SOURCE-A", "SOURCE-B")])
        summary, profile = self.prepare(spark)
        ids = [f"P{i:08d}" for i in range(1, 21)]
        data, plan = generate_customer_relationships(ids, profile, 42, spark.date_sampler())
        spark.db.execute("DELETE FROM person_input")
        spark.db.executemany("INSERT INTO person_input VALUES (?)", [(value,) for value in ids])
        spark.db.execute("DELETE FROM relationship_input")
        def primitive(value):
            if isinstance(value, np.datetime64):
                return None if np.isnat(value) else str(value)
            return value.item() if isinstance(value, np.generic) else value
        spark.db.executemany("INSERT INTO relationship_input VALUES (?,?,?,?,?,?,?,?,?)",
                             [tuple(primitive(data[column][i]) for column in FIELDS) for i in range(plan["row_count"])])
        spark.db.executescript("""
            UPDATE active_profile_run SET run_id='generated-B', profile_type='GENERATED';
            INSERT INTO profile_runs VALUES ('generated-B','GENERATED','RUNNING',NULL);
        """)
        generated = profile_customer_relationships(spark, spark.inputs)
        self.assertEqual((generated["valid_rows"], generated["invalid_endpoint_rows"], generated["person_count"]), (10, 0, 20))
        self.assertEqual(load_customer_relationship_profile(spark, "source-A")["profile_signature"], profile["profile_signature"])
        for run, expected in (("source-A", 2), ("generated-B", 20)):
            count = spark.db.execute("SELECT SUM(entity_count) FROM cardinality_profile WHERE run_id=? AND relationship_name='CUSTOMER_RELATIONSHIP_OUTGOING'", (run,)).fetchone()[0]
            self.assertEqual(count, expected)

    def test_partial_degree_evidence_is_not_treated_as_a_complete_source_profile(self):
        spark = self.fixture(["SOURCE-A", "SOURCE-B", "SOURCE-C"], [edge("SOURCE-A", "SOURCE-B")])
        summary, profile = self.prepare(spark)
        spark.db.execute("DELETE FROM customer_relationship_degree_profile WHERE outgoing_count=1")
        with self.assertRaisesRegex(ValueError, "degree profile"):
            load_customer_relationship_profile(spark, "source-A")


if __name__ == "__main__":
    unittest.main()
