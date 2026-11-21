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
  querySelectorAll(selector){return all(this).filter(n=>selector.startsWith('.')?n.className===selector.slice(1):n.tagName===selector.toUpperCase());}
  querySelector(selector){return this.querySelectorAll(selector)[0];}
  contains(other){return all(this).includes(other);}
  focus(){this.ownerDocument.activeElement=this;this.events.focus?.();}
  scrollIntoView(options){this.scrolled=options;}
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

test('expanded findings retain their measured ranking and have distinct disclosure labels',()=>{
  const view=validation.normalizeValidation(clone()),root=validation.executiveFindings(document(),view);
  for(const [i,key] of ['strengths','weaknesses'].entries()){
    const panel=root.children[i],lists=all(panel).filter(n=>n.tagName==='OL');
    assert.equal(lists[0].attributes.start,'1');
    if(view.v[key].length>3){assert.equal(lists[1].attributes.start,'4');assert.equal(lists[1].style.counterReset,'findings 3');}
    const summary=all(panel).find(n=>n.tagName==='SUMMARY');
    if(summary)assert.equal(summary.textContent,key==='strengths'?'More measured strengths':'More measured discrepancies');
  }
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
function pipeline(isMobile=false){
  const doc=document(),ids={},make=(id,tag='div')=>{const node=new Node(doc,tag);ids[id]=node;return node;};
  const explorer=make('pipeline-explorer'),panel=make('pipeline-detail'),overview=make('pipeline-overview'),status=make('pipeline-status','p'),reset=make('pipeline-reset','button');
  const stages=Array.from({length:7},(_,i)=>{const stage=new Node(doc,'li');stage.className='pipeline-stage';stage.dataset.detail='detail-'+i;stage.dataset.title='Stage '+i;
    const button=new Node(doc,'button'),more=new Node(doc,'span');more.className='stage-more';stage.append(button,more);explorer.append(stage);panel.append(make('detail-'+i,'article'));return {stage,button,more,detail:ids['detail-'+i]};});
  panel.append(status,reset,overview);explorer.append(panel);doc.getElementById=id=>ids[id];setupPipeline(doc,{isMobile:()=>isMobile});
  return {doc,explorer,panel,overview,status,reset,stages};
}
test('hover previews one stage without moving the page; leaving restores the overview',()=>{
  const p=pipeline(),s=p.stages[2];assert.equal(p.overview.hidden,false);assert.ok(p.stages.every(s=>s.detail.hidden));
  s.stage.events.pointerenter({pointerType:'mouse'});assert.equal(s.button.attributes['aria-expanded'],'true');assert.equal(s.detail.hidden,false);assert.equal(p.overview.hidden,true);assert.match(p.status.textContent,/Preview/);
  assert.equal(p.panel.scrolled,undefined);p.explorer.events.pointerleave();assert.equal(s.detail.hidden,true);assert.equal(p.overview.hidden,false);
});
test('click keeps a stage selected through pointer leave and outside focus; second click clears',()=>{
  const p=pipeline(),s=p.stages[2];s.button.focus();s.button.events.click();assert.equal(s.more.textContent,'Selected');
  assert.equal(s.button.attributes['aria-pressed'],'true');assert.ok(p.stages.filter(other=>other!==s).every(other=>other.button.attributes['aria-pressed']==='false'));
  p.explorer.events.pointerleave();assert.equal(s.detail.hidden,false);p.explorer.events.focusout({relatedTarget:new Node(p.doc,'p')});assert.equal(s.detail.hidden,false);
  const other=p.stages[4];other.stage.events.pointerenter({pointerType:'mouse'});assert.equal(other.detail.hidden,false);assert.equal(s.detail.hidden,true);
  p.explorer.events.pointerleave();assert.equal(s.detail.hidden,false);assert.equal(other.detail.hidden,true);
  s.button.events.click();assert.equal(p.overview.hidden,false);assert.ok(p.stages.every(s=>s.button.attributes['aria-expanded']==='false'));
  assert.ok(p.stages.every(s=>s.button.attributes['aria-pressed']==='false'));
});
test('keyboard previews, arrows, Home/End, Escape and Back to stages keep focus predictable',()=>{
  const p=pipeline(),s=p.stages[2];s.button.focus();assert.equal(s.detail.hidden,false);
  const key=k=>({key:k,preventDefault(){this.prevented=true;}});
  s.button.events.keydown(key('ArrowRight'));assert.equal(p.doc.activeElement,p.stages[3].button);
  p.stages[3].button.events.keydown(key('End'));assert.equal(p.doc.activeElement,p.stages[6].button);
  p.stages[6].button.events.keydown(key('Home'));assert.equal(p.doc.activeElement,p.stages[0].button);
  p.explorer.events.keydown(key('Escape'));assert.equal(p.overview.hidden,false);assert.equal(p.doc.activeElement,p.stages[0].button);
  s.button.focus();s.button.events.click();p.reset.focus();p.reset.events.click();assert.equal(p.doc.activeElement,s.button);assert.equal(s.detail.hidden,true);assert.equal(p.reset.hidden,true);
});
test('touch has no hover dependency; selecting scrolls to details and leaves all seven stages available',()=>{
  const p=pipeline(true),s=p.stages[4];s.stage.events.pointerenter({pointerType:'touch'});assert.equal(p.overview.hidden,false);
  s.button.events.click();assert.equal(s.detail.hidden,false);assert.deepEqual(p.panel.scrolled,{block:'nearest',behavior:'auto'});
  assert.equal(p.stages.length,7);assert.ok(p.stages.every(s=>!s.stage.hidden&&!s.button.disabled));
  s.button.events.click();assert.equal(p.overview.hidden,false);
});
test('pipeline content supplies four business-facing facts for every existing stage',()=>{
  const html=fs.readFileSync(require.resolve('../docs/index.html'),'utf8'),section=html.split('id="pipeline-explorer"')[1].split('<section id="evidence"')[0];
  assert.equal((section.match(/class="stage-detail"/g)||[]).length,7);assert.doesNotMatch(section,/role="tooltip"/);
  for(const label of ['Purpose','Inputs','Outputs','Business value'])assert.equal((section.match(new RegExp('<dt>'+label+'</dt>','g'))||[]).length,7);
  for(const id of ['source','profile','ai','review','generate','validate','report'])assert.match(section,new RegExp('aria-controls="stage-'+id+'"'));
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

test('both pages offer the same named routes between the three exploration experiences',()=>{
  for(const name of ['index.html','validation.html']){
    const html=fs.readFileSync(require.resolve('../docs/'+name),'utf8'),nav=html.match(/<nav aria-label="Main navigation">(.*?)<\/nav>/s)[1];
    assert.deepEqual([...nav.matchAll(/<a[^>]*>(.*?)<\/a>/g)].map(m=>m[1]),['Overview','Pipeline','Validation Report','Synthetic Data Explorer','Downloads']);
    assert.equal((nav.match(/aria-current="page"/g)||[]).length,1);
    assert.match(nav,/href="(?:index.html)?#process"/);assert.match(nav,/href="(?:index.html)?#explore-records"/);
    assert.match(html,/aria-label="Explore SAGE"/);
  }
});

test('first-time reading path puts measured findings before detailed methodology and demo browsing',()=>{
  const html=fs.readFileSync(require.resolve('../docs/index.html'),'utf8');
  const sections=[...html.matchAll(/<section id="([^"]+)"/g)].map(m=>m[1]);
  assert.deepEqual(sections,['overview','process','validation','evidence','control','generation','explore-records','download-dataset','priorities']);
  const hero=html.split('<section id="overview"')[1].split('<section id="process"')[0];
  assert.match(hero,/SOURCE means the fabricated development baseline/);assert.match(hero,/href="#process">See how SAGE works/);
  assert.match(html,/AI sees statistical summaries, never individual banking records/);
  assert.match(html,/AI-generated text is never executed/);
});

test('report navigation prioritizes summary and keeps every evidence destination in a native disclosure',()=>{
  const html=fs.readFileSync(require.resolve('../docs/validation.html'),'utf8');
  const nav=html.match(/<nav class="report-nav"[^>]*>(.*?)<\/nav>/s)[1];
  assert.match(nav,/<details class="report-evidence-links"><summary>Evidence sections<\/summary>/);
  assert.doesNotMatch(nav,/<details[^>]*\bopen\b/);
  const links=[...nav.matchAll(/href="#([^"]+)"/g)].map(m=>m[1]);
  assert.deepEqual(links,['summary','findings','explore-validation','numeric','categorical','completeness','dependencies','structure','privacy','methodology']);
  const root=validation.renderValidation(document(),validation.normalizeValidation(clone()));
  for(const id of links)assert.ok(all(root).some(n=>n.id===id),'Missing destination '+id);
});

test('overview offers an in-place retry after unavailable results without substituting measurements',async()=>{
  const doc=document(),ids={};for(const name of ['executive-results','hero-status','distribution-preview','hero-customers','hero-accounts','hero-rules'])ids[name]=new Node(doc,'div');doc.getElementById=id=>ids[id];
  const previous=global.window;global.window={SageResults:results,SageValidation:validation,SageViz:viz};let available=false,calls=0;
  try{await mountShowcase(doc,{location:{origin:'https://example.invalid'},fetcher:async()=>{calls++;return available?{ok:true,text:async()=>JSON.stringify(fixture)}:{ok:false};}});
    const retry=all(ids['executive-results']).find(n=>n.tagName==='BUTTON');assert.equal(retry.textContent,'Retry latest results');assert.equal(ids['hero-customers'].textContent,'—');
    available=true;const recovering=retry.events.click();assert.equal(retry.disabled,true);assert.match(ids['hero-status'].textContent,/Loading/);await recovering;
    assert.equal(calls,2);assert.equal(ids['hero-customers'].textContent,viz.fmt(fixture.generation.customers.value));assert.equal(ids['executive-results'].attributes['aria-busy'],'false');
  }finally{global.window=previous;}
});
