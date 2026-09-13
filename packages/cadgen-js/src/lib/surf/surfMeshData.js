// meshData from a .surf container (design/surface-rendering.md R2/R5).
//
// Produces the structure buildMeshDataFromGlbBuffer produced from a component
// GLB, so everything downstream — package composition, themes, selection
// ranges — is untouched by the artifact swap. Geometry is tessellated
// client-side from exact surfaces (grid + clip, curvature-driven), in CAD
// units, and handed on INDEXED: the tessellator's shared vertices, normals and
// index buffer are the render buffers, never expanded per corner. CAD edges
// ride beside the triangles as indexed line segments built from the same
// tessellation's boundary polylines (design/viewer-memory.md lever B).

import { linearRgbToHex } from "../color.js";
import { parseSurf } from "./container.js";
import { tessellateComponent } from "./tessellate.js";

import { buildCadEdgeLines } from "../render/cadEdgeData.js";

// A typed array is shared when it owns its buffer (a fresh tessellation) and
// copied when it is a view (a decoded .tess cache entry is one buffer holding
// positions, normals, face ords, indices, side ords and every polyline; sharing
// a view would keep the whole entry resident once the meshData outlives it).
function ownedArray(array, Ctor) {
  if (array instanceof Ctor && array.byteOffset === 0 && array.byteLength === array.buffer.byteLength) {
    return array;
  }
  return Ctor.from(array || []);
}

export function buildMeshDataFromSurf(index, floats, options = {}) {
  const component = options.component || tessellateComponent(index, floats, options);
  const vertices = ownedArray(component.positions, Float32Array);
  const normals = ownedArray(component.normals, Float32Array);
  const indices = ownedArray(component.indices, Uint32Array);
  const vertexCount = vertices.length / 3;
  const triangleCount = indices.length / 3;
  const cadEdges = buildCadEdgeLines(component.edges);

  const bounds = {
    min: [...component.bounds.min],
    max: [...component.bounds.max],
  };

  // The surf's partColor is LINEAR RGBA (a build123d/OCCT Color), while
  // `part.color` is the sRGB hex the viewer decodes with new THREE.Color.
  const partColor = Array.isArray(index.partColor) ? index.partColor : null;
  const color = partColor ? linearRgbToHex(partColor) : null;
  const part = {
    id: "surf:0",
    occurrenceId: "",
    primitiveIndex: 0,
    name: "",
    label: "",
    nodeType: "part",
    color,
    opacity: partColor && Number.isFinite(partColor[3]) ? partColor[3] : 1,
    hasSourceColors: Boolean(color),
    bounds,
    vertexOffset: 0,
    vertexCount,
    triangleOffset: 0,
    triangleCount,
    edgeIndexOffset: 0,
    edgeIndexCount: 0,
  };

  return {
    vertices,
    indices,
    normals,
    colors: new Float32Array(0),
    edge_indices: new Uint32Array(0),
    cadEdgePositions: cadEdges.positions,
    cadEdgeIndices: cadEdges.indices,
    cadEdgeClassRanges: cadEdges.classRanges,
    bounds,
    parts: [part],
    has_source_colors: Boolean(color),
    sourceColor: color || "",
  };
}

export function buildMeshDataFromSurfBuffer(buffer, options = {}) {
  const { index, floats } = parseSurf(buffer);
  return buildMeshDataFromSurf(index, floats, options);
}
