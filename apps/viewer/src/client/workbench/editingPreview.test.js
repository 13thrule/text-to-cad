import assert from "node:assert/strict";
import test from "node:test";
import { initialEditingPreview, reduceEditingPreview, editingPreviewEntry, editingPreviewLabel, previewGeometryChanged } from "./editingPreview.js";

test("an empty initial catalog is safe and geometry changes invalidate only the same file", () => {
  assert.equal(previewGeometryChanged(null, {}), false);
  assert.equal(previewGeometryChanged({}, {}), false);
  const prior = { file: "part.step", hash: "saved", preview: false };
  assert.equal(previewGeometryChanged(prior, { ...prior, hash: "preview", preview: true }), true);
  assert.equal(previewGeometryChanged(prior, { ...prior, file: "other.step", hash: "preview", preview: true }), false);
});

const update = (revision, tree, extra = {}) => ({ epoch: "a", revision, output: "/part.step", state: "building",
  ...(tree ? { preview: { tree, url: `/${tree}`, sequence: 1 } } : {}), ...extra });

test("new request preserves visible geometry until its preview arrives and ignores late older results", () => {
  const first = reduceEditingPreview(initialEditingPreview(), update(1, "old"));
  const pending = reduceEditingPreview(first, update(2));
  assert.equal(pending.preview.tree, "old");
  assert.equal(reduceEditingPreview(pending, update(1, "late")), pending);
  const ready = reduceEditingPreview(pending, update(2, "new"));
  assert.equal(ready.preview.tree, "new");
});
test("a daemon epoch change expires preview ordering and failed saves retain the visible model", () => {
  const first = reduceEditingPreview(initialEditingPreview(), update(99, "old"));
  const failed = reduceEditingPreview(first, update(100, null, { state: "failed", error: "Disk full" }));
  assert.equal(failed.preview.tree, "old");
  assert.equal(editingPreviewLabel(failed, true), "Disk full");
  const restarted = reduceEditingPreview(failed, { ...update(1), epoch: "b" });
  assert.equal(restarted.preview, null);
});
test("preview leaves the saved catalog immutable and waits for saved byte identity before switching back", () => {
  const saved = { tree: "saved-tree", documentHash: "bytes" };
  const state = reduceEditingPreview(initialEditingPreview(), update(1, "preview", { saved }));
  const entry = { file: "/part.step", kind: "assembly", hash: "old", sourceUrl: "/old.json", poseUrl: "/old.json" };
  const render = editingPreviewEntry(state, entry);
  assert.equal(render.hash, "preview");
  assert.equal(render.poseUrl, "");
  assert.equal(entry.hash, "old");
  assert.ok(editingPreviewEntry(state, { ...entry, hash: "saved-tree", documentHash: "other-bytes" }));
  assert.equal(editingPreviewEntry(state, { ...entry, hash: "saved-tree", documentHash: "bytes" }), null);
  const pending = reduceEditingPreview(state, update(2));
  assert.equal(editingPreviewEntry(pending, { ...entry, hash: "saved-tree", documentHash: "bytes" }), null,
    "starting the next edit must not revert the last visible saved geometry to an old preview");
  const newPreview = reduceEditingPreview(pending, update(2, "new-preview"));
  assert.equal(editingPreviewEntry(newPreview, { ...entry, hash: "saved-tree", documentHash: "bytes" }).hash, "new-preview");
  assert.equal(editingPreviewEntry(state, { ...entry, file: "relative/part.step" }).file, "relative/part.step");
});
