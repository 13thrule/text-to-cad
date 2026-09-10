// The worker client's cache identity rule: only a content-addressed component
// surf (components/<cid>.surf) may key the shared tessellation cache — an
// arbitrary .surf path has no stable identity and caching it by name would
// collide across models.
import assert from "node:assert/strict";
import test from "node:test";

import {
  cidFromSurfUrl,
  loadSurfComponentInWorker,
  releaseSurfWorkerPool,
  releaseSurfWorkerPoolWhenIdle,
} from "./surfWorkerClient.js";
import { setTessellationCacheProvider } from "./tessellationCache.js";

test("cidFromSurfUrl accepts only components/<cid>.surf", () => {
  assert.equal(
    cidFromSurfUrl("/__cad/models/__cadgen__/models/x.step/components/abc123.surf"),
    "abc123",
  );
  assert.equal(cidFromSurfUrl("http://h/pkg/components/deadbeef.surf?v=1#frag"), "deadbeef");
  assert.equal(cidFromSurfUrl("/pkg/components/upper%2Bcase.surf"), "upper+case");
  assert.equal(cidFromSurfUrl("/pkg/other/abc.surf"), "", "non-components dir");
  assert.equal(cidFromSurfUrl("/components/abc.notsurf"), "", "wrong extension");
  assert.equal(cidFromSurfUrl("abc.surf"), "", "no components parent");
  assert.equal(cidFromSurfUrl(""), "");
});

test("cidFromSurfUrl reads the viewer's query-form asset URLs", () => {
  // The viewer serves package components through /__cad/asset?file=<abs path>.
  // The first release parsed only path-form URLs, which disabled the entire
  // shared-cache integration in the real client (no reads, no write-backs).
  assert.equal(
    cidFromSurfUrl(
      "/__cad/asset?file=%2Fabs%2Fmodels%2F__cadgen__%2Fmodels%2Fx.step%2Fcomponents%2Fc384534572a08e23.surf&v=abc123",
    ),
    "c384534572a08e23",
  );
  assert.equal(
    cidFromSurfUrl("/__cad/asset?v=1&file=/plain/pkg/components/deadbeef.surf"),
    "deadbeef",
    "unencoded file param, param order independent",
  );
  assert.equal(
    cidFromSurfUrl("/__cad/asset?file=/pkg/components/abc.surf#frag"),
    "abc",
    "fragment stripped before query parse",
  );
  assert.equal(
    cidFromSurfUrl("/__cad/asset?file=/pkg/other/abc.surf"),
    "",
    "query form still requires a components/ parent",
  );
  assert.equal(
    cidFromSurfUrl("/__cad/asset?file=/pkg/components/assembly.json"),
    "",
    "query form still requires the .surf extension",
  );
  assert.equal(cidFromSurfUrl("/__cad/asset?other=/pkg/components/abc.surf"), "", "no file param");
});

test("loadSurfComponentInWorker returns null where Workers do not exist (node)", () => {
  assert.equal(loadSurfComponentInWorker("/pkg/components/abc.surf"), null);
});

test("worker requests declare a bounded render/selectors capability set", async () => {
  const messages = [];
  class FakeWorker {
    constructor() { this.listeners = {}; }
    addEventListener(type, handler) { this.listeners[type] = handler; }
    postMessage(message) {
      messages.push(message);
      setTimeout(() => this.listeners.message?.({
        data: {
          id: message.id,
          ok: true,
          ...(message.capabilities.render ? { meshData: { parts: [] } } : {}),
          ...(message.capabilities.selectors ? { bundle: { manifest: {}, buffers: {} } } : {}),
        },
      }), 0);
    }
    terminate() {}
  }
  const savedWorker = globalThis.Worker;
  globalThis.Worker = FakeWorker;
  try {
    const render = await loadSurfComponentInWorker("http://x/components/render.surf", {
      capabilities: { render: true, selectors: false },
    });
    const selectors = await loadSurfComponentInWorker("http://x/components/selectors.surf", {
      capabilities: { render: false, selectors: true },
    });
    assert.deepEqual(messages.map((message) => message.capabilities), [
      { render: true, selectors: false },
      { render: false, selectors: true },
    ]);
    assert.ok(render.meshData);
    assert.equal(render.bundle, undefined);
    assert.ok(selectors.bundle);
    assert.equal(selectors.meshData, undefined);
    assert.throws(
      () => loadSurfComponentInWorker("http://x/components/none.surf", { capabilities: {} }),
      /must require render or selectors capability/,
    );
  } finally {
    releaseSurfWorkerPool();
    globalThis.Worker = savedWorker;
  }
});

