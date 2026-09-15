import { VIEWER_PICK_MODE } from "cadgen-js/lib/viewer/constants.js";

export function viewerSelectorRuntimeForRenderPane({
  renderMode = false,
  hasTopology = false,
  retainingPreviousStepMesh = false,
  selectorRuntime = null
} = {}) {
  // Animation evaluates occurrence labels and mesh data. Inspection selectors
  // would only allocate invisible picking geometry in the photographic scene.
  return !renderMode && hasTopology && !retainingPreviousStepMesh ? selectorRuntime : null;
}

// The part selection the scene may highlight. Render is a photographic view:
// the Inspect selection effect tints the selected surface and draws a dithered
// occlusion ghost through everything in front of it, which would repaint the
// very material the Materials tab just applied. The Materials tab's Parts list
// carries the selection instead, so Render hands the scene no selected parts.
export function viewerSelectedPartIdsForRenderPane({
  renderMode = false,
  hasParts = false,
  selectedPartIds = []
} = {}) {
  return !renderMode && hasParts && Array.isArray(selectedPartIds) ? selectedPartIds : [];
}

// Callers decide whether picking is enabled (parts, topology, or Measure).
// This helper stays format-agnostic.
export function viewerPickModeForRenderPane({
  panToolActive = false,
  topologySelectionPending = false,
  topologySelectionUnavailable = false,
  topologySelectionDeferred = false,
  topologyPickingActive = false,
  viewerMode = "",
  assemblyPickingActive = false,
  focusedPartIds = "",
  measureMode = false
} = {}) {
  // While panning, a drag is a camera move — picking on release would select
  // whatever the drag happened to finish over.
  if (panToolActive) {
    return VIEWER_PICK_MODE.NONE;
  }
  if (topologySelectionPending || topologySelectionUnavailable || topologySelectionDeferred) {
    return VIEWER_PICK_MODE.NONE;
  }
  // Measure outranks both part and topology selection, and needs neither. The
  // endpoint always comes from the ray hit on the visible mesh; loaded topology
  // only refines that hit into a snap. An assembly with nothing expanded still
  // measures surface to surface across its parts.
  if (measureMode) {
    return VIEWER_PICK_MODE.MEASURE;
  }
  if (
    viewerMode === "assembly" &&
    !topologyPickingActive &&
    (
      assemblyPickingActive ||
      !String(focusedPartIds || "").trim()
    )
  ) {
    return VIEWER_PICK_MODE.ASSEMBLY;
  }
  return VIEWER_PICK_MODE.AUTO;
}
