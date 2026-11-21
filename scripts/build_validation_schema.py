"""Maintain the closed public v2 schema from fixed report keys (no live inputs)."""

import json
from pathlib import Path
from synthetic_banking.validation_reporting import build_validation_report, NUMERIC, DATES, FIELDS, CARDINALITIES, RULES, TABLES, THRESHOLDS, POLICY_VERSION, MIN_CONDITIONAL_ROWS, SCREENING_THRESHOLDS, SCREENING_POLICY_VERSION
from synthetic_banking.privacy_reporting import PATTERNS
from synthetic_banking.null_rates import FIELDS as NULL_FIELDS, POLICY_VERSION as NULL_POLICY_VERSION, REASONS as NULL_REASONS, SUMMARY_KEYS

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "docs/reporting"


def obj(properties):
    return dict(type="object", properties=properties, required=list(properties), additionalProperties=False)


def array(item, length):
    return dict(type="array", items=item, minItems=length, maxItems=length)


def enum(values):
    return {"enum": list(values)}


def build_schema():
    template = build_validation_report([])
    number = {"type": ["number", "null"]}
    integer = {"type": "integer", "minimum": 0}
    status = enum(("STRONG", "ACCEPTABLE", "NEEDS_REVIEW", "UNAVAILABLE", "TRIVIAL"))
    assessment = obj(dict(
        key=enum(a["key"] for a in template["assessments"]), label=enum(a["label"] for a in template["assessments"]),
        family=enum(sorted({a["family"] for a in template["assessments"]})), status=status,
        source=number, generated=number, difference=number, score=number, policy=enum((*THRESHOLDS, None)),
        source_n=number, generated_n=number, source_count=number, generated_count=number,
        reason=enum((*NULL_REASONS, "metric_unavailable", "zero_or_missing_source_iqr", "insufficient_conditional_rows",
                     "source_comparison_unavailable", "not_in_saved_fidelity_report"))))
    report = obj(dict(
        status=enum(("AVAILABLE", "PENDING")), policy_version={"const": POLICY_VERSION},
        thresholds=obj({k: obj({name: {"const": value} for name, value in v.items()}) for k, v in THRESHOLDS.items()}),
        min_conditional_rows={"const": MIN_CONDITIONAL_ROWS},
        summary=obj({k: enum(("PENDING", "REVIEW_REQUIRED", "PARTIAL", "WITHIN_TOLERANCE")) if k == "comparison_status" else integer
                     for k in template["summary"]}),
        strengths={"type": "array", "items": assessment["properties"]["key"], "maxItems": 6, "uniqueItems": True},
        weaknesses={"type": "array", "items": assessment["properties"]["key"], "maxItems": 6, "uniqueItems": True},
        assessments=array(assessment, len(template["assessments"])),
        numeric=array(obj(dict(key=enum(r[0] for r in NUMERIC), label=enum(r[3] for r in NUMERIC), source_iqr=number,
            percentiles=array(obj(dict(name=enum(("P25", "P50", "P75", "P95")), source=number, generated=number, difference=number)), 4),
            average_difference_pct_iqr=number, max_difference_pct_iqr=number, status=status)), len(NUMERIC)),
        categorical=array(obj(dict(category=enum(("Y", "N")), source=number, generated=number, absolute_difference_pp=number, status=status)), 2),
        dates=array(obj(dict(key=enum(r[0] for r in DATES), label=enum(r[3] for r in DATES), total_variation_pct=number,
            earliest_shift_days=number, latest_shift_days=number, status=status)), len(DATES)),
        cardinality=array(obj(dict(key=enum(r[0] for r in CARDINALITIES), label=enum(r[2] for r in CARDINALITIES),
            total_variation_pct=number, source_mean=number, generated_mean=number, status=status,
            bins=array(obj(dict(bucket=enum(("0", "1", "2", "3", "4", "5+")), source=number, generated=number, absolute_difference_pp=number)), 6))), len(CARDINALITIES)),
        populations=array(obj(dict(table=enum(TABLES), source=number, generated=number, difference=number)), len(TABLES)),
        accounts_per_person=obj(dict(source=number, generated=number)),
        rule_outcomes=array(obj(dict(implementation=enum(r[0] for r in RULES), target=enum(r[1] for r in RULES),
            proposed=integer, approved=integer, applied=integer, skipped=integer)), len(RULES))))
    # Optional, aggregate-only addition: historical v2 artifacts remain valid.
    report["properties"]["summary"]["required"].remove("trivial_zero_null")
    count = {"type": ["integer", "null"], "minimum": 0}
    rate = {"type": ["number", "null"], "minimum": 0, "maximum": 1}
    null_keys = [f"null_field.{t}.{c}" for t,c in NULL_FIELDS]
    null_row = obj(dict(key=enum(null_keys), table=enum(sorted({t for t,c in NULL_FIELDS})),
        column=enum(sorted({c for t,c in NULL_FIELDS})), label=enum(f"{t}.{c} · null rate" for t,c in NULL_FIELDS),
        family={"const":"nulls"}, policy={"const":"proportion_pp"},
        source=rate, generated=rate, difference=number, score=number,
        source_n=count, generated_n=count, source_count=count, generated_count=count,
        status=status, classification=enum(("TRIVIAL_MATCH","MEANINGFUL_MATCH","DISCREPANCY","UNAVAILABLE")),
        pattern=enum(("ZERO_ZERO","ZERO_NONZERO","NONZERO_ZERO","NONZERO_NONZERO","UNAVAILABLE")),
        reason=enum(NULL_REASONS), strength_eligible={"type":"boolean"}, all_null_match={"type":"boolean"}))
    report["properties"]["null_rate_audit"] = obj(dict(policy_version={"const":NULL_POLICY_VERSION},
        thresholds=obj({k:{"const":v} for k,v in THRESHOLDS["proportion_pp"].items()}),
        zero_presence_requires_review={"const":True}, summary=obj({k:integer for k in SUMMARY_KEYS}),
        rows=array(null_row,len(NULL_FIELDS))))
    report["properties"]["dependency_fidelity"] = obj(dict(
        categorical=array(obj(dict(
            key=enum(("account_type_product", "client_tsys_product")),
            label=enum(("Account type / client product", "Client / TSYS product")),
            source_cramers_v=rate, generated_cramers_v=rate, absolute_association_gap=rate,
            source_n=count, generated_n=count, conditional_tvd_pct={"type": ["number", "null"], "minimum": 0, "maximum": 100},
            unsupported_combination_rate=rate)), 2),
        numeric_segments=array(obj(dict(bucket=enum(("Q1", "Q2", "Q3", "Q4")),
            source_mean=number, generated_mean=number, mean_difference=number,
            source_n=count, generated_n=count)), 4)))
    extra=template['post_pilot']
    extra_assessment=obj(dict(key=enum(a['key'] for a in extra['assessments']),
        label=enum(a['label'] for a in extra['assessments']),family=enum(sorted({a['family'] for a in extra['assessments']})),
        score=number,policy=enum(SCREENING_THRESHOLDS),status=status,source=number,generated=number,difference=number,
        source_n=count,generated_n=count))
    report['properties']['post_pilot']=obj(dict(
        policy_version={'const':SCREENING_POLICY_VERSION},provisional={'const':True},
        thresholds=obj({k:obj({name:{'const':value} for name,value in v.items()}) for k,v in SCREENING_THRESHOLDS.items()}),
        integrity_requirements=obj(dict(snapshot_join_coverage={'const':1.0},allowed_violations={'const':0})),
        min_conditional_rows={'const':MIN_CONDITIONAL_ROWS},assessments=array(extra_assessment,len(extra['assessments'])),
        numeric_details=array(obj(dict(key=enum(r[0] for r in NUMERIC),label=enum(r[3] for r in NUMERIC),
            mean_relative_pct=number,tail_points=array(obj(dict(name=enum(('P01','P05','P99')),source=number,generated=number,difference=number)),3),
            **{side+'_'+metric:number for side in ('source','generated') for metric in ('minimum','maximum','stddev')})),4),
        strengths={'type':'array','items':enum([a['key'] for a in template['assessments']+extra['assessments']]+null_keys),'maxItems':6,'uniqueItems':True},
        weaknesses={'type':'array','items':enum([a['key'] for a in template['assessments']+extra['assessments']]+null_keys),'maxItems':6,'uniqueItems':True},
        zero_reference_alerts={'type':'array','items':enum('mean.'+r[0] for r in NUMERIC),'maxItems':4,'uniqueItems':True}))
    schema = json.loads((FOLDER / "pipeline-report-v1.schema.json").read_text())
    schema["title"] = "Synthetic banking public pipeline report, version 2.0"
    schema["description"] = "Sanitized aggregates and prototype validation screening; no execution IDs or row records."
    schema["properties"]["schema_version"] = {"const": "2.0"}
    schema["properties"]["validation_report"] = report
    schema['properties']['demo_dataset'] = obj(dict(
        dataset_version={'type':'string','pattern':r'^sage-demo-v[1-9][0-9]*(\.[0-9]+)*$'},
        release_mode={'const':'DEMO_ONLY'}, preview_sha256={'type':'string','pattern':'^[0-9a-f]{64}$'}))
    privacy_policy=obj(dict(rare_min_count={'type':'integer','minimum':1},max_synthetic_rare_fraction=rate,
        min_complete_fraction={'type':'number','exclusiveMinimum':0,'maximum':1},
        near_date_days={'type':'integer','minimum':0,'maximum':366},max_similarity_candidates={'type':'integer','minimum':1}))
    schema['properties']['privacy']=obj(dict(status=enum(('PASS','REVIEW_REQUIRED','BLOCKED','UNAVAILABLE')),
        row_level_downloads_enabled={'const':False},formal_anonymization_certified={'const':False},
        policy_version=enum(('basic_v1',None)),policy={'anyOf':[privacy_policy,{'type':'null'}]},
        checks_recorded=count,checks_expected=count,identifier_overlap_rows=count,exact_source_row_matches=count,
        near_matches=obj(dict(variables={'const':['BIRTH_DT','SINCE_DT','GENDER_CD']},evaluated_rows=count,flagged_rows=count,
            flagged_fraction=rate,minimum_combined_distance_days=count,complete_case_coverage=rate)),
        categorical_patterns=array(obj(dict(key=enum(p[0] for p in PATTERNS),label=enum(p[1] for p in PATTERNS),
            status=enum(('PASS','INFO','FAIL','REVIEW_REQUIRED','UNAVAILABLE','ERROR')),evaluated_rows=count,
            synthetic_rare_rows=count,source_rare_match_rows=count,complete_case_coverage=rate)),3)))
    schema["required"].append("validation_report")
    return schema


