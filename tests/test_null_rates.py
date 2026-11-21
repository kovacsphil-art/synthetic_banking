"""Missingness policy regressions use only fabricated aggregate counts."""

import json
from pathlib import Path
import shutil
import subprocess
import unittest

from synthetic_banking.null_rates import classify, build_null_rate_audit, FIELDS
from synthetic_banking.validation_reporting import build_validation_report, THRESHOLDS
from validation_report_fixtures import validation_metrics

LIMITS = THRESHOLDS["proportion_pp"]


def evidence(sc, sn, gc, gn, **extra):
    return dict(family="NULL_RATE", entity_name="PERSON", column_name="BIRTH_DT", metric="null_rate",
                comparison_status="COMPARABLE", source_count=sc, source_sample_size=sn,
                generated_count=gc, generated_sample_size=gn, **extra)


class NullRateTests(unittest.TestCase):
    def test_requested_patterns_use_exact_counts(self):
        cases = [
            ((0,100,0,200), "ZERO_ZERO", "TRIVIAL", "TRIVIAL_MATCH"),
            ((0,100,1,200), "ZERO_NONZERO", "NEEDS_REVIEW", "DISCREPANCY"),
            ((1,100,0,200), "NONZERO_ZERO", "NEEDS_REVIEW", "DISCREPANCY"),
            ((10,100,20,200), "NONZERO_NONZERO", "STRONG", "MEANINGFUL_MATCH"),
            ((10,100,24,200), "NONZERO_NONZERO", "ACCEPTABLE", "MEANINGFUL_MATCH"),
            ((10,100,50,200), "NONZERO_NONZERO", "NEEDS_REVIEW", "DISCREPANCY"),
            ((None,100,0,200), "UNAVAILABLE", "UNAVAILABLE", "UNAVAILABLE"),
        ]
        for counts, pattern, status, category in cases:
            with self.subTest(counts=counts):
                r=classify(evidence(*counts), LIMITS)
                self.assertEqual((r["pattern"],r["status"],r["classification"]),(pattern,status,category))
                self.assertEqual(r["strength_eligible"],status=="STRONG" and category=="MEANINGFUL_MATCH")

    def test_tiny_nonzero_rates_rounding_to_zero_are_not_trivial(self):
        row=evidence(1,1_000_000,2,2_000_000,source_value=0.,generated_value=0.)
        r=classify(row,LIMITS)
        self.assertEqual(r["classification"],"MEANINGFUL_MATCH")
        self.assertEqual(r["source"],.000001)
        self.assertGreater(r["source"],0)
        self.assertEqual(classify(evidence(0,1_000_000,1,1_000_000),LIMITS)["status"],"NEEDS_REVIEW")

    def test_invalid_empty_and_missing_counts_never_pass_using_percentages(self):
        for counts in [(101,100,0,200),(-1,100,0,200),(.5,100,0,200),(False,100,0,200),
                       (0,0,0,200),(0,None,0,200),(float("nan"),100,0,200),(0,100,float("inf"),200)]:
            with self.subTest(counts=counts):
                r=classify(evidence(*counts,source_value=0.,generated_value=0.),LIMITS)
                self.assertEqual(r["status"],"UNAVAILABLE")
                json.dumps(r,allow_nan=False)

    def test_complete_inventory_keeps_zeroes_missing_rows_and_duplicate_reasons(self):
        r=build_null_rate_audit([evidence(0,100,0,200)],LIMITS)
        self.assertEqual(len(r["rows"]),len(FIELDS))
        self.assertEqual(r["summary"]["trivial_zero_null"],1)
        self.assertEqual(r["summary"]["eligible_nontrivial"],0)
        self.assertEqual(r["summary"]["unavailable"],len(FIELDS)-1)
        r=build_null_rate_audit([evidence(0,100,0,200)]*2,LIMITS)
        self.assertEqual(next(a for a in r["rows"] if a["column"]=="BIRTH_DT")["reason"],"duplicate_null_evidence")

    def test_core_and_full_findings_exclude_trivial_without_changing_other_metrics(self):
        rows=validation_metrics()
        before=build_validation_report(rows)
        for row in rows:
            if row["family"]=="NULL_RATE":
                row.update(source_count=0,generated_count=0,source_value=0.,generated_value=0.)
        # A meaningful match elsewhere must remain available to executive findings.
        rows.append(dict(evidence(10,100,20,200),column_name="EMP_TYPE_CD"))
        result=build_validation_report(rows)
        for a,b in zip(before["assessments"],result["assessments"]):
            if a["family"]!="nulls":self.assertEqual(a,b)
        self.assertEqual(before["summary"]["variables_total"],result["summary"]["variables_total"])
        self.assertEqual(before["summary"]["checks_evaluated"],result["summary"]["checks_evaluated"])
        self.assertEqual(result["summary"]["trivial_zero_null"],8)
        self.assertEqual(result["summary"]["strong"],before["summary"]["strong"]-8)
        lookup={a["key"]:a for a in [*result["assessments"],*result["null_rate_audit"]["rows"]]}
        self.assertFalse(any(lookup[k]["status"]=="TRIVIAL" for k in result["strengths"]))
        self.assertIn("null_field.PERSON.EMP_TYPE_CD",result["post_pilot"]["strengths"])
        self.assertEqual(result["post_pilot"]["assessments"],before["post_pilot"]["assessments"])

    def test_material_discrepancies_are_findings_and_new_metadata_is_closed(self):
        rows=validation_metrics()+[dict(evidence(0,100,200,200),column_name="DOMICILE_TRANSIT_NUM"),
                                   dict(evidence(1,100,2,200),column_name="PRIVATE_UNKNOWN_FIELD")]
        result=build_validation_report(rows)
        self.assertIn("null_field.PERSON.DOMICILE_TRANSIT_NUM",result["post_pilot"]["weaknesses"])
        self.assertEqual(result["null_rate_audit"]["summary"]["additional_unpublished_variables"],1)
        self.assertNotIn("PRIVATE_UNKNOWN_FIELD",json.dumps(result))

    def test_all_null_preservation_is_explicit_and_partial_matches_rank_first(self):
        rows=validation_metrics()+[dict(evidence(100,100,200,200),column_name="BANKRUPTCY_DT")]
        result=build_validation_report(rows)
        self.assertEqual(result["null_rate_audit"]["summary"]["all_null_matches"],1)
        selected=[k for k in result["post_pilot"]["strengths"] if k.startswith("null_field.")]
        self.assertNotIn("null_field.PERSON.BANKRUPTCY_DT",selected)

    @unittest.skipUnless(shutil.which("node"), "Node is required for the browser contract parity check")
    def test_emitted_json_and_browser_share_the_same_summary_and_classifications(self):
        from scripts.publish_showcase import validate_report
        root=Path(__file__).resolve().parents[1]
        report=json.loads((root/"docs/reporting/example.json").read_text())
        rows=validation_metrics()
        for row in rows:
            if row["family"]=="NULL_RATE":row.update(source_count=0,generated_count=0,source_value=0.,generated_value=0.)
        rows.extend([dict(evidence(0,100,200,200),column_name="DOMICILE_TRANSIT_NUM"),
                     dict(evidence(1,1_000_000,2,2_000_000),column_name="BANKRUPTCY_DT")])
        report["validation_report"]=build_validation_report(rows)
        payload=json.dumps(report)
        validate_report(payload.encode())
        code="const r=JSON.parse(require('fs').readFileSync(0,'utf8'));const v=require('./docs/validation.js').normalizeValidation(r).v;process.stdout.write(JSON.stringify({core:v.summary,audit:v.null_rate_audit.summary,strengths:v.post_pilot.strengths}));"
        result=subprocess.run([shutil.which("node"),"-e",code],input=payload,capture_output=True,text=True,cwd=root,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        browser=json.loads(result.stdout)
        for name,expected in (("core",report["validation_report"]["summary"]),("audit",report["validation_report"]["null_rate_audit"]["summary"]),
                              ("strengths",report["validation_report"]["post_pilot"]["strengths"])):
            self.assertEqual(browser[name],expected)


if __name__=="__main__":unittest.main()
