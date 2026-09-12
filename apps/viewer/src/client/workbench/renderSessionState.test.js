import assert from "node:assert/strict";
import test from "node:test";
import { resolveSceneSettings } from "cadgen-js/common/sceneSettings.js";

import {
  DEFAULT_RENDER_PAYLOAD,
  createRenderSessionState,
  parseRenderSettingsText,
  renderCameraSeed,
  renderPayloadForCopy,
  renderSessionForEnabledChange,
  renderSessionForPayloadApply,
  renderSessionForReset,
  renderVisualSettingsKey,
  resetRenderPayload,
  resolveRenderCameraSnapshot,
  resolveRenderSessionQuality,
  setRenderPayloadValue,
  updateRenderPayload
} from "./renderSessionState.js";

test("render sessions default to an off, sparse photographic setup", () => {
  const state = createRenderSessionState();

  assert.equal(state.enabled, false);
  assert.deepEqual(state.payload, DEFAULT_RENDER_PAYLOAD);
  assert.equal(state.cadProjection, "orthographic");
  assert.equal(state.cadCamera, null);
  assert.deepEqual(state.openSectionIds, ["render"]);
});

test("Render tab selection stays outside the copied payload and starts at Studio on re-entry", () => {
  const session = createRenderSessionState({
    enabled: true,
    openSectionIds: ["animation", "display", "animation"],
    payload: { exposure: 0.5 }
  });
  assert.deepEqual(session.openSectionIds, ["animation"]);
  assert.deepEqual(renderPayloadForCopy(session), { exposure: 0.5 });
  assert.deepEqual(createRenderSessionState(JSON.parse(JSON.stringify(session))).openSectionIds, ["animation"]);
  const disabled = renderSessionForEnabledChange(session, false);
  assert.deepEqual(disabled.openSectionIds, ["animation"]);
  const reenabled = renderSessionForEnabledChange(disabled, true);
  assert.deepEqual(reenabled.openSectionIds, ["render"]);
  assert.equal(reenabled.payload.exposure, 0.5);
});

test("an omitted studio follows app appearance until explicitly pinned", () => {
  const adaptive = createRenderSessionState({ enabled: true }).payload;
  assert.equal(resolveSceneSettings({ appearance: "light", render: adaptive }).render.configuration.studio, "light");
  assert.equal(resolveSceneSettings({ appearance: "dark", render: adaptive }).render.configuration.studio, "dark");
  assert.equal(Object.hasOwn(adaptive, "studio"), false);

  const pinned = updateRenderPayload(adaptive, { studio: "light" });
  assert.equal(resolveSceneSettings({ appearance: "dark", render: pinned }).render.configuration.studio, "light");
  assert.equal(pinned.studio, "light");
});

test("photographic edits write directly into the sparse public payload", () => {
  let payload = setRenderPayloadValue(DEFAULT_RENDER_PAYLOAD, ["lighting", "size"], 1.75);
  payload = setRenderPayloadValue(payload, ["backdrop", "transparent"], true);
  payload = setRenderPayloadValue(payload, ["exposure"], -0.7);

  assert.deepEqual(payload, {
    lighting: { size: 1.75 },
    backdrop: { transparent: true },
    exposure: -0.7
  });
});

test("reset clears every customization while preserving the live pose, not its Render lens", () => {
  const payload = resetRenderPayload({
    position: [10, 20, 30],
    target: [1, 2, 3],
    up: [0, 0, 1],
    zoom: 1.2,
    projection: "perspective",
    focalLength: 85
  });

  assert.deepEqual(payload, {
    camera: {
      position: [10, 20, 30],
      target: [1, 2, 3],
      up: [0, 0, 1],
      zoom: 1.2
    }
  });
});

