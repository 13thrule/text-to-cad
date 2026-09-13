# Cadgen and Viewer review — 12 September 2026

Warm generation and editing improved substantially against main. Unchanged
builds fell from about 2.6–2.7 seconds to 0.11–0.13 seconds; edits that actually
change geometry improved by 2.9–14.1× in these fixtures. Warm normal-CAD
snapshots improved by about 1.5×. Cold rendering is **not uniformly faster**:
the 118-occurrence iris becomes visible sooner but takes 35% longer to finish
loading every part at standard detail.

This is a review and measurement checkpoint, not evidence that all performance
work is finished or that cadgen has achieved FreeCAD parity.

## Comparison and method

- Before: frozen `main` commit `3e4dfdeef2cbd5804c369592b59620132188a150`.
- After: `codex/tendon-hand-performance`, starting at
  `10b90215febea61b01c258cf04f33dbb39fe7dc5`, plus the fixes recorded below.
  Raw evidence includes source fingerprints for the measured phases.
- Apple M1 Max, 64 GiB RAM, macOS 26.5.1, Python 3.13.13,
  build123d 0.11.1, cadquery-ocp 7.9.3.1.1, Chromium 151.0.7922.34.
  Main and branch used the same dependency installations and hardware.
- Generation measures the public `python model.py --json` command from process
  start through exit, including IPC and saving the requested STEP. It does not
  measure only the Python function or an OCCT operation.
- Independent stores and identical source bytes per revision; one empty-store
  build and three samples per warm scenario. Each changed value was previously
  unseen. Before/after order was interleaved. Headline warm values are medians.
- “Cold” means an empty application store and a new model worker, not a flushed
  filesystem cache or a guaranteed new daemon supervisor. The initial harness
  attempted an obsolete stop command; its return code did not establish a
  supervisor restart. New model workers and empty stores were verified.
- Timed studies ran serially, apart from normal desktop activity. Full-suite
  and installed-wheel smoke timings are functional checks, not benchmarks.
- No giant tendon-hand or other five-minute generation was rerun for this
  review. The largest fresh browser fixture was a 12 MiB iris assembly with
  91 unique components and 118 occurrences.

All **80 generation commands succeeded**. All **40 before/after pairs had
identical model-source hashes and byte-identical STEP output**. This controls
geometry correctness; it does not imply pixel-identical viewport output.

## Generation and warm editing

Seconds, before → after. Cold is one sample; other columns are three-sample
medians. “Unchanged” is a warm rerun without an edit, not an incremental edit.

| Model | Empty-store generation | Unchanged warm build | Warm geometry edit | Warm placement edit |
| --- | ---: | ---: | ---: | ---: |
| Drilled plate, 1 part, 21 KiB STEP | 6.278 → 3.375 | 2.705 → 0.118 | 2.690 → 0.191 | 2.679 → 0.190 |
| Drilled plates, 24 parts, 72 KiB STEP | 5.139 → 2.637 | 2.609 → 0.112 | 2.696 → 0.257 | 2.687 → 0.259 |
| Procedural planetary, 9 parts, 2.2 MiB STEP | 6.217 → 3.768 | 2.670 → 0.132 | 3.138 → 1.077 | 3.135 → 1.049 |
| Imported planetary STEP, 9 parts | 6.328 → 5.862 | 2.576 → 0.121 | 3.087 → 0.693 | 3.202 → 0.676 |

The corresponding warm speedups are **20–23× unchanged**, **2.9–14.1× for
geometry edits**, and **3.0–14.1× for placement edits**. Procedural cold builds
improved 1.65–1.95×; importing the planetary STEP improved only 1.08×.

The plate edit changes one hole radius or one plate's Z placement. The planetary
edit changes the carrier diameter or placement. The imported case reads the
same saved STEP and replaces or moves its carrier. These are ordinary `@step`
models; they do not require authors to import a new cache utility or opt into
new component decorators.

