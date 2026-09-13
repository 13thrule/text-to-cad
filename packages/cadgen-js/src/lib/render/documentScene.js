// One scene adoption path for native document meshes, independent of React,
// source execution, STEP translation, and photographic lighting settings.
import { decodeDocumentMesh } from "./documentMesh.js";
import { buildCadEdgeLines } from "./cadEdgeData.js";
import { buildComposedPackageMeshData } from "../assembly/meshData.js";
import { bindDocumentPicking } from "./documentPicking.js";
import { validateDocumentManifest, MAX_MESH_BYTES, MAX_ASSET_BYTES } from "./documentManifest.js";

const adopted = new WeakMap();
function fail(message) { throw new Error(`Invalid document scene: ${message}`); }

function sourceMesh(mesh, inspection) {
  const origin = mesh.header.origin;
  const bounds = {
    min: mesh.header.bounds.min.map((value, axis) => value - origin[axis]),
    max: mesh.header.bounds.max.map((value, axis) => value - origin[axis]),
  };
  const edges = inspection ? mesh.header.edges.map(([ordinal, start, count, kind]) => ({
    ordinal, visibilityClass: kind === "smooth" ? "tangent" : kind === "seam" ? "seam" : "feature",
    polyline: mesh.edgePositions.subarray(start * 3, (start + count) * 3),
  })) : null;
  const lines = inspection ? buildCadEdgeLines(edges, { retainOrdinals: true }) : null;
  const source = {
    vertices: mesh.positions, normals: mesh.normals, indices: mesh.indices,
    colors: new Float32Array(0), edge_indices: new Uint32Array(0),
    cadEdgePositions: lines?.positions || new Float32Array(0),
    cadEdgeIndices: lines?.indices || new Uint32Array(0), cadEdgeClassRanges: lines?.classRanges || [],
    bounds, origin,
    parts: [{ id: "prototype", primitiveIndex: 0, vertexOffset: 0, vertexCount: mesh.positions.length / 3,
      triangleOffset: 0, triangleCount: mesh.indices.length / 3, bounds }],
  };
  Object.defineProperties(source, {
    documentFaceRanges: { enumerable: true,
      value: Object.freeze(mesh.header.faces.map((row) => Object.freeze([...row]))) },
  });
  if (inspection) Object.defineProperties(source, {
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
export async function adoptDocumentScene(input, fetchMesh, { previous = null, signal = null, inspection = true } = {}) {
  if (typeof inspection !== "boolean") throw new TypeError("Document inspection policy must be a boolean");
  const { manifest, root } = validateDocumentManifest(input);
  if (typeof fetchMesh !== "function") throw new TypeError("A document scene requires an asset reader");
  const priorCandidate = adopted.get(previous);
  const prior = priorCandidate?.inspection === inspection ? priorCandidate : null;
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
    meshes.set(id, sourceMesh(decodeDocumentMesh(owned), inspection));
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
  if (inspection) bindDocumentPicking(scene, manifest, meshes);
  // Native face/edge ordinals only resolve under this exact document revision.
  // A future correspondence resolver may explicitly remap an old selection.
  adopted.set(scene, { owner: manifest.owner, revision: manifest.revision, inspection, meshes, styles,
    sizes: new Map(Object.values(manifest.prototypes).map((row) => [row.mesh, row.bytes])) });
  return scene;
}
