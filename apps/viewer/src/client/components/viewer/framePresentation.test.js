import assert from "node:assert/strict";
import test from "node:test";
import { createFramePresentation, viewerTransitionBackdrop } from "./framePresentation.js";

test("Render stays covered until both geometry and the studio can produce a frame", () => {
  const canvas = { style: {} }, events = [];
  const presentation = createFramePresentation({ canvas, renderMode: true, onFirstFrame: () => events.push("present") });
  const draw = () => { assert.equal(canvas.style.visibility, "hidden"); events.push("draw"); };
  assert.equal(presentation.draw({ hasVisibleModel: false, environmentReady: true }, draw), false);
  assert.equal(presentation.draw({ hasVisibleModel: true, environmentReady: false }, draw), false);
  assert.deepEqual(events, []);
  presentation.draw({ hasVisibleModel: true, environmentReady: true }, draw);
  assert.deepEqual(events, ["draw", "present"]);
  assert.equal(canvas.style.visibility, "visible");
  presentation.draw({ hasVisibleModel: true, environmentReady: true }, () => events.push("orbit"));
  assert.deepEqual(events, ["draw", "present", "orbit"], "orbit does not restart loading");
  presentation.draw({ hasVisibleModel: false }, () => events.push("clear"));
  assert.equal(events.at(-1), "clear", "clearing an existing model must not leave its old pixels visible");
});

test("Inspect can present without constructing a photographic environment", () => {
  const canvas = { style: {} };
  const presentation = createFramePresentation({ canvas, renderMode: false });
  assert.equal(presentation.draw({ hasVisibleModel: true }, () => {}), true);
  assert.equal(canvas.style.visibility, "visible");
});

test("a failed draw never uncovers the uninitialized canvas", () => {
  const canvas = { style: {} };
  const presentation = createFramePresentation({ canvas, renderMode: true, onFirstFrame: () => assert.fail("not drawn") });
  assert.throws(() => presentation.draw({ hasVisibleModel: true, environmentReady: true }, () => { throw Error("draw failed"); }));
  assert.equal(canvas.style.visibility, "hidden");
});

test("transition colors follow the destination studio, including custom and transparent backdrops", () => {
  for (const transparent of [false, true]) {
    const style = viewerTransitionBackdrop({ renderMode: true, renderConfiguration: { backdrop: { color: "#103040", transparent } }, viewerTheme: { sceneBackground: "#ffffff" } });
    assert.equal(style.backgroundColor, "#103040");
    assert.equal(style.color, "#e2e8f0");
  }
  assert.equal(viewerTransitionBackdrop({ renderMode: true, renderConfiguration: { backdrop: { color: "#e7e7e5" } } }).color, "#334155");
  assert.equal(viewerTransitionBackdrop({ renderMode: false, background: { solidColor: "#f1f5f9" } }).backgroundColor, "#f1f5f9");
});
