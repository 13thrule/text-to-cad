# Integration validation — September 10, 2026

Implementation branch: `codex/tendon-hand-performance`, based on the reviewed
preview branch at `7aa3e85be76f305437abd3d7aba26e38b28e43cb`. This record covers
functional and lifecycle checks. Concurrent test activity makes their elapsed
times unsuitable for performance comparisons; the isolated CPU study is in
[RESULTS-20260910.md](RESULTS-20260910.md).

## Current checkpoint

The branch remains under active implementation. Ongoing acceptance uses the
nine-part planetary assembly and modest repeated-parts fixtures. The user
stopped further tendon-hand stress tests on September 11; prior hand results
remain historical evidence, without a further full-hand acceptance gate.

On `8971f760d`, **1,015 shared JavaScript tests and 486 viewer tests pass**.
The changes cover unchanged selection identity, exact mesh/selector publication,
reservation ownership through scene adoption, partial-failure teardown,
restoration and stale-context rejection. Independent review passed. Production
bundling and its freshness gate pass. Repository policy checks pass with one
skip; two local-IPC modules were rerun with the required sandbox allowance.
Docs checks pass, with the Next build rerun with local helper ports enabled.
The canonical version and skill pins remain `0.5.1`.

The latest broad Python run passed **1,593 package tests**, including the viewer
backend and bounded sibling preparation. Its 334.801-second duration is
functional validation, not a benchmark. Python behavior is unchanged by
`8971f760d`. The 24 browser-harness helper tests pass at their previous
checkpoint and were rerun successfully after the alert fix; adaptive satisfaction
requires settled quality and no unmet targets.

The [installed-wheel checkpoint](results/installed-wheel-8971f760d-20260911.json.gz)
passes on `8971f760d`: 182 Python files and 29 runtime files match source,
wheel and isolated installation; all served viewer assets and four workers
match the installed bytes. Cold/warm decorated builds retain identical outputs
and exact pins. After deleting source and the build store, source-free STEP
inspection, STEP/STL/GLB export, posed PNG and a three-frame MP4 pass with
model/output index reads forbidden. Cold import also forbids code-index reads.
The generated and cold-imported document trees agree. The posed image and
first/last video frames were visually inspected, and the owned validation
viewer exited normally. This is a functional packaging check, not a timing
measurement. The [preceding wheel checkpoint](results/installed-wheel-2709968dc-20260911.json.gz)
and [earlier wheel proof](results/installed-wheel-current-20260910.json.gz) remain
separate historical evidence. Later runtime changes require relevant validation.

The [integrated medium adaptive check](results/viewer-nine-adaptive-ownership-integrated-20260910.json.gz)
passes all 13 assertions with no page/HTTP errors and all requested detail
targets settled. Peak renderer RSS is 210.56 MiB; orbit frame interval p95 is
8.7 ms. The complete nine-part view was visually reviewed. The [integrated ownership checks](VIEWER-OWNERSHIP-INTEGRATED-20260910.md)
pass 90 assertions across the adaptive and seven failure/interaction cases.
The alert-only follow-up on `c07488e1d` passes 15 more assertions: after actual
restoration the obsolete error overlay clears while selection and exact
mesh/selector pairing remain. Its 486 viewer tests and canonical bundle/check
pass. Injected delays and faults are functional probes, not performance measurements.
Bounded grouping is committed in `9be4f5424`. The integrated client passes
**506 viewer tests and 1,015 shared JavaScript tests**, plus canonical bundling
and freshness checks. The [moderate batch study](VIEWER-LOD-BATCH-MODERATE-20260910.md)
passes nine alternating measured runs. Two subsequent combined-main functional
checks pass **32 assertions**: exact two-component restoration across all 24
occurrences with the selected face and matching selectors, and delayed-reply
rejection across a model switch. All reservations, staged buffers and workers
drain. The restoration close-up and complete planetary smoke were visually
reviewed. Existing user viewers remain running; private measurement instances
closed. The [viewer wheel check](results/installed-wheel-viewer-9be4f5424-20260911.json.gz)
passes for `9be4f5424`: all 22 client assets match the source build, fresh staging,
wheel, isolated installation and actual HTTP responses. A supplemental capture
records module paths, hashes, import paths and kernel-free state inside the exact
server process used for those HTTP checks. Both owned servers exited normally.
This asset-only check does not replace full Python/export validation after
subsequent backend changes.

