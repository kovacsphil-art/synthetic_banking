"""Aggregate customer-relationship evidence, with no SOURCE identifiers collected."""

import hashlib
import json

from synthetic_banking.profiling import PROFILE_SCHEMA, _active_run, _identifier, _replace_run, _rows


TABLE = "CUSTOMER_RELATIONSHIP"
FROM, TO = "FROM_PARTY_ID", "TO_PARTY_ID"
FORWARD, REVERSE = "FROM_TO_CUST_RELATN_CD", "TO_FROM_CUST_RELATN_CD"
MAX_PATTERNS = 4096
MAX_MULTIPLICITY = 1000
SUMMARY_SCHEMA = """
    run_id STRING, profile_type STRING, person_count BIGINT, raw_rows BIGINT,
    valid_rows BIGINT, invalid_endpoint_rows BIGINT, self_rows BIGINT,
    directed_dyads BIGINT, reciprocal_dyads BIGINT, self_dyads BIGINT, max_multiplicity BIGINT
"""
DEGREE_SCHEMA = """
    run_id STRING, profile_type STRING, outgoing_count BIGINT, incoming_count BIGINT,
    reciprocal_count BIGINT, self_count BIGINT, outgoing_rows BIGINT, incoming_rows BIGINT,
    party_count BIGINT, proportion DOUBLE
"""
DYAD_SCHEMA = """
    run_id STRING, profile_type STRING, edge_kind STRING, forward_count BIGINT,
    reverse_count BIGINT, dyad_count BIGINT
"""
TYPE_SCHEMA = """
    run_id STRING, profile_type STRING, edge_kind STRING,
    forward_from_to STRING, forward_to_from STRING, reverse_from_to STRING, reverse_to_from STRING,
    forward_nulls STRING, reverse_nulls STRING, record_count BIGINT
"""
OWNERSHIP_SCHEMA = """
    run_id STRING, profile_type STRING, from_to STRING, to_from STRING,
    non_null_count BIGINT, min_value DOUBLE, p01 DOUBLE, p05 DOUBLE, p25 DOUBLE,
    p50 DOUBLE, p75 DOUBLE, p95 DOUBLE, p99 DOUBLE, max_value DOUBLE, invalid_count BIGINT
"""
FIELD_SCHEMA = """
    run_id STRING, profile_type STRING, column_name STRING, data_type STRING,
    non_null_count BIGINT, null_count BIGINT, min_length INT, max_length INT,
    digit_count BIGINT, numeric_min DOUBLE, numeric_max DOUBLE
"""
SCHEMAS = {
    "customer_relationship_summary": SUMMARY_SCHEMA,
    "customer_relationship_degree_profile": DEGREE_SCHEMA,
    "customer_relationship_dyad_profile": DYAD_SCHEMA,
    "customer_relationship_type_profile": TYPE_SCHEMA,
    "customer_relationship_ownership_profile": OWNERSHIP_SCHEMA,
    "customer_relationship_field_profile": FIELD_SCHEMA,
}


def _table(value):
    return ".".join(_identifier(part) for part in value.split("."))


