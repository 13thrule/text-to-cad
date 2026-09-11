# Separate canonical geometry from derived surfaces

The private feasibility proof and matched resident measurement passed. See the
[core results and qualifications](DEFERRED-SURF-CORE-20260911.md). Production
integration now passes the frozen package, installed-wheel and moderate-browser
checks with geometry-tree schema 1, model/document schema 4, separate surface
indexes and TESS v4. Final public timing comparisons are recorded separately in
the [integration report](DEFERRED-SURF-INTEGRATION-20260911.md).
The release version remains unchanged.
The proposal and staged acceptance sequence below record the design decision;
their private-only implementation restriction has been satisfied by that proof.

## Decision and benefit boundary

The accepted implementation separates geometry publication from display work.
It is a coordinated store contract change, not making today's `surf` field
optional. A complete native geometry result must contain everything needed
for an independent private reconstruction. Display and selector readiness are
separate derived facts and cannot change that result's identity.

The resident nine-part cleanup study measured 1,079.46 ms complete compile;
baseline attribution found 255.37 ms STEP snapshot/parse and 758.01 ms SURF
extraction. These are medians of nested instrumented stages, not quantities
that can be subtracted to predict an exact new total. Approximately 0.75 s of
work is a credible target for removal from a cold geometry reader's critical
path. Parsing alone already exceeds 250 ms in this fixture. Worker scheduling,
canonical BREP writes/validation, exact bounds and the caller's private native
construction remain. The bounded resident study now measures 342 ms native cold
read/publication, while total input surface readiness remains about 1.18 s.

This can improve public `read_step`, STEP re-emission and native parent edits
that do not need selectors. It does not remove extraction from first display,
inspection, selector resolution or mesh export. A saved document never borrows
the authored source tree: new STEP bytes still undergo canonical readback.

## Proposed hard-cut contract

1. A schema-versioned geometry tree owns hierarchy, occurrences, names,
   transforms, uniform colors/PBR, exact bounds, links and component inputs.
   Each component names an immutable BREP object and an immutable normalized
   face-ordinal RGBA recipe. The recipe can initially be inline in the tree's
   component entry; the tree already gives it content addressing. A separate
   appearance object or native ownership layer is unnecessary.
2. Native-readable geometry completeness requires the exact tree/link closure,
   BREP bytes and intrinsic recipe. Every component advertised as native-readable
   must privately decode to a non-null shape; transforms must validate before publication. Consumers
   construct private shapes and private metadata. SURF absence does not make
   a native-readable geometry pin stale. Loss/corruption of required geometry
   still does. A new-schema eager-only exception is described below; it never
   advertises native readability or byte-only surface regeneration.
3. A new artifact-derived `index/surface/<full derivation key>` atomically
   names a SURF object and its full verified inputs. The key covers the full
   component input, extraction algorithm, SURF format and known runtime
   producer identity (OCP binding/distribution and any build123d dependency).
   This index contains no source, path, model record or output-record key.
   Publish the verified SURF object before its index entry. Never add its hash
   back into the immutable geometry tree after derivation.
4. One internal pool operation accepts exact geometry-tree/component pins,
   resolves only captured artifact-side inputs, checks their hashes, privately
   decodes BREP, applies the owned recipe, and runs the existing extractor.
   No live authored shape crosses this boundary. No kernel work moves into
   the HTTP server. The existing worker budget, job errors and yielding rules
   apply; group small component requests rather than spawn a process per CID.
   Coalescing is an optimization. Racing deterministic writers must be safe
   without locks, and cancellation must not publish an incomplete index.
5. Every concrete tessellation and selector request binds the same resolved
   full SURF object digest, numeric quality and mesher algorithm. The current
   persistent `cid-t<algorithm>-l...-a...` key is insufficient if SURF becomes
   independently versioned. Change the shared JS/Python key contract to use
   the full surface identity. Display and selector payloads must never mix
   two producers or two concrete quality settings.

Keeping component-input-v2/extraction-19 would work only if that old field is
frozen as a geometry compatibility domain and no longer bumped for SURF
changes. A cleaner hard cut is a geometry-input-v3 domain over pinned BREP
codec/bytes and normalized intrinsic recipe, with extraction version solely
in the surface derivation key. Retain full input hashes for validation even
where a short CID is used in occurrence tables. New geometry-tree,
record/document payload versions reject the previous contract; no old-schema
fallback. Object addresses and document keys remain raw byte hashes. The
sidecar schema need not change merely for this separation if occurrence/face
IDs and document binding remain identical. No release-version change.

## Runtime producer and warm display

