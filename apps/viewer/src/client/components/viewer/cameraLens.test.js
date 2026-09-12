import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import {
  CAD_DEFAULT_VERTICAL_FOV_DEGREES,
  explicitViewerFocalLength,
  perspectiveDistanceScale
} from "./cameraLens.js";

test("a missing Render lens returns the perspective camera to CAD's native field of view", () => {
  assert.equal(CAD_DEFAULT_VERTICAL_FOV_DEGREES, 48);
  assert.equal(explicitViewerFocalLength(null), null);
  assert.equal(explicitViewerFocalLength(undefined), null);
  assert.equal(explicitViewerFocalLength("50"), null);
  assert.equal(explicitViewerFocalLength(0), null);
  assert.equal(explicitViewerFocalLength(50), 50);
});

test("lens changes preserve projected subject scale by changing camera distance", () => {
  assert.equal(perspectiveDistanceScale(48, 48), 1);
  assert.ok(perspectiveDistanceScale(48, 30) > 1);
  assert.ok(perspectiveDistanceScale(30, 48) < 1);
  assert.equal(perspectiveDistanceScale(0, 30), 1);
});

test("resetting an 85 mm Render lens to 50 mm preserves projected composition", () => {
  const camera = new THREE.PerspectiveCamera(48, 16 / 9, 0.1, 10000);
  camera.setFocalLength(85);
  const previousFov = camera.fov;
  const previousDistance = 628.5778;
  const previousProjectedScale = 1 / (previousDistance * Math.tan(previousFov * Math.PI / 360));

  camera.setFocalLength(50);
  const nextDistance = previousDistance * perspectiveDistanceScale(previousFov, camera.fov);
  const nextProjectedScale = 1 / (nextDistance * Math.tan(camera.fov * Math.PI / 360));

  assert.ok(nextDistance < previousDistance);
  assert.ok(Math.abs(nextProjectedScale - previousProjectedScale) < 1e-12);
});
