import { surfTessellationCacheKey } from "cadgen-js/lib/renderAssetClient.js";
import { lodTessellationForLevel, normalizeLodLevel } from "cadgen-js/lib/surf/lodPolicy.js";

import { resolvePackageAssetUrl } from "./packageAssetUrl.js";

export function matchingDisplayedPackageContext(displayed, meshState, file) {
  const expectedFile = String(file || "");
  if (!displayed?.complete || !meshState?.assemblyInteractionReady) return null;
  if (String(displayed.file || "") !== expectedFile || String(meshState.file || "") !== expectedFile) {
    return null;
  }
  return String(displayed.meshHash || "") === String(meshState.meshHash || "")
    ? displayed
    : null;
}

// Keep decoded geometry that is still visible alive across an atomic revision
// swap. Matching uses the render client's concrete immutable identity (source,
// full surfObject, cid and exact tessellation), never the display LOD label by
// itself. Composition applies the new descriptor's placements and appearance.
export function retainedComponentMeshesForRevision({
  previous,
  descriptor,
  meshUrl,
} = {}) {
  if (!previous?.descriptor || !previous?.meshUrl || !descriptor || !meshUrl) {
    return {};
  }
  const retained = {};
  for (const [cid, component] of Object.entries(descriptor.components || {})) {
    const oldComponent = previous.descriptor.components?.[cid];
    const meshData = previous.componentMeshDataByCid?.[cid];
    if (!oldComponent?.surf || !component?.surf || !meshData) continue;
    const level = normalizeLodLevel(
      previous.componentLodLevelByCid?.[cid] ?? meshData.lodLevel,
    );
    if (meshData.lodLevel != null && normalizeLodLevel(meshData.lodLevel) !== level) continue;
    const tessellation = lodTessellationForLevel(level);
    const oldKey = surfTessellationCacheKey(
      resolvePackageAssetUrl(previous.meshUrl, oldComponent.surf),
      tessellation,
      oldComponent,
    );
    const nextKey = surfTessellationCacheKey(
      resolvePackageAssetUrl(meshUrl, component.surf),
      tessellation,
      component,
    );
    if (oldKey === nextKey) retained[cid] = meshData;
  }
  return retained;
}
