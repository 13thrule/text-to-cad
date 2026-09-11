// Ephemeral per-tab editing state. Saved-file catalog entries remain immutable.
export function initialEditingPreview() {
  return {
    epoch: "",
    revision: 0,
    preview: null,
    previewUnavailable: false,
    saved: null,
    retainedSaved: null,
    state: "disconnected",
    error: "",
  };
}

export function previewGeometryChanged(previous, next) {
  return Boolean(previous && next && previous.file === next.file && previous.hash !== next.hash &&
    (previous.preview || next.preview));
}

export function reduceEditingPreview(current, next) {
  if (!next || typeof next !== "object") return current;
  if (!next.epoch) {
    return { ...current, state: "disconnected", error: next.error || "" };
  }
  const previous = current.epoch && current.epoch !== next.epoch ? initialEditingPreview() : current;
  const revision = Number(next.revision) || 0;
  if (revision < previous.revision) return current;
  const same = revision === previous.revision;
  const candidate = next.preview;
  let preview = candidate && (!same || !previous.preview || previous.preview.revision !== revision || candidate.sequence >= previous.preview.sequence)
    ? { ...candidate, revision } : previous.preview;
  if (JSON.stringify(preview) === JSON.stringify(previous.preview)) preview = previous.preview;
  const previewUnavailable = candidate
    ? false
    : next.previewUnavailable === true
      ? true
      : same
        ? previous.previewUnavailable === true
        : false;
  return {
    epoch: next.epoch,
    revision,
    preview,
    previewUnavailable,
    saved: next.saved || null,
    retainedSaved: next.saved || previous.saved || previous.retainedSaved || null,
    state: next.state || "building",
    error: next.error || "",
    output: next.output,
    file: next.file || next.output,
  };
}

export function editingPreviewEntry(state, catalogEntry) {
  if (!state.preview) return null;
  // Follow edits remains on the authored tree after this revision's STEP save.
  // The saved catalog is selected only for a completed revision which had no
  // matching preview (a no-op), or when the server says that preview's object
  // graph is gone. If the latest save failed, an earlier validated saved
  // result can still recover that expired preview. In all cases the catalog
  // must prove the exact saved tree and document-byte identities; a merely
  // pending revision must not displace the previous usable preview.
  const savedFallback = state.saved || (state.previewUnavailable ? state.retainedSaved : null);
  const savedMatchesCatalog = savedFallback &&
    catalogEntry?.hash === savedFallback.tree &&
    catalogEntry?.documentHash === savedFallback.documentHash;
  if (savedMatchesCatalog && (
    state.previewUnavailable === true || state.preview.revision !== state.revision
  )) return null;
  return {
    ...catalogEntry,
    file: catalogEntry?.file || state.file || state.output,
    kind: state.preview.kind || catalogEntry?.kind || "part",
    url: state.preview.url,
    hash: state.preview.tree,
    bytes: 0,
    documentHash: "",
    sourceUrl: "",
    sourceSidecar: null,
    appearanceHash: "",
    poseUrl: "",
    renderModuleUrl: catalogEntry?.renderModuleUrl || state.preview.renderModuleUrl || "",
    editingPreview: true,
    previewKinematics: state.preview.kinematics || null,
  };
}

export function editingPreviewLabel(state, showingPreview) {
  if (state.previewUnavailable && state.saved && !showingPreview) return "STEP saved · preview unavailable";
  if (state.error || state.state === "failed") return state.error || "Save failed";
  if (state.state === "disconnected") return showingPreview ? "Preview disconnected" : "Waiting for edits";
  if (state.saved) return showingPreview ? "Preview · STEP saved" : "Saved";
  if (showingPreview) return "Preview · saving STEP";
  if (["submitted", "queued", "building"].includes(state.state)) return "Building preview";
  return "Saved file";
}
