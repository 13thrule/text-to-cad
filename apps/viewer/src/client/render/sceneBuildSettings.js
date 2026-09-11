export function sceneBuildStructuralKey({
  displayMode,
  applyDisplayModeEdgePolicy,
  sceneScaleMode,
  edgeSettings,
  recomputeNormals,
  silhouette,
  wireframeEdgeColor
} = {}) {
  return JSON.stringify({
    displayMode,
    applyDisplayModeEdgePolicy,
    scale: sceneScaleMode,
    edgeSettings,
    recomputeNormals,
    silhouette,
    wireframeEdgeColor
  });
}
