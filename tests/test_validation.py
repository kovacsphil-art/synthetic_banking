import contextlib
import io
import json
import math
import re
import sqlite3
from types import SimpleNamespace
import unittest

from synthetic_banking.validation import (
    AUDIT_TABLE,
    GENERATED_SCHEMA,
    GeneratedValidationError,
    check_validated_versions,
    expected_generated_schema,
    null_padding_type,
    validate_generated_batch,
    RELATIONSHIP_AUDIT_TABLE,
)


SCHEMAS = {
    "PERSON": {"PARTY_ID": "string", "BIRTH_DT": "date", "SINCE_DT": "timestamp", "OPTIONAL_CD": "string"},
    "CUSTOMER_ACCOUNT_REL": {"PARTY_ID": "string", "ACCT_ID": "string"},
    "CUSTOMER_RELATIONSHIP": {"FROM_PARTY_ID": "string", "TO_PARTY_ID": "string",
                              "FROM_TO_CUST_RELATN_CD": "string", "TO_FROM_CUST_RELATN_CD": "string",
                              "ownership_percentage": "double", "OWNED_BUS_SINCE_DT": "date"},
    "TKQ_ACCOUNT": {
        "ACCOUNT_ID": "string", "BUSINESSEFFECTIVEDATE": "timestamp",
        "CREDIT_LIMIT_AMT": "double", "_UTILIZATION_RATE": "double",
        "PAST_DUE_INDICATO_CD": "string", "DELINQUENCY_CNT": "bigint",
    },
    "TKQ_ACCOUNT_BALANCE": {
        "ACCOUNT_ID": "string", "BUSINESSEFFECTIVEDATE": "timestamp",
        "CURRENT_BALANCE_AMT": "double", "AVAILABLE_TO_BUY_AMT": "double", "OVERLIMIT_AMT": "double",
    },
    "TRADELINES": {"account_number": "string", "REQ-CIF-KEY": "string", "REQ-CIF-TIE-BREAKER": "bigint"},
}


class GeneratedValidationTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.row_factory = sqlite3.Row
        self.db.create_function("GREATEST", -1, max)
        self.db.create_function("FLOOR", 1, lambda value: None if value is None else math.floor(value))
        self.db.create_function("ISNAN", 1, lambda value: value is not None and math.isnan(value))
        self.db.create_function("format_string", 2, lambda pattern, value: None if value is None else pattern % value)
        self.schemas = {name: columns.copy() for name, columns in SCHEMAS.items()}
        self.versions = dict.fromkeys((*self.schemas, AUDIT_TABLE, RELATIONSHIP_AUDIT_TABLE), 0)
        self.spark = SimpleNamespace(
            catalog=SimpleNamespace(tableExists=lambda name: name.rsplit(".", 1)[-1] in self.versions),
            table=self.table,
            sql=self.sql,
        )
        self.db.executescript("""
            CREATE TABLE PERSON (PARTY_ID, BIRTH_DT, SINCE_DT, OPTIONAL_CD);
            INSERT INTO PERSON VALUES ('P00000001', '1980-01-01', '2020-01-01', NULL),
                                      ('P00000002', NULL, NULL, NULL);
            CREATE TABLE CUSTOMER_ACCOUNT_REL (PARTY_ID, ACCT_ID);
            INSERT INTO CUSTOMER_ACCOUNT_REL VALUES ('P00000001', 'A000000001'),
                                                     ('P00000002', 'A000000002');
            CREATE TABLE TKQ_ACCOUNT (
                ACCOUNT_ID, BUSINESSEFFECTIVEDATE, CREDIT_LIMIT_AMT, _UTILIZATION_RATE,
                PAST_DUE_INDICATO_CD, DELINQUENCY_CNT
            );
            INSERT INTO TKQ_ACCOUNT VALUES ('A000000001', '2026-10-01', 100, 0.30, 'N', 0),
                                           ('A000000002', '2026-10-02', 100, 1.25, 'Y', 2);
            CREATE TABLE TKQ_ACCOUNT_BALANCE (
                ACCOUNT_ID, BUSINESSEFFECTIVEDATE, CURRENT_BALANCE_AMT, AVAILABLE_TO_BUY_AMT, OVERLIMIT_AMT
            );
            INSERT INTO TKQ_ACCOUNT_BALANCE VALUES ('A000000002', '2026-10-02', 125, 0, 25),
                                                   ('A000000001', '2026-10-01', 30, 70, 0);
            CREATE TABLE TRADELINES (account_number, "REQ-CIF-KEY", "REQ-CIF-TIE-BREAKER");
            INSERT INTO TRADELINES VALUES ('TL0000000001', 'P00000001', 1);
            CREATE TABLE rule_execution_log (
                generation_id, source_run_id, proposal_id, batch_id, target_table,
                target_column, approved, implemented, reason
            );
            INSERT INTO rule_execution_log VALUES
                ('generated', 'source', 'proposal-example', 'batch-example', 'TKQ_ACCOUNT_BALANCE',
                 'UNSUPPORTED_AMT', TRUE, FALSE, 'no_implementation');
            CREATE TABLE CUSTOMER_RELATIONSHIP (FROM_PARTY_ID, TO_PARTY_ID, FROM_TO_CUST_RELATN_CD, TO_FROM_CUST_RELATN_CD, ownership_percentage, OWNED_BUS_SINCE_DT);
            INSERT INTO CUSTOMER_RELATIONSHIP VALUES ('P00000001','P00000002','PARENT','CHILD',25,NULL);
            CREATE TABLE customer_relationship_generation_log (generation_id, source_run_id, seed, implementation_version, plan_json);
            CREATE TABLE profile_runs (run_id, profile_type, status, completed_at);
            INSERT INTO profile_runs VALUES ('source','SOURCE','COMPLETED','2026-01-01');
            CREATE TABLE customer_relationship_summary (run_id, profile_type, self_rows);
            INSERT INTO customer_relationship_summary VALUES ('source','SOURCE',0);
        """)
        self.relationship_plan = {"source_run_id": "source", "seed": 42, "self_allowed": False,
                                  "row_count": 1, "self_rows": 0, "generated_person_count": 2,
                                  "implementation_version": "customer_relationships_v1", "profile_signature": "fabricated",
                                  "null_counts": {"FROM_TO_CUST_RELATN_CD": 0, "TO_FROM_CUST_RELATN_CD": 0,
                                                  "ownership_percentage": 0, "OWNED_BUS_SINCE_DT": 1}}
        self.db.execute("INSERT INTO customer_relationship_generation_log VALUES ('generated','source',42,'customer_relationships_v1',?)", (json.dumps(self.relationship_plan),))
        self.counts = dict.fromkeys(self.schemas, 2) | {"TRADELINES": 1, "CUSTOMER_RELATIONSHIP": 1}

    def table(self, name):
        fields = [
            SimpleNamespace(name=column, dataType=SimpleNamespace(simpleString=lambda type=type: type))
            for column, type in self.schemas[name.rsplit(".", 1)[-1]].items()
        ]
        return SimpleNamespace(schema=SimpleNamespace(fields=fields))

    def sql(self, sql, args=None):
        sql = sql.strip().replace(GENERATED_SCHEMA + ".", "").replace("workspace.synthetic_profile.", "")
        if sql.startswith("DESCRIBE DETAIL"):
            name = sql.split()[2]
            return SimpleNamespace(first=lambda: {"format": "delta", "id": name + "-id"})
        if sql.startswith("DESCRIBE HISTORY"):
            name = sql.split()[2]
            return SimpleNamespace(first=lambda: {"version": self.versions[name]})
        sql = re.sub(r"CAST\((`[^`]+`) AS DATE\)", r"DATE(\1)", sql)
        sql = sql.replace(" AS STRING)", " AS TEXT)")
        result = self.db.execute(sql.replace("TRY_CAST(", "CAST("), args or {})
        return SimpleNamespace(first=result.fetchone, collect=result.fetchall)

    def validate(self):
        return validate_generated_batch(
            self.spark, SCHEMAS, self.counts, "generated", "source", expected_audit_rows=1,
        )

    def test_valid_batch_returns_versions_and_reports_unimplemented_approvals(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            versions = self.validate()
            check_validated_versions(self.spark, versions)

        self.assertEqual(set(versions), set(self.schemas) | {AUDIT_TABLE, RELATIONSHIP_AUDIT_TABLE})
        self.assertIn("2/2 accounts, 2/2 balances", output.getvalue())
        self.assertIn("Approved rules without a matching implementation: 1", output.getvalue())
        self.assertIn("proposal-example, batch batch-example", output.getvalue())

    def test_applied_conditional_rule_rejects_unsupported_saved_combinations(self):
        for column in ("ACCOUNT_TYPE_CD", "CLIENT_PRODUCT_CD"):
            self.db.execute(f"ALTER TABLE TKQ_ACCOUNT ADD COLUMN {column}")
            self.schemas["TKQ_ACCOUNT"][column] = "string"
        self.db.execute("UPDATE TKQ_ACCOUNT SET ACCOUNT_TYPE_CD='TYPE', CLIENT_PRODUCT_CD='PRODUCT'")
        self.db.executescript("""
            ALTER TABLE rule_execution_log ADD COLUMN applied;
            ALTER TABLE rule_execution_log ADD COLUMN implementation_name;
            UPDATE rule_execution_log SET target_table='TKQ_ACCOUNT', target_column='CLIENT_PRODUCT_CD',
                approved=TRUE, implemented=TRUE, applied=TRUE, implementation_name='conditional_categorical_v1';
            CREATE TABLE categorical_conditional_profile
                (run_id, profile_type, logical_table_name, parent_column, child_column, parent_value, child_value, record_count);
            INSERT INTO categorical_conditional_profile VALUES
                ('source','SOURCE','TKQ_ACCOUNT','ACCOUNT_TYPE_CD','CLIENT_PRODUCT_CD','TYPE','PRODUCT',100),
                ('other','SOURCE','TKQ_ACCOUNT','ACCOUNT_TYPE_CD','CLIENT_PRODUCT_CD','TYPE','UNSUPPORTED',100),
                ('source','GENERATED','TKQ_ACCOUNT','ACCOUNT_TYPE_CD','CLIENT_PRODUCT_CD','TYPE','UNSUPPORTED',100);
        """)
        with contextlib.redirect_stdout(io.StringIO()):
            self.validate()
            self.db.execute("UPDATE TKQ_ACCOUNT SET CLIENT_PRODUCT_CD='UNSUPPORTED' WHERE ACCOUNT_ID='A000000001'")
            with self.assertRaisesRegex(GeneratedValidationError, "1 SOURCE-unsupported conditional combinations"):
                self.validate()

    def test_incomplete_and_changed_outputs_are_rejected(self):
        with contextlib.redirect_stdout(io.StringIO()):
            versions = self.validate()
        with self.assertRaisesRegex(GeneratedValidationError, "no validation record"):
            check_validated_versions(self.spark, None)
        self.versions["TKQ_ACCOUNT"] += 1
        with self.assertRaisesRegex(GeneratedValidationError, "changed since validation: TKQ_ACCOUNT"):
            check_validated_versions(self.spark, versions)
        del self.versions["TKQ_ACCOUNT_BALANCE"]
        with self.assertRaisesRegex(GeneratedValidationError, "Missing generated Delta table"):
            check_validated_versions(self.spark, versions)

    def test_schema_validation_checks_missing_columns_and_compatible_types(self):
        self.schemas["TKQ_ACCOUNT"]["CREDIT_LIMIT_AMT"] = "decimal(12,2)"
        with contextlib.redirect_stdout(io.StringIO()):
            self.validate()
        self.schemas["TKQ_ACCOUNT"]["CREDIT_LIMIT_AMT"] = "string"
        del self.schemas["TKQ_ACCOUNT"]["PAST_DUE_INDICATO_CD"]
        with self.assertRaisesRegex(GeneratedValidationError, "CREDIT_LIMIT_AMT has type string"):
            self.validate()

    def test_snapshot_dates_must_use_the_same_type(self):
        self.schemas["TKQ_ACCOUNT_BALANCE"]["BUSINESSEFFECTIVEDATE"] = "date"
        with self.assertRaisesRegex(GeneratedValidationError, "same type"):
            self.validate()

    def test_saved_temporal_violations_within_the_same_year_are_rejected(self):
        columns = ("OPEN_DT", "CLOSE_DT", "LAST_PAYMENT_DT", "LAST_PURCHASE_DT")
        for column in columns:
            self.db.execute(f"ALTER TABLE TKQ_ACCOUNT ADD COLUMN {column}")
            self.schemas["TKQ_ACCOUNT"][column] = "timestamp"
        self.db.execute("UPDATE TKQ_ACCOUNT SET OPEN_DT='2026-01-10', CLOSE_DT='2026-09-01', LAST_PAYMENT_DT='2026-09-01', LAST_PURCHASE_DT='2026-09-01'")
        with contextlib.redirect_stdout(io.StringIO()):
            self.validate()
        for update, metric in (
            ("CLOSE_DT='2026-01-01'", "OPEN_DT<=CLOSE_DT"),
            ("LAST_PAYMENT_DT='2026-01-01'", "OPEN_DT<=LAST_PAYMENT_DT"),
            ("LAST_PURCHASE_DT='2026-12-01'", "LAST_PURCHASE_DT<=BUSINESSEFFECTIVEDATE"),
        ):
            with self.subTest(metric=metric), contextlib.redirect_stdout(io.StringIO()):
                self.db.execute("SAVEPOINT temporal")
                try:
                    self.db.execute(f"UPDATE TKQ_ACCOUNT SET {update}")
                    with self.assertRaisesRegex(GeneratedValidationError, re.escape(metric)):
                        self.validate()
                finally:
                    self.db.execute("ROLLBACK TO temporal")
                    self.db.execute("RELEASE temporal")

    def test_saved_date_null_counts_must_match_the_source_plan(self):
        with contextlib.redirect_stdout(io.StringIO()):
            validate_generated_batch(self.spark, SCHEMAS, self.counts, "generated", "source", 1,
                                     expected_date_null_counts={"PERSON": {"BIRTH_DT": 1, "SINCE_DT": 1}})
            with self.assertRaisesRegex(GeneratedValidationError, "SOURCE null plan"):
                validate_generated_batch(self.spark, SCHEMAS, self.counts, "generated", "source", 1,
                                         expected_date_null_counts={"PERSON": {"BIRTH_DT": 0}})
            with self.assertRaisesRegex(GeneratedValidationError, "saved temporal column"):
                validate_generated_batch(self.spark, SCHEMAS, self.counts, "generated", "source", 1,
                                         expected_date_null_counts={"PERSON": {"OPTIONAL_CD": 0}})

    def test_customer_relationship_integrity_self_policy_percentages_nulls_and_audit(self):
        cases = (
            ("UPDATE CUSTOMER_RELATIONSHIP SET TO_PARTY_ID='missing'", "nonexistent FROM/TO"),
            ("UPDATE CUSTOMER_RELATIONSHIP SET FROM_PARTY_ID=NULL", "null or nonexistent"),
            ("UPDATE CUSTOMER_RELATIONSHIP SET TO_PARTY_ID=FROM_PARTY_ID", "self-relationships"),
            ("UPDATE CUSTOMER_RELATIONSHIP SET ownership_percentage=101", "ownership percentages"),
            ("UPDATE CUSTOMER_RELATIONSHIP SET FROM_TO_CUST_RELATN_CD=NULL", "null plan"),
            ("DELETE FROM customer_relationship_generation_log", "exactly once"),
            ("UPDATE customer_relationship_generation_log SET source_run_id='wrong'", "exactly once"),
            ("UPDATE customer_relationship_summary SET profile_type='GENERATED'", "pinned completed SOURCE"),
        )
        for update, message in cases:
            with self.subTest(update=update), contextlib.redirect_stdout(io.StringIO()):
                self.db.execute("SAVEPOINT relationship")
                try:
                    self.db.execute(update)
                    with self.assertRaisesRegex(GeneratedValidationError, message):
                        self.validate()
                finally:
                    self.db.execute("ROLLBACK TO relationship")
                    self.db.execute("RELEASE relationship")
        del self.versions["CUSTOMER_RELATIONSHIP"]
        with self.assertRaisesRegex(GeneratedValidationError, "Missing generated Delta table"):
            self.validate()

    def test_empty_customer_relationship_output_and_source_supported_self_links(self):
        self.db.execute("UPDATE CUSTOMER_RELATIONSHIP SET TO_PARTY_ID=FROM_PARTY_ID")
        self.db.execute("UPDATE customer_relationship_summary SET self_rows=1")
        self.relationship_plan.update(self_allowed=True, self_rows=1)
        self.db.execute("UPDATE customer_relationship_generation_log SET plan_json=?", (json.dumps(self.relationship_plan),))
        with contextlib.redirect_stdout(io.StringIO()):
            self.validate()
        self.db.execute("DELETE FROM CUSTOMER_RELATIONSHIP")
        self.relationship_plan.update(row_count=0, self_rows=0, null_counts=dict.fromkeys(self.relationship_plan["null_counts"], 0))
        self.counts["CUSTOMER_RELATIONSHIP"] = 0
        self.db.execute("UPDATE customer_relationship_generation_log SET plan_json=?", (json.dumps(self.relationship_plan),))
        with contextlib.redirect_stdout(io.StringIO()):
            versions = self.validate()
        self.assertIn("CUSTOMER_RELATIONSHIP", versions)

    def test_rejects_bad_counts_keys_invariants_and_audit_rows(self):
        cases = (
            ("DELETE FROM TKQ_ACCOUNT_BALANCE WHERE ACCOUNT_ID = 'A000000001'", "row count differs"),
            ("UPDATE TKQ_ACCOUNT_BALANCE SET BUSINESSEFFECTIVEDATE = NULL", "join coverage"),
            ("UPDATE PERSON SET PARTY_ID = 'P00000003' WHERE PARTY_ID = 'P00000001'", "out-of-sequence"),
            ("UPDATE TKQ_ACCOUNT_BALANCE SET ACCOUNT_ID = 'A000000001'", "duplicate"),
            ("UPDATE CUSTOMER_ACCOUNT_REL SET PARTY_ID = 'unknown'", "orphan_account_links"),
            ('UPDATE TRADELINES SET "REQ-CIF-TIE-BREAKER" = 2', "invalid_tradeline_links"),
            ("UPDATE PERSON SET SINCE_DT = '1970-01-01'", "violate SINCE_DT"),
            ("UPDATE TKQ_ACCOUNT_BALANCE SET AVAILABLE_TO_BUY_AMT = NULL", "invalid_amounts"),
            ("UPDATE TKQ_ACCOUNT SET _UTILIZATION_RATE = 0", "invalid_utilization"),
            ("UPDATE TKQ_ACCOUNT SET DELINQUENCY_CNT = 1.5 WHERE PAST_DUE_INDICATO_CD = 'Y'", "invalid_delinquency"),
            ("UPDATE rule_execution_log SET source_run_id = 'wrong-source'", "saved rule audit"),
        )
        for update, message in cases:
            with self.subTest(update=update), contextlib.redirect_stdout(io.StringIO()):
                self.db.execute("SAVEPOINT invalid")
                try:
                    self.db.execute(update)
                    with self.assertRaisesRegex(GeneratedValidationError, message):
                        self.validate()
                finally:
                    self.db.execute("ROLLBACK TO invalid")
                    self.db.execute("RELEASE invalid")

    def test_pinned_schema_preserves_noncritical_columns_and_overrides_synthetic_keys(self):
        profile = [
            SimpleNamespace(logical_table_name=name, column_name=column, data_type="BIGINT")
            for name, columns in SCHEMAS.items() for column in columns
        ]
        expected = expected_generated_schema(SimpleNamespace(itertuples=lambda index: profile))
        self.assertEqual(expected["PERSON"]["PARTY_ID"], "string")
        self.assertEqual(expected["PERSON"]["OPTIONAL_CD"], "BIGINT")
        source_type = SimpleNamespace(simpleString=lambda: "decimal(12,2)")
        self.assertIs(null_padding_type("double", source_type), source_type)
        self.assertEqual(null_padding_type("string", source_type), "string")
