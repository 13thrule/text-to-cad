// Same-tab CAD lifecycle QA. Starts its own browser, uses an existing viewer.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
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
const loadTimings=[];
const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const git=(...argv)=>execFileSync('git',argv,{cwd:repo,encoding:'utf8'}).trim();
const revision=git('rev-parse','HEAD');
const runtimeChanges=git('status','--porcelain','--','packages/cadgen-js/src','apps/viewer/src','packages/cadgen/src/cadgen');
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

async function waitLoaded(file,previousModelKey=null){
  await page.waitForFunction(({expected,previousModelKey})=>{
    const browse=[...document.querySelectorAll('button')].some(b=>b.getAttribute('aria-label')===`Browse ${expected}`);
    const c=window.__cadMeshCost;
    const key=window.__cadModelPlacement?.modelKey;
    return browse && c && c.final===true && key && key!==previousModelKey;
  },{expected:file,previousModelKey},{timeout:120000});
  const finalPublicationObservedAt=performance.now();
  await page.waitForTimeout(900);
  return finalPublicationObservedAt;
}
async function choose(file){
  let button=page.locator('button[aria-label^="Browse "]:visible').first();
  if(await button.count()===0){await page.getByRole('button',{name:'Toggle CAD Viewer',exact:true}).click({force:true});button=page.locator('button[aria-label^="Browse "]:visible').first();}
  await button.click({force:true});
  const previousModelKey=await page.evaluate(()=>window.__cadModelPlacement?.modelKey);
  const started=performance.now();
  await page.getByRole('menuitem',{name:file,exact:true}).click();
  const readyAt=await waitLoaded(file,previousModelKey);
  loadTimings.push({file,kind:'same-tab-switch',throughFinalPublicationMs:readyAt-started,throughSettleMs:performance.now()-started,settleMs:900});
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

const navigationStarted=performance.now();
await page.goto(`${base}/?file=${encodeURIComponent(repeatedFile)}`,{waitUntil:'domcontentloaded',timeout:120000});
const readyAt=await waitLoaded(repeatedFile);
loadTimings.push({file:repeatedFile,kind:'fresh-browser-navigation',throughFinalPublicationMs:readyAt-navigationStarted,throughSettleMs:performance.now()-navigationStarted,settleMs:900});
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
  const demandStarted=performance.now();
  await page.getByRole('button',{name:`Expand ${firstPart}`,exact:true}).click();
  await page.waitForFunction(before=>(window.__cadRenderMemoryProbe?.().assetCaches?.selector?.entries||0)>before,selectorsBefore,{timeout:30000});
  selectorsAfter=await page.evaluate(()=>window.__cadRenderMemoryProbe?.().assetCaches?.selector?.entries||0);
  loadTimings.push({file:repeatedFile,kind:'first-tree-topology-demand',throughSelectorReadyMs:performance.now()-demandStarted});
}
snapshots.push(await collect('repeated-after-first-pick'));

const sequence=[otherFile,repeatedFile,otherFile,repeatedFile,otherFile,repeatedFile];
for(let i=0;i<sequence.length;i++){
  await choose(sequence[i]);
  await page.mouse.move(570,430);await page.waitForTimeout(100);await page.mouse.click(570,430);await page.waitForTimeout(180);
  snapshots.push(await collect(`cycle-${i+1}-${sequence[i]}`));
}
await page.getByRole('button',{name:'Orbit',exact:true}).click();
await page.mouse.move(550,430);
await page.evaluate(()=>{
  const sample={frames:[],drawCalls:[],active:true,last:performance.now(),drawBase:window.__cycleGpu.draws};
  window.__cycleOrbit=sample;
  const frame=(now)=>{
    if(!sample.active)return;
    sample.frames.push(now-sample.last);
    sample.drawCalls.push(window.__cycleGpu.draws-sample.drawBase);
    sample.last=now;sample.drawBase=window.__cycleGpu.draws;
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
});
await page.mouse.down();
// Keep the camera moving for 100 steps, at least 40 ms apart. rAF intervals
// measure browser presentation cadence during interaction, not GPU time.
const orbitStarted=performance.now();
for(let i=0;i<100;i++){
  const angle=i*Math.PI/25;
  await page.mouse.move(550+90*Math.sin(angle),430+55*(1-Math.cos(angle)));
  await page.waitForTimeout(40);
}
await page.mouse.up();
const orbit=await page.evaluate(()=>{
  const sample=window.__cycleOrbit;
  sample.active=false;
  const summarize=(values)=>{
    const sorted=values.slice(2).sort((a,b)=>a-b);
    const at=(q)=>sorted.length ? sorted[Math.min(sorted.length-1,Math.ceil(sorted.length*q)-1)] : null;
    return {samples:sorted.length,p50:at(0.5),p95:at(0.95),max:at(1)};
  };
  return {frameIntervalsMs:summarize(sample.frames),drawCallsPerFrame:summarize(sample.drawCalls),rawFrameIntervalsMs:sample.frames,rawDrawCallsPerFrame:sample.drawCalls};
});
orbit.durationMs=performance.now()-orbitStarted;
await page.waitForTimeout(350);
snapshots.push(await collect('repeated-after-final-orbit'));

const result={
  generatedAt:new Date().toISOString(),
  loadTimings,
  orbit,
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
result.environment={node:process.version,platform:process.platform,arch:process.arch,cpu:os.cpus()[0]?.model,totalMemoryBytes:os.totalmem(),revision,runtimeChangesAtStart:runtimeChanges,runtimeChangesAtEnd:git('status','--porcelain','--','packages/cadgen-js/src','apps/viewer/src','packages/cadgen/src/cadgen'),url:base,file:repeatedFile,other:otherFile,browserCache:'fresh profile initially; same profile for switches',tessellationCache:'preexisting server cache; neither cleared nor controlled by this harness',viewport:{width:1400,height:900},angle:'metal',lod:'default'};
fs.mkdirSync(path.dirname(path.resolve(args.out)),{recursive:true});
fs.writeFileSync(args.out,JSON.stringify(result,null,2)+'\n');
if (!Object.values(result.assertions).every(Boolean)) process.exitCode=1;
console.log(JSON.stringify(result,null,2));
await cdp.detach().catch(()=>{});
} finally {
await context.close();fs.rmSync(profile,{recursive:true,force:true});
}
