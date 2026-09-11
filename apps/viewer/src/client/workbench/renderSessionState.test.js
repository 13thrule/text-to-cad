import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_RENDER_PAYLOAD,
  createRenderSessionState,
  parseRenderSettingsText,
  renderCameraSeed,
  renderPayloadForCopy,
  renderSessionForPayloadApply,
  renderVisualSettingsKey,
  resolveRenderSessionQuality,
  resolveRenderCameraSnapshot,
  replaceRenderAppearance,
  replaceRenderPreset,
  setRenderSetting
} from "./renderSessionState.js";

test("render sessions default to an off, high-quality adaptive studio", () => {
  const state = createRenderSessionState();

  assert.equal(state.enabled, false);
  assert.deepEqual(state.payload, DEFAULT_RENDER_PAYLOAD);
  assert.equal(state.cadProjection, "orthographic");
  assert.equal(state.cadCamera, null);
});

test("render setting edits remain sparse and preserve quality", () => {
  const payload = setRenderSetting(DEFAULT_RENDER_PAYLOAD, ["materials", "roughness"], 0.23);

  assert.deepEqual(payload, {
    ...DEFAULT_RENDER_PAYLOAD,
    settings: { materials: { roughness: 0.23 } }
  });
});

test("changing studio clears authored studio settings but keeps camera and display", () => {
  const payload = replaceRenderPreset({
    ...DEFAULT_RENDER_PAYLOAD,
    settings: { materials: { metalness: 0.4 } },
    camera: { preset: "front" },
    display: { mode: "wireframe" }
  }, { studio: "studio-dark" });

  assert.equal(payload.studio, "studio-dark");
  assert.equal(payload.settings, undefined);
  assert.deepEqual(payload.camera, { preset: "front" });
  assert.deepEqual(payload.display, { mode: "wireframe" });
});

test("changing appearance preserves sparse custom settings", () => {
  const payload = replaceRenderAppearance({
    ...DEFAULT_RENDER_PAYLOAD,
    settings: { materials: { roughness: 0.27 }, lighting: { toneMappingExposure: 1.4 } },
    camera: { preset: "front" }
  }, "dark");

  assert.equal(payload.appearance, "dark");
  assert.equal(payload.settings.materials.roughness, 0.27);
  assert.equal(payload.settings.lighting.toneMappingExposure, 1.4);
  assert.deepEqual(payload.camera, { preset: "front" });
});

test("pasting while disabled captures the current CAD camera before enabling Render", () => {
  const activeCadCamera = {
    position: [12, 22, 32],
    target: [1, 2, 3],
    up: [0, 0, 1],
    zoom: 1.15,
    projection: "orthographic",
    orthographicHalfHeight: 24
  };
  const next = renderSessionForPayloadApply(createRenderSessionState({
    enabled: false,
    cadCamera: { position: [1, 1, 1], target: [0, 0, 0], up: [0, 0, 1] }
  }), {
    ...DEFAULT_RENDER_PAYLOAD,
    camera: { preset: "front" }
  }, {
    activeCamera: activeCadCamera,
    activeProjection: "orthographic"
  });

  assert.equal(next.enabled, true);
  assert.deepEqual(next.cadCamera, activeCadCamera);
  assert.equal(next.cadProjection, "orthographic");
  assert.deepEqual(next.payload.camera, { preset: "front" });
});

test("pasting while enabled keeps the CAD restore camera", () => {
  const cadCamera = { position: [5, 6, 7], target: [0, 0, 0], up: [0, 0, 1], projection: "orthographic" };
  const next = renderSessionForPayloadApply(createRenderSessionState({
    enabled: true,
    cadCamera,
    payload: DEFAULT_RENDER_PAYLOAD
  }), {
    ...DEFAULT_RENDER_PAYLOAD,
    studio: "studio-dark"
  }, {
    activeCamera: { position: [50, 60, 70], target: [4, 5, 6], up: [0, 0, 1], projection: "perspective" }
  });

  assert.deepEqual(next.cadCamera, cadCamera);
  assert.equal(next.payload.studio, "studio-dark");
});

