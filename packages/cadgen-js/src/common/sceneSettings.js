import {
  CAMERA_PROJECTION,
  normalizeCameraSpec
} from "./camera.js";
import {
  CAD_DISPLAY_MODE,
  CAD_PART_COLOR_MODE,
  DEFAULT_DISPLAY_SETTINGS,
  DISABLED_DISPLAY_EDGE_SETTINGS,
  DISABLED_DISPLAY_GUIDE_SETTINGS,
  normalizePartColorSettings,
  normalizeDisplaySettings,
  validateDisplaySettings
} from "./displaySettings.js";
import {
  cloneThemePresetSettings,
  ENVIRONMENT_PRESETS,
  normalizeThemeSettings
} from "./themeSettings.js";

export const SCENE_APPEARANCE = Object.freeze({
  SYSTEM: "system",
  LIGHT: "light",
  DARK: "dark"
});

export const RENDER_STUDIO = Object.freeze({
  DEFAULT: "default",
  LIGHT: "studio-light",
  DARK: "studio-dark",
  BLUE: "blue",
  PINK: "pink",
  CLAY_SUNRISE: "clay-sunrise",
  TERMINAL: "terminal"
});

export const RENDER_STUDIO_PRESETS = Object.freeze([
  Object.freeze({ id: RENDER_STUDIO.DEFAULT, label: "Studio" }),
  Object.freeze({ id: RENDER_STUDIO.LIGHT, label: "Bright studio" }),
  Object.freeze({ id: RENDER_STUDIO.DARK, label: "Dark studio" }),
  Object.freeze({ id: RENDER_STUDIO.BLUE, label: "Blue" }),
  Object.freeze({ id: RENDER_STUDIO.PINK, label: "Magenta" }),
  Object.freeze({ id: RENDER_STUDIO.CLAY_SUNRISE, label: "Clay" }),
  Object.freeze({ id: RENDER_STUDIO.TERMINAL, label: "Terminal" })
]);

export const SCENE_QUALITY = Object.freeze({
  INTERACTIVE: "interactive",
  STANDARD: "standard",
  HIGH: "high"
});

export const SCENE_QUALITY_PRESETS = Object.freeze([
  Object.freeze({
    id: SCENE_QUALITY.INTERACTIVE,
    label: "Interactive",
    targetPixelError: 1.25,
    minimumLodLevel: 1,
    idlePixelRatioCap: 1.5,
    snapshotLodLevel: 1,
    renderScale: 1
  }),
  Object.freeze({
    id: SCENE_QUALITY.STANDARD,
    label: "Standard",
    targetPixelError: 1,
    minimumLodLevel: 1,
    idlePixelRatioCap: 2,
    snapshotLodLevel: 1,
    renderScale: 1
  }),
  Object.freeze({
    id: SCENE_QUALITY.HIGH,
    label: "High",
    targetPixelError: 0.5,
    minimumLodLevel: 1,
    idlePixelRatioCap: 2,
    snapshotLodLevel: 2,
    renderScale: 2
  })
]);

export const RENDER_PAYLOAD_KEYS = Object.freeze([
  "studio",
  "appearance",
  "quality",
  "settings",
  "camera",
  "display"
]);

export const RENDER_SETTINGS_KEYS = Object.freeze([
  "materials",
  "background",
  "floor",
  "environment",
  "lighting"
]);

const RENDER_STUDIO_IDS = new Set(RENDER_STUDIO_PRESETS.map((preset) => preset.id));
const SCENE_QUALITY_BY_ID = new Map(SCENE_QUALITY_PRESETS.map((preset) => [preset.id, preset]));
const RENDER_STUDIO_THEME_IDS = Object.freeze({
  [RENDER_STUDIO.LIGHT]: "vibrant",
  [RENDER_STUDIO.DARK]: "cinematic",
  [RENDER_STUDIO.BLUE]: "blue",
  [RENDER_STUDIO.PINK]: "pink",
  [RENDER_STUDIO.CLAY_SUNRISE]: "clay-sunrise",
  [RENDER_STUDIO.TERMINAL]: "terminal"
});

