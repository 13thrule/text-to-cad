# Exact-reference assembly composition

Eligible decorated-child assemblies now avoid reconstructing their native child
containers, reserializing their unchanged geometry, and constructing the first
XCAF scene before source preview. A nine-part, 582-face planetary assembly
improved from **142.8 to 92.4 ms to source preview** and **374.1 to 322.2 ms to
complete save** in the bounded warm comparison. Every enabled/disabled pair
produced the same TREE hash and actual STEP bytes.

This is the R1 increment on `codex/tendon-hand-performance`. It introduces no
native-shape LRU, store schema, author decorator, FreeCAD dependency, or changes
to immutable object and atomic-index meanings.

## Scope and ownership

The constructor fast path accepts an exact plain `Compound` with `obj=None`,
`parent=None`, and an exact list/tuple containing **2–64 distinct, unparented,
unforced `LazyCompound` wrappers from the active build frame**. Placements must
be ordinary `Location`, `Pos`, or `Rot` values, and child label/color values
must have their standard types. Child material/face overrides, occurrence-tree
overrides, native tags, subclasses, mixed inputs, nested constructor calls and
other unsupported cases use the ordinary path. Both current and queued child
jobs qualify; queued results resolve in the original attachment order.

An eligible root is temporarily an internal `_ReferenceCompound` subclass.
`isinstance(root, Compound)` remains true, but **`type(root) is Compound` is
observably false until native access**. That is an intentional, documented
change to exact-type introspection. The instance becomes an ordinary Compound
only after its correct native container has been installed. The original
constructor still performs argument checking, anytree attachment and rollback.

Native root reads/writes, copy, deepcopy, pickle, bounds, booleans and hierarchy
edits force ordinary geometry. A child's native escape, wrapper replacement,
native placement edit, or hierarchy edit first captures its parent's original
native inputs. This preserves the distinction between a replaced wrapper and
an in-place edit to shared native topology. Direct `plain_shape.parent = child`
is covered through anytree's private child-list accessor as well as its public
children property. No retained prototype escapes to authored code.

Only the source-publication call in `_generate_step_outputs` opts into the
lightweight `LoadedStepScene`. It owns real private native shapes decoded once
per distinct full geometry identity, along with occurrence transforms, names,
colors and face appearance. Repeated child calls retain separate prototype
keys, preserving the existing adaptive topology counts. The scene's consumers
before final save read those shapes; canonical publication prepares its own
private document. Other native scene/export callers keep the ordinary XCAF
path. There is no cross-build native ownership or RAM substitute for a saved
document.

Each private constructor/packaging snapshot verifies each unique exact tree
once. A later source-scene, link, or native consumer verifies required objects
again. Final publication still verifies its complete required closure. Missing
or corrupt objects cannot be hidden by a prior RAM snapshot, and later source
edits or records cannot replace an earlier child pin. Declared child outputs,
including discarded calls and failed mesh exports, still gate parent commit.

The broad deferred-constructor approach rejected in the earlier
[feasibility report](DEFERRED-ASSEMBLY-FEASIBILITY-20260911.md) remains unsuitable.
This implementation restricts eligibility and intercepts the native escape and
hierarchy boundaries that made an unrestricted list-of-pins approach incorrect.

## Bounded paired measurements

All numbers are medians of three paired placement revisions, in milliseconds.
The ordinary path is the same working tree with only `_references._ENABLED`
disabled. Pair order alternates. The process/kernel and child output records
are warm; each exact revision's artifact readback and scalar entries are
prewarmed before either timed member. These measurements therefore do **not**
include cold startup, cold child construction, unseen STEP readback, meshing,
network delivery, or browser first frame. Source preview and complete save are
separate timestamps from an actual `run_model_argv` invocation.

| Fixture | Preview ordinary → reference | Improvement | Complete ordinary → reference | Improvement |
|---|---:|---:|---:|---:|
| 2 occurrences, box/torus | 20.413 → 19.667 | 3.7% | 34.268 → 34.169 | 0.3% |
| 9 occurrences, 3 distinct geometries | 34.338 → 29.069 | 15.3% | 56.287 → 53.094 | 5.7% |
| 24 occurrences, 3 distinct geometries | 60.917 → 40.372 | 33.7% | 91.679 → 70.562 | 23.0% |
| 9-part planetary, 582 faces | 142.800 → 92.413 | 35.3% | 374.107 → 322.157 | 13.9% |

