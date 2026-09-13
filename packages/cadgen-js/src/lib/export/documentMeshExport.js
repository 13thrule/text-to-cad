// Static export from the same closed native mesh packets consumed by display.
// No package directory, source, surface extractor, geometry cache or Three scene.
import { validateDocumentManifest, MAX_ASSET_BYTES } from "../render/documentManifest.js";
import { decodeDocumentMesh } from "../render/documentMesh.js";
import { writeGlb } from "../glb/writeGlb.js";
import { xmlEscape, zipStore } from "./meshFormats.js";
import { linearToSrgb, srgbToLinear } from "../color.js";

export const DOCUMENT_MESH_EXPORT_VERSION = 1;
export const MAX_EXPORT_BYTES = 128 * 1024 ** 2;
const MAX_VARIANTS = 100_000;
const I = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
const BASIS = [.001, 0, 0, 0, 0, 0, .001, 0, 0, -.001, 0, 0, 0, 0, 0, 1];
const DEFAULT_RGBA = [212, 212, 216].map((v) => srgbToLinear(v / 255)).concat(1);
const text = new TextEncoder();
const key = (path) => JSON.stringify(path);
const columnMajor = (m) => m.map((_, i) => m[(i % 4) * 4 + Math.floor(i / 4)]);
const det = (m) => m[0] * (m[5] * m[10] - m[6] * m[9])
  - m[1] * (m[4] * m[10] - m[6] * m[8]) + m[2] * (m[4] * m[9] - m[5] * m[8]);
function fail(message) { throw new Error(`Native mesh export: ${message}`); }
function bounded(size, limit = MAX_EXPORT_BYTES) {
  if (!Number.isSafeInteger(size) || size < 0 || size > limit) fail("byte capacity exceeded");
}
function matrix(m) {
  if (!Number.isFinite(det(m)) || Math.abs(det(m)) < 1e-15) fail("singular occurrence transform");
  // glTF node matrices must decompose into TRS. Refuse shears explicitly.
  const columns = [0, 1, 2].map((axis) => [m[axis], m[4 + axis], m[8 + axis]]);
  for (let a = 0; a < 3; a++) for (let b = a + 1; b < 3; b++) {
    const dot = columns[a].reduce((sum, v, i) => sum + v * columns[b][i], 0);
    if (Math.abs(dot) > 1e-10 * Math.hypot(...columns[a]) * Math.hypot(...columns[b])) fail("sheared occurrence transform");
  }
}
function originMatrix(origin) {
  const m = [...I]; [m[3], m[7], m[11]] = origin; return m;
}
function point(m, p, origin, offset) {
  const x = p[offset] + origin[0], y = p[offset + 1] + origin[1], z = p[offset + 2] + origin[2];
  const result = [m[0] * x + m[1] * y + m[2] * z + m[3],
    m[4] * x + m[5] * y + m[6] * z + m[7], m[8] * x + m[9] * y + m[10] * z + m[11]];
  if (!result.every(Number.isFinite)) fail("nonfinite transformed vertex");
  return result;
}
function normal(points) {
  const u = points[1].map((v, i) => v - points[0][i]);
  const v = points[2].map((v, i) => v - points[0][i]);
  return [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]];
}
function xml(value) {
  const s = String(value);
  if (/[\u0000-\u0008\u000b\u000c\u000e-\u001f\ud800-\udfff\ufffe\uffff]/u.test(s)) fail("authored text is not XML text");
  return xmlEscape(s);
}
function authored(appearance) {
  // Closed author values only. None of the producer/owner identities reach bytes.
  return JSON.parse(JSON.stringify(appearance));
}
function canonicalNodes(validated) {
  const byPath = new Map(), children = new Map();
  return validated.nodes.map((row) => {
    const parentKey = key(row.path.slice(0, -1));
    const ordinal = (children.get(parentKey) || 0) + 1;
    children.set(parentKey, ordinal);
    const parent = byPath.get(parentKey);
    const path = [...(parent?.path || []), ordinal];
    const node = { ...row, originalKey: key(row.path), path, parent: parent ? key(parent.path) : undefined };
    matrix(row.transform);
    byPath.set(key(row.path), node);
    return node;
  });
}

