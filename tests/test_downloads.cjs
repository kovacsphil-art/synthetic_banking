"use strict";
const test=require('node:test'),assert=require('node:assert/strict'),{createHash,webcrypto}=require('node:crypto');
const catalog=require('../docs/records-config.js'),downloads=require('../docs/downloads.js');
function fixture(status='PUBLISHED'){
  const preview={schema_version:'1.0',release_mode:'DEMO_ONLY',baseline:'FABRICATED_DEVELOPMENT',dataset_version:'sage-demo-v1.1',
    generated_at:'2026-01-01T01:00:00Z',privacy_status:'REVIEW_REQUIRED',preview_row_limit:15,
    tables:Object.entries(catalog.tables).map(([name,s])=>({name,total_rows:100,total_columns:s.total_columns,columns:s.columns.map(c=>c.key),
      rows:Array.from({length:15},(_,i)=>s.columns.map(c=>({person_id:'P'+String(i+1).padStart(8,'0'),account_id:'A'+String(i+1).padStart(9,'0'),
        tradeline_id:'TL'+String(i+1).padStart(10,'0'),code:'A',number:100,date:'2026-09-30T00:00:00'}[c.kind])))}))};
  const raw=JSON.stringify(preview),m={schema_version:'1.0',release_mode:'DEMO_ONLY',baseline:'FABRICATED_DEVELOPMENT',verification:'VERIFIED_DEMO_ONLY',
    dataset_version:preview.dataset_version,generation_date:'2026-01-01T00:00:00Z',exported_at:'2026-01-01T01:00:00Z',verified_at:'2026-01-01T02:00:00Z',
    privacy_status:'REVIEW_REQUIRED',preview_sha256:createHash('sha256').update(raw).digest('hex'),repository:downloads.REPOSITORY,
    publication_status:status,publication_checked_at:status==='PUBLISHED'?'2026-01-01T03:00:00Z':null,
    assets:downloads.ASSETS.map(([key,file],i)=>({key,file,bytes:1000+i,sha256:String(i).repeat(64),rows:Object.hasOwn(catalog.tables,key)?100:null}))};
  const release={tag_name:m.dataset_version,draft:false,prerelease:false,published_at:'2026-01-01T03:00:00Z',assets:m.assets.map(a=>({name:a.file,size:a.bytes,
    state:'uploaded',digest:'sha256:'+a.sha256,browser_download_url:downloads.assetUrl(m,a.file)}))};
  const report={validation:{status:'PASS'},privacy:{status:m.privacy_status},demo_dataset:{dataset_version:m.dataset_version,release_mode:'DEMO_ONLY',preview_sha256:m.preview_sha256},generation:{table_rows:m.assets.slice(2).map(a=>({table:a.key,status:'AVAILABLE',value:a.rows}))}};
  return {m,raw,preview,release,report};
}
class Node{
  constructor(doc,tag){this.ownerDocument=doc;this.tagName=tag.toUpperCase();this.children=[];this.attributes={};this.dataset={};this.events={};this._text='';}
  set textContent(t){this._text=String(t);this.children=[];}get textContent(){return this._text+this.children.map(c=>c.textContent).join(' ');}
  append(...items){this.children.push(...items);}replaceChildren(...items){this.children=items;this._text='';}
  setAttribute(k,v){this.attributes[k]=String(v);}addEventListener(k,v){this.events[k]=v;}
}
function all(n){return [n,...n.children.flatMap(all)];}
function document(){const d={baseURI:'https://example.invalid/sage/index.html'};d.createElement=t=>new Node(d,t);const root=new Node(d,'div');d.getElementById=id=>id==='dataset-downloads'?root:null;return {d,root};}
const location={origin:'https://example.invalid'},response=value=>({ok:true,text:async()=>typeof value==='string'?value:JSON.stringify(value)});
function transport(f,calls=[]){return async(url,options)=>{calls.push([url,options]);return response(url.endsWith('/dataset-downloads.json')?f.m:url.endsWith('/demo-preview.json')?f.raw:url.endsWith('/latest-pipeline.json')?f.report:f.release);};}