test("releaseSurfWorkerPool terminates idle workers and the next request builds a fresh pool", async () => {
  const terminated = [];
  const created = [];
  class FakeWorker {
    constructor() { this.listeners = {}; created.push(this); }
    addEventListener(type, handler) { this.listeners[type] = handler; }
    postMessage(message) {
      // Answer on a later turn, as a real worker does.
      setTimeout(() => this.listeners.message?.({
        data: { id: message.id, ok: true, meshData: { parts: [] }, bundle: null }
      }), 0);
    }
    terminate() { terminated.push(this); }
  }
  const savedWorker = globalThis.Worker;
  globalThis.Worker = FakeWorker;
  try {
    assert.equal(releaseSurfWorkerPool(), false, "nothing to release before the first request");
    const inFlight = loadSurfComponentInWorker("http://x/components/aa.surf");
    assert.ok(created.length > 0, "the first request builds the pool");
    assert.equal(releaseSurfWorkerPool(), false, "a request in flight keeps the pool");
    await inFlight;
    assert.equal(releaseSurfWorkerPool(), true);
    assert.equal(terminated.length, created.length, "every worker was terminated");
    const before = created.length;
    await loadSurfComponentInWorker("http://x/components/bb.surf");
    assert.ok(created.length > before, "the next request builds a fresh pool");
    releaseSurfWorkerPool();
  } finally {
    globalThis.Worker = savedWorker;
  }
});

test("releaseSurfWorkerPoolWhenIdle releases an overlapping request after it completes", async () => {
  const created = [];
  const terminated = [];
  class FakeWorker {
    constructor() { this.listeners = {}; created.push(this); }
    addEventListener(type, handler) { this.listeners[type] = handler; }
    postMessage(message) { this.message = message; }
    terminate() { terminated.push(this); }
  }
  const savedWorker = globalThis.Worker;
  globalThis.Worker = FakeWorker;
  try {
    const inFlight = loadSurfComponentInWorker("http://x/components/overlap.surf");
    const released = releaseSurfWorkerPoolWhenIdle();
    assert.equal(terminated.length, 0, "in-flight work is not terminated");
    const worker = created.find((candidate) => candidate.message?.type === "loadSurf");
    worker.listeners.message({
      data: { id: worker.message.id, ok: true, meshData: { parts: [] } },
    });
    await inFlight;
    assert.equal(await released, true);
    assert.equal(terminated.length, created.length, "all isolates release at idle");
  } finally {
    releaseSurfWorkerPool();
    globalThis.Worker = savedWorker;
  }
});

test("releaseSurfWorkerPoolWhenIdle releases after the last request aborts", async () => {
  const created = [];
  const terminated = [];
  class FakeWorker {
    constructor() { this.listeners = {}; created.push(this); }
    addEventListener(type, handler) { this.listeners[type] = handler; }
    postMessage(message) { this.message = message; }
    terminate() { terminated.push(this); }
  }
  const savedWorker = globalThis.Worker;
  globalThis.Worker = FakeWorker;
  const controller = new AbortController();
  try {
    const inFlight = loadSurfComponentInWorker("http://x/components/abort.surf", {
      signal: controller.signal,
    });
    const released = releaseSurfWorkerPoolWhenIdle();
    controller.abort();
    await assert.rejects(inFlight, { name: "AbortError" });
    assert.equal(await released, true);
    assert.equal(terminated.length, created.length, "abort drains and releases the pool");
  } finally {
    releaseSurfWorkerPool();
    globalThis.Worker = savedWorker;
  }
});

