#!/usr/bin/env node
// Bounded, paired preview-delivery probe. Product files are never modified.
// Run against a Vite viewer whose backend uses the same cache/daemon arguments.
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { spawn, execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { performance } from "node:perf_hooks";

const options = {
  root: process.cwd(), url: "http://127.0.0.1:4173",
  python: process.env.VIEWER_PYTHON || "python3", browserRoot: process.env.VIEWER_BROWSER_ROOT || "",
  fixtureRoot: "models/tmp/r4-preview-delivery", cache: "", daemonState: "",
  daemonSocket: "/private/tmp/cadgen-r4-preview.sock", output: "",
  counts: [2, 24], scenarios: ["placement", "geometry"], baselineSource: "displayed", timeoutSec: 180,
};
const names = {
  "--root": "root", "--url": "url", "--python": "python", "--browser-root": "browserRoot",
  "--fixture-root": "fixtureRoot", "--cache": "cache", "--daemon-state": "daemonState",
  "--daemon-socket": "daemonSocket", "--output": "output", "--timeout-sec": "timeoutSec",
  "--baseline-source": "baselineSource",
};
for (let i = 2; i < process.argv.length; i += 1) {
  const argument = process.argv[i];
  if (argument === "--counts") options.counts = process.argv[++i].split(",").map(Number);
  else if (argument === "--scenarios") options.scenarios = process.argv[++i].split(",");
  else if (names[argument]) options[names[argument]] = process.argv[++i];
  else throw new Error(`Unknown argument: ${argument}`);
}
options.root = path.resolve(options.root);
for (const name of ["fixtureRoot", "browserRoot", "cache", "daemonState", "output"]) {
  const defaults = {
    browserRoot: "apps/viewer", cache: `${options.fixtureRoot}/cache`,
    daemonState: `${options.fixtureRoot}/daemon`,
    output: "scripts/bench/cadgen-performance/results/r4-preview-delivery-20260911.json",
  };
  options[name] = path.resolve(options.root, options[name] || defaults[name]);
}
if (!options.fixtureRoot.startsWith(`${path.join(options.root, "models")}${path.sep}`)) {
  throw new Error("Fixture root must be inside this checkout's models directory");
}
if (!options.counts.length || options.counts.some(n => ![2, 24].includes(n))) {
  throw new Error("This bounded probe supports only 2 and 24 occurrences");
}
if (!options.scenarios.length || options.scenarios.some(name => !["placement", "geometry"].includes(name))) {
  throw new Error("This bounded probe supports only placement and geometry scenarios");
}
if (!["displayed", "authored"].includes(options.baselineSource)) throw new Error("Invalid baseline source mode");
const now = () => performance.timeOrigin + performance.now();
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const assert = (value, message) => { if (!value) throw new Error(message); };
const round = value => Math.round(value * 100) / 100;
const require = createRequire(path.join(options.browserRoot, "package.json"));
const { chromium } = require("playwright");
const environment = {
  ...process.env, CADGEN_DAEMON: "1", CADGEN_CACHE_DIR: options.cache,
  CADGEN_DAEMON_STATE_DIR: options.daemonState, CADGEN_DAEMON_SOCKET: options.daemonSocket,
  PYTHONPATH: path.join(options.root, "packages/cadgen/src"),
};
const children = new Set();
const originalSources = new Map();
let browser;
let nonce = 0;
const startedAt = new Date().toISOString();
const report = { status: "running", startedAt, options, trials: [] };

function runtimeProvenance() {
  const roots = ["packages/cadgen/src/cadgen", "packages/cadgen-js/src", "apps/viewer/src"];
  const files = [];
  function visit(relative) {
    for (const entry of fs.readdirSync(path.join(options.root, relative), { withFileTypes: true })) {
      if (entry.name === "__pycache__" || entry.name === "_runtime") continue;
      const child = path.join(relative, entry.name);
      if (entry.isDirectory()) visit(child);
      else if (/\.(?:py|js|mjs|jsx|json)$/u.test(entry.name)) files.push(child);
    }
  }
  roots.forEach(visit);
  const hash = crypto.createHash("sha256");
  for (const file of files.sort()) hash.update(file).update("\0").update(fs.readFileSync(path.join(options.root, file)));
  return {
    head: execFileSync("git", ["rev-parse", "HEAD"], { cwd: options.root, encoding: "utf8" }).trim(),
    runtimeSourceSha256: hash.digest("hex"), files: files.length,
    dirty: execFileSync("git", ["status", "--short", "--", ...roots], { cwd: options.root, encoding: "utf8" }).trim(),
    node: process.version, platform: process.platform, arch: process.arch,
  };
}

function fixtureSource(count, { movedX, width }) {
  // The idempotent observer only timestamps existing publication events. Its
  // isolated worker retains at most one wrapper across repeated source loads.
  return `from cadgen import build123d as bd\nfrom cadgen import step\nimport os as _os\n\n` +
    `if _os.environ.get("CADGEN_JOB_ID"):\n` +
    `    from cadgen.daemon import executors as _events\n` +
    `    if not getattr(_events.emit_event, "_r4_observer", False):\n` +
    `        def _install_r4_observer():\n` +
    `            import json, time\n` +
    `            original = _events.emit_event\n` +
    `            def observed(event):\n` +
    `                for field in ("sourceResult", "preview", "saved"):\n` +
    `                    if isinstance(event.get(field), dict):\n` +
    `                        at = time.time_ns() / 1000000\n` +
    `                        print("R4_EVENT " + json.dumps({"atEpochMs": at, "field": field, "payload": event[field]}), flush=True)\n` +
    `                return original(event)\n` +
    `            observed._r4_observer = True\n` +
    `            _events.emit_event = observed\n` +
    `        _install_r4_observer()\n\n` +
    `RUN_TOKEN = ${JSON.stringify(`${startedAt}:${++nonce}`)}\nMOVED_X = ${movedX}\nTARGET_WIDTH = ${width}\n\n` +
    `@step(out="repeated${count}.step")\ndef repeated${count}():\n` +
    `    box = bd.Box(12, 10, 8)\n    cylinder = bd.Cylinder(5, 8)\n    parts = []\n` +
    `    for index in range(${count / 2}):\n` +
    `        x = (index % 6) * 22\n        y = (index // 6) * 34\n` +
    `        item = bd.Box(TARGET_WIDTH, 10, 8) if index == 0 else box\n` +
    `        item = item.moved(bd.Location((x + (MOVED_X if index == 0 else 0), y, 0)))\n` +
    `        item.label = "target_box" if index == 0 else f"box_{index}"\n        parts.append(item)\n` +
    `        item = cylinder.moved(bd.Location((x, y + 17, 0)))\n` +
    `        item.label = f"cylinder_{index}"\n        parts.append(item)\n` +
    `    return bd.Compound(obj=parts, children=parts, label="r4_repeated_${count}")\n\n` +
    `if __name__ == "__main__":\n    repeated${count}()\n`;
}

function writeFixture(count, constants) {
  const source = path.join(options.fixtureRoot, `repeated${count}.py`);
  fs.mkdirSync(path.dirname(source), { recursive: true });
  if (!originalSources.has(source)) {
    originalSources.set(source, fs.existsSync(source) ? fs.readFileSync(source) : null);
  }
  const began = now();
  fs.writeFileSync(source, fixtureSource(count, constants), "utf8");
  return { source, sourceWriteStartedAt: began, sourceWriteAt: now() };
}

function runModel(source) {
  const events = [];
  const spawnedAt = now();
  const child = spawn(options.python, [source], { cwd: options.root, env: environment, stdio: ["ignore", "pipe", "pipe"] });
  children.add(child);
  const chunks = { stdout: "", stderr: "" };
  const pending = { stdout: "", stderr: "" };
  for (const stream of ["stdout", "stderr"]) child[stream].on("data", data => {
    chunks[stream] += data;
    pending[stream] += data;
    const lines = pending[stream].split("\n");
    pending[stream] = lines.pop();
    for (const line of lines) {
      const position = line.indexOf("R4_EVENT ");
      if (position < 0) continue;
      try { events.push({ ...JSON.parse(line.slice(position + 9)), receivedAt: now() }); } catch { /* other progress text */ }
    }
  });
  const promise = new Promise((resolve, reject) => {
    child.once("error", reject);
    child.once("exit", code => {
      children.delete(child);
      if (code !== 0) reject(new Error(`Model exited ${code}: ${chunks.stdout}\n${chunks.stderr}`));
      else resolve({ spawnedAt, exitedAt: now(), events, stdout: chunks.stdout, stderr: chunks.stderr });
    });
  });
  // A browser assertion may reject before the child completes: keep its error
  // handled without changing what the eventual awaited promise reports.
  promise.catch(() => {});
  return promise;
}

function installBrowserProbe() {
  const clock = () => performance.timeOrigin + performance.now();
  const ids = new WeakMap();
  let nextId = 0;
  const id = value => {
    if (!value || typeof value !== "object") return null;
    if (!ids.has(value)) ids.set(value, ++nextId);
    return ids.get(value);
  };
  const probe = {
    responses: [], requests: [], latest: null, target: null, adoption: null, firstDraw: null, renderSamples: [],
    adoptionCount: 0, drawCount: 0, requestCount: 0,
  };
  const close = (a, b) => Number.isFinite(a) && Math.abs(a - b) < 0.002;
  const targetPart = source => (source?.parts || []).find(part => part.name === "target_box" || part.label === "target_box");
  function sourceMatches(source, target) {
    const part = targetPart(source);
    return Boolean(target && source?.parts?.length === target.count && part?.bounds &&
      close((part.bounds.min[0] + part.bounds.max[0]) / 2, target.movedX) &&
      close(part.bounds.max[0] - part.bounds.min[0], target.width));
  }
  function workspaceBindings(source) {
    const found = [];
    const seen = new Set();
    for (const canvas of document.querySelectorAll("canvas")) {
      const key = Object.keys(canvas).find(value => value.startsWith("__reactFiber$"));
      let fiber = key ? canvas[key] : null;
      while (fiber) {
        const type = fiber.elementType || fiber.type;
        const name = type?.displayName || type?.name || type?.render?.name || "";
        if (name.startsWith("CadWorkspace")) {
          for (const current of [fiber, fiber.alternate].filter(Boolean)) {
            let hook = current.memoizedState;
            while (hook) {
              for (const state of [hook.memoizedState, hook.memoizedState?.current]) {
                if (!state || state.meshData !== source || !state.meshHash) continue;
                const signature = `${state.file}|${state.meshHash}|${state.entry?.hash || ""}`;
                if (seen.has(signature)) continue;
                seen.add(signature);
                found.push({
                  file: state.file, meshHash: state.meshHash,
                  entryHash: state.entry?.hash || null, editingPreview: state.entry?.editingPreview ?? null,
                  components: Object.fromEntries(Object.entries(state.componentIdentityByCid || {}).map(([cid, item]) =>
                    [cid, { surfaceInput: item.surfaceInput, surfaceObject: item.surfaceObject,
                      surfUrl: item.surfUrl, level: state.componentLodLevelByCid?.[cid] }])),
                });
              }
              hook = hook.next;
            }
          }
        }
        fiber = fiber.return;
      }
    }
    return found;
  }
  function snapshot(source, runtime) {
    return {
      sourceId: id(source), workspaceBindings: workspaceBindings(source),
      parts: (source?.parts || []).map(part => ({
        occurrence: part.occurrenceId || part.id, name: part.name, component: part.componentId,
        row: id(part), sourceMesh: id(part.sourceMesh), bounds: part.bounds, transform: part.transform,
        sourceMeshKey: part.sourceMeshKey, lodLevel: part.lodLevel ?? null,
        sourceLodLevel: part.sourceMesh?.lodLevel ?? null, sourceLodKey: part.sourceMesh?.lodKey ?? null,
        sourceVertexCount: (part.sourceMesh?.vertices?.length || 0) / 3,
        sourceTriangleCount: (part.sourceMesh?.indices?.length || 0) / 3,
        sourceEdgeSegments: (part.sourceMesh?.edge_indices?.length || 0) / 2,
      })),
      records: (runtime.displayRecords || []).map(record => ({
        occurrence: record.partId, record: id(record), geometry: id(record.mesh?.geometry),
        positions: id(record.mesh?.geometry?.attributes?.position),
        index: id(record.mesh?.geometry?.index),
      })),
      resources: window.__cadRenderMemoryProbe?.() || null,
    };
  }
  probe.arm = target => {
    probe.target = target; probe.adoption = null; probe.firstDraw = null; probe.renderSamples = [];
  };
  probe.adopt = (source, adopted, runtime) => {
    if (!adopted || runtime?.cadScene?.source !== source) return;
    probe.adoptionCount += 1;
    probe.latest = { at: clock(), source, runtime };
    if (!runtime.renderer.__r4Wrapped) {
      const render = runtime.renderer.render;
      runtime.renderer.render = function(scene, camera, ...rest) {
        const began = clock();
        const result = render.call(this, scene, camera, ...rest);
        if (scene === runtime.scene && probe.target) {
          probe.renderSamples.push({ at: clock(), records: runtime.displayRecords?.length || 0,
            sourceId: id(runtime.cadScene?.source), target: sourceMatches(runtime.cadScene?.source, probe.target) });
        }
        // Only this actual main model scene counts; HUD/render-target draws do
        // not become a false new-frame receipt merely because cadScene is current.
        if (scene === runtime.scene && runtime.cadScene?.source === probe.latest?.source) {
          probe.drawCount += 1;
          probe.latest.drawAt = clock();
          probe.latest.drawSource = runtime.cadScene.source;
          if (probe.adoption && !probe.firstDraw &&
              probe.adoption.source === runtime.cadScene.source &&
              sourceMatches(runtime.cadScene.source, probe.target)) {
            probe.firstDraw = { at: clock(), began, sourceId: id(runtime.cadScene.source),
              mainScene: true, drawCount: probe.drawCount };
          }
        }
        return result;
      };
      runtime.renderer.__r4Wrapped = true;
    }
    if (!probe.adoption && sourceMatches(source, probe.target)) {
      const at = clock();
      probe.adoption = { at, source, snapshot: snapshot(source, runtime) };
    }
  };
  probe.state = () => ({
    latest: probe.latest ? snapshot(probe.latest.source, probe.latest.runtime) : null,
    adoption: probe.adoption ? { at: probe.adoption.at, ...probe.adoption.snapshot } : null,
    firstDraw: probe.firstDraw, requests: probe.requests, responses: probe.responses,
    renderSamples: probe.renderSamples,
    baselineLastDrawAt: probe.latest?.drawAt || null,
  });
  probe.matches = target => {
    const { source, runtime, at, drawAt, drawSource } = probe.latest || {};
    return sourceMatches(source, target) && runtime?.cadScene?.source === source &&
      drawSource === source && drawAt >= at && runtime.displayRecords?.length === target.count &&
      (!target.tree || workspaceBindings(source).some(state => state.meshHash === target.tree)) &&
      source.parts.every(part => part && part.sourceMesh && (part.occurrenceId || part.id)) &&
      runtime.displayRecords.every(record => record?.partId && record.mesh?.geometry?.attributes?.position);
  };
  const fetch = window.fetch;
  window.fetch = function(input, init) {
    const url = String(input?.url || input);
    if (!url.includes("/__cad/preview?")) return fetch.call(this, input, init);
    const request = { id: ++probe.requestCount, at: clock(), url };
    probe.requests.push(request);
    return fetch.call(this, input, init).then(response => {
      request.headersAt = clock();
      const json = response.json.bind(response);
      response.json = async () => {
        const value = await json();
        const received = { requestId: request.id, headersAt: request.headersAt, at: clock(),
          revision: value.revision, state: value.state, feedCursor: value.feedCursor,
          preview: value.preview, saved: value.saved, error: value.error };
        probe.responses.push(received);
        return value;
      };
      return response;
    });
  };
  window.__r4PreviewProbe = probe;
}

const legacyFeed = `export function observeEditingPreview(file, onUpdate, onError, {
  fetchImpl = globalThis.fetch, schedule = globalThis.setTimeout, cancel = globalThis.clearTimeout,
} = {}) {
  const controller = new AbortController(); let timer;
  const poll = async () => {
    let delay = 500;
    try {
      const query = new URLSearchParams({ file });
      const response = await fetchImpl('/__cad/preview?' + query, { signal: controller.signal, cache: 'no-store' });
      if (!response.ok) throw new Error('Editing preview is unavailable');
      const next = await response.json();
      if (controller.signal.aborted) return;
      delay = ['submitted', 'queued', 'building'].includes(next.state) ? 100 : 500;
      onUpdate(next);
    } catch (error) { if (controller.signal.aborted) return; onError(error); }
    if (!controller.signal.aborted) timer = schedule(poll, delay);
  };
  poll(); return () => { controller.abort(); cancel(timer); };
}\n`;

async function openProbe(mode, fileRef, baseline) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 });
  await context.addInitScript(installBrowserProbe);
  const patches = { adoption: 0, legacy: 0 };
  await context.route("**/src/client/components/CadViewer.js*", async route => {
    const response = await route.fetch();
    const body = await response.text();
    const pattern = /const adopted = runtime\.cadScene === cadScene && runtime\.activeModelKey === \(modelKey \|\| ""\) && cadScene\.source === meshData;/gu;
    assert([...body.matchAll(pattern)].length === 1, "CadViewer adoption patch must match exactly once");
    patches.adoption += 1;
    await route.fulfill({ response, body: body.replace(pattern,
      '$&\n    globalThis.__r4PreviewProbe?.adopt(meshData, adopted, runtime);') });
  });
  if (mode === "legacy-poll") await context.route("**/src/client/workbench/editingPreviewFeed.js*", async route => {
    patches.legacy += 1;
    await route.fulfill({ status: 200, contentType: "text/javascript", body: legacyFeed });
  });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", error => errors.push(String(error)));
  await page.goto(`${options.url}/?file=${encodeURIComponent(fileRef)}&mode=editing`, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForFunction(target => window.__r4PreviewProbe?.matches(target), baseline, { timeout: 30000 });
  await page.waitForFunction(() => window.__r4PreviewProbe.responses.some(item => item.state === "done" && item.preview), null, { timeout: 15000 });
  assert(patches.adoption > 0 && (mode !== "legacy-poll" || patches.legacy > 0), "Expected served-source probe was not installed");
  const clocks = [];
  for (let i = 0; i < 5; i += 1) {
    const began = now();
    const browserAt = await page.evaluate(() => performance.timeOrigin + performance.now());
    const ended = now();
    clocks.push({ offsetMs: browserAt - (began + ended) / 2, uncertaintyMs: (ended - began) / 2 });
  }
  clocks.sort((a, b) => a.uncertaintyMs - b.uncertaintyMs);
  return { context, page, errors, patches, clockCalibration: clocks[0] };
}

