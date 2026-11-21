"use strict";
const test=require("node:test"),assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path");
const {normalizeValidation,renderValidation,mountValidation,classifyNull,nullSummary,normalizeNullAudit,executiveSummary,scopeCounts,findingCopy,findingEvidence,headlineFindings,metricGuide,TERMS}=require("../docs/validation.js");
const nullConfig=require('../docs/validation-config.js').null_rates;
const fixture=JSON.parse(fs.readFileSync(path.join(__dirname,"../docs/reporting/example.json"),"utf8"));

function nullAudit(overrides={}){
  const rows=nullConfig.fields.map(([table,column])=>{
    const key='null_field.'+table+'.'+column;
    const counts=overrides[key]||{source_count:null,source_n:null,generated_count:null,generated_n:null};
    return {key,table,column,label:table+'.'+column+' · null rate',family:'nulls',policy:'proportion_pp',...classifyNull(counts)};
  });
  return {policy_version:nullConfig.policy_version,thresholds:{strong:1,acceptable:3},zero_presence_requires_review:true,summary:nullSummary(rows),rows};
}
class Node {
  constructor(doc,tag,text=""){this.ownerDocument=doc;this.tagName=tag.toUpperCase();this.children=[];this.attributes={};this.dataset={};this.events={};this.style={};this._text=text;this.value="";}
  set textContent(v){this._text=String(v);this.children=[];}
  get textContent(){return this._text+this.children.map(n=>n.textContent).join(" ");}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this._text="";this.children=nodes;}
  setAttribute(k,v){this.attributes[k]=v;}
  addEventListener(k,v){this.events[k]=v;}
  focus(options){this.ownerDocument.activeElement=this;this.focusOptions=options;}
  scrollIntoView(options){this.scrolled=options;}
}
function document(){const d={baseURI:"https://example.invalid/project/validation.html"};d.createElement=t=>new Node(d,t);d.createElementNS=(_,t)=>new Node(d,t);return d;}
function all(n){return [n,...n.children.flatMap(all)];}
const clone=()=>structuredClone(fixture);
const location={origin:"https://example.invalid",protocol:"https:"};
const response=r=>({ok:true,text:async()=>JSON.stringify(r)});
const postFixture=JSON.parse(fs.readFileSync(path.join(__dirname,"../docs/reporting/example-postpilot.json"),"utf8"));

test("post-pilot mean/tail screens and privacy findings remain separate and visible",()=>{
  const r=structuredClone(postFixture),node=renderValidation(document(),normalizeValidation(r));
  assert.match(node.textContent,/Numeric mean screening/);assert.match(node.textContent,/P01 \/ P05 \/ P99 tail screening/);
  assert.match(node.textContent,/Current balance has a higher average/);assert.match(node.textContent,/REVIEW_REQUIRED/);
  assert.match(node.textContent,/SOURCE-rare pattern matches/);assert.match(node.textContent,/General dataset release blocked/);
  assert.match(node.textContent,/DEMO_ONLY eligibility separately requires exact fabricated-origin verification/);
  assert.match(node.textContent,/Additional provisional screens/);assert.match(node.textContent,/Mandatory integrity requirements/);
  assert.equal(all(node).filter(n=>n.className?.includes("mean-series")).length,8);
  assert.ok(!all(node).some(n=>n.tagName==="A"&&/\.zip|\.csv|\.parquet/.test(n.attributes.href||"")));
  const unchanged=structuredClone(r);delete unchanged.rules;delete unchanged.validation_report.rule_outcomes;
  assert.equal(renderValidation(document(),normalizeValidation(unchanged)).textContent,node.textContent);
});

test('mean investigation distinguishes method diagnostics from live results and keeps calibration inactive',()=>{
  const report=structuredClone(postFixture),node=renderValidation(document(),normalizeValidation(report));
  const explanation=all(node).find(n=>n.tagName==='DETAILS'&&n.children[0].textContent==='Why the balance mean can worsen while percentiles improve');
  assert.ok(explanation);assert.match(explanation.textContent,/preserves their raw values and mean/);
  assert.match(explanation.textContent,/cap at 125%/);assert.match(explanation.textContent,/separate from the live measurements/);
  assert.match(explanation.textContent,/No calibration has been activated/);
  assert.doesNotMatch(explanation.textContent,/3,145|159\.09|27\.06|1,107|343|5\.45/);
  assert.deepEqual(report,postFixture);
});

test('privacy interpretation uses current aggregate flags without turning demo eligibility into clearance',()=>{
  const report=structuredClone(postFixture);report.privacy.near_matches.flagged_rows=7;
  report.privacy.near_matches.flagged_fraction=7/report.privacy.near_matches.evaluated_rows;
  const node=renderValidation(document(),normalizeValidation(report));
  const privacy=all(node).find(n=>n.id==='privacy');
  assert.match(privacy.textContent,/7 \/ 200 \(3\.5%\)/);
  assert.match(privacy.textContent,/not confirmed disclosures/);assert.match(privacy.textContent,/not an estimated probability/);
  assert.match(privacy.textContent,/exact fabricated-origin verification/);
  assert.match(privacy.textContent,/does not change the privacy assessment/);
  assert.match(privacy.textContent,/Do not relax thresholds/);
  assert.equal(report.privacy.row_level_downloads_enabled,false);assert.equal(report.privacy.status,'REVIEW_REQUIRED');
});

