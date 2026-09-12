import assert from "node:assert/strict";
import test from "node:test";

import * as THREE from "three";

import {
  cloneThemePresetSettings,
  normalizeThemeSettings,
  resolveThemeSettingsForColorMode
} from "./themeSettings.js";
import {
  addFloor,
  applyEnvironment,
  applyLighting,
  createSharedRenderOptions,
  RENDER_SCENE_SCALE,
  boundsCorners,
  boundsFromVertices,
  centerAndRadiusFromBounds,
  fitOrthographicCamera,
  fitPerspectiveCamera,
  frameHalfHeightForView,
  framePadding,
  inferRenderSceneScale,
  outputSize,
  resolveRenderView,
  resolveThemeJobConfig,
  resolveThemeSettings
} from "./renderOptions.js";

const SCALE_SETTINGS = Object.freeze({
  [RENDER_SCENE_SCALE.CAD]: Object.freeze({
    minBoundsSpan: 1,
    minModelRadius: 1,
    minFloorSize: 100,
    minCameraDistance: 10,
    minCameraFar: 1000
  }),
  [RENDER_SCENE_SCALE.URDF]: Object.freeze({
    minBoundsSpan: 0.05,
    minModelRadius: 0.05,
    minFloorSize: 0.05,
    minCameraDistance: 0.5,
    minCameraFar: 10
  })
});

function assertClose(actual, expected, epsilon = 1e-6) {
  assert.ok(Math.abs(actual - expected) <= epsilon, `${actual} !== ${expected}`);
}

test("shared render options preserve explicit caller-owned values without defaults", () => {
  const options = createSharedRenderOptions({
    displayMode: "wireframe",
    background: false,
    renderScale: 0
  });

  assert.equal(options.themeSettings, null);
  assert.equal(options.display, null);
  assert.equal(Object.hasOwn(options, "displayMode"), false);
  assert.equal(options.background, false);
  assert.equal(options.renderScale, 0);
});

test("disabled environments clear both the texture and shared intensity", async () => {
  const scene = new THREE.Scene();
  scene.environment = new THREE.Texture();
  scene.environmentIntensity = 4;
  const resource = await applyEnvironment(scene, {
    environment: { enabled: false, intensity: 0.25 }
  });
  assert.equal(resource, null);
  assert.equal(scene.environment, null);
  assert.equal(scene.environmentIntensity, 0);
});

test("theme resolution uses saved theme ids or direct theme settings", () => {
  assert.deepEqual(
    resolveThemeSettings({}, { defaultThemeId: "workbench-light" }),
    normalizeThemeSettings(cloneThemePresetSettings("workbench-light"))
  );
  assert.deepEqual(
    resolveThemeSettings({ theme: "workbench-dark" }, { defaultThemeId: "workbench-light" }),
    resolveThemeSettingsForColorMode(cloneThemePresetSettings("workbench-dark"), { prefersDark: false })
  );
  assert.deepEqual(
    resolveThemeJobConfig({
      theme: {
        materials: { defaultColor: "#123456" }
      }
    }, { defaultThemeId: "workbench-light" }),
    {
      themeId: "workbench-light",
      settings: { materials: { defaultColor: "#123456" } }
    }
  );
});

test("view presets and azimuth/elevation camera parsing remain stable", () => {
  const top = resolveRenderView("top");
  assert.equal(top.name, "top");
  assert.deepEqual(top.direction, [0, 0, 1]);
  assert.deepEqual(top.up, [0, 1, 0]);

  const custom = resolveRenderView("45:30");
  assert.equal(custom.name, "45:30");
  assertClose(custom.direction[0], Math.SQRT1_2 * Math.cos(Math.PI / 6));
  assertClose(custom.direction[1], -Math.SQRT1_2 * Math.cos(Math.PI / 6));
  assertClose(custom.direction[2], 0.5);
});