const STUDIO_SETTING_BLOCK_KEYS = Object.freeze({
  materials: Object.freeze([
    "defaultColor",
    "fillColors",
    "cycleColors",
    "overrideSourceColors",
    "tintMode",
    "tintStrength",
    "saturation",
    "contrast",
    "brightness",
    "roughness",
    "metalness",
    "clearcoat",
    "clearcoatRoughness",
    "opacity",
    "envMapIntensity",
    "emissiveIntensity"
  ]),
  background: Object.freeze([
    "type",
    "solidColor",
    "linearStart",
    "linearEnd",
    "linearAngle",
    "radialInner",
    "radialOuter"
  ]),
  floor: Object.freeze([
    "mode",
    "enabled",
    "followModel",
    "color",
    "roughness",
    "reflectivity",
    "shadowOpacity",
    "horizonBlend"
  ]),
  environment: Object.freeze([
    "enabled",
    "presetId",
    "intensity",
    "rotationY",
    "useAsBackground"
  ]),
  lighting: Object.freeze([
    "toneMappingExposure",
    "directional",
    "fill",
    "rim",
    "spot",
    "point",
    "ambient",
    "hemisphere"
  ])
});

const LIGHT_KEYS = Object.freeze({
  directional: Object.freeze(["enabled", "color", "intensity", "position"]),
  fill: Object.freeze(["enabled", "color", "intensity", "position"]),
  rim: Object.freeze(["enabled", "color", "intensity", "position"]),
  spot: Object.freeze(["enabled", "color", "intensity", "angle", "distance", "position"]),
  point: Object.freeze(["enabled", "color", "intensity", "distance", "position"]),
  ambient: Object.freeze(["enabled", "color", "intensity"]),
  hemisphere: Object.freeze(["enabled", "skyColor", "groundColor", "intensity"])
});

const EXPLICIT_PBR_MATERIAL_KEYS = Object.freeze([
  "roughness",
  "metalness",
  "clearcoat",
  "clearcoatRoughness"
]);
const HEX_COLOR_PATTERN = /^#(?:[0-9a-fA-F]{3}){1,2}$/;
const ENVIRONMENT_PRESET_IDS = new Set(ENVIRONMENT_PRESETS.map((preset) => preset.id));

const DEFAULT_NORMAL_CAMERA = Object.freeze({
  preset: "iso",
  projection: CAMERA_PROJECTION.ORTHOGRAPHIC
});

const DEFAULT_RENDER_CAMERA = Object.freeze({
  preset: "iso",
  projection: CAMERA_PROJECTION.PERSPECTIVE
});

export const DEFAULT_RENDER_DISPLAY_SETTINGS = Object.freeze({
  ...DEFAULT_DISPLAY_SETTINGS,
  mode: CAD_DISPLAY_MODE.SHADED,
  edges: DISABLED_DISPLAY_EDGE_SETTINGS,
  guides: DISABLED_DISPLAY_GUIDE_SETTINGS
});

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function cloneValue(value) {
  if (Array.isArray(value)) {
    return value.map(cloneValue);
  }
  if (isPlainObject(value)) {
    return Object.fromEntries(Object.entries(value).map(([key, entry]) => [key, cloneValue(entry)]));
  }
  return value;
}

function mergeSettings(base, override) {
  if (!isPlainObject(override)) {
    return cloneValue(base);
  }
  const result = cloneValue(base);
  for (const [key, value] of Object.entries(override)) {
    result[key] = isPlainObject(value) && isPlainObject(result[key])
      ? mergeSettings(result[key], value)
      : cloneValue(value);
  }
  return result;
}

function validateKeys(source, allowed, fieldName) {
  const unknown = Object.keys(source).filter((key) => !allowed.includes(key));
  if (unknown.length) {
    throw new Error(`Unsupported ${fieldName} fields: ${unknown.join(", ")}`);
  }
}

function validatePosition(position, fieldName) {
  if (position == null) {
    return;
  }
  if (!isPlainObject(position)) {
    throw new Error(`${fieldName} must be an object`);
  }
  validateKeys(position, ["x", "y", "z"], fieldName);
  for (const axis of ["x", "y", "z"]) {
    if (Object.prototype.hasOwnProperty.call(position, axis)) {
      validateNumber(position[axis], `${fieldName}.${axis}`, -5000, 5000);
    }
  }
}