async function capture(input, assets) {
  const validated = validateDocumentManifest(input);
  if (!(assets instanceof Map)) fail("assets must be a closed byte map");
  const owned = new Map();
  let total = 0;
  for (const row of Object.values(validated.manifest.prototypes)) {
    if (owned.has(row.mesh)) continue;
    const bytes = assets.get(row.mesh);
    if (!(bytes instanceof Uint8Array) || bytes.length !== row.bytes) fail("asset byte length mismatch");
    total += bytes.length; bounded(total, MAX_ASSET_BYTES);
    owned.set(row.mesh, Uint8Array.from(bytes));
  }
  if (owned.size !== assets.size) fail("unreferenced asset bytes");
  const meshes = new Map();
  for (const [identity, bytes] of owned) {
    const digest = [...new Uint8Array(await globalThis.crypto.subtle.digest("SHA-256", bytes))]
      .map((v) => v.toString(16).padStart(2, "0")).join("");
    if (digest !== identity) fail("asset digest mismatch");
    meshes.set(identity, decodeDocumentMesh(bytes));
  }
  const nodes = canonicalNodes(validated), nodeByOriginal = new Map(nodes.map((n) => [n.originalKey, n]));
  const variants = [], variantByKey = new Map();
  let variantBytes = 0;
  const occurrences = validated.manifest.occurrences.map((row) => {
    const node = nodeByOriginal.get(key(row.path));
    const meshKey = validated.manifest.prototypes[row.prototype].mesh;
    const mesh = meshes.get(meshKey);
    const own = row.appearance;
    if (own.face_colors?.some(([ordinal]) => ordinal >= mesh.header.faces.length)) fail("face color ordinal is absent");
    const recipe = JSON.stringify([meshKey, own.color || null, own.face_colors || [], own.pbr || {}]);
    let variant = variantByKey.get(recipe);
    if (!variant) {
      if (variants.length >= MAX_VARIANTS) fail("style variant capacity exceeded");
      variantBytes += mesh.indices.byteLength + mesh.header.faces.length * 64;
      bounded(variantBytes);
      const overrides = new Map(own.face_colors || []);
      const colors = mesh.header.faces.map(([ordinal]) => overrides.get(ordinal) || own.color || DEFAULT_RGBA);
      variant = { index: variants.length, mesh, colors, pbr: own.pbr || {} };
      variants.push(variant); variantByKey.set(recipe, variant);
    }
    return { ...row, path: node.path, variant };
  });
  return { nodes, occurrences, variants, meshes };
}

function facts(scene, format) {
  const omissions = [];
  for (const row of scene.occurrences) {
    const own = row.appearance, fields = [];
    if (format === "stl") fields.push(...Object.keys(own));
    if (format === "3mf") {
      for (const field of ["clearcoat", "clearcoatRoughness", "opacity"]) {
        if (Object.hasOwn(own.pbr || {}, field)) fields.push(`pbr.${field}`);
      }
      if (own.color?.[3] < 1 || own.face_colors?.some(([, rgba]) => rgba[3] < 1)) fields.push("color.alpha");
    }
    if (fields.length) omissions.push({ path: row.path, fields, reason: "format has no supported rendering representation" });
  }
  return { codec: DOCUMENT_MESH_EXPORT_VERSION, format,
    triangles: scene.occurrences.reduce((n, row) => n + row.variant.mesh.indices.length / 3, 0),
    prototypeVariants: scene.variants.length, occurrences: scene.occurrences.length,
    capabilities: { units: format === "glb" ? "meter" : "millimeter", instancing: format !== "stl",
      color: format === "glb" ? "linear-rgba" : format === "3mf" ? "srgb-rgb" : "none",
      pbr: format === "glb" ? ["roughness", "metalness", "clearcoat", "clearcoatRoughness", "opacity"]
        : format === "3mf" ? ["roughness", "metalness"] : [],
      authoredMetadata: format !== "stl" }, omissions,
    precision: { positions: format === "stl" ? "world-float32" : "native-local-float32-with-float64-transforms",
      color: format === "glb" ? "linear-json-number" : format === "3mf" ? "srgb-8-bit" : "none" } };
}

