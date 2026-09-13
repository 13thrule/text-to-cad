// Exact native selections for one adopted scene. Geometry intervals are shared;
// owner/revision/path/prototype scope always belongs to the occurrence being hit.
const scopes = new WeakMap();

/** Internal adoption hook. Inputs have passed documentScene's closed validator. */
export function bindDocumentPicking(scene, manifest, meshes) {
  const occurrences = new Map();
  for (const row of manifest.occurrences) {
    const source = meshes.get(manifest.prototypes[row.prototype].mesh);
    // Capture descriptors, not public mutable scene properties or arbitrary IDs.
    // In particular do not read the lazy edge interval getter during Render.
    const edgeRanges = Object.getOwnPropertyDescriptor(source, "documentEdgePickRanges").get;
    occurrences.set(row.id, {
      scope: Object.freeze({ version: 1, owner: manifest.owner, revision: manifest.revision,
        path: Object.freeze([...row.path]), prototype: row.prototype }),
      faces: source.documentFaceRanges,
      edges: () => edgeRanges.call(source),
    });
  }
  scopes.set(scene, occurrences);
}

function occurrence(scene, id) {
  const rows = scopes.get(scene);
  if (!rows) throw new TypeError("Picking requires an adopted document scene");
  if (typeof id !== "string" || !rows.has(id)) {
    throw new RangeError("Occurrence is absent from this exact document revision");
  }
  return rows.get(id);
}

function index(value) {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new RangeError("Document picking requires a nonnegative integer index");
  }
}

function find(ranges, value, start, count, ordinal) {
  let low = 0, high = ranges.length - 1;
  while (low <= high) {
    const middle = Math.floor((low + high) / 2), row = ranges[middle];
    if (value < start(row)) high = middle - 1;
    else if (value >= start(row) + count(row)) low = middle + 1;
    else return ordinal(row);
  }
  throw new RangeError("Pick index is absent from native topology ranges");
}

export function documentComponentReference(scene, occurrenceId) {
  return Object.freeze({ ...occurrence(scene, occurrenceId).scope, kind: "component", ordinal: null });
}

/** Three ray faceIndex is a local triangle index in the shared prototype mesh. */
export function documentFaceReference(scene, occurrenceId, triangleIndex) {
  const selected = occurrence(scene, occurrenceId);
  index(triangleIndex);
  // Face intervals already describe consecutive index triples. Binary-search
  // them directly: there is no per-triangle lookup allocation, even in Inspect.
  const ordinal = find(selected.faces, triangleIndex,
    (row) => row[3] / 3, (row) => row[4] / 3, (row) => row[0]);
  return Object.freeze({ ...selected.scope, kind: "face", ordinal });
}

/** Index into packed cadEdgeIndices PAIRS, after CAD line-class grouping.
 * A class-local line hit adds classRanges.segmentStart to its segment index.
 * A Three LineSegments hit exposes a starting index, so divide that by two.
 * Shader/instanced edge renderers must supply this same packed segment index.
 */
export function documentEdgeReference(scene, occurrenceId, packedSegmentIndex) {
  const selected = occurrence(scene, occurrenceId);
  index(packedSegmentIndex);
  const ordinal = find(selected.edges(), packedSegmentIndex,
    (row) => row.segmentStart, (row) => row.segmentCount, (row) => row.ordinal);
  return Object.freeze({ ...selected.scope, kind: "edge", ordinal });
}