function validateNumber(value, fieldName, min = -Infinity, max = Infinity) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < min || value > max) {
    throw new Error(`${fieldName} must be a finite number between ${min} and ${max}`);
  }
}

function validateBoolean(value, fieldName) {
  if (typeof value !== "boolean") {
    throw new Error(`${fieldName} must be a boolean`);
  }
}

function validateColor(value, fieldName) {
  if (typeof value !== "string" || !HEX_COLOR_PATTERN.test(value.trim())) {
    throw new Error(`${fieldName} must be a hex color`);
  }
}

function validateOptionalFields(source, keys, validator, prefix) {
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(source, key)) {
      validator(source[key], `${prefix}.${key}`);
    }
  }
}

function validateRenderSettings(settings) {
  if (!isPlainObject(settings)) {
    throw new Error("render.settings must be an object");
  }
  validateKeys(settings, RENDER_SETTINGS_KEYS, "render.settings");
  for (const [blockName, value] of Object.entries(settings)) {
    if (!isPlainObject(value)) {
      throw new Error(`render.settings.${blockName} must be an object`);
    }
    validateKeys(value, STUDIO_SETTING_BLOCK_KEYS[blockName], `render.settings.${blockName}`);
  }
  const floorMode = settings.floor?.mode;
  if (floorMode != null && !["stage", "none"].includes(String(floorMode).trim().toLowerCase())) {
    throw new Error("render.settings.floor.mode must be 'stage' or 'none'; use display.guides for grid and axis");
  }
  const materials = settings.materials || {};
  validateOptionalFields(materials, ["defaultColor"], validateColor, "render.settings.materials");
  if (Object.prototype.hasOwnProperty.call(materials, "fillColors")) {
    if (!Array.isArray(materials.fillColors) || materials.fillColors.length < 1 || materials.fillColors.length > 50) {
      throw new Error("render.settings.materials.fillColors must contain 1 to 50 hex colors");
    }
    materials.fillColors.forEach((color, index) => validateColor(color, `render.settings.materials.fillColors[${index}]`));
  }
  validateOptionalFields(
    materials,
    ["cycleColors", "overrideSourceColors"],
    validateBoolean,
    "render.settings.materials"
  );
  if (Object.prototype.hasOwnProperty.call(materials, "tintMode") && !["multiply", "blend"].includes(materials.tintMode)) {
    throw new Error("render.settings.materials.tintMode must be 'multiply' or 'blend'");
  }
  const materialRanges = {
    tintStrength: [0, 1],
    saturation: [0, 2.5],
    contrast: [0, 2.5],
    brightness: [0, 2],
    roughness: [0, 1],
    metalness: [0, 1],
    clearcoat: [0, 1],
    clearcoatRoughness: [0, 1],
    opacity: [0, 1],
    envMapIntensity: [0, 4],
    emissiveIntensity: [0, 2]
  };
  for (const [key, [min, max]] of Object.entries(materialRanges)) {
    if (Object.prototype.hasOwnProperty.call(materials, key)) {
      validateNumber(materials[key], `render.settings.materials.${key}`, min, max);
    }
  }

  const background = settings.background || {};
  if (Object.prototype.hasOwnProperty.call(background, "type") && !["solid", "linear", "radial", "transparent"].includes(background.type)) {
    throw new Error("render.settings.background.type must be 'solid', 'linear', 'radial', or 'transparent'");
  }
  validateOptionalFields(
    background,
    ["solidColor", "linearStart", "linearEnd", "radialInner", "radialOuter"],
    validateColor,
    "render.settings.background"
  );
  if (Object.prototype.hasOwnProperty.call(background, "linearAngle")) {
    validateNumber(background.linearAngle, "render.settings.background.linearAngle", -360, 360);
  }

  const floor = settings.floor || {};
  validateOptionalFields(floor, ["enabled", "followModel"], validateBoolean, "render.settings.floor");
  validateOptionalFields(floor, ["color"], validateColor, "render.settings.floor");
  validateOptionalFields(
    floor,
    ["roughness", "reflectivity", "shadowOpacity", "horizonBlend"],
    (value, fieldName) => validateNumber(value, fieldName, 0, 1),
    "render.settings.floor"
  );

  const environment = settings.environment || {};
  validateOptionalFields(environment, ["enabled", "useAsBackground"], validateBoolean, "render.settings.environment");
  if (Object.prototype.hasOwnProperty.call(environment, "presetId") && !ENVIRONMENT_PRESET_IDS.has(environment.presetId)) {
    throw new Error(`Unknown render.settings.environment.presetId '${environment.presetId}'`);
  }
  if (Object.prototype.hasOwnProperty.call(environment, "intensity")) {
    validateNumber(environment.intensity, "render.settings.environment.intensity", 0, 4);
  }
  if (Object.prototype.hasOwnProperty.call(environment, "rotationY")) {
    validateNumber(environment.rotationY, "render.settings.environment.rotationY", -Math.PI * 2, Math.PI * 2);
  }

  const lighting = settings.lighting || {};
  if (Object.prototype.hasOwnProperty.call(lighting, "toneMappingExposure")) {
    validateNumber(lighting.toneMappingExposure, "render.settings.lighting.toneMappingExposure", 0.05, 6);
  }
  for (const [lightName, value] of Object.entries(lighting)) {
    if (lightName === "toneMappingExposure") {
      continue;
    }
    if (!isPlainObject(value)) {
      throw new Error(`render.settings.lighting.${lightName} must be an object`);
    }
    validateKeys(value, LIGHT_KEYS[lightName], `render.settings.lighting.${lightName}`);
    validateOptionalFields(value, ["enabled"], validateBoolean, `render.settings.lighting.${lightName}`);
    validateOptionalFields(value, ["color"], validateColor, `render.settings.lighting.${lightName}`);
    validateOptionalFields(value, ["skyColor", "groundColor"], validateColor, `render.settings.lighting.${lightName}`);
    if (Object.prototype.hasOwnProperty.call(value, "intensity")) {
      validateNumber(value.intensity, `render.settings.lighting.${lightName}.intensity`, 0, 20);
    }
    if (Object.prototype.hasOwnProperty.call(value, "distance")) {
      validateNumber(value.distance, `render.settings.lighting.${lightName}.distance`, 0, 5000);
    }
    if (Object.prototype.hasOwnProperty.call(value, "angle")) {
      validateNumber(value.angle, `render.settings.lighting.${lightName}.angle`, 0.01, Math.PI / 2);
    }
    validatePosition(value.position, `render.settings.lighting.${lightName}.position`);
  }
}