function stl(scene, name, metadata) {
  const count = metadata.triangles;
  bounded(84 + count * 50);
  const bytes = new Uint8Array(84 + count * 50), view = new DataView(bytes.buffer);
  bytes.set(text.encode(`cadgen ${name}`).subarray(0, 80)); view.setUint32(80, count, true);
  let offset = 84, maxError = 0;
  for (const row of scene.occurrences) {
    const { mesh } = row.variant;
    const flip = det(row.transform) < 0;
    for (let index = 0; index < mesh.indices.length; index += 3) {
      const ids = [mesh.indices[index], mesh.indices[index + (flip ? 2 : 1)], mesh.indices[index + (flip ? 1 : 2)]];
      const actual = ids.map((v) => point(row.transform, mesh.positions, mesh.header.origin, v * 3));
      const rounded = actual.map((p) => p.map((v) => {
        const f = Math.fround(v);
        if (!Number.isFinite(f)) fail("STL coordinate exceeds float32");
        maxError = Math.max(maxError, Math.abs(v - f)); return f;
      }));
      const n = normal(rounded), original = normal(actual), length = Math.hypot(...n);
      if (!length || !Number.isFinite(length) || n.reduce((sum, v, i) => sum + v * original[i], 0) <= 0) {
        fail("STL world precision collapses or reverses a triangle");
      }
      for (const value of [...n.map((v) => v / length), ...rounded.flat()]) {
        view.setFloat32(offset, value || 0, true); offset += 4;
      }
      offset += 2;
    }
  }
  metadata.precision.maxPositionRoundingMm = maxError;
  return bytes;
}

function glb(scene, name) {
  const primitives = [];
  const labelBytes = text.encode(name).length;
  let estimate = 4096;
  for (const mesh of scene.meshes.values()) estimate += mesh.positions.byteLength + mesh.normals.byteLength;
  for (const variant of scene.variants) {
    const groups = new Map();
    variant.mesh.header.faces.forEach((range, ordinal) => {
      const rgba = variant.colors[ordinal], colorKey = JSON.stringify(rgba);
      let group = groups.get(colorKey);
      if (!group) groups.set(colorKey, (group = { rgba, ranges: [], count: 0 }));
      group.ranges.push(range); group.count += range[4];
    });
    for (const group of groups.values()) {
      estimate += group.count * 4 + 2048 + labelBytes * 3; bounded(estimate);
      const indices = new Uint32Array(group.count); let offset = 0;
      for (const range of group.ranges) {
        indices.set(variant.mesh.indices.subarray(range[3], range[3] + range[4]), offset); offset += range[4];
      }
      primitives.push({ positions: variant.mesh.positions, normals: variant.mesh.normals, indices,
        linearColor: group.rgba, material: variant.pbr, node: `mesh${variant.index}`, name });
    }
  }
  const occurrences = new Map(scene.occurrences.map((row) => [key(row.path), row]));
  const sceneNodes = [{ key: "basis", matrix: columnMajor(BASIS), name }];
  for (const node of scene.nodes) {
    const id = key(node.path), row = occurrences.get(id);
    sceneNodes.push({ key: id, parent: node.parent || "basis", matrix: columnMajor(node.transform),
      name: node.label, extras: { cadPath: node.path, authored: authored(node.appearance) } });
    if (row) sceneNodes.push({ key: `${id}:mesh`, parent: id, mesh: `mesh${row.variant.index}`,
      matrix: columnMajor(originMatrix(row.variant.mesh.header.origin)), name: node.label });
  }
  estimate += text.encode(JSON.stringify(sceneNodes)).length * 2; bounded(estimate);
  return writeGlb({ primitives }, { preset: "export", name, units: "m", upAxis: "y", sceneNodes });
}

