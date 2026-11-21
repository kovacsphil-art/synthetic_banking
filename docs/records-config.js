/* Generated from demo_preview.py; no runtime or row data. */
(() => { const config = {
  "schema_version": "1.0",
  "row_limit": 15,
  "max_bytes": 98304,
  "tables": {
    "PERSON": {
      "label": "Customers",
      "description": "Fabricated customer profiles.",
      "total_columns": 19,
      "relationship": "Customer ID links a person to account links, customer relationships and tradelines.",
      "columns": [
        {
          "key": "PARTY_ID",
          "label": "Customer ID",
          "kind": "person_id",
          "description": "Synthetic identifier for a customer; used to connect records across tables."
        },
        {
          "key": "CLIENT_STAT_CD",
          "label": "Customer status",
          "kind": "code",
          "description": "Development status code: A = active, C = closed, D = deceased."
        },
        {
          "key": "CUST_TYPE_CD",
          "label": "Customer type",
          "kind": "code",
          "description": "Development customer type; IND denotes an individual."
        },
        {
          "key": "EMP_TYPE_CD",
          "label": "Employment",
          "kind": "code",
          "description": "Employment category: FT full-time, PT part-time, SELF self-employed, UNEMP unemployed, RET retired, STU student."
        },
        {
          "key": "OCCUP_CAT_CD",
          "label": "Occupation group",
          "kind": "code",
          "description": "Broad occupation code: PRO professional, MGT management, TRD trades, SRV service, RET retired, STU student."
        },
        {
          "key": "PREF_LANG_CD",
          "label": "Language",
          "kind": "code",
          "description": "Preferred-language code; EN = English, FR = French."
        }
      ]
    },
    "CUSTOMER_ACCOUNT_REL": {
      "label": "Customer–account links",
      "description": "Links customers to internal accounts.",
      "total_columns": 6,
      "relationship": "Customer ID references PERSON. Account ID references TKQ_ACCOUNT. One customer can have several accounts.",
      "columns": [
        {
          "key": "PARTY_ID",
          "label": "Customer ID",
          "kind": "person_id",
          "description": "References the synthetic customer in PERSON."
        },
        {
          "key": "ACCT_ID",
          "label": "Account ID",
          "kind": "account_id",
          "description": "References the synthetic internal account in TKQ_ACCOUNT."
        },
        {
          "key": "ACCT_SUBSYS_MNEMONIC_CD",
          "label": "Account system",
          "kind": "code",
          "description": "Development mnemonic for the account system."
        },
        {
          "key": "PRIMARY_OWNERSHIP_FLAG",
          "label": "Primary owner",
          "kind": "code",
          "description": "Y indicates primary ownership; N indicates otherwise."
        },
        {
          "key": "PROD_CD",
          "label": "Product",
          "kind": "code",
          "description": "Product code recorded on the customer–account link."
        },
        {
          "key": "RELATN_TYPE_CD",
          "label": "Link type",
          "kind": "code",
          "description": "Type of customer-to-account relationship; PRIMARY denotes the primary link."
        }
      ]
    },
    "CUSTOMER_RELATIONSHIP": {
      "label": "Customer relationships",
      "description": "Directed relationships between synthetic customers.",
      "total_columns": 9,
      "relationship": "Both From customer and To customer reference PERSON. The two relationship codes describe the two directions; repeated pairs may exist.",
      "columns": [
        {
          "key": "FROM_PARTY_ID",
          "label": "From customer",
          "kind": "person_id",
          "description": "Synthetic customer at the starting end of this relationship."
        },
        {
          "key": "TO_PARTY_ID",
          "label": "To customer",
          "kind": "person_id",
          "description": "Synthetic customer at the other end of this relationship."
        },
        {
          "key": "FROM_TO_CUST_RELATN_CD",
          "label": "From → to",
          "kind": "code",
          "description": "Relationship type in the forward direction."
        },
        {
          "key": "TO_FROM_CUST_RELATN_CD",
          "label": "To → from",
          "kind": "code",
          "description": "Relationship type in the reverse direction."
        },
        {
          "key": "ownership_percentage",
          "label": "Ownership %",
          "kind": "number",
          "description": "Optional ownership percentage. Not recorded means the generated field is null."
        },
        {
          "key": "OWNED_BUS_SINCE_DT",
          "label": "Ownership since",
          "kind": "date",
          "description": "Optional date associated with business ownership; not a customer birth date."
        }
      ]
    },
    "TKQ_ACCOUNT": {
      "label": "Accounts",
      "description": "Internal account snapshots and product details.",
      "total_columns": 100,
      "relationship": "Account ID plus Effective date identify a snapshot and match the balance table. Customer–account links identify its customer.",
      "columns": [
        {
          "key": "ACCOUNT_ID",
          "label": "Account ID",
          "kind": "account_id",
          "description": "Synthetic internal account identifier; not a payment-card number."
        },
        {
          "key": "ACCOUNT_TYPE_CD",
          "label": "Account type",
          "kind": "code",
          "description": "Development account type, such as VISA or MC."
        },
        {
          "key": "CLIENT_PRODUCT_CD",
          "label": "Client product",
          "kind": "code",
          "description": "Product category sampled conditionally when its reviewed implementation applies."
        },
        {
          "key": "TSYS_PRODUCT_CD",
          "label": "System product",
          "kind": "code",
          "description": "Account-system product code associated with the client product."
        },
        {
          "key": "CREDIT_LIMIT_AMT",
          "label": "Credit limit",
          "kind": "number",
          "description": "Saved synthetic credit limit in native demo amount units."
        },
        {
          "key": "PAST_DUE_INDICATO_CD",
          "label": "Past due",
          "kind": "code",
          "description": "Y indicates a generated past-due account; N indicates otherwise."
        },
        {
          "key": "OPEN_DT",
          "label": "Opened",
          "kind": "date",
          "description": "Synthetic account opening date."
        },
        {
          "key": "BUSINESSEFFECTIVEDATE",
          "label": "Effective date",
          "kind": "date",
          "description": "Snapshot date shared with the corresponding account balance; use it with Account ID to join."
        }
      ]
    },
    "TKQ_ACCOUNT_BALANCE": {
      "label": "Account balances",
      "description": "Amounts for the corresponding account snapshots.",
      "total_columns": 48,
      "relationship": "Join TKQ_ACCOUNT using both Account ID and Effective date. The two fields must agree for the same snapshot.",
      "columns": [
        {
          "key": "ACCOUNT_ID",
          "label": "Account ID",
          "kind": "account_id",
          "description": "References the synthetic account in TKQ_ACCOUNT."
        },
        {
          "key": "BUSINESSEFFECTIVEDATE",
          "label": "Effective date",
          "kind": "date",
          "description": "Shared snapshot date; join together with Account ID."
        },
        {
          "key": "CURRENT_BALANCE_AMT",
          "label": "Balance",
          "kind": "number",
          "description": "Saved synthetic current balance in native demo amount units."
        },
        {
          "key": "AVAILABLE_TO_BUY_AMT",
          "label": "Available credit",
          "kind": "number",
          "description": "Maximum of credit limit minus balance and zero."
        },
        {
          "key": "OVERLIMIT_AMT",
          "label": "Over limit",
          "kind": "number",
          "description": "Maximum of balance minus credit limit and zero."
        }
      ]
    },
    "TRADELINES": {
      "label": "Tradelines",
      "description": "External-credit-style records linked to customers.",
      "total_columns": 38,
      "relationship": "Customer ID references PERSON. Tradeline ID is separate from the internal Account ID and does not join to TKQ_ACCOUNT.",
      "columns": [
        {
          "key": "account_number",
          "label": "Tradeline ID",
          "kind": "tradeline_id",
          "description": "Synthetic identifier for an external-credit-style record; not an actual account number."
        },
        {
          "key": "REQ-CIF-KEY",
          "label": "Customer ID",
          "kind": "person_id",
          "description": "References the synthetic customer in PERSON."
        },
        {
          "key": "account_type_code",
          "label": "Credit type",
          "kind": "code",
          "description": "Development credit category: CC credit card, LOC line of credit, AUTO vehicle, MTG mortgage, INST instalment."
        },
        {
          "key": "credit_limit_amount",
          "label": "Credit limit",
          "kind": "number",
          "description": "Synthetic credit limit in native demo amount units."
        },
        {
          "key": "current_balance_amount",
          "label": "Balance",
          "kind": "number",
          "description": "Synthetic current balance in native demo amount units."
        },
        {
          "key": "account_open_date",
          "label": "Opened",
          "kind": "date",
          "description": "Synthetic tradeline opening date."
        },
        {
          "key": "account_closed_indicator",
          "label": "Closed",
          "kind": "code",
          "description": "Y indicates a closed generated tradeline; N indicates otherwise."
        }
      ]
    }
  }
}; if(typeof module!=="undefined"&&module.exports)module.exports=config; else window.SageRecordsConfig=config; })();
