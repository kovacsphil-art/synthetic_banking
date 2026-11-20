"use strict";
const test=require("node:test"), assert=require("node:assert/strict"),fs=require("node:fs");
const viz=require("../docs/executive-viz.js"), validation=require("../docs/validation.js"),results=require("../docs/results.js"),{setupPipeline,mountShowcase}=require("../docs/showcase.js");
const fixture=JSON.parse(fs.readFileSync(require.resolve("../docs/reporting/example.json"),"utf8"));
class Node {
  constructor(doc,tag){this.ownerDocument=doc;this.tagName=tag.toUpperCase();this.children=[];this.attributes={};this.dataset={};this.events={};this.style={};this._text="";}
  set textContent(v){this._text=String(v);this.children=[];}
  get textContent(){return this._text+this.children.map(n=>n.textContent).join(" ");}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=nodes;this._text="";}
  setAttribute(k,v){this.attributes[k]=String(v);}
  addEventListener(k,v){this.events[k]=v;}
  querySelector(selector){return all(this).find(n=>n.tagName===selector.toUpperCase());}
  contains(other){return all(this).includes(other);}
}
function all(n){return [n,...n.children.flatMap(all)];}
function document(){const d={baseURI:"https://example.invalid/index.html",events:{},addEventListener(k,v){this.events[k]=v;}};d.createElement=t=>new Node(d,t);d.createElementNS=(_,t)=>new Node(d,t);return d;}
const clone=()=>structuredClone(fixture);
test("distribution plots only the four supplied percentiles and switches variables",()=>{
  const doc=document(),v=validation.normalizeValidation(clone()).v,root=viz.distribution(doc,v);
  assert.match(root.textContent,/not a density estimate/);
  assert.equal(all(root).filter(n=>n.tagName==="CIRCLE").length,8);
  const points=v.numeric[0].percentiles;points.forEach(p=>assert.ok(root.textContent.includes(viz.fmt(p.source))));
  const select=all(root).find(n=>n.tagName==="SELECT");select.value="overlimit";select.events.change();assert.match(root.textContent,/Overlimit/);
});
test("missing conditional points make gaps; sparse comparisons have hollow markers and raw values",()=>{
  const v=validation.normalizeValidation(clone()).v,rows=v.assessments.filter(a=>a.family==="conditional");
  rows[1].source=null;rows[1].status="UNAVAILABLE";rows[3].status="UNAVAILABLE";
  const root=viz.conditional(document(),v),nodes=all(root);
  assert.equal(nodes.filter(n=>n.tagName==="CIRCLE"&&n.attributes.class.includes("viz-original")).length,4);
  assert.equal(nodes.filter(n=>n.tagName==="LINE"&&n.attributes.class==="viz-line viz-original").length,2);
  assert.ok(nodes.some(n=>n.tagName==="CIRCLE"&&n.attributes.class.includes("viz-sparse")));
  assert.match(root.textContent,/Unavailable/);assert.match(root.textContent,/comparison pending/);
});
test("executive summary uses measured counts without an overall percentage or AI execution metric",()=>{
  const report=clone(),v=validation.normalizeValidation(report).v,s=viz.summary(report,v);
  assert.equal(Object.hasOwn(s,"within"),false);assert.equal(Object.hasOwn(s,"applied"),false);
  assert.equal(s.relationshipCompared+s.relationshipPending,v.assessments.filter(a=>["correlation","conditional","cardinality","graph"].includes(a.family)).length);
  assert.ok(s.relationshipMatched<=s.relationshipCompared);
  assert.match(validation.executiveSummary(document(),{report,v}).textContent,/not an overall accuracy score/);
});

test("cardinality selector draws only published bins and leaves missing distributions unavailable",()=>{
  const v=validation.normalizeValidation(clone()).v,root=viz.cardinality(document(),v);
  assert.match(root.textContent,/0 related records/);assert.match(root.textContent,/5\+ related records/);
  assert.match(root.textContent,/full saved distribution/);
  const select=all(root).find(n=>n.tagName==="SELECT");select.value="tradelines_per_customer";select.events.change();
  assert.match(root.textContent,/No paired cardinality distribution/);
  assert.equal(all(root).filter(n=>n.className?.includes("category-fill")).length,0);
});
test("malformed chart values, public labels and headline counts are rejected",()=>{
  for(const mutate of [r=>r.validation_report.numeric[0].label="PRIVATE_VALUE",r=>r.validation_report.numeric[0].percentiles[0].source="PRIVATE_VALUE",r=>r.validation_report.summary.variables_total=999,r=>r.validation_report.numeric[0].status="UNAVAILABLE"]){const r=clone();mutate(r);assert.throws(()=>validation.normalizeValidation(r),/Invalid/);}
});
test("pipeline supports focus, first tap, second tap, Escape and outside dismissal",()=>{
  const doc=document(),stages=Array.from({length:7},()=>{const s=new Node(doc,"li");s.append(new Node(doc,"button"));return s;});doc.querySelectorAll=()=>stages;setupPipeline(doc);
  const stage=stages[2],button=stage.children[0];doc.activeElement=button;button.events.focus();assert.equal(button.attributes["aria-expanded"],"true");
  button.events.click();assert.equal(button.attributes["aria-expanded"],"true");button.events.click();assert.equal(button.attributes["aria-expanded"],"false");
  button.events.focus();doc.events.keydown({key:"Escape"});assert.equal(button.attributes["aria-expanded"],"false");
  button.events.click();assert.equal(button.attributes["aria-expanded"],"true");doc.events.click({target:new Node(doc,"p")});assert.equal(button.attributes["aria-expanded"],"false");
});
test("overview loads real aggregate fields and fails safely without exposing payloads",async()=>{
  const doc=document(),ids={};for(const name of ["executive-results","hero-status","distribution-preview","hero-customers","hero-accounts","hero-rules"])ids[name]=new Node(doc,"div");doc.getElementById=id=>ids[id];
  const previous=global.window;global.window={SageResults:results,SageValidation:validation,SageViz:viz};
  try{await mountShowcase(doc,{location:{origin:"https://example.invalid"},fetcher:async()=>({ok:true,text:async()=>JSON.stringify(fixture)})});assert.equal(ids["hero-customers"].textContent,viz.fmt(fixture.generation.customers.value));assert.match(ids["executive-results"].textContent,/Strongest measured areas/);
    await mountShowcase(doc,{location:{origin:"https://example.invalid"},fetcher:async()=>{throw new Error("PRIVATE_PAYLOAD");}});assert.match(ids["hero-status"].textContent,/unavailable/);assert.equal(ids["hero-customers"].textContent,"—");assert.ok(!ids["executive-results"].textContent.includes("PRIVATE"));
    ids["executive-results"].dataset.reportUrl="https://private.invalid/report";let called=false;await mountShowcase(doc,{location:{origin:"https://example.invalid"},fetcher:async()=>{called=true;}});assert.equal(called,false);
  }finally{global.window=previous;}
});
test("public pages use SAGE, concise process naming and only the versioned local assets",()=>{
  for(const name of ["index.html","validation.html"]){const html=fs.readFileSync(require.resolve("../docs/"+name),"utf8");assert.match(html,/SAGE/);assert.doesNotMatch(html,/RCAR|notebook/i);assert.doesNotMatch(html,/<script[^>]+https?:/i);for(const m of html.matchAll(/(?:src|href)="([^"?#]+\.(?:js|css))[^\"]*"/g))assert.ok(fs.existsSync(require.resolve("../docs/"+m[1])));}
});
