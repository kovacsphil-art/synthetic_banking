'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const {normalizeValidation,exploreValidation,renderValidation}=require('../docs/validation.js');
const fixture=JSON.parse(fs.readFileSync(require.resolve('../docs/reporting/example.json'),'utf8'));
class Node{
  constructor(doc,tag){this.ownerDocument=doc;this.tagName=tag.toUpperCase();this.children=[];this.attributes={};this.dataset={};this.events={};this.style={};this._text='';this.value='';}
  set textContent(t){this._text=String(t);this.children=[];}get textContent(){return this._text+this.children.map(c=>c.textContent).join(' ');}
  append(...n){this.children.push(...n);}replaceChildren(...n){this.children=n;this._text='';}
  setAttribute(k,v){this.attributes[k]=String(v);}addEventListener(k,v){this.events[k]=v;}
  focus(){this.ownerDocument.activeElement=this;this.events.focus?.();}
}
function all(n){return [n,...n.children.flatMap(all)];}
function setup(){const doc={};doc.createElement=t=>new Node(doc,t);doc.createElementNS=(_,t)=>new Node(doc,t);const view=normalizeValidation(structuredClone(fixture)),root=exploreValidation(doc,view);return {doc,view,root,panel:k=>all(root).find(n=>n.id==='validation-panel-'+k)};}
const named=(n,role,label)=>all(n).find(n=>n.attributes.role===role&&n.textContent===label);
const select=(p,label)=>all(p).find(n=>n.tagName==='SELECT'&&n.attributes['aria-label']===label);
const table=p=>all(p).find(n=>n.tagName==='TABLE'&&n.children[0].textContent.endsWith('statistical differences'));
const rows=p=>table(p).children.find(n=>n.tagName==='TBODY').children;
const change=(node,value)=>{node.value=value;node.events.change();};

test('tabs keep executive summary and headline findings visible, with one active accessible panel',()=>{
  const s=setup(),tabs=all(s.root).filter(n=>n.attributes.role==='tab');assert.equal(tabs.length,3);
  assert.equal(tabs[0].attributes['aria-selected'],'true');assert.equal(s.panel('numeric').hidden,false);assert.equal(s.panel('categorical').hidden,true);
  tabs[0].events.keydown({key:'ArrowRight',preventDefault(){}});assert.equal(s.doc.activeElement,tabs[1]);assert.equal(tabs[1].tabIndex,0);assert.equal(s.panel('numeric').hidden,true);
  tabs[1].events.keydown({key:'End',preventDefault(){}});assert.equal(s.doc.activeElement,tabs[2]);assert.equal(s.panel('dependency').hidden,false);
  tabs[2].events.keydown({key:'Home',preventDefault(){}});assert.equal(s.doc.activeElement,tabs[0]);
  const report=renderValidation(s.doc,s.view),ids=report.children.map(n=>n.id);assert.ok(ids.indexOf('summary')<ids.indexOf('explore-validation'));assert.ok(ids.indexOf('findings')<ids.indexOf('explore-validation'));
  assert.ok(!report.children.find(n=>n.id==='summary').hidden);assert.ok(!report.children.find(n=>n.id==='findings').hidden);
});
test('numeric selector uses only supplied percentiles and preserves input measurements',()=>{
  const s=setup(),before=JSON.stringify(s.view),p=s.panel('numeric'),picker=select(p,'Numeric variable');
  change(picker,'current_balance');assert.match(p.textContent,/Current balance: original vs synthetic percentiles/);
  const chart=all(p).find(n=>n.tagName==='FIGURE');assert.equal(all(chart).filter(n=>n.tagName==='CIRCLE').length,8);
  const supplied=s.view.v.numeric.find(n=>n.key==='current_balance');for(const point of supplied.percentiles)assert.ok(chart.textContent.includes(new Intl.NumberFormat('en',{maximumFractionDigits:2}).format(point.source)));
  assert.equal(JSON.stringify(s.view),before);
});
test('difference table toggles sort direction without losing focus; unavailable comparisons stay last',()=>{
  const s=setup(),p=s.panel('numeric'),header=all(p).find(n=>n.tagName==='BUTTON'&&n.attributes['aria-label']==='Sort numeric differences by gap');
  assert.equal(rows(p)[0].children[0].textContent,'Available credit');assert.equal(rows(p).at(-1).children[0].textContent,'Overlimit amount');
  header.focus();header.events.click();assert.equal(rows(p)[0].children[0].textContent,'Credit limit');assert.equal(rows(p).at(-1).children[0].textContent,'Overlimit amount');assert.equal(s.doc.activeElement,header);
  const th=all(p).find(n=>n.tagName==='TH'&&n.children.includes(header));assert.equal(th.attributes['aria-sort'],'ascending');
  assert.equal(header.dataset.sortLabel,'Smallest first');
  assert.match(table(p).textContent,/SOURCE median \(P50\)/);assert.match(table(p).textContent,/Worst percentile gap \/ IQR/);
});
test('strongest and weakest reuse published status without treating unavailable rows as weak',()=>{
  const s=setup(),p=s.panel('numeric'),mode=select(p,'Numeric match view');
  change(mode,'strong');assert.ok(rows(p).every(n=>n.textContent.includes('Strong match')));assert.ok(!table(p).textContent.includes('Overlimit amount'));
  change(mode,'weak');assert.equal(rows(p).length,1);assert.equal(rows(p)[0].children[0].textContent,'Available credit');assert.equal(select(p,'Numeric variable').value,'available_credit');
  const cat=s.panel('categorical');change(select(cat,'Categorical match view'),'weak');assert.match(cat.textContent,/No published categorical comparisons have this classification/);assert.match(cat.textContent,/No substitute statistics/);assert.ok(!table(cat));
});
test('categorical exploration honestly exposes the one published variable and measured category shares',()=>{
  const s=setup(),p=s.panel('categorical'),picker=select(p,'Categorical variable');assert.equal(picker.children.length,1);assert.equal(picker.disabled,true);
  assert.match(p.textContent,/Only one published variable matches this view/);assert.equal(picker.attributes['aria-describedby'],'explore-variable-help-categorical');
  assert.match(p.textContent,/one categorical variable/);assert.equal(rows(p).length,2);assert.match(table(p).textContent,/SOURCE share/);assert.match(table(p).textContent,/pp/);
});
test('dependency charts switch between measured conditional rates and Pearson coefficients',()=>{
  const s=setup(),p=s.panel('dependency'),picker=select(p,'Dependency variable');
  assert.match(p.textContent,/past-due rates by credit utilization/i);assert.equal(rows(p).length,5);
  change(picker,'correlation');assert.match(p.textContent,/Pearson correlation/);assert.equal(rows(p).length,1);
  const circles=all(p).filter(n=>n.tagName==='CIRCLE');assert.equal(circles.length,2);assert.ok(circles.every(n=>n.attributes.cx==='390'));assert.match(p.textContent,/correlation units/);
});
test('metric guides work on focus, hover, tap and Escape without adding statistics',()=>{
  const s=setup(),p=s.panel('numeric'),b=all(p).find(n=>n.tagName==='BUTTON'&&n.textContent==='Metric guide'),tip=all(p).find(n=>n.attributes.role==='tooltip');
  assert.equal(tip.hidden,true);b.focus();assert.equal(tip.hidden,false);assert.match(tip.textContent,/IQR/);
  b.events.click();assert.equal(tip.hidden,false);b.events.keydown({key:'Escape',preventDefault(){}});assert.equal(tip.hidden,true);assert.equal(s.doc.activeElement,b);
  const wrap=all(p).find(n=>n.className==='metric-guide');s.doc.activeElement=null;wrap.events.pointerenter({pointerType:'touch'});assert.equal(tip.hidden,true);wrap.events.pointerenter({pointerType:'mouse'});assert.equal(tip.hidden,false);wrap.events.pointerleave();assert.equal(tip.hidden,true);
});

