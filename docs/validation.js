/* Static, aggregate-only validation view. All dynamic text uses textContent. */
(() => {
  "use strict";
  const CONFIG = typeof module!=="undefined" && module.exports ? require("./validation-config.js") : window.ValidationConfig;
  const VIZ = typeof module!=="undefined" && module.exports ? require("./executive-viz.js") : window.SageViz;
  const LABELS = {
    STRONG: "Strong match", ACCEPTABLE: "Acceptable", NEEDS_REVIEW: "Needs review", UNAVAILABLE: "Pending",
    REVIEW_REQUIRED: "Differences need review", PARTIAL: "Some evidence pending", WITHIN_TOLERANCE: "Within configured tolerances", PENDING: "Validation results pending",
  };
  const NUMERIC = {credit_limit: "Credit limit", current_balance: "Current balance", available_credit: "Available credit", overlimit: "Overlimit amount"};
  const TABLES = {PERSON: "Customers (PERSON)", TKQ_ACCOUNT: "Accounts", TKQ_ACCOUNT_BALANCE: "Balances", TRADELINES: "Tradelines", CUSTOMER_ACCOUNT_REL: "Customer–account links", CUSTOMER_RELATIONSHIP: "Customer relationships"};
  const UNITS = {numeric_iqr_pct: "% of SOURCE IQR (worst percentile)", proportion_pp: "pp", conditional_pp: "pp", correlation: "correlation units", distribution_tvd_pct: "% total variation", integrity: "% generated rows"};
  const REASONS = {metric_unavailable: "Paired evidence missing or undefined.", zero_or_missing_source_iqr: "SOURCE IQR is zero or missing; normalized percentile difference is undefined.", insufficient_conditional_rows: "Fewer than the configured minimum rows in at least one population.", source_comparison_unavailable: "Generated check measured; SOURCE comparison unavailable.", not_in_saved_fidelity_report: "This check is not present in the saved fidelity report."};
  const nf = new Intl.NumberFormat("en", {maximumFractionDigits: 2});
  const fmt = value => typeof value === "number" && Number.isFinite(value) ? nf.format(value) : "Pending";
  const measure = (value,unit) => typeof value === "number" && Number.isFinite(value) ? fmt(value)+(unit.startsWith("%")?"":" ")+unit : "Pending";
  const pct = value => typeof value === "number" && Number.isFinite(value) ? nf.format(value*100)+"%" : "Pending";
  const state = value => LABELS[value] || "Pending";
  const signed = value => typeof value === "number" && Number.isFinite(value) ? (value > 0 ? "+" : "")+fmt(value) : "Pending";
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
    if(!Array.isArray(v.rule_outcomes)||v.rule_outcomes.length!==3||v.rule_outcomes.some(r=>!["available_to_buy","overlimit_amount","delinquency_by_utilization"].includes(r.implementation)))throw new Error("Invalid validation report");
    for(const [name,count] of [["strong","STRONG"],["acceptable","ACCEPTABLE"],["needs_review","NEEDS_REVIEW"],["unavailable","UNAVAILABLE"]])if(v.summary[name]!==v.assessments.filter(a=>a.status===count).length)throw new Error("Invalid validation report");
    for(const key of ["strengths","weaknesses"]){
      if(!Array.isArray(v[key]) || v[key].length>6 || new Set(v[key]).size!==v[key].length)throw new Error("Invalid validation report");
      if(v[key].some(k=>!v.assessments.some(a=>a.key===k && a.status===(key==="strengths"?"STRONG":"NEEDS_REVIEW"))))throw new Error("Invalid validation report");
    }
    // Ignore IDs and any arbitrary extra metadata; only the public report is hosted.
    return {report, v};
  }

  function renderTechnicalValidation(doc, view) {
    const {report,v}=view, content=el(doc,"div"), byKey=new Map(v.assessments.map(a=>[a.key,a]));
    const summary=section(doc,"summary","The comparison at a glance");
    summary.append(el(doc,"p",state(v.summary.comparison_status),"report-verdict"),el(doc,"p","Completed "+new Date(report.pipeline_completed_at).toLocaleString("en",{timeZone:"UTC"})+" UTC","measurement-note"));
    const metrics=el(doc,"dl",undefined,"results-metrics report-metrics");
    for(const [label,value] of [["Variables evaluated",v.summary.variables_evaluated],["Within tolerance",v.summary.variables_within_tolerance],["Variables needing review",v.summary.variables_requiring_review],["Variables incomplete",v.summary.variables_incomplete],["Rules actually applied",report.rules?.applied?.value],["Checks evaluated",v.summary.checks_evaluated]]){const item=el(doc,"div");item.append(el(doc,"dt",label),el(doc,"dd",fmt(value)));metrics.append(item);}
    summary.append(metrics,el(doc,"p","Counts cover selected public variables. A variable is within tolerance only when all of its selected distribution and null-rate checks are available and within tolerance. Evaluated means at least one check is available.","measurement-note"));
    const coverage=el(doc,"p",undefined,"boundary-note"); const cov=report.validation.account_balance_join_coverage;
    coverage.textContent="Account/balance coverage: "+pct(cov.accounts_with_balance.value)+" of accounts have balances; "+pct(cov.balances_with_account.value)+" of balances have accounts. Saved-output integrity validation passed.";summary.append(coverage);
    const warnings=el(doc,"ul",undefined,"results-notes");
    if(v.summary.needs_review)warnings.append(el(doc,"li",fmt(v.summary.needs_review)+" checks exceed the prototype display tolerance. Inspect the measured differences below."));
    if(v.summary.unavailable)warnings.append(el(doc,"li",fmt(v.summary.unavailable)+" checks are pending or undefined. Missing evidence is never counted as a strong match."));
    if(report.rules?.approved_unimplemented?.value)warnings.append(el(doc,"li",fmt(report.rules.approved_unimplemented.value)+" approved proposals lacked an implementation and were skipped."));
    if(report.rules?.skipped?.value)warnings.append(el(doc,"li",fmt(report.rules.skipped.value)+" proposals did not affect the dataset."));
    summary.append(warnings);

    const findings=section(doc,"findings","Where it matches — and where it differs","These selections are calculated from this run’s metrics. They are ranked using the documented tolerances, with at most two findings per metric family.");
    const columns=el(doc,"div",undefined,"findings-grid");
    for(const [key,title,empty] of [["strengths","Strongest measured areas","No selected check meets the strong-match threshold."],["weaknesses","Priority areas for improvement","No measured check exceeds the configured tolerance. Pending evidence still needs investigation."]]){
      const panel=el(doc,"div",undefined,"finding-panel");panel.append(el(doc,"h3",title));const list=el(doc,"ol",undefined,"finding-list");
      for(const id of v[key]){const a=byKey.get(id),li=el(doc,"li");li.append(el(doc,"strong",a.label),el(doc,"p",measure(a.score,UNITS[a.policy]||UNITS.integrity)),badge(doc,a.status));list.append(li);}
      panel.append(v[key].length?list:el(doc,"p",empty));columns.append(panel);
    }findings.append(columns);

    const numeric=section(doc,"numeric","Numeric distributions","Lower bars mean smaller average percentile differences. The chart compares P25, P50, P75 and P95 using the SOURCE interquartile range (IQR = P75 − P25). The status uses the worst of those four differences, so an average cannot hide a large deviation.");
    const ordered=[...v.numeric].sort((a,b)=>(a.average_difference_pct_iqr??Infinity)-(b.average_difference_pct_iqr??Infinity)||a.key.localeCompare(b.key));
    const scale=Math.max(15,...ordered.map(r=>r.average_difference_pct_iqr||0));
    const chart=el(doc,"ol",undefined,"percentile-chart");chart.setAttribute("aria-label","Average absolute percentile difference as a percentage of SOURCE IQR; lower is better");
    for(const row of ordered){const li=el(doc,"li"), label=el(doc,"div",undefined,"chart-label");label.append(el(doc,"strong",NUMERIC[row.key]),badge(doc,row.status));const track=el(doc,"div",undefined,"chart-track");track.setAttribute("aria-hidden","true");const bar=el(doc,"div",undefined,"chart-bar "+(row.status==="NEEDS_REVIEW"?"chart-review":""));bar.style.width=Math.max(0,Math.min(100,100*(row.average_difference_pct_iqr||0)/scale))+"%";track.append(bar);li.append(label,track,el(doc,"p",measure(row.average_difference_pct_iqr,"% of SOURCE IQR")+" · worst percentile: "+measure(row.max_difference_pct_iqr,"%"),"chart-value"));chart.append(li);}numeric.append(chart);
    const sortLabel=el(doc,"label","Sort numeric table ","report-sort"),sort=el(doc,"select");sort.setAttribute("aria-label","Sort numeric table");
    for(const [value,label] of [["worst","Largest difference first"],["best","Smallest difference first"],["name","Variable name"]]){const option=el(doc,"option",label);option.value=value;sort.append(option);}sortLabel.append(sort);numeric.append(sortLabel);
    const numericTable=el(doc,"div");function drawNumeric(){const rows=[...v.numeric].sort((a,b)=>sort.value==="name"?NUMERIC[a.key].localeCompare(NUMERIC[b.key]):sort.value==="best"?(a.average_difference_pct_iqr??Infinity)-(b.average_difference_pct_iqr??Infinity):(b.average_difference_pct_iqr??-Infinity)-(a.average_difference_pct_iqr??-Infinity));numericTable.replaceChildren(table(doc,"Numeric percentile comparison",["Variable","SOURCE P25","Synthetic P25","SOURCE P50","Synthetic P50","SOURCE P75","Synthetic P75","SOURCE P95","Synthetic P95","Mean |difference| / IQR","Worst / IQR","Status"],rows.map(row=>{const values=[NUMERIC[row.key]];for(const name of ["P25","P50","P75","P95"]){const p=row.percentiles.find(p=>p.name===name);values.push(fmt(p.source),fmt(p.generated));}return [...values,measure(row.average_difference_pct_iqr,"%"),measure(row.max_difference_pct_iqr,"%"),badge(doc,row.status)];})));}sort.value="worst";sort.addEventListener("change",drawNumeric);drawNumeric();numeric.append(numericTable,el(doc,"p","A zero or missing SOURCE IQR makes the normalized score undefined. The raw percentiles remain visible. Tables scroll horizontally on narrow screens.","measurement-note"));content.append(numeric);

    const categorical=section(doc,"categorical","Categorical and missing-value fidelity","Selected past-due categories are shown below. Percentage-point differences compare proportions directly; a smaller difference is a closer marginal match.");
    categorical.append(table(doc,"Past-due indicator proportions",["Category","SOURCE","Synthetic","Absolute difference","Status"],v.categorical.map(r=>[r.category==="Y"?"Past due (Y)":"Not past due (N)",pct(r.source),pct(r.generated),measure(r.absolute_difference_pp,"pp"),badge(doc,r.status)])));
    const assessmentRows=rows=>rows.map(a=>[a.label,pct(a.source),pct(a.generated),measure(a.score,UNITS[a.policy]||UNITS.integrity),badge(doc,a.status)]);
    categorical.append(details(doc,"Selected null-rate comparisons",table(doc,"Null rates",["Variable","SOURCE null rate","Synthetic null rate","Absolute difference","Status"],assessmentRows(v.assessments.filter(a=>a.family==="nulls")))));
    categorical.append(details(doc,"Date-distribution comparisons",table(doc,"Calendar-month distributions",["Variable","Total variation","Earliest shift","Latest shift","Status"],v.dates.map(r=>[r.label,measure(r.total_variation_pct,"%"),signed(r.earliest_shift_days)+" days",signed(r.latest_shift_days)+" days",badge(doc,r.status)])),el(doc,"p","Date similarity compares calendar-month proportions. Boundary shifts are synthetic minus SOURCE, in days. No individual dates are published.","measurement-note")));content.append(categorical);

    const dependencies=section(doc,"dependencies","Were relationships preserved?","Matching individual distributions does not establish that dependencies were preserved. Inspect the paired correlation, conditional outcome rates and relationship-count distributions independently of the rule-execution audit.");
    const corr=byKey.get("correlation.balance_limit");dependencies.append(table(doc,"Credit-limit / balance Pearson correlation",["Relationship","SOURCE correlation","Synthetic correlation","Absolute difference","Status"],[[corr.label,fmt(corr.source),fmt(corr.generated),fmt(corr.score),badge(doc,corr.status)]]));
    dependencies.append(table(doc,"Past-due rates by utilization bucket",["Utilization bucket","SOURCE rate","Synthetic rate","Difference","SOURCE n","Synthetic n","Status"],v.assessments.filter(a=>a.family==="conditional").map(a=>[a.label.replace("Past due · utilization ",""),pct(a.source),pct(a.generated),measure(a.difference===null?null:Math.abs(a.difference)*100,"pp"),fmt(a.source_n),fmt(a.generated_n),badge(doc,a.status)])),el(doc,"p","Conditional comparisons require at least "+v.min_conditional_rows+" rows in each bucket on both sides. Smaller buckets retain their raw rates, differences and counts but cannot be classified as a match.","measurement-note"));
    dependencies.append(table(doc,"Relationship cardinality fidelity",["Relationship","SOURCE mean","Synthetic mean","Distribution total variation","Status"],v.cardinality.map(r=>[r.label,fmt(r.source_mean),fmt(r.generated_mean),measure(r.total_variation_pct,"%"),badge(doc,r.status)])));
    for(const r of v.cardinality)dependencies.append(details(doc,r.label+" · distribution detail",table(doc,r.label+" proportions",["Relationships","SOURCE","Synthetic","Absolute difference"],r.bins.map(b=>[b.bucket,pct(b.source),pct(b.generated),measure(b.absolute_difference_pp,"pp")])),el(doc,"p","Bins 5 and above are combined for display. Total variation uses the full original distribution, so tail differences remain included.","measurement-note")));
    dependencies.append(details(doc,"CUSTOMER_RELATIONSHIP directionality",table(doc,"Customer-relationship dyad proportions",["Pattern","SOURCE","Synthetic","Absolute difference","Status"],assessmentRows(v.assessments.filter(a=>a.family==="graph")))));
    const ruleLabels={available_to_buy:"Available-credit formula",overlimit_amount:"Overlimit formula",delinquency_by_utilization:"Utilization-conditioned delinquency"};
    dependencies.append(table(doc,"Predefined AI-rule implementation outcomes",["Implementation","Proposed","Approved","Applied","Skipped"],v.rule_outcomes.map(r=>[ruleLabels[r.implementation]||"Known implementation",fmt(r.proposed),fmt(r.approved),fmt(r.applied),fmt(r.skipped)])),el(doc,"p","Applied means the implementation affected generation. It is not evidence that the measured dependency matched. Unsupported proposals remain in the aggregate skipped count in the summary.","measurement-note"));content.append(dependencies);

    const structure=section(doc,"structure","Population and structural validation","Different SOURCE and synthetic population sizes are expected when the requested generation size differs. Counts are shown as context rather than classified as a fidelity failure.");
    structure.append(table(doc,"Population sizes",["Population","SOURCE rows","Synthetic rows","Difference"],v.populations.map(r=>[TABLES[r.table]||"Population",fmt(r.source),fmt(r.generated),signed(r.difference)])),el(doc,"p","Accounts per person (total account rows ÷ PERSON rows): SOURCE "+fmt(v.accounts_per_person.source)+"; synthetic "+fmt(v.accounts_per_person.generated)+". This population ratio differs from the profiled per-customer relationship distribution.","measurement-note"));
    structure.append(table(doc,"Generated structural and business-rule checks",["Check","SOURCE rate","Synthetic rate","SOURCE matched / violations","Synthetic matched / violations","Eligible synthetic rows","Status"],v.assessments.filter(a=>a.family==="integrity").map(a=>[a.label,pct(a.source),pct(a.generated),fmt(a.source_count),fmt(a.generated_count),fmt(a.generated_n),badge(doc,a.status,true)])),el(doc,"p","Both join-coverage directions require 100%. Measured generated violation rates must be zero. Other cross-table referential-integrity comparisons are pending because they are not recorded in the saved fidelity report.","measurement-note"));content.append(structure);

    const interpretation=section(doc,"interpretation","Thresholds and coverage","These centralized prototype tolerances support screening and prioritization. They are not calibrated business acceptance criteria, a statistical significance test, an overall score or privacy clearance.");
    const names={numeric_iqr_pct:"Worst percentile difference / SOURCE IQR",proportion_pp:"Category, null or dyad difference",conditional_pp:"Conditional outcome difference",correlation:"Absolute Pearson difference",distribution_tvd_pct:"Calendar-month / cardinality total variation"};
    interpretation.append(table(doc,"Prototype tolerance policy "+v.policy_version,["Metric","Strong match at or below","Acceptable at or below","Needs review"],Object.entries(v.thresholds).map(([key,t])=>[names[key],fmt(t.strong)+" "+UNITS[key],fmt(t.acceptable)+" "+UNITS[key],"Above "+fmt(t.acceptable)+" "+UNITS[key]])),el(doc,"p","Numeric chart = 100 × mean absolute P25/P50/P75/P95 difference ÷ SOURCE IQR. Status uses the maximum percentile difference. Total variation = 50 × sum of absolute proportion differences, on a 0–100% scale. Signed raw differences are synthetic minus SOURCE.","measurement-note"));
    const pending=v.assessments.filter(a=>a.reason);interpretation.append(details(doc,"Pending evidence and comparison limitations",table(doc,"Evidence availability notes",["Check","Context"],pending.map(a=>[a.label,REASONS[a.reason]||"Evidence pending."])),el(doc,"p","This public report selects four numeric variables, one categorical variable, three date variables and configured relationships. It does not evaluate every field or category. It excludes record-level data, identifiers and internal execution IDs. No day-of-month or time-of-day distribution test is included.","measurement-note")));content.append(interpretation);
    return content;
  }

  function executiveSummary(doc,view) {
    const {report,v}=view,s=VIZ.summary(report,v),root=el(doc,"div");
    const metrics=el(doc,"dl",undefined,"exec-metrics");
    const coverage=s.coverage, both=[coverage.accounts_with_balance.value,coverage.balances_with_account.value];
    for(const [value,label] of [[s.within===null?"Pending":fmt(s.within)+"%","Selected variables within tolerance"],[fmt(v.summary.variables_evaluated),"Variables evaluated"],[both.every(n=>typeof n==="number")?pct(Math.min(...both)):"Pending","Account / balance join coverage"],[s.relationshipCompared?s.relationshipMatched+" / "+s.relationshipCompared:"Pending","Relationship checks within tolerance"],[fmt(s.applied),"Reviewed rules actually applied"]]){const item=el(doc,"div");item.append(el(doc,"dt",label),el(doc,"dd",value));metrics.append(item);}
    root.append(metrics,el(doc,"p",v.summary.variables_within_tolerance+" of "+v.summary.variables_total+" selected variables within tolerance · "+v.summary.variables_requiring_review+" need review · "+v.summary.variables_incomplete+" incomplete. The percentage includes incomplete variables in its denominator; it is not an overall quality score.","measurement-note"),el(doc,"p",s.relationshipPending+" relationship checks have insufficient or missing evidence. Join coverage reports the lower of the two directions; integrity is assessed separately from statistical similarity.","measurement-note"));return root;
  }
  function executiveFindings(doc,view) {
    const {v}=view,root=el(doc,"div",undefined,"findings-grid"),byKey=new Map(v.assessments.map(a=>[a.key,a]));
    for(const [key,title] of [["strengths","Strongest measured areas"],["weaknesses","Largest measured deviations"]]){const panel=el(doc,"div",undefined,"finding-panel");panel.append(el(doc,"h3",title));const makeList=ids=>{const list=el(doc,"ol",undefined,"finding-list");for(const id of ids){const a=byKey.get(id),li=el(doc,"li");li.append(el(doc,"strong",a.label),el(doc,"p",measure(a.score,UNITS[a.policy]||UNITS.integrity)),badge(doc,a.status));list.append(li);}return list;};panel.append(v[key].length?makeList(v[key].slice(0,3)):el(doc,"p","No qualifying measured findings yet."));if(v[key].length>3)panel.append(details(doc,"More measured findings",makeList(v[key].slice(3))));root.append(panel);}return root;
  }
  function renderValidation(doc,view) {
    const {report,v}=view,root=el(doc,"div");
    const summary=section(doc,"summary","The structure holds. Statistical gaps remain visible.");
    summary.append(el(doc,"p",state(v.summary.comparison_status),"report-verdict"),el(doc,"p","Completed "+new Date(report.pipeline_completed_at).toLocaleString("en",{timeZone:"UTC"})+" UTC","measurement-note"),executiveSummary(doc,view),el(doc,"p","Saved-output integrity checks passed. Prototype tolerances support investigation; they do not establish business acceptance or privacy clearance.","boundary-note"));
    if(report.rules?.approved_unimplemented?.value)summary.append(el(doc,"p",fmt(report.rules.approved_unimplemented.value)+" approved proposals had no implementation and were skipped.","results-notice"));
    if(report.rules?.skipped?.value)summary.append(el(doc,"p",fmt(report.rules.skipped.value)+" proposals did not affect this dataset.","measurement-note"));
    const findings=section(doc,"findings","Where the evidence is strongest — and weakest","Ranked from this run’s measured results using the published prototype tolerances. Missing evidence is never counted as a strong match.");findings.append(executiveFindings(doc,view));
    const numeric=section(doc,"numeric","Compare the shape, then inspect the gap","Four measured percentiles reveal location and tail differences. Change the variable to inspect another distribution.");numeric.append(VIZ.distribution(doc,v));
    const bars=el(doc,"ol",undefined,"percentile-chart"),scale=Math.max(15,...v.numeric.map(n=>n.average_difference_pct_iqr||0));
    bars.setAttribute("aria-label","Fidelity by variable: average percentile difference, lower is closer");
    for(const n of [...v.numeric].sort((a,b)=>(a.average_difference_pct_iqr??Infinity)-(b.average_difference_pct_iqr??Infinity))){const li=el(doc,"li"),title=el(doc,"div",undefined,"chart-label"),track=el(doc,"div",undefined,"chart-track"),bar=el(doc,"div",undefined,"chart-bar "+(n.status==="NEEDS_REVIEW"?"chart-review":""));title.append(el(doc,"strong",NUMERIC[n.key]),badge(doc,n.status));bar.style.width=Math.max(0,Math.min(100,100*(n.average_difference_pct_iqr||0)/scale))+"%";track.setAttribute("aria-hidden","true");track.append(bar);li.append(title,track,el(doc,"p",measure(n.average_difference_pct_iqr,"% of original interquartile range")+" average gap · worst percentile "+measure(n.max_difference_pct_iqr,"%"),"chart-value"));bars.append(li);}
    numeric.append(el(doc,"h3","Fidelity by variable · lower is closer"),bars,el(doc,"p","Bars show the average difference across four percentiles, relative to the original middle-50% range. Classifications use the worst percentile. A zero original range makes this normalized score unavailable, even when raw differences exist.","measurement-note"));
    const categorical=section(doc,"categorical","Does the category mix carry through?","Compare the measured past-due proportions directly.");categorical.append(VIZ.categorical(doc,v));
    const dependencies=section(doc,"dependencies","Similar marginals can conceal weaker relationships","Past-due rates are compared within utilization groups, alongside the balance / credit-limit relationship.");dependencies.append(VIZ.conditional(doc,v),el(doc,"p","Hollow markers indicate a comparison with fewer than "+v.min_conditional_rows+" records on either side, or missing evidence. Raw rates remain visible; missing original rates are not treated as zero.","measurement-note"));const corr=v.assessments.find(a=>a.key==="correlation.balance_limit");dependencies.append(el(doc,"div",undefined,"correlation-callout"));const callout=dependencies.children[dependencies.children.length-1];callout.append(el(doc,"h3","Balance / credit-limit correlation"),el(doc,"p",fmt(corr.source)+" original → "+fmt(corr.generated)+" synthetic","exec-number"),badge(doc,corr.status),el(doc,"p","Absolute gap: "+fmt(corr.score)+". Correlation describes association, not causation.","measurement-note"));
    const evidence=section(doc,"structure","The complete evidence stays one click away","Inspect counts, rule outcomes, raw comparisons, missing evidence and the screening policy.");
    const technical=renderTechnicalValidation(doc,view);for(const child of technical.children)if(child.id)child.id="detail-"+child.id;
    evidence.append(details(doc,"Open detailed comparisons and methodology",technical));
    root.append(summary,findings,numeric,categorical,dependencies,evidence);return root;
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
