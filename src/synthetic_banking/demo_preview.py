"""Bounded synthetic-only preview projection, called inside the gated demo export."""
from datetime import date, datetime
import json
import math
import re

ROW_LIMIT = 15
MAX_BYTES = 96 * 1024


def column(key, label, kind, description):
    return dict(key=key, label=label, kind=kind, description=description)


SPEC = {
    "PERSON": dict(label="Customers", description="Fabricated customer profiles.", total_columns=19,
        relationship="Customer ID links a person to account links, customer relationships and tradelines.", columns=[
        column("PARTY_ID", "Customer ID", "person_id", "Synthetic identifier for a customer; used to connect records across tables."),
        column("CLIENT_STAT_CD", "Customer status", "code", "Development status code: A = active, C = closed, D = deceased."),
        column("CUST_TYPE_CD", "Customer type", "code", "Development customer type; IND denotes an individual."),
        column("EMP_TYPE_CD", "Employment", "code", "Employment category: FT full-time, PT part-time, SELF self-employed, UNEMP unemployed, RET retired, STU student."),
        column("OCCUP_CAT_CD", "Occupation group", "code", "Broad occupation code: PRO professional, MGT management, TRD trades, SRV service, RET retired, STU student."),
        column("PREF_LANG_CD", "Language", "code", "Preferred-language code; EN = English, FR = French.")]),
    "CUSTOMER_ACCOUNT_REL": dict(label="Customer–account links", description="Links customers to internal accounts.", total_columns=6,
        relationship="Customer ID references PERSON. Account ID references TKQ_ACCOUNT. One customer can have several accounts.", columns=[
        column("PARTY_ID", "Customer ID", "person_id", "References the synthetic customer in PERSON."),
        column("ACCT_ID", "Account ID", "account_id", "References the synthetic internal account in TKQ_ACCOUNT."),
        column("ACCT_SUBSYS_MNEMONIC_CD", "Account system", "code", "Development mnemonic for the account system."),
        column("PRIMARY_OWNERSHIP_FLAG", "Primary owner", "code", "Y indicates primary ownership; N indicates otherwise."),
        column("PROD_CD", "Product", "code", "Product code recorded on the customer–account link."),
        column("RELATN_TYPE_CD", "Link type", "code", "Type of customer-to-account relationship; PRIMARY denotes the primary link.")]),
    "CUSTOMER_RELATIONSHIP": dict(label="Customer relationships", description="Directed relationships between synthetic customers.", total_columns=9,
        relationship="Both From customer and To customer reference PERSON. The two relationship codes describe the two directions; repeated pairs may exist.", columns=[
        column("FROM_PARTY_ID", "From customer", "person_id", "Synthetic customer at the starting end of this relationship."),
        column("TO_PARTY_ID", "To customer", "person_id", "Synthetic customer at the other end of this relationship."),
        column("FROM_TO_CUST_RELATN_CD", "From → to", "code", "Relationship type in the forward direction."),
        column("TO_FROM_CUST_RELATN_CD", "To → from", "code", "Relationship type in the reverse direction."),
        column("ownership_percentage", "Ownership %", "number", "Optional ownership percentage. Not recorded means the generated field is null."),
        column("OWNED_BUS_SINCE_DT", "Ownership since", "date", "Optional date associated with business ownership; not a customer birth date.")]),
    "TKQ_ACCOUNT": dict(label="Accounts", description="Internal account snapshots and product details.", total_columns=100,
        relationship="Account ID plus Effective date identify a snapshot and match the balance table. Customer–account links identify its customer.", columns=[
        column("ACCOUNT_ID", "Account ID", "account_id", "Synthetic internal account identifier; not a payment-card number."),
        column("ACCOUNT_TYPE_CD", "Account type", "code", "Development account type, such as VISA or MC."),
        column("CLIENT_PRODUCT_CD", "Client product", "code", "Product category sampled conditionally when its reviewed implementation applies."),
        column("TSYS_PRODUCT_CD", "System product", "code", "Account-system product code associated with the client product."),
        column("CREDIT_LIMIT_AMT", "Credit limit", "number", "Saved synthetic credit limit in native demo amount units."),
        column("PAST_DUE_INDICATO_CD", "Past due", "code", "Y indicates a generated past-due account; N indicates otherwise."),
        column("OPEN_DT", "Opened", "date", "Synthetic account opening date."),
        column("BUSINESSEFFECTIVEDATE", "Effective date", "date", "Snapshot date shared with the corresponding account balance; use it with Account ID to join.")]),
    "TKQ_ACCOUNT_BALANCE": dict(label="Account balances", description="Amounts for the corresponding account snapshots.", total_columns=48,
        relationship="Join TKQ_ACCOUNT using both Account ID and Effective date. The two fields must agree for the same snapshot.", columns=[
        column("ACCOUNT_ID", "Account ID", "account_id", "References the synthetic account in TKQ_ACCOUNT."),
        column("BUSINESSEFFECTIVEDATE", "Effective date", "date", "Shared snapshot date; join together with Account ID."),
        column("CURRENT_BALANCE_AMT", "Balance", "number", "Saved synthetic current balance in native demo amount units."),
        column("AVAILABLE_TO_BUY_AMT", "Available credit", "number", "Maximum of credit limit minus balance and zero."),
        column("OVERLIMIT_AMT", "Over limit", "number", "Maximum of balance minus credit limit and zero.")]),
    "TRADELINES": dict(label="Tradelines", description="External-credit-style records linked to customers.", total_columns=38,
        relationship="Customer ID references PERSON. Tradeline ID is separate from the internal Account ID and does not join to TKQ_ACCOUNT.", columns=[
        column("account_number", "Tradeline ID", "tradeline_id", "Synthetic identifier for an external-credit-style record; not an actual account number."),
        column("REQ-CIF-KEY", "Customer ID", "person_id", "References the synthetic customer in PERSON."),
        column("account_type_code", "Credit type", "code", "Development credit category: CC credit card, LOC line of credit, AUTO vehicle, MTG mortgage, INST instalment."),
        column("credit_limit_amount", "Credit limit", "number", "Synthetic credit limit in native demo amount units."),
        column("current_balance_amount", "Balance", "number", "Synthetic current balance in native demo amount units."),
        column("account_open_date", "Opened", "date", "Synthetic tradeline opening date."),
        column("account_closed_indicator", "Closed", "code", "Y indicates a closed generated tradeline; N indicates otherwise.")]),
}


