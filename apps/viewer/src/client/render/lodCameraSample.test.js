import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";
import { lodSceneMayMove, sampleLodCamera, resampleLodAfterViewportResize } from "./lodCameraSample.js";
import { createLodScheduler } from "./lodScheduler.js";

const bounds = (min, max) => ({ min, max });
const cube = (x, y = 0, z = 0) => bounds([x - .5, y - .5, z - .5], [x + .5, y + .5, z + .5]);
function fixture(entries) {
  const camera = new THREE.OrthographicCamera(-5, 5, 5, -5, 1, 20);
  camera.position.set(0, 0, 10); camera.lookAt(0, 0, 0);
  const components = new Map();
  const displayRecords = entries.map(([cid, partBounds]) => {
    if (!components.has(cid)) components.set(cid, { centers: [], diagonal: 2, level: 0 });
    components.get(cid).centers.push(partBounds.min.map((value, axis) => (value + partBounds.max[axis]) / 2));
    return { sourcePart: { componentId: cid }, partBounds, mesh: { visible: true }, material: { visible: true } };
  });
  return { runtime: { camera, modelGroup: new THREE.Group(), renderer: { domElement: { clientHeight: 1000 } }, displayRecords }, components };
}
function sample(f, options = {}) { return sampleLodCamera(THREE, f.runtime, { components: f.components, ...options }); }

test("full boxes crossing side/near/far planes remain eligible when their centers are outside", () => {
  const f = fixture([
    ["side", bounds([4.9, -.1, 0], [5.3, .1, 1])],
    ["near", bounds([-.1, -.1, 8.8], [.1, .1, 9.4])],
    ["far", bounds([-.1, -.1, -10.4], [.1, .1, -9.8])],
    ["offside", cube(8)], ["behind", cube(0, 0, 12)], ["beyond", cube(0, 0, -12)],
  ]);
  const s = sample(f);
  for (const cid of ["side", "near", "far"]) assert.ok(Number.isFinite(s.distanceFor(cid)), cid);
  for (const cid of ["offside", "behind", "beyond"]) {
    assert.equal(s.visibleFor(cid), false, cid);
    assert.ok(Number.isFinite(s.distanceFor(cid)), "retained distance supports pressure coarsening");
  }
  assert.equal(s.visibility.visibleComponents, 3); assert.equal(s.visibility.excludedComponents, 3);
});

test("a repeated component uses the nearest visible occurrence, ignoring display/material visibility flags", () => {
  const f = fixture([["same", cube(6, 0, 8)], ["same", cube(0)]]);
  f.runtime.displayRecords[1].mesh.visible = false;
  f.runtime.displayRecords[1].material.visible = false;
  f.runtime.displayRecords[1].effectVisible = false;
  const s = sample(f);
  assert.equal(s.distanceFor("same"), 10);
  assert.equal(s.visibility.visibleOccurrences, 1); assert.equal(s.visibility.excludedOccurrences, 1);
  assert.equal(s.visibility.excludedComponents, 0);
});

test("occurrence bounds include base placement once; rotated mirrored/nonuniform group and parent transforms stay live", () => {
  const f = fixture([["part", cube(7)]]), r = f.runtime.displayRecords[0];
  r.baseTransform = new THREE.Matrix4().makeTranslation(100, 0, 0).toArray();
  const parent = new THREE.Group(); parent.add(f.runtime.modelGroup);
  f.runtime.modelGroup.scale.set(-2, .5, 3);
  f.runtime.modelGroup.rotation.z = Math.PI / 2;
  parent.position.y = 14;
  const s = sample(f);
  assert.ok(Number.isFinite(s.distanceFor("part")), "base placement must not be reapplied");
  assert.ok(Math.abs(s.distanceFor("part") - 10) < 1e-8);
  parent.position.x = 20;
  assert.equal(sample(f).visibleFor("part"), false);
  assert.equal(s.distanceFor("part"), 10, "the prior numeric camera sample is immutable");
});

test("missing, partial or invalid occurrence bounds use conservative summary fallback", () => {
  const f = fixture([["partial", cube(9)], ["partial", cube(0)], ["invalid", cube(0)], ["missing", cube(2)]]);
  f.runtime.displayRecords.splice(3, 1); f.runtime.displayRecords.splice(1, 1);
  f.runtime.displayRecords[1].partBounds = bounds([NaN, 0, 0], [1, 1, 1]);
  const s = sample(f);
  assert.equal(s.distanceFor("partial"), 10);
  for (const cid of f.components.keys()) assert.ok(Number.isFinite(s.distanceFor(cid)));
  assert.equal(s.visibility.fallbackComponents, 3);
  assert.equal(s.visibility.fallbackOccurrences, 1); assert.equal(s.visibility.pendingOccurrences, 2);
});

test("any joint/module capability, including paused or disabled state, fails open", () => {
  assert.equal(lodSceneMayMove(), false);
  for (const capability of [{ robot: true }, { drawing: true }, { kinematics: { parameterValues: {} } },
    { kinematicsLoading: true }, { renderModuleUrl: "paused.step.js" }, { exploded: true }]) {
    const f = fixture([["offscreen", cube(20)]]);
    const s = sample(f, { dynamicScene: lodSceneMayMove(capability) });
    assert.ok(Number.isFinite(s.distanceFor("offscreen")));
    assert.equal(s.visibility.dynamicFailOpen, 1); assert.equal(s.visibility.excludedComponents, 0);
  }
});

