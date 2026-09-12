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
  LIGHT: "studio-light",
  DARK: "studio-dark"
});

export const RENDER_STUDIO_PRESETS = Object.freeze([
  Object.freeze({ id: RENDER_STUDIO.LIGHT, label: "Light studio" }),
  Object.freeze({ id: RENDER_STUDIO.DARK, label: "Dark studio" }),
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
    renderScale: 1,
    shadowMapSize: 2048,
    environmentMapSize: 256
  }),
  Object.freeze({
    id: SCENE_QUALITY.STANDARD,
    label: "Standard",
    targetPixelError: 1,
    minimumLodLevel: 1,
    idlePixelRatioCap: 2,
    snapshotLodLevel: 1,
    renderScale: 1,
    shadowMapSize: 2048,
    environmentMapSize: 256
  }),
  Object.freeze({
    id: SCENE_QUALITY.HIGH,
    label: "High",
    targetPixelError: 0.25,
    minimumLodLevel: 1,
    idlePixelRatioCap: 2,
    snapshotLodLevel: 3,
    renderScale: 2,
    shadowMapSize: 4096,
    environmentMapSize: 512
  })
]);

export const RENDER_PAYLOAD_KEYS = Object.freeze([
  "studio",
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
const STUDIO_MATERIAL_SETTINGS = Object.freeze({
  defaultColor: "#b9bdc3",
  fillColors: Object.freeze(["#b9bdc3"]),
  cycleColors: false,
  overrideSourceColors: false,
  tintMode: "blend",
  tintStrength: 0,
  saturation: 1,
  contrast: 1,
  brightness: 1,
  roughness: 0.36,
  metalness: 0.03,
  clearcoat: 0.2,
  clearcoatRoughness: 0.26,
  opacity: 1,
  envMapIntensity: 1.05,
  emissiveIntensity: 0
});

const STUDIO_ENVIRONMENT_SETTINGS = Object.freeze({
  enabled: true,
  presetId: "studio-softbox",
  intensity: 0.25,
  rotationY: -0.35,
  useAsBackground: false
});

const STUDIO_LIGHTING_SETTINGS = Object.freeze({
  toneMappingExposure: 0.8,
  directional: Object.freeze({
    enabled: true,
    color: "#fffaf2",
    intensity: 2.8,
    position: Object.freeze({ x: -190, y: 240, z: 300 })
  }),
  fill: Object.freeze({
    enabled: true,
    color: "#e8eef7",
    intensity: 0.08,
    position: Object.freeze({ x: 120, y: 80, z: 210 })
  }),
  rim: Object.freeze({
    enabled: true,
    color: "#f3f7ff",
    intensity: 0.3,
    position: Object.freeze({ x: -320, y: 260, z: 160 })
  }),
  spot: Object.freeze({
    enabled: false,
    color: "#ffffff",
    intensity: 0,
    angle: 0.7,
    distance: 0,
    position: Object.freeze({ x: 190, y: 210, z: 170 })
  }),
  point: Object.freeze({
    enabled: false,
    color: "#ffffff",
    intensity: 0,
    distance: 0,
    position: Object.freeze({ x: -240, y: 110, z: -210 })
  }),
  ambient: Object.freeze({
    enabled: true,
    color: "#ffffff",
    intensity: 0.02
  }),
  hemisphere: Object.freeze({
    enabled: true,
    skyColor: "#eef2f7",
    groundColor: "#5f5d59",
    intensity: 0.05
  })
});

const STUDIO_FLOOR_SETTINGS = Object.freeze({
  mode: "stage",
  enabled: true,
  followModel: true,
  roughness: 0.72,
  reflectivity: 0.1,
  shadowOpacity: 0.4,
  horizonBlend: 0.38
});

const RENDER_STUDIO_SETTINGS = Object.freeze({
  [RENDER_STUDIO.LIGHT]: Object.freeze({
    materials: STUDIO_MATERIAL_SETTINGS,
    background: Object.freeze({
      type: "radial",
      solidColor: "#e8e9e8",
      linearStart: "#f7f7f5",
      linearEnd: "#d8dadd",
      linearAngle: 135,
      radialInner: "#f7f7f5",
      radialOuter: "#d8dadd"
    }),
    floor: Object.freeze({ ...STUDIO_FLOOR_SETTINGS, color: "#d4d5d3" }),
    environment: STUDIO_ENVIRONMENT_SETTINGS,
    lighting: STUDIO_LIGHTING_SETTINGS
  }),
  [RENDER_STUDIO.DARK]: Object.freeze({
    materials: STUDIO_MATERIAL_SETTINGS,
    background: Object.freeze({
      type: "radial",
      solidColor: "#101113",
      linearStart: "#181a1d",
      linearEnd: "#070809",
      linearAngle: 135,
      radialInner: "#181a1d",
      radialOuter: "#070809"
    }),
    floor: Object.freeze({ ...STUDIO_FLOOR_SETTINGS, color: "#111214" }),
    environment: STUDIO_ENVIRONMENT_SETTINGS,
    lighting: STUDIO_LIGHTING_SETTINGS
  })
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

export function normalizeRenderStudioId(value) {
  const normalized = String(value ?? "").trim().toLowerCase();
  if (normalized === "default") {
    throw new Error("Render studio 'default' was removed; omit studio to follow appearance.");
  }
  if (normalized === "cinematic") {
    throw new Error("Render studio 'cinematic' was removed; use 'studio-dark'.");
  }
  if (normalized === "vibrant") {
    throw new Error("Render studio 'vibrant' was removed; use 'studio-light'.");
  }
  if (["colorful", "blue", "pink", "clay", "clay-sunrise", "terminal"].includes(normalized)) {
    throw new Error(
      `Render studio '${normalized}' was removed; use 'studio-light' or 'studio-dark' and customize render.settings.`
    );
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
  if (Object.prototype.hasOwnProperty.call(render, "appearance")) {
    throw new Error(
      "render.appearance was removed; omit studio to follow appearance, or use 'studio-light' or 'studio-dark' to pin it."
    );
  }
  validateKeys(render, RENDER_PAYLOAD_KEYS, "render");
  const quality = normalizeSceneQuality(render.quality, { fallback: SCENE_QUALITY.HIGH });
  const result = { quality };
  if (Object.prototype.hasOwnProperty.call(render, "studio")) {
    result.studio = normalizeRenderStudioId(render.studio);
  }
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
  if (studio != null) {
    return studio;
  }
  return appearance === SCENE_APPEARANCE.DARK
    ? RENDER_STUDIO.DARK
    : RENDER_STUDIO.LIGHT;
}

function studioSettings(studio, appearance) {
  const concreteStudio = resolvedStudioId(studio, appearance);
  const settings = cloneValue(RENDER_STUDIO_SETTINGS[concreteStudio]);
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
        // CAD is an inspection view with no reflection environment. Keep the
        // authored albedo and opacity, but use the workbench's matte PBR
        // channels so authored metals do not collapse to near-black.
        materialOverrides: explicitMaterialOverrides(settings),
        payload: null
      },
      quality: resolveSceneQuality(quality, { fallback: SCENE_QUALITY.INTERACTIVE }),
      camera: resolveCamera(DEFAULT_NORMAL_CAMERA, camera),
      display: resolvedDisplay
    };
  }

  const payload = normalizeRenderPayload(render);
  const effectiveStudio = resolvedStudioId(payload.studio, baseAppearance);
  const resolvedDisplay = resolveDisplay(
    DEFAULT_RENDER_DISPLAY_SETTINGS,
    payload.display,
    display
  );
  const presetSettings = publicRenderSettings(studioSettings(effectiveStudio, baseAppearance));
  const mergedSettings = publicRenderSettings(mergeSettings(presetSettings, payload.settings));
  const settings = applyPartColor(mergedSettings, resolvedDisplay.partColor);
  return {
    appearance: baseAppearance,
    render: {
      enabled: true,
      studio: effectiveStudio,
      settings,
      materialOverrides: explicitMaterialOverrides(payload.settings),
      payload
    },
    quality: resolveSceneQuality(quality, { fallback: payload.quality }),
    camera: resolveCamera(DEFAULT_RENDER_CAMERA, payload.camera, camera),
    display: resolvedDisplay
  };
}