def config():
    return dict(schema_version="1.0", row_limit=ROW_LIMIT, max_bytes=MAX_BYTES, tables=SPEC)


def preview_value(spec, value):
    from synthetic_banking.demo_export import inspect_value, fail
    if isinstance(value, (datetime, date)):
        value = value.isoformat()
    inspect_value(spec["key"], value)
    kind = spec["kind"]
    if value is None:
        if kind.endswith("_id"):
            fail("preview_key_missing")
        return None
    patterns = {"person_id": r"P[0-9]{8}", "account_id": r"A[0-9]{9}", "tradeline_id": r"TL[0-9]{10}",
                "code": r"[A-Za-z0-9 _/.-]{1,32}",
                "date": r"[0-9]{4}-[0-9]{2}-[0-9]{2}(?:T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|\+00:00)?)?"}
    if kind == "number":
        if type(value) not in (int, float) or not math.isfinite(value):
            fail("invalid_preview_number")
    elif not isinstance(value, str) or not re.fullmatch(patterns[kind], value):
        fail("invalid_preview_value")
    if kind == "date":
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            fail("invalid_preview_date")
    return value


def build_preview(frames, counts, *, dataset_version, generated_at, privacy_status):
    """Only call after exact fabricated-origin verification and content screening."""
    from synthetic_banking.demo_export import KEYS, fail
    if (not re.fullmatch(r"sage-demo-v[1-9][0-9]*(?:\.[0-9]+)*", dataset_version)
            or privacy_status not in {"PASS", "REVIEW_REQUIRED"} or set(frames) != set(SPEC) or set(counts) != set(SPEC)):
        fail("preview_provenance_required")
    result = dict(schema_version="1.0", release_mode="DEMO_ONLY", baseline="FABRICATED_DEVELOPMENT",
                  dataset_version=dataset_version, generated_at=generated_at, privacy_status=privacy_status,
                  preview_row_limit=ROW_LIMIT, tables=[])
    for name, spec in SPEC.items():
        fields = [c["key"] for c in spec["columns"]]
        if len(frames[name].columns) != spec["total_columns"] or not set(fields).issubset(frames[name].columns):
            fail("preview_schema_not_reviewed")
        if type(counts[name]) is not int or not 0 <= counts[name] <= 250_000:
            fail("preview_count_unavailable")
        # The same key order as the CSV export. At most 15 selected records/table
        # are collected; the complete tables are never put into the browser JSON.
        selected = frames[name].orderBy(*KEYS[name]).select(*fields).limit(ROW_LIMIT).collect()
        if any(len(row) != len(fields) for row in selected):
            fail("preview_row_width_mismatch")
        rows = [[preview_value(column, value) for column, value in zip(spec["columns"], row)] for row in selected]
        if len(rows) != min(ROW_LIMIT, counts[name]) or any(len(row) != len(fields) for row in rows):
            fail("preview_row_count_mismatch")
        result["tables"].append(dict(name=name, total_rows=counts[name], total_columns=spec["total_columns"], columns=fields, rows=rows))
    raw = json.dumps(result, allow_nan=False, separators=(",", ":")).encode("utf-8")+b"\n"
    if len(raw) > MAX_BYTES:
        fail("preview_size_limit")
    return raw


