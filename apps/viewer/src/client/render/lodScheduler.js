// Viewport LOD scheduler (design/unified-tessellation.md Phase 5).
//
// Non-React glue between camera samples and level-keyed re-tessellation. The
// policy math lives in cadgen-js (lodPolicy.js — pure); this module owns TIME:
// debounce after camera movement, one re-tessellation in flight, worst
// projected error first, and cancellation when a newer sample changes the
// plan. It knows nothing about three.js or React: the host feeds camera
// samples and receives level swaps through a callback.

import {
  LOD_CHORD_LEVELS,
  normalizeLodLevel,
  planLodWork,
  projectedChordErrorPx
} from "cadgen-js/lib/surf/lodPolicy.js";

export const LOD_DEBOUNCE_MS = 200;

/**
 * createLodScheduler({
 *   loadLevel(cid, level, { signal }) -> Promise<payload>,
 *   applyLevel(cid, level, payload),
 *   reserveLevel?({ cid, currentLevel, level, direction }) -> { ok, token?, detail? },
 *   releaseLevel?(token),
 *   memoryPressure?() -> boolean,
 *   onLimitation?(detail),
 *   debounceMs?, levels?,
 *   setTimeoutFn?/clearTimeoutFn? (test clocks),
 * })
 *
 * Host contract:
 *  - setComponents([{ cid, diagonal }]) once per model load (resets levels);
 *    `{ preserveLevels: true }` when the SAME model grows (progressive
 *    publish adds components per batch): retained cids keep their level and
 *    an in-flight load for a retained cid keeps running;
 *  - onCameraSample({ camera, viewportHeightPx, distanceFor(cid) }) per
 *    camera change — cheap, just stamps state and re-arms the debounce;
 *  - dispose() on unmount.
 */