Neither the extraction version nor the actual native producer belongs in a
canonical geometry tree. With identical geometry inputs, changing the display
producer must leave the tree hash unchanged. A request instead freezes its
producer and derives a full surface input key, `D`, from that producer and the
geometry input. The exact SURF output has a separate content hash, `O`.

A fresh viewer must not start OpenCascade merely to select an already cached
mesh. The existing document index can carry an optional, worker-attested
`surfaceProducer` hint alongside its tree. The existing ephemeral preview event
carries the same information. These are derived selection facts: they change
neither the document key nor the tree, require no new persistent view/session
store, and do not make geometry incomplete when absent. Read tree and hint
from one index snapshot. A same-tree rewrite preserves a valid hint unless an
attested producer is explicitly selected; a changed tree drops both the old
hint and its external-output mesh ledger.

That hint may select older but still valid assets. A cached TESS supplies its
own `D` and `O`, so it renders even after the surface index and SURF object are
deleted. A later selector request must recover exactly that `O`. If the old
producer is unavailable, obtain the current producer and stage a new view with
new identities; never attach its selectors to the old displayed mesh. A bare
tree request with no producer hint pays producer initialization explicitly.

The shared TESS lookup key, `L`, binds `D`, tessellator version, payload version,
and both exact numeric tolerances. Encode each positive finite tolerance as
its 16 hexadecimal IEEE-754 binary64 digits; the existing six-digit decimal
format can merge distinct values. The displayed mesh/selector identity adds
the full `O` to `L`. TESS version 4 carries and validates those inputs. Object
hashes in a TESS header are provenance, not a requirement that SURF still exist
or a transitive GC root.

Probe encoded/decoded sizes before downloading whole cached meshes. Fetching
an assembly's complete TESS batch before memory admission would retain a
browser-crash path. Full payload/hash validation still precedes adoption;
metadata estimates cannot override observed body sizes. The interface and
shared codec remain private work, with browser integration gated on the core
feasibility result.

## Identity and semantic dependencies

`_content_hash_and_bytes` already establishes component identity before SURF
exists (`_internal/component_package.py:120`). `_document_walk` already owns
the normalized STEP face colors and BREP bytes (`store/build.py:174`). It also
produces placements, grouping and native exact bounds without SURF; tree
stats are only occurrence/link counts (`store/build.py:505`). There is no need
to front-load face metrics or edge classification for geometry publication.

`surface_extract.py:735` uses `TopExp.MapShapes` face/edge ordinals, solid/shell
membership, exact metrics, trimming loops and seam adjacency. Deferred
extraction must preserve all of those by consuming the same validated BREP
and recipe. It must not reconstruct a different compound or infer IDs from
triangles. Raw STEP recipes contain only actual mapped faces. For authored
inputs, positive but nonexistent ordinals are currently accepted by input
normalization but absent from extracted SURF; the cutover must specify and
test their effective recipe rather than silently changing cold/hit metadata.

Distinct face-color inputs can share identical BREP bytes. Preserve the current
private topology separation between those variants; otherwise XCAF style
assignment can overwrite a sibling's colors. Preserve occurrence PBR ownership
and sidecar overlays independently from canonical geometry. Resolved kinematics
still require the selected saved-document digest and the normal node/face
correspondence checks.

## Unreadable BREP is a real prerequisite

The current worker marks deserialization failure as `PAYLOAD_UNREADABLE`
(`component_package.py:403`). `_publish_tree` then extracts from the original
native shape and writes BREP again (`store/build.py:597`). This preserves a
display SURF even when the serialized geometry cannot cross the process
boundary. It is not a recovery strategy available to a later byte-only job.
Current saved scene reconstruction itself misses on those unreadable bytes
(`step_scene_package.py:45,125`); publishing another such geometry tree would
not meet the proposed native-readiness promise.

The private spike must record this case, not silently use the original shape
inside a supposedly byte-only lazy job. There are two sound options to prove:

- A deterministic readable alternate codec selected only when pinned binary-v4
  round-trip fails. BRepTools ASCII is a candidate, not an established solution:
  first prove exact geometry, flags, topology order/face colors, independent
  ownership and deterministic reserialization on an actual reproducer. Record
  the codec in the component definition; every native reader and worker uses
  the same decoder. Do not normalize geometry, repair topology or omit failed
  entities merely to make decoding succeed.
