# Retained-document P0 benchmark

## Resident browser integration review

`resident_viewer.py` is a bounded internal integration harness for the plate
and 24-part fixtures. It owns one dispatcher, executes captured source, requests
revision-bound prototype meshes and renders through the shared scene runtime.
Run it with this checkout's CAD Python and JavaScript dependencies:

```sh
PYTHONPATH=packages/cadgen/src .venv/bin/python \
  scripts/bench/cadgen-performance/document-engine/resident_viewer.py \
  --scratch models/tmp/document-resident-review
```

Open the printed localhost URL. Rebuild unchanged, change holes and move one
part exercise separate invalidations. Click a visible face in Inspect to query
the exact native revision; Render requests no CAD edges and installs no picker.
The view selector reloads the test page with the same native owner, rather than
claiming to test the public viewer's mode-switch lifecycle. Both modes use the
same explicitly reported native mesh defaults; the Render choice exercises
Final lighting, with capture scale fixed to one. It does not yet test the
planned screen-error detail ladder.

Diagnostics separate source generation/save, native display derivation,
transfer/adoption and scene/GPU completion. `acceptedToGpuMs` ends after
`gl.finish()` and excludes compositor presentation; it is a live diagnostic,
not a paired benchmark. `retainedGeometryRecords` counts occurrence records
whose geometry was reused, while `uniqueGeometries` counts actual geometry
objects. Twenty-four occurrences can share one geometry. A model choice
reloads the page and therefore transfers its mesh even if the native owner is
warm. The harness has no public catalog, file watching, naming reconciliation
or authentication beyond a per-process local capability token.

The 2026-09-13 manual review against frozen native `801057d1b` and the current
JS path verified unchanged, placement and hole edits on the assembly, plus
the small plate and light/dark photographic views. Unchanged and placement
updates transferred no mesh bytes and retained geometry for all 24 records;
the hole edit transferred one 31,588-byte shared mesh. Exact picking on the
moved top face reported z=12 mm; increasing the hole radius from 3 to 3.5 mm
changed its reported area from 585.537619 to 544.696914 mm². These checks do not
establish the public resident-viewer or large-assembly gate.

## Real 118-occurrence assembly

The `full-paired` command additionally accepts `--models iris118`. It uses the
existing mechanical iris source under `models/assemblies/src/`, preserving all
modeling helpers and geometry. It redirects the one declared STEP into the
benchmark directory and instruments source execution. The local geometry edit
changes the base-ring mounting-hole diameter; the placement edit translates
only that base ring along Z. Every saved result is independently imported and
checks all 118 occurrences, including the 117 parts that must stay unchanged.
This fixture is opt-in; default short runs still use the plate and Assembly24.

Its frozen old-engine cold build is approximately 20 seconds on the development
machine. Start with three cold and three warm samples, run the two engines
serially, and use `--warm-timeout 160` for each primed edit session. The per-build
cap remains 60 seconds. Use the same `full-paired` report arguments described
below; both runtime revisions are archived before timing and the report keeps
every sample, actual output check, and independent geometry oracle. Do not mix
in-process diagnostic timings with this complete STEP-plus-companion boundary.

## Serial engine benchmark

`harness.py` prepares code-only frozen runtime archives, runs the two bounded
fixtures serially, validates every completed STEP with an independent cold
readback, and records command stages, optional engine counters, source side
effects, RSS samples, dependency fingerprints, and cleanup. It does not start a
browser and does not use the giant assembly corpus.

The permanent source paths are
`models/performance_document/plate.py` and
`models/performance_document/assembly24.py`. Generated copies and outputs use
the `--scratch` path. Every completed measured command is fsynced immediately
to `REPORT.json.samples.jsonl`; an interrupted run therefore leaves an
explicit incomplete raw record even when the final aggregate is absent.

Use the repository's CAD Python and this checkout's source for the controller:

```sh
CAD_PYTHON="${CAD_PYTHON:-$(command -v python3)}"
test ! -x .venv/bin/python || CAD_PYTHON="$PWD/.venv/bin/python"
PYTHONPATH=packages/cadgen/src "$CAD_PYTHON" \
  scripts/bench/cadgen-performance/document-engine/harness.py preflight

PYTHONPATH=packages/cadgen/src "$CAD_PYTHON" \
  scripts/bench/cadgen-performance/document-engine/harness.py run \
  --revision 5c4a212cae32e834fa4d805ae778ab5ee6cd71a2 \
  --cold-samples 1 --warm-samples 2 \
  --scratch models/tmp/performance-document-smoke \
  --report scripts/bench/cadgen-performance/document-engine/results/checkpoint-smoke.json
```

