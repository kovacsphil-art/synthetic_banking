from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch,Mock
from synthetic_banking.privacy_reporting import public_privacy_summary,load_public_privacy
from privacy_report_fixtures import privacy_evidence


class PrivacyReportingTests(unittest.TestCase):
    def test_projection_distinguishes_source_rarity_and_keeps_release_disabled(self):
        a,rows=privacy_evidence();a['reviewed_by']='PRIVATE_PERSON'
        rows[0]['row_sample']='PRIVATE_RECORD'
        result=public_privacy_summary(a,rows)
        self.assertEqual(result['status'],'REVIEW_REQUIRED')
        self.assertFalse(result['row_level_downloads_enabled'])
        self.assertEqual(result['near_matches']['flagged_rows'],2)
        self.assertEqual(result['near_matches']['flagged_fraction'],.01)
        self.assertEqual(result['categorical_patterns'][0]['synthetic_rare_rows'],0)
        self.assertEqual(result['categorical_patterns'][0]['source_rare_match_rows'],3)
        self.assertEqual(result['identifier_overlap_rows'],0)
        text=json.dumps(result,allow_nan=False)
        for secret in ('fabricated-','PRIVATE_','reviewed_by','row_sample'):
            self.assertNotIn(secret,text)

    def test_missing_incomplete_or_different_policy_never_clears_release(self):
        self.assertEqual(public_privacy_summary()['status'],'UNAVAILABLE')
        a,rows=privacy_evidence();a['status']='PASS'
        self.assertEqual(public_privacy_summary(a,rows)['status'],'REVIEW_REQUIRED')
        result=public_privacy_summary(a,rows[:-1])
        self.assertEqual(result['status'],'BLOCKED');self.assertIsNone(result['near_matches']['flagged_rows'])
        a['policy_sha256']='wrong'
        self.assertEqual(public_privacy_summary(a,rows)['status'],'UNAVAILABLE')

    def test_loader_requires_exact_assessment_and_dataset_snapshots(self):
        a,rows=privacy_evidence()
        def frame(values):return SimpleNamespace(collect=lambda:[SimpleNamespace(asDict=lambda value=value:deepcopy(value)) for value in values])
        spark=SimpleNamespace(sql=Mock(side_effect=lambda sql,args:frame([a] if 'privacy_assessments' in sql else rows)))
        with patch('synthetic_banking.privacy._validated_generation',return_value={'validated_versions':{'PERSON':'fabricated-delta:3'}}),patch(
            'synthetic_banking.privacy_sources.load_source_snapshots',return_value={}),patch('synthetic_banking.privacy_sources.snapshot_signature',return_value='fabricated-snapshot'):
            report=load_public_privacy(spark,'fabricated-source','fabricated-generation','fabricated-batch','fabricated-assessment')
            self.assertEqual(report['status'],'REVIEW_REQUIRED')
            self.assertTrue(all('current_run' not in c.args[0] and 'ORDER BY' not in c.args[0] for c in spark.sql.call_args_list))
            with self.assertRaisesRegex(ValueError,'does not match'):
                load_public_privacy(spark,'wrong-source','fabricated-generation','fabricated-batch','fabricated-assessment')
            a['generated_versions_json']='{}'
            with self.assertRaisesRegex(ValueError,'snapshots do not match'):
                load_public_privacy(spark,'fabricated-source','fabricated-generation','fabricated-batch','fabricated-assessment')
