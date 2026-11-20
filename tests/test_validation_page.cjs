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
}
function document(){const d={baseURI:"https://example.invalid/project/validation.html"};d.createElement=t=>new Node(d,t);return d;}
function all(n){return [n,...n.children.flatMap(all)];}
const clone=()=>structuredClone(fixture);
const location={origin:"https://example.invalid",protocol:"https:"};
const response=r=>({ok:true,text:async()=>JSON.stringify(r)});

test("measured classifications, raw percentiles, populations and dependencies are displayed",()=>{
  const view=normalizeValidation(clone()),node=renderValidation(document(),view),text=node.textContent;
  assert.match(text,/Differences need review/);assert.match(text,/30% total variation/);
  assert.match(text,/SOURCE P25/);assert.match(text,/Strong match/);assert.match(text,/Needs review/);
  assert.match(text,/Credit limit \/ balance correlation/);assert.match(text,/Accounts per person/);
  assert.match(text,/Other cross-table referential integrity/);assert.match(text,/Pending/);
  assert.ok(!text.includes("high quality"));
  const conditional=all(node).find(n=>n.tagName==="TABLE"&&n.children[0].textContent==="Past-due rates by utilization bucket");
  assert.match(conditional.textContent,/Strong match/);assert.doesNotMatch(conditional.textContent,/Passed/);
  const integrity=all(node).find(n=>n.tagName==="TABLE"&&n.children[0].textContent==="Generated structural and business-rule checks");
  assert.match(integrity.textContent,/Passed/);
});

test("numeric table sorts independently without losing raw data",()=>{
  const node=renderValidation(document(),normalizeValidation(clone()));
  const select=all(node).find(n=>n.tagName==="SELECT");
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
