// Byte attribution of what the viewer retains for the displayed model, read by
// the headless memory harness through window.__cadRenderMemoryProbe(). Every
// GPU-side array is counted once (occurrences share component geometry), split
// into surface geometry, CAD edge lines and raycast BVHs, beside the render
// asset caches' own accounting. It also refreshes the shared admission ledger.
import { renderAssetCacheStats } from "cadgen-js/lib/renderAssetClient.js";
import { cadEdgeInstanceSets } from "cadgen-js/common/cadEdgeInstances.js";
import { viewerMemoryPolicy } from "./viewerMemoryPolicy.js";

function geometryBuffers(geometry) {
  const buffers = new Set();
  if (geometry?.index) {
    buffers.add(geometry.index);
  }
  for (const attribute of Object.values(geometry?.attributes || {})) {
    buffers.add(attribute.isInterleavedBufferAttribute ? attribute.data : attribute);
  }
  return buffers;
}

function bvhBytes(geometry) {
  const roots = geometry?.boundsTree?._roots;
  if (!Array.isArray(roots)) {
    return 0;
  }
  return roots.reduce((sum, root) => sum + (root?.byteLength || 0), 0);
}

export function renderMemoryAccounting(runtime) {
  const records = Array.isArray(runtime?.displayRecords) ? runtime.displayRecords : [];
  const seenGeometries = new Set();
  const seenBuffers = new Set();
  const seenArrayBuffers = new Set();
  const seenMaterials = new Set();
  const totals = {
    occurrences: 0,
    edgeObjects: 0,
    edgeInstanceSets: 0,
    edgeInstances: 0,
    surfaceInstanceSets: 0,
    surfaceInstances: 0,
    surfaceInstanceBytes: 0,
    geometries: 0,
    buffers: 0,
    materials: 0,
    surfaceBytes: 0,
    edgeBytes: 0,
    bvhBytes: 0,
    bvhGeometries: 0,
    // Picking, which the byte accounting used to miss entirely: the triangle ->
    // face-row map is allocated PER OCCURRENCE (one Uint32 per occurrence
    // triangle), and the merged face/edge/vertex pick proxies carry their own
    // geometry and BVH. On an assembly with thousands of occurrences these are
    // the same order as the geometry itself, so a memory decision taken without
    // them is taken half-blind.
    faceIdBytes: 0,
    faceIdArrays: 0,
    pickBytes: 0,
    pickGeometries: 0,
    deformationBytes: 0
  };
  const visit = (object, kind) => {
    const geometry = object?.geometry;
    if (!geometry) {
      return;
    }
    for (const material of Array.isArray(object.material) ? object.material : [object.material]) {
      if (material) {
        seenMaterials.add(material);
      }
    }
    if (seenGeometries.has(geometry)) {
      return;
    }
    seenGeometries.add(geometry);
    for (const buffer of geometryBuffers(geometry)) {
      if (seenBuffers.has(buffer)) {
        continue;
      }
      seenBuffers.add(buffer);
      if (buffer.array?.buffer) seenArrayBuffers.add(buffer.array.buffer);
      totals[kind === "edge" ? "edgeBytes" : "surfaceBytes"] += buffer.array?.byteLength || 0;
    }
    const bvh = bvhBytes(geometry);
    if (bvh) {
      totals.bvhBytes += bvh;
      totals.bvhGeometries += 1;
    }
  };
  const seenFaceIds = new Set();
  const countFaceIds = (object) => {
    const faceIds = object?.userData?.faceIds;
    if (!ArrayBuffer.isView(faceIds) || seenFaceIds.has(faceIds)) {
      return;
    }
    seenFaceIds.add(faceIds);
    totals.faceIdBytes += faceIds.byteLength;
    totals.faceIdArrays += 1;
  };
  for (const record of records) {
    if (record?.mesh) {
      totals.occurrences += 1;
      visit(record.mesh, "surface");
      countFaceIds(record.mesh);
    }
    if (record?.edges) {
      totals.edgeObjects += 1;
      record.edges.traverse ? record.edges.traverse((child) => visit(child, "edge")) : visit(record.edges, "edge");
    }
    if (record?.edgeInstance) {
      totals.edgeInstances += 1;
    }
  }
  // Instanced CAD edges: one draw per component; its segment texture (shared
  // by every occurrence, cached on the component), instance texture and quad.
  const seenSegmentTextures = new Set();
  for (const set of cadEdgeInstanceSets(runtime)) {
    totals.edgeInstanceSets += 1;
    visit(set.object, "edge");
    for (const material of set.materials) {
      seenMaterials.add(material);
    }
    totals.edgeBytes += set.instanceByteLength;
    if (!seenSegmentTextures.has(set.segments)) {
      seenSegmentTextures.add(set.segments);
      totals.edgeBytes += set.segments.byteLength;
    }
  }
  // Instanced CAD surfaces share their component geometry with the proxy
  // records above, but own matrix/color attributes and a cloned draw material.
  // Those allocations must participate in admission even though they do not
  // appear in a record's private Mesh.
  const surfaceInstanceSets = runtime?.cadSurfaceInstanceSets
    || runtime?.cadScene?.runtime?.cadSurfaceInstanceSets
    || [];
  for (const set of surfaceInstanceSets) {
    const object = set?.object;
    if (!object) continue;
    totals.surfaceInstanceSets += 1;
    totals.surfaceInstances += Number(object.count) || set.records?.length || 0;
    visit(object, "surface");
    for (const buffer of [object.instanceMatrix, object.instanceColor]) {
      if (!buffer || seenBuffers.has(buffer)) continue;
      seenBuffers.add(buffer);
      if (buffer.array?.buffer) seenArrayBuffers.add(buffer.array.buffer);
      const byteLength = buffer.array?.byteLength || 0;
      totals.surfaceInstanceBytes += byteLength;
      totals.surfaceBytes += byteLength;
    }
  }
  // The merged pick proxies: their own geometry, their own BVH, their own
  // face-id map, all outside the display records.
  const pickRoots = [
    runtime?.facePickMesh,
    runtime?.facePickGroup,
    runtime?.edgePickGroup,
    runtime?.vertexPickGroup
  ];
  for (const root of pickRoots) {
    if (!root) {
      continue;
    }
    const visitPick = (object) => {
      countFaceIds(object);
      const geometry = object?.geometry;
      if (!geometry || seenGeometries.has(geometry)) {
        return;
      }
      seenGeometries.add(geometry);
      totals.pickGeometries += 1;
      for (const buffer of geometryBuffers(geometry)) {
        if (!seenBuffers.has(buffer)) {
          seenBuffers.add(buffer);
          if (buffer.array?.buffer) seenArrayBuffers.add(buffer.array.buffer);
          totals.pickBytes += buffer.array?.byteLength || 0;
        }
      }
      const bvh = bvhBytes(geometry);
      if (bvh) {
        totals.bvhBytes += bvh;
        totals.bvhGeometries += 1;
      }
    };
    if (typeof root.traverse === "function") {
      root.traverse(visitPick);
    } else {
      visitPick(root);
    }
  }
  // Tube deformation retains a refined rest mesh/mapping beside the posed
  // display geometry. Count typed arrays reachable from its private state that
  // were not already attributed to a visible geometry.
  const seenDeformationObjects = new Set();
  const visitDeformation = (value) => {
    if (!value || typeof value !== "object" || seenDeformationObjects.has(value)) return;
    seenDeformationObjects.add(value);
    if (ArrayBuffer.isView(value)) {
      if (!seenArrayBuffers.has(value.buffer)) {
        seenArrayBuffers.add(value.buffer);
        // A subview keeps the entire allocation alive. This matches the cache
        // accounting and prevents packed deformation state from looking free.
        totals.deformationBytes += value.buffer.byteLength;
      }
      return;
    }
    if (value instanceof ArrayBuffer) {
      if (!seenArrayBuffers.has(value)) {
        seenArrayBuffers.add(value);
        totals.deformationBytes += value.byteLength;
      }
      return;
    }
    for (const child of Object.values(value)) visitDeformation(child);
  };
  for (const record of records) visitDeformation(record?.tubeDeformationState);
  totals.geometries = seenGeometries.size;
  totals.buffers = seenBuffers.size;
  totals.materials = seenMaterials.size;
  const gpuEstimatedBytes = totals.surfaceBytes + totals.edgeBytes + totals.pickBytes;
  const displayCpuBytes = totals.surfaceBytes + totals.edgeBytes;
  const assetCaches = renderAssetCacheStats();
  viewerMemoryPolicy.setRetained("displayCpu", displayCpuBytes);
  viewerMemoryPolicy.setRetained("gpuEstimated", gpuEstimatedBytes);
  viewerMemoryPolicy.setRetained("bvh", totals.bvhBytes);
  viewerMemoryPolicy.setRetained("deformation", totals.deformationBytes);
  viewerMemoryPolicy.setRetained(
    "selectors",
    (Number(assetCaches.selector?.typedBytes) || 0) + totals.faceIdBytes + totals.pickBytes
  );
  viewerMemoryPolicy.setRetained("assetCaches", Object.entries(assetCaches).reduce(
    (sum, [name, stats]) => name === "surfLeash" || name === "selector"
      ? sum
      : sum + (Number(stats?.typedBytes) || 0),
    0
  ));
  return {
    ...totals,
    displayCpuBytes,
    gpuEstimatedBytes,
    assetCaches,
    memoryPolicy: viewerMemoryPolicy.snapshot(),
    at: typeof performance !== "undefined" ? performance.now() : Date.now()
  };
}