The [matched selection retention study](VIEWER-SELECTION-RETENTION-20260911.md)
shows the same 246 detail adoptions retaining 9 workspace contexts instead of
503, and post-collection backing storage falling from 19.953 to 3.393 MB.
The isolated selection fix also passed the last permitted hand L1 test at
1,482 MiB, with all 866 components and 3,259 occurrences. That historical
result does not validate later runtime changes or cold fine-detail meshing.
See the [browser comparison](VIEWER-NINE-BEFORE-AFTER-20260910.md) and
[memory investigation](VIEWER-MEMORY-DIAGNOSTIC-20260910.md) for the earlier
failed checkpoints and the exact cache/measurement boundaries.

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

## Resumed implementation validation

The earlier record describes the first implementation, not a completed plan.
The resumed work adds native mutation integrity, complete pin checks, retained
revision failure coverage, coalesced-consumer lifetime protection, exact browser
reuse across revisions, initial coarse loading, and corrected progressive
failure and worker-memory accounting.

- Full package/skill Python suites: **1,872 tests pass**, including 1,441 cadgen
  tests and its viewer backend. The expanded cases cover native Add/Remove and
  orientation edits, descendant metadata, pinned child updates, cache deletion
  and GC, all save publication boundaries, and coalesced producer disconnects.
- Shared JavaScript: **945 tests pass**. Viewer: **398 tests pass** after the
  final per-worker accounting and completed-scene reporting changes.
- Global policies: **126 tests, one skipped**, no failures. Bundle generation,
  freshness and docs build pass. Python and viewer suites were rerun after the
  final dependency, component-route and diagnostic changes.
- The benchmark completion gate rejects partial, missing and inconsistent
  component counts, stale scene synchronization and incomplete rendered
  occurrence counts. Its ramp includes clears/restarts. Node bounds page probes and reports a drained terminal
  memory denial promptly instead of waiting for the entire timeout.

The [real preview-reuse check](results/preview-reuse-20260910.json) uses the
nine-part fixture, two geometry edits and a fresh browser. Each revision changes
one component. There are no asset requests for the other eight, and no saved-tree
geometry request while Follow edits retains the authored preview. Switching to
Saved file requests the canonical saved tree; its document hash matches actual
STEP bytes. Both edits retain all nine displayed components and there are no
page errors. LOD refinement is disabled to isolate exact revision reuse. This
is functional evidence, not a latency result: broader Python tests ran at the
same time. The report includes the exact built asset hashes.

Three earlier hand attempts are failed or partial evidence. The third keeps
56 components visible after admission fails, with no late publication/retry
loop, but still does not complete. Its largest-renderer peak is about 1,207 MiB.
Subsequent small regressions reproduce real slot releases during an awaited
reclaim and verify that a completely replaced worker pool starts with no stale
high-water charge. Partial reclamation conservatively preserves the estimate.
The hand milestone remains separate from those passing unit tests.

The final [cold hand](results/hand-route-final-20260910.json) and
[cached hand](results/hand-route-cached-20260910.json) complete all 866 components
and 3,259 rendered occurrences in 67.86 and 18.77 seconds. First-geometry frame
proxies are 2.12 and 1.64 seconds. Neither has a page exception or crash; cold
cache resource-404s are expected and disappear in the cached run. Peak largest
renderer RSS is 1,965 and 1,890 MiB, leaving little headroom below 2 GiB. Both
use initial coarse detail with refinement disabled. They do not validate
full-resolution interactive loading, large-hand orbiting, or a hard RSS limit.

