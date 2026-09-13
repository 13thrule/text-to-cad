// Revision-bound native prototype packets. Geometry is decoded once and may be
// shared across occurrences; placement/material state does not live in this file.
const MAGIC = [67, 71, 77, 69, 83, 72, 0, 2];
const MAX_PACKET_BYTES = 128 * 1024 ** 2;
const MAX_HEADER_BYTES = 16 * 1024 ** 2;
const MAX_TOPOLOGY_ROWS = 100_000;
const LAYOUT = [
  ["positions", "f", 3, Float32Array],
  ["normals", "f", 3, Float32Array],
  ["indices", "I", 1, Uint32Array],
  ["edgePositions", "f", 3, Float32Array],
];
const EDGE_CLASSES = new Set(["free", "boundary", "nonmanifold", "sharp", "smooth", "seam", "degenerate"]);
const integer = (value) => Number.isSafeInteger(value) && value >= 0;
const vector = (value) => Array.isArray(value) && value.length === 3 && value.every(Number.isFinite);

function fail(message) {
  throw new Error(`Invalid document mesh: ${message}`);
}

function validateRanges(rows, vertices, indices = null) {
  if (!Array.isArray(rows) || rows.length > MAX_TOPOLOGY_ROWS) fail("topology ranges");
  let vertexOffset = 0;
  let indexOffset = 0;
  rows.forEach((row, ordinal) => {
    if (!Array.isArray(row) || row.length !== (indices ? 5 : 4)
      || !(indices ? row : row.slice(0, 3)).every(integer)
      || row[0] !== ordinal || row[1] !== vertexOffset) fail("topology ordinal");
    vertexOffset += row[2];
    if (!integer(vertexOffset) || vertexOffset > vertices) fail("topology vertex bounds");
    if (indices) {
      if (row[3] !== indexOffset || row[4] % 3 || row[2] < 3 || row[4] < 3) fail("face indices");
      const end = indexOffset + row[4];
      if (!integer(end) || end > indices.length) fail("topology index bounds");
      for (let i = indexOffset; i < end; i++) {
        if (indices[i] < row[1] || indices[i] >= vertexOffset) fail("face vertex range");
      }
      indexOffset = end;
    } else if (!EDGE_CLASSES.has(row[3])
      || (row[3] === "degenerate" ? row[2] !== 0 : row[2] < 2)) fail("edge class or point count");
  });
  if (vertexOffset !== vertices || (indices && indexOffset !== indices.length)) fail("topology coverage");
}

/**
 * Validates a closed little-endian packet and returns views over its owned byte
 * buffer. The caller must not mutate/transfer that buffer while its scene uses
 * it. No native objects, Three scenes, textures, or animation mixers are shared.
 */
export function decodeDocumentMesh(input) {
  let bytes = input instanceof ArrayBuffer ? new Uint8Array(input) : input;
  if (!(bytes instanceof Uint8Array) || bytes.length < 12 || bytes.length > MAX_PACKET_BYTES) fail("length");
  if (!MAGIC.every((value, index) => bytes[index] === value)) fail("version");
  // Network buffers are aligned. Accommodate a sliced container without making
  // one copy per attribute; only that unaligned packet needs an owning copy.
  // Buffer.slice() aliases its input, unlike Uint8Array.slice(). Use an
  // explicit typed-array copy for Node buffers as well as browser views.
  if (!(bytes.buffer instanceof ArrayBuffer) || bytes.buffer.resizable) fail("mutable buffer storage");
  if (bytes.byteOffset % 4) bytes = Uint8Array.from(bytes);
  if (new Uint8Array(new Uint32Array([1]).buffer)[0] !== 1) fail("host byte order");
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const headerLength = view.getUint32(8, true);
  const start = 12 + headerLength + (4 - headerLength % 4) % 4;
  if (!headerLength || headerLength > MAX_HEADER_BYTES || start > bytes.length) fail("descriptor length");
  let header;
  try {
    header = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes.subarray(12, 12 + headerLength)));
  } catch {
    fail("descriptor JSON");
  }
  if (header?.version !== 2 || !integer(header.discardedZeroAreaTriangles)
    || !header.buffers || typeof header.buffers !== "object"
    || Array.isArray(header.buffers) || Object.keys(header.buffers).length !== LAYOUT.length) fail("descriptor schema");
  const options = header.options;
  if (!options || Object.keys(options).length !== 3
    || !Number.isFinite(options.relative_chord) || options.relative_chord <= 0 || options.relative_chord > 1
    || !Number.isFinite(options.angular) || options.angular <= 0 || options.angular > Math.PI
    || typeof options.edges !== "boolean" || !Number.isFinite(header.linearDeflection)
    || header.linearDeflection <= 0) fail("meshing parameters");
  if (!vector(header.origin) || !vector(header.bounds?.min) || !vector(header.bounds?.max)
    || header.bounds.min.some((value, index) => value > header.bounds.max[index])) fail("bounds");
  const arrays = {};
  let offset = 0;
  for (const [name, type, width, Ctor] of LAYOUT) {
    const row = header.buffers[name];
    if (!row || row.type !== type || row.width !== width
      || !integer(row.count) || row.count % width || !integer(row.offset)
      || !integer(row.bytes) || row.offset !== offset || row.bytes !== row.count * 4
      || start + offset + row.bytes > bytes.length) fail("buffer range");
    const data = new Ctor(bytes.buffer, bytes.byteOffset + start + offset, row.count);
    if (type === "f") {
      for (let i = 0; i < data.length; i++) if (!Number.isFinite(data[i])) fail("nonfinite coordinate");
    }
    arrays[name] = data;
    offset += row.bytes;
  }
  if (start + offset !== bytes.length || arrays.positions.length < 9 || arrays.indices.length < 3
    || arrays.positions.length !== arrays.normals.length
    || arrays.indices.length % 3) fail("attribute counts");
  validateRanges(header.faces, arrays.positions.length / 3, arrays.indices);
  validateRanges(header.edges, arrays.edgePositions.length / 3);
  return { header, ...arrays };
}
