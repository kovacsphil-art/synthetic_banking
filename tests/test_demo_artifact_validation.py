"""CSV/ZIP/preview validation uses deliberately tiny fabricated records."""
import csv
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
import zipfile

from synthetic_banking.demo_artifact_validation import verify_demo_package, TABLES


def fixture(folder, mutation=None):
    rows={'PERSON':[{'PARTY_ID':'P00000001'},{'PARTY_ID':'P00000002'}],
          'TKQ_ACCOUNT':[{'ACCOUNT_ID':'A000000001','BUSINESSEFFECTIVEDATE':'2026-01-01'}],
          'TKQ_ACCOUNT_BALANCE':[{'ACCOUNT_ID':'A000000001','BUSINESSEFFECTIVEDATE':'2026-01-01'}],
          'CUSTOMER_ACCOUNT_REL':[{'PARTY_ID':'P00000001','ACCT_ID':'A000000001'}],
          'CUSTOMER_RELATIONSHIP':[{'FROM_PARTY_ID':'P00000001','TO_PARTY_ID':'P00000002'}],
          'TRADELINES':[{'account_number':'TL0000000001','REQ-CIF-KEY':'P00000002'}]}
    if mutation:mutation(rows)
    for table in TABLES:
        with (folder/(table+'.csv')).open('w',encoding='utf-8',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[table][0]));writer.writeheader();writer.writerows(rows[table])
    counts={t:len(rows[t]) for t in TABLES}
    preview=dict(dataset_version='sage-demo-v123',release_mode='DEMO_ONLY',privacy_status='REVIEW_REQUIRED',
        tables=[dict(name=t,total_rows=counts[t],columns=list(rows[t][0]),rows=[list(r.values()) for r in rows[t]]) for t in TABLES])
    raw=json.dumps(preview).encode();(folder/'demo-preview.json').write_bytes(raw)
    (folder/'data_dictionary.md').write_text('Fabricated test dictionary')
    metadata=dict(release_mode='DEMO_ONLY',dataset_version='sage-demo-v123',privacy_status='REVIEW_REQUIRED',table_counts=counts)
    with zipfile.ZipFile(folder/'SAGE_DEMO_ONLY.zip','w') as archive:
        for name in [*(t+'.csv' for t in TABLES),'data_dictionary.md']:archive.write(folder/name,name)
        archive.writestr('metadata.json',json.dumps(metadata))
    manifest=dict(release_mode='DEMO_ONLY',verification='VERIFIED_DEMO_ONLY',dataset_version='sage-demo-v123',privacy_status='REVIEW_REQUIRED',
        preview_sha256=hashlib.sha256(raw).hexdigest(),assets=[])
    for key,name in [('ZIP','SAGE_DEMO_ONLY.zip'),('DICTIONARY','data_dictionary.md'),*((t,t+'.csv') for t in TABLES)]:
        content=(folder/name).read_bytes();manifest['assets'].append(dict(key=key,file=name,bytes=len(content),sha256=hashlib.sha256(content).hexdigest(),rows=counts.get(key)))
    return manifest


class DemoArtifactValidationTests(TestCase):
    def test_all_six_csvs_zip_preview_and_references_agree(self):
        with TemporaryDirectory() as temp:
            folder=Path(temp);manifest=fixture(folder);result=verify_demo_package(folder,manifest)
            self.assertEqual(result['status'],'PASS');self.assertEqual(result['orphan_references'],0)
            self.assertEqual(result['account_balance_join_coverage'],1);self.assertTrue(result['preview_matches_csv'])
            self.assertEqual(result['zip_members_verified'],8)

    def test_rehashed_and_consistent_archives_with_invalid_references_still_fail(self):
        for mutate in (lambda r:r['CUSTOMER_ACCOUNT_REL'][0].update(PARTY_ID='P99999999'),
                       lambda r:r['CUSTOMER_ACCOUNT_REL'][0].update(ACCT_ID='A999999999'),
                       lambda r:r['CUSTOMER_RELATIONSHIP'][0].update(TO_PARTY_ID='P99999999'),
                       lambda r:r['TRADELINES'][0].update(**{'REQ-CIF-KEY':'P99999999'}),
                       lambda r:r['TKQ_ACCOUNT_BALANCE'][0].update(BUSINESSEFFECTIVEDATE='2026-01-02'),
                       lambda r:r['PERSON'].append(r['PERSON'][0].copy())):
            with TemporaryDirectory() as temp:
                folder=Path(temp);manifest=fixture(folder,mutate)
                with self.assertRaisesRegex(ValueError,'integrity_failed'):verify_demo_package(folder,manifest)

    def test_changed_preview_values_version_and_zip_bytes_fail(self):
        for version in (True,False):
            with TemporaryDirectory() as temp:
                folder=Path(temp);manifest=fixture(folder);preview=json.loads((folder/'demo-preview.json').read_bytes())
                if version:preview['dataset_version']='sage-demo-v999'
                else:preview['tables'][0]['rows'][0][0]='P99999999'
                raw=json.dumps(preview).encode();(folder/'demo-preview.json').write_bytes(raw);manifest['preview_sha256']=hashlib.sha256(raw).hexdigest()
                with self.assertRaises(ValueError):verify_demo_package(folder,manifest)
        with TemporaryDirectory() as temp:
            folder=Path(temp);manifest=fixture(folder);(folder/'SAGE_DEMO_ONLY.zip').write_bytes(b'changed')
            with self.assertRaises(ValueError):verify_demo_package(folder,manifest)