The smoke run is functional instrumentation validation, not percentile
evidence. The frozen exploratory series is `--cold-samples 5 --warm-samples
10`, run only in a reserved serial native-compute window. Each command is
capped at 60 seconds, and sample counts are capped at five cold and ten warm.
Run the candidate and main revisions separately so a failed or noisy run
remains attributable. Budget about three minutes for the optimized checkpoint
and five minutes for main on the reference host; reserve ten minutes for the
serial pair plus report finalization.

After both runs complete, enforce cross-revision saved-geometry parity and
produce the bounded median-ratio record:

```sh
PYTHONPATH=packages/cadgen/src "$CAD_PYTHON" \
  scripts/bench/cadgen-performance/document-engine/harness.py compare \
  --baseline scripts/bench/cadgen-performance/document-engine/results/main.json \
  --candidate scripts/bench/cadgen-performance/document-engine/results/checkpoint.json \
  --report scripts/bench/cadgen-performance/document-engine/results/comparison.json
```

The comparison requires identical fixture hashes and sample counts; the
candidate model/scenario set may be a subset of the baseline. It checks labels,
validity, volume, area, bounds and topology counts for every measured sample.
STEP byte equality is recorded separately and is not the geometry oracle.
Timing ratios are emitted only when both reports use the same boundary kind and
neither environment note marks its timings noncomparable.

The internal retained-engine mode has no public product flag. It calls the full
`run_model_argv` pipeline inside `DocumentService.activate()`, including
explicit STEP completion, and separately records the source/geometry interval
and transaction counters. Cold samples get a new process and service; each warm
scenario keeps one process and service while ordinary Python executes on every
call:

```sh
PYTHONPATH=packages/cadgen/src "$CAD_PYTHON" \
  scripts/bench/cadgen-performance/document-engine/harness.py candidate \
  --cold-samples 1 --warm-samples 2 \
  --scratch models/tmp/performance-document-candidate-smoke \
  --report scripts/bench/cadgen-performance/document-engine/results/candidate-smoke.json
```

For a timing comparison on the same in-process boundary, use frozen legacy
source with a separate worker process. That process installs the legacy
operation witness; a retained worker never does:

```sh
PYTHONPATH=packages/cadgen/src "$CAD_PYTHON" \
  scripts/bench/cadgen-performance/document-engine/harness.py legacy-inprocess \
  --revision 5c4a212cae32e834fa4d805ae778ab5ee6cd71a2 \
  --cold-samples 1 --warm-samples 2 \
  --scratch models/tmp/performance-document-legacy-inprocess-smoke \
  --report scripts/bench/cadgen-performance/document-engine/results/legacy-inprocess-smoke.json
```

Both in-process reports hash the runtime source tree before and after the run
and fail if it changes. The frozen shell/daemon command remains the public
workflow baseline, but its different launch and IPC boundary cannot supply a
candidate timing ratio.

For a matched timing series, `paired` is the durable controller. It alternates
which engine runs first for every pair. Each cold sample is one pair of fresh
workers. Each warm fixture/scenario is one pair of complete persistent-worker
blocks, with ten calls executed contiguously inside each engine's worker; warm
samples are not described as sample-by-sample interleaving. Both reports and
the comparison contain the actual chronological dispatch ledger and the exact
execution labels inside every warm block. Controller elapsed time establishes
order only and is not benchmark evidence.

The full paired command uses five cold and ten warm samples, a 60-second cold
worker cap, and a 120-second warm-worker cap. It writes separate legacy and
retained reports plus their geometry-parity comparison. Both engines use the
same full in-process `run_model_argv` boundary; public CLI process launch and
daemon IPC remain excluded. Corrected reports identify this boundary as
`in-process-run-model-argv-with-first-call-engine-setup-v2`; the versioned name
prevents an older report that prewarmed only legacy from yielding automatic
cold ratios against it.

Cold timing begins before each engine's own setup. Legacy therefore pays
`memoization.install(trusted_worker=True)` and its build123d/native imports;
retained pays `DocumentService` import/construction and the native/frontend
imports reached by its first source call. Every cold row records
`engineSetupMs`, `runModelArgvMs`, and their enclosing total. The common harness
and `run_model_argv` module imports happen before that boundary in both fresh
workers. Warm setup occurs in the scenario's unmeasured prime.

