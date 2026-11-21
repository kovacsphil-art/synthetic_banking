"use strict";
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const {createHash,webcrypto}=require('node:crypto');
const config=require('../docs/records-config.js');
const {normalizePreview,renderTable,mountRecords,loadPreview}=require('../docs/records.js');
function fixture(){return {schema_version:'1.0',release_mode:'DEMO_ONLY',baseline:'FABRICATED_DEVELOPMENT',dataset_version:'sage-demo-v1.1',
  generated_at:'2026-01-01T00:00:00+00:00',privacy_status:'REVIEW_REQUIRED',preview_row_limit:15,
  tables:Object.entries(config.tables).map(([name,spec])=>({name,total_rows:100,total_columns:spec.total_columns,columns:spec.columns.map(c=>c.key),
    rows:Array.from({length:15},(_,i)=>spec.columns.map(c=>({person_id:'P'+String(i+1).padStart(8,'0'),account_id:'A'+String(i+1).padStart(9,'0'),
      tradeline_id:'TL'+String(i+1).padStart(10,'0'),code:'A',number:i+100,date:'2026-09-30T00:00:00'}[c.kind])))}))};}
class Node {
  constructor(doc,tag){this.ownerDocument=doc;this.tagName=tag.toUpperCase();this.children=[];this.attributes={};this.events={};this.dataset={};this._text='';}
  set textContent(value){this._text=String(value);this.children=[];}
  get textContent(){return this._text+this.children.map(n=>n.textContent).join(' ');}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=nodes;this._text='';}
  setAttribute(k,v){this.attributes[k]=String(v);}
  addEventListener(k,v){this.events[k]=v;}
}
function all(node){return [node,...node.children.flatMap(all)];}
function document(){const doc={baseURI:'https://example.invalid/sage/index.html'};doc.createElement=t=>new Node(doc,t);const root=new Node(doc,'div');doc.getElementById=id=>id==='records-explorer'?root:null;return {doc,root};}
const location={origin:'https://example.invalid'};
const response=data=>({ok:true,text:async()=>JSON.stringify(data)});
function verifiedTransport(calls=[],status='PUBLISHED'){
  const downloads=require('../docs/downloads.js'),preview=fixture();
  const m={schema_version:'1.0',release_mode:'DEMO_ONLY',baseline:'FABRICATED_DEVELOPMENT',verification:'VERIFIED_DEMO_ONLY',dataset_version:preview.dataset_version,
    generation_date:preview.generated_at,exported_at:preview.generated_at,verified_at:preview.generated_at,privacy_status:preview.privacy_status,
    preview_sha256:createHash('sha256').update(JSON.stringify(preview)).digest('hex'),repository:downloads.REPOSITORY,publication_status:status,
    publication_checked_at:status==='PUBLISHED'?preview.generated_at:null,assets:downloads.ASSETS.map(([key,file],i)=>({key,file,bytes:1000+i,sha256:String(i).repeat(64),rows:Object.hasOwn(config.tables,key)?100:null}))};
  const report={validation:{status:'PASS'},privacy:{status:m.privacy_status},demo_dataset:{dataset_version:m.dataset_version,release_mode:'DEMO_ONLY',preview_sha256:m.preview_sha256},generation:{table_rows:m.assets.slice(2).map(a=>({table:a.key,status:'AVAILABLE',value:a.rows}))}};
  const release={tag_name:m.dataset_version,draft:false,prerelease:false,published_at:m.verified_at,assets:m.assets.map(a=>({name:a.file,size:a.bytes,state:'uploaded',digest:'sha256:'+a.sha256,browser_download_url:downloads.assetUrl(m,a.file)}))};
  return async(url,options)=>{calls.push([url,options]);return response(url.endsWith('/dataset-downloads.json')?m:url.endsWith('/demo-preview.json')?preview:url.endsWith('/latest-pipeline.json')?report:release);};
}

