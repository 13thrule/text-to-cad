import assert from "node:assert/strict";
import test from "node:test";

import { resolveFileStatus } from "./fileStatus.js";

const ready = {
  hasFile: true,
  hasGeometry: true,
  qualityStatus: { state: "standard", title: "Standard detail is ready." }
};

test("no selected file has no filename status", () => {
  assert.equal(resolveFileStatus(), null);
});

test("ordinary saved STEP files stay Ready when the optional editing feed is disconnected", () => {
  assert.deepEqual(resolveFileStatus({
    ...ready,
    editingState: { state: "disconnected", error: "The build daemon is unavailable" }
  }), {
    label: "Ready",
    title: "The saved file is loaded.",
    tone: "neutral",
    busy: false
  });
});

test("build and load failures outrank usable geometry and loading activity", () => {
  assert.deepEqual(resolveFileStatus({
    ...ready,
    error: { severity: "error", summary: "Compile failed", message: "Fillet radius is too large" },
    activity: { loading: true, label: "loading mesh", title: "Loading CAD" }
  }), {
    label: "Build failed",
    title: "Fillet radius is too large",
    tone: "error",
    busy: false
  });

  assert.equal(resolveFileStatus({
    ...ready,
    error: "GLB parser failed"
  }).label, "Load failed");
});

test("failed STEP saves stay visible while their usable preview remains visible", () => {
  assert.deepEqual(resolveFileStatus({
    ...ready,
    showingPreview: true,
    editingState: {
      state: "failed",
      error: "Disk full",
      revision: 4,
      preview: { revision: 4 }
    }
  }), {
    label: "Save failed",
    title: "Disk full",
    tone: "error",
    busy: false
  });
});

test("an edit that fails before publishing its current preview is a build failure", () => {
  assert.deepEqual(resolveFileStatus({
    ...ready,
    showingPreview: true,
    editingState: {
      state: "failed",
      error: "Sketch constraint failed",
      revision: 5,
      preview: { revision: 4 }
    }
  }), {
    label: "Build failed",
    title: "Sketch constraint failed",
    tone: "error",
    busy: false
  });

  assert.equal(resolveFileStatus({
    hasFile: true,
    editingState: { state: "failed", error: "Model returned no shape", revision: 1 }
  }).label, "Build failed");
});

test("annotation warnings are metadata issues rather than load failures", () => {
  assert.deepEqual(resolveFileStatus({
    ...ready,
    error: {
      severity: "warning",
      title: "Annotations unavailable",
      message: "The annotation sidecar could not be parsed."
    }
  }), {
    label: "Metadata issue",
    title: "The annotation sidecar could not be parsed.",
    tone: "warning",
    busy: false
  });
});

test("edit queue, build, and save statuses reflect the live revision", () => {
  assert.equal(resolveFileStatus({
    ...ready,
    editingState: { state: "queued", revision: 3 }
  }).label, "Queued");

  assert.equal(resolveFileStatus({
    ...ready,
    showingPreview: true,
    editingState: { state: "building", revision: 3, preview: { revision: 2 } }
  }).label, "Building", "a retained older preview does not pretend the current revision is saving");

  assert.deepEqual(resolveFileStatus({
    ...ready,
    showingPreview: true,
    editingState: { state: "building", revision: 3, preview: { revision: 3 } }
  }), {
    label: "Saving",
    title: "The current live preview is visible while its STEP file is saved.",
    tone: "info",
    busy: true
  });
});

test("real build and loader activity use compact labels and preserve detailed tooltips", () => {
  assert.deepEqual(resolveFileStatus({
    hasFile: true,
    activity: {
      loading: true,
      label: "generating 14/20",
      title: "Tessellating components — phase 2/3 — 14 of 20"
    }
  }), {
    label: "Building",
    title: "Tessellating components — phase 2/3 — 14 of 20",
    tone: "info",
    busy: true
  });

  assert.equal(resolveFileStatus({
    hasFile: true,
    activity: { loading: true, label: "loading STEP module" }
  }).label, "Loading");
  assert.equal(resolveFileStatus({
    hasFile: true,
    activity: { loading: true, label: "building topology", title: "Preparing selectable topology" }
  }).label, "Loading", "background interaction preparation is not presented as a model build");
});

test("quality failures and limits are visible while background refinement stays quiet", () => {
  assert.equal(resolveFileStatus({
    ...ready,
    qualityStatus: { state: "error", title: "Surface adoption failed." }
  }).label, "Detail failed");
  assert.equal(resolveFileStatus({
    ...ready,
    qualityStatus: { state: "limited", title: "Additional detail did not fit in memory." }
  }).label, "Reduced detail");
  assert.deepEqual(resolveFileStatus({
    ...ready,
    qualityStatus: { state: "refining", title: "More detail is loading." }
  }), {
    label: "Ready",
    title: "The saved file is loaded.",
    tone: "neutral",
    busy: false
  });
  assert.deepEqual(resolveFileStatus({
    ...ready,
    activity: { loading: true, label: "refining detail" }
  }), resolveFileStatus(ready));
  assert.equal(resolveFileStatus({
    ...ready,
    qualityStatus: { state: "refining" },
    editingState: { state: "done", saved: { tree: "tree" } }
  }).label, "Saved");
  assert.equal(resolveFileStatus({
    ...ready,
    qualityStatus: { state: "high", title: "High-detail geometry is ready." }
  }).label, "Ready");
});

test("stable live states distinguish a validated save from an unsaved preview", () => {
  assert.deepEqual(resolveFileStatus({
    ...ready,
    showingPreview: true,
    editingState: { state: "done", saved: { tree: "tree", documentHash: "bytes" } }
  }), {
    label: "Saved",
    title: "The live preview is visible and its STEP file was saved.",
    tone: "success",
    busy: false
  });

  assert.deepEqual(resolveFileStatus({
    ...ready,
    showingPreview: true,
    editingState: { state: "done" }
  }), {
    label: "Preview",
    title: "Showing a live preview that has not been saved to STEP.",
    tone: "info",
    busy: false
  });
});

test("lost and disconnected live previews remain honest without affecting static files", () => {
  assert.equal(resolveFileStatus({
    ...ready,
    editingState: {
      state: "done",
      error: "Preview geometry is no longer available in the cache",
      previewUnavailable: true,
      saved: { tree: "tree", documentHash: "bytes" }
    }
  }).label, "Preview lost");

  assert.deepEqual(resolveFileStatus({
    ...ready,
    showingPreview: true,
    editingState: { state: "disconnected", error: "Connection closed" }
  }), {
    label: "Offline",
    title: "Connection closed",
    tone: "warning",
    busy: false
  });
});

test("every emitted badge label stays within the one-to-two word contract", () => {
  const cases = [
    ready,
    { hasFile: true },
    { ...ready, error: "bad" },
    { ...ready, error: { kind: "build", message: "bad" } },
    { ...ready, editingState: { state: "failed" } },
    { ...ready, editingState: { state: "queued" } },
    { ...ready, editingState: { state: "building" } },
    { ...ready, activity: { loading: true, label: "loading meshes 2/4" } },
    { ...ready, qualityStatus: { state: "preview" } },
    { ...ready, qualityStatus: { state: "refining" } },
    { ...ready, qualityStatus: { state: "limited" } },
    { ...ready, qualityStatus: { state: "error" } },
    { ...ready, showingPreview: true, editingState: { state: "done" } },
    { ...ready, editingState: { state: "done", saved: { tree: "tree" } } }
  ];

  for (const input of cases) {
    const result = resolveFileStatus(input);
    assert.ok(result.label.split(/\s+/).length <= 2, result.label);
  }
});
