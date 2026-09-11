# Pure intermediate factories: R2 validation, 2026-09-11

`@feature` adds optional reuse of expensive, parameterized intermediate CAD
factories. It skips the factory's Python/builder work, in addition to the
existing kernel-operation cache. It writes immutable BREP objects and ordinary
operation-index entries; the enclosing `@step` model still owns the build,
dependency closure and exports. No FreeCAD dependency or extra authoring cache
helpers were introduced.

This is an explicit **pure factory contract**, not automatic purity certification.
See [the public contract](../../../packages/cadgen/FEATURES.md). The implementation
declines unsupported inputs/code/contexts and provides bounded defensive runtime
checks. Arbitrary dependency mutation and observable side effects are outside
the contract. A fresh worker establishes the runtime witness before authored
source loads; generic embedded execution does not reuse feature results.

## Matched public source-edit builds

The durable [harness](feature_factories.py) constructs assemblies of drilled
plates through an actual `@step` parent and separate `@feature` helper module.
Each source revision changes the assembly placement. A separate request constant
makes both variants execute the model even when their final geometry is identical.
The helper has six possible width/hole-count combinations; larger cases repeat
those prototypes. The largest case has 24 occurrences and a 318,202-byte STEP.

Both modes use the same current branch, warm `op_memo`, worker bootstrap and
canonical-return semantics. “Before” is `CADGEN_FEATURE_CACHE=0`; “after” enables
feature result reuse. This isolates R2 and is not a comparison against the entire
branch's original baseline. Source-file writes and worker startup are excluded.
Three pairs per size alternate execution order. Figures are medians in
milliseconds, including every ordinary public-build stage after the call starts.
New output revisions are not individually prewarmed for equal STEP readback
cost: the first condition can pay the new readback while the second reuses it.
Complete-save medians are therefore public-path observations with this order
limitation. Preview timing is shown separately.

| Assembly | Source result before → after | Preview event before → after | Complete STEP save before → after |
| --- | ---: | ---: | ---: |
| 3 parts | 171.5 → 48.9 (3.51×) | 171.6 → 49.0 (3.50×) | 206.3 → 74.9 (2.75×) |
| 9 parts | 583.8 → 123.5 (4.73×) | 583.8 → 123.6 (4.72×) | 675.6 → 173.8 (3.89×) |
| 24 parts | 1,603.0 → 235.2 (6.82×) | 1,603.1 → 235.3 (6.81×) | 1,704.0 → 309.0 (5.51×) |

Every matched pair produced **identical tree addresses and exact STEP bytes**.
Enabled runs recorded one feature hit per part; disabled runs recorded one
executed miss per part. The preview event means source geometry is available to
the viewer pipeline; it does not measure a browser frame. Complete save includes
ordinary persistence and STEP readback. The run completed within its 90-second
outer-process deadline; no giant assembly was used.

Raw observations, output identities, dependency versions and runtime source
hashes are in [feature-factories-20260911.json](results/feature-factories-20260911.json).
Measured on macOS 26.5.1 arm64, Python 3.13.13, build123d 0.11.1 and
cadquery-ocp-novtk 7.9.3.1.1. Native/browser timing windows were serialized with
the other work in this branch.

Reproduce from the repository root with a configured CAD Python environment:

```sh
PYTHONPATH=packages/cadgen/src .venv/bin/python \
  scripts/bench/cadgen-performance/feature_factories.py \
  --parts 3 9 24 --repeats 3 --timeout 90 \
  --output models/tmp/feature-factories-benchmark \
  --report models/tmp/feature-factories-benchmark/report.json
```

The harness creates its fixtures and CAD outputs only under `models/`. Its
generated outputs are not committed. A checkout can substitute another existing
CAD Python environment without copying it into the worktree.

## One local geometry edit

A separate nine-part run changes the width argument of occurrence 0 from its
70 mm baseline to 71, 72 and 73 mm. The other eight occurrences keep their
original arguments and placements. The six baseline factory combinations are
primed first in an independent store; each measured width is new to the feature
cache. This measures a local geometry change, rather than an all-hit placement
edit.

Each enabled run recorded **eight hits and one executed miss**; each disabled
run executed all nine factories. Every enabled/disabled pair produced identical
tree addresses and exact STEP bytes. Against the baseline, only occurrence 0's
component and BREP identity changed. All nine placements and all eight other
component/BREP identities stayed identical.

