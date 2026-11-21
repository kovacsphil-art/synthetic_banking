"""Fabricated privacy metadata and aggregate counts; no matched records."""
from dataclasses import asdict
from datetime import datetime, timezone
import json
from synthetic_banking.privacy_checks import PrivacyPolicy
from test_privacy import complete_metrics


def privacy_evidence():
    policy=PrivacyPolicy()
    assessment=dict(assessment_id='fabricated-assessment',source_run_id='fabricated-source',generation_id='fabricated-generation',
        completed_at=datetime(2026,1,1,tzinfo=timezone.utc),status='REVIEW_REQUIRED',policy_version='basic_v1',
        policy_json=json.dumps(asdict(policy)),policy_sha256=policy.fingerprint,metric_count=25,
        generated_versions_json=json.dumps({'PERSON':'fabricated-delta:3'}),source_snapshot_sha256='fabricated-snapshot')
    metrics=[m.record() for m in complete_metrics()]
    for m in metrics:
        m.update(assessment_id=assessment['assessment_id'],source_run_id=assessment['source_run_id'],generation_id=assessment['generation_id'],evaluated_rows=200)
        if m['check_name']=='QUASI_SIMILARITY':
            m.update(status='REVIEW_REQUIRED',flagged_rows=2,details_json=json.dumps(dict(generated_complete_rows=200,source_complete_rows=100,
                rare_rows=2,matched_rows=2,minimum_matched_distance_days=3,complete_case_coverage=1.)))
        if m['check_name']=='RARE_COMBINATION':
            source_rare=3 if m['columns']==['GENDER_CD','PREF_LANG_CD','CUST_TYPE_CD'] else 0
            m.update(status='REVIEW_REQUIRED' if source_rare else 'PASS',details_json=json.dumps(dict(synthetic_rare=0,source_rare=source_rare,complete_case_coverage=1.)))
    return assessment,metrics
