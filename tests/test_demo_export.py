"""Only fabricated rows and metadata. No workspace or genuine SOURCE fixtures."""
import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
import zipfile
from collections import Counter
from types import SimpleNamespace

from synthetic_banking.demo_export import (
    TABLES, DemoExportError, check_mode, check_schema, inspect_value, load_policy,
    write_csv, build_archive, export_demo_dataset,
    _same_rows, verify_source_replay,
    _context,
)


class DemoExportTests(unittest.TestCase):
    def test_context_retains_review_required_and_rejects_issues_or_stale_assessments(self):
        from privacy_report_fixtures import privacy_evidence
        from synthetic_banking.privacy_reporting import public_privacy_summary
        from copy import deepcopy
        assessment,metrics=privacy_evidence()
        privacy=public_privacy_summary(assessment,metrics)
        ids={'source_run_id':'fabricated-source','batch_id':'fabricated-batch',
             'generation_id':'fabricated-generation','generated_run_id':'fabricated-generated',
             'privacy_assessment_id':'fabricated-assessment'}
        evidence={'issues':False,'latest':'fabricated-assessment','privacy':privacy,'metrics':metrics}
        def query(sql,args):
            if 'fidelity_metrics' in sql:
                rows=[{'generated_check_status':'ISSUE' if evidence['issues'] else 'PASS'}]
            elif 'privacy_assessments' in sql:
                rows=[{'assessment_id':evidence['latest']}]
            else:rows=evidence['metrics']
            class Row(dict):
                def asDict(self):return deepcopy(dict(self))
            objects=[Row(r) for r in rows]
            return SimpleNamespace(collect=lambda:objects,first=lambda:rows[0])
        spark=SimpleNamespace(sql=Mock(side_effect=query))
        with patch('synthetic_banking.demo_export.require_profile_pair'),patch(
            'synthetic_banking.demo_export.check_approvals'),patch('synthetic_banking.demo_export.enforce_approval'),patch(
            'synthetic_banking.demo_export._validated_generation',return_value={'validated_versions':{'PERSON':'fake:1'}}),patch(
            'synthetic_banking.demo_export.load_source_snapshots',return_value={}),patch(
            'synthetic_banking.demo_export._source_identity_unchanged'),patch(
            'synthetic_banking.demo_export.load_public_privacy',side_effect=lambda *args:evidence['privacy']):
            _,_,result=_context(spark,ids)
            self.assertEqual(result['status'],'REVIEW_REQUIRED')
            for key,value in (('issues',True),('latest','old-assessment'),
                              ('privacy',dict(privacy,status='BLOCKED')),('metrics',metrics[:-1])):
                original=evidence[key];evidence[key]=value
                with self.subTest(key=key),self.assertRaises(DemoExportError):_context(spark,ids)
                evidence[key]=original
        self.assertTrue(all('SELECT' in c.args[0] and 'current_run' not in c.args[0] for c in spark.sql.call_args_list))

    def test_replay_compares_both_sides_and_retains_duplicate_multiplicity(self):
        class Frame:
            columns=['fabricated_key']
            def __init__(self,rows):self.rows=rows
            def select(self,*columns):return self
            def exceptAll(self,other):
                return Frame(list((Counter(self.rows)-Counter(other.rows)).elements()))
            def limit(self,n):return Frame(self.rows[:n])
            def count(self):return len(self.rows)
        self.assertTrue(_same_rows(Frame(['P1','P2']),Frame(['P2','P1'])))
        for actual,expected in ((['P1'],['P1','P2']),(['P1','P2'],['P1']),(['P1','P1'],['P1'])):
            self.assertFalse(_same_rows(Frame(actual),Frame(expected)))

    def test_unreviewed_script_cannot_prove_fabricated_source(self):
        policy=load_policy();policy['generator_sha256']='wrong'
        with self.assertRaisesRegex(DemoExportError,'unreviewed_fabricated_generator'):
            verify_source_replay(Mock(),{},policy)

    def test_source_mismatch_prevents_any_generated_replay_or_export(self):
        spark=Mock();spark.conf.get.return_value='UTC'
        with patch('synthetic_banking.demo_export._context',return_value=({}, {}, {})),patch(
            'synthetic_banking.demo_export.verify_source_replay',side_effect=DemoExportError('source_not_exact_fabricated_replay')),patch(
            'synthetic_banking.demo_export.Path.mkdir') as mkdir:
            with self.assertRaisesRegex(DemoExportError,'source_not_exact'):
                export_demo_dataset(spark,release_mode='DEMO_ONLY',dataset_version='sage-demo-v999',
                    source_run_id='fabricated-source',batch_id='fabricated-batch',generation_id='fabricated-generation',
                    generated_run_id='fabricated-generated',privacy_assessment_id='fabricated-privacy')
            mkdir.assert_not_called()
            spark.read.option.assert_not_called()

    def test_only_explicit_demo_mode_and_safe_new_version_are_accepted(self):
        check_mode('DEMO_ONLY')
        for value in ('', 'PASS', 'PUBLIC', 'demo_only', None):
            with self.subTest(mode=value), self.assertRaises(DemoExportError):
                check_mode(value)
        spark = Mock()
        with self.assertRaises(DemoExportError):
            export_demo_dataset(spark, release_mode='DEMO_ONLY', dataset_version='../docs',
                source_run_id='fabricated-source', batch_id='fabricated-batch', generation_id='fabricated-generation',
                generated_run_id='fabricated-profile', privacy_assessment_id='fabricated-privacy')
        spark.sql.assert_not_called()

    def test_closed_schema_rejects_extra_sensitive_fields_and_wrong_types(self):
        policy = load_policy()
        fields = list(policy['columns']['PERSON'].items())
        check_schema('PERSON', fields, policy)
        for changed in (fields+[('EMAIL','string')], fields[:-1], fields+[fields[0]],
                        [(c,'array<string>' if i==0 else t) for i,(c,t) in enumerate(fields)]):
            with self.subTest(fields=changed), self.assertRaises(DemoExportError):
                check_schema('PERSON', changed, policy)

    def test_secrets_contacts_formulas_and_long_identifiers_fail_without_echo(self):
        for value in ('private@example.invalid','password=do-not-log-me','ghp_'+'a'*36,
                      '-----BEGIN PRIVATE KEY-----', 'AKIA'+'A'*16, 'dapi'+'a'*32,
                      '=HYPERLINK("x")', '+cmd', ' @command', '4111111111111111', '\\N', 'a\tb', float('inf')):
            with self.subTest(kind=type(value).__name__), self.assertRaises(DemoExportError) as caught:
                inspect_value('fabricated_field', value)
            self.assertNotIn(str(value), str(caught.exception))
        for value in ('P00000001','A000000001','TL0000000001','2026-09-30','Analyst',None,0,-42.5):
            inspect_value('fabricated_field', value)
        inspect_value('payment_pattern','1'*24)

    def test_csv_preserves_synthetic_keys_nulls_and_exact_row_counts(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)/'PERSON.csv'
            result = write_csv(path,['PARTY_ID','example','amount'],
                [('P00000001','a,b',0),('P00000002',None,-1.25)],2)
            with path.open(newline='') as stream:
                rows = list(csv.reader(stream))
            self.assertEqual(rows[1],['P00000001','a,b','0'])
            self.assertEqual(rows[2],['P00000002','\\N','-1.25'])
            self.assertEqual(result['bytes'],path.stat().st_size)
            self.assertEqual(result['rows'],2)
            with self.assertRaises(FileExistsError):
                write_csv(path,['PARTY_ID'],[],0)

    def test_missing_rows_and_export_budgets_fail(self):
        with TemporaryDirectory() as directory:
            for name,rows,count,budget in [('missing',[],1,100),('budget',[('P00000001',)],1,2)]:
                with self.subTest(name=name), self.assertRaises(DemoExportError):
                    write_csv(Path(directory)/(name+'.csv'),['PARTY_ID'],rows,count,byte_budget=budget)

    def test_archive_has_exactly_six_csvs_dictionary_and_metadata_and_retains_review(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            manifests = [write_csv(folder/(table+'.csv'),['fabricated_key'],[('P00000001',)],1) for table in TABLES]
            metadata = {'release_mode':'DEMO_ONLY','privacy_status':'REVIEW_REQUIRED','seed':42}
            result = build_archive(folder,manifests,metadata,'# Fabricated dictionary')
            with zipfile.ZipFile(folder/result['file']) as bundle:
                self.assertEqual(set(bundle.namelist()),{t+'.csv' for t in TABLES}|{'metadata.json','data_dictionary.md'})
                self.assertEqual(json.loads(bundle.read('metadata.json'))['privacy_status'],'REVIEW_REQUIRED')
            self.assertGreater(result['bytes'],0)

    def test_archive_rejects_changed_or_missing_csv(self):
        with TemporaryDirectory() as directory:
            folder=Path(directory)
            manifests=[write_csv(folder/(table+'.csv'),['fabricated_key'],[],0) for table in TABLES]
            with self.assertRaises(DemoExportError):
                build_archive(folder,manifests[:-1],{},'')
            (folder/manifests[0]['file']).write_text('changed')
            with self.assertRaises(DemoExportError):
                build_archive(folder,manifests,{},'')

    def test_zip_never_uses_random_writes_on_the_destination_volume(self):
        with TemporaryDirectory() as directory:
            folder=Path(directory)
            manifests=[write_csv(folder/(table+'.csv'),['fabricated_key'],[],0) for table in TABLES]
            real_zip=zipfile.ZipFile
            def volume_zip(path,mode='r',**kwargs):
                if Path(path).parent==folder and mode!='r':
                    raise OSError(5,'Fabricated Volume does not permit ZIP seek writes')
                return real_zip(path,mode,**kwargs)
            with patch('synthetic_banking.demo_export.zipfile.ZipFile',side_effect=volume_zip):
                result=build_archive(folder,manifests,{'release_mode':'DEMO_ONLY'},'Fabricated dictionary')
            self.assertGreater(result['bytes'],0)

    def test_uncertain_provenance_stops_before_any_export_directory(self):
        spark=Mock(); spark.conf.get.return_value='UTC'
        with patch('synthetic_banking.demo_export._context',side_effect=DemoExportError('uncertain_provenance')),patch(
                'synthetic_banking.demo_export.Path.mkdir') as mkdir:
            with self.assertRaisesRegex(DemoExportError,'uncertain_provenance'):
                export_demo_dataset(spark,release_mode='DEMO_ONLY',dataset_version='sage-demo-v999',
                    source_run_id='fabricated-source',batch_id='fabricated-batch',generation_id='fabricated-generation',
                    generated_run_id='fabricated-generated',privacy_assessment_id='fabricated-privacy')
            mkdir.assert_not_called()

    def test_private_export_is_not_a_publisher_asset_or_main_pipeline_task(self):
        root=Path(__file__).resolve().parents[1]
        publication=(root/'.github/workflows/publish-showcase.yml').read_text()
        main=(root/'resources/synthetic_pipeline.job.yml').read_text()
        self.assertNotIn('DEMO_ONLY',main)
        self.assertNotIn('demo_dataset_exports',publication)
        self.assertNotIn('08_Demo_Dataset_Export',main)
        demo=(root/'resources/demo_dataset_export.job.yml').read_text()
        self.assertIn('default: DISABLED',demo)
        for name in ('release_mode','dataset_version','source_run_id','batch_id','generation_id','generated_run_id','privacy_assessment_id'):
            self.assertIn('{{job.parameters.'+name+'}}',demo)