```sh
PYTHONPATH=packages/cadgen/src "$CAD_PYTHON" \
  scripts/bench/cadgen-performance/document-engine/harness.py paired \
  --baseline-revision 5c4a212cae32e834fa4d805ae778ab5ee6cd71a2 \
  --cold-samples 5 --warm-samples 10 \
  --cold-timeout 60 --warm-timeout 120 \
  --scratch models/tmp/performance-document-paired \
  --baseline-report scripts/bench/cadgen-performance/document-engine/results/paired-legacy.json \
  --candidate-report scripts/bench/cadgen-performance/document-engine/results/paired-retained.json \
  --comparison-report scripts/bench/cadgen-performance/document-engine/results/paired-comparison.json
```

That `paired` mode remains valid evidence for its versioned in-process
development boundary. It is obsolete as a comparison for the direct document
worker because it excludes the new process bridge and enters both engines
through `run_model_argv`.

`full-paired` is the durable complete-request comparison. The controller
accepts one exact entry buffer for each single-file fixture. Current cadgen
sends it through `DocumentWorker`; frozen cadgen has no captured-input door, so
the benchmark-only adapter materializes those accepted bytes immediately before
calling the frozen runner. This changes the old path-only input semantics and
is neither a compatibility layer nor a product API. The adapter write is inside
the headline and is also reported as `adapterWriteMs`; no stage is silently
subtracted to manufacture a kernel comparison.

The versioned boundary is
`captured-entry-to-attested-step-pair-full-request-v2`. The paired output
contract now verifies both the required STEP bytes and actual absence of its
companion for these annotation-free fixtures. Candidate receipts must attest
both obligations; frozen legacy receives the same actual-absence check inside
the timed boundary. Historical v1 reports remain valid for their own boundary
and are never mixed with v2 ratios. Cold begins before launching
the adapter process and includes adapter/bootstrap setup. Warm begins before
engine input delivery inside a persistent adapter after one unmeasured prime.
`acceptedBufferReadHashMs` records the transport-buffer read and digest: it is
inside the cold boundary and outside the warm boundary. Both boundaries end
only after source execution or preserved legacy freshness behavior, native
work, the required STEP publication, and a hash/size check of the actual
destination bytes. Current rows include the document-worker IPC. Archive copy,
resident display, release/shutdown, independent readback, oracle work, report
writing, and controller chronology remain outside this boundary.

The source-capture statement is deliberately narrow: only the exact entry is
captured before dispatch. Helpers and managed data are captured when actually
consumed by `SourceSession`; these fixtures have neither, and the report does
not claim an atomic project snapshot. After each session, one common current
runtime reads the archived actual STEP bytes with the source hidden and checks
labels, validity, volume, area, bounds, and topology. That independent
saved-byte readback is distinct from the in-request destination receipt. A
candidate-only pinned resident display is recorded after all generation samples
as a separate diagnostic. The comparison never divides resident-display time
by saved-reopen time.

Do not start even a `1` cold / `2` warm functional smoke until both runtime
trees are frozen and the native worker is released for the run. The complete
bounded matrix remains five cold and ten warm samples:

```sh
PYTHONPATH=packages/cadgen/src "$CAD_PYTHON" \
  scripts/bench/cadgen-performance/document-engine/harness.py full-paired \
  --baseline-revision 5c4a212cae32e834fa4d805ae778ab5ee6cd71a2 \
  --cold-samples 5 --warm-samples 10 \
  --cold-timeout 60 --warm-timeout 120 \
  --scratch models/tmp/performance-document-full-paired \
  --baseline-report scripts/bench/cadgen-performance/document-engine/results/full-paired-legacy.json \
  --candidate-report scripts/bench/cadgen-performance/document-engine/results/full-paired-current.json \
  --comparison-report scripts/bench/cadgen-performance/document-engine/results/full-paired-comparison.json
```

Reports and raw JSONL journals record the actual alternating order. Each cold
sample is a pair of fresh adapters. Each warm pair alternates first engine by a
whole persistent scenario block; it does not claim sample-by-sample
interleaving. Comparison ratios require this exact boundary identifier, the
same required-STEP contract, identical accepted entry digests, stable runtime
trees, byte-attested outputs, complete independent saved-file oracles, and a
timing-qualified environment. The harness reports medians and observed ranges,
never p95.

`profile_unchanged.py` is a diagnostic for unexplained warm overhead. Run it
with `PYTHONPATH` pointing at the exact archived candidate runtime, once for
each fixture and one process at a time. It primes a direct `DocumentService`,
then profiles ordinary captured-source replay and STEP publication inside the
native owner process:

```sh
PYTHONPATH="$CANDIDATE_ARCHIVE/packages/cadgen/src" "$CAD_PYTHON" \
  scripts/bench/cadgen-performance/document-engine/profile_unchanged.py \
  --model plate --source models/performance_document/plate.py \
  --scratch models/tmp/performance-document-profile-plate \
  --report models/tmp/performance-document-profile-plate.json \
  --candidate-revision "$CANDIDATE_REVISION"
```