export function normalizeSceneAppearance(value = SCENE_APPEARANCE.SYSTEM, {
  prefersDark = false
} = {}) {
  const normalized = String(value ?? SCENE_APPEARANCE.SYSTEM).trim().toLowerCase();
  if (normalized === SCENE_APPEARANCE.SYSTEM) {
    return prefersDark ? SCENE_APPEARANCE.DARK : SCENE_APPEARANCE.LIGHT;
  }
  if (normalized === SCENE_APPEARANCE.LIGHT || normalized === SCENE_APPEARANCE.DARK) {
    return normalized;
  }
  throw new Error("appearance must be 'system', 'light', or 'dark'");
}

export function normalizeRenderStudioId(value = RENDER_STUDIO.DEFAULT) {
  const normalized = String(value ?? RENDER_STUDIO.DEFAULT).trim().toLowerCase();
  if (normalized === "cinematic") {
    throw new Error("Render studio 'cinematic' was removed; use 'studio-dark'.");
  }
  if (normalized === "vibrant") {
    throw new Error("Render studio 'vibrant' was removed; use 'studio-light'.");
  }
  if (!RENDER_STUDIO_IDS.has(normalized)) {
    throw new Error(`Unknown render studio '${value}'. Expected one of: ${[...RENDER_STUDIO_IDS].join(", ")}`);
  }
  return normalized;
}

export function normalizeSceneQuality(value, {
  fallback = SCENE_QUALITY.STANDARD
} = {}) {
  const normalized = String(value ?? fallback).trim().toLowerCase();
  if (!SCENE_QUALITY_BY_ID.has(normalized)) {
    throw new Error(`Unknown scene quality '${value}'. Expected one of: ${[...SCENE_QUALITY_BY_ID.keys()].join(", ")}`);
  }
  return normalized;
}

