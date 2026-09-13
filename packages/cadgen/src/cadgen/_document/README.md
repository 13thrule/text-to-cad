# Retained document engine foundations

This internal module implements resident native ownership, revision behavior,
captured source execution and direct STEP products. It includes a transactional
catalog foundation; native checkpoint/service recovery is still being integrated.
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

Multi-input evaluations also encode the canonical allocation-provenance DAG:
input roots and their dependencies receive local indices in traversal order.
The hashed payload contains no execution UUIDs. Repeated references and shared
ancestry distinguish `(a, a)` from independent equal `(a, b)`, and a root with
its face from that root with another allocation's equal face. Replaying the
same relationships reuses the result. This conservative P1 encoding traverses
the relevant dependency graph; provenance reuse is a future profiling target.

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
digest, stages privately and verifies final bytes. Per-face appearance, full
materials, kinematics and all mesh declarations still need producer coverage;
unsupported declarations do not route to the previous generation engine.

The new catalog uses SQLite/WAL and immutable opaque payloads, with head
transactions, exact reader leases, receipt records and bounded reclamation.
Version changes reset only owned disposable data. Crash tests cover both
reclamation phases and concurrent readers. The catalog imports no kernel and
contains no previous-store reader. It is a storage primitive, not proof of
complete process recovery or persisted native alias correctness.

Permanent topology naming, complete builder effects, format fidelity,
cross-process service integration, actual memory accounting and end-to-end
performance acceptance remain open. Stock input-free constructors can reuse
after unrelated native escapes only under an explicit closed-provider contract;
input-dependent and user-overridden operations remain conservative.

The final cutover resets old derived storage and removes the old execution
backend. There are no schema readers, cache converters or compatibility aliases
in this module. The existing pipeline bridge is temporary development
integration, not a supported alternate backend.
