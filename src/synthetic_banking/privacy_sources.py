"""Retain metadata for the Delta inputs of a SOURCE profile, never source rows."""

import hashlib
import json
import re

from synthetic_banking.config import CATALOG, PROFILE_SCHEMA, STAGING_SCHEMA, SOURCE_ALIASES

SOURCE_SNAPSHOTS = f"{PROFILE_SCHEMA}.privacy_source_snapshots"
SOURCE_SCHEMA = """run_id STRING, logical_table_name STRING, source_object STRING,
    table_id STRING, delta_version BIGINT, alias_sha256 STRING, status STRING"""


def quote(name):
    return ".".join("`" + part.replace("`", "``") + "`" for part in name.split("."))


def delta_identity(spark, name):
    detail = spark.sql(f"DESCRIBE DETAIL {quote(name)}").first()
    history = spark.sql(f"DESCRIBE HISTORY {quote(name)} LIMIT 1").first()
    if not detail or detail["format"] != "delta" or not detail["id"] or history is None:
        raise ValueError("A versioned Delta input is required.")
    return str(detail["id"]), int(history["version"])


def _alias_digest(spark, alias, source_object):
    ddl = spark.sql(f"SHOW CREATE TABLE {quote(alias)}").first()[0]
    normalized = re.sub(r"\s+", " ", ddl.replace("`", "")).strip().rstrip(";").lower()
    # This pipeline's SOURCE aliases are simple SELECT * views created by Notebook 01.
    if not re.search(r"\bas select \* from " + re.escape(source_object.lower()) + r"$", normalized):
        raise ValueError("The SOURCE alias is not the configured staging-table projection.")
    return hashlib.sha256(ddl.encode("utf-8")).hexdigest()


def _save(spark, run_id, rows):
    spark.sql(f"CREATE TABLE IF NOT EXISTS {SOURCE_SNAPSHOTS} ({SOURCE_SCHEMA}) USING DELTA")
    spark.createDataFrame(rows, SOURCE_SCHEMA).createOrReplaceTempView("privacy_source_snapshots_write")
    spark.sql(f"""INSERT INTO {SOURCE_SNAPSHOTS} REPLACE WHERE run_id = :source
        SELECT * FROM privacy_source_snapshots_write""", args={"source": run_id})


def capture_source_inputs(spark, run_id="", profile_inputs=None):
    """Best-effort evidence. Failure blocks row release, not ordinary profiling."""
    profile_inputs = profile_inputs or {name: f"{CATALOG}.{alias}" for name, alias in SOURCE_ALIASES.items()}
    rows = []
    for table in SOURCE_ALIASES:
        source = f"{STAGING_SCHEMA}.{table}"
        row = dict(run_id=run_id, logical_table_name=table, source_object=source,
                   table_id=None, delta_version=None, alias_sha256=None, status="UNAVAILABLE")
        try:
            row["alias_sha256"] = _alias_digest(spark, profile_inputs[table], source)
            row["table_id"], row["delta_version"] = delta_identity(spark, source)
            row["status"] = "CAPTURED"
        except Exception:
            pass  # Do not log Spark exception text that might contain source values.
        rows.append(row)
    if run_id:
        try:
            _save(spark, run_id, rows)
        except Exception:
            print("Privacy SOURCE snapshots could not be recorded; row-level release remains blocked.")
    return rows


def bind_source_snapshots(spark, run_id, captured):
    rows = [dict(row, run_id=run_id) for row in captured]
    try:
        _save(spark, run_id, rows)
    except Exception:
        print("Privacy SOURCE snapshots could not be recorded; row-level release remains blocked.")
    return rows


def finalize_source_inputs(spark, run_id, profile_inputs, captured):
    """Verify no staging or alias changes occurred while SOURCE was profiled."""
    rows = [dict(row) for row in captured]
    for row in rows:
        try:
            identity = delta_identity(spark, row["source_object"])
            digest = _alias_digest(spark, profile_inputs[row["logical_table_name"]], row["source_object"])
            row["status"] = "VERIFIED" if (row["status"] == "CAPTURED"
                and identity == (row["table_id"], row["delta_version"]) and digest == row["alias_sha256"]) else "UNAVAILABLE"
        except Exception:
            row["status"] = "UNAVAILABLE"
    try:
        _save(spark, run_id, rows)
    except Exception:
        print("Privacy SOURCE snapshot verification could not be saved; row-level release remains blocked.")


def load_source_snapshots(spark, source_run_id):
    if not spark.catalog.tableExists(SOURCE_SNAPSHOTS):
        raise ValueError("Verified SOURCE snapshots are unavailable.")
    rows = [row.asDict() for row in spark.sql(f"SELECT * FROM {SOURCE_SNAPSHOTS} WHERE run_id = :source",
                                            args={"source": source_run_id}).collect()]
    if (len(rows) != len(SOURCE_ALIASES) or {row["logical_table_name"] for row in rows} != set(SOURCE_ALIASES)
            or any(row["status"] != "VERIFIED" or row["run_id"] != source_run_id
                   or not row["table_id"] or row["delta_version"] is None
                   or row["source_object"] != f"{STAGING_SCHEMA}.{row['logical_table_name']}" for row in rows)):
        raise ValueError("Verified SOURCE snapshots are incomplete.")
    return {row["logical_table_name"]: row for row in rows}


def snapshot_signature(snapshots):
    return hashlib.sha256(json.dumps(snapshots, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