export function resolveSceneQuality(value, options = {}) {
  return { ...SCENE_QUALITY_BY_ID.get(normalizeSceneQuality(value, options)) };
}

export function normalizeRenderPayload(render) {
  if (!isPlainObject(render)) {
    throw new Error("render must be an object");
  }
  validateKeys(render, RENDER_PAYLOAD_KEYS, "render");
  const studio = normalizeRenderStudioId(render.studio);
  const appearance = render.appearance == null
    ? SCENE_APPEARANCE.SYSTEM
    : String(render.appearance).trim().toLowerCase();
  normalizeSceneAppearance(appearance);
  const quality = normalizeSceneQuality(render.quality, { fallback: SCENE_QUALITY.HIGH });
  const result = { studio, appearance, quality };
  if (Object.prototype.hasOwnProperty.call(render, "settings")) {
    validateRenderSettings(render.settings);
    result.settings = cloneValue(render.settings);
  }
  if (Object.prototype.hasOwnProperty.call(render, "camera")) {
    normalizeCameraSpec(render.camera, {
      strict: true,
      defaultProjection: CAMERA_PROJECTION.PERSPECTIVE
    });
    result.camera = cloneValue(render.camera);
  }
  if (Object.prototype.hasOwnProperty.call(render, "display")) {
    validateDisplaySettings(render.display);
    normalizeDisplaySettings(render.display, { fallback: DEFAULT_RENDER_DISPLAY_SETTINGS });
    result.display = cloneValue(render.display);
  }
  return result;
}

function resolvedStudioId(studio, appearance) {
  if (studio !== RENDER_STUDIO.DEFAULT) {
    return studio;
  }
  return appearance === SCENE_APPEARANCE.DARK
    ? RENDER_STUDIO.DARK
    : RENDER_STUDIO.LIGHT;
}

function studioSettings(studio, appearance) {
  const concreteStudio = resolvedStudioId(studio, appearance);
  const settings = cloneThemePresetSettings(RENDER_STUDIO_THEME_IDS[concreteStudio]);
  return normalizeThemeSettings(settings);
}

function normalSettings(appearance) {
  return normalizeThemeSettings(cloneThemePresetSettings(
    appearance === SCENE_APPEARANCE.DARK ? "workbench-dark" : "workbench-light"
  ));
}

function publicRenderSettings(settings) {
  const normalized = normalizeThemeSettings(settings);
  return {
    materials: cloneValue(normalized.materials),
    background: cloneValue(normalized.background),
    floor: cloneValue(normalized.floor),
    environment: cloneValue(normalized.environment),
    lighting: cloneValue(normalized.lighting)
  };
}

function cameraPatch(value) {
  if (value == null) {
    return null;
  }
  return typeof value === "string" ? { preset: value } : cloneValue(value);
}

function resolveCamera(base, ...overrides) {
  let merged = cloneValue(base);
  for (const override of overrides) {
    const patch = cameraPatch(override);
    if (patch) {
      // A higher-priority named view selects that view in full. Retaining a
      // lower-priority custom pose would make `{preset: "front"}` still show
      // the copied Render camera. A projection-only patch intentionally keeps
      // the pose so callers can switch lenses without losing framing.
      if (Object.prototype.hasOwnProperty.call(patch, "preset")) {
        for (const field of ["name", "position", "target", "direction", "up", "zoom", "orthographicHalfHeight"]) {
          delete merged[field];
        }
      } else if (
        Object.prototype.hasOwnProperty.call(patch, "direction") &&
        !Object.prototype.hasOwnProperty.call(patch, "position")
      ) {
        // A higher-priority direction is another complete orientation choice.
        // Drop a copied position that would otherwise make normalization infer
        // direction from position -> target and silently ignore this patch.
        // The target and up vector remain useful framing/roll inputs.
        for (const field of ["name", "preset", "position", "orthographicHalfHeight"]) {
          delete merged[field];
        }
      }
      merged = { ...merged, ...patch };
    }
  }
  const spec = normalizeCameraSpec(merged, {
    strict: true,
    defaultProjection: base.projection
  });
  const result = {
    preset: spec.preset,
    name: spec.name,
    projection: spec.projection,
    direction: [...spec.direction],
    up: [...spec.up],
    zoom: spec.zoom
  };
  if (spec.orthographicHalfHeight != null) {
    result.orthographicHalfHeight = spec.orthographicHalfHeight;
  }
  if (spec.position) {
    result.position = [...spec.position];
  }
  if (spec.target) {
    result.target = [...spec.target];
  }
  return result;
}