| Nine-part local edit | Reuse disabled | Reuse enabled | Speedup |
| --- | ---: | ---: | ---: |
| Source result | 578.2 ms | 140.0 ms | 4.13× |
| Preview event | 578.3 ms | 140.1 ms | 4.13× |
| Complete STEP save | 675.2 ms | 190.6 ms | 3.54× |

These are medians of three pairs. Each new output revision was **not separately
prewarmed for equal STEP readback cost**. Alternating pair order reduces but does
not eliminate that difference: the first condition can pay for the novel STEP
readback and new kernel operations; the second can reuse them. With three pairs,
reuse is second twice. Complete-save figures are public-path observations with
that limitation, not isolated recomputation or writer timings. Preview gains
are reported separately and still do not measure a browser frame.

| Width | First condition | Preview disabled → enabled | Complete save disabled → enabled |
| --- | --- | ---: | ---: |
| 71 mm | Reuse disabled | 592.9 → 137.5 ms | 692.2 → 186.3 ms |
| 72 mm | Reuse enabled | 563.1 → 163.3 ms | 615.3 → 261.5 ms |
| 73 mm | Reuse disabled | 578.3 → 140.1 ms | 675.2 → 190.6 ms |

The six timed public calls completed within the 60-second process deadline.
The [separate raw observations](results/feature-local-geometry-20260911.json)
retain pair order, all occurrence/component/BREP identities and runtime source
hashes. Earlier placement measurements and their raw file remain unchanged.

```sh
PYTHONPATH=packages/cadgen/src .venv/bin/python \
  scripts/bench/cadgen-performance/feature_factories.py \
  --scenario local-geometry --parts 9 --repeats 3 --timeout 60 \
  --output models/tmp/feature-local-geometry-benchmark \
  --report models/tmp/feature-local-geometry-benchmark/report.json
```

## Cost and scope

A separate five-repetition diagnostic compared ordinary undecorated factory
bodies with fully guarded feature hits, with ordinary `op_memo` enabled in both.
Ordinary/cached volumes and first-canonical/hit byte comparisons passed. The
median defensive runtime check alone was 3.86 ms; it is deliberately conservative.

| Factory | Holes | Ordinary body | Feature hit | Speedup |
| --- | ---: | ---: | ---: | ---: |
| Algebra booleans | 2 | 2.30 ms | 5.32 ms | 0.43× |
| Algebra booleans | 6 | 7.28 ms | 4.66 ms | 1.56× |
| Algebra booleans | 12 | 17.85 ms | 4.74 ms | 3.77× |
| BuildPart builder | 2 | 8.00 ms | 4.81 ms | 1.66× |
| BuildPart builder | 6 | 28.94 ms | 4.56 ms | 6.34× |
| BuildPart builder | 12 | 74.95 ms | 4.77 ms | 15.72× |

[Diagnostic observations](results/feature-factory-micro-20260911.json) illustrate
why this decorator belongs on costly helpers, not every primitive. The public
source-edit table above is the reproducible end-to-end acceptance benchmark.

These gains require reusable pure factories. Changing factory/helper code or
keyed parameters recomputes affected results. Editing another function in the
same source file conservatively invalidates its factories too. Arbitrary
monolithic Python is not transformed into a FreeCAD-style feature graph, and
these results do not establish overall FreeCAD parity or a 100× application
speedup. They demonstrate selective recomputation without replacing build123d
or adding a mutable document/cache framework.

## Correctness coverage

The focused feature suites passed **23 tests in 12.14 seconds**:

```sh
PYTHONPATH=packages/cadgen/src .venv/bin/python -m unittest \
  tests.python.packages.cadgen.test_features \
  tests.python.packages.cadgen.test_feature_build
```

Coverage includes cold/warm/disabled canonical equivalence, private returned
geometry, defaults/kwargs/arguments, actual helper/code/global/source changes,
deleted/corrupt object recovery, builder/location/workplane fallback, unsupported
attributes and wrappers, missing globals, fake modules, covered runtime/default
mutations, tuple-identity and NaN input rejection, child/file dependency fallback,
kernel-free decorator import, untrusted embedding, and public `@step` edits.
Two fresh worker interpreters verify persistent feature hits and exact STEP
output equality after restart. A helper-source edit invalidates the parent and
changes its tree and STEP output. Independent cache-soundness review accepted
the implementation within the documented pure/value-input/unmodified-runtime
contract after the concrete alias and defensive guard regressions were fixed.