The helper requires one exact source execution and one actual-byte STEP receipt
per profiled call. It excludes `DocumentWorker` IPC, and cProfile changes the
elapsed cost, so its timings are attribution evidence only. Do not combine them
with `fullRequestMs` or use them in engine ratios.

The runtime archive contains only `packages/cadgen/src` from the named commit
and lives under `/private/tmp`. `full-paired` archives current HEAD there too;
both engines and the common readback use those immutable archives, so later
working-tree edits cannot alter an active series. The report records the exact
candidate HEAD used and whether the checkout HEAD moved afterward. Fixture
work, STEP output and private stores live
under the requested `models/tmp` directory. The harness kills only daemon PIDs
returned by its private socket and verifies their cleanup.

See [CONTRACT.md](CONTRACT.md) for the frozen semantics, counter hook, oracles,
format matrix and provisional memory budgets. [BASELINES.md](BASELINES.md)
separates trustworthy historical observations from fresh harness results.
`freecad_reference.py` supplies the equivalent retained FreeCAD plate and
24-occurrence operations; its stages remain separate from source-command time.
When FreeCAD is installed, run each model independently:

```sh
python3 scripts/bench/cadgen-performance/document-engine/freecad_reference.py \
  --freecad /Applications/FreeCAD.app/Contents/Resources/bin/FreeCADCmd \
  --model plate --samples 5 \
  --scratch models/tmp/performance-document-freecad-plate \
  --report scripts/bench/cadgen-performance/document-engine/results/freecad-plate.json \
  --cadgen-report scripts/bench/cadgen-performance/document-engine/results/checkpoint.json
```

The FreeCAD report times edit plus recompute, an exact native volume query,
one prototype mesh, whole-document STEP export, and cold STEP readback as
separate stages. It uses private settings and does not touch a running GUI.
It passes only when every measured label, validity bit, volume, area, bound,
and solid/face/edge/vertex count matches the corresponding saved-file oracle
in a complete cadgen harness report.
The FreeCAD geometry edit rebuilds the complete plate factory and assigns it to
the retained occurrences. It is labeled as a whole-factory architecture
reference and does not claim feature-level dirty-hole recomputation.

## Native mesh quality comparison

`mesh_compare.py` is a bounded comparison harness for the candidate retained
document mesher. It feeds independent ownership copies of one native shape to
`cadgen._document.meshing` and to the former SURF plus cadgen-js tessellator.
The latter is a comparison oracle only; the harness does not install it as a
fallback or expose it to model authors.

Run the correctness and quality set with the CAD Python. Generated CGMESH,
SURF, TESS, and JSON files stay under `models/tmp`:

```sh
CAD_PYTHON="${CAD_PYTHON:-$(command -v python3)}"
PYTHONPATH=packages/cadgen/src "$CAD_PYTHON" \
  scripts/bench/cadgen-performance/document-engine/mesh_compare.py \
  --scratch models/tmp/document-engine-mesh-compare
```

The six bounded cases are a drilled and filleted plate, a translated cylinder,
sphere, torus, trimmed fillet/cut solid, and a modest curved boolean solid.
Each report checks exact native validity, volume, area and bounds; complete
face and nondegenerate-edge coverage; sampled triangle-centroid distance to
the corresponding trimmed native face; sampled display-edge distance; mesh
volume and face areas; normal/winding agreement; coordinate-welded closure;
and axis support extents as limited silhouette evidence. It records raw
triangle counts but never treats equal counts or equal numeric tolerances as a
quality proof. Centroid sampling is not a global Hausdorff bound, and axis
support does not compare full occluding contours; these limits are repeated in
the report. A completed report exits nonzero when either pipeline fails a
quality gate; that result is a finding, while exceptions indicate a harness or
fixture failure.

Without `--serial-window`, every stage time is labeled
`diagnostic-concurrent-functional-only`. Node process and module setup is a
separate cold boundary; decode, tessellation and packing are per-request warm
stages in one persistent worker. Python CAD imports are also separate, while
Python interpreter launch is explicitly excluded. Use `--serial-window` only
inside an externally reserved native-compute window; setting it is an
attestation by the operator, not automatic host-idleness detection.

## Installed dependency closure observation

`dependencies.py` counts installed logical files in the selected Python
dependency closure. It does not measure downloads, compressed packages, or a
minimal headless installation. On this host, the build123d closure occupied
449,070,691 bytes and had no missing packages. FreeCAD.app occupied
2,675,673,689 bytes. The raw `models/tmp/document-dependencies/report.json`
file remains a machine-local diagnostic and is not a frozen benchmark report.
