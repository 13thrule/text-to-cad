// React face of viewport LOD (design/unified-tessellation.md Phase 5).
//
// Owns a lodScheduler for the current package: camera-settle events sample
// the viewer (projection, viewport height, live distances to each unique
// component's nearest visible occurrence), the scheduler picks the worst offender,
// the level-keyed loader re-tessellates it in the surf worker pool, and the
// payload swaps in through useCadAssets' re-composition. Kill switch for
// debugging: `window.__CAD_VIEWER_LOD__ = false` before loading a model.
import { useCallback, useEffect, useRef } from "react";

import { loadRenderSurfPayloadAtLevel, reclaimIdleSurfWorkers, releaseSurfWorkers } from "cadgen-js/lib/renderAssetClient.js";
import { estimateMeshRenderCost } from "cadgen-js/lib/render/meshCost.js";
import { lodTessellationForLevel } from "cadgen-js/lib/surf/lodPolicy.js";

import { createLodScheduler } from "./lodScheduler.js";
import { syncSurfWorkerMemory } from "./surfWorkerMemoryPolicy.js";
import { viewerMemoryPolicy } from "./viewerMemoryPolicy.js";
import { estimateViewportLodMemory } from "./viewportLodMemory.js";

function publishLodMemoryLimitation(detail) {
  if (typeof window === "undefined") return;
  window.__cadViewerMemoryLimitation = detail;
  window.__cadViewerMemory = viewerMemoryPolicy.snapshot();
  window.dispatchEvent(new CustomEvent("cad:memory-limitation", { detail }));
}

/** Report blocked camera targets, without clearing another subsystem's limit. */
export function syncViewportLodLimitation(status, policy = viewerMemoryPolicy, publish = publishLodMemoryLimitation) {
  const targets = status?.disposed ? [] : (status?.unmetTargets || [])
    .filter(({ reason }) => reason === "memory-denied" || reason === "memory-pressure");
  if (targets.length) {
    const detail = { source: "viewportLod", preservingCurrentView: true, unmetTargets: targets };
    policy.noteLimitation(detail);
    publish(detail);
  } else if (policy.snapshot().lastLimitation?.source === "viewportLod") {
    policy.clearLimitation();
    publish(null);
  }
}

function lodEnabled() {
  return typeof window === "undefined" || window.__CAD_VIEWER_LOD__ !== false;
}

