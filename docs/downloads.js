/* Version-pinned, verified DEMO_ONLY Release links. No dataset bytes are fetched. */
(() => {
  "use strict";
  const node=typeof module!=="undefined"&&module.exports;
  const catalog=node?require('./records-config.js'):window.SageRecordsConfig;
  const records=node?require('./records.js'):window.SageRecords;
  const REPOSITORY='kovacsphil-art/synthetic_banking',MAX_BYTES=16*1024;
  const ASSETS=[['ZIP','SAGE_DEMO_ONLY.zip'],['DICTIONARY','data_dictionary.md'],...Object.keys(catalog.tables).map(t=>[t,t+'.csv'])];
  const fields=['schema_version','release_mode','baseline','verification','dataset_version','generation_date','exported_at','verified_at','privacy_status','preview_sha256','repository','publication_status','publication_checked_at','assets'];
  const exact=(o,ks)=>o&&typeof o==='object'&&!Array.isArray(o)&&Object.keys(o).length===ks.length&&ks.every(k=>Object.hasOwn(o,k));
  const digest=v=>typeof v==='string'&&/^[0-9a-f]{64}$/.test(v);
  const timestamp=v=>typeof v==='string'&&/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$/.test(v)&&Number.isFinite(Date.parse(v))&&new Date(v).toISOString().slice(0,10)===v.slice(0,10);
  function normalizeManifest(m){
    if(!exact(m,Object.hasOwn(m||{},'download_urls')?[...fields,'download_urls']:fields)||m.schema_version!=='1.0'||m.release_mode!=='DEMO_ONLY'||m.baseline!=='FABRICATED_DEVELOPMENT'||m.verification!=='VERIFIED_DEMO_ONLY'||
      m.repository!==REPOSITORY||typeof m.dataset_version!=='string'||!/^sage-demo-v[1-9][0-9]*(?:\.[0-9]+)*$/.test(m.dataset_version)||
      ![m.generation_date,m.exported_at,m.verified_at].every(timestamp)||Date.parse(m.generation_date)>Date.parse(m.exported_at)||Date.parse(m.exported_at)>Date.parse(m.verified_at)||
      !['PASS','REVIEW_REQUIRED'].includes(m.privacy_status)||!digest(m.preview_sha256)||!['UNPUBLISHED','PUBLISHED','WITHDRAWN'].includes(m.publication_status)||
      (m.publication_status==='PUBLISHED'? !timestamp(m.publication_checked_at)||Date.parse(m.publication_checked_at)<Date.parse(m.verified_at):m.publication_checked_at!==null)||
      !Array.isArray(m.assets)||m.assets.length!==8)throw new Error('Invalid download manifest');
    m.assets.forEach((a,i)=>{const [key,file]=ASSETS[i];if(!exact(a,['key','file','bytes','sha256','rows'])||a.key!==key||a.file!==file||
      !Number.isSafeInteger(a.bytes)||a.bytes<=0||a.bytes>512*1024*1024||!digest(a.sha256)||
      (Object.hasOwn(catalog.tables,key)?!Number.isSafeInteger(a.rows)||a.rows<0||a.rows>250000:a.rows!==null))throw new Error('Invalid download asset');});
    if(Object.hasOwn(m,'download_urls')&&(m.publication_status!=='PUBLISHED'||!exact(m.download_urls,ASSETS.map(a=>a[0]))||
      !ASSETS.every(([key,file])=>m.download_urls[key]===assetUrl(m,file))))throw new Error('Invalid download URLs');
    return m;
  }
  function releaseUrl(m){return 'https://api.github.com/repos/'+REPOSITORY+'/releases/tags/'+m.dataset_version;}
  function assetUrl(m,file){return 'https://github.com/'+REPOSITORY+'/releases/download/'+m.dataset_version+'/'+file;}
  function validateRelease(m,release){
    if(!release||release.tag_name!==m.dataset_version||release.draft!==false||release.prerelease!==false||!timestamp(release.published_at)||!Array.isArray(release.assets)||release.assets.length>100)throw new Error('Release unavailable');
    const urls={};
    for(const expected of m.assets){const matches=release.assets.filter(a=>a.name===expected.file);
      if(matches.length!==1)throw new Error('Release asset unavailable');
      const a=matches[0];if(a.state!=='uploaded'||a.size!==expected.bytes||a.digest!=='sha256:'+expected.sha256||a.browser_download_url!==assetUrl(m,expected.file))throw new Error('Release asset mismatch');
      urls[expected.key]=assetUrl(m,expected.file);
    }return urls;
  }
  async function validatePreview(m,raw,crypto=globalThis.crypto){
    const bytes=new TextEncoder().encode(raw);if(bytes.length>catalog.max_bytes||!crypto?.subtle)throw new Error('Preview verification unavailable');
    const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(v=>v.toString(16).padStart(2,'0')).join('');
    const p=records.normalizePreview(JSON.parse(raw));
    if(hash!==m.preview_sha256||p.dataset_version!==m.dataset_version||p.privacy_status!==m.privacy_status||
      p.tables.some(t=>m.assets.find(a=>a.key===t.name).rows!==t.total_rows))throw new Error('Outdated download export');
    return p;
  }
  async function readText(response,maximum){
    if(!response.ok||Number(response.headers?.get('content-length'))>maximum)throw new Error('Download metadata unavailable');
    let raw='';
    if(response.body?.getReader){const reader=response.body.getReader(),decoder=new TextDecoder('utf-8',{fatal:true});let size=0;
      try{while(true){const {done,value}=await reader.read();if(done)break;size+=value.byteLength;if(size>maximum){await reader.cancel();throw new Error('Download metadata exceeds limit');}raw+=decoder.decode(value,{stream:true});}raw+=decoder.decode();}finally{reader.releaseLock();}
    }else raw=await response.text();
    if(new TextEncoder().encode(raw).length>maximum)throw new Error('Download metadata exceeds limit');return raw;
  }
  async function verifyRelease(m,{fetcher=globalThis.fetch,signal}={}){
    const response=await fetcher(releaseUrl(m),{credentials:'omit',cache:'no-store',redirect:'error',signal,headers:{Accept:'application/vnd.github+json'}});
    return validateRelease(m,JSON.parse(await readText(response,128*1024)));
  }
  async function loadDownloadState(doc,{fetcher=globalThis.fetch,location=globalThis.location,crypto=globalThis.crypto,timeoutMs=10000}={}){
    const controller=new AbortController();let timer;
    const work=(async()=>{
      function local(name){const url=new URL(name,doc.baseURI);if(!['http:','https:'].includes(url.protocol)||url.origin!==location.origin)throw new Error('Invalid download metadata origin');return url.href;}
      const options={credentials:'omit',cache:'no-store',redirect:'error',signal:controller.signal};
      let manifest;
      try{manifest=normalizeManifest(JSON.parse(await readText(await fetcher(local('dataset-downloads.json'),options),MAX_BYTES)));}catch(_){return {status:'unavailable'};}
      let raw;
      try{raw=await readText(await fetcher(local('demo-preview.json'),options),catalog.max_bytes);}catch(_){return {status:'preview_unavailable'};}
      try{await validatePreview(manifest,raw,crypto);}catch(_){return {status:'outdated'};}
      // The current report must explicitly identify this exact demo cohort.
      let report;
      try{report=JSON.parse(await readText(await fetcher(local('latest-pipeline.json'),options),1024*1024));}
      catch(_){return {status:'outdated'};}
      if(report.validation?.status!=='PASS'||report.demo_dataset?.release_mode!=='DEMO_ONLY'||
        report.demo_dataset?.dataset_version!==manifest.dataset_version||report.demo_dataset?.preview_sha256!==manifest.preview_sha256||
        report.privacy?.status!==manifest.privacy_status||!manifest.assets.slice(2).every(a=>report.generation?.table_rows?.some(r=>r.table===a.key&&r.status==='AVAILABLE'&&r.value===a.rows)))return {status:'outdated'};
      if(manifest.publication_status==='UNPUBLISHED')return {status:'unpublished',manifest};
      if(manifest.publication_status==='WITHDRAWN')return {status:'withdrawn',manifest};
      try{return {status:'ready',manifest,urls:await verifyRelease(manifest,{fetcher,signal:controller.signal})};}
      catch(_){return {status:'release_unavailable',manifest};}
    })();
    try{return await Promise.race([work,new Promise(resolve=>{timer=setTimeout(()=>{controller.abort();resolve({status:'unavailable'});},timeoutMs);})]);}
    finally{clearTimeout(timer);}
  }
  const fmt=new Intl.NumberFormat('en',{maximumFractionDigits:1});
  function size(bytes){return Number.isSafeInteger(bytes)?bytes>=1e6?fmt.format(bytes/1e6)+' MB':bytes>=1000?fmt.format(bytes/1000)+' KB':bytes+' B':'Size unavailable';}
  function el(doc,tag,text,cls){const n=doc.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
  const STATES={loading:['Checking download availability…','Verifying the demo version and publication status.'],
    unavailable:['Downloads unavailable','A verified demo download manifest is not available. No dataset links are enabled.'],
    preview_unavailable:['Downloads unavailable','The demo preview could not be verified. Downloads stay disabled until the matching version is available.'],
    outdated:['Downloads out of date','The export does not match the current pipeline report and demo preview. A matching verified version is required.'],
    unpublished:['Verified demo export — not published','The demo files have been verified, but have not been published as Release assets. Downloads are not enabled yet.'],
    withdrawn:['Downloads withdrawn','Downloads for this demo version have been withdrawn.'],
    release_unavailable:['Downloads temporarily unavailable','The versioned Release files could not be confirmed. A file may be missing, changed, or temporarily inaccessible. Recheck availability.'],
    ready:['Demo downloads available','The published Release files match the verified demo export and this preview.']};
  function renderDownloads(doc,state){
    const root=el(doc,'div'),[title,note]=STATES[state.status]||STATES.unavailable,m=state.manifest,ready=state.status==='ready';root.dataset.downloadState=state.status;
    const heading=el(doc,'p',title,'download-status');heading.id='dataset-download-status';heading.setAttribute('role','status');heading.setAttribute('aria-live','polite');root.append(heading,el(doc,'p',note,'download-note'));
    function control(key,label,cls){const item=m?.assets.find(a=>a.key===key),url=ready&&state.urls?.[key];
      const node=el(doc,url?'a':'button',label,cls||'button button-secondary');
      if(url){node.setAttribute('href',url);node.setAttribute('download',item.file);node.setAttribute('rel','noopener noreferrer');}
      else{node.type='button';node.disabled=true;node.setAttribute('aria-describedby',heading.id);}
      if(Object.hasOwn(catalog.tables,key))node.setAttribute('aria-label','Download '+catalog.tables[key].label+' CSV');return node;}
    if(m){root.append(el(doc,'p','DEMO_ONLY · '+m.dataset_version+' · Privacy screening: '+m.privacy_status+'. Demo eligibility is separate from the standard privacy release status in the Validation Report. This is not formal anonymization certification.','download-context'));}
    const bundle=el(doc,'div',undefined,'download-bundle'),zip=m?.assets.find(a=>a.key==='ZIP'),dictionary=m?.assets.find(a=>a.key==='DICTIONARY');
    bundle.append(el(doc,'div',undefined,'download-bundle-copy'));
    const copy=bundle.children[0];copy.append(el(doc,'h3','The complete six-table demo'),el(doc,'p','One ZIP with all six CSVs, the data dictionary and generation metadata.'),
      el(doc,'p',zip?size(zip.bytes)+' · '+new Intl.NumberFormat('en').format(m.assets.reduce((n,a)=>n+(a.rows||0),0))+' records across six tables':'ZIP size and record counts unavailable','download-size'));
    const actions=el(doc,'div',undefined,'download-bundle-actions');actions.append(control('ZIP','Download complete dataset (ZIP)','button button-primary'),control('DICTIONARY','Download data dictionary'),
      el(doc,'span',dictionary?'Dictionary · '+size(dictionary.bytes):'Dictionary size unavailable','download-size'));bundle.append(actions);root.append(bundle);
    const grid=el(doc,'div',undefined,'download-files');
    for(const [name,spec] of Object.entries(catalog.tables)){const file=m?.assets.find(a=>a.key===name),card=el(doc,'article',undefined,'download-file');
      card.append(el(doc,'h3',spec.label),el(doc,'code',name+'.csv'),el(doc,'p',spec.description),
        el(doc,'p',file?new Intl.NumberFormat('en').format(file.rows)+' records · '+size(file.bytes):'Record count and size unavailable','download-file-facts'),
        control(name,'Download CSV'));grid.append(card);
    }root.append(grid,el(doc,'p','Release links are pinned to the displayed demo version. Missing or mismatched assets disable the complete set of download controls.','download-note'));
    return root;
  }
  async function mountDownloads(doc,options={}){
    const root=doc.getElementById('dataset-downloads');if(!root)return;
    async function refresh(){root.setAttribute('aria-busy','true');root.replaceChildren(renderDownloads(doc,{status:'loading'}));
      const state=await loadDownloadState(doc,options);const view=renderDownloads(doc,state),button=el(doc,'button','Recheck availability','button button-secondary');button.type='button';button.addEventListener('click',refresh);view.append(button);root.replaceChildren(view);root.setAttribute('aria-busy','false');}
    await refresh();
  }
  const api={REPOSITORY,ASSETS,normalizeManifest,assetUrl,releaseUrl,validateRelease,validatePreview,verifyRelease,loadDownloadState,renderDownloads,mountDownloads};
  if(node)module.exports=api;else window.SageDownloads=api;
  if(typeof document!=='undefined')mountDownloads(document);
})();
