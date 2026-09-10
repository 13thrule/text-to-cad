#!/usr/bin/env node
// Repository-only CPU/codec experiment. No browser, GPU or shared cache writes.
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { resolve, join } from "node:path";
import { createHash } from "node:crypto";
import { gzipSync } from "node:zlib";
import { performance } from "node:perf_hooks";
import { parseSurf } from "../../../packages/cadgen-js/src/lib/surf/container.js";
import { tessellateComponent, DEFAULT_OPTIONS, TESSELLATION_VERSION } from "../../../packages/cadgen-js/src/lib/surf/tessellate.js";
import { encodeComponentTessellation, decodeComponentTessellation, edgeClassesFromSurfIndex, TESS_CACHE_VERSION } from "../../../packages/cadgen-js/src/lib/surf/tessellationCache.js";

const argv = process.argv.slice(2);
const option = (key, fallback) => argv.includes(key) ? argv[argv.indexOf(key) + 1] : fallback;
const sha = (bytes) => createHash("sha256").update(bytes).digest("hex");
const asBuffer = (bytes) => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
const elapsed = (action) => { const start = performance.now(); const value = action(); return [value, performance.now() - start]; };

// Geometric audit is deliberately outside the timed meshing/codec sections.
function quality(mesh) {
  const { positions: p, normals, indices, faceRanges } = mesh;
  const epsilon = Math.max(1e-7, mesh.scale * 1e-6);
  const keys = [];
  for (let i = 0; i < p.length; i += 3) keys.push([p[i], p[i + 1], p[i + 2]].map(n => Math.round(n / epsilon)).join(","));
  const edges = new Map(), areas = {};
  let volume = 0, degenerate = 0, reversedNormals = 0, badNormals = 0;
  let invalidFaceReferences = 0, invalidSideReferences = 0;
  const edgeOrdinals = new Set(mesh.edges.map(edge => edge.ord));
  for (const ord of mesh.sideOrds) if (ord && !edgeOrdinals.has(ord)) invalidSideReferences++;
  for (let i = 0; i < normals.length; i += 3) if (Math.abs(Math.hypot(normals[i], normals[i + 1], normals[i + 2]) - 1) > 1e-3) badNormals++;
  for (const range of faceRanges) {
    let area = 0;
    for (let i = range.indexStart; i < range.indexStart + range.indexCount; i += 3) {
      const ids = [indices[i], indices[i + 1], indices[i + 2]];
      if (ids.some(id => mesh.faceOrds[id] !== range.ord)) invalidFaceReferences++;
      const a = ids[0] * 3, b = ids[1] * 3, c = ids[2] * 3;
      const ux = p[b] - p[a], uy = p[b + 1] - p[a + 1], uz = p[b + 2] - p[a + 2];
      const vx = p[c] - p[a], vy = p[c + 1] - p[a + 1], vz = p[c + 2] - p[a + 2];
      const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
      const length = Math.hypot(nx, ny, nz);
      if (length < epsilon * epsilon) { degenerate++; continue; }
      area += length / 2;
      volume += (p[a] * (p[b + 1] * p[c + 2] - p[b + 2] * p[c + 1]) + p[a + 1] * (p[b + 2] * p[c] - p[b] * p[c + 2]) + p[a + 2] * (p[b] * p[c + 1] - p[b + 1] * p[c])) / 6;
      const dot = nx * (normals[a] + normals[b] + normals[c]) + ny * (normals[a + 1] + normals[b + 1] + normals[c + 1]) + nz * (normals[a + 2] + normals[b + 2] + normals[c + 2]);
      if (dot < -1e-6 * length) reversedNormals++;
      for (let edge = 0; edge < 3; edge++) {
        const first = keys[ids[edge]], second = keys[ids[(edge + 1) % 3]];
        const key = first < second ? `${first}|${second}` : `${second}|${first}`;
        const before = edges.get(key) || [0, 0];
        edges.set(key, [before[0] + 1, before[1] + (first < second ? 1 : -1)]);
      }
    }
    areas[range.ord] = area;
  }
  return { signedVolume: volume, faceAreas: areas, weldEpsilonMm: epsilon, degenerateTriangles: degenerate,
    unmatchedEdges: [...edges.values()].filter(([n]) => n !== 2).length,
    inconsistentEdgeWinding: [...edges.values()].filter(([n, sign]) => n === 2 && sign !== 0).length,
    reversedNormalTriangles: reversedNormals, nonUnitNormals: badNormals,
    invalidFaceReferences, invalidSideReferences,
    faceOrdinals: faceRanges.map(range => range.ord), edgeOrdinals: mesh.edges.map(edge => edge.ord),
    labelledTriangleSides: [...mesh.sideOrds].filter(Boolean).length };
}

