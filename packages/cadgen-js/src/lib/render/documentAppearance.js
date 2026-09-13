// Closed document appearance values. These are metadata, never geometry keys.
export const DOCUMENT_PBR_FIELDS = Object.freeze([
  "roughness", "metalness", "clearcoat", "clearcoatRoughness", "opacity",
]);
const fields = new Set(["color", "pbr", "material", "face_colors", "physical_material"]);
const physicalFields = ["name", "description", "density", "density_name", "density_type"];
const unit = (value) => typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
const plain = (value) => value !== null && typeof value === "object"
  && [Object.prototype, null].includes(Object.getPrototypeOf(value));
function fail() { throw new Error("Invalid document scene: appearance"); }
function rgba(value) {
  if (!Array.isArray(value) || value.length !== 4 || !value.every(unit)) fail();
  return [...value];
}

export function documentAppearance(value) {
  if (!plain(value) || Object.keys(value).some((key) => !fields.has(key))) fail();
  const result = {};
  if (Object.hasOwn(value, "color")) result.color = rgba(value.color);
  if (Object.hasOwn(value, "pbr")) {
    if (!plain(value.pbr) || Object.keys(value.pbr).some((key) => !DOCUMENT_PBR_FIELDS.includes(key))
      || !Object.values(value.pbr).every(unit)) fail();
    result.pbr = Object.fromEntries(DOCUMENT_PBR_FIELDS.filter((key) => Object.hasOwn(value.pbr, key))
      .map((key) => [key, value.pbr[key]]));
  }
  if (Object.hasOwn(value, "material")) {
    if (typeof value.material !== "string" || value.material.length > 4096 || value.material.includes("\0")) fail();
    result.material = value.material;
  }
  if (Object.hasOwn(value, "face_colors")) {
    if (!Array.isArray(value.face_colors) || value.face_colors.length > 100_000) fail();
    let previous = -1;
    result.face_colors = value.face_colors.map((row) => {
      if (!Array.isArray(row) || row.length !== 2 || !Number.isSafeInteger(row[0])
        || row[0] <= previous || row[0] >= 100_000) fail();
      previous = row[0];
      return [row[0], rgba(row[1])];
    });
  }
  if (Object.hasOwn(value, "physical_material")) {
    const physical = value.physical_material;
    if (!plain(physical) || Object.keys(physical).length !== physicalFields.length
      || physicalFields.some((key) => !Object.hasOwn(physical, key))) fail();
    for (const key of physicalFields) {
      if (key === "density") {
        if (typeof physical[key] !== "number" || !Number.isFinite(physical[key])
          || physical[key] < 0 || physical[key] > 1e100) fail();
      } else if (typeof physical[key] !== "string" || physical[key].length > 4096 || physical[key].includes("\0")) fail();
    }
    result.physical_material = Object.fromEntries(physicalFields.map((key) => [key, physical[key]]));
  }
  return result;
}

export function mergeDocumentAppearance(parent = {}, own = {}) {
  // Face styles name topology in one prototype and never cascade to children.
  const { face_colors: ignored, ...inherited } = parent;
  const result = { ...inherited, ...own };
  if (parent.pbr || own.pbr) result.pbr = { ...parent.pbr, ...own.pbr };
  return documentAppearance(result);
}

export function documentAppearanceBytes(value) {
  // Conservative expanded JSON size, before any unbounded serialization.
  return 512 + (value.material?.length || 0) * 6 + (value.face_colors?.length || 0) * 192
    + physicalFields.reduce((sum, key) => sum + (typeof value.physical_material?.[key] === "string"
      ? value.physical_material[key].length * 6 : 64), 0);
}
