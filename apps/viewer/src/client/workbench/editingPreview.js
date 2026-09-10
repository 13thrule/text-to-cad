// Ephemeral per-tab editing state. Saved-file catalog entries remain immutable.
export function initialEditingPreview() {
  return { epoch: "", revision: 0, preview: null, saved: null, retainedSaved: null, state: "disconnected", error: "" };
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
  return {
    epoch: next.epoch,
    revision,
    preview,
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
  // Only the saved-byte resolver can restore the saved-file representation and
  // its bound sidecar. Until the catalog catches up, keep the usable preview.
  const saved = state.saved || (state.preview.revision < state.revision ? state.retainedSaved : null);
  if (saved && catalogEntry?.hash === saved.tree &&
      catalogEntry?.documentHash === saved.documentHash) return null;
  return {
    ...catalogEntry,
    file: catalogEntry?.file || state.file || state.output,
    kind: state.preview.kind || catalogEntry?.kind || "part",
    url: state.preview.url,
    hash: state.preview.tree,
    bytes: 0,
    documentHash: "",
    sourceUrl: "",
    poseUrl: "",
    renderModuleUrl: catalogEntry?.renderModuleUrl || state.preview.renderModuleUrl || "",
    editingPreview: true,
    previewKinematics: state.preview.kinematics || null,
  };
}

export function editingPreviewLabel(state, showingPreview) {
  if (state.error || state.state === "failed") return state.error || "Save failed";
  if (state.state === "disconnected") return showingPreview ? "Preview disconnected" : "Waiting for edits";
  if (state.saved) return "Saved";
  if (showingPreview) return "Preview · saving STEP";
  if (["submitted", "queued", "building"].includes(state.state)) return "Building preview";
  return "Saved file";
}
