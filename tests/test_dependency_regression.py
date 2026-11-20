"""Fixed pre-change regression evidence, generated entirely from fabricated profiles."""

from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

try:
    import pandas as pd
except ImportError:
    pd = None

from synthetic_banking.rules import (
    RuleProposal, apply_delinquency_rule, delinquency_probabilities, utilization_buckets,
)


SOURCE = "source-A"
BUCKETS = ("0-30%", "30-60%", "60-80%", "80-100%", "100%+")


def measured_profile():
    return [dict(run_id=SOURCE, entity_name="ACCOUNT", condition_variable="UTILIZATION_RATE",
                 outcome_variable="PAST_DUE_INDICATO_CD", condition_bucket=bucket,
                 record_count=100, outcome_rate=rate)
            for bucket, rate in zip(BUCKETS, (.1, .2, .3, .4, .5))]


def reviewed_proposals():
    available = RuleProposal("available", SOURCE, "TKQ_ACCOUNT_BALANCE", "AVAILABLE_TO_BUY_AMT", "DERIVED",
                             ("CREDIT_LIMIT_AMT", "CURRENT_BALANCE_AMT"), "APPROVED", "fabricated-batch", True)
    return (available, replace(available, proposal_id="overlimit", target_column="OVERLIMIT_AMT"),
            replace(available, proposal_id="delinquency", target_table="TKQ_ACCOUNT",
                    target_column="PAST_DUE_INDICATO_CD", rule_type="CONDITIONAL",
                    parent_columns=("UTILIZATION_RATE",)))


class SharedDependencyTests(unittest.TestCase):
    def test_shared_lookup_matches_original_scalar_boundaries_and_default(self):
        # Independent transcription of the old scalar branch, including NaN/inf behaviour.
        def original(value, rates):
            if value < .3:
                bucket = "0-30%"
            elif value < .6:
                bucket = "30-60%"
            elif value < .8:
                bucket = "60-80%"
            elif value <= 1:
                bucket = "80-100%"
            else:
                bucket = "100%+"
            return rates.get(bucket, .05)

        values = np.array([-np.inf, -1, 0, np.nextafter(.3, 0), .3, np.nextafter(.6, 0),
                           .6, np.nextafter(.8, 0), .8, 1, np.nextafter(1., 2), np.inf, np.nan])
        for rates in ({}, {"0-30%": .1, "60-80%": .3, "100%+": .8}):
            with self.subTest(rates=rates):
                np.testing.assert_array_equal(delinquency_probabilities(values, rates),
                                              [original(value, rates) for value in values])
        self.assertEqual(utilization_buckets([.3, .6, .8, 1., 1.01]).tolist(),
                         ["30-60%", "60-80%", "80-100%", "80-100%", "100%+"])

    def test_framework_owns_fallback_lookup_and_uses_only_the_pinned_source(self):
        rows = measured_profile()
        evidence = [dict(row, run_id="GENERATED-other", outcome_rate=1) for row in rows]
        evidence += [dict(row, entity_name="OTHER", outcome_rate=1) for row in rows]
        evidence += rows[:-1]
        flags, events = apply_delinquency_rule(SOURCE, (), [.1, .4, .7, .9, 1.2], evidence, [.15] * 5)
        np.testing.assert_array_equal(flags, [False, True, True, True, False])
        self.assertEqual([(e.outcome, e.rows_processed, e.applied) for e in events],
                         [("LEGACY_FALLBACK", 5, False)])

    def test_strict_review_checks_do_not_replace_missing_evidence_with_default(self):
        _, _, conditional = reviewed_proposals()
        evidence = iter(measured_profile()[:-1])
        flags, events = apply_delinquency_rule(SOURCE, (conditional,), [1.2], evidence, [.04])
        np.testing.assert_array_equal(flags, [True])  # Preserved legacy 5%, not an approved rule.
        self.assertEqual((events[0].reason, events[0].approved, events[0].implemented, events[0].applied),
                         ("missing_conditional_profile", True, True, False))
        self.assertEqual(events[-1].outcome, "LEGACY_FALLBACK")

    def test_duplicate_evidence_is_skipped_but_original_last_rate_fallback_is_preserved(self):
        _, _, conditional = reviewed_proposals()
        evidence = measured_profile() + [dict(measured_profile()[0], outcome_rate=.9)]
        flags, events = apply_delinquency_rule(SOURCE, (conditional,), [.1], iter(evidence), [.5])
        np.testing.assert_array_equal(flags, [True])
        self.assertEqual(events[0].reason, "invalid_conditional_profile")
        self.assertFalse(events[0].applied)
        self.assertEqual(events[-1].outcome, "LEGACY_FALLBACK")

    def test_approved_execution_does_not_compute_an_unused_legacy_lookup(self):
        _, _, conditional = reviewed_proposals()
        with patch("synthetic_banking.rules._legacy_delinquency_probabilities", side_effect=AssertionError("unused lookup")):
            flags, events = apply_delinquency_rule(SOURCE, (conditional,), [.4], iter(measured_profile()), [.1])
        np.testing.assert_array_equal(flags, [True])
        self.assertEqual((events[0].outcome, events[0].execution_order), ("APPLIED", 3))
        self.assertEqual(len(events), 1)