test("animated, collapsing, CPU and GPU deformed records fail open even without capability metadata", () => {
  for (const effect of [{ effectMatrix: new THREE.Matrix4().makeTranslation(30, 0, 0) },
    { explodedViewMatrix: new THREE.Matrix4().makeTranslation(30, 0, 0) },
    { effectDeformation: {} }, { tubeDeformationState: { active: true } }, { tubeGpuState: { active: true } }]) {
    const f = fixture([["posed", cube(20)], ["other", cube(-20)]]);
    Object.assign(f.runtime.displayRecords[0], effect);
    const s = sample(f);
    assert.ok(Number.isFinite(s.distanceFor("posed"))); assert.ok(Number.isFinite(s.distanceFor("other")));
    assert.equal(s.visibility.dynamicFailOpen, 1); assert.equal(s.visibility.excludedComponents, 0);
  }
});

test("perspective cameras also retain intersecting boxes and see camera-parent transforms", () => {
  const f = fixture([["center", cube(0)], ["offscreen", cube(20)]]);
  const camera = new THREE.PerspectiveCamera(45, 1, 1, 20);
  camera.position.set(0, 0, 10); camera.lookAt(0, 0, 0);
  const parent = new THREE.Group(); parent.add(camera); f.runtime.camera = camera;
  assert.equal(sample(f).distanceFor("center"), 10);
  assert.equal(sample(f).visibleFor("offscreen"), false);
  parent.position.x = 20;
  assert.equal(sample(f).distanceFor("offscreen"), 10);
  assert.equal(sample(f).visibleFor("center"), false);
});

test("visibility exclusion preserves the scheduler's canonical floor for every component", async () => {
  const f = fixture([["offscreen", cube(20)], ["also-offscreen", cube(-20)]]);
  for (const minimumLevel of [0, 1]) {
    let timer; const loads = [];
    const scheduler = createLodScheduler({ minimumLevel,
      setTimeoutFn: fn => { timer = fn; return 1; }, clearTimeoutFn: () => {},
      loadLevel: async (cid, level) => { loads.push([cid, level]); return {}; }, applyLevel: () => {} });
    scheduler.setComponents([...f.components].map(([cid, value]) => ({ cid, ...value })));
    scheduler.onCameraSample(sample(f)); timer();
    for (let i = 0; i < 20; i++) await Promise.resolve();
    assert.equal(loads.length, minimumLevel ? 2 : 0);
    for (const cid of f.components.keys()) assert.equal(scheduler.levelOf(cid), minimumLevel);
    assert.equal(scheduler.busy(), false); scheduler.dispose();
  }
});

test("pressure releases offscreen L3 first, while normal exclusion retains existing detail and pressure honors the floor", async () => {
  const f = fixture([["visible", cube(0)], ["offscreen", cube(20)]]);
  for (const pressure of [false, true]) {
    let timer; const loads = [];
    const scheduler = createLodScheduler({ minimumLevel: 1, memoryPressure: () => pressure,
      setTimeoutFn: fn => { timer = fn; return 1; }, clearTimeoutFn: () => {},
      loadLevel: async (cid, level) => { loads.push([cid, level]); return {}; }, applyLevel: () => {} });
    scheduler.setComponents([...f.components].map(([cid, value]) => ({ cid, ...value, level: 3 })));
    scheduler.onCameraSample(sample(f)); timer();
    for (let i = 0; i < 60; i++) await Promise.resolve();
    if (pressure) {
      assert.deepEqual(loads.slice(0, 2), [["offscreen", 2], ["offscreen", 1]]);
      assert.equal(scheduler.levelOf("offscreen"), 1);
      assert.equal(scheduler.levelOf("visible"), 1);
      assert.ok(loads.every(([, level]) => level >= 1));
    } else {
      assert.equal(scheduler.levelOf("offscreen"), 3);
      assert.ok(loads.every(([cid]) => cid !== "offscreen"));
    }
    scheduler.dispose();
  }
});

test("resize resamples newly visible parts even with unchanged framing/persisted perspective", () => {
  const f = fixture([["side", cube(7)]]);
  assert.equal(sample(f).visibleFor("side"), false);
  const events = [];
  f.runtime.camera.left = -10; f.runtime.camera.right = 10;
  f.runtime.camera.updateProjectionMatrix();
  let next;
  const callbacks = { syncFraming: () => false, syncZoom: () => events.push("zoom"),
    emitPerspective: () => events.push("perspective"), resample: () => { events.push("lod"); next = sample(f); } };
  resampleLodAfterViewportResize(f.runtime, callbacks);
  assert.equal(next.visibleFor("side"), true);
  assert.deepEqual(events, ["lod"]);
  events.length = 0;
  resampleLodAfterViewportResize(f.runtime, { ...callbacks, syncFraming: () => true });
  assert.deepEqual(events, ["zoom", "perspective", "lod"]);
});

test("live pose/post-transform order matches the displayed center without mutating bounds or transforms", () => {
  const f = fixture([["posed", cube(1)]]), r = f.runtime.displayRecords[0];
  r.baseTransform = new THREE.Matrix4().makeTranslation(100, 0, 0).toArray();
  r.effectMatrix = new THREE.Matrix4().makeRotationZ(Math.PI / 2);
  r.explodedViewMatrix = new THREE.Matrix4().makeTranslation(0, 3, 0);
  f.runtime.modelGroup.rotation.z = Math.PI / 2; f.runtime.modelGroup.position.x = 10;
  const before = JSON.stringify([r.partBounds, r.baseTransform, r.effectMatrix.elements, r.explodedViewMatrix.elements]);
  const s = sample(f);
  assert.ok(Math.abs(s.distanceFor("posed") - Math.sqrt(136)) < 1e-8);
  assert.equal(JSON.stringify([r.partBounds, r.baseTransform, r.effectMatrix.elements, r.explodedViewMatrix.elements]), before);
  assert.ok(Object.values(s.visibility).every(Number.isFinite), "diagnostics contain only numeric counts");
});
