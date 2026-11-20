"""Bounded Spark SQL disclosure screens; only scalar aggregates leave Spark."""

from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
import re

from synthetic_banking.validation import GENERATED_TABLES

POLICY_VERSION = "basic_v1"
IDENTIFIERS = {
    "party": (("PERSON", "PARTY_ID"), ("CUSTOMER_ACCOUNT_REL", "PARTY_ID"),
              ("CUSTOMER_RELATIONSHIP", "FROM_PARTY_ID"), ("CUSTOMER_RELATIONSHIP", "TO_PARTY_ID"),
              ("TRADELINES", "REQ-CIF-KEY")),
    "account": (("TKQ_ACCOUNT", "ACCOUNT_ID"), ("TKQ_ACCOUNT_BALANCE", "ACCOUNT_ID"), ("CUSTOMER_ACCOUNT_REL", "ACCT_ID")),
    "tradeline": (("TRADELINES", "account_number"),),
}
RARE_PAIRS = (
    ("PERSON", ("GENDER_CD", "PREF_LANG_CD", "CUST_TYPE_CD")),
    ("PERSON", ("EMP_TYPE_CD", "OCCUP_CAT_CD")),
    ("TKQ_ACCOUNT", ("ACCOUNT_TYPE_CD", "CLIENT_PRODUCT_CD")),
)
QUASI = ("BIRTH_DT", "SINCE_DT", "GENDER_CD")


@dataclass(frozen=True)
class PrivacyPolicy:
    rare_min_count: int = 5
    max_synthetic_rare_fraction: float = .01
    min_complete_fraction: float = .90
    near_date_days: int = 7
    max_similarity_candidates: int = 2_000_000

    def __post_init__(self):
        for value in (self.rare_min_count, self.max_similarity_candidates):
            if type(value) is not int or value < 1:
                raise ValueError("Privacy count limits must be positive integers.")
        if type(self.near_date_days) is not int or not 0 <= self.near_date_days <= 366:
            raise ValueError("near_date_days must be between zero and 366.")
        if (type(self.max_synthetic_rare_fraction) not in {int, float} or type(self.min_complete_fraction) not in {int, float}
                or not 0 <= self.max_synthetic_rare_fraction <= 1 or not 0 < self.min_complete_fraction <= 1):
            raise ValueError("Privacy coverage/fraction thresholds are invalid.")

    @property
    def fingerprint(self):
        return hashlib.sha256(json.dumps({"version": POLICY_VERSION, **asdict(self)}, sort_keys=True).encode()).hexdigest()


@dataclass
class PrivacyMetric:
    check_name: str
    logical_table_name: str
    columns: tuple[str, ...]
    status: str
    evaluated_rows: int | None = None
    flagged_rows: int | None = None
    metric_value: float | None = None
    threshold: float | None = None
    reason_code: str | None = None
    details: dict = field(default_factory=dict)

    def record(self):
        record = asdict(self)
        record["columns"] = list(self.columns)
        record["details_json"] = json.dumps(record.pop("details"), sort_keys=True, allow_nan=False)
        return record


def disclosure_status(metrics):
    if not metrics or any(m.status in {"ERROR", "UNAVAILABLE"} for m in metrics):
        return "BLOCKED"
    if any(m.status == "FAIL" for m in metrics):
        return "BLOCKED"
    if any(m.status == "REVIEW_REQUIRED" for m in metrics):
        return "REVIEW_REQUIRED"
    return "PASS" if any(m.status == "PASS" for m in metrics) and all(m.status in {"PASS", "INFO"} for m in metrics) else "BLOCKED"


def _col(name):
    return "`" + name.replace("`", "``") + "`"


def _type(value):
    return bool(re.fullmatch(r"string|boolean|tinyint|smallint|int|bigint|float|double|date|timestamp(?:_ntz|_ltz)?|decimal\(\d+,\d+\)", value))


