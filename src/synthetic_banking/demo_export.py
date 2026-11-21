"""Private, fail-closed DEMO_ONLY export; never confers privacy/release clearance.

SOURCE rows stay in Spark. Both replay checks compare full multisets, not samples.
Only reviewed repository functions are imported; proposal text is never executed.
"""
from contextlib import redirect_stdout
from dataclasses import asdict
from datetime import date, datetime, timezone
import csv
import hashlib
import importlib.util
from io import StringIO
import json
import math
from pathlib import Path
import re
import shutil
from tempfile import TemporaryDirectory
from uuid import uuid4
import zipfile

from synthetic_banking.config import SOURCE_DIR, GENERATED_SCHEMA, PROFILE_SCHEMA, GenerationSettings
from synthetic_banking.privacy import _validated_generation, _complete_checks, _source_identity_unchanged
from synthetic_banking.privacy_reporting import load_public_privacy
from synthetic_banking.privacy_sources import load_source_snapshots, snapshot_signature
from synthetic_banking.workflow import required_id, require_profile_pair, check_approvals, enforce_approval

TABLES = ("PERSON", "CUSTOMER_ACCOUNT_REL", "CUSTOMER_RELATIONSHIP", "TKQ_ACCOUNT", "TKQ_ACCOUNT_BALANCE", "TRADELINES")
EXPORT_ROOT = SOURCE_DIR + "/demo_dataset_exports"  # Not the publisher-readable reporting Volume.
POLICY_PATH = Path(__file__).with_name("demo_export_policy.json")
MAX_TABLE_ROWS = 250_000
MAX_TOTAL_BYTES = 512 * 1024 * 1024
NULL_MARKER = "\\N"
KEYS = {"PERSON": ("PARTY_ID",), "CUSTOMER_ACCOUNT_REL": ("PARTY_ID", "ACCT_ID"),
        "CUSTOMER_RELATIONSHIP": ("FROM_PARTY_ID", "TO_PARTY_ID"),
        "TKQ_ACCOUNT": ("ACCOUNT_ID", "BUSINESSEFFECTIVEDATE"),
        "TKQ_ACCOUNT_BALANCE": ("ACCOUNT_ID", "BUSINESSEFFECTIVEDATE"),
        "TRADELINES": ("account_number",)}
RELATIONSHIPS = (
    "CUSTOMER_ACCOUNT_REL.PARTY_ID -> PERSON.PARTY_ID",
    "CUSTOMER_ACCOUNT_REL.ACCT_ID -> TKQ_ACCOUNT.ACCOUNT_ID",
    "CUSTOMER_RELATIONSHIP.FROM_PARTY_ID -> PERSON.PARTY_ID",
    "CUSTOMER_RELATIONSHIP.TO_PARTY_ID -> PERSON.PARTY_ID",
    "TKQ_ACCOUNT_BALANCE.(ACCOUNT_ID, BUSINESSEFFECTIVEDATE) -> TKQ_ACCOUNT.(ACCOUNT_ID, BUSINESSEFFECTIVEDATE)",
    "TRADELINES.REQ-CIF-KEY -> PERSON.PARTY_ID",
)
TABLE_PURPOSES = {
    "PERSON": "Fabricated customer attributes and lifecycle dates. PARTY_ID is the parent customer key.",
    "CUSTOMER_ACCOUNT_REL": "Customer-to-internal-account links, relationship codes and ownership flags.",
    "CUSTOMER_RELATIONSHIP": "Directed links between generated people, with directional types and optional ownership/date metadata. Endpoint pairs need not be unique.",
    "TKQ_ACCOUNT": "Internal account snapshots, limits, product/status fields, activity dates and delinquency attributes.",
    "TKQ_ACCOUNT_BALANCE": "Amounts associated with the corresponding internal account snapshot, including current balance, available credit and overlimit.",
    "TRADELINES": "External-credit-style records linked to generated people; their account numbers are independent of internal accounts.",
}
_SECRET = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b|\bdapi[a-zA-Z0-9]{20,}\b|"
    r"\bgh[pousr]_[a-zA-Z0-9]{20,}\b|\bgithub_pat_[a-zA-Z0-9_]{20,}\b|"
    r"\beyJ[a-zA-Z0-9_-]{8,}\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+|"
    r"(?:password|passwd|client_secret|api[_ -]?key|access[_ -]?token)\s*[:=]|"
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}|"
    r"https?://[^\s/:]+:[^\s/@]+@", re.I)
