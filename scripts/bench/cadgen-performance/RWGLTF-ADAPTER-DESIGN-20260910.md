# Native mesh adapter — deferred integration design

Production design only; the first component adapter now has a private prototype.
The [opportunity study](RWGLTF-OPPORTUNITY-20260910.md) proves C++ packing and
named-face recovery. Its tighter native case improves measured accuracy at
approximately the earlier JS latency; it does not establish a complete faster
backend. No production path, cache key or dependency changed.

The subsequent [moderate quality/cost comparison](RWGLTF-MODERATE-QUALITY-20260910.md)
recommends deferring production integration and prioritizing publication/build
overhead. The requirements below preserve the architecture if later workload
evidence justifies it; they are not an active implementation plan.

## First increment: one private component to existing render/selector data

1. Verify a complete canonical component's BREP/SURF addresses; reconstruct one
   private BREP and mesh it once. Build canonical face/edge maps with the same
   `TopExp.MapShapes` convention as SURF. Keep the existing named-face GLB
   carrier; a missing expected face is a visible failure or an explicitly
   justified zero-area topology case, never a silently discarded ID.
2. Before releasing that private shape, capture sparse boundary metadata:
   face ordinal, edge ordinal, and each boundary polygon's local triangulation
   node indices. Traverse face edges with their orientation and handle both
   representations of a closed seam. [OCCT's implementation](https://raw.githubusercontent.com/Open-Cascade-SAS/OCCT/V7_9_3/src/BRep/BRep_Tool.cxx)
   selects the second closed-triangulation polygon for a reversed edge. Verify
   this against forward/reversed faces and both seam occurrences in fixtures.
   This work scales with boundary nodes, not every surface vertex/triangle.
3. Decode named-face arrays in shared JS; apply one explicit coordinate/unit
   conversion and produce the existing component shape: positions, normals,
   indices, face ordinals/ranges, edge polylines and opposite-triangle-side
   edge ordinals. Build edge polylines from those exact indexed positions.
   Verify every adjacent face represents the same canonical edge positions
   and segments; do not hide disagreements by substituting unrelated SURF
   curve samples. Named GLB leaves are a transport mapping, not hundreds of
   new display draw calls.
4. Reuse `buildMeshDataFromSurf` and `buildSelectorBundleFromSurf` with that same
   completed component. SURF supplies exact topology/metrics, edge classes and
   intrinsic appearance; native arrays supply concrete geometry. Render-only
   and later selector requests must use the identical concrete payload/key.

This increment stays in private helpers first. It needs no native renderer
endpoint or public authoring API. Its output may use the existing TESS v3 codec
under private filenames; it must not write the current JS mesh index.

## Acceptance and unresolved correctness

The completed private prototype used a small box/hole, a cylindrical seam,
sphere/cone poles, a trimmed NURBS patch and one 822-face component. Further
work, if authorized, uses only small/moderate fixtures. Check every face/edge reference,
both seam sides, boundary coincidence at transported Float32 precision,
mirrored/located faces, face colors, and actual face/edge hit IDs. Compare cold
conversion with encoded/decoded reuse and with render-first/selector-later
requests. Verify independent ownership and input byte immutability.

Classify the remaining native flags before correcting them. A normal-dot flag
alone does not establish that swapping triangle winding is correct at a pole.
Any proven collapse removal or normal repair must retain/rebuild face ranges,
side ordinals and edge references consistently. The tighter native case still
has 47 collapse flags and seven normal flags. Audit bounded facet/vertex
deviation against exact surfaces and trim boundaries, not volume alone; current
JS's nine omitted tiny faces and thousands of flags remain a separate limitation.

Measure the entire candidate boundary: private reconstruction, meshing, sparse
edge extraction, C++ writing, JS decode/normalization, codec, mesh construction,
selector construction and peak process memory. The 83/232 ms writer times alone
do not include those costs. Use one component at a time; do not start another
tolerance sweep or whole-hand benchmark to establish this contract.

## Shipping would require a separate integration decision

Current misses in `renderAssetClient`, `surfWorker`, `common/source`, and Node
exports execute the shared JS tessellator; the viewer's `tess_cache.py` only
serves opaque bytes. An OCP implementation needs a lazy native build-pool job,
never kernel work in the viewer HTTP process. Every rendering/export door needs
the same backend-resolution rule, including cold source-free saved documents.
Admit/cancel native jobs with bounded concurrency and account for their private
BREP/mesh/GLB memory alongside staged browser payloads and actual scene adoption.

A native result needs an explicit backend/algorithm identity covering OCCT
version, meshing parameters, edge extraction, coordinate/Float32 normalization
and any quality corrections. The renderer, shared mesh index, late selector
loads and worker messages must agree on the full concrete identity. A failed
native request cannot publish JS triangles under the native key or mix native
display arrays with selectors from a different tessellation. Cache misses,
corruption, deletion and forced rebuild must preserve the ordinary store laws.
Whether to adopt a single native default or retain separate explicit backends
belongs to that later decision, after the private adapter passes these checks.

### Concrete integration boundary

Keep `cadgen-js` independent of Python. Its adapter should be a pure decoder of
verified GLB/boundary bytes into the existing component/TESS structure; no native
imports, HTTP knowledge, source evaluation, per-face display objects, or viewer
state. Native triangulation and sparse boundary extraction belong to a lazy
cadgen build-pool job over pinned BREP and SURF bytes. A private shape owns the
triangulation for that job only. Never mesh a materialized author's shape or
write that triangulation back into the canonical BREP.

The internal producer can expose one operation: resolve or derive a complete
component tessellation for pinned geometry, effective tolerances and an explicit
algorithm identity. It must verify the BREP/SURF bytes it consumes; after the JS
adapter validates counts, face/edge relations and payload shape, publish one
content-addressed TESS object and atomically update its derived mesh index.
Bind the concrete key to both immutable input addresses and the native/OCCT/
adapter version, not a mutable model name or request-local occurrence. A cache
hit and forced reconstruction must yield the same arrays. Native failure is an
ordinary visible derivation failure, never JS output under that native identity.

Viewer misses, Node mesh exports and snapshot misses must call that same
producer/provider before decoding. The HTTP server remains kernel-free and
only schedules/polls the admitted job or serves immutable bytes. Render-only
hits use the complete TESS header; a later selector request reads canonical
SURF metadata but uses the exact cached component arrays. Keep component,
algorithm, codec and tolerance identities in asynchronous request/result checks,
including cancellation, replacement and an active selector's LOD publication.
Transient GLB/boundary carriers need not become another persistent cache family.

The static docs site is a separate practical constraint: it has no Python
backend and presently publishes only SURF/tree assets. A native-default scheme
must export verified TESS entries for every supported docs LOD/tolerance during
asset preparation, with a manifest that pins their concrete identities. The
static reader can only decode those entries. Silently generating JS triangles
on a missing native entry would break the cache law. Either the build rejects
an incomplete asset closure, or an explicitly separate JS backend remains a
separate product decision and identity. A browser-only native cache miss cannot
be solved by this C++ adapter alone.

Admission must cover the actual process arrangement. The private prototype
ends its native child before starting the JS decoder; its per-process peaks
are not the peak of a resident native worker plus a simultaneous Node child.
A production build-pool job needs a combined native/scratch/GLB/Node budget,
bounded concurrency, and cancellation that does not release ownership while a
child can still allocate or publish. No persistent pool is needed to prove the
first integration; any later worker-reuse optimization needs its own measured
memory and cleanup evidence. Browser staging and scene-adoption reservations
remain necessary after the native job finishes.
