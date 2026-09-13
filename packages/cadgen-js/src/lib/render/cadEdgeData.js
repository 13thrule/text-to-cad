// The line pass groups CAD edges by class so display.edges.classes styles each
// one; every other edge class the extractor knows (boundary, nonManifold,
// unknown) draws as a feature edge, `none` is not drawn at all.
export const CAD_EDGE_LINE_CLASSES = Object.freeze(["feature", "tangent", "seam", "degenerate"]);

function lineClassForEdge(edge) {
  const visibilityClass = String(edge?.visibilityClass || "").trim();
  if (visibilityClass === "none") {
    return "";
  }
  return CAD_EDGE_LINE_CLASSES.includes(visibilityClass) ? visibilityClass : "feature";
}

// Indexed line segments for the GL_LINES edge pass: every polyline point once
// (`positions`, xyz), one Uint32 pair per segment (`indices`), both grouped by
// class in CAD_EDGE_LINE_CLASSES order so a class is a contiguous point range
// and a contiguous segment range (`classRanges`). Per segment this is 8 bytes
// plus ~14 bytes of shared points — about 1.5 bytes per surface triangle.
export function buildCadEdgeLines(edges, { retainOrdinals = false } = {}) {
  const byClass = new Map(CAD_EDGE_LINE_CLASSES.map((classId) => [classId, []]));
  let pointTotal = 0;
  let segmentTotal = 0;
  for (const edge of Array.isArray(edges) ? edges : []) {
    const classId = lineClassForEdge(edge);
    const polyline = edge?.polyline;
    if (!classId || !(polyline instanceof Float32Array) || polyline.length < 6) {
      continue;
    }
    byClass.get(classId).push(retainOrdinals ? { polyline, ordinal: edge.ordinal } : polyline);
    pointTotal += polyline.length / 3;
    segmentTotal += polyline.length / 3 - 1;
  }
  const positions = new Float32Array(pointTotal * 3);
  const indices = new Uint32Array(segmentTotal * 2);
  const classRanges = [];
  let pointCursor = 0;
  let segmentCursor = 0;
  for (const classId of CAD_EDGE_LINE_CLASSES) {
    const pointStart = pointCursor;
    const segmentStart = segmentCursor;
    for (const item of byClass.get(classId)) {
      const polyline = retainOrdinals ? item.polyline : item;
      positions.set(polyline, pointCursor * 3);
      const pointCount = polyline.length / 3;
      for (let point = 0; point + 1 < pointCount; point += 1) {
        indices[segmentCursor * 2] = pointCursor + point;
        indices[segmentCursor * 2 + 1] = pointCursor + point + 1;
        segmentCursor += 1;
      }
      pointCursor += pointCount;
    }
    if (segmentCursor > segmentStart) {
      classRanges.push({
        classId,
        pointStart,
        pointCount: pointCursor - pointStart,
        segmentStart,
        segmentCount: segmentCursor - segmentStart,
      });
    }
  }
  const result = { positions, indices, classRanges };
  if (retainOrdinals) {
    // Keep exact native ordinals through class grouping. Render allocates no
    // picking index. The first edge pick builds one interval per drawn edge,
    // shared by every occurrence of this geometry, never one entry per segment.
    let cached = null;
    Object.defineProperty(result, "edgeRanges", { get() {
      if (cached) return cached;
      const ranges = [];
      let start = 0;
      for (const classId of CAD_EDGE_LINE_CLASSES) {
        for (const { polyline, ordinal } of byClass.get(classId)) {
          if (!Number.isSafeInteger(ordinal) || ordinal < 0) {
            throw new Error("CAD edge picking requires exact nonnegative ordinals");
          }
          const count = polyline.length / 3 - 1;
          ranges.push(Object.freeze({ ordinal, segmentStart: start, segmentCount: count }));
          start += count;
        }
      }
      cached = Object.freeze(ranges);
      return cached;
    } });
  }
  return result;
}