test("copy uses the stored Render camera while disabled and the live camera while enabled", () => {
  const storedRenderCamera = { position: [30, 40, 50], target: [3, 4, 5], up: [0, 0, 1], projection: "perspective" };
  const activeCadCamera = { position: [10, 20, 30], target: [1, 2, 3], up: [0, 0, 1], projection: "orthographic" };
  const disabled = createRenderSessionState({
    enabled: false,
    payload: { ...DEFAULT_RENDER_PAYLOAD, camera: storedRenderCamera }
  });
  assert.deepEqual(
    renderPayloadForCopy(disabled, { activeCamera: activeCadCamera }).camera,
    storedRenderCamera
  );

  const activeRenderCamera = { position: [60, 70, 80], target: [6, 7, 8], up: [0, 0, 1], projection: "perspective" };
  assert.deepEqual(
    renderPayloadForCopy({ ...disabled, enabled: true }, { activeCamera: activeRenderCamera }).camera,
    activeRenderCamera
  );
});

test("render camera seeds retain framing without carrying CAD projection or revision metadata", () => {
  assert.deepEqual(renderCameraSeed({
    position: [10, 20, 30],
    target: [1, 2, 3],
    up: [0, 0, 1],
    zoom: 1.4,
    projection: "orthographic",
    orthographicHalfHeight: 42,
    modelKey: "old-revision"
  }), {
    position: [10, 20, 30],
    target: [1, 2, 3],
    up: [0, 0, 1],
    zoom: 1.4,
    orthographicHalfHeight: 42
  });
});

test("camera presets and projection-only payloads resolve against current model bounds", () => {
  const bounds = { min: [0, 0, 0], max: [20, 40, 10] };
  const front = resolveRenderCameraSnapshot({ preset: "front", projection: "perspective" }, bounds);
  assert.deepEqual(front.target, [10, 20, 5]);
  assert.equal(front.position[0], 10);
  assert.ok(front.position[1] < 20);
  assert.equal(front.projection, "perspective");

  const projectionOnly = resolveRenderCameraSnapshot({ projection: "orthographic" }, bounds);
  assert.deepEqual(projectionOnly.target, [10, 20, 5]);
  assert.equal(projectionOnly.projection, "orthographic");
});

test("camera-only changes retain the Render visual settings key", () => {
  const base = {
    ...DEFAULT_RENDER_PAYLOAD,
    settings: { materials: { roughness: 0.4 } },
    display: { mode: "shaded" }
  };
  assert.equal(
    renderVisualSettingsKey({ ...base, camera: { preset: "front" } }),
    renderVisualSettingsKey({ ...base, camera: { preset: "top" } })
  );
  assert.equal(
    renderVisualSettingsKey({ ...base, quality: "interactive" }),
    renderVisualSettingsKey({ ...base, quality: "high" })
  );
  assert.notEqual(
    renderVisualSettingsKey(base),
    renderVisualSettingsKey({ ...base, settings: { materials: { roughness: 0.7 } } })
  );
});

test("quality resolves independently while Render visual settings stay stable", () => {
  assert.equal(resolveRenderSessionQuality(createRenderSessionState()).id, "interactive");
  assert.equal(resolveRenderSessionQuality(createRenderSessionState({
    enabled: true,
    payload: { ...DEFAULT_RENDER_PAYLOAD, quality: "standard" }
  })).id, "standard");
  assert.equal(resolveRenderSessionQuality(createRenderSessionState({
    enabled: true,
    payload: DEFAULT_RENDER_PAYLOAD
  })).id, "high");
});

test("copied render envelopes validate and canonicalize for the CLI", () => {
  const payload = parseRenderSettingsText(JSON.stringify({
    studio: "studio-light",
    appearance: "dark",
    quality: "standard",
    settings: { lighting: { toneMappingExposure: 1.25 } }
  }), { prefersDark: true });

  assert.deepEqual(payload, {
    studio: "studio-light",
    appearance: "dark",
    quality: "standard",
    settings: { lighting: { toneMappingExposure: 1.25 } }
  });
});

test("pasted render envelopes report JSON and schema failures", () => {
  assert.throws(() => parseRenderSettingsText("{broken"), /Invalid JSON/);
  assert.throws(
    () => parseRenderSettingsText('{"studio":"default","unknown":true}'),
    /Unsupported render fields: unknown/
  );
  assert.throws(
    () => parseRenderSettingsText('{"display":{"mode":"solid"}}'),
    /use 'shaded_edges'/
  );
});
