"""Prepare download metadata from a verified private demo export; never publishes."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import zipfile

from synthetic_banking.config import PROFILE_SCHEMA
from synthetic_banking.demo_export import TABLES, EXPORT_ROOT, MAX_TOTAL_BYTES, digest_file, load_policy, DemoExportError

REPOSITORY = "kovacsphil-art/synthetic_banking"
ASSETS = (("ZIP", "SAGE_DEMO_ONLY.zip"), ("DICTIONARY", "data_dictionary.md"),
          *((name, name+".csv") for name in TABLES))
MAX_MANIFEST_BYTES = 16 * 1024


def _require(condition):
    if not condition:
        raise DemoExportError("download_manifest_requires_verified_demo_export")


def _timestamp(value):
    _require(isinstance(value, str))
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        _require(parsed.utcoffset() is not None and parsed.utcoffset().total_seconds() == 0)
    except (TypeError, ValueError):
        raise DemoExportError("download_manifest_invalid_timestamp") from None
    return value


def _hash_stream(stream):
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024*1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def verify_export_files(record, folder, policy):
    """Verify original audit, readiness, all file bytes and ZIP members. No rows logged."""
    folder = Path(folder)
    version = record.get("dataset_version")
    _require(isinstance(version, str) and re.fullmatch(r"sage-demo-v[1-9][0-9]*(?:\.[0-9]+)*", version))
    _require(record.get("release_mode") == "DEMO_ONLY" and record.get("privacy_status") in {"PASS", "REVIEW_REQUIRED"})
    proof = record.get("proof") or {}
    _require(proof.get("policy") == policy["policy_version"] and proof.get("script_sha256") == policy["generator_sha256"])
    for key in ("source", "generated"):
        entries = proof.get(key) or {}
        _require(set(entries) == set(TABLES) and all(r.get("status") == "EXACT_REPLAY" and
            type(r.get("rows")) is int and 0 <= r["rows"] <= 250_000 for r in entries.values()))
    _require(proof["source"]["PERSON"]["rows"] == policy["source_people"])
    files = record.get("files") or []
    _require(len(files) == 6 and {r.get("file") for r in files} == {t+".csv" for t in TABLES})
    _require(all(type(r.get("bytes")) is int and 0 < r["bytes"] <= MAX_TOTAL_BYTES and
        isinstance(r.get("sha256"), str) and re.fullmatch("[0-9a-f]{64}", r["sha256"]) and
        type(r.get("rows")) is int and r["rows"] == proof["generated"][r["file"][:-4]]["rows"] for r in files))
    _require(sum(r["bytes"] for r in files) <= MAX_TOTAL_BYTES)

    def path(name):
        result = folder / name
        _require(result.is_file() and not result.is_symlink() and result.resolve().parent == folder.resolve())
        return result

    metadata_path, ready_path = path("metadata.json"), path("_SUCCESS")
    _require(metadata_path.stat().st_size <= 32*1024 and ready_path.stat().st_size <= 4096)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    ready = json.loads(ready_path.read_text(encoding="utf-8"))
    _require(metadata.get("release_mode") == ready.get("release_mode") == "DEMO_ONLY" and
        metadata.get("dataset_version") == ready.get("dataset_version") == version and
        metadata.get("privacy_status") == record["privacy_status"] and metadata.get("files") == files and
        metadata.get("table_counts") == {t: proof["generated"][t]["rows"] for t in TABLES})
    preview = record.get("preview") or {}
    _require(preview.get("file") == "demo-preview.json" and metadata.get("preview") == preview and
        ready.get("preview_sha256") == preview.get("sha256"))
    preview_path = path("demo-preview.json")
    _require(preview_path.stat().st_size == preview.get("bytes") and digest_file(preview_path) == preview.get("sha256"))
    archive = record.get("archive") or {}
    _require(archive.get("file") == "SAGE_DEMO_ONLY.zip" and ready.get("archive_sha256") == archive.get("sha256"))
    archive_path = path(archive["file"])
    _require(archive_path.stat().st_size == archive.get("bytes") and digest_file(archive_path) == archive.get("sha256"))
    for item in files:
        file_path = path(item["file"])
        _require(file_path.stat().st_size == item["bytes"] and digest_file(file_path) == item["sha256"])
    dictionary_path = path("data_dictionary.md")
    _require(0 < dictionary_path.stat().st_size <= 256*1024)
    dictionary = dict(file="data_dictionary.md", bytes=dictionary_path.stat().st_size, sha256=digest_file(dictionary_path))
    with zipfile.ZipFile(archive_path) as bundle:
        expected = {r["file"] for r in files} | {"metadata.json", "data_dictionary.md"}
        _require(len(bundle.namelist()) == 8 and set(bundle.namelist()) == expected)
        for item in [*files, dictionary, dict(file="metadata.json", bytes=metadata_path.stat().st_size, sha256=digest_file(metadata_path))]:
            _require(bundle.getinfo(item["file"]).file_size == item["bytes"])
            with bundle.open(item["file"]) as stream:
                _require(_hash_stream(stream) == item["sha256"])
    return metadata, dictionary


def build_download_manifest(record, metadata, dictionary):
    """Closed public projection only. Publication is always disabled on preparation."""
    by_name = {r["file"]: r for r in record["files"]}
    by_name.update({record["archive"]["file"]: record["archive"], dictionary["file"]: dictionary})
    result = dict(schema_version="1.0", release_mode="DEMO_ONLY", baseline="FABRICATED_DEVELOPMENT",
        verification="VERIFIED_DEMO_ONLY", dataset_version=record["dataset_version"],
        generation_date=_timestamp(metadata["generation_date"]), exported_at=_timestamp(metadata["exported_at"]),
        verified_at=datetime.now(timezone.utc).isoformat(), privacy_status=record["privacy_status"],
        preview_sha256=record["preview"]["sha256"], repository=REPOSITORY,
        publication_status="UNPUBLISHED", publication_checked_at=None,
        assets=[dict(key=key, file=name, bytes=by_name[name]["bytes"], sha256=by_name[name]["sha256"],
                     rows=by_name[name]["rows"] if key in TABLES else None) for key,name in ASSETS])
    _require(len(json.dumps(result).encode()) <= MAX_MANIFEST_BYTES)
    return result


def prepare_download_manifest(spark, export_id, dataset_version):
    """Read a specific completed export, not current_run/current generation or latest."""
    _require(isinstance(export_id, str) and export_id.strip() and isinstance(dataset_version,str) and
        re.fullmatch(r"sage-demo-v[1-9][0-9]*(?:\.[0-9]+)*", dataset_version))
    rows = [r.asDict() for r in spark.sql(f"""SELECT * FROM {PROFILE_SCHEMA}.demo_dataset_exports
        WHERE export_id=:export AND dataset_version=:version""", args={"export":export_id,"version":dataset_version}).collect()]
    _require(len(rows) == 1 and rows[0]["release_mode"] == "DEMO_ONLY")
    row = rows[0]
    record = json.loads(row["manifest_json"])
    folder = Path(EXPORT_ROOT) / dataset_version
    _require(record.get("export_id") == export_id and record.get("dataset_version") == dataset_version and
        record.get("location") == str(folder) and record.get("source_run_id") == row["source_run_id"] and
        record.get("generation_id") == row["generation_id"] and record.get("privacy_status") == row["privacy_status"])
    # An old passing or review-required assessment cannot override a newer blocked one.
    assessments = [r.asDict() for r in spark.sql(f"""SELECT * FROM {PROFILE_SCHEMA}.privacy_assessments
        WHERE generation_id=:generation ORDER BY started_at DESC, assessment_id DESC LIMIT 1""",
        args={"generation": record["generation_id"]}).collect()]
    _require(len(assessments) == 1)
    assessment = assessments[0]
    _require(assessment["assessment_id"] == record.get("privacy_assessment_id") and
        assessment["source_run_id"] == record["source_run_id"] and assessment["completed_at"] is not None and
        assessment["status"] == record["privacy_status"] and
        json.loads(assessment["generated_versions_json"]) == record.get("validated_versions"))
    from synthetic_banking.privacy import _complete_checks
    from synthetic_banking.privacy_reporting import public_privacy_summary
    metrics = [r.asDict() for r in spark.sql(f"""SELECT * FROM {PROFILE_SCHEMA}.privacy_metrics
        WHERE assessment_id=:assessment AND source_run_id=:source AND generation_id=:generation""",
        args={"assessment":assessment["assessment_id"],"source":record["source_run_id"],"generation":record["generation_id"]}).collect()]
    privacy = public_privacy_summary(assessment, metrics)
    _require(_complete_checks(metrics) and privacy["status"] == record["privacy_status"] and
        privacy["identifier_overlap_rows"] == privacy["exact_source_row_matches"] == 0 and
        all(m["status"] in {"PASS","INFO","REVIEW_REQUIRED"} for m in metrics))
    metadata, dictionary = verify_export_files(record, folder, load_policy())
    return build_download_manifest(record, metadata, dictionary)


def download_schema():
    def obj(properties):
        return dict(type="object",properties=properties,required=list(properties),additionalProperties=False)
    timestamp = dict(type="string",format="date-time")
    assets = [obj(dict(key=dict(const=key),file=dict(const=name),bytes=dict(type="integer",minimum=1,maximum=MAX_TOTAL_BYTES),
        sha256=dict(type="string",pattern="^[0-9a-f]{64}$"),
        rows=dict(type="integer",minimum=0,maximum=250_000) if key in TABLES else dict(type="null"))) for key,name in ASSETS]
    schema = {"$schema":"https://json-schema.org/draft/2020-12/schema", **obj(dict(
        schema_version=dict(const="1.0"),release_mode=dict(const="DEMO_ONLY"),baseline=dict(const="FABRICATED_DEVELOPMENT"),
        verification=dict(const="VERIFIED_DEMO_ONLY"),dataset_version=dict(type="string",pattern=r"^sage-demo-v[1-9][0-9]*(\.[0-9]+)*$"),
        generation_date=timestamp,exported_at=timestamp,verified_at=timestamp,privacy_status=dict(enum=["PASS","REVIEW_REQUIRED"]),
        preview_sha256=dict(type="string",pattern="^[0-9a-f]{64}$"),repository=dict(const=REPOSITORY),
        publication_status=dict(enum=["UNPUBLISHED","PUBLISHED","WITHDRAWN"]),
        publication_checked_at=dict(anyOf=[timestamp,dict(type="null")]),
        assets=dict(type="array",prefixItems=assets,items=False,minItems=8,maxItems=8)))}
    schema['properties']['download_urls']=obj({key:dict(type='string',pattern=
        r'^https://github\.com/'+re.escape(REPOSITORY)+r'/releases/download/sage-demo-v[1-9][0-9]*(?:\.[0-9]+)*/'+re.escape(name)+r'$') for key,name in ASSETS})
    return schema
