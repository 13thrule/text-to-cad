# Component publication profile — 2026-09-10

[Raw report](results/viewer-publication-phases-20260910.json.gz) records 24 bounded
component replacements through the current composition helper, React CadViewer
and WebGL renderer. It uses two real cached canonical meshes from repeated24,
replicated into 32 or 64 logical components with 16 occurrences each. Placements
and level identity changes are synthetic; meshing, Python source execution,
CadWorkspace and useCadAssets/network queues are excluded. This isolates display
publication cost and does not establish full-hand throughput or before/after gains.

The profiler wraps current source functions and React effects only in its temporary
esbuild output. Shipped files receive no profiling instrumentation. The report
retains the harness sources, original source hashes, instrumented hashes and bundle
hash. Chromium 148.0.7778.96 uses Metal on Apple M1 Max. Runtime fingerprints were
unchanged throughout 19:49:27.989–19:49:32.946 UTC, with no competing timed work.
There were no page or console errors and no allocation sampling or forced GC.

| Phase, median per replacement | 512 records | 1,024 records |
| --- | ---: | ---: |
| Reference composition | 0.30 ms | 0.45 ms |
| React queued to layout commit | about 0.8 ms | about 0.8 ms |
| Main scene effect | 6.80 ms | 10.55 ms |
| Shared mutable state | 2.55 ms | 4.05 ms |
| Surface-instance synchronization, seven calls | 3.45 ms | 6.55 ms |
| App clip synchronization, four calls | 2.40 ms | 4.65 ms |
| Later no-module effects pass | 1.70 ms | 3.25 ms |
| Later selector/clip pass | 0.75 ms | 1.30 ms |

Phase times are inclusive and nested: they must not be added. At 1,024 records,
queued-to-first-render time was 35.4–41.2 ms. The 512-record first replacement had
a 331.1 ms cold render outlier; its remaining replacements took 30–40 ms.
The first-frame observation follows renderer.render, not GPU completion.

Each update replaced 16 records, but applied material settings 1,040 times and
record transforms 3,088 times at the larger size. Only the 16 new records
incremented material versions, consistent with the separate material fix; total
material versions remained 1,024 after replacement. All records had zero rawColors
and zero hasVertexColors, with zero color-buffer allocation/version churn. The
canonical SURF adapter emits an empty colors array; uniform partColor metadata
does not create per-vertex colors. This does not measure a colored imported-GLB path.

The steady-disabled exploded-view guard was invoked twice per replacement and
took 0–0.1 ms in the larger fixture. A rest pose now skips clearing records,
reapplying transforms and publishing a new pose tick. Its four focused regressions
cover an initial rest pose, retained/new records at rest, interrupted collapse,
and residual matrices even when progress is zero. The guard still clears any
unfinished pose; it does not suppress active animation or collapse cleanup.

The scheduler has a 200 ms camera debounce, but no delay between successive LOD
jobs: its completion handler immediately evaluates the next component. Existing
sceneSync timing covers only the main scene effect, excluding later effects.
This profile supports reducing redundant clip/instance work before broader
incremental updates. A narrow next candidate is to update existing surface-instance
materials directly during clipping, as shared cadScene.syncClip already does,
while preserving reconciliation after visibility, color, deformation or transform
changes. No such change is included in this report.

## Matched clipping A/B

The subsequent [before](results/viewer-publication-phases-clip-before-20260910.json.gz)
and [after](results/viewer-publication-phases-clip-after-20260910.json.gz) reports use
the same fixture, 12 replacements at each size, and identical current source.
The before build restores only the old clipping behavior in the temporary esbuild
transform: clipping calls full instance reconciliation, and every material clip
call replaces its metadata object. The after build updates existing instance draw
materials directly and replaces clip metadata only when its enabled/count state
changes. This is a controlled source diagnostic, not an archived release or a
full-hand performance comparison. The raw reports retain the generic source-profile
qualification; this section describes the matched comparison explicitly.

Original hashes match for all nine instrumented source files; only modelRuntime.js
and cadScene.js have different transformed hashes. Both reports retain source
fingerprint `60432aba46a1a9aacaa80b5cf3049f630da07e58e91fc84e33d9cb640802bb3f`
at start and end. The material-version and exploded-view fixes are identical in
both builds. Before ran 19:57:58.327–19:58:02.218 UTC; after ran
19:58:13.817–19:58:17.645 UTC, without competing compute. Both private browsers and
servers closed successfully, with no page or console errors.

| Per replacement, median unless noted | 512 before | 512 after | 1,024 before | 1,024 after |
| --- | ---: | ---: | ---: | ---: |
| Instance synchronization calls, every sample | 7 | 3 | 7 | 3 |
| Clip metadata object replacements, every sample | 2,914 | 19 | 5,826 | 19 |
| Instance synchronization, total inclusive | 2.95 ms | 1.45 ms | 5.85 ms | 2.95 ms |
| Clip synchronization, four calls | 2.00 ms | 0.35 ms | 4.05 ms | 0.70 ms |
| Main scene effect | 7.05 ms | 6.10 ms | 11.55 ms | 10.00 ms |
| Later no-module effects pass | 1.70 ms | 1.30 ms | 2.70 ms | 2.20 ms |
| Later selector/clip pass | 0.60 ms | 0.20 ms | 1.20 ms | 0.40 ms |
| Reference composition | 0.40 ms | 0.35 ms | 0.60 ms | 0.60 ms |
| React queued to layout commit | 0.80 ms | 0.70 ms | 1.05 ms | 1.00 ms |
| Queued to first rendered frame | 32.60 ms | 31.20 ms | 39.00 ms | 36.05 ms |
| First rendered frame, full range | 27.3–50.8 ms | 25.6–48.1 ms | 33.7–57.8 ms | 34.4–43.7 ms |

The fixed reduction in work is clearer than the small frame-time difference:
these are single ordered, instrumented browser runs, and phase timings overlap.
The 1,024-record clip phase range is 3.4–6.3 ms before and 0.4–0.9 ms after.
All first replacements are retained in the statistics. No full-hand gain or
isolated speedup for either clipping change is inferred from this combined A/B.
The three remaining instance reconciliations follow visual-state updates and
preserve their existing behavior. Material/transform passes still traverse the
scene; the larger fixture applies material settings 1,040 times and transforms
3,088 times per replacement. Both variants retain 1,024 records and 64 instance
sets, increment only the 16 replacement material versions, and allocate no vertex
color buffers. This supports the clipping change without claiming that all
publication overhead is removed.

The 52 focused shared tests pass. The new regressions exercise clip enable,
offset and disable without invoking membership reconciliation; they preserve the
draw object, original instance slots, matrix/color arrays and their versions.
They also cover direct and nested runtime sets, duplicate set references,
disposed-set exclusion, a subsequent ordinary instance sync, and metadata
copy-on-change versus offset-only shader/material updates.

Reproduction uses the embedded `build.mjs`, `entry.jsx`, and `check.mjs` in each raw
report. Build/run with `PROFILE_CLIP_BASELINE=1` and `PROFILE_LABEL=clip-before`,
then rebuild/run with no baseline flag and `PROFILE_LABEL=clip-after`. The harness
is temporary and does not modify shipped sources or production assets. Focused
validation command:

```sh
node --test packages/cadgen-js/src/lib/viewer/modelRuntime.test.js \
  packages/cadgen-js/src/common/cadScene.test.js \
  packages/cadgen-js/src/common/cadSurfaceInstances.test.js
```