async function alignPollingPhase(page, phaseMs) {
  const after = await page.evaluate(() => window.__r4PreviewProbe.responses.length);
  await page.waitForFunction(count => window.__r4PreviewProbe.responses.slice(count)
    .some(item => item.state === "done" && item.preview), after, { timeout: 5000 });
  const receipt = await page.evaluate(() => window.__r4PreviewProbe.responses.at(-1));
  const elapsed = await page.evaluate(at => performance.timeOrigin + performance.now() - at, receipt.at);
  if (phaseMs > elapsed) await pause(phaseMs - elapsed);
  return receipt;
}

function summarizeReuse(before, after) {
  const parts = new Map(before.parts.map(part => [part.occurrence, part]));
  const records = new Map(before.records.map(record => [record.occurrence, record]));
  const sameIdentity = (left, right) => Number.isInteger(right) && right > 0 && left === right;
  const coverage = state => ({
    partRows: state.parts.filter(part => Number.isInteger(part.row) && part.row > 0).length,
    sourceMeshes: state.parts.filter(part => Number.isInteger(part.sourceMesh) && part.sourceMesh > 0).length,
    displayRecords: state.records.filter(record => Number.isInteger(record.record) && record.record > 0).length,
    geometryObjects: state.records.filter(record => Number.isInteger(record.geometry) && record.geometry > 0).length,
    positionAttributes: state.records.filter(record => Number.isInteger(record.positions) && record.positions > 0).length,
  });
  return {
    occurrences: after.parts.length,
    identityCoverageBefore: coverage(before), identityCoverageAfter: coverage(after),
    sameComponentIds: after.parts.filter(part => parts.get(part.occurrence)?.component === part.component).length,
    samePartRows: after.parts.filter(part => sameIdentity(parts.get(part.occurrence)?.row, part.row)).length,
    sameSourceMeshes: after.parts.filter(part => sameIdentity(parts.get(part.occurrence)?.sourceMesh, part.sourceMesh)).length,
    sameDisplayRecords: after.records.filter(record => sameIdentity(records.get(record.occurrence)?.record, record.record)).length,
    sameGpuGeometryObjects: after.records.filter(record => sameIdentity(records.get(record.occurrence)?.geometry, record.geometry)).length,
    samePositionAttributes: after.records.filter(record => sameIdentity(records.get(record.occurrence)?.positions, record.positions)).length,
  };
}