_FORBIDDEN_FIELD = re.compile(r"(?:password|secret|token|credential|email|e_mail|phone|address|passport|social_insurance|national_id|first_name|last_name|full_name|card_number|cardholder)", re.I)


class DemoExportError(ValueError):
    """Fixed reasons only: never include a rejected cell, row, or Spark exception."""


def fail(reason):
    raise DemoExportError(reason)


def load_policy():
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    if policy.get("policy_version") != "fabricated_development_v1" or set(policy.get("columns", {})) != set(TABLES):
        fail("demo_policy_unavailable")
    return policy


def check_mode(mode):
    if mode != "DEMO_ONLY":
        fail("explicit_DEMO_ONLY_required")


def check_schema(table, fields, policy):
    """Closed, reviewed schema; new columns/types need an explicit policy review."""
    expected = policy["columns"].get(table, {})
    aliases = {"bigint": "long", "integer": "int", "timestamp_ltz": "timestamp"}
    actual = dict(fields)
    if len(actual) != len(fields) or set(actual) != set(expected):
        fail("unreviewed_schema")
    for column, kind in actual.items():
        if (_FORBIDDEN_FIELD.search(column) or
                aliases.get(kind.lower(), kind.lower()) != aliases.get(expected[column], expected[column])):
            fail("unexpected_sensitive_field_or_type")


def inspect_value(column, value):
    """Conservative secret/contact/formula screen, in addition to exact origin proof."""
    if isinstance(value, str):
        if (len(value) > 512 or value == NULL_MARKER or _SECRET.search(value)
                or value.lstrip().startswith(("=", "+", "-", "@"))
                or any(ord(c) < 32 or ord(c) == 127 for c in value)):
            fail("unsafe_string_content")
        # Payment patterns are intentionally digit strings, not payment-card numbers.
        if column.lower() != "payment_pattern" and re.search(r"(?<!\d)\d{13,19}(?!\d)", value):
            fail("unexpected_long_numeric_identifier")
    elif isinstance(value, float) and not math.isfinite(value):
        fail("nonfinite_export_value")
    elif value is not None and not isinstance(value, (str, int, float, date, datetime)):
        from decimal import Decimal
        if not isinstance(value, Decimal) or not value.is_finite():
            fail("unsupported_export_value")


def cell(value):
    if value is None:
        return NULL_MARKER
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def digest_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_csv(path, columns, rows, expected_count, *, byte_budget=MAX_TOTAL_BYTES):
    """Stream only pinned synthetic rows; no resampling, anonymization or key changes."""
    count = 0
    with path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(columns)
        for row in rows:
            values = tuple(row)
            if len(values) != len(columns):
                fail("invalid_csv_row_width")
            for column, value in zip(columns, values):
                inspect_value(column, value)
            writer.writerow([cell(value) for value in values])
            count += 1
            if count > MAX_TABLE_ROWS or stream.tell() > byte_budget:
                fail("demo_export_budget_exceeded")
    if count != expected_count:
        fail("export_row_count_mismatch")
    return dict(file=path.name, rows=count, bytes=path.stat().st_size, sha256=digest_file(path))


def _same_rows(actual, expected):
    if set(actual.columns) != set(expected.columns):
        return False
    expected = expected.select(*actual.columns)
    return not actual.exceptAll(expected).limit(1).count() and not expected.exceptAll(actual).limit(1).count()


def _generated_replay_frame(spark, frame, actual):
    """Mirror save_generation's existing pandas inference and typed-null behavior."""
    from pyspark.sql import functions as F
    nulls = frame.columns[frame.isna().all()].tolist()
    populated = frame.drop(columns=nulls)
    if frame.empty:
        return spark.createDataFrame([], actual.schema)
    output = spark.createDataFrame(populated)
    for field in actual.schema.fields:
        if field.name in nulls:
            output = output.withColumn(field.name, F.lit(None).cast(field.dataType))
    return output.select(*(F.col("`"+f.name.replace("`", "``")+"`").cast(f.dataType).alias(f.name)
                           for f in actual.schema.fields))


