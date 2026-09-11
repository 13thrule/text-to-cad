import assert from "node:assert/strict";
import test from "node:test";

import {
  CAD_DISPLAY_MODE,
  DEFAULT_DISPLAY_EDGE_SETTINGS,
  DEFAULT_DISPLAY_GUIDE_SETTINGS,
  DEFAULT_DISPLAY_SETTINGS,
  DEFAULT_EXPLODED_VIEW_SETTINGS,
  DEFAULT_PART_COLOR_SETTINGS,
  displayModeForcesEdges,
  displayModeShowsEdges,
  displayModeShowsThroughEdges,
  displayModeSurfaceOpacity,
  displayModeUsesUnlitSurfaces,
  displaySettingsEqual,
  normalizeDisplayEdgeSettings,
  normalizeDisplaySettings,
  normalizeExplodedViewSettings,
  resolveDisplayMode
} from "./displaySettings.js";

test("display settings own CAD presentation fields while camera owns projection", () => {
  assert.deepEqual(normalizeDisplaySettings(), DEFAULT_DISPLAY_SETTINGS);
  assert.equal(resolveDisplayMode({ mode: "wireframe" }), CAD_DISPLAY_MODE.WIREFRAME);
  assert.throws(
    () => normalizeDisplaySettings({ projection: "perspective" }),
    /Unsupported display fields: projection/
  );
  assert.deepEqual(normalizeDisplaySettings({
    mode: "wireframe",
    clip: { enabled: true, axis: "z", offsets: { z: 0.4 }, invert: true }
  }), {
    mode: CAD_DISPLAY_MODE.WIREFRAME,
    clip: {
      enabled: true,
      axis: "z",
      offset: 0.4,
      offsets: { x: 0, y: 0, z: 0.4 },
      invert: true
    },
    exploded: DEFAULT_EXPLODED_VIEW_SETTINGS,
    edges: DEFAULT_DISPLAY_EDGE_SETTINGS,
    guides: DEFAULT_DISPLAY_GUIDE_SETTINGS,
    partColor: DEFAULT_PART_COLOR_SETTINGS
  });
});

test("display settings normalize edge styling independently from studio settings", () => {
  assert.deepEqual(normalizeDisplayEdgeSettings({
    enabled: false,
    color: "#ABC",
    thickness: 2,
    classes: { tangent: { color: "#456", opacity: 0.25, thickness: 4 } },
    highlightColor: "#123456",
    highlightOpacity: 0.4,
    highlightThickness: 4,
    silhouette: true,
    silhouetteScale: 0.01
  }), {
    enabled: false,
    color: "#aabbcc",
    thickness: 2,
    classes: {
      feature: { color: "#aabbcc", opacity: 1, thickness: 1.15 },
      tangent: { color: "#445566", opacity: 0.25, thickness: 4 },
      seam: { color: "#aabbcc", opacity: 0.85, thickness: 1.15 },
      degenerate: { color: "#aabbcc", opacity: 1, thickness: 0 }
    },
    highlightColor: "#123456",
    highlightOpacity: 0.4,
    highlightThickness: 4,
    silhouette: true,
    silhouetteScale: 0.01
  });
  assert.equal(normalizeDisplaySettings({
    mode: "shaded_edges",
    edges: { enabled: false, color: "#456" }
  }).edges.color, "#445566");
});

test("display settings normalize exploded view, guides, and part colors", () => {
  assert.deepEqual(normalizeExplodedViewSettings({ enabled: true, amount: 0.5 }), {
    enabled: true,
    amount: 0.5
  });
  assert.equal(normalizeExplodedViewSettings({ amount: 9 }).amount, 1);
  assert.equal(normalizeExplodedViewSettings({ amount: -1 }).amount, 0);
  assert.deepEqual(normalizeExplodedViewSettings({ enabled: 1 }), { enabled: false, amount: 0 });

  const normalized = normalizeDisplaySettings({
    guides: {
      grid: { enabled: false, centerColor: "#ABC", density: 2 },
      axis: { enabled: false }
    },
    partColor: { mode: "by_part", color: "#123456", colors: ["#abc", "#445566"] }
  });
  assert.equal(normalized.guides.grid.enabled, false);
  assert.equal(normalized.guides.grid.centerColor, "#aabbcc");
  assert.equal(normalized.guides.grid.density, 2);
  assert.equal(normalized.guides.axis.enabled, false);
  assert.deepEqual(normalized.partColor, {
    mode: "by_part",
    color: "#123456",
    colors: ["#aabbcc", "#445566"]
  });
});

test("display mode vocabulary is canonical and retired values teach replacements", () => {
  for (const mode of Object.values(CAD_DISPLAY_MODE)) {
    assert.equal(resolveDisplayMode({ mode }), mode);
  }
  assert.throws(() => resolveDisplayMode({ mode: "solid" }), /use 'shaded_edges'/);
  assert.throws(() => resolveDisplayMode({ mode: "rendered" }), /use 'shaded'/);
  for (const alias of ["edges", "shaded-with-edges", "x-ray", "theme", "wire"]) {
    assert.throws(() => resolveDisplayMode({ mode: alias }), /Unknown display mode/);
  }
});

test("display mode policies describe edge and surface behavior", () => {
  assert.equal(displayModeShowsEdges(CAD_DISPLAY_MODE.SHADED_EDGES), true);
  assert.equal(displayModeForcesEdges(CAD_DISPLAY_MODE.SHADED_EDGES), true);
  assert.equal(displayModeShowsEdges(CAD_DISPLAY_MODE.SHADED), false);
  assert.equal(displayModeShowsEdges(CAD_DISPLAY_MODE.WIREFRAME), true);
  assert.equal(displayModeShowsThroughEdges(CAD_DISPLAY_MODE.HIDDEN_EDGES), true);
  assert.equal(displayModeShowsThroughEdges(CAD_DISPLAY_MODE.TRANSPARENT), true);
  assert.equal(displayModeUsesUnlitSurfaces(CAD_DISPLAY_MODE.UNSHADED), true);
  assert.equal(displayModeSurfaceOpacity(CAD_DISPLAY_MODE.TRANSPARENT, 1), 0.22);
  assert.equal(displayModeSurfaceOpacity(CAD_DISPLAY_MODE.HIDDEN_LINES_REMOVED, 1), 0.045);
});

test("display settings compare after normalization", () => {
  assert.equal(displaySettingsEqual(
    { mode: "wireframe", clip: { enabled: true, axis: "x", offsets: { x: 0.5 } } },
    { mode: CAD_DISPLAY_MODE.WIREFRAME, clip: { enabled: true, axis: "x", offsets: { x: 0.5 } } }
  ), true);
  assert.equal(displaySettingsEqual({ mode: "shaded" }, { mode: "wireframe" }), false);
  assert.equal(displaySettingsEqual(
    { mode: "shaded_edges", exploded: { enabled: true } },
    { mode: "shaded_edges", exploded: { enabled: false } }
  ), false);
  assert.equal(displaySettingsEqual(
    { mode: "shaded_edges", edges: { color: "#111111" } },
    { mode: "shaded_edges", edges: { color: "#222222" } }
  ), false);
  assert.equal(displaySettingsEqual(
    { guides: { grid: { enabled: false } } },
    { guides: { grid: { enabled: true } } }
  ), false);
  assert.equal(displaySettingsEqual(
    { partColor: { mode: "single", color: "#111111" } },
    { partColor: { mode: "single", color: "#222222" } }
  ), false);
});