Much of the gain comes from avoiding caller-side kernel startup, rehydration
and unnecessary work, while retaining the warm worker and cached outputs.
These figures do **not** mean OCCT booleans became 20 times faster. Flat model
functions can still rerun their source operations for a placement change;
explicit dependency/component boundaries offer further reuse.

The review bumps only model-record admission to schema 6. Existing records from
older builds are not trusted because they cannot prove declaration-time input
hashing, so the next source invocation rebuilds once. Immutable geometry,
SURF/TESS artifacts and saved-document mappings remain valid. The warm numbers
above describe steady-state reuse after that one-time cutover.

## Rendering models to snapshots

Normal CAD snapshots, **without `--render`**, at 1200×900. Each call starts a
fresh CLI process and browser. “Warm” reuses derived artifacts on disk.

| Model | First snapshot after generation | Warm snapshot median | Fresh generation + first snapshot |
| --- | ---: | ---: | ---: |
| Drilled plate | 1.672 → 3.470 s | 1.659 → 1.106 s | 7.126 → 6.756 s |
| 24 drilled plates | 1.642 → 3.452 s | 1.680 → 1.119 s | 6.667 → 6.076 s |
| Planetary assembly | 1.674 → 4.440 s | 1.685 → 1.155 s | 7.864 → 8.100 s |

Warm snapshots are **1.46–1.50× faster**. First snapshots alone are slower:
surface derivation has moved out of generation and onto first display, which
can also start an artifact worker. Counting generation and first snapshot
together makes the tradeoff visible: 5–9% faster for the plates, 3% slower for
the planetary assembly. The setup-generation times in this table were measured
in a separate fresh-store run immediately before these snapshots.

The review initially measured a branch regression of roughly 3.7 seconds for a
warm snapshot. Profiling traced it to dispatching browser orchestration through
an extra worker that eagerly imported the kernel. Snapshot orchestration now
runs in the kernel-free caller; missing STEP compilation and surfaces still
use the artifact pool. The table above was rerun after that fix. The initial
samples are preserved separately as `snapshotsBeforeRoutingFix`.

## Browser load and interaction

Default Inspect/CAD view, fresh browser contexts, 1280×900, DPR 1, Metal-backed
Chromium. First visibility is the first actual default-framebuffer triangle
draw after publishing model placement; this is **not** a compositor paint or
GPU-completion measurement. Main and branch use their own default tessellation
policies, so these are product-default comparisons rather than matched-mesh
benchmarks.

| Model | Cold first visible geometry | Warm first visible geometry, median |
| --- | ---: | ---: |
| Drilled plate | 3.798 → 3.001 s | 205 → 199 ms |
| 24 drilled plates | 2.289 → 6.267 s | 223 → 222 ms |
| Planetary assembly | 7.733 → 8.206 s | 268 → 227 ms |
| Iris, 118 occurrences | 12.208 → 8.004 s | 587 → 237 ms |

Cold is one sample per model. The small-model study shares a daemon across
successive fixtures, so kernel warmth can differ from cache warmth. The cold
24-plate and planetary regressions are real observations, but need repeated
cold trials before assigning a stable percentage to them.

The iris requires a separate completeness check:

| Iris milestone | Before | After | Interpretation |
| --- | ---: | ---: | --- |
| Cold, first geometry | 12.208 s | 8.004 s | Earlier partial scene |
| Cold, all parts and standard detail | 12.254 s | 16.571 s | **35% slower** completion |
| Warm, first geometry, median | 587 ms | 237 ms | 2.47× earlier visibility |
| Warm, all parts and standard detail, median | 623 ms | 673 ms | Similar; after is about 8% slower |

The complete gate checks **91 loaded components, 118 scene occurrences and
settled standard detail** on the branch. Main publishes its complete scene
atomically. An earlier iris probe mistakenly treated a settled partial subset
as completion; that raw study is retained but excluded from these results.

