"""Run-scoped handoff for the existing verified fabricated demo exporter.

No generation formulas or privacy decisions live here. Readiness is written last.
"""
import hashlib
import json
from pathlib import Path
import shutil

from synthetic_banking.config import PROFILE_SCHEMA
from synthetic_banking.demo_export import export_demo_dataset, EXPORT_ROOT, digest_file, _context, fail
from synthetic_banking.demo_downloads import prepare_download_manifest
from synthetic_banking.workflow import required_id

IDS = ('source_run_id', 'batch_id', 'generation_id', 'generated_run_id', 'privacy_assessment_id')


def execution_directory(report_output_dir, workflow_run_id):
    if not isinstance(workflow_run_id, str) or not workflow_run_id.isascii() or not workflow_run_id.isdigit():
        fail('numeric_workflow_run_id_required')
    base = Path(report_output_dir)
    if not str(base).startswith('/Volumes/') or '..' in base.parts or len(base.parts) < 5:
        fail('reporting_volume_required')
    return base / 'runs' / workflow_run_id


def dataset_version(ids):
    # Public dataset version is opaque; do not put private workflow UUIDs in URLs.
    digest = hashlib.sha256(json.dumps({k: ids[k] for k in IDS}, sort_keys=True).encode()).hexdigest()
    return 'sage-demo-v' + str(int(digest[:24], 16))


def verify_demo_stage(spark, *, release_mode, report_output_dir, workflow_run_id, validation_status, **ids):
    if release_mode == 'DISABLED':
        return dict(status='DISABLED', dataset_version='')
    if release_mode != 'DEMO_ONLY' or validation_status != 'PASS' or set(ids) != set(IDS):
        fail('explicit_validated_demo_mode_required')
    ids = {k: required_id(v, k) for k, v in ids.items()}
    destination = execution_directory(report_output_dir, workflow_run_id) / 'demo'
    version = dataset_version(ids)
    # A repair reuses only this same generation's immutable, independently rechecked export.
    _context(spark, ids)
    if (Path(EXPORT_ROOT) / version).exists():
        rows = [r.asDict() for r in spark.sql(f'''SELECT manifest_json FROM {PROFILE_SCHEMA}.demo_dataset_exports
            WHERE dataset_version=:version''', args={'version': version}).collect()]
        if len(rows) != 1:
            fail('demo_repair_requires_one_completed_export')
        record = json.loads(rows[0]['manifest_json'])
        if any(record.get(k) != v for k, v in ids.items()):
            fail('demo_export_lineage_mismatch')
    else:
        record = export_demo_dataset(spark, release_mode=release_mode, dataset_version=version, **ids)
    manifest = prepare_download_manifest(spark, record['export_id'], version)
    source = Path(EXPORT_ROOT) / version
    destination.mkdir(parents=True, exist_ok=True)
    ready = destination / '_READY.json'
    ready.unlink(missing_ok=True)
    for asset in [*manifest['assets'], dict(file='demo-preview.json', sha256=manifest['preview_sha256'])]:
        target = destination / asset['file']
        with (source / asset['file']).open('rb') as incoming, target.open('wb') as outgoing:
            shutil.copyfileobj(incoming, outgoing, 1024*1024)
        if digest_file(target) != asset['sha256'] or ('bytes' in asset and target.stat().st_size != asset['bytes']):
            fail('demo_transport_copy_mismatch')
    (destination / 'dataset-downloads.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    from synthetic_banking.demo_artifact_validation import verify_demo_package
    verify_demo_package(destination, manifest)
    # Recheck current lineage after copies; partial copies never receive readiness.
    _context(spark, ids)
    ready.write_text(json.dumps(dict(schema_version='1.0', ids=ids, dataset_version=version,
        manifest_sha256=digest_file(destination / 'dataset-downloads.json')))+'\n', encoding='utf-8')
    return dict(status='VERIFIED_DEMO_ONLY', dataset_version=version)


def reporting_demo_context(report_output_dir, workflow_run_id, status, expected_version, ids, include_manifest_hash=False):
    """Rebind every handoff ID before adding a public dataset reference to a report."""
    if status == 'DISABLED' and expected_version == '':
        return (None, None) if include_manifest_hash else None
    if status != 'VERIFIED_DEMO_ONLY' or set(ids) != set(IDS):
        fail('verified_demo_handoff_required')
    folder = execution_directory(report_output_dir, workflow_run_id) / 'demo'
    ready = json.loads((folder / '_READY.json').read_text(encoding='utf-8'))
    manifest_path = folder / 'dataset-downloads.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if (ready.get('ids') != ids or ready.get('dataset_version') != expected_version or
            expected_version != dataset_version(ids) or manifest.get('dataset_version') != expected_version or
            manifest.get('publication_status') != 'UNPUBLISHED' or
            ready.get('manifest_sha256') != digest_file(manifest_path)):
        fail('demo_reporting_lineage_mismatch')
    for asset in [*manifest['assets'], dict(file='demo-preview.json', sha256=manifest['preview_sha256'])]:
        if digest_file(folder / asset['file']) != asset['sha256']:
            fail('demo_reporting_artifact_changed')
    reference = dict(dataset_version=expected_version, release_mode='DEMO_ONLY',
                     preview_sha256=manifest['preview_sha256'])
    return (reference, ready['manifest_sha256']) if include_manifest_hash else reference
