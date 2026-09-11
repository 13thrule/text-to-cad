#!/usr/bin/env node
// Browser correctness probe for retained STEP scene updates. It mutates only
// models/tmp/r3-browser/repeated24.py and restores that source on every exit.

import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { createRequire } from "node:module";

function args(argv) {
  const out = {
    url: "http://127.0.0.1:4173",
    root: process.cwd(),
    python: process.env.VIEWER_PYTHON || "python3",
    browserRoot: process.env.VIEWER_BROWSER_ROOT || "",
    daemonState: process.env.CADGEN_DAEMON_STATE_DIR || "",
    daemonSocket: process.env.CADGEN_DAEMON_SOCKET || "/private/tmp/cadgen-r3-browser.sock",
    output: "",
  };
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === "--url") out.url = argv[++i];
    else if (argv[i] === "--root") out.root = argv[++i];
    else if (argv[i] === "--python") out.python = argv[++i];
    else if (argv[i] === "--browser-root") out.browserRoot = argv[++i];
    else if (argv[i] === "--daemon-state") out.daemonState = argv[++i];
    else if (argv[i] === "--daemon-socket") out.daemonSocket = argv[++i];
    else if (argv[i] === "--output") out.output = argv[++i];
    else throw new Error(`unknown argument ${argv[i]}`);
  }
  out.root = path.resolve(out.root);
  out.browserRoot = path.resolve(out.browserRoot || path.join(out.root, "apps/viewer"));
  out.daemonState = path.resolve(out.daemonState || path.join(out.root, "models/tmp/r3-browser/daemon"));
  out.output = path.resolve(out.output || path.join(
    out.root, "scripts/bench/cadgen-performance/results/r3-incremental-browser.json",
  ));
  return out;
}

const options = args(process.argv.slice(2));
const sourcePath = path.join(options.root, "models/tmp/r3-browser/repeated24.py");
const cachePath = path.join(options.root, "models/tmp/r3-browser/cache");
const fileRef = "tmp/r3-browser/repeated24.step";
const fixtureSource = `from cadgen import build123d as bd
from cadgen import step

MOVED_X = 0.0
BOX_SIZE = 12.0

@step(out="repeated24.step")
def repeated24():
    box = bd.Box(BOX_SIZE, 10, 8)
    cylinder = bd.Cylinder(5, 8)
    parts = []
    for index in range(12):
        x = (index % 6) * 22
        y = (index // 6) * 34
        if index == 7:
            x += MOVED_X
        box_copy = box.moved(bd.Location((x, y, 0)))
        box_copy.label = f"box_{index + 1}"
        parts.append(box_copy)
        cylinder_copy = cylinder.moved(bd.Location((x, y + 17, 0)))
        cylinder_copy.label = f"cylinder_{index + 1}"
        parts.append(cylinder_copy)
    return bd.Compound(obj=parts, children=parts, label="r3_repeated_24")

if __name__ == "__main__":
    repeated24()
`;
const sourceExisted = fs.existsSync(sourcePath);
const originalSource = sourceExisted ? fs.readFileSync(sourcePath, "utf8") : fixtureSource;
fs.mkdirSync(path.dirname(sourcePath), { recursive: true });
const require = createRequire(path.join(options.browserRoot, "package.json"));
const { chromium } = require("playwright");
const { PNG } = require("pngjs");
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const initialBoxSize = 12.1 + (Date.now() % 1000) / 10000;

function assert(value, message) {
  if (!value) throw new Error(message);
}

function setConstants({ movedX, boxSize }) {
  fs.writeFileSync(sourcePath, originalSource
    .replace(/MOVED_X = [-.\d]+/u, `MOVED_X = ${movedX}`)
    .replace(/BOX_SIZE = [-.\d]+/u, `BOX_SIZE = ${boxSize}`));
}