async function trial(count, scenario, mode, baseline, target, phaseMs) {
  const reset = writeFixture(count, baseline);
  const baselineBuild = await runModel(reset.source);
  const baselinePreview = baselineBuild.events.find(event => event.field === "preview");
  assert(baselinePreview, "Baseline build has no authored preview TREE");
  const baselineTarget = { count, ...baseline,
    ...(options.baselineSource === "authored" ? { tree: baselinePreview.payload.tree } : {}) };
  const fileRef = path.relative(report.viewerRoot, path.join(options.fixtureRoot, `repeated${count}.step`)).replaceAll(path.sep, "/");
  assert(!fileRef.startsWith("../"), "The viewer's served root does not contain the R4 fixtures");
  const opened = await openProbe(mode, fileRef, baselineTarget);
  try {
    const idleResponse = await alignPollingPhase(opened.page, phaseMs);
    await opened.page.waitForFunction(target => window.__r4PreviewProbe.matches(target), baselineTarget, { timeout: 15000 });
    const before = await opened.page.evaluate(({ target, baseline }) => {
      if (!window.__r4PreviewProbe.matches(baseline)) throw new Error("Baseline scene ceased to be live before arming");
      const before = window.__r4PreviewProbe.state();
      window.__r4PreviewProbe.arm(target);
      return before;
    }, { target: { count, ...target }, baseline: baselineTarget });
    const write = writeFixture(count, target);
    const build = runModel(write.source); // Deliberately asynchronous: browser keeps receiving and drawing.
    await opened.page.waitForFunction(() => Boolean(window.__r4PreviewProbe.firstDraw), null, { timeout: 30000 });
    const built = await build;
    const observed = await opened.page.evaluate(() => window.__r4PreviewProbe.state());
    const previewEvent = built.events.find(event => event.field === "preview");
    const savedEvent = built.events.find(event => event.field === "saved");
    assert(previewEvent && savedEvent, "Ordinary model did not publish both preview and save events");
    if (options.baselineSource === "authored") {
      assert(before.latest.workspaceBindings.some(state => state.meshHash === baselinePreview.payload.tree),
        "Live baseline source is not bound to its exact authored TREE");
      assert(observed.adoption.workspaceBindings.some(state => state.meshHash === previewEvent.payload.tree),
        "Adopted target source is not bound to its exact authored TREE");
    }
    const savedBytesHash = crypto.createHash("sha256")
      .update(fs.readFileSync(savedEvent.payload.output)).digest("hex");
    assert(savedBytesHash === savedEvent.payload.documentHash, "Saved event does not match actual STEP bytes");
    const response = observed.responses.find(item => item.at > idleResponse.at &&
      item.preview?.tree === previewEvent.payload.tree && item.revision > idleResponse.revision);
    assert(response, "No HTTP preview receipt matches this worker's exact TREE and newer revision");
    assert(observed.adoption && observed.firstDraw.sourceId === observed.adoption.sourceId,
      "First renderer draw does not belong to the adopted target source");
    assert(opened.errors.length === 0, `Browser errors: ${opened.errors.join("; ")}`);
    const offset = opened.clockCalibration.offsetMs;
    const browserAt = value => value - offset;
    const points = {
      sourceWrite: write.sourceWriteAt,
      pythonSpawn: built.spawnedAt,
      workerPreviewEvent: previewEvent.atEpochMs,
      previewEventClientReceipt: previewEvent.receivedAt,
      httpHeaders: browserAt(response.headersAt),
      httpJsonReceipt: browserAt(response.at),
      actualSceneAdoption: browserAt(observed.adoption.at),
      firstMainSceneDrawBegan: browserAt(observed.firstDraw.began),
      firstMainSceneDrawCompleted: browserAt(observed.firstDraw.at),
      workerStepSavedEvent: savedEvent.atEpochMs,
      pythonExit: built.exitedAt,
    };
    const timingsMs = Object.fromEntries(Object.entries(points).map(([key, value]) => [key, round(value - write.sourceWriteAt)]));
    const clockToleranceMs = 2 + opened.clockCalibration.uncertaintyMs;
    assert(points.actualSceneAdoption <= points.firstMainSceneDrawBegan + clockToleranceMs &&
      points.firstMainSceneDrawBegan <= points.firstMainSceneDrawCompleted,
    "The observed main-scene draw precedes its adoption receipt");
    const previewOrderingVerified = points.workerPreviewEvent <= points.httpJsonReceipt + clockToleranceMs &&
      points.httpJsonReceipt <= points.actualSceneAdoption + clockToleranceMs;
    const lastIdleBeforeWrite = observed.responses.filter(item => item.state === "done" && item.preview &&
      browserAt(item.at) <= write.sourceWriteAt).at(-1) || idleResponse;
    const requestsInFlightAtWrite = observed.requests.filter(item => browserAt(item.at) <= write.sourceWriteAt &&
      (!item.headersAt || browserAt(item.headersAt) > write.sourceWriteAt));
    const reuse = summarizeReuse(before.latest, observed.adoption);
    for (const coverage of [reuse.identityCoverageBefore, reuse.identityCoverageAfter]) {
      assert(Object.values(coverage).every(value => value === count),
        `Baseline/adopted identity coverage is incomplete: ${JSON.stringify(coverage)}`);
    }
    const activeRenderSamples = observed.renderSamples.filter(item => browserAt(item.at) >= write.sourceWriteAt);
    assert(activeRenderSamples.every(item => item.records === count),
      `A displayed edit frame lost complete geometry: ${JSON.stringify(activeRenderSamples)}`);
    assert(reuse.sameComponentIds === count - (scenario === "geometry" ? 1 : 0),
      `Unexpected component changes: ${JSON.stringify(reuse)}`);
    return {
      count, scenario, mode, target, baseline, requestedIdlePhaseMs: phaseMs,
      baselineSourceMode: options.baselineSource, baselinePreviewTree: baselinePreview.payload.tree,
      phaseAnchorResponseToSourceWriteMs: round(write.sourceWriteAt - browserAt(idleResponse.at)),
      actualIdleResponseToSourceWriteMs: round(write.sourceWriteAt - browserAt(lastIdleBeforeWrite.at)),
      previewRequestsInFlightAtSourceWrite: requestsInFlightAtWrite.map(item => item.id),
      baselineIdentitySnapshotTiming: "immediately before source write, after polling-phase alignment",
      baselineActualMainSceneDrawAt: browserAt(before.baselineLastDrawAt),
      clockCalibration: opened.clockCalibration, patches: opened.patches,
      deliveryPath: previewOrderingVerified ? "verified-preview" : "saved-catalog-or-other-unproven-preview",
      previewOrderingVerified, clockToleranceMs,
      previewTree: previewEvent.payload.tree, savedTree: savedEvent.payload.tree,
      savedDocumentHash: savedEvent.payload.documentHash, actualSavedBytesSha256: savedBytesHash,
      pointsEpochMs: points, timingsMs, reuse,
      before: before.latest, adoption: observed.adoption, firstDraw: observed.firstDraw,
      activeRenderSamples,
      previewRequests: observed.requests.filter(item => item.at >= idleResponse.at),
      previewResponses: observed.responses.filter(item => item.at >= idleResponse.at),
      workerEvents: built.events, errors: opened.errors,
    };
  } finally { await opened.context.close(); }
}