test('ready downloads use exact HTTPS versioned Release URLs and never fetch dataset bytes',async()=>{
  const f=fixture(),calls=[],{d}=document();
  const state=await downloads.loadDownloadState(d,{location,crypto:webcrypto,fetcher:transport(f,calls)});
  assert.equal(state.status,'ready');assert.equal(Object.keys(state.urls).length,8);assert.equal(calls.length,4);
  assert.equal(calls[3][0],'https://api.github.com/repos/'+downloads.REPOSITORY+'/releases/tags/sage-demo-v1.1');
  assert.ok(calls.every(([url,o])=>!url.endsWith('.zip')&&!url.endsWith('.csv')&&o.credentials==='omit'&&o.redirect==='error'));
  for(const url of Object.values(state.urls)){assert.ok(url.startsWith('https://github.com/'+downloads.REPOSITORY+'/releases/download/sage-demo-v1.1/'));assert.ok(!url.includes('/latest/'));}
});
test('unpublished verified exports show metadata with all eight controls disabled and no public API call',async()=>{
  const f=fixture('UNPUBLISHED'),calls=[],{d}=document();
  const state=await downloads.loadDownloadState(d,{location,crypto:webcrypto,fetcher:transport(f,calls)});assert.equal(state.status,'unpublished');assert.equal(calls.length,3);
  const view=downloads.renderDownloads(d,state);assert.match(view.textContent,/not published/);assert.match(view.textContent,/REVIEW_REQUIRED/);
  assert.equal(all(view).filter(n=>n.tagName==='BUTTON'&&n.disabled).length,8);assert.equal(all(view).filter(n=>n.tagName==='A').length,0);
  for(const s of Object.values(catalog.tables))assert.ok(view.textContent.includes(s.description));assert.match(view.textContent,/100 records/);
});
test('wrong version, preview hash, table counts or privacy status mark exports outdated',async()=>{
  for(const mutate of [f=>f.m.dataset_version='sage-demo-v2',f=>f.m.preview_sha256='f'.repeat(64),f=>f.m.assets[2].rows=99,f=>f.m.privacy_status='PASS']){
    const f=fixture(),{d}=document();mutate(f);const calls=[];
    const state=await downloads.loadDownloadState(d,{location,crypto:webcrypto,fetcher:transport(f,calls)});assert.equal(state.status,'outdated');assert.equal(calls.length,2);
    assert.equal(all(downloads.renderDownloads(d,state)).filter(n=>n.tagName==='A').length,0);
  }
});
test('missing assets, changed bytes or SHA, drafts, wrong tags and foreign download URLs disable the whole set',async()=>{
  for(const mutate of [f=>f.release.assets.pop(),f=>f.release.assets[0].size++,f=>f.release.assets[0].digest=null,f=>f.release.assets[0].digest='sha256:'+'f'.repeat(64),
    f=>f.release.draft=true,f=>f.release.prerelease=true,f=>f.release.tag_name='sage-demo-v2',f=>f.release.assets[0].browser_download_url='https://private.invalid/file.zip',
    f=>f.release.assets.push(f.release.assets[0])]){
    const f=fixture(),{d}=document();mutate(f);const state=await downloads.loadDownloadState(d,{location,crypto:webcrypto,fetcher:transport(f)});
    assert.equal(state.status,'release_unavailable');assert.equal(all(downloads.renderDownloads(d,state)).filter(n=>n.tagName==='A').length,0);
  }
});
test('unverified origins, internal metadata and arbitrary asset names cannot become links',()=>{
  for(const mutate of [m=>m.location='/Volumes/private',m=>m.release_mode='PUBLIC',m=>m.baseline='PRODUCTION',m=>m.verification='APPROVED',
    m=>m.repository='attacker/other',m=>m.assets[0].url='http://private',m=>m.assets[0].file='../source.zip',m=>m.assets[2].rows=true,m=>m.verified_at='2026-02-30T00:00:00Z']){
    const {m}=fixture();mutate(m);assert.throws(()=>downloads.normalizeManifest(m),/Invalid/);
  }
});
test('enabled links provide ZIP, dictionary and six labelled CSV downloads',async()=>{
  const f=fixture(),{d}=document(),state=await downloads.loadDownloadState(d,{location,crypto:webcrypto,fetcher:transport(f)});
  const view=downloads.renderDownloads(d,state),links=all(view).filter(n=>n.tagName==='A');assert.equal(links.length,8);
  assert.equal(links.filter(n=>n.attributes.download.endsWith('.csv')).length,6);assert.ok(links.some(n=>n.attributes.download==='data_dictionary.md'));
  assert.ok(links.some(n=>n.textContent==='Download complete dataset (ZIP)'));assert.ok(links.filter(n=>n.attributes.download.endsWith('.csv')).every(n=>n.attributes['aria-label']));
});

