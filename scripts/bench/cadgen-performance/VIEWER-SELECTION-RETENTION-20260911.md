# Selection updates retained old detail generations

Preserving unchanged selection arrays removes the demonstrated retention chain
during repeated detail upgrades. The isolated nine-part comparison retains
9 workspace contexts and 5 assembly maps, down from 503 contexts and 250 maps.
It does not establish that every viewer interaction is free of retention.

| After the same 20 zoom cycles and 246 detail adoptions | Original `2709968dc` | Only selection fix |
| --- | ---: | ---: |
| Strongly reachable workspace contexts | 503 | 9 |
| Distinct assembly maps / valid-leaf sets | 250 / 250 | 5 / 5 |
| JavaScript heap after collection, decimal MB | 21.419 | 16.430 |
| Backing storage after collection, decimal MB | 19.953 | 3.393 |
| Final component levels | 6 L0 / 1 L1 / 2 L2 | 6 L0 / 1 L1 / 2 L2 |

Backing storage includes ArrayBuffers and external strings. These are quiescent
retention measurements; neither diagnostic peak RSS nor pre-collection heap
size is a normal-viewing memory benchmark. Inspector snapshot work is included
in the diagnostic peak.

A separate [full-hand run](results/hand-canonical-l1-selection-identity-summary-20260910.json)
passes the unchanged 2 GiB limit: all 866 components reach L1, retaining 3,259
occurrences, at a peak renderer RSS of 1,482 MiB. The preceding unpatched run
crossed 2 GiB at 654 L1 / 212 L0. The candidate completes in 97.581 seconds;
all L0/L1 meshes are cached, and no forced collection or allocation sampling
runs before grading. This validates memory headroom, not a matched latency
improvement. The candidate excludes the concurrent scene-recovery changes;
the combined runtime still requires validation.

## Cause and change

Every detail publication creates new containers for valid selection IDs. The
selection effect previously filtered the selected-part, selected-reference and
hidden-part lists into new arrays even when their contents were unchanged.
That caused another workspace render and regenerated persistence callbacks.
Those callbacks and assembly callbacks retained alternating historical render
contexts, including maps and geometry reachable from those contexts.

The [original strong-path proof](results/viewer-nine-retainer-paths-20260910.json)
contains 245 transitions that preserve assembly maps while replacing selection
arrays, alternating with 245 transitions that preserve selection arrays while
replacing assembly maps, with no exceptions along the recorded path. All those
selection arrays are empty. The path remains rooted in DOM/React state after
excluding every diagnostic `__cad*` edge. Removing only two named callback
edges does not disconnect the old contexts; other callbacks share the same
lexical scope.

The change keeps the existing selection lists when every ID survives. Actual
removals still produce a filtered list with the same order and duplicates, and
the same predicates still prune invalid part/reference/hidden IDs. Empty-state
clearing also preserves an already-empty list. No geometry, cache identity,
authoring interface or saved-file behavior changes.

## Verification

The [original capture](results/viewer-nine-retainer-20260910.json.gz) and
[isolated candidate](results/viewer-nine-retainer-selection-identity-20260910.json.gz)
use the same medium assembly, warm detail cache and 800%/100% sequence. Each
leg waits for actual detail/adoption/worker idleness. Both captures prove
quiescence before collection and unchanged publication/adoption state through
the snapshot, with all nine parts present and no page or HTTP errors.

The candidate archives `2709968dc` and changes only the selection hook and its
small value helper/test. Its 474 archived source blobs are checked against the
commit; actual served client and worker assets and installed dependencies are
verified. Concurrent scene-recovery implementation in the main checkout is
excluded. The [candidate path analysis](results/viewer-nine-retainer-selection-identity-paths-20260910.json)
records exact remapped bindings, snapshot hashes and strongly reachable nodes.
Raw heap snapshots remain local, outside Git; compact structural evidence is
retained here.

Nineteen focused value, selection and isolation tests pass, and independent
review finds no change to nonempty pruning or hover behavior. A separate
[functional browser check](results/viewer-nine-selection-identity-functional-20260910.json)
passes seven assertions: selecting `carrier_plate` survives detail changes at
800% and 100%; Hide removes that part and dims its row while retaining the other
parts. Both screenshots were visually reviewed. A failed functional-harness
locator attempt is preserved separately and is not an application failure.
