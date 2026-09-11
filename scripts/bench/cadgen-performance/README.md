# Cadgen warm-build and meshing benchmarks

Start with the [current summary](SUMMARY-20260911.md). The latest
[FreeCAD-inspired follow-on](FOLLOWON-INTEGRATION-20260911.md) links the
reference-assembly, pure-factory, incremental-scene, preview-delivery, command-completion and
dependency-footprint studies and their reproduction commands. These use small
and moderate fixtures; historical giant-assembly results are not current
acceptance requirements.

These repository commands reproduce two CPU studies: cached model edits with
preview/save events, and native OCCT triangulation versus the current JavaScript
SURF tessellator. They do not change the runtime or select a different production
mesher. See [the recorded study](RESULTS-20260910.md) for results and limitations.
The [saved-document repair](SAVED-IDENTITY-FOLLOWUP.md) has a separate
[nine-part rerun](RESULTS-20260910.md#saved-document-repair-warm-check) and
[validation record](VALIDATION-20260910.md#saved-document-identity-repair).
Earlier hand measurements retain their original runtime fingerprint; the
repair does not turn those coarse-load results into full-detail acceptance.

Run from the repository root with a CAD development environment and Node
available. In a lightweight worktree, `CAD_PYTHON` may name the existing CAD
environment's Python; `PYTHONPATH` selects this checkout's cadgen source.

```sh
CAD_PYTHON=./.venv/bin/python
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PWD/packages/cadgen/src"

"$CAD_PYTHON" scripts/bench/cadgen-performance/prepare.py fixture \
  --directory models/tmp/performance-study

"$CAD_PYTHON" scripts/bench/cadgen-performance/warm_build.py \
  --model models/tmp/performance-study/planetary_gear_assembly.py \
  --store models/tmp/performance-study/store \
  --report tmp/performance-study/warm.json --iterations 3

"$CAD_PYTHON" scripts/bench/cadgen-performance/prepare.py view \
  --model models/tmp/performance-study/planetary_gear_assembly.py \
  --store models/tmp/performance-study/store \
  --directory models/tmp/performance-study/view

"$CAD_PYTHON" scripts/bench/cadgen-performance/native_mesh.py \
  --view models/tmp/performance-study/view \
  --report tmp/performance-study/native.json --iterations 3
```

The fixture preparation copies the checked-in nine-part planetary model and
changes only its output decorators: one local `planetary.step`, without mesh
exports or a kinematics sidecar. It refuses to overwrite an existing source.
The view preparation reads the completed model record and resolves the pinned
tree's display view through the artifact pool before copying its immutable
BREP/SURF inputs. Missing surfaces are derived outside the measured mesh phase;
this does not run model source or parse STEP. A view is a fixed
snapshot, so later model/store changes do not alter the meshing inputs.

Use an isolated fixture and store. Stop other builds, browser CAD loading, and
runtime edits during timing; the scripts do not acquire a machine-wide lock.
Coordinate a timing window if other agents share the checkout. All CAD inputs,
cache scratch space, and generated artifacts stay under `models/`. JSON and
text logs may go under `tmp/`; retain useful study reports here when reviewing
results. Neither command deletes the supplied store. A new run overwrites the
chosen report and matching log/report filenames, so use a new report basename
to preserve an earlier study.
Structured reports retain individual samples, runner events, stage timings and
content proofs. New per-call `*-logs/` console directories remain local; older
already-tracked logs are retained as historical evidence. Rerunning the harness
recreates its console logs alongside the report.

Large raw reports and profiler captures are retained losslessly as `.gz` files.
[The archive manifest](results/compressed-evidence.json) records original and
compressed sizes and SHA-256 digests. Small summaries remain readable JSON;
compressed reports preserve every original sample, helper and identity proof.
Use `gzip -dk path/to/report.json.gz` to restore its original local path before
running a helper that reads it. The restored raw copy is ignored by Git.

## Browser lifecycle and preview validation

[The integration record](VALIDATION-20260910.md) distinguishes functional
browser checks from the isolated CPU timings below. The inexpensive repeated
fixture is `models/examples/performance/repeated24.py`: 24 occurrences of two
components. Copy it beside the prepared planetary source, run both scripts,
and start `cadgen viewer` from that directory. Keep the same cache directory
for the builds and viewer.

The lifecycle harness uses that already-running viewer and opens its own
headless Chromium; it does not use the user's browser or stop the server.
With the viewer dependencies installed, run:

```sh
node scripts/bench/viewer-memory/lifecycle.mjs \
  --url http://127.0.0.1:3245 \
  --file repeated24.step --other planetary.step \
  --out tmp/performance-study/lifecycle.json
```

Use the port announced by your viewer. Both files must be in the served
directory; the harness selects them through the sidebar. It checks delayed
topology demand, repeated same-tab switches, hover/selection, orbiting, memory
admission and actual WebGL buffer releases, collecting after explicit browser
GC. Its report identifies when the first topology request came from expanding
a tree occurrence rather than a canvas pick. Aborted requests during intentional
switches are recorded but do not count as unexpected failures. The harness
also records navigation/switch duration through an explicit 900 ms settling
period, first tree-topology demand latency when that fallback is used, and
browser frame intervals/draw counts during a bounded camera orbit. Frame
intervals describe browser presentation cadence, not GPU execution time.
The report names the viewport, browser and server-cache assumptions, hardware,
commit and any runtime changes. Run it without competing builds or browsers
when interpreting those timings. It neither clears server tessellation caches
nor proves absence of every possible long-session leak.

Copy `models/examples/performance/repeated24.step.js` beside the repeated STEP
and pass `--animation-ms 5000` to measure its moving occurrences, frame cadence
and GPU allocation plateau. The harness exits Orbit mode before opening the
animation transport. `--edit-cycles 6 --edit-target models/.../repeated24.step
--edit-variant models/.../repeated24_variant.step` additionally alternates two
explicit geometry-only STEP fixtures through the same saved path and browser
tab. It records retained heap/owned/GPU bytes after every complete replacement
and restores the target's original bytes and timestamps in `finally`. The paths
must be under `models/`, the bytes must differ, and annotation sidecars are
refused. These measurements cover saved-file replacement, excluding model
execution and preview publication. Use disposable fixture copies and at least
four edit cycles: the plateau check needs two settled observations of each
revision and compares GPU bytes and buffer counts within that revision. The
harness rejects one to three edit cycles before contacting the viewer.

For a bounded large STEP load, `scripts/bench/viewer-memory/measure.mjs`
requires the current client's complete component publication: a visible
partial scene or a cleared diagnostic during failure/retry is not success.
`loaded` requires `final: true`, equal positive loaded/total component counts,
matching actual scene occurrence counts, and a completed scene synchronization
after the final publication. This harness no longer supports the older
single-publication fallback.
Its response-failure list distinguishes expected tessellation-cache misses
from asset failures. The first-geometry frame remains a separate measurement.
The Node process bounds renderer probes; a blocked page cannot satisfy its own
timeout. Partial-load ramps include explicit clears/restarts; current and last
published costs remain separate. Memory readings are retained even if completion
times out. A probe timeout is reported separately from a renderer crash.
Before opening Chromium, the harness checks that the served index and its
referenced entry assets match this checkout's built client byte for byte. A
disk fingerprint alone does not establish which checkout a server serves.
Reports also record browser/Node/host versions and installed render dependency
versions, resolved metadata paths and hashes at both ends; a lockfile alone
does not establish what a borrowed dependency directory actually contains.
Launch Python with `PYTHONPATH=<checkout>/packages/cadgen/src` and verify
`cadgen.__file__` and `cadgen.viewer.__file__` when comparing checkouts.

Default adaptive acceptance uses a separate harness. Current iteration uses
the nine-part planetary and modest repeated-parts fixtures; further tendon-hand
stress tests were stopped at the user's request. Historical forced-L1 results
remain separate from default adaptive behavior.

```sh
node scripts/bench/viewer-memory/adaptive.mjs \
  --url http://127.0.0.1:3276 --file planetary.step \
  --components 9 --occurrences 9 \
  --out tmp/performance-study/planetary-default-adaptive.json \
  --screenshot models/tmp/performance-study/planetary-default-adaptive.png
```

This uses production default LOD and worker settings, a fresh private browser,
an existing caller-owned viewer/store, and at most 180 seconds / 2 GiB for the
largest renderer. It verifies served entry and worker assets plus installed
dependency versions against their locks. Optional `--server-provenance` includes
an existing JSON proof of server module paths; it does not silently import a
second server as evidence. Coordinate the run with other timed workloads.
Set `PLAYWRIGHT_FROM` to an existing Playwright package directory if it is not
installed in the viewer's dependency directory. `--cache-state` records an
explicit fixture/cache qualification, such as a census-populated canonical L1
cache with higher levels still absent; the harness never assumes a cold cache.
Optional `--resize-to 1600x900` widens the real browser viewport and restores it,
requiring a scheduler reevaluation and stable complete scene after both changes.
Native window Resource Timing uses a bounded 8,192-entry browser buffer and
collects up to 4,096 matching same-origin tessellation-cache/SURF entries only
after grading. The report keeps route identifiers and numeric request/response
phases and byte sizes, with explicit truncation and a grading-time cutoff;
there are no response-body copies or production fetch changes. Worker-owned
SURF fetches have separate timelines and are outside this window-only capture.
HTTP methods, server CPU time, JS body materialization and GPU completion are
not inferred from those entries. The separate worker postMessage timestamps
start after the main thread's cache HTTP/body read and dispatch queue.

The harness waits for complete actual scene records and a subsequent draw, then
requires two seconds of stable camera input/zoom, LOD publication and level
counts, with no active scheduler job/timer, reservations, uploads or workers.
Policy satisfaction additionally requires the scheduler's explicit
`qualitySettled` signal and an empty unmet-target list. Idle alone is insufficient;
pressure-capped and admission-denied targets remain budget-limited even if a
UI limitation message has been cleared.
It orbits, zooms/unzooms with a recorded wheel sequence, selects/clears one
occurrence row and observes idle afterward. A near/returned-view settle timeout
is recorded as a failed phase while recovery and selection continue within the
original total deadline; later recovery cannot turn that run into a pass.
Initial-load, RSS, total-deadline and browser failures still stop immediately.
Denied detail can leave a valid
stable complete view; that outcome is reported separately from a policy-satisfied
pass. No refinement/denial activity makes the adaptive exercise inconclusive.
Orbit cadence must meet PLAN's strict p95 below 33 ms; an additional explicit
maximum-frame guard is 250 ms. Zoom intervals are reported separately. The first
two rAF intervals are excluded, matching the existing medium lifecycle method.
The 100 orbit input steps wait at least 50 ms each; browser input latency can
extend the actual motion beyond five seconds, so the report records its duration.
There is no forced GC or allocation sampling before grading. The screenshot
and any failure-side heap diagnostics occur afterward, and require explicit
visual review. Numerical probes cannot prove visual correctness alone.

Run `node --test scripts/bench/viewer-memory/adaptive-support.test.mjs` for the
pure completeness/stability/budget classification and process-RSS accounting
checks. This harness does not execute CAD source, alter export/cache identity,
hide parts, raise memory limits, or stop the server.

For an isolated dense-component picking study, use an existing canonical TESS
object and the currently served production viewer:

```sh
node scripts/bench/viewer-memory/picking.mjs \
  --url http://127.0.0.1:3245 --tess models/.../store/objects/ab/cdef... \
  --out tmp/performance-study/picking.json
```

This bundles a temporary probe from the current shared picking code, separately
verifies the actual Vite worker asset served by the viewer, and transfers input
arrays through a temporary local HTTP server. It records the exact first-ray
fallback, worker-ready latency, main-thread long tasks, hit multisets and
unchanged display arrays. Admission rejection and geometry-disposal cancellation
run after the timed window. This is a component CPU/picking study without WebGL;
worker elapsed time is not main-thread blocking time or whole-assembly picking.
The runner closes only its own browser and temporary HTTP server.

`--heap-diagnostics` adds sampled allocation provenance. Every responsive run
also records main-page and live-worker CDP heap usage, array backing storage,
pending cache-upload bytes, and RSS before and after a forced collection. On
failure it first stops only workers in its disposable diagnostic page, keeping
the completion result failed. Later workers in that diagnostic page are
terminated immediately too. A second collection follows the settling interval
so already-queued publications do not trivially pollute the after-GC sample.
The report still does not claim main-thread quiescence or a leak from one heap
reading. Sampling and collection are diagnostic overhead;
use separate uncontended runs for timing acceptance. Worker request summaries
retain only bounded metadata, never mesh or upload arrays.

Pass `--min-lod 1` to require canonical detail on every component. This enables
a harness-only display floor, leaving export tolerances and concrete mesh keys
unchanged. Completion requires all component levels to meet that floor, an idle
LOD scheduler with no pending camera evaluation, and scene synchronization after
the latest replacement publication. The report includes level counts and unmet
detail counts; a complete coarse model cannot pass this check. Without the flag,
the ordinary camera-based detail policy remains in effect.

## Warm builds and repeated imports

`warm_build.py` imports the kernel before timing and invokes the normal model
runner repeatedly in one interpreter. It primes the baseline, geometry edit,
and placement edit before measuring. Each measured geometry or placement edit
is followed by an untimed baseline restoration build. The default substitutions
change the carrier diameter from 105 to 106 mm and move it down 0.5 mm.
Other single-output fixtures can provide exact `--geometry-from`,
`--geometry-to`, `--placement-from`, and `--placement-to` strings; each source
match must be unique. The model must declare its outputs beneath `models/`.

The command restores the exact original source bytes and timestamps in `finally`,
including when a build fails. A failed run can leave the last successful CAD
output beside that restored source; build it again before using that output.
An external kill cannot run `finally`, which is another reason to use a copy.
Do not edit the fixture concurrently with the benchmark.

The JSON contains every runner event with a `perf_counter` timestamp, normal
verbose stage logs, operation-cache deltas, component IDs, tree/document hashes,
peak process RSS, and the measured distributions. `firstPreviewMs` is the
backend's preview publication event; it is **not** browser geometry visibility.
`savedMs` is its saved-publication event; runner completion follows separately.
Stage logs are rounded and some stages are nested, so their durations must not
be added as though they were disjoint. Source writes, kernel startup, daemon
IPC, and browser work are outside the build timing window. No profiler runs.

The default edit samples revisit already-primed output variants. To distinguish
that case from a new edit, repeat `--novel-geometry-to '<replacement>'` and
`--novel-placement-to '<replacement>'` with distinct replacements. These run
once each after the primed samples, restoring the baseline between edits.
`novelSummary` is separate from the repeated-edit `summary`, and every novel
sample must produce a STEP digest not previously emitted in the study. Use a
fresh dedicated store to exclude earlier runs: the digest assertion alone
cannot prove an existing store has never seen those bytes. Reusing a canonical
saved-document cache can accelerate repeated output variants; it cannot skip
STEP parsing for a genuinely new output digest.

The import study copies the completed STEP into a separate empty store under
`models/`. The cold public `read_step()` includes the compile subprocess startup.
Subsequent calls run in the same interpreter with compile submission forbidden;
the report records the input-byte hash, size, volume, and call durations. This
is a public import-hit measurement, separate from warm model execution. It does
not measure a fresh caller's Python/kernel startup.

## The same assembly split into child models

`models/examples/performance/planetary_split` is a separate architecture
example: the same nine-part geometry composed through nine ordinary `@step`
children. Each child declares a real STEP save. Its root imports only model
functions, submits all children before reading their geometry, and owns the
carrier placement. Only `carrier_plate.py` owns the carrier diameter.

Copy the source before generating or editing it:

```sh
"$CAD_PYTHON" scripts/bench/cadgen-performance/prepare.py split-fixture \
  --directory models/tmp/planetary-split-study
```

Build that copied root and an isolated monolithic copy with the same store.
Then `verify_split.py --monolithic-model <mono.py> --split-model <split.py>
--store <store> --report <report.json>` compares saved component identities,
names, colors, placements, volume, bounding box, solid count and nine child
pins. It also records whether the complete saved STEP and document tree are
identical. Its geometry reads forbid source-record lookup, STEP parsing,
raw-import fallback and compile submission. It builds nothing.

The warm harness can edit a child source while rebuilding its root:

```sh
"$CAD_PYTHON" scripts/bench/cadgen-performance/warm_build.py \
  --model models/tmp/planetary-split-study/src/planetary_gear_assembly.py \
  --geometry-model models/tmp/planetary-split-study/src/carrier_plate.py \
  --placement-from 'CARRIER_OFFSET_Z = 0.0' \
  --placement-to 'CARRIER_OFFSET_Z = -0.5' \
  --store models/tmp/planetary-split-study/store \
  --report tmp/performance-study/split-warm.json --iterations 3 \
  --assert-child-pins --skip-imports \
  --child-daemon-socket /tmp/cadgen-planetary-split-study.sock
```

The caller owns that dedicated daemon and its lifecycle; choose a socket not
used by another task, and stop only the daemon started for this study. Without
`--child-daemon-socket`, child builds use transient processes, whose startup
is inside each affected edit. With it, priming warms the child workers; child
IPC and all declared saves remain inside the timed calls. The root always
executes in the harness interpreter. `--geometry-model` and
`--placement-model` independently select each substitution's source; both
default to the root. Every touched source's exact bytes and timestamps are
restored in `finally`.

`--assert-child-pins` requires the geometry edit to replace exactly the
specified child's pin, while placement preserves all pins. The report keeps
child records, output digests and per-model source-ready, preview, save and
terminal receipt times. `firstPreviewMs` and `savedMs` refer only to the root;
a child's preview cannot satisfy root preview timing. Operation-cache counts
and RSS are for the root process, excluding child-process totals. Read imports
are separate work; `--skip-imports` omits them for this architectural study.

This is not a same-script speedup or a replacement for the original monolithic
preview target. The [reviewed-commit monolithic baseline](BEFORE-7AA-20260910.md)
has no source-ready/early-preview event. Compare the split fixture on that
same reviewed runtime and the final runtime before attributing a difference
to early child-result consumption rather than source boundaries alone.

## Imported STEP edits

The [small extraction-batch study](COMPONENT-EXTRACTION-20260910.md) isolates
fresh worker startup from extraction, verifies serial/spawn output parity,
and records the measured basis for the default 512 KiB BREP scheduling cutoff.

The ordinary `models/examples/performance/planetary_imported` fixture reads
the fixed nine-part STEP and changes only its carrier; no gear generation
runs. `imported_step_edit.py` prepares scratch copies, validates native part
retention and saved geometry, and checks every warm report's component
identities. Its model uses only existing `@step`, public `read_step` and
build123d operations. Run the existing `warm_build.py` with the source and
placement substitutions documented in the fixture's README.

The [matched imported-STEP study](IMPORTED-STEP-20260910.md) records identical
inputs and saved outputs on the reviewed baseline and current runtime,
including cold preparation, warm saved builds and current source previews.
This makes STEP loading and local editing explicit alongside the monolithic
and split procedural studies.

## FreeCAD retained-document comparison

With FreeCAD installed, `freecad_edit.py` imports the same nine-part STEP into
an isolated headless FreeCAD document. It times replacing only the carrier
(105 to 106 mm), moving it down 0.5 mm, native meshing of that part, whole
assembly STEP export, and STEP read-back separately:

```sh
python3 scripts/bench/cadgen-performance/freecad_edit.py \
  --freecad /Applications/FreeCAD.app/Contents/Resources/bin/FreeCADCmd \
  --step models/tmp/performance-study/planetary.step \
  --directory models/tmp/performance-study/freecad \
  --report tmp/performance-study/freecad.json --iterations 5
```

The command uses FreeCAD's bundled Python/kernel and private configuration
files. It does not touch a running FreeCAD GUI or the input STEP. Temporary
exports stay under the supplied `models/` directory and are removed. The
report includes both kernel versions through its controller and worker
metadata, retained part counts, input integrity, saved volume, and stage
medians after a priming sample. Native mesh parameters are explicit but are
not a matched-quality comparison with cadgen; use the meshing study for that.
These are in-memory feature/placement operations on a retained document,
whereas `warm_build.py` reruns the full Python model. The distinction measures
the execution architectures; it is not evidence of measured FreeCAD GUI
frame latency or a whole-build speedup from a single kernel operation.

## Native meshing experiment

`native_mesh.py` runs two independent process trials. Each trial runs the
current JS mesher in Node, native meshing in Python/OCCT, and the production
JS TESS decoder over native candidate payloads. Each component/LOD has three
samples by default. The component list comes from `assembly.json`; leftover
files outside that list are ignored. BREP and SURF hashes are checked across
the comparison. Private candidate TESS files use experiment-specific names,
never canonical mesh keys or `index/mesh` entries, and are removed afterward.
The raw reports' `cachePath` values therefore describe expired scratch paths.

The default normalized chords are `0.003` and `0.0015`. Native meshing uses
`absoluteChordMm = component.scale * chordTolerance * nativeChordScale`, the JS default angular
tolerance, `isRelative=False`, and `isInParallel=False`. OCCT's relative mode
scales against edges, so passing the normalized JS value directly would compare
different physical tolerances. The native constructor performs the meshing
operation. See the [OCCT API documentation](https://occt3d.com/dev/doc/refman/html/class_b_rep_mesh___incremental_mesh.html).
Equal chord/angular inputs do **not** establish equal visual quality: these
algorithms refine geometry differently. `--chords` accepts a comma-separated
list for further tolerance sweeps. `--native-chord-scale` defaults to 1 and
allows an explicit finer native setting against the same JS reference chord.
The [mesher v2 comparison](MESHER-V2-20260910.md) uses 0.5 and adds a bounded
curved/trimmed/singular corpus:

```sh
"$CAD_PYTHON" scripts/bench/cadgen-performance/mesh_corpus.py \
  --view models/tmp/performance-study/curved

"$CAD_PYTHON" scripts/bench/cadgen-performance/native_mesh.py \
  --view models/tmp/performance-study/curved \
  --report tmp/performance-study/curved-native.json \
  --iterations 3 --native-chord-scale 0.5
```

Corpus preparation refuses an existing destination and writes only private
BREP/SURF inputs, without publishing a model or store index.

Every native sample reconstructs a private shape from the same BREP and removes
existing triangulation before timing. It records serialization hashes before
property queries, before meshing, after meshing, and after extraction, as well
as the unchanged input-file hash. Native extraction includes per-face analytic
normals, winding correction, stable face/edge ordinals, edge polylines, and
opposite-vertex triangle-side ordinals. It discards triangles that collapse at
Float32 transport precision, including that work in extraction time and
reporting the discarded count. Candidate bytes use the existing TESS
layout for size/decode comparisons; this does not grant them the current
mesher's cache or export identity.

The report separates file reads, parse/reconstruction, meshing, Python extraction,
encoding, and cached reads/decoding. Reads are normally OS-page-cache hits.
Geometry audits and exact OCCT area/volume queries run outside those timings.
The audits check triangle normals, reference ranges, a quantized edge-weld
heuristic, and area/volume differences. All used vertices, triangle-edge
midpoints and centroids are also projected onto the exact OCCT face surface;
the report includes maximum sampled error and projection fallbacks. These
samples do not establish a continuous surface bound or prove trim coverage.
They are useful checks, not a proof of
watertightness, matching Hausdorff error, correct on-screen picking, or equal
visual quality. Byte hashes compare repeated samples and fresh processes.
Peak RSS covers the whole process, including runtime imports and audit work;
it is not incremental mesh memory or GPU memory.

Both scripts record hardware, language/library versions, Git HEAD, and a digest
of cadgen Python/JS runtime sources. `runtimeUnchangedDuringStudy` must be true
for an interpretable run. The source digest identifies a dirty checkout better
than HEAD alone; retain the corresponding code revision with the report.

These commands do not time HTTP transport, browser worker messaging, main-thread
packing, selection/BVH construction, React publication, GPU uploads, first
visible geometry, orbit frame time, or picking latency. Compressed payload size
is only a potential transport cost. Use the viewer benchmark commands for those
separate stages; a fast kernel result alone is not an end-to-end speedup.

`viewer_quality.mjs` measures first visible geometry, complete preview, and
standard-detail completion separately in a real browser. Run it against a private
viewer/store with prepared geometry and a deliberate display-cache state; see
[standard-detail results and reproduction](VIEWER-QUALITY-20260911.md). It rejects
an incomplete standard result and reports page errors, adopted levels and
resource estimates. Snapshots belong under `models/`; detailed local JSON can go
under `tmp/`.