def verify_source_replay(spark, snapshots, policy):
    """Recreate known fake inputs in Databricks memory; compare exact SOURCE snapshots."""
    repo = Path(__file__).resolve().parents[2]
    script = repo / "scripts" / "Scotia Fake Records.py"
    content = script.read_text(encoding="utf-8").replace("\r\n", "\n")
    if hashlib.sha256(content.encode()).hexdigest() != policy["generator_sha256"]:
        fail("unreviewed_fabricated_generator")
    spec = importlib.util.spec_from_file_location("sage_reviewed_fake_records", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # Fixed reviewed repository code, never proposal text.
    workbook = str(Path(SOURCE_DIR) / "RCAR_source_column_list.xlsx")
    if not Path(workbook).is_file():
        fail("fabricated_schema_workbook_missing")
    fake = module.generate_fake_banking_data(policy["source_people"], workbook, policy["source_seed"])
    module.validate_relationships(fake)
    proof = {}
    # Match the original Parquet conversion (including nulls and microsecond precision).
    with TemporaryDirectory(prefix="sage-fabricated-replay-") as temporary:
        for table in TABLES:
            snapshot = snapshots[table]
            actual = spark.read.option("versionAsOf", snapshot["delta_version"]).table(snapshot["source_object"])
            if set(actual.columns) != set(policy["columns"][table]) - ({"_UTILIZATION_RATE"} if table == "TKQ_ACCOUNT" else set()):
                fail("source_schema_not_reviewed")
            path = str(Path(temporary) / (table + ".parquet"))
            fake[table].to_parquet(path, index=False, engine="pyarrow", coerce_timestamps="us", allow_truncated_timestamps=True)
            # Spark cannot read driver-local files on serverless: use Arrow's converted
            # pandas values, then preserve the SOURCE schema through explicit casts.
            import pandas as pd
            expected = _generated_replay_frame(spark, pd.read_parquet(path), actual)
            if not _same_rows(actual, expected):
                fail("source_not_exact_fabricated_replay:" + table)
            proof[table] = {"status": "EXACT_REPLAY", "rows": len(fake[table])}
    return proof


def _context(spark, ids):
    require_profile_pair(spark, ids["source_run_id"], ids["batch_id"], ids["generation_id"], ids["generated_run_id"])
    enforce_approval(check_approvals(spark, ids["source_run_id"], ids["batch_id"]))
    state = _validated_generation(spark, ids["source_run_id"], ids["generation_id"], ids["batch_id"])
    snapshots = load_source_snapshots(spark, ids["source_run_id"])
    _source_identity_unchanged(spark, snapshots)
    args = {"source": ids["source_run_id"], "generated": ids["generated_run_id"], "generation": ids["generation_id"]}
    metrics = spark.sql(f"""SELECT generated_check_status FROM {PROFILE_SCHEMA}.fidelity_metrics
        WHERE source_run_id=:source AND generated_run_id=:generated AND generation_id=:generation""", args=args).collect()
    if not metrics or any(r["generated_check_status"] == "ISSUE" for r in metrics):
        fail("validated_profile_pair_required")
    latest = spark.sql(f"""SELECT assessment_id FROM {PROFILE_SCHEMA}.privacy_assessments
        WHERE generation_id=:generation ORDER BY started_at DESC, assessment_id DESC LIMIT 1""", args={"generation": ids["generation_id"]}).first()
    if not latest or latest["assessment_id"] != ids["privacy_assessment_id"]:
        fail("current_privacy_assessment_required")
    privacy = load_public_privacy(spark, ids["source_run_id"], ids["generation_id"], ids["batch_id"], ids["privacy_assessment_id"])
    rows = [r.asDict() for r in spark.sql(f"""SELECT * FROM {PROFILE_SCHEMA}.privacy_metrics
        WHERE assessment_id=:assessment AND source_run_id=:source AND generation_id=:generation""",
        args={"assessment": ids["privacy_assessment_id"], "source": ids["source_run_id"], "generation": ids["generation_id"]}).collect()]
    if (privacy["status"] not in {"PASS", "REVIEW_REQUIRED"} or not _complete_checks(rows)
            or any(r["status"] not in {"PASS", "INFO", "REVIEW_REQUIRED"} for r in rows)
            or privacy["identifier_overlap_rows"] != 0 or privacy["exact_source_row_matches"] != 0):
        fail("privacy_evidence_incomplete_or_blocked")
    return state, snapshots, privacy


def _dictionary(frames):
    lines = ["# SAGE fabricated demonstration dataset", "",
        "DEMO_ONLY. All records derive from verified fabricated development inputs.",
        "Not real customers, production-representative data, or anonymization certification.",
        "Privacy screening findings remain in metadata.json. Publication requires the separate verified DEMO_ONLY release workflow.", "",
        "UTF-8 CSV, comma delimiter, quoted as needed; \\N represents NULL (empty strings remain empty).",
        "Import identifiers as text to preserve zero padding. Dates/timestamps use ISO 8601;",
        "Spark timestamps are exported in UTC; TIMESTAMP_NTZ values have no timezone.",
        "Numeric values retain saved precision. No keys, values or null masks were resampled.", "", "## Relationships", ""]
    lines += ["- " + relationship for relationship in RELATIONSHIPS]
    lines += ["", "CUSTOMER_ACCOUNT_REL maps people to internal accounts; TRADELINES are external-style",
              "credit records linked to a person, not a foreign key to internal accounts.",
              "CUSTOMER_RELATIONSHIP direction codes describe FROM→TO and TO→FROM separately.", ""]
    for table in TABLES:
        lines += ["## " + table, "", TABLE_PURPOSES[table], "", "Key/link fields: " + ", ".join(KEYS[table]), "",
                  "| Field | Saved type | Meaning |", "| --- | --- | --- |"]
        for field in frames[table].schema.fields:
            key = field.name in KEYS[table] or field.name in {"PARTY_ID", "REQ-CIF-KEY"}
            meaning = "Synthetic key / relationship field" if key else "Derived balance ÷ credit limit" if field.name == "_UTILIZATION_RATE" else "Fabricated temporal attribute" if "timestamp" in field.dataType.simpleString() or field.dataType.simpleString() == "date" else "Fabricated measured attribute; field name follows the development schema"
            lines.append(f"| {field.name} | {field.dataType.simpleString()} | {meaning} |")
        lines.append("")
    return "\n".join(lines)


def build_archive(folder, manifests, metadata, dictionary):
    expected = {table + ".csv" for table in TABLES}
    if {m["file"] for m in manifests} != expected or len(manifests) != 6:
        fail("six_table_manifest_required")
    for manifest in manifests:
        path = folder / manifest["file"]
        if path.stat().st_size != manifest["bytes"] or digest_file(path) != manifest["sha256"]:
            fail("csv_manifest_mismatch")
    (folder / "metadata.json").write_text(json.dumps(metadata, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    (folder / "data_dictionary.md").write_text(dictionary+"\n", encoding="utf-8")
    archive = folder / "SAGE_DEMO_ONLY.zip"
    # Volume FUSE does not support ZIP's seek/backpatch writes. Build and close the
    # archive in private driver scratch, then copy sequentially to the new Volume file.
    with TemporaryDirectory(prefix="sage-demo-zip-") as temporary:
        local_archive = Path(temporary) / archive.name
        with zipfile.ZipFile(local_archive, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
            for name in sorted(expected | {"metadata.json", "data_dictionary.md"}):
                bundle.write(folder / name, arcname=name)
        with local_archive.open("rb") as source, archive.open("xb") as target:
            shutil.copyfileobj(source, target, length=1024*1024)
        if digest_file(local_archive) != digest_file(archive):
            fail("zip_copy_verification_failed")
    with zipfile.ZipFile(archive) as bundle:
        if set(bundle.namelist()) != expected | {"metadata.json", "data_dictionary.md"} or bundle.testzip():
            fail("zip_verification_failed")
    return {"file": archive.name, "bytes": archive.stat().st_size, "sha256": digest_file(archive)}


def export_demo_dataset(spark, *, release_mode, dataset_version, source_run_id, batch_id,
                        generation_id, generated_run_id, privacy_assessment_id):
    """Opt-in private export. A directory is ready only with its final _SUCCESS receipt."""
    check_mode(release_mode)
    if not re.fullmatch(r"sage-demo-v[1-9][0-9]*(?:\.[0-9]+)*", dataset_version):
        fail("invalid_demo_dataset_version")
    ids = {name: required_id(value, name) for name, value in locals().copy().items()
           if name in {"source_run_id", "batch_id", "generation_id", "generated_run_id", "privacy_assessment_id"}}
    if spark.conf.get("spark.sql.session.timeZone") not in {"UTC", "Etc/UTC"}:
        fail("UTC_session_required")
    policy = load_policy()
    folder = Path(EXPORT_ROOT) / dataset_version
    if folder.exists():
        fail("demo_dataset_version_already_exists")
    state, snapshots, privacy = _context(spark, ids)
    source_proof = verify_source_replay(spark, snapshots, policy)
    frames, counts = {}, {}
    for table in TABLES:
        _, version = state["validated_versions"][table].rsplit(":", 1)
        frames[table] = spark.read.option("versionAsOf", int(version)).table(f"{GENERATED_SCHEMA}.{table}")
        check_schema(table, [(f.name, f.dataType.simpleString()) for f in frames[table].schema.fields], policy)
        counts[table] = frames[table].count()
        if not 0 <= counts[table] <= MAX_TABLE_ROWS:
            fail("demo_export_budget_exceeded")
    audit = [r.asDict() for r in spark.sql(f"""SELECT * FROM {GENERATED_SCHEMA}.rule_execution_log
        WHERE generation_id=:generation AND source_run_id=:source""",
        args={"generation": generation_id, "source": source_run_id}).collect()]
    seeds = {r.get("seed") for r in audit}
    if len(seeds) != 1 or not audit or not all(r.get("logged_at") for r in audit):
        fail("generation_seed_or_audit_missing")
    seed = next(iter(seeds))
    if type(seed) is not int:
        fail("generation_seed_or_audit_missing")
    from synthetic_banking.profiles import load_generation_profiles
    from synthetic_banking.generation import generate_dataset
    # Quiet ordinary progress messages; never display any recreated records.
    with redirect_stdout(StringIO()):
        profiles = load_generation_profiles(spark, source_run_id)
        replay = generate_dataset(spark, profiles, GenerationSettings(num_customers=counts["PERSON"], seed=seed, proposal_batch_id=batch_id))
    for table in TABLES:
        if not _same_rows(frames[table], _generated_replay_frame(spark, replay.tables[table], frames[table])):
            fail("generated_not_exact_reviewed_replay:" + table)
    event_fields = tuple(asdict(replay.rule_events[0])) if replay.rule_events else ()
    canonical = lambda row: json.dumps({key: row[key] for key in event_fields}, sort_keys=True, default=list)
    if not event_fields or sorted(canonical(asdict(e)) for e in replay.rule_events) != sorted(canonical(r) for r in audit):
        fail("generation_rule_audit_replay_mismatch")
    generation_date = max(r["logged_at"] for r in audit).replace(tzinfo=timezone.utc).isoformat()
    proof = {"policy": policy["policy_version"], "script_sha256": policy["generator_sha256"],
             "source": source_proof, "generated": {table: {"status": "EXACT_REPLAY", "rows": counts[table]} for table in TABLES}}
    # Check every saved value before creating any export file.
    for table in TABLES:
        for row in frames[table].toLocalIterator():
            for column, value in zip(frames[table].columns, row):
                inspect_value(column, value)
    again, latest_snapshots, latest_privacy = _context(spark, ids)
    if dict(again["validated_versions"]) != dict(state["validated_versions"]) or snapshot_signature(latest_snapshots) != snapshot_signature(snapshots) or latest_privacy != privacy:
        fail("demo_provenance_changed")
    # A new version only, never a replace of a previous valid artifact.
    folder.parent.mkdir(parents=True, exist_ok=True)
    if folder.parent.resolve() != Path(EXPORT_ROOT):
        fail("demo_export_path_changed")
    folder.mkdir()
    stage = "csv"
    try:
        manifests = []
        for table in TABLES:
            manifests.append(write_csv(folder / (table+".csv"), frames[table].columns,
                frames[table].orderBy(*KEYS[table]).toLocalIterator(), counts[table],
                byte_budget=MAX_TOTAL_BYTES-sum(m["bytes"] for m in manifests)))
        stage = "preview"
        from synthetic_banking.demo_preview import build_preview
        exported_at = datetime.now(timezone.utc).isoformat()
        preview_path = folder / "demo-preview.json"
        preview_path.write_bytes(build_preview(frames, counts, dataset_version=dataset_version,
            generated_at=exported_at, privacy_status=privacy["status"]))
        preview = {"file": preview_path.name, "bytes": preview_path.stat().st_size, "sha256": digest_file(preview_path)}
        metadata = {"schema_version": "1.0", "release_mode": "DEMO_ONLY", "dataset_version": dataset_version,
            "generation_date": generation_date, "exported_at": exported_at, "seed": seed,
            "baseline": "Verified fabricated development records; not production banking/customer data",
            "publication_authorized": False, "privacy_status": privacy["status"],
            "privacy_findings": {"near_matches": privacy["near_matches"]["flagged_rows"],
                "source_rare_matches": sum(r["source_rare_match_rows"] or 0 for r in privacy["categorical_patterns"])},
            "limitations": "DEMO_ONLY origin verification does not change privacy screening or confer anonymization certification.",
            "null_marker": NULL_MARKER, "table_counts": counts, "files": manifests, "preview": preview}
        stage = "archive"
        archive = build_archive(folder, manifests, metadata, _dictionary(frames))
        stage = "final_provenance"
        final_state, final_snapshots, final_privacy = _context(spark, ids)
        if dict(final_state["validated_versions"]) != dict(state["validated_versions"]) or snapshot_signature(final_snapshots) != snapshot_signature(snapshots) or final_privacy != privacy:
            fail("demo_provenance_changed")
        receipt = {"export_id": str(uuid4()), **ids, "dataset_version": dataset_version, "release_mode": "DEMO_ONLY",
                   "privacy_status": privacy["status"], "location": str(folder), "files": manifests, "archive": archive, "preview": preview,
                   "proof": proof, "validated_versions": dict(state["validated_versions"])}
        stage = "audit"
        spark.sql(f"""CREATE TABLE IF NOT EXISTS {PROFILE_SCHEMA}.demo_dataset_exports
            (export_id STRING, source_run_id STRING, generation_id STRING, dataset_version STRING,
             release_mode STRING, privacy_status STRING, manifest_json STRING, exported_at TIMESTAMP) USING DELTA""")
        spark.createDataFrame([(receipt["export_id"], source_run_id, generation_id, dataset_version, "DEMO_ONLY", privacy["status"],
            json.dumps(receipt, sort_keys=True), datetime.now(timezone.utc))],
            "export_id STRING, source_run_id STRING, generation_id STRING, dataset_version STRING, release_mode STRING, privacy_status STRING, manifest_json STRING, exported_at TIMESTAMP"
        ).write.format("delta").mode("append").saveAsTable(f"{PROFILE_SCHEMA}.demo_dataset_exports")
        stage = "readiness"
        (folder / "_SUCCESS").write_text(json.dumps({"dataset_version": dataset_version, "archive_sha256": archive["sha256"], "preview_sha256": preview["sha256"], "release_mode": "DEMO_ONLY"})+"\n")
        return receipt
    except Exception as error:
        # Remove only this call's newly created directory inside the fixed private root.
        if folder.parent.resolve() == Path(EXPORT_ROOT) and folder.name == dataset_version and not folder.is_symlink():
            shutil.rmtree(folder)
        reason = str(error) if isinstance(error, DemoExportError) else type(error).__name__
        code = getattr(error, "errno", None)
        raise DemoExportError(f"demo_export_failed:{stage}:{reason}:errno={code}") from None