Orbit frame intervals were approximately **8.3 ms median on both revisions**;
the tested models do not demonstrate a meaningful interaction-FPS improvement.
The intervals describe browser presentation cadence, not GPU execution time.
No JavaScript exceptions occurred in the measured browser runs. Triangle
counters in the raw probe include edge quads on the branch; old native line
draws do not contribute triangles, so the counters are not a surface-quality
or geometry-complexity comparison.

The branch's iris display was resident without selector, face-ID, picking or
BVH allocations before inspection. Its own accounting estimated about 4.79 MiB
of display data. There is no equivalent baseline accounting probe, so this is
not evidence of a particular memory-reduction factor.

## Review findings and fixes

| Finding | Fix and verification |
| --- | --- |
| Warm STEP snapshots paid for an unnecessary kernel worker | Keep orchestration kernel-free; delegate only missing artifact derivation. Preimport boundary tests, cold foreign STEP snapshot and fresh before/after snapshot measurements passed. |
| A declared data file could change during a build and have its later bytes recorded as the source of stale geometry | Capture its hash at first declaration, preserve that hash through STEP and DXF closure publication. Mutation-during-build regressions passed. A path-returning API cannot make an author's later separate file read atomic; this constraint is documented. |
| Animation export could hash a module, then execute changed module text after mesh preparation | Execute the same immutable text snapshot used by the variant key; isolate temporary source outside the store. An animation-only key salt rejects old potentially contaminated export entries without changing geometry/static mesh keys. Source-swap, reuse and cleanup tests passed. |
| Incremental assembly updates could retain old children when a subassembly becomes a leaf | Reuse prior child-array identity only when the prior array is actually empty. Branch-to-leaf and last-child-removal regressions passed. |
| Morph GLB exports falsely warned that the Viewer ignored animation | Remove the obsolete warning; retain actual export limitations. |
| Parallel tests shared a daemon while using separate stores | Give each test module a private endpoint, auth state and store; retire only its owned daemon. Correct the cold/warm equivalence helper's ambient lookup and obsolete stop command. No production retries or weakened assertions were added. |
| Repeated local wheel builds retained obsolete hashed Viewer assets in setuptools scratch | The canonical wheel gate now stages a clean package and requires exact runtime filenames and bytes. The contaminated local wheel had 54 runtime entries and was 4.24 MB; the verified clean wheel has 29 and is 2.50 MB. This compares local build hygiene, not main/branch dependency size. |

Review covered the Python store's object/index boundaries and freshness,
generation/daemon/artifact paths, shared mesh and animation ownership,
incremental assembly synchronization, viewer mode separation, and the shipping
wheel/runtime boundary. The fixes preserve the clean object/index model and
do not introduce author-facing cache plumbing.

## Manual and integration verification

- In-app browser: selected a STEP component and face; confirmed a populated
  reference (`o1.1.f3`) and geometry measurements after lazy topology loading.
- Verified simplified Display controls, fixed edge styling and grid toggle;
  switched Inspect → Render → Inspect and checked restored CAD settings.
  Light/dark appearance and the studio backdrop updated correctly.
- Visually checked the centrifugal impeller. The blade facets come from the
  model's authored polygon outline, not lost tessellation detail.
- Loaded STL and 3MF in both modes. Render exposes Studio and hides CAD tools.
  These simple static mesh fixtures do not claim broad material/format coverage.
- Played the Fox GLB's Run clip, switched modes while it played, then paused and
  scrubbed. Animation remains available in Render; static meshes have no
  Animation tab.
- Verified network, compiler and HTTP 503 error recovery, including a 100-line
  diagnostic, with no JavaScript exceptions or unintended forced rebuild POST.
- Rebuilt and installed the wheel in a scratch venv outside the checkout.
  Verified imported package/runtime paths, generated STEP and DXF, exported
  STL/3MF/GLB, produced five mixed-format snapshots and served the bundled
  Viewer with all five catalog entries. Its owned server was stopped.
  Final clean wheel: 2,504,876 bytes, SHA-256
  `43bf53f3ca1b944011d088f1e21d6230d7e5d9d539a1460fedb5e692a0315d5b`.
