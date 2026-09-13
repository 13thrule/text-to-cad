import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { loadSource } from "./source.js";
import { loadDocumentSnapshot, DOCUMENT_ASSET_PREFIX } from "./documentSnapshotSource.js";
import { documentFaceReference } from "../lib/render/documentPicking.js";

const hash = (value) => createHash("sha256").update(value).digest("hex");
function fixture({ render = false, final = false } = {}) {
  const policy = { relative_chord: final ? .00015 : .0015, angular: .35, edges: !render };
  const values = [new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]), new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]),
    new Uint32Array([0, 1, 2]), new Float32Array(render ? [] : [0, 0, 0, 1, 0, 0])];
  const header = { version: 2, discardedZeroAreaTriangles: 0, options: policy,
    linearDeflection: .01, origin: [0, 0, 0], bounds: { min: [0, 0, 0], max: [1, 1, 0] },
    faces: [[0, 0, 3, 0, 3]], edges: render ? [] : [[0, 0, 2, "boundary"]], buffers: {} };
  let offset = 0;
  ["positions", "normals", "indices", "edgePositions"].forEach((name, i) => {
    header.buffers[name] = { offset, bytes: values[i].byteLength, count: values[i].length, type: i === 2 ? "I" : "f", width: i === 2 ? 1 : 3 };
    offset += values[i].byteLength;
  });
  const json = new TextEncoder().encode(JSON.stringify(header)), start = 12 + json.length + (4 - json.length % 4) % 4;
  const mesh = new Uint8Array(start + offset);
  mesh.set([67, 71, 77, 69, 83, 72, 0, 2]); new DataView(mesh.buffer).setUint32(8, json.length, true); mesh.set(json, 12);
  let cursor = start;
  for (const value of values) { mesh.set(new Uint8Array(value.buffer), cursor); cursor += value.byteLength; }
  const meshHash = hash(mesh), I = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
  const own = { color: [.2, .4, .6, .5], pbr: { roughness: .25, opacity: .8 }, face_colors: [[0, [1, 0, 0, .4]]] };
  const manifest = { version: 1, owner: "snapshot-owner", revision: 2,
    nodes: [{ path: ["root"], kind: "group", label: "Assembly", transform: I, appearance: {} }],
    prototypes: { proto: { mesh: meshHash, bytes: mesh.length } }, occurrences: [] };
  for (let i = 0; i < 3; i++) {
    const transform = I.map((x, j) => j === 3 ? i * 2 : x), path = ["root", String(i)], label = `Part ${i}`;
    manifest.nodes.push({ path, kind: "part", label, transform, appearance: own });
    manifest.occurrences.push({ path, prototype: "proto", label, transform, appearance: own });
  }
  const manifestBytes = new TextEncoder().encode(JSON.stringify(manifest)), manifestHash = hash(manifestBytes);
  const descriptor = { version: 1, owner: manifest.owner, revision: manifest.revision,
    manifest: { sha256: manifestHash, bytes: manifestBytes.length }, assets: { [meshHash]: { bytes: mesh.length } }, meshing: policy };
  const job = { mode: "view", resolved: { kind: "step", inputPath: "saved.step", rootPath: "/private/staging", document: descriptor },
    ...(render ? { render: { quality: final ? "final" : "preview" } } : {}) };
  const bytes = new Map([[manifestHash, manifestBytes], [meshHash, mesh]]), reads = [];
  const fetcher = async (url) => {
    assert.ok(url.startsWith(DOCUMENT_ASSET_PREFIX), `unexpected source/cache read: ${url}`);
    const id = url.slice(DOCUMENT_ASSET_PREFIX.length); reads.push(id);
    assert.ok(bytes.has(id), "request outside captured inventory");
    const body = bytes.get(id);
    return new Response(body, { headers: { "content-length": String(body.length) } });
  };
  return { job, descriptor, manifest, meshHash, manifestHash, bytes, reads, fetcher };
}

