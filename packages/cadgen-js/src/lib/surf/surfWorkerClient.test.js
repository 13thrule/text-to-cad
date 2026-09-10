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