if __name__ == "__main__":
    (FOLDER / "pipeline-report.schema.json").write_text(json.dumps(build_schema(), indent=2)+"\n", encoding="utf-8")
    template = build_validation_report([])
    config = dict(assessments={a["key"]: {k: a[k] for k in ("label", "family", "policy")} for a in template["assessments"]},
                  thresholds=THRESHOLDS,policy_version=POLICY_VERSION,min_conditional_rows=MIN_CONDITIONAL_ROWS,
                  null_rates=dict(policy_version=NULL_POLICY_VERSION,fields=[list(f) for f in NULL_FIELDS], reasons=list(NULL_REASONS), summary_keys=list(SUMMARY_KEYS),
                    core_fields={"null."+key:[table,column] for key,table,column,label in FIELDS}),
                  post_pilot=dict(policy_version=SCREENING_POLICY_VERSION,thresholds=SCREENING_THRESHOLDS,
                    assessments={a['key']:{k:a[k] for k in ('label','family')} for a in template['post_pilot']['assessments']}))
    code = "/* Generated from validation_reporting.py; run scripts/build_validation_schema.py. */\n"
    code += "(() => { const config = " + json.dumps(config, indent=2) + ";\n"
    code += "if (typeof module !== 'undefined' && module.exports) module.exports = config;\n"
    code += "if (typeof window !== 'undefined') window.ValidationConfig = config; })();\n"
    (ROOT / "docs/validation-config.js").write_text(code, encoding="utf-8")
