import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import * as THREE from "three";
import { buildModel } from "../../common/cadScene.js";
import { adoptDocumentScene } from "./documentScene.js";

const I = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
const move = (x) => I.map((v, i) => i === 3 ? x : v);
function packet() {
  const values = [new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]),
    new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]), new Uint32Array([0, 1, 2]),
    new Float32Array([0, 0, 0, 1, 0, 0])];
  const header = { version: 2, discardedZeroAreaTriangles: 0, options: { relative_chord: .0015, angular: .35, edges: true },
    linearDeflection: .01, origin: [10, 20, 30], bounds: { min: [10, 20, 30], max: [11, 21, 30] },
    faces: [[0, 0, 3, 0, 3]], edges: [[0, 0, 2, "boundary"]], buffers: {} };
  let offset = 0;
  ["positions", "normals", "indices", "edgePositions"].forEach((name, i) => {
    header.buffers[name] = { offset, bytes: values[i].byteLength, count: values[i].length,
      type: i === 2 ? "I" : "f", width: i === 2 ? 1 : 3 };
    offset += values[i].byteLength;
  });
  const json = new TextEncoder().encode(JSON.stringify(header));
  const start = 12 + json.length + (4 - json.length % 4) % 4;
  const bytes = new Uint8Array(start + offset);
  bytes.set([67, 71, 77, 69, 83, 72, 0, 2]);
  new DataView(bytes.buffer).setUint32(8, json.length, true);
  bytes.set(json, 12);
  let cursor = start;
  for (const value of values) { bytes.set(new Uint8Array(value.buffer), cursor); cursor += value.byteLength; }
  return bytes;
}
function fixture(revision = 1) {
  const bytes = packet(), hash = createHash("sha256").update(bytes).digest("hex");
  const manifest = { version: 1, owner: "owner", revision,
    nodes: [{ path: ["root"], kind: "group", label: "Assembly", transform: move(5), appearance: { color: [1, 0, 0, .5] } },
      { path: ["root", "group"], kind: "group", label: "Nested", transform: move(10), appearance: { pbr: { roughness: .25 } } }],
    prototypes: { proto: { mesh: hash, bytes: bytes.length } }, occurrences: [] };
  for (let i = 0; i < 24; i++) {
    const path = ["root", "group", String(i)];
    manifest.nodes.push({ path, kind: "part", label: String(i), transform: move(i * 2), appearance: {} });
    manifest.occurrences.push({ path, prototype: "proto", label: String(i), transform: move(15 + i * 2),
      appearance: { color: [1, 0, 0, .5], pbr: { roughness: .25 } } });
  }
  return { bytes, hash, manifest };
}

test("nested occurrences decode once, apply origin once, and share geometry across live models", async () => {
  const { bytes, manifest } = fixture();
  let reads = 0;
  const first = await adoptDocumentScene(manifest, async () => { reads++; return bytes; });
  assert.equal(reads, 1);
  assert.equal(first.parts.length, 24);
  assert.equal(first.assemblyRoot.children[0].children.length, 24);
  assert.deepEqual(first.bounds, { min: [25, 20, 30], max: [72, 21, 30] });
  assert.equal(first.parts[0].opacity, .5);
  assert.equal(first.parts[0].material.roughness, .25);
  assert.ok(first.parts.every((p) => p.sourceMesh === first.parts[0].sourceMesh));
  const second = await adoptDocumentScene(fixture(2).manifest, () => assert.fail("refetched immutable asset"), { previous: first });
  assert.equal(first.parts[0].sourceMesh, second.parts[0].sourceMesh);
  assert.notEqual(first.parts[0].id, second.parts[0].id, "selection identities are revision-scoped");
  const a = buildModel(THREE, first, { renderPartsIndividually: true });
  const b = buildModel(THREE, second, { renderPartsIndividually: true });
  assert.equal(a.displayRecords.length, 24);
  assert.equal(a.displayRecords[0].geometry, b.displayRecords[0].geometry);
  assert.equal(a.displayRecords[0].mesh.matrix.elements[12], 25);
  const geometry = b.displayRecords[0].geometry;
  let disposed = 0;
  geometry.addEventListener("dispose", () => { disposed++; });
  a.dispose();
  assert.equal(disposed, 0);
  assert.equal(b.displayRecords[0].geometry.getAttribute("position").count, 3);
  assert.ok(b.root.children.length);
  b.dispose();
});