function runModel() {
  return new Promise((resolve, reject) => {
    const child = spawn(options.python, [sourcePath], {
      cwd: options.root,
      env: {
        ...process.env,
        CADGEN_DAEMON: "1",
        CADGEN_CACHE_DIR: cachePath,
        CADGEN_DAEMON_STATE_DIR: options.daemonState,
        CADGEN_DAEMON_SOCKET: options.daemonSocket,
        PYTHONPATH: path.join(options.root, "packages/cadgen/src"),
      },
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", chunk => { stdout += chunk; });
    child.stderr.on("data", chunk => { stderr += chunk; });
    child.once("error", reject);
    child.once("exit", code => code === 0
      ? resolve(`${stdout}\n${stderr}`)
      : reject(new Error(`model exited ${code}:\n${stdout}\n${stderr}`)));
  });
}

async function chipRef(page) {
  const button = page.locator('button[title*="#o"]:visible').first();
  const title = await button.getAttribute("title", { timeout: 250 }).catch(() => "");
  if (title) return title.replace(/^Copy /u, "").trim();
  const text = await page.locator("text=/Copy .*#o/").filter({ visible: true }).first()
    .textContent({ timeout: 250 }).catch(() => "");
  return text.replace(/^Copy /u, "").trim();
}

async function memory(page) {
  return page.evaluate(() => window.__cadRenderMemoryProbe?.());
}

function stableResources(value) {
  return Object.fromEntries([
    "occurrences", "geometries", "buffers", "materials",
    "surfaceInstanceSets", "surfaceInstances", "edgeInstanceSets", "edgeInstances",
  ].map(key => [key, value[key]]));
}

function pixelDelta(a, b, offset) {
  return Math.abs(a[offset] - b[offset])
    + Math.abs(a[offset + 1] - b[offset + 1])
    + Math.abs(a[offset + 2] - b[offset + 2]);
}

async function targetPixels(page) {
  const canvas = page.locator("canvas").first();
  const box = await canvas.boundingBox();
  assert(box, "primary canvas has no bounds");
  const before = PNG.sync.read(await page.screenshot());
  const collapse = page.getByRole("button", { name: "Collapse box_8", exact: true });
  if (!await collapse.count()) {
    const treeButtons = await page.getByRole("button").evaluateAll(nodes => nodes
      .map(node => node.getAttribute("aria-label")).filter(label => /box_8/u.test(label || "")));
    throw new Error(`expanded box_8 row disappeared; buttons=${JSON.stringify(treeButtons)} body=${(await page.locator("body").innerText()).slice(0, 1200)}`);
  }
  await collapse.locator("xpath=ancestor::*[@role='treeitem'][1]").click();
  await page.waitForTimeout(250);
  const selectedRef = await chipRef(page);
  const occurrence = selectedRef.split("#")[1] || "";
  assert(/^o\S+$/u.test(occurrence), `tree did not select box_8: ${selectedRef}`);
  const after = PNG.sync.read(await page.screenshot());
  const mask = new Set();
  const sheetEdge = await page.getByRole("button", { name: "Resize STEP sidebar", exact: true })
    .boundingBox().catch(() => null);
  const left = Math.max(0, Math.floor(box.x));
  const right = Math.min(after.width - 1, Math.ceil(sheetEdge?.x ?? (box.x + box.width)) - 2);
  const top = Math.max(48, Math.floor(box.y));
  const bottom = Math.min(after.height - 130, Math.ceil(box.y + box.height));
  for (let y = top; y <= bottom; y += 1) for (let x = left; x <= right; x += 1) {
    const offset = (y * after.width + x) * 4;
    if (pixelDelta(before.data, after.data, offset) > 75) mask.add(`${x},${y}`);
  }
  assert(mask.size > 100, `box_8 selection changed only ${mask.size} canvas pixels`);
  const points = [...mask].map(value => value.split(",").map(Number));
  const xs = points.map(point => point[0]);
  const ys = points.map(point => point[1]);
  const bounds = {
    left: Math.min(...xs), right: Math.max(...xs),
    top: Math.min(...ys), bottom: Math.max(...ys),
  };
  const center = { x: (bounds.left + bounds.right) / 2, y: (bounds.top + bounds.bottom) / 2 };
  const boundary = points.filter(([x, y]) => (
    !mask.has(`${x - 3},${y}`) || !mask.has(`${x + 3},${y}`)
    || !mask.has(`${x},${y - 3}`) || !mask.has(`${x},${y + 3}`)
  ));
  const clearCandidates = [
    { x: left + 10, y: top + 10 }, { x: right - 10, y: top + 10 },
    { x: left + 10, y: bottom - 10 }, { x: right - 10, y: bottom - 10 },
  ].filter(point => !mask.has(`${Math.round(point.x)},${Math.round(point.y)}`));
  const clearPoint = await page.evaluate(candidates => {
    const canvas = document.querySelector("canvas");
    return candidates.find(point => document.elementFromPoint(point.x, point.y) === canvas) || null;
  }, clearCandidates);
  assert(clearPoint, "no unobscured blank WebGL point is available");
  return { box, bounds, center, boundary, clearPoint, occurrence,
    viewport: { left, right, top, bottom } };
}

async function hydrateTarget(page) {
  const openSheet = page.getByRole("button", { name: "Expand STEP sheet", exact: true });
  if (await openSheet.count()) await openSheet.click();
  const before = (await memory(page)).assetCaches.selector.entries;
  const expand = page.getByRole("button", { name: "Expand box_8", exact: true });
  if (!await expand.count()) {
    const labels = await page.getByRole("button").evaluateAll(nodes => nodes
      .map(node => node.getAttribute("aria-label")).filter(Boolean));
    throw new Error(`box_8 cannot expand; buttons=${JSON.stringify(labels)}`);
  }
  await expand.click();
  try {
    await page.getByText("Face f1", { exact: true }).waitFor({ timeout: 30000 });
  } catch (error) {
    const labels = await page.getByRole("button").evaluateAll(nodes => nodes
      .map(node => node.getAttribute("aria-label")).filter(Boolean));
    const body = (await page.locator("body").innerText()).slice(0, 2500);
    throw new Error(`box_8 topology did not become ready; buttons=${JSON.stringify(labels)} body=${JSON.stringify(body)}`, { cause: error });
  }
  await page.waitForFunction(
    count => (window.__cadRenderMemoryProbe?.().assetCaches?.selector?.entries || 0) >= count
      && (window.__cadRenderMemoryProbe?.().selectorCpuBytes || 0) > 0,
    before,
  );
  // Expanding can trigger an exact surface-view replacement. The tree rows
  // arrive before the display/selector pair's React adoption receipt.
  await page.waitForTimeout(1200);
}

async function pickingReadiness(page) {
  return page.evaluate(() => {
    let fiber = null;
    for (const canvas of document.querySelectorAll("canvas")) {
      const fiberKey = Object.keys(canvas).find(key => key.startsWith("__reactFiber$"));
      let candidate = fiberKey ? canvas[fiberKey] : null;
      while (candidate) {
        const name = candidate.elementType?.displayName || candidate.elementType?.name
          || candidate.elementType?.render?.name || candidate.type?.displayName
          || candidate.type?.name || candidate.type?.render?.name || "";
        if (String(name).startsWith("CadViewer")) {
          fiber = candidate;
          break;
        }
        candidate = candidate.return;
      }
      if (fiber) break;
    }
    if (!fiber) return { fiberFound: false };
    const props = fiber.memoizedProps || {};
    let renderPaneFiber = fiber.return;
    while (renderPaneFiber) {
      const type = renderPaneFiber.elementType || renderPaneFiber.type;
      const name = type?.displayName || type?.name || type?.render?.name || "";
      if (name === "CadRenderPane") break;
      renderPaneFiber = renderPaneFiber.return;
    }
    const renderPaneProps = renderPaneFiber?.memoizedProps || {};
    const selector = props.selectorRuntime || null;
    let runtime = null;
    let hook = fiber.memoizedState;
    const selectorRefs = [];
    while (hook) {
      const current = hook.memoizedState?.current;
      if (!runtime && current?.displayRecords && current?.facePickGroup && current?.raycaster) runtime = current;
      if (current?.referenceMap instanceof Map && current?.faceReferenceByRowIndex instanceof Map) {
        selectorRefs.push(current);
      }
      hook = hook.next;
    }
    const recordFaceSources = new Map();
    for (const record of runtime?.displayRecords || []) {
      const source = record?.mesh?.userData?.faceIdsSource || null;
      recordFaceSources.set(source, (recordFaceSources.get(source) || 0) + 1);
    }
    const faceIds = Array.from(runtime?.displayRecords || [], record => record?.mesh?.userData?.faceIds?.length || 0);
    return {
      fiberFound: true,
      modelKey: String(props.modelKey || ""),
      pickMode: String(props.pickMode || ""),
      stepUpdateInProgress: renderPaneProps.stepUpdateInProgress === true,
      retainingPreviousStepMesh: renderPaneProps.retainingPreviousStepMesh === true,
      referenceSelectionPending: renderPaneProps.referenceSelectionPending === true,
      viewerLoading: renderPaneProps.viewerLoading === true,
      viewerAlertTitle: String(renderPaneProps.viewerAlert?.title || ""),
      viewerAlertMessage: String(renderPaneProps.viewerAlert?.message || ""),
      renderPaneHasMesh: Boolean(renderPaneProps.selectedMeshData),
      selectorPresent: Boolean(selector),
      selectorReferences: selector?.referenceMap?.size || 0,
      selectorFaces: selector?.faceReferenceByRowIndex?.size || 0,
      selectorEdges: selector?.edgeReferenceByRowIndex?.size || 0,
      selectorProxyTriangles: Math.floor((selector?.proxy?.faceIndices?.length || 0) / 3),
      selectorProxySegments: Math.floor((selector?.proxy?.edgeIndices?.length || 0) / 2),
      pickableFaces: Array.isArray(props.pickableFaces) ? props.pickableFaces.length : 0,
      pickableEdges: Array.isArray(props.pickableEdges) ? props.pickableEdges.length : 0,
      focusedPartIds: Array.isArray(props.focusedPartId) ? props.focusedPartId : [props.focusedPartId].filter(Boolean),
      runtimeFound: Boolean(runtime),
      displayRecords: runtime?.displayRecords?.length || 0,
      facePickTriangles: Math.floor((runtime?.facePickMesh?.geometry?.index?.count || 0) / 3),
      edgePickSegments: Math.floor((runtime?.edgePickLines?.geometry?.index?.count || 0) / 2),
      recordFaceIds: faceIds,
      recordsBoundToPropSelector: recordFaceSources.get(selector) || 0,
      recordsWithoutFaceSource: recordFaceSources.get(null) || 0,
      selectorHookRefMatchesProp: selectorRefs.filter(value => value === selector).length,
      selectorHookRefCount: selectorRefs.length,
    };
  });
}

async function exactPicks(page, evidence) {
  const prefix = `#${evidence.occurrence}.`;
  const found = {};
  const observed = [];
  // Expanding the occurrence in the STEP tree is the topology-mode contract.
  // Do not double-click here: double activation changes focus/isolation state
  // and would make this probe test a different interaction.
  const interior = [];
  for (const fy of [0.25, 0.4, 0.6, 0.75]) for (const fx of [0.25, 0.4, 0.6, 0.75]) {
    interior.push({
      x: evidence.bounds.left + (evidence.bounds.right - evidence.bounds.left) * fx,
      y: evidence.bounds.top + (evidence.bounds.bottom - evidence.bounds.top) * fy,
    });
  }
  const candidatePool = [
    evidence.center,
    ...interior,
    ...evidence.boundary.filter((_, index) => index % Math.max(1, Math.floor(evidence.boundary.length / 24)) === 0)
      .map(([x, y]) => ({ x, y })),
  ];
  const candidates = await page.evaluate(points => {
    const canvas = document.querySelector("canvas");
    return points.filter(point => document.elementFromPoint(point.x, point.y) === canvas);
  }, candidatePool);
  assert(candidates.length > 0, "no exact-pick candidate targets the WebGL canvas");
  for (const point of candidates) {
    // Keep movement and activation in one task: this is the regression for a
    // quick click arriving before the next hover frame.
    await page.mouse.click(point.x, point.y);
    // Single activation commits after the 220ms double-click window.
    await page.waitForTimeout(260);
    const ref = await chipRef(page);
    if (ref) observed.push(ref);
    if (ref.includes(prefix) && /\.f\d+$/u.test(ref) && !found.face) found.face = { ref, point };
    if (ref.includes(prefix) && /\.e\d+$/u.test(ref) && !found.edge) found.edge = { ref, point };
    if (found.face && found.edge) break;
  }
  assert(found.face, `no exact box_8 face pick; observed=${JSON.stringify([...new Set(observed)])} evidence=${JSON.stringify({ bounds: evidence.bounds, center: evidence.center, boundary: evidence.boundary.length })}`);
  assert(found.edge, `no exact box_8 edge pick; observed=${JSON.stringify([...new Set(observed)])} evidence=${JSON.stringify({ bounds: evidence.bounds, center: evidence.center, boundary: evidence.boundary.length })}`);
  return found;
}

async function hoverPixels(page, point, canvasBox, clearPoint, viewport) {
  await page.mouse.click(clearPoint.x, clearPoint.y);
  await page.waitForTimeout(260);
  assert(!await chipRef(page), "blank WebGL click did not clear selection");
  await page.mouse.move(clearPoint.x, clearPoint.y);
  await page.waitForTimeout(260);
  const before = PNG.sync.read(await page.screenshot());
  await page.mouse.move(point.x, point.y);
  await page.waitForTimeout(250);
  const after = PNG.sync.read(await page.screenshot());
  let changed = 0;
  for (let y = Math.floor(viewport.top); y <= Math.ceil(viewport.bottom); y += 1) {
    for (let x = Math.floor(viewport.left); x <= Math.ceil(viewport.right); x += 1) {
      if (pixelDelta(before.data, after.data, (y * after.width + x) * 4) > 40) changed += 1;
    }
  }
  return changed;
}

function assertPickingReady(readiness, phase) {
  assert(readiness.fiberFound && readiness.runtimeFound, `${phase}: picking runtime unavailable`);
  assert(readiness.pickMode === "auto", `${phase}: unexpected pick mode ${readiness.pickMode}`);
  assert(!readiness.stepUpdateInProgress && !readiness.referenceSelectionPending
    && !readiness.retainingPreviousStepMesh && !readiness.viewerLoading && readiness.renderPaneHasMesh,
  `${phase}: scene/reference adoption is still pending: ${JSON.stringify(readiness)}`);
  assert(readiness.selectorPresent && readiness.pickableFaces > 0 && readiness.pickableEdges > 0,
    `${phase}: selector topology is not pickable: ${JSON.stringify(readiness)}`);
  assert(readiness.recordsBoundToPropSelector === readiness.displayRecords,
    `${phase}: display records do not own the current selector: ${JSON.stringify(readiness)}`);
}

async function revise(page, constants, previousCount, baseline) {
  setConstants(constants);
  let settled = false;
  const samples = [];
  const build = runModel().finally(() => { settled = true; });
  while (!settled) {
    const sample = await page.evaluate(() => ({
      memory: window.__cadRenderMemoryProbe?.(),
      sync: structuredClone(window.__cadSceneSync),
    }));
    if (sample.memory) samples.push(sample);
    await pause(10);
  }
  const output = await build;
  await page.waitForFunction(count => (window.__cadSceneSync?.count || 0) > count, previousCount, { timeout: 30000 });
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await page.waitForTimeout(250); // Let the following saved-result response reduce before interaction.
  const final = await page.evaluate(() => ({
    memory: window.__cadRenderMemoryProbe(),
    sync: structuredClone(window.__cadSceneSync),
  }));
  samples.push(final);
  for (const sample of samples) {
    const detail = JSON.stringify({
      observed: stableResources(sample.memory),
      baseline: stableResources(baseline),
      sync: sample.sync,
      at: sample.memory.at,
    });
    assert(sample.memory.occurrences >= baseline.occurrences, `replacement blanked displayed occurrences: ${detail}`);
    assert(sample.memory.geometries > 0 && sample.memory.buffers > 0,
      `replacement has no display resources: ${detail}`);
  }
  const entries = final.sync.entries.slice(previousCount);
  assert(entries.length > 0 && entries.every(entry => entry.records === baseline.occurrences),
    `partial scene publication: ${JSON.stringify(entries)}`);
  return { output, samples, ...final, entries };
}

async function failReplacement(page, constants) {
  let failedGlbResponses = 0;
  const interceptedResponses = [];
  const storeRoute = async route => {
    const response = await route.fetch();
    const contentType = String(response.headers()["content-type"] || "").toLowerCase();
    const body = await response.body();
    const magic = body.subarray(0, 4).toString("ascii");
    interceptedResponses.push({
      url: route.request().url(),
      status: response.status(),
      contentType,
      bytes: body.length,
      magic,
    });
    if (contentType.includes("gltf-binary") || magic === "glTF" || magic === "SURF") {
      failedGlbResponses += 1;
      await route.abort("failed");
      return;
    }
    await route.fulfill({ response, body });
  };
  await page.route("**/__cad/store?*", storeRoute);
  try {
    setConstants(constants);
    await runModel();
    const deadline = Date.now() + 30000;
    let readiness = null;
    while (Date.now() < deadline) {
      readiness = await pickingReadiness(page);
      if (
        readiness.retainingPreviousStepMesh &&
        !readiness.viewerLoading &&
        (readiness.viewerAlertTitle || readiness.viewerAlertMessage)
      ) break;
      await pause(25);
    }
    assert(readiness?.retainingPreviousStepMesh,
      `failed replacement did not retain its predecessor: ${JSON.stringify({ readiness, interceptedResponses })}`);
    assert(readiness.pickMode === "none" && !readiness.selectorPresent &&
      readiness.pickableFaces === 0 && readiness.pickableEdges === 0,
    `failed retained scene remained interactive: ${JSON.stringify(readiness)}`);
    assert(readiness.displayRecords === 24,
      `failed replacement blanked the old display: ${JSON.stringify(readiness)}`);
    assert(failedGlbResponses > 0, "failure injection intercepted no component GLB");
    const attemptsAtFailure = failedGlbResponses;
    await pause(1200);
    assert(failedGlbResponses === attemptsAtFailure,
      `failed target retried automatically (${attemptsAtFailure} -> ${failedGlbResponses})`);
    return {
      failedGlbResponses,
      interceptedResponses,
      readiness,
      resources: stableResources(await memory(page)),
      sceneCount: await page.evaluate(() => window.__cadSceneSync?.count || 0),
    };
  } finally {
    await page.unroute("**/__cad/store?*", storeRoute);
  }
}

let browser;
const diagnostics = { fixture: fileRef };
try {
  setConstants({ movedX: 0, boxSize: initialBoxSize });
  fs.appendFileSync(sourcePath, `\n# browser probe ${Date.now()}\n`);
  browser = await chromium.launch({ headless: true, args: ["--use-angle=metal"] });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const errors = [];
  const expectedFailureErrors = [];
  let failureInjectionActive = false;
  page.on("pageerror", error => errors.push(String(error)));
  page.on("console", message => {
    if (message.type() !== "error") return;
    (failureInjectionActive ? expectedFailureErrors : errors).push(message.text());
  });
  // The held preview request deliberately prevents networkidle.
  await page.goto(`${options.url}/?file=${encodeURIComponent(fileRef)}&mode=editing`, {
    waitUntil: "domcontentloaded", timeout: 60000,
  });
  await page.waitForFunction(() => (window.__cadRenderMemoryProbe?.().occurrences || 0) === 24, null, { timeout: 30000 });
  const initialSavedCount = await page.evaluate(() => window.__cadSceneSync?.count || 0);
  await runModel(); // Attach after the held/retrying editing feed exists.
  await page.waitForFunction(count => (window.__cadSceneSync?.count || 0) > count, initialSavedCount, { timeout: 30000 });
  await page.waitForTimeout(1200); // Initial preview and saved-result feed responses are distinct.
  await hydrateTarget(page);

  const initialEvidence = await targetPixels(page);
  const initialReadiness = await pickingReadiness(page);
  diagnostics.initialReadiness = initialReadiness;
  assertPickingReady(initialReadiness, "initial");
  const initialPicks = await exactPicks(page, initialEvidence);
  const initialHover = await hoverPixels(page, initialPicks.face.point, initialEvidence.box,
    initialEvidence.clearPoint, initialEvidence.viewport);
  const initial = {
    memory: await memory(page),
    sync: await page.evaluate(() => structuredClone(window.__cadSceneSync)),
  };

  const placement = await revise(
    page, { movedX: 15, boxSize: initialBoxSize }, initial.sync.count, initial.memory,
  );
  await hydrateTarget(page);
  const placementEvidence = await targetPixels(page);
  const placementReadiness = await pickingReadiness(page);
  diagnostics.placementReadiness = placementReadiness;
  assertPickingReady(placementReadiness, "placement");
  assert(placementEvidence.occurrence === initialEvidence.occurrence, "placement changed box_8 occurrence identity");
  const placementPicks = await exactPicks(page, placementEvidence);
  const placementHover = await hoverPixels(page, placementPicks.face.point, placementEvidence.box,
    placementEvidence.clearPoint, placementEvidence.viewport);
  placement.postInteractionMemory = await memory(page);
  assert(Math.hypot(
    placementEvidence.center.x - initialEvidence.center.x,
    placementEvidence.center.y - initialEvidence.center.y,
  ) > 3, "placement revision did not visibly move box_8");

  failureInjectionActive = true;
  const failedReplacement = await failReplacement(
    page, { movedX: 15, boxSize: initialBoxSize + 0.5 },
  );
  failureInjectionActive = false;

  const geometry = await revise(
    page, { movedX: 15, boxSize: initialBoxSize + 1 },
    failedReplacement.sceneCount, placement.postInteractionMemory,
  );
  await hydrateTarget(page);
  const geometryEvidence = await targetPixels(page);
  const geometryReadiness = await pickingReadiness(page);
  diagnostics.geometryReadiness = geometryReadiness;
  assertPickingReady(geometryReadiness, "component replacement");
  assert(geometryEvidence.occurrence === initialEvidence.occurrence, "replacement changed box_8 occurrence identity");
  const geometryPicks = await exactPicks(page, geometryEvidence);
  const geometryHover = await hoverPixels(page, geometryPicks.face.point, geometryEvidence.box,
    geometryEvidence.clearPoint, geometryEvidence.viewport);
  geometry.postInteractionMemory = await memory(page);
  const placementArea = (placementEvidence.bounds.right - placementEvidence.bounds.left)
    * (placementEvidence.bounds.bottom - placementEvidence.bounds.top);
  const geometryArea = (geometryEvidence.bounds.right - geometryEvidence.bounds.left)
    * (geometryEvidence.bounds.bottom - geometryEvidence.bounds.top);
  assert(Math.abs(geometryArea - placementArea) > 20,
    `geometry revision did not visibly resize box_8: ${placementArea} -> ${geometryArea}`);

  for (const [name, state] of [["placement", placement], ["geometry", geometry]]) {
    assert(JSON.stringify(stableResources(state.postInteractionMemory)) === JSON.stringify(stableResources(initial.memory)),
      `${name} leaked live renderer resources: ${JSON.stringify(stableResources(state.postInteractionMemory))}`);
    const policy = state.postInteractionMemory.memoryPolicy;
    assert(policy.reservationCount === 0 && policy.retainedByCategory.replacementPending === 0,
      `${name} left replacement ownership pending`);
    assert(Object.keys(policy.inFlightByCategory || {}).length === 0, `${name} left in-flight ownership`);
  }
  assert(Math.min(initialHover, placementHover, geometryHover) > 100, "face hover produced no visible highlight");
  assert(errors.length === 0, `browser errors:\n${errors.join("\n")}`);

  const result = {
    status: "passed",
    fixture: fileRef,
    targetOccurrence: initialEvidence.occurrence,
    initial: {
      picks: initialPicks, hoverChangedPixels: initialHover,
      resources: stableResources(initial.memory), selectorEntries: initial.memory.assetCaches.selector.entries,
      readiness: initialReadiness,
    },
    placement: {
      picks: placementPicks, hoverChangedPixels: placementHover,
      resources: stableResources(placement.memory), selectorEntries: placement.memory.assetCaches.selector.entries,
      postInteractionResources: stableResources(placement.postInteractionMemory),
      sceneUpdates: placement.entries, sampledFrames: placement.samples.length,
      readiness: placementReadiness,
    },
    componentReplacement: {
      picks: geometryPicks, hoverChangedPixels: geometryHover,
      resources: stableResources(geometry.memory), selectorEntries: geometry.memory.assetCaches.selector.entries,
      postInteractionResources: stableResources(geometry.postInteractionMemory),
      sceneUpdates: geometry.entries, sampledFrames: geometry.samples.length,
      readiness: geometryReadiness,
    },
    failedReplacement: {
      ...failedReplacement,
      expectedConsoleErrors: expectedFailureErrors,
    },
    errors,
  };
  fs.mkdirSync(path.dirname(options.output), { recursive: true });
  fs.writeFileSync(options.output, `${JSON.stringify(result, null, 2)}\n`);
  console.log(JSON.stringify(result, null, 2));
} catch (error) {
  const result = {
    status: "failed",
    ...diagnostics,
    error: error instanceof Error ? error.stack : String(error),
  };
  fs.mkdirSync(path.dirname(options.output), { recursive: true });
  fs.writeFileSync(options.output, `${JSON.stringify(result, null, 2)}\n`);
  throw error;
} finally {
  if (sourceExisted) fs.writeFileSync(sourcePath, originalSource);
  else if (fs.existsSync(sourcePath)) fs.unlinkSync(sourcePath);
  await browser?.close();
}