test("reset preserves enablement and the saved CAD restore camera", () => {
  const cadCamera = {
    position: [10, 20, 30], target: [1, 2, 3], up: [0, 0, 1],
    projection: "orthographic", orthographicHalfHeight: 24
  };
  const renderCamera = {
    position: [50, 60, 70], target: [4, 5, 6], up: [0, 0, 1],
    projection: "perspective", focalLength: 90
  };
  const customized = createRenderSessionState({
    enabled: false,
    cadCamera,
    cadProjection: "orthographic",
    payload: { studio: "dark", quality: "preview", exposure: 1, camera: renderCamera }
  });

  const disabledReset = renderSessionForReset(customized, { activeCamera: renderCamera });
  assert.equal(disabledReset.enabled, false);
  assert.deepEqual(disabledReset.payload, {});
  assert.deepEqual(disabledReset.cadCamera, cadCamera);

  const enabledReset = renderSessionForReset({ ...customized, enabled: true }, { activeCamera: renderCamera });
  assert.equal(enabledReset.enabled, true);
  assert.deepEqual(enabledReset.cadCamera, cadCamera);
  assert.deepEqual(enabledReset.payload.camera, {
    position: renderCamera.position,
    target: renderCamera.target,
    up: renderCamera.up
  });
});

test("pasting while disabled captures the current CAD camera before enabling Render", () => {
  const activeCadCamera = {
    position: [12, 22, 32], target: [1, 2, 3], up: [0, 0, 1], zoom: 1.15,
    projection: "orthographic", focalLength: 22, orthographicHalfHeight: 24
  };
  const next = renderSessionForPayloadApply(createRenderSessionState({ enabled: false }), {
    studio: "dark",
    camera: { preset: "front", focalLength: 70 }
  }, {
    activeCamera: activeCadCamera,
    activeProjection: "orthographic"
  });

  assert.equal(next.enabled, true);
  assert.deepEqual(next.cadCamera, activeCadCamera);
  assert.equal(next.cadProjection, "orthographic");
  assert.deepEqual(next.payload.camera, { preset: "front", focalLength: 70 });
});

test("first enable saves the CAD camera without seeding Render composition from it", () => {
  const cadCamera = {
    position: [90, 80, 70], target: [9, 8, 7], up: [0, 0, 1], zoom: 1.4,
    projection: "orthographic", focalLength: 21, orthographicHalfHeight: 18
  };
  const first = renderSessionForEnabledChange(createRenderSessionState(), true, {
    activeCamera: cadCamera,
    activeProjection: "orthographic"
  });
  assert.equal(first.enabled, true);
  assert.deepEqual(first.cadCamera, cadCamera);
  assert.deepEqual(first.payload, {});

  const savedRenderCamera = {
    position: [30, 40, 50], target: [3, 4, 5], up: [0, 0, 1],
    projection: "perspective", focalLength: 75
  };
  const disabled = renderSessionForEnabledChange({ ...first, payload: { exposure: 1 } }, false, {
    activeCamera: savedRenderCamera
  });
  const reenabled = renderSessionForEnabledChange(disabled, true, { activeCamera: cadCamera });
  assert.deepEqual(reenabled.payload.camera, savedRenderCamera);
  assert.deepEqual(reenabled.cadCamera, cadCamera);
});

test("pasting while enabled leaves the CAD restore camera untouched", () => {
  const cadCamera = { position: [5, 6, 7], target: [0, 0, 0], up: [0, 0, 1], projection: "orthographic" };
  const next = renderSessionForPayloadApply(createRenderSessionState({
    enabled: true,
    cadCamera
  }), { exposure: 1.5 }, {
    activeCamera: { position: [50, 60, 70], target: [4, 5, 6], up: [0, 0, 1], projection: "perspective" }
  });

  assert.deepEqual(next.cadCamera, cadCamera);
  assert.equal(next.payload.exposure, 1.5);
});

test("copy uses stored Render camera while disabled and live Render camera while enabled", () => {
  const storedRenderCamera = {
    position: [30, 40, 50], target: [3, 4, 5], up: [0, 0, 1], projection: "perspective", focalLength: 65
  };
  const disabled = createRenderSessionState({ enabled: false, payload: { camera: storedRenderCamera } });
  assert.deepEqual(renderPayloadForCopy(disabled, {
    activeCamera: { position: [10, 20, 30], target: [1, 2, 3], up: [0, 0, 1], projection: "orthographic" }
  }).camera, storedRenderCamera);

  const activeRenderCamera = {
    position: [60, 70, 80], target: [6, 7, 8], up: [0, 0, 1], projection: "perspective", focalLength: 105
  };
  assert.deepEqual(renderPayloadForCopy({ ...disabled, enabled: true }, {
    activeCamera: activeRenderCamera
  }).camera, activeRenderCamera);
});

