# Private native mesh adapter — 10 September 2026

The native C++ packing path now produces the existing component, render and
selector structures with coherent face and edge identities. All seven fixtures
pass the boundary contract. This is a private prototype, **not a production
backend decision or a matched-quality result**. No runtime, dependency, cache
identity, canonical object/index or viewer behavior changed.

The [raw proof](results/rwgltf-adapter-20260910.json.gz) embeds the executed helper
versions, source hashes, input/output addresses, per-stage observations and full
audit rows. Candidate GLB, sparse metadata and TESS files are confined to
`models/tmp/rwgltf-adapter-20260910`. Each native child had a 60-second limit;
the successful seven-case extraction/adapter batch took about 9.7 seconds across
serial processes. Exact geometry audits ran separately and are not timing
comparisons. The completed large-component evidence predates the instruction to
stop hand-component experiments; subsequent comparisons use moderate fixtures.

## Concrete geometry and selector contract

Each input BREP is hash-verified, reconstructed privately, cleaned and meshed
once. Canonical `TopExp` face/edge ordinals agree with SURF. Named XCAF face
leaves preserve face identity through C++ GLB export. Sparse metadata captures
`PolygonOnTriangulation` node indices from that same mesh, explicitly selecting
both oriented representations of every closed seam.

The JS adapter merges these transport leaves into **one render primitive**,
converts units/axes, and builds face ranges, per-vertex face ordinals, opposite
triangle-side edge ordinals and canonical edge polylines. Every edge point comes
from an actual triangle vertex. All adjacent-face/seam sequences compare equal
at Float32 coordinate precision, allowing reversal and numeric equality of
signed zero. No independent curve sampling or snapping hides a disagreement.

| Fixture | Faces | Triangles | Seam pairs | Exact zero-area triangles | Normal flags |
| --- | ---: | ---: | ---: | ---: | ---: |
| Colored box | 6 | 12 | 0 | 0 | 0 |
| Perforated plate / cylindrical seams | 6 | 1,160 | 4 | 0 | 0 |
| Sphere poles | 1 | 29,946 | 1 | 2 | 0 |
| Cone apex | 2 | 2,855 | 1 | 1 | 0 |
| Torus seams | 1 | 27,300 | 2 | 0 | 0 |
| Trimmed NURBS | 10 | 10,168 | 1 | 0 | 0 |
| Previously selected slow component | 822 | 173,405 | 129 | 27 | 1 |

Every case has zero missing nondegenerate boundary polygons, conflicting side
labels, unlabelled face-boundary sides, absent polygon segments or cross-face
edge mismatches. All seam pairs use distinct local node sequences. The slow
case maps all 2,545 canonical edges and 33,741 labelled triangle sides.

`buildMeshDataFromSurf` and `buildSelectorBundleFromSurf` consume that same
component. Tests compare every display/proxy edge point, index and ID with its
component polyline; face runs tile every triangle and agree with the face
ordinal channel. Actual stock Three face rays and bounded line rays recover
the corresponding IDs. Encoded/decoded TESS arrays match byte-for-byte;
render-only surrogate-index loading and later SURF selector construction
produce equal render/selector arrays and manifests. Face-range colors survive
the codec, including two explicitly colored box faces.

## Processing phases and memory

The slow component's single isolated observation separates the actual adapter
work from the exact-geometry audits:

| Phase | Milliseconds |
| --- | ---: |
| Native read/verify, private reconstruction and maps | 20.84 |
| Serial native meshing | 1,631.26 |
| Sparse boundary extraction plus sampled triangle truth | 68.58 |
| Named-face document | 5.67 |
| C++ GLB write | 86.70 |
| Boundary JSON encode/write | 11.60 |
| JS SURF/metadata/GLB read, verify and parse | 27.37 |
| JS coordinate conversion and merged arrays | 40.57 |
| JS edge/side mapping and exhaustive boundary/relation checks | 154.30 |
| Render data / selector data construction | 1.31 / 37.37 |
| TESS encode / decode | 1.92 / 1.09 |
| **Recorded derivation stages** | **2,088.58** |