- The final lifecycle run passed all ten assertions: six model switches, lazy
  topology demand, orbiting and four saved-STEP replacements. Returned scenes
  retained exactly 20,420 GPU-buffer bytes / 17 buffers; all four edit snapshots
  retained 20,496 bytes / 17 buffers, and artifact workers were reclaimed.
  Source execution is excluded from this saved-file replacement check.
  Initial strict memory comparisons had mixed selection states; the harness
  now preserves selection and parks hover outside the viewport while retaining
  exact equality assertions.
- One HTTP 400 console message occurred in the initial edit run. It did not
  reproduce in subsequent instrumented runs, including the final four-edit run.
  The harness now records failed-response URL, status and bounded body. No
  production cause or fix was established for that isolated observation.

The full package suite passed **1,841 tests**, followed by **51 focused tests**
covering the final schema cutover, input freshness, animated exports and the
snapshot kernel boundary. Shared JavaScript passed **1,083 tests**, and the
viewer client passed **619 tests**. All existing skill
suites passed after correcting stale DXF/Display assertions, and the final
global gate passed **137 tests (one skipped)**. The apparent cross-language
tessellator-version failure was a test importing another checkout's package;
the corrected test pins this source and verifies complete cache-key parity.
The production versions already agreed.

Canonical bundling and generated-runtime freshness checks passed. Full-suite
attempts, focused reruns and lifecycle results are preserved separately in the
archived validation evidence. Generated CAD, images, wheel files and caches remain untracked under
`models/tmp/full-review-20260912`.

## Remaining performance work

1. Improve cold surface preparation and complete-scene scheduling. The iris
   result shows that earlier streaming does not automatically reduce the time
   until every part is usable at standard detail.
2. Reduce first-display worker/startup costs without moving expensive display
   work back onto every generation. Measure generation, first visibility and
   complete readiness together when choosing the policy.
3. Extend retained component/dependency reuse to real edited assemblies, then
   benchmark edit-to-visible latency including eventual STEP save. The CLI
   warm-edit table here ends at saved STEP; it is not an end-to-end live-browser
   latency table.
4. Continue bounded long-session and complex-format coverage. Passing these
   checks is not proof that arbitrary large assemblies cannot exhaust a browser.
   Retain the new HTTP diagnostics to identify the isolated 400 if it recurs.

No fresh FreeCAD run was part of this review. Earlier retained-document FreeCAD
operation timings exclude costs included in these command-level measurements;
putting them in the same table would imply a comparison we have not established.
The current results support tangible cadgen improvements, not a general 100×
speedup or completed FreeCAD parity.

## Evidence and reproduction

Lossless archives under `results/` contain the per-sample timings, source/STEP
hashes, source fingerprints, browser counters and temporary study helpers:

- `full-review-20260912.json.gz`: generation, final snapshots and the initial
  snapshot regression measurements, separately labelled.
- `full-review-browser-20260912.json.gz`: plate and planetary browser runs.
- `full-review-browser-iris-complete-20260912.json.gz`: corrected iris study.
- `full-review-browser-iris-20260912.json.gz`: superseded partial-scene probe,
  retained for audit only.
- `full-review-reproduction-20260912.json.gz`: exact helper sources, fixture
  source, configuration, installed-wheel provenance and validation records.

The [archive manifest](results/compressed-evidence.json) records raw and
compressed SHA-256 hashes. Extract with `gzip -dk` to read the JSON. Helpers use
explicit local paths and ports from the recorded configuration; substitute
your own checkout, Python, baseline archive and fresh fixture/cache directories
before running. Use the canonical `scripts/bundle/bundle.sh` entry point for
both revisions. Do not reuse the obsolete daemon-stop calls as proof of a cold
supervisor; the measurements above deliberately make the narrower claim.
