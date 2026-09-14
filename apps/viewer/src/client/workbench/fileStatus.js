function status(label, title, tone = "neutral", busy = false) {
  return { label, title, tone, busy };
}

function text(value) {
  return String(value || "").trim();
}

function previewIsCurrent(editingState) {
  const revision = Number(editingState?.revision) || 0;
  const previewRevision = Number(editingState?.preview?.revision) || 0;
  return Boolean(revision && previewRevision === revision);
}

function failureStatus(error, { hasGeometry, editingState, showingPreview }) {
  const editState = text(editingState?.state).toLowerCase();
  const editError = text(editingState?.error);
  const explicitEditFailure = editState === "failed" && editError;
  const blockedMissingPreview = editingState?.previewUnavailable
    && !hasGeometry
    && !editingState?.saved
    && !editingState?.retainedSaved;
  const failure = error || (explicitEditFailure || blockedMissingPreview
    ? { message: editError || "The live model is no longer available." }
    : null);
  if (!failure) {
    return null;
  }

  const record = typeof failure === "object" ? failure : {};
  if (record.severity === "warning") {
    return null;
  }
  const updatedModelVisible = showingPreview && previewIsCurrent(editingState);
  const usableModelVisible = Boolean(hasGeometry || showingPreview);
  const label = usableModelVisible ? "Update failed" : "Open failed";
  const detail = updatedModelVisible && explicitEditFailure
    ? "The updated model is visible, but the STEP file could not be written."
    : text(typeof failure === "string"
      ? failure
      : record.message || record.title || record.summary || record.error);
  return status(
    label,
    detail || (usableModelVisible
      ? "The existing model remains visible, but its update failed."
      : "The selected file could not be opened."),
    "error"
  );
}

/**
 * Resolve the single compact status shown beside the selected filename.
 *
 * `opening` covers every incomplete first load, including a progressive load
 * that already has partial geometry. `updating` covers a replacement of a
 * complete same-file view. `showingPreview` is true only after the current
 * authored preview has actually reached the viewport.
 */
export function resolveFileStatus({
  hasFile = false,
  error = null,
  opening = false,
  updating = false,
  loadingTitle = "",
  editingState = null,
  showingPreview = false,
  qualityStatus = null,
  hasGeometry = false
} = {}) {
  if (!hasFile) {
    return null;
  }

  const failure = failureStatus(error, { hasGeometry, editingState, showingPreview });
  if (failure) {
    return failure;
  }

  // A current preview is the result of the update. Its STEP save and any
  // remaining background preparation do not keep the filename busy.
  if (updating) {
    if (!showingPreview) {
      return status(
        "Updating",
        text(loadingTitle) || "Preparing the updated model.",
        "info",
        true
      );
    }
  } else if (opening) {
    return status(
      "Opening",
      text(loadingTitle) || "Opening the selected file.",
      "info",
      true
    );
  }

  if (error?.severity === "warning") {
    return status("Model warning", text(error.message || error.title), "warning");
  }

  if (qualityStatus?.state === "limited" || qualityStatus?.state === "error") {
    return status(
      "Limited detail",
      text(qualityStatus.title) || "Some model detail is unavailable.",
      "warning"
    );
  }

  return null;
}
