import assert from "node:assert/strict";
import test from "node:test";

import {
  RENDER_PAYLOAD_KEYS,
  RENDER_STUDIO_PRESETS,
  SCENE_QUALITY,
  normalizeRenderPayload,
  resolveDisplayMaterialSettings,
  resolveSceneSettings
} from "./sceneSettings.js";

test("normal CAD scenes follow appearance with neutral inspection defaults", () => {
  const light = resolveSceneSettings({ appearance: "light" });
  const dark = resolveSceneSettings({ appearance: "dark" });

  assert.equal(light.render.enabled, false);
  assert.equal(light.camera.projection, "orthographic");
  assert.equal(light.display.mode, "shaded_edges");
  assert.equal(light.display.guides.grid.enabled, true);
  assert.equal(light.display.guides.axis.enabled, true);
  assert.equal(light.display.partColor.mode, "original");
  assert.equal(light.render.settings.materials.overrideSourceColors, false);
  assert.equal(light.quality.id, SCENE_QUALITY.INTERACTIVE);
  assert.equal(light.render.settings.background.solidColor, "#f0f4f9");
  assert.equal(dark.render.settings.background.solidColor, "#333333");
});

test("omitted Render studio follows appearance while the normalized payload stays sparse", () => {
  const light = resolveSceneSettings({ appearance: "light", render: {} });
  const dark = resolveSceneSettings({ appearance: "dark", render: {} });

  assert.equal(light.render.enabled, true);
  assert.equal(light.render.studio, "studio-light");
  assert.equal(dark.render.studio, "studio-dark");
  assert.equal(Object.hasOwn(light.render.payload, "studio"), false);
  assert.equal(Object.hasOwn(normalizeRenderPayload({}), "studio"), false);
  assert.equal(light.render.payload.quality, "high");
  assert.equal(light.camera.projection, "perspective");
  assert.equal(light.display.mode, "shaded");
  assert.equal(light.display.guides.grid.enabled, false);
  assert.equal(light.display.guides.axis.enabled, false);
  assert.equal(light.render.settings.materials.overrideSourceColors, false);
  assert.equal(light.quality.id, SCENE_QUALITY.HIGH);
  assert.equal(light.quality.targetPixelError, 0.25);
  assert.equal(light.quality.snapshotLodLevel, 3);
  assert.equal(light.quality.renderScale, 2);
  assert.equal(light.quality.shadowMapSize, 4096);
  assert.equal(light.quality.environmentMapSize, 512);
  assert.equal(light.render.settings.background.solidColor, "#e8e9e8");
  assert.equal(dark.render.settings.background.solidColor, "#101113");

  const pinnedLight = resolveSceneSettings({
    appearance: "dark",
    render: { studio: "studio-light" }
  });
  assert.equal(pinnedLight.appearance, "dark");
  assert.equal(pinnedLight.render.studio, "studio-light");
  assert.equal(pinnedLight.render.payload.studio, "studio-light");
});