function saveReport() {
  fs.mkdirSync(path.dirname(options.output), { recursive: true });
  fs.writeFileSync(options.output, `${JSON.stringify(report, null, 2)}\n`, "utf8");
}

function restoreOriginalSources() {
  for (const [source, original] of originalSources) {
    if (original !== null) fs.writeFileSync(source, original);
  }
}

const deadline = setTimeout(() => {
  for (const child of children) child.kill("SIGTERM");
  report.status = "timed-out"; report.error = `Hard deadline ${options.timeoutSec}s`;
  saveReport(); restoreOriginalSources();
  Promise.resolve(browser?.close()).finally(() => process.exit(1));
}, Number(options.timeoutSec) * 1000);
try {
  report.provenanceBefore = runtimeProvenance();
  report.harnessSourceSha256 = crypto.createHash("sha256")
    .update(fs.readFileSync(new URL(import.meta.url))).digest("hex");
  report.clockSources = {
    node: "performance.timeOrigin + performance.now() (Unix epoch milliseconds)",
    worker: "time.time_ns()/1e6 at preview/saved event emission, before original emit_event; shared host wall clock",
    browser: "performance.timeOrigin + performance.now(); minimum-RTT five-sample offset estimate subtracted",
    nodeWallClockDeltaMs: now() - Date.now(),
  };
  const serverResponse = await fetch(`${options.url}/__cad/server`);
  assert(serverResponse.ok, "Viewer backend did not expose its serving root");
  report.viewerServer = await serverResponse.json();
  report.viewerRoot = path.resolve(report.viewerServer.rootPath || options.root);
  browser = await chromium.launch({ headless: true, args: ["--use-angle=metal"] });
  report.chromium = await browser.version();
  let pairIndex = 0;
  for (const count of options.counts) for (const scenario of options.scenarios) {
    const baseline = { movedX: 0, width: 12.25 };
    const target = scenario === "placement" ? { movedX: 7, width: baseline.width } : { movedX: 0, width: 13.25 };
    // Both exact output revisions and saved STEP readbacks are warmed before
    // either timed condition. Nonces force the same source-replay path each run.
    await runModel(writeFixture(count, baseline).source);
    await runModel(writeFixture(count, target).source);
    const order = pairIndex % 2 === 0 ? ["legacy-poll", "held-feed"] : ["held-feed", "legacy-poll"];
    const phaseMs = pairIndex % 2 === 0 ? 125 : 375;
    for (const mode of order) {
      const result = await trial(count, scenario, mode, baseline, target, phaseMs);
      result.pairIndex = pairIndex; result.order = order;
      report.trials.push(result); saveReport();
      console.log(JSON.stringify({ count, scenario, mode, timingsMs: result.timingsMs, reuse: result.reuse }));
    }
    const [first, second] = report.trials.slice(-2);
    assert(first.previewTree === second.previewTree && first.savedDocumentHash === second.savedDocumentHash,
      "Paired conditions did not publish identical geometry and STEP bytes");
    pairIndex += 1;
  }
  report.provenanceAfter = runtimeProvenance();
  assert(report.provenanceBefore.runtimeSourceSha256 === report.provenanceAfter.runtimeSourceSha256,
    "Runtime source content changed during measurement");
  report.status = "passed";
  report.completedAt = new Date().toISOString();
  saveReport();
} catch (error) {
  report.status = "failed"; report.error = error instanceof Error ? error.stack : String(error);
  saveReport(); throw error;
} finally {
  clearTimeout(deadline);
  for (const child of children) child.kill("SIGTERM");
  await browser?.close();
  restoreOriginalSources();
}
