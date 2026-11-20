import json
import unittest

import numpy as np

from synthetic_banking.dates import DateGenerationError, DateSampler, load_date_sampler
from test_categorical_profiling import CategoricalSpark


def profiles(specifications):
    """Fabricated month-count inputs, not row-level banking data."""
    dates, months, quality = [], [], []
    for table, column, earliest, latest, bins, nulls in specifications:
        observed = sum(count for _, count in bins)
        common = {"run_id": "source-A", "logical_table_name": table, "column_name": column}
        dates.append({**common, "earliest_date": earliest, "latest_date": latest, "non_null_count": observed})
        quality.append({**common, "row_count": observed + nulls, "null_count": nulls})
        months.extend({**common, "profile_type": "SOURCE", "month_bucket": month, "record_count": count,
                       "non_null_count": observed, "proportion": count / observed} for month, count in bins)
    return dates, months, quality


def sampler(specifications, seed=42):
    return DateSampler("source-A", seed, *profiles(specifications))


def ordered(values, parent, child):
    if parent in values and child in values:
        valid = ~np.isnat(values[parent]) & ~np.isnat(values[child])
        return bool(np.all(values[parent][valid] <= values[child][valid]))
    return True


class DateSamplingTests(unittest.TestCase):
    def test_month_weights_null_counts_and_day_support_are_preserved(self):
        model = sampler([("PERSON", "TEST_DT", "2020-01-01", "2020-12-31", [("2020-01", 900), ("2020-12", 100)], 100)])
        values = model.generate_table("PERSON", 11000)["TEST_DT"]
        self.assertEqual(int(np.isnat(values).sum()), 1000)
        observed = values[~np.isnat(values)]
        january = observed.astype("datetime64[M]") == np.datetime64("2020-01", "M")
        self.assertAlmostEqual(float(january.mean()), .9, delta=.015)
        self.assertEqual(set(observed.astype("datetime64[M]").astype(str)), {"2020-01", "2020-12"})
        self.assertGreater(len(np.unique(observed)), 50)
        self.assertEqual(model.expected_null_counts["PERSON"]["TEST_DT"], 1000)
        self.assertEqual(model.diagnostics[0]["method"], "MONTHLY")

    def test_partial_month_and_leap_day_bounds(self):
        model = sampler([("PERSON", "TEST_DT", "2024-02-28", "2024-03-01", [("2024-02", 90), ("2024-03", 10)], 0)])
        values = model.generate_table("PERSON", 2000)["TEST_DT"]
        self.assertEqual(set(values.astype(str)), {"2024-02-28", "2024-02-29", "2024-03-01"})
        self.assertAlmostEqual(float((values == np.datetime64("2024-03-01")).mean()), .1, delta=.025)

    def test_ordering_preserves_both_null_masks_without_clamping(self):
        model = sampler([
            ("PERSON", "BIRTH_DT", "2010-01-01", "2014-01-31", [("2010-01", 40), ("2014-01", 40)], 20),
            ("PERSON", "SINCE_DT", "2005-01-01", "2020-01-31", [("2005-01", 30), ("2020-01", 30)], 40),
        ])
        values = model.generate_table("PERSON", 1000)
        self.assertTrue(ordered(values, "BIRTH_DT", "SINCE_DT"))
        self.assertEqual(int(np.isnat(values["BIRTH_DT"]).sum()), 200)
        self.assertEqual(int(np.isnat(values["SINCE_DT"]).sum()), 400)
        valid = ~np.isnat(values["BIRTH_DT"]) & ~np.isnat(values["SINCE_DT"])
        self.assertFalse(np.any(values["BIRTH_DT"][valid] == values["SINCE_DT"][valid]))

    def test_infeasible_non_null_dates_raise_instead_of_adding_nulls_or_changing_support(self):
        model = sampler([
            ("PERSON", "BIRTH_DT", "2030-01-01", "2030-01-31", [("2030-01", 100)], 0),
            ("PERSON", "SINCE_DT", "2000-01-01", "2000-01-31", [("2000-01", 100)], 0),
        ])
        with self.assertRaisesRegex(DateGenerationError, "no feasible SOURCE date"):
            model.generate_table("PERSON", 10)
        self.assertEqual(model.expected_null_counts, {})

    def test_account_ordering_uses_month_gaps_and_shares_snapshots_by_synthetic_id(self):
        model = sampler([
            ("TKQ_ACCOUNT", "OPEN_DT", "2020-06-01", "2020-06-30", [("2020-06", 100)], 0),
            ("TKQ_ACCOUNT", "CLOSE_DT", "2020-06-01", "2021-01-31", [("2020-06", 25), ("2021-01", 25)], 50),
            ("TKQ_ACCOUNT", "LAST_PAYMENT_DT", "2020-01-01", "2020-12-31", [("2020-01", 50), ("2020-12", 50)], 0),
            ("TKQ_ACCOUNT", "LAST_PURCHASE_DT", "2020-12-01", "2020-12-31", [("2020-12", 70)], 30),
            ("TKQ_ACCOUNT", "BUSINESSEFFECTIVEDATE", "2020-10-01", "2020-12-15", [("2020-10", 50), ("2020-12", 50)], 0),
            ("TKQ_ACCOUNT_BALANCE", "BUSINESSEFFECTIVEDATE", "2020-10-01", "2020-12-15", [("2020-10", 50), ("2020-12", 50)], 0),
        ])
        account_ids = [f"A{i:09d}" for i in range(1, 101)]
        balances = list(reversed(account_ids))
        a, b = model.generate_accounts(account_ids, balances)
        self.assertEqual(int(np.isnat(a["CLOSE_DT"]).sum()), 50)
        self.assertEqual(int(np.isnat(a["LAST_PURCHASE_DT"]).sum()), 30)
        for child in ("CLOSE_DT", "LAST_PAYMENT_DT", "LAST_PURCHASE_DT", "BUSINESSEFFECTIVEDATE"):
            self.assertTrue(ordered(a, "OPEN_DT", child))
        for child in ("LAST_PAYMENT_DT", "LAST_PURCHASE_DT"):
            self.assertTrue(ordered(a, child, "BUSINESSEFFECTIVEDATE"))
        # Gap propagation removes October before sampling, rather than failing randomly later.
        self.assertTrue(np.all(a["BUSINESSEFFECTIVEDATE"].astype("datetime64[M]") == np.datetime64("2020-12", "M")))
        self.assertTrue(np.all(a["LAST_PAYMENT_DT"].astype("datetime64[M]") == np.datetime64("2020-12", "M")))
        np.testing.assert_array_equal(a["BUSINESSEFFECTIVEDATE"], b["BUSINESSEFFECTIVEDATE"][::-1])
        self.assertEqual(model.expected_null_counts["TKQ_ACCOUNT_BALANCE"]["BUSINESSEFFECTIVEDATE"], 0)

    def test_effective_key_is_non_null_even_when_source_key_is_nullable(self):
        model = sampler([
            ("TKQ_ACCOUNT", "BUSINESSEFFECTIVEDATE", "2020-01-01", "2020-01-31", [("2020-01", 50)], 50),
            ("TKQ_ACCOUNT_BALANCE", "BUSINESSEFFECTIVEDATE", "2020-01-10", "2020-01-20", [("2020-01", 80)], 20),
        ])
        a, b = model.generate_accounts(["A1", "A2"], ["A2", "A1"])
        self.assertFalse(np.isnat(a["BUSINESSEFFECTIVEDATE"]).any())
        self.assertTrue(np.all(a["BUSINESSEFFECTIVEDATE"] >= np.datetime64("2020-01-10")))
        self.assertTrue(np.all(a["BUSINESSEFFECTIVEDATE"] <= np.datetime64("2020-01-20")))
        self.assertEqual(model.diagnostics[-1]["source_null_rate"], .2)
        with self.assertRaisesRegex(DateGenerationError, "same accounts"):
            model.generate_accounts(["A1"], ["A2"])

    def test_tradeline_temporal_rules_and_empty_tables(self):
        model = sampler([
            ("TRADELINES", "account_open_date", "2015-01-01", "2020-01-31", [("2015-01", 50), ("2020-01", 50)], 0),
            ("TRADELINES", "account_closed_date", "2018-01-01", "2020-01-31", [("2018-01", 20), ("2020-01", 20)], 60),
            ("TRADELINES", "last_activity_date", "2019-01-01", "2020-01-31", [("2019-01", 50), ("2020-01", 50)], 0),
            ("TRADELINES", "snapshot_date", "2020-01-01", "2020-01-31", [("2020-01", 100)], 0),
        ])
        values = model.generate_table("TRADELINES", 100)
        self.assertTrue(ordered(values, "account_open_date", "account_closed_date"))
        self.assertTrue(ordered(values, "account_open_date", "last_activity_date"))
        self.assertTrue(ordered(values, "last_activity_date", "snapshot_date"))
        self.assertEqual(int(np.isnat(values["account_closed_date"]).sum()), 60)
        self.assertTrue(all(len(x) == 0 for x in model.generate_table("TRADELINES", 0).values()))

    def test_same_seed_is_repeatable_and_unrelated_rng_and_columns_are_independent(self):
        specs = [("PERSON", "TEST_DT", "2020-01-01", "2020-12-31", [("2020-01", 70), ("2020-12", 30)], 20)]
        a, b = sampler(specs), sampler(specs)
        rng = np.random.default_rng(42)
        before = json.dumps(rng.bit_generator.state)
        np.testing.assert_array_equal(a.generate_table("PERSON", 100)["TEST_DT"], b.generate_table("PERSON", 100)["TEST_DT"])
        self.assertEqual(before, json.dumps(rng.bit_generator.state))
        np.testing.assert_array_equal(a.generate_table("PERSON", 100)["TEST_DT"], b.generate_table("PERSON", 100)["TEST_DT"])
        c = sampler(specs, seed=43)
        self.assertFalse(np.array_equal(a.generate_table("PERSON", 100)["TEST_DT"].view("i8"), c.generate_table("PERSON", 100)["TEST_DT"].view("i8")))
        extra = sampler(specs + [("PERSON", "ANOTHER_DT", "2019-01-01", "2019-01-31", [("2019-01", 100)], 0)])
        np.testing.assert_array_equal(a.generate_table("PERSON", 100)["TEST_DT"], extra.generate_table("PERSON", 100)["TEST_DT"])

    def test_all_null_dates_and_explicit_legacy_range_fallback(self):
        dates, months, quality = profiles([
            ("PERSON", "ALL_NULL_DT", None, None, [], 100),
            ("PERSON", "TEST_DT", "2020-01-01", "2020-01-31", [("2020-01", 80)], 20),
        ])
        model = DateSampler("source-A", 42, dates, [], quality)
        values = model.generate_table("PERSON", 100)
        self.assertEqual(int(np.isnat(values["ALL_NULL_DT"]).sum()), 100)
        self.assertEqual(int(np.isnat(values["TEST_DT"]).sum()), 20)
        self.assertEqual({row["method"] for row in model.diagnostics}, {"ALL_NULL", "RANGE_FALLBACK"})
        with self.assertRaisesRegex(DateGenerationError, "usable account/balance"):
            model.generate_accounts(["A1"], ["A1"])

    def test_mixed_runs_and_corrupt_or_incomplete_month_profiles_are_rejected(self):
        original = profiles([("PERSON", "TEST_DT", "2020-01-01", "2020-12-31", [("2020-01", 90), ("2020-12", 10)], 0)])
        for corrupt in ("wrong_run", "generated", "duplicate", "incomplete"):
            dates, months, quality = ([dict(row) for row in part] for part in original)
            if corrupt == "wrong_run": months[0]["run_id"] = "generated-B"
            elif corrupt == "generated": months[0]["profile_type"] = "GENERATED"
            elif corrupt == "duplicate": months.append(dict(months[0]))
            else: months.pop()
            with self.subTest(corrupt=corrupt), self.assertRaises(DateGenerationError):
                DateSampler("source-A", 42, dates, months, quality)

    def test_loader_requires_exact_completed_source_and_reads_only_aggregate_tables(self):
        spark = CategoricalSpark()
        self.addCleanup(spark.db.close)
        spark.db.executescript("""
            CREATE TABLE date_profile (run_id, logical_table_name, column_name, earliest_date, latest_date, non_null_count);
            INSERT INTO date_profile VALUES ('source-A','PERSON','TEST_DT','2020-01-01','2020-12-31',100);
            INSERT INTO column_quality VALUES ('source-A','PERSON','TEST_DT',100,100,12);
            ALTER TABLE column_quality ADD COLUMN null_count;
            UPDATE column_quality SET null_count=0;
            CREATE TABLE date_distribution_profile (run_id, profile_type, logical_table_name, column_name, month_bucket, record_count, non_null_count, proportion);
            INSERT INTO date_distribution_profile VALUES ('source-A','SOURCE','PERSON','TEST_DT','2020-01',90,100,.9),
              ('source-A','SOURCE','PERSON','TEST_DT','2020-12',10,100,.1);
            INSERT INTO profile_runs VALUES ('generated-B','GENERATED','COMPLETED','2026-01-02');
        """)
        with self.assertRaisesRegex(DateGenerationError, "completed SOURCE"):
            load_date_sampler(spark, "source-A", 42)
        spark.db.execute("UPDATE profile_runs SET status='COMPLETED', completed_at='2026-01-01' WHERE run_id='source-A'")
        model = load_date_sampler(spark, "source-A", 42)
        self.assertEqual(model.source_run_id, "source-A")
        self.assertEqual(len(model.generate_table("PERSON", 100)["TEST_DT"]), 100)
        with self.assertRaisesRegex(DateGenerationError, "completed SOURCE"):
            load_date_sampler(spark, "generated-B", 42)
        self.assertTrue(all("current_run" not in sql and "FROM person_data" not in sql for sql, _ in spark.queries))

    def test_extracted_samplers_preserve_non_date_values_and_null_counts(self):
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("Optional notebook integration check requires the notebook's pandas dependency.")
        model = sampler([
            ("PERSON", "BIRTH_DT", "1980-01-01", "1980-01-31", [("1980-01", 80)], 20),
            ("PERSON", "SINCE_DT", "2000-01-01", "2000-01-31", [("2000-01", 70)], 30),
            ("TKQ_ACCOUNT", "OPEN_DT", "2020-01-01", "2020-01-31", [("2020-01", 100)], 0),
            ("TKQ_ACCOUNT", "CLOSE_DT", "2020-09-01", "2020-09-30", [("2020-09", 80)], 20),
            ("TKQ_ACCOUNT", "LAST_PAYMENT_DT", "2020-08-01", "2020-10-31", [("2020-08", 50), ("2020-10", 50)], 0),
            ("TKQ_ACCOUNT", "BUSINESSEFFECTIVEDATE", "2020-12-01", "2020-12-31", [("2020-12", 100)], 0),
            ("TKQ_ACCOUNT_BALANCE", "BUSINESSEFFECTIVEDATE", "2020-12-01", "2020-12-31", [("2020-12", 100)], 0),
        ])
        person = pd.DataFrame({"PARTY_ID": [f"P{i}" for i in range(10)], "TEST_AMT": np.arange(10), "TEST_CD": ["FAKE"] * 10})
        account = pd.DataFrame({"ACCOUNT_ID": [f"A{i}" for i in range(10)], "CREDIT_LIMIT_AMT": np.arange(10) + 100})
        balance = pd.DataFrame({"ACCOUNT_ID": list(reversed(account["ACCOUNT_ID"])), "CURRENT_BALANCE_AMT": np.arange(10) + 5})
        from types import SimpleNamespace
        from synthetic_banking.generators import ProfileGenerators
        samplers = ProfileGenerators(SimpleNamespace(
            category_stats=pd.DataFrame(columns=["logical_table_name", "column_name"]),
            numeric_stats=pd.DataFrame(columns=["logical_table_name", "column_name"]),
            column_quality=pd.DataFrame(columns=["logical_table_name", "column_name"]),
            structural_stats=pd.DataFrame(),
        ), np.random.default_rng(42))
        for column, values in model.generate_table("PERSON", len(person)).items():
            person[column] = values
        account_dates, balance_dates = model.generate_accounts(account["ACCOUNT_ID"], balance["ACCOUNT_ID"])
        for column, values in account_dates.items():
            account[column] = values
        samplers.fill_profiled_fields(balance, "TKQ_ACCOUNT_BALANCE", protected_columns=["ACCOUNT_ID"])
        for column, values in balance_dates.items():
            balance[column] = values
        np.testing.assert_array_equal(person["TEST_AMT"], np.arange(10))
        self.assertEqual(person["TEST_CD"].tolist(), ["FAKE"] * 10)
        np.testing.assert_array_equal(account["CREDIT_LIMIT_AMT"], np.arange(10) + 100)
        np.testing.assert_array_equal(balance["CURRENT_BALANCE_AMT"], np.arange(10) + 5)
        self.assertEqual((person["BIRTH_DT"].isna().sum(), person["SINCE_DT"].isna().sum()), (2, 3))
        self.assertEqual(account["CLOSE_DT"].isna().sum(), 2)
        aligned = balance.set_index("ACCOUNT_ID")["BUSINESSEFFECTIVEDATE"].reindex(account["ACCOUNT_ID"])
        np.testing.assert_array_equal(account["BUSINESSEFFECTIVEDATE"], aligned)


if __name__ == "__main__":
    unittest.main()