test("explicit camera presets replace lower-priority poses while projection-only overrides preserve them", () => {
  const copiedPose = {
    position: [10, 20, 30],
    target: [1, 2, 3],
    up: [0, 0, 1],
    zoom: 1.4,
    orthographicHalfHeight: 18
  };
  const selectedView = resolveSceneSettings({
    render: { camera: copiedPose },
    camera: { preset: "front" }
  });
  assert.equal(selectedView.camera.preset, "front");
  assert.deepEqual(selectedView.camera.direction, [0, -1, 0]);
  assert.deepEqual(selectedView.camera.up, [0, 0, 1]);
  assert.equal(Object.hasOwn(selectedView.camera, "position"), false);
  assert.equal(Object.hasOwn(selectedView.camera, "target"), false);
  assert.equal(Object.hasOwn(selectedView.camera, "orthographicHalfHeight"), false);
  assert.equal(selectedView.camera.zoom, 1);

  const selectedByString = resolveSceneSettings({
    render: { camera: copiedPose },
    camera: "front"
  });
  assert.equal(selectedByString.camera.preset, "front");
  assert.deepEqual(selectedByString.camera.direction, [0, -1, 0]);
  assert.equal(Object.hasOwn(selectedByString.camera, "position"), false);

  const changedLens = resolveSceneSettings({
    render: { camera: copiedPose },
    camera: { projection: "orthographic" }
  });
  assert.equal(changedLens.camera.projection, "orthographic");
  assert.deepEqual(changedLens.camera.position, copiedPose.position);
  assert.deepEqual(changedLens.camera.target, copiedPose.target);
  assert.deepEqual(changedLens.camera.up, copiedPose.up);
  assert.equal(changedLens.camera.zoom, copiedPose.zoom);
  assert.equal(changedLens.camera.orthographicHalfHeight, copiedPose.orthographicHalfHeight);

  const changedDirection = resolveSceneSettings({
    render: { camera: copiedPose },
    camera: { direction: [0, 1, 0] }
  });
  assert.equal(changedDirection.camera.name, "custom");
  assert.deepEqual(changedDirection.camera.direction, [0, 1, 0]);
  assert.deepEqual(changedDirection.camera.target, copiedPose.target);
  assert.deepEqual(changedDirection.camera.up, copiedPose.up);
  assert.equal(changedDirection.camera.zoom, copiedPose.zoom);
  assert.equal(Object.hasOwn(changedDirection.camera, "position"), false);
  assert.equal(Object.hasOwn(changedDirection.camera, "orthographicHalfHeight"), false);
});

test("scene precedence is base then embedded Render then explicit overrides", () => {
  const resolved = resolveSceneSettings({
    render: {
      camera: { preset: "top", projection: "orthographic" },
      display: { mode: "wireframe", guides: { grid: { enabled: true } } }
    },
    camera: { preset: "front", projection: "perspective" },
    display: { mode: "shaded_edges", guides: { axis: { enabled: true } } }
  });

  assert.equal(resolved.camera.preset, "front");
  assert.equal(resolved.camera.projection, "perspective");
  assert.equal(resolved.display.mode, "shaded_edges");
  assert.equal(resolved.display.guides.grid.enabled, true);
  assert.equal(resolved.display.guides.axis.enabled, true);
});

test("Render exposes exactly two studios and teaches retired payloads", () => {
  assert.deepEqual(RENDER_STUDIO_PRESETS.map(({ id, label }) => ({ id, label })), [
    { id: "studio-light", label: "Light studio" },
    { id: "studio-dark", label: "Dark studio" }
  ]);
  assert.throws(
    () => resolveSceneSettings({ render: { studio: "cinematic" } }),
    /use 'studio-dark'/
  );
  assert.throws(
    () => resolveSceneSettings({ render: { studio: "vibrant" } }),
    /use 'studio-light'/
  );
  assert.throws(
    () => resolveSceneSettings({ render: { studio: "default" } }),
    /omit studio to follow appearance/
  );
  for (const studio of ["colorful", "blue", "pink", "clay", "clay-sunrise", "terminal"]) {
    assert.throws(
      () => resolveSceneSettings({ render: { studio } }),
      /customize render\.settings/
    );
  }
  assert.throws(
    () => resolveSceneSettings({ render: { appearance: "dark" } }),
    /render\.appearance was removed; omit studio to follow appearance/
  );
  assert.deepEqual(RENDER_PAYLOAD_KEYS, ["studio", "quality", "settings", "camera", "display"]);
});

test("light and dark studios share a neutral shape-revealing pipeline", () => {
  const light = resolveSceneSettings({ render: { studio: "studio-light" } }).render.settings;
  const dark = resolveSceneSettings({ render: { studio: "studio-dark" } }).render.settings;

  assert.deepEqual(light.materials, dark.materials);
  assert.deepEqual(light.environment, dark.environment);
  assert.deepEqual(light.lighting, dark.lighting);
  assert.deepEqual(
    { ...light.floor, color: null },
    { ...dark.floor, color: null }
  );
  assert.notEqual(light.background.solidColor, dark.background.solidColor);
  assert.notEqual(light.floor.color, dark.floor.color);
  assert.equal(light.materials.metalness, 0.03);
  assert.equal(light.materials.saturation, 1);
  assert.equal(light.materials.contrast, 1);
  assert.equal(light.materials.brightness, 1);
  assert.equal(light.environment.presetId, "studio-softbox");
  assert.equal(light.lighting.spot.enabled, false);
  assert.equal(light.lighting.point.enabled, false);
  assert.ok(light.lighting.toneMappingExposure < 1);
});