test("privacy never becomes clearance through missing evidence or altered labels",()=>{
  for(const mutate of [r=>r.privacy.row_level_downloads_enabled=true,r=>r.privacy.status="PASS",r=>r.privacy.near_matches.variables[0]="PRIVATE_PERSON",
    r=>r.privacy.near_matches.flagged_fraction=.99,r=>r.privacy.categorical_patterns[0].label="PRIVATE_PATTERN",r=>r.privacy.policy.near_date_days=-1,
    r=>r.validation_report.post_pilot.assessments[0].status="NEEDS_REVIEW",r=>r.validation_report.post_pilot.thresholds.mean_relative_pct.acceptable=999,
    r=>r.validation_report.post_pilot.numeric_details[0].tail_points[0].source="PRIVATE_VALUE"]){
    const r=structuredClone(postFixture);mutate(r);assert.throws(()=>normalizeValidation(r),/Invalid/);
  }
  const r=structuredClone(postFixture);r.private_source_rows=["PRIVATE_ROW"];r.privacy.private_id="PRIVATE_ID";
  assert.ok(!renderValidation(document(),normalizeValidation(r)).textContent.includes("PRIVATE_"));
});

function dependencyEvidence(){return {
  categorical:[{key:"account_type_product",label:"Account type / client product"},{key:"client_tsys_product",label:"Client / TSYS product"}].map(r=>({...r,source_cramers_v:1,generated_cramers_v:.99,absolute_association_gap:.01,source_n:1000,generated_n:10000,conditional_tvd_pct:.5,unsupported_combination_rate:0})),
  numeric_segments:["Q1","Q2","Q3","Q4"].map(bucket=>({bucket,source_mean:100,generated_mean:101,mean_difference:1,source_n:250,generated_n:2500}))
};}

test("optional sampling fidelity renders safely without changing headline classifications",()=>{
  const r=clone();r.validation_report.dependency_fidelity=dependencyEvidence();
  const node=renderValidation(document(),normalizeValidation(r));
  assert.match(node.textContent,/Conditional account-product fidelity/);
  assert.match(node.textContent,/Balance means by SOURCE credit-limit quartile/);
  assert.match(node.textContent,/outside the headline check counts/);
  for(const mutate of [d=>d.categorical[0].label="PRIVATE_LABEL",d=>d.categorical[0].conditional_tvd_pct=101,
    d=>d.categorical[0].unsupported_combination_rate=-1,d=>d.categorical[0].source_n=.5,
    d=>d.numeric_segments[1].bucket="Q1",d=>d.numeric_segments[0].generated_mean="PRIVATE"]){
    const r=clone(),d=dependencyEvidence();mutate(d);r.validation_report.dependency_fidelity=d;
    assert.throws(()=>normalizeValidation(r),/Invalid dependency evidence/);
  }
  r.validation_report.dependency_fidelity.numeric_segments[0].mean_difference=null;
  assert.ok(renderValidation(document(),normalizeValidation(r)).textContent.includes("Unavailable"));
});

test("measured classifications, raw percentiles, populations and dependencies are displayed",()=>{
  const view=normalizeValidation(clone()),node=renderValidation(document(),view),text=node.textContent;
  assert.match(text,/selected variables meet every core tolerance/);assert.match(text,/30% total variation/);
  assert.match(text,/SOURCE P25/);assert.match(text,/Strong match/);assert.match(text,/Needs review/);
  assert.match(text,/Credit limit \/ balance correlation/);assert.match(text,/Accounts per person/);
  assert.match(text,/Other cross-table referential integrity/);assert.match(text,/Unavailable/);
  assert.ok(!text.includes("high quality"));
  const conditional=all(node).find(n=>n.tagName==="TABLE"&&n.children[0].textContent==="Past-due rates by utilization bucket");
  assert.match(conditional.textContent,/Strong match/);assert.doesNotMatch(conditional.textContent,/Passed/);
  const integrity=all(node).find(n=>n.tagName==="TABLE"&&n.children[0].textContent==="Generated structural and business-rule checks");
  assert.match(integrity.textContent,/Passed/);
});

test("numeric table sorts independently without losing raw data",()=>{
  const node=renderValidation(document(),normalizeValidation(clone()));
  const select=all(node).find(n=>n.tagName==="SELECT"&&n.attributes["aria-label"]==="Sort numeric table");
  const numericTable=()=>all(node).find(n=>n.tagName==="TABLE"&&n.children[0].textContent==="Numeric percentile comparison");
  assert.ok(numericTable().textContent.indexOf("Available credit")<numericTable().textContent.indexOf("Credit limit"));
  select.value="best";select.events.change();
  assert.ok(numericTable().textContent.indexOf("Credit limit")<numericTable().textContent.indexOf("Available credit"));
  select.value="name";select.events.change();assert.match(numericTable().textContent,/SOURCE P95/);
});

