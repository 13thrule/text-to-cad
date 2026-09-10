import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";
import { buildModel } from "cadgen-js/common/cadScene.js";
import { buildComposedPackageMeshData } from "cadgen-js/lib/assembly/meshData.js";
import { createLodSceneAdoption } from "./lodSceneAdoption.js";
import { createLodScheduler } from "./lodScheduler.js";

const bounds = { min: [0, 0, 0], max: [2, 1, 1] };
function mesh(version) {
  return { version, vertices: new Float32Array([0, 0, 0, 1 + version / 10, 0, 0, 0, 1, 0]),
    normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]), indices: new Uint32Array([0, 1, 2]), bounds,
    parts: [{ id: "surface", vertexCount: 3, triangleCount: 1 }] };
}
function source(rows) {
  return { bounds, parts: rows.map(([id, cid, value]) => ({ id, occurrenceId: id, componentId: cid,
    sourceMesh: value, sourceMeshKey: `${cid}:${value.version}`, bounds, vertexCount: 3, triangleCount: 1 })) };
}
function fixture() {
  const payload = mesh(1);
  const published = source([["a1", "a", payload], ["a2", "a", payload]]);
  let ctx = { file: "same.step", meshHash: "revision-a", meshData: published }, time = 0;
  const tracker = createLodSceneAdoption({ currentContext: () => ctx, now: () => time });
  return { payload, published, tracker, get ctx() { return ctx; }, set ctx(value) { ctx = value; },
    advance: value => { time += value; },
    expect: signal => tracker.expect({ context: ctx, source: published, componentId: "a", componentMesh: payload, signal }) };
}
async function ticks(count = 12) { for (let i = 0; i < count; i++) await Promise.resolve(); }

test("only actual current source adoption releases the exact component payload", async () => {
  const f = fixture(); let done = false;
  const promise = f.expect().then(value => { done = true; return value; });
  await ticks(); assert.equal(done, false); assert.equal(f.tracker.snapshot().pending, 1);
  assert.equal(f.tracker.adopted({ ...f.published }), false, "equal-looking source is not adopted identity");
  await ticks(); assert.equal(done, false);
  f.advance(35); assert.equal(f.tracker.adopted(f.published), true);
  assert.equal(await promise, true);
  assert.deepEqual(f.tracker.snapshot(), { requested: 1, adopted: 1, rejected: 0, lastWaitMs: 35, maxWaitMs: 35, pending: 0, pendingMs: 0 });
});

test("progressive supersession acknowledges the current larger source carrying every exact occurrence", async () => {
  const f = fixture(), promise = f.expect();
  const expanded = source([["a1", "a", f.payload], ["a2", "a", f.payload], ["b1", "b", mesh(0)]]);
  f.ctx.meshData = expanded;
  assert.equal(f.tracker.adopted(f.published), false);
  assert.equal(f.tracker.snapshot().pending, 1);
  assert.equal(f.tracker.adopted(expanded), true); assert.equal(await promise, true);
});

test("immutable descriptor composition publishes all occurrences of each available component together", async () => {
  const occurrences = Object.freeze([
    Object.freeze({ id: "a1", component: "a" }), Object.freeze({ id: "b1", component: "b" }),
    Object.freeze({ id: "a2", component: "a" }),
  ]);
  const descriptor = Object.freeze({ occurrences, assembly: { root: { id: "root", nodeType: "assembly",
    children: occurrences.map(({ id }) => ({ id, nodeType: "part", children: [] })) } } });
  const a = mesh(1), first = buildComposedPackageMeshData(descriptor, { a });
  assert.deepEqual(first.parts.map(part => part.id), ["a1", "a2"]);
  const ctx = { file: "same.step", meshHash: "revision", meshData: first };
  const tracker = createLodSceneAdoption({ currentContext: () => ctx });
  const adopted = tracker.expect({ context: ctx, source: first, componentId: "a", componentMesh: a });
  ctx.meshData = buildComposedPackageMeshData(descriptor, { a, b: mesh(0) }, { previous: first });
  assert.deepEqual(ctx.meshData.parts.filter(part => part.componentId === "a").map(part => part.id), ["a1", "a2"]);
  assert.equal(tracker.adopted(ctx.meshData), true);
  assert.equal(await adopted, true);
});

test("wrong payload, missing/duplicate/unexpected occurrences reject and clear references", async () => {
  for (const rows of [
    f => [["a1", "a", mesh(1)], ["a2", "a", f.payload]],
    f => [["a1", "a", f.payload]],
    f => [["a1", "a", f.payload], ["a1", "a", f.payload]],
    f => [["a1", "a", f.payload], ["other", "a", f.payload]],
  ]) {
    const f = fixture(), promise = f.expect(); f.ctx.meshData = source(rows(f));
    assert.equal(f.tracker.adopted(f.ctx.meshData), false); assert.equal(await promise, false);
    assert.equal(f.tracker.snapshot().pending, 0);
  }
});

test("same-file context/revision changes reject stale adoption even when geometry is shared", async () => {
  for (const change of [f => { f.ctx = { ...f.ctx }; }, f => { f.ctx.meshHash = "revision-b"; }, f => { f.ctx = null; }]) {
    const f = fixture(), promise = f.expect(); change(f);
    assert.equal(f.tracker.adopted(f.published), false); assert.equal(await promise, false);
    assert.equal(f.tracker.snapshot().pending, 0);
  }
});

