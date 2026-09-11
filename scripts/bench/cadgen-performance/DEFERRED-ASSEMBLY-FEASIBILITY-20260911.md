# Deferred assembly feasibility and private bounds spike

**Decision:** do not defer ordinary authored `Compound` construction. A smaller
post-body bounds optimization is feasible for a validated canonical descriptor,
using the existing `index/op` value mechanism. The private spike below establishes
exact bounds parity on seven fixtures; it does not establish an end-to-end speedup
or authorize publication reordering.

Reviewed Python: `8971f760dcf7f5ccd0dd29a19d67201ebd3523e6`. All 182 copied
`cadgen` Python files match both current source and the measured `2709968dc`
archive. No production, dependency, or archived runtime was changed.

## Why transparent Compound deferral is unsound

The installed build123d 0.11.1 `topology/composite.py:136–172` reads each
`obj` member's `wrapped` during construction. `children=` instead runs normal
anytree validation/attachment, whose hooks rebuild the native compound
(`:846–898`). These are observable native ownership and error boundaries.

For example, after `a = Compound([child])`, replacing `child.wrapped` must not
replace the native value already captured by `a`. Conversely, an in-place edit
to their shared native TShape must remain visible. Re-reading the child later
gets the first case wrong; reconstructing its original immutable pin gets the
second wrong. Labels, placement, attachment, subclass hooks and callbacks add
similar construction-time distinctions. A correct general solution would need
to reproduce a connected mutable ownership graph and its callbacks, not merely
save a list of pins until `a.wrapped` is read.

