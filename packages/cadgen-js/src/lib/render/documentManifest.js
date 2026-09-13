// Closed native document scene validation shared by display and static export.
import { documentAppearance as appearance, documentAppearanceBytes, mergeDocumentAppearance } from "./documentAppearance.js";

const HASH = /^[a-f0-9]{64}$/;
const identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
const MAX_NODES = 100_000;
const MAX_MANIFEST_BYTES = 16 * 1024 ** 2;
export const MAX_MESH_BYTES = 128 * 1024 ** 2;
export const MAX_ASSET_BYTES = 256 * 1024 ** 2;
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
export function validateDocumentManifest(input) {
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
    nodes.set(key, { node, path: p, local, own, label: row.label, world: multiply(parent?.world || identity, local),
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
  return { manifest: { owner: input.owner, revision: input.revision, prototypes, occurrences }, root,
    nodes: [...nodes.values()].map((row) => ({ path: row.path, label: row.label,
      transform: row.local, appearance: row.own, kind: row.node.nodeType === "part" ? "part" : "group" })) };
}