def preview_schema():
    def obj(properties):
        return dict(type="object", properties=properties, required=list(properties), additionalProperties=False)
    table_specs = []
    patterns = {"person_id": "^P[0-9]{8}$", "account_id": "^A[0-9]{9}$", "tradeline_id": "^TL[0-9]{10}$",
                "code": "^[A-Za-z0-9 _/.-]{1,32}$", "date": "^[0-9]{4}-[0-9]{2}-[0-9]{2}(T[0-9:.]+(Z|\\+00:00)?)?$"}
    for name, spec in SPEC.items():
        values = []
        for c in spec["columns"]:
            kind = c["kind"]
            field = dict(type="number") if kind == "number" else dict(type="string", pattern=patterns[kind])
            values.append(field if kind.endswith("_id") else dict(anyOf=[field, dict(type="null")]))
        row = dict(type="array", prefixItems=values, items=False, minItems=len(values), maxItems=len(values))
        table_specs.append(obj(dict(name=dict(const=name), total_rows=dict(type="integer",minimum=0,maximum=250_000),
            total_columns=dict(const=spec["total_columns"]), columns=dict(const=[c["key"] for c in spec["columns"]]),
            rows=dict(type="array",items=row,maxItems=ROW_LIMIT))))
    return {"$schema":"https://json-schema.org/draft/2020-12/schema", **obj(dict(
        schema_version=dict(const="1.0"),release_mode=dict(const="DEMO_ONLY"),baseline=dict(const="FABRICATED_DEVELOPMENT"),
        dataset_version=dict(type="string",pattern=r"^sage-demo-v[1-9][0-9]*(\.[0-9]+)*$"),
        generated_at=dict(type="string",format="date-time"),privacy_status=dict(enum=["PASS","REVIEW_REQUIRED"]),
        preview_row_limit=dict(const=ROW_LIMIT),tables=dict(type="array",prefixItems=table_specs,items=False,minItems=6,maxItems=6)))}