function threemf(scene, name, metadata) {
  const chunks = []; let length = 0;
  const put = (s) => { length += text.encode(s).length; bounded(length + 4096); chunks.push(s); };
  const xform = (m) => [m[0], m[4], m[8], m[1], m[5], m[9], m[2], m[6], m[10], m[3], m[7], m[11]].join(" ");
  const colorRows = [], colorKeys = new Map(); let maxColorError = 0;
  for (const variant of scene.variants) {
    variant.colorIndices = variant.colors.map((rgba) => {
      const value = [rgba.slice(0, 3), variant.pbr.roughness ?? .72, variant.pbr.metalness ?? .02];
      const identity = JSON.stringify(value);
      if (!colorKeys.has(identity)) {
        bounded((colorRows.length + 1) * 256);
        const rgb = rgba.slice(0, 3).map((v) => Math.round(linearToSrgb(v) * 255));
        maxColorError = Math.max(maxColorError, ...rgb.map((v, i) => Math.abs(srgbToLinear(v / 255) - rgba[i])));
        colorKeys.set(identity, colorRows.length);
        colorRows.push({ hex: `#${rgb.map((v) => v.toString(16).padStart(2, "0")).join("")}FF`, roughness: value[1], metalness: value[2] });
      }
      return colorKeys.get(identity);
    });
  }
  const nextId = 3 + scene.variants.length;
  const nodeIds = new Map(scene.nodes.map((node, index) => [key(node.path), nextId + index]));
  const occurrences = new Map(scene.occurrences.map((row) => [key(row.path), row]));
  const children = new Map();
  for (const node of scene.nodes) {
    if (node.parent !== undefined) {
      if (!children.has(node.parent)) children.set(node.parent, []);
      children.get(node.parent).push(node);
    }
  }
  put(`<?xml version="1.0" encoding="UTF-8"?><model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" xmlns:m="http://schemas.microsoft.com/3dmanufacturing/material/2015/02" xmlns:cadgen="urn:cadgen:document:mesh:1" requiredextensions="m"><metadata name="Title">${xml(name)}</metadata><resources>`);
  put('<m:pbmetallicdisplayproperties id="1">');
  colorRows.forEach((row, index) => put(`<m:pbmetallic name="finish-${index}" metallicness="${row.metalness}" roughness="${row.roughness}"/>`));
  put('</m:pbmetallicdisplayproperties><m:colorgroup id="2" displaypropertiesid="1">');
  colorRows.forEach((row) => put(`<m:color color="${row.hex}"/>`));
  put('</m:colorgroup>');
  for (const variant of scene.variants) {
    const mesh = variant.mesh;
    put(`<object id="${variant.index + 3}" type="model"><mesh><vertices>`);
    for (let i = 0; i < mesh.positions.length; i += 3) {
      put(`<vertex x="${mesh.positions[i]}" y="${mesh.positions[i + 1]}" z="${mesh.positions[i + 2]}"/>`);
    }
    put('</vertices><triangles>');
    mesh.header.faces.forEach((range, ordinal) => {
      for (let i = range[3]; i < range[3] + range[4]; i += 3) {
        const c = variant.colorIndices[ordinal];
        put(`<triangle v1="${mesh.indices[i]}" v2="${mesh.indices[i + 1]}" v3="${mesh.indices[i + 2]}" pid="2" p1="${c}" p2="${c}" p3="${c}"/>`);
      }
    });
    put('</triangles></mesh></object>');
  }
  // Children precede parents in resources, as required by the core spec.
  for (const node of [...scene.nodes].reverse()) {
    const id = key(node.path), row = occurrences.get(id);
    put(`<object id="${nodeIds.get(id)}" type="model" name="${xml(node.label)}"><metadatagroup><metadata name="cadgen:path" preserve="true">${xml(id)}</metadata><metadata name="cadgen:authored" preserve="true">${xml(JSON.stringify(authored(node.appearance)))}</metadata></metadatagroup><components>`);
    if (row) put(`<component objectid="${row.variant.index + 3}" transform="${xform(originMatrix(row.variant.mesh.header.origin))}"/>`);
    else for (const child of children.get(id) || []) {
      put(`<component objectid="${nodeIds.get(key(child.path))}" transform="${xform(child.transform)}"/>`);
    }
    put('</components></object>');
  }
  const root = scene.nodes[0];
  put(`</resources><build><item objectid="${nodeIds.get(key(root.path))}" transform="${xform(root.transform)}"/></build></model>`);
  metadata.precision.maxLinearColorRounding = maxColorError;
  return zipStore([
    { name: "[Content_Types].xml", body: '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>' },
    { name: "_rels/.rels", body: '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>' },
    { name: "3D/3dmodel.model", body: chunks.join("") },
  ]);
}

export async function exportDocumentMeshes(manifest, assets, formats, { name = "model" } = {}) {
  if (!Array.isArray(formats) || !formats.length || formats.length > 3 || new Set(formats).size !== formats.length
    || formats.some((value) => !["stl", "glb", "3mf"].includes(value))) fail("invalid static format request");
  if (typeof name !== "string" || !name || name.length > 4096) fail("invalid export label");
  const scene = await capture(manifest, assets);
  const products = [];
  let total = 0;
  for (const format of formats) {
    const metadata = facts(scene, format);
    const bytes = format === "stl" ? stl(scene, name, metadata)
      : format === "glb" ? glb(scene, name) : threemf(scene, name, metadata);
    total += bytes.length; bounded(total);
    products.push({ format, bytes, facts: metadata });
  }
  return products;
}
