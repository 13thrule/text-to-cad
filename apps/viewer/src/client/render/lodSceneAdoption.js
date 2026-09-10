// App-private backpressure between a LOD state publication and scene adoption.
// One scheduler operation owns one pending payload; nothing enters saved data.
// This confirms CPU/Three ownership and accounting, not a GPU upload fence.
export function createLodSceneAdoption({ currentContext, now = () => performance.now() }) {
  let pending = null;
  const stats = { requested: 0, adopted: 0, rejected: 0, lastWaitMs: 0, maxWaitMs: 0 };
  function settle(ok) {
    const request = pending;
    if (!request) return false;
    pending = null;
    request.signal?.removeEventListener("abort", request.abort);
    stats.lastWaitMs = Math.max(0, now() - request.startedAt);
    stats.maxWaitMs = Math.max(stats.maxWaitMs, stats.lastWaitMs);
    stats[ok ? "adopted" : "rejected"]++;
    request.resolve(ok);
    return ok;
  }
  function contextMatches(request) {
    const ctx = currentContext();
    return Boolean(ctx && ctx === request.context && ctx.file === request.file && ctx.meshHash === request.revision);
  }
  return {
    expect({ context, source, componentId, componentMesh, signal }) {
      settle(false);
      stats.requested++;
      const sourceIds = (source?.parts || []).filter(part => part.componentId === componentId)
        .map(part => part.occurrenceId || part.id);
      const ids = new Set(sourceIds);
      return new Promise(resolve => {
        const request = { context, file: context?.file, revision: context?.meshHash,
          componentId, componentMesh, ids, signal, resolve, startedAt: now(), abort: () => settle(false) };
        pending = request;
        if (signal?.aborted || !ids.size || ids.size !== sourceIds.length || sourceIds.some(id => !id)
          || !contextMatches(request)) settle(false);
        else signal?.addEventListener("abort", request.abort, { once: true });
      });
    },
    adopted(source) {
      const request = pending;
      if (!request) return false;
      if (!contextMatches(request)) return settle(false);
      // A progressive publication can supersede the original composed object
      // before React adopts it. Acknowledge the actual current source only if
      // it still contains every requested occurrence at the exact new payload.
      // The context's immutable descriptor publishes every occurrence of a CID
      // together, so a changed same-CID occurrence set is not that publication.
      if (source !== request.context.meshData) return false;
      const seen = new Set();
      for (const part of source?.parts || []) {
        if (part.componentId !== request.componentId) continue;
        const id = part.occurrenceId || part.id;
        if (!request.ids.has(id) || seen.has(id) || part.sourceMesh !== request.componentMesh) return settle(false);
        seen.add(id);
      }
      return settle(seen.size === request.ids.size);
    },
    failed(source) {
      if (pending && (!source || !contextMatches(pending) || source === pending.context.meshData)) settle(false);
    },
    checkContext() {
      if (pending && !contextMatches(pending)) settle(false);
    },
    cancel: () => settle(false),
    snapshot: () => ({ ...stats, pending: Number(!!pending), pendingMs: pending ? Math.max(0, now() - pending.startedAt) : 0 }),
  };
}
