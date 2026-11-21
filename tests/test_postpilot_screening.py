from copy import deepcopy
import json
import unittest
from unittest.mock import patch
from synthetic_banking.validation_reporting import build_validation_report,SCREENING_THRESHOLDS
from validation_report_fixtures import validation_metrics


class PostpilotScreeningTests(unittest.TestCase):
    def test_means_zero_references_and_missing_tails_stay_distinct(self):
        r=build_validation_report(validation_metrics());p=r['post_pilot'];a={a['key']:a for a in p['assessments']}
        self.assertEqual(a['mean.current_balance']['status'],'NEEDS_REVIEW')
        self.assertEqual(a['mean.overlimit']['policy'],'zero_mean_absolute')
        self.assertEqual(a['mean.overlimit']['status'],'STRONG')
        self.assertEqual(a['tail.current_balance']['status'],'UNAVAILABLE')
        self.assertEqual(len(p['assessments']),13)
        self.assertEqual(p['integrity_requirements'],{'snapshot_join_coverage':1.,'allowed_violations':0})
        self.assertEqual(r['summary']['variables_total'],8)
        self.assertEqual(r,build_validation_report(list(reversed(validation_metrics()))))

    def test_configurable_policy_and_zero_reference_alert_without_invented_denominator(self):
        rows=validation_metrics()
        for row in rows:
            if row['family']=='NUMERIC' and row['column_name']=='OVERLIMIT_AMT' and row['metric']=='mean_value':
                row.update(generated_value=12.,difference=12.)
        result=build_validation_report(rows)['post_pilot']
        self.assertIn('mean.overlimit',result['zero_reference_alerts'])
        self.assertNotIn('mean.overlimit',result['weaknesses'])
        changed=deepcopy(SCREENING_THRESHOLDS);changed['mean_relative_pct']={'strong':20.,'acceptable':30.}
        with patch('synthetic_banking.validation_reporting.SCREENING_THRESHOLDS',changed):
            a=next(a for a in build_validation_report(rows)['post_pilot']['assessments'] if a['key']=='mean.current_balance')
            self.assertEqual(a['status'],'STRONG')
        changed['mean_relative_pct']['strong']=float('nan')
        with patch('synthetic_banking.validation_reporting.SCREENING_THRESHOLDS',changed),self.assertRaises(ValueError):
            build_validation_report(rows)

    def test_tail_and_missing_values_never_fabricate_a_pass(self):
        rows=validation_metrics();source=next(r for r in rows if r['family']=='NUMERIC' and r['column_name']=='CURRENT_BALANCE_AMT')
        for metric,value in (('p01',10.),('p05',20.),('p99',500.)):
            rows.append(dict(source,metric=metric,source_value=value,generated_value=value+100.,difference=100.))
        a=next(a for a in build_validation_report(rows)['post_pilot']['assessments'] if a['key']=='tail.current_balance')
        self.assertEqual(a['status'],'NEEDS_REVIEW')
        rows[-1]['generated_value']=float('inf')
        r=build_validation_report(rows);json.dumps(r,allow_nan=False)
        self.assertEqual(next(a for a in r['post_pilot']['assessments'] if a['key']=='tail.current_balance')['status'],'UNAVAILABLE')
