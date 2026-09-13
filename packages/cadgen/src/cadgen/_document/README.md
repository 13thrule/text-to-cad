# Retained document engine foundations

This internal module implements resident native ownership, revision behavior,
captured source execution and direct STEP products. It includes a transactional
catalog and native checkpoint recovery. Process integration and broader producer
coverage are still being tested.
It does not claim a finished replacement for every generation or saved-file path.

`Document.begin()` creates a candidate revision. Trusted frontend adapters call
`evaluate(OperatorSpec, parameters, input_handles, compute)`. A successful
`commit()` publishes geometry; declared exports remain separate obligations.
The context manager aborts an uncommitted candidate and never commits implicitly.
`pin()` leases an exact immutable revision; collection retains active pins,
transactions, and outstanding explicit exports. An older revision cannot replace
a newer head or silently overwrite a newer claim on the same output path.

Evaluation identity includes typed normalized arguments, input evaluation IDs,
operator version, mutation contract, and runtime configuration. It does not
serialize native geometry. Logical feature identity, immutable prototype identity,
execution allocation identity, and exact stored-byte identity have different
jobs. Two independent identical constructors share one immutable prototype but
receive distinct allocations; assigning a wrapper to another variable preserves
that wrapper's allocation.

Multi-input evaluations distinguish repeated references and shared ancestry:
`(a, a)` differs from independent equal `(a, b)`, as does a root with its own
face versus another allocation's equal face. Disjoint input graphs use a compact
tag; local ancestry intervals prove the common fresh-input case without walking
history. Overlapping intervals use exact canonical DAG traversal. Neither local
ranks nor execution UUIDs enter the key, so replay and checkpoint reconstruction
produce the same identities.

The document's native pointers are private to trusted engine adapters. The
default mutation contract copies inputs. An adapter may opt into `READ_ONLY`
only for a proven non-destructive operation. Callback closures must not retain or
publish native pointers. Scalar queries reject ordinary native shape containers;
arbitrary Python object introspection is not a sandbox. Native escapes copy each
connected native alias family together through OCCT's copy algorithm. This
preserves shared topology and the pcurve/surface bindings that manual topology
substitution between independent deep copies can break. Once an escape starts, downstream operations
consume current private inputs, receive volatile evaluation identities, and
publish copied snapshots. Coincident independent roots stay distinct; selected
subshapes and their parents retain current-execution aliases. Ambiguous shared
input provenance raises an error requiring private operation replay; the core
does not guess a correspondence. Rigid placements and selections of a single
native root are copied in a common frame and retain their native partner
relationships, including a placed final result with upstream modeling history.
Private-input operators use the same allocation-aware family copying in a
temporary arena, so equal independent constructors cannot become aliases at
that boundary. New modeling topology that mixes already placed alias families
still requires private replay instead of a potentially invalid topology rewrite.

Occurrences store placement and appearance separately from prototypes.
The bound returned root is the only scene hierarchy. Evaluated intermediate
tools and discarded groups remain computation dependencies, not visible parts.
There is no second occurrence ledger or compatibility scene channel.
Derivations receive private copies, since OCCT meshing attaches triangulation.
Their immutable results are keyed by prototype and explicit derivation options.
A placement-only revision can reuse both its native prototype and its mesh.
Located queries preserve this separation: their native view does not replace
the returned occurrence's canonical prototype.

`RevisionConsumer` pins an exact committed root and resolves occurrence paths
within that owner and revision. Trusted read-only queries return immutable
values; derived callbacks operate on private native copies and reuse immutable
results per prototype, runtime and explicit options. The native 24-occurrence
test meshes once and reuses that product across placement and appearance edits.
These are resident consumer checks, not yet a browser-update benchmark.

The native meshing producer derives one immutable packed packet per prototype
and quality. OCCT surface/interior deflection is explicit and scales with each
prototype's bounds. Analytic normals, face ranges and classified edge polylines
travel with centered float32 positions and a double-precision origin. Triangles
that collapse to exactly zero area in the transported coordinates are removed;
remaining face coverage, orientation, welded closure and sampled trimmed-surface
error are tested. This is sampled quality evidence, not a global Hausdorff bound.

