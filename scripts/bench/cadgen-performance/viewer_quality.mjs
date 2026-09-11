#!/usr/bin/env node
// Measure initial geometry, complete preview, and standard-quality settlement
// separately. Use a private viewer/store and real saved STEP fixtures; import
// them beforehand to exclude STEP translation from browser display timings.
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
const require=createRequire(path.resolve('packages/cadgen-js/package.json'));
const {chromium}=require('playwright');
const args=Object.fromEntries(process.argv.slice(2).reduce((rows,v,i,a)=>i%2 ? rows : [...rows,[v.replace(/^--/,''),a[i+1]]],[]));
if(!args.url || !args.file || !args.output) throw new Error('--url, --file, and --output are required');
const output=path.resolve(args.output);
const browser=await chromium.launch({headless:true,args:['--use-angle=metal']});
const errors=[],requests={};
try {
 const page=await browser.newPage({viewport:{width:1400,height:900}});
 page.on('pageerror',e=>errors.push(String(e)));
 page.on('request',request=>{const url=new URL(request.url());if(url.pathname.startsWith('/__')){
   const route=url.pathname.replace(/\/__tess_cache\/[^/]+\.tess$/, '/__tess_cache/{key}.tess');
   const key=request.method()+' '+route;requests[key]=(requests[key]||0)+1;
 }});
 await page.addInitScript(()=>{
   const trace=window.__qualityBench={samples:[],adoptions:[],statuses:[],firstGeometryMs:null,completePreviewMs:null,standardCompleteMs:null};
   window.addEventListener('cad:lod-level',e=>trace.adoptions.push({at:performance.now(),...e.detail}));
   window.addEventListener('cad:lod-status',e=>{const s=e.detail;trace.statuses.push({at:performance.now(),componentCount:s.componentCount,belowMinimum:s.belowMinimum,standardSettled:s.standardSettled,qualitySettled:s.qualitySettled});});
   setInterval(()=>{
     const mesh=window.__cadMeshCost,lod=window.__cadViewportLod?.(),memory=window.__cadRenderMemoryProbe?.();
     if(!mesh||!memory?.occurrences) return;
     const at=performance.now();
     if(trace.firstGeometryMs===null)trace.firstGeometryMs=at;
     if(mesh.final&&trace.completePreviewMs===null)trace.completePreviewMs=at;
     const noCoarse=!(lod?.levelCounts?.[0]>0);
     const standard=lod?.standardSettled ?? (lod?.qualitySettled&&noCoarse);
     if(mesh.final&&lod?.componentCount===mesh.totalComponents&&standard&&trace.standardCompleteMs===null)trace.standardCompleteMs=at;
     trace.samples.push({at,loaded:mesh.loadedComponents,total:mesh.totalComponents,levels:lod?.levelCounts,
       standardSettled:standard,qualitySettled:lod?.qualitySettled,occupied:lod?.occupied,
       displayCpuBytes:memory.displayCpuBytes,surfaceBytes:memory.surfaceBytes,
       policy:window.__cadViewerMemoryPolicySnapshot?.()});
   },100);
 });
 await page.goto(new URL('?file='+encodeURIComponent(args.file),args.url).href,{waitUntil:'domcontentloaded'});
 let outcome='complete';
 try {
   await page.waitForFunction(baseline=>{
     const mesh=window.__cadMeshCost,lod=window.__cadViewportLod?.();
     return mesh?.final&&lod?.componentCount===mesh.totalComponents&&!lod.busy&&!lod.pendingEvaluation
       &&(baseline?lod.qualitySettled:lod.standardSettled===true);
   },args.baseline==='true',{timeout:Number(args.timeout||120000),polling:100});
 }catch {outcome='timeout';}
 await page.waitForTimeout(110);
 await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
 const result=await page.evaluate(()=>({trace:window.__qualityBench,mesh:window.__cadMeshCost,
   lod:window.__cadViewportLod?.(),memory:window.__cadRenderMemoryProbe?.(),quality:window.__cadViewerQuality,
   limitation:window.__cadViewerMemoryLimitation,body:document.body.innerText}));
 fs.mkdirSync(path.dirname(output),{recursive:true});
 if(args.screenshot)await page.screenshot({path:path.resolve(args.screenshot)});
 const report={time:new Date().toISOString(),url:args.url,file:args.file,browser:browser.version(),outcome,errors,requests,...result};
 fs.writeFileSync(output,JSON.stringify(report,null,2)+'\n');
 console.log(JSON.stringify({output,outcome,errors,firstGeometryMs:result.trace.firstGeometryMs,completePreviewMs:result.trace.completePreviewMs,
   standardCompleteMs:result.trace.standardCompleteMs,levels:result.lod?.levelCounts,unmetTargets:result.lod?.unmetTargets,requests},null,2));
 if(outcome!=='complete'||errors.length)process.exitCode=1;
 if(args.baseline!=='true' && outcome==='complete') {
   if(!result.quality?.standardQualityReady || result.quality?.state!=='standard') {
     console.error('Quality status did not converge with the settled standard mesh');process.exitCode=1;
   }
 }
}finally{await browser.close();}