test("unknown metadata is ignored; unapproved labels and inconsistent status fail safely",()=>{
  const r=clone();r.source_run_id="SECRET_RUN";r.rows=[{PARTY_ID:"SECRET_PARTY"}];
  assert.ok(!renderValidation(document(),normalizeValidation(r)).textContent.includes("SECRET"));
  for(const mutate of [r=>r.validation_report.assessments[0].label="SECRET_PARTY",r=>r.validation_report.assessments[0].status="NEEDS_REVIEW",
    r=>r.validation_report.thresholds.numeric_iqr_pct.acceptable=999,r=>r.validation_report.summary.strong=999,
    r=>r.validation_report.strengths.push("numeric.available_credit"),r=>r.validation_report.cardinality[0].bins[0].bucket="SECRET"]){
    const r=clone();mutate(r);assert.throws(()=>normalizeValidation(r),/Invalid/);
  }
});

test("legacy or unavailable evidence stays pending instead of inventing a report",async()=>{
  const old=clone();old.schema_version="1.0";assert.equal(normalizeValidation(old),null);
  const r=clone();r.validation_report.status="PENDING";assert.equal(normalizeValidation(r),null);
  const doc=document(),root=new Node(doc,"div");
  const loader=mountValidation(root,{fetcher:async()=>response(old),location});await loader.ready;
  assert.match(root.textContent,/Validation results pending/);assert.doesNotMatch(root.textContent,/What SAGE reproduced well/);
});

test("refresh failures clear previous figures and recover; fetch is public same-origin only",async()=>{
  const doc=document(),root=new Node(doc,"div");let calls=[],fail=false;
  const loader=mountValidation(root,{location,fetcher:async(url,options)=>{calls.push({url,options});if(fail)throw new Error("PRIVATE_PAYLOAD");return response(fixture);}});
  await loader.ready;assert.match(root.textContent,/Latest validated pipeline results loaded/);
  assert.equal(calls[0].url,"https://example.invalid/project/latest-pipeline.json");assert.equal(calls[0].options.credentials,"omit");
  fail=true;await loader.refresh();assert.match(root.textContent,/Validation results pending/);assert.ok(!root.textContent.includes("PRIVATE_PAYLOAD"));assert.doesNotMatch(root.textContent,/What SAGE reproduced well/);
  fail=false;await loader.refresh();assert.match(root.textContent,/What SAGE reproduced well/);
  root.dataset.reportUrl="https://elsewhere.invalid/private.json";await loader.refresh();assert.equal(calls.length,3);
});

test("a stalled request times out with the accessible pending state",async()=>{
  const root=new Node(document(),"div");const loader=mountValidation(root,{location,timeoutMs:5,fetcher:async(_,o)=>new Promise((_,reject)=>o.signal.addEventListener("abort",()=>reject(new Error("aborted"))))});
  await loader.ready;assert.match(root.textContent,/Validation results pending/);assert.equal(root.attributes["aria-busy"],"false");
});

test("a report deep link is restored after rendering, without stealing focus on refresh",async()=>{
  const doc=document(),root=new Node(doc,'div'),loc={...location,hash:'#dependencies'};
  doc.getElementById=id=>all(root).find(n=>n.id===id);
  const loader=mountValidation(root,{location:loc,fetcher:async()=>response(fixture)});await loader.ready;
  assert.equal(doc.activeElement.id,'dependencies');assert.equal(doc.activeElement.tabIndex,-1);
  assert.deepEqual(doc.activeElement.focusOptions,{preventScroll:true});
  assert.deepEqual(doc.activeElement.scrolled,{block:'start',behavior:'auto'});
  const refresh=new Node(doc,'button');doc.activeElement=refresh;await loader.refresh();assert.equal(doc.activeElement,refresh);
  assert.equal(doc.getElementById('dependencies').scrolled,undefined);
});

test("pending report loading respects user focus, changed fragments and unknown anchors",async()=>{
  for(const change of ['focus','hash','unknown']){
    const doc=document(),root=new Node(doc,'div'),loc={...location,hash:change==='unknown'?'#private-metadata':'#numeric'};
    doc.getElementById=id=>all(root).find(n=>n.id===id);
    let release;const loader=mountValidation(root,{location:loc,fetcher:()=>new Promise(resolve=>{release=resolve;})});
    const control=new Node(doc,'button');if(change==='focus')doc.activeElement=control;if(change==='hash')loc.hash='#privacy';
    release(response(fixture));await loader.ready;
    assert.ok(!all(root).some(n=>n.scrolled));assert.equal(doc.activeElement,change==='focus'?control:undefined);
  }
});

test("privacy explanation links to demo checks without enabling general row release",()=>{
  const report=structuredClone(postFixture),node=renderValidation(document(),normalizeValidation(report));
  const link=all(node).find(n=>n.tagName==='A'&&n.textContent==='Check verified fabricated demo availability');
  assert.equal(link.attributes.href,'index.html#download-dataset');
  assert.match(node.textContent,/General dataset release remains blocked/);assert.match(node.textContent,/REVIEW_REQUIRED/);
  assert.equal(report.privacy.row_level_downloads_enabled,false);
});

