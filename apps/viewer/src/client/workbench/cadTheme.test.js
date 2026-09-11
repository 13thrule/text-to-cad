import assert from "node:assert/strict";
import test from "node:test";
import { cloneThemePresetSettings, resolveThemeSettingsForId } from "cadgen-js/lib/themeSettings.js";
import { resolveCadThemeSettings } from "./cadTheme.js";

test("System follows app appearance and its background token without altering the preset", () => {
  for (const prefersDark of [false, true]) {
    const source = resolveThemeSettingsForId("system", { prefersDark });
    const before = structuredClone(source);
    const chromeBackdropColor = prefersDark ? "#292929" : "#ffffff";
    const result = resolveCadThemeSettings(source, "system", { prefersDark, chromeBackdropColor });
    assert.equal(result.background.type, "solid");
    assert.equal(result.background.solidColor, chromeBackdropColor);
    assert.equal(result.colorMode, prefersDark ? "dark" : "light");
    assert.deepEqual(result.materials, source.materials);
    assert.deepEqual(result.lighting, source.lighting);
    assert.deepEqual(source, before);
  }
});

test("explicit scene presets retain their colors when app appearance changes", () => {
  for (const id of ["workbench-light", "workbench-dark", "cinematic"]) {
    const source = cloneThemePresetSettings(id);
    const light = resolveCadThemeSettings(source, id, { prefersDark: false, chromeBackdropColor: "#ffffff" });
    const dark = resolveCadThemeSettings(source, id, { prefersDark: true, chromeBackdropColor: "#292929" });
    assert.deepEqual(light, dark, id);
    assert.deepEqual(dark.background, source.background, id);
  }
});

test("custom backgrounds remain authored values, independent of app tokens", () => {
  const source = cloneThemePresetSettings("cinematic");
  source.background.radialOuter = "#193355";
  source.modeColors.dark.background.radialOuter = "#193355";
  for (const prefersDark of [false, true]) {
    const result = resolveCadThemeSettings(source, "custom", { prefersDark, chromeBackdropColor: "#aabbcc" });
    assert.equal(result.background.radialOuter, "#193355");
    assert.equal(result.background.type, "radial");
  }
});
