// Saved STEP annotations are document-bound data. Geometry remains identified
// by the immutable STEP tree; these helpers validate and compose annotations
// into a private descriptor owned by the current reader.

export const SOURCE_SIDECAR_SCHEMA_VERSION = 8;
export const SOURCE_APPEARANCE_CHANNELS = Object.freeze([
  "roughness",
  "metalness",
  "clearcoat",
  "clearcoatRoughness",
  "opacity"
]);

const SOURCE_APPEARANCE_CHANNEL_SET = new Set(SOURCE_APPEARANCE_CHANNELS);
function isObject(value) {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function sidecarName(url) {
  const text = String(url || "").split("#")[0];
  const query = /[?&]file=([^&]+)/.exec(text);
  const target = query ? decodeURIComponent(query[1]) : text.split("?")[0];
  return target.replace(/\\/g, "/").split("/").filter(Boolean).pop() || "sidecar";
}

function normalizedDocumentHash(value) {
  const digest = String(value || "").trim().toLowerCase();
  return /^[0-9a-f]{64}$/.test(digest) ? digest : "";
}

export function normalizeSourceAppearance(block) {
  if (block === undefined || block === null) {
    return null;
  }
  if (!isObject(block) || Object.keys(block).length !== 1 || !Object.hasOwn(block, "occurrences")) {
    throw new Error("appearance must contain only an occurrences object");
  }
  if (!isObject(block.occurrences)) {
    throw new Error("appearance.occurrences must be an object keyed by occurrence id");
  }
  const occurrenceEntries = [];
  for (const occurrenceId of Object.keys(block.occurrences).sort()) {
    if (!occurrenceId.trim()) {
      throw new Error("appearance occurrence ids must be nonempty strings");
    }
    const material = block.occurrences[occurrenceId];
    const keys = isObject(material) ? Object.keys(material) : [];
    if (!keys.length || keys.some((key) => !SOURCE_APPEARANCE_CHANNEL_SET.has(key))) {
      throw new Error(
        `appearance ${occurrenceId}: expected supported PBR channels: ${SOURCE_APPEARANCE_CHANNELS.join(", ")}`
      );
    }
    const normalizedMaterial = {};
    for (const key of keys.sort()) {
      const value = material[key];
      if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 1) {
        throw new Error(`appearance ${occurrenceId}.${key}: expected a finite number between 0 and 1`);
      }
      normalizedMaterial[key] = value;
    }
    occurrenceEntries.push([occurrenceId, normalizedMaterial]);
  }
  return occurrenceEntries.length ? { occurrences: Object.fromEntries(occurrenceEntries) } : null;
}

export function validateSourceSidecar(sidecar, { url = "", documentHash = "" } = {}) {
  if (!isObject(sidecar)) {
    throw new Error(`${sidecarName(url)}: unsupported sidecar schema none (expected ${SOURCE_SIDECAR_SCHEMA_VERSION})`);
  }
  if (sidecar.schemaVersion !== SOURCE_SIDECAR_SCHEMA_VERSION) {
    const name = sidecarName(url);
    const model = name.replace(/\.(step|stp)\.json$/i, "");
    throw new Error(
      `${name}: unsupported sidecar schema ${sidecar.schemaVersion ?? "none"} `
      + `(expected ${SOURCE_SIDECAR_SCHEMA_VERSION}) — rebuild the model `
      + `(python ${model}.py) or re-annotate the document (cadgen step build)`
    );
  }
  const expected = normalizedDocumentHash(documentHash);
  if (!expected) {
    throw new Error(`${sidecarName(url)}: saved sidecar load requires the STEP documentHash`);
  }
  const found = normalizedDocumentHash(sidecar.documentHash);
  if (found !== expected) {
    const name = sidecarName(url);
    const model = name.replace(/\.(step|stp)\.json$/i, "");
    throw new Error(
      `${name}: documentHash ${found || "none"} does not match STEP sha256 ${expected} `
      + `— rebuild the model (python ${model}.py) or re-annotate the document (cadgen step build)`
    );
  }
  return {
    ...sidecar,
    ...(Object.hasOwn(sidecar, "appearance")
      ? { appearance: normalizeSourceAppearance(sidecar.appearance) }
      : {})
  };
}

export async function loadSourceSidecar(sidecarUrl, { documentHash = "" } = {}) {
  const url = String(sidecarUrl || "").trim();
  if (!url) {
    return null;
  }
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load model sidecar: HTTP ${response.status}`);
  }
  return validateSourceSidecar(await response.json(), { url, documentHash });
}

export function applySourceAppearance(descriptor, block) {
  if (!isObject(descriptor)) {
    throw new Error("appearance requires an assembly package descriptor");
  }
  const appearance = normalizeSourceAppearance(block);
  if (!appearance) {
    return descriptor;
  }
  const sourceOccurrences = Array.isArray(descriptor.occurrences) ? descriptor.occurrences : [];
  const byId = new Map(sourceOccurrences.map((occurrence) => [String(occurrence?.id || ""), occurrence]));
  const replacements = new Map();
  for (const [occurrenceId, material] of Object.entries(appearance.occurrences)) {
    const target = byId.get(occurrenceId);
    if (!target || !String(target.component || "").trim()) {
      throw new Error(`appearance targets missing document occurrence ${occurrenceId}`);
    }
    replacements.set(occurrenceId, { ...target, material: { ...material } });
  }
  return {
    ...descriptor,
    occurrences: sourceOccurrences.map((occurrence) => (
      replacements.get(String(occurrence?.id || "")) || occurrence
    ))
  };
}