test("an old idle-release waiter cannot terminate a replacement pool", async () => {
  const created = [];
  const terminated = [];
  class FakeWorker {
    constructor() { this.listeners = {}; created.push(this); }
    addEventListener(type, handler) { this.listeners[type] = handler; }
    postMessage(message) { this.message = message; }
    terminate() { terminated.push(this); }
  }
  const savedWorker = globalThis.Worker;
  globalThis.Worker = FakeWorker;
  try {
    const oldRequest = loadSurfComponentInWorker("http://x/components/old.surf");
    const oldRelease = releaseSurfWorkerPoolWhenIdle();
    const oldWorkers = [...created];
    oldWorkers[0].listeners.error({ message: "old pool failed" });
    const replacementRequest = loadSurfComponentInWorker("http://x/components/new.surf");
    const replacementWorkers = created.filter((worker) => !oldWorkers.includes(worker));

    await assert.rejects(oldRequest, /old pool failed/);
    assert.equal(await oldRelease, true, "the failed generation has released");
    assert.equal(
      replacementWorkers.some((worker) => terminated.includes(worker)),
      false,
      "the old waiter is scoped to its own generation",
    );

    const assigned = replacementWorkers.find((worker) => worker.message?.type === "loadSurf");
    assigned.listeners.message({
      data: { id: assigned.message.id, ok: true, meshData: { parts: [] } },
    });
    await replacementRequest;
  } finally {
    releaseSurfWorkerPool();
    globalThis.Worker = savedWorker;
  }
});

test("aborting synchronous work replaces only its worker and preserves unrelated and queued jobs", async () => {
  const created = [];
  const terminated = [];
  class FakeWorker {
    constructor() { this.listeners = {}; this.messages = []; created.push(this); }
    addEventListener(type, handler) { this.listeners[type] = handler; }
    postMessage(message) { this.messages.push(message); }
    terminate() { terminated.push(this); }
  }
  const savedWorker = globalThis.Worker;
  globalThis.Worker = FakeWorker;
  const controller = new AbortController();
  try {
    const cancelled = loadSurfComponentInWorker("http://x/components/cancelled.surf", {
      signal: controller.signal,
    });
    const initialWorkers = [...created];
    const poolCount = initialWorkers.length;
    const unrelated = [];
    for (let index = 1; index < poolCount; index += 1) {
      unrelated.push(loadSurfComponentInWorker(`http://x/components/keep-${index}.surf`));
    }
    const queued = loadSurfComponentInWorker("http://x/components/queued.surf");
    assert.equal(
      initialWorkers.reduce((sum, worker) => sum + worker.messages.length, 0),
      poolCount,
      "one job occupies each worker and excess work stays on the client queue",
    );

    const cancelledWorker = initialWorkers.find((worker) =>
      worker.messages.some((message) => message.url.endsWith("cancelled.surf")));
    controller.abort();
    await assert.rejects(cancelled, { name: "AbortError" });
    assert.ok(terminated.includes(cancelledWorker), "the blocked worker was terminated");
    assert.equal(
      initialWorkers.filter((worker) => worker !== cancelledWorker).some((worker) => terminated.includes(worker)),
      false,
      "workers running unrelated jobs survive",
    );

    const replacement = created.find((worker) => !initialWorkers.includes(worker));
    const queuedMessage = replacement.messages.find((message) => message.url.endsWith("queued.surf"));
    assert.ok(queuedMessage, "the replacement immediately accepts queued work");
    // A late event already queued by the terminated worker cannot settle the
    // replacement's request because request ownership includes the slot.
    cancelledWorker.listeners.message({
      data: { id: queuedMessage.id, ok: true, meshData: { parts: ["stale"] } },
    });

    for (const worker of initialWorkers) {
      if (worker === cancelledWorker) continue;
      const message = worker.messages[0];
      worker.listeners.message({ data: { id: message.id, ok: true, meshData: { parts: [] } } });
    }
    replacement.listeners.message({
      data: { id: queuedMessage.id, ok: true, meshData: { parts: ["queued"] } },
    });
    assert.deepEqual((await queued).meshData.parts, ["queued"]);
    await Promise.all(unrelated);
  } finally {
    releaseSurfWorkerPool();
    globalThis.Worker = savedWorker;
  }
});

