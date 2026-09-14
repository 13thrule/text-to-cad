import assert from "node:assert/strict";
import test from "node:test";

import { resolveFileStatus } from "./fileStatus.js";

const ready = { hasFile: true, hasGeometry: true };

test("idle files and optional edit-feed states stay quiet", () => {
  assert.equal(resolveFileStatus(), null);
  assert.equal(resolveFileStatus(ready), null);
  assert.equal(resolveFileStatus({
    ...ready,
    showingPreview: true,
    editingState: { state: "done", saved: { tree: "saved" } }
  }), null);
  assert.equal(resolveFileStatus({
    ...ready,
    showingPreview: true,
    editingState: { state: "disconnected", error: "Connection closed" }
  }), null);
  assert.equal(resolveFileStatus({
    ...ready,
    showingPreview: true,
    editingState: { state: "building", revision: 3, preview: { revision: 3 } }
  }), null);
});

test("opening is authoritative for incomplete first loads, including partial geometry", () => {
  assert.deepEqual(resolveFileStatus({
    ...ready,
    opening: true,
    loadingTitle: "Loading components 4 of 12"
  }), {
    label: "Opening",
    title: "Loading components 4 of 12",
    tone: "info",
    busy: true
  });
});

test("updates stay busy only until the current preview is displayed", () => {
  assert.equal(resolveFileStatus({
    ...ready,
    opening: true,
    updating: true,
    loadingTitle: "Preparing replacement geometry"
  }).label, "Updating");

  assert.equal(resolveFileStatus({
    ...ready,
    updating: true,
    showingPreview: true,
    editingState: { state: "building", revision: 4, preview: { revision: 4 } }
  }), null);
});

test("failures distinguish opening from replacement while preserving diagnostics", () => {
  const diagnostic = "Invalid file header\nfull parser trace";
  assert.deepEqual(resolveFileStatus({
    hasFile: true,
    error: { message: diagnostic }
  }), {
    label: "Open failed",
    title: diagnostic,
    tone: "error",
    busy: false
  });
  assert.equal(resolveFileStatus({
    ...ready,
    error: { message: "Replacement decode failed" }
  }).label, "Update failed");
});

test("a failed save explains that the updated model remains visible", () => {
  assert.deepEqual(resolveFileStatus({
    ...ready,
    showingPreview: true,
    editingState: {
      state: "failed",
      error: "Disk full",
      revision: 5,
      preview: { revision: 5 }
    }
  }), {
    label: "Update failed",
    title: "The updated model is visible, but the STEP file could not be written.",
    tone: "error",
    busy: false
  });
});

test("warnings remain actionable while successful background work stays quiet", () => {
  assert.equal(resolveFileStatus({
    ...ready,
    error: { severity: "warning", message: "Saved model settings are unavailable." }
  }).label, "Model warning");
  assert.equal(resolveFileStatus({
    ...ready, opening: true,
    error: { severity: "warning", message: "Saved model settings are unavailable." }
  }).label, "Opening");
  assert.equal(resolveFileStatus({
    ...ready,
    editingState: { state: "done", previewUnavailable: true, saved: { tree: "saved" } }
  }), null);
  assert.equal(resolveFileStatus({
    hasFile: true,
    editingState: { state: "done", previewUnavailable: true }
  }).label, "Open failed");
  assert.deepEqual(resolveFileStatus({
    ...ready,
    qualityStatus: { state: "refining", title: "More detail is loading." }
  }), null);
  assert.deepEqual(resolveFileStatus({
    ...ready,
    qualityStatus: { state: "error", title: "Fine surfaces could not be loaded." }
  }), {
    label: "Limited detail",
    title: "Fine surfaces could not be loaded.",
    tone: "warning",
    busy: false
  });
});

test("the resolver emits only the approved filename labels", () => {
  const inputs = [
    { hasFile: true, opening: true },
    { ...ready, updating: true },
    { hasFile: true, error: "bad" },
    { ...ready, error: "bad" },
    { ...ready, qualityStatus: { state: "limited" } },
    { ...ready, error: { severity: "warning", message: "Missing settings" } }
  ];
  const allowed = new Set(["Opening", "Updating", "Open failed", "Update failed", "Limited detail", "Model warning"]);
  for (const input of inputs) {
    assert.ok(allowed.has(resolveFileStatus(input).label));
  }
});