def profile_customer_relationships(spark, profile_inputs):
    """Inspect active schema and store bounded graph/attribute histograms for either run type."""
    run = _active_run(spark)
    inventory = _rows(spark, "SELECT logical_table_name, column_name, data_type FROM active_column_inventory")
    fields = {row["column_name"].upper(): row for row in inventory if row["logical_table_name"] == TABLE}
    if TABLE not in profile_inputs or "PERSON" not in profile_inputs or not {FROM, TO, FORWARD, REVERSE} <= fields.keys():
        raise ValueError("CUSTOMER_RELATIONSHIP profiling needs PERSON, FROM/TO_PARTY_ID and both directional relationship-code columns.")
    if len(fields) > 64:
        raise ValueError("Customer relationship profiling supports at most 64 explicitly reviewed schema columns.")
    if any("|" in name or "'" in name or "\\" in name for name in fields):
        raise ValueError("Relationship profile column names cannot contain null-mask delimiters, quotes or backslashes.")
    for name in (FORWARD, REVERSE):
        if fields[name]["data_type"].upper().split("(")[0] not in ("STRING", "VARCHAR", "CHAR"):
            raise ValueError("Directional relationship codes must have text types.")
    if "OWNERSHIP_PERCENTAGE" in fields and fields["OWNERSHIP_PERCENTAGE"]["data_type"].upper().split("(")[0] not in (
        "BYTE", "SHORT", "INT", "INTEGER", "LONG", "BIGINT", "FLOAT", "DOUBLE", "DECIMAL", "NUMERIC",
    ):
        raise ValueError("ownership_percentage requires a numeric SOURCE type.")
    q = lambda name: _identifier(fields[name]["column_name"])
    source, person = _table(profile_inputs[TABLE]), _table(profile_inputs["PERSON"])
    nullable = sorted(name for name in fields if name not in (FROM, TO))
    nulls = ", ".join(f"CASE WHEN r.{q(name)} IS NULL THEN '{name}' END" for name in nullable)
    cte = f"""
        WITH people AS (SELECT DISTINCT CAST(PARTY_ID AS STRING) AS PARTY_ID FROM {person} WHERE PARTY_ID IS NOT NULL),
        valid AS (
            SELECT r.* FROM {source} r JOIN people f ON CAST(r.{q(FROM)} AS STRING) = f.PARTY_ID
                JOIN people t ON CAST(r.{q(TO)} AS STRING) = t.PARTY_ID
        ), pairs AS (
            SELECT CAST({q(FROM)} AS STRING) AS f, CAST({q(TO)} AS STRING) AS t, COUNT(*) AS n FROM valid GROUP BY {q(FROM)}, {q(TO)}
        ), classified AS (
            SELECT p.*, b.n AS back_n,
                CASE WHEN p.f = p.t THEN 'SELF' WHEN b.n IS NOT NULL THEN 'RECIPROCAL' ELSE 'DIRECTED' END AS edge_kind
            FROM pairs p LEFT JOIN pairs b ON p.f = b.t AND p.t = b.f
        )
    """
    summary = _rows(spark, cte + f"""
        SELECT (SELECT COUNT(*) FROM people) AS person_count,
            (SELECT COUNT(*) FROM {source}) AS raw_rows,
            (SELECT COUNT(*) FROM valid) AS valid_rows,
            (SELECT COUNT(*) FROM valid WHERE CAST({q(FROM)} AS STRING) = CAST({q(TO)} AS STRING)) AS self_rows,
            (SELECT COUNT(*) FROM classified WHERE edge_kind = 'DIRECTED') AS directed_dyads,
            (SELECT COUNT(*) FROM classified WHERE edge_kind = 'RECIPROCAL' AND f < t) AS reciprocal_dyads,
            (SELECT COUNT(*) FROM classified WHERE edge_kind = 'SELF') AS self_dyads,
            (SELECT COALESCE(MAX(n), 0) FROM pairs) AS max_multiplicity
    """)[0]
    summary.update(run, invalid_endpoint_rows=summary["raw_rows"] - summary["valid_rows"])
    if summary["max_multiplicity"] > MAX_MULTIPLICITY:
        raise ValueError("SOURCE relationship multiplicity exceeds 1000 rows per directed pair; review before generation.")
    degrees = _rows(spark, cte + f"""
        , out_counts AS (
            SELECT f, SUM(CASE WHEN edge_kind = 'DIRECTED' THEN 1 ELSE 0 END) AS outgoing_count,
                SUM(CASE WHEN edge_kind = 'RECIPROCAL' THEN 1 ELSE 0 END) AS reciprocal_count,
                SUM(CASE WHEN edge_kind = 'SELF' THEN 1 ELSE 0 END) AS self_count, SUM(n) AS outgoing_rows
            FROM classified GROUP BY f
        ), in_counts AS (
            SELECT t, SUM(CASE WHEN edge_kind = 'DIRECTED' THEN 1 ELSE 0 END) AS incoming_count, SUM(n) AS incoming_rows
            FROM classified GROUP BY t
        ), degrees AS (
            SELECT COALESCE(o.outgoing_count, 0) AS outgoing_count, COALESCE(i.incoming_count, 0) AS incoming_count,
                COALESCE(o.reciprocal_count, 0) AS reciprocal_count, COALESCE(o.self_count, 0) AS self_count,
                COALESCE(o.outgoing_rows, 0) AS outgoing_rows, COALESCE(i.incoming_rows, 0) AS incoming_rows
            FROM people p LEFT JOIN out_counts o ON p.PARTY_ID = o.f LEFT JOIN in_counts i ON p.PARTY_ID = i.t
        )
        SELECT outgoing_count, incoming_count, reciprocal_count, self_count, outgoing_rows, incoming_rows,
            COUNT(*) AS party_count FROM degrees
        GROUP BY outgoing_count, incoming_count, reciprocal_count, self_count, outgoing_rows, incoming_rows
        LIMIT {MAX_PATTERNS + 1}
    """)
    for row in degrees:
        row.update(run, proportion=row["party_count"] / summary["person_count"])
    dyads = _rows(spark, cte + f"""
        SELECT edge_kind, n AS forward_count, CASE WHEN edge_kind = 'RECIPROCAL' THEN back_n ELSE 0 END AS reverse_count,
            COUNT(*) AS dyad_count FROM classified
        WHERE edge_kind <> 'RECIPROCAL' OR f < t GROUP BY edge_kind, n,
            CASE WHEN edge_kind = 'RECIPROCAL' THEN back_n ELSE 0 END LIMIT {MAX_PATTERNS + 1}
    """)
    types = _rows(spark, cte + f"""
        , attributes AS (
            SELECT CAST(r.{q(FROM)} AS STRING) AS f, CAST(r.{q(TO)} AS STRING) AS t, CAST(r.{q(FORWARD)} AS STRING) AS forward_type,
                CAST(r.{q(REVERSE)} AS STRING) AS backward_type, CONCAT_WS('|', {nulls}) AS nulls,
                COUNT(*) AS n FROM valid r GROUP BY r.{q(FROM)}, r.{q(TO)}, r.{q(FORWARD)}, r.{q(REVERSE)}, CONCAT_WS('|', {nulls})
        )
        SELECT c.edge_kind, a.forward_type AS forward_from_to, a.backward_type AS forward_to_from,
            b.forward_type AS reverse_from_to, b.backward_type AS reverse_to_from,
            a.nulls AS forward_nulls, b.nulls AS reverse_nulls, SUM(a.n * COALESCE(b.n, 1)) AS record_count
        FROM classified c JOIN attributes a ON a.f = c.f AND a.t = c.t
        LEFT JOIN attributes b ON c.edge_kind = 'RECIPROCAL' AND b.f = a.t AND b.t = a.f
        WHERE c.edge_kind <> 'RECIPROCAL' OR c.f < c.t
        GROUP BY c.edge_kind, a.forward_type, a.backward_type, b.forward_type, b.backward_type, a.nulls, b.nulls
        LIMIT {MAX_PATTERNS + 1}
    """)
    ownership = []
    if "OWNERSHIP_PERCENTAGE" in fields:
        value = f"CAST({q('OWNERSHIP_PERCENTAGE')} AS DOUBLE)"
        quantiles = ", ".join(f"PERCENTILE_APPROX({value}, {p}, 10000) AS {name}" for name, p in
                              (("p01", .01), ("p05", .05), ("p25", .25), ("p50", .5), ("p75", .75), ("p95", .95), ("p99", .99)))
        ownership = _rows(spark, cte + f"""
            SELECT CAST({q(FORWARD)} AS STRING) AS from_to, CAST({q(REVERSE)} AS STRING) AS to_from,
                COUNT({value}) AS non_null_count, MIN({value}) AS min_value, {quantiles}, MAX({value}) AS max_value,
                COUNT(CASE WHEN {value} < 0 OR {value} > 100 OR ISNAN({value}) THEN 1 END) AS invalid_count
            FROM valid GROUP BY {q(FORWARD)}, {q(REVERSE)} LIMIT {MAX_PATTERNS + 1}
        """)
    field_profiles = []
    for name in nullable:
        kind = fields[name]["data_type"].upper().split("(")[0]
        extras = ""
        if kind in ("STRING", "VARCHAR", "CHAR"):
            extras = f""", MIN(LENGTH({q(name)})) AS min_length, MAX(LENGTH({q(name)})) AS max_length,
                COUNT(CASE WHEN {q(name)} RLIKE '^[0-9]+$' THEN 1 END) AS digit_count,
                MIN(TRY_CAST({q(name)} AS DOUBLE)) AS numeric_min, MAX(TRY_CAST({q(name)} AS DOUBLE)) AS numeric_max"""
        raw = _rows(spark, cte + f"SELECT COUNT({q(name)}) AS non_null_count, COUNT(*) - COUNT({q(name)}) AS null_count {extras} FROM valid")[0]
        row = {field.strip().split()[0]: None for field in FIELD_SCHEMA.split(",")}
        row.update(run, column_name=fields[name]["column_name"], data_type=fields[name]["data_type"], **raw)
        field_profiles.append(row)
    outputs = (degrees, dyads, types, ownership, field_profiles)
    if any(len(rows) > MAX_PATTERNS for rows in outputs):
        raise ValueError("Relationship aggregate patterns exceed the 4096-pattern bound; review the SOURCE schema/data.")
    if _active_run(spark) != run:
        raise ValueError("Active run changed while customer relationships were profiled.")
    for name, rows in zip(tuple(SCHEMAS)[1:], outputs):
        _replace_run(spark, name, SCHEMAS[name], [{**row, **run} for row in rows], run["run_id"])
    # Extend the existing structural profile without replacing account/tradeline metrics.
    cardinalities = []
    for field, label in (("outgoing_rows", "OUTGOING"), ("incoming_rows", "INCOMING"),
                         ("reciprocal_count", "RECIPROCAL_NEIGHBORS"), ("self_count", "SELF_DYADS")):
        totals = {}
        for row in degrees:
            totals[row[field]] = totals.get(row[field], 0) + row["party_count"]
        cardinalities.extend((run["run_id"], f"CUSTOMER_RELATIONSHIP_{label}", value, count, count / summary["person_count"])
                             for value, count in sorted(totals.items()))
    cardinality_schema = "run_id STRING, relationship_name STRING, cardinality INT, entity_count BIGINT, proportion DOUBLE"
    spark.createDataFrame(cardinalities, cardinality_schema).createOrReplaceTempView("customer_relationship_cardinalities_write")
    spark.sql(f"""INSERT INTO {PROFILE_SCHEMA}.cardinality_profile
        REPLACE WHERE run_id = :run AND relationship_name IN (
            'CUSTOMER_RELATIONSHIP_OUTGOING','CUSTOMER_RELATIONSHIP_INCOMING',
            'CUSTOMER_RELATIONSHIP_RECIPROCAL_NEIGHBORS','CUSTOMER_RELATIONSHIP_SELF_DYADS')
        SELECT * FROM customer_relationship_cardinalities_write""", args={"run": run["run_id"]})
    _replace_run(spark, "customer_relationship_summary", SUMMARY_SCHEMA, [summary], run["run_id"])
    print(f"{run['profile_type']} CUSTOMER_RELATIONSHIP: {summary['valid_rows']} valid rows; "
          f"{summary['invalid_endpoint_rows']} excluded null/orphan endpoint rows; {summary['self_rows']} self rows.")
    return summary


