"""Public, deterministic screening of saved fidelity aggregates; no row reads."""

import json
import math

# Prototype display tolerances, not calibrated acceptance/release standards.
POLICY_VERSION = "prototype_v1"
THRESHOLDS = {
    "numeric_iqr_pct": {"strong": 5.0, "acceptable": 15.0},
    "proportion_pp": {"strong": 1.0, "acceptable": 3.0},
    "conditional_pp": {"strong": 2.0, "acceptable": 5.0},
    "correlation": {"strong": 0.05, "acceptable": 0.15},
    "distribution_tvd_pct": {"strong": 2.0, "acceptable": 5.0},
}
MIN_CONDITIONAL_ROWS = 30
NUMERIC = (
    ("credit_limit", "TKQ_ACCOUNT", "CREDIT_LIMIT_AMT", "Credit limit"),
    ("current_balance", "TKQ_ACCOUNT_BALANCE", "CURRENT_BALANCE_AMT", "Current balance"),
    ("available_credit", "TKQ_ACCOUNT_BALANCE", "AVAILABLE_TO_BUY_AMT", "Available credit"),
    ("overlimit", "TKQ_ACCOUNT_BALANCE", "OVERLIMIT_AMT", "Overlimit amount"),
)
DATES = (("birth", "PERSON", "BIRTH_DT", "Birth-date distribution"),
         ("customer_since", "PERSON", "SINCE_DT", "Customer-since distribution"),
         ("account_open", "TKQ_ACCOUNT", "OPEN_DT", "Account-open distribution"))
FIELDS = (*NUMERIC, ("past_due", "TKQ_ACCOUNT", "PAST_DUE_INDICATO_CD", "Past-due indicator"), *DATES)
CARDINALITIES = (("accounts_per_customer", "ACCOUNTS_PER_PARTY", "Accounts per customer"),
                 ("relationships_outgoing", "CUSTOMER_RELATIONSHIP_OUTGOING", "Outgoing relationships per person"),
                 ("relationships_incoming", "CUSTOMER_RELATIONSHIP_INCOMING", "Incoming relationships per person"),
                 ("tradelines_per_customer", "TRADELINES_PER_CIF", "Tradelines per customer"))
BUCKETS = ("0-30%", "30-60%", "60-80%", "80-100%", "100%+")
TABLES = ("PERSON", "CUSTOMER_ACCOUNT_REL", "TKQ_ACCOUNT", "TKQ_ACCOUNT_BALANCE", "TRADELINES", "CUSTOMER_RELATIONSHIP")
CHECKS = (
    ("account_coverage", "JOIN_COVERAGE", "TKQ_ACCOUNT", "snapshot_join_coverage", "Accounts with a balance"),
    ("balance_coverage", "JOIN_COVERAGE", "TKQ_ACCOUNT_BALANCE", "snapshot_join_coverage", "Balances with an account"),
    ("available_formula", "BUSINESS_RULE", "TKQ_ACCOUNT_BALANCE", "available_to_buy_formula", "Available-credit formula violations"),
    ("overlimit_formula", "BUSINESS_RULE", "TKQ_ACCOUNT_BALANCE", "overlimit_formula", "Overlimit formula violations"),
    ("balance_cap", "BUSINESS_RULE", "TKQ_ACCOUNT_BALANCE", "balance_cap", "Balance-cap violations"),
    ("negative_balance", "BUSINESS_RULE", "TKQ_ACCOUNT_BALANCE", "negative_current_balance", "Negative balance violations"),
    ("delinquency_flag", "BUSINESS_RULE", "TKQ_ACCOUNT", "delinquency_flag_count", "Delinquency flag/count violations"),
    ("birth_order", "TEMPORAL_RULE", "PERSON", "BIRTH_DT<=SINCE_DT", "Birth/customer-since ordering violations"),
    ("account_date_order", "TEMPORAL_RULE", "TKQ_ACCOUNT", "OPEN_DT<=CLOSE_DT", "Account open/close ordering violations"),
    ("relationship_endpoints", "CUSTOMER_RELATIONSHIP", "CUSTOMER_RELATIONSHIP", "invalid_endpoint_rate", "Customer-relationship invalid endpoints"),
)
GRAPH = ("directed_dyads_proportion", "reciprocal_dyads_proportion", "self_dyads_proportion")
RULES = (("available_to_buy", "AVAILABLE_TO_BUY_AMT"), ("overlimit_amount", "OVERLIMIT_AMT"),
         ("delinquency_by_utilization", "PAST_DUE_INDICATO_CD"))