test("render camera seeds retain lens and framing without CAD projection or model metadata", () => {
  assert.deepEqual(renderCameraSeed({
    position: [10, 20, 30], target: [1, 2, 3], up: [0, 0, 1], zoom: 1.4,
    projection: "orthographic", focalLength: 72, orthographicHalfHeight: 42, modelKey: "old"
  }), {
    position: [10, 20, 30], target: [1, 2, 3], up: [0, 0, 1], zoom: 1.4,
    focalLength: 72, orthographicHalfHeight: 42
  });
});

test("camera presets and projection-only payloads resolve against current model bounds", () => {
  const bounds = { min: [0, 0, 0], max: [20, 40, 10] };
  const front = resolveRenderCameraSnapshot({ preset: "front", projection: "perspective", focalLength: 80 }, bounds);
  assert.deepEqual(front.target, [10, 20, 5]);
  assert.ok(front.position[1] < 20);
  assert.equal(front.projection, "perspective");
  assert.equal(front.focalLength, 80);

  assert.equal(resolveRenderCameraSnapshot({ projection: "orthographic" }, bounds).projection, "orthographic");
});

test("camera and quality changes retain the Render visual settings identity", () => {
  const base = { exposure: 0.5, lighting: { size: 1.2 }, backdrop: { ground: true } };
  assert.equal(
    renderVisualSettingsKey({ ...base, camera: { preset: "front" } }),
    renderVisualSettingsKey({ ...base, camera: { preset: "top" } })
  );
  assert.equal(
    renderVisualSettingsKey({ ...base, quality: "preview" }),
    renderVisualSettingsKey({ ...base, quality: "final" })
  );
  assert.notEqual(renderVisualSettingsKey(base), renderVisualSettingsKey({ ...base, exposure: 1 }));
});

test("Render quality resolves independently from the photographic visual payload", () => {
  assert.equal(resolveRenderSessionQuality(createRenderSessionState()).id, "interactive");
  assert.equal(resolveRenderSessionQuality(createRenderSessionState({
    enabled: true,
    payload: { quality: "preview" }
  })).id, "standard");
  const final = resolveRenderSessionQuality(createRenderSessionState({ enabled: true }));
  assert.equal(final.id, "high");
  assert.equal(final.targetPixelError, 0.25);
  assert.equal(final.snapshotLodLevel, 3);
  assert.equal(final.shadowMapSize, 4096);
  assert.equal(final.environmentMapSize, 512);
});

test("clipboard envelopes validate and canonicalize for the CLI", () => {
  const payload = parseRenderSettingsText(JSON.stringify({
    studio: "dark",
    quality: "preview",
    exposure: -0.5,
    lighting: { rotation: 45, size: 1.5, fill: 0.4 },
    backdrop: { color: "#123456", transparent: false, ground: true },
    camera: { preset: "front", focalLength: 85 }
  }));

  assert.deepEqual(payload, {
    studio: "dark",
    quality: "preview",
    exposure: -0.5,
    lighting: { rotation: 45, size: 1.5, fill: 0.4 },
    backdrop: { color: "#123456", transparent: false, ground: true },
    camera: { preset: "front", focalLength: 85 }
  });
});

test("clipboard parsing reports malformed JSON and closed-schema failures", () => {
  assert.throws(() => parseRenderSettingsText("{broken"), /Invalid JSON/);
  assert.throws(() => parseRenderSettingsText('{"unknown":true}'), /Unsupported render fields: unknown/);
  assert.throws(() => parseRenderSettingsText('{"display":{"mode":"wireframe"}}'), /Unsupported render fields: display/);
  assert.throws(() => parseRenderSettingsText('{"lighting":{"size":5}}'), /size/);
  assert.throws(() => parseRenderSettingsText('{"camera":{"focalLength":10}}'), /focalLength/);
});
