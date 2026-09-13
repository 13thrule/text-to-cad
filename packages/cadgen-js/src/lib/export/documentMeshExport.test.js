import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { exportDocumentMeshes } from "./documentMeshExport.js";

const I = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
const move = (x) => I.map((v, i) => i === 3 ? x : v);
function fixture({ origin = [10, 20, 30], identity = "private-first", mirror = false } = {}) {
  const positions = new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 1, 0, 1, 0, 1, 1]);
  const arrays = [positions, new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1]),
    new Uint32Array([0, 1, 2, 3, 4, 5]), new Float32Array()];
  const header = { version: 2, discardedZeroAreaTriangles: 0, options: { relative_chord: .0015, angular: .35, edges: false },
    linearDeflection: .01, origin, bounds: { min: origin, max: origin.map((v) => v + 1) },
    faces: [[0, 0, 3, 0, 3], [1, 3, 3, 3, 3]], edges: [], buffers: {} };
  let offset = 0;
  ["positions", "normals", "indices", "edgePositions"].forEach((name, i) => {
    header.buffers[name] = { offset, bytes: arrays[i].byteLength, count: arrays[i].length,
      type: i === 2 ? "I" : "f", width: i === 2 ? 1 : 3 };
    offset += arrays[i].byteLength;
  });
  const json = new TextEncoder().encode(JSON.stringify(header));
  const start = 12 + json.length + (4 - json.length % 4) % 4, bytes = new Uint8Array(start + offset);
  bytes.set([67, 71, 77, 69, 83, 72, 0, 2]);
  new DataView(bytes.buffer).setUint32(8, json.length, true); bytes.set(json, 12);
  let cursor = start;
  for (const array of arrays) { bytes.set(new Uint8Array(array.buffer), cursor); cursor += array.byteLength; }
  const hash = createHash("sha256").update(bytes).digest("hex");
  const color = [.1234567890123456, .3456789012345678, .6789012345678901, .7];
  const pbr = { roughness: .27, metalness: .63, clearcoat: 0, clearcoatRoughness: .12, opacity: .4 };
  const material = { name: "Alloy", description: "Authored only", density: 2.7, density_name: "g/cm3", density_type: "mass" };
  const appearance = { color, pbr, material: "tag", physical_material: material };
  const root = identity + "-root", group = identity + "-group";
  const manifest = { version: 1, owner: identity + "-owner", revision: 37,
    nodes: [{ path: [root], kind: "group", label: "Assembly", transform: move(5), appearance },
      { path: [root, group], kind: "group", label: "Nested", transform: move(10), appearance: {} }],
    prototypes: { [identity]: { mesh: hash, bytes: bytes.length } }, occurrences: [] };
  for (let index = 0; index < 3; index++) {
    const path = [root, group, identity + index], local = move(index * 2), world = move(15 + index * 2);
    if (mirror && index === 0) local[0] = world[0] = -1;
    const own = index === 2 ? { face_colors: [[1, [.2, .3, .4, .8]]] } : {};
    manifest.nodes.push({ path, kind: "part", label: `Part ${index}`, transform: local, appearance: own });
    manifest.occurrences.push({ path, prototype: identity, label: `Part ${index}`, transform: world,
      appearance: { ...appearance, ...own } });
  }
  return { manifest, bytes, hash, assets: new Map([[hash, bytes]]) };
}
function glbJson(bytes) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  assert.equal(view.getUint32(0, true), 0x46546c67);
  assert.equal(view.getUint32(4, true), 2);
  assert.equal(view.getUint32(8, true), bytes.length);
  assert.equal(view.getUint32(16, true), 0x4e4f534a);
  return JSON.parse(new TextDecoder().decode(bytes.subarray(20, 20 + view.getUint32(12, true))));
}
async function loadGlb(bytes) {
  return new Promise((resolve, reject) => new GLTFLoader().parse(
    bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), "", resolve, reject));
}
function zipEntries(bytes) {
  // Independent stored-ZIP parser: directory and local records must agree.
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength), entries = new Map();
  let cursor = 0;
  while (view.getUint32(cursor, true) === 0x04034b50) {
    assert.equal(view.getUint16(cursor + 8, true), 0);
    const size = view.getUint32(cursor + 18, true), nameLength = view.getUint16(cursor + 26, true);
    const extra = view.getUint16(cursor + 28, true), start = cursor + 30 + nameLength + extra;
    const name = new TextDecoder().decode(bytes.subarray(cursor + 30, cursor + 30 + nameLength));
    entries.set(name, new TextDecoder().decode(bytes.subarray(start, start + size)));
    cursor = start + size;
  }
  let count = 0;
  while (view.getUint32(cursor, true) === 0x02014b50) {
    const n = view.getUint16(cursor + 28, true), e = view.getUint16(cursor + 30, true), c = view.getUint16(cursor + 32, true);
    const name = new TextDecoder().decode(bytes.subarray(cursor + 46, cursor + 46 + n));
    assert.ok(entries.has(name)); count++; cursor += 46 + n + e + c;
  }
  assert.equal(count, entries.size); assert.equal(view.getUint32(cursor, true), 0x06054b50);
  return entries;
}

