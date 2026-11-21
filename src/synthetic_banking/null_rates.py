"""Count-based missingness screening of saved aggregates, never row records."""

from collections import defaultdict
import json
from pathlib import Path

POLICY_VERSION = "null_rates_v1"
# Reviewed public column names/types only. No field values come from this policy.
_schema = json.loads(Path(__file__).with_name("demo_export_policy.json").read_text(encoding="utf-8"))["columns"]
FIELDS = tuple(sorted((table, column) for table, columns in _schema.items() for column in columns))
REASONS = (None, "missing_null_counts", "invalid_null_counts", "duplicate_null_evidence",
           "null_comparison_unavailable", "zero_null_in_both", "zero_presence_change")
SUMMARY_KEYS = ("variables_total", "variables_evaluated", "trivial_zero_null", "eligible_nontrivial",
                "meaningful_matches", "material_discrepancies", "requiring_review", "unavailable",
                "source_zero_generated_nonzero", "source_nonzero_generated_zero", "both_nonzero",
                "all_null_matches", "additional_unpublished_variables")


def count(value):
    # Reject booleans/fractions/non-finite/unsafe JSON integers.
    return value if type(value) in (int, float) and 0 <= value <= 2**53-1 and value == int(value) else None


def classify(row, limits):
    """Counts take precedence over stored/rounded rates. Missing counts never pass.

    Any zero/nonzero transition requires review, even below the pp tolerance.
    This is a qualitative missingness change, not a significance claim.
    """
    keys = ("source_count", "source_sample_size", "generated_count", "generated_sample_size")
    sc, sn, gc, gn = (count(row.get(k)) for k in keys)
    reason = ("duplicate_null_evidence" if row.get("duplicate") else
              "missing_null_counts" if any(row.get(k) is None for k in keys) else
              "invalid_null_counts" if None in (sc, sn, gc, gn) or not sn or not gn or sc > sn or gc > gn else
              "null_comparison_unavailable" if row.get("comparison_status") != "COMPARABLE" else None)
    valid = reason is None
    s = sc/sn if sc is not None and sn and sc <= sn else None
    g = gc/gn if gc is not None and gn and gc <= gn else None
    score = 100*abs(g-s) if valid else None
    pattern = ("UNAVAILABLE" if not valid else "ZERO_ZERO" if sc == gc == 0 else
               "ZERO_NONZERO" if sc == 0 else "NONZERO_ZERO" if gc == 0 else "NONZERO_NONZERO")
    if pattern == "UNAVAILABLE":
        status, category = "UNAVAILABLE", "UNAVAILABLE"
    elif pattern == "ZERO_ZERO":
        status, category, reason = "TRIVIAL", "TRIVIAL_MATCH", "zero_null_in_both"
    elif pattern in ("ZERO_NONZERO", "NONZERO_ZERO"):
        status, category, reason = "NEEDS_REVIEW", "DISCREPANCY", "zero_presence_change"
    elif score > limits["acceptable"] + 1e-9:
        status, category = "NEEDS_REVIEW", "DISCREPANCY"
    else:
        status = "STRONG" if score <= limits["strong"] + 1e-9 else "ACCEPTABLE"
        category = "MEANINGFUL_MATCH"
    return dict(source=s, generated=g, difference=g-s if valid else None, score=score,
                source_count=sc, generated_count=gc, source_n=sn, generated_n=gn,
                status=status, classification=category, pattern=pattern, reason=reason,
                strength_eligible=category == "MEANINGFUL_MATCH" and status == "STRONG",
                all_null_match=valid and sc == sn and gc == gn)


def summarize(rows, additional=0):
    n = lambda **criteria: sum(all(row[k] == value for k, value in criteria.items()) for row in rows)
    trivial, unavailable = n(status="TRIVIAL"), n(status="UNAVAILABLE")
    return dict(variables_total=len(rows), variables_evaluated=len(rows)-unavailable,
                trivial_zero_null=trivial, eligible_nontrivial=len(rows)-unavailable-trivial,
                meaningful_matches=n(classification="MEANINGFUL_MATCH"),
                material_discrepancies=n(classification="DISCREPANCY"), requiring_review=n(status="NEEDS_REVIEW"),
                unavailable=unavailable, source_zero_generated_nonzero=n(pattern="ZERO_NONZERO"),
                source_nonzero_generated_zero=n(pattern="NONZERO_ZERO"), both_nonzero=n(pattern="NONZERO_NONZERO"),
                all_null_matches=n(all_null_match=True), additional_unpublished_variables=additional)


def build_null_rate_audit(metrics, limits):
    grouped = defaultdict(list)
    for row in metrics:
        if row.get("family") == "NULL_RATE" and row.get("metric") == "null_rate":
            grouped[row.get("entity_name"), row.get("column_name")].append(row)
    rows = []
    for table, column in FIELDS:
        evidence = grouped.get((table, column), [])
        row = evidence[0] if len(evidence) == 1 else {"duplicate": len(evidence) > 1}
        rows.append(dict(key=f"null_field.{table}.{column}", table=table, column=column,
                         label=f"{table}.{column} · null rate", family="nulls", policy="proportion_pp",
                         **classify(row, limits)))
    return dict(policy_version=POLICY_VERSION, thresholds=dict(limits), zero_presence_requires_review=True,
                summary=summarize(rows, len(set(grouped)-set(FIELDS))), rows=rows)


def strength_eligible(assessment):
    return assessment["status"] == "STRONG" and (assessment["family"] != "nulls" or
           assessment.get("strength_eligible") is True)