The cheap SURF scale preparation was measured separately afterward at 40.18 ms,
with unchanged numeric results. Neither figure includes process startup, final
coherence/raycast assertions, numeric audits or report serialization. Exact
GProps alone took 1,108.57 ms outside the derivation sum. The successful slow
controller operation took 4.25 seconds including startup and these checks.

The prior current-JS mesh-plus-encode sample was 6,763.42 ms; it omits its own
render/selector construction and uses different geometry. These numbers show
an opportunity, not an equal-quality end-to-end speedup. The native GLB hash
matches the earlier independently repeated reconstruction. The newly added
boundary/TESS payload was not independently regenerated twice.

Slow native and JS child peaks were 390.78 MiB and 213.39 MiB respectively.
Children ran sequentially; these are not a resident native worker plus Node
child's combined peak. The boundary carrier is 881,455 bytes. Input files and
imported shared code remained unchanged; unrelated app source changes were not
part of a whole-repository freeze claim.

## Surface accuracy and the projector artifact

The existing exact-surface audit inspected every facet on the box, perforated
plate, cone and trimmed NURBS. Dense sphere/torus cases used 258 deterministic
triangles each; the slow component used 2,841 triangles spanning every face.
It projects vertices, side midpoints and centroids. This is a finite sample,
not a continuous error bound or a full trim-containment proof.

The raw UV-limited projection reported 0.339905 mm on slow spherical face 140.
That is **not a demonstrated mesh error**: the same point is 0.004949944 mm
from the exact bounded face, and the independent sphere-distance formula agrees.
The projector selected a different stationary point near the trim boundary.
Its original audit only applies the boundary fallback to vertices, so a facet
midpoint can retain this overestimate. Raw results remain intact beside the
independent cross-check.

A different slow sample, on sphere face 194, is confirmed at 0.020349485 mm
against a requested chord of 0.018674139 mm. A NURBS sample on face 22 is
confirmed at 0.018924539 mm. The trimmed fixture's checked raw maxima of
0.004864 mm also overestimate bounded-face distances, which are 0.001330 mm
for those points. None of this establishes a global maximum or that every
native face meets the requested chord.

The identical prior numeric-array audit was reused without running its report
writer. All position/normal channels are finite and normals are nonzero/unit.
The sphere's two, cone's one and slow component's 27 collapse flags are all
**exact zero-area triangles** after transport. They contribute zero volume.
The remaining slow normal flag is on a noncollapsed cone triangle; its cause
and any repair remain unresolved. No triangles or normals were silently changed.

## Decision and next step

This original checkpoint did not provide matched-quality surface-deviation
evidence against current JS. Native has fewer flags and preserves the nine tiny
face ranges omitted by the earlier JS slow-component output, but triangle
counts, volume and this native-only projection audit cannot establish quality
equivalence. The subsequent [moderate-fixture comparison](RWGLTF-MODERATE-QUALITY-20260910.md)
uses common exact surface positions and reciprocal bounded-face checks. It
finds one unadjusted native exceedance, then tests a single uniform half-chord
margin against the original target. All seven moderate/small fixtures meet
that finite sampled target with the margin. No further hand-component workload
was performed for that comparison, and the slow component remains outside its
matched-query evidence.

The same moderate report now includes captured JS and native costs. It
recommends **deferring production integration**: plate/gear observations are
promising, but the half-chord curved cases cost more and no matched end-to-end
benefit has been measured. If later evidence justifies implementation, it
requires **one pinned native producer/provider across every reader**, as set out
in the [integration design](RWGLTF-ADAPTER-DESIGN-20260910.md). Viewer-only native
meshing would leave exports, snapshots and static docs inconsistent. Static
docs require precomputed entries or an explicit separate backend decision;
native-key misses must never silently return JS triangles. Mirrored/located
native carriers, process cancellation, deletion/corruption races and force
equivalence remain integration requirements, not claims of this prototype.