test("scene scale inference, bounds, and camera framing are policy-free helpers", () => {
  assert.equal(inferRenderSceneScale({ explicit: "urdf" }), RENDER_SCENE_SCALE.URDF);
  assert.equal(inferRenderSceneScale({ kind: "sdf" }), RENDER_SCENE_SCALE.URDF);
  assert.equal(inferRenderSceneScale({ parts: [{ linkName: "base_link" }] }), RENDER_SCENE_SCALE.URDF);
  assert.equal(inferRenderSceneScale({ kind: "glb", parts: [] }), RENDER_SCENE_SCALE.CAD);

  const bounds = boundsFromVertices(new Float32Array([0, 0, 0, 2, 4, 6]));
  assert.deepEqual(bounds, { min: [0, 0, 0], max: [2, 4, 6] });

  const { center, radius } = centerAndRadiusFromBounds(bounds, RENDER_SCENE_SCALE.CAD, SCALE_SETTINGS);
  assert.deepEqual(center.toArray(), [1, 2, 3]);
  assertClose(radius, Math.sqrt(56) / 2);

  const view = resolveRenderView("iso");
  const halfHeight = frameHalfHeightForView(view, bounds, 800, 600, 0.12, RENDER_SCENE_SCALE.CAD, SCALE_SETTINGS);
  assert.ok(halfHeight > 0);

  const camera = new THREE.OrthographicCamera();
  fitOrthographicCamera(camera, view, bounds, 800, 600, {
    padding: 0.12,
    sceneScale: RENDER_SCENE_SCALE.CAD,
    settingsByScale: SCALE_SETTINGS
  });
  assertClose(camera.top, halfHeight);
  assertClose(camera.bottom, -halfHeight);
  assertClose(camera.left, -halfHeight * (800 / 600));
  assertClose(camera.right, halfHeight * (800 / 600));
  assert.equal(camera.near, 0.01);
  assert.equal(camera.far >= 1000, true);
});

test("automatic perspective framing fits bounds to padding at wide and tall aspects", () => {
  const bounds = { min: [-50, -10, -5], max: [50, 10, 5] };
  const padding = 0.04;
  const safeContentScale = 1 - padding * 2;
  const fittedDistance = (width, height) => {
    const camera = new THREE.PerspectiveCamera(48, width / height, 0.1, 1000);
    const resolved = fitPerspectiveCamera(
      camera,
      { preset: "front", projection: "perspective" },
      bounds,
      width,
      height,
      {
        padding,
        sceneScale: RENDER_SCENE_SCALE.CAD,
        settingsByScale: SCALE_SETTINGS
      }
    );
    const projected = boundsCorners(bounds).map((point) => point.project(camera));
    const maxX = Math.max(...projected.map((point) => Math.abs(point.x)));
    const maxY = Math.max(...projected.map((point) => Math.abs(point.y)));
    assert.ok(maxX <= safeContentScale + 1e-6, `${maxX} exceeds horizontal padding`);
    assert.ok(maxY <= safeContentScale + 1e-6, `${maxY} exceeds vertical padding`);
    assert.ok(Math.max(maxX, maxY) >= safeContentScale - 1e-6, "fit should use the limiting output dimension");
    return new THREE.Vector3(...resolved.position).distanceTo(new THREE.Vector3(...resolved.target));
  };

  const wideDistance = fittedDistance(800, 400);
  const tallDistance = fittedDistance(400, 800);
  assert.ok(tallDistance > wideDistance, `${tallDistance} should exceed ${wideDistance}`);
});

test("tight perspective framing can fit visible points instead of empty bounds corners", () => {
  const bounds = { min: [-100, -100, -100], max: [100, 100, 100] };
  const fit = (framePoints = null) => {
    const camera = new THREE.PerspectiveCamera(48, 1, 0.1, 1000);
    const resolved = fitPerspectiveCamera(
      camera,
      { preset: "front", projection: "perspective" },
      bounds,
      480,
      480,
      {
        framePoints,
        padding: 0.04,
        sceneScale: RENDER_SCENE_SCALE.CAD,
        settingsByScale: SCALE_SETTINGS
      }
    );
    return {
      camera,
      distance: new THREE.Vector3(...resolved.position).distanceTo(new THREE.Vector3(...resolved.target))
    };
  };
  const visiblePoints = [
    new THREE.Vector3(-100, 0, 0),
    new THREE.Vector3(100, 0, 0),
    new THREE.Vector3(0, -100, 0),
    new THREE.Vector3(0, 100, 0),
    new THREE.Vector3(0, 0, -100),
    new THREE.Vector3(0, 0, 100)
  ];
  const boundsFit = fit();
  const tightFit = fit(visiblePoints);

  assert.ok(tightFit.distance < boundsFit.distance, `${tightFit.distance} should be closer than ${boundsFit.distance}`);
  const maxProjected = Math.max(...visiblePoints.flatMap((point) => {
    const projected = point.clone().project(tightFit.camera);
    return [Math.abs(projected.x), Math.abs(projected.y)];
  }));
  assertClose(maxProjected, 0.92, 1e-6);
});

