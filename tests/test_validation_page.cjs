"use strict";
const test=require("node:test"),assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path");
const {normalizeValidation,renderValidation,mountValidation}=require("../docs/validation.js");
const fixture=JSON.parse(fs.readFileSync(path.join(__dirname,"../docs/reporting/example.json"),"utf8"));
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
  assert.match(node.textContent,/Balance mean needs review/);assert.match(node.textContent,/REVIEW_REQUIRED/);
  assert.match(node.textContent,/SOURCE-rare pattern matches/);assert.match(node.textContent,/General dataset release blocked/);
  assert.match(node.textContent,/Fabricated demo downloads require separate verification/);
  assert.match(node.textContent,/Additional provisional screens/);assert.match(node.textContent,/Mandatory integrity requirements/);
  assert.equal(all(node).filter(n=>n.className?.includes("mean-series")).length,8);
  assert.ok(!all(node).some(n=>n.tagName==="A"&&/\.zip|\.csv|\.parquet/.test(n.attributes.href||"")));
  const unchanged=structuredClone(r);delete unchanged.rules;delete unchanged.validation_report.rule_outcomes;
  assert.equal(renderValidation(document(),normalizeValidation(unchanged)).textContent,node.textContent);
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
  assert.match(text,/Differences need review/);assert.match(text,/30% total variation/);
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
  assert.match(root.textContent,/Validation results pending/);assert.doesNotMatch(root.textContent,/Strongest measured areas/);
});

test("refresh failures clear previous figures and recover; fetch is public same-origin only",async()=>{
  const doc=document(),root=new Node(doc,"div");let calls=[],fail=false;
  const loader=mountValidation(root,{location,fetcher:async(url,options)=>{calls.push({url,options});if(fail)throw new Error("PRIVATE_PAYLOAD");return response(fixture);}});
  await loader.ready;assert.match(root.textContent,/Latest validated pipeline results loaded/);
  assert.equal(calls[0].url,"https://example.invalid/project/latest-pipeline.json");assert.equal(calls[0].options.credentials,"omit");
  fail=true;await loader.refresh();assert.match(root.textContent,/Validation results pending/);assert.ok(!root.textContent.includes("PRIVATE_PAYLOAD"));assert.doesNotMatch(root.textContent,/Strongest measured areas/);
  fail=false;await loader.refresh();assert.match(root.textContent,/Strongest measured areas/);
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
    assert.ok(captions.includes(caption));
  assert.match(root.textContent,/It does not establish how many of all customers have zero accounts/);
  assert.match(root.textContent,/not equality with SOURCE/);
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