const reportPath = resolve(option("--report", "native-js.json"));
const iterations = Number(option("--iterations", "3"));
const cacheDir = resolve(option("--cache-dir", "models/tmp/native-mesh-benchmark"));
mkdirSync(cacheDir, { recursive: true });
const rows = [];
const nativeManifest = option("--decode-native", "");
if (nativeManifest) {
  const native = JSON.parse(readFileSync(nativeManifest, "utf8"));
  for (const row of native.rows) {
    const samples = [];
    let mesh;
    for (let i = 0; i < iterations; i++) {
      const [bytes, readMs] = elapsed(() => readFileSync(row.cachePath));
      const [decoded, decodeMs] = elapsed(() => decodeComponentTessellation(new Uint8Array(asBuffer(bytes))));
      if (!decoded) throw new Error("Native candidate is not a complete TESS payload");
      mesh = decoded.component;
      samples.push({ readMs, decodeMs });
    }
    rows.push({ cid: row.cid, chordTolerance: row.chordTolerance, samples, quality: quality(mesh) });
  }
} else {
  const view = resolve(option("--view", "models/tmp/perf-audit/view"));
  const descriptor = JSON.parse(readFileSync(join(view, "assembly.json"), "utf8"));
  const chords = option("--chords", "0.003,0.0015").split(",").map(Number);
  const names = Object.fromEntries(descriptor.occurrences.map(occ => [occ.component, occ.name]));
  for (const cid of Object.keys(descriptor.components).sort()) for (const chordTolerance of chords) {
    const sourcePath = join(view, "components", `${cid}.surf`);
    const inputBytes = readFileSync(sourcePath);
    const brep = readFileSync(join(view, "components", `${cid}.brep`));
    const options = { ...DEFAULT_OPTIONS, chordTolerance };
    const samples = [];
    let mesh, encoded, index;
    const hashes = [];
    for (let i = 0; i < iterations; i++) {
      const [bytes, readMs] = elapsed(() => readFileSync(sourcePath));
      const [parsed, parseMs] = elapsed(() => parseSurf(asBuffer(bytes)));
      index = parsed.index;
      const [result, meshMs] = elapsed(() => tessellateComponent(index, parsed.floats, options));
      mesh = result;
      const [cacheBytes, encodeMs] = elapsed(() => encodeComponentTessellation(mesh, { edgeClasses: edgeClassesFromSurfIndex(index), partColor: index.partColor ?? null }));
      encoded = cacheBytes;
      hashes.push(sha(encoded));
      samples.push({ readMs, parseMs, meshMs, encodeMs });
    }
    const cachePath = join(cacheDir, `js-${cid}-${chordTolerance}.tess`);
    writeFileSync(cachePath, encoded);
    const cachedSamples = [];
    for (let i = 0; i < iterations; i++) {
      const [bytes, readMs] = elapsed(() => readFileSync(cachePath));
      const [decoded, decodeMs] = elapsed(() => decodeComponentTessellation(new Uint8Array(asBuffer(bytes))));
      if (!decoded) throw new Error("JS cache decode failed");
      cachedSamples.push({ readMs, decodeMs });
    }
    rows.push({ cid, name: names[cid], chordTolerance, options, scale: mesh.scale, absoluteChordMm: mesh.scale * chordTolerance,
      surfBytes: inputBytes.length, surfSha256: sha(inputBytes), brepBytes: brep.length, brepSha256: sha(brep),
      faceCount: index.faces.length, edgeCount: index.edges.length,
      surfaceTypes: [...new Set(index.faces.map(face => face.surface?.kind || face.surfaceType))],
      vertices: mesh.positions.length / 3, triangles: mesh.indices.length / 3, encodedBytes: encoded.length,
      gzipBytes: gzipSync(encoded).length, meshHash: hashes[0], repeatDeterministic: new Set(hashes).size === 1,
      samples, cachedSamples, quality: quality(mesh), cachePath });
  }
}
writeFileSync(reportPath, JSON.stringify({ node: process.version, tessellationVersion: TESSELLATION_VERSION,
  cacheVersion: TESS_CACHE_VERSION, processPeakRssBytes: process.resourceUsage().maxRSS * 1024,
  timingBoundary: "Node CPU only; mesh, codec and page-cached filesystem reads separated; no network/main-thread/GPU", rows }, null, 2) + "\n");