test("final-cohort report is independent of rule approvals and application metadata",()=>{
  const original=renderValidation(document(),normalizeValidation(clone())).textContent;
  const report=clone();delete report.rules;delete report.validation_report.rule_outcomes;
  const rendered=renderValidation(document(),normalizeValidation(report)).textContent;
  assert.equal(rendered,original);
  assert.doesNotMatch(rendered,/\bLLM\b|\bAI\b|approved|rule outcomes|rules actually applied|control group|attribution/i);
  assert.match(rendered,/fake development SOURCE baseline/);
  assert.match(rendered,/real production banking data/);
  const summary=all(renderValidation(document(),normalizeValidation(report))).find(n=>n.id==="summary");
  const headlines=all(summary).filter(n=>n.tagName==="DD").map(n=>n.textContent);
  assert.ok(headlines.length>0);assert.ok(headlines.every(text=>!text.includes("%")));
});

test("raw upper-tail gaps remain visible when a zero SOURCE IQR prevents grading",()=>{
  const report=clone(),r=report.validation_report.numeric.find(r=>r.key==="overlimit");
  r.percentiles.forEach(p=>{p.source=0;p.generated=p.name==="P95"?656.46:0;p.difference=p.generated;});
  const node=renderValidation(document(),normalizeValidation(report));
  const tail=all(node).find(n=>n.tagName==="TABLE"&&n.children[0].textContent==="Upper-tail comparison");
  assert.match(tail.textContent,/Overlimit amount 0 656.46 \+656.46 0 656.46/);
  assert.match(node.textContent,/beyond P95 remains unavailable/);
  assert.match(node.textContent,/zero or missing IQR prevents normalization/);
  assert.match(node.textContent,/Not comparable/);
});

test("missingness, dates, cardinalities and structural evidence are primary sections",()=>{
  const root=renderValidation(document(),normalizeValidation(clone()));
  for(const id of ["completeness","dependencies","structure","methodology"])
    assert.ok(root.children.some(n=>n.id===id));
  const captions=all(root).filter(n=>n.tagName==="CAPTION").map(n=>n.textContent);
  for(const caption of ["Null rates","Calendar-month distributions","Relationship cardinality fidelity","Customer-relationship directionality","Generated structural and business-rule checks","Prototype tolerance policy prototype_v1"])
    assert.ok(captions.some(c=>c===caption||(caption==='Null rates'&&c==='Null rates · exact counts across six tables')));
  assert.match(root.textContent,/It does not establish how many of all customers have zero accounts/);
  assert.match(root.textContent,/not equality with SOURCE/);
});

test('exact null counts distinguish every requested pattern and tiny nonzero rates',()=>{
  const cases=[
    [0,100,0,200,'TRIVIAL'],[0,100,1,200,'NEEDS_REVIEW'],[1,100,0,200,'NEEDS_REVIEW'],
    [10,100,20,200,'STRONG'],[10,100,24,200,'ACCEPTABLE'],[10,100,50,200,'NEEDS_REVIEW'],
    [null,100,0,200,'UNAVAILABLE'],[1,1000000,2,2000000,'STRONG'],[101,100,0,200,'UNAVAILABLE']
  ];
  for(const [sc,sn,gc,gn,status] of cases){const r=classifyNull({source_count:sc,source_n:sn,generated_count:gc,generated_n:gn,source:0,generated:0});assert.equal(r.status,status);if(sc===1&&sn===1000000)assert.equal(r.source,.000001);}
});

test('all-table null audit validates count-bound classifications and cannot invent strengths',()=>{
  const zero={source_count:0,source_n:100,generated_count:0,generated_n:200};
  const a=nullAudit({'null_field.PERSON.BIRTH_DT':zero});assert.equal(normalizeNullAudit(a).summary.trivial_zero_null,1);
  for(const mutate of [r=>r.rows.find(x=>x.column==='BIRTH_DT').status='STRONG',r=>r.summary.meaningful_matches=99,
    r=>r.rows[0].column='PRIVATE_FIELD',r=>r.rows.find(x=>x.column==='BIRTH_DT').source=.01]){
    const bad=structuredClone(a);mutate(bad);assert.throws(()=>normalizeNullAudit(bad));
  }
});

test('legacy reports remove exact zero-null strengths without changing unrelated metrics or input JSON',()=>{
  const r=clone(),v=r.validation_report;
  for(const a of v.assessments.filter(a=>a.family==='nulls'))Object.assign(a,{source:0,generated:0,difference:0,score:0,status:'STRONG',source_count:0,generated_count:0});
  const before=structuredClone(r),view=normalizeValidation(r);
  assert.deepEqual(r,before);assert.equal(view.v.summary.trivial_zero_null,8);
  assert.equal(view.v.summary.strong,v.summary.strong-8);assert.equal(view.v.summary.checks_evaluated,v.summary.checks_evaluated);
  assert.ok(view.v.strengths.every(k=>!k.startsWith('null.')));
  assert.deepEqual(view.v.assessments.filter(a=>a.family!=='nulls'),v.assessments.filter(a=>a.family!=='nulls'));
});