export function createLodScheduler({
  loadLevel,
  applyLevel,
  reserveLevel = null,
  releaseLevel = null,
  memoryPressure = () => false,
  onLimitation = null,
  onIdle = null,
  debounceMs = LOD_DEBOUNCE_MS,
  levels = LOD_CHORD_LEVELS,
  minimumLevel = 0,
  setTimeoutFn = (...args) => setTimeout(...args),
  clearTimeoutFn = (handle) => clearTimeout(handle),
} = {}) {
  const components = new Map(); // cid -> { diagonal, level }
  // (cid:level) loads that failed since the last camera sample. Without this
  // memo a persistently failing load busy-loops the drain (fail -> finally ->
  // re-plan -> same item); with it the failure parks until the camera moves.
  const failed = new Set();
  let lastSample = null;
  let timer = null;
  let inFlight = null; // { cid, level, controller, reservation }
  let disposed = false;
  const floorLevel = normalizeLodLevel(minimumLevel);

  function setComponents(list, { preserveLevels = false } = {}) {
    const previous = preserveLevels ? new Map(components) : null;
    components.clear();
    for (const { cid, diagonal, level } of list || []) {
      if (cid && Number.isFinite(diagonal) && diagonal > 0) {
        components.set(cid, {
          diagonal,
          level: previous?.get(cid)?.level ?? normalizeLodLevel(level),
        });
      }
    }
    // A model switch cancels stale work; a growing model keeps a load whose
    // component is still present (its level would otherwise be re-requested,
    // or a finer displayed level re-stepped through a coarser one).
    if (!preserveLevels || !inFlight || !components.has(inFlight.cid)) {
      cancelInFlight();
    }
    if (preserveLevels && lastSample && timer === null && !inFlight) {
      timer = setTimeoutFn(() => { timer = null; evaluate(); }, debounceMs);
    }
  }

  function cancelInFlight() {
    if (inFlight) {
      const task = inFlight;
      task.controller.abort();
      releaseReservation(task);
      inFlight = null;
    }
  }

  function releaseReservation(task) {
    if (!task?.reservation) return;
    const token = task.reservation;
    task.reservation = null;
    releaseLevel?.(token);
  }

  function onCameraSample(sample) {
    if (disposed) {
      return;
    }
    lastSample = sample;
    failed.clear();
    if (timer !== null) {
      clearTimeoutFn(timer);
    }
    timer = setTimeoutFn(() => {
      timer = null;
      evaluate();
    }, debounceMs);
  }

  function entriesForPlan() {
    const entries = [];
    for (const [cid, state] of components) {
      const cameraDistance = lastSample.distanceFor(cid);
      if (!Number.isFinite(cameraDistance)) {
        continue;
      }
      entries.push({
        cid,
        currentLevel: state.level,
        sample: {
          diagonal: state.diagonal,
          cameraDistance,
          camera: lastSample.camera,
          viewportHeightPx: lastSample.viewportHeightPx,
        },
      });
    }
    return entries;
  }

  function evaluate() {
    if (disposed || !lastSample || inFlight) {
      return;
    }
    const entries = entriesForPlan();
    const pressure = memoryPressure?.() === true;
    const plan = planLodWork(entries, levels)
      .map((item) => ({ ...item, level: Math.max(floorLevel, item.level) }))
      .filter((item) => item.level !== components.get(item.cid)?.level)
      .filter((item) => !failed.has(`${item.cid}:${item.level}`))
      .filter((item) => !pressure || item.level < (components.get(item.cid)?.level ?? 0));
    if (!pressure && floorLevel > 0) {
      const planned = new Set(plan.map((item) => item.cid));
      for (const [cid, state] of components) {
        const level = state.level + 1;
        if (state.level >= floorLevel || planned.has(cid) || failed.has(`${cid}:${level}`)) continue;
        plan.push({ cid, level, errorPx: 0 });
      }
    }
    if (pressure) {
      const planned = new Set(plan.map((item) => `${item.cid}:${item.level}`));
      for (const entry of entries) {
        if (entry.currentLevel <= 0) continue;
        const level = entry.currentLevel - 1;
        const key = `${entry.cid}:${level}`;
        if (!planned.has(key) && !failed.has(key)) {
          plan.push({
            cid: entry.cid,
            level,
            errorPx: projectedChordErrorPx({
              ...entry.sample,
              chordRel: levels[entry.currentLevel],
            }),
          });
        }
      }
    }
    if (!plan.length) {
      onIdle?.();
      return;
    }
    if (pressure) {
      // A downgrade releases retained detail. Under pressure it must run
      // before a visually useful but memory-increasing refinement.
      plan.sort((a, b) => {
        const aCurrent = components.get(a.cid)?.level ?? 0;
        const bCurrent = components.get(b.cid)?.level ?? 0;
        const aCoarsens = aCurrent > a.level;
        const bCoarsens = bCurrent > b.level;
        if (aCoarsens !== bCoarsens) return aCoarsens ? -1 : 1;
        return aCoarsens ? a.errorPx - b.errorPx : b.errorPx - a.errorPx;
      });
    }
    const { cid, level } = plan[0];
    const currentLevel = components.get(cid)?.level ?? 0;
    const direction = level < currentLevel ? "coarsen" : "refine";
    const reservation = reserveLevel?.({ cid, currentLevel, level, direction }) ?? { ok: true, token: null };
    if (reservation.ok === false) {
      failed.add(`${cid}:${level}`);
      onLimitation?.(reservation.detail || { cid, currentLevel, level, direction });
      // Try another component. The denied level stays parked until a fresh
      // camera sample (or changed retained accounting) explicitly retries it.
      evaluate();
      return;
    }
    const controller = new AbortController();
    const task = { cid, level, controller, reservation: reservation.token || null };
    inFlight = task;
    Promise.resolve(loadLevel(cid, level, { signal: controller.signal }))
      .then((payload) => {
        if (disposed || controller.signal.aborted) {
          return;
        }
        const state = components.get(cid);
        if (state) {
          const commitLevel = (applied) => {
            if (applied === false || disposed || controller.signal.aborted) return;
            const current = components.get(cid);
            if (current) current.level = level;
          };
          const applied = applyLevel(cid, level, payload, { signal: controller.signal });
          if (typeof applied?.then === "function") return applied.then(commitLevel);
          commitLevel(applied);
        }
      })
      .catch(() => {
        // Aborted or failed: the component stays at its current level and the
        // (cid, level) parks until the next camera sample. A failed level must
        // never break the model that already renders — or spin the drain.
        failed.add(`${cid}:${level}`);
      })
      .finally(() => {
        releaseReservation(task);
        if (inFlight?.controller === controller) {
          inFlight = null;
        }
        // More work may be queued behind the swap (other components, or the
        // next rung of this one) — keep draining until the plan is empty.
        if (!disposed) {
          evaluate();
        }
      });
  }

  function dispose() {
    disposed = true;
    if (timer !== null) {
      clearTimeoutFn(timer);
      timer = null;
    }
    cancelInFlight();
    onIdle?.();
  }

  return {
    setComponents,
    onCameraSample,
    dispose,
    // Introspection for tests and debugging overlays.
    levelOf: (cid) => components.get(cid)?.level ?? null,
    busy: () => inFlight !== null,
    snapshot: () => ({
      componentCount: components.size,
      levelCounts: [...components.values()].reduce((counts, state) => {
        counts[state.level] = (counts[state.level] || 0) + 1;
        return counts;
      }, {}),
      minimumLevel: floorLevel,
      belowMinimum: [...components.values()].filter((state) => state.level < floorLevel).length,
      busy: inFlight !== null,
      pendingEvaluation: timer !== null,
      failedLevels: failed.size,
    }),
  };
}
