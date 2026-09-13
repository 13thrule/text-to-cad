import test from "node:test";
import assert from "node:assert/strict";
import { decodeDocumentMesh } from "./documentMesh.js";

function packet(change = () => {}) {
  const header = {
    options: { relative_chord: .0015, angular: .35, edges: true }, linearDeflection: .01,
    version: 2, discardedZeroAreaTriangles: 2,
    origin: [10, 20, 30], bounds: { min: [10, 20, 30], max: [11, 21, 30] },
    faces: [[0, 0, 3, 0, 3]], edges: [[0, 0, 2, "boundary"]], buffers: {},
  };
  const values = {
    positions: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]),
    normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]),
    indices: new Uint32Array([0, 1, 2]), edgePositions: new Float32Array([0, 0, 0, 1, 0, 0]),
  };
  let offset = 0;
  for (const [name, value] of Object.entries(values)) {
    header.buffers[name] = { offset, bytes: value.byteLength, count: value.length,
      type: name === "indices" ? "I" : "f", width: name === "indices" ? 1 : 3 };
    offset += value.byteLength;
  }
  change(header, values);
  const encoded = new TextEncoder().encode(JSON.stringify(header));
  const start = 12 + encoded.length + (4 - encoded.length % 4) % 4;
  const result = new Uint8Array(start + offset);
  result.set([67, 71, 77, 69, 83, 72, 0, 2]);
  new DataView(result.buffer).setUint32(8, encoded.length, true);
  result.set(encoded, 12);
  let cursor = start;
  for (const value of Object.values(values)) {
    result.set(new Uint8Array(value.buffer), cursor);
    cursor += value.byteLength;
  }
  return result;
}

test("native mesh arrays share one transfer buffer and preserve topology ranges", () => {
  const bytes = packet();
  const mesh = decodeDocumentMesh(bytes);
  assert.deepEqual([...mesh.indices], [0, 1, 2]);
  assert.deepEqual(mesh.header.origin, [10, 20, 30]);
  assert.equal(mesh.header.discardedZeroAreaTriangles, 2);
  for (const name of ["positions", "normals", "indices", "edgePositions"]) {
    assert.equal(mesh[name].buffer, bytes.buffer);
  }
  assert.deepEqual(mesh.header.faces, [[0, 0, 3, 0, 3]]);
});

test("unaligned packet gets only one aligned backing copy", () => {
  const bytes = packet();
  const container = new Uint8Array(bytes.length + 1);
  container.set(bytes, 1);
  const mesh = decodeDocumentMesh(container.subarray(1));
  assert.notEqual(mesh.positions.buffer, container.buffer);
  assert.equal(mesh.positions.buffer, mesh.indices.buffer);
});

test("corrupt ranges, indices and finite coordinates are rejected", () => {
  const changes = [
    (h) => { h.version = 1; },
    (h) => { h.discardedZeroAreaTriangles = -1; },
    (h) => { h.discardedZeroAreaTriangles = true; },
    (h) => { delete h.discardedZeroAreaTriangles; },
    (h) => { h.linearDeflection = null; },
    (h) => { h.options.angular = true; },
    (h) => { h.options.edges = 1; },
    (h) => { h.buffers.normals.offset = 0; },
    (h) => { h.buffers.indices.count = -1; },
    (h) => { h.faces = []; },
    (h) => { h.edges[0][3] = "unknown"; },
    (h) => { h.bounds.min[0] = 1e6; },
    (_, v) => { v.indices[0] = 50; },
    (_, v) => { v.positions[0] = Infinity; },
  ];
  for (const change of changes) assert.throws(() => decodeDocumentMesh(packet(change)), /Invalid document mesh/);
  const valid = packet();
  const legacy = valid.slice();
  legacy[7] = 1;
  assert.throws(() => decodeDocumentMesh(legacy), /Invalid document mesh: version/);
  assert.throws(() => decodeDocumentMesh(valid.subarray(0, valid.length - 1)), /Invalid document mesh/);
  assert.throws(() => decodeDocumentMesh(new Uint8Array([...valid, 0])), /Invalid document mesh/);
});

test("unaligned Node Buffer is copied once, aligned Buffer stays zero-copy", () => {
  const bytes = packet();
  const container = Buffer.alloc(bytes.length + 4);
  container.set(bytes, 1);
  const mesh = decodeDocumentMesh(container.subarray(1, 1 + bytes.length));
  assert.notEqual(mesh.positions.buffer, container.buffer);
  assert.equal(mesh.positions.buffer, mesh.indices.buffer);
  container.set(bytes, 0);
  const aligned = decodeDocumentMesh(container.subarray(0, bytes.length));
  assert.equal(aligned.positions.buffer, container.buffer);
});

test("malicious topology ranges reject before walking declared counts", () => {
  for (const change of [
    (h) => { h.faces[0][4] = 9_000_000_000_000_000; },
    (h) => { h.faces[0][2] = 9_000_000_000_000_000; },
    (h) => { h.faces[0][4] = 0; },
    (h) => { h.edges[0][3] = "degenerate"; },
    (h) => { h.edges[0][2] = 1; },
  ]) assert.throws(() => decodeDocumentMesh(packet(change)), /Invalid document mesh/);
});

test("free and nonmanifold edges are preserved, concurrently mutable storage is rejected", () => {
  for (const kind of ["free", "nonmanifold"]) {
    const mesh = decodeDocumentMesh(packet((h) => { h.edges[0][3] = kind; }));
    assert.equal(mesh.header.edges[0][3], kind);
  }
  const bytes = packet();
  const shared = new Uint8Array(new SharedArrayBuffer(bytes.length));
  shared.set(bytes);
  assert.throws(() => decodeDocumentMesh(shared), /Invalid document mesh/);
  if (ArrayBuffer.prototype.resize) {
    const resizable = new Uint8Array(new ArrayBuffer(bytes.length, { maxByteLength: bytes.length * 2 }));
    resizable.set(bytes);
    assert.throws(() => decodeDocumentMesh(resizable), /Invalid document mesh/);
  }
});
