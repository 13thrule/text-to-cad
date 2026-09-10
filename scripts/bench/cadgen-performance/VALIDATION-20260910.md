# Integration validation — September 10, 2026

Implementation branch: `codex/tendon-hand-performance`, based on the reviewed
preview branch at `7aa3e85be76f305437abd3d7aba26e38b28e43cb`. This record covers
functional and lifecycle checks. Concurrent test activity makes their elapsed
times unsuitable for performance comparisons; the isolated CPU study is in
[RESULTS-20260910.md](RESULTS-20260910.md).

## Browser behavior

[First save](results/preview-first-save-20260910.json): Chromium rendered all
nine parts from a preview while the output STEP did not yet exist, then loaded
the distinct saved tree. No page errors occurred. Initial tessellation-cache
404s were cache misses and were filled normally; there were no failed preview
or geometry endpoints.

[Warm edit and failure](results/preview-edit-failure-20260910.json): changing
the carrier diameter changed the saved STEP bytes and tree. All nine occurrences
remained displayed throughout the replacement. A subsequent deliberate model
exception produced a visible failure, retained the last complete scene, and
left the saved STEP byte-for-byte unchanged. Saved-file/Follow-edits toggling
worked. The fixture source was restored and successfully rebuilt afterward.

[Repeated-file lifecycle](results/viewer-lifecycle-20260910.json): a 24-occurrence
fixture uses two surface instance sets and two edge instance sets. The first
explicit topology demand changes selector entries from zero to one; this run
used tree expansion after the canvas sweep missed geometry. The inspector
resolved the occurrence, and 23 unaffected surfaces remained instanced through
selection. Six same-tab sidebar switches, hover/selection and orbiting produced
no page errors or memory limitations. After explicit browser GC:

| Settled file | GPU buffer bytes | GPU buffers |
| --- | ---: | ---: |
| Repeated assembly, each return | 21,668 | 17 |
| Planetary assembly, each return | 265,500 | 48 |

Buffer-deletion counts rose 81 → 150 → 219 across repeated returns, confirming
release of old allocations. Worker-resident estimates returned to zero after
all settled loads, including overlapping LOD work. JavaScript heap grew modestly
while paths warmed; this short test proves a GPU/resource plateau for these
fixtures, not absence of every possible long-session leak. Intentional model
switches aborted obsolete requests; those cancellations are recorded.

An earlier [medium-file smoke](results/medium-browser-20260910.json) measured
first visible geometry at about 537 ms and peak largest-renderer RSS at about
291 MiB. It predates the final admission-status, instance-accounting and idle
cleanup corrections and is retained as context, not a final release benchmark.
The very large hand was not rerun.

### Final browser confirmation

[Cold/cached loads](results/viewer-cold-warm-20260910.json) and the
[final lifecycle/orbit run](results/viewer-lifecycle-final-20260910.json) use
runtime `947f1daded11eab5f0a432cad32b486b88cd5962`. No concurrent task builds,
tests or other task browsers ran during these measurements. Both STEP files
were copied to a source-free directory. The private store retained canonical
document/component indexes but omitted model, output and mesh indexes; model
and output indexes remained absent after all browser runs. Byte digests match
the originals. Thus these checks also exercise saved-document independence.

| Nine-part assembly | Empty mesh index | Populated mesh index |
| --- | ---: | ---: |
| First geometry frame proxy | 367 ms | 263 ms |
| Largest renderer peak RSS | 279 MiB | 168 MiB |

Each run starts a fresh browser profile. These are one cold/cached pair, not
statistical distributions. The first-geometry probe observes a published
component followed by WebGL draw calls in a browser frame, not a GPU completion
fence. The harness's full-load observation polls at 500 ms, so its roughly
659/656 ms readings are too coarse to compare full-load latency. Both runs
display all nine parts and have no page exceptions or crashes. The cold run
logs nine resource-404 messages while populating the initially empty mesh
cache; the cached run logs none.

The final lifecycle run passes all eight assertions. Repeated returns still
settle at 21,668 GPU buffer bytes / 17 buffers; deletion counts increase
78 → 147 → 216, and worker-resident estimates return to zero. First explicit
topology demand uses tree expansion and observes selector readiness in 142 ms,
including automation overhead. Six same-tab switches observe final publication
in 234–286 ms before the separate 900 ms settling period. During a 5.05-second
active orbit of the repeated assembly, 603 measured browser frame intervals
have p50 8.3 ms, p95 9.9 ms and maximum 10.3 ms; per-frame draw count is 10.
The viewport is 1400×900 with Metal and default LOD settings. These intervals
measure browser presentation cadence, not isolated GPU execution, and do not
establish large-hand frame rate or improvement over a pre-instancing baseline.

## Tests and packaging

- Cadgen package Python suite: 1,373 tests pass, including the viewer backend.
- CAD skill suite: 287 tests pass after updating bound-sidecar fixtures; the
  snapshot CLI module also passes all 120 focused cases.
- Other Python skill suites: 144 tests pass across Bambu, Viewer, DfAM, DXF,
  G-code, SendCutSend and step.parts.
- Global repository policy suite: 126 tests, one skipped, no failures.
- cadgen-js: 931 tests pass after the final worker-cancellation patch. Viewer
  client: 372 tests pass on that patch.
- Production viewer and docs checks pass. The docs check required local
  dependency files because Turbopack rejects an external node_modules symlink.
- Canonical version/skill pins remain 0.5.1; no release bump.
- The wheel content gate finds all required runtime assets. A disposable venv
  imports cadgen and its Node/browser assets from the installed wheel, with no
  repository source on its import path. Heavy CAD dependencies are reused via
  a later site-packages entry without processing the editable install.
- That installed wheel builds and reuses a two-part annotated hinge, verifies
  schema-7 binding to actual STEP SHA-256, inspects it, re-emits STEP, exports
  GLB, renders a posed PNG, and encodes three animation frames as MP4.

Final concurrency review added three supervisor-level coalescing regressions:
followers cannot hide an owner's preview, finish before its full completion,
or become the producer after success/failure. Those and adjacent daemon/feed
tests pass (73 total). A fourth added regression copies and renames a STEP,
forbids model/output reads, text parsing and compile submission, then reuses
the document tree and reconstructs its canonical geometry. Its four-test
module, including the saved-reader snapshot, passes.

Worker cancellation has 32 focused passing tests plus independent fault probes
for queued/cache-waiting aborts, late replies, all-slot failure, surviving-slot
dispatch and idle release. Each worker owns one synchronous request; active
cancellation replaces that isolate, with other callers preserved. Failed
accepted worker jobs propagate an error without moving tessellation onto the
main thread. This final patch was independently reviewed before bundling.

The final bundle freshness check and docs build pass again after cancellation.
The [final wheel check](results/packaging-final-20260910.json) starts with clean
setuptools staging, avoiding obsolete hashed assets from earlier local builds.
All 28 packaged runtime files match the current generated paths and bytes
exactly. Reinstalling that wheel and repeating the six installed-package
build/reuse/inspection/export checks passes. Task-owned viewers and the preview
daemon are stopped.
Runtime changes are committed through `947f1dade`; the plan records the subsystem
commits. These checks do not establish the unmet 250 ms preview target,
large-hand targets, hard process-memory limits, or native-mesher quality parity.
