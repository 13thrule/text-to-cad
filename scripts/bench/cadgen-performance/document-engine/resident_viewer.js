// Bounded integration client. Uses the same mesh adoption, model records,
// lighting, camera framing and exact picking functions as shipping consumers.
import * as THREE from "../../../../packages/cadgen-js/node_modules/three/build/three.module.js";
import { OrbitControls } from "../../../../packages/cadgen-js/node_modules/three/examples/jsm/controls/OrbitControls.js";
import { adoptDocumentScene } from "../../../../packages/cadgen-js/src/lib/render/documentScene.js";
import { documentFaceReference } from "../../../../packages/cadgen-js/src/lib/render/documentPicking.js";
import { buildModel } from "../../../../packages/cadgen-js/src/common/cadScene.js";
import { renderModel, renderJobContext, modelOptionsForRenderJob, fitPerspectiveCamera } from "../../../../packages/cadgen-js/src/common/renderMeshScene.js";
import { syncScreenSpaceLineMaterialResolution } from "../../../../packages/cadgen-js/src/common/renderEdges.js";
import { fitCameraDepthToBounds } from "../../../../packages/cadgen-js/src/common/renderOptions.js";

const token = new URL(location.href).searchParams.get("token");
const status = document.querySelector("#status"), facts = document.querySelector("#facts");
const header = document.querySelector("header");
const selectedModel = new URL(location.href).searchParams.get("model");
if (["plate", "assembly24"].includes(selectedModel)) document.querySelector("#model").value = selectedModel;
const selectedView = new URL(location.href).searchParams.get("view") || "inspect-light";
if (["inspect-light", "inspect-dark", "render-light", "render-dark"].includes(selectedView))
  document.querySelector("#view").value = selectedView;
