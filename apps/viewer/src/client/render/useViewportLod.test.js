import assert from "node:assert/strict";
import test from "node:test";

import { dispatchViewportLodStatus, syncViewportLodLimitation, viewportLodMinimumLevel } from "./useViewportLod.js";
import { createViewerMemoryPolicy } from "./viewerMemoryPolicy.js";

test("partial fallback retains the unresolved camera target and only clears after it resolves", () => {
  const policy = createViewerMemoryPolicy();
  const published = [];
  const target = { cid: "limited", currentLevel: 2, targetLevel: 3, reason: "memory-denied" };
  syncViewportLodLimitation({ qualitySettled: false, unmetTargets: [target] }, policy, detail => published.push(detail));
  assert.deepEqual(policy.snapshot().lastLimitation.unmetTargets, [target]);
  // Another component's success does not remove the outstanding target.
  syncViewportLodLimitation({ qualitySettled: false, unmetTargets: [target] }, policy, detail => published.push(detail));
  assert.equal(policy.snapshot().lastLimitation.source, "viewportLod");
  syncViewportLodLimitation({ qualitySettled: true, unmetTargets: [] }, policy, detail => published.push(detail));
  assert.equal(policy.snapshot().lastLimitation, null);
  assert.equal(published.at(-1), null);
});

test("LOD idle and disposal clear only LOD-owned memory limitations", () => {
  const policy = createViewerMemoryPolicy();
  const foreign = { source: "assetLoad", requestedBytes: 123 };
  policy.noteLimitation(foreign);
  syncViewportLodLimitation({ qualitySettled: true, unmetTargets: [] }, policy, () => assert.fail("foreign limit must stay"));
  syncViewportLodLimitation({ disposed: true }, policy, () => assert.fail("foreign limit must stay"));
  assert.equal(policy.snapshot().lastLimitation, foreign);
  syncViewportLodLimitation({ unmetTargets: [{ cid: "part", currentLevel: 1, targetLevel: 3, reason: "memory-pressure" }] }, policy, () => {});
  assert.equal(policy.snapshot().lastLimitation.source, "viewportLod");
  syncViewportLodLimitation({ disposed: true }, policy, () => {});
  assert.equal(policy.snapshot().lastLimitation, null);
});

test("hard worker failure remains scheduler telemetry rather than a false memory limitation", () => {
  const policy = createViewerMemoryPolicy();
  syncViewportLodLimitation({ qualitySettled: false,
    unmetTargets: [{ cid: "part", currentLevel: 2, targetLevel: 3, reason: "load-failed" }] }, policy,
  () => assert.fail("worker failure is not a memory denial"));
  assert.equal(policy.snapshot().lastLimitation, null);
});

test("settlement clears an older published LOD warning after progressive load cleared the ledger", () => {
  const policy = createViewerMemoryPolicy();
  const warning = { source: "viewportLod", unmetTargets: [{ reason: "memory-pressure" }] };
  const published = [];
  policy.noteLimitation(warning);
  policy.clearLimitation();
  syncViewportLodLimitation({ qualitySettled: true, unmetTargets: [] }, policy,
    value => published.push(value), warning);
  assert.deepEqual(published, [null]);
});

test("production viewport floor is canonical L1 while the harness can explicitly request L0", () => {
  assert.equal(viewportLodMinimumLevel(null), 1);
  assert.equal(viewportLodMinimumLevel({}), 1);
  assert.equal(viewportLodMinimumLevel({ __CAD_VIEWER_MIN_LOD__: 0 }), 0);
});

test("LOD status dispatch preserves the full scheduler snapshot for UI consumers", () => {
  const events = [];
  class EventStub { constructor(type, options) { this.type = type; this.detail = options.detail; } }
  const target = { dispatchEvent: event => events.push(event) };
  const status = { file: "assembly.step", modelKey: "assembly.step:rev-a", scope: "visible-components",
    componentCount: 64, minimumLevel: 1, belowMinimum: 12,
    standardSettled: false, qualitySettled: false, unmetTargets: [] };
  dispatchViewportLodStatus(status, target, EventStub);
  assert.equal(events[0].type, "cad:lod-status");
  assert.equal(events[0].detail, status);
});
