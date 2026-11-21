"""Fabricated export handoffs: no Spark generation or public network calls."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

from synthetic_banking.demo_workflow import IDS, dataset_version, verify_demo_stage, reporting_demo_context, execution_directory
from synthetic_banking.demo_export import DemoExportError
from scripts.publish_showcase import ROOT, retrieve_demo


def fixture(folder):
    manifest=json.loads((ROOT/'docs/dataset-downloads.json').read_text())
    manifest.update(publication_status='UNPUBLISHED',publication_checked_at=None)
    manifest.pop('download_urls',None)
    preview=b'{"fabricated_test_only":true}\n'
    manifest['preview_sha256']=hashlib.sha256(preview).hexdigest()
    (folder/'demo-preview.json').write_bytes(preview)
    for asset in manifest['assets']:
        content=('Fabricated fixture '+asset['file']).encode()
        (folder/asset['file']).write_bytes(content)
        asset.update(bytes=len(content),sha256=hashlib.sha256(content).hexdigest())
    return manifest


class DemoWorkflowTests(TestCase):
    def setUp(self):
        self.ids={key:'fabricated-'+key for key in IDS}
        check=patch('synthetic_banking.demo_artifact_validation.verify_demo_package')
        check.start();self.addCleanup(check.stop)

    def test_disabled_mode_does_not_touch_source_tables_or_files(self):
        with patch('synthetic_banking.demo_workflow._context') as context:
            result=verify_demo_stage(None,release_mode='DISABLED',report_output_dir='',workflow_run_id='',validation_status='PASS')
            self.assertEqual(result,dict(status='DISABLED',dataset_version=''))
            context.assert_not_called()
        for mode,status in (('DEMO_ONLY','FAIL'),('DEMO','PASS'),('PRODUCTION','PASS')):
            with self.assertRaises(DemoExportError):
                verify_demo_stage(None,release_mode=mode,report_output_dir='',workflow_run_id='',validation_status=status,**self.ids)

    def test_execution_paths_and_versions_do_not_leak_private_identifiers(self):
        version=dataset_version(self.ids)
        self.assertEqual(version,dataset_version(dict(reversed(list(self.ids.items())))))
        self.assertNotEqual(version,dataset_version({**self.ids,'generation_id':'different'}))
        for private in self.ids.values():self.assertNotIn(private,version)
        for base,run in (('/Volumes/c/s/v/../private','20'),('/tmp/report','20'),('/Volumes/c/s/v','../20')):
            with self.assertRaises(DemoExportError):execution_directory(base,run)

    def test_exact_validated_ids_are_reused_and_readiness_binds_every_file(self):
        with TemporaryDirectory() as temp:
            root=Path(temp);private=root/'private';private.mkdir();execution=root/'run';execution.mkdir()
            version=dataset_version(self.ids);folder=private/version;folder.mkdir();manifest=fixture(folder)
            manifest['dataset_version']=version
            record={'export_id':'fabricated-export',**self.ids}
            spark=Mock();spark.sql.return_value.collect.return_value=[Mock(asDict=lambda:{'manifest_json':json.dumps(record)})]
            with patch('synthetic_banking.demo_workflow.EXPORT_ROOT',str(private)),patch('synthetic_banking.demo_workflow.execution_directory',return_value=execution),patch('synthetic_banking.demo_workflow._context') as context,patch('synthetic_banking.demo_workflow.export_demo_dataset') as export,patch('synthetic_banking.demo_workflow.prepare_download_manifest',return_value=manifest) as prepare:
                for _ in range(2):
                    result=verify_demo_stage(spark,release_mode='DEMO_ONLY',report_output_dir='ignored',workflow_run_id='20',validation_status='PASS',**self.ids)
                    self.assertEqual(result['status'],'VERIFIED_DEMO_ONLY')
                    reference=reporting_demo_context('ignored','20',result['status'],version,self.ids)
                    self.assertEqual(reference['preview_sha256'],manifest['preview_sha256'])
                export.assert_not_called();prepare.assert_called_with(spark,'fabricated-export',version)
                self.assertEqual(context.call_count,4)
                for key in IDS:
                    with self.assertRaises(DemoExportError):reporting_demo_context('ignored','20',result['status'],version,{**self.ids,key:'wrong'})
                (execution/'demo/PERSON.csv').write_text('changed')
                with self.assertRaises(DemoExportError):reporting_demo_context('ignored','20',result['status'],version,self.ids)
                bad={**record,'generation_id':'wrong'}
                spark.sql.return_value.collect.return_value=[Mock(asDict=lambda:{'manifest_json':json.dumps(bad)})]
                with self.assertRaises(DemoExportError):verify_demo_stage(spark,release_mode='DEMO_ONLY',report_output_dir='ignored',workflow_run_id='20',validation_status='PASS',**self.ids)

    def test_no_readiness_when_reproduction_or_final_lineage_verification_fails(self):
        with TemporaryDirectory() as temp:
            root=Path(temp);private=root/'private';private.mkdir();execution=root/'run';execution.mkdir()
            version=dataset_version(self.ids);folder=private/version;folder.mkdir();manifest=fixture(folder);manifest['dataset_version']=version
            spark=Mock();record={'export_id':'fabricated-export',**self.ids}
            spark.sql.return_value.collect.return_value=[Mock(asDict=lambda:{'manifest_json':json.dumps(record)})]
            with patch('synthetic_banking.demo_workflow.EXPORT_ROOT',str(private)),patch('synthetic_banking.demo_workflow.execution_directory',return_value=execution),patch('synthetic_banking.demo_workflow.prepare_download_manifest',return_value=manifest),patch('synthetic_banking.demo_workflow._context',side_effect=[None,DemoExportError('changed')]):
                with self.assertRaises(DemoExportError):verify_demo_stage(spark,release_mode='DEMO_ONLY',report_output_dir='ignored',workflow_run_id='20',validation_status='PASS',**self.ids)
                self.assertFalse((execution/'demo/_READY.json').exists())

    def test_new_export_calls_existing_exporter_with_all_exact_ids(self):
        with TemporaryDirectory() as temp:
            root=Path(temp);private=root/'private';private.mkdir();execution=root/'run';execution.mkdir()
            version=dataset_version(self.ids);manifest=None
            def export(spark,**parameters):
                nonlocal manifest
                folder=private/version;folder.mkdir();manifest=fixture(folder);manifest['dataset_version']=version
                return {'export_id':'new-fabricated-export',**self.ids}
            with patch('synthetic_banking.demo_workflow.EXPORT_ROOT',str(private)),patch('synthetic_banking.demo_workflow.execution_directory',return_value=execution),patch('synthetic_banking.demo_workflow._context'),patch('synthetic_banking.demo_workflow.export_demo_dataset',side_effect=export) as generate,patch('synthetic_banking.demo_workflow.prepare_download_manifest',side_effect=lambda *args:manifest):
                result=verify_demo_stage(None,release_mode='DEMO_ONLY',report_output_dir='ignored',workflow_run_id='20',validation_status='PASS',**self.ids)
                generate.assert_called_once_with(None,release_mode='DEMO_ONLY',dataset_version=version,**self.ids)
                self.assertEqual(result['dataset_version'],version)
                public,checksum=reporting_demo_context('ignored','20',result['status'],version,self.ids,include_manifest_hash=True)
                self.assertEqual(public['dataset_version'],version)
                self.assertEqual(len(checksum),64)

    def test_publisher_retrieves_only_run_scoped_verified_files_and_rejects_mismatches(self):
        from io import BytesIO
        from types import SimpleNamespace
        with TemporaryDirectory() as temp:
            folder=Path(temp);manifest=fixture(folder)
            report=json.loads((ROOT/'docs/reporting/example.json').read_text())
            report['privacy']={'status':manifest['privacy_status']}
            report['demo_dataset']={k:manifest[k] for k in ('dataset_version','release_mode','preview_sha256')}
            for row in report['generation']['table_rows']:
                row['status']='AVAILABLE';row['value']=next(a['rows'] for a in manifest['assets'] if a['key']==row['table'])
            payloads={a['file']:(folder/a['file']).read_bytes() for a in manifest['assets']}
            payloads.update({'dataset-downloads.json':json.dumps(manifest).encode(),'demo-preview.json':(folder/'demo-preview.json').read_bytes()})
            calls=[]
            def download(p):
                calls.append(p);return SimpleNamespace(contents=BytesIO(payloads[Path(p).name]))
            client=SimpleNamespace(files=SimpleNamespace(download=download))
            receipt={'demo_export_status':'VERIFIED_DEMO_ONLY','demo_manifest_sha256':hashlib.sha256(payloads['dataset-downloads.json']).hexdigest()}
            retrieve_demo(client,report,{'run_id':20},receipt,'/Volumes/c/s/reports',folder/'incoming')
            self.assertEqual(len(calls),10)
            self.assertTrue(all(p.startswith('/Volumes/c/s/reports/runs/20/demo/') for p in calls))
            bad=deepcopy(report);bad['demo_dataset']['dataset_version']='sage-demo-v2'
            with self.assertRaises(ValueError):retrieve_demo(client,bad,{'run_id':20},receipt,'/Volumes/c/s/reports',folder/'bad')
            payloads['PERSON.csv']=b'changed'
            with self.assertRaises(ValueError):retrieve_demo(client,report,{'run_id':20},receipt,'/Volumes/c/s/reports',folder/'changed')