The [resumed wheel check](results/packaging-resumed-20260910.json) rebuilds clean
setuptools staging and verifies all 28 runtime files against generated paths
and bytes. Installed-package validation starts with an empty disposable store,
asserts a real cold build followed by a warm hit, then inspects, re-emits STEP
and exports GLB. The same wheel renders a posed PNG and a three-frame MP4;
the PNG was visually inspected. No repository source supplies cadgen to that
environment. The task-owned viewer has been stopped.

The passing suites do **not** prove every store invariant. A new tiny diagnostic
confirms a pre-existing source-PBR/document-key collision and generated versus
cold-import naming/grouping mismatch. These were unresolved at that checkpoint. See the original
[evidence](results/material-document-identity-20260910.json) and the subsequent
[implemented repair](SAVED-IDENTITY-FOLLOWUP.md). The new phase is documented
separately below; the earlier test totals and wheel used schema 7.

The hand and warm-build reports match committed runtime `ddd5817ec` by a
post-commit fingerprint check. A later conservative module-alias guard,
`d14d7f992`, changes dependency classification only; it introduces no browser or
kernel-performance change. The wheel was rebuilt and its installed checks
repeated on that commit. The warm study retains source bytes/timestamps and
still misses the preview target. No release version change or push is part of
this integration.

## Saved-document identity repair

This phase implements the [saved identity repair](SAVED-IDENTITY-FOLLOWUP.md).
It uses one canonical parsed-scene path for generated and imported documents,
separate authored result and document trees, schema-8 bound PBR annotations,
complete face-color component identity, private material/topology ownership,
and coherent document-hash/tree selection across readers. It closes the
original defect; it does not close the remaining performance targets.

The [suite record](results/validation-appearance-20260910.json) identifies each
completed check. The final runtime fingerprint is
`f47265c3decbf8ed665984eb0bfd4f8228f304c6e070efa75f9371139c9d07fb`.
The older hand and warm reports above retain their original fingerprints.
The hand was not rebuilt for this repair, following the request to keep ongoing
work on modest assemblies.

- Package Python: **1,481 tests pass**, including the viewer backend.
- CAD skill: **290 tests pass**. Other skill suites: **144 tests pass**.
  The aggregate is **1,915 package/skill tests**; suites were completed through
  targeted reruns, not one uninterrupted green wrapper invocation.
- Shared JavaScript: **951 tests pass**. Viewer client: **398 tests pass**.
- Global policy suite: **126 tests, one skipped**, no failures. The final
  encoding/package-boundary check passes another seven focused cases.
- Runtime bundle generation, viewer production build, final bundle freshness,
  docs check, canonical version and skill pins pass. `VERSION` remains 0.5.1.
- The final [wheel record](results/packaging-appearance-20260910.json) verifies
  all **28** runtime files and **181** Python files against this checkout's
  exact bytes, from clean setuptools staging. Six installed commands pass:
  installed-path assertion, cold build, warm hit, inspection, STEP reemit and
  bare GLB export. Cadgen comes from the wheel; heavy dependencies are reused
  through a later site-packages entry without loading the editable install.
- That same wheel renders an `open`-pose PNG, visually inspected, and a
  three-frame 640×480 MP4. ffprobe confirms 10 fps and 0.3 seconds. These are
  functional packaging checks, not performance comparisons.

The full run exposed two test-maintenance issues after the production repair:
robot-description tests assumed temporary files always lived outside the repo,
and two imported-scene tests still mocked the old packaging function. Fixtures
now live under `models/tmp`, path assertions check the actual referenced file,
and mocks assert the exact canonical scene/preload contract. No production
fallback was added to satisfy these tests. Earlier sandbox-only socket failures
were rerun with local IPC enabled. The logs retain those failed attempts.

