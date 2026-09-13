// A native snapshot consumes only its captured manifest and packed mesh assets.
// This module has no package/SURF/cache/source-module fallback.
import { adoptDocumentScene } from "../lib/render/documentScene.js";
import { validateDocumentManifest, MAX_MESH_BYTES, MAX_ASSET_BYTES } from "../lib/render/documentManifest.js";

export const DOCUMENT_ASSET_PREFIX = "/__document_asset/";
export const MAX_DOCUMENT_MANIFEST_BYTES = 16 * 1024 ** 2;
const HASH = /^[0-9a-f]{64}$/;
const FORBIDDEN = ["selection", "kinematics", "jointValues", "animation", "video", "pose",
  "selectorRuntime", "displayEdgeRuntime", "stepParameterUrl", "sourceSidecar", "meshData", "package", "url", "glbUrl"];
function fail(message) { throw new Error(`Invalid native snapshot: ${message}`); }
function object(value, keys, label) {
  if (!value || Object.getPrototypeOf(value) !== Object.prototype
      || Object.keys(value).some((key) => !keys.includes(key)) || keys.some((key) => !Object.hasOwn(value, key))) fail(label);
}
function length(value, max) { return Number.isSafeInteger(value) && value > 0 && value <= max; }
async function digest(bytes) {
  return [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))]
    .map((value) => value.toString(16).padStart(2, "0")).join("");
}

async function fetchBytes(identity, size, fetcher, signal) {
  signal?.throwIfAborted();
  const origin = globalThis.__cadgenSnapshotAssetOrigin || "";
  const response = await fetcher(`${origin}${DOCUMENT_ASSET_PREFIX}${identity}`, { signal, cache: "no-store" });
  if (!response.ok) fail(`asset HTTP ${response.status}`);
  const declared = response.headers.get("content-length");
  if (declared !== String(size) || !response.body?.getReader) fail("asset response length/stream");
  const reader = response.body.getReader(), bytes = new Uint8Array(size);
  let offset = 0, complete = false;
  try {
    for (;;) {
      signal?.throwIfAborted();
      const { value, done } = await reader.read();
      if (done) break;
      if (!(value instanceof Uint8Array) || offset + value.byteLength > size) fail("asset exceeded its admitted byte length");
      bytes.set(value, offset); offset += value.byteLength;
    }
    if (offset !== size) fail("truncated asset");
    complete = true;
    return bytes;
  } finally {
    try { if (!complete) await reader.cancel(); }
    finally { reader.releaseLock(); }
  }
}

export async function loadDocumentSnapshot(job, { tessellation = {}, signal = null, fetch: fetcher = globalThis.fetch } = {}) {
  if ((job.mode || "view") !== "view" || FORBIDDEN.some((key) => Object.hasOwn(job, key))) fail("unsupported motion, selection or mixed input");
  const resolved = job.resolved;
  if (Object.keys(resolved).some((key) => !["kind", "rootPath", "inputPath", "document", "inputHash"].includes(key))
      || !["step", "stp"].includes(resolved.kind) || (job.kind && !["step", "stp"].includes(job.kind))) fail("resolved source fields");
  const input = resolved.document;
  object(input, ["version", "owner", "revision", "manifest", "assets", "meshing"], "descriptor fields");
  if (input.version !== 1 || typeof input.owner !== "string" || !input.owner.length || input.owner.length > 4096
      || !Number.isSafeInteger(input.revision) || input.revision < 1) fail("revision");
  object(input.manifest, ["sha256", "bytes"], "manifest binding");
  if (!HASH.test(input.manifest.sha256) || !length(input.manifest.bytes, MAX_DOCUMENT_MANIFEST_BYTES)) fail("manifest bounds");
  object(input.meshing, ["relative_chord", "angular", "edges"], "mesh policy");
  const expected = { relative_chord: tessellation.chordTolerance ?? .0015,
    angular: tessellation.angleTolerance ?? .35, edges: job.render == null };
  if (Object.keys(expected).some((key) => input.meshing[key] !== expected[key])) fail("mesh policy differs from requested quality");
  if (!input.assets || Object.getPrototypeOf(input.assets) !== Object.prototype
      || !Object.keys(input.assets).length || Object.keys(input.assets).length > 100_000) fail("asset inventory");
  // Freeze authority before the first fetch, including inventory and appearance mode.
  const assets = new Map(); let total = 0;
  for (const [identity, row] of Object.entries(input.assets)) {
    object(row, ["bytes"], "mesh binding");
    if (!HASH.test(identity) || identity === input.manifest.sha256 || !length(row.bytes, MAX_MESH_BYTES)) fail("mesh bounds");
    total += row.bytes; if (total > MAX_ASSET_BYTES) fail("asset byte capacity");
    assets.set(identity, row.bytes);
  }
  const binding = { ...input.manifest }, owner = input.owner, revision = input.revision;
  const capturedResolved = { ...resolved, document: { ...input, manifest: binding,
    assets: Object.fromEntries([...assets].map(([id, bytes]) => [id, { bytes }])), meshing: { ...expected } } };
  const manifestBytes = await fetchBytes(binding.sha256, binding.bytes, fetcher, signal);
  if (await digest(manifestBytes) !== binding.sha256) fail("manifest hash mismatch");
  const manifest = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(manifestBytes));
  const validated = validateDocumentManifest(manifest).manifest;
  if (validated.owner !== owner || validated.revision !== revision) fail("manifest revision mismatch");
  const used = new Map(Object.values(validated.prototypes).map((row) => [row.mesh, row.bytes]));
  if (used.size !== assets.size || [...used].some(([id, size]) => assets.get(id) !== size)) fail("manifest asset inventory mismatch");
  const meshData = await adoptDocumentScene(manifest, async (identity) => {
    const bytes = await fetchBytes(identity, assets.get(identity), fetcher, signal);
    // The packet's policy is part of its hash but must also match this job.
    if (bytes.byteLength < 12) fail("mesh framing");
    const headerSize = new DataView(bytes.buffer).getUint32(8, true);
    if (headerSize > MAX_DOCUMENT_MANIFEST_BYTES || headerSize > bytes.byteLength - 12) fail("mesh header bounds");
    const header = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes.subarray(12, 12 + headerSize)));
    if (!header.options || Object.keys(expected).some((key) => header.options[key] !== expected[key])) fail("packed mesh policy mismatch");
    return bytes;
  }, { signal, inspection: expected.edges });
  return { kind: "step", meshData, selectorRuntime: null, displayEdgeRuntime: null,
    stepParameterSource: null, resolved: capturedResolved, url: "", glbUrl: "", cadPath: capturedResolved.inputPath || "" };
}