- An explicit **eager-only component kind within the new schema**. At initial
  publication, the private parsed/authored shape supplies SURF through the
  existing eager extractor; that exact SURF is a required immutable object of
  this exceptional component. The BREP and intrinsic recipe remain recorded,
  but the component does not promise native reconstruction. This preserves the
  existing public-native failure and successful-render distinction. Its SURF
  cannot be dropped from required closure or regenerated by a BREP-only job.
  When a saved document's eager-only closure is damaged, recompile the actual
  selected STEP bytes and verify the document digest and regenerated component
  input before atomic repair. The repair request carries the path/digest;
  no source/path metadata enters the component. For an authored source pin,
  missing required eager SURF retains the existing incomplete-pin behavior;
  never substitute saved geometry or a latest child result to repair it.

The eager-only form is not a legacy schema shim: both component kinds belong
to one strict new schema and have explicit completeness/regeneration rules.
Ordinary readable components still gain deferred surfaces in the same assembly.
Their identity is independent of disposable SURF readiness; exceptional eager
components necessarily pin the display bytes that make them renderable. A
store reset does not authorize rejecting formerly renderable documents. Prefer
this selective fast path if a readable alternate codec lacks evidence. No
permanently hidden native prototype is proposed.

Classify an eager-only component only from a freshly serialized known native
input, with the same prevalidation on hits and misses. Corrupt/missing bytes
read from an index are a cache miss requiring ordinary verified recovery, not
permission to relabel that component eager-only. Exception messages do not
enter identities. Its native reader still follows the ordinary decode/failure
path; the kind promises neither a fabricated native shape nor forced failure
if a supported decoder can read the exact bytes.

The targeted source search found the fallback in component extraction and
validity code, but no checked-in regression naming `PAYLOAD_UNREADABLE` or the
point-representation asymmetry. Existing deliberately invalid-cache tests are
not native serializer reproductions. Finding or constructing a small real
reproducer is a prerequisite to codec expansion; do not use a large assembly
or a mocked decoder failure as proof of codec geometry parity.

### Actual codec findings from the bounded spike

Tiny native reproductions on OCP 7.9.3.1 / cadquery-ocp 7.9.3.1.1 establish two
distinct point-representation faults. BinTools v4 can throw or silently alter
a PointOnCurve parameter. Both binary v4 and v3 can swap a PointOnSurface's
distinct U/V values. Pinned binary v3 preserves the first cases, and pinned
BRepTools ASCII v3 preserves the second, including complete native bytes.
The private closed codec set therefore contains all three explicit formats;
the declared format must match the payload header before decoding.

The current eager worker decodes the input for extraction but stores the
original BREP payload verbatim. Ordinary consumers decode those same bytes.
Five of the nine planetary components undergo small unit-direction
normalizations during reading; this is existing behavior. An unconditional
original-byte fixed-point requirement would incorrectly exclude those five.
All nine have empty vertex point-representation lists, so the guarded v4 path
preserves their exact existing stored bytes, native result and SURF output.

The frozen strict three-codec helper requires full native-byte fidelity on
point-bearing shapes, with v3 then ASCII recovery. Two fresh processes pass
19 native/control/actual-worker comparisons each and nine negative header
checks. It still conservatively rejects some potentially healthy point-bearing
shapes when unrelated native normalization changes their serialized bytes.
That is an unresolved coverage limit, not proof of geometric corruption.
A separate exact vertex-representation experiment passed and supplied the
recommended narrow v4 guard. Its v3 and ASCII recovery retain the strict full
native-byte checks. The combined helper passes 20 comparisons; no approximate
comparison or silent native-unavailable regression was accepted for speed.

## Reader and ownership map

| Boundary | Required change / responsibility |
|---|---|
| `store/build.py`, `trees.py`, `records.py`, `paths.py` | Publish geometry inputs and tree independently of extraction; one strict new schema; immutable complete closure and exact pins. Source/result and saved/readback remain separate. |
| `component_package.py`, new store surface producer, `daemon/executors.py` plus tool dispatch | Share canonical BREP/recipe derivation; add artifact-only surface work in the existing pool, explicit store root and producer key; no author utility. |
| `store/materialize.py:448,577`, `_internal/step_scene_package.py:125` | Replace SURF color reads with verified recipes; retain current per-call native decode, variant topology ownership, metadata and exact document snapshot binding. Public `read_step` still returns ordinary build123d geometry. |
| `_ready_children.py`, `_descriptor_bounds.py`, `store/lazy.py`, gate/source-result publication | Verify and budget BREP/recipe/tree closure instead of making native reuse depend on SURF. Keep native prevalidation, callback ordering, exact child pins and every called child's declared-output wait. |
| `store/view.py`, `catalog.py`, `step_topology_artifact.py`, `step_export_target.py`, `_internal/step_reemit.py`, `snapshot_cli.py` | Geometry-only consumers never call a render view accidentally. Render/selector/export view preparation first ensures required surfaces, then creates one owned descriptor with exact surface hashes. Cached temporary views must not certify an incomplete closure. Plain STEP reemit skips SURF; selector-based kinematics legitimately demands it. |
| Viewer `artifact_status.py`, `compiles.py`, `store_paths.py`; shared render client/provider | Distinguish geometry compiled from surfaces pending/failed and pixels ready. Missing surfaces request artifact derivation, not STEP reparse/source rebuild. First increment may ensure a complete view before loading; progressive native surface production is a separate optimization. |
| Shared TESS cache, workers, selectors, Node exporters; static docs/export preparation | One full surface-derived identity everywhere. Static/offline packages must finish and copy all required SURF objects before delivery; no server or Python may be assumed at static runtime. |
| `store/gc.py`, repair helpers, all publish/lookup paths | Mark required geometry closure from both model and document roots, recipe objects if later split out, eager-only SURF dependencies, and valid derived object indexes. Document mesh-ledger hashes describe external outputs, not stored mesh objects; do not invent object roots from them. A lazy surface index miss/deletion only loses derived data. Verify consumed bytes; atomic repair writes only known hash-matching data; no delete-before-repair race. |