test("mutable manifest and fetched buffers are isolated across asynchronous hashing", async () => {
  const { bytes, manifest } = fixture();
  let release;
  const pending = adoptDocumentScene(manifest, () => new Promise((resolve) => { release = resolve; }));
  manifest.nodes.length = 0;
  manifest.occurrences[0].transform[3] = 999;
  release(bytes);
  // Loader resumes and snapshots bytes before crypto yields; the next queued
  // microtask then mutates the fetcher's original storage during hashing.
  queueMicrotask(() => bytes.fill(0));
  const scene = await pending;
  assert.equal(scene.parts[0].transform[3], 25);
  assert.equal(scene.parts[0].sourceMesh.vertices[3], 1);
});

test("unknown appearance, inconsistent hierarchy and excessive budgets fail before fetching", async () => {
  const changes = [
    (m) => { m.nodes[0].appearance.material = "steel"; },
    (m) => { m.occurrences[0].appearance.pbr.texture = "url"; },
    (m) => { m.nodes.pop(); },
    (m) => { m.occurrences.pop(); },
    (m) => { m.occurrences[0].prototype = "missing"; },
    (m) => { m.occurrences[0].transform[3]++; },
    (m) => { m.prototypes.proto.bytes = 129 * 1024 ** 2; },
    (m) => { m.nodes = Array(100_001); },
  ];
  for (const change of changes) {
    const { manifest } = fixture(); change(manifest);
    await assert.rejects(adoptDocumentScene(manifest, () => assert.fail("invalid manifest fetched assets")), /Invalid document scene/);
  }
});

test("bad asset, cancellation and older candidates leave previous scene functional", async () => {
  const { bytes, manifest } = fixture(2);
  const first = await adoptDocumentScene(manifest, async () => bytes);
  const other = fixture(3); other.manifest.prototypes.proto.mesh = "f".repeat(64);
  await assert.rejects(adoptDocumentScene(other.manifest, async () => other.bytes, { previous: first }), /do not match/);
  await assert.rejects(adoptDocumentScene(other.manifest, async () => new Uint8Array(0), { previous: first }), /byte length/);
  const controller = new AbortController(); controller.abort();
  await assert.rejects(adoptDocumentScene(manifest, () => assert.fail("cancelled fetch"), { previous: first, signal: controller.signal }), { name: "AbortError" });
  const older = await adoptDocumentScene(fixture(1).manifest, () => assert.fail("refetch"), { previous: first });
  assert.equal(older.documentRevision.revision, 1);
  assert.equal(first.documentRevision.revision, 2);
  assert.deepEqual(first.bounds, { min: [25, 20, 30], max: [72, 21, 30] });
  const foreign = fixture(2); foreign.manifest.owner = "foreign";
  const next = await adoptDocumentScene(foreign.manifest, () => assert.fail("content hash can share across owners"), { previous: first });
  assert.notEqual(next.parts[0].id, first.parts[0].id);
  let fetched = 0;
  await adoptDocumentScene(manifest, async () => { fetched++; return bytes; }, { previous: { ...first } });
  assert.equal(fetched, 1, "a copied public scene does not attest to validated assets");
});

test("mirrored occurrence keeps centered geometry and places mirrored bounds correctly", async () => {
  const { manifest, bytes } = fixture();
  manifest.nodes[2].transform[0] = -1;
  manifest.occurrences[0].transform[0] = -1;
  const scene = await adoptDocumentScene(manifest, async () => bytes);
  assert.equal(scene.parts[0].mirrored, true);
  assert.deepEqual(scene.parts[0].bounds, { min: [4, 20, 30], max: [5, 21, 30] });
  assert.equal(scene.parts[0].sourceMesh.vertices[3], 1);
  const model = buildModel(THREE, scene, { renderPartsIndividually: true });
  assert.equal(model.displayRecords[0].mesh.matrix.determinant(), -1);
  model.dispose();
});
