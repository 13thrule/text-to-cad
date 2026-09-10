// Viewport LOD scheduler (design/unified-tessellation.md Phase 5).
//
// Non-React glue between camera samples and level-keyed re-tessellation. The
// policy math lives in cadgen-js (lodPolicy.js — pure); this module owns TIME:
// debounce after camera movement, one replacement through scene adoption,
// worst projected error first, and cancellation on model replacement. Camera
// changes replan after the accepted replacement finishes. It knows nothing
// about three.js or React: the host feeds camera
// samples and receives level swaps through a callback.

import {
  LOD_CHORD_LEVELS,
  nextLevel,
  normalizeLodLevel,
  projectedChordErrorPx,
  settledLevel,
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
 *   onIdle?({ qualitySettled, unmetTargets, disposed }),
 *   debounceMs?, levels?,
 *   setTimeoutFn?/clearTimeoutFn? (test clocks),
 * })
 *
 * Host contract:
 *  - setComponents([{ cid, diagonal }]) once per model load (resets levels);
 *    `{ preserveLevels: true }` when the SAME model grows (progressive
 *    publish adds components per batch): retained cids keep their level and
 *    an in-flight load for a retained cid keeps running;
 *  - onCameraSample({ camera, viewportHeightPx, distanceFor(cid), cameraKey? })
 *    stamps numeric state and re-arms debounce. A stable cameraKey excludes
 *    geometry/accounting changes; only a new key or explicit `{ retry: true }`
 *    clears failures/pressure ceilings. Omitting the key means explicit retry;
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
  // (cid:level) loads that failed since the last camera/retry epoch. Without this
  // memo a persistently failing load busy-loops the drain (fail -> finally ->
  // re-plan -> same item); with it the failure parks until the camera moves.
  const failed = new Map(); // cid:level -> load/adoption failure reason
  // A successful intermediate adoption supplies measured bytes for a new
  // estimate. Only that changed current rung permits another admission check.
  const denied = new Map(); // cid:current:requested -> admission detail
  const pressureCeilings = new Map(); // cid -> highest rung until fresh camera intent
  let sampleEpoch = 0;
  let modelEpoch = 0;
  let lastPressure = false;
  let lastSample = null;
  let timer = null;
  let inFlight = null; // { cid, level, controller, reservation }
  let disposed = false;
  const floorLevel = normalizeLodLevel(minimumLevel);

  function setComponents(list, { preserveLevels = false } = {}) {
    const hadModel = components.size > 0 || lastSample !== null || inFlight !== null;
    if (!preserveLevels) {
      modelEpoch += 1;
      lastSample = null;
      lastPressure = false;
      if (timer !== null) {
        clearTimeoutFn(timer);
        timer = null;
      }
      failed.clear();
      denied.clear();
      pressureCeilings.clear();
    }
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
    if (!preserveLevels && hadModel) onIdle?.(qualityStatus());
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

  function onCameraSample(sample, { retry = false } = {}) {
    if (disposed) {
      return;
    }
    // Hosts supply cameraKey from camera/viewport state, excluding component
    // bounds. Publication/accounting resamples must not restart pressure loops.
    // An omitted key preserves the explicit-camera-call contract for hosts
    // without automatic resampling; retry is an explicit external intent.
    const fresh = !lastSample || retry || !Object.hasOwn(sample, "cameraKey") || sample.cameraKey !== lastSample.cameraKey;
    lastSample = sample;
    if (fresh) {
      sampleEpoch += 1;
      failed.clear();
      denied.clear();
      pressureCeilings.clear();
    }
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
        visible: lastSample.visibleFor?.(cid) !== false,
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

  function blocked(cid, currentLevel, level) {
    return failed.has(`${cid}:${level}`) || denied.has(`${cid}:${currentLevel}:${level}`);
  }

  function availableLevel(cid, currentLevel, targetLevel) {
    // All endpoints come from normalized component/policy levels. Prefer the
    // target, then strictly intermediate rungs, without same-state retries.
    const direction = Math.sign(targetLevel - currentLevel);
    if (!direction) return null;
    for (let level = targetLevel; level !== currentLevel; level -= direction) {
      if (level >= floorLevel && !blocked(cid, currentLevel, level)) return level;
    }
    return null;
  }

  function qualityStatus(entries = lastSample ? entriesForPlan() : [], pressure = lastPressure) {
    const byCid = new Map(entries.map((entry) => [entry.cid, entry]));
    const unmetTargets = [];
    for (const [cid, state] of components) {
      const entry = byCid.get(cid);
      const cameraTargetLevel = entry?.visible
        ? Math.max(floorLevel, settledLevel(entry.sample, state.level, levels))
        : Math.max(floorLevel, state.level);
      const blockedCoarsen = pressure && state.level > floorLevel && blocked(cid, state.level, state.level - 1);
      const targetLevel = blockedCoarsen ? state.level - 1 : cameraTargetLevel;
      if (targetLevel === state.level) continue;
      let blockedLevel = targetLevel;
      // The legacy floor path can require a blocked intermediate before the
      // final floor is even attempted (e.g. offscreen L0 -> L1 -> floor L2).
      if (state.level < floorLevel && !blocked(cid, state.level, targetLevel) && blocked(cid, state.level, state.level + 1)) {
        blockedLevel = state.level + 1;
      }
      const detail = denied.get(`${cid}:${state.level}:${blockedLevel}`);
      const ceiling = pressureCeilings.get(cid);
      const pressureLimited = (blockedCoarsen && !detail) || (pressure && targetLevel > state.level) ||
        (ceiling !== undefined && targetLevel > ceiling);
      const reason = pressureLimited ? "memory-pressure"
        : failed.get(`${cid}:${blockedLevel}`) || (detail ? "memory-denied" : "pending");
      unmetTargets.push({ cid, currentLevel: state.level, targetLevel, reason,
        ...(blockedCoarsen ? { cameraTargetLevel } : {}),
        ...(ceiling !== undefined ? { pressureCeiling: ceiling } : {}),
        ...(blockedLevel !== targetLevel ? { blockedLevel } : {}), ...(detail ? { detail } : {}) });
    }
    return {
      qualitySettled: !disposed && !!lastSample && !inFlight && timer === null && unmetTargets.length === 0,
      memoryPressure: pressure,
      unmetTargets,
      disposed,
    };
  }

  function parkFailure(task, reason) {
    if (!disposed && !task.controller.signal.aborted &&
        task.modelEpoch === modelEpoch && task.sampleEpoch === sampleEpoch) {
      failed.set(`${task.cid}:${task.level}`, reason);
    }
  }

  function planWork(entries, pressure) {
    const plan = [];
    for (const entry of entries) {
      if (!entry.visible) continue;
      const policyLevel = pressure
        ? nextLevel(entry.sample, entry.currentLevel, levels)
        : settledLevel(entry.sample, entry.currentLevel, levels);
      if (policyLevel === entry.currentLevel) continue;
      const targetLevel = Math.max(floorLevel, policyLevel);
      const admittedTarget = !pressure && targetLevel > entry.currentLevel
        ? Math.min(targetLevel, pressureCeilings.get(entry.cid) ?? targetLevel) : targetLevel;
      const level = pressure
        ? (blocked(entry.cid, entry.currentLevel, targetLevel) ? null : targetLevel)
        : availableLevel(entry.cid, entry.currentLevel, admittedTarget);
      if (level === null || level === entry.currentLevel || (pressure && level > entry.currentLevel)) continue;
      plan.push({ cid: entry.cid, level, targetLevel, errorPx: projectedChordErrorPx({
        ...entry.sample, chordRel: levels[entry.currentLevel],
      }) });
    }
    plan.sort((a, b) => b.errorPx - a.errorPx);
    if (!pressure && floorLevel > 0) {
      const planned = new Set(plan.map((item) => item.cid));
      for (const [cid, state] of components) {
        const level = state.level + 1;
        if (state.level >= floorLevel || planned.has(cid) || blocked(cid, state.level, level)) continue;
        plan.push({ cid, level, targetLevel: floorLevel, errorPx: 0 });
      }
    }
    if (pressure) {
      const planned = new Set(plan.map((item) => `${item.cid}:${item.level}`));
      for (const entry of entries) {
        if (entry.currentLevel <= floorLevel) continue;
        const level = entry.currentLevel - 1;
        const key = `${entry.cid}:${level}`;
        if (!planned.has(key) && !blocked(entry.cid, entry.currentLevel, level)) {
          plan.push({
            cid: entry.cid,
            level,
            targetLevel: level,
            errorPx: entry.visible ? projectedChordErrorPx({
              ...entry.sample,
              chordRel: levels[entry.currentLevel],
            }) : 0,
          });
        }
      }
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
    return plan;
  }

  function evaluate() {
    if (disposed || !lastSample || inFlight) return;
    // Each denied iteration removes a distinct candidate. Keep a large model's
    // denial drain off the call stack; only successful adoption changes state.
    let request;
    let reservation;
    while (!disposed && !inFlight) {
      const entries = entriesForPlan();
      const pressure = memoryPressure?.() === true;
      lastPressure = pressure;
      request = planWork(entries, pressure)[0];
      if (!request) {
        onIdle?.(qualityStatus(entries, pressure));
        return;
      }
      const { cid, level, targetLevel } = request;
      const currentLevel = components.get(cid)?.level ?? 0;
      const direction = level < currentLevel ? "coarsen" : "refine";
      reservation = reserveLevel?.({ cid, currentLevel, level, direction }) ?? { ok: true, token: null };
      if (reservation.ok !== false) { request = { ...request, pressure }; break; }
      const detail = { ...reservation.detail, cid, currentLevel, level, targetLevel, direction };
      denied.set(`${cid}:${currentLevel}:${level}`, detail);
      onLimitation?.(detail);
    }
    if (disposed || inFlight) {
      if (reservation?.ok !== false && reservation?.token) releaseLevel?.(reservation.token);
      return;
    }
    const { cid, level, pressure } = request;
    const currentLevel = components.get(cid)?.level ?? 0;
    const controller = new AbortController();
    const task = { cid, level, currentLevel, pressure, controller, reservation: reservation.token || null, sampleEpoch, modelEpoch };
    inFlight = task;
    let loaded;
    try {
      loaded = Promise.resolve(loadLevel(cid, level, { signal: controller.signal }));
    } catch (error) {
      loaded = Promise.reject(error);
    }
    loaded
      .then((payload) => {
        if (disposed || controller.signal.aborted) {
          return;
        }
        const state = components.get(cid);
        if (state) {
          const commitLevel = (applied) => {
            if (disposed || controller.signal.aborted) return;
            if (applied === false) {
              // A refused scene adoption is a failed attempt, not permission
              // to immediately requeue the same level in a microtask loop.
              parkFailure(task, "adoption-refused");
              return;
            }
            const current = components.get(cid);
            if (current) {
              current.level = level;
              if (task.pressure && level < task.currentLevel && task.sampleEpoch === sampleEpoch) {
                pressureCeilings.set(cid, Math.max(floorLevel, Math.min(pressureCeilings.get(cid) ?? level, level)));
              }
            }
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
        parkFailure(task, "load-failed");
      })
      .finally(() => {
        releaseReservation(task);
        if (inFlight !== task) return;
        inFlight = null;
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
    onIdle?.(qualityStatus());
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
      deniedAttempts: denied.size,
      pressureLimitedComponents: pressureCeilings.size,
      ...qualityStatus(),
    }),
  };
}
