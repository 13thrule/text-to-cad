// One scene adoption path for native document meshes, independent of React,
// source execution, STEP translation, and photographic lighting settings.
import { decodeDocumentMesh } from "./documentMesh.js";
import { buildCadEdgeLines } from "./cadEdgeData.js";
import { buildComposedPackageMeshData } from "../assembly/meshData.js";
import { bindDocumentPicking } from "./documentPicking.js";
import { documentAppearance as appearance, documentAppearanceBytes, mergeDocumentAppearance } from "./documentAppearance.js";

const adopted = new WeakMap();
const HASH = /^[a-f0-9]{64}$/;
const identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
const MAX_NODES = 100_000;
const MAX_MANIFEST_BYTES = 16 * 1024 ** 2;
const MAX_MESH_BYTES = 128 * 1024 ** 2;
const MAX_ASSET_BYTES = 256 * 1024 ** 2;
const plain = (v) => v && typeof v === "object" && !Array.isArray(v);
const keys = (v, allowed) => plain(v) && Object.keys(v).every((key) => allowed.includes(key));
const pathKey = (path) => JSON.stringify(path);
const multiply = (a, b) => a.map((_, i) => [0, 1, 2, 3].reduce((sum, k) => sum + a[Math.floor(i / 4) * 4 + k] * b[k * 4 + i % 4], 0));
function fail(message) { throw new Error(`Invalid document scene: ${message}`); }
function transform(value) {
  if (!Array.isArray(value) || value.length !== 16 || !value.every(Number.isFinite)
    || value.slice(12).some((v, i) => v !== identity[12 + i])) fail("affine transform");
  return [...value];
}
function validateManifest(input) {
  if (!keys(input, ["version", "owner", "revision", "nodes", "occurrences", "prototypes"])
    || input.version !== 1 || typeof input.owner !== "string" || !input.owner || input.owner.length > 1024
    || !Number.isSafeInteger(input.revision) || input.revision < 1
    || !Array.isArray(input.nodes) || input.nodes.length > MAX_NODES
    || !Array.isArray(input.occurrences) || !input.occurrences.length || input.occurrences.length > MAX_NODES
    || !plain(input.prototypes) || Object.keys(input.prototypes).length > MAX_NODES) fail("manifest");
  // Copy only the bounded closed vocabulary, synchronously before any await.
  let metadataBytes = 0;
  const path = (value) => {
    if (!Array.isArray(value) || !value.length || value.length > 128
      || !value.every((key) => typeof key === "string" && key.length > 0 && key.length <= 1024)) fail("path");
    metadataBytes += value.reduce((n, key) => n + key.length * 6 + 3, 0) + 512;
    if (metadataBytes > MAX_MANIFEST_BYTES) fail("manifest size");
    return [...value];
  };
  const nodes = new Map();
  let root = null;
  const idFor = (p) => JSON.stringify([input.owner, input.revision, ...p]);
  for (const row of input.nodes) {
    if (!keys(row, ["path", "kind", "label", "transform", "appearance"])
      || !["group", "part"].includes(row.kind) || typeof row.label !== "string" || row.label.length > 4096) fail("node");
    const p = path(row.path), key = pathKey(p), local = transform(row.transform), own = appearance(row.appearance);
    if (row.kind === "group" && own.face_colors?.length) fail("group face colors");
    metadataBytes += row.label.length * 6 + documentAppearanceBytes(own);
    if (metadataBytes > MAX_MANIFEST_BYTES || nodes.has(key)) fail("node size or duplicate");
    const parent = nodes.get(pathKey(p.slice(0, -1)));
    const node = { id: idFor(p), name: row.label || p.at(-1), nodeType: row.kind === "group" ? "subassembly" : "part", children: [] };
    if (p.length === 1) {
      if (root) fail("multiple roots");
      root = node;
    } else {
      if (!parent || parent.node.nodeType === "part") fail("parent unavailable");
      parent.node.children.push(node);
    }
    nodes.set(key, { node, label: row.label, world: multiply(parent?.world || identity, local),
      appearance: mergeDocumentAppearance(parent?.appearance, own) });
  }
  if (!root) fail("root unavailable");
  const prototypes = Object.create(null), sizes = new Map();
  let total = 0;
  for (const [key, row] of Object.entries(input.prototypes)) {
    if (!key || key.length > 1024 || !keys(row, ["mesh", "bytes"]) || !HASH.test(row.mesh)
      || !Number.isSafeInteger(row.bytes) || row.bytes < 12 || row.bytes > MAX_MESH_BYTES) fail("prototype");
    metadataBytes += key.length * 6 + 128;
    if (metadataBytes > MAX_MANIFEST_BYTES) fail("manifest size");
    if (sizes.has(row.mesh) && sizes.get(row.mesh) !== row.bytes) fail("inconsistent asset size");
    if (!sizes.has(row.mesh)) total += row.bytes;
    if (total > MAX_ASSET_BYTES) fail("asset budget");
    sizes.set(row.mesh, row.bytes);
    prototypes[key] = { mesh: row.mesh, bytes: row.bytes };
  }
  const seen = new Set(), used = new Set();
  const occurrences = input.occurrences.map((row) => {
    if (!keys(row, ["path", "prototype", "transform", "label", "appearance"])) fail("occurrence fields");
    const p = path(row.path), key = pathKey(p), node = nodes.get(key);
    if (seen.has(key) || node?.node.nodeType !== "part" || row.label !== node.label) fail("occurrence membership");
    seen.add(key);
    const world = transform(row.transform), effective = appearance(row.appearance);
    metadataBytes += documentAppearanceBytes(effective);
    if (metadataBytes > MAX_MANIFEST_BYTES) fail("manifest size");
    if (!world.every((v, i) => Number.isFinite(node.world[i]) && v === node.world[i])
      || JSON.stringify(effective) !== JSON.stringify(node.appearance)) fail("node/occurrence disagreement");
    if (typeof row.prototype !== "string" || !Object.hasOwn(prototypes, row.prototype)) fail("prototype unavailable");
    used.add(row.prototype);
    return { id: idFor(p), path: p, prototype: row.prototype, transform: world, label: row.label, appearance: effective };
  });
  if ([...nodes.values()].filter(({ node }) => node.nodeType === "part").length !== seen.size
    || used.size !== Object.keys(prototypes).length) fail("incomplete geometry membership");
  return { manifest: { owner: input.owner, revision: input.revision, prototypes, occurrences }, root };
}

