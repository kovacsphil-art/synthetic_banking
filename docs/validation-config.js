/* Generated from validation_reporting.py; run scripts/build_validation_schema.py. */
(() => { const config = {
  "assessments": {
    "numeric.credit_limit": {
      "label": "Credit limit",
      "family": "numeric",
      "policy": "numeric_iqr_pct"
    },
    "numeric.current_balance": {
      "label": "Current balance",
      "family": "numeric",
      "policy": "numeric_iqr_pct"
    },
    "numeric.available_credit": {
      "label": "Available credit",
      "family": "numeric",
      "policy": "numeric_iqr_pct"
    },
    "numeric.overlimit": {
      "label": "Overlimit amount",
      "family": "numeric",
      "policy": "numeric_iqr_pct"
    },
    "categorical.past_due": {
      "label": "Past-due category proportions",
      "family": "categorical",
      "policy": "proportion_pp"
    },
    "null.credit_limit": {
      "label": "Credit limit \u00b7 null rate",
      "family": "nulls",
      "policy": "proportion_pp"
    },
    "null.current_balance": {
      "label": "Current balance \u00b7 null rate",
      "family": "nulls",
      "policy": "proportion_pp"
    },
    "null.available_credit": {
      "label": "Available credit \u00b7 null rate",
      "family": "nulls",
      "policy": "proportion_pp"
    },
    "null.overlimit": {
      "label": "Overlimit amount \u00b7 null rate",
      "family": "nulls",
      "policy": "proportion_pp"
    },
    "null.past_due": {
      "label": "Past-due indicator \u00b7 null rate",
      "family": "nulls",
      "policy": "proportion_pp"
    },
    "null.birth": {
      "label": "Birth-date distribution \u00b7 null rate",
      "family": "nulls",
      "policy": "proportion_pp"
    },
    "null.customer_since": {
      "label": "Customer-since distribution \u00b7 null rate",
      "family": "nulls",
      "policy": "proportion_pp"
    },
    "null.account_open": {
      "label": "Account-open distribution \u00b7 null rate",
      "family": "nulls",
      "policy": "proportion_pp"
    },
    "date.birth": {
      "label": "Birth-date distribution",
      "family": "dates",
      "policy": "distribution_tvd_pct"
    },
    "date.customer_since": {
      "label": "Customer-since distribution",
      "family": "dates",
      "policy": "distribution_tvd_pct"
    },
    "date.account_open": {
      "label": "Account-open distribution",
      "family": "dates",
      "policy": "distribution_tvd_pct"
    },
    "cardinality.accounts_per_customer": {
      "label": "Accounts per customer",
      "family": "cardinality",
      "policy": "distribution_tvd_pct"
    },
    "cardinality.relationships_outgoing": {
      "label": "Outgoing relationships per person",
      "family": "cardinality",
      "policy": "distribution_tvd_pct"
    },
    "cardinality.relationships_incoming": {
      "label": "Incoming relationships per person",
      "family": "cardinality",
      "policy": "distribution_tvd_pct"
    },
    "cardinality.tradelines_per_customer": {
      "label": "Tradelines per customer",
      "family": "cardinality",
      "policy": "distribution_tvd_pct"
    },
    "correlation.balance_limit": {
      "label": "Credit limit / balance correlation",
      "family": "correlation",
      "policy": "correlation"
    },
    "conditional.0": {
      "label": "Past due \u00b7 utilization 0-30%",
      "family": "conditional",
      "policy": "conditional_pp"
    },
    "conditional.1": {
      "label": "Past due \u00b7 utilization 30-60%",
      "family": "conditional",
      "policy": "conditional_pp"
    },
    "conditional.2": {
      "label": "Past due \u00b7 utilization 60-80%",
      "family": "conditional",
      "policy": "conditional_pp"
    },
    "conditional.3": {
      "label": "Past due \u00b7 utilization 80-100%",
      "family": "conditional",
      "policy": "conditional_pp"
    },
    "conditional.4": {
      "label": "Past due \u00b7 utilization 100%+",
      "family": "conditional",
      "policy": "conditional_pp"
    },
    "integrity.account_coverage": {
      "label": "Accounts with a balance",
      "family": "integrity",
      "policy": null
    },
    "integrity.balance_coverage": {
      "label": "Balances with an account",
      "family": "integrity",
      "policy": null
    },
    "integrity.available_formula": {
      "label": "Available-credit formula violations",
      "family": "integrity",
      "policy": null
    },
    "integrity.overlimit_formula": {
      "label": "Overlimit formula violations",
      "family": "integrity",
      "policy": null
    },
    "integrity.balance_cap": {
      "label": "Balance-cap violations",
      "family": "integrity",
      "policy": null
    },
    "integrity.negative_balance": {
      "label": "Negative balance violations",
      "family": "integrity",
      "policy": null
    },
    "integrity.delinquency_flag": {
      "label": "Delinquency flag/count violations",
      "family": "integrity",
      "policy": null
    },
    "integrity.birth_order": {
      "label": "Birth/customer-since ordering violations",
      "family": "integrity",
      "policy": null
    },
    "integrity.account_date_order": {
      "label": "Account open/close ordering violations",
      "family": "integrity",
      "policy": null
    },
    "integrity.relationship_endpoints": {
      "label": "Customer-relationship invalid endpoints",
      "family": "integrity",
      "policy": null
    },
    "graph.directed_dyads_proportion": {
      "label": "Customer relationships \u00b7 directed dyads",
      "family": "graph",
      "policy": "proportion_pp"
    },
    "graph.reciprocal_dyads_proportion": {
      "label": "Customer relationships \u00b7 reciprocal dyads",
      "family": "graph",
      "policy": "proportion_pp"
    },
    "graph.self_dyads_proportion": {
      "label": "Customer relationships \u00b7 self dyads",
      "family": "graph",
      "policy": "proportion_pp"
    },
    "integrity.other_references": {
      "label": "Other cross-table referential integrity",
      "family": "integrity",
      "policy": null
    }
  },
  "thresholds": {
    "numeric_iqr_pct": {
      "strong": 5.0,
      "acceptable": 15.0
    },
    "proportion_pp": {
      "strong": 1.0,
      "acceptable": 3.0
    },
    "conditional_pp": {
      "strong": 2.0,
      "acceptable": 5.0
    },
    "correlation": {
      "strong": 0.05,
      "acceptable": 0.15
    },
    "distribution_tvd_pct": {
      "strong": 2.0,
      "acceptable": 5.0
    }
  },
  "policy_version": "prototype_v1",
  "min_conditional_rows": 30,
  "null_rates": {
    "policy_version": "null_rates_v1",
    "fields": [
      [
        "CUSTOMER_ACCOUNT_REL",
        "ACCT_ID"
      ],
      [
        "CUSTOMER_ACCOUNT_REL",
        "ACCT_SUBSYS_MNEMONIC_CD"
      ],
      [
        "CUSTOMER_ACCOUNT_REL",
        "PARTY_ID"
      ],
      [
        "CUSTOMER_ACCOUNT_REL",
        "PRIMARY_OWNERSHIP_FLAG"
      ],
      [
        "CUSTOMER_ACCOUNT_REL",
        "PROD_CD"
      ],
      [
        "CUSTOMER_ACCOUNT_REL",
        "RELATN_TYPE_CD"
      ],
      [
        "CUSTOMER_RELATIONSHIP",
        "FROM_PARTY_ID"
      ],
      [
        "CUSTOMER_RELATIONSHIP",
        "FROM_TO_CUST_RELATN_CD"
      ],
      [
        "CUSTOMER_RELATIONSHIP",
        "LAST_UPDT_CHANNEL_CD"
      ],
      [
        "CUSTOMER_RELATIONSHIP",
        "LAST_UPDT_TRANSIT_NUM"
      ],
      [
        "CUSTOMER_RELATIONSHIP",
        "ORIGINATING_APP_CD"
      ],
      [
        "CUSTOMER_RELATIONSHIP",
        "OWNED_BUS_SINCE_DT"
      ],
      [
        "CUSTOMER_RELATIONSHIP",
        "TO_FROM_CUST_RELATN_CD"
      ],
      [
        "CUSTOMER_RELATIONSHIP",
        "TO_PARTY_ID"
      ],
      [
        "CUSTOMER_RELATIONSHIP",
        "ownership_percentage"
      ],
      [
        "PERSON",
        "BANKRUPTCY_DT"
      ],
      [
        "PERSON",
        "BIRTH_DT"
      ],
      [
        "PERSON",
        "CLIENT_STAT_CD"
      ],
      [
        "PERSON",
        "CUST_TYPE_CD"
      ],
      [
        "PERSON",
        "DECEASED_DT"
      ],
      [
        "PERSON",
        "DOMICILE_TRANSIT_NUM"
      ],
      [
        "PERSON",
        "EMP_TYPE_CD"
      ],
      [
        "PERSON",
        "GENDER_CD"
      ],
      [
        "PERSON",
        "KYC_REFRESH_DT"
      ],
      [
        "PERSON",
        "LEFT_DT"
      ],
      [
        "PERSON",
        "MARITAL_STAT_CD"
      ],
      [
        "PERSON",
        "OCCUP_CAT_CD"
      ],
      [
        "PERSON",
        "OCCUP_DESC"
      ],
      [
        "PERSON",
        "PARTY_ID"
      ],
      [
        "PERSON",
        "PARTY_SUBSYS_MNEMONIC_CD"
      ],
      [
        "PERSON",
        "PREF_LANG_CD"
      ],
      [
        "PERSON",
        "SENSITIVITY_CD"
      ],
      [
        "PERSON",
        "SINCE_DT"
      ],
      [
        "PERSON",
        "SRC_IDENTITY_CD"
      ],
      [
        "TKQ_ACCOUNT",
        "ACCOUNT_ID"
      ],
      [
        "TKQ_ACCOUNT",
        "ACCOUNT_TYPE_CD"
      ],
      [
        "TKQ_ACCOUNT",
        "ACCT_STATUS_CODE_MAINTENANCE_DT"
      ],
      [
        "TKQ_ACCOUNT",
        "ACQUISITION_STRATEGY_CD"
      ],
      [
        "TKQ_ACCOUNT",
        "ACTUAL_BILL_OVERLIMIT_LTD_CNT"
      ],
      [
        "TKQ_ACCOUNT",
        "ALTERNATE_DISCLOSURE_GROUP"
      ],
      [
        "TKQ_ACCOUNT",
        "ALT_DISCL_GRP_CD"
      ],
      [
        "TKQ_ACCOUNT",
        "ALT_DISCL_GRP_START_DATE"
      ],
      [
        "TKQ_ACCOUNT",
        "ALT_DISCL_GRP_STOP_DATE"
      ],
      [
        "TKQ_ACCOUNT",
        "ALT_DISC_GRP_DURATION"
      ],
      [
        "TKQ_ACCOUNT",
        "AM02_RES_INDICATOR"
      ],
      [
        "TKQ_ACCOUNT",
        "ANNUAL_FEE_CHARGE_DT"
      ],
      [
        "TKQ_ACCOUNT",
        "AUTO_LIMIT_INCREASE_IND"
      ],
      [
        "TKQ_ACCOUNT",
        "AUTO_PAYMENT_METHOD_CD"
      ],
      [
        "TKQ_ACCOUNT",
        "AUTO_PAYMENT_OPTION_SET"
      ],
      [
        "TKQ_ACCOUNT",
        "AUTO_REAGE_CNT"
      ],
      [
        "TKQ_ACCOUNT",
        "AVERAGE_DELINQUENCY_MONTHLY_AMT"
      ],
      [
        "TKQ_ACCOUNT",
        "BILLED_LTD_CNT"
      ],
      [
        "TKQ_ACCOUNT",
        "BIL_STATEMENT_AT_CYLE_CD"
      ],
      [
        "TKQ_ACCOUNT",
        "BKDT_BAL_PREV_STATEMENT_AMT"
      ],
      [
        "TKQ_ACCOUNT",
        "BRANCH_NUM"
      ],
      [
        "TKQ_ACCOUNT",
        "BUSINESSEFFECTIVEDATE"
      ],
      [
        "TKQ_ACCOUNT",
        "CARD_EXPIRY_DT"
      ],
      [
        "TKQ_ACCOUNT",
        "CASH_APR"
      ],
      [
        "TKQ_ACCOUNT",
        "CHARGE_OFF_DT"
      ],
      [
        "TKQ_ACCOUNT",
        "CLIENT_PRODUCT_CD"
      ],
      [
        "TKQ_ACCOUNT",
        "CLOSE_DT"
      ],
      [
        "TKQ_ACCOUNT",
        "CLOSE_STATUS_DT"
      ],
      [
        "TKQ_ACCOUNT",
        "CMP_METHOD_CD"
      ],
      [
        "TKQ_ACCOUNT",
        "CONSECUTIVE_PAST_DUE_BILL_DAYS_CNT"
      ],
      [
        "TKQ_ACCOUNT",
        "CONSECUTIVE_PAST_DUE_BILL_TIMES_CNT"
      ],
      [
        "TKQ_ACCOUNT",
        "CREDIT_LIMIT_AMT"
      ],
      [
        "TKQ_ACCOUNT",
        "CREDIT_REVOKE_DT"
      ],
      [
        "TKQ_ACCOUNT",
        "CREDIT_REVOKE_STATUS_DT"
      ],
      [
        "TKQ_ACCOUNT",
        "CURRENT_CREDIT_SCORE"
      ],
      [
        "TKQ_ACCOUNT",
        "CURRENT_CREDIT_SCORE_DT"
      ],
      [
        "TKQ_ACCOUNT",
        "CURRENT_OUT_CASH_AMT"
      ],
      [
        "TKQ_ACCOUNT",
        "CYCLED_OUTSTANDING_AMT"
      ],
      [
        "TKQ_ACCOUNT",
        "CYCLES_TO_ACTIVATE_CNT"
      ],
      [
        "TKQ_ACCOUNT",
        "CYCLE_NUM"
      ],
      [
        "TKQ_ACCOUNT",
        "DATE_LAST_PERM_CR_CHG"
      ],
      [
        "TKQ_ACCOUNT",
        "DELINQUENCY_CNT"
      ],
      [
        "TKQ_ACCOUNT",
        "DISCLOSURE_GRP"
      ],
      [
        "TKQ_ACCOUNT",
        "FINANCE_CHARGE_FEE_WAIVE_FLAG"
      ],
      [
        "TKQ_ACCOUNT",
        "FIRST_DLQ_DATE"
      ],
      [
        "TKQ_ACCOUNT",
        "FIRST_USE_DT"
      ],
      [
        "TKQ_ACCOUNT",
        "HIGH_BALANCE_AMT"
      ],
      [
        "TKQ_ACCOUNT",
        "HIGH_BALANCE_DT"
      ],
      [
        "TKQ_ACCOUNT",
        "LAST_CASH_ADVANCE_AMT"
      ],
      [
        "TKQ_ACCOUNT",
        "LAST_CASH_ADVANCE_DT"
      ],
      [
        "TKQ_ACCOUNT",
        "LAST_CREDIT_DT"
      ],
      [
        "TKQ_ACCOUNT",
        "LAST_CYCLE_BILLING_DATE"
      ],
      [
        "TKQ_ACCOUNT",
        "LAST_DISCLOSURE_GROUP_CHANGE_DT"
      ],
      [
        "TKQ_ACCOUNT",
        "LAST_FEATURE_OPTION_SET_MAINTENANCE_DT"
      ],
      [
        "TKQ_ACCOUNT",
        "LAST_FINANCIAL_ACTIVITY_DT"
      ],
      [
        "TKQ_ACCOUNT",
        "LAST_LIMIT_CHANGE_DT"
      ],
      [
        "TKQ_ACCOUNT",
        "LAST_MAINTENACE_DT"
      ],
      [
        "TKQ_ACCOUNT",
        "LAST_NSF_PAYMENT_DT"
      ],
      [
        "TKQ_ACCOUNT",
        "LAST_PAID_AMT"
      ],
      [
        "TKQ_ACCOUNT",
        "LAST_PAST_DUE_DT"
      ],
      [
        "TKQ_ACCOUNT",
        "LAST_PAYMENT_DT"
      ],
      [
        "TKQ_ACCOUNT",
        "LAST_PURCHASE_DT"
      ],
      [
        "TKQ_ACCOUNT",
        "LAST_REAGE_DT"
      ],
      [
        "TKQ_ACCOUNT",
        "LAST_REAGE_TYPE_CD"
      ],
      [
        "TKQ_ACCOUNT",
        "LAST_STATEMENT_BALANCE_AMT"
      ],
      [
        "TKQ_ACCOUNT",
        "LAST_STATEMENT_DT"
      ],
      [
        "TKQ_ACCOUNT",
        "LAST_SYS_GENERATED_TRANS_DT"
      ],
      [
        "TKQ_ACCOUNT",
        "MANUAL_REAGE_CNT"
      ],
      [
        "TKQ_ACCOUNT",
        "MAN_PASTDUE_REAGE_DT"
      ],
      [
        "TKQ_ACCOUNT",
        "MID_CYCLE_RATE2_START_DT"
      ],
      [
        "TKQ_ACCOUNT",
        "MID_CYCLE_RATE3_START_DT"
      ],
      [
        "TKQ_ACCOUNT",
        "MINIMUM_PAYMENT_DUE_AMT"
      ],
      [
        "TKQ_ACCOUNT",
        "OFFICER_NBR"
      ],
      [
        "TKQ_ACCOUNT",
        "OPEN_DT"
      ],
      [
        "TKQ_ACCOUNT",
        "ORIGINAL_CREDIT_LIMIT_AMT"
      ],
      [
        "TKQ_ACCOUNT",
        "OUTSTANDING_CARD_NUM"
      ],
      [
        "TKQ_ACCOUNT",
        "OVR_REAS_DSPLY_CD"
      ],
      [
        "TKQ_ACCOUNT",
        "PASTDUE_AT_CYCLE"
      ],
      [
        "TKQ_ACCOUNT",
        "PAST_DUE_INDICATO_CD"
      ],
      [
        "TKQ_ACCOUNT",
        "PAYMENT_DUE_DATE"
      ],
      [
        "TKQ_ACCOUNT",
        "PCL_PENDING_CL_OFFER_AMT"
      ],
      [
        "TKQ_ACCOUNT",
        "POTENTIAL_PURGE_DT"
      ],
      [
        "TKQ_ACCOUNT",
        "PREVIOUS_STATEMENT_BALANCE_AMT"
      ],
      [
        "TKQ_ACCOUNT",
        "PRODUCT_CHANGE_DT"
      ],
      [
        "TKQ_ACCOUNT",
        "PURCHASES_PYE_AMT"
      ],
      [
        "TKQ_ACCOUNT",
        "PURCHASE_APR"
      ],
      [
        "TKQ_ACCOUNT",
        "REINSTATED_CHARGED_OFF_DT"
      ],
      [
        "TKQ_ACCOUNT",
        "START_TEMP_MIN_PAY_DATE"
      ],
      [
        "TKQ_ACCOUNT",
        "STATEMENT_CNT"
      ],
      [
        "TKQ_ACCOUNT",
        "STATUS_KEY_CNT"
      ],
      [
        "TKQ_ACCOUNT",
        "STOP_TEMP_MIN_PAY_DATE"
      ],
      [
        "TKQ_ACCOUNT",
        "ST_PROV_RES_PRIM_CD"
      ],
      [
        "TKQ_ACCOUNT",
        "ST_PROV_RES_PRIM_PREV_CD"
      ],
      [
        "TKQ_ACCOUNT",
        "SUFFIX_NUM"
      ],
      [
        "TKQ_ACCOUNT",
        "TNDM_AUTH_PROC_TIER_END_DATE"
      ],
      [
        "TKQ_ACCOUNT",
        "TNDM_AUTH_PROC_TIER_START_DATE"
      ],
      [
        "TKQ_ACCOUNT",
        "TRANSFER_FROM_ACCOUNT_INDICATOR_FLAG"
      ],
      [
        "TKQ_ACCOUNT",
        "TSYS_PRODUCT_CD"
      ],
      [
        "TKQ_ACCOUNT",
        "YTD_CASH_ADV_FEE_AS"
      ],
      [
        "TKQ_ACCOUNT",
        "_UTILIZATION_RATE"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "ACCOUNT_ID"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "AMT_PDUE_121_150"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "AMT_PDUE_151_180"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "AMT_PDUE_181_210"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "AMT_PDUE_1_30"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "AMT_PDUE_211_240"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "AMT_PDUE_241_270"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "AMT_PDUE_271_UP"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "AMT_PDUE_31_60"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "AMT_PDUE_61_90"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "AMT_PDUE_91_120"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "AVAILABLE_TO_BUY_AMT"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "AVERAGE_DAILY_BAL_AMT"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "BUSINESSEFFECTIVEDATE"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "CASH_ADVANCE_CTD_AMT"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "CASH_AVAILABLE_AMT"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "CASH_LIMIT_AMT"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "CHARGED_OFF_AMT"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "CLOSE_STATUS_DT"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "CURRENT_BALANCE_AMT"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "FINANCE_CHARGE_BILLED_AMT"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "FINANCIAL_CHARGE_PAID_YTD_AMT"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "FINANCIAL_CHARGE_YTD_AMT"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "LIFETIME_PURCHASE_CNT"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "NUM_PDUE_121_150"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "NUM_PDUE_151_180"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "NUM_PDUE_181_210"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "NUM_PDUE_1_30"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "NUM_PDUE_211_240"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "NUM_PDUE_241_270"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "NUM_PDUE_271_UP"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "NUM_PDUE_31_60"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "NUM_PDUE_61_90"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "NUM_PDUE_91_120"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "OUTSTANDING_AUTHORIZATION_AMT"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "OUTSTANDING_AUTH_CNT"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "OVERLIMIT_AMT"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "PAYMENTS_CTD_CNT"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "PAYMENTS_YTD_CNT"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "PAYMENT_CTD_AMT"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "PAYMENT_YTD_AMT"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "PRINCIPAL_BAL_CHARGEOFF_AMT"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "PURCHASED_AMT"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "PURCHASE_CTD_CNT"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "PURCHASE_YTD_AMT"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "PURCHASE_YTD_CNT"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "SERVICE_CHRG_CTD_AMT"
      ],
      [
        "TKQ_ACCOUNT_BALANCE",
        "UPAID_FINANCE_CHRG_CTD_AMT"
      ],
      [
        "TRADELINES",
        "REQ-CIF-KEY"
      ],
      [
        "TRADELINES",
        "REQ-CIF-TIE-BREAKER"
      ],
      [
        "TRADELINES",
        "account_closed_date"
      ],
      [
        "TRADELINES",
        "account_closed_indicator"
      ],
      [
        "TRADELINES",
        "account_designator_code"
      ],
      [
        "TRADELINES",
        "account_number"
      ],
      [
        "TRADELINES",
        "account_open_date"
      ],
      [
        "TRADELINES",
        "account_paid_out_date"
      ],
      [
        "TRADELINES",
        "account_type_code"
      ],
      [
        "TRADELINES",
        "amount_past_due"
      ],
      [
        "TRADELINES",
        "collateral_text"
      ],
      [
        "TRADELINES",
        "credit_limit_amount"
      ],
      [
        "TRADELINES",
        "currency_code"
      ],
      [
        "TRADELINES",
        "current_balance_amount"
      ],
      [
        "TRADELINES",
        "current_manner_of_payment_code"
      ],
      [
        "TRADELINES",
        "high_credit_amount"
      ],
      [
        "TRADELINES",
        "historical_counters_verification_indicator"
      ],
      [
        "TRADELINES",
        "industry_code"
      ],
      [
        "TRADELINES",
        "ingest_timestamp"
      ],
      [
        "TRADELINES",
        "last_activity_date"
      ],
      [
        "TRADELINES",
        "months_reviewed_count"
      ],
      [
        "TRADELINES",
        "narrative_code_1"
      ],
      [
        "TRADELINES",
        "narrative_code_2"
      ],
      [
        "TRADELINES",
        "payment_amount"
      ],
      [
        "TRADELINES",
        "payment_frequency_code"
      ],
      [
        "TRADELINES",
        "payment_pattern"
      ],
      [
        "TRADELINES",
        "payment_pattern_start_date"
      ],
      [
        "TRADELINES",
        "segment_type"
      ],
      [
        "TRADELINES",
        "snapshot_date"
      ],
      [
        "TRADELINES",
        "source_extract_timestamp"
      ],
      [
        "TRADELINES",
        "subscriber_code"
      ],
      [
        "TRADELINES",
        "subscriber_name"
      ],
      [
        "TRADELINES",
        "terms_duration_months"
      ],
      [
        "TRADELINES",
        "times_30_days_late_count"
      ],
      [
        "TRADELINES",
        "times_60_days_late_count"
      ],
      [
        "TRADELINES",
        "times_90_days_late_count"
      ],
      [
        "TRADELINES",
        "trade_last_verified_date"
      ],
      [
        "TRADELINES",
        "trade_verification_indicator"
      ]
    ],
    "reasons": [
      null,
      "missing_null_counts",
      "invalid_null_counts",
      "duplicate_null_evidence",
      "null_comparison_unavailable",
      "zero_null_in_both",
      "zero_presence_change"
    ],
    "summary_keys": [
      "variables_total",
      "variables_evaluated",
      "trivial_zero_null",
      "eligible_nontrivial",
      "meaningful_matches",
      "material_discrepancies",
      "requiring_review",
      "unavailable",
      "source_zero_generated_nonzero",
      "source_nonzero_generated_zero",
      "both_nonzero",
      "all_null_matches",
      "additional_unpublished_variables"
    ],
    "core_fields": {
      "null.credit_limit": [
        "TKQ_ACCOUNT",
        "CREDIT_LIMIT_AMT"
      ],
      "null.current_balance": [
        "TKQ_ACCOUNT_BALANCE",
        "CURRENT_BALANCE_AMT"
      ],
      "null.available_credit": [
        "TKQ_ACCOUNT_BALANCE",
        "AVAILABLE_TO_BUY_AMT"
      ],
      "null.overlimit": [
        "TKQ_ACCOUNT_BALANCE",
        "OVERLIMIT_AMT"
      ],
      "null.past_due": [
        "TKQ_ACCOUNT",
        "PAST_DUE_INDICATO_CD"
      ],
      "null.birth": [
        "PERSON",
        "BIRTH_DT"
      ],
      "null.customer_since": [
        "PERSON",
        "SINCE_DT"
      ],
      "null.account_open": [
        "TKQ_ACCOUNT",
        "OPEN_DT"
      ]
    }
  },
  "post_pilot": {
    "policy_version": "post_pilot_v1",
    "thresholds": {
      "mean_relative_pct": {
        "strong": 1.0,
        "acceptable": 3.0
      },
      "zero_mean_absolute": {
        "strong": 0.0,
        "acceptable": 0.0
      },
      "tail_iqr_pct": {
        "strong": 5.0,
        "acceptable": 15.0
      },
      "conditional_tvd_pct": {
        "strong": 2.0,
        "acceptable": 5.0
      },
      "date_bound_days": {
        "strong": 1.0,
        "acceptable": 7.0
      }
    },
    "assessments": {
      "mean.credit_limit": {
        "label": "Credit limit mean",
        "family": "mean"
      },
      "tail.credit_limit": {
        "label": "Credit limit tail percentiles",
        "family": "tail"
      },
      "mean.current_balance": {
        "label": "Current balance mean",
        "family": "mean"
      },
      "tail.current_balance": {
        "label": "Current balance tail percentiles",
        "family": "tail"
      },
      "mean.available_credit": {
        "label": "Available credit mean",
        "family": "mean"
      },
      "tail.available_credit": {
        "label": "Available credit tail percentiles",
        "family": "tail"
      },
      "mean.overlimit": {
        "label": "Overlimit amount mean",
        "family": "mean"
      },
      "tail.overlimit": {
        "label": "Overlimit amount tail percentiles",
        "family": "tail"
      },
      "date_bounds.birth": {
        "label": "Birth-date distribution bounds",
        "family": "date_bounds"
      },
      "date_bounds.customer_since": {
        "label": "Customer-since distribution bounds",
        "family": "date_bounds"
      },
      "date_bounds.account_open": {
        "label": "Account-open distribution bounds",
        "family": "date_bounds"
      },
      "categorical_conditional.account_type_product": {
        "label": "Account type / client product",
        "family": "categorical_conditional"
      },
      "categorical_conditional.client_tsys_product": {
        "label": "Client / TSYS product",
        "family": "categorical_conditional"
      }
    }
  }
};
if (typeof module !== 'undefined' && module.exports) module.exports = config;
if (typeof window !== 'undefined') window.ValidationConfig = config; })();
