# P0 retained-document contract

Status: frozen provisionally before the document core is implemented. Numeric
ceilings may be replaced only by a reviewed P0 rerun with the same fixture and
boundary; candidate measurements do not silently move a gate.

## Frozen revisions and boundaries

- Candidate checkpoint: `5c4a212cae32e834fa4d805ae778ab5ee6cd71a2`.
  Its production code is identical to `18cc312ce`; the intervening changes are
  the replacement plan, viewer-quality notes, and export documentation.
- Historic optimized implementation: `18cc312ce`.
- Main comparison: `3e4dfdeef2cbd5804c369592b59620132188a150`.
- Source-command time begins immediately before spawning `python MODEL --json`
  and ends at actual process exit. A successful sample requires the declared
  STEP output and its independent readback oracle.
- Cold means a new private daemon, worker, store, and model copy. It does not
  claim a cold filesystem cache. Each warm scenario has its own private daemon,
  worker, store, and model copy; its unmeasured prime is excluded.
- `unchanged`, `local_geometry`, and `placement` retain those exact meanings.
  Local geometry changes only `HOLE_RADIUS`. Placement changes only the root Z
  for the plate or occurrence `plate_01` for the assembly. Each changed value is
  previously unseen in that session.

The plate is an 80 x 50 x 6 mm box with its minimum at Z=0, four 4 mm-radius
vertical-edge fillets, and four through-holes centered at X=+/-28, Y=+/-13.
The assembly prototype is 32 x 22 x 4 mm with 2.5 mm vertical-edge fillets and
four through-holes centered at X=+/-10, Y=+/-6. Its 24 labeled occurrences use
a 6 x 4 grid with 42 mm X and 32 mm Y pitch. The initial hole radius is 3 mm.
The exact source SHA-256 values are frozen in `BASELINES.md`.

Every command records process-exit time and counts JSON completion events.
Future runtimes should additionally append JSON Lines to the path in
`CADGEN_DOCUMENT_BENCH_TRACE`. One object per accepted revision has this shape:

```json
{
  "schema": 1,
  "revision": "engine revision identity",
  "stagesMs": {
    "sourceCapture": 0,
    "graphReconciliation": 0,
    "dirtyComputation": 0,
    "nativeReadiness": 0,
    "topologyReadiness": 0,
    "meshDerivation": 0,
    "exchangeExport": 0,
    "savedFileVerification": 0
  },
  "counters": {
    "geometryRecomputations": 0,
    "nativeEvaluations": 0,
    "brepSerializations": 0,
    "brepDeserializations": 0,
    "prototypeMeshes": 0,
    "occurrencePlacementUpdates": 0
  }
}
```

The harness preserves unknown fields, rejects malformed JSON, and reports an
absent hook as `unavailable`; absence is expected for both frozen legacy
revisions. A candidate cannot claim the P1 zero-recompute/zero-remesh gates
without these counters or equivalent reviewed instrumentation. Counter time is
inside the source-command boundary.

The internal candidate mode reads the current transaction `EvaluationStats`
directly. Its `computed` field counts all document-core operators, including
rigid transforms and opaque captures, rather than only surface and boolean
modeling. Its derivation counters cover only document-core derivations; they do
not cover downstream exporter, viewer, or snapshot meshing. A zero aggregate
therefore cannot establish zero modeling or end-to-end zero remesh. Those gates
need classified operator events plus downstream mesh instrumentation.

The prototype's current `EvaluationStats.computed` is a literal count of all
document-core operator evaluations, including rigid transforms and opaque
captures; it is not a count of only new surfaces or boolean modeling.
`derived_computed` and `derived_reused` cover only derivations owned by the
document core. They do not observe downstream STEP/export or Viewer meshing.
No zero-modeling or end-to-end zero-remesh claim may be inferred from either
aggregate until classified operator and downstream mesh instrumentation exists.

## Semantics retained and replaced

The new engine retains parameterless `@step` model functions, child-call
composition, returned usable shapes, relative-to-source declared `out=`, format
decorator stacking, labels/materials/placements, and success only after every
declared output plus required STEP verification completes. A saved STEP remains
usable after source and disposable engine state are unavailable. Imported STEP
bytes are authoritative and never cause source execution.

Ordinary Python runs once for every source command, including unchanged calls.
Its loops, branches, I/O, callbacks, native query results and side effects keep
normal Python semantics. The legacy whole-call freshness gate may skip the body;
the harness records this as a known replaced law, not an oracle to preserve.
The public `@memo` decorator, operation-memo environment controls, store schema,
directory-per-index layout, serialization-derived operation identity, global
geometric equality patches, and author purity contract are also replaced.

Native mutation and aliasing remain normal within the current execution. A
managed retained input is isolated before a native escape can mutate it, while
aliases inside that private escape remain aliases. A later revision must equal
a fresh direct-kernel computation. Unsupported native regions execute privately
or fail explicitly; they cannot mutate retained ancestors invisibly.

Generated/modified/deleted topology history and occurrence provenance are part
of an operator result. A split, merge, reorder, mirror, or pair of coincident
faces must either reconcile unambiguously or invalidate the ambiguous reference.
No selection may silently attach to a different occurrence or subelement.

