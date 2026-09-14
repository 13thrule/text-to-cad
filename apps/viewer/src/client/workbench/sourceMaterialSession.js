import {
  resolveSourceAppearance,
  SOURCE_MATERIAL_DEFAULTS
} from "cadgen-js/common/sourceSidecar.js";

const EMPTY_OVERLAY = Object.freeze({ materials: Object.freeze({}), assignments: Object.freeze({}) });

function normalizedId(value) {
  return String(value || "").trim();
}

function sessionOverlay(value) {
  return value && typeof value === "object"
    ? {
        materials: value.materials && typeof value.materials === "object" ? value.materials : {},
        assignments: value.assignments && typeof value.assignments === "object" ? value.assignments : {}
      }
    : EMPTY_OVERLAY;
}

export function sourceMaterialOverlayIsEmpty(value) {
  const overlay = sessionOverlay(value);
  return !Object.keys(overlay.materials).length && !Object.keys(overlay.assignments).length;
}

export function sourceAppearanceHasMaterials(appearance) {
  const resolved = resolveSourceAppearance(appearance);
  return Boolean(resolved && Object.keys(resolved.materials || {}).length);
}

export function effectiveSourceAppearance(appearance, overlay) {
  return resolveSourceAppearance(appearance, sessionOverlay(overlay));
}

export function sourceMaterialParts(meshData) {
  return (Array.isArray(meshData?.parts) ? meshData.parts : []).map((part) => ({
    id: normalizedId(part?.occurrenceId || part?.id),
    label: String(part?.label || part?.name || part?.occurrenceId || part?.id || "Part").trim() || "Part",
    color: String(part?.sourceColor || "").trim()
  })).filter((part) => part.id);
}

export function sourceMaterialTargets(meshData) {
  const parts = sourceMaterialParts(meshData);
  const partById = new Map(parts.map((part) => [part.id, part]));
  const targets = [];
  const visit = (node, depth = 0) => {
    const children = Array.isArray(node?.children) ? node.children : [];
    const nodeId = normalizedId(node?.occurrenceId || node?.id);
    if (!children.length) {
      const part = partById.get(nodeId);
      return part ? [part.id] : [];
    }
    const occurrenceIds = [...new Set(children.flatMap((child) => visit(child, depth + 1)))];
    if (occurrenceIds.length > 1) {
      targets.push({
        id: `group:${nodeId || targets.length}`,
        label: String(node?.displayName || node?.label || node?.name || "Group").trim() || "Group",
        occurrenceIds,
        depth: Math.max(depth - 1, 0),
        group: true
      });
    }
    return occurrenceIds;
  };
  if (meshData?.assemblyRoot) visit(meshData.assemblyRoot);
  for (const part of parts) {
    targets.push({ ...part, occurrenceIds: [part.id], depth: 0, group: false });
  }
  return targets;
}

export function sourceMaterialUsage(appearance, overlay, parts) {
  const effective = effectiveSourceAppearance(appearance, overlay);
  const counts = Object.fromEntries(Object.keys(effective?.materials || {}).map((id) => [id, 0]));
  for (const part of Array.isArray(parts) ? parts : []) {
    const materialId = normalizedId(effective?.assignments?.[normalizedId(part?.id)]);
    if (materialId && Object.hasOwn(counts, materialId)) {
      counts[materialId] += 1;
    }
  }
  return counts;
}

export function sourceMaterialFallbackColor(effectiveAppearance, materialId, parts, neutral = "#b8b8b8") {
  const id = normalizedId(materialId);
  const assigned = (Array.isArray(parts) ? parts : []).filter((part) => (
    normalizedId(effectiveAppearance?.assignments?.[normalizedId(part?.id)]) === id
  ));
  if (!assigned.length) return neutral;
  const colors = assigned.map((part) => {
    const color = String(part?.color || "").trim().toLowerCase();
    return /^#[0-9a-f]{6}$/.test(color) ? color : "";
  });
  if (colors.some((color) => !color)) return neutral;
  return colors.every((color) => color === colors[0]) ? colors[0] : neutral;
}