const photographic = document.querySelector("#view").value.startsWith("render");
let source = null, model = null, viewport = null, camera = null, controls = null;
let radius = 3, z = 0, busy = false;
const known = new Set();
const errors = [];
window.reviewErrors = errors;
async function post(path, value) {
  const response = await fetch(path, { method: "POST", headers: {
    "Content-Type": "application/json", "X-Review-Token": token }, body: JSON.stringify(value) });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `Request failed (${response.status})`);
  return result;
}
function draw() {
  if (photographic) fitCameraDepthToBounds(camera, model.bounds);
  const size = viewport.renderer.getDrawingBufferSize(new THREE.Vector2());
  syncScreenSpaceLineMaterialResolution(model.runtime.screenSpaceLineMaterials, size.x, size.y);
  viewport.renderer.render(viewport.scene, camera);
}
function resize() {
  if (!viewport) return;
  const width = Math.max(200, innerWidth - 310), height = innerHeight - header.offsetHeight;
  viewport.renderer.setSize(width, height);
  camera.aspect = width / height;
  fitPerspectiveCamera(camera, viewport.context.camera, model.bounds, width, height);
  camera.updateProjectionMatrix();
  draw();
}
window.addEventListener("resize", resize);
window.generateReview = async (kind = "unchanged") => {
  if (busy) throw new Error("A review request is already running");
  busy = true; status.textContent = "Building";
  if (kind === "geometry") radius = radius === 3 ? 3.5 : 3;
  if (kind === "placement") z = z === 0 ? 8 : 0;
  const started = performance.now();
  try {
    const result = await post("/generate", { model: document.querySelector("#model").value,
      radius, z, known: [...known], render: photographic });
    const received = performance.now();
    const previous = source;
    source = await adoptDocumentScene(result.manifest, async (id) => {
      const response = await fetch(`/mesh/${id}?token=${token}`);
      if (!response.ok) throw new Error("Mesh asset unavailable");
      const payload = await response.arrayBuffer();
      known.add(id);
      return payload;
    }, { previous });
    // Keep known hints bounded to assets attested by the currently owned scene.
    const needed = new Set(Object.values(result.manifest.prototypes).map((row) => row.mesh));
    for (const id of known) if (!needed.has(id)) known.delete(id);
    const adopted = performance.now();
    const geometries = new Set(model?.displayRecords.map((row) => row.geometry) || []);
    if (!model) {
      const job = { kind: "step", appearance: document.querySelector("#view").value.endsWith("dark") ? "dark" : "light",
        ...(photographic ? { render: { quality: "final" } } : {}), output: { width: 1200, height: 900, renderScale: 1 } };
      const context = renderJobContext(source, job);
      model = buildModel(THREE, source, modelOptionsForRenderJob(context, job));
      viewport = renderModel(THREE, model, { context, job });
      // The snapshot renderer owns its canvas body; restore this test shell
      // around that canvas rather than duplicating its render setup.
      document.body.prepend(header, facts);
      await viewport.ready;
      camera = viewport.perspectiveCamera;
      fitPerspectiveCamera(camera, context.camera, model.bounds,
        Math.max(200, innerWidth - 310), innerHeight - header.offsetHeight);
      controls = new OrbitControls(camera, viewport.renderer.domElement);
      controls.target.copy(new THREE.Box3(new THREE.Vector3(...model.bounds.min),
        new THREE.Vector3(...model.bounds.max)).getCenter(new THREE.Vector3()));
      controls.addEventListener("change", draw);
      controls.update();
      if (!photographic) viewport.renderer.domElement.addEventListener("click", pick);
      resize();
    } else model.update({ source });
    draw();
    const gl = viewport.renderer.getContext();
    gl.finish(); // Explicit GPU-completion diagnostic, not a compositor timestamp.
    const completed = performance.now();
    await new Promise(requestAnimationFrame);
    window.reviewResult = { kind, view: document.querySelector("#view").value, parts: source.parts.length, revision: source.documentRevision,
      generationMs: result.generationMs, displayMs: result.displayMs,
      requestMs: received-started, adoptionMs: adopted-received,
      sceneAndGpuMs: completed-adopted, acceptedToGpuMs: completed-started,
      transferredMeshes: result.transferredMeshes, transferredMeshBytes: result.transferredMeshBytes,
      retainedGeometryRecords: model.displayRecords.filter((row) => geometries.has(row.geometry)).length,
      uniqueGeometries: new Set(model.displayRecords.map((row) => row.geometry)).size,
      evaluations: result.generation.evaluations, products: result.generation.products };
    facts.textContent = JSON.stringify(window.reviewResult, null, 2);
    status.textContent = "Complete";
    return window.reviewResult;
  } catch (error) {
    errors.push(String(error)); status.textContent = "Failed"; facts.textContent = error.stack; throw error;
  } finally { busy = false; }
};
async function pick(event) {
  if (busy) return;
  const rect = viewport.renderer.domElement.getBoundingClientRect();
  const pointer = new THREE.Vector2((event.clientX-rect.left)/rect.width*2-1,
    1-(event.clientY-rect.top)/rect.height*2);
  const ray = new THREE.Raycaster(); ray.setFromCamera(pointer, camera);
  const hits = model.displayRecords.flatMap((record) => ray.intersectObject(record.mesh, false)
    .filter((hit) => Number.isInteger(hit.faceIndex)).map((hit) => ({ record, hit })))
    .sort((a, b) => a.hit.distance-b.hit.distance);
  for (const { record, hit } of hits.slice(0, 1)) {
    const reference = documentFaceReference(source, record.partId, hit.faceIndex);
    const result = await post("/query", { reference });
    window.reviewPick = { reference, ...result };
    facts.textContent = JSON.stringify(window.reviewPick, null, 2);
    return;
  }
}
for (const kind of ["unchanged", "geometry", "placement"])
  document.querySelector(`#${kind}`).onclick = () => window.generateReview(kind).catch(() => {});
for (const id of ["model", "view"]) document.querySelector(`#${id}`).onchange = () => {
  const url = new URL(location.href); url.searchParams.set(id, document.querySelector(`#${id}`).value);
  location.href = url.href;
};
await window.generateReview();