test("a pending warm-cache lookup does not occupy a worker slot", async (t) => {
  const created = [];
  class FakeWorker {
    constructor() { this.listeners = {}; this.messages = []; created.push(this); }
    addEventListener(type, handler) { this.listeners[type] = handler; }
    postMessage(message) { this.messages.push(message); }
    terminate() {}
  }
  let resolveCache;
  setTessellationCacheProvider({
    get: () => new Promise((resolve) => { resolveCache = resolve; }),
    async put() {},
  });
  t.after(() => setTessellationCacheProvider(null));
  const savedWorker = globalThis.Worker;
  globalThis.Worker = FakeWorker;
  try {
    const awaitingCache = loadSurfComponentInWorker("http://x/components/cached.surf");
    assert.equal(created.some((worker) => worker.messages.length > 0), false);
    const ready = loadSurfComponentInWorker("http://x/not-content-addressed.surf");
    const readyWorker = created.find((worker) => worker.messages.length > 0);
    assert.ok(readyWorker, "ready work dispatches while the cache lookup waits");
    const readyMessage = readyWorker.messages[0];
    readyWorker.listeners.message({
      data: { id: readyMessage.id, ok: true, meshData: { parts: ["ready"] } },
    });
    assert.deepEqual((await ready).meshData.parts, ["ready"]);

    resolveCache(null);
    await new Promise((resolve) => setTimeout(resolve, 0));
    const cachedWorker = created.find((worker) =>
      worker.messages.some((message) => message.url.endsWith("cached.surf")));
    const cachedMessage = cachedWorker.messages.find((message) => message.url.endsWith("cached.surf"));
    cachedWorker.listeners.message({
      data: { id: cachedMessage.id, ok: true, meshData: { parts: ["cached"] } },
    });
    assert.deepEqual((await awaitingCache).meshData.parts, ["cached"]);
  } finally {
    releaseSurfWorkerPool();
    globalThis.Worker = savedWorker;
  }
});

test("a worker runtime error replaces one slot without rejecting unrelated work", async () => {
  const created = [];
  const terminated = [];
  class FakeWorker {
    constructor() { this.listeners = {}; this.messages = []; created.push(this); }
    addEventListener(type, handler) { this.listeners[type] = handler; }
    postMessage(message) { this.messages.push(message); }
    terminate() { terminated.push(this); }
  }
  const savedWorker = globalThis.Worker;
  globalThis.Worker = FakeWorker;
  try {
    const failed = loadSurfComponentInWorker("http://x/components/fail.surf");
    const kept = loadSurfComponentInWorker("http://x/components/keep.surf");
    const failedWorker = created.find((worker) => worker.messages[0]?.url.endsWith("fail.surf"));
    const keptWorker = created.find((worker) => worker.messages[0]?.url.endsWith("keep.surf"));
    failedWorker.listeners.error({ message: "worker crashed" });
    await assert.rejects(failed, /worker crashed/);
    assert.ok(terminated.includes(failedWorker));
    assert.equal(terminated.includes(keptWorker), false);
    const keptMessage = keptWorker.messages[0];
    keptWorker.listeners.message({
      data: { id: keptMessage.id, ok: true, meshData: { parts: ["kept"] } },
    });
    assert.deepEqual((await kept).meshData.parts, ["kept"]);
    assert.ok(created.length > 3, "the failed slot was replaced");
  } finally {
    releaseSurfWorkerPool();
    globalThis.Worker = savedWorker;
  }
});

