"""Refactor regressions use fabricated aggregates and lightweight Spark adapters."""

from contextlib import redirect_stdout
import ast
from hashlib import sha256
import inspect
from io import StringIO
import json
from pathlib import Path
import sqlite3
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

from synthetic_banking.config import GenerationSettings, SOURCE_ALIASES
from synthetic_banking.profiles import select_source_run, validate_pilot_selection
from synthetic_banking.profiling_run import load_source_inputs, completed_generation, complete_profile_run, ProfilingInputs
from synthetic_banking.profiling_sql import QUERIES, FEATURE_QUERIES
from synthetic_banking.proposals import start_proposal_batch, build_model_request, call_proposal_model, store_proposals

try:
    import pandas as pd
except ImportError:
    pd = None

FIXTURES = Path(__file__).parent / "fixtures"


class RunSpark:
    def __init__(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE profile_runs(run_id, profile_type, status, started_at, completed_at);
            INSERT INTO profile_runs VALUES
              ('source-old','SOURCE','COMPLETED','2026-01-01','2026-01-02'),
              ('source-new','SOURCE','COMPLETED','2026-02-01','2026-02-02'),
              ('generated-newest','GENERATED','COMPLETED','2026-05-01','2026-05-02'),
              ('source-running','SOURCE','RUNNING','2026-06-01',NULL),
              ('source-no-completion','SOURCE','COMPLETED','2026-07-01',NULL);
        """)
        self.queries = []

    def sql(self, query, args=None):
        self.queries.append((query, args))
        row = self.db.execute(query.replace("workspace.synthetic_profile.", ""), args or {}).fetchone()
        return SimpleNamespace(first=lambda: row)


class SourceSelectionTests(unittest.TestCase):
    def setUp(self):
        self.spark = RunSpark()
        self.addCleanup(self.spark.db.close)

    def test_latest_completed_source_ignores_generated_and_incomplete(self):
        self.assertEqual(select_source_run(self.spark), "source-new")
        self.assertTrue(all("current_run" not in query for query, _ in self.spark.queries))
        self.spark.db.execute("INSERT INTO profile_runs VALUES ('source-tie', 'SOURCE', 'COMPLETED', '2026-02-01', '2026-02-02')")
        self.assertEqual(select_source_run(self.spark), "source-tie")

    def test_explicit_source_is_pinned_and_generated_is_rejected(self):
        self.assertEqual(select_source_run(self.spark, "source-old"), "source-old")
        for invalid in ("generated-newest", "source-running", "source-no-completion", "missing"):
            with self.subTest(run=invalid), self.assertRaisesRegex(ValueError, "completed SOURCE"):
                select_source_run(self.spark, invalid)
        self.spark.db.execute("DELETE FROM profile_runs WHERE profile_type = 'SOURCE'")
        with self.assertRaisesRegex(RuntimeError, "No completed SOURCE"):
            select_source_run(self.spark)

    def test_pilot_requires_explicit_source_batch_and_distinct_ids(self):
        validate_pilot_selection("", "", ())
        validate_pilot_selection("source-old", "batch", ("a", "b"))
        for values in (("", "batch", ("a",)), ("source-old", "", ("a",)),
                       ("source-old", "batch", ()), ("source-old", "batch", ("a", "a")),
                       ("source-old", "batch", ("a", "b", "c", "d"))):
            with self.subTest(values=values), self.assertRaises(ValueError):
                validate_pilot_selection(*values)

    def test_proposal_batch_uses_same_source_selector_and_preserves_scope(self):
        self.spark.createDataFrame = Mock(return_value=SimpleNamespace(createOrReplaceTempView=Mock()))
        source, batch, scope = start_proposal_batch(self.spark, "source-old", balance_pilot=True)
        self.assertEqual((source, scope), ("source-old", "BALANCE_PILOT"))
        self.assertTrue(batch)
        self.assertEqual(self.spark.createDataFrame.call_args.args[0], [(source, batch, scope)])
        with self.assertRaisesRegex(ValueError, "only one"):
            start_proposal_batch(self.spark, "source-old", balance_pilot=True, delinquency_pilot=True)
        with self.assertRaisesRegex(ValueError, "source_run_id"):
            start_proposal_batch(self.spark, delinquency_pilot=True)


class LifecycleTests(unittest.TestCase):
    def test_preflight_checks_every_file_before_any_write(self):
        spark = Mock()
        dbutils = SimpleNamespace(fs=SimpleNamespace(ls=lambda _: []))
        with self.assertRaisesRegex(FileNotFoundError, "RCAR_synthetic_PERSON.parquet"):
            load_source_inputs(spark, dbutils, "SOURCE", "/fabricated/inputs")
        spark.read.parquet.assert_not_called()
        dbutils.fs.ls = Mock(side_effect=PermissionError("fabricated"))
        with self.assertRaisesRegex(RuntimeError, "volume read access"):
            load_source_inputs(spark, dbutils, "SOURCE", "/fabricated/inputs")
        load_source_inputs(spark, dbutils, "GENERATED")
        self.assertEqual(dbutils.fs.ls.call_count, 1)
        with self.assertRaises(ValueError):
            load_source_inputs(spark, dbutils, "SELECT")

    def test_source_loading_preserves_all_six_staging_destinations(self):
        spark = Mock()
        writer = spark.read.parquet.return_value.write
        writer.format.return_value = writer
        writer.mode.return_value = writer
        writer.option.return_value = writer
        dbutils = SimpleNamespace(fs=SimpleNamespace(ls=lambda _: [
            SimpleNamespace(name=f"RCAR_synthetic_{table}.parquet") for table in SOURCE_ALIASES
        ]))
        load_source_inputs(spark, dbutils, "SOURCE", "/fabricated/inputs/")
        self.assertEqual([c.args[0] for c in spark.read.parquet.call_args_list],
                         [f"/fabricated/inputs/RCAR_synthetic_{table}.parquet" for table in SOURCE_ALIASES])
        self.assertEqual([c.args[0] for c in writer.saveAsTable.call_args_list],
                         [f"workspace.default.{table}" for table in SOURCE_ALIASES])

    def test_generated_version_gate_and_end_of_profile_identity_gate_survive_extraction(self):
        state = {"status": "COMPLETED", "generation_id": "g", "source_run_id": "source-old", "validated_versions": {"fake": "1"}}
        spark = SimpleNamespace(catalog=SimpleNamespace(tableExists=lambda _: True))
        class Row(dict):
            def asDict(self): return dict(self)
        spark.table = lambda _: SimpleNamespace(take=lambda _: [Row(state)])
        with patch("synthetic_banking.validation.check_validated_versions") as check:
            self.assertEqual(completed_generation(spark)["generation_id"], "g")
            check.assert_called_once_with(spark, state["validated_versions"])
        inputs = ProfilingInputs("GENERATED", "expected-g", "source-old", {})
        with patch("synthetic_banking.profiling_run.completed_generation", return_value={"generation_id": "changed"}), self.assertRaisesRegex(RuntimeError, "changed during profiling"):
            complete_profile_run(spark, inputs, "generated-profile")

    def test_sql_and_feature_definitions_match_pre_refactor_snapshot(self):
        reference = json.loads((FIXTURES / "refactor_sql_reference.json").read_text())
        self.assertEqual({k: [sha256(v.encode()).hexdigest() for v in values] for k, values in QUERIES.items()}, reference["profiling_queries"])
        self.assertEqual({k: sha256(v.encode()).hexdigest() for k, v in FEATURE_QUERIES.items()}, reference["features"])

    def test_extracted_marginal_aggregations_match_original_ast(self):
        from synthetic_banking import marginal_profiles
        reference = json.loads((FIXTURES / "refactor_sql_reference.json").read_text())
        class OriginalNames(ast.NodeTransformer):
            def visit_Call(self, node):
                node = self.generic_visit(node)
                if isinstance(node.func, ast.Name) and node.func.id == "configured_sql":
                    return node.args[0]
                return node

            def visit_JoinedStr(self, node):
                node = self.generic_visit(node)
                values = []
                for value in node.values:
                    if isinstance(value, ast.FormattedValue) and isinstance(value.value, ast.Name) and value.value.id == "CATALOG":
                        value = ast.Constant(value="workspace")
                    if values and isinstance(values[-1], ast.Constant) and isinstance(value, ast.Constant):
                        values[-1].value += value.value
                    else:
                        values.append(value)
                node.values = values
                return node
        for name, expected in reference["marginals"].items():
            with self.subTest(function=name):
                body = ast.parse(inspect.getsource(getattr(marginal_profiles, name))).body[0].body
                body = [node for node in body if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                        and isinstance(node.value.func, ast.Name) and node.value.func.id == "run_profile_sql")]
                normalized = OriginalNames().visit(ast.Module(body=body, type_ignores=[]))
                self.assertEqual(sha256(ast.dump(normalized).encode()).hexdigest(), expected)


class ProposalExtractionTests(unittest.TestCase):
    def test_all_prompt_variants_match_original_prompt_bytes(self):
        reference = json.loads((FIXTURES / "refactor_sql_reference.json").read_text())
        for scope, expected in reference["prompts"].items():
            with self.subTest(scope=scope):
                request = dict(source_run_id="source-A", batch_id="batch-A", scope_name=scope,
                               profile_summary="fabricated aggregate column summary")
                rows = []
                def create(values, schema):
                    rows.extend(values)
                    return SimpleNamespace(createOrReplaceTempView=lambda _: None)
                spark = SimpleNamespace(table=lambda _: SimpleNamespace(first=lambda: request),
                                        sql=lambda query, args: SimpleNamespace(collect=lambda: [SimpleNamespace(asDict=lambda: dict(
                                            condition_bucket="0-30%", record_count=100, outcome_rate=.2))]),
                                        createDataFrame=create)
                with patch("synthetic_banking.profiling.load_categorical_evidence", return_value=[]), patch(
                        "synthetic_banking.numeric_dependencies.load_numeric_evidence", return_value=[]), redirect_stdout(StringIO()):
                    self.assertEqual(build_model_request(spark), request)
                self.assertEqual(rows[0][:3], ("source-A", "batch-A", scope))
                self.assertEqual(sha256(rows[0][3].encode()).hexdigest(), expected)

    def test_stored_response_is_reused_and_new_proposals_are_pending(self):
        functions = SimpleNamespace(col=lambda name: name)
        sql_module = ModuleType("pyspark.sql")
        sql_module.functions = functions
        frame = Mock()
        frame.filter.return_value.first.return_value = {"batch_id": "batch-A"}
        spark = SimpleNamespace(table=lambda _: frame, sql=Mock())
        with patch.dict(sys.modules, {"pyspark": ModuleType("pyspark"), "pyspark.sql": sql_module}), redirect_stdout(StringIO()):
            call_proposal_model(spark, {"batch_id": "batch-A"})
            spark.sql.assert_not_called()
            frame.filter.return_value.first.return_value = None
            call_proposal_model(spark, {"batch_id": "batch-A"})
        query, = spark.sql.call_args.args
        self.assertIn("FROM ai_model_request", query)
        self.assertIn(":model_endpoint", query)
        self.assertEqual(spark.sql.call_args.kwargs["args"], {"model_endpoint": "system.ai.gpt-oss-20b"})
        spark.sql.reset_mock()
        frame.selectExpr.return_value.first.return_value = {"rules": []}
        store_proposals(spark)
        parse_query = spark.sql.call_args_list[0].args[0]
        insert_query = spark.sql.call_args_list[1].args[0]
        self.assertIn("b.batch_id = r.batch_id AND b.source_run_id = r.source_run_id", parse_query)
        self.assertIn("'PENDING'", insert_query)
        self.assertIn("LEFT ANTI JOIN", insert_query)
        spark.sql.reset_mock()
        frame.selectExpr.return_value.first.return_value = {"rules": None}
        with self.assertRaisesRegex(RuntimeError, "valid rules array"):
            store_proposals(spark)
        self.assertEqual(spark.sql.call_count, 1)


@unittest.skipIf(pd is None, "Generator integration requires pandas, included in Databricks.")
class ExtractedGenerationTests(unittest.TestCase):
    def test_storage_publishes_completed_only_after_validation(self):
        from synthetic_banking.storage import save_generation
        from synthetic_banking.validation import GeneratedValidationError
        functions = SimpleNamespace(col=lambda value: value, current_timestamp=lambda: "now")
        sql_module = ModuleType("pyspark.sql")
        sql_module.functions = functions

        for succeeds in (True, False):
            with self.subTest(validation_succeeds=succeeds):
                writes = []
                class Frame:
                    def __init__(self, rows): self.rows = rows
                    @property
                    def write(self): return self
                    def withColumn(self, *args): return self
                    def select(self, *args): return self
                    def format(self, *args): return self
                    def mode(self, *args): return self
                    def option(self, *args): return self
                    def saveAsTable(self, name): writes.append((name, self.rows))
                spark = SimpleNamespace(sql=lambda query: None,
                                        table=lambda _: SimpleNamespace(collect=lambda: []),
                                        createDataFrame=lambda rows, *args: Frame(rows))
                result = SimpleNamespace(
                    source_run_id="source-A", settings=GenerationSettings(1, 42), expected_schema={}, rule_events=(),
                    relationship_plan={"implementation_version": "customer_relationships_v1"}, date_null_counts={},
                    expected_counts={"PERSON": 1, "TKQ_ACCOUNT": 1, "TRADELINES": 1},
                    tables={table: pd.DataFrame({"TEST": ["fabricated"]}) for table in SOURCE_ALIASES},
                )
                versions = {table: "1" for table in SOURCE_ALIASES}
                with patch.dict(sys.modules, {"pyspark": ModuleType("pyspark"), "pyspark.sql": sql_module}), patch(
                        "synthetic_banking.storage.validate_generated_batch", return_value=versions,
                        side_effect=None if succeeds else GeneratedValidationError("fabricated validation failure")) as validate, redirect_stdout(StringIO()):
                    if succeeds:
                        generation_id = save_generation(spark, result)
                    else:
                        with self.assertRaisesRegex(GeneratedValidationError, "validation failure"):
                            save_generation(spark, result)
                states = [rows[0] for table, rows in writes if table.endswith(".generation_state")]
                self.assertEqual([state[2] for state in states], ["RUNNING", "COMPLETED"] if succeeds else ["RUNNING"])
                self.assertEqual(states[0][1], "source-A")
                self.assertEqual(validate.call_args.args[4], "source-A")
                self.assertTrue(set(SOURCE_ALIASES).issubset({table.rsplit(".", 1)[1] for table, _ in writes}))
                self.assertTrue(any(table.endswith(".rule_execution_log") for table, _ in writes))
                self.assertTrue(any(table.endswith(".customer_relationship_generation_log") for table, _ in writes))
                if succeeds:
                    self.assertEqual(states[0][0], generation_id)
                    self.assertEqual(states[-1][0], generation_id)
                    self.assertEqual(states[-1][3], versions)

    def test_profile_loader_filters_every_profile_to_the_selected_source(self):
        from synthetic_banking.profiles import load_generation_profiles
        spark = RunSpark()
        self.addCleanup(spark.db.close)
        reads = []
        class Column:
            def __init__(self, name): self.name = name
            def __eq__(self, value): return (self.name, value)
            def alias(self, _): return self
        class Frame:
            def __init__(self, name):
                self.name = name
                self.where = None
            def filter(self, expr):
                self.where = expr
                return self
            def join(self, other, **kwargs):
                self.assert_same_run(other)
                return self
            def assert_same_run(self, other):
                if self.where != other.where: raise AssertionError("Mixed profile runs")
            def select(self, *args): return self
            def toPandas(self): return pd.DataFrame()
        def table(name):
            frame = Frame(name)
            reads.append(frame)
            return frame
        spark.table = table
        sql_module = ModuleType("pyspark.sql")
        sql_module.functions = SimpleNamespace(col=Column)
        with patch.dict(sys.modules, {"pyspark": ModuleType("pyspark"), "pyspark.sql": sql_module}), patch(
                "synthetic_banking.profiles.load_customer_relationship_profile", return_value={}) as relationships, redirect_stdout(StringIO()):
            result = load_generation_profiles(spark, "source-old")
        self.assertEqual(result.source_run_id, "source-old")
        relationships.assert_called_once_with(spark, "source-old")
        self.assertEqual({frame.name.rsplit(".", 1)[1] for frame in reads}, {
            "column_quality", "numeric_profile", "category_profile", "date_profile",
            "relationship_profile", "cardinality_profile", "conditional_profile",
        })
        self.assertTrue(all(frame.where == ("run_id", "source-old") for frame in reads))

    def generate(self, n, seed, proposals=()):
        from generation_fixtures import fabricated_profiles
        from synthetic_banking.generation import generate_dataset
        profiles, date_factory = fabricated_profiles()
        spark = SimpleNamespace(catalog=SimpleNamespace(tableExists=lambda _: False))
        with redirect_stdout(StringIO()), patch("synthetic_banking.generation.load_rule_proposals", return_value=proposals):
            return generate_dataset(spark, profiles, GenerationSettings(n, seed), date_sampler=date_factory(seed))

    def test_outputs_audits_and_rng_match_original_notebook_for_two_seeds(self):
        from generation_fixtures import fingerprint
        reference = json.loads((FIXTURES / "generation_reference.json").read_text())
        for case, expected in reference.items():
            with self.subTest(case=case):
                result = self.generate(*map(int, case.split(":")))
                actual = fingerprint(result.tables, result.rule_events, result.rng_state, result.relationship_plan)
                self.assertEqual(json.loads(json.dumps(actual)), expected)

    def test_controlled_registry_remains_wired_to_extracted_pipeline(self):
        from dataclasses import replace
        from generation_fixtures import fingerprint
        from synthetic_banking.rules import RuleProposal
        approved = RuleProposal("reviewed", "source-A", "TKQ_ACCOUNT_BALANCE", "AVAILABLE_TO_BUY_AMT", "DERIVED",
                                ("TKQ_ACCOUNT.CREDIT_LIMIT_AMT", "TKQ_ACCOUNT_BALANCE.CURRENT_BALANCE_AMT"),
                                "APPROVED", "batch-A", True)
        legacy = self.generate(8, 42)
        for proposal, expected, reason in ((approved, "APPLIED", None),
                                           (replace(approved, approval_status="REJECTED"), "SKIPPED", "not_approved"),
                                           (replace(approved, target_column="UNKNOWN"), "SKIPPED", "no_implementation")):
            with self.subTest(expected=expected):
                result = self.generate(8, 42, (proposal,))
                event = next(e for e in result.rule_events if e.proposal_id == "reviewed")
                self.assertEqual(event.outcome, expected)
                self.assertEqual(event.applied, expected == "APPLIED")
                self.assertEqual(event.reason, reason)
                # Known balance formula is the existing legacy formula; approval does not shift RNG.
                self.assertEqual(fingerprint(result.tables, (), result.rng_state, result.relationship_plan),
                                 fingerprint(legacy.tables, (), legacy.rng_state, legacy.relationship_plan))

    def test_marginal_sampler_edge_fallbacks_do_not_consume_rng(self):
        from generation_fixtures import fabricated_profiles
        from synthetic_banking.generators import ProfileGenerators
        profiles, _ = fabricated_profiles()
        rng = np.random.default_rng(7)
        samplers = ProfileGenerators(profiles, rng)
        before = json.dumps(rng.bit_generator.state)
        self.assertTrue(np.isnan(samplers.generate_numeric("MISSING", "MISSING", 5)).all())
        self.assertEqual(samplers.generate_categorical("MISSING", "MISSING", 3).tolist(), [None] * 3)
        self.assertEqual(samplers.generate_cardinality("MISSING", 3, fallback=2).tolist(), [2] * 3)
        self.assertEqual(before, json.dumps(rng.bit_generator.state))
        row = profiles.numeric_stats.index[0]
        fields = ["min_value", "p01", "p05", "p25", "p50", "p75", "p95", "p99", "max_value"]
        profiles.numeric_stats.loc[row, fields] = np.nan
        profiles.numeric_stats.loc[row, "p50"] = 123
        self.assertEqual(samplers.generate_numeric("PERSON", "INCOME_AMT", 4).tolist(), [123] * 4)
        self.assertEqual(before, json.dumps(rng.bit_generator.state))


if __name__ == "__main__":
    unittest.main()
