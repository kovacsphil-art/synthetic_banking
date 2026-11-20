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
    if(v.policy_version!=="prototype_v1" || !Array.isArray(v.assessments) || v.assessments.length>100 ||
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
    return {report, v};
  }

  function executiveSummary(doc,view) {
    const {v}=view, root=el(doc,"div"),metrics=el(doc,"dl",undefined,"exec-metrics quality-metrics");
    for(const [value,label] of [[v.summary.variables_evaluated,"Variables evaluated"],[v.summary.checks_evaluated,"Checks with measured evidence"],[v.summary.needs_review,"Checks needing review"],[v.summary.unavailable,"Checks not comparable"]]){
      const item=el(doc,"div");item.append(el(doc,"dt",label),el(doc,"dd",fmt(value)));metrics.append(item);
    }
    root.append(metrics,el(doc,"p",v.summary.variables_within_tolerance+" of "+v.summary.variables_total+" selected variables have all selected checks within tolerance; "+v.summary.variables_requiring_review+" need review and "+v.summary.variables_incomplete+" have incomplete evidence. These counts are not an overall accuracy score.","measurement-note"),el(doc,"p","Comparison is against the repository’s fake development SOURCE baseline. Representativeness of real production banking data has not been established.","baseline-notice"));
    return root;
  }

  function executiveFindings(doc,view) {
    const {v}=view,root=el(doc,"div",undefined,"findings-grid"),byKey=new Map(v.assessments.map(a=>[a.key,a]));
    for(const [key,title] of [["strengths","Strongest measured areas"],["weaknesses","Largest measured deviations"]]){
      const panel=el(doc,"div",undefined,"finding-panel");panel.append(el(doc,"h3",title));
      const makeList=ids=>{const list=el(doc,"ol",undefined,"finding-list");for(const id of ids){const a=byKey.get(id),li=el(doc,"li");li.append(el(doc,"strong",a.label),el(doc,"p",measure(a.score,UNITS[a.policy]||UNITS.integrity)),badge(doc,a.status));list.append(li);}return list;};
      panel.append(v[key].length?makeList(v[key].slice(0,3)):el(doc,"p","No qualifying measured findings yet."));
      if(v[key].length>3)panel.append(details(doc,"More measured findings",makeList(v[key].slice(3))));root.append(panel);
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

  function renderValidation(doc,view) {
    const {report,v}=view,root=el(doc,"div"),byKey=new Map(v.assessments.map(a=>[a.key,a]));
    const summary=section(doc,"summary","Assess the final cohort, dimension by dimension.");
    summary.append(el(doc,"p",state(v.summary.comparison_status),"report-verdict"),el(doc,"p","Completed "+new Date(report.pipeline_completed_at).toLocaleString("en",{timeZone:"UTC"})+" UTC","measurement-note"),executiveSummary(doc,view),dimensionTable(doc,v),el(doc,"p","A structural pass confirms the measured generated constraint. It is separate from a statistical match to SOURCE. Missing evidence is never counted as a strong match.","measurement-note"));
    const findings=section(doc,"findings","Preserved characteristics and material discrepancies","Ranked automatically from measured departures relative to each metric’s documented prototype tolerance. This ranking prioritizes review; it is not a significance test.");findings.append(executiveFindings(doc,view));

    const numeric=section(doc,"numeric","Inspect the distribution — including the upper tail","Compare four measured percentiles. A close median can coexist with a materially different upper tail.");numeric.append(VIZ.distribution(doc,v));
    const bars=el(doc,"ol",undefined,"percentile-chart"),scale=Math.max(15,...v.numeric.map(n=>n.average_difference_pct_iqr||0));bars.setAttribute("aria-label","Fidelity by variable: average percentile difference, lower is closer");
    for(const n of [...v.numeric].sort((a,b)=>(a.average_difference_pct_iqr??Infinity)-(b.average_difference_pct_iqr??Infinity))){
      const li=el(doc,"li"),title=el(doc,"div",undefined,"chart-label"),track=el(doc,"div",undefined,"chart-track"),bar=el(doc,"div",undefined,"chart-bar "+(n.status==="NEEDS_REVIEW"?"chart-review":""));
      title.append(el(doc,"strong",NUMERIC[n.key]),badge(doc,n.status));bar.style.width=Math.max(0,Math.min(100,100*(n.average_difference_pct_iqr||0)/scale))+"%";track.setAttribute("aria-hidden","true");track.append(bar);
      li.append(title,track,el(doc,"p",measure(n.average_difference_pct_iqr,"% of SOURCE IQR")+" average gap · worst percentile "+measure(n.max_difference_pct_iqr,"%"),"chart-value"));bars.append(li);
    }
    numeric.append(el(doc,"h3","Numeric fidelity · lower is closer"),bars,el(doc,"p","IQR is the SOURCE middle-50% range (P75 minus P25). Bars average four absolute percentile gaps relative to that range; status uses the worst gap. A zero or missing IQR prevents normalization, even when raw differences are available.","measurement-note"));
    const span=(a,b)=>typeof a==="number"&&typeof b==="number"?a-b:null;
    numeric.append(table(doc,"Upper-tail comparison",["Variable","SOURCE P95","Synthetic P95","P95 gap","SOURCE P95 − P50","Synthetic P95 − P50"],v.numeric.map(r=>{const p95=r.percentiles.find(p=>p.name==="P95"),p50=r.percentiles.find(p=>p.name==="P50");return [NUMERIC[r.key],fmt(p95.source),fmt(p95.generated),signed(p95.difference),fmt(span(p95.source,p50.source)),fmt(span(p95.generated,p50.generated))];})),el(doc,"p","Upper spread is P95 minus the median (P50), derived from published percentiles. Signed gaps are synthetic minus SOURCE. P01, P05, P99, extrema and full histogram bins are not published in this artifact; behaviour beyond P95 is not assessed here. No density curve is estimated.","measurement-note"),details(doc,"All numeric percentiles and sortable comparisons",numericDetail(doc,v)));

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
      dependencies.append(details(doc,"Additional measured account dependencies",
        table(doc,"Conditional account-product fidelity",["Relationship","SOURCE V","Synthetic V","Absolute V gap","Conditional total variation","Unsupported combinations","SOURCE n","Synthetic n"],d.categorical.map(r=>[r.label,fmt(r.source_cramers_v),fmt(r.generated_cramers_v),fmt(r.absolute_association_gap),measure(r.conditional_tvd_pct,"%"),pct(r.unsupported_combination_rate),fmt(r.source_n),fmt(r.generated_n)])),
        table(doc,"Balance means by SOURCE credit-limit quartile",["SOURCE interval","SOURCE mean","Synthetic mean","Mean difference","SOURCE pairs","Synthetic pairs"],d.numeric_segments.map(r=>[r.bucket,fmt(r.source_mean),fmt(r.generated_mean),signed(r.mean_difference),fmt(r.source_n),fmt(r.generated_n)])),
        el(doc,"p","Conditional total variation weights each parent group by its SOURCE share. Unsupported combinations had zero observed SOURCE support; this does not establish impossibility. Numeric differences require identical SOURCE interval boundaries. These supplemental observations are outside the headline check counts and have no separate acceptance classification.","measurement-note")));
    }
    const structure=section(doc,"structure","Preserve the population’s links and record counts","Compare relationship-count distributions and directionality. Structural constraints are evaluated separately from statistical resemblance.");
    structure.append(VIZ.cardinality(doc,v),table(doc,"Relationship cardinality fidelity",["Relationship","SOURCE mean","Synthetic mean","Full-distribution total variation","Status"],v.cardinality.map(r=>[r.label,fmt(r.source_mean),fmt(r.generated_mean),measure(r.total_variation_pct,"%"),badge(doc,r.status)])),el(doc,"p","Accounts per customer profiles parties represented in the customer–account link table, including only that profiled population. It does not establish how many of all customers have zero accounts.","measurement-note"),el(doc,"p","Accounts per person (all account rows ÷ all PERSON rows): SOURCE "+fmt(v.accounts_per_person.source)+"; synthetic "+fmt(v.accounts_per_person.generated)+". This population ratio can differ even when the linked-customer cardinality distribution is close.","measurement-note"));
    structure.append(table(doc,"Customer-relationship directionality",["Pattern","SOURCE","Synthetic","Absolute gap","Status"],v.assessments.filter(a=>a.family==="graph").map(a=>[a.label,pct(a.source),pct(a.generated),measure(a.score,"pp"),badge(doc,a.status)])));
    structure.append(table(doc,"Generated structural and business-rule checks",["Check","SOURCE rate","Synthetic rate","SOURCE matched / violations","Synthetic matched / violations","Eligible synthetic rows","Status"],v.assessments.filter(a=>a.family==="integrity").map(a=>[a.label,pct(a.source),pct(a.generated),fmt(a.source_count),fmt(a.generated_count),fmt(a.generated_n),badge(doc,a.status,true)])),el(doc,"p","Account/balance joins require 100% coverage in both directions. Other measured generated violation rates must be zero. Passed describes the generated constraint, not equality with SOURCE or comprehensive referential coverage. Unrecorded cross-table comparisons remain unavailable.","measurement-note"),details(doc,"Population sizes and comparison context",table(doc,"Population sizes",["Population","SOURCE rows","Synthetic rows","Difference"],v.populations.map(r=>[TABLES[r.table],fmt(r.source),fmt(r.generated),signed(r.difference)])),el(doc,"p","Different requested population sizes are expected. Raw row-count differences are context, not a statistical fidelity failure.","measurement-note")));

    const methodology=section(doc,"methodology","Understand the tolerances — and the limits","These are transparent prototype screening thresholds, not calibrated business acceptance criteria or a statistical guarantee. No single overall accuracy percentage is calculated.");
    const names={numeric_iqr_pct:"Worst percentile gap / SOURCE IQR",proportion_pp:"Category, null or dyad gap",conditional_pp:"Conditional outcome gap",correlation:"Absolute Pearson gap",distribution_tvd_pct:"Month / cardinality total variation"};
    methodology.append(table(doc,"Prototype tolerance policy "+v.policy_version,["Metric","Strong match at or below","Acceptable at or below","Needs review"],Object.entries(v.thresholds).map(([key,t])=>[names[key],fmt(t.strong)+" "+UNITS[key],fmt(t.acceptable)+" "+UNITS[key],"Above "+fmt(t.acceptable)+" "+UNITS[key]])),el(doc,"p","Numeric normalized gap = 100 × absolute percentile difference ÷ SOURCE IQR; status uses the maximum across P25/P50/P75/P95. Distribution total variation = 50 × the sum of absolute proportion differences. Category, null and conditional gaps use percentage points (pp). These percentages measure departures, not accuracy.","measurement-note"),el(doc,"p","Strengths and discrepancies are ranked by departure divided by the applicable acceptable threshold, with at most two findings per metric family. Strengths use strong statistical comparisons; structural passes are shown separately. This prioritization does not combine metrics into a score.","measurement-note"));
    const limits=el(doc,"ul",undefined,"quality-limitations");
    for(const text of ["The development SOURCE baseline is fabricated. Matching it does not establish representativeness of production banking populations.","The public report covers four numeric variables, one categorical variable, three date variables and selected relationships; it does not assess every field or joint distribution.","Sparse conditional buckets, zero SOURCE IQR, absent profiles and missing paired counts limit interpretation. Unavailable evidence is not proof of similarity or a measured discrepancy.","Percentile profiles summarize selected points. Extreme tails beyond P95, full density shape, detailed temporal patterns and some cross-table reference comparisons are unavailable here.","Prototype tolerances are descriptive screening settings. Sampling uncertainty is not quantified, and statistical similarity does not establish privacy or external-release suitability."])limits.append(el(doc,"li",text));
    methodology.append(limits,details(doc,"Unavailable evidence and reasons",table(doc,"Evidence availability notes",["Characteristic","Context"],v.assessments.filter(a=>a.reason).map(a=>[a.label,REASONS[a.reason]||"Evidence unavailable."]))));
    root.append(summary,findings,numeric,categorical,completeness,dependencies,structure,methodology);return root;
  }
  function mountValidation(root,{fetcher=globalThis.fetch,location=globalThis.location,timeoutMs=10000}={}){
    const doc=root.ownerDocument,status=el(doc,"p","Validation results pending","results-notice"),body=el(doc,"div"),button=el(doc,"button","Refresh validation report","button button-secondary");button.type="button";status.setAttribute("role","status");status.setAttribute("aria-live","polite");const toolbar=el(doc,"div",undefined,"report-toolbar");toolbar.append(status,button);root.replaceChildren(toolbar,body);let loading=false;
    async function refresh(){if(loading)return;loading=true;button.disabled=true;root.setAttribute("aria-busy","true");status.textContent="Loading validation report";const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),timeoutMs);
      try{const url=new URL(root.dataset.reportUrl||"latest-pipeline.json",doc.baseURI);if(!["http:","https:"].includes(url.protocol)||url.origin!==location.origin)throw new Error("Invalid report URL");const response=await fetcher(url.href,{cache:"no-store",credentials:"omit",redirect:"error",signal:controller.signal});if(!response.ok)throw new Error("Unavailable");const text=await response.text();if(text.length>1024*1024)throw new Error("Oversize");const view=normalizeValidation(JSON.parse(text));if(!view)throw new Error("Pending");body.replaceChildren(renderValidation(doc,view));status.textContent="Latest validated pipeline results loaded";
      }catch(_){body.replaceChildren(el(doc,"p","A complete version-2 validation report has not been published here or could not be read. The project methodology and existing summary remain available.","measurement-note"));status.textContent="Validation results pending";}finally{clearTimeout(timer);loading=false;button.disabled=false;root.setAttribute("aria-busy","false");}}
    button.addEventListener("click",refresh);return {ready:refresh(),refresh};
  }
  const api={normalizeValidation,renderValidation,mountValidation,executiveSummary,executiveFindings};
  if(typeof module!=="undefined"&&module.exports)module.exports=api;
  if(typeof window!=="undefined")window.SageValidation=api;
  if(typeof document!=="undefined"){const root=document.getElementById("validation-report");if(root)mountValidation(root);}
})();