test('package guide explains included metadata, imports and relationships without adding unverified URLs',async()=>{
  const f=fixture(),{d}=document(),state=await downloads.loadDownloadState(d,{location,crypto:webcrypto,fetcher:transport(f)});
  const view=downloads.renderDownloads(d,state),nodes=all(view),guide=nodes.find(n=>n.className==='download-guide');
  assert.equal(guide.children[0].textContent,'Using the demo files');assert.equal(guide.open,undefined);
  for(const phrase of ['metadata.json','random seed','file checksums','both Account ID and Effective date','Import identifiers as text','\\N means a missing value','Related records can fall outside the preview'])assert.ok(guide.textContent.includes(phrase));
  assert.equal(all(guide).filter(n=>n.tagName==='DT').length,4);
  const times=nodes.filter(n=>n.tagName==='TIME');assert.deepEqual(times.map(n=>n.attributes.datetime),[f.m.generation_date,f.m.verified_at]);
  assert.ok(times.every(n=>n.textContent.endsWith('UTC')));assert.equal(nodes.filter(n=>n.tagName==='A').length,8);
});

test('unavailable packages never invent dates or bypass disabled controls through the guide',()=>{
  const {d}=document(),view=downloads.renderDownloads(d,{status:'unavailable'}),nodes=all(view);
  assert.equal(nodes.filter(n=>n.tagName==='TIME'||n.tagName==='A').length,0);
  assert.equal(nodes.filter(n=>n.tagName==='BUTTON'&&n.disabled).length,8);
  assert.ok(nodes.some(n=>n.className==='download-guide'));
});
test('missing manifests, rate limits and timeouts fail safely without displaying response content',async()=>{
  const {d,root}=document();await downloads.mountDownloads(d,{location,crypto:webcrypto,fetcher:async()=>({ok:false,text:async()=>'PRIVATE_SOURCE_RECORD'})});
  assert.match(root.textContent,/Downloads unavailable/);assert.ok(!root.textContent.includes('PRIVATE'));assert.equal(all(root).filter(n=>n.tagName==='A').length,0);
  const f=fixture();const state=await downloads.loadDownloadState(d,{location,crypto:webcrypto,fetcher:async(url,o)=>url.startsWith('https://api.github.com')?{ok:false}:transport(f)(url,o)});
  assert.equal(state.status,'release_unavailable');
  assert.equal((await downloads.loadDownloadState(d,{location,timeoutMs:5,fetcher:async()=>new Promise(()=>{})})).status,'unavailable');
});
test('withdrawn exports stay disabled; HTTP/local file origins cannot supply metadata',async()=>{
  const {d}=document();const f=fixture('WITHDRAWN'),calls=[];
  assert.equal((await downloads.loadDownloadState(d,{location,crypto:webcrypto,fetcher:transport(f,calls)})).status,'withdrawn');assert.equal(calls.length,3);
  d.baseURI='file:///index.html';let fetched=false;
  assert.equal((await downloads.loadDownloadState(d,{location,fetcher:async()=>{fetched=true;}})).status,'unavailable');assert.equal(fetched,false);
});

test('latest report must identify the exact demo version, preview and six table counts',async()=>{
  for(const change of [f=>delete f.report.demo_dataset,f=>f.report.demo_dataset.dataset_version='sage-demo-v999',
    f=>f.report.demo_dataset.preview_sha256='f'.repeat(64),f=>f.report.generation.table_rows[0].value++,f=>f.report.privacy.status='PASS']){
    const f=fixture(),{d}=document();change(f);const calls=[];
    const state=await downloads.loadDownloadState(d,{location,crypto:webcrypto,fetcher:transport(f,calls)});
    assert.equal(state.status,'outdated');assert.equal(calls.length,3);assert.equal(all(downloads.renderDownloads(d,state)).filter(n=>n.tagName==='A').length,0);
  }
});

test('published manifest URLs must exactly match all eight canonical versioned assets',()=>{
  const {m}=fixture();m.download_urls=Object.fromEntries(downloads.ASSETS.map(([k,f])=>[k,downloads.assetUrl(m,f)]));
  assert.equal(downloads.normalizeManifest(m).download_urls.ZIP,downloads.assetUrl(m,'SAGE_DEMO_ONLY.zip'));
  m.download_urls.PERSON='https://private.invalid/source.csv';assert.throws(()=>downloads.normalizeManifest(m),/Invalid download URLs/);
});
