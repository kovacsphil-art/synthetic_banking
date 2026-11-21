/* Static, aggregate-only validation view. All dynamic text uses textContent. */
(() => {
  "use strict";
  const CONFIG = typeof module!=="undefined" && module.exports ? require("./validation-config.js") : window.ValidationConfig;
  const VIZ = typeof module!=="undefined" && module.exports ? require("./executive-viz.js") : window.SageViz;
  const LABELS = {
    STRONG: "Strong match", ACCEPTABLE: "Acceptable", NEEDS_REVIEW: "Needs review", UNAVAILABLE: "Not comparable", TRIVIAL: "Trivial zero-null match",
    REVIEW_REQUIRED: "Differences need review", PARTIAL: "Some evidence pending", WITHIN_TOLERANCE: "Within configured tolerances", PENDING: "Validation results pending",
  };
  const NUMERIC = {credit_limit: "Credit limit", current_balance: "Current balance", available_credit: "Available credit", overlimit: "Overlimit amount"};
  const TABLES = {PERSON: "Customers (PERSON)", TKQ_ACCOUNT: "Accounts", TKQ_ACCOUNT_BALANCE: "Balances", TRADELINES: "Tradelines", CUSTOMER_ACCOUNT_REL: "Customer–account links", CUSTOMER_RELATIONSHIP: "Customer relationships"};
  const UNITS = {numeric_iqr_pct: "% of SOURCE IQR (worst percentile)", proportion_pp: "pp", conditional_pp: "pp", correlation: "correlation units", distribution_tvd_pct: "% total variation", integrity: "% generated rows"};
  Object.assign(UNITS,{mean_relative_pct:"% of SOURCE mean",zero_mean_absolute:"native amount units",tail_iqr_pct:"% of SOURCE IQR (tail)",conditional_tvd_pct:"% conditional total variation",date_bound_days:"days"});
  const REASONS = {metric_unavailable: "Paired evidence missing or undefined.", zero_or_missing_source_iqr: "SOURCE IQR is zero or missing; normalized percentile difference is undefined.", insufficient_conditional_rows: "Fewer than the configured minimum rows in at least one population.", source_comparison_unavailable: "Generated check measured; SOURCE comparison unavailable.", not_in_saved_fidelity_report: "This check is not present in the saved fidelity report."};
  const nf = new Intl.NumberFormat("en", {maximumFractionDigits: 2});
  const fmt = value => typeof value === "number" && Number.isFinite(value) ? nf.format(value) : "Unavailable";
  const measure = (value,unit) => typeof value === "number" && Number.isFinite(value) ? fmt(value)+(unit.startsWith("%")?"":" ")+unit : "Unavailable";
  const pct = value => typeof value === "number" && Number.isFinite(value) ? nf.format(value*100)+"%" : "Unavailable";
  const state = value => LABELS[value] || "Unavailable";
  const signed = value => typeof value === "number" && Number.isFinite(value) ? (value > 0 ? "+" : "")+fmt(value) : "Unavailable";
  function el(doc, tag, text, cls) { const node=doc.createElement(tag); if (text !== undefined) node.textContent=text; if (cls) node.className=cls; return node; }
  function badge(doc, value, integrity=false) { return el(doc, "span", integrity&&value==="STRONG"?"Passed":state(value), "match-badge match-"+(Object.hasOwn(LABELS,value) ? value.toLowerCase() : "unavailable")); }
  function section(doc, id, title, note) { const node=el(doc,"section",undefined,"report-section"); node.id=id; node.append(el(doc,"h2",title)); if(note) node.append(el(doc,"p",note,"report-description")); return node; }
  function details(doc, title, ...content) { const node=el(doc,"details",undefined,"report-details"); node.append(el(doc,"summary",title),...content); return node; }
  function table(doc, title, headers, rows) {
    const wrap=el(doc,"div",undefined,"table-scroll"); wrap.tabIndex=0; wrap.setAttribute("role","region"); wrap.setAttribute("aria-label",title);
    const node=el(doc,"table",undefined,"report-table"); node.append(el(doc,"caption",title));
    const head=el(doc,"thead"), tr=el(doc,"tr"); headers.forEach(h=>{const th=el(doc,"th",h);th.setAttribute("scope","col");tr.append(th);}); head.append(tr);
    const body=el(doc,"tbody"); rows.forEach(row=>{const tr=el(doc,"tr");row.forEach((v,i)=>{const td=el(doc,i===0?"th":"td"); if(i===0)td.setAttribute("scope","row"); if(typeof v === "object" && v !== null)td.append(v);else td.textContent=v;tr.append(td);});body.append(tr);});node.append(head,body);wrap.append(node);return wrap;
  }

  function classifyNull(a,limits=CONFIG.thresholds.proportion_pp) {
    const count=x=>Number.isSafeInteger(x)&&x>=0?x:null;
    const [sc,sn,gc,gn]=[a.source_count,a.source_n,a.generated_count,a.generated_n].map(count);
    const missing=[a.source_count,a.source_n,a.generated_count,a.generated_n].some(x=>x==null);
    let reason=a.reason==='duplicate_null_evidence'?'duplicate_null_evidence':a.reason==='invalid_null_counts'?'invalid_null_counts':missing?'missing_null_counts':
      [sc,sn,gc,gn].some(x=>x===null)||!sn||!gn||sc>sn||gc>gn?'invalid_null_counts':
      a.reason==='null_comparison_unavailable'?'null_comparison_unavailable':null;
    const valid=reason===null,source=sc!==null&&sn&&sc<=sn?sc/sn:null,generated=gc!==null&&gn&&gc<=gn?gc/gn:null;
    const score=valid?Math.abs(generated-source)*100:null;
    const pattern=!valid?'UNAVAILABLE':sc===0&&gc===0?'ZERO_ZERO':sc===0?'ZERO_NONZERO':gc===0?'NONZERO_ZERO':'NONZERO_NONZERO';
    let status,classification;
    if(!valid){status='UNAVAILABLE';classification='UNAVAILABLE';}
    else if(pattern==='ZERO_ZERO'){status='TRIVIAL';classification='TRIVIAL_MATCH';reason='zero_null_in_both';}
    else if(pattern!=='NONZERO_NONZERO'){status='NEEDS_REVIEW';classification='DISCREPANCY';reason='zero_presence_change';}
    else if(score>limits.acceptable+1e-9){status='NEEDS_REVIEW';classification='DISCREPANCY';}
    else{status=score<=limits.strong+1e-9?'STRONG':'ACCEPTABLE';classification='MEANINGFUL_MATCH';}
    return {source,generated,difference:valid?generated-source:null,score,source_count:sc,generated_count:gc,source_n:sn,generated_n:gn,
      status,classification,pattern,reason,strength_eligible:classification==='MEANINGFUL_MATCH'&&status==='STRONG',all_null_match:valid&&sc===sn&&gc===gn};
  }

  function nullSummary(rows,additional=0){
    const n=(key,value)=>rows.filter(r=>r[key]===value).length,trivial=n('status','TRIVIAL'),missing=n('status','UNAVAILABLE');
    return {variables_total:rows.length,variables_evaluated:rows.length-missing,trivial_zero_null:trivial,eligible_nontrivial:rows.length-missing-trivial,
      meaningful_matches:n('classification','MEANINGFUL_MATCH'),material_discrepancies:n('classification','DISCREPANCY'),requiring_review:n('status','NEEDS_REVIEW'),unavailable:missing,
      source_zero_generated_nonzero:n('pattern','ZERO_NONZERO'),source_nonzero_generated_zero:n('pattern','NONZERO_ZERO'),both_nonzero:n('pattern','NONZERO_NONZERO'),
      all_null_matches:n('all_null_match',true),additional_unpublished_variables:additional};
  }

  function normalizeNullAudit(audit){
    if(audit===undefined)return null;
    const spec=CONFIG.null_rates,fields=new Map(spec.fields.map(([t,c])=>['null_field.'+t+'.'+c,[t,c]]));
    if(!audit||audit.policy_version!==spec.policy_version||audit.zero_presence_requires_review!==true||
      audit.thresholds?.strong!==CONFIG.thresholds.proportion_pp.strong||audit.thresholds?.acceptable!==CONFIG.thresholds.proportion_pp.acceptable||
      !Array.isArray(audit.rows)||audit.rows.length!==fields.size||new Set(audit.rows.map(r=>r.key)).size!==fields.size||
      !Number.isSafeInteger(audit.summary?.additional_unpublished_variables)||audit.summary.additional_unpublished_variables<0)throw new Error('Invalid null audit');
    for(const r of audit.rows){const field=fields.get(r.key);
      if(!field||r.table!==field[0]||r.column!==field[1]||r.label!==field[0]+'.'+field[1]+' · null rate'||r.family!=='nulls'||r.policy!=='proportion_pp'||!spec.reasons.includes(r.reason))throw new Error('Invalid null evidence');
      const expected=classifyNull(r);
      for(const [k,v] of Object.entries(expected))if(typeof v==='number'?typeof r[k]!=='number'||Math.abs(r[k]-v)>1e-12:r[k]!==v)throw new Error('Inconsistent null evidence');
    }
    const expected=nullSummary(audit.rows,audit.summary.additional_unpublished_variables);
    for(const k of spec.summary_keys)if(audit.summary[k]!==expected[k])throw new Error('Inconsistent null summary');
    return audit;
  }

  function legacyNullCorrection(v){
    // Historical v2 files stay readable, but exact zero counts never become strengths.
    for(const a of v.assessments.filter(a=>a.family==='nulls')){
      const r=classifyNull(a);for(const k of ['source','generated','difference','score','source_count','source_n','generated_count','generated_n','status','reason'])a[k]=r[k];
    }
    const counts=Object.fromEntries(['STRONG','ACCEPTABLE','NEEDS_REVIEW','UNAVAILABLE','TRIVIAL'].map(s=>[s,v.assessments.filter(a=>a.status===s).length]));
    Object.assign(v.summary,{strong:counts.STRONG,acceptable:counts.ACCEPTABLE,needs_review:counts.NEEDS_REVIEW,unavailable:counts.UNAVAILABLE,trivial_zero_null:counts.TRIVIAL,checks_evaluated:v.assessments.length-counts.UNAVAILABLE});
    // Fixed core variable grouping follows numeric/category/date keys, not field-name guesses.
    const variables=['credit_limit','current_balance','available_credit','overlimit','past_due','birth','customer_since','account_open'];
    const states=variables.map(key=>v.assessments.filter(a=>a.key.endsWith('.'+key)&&['numeric','categorical','dates','nulls'].includes(a.family)));
    v.summary.variables_evaluated=states.filter(rows=>rows.some(a=>a.status!=='UNAVAILABLE')).length;
    v.summary.variables_requiring_review=states.filter(rows=>rows.some(a=>a.status==='NEEDS_REVIEW')).length;
    v.summary.variables_incomplete=states.filter(rows=>!rows.some(a=>a.status==='NEEDS_REVIEW')&&rows.some(a=>a.status==='UNAVAILABLE')).length;
    v.summary.variables_within_tolerance=8-v.summary.variables_requiring_review-v.summary.variables_incomplete;
    v.summary.comparison_status=v.summary.needs_review?'REVIEW_REQUIRED':v.summary.unavailable?'PARTIAL':'WITHIN_TOLERANCE';
    const byKey=new Map(v.assessments.map(a=>[a.key,a]));
    for(const selection of [v,v.post_pilot].filter(Boolean))for(const key of ['strengths','weaknesses'])selection[key]=selection[key].filter(id=>{
      const a=byKey.get(id);return !a||a.family!=='nulls'||(key==='strengths'?classifyNull(a).strength_eligible:a.status==='NEEDS_REVIEW');
    });
  }

  function normalizeValidation(report) {
    if (!report || report.schema_version !== "2.0" || report.validation?.status !== "PASS") return null;
    if(typeof report.pipeline_completed_at!=="string" || !Number.isFinite(Date.parse(report.pipeline_completed_at)))throw new Error("Invalid validation report");
    const rawValidation=report.validation_report;
    const v=rawValidation?structuredClone(rawValidation):rawValidation;
    if(!v || v.status!=="AVAILABLE") return null;
    const statuses=["STRONG","ACCEPTABLE","NEEDS_REVIEW","UNAVAILABLE","TRIVIAL"];
    const audit=normalizeNullAudit(v.null_rate_audit);
    if(v.policy_version!==CONFIG.policy_version || v.min_conditional_rows!==CONFIG.min_conditional_rows || !Array.isArray(v.assessments) || v.assessments.length>100 ||
       !Array.isArray(v.numeric) || v.numeric.length!==4 || !v.summary || !v.thresholds) throw new Error("Invalid validation report");
    const seen=new Set();
    if(v.assessments.length!==Object.keys(CONFIG.assessments).length)throw new Error("Invalid validation report");
    for(const [name,limits] of Object.entries(CONFIG.thresholds)){
      if(v.thresholds[name]?.strong!==limits.strong || v.thresholds[name]?.acceptable!==limits.acceptable)throw new Error("Invalid validation report");
    }
    if(Object.keys(v.thresholds).length!==Object.keys(CONFIG.thresholds).length)throw new Error("Invalid validation report");
    for(const a of v.assessments){
      if(typeof a.key!=="string" || seen.has(a.key) || !statuses.includes(a.status) || typeof a.label!=="string" || a.label.length>140 ||
         (a.score!==null && (typeof a.score!=="number" || !Number.isFinite(a.score) || a.score<0)))throw new Error("Invalid validation report");
      seen.add(a.key);
      const expected=CONFIG.assessments[a.key];
      if(!expected || a.label!==expected.label || a.family!==expected.family || a.policy!==expected.policy)throw new Error("Invalid validation report");
      const limits=CONFIG.thresholds[a.policy];
      const nullEvidence=a.family==='nulls'&&audit?classifyNull(a):null;
      const expectedStatus=nullEvidence?nullEvidence.status:a.score===null?"UNAVAILABLE":!limits?(a.score===0?"STRONG":"NEEDS_REVIEW"):a.score<=limits.strong+1e-9?"STRONG":a.score<=limits.acceptable+1e-9?"ACCEPTABLE":"NEEDS_REVIEW";
      if(a.status!==expectedStatus)throw new Error("Invalid validation report");
      if(nullEvidence){
        const field=CONFIG.null_rates.core_fields[a.key], full=audit.rows.find(r=>r.table===field[0]&&r.column===field[1]);
        for(const k of ['source','generated','difference','score','reason','status','source_count','generated_count','source_n','generated_n'])if(a[k]!==nullEvidence[k]||a[k]!==full[k])throw new Error('Inconsistent core null evidence');
      }
      for(const name of ["source","generated","difference","source_n","generated_n","source_count","generated_count"]){if(a[name]!==null && (typeof a[name]!=="number"||!Number.isFinite(a[name])))throw new Error("Invalid validation report");}
    }
    if(v.numeric.length!==new Set(v.numeric.map(n=>n.key)).size)throw new Error("Invalid validation report");
    const finiteOrNull=value=>value===null||(typeof value==="number"&&Number.isFinite(value));
    for(const n of v.numeric){
      if(!Object.hasOwn(NUMERIC,n.key) || n.label!==NUMERIC[n.key] || !Array.isArray(n.percentiles) || n.percentiles.length!==4 ||
         new Set(n.percentiles.map(p=>p.name)).size!==4 || n.percentiles.some(p=>!["P25","P50","P75","P95"].includes(p.name)))throw new Error("Invalid validation report");
      if([n.source_iqr,n.average_difference_pct_iqr,n.max_difference_pct_iqr,...n.percentiles.flatMap(p=>[p.source,p.generated,p.difference])].some(value=>!finiteOrNull(value)))throw new Error("Invalid validation report");
      const a=v.assessments.find(a=>a.key==="numeric."+n.key);if(n.status!==a.status || n.max_difference_pct_iqr!==a.score)throw new Error("Invalid validation report");
    }
    for(const name of ["variables_total","variables_evaluated","variables_within_tolerance","variables_requiring_review","variables_incomplete","checks_evaluated","strong","acceptable","needs_review","unavailable"])if(!Number.isSafeInteger(v.summary[name])||v.summary[name]<0)throw new Error("Invalid validation report");
    if(v.summary.variables_total!==8 || v.summary.variables_evaluated>v.summary.variables_total || v.summary.variables_within_tolerance+v.summary.variables_requiring_review+v.summary.variables_incomplete!==v.summary.variables_total || v.summary.checks_evaluated!==v.summary.strong+v.summary.acceptable+v.summary.needs_review+(v.summary.trivial_zero_null||0))throw new Error("Invalid validation report");
    if((v.summary.trivial_zero_null||0)!==v.assessments.filter(a=>a.status==='TRIVIAL').length)throw new Error('Invalid trivial count');
    if(audit){const expected=v.summary.needs_review||audit.summary.requiring_review?'REVIEW_REQUIRED':v.summary.unavailable||audit.summary.unavailable?'PARTIAL':'WITHIN_TOLERANCE';if(v.summary.comparison_status!==expected)throw new Error('Inconsistent null review status');}
    for(const [name,keys] of [["dates",["birth","customer_since","account_open"]],["cardinality",["accounts_per_customer","relationships_outgoing","relationships_incoming","tradelines_per_customer"]]]){
      if(!Array.isArray(v[name]) || v[name].length!==keys.length || new Set(v[name].map(r=>r.key)).size!==keys.length || v[name].some(r=>!keys.includes(r.key)))throw new Error("Invalid validation report");
      for(const r of v[name]){const a=v.assessments.find(a=>a.key===(name==="dates"?"date.":"cardinality.")+r.key);if(r.label!==a.label||r.status!==a.status)throw new Error("Invalid validation report");}
    }
    if(!Array.isArray(v.categorical)||v.categorical.length!==2||new Set(v.categorical.map(r=>r.category)).size!==2||v.categorical.some(r=>!["Y","N"].includes(r.category)))throw new Error("Invalid validation report");
    for(const r of v.cardinality){if(!Array.isArray(r.bins)||r.bins.length!==6||new Set(r.bins.map(b=>b.bucket)).size!==6||r.bins.some(b=>!["0","1","2","3","4","5+"].includes(b.bucket)))throw new Error("Invalid validation report");}
    if(!Array.isArray(v.populations)||v.populations.length!==6||new Set(v.populations.map(r=>r.table)).size!==6||v.populations.some(r=>!Object.hasOwn(TABLES,r.table)))throw new Error("Invalid validation report");
    for(const [name,count] of [["strong","STRONG"],["acceptable","ACCEPTABLE"],["needs_review","NEEDS_REVIEW"],["unavailable","UNAVAILABLE"]])if(v.summary[name]!==v.assessments.filter(a=>a.status===count).length)throw new Error("Invalid validation report");
    for(const key of ["strengths","weaknesses"]){
      if(!Array.isArray(v[key]) || v[key].length>6 || new Set(v[key]).size!==v[key].length)throw new Error("Invalid validation report");
      if(v[key].some(k=>!v.assessments.some(a=>a.key===k && a.status===(key==="strengths"?"STRONG":"NEEDS_REVIEW"))))throw new Error("Invalid validation report");
    }
    // Ignore IDs and any arbitrary extra metadata; only the public report is hosted.
    if(v.dependency_fidelity!==undefined){
      const d=v.dependency_fidelity, labels={account_type_product:"Account type / client product",client_tsys_product:"Client / TSYS product"};
      const bounded=(value,max)=>value===null||(typeof value==="number"&&Number.isFinite(value)&&value>=0&&value<=max);
      const count=value=>value===null||(Number.isSafeInteger(value)&&value>=0);
      if(!d || !Array.isArray(d.categorical)||d.categorical.length!==2||new Set(d.categorical.map(r=>r.key)).size!==2||
         !Array.isArray(d.numeric_segments)||d.numeric_segments.length!==4||new Set(d.numeric_segments.map(r=>r.bucket)).size!==4)throw new Error("Invalid dependency evidence");
      for(const r of d.categorical){
        if(!Object.hasOwn(labels,r.key)||r.label!==labels[r.key]||![r.source_cramers_v,r.generated_cramers_v,r.absolute_association_gap,r.unsupported_combination_rate].every(x=>bounded(x,1))||
           !bounded(r.conditional_tvd_pct,100)||!count(r.source_n)||!count(r.generated_n))throw new Error("Invalid dependency evidence");
      }
      for(const r of d.numeric_segments)if(!["Q1","Q2","Q3","Q4"].includes(r.bucket)||![r.source_mean,r.generated_mean,r.mean_difference].every(finiteOrNull)||!count(r.source_n)||!count(r.generated_n))throw new Error("Invalid dependency evidence");
    }
    if(v.post_pilot!==undefined){
      const p=v.post_pilot,expected=CONFIG.post_pilot;
      if(!p||p.policy_version!==expected.policy_version||p.provisional!==true||p.min_conditional_rows!==CONFIG.min_conditional_rows||
        p.integrity_requirements?.snapshot_join_coverage!==1||p.integrity_requirements?.allowed_violations!==0||
        !p.thresholds||Object.keys(p.thresholds).length!==Object.keys(expected.thresholds).length)throw new Error("Invalid screening policy");
      for(const [k,t] of Object.entries(expected.thresholds))if(p.thresholds[k]?.strong!==t.strong||p.thresholds[k]?.acceptable!==t.acceptable)throw new Error("Invalid screening policy");
      if(!Array.isArray(p.assessments)||p.assessments.length!==Object.keys(expected.assessments).length||new Set(p.assessments.map(a=>a.key)).size!==p.assessments.length)throw new Error("Invalid screening evidence");
      for(const a of p.assessments){
        const spec=expected.assessments[a.key],limits=expected.thresholds[a.policy];
        const kind={tail:"tail_iqr_pct",date_bounds:"date_bound_days",categorical_conditional:"conditional_tvd_pct"};
        if(!spec||a.label!==spec.label||a.family!==spec.family||!limits||
          a.policy!==(a.family==="mean"?(a.source===0?"zero_mean_absolute":"mean_relative_pct"):kind[a.family])||
          ![a.source,a.generated,a.difference,a.score,a.source_n,a.generated_n].every(finiteOrNull)||a.score!==null&&a.score<0)throw new Error("Invalid screening evidence");
        const status=a.score===null?"UNAVAILABLE":a.score<=limits.strong+1e-9?"STRONG":a.score<=limits.acceptable+1e-9?"ACCEPTABLE":"NEEDS_REVIEW";
        if(a.status!==status)throw new Error("Invalid screening evidence");
      }
      if(!Array.isArray(p.numeric_details)||p.numeric_details.length!==4||new Set(p.numeric_details.map(r=>r.key)).size!==4)throw new Error("Invalid screening evidence");
      for(const r of p.numeric_details)if(!Object.hasOwn(NUMERIC,r.key)||r.label!==NUMERIC[r.key]||!Array.isArray(r.tail_points)||r.tail_points.length!==3||
        new Set(r.tail_points.map(t=>t.name)).size!==3||r.tail_points.some(t=>!["P01","P05","P99"].includes(t.name)||![t.source,t.generated,t.difference].every(finiteOrNull))||
        ![r.mean_relative_pct,r.source_minimum,r.generated_minimum,r.source_maximum,r.generated_maximum,r.source_stddev,r.generated_stddev].every(finiteOrNull))throw new Error("Invalid screening evidence");
      const all=[...v.assessments,...p.assessments,...(audit?.rows||[])];
      for(const [k,status] of [["strengths","STRONG"],["weaknesses","NEEDS_REVIEW"],["zero_reference_alerts","NEEDS_REVIEW"]])if(!Array.isArray(p[k])||p[k].length>6||new Set(p[k]).size!==p[k].length||p[k].some(key=>!all.some(a=>a.key===key&&a.status===status&&(k!=="zero_reference_alerts"||a.policy==="zero_mean_absolute"))))throw new Error("Invalid screening findings");
    }
    normalizePrivacy(report.privacy);
    if(!audit)legacyNullCorrection(v);
    return {report, v};
  }

  function normalizePrivacy(p){
    if(p===undefined)return null;
    const count=n=>n===null||Number.isSafeInteger(n)&&n>=0,rate=n=>n===null||typeof n==="number"&&Number.isFinite(n)&&n>=0&&n<=1;
    if(!p||!["PASS","REVIEW_REQUIRED","BLOCKED","UNAVAILABLE"].includes(p.status)||p.row_level_downloads_enabled!==false||p.formal_anonymization_certified!==false||
      ![p.checks_recorded,p.checks_expected,p.identifier_overlap_rows,p.exact_source_row_matches].every(count))throw new Error("Invalid privacy report");
    if(p.policy!==null){const c=p.policy;if(!c||p.policy_version!=="basic_v1"||!Number.isSafeInteger(c.rare_min_count)||c.rare_min_count<1||
      !Number.isSafeInteger(c.near_date_days)||c.near_date_days<0||c.near_date_days>366||!Number.isSafeInteger(c.max_similarity_candidates)||c.max_similarity_candidates<1||
      c.max_synthetic_rare_fraction===null||!rate(c.max_synthetic_rare_fraction)||c.min_complete_fraction===null||!rate(c.min_complete_fraction)||c.min_complete_fraction===0)throw new Error("Invalid privacy policy");
    }else if(p.policy_version!==null||p.status!=="UNAVAILABLE")throw new Error("Invalid privacy policy");
    const n=p.near_matches;
    if(!n||JSON.stringify(n.variables)!==JSON.stringify(["BIRTH_DT","SINCE_DT","GENDER_CD"])||![n.evaluated_rows,n.flagged_rows,n.minimum_combined_distance_days].every(count)||
      !rate(n.flagged_fraction)||!rate(n.complete_case_coverage)||n.flagged_rows!==null&&n.evaluated_rows!==null&&n.flagged_rows>n.evaluated_rows||
      n.flagged_fraction!==(n.flagged_rows!==null&&n.evaluated_rows?n.flagged_rows/n.evaluated_rows:null))throw new Error("Invalid privacy evidence");
    const labels={customer_category:"Customer category pattern",employment:"Employment / occupation pattern",account_product:"Account type / product pattern"};
    if(!Array.isArray(p.categorical_patterns)||p.categorical_patterns.length!==3||new Set(p.categorical_patterns.map(r=>r.key)).size!==3||p.categorical_patterns.some(r=>!Object.hasOwn(labels,r.key)||r.label!==labels[r.key]||
      !["PASS","INFO","FAIL","REVIEW_REQUIRED","UNAVAILABLE","ERROR"].includes(r.status)||![r.evaluated_rows,r.synthetic_rare_rows,r.source_rare_match_rows].every(count)||!rate(r.complete_case_coverage)))throw new Error("Invalid privacy evidence");
    if(p.status==="PASS"&&(!p.policy||p.checks_recorded!==p.checks_expected||p.identifier_overlap_rows!==0||p.exact_source_row_matches!==0||n.flagged_rows!==0||
      p.categorical_patterns.some(r=>!["PASS","INFO"].includes(r.status)||r.source_rare_match_rows!==0)))throw new Error("Invalid privacy clearance");
    return p;
  }

  function scopeCounts(v){
    // Presentation counts only: statuses and thresholds are supplied by the report.
    const screens=v.post_pilot?.assessments;
    return {core:v.summary,additional:screens?{total:screens.length,
      within:screens.filter(a=>['STRONG','ACCEPTABLE'].includes(a.status)).length,
      review:screens.filter(a=>a.status==='NEEDS_REVIEW').length,
      unavailable:screens.filter(a=>a.status==='UNAVAILABLE').length}:null,missingness:v.null_rate_audit?.summary||null};
  }

  function missingnessScopeDetails(doc,n){
    return details(doc,'Scope, exclusions and missing evidence',
      el(doc,'p','The full missingness audit covers '+fmt(n.variables_total)+' reviewed fields. '+fmt(n.variables_evaluated)+' have valid paired counts: '+fmt(n.trivial_zero_null)+' are trivial zero-to-zero matches and '+fmt(n.eligible_nontrivial)+' are nontrivial comparisons. '+fmt(n.unavailable)+' cannot be compared.','measurement-note'),
      el(doc,'p',fmt(n.trivial_zero_null)+' zero-null observations remain accessible in the detailed table but are excluded from highlighted strengths. Filters do not change these counts.','measurement-note'),
      el(doc,'p','Of '+fmt(n.meaningful_matches)+' preserved nonzero rates, '+fmt(n.meaningful_matches-n.all_null_matches)+' have both observed and missing values; '+fmt(n.all_null_matches)+' are entirely null in both populations. Entirely-null agreement demonstrates missingness only, not fidelity of observed values.','measurement-note'));
  }

  function executiveSummary(doc,view,{compact=false}={}) {
    const {v}=view,{core:s,additional:p,missingness:n}=scopeCounts(v),root=el(doc,'div',undefined,'validation-brief');
    const core=el(doc,'article',undefined,'core-outcome');core.setAttribute('aria-label','Core variable validation');
    core.append(el(doc,'p','Core variable validation · '+fmt(s.variables_total)+' selected variables','eyebrow'));
    const conclusion=fmt(s.variables_within_tolerance)+' of '+fmt(s.variables_total)+' selected variables meet every core tolerance.';
    core.append(el(doc,'p',conclusion,'validation-takeaway'));
    const metrics=el(doc,'dl',undefined,'variable-outcomes');
    for(const [value,label,kind] of [[s.variables_within_tolerance,'Within tolerance','within'],[s.variables_requiring_review,'Need review','review'],[s.variables_incomplete,'Incomplete evidence','incomplete']]){
      const item=el(doc,'div',undefined,'outcome-'+kind);item.append(el(doc,'dt',label),el(doc,'dd',fmt(value)));metrics.append(item);
    }
    const bar=el(doc,'div',undefined,'variable-outcome-bar');bar.setAttribute('aria-hidden','true');
    for(const [value,kind] of [[s.variables_within_tolerance,'within'],[s.variables_requiring_review,'review'],[s.variables_incomplete,'incomplete']]){const segment=el(doc,'span',undefined,'outcome-'+kind);segment.style.flexGrow=String(value);bar.append(segment);}
    core.append(metrics,bar,el(doc,'p','Only the '+fmt(s.variables_total)+' selected variables contribute to these outcomes. The full-dataset missingness audit is a separate scope.','measurement-note'));
    const counts=details(doc,'What passes — and how the core checks were counted',
      el(doc,'p','A variable is one field, such as credit limit or account-open date.'),
      el(doc,'p','A variable is within tolerance only when all its core checks are within their tolerances and none has unavailable evidence. Any check needing review puts the variable in Need review; otherwise missing evidence makes it Incomplete.'),
      el(doc,'p',fmt(s.checks_evaluated)+' individual core checks have measured evidence; '+fmt(s.unavailable)+' are not comparable. These '+fmt(s.checks_evaluated+s.unavailable)+' checks cover the selected variables, relationships and structural integrity. They are not '+fmt(s.checks_evaluated+s.unavailable)+' different variables.'),
      el(doc,'p',fmt(s.trivial_zero_null||0)+' of the measured core checks are trivial zero-null observations. They remain recorded but do not count as statistical strengths.'),
      el(doc,'p','Not comparable means evidence is missing, undefined or too sparse to judge. It is neither a pass nor a measured failure. These counts are not an overall accuracy score.'),
      dimensionTable(doc,v));
    core.append(counts);root.append(core);
    const privacy=el(doc,'aside',undefined,'privacy-separation');privacy.setAttribute('aria-label','Separate privacy assessment');
    const privacyLink=el(doc,'a','Read the separate privacy assessment','text-link');privacyLink.setAttribute('href',compact?'validation.html#privacy':'#privacy');
    privacy.append(el(doc,'strong','Privacy · '+(view.report.privacy?.status||'UNAVAILABLE')),el(doc,'p','Statistical similarity does not establish privacy clearance. General dataset release remains blocked.'),privacyLink);root.append(privacy);
    if(compact)return root;
    const scopes=el(doc,'div',undefined,'secondary-scopes');
    const extra=el(doc,'article',undefined,'validation-scope');extra.setAttribute('aria-label','Additional statistical checks');
    extra.append(el(doc,'h3','Additional statistical checks'));
    if(p){extra.append(el(doc,'p',p.within+p.review?fmt(p.review)+' of '+fmt(p.total)+' additional checks need review.':'Additional checks lack comparable evidence.','scope-takeaway'),
      el(doc,'p',fmt(p.within)+' within tolerance · '+fmt(p.unavailable)+' not comparable. These are checks, not additional variables.','measurement-note'),
      details(doc,'What the additional checks cover',el(doc,'p','Means, tails, date boundaries and conditional relationships provide a second view of fidelity. These '+fmt(p.total)+' checks are separate from the core variable outcomes.'),
        table(doc,'Additional checks · separate scope',['Within tolerance','Need review','Not comparable','Total checks'],[[fmt(p.within),fmt(p.review),fmt(p.unavailable),fmt(p.total)]])));
    }else extra.append(el(doc,'p','Additional statistical checks are unavailable in this reporting artifact.','measurement-note'));
    const missing=el(doc,'article',undefined,'validation-scope');missing.setAttribute('aria-label','Full-dataset missingness audit');
    missing.append(el(doc,'h3','Full-dataset missingness audit'));
    if(n){missing.append(el(doc,'p',n.eligible_nontrivial?fmt(n.meaningful_matches)+' of '+fmt(n.eligible_nontrivial)+' nontrivial comparisons preserve missingness within tolerance.':'No nontrivial missingness comparisons are available.','scope-takeaway'),
      el(doc,'p',fmt(n.requiring_review)+' need review. Scope: '+fmt(n.variables_total)+' reviewed fields; '+fmt(n.unavailable)+' unavailable comparison'+(n.unavailable===1?'':'s')+'.','measurement-note'),missingnessScopeDetails(doc,n));
    }else missing.append(el(doc,'p','Full six-table null-rate audit unavailable in this historical report. Selected zero-null observations are excluded from strengths; missing comparisons are not invented.','measurement-note'));
    const additionalLink=el(doc,'a','Inspect detailed measurements','text-link');additionalLink.setAttribute('href','#numeric');extra.append(additionalLink);
    const missingLink=el(doc,'a','Inspect missingness comparisons','text-link');missingLink.setAttribute('href','#completeness');missing.append(missingLink);
    scopes.append(extra,missing);root.append(scopes);return root;
  }

  function findingCopy(a,v){
    const strong=a.status==='STRONG',copy={title:a.label,why:strong?'This characteristic supports closer baseline-like test scenarios.':'Review this characteristic before relying on baseline-like test scenarios.',
      source:fmt(a.source),synthetic:fmt(a.generated),gap:measure(a.score,UNITS[a.policy]||UNITS.integrity)};
    const fieldNames={DOMICILE_TRANSIT_NUM:['Customer home-branch codes','customer segmentation by home branch'],BRANCH_NUM:['Account branch codes','account segmentation by branch'],OFFICER_NBR:['Account officer codes','officer-based account scenarios'],amount_past_due:['Tradeline past-due amounts','past-due credit scenarios'],subscriber_code:['Tradeline subscriber codes','credit-provider segmentation']};
    if(a.family==='nulls'){
      const field=fieldNames[a.column],label=field?field[0]:a.label.replace(' · null rate','');
      copy.title=strong?label+' preserve their missing-value pattern':a.generated===1&&a.source<1?label+' are absent from the synthetic cohort':a.generated>a.source?label+' are missing more often':label+' are missing less often';
      copy.source=pct(a.source)+' missing';copy.synthetic=pct(a.generated)+' missing';
      copy.why=field?'Could affect tests involving '+field[1]+'.':'Missing values can change which records remain in analysis.';
    }else if(a.family==='numeric'){
      copy.title=a.label+(strong?' has closely matching measured percentiles':' has gaps at key points in its range');
      const r=v.numeric.find(r=>'numeric.'+r.key===a.key),points=r?.percentiles.filter(p=>p.difference!==null)||[];
      const worst=points.sort((a,b)=>Math.abs(b.difference)-Math.abs(a.difference))[0];
      if(worst){const point={P25:'lower-quarter point (P25)',P50:'median (P50)',P75:'upper-quarter point (P75)',P95:'high-end point (P95)'}[worst.name];copy.source=fmt(worst.source)+' at the '+point;copy.synthetic=fmt(worst.generated)+' at the '+point;}
      copy.why=a.key==='numeric.available_credit'?'Could affect scenarios based on available spending capacity.':'The range of amounts matters for dashboard totals and threshold-based scenarios.';
    }else if(a.family==='mean'){
      copy.title=a.label.replace(' mean','')+(strong?' has a close average':a.generated>a.source?' has a higher average':' has a lower average');
      copy.why='A different average can change exposure or balance summaries in analytical tests.';
    }else if(a.family==='dates'){
      copy.title=a.key==='date.birth'?'The customer age mix needs review':a.key==='date.customer_since'?'The customer tenure mix needs review':a.label+' needs review';
      if(strong)copy.title=a.label+' closely matches';copy.source='Monthly proportions not published';copy.synthetic='Monthly proportions not published';
      copy.why='Date patterns can change the mix of customers represented in time-based segments.';
    }else if(a.family==='date_bounds'){
      copy.title=a.label.replace(' distribution bounds',' date bounds')+(strong?' closely match':' differ');
      copy.source='Absolute dates not published';copy.synthetic='Absolute dates not published';
      copy.why='Matching boundaries supports date-range scenarios; it does not establish a matching distribution inside that range.';
    }else if(a.family==='cardinality'){
      const r=v.cardinality.find(r=>'cardinality.'+r.key===a.key);copy.title=a.label+(strong?' closely match':' need review');
      copy.source=fmt(r?.source_mean)+' on average';copy.synthetic=fmt(r?.generated_mean)+' on average';
      copy.why='Record links determine the workload and joins exercised by relational tests.';
    }else if(a.family==='categorical_conditional'){
      const r=v.dependency_fidelity?.categorical.find(r=>'categorical_conditional.'+r.key===a.key);
      copy.title=a.key.endsWith('client_tsys_product')?'Product-code relationships '+(strong?'closely match':'need review'):'Account-type and product pairings '+(strong?'closely match':'need review');
      copy.source=fmt(r?.source_cramers_v)+' association strength';copy.synthetic=fmt(r?.generated_cramers_v)+' association strength';
      copy.why='Consistent combinations matter when testing related account and product fields.';
    }else if(a.family==='correlation'){
      copy.title=strong?'Balances and credit limits retain a similar relationship':'The balance–credit-limit relationship differs';
      copy.why='Independent-looking amounts can misrepresent scenarios that depend on the two fields varying together.';
    }else if(a.family==='conditional'){
      copy.title=strong?'Past-due rates closely match in this utilization group':'Past-due rates differ in this utilization group';copy.source=pct(a.source);copy.synthetic=pct(a.generated);
      copy.why='This relationship matters for scenarios that segment accounts by credit usage.';
    }
    return copy;
  }

  function executiveFindings(doc,view) {
    const {v}=view,root=el(doc,"div",undefined,"findings-grid"),byKey=new Map([...v.assessments,...(v.post_pilot?.assessments||[]),...(v.null_rate_audit?.rows||[])].map(a=>[a.key,a]));
    for(const [key,title] of [["strengths","Strongest measured areas"],["weaknesses","Largest measured deviations"]]){
      const panel=el(doc,"div",undefined,"finding-panel");panel.append(el(doc,"h3",title));
      const makeList=(ids,offset=0)=>{const list=el(doc,"ol",undefined,"finding-list");list.setAttribute("start",String(offset+1));list.style.counterReset="findings "+offset;for(const id of ids){const a=byKey.get(id),copy=findingCopy(a,v),li=el(doc,"li");const scope=a.key.startsWith('null_field.')?'Full-dataset missingness':v.post_pilot?.assessments.some(r=>r.key===a.key)?'Additional statistical check':'Core evidence';li.append(el(doc,"strong",copy.title),el(doc,'p',scope,'finding-scope'),el(doc,"p",'SOURCE '+copy.source+' · Synthetic '+copy.synthetic,'finding-values'),el(doc,'p',copy.why,'finding-meaning'),details(doc,'Measurement details',el(doc,'p',a.label+' · '+copy.gap),badge(doc,a.status)));list.append(li);}return list;};
      const selected=v.post_pilot?.[key]||v[key];
      panel.append(selected.length?makeList(selected.slice(0,3)):el(doc,"p","No qualifying measured findings yet."));
      if(selected.length>3)panel.append(details(doc,key==="strengths"?"More measured strengths":"More measured discrepancies",makeList(selected.slice(3),3)));root.append(panel);
    }
    return root;
  }

  // Presentation only: consume existing scores/statuses; do not reclassify evidence.
  function explorationRows(v,kind,key) {
    if(kind==='numeric')return v.assessments.filter(a=>a.family==='numeric').map(a=>({...a,gap:a.score,rank:a.status==='UNAVAILABLE'?null:a.score}));
    if(kind==='categorical')return v.categorical.map(r=>({key:r.category,label:r.category==='Y'?'Past due (Y)':'Not past due (N)',source:r.source,generated:r.generated,gap:r.absolute_difference_pp,rank:r.status==='UNAVAILABLE'?null:r.absolute_difference_pp,status:r.status,reason:null}));
    return v.assessments.filter(a=>key==='correlation'?a.key==='correlation.balance_limit':a.family==='conditional').map(a=>({...a,label:key==='correlation'?a.label:a.label.replace('Past due · utilization ',''),gap:key==='correlation'?a.score:a.difference===null?null:Math.abs(a.difference)*100,rank:a.status==='UNAVAILABLE'?null:a.score}));
  }
  const guideDocuments=new WeakSet(),openGuides=new WeakMap();
  function metricGuide(doc,id) {
    const wrap=el(doc,'div',undefined,'metric-guide'),button=el(doc,'button','Metric guide'),tip=el(doc,'div',undefined,'metric-tooltip');
    button.type='button';button.setAttribute('aria-controls',id);button.setAttribute('aria-expanded','false');tip.id=id;tip.hidden=true;tip.setAttribute('role','tooltip');button.setAttribute('aria-describedby',id);wrap.append(button,tip);let pinned=false;
    const close=()=>{pinned=false;show(false);};
    const show=open=>{if(open){const previous=openGuides.get(doc);if(previous&&previous!==close)previous();openGuides.set(doc,close);}else if(openGuides.get(doc)===close)openGuides.delete(doc);tip.hidden=!open;button.setAttribute('aria-expanded',String(open));};
    wrap.addEventListener('pointerenter',e=>{if(e.pointerType!=='touch')show(true);});
    wrap.addEventListener('pointerleave',()=>{if(!pinned&&doc.activeElement!==button)show(false);});
    button.addEventListener('focus',()=>show(true));button.addEventListener('blur',()=>{pinned=false;show(false);});
    button.addEventListener('click',()=>{pinned=!pinned;show(pinned);});
    button.addEventListener('keydown',e=>{if(e.key==='Escape'){pinned=false;show(false);e.preventDefault();}});
    // Dismiss hover help with Escape even when keyboard focus is elsewhere.
    if(doc.addEventListener&&!guideDocuments.has(doc)){doc.addEventListener('keydown',e=>{if(e.key==='Escape')openGuides.get(doc)?.();});guideDocuments.add(doc);}
    return {wrap,tip};
  }
  function exploreValidation(doc,view) {
    const v=view.v,root=section(doc,'explore-validation','Explore the measured results','Choose a validation type and a published variable. The executive findings above and the full evidence below remain available.'),tabs=el(doc,'div',undefined,'validation-tabs');
    root.className+=' validation-explorer';tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label','Validation type');
    const kinds=[['numeric','Numeric'],['categorical','Categorical'],['dependency','Dependency']],buttons=[],panels=[];
    const finite=n=>typeof n==='number'&&Number.isFinite(n),matches=(r,mode)=>mode==='all'||r.status===(mode==='strong'?'STRONG':'NEEDS_REVIEW');
    root.append(tabs);
    for(const [kind,label] of kinds){
      const tab=el(doc,'button',label),panel=el(doc,'div',undefined,'validation-panel'),controls=el(doc,'div',undefined,'validation-controls'),variable=el(doc,'select'),mode=el(doc,'select');
      tab.type='button';tab.id='validation-tab-'+kind;tab.setAttribute('role','tab');tab.setAttribute('aria-controls','validation-panel-'+kind);tabs.append(tab);buttons.push(tab);
      panel.id='validation-panel-'+kind;panel.setAttribute('role','tabpanel');panel.setAttribute('aria-labelledby',tab.id);panel.tabIndex=0;panels.push(panel);
      function picker(text,node,id){const l=el(doc,'label',text);node.id=id;l.setAttribute('for',id);const field=el(doc,'div');field.append(l,node);return field;}
      variable.setAttribute('aria-label',label+' variable');mode.setAttribute('aria-label',label+' match view');
      for(const [value,text] of [['all','All comparisons'],['strong','Strongest matches'],['weak','Weakest matches']]){const o=el(doc,'option',text);o.value=value;mode.append(o);}mode.value='all';
      const variableField=picker(kind==='dependency'?'Relationship':'Variable',variable,'explore-variable-'+kind),variableHelp=el(doc,'p',undefined,'control-help');variableHelp.id='explore-variable-help-'+kind;variable.setAttribute('aria-describedby',variableHelp.id);variableField.append(variableHelp);
      controls.append(variableField,picker('Show matches',mode,'explore-matches-'+kind));
      const guide=metricGuide(doc,'metric-guide-'+kind),chart=el(doc,'div',undefined,'exploration-chart'),summary=el(doc,'p',undefined,'exploration-status'),tableRoot=el(doc,'div');summary.setAttribute('role','status');summary.setAttribute('aria-live','polite');
      controls.append(guide.wrap);panel.append(controls,el(doc,'p','Strongest uses the published Strong match classification; weakest uses Needs review. These describe the displayed metric, not overall variable quality. Missing or sparse evidence is never counted as a weak match.','measurement-note'),summary,chart,tableRoot);root.append(panel);
      let selected=kind==='numeric'?'credit_limit':kind==='categorical'?'past_due':'utilization',sort='gap',direction='descending';
      const variables=kind==='numeric'?v.numeric.map(n=>({key:n.key,label:n.label})):kind==='categorical'?[{key:'past_due',label:'Past-due indicator'}]:[{key:'utilization',label:'Past-due rates by utilization'},{key:'correlation',label:'Credit limit / balance correlation'}];
      function rowsFor(key){const rows=explorationRows(v,kind,key);return kind==='numeric'?rows.filter(r=>r.key==='numeric.'+key):rows;}
      function draw(){
        const eligible=variables.filter(n=>rowsFor(n.key).some(r=>matches(r,mode.value)));variable.replaceChildren();
        for(const n of eligible){const o=el(doc,'option',n.label);o.value=n.key;variable.append(o);}
        if(!eligible.some(n=>n.key===selected))selected=eligible[0]?.key||'';
        if(!eligible.length){const o=el(doc,'option','No matching variables');o.value='';variable.append(o);}
        variable.value=selected;variable.disabled=eligible.length<=1;
        variableHelp.textContent=eligible.length===1?'Only one published variable matches this view.':eligible.length===0?'No published variables match this view.':'';variableHelp.hidden=eligible.length>1;
        const descriptor=eligible.find(n=>n.key===selected),rows=explorationRows(v,kind,selected).filter(r=>matches(r,mode.value));
        const rates=kind==='categorical'||kind==='dependency'&&selected!=='correlation';
        const unit=kind==='numeric'?'% of SOURCE IQR':rates?'pp':'correlation units';
        const gapLabel=kind==='numeric'?'Worst percentile gap / IQR':'Absolute gap';
        guide.tip.textContent=kind==='numeric'?'P25, P50, P75 and P95 are measured percentiles; P50 is the median. IQR is the SOURCE middle-50% range. The gap is the published worst percentile gap relative to SOURCE IQR. The table shows medians alongside that distribution gap. A zero or missing IQR prevents normalization.':kind==='categorical'?'Category shares use a common 0–100% scale. A percentage-point (pp) gap is the absolute difference between the two shares, not a relative accuracy percentage. This report publishes only the past-due indicator.':selected==='correlation'?'Pearson r describes linear association on a −1 to +1 scale, not causation. The gap is the absolute difference between the published SOURCE and Synthetic coefficients. Missing paired sample counts remain unavailable.':'Utilization is balance relative to credit limit. Each point shows the past-due share in that utilization bucket. Gaps use percentage points (pp). Sparse buckets retain raw rates but are not comparable under the existing sample-size policy.';
        chart.replaceChildren();
        if(!descriptor){guide.tip.textContent='This view has no published comparisons with the selected classification. Choose All comparisons to inspect the available evidence. No missing result is treated as a weak match.';chart.append(el(doc,'p','No published '+label.toLowerCase()+' comparisons have this classification. Choose All comparisons to see the available evidence.','results-notice'));tableRoot.replaceChildren();summary.textContent='No matching comparisons. No substitute statistics are shown.';return;}
        chart.append(el(doc,'h3',descriptor.label));
        const points=kind==='numeric'?v.numeric.find(n=>n.key===selected).percentiles:rowsFor(selected);
        const hasSource=points.some(p=>finite(p.source)),hasGenerated=points.some(p=>finite(p.generated));
        if(!hasSource&&!hasGenerated)chart.append(el(doc,'p','Comparison chart unavailable: neither population has published values for this metric.','results-notice'));
        else{
          if(!hasSource||!hasGenerated)chart.append(el(doc,'p',(!hasSource?'SOURCE':'Synthetic')+' values are unavailable. Only published points from the other population are shown.','results-notice'));
          if(kind==='numeric')chart.append(VIZ.distribution(doc,v,{key:selected,showSelector:false}));
          else if(kind==='categorical')chart.append(VIZ.categorical(doc,v),el(doc,'p','The sanitized report contains one categorical variable; no other category distributions are inferred.','measurement-note'));
          else if(selected==='utilization')chart.append(VIZ.conditional(doc,v),el(doc,'p','All published buckets remain visible. Hollow points lack sufficient comparison evidence; at least '+v.min_conditional_rows+' records per bucket are required in each population.','measurement-note'));
          else{const a=points[0];if([a.source,a.generated].some(n=>finite(n)&&(n< -1||n>1)))chart.append(el(doc,'p','Correlation chart unavailable: a reported coefficient is outside the expected −1 to +1 range.','results-notice'));
            else chart.append(VIZ.lineChart(doc,'Credit limit / balance: SOURCE and Synthetic Pearson correlation',['Pearson r'],[a.source],[a.generated],{domain:[-1,1],sparse:a.status==='UNAVAILABLE'?[0]:[]}));}
        }
        if(kind==='numeric'&&rowsFor(selected)[0].reason)chart.append(el(doc,'p',REASONS[rowsFor(selected)[0].reason]||'Comparison evidence is unavailable.','measurement-note'));
        const wrap=el(doc,'div',undefined,'table-scroll'),t=el(doc,'table',undefined,'report-table'),thead=el(doc,'thead'),tr=el(doc,'tr'),tbody=el(doc,'tbody');
        wrap.tabIndex=0;wrap.setAttribute('role','region');wrap.setAttribute('aria-label',label+' largest differences');
        const headers=[kind==='numeric'?'Variable':kind==='categorical'?'Category':'Relationship / bucket',kind==='numeric'?'SOURCE median (P50)':rates?'SOURCE share':'SOURCE r',kind==='numeric'?'Synthetic median (P50)':rates?'Synthetic share':'Synthetic r',gapLabel,'Status'],sortable=[];
        headers.forEach((text,i)=>{const th=el(doc,'th');th.setAttribute('scope','col');if(i===0||i===3){const key=i===0?'name':'gap',b=el(doc,'button',text,'exploration-sort');b.type='button';b.setAttribute('aria-label','Sort '+label.toLowerCase()+' differences by '+(key==='name'?'name':'gap'));b.addEventListener('click',()=>{direction=sort===key?(direction==='descending'?'ascending':'descending'):key==='gap'?'descending':'ascending';sort=key;drawRows();});th.append(b);sortable.push({th,key});}else th.textContent=text;tr.append(th);});thead.append(tr);
        function drawRows(){
          const ordered=[...rows].sort((a,b)=>{const aMissing=!finite(a.rank),bMissing=!finite(b.rank);if(aMissing!==bMissing)return aMissing?1:-1;const result=sort==='name'?a.label.localeCompare(b.label):(a.rank??0)-(b.rank??0);return (direction==='descending'?-result:result)||a.label.localeCompare(b.label);});tbody.replaceChildren();
          for(const r of ordered){const row=el(doc,'tr'),name=el(doc,'th',r.label);name.setAttribute('scope','row');row.append(name);
            for(const value of [rates?pct(r.source):fmt(r.source),rates?pct(r.generated):fmt(r.generated),measure(r.gap,unit)])row.append(el(doc,'td',value));
            const statusCell=el(doc,'td');statusCell.append(badge(doc,r.status));if(r.reason)statusCell.append(el(doc,'span',REASONS[r.reason]||'Comparison evidence unavailable.','exploration-reason'));row.append(statusCell);tbody.append(row);}
          for(const s of sortable){s.th.setAttribute('aria-sort',sort===s.key?direction:'none');s.th.children[0].dataset.sortLabel=sort===s.key?(sort==='name'?(direction==='ascending'?'A–Z':'Z–A'):direction==='descending'?'Largest first':'Smallest first'):'Sort';}
          summary.textContent=label+' · '+descriptor.label+'. Showing '+rows.length+' comparison'+(rows.length===1?'':'s')+'. Sorted by '+(sort==='name'?(direction==='ascending'?'name A–Z':'name Z–A'):direction==='descending'?'largest comparable gap':'smallest comparable gap')+'.';
        }
        t.append(el(doc,'caption',label+' statistical differences'),thead,tbody);wrap.append(t);tableRoot.replaceChildren(el(doc,'p','Sort using the first or gap column heading. Only comparable rows are ranked; missing or sparse comparisons stay last even when raw values are shown. All gaps are published measurements, not an overall accuracy score.','measurement-note'),wrap);drawRows();
      }
      variable.addEventListener('change',()=>{selected=variable.value;draw();});mode.addEventListener('change',draw);draw();
    }
    function activate(index,focus=false){buttons.forEach((b,i)=>{b.setAttribute('aria-selected',String(i===index));b.tabIndex=i===index?0:-1;panels[i].hidden=i!==index;});if(focus)buttons[index].focus();}
    buttons.forEach((b,i)=>{b.addEventListener('click',()=>activate(i));b.addEventListener('keydown',e=>{const key={ArrowRight:(i+1)%3,ArrowLeft:(i+2)%3,Home:0,End:2};if(Object.hasOwn(key,e.key)){e.preventDefault();activate(key[e.key],true);}});});activate(0);return root;
  }

  function dimensionTable(doc,v) {
    const families=[["numeric","Numeric distributions"],["categorical","Categorical proportions"],["nulls","Missingness"],["dates","Date distributions"],["correlation","Correlations"],["conditional","Conditional outcomes"],["cardinality","Relationship cardinalities"],["graph","Relationship directionality"],["integrity","Structural / business checks"]];
    return table(doc,"Evidence by dimension",["Dimension","Strong / passed","Acceptable","Needs review","Not comparable","Trivial zero-null"],families.map(([key,label])=>{
      const rows=v.assessments.filter(a=>a.family===key);return [label,...["STRONG","ACCEPTABLE","NEEDS_REVIEW","UNAVAILABLE","TRIVIAL"].map(status=>fmt(rows.filter(a=>a.status===status).length))];
    }));
  }

  function nullDetail(doc,v){
    const root=el(doc,'div',undefined,'null-detail'),audit=v.null_rate_audit;
    const rows=audit?.rows||v.assessments.filter(a=>a.family==='nulls');
    if(audit){const n=audit.summary,metrics=el(doc,'dl',undefined,'exec-metrics quality-metrics');
      for(const [value,label] of [[n.eligible_nontrivial,'Nontrivial comparisons'],[n.meaningful_matches,'Nonzero rates within tolerance'],[n.requiring_review,'Need review'],[n.unavailable,'Not comparable']]){
        const item=el(doc,'div');item.append(el(doc,'dt',label),el(doc,'dd',fmt(value)));metrics.append(item);
      }root.append(metrics,el(doc,'p','Missingness is assessed across '+fmt(n.variables_total)+' reviewed fields. Focus first on nontrivial comparisons and fields needing review.','measurement-note'),missingnessScopeDetails(doc,n));
      if(n.additional_unpublished_variables)root.append(el(doc,'p',n.additional_unpublished_variables+' additional fields are outside the reviewed public metadata allowlist. Their comparisons remain in the private fidelity tables.','measurement-note'));
      const matches=rows.filter(r=>r.strength_eligible).sort((a,b)=>Number(a.all_null_match)-Number(b.all_null_match)||a.score-b.score||a.key.localeCompare(b.key));
      root.append(el(doc,'h3','Meaningful null-rate preservation'),matches.length?el(doc,'p',matches.slice(0,3).map(r=>r.table+'.'+r.column+' ('+fmt(r.score)+' pp gap)').join('; ')+'.','measurement-note'):el(doc,'p','No qualifying meaningful null-rate strengths are available. Zero-to-zero observations do not fill this list.','unavailable-note'));
      const issues=rows.filter(r=>r.status==='NEEDS_REVIEW').sort((a,b)=>b.score-a.score||a.key.localeCompare(b.key));
      if(issues.length){const list=el(doc,'ul',undefined,'quality-limitations');for(const r of issues.slice(0,6))list.append(el(doc,'li',r.table+'.'+r.column+': SOURCE '+pct(r.source)+'; synthetic '+pct(r.generated)+' ('+fmt(r.score)+' pp gap).'));root.append(el(doc,'h3','Null-rate discrepancies'),list);}
    }else root.append(el(doc,'p','Full-table audit unavailable. Only the selected historical comparisons are shown; no missing comparisons are invented.','measurement-note'));
    root.append(details(doc,'How missingness is assessed',el(doc,'p','Exact null counts ÷ row counts determine rates. Zero in both populations is a trivial observation. A zero/nonzero transition always requires review; when both rates are nonzero, gaps above '+fmt(CONFIG.thresholds.proportion_pp.acceptable)+' pp require review. These are provisional screening rules, not significance tests.','measurement-note')));
    const controls=el(doc,'div',undefined,'null-controls'),label=el(doc,'label','Table '),select=el(doc,'select');select.setAttribute('aria-label','Null-rate table');
    for(const [value,text] of [['all','All six tables'],...Object.entries(TABLES)]){const option=el(doc,'option',text);option.value=value;select.append(option);}select.value='all';label.append(select);
    const toggleLabel=el(doc,'label'),toggle=el(doc,'input');toggle.type='checkbox';toggle.checked=true;toggle.setAttribute('aria-label','Hide trivial zero-null matches');toggleLabel.append(toggle,el(doc,'span',' Hide trivial zero-null matches'));controls.append(label,toggleLabel);
    const status=el(doc,'p',undefined,'measurement-note');status.setAttribute('role','status');const body=el(doc,'div');
    const precise=value=>typeof value==='number'&&Number.isFinite(value)?new Intl.NumberFormat('en',{maximumSignificantDigits:5}).format(value*100)+'%':'Unavailable';
    const counts=(a,side)=>a[side+'_count']===null||a[side+'_n']===null?'Unavailable':fmt(a[side+'_count'])+' / '+fmt(a[side+'_n']);
    const reason=a=>a.reason==='zero_null_in_both'?'Excluded from strengths':a.reason==='zero_presence_change'?'Missingness appeared/disappeared':a.reason&&a.status==='UNAVAILABLE'?'Missing, invalid or unpaired counts':a.all_null_match?'Entirely null in both':a.classification==='MEANINGFUL_MATCH'?'Nonzero rate preserved':'';
    function draw(){const visible=rows.filter(r=>(select.value==='all'||r.table===select.value)&&(!toggle.checked||r.status!=='TRIVIAL'));
      status.textContent=visible.length+' fields shown. Full audit: '+rows.length+' recorded comparisons. Display filters do not change assessment counts.';
      body.replaceChildren(table(doc,'Null rates · exact counts across six tables',['Table / field','SOURCE null / rows','SOURCE rate','Synthetic null / rows','Synthetic rate','Absolute gap (pp)','Assessment','Context'],visible.map(a=>[a.table?a.table+'.'+a.column:a.label,counts(a,'source'),precise(a.source),counts(a,'generated'),precise(a.generated),a.score===null?'Unavailable':new Intl.NumberFormat('en',{maximumSignificantDigits:5}).format(a.score),badge(doc,a.status),reason(a)])));
      if(!visible.length)body.append(el(doc,'p','No comparisons match these display options.','unavailable-note'));
    }
    select.addEventListener('change',draw);toggle.addEventListener('change',draw);draw();root.append(controls,status,body);return root;
  }

  function numericDetail(doc,v) {
    const root=el(doc,"div"),sortLabel=el(doc,"label","Sort numeric table ","report-sort"),sort=el(doc,"select"),body=el(doc,"div");sort.setAttribute("aria-label","Sort numeric table");
    for(const [value,label] of [["worst","Largest difference first"],["best","Smallest difference first"],["name","Variable name"]]){const option=el(doc,"option",label);option.value=value;sort.append(option);}sortLabel.append(sort);
    function draw(){const rows=[...v.numeric].sort((a,b)=>sort.value==="name"?NUMERIC[a.key].localeCompare(NUMERIC[b.key]):sort.value==="best"?(a.average_difference_pct_iqr??Infinity)-(b.average_difference_pct_iqr??Infinity):(b.average_difference_pct_iqr??-Infinity)-(a.average_difference_pct_iqr??-Infinity));
      body.replaceChildren(table(doc,"Numeric percentile comparison",["Variable","SOURCE P25","Synthetic P25","SOURCE P50","Synthetic P50","SOURCE P75","Synthetic P75","SOURCE P95","Synthetic P95","Mean gap / IQR","Worst gap / IQR","Status"],rows.map(r=>{const values=[NUMERIC[r.key]];for(const name of ["P25","P50","P75","P95"]){const p=r.percentiles.find(p=>p.name===name);values.push(fmt(p.source),fmt(p.generated));}return [...values,measure(r.average_difference_pct_iqr,"%"),measure(r.max_difference_pct_iqr,"%"),badge(doc,r.status)];})));
    }
    sort.value="worst";sort.addEventListener("change",draw);draw();root.append(sortLabel,body);return root;
  }

  function numericScreening(doc,v){
    const root=el(doc,"div"),p=v.post_pilot,byKey=new Map(p.assessments.map(a=>[a.key,a])),bars=el(doc,"ol",undefined,"mean-comparisons");
    const investigationLink=el(doc,"a","Read the archived pilot investigation","text-link");investigationLink.setAttribute("href","https://github.com/kovacsphil-art/synthetic_banking/blob/main/docs/post-pilot-review.md#balance-mean-explanation-supported-by-decomposition");
    root.append(el(doc,"h3","Means and tail behaviour"),el(doc,"p","A mean uses every value, including extremes. Assess it alongside percentile shape, rather than using one as a substitute for the other.","measurement-note"));
    for(const r of p.numeric_details){
      const a=byKey.get("mean."+r.key),li=el(doc,"li"),heading=el(doc,"div",undefined,"chart-label");heading.append(el(doc,"strong",r.label),badge(doc,a.status));li.append(heading);
      const maximum=Math.max(a.source||0,a.generated||0,0);
      for(const [label,value,cls] of [["SOURCE",a.source,"mean-source"],["Synthetic",a.generated,"mean-synthetic"]]){
        const row=el(doc,"div",undefined,"mean-series"),track=el(doc,"span",undefined,"chart-track"),bar=el(doc,"span",undefined,"chart-bar "+cls);
        bar.style.width=maximum>0&&value!==null?Math.max(0,Math.min(100,100*value/maximum))+"%":"0%";track.setAttribute("aria-hidden","true");track.append(bar);
        row.append(el(doc,"span",label),track,el(doc,"strong",fmt(value)));li.append(row);
      }bars.append(li);
    }
    root.append(bars,el(doc,"p","Each variable has its own linear scale from zero to the larger mean; compare the two series within a variable. Values use native amount units. Missing values are unavailable, not zero.","measurement-note"),
      table(doc,"Numeric mean screening",["Variable","SOURCE mean","Synthetic mean","Signed gap","Gap / SOURCE mean","Status"],p.numeric_details.map(r=>{const a=byKey.get("mean."+r.key);return [r.label,fmt(a.source),fmt(a.generated),signed(a.difference),measure(r.mean_relative_pct,"%"),badge(doc,a.status)];})),
      el(doc,"p","A zero SOURCE mean has no relative percentage. Any nonzero departure is flagged under the provisional native-unit zero-reference tolerance. These are statistical screens, separate from mandatory integrity checks.","measurement-note"),
      details(doc,"Why the balance mean can worsen while percentiles improve",
        el(doc,"p","The current sampler interpolates between measured percentiles. Those points constrain distribution shape, but do not guarantee the measured SOURCE mean."),
        el(doc,"p","Rank coupling reorders the existing balance draws; it preserves their raw values and mean. The later cap at 125% of each account’s credit limit can clip different amounts after that reordering, changing the saved balance distribution."),
        el(doc,"p","The archived pilot replay isolated fewer capped balances as the reason its saved mean rose. The previous pairing’s cap partly offset the sampler’s upward mean bias. These are method diagnostics, separate from the live measurements above."),
        el(doc,"p","Next step: assess credit-limit and balance means together, including available credit and overlimit amounts. A balance-only calibration can improve one mean while worsening a derived amount. No calibration has been activated; the existing coupling and constraints remain in place."),investigationLink),
      table(doc,"P01 / P05 / P99 tail screening",["Variable","SOURCE P01","Synthetic P01","SOURCE P05","Synthetic P05","SOURCE P99","Synthetic P99","Worst gap / IQR","Status"],p.numeric_details.map(r=>{const a=byKey.get("tail."+r.key),values=[r.label];for(const name of ["P01","P05","P99"]){const t=r.tail_points.find(t=>t.name===name);values.push(fmt(t.source),fmt(t.generated));}return [...values,measure(a.score,"%"),badge(doc,a.status)];})),
      details(doc,"Extrema and spread",table(doc,"Extrema and standard deviation",["Variable","SOURCE min","Synthetic min","SOURCE max","Synthetic max","SOURCE std. dev.","Synthetic std. dev."],p.numeric_details.map(r=>[r.label,fmt(r.source_minimum),fmt(r.generated_minimum),fmt(r.source_maximum),fmt(r.generated_maximum),fmt(r.source_stddev),fmt(r.generated_stddev)]))));
    return root;
  }

  function privacySection(doc,report){
    const p=report.privacy,root=section(doc,"privacy","Privacy review and publication boundary","Statistical similarity does not establish privacy clearance. General dataset release remains blocked; fabricated demo downloads have a separate verification process.");
    if(!p){root.append(el(doc,"p","Privacy assessment unavailable. This report does not establish release clearance.","release-notice"));return root;}
    root.append(el(doc,"p",p.status,"report-verdict"),el(doc,"p","General dataset release blocked · No formal anonymization certification","release-notice"),
      table(doc,"Aggregate privacy screening",["Check","Measured result"],[["Recorded checks",fmt(p.checks_recorded)+" / "+fmt(p.checks_expected)],["Identifier overlap rows",fmt(p.identifier_overlap_rows)],["Exact SOURCE-row matches",fmt(p.exact_source_row_matches)],["Selected quasi-identifier near matches",fmt(p.near_matches.flagged_rows)+" / "+fmt(p.near_matches.evaluated_rows)+" ("+pct(p.near_matches.flagged_fraction)+")"],["Minimum combined date distance among matches",measure(p.near_matches.minimum_combined_distance_days,"days")]]));
    if(p.policy){const c=p.policy;root.append(el(doc,"p","The similarity screen requires the same gender and birth/customer-since dates each within "+c.near_date_days+" days, with SOURCE pattern support below "+c.rare_min_count+" for a review flag. It is a bounded candidate comparison, not a global nearest-neighbour or re-identification test.","measurement-note"),
      table(doc,"Categorical-pattern privacy checks",["Pattern","Evaluated synthetic rows","Synthetic-rare rows","SOURCE-rare pattern matches","Complete-case coverage","Status"],p.categorical_patterns.map(r=>[r.label,fmt(r.evaluated_rows),fmt(r.synthetic_rare_rows),fmt(r.source_rare_match_rows),pct(r.complete_case_coverage),r.status])),
      el(doc,"p","Synthetic rarity and SOURCE rarity differ: a pattern can be common in a larger generated cohort yet have low SOURCE support. Any SOURCE-rare match requires review; synthetic-rare fraction above "+pct(c.max_synthetic_rare_fraction)+" or coverage below "+pct(c.min_complete_fraction)+" also requires review. Identifier overlap or exact SOURCE-row matches block release; missing checks or a candidate budget above "+fmt(c.max_similarity_candidates)+" are not passing evidence.","measurement-note"));}
    root.append(el(doc,"p","The SOURCE baseline is fabricated development data. These are similarity flags, not confirmed disclosures. Shared distributions can produce chance matches; no real-customer disclosure is demonstrated here. The flagged fraction is not an estimated probability of re-identification.","measurement-note"),
      details(doc,"What REVIEW_REQUIRED means for the fabricated demo",
        el(doc,"p","This fixed-variable screen is useful as a lightweight diagnostic, but cannot prove fabricated origin or establish privacy clearance. It does not test other identifying combinations, external-data linkage, membership inference or cumulative risk across releases."),
        el(doc,"p","DEMO_ONLY eligibility separately requires exact fabricated-origin verification, schema and content screening, matching dataset versions and explicit publication authorization. Verified demo availability does not change the privacy assessment or permit production-derived records."),
        el(doc,"p","For any proposed general release, review the need for exact birth/customer-since dates and gender. Consider coarsening or omitting unnecessary fields and reviewing low-support categories, then re-screen the actual release and assess utility loss. Do not relax thresholds merely to clear these findings.")));
    const demoLink=el(doc,"a","Check verified fabricated demo availability","text-link");demoLink.setAttribute("href","index.html#download-dataset");root.append(demoLink);
    return root;
  }

  function renderValidation(doc,view) {
    const {report,v}=view,root=el(doc,"div"),byKey=new Map(v.assessments.map(a=>[a.key,a]));
    const summary=section(doc,"summary",v.summary.variables_requiring_review?'Core results need review.':v.summary.variables_incomplete?'Some core evidence is incomplete.':'Selected variables meet the core tolerances.');
    summary.append(executiveSummary(doc,view),el(doc,"p","Completed "+new Date(report.pipeline_completed_at).toLocaleString("en",{timeZone:"UTC"})+" UTC · Comparison is against the repository’s fake development SOURCE baseline. Representativeness of real production banking data has not been established.","measurement-note"));
    const findings=section(doc,"findings","What matches — and what could affect its use","Largest deviations and strong matches are selected from the measured results. Each finding names its scope; expand its measurement details for the underlying metric.");findings.append(executiveFindings(doc,view));

    const numeric=section(doc,"numeric","Inspect the distribution — including the upper tail","Compare four measured percentiles. A close median can coexist with a materially different upper tail.");numeric.append(VIZ.distribution(doc,v));
    if(v.post_pilot)numeric.append(numericScreening(doc,v));
    const bars=el(doc,"ol",undefined,"percentile-chart"),scale=Math.max(15,...v.numeric.map(n=>n.average_difference_pct_iqr||0));bars.setAttribute("aria-label","Fidelity by variable: average percentile difference, lower is closer");
    for(const n of [...v.numeric].sort((a,b)=>(a.average_difference_pct_iqr??Infinity)-(b.average_difference_pct_iqr??Infinity))){
      const li=el(doc,"li"),title=el(doc,"div",undefined,"chart-label"),track=el(doc,"div",undefined,"chart-track"),bar=el(doc,"div",undefined,"chart-bar "+(n.status==="NEEDS_REVIEW"?"chart-review":""));
      title.append(el(doc,"strong",NUMERIC[n.key]),badge(doc,n.status));bar.style.width=Math.max(0,Math.min(100,100*(n.average_difference_pct_iqr||0)/scale))+"%";track.setAttribute("aria-hidden","true");track.append(bar);
      li.append(title,track,el(doc,"p",measure(n.average_difference_pct_iqr,"% of SOURCE IQR")+" average gap · worst percentile "+measure(n.max_difference_pct_iqr,"%"),"chart-value"));bars.append(li);
    }
    numeric.append(el(doc,"h3","Numeric fidelity · lower is closer"),bars,el(doc,"p","IQR is the SOURCE middle-50% range (P75 minus P25). Bars average four absolute percentile gaps relative to that range; status uses the worst gap. A zero or missing IQR prevents normalization, even when raw differences are available.","measurement-note"));
    const span=(a,b)=>typeof a==="number"&&typeof b==="number"?a-b:null;
    numeric.append(table(doc,"Upper-tail comparison",["Variable","SOURCE P95","Synthetic P95","P95 gap","SOURCE P95 − P50","Synthetic P95 − P50"],v.numeric.map(r=>{const p95=r.percentiles.find(p=>p.name==="P95"),p50=r.percentiles.find(p=>p.name==="P50");return [NUMERIC[r.key],fmt(p95.source),fmt(p95.generated),signed(p95.difference),fmt(span(p95.source,p50.source)),fmt(span(p95.generated,p50.generated))];})),el(doc,"p","Upper spread is P95 minus the median (P50), derived from published percentiles. Signed gaps are synthetic minus SOURCE. Additional P01/P05/P99, extrema and spread are shown when supplied below; otherwise evidence beyond P95 remains unavailable. Full histogram bins are not published. No density curve is estimated.","measurement-note"),details(doc,"All numeric percentiles and sortable comparisons",numericDetail(doc,v)));

    const categorical=section(doc,"categorical","Compare category proportions directly","The public selection covers the past-due indicator. Similarity here does not establish similarity for every categorical field.");
    categorical.append(VIZ.categorical(doc,v),table(doc,"Past-due indicator proportions",["Category","SOURCE","Synthetic","Absolute gap","Status"],v.categorical.map(r=>[r.category==="Y"?"Past due (Y)":"Not past due (N)",pct(r.source),pct(r.generated),measure(r.absolute_difference_pp,"pp"),badge(doc,r.status)])));

    const completeness=section(doc,"completeness","Missingness and dates are part of fidelity","Compare missing-value proportions and calendar-month distributions, alongside shifts in date boundaries.");
    completeness.append(nullDetail(doc,v),el(doc,"h3","Date-distribution gaps · lower is closer"));
    const dateBars=el(doc,"ol",undefined,"percentile-chart"),dateScale=Math.max(5,...v.dates.map(d=>d.total_variation_pct||0));dateBars.setAttribute("aria-label","Calendar-month distribution total variation, lower is closer");
    for(const d of v.dates){const li=el(doc,"li"),heading=el(doc,"div",undefined,"chart-label"),track=el(doc,"div",undefined,"chart-track"),bar=el(doc,"div",undefined,"chart-bar "+(d.status==="NEEDS_REVIEW"?"chart-review":""));heading.append(el(doc,"strong",d.label),badge(doc,d.status));bar.style.width=Math.max(0,Math.min(100,100*(d.total_variation_pct||0)/dateScale))+"%";track.setAttribute("aria-hidden","true");track.append(bar);li.append(heading,track,el(doc,"p",measure(d.total_variation_pct,"% total variation"),"chart-value"));dateBars.append(li);}
    completeness.append(dateBars,table(doc,"Calendar-month distributions",["Date characteristic","Monthly total variation","Earliest boundary shift","Latest boundary shift","Status"],v.dates.map(r=>[r.label,measure(r.total_variation_pct,"%"),measure(r.earliest_shift_days,"days"),measure(r.latest_shift_days,"days"),badge(doc,r.status)])),el(doc,"p","Total variation summarizes the difference between complete calendar-month proportion distributions, on a 0–100% scale. Boundary shifts are synthetic minus SOURCE in days. The artifact contains these aggregate distances, not the month-by-month bins; day-of-month and time-of-day fidelity remain unmeasured.","measurement-note"));

    const dependencies=section(doc,"dependencies","Check relationships as well as individual fields","Compare observed correlations and conditional past-due rates in the final cohort. Association does not establish causation.");
    const corr=byKey.get("correlation.balance_limit"),callout=el(doc,"div",undefined,"correlation-callout");callout.append(el(doc,"h3","Credit limit / balance correlation"),el(doc,"p",fmt(corr.source)+" SOURCE · "+fmt(corr.generated)+" synthetic","exec-number"),badge(doc,corr.status));
    dependencies.append(callout,table(doc,"Credit-limit / balance Pearson correlation",["Relationship","SOURCE","Synthetic","Absolute gap","SOURCE pairs","Synthetic pairs","Status"],[[corr.label,fmt(corr.source),fmt(corr.generated),fmt(corr.score),fmt(corr.source_n),fmt(corr.generated_n),badge(doc,corr.status)]]),el(doc,"p","Paired counts are unavailable when the saved correlation did not record them. No confidence interval or significance claim is inferred.","measurement-note"),VIZ.conditional(doc,v),table(doc,"Past-due rates by utilization bucket",["Utilization","SOURCE rate","Synthetic rate","Absolute gap","SOURCE n","Synthetic n","Status"],v.assessments.filter(a=>a.family==="conditional").map(a=>[a.label.replace("Past due · utilization ",""),pct(a.source),pct(a.generated),measure(a.difference===null?null:Math.abs(a.difference)*100,"pp"),fmt(a.source_n),fmt(a.generated_n),badge(doc,a.status)])),el(doc,"p","Conditional classifications require at least "+v.min_conditional_rows+" records per bucket in each population. Hollow points retain raw rates but lack sufficient comparison evidence. Missing SOURCE rates are not treated as zero.","measurement-note"));

    if(v.dependency_fidelity){
      const d=v.dependency_fidelity;
      dependencies.append(el(doc,"h3","Account-product dependencies"),
        table(doc,"Conditional account-product fidelity",["Relationship","SOURCE V","Synthetic V","Absolute V gap","Conditional total variation","Unsupported combinations","SOURCE n","Synthetic n","Status"],d.categorical.map(r=>{const a=v.post_pilot?.assessments.find(a=>a.key==="categorical_conditional."+r.key);return [r.label,fmt(r.source_cramers_v),fmt(r.generated_cramers_v),fmt(r.absolute_association_gap),measure(r.conditional_tvd_pct,"%"),pct(r.unsupported_combination_rate),fmt(r.source_n),fmt(r.generated_n),a?badge(doc,a.status):"Not classified"];})),
        details(doc,"Balance means within SOURCE credit-limit quartiles",table(doc,"Balance means by SOURCE credit-limit quartile",["SOURCE interval","SOURCE mean","Synthetic mean","Mean difference","SOURCE pairs","Synthetic pairs"],d.numeric_segments.map(r=>[r.bucket,fmt(r.source_mean),fmt(r.generated_mean),signed(r.mean_difference),fmt(r.source_n),fmt(r.generated_n)]))),
        el(doc,"p","Conditional total variation weights each parent group by its SOURCE share. Unsupported combinations had zero observed SOURCE support; this does not establish impossibility. Numeric differences require identical SOURCE interval boundaries. These supplemental observations are outside the headline check counts; categorical distances use the additional provisional screening policy when supplied.","measurement-note"));
    }
    const structure=section(doc,"structure","Preserve the population’s links and record counts","Compare relationship-count distributions and directionality. Structural constraints are evaluated separately from statistical resemblance.");
    structure.append(VIZ.cardinality(doc,v),table(doc,"Relationship cardinality fidelity",["Relationship","SOURCE mean","Synthetic mean","Full-distribution total variation","Status"],v.cardinality.map(r=>[r.label,fmt(r.source_mean),fmt(r.generated_mean),measure(r.total_variation_pct,"%"),badge(doc,r.status)])),el(doc,"p","Accounts per customer profiles parties represented in the customer–account link table, including only that profiled population. It does not establish how many of all customers have zero accounts.","measurement-note"),el(doc,"p","Accounts per person (all account rows ÷ all PERSON rows): SOURCE "+fmt(v.accounts_per_person.source)+"; synthetic "+fmt(v.accounts_per_person.generated)+". This population ratio can differ even when the linked-customer cardinality distribution is close.","measurement-note"));
    structure.append(table(doc,"Customer-relationship directionality",["Pattern","SOURCE","Synthetic","Absolute gap","Status"],v.assessments.filter(a=>a.family==="graph").map(a=>[a.label,pct(a.source),pct(a.generated),measure(a.score,"pp"),badge(doc,a.status)])));
    structure.append(table(doc,"Generated structural and business-rule checks",["Check","SOURCE rate","Synthetic rate","SOURCE matched / violations","Synthetic matched / violations","Eligible synthetic rows","Status"],v.assessments.filter(a=>a.family==="integrity").map(a=>[a.label,pct(a.source),pct(a.generated),fmt(a.source_count),fmt(a.generated_count),fmt(a.generated_n),badge(doc,a.status,true)])),el(doc,"p","Account/balance joins require 100% coverage in both directions. Other measured generated violation rates must be zero. Passed describes the generated constraint, not equality with SOURCE or comprehensive referential coverage. Unrecorded cross-table comparisons remain unavailable.","measurement-note"),details(doc,"Population sizes and comparison context",table(doc,"Population sizes",["Population","SOURCE rows","Synthetic rows","Difference"],v.populations.map(r=>[TABLES[r.table],fmt(r.source),fmt(r.generated),signed(r.difference)])),el(doc,"p","Different requested population sizes are expected. Raw row-count differences are context, not a statistical fidelity failure.","measurement-note")));

    const methodology=section(doc,"methodology","Understand the tolerances — and the limits","These are transparent prototype screening thresholds, not calibrated business acceptance criteria or a statistical guarantee. No single overall accuracy percentage is calculated.");
    const names={numeric_iqr_pct:"Worst percentile gap / SOURCE IQR",proportion_pp:"Category, null or dyad gap",conditional_pp:"Conditional outcome gap",correlation:"Absolute Pearson gap",distribution_tvd_pct:"Month / cardinality total variation"};
    methodology.append(table(doc,"Prototype tolerance policy "+v.policy_version,["Metric","Strong match at or below","Acceptable at or below","Needs review"],Object.entries(v.thresholds).map(([key,t])=>[names[key],fmt(t.strong)+" "+UNITS[key],fmt(t.acceptable)+" "+UNITS[key],"Above "+fmt(t.acceptable)+" "+UNITS[key]])),el(doc,"p","Numeric normalized gap = 100 × absolute percentile difference ÷ SOURCE IQR; status uses the maximum across P25/P50/P75/P95. Distribution total variation = 50 × the sum of absolute proportion differences. Category, null and conditional gaps use percentage points (pp). These percentages measure departures, not accuracy.","measurement-note"),el(doc,"p","Strengths and discrepancies are ranked by departure divided by the applicable acceptable threshold, with at most two findings per metric family. Strengths use strong statistical comparisons; structural passes are shown separately. This prioritization does not combine metrics into a score.","measurement-note"));
    if(v.post_pilot){
      const labels={mean_relative_pct:"Absolute mean gap / SOURCE mean",zero_mean_absolute:"Zero SOURCE mean: native-unit departure",tail_iqr_pct:"Worst P01 / P05 / P99 gap / SOURCE IQR",conditional_tvd_pct:"Categorical conditional total variation",date_bound_days:"Largest date boundary shift"};
      methodology.append(table(doc,"Additional provisional screens · "+v.post_pilot.policy_version,["Metric","Strong at or below","Acceptable at or below","Review above"],Object.entries(v.post_pilot.thresholds).map(([k,t])=>[labels[k],measure(t.strong,UNITS[k]),measure(t.acceptable,UNITS[k]),measure(t.acceptable,UNITS[k])])),
        el(doc,"p","Mandatory integrity requirements remain 100% snapshot coverage and zero configured key/reference/business/temporal violations. Statistical tolerances cannot waive those requirements. Mean relative gap = 100 × absolute mean difference ÷ absolute SOURCE mean. Zero-reference native-unit departures are displayed separately, not ranked against percentages through an invented denominator. Thresholds are centrally configurable and provisional until calibrated to stakeholder use cases.","measurement-note"));
    }
    const limits=el(doc,"ul",undefined,"quality-limitations");
    methodology.append(el(doc,'p','Missingness policy null_rates_v1: exact zero-null counts in both populations are TRIVIAL and excluded from strengths, including historical reports. Nonzero rates are graded with the existing 1 pp strong / 3 pp acceptable thresholds. Any zero/nonzero transition needs review regardless of gap size; this qualitative screen is not a claim of statistical significance. Core and all-table counts have separate denominators, with no combined fidelity percentage.','measurement-note'));
    for(const text of ["The development SOURCE baseline is fabricated. Matching it does not establish representativeness of production banking populations.","The public report covers four numeric variables, one categorical variable, three date variables and selected relationships; the separate null audit covers the reviewed fields across all six tables. It does not assess every joint distribution.","Sparse conditional buckets, zero SOURCE IQR, absent profiles and missing paired counts limit interpretation. Unavailable evidence is not proof of similarity or a measured discrepancy.","Percentile profiles summarize selected points. Selected tail percentiles and extrema do not establish full tail-density or joint-distribution fidelity. Detailed temporal patterns and some reference comparisons remain unmeasured.","Prototype tolerances are descriptive screening settings. Sampling uncertainty is not quantified, and statistical similarity does not establish privacy or external-release suitability."])limits.append(el(doc,"li",text));
    methodology.append(limits,details(doc,"Unavailable evidence and reasons",table(doc,"Evidence availability notes",["Characteristic","Context"],v.assessments.filter(a=>a.reason).map(a=>[a.label,REASONS[a.reason]||"Evidence unavailable."]))));
    if(v.post_pilot)completeness.append(table(doc,"Date-boundary screening",["Characteristic","Largest absolute boundary shift","Status"],v.post_pilot.assessments.filter(a=>a.family==="date_bounds").map(a=>[a.label,measure(a.score,"days"),badge(doc,a.status)])));
    root.append(summary,findings,exploreValidation(doc,view),numeric,categorical,completeness,dependencies,structure,privacySection(doc,report),methodology);return root;
  }
  function mountValidation(root,{fetcher=globalThis.fetch,location=globalThis.location,timeoutMs=10000}={}){
    const doc=root.ownerDocument,status=el(doc,"p","Validation results pending","results-notice"),body=el(doc,"div"),button=el(doc,"button","Refresh validation report","button button-secondary");button.type="button";status.setAttribute("role","status");status.setAttribute("aria-live","polite");const toolbar=el(doc,"div",undefined,"report-toolbar");toolbar.append(status,button);root.replaceChildren(toolbar,body);let loading=false,firstLoad=true;
    const initialHash=location?.hash,initialFocus=doc.activeElement;
    async function refresh(){if(loading)return;loading=true;button.disabled=true;button.textContent="Loading report…";root.setAttribute("aria-busy","true");status.textContent="Loading validation report";const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),timeoutMs);
      try{const url=new URL(root.dataset.reportUrl||"latest-pipeline.json",doc.baseURI);if(!["http:","https:"].includes(url.protocol)||url.origin!==location.origin)throw new Error("Invalid report URL");const response=await fetcher(url.href,{cache:"no-store",credentials:"omit",redirect:"error",signal:controller.signal});if(!response.ok)throw new Error("Unavailable");const text=await response.text();if(text.length>1024*1024)throw new Error("Oversize");const view=normalizeValidation(JSON.parse(text));if(!view)throw new Error("Pending");body.replaceChildren(renderValidation(doc,view));status.textContent="Latest validated pipeline results loaded";
        // The requested section does not exist until the JSON has rendered.
        // Respect an initial deep link without taking focus back after user interaction or refresh.
        if(firstLoad&&initialHash===location?.hash&&doc.activeElement===initialFocus&&/^#(?:summary|findings|explore-validation|numeric|categorical|completeness|dependencies|structure|privacy|methodology)$/.test(initialHash||"")){
          const target=doc.getElementById?.(initialHash.slice(1));if(target){target.tabIndex=-1;target.focus({preventScroll:true});target.scrollIntoView({block:"start",behavior:"auto"});}
        }
      }catch(_){body.replaceChildren(el(doc,"p","The latest validation report is unavailable or incomplete. Use Refresh validation report to try again. Pipeline methodology and the verified demo explorer remain accessible from the navigation; no substitute statistics are shown.","measurement-note"));status.textContent="Validation results pending";}finally{clearTimeout(timer);firstLoad=false;loading=false;button.disabled=false;button.textContent="Refresh validation report";root.setAttribute("aria-busy","false");}}
    button.addEventListener("click",refresh);return {ready:refresh(),refresh};
  }
  const api={normalizeValidation,normalizePrivacy,renderValidation,mountValidation,executiveSummary,executiveFindings,exploreValidation,explorationRows,classifyNull,nullSummary,normalizeNullAudit,scopeCounts,findingCopy};
  if(typeof module!=="undefined"&&module.exports)module.exports=api;
  if(typeof window!=="undefined")window.SageValidation=api;
  if(typeof document!=="undefined"){const root=document.getElementById("validation-report");if(root)mountValidation(root);}
})();
