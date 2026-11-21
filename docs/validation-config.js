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