test('bounded preview has six tables, selected columns and synthetic keys only',()=>{
  const p=normalizePreview(fixture());assert.equal(p.tables.length,6);assert.equal(p.tables.reduce((n,t)=>n+t.rows.length,0),90);
  assert.equal(p.tables.find(t=>t.name==='TKQ_ACCOUNT').total_columns,100);
  assert.equal(p.tables.find(t=>t.name==='TKQ_ACCOUNT').columns.length,8);
});
test('full datasets, unknown metadata, source identifiers and unsafe cell values are rejected',()=>{
  for(const mutate of [r=>r.source_run_id='PRIVATE',r=>r.tables[0].rows.push(r.tables[0].rows[0]),r=>r.tables[0].rows[0][0]='P0000000001',
    r=>r.tables[0].rows[0][1]='private@example.invalid',r=>r.tables[0].rows[0][1]='AKIA'+'A'.repeat(16),r=>r.tables[0].rows[0][1]='<script>PRIVATE</script>',
    r=>r.tables[3].rows[0][4]='PRIVATE',r=>r.tables[3].rows[0][4]=Infinity,r=>r.tables[0].total_columns=999,r=>r.tables[0].columns[0]='EMAIL',
    r=>r.tables[0].rows[0][0]=null,r=>r.privacy_status='PASSED',r=>r.baseline='PRODUCTION',r=>r.tables[3].rows[0][6]='2026-02-30',
    r=>r.generated_at='2026-02-30T00:00:00Z',r=>r.tables[0].file='/data/full.csv']){
    const r=fixture();mutate(r);assert.throws(()=>normalizePreview(r),/Invalid/);
  }
});
test('each table renders counts, column descriptions, relationships and an accessible scroll region',()=>{
  const {doc}=document(),p=normalizePreview(fixture());
  for(const table of p.tables){const node=renderTable(doc,table),nodes=all(node);assert.match(node.textContent,/Records in full table/);assert.match(node.textContent,/Columns in full table/);
    assert.ok(node.textContent.includes(config.tables[table.name].relationship));assert.ok(nodes.some(n=>n.tagName==='DETAILS'));
    assert.equal(nodes.filter(n=>n.tagName==='TR').length,16);assert.equal(nodes.filter(n=>n.attributes.scope==='row').length,15);
    assert.ok(nodes.some(n=>n.attributes.role==='region'&&n.tabIndex===0&&n.attributes['aria-describedby']));
    assert.ok(node.textContent.includes(config.tables[table.name].columns[0].description));
    assert.equal(nodes.filter(n=>n.className==='record-id-value').length,15*config.tables[table.name].columns.filter(c=>c.kind.endsWith('_id')).length);
    assert.ok(nodes.filter(n=>n.attributes.scope==='col').every(n=>n.attributes['aria-describedby']));
  }
});
test('missing values are visible as not recorded and empty tables do not invent rows',()=>{
  const {doc}=document(),p=fixture();p.tables[2].rows[0][4]=null;
  assert.match(renderTable(doc,normalizePreview(p).tables[2]).textContent,/Not recorded/);
  p.tables[0].total_rows=0;p.tables[0].rows=[];
  assert.match(renderTable(doc,normalizePreview(p).tables[0]).textContent,/No records/);
});
test('table selection reuses verified bounded metadata and updates CSV links without requesting dataset bytes',async()=>{
  const {doc,root}=document();let calls=[];
  await mountRecords(doc,{location,crypto:webcrypto,fetcher:verifiedTransport(calls)});
  const select=all(root).find(n=>n.tagName==='SELECT');assert.equal(select.disabled,false);
  for(const name of Object.keys(config.tables)){select.value=name;select.events.change();assert.ok(root.textContent.includes(config.tables[name].label));
    const links=all(root).filter(n=>n.tagName==='A');assert.equal(links.length,2);assert.ok(links[0].attributes.href.endsWith('/sage-demo-v1.1/'+name+'.csv'));assert.ok(links[1].attributes.href.endsWith('/SAGE_DEMO_ONLY.zip'));}
  assert.equal(calls.length,4);assert.ok(calls.every(([url])=>!url.endsWith('.csv')&&!url.endsWith('.zip')));
  assert.equal(calls[0][1].credentials,'omit');assert.equal(calls[0][1].redirect,'error');
  assert.match(root.textContent,/rows 1–15/);assert.match(root.textContent,/REVIEW_REQUIRED/);assert.match(root.textContent,/same verified DEMO_ONLY version/);
});
test('missing or invalid JSON clears data, offers retry and never displays payloads',async()=>{
  const {doc,root}=document();let valid=false;
  const transport=verifiedTransport();await mountRecords(doc,{location,crypto:webcrypto,fetcher:(...args)=>valid?transport(...args):Promise.resolve({ok:false,text:async()=>'PRIVATE'})});
  assert.match(root.textContent,/Demo preview unavailable/);assert.ok(!root.textContent.includes('PRIVATE'));assert.equal(all(root).filter(n=>n.tagName==='TABLE').length,0);
  const retry=all(root).find(n=>n.tagName==='BUTTON');assert.equal(retry.hidden,false);valid=true;await retry.events.click();assert.equal(retry.hidden,true);
  assert.equal(all(root).filter(n=>n.tagName==='TABLE').length,1);
});
test('cross-origin, CSV, file URLs, oversize data and stalled requests fail safely',async()=>{
  const {doc}=document();let called=false;
  for(const url of ['https://private.invalid/demo-preview.json','full.csv','file:///preview.json'])await assert.rejects(loadPreview(doc,async()=>{called=true;},location,url,20));
  assert.equal(called,false);
  await assert.rejects(loadPreview(doc,async()=>({ok:true,text:async()=>' '.repeat(config.max_bytes+1)}),location,'demo-preview.json',20));
  await assert.rejects(loadPreview(doc,async()=>new Promise(()=>{}),location,'demo-preview.json',5),/timed out/);
});
test('explorer keeps measured validation separate and never fetches full datasets itself',()=>{
  const html=fs.readFileSync(require.resolve('../docs/index.html'),'utf8');
  assert.match(html,/Demo data — not actual customer records/);assert.match(html,/id="explore-records"/);assert.match(html,/records-config.js/);assert.match(html,/records.js/);
  const js=fs.readFileSync(require.resolve('../docs/records.js'),'utf8');assert.doesNotMatch(js,/innerHTML|SageValidation|latest-pipeline\.json|\.csv["']|\.zip["']/);assert.match(js,/getDownloadState/);
});

test('unpublished verified previews retain rows with disabled links; withdrawn or missing manifests hide records',async()=>{
  for(const status of ['UNPUBLISHED','WITHDRAWN']){
    const {doc,root}=document();await mountRecords(doc,{location,crypto:webcrypto,fetcher:verifiedTransport([],status)});
    assert.equal(all(root).filter(n=>n.tagName==='A').length,0);
    assert.equal(all(root).filter(n=>n.tagName==='TABLE').length,status==='UNPUBLISHED'?1:0);
    if(status==='UNPUBLISHED')assert.equal(all(root).filter(n=>n.tagName==='BUTTON'&&n.disabled).length,2);
  }
});

test('preview and downloads share in-flight verification but retries perform fresh checks',async()=>{
  const downloads=require('../docs/downloads.js'),{doc,root}=document(),calls=[],downloadRoot=new Node(doc,'div');
  doc.getElementById=id=>id==='records-explorer'?root:id==='dataset-downloads'?downloadRoot:null;
  const options={location,crypto:webcrypto,fetcher:verifiedTransport(calls)};
  await Promise.all([mountRecords(doc,options),downloads.mountDownloads(doc,options)]);assert.equal(calls.length,4);
  assert.equal(all(root).filter(n=>n.tagName==='TABLE').length,1);assert.equal(all(downloadRoot).filter(n=>n.tagName==='A').length,8);
  await downloads.getDownloadState(doc,options);assert.equal(calls.length,8);
});

test('mismatched preview fingerprints or current report provenance never render records or links',async()=>{
  for(const path of ['/demo-preview.json','/latest-pipeline.json']){
    const {doc,root}=document(),transport=verifiedTransport();
    await mountRecords(doc,{location,crypto:webcrypto,fetcher:async(url,options)=>{
      const res=await transport(url,options);if(!url.endsWith(path))return res;
      const value=JSON.parse(await res.text());if(path==='/demo-preview.json')value.tables[0].rows[0][1]='B';else value.demo_dataset.dataset_version='sage-demo-v999';return response(value);
    }});
    assert.equal(all(root).filter(n=>n.tagName==='TABLE'||n.tagName==='A').length,0);assert.match(root.textContent,/matching verified DEMO_ONLY manifest/);
  }
});

test('Release API failures retain verified preview rows but cannot enable download links',async()=>{
  const {doc,root}=document(),transport=verifiedTransport();await mountRecords(doc,{location,crypto:webcrypto,fetcher:(url,o)=>url.startsWith('https://api.github.com')?Promise.resolve({ok:false}):transport(url,o)});
  assert.equal(all(root).filter(n=>n.tagName==='TABLE').length,1);assert.equal(all(root).filter(n=>n.tagName==='A').length,0);assert.match(root.textContent,/temporarily unavailable/);
});
test('oversize streamed responses are cancelled before the rest of a file is read',async()=>{
  const {doc}=document();let reads=0,cancelled=false,released=false;
  const reader={read:async()=>{reads++;return {done:false,value:new Uint8Array(config.max_bytes+1)};},cancel:async()=>{cancelled=true;},releaseLock:()=>{released=true;}};
  await assert.rejects(loadPreview(doc,async()=>({ok:true,body:{getReader:()=>reader}}),location,'demo-preview.json',100),/exceeds limit/);
  assert.equal(reads,1);assert.equal(cancelled,true);assert.equal(released,true);
});
