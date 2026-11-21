/* Read-only GitHub verification; updates local metadata only. Never uploads/pushes. */
'use strict';
const fs=require('node:fs'),path=require('node:path'),{webcrypto}=require('node:crypto');
const {normalizeManifest,validatePreview,verifyRelease}=require('../docs/downloads.js');
async function main(){
  const root=path.resolve(__dirname,'../docs'),target=path.join(root,'dataset-downloads.json');
  const raw=fs.readFileSync(target);if(raw.length>16*1024)throw new Error('Manifest too large');
  const existing=normalizeManifest(JSON.parse(raw));
  if(existing.publication_status==='WITHDRAWN')throw new Error('A withdrawn manifest requires a new reviewed preparation.');
  await validatePreview(existing,fs.readFileSync(path.join(root,'demo-preview.json'),'utf8'),webcrypto);
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
  let urls;
  try{urls=await verifyRelease(existing,{signal:controller.signal});}finally{clearTimeout(timer);}
  const candidate={...existing,publication_status:'PUBLISHED',publication_checked_at:new Date().toISOString(),download_urls:urls};
  normalizeManifest(candidate);
  const temporary=target+'.tmp';
  let created=false;
  try{fs.writeFileSync(temporary,JSON.stringify(candidate,null,2)+'\n',{flag:'wx'});created=true;fs.renameSync(temporary,target);}
  finally{if(created&&fs.existsSync(temporary))fs.unlinkSync(temporary);}
  console.log('Published Release assets verified. Local manifest is ready; no assets were uploaded and no website was deployed.');
}
if(require.main===module)main().catch(()=>{console.error('Download verification stopped. Previous manifest retained; check the exact Release tag, all eight assets, sizes, SHA-256 digests and matching demo preview.');process.exitCode=1;});
module.exports={main};
