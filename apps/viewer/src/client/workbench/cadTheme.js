import { resolveThemeSettingsForColorMode, SYSTEM_THEME_ID } from "cadgen-js/lib/themeSettings.js";

// PR #369's scene/chrome boundary: only System borrows the app background.
export function resolveCadThemeSettings(themeSettings, themeId, { prefersDark, chromeBackdropColor }) {
  const resolved = resolveThemeSettingsForColorMode(themeSettings, { prefersDark });
  if (themeId !== SYSTEM_THEME_ID) return resolved;
  return {
    ...resolved,
    background: { ...resolved.background, type: "solid", solidColor: chromeBackdropColor }
  };
}
