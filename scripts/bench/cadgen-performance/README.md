# Cadgen warm-build and meshing benchmarks

These repository commands reproduce two CPU studies: cached model edits with
preview/save events, and native OCCT triangulation versus the current JavaScript
SURF tessellator. They do not change the runtime or select a different production
mesher. See [the recorded study](RESULTS-20260910.md) for results and limitations.

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
The view preparation reads the completed model record, flattens its pinned tree,
checks the referenced BREP/SURF object hashes, and copies those immutable bytes.
It does not import model code, parse STEP, or import OCCT. A view is a fixed
snapshot, so later model/store changes do not alter the meshing inputs.

Use an isolated fixture and store. Stop other builds, browser CAD loading, and
runtime edits during timing; the scripts do not acquire a machine-wide lock.
Coordinate a timing window if other agents share the checkout. All CAD inputs,
cache scratch space, and generated artifacts stay under `models/`. JSON and
text logs may go under `tmp/`; retain useful study reports here when reviewing
results. Neither command deletes the supplied store. A new run overwrites the
chosen report and matching log/report filenames, so use a new report basename
to preserve an earlier study.

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

The import study copies the completed STEP into a separate empty store under
`models/`. The cold public `read_step()` includes the compile subprocess startup.
Subsequent calls run in the same interpreter with compile submission forbidden;
the report records the input-byte hash, size, volume, and call durations. This
is a public import-hit measurement, separate from warm model execution. It does
not measure a fresh caller's Python/kernel startup.

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
`absoluteChordMm = component.scale * chordTolerance`, the JS default angular
tolerance, `isRelative=False`, and `isInParallel=False`. OCCT's relative mode
scales against edges, so passing the normalized JS value directly would compare
different physical tolerances. The native constructor performs the meshing
operation. See the [OCCT API documentation](https://occt3d.com/dev/doc/refman/html/class_b_rep_mesh___incremental_mesh.html).
Equal chord/angular inputs do **not** establish equal visual quality: these
algorithms refine geometry differently. `--chords` accepts a comma-separated
list for further tolerance sweeps.

Every native sample reconstructs a private shape from the same BREP and removes
existing triangulation before timing. It records serialization hashes before
property queries, before meshing, after meshing, and after extraction, as well
as the unchanged input-file hash. Native extraction includes per-face analytic
normals, winding correction, stable face/edge ordinals, edge polylines, and
opposite-vertex triangle-side ordinals. Candidate bytes use the existing TESS
layout for size/decode comparisons; this does not grant them the current
mesher's cache or export identity.

The report separates file reads, parse/reconstruction, meshing, Python extraction,
encoding, and cached reads/decoding. Reads are normally OS-page-cache hits.
Geometry audits and exact OCCT area/volume queries run outside those timings.
The audits check triangle normals, reference ranges, a quantized edge-weld
heuristic, and area/volume differences. They are useful checks, not a proof of
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