function resolveDisplay(base, ...overrides) {
  let resolved = normalizeDisplaySettings(base, { fallback: base });
  for (const override of overrides) {
    if (override != null) {
      validateDisplaySettings(override);
      resolved = normalizeDisplaySettings(override, { fallback: resolved });
    }
  }
  return resolved;
}

export function resolveDisplayMaterialSettings(materialSettings = {}, partColorSettings = null) {
  const partColor = normalizePartColorSettings(partColorSettings);
  if (partColor.mode === CAD_PART_COLOR_MODE.ORIGINAL) {
    return { ...materialSettings };
  }
  const materials = { ...materialSettings, overrideSourceColors: true };
  if (partColor.mode === CAD_PART_COLOR_MODE.SINGLE) {
    materials.defaultColor = partColor.color;
    materials.fillColors = [partColor.color];
    materials.cycleColors = false;
  } else {
    materials.defaultColor = partColor.colors[0] || partColor.color;
    materials.fillColors = [...partColor.colors];
    materials.cycleColors = true;
  }
  return materials;
}

function applyPartColor(settings, partColor) {
  return {
    ...settings,
    materials: resolveDisplayMaterialSettings(settings.materials, partColor)
  };
}

function explicitMaterialOverrides(settings = {}) {
  const materials = isPlainObject(settings.materials) ? settings.materials : {};
  return Object.fromEntries(EXPLICIT_PBR_MATERIAL_KEYS
    .filter((key) => Object.prototype.hasOwnProperty.call(materials, key))
    .map((key) => [key, Number(materials[key])]));
}

/**
 * Resolve shared viewer/snapshot scene policy without retaining app state.
 * Precedence is base CAD policy, Render defaults and embedded overrides, then
 * explicit top-level camera/display overrides.
 */
export function resolveSceneSettings({
  appearance = SCENE_APPEARANCE.SYSTEM,
  prefersDark = false,
  render = null,
  quality = null,
  camera = null,
  display = null
} = {}) {
  const baseAppearance = normalizeSceneAppearance(appearance, { prefersDark });
  if (render == null) {
    const resolvedDisplay = resolveDisplay(DEFAULT_DISPLAY_SETTINGS, display);
    const settings = applyPartColor(publicRenderSettings(normalSettings(baseAppearance)), resolvedDisplay.partColor);
    return {
      appearance: baseAppearance,
      render: {
        enabled: false,
        studio: null,
        settings,
        materialOverrides: {},
        payload: null
      },
      quality: resolveSceneQuality(quality, { fallback: SCENE_QUALITY.INTERACTIVE }),
      camera: resolveCamera(DEFAULT_NORMAL_CAMERA, camera),
      display: resolvedDisplay
    };
  }

  const payload = normalizeRenderPayload(render);
  const renderAppearance = normalizeSceneAppearance(payload.appearance, {
    prefersDark: baseAppearance === SCENE_APPEARANCE.DARK
  });
  const resolvedDisplay = resolveDisplay(
    DEFAULT_RENDER_DISPLAY_SETTINGS,
    payload.display,
    display
  );
  const presetSettings = publicRenderSettings(studioSettings(payload.studio, renderAppearance));
  const mergedSettings = publicRenderSettings(mergeSettings(presetSettings, payload.settings));
  const settings = applyPartColor(mergedSettings, resolvedDisplay.partColor);
  return {
    appearance: renderAppearance,
    render: {
      enabled: true,
      studio: payload.studio,
      settings,
      materialOverrides: explicitMaterialOverrides(payload.settings),
      payload
    },
    quality: resolveSceneQuality(quality, { fallback: payload.quality }),
    camera: resolveCamera(DEFAULT_RENDER_CAMERA, payload.camera, camera),
    display: resolvedDisplay
  };
}