function sourceMesh(mesh) {
  const origin = mesh.header.origin;
  const bounds = {
    min: mesh.header.bounds.min.map((value, axis) => value - origin[axis]),
    max: mesh.header.bounds.max.map((value, axis) => value - origin[axis]),
  };
  const edges = mesh.header.edges.map(([ordinal, start, count, kind]) => ({
    ordinal, visibilityClass: kind === "smooth" ? "tangent" : kind === "seam" ? "seam" : "feature",
    polyline: mesh.edgePositions.subarray(start * 3, (start + count) * 3),
  }));
  const lines = buildCadEdgeLines(edges, { retainOrdinals: true });
  const source = {
    vertices: mesh.positions, normals: mesh.normals, indices: mesh.indices,
    colors: new Float32Array(0), edge_indices: new Uint32Array(0),
    cadEdgePositions: lines.positions, cadEdgeIndices: lines.indices, cadEdgeClassRanges: lines.classRanges,
    bounds, origin,
    parts: [{ id: "prototype", primitiveIndex: 0, vertexOffset: 0, vertexCount: mesh.positions.length / 3,
      triangleOffset: 0, triangleCount: mesh.indices.length / 3, bounds }],
  };
  Object.defineProperties(source, {
    documentFaceRanges: { enumerable: true,
      value: Object.freeze(mesh.header.faces.map((row) => Object.freeze([...row]))) },
    documentEdgeRanges: { enumerable: true,
      value: Object.freeze(mesh.header.edges.map((row) => Object.freeze([...row]))) },
    documentEdgePickRanges: { get: () => lines.edgeRanges },
  });
  return source;
}

function translatedOrigin(transform, origin) {
  const matrix = [...transform];
  for (let row = 0; row < 3; row++) {
    matrix[row * 4 + 3] += transform[row * 4] * origin[0]
      + transform[row * 4 + 1] * origin[1] + transform[row * 4 + 2] * origin[2];
  }
  if (!matrix.every(Number.isFinite)) fail("transformed mesh origin");
  return matrix;
}

function faceColorMesh(source, own) {
  // Packed faces have disjoint vertex intervals. A style variant owns only its
  // color attribute; positions, indices, normals and picking intervals stay
  // identical to the geometry-only mesh. Missing authored colors remain
  // explicit: the display runtime resolves those vertices from its own fill
  // policy without tinting authored faces or baking a theme into this source.
  const colors = new Float32Array(source.vertices.length / 3 * 4);
  const base = own.color || [0, 0, 0, 1];
  const defaultColorMask = own.color ? null : new Uint8Array(colors.length / 4).fill(1);
  for (let offset = 0; offset < colors.length; offset += 4) colors.set(base, offset);
  const ranges = new Map(source.documentFaceRanges.map((row) => [row[0], row]));
  for (const [ordinal, rgba] of own.face_colors) {
    const range = ranges.get(ordinal);
    if (!range) fail("face color ordinal is absent from the prototype");
    for (let vertex = range[1]; vertex < range[1] + range[2]; vertex++) {
      colors.set(rgba, vertex * 4);
      if (defaultColorMask) defaultColorMask[vertex] = 0;
    }
  }
  const variant = Object.defineProperties({}, Object.getOwnPropertyDescriptors(source));
  variant.colors = colors;
  variant.colorItemSize = 4;
  variant.defaultColorMask = defaultColorMask;
  variant.hasVertexAlpha = colors.some((value, index) => index % 4 === 3 && value < .999);
  return variant;
}