test("native Inspect and Render use the shared source loader and read each asset once", async () => {
  for (const render of [false, true]) {
    const f = fixture({ render });
    const original = globalThis.fetch;
    globalThis.fetch = f.fetcher;
    try {
      const source = await loadSource(f.job);
      assert.equal(source.meshData.parts.length, 3);
      assert.deepEqual(f.reads, [f.manifestHash, f.meshHash]);
      assert.equal(source.meshData.parts[0].sourceMesh, source.meshData.parts[1].sourceMesh);
      assert.equal(source.meshData.parts[0].material.roughness, .25);
      assert.equal(source.meshData.parts[0].sourceMesh.colors[0], 1);
      if (render) {
        assert.equal(source.meshData.parts[0].sourceMesh.cadEdgePositions.length, 0);
        assert.throws(() => documentFaceReference(source.meshData, source.meshData.parts[0].id, 0), /adopted document scene/);
      } else {
        assert.ok(source.meshData.parts[0].sourceMesh.cadEdgePositions.length);
        assert.equal(documentFaceReference(source.meshData, source.meshData.parts[0].id, 0).ordinal, 0);
      }
    } finally { globalThis.fetch = original; }
  }
});

test("native job option and asset bounds rejection precedes every fetch", async () => {
  const cases = [
    (f) => { f.job.animation = null; }, (f) => { f.job.selection = {}; },
    (f) => { f.job.resolved.package = {}; }, (f) => { f.descriptor.manifest.bytes = 17 * 1024 ** 2; },
    (f) => { f.descriptor.assets[f.meshHash].bytes = 129 * 1024 ** 2; },
    (f) => { f.descriptor.meshing.edges = false; }, (f) => { f.job.mode = "list"; },
  ];
  for (const change of cases) {
    const f = fixture(); change(f);
    await assert.rejects(loadDocumentSnapshot(f.job, { fetch: () => assert.fail("invalid job fetched") }), /native snapshot/);
  }
});

test("hash mismatch, missing complete membership, streamed overflow and truncation fail loudly", async () => {
  for (const mode of ["manifestHash", "membership", "meshHash", "overflow", "truncated"]) {
    const f = fixture();
    if (mode === "manifestHash") f.bytes.get(f.manifestHash)[0] ^= 1;
    if (mode === "meshHash") f.bytes.get(f.meshHash)[f.bytes.get(f.meshHash).length - 1] ^= 1;
    if (mode === "membership") f.descriptor.assets["f".repeat(64)] = { bytes: 12 };
    const fetcher = ["overflow", "truncated"].includes(mode) ? async () => {
      const body = f.bytes.get(f.manifestHash);
      return new Response(mode === "overflow" ? new Uint8Array(body.length + 1) : body.subarray(1),
        { headers: { "content-length": String(body.length) } });
    } : f.fetcher;
    await assert.rejects(loadDocumentSnapshot(f.job, { fetch: fetcher }), /hash|inventory|byte length|truncated|match/);
    if (mode !== "meshHash") assert.ok(f.reads.length <= 1);
  }
});

test("queued descriptor mutation cannot change captured asset authority or appearance mode", async () => {
  const f = fixture();
  let resume;
  const pending = loadDocumentSnapshot(f.job, { fetch: async (url) => {
    if (!resume) await new Promise((resolve) => { resume = resolve; });
    return f.fetcher(url);
  } });
  f.descriptor.owner = "changed";
  f.descriptor.manifest.sha256 = "f".repeat(64);
  f.descriptor.assets = {};
  f.job.resolved.inputPath = "changed.step";
  f.job.render = {};
  resume();
  const source = await pending;
  assert.equal(source.meshData.documentRevision.owner, "snapshot-owner");
  assert.equal(documentFaceReference(source.meshData, source.meshData.parts[0].id, 0).ordinal, 0);
  assert.equal(source.resolved.document.owner, "snapshot-owner");
  assert.equal(source.cadPath, "saved.step");
});

test("an already cancelled native load makes no asset request", async () => {
  const f = fixture(), controller = new AbortController(); controller.abort();
  await assert.rejects(loadDocumentSnapshot(f.job, { signal: controller.signal, fetch: () => assert.fail("cancelled fetch") }), /abort/i);
});