test('hover help is dismissible without focus and repeated rendering keeps one document Escape listener',()=>{
  const s=setup(),handlers=[];s.doc.addEventListener=(name,handler)=>handlers.push([name,handler]);
  const root=exploreValidation(s.doc,s.view),p=all(root).find(n=>n.id==='validation-panel-numeric'),wrap=all(p).find(n=>n.className==='metric-guide'),tip=all(p).find(n=>n.attributes.role==='tooltip');
  wrap.events.pointerenter({pointerType:'mouse'});assert.equal(tip.hidden,false);handlers[0][1]({key:'Escape'});assert.equal(tip.hidden,true);
  exploreValidation(s.doc,s.view);assert.equal(handlers.length,1);
});
test('missing distributions display an informative unavailable state without axes or invented points',()=>{
  const s=setup();for(const point of s.view.v.numeric[0].percentiles){point.source=null;point.generated=null;point.difference=null;}
  const root=exploreValidation(s.doc,s.view),p=all(root).find(n=>n.id==='validation-panel-numeric');assert.match(p.textContent,/neither population has published values/);assert.equal(all(p).filter(n=>n.tagName==='CIRCLE').length,0);
});
test('sparse conditional comparisons stay unranked while their raw chart points remain visible',()=>{
  const s=setup(),a=s.view.v.assessments.find(a=>a.key==='conditional.3');a.status='UNAVAILABLE';a.score=null;a.reason='insufficient_conditional_rows';a.source_n=15;
  const root=exploreValidation(s.doc,s.view),p=all(root).find(n=>n.id==='validation-panel-dependency');
  assert.match(rows(p).at(-1).textContent,/Fewer than the configured minimum/);
  assert.equal(all(p).filter(n=>n.tagName==='CIRCLE'&&n.attributes.class.includes('viz-sparse')).length,2);
  change(select(p,'Dependency match view'),'strong');assert.ok(rows(p).every(r=>r.textContent.includes('Strong match')));
  assert.equal(all(p).filter(n=>n.tagName==='CIRCLE').length,10);
});
