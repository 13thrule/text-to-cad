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

## Tests and packaging

- Cadgen package Python suite: 1,373 tests pass, including the viewer backend.
- CAD skill suite: 287 tests pass after updating bound-sidecar fixtures; the
  snapshot CLI module also passes all 120 focused cases.
- Other Python skill suites: 144 tests pass across Bambu, Viewer, DfAM, DXF,
  G-code, SendCutSend and step.parts.
- Global repository policy suite: 126 tests, one skipped, no failures.
- cadgen-js: 922 tests pass. Viewer client: 372 tests pass.
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

The final bundle freshness check passes. Runtime changes are committed through
`43b233233`; the plan records the subsystem commits. These checks do not establish the unmet 250 ms preview target,
large-hand targets, hard process-memory limits, or native-mesher quality parity.