Current bounded sibling preparation deliberately retains those boundaries:
[`_ready_children.install`](../../../packages/cadgen/src/cadgen/store/_ready_children.py#L182)
captures eligible arguments but calls the original constructor;
[`LazyCompound._force`](../../../packages/cadgen/src/cadgen/store/lazy.py#L284)
consumes a private result only at the ordinary force point. Native and descendant
metadata integrity still decide links in
[`_walk_compound`](../../../packages/cadgen/src/cadgen/store/build.py#L304).
Deferring construction also would not by itself remove the initial XCAF scene
build in
[`_write_shape_step_payload`](../../../packages/cadgen/src/cadgen/_internal/generation_runner.py#L239).

Exact child pins and
[`BuildFrame.wait_children`](../../../packages/cadgen/src/cadgen/authoring.py#L120)
can preserve discarded-call output completion, but do not solve those mutation
semantics. Saved-file readers must continue to use the emitted STEP bytes and
their verified canonical readback, independently of an authored preview.

## Cost ceiling and existing bounds reuse

The [frozen split study](results/split-frozen-siblings-summary-20260911.json)
reports these current medians in milliseconds:

| Edit | Source preview | Complete save | Private document preparation | STEP readback |
|---|---:|---:|---:|---:|
| Repeated geometry | 227.5 | 420.1 | 18 | 27 |
| Repeated placement | 183.1 | 413.2 | 18 | 32 |
| New geometry | 267.4 | 950.0 | 23 | 272 |
| New placement | 232.7 | 674.8 | 19 | 256 |

Preparation samples span 17–28 ms. Moving that work after preview could remove
at most that measured stage from the preview path, before paying new validation
and lookup costs; it does not remove document construction from a completed save.
Stages are rounded and some are nested. These are three-sample sequential
observations with uncontrolled user/host activity, not a causal interleaved test.
The older [stage profile](results/split-stage-profile-summary-20260910.json)
also includes child wait inside force time; that whole interval is not removable
native work. New-output raw STEP readback remains the largest measured save
stage. Exact-output readback caching already handles previously seen bytes.

Existing metadata is insufficient for a direct replacement. A rotated local
AABB generally overbounds a curved part. SURF's
[`_bnd_box`](../../../packages/cadgen/src/cadgen/_internal/surface_extract.py#L82)
can fall back from `AddOptimal` to `Add`, unlike the document bound helper.
The existing
[`occurrence_bbox.optimal.untranslated.v1`](../../../packages/cadgen/src/cadgen/_internal/component_package.py#L217)
memo still constructs a current native digest before lookup. A canonical BREP
object hash is not that normalized native digest and cannot be substituted into
its key domain.

## Exact boundary supported by the private spike

The candidate uses a separate measurement name in the existing op index:
`private.component_bbox.canonical_full_placement.v1`. Its input is verified
canonical BREP bytes identified by their digest, plus all 16 placement doubles
encoded exactly as bytes. It privately reconstructs and places the component
using the same
[`materialize_descriptor`](../../../packages/cadgen/src/cadgen/store/materialize.py#L572)
helpers, calls the existing `_bbox_from_shape`, and caches only six finite
numbers. No native object, new object family, or author API is introduced.

The sufficient implementation conditions are stricter than “the test fixtures
passed”:

- Capture verified tree/BREP/SURF snapshots and a complete occurrence/hierarchy
  bijection. Only the standard descriptor materializer may define the scene;
  no user callbacks, malformed nodes, missing occurrences, or alternate builder.
- Use the same exact placement conversion, canonical reconstruction, native
  leaf traversal and bound helper. Generated grouping compounds have identity
  placements; preserve their child traversal order, including signed-zero ties.
  Keep internal native compound leaves inside the existing helper.
- Merge the helper's already-final world-coordinate extrema. Do not transform
  cached AABB corners, round matrix keys, reassociate translation after a merge,
  or replace leaf-wise bounds with one different native bounding operation.
- Validate finite, closed, ordered extrema and verified byte limits. Any
  unsupported shape/transform, incomplete graph, invalid value, lost object, or
  native failure uses the existing whole-document path. A miss derives from
  private bytes; it must not borrow a live authored shape.

This partition follows the current algorithm, not a general claim about OCCT
boxes. [`AddOptimal`](https://raw.githubusercontent.com/Open-Cascade-SAS/OCCT/V7_9_3/src/BRepBndLib/BRepBndLib.cxx)
has face/edge-specific extrema and gap handling.
[`Bnd_Box::Add` and `Get`](https://raw.githubusercontent.com/Open-Cascade-SAS/OCCT/V7_9_3/src/Bnd/Bnd_Box.cxx)
merge raw extrema and the maximum gap, then expand on `Get`; arbitrary merging
of those boxes is not interchangeable with the runtime's per-leaf numeric
merge. Identity grouping does not add another numeric transform:
[`TopoDS_Iterator`](https://raw.githubusercontent.com/Open-Cascade-SAS/OCCT/V7_9_3/src/TopoDS/TopoDS_Iterator.cxx)
skips moving children for an identity parent, and
[`TopLoc_Location::Multiplied`](https://raw.githubusercontent.com/Open-Cascade-SAS/OCCT/V7_9_3/src/TopLoc/TopLoc_Location.cxx)
returns the other operand for identity composition.

The [raw proof](results/descriptor-bounds-parity-spike-20260911.json) embeds the
helper, all copied-source hashes, dependency hashes, object provenance and exact
bounds. Seven cases passed cold-key, RAM and disk paths: nine-part planetary;
holes; rotated NURBS cylinder/sphere; a native nested component; repeated
instances; mixed native tolerances; and mirrored, placed nested groups.
All **21 comparisons matched both canonical JSON and all six double bytes**.
Twelve negative checks cover missing/corrupt trees, BREP and SURF after cache
hits, malformed/deleted op entries, unsupported cached values, nonfinite
placement, unsupported hierarchy and absent native bounds.

The planetary helper observed 2.15 ms on a RAM hit and 2.39 ms on disk,
including verified component reads; its cold outer key took 41.98 ms. These are
single functional observations, not benchmark results. The candidate excludes
descriptor capture, appearance and whole-document assembly. Control ran first
and can warm the inner bounds memo. Its 63.19 ms combined materialization/bounds
observation is therefore not an end-to-end baseline or a justified savings claim.
All artifacts and store writes are under `models/tmp/descriptor-bounds-spike-20260911`;
the fresh private runtime is under `/private/tmp`, not the measured archive.

## One bounded next implementation plan

First integrate only a validated descriptor-bounds provider into a private copy
of [`build_tree_through_step`](../../../packages/cadgen/src/cadgen/store/build.py#L886),
keeping the existing document preparation and publication order. Reuse
`index/op` with an explicit kernel/bounds algorithm identity; retain normal
forced derivation and whole-document fallback. Compare complete tree bytes and
STEP bytes across cold, warm, disabled memo, force, deletion and repair paths,
including changed placements, face colors, nested links and internal compounds.

Only after that proof should a separate change consider moving private document
preparation after source publication. It must capture geometry **and** appearance
before the callback, reverify consumed pins, preserve output waiting and errors,
and test caller mutation, cache deletion/repair, cancellation and reentrancy
during that wait. New own components without complete verified addresses and
any unsupported descriptor should retain today's order. STEP export,
authored-to-written correspondence and truthful canonical readback remain
unchanged. This spike proves the bounds measurement boundary; it does not yet
prove that broader publication lifecycle or a useful complete-build speedup.