test('missingness details retain every observation and support reversible native filters',()=>{
  const view=normalizeValidation(clone()),a=nullAudit({
    'null_field.PERSON.BIRTH_DT':{source_count:0,source_n:100,generated_count:0,generated_n:200},
    'null_field.PERSON.SINCE_DT':{source_count:1,source_n:1000000,generated_count:2,generated_n:2000000},
    'null_field.TKQ_ACCOUNT.BRANCH_NUM':{source_count:0,source_n:100,generated_count:200,generated_n:200}
  });view.v.null_rate_audit=a;
  const root=renderValidation(document(),view),select=all(root).find(n=>n.attributes['aria-label']==='Null-rate table'),toggle=all(root).find(n=>n.attributes['aria-label']==='Hide trivial zero-null matches');
  const grid=()=>all(root).find(n=>n.tagName==='TABLE'&&n.children[0].textContent==='Null rates · exact counts across six tables');
  const count=()=>grid().children[2].children.length;
  assert.equal(toggle.checked,true);assert.equal(count(),nullConfig.fields.length-1);assert.match(grid().textContent,/0\.0001%/);assert.match(root.textContent,/entirely-null agreement/i);
  toggle.checked=false;toggle.events.change();assert.equal(count(),nullConfig.fields.length);
  toggle.checked=true;toggle.events.change();assert.equal(count(),nullConfig.fields.length-1);
  select.value='PERSON';select.events.change();assert.equal(count(),nullConfig.fields.filter(([t,c])=>t==='PERSON'&&c!=='BIRTH_DT').length);
  toggle.checked=false;toggle.events.change();assert.equal(count(),nullConfig.fields.filter(([t])=>t==='PERSON').length);
  select.value='all';select.events.change();assert.equal(count(),nullConfig.fields.length);
  const noMatches=normalizeValidation(clone());noMatches.v.null_rate_audit=nullAudit({'null_field.PERSON.BIRTH_DT':{source_count:0,source_n:100,generated_count:0,generated_n:200}});
  assert.match(renderValidation(document(),noMatches).textContent,/No independently supported missingness strengths/);
});

test('summary leads with variable outcomes and separates the three reporting scopes',()=>{
  const report=JSON.parse(fs.readFileSync(path.join(__dirname,'../docs/latest-pipeline.json'),'utf8'));
  const original=structuredClone(report),view=normalizeValidation(report),counts=scopeCounts(view.v),root=executiveSummary(document(),view);
  const scope=name=>all(root).find(n=>n.attributes['aria-label']===name),core=scope('Key variable validation');
  const outcomes=core.children.find(n=>n.className==='variable-outcomes');
  assert.deepEqual(all(outcomes).filter(n=>n.tagName==='DD').map(n=>n.textContent),[
    String(counts.core.variables_within_tolerance),String(counts.core.variables_requiring_review),String(counts.core.variables_incomplete)]);
  assert.equal(counts.core.variables_within_tolerance+counts.core.variables_requiring_review+counts.core.variables_incomplete,counts.core.variables_total);
  assert.ok(core.textContent.includes(counts.core.variables_total+' selected variables'));
  const coreDetails=core.children.find(n=>n.tagName==='DETAILS');assert.ok(coreDetails);assert.ok(!coreDetails.open);
  assert.match(coreDetails.textContent,/measured evidence/);assert.match(coreDetails.textContent,/neither a pass nor a measured failure/);
  assert.equal(counts.additional.within+counts.additional.review+counts.additional.unavailable,counts.additional.total);
  const additional=scope('Additional statistical checks');assert.ok(additional.textContent.includes(counts.additional.total+' additional checks'));
  assert.match(additional.textContent,/not additional variables/);
  const n=counts.missingness;assert.equal(n.meaningful_matches+n.requiring_review,n.eligible_nontrivial);
  assert.equal(n.eligible_nontrivial+n.trivial_zero_null+n.unavailable,n.variables_total);
  const missing=scope('Full-dataset missingness audit');assert.ok(missing.textContent.includes(n.meaningful_matches+' of '+n.eligible_nontrivial+' nontrivial comparisons'));
  assert.ok(missing.children.find(n=>n.tagName==='DETAILS').textContent.includes(n.trivial_zero_null+' zero-null observations'));
  const privacy=scope('Separate privacy assessment');assert.match(privacy.textContent,/REVIEW_REQUIRED/);assert.match(privacy.textContent,/Statistical similarity does not establish privacy clearance/);
  assert.ok(!all(outcomes).filter(n=>n.tagName==='DD').some(n=>n.textContent.includes('%')));assert.deepEqual(report,original);
});

