/* Only verified, execution-bound fabricated exports. Never modifies an old asset. */
'use strict';
const fs=require('node:fs'),path=require('node:path'),{createHash,webcrypto}=require('node:crypto'),{execFileSync}=require('node:child_process');
const downloads=require('../docs/downloads.js');
const REPO=downloads.REPOSITORY;
function github(method,endpoint,body,file){
  const args=['api','--method',method,endpoint,'-H','Accept: application/vnd.github+json'];
  if(file)args.push('-H','Content-Type: application/octet-stream','--input',file);
  else if(body)args.push('--input','-');
  try{return JSON.parse(execFileSync('gh',args,{input:body?JSON.stringify(body):undefined,encoding:'utf8',maxBuffer:2*1024*1024,stdio:['pipe','pipe','pipe']}));}
  catch(error){if(method==='GET'&&String(error.stderr).includes('(HTTP 404)'))return null;throw new Error('Release request failed');}
}
function bindReport(m,report){
  const d=report.demo_dataset;
  if(report.validation?.status!=='PASS'||!d||d.dataset_version!==m.dataset_version||d.release_mode!=='DEMO_ONLY'||d.preview_sha256!==m.preview_sha256||report.privacy?.status!==m.privacy_status)throw new Error('Report/demo mismatch');
  for(const asset of m.assets.slice(2))if(!report.generation?.table_rows?.some(r=>r.table===asset.key&&r.status==='AVAILABLE'&&r.value===asset.rows))throw new Error('Report/demo counts mismatch');
}
function matchesAsset(m,release,asset,expected){
  if(asset.state!=='uploaded'||asset.size!==expected.bytes||asset.digest!=='sha256:'+expected.sha256)return false;
  if(asset.browser_download_url===downloads.assetUrl(m,expected.file))return true;
  // GitHub uses private untagged URLs until a new draft tag is published.
  const prefix='https://github.com/'+REPO+'/releases/download/';
  if(!release.draft||typeof asset.browser_download_url!=='string'||!asset.browser_download_url.startsWith(prefix))return false;
  const parts=asset.browser_download_url.slice(prefix.length).split('/');
  return parts.length===2&&/^untagged-[a-z0-9]+$/.test(parts[0])&&parts[1]===expected.file;
}
async function findRelease(api,prefix,version){
  const published=await api('GET',prefix+'/tags/'+version);if(published)return published;
  // A draft without a created Git tag can be absent from GET /tags/{tag}.
  for(let page=1;page<=10;page++){
    const releases=await api('GET',prefix+'?per_page=100&page='+page);
    if(!Array.isArray(releases))throw new Error('Release listing unavailable');
    const matches=releases.filter(r=>r.tag_name===version);
    if(matches.length>1)throw new Error('Ambiguous draft Release');
    if(matches.length)return matches[0];
    if(releases.length<100)return null;
  }throw new Error('Release lookup budget exceeded');
}
async function publishDemo({folder,docs,commit,api=github}){
  const raw=fs.readFileSync(path.join(folder,'dataset-downloads.json'));
  if(raw.length>16384)throw new Error('Oversize manifest');
  const m=downloads.normalizeManifest(JSON.parse(raw));
  if(m.publication_status!=='UNPUBLISHED'||!/^[0-9a-f]{40,64}$/.test(commit))throw new Error('Unverified publication input');
  const report=JSON.parse(fs.readFileSync(path.join(docs,'latest-pipeline.json')));
  bindReport(m,report);
  const preview=fs.readFileSync(path.join(folder,'demo-preview.json'));
  await downloads.validatePreview(m,preview.toString('utf8'),webcrypto);
  for(const asset of m.assets){const file=path.join(folder,asset.file),stat=fs.lstatSync(file);
    if(!stat.isFile()||stat.isSymbolicLink()||stat.size!==asset.bytes)throw new Error('Asset size mismatch');
    // Streaming prevents complete CSV/ZIP contents being loaded into memory or logs.
    const hash=createHash('sha256');for await(const chunk of fs.createReadStream(file))hash.update(chunk);
    if(hash.digest('hex')!==asset.sha256)throw new Error('Asset hash mismatch');
  }
  const prefix='repos/'+REPO+'/releases';
  let release=await findRelease(api,prefix,m.dataset_version);
  if(!release)release=await api('POST',prefix,{tag_name:m.dataset_version,target_commitish:commit,
    name:'SAGE fabricated demonstration dataset '+m.dataset_version,
    body:'DEMO_ONLY: illustrative synthetic records generated exclusively from verified fabricated development inputs. Not actual customers or production-representative banking data. Privacy screening remains '+m.privacy_status+'. Read the included dictionary and metadata.',
    draft:true,prerelease:false,make_latest:'false'});
  if(!Number.isSafeInteger(release.id)||release.id<=0||release.tag_name!==m.dataset_version||typeof release.draft!=='boolean'||release.prerelease!==false||!Array.isArray(release.assets))throw new Error('Unexpected Release');
  if(release.assets.some(a=>!m.assets.some(b=>b.file===a.name)))throw new Error('Unexpected Release asset');
  for(const asset of m.assets){const existing=release.assets.filter(a=>a.name===asset.file);
    if(existing.length>1)throw new Error('Duplicate Release asset');
    if(existing.length){if(!matchesAsset(m,release,existing[0],asset))throw new Error('Existing immutable asset differs');}
    else{if(!release.draft)throw new Error('Published Release is incomplete');
      await api('POST','https://uploads.github.com/repos/'+REPO+'/releases/'+release.id+'/assets?name='+encodeURIComponent(asset.file),null,path.join(folder,asset.file));}
  }
  release=await api('GET',prefix+'/'+release.id);
  // Verify the whole draft before making any of its assets public.
  if(!release||release.tag_name!==m.dataset_version||release.prerelease!==false||!Array.isArray(release.assets)||release.assets.length!==8||
    !m.assets.every(expected=>release.assets.filter(a=>a.name===expected.file).length===1&&matchesAsset(m,release,release.assets.find(a=>a.name===expected.file),expected)))throw new Error('Incomplete draft assets');
  if(release.draft)release=await api('PATCH',prefix+'/'+release.id,{draft:false,make_latest:'false'});
  const urls=downloads.validateRelease(m,release);
  const published={...m,publication_status:'PUBLISHED',publication_checked_at:new Date().toISOString(),download_urls:urls};
  // Polling the same successful run must not create a timestamp-only Git commit.
  try{
    const previous=downloads.normalizeManifest(JSON.parse(fs.readFileSync(path.join(docs,'dataset-downloads.json'))));
    const stable=Object.keys(m).filter(k=>!['publication_status','publication_checked_at'].includes(k));
    if(previous.publication_status==='PUBLISHED'&&stable.every(k=>JSON.stringify(previous[k])===JSON.stringify(m[k])))published.publication_checked_at=previous.publication_checked_at;
  }catch(_){/* No matching previously published manifest. */}
  downloads.normalizeManifest(published);
  // Git commit/Pages deployment occurs only after all three files pass this step.
  fs.writeFileSync(path.join(docs,'demo-preview.json'),preview);
  fs.writeFileSync(path.join(docs,'dataset-downloads.json'),JSON.stringify(published,null,2)+'\n');
  return published;
}
if(require.main===module){
  const root=path.resolve(__dirname,'..');
  if(process.env.SAGE_PUBLISH_DEMO_DATASETS!=='true')throw new Error('Demo publication disabled');
  publishDemo({folder:path.join(root,'.databricks/publication/demo'),docs:path.join(root,'docs'),commit:process.env.GITHUB_SHA||''})
    .then(()=>console.log('Verified DEMO_ONLY Release and matching public metadata ready.'))
    .catch(()=>{console.error('Demo publication stopped. Previous public downloads retained; check verified provenance and Release asset checks.');process.exitCode=1;});
}
module.exports={publishDemo,bindReport};