## Geometry and file oracles

Each sample is independently imported from the exact saved STEP bytes using a
fresh readback store. The oracle requires a valid shape, the expected 1 or 24
labeled occurrences, one solid per occurrence, finite volume/area/bounds, and a
stable face/edge/vertex count within a scenario. Unchanged samples must preserve
their STEP SHA-256 and full geometry description. A larger hole radius must
reduce volume while preserving bounds and labels. A placement edit must preserve
per-occurrence geometry measures and translate only the named target's Z bounds.

Cross-revision parity compares the normalized geometry descriptions with numeric
tolerances. Byte-identical STEP is required within one runtime/scenario when
the exact inputs repeat; it is recorded but is not the cross-kernel geometry
oracle. Cache-loss validation removes only the private disposable store, then
reimports the saved STEP without the source directory.

The optional FreeCAD retained-document reference is publishable only when its
per-sample labels, validity, volumes, areas, bounds, and solid/face/edge/vertex
counts match a complete cadgen saved-file report. Its geometry edit rebuilds
the complete plate factory and is not evidence of feature-level dirty-hole
recomputation. FreeCAD stage times remain separate from source-command times.

## Completion and format matrix

| Door/input | Durable authority | Successful completion | Mutation/independence guarantee |
| --- | --- | --- | --- |
| `python model.py` with `@step(out=...)` | Python plus declared inputs | Geometry publication, declared STEP write, translation/readback verification, sidecar binding, then process exit | A late older save cannot overwrite a newer accepted revision; returned shape remains usable |
| `@stl`, `@threemf`, `@glb` stacked with `@step` | Same source revision | Every independently declared variant completes before source-command success | Decorator order is neutral; one failed output fails the command rather than silently publishing partial success |
| Mesh-only decorated source | Python plus declared inputs | Declared mesh outputs complete; no implicit STEP or sidecar | Same child composition and unchanged-call contract as `@step` |
| Saved STEP import/view/inspect | Exact file bytes | Requested import/topology/display stage completes against the pinned bytes | Never executes nearby source; external replacement creates a distinct revision |
| `cadgen {stl,3mf,glb} build saved.step` | Exact STEP bytes and explicit/declarative export request | Requested mesh artifact is complete/current; never rewrites STEP | Imported STEP declares no variants; an explicit output is required |
| STEP snapshot/viewer | Exact saved bytes, or an explicitly pinned resident revision for editing preview | First geometry and complete requested detail are separate milestones | Saved-file CLI observes file bytes; resident preview cannot impersonate them |
| STL / 3MF / GLB | Exact mesh file bytes | Parse plus complete requested display/snapshot | No CAD topology is inferred; static/animated/material capabilities remain format-specific |
| DXF / URDF / SRDF / SDF shared consumers | Exact source/file contract of that door | Existing validate/snapshot obligations remain | Document-engine cutover cannot break their shared runtime paths |

## Provisional fixture memory and lifecycle gates

These are ceilings, not observations. They are intentionally conservative for
the small fixtures and freeze before candidate timing. RSS and owned-resource
accounting are recorded separately; missing GPU counters cannot be treated as
zero. `settled` is sampled after a 2-second idle plateau.

| Owner | Plate peak / settled | Assembly24 peak / settled |
| --- | ---: | ---: |
| Owning kernel service tree RSS | 896 / 800 MiB | 1,024 / 896 MiB |
| Browser renderer RSS | 256 / 224 MiB | 320 / 256 MiB |
| Browser GPU-process RSS | 192 / 160 MiB | 224 / 192 MiB |
| Decoded CPU arrays owned by scene | 24 / 16 MiB | 48 / 24 MiB |
| Snapshot worker tree RSS while retained | 384 / 320 MiB | 448 / 384 MiB |

At most two complete revision payloads may overlap during replacement. Queues
are capped at 32 accepted revisions or 64 MiB of referenced payload, whichever
comes first. Superseded/cancelled work must release reservations, native pins,
temporary files, workers and decoded arrays within 5 seconds. After 20 edit and
dispose cycles, two successive settled samples 2 seconds apart must stay within
16 MiB or 5% (whichever is larger) for kernel RSS, renderer RSS and decoded
arrays.

A snapshot service may keep its bounded worker process alive between requests.
After each snapshot finishes, request-owned native pins, decoded arrays,
temporary files and reservations must release within the 5-second deadline;
the retained worker must then satisfy the active settled RSS ceiling above.
Zero live snapshot-worker processes is required only within 5 seconds after an
explicit snapshot-service or browser shutdown. The zero-after-shutdown gate and
the active settled-worker gate are recorded separately.

A one-sample harness preflight observed a 745 MiB plate service-tree plateau;
that functional observation set the plate ceiling before any document-engine
candidate existed. The assembly ceiling includes additional bounded headroom,
not an observed assembly result. Historic browser studies support keeping the
browser ceilings bounded, but they do not constitute measurements of this new
harness. Fresh observed values remain in result JSON and are never backfilled
into this contract.