test("sparse PBR edits override authored channels while studio values remain fallbacks", () => {
  const defaults = resolveSceneSettings({ render: {} });
  const customized = resolveSceneSettings({
    render: {
      settings: {
        materials: { roughness: 0.08, metalness: 0.92 }
      }
    }
  });

  assert.deepEqual(defaults.render.materialOverrides, {});
  assert.equal(defaults.render.settings.materials.roughness, 0.36);
  assert.deepEqual(customized.render.materialOverrides, { roughness: 0.08, metalness: 0.92 });
  assert.equal(customized.render.settings.materials.roughness, 0.08);
  assert.deepEqual(customized.render.payload.settings, {
    materials: { roughness: 0.08, metalness: 0.92 }
  });
});

test("normal CAD uses matte inspection PBR while preserving authored color channels", () => {
  const scene = resolveSceneSettings({ appearance: "light" });

  assert.equal(scene.render.enabled, false);
  assert.deepEqual(scene.render.materialOverrides, {
    roughness: scene.render.settings.materials.roughness,
    metalness: scene.render.settings.materials.metalness,
    clearcoat: scene.render.settings.materials.clearcoat,
    clearcoatRoughness: scene.render.settings.materials.clearcoatRoughness
  });
  assert.equal(scene.render.settings.materials.overrideSourceColors, false);
  assert.equal(Object.hasOwn(scene.render.materialOverrides, "opacity"), false);
});

test("part color policy is display-owned and preserves the editable palette", () => {
  const single = resolveSceneSettings({
    display: { partColor: { mode: "single", color: "#123456" } }
  });
  const byPart = resolveSceneSettings({
    display: { partColor: { mode: "by_part", colors: ["#112233", "#abcdef"] } }
  });

  assert.equal(single.render.settings.materials.overrideSourceColors, true);
  assert.deepEqual(single.render.settings.materials.fillColors, ["#123456"]);
  assert.equal(single.render.settings.materials.cycleColors, false);
  assert.equal(byPart.render.settings.materials.overrideSourceColors, true);
  assert.deepEqual(byPart.render.settings.materials.fillColors, ["#112233", "#abcdef"]);
  assert.equal(byPart.render.settings.materials.cycleColors, true);
  assert.deepEqual(resolveDisplayMaterialSettings(
    { defaultColor: "#ffffff", overrideSourceColors: false },
    { mode: "single", color: "#123456" }
  ), {
    defaultColor: "#123456",
    fillColors: ["#123456"],
    cycleColors: false,
    overrideSourceColors: true
  });
});

test("Render validation rejects unknown and malformed fields atomically", () => {
  assert.throws(() => resolveSceneSettings({ render: { nope: true } }), /Unsupported render fields/);
  assert.throws(() => resolveSceneSettings({ render: { studio: 0 } }), /Unknown render studio/);
  assert.throws(() => resolveSceneSettings({ render: { quality: 0 } }), /Unknown scene quality/);
  assert.throws(
    () => resolveSceneSettings({ render: { settings: { floor: { grid: {} } } } }),
    /Unsupported render.settings.floor fields/
  );
  assert.throws(
    () => resolveSceneSettings({ render: { settings: { materials: { roughness: "0.2" } } } }),
    /roughness must be a finite number/
  );
  assert.throws(
    () => resolveSceneSettings({ render: { settings: { materials: { metalness: 2 } } } }),
    /metalness must be a finite number/
  );
  assert.throws(
    () => resolveSceneSettings({ render: { settings: { lighting: { directional: { position: 4 } } } } }),
    /position must be an object/
  );
  assert.throws(
    () => resolveSceneSettings({ render: { camera: { projection: "fisheye" } } }),
    /camera.projection/
  );
  assert.throws(
    () => resolveSceneSettings({ render: { display: { guides: { grid: { opacity: "0.5" } } } } }),
    /display.guides.grid.opacity must be a finite number/
  );
  assert.throws(
    () => resolveSceneSettings({ render: { display: { partColor: { mode: "by_part", colors: [] } } } }),
    /display.partColor.colors must contain 1 to 50/
  );
});