class SparkPrivacyChecks:
    """Input frames must already refer to pinned Delta versions, not mutable aliases."""

    def __init__(self, spark, sources, generated, policy=PrivacyPolicy()):
        self.spark, self.policy = spark, policy
        self.sources, self.generated = {}, {}
        self.counts = {}
        for prefix, frames, schemas in (("src", sources, self.sources), ("gen", generated, self.generated)):
            for table in GENERATED_TABLES:
                frame = frames[table]
                schemas[table] = {f.name.upper(): (f.name, f.dataType.simpleString().lower()) for f in frame.schema.fields}
                frame.createOrReplaceTempView(self.view(prefix, table))
                self.counts[prefix, table] = self.scalar(f"SELECT COUNT(*) AS n FROM {self.view(prefix, table)}")["n"]

    @staticmethod
    def view(prefix, table):
        return f"privacy_{prefix}_{table.lower()}"

    def scalar(self, query):
        values = self.spark.sql(query).first().asDict()
        # Guard against accidentally collecting a category, identifier or row value.
        if any(value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)) for value in values.values()):
            raise ValueError("Only finite numeric privacy aggregates may leave Spark.")
        return values

    def available(self, table, columns):
        return all(c.upper() in schemas[table] for schemas in (self.sources, self.generated) for c in columns)

    def name(self, prefix, table, column):
        return _col((self.sources if prefix == "src" else self.generated)[table][column.upper()][0])

    def identifier_checks(self):
        metrics = []
        for members in IDENTIFIERS.values():
            missing = any(not self.available(table, (column,)) for table, column in members)
            pool = " UNION ".join(
                f"SELECT NULLIF(UPPER(TRIM(CAST({self.name('src', table, column)} AS STRING))), '') AS id_value FROM {self.view('src', table)}"
                for table, column in members if self.available(table, (column,)))
            for table, column in members:
                if missing:
                    metrics.append(PrivacyMetric("IDENTIFIER_OVERLAP", table, (column,), "UNAVAILABLE", reason_code="identifier_domain_incomplete"))
                    continue
                value = self.name("gen", table, column)
                row = self.scalar(f"""WITH source_ids AS ({pool}), generated_ids AS (
                    SELECT NULLIF(UPPER(TRIM(CAST({value} AS STRING))), '') AS id_value FROM {self.view('gen', table)}
                ) SELECT COUNT(*) AS eligible,
                    COALESCE(SUM(CASE WHEN s.id_value IS NOT NULL THEN 1 ELSE 0 END), 0) AS flagged
                    FROM generated_ids g LEFT JOIN source_ids s ON s.id_value = g.id_value WHERE g.id_value IS NOT NULL""")
                metrics.append(PrivacyMetric("IDENTIFIER_OVERLAP", table, (column,), "FAIL" if row["flagged"] else "PASS",
                    row["eligible"], row["flagged"], row["flagged"] / row["eligible"] if row["eligible"] else None, 0,
                    "identifier_reuse" if row["flagged"] else None,
                    {"excluded_null_or_blank_rows": self.counts["gen", table] - row["eligible"]}))
        return metrics

    def _row_projection(self, table, columns):
        expressions, lossless = [], []
        for index, column in enumerate(columns):
            source_name, source_type = self.sources[table][column]
            gen_name, gen_type = self.generated[table][column]
            if not _type(source_type) or not _type(gen_type):
                raise ValueError("Unsupported row-comparison type.")
            value = _col(gen_name)
            if source_type != gen_type:
                converted = f"TRY_CAST({value} AS {source_type})"
                lossless.append(f"(TRY_CAST({converted} AS {gen_type}) <=> {value})")
                value = converted
            expressions.append(f"{value} AS c{index}")
        generated = f"SELECT {', '.join(expressions)} FROM {self.view('gen', table)}"
        if lossless:
            generated += " WHERE " + " AND ".join(lossless)
        source = f"SELECT {', '.join(self.name('src', table, column) + f' AS c{i}' for i, column in enumerate(columns))} FROM {self.view('src', table)}"
        return source, generated

    def row_checks(self):
        metrics = []
        identifiers = {column.upper() for members in IDENTIFIERS.values() for _, column in members} | {"REQ-CIF-TIE-BREAKER"}
        for table in GENERATED_TABLES:
            original = list(self.sources[table])
            for check, columns in (("FULL_ROW_MATCH", original), ("PAYLOAD_MATCH", [c for c in original if c not in identifiers])):
                if not columns or not self.available(table, columns):
                    metrics.append(PrivacyMetric(check, table, tuple(columns), "UNAVAILABLE", reason_code="incomplete_comparison_schema"))
                    continue
                try:
                    source, generated = self._row_projection(table, columns)
                except ValueError:
                    metrics.append(PrivacyMetric(check, table, tuple(columns), "UNAVAILABLE", reason_code="unsupported_comparison_type"))
                    continue
                names = ", ".join(f"c{i}" for i in range(len(columns)))
                equality = " AND ".join(f"g.c{i} <=> s.c{i}" for i in range(len(columns)))
                row = self.scalar(f"""WITH source_payload AS (
                    SELECT {names}, COUNT(*) AS support FROM ({source}) GROUP BY {names}
                ), generated_payload AS ({generated})
                SELECT COUNT(*) AS matched, COALESCE(SUM(CASE WHEN s.support < {self.policy.rare_min_count} THEN 1 ELSE 0 END), 0) AS rare_matched
                FROM generated_payload g JOIN source_payload s ON {equality}""")
                informative = len(columns) >= 3 and any(self.sources[table][c][1] not in {"string", "boolean"} for c in columns)
                status = ("FAIL" if row["matched"] else "PASS") if check == "FULL_ROW_MATCH" else (
                    "REVIEW_REQUIRED" if informative and row["rare_matched"] else "PASS" if informative else "INFO")
                flagged = row["matched"] if check == "FULL_ROW_MATCH" else row["rare_matched"]
                metrics.append(PrivacyMetric(check, table, tuple(columns), status, self.counts["gen", table], flagged,
                    flagged / self.counts["gen", table] if self.counts["gen", table] else None, 0,
                    "exact_row_copy" if status == "FAIL" else "rare_payload_copy" if status == "REVIEW_REQUIRED" else "low_information_payload" if status == "INFO" else None,
                    {"matching_rows": row["matched"], "low_support_matching_rows": row["rare_matched"]}))
        return metrics

    def _category_query(self, prefix, table, columns):
        values = [f"NULLIF(UPPER(TRIM(CAST({self.name(prefix, table, col)} AS STRING))), '')" for col in columns]
        return f"SELECT {', '.join(value + f' AS c{i}' for i, value in enumerate(values))} FROM {self.view(prefix, table)} WHERE " + " AND ".join(value + " IS NOT NULL" for value in values)

    def rare_checks(self):
        metrics = []
        for table, columns in RARE_PAIRS:
            if not self.available(table, columns):
                metrics.append(PrivacyMetric("RARE_COMBINATION", table, columns, "UNAVAILABLE", reason_code="categorical_columns_missing"))
                continue
            source = self._category_query("src", table, columns)
            generated = self._category_query("gen", table, columns)
            names = ", ".join(f"c{i}" for i in range(len(columns)))
            equality = " AND ".join(f"g.c{i} = s.c{i}" for i in range(len(columns)))
            row = self.scalar(f"""WITH s AS (SELECT {names}, COUNT(*) AS support FROM ({source}) GROUP BY {names}),
                g AS (SELECT {names}, COUNT(*) AS support FROM ({generated}) GROUP BY {names})
                SELECT COALESCE(SUM(g.support), 0) AS eligible,
                    COALESCE(SUM(CASE WHEN g.support < {self.policy.rare_min_count} THEN g.support ELSE 0 END), 0) AS synthetic_rare,
                    COALESCE(SUM(CASE WHEN s.support < {self.policy.rare_min_count} THEN g.support ELSE 0 END), 0) AS source_rare,
                    COALESCE(SUM(CASE WHEN s.support IS NULL THEN g.support ELSE 0 END), 0) AS source_unseen,
                    COALESCE(SUM(CASE WHEN g.support < {self.policy.rare_min_count} THEN 1 ELSE 0 END), 0) AS rare_groups
                FROM g LEFT JOIN s ON {equality}""")
            source_eligible = self.scalar(f"SELECT COUNT(*) AS n FROM ({source})")["n"]
            coverage = min(source_eligible / max(self.counts["src", table], 1), row["eligible"] / max(self.counts["gen", table], 1))
            ratio = row["synthetic_rare"] / row["eligible"] if row["eligible"] else None
            status = "UNAVAILABLE" if not source_eligible or not row["eligible"] else (
                "REVIEW_REQUIRED" if coverage < self.policy.min_complete_fraction or row["source_rare"] or ratio > self.policy.max_synthetic_rare_fraction else "PASS")
            metrics.append(PrivacyMetric("RARE_COMBINATION", table, columns, status, row["eligible"], row["synthetic_rare"], ratio,
                self.policy.max_synthetic_rare_fraction, "rare_or_incomplete_categorical_patterns" if status != "PASS" else None,
                {**row, "source_complete_rows": source_eligible, "complete_case_coverage": coverage}))
        return metrics

    def similarity_check(self):
        table = "PERSON"
        metric = PrivacyMetric("QUASI_SIMILARITY", table, QUASI, "UNAVAILABLE", reason_code="quasi_columns_missing")
        if not self.available(table, QUASI):
            return metric
        if any(self.sources[table][c][1] not in {"date", "timestamp", "timestamp_ntz", "timestamp_ltz"}
               or self.generated[table][c][1] not in {"date", "timestamp", "timestamp_ntz", "timestamp_ltz"} for c in QUASI[:2]):
            metric.reason_code = "quasi_dates_require_temporal_types"
            return metric
        queries = {}
        for prefix in ("src", "gen"):
            birth, since, gender = (self.name(prefix, table, c) for c in QUASI)
            queries[prefix] = f"""SELECT TO_DATE({birth}) AS birth, TO_DATE({since}) AS since,
                NULLIF(UPPER(TRIM(CAST({gender} AS STRING))), '') AS gender
                FROM {self.view(prefix, table)} WHERE {birth} IS NOT NULL AND {since} IS NOT NULL
                AND NULLIF(TRIM(CAST({gender} AS STRING)), '') IS NOT NULL"""
        width = self.policy.near_date_days + 1
        ctes = f"""WITH s AS (SELECT birth, since, gender, COUNT(*) AS support,
            FLOOR(DATEDIFF(birth, DATE '1970-01-01') / {width}.0) AS bucket FROM ({queries['src']}) GROUP BY birth, since, gender),
            g AS (SELECT birth, since, gender, COUNT(*) AS weight,
            FLOOR(DATEDIFF(birth, DATE '1970-01-01') / {width}.0) AS bucket FROM ({queries['gen']}) GROUP BY birth, since, gender),
            expanded AS (SELECT g.*, bucket - 1 AS candidate_bucket FROM g UNION ALL SELECT g.*, bucket AS candidate_bucket FROM g
                UNION ALL SELECT g.*, bucket + 1 AS candidate_bucket FROM g)"""
        size = self.scalar(ctes + """, sb AS (SELECT gender, bucket, COUNT(*) AS n FROM s GROUP BY gender, bucket),
            gb AS (SELECT gender, candidate_bucket, COUNT(*) AS n FROM expanded GROUP BY gender, candidate_bucket)
            SELECT COALESCE(SUM(sb.n * gb.n), 0) AS pairs FROM sb JOIN gb ON sb.gender = gb.gender AND sb.bucket = gb.candidate_bucket""")["pairs"]
        eligible = {p: self.scalar(f"SELECT COUNT(*) AS n FROM ({q})")["n"] for p, q in queries.items()}
        metric.details = {"candidate_pairs": size, "source_complete_rows": eligible["src"], "generated_complete_rows": eligible["gen"]}
        metric.evaluated_rows = eligible["gen"]
        if not eligible["src"] or not eligible["gen"] or size > self.policy.max_similarity_candidates:
            metric.reason_code = "similarity_budget_or_coverage_unavailable"
            return metric
        days = self.policy.near_date_days
        row = self.scalar(ctes + f""", matched AS (
            SELECT g.birth, g.since, g.gender, g.weight,
                MAX(CASE WHEN s.support < {self.policy.rare_min_count} THEN 1 ELSE 0 END) AS rare,
                MIN(ABS(DATEDIFF(g.birth, s.birth)) + ABS(DATEDIFF(g.since, s.since))) AS distance_days
            FROM expanded g JOIN s ON g.gender = s.gender AND g.candidate_bucket = s.bucket
            WHERE ABS(DATEDIFF(g.birth, s.birth)) <= {days} AND ABS(DATEDIFF(g.since, s.since)) <= {days}
            GROUP BY g.birth, g.since, g.gender, g.weight)
            SELECT COALESCE(SUM(weight), 0) AS matched_rows, COALESCE(SUM(CASE WHEN rare = 1 THEN weight ELSE 0 END), 0) AS rare_rows,
                MIN(distance_days) AS minimum_matched_distance_days FROM matched""")
        coverage = min(eligible[p] / max(self.counts[p, table], 1) for p in eligible)
        metric.status = "REVIEW_REQUIRED" if row["rare_rows"] or coverage < self.policy.min_complete_fraction else "PASS"
        metric.flagged_rows = row["rare_rows"]
        metric.metric_value = row["rare_rows"] / eligible["gen"]
        metric.threshold = 0
        metric.reason_code = "rare_or_incomplete_quasi_matches" if metric.status != "PASS" else None
        metric.details.update(row, complete_case_coverage=coverage)
        return metric

    def run(self):
        return [*self.identifier_checks(), *self.row_checks(), *self.rare_checks(), self.similarity_check()]
