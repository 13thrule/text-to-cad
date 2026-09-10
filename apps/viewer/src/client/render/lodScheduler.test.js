// The LOD scheduler owns time: debounce, one in-flight re-tessellation,
// worst-first ordering, cancellation, and drain-until-settled.
import assert from "node:assert/strict";
import test from "node:test";

import { createLodScheduler } from "./lodScheduler.js";

// A camera sample factory over a fake model: per-cid distances, 1000px / 45deg.
function sampleWith(distances) {
  return {
    camera: { kind: "perspective", fovYDeg: 45 },
    viewportHeightPx: 1000,
    distanceFor: (cid) => distances[cid],
  };
}

// Manual clock: timers fire only when the test says so.
function makeClock() {
  const timers = new Map();
  let nextId = 1;
  return {
    setTimeoutFn: (fn) => {
      const id = nextId;
      nextId += 1;
      timers.set(id, fn);
      return id;
    },
    clearTimeoutFn: (id) => timers.delete(id),
    fire: () => {
      const pending = [...timers.values()];
      timers.clear();
      pending.forEach((fn) => fn());
    },
    count: () => timers.size,
  };
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

// queueMicrotask twice: the scheduler's apply/drain settles across two
// microtask hops (then + finally). No setImmediate — that's node-only and the
// unbound-identifier policy test rejects it in client code.
const tick = async () => {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
};

test("an omitted level means the canonical default while explicit L0 stays coarse", () => {
  const scheduler = createLodScheduler({ loadLevel: async () => ({}), applyLevel: () => {} });
  scheduler.setComponents([
    { cid: "default", diagonal: 100 },
    { cid: "coarse", diagonal: 100, level: 0 },
  ]);
  assert.equal(scheduler.levelOf("default"), 1);
  assert.equal(scheduler.levelOf("coarse"), 0);
  scheduler.dispose();
});

test("a canonical quality floor refines distant coarse leaves and later progressive arrivals", async () => {
  const clock = makeClock();
  const loads = [];
  const scheduler = createLodScheduler({
    ...clock,
    minimumLevel: 1,
    loadLevel: async (cid, level) => { loads.push(`${cid}@${level}`); return {}; },
    applyLevel: () => {},
  });
  scheduler.setComponents([{ cid: "first", diagonal: 10, level: 0 }]);
  scheduler.onCameraSample(sampleWith({ first: 10000, later: 10000 }));
  clock.fire(); await tick(); await tick();
  assert.equal(scheduler.levelOf("first"), 1);
  scheduler.setComponents([{ cid: "first", diagonal: 10, level: 0 }, { cid: "later", diagonal: 10, level: 0 }], { preserveLevels: true });
  clock.fire(); await tick(); await tick();
  assert.deepEqual(loads, ["first@1", "later@1"]);
  assert.deepEqual(scheduler.snapshot().levelCounts, { 1: 2 });
  assert.equal(scheduler.snapshot().belowMinimum, 0);
  scheduler.dispose();
});

test("debounce: rapid samples collapse to one evaluation; worst error loads first", async () => {
  const clock = makeClock();
  const loads = [];
  const applied = [];
  const gates = [];
  const scheduler = createLodScheduler({
    loadLevel: (cid, level) => {
      loads.push(`${cid}@L${level}`);
      const gate = deferred();
      gates.push(gate);
      return gate.promise;
    },
    applyLevel: (cid, level) => applied.push(`${cid}@L${level}`),
    setTimeoutFn: clock.setTimeoutFn,
    clearTimeoutFn: clock.clearTimeoutFn,
  });
  scheduler.setComponents([
    { cid: "near", diagonal: 100, level: 0 },
    { cid: "mid", diagonal: 100, level: 0 },
    { cid: "far", diagonal: 100, level: 0 },
  ]);
  const sample = sampleWith({ near: 60, mid: 150, far: 5000 });
  scheduler.onCameraSample(sample);
  scheduler.onCameraSample(sample);
  scheduler.onCameraSample(sample);
  assert.equal(clock.count(), 1, "re-armed debounce keeps one pending timer");
  assert.equal(loads.length, 0, "nothing loads before the debounce fires");
  clock.fire();
  assert.deepEqual(loads, ["near@L1"], "worst projected error first, one in flight");
  assert.ok(scheduler.busy());

  // Finishing the swap drains the next-worst item.
  gates[0].resolve({ fake: true });
  await tick();
  assert.equal(scheduler.levelOf("near"), 1);
  assert.deepEqual(applied, ["near@L1"]);
  assert.ok(loads.length >= 2 && loads[1].startsWith("near@L2") || loads[1].startsWith("mid@L1"),
    `drain continues: ${JSON.stringify(loads)}`);
  scheduler.dispose();
});

test("drain climbs the ladder to settle, then goes quiet", async () => {
  const clock = makeClock();
  const loads = [];
  let idleCalls = 0;
  const scheduler = createLodScheduler({
    onIdle: () => { idleCalls += 1; },
    loadLevel: (cid, level) => {
      loads.push(level);
      return Promise.resolve({});
    },
    applyLevel: () => {},
    setTimeoutFn: clock.setTimeoutFn,
    clearTimeoutFn: clock.clearTimeoutFn,
  });
  scheduler.setComponents([{ cid: "part", diagonal: 100, level: 0 }]);
  scheduler.onCameraSample(sampleWith({ part: 52 }));
  clock.fire();
  for (let i = 0; i < 6; i += 1) {
    await tick();
  }
  assert.deepEqual(loads, [1, 2, 3], "one rung at a time, stops at the finest");
  assert.equal(scheduler.levelOf("part"), 3);
  assert.equal(scheduler.busy(), false, "settled: no further work");
  assert.equal(idleCalls, 1, "worker ownership ends once after the whole drain, not after each component");
  scheduler.dispose();
});

test("dispose aborts in-flight work and a late resolve applies nothing", async () => {
  const clock = makeClock();
  const gate = deferred();
  let aborted = false;
  const applied = [];
  const releases = [];
  const scheduler = createLodScheduler({
    reserveLevel: () => ({ ok: true, token: "dispose-reservation" }),
    releaseLevel: (token) => releases.push(token),
    loadLevel: (cid, level, { signal }) => {
      signal.addEventListener("abort", () => {
        aborted = true;
      });
      return gate.promise;
    },
    applyLevel: (cid, level) => applied.push(level),
    setTimeoutFn: clock.setTimeoutFn,
    clearTimeoutFn: clock.clearTimeoutFn,
  });
  scheduler.setComponents([{ cid: "part", diagonal: 100, level: 0 }]);
  scheduler.onCameraSample(sampleWith({ part: 60 }));
  clock.fire();
  assert.ok(scheduler.busy());
  scheduler.dispose();
  assert.equal(aborted, true, "dispose aborts the in-flight load");
  gate.resolve({});
  await tick();
  assert.deepEqual(applied, [], "a late payload is dropped");
  assert.deepEqual(releases, ["dispose-reservation"], "cancellation releases its reservation exactly once");
});

test("a failed level load leaves the current level standing and does not wedge", async () => {
  const clock = makeClock();
  let calls = 0;
  const scheduler = createLodScheduler({
    loadLevel: () => {
      calls += 1;
      return Promise.reject(new Error("worker died"));
    },
    applyLevel: () => {
      throw new Error("must not apply a failed load");
    },
    setTimeoutFn: clock.setTimeoutFn,
    clearTimeoutFn: clock.clearTimeoutFn,
  });
  scheduler.setComponents([{ cid: "part", diagonal: 100, level: 0 }]);
  scheduler.onCameraSample(sampleWith({ part: 60 }));
  clock.fire();
  await tick();
  await tick();
  assert.equal(scheduler.levelOf("part"), 0, "level unchanged after failure");
  assert.equal(scheduler.busy(), false, "scheduler is not wedged");
  assert.ok(calls >= 1);
  scheduler.dispose();
});

test("a denied refinement keeps the usable level and reports the limitation", async () => {
  const clock = makeClock();
  const loads = [];
  const limitations = [];
  const scheduler = createLodScheduler({
    loadLevel: (cid, level) => {
      loads.push(`${cid}@${level}`);
      return Promise.resolve({});
    },
    applyLevel: () => {},
    reserveLevel: ({ cid, currentLevel, level, direction }) => ({
      ok: false,
      detail: { cid, currentLevel, level, direction, requestedBytes: 400 },
    }),
    onLimitation: (detail) => limitations.push(detail),
    setTimeoutFn: clock.setTimeoutFn,
    clearTimeoutFn: clock.clearTimeoutFn,
  });
  scheduler.setComponents([{ cid: "part", diagonal: 100, level: 0 }]);
  scheduler.onCameraSample(sampleWith({ part: 60 }));
  clock.fire();
  await tick();
  assert.deepEqual(loads, [], "denied work never starts");
  assert.equal(scheduler.levelOf("part"), 0, "current display remains usable");
  assert.deepEqual(limitations.map(({ direction }) => direction), ["refine"]);
  assert.equal(scheduler.busy(), false);
  scheduler.dispose();
});

test("LOD reservation spans replacement load and apply, then releases", async () => {
  const clock = makeClock();
  const gate = deferred();
  const events = [];
  const scheduler = createLodScheduler({
    reserveLevel: ({ direction }) => {
      events.push(`reserve:${direction}`);
      return { ok: true, token: "r1" };
    },
    loadLevel: () => {
      events.push("load");
      return gate.promise;
    },
    applyLevel: () => events.push("apply"),
    releaseLevel: (token) => events.push(`release:${token}`),
    setTimeoutFn: clock.setTimeoutFn,
    clearTimeoutFn: clock.clearTimeoutFn,
  });
  scheduler.setComponents([{ cid: "part", diagonal: 100, level: 0 }]);
  scheduler.onCameraSample(sampleWith({ part: 60 }));
  clock.fire();
  assert.deepEqual(events, ["reserve:refine", "load"]);
  gate.resolve({});
  await tick();
  assert.deepEqual(events.slice(0, 4), ["reserve:refine", "load", "apply", "release:r1"]);
  scheduler.dispose();
});

test("async selector reconciliation retains admission and delays the committed level", async () => {
  const clock = makeClock();
  const apply = deferred();
  const released = [];
  const scheduler = createLodScheduler({
    ...clock,
    loadLevel: async () => ({}),
    applyLevel: () => apply.promise,
    reserveLevel: () => ({ ok: true, token: "held" }),
    releaseLevel: (token) => released.push(token),
  });
  scheduler.setComponents([{ cid: "part", diagonal: 100, level: 0 }]);
  scheduler.onCameraSample(sampleWith({ part: 60 }));
  clock.fire();
  await tick();
  assert.equal(scheduler.levelOf("part"), 0);
  assert.equal(scheduler.busy(), true);
  assert.deepEqual(released, []);
  scheduler.onCameraSample(sampleWith({ part: 10000 }));
  apply.resolve(true);
  await tick(); await tick();
  assert.ok(released.includes("held"));
  scheduler.dispose();
});

test("a model switch aborts pending selector reconciliation and ignores its late apply", async () => {
  const clock = makeClock();
  const gate = deferred();
  let applySignal;
  const scheduler = createLodScheduler({
    ...clock,
    loadLevel: async () => ({}),
    applyLevel: (_cid, _level, _payload, { signal }) => { applySignal = signal; return gate.promise; },
  });
  scheduler.setComponents([{ cid: "old", diagonal: 100, level: 0 }]);
  scheduler.onCameraSample(sampleWith({ old: 60 }));
  clock.fire(); await tick();
  scheduler.setComponents([{ cid: "new", diagonal: 100, level: 0 }]);
  assert.equal(applySignal.aborted, true);
  gate.resolve(false); await tick(); await tick();
  assert.equal(scheduler.levelOf("new"), 0);
  assert.equal(scheduler.levelOf("old"), null);
  scheduler.dispose();
});

test("memory pressure coarsens the least-visible detail even while the camera requests fine geometry", async () => {
  const clock = makeClock();
  const loads = [];
  const scheduler = createLodScheduler({
    memoryPressure: () => true,
    loadLevel: (cid, level) => {
      loads.push(`${cid}@L${level}`);
      return Promise.resolve({});
    },
    applyLevel: () => {},
    setTimeoutFn: clock.setTimeoutFn,
    clearTimeoutFn: clock.clearTimeoutFn,
  });
  scheduler.setComponents([
    { cid: "near", diagonal: 100, level: 2 },
    { cid: "farther", diagonal: 100, level: 2 },
  ]);
  scheduler.onCameraSample(sampleWith({ near: 52, farther: 80 }));
  clock.fire();
  for (let i = 0; i < 8; i += 1) await tick();
  assert.equal(loads[0], "farther@L1", "smaller screen error releases detail first");
  assert.equal(scheduler.levelOf("near"), 0);
  assert.equal(scheduler.levelOf("farther"), 0);
  scheduler.dispose();
});

test("setComponents resets levels and cancels stale work (model switch)", async () => {
  const clock = makeClock();
  const gate = deferred();
  let aborted = false;
  const scheduler = createLodScheduler({
    loadLevel: (cid, level, { signal }) => {
      signal.addEventListener("abort", () => {
        aborted = true;
      });
      return gate.promise;
    },
    applyLevel: () => {},
    setTimeoutFn: clock.setTimeoutFn,
    clearTimeoutFn: clock.clearTimeoutFn,
  });
  scheduler.setComponents([{ cid: "old", diagonal: 100, level: 0 }]);
  scheduler.onCameraSample(sampleWith({ old: 60 }));
  clock.fire();
  assert.ok(scheduler.busy());
  scheduler.setComponents([{ cid: "new", diagonal: 50, level: 0 }]);
  assert.equal(aborted, true, "model switch cancels the stale load");
  assert.equal(scheduler.levelOf("old"), null);
  assert.equal(scheduler.levelOf("new"), 0);
  scheduler.dispose();
});

test("setComponents({ preserveLevels }) keeps levels and in-flight work while the same model grows", async () => {
  const clock = makeClock();
  const gate = deferred();
  let aborted = false;
  const scheduler = createLodScheduler({
    loadLevel: (cid, level, { signal }) => {
      signal.addEventListener("abort", () => {
        aborted = true;
      });
      return gate.promise;
    },
    applyLevel: () => {},
    setTimeoutFn: clock.setTimeoutFn,
    clearTimeoutFn: clock.clearTimeoutFn,
  });
  // First progressive batch: "part" loads to a finer level.
  scheduler.setComponents([{ cid: "part", diagonal: 100, level: 0 }]);
  scheduler.onCameraSample(sampleWith({ part: 60 }));
  clock.fire();
  assert.ok(scheduler.busy());
  gate.resolve({});
  await tick();
  // The drain has already moved the near component to a finer rung.
  assert.equal(scheduler.levelOf("part"), 2);
  // A later batch adds a component: the applied level survives.
  scheduler.setComponents([{ cid: "part", diagonal: 100, level: 0 }, { cid: "later", diagonal: 50, level: 0 }], { preserveLevels: true });
  assert.equal(scheduler.levelOf("part"), 2);
  assert.equal(scheduler.levelOf("later"), 0);
  // An in-flight load for a retained cid keeps running across a grow...
  const gate2 = deferred();
  const scheduler2 = createLodScheduler({
    loadLevel: (cid, level, { signal }) => {
      signal.addEventListener("abort", () => {
        aborted = true;
      });
      return gate2.promise;
    },
    applyLevel: () => {},
    setTimeoutFn: clock.setTimeoutFn,
    clearTimeoutFn: clock.clearTimeoutFn,
  });
  scheduler2.setComponents([{ cid: "part", diagonal: 100, level: 0 }]);
  scheduler2.onCameraSample(sampleWith({ part: 60 }));
  clock.fire();
  assert.ok(scheduler2.busy());
  scheduler2.setComponents([{ cid: "part", diagonal: 100, level: 0 }, { cid: "later", diagonal: 50, level: 0 }], { preserveLevels: true });
  assert.equal(aborted, false, "growing the model keeps the in-flight load");
  assert.ok(scheduler2.busy());
  // ...but the default (model switch) still resets everything.
  scheduler2.setComponents([{ cid: "part", diagonal: 100, level: 0 }]);
  assert.equal(aborted, true);
  assert.equal(scheduler2.levelOf("part"), 0);
  scheduler.dispose();
  scheduler2.dispose();
});