def load_customer_relationship_profile(spark, source_run_id):
    """Load schema and measured aggregates for exactly one completed SOURCE run."""
    run = _rows(spark, f"""SELECT run_id FROM {PROFILE_SCHEMA}.profile_runs
        WHERE run_id = :source AND profile_type = 'SOURCE' AND status = 'COMPLETED' AND completed_at IS NOT NULL
    """, {"source": source_run_id})
    if not source_run_id or len(run) != 1 or not all(spark.catalog.tableExists(f"{PROFILE_SCHEMA}.{name}") for name in SCHEMAS):
        raise ValueError("Run Notebook 01 SOURCE with customer-relationship profiling before generation.")
    result = {"source_run_id": source_run_id}
    for name in SCHEMAS:
        result[name] = _rows(spark, f"SELECT * FROM {PROFILE_SCHEMA}.{name} WHERE run_id = :source AND profile_type = 'SOURCE' LIMIT {MAX_PATTERNS + 1}", {"source": source_run_id})
        if len(result[name]) > MAX_PATTERNS:
            raise ValueError("Customer relationship profile exceeds the aggregate pattern bound.")
    summaries = result["customer_relationship_summary"]
    if len(summaries) != 1:
        raise ValueError("Missing/duplicate customer relationship summary for the selected SOURCE run.")
    summary = summaries[0]
    if summary["raw_rows"] and not summary["valid_rows"]:
        raise ValueError("No SOURCE customer relationships reference valid PERSON endpoints; repair SOURCE first.")
    degrees = result["customer_relationship_degree_profile"]
    if (sum(row["party_count"] for row in degrees) != summary["person_count"]
        or sum(row["party_count"] * row["outgoing_rows"] for row in degrees) != summary["valid_rows"]
        or sum(row["party_count"] * row["incoming_rows"] for row in degrees) != summary["valid_rows"]
        or sum(row["party_count"] * row["outgoing_count"] for row in degrees) != summary["directed_dyads"]
        or sum(row["party_count"] * row["incoming_count"] for row in degrees) != summary["directed_dyads"]
        or sum(row["party_count"] * row["reciprocal_count"] for row in degrees) != 2 * summary["reciprocal_dyads"]
        or sum(row["party_count"] * row["self_count"] for row in degrees) != summary["self_dyads"]):
        raise ValueError("Incomplete/inconsistent SOURCE relationship degree profile; re-profile SOURCE.")
    dyads = result["customer_relationship_dyad_profile"]
    if any(row["edge_kind"] not in ("DIRECTED", "RECIPROCAL", "SELF") for row in dyads + result["customer_relationship_type_profile"]):
        raise ValueError("Unsupported SOURCE relationship dyad kind.")
    if sum(row["dyad_count"] * (row["forward_count"] + row["reverse_count"]) for row in dyads) != summary["valid_rows"]:
        raise ValueError("Incomplete SOURCE dyad multiplicity profile.")
    for kind, field in (("DIRECTED", "directed_dyads"), ("RECIPROCAL", "reciprocal_dyads"), ("SELF", "self_dyads")):
        if sum(row["dyad_count"] for row in dyads if row["edge_kind"] == kind) != summary[field]:
            raise ValueError("SOURCE dyad kinds disagree with their summary.")
        templates = [row for row in result["customer_relationship_type_profile"] if row["edge_kind"] == kind]
        expected_templates = sum(row["dyad_count"] * row["forward_count"] * (row["reverse_count"] if kind == "RECIPROCAL" else 1)
                                 for row in dyads if row["edge_kind"] == kind)
        if (bool(templates) != bool(summary[field]) or any(row["record_count"] <= 0 for row in templates)
            or sum(row["record_count"] for row in templates) != expected_templates):
            raise ValueError("SOURCE directional type/null-pattern evidence is missing or invalid.")
    if any(row["non_null_count"] + row["null_count"] != summary["valid_rows"] for row in result["customer_relationship_field_profile"]):
        raise ValueError("SOURCE relationship field/null counts are incomplete.")
    result["column_quality"] = _rows(spark, f"SELECT * FROM {PROFILE_SCHEMA}.column_quality WHERE run_id = :source AND logical_table_name = 'CUSTOMER_RELATIONSHIP'", {"source": source_run_id})
    for name in ("category_profile", "numeric_profile"):
        result[name] = _rows(spark, f"SELECT * FROM {PROFILE_SCHEMA}.{name} WHERE run_id = :source AND logical_table_name = 'CUSTOMER_RELATIONSHIP'", {"source": source_run_id})
    for value in result.values():
        if isinstance(value, list):
            value.sort(key=lambda row: json.dumps(row, sort_keys=True, default=str, allow_nan=False))
    signature = json.dumps(result, sort_keys=True, default=str, allow_nan=False)
    result["profile_signature"] = hashlib.sha256(signature.encode("utf-8")).hexdigest()
    return result
