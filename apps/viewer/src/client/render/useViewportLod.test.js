import assert from "node:assert/strict";
import test from "node:test";

import { syncViewportLodLimitation } from "./useViewportLod.js";
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