async function digestBytes(bytes) {
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  return Array.from(digest, (value) => value.toString(16).padStart(2, "0")).join("");
}

/** Return a complete candidate; never apply it to or dispose the previous scene.
 * Returned source arrays are scene-owned and must not be mutated by callers.
 * Revision-scoped IDs intentionally prevent implicit selection correspondence.
 */
export async function adoptDocumentScene(input, fetchMesh, { previous = null, signal = null } = {}) {
  const { manifest, root } = validateManifest(input);
  if (typeof fetchMesh !== "function") throw new TypeError("A document scene requires an asset reader");
  const prior = adopted.get(previous);
  const meshes = new Map();
  const check = () => signal?.throwIfAborted();
  for (const row of manifest.occurrences) {
    const id = manifest.prototypes[row.prototype].mesh;
    if (meshes.has(id)) continue;
    check();
    if (prior?.meshes.has(id)) {
      if (prior.sizes.get(id) !== manifest.prototypes[row.prototype].bytes) fail("reused asset size");
      meshes.set(id, prior.meshes.get(id));
      continue;
    }
    const fetched = await fetchMesh(id, { signal });
    check();
    const bytes = fetched instanceof ArrayBuffer ? new Uint8Array(fetched) : fetched;
    if (!(bytes instanceof Uint8Array) || !(bytes.buffer instanceof ArrayBuffer) || bytes.buffer.resizable
      || bytes.byteLength !== manifest.prototypes[row.prototype].bytes || bytes.byteLength > MAX_MESH_BYTES) fail("asset byte length/storage");
    // Own one snapshot across asynchronous hashing and all later zero-copy
    // attribute views. The fetcher's mutable input never becomes scene state.
    const owned = Uint8Array.from(bytes);
    const actual = await digestBytes(owned);
    if (actual !== id) throw new Error("Document mesh bytes do not match the requested asset");
    check();
    meshes.set(id, sourceMesh(decodeDocumentMesh(owned)));
  }
  check();
  const styles = new Map(), styleKeys = new Map(), components = new Map(meshes), occurrences = [];
  let styleBytes = 0;
  const nativeBytes = [...new Map(Object.values(manifest.prototypes).map((row) => [row.mesh, row.bytes])).values()]
    .reduce((sum, size) => sum + size, 0);
  for (const row of manifest.occurrences) {
    check();
    let component = manifest.prototypes[row.prototype].mesh;
    const source = meshes.get(component), matrix = translatedOrigin(row.transform, source.origin);
    const styled = !!row.appearance.face_colors?.length;
    if (styled) {
      const recipe = JSON.stringify([component, row.appearance.color || null, row.appearance.face_colors]);
      let key = styleKeys.get(recipe);
      if (!key) {
        key = `face-style:${await digestBytes(new TextEncoder().encode(recipe))}`;
        check();
        styleKeys.set(recipe, key);
        styleBytes += source.vertices.length / 3 * (4 * 4 + (row.appearance.color ? 0 : 1));
        if (nativeBytes + styleBytes > MAX_ASSET_BYTES) fail("appearance buffer budget");
        const variant = prior?.styles?.get(key) || faceColorMesh(source, row.appearance);
        styles.set(key, variant);
        components.set(key, variant);
      }
      component = key;
    }
    for (const x of [source.bounds.min[0], source.bounds.max[0]])
      for (const y of [source.bounds.min[1], source.bounds.max[1]])
        for (const z of [source.bounds.min[2], source.bounds.max[2]])
          for (let a = 0; a < 3; a++)
            if (!Number.isFinite(matrix[a * 4] * x + matrix[a * 4 + 1] * y + matrix[a * 4 + 2] * z + matrix[a * 4 + 3])) fail("transformed mesh bounds");
    occurrences.push({ id: row.id, component,
      name: row.label, transform: matrix,
      color: styled ? undefined : row.appearance.color, material: row.appearance.pbr });
  }
  const descriptor = { entryKind: root.nodeType === "part" ? "part" : "assembly",
    assembly: { root }, occurrences };
  const compatiblePrevious = prior?.owner === manifest.owner ? previous : null;
  const scene = buildComposedPackageMeshData(descriptor, components, { previous: compatiblePrevious });
  scene.documentRevision = Object.freeze({ owner: manifest.owner, revision: manifest.revision });
  bindDocumentPicking(scene, manifest, meshes);
  // Native face/edge ordinals only resolve under this exact document revision.
  // A future correspondence resolver may explicitly remap an old selection.
  adopted.set(scene, { owner: manifest.owner, revision: manifest.revision, meshes, styles,
    sizes: new Map(Object.values(manifest.prototypes).map((row) => [row.mesh, row.bytes])) });
  return scene;
}
