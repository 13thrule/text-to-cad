import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import * as THREE from "three";
import { buildModel } from "../../common/cadScene.js";
import { adoptDocumentScene } from "./documentScene.js";
import { buildCadEdgeLines } from "./cadEdgeData.js";
import { bindDocumentPicking, documentComponentReference, documentFaceReference, documentEdgeReference } from "./documentPicking.js";

const I = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
function fixture(revision = 1, owner = "owner") {
  const positions = new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0, 2, 0, 0, 3, 0, 0, 2, 1, 0]);
  const normals = new Float32Array(positions.length);
  for (let i = 2; i < normals.length; i += 3) normals[i] = 1;
  const points = [], edges = [];
  for (const [ordinal, kind] of ["seam", "smooth", "sharp", "boundary", "nonmanifold", "free", "degenerate"].entries()) {
    const count = kind === "degenerate" ? 0 : ordinal % 2 + 2;
    edges.push([ordinal, points.length / 3, count, kind]);
    for (let i = 0; i < count; i++) points.push(i, ordinal, 0);
  }
  const values = [positions, normals, new Uint32Array([0, 1, 2, 3, 4, 5]), new Float32Array(points)];
  const header = { version: 2, discardedZeroAreaTriangles: 0,
    options: { relative_chord: .0015, angular: .35, edges: true }, linearDeflection: .01,
    origin: [10, 20, 30], bounds: { min: [10, 20, 30], max: [13, 26, 30] },
    faces: [[0, 0, 3, 0, 3], [1, 3, 3, 3, 3]], edges, buffers: {} };
  let offset = 0;
  ["positions", "normals", "indices", "edgePositions"].forEach((key, i) => {
    header.buffers[key] = { offset, bytes: values[i].byteLength, count: values[i].length,
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
  const hash = createHash("sha256").update(bytes).digest("hex");
  const manifest = { version: 1, owner, revision, prototypes: { prototype: { mesh: hash, bytes: bytes.length } },
    nodes: [{ path: ["root"], kind: "group", label: "Group", appearance: {}, transform: I }], occurrences: [] };
  for (let i = 0; i < 24; i++) {
    const path = ["root", `instance-${i}`], transform = [...I];
    transform[3] = i * 10;
    if (i % 2) { transform[0] = 0; transform[1] = -1; transform[4] = -1; transform[5] = 0; }
    manifest.nodes.push({ path, kind: "part", label: "Repeated", appearance: {}, transform });
    manifest.occurrences.push({ path, prototype: "prototype", label: "Repeated", appearance: {}, transform });
  }
  return { manifest, bytes };
}

test("every grouped CAD line segment retains its exact edge ordinal across all classes", () => {
  const polyline = (count) => new Float32Array(Array.from({ length: count * 3 }, (_, i) => i));
  const edges = [
    { ordinal: 40, visibilityClass: "seam", polyline: polyline(3) },
    { ordinal: 41, visibilityClass: "none", polyline: polyline(2) },
    { ordinal: 42, visibilityClass: "tangent", polyline: polyline(4) },
    { ordinal: 43, visibilityClass: "feature", polyline: polyline(2) },
    { ordinal: 44, visibilityClass: "boundary", polyline: polyline(3) },
    { ordinal: 45, visibilityClass: "nonManifold", polyline: polyline(2) },
    { ordinal: 46, visibilityClass: "unknown", polyline: polyline(2) },
    { ordinal: 47, visibilityClass: "degenerate", polyline: polyline(2) },
    { ordinal: 48, visibilityClass: "feature", polyline: polyline(1) },
  ];
  const lines = buildCadEdgeLines(edges, { retainOrdinals: true });
  edges[0].ordinal = 999;
  assert.deepEqual(lines.edgeRanges.map((row) => row.ordinal), [43, 44, 45, 46, 42, 40, 47]);
  assert.equal(lines.edgeRanges.reduce((count, row) => count + row.segmentCount, 0), lines.indices.length / 2);
  assert.equal(lines.edgeRanges, lines.edgeRanges, "intervals are built once");
  assert.equal(lines.edgeRanges[4].segmentStart, lines.classRanges[1].segmentStart);
  assert.ok(Object.isFrozen(lines.edgeRanges[0]));
  assert.equal(Object.hasOwn(buildCadEdgeLines(edges), "edgeRanges"), false, "ordinary Render sources opt out");
});

test("Render binding and face picks do not construct edge interval indices", () => {
  const scene = {}, source = { documentFaceRanges: [[0, 0, 3, 0, 3]] };
  let requests = 0;
  Object.defineProperty(source, "documentEdgePickRanges", { get() {
    requests++;
    return [{ ordinal: 9, segmentStart: 0, segmentCount: 1 }];
  } });
  bindDocumentPicking(scene, { owner: "owner", revision: 1,
    prototypes: { p: { mesh: "asset" } }, occurrences: [{ id: "opaque-occurrence-key", path: ["root", "child"], prototype: "p" }] },
  new Map([["asset", source]]));
  assert.equal(requests, 0);
  assert.equal(documentComponentReference(scene, "opaque-occurrence-key").kind, "component");
  assert.equal(documentFaceReference(scene, "opaque-occurrence-key", 0).ordinal, 0);
  assert.equal(requests, 0);
  assert.equal(documentEdgeReference(scene, "opaque-occurrence-key", 0).ordinal, 9);
  assert.equal(requests, 1);
});

test("mirrored placed instances share geometry while triangle and edge picks retain exact occurrence scope", async () => {
  const { manifest, bytes } = fixture();
  const scene = await adoptDocumentScene(manifest, async () => bytes);
  const source = scene.parts[0].sourceMesh;
  assert.ok(scene.parts.every((part) => part.sourceMesh === source));
  const model = buildModel(THREE, scene, { renderPartsIndividually: true });
  model.root.updateMatrixWorld(true);
  for (const [i, part] of scene.parts.entries()) {
    for (let face = 0; face < 2; face++) {
      const record = model.displayRecords[i];
      const center = record.mesh.localToWorld(new THREE.Vector3(face * 2 + 1 / 3, 1 / 3, 0));
      const ray = new THREE.Raycaster(center.clone().add(new THREE.Vector3(0, 0, 10)), new THREE.Vector3(0, 0, -1));
      const hit = ray.intersectObject(record.mesh)[0];
      assert.ok(hit, "actual Three ray hits the placed/mirrored prototype");
      const ref = documentFaceReference(scene, part.id, hit.faceIndex);
      assert.equal(ref.ordinal, face);
      assert.deepEqual(ref.path, ["root", `instance-${i}`]);
      assert.equal(ref.prototype, "prototype");
      assert.equal(ref.owner, "owner");
      assert.equal(ref.revision, 1);
      assert.ok(Object.isFrozen(ref) && Object.isFrozen(ref.path));
    }
    const expected = [2, 3, 3, 4, 5, 5, 1, 1, 0];
    for (let segment = 0; segment < expected.length; segment++) {
      assert.equal(documentEdgeReference(scene, part.id, segment).ordinal, expected[segment]);
    }
    assert.equal(documentComponentReference(scene, part.id).ordinal, null);
  }
  assert.equal(source.documentEdgePickRanges.length, 6, "degenerate edges generate no pickable segments");
  model.dispose();
});

test("new revisions and owners reuse bytes but reject stale, forged and out-of-range picks", async () => {
  const firstInput = fixture(), secondInput = fixture(2), foreignInput = fixture(2, "foreign");
  const first = await adoptDocumentScene(firstInput.manifest, async () => firstInput.bytes);
  const second = await adoptDocumentScene(secondInput.manifest, () => assert.fail("asset refetch"), { previous: first });
  const foreign = await adoptDocumentScene(foreignInput.manifest, () => assert.fail("asset refetch"), { previous: second });
  assert.equal(first.parts[0].sourceMesh, foreign.parts[0].sourceMesh);
  for (const scene of [second, foreign]) {
    assert.throws(() => documentFaceReference(scene, first.parts[0].id, 0), /exact document revision/);
  }
  const part = second.parts[0];
  assert.equal(documentFaceReference(second, part.id, 0).revision, 2);
  assert.equal(documentFaceReference(foreign, foreign.parts[0].id, 0).owner, "foreign");
  for (const value of [-1, 2, Infinity, NaN, true, "0", 1e20]) {
    assert.throws(() => documentFaceReference(second, part.id, value), RangeError);
  }
  for (const value of [-1, 9, Infinity, true, "0"]) {
    assert.throws(() => documentEdgeReference(second, part.id, value), RangeError);
  }
  assert.throws(() => documentFaceReference({ ...second }, part.id, 0), /adopted document scene/);
  assert.throws(() => documentFaceReference(second, "forged", 0), /exact document revision/);
  second.documentRevision = { owner: "forged", revision: 999 };
  assert.equal(documentFaceReference(second, part.id, 0).revision, 2, "public metadata is not scope authority");
  assert.throws(() => { part.sourceMesh.documentFaceRanges[0][0] = 999; }, TypeError);
  assert.throws(() => { part.sourceMesh.documentFaceRanges = [[999, 0, 3, 0, 3]]; }, TypeError);
});
