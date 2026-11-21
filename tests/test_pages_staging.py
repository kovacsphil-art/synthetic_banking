"""Deployment-package checks use fabricated public contract data, never live credentials."""
from copy import deepcopy
import hashlib
import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.stage_showcase import STATIC_FILES, DEMO_FILES, stage_site, ROOT
from synthetic_banking.demo_preview import SPEC


def fixture(source):
    source.mkdir()
    for name in STATIC_FILES:
        (source/name).write_bytes((ROOT/'docs'/name).read_bytes())
    report=json.loads((ROOT/'docs/reporting/example-postpilot.json').read_bytes())
    (source/'latest-pipeline.json').write_text(json.dumps(report),encoding='utf-8')
    return report


def demo(source, report):
    counts={r['table']:r['value'] for r in report['generation']['table_rows']}
    values={'person_id':'P00000001','account_id':'A000000001','tradeline_id':'TL0000000001','code':'A','number':100,'date':'2026-01-01T00:00:00'}
    preview=dict(schema_version='1.0',release_mode='DEMO_ONLY',baseline='FABRICATED_DEVELOPMENT',dataset_version='sage-demo-v123',
        generated_at='2026-01-01T01:00:00Z',privacy_status=report['privacy']['status'],preview_row_limit=15,
        tables=[dict(name=name,total_rows=counts[name],total_columns=spec['total_columns'],columns=[c['key'] for c in spec['columns']],
            rows=[[values[c['kind']] for c in spec['columns']] for _ in range(min(15,counts[name]))]) for name,spec in SPEC.items()])
    raw=json.dumps(preview).encode();(source/'demo-preview.json').write_bytes(raw)
    assets=[('ZIP','SAGE_DEMO_ONLY.zip'),('DICTIONARY','data_dictionary.md'),*((name,name+'.csv') for name in SPEC)]
    manifest=dict(schema_version='1.0',release_mode='DEMO_ONLY',baseline='FABRICATED_DEVELOPMENT',verification='VERIFIED_DEMO_ONLY',
        dataset_version=preview['dataset_version'],generation_date='2026-01-01T00:00:00Z',exported_at=preview['generated_at'],verified_at='2026-01-01T02:00:00Z',
        privacy_status=preview['privacy_status'],preview_sha256=hashlib.sha256(raw).hexdigest(),repository='kovacsphil-art/synthetic_banking',
        publication_status='PUBLISHED',publication_checked_at='2026-01-01T03:00:00Z',
        assets=[dict(key=key,file=name,bytes=1000+i,sha256='a'*64,rows=counts.get(key)) for i,(key,name) in enumerate(assets)])
    manifest['download_urls']={a['key']:'https://github.com/'+manifest['repository']+'/releases/download/'+manifest['dataset_version']+'/'+a['file'] for a in manifest['assets']}
    (source/'dataset-downloads.json').write_text(json.dumps(manifest),encoding='utf-8')
    report['demo_dataset']={key:manifest[key] for key in ('dataset_version','release_mode','preview_sha256')}
    (source/'latest-pipeline.json').write_text(json.dumps(report),encoding='utf-8')
    return manifest