test("native GLB retains exact linear RGBA, finish, indexed variants and repeated mesh nodes", async () => {
  const f = fixture(), [{ bytes, facts }] = await exportDocumentMeshes(f.manifest, f.assets, ["glb"]);
  const json = glbJson(bytes), color = f.manifest.nodes[0].appearance.color;
  assert.equal(json.meshes.length, 2); assert.equal(json.nodes.filter((node) => node.mesh === 0).length, 2);
  assert.equal(json.nodes.filter((node) => node.mesh === 1).length, 1);
  assert.deepEqual(json.materials[0].pbrMetallicRoughness.baseColorFactor, [...color.slice(0, 3), color[3] * .4]);
  assert.equal(json.materials[0].pbrMetallicRoughness.roughnessFactor, .27);
  assert.equal(json.materials[0].pbrMetallicRoughness.metallicFactor, .63);
  assert.deepEqual(json.materials[0].extensions.KHR_materials_clearcoat, { clearcoatFactor: 0, clearcoatRoughnessFactor: .12 });
  assert.equal(json.materials[0].alphaMode, "BLEND");
  const positions = json.meshes.flatMap((mesh) => mesh.primitives.map((p) => json.accessors[p.attributes.POSITION].bufferView));
  assert.equal(new Set(positions).size, 1, "style variants share the native indexed vertex buffer");
  assert.deepEqual(json.nodes[1].extras.authored.physical_material, f.manifest.nodes[0].appearance.physical_material);
  assert.equal(facts.precision.color, "linear-json-number"); assert.deepEqual(facts.omissions, []);
  const loaded = await loadGlb(bytes), bounds = new THREE.Box3().setFromObject(loaded.scene);
  assert.ok(bounds.min.distanceTo(new THREE.Vector3(.025, .030, -.021)) < 1e-12);
  assert.ok(bounds.max.distanceTo(new THREE.Vector3(.030, .031, -.020)) < 1e-12);
  const meshes = []; loaded.scene.traverse((node) => { if (node.isMesh) meshes.push(node); });
  assert.equal(meshes.length, 4); // two plain occurrences and the two colored face primitives
  assert.equal(meshes[0].geometry.index.count, 6);
});

test("all bytes are deterministic across ephemeral owners, revisions, prototype and allocation keys", async () => {
  const a = fixture(), b = fixture({ identity: "secret-other-allocation" }); b.manifest.revision = 999;
  const aa = await exportDocumentMeshes(a.manifest, a.assets, ["stl", "glb", "3mf"]);
  const bb = await exportDocumentMeshes(b.manifest, b.assets, ["stl", "glb", "3mf"]);
  for (let i = 0; i < aa.length; i++) {
    assert.deepEqual(aa[i].bytes, bb[i].bytes);
    assert.ok(!new TextDecoder().decode(aa[i].bytes).includes("private-first"));
  }
});

