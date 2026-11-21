/* Small, dependency-free charts of published aggregates. No estimates or row data. */
(() => {
  "use strict";
  const finite = n => typeof n === "number" && Number.isFinite(n);
  const fmt = n => finite(n) ? new Intl.NumberFormat("en", {maximumFractionDigits: 2}).format(n) : "Unavailable";
  function el(doc, tag, text, cls) { const n=doc.createElement(tag); if(text!==undefined)n.textContent=text; if(cls)n.className=cls; return n; }
  function svg(doc, tag, attrs={}, text) { const n=doc.createElementNS("http://www.w3.org/2000/svg",tag); for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v)); if(text!==undefined)n.textContent=text; return n; }
  function legend(doc) { const n=el(doc,"p",undefined,"viz-legend"); n.append(el(doc,"span","SOURCE baseline","legend-original"),el(doc,"span","Synthetic cohort","legend-synthetic")); return n; }
  function dataTable(doc, headings, rows) { const d=el(doc,"details",undefined,"report-details"),wrap=el(doc,"div",undefined,"table-scroll"), t=el(doc,"table",undefined,"report-table"),head=el(doc,"thead"),body=el(doc,"tbody"),hr=el(doc,"tr"); wrap.tabIndex=0; wrap.setAttribute("role","region");wrap.setAttribute("aria-label","Chart data");headings.forEach(h=>{const n=el(doc,"th",h);n.setAttribute("scope","col");hr.append(n);});head.append(hr);rows.forEach(r=>{const tr=el(doc,"tr");r.forEach((v,i)=>{const n=el(doc,i?"td":"th",v);if(!i)n.setAttribute("scope","row");tr.append(n);});body.append(tr);});t.append(el(doc,"caption","Published chart values"),head,body);wrap.append(t);d.append(el(doc,"summary","View chart values"),wrap);return d; }
  function lineChart(doc, title, labels, original, generated, {percent=false, sparse=[], positions=null, domain=null}={}) {
    const figure=el(doc,"figure",undefined,"exec-chart"), chart=svg(doc,"svg",{viewBox:"0 0 760 315",role:"img","aria-label":title});
    chart.append(svg(doc,"title",{},title),svg(doc,"desc",{},"Solid charcoal: original. Dashed red: synthetic. Lines join measured points only. Missing values create gaps. Hollow points indicate insufficient comparison evidence."));
    const values=[...original,...generated].filter(finite), lo=domain?domain[0]:percent?0:Math.min(0,...values), upper=Math.max(1,...values)*1.08, unit=10**Math.floor(Math.log10(upper)), hi=domain?domain[1]:percent?100:Math.ceil(upper/unit)*unit;
    const x=i=>labels.length===1?390:80+620*(positions?(positions[i]-positions[0])/(positions[positions.length-1]-positions[0]):i/Math.max(1,labels.length-1)), y=n=>255-(n-lo)/(hi-lo)*215;
    for(let i=0;i<=4;i++){const value=lo+(hi-lo)*i/4, yy=y(value),label=percent?fmt(value)+"%":Math.abs(value)>=1000?fmt(value/1000)+"k":fmt(value);chart.append(svg(doc,"line",{x1:80,x2:700,y1:yy,y2:yy,class:"viz-grid"}),svg(doc,"text",{x:68,y:yy+5,"text-anchor":"end",class:"viz-axis"},label));}
    labels.forEach((label,i)=>chart.append(svg(doc,"text",{x:x(i),y:300,"text-anchor":"middle",class:"viz-axis"},label)));
    for(const [series,cls] of [[original,"original"],[generated,"synthetic"]]){
      let previous=null;
      series.forEach((value,i)=>{if(!finite(value)){previous=null;return;}if(previous!==null)chart.append(svg(doc,"line",{x1:x(previous),y1:y(series[previous]),x2:x(i),y2:y(value),class:"viz-line viz-"+cls}));const point=svg(doc,"circle",{cx:x(i),cy:y(value),r:5,class:"viz-point viz-"+cls+(sparse.includes(i)?" viz-sparse":"")});point.append(svg(doc,"title",{},labels[i]+" · "+cls+": "+fmt(value)+(percent?"%":"")+(sparse.includes(i)?" · comparison pending":"")));chart.append(point);previous=i;});
    }
    figure.append(legend(doc),chart,dataTable(doc,["Measured point","SOURCE baseline","Synthetic cohort"],labels.map((label,i)=>[label,fmt(original[i])+(percent&&finite(original[i])?"%":""),fmt(generated[i])+(percent&&finite(generated[i])?"%":"")])));return figure;
  }
  function distribution(doc,v,{key="credit_limit",showSelector=true}={}) {
    const root=el(doc,"div"),label=el(doc,"label","Compare a variable ","viz-select"),select=el(doc,"select"),body=el(doc,"div");select.setAttribute("aria-label","Distribution variable");
    v.numeric.forEach(r=>{const option=el(doc,"option",r.label);option.value=r.key;select.append(option);});select.value=v.numeric.some(r=>r.key===key)?key:v.numeric[0]?.key;
    function draw(){const r=v.numeric.find(r=>r.key===select.value)||v.numeric[0],points=["P25","P50","P75","P95"].map(name=>r.percentiles.find(p=>p.name===name));body.replaceChildren(lineChart(doc,r.label+": original vs synthetic percentiles",points.map(p=>p.name),points.map(p=>p.source),points.map(p=>p.generated),{positions:[25,50,75,95]}),el(doc,"p","Measured percentile profile, not a density estimate. Lines connect the 25th, 50th, 75th and 95th percentiles; no individual records are shown.","measurement-note"));}
    select.addEventListener("change",draw);label.append(select);if(showSelector)root.append(label);root.append(body);draw();return root;
  }
  function categorical(doc,v) {
    const root=el(doc,"figure",undefined,"category-chart");root.append(legend(doc));
    for(const row of v.categorical){const group=el(doc,"div",undefined,"category-group");group.append(el(doc,"h3",row.category==="Y"?"Past due":"Not past due"));for(const [field,label] of [["source","SOURCE"],["generated","Synthetic"]]){const line=el(doc,"div",undefined,"category-line"),track=el(doc,"div",undefined,"category-track"),bar=el(doc,"div",undefined,"category-fill "+field);bar.style.width=finite(row[field])?Math.max(0,Math.min(100,row[field]*100))+"%":"0%";track.setAttribute("aria-hidden","true");track.append(bar);line.append(el(doc,"span",label),track,el(doc,"strong",finite(row[field])?fmt(row[field]*100)+"%":"Pending"));group.append(line);}group.append(el(doc,"p",fmt(row.absolute_difference_pp)+" percentage-point difference","measurement-note"));root.append(group);}root.append(el(doc,"figcaption","Both series use the same 0–100% scale. A close category mix does not establish preserved relationships."));return root;
  }
  function conditional(doc,v){const rows=v.assessments.filter(a=>a.family==="conditional").sort((a,b)=>a.key.localeCompare(b.key));const labels=rows.map(r=>r.label.replace("Past due · utilization ",""));return lineChart(doc,"Past-due rates by credit utilization",labels,rows.map(r=>finite(r.source)?r.source*100:null),rows.map(r=>finite(r.generated)?r.generated*100:null),{percent:true,sparse:rows.flatMap((r,i)=>r.status==="UNAVAILABLE"?[i]:[])});}
  function cardinality(doc,v) {
    const root=el(doc,"div"),label=el(doc,"label","Compare a relationship ","viz-select"),select=el(doc,"select"),body=el(doc,"div");select.setAttribute("aria-label","Cardinality relationship");
    v.cardinality.forEach(r=>{const option=el(doc,"option",r.label);option.value=r.key;select.append(option);});select.value="accounts_per_customer";
    function draw(){const r=v.cardinality.find(r=>r.key===select.value)||v.cardinality[0];
      const available=r.bins.some(b=>finite(b.source)||finite(b.generated));
      if(!available){body.replaceChildren(el(doc,"p","No paired cardinality distribution is available for this relationship. No substitute distribution is drawn.","results-notice"));return;}
      const chart=el(doc,"div",undefined,"category-chart cardinality-chart");chart.append(legend(doc));
      for(const b of r.bins){const group=el(doc,"div",undefined,"category-group");group.append(el(doc,"h4",b.bucket+" related records"));for(const [field,title] of [["source","SOURCE"],["generated","Synthetic"]]){const line=el(doc,"div",undefined,"category-line"),track=el(doc,"div",undefined,"category-track"),bar=el(doc,"div",undefined,"category-fill "+field);bar.style.width=finite(b[field])?Math.max(0,Math.min(100,b[field]*100))+"%":"0%";track.setAttribute("aria-hidden","true");track.append(bar);line.append(el(doc,"span",title),track,el(doc,"strong",finite(b[field])?fmt(b[field]*100)+"%":"Unavailable"));group.append(line);}chart.append(group);}
      body.replaceChildren(chart,dataTable(doc,["Related records","SOURCE proportion","Synthetic proportion","Absolute gap (pp)"],r.bins.map(b=>[b.bucket,finite(b.source)?fmt(b.source*100)+"%":"Unavailable",finite(b.generated)?fmt(b.generated*100)+"%":"Unavailable",fmt(b.absolute_difference_pp)])),el(doc,"p","Each pair uses the same 0–100% scale. Counts of five or more are grouped for display; total variation uses the full saved distribution.","measurement-note"));}
    select.addEventListener("change",draw);label.append(select);root.append(label,body);draw();return root;
  }
  function summary(report,v){const checks=v.assessments.filter(a=>["correlation","conditional","cardinality","graph"].includes(a.family)),available=checks.filter(a=>a.status!=="UNAVAILABLE");return {relationshipMatched:available.filter(a=>["STRONG","ACCEPTABLE"].includes(a.status)).length,relationshipCompared:available.length,relationshipPending:checks.length-available.length,coverage:report.validation.account_balance_join_coverage};}
  const api={distribution,categorical,conditional,cardinality,summary,fmt,lineChart};if(typeof module!=="undefined"&&module.exports)module.exports=api;if(typeof window!=="undefined")window.SageViz=api;
})();
