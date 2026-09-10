import { LOD_CHORD_LEVELS } from "cadgen-js/lib/surf/lodPolicy.js";

export const LOD_SELECTOR_AND_GPU_ESTIMATE_MULTIPLIER = 2.5;
export const LOD_WORKER_TEMP_ESTIMATE_MULTIPLIER = 2;

export function estimateViewportLodMemory({ meshBytes, currentLevel, level }) {
  const currentBytes = Math.max(1, Number(meshBytes) || 0);
  const toleranceRatio = LOD_CHORD_LEVELS[currentLevel] / LOD_CHORD_LEVELS[level];
  const nextMeshBytes = Math.ceil(currentBytes * Math.max(0.2, toleranceRatio));
  return {
    currentBytes,
    nextMeshBytes,
    replacementBytes: nextMeshBytes * LOD_SELECTOR_AND_GPU_ESTIMATE_MULTIPLIER,
    workerTemporaryBytes: nextMeshBytes * LOD_WORKER_TEMP_ESTIMATE_MULTIPLIER,
  };
}