test("a failed replacement constructor preserves surviving workers and their queue", async () => {
  const created = [];
  const terminated = [];
  let failNextConstructor = false;
  class FakeWorker {
    constructor() {
      if (failNextConstructor) {
        failNextConstructor = false;
        throw new Error("replacement unavailable");
      }
      this.listeners = {};
      this.messages = [];
      created.push(this);
    }
    addEventListener(type, handler) { this.listeners[type] = handler; }
    postMessage(message) { this.messages.push(message); }
    terminate() { terminated.push(this); }
  }
  const savedWorker = globalThis.Worker;
  globalThis.Worker = FakeWorker;
  const controller = new AbortController();
  try {
    const cancelled = loadSurfComponentInWorker("http://x/components/cancel-constructor.surf", {
      signal: controller.signal,
    });
    const initialWorkers = [...created];
    const poolCount = initialWorkers.length;
    const survivors = [];
    for (let index = 1; index < poolCount; index += 1) {
      survivors.push(loadSurfComponentInWorker(`http://x/components/survivor-${index}.surf`));
    }
    const queued = loadSurfComponentInWorker("http://x/components/after-constructor-failure.surf");
    failNextConstructor = true;
    controller.abort();
    await assert.rejects(cancelled, { name: "AbortError" });

    const liveWorkers = initialWorkers.filter((worker) => !terminated.includes(worker));
    assert.equal(liveWorkers.length, poolCount - 1, "only the cancelled slot was lost");
    const firstLive = liveWorkers[0];
    const firstMessage = firstLive.messages[0];
    firstLive.listeners.message({
      data: { id: firstMessage.id, ok: true, meshData: { parts: ["survivor"] } },
    });
    const queuedMessage = firstLive.messages.find((message) =>
      message.url.endsWith("after-constructor-failure.surf"));
    assert.ok(queuedMessage, "a surviving slot continues draining queued jobs");
    firstLive.listeners.message({
      data: { id: queuedMessage.id, ok: true, meshData: { parts: ["queued"] } },
    });
    for (const worker of liveWorkers.slice(1)) {
      const message = worker.messages[0];
      worker.listeners.message({
        data: { id: message.id, ok: true, meshData: { parts: ["survivor"] } },
      });
    }
    assert.deepEqual((await queued).meshData.parts, ["queued"]);
    await Promise.all(survivors);
  } finally {
    releaseSurfWorkerPool();
    globalThis.Worker = savedWorker;
  }
});

test("synchronous post failures drain a queued batch without recursive dispatch", async () => {
  const created = [];
  class FakeWorker {
    constructor() { this.listeners = {}; this.messages = []; created.push(this); }
    addEventListener(type, handler) { this.listeners[type] = handler; }
    postMessage(message) {
      if (message.url.includes("post-failure-")) throw new Error(`post failed ${message.id}`);
      this.messages.push(message);
    }
    terminate() {}
  }
  const savedWorker = globalThis.Worker;
  globalThis.Worker = FakeWorker;
  try {
    const first = loadSurfComponentInWorker("http://x/components/blocker.surf");
    const initialWorkers = [...created];
    const blockers = [first];
    for (let index = 1; index < initialWorkers.length; index += 1) {
      blockers.push(loadSurfComponentInWorker(`http://x/components/blocker-${index}.surf`));
    }
    const failed = Array.from({ length: 40 }, (_, index) =>
      loadSurfComponentInWorker(`http://x/components/post-failure-${index}.surf`));
    const final = loadSurfComponentInWorker("http://x/components/final-good.surf");

    const firstMessage = initialWorkers[0].messages[0];
    initialWorkers[0].listeners.message({
      data: { id: firstMessage.id, ok: true, meshData: { parts: ["blocker"] } },
    });
    const failures = await Promise.allSettled(failed);
    assert.ok(failures.every((result) => result.status === "rejected"));
    const finalWorker = created.find((worker) =>
      worker.messages.some((message) => message.url.endsWith("final-good.surf")));
    const finalMessage = finalWorker.messages.find((message) => message.url.endsWith("final-good.surf"));
    assert.ok(finalMessage, "the iterative drain reaches later good work");
    finalWorker.listeners.message({
      data: { id: finalMessage.id, ok: true, meshData: { parts: ["final"] } },
    });
    for (const worker of initialWorkers.slice(1)) {
      const message = worker.messages[0];
      worker.listeners.message({
        data: { id: message.id, ok: true, meshData: { parts: ["blocker"] } },
      });
    }
    assert.deepEqual((await final).meshData.parts, ["final"]);
    await Promise.all(blockers);
  } finally {
    releaseSurfWorkerPool();
    globalThis.Worker = savedWorker;
  }
});