test('summary numbers follow supplied JSON and unavailable scopes never imply success',()=>{
  const view=normalizeValidation(clone());
  Object.assign(view.v.summary,{variables_total:12,variables_within_tolerance:7,variables_requiring_review:2,variables_incomplete:3});
  const root=executiveSummary(document(),view);assert.match(root.textContent,/7 of 12 selected variables/);
  const outcomes=all(root).find(n=>n.className==='variable-outcomes');assert.deepEqual(all(outcomes).filter(n=>n.tagName==='DD').map(n=>n.textContent),['7','2','3']);
  delete view.v.post_pilot;delete view.v.null_rate_audit;
  const pending=executiveSummary(document(),view);assert.match(pending.textContent,/Additional statistical checks are unavailable/);assert.match(pending.textContent,/null-rate audit unavailable/);
  assert.doesNotMatch(pending.textContent,/0 of 0|100% accurate|overall accuracy percentage/);
  const compact=executiveSummary(document(),view,{compact:true});assert.ok(!all(compact).some(n=>n.attributes['aria-label']==='Additional statistical checks'));
});

test('business findings lead with interpretation then preserve measured values and context',()=>{
  const report=JSON.parse(fs.readFileSync(path.join(__dirname,'../docs/latest-pipeline.json'),'utf8')),view=normalizeValidation(report);
  const a={key:'null_field.PERSON.DOMICILE_TRANSIT_NUM',column:'DOMICILE_TRANSIT_NUM',family:'nulls',label:'Customer home-branch codes',policy:'proportion_pp',status:'NEEDS_REVIEW',source:0,generated:1,score:100};
  const copy=findingCopy(a,view.v);assert.equal(copy.title,'Customer home-branch codes are absent from the synthetic cohort');
  assert.equal(copy.source,'0% missing');assert.equal(copy.synthetic,'100% missing');assert.match(copy.why,/customer segmentation by home branch/);
  const available={key:'numeric.available_credit',label:'Available credit',family:'numeric',policy:'numeric_iqr_pct',status:'NEEDS_REVIEW',score:50,source:200,generated:200};
  const range=findingCopy(available,{numeric:[{key:'available_credit',percentiles:[{name:'P50',source:200,generated:200,difference:0},{name:'P95',source:400,generated:500,difference:100}]}]});
  assert.match(range.title,/gaps at key points/);assert.match(range.source,/high-end point \(P95\)/);assert.match(range.why,/available spending capacity/);
  const birth=findingCopy(view.v.assessments.find(a=>a.key==='date.birth'),view.v);
  assert.match(birth.title,/birth-date patterns/);assert.match(birth.source,/not published/);assert.match(birth.why,/time-based segments/);
  const rendered=renderValidation(document(),view),panel=all(rendered).find(n=>n.id==='findings');
  const first=all(panel).find(n=>n.tagName==='LI');assert.equal(first.children[0].tagName,'STRONG');
  assert.equal(first.children[1].className,'finding-explanation');assert.equal(first.children[2].className,'finding-scope');
  assert.equal(first.children[4].className,'finding-values');assert.equal(first.children[6].className,'finding-meaning');
  assert.equal(first.children[8].tagName,'DETAILS');assert.ok(!first.children[8].open);
});

test("sparse conditional evidence keeps rates and counts without a passing label",()=>{
  const report=clone(),v=report.validation_report,a=v.assessments.find(a=>a.key==="conditional.0");
  a.source_n=29;a.score=null;a.status="UNAVAILABLE";a.reason="insufficient_conditional_rows";
  v.strengths=v.strengths.filter(key=>key!==a.key);
  for(const [field,status] of [["strong","STRONG"],["acceptable","ACCEPTABLE"],["needs_review","NEEDS_REVIEW"],["unavailable","UNAVAILABLE"]])v.summary[field]=v.assessments.filter(a=>a.status===status).length;
  v.summary.checks_evaluated=v.summary.strong+v.summary.acceptable+v.summary.needs_review;
  const root=renderValidation(document(),normalizeValidation(report));
  const t=all(root).find(n=>n.tagName==="TABLE"&&n.children[0].textContent==="Past-due rates by utilization bucket");
  assert.match(t.textContent,/0-30% 10% 11% 1 pp 29 200 Not comparable/);
  assert.match(root.textContent,/at least 30 records per bucket/);
});

test('headline evidence separates trivial, constant, constructed, boundary and supported zero gaps',()=>{
  const v=normalizeValidation(structuredClone(postFixture)).v;
  const sample={key:'conditional.0',family:'conditional',status:'STRONG',score:0,source:.2,generated:.2,source_n:100,generated_n:200};
  assert.equal(findingEvidence(v,sample).eligible,true);
  assert.equal(findingEvidence(v,{...sample,source:0,generated:0}).kind,'limited');
  assert.equal(findingEvidence(v,{...sample,source:1,generated:1}).eligible,false);
  assert.equal(findingEvidence(v,{...sample,source_n:29}).kind,'insufficient');
  assert.equal(findingEvidence(v,{...sample,source_n:null}).eligible,false);
  assert.equal(findingEvidence(v,{...sample,status:'UNAVAILABLE',score:null}).eligible,false);
  assert.equal(findingEvidence(v,{...sample,key:'integrity.available_formula',family:'integrity'}).kind,'integrity');
  assert.equal(findingEvidence(v,{...sample,key:'date_bounds.account_open',family:'date_bounds'}).kind,'boundary');
  assert.equal(findingEvidence(v,{...sample,key:'graph.directed_dyads_proportion',family:'graph',source:1,generated:1}).kind,'constructed');
  const counts={source_count:0,source_n:100,generated_count:0,generated_n:200};
  const nullRow={...sample,key:'null_field.TRADELINES.payment_pattern',table:'TRADELINES',column:'payment_pattern',family:'nulls',...classifyNull(counts)};
  assert.equal(findingEvidence(v,nullRow).eligible,false);
  assert.equal(findingEvidence(v,{...nullRow,...classifyNull({...counts,source_count:100,generated_count:200})}).eligible,false);
  const mixed={...nullRow,...classifyNull({...counts,source_count:20,generated_count:40})};
  assert.equal(findingEvidence(v,mixed).eligible,true);
  assert.equal(findingEvidence(v,{...mixed,table:'PERSON',column:'BANKRUPTCY_DT'}).kind,'constructed');
  const numeric={...sample,key:'mean.overlimit',family:'mean',source:0,generated:0};
  v.post_pilot.numeric_details.find(r=>r.key==='overlimit').source_stddev=0;
  assert.equal(findingEvidence(v,numeric).kind,'limited');
});