def number(value):
    return value if type(value) in (int, float) and math.isfinite(value) else None


def grade(score, policy):
    if score is None:
        return "UNAVAILABLE"
    limits = THRESHOLDS[policy]
    return "STRONG" if score <= limits["strong"]+1e-9 else "ACCEPTABLE" if score <= limits["acceptable"]+1e-9 else "NEEDS_REVIEW"


def build_validation_report(metrics, rule_outcomes=()):
    """Project fixed public keys; discard internal IDs, values and free-form text."""
    def dims(row):
        try:
            value = json.loads(row.get("dimensions_json") or "{}")
            return value if isinstance(value, dict) else {}
        except (ValueError, TypeError):
            return {}

    def find(family, entity, column, metric, **dimensions):
        rows = [r for r in metrics if (r.get("family"), r.get("entity_name"), r.get("column_name"), r.get("metric")) ==
                (family, entity, column, metric) and all(dims(r).get(k) == v for k, v in dimensions.items())]
        if len(rows) > 1:
            raise ValueError("Duplicate selected validation evidence.")
        return rows[0] if rows else {}

    def values(row):
        s, g = number(row.get("source_value")), number(row.get("generated_value"))
        return s, g, row.get("comparison_status") == "COMPARABLE" and s is not None and g is not None

    assessments, variable_checks = [], {}

    def assess(key, label, family, row, score, policy, *, reason=None, variable=None, status=None):
        s, g, comparable = values(row)
        delta = number(g - s) if comparable else None
        a = dict(key=key, label=label, family=family, status=status or grade(score, policy),
                 source=s, generated=g, difference=delta, score=number(score), policy=policy,
                 source_n=number(row.get("source_sample_size")), generated_n=number(row.get("generated_sample_size")),
                 source_count=number(row.get("source_count")), generated_count=number(row.get("generated_count")),
                 reason=reason or ("metric_unavailable" if score is None else None))
        assessments.append(a)
        if variable:
            variable_checks.setdefault(variable, []).append(a)
        return a

    numeric = []
    for key, table, column, label in NUMERIC:
        rows = [find("NUMERIC", table, column, p) for p in ("p25", "p50", "p75", "p95")]
        points = []
        for name, row in zip(("P25", "P50", "P75", "P95"), rows):
            s, g, valid = values(row)
            points.append(dict(name=name, source=s, generated=g, difference=number(g-s) if valid else None))
        lo, hi = points[0]["source"], points[2]["source"]
        iqr = number(hi-lo) if lo is not None and hi is not None else None
        available = all(p["difference"] is not None for p in points) and iqr is not None and iqr > 0
        scores = [number(100*abs(p["difference"])/iqr) for p in points] if available else []
        available = available and all(s is not None for s in scores)
        average, worst = (sum(scores)/4, max(scores)) if available else (None, None)
        a = assess("numeric."+key, label, "numeric", rows[1], worst, "numeric_iqr_pct", variable=key,
                   reason="zero_or_missing_source_iqr" if iqr is None or iqr <= 0 else None)
        numeric.append(dict(key=key, label=label, source_iqr=iqr, percentiles=points,
                            average_difference_pct_iqr=average, max_difference_pct_iqr=worst, status=a["status"]))

    categorical, cat_scores = [], []
    for category in ("Y", "N"):
        row = find("CATEGORICAL", "TKQ_ACCOUNT", "PAST_DUE_INDICATO_CD", "proportion", category_value=category)
        s, g, valid = values(row)
        valid = valid and 0 <= s <= 1 and 0 <= g <= 1
        score = abs(g-s)*100 if valid else None
        cat_scores.append(score)
        categorical.append(dict(category=category, source=s, generated=g, absolute_difference_pp=score,
                                status=grade(score, "proportion_pp")))
    assess("categorical.past_due", "Past-due category proportions", "categorical", {},
           max(cat_scores) if all(s is not None for s in cat_scores) else None, "proportion_pp", variable="past_due")

    for key, table, column, label in FIELDS:
        row = find("NULL_RATE", table, column, "null_rate")
        s, g, valid = values(row)
        score = abs(g-s)*100 if valid and 0 <= s <= 1 and 0 <= g <= 1 else None
        assess("null."+key, label+" · null rate", "nulls", row, score, "proportion_pp", variable=key)

    def distribution(family, entity, column, dimension):
        rows = [r for r in metrics if (r.get("family"), r.get("entity_name"), r.get("column_name"), r.get("metric")) ==
                (family, entity, column, "proportion")]
        bins = [dims(r).get(dimension) for r in rows]
        if not rows or len(set(bins)) != len(bins) or any(b is None for b in bins):
            return rows, None
        if not all(values(r)[2] and 0 <= r["source_value"] <= 1 and 0 <= r["generated_value"] <= 1 for r in rows):
            return rows, None
        if any(abs(sum(r[side+"_value"] for r in rows)-1) > 1e-6 for side in ("source", "generated")):
            return rows, None
        return rows, 50*sum(abs(r["generated_value"]-r["source_value"]) for r in rows)

    dates = []
    for key, table, column, label in DATES:
        rows, score = distribution("DATE_DISTRIBUTION", table, column, "month_bucket")
        assess("date."+key, label, "dates", {}, score, "distribution_tvd_pct", variable=key)
        shifts = []
        for metric in ("earliest_date", "latest_date"):
            s, g, valid = values(find("DATE_RANGE", table, column, metric))
            shifts.append(g-s if valid else None)
        dates.append(dict(key=key, label=label, total_variation_pct=score,
                          earliest_shift_days=shifts[0], latest_shift_days=shifts[1], status=grade(score, "distribution_tvd_pct")))

    cardinality = []
    for key, entity, label in CARDINALITIES:
        rows, score = distribution("CARDINALITY", entity, None, "cardinality")
        assess("cardinality."+key, label, "cardinality", {}, score, "distribution_tvd_pct")
        bins = []
        for bucket in ("0", "1", "2", "3", "4", "5+"):
            selected = [r for r in rows if type(dims(r).get("cardinality")) in (int, float)
                        and (dims(r)["cardinality"] >= 5 if bucket == "5+" else dims(r)["cardinality"] == int(bucket))]
            s = sum(r["source_value"] for r in selected) if score is not None else None
            g = sum(r["generated_value"] for r in selected) if score is not None else None
            bins.append(dict(bucket=bucket, source=s, generated=g, absolute_difference_pp=abs(g-s)*100 if s is not None else None))
        mean = find("CARDINALITY", entity, None, "mean_cardinality")
        s, g, valid = values(mean)
        cardinality.append(dict(key=key, label=label, total_variation_pct=score, bins=bins,
                                source_mean=s, generated_mean=g, status=grade(score, "distribution_tvd_pct")))

    correlation = find("CORRELATION", "ACCOUNT", "CREDIT_LIMIT_AMT", "PEARSON_CORRELATION", variable_2="CURRENT_BALANCE_AMT")
    s, g, valid = values(correlation)
    assess("correlation.balance_limit", "Credit limit / balance correlation", "correlation", correlation,
           abs(g-s) if valid and -1 <= s <= 1 and -1 <= g <= 1 else None, "correlation")
    for index, bucket in enumerate(BUCKETS):
        row = find("CONDITIONAL", "ACCOUNT", "PAST_DUE_INDICATO_CD", "outcome_rate",
                   parent_column="UTILIZATION_RATE", condition_bucket=bucket)
        s, g, valid = values(row)
        enough = all((number(row.get(side+"_sample_size")) or 0) >= MIN_CONDITIONAL_ROWS for side in ("source", "generated"))
        score = abs(g-s)*100 if valid and enough and 0 <= s <= 1 and 0 <= g <= 1 else None
        assess("conditional."+str(index), "Past due · utilization "+bucket, "conditional", row, score, "conditional_pp",
               reason="insufficient_conditional_rows" if valid and not enough else None)

    for key, family, table, metric, label in CHECKS:
        row = find(family, table, None, metric)
        s, g, valid = values(row)
        enough = (number(row.get("generated_sample_size")) or 0) > 0
        valid_gen = g is not None and 0 <= g <= 1 and enough
        score = (100*(1-g) if family == "JOIN_COVERAGE" else 100*g) if valid_gen else None
        assess("integrity."+key, label, "integrity", row, score, None,
               status="UNAVAILABLE" if score is None else "STRONG" if score == 0 else "NEEDS_REVIEW",
               reason="source_comparison_unavailable" if valid_gen and not valid else None)
    for metric in GRAPH:
        row = find("CUSTOMER_RELATIONSHIP", "CUSTOMER_RELATIONSHIP", None, metric)
        s, g, valid = values(row)
        assess("graph."+metric, "Customer relationships · "+metric.replace("_dyads_proportion", " dyads"),
               "graph", row, abs(g-s)*100 if valid else None, "proportion_pp")
    assess("integrity.other_references", "Other cross-table referential integrity", "integrity", {}, None, None,
           reason="not_in_saved_fidelity_report", status="UNAVAILABLE")

    populations = []
    for table in TABLES:
        s, g, valid = values(find("ROW_COUNT", table, None, "row_count"))
        populations.append(dict(table=table, source=s, generated=g, difference=number(g-s) if valid else None))
    counts = {r["table"]: r for r in populations}
    ratios = []
    for side in ("source", "generated"):
        n, d = counts["TKQ_ACCOUNT"][side], counts["PERSON"][side]
        ratios.append(n/d if n is not None and d is not None and d > 0 else None)

    outcomes = []
    for implementation, target in RULES:
        rows = [r for r in rule_outcomes if r.get("implementation_name") == implementation and r.get("proposal_id") is not None]
        outcomes.append(dict(implementation=implementation, target=target, proposed=len(rows),
                             approved=sum(r.get("approved") is True for r in rows),
                             applied=sum(r.get("applied") is True for r in rows),
                             skipped=sum(r.get("outcome") == "SKIPPED" for r in rows)))

    status_counts = {name: sum(a["status"] == name for a in assessments) for name in ("STRONG", "ACCEPTABLE", "NEEDS_REVIEW", "UNAVAILABLE")}
    variable_status = []
    for checks in variable_checks.values():
        states = {c["status"] for c in checks}
        variable_status.append("NEEDS_REVIEW" if "NEEDS_REVIEW" in states else "UNAVAILABLE" if "UNAVAILABLE" in states else "ACCEPTABLE")
    evaluated = sum(a["status"] != "UNAVAILABLE" for a in assessments)
    overall = "PENDING" if evaluated == 0 else "REVIEW_REQUIRED" if status_counts["NEEDS_REVIEW"] else "PARTIAL" if status_counts["UNAVAILABLE"] else "WITHIN_TOLERANCE"

    def relative(a):
        tolerance = THRESHOLDS[a["policy"]]["acceptable"] if a["policy"] else 1
        return a["score"]/tolerance

    def select(rows, worst=False):
        # Rank normalized departures, then fixed public keys; limit two per family.
        rows = sorted(rows, key=lambda a: ((-1 if worst else 1)*relative(a), a["key"]))
        selected, families = [], {}
        for cap in ((2,) if worst else (1, 2)):
            for row in rows:
                if row["key"] in selected or families.get(row["family"], 0) >= cap:
                    continue
                selected.append(row["key"])
                families[row["family"]] = families.get(row["family"], 0)+1
                if len(selected) == 6:
                    return selected
        return selected

    return dict(status="AVAILABLE" if evaluated else "PENDING", policy_version=POLICY_VERSION,
                thresholds={k: dict(v) for k, v in THRESHOLDS.items()}, min_conditional_rows=MIN_CONDITIONAL_ROWS,
                summary=dict(comparison_status=overall, variables_total=len(variable_checks),
                             variables_evaluated=sum(any(a["status"] != "UNAVAILABLE" for a in c) for c in variable_checks.values()),
                             variables_within_tolerance=variable_status.count("ACCEPTABLE"),
                             variables_requiring_review=variable_status.count("NEEDS_REVIEW"),
                             variables_incomplete=variable_status.count("UNAVAILABLE"), checks_evaluated=evaluated,
                             strong=status_counts["STRONG"], acceptable=status_counts["ACCEPTABLE"],
                             needs_review=status_counts["NEEDS_REVIEW"], unavailable=status_counts["UNAVAILABLE"]),
                strengths=select([a for a in assessments if a["status"] == "STRONG" and a["family"] != "integrity"]),
                weaknesses=select([a for a in assessments if a["status"] == "NEEDS_REVIEW"], worst=True),
                assessments=assessments, numeric=numeric, categorical=categorical, dates=dates,
                cardinality=cardinality, populations=populations,
                accounts_per_person=dict(source=ratios[0], generated=ratios[1]), rule_outcomes=outcomes)