test("abort/replacement removes prior listeners; stale failure cannot reject a newer source", async () => {
  const f = fixture(), first = new AbortController(), second = new AbortController();
  const old = f.expect(first.signal); const current = f.expect(second.signal);
  assert.equal(await old, false); first.abort();
  assert.equal(f.tracker.snapshot().pending, 1);
  f.tracker.failed({ ...f.published }); assert.equal(f.tracker.snapshot().pending, 1);
  second.abort(); assert.equal(await current, false); assert.equal(f.tracker.snapshot().pending, 0);
  const alreadyAborted = new AbortController(); alreadyAborted.abort();
  assert.equal(await f.expect(alreadyAborted.signal), false);
});

test("current render failure, unmount and refused model-switch publication settle false", async () => {
  for (const cancel of [f => f.tracker.failed(f.published), f => f.tracker.failed(null),
    f => f.tracker.cancel(), f => { f.ctx = null; f.tracker.checkContext(); }]) {
    const f = fixture(), promise = f.expect(); cancel(f);
    assert.equal(await promise, false); assert.equal(f.tracker.snapshot().pending, 0);
    assert.equal(f.tracker.adopted(f.published), false, "late callback cannot resurrect a settled request");
  }
});

test("scheduler reservation spans real scene adoption and blocks the next cached component", async () => {
  const base = mesh(0), a = mesh(1), b = mesh(2);
  const ctx = { file: "same.step", meshHash: "revision", meshData: source([["a1", "a", base], ["b1", "b", base]]) };
  const tracker = createLodSceneAdoption({ currentContext: () => ctx });
  const scene = buildModel(THREE, ctx.meshData, { renderPartsIndividually: true });
  const reservations = new Set(), released = [], loads = [];
  let timer;
  const scheduler = createLodScheduler({ minimumLevel: 1,
    setTimeoutFn: fn => { timer = fn; return 1; }, clearTimeoutFn: () => {},
    reserveLevel: ({ cid }) => { reservations.add(cid); return { ok: true, token: cid }; },
    releaseLevel: cid => { reservations.delete(cid); released.push(cid); },
    loadLevel: async cid => { loads.push(cid); return cid === "a" ? a : b; },
    applyLevel: (cid, level, payload, { signal }) => {
      ctx.meshData = source(ctx.meshData.parts.map(part => [part.id, part.componentId, part.componentId === cid ? payload : part.sourceMesh]));
      return tracker.expect({ context: ctx, source: ctx.meshData, componentId: cid, componentMesh: payload, signal });
    } });
  scheduler.setComponents([{ cid: "a", diagonal: 2, level: 0 }, { cid: "b", diagonal: 2, level: 0 }]);
  scheduler.onCameraSample({ camera: { kind: "orthographic", visibleWorldHeight: 10000 }, viewportHeightPx: 1000, distanceFor: () => 1000 });
  timer(); await ticks();
  assert.deepEqual(loads, ["a"]); assert.deepEqual([...reservations], ["a"]); assert.equal(scheduler.levelOf("a"), 0);
  assert.notEqual(scene.source, ctx.meshData);
  scene.update({ source: ctx.meshData });
  assert.equal(scene.displayRecords.find(record => record.partId === "a1").sourcePart.sourceMesh, a);
  assert.equal(tracker.adopted(scene.source), true); await ticks();
  assert.deepEqual(loads, ["a", "b"]); assert.deepEqual(released, ["a"]); assert.deepEqual([...reservations], ["b"]);
  scene.update({ source: ctx.meshData }); assert.equal(tracker.adopted(scene.source), true); await ticks();
  assert.deepEqual(released, ["a", "b"]); assert.equal(reservations.size, 0); assert.equal(tracker.snapshot().pending, 0);
  assert.deepEqual(scheduler.snapshot().levelCounts, { 1: 2 });
  scheduler.dispose(); scene.dispose();
});

test("refused asynchronous adoption parks once, releases once, and retries only after a new camera sample", async () => {
  let timer, loads = 0, releases = 0;
  const scheduler = createLodScheduler({ minimumLevel: 1,
    setTimeoutFn: fn => { timer = fn; return 1; }, clearTimeoutFn: () => {},
    reserveLevel: () => ({ ok: true, token: "reservation" }), releaseLevel: () => { releases++; },
    loadLevel: async () => { loads++; return {}; }, applyLevel: async () => false });
  const sample = { camera: { kind: "orthographic", visibleWorldHeight: 10000 }, viewportHeightPx: 1000, distanceFor: () => 1000 };
  scheduler.setComponents([{ cid: "a", diagonal: 2, level: 0 }]); scheduler.onCameraSample(sample); timer(); await ticks(40);
  assert.equal(loads, 1); assert.equal(releases, 1); assert.equal(scheduler.snapshot().failedLevels, 1); assert.equal(scheduler.busy(), false);
  scheduler.onCameraSample(sample); timer(); await ticks(40);
  assert.equal(loads, 2); assert.equal(releases, 2); scheduler.dispose(); assert.equal(releases, 2);
});