test('nontrivial exact distribution matches qualify with variation and paired evidence; constants do not',()=>{
  const v=normalizeValidation(clone()).v,a={key:'cardinality.accounts_per_customer',family:'cardinality',status:'STRONG',score:0,source_n:100,generated_n:200};
  const r=v.cardinality.find(r=>r.key==='accounts_per_customer');
  r.bins.forEach((b,i)=>{b.source=i<2?.5:0;b.generated=b.source;});
  assert.equal(findingEvidence(v,a).eligible,true);
  assert.equal(findingEvidence(v,{...a,source_n:null}).eligible,false);
  r.bins.forEach((b,i)=>{b.source=i===0?1:0;});assert.equal(findingEvidence(v,a).kind,'limited');
  const c=v.assessments.find(r=>r.key==='categorical.past_due');
  Object.assign(v.assessments.find(r=>r.key==='null.past_due'),{source_count:0,source_n:100,generated_count:0,generated_n:200});
  v.categorical.forEach(r=>{r.source=.5;r.generated=.5;});c.score=0;
  assert.equal(findingEvidence(v,c).eligible,true);
  v.categorical.forEach((r,i)=>{r.source=i===0?1:0;r.generated=r.source;});assert.equal(findingEvidence(v,c).eligible,false);
  const d={...a,key:'categorical_conditional.account_type_product',family:'categorical_conditional'};
  assert.match(findingEvidence(v,d).reason,/per-group support/);
});

test('headline selections audit every excluded match without changing measurements, grades or counts',()=>{
  const report=JSON.parse(fs.readFileSync(path.join(__dirname,'../docs/latest-pipeline.json'),'utf8')),view=normalizeValidation(report),before=structuredClone(view),selection=headlineFindings(view.v);
  assert.ok(selection.strengths.length>0);assert.ok(selection.strengths.every(a=>findingEvidence(view.v,a).eligible));
  assert.ok(!selection.strengths.some(a=>['integrity','graph','date_bounds','categorical_conditional'].includes(a.family)));
  for(const key of view.v.post_pilot.strengths){assert.ok([...selection.strengths,...selection.audit].some(a=>a.key===key));}
  const allWeak=[...view.v.assessments,...view.v.post_pilot.assessments,...view.v.null_rate_audit.rows].filter(a=>a.status==='NEEDS_REVIEW'&&a.family!=='nulls'||a.status==='NEEDS_REVIEW'&&a.key.startsWith('null_field.'));
  for(const a of allWeak)assert.ok(selection.weaknesses.some(r=>r.key===a.key));
  assert.ok(selection.weaknesses.some(a=>a.key==='mean.overlimit')); // Native-unit alert remains visible without an invented rank divisor.
  const rendered=renderValidation(document(),view),findings=all(rendered).find(n=>n.id==='findings');
  for(const panel of all(findings).filter(n=>n.className==='finding-panel')){const list=panel.children.find(n=>n.tagName==='OL');assert.ok(list.children.length<=3);}
  assert.match(findings.textContent,/Why some matches are not headline strengths/);assert.match(findings.textContent,/Integrity check passed/);
  assert.deepEqual(view,before);assert.deepEqual(report,view.report);
});

test('large missingness gaps preserve direction, true values, all five omissions and code-path context',()=>{
  const v=normalizeValidation(clone()).v,base={key:'null_field.PERSON.DOMICILE_TRANSIT_NUM',table:'PERSON',column:'DOMICILE_TRANSIT_NUM',family:'nulls',label:'Customer transit',policy:'proportion_pp',status:'NEEDS_REVIEW',score:100};
  const missing=findingCopy({...base,source:0,generated:1},v);assert.equal(missing.source,'0% missing');assert.equal(missing.synthetic,'100% missing');assert.match(missing.comparison,/100 percentage points higher/);assert.match(missing.explanation,/No synthetic records contain/);
  const restored=findingCopy({...base,source:1,generated:0},v);assert.match(restored.comparison,/100 percentage points lower/);assert.match(restored.explanation,/SOURCE baseline/);assert.doesNotMatch(restored.title,/absent/);
  const r=JSON.parse(fs.readFileSync(path.join(__dirname,'../docs/latest-pipeline.json'),'utf8')),view=normalizeValidation(r),node=renderValidation(document(),view),findings=all(node).find(n=>n.id==='findings');
  for(const col of ['DOMICILE_TRANSIT_NUM','BRANCH_NUM','OFFICER_NBR','amount_past_due','subscriber_code'])assert.ok(headlineFindings(view.v).weaknesses.some(a=>a.column===col));
  assert.match(findings.textContent,/pads unsupported schema columns with nulls/);
  const rates=all(findings).filter(n=>n.className==='finding-values'&&n.attributes.role==='group');assert.ok(rates.length>0);
  assert.ok(rates.every(n=>n.attributes['aria-label'].includes('shared 0–100% scale')));
});