For missing BREP/tree objects, a document reader recompiles its selected saved
bytes; a pinned source consumer retains its existing missing-pin failure/rebuild
contract. Never replace a missing pin with a latest record. A geometry-only read
with a deleted surface index must still succeed without extraction. A later
render re-derives the surface or fails loudly without a partial output. SURF
failure is then a surface-job failure, not evidence that valid native geometry
was never compiled; that state change must be explicit in the new contract.

## Bounded private spike and delegation

The proposed new module is `cadgen/store/surfaces.py`: the typed artifact-input
key, index validation and derivation operation. Keep geometry serialization and
recipe normalization in `component_package.py` initially, with one implementation
shared by publication and the worker. Add an internal `submit_surfaces` entry
beside `submit_compile` and register its worker dispatch; do not create a new
public model-author function. Shared mesh-key changes belong in
`lib/surf/tessellationCache.js` and its Python/provider mirrors.

The pool integration needs a typed artifact subject, not a fake `.step` or `.py`
path. Currently `daemon/server.py:291` infers a subject from argv suffixes,
`Job` resolves a model path, and `jobs.py:75` treats every non-Python subject as
an output path. Surface work must have no declared filesystem output and must
not become an editing producer. Register an internal tool in `server.py` /
`worker.py`, keep its model-worker binding empty (borrow a spare), and coalesce
on `(store root, surface operation, sorted full input/producer keys)` separately
from the human-facing document/request context. A request from a worker must
release its execution slot while awaiting that dependent job, as a document
compile already does. Do not hold a slot and wait for a child needing the same
single available slot. The synchronous in-worker producer may reuse its current
slot instead; there must be only one accounted execution path, not recursive
submission plus an unaccounted local fallback. Different overlapping batches
may duplicate deterministic work initially; a separate per-component queue is
not required for feasibility.

Do not start with browser integration. Use a fresh private implementation copy,
small colored/nested/repeated/curved fixtures and the existing nine-part import.
First implement only the strict geometry input/tree format, BREP validation,
recipe-based saved reconstruction, and a callable artifact-only surface producer.
Invoke the existing extractor unchanged on the private decoded inputs; no new
mesher. Keep public main/runtime files unchanged.

Required proof: (1) complete cold/current/force geometry and STEP parity;
(2) byte-identical eager/deferred SURF and same face/edge ordinals/colors;
(3) all surface data/indexes absent while native read/reemit/materialization
succeed without extraction; (4) corrupt/missing required geometry, invalid BREP
and transform cannot gain early publication, and deletion/repair races do not
hide mismatches; (5) distinct same-BREP color variants and callback mutation own
their geometry/metadata; (6) surface producer failure, duplicate writers and
one-slot nested demand cannot deadlock or publish partial success.

Only after that proof, coordinate one bounded interleaved nine-part measurement:
resident cold compile/public read, native local edit/save, and first surface
readiness. Report extraction moved to the latter separately, plus native
validation/recipe overhead. Reject the spike if serialization coverage cannot
be preserved or the geometry-reader gain is erased. This is a larger measured
opportunity than another 10–20 ms post-body tweak, but not permission for a
broad rewrite before the feasibility result.

After a passing feasibility result: one owner controls store schema/identity,
producer/pool and GC; a second owns native consumers/materialization/appearance
and their cache-loss tests; a third owns shared render identity/viewer readiness
and static/export adapters after the interface freezes. Root retains cross-door,
installed-wheel and source-free integration acceptance. Avoid concurrent edits
to `store/build.py` or separate per-reader producer contracts.
