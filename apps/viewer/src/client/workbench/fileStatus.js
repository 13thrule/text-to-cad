const ACTIVE_EDIT_STATES = new Set(["submitted", "queued", "building"]);

function status(label, title, tone = "neutral", busy = false) {
  return { label, title, tone, busy };
}

function text(value) {
  return String(value || "").trim();
}

function failureStatus(error) {
  if (!error) {
    return null;
  }

  const record = typeof error === "object" ? error : {};
  const detail = text(
    typeof error === "string"
      ? error
      : record.message || record.title || record.summary || record.error
  );
  const hint = `${text(record.kind)} ${text(record.summary)} ${text(record.title)}`.toLowerCase();
  const isMetadata = /(annotation|metadata)/.test(hint);
  const isBuild = /(build|compile|generat)/.test(hint);
  const isWarning = record.severity === "warning";
  const label = isMetadata
    ? "Metadata issue"
    : isBuild
    ? (isWarning ? "Build issue" : "Build failed")
    : (isWarning ? "Load issue" : "Load failed");

  return status(label, detail || (isMetadata
    ? "Some file metadata is unavailable."
    : isBuild
      ? "The file could not be built."
      : "The file could not be loaded."), isWarning ? "warning" : "error");
}

function activityStatus(activity) {
  if (!activity?.loading) {
    return null;
  }

  const activityLabel = text(activity.label);
  const hint = `${text(activity.kind)} ${activityLabel}`.toLowerCase();
  // Camera-driven detail work is background viewport activity, not file I/O.
  if (/refin/.test(hint) && text(activity.kind).toLowerCase() !== "build") {
    return null;
  }
  const label = text(activity.kind).toLowerCase() === "build" || /(generat|compil)/.test(hint)
    ? "Building"
    : /sav/.test(hint)
      ? "Saving"
      : "Loading";
  return status(label, text(activity.title) || activityLabel || `${label} file.`, "info", true);
}

function previewIsCurrent(editingState) {
  const revision = Number(editingState?.revision) || 0;
  const previewRevision = Number(editingState?.preview?.revision) || 0;
  return Boolean(revision && previewRevision === revision);
}

/**
 * Resolve the single compact status shown beside the selected filename.
 *
 * `error` is the selected file's already-resolved build/load alert.
 * `activity` is the existing filename load activity record.
 * `editingState` is the state returned by useEditingPreview, while
 * `showingPreview` says whether that authored tree is the visible geometry.
 * `qualityStatus` is the public viewport quality status.
 */
export function resolveFileStatus({
  hasFile = false,
  error = null,
  activity = null,
  editingState = null,
  showingPreview = false,
  qualityStatus = null,
  hasGeometry = false
} = {}) {
  if (!hasFile) {
    return null;
  }

  const failure = failureStatus(error);
  if (failure) {
    return failure;
  }

  const editState = text(editingState?.state).toLowerCase();
  const editError = text(editingState?.error);
  const feedDisconnected = editState === "disconnected";

  if (editingState?.previewUnavailable) {
    return status(
      "Preview lost",
      editError || (editingState?.saved
        ? "The STEP file was saved, but its live preview is no longer available."
        : "The live preview is no longer available."),
      "warning"
    );
  }

  // The editing feed is optional input. A disconnected feed beside an ordinary
  // saved-file view must not turn the file into a permanent warning or wait.
  if (!feedDisconnected && (editState === "failed" || editError)) {
    const saveFailed = previewIsCurrent(editingState);
    return status(
      saveFailed ? "Save failed" : "Build failed",
      editError || (saveFailed
        ? "The live revision could not be saved to STEP."
        : "The live revision could not be built."),
      "error"
    );
  }

  if (qualityStatus?.state === "error") {
    return status(
      "Detail failed",
      text(qualityStatus.title) || "The visible model could not finish loading detail.",
      "error"
    );
  }

  if (ACTIVE_EDIT_STATES.has(editState)) {
    if (showingPreview && previewIsCurrent(editingState) && !editingState?.saved) {
      return status(
        "Saving",
        "The current live preview is visible while its STEP file is saved.",
        "info",
        true
      );
    }
    const queued = editState === "submitted" || editState === "queued";
    return status(
      queued ? "Queued" : "Building",
      queued
        ? "The next live revision is queued to build."
        : "The next live revision is building.",
      "info",
      true
    );
  }

  const loading = activityStatus(activity);
  if (loading) {
    return loading;
  }

  if (qualityStatus?.state === "limited") {
    return status(
      "Reduced detail",
      text(qualityStatus.title) || "Available memory limits the visible model detail.",
      "warning"
    );
  }

  if (qualityStatus?.state === "preview") {
    return status(
      "Preview",
      text(qualityStatus.title) || "Preview detail is visible while standard detail is prepared.",
      "info",
      true
    );
  }

  if (feedDisconnected && showingPreview) {
    return status(
      "Offline",
      editError || "The live preview remains visible, but its edit feed is disconnected.",
      "warning"
    );
  }

  if (editingState?.saved) {
    return status(
      "Saved",
      showingPreview
        ? "The live preview is visible and its STEP file was saved."
        : "The latest live revision is saved to STEP.",
      "success"
    );
  }

  if (showingPreview) {
    return status(
      "Preview",
      "Showing a live preview that has not been saved to STEP.",
      "info"
    );
  }

  if (hasGeometry) {
    return null;
  }

  return status("Loading", "Loading the selected file.", "info", true);
}