test("STL stores millimeter world triangles and reverses mirrored winding", async () => {
  const f = fixture({ mirror: true }), [{ bytes, facts }] = await exportDocumentMeshes(f.manifest, f.assets, ["stl"]);
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  assert.equal(bytes.length, 84 + 6 * 50); assert.equal(view.getUint32(80, true), 6);
  const values = Array.from({ length: 12 }, (_, i) => view.getFloat32(84 + i * 4, true));
  assert.deepEqual(values, [0, 0, 1, 5, 20, 30, 5, 21, 30, 4, 20, 30]);
  assert.equal(facts.precision.maxPositionRoundingMm, 0);
  assert.equal(facts.capabilities.color, "none"); assert.equal(facts.omissions.length, 3);
});

test("large origin remains a GLB double transform, while a collapsed STL explicitly fails", async () => {
  const f = fixture({ origin: [1e12, 20, 30] });
  const [{ bytes }] = await exportDocumentMeshes(f.manifest, f.assets, ["glb"]);
  const json = glbJson(bytes), meshNode = json.nodes.find((node) => node.mesh === 0);
  assert.equal(meshNode.matrix[12], 1e12);
  const p = json.accessors[json.meshes[0].primitives[0].attributes.POSITION];
  assert.deepEqual(p.min, [0, 0, 0]); assert.deepEqual(p.max, [1, 1, 1]);
  await assert.rejects(exportDocumentMeshes(f.manifest, f.assets, ["stl"]), /precision collapses/);
});

test("3MF uses standard indexed color and metallic display resources with explicit omissions", async () => {
  const f = fixture(), [{ bytes, facts }] = await exportDocumentMeshes(f.manifest, f.assets, ["3mf"]);
  const entries = zipEntries(bytes), model = entries.get("3D/3dmodel.model");
  assert.equal(entries.size, 3); assert.match(model, /unit="millimeter"/);
  assert.match(model, /<m:colorgroup id="2" displaypropertiesid="1">/);
  assert.match(model, /metallicness="0.63" roughness="0.27"/);
  assert.equal((model.match(/<mesh>/g) || []).length, 2);
  assert.equal((model.match(/<component objectid="3"/g) || []).length, 2);
  assert.match(model, /transform="1 0 0 0 1 0 0 0 1 10 20 30"/);
  assert.match(model, /pid="2" p1="1" p2="1" p3="1"/);
  assert.equal(facts.capabilities.color, "srgb-rgb");
  assert.ok(facts.precision.maxLinearColorRounding > 0);
  assert.deepEqual(facts.omissions[0].fields, ["pbr.clearcoat", "pbr.clearcoatRoughness", "pbr.opacity", "color.alpha"]);
});

test("producer snapshots metadata and bytes before asynchronous hashing", async () => {
  const f = fixture(), expected = fixture();
  const pending = exportDocumentMeshes(f.manifest, f.assets, ["glb"]);
  f.bytes.fill(0); f.manifest.nodes.length = 0; f.manifest.occurrences[0].appearance.color[0] = 1;
  assert.deepEqual((await pending)[0].bytes, (await exportDocumentMeshes(expected.manifest, expected.assets, ["glb"]))[0].bytes);
});

test("bad byte binding, absent face, unsupported transforms and XML text fail closed", async () => {
  const bad = fixture(); bad.bytes[bad.bytes.length - 1] ^= 1;
  await assert.rejects(exportDocumentMeshes(bad.manifest, bad.assets, ["glb"]), /digest mismatch/);
  const face = fixture(); face.manifest.nodes[4].appearance.face_colors[0][0] = 2;
  await assert.rejects(exportDocumentMeshes(face.manifest, face.assets, ["glb"]), /face color ordinal/);
  const shear = fixture(); shear.manifest.nodes[2].transform[1] = .5; shear.manifest.occurrences[0].transform[1] = .5;
  await assert.rejects(exportDocumentMeshes(shear.manifest, shear.assets, ["glb"]), /sheared/);
  const label = fixture(); label.manifest.nodes[0].label = "bad\u0000label";
  await assert.rejects(exportDocumentMeshes(label.manifest, label.assets, ["3mf"]), /XML text/);
  label.manifest.nodes[0].label = "bad\ud800label";
  await assert.rejects(exportDocumentMeshes(label.manifest, label.assets, ["3mf"]), /XML text/);
});