test("perspective framing preserves explicit camera position and target", () => {
  const cameraSpec = {
    position: [23, -41, 17],
    target: [1, 2, 3],
    up: [0, 0, 1],
    projection: "perspective"
  };
  const bounds = { min: [-500, -200, -100], max: [600, 300, 200] };
  for (const [width, height, padding] of [[1600, 400, 0], [400, 1600, 0.15]]) {
    const camera = new THREE.PerspectiveCamera(48, width / height, 0.1, 1000);
    const resolved = fitPerspectiveCamera(camera, cameraSpec, bounds, width, height, {
      framePoints: [new THREE.Vector3(1000, 1000, 1000)],
      padding,
      sceneScale: RENDER_SCENE_SCALE.CAD,
      settingsByScale: SCALE_SETTINGS
    });
    assert.deepEqual(camera.position.toArray(), cameraSpec.position);
    assert.deepEqual(resolved.position, cameraSpec.position);
    assert.deepEqual(resolved.target, cameraSpec.target);
  }
});

test("orthographic framing restores canonical half-height and zoom", () => {
  const camera = new THREE.OrthographicCamera();
  const resolved = fitOrthographicCamera(
    camera,
    {
      preset: "front",
      projection: "orthographic",
      orthographicHalfHeight: 42,
      zoom: 1.5
    },
    { min: [-500, -500, -500], max: [500, 500, 500] },
    800,
    400,
    {
      padding: 0.04,
      sceneScale: RENDER_SCENE_SCALE.CAD,
      settingsByScale: SCALE_SETTINGS
    }
  );

  assert.equal(resolved.orthographicHalfHeight, 42);
  assert.equal(camera.top, 42);
  assert.equal(camera.bottom, -42);
  assert.equal(camera.left, -84);
  assert.equal(camera.right, 84);
  assert.equal(camera.zoom, 1.5);
});

test("output sizing and padding helpers preserve snapshot fallback semantics", () => {
  assert.deepEqual(outputSize({}, {}), { width: 1400, height: 900 });
  assert.deepEqual(outputSize({ width: 320, height: 240 }, { output: { width: 1400, height: 900 } }), { width: 320, height: 240 });
  assert.deepEqual(outputSize({}, { output: { width: 1600, height: 1200 } }), { width: 1600, height: 1200 });
  assert.equal(framePadding({}), 0.04);
  assert.equal(framePadding({ output: { padding: 0 } }), 0);
  assert.equal(framePadding({ output: { padding: 0.02 } }), 0.02);
  assert.equal(framePadding({ output: { padding: -0.02 } }), 0);
  assert.equal(framePadding({ output: { paddingPercent: 0.25 } }), 0.15);
  assert.equal(framePadding({ output: { paddingPercent: 0.13 } }), 0.13);
});

test("inspection guides use display-owned opacity and density", () => {
  const scene = new THREE.Scene();
  addFloor(
    scene,
    { min: [0, 0, 0], max: [10, 10, 10] },
    normalizeThemeSettings({
      floor: { mode: "none", enabled: false }
    }),
    RENDER_SCENE_SCALE.CAD,
    SCALE_SETTINGS,
    { grid: { enabled: true, centerColor: "#123456", cellColor: "#abcdef", opacity: 0.37, density: 2 } }
  );

  const grid = scene.children[0];
  const materials = Array.isArray(grid.material) ? grid.material : [grid.material];
  assert.equal(grid.type, "GridHelper");
  assert.equal(grid.geometry.getAttribute("position").count, 4 * (56 + 1));
  assert.equal(materials[0].opacity, 0.37);
  assert.equal(materials[0].transparent, true);
  assert.equal(materials[0].depthWrite, false);
});