The small corpus uses a box, torus and drilled block. The medium corpus uses
the existing split planetary geometry; the root uses `Compound(children=parts)`
instead of its redundant `obj=parts, children=parts` arguments. All other source
files are identical to the durable split fixture. Nine child outputs are seeded
before its three parent revisions. No giant assembly was built.

| Work counted | 24-occurrence preview | 24-occurrence complete | Planetary preview | Planetary complete |
|---|---:|---:|---:|---:|
| Native BREP decodes | 27 → 6 | 33 → 12 | 18 → 18 | 36 → 36 |
| Native BREP serializations | 48 → 0 | 51 → 3 | 18 → 0 | 27 → 9 |
| XCAF document constructions | 1 → 0 | 2 → 1 | 1 → 0 | 2 → 1 |
| Authored child materializations | 24 → 0 | 24 → 0 | 9 → 0 | 9 → 0 |
| Surface extractions | 0 → 0 | 0 → 0 | 0 → 0 | 0 → 0 |

The first implementation verified the same tree repeatedly per occurrence;
its 24-occurrence preview gain was only about 9%. Sharing verification within
each private snapshot made the larger difference shown here without removing
the next consumer's or final publisher's checks.

An initial private deep-copy feasibility study was rejected: box/sphere/torus/
drilled-block clone savings were only about 18–37 microseconds per shape, and
the drilled block's serialized BREP changed by 43 bytes despite equal volume.
The implementation does not infer arbitrary OCCT fidelity from volume or one
serialized comparison.

## Evidence and reproduction

Raw paired samples, counters, exact hashes and the original measurement method
are in [small results](results/reference-assemblies-small-20260911.json) and
[planetary results](results/reference-assemblies-planetary-20260911.json).
There were 18 small and 6 planetary timed calls, with 9 and 3 exact-revision
prewarms respectively. Each helper had an 85-second alarm; the coordinated
combined measured workload completed in roughly 15 seconds. Python was
`/Users/jakefitzgerald/robots/text-to-cad/.venv/bin/python`, using this worktree's
`packages/cadgen/src` on `PYTHONPATH`. No environment installation was changed.

The consolidated durable [helper](reference_assemblies.py) reproduces the same
sampling and assertions and creates CAD artifacts only in a disposable
`models/tmp` directory. From the repository, with an installed CAD Python:

```sh
PYTHONPATH=packages/cadgen/src:. "$CADGEN_PYTHON" scripts/bench/cadgen-performance/reference_assemblies.py --fixture small --result /tmp/reference-small.json
PYTHONPATH=packages/cadgen/src:. "$CADGEN_PYTHON" scripts/bench/cadgen-performance/reference_assemblies.py --fixture planetary --result /tmp/reference-planetary.json
```

The planetary source must be available locally under
`models/examples/performance/planetary_split/src`; the helper copies its sources
and changes only the redundant root constructor arguments. Run timing helpers
serially without competing native or Node workloads. The helper itself was
syntax-checked after consolidation; the recorded runs used the original
equivalent temporary helpers.

## Correctness and remaining validation

The final native-escape/hierarchy correction passes **90 focused tests in
6.650 seconds** across `test_reference_assemblies`, `test_ready_children`,
`test_lazy_children`, `test_materialized_identity`, and `test_materialize_caches`.
Coverage includes exact cold/warm/disabled/forced TREE and STEP parity; intrinsic
rotated roots; inherited colors, material and face overrides; mutation and
replacement; missing/corrupt objects and repair; queued failures; exact pins;
and a real decorated public build with non-default mesh tolerances and fresh
worker restart. The eligible source path still asserts zero authored-child
materializations after that correction.

Before the final escape correction, **34 reference and source-job tests passed
in 32.565 seconds**, including two-placement reference roots previewing while a
child save is blocked, discarded child output completion, child STEP/mesh
failure preserving the parent, and mesh-only parent ordering. The final
correction affects native escape, not the unexposed source path; timings were
not rerun after that correction. Integrated suite reruns, package/bundle checks
and overall performance acceptance belong to the parent integration task.
No commit, release version change, or runtime bundle was made by this subtask.
