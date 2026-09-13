// A newly allocated WebGL canvas has no presentable scene. Keep it covered
// until the destination mode has drawn geometry with its own lighting.
export function createFramePresentation({ canvas, renderMode, onFirstFrame }) {
  canvas.style.visibility = "hidden";
  let presented = false;
  return {
    draw(runtime, drawFrame) {
      if (!presented && (!runtime?.hasVisibleModel || (renderMode && !runtime.environmentReady))) return false;
      drawFrame();
      if (!presented) {
        presented = true;
        canvas.style.visibility = "visible";
        onFirstFrame?.();
      }
      return true;
    }
  };
}

export function viewerTransitionBackdrop({ renderMode, renderConfiguration, background, viewerTheme }) {
  const color = (renderMode ? renderConfiguration?.backdrop?.color : background?.solidColor)
    || viewerTheme?.sceneBackground || "#f1f5f9";
  const hex = String(color).replace(/^#/, "");
  const rgb = (hex.length === 3 ? [...hex].map(value => value + value).join("") : hex);
  const luminance = /^[\da-f]{6}$/i.test(rgb)
    ? [0.2126, 0.7152, 0.0722].reduce((sum, weight, index) => (
        sum + weight * parseInt(rgb.slice(index * 2, index * 2 + 2), 16) / 255
      ), 0)
    : 1;
  return { backgroundColor: color, color: luminance > 0.5 ? "#334155" : "#e2e8f0" };
}