test("display guides render independently from the studio stage floor", () => {
  const scene = new THREE.Scene();
  addFloor(
    scene,
    { min: [0, 0, 0], max: [10, 10, 10] },
    normalizeThemeSettings({
      floor: {
        mode: "stage",
        enabled: true,
        color: "#ddeeff",
        roughness: 0.36,
        reflectivity: 0.42,
        shadowOpacity: 0.25
      }
    }),
    RENDER_SCENE_SCALE.CAD,
    SCALE_SETTINGS,
    { grid: { enabled: true, centerColor: "#123456", cellColor: "#abcdef", opacity: 0.37, density: 2 } }
  );

  const grid = scene.children.find((child) => child.type === "GridHelper");
  const plane = scene.children.find((child) => child.material?.isMeshPhysicalMaterial);
  const shadow = scene.children.find((child) => child.material?.isShadowMaterial);
  const gridMaterials = Array.isArray(grid.material) ? grid.material : [grid.material];

  assert.ok(grid);
  assert.ok(plane);
  assert.ok(shadow);
  assert.equal(gridMaterials[0].opacity, 0.37);
  assert.equal(grid.position.z, 0);
  assert.equal(plane.material.color.getHexString(), "ddeeff");
  assert.equal(plane.material.roughness, 0.36);
  assert.ok(Math.abs(plane.material.reflectivity - 0.42) < 1e-9);
  assert.equal(plane.material.specularIntensity, 1);
  assert.equal(plane.material.metalness, 0);
  assert.equal(shadow.receiveShadow, true);
  assert.equal(shadow.material.opacity, 0.25);
});

test("snapshot lights scale to model bounds and fit the directional shadow camera", () => {
  const scene = new THREE.Scene();
  const lights = applyLighting(scene, normalizeThemeSettings({
    lighting: {
      directional: { position: { x: 240, y: -150, z: 340 } },
      spot: { enabled: true, distance: 600, position: { x: 160, y: -120, z: 140 } }
    }
  }), {
    bounds: { min: [0, 0, 0], max: [760, 0, 0] },
    sceneScale: RENDER_SCENE_SCALE.CAD,
    shadowMapSize: 512
  });

  assert.equal(lights.radius, 380);
  assert.equal(lights.positionScale, 0.5);
  assert.deepEqual(lights.directional.position.toArray(), [120, -75, 170]);
  assert.equal(lights.spot.distance, 300);
  assert.equal(lights.directional.shadow.mapSize.x, 512);
  assert.equal(lights.directional.shadow.camera.left, -1064);
  assert.equal(lights.directional.shadow.camera.right, 1064);
  assert.ok(lights.directional.shadow.camera.far >= lights.directional.position.length());
});

test("resolveThemeSettings applies colorMode to object themes", () => {
  // colorMode was previously honoured only for saved-theme-id STRINGS, which
  // made it an accepted-but-inert key in theme JSON: "light" and "dark"
  // produced byte-identical renders.
  const base = normalizeThemeSettings(cloneThemePresetSettings("workbench-light"));
  const withModes = {
    ...base,
    modeColors: {
      light: { background: { solidColor: "#ffffff" } },
      dark: { background: { solidColor: "#000000" } }
    }
  };

  const light = resolveThemeSettings({
    theme: { ...withModes, colorMode: "light" }
  });
  const dark = resolveThemeSettings({
    theme: { ...withModes, colorMode: "dark" }
  });

  assert.equal(light.background.solidColor, "#ffffff");
  assert.equal(dark.background.solidColor, "#000000");
});

test("resolveThemeSettings is the identity for settings without modeColors", () => {
  // The safety property of applying colorMode unconditionally: when no explicit
  // modeColors block is supplied, normalizeThemeModeColors derives it from the
  // settings themselves, so re-applying it must not alter anything.
  const settings = normalizeThemeSettings(cloneThemePresetSettings("workbench-light"));
  const explicit = { ...settings, background: { ...settings.background, solidColor: "#123456" } };
  delete explicit.modeColors;

  const resolved = resolveThemeSettings({ theme: explicit });

  assert.equal(resolved.background.solidColor, "#123456");
});
