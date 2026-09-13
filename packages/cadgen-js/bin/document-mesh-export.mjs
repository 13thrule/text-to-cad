#!/usr/bin/env node
// Private closed-value entry. Filesystem capabilities are the three inherited
// regular descriptors; payloads contain no filenames, source or store lookups.
import fs from "node:fs";
import { createHash } from "node:crypto";
import { exportDocumentMeshes, MAX_EXPORT_BYTES } from "../src/lib/export/documentMeshExport.js";
import { MAX_ASSET_BYTES } from "../src/lib/render/documentManifest.js";

const MAX_HEADER = 16 * 1024 ** 2;
const INPUT_MAGIC = Buffer.from("CGEXIN01"), OUTPUT_MAGIC = Buffer.from("CGEXOU01");
const plain = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
const exact = (v, fields) => plain(v) && Object.keys(v).length === fields.length && fields.every((key) => Object.hasOwn(v, key));
const digest = (bytes) => createHash("sha256").update(bytes).digest("hex");
function readInput() {
  const stat = fs.fstatSync(0);
  if (!stat.isFile() || stat.size < 12 || stat.size > 12 + MAX_HEADER + MAX_ASSET_BYTES) throw new Error("input frame capacity");
  const bytes = fs.readFileSync(0);
  if (bytes.length !== stat.size || !bytes.subarray(0, 8).equals(INPUT_MAGIC)) throw new Error("input frame magic or size");
  const size = bytes.readUInt32LE(8);
  if (size > MAX_HEADER || size + 12 > bytes.length) throw new Error("input metadata capacity");
  const header = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes.subarray(12, 12 + size)));
  if (!exact(header, ["version", "manifest", "assets", "formats", "name"]) || header.version !== 1
    || !Array.isArray(header.assets) || header.assets.length > 100_000) throw new Error("input metadata schema");
  const assets = new Map(); let offset = 12 + size, total = 0;
  for (const row of header.assets) {
    if (!exact(row, ["sha256", "bytes"]) || !/^[a-f0-9]{64}$/.test(row.sha256)
      || !Number.isSafeInteger(row.bytes) || row.bytes < 12 || assets.has(row.sha256)) throw new Error("input asset schema");
    total += row.bytes;
    if (total > MAX_ASSET_BYTES || offset + row.bytes > bytes.length) throw new Error("input asset capacity");
    assets.set(row.sha256, bytes.subarray(offset, offset + row.bytes)); offset += row.bytes;
  }
  if (offset !== bytes.length) throw new Error("trailing input bytes");
  return { header, assets };
}
function writeAll(bytes) {
  for (let offset = 0; offset < bytes.length;) {
    const count = fs.writeSync(1, bytes, offset, Math.min(1024 ** 2, bytes.length - offset));
    if (!count) throw new Error("output write made no progress");
    offset += count;
  }
}
try {
  if (!fs.fstatSync(1).isFile()) throw new Error("output requires an owned regular descriptor");
  const { header, assets } = readInput();
  const products = await exportDocumentMeshes(header.manifest, assets, header.formats, { name: header.name });
  const metadata = Buffer.from(JSON.stringify({ version: 1, runtime: { node: process.version, v8: process.versions.v8 },
    products: products.map(({ format, bytes, facts }) => ({ format, bytes: bytes.length, sha256: digest(bytes), facts })) }));
  if (metadata.length > MAX_HEADER || products.reduce((sum, row) => sum + row.bytes.length, 0) > MAX_EXPORT_BYTES) {
    throw new Error("output frame capacity");
  }
  const prefix = Buffer.alloc(12); OUTPUT_MAGIC.copy(prefix); prefix.writeUInt32LE(metadata.length, 8);
  writeAll(prefix); writeAll(metadata);
  for (const product of products) writeAll(product.bytes);
} catch (error) {
  fs.writeSync(2, Buffer.from(String(error?.stack || error)).subarray(0, 16 * 1024));
  process.exitCode = 1;
}
