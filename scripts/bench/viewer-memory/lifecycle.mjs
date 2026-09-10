// Same-tab CAD lifecycle QA. Starts its own browser, uses an existing viewer.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire(new URL('../../../apps/viewer/package.json', import.meta.url));
const { chromium } = require(process.env.PLAYWRIGHT_FROM || 'playwright');

const args = {};
for (let i=2;i<process.argv.length;i+=2) {
  const flag=process.argv[i];
  if (!['--url','--file','--other','--out','--first-part'].includes(flag) || !process.argv[i+1]) {
    throw new Error('Usage: lifecycle.mjs --url ORIGIN --file repeated24.step --other planetary.step --out REPORT.json [--first-part box_1]');
  }
  args[flag.slice(2)]=process.argv[i+1];
}
if (!args.url || !args.file || !args.other || !args.out) throw new Error('--url, --file, --other and --out are required');
const base=args.url.replace(/\/+$/, '');
const repeatedFile=args.file, otherFile=args.other;
const firstPart=args['first-part'] || 'box_1';
const profile=fs.mkdtempSync(path.join(os.tmpdir(),'viewer-cycle-'));
const errors=[];
const failed=[];
const context=await chromium.launchPersistentContext(profile,{
  headless:true, viewport:{width:1400,height:900},
  args:['--use-angle=metal','--enable-precise-memory-info','--disable-features=PrivateNetworkAccessSendPreflights']
});
try {
const page=context.pages()[0] || await context.newPage();
await page.addInitScript(() => {
  const stats={liveBytes:0,peakBytes:0,liveBufferCount:0,peakBufferCount:0,uploads:0,deletes:0,draws:0,instancedDraws:0};
  const sizes=new WeakMap();
  const bound=new WeakMap();
  window.__cycleGpu=stats;
  const patch=(proto)=>{
    if(!proto || proto.__cyclePatched)return; proto.__cyclePatched=true;
    const bindBuffer=proto.bindBuffer,bufferData=proto.bufferData,deleteBuffer=proto.deleteBuffer;
    proto.bindBuffer=function(target,buffer){let map=bound.get(this);if(!map){map=new Map();bound.set(this,map)}map.set(target,buffer);return bindBuffer.apply(this,arguments)};
    proto.bufferData=function(target,source){const size=typeof source==='number'?source:(source?.byteLength||0);const buffer=bound.get(this)?.get(target);if(buffer){const old=sizes.get(buffer)||0;if(!old){stats.liveBufferCount++;stats.peakBufferCount=Math.max(stats.peakBufferCount,stats.liveBufferCount)}sizes.set(buffer,size);stats.liveBytes+=size-old;stats.peakBytes=Math.max(stats.peakBytes,stats.liveBytes)}stats.uploads++;return bufferData.apply(this,arguments)};
    proto.deleteBuffer=function(buffer){const old=sizes.get(buffer)||0;if(old){stats.liveBytes-=old;stats.liveBufferCount--;sizes.set(buffer,0);stats.deletes++}return deleteBuffer.apply(this,arguments)};
    for(const name of ['drawElements','drawArrays','drawElementsInstanced','drawArraysInstanced']){const original=proto[name];if(typeof original!=='function')continue;proto[name]=function(){stats.draws++;if(name.includes('Instanced'))stats.instancedDraws++;return original.apply(this,arguments)}}
  };
  patch(window.WebGLRenderingContext?.prototype); patch(window.WebGL2RenderingContext?.prototype);
});
page.on('pageerror',e=>errors.push(String(e?.message||e)));
page.on('requestfailed',r=>failed.push(`${r.failure()?.errorText||'failed'} ${r.url()}`));

async function waitLoaded(file){
  await page.waitForFunction(expected=>{
    const browse=[...document.querySelectorAll('button')].some(b=>b.getAttribute('aria-label')===`Browse ${expected}`);
    const c=window.__cadMeshCost;
    return browse && c && c.final===true && window.__cadModelPlacement?.modelKey;
  },file,{timeout:120000});
  await page.waitForTimeout(900);
}
async function choose(file){
  let button=page.locator('button[aria-label^="Browse "]:visible').first();
  if(await button.count()===0){await page.getByRole('button',{name:'Toggle CAD Viewer',exact:true}).click({force:true});button=page.locator('button[aria-label^="Browse "]:visible').first();}
  await button.click({force:true});
  await page.getByRole('menuitem',{name:file,exact:true}).click();
  await waitLoaded(file);
}
const cdp=await context.newCDPSession(page);
async function collect(label,forceGc=true){
  if(forceGc){await cdp.send('HeapProfiler.collectGarbage');await page.waitForTimeout(700)}
  return page.evaluate(label=>({
    label,
    file:[...document.querySelectorAll('button')].find(b=>b.getAttribute('aria-label')?.startsWith('Browse '))?.getAttribute('aria-label')?.slice(7)||'',
    probe:window.__cadRenderMemoryProbe?.()||null,
    gpu:{...window.__cycleGpu},
    heap:performance.memory?{used:performance.memory.usedJSHeapSize,total:performance.memory.totalJSHeapSize}:null,
    limitation:window.__cadRenderMemoryProbe?.()?.memoryPolicy?.lastLimitation ?? window.__cadViewerMemory?.lastLimitation ?? null,
    inspector:(document.body?.innerText||'').split('\n').slice(-12)
  }),label);
}

await page.goto(`${base}/?file=${encodeURIComponent(repeatedFile)}`,{waitUntil:'domcontentloaded',timeout:120000});
await waitLoaded(repeatedFile);
const snapshots=[];
snapshots.push(await collect('repeated-initial'));
const selectorsBefore=snapshots[0].probe?.assetCaches?.selector?.entries ?? null;
let firstPickMethod='canvas';
// Sweep a small central grid: the repeated fixture spans most of this region.
for(const [x,y] of [[570,430],[500,430],[640,430],[570,360],[570,500]]){
  await page.mouse.move(x,y); await page.waitForTimeout(120); await page.mouse.click(x,y); await page.waitForTimeout(350);
  const entries=await page.evaluate(()=>window.__cadRenderMemoryProbe?.().assetCaches?.selector?.entries||0);
  if(entries>selectorsBefore)break;
}
let selectorsAfter=await page.evaluate(()=>window.__cadRenderMemoryProbe?.().assetCaches?.selector?.entries||0);
if(selectorsAfter<=selectorsBefore){
  firstPickMethod='tree-expand-fallback';
  await page.getByRole('button',{name:`Expand ${firstPart}`,exact:true}).click();
  await page.waitForFunction(before=>(window.__cadRenderMemoryProbe?.().assetCaches?.selector?.entries||0)>before,selectorsBefore,{timeout:30000});
  selectorsAfter=await page.evaluate(()=>window.__cadRenderMemoryProbe?.().assetCaches?.selector?.entries||0);
}
snapshots.push(await collect('repeated-after-first-pick'));

const sequence=[otherFile,repeatedFile,otherFile,repeatedFile,otherFile,repeatedFile];
for(let i=0;i<sequence.length;i++){
  await choose(sequence[i]);
  await page.mouse.move(570,430);await page.waitForTimeout(100);await page.mouse.click(570,430);await page.waitForTimeout(180);
  snapshots.push(await collect(`cycle-${i+1}-${sequence[i]}`));
}
await page.getByRole('button',{name:'Orbit',exact:true}).click();
await page.mouse.move(550,430);await page.mouse.down();await page.mouse.move(660,485,{steps:12});await page.mouse.up();await page.waitForTimeout(350);
snapshots.push(await collect('repeated-after-final-orbit'));

const result={
  generatedAt:new Date().toISOString(),
  firstPick:{method:firstPickMethod,selectorsBefore,selectorsAfter},
  snapshots,
  pageErrors:errors,
  requestFailures:failed,
  assertions:{
    repeatedInstancing:snapshots[0].probe?.surfaceInstanceSets===2 && snapshots[0].probe?.surfaceInstances===24,
    lazyInitially:selectorsBefore===0,
    firstDemandLoaded:selectorsAfter>selectorsBefore,
    noPageErrors:errors.length===0,
    noUnexpectedRequestFailures:failed.every(value=>value.startsWith('net::ERR_ABORTED ')),
    noLimitations:snapshots.every(s=>s.limitation==null),
  }
};
const repeated=snapshots.filter(s=>s.file===repeatedFile);
result.repeatedPlateau={
  gpuLiveBytes:repeated.map(s=>s.gpu.liveBytes),
  gpuLiveBufferCount:repeated.map(s=>s.gpu.liveBufferCount),
  heapUsed:repeated.map(s=>s.heap?.used),
  probeOwned:repeated.map(s=>s.probe?.memoryPolicy?.estimatedOwnedBytes),
  surfaceSets:repeated.map(s=>s.probe?.surfaceInstanceSets),
  deletes:repeated.map(s=>s.gpu.deletes)
};
const returned=repeated.filter(s=>s.label.startsWith('cycle-'));
result.assertions.gpuPlateau=returned.length===3 && new Set(returned.map(s=>s.gpu.liveBytes)).size===1 && new Set(returned.map(s=>s.gpu.liveBufferCount)).size===1;
result.assertions.workersReclaimed=snapshots.every(s=>(s.probe?.memoryPolicy?.retainedByCategory?.workerResidentEstimated || 0)===0);
result.environment={node:process.version,platform:process.platform,arch:process.arch,url:base,file:repeatedFile,other:otherFile};
fs.mkdirSync(path.dirname(path.resolve(args.out)),{recursive:true});
fs.writeFileSync(args.out,JSON.stringify(result,null,2)+'\n');
if (!Object.values(result.assertions).every(Boolean)) process.exitCode=1;
console.log(JSON.stringify(result,null,2));
await cdp.detach().catch(()=>{});
} finally {
await context.close();fs.rmSync(profile,{recursive:true,force:true});
}