`build_display` publishes complete immutable hierarchy/appearance data and
content-addressed mesh packets for an exact revision. The shared JavaScript
decoder validates framing and topology ranges, verifies asset bytes and reuses
prototype geometry across scene owners. Previous products must be attested live
products, rather than caller-constructed reuse hints. A temporary browser harness
has displayed 24 colored occurrences through Inspect and both photographic
backgrounds using this path. The public viewer's resident update integration is
still a separate gate.

`TopologyHistory` carries generated, modified, deleted and unchanged relations
captured while the kernel builder still exists. Subelement ordinals are exact
within one evaluation, not persistent selection names. Unknown history is marked
incomplete. This contract preserves evidence for later naming work; it does not
solve source reconciliation or ambiguous topology references.

`ResourceAdmission` is the common synchronous reservation protocol for native,
query, escape, mesh, export, and checkpoint work. It reserves declared CPU and
memory estimates, releases on error/cancellation, and explicitly rejects excess
demand. It does not measure native allocations or promise a process RSS ceiling.
There are no hidden worker pools. Future scheduling can queue the same requests;
native work currently stays on the document's owning thread.

## Custom core and OCAF comparison

[OCAF](https://occt3d.com/dev/doc/overview/html/occt_user_guides__ocaf.html)
provides document attributes, transactions, undo, function dependencies and naming
services. Naming still needs modeling algorithms to report topology evolution.
Those facilities are useful, but do not by themselves express our source replay,
evaluation/allocation distinction, native-escape ownership, exact consumer pins,
or export-completion obligations. These remain application contracts either way.

The installed bindings were exercised with `TDocStd_Document.NewCommand`,
`CommitCommand`, `AbortCommand`, a `TDataStd_Integer` rollback, and
`TNaming_Builder.Generated`. The explicit cleanup version succeeds. A standalone
probe retaining attribute/builder wrappers through interpreter shutdown aborted
with `Standard_NullObject`; releasing wrappers and clearing undo/attributes before
document teardown avoids that observed lifetime issue. This is evidence about
this integration probe, not a general claim that OCAF is unsafe.

The selected P1 implementation is the small Python revision/lease core plus
explicit OCCT copy and history adapters. It makes the ownership contracts directly
testable without translating a second state model into OCAF labels. There is one
production prototype, not a custom/OCAF backend switch. This is a scope and
integration choice, with no unmeasured speed advantage claimed. The
[OCCT boolean ownership API](https://occt3d.com/dev/doc/refman/html/class_b_rep_algo_a_p_i___builder_algo.html)
supplies explicit non-destructive execution for the boolean adapter.

## Execution, saves and disposable storage

`DocumentService.generate` captures the entry source once before request
acceptance. `SourceSession` compiles captured first-party files with ordinary
module/package/namespace ordering and tracks each function's exact compiled
buffer through reloads. Source reads are captured as consumed; this is not an
atomic snapshot of a whole project. Ordinary authored Python always replays.
Only session-owned modules and model declarations are restored at teardown.

Called model bodies execute in the same native transaction. `publish_result`
pins their returned roots without replacing the parent's root or detaching
native aliases. Each call saves its declared outputs before returning, including
discarded calls. Completed child saves survive parent failure. The coordinator
records immutable request tickets, child invocations, geometry readiness and
actual publication order. It serializes process-local output claims; it cannot
provide filesystem compare-and-swap against arbitrary external writers.

The STEP publisher constructs a private XCAF document directly from a pinned
root. It retains one native prototype per definition, preserves placements,
names and ordinary colors, and caches immutable encoded products. Product
identity reflects serialized inputs; logical/allocation identifiers are not
file content. Actual saved bytes are independently read and remain distinct
from source-native geometry. Destination replacement checks the selected prior
digest, stages privately and verifies final bytes. Exact copier history maps
authored per-face colors onto retained prototypes; root relocation maps the same
topology without assuming enumeration order. Native STEP colors and physical
materials have independent readback checks. A translator dropping a physical
material field fails explicitly. Generic source-to-saved face correspondence
remains open: current readback verifies the palette, with actual face-placement
checks on the bounded native fixtures. PBR annotations, kinematics and all mesh
declarations still need complete publication coverage;
unsupported declarations do not route to the previous generation engine.

The new catalog uses SQLite/WAL and immutable opaque payloads, with head
transactions, exact reader leases, receipt records and bounded reclamation.
Version changes reset only owned disposable data. Crash tests cover both
reclamation phases and concurrent readers. The catalog imports no kernel and
contains no previous-store reader. It is a storage primitive, not proof of
complete process recovery by itself.

The native checkpoint codec stores one alias-preserving binary shape graph,
evaluation/allocation dependencies, exact roots, topology history and required
structural auxiliary results. Recovery verifies all reachable native subshape
sharing classes and the allocation-provenance DAG before installing a new owner.
Auxiliary values are closed, immutable and bounded in their expanded form;
builder layouts cannot live only in a disposable mesh/derivation cache. Codec
version 4 is a hard cut, with no earlier-version reader. Disjoint allocation
graphs use compact evaluation provenance. Local ancestry intervals accelerate
the proof but never enter identity; overlapping intervals use exact traversal,
so reordered checkpoint reconstruction produces the same keys.

An idle `DocumentService.checkpoint` publishes through the catalog head selected
when that owner was acquired. A conflict does not authorize overwriting the other
owner on a retry. Registry eviction respects live revision pins. On a registry
miss the service can recover geometry, but authored Python still replays and
every explicit output gets a fresh save receipt. Corrupt or missing derived
checkpoints rebuild through this engine. Historical export completion is not
evidence that a destination still contains the saved bytes.

`load_step` opens captured actual bytes in a separate saved-artifact owner keyed
by those bytes and importer/runtime policy. Equal files may share that owner;
changed bytes select a different one. A recovered saved-file root needs no
source execution or repeated STEP parse. Checkpointing remains explicit internal
maintenance; it does not delay every warm source call or acknowledge a hidden
durable authoring save.

The private `DocumentWorker` bridge owns the kernel in a spawned process and
accepts captured source or saved STEP buffers. Display returns a revision manifest
and only missing immutable binary meshes; exact inspection uses typed occurrence
references. Value framing bounds both encoded bytes and expanded metadata.
The client watches the whole transfer, including blocked writes and incomplete
frame reads. Request timeout or an interrupted stream destroys the owner without
replaying authored work; parent loss also has bounded cleanup. I/O threads carry
only framed values and bytes and are joined during teardown.

`DocumentDispatcher` owns that client on one dedicated thread. Its active and
queued requests share bounded input bytes, count and acceptance deadlines.
Parameters and environment are captured when submitted. Exact revision leases
are checked before dispatch and invalidated on release or owner loss; only a new
explicit source/open request may start another owner. Expired queued work is
removed when observed by a waiter, submitter or dispatcher, with retained inputs
remaining within the queue budget meanwhile. These boundaries pass real process
and concurrent-client tests, but are not yet the public daemon or live viewer
transport. STEP product pruning reuses immutable revision root digests and drops
them with their owning revisions.

Permanent topology naming, complete builder effects, format fidelity,
cross-process service integration, actual memory accounting and end-to-end
performance acceptance remain open. Stock input-free constructors can reuse
after unrelated native escapes only under an explicit closed-provider contract;
input-dependent and user-overridden operations remain conservative.

Closed stock provider inventories are retained in a bounded process cache.
Reuse still checks installed callable code, defaults, closures, globals and
descriptor presence without invoking source callbacks. Internal frontend
interceptors are checked after installation too. The bounded sketch adapter
retains explicit polygon construction, the first sketch ADD, pending faces and
single-face extrusion with their wrapper/native alias families. Other builder
settings execute privately. Complete builder coverage is not implied by those
operators, and warm overhead still requires the full-request benchmark.

The final cutover resets old derived storage and removes the old execution
backend. There are no schema readers, cache converters or compatibility aliases
in this module. The existing pipeline bridge is temporary development
integration, not a supported alternate backend.
