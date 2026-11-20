/* Public SAGE overview: one sanitized report, with a clear unavailable state. */
(() => {
  "use strict";
  function setupPipeline(doc) {
    const stages=[...doc.querySelectorAll(".pipeline-stage")];
    function set(stage,open){stage.dataset.open=String(open);stage.querySelector("button").setAttribute("aria-expanded",String(open));}
    function closeAll(){stages.forEach(s=>{set(s,false);s.dataset.pinned="false";});}
    for(const stage of stages){const button=stage.querySelector("button");stage.addEventListener("pointerenter",()=>{closeAll();stage.dataset.dismissed="false";set(stage,true);});stage.addEventListener("pointerleave",()=>{if(!stage.contains(doc.activeElement))set(stage,false);});button.addEventListener("focus",()=>{closeAll();stage.dataset.dismissed="false";set(stage,true);});stage.addEventListener("focusout",e=>{if(!stage.contains(e.relatedTarget))set(stage,false);});button.addEventListener("click",()=>{const open=stage.dataset.pinned!=="true";closeAll();stages.forEach(s=>s.dataset.pinned="false");stage.dataset.pinned=String(open);stage.dataset.dismissed=String(!open);set(stage,open);});}
    doc.addEventListener("keydown",e=>{if(e.key==="Escape"){closeAll();stages.forEach(s=>{s.dataset.dismissed="true";s.dataset.pinned="false";});}});
    // Click outside always restores the uncluttered process view.
    doc.addEventListener("click",e=>{if(!stages.some(s=>s.contains(e.target)))closeAll();});
  }
  async function mountShowcase(doc,{fetcher=globalThis.fetch,location=globalThis.location,timeoutMs=10000}={}) {
    const root=doc.getElementById("executive-results");if(!root)return;
    const status=doc.getElementById("hero-status"),plot=doc.getElementById("distribution-preview"),controller=new AbortController(),timer=setTimeout(()=>controller.abort(),timeoutMs);
    const text=(id,value)=>{const n=doc.getElementById(id);if(n)n.textContent=value;};root.setAttribute("aria-busy","true");
    try{const url=new URL(root.dataset.reportUrl||"latest-pipeline.json",doc.baseURI);if(!["https:","http:"].includes(url.protocol)||url.origin!==location.origin)throw new Error("Unavailable");
      const response=await fetcher(url.href,{cache:"no-store",credentials:"omit",redirect:"error",signal:controller.signal});if(!response.ok)throw new Error("Unavailable");const raw=await response.text();if(raw.length>1024*1024)throw new Error("Unavailable");const report=JSON.parse(raw),brief=window.SageResults.normalizeReport(report),view=window.SageValidation.normalizeValidation(report);
      if(!view)throw new Error("Pending");const f=window.SageViz.fmt;
      text("hero-customers",f(brief.customers));text("hero-accounts",f(brief.accounts));text("hero-rules",f(brief.applied));
      status.textContent="Integrity checks passed · "+new Date(report.pipeline_completed_at).toLocaleDateString("en",{timeZone:"UTC",year:"numeric",month:"short",day:"numeric"});
      const stamp=doc.createElement("p");stamp.className="small-label";stamp.textContent="Measured results · "+new Date(report.pipeline_completed_at).toLocaleString("en",{timeZone:"UTC"})+" UTC";
      root.replaceChildren(stamp,window.SageValidation.executiveSummary(doc,view),window.SageValidation.executiveFindings(doc,view));plot.replaceChildren(window.SageViz.distribution(doc,view.v));
    }catch(_){status.textContent="Latest results unavailable";["hero-customers","hero-accounts","hero-rules"].forEach(id=>text(id,"—"));const p=doc.createElement("p");p.className="results-notice";p.setAttribute("role","status");p.textContent="Latest results unavailable. The methodology remains available; publish a complete validated report to populate these measures.";root.replaceChildren(p);const note=doc.createElement("p");note.className="results-notice";note.textContent="Measured distribution results pending. No illustrative values are substituted.";plot.replaceChildren(note);
    }finally{clearTimeout(timer);root.setAttribute("aria-busy","false");}
  }
  if(typeof module!=="undefined"&&module.exports)module.exports={setupPipeline,mountShowcase};
  if(typeof document!=="undefined"){setupPipeline(document);mountShowcase(document);}
})();
