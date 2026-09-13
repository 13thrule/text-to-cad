import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import * as THREE from "three";
import { buildModel } from "../../common/cadScene.js";
import { adoptDocumentScene } from "./documentScene.js";
import { documentFaceReference } from "./documentPicking.js";
import { documentAppearance } from "./documentAppearance.js";

const I = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
const move = (x) => I.map((v, i) => i === 3 ? x : v);

test("document appearance transport honors native metadata limits", () => {
  assert.throws(() => documentAppearance({ face_colors: [[100_000, [1, 0, 0, 1]]] }), /appearance/);
  const material = { name: "Steel", description: "", density: 1e101, density_name: "", density_type: "" };
  assert.throws(() => documentAppearance({ physical_material: material }), /appearance/);
  assert.equal(documentAppearance({ physical_material: { ...material, density: 1e100 } })
    .physical_material.density, 1e100);
});

test("sparse face colors preserve the product of color alpha and PBR opacity on other faces", async () => {
  const { manifest, bytes } = fixture(1, true);
  manifest.nodes[0].appearance.pbr = { opacity: .4 };
  for (const row of manifest.occurrences) row.appearance.pbr.opacity = .4;
  const plain = await adoptDocumentScene(manifest, async () => bytes);
  const before = buildModel(THREE, plain, { renderPartsIndividually: true });
  assert.equal(before.displayRecords[0].sourceOpacity, .2);

  manifest.revision = 2;
  manifest.nodes[2].appearance.face_colors = [[0, [0, 1, 0, .8]]];
  manifest.occurrences[0].appearance.face_colors = [[0, [0, 1, 0, .8]]];
  const styled = await adoptDocumentScene(manifest, () => assert.fail("unchanged geometry refetch"), { previous: plain });
  const after = buildModel(THREE, styled, { renderPartsIndividually: true });
  const record = after.displayRecords[0], colors = record.geometry.getAttribute("color");
  assert.equal(record.sourceOpacity, .4);
  assert.equal(colors.getW(3) * record.sourceOpacity, before.displayRecords[0].sourceOpacity);
  assert.ok(Math.abs(colors.getW(0) * record.sourceOpacity - .32) < 1e-7);
  assert.equal(after.displayRecords[1].sourceOpacity, .2);
  before.dispose(); after.dispose();
});
function packet(twoFaces = false) {
  const first = [0, 0, 0, 1, 0, 0, 0, 1, 0], normal = [0, 0, 1, 0, 0, 1, 0, 0, 1];
  const values = [new Float32Array(twoFaces ? [...first, 0, 0, 1, 1, 0, 1, 0, 1, 1] : first),
    new Float32Array(twoFaces ? [...normal, ...normal] : normal), new Uint32Array(twoFaces ? [0, 1, 2, 3, 4, 5] : [0, 1, 2]),
    new Float32Array([0, 0, 0, 1, 0, 0])];
  const header = { version: 2, discardedZeroAreaTriangles: 0, options: { relative_chord: .0015, angular: .35, edges: true },
    linearDeflection: .01, origin: [10, 20, 30], bounds: { min: [10, 20, 30], max: [11, 21, twoFaces ? 31 : 30] },
    faces: twoFaces ? [[0, 0, 3, 0, 3], [1, 3, 3, 3, 3]] : [[0, 0, 3, 0, 3]], edges: [[0, 0, 2, "boundary"]], buffers: {} };
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
function fixture(revision = 1, twoFaces = false) {
  const bytes = packet(twoFaces), hash = createHash("sha256").update(bytes).digest("hex");
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

test("sparse face colors leave unauthored faces on the current display fill policy", async () => {
  const { bytes, manifest } = fixture(1, true);
  delete manifest.nodes[0].appearance.color;
  for (const row of manifest.occurrences) delete row.appearance.color;
  const plain = await adoptDocumentScene(manifest, async () => bytes);
  manifest.revision = 2;
  for (const node of manifest.nodes.filter((node) => node.kind === "part"))
    node.appearance.face_colors = [[0, [.2, .6, .4, .8]]];
  for (const row of manifest.occurrences) row.appearance.face_colors = [[0, [.2, .6, .4, .8]]];
  const styled = await adoptDocumentScene(manifest, () => assert.fail("same geometry"), { previous: plain });
  assert.deepEqual(Array.from(styled.parts[0].sourceMesh.defaultColorMask), [0, 0, 0, 1, 1, 1]);
  const settings = { renderPartsIndividually: true,
    materialSettings: { defaultColor: "#b6c4ce", fillColors: ["#b6c4ce", "#283040"],
      cycleColors: true, brightness: .8, tintStrength: .3, tintMode: "blend" } };
  const before = buildModel(THREE, plain, settings);
  const after = buildModel(THREE, styled, settings);
  function checkUnstyled() {
    for (let index = 0; index < before.displayRecords.length; index++) {
      const expected = before.displayRecords[index].material.color.toArray();
      const actual = after.displayRecords[index].geometry.getAttribute("color");
      for (let axis = 0; axis < 3; axis++) assert.ok(Math.abs(actual.array[3 * 4 + axis] - expected[axis]) < 1e-6);
      assert.equal(actual.getW(3), 1);
      assert.ok(Math.abs(actual.getW(0) - .8) < 1e-6);
    }
  }
  checkUnstyled();
  const oldGeometry = after.displayRecords[0].geometry;
  const oldColors = Array.from(oldGeometry.getAttribute("color").array);
  const otherOwner = buildModel(THREE, styled, settings);
  const update = { materialSettings: { ...settings.materialSettings, fillColors: ["#ffffff", "#101010"] } };
  before.update(update); after.update(update);
  checkUnstyled();
  assert.notEqual(after.displayRecords[0].geometry, oldGeometry);
  assert.deepEqual(Array.from(oldGeometry.getAttribute("color").array), oldColors);
  assert.deepEqual(Array.from(after.displayRecords[0].geometry.getAttribute("color").array.slice(0, 4)), oldColors.slice(0, 4),
    "changing the display fallback does not recolor authored faces");
  before.dispose(); after.dispose(); otherOwner.dispose();
});

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
    (m) => { m.nodes[0].appearance.arbitrary = "steel"; },
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

test("PBR fields inherit independently and exact face colors share geometry without tint or alpha loss", async () => {
  const { bytes, manifest } = fixture(1, true);
  manifest.nodes[0].appearance.pbr = { metalness: .7, roughness: .9 };
  manifest.nodes[0].appearance.material = "steel";
  for (let i = 0; i < 24; i++) {
    manifest.nodes[i + 2].appearance.face_colors = [[0, [0, 0, 1, .25]]];
    manifest.occurrences[i].appearance = {
      ...manifest.occurrences[i].appearance,
      pbr: { metalness: .7, roughness: .25 }, material: "steel",
      face_colors: [[0, [0, 0, 1, .25]]],
    };
  }
  const first = await adoptDocumentScene(manifest, async () => bytes);
  const source = first.parts[0].sourceMesh;
  assert.ok(first.parts.every((part) => part.sourceMesh === source));
  assert.equal(first.parts[0].color, null, "the material must not multiply authored face colors");
  assert.deepEqual(Array.from(source.colors.slice(0, 4)), [0, 0, 1, .25]);
  assert.deepEqual(Array.from(source.colors.slice(12, 16)), [1, 0, 0, .5]);
  assert.equal(first.parts[0].material.metalness, .7);
  assert.equal(first.parts[0].material.roughness, .25);
  assert.equal(documentFaceReference(first, first.parts[0].id, 1).ordinal, 1);

  const a = buildModel(THREE, first, { renderPartsIndividually: true });
  assert.equal(a.displayRecords[0].geometry.getAttribute("color").itemSize, 4);
  assert.equal(a.displayRecords[0].material.transparent, true);
  assert.equal(a.displayRecords[0].material.opacity, 1, "face alpha rides the vertex attribute once");
  assert.equal(a.displayRecords[0].material.color.getHex(), 0xffffff);
  manifest.revision++;
  const next = await adoptDocumentScene(manifest, () => assert.fail("appearance update refetched geometry"), { previous: first });
  assert.equal(next.parts[0].sourceMesh, source);
  const b = buildModel(THREE, next, { renderPartsIndividually: true });
  assert.equal(b.displayRecords[0].geometry, a.displayRecords[0].geometry);
  a.dispose();
  assert.ok(b.displayRecords[0].geometry.getAttribute("position"));
  b.dispose();
});

test("different face recipes keep native arrays and picking but own their color buffers", async () => {
  const { bytes, manifest } = fixture(1, true);
  for (let i = 0; i < 2; i++) {
    const colors = [[i, [0, 1, 0, 1]]];
    manifest.nodes[i + 2].appearance.face_colors = colors;
    manifest.occurrences[i].appearance.face_colors = colors;
  }
  const scene = await adoptDocumentScene(manifest, async () => bytes);
  const [a, b, plain] = scene.parts.map((part) => part.sourceMesh);
  assert.notEqual(a, b);
  assert.equal(a.vertices, b.vertices);
  assert.equal(a.vertices, plain.vertices);
  assert.equal(a.indices, b.indices);
  assert.equal(a.normals, b.normals);
  assert.notEqual(a.colors, b.colors);
  assert.deepEqual(Array.from(a.colors.slice(0, 3)), [0, 1, 0]);
  assert.deepEqual(Array.from(b.colors.slice(0, 3)), [1, 0, 0]);
  assert.equal(documentFaceReference(scene, scene.parts[1].id, 0).ordinal, 0);

  manifest.nodes[2].appearance.face_colors = [[2, [1, 1, 1, 1]]];
  manifest.occurrences[0].appearance.face_colors = [[2, [1, 1, 1, 1]]];
  await assert.rejects(adoptDocumentScene(manifest, async () => bytes), /face color ordinal/);
});
