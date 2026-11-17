import contextlib
import io
import math
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
)


SCHEMAS = {
    "PERSON": {"PARTY_ID": "string", "BIRTH_DT": "date", "SINCE_DT": "timestamp", "OPTIONAL_CD": "string"},
    "CUSTOMER_ACCOUNT_REL": {"PARTY_ID": "string", "ACCT_ID": "string"},
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
        self.db.create_function("format_string", 2, lambda pattern, value: None if value is None else pattern % value)
        self.schemas = {name: columns.copy() for name, columns in SCHEMAS.items()}
        self.versions = dict.fromkeys((*self.schemas, AUDIT_TABLE), 0)
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
        """)
        self.counts = dict.fromkeys(self.schemas, 2) | {"TRADELINES": 1}

    def table(self, name):
        fields = [
            SimpleNamespace(name=column, dataType=SimpleNamespace(simpleString=lambda type=type: type))
            for column, type in self.schemas[name.rsplit(".", 1)[-1]].items()
        ]
        return SimpleNamespace(schema=SimpleNamespace(fields=fields))

    def sql(self, sql, args=None):
        sql = sql.strip().replace(GENERATED_SCHEMA + ".", "")
        if sql.startswith("DESCRIBE DETAIL"):
            name = sql.split()[2]
            return SimpleNamespace(first=lambda: {"format": "delta", "id": name + "-id"})
        if sql.startswith("DESCRIBE HISTORY"):
            name = sql.split()[2]
            return SimpleNamespace(first=lambda: {"version": self.versions[name]})
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

        self.assertEqual(set(versions), set(self.schemas) | {AUDIT_TABLE})
        self.assertIn("2/2 accounts, 2/2 balances", output.getvalue())
        self.assertIn("Approved rules without a matching implementation: 1", output.getvalue())
        self.assertIn("proposal-example, batch batch-example", output.getvalue())

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