export function useViewportLod({ viewerRef, lodPackage, applyComponentLodPayload, componentLodNeedsSelectors, dynamicScene = false }) {
  const componentsRef = useRef(new Map());
  const applyRef = useRef(applyComponentLodPayload);
  applyRef.current = applyComponentLodPayload;
  const selectorsRef = useRef(componentLodNeedsSelectors);
  selectorsRef.current = componentLodNeedsSelectors;
  const schedulerRef = useRef(null);
  const visibilityRef = useRef(null);

  useEffect(() => {
    const scheduler = createLodScheduler({
      // Harness-only quality floor: exact tessellation options still name
      // every mesh and export defaults are untouched.
      minimumLevel: typeof window !== "undefined" ? Number(window.__CAD_VIEWER_MIN_LOD__ || 0) : 0,
      reserveLevel: ({ cid, currentLevel, level, direction }) => {
        const component = componentsRef.current.get(cid);
        const { currentBytes, nextMeshBytes, admissionBytes } = estimateViewportLodMemory({
          meshBytes: component?.meshBytes,
          currentLevel,
          level,
        });
        const request = {
          category: "replacement",
          bytes: admissionBytes,
          label: `${cid}@L${level}`,
          kind: direction,
          replacingBytes: currentBytes,
          finalBytes: nextMeshBytes,
        };
        const reservation = viewerMemoryPolicy.reserve({ ...request, recordLimitation: false });
        if (reservation.ok) return reservation;
        reclaimIdleSurfWorkers();
        syncSurfWorkerMemory();
        return viewerMemoryPolicy.reserve({ ...request, recordLimitation: false });
      },
      releaseLevel: (token) => viewerMemoryPolicy.release(token),
      memoryPressure: () => {
        const memory = viewerMemoryPolicy.snapshot();
        return memory.availableBytes < memory.ownedLimitBytes * 0.15;
      },
      onLimitation: (detail) => {
        const owned = { ...detail, source: "viewportLod" };
        viewerMemoryPolicy.noteLimitation(owned);
        publishLodMemoryLimitation(owned);
      },
      onIdle: (status) => {
        syncViewportLodLimitation(status);
        releaseSurfWorkers().then(syncSurfWorkerMemory, syncSurfWorkerMemory);
      },
      loadLevel: (cid, level, { signal }) => {
        const component = componentsRef.current.get(cid);
        if (!component) {
          return Promise.reject(new Error(`unknown LOD component ${cid}`));
        }
        const { workerTemporaryBytes } = estimateViewportLodMemory({
          meshBytes: component.meshBytes,
          currentLevel: component.level,
          level,
        });
        return loadRenderSurfPayloadAtLevel(component.surfUrl, {
          signal,
          tessellation: lodTessellationForLevel(level),
          identity: component.identity,
          selectors: selectorsRef.current?.(cid) === true,
          memoryEstimateBytes: workerTemporaryBytes,
        }).finally(() => {
          syncSurfWorkerMemory();
        });
      },
      applyLevel: async (cid, level, payload, { signal }) => {
        if (await applyRef.current?.(cid, level, payload, { signal }) === false || signal.aborted) return false;
        const component = componentsRef.current.get(cid);
        if (component && payload?.meshData) {
          component.meshBytes = estimateMeshRenderCost(payload.meshData).typedArrayBytes;
          component.level = level;
        }
        // Observable swap signal: headless verification and debugging listen
        // for it; carries no payload references.
        if (typeof window !== "undefined") {
          window.dispatchEvent(new CustomEvent("cad:lod-level", { detail: { cid, level } }));
        }
        return true;
      }
    });
    schedulerRef.current = scheduler;
    const snapshot = () => ({ ...scheduler.snapshot(), visibility: visibilityRef.current });
    if (typeof window !== "undefined") window.__cadViewportLod = snapshot;
    return () => {
      scheduler.dispose();
      schedulerRef.current = null;
      if (typeof window !== "undefined" && window.__cadViewportLod === snapshot) delete window.__cadViewportLod;
    };
  }, []);

  // The package summary is republished per progressive-load batch (useCadAssets),
  // so the same file arriving again means the model GREW: keep the levels
  // already applied. A different file (or null between loads) is a reset.
  const lodPackageFileRef = useRef("");
  useEffect(() => {
    const components = lodEnabled() ? lodPackage?.components || [] : [];
    const file = String(lodPackage?.file || "");
    const preserveLevels = !!file && file === lodPackageFileRef.current;
    lodPackageFileRef.current = file;
    visibilityRef.current = null;
    componentsRef.current = new Map(components.map((component) => [component.cid, component]));
    schedulerRef.current?.setComponents(
      components.map(({ cid, diagonal, level }) => ({ cid, diagonal, level })),
      { preserveLevels }
    );
  }, [lodPackage]);

  // One numeric distance map per camera/summary/capability change. The sampler
  // checks whole occurrence bounds, never just centers or material visibility.
  // The scheduler owns the debounce and does not rescan records per component.
  const onCameraMoved = useCallback(() => {
    if (!componentsRef.current.size) {
      return;
    }
    const sampler = viewerRef.current?.sampleLodCamera?.({ components: componentsRef.current, dynamicScene });
    if (!sampler) {
      return;
    }
    visibilityRef.current = sampler.visibility;
    schedulerRef.current?.onCameraSample(sampler);
  }, [viewerRef, dynamicScene]);

  // Initial framing can notify before the package summary reaches this hook.
  // Sample once after installing the summary too: otherwise a stationary
  // camera leaves a newly published model coarse until the user moves it.
  useEffect(() => { onCameraMoved(); }, [lodPackage, onCameraMoved]);

  return { onCameraMoved };
}
