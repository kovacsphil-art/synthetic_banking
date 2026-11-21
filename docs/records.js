/* Bounded fabricated demo preview. Never requests Delta tables, CSVs or ZIPs. */
(() => {
  "use strict";
  const CONFIG=typeof module!=="undefined"&&module.exports?require("./records-config.js"):window.SageRecordsConfig;
  const keys=(object,expected)=>object&&typeof object==="object"&&!Array.isArray(object)&&Object.keys(object).length===expected.length&&expected.every(k=>Object.hasOwn(object,k));
  const integer=n=>Number.isSafeInteger(n)&&n>=0&&n<=250000;
  const patterns={person_id:/^P[0-9]{8}$/,account_id:/^A[0-9]{9}$/,tradeline_id:/^TL[0-9]{10}$/,code:/^[A-Za-z0-9 _/.-]{1,32}$/,
    date:/^[0-9]{4}-[0-9]{2}-[0-9]{2}(?:T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|\+00:00)?)?$/};
  const validDate=value=>Number.isFinite(Date.parse(value))&&new Date(value).toISOString().slice(0,10)===value.slice(0,10);
  const secret=/\b(?:AKIA|ASIA)[A-Z0-9]{16}\b|\bdapi[a-zA-Z0-9]{20,}\b|\bgh[pousr]_[a-zA-Z0-9]{20,}\b|\bgithub_pat_/i;
  function normalizePreview(report){
    if(!keys(report,["schema_version","release_mode","baseline","dataset_version","generated_at","privacy_status","preview_row_limit","tables"])||
      report.schema_version!==CONFIG.schema_version||report.release_mode!=="DEMO_ONLY"||report.baseline!=="FABRICATED_DEVELOPMENT"||
      typeof report.dataset_version!=="string"||!/^sage-demo-v[1-9][0-9]*(?:\.[0-9]+)*$/.test(report.dataset_version)||
      typeof report.generated_at!=="string"||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)$/.test(report.generated_at)||!validDate(report.generated_at)||
      !["PASS","REVIEW_REQUIRED"].includes(report.privacy_status)||report.preview_row_limit!==CONFIG.row_limit||!Array.isArray(report.tables)||report.tables.length!==6)throw new Error("Invalid demo preview");
    const tables=Object.entries(CONFIG.tables).map(([name,spec],i)=>{
      const table=report.tables[i];
      if(!keys(table,["name","total_rows","total_columns","columns","rows"])||table.name!==name||!integer(table.total_rows)||table.total_columns!==spec.total_columns||
        JSON.stringify(table.columns)!==JSON.stringify(spec.columns.map(c=>c.key))||!Array.isArray(table.rows)||table.rows.length!==Math.min(CONFIG.row_limit,table.total_rows))throw new Error("Invalid demo table");
      for(const row of table.rows){
        if(!Array.isArray(row)||row.length!==spec.columns.length)throw new Error("Invalid demo row");
        row.forEach((value,j)=>{
          const kind=spec.columns[j].kind;
          if(value===null&&!kind.endsWith("_id"))return;
          if(kind==="number"?typeof value!=="number"||!Number.isFinite(value):typeof value!=="string"||!patterns[kind].test(value)||secret.test(value)||kind==="date"&&!validDate(value))throw new Error("Invalid demo value");
        });
      }
      return table;
    });
    return {...report,tables};
  }
  function el(doc,tag,text,cls){const node=doc.createElement(tag);if(text!==undefined)node.textContent=text;if(cls)node.className=cls;return node;}
  const nf=new Intl.NumberFormat("en",{maximumFractionDigits:2});
  const dateFormat=new Intl.DateTimeFormat("en",{timeZone:"UTC",year:"numeric",month:"short",day:"numeric"});
  function display(value,kind){
    if(value===null)return "Not recorded";
    if(kind==="number")return nf.format(value);
    if(kind==="date")return dateFormat.format(new Date(value.endsWith("Z")||value.includes("+")?value:value.includes("T")?value+"Z":value+"T00:00:00Z"));
    return value;
  }
  function renderTable(doc,table,downloads=null){
    const spec=CONFIG.tables[table.name],root=el(doc,"div",undefined,"record-view");
    const heading=el(doc,"h3",spec.label);heading.id="record-table-title";
    root.append(heading,el(doc,"p",table.name,"record-context"),el(doc,"p",spec.description,"record-purpose"));
    const metrics=el(doc,"dl",undefined,"record-metrics");
    for(const [label,value] of [["Records in full table",nf.format(table.total_rows)],["Columns in full table",table.total_columns],["Columns shown",table.columns.length]]){
      const group=el(doc,"div");group.append(el(doc,"dt",label),el(doc,"dd",String(value)));metrics.append(group);
    }
    root.append(metrics,el(doc,"p",spec.relationship,"record-relationship"),el(doc,"p","Highlighted identifiers are synthetic. They identify fabricated records and connect related tables; the relationship note above explains which keys to match.","record-key-legend"));
    const guide=el(doc,"details",undefined,"record-guide");guide.append(el(doc,"summary","Column guide · "+table.columns.length+" shown"));
    const definitions=el(doc,"dl");
    for(const [i,c] of spec.columns.entries()){const group=el(doc,"div"),term=el(doc,"dt",c.label),desc=el(doc,"dd",c.description);desc.id="record-column-"+i;desc.append(el(doc,"code",c.key));group.append(term,desc);definitions.append(group);}
    guide.append(definitions);root.append(guide);
    if(downloads)root.append(downloads);
    if(!table.rows.length){root.append(el(doc,"p","No records in this demo table.","results-notice"));return root;}
    const help=el(doc,"p","Scroll horizontally to see every preview column. On a keyboard, focus the table area and use the arrow keys.","record-scroll-help");help.id="record-scroll-help";
    const wrap=el(doc,"div",undefined,"record-scroll");wrap.tabIndex=0;wrap.setAttribute("role","region");wrap.setAttribute("aria-labelledby",heading.id);wrap.setAttribute("aria-describedby",help.id);
    const grid=el(doc,"table",undefined,"record-table");grid.append(el(doc,"caption",spec.label+" · first "+table.rows.length+" records · selected columns"));
    const head=el(doc,"thead"),header=el(doc,"tr");
    spec.columns.forEach((c,i)=>{const th=el(doc,"th",c.label,c.kind.endsWith("_id")?"record-key-heading":"");th.setAttribute("scope","col");th.setAttribute("title",c.description+" ("+c.key+")");th.setAttribute("aria-describedby","record-column-"+i);header.append(th);});head.append(header);
    const body=el(doc,"tbody");
    for(const values of table.rows){const row=el(doc,"tr");values.forEach((value,i)=>{const isId=spec.columns[i].kind.endsWith("_id"),td=el(doc,i===0?"th":"td",undefined,value===null?"record-null":isId?"record-id":"");if(isId)td.append(el(doc,"span",display(value,spec.columns[i].kind),"record-id-value"));else td.textContent=display(value,spec.columns[i].kind);if(i===0)td.setAttribute("scope","row");if(value!==null)td.setAttribute("title",String(value));row.append(td);});body.append(row);}
    grid.append(head,body);wrap.append(grid);root.append(help,wrap,
      el(doc,"p","This shows selected columns from the first "+table.rows.length+" records in export key order. Linked records can fall outside the preview. Not recorded means a saved null value.","record-footnote"));
    return root;
  }
  async function loadPreview(doc,fetcher,location,url,timeoutMs){
    const target=new URL(url,doc.baseURI);
    if(!["http:","https:"].includes(target.protocol)||target.origin!==location.origin||!target.pathname.endsWith("/demo-preview.json")||target.search||target.hash)throw new Error("Invalid preview URL");
    const controller=new AbortController();let timer;
    try{
      const request=(async()=>{
        const response=await fetcher(target.href,{credentials:"omit",cache:"no-store",redirect:"error",signal:controller.signal});
        if(!response.ok)throw new Error("Preview unavailable");
        if(Number(response.headers?.get("content-length"))>CONFIG.max_bytes){controller.abort();throw new Error("Preview exceeds limit");}
        let raw;
        if(response.body?.getReader){
          const reader=response.body.getReader(),decoder=new TextDecoder("utf-8",{fatal:true});let bytes=0;raw="";
          try{while(true){const {done,value}=await reader.read();if(done)break;bytes+=value.byteLength;
            if(bytes>CONFIG.max_bytes){await reader.cancel();throw new Error("Preview exceeds limit");}raw+=decoder.decode(value,{stream:true});}raw+=decoder.decode();}
          finally{reader.releaseLock();}
        }else raw=await response.text();
        if(new TextEncoder().encode(raw).length>CONFIG.max_bytes)throw new Error("Preview exceeds limit");
        return normalizePreview(JSON.parse(raw));
      })();
      return await Promise.race([request,new Promise((_,reject)=>{timer=setTimeout(()=>{controller.abort();reject(new Error("Preview timed out"));},timeoutMs);})]);
    }finally{clearTimeout(timer);}
  }
  async function mountRecords(doc,options={}){
    const root=doc.getElementById("records-explorer");if(!root)return;
    const downloads=typeof module!=="undefined"&&module.exports?require('./downloads.js'):window.SageDownloads;
    const status=el(doc,"p","Verifying demo preview…","record-status");status.setAttribute("role","status");status.setAttribute("aria-live","polite");
    const controls=el(doc,"div",undefined,"record-controls"),label=el(doc,"label","Choose a table"),select=el(doc,"select");select.id="record-table-select";label.setAttribute("for",select.id);
    for(const [name,spec] of Object.entries(CONFIG.tables)){const option=el(doc,"option",spec.label+" — "+name);option.value=name;select.append(option);}
    select.value="PERSON";select.disabled=true;
    const button=el(doc,"button","Retry preview","button button-secondary");button.type="button";button.hidden=true;
    controls.append(label,select,button);const context=el(doc,"p",undefined,"record-context"),body=el(doc,"div");root.replaceChildren(status,controls,context,body);
    let preview=null,state=null;
    function draw(){if(!preview)return;const table=preview.tables.find(t=>t.name===select.value);body.replaceChildren(renderTable(doc,table,downloads.renderRecordDownloads(doc,state,table.name)));status.textContent=CONFIG.tables[table.name].label+": showing "+(table.rows.length?"rows 1–"+table.rows.length:"0 rows")+" of "+nf.format(table.total_rows)+" records.";}
    select.addEventListener("change",draw);
    async function refresh(){
      root.setAttribute("aria-busy","true");select.disabled=true;button.disabled=true;status.textContent="Verifying demo preview…";body.replaceChildren();context.textContent="";preview=null;
      try{state=await downloads.getDownloadState(doc,options);if(!state.preview)throw new Error('Verified preview unavailable');preview=state.preview;select.disabled=false;button.hidden=true;
        context.textContent="DEMO_ONLY · "+preview.dataset_version+" · Exported "+dateFormat.format(new Date(preview.generated_at))+" UTC · Privacy screening: "+preview.privacy_status+". Demo eligibility is separate from standard privacy clearance.";draw();
      }catch(_){status.textContent="Demo preview unavailable";button.hidden=false;body.append(el(doc,"p","A matching verified DEMO_ONLY manifest and preview are required. The export may be missing, out of date or withdrawn. The project overview and Validation Report remain available; no substitute records or dataset links are shown.","results-notice"));
      }finally{button.disabled=false;root.setAttribute("aria-busy","false");}
    }
    button.addEventListener("click",refresh);await refresh();
  }
  const api={normalizePreview,renderTable,loadPreview,mountRecords};
  if(typeof module!=="undefined"&&module.exports)module.exports=api;else window.SageRecords=api;
  // downloads.js starts both views after the shared verification API is ready.
})();
