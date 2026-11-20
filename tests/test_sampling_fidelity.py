"""Fabricated aggregate comparisons for conditional sampling and its public projection."""
from copy import deepcopy
import json
import unittest

from synthetic_banking.fidelity import compare_profiles
from synthetic_banking.profiling import categorical_statistics
from synthetic_banking.validation_reporting import build_validation_report


def paired_profiles():
    profiles = {"categorical_relationship_profile": [], "categorical_conditional_profile": []}
    for run, counts in (("source", (("PRIVATE_A", "PRIVATE_C", 80), ("PRIVATE_B", "PRIVATE_D", 20))),
                        ("generated", (("PRIVATE_A", "PRIVATE_C", 60), ("PRIVATE_A", "PRIVATE_D", 20), ("PRIVATE_B", "PRIVATE_D", 20)))):
        summary, cells = categorical_statistics([dict(parent_value=p, child_value=c, record_count=n) for p,c,n in counts], 100)
        identity = dict(run_id=run, logical_table_name="TKQ_ACCOUNT", parent_column="ACCOUNT_TYPE_CD", child_column="CLIENT_PRODUCT_CD")
        profiles["categorical_relationship_profile"].append(dict(summary, **identity))
        profiles["categorical_conditional_profile"].extend(dict(c, **identity) for c in cells)
    return profiles


class SamplingFidelityTests(unittest.TestCase):
    def test_conditional_rates_zero_cells_and_weighted_public_tvd(self):
        report = compare_profiles("source", "generated", "generation", paired_profiles())
        metrics = report["metrics"]
        row = next(r for r in metrics if r["family"] == "CATEGORICAL_CONDITIONAL" and r["metric"] == "unsupported_combination_rate")
        self.assertAlmostEqual(row["generated_value"], .2)
        supplemental = build_validation_report(metrics)["dependency_fidelity"]
        categorical = supplemental["categorical"][0]
        self.assertAlmostEqual(categorical["conditional_tvd_pct"], 20.)
        self.assertAlmostEqual(categorical["unsupported_combination_rate"], .2)
        self.assertEqual(categorical["source_n"], 100)
        self.assertIsNone(supplemental["categorical"][1]["conditional_tvd_pct"])
        self.assertTrue(all(r["mean_difference"] is None for r in supplemental["numeric_segments"]))
        self.assertNotIn("PRIVATE_", json.dumps(supplemental))
        json.dumps(supplemental, allow_nan=False)

    def test_missing_parent_and_incomplete_grid_are_not_zero_improvement(self):
        profiles = paired_profiles()
        profiles["categorical_conditional_profile"].pop()
        report = compare_profiles("source", "generated", "generation", profiles)
        result = build_validation_report(report["metrics"])["dependency_fidelity"]["categorical"][0]
        self.assertIsNone(result["conditional_tvd_pct"])
        self.assertIsNone(result["unsupported_combination_rate"])
        self.assertNotIn("dependency_fidelity", build_validation_report([]))

    def test_duplicate_conditional_cells_are_not_reported_as_a_valid_distance(self):
        metrics = compare_profiles("source", "generated", "generation", paired_profiles())["metrics"]
        cell = next(r for r in metrics if r["family"] == "CATEGORICAL_CONDITIONAL" and r["metric"] == "conditional_proportion")
        metrics.append(deepcopy(cell))
        result = build_validation_report(metrics)["dependency_fidelity"]["categorical"][0]
        self.assertIsNone(result["conditional_tvd_pct"])

    def test_source_quantile_boundary_mismatch_keeps_difference_unavailable(self):
        common = dict(entity_name="ACCOUNT", variable_1="TKQ_ACCOUNT.CREDIT_LIMIT_AMT",
                      variable_2="TKQ_ACCOUNT_BALANCE.CURRENT_BALANCE_AMT", scope="X_QUARTILE",
                      segment_value="Q1", segment_column=None, segment_is_null=False, pair_count=100,
                      profile_status="PROFILED", lower_bound=None, y_mean=100.)
        profiles = {"numeric_dependency_profile": [dict(common, run_id="source", upper_bound=1000.),
                                                     dict(common, run_id="generated", upper_bound=2000.)]}
        result = build_validation_report(compare_profiles("source", "generated", "generation", profiles)["metrics"])
        row = result["dependency_fidelity"]["numeric_segments"][0]
        self.assertEqual(row["source_mean"], 100.)
        self.assertIsNone(row["mean_difference"])
