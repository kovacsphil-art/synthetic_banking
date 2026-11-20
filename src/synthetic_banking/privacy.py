"""Separate disclosure-risk assessments and a fail-closed row-release guard."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from uuid import uuid4

from synthetic_banking.config import PROFILE_SCHEMA, GENERATED_SCHEMA
from synthetic_banking.profiling_run import completed_generation
from synthetic_banking.profiles import select_source_run
from synthetic_banking.privacy_checks import PrivacyMetric, PrivacyPolicy, SparkPrivacyChecks, disclosure_status, IDENTIFIERS, RARE_PAIRS, QUASI, POLICY_VERSION
from synthetic_banking.privacy_sources import delta_identity, load_source_snapshots, snapshot_signature
from synthetic_banking.validation import GENERATED_TABLES
from synthetic_banking.workflow import required_id

ASSESSMENTS = f"{PROFILE_SCHEMA}.privacy_assessments"
METRICS = f"{PROFILE_SCHEMA}.privacy_metrics"
ASSESSMENT_SCHEMA = """assessment_id STRING, source_run_id STRING, generation_id STRING,
    started_at TIMESTAMP, completed_at TIMESTAMP, status STRING, policy_sha256 STRING,
    policy_version STRING, policy_json STRING, generated_versions_json STRING,
    source_snapshot_sha256 STRING, metric_count BIGINT"""
METRIC_SCHEMA = """assessment_id STRING, source_run_id STRING, generation_id STRING,
    check_name STRING, logical_table_name STRING, columns ARRAY<STRING>, status STRING,
    evaluated_rows BIGINT, flagged_rows BIGINT, metric_value DOUBLE, threshold DOUBLE,
    reason_code STRING, details_json STRING"""


class PrivacyGateError(ValueError):
    """No row-level distribution is permitted by this screening gate."""


@dataclass
class PrivacyAssessment:
    assessment_id: str
    source_run_id: str
    generation_id: str
    status: str
    metrics: tuple[PrivacyMetric, ...]


def _validated_generation(spark, source_run_id, generation_id, batch_id=""):
    source = required_id(source_run_id, "SOURCE run_id")
    generation = required_id(generation_id, "generation_id")
    select_source_run(spark, source)
    state = completed_generation(spark)
    if (state["generation_id"] != generation or state["source_run_id"] != source
            or batch_id and state["proposal_batch_id"] != batch_id):
        raise PrivacyGateError("Privacy inputs do not match the validated generation and SOURCE run.")
    return state


def _save_assessment(spark, record):
    spark.sql(f"CREATE TABLE IF NOT EXISTS {ASSESSMENTS} ({ASSESSMENT_SCHEMA}) USING DELTA")
    spark.createDataFrame([record], ASSESSMENT_SCHEMA).createOrReplaceTempView("privacy_assessment_write")
    spark.sql(f"""INSERT INTO {ASSESSMENTS} REPLACE WHERE assessment_id = :assessment
        SELECT * FROM privacy_assessment_write""", args={"assessment": record["assessment_id"]})


def _save_metrics(spark, result):
    spark.sql(f"CREATE TABLE IF NOT EXISTS {METRICS} ({METRIC_SCHEMA}) USING DELTA")
    rows = []
    for metric in result.metrics:
        row = dict(assessment_id=result.assessment_id, source_run_id=result.source_run_id, generation_id=result.generation_id, **metric.record())
        for key in ("threshold", "metric_value"):
            if row[key] is not None:
                row[key] = float(row[key])
        rows.append(row)
    spark.createDataFrame(rows, METRIC_SCHEMA).write.format("delta").mode("append").saveAsTable(METRICS)


def _source_identity_unchanged(spark, snapshots):
    for snapshot in snapshots.values():
        identity, version = delta_identity(spark, snapshot["source_object"])
        if identity != snapshot["table_id"] or version < snapshot["delta_version"]:
            raise PrivacyGateError("The SOURCE snapshot identity is no longer available.")


def run_privacy_assessment(spark, source_run_id, generation_id, *, batch_id="", policy=PrivacyPolicy()):
    """Risk findings are persisted and returned; aggregate-only workflows may continue."""
    source_run_id = required_id(source_run_id, "SOURCE run_id")
    generation_id = required_id(generation_id, "generation_id")
    state = _validated_generation(spark, source_run_id, generation_id, batch_id)
    record = dict(assessment_id=str(uuid4()), source_run_id=source_run_id, generation_id=generation_id,
                  started_at=datetime.now(timezone.utc), completed_at=None, status="RUNNING",
                  policy_sha256=policy.fingerprint,
                  policy_version=POLICY_VERSION, policy_json=json.dumps(asdict(policy), sort_keys=True, allow_nan=False),
                  generated_versions_json=json.dumps(dict(state["validated_versions"]), sort_keys=True),
                  source_snapshot_sha256=None, metric_count=0)
    _save_assessment(spark, record)  # RUNNING is deliberately not release clearance.
    metrics = []
    try:
        snapshots = load_source_snapshots(spark, source_run_id)
        record["source_snapshot_sha256"] = snapshot_signature(snapshots)
        _source_identity_unchanged(spark, snapshots)
        source_frames = {name: spark.read.option("versionAsOf", row["delta_version"]).table(row["source_object"])
                         for name, row in snapshots.items()}
        generated_frames = {}
        for table in GENERATED_TABLES:
            identity, version = state["validated_versions"][table].rsplit(":", 1)
            if not identity or not version.isdigit():
                raise PrivacyGateError("Validated generation snapshots are incomplete.")
            generated_frames[table] = spark.read.option("versionAsOf", int(version)).table(f"{GENERATED_SCHEMA}.{table}")
        metrics = SparkPrivacyChecks(spark, source_frames, generated_frames, policy).run()
        # Refuse input replacement or altered evidence during this scan.
        current = _validated_generation(spark, source_run_id, generation_id, batch_id)
        if dict(current["validated_versions"]) != dict(state["validated_versions"]):
            raise PrivacyGateError("Generated inputs changed during privacy screening.")
        if snapshot_signature(load_source_snapshots(spark, source_run_id)) != record["source_snapshot_sha256"]:
            raise PrivacyGateError("SOURCE snapshot evidence changed during privacy screening.")
        _source_identity_unchanged(spark, snapshots)
    except Exception:
        # Never print exception messages, sample rows, matched values, or row hashes.
        metrics = [PrivacyMetric("INPUT_OR_CHECK_FAILURE", "PIPELINE", (), "UNAVAILABLE",
                                 reason_code="snapshot_or_check_unavailable")]
    if disclosure_status(metrics) == "PASS" and not _complete_checks([m.record() for m in metrics]):
        metrics.append(PrivacyMetric("CHECK_COVERAGE", "PIPELINE", (), "UNAVAILABLE", reason_code="required_privacy_checks_incomplete"))
    status = disclosure_status(metrics)
    result = PrivacyAssessment(record["assessment_id"], source_run_id, generation_id, status, tuple(metrics))
    _save_metrics(spark, result)
    record.update(status=status, metric_count=len(metrics), completed_at=datetime.now(timezone.utc))
    _save_assessment(spark, record)
    return result


def _complete_checks(rows):
    identifiers = {(table, (column,)) for members in IDENTIFIERS.values() for table, column in members}
    expected = {"IDENTIFIER_OVERLAP": identifiers,
                "RARE_COMBINATION": {(table, tuple(columns)) for table, columns in RARE_PAIRS},
                "QUASI_SIMILARITY": {("PERSON", QUASI)}}
    for name, keys in expected.items():
        selected = [row for row in rows if row["check_name"] == name]
        if len(selected) != len(keys) or {(r["logical_table_name"], tuple(r["columns"])) for r in selected} != keys:
            return False
    for name in ("FULL_ROW_MATCH", "PAYLOAD_MATCH"):
        selected = [row for row in rows if row["check_name"] == name]
        if len(selected) != len(GENERATED_TABLES) or {r["logical_table_name"] for r in selected} != set(GENERATED_TABLES):
            return False
    return len(rows) == len(identifiers) + len(RARE_PAIRS) + 1 + 2 * len(GENERATED_TABLES)


def require_row_level_release(spark, source_run_id, generation_id, assessment_id, *, policy=PrivacyPolicy()):
    """Mandatory guard for future row exports/downloads; never for aggregate HTML."""
    try:
        source_run_id = required_id(source_run_id, "SOURCE run_id")
        generation_id = required_id(generation_id, "generation_id")
        assessment_id = required_id(assessment_id, "privacy assessment_id")
        state = _validated_generation(spark, source_run_id, generation_id)
        if not spark.catalog.tableExists(ASSESSMENTS) or not spark.catalog.tableExists(METRICS):
            raise PrivacyGateError("Privacy assessment is missing.")
        rows = spark.sql(f"""SELECT * FROM {ASSESSMENTS} WHERE generation_id = :generation
            ORDER BY started_at DESC, assessment_id DESC LIMIT 1""", args={"generation": generation_id}).collect()
        if len(rows) != 1:
            raise PrivacyGateError("Privacy assessment is missing.")
        latest = rows[0].asDict()
        if (latest["assessment_id"] != assessment_id or latest["source_run_id"] != source_run_id
                or latest["status"] != "PASS" or latest["completed_at"] is None
                or latest["policy_sha256"] != policy.fingerprint
                or json.loads(latest["generated_versions_json"]) != dict(state["validated_versions"])):
            raise PrivacyGateError("Privacy clearance is missing, stale or requires review.")
        snapshots = load_source_snapshots(spark, source_run_id)
        if snapshot_signature(snapshots) != latest["source_snapshot_sha256"]:
            raise PrivacyGateError("SOURCE snapshot provenance changed.")
        _source_identity_unchanged(spark, snapshots)
        metrics = [r.asDict() for r in spark.sql(f"""SELECT check_name, logical_table_name, columns, status
            FROM {METRICS} WHERE assessment_id = :assessment AND source_run_id = :source AND generation_id = :generation""",
            args={"assessment": assessment_id, "source": source_run_id, "generation": generation_id}).collect()]
        if (len(metrics) != latest["metric_count"] or not _complete_checks(metrics)
                or any(r["status"] != "PASS" and not (r["check_name"] == "PAYLOAD_MATCH" and r["status"] == "INFO") for r in metrics)):
            raise PrivacyGateError("Privacy checks are incomplete or have unresolved findings.")
        return latest
    except Exception:
        raise PrivacyGateError("Row-level release blocked: complete, current privacy screening PASS is required. See aggregate privacy metrics.") from None
