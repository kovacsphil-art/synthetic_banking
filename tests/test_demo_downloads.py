"""Download provenance tests use small, fabricated files and metadata only."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
import zipfile

from synthetic_banking.demo_downloads import verify_export_files, build_download_manifest, download_schema, prepare_download_manifest
from synthetic_banking.demo_export import TABLES, digest_file, load_policy, DemoExportError


def fabricated_export(folder):
    policy=load_policy();files=[]
    for name in TABLES:
        path=folder/(name+'.csv');path.write_text('fabricated_key\nDEMO_1\n')
        files.append(dict(file=path.name,rows=1,bytes=path.stat().st_size,sha256=digest_file(path)))
    preview=folder/'demo-preview.json';preview.write_text('{"fabricated_fixture":true}')
    preview_info=dict(file=preview.name,bytes=preview.stat().st_size,sha256=digest_file(preview))
    metadata=dict(release_mode='DEMO_ONLY',dataset_version='sage-demo-v1',privacy_status='REVIEW_REQUIRED',
        generation_date='2026-01-01T00:00:00+00:00',exported_at='2026-01-01T01:00:00+00:00',
        table_counts={t:1 for t in TABLES},files=files,preview=preview_info)
    (folder/'metadata.json').write_text(json.dumps(metadata))
    (folder/'data_dictionary.md').write_text('# Fabricated dictionary\nNo customer records.\n')
    archive=folder/'SAGE_DEMO_ONLY.zip'
    with zipfile.ZipFile(archive,'x') as bundle:
        for name in [*(t+'.csv' for t in TABLES),'metadata.json','data_dictionary.md']:bundle.write(folder/name,arcname=name)
    archive_info=dict(file=archive.name,bytes=archive.stat().st_size,sha256=digest_file(archive))
    record=dict(export_id='private-id',source_run_id='private-source',release_mode='DEMO_ONLY',dataset_version='sage-demo-v1',
        privacy_status='REVIEW_REQUIRED',files=files,archive=archive_info,preview=preview_info,
        proof=dict(policy=policy['policy_version'],script_sha256=policy['generator_sha256'],
            source={t:dict(status='EXACT_REPLAY',rows=1000 if t=='PERSON' else 1) for t in TABLES},
            generated={t:dict(status='EXACT_REPLAY',rows=1) for t in TABLES}))
    (folder/'_SUCCESS').write_text(json.dumps(dict(release_mode='DEMO_ONLY',dataset_version='sage-demo-v1',
        archive_sha256=archive_info['sha256'],preview_sha256=preview_info['sha256'])))
    return record,policy


class DemoDownloadTests(unittest.TestCase):
    def test_newer_or_mismatched_privacy_evidence_stops_before_file_access(self):
        from synthetic_banking.demo_export import EXPORT_ROOT
        record=dict(export_id='fabricated-export',dataset_version='sage-demo-v1',release_mode='DEMO_ONLY',
            location=str(Path(EXPORT_ROOT)/'sage-demo-v1'),source_run_id='fabricated-source',
            generation_id='fabricated-generation',privacy_assessment_id='original-assessment',
            privacy_status='REVIEW_REQUIRED',validated_versions={'PERSON':'1'})
        audit=dict(release_mode='DEMO_ONLY',source_run_id=record['source_run_id'],generation_id=record['generation_id'],
            privacy_status='REVIEW_REQUIRED',manifest_json=json.dumps(record))
        matching=dict(assessment_id='original-assessment',source_run_id=record['source_run_id'],completed_at='2026-01-01',
            status='REVIEW_REQUIRED',generated_versions_json=json.dumps(record['validated_versions']))
        for change in ({'assessment_id':'newer-assessment','status':'BLOCKED'}, {'source_run_id':'different-source'},
                       {'completed_at':None}, {'generated_versions_json':'{"PERSON":"2"}'}):
            assessment={**matching,**change};spark=Mock()
            spark.sql.side_effect=[Mock(collect=lambda:[Mock(asDict=lambda:audit)]),
                                   Mock(collect=lambda:[Mock(asDict=lambda:assessment)])]
            with patch('synthetic_banking.demo_downloads.verify_export_files') as files:
                with self.assertRaises(DemoExportError):
                    prepare_download_manifest(spark,record['export_id'],record['dataset_version'])
                files.assert_not_called()

    def test_preparation_checks_all_assets_and_never_authorizes_publication(self):
        with TemporaryDirectory() as temporary:
            folder=Path(temporary);record,policy=fabricated_export(folder)
            metadata,dictionary=verify_export_files(record,folder,policy)
            manifest=build_download_manifest(record,metadata,dictionary)
            self.assertEqual(manifest['publication_status'],'UNPUBLISHED')
            self.assertIsNone(manifest['publication_checked_at'])
            self.assertEqual(manifest['privacy_status'],'REVIEW_REQUIRED')
            self.assertEqual(len(manifest['assets']),8)
            self.assertEqual(sum(a['rows'] or 0 for a in manifest['assets']),6)
            encoded=json.dumps(manifest)
            for excluded in ('private-id','private-source','/Volumes/','source_run_id','export_id'):
                self.assertNotIn(excluded,encoded)
            try:
                from jsonschema import Draft202012Validator,FormatChecker
            except ImportError:return
            self.assertTrue(Draft202012Validator(download_schema(),format_checker=FormatChecker()).is_valid(manifest))

    def test_missing_uncertain_provenance_wrong_mode_and_changed_artifacts_fail(self):
        mutations=(lambda r:r.update(release_mode='PRODUCTION'),lambda r:r['proof'].update(policy='unknown'),
            lambda r:r['proof']['source']['PERSON'].update(status='UNAVAILABLE'),
            lambda r:r['proof']['generated'].pop('TRADELINES'),lambda r:r['files'][0].update(file='../secret.csv'),
            lambda r:r['archive'].update(sha256='0'*64),lambda r:r.update(privacy_status='BLOCKED'))
        for mutate in mutations:
            with TemporaryDirectory() as temporary:
                folder=Path(temporary);record,policy=fabricated_export(folder);mutate(record)
                with self.assertRaises((DemoExportError,KeyError)):verify_export_files(record,folder,policy)
        for name in ('_SUCCESS','PERSON.csv','data_dictionary.md','demo-preview.json'):
            with TemporaryDirectory() as temporary:
                folder=Path(temporary);record,policy=fabricated_export(folder)
                (folder/name).write_text('tampered fabricated content')
                with self.assertRaises((DemoExportError,ValueError)):verify_export_files(record,folder,policy)

    def test_closed_public_schema_rejects_internal_paths_and_arbitrary_urls(self):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:self.skipTest('jsonschema required')
        with TemporaryDirectory() as temporary:
            folder=Path(temporary);record,policy=fabricated_export(folder)
            metadata,dictionary=verify_export_files(record,folder,policy)
            manifest=build_download_manifest(record,metadata,dictionary);validator=Draft202012Validator(download_schema())
            for mutate in (lambda r:r.update(location='/Volumes/private'),lambda r:r['assets'][0].update(url='https://private.invalid/file'),
                           lambda r:r.update(repository='attacker/other'),lambda r:r['assets'][0].update(file='source.zip')):
                bad=deepcopy(manifest);mutate(bad);self.assertFalse(validator.is_valid(bad))
