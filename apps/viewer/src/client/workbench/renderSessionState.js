import {
  RENDER_STUDIO,
  SCENE_APPEARANCE,
  SCENE_QUALITY,
  normalizeRenderPayload,
  resolveSceneSettings
} from "cadgen-js/common/sceneSettings.js";
import {
  CAMERA_PROJECTION,
  normalizeCameraProjection,
  resolveCameraSnapshot
} from "cadgen-js/common/camera.js";
import { clonePerspectiveSnapshot } from "cadgen-js/lib/perspective.js";

export const DEFAULT_RENDER_PAYLOAD = Object.freeze({
  studio: RENDER_STUDIO.DEFAULT,
  appearance: SCENE_APPEARANCE.SYSTEM,
  quality: SCENE_QUALITY.HIGH
});

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function cloneValue(value) {
  if (Array.isArray(value)) {
    return value.map(cloneValue);
  }
  if (isPlainObject(value)) {
    return Object.fromEntries(Object.entries(value).map(([key, child]) => [key, cloneValue(child)]));
  }
  return value;
}

export function createRenderSessionState(value = null) {
  const source = isPlainObject(value) ? value : {};
  let payload;
  try {
    payload = normalizeRenderPayload(isPlainObject(source.payload) ? source.payload : DEFAULT_RENDER_PAYLOAD);
  } catch {
    payload = normalizeRenderPayload(DEFAULT_RENDER_PAYLOAD);
  }
  return {
    enabled: source.enabled === true,
    payload,
    cadCamera: renderCameraSnapshot(source.cadCamera),
    cadProjection: normalizeCameraProjection(
      source.cadProjection || source.cadCamera?.projection,
      CAMERA_PROJECTION.ORTHOGRAPHIC
    )
  };
}

export function renderSessionStateEqual(a, b) {
  return JSON.stringify(createRenderSessionState(a)) === JSON.stringify(createRenderSessionState(b));
}

export function renderCameraSeed(snapshot, { includeOrthographicFraming = true } = {}) {
  const camera = clonePerspectiveSnapshot(snapshot);
  if (!camera) {
    return null;
  }
  return {
    position: camera.position,
    target: camera.target,
    up: camera.up,
    ...(Object.prototype.hasOwnProperty.call(camera, "zoom") ? { zoom: camera.zoom } : {}),
    ...(includeOrthographicFraming && Object.prototype.hasOwnProperty.call(camera, "orthographicHalfHeight")
      ? { orthographicHalfHeight: camera.orthographicHalfHeight }
      : {})
  };
}

export function renderCameraSnapshot(camera) {
  const snapshot = clonePerspectiveSnapshot(camera);
  if (!snapshot) {
    return null;
  }
  return {
    position: snapshot.position,
    target: snapshot.target,
    up: snapshot.up,
    ...(Object.prototype.hasOwnProperty.call(snapshot, "zoom") ? { zoom: snapshot.zoom } : {}),
    ...(Object.prototype.hasOwnProperty.call(snapshot, "projection") ? { projection: snapshot.projection } : {}),
    ...(Object.prototype.hasOwnProperty.call(snapshot, "orthographicHalfHeight")
      ? { orthographicHalfHeight: snapshot.orthographicHalfHeight }
      : {})
  };
}

export function resolveRenderCameraSnapshot(camera, bounds = null, { sceneScale = "cad" } = {}) {
  return renderCameraSnapshot(resolveCameraSnapshot(camera, bounds, { sceneScale }));
}

export function setRenderSetting(payload, path, value) {
  const normalizedPayload = normalizeRenderPayload(payload || DEFAULT_RENDER_PAYLOAD);
  const normalizedPath = (Array.isArray(path) ? path : []).map((part) => String(part || "").trim()).filter(Boolean);
  if (!normalizedPath.length) {
    return normalizedPayload;
  }
  const settings = cloneValue(normalizedPayload.settings || {});
  let cursor = settings;
  for (let index = 0; index < normalizedPath.length - 1; index += 1) {
    const part = normalizedPath[index];
    cursor[part] = isPlainObject(cursor[part]) ? { ...cursor[part] } : {};
    cursor = cursor[part];
  }
  cursor[normalizedPath[normalizedPath.length - 1]] = cloneValue(value);
  return normalizeRenderPayload({ ...normalizedPayload, settings });
}

export function replaceRenderPreset(payload, patch = {}) {
  const normalizedPayload = normalizeRenderPayload(payload || DEFAULT_RENDER_PAYLOAD);
  const next = { ...normalizedPayload, ...patch };
  delete next.settings;
  return normalizeRenderPayload(next);
}

export function replaceRenderAppearance(payload, appearance) {
  return normalizeRenderPayload({
    ...normalizeRenderPayload(payload || DEFAULT_RENDER_PAYLOAD),
    appearance
  });
}

export function renderSessionForPayloadApply(session, payload, {
  activeCamera = null,
  activeProjection = null
} = {}) {
  const current = createRenderSessionState(session);
  if (current.enabled) {
    return createRenderSessionState({ ...current, payload });
  }
  const cadCamera = renderCameraSnapshot(activeCamera) || current.cadCamera;
  return createRenderSessionState({
    ...current,
    enabled: true,
    payload,
    cadCamera,
    cadProjection: cadCamera?.projection || activeProjection || current.cadProjection
  });
}

export function renderPayloadForCopy(session, {
  activeCamera = null,
  activeProjection = null
} = {}) {
  const current = createRenderSessionState(session);
  if (!current.enabled) {
    return current.payload;
  }
  const camera = renderCameraSnapshot(activeCamera);
  return createRenderSessionState({
    ...current,
    payload: camera
      ? {
          ...current.payload,
          camera: {
            ...renderCameraSeed(camera),
            projection: camera.projection || activeProjection
          }
        }
      : current.payload
  }).payload;
}

export function renderVisualPayload(payload) {
  const {
    camera: _camera,
    quality: _quality,
    ...visual
  } = normalizeRenderPayload(payload || DEFAULT_RENDER_PAYLOAD);
  return visual;
}

export function renderVisualSettingsKey(payload) {
  return JSON.stringify(renderVisualPayload(payload));
}

export function resolveRenderSessionQuality(session, options = {}) {
  const current = createRenderSessionState(session);
  return resolveSceneSettings({
    appearance: options.appearance,
    prefersDark: options.prefersDark === true,
    render: current.enabled ? { quality: current.payload.quality } : null
  }).quality;
}

export function parseRenderSettingsText(text, options = {}) {
  let parsed;
  try {
    parsed = JSON.parse(String(text || ""));
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`Invalid JSON: ${message}`);
  }
  if (!isPlainObject(parsed)) {
    throw new Error("Invalid render settings: expected a JSON object.");
  }
  try {
    return resolveSceneSettings({
      appearance: options.appearance,
      prefersDark: options.prefersDark === true,
      render: parsed
    }).render.payload;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`Invalid render settings: ${message}`);
  }
}