export function patchSourceMaterialOverlay(overlay, materialId, patch) {
  const current = sessionOverlay(overlay);
  const id = normalizedId(materialId);
  if (!id) return current;
  return {
    materials: {
      ...current.materials,
      [id]: { ...(current.materials[id] || {}), ...(patch || {}) }
    },
    assignments: { ...current.assignments }
  };
}

export function assignSourceMaterialOverlay(overlay, occurrenceIds, materialId) {
  const current = sessionOverlay(overlay);
  const id = normalizedId(materialId);
  const assignments = { ...current.assignments };
  for (const occurrenceId of Array.isArray(occurrenceIds) ? occurrenceIds : []) {
    const normalizedOccurrenceId = normalizedId(occurrenceId);
    if (normalizedOccurrenceId && id) assignments[normalizedOccurrenceId] = id;
  }
  return { materials: { ...current.materials }, assignments };
}

export function nextSourceMaterialCopyId(appearance, overlay, sourceId) {
  const prefix = `${normalizedId(sourceId) || "material"}-copy`;
  const effective = effectiveSourceAppearance(appearance, overlay);
  const ids = new Set(Object.keys(effective?.materials || {}));
  let index = 1;
  while (ids.has(`${prefix}-${index}`)) index += 1;
  return `${prefix}-${index}`;
}

export function duplicateSourceMaterialOverlay(appearance, overlay, sourceId, occurrenceIds) {
  const effective = effectiveSourceAppearance(appearance, overlay);
  const source = effective?.materials?.[normalizedId(sourceId)];
  if (!source) return sessionOverlay(overlay);
  const materialId = nextSourceMaterialCopyId(appearance, overlay, sourceId);
  const name = `${String(source.name || "Material").trim() || "Material"} copy`;
  const next = patchSourceMaterialOverlay(overlay, materialId, { ...source, name });
  return {
    overlay: assignSourceMaterialOverlay(next, occurrenceIds, materialId),
    materialId
  };
}

export function sourceMaterialEditorValue(material, key, fallbackColor = "#b8b8b8") {
  if (key === "baseColor") {
    return String(material?.baseColor || fallbackColor || "#b8b8b8").toLowerCase();
  }
  const value = Number(material?.[key]);
  if (Number.isFinite(value)) return Math.min(Math.max(value, 0), 1);
  return SOURCE_MATERIAL_DEFAULTS[key];
}

export function applySourceMaterialOverlayToMeshData(meshData, overlay) {
  if (!meshData?.appearance || !sourceAppearanceHasMaterials(meshData.appearance)) return meshData;
  const effective = effectiveSourceAppearance(meshData.appearance, overlay);
  if (!effective) return meshData;
  const parts = (Array.isArray(meshData.parts) ? meshData.parts : []).map((part) => {
    const occurrenceId = normalizedId(part?.occurrenceId || part?.id);
    const materialId = normalizedId(effective.assignments?.[occurrenceId]);
    const material = effective.materials?.[materialId];
    if (!material) return part;
    const channels = {
      roughness: sourceMaterialEditorValue(material, "roughness"),
      metalness: sourceMaterialEditorValue(material, "metalness"),
      clearcoat: sourceMaterialEditorValue(material, "clearcoat"),
      clearcoatRoughness: sourceMaterialEditorValue(material, "clearcoatRoughness"),
      opacity: sourceMaterialEditorValue(material, "opacity")
    };
    const sourceOpacity = Number.isFinite(Number(part?.sourceOpacity))
      ? Math.min(Math.max(Number(part.sourceOpacity), 0), 1)
      : 1;
    return {
      ...part,
      materialId,
      materialName: material.name,
      color: material.baseColor || part.sourceColor || null,
      material: channels,
      opacity: sourceOpacity * channels.opacity
    };
  });
  return { ...meshData, appearance: effective, parts };
}
