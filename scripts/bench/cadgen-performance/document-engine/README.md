# Retained-document P0 benchmark

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

The runtime archive contains only `packages/cadgen/src` from the named commit
and lives under `/private/tmp`. Fixture work, STEP output and private stores live
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
