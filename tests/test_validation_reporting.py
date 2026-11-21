from copy import deepcopy
import json
import unittest

from synthetic_banking.validation_reporting import build_validation_report, grade
from validation_report_fixtures import validation_metrics


class ValidationReportingTests(unittest.TestCase):
    def setUp(self):
        self.metrics=validation_metrics()

    def test_real_metrics_drive_classifications_and_ranked_findings(self):
        result=build_validation_report(self.metrics)
        rows={a["key"]:a for a in result["assessments"]}
        self.assertEqual(rows["numeric.credit_limit"]["status"], "STRONG")
        self.assertEqual(rows["numeric.current_balance"]["status"], "ACCEPTABLE")
        self.assertEqual(rows["numeric.available_credit"]["status"], "NEEDS_REVIEW")
        self.assertEqual(rows["numeric.overlimit"]["status"], "UNAVAILABLE")
        self.assertIn("numeric.available_credit", result["weaknesses"])
        self.assertIn("date.birth", result["weaknesses"])
        self.assertAlmostEqual(rows["date.birth"]["score"], 30)
        self.assertEqual(result["summary"]["variables_total"], 8)
        self.assertEqual(result, build_validation_report(list(reversed(self.metrics))))
        self.assertEqual(result["summary"]["comparison_status"], "REVIEW_REQUIRED")
        self.assertTrue(all(rows[k]["status"]=="STRONG" for k in result["strengths"]))

    def test_chart_average_does_not_hide_a_large_single_percentile(self):
        row=next(r for r in self.metrics if r["column_name"]=="CREDIT_LIMIT_AMT" and r["metric"]=="p95")
        row["generated_value"]+=100
        result=build_validation_report(self.metrics)
        numeric=result["numeric"][0]
        self.assertEqual(numeric["status"], "NEEDS_REVIEW")
        self.assertGreater(numeric["max_difference_pct_iqr"], numeric["average_difference_pct_iqr"])

    def test_no_evidence_is_pending_without_invented_strengths(self):
        result=build_validation_report([])
        self.assertEqual(result["status"], "PENDING")
        self.assertEqual(result["strengths"], [])
        self.assertEqual(result["weaknesses"], [])
        self.assertEqual(result["summary"]["checks_evaluated"], 0)

    def test_small_conditional_populations_retain_raw_rates_but_cannot_pass(self):
        row=next(r for r in self.metrics if r["family"]=="CONDITIONAL")
        row["source_sample_size"]=29
        a=next(a for a in build_validation_report(self.metrics)["assessments"] if a["key"]=="conditional.0")
        self.assertEqual(a["status"], "UNAVAILABLE")
        self.assertEqual(a["source"], .1)
        self.assertIsNone(a["score"])

    def test_nonfinite_missing_and_incomplete_distributions_never_pass(self):
        row=next(r for r in self.metrics if r["family"]=="DATE_DISTRIBUTION")
        row["source_value"]=.2
        self.metrics[0]["generated_value"]=float("inf")
        result=build_validation_report(self.metrics)
        json.dumps(result, allow_nan=False)
        self.assertEqual(result["dates"][0]["status"], "UNAVAILABLE")
        self.assertEqual(result["numeric"][0]["status"], "UNAVAILABLE")

    def test_integrity_needs_zero_violations_and_full_coverage(self):
        row=next(r for r in self.metrics if r["family"]=="JOIN_COVERAGE")
        row["generated_value"]=.999
        a=next(a for a in build_validation_report(self.metrics)["assessments"] if a["key"]=="integrity.account_coverage")
        self.assertEqual(a["status"], "NEEDS_REVIEW")
        row["generated_sample_size"]=0
        a=next(a for a in build_validation_report(self.metrics)["assessments"] if a["key"]=="integrity.account_coverage")
        self.assertEqual(a["status"], "UNAVAILABLE")

    def test_public_projection_discards_ids_categories_and_free_text(self):
        for row in self.metrics:
            row.update(source_run_id="SECRET_SOURCE", generated_run_id="SECRET_GENERATED", reason="PRIVATE_REASON")
        self.metrics.append(dict(family="CATEGORICAL",entity_name="PERSON",column_name="PARTY_ID",metric="proportion",
                                 dimensions_json=json.dumps({"category_value":"PRIVATE_PARTY"}),source_value=1,generated_value=1))
        audit=[dict(proposal_id="SECRET_PROPOSAL", implementation_name="available_to_buy", approved=True,applied=True,outcome="APPLIED",proposed_rule="PRIVATE_TEXT"),
               dict(proposal_id=None,implementation_name="overlimit_amount",applied=True)]
        report=build_validation_report(self.metrics,audit)
        text=json.dumps(report)
        # Reviewed identifier COLUMN NAMES now appear in the all-field null audit;
        # actual identifiers, arbitrary categories and execution IDs still cannot.
        for forbidden in ("SECRET_","PRIVATE_"):
            self.assertNotIn(forbidden,text)
        self.assertEqual(report["rule_outcomes"][0]["applied"],1)
        self.assertEqual(report["rule_outcomes"][1]["applied"],0)

    def test_threshold_boundaries_and_per_family_caps(self):
        self.assertEqual(grade(1.0+1e-15,"proportion_pp"),"STRONG")
        self.assertEqual(grade(3,"proportion_pp"),"ACCEPTABLE")
        self.assertEqual(grade(3.01,"proportion_pp"),"NEEDS_REVIEW")
        result=build_validation_report(self.metrics)
        for field in ("strengths","weaknesses"):
            families=[next(a["family"] for a in result["assessments"] if a["key"]==key) for key in result[field]]
            self.assertTrue(all(families.count(f)<=2 for f in families))


if __name__=="__main__":unittest.main()
