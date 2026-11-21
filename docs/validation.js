/* Static, aggregate-only validation view. All dynamic text uses textContent. */
(() => {
  "use strict";
  const CONFIG = typeof module!=="undefined" && module.exports ? require("./validation-config.js") : window.ValidationConfig;
  const VIZ = typeof module!=="undefined" && module.exports ? require("./executive-viz.js") : window.SageViz;
  const LABELS = {
    STRONG: "Strong match", ACCEPTABLE: "Acceptable", NEEDS_REVIEW: "Needs review", UNAVAILABLE: "Not comparable",
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

  function normalizeValidation(report) {
    if (!report || report.schema_version !== "2.0" || report.validation?.status !== "PASS") return null;
    if(typeof report.pipeline_completed_at!=="string" || !Number.isFinite(Date.parse(report.pipeline_completed_at)))throw new Error("Invalid validation report");
    const v=report.validation_report;
    if(!v || v.status!=="AVAILABLE") return null;
    const statuses=["STRONG","ACCEPTABLE","NEEDS_REVIEW","UNAVAILABLE"];
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
      const expectedStatus=a.score===null?"UNAVAILABLE":!limits?(a.score===0?"STRONG":"NEEDS_REVIEW"):a.score<=limits.strong+1e-9?"STRONG":a.score<=limits.acceptable+1e-9?"ACCEPTABLE":"NEEDS_REVIEW";
      if(a.status!==expectedStatus)throw new Error("Invalid validation report");
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
    if(v.summary.variables_total!==8 || v.summary.variables_evaluated>v.summary.variables_total || v.summary.variables_within_tolerance+v.summary.variables_requiring_review+v.summary.variables_incomplete!==v.summary.variables_total || v.summary.checks_evaluated!==v.summary.strong+v.summary.acceptable+v.summary.needs_review)throw new Error("Invalid validation report");
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
      const all=[...v.assessments,...p.assessments];
      for(const [k,status] of [["strengths","STRONG"],["weaknesses","NEEDS_REVIEW"],["zero_reference_alerts","NEEDS_REVIEW"]])if(!Array.isArray(p[k])||p[k].length>6||new Set(p[k]).size!==p[k].length||p[k].some(key=>!all.some(a=>a.key===key&&a.status===status&&(k!=="zero_reference_alerts"||a.policy==="zero_mean_absolute"))))throw new Error("Invalid screening findings");
    }
    normalizePrivacy(report.privacy);
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

  function executiveSummary(doc,view) {
    const {v}=view, root=el(doc,"div"),metrics=el(doc,"dl",undefined,"exec-metrics quality-metrics");
    for(const [value,label] of [[v.summary.variables_evaluated,"Variables evaluated"],[v.summary.checks_evaluated,"Checks with measured evidence"],[v.summary.needs_review,"Checks needing review"],[v.summary.unavailable,"Checks not comparable"]]){
      const item=el(doc,"div");item.append(el(doc,"dt",(v.post_pilot?"Core · ":"")+label),el(doc,"dd",fmt(value)));metrics.append(item);
    }
    root.append(metrics,el(doc,"p",v.summary.variables_within_tolerance+" of "+v.summary.variables_total+" selected variables have all "+(v.post_pilot?"core":"selected")+" checks within tolerance; "+v.summary.variables_requiring_review+" need review and "+v.summary.variables_incomplete+" have incomplete evidence. These counts are not an overall accuracy score.","measurement-note"),el(doc,"p","Comparison is against the repository’s fake development SOURCE baseline. Representativeness of real production banking data has not been established.","baseline-notice"));
    if(v.post_pilot){
      root.append(el(doc,"p",v.post_pilot.assessments.length+" additional mean, tail, boundary and categorical-dependency screens are shown separately: "+v.post_pilot.assessments.filter(a=>a.status==="NEEDS_REVIEW").length+" need review; "+v.post_pilot.assessments.filter(a=>a.status==="UNAVAILABLE").length+" are not comparable. They are excluded from the core counts above.","measurement-note"));
      const mean=v.post_pilot.assessments.find(a=>a.key==="mean.current_balance");
      if(mean?.status==="NEEDS_REVIEW")root.append(el(doc,"p","Balance mean needs review: SOURCE "+fmt(mean.source)+"; synthetic "+fmt(mean.generated)+" ("+measure(mean.score,UNITS[mean.policy])+"). Close percentiles do not establish a close mean.","baseline-notice"));
    }
    root.append(el(doc,"p","Privacy: "+(view.report.privacy?.status||"UNAVAILABLE")+" · Row-level downloads disabled.","release-notice"));
    return root;
  }

  function executiveFindings(doc,view) {
    const {v}=view,root=el(doc,"div",undefined,"findings-grid"),byKey=new Map([...v.assessments,...(v.post_pilot?.assessments||[])].map(a=>[a.key,a]));
    for(const [key,title] of [["strengths","Strongest measured areas"],["weaknesses","Largest measured deviations"]]){
      const panel=el(doc,"div",undefined,"finding-panel");panel.append(el(doc,"h3",title));
      const makeList=ids=>{const list=el(doc,"ol",undefined,"finding-list");for(const id of ids){const a=byKey.get(id),li=el(doc,"li");li.append(el(doc,"strong",a.label),el(doc,"p",measure(a.score,UNITS[a.policy]||UNITS.integrity)),badge(doc,a.status));list.append(li);}return list;};
      const selected=v.post_pilot?.[key]||v[key];
      panel.append(selected.length?makeList(selected.slice(0,3)):el(doc,"p","No qualifying measured findings yet."));
      if(selected.length>3)panel.append(details(doc,"More measured findings",makeList(selected.slice(3))));root.append(panel);
    }
    return root;
  }

  function dimensionTable(doc,v) {
    const families=[["numeric","Numeric distributions"],["categorical","Categorical proportions"],["nulls","Missingness"],["dates","Date distributions"],["correlation","Correlations"],["conditional","Conditional outcomes"],["cardinality","Relationship cardinalities"],["graph","Relationship directionality"],["integrity","Structural / business checks"]];
    return table(doc,"Evidence by dimension",["Dimension","Strong / passed","Acceptable","Needs review","Not comparable"],families.map(([key,label])=>{
      const rows=v.assessments.filter(a=>a.family===key);return [label,...["STRONG","ACCEPTABLE","NEEDS_REVIEW","UNAVAILABLE"].map(status=>fmt(rows.filter(a=>a.status===status).length))];
    }));
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
      table(doc,"P01 / P05 / P99 tail screening",["Variable","SOURCE P01","Synthetic P01","SOURCE P05","Synthetic P05","SOURCE P99","Synthetic P99","Worst gap / IQR","Status"],p.numeric_details.map(r=>{const a=byKey.get("tail."+r.key),values=[r.label];for(const name of ["P01","P05","P99"]){const t=r.tail_points.find(t=>t.name===name);values.push(fmt(t.source),fmt(t.generated));}return [...values,measure(a.score,"%"),badge(doc,a.status)];})),
      details(doc,"Extrema and spread",table(doc,"Extrema and standard deviation",["Variable","SOURCE min","Synthetic min","SOURCE max","Synthetic max","SOURCE std. dev.","Synthetic std. dev."],p.numeric_details.map(r=>[r.label,fmt(r.source_minimum),fmt(r.generated_minimum),fmt(r.source_maximum),fmt(r.generated_maximum),fmt(r.source_stddev),fmt(r.generated_stddev)]))));
    return root;
  }

  function privacySection(doc,report){
    const p=report.privacy,root=section(doc,"privacy","Privacy review and publication boundary","Privacy screens assess a separate risk question from statistical fidelity. Row-level dataset downloads are disabled.");
    if(!p){root.append(el(doc,"p","Privacy assessment unavailable. This report does not establish release clearance.","release-notice"));return root;}
    root.append(el(doc,"p",p.status,"report-verdict"),el(doc,"p","Row-level downloads disabled · No formal anonymization certification","release-notice"),
      table(doc,"Aggregate privacy screening",["Check","Measured result"],[["Recorded checks",fmt(p.checks_recorded)+" / "+fmt(p.checks_expected)],["Identifier overlap rows",fmt(p.identifier_overlap_rows)],["Exact SOURCE-row matches",fmt(p.exact_source_row_matches)],["Selected quasi-identifier near matches",fmt(p.near_matches.flagged_rows)+" / "+fmt(p.near_matches.evaluated_rows)+" ("+pct(p.near_matches.flagged_fraction)+")"],["Minimum combined date distance among matches",measure(p.near_matches.minimum_combined_distance_days,"days")]]));
    if(p.policy){const c=p.policy;root.append(el(doc,"p","The similarity screen requires the same gender and birth/customer-since dates each within "+c.near_date_days+" days, with SOURCE pattern support below "+c.rare_min_count+" for a review flag. It is a bounded candidate comparison, not a global nearest-neighbour or re-identification test.","measurement-note"),
      table(doc,"Categorical-pattern privacy checks",["Pattern","Evaluated synthetic rows","Synthetic-rare rows","SOURCE-rare pattern matches","Complete-case coverage","Status"],p.categorical_patterns.map(r=>[r.label,fmt(r.evaluated_rows),fmt(r.synthetic_rare_rows),fmt(r.source_rare_match_rows),pct(r.complete_case_coverage),r.status])),
      el(doc,"p","Synthetic rarity and SOURCE rarity differ: a pattern can be common in a larger generated cohort yet have low SOURCE support. Any SOURCE-rare match requires review; synthetic-rare fraction above "+pct(c.max_synthetic_rare_fraction)+" or coverage below "+pct(c.min_complete_fraction)+" also requires review. Identifier overlap or exact SOURCE-row matches block release; missing checks or a candidate budget above "+fmt(c.max_similarity_candidates)+" are not passing evidence.","measurement-note"));}
    root.append(el(doc,"p","The SOURCE baseline is fabricated development data. Near matches can arise by chance when both populations share distributions; they do not demonstrate copying or certify safety. Production use needs a contextual disclosure review. Keep release blocked while reviewing quasi-identifiers, date granularity, rare categories and the need for each published field.","measurement-note"));
    return root;
  }

  function renderValidation(doc,view) {
    const {report,v}=view,root=el(doc,"div"),byKey=new Map(v.assessments.map(a=>[a.key,a]));
    const summary=section(doc,"summary","Assess the final cohort, dimension by dimension.");
    summary.append(el(doc,"p",state(v.summary.comparison_status),"report-verdict"),el(doc,"p","Completed "+new Date(report.pipeline_completed_at).toLocaleString("en",{timeZone:"UTC"})+" UTC","measurement-note"),executiveSummary(doc,view),dimensionTable(doc,v),el(doc,"p","A structural pass confirms the measured generated constraint. It is separate from a statistical match to SOURCE. Missing evidence is never counted as a strong match.","measurement-note"));
    const findings=section(doc,"findings","Preserved characteristics and material discrepancies","Ranked automatically from measured departures relative to each metric’s documented prototype tolerance. This ranking prioritizes review; it is not a significance test.");findings.append(executiveFindings(doc,view));

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
    completeness.append(table(doc,"Null rates",["Characteristic","SOURCE null rate","Synthetic null rate","Absolute gap","Status"],v.assessments.filter(a=>a.family==="nulls").map(a=>[a.label,pct(a.source),pct(a.generated),measure(a.score,"pp"),badge(doc,a.status)])),el(doc,"h3","Date-distribution gaps · lower is closer"));
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
    for(const text of ["The development SOURCE baseline is fabricated. Matching it does not establish representativeness of production banking populations.","The public report covers four numeric variables, one categorical variable, three date variables and selected relationships; it does not assess every field or joint distribution.","Sparse conditional buckets, zero SOURCE IQR, absent profiles and missing paired counts limit interpretation. Unavailable evidence is not proof of similarity or a measured discrepancy.","Percentile profiles summarize selected points. Selected tail percentiles and extrema do not establish full tail-density or joint-distribution fidelity. Detailed temporal patterns and some reference comparisons remain unmeasured.","Prototype tolerances are descriptive screening settings. Sampling uncertainty is not quantified, and statistical similarity does not establish privacy or external-release suitability."])limits.append(el(doc,"li",text));
    methodology.append(limits,details(doc,"Unavailable evidence and reasons",table(doc,"Evidence availability notes",["Characteristic","Context"],v.assessments.filter(a=>a.reason).map(a=>[a.label,REASONS[a.reason]||"Evidence unavailable."]))));
    if(v.post_pilot)completeness.append(table(doc,"Date-boundary screening",["Characteristic","Largest absolute boundary shift","Status"],v.post_pilot.assessments.filter(a=>a.family==="date_bounds").map(a=>[a.label,measure(a.score,"days"),badge(doc,a.status)])));
    root.append(summary,findings,numeric,categorical,completeness,dependencies,structure,privacySection(doc,report),methodology);return root;
  }
  function mountValidation(root,{fetcher=globalThis.fetch,location=globalThis.location,timeoutMs=10000}={}){
    const doc=root.ownerDocument,status=el(doc,"p","Validation results pending","results-notice"),body=el(doc,"div"),button=el(doc,"button","Refresh validation report","button button-secondary");button.type="button";status.setAttribute("role","status");status.setAttribute("aria-live","polite");const toolbar=el(doc,"div",undefined,"report-toolbar");toolbar.append(status,button);root.replaceChildren(toolbar,body);let loading=false;
    async function refresh(){if(loading)return;loading=true;button.disabled=true;root.setAttribute("aria-busy","true");status.textContent="Loading validation report";const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),timeoutMs);
      try{const url=new URL(root.dataset.reportUrl||"latest-pipeline.json",doc.baseURI);if(!["http:","https:"].includes(url.protocol)||url.origin!==location.origin)throw new Error("Invalid report URL");const response=await fetcher(url.href,{cache:"no-store",credentials:"omit",redirect:"error",signal:controller.signal});if(!response.ok)throw new Error("Unavailable");const text=await response.text();if(text.length>1024*1024)throw new Error("Oversize");const view=normalizeValidation(JSON.parse(text));if(!view)throw new Error("Pending");body.replaceChildren(renderValidation(doc,view));status.textContent="Latest validated pipeline results loaded";
      }catch(_){body.replaceChildren(el(doc,"p","A complete version-2 validation report has not been published here or could not be read. The project methodology and existing summary remain available.","measurement-note"));status.textContent="Validation results pending";}finally{clearTimeout(timer);loading=false;button.disabled=false;root.setAttribute("aria-busy","false");}}
    button.addEventListener("click",refresh);return {ready:refresh(),refresh};
  }
  const api={normalizeValidation,normalizePrivacy,renderValidation,mountValidation,executiveSummary,executiveFindings};
  if(typeof module!=="undefined"&&module.exports)module.exports=api;
  if(typeof window!=="undefined")window.SageValidation=api;
  if(typeof document!=="undefined"){const root=document.getElementById("validation-report");if(root)mountValidation(root);}
})();