class PagesStagingTests(unittest.TestCase):
    def test_aggregate_only_package_has_exact_allowlist_and_no_demo_or_row_files(self):
        with TemporaryDirectory() as temp:
            root=Path(temp);source=root/'docs';report=fixture(source);demo(source,report)
            for name in ('PERSON.csv','source.parquet','private.env','SAGE_DEMO_ONLY.zip','example.json'):
                (source/name).write_text('FABRICATED_NOT_FOR_PAGES')
            target=root/'site';result=stage_site(source,target)
            self.assertEqual({p.name for p in target.iterdir()},set(STATIC_FILES)|{'latest-pipeline.json','.nojekyll'})
            self.assertFalse(result['demo_metadata_included'])
            self.assertEqual(json.loads((target/'latest-pipeline.json').read_bytes()),report)

    def test_verified_demo_stages_only_matching_bounded_preview_and_manifest(self):
        with TemporaryDirectory() as temp:
            root=Path(temp);source=root/'docs';report=fixture(source);manifest=demo(source,report)
            result=stage_site(source,root/'site',include_demo=True)
            self.assertTrue(result['demo_metadata_included'])
            self.assertEqual({p.name for p in (root/'site').iterdir()},set(STATIC_FILES)|set(DEMO_FILES)|{'latest-pipeline.json','.nojekyll'})
            self.assertEqual(hashlib.sha256((root/'site/demo-preview.json').read_bytes()).hexdigest(),manifest['preview_sha256'])
            self.assertEqual(json.loads((root/'site/latest-pipeline.json').read_bytes())['privacy']['status'],'REVIEW_REQUIRED')

    def test_unverified_mixed_generation_withdrawn_and_foreign_demo_links_stop_before_staging(self):
        for change in ('version','hash','count','privacy','withdrawn','url','source'):
            with self.subTest(change=change),TemporaryDirectory() as temp:
                root=Path(temp);source=root/'docs';report=fixture(source);m=demo(source,report)
                if change=='version':m['dataset_version']='sage-demo-v456'
                if change=='hash':m['preview_sha256']='f'*64
                if change=='count':m['assets'][2]['rows']+=1
                if change=='privacy':m['privacy_status']='PASS'
                if change=='withdrawn':m['publication_status']='WITHDRAWN'
                if change=='url':m['download_urls']['PERSON']='https://private.invalid/source.csv'
                if change=='source':m['baseline']='PRODUCTION'
                (source/'dataset-downloads.json').write_text(json.dumps(m),encoding='utf-8')
                with self.assertRaises(ValueError):stage_site(source,root/'site',include_demo=True)
                self.assertFalse((root/'site').exists())

    def test_private_report_payloads_are_rejected_and_warning_text_is_sanitized(self):
        with TemporaryDirectory() as temp:
            root=Path(temp);source=root/'docs';report=fixture(source)
            report['source_rows']=['PRIVATE'];(source/'latest-pipeline.json').write_text(json.dumps(report))
            with self.assertRaises(ValueError):stage_site(source,root/'blocked')
            report.pop('source_rows');report['warnings'][0]['message']='PRIVATE_WARNING'
            (source/'latest-pipeline.json').write_text(json.dumps(report));stage_site(source,root/'site')
            self.assertNotIn('PRIVATE_WARNING',(root/'site/latest-pipeline.json').read_text())

    def test_missing_external_and_removed_required_assets_prevent_a_usable_package(self):
        for mode in ('missing','external','removed'):
            with self.subTest(mode=mode),TemporaryDirectory() as temp:
                root=Path(temp);source=root/'docs';fixture(source)
                if mode=='missing':(source/'styles.css').unlink()
                else:
                    html=(source/'index.html').read_text()
                    html=html+'<script src="https://private.invalid/script.js"></script>' if mode=='external' else re.sub(r'<script src="validation\.js[^\"]*" defer></script>','',html)
                    (source/'index.html').write_text(html)
                with self.assertRaises(ValueError):stage_site(source,root/'site')
                self.assertFalse((root/'site').exists())

    def test_existing_destination_is_never_overwritten(self):
        with TemporaryDirectory() as temp:
            root=Path(temp);source=root/'docs';fixture(source);target=root/'site';target.mkdir()
            previous=b'PREVIOUS_PUBLISHED_BYTES';(target/'index.html').write_bytes(previous)
            with self.assertRaises(ValueError):stage_site(source,target)
            self.assertEqual((target/'index.html').read_bytes(),previous)

    def test_workflow_checks_precede_commit_and_deployment_and_keep_both_triggers(self):
        workflow=(ROOT/'.github/workflows/publish-showcase.yml').read_text()
        for marker in ('workflow_dispatch:','schedule:','cancel-in-progress: false','test_pages_staging.py','node --test'):
            self.assertIn(marker,workflow)
        self.assertLess(workflow.index('Stage and check the exact public artifact'),workflow.index('Commit only verified public'))
        self.assertLess(workflow.index('Check staged browser contract'),workflow.index('actions/upload-pages-artifact'))
        self.assertIn('needs: prepare',workflow);self.assertIn("if: needs.prepare.outputs.ready == 'true'",workflow)


if __name__=='__main__':unittest.main()
