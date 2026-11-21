"""Aggregate integrity checks on an already origin-verified fabricated CSV package.

Never use this as a replacement for fabricated-origin replay or privacy screening.
No records or matching values are returned, logged, or included in errors.
"""
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import zipfile

TABLES = ('PERSON','CUSTOMER_ACCOUNT_REL','CUSTOMER_RELATIONSHIP','TKQ_ACCOUNT','TKQ_ACCOUNT_BALANCE','TRADELINES')


def _require(condition):
    if not condition:
        raise ValueError('verified_demo_package_integrity_failed')


def _digest(stream):
    digest=hashlib.sha256()
    for block in iter(lambda:stream.read(1024*1024),b''):
        digest.update(block)
    return digest.hexdigest()


def verify_demo_package(folder, manifest):
    """Verify all six file counts, references, ZIP members and preview values."""
    folder=Path(folder)
    _require(manifest.get('release_mode')=='DEMO_ONLY' and manifest.get('verification')=='VERIFIED_DEMO_ONLY')
    _require(len(manifest['assets'])==8)
    expected={t+'.csv' for t in TABLES}|{'SAGE_DEMO_ONLY.zip','data_dictionary.md'}
    _require({a['file'] for a in manifest['assets']}==expected)
    assets={a['key']:a for a in manifest['assets']}
    for asset in assets.values():
        file=folder/asset['file']
        _require(file.is_file() and not file.is_symlink() and file.stat().st_size==asset['bytes'])
        with file.open('rb') as stream:_require(_digest(stream)==asset['sha256'])
    preview_path=folder/'demo-preview.json'
    _require(preview_path.stat().st_size<=96*1024)
    with preview_path.open('rb') as stream:_require(_digest(stream)==manifest['preview_sha256'])
    preview=json.loads(preview_path.read_text(encoding='utf-8'))
    _require(preview['dataset_version']==manifest['dataset_version'] and preview['release_mode']=='DEMO_ONLY' and
             preview['privacy_status']==manifest['privacy_status'] and len(preview['tables'])==6)
    previews={t['name']:t for t in preview['tables']}
    _require(set(previews)==set(TABLES))
    people=set();accounts=set();account_keys=set();balance_keys=set();tradelines=set();counts={}
    # Parent entities first. Only keys and the bounded preview comparison are kept.
    for table in ('PERSON','TKQ_ACCOUNT','TKQ_ACCOUNT_BALANCE','CUSTOMER_ACCOUNT_REL','CUSTOMER_RELATIONSHIP','TRADELINES'):
        p=previews[table];count=0
        with (folder/(table+'.csv')).open(encoding='utf-8',newline='') as stream:
            reader=csv.DictReader(stream)
            _require(reader.fieldnames and len(set(reader.fieldnames))==len(reader.fieldnames) and set(p['columns']).issubset(reader.fieldnames))
            for row in reader:
                _require(None not in row and None not in row.values())
                if count<len(p['rows']):
                    _require(len(p['rows'][count])==len(p['columns']))
                    for col,value in zip(p['columns'],p['rows'][count]):
                        if value is None:_require(row[col]=='\\N')
                        elif type(value) in (int,float):
                            try:_require(Decimal(row[col])==Decimal(str(value)))
                            except InvalidOperation:raise ValueError('verified_demo_package_integrity_failed') from None
                        else:_require(row[col]==str(value))
                if table=='PERSON':
                    key=row['PARTY_ID'];_require(re.fullmatch(r'P[0-9]{8}',key) and key not in people);people.add(key)
                elif table=='TKQ_ACCOUNT':
                    key=row['ACCOUNT_ID'];snapshot=(key,row['BUSINESSEFFECTIVEDATE'])
                    _require(re.fullmatch(r'A[0-9]{9}',key) and snapshot[1] not in ('','\\N') and snapshot not in account_keys)
                    accounts.add(key);account_keys.add(snapshot)
                elif table=='TKQ_ACCOUNT_BALANCE':
                    snapshot=(row['ACCOUNT_ID'],row['BUSINESSEFFECTIVEDATE'])
                    _require(snapshot in account_keys and snapshot not in balance_keys);balance_keys.add(snapshot)
                elif table=='CUSTOMER_ACCOUNT_REL':_require(row['PARTY_ID'] in people and row['ACCT_ID'] in accounts)
                elif table=='CUSTOMER_RELATIONSHIP':_require(row['FROM_PARTY_ID'] in people and row['TO_PARTY_ID'] in people)
                else:
                    key=row['account_number'];_require(row['REQ-CIF-KEY'] in people and re.fullmatch(r'TL[0-9]{10}',key) and key not in tradelines);tradelines.add(key)
                count+=1;_require(count<=250000)
        _require(count==assets[table]['rows']==p['total_rows'] and len(p['rows'])==min(15,count))
        counts[table]=count
    _require(account_keys==balance_keys)
    with zipfile.ZipFile(folder/'SAGE_DEMO_ONLY.zip') as archive:
        expected_members={t+'.csv' for t in TABLES}|{'data_dictionary.md','metadata.json'}
        _require(len(archive.namelist())==8 and set(archive.namelist())==expected_members)
        for asset in assets.values():
            if asset['key']=='ZIP':continue
            _require(archive.getinfo(asset['file']).file_size==asset['bytes'])
            with archive.open(asset['file']) as stream:_require(_digest(stream)==asset['sha256'])
        _require(archive.getinfo('metadata.json').file_size<=32*1024)
        metadata=json.loads(archive.read('metadata.json'))
        _require(metadata['release_mode']=='DEMO_ONLY' and metadata['dataset_version']==manifest['dataset_version'] and
                 metadata['privacy_status']==manifest['privacy_status'] and metadata['table_counts']==counts)
    return dict(status='PASS',table_counts=counts,account_balance_join_coverage=1.0 if account_keys else None,
                orphan_references=0,preview_matches_csv=True,zip_members_verified=8)
