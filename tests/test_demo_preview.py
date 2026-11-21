"""All preview test records are fabricated; no SOURCE records or live access."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import unittest

from synthetic_banking.demo_preview import SPEC, ROW_LIMIT, MAX_BYTES, build_preview, preview_schema
from synthetic_banking.demo_export import DemoExportError, load_policy


class Frame:
    def __init__(self, name, rows=None, columns=None):
        self.columns=columns or list(load_policy()['columns'][name])
        self.rows=rows or []
        self.calls=[]
    def orderBy(self,*keys):
        self.calls.append(('orderBy',keys));return self
    def select(self,*columns):
        self.calls.append(('select',columns));self.selected=columns;return self
    def limit(self,n):
        self.calls.append(('limit',n));self.maximum=n;return self
    def collect(self):
        self.calls.append(('collect',));return [tuple(r.get(c) for c in self.selected) for r in self.rows[:self.maximum]]


def fabricated_preview():
    frames={}
    for name,spec in SPEC.items():
        rows=[]
        for i in range(30):
            values={'person_id':f'P{i+1:08d}','account_id':f'A{i+1:09d}','tradeline_id':f'TL{i+1:010d}',
                    'code':'A','number':100.+i,'date':'2026-09-30T00:00:00'}
            rows.append({c['key']:values[c['kind']] for c in spec['columns']})
        frames[name]=Frame(name,rows)
    raw=build_preview(frames,{name:30 for name in SPEC},dataset_version='sage-demo-v1.1',
        generated_at='2026-01-01T00:00:00+00:00',privacy_status='REVIEW_REQUIRED')
    return json.loads(raw),frames


class DemoPreviewTests(unittest.TestCase):
    def test_only_fifteen_selected_rows_per_table_are_collected(self):
        report,frames=fabricated_preview()
        self.assertLess(len(json.dumps(report).encode()),MAX_BYTES)
        self.assertEqual(report['privacy_status'],'REVIEW_REQUIRED')
        self.assertEqual(sum(len(t['rows']) for t in report['tables']),90)
        for table in report['tables']:
            self.assertEqual(table['total_rows'],30)
            self.assertEqual(len(table['rows']),ROW_LIMIT)
            self.assertEqual(table['total_columns'],SPEC[table['name']]['total_columns'])
            calls=frames[table['name']].calls
            self.assertEqual([c[0] for c in calls],['orderBy','select','limit','collect'])
            self.assertEqual(calls[2],('limit',15))
        encoded=json.dumps(report)
        for excluded in ('source_run_id','generation_id'):
            self.assertNotIn(excluded,encoded)
        for excluded in ('BIRTH_DT','SINCE_DT','GENDER_CD','OCCUP_DESC'):
            self.assertNotIn(excluded,report['tables'][0]['columns'])

    def test_schema_and_browser_catalog_have_one_source_of_truth(self):
        from synthetic_banking.demo_preview import config
        root=Path(__file__).resolve().parents[1]
        self.assertEqual(json.loads((root/'docs/reporting/demo-preview.schema.json').read_text()),preview_schema())
        text=(root/'docs/records-config.js').read_text(encoding='utf-8')
        self.assertIn(json.dumps(config(),indent=2,ensure_ascii=False),text)

    @unittest.skipUnless(importlib.util.find_spec('jsonschema'),'jsonschema required')
    def test_contract_rejects_extra_fields_source_ids_and_full_datasets(self):
        from jsonschema import Draft202012Validator,FormatChecker
        report,_=fabricated_preview();v=Draft202012Validator(preview_schema(),format_checker=FormatChecker())
        self.assertTrue(v.is_valid(report))
        for mutate in (lambda r:r.update(source_run_id='private-source'),
                       lambda r:r['tables'][0]['rows'].append(r['tables'][0]['rows'][0]),
                       lambda r:r['tables'][0]['rows'][0].__setitem__(0,'P0000000001'),
                       lambda r:r['tables'][0].update(columns=['EMAIL']),
                       lambda r:r.update(release_mode='PUBLIC')):
            bad=deepcopy(report);mutate(bad);self.assertFalse(v.is_valid(bad))

    def test_secret_content_unknown_schema_and_invalid_privacy_fail_closed(self):
        _,frames=fabricated_preview()
        for value in ('private@example.invalid','ghp_'+'a'*36,'<script>alert(1)</script>'):
            frames['PERSON'].rows[0]['CLIENT_STAT_CD']=value
            with self.assertRaises(DemoExportError):
                build_preview(frames,{n:30 for n in SPEC},dataset_version='sage-demo-v1',generated_at='2026-01-01T00:00:00Z',privacy_status='REVIEW_REQUIRED')
        _,frames=fabricated_preview();frames['PERSON'].columns.append('EMAIL')
        with self.assertRaises(DemoExportError):
            build_preview(frames,{n:30 for n in SPEC},dataset_version='sage-demo-v1',generated_at='2026-01-01T00:00:00Z',privacy_status='REVIEW_REQUIRED')
        with self.assertRaises(DemoExportError):
            build_preview(frames,{n:30 for n in SPEC},dataset_version='sage-demo-v1',generated_at='2026-01-01T00:00:00Z',privacy_status='BLOCKED')
