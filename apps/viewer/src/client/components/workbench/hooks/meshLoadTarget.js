export function meshLoadTargetsEntry({
  inProgress,
  targetFile,
  targetHash,
  entryFile,
  entryHash,
} = {}) {
  return inProgress === true
    && String(targetFile || "") === String(entryFile || "")
    && String(targetHash || "") === String(entryHash || "")
    && String(entryHash || "").length > 0;
}

export function shouldStartMeshLoad({
  selectedMeshMatches,
  isAssembly,
  interactionReady,
  hydrationFailed,
  ...target
} = {}) {
  if (meshLoadTargetsEntry(target)) return false;
  if (selectedMeshMatches && (!isAssembly || interactionReady || hydrationFailed)) return false;
  return true;
}

export function meshLoadErrorForViewer({
  fatalError = "",
  hydrationFailed = false,
  backgroundError = "",
} = {}) {
  if (fatalError) return String(fatalError);
  if (!hydrationFailed) return "";
  return String(backgroundError || "Assembly mesh loading stopped before every component was available.");
}
