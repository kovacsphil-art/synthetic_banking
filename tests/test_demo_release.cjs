'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),{createHash}=require('node:crypto');
const {publishDemo}=require('../scripts/publish_demo_release.cjs'),downloads=require('../docs/downloads.js');
const hash=b=>createHash('sha256').update(b).digest('hex');
function fixture(){
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'sage-fabricated-release-')),folder=path.join(root,'incoming'),docs=path.join(root,'docs');fs.mkdirSync(folder);fs.mkdirSync(docs);
  const raw=fs.readFileSync(path.join(__dirname,'../docs/demo-preview.json'));
  const preview=JSON.parse(raw),m={schema_version:'1.0',release_mode:'DEMO_ONLY',baseline:'FABRICATED_DEVELOPMENT',verification:'VERIFIED_DEMO_ONLY',
    dataset_version:preview.dataset_version,generation_date:'2026-01-01T00:00:00Z',exported_at:'2026-01-01T01:00:00Z',verified_at:'2026-01-01T02:00:00Z',
    privacy_status:preview.privacy_status,preview_sha256:hash(raw),repository:downloads.REPOSITORY,publication_status:'UNPUBLISHED',publication_checked_at:null,
    assets:downloads.ASSETS.map(([key,file])=>{const content=Buffer.from('fabricated test '+file);fs.writeFileSync(path.join(folder,file),content);return {key,file,bytes:content.length,sha256:hash(content),rows:preview.tables.find(t=>t.name===key)?.total_rows??null};})};
  fs.writeFileSync(path.join(folder,'demo-preview.json'),raw);fs.writeFileSync(path.join(folder,'dataset-downloads.json'),JSON.stringify(m));
  const report={validation:{status:'PASS'},privacy:{status:m.privacy_status},demo_dataset:{dataset_version:m.dataset_version,release_mode:'DEMO_ONLY',preview_sha256:m.preview_sha256},
    generation:{table_rows:m.assets.slice(2).map(a=>({table:a.key,status:'AVAILABLE',value:a.rows}))}};
  fs.writeFileSync(path.join(docs,'latest-pipeline.json'),JSON.stringify(report));
  fs.writeFileSync(path.join(docs,'dataset-downloads.json'),'previous-valid-downloads');fs.writeFileSync(path.join(docs,'demo-preview.json'),'previous-valid-preview');
  let release=null;const calls=[];
  async function api(method,url,body,file){calls.push({method,url,body,file});
    if(method==='GET')return release;
    if(method==='POST'&&!file){release={id:12,tag_name:body.tag_name,draft:true,prerelease:false,published_at:null,assets:[]};return release;}
    if(file){const expected=m.assets.find(a=>a.file===path.basename(file));release.assets.push({name:expected.file,size:expected.bytes,digest:'sha256:'+expected.sha256,state:'uploaded',browser_download_url:downloads.assetUrl(m,expected.file)});return release.assets.at(-1);}
    if(method==='PATCH'){release.draft=false;release.published_at=new Date().toISOString();return release;}
    throw Error('Unexpected API call');
  }
  return {root,folder,docs,m,report,calls,api,release:()=>release,options:()=>({folder,docs,commit:'a'.repeat(40),api}),cleanup:()=>fs.rmSync(root,{recursive:true,force:true})};
}
test('whole verified set stays draft until eight uploads and checks finish; only metadata reaches docs',async()=>{
  const f=fixture();try{
    const published=await publishDemo(f.options());assert.equal(published.publication_status,'PUBLISHED');assert.equal(published.privacy_status,'REVIEW_REQUIRED');
    assert.equal(f.calls.filter(c=>c.file).length,8);const patch=f.calls.findIndex(c=>c.method==='PATCH');assert.ok(f.calls.slice(0,patch).filter(c=>c.file).length===8);
    assert.equal(f.calls.find(c=>c.method==='POST'&&!c.file).body.draft,true);
    assert.deepEqual(fs.readdirSync(f.docs).sort(),['dataset-downloads.json','demo-preview.json','latest-pipeline.json']);
    assert.deepEqual(JSON.parse(fs.readFileSync(path.join(f.docs,'dataset-downloads.json'))),published);
  }finally{f.cleanup();}
});
test('missing or changed local bytes and report lineage mismatch stop before any network mutation',async()=>{
  for(const change of [f=>fs.writeFileSync(path.join(f.folder,'PERSON.csv'),'tampered'),f=>fs.unlinkSync(path.join(f.folder,'TRADELINES.csv')),
    f=>{f.report.demo_dataset.dataset_version='sage-demo-v999';fs.writeFileSync(path.join(f.docs,'latest-pipeline.json'),JSON.stringify(f.report));}]){
    const f=fixture();try{change(f);await assert.rejects(publishDemo(f.options()));assert.equal(f.calls.length,0);assert.equal(fs.readFileSync(path.join(f.docs,'dataset-downloads.json'),'utf8'),'previous-valid-downloads');}finally{f.cleanup();}
  }
});
test('interrupted upload retains previous downloads and a private draft; repair fills missing assets',async()=>{
  const f=fixture();try{let uploads=0;const api=async(...args)=>{if(args[3]&&++uploads===3)throw Error('fabricated interruption');return f.api(...args);};
    await assert.rejects(publishDemo({...f.options(),api}));assert.equal(f.release().draft,true);assert.equal(f.release().assets.length,2);
    assert.equal(fs.readFileSync(path.join(f.docs,'dataset-downloads.json'),'utf8'),'previous-valid-downloads');
    await publishDemo(f.options());assert.equal(f.release().draft,false);assert.equal(f.release().assets.length,8);
  }finally{f.cleanup();}
});
test('existing valid published release is reused without overwrite; changed assets are never replaced',async()=>{
  const f=fixture();try{await publishDemo(f.options());let previousCalls=f.calls.length;
    const before=fs.readFileSync(path.join(f.docs,'dataset-downloads.json'));
    await publishDemo(f.options());assert.deepEqual(fs.readFileSync(path.join(f.docs,'dataset-downloads.json')),before);
    assert.ok(f.calls.slice(previousCalls).every(c=>c.method==='GET'));
    f.release().assets[0].digest='sha256:'+'f'.repeat(64);previousCalls=f.calls.length;
    const previous=fs.readFileSync(path.join(f.docs,'dataset-downloads.json'));await assert.rejects(publishDemo(f.options()));
    assert.ok(f.calls.slice(previousCalls).every(c=>c.method==='GET'));assert.deepEqual(fs.readFileSync(path.join(f.docs,'dataset-downloads.json')),previous);
  }finally{f.cleanup();}
});
