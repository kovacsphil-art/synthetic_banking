/* Public SAGE overview: one sanitized report, with a clear unavailable state. */
(() => {
  "use strict";
  function setupPipeline(doc,{isMobile=()=>globalThis.matchMedia?.('(max-width: 650px)').matches||false}={}) {
    const explorer=doc.getElementById('pipeline-explorer'),panel=doc.getElementById('pipeline-detail');
    if(!explorer||!panel)return;
    const overview=doc.getElementById('pipeline-overview'),status=doc.getElementById('pipeline-status'),reset=doc.getElementById('pipeline-reset');
    const stages=[...explorer.querySelectorAll('.pipeline-stage')].map(stage=>({stage,button:stage.querySelector('button'),more:stage.querySelector('.stage-more'),detail:doc.getElementById(stage.dataset.detail)}));
    if(!stages.length||!overview||!status||!reset||stages.some(s=>!s.button||!s.detail||!s.more))return;
    let pinned=null,preview=null,last=null,restoringFocus=false;
    function render(){
      const current=preview||pinned;overview.hidden=!!current;reset.hidden=!current;
      for(const s of stages){const active=s===current;s.stage.dataset.open=String(active);s.stage.dataset.pinned=String(s===pinned);
        s.button.setAttribute('aria-expanded',String(active));s.button.setAttribute('aria-pressed',String(s===pinned));s.detail.hidden=!active;s.more.textContent=s===pinned?'Selected':active?'Preview':'Explore';}
      status.textContent=current?'Stage '+String(stages.indexOf(current)+1).padStart(2,'0')+' of '+String(stages.length).padStart(2,'0')+' · '+current.stage.dataset.title+' · '+(current===pinned?'Selected':'Preview'):'The complete process · Explore any stage';
      if(current)last=current;
    }
    function clear(returnFocus=false){pinned=null;preview=null;render();
      if(returnFocus&&last){restoringFocus=true;last.button.focus();restoringFocus=false;}}
    for(const s of stages){s.button.disabled=false;
      s.stage.addEventListener('pointerenter',e=>{if(e.pointerType==='touch')return;preview=s;render();});
      s.button.addEventListener('focus',()=>{if(!restoringFocus){preview=s;render();}});
      s.button.addEventListener('click',()=>{if(pinned===s){clear();return;}pinned=s;preview=null;render();
        // Tap brings the explanation into view; hover and focus never move the page.
        if(isMobile())panel.scrollIntoView({block:'nearest',behavior:'auto'});});
      s.button.addEventListener('keydown',e=>{
        const index=stages.indexOf(s),keys={ArrowRight:(index+1)%stages.length,ArrowDown:(index+1)%stages.length,ArrowLeft:(index+stages.length-1)%stages.length,ArrowUp:(index+stages.length-1)%stages.length,Home:0,End:stages.length-1};
        if(Object.hasOwn(keys,e.key)){e.preventDefault();stages[keys[e.key]].button.focus();}
      });
    }
    explorer.addEventListener('pointerleave',()=>{if(!panel.contains(doc.activeElement)){preview=stages.find(s=>s.button===doc.activeElement)||null;render();}});
    explorer.addEventListener('focusout',e=>{if(!explorer.contains(e.relatedTarget)){preview=null;render();}});
    explorer.addEventListener('keydown',e=>{if(e.key==='Escape'&&(preview||pinned)){e.preventDefault();clear(panel.contains(doc.activeElement));}});
    reset.addEventListener('click',()=>clear(true));render();
  }
  async function mountShowcase(doc,{fetcher=globalThis.fetch,location=globalThis.location,timeoutMs=10000}={}) {
    const root=doc.getElementById("executive-results");if(!root)return;
    const status=doc.getElementById("hero-status"),plot=doc.getElementById("distribution-preview"),controller=new AbortController(),timer=setTimeout(()=>controller.abort(),timeoutMs);
    const text=(id,value)=>{const n=doc.getElementById(id);if(n)n.textContent=value;};root.setAttribute("aria-busy","true");status.textContent="Loading latest results…";
    try{const url=new URL(root.dataset.reportUrl||"latest-pipeline.json",doc.baseURI);if(!["https:","http:"].includes(url.protocol)||url.origin!==location.origin)throw new Error("Unavailable");
      const response=await fetcher(url.href,{cache:"no-store",credentials:"omit",redirect:"error",signal:controller.signal});if(!response.ok)throw new Error("Unavailable");const raw=await response.text();if(raw.length>1024*1024)throw new Error("Unavailable");const report=JSON.parse(raw),brief=window.SageResults.normalizeReport(report),view=window.SageValidation.normalizeValidation(report);
      if(!view)throw new Error("Pending");const f=window.SageViz.fmt;
      text("hero-customers",f(brief.customers));text("hero-accounts",f(brief.accounts));text("hero-rules",f(brief.applied));
      status.textContent="Integrity checks passed · "+new Date(report.pipeline_completed_at).toLocaleDateString("en",{timeZone:"UTC",year:"numeric",month:"short",day:"numeric"})+" · Privacy "+(report.privacy?.status||"UNAVAILABLE");
      const stamp=doc.createElement("p");stamp.className="small-label";stamp.textContent="Measured results · "+new Date(report.pipeline_completed_at).toLocaleString("en",{timeZone:"UTC"})+" UTC";
      root.replaceChildren(stamp,window.SageValidation.executiveSummary(doc,view,{compact:true}),window.SageValidation.executiveFindings(doc,view));plot.replaceChildren(window.SageViz.distribution(doc,view.v));
    }catch(_){status.textContent="Latest results unavailable";["hero-customers","hero-accounts","hero-rules"].forEach(id=>text(id,"—"));const p=doc.createElement("p");p.className="results-notice";p.setAttribute("role","status");p.textContent="Latest results could not be loaded. Try again; the project methodology remains available.";const retry=doc.createElement('button');retry.type='button';retry.className='button button-secondary';retry.textContent='Retry latest results';retry.addEventListener('click',()=>{retry.disabled=true;return mountShowcase(doc,{fetcher,location,timeoutMs});});root.replaceChildren(p,retry);const note=doc.createElement("p");note.className="results-notice";note.textContent="Measured distribution results pending. No illustrative values are substituted.";plot.replaceChildren(note);
    }finally{clearTimeout(timer);root.setAttribute("aria-busy","false");}
  }
  if(typeof module!=="undefined"&&module.exports)module.exports={setupPipeline,mountShowcase};
  if(typeof document!=="undefined"){setupPipeline(document);mountShowcase(document);}
})();