@unittest.skipIf(pd is None, "Generator integration requires pandas, included in Databricks.")
class CohortDependencyRegressionTests(unittest.TestCase):
    def test_existing_scalar_sampler_delegates_without_consuming_random_numbers(self):
        from generation_fixtures import fabricated_profiles
        from synthetic_banking.generators import ProfileGenerators
        profiles, _ = fabricated_profiles()
        rng = np.random.default_rng(42)
        sampler = ProfileGenerators(profiles, rng)
        sampler.delinquency_rates = {"30-60%": .2}
        before = json.dumps(rng.bit_generator.state)
        self.assertEqual(sampler.get_delinquency_probability(.3), .2)
        self.assertEqual(sampler.get_delinquency_probability(1.1), .05)
        self.assertEqual(json.dumps(rng.bit_generator.state), before)

    def test_six_table_distributions_rng_and_audit_match_pre_change_generation(self):
        from generation_fixtures import fabricated_profiles, fingerprint
        from synthetic_banking.config import GenerationSettings
        from synthetic_banking.generation import generate_dataset
        reference = json.loads((Path(__file__).parent / "fixtures/dependency_generation_reference.json").read_text())
        approvals = reviewed_proposals()
        scenarios = {
            "no_proposals": (),
            "approved": approvals,
            "pending": tuple(replace(p, approval_status="PENDING") for p in approvals),
            "rejected": tuple(replace(p, approval_status="REJECTED") for p in approvals),
            "unsupported": (replace(approvals[0], target_column="UNIMPLEMENTED"),),
            "unverified": tuple(replace(p, has_review_provenance=False) for p in approvals),
            "conflicting": (*approvals, replace(approvals[-1], proposal_id="conflicting-delinquency")),
        }
        for name, expected in reference.items():
            for scenario, proposals in scenarios.items():
                with self.subTest(profile=name, scenario=scenario):
                    profiles, dates = fabricated_profiles()
                    if name == "missing_bucket":
                        profiles.conditional_stats = profiles.conditional_stats[profiles.conditional_stats.condition_bucket != "100%+"]
                    settings = GenerationSettings(expected["customers"], expected["seed"])
                    with redirect_stdout(StringIO()), patch("synthetic_banking.generation.load_rule_proposals", return_value=proposals):
                        result = generate_dataset(SimpleNamespace(), profiles, settings, date_sampler=dates(settings.seed))
                    actual = fingerprint(result.tables, (), result.rng_state, {})
                    self.assertEqual(actual["tables"], expected["tables"])
                    self.assertEqual(actual["rng_state"], expected["rng_state"])
                    for column, values in expected["numeric"].items():
                        table = "TKQ_ACCOUNT" if column == "CREDIT_LIMIT_AMT" else "TKQ_ACCOUNT_BALANCE"
                        generated = result.tables[table][column].to_numpy(dtype=float)
                        self.assertEqual(float(np.mean(generated)), values["mean"])
                        np.testing.assert_array_equal(np.quantile(generated, [0, .25, .5, .75, .95, 1]), values["quantiles"])
                    accounts = result.tables["TKQ_ACCOUNT"]
                    u = accounts._UTILIZATION_RATE.to_numpy()
                    masks = (u < .3, (u >= .3) & (u < .6), (u >= .6) & (u < .8), (u >= .8) & (u <= 1), u > 1)
                    for bucket, mask in zip(BUCKETS, masks):
                        self.assertEqual(int(mask.sum()), expected["conditional"][bucket]["rows"])
                        self.assertEqual(int(accounts.loc[mask, "PAST_DUE_INDICATO_CD"].eq("Y").sum()),
                                         expected["conditional"][bucket]["past_due"])
                    proposal_events = [e for e in result.rule_events if e.proposed]
                    self.assertEqual(sorted(e.proposal_id for e in proposal_events), sorted(p.proposal_id for p in proposals))
                    self.assertTrue(all(e.batch_id == "fabricated-batch" for e in proposal_events))
                    for event in proposal_events:
                        eligible = scenario in ("approved", "conflicting")
                        if event.target_column == "PAST_DUE_INDICATO_CD":
                            eligible = eligible and name == "complete" and scenario != "conflicting"
                        self.assertEqual(event.applied, eligible)
                        self.assertEqual(event.outcome, "APPLIED" if eligible else "SKIPPED")
                    executed = [e for e in result.rule_events if e.outcome in ("APPLIED", "LEGACY_FALLBACK")]
                    self.assertEqual([e.execution_order for e in executed], [1, 2, 3])
                    self.assertEqual(len({(e.target_table, e.target_column) for e in executed}), 3)
                    self.assertTrue(all(e.rows_processed == len(accounts) for e in executed))
                    self.assertTrue(all(not e.applied and not e.approved and e.proposal_id is None
                                        for e in executed if e.outcome == "LEGACY_FALLBACK"))


if __name__ == "__main__":
    unittest.main()
