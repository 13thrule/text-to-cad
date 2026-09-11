# Deferred assembly feasibility and private bounds spike

**Decision:** preserve ordinary authored `Compound` construction. The bounded
post-body candidate passed exact-output checks and an interleaved nine-part
comparison, and the provider and internal publication increment passed independent
review and are integrated. The implementation does not defer authored native access or change
saved-file semantics. Its preview gain is modest; completed saves remain far
above 250 ms.

The initial review used Python `8971f760dcf7f5ccd0dd29a19d67201ebd3523e6`,
whose 182 files matched the measured `2709968dc` archive. The final comparison
adds the identical later operation-cache v7 LRU/native-identity correction
(`a862c3d1e`, file SHA `20db00495955e00911e08d00abc66811edc09009070412974b8a1ec71ccd0464`)
to each fresh private copy. The measured archive was preserved; this investigation
made no production, dependency, bundle or Git changes. The reviewed production
delta was subsequently applied with every base and candidate file hash verified
and committed as `47b2f94e6`. Its 22 focused tests, all 1,619 integrated package
tests and the source-free installed-wheel export proof pass.

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

## Final private implementation and comparison

The provider uses `component_bbox.canonical_full_placement.algorithm1` through
the existing numeric op index, with the actual native/binding identity in its
key. A separate internal-only increment captures verified tree/BREP/SURF bytes,
full occurrence/group metadata and immutable face-color recipes. Before the
source callback, it decodes every unique native BREP, privately copies topology
for appearance variants, and validates every native placement. Those same
prototypes supply bounds misses; only the ordinary occurrence/group assembly
moves after the callback. A warm scalar hit never certifies native validity.
Direct callbacks, force, new own components and unsupported inputs retain the
ordinary order. The existing child-output wait and disk-closure check stay in
place, with no post-callback lookup of a newer child or reconstruction input.

Limits are 64 occurrences, 16 components, 32 trees and depth 32; 64 KiB each for
aggregate tree bytes and flattened descriptor, 768 KiB BREP, 4 MiB SURF and
256 KiB retained appearance recipes. Accounted retained payload/recipes total
at most 5.125 MiB, plus bounded Python/native overhead. This is not an RSS cap.
A failed optional preparation releases its owners before ordinary fallback.

The [summary and all sample ranges](results/descriptor-bounds-interleaved-summary-20260911.json)
and [compressed complete proof](results/descriptor-bounds-interleaved-20260911.json.gz)
record the single comparison at **01:50:54.314–01:52:21.211 UTC**. Each condition
used one warm root interpreter and its own two-worker daemon/store. Kernel
startup, controller waiting and source writes were outside each build timer;
normal child IPC, source preview and declared-output completion were included.
All 96 calls succeeded. Each checked the actual root and nine child STEP files;
all 32 cross-condition source/document/STEP/pin comparisons matched. Every owned
daemon exited zero, source bytes/mtimes were restored, and runtime hashes stayed
fixed. A preliminary IPC-permission failure performed zero CAD calls and is
preserved separately in the proof.

Median milliseconds; each cell is **preview / complete call**:

| Edit | Common-v7 baseline | Bounds provider | Provider + internal deferral |
|---|---:|---:|---:|
| Repeated geometry | 221.1 / 421.5 | 204.8 / 406.9 | 205.8 / 421.7 |
| Repeated placement | 190.6 / 398.8 | 168.6 / 372.0 | 163.9 / 375.4 |
| New geometry | 235.4 / 655.3 | 227.6 / 659.7 | 214.8 / 649.4 |
| New placement | 185.6 / 612.9 | 171.5 / 600.7 | 160.7 / 597.9 |

There are three trials per repeated edit, and three distinct never-seen values
executed once each per condition. Order repeats baseline/provider/lifecycle,
lifecycle/provider/baseline, then provider/baseline/lifecycle: interleaved but
not perfectly balanced by position. User/host activity was uncontrolled. No
samples were removed: provider repeated geometry included a 270.5 ms preview /
622.1 ms complete outlier; baseline and lifecycle also had save-time outliers.
This is a small comparison, not a tail-latency guarantee.

Provider preview improved in 11/12 paired edits; the full candidate improved in
12/12. Median paired preview changes for the full candidate were −16.2, −26.7,
−22.2 and −24.2 ms for the four rows above. Complete-call median differences
were approximately neutral for repeated geometry and 6–23 ms lower elsewhere;
individual saves varied substantially. Native readback of new output bytes
still took about 250–257 ms and remains the larger save-stage target. The result
supports the narrow preview optimization, not an assertion that document
construction was eliminated or that every save became faster.

The private provider passed 10 tests/20 full equality rows; the final lifecycle
passed 21 tests/40 full equality rows across box, holes, NURBS and the moderate
planetary fixture. These compare complete source trees, STEP bytes, canonical
document hashes, face/PBR appearance and occurrence/node maps. Real cached scalar
entries for malformed BREP and singular placements still produced the same
pre-preview failure as the ordinary path, with no preview callback or STEP file.
Mutation, reentrancy, cache deletion, discarded-child output failure, force,
disabled memo, byte budgets and fallback ownership are covered.

The production-ready delta uses only small generated fixtures and ordinary repo
test support: 22 focused tests pass, including distinct face-color components
sharing one BREP and requiring separate private topology. Its executable runtime
AST matches the measured lifecycle candidate after removing documentation and
type annotations. Package-contained docs, tests, exact base/file hashes and the
ready patch are preserved with the final proof. No extra timing was run for this
packaging-only cleanup.