The [real saved-appearance browser check](results/saved-appearance-browser-20260910.json)
changes a one-part fixture's bound sidecar, then removes it. Actual WebGL
roughness/metalness/clearcoat change from 0.18/0.82/0.65 to 0.86/0.06/0.05,
then to defaults 0.58/0.02/0.12. STEP and canonical tree identities stay fixed;
no new SURF or tessellation response body is requested on either change. The
viewer performs a metadata HEAD probe, renders the one occurrence throughout,
and reports no page errors. This browser check predates the last Python-only
component identity and coherent-reader fixes; its JavaScript is unchanged.
It is evidence of material composition and reuse, not final-runtime latency.

Regression coverage additionally verifies identical STEP files with different
PBR sidecars, source/store deletion with real GLB export, exact nested group
mapping, red/blue face-color variants through moved pins and cold imports,
metadata deletion/overrides, reemit output-pair recovery, and file replacement
between geometry selection and annotation/export setup. An independent final
contract review found no critical issue in the integrated publication/read paths.
Known bounds remain: explicit-GC loss can invalidate a retained view, STEP and
sidecar replacements are separate atomic operations, and the existing file-hash
memo assumes a byte change also changes mtime or size.

At this checkpoint the plan remained **in progress**. Later work below replaces
shared live-shape retention with canonical bytes and private reconstruction;
automatic-export coalescing does not apply to the explicit-build flow. The
native study supports retaining JS; it does not establish native visual or
interactive parity.

## Locked-dependency integration checkpoint

The installed dependencies used by the historical browser checks included
three-mesh-bvh 0.8.0, although the repository lock requires 0.9.14. Those reports
now retain that actual-version qualification. Their numeric results are not
validation of 0.9.14. Isolated, offline lockfile installs in this worktree now
resolve Three.js 0.185.1, three-mesh-bvh 0.9.14 and React 18.3.1. The primary
checkout and both lockfiles are unchanged. Browser fingerprints record actual
resolved dependency paths, versions and package-manifest digests.

- Shared JavaScript: **974 tests pass** with the locked dependencies.
- Viewer client: **409 tests pass** with the locked dependencies.
- Production bundle generation and `bundle.sh --check` pass after those tests.
- The package Python suite passed **1,536 tests**, including the viewer backend,
  with exact-output readback reuse and the 768 KiB extraction crossover. This
  precedes the subsequent live vertex-hash correction and source-free corrupt
  object repair; those changes require their own validation.

Full-hand canonical-detail acceptance, matched final repeated and unseen edit
measurements, and a fresh installed-wheel check remain pending. Passing these
test suites does not establish the remaining performance targets.

The final backend integration then passed **1,545 package Python tests** in
368.903 seconds, including the viewer backend. It includes live native vertex
hashing, actual topology-shape classification for protected extrusion inputs,
operation-cache salt 6, and source-free repair of corrupt or unreadable cached
objects. The targeted factory regression verifies cold, RAM and disk results
have private geometry and equivalent bytes and wrapper attributes. The original
profile remains unchanged and no memo fallback is introduced. Nine-part
cold/warm geometry also remains valid and byte-identical.

The repository policy suite passed **126 tests with one skip**; docs production
checks and the canonical 0.5.1 version/pin check passed. Subsequent browser-only
instance and worker changes require separate JavaScript, browser and bundle
validation; these Python results are not claims about those later changes.

## Surface worker and instance retention checkpoint

The integrated shared runtime passes **992 JavaScript tests** and the viewer
passes **409 client tests** with the isolated locked dependencies. This includes
retained instance groups, direct visibility/deformation/material updates,
virtualized assembly rows, unchanged composition reuse, and the surface BVH
worker's admission, stale-result rejection, cancellation and exact hit tests.
The focused worker checks also execute the real worker entry in a Node worker
thread; browser worker latency still requires the measured browser check.

`scripts/bundle/bundle.sh` and `--check` pass. Vite emits the dedicated
`raycastBvhWorker-Bx8Ori6S.js` asset, and the viewer's main entry is
`index-7SVkujAV.js`. The snapshot renderer does not import this interactive
worker path, so it needs no extra worker route. All 1,545 backend test results
above still apply: no Python runtime changed after that suite. The current
full-hand and installed-wheel gates remain pending.