test('all contextual help shares accessible focus, tap, outside-click, blur and Escape behaviour',()=>{
  const doc=document(),handlers={};doc.addEventListener=(type,fn)=>{(handlers[type]??=[]).push(fn);};
  const first=metricGuide(doc,'test-key',{label:'Key Variables Evaluated',description:TERMS.key,icon:true}),second=metricGuide(doc,'test-null',{label:'Null-rate differences',description:TERMS.nulls,icon:true});
  assert.equal(first.tip.hidden,true);assert.equal(first.tip.attributes.role,'tooltip');assert.equal(first.button.attributes['aria-describedby'],'test-key');assert.equal(first.button.attributes['aria-label'],'About Key Variables Evaluated');
  first.button.events.focus();assert.equal(first.tip.hidden,false);first.button.events.click();assert.equal(first.tip.hidden,false);
  handlers.pointerdown[0]({target:first.button});assert.equal(first.tip.hidden,false);
  handlers.pointerdown[0]({target:{}});assert.equal(first.tip.hidden,true);assert.equal(first.button.attributes['aria-expanded'],'false');
  first.wrap.events.pointerenter({pointerType:'touch'});assert.equal(first.tip.hidden,true);
  first.button.events.click();assert.equal(first.tip.hidden,false);first.button.events.click();assert.equal(first.tip.hidden,true);
  first.wrap.events.pointerenter({pointerType:'mouse'});assert.equal(first.tip.hidden,false);first.wrap.events.pointerleave();assert.equal(first.tip.hidden,true);
  first.button.events.focus();second.button.events.focus();assert.equal(first.tip.hidden,true);assert.equal(second.tip.hidden,false);
  handlers.keydown[0]({key:'Escape'});assert.equal(second.tip.hidden,true);
  first.button.events.focus();first.button.events.blur();assert.equal(first.tip.hidden,true);
  assert.equal(handlers.keydown.length,1);assert.equal(handlers.pointerdown.length,1);
  const view=normalizeValidation(structuredClone(postFixture)),node=renderValidation(doc,view),tips=all(node).filter(n=>n.attributes.role==='tooltip');
  assert.equal(tips.length,12);assert.equal(new Set(tips.map(n=>n.id)).size,tips.length);
  for(const name of ['key','within','review','unavailable','fidelity','conditional','nulls','variation','correlation'])assert.ok(tips.some(n=>n.textContent===TERMS[name]));
});

test('findings explain supplied tail points and keep very small nonzero rates visible',()=>{
  const v=normalizeValidation(structuredClone(postFixture)).v,tail=v.post_pilot.assessments.find(a=>a.key==='tail.available_credit');
  const detail=v.post_pilot.numeric_details.find(r=>r.key==='available_credit');
  detail.tail_points=[{name:'P01',source:10,generated:1,difference:-9},{name:'P05',source:20,generated:8,difference:-12},{name:'P99',source:99,generated:100,difference:1}];
  const copy=findingCopy(tail,v);assert.equal(copy.source,'20 at the lowest 5% point');assert.equal(copy.synthetic,'8 at the lowest 5% point');assert.match(copy.comparison,/12 amount units lower/);
  const tiny=findingCopy({key:'null_field.TRADELINES.payment_pattern',column:'payment_pattern',family:'nulls',status:'NEEDS_REVIEW',source:0,generated:.000001,score:.0001},v);
  assert.equal(tiny.synthetic,'0.0001% missing');assert.match(tiny.comparison,/0\.0001 percentage points higher/);
});

test('a strong saved grade cannot fill missing paired numeric or category evidence',()=>{
  const v=normalizeValidation(structuredClone(postFixture)).v,a=v.assessments.find(a=>a.key==='numeric.credit_limit');
  v.numeric.find(n=>n.key==='credit_limit').percentiles[0].source=null;assert.equal(findingEvidence(v,a).eligible,false);
  const category=v.assessments.find(a=>a.key==='categorical.past_due');v.assessments.find(a=>a.key==='null.past_due').source_count=null;
  assert.equal(findingEvidence(v,category).eligible,false);
  const t=v.post_pilot.assessments.find(a=>a.key==='tail.current_balance');v.post_pilot.numeric_details.find(n=>n.key==='current_balance').tail_points=[];
  assert.equal(findingEvidence(v,t).eligible,false);
});
