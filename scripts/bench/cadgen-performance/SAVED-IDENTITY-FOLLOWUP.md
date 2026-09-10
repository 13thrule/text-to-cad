# Saved document identity repair

**Implemented; this closes a correctness gap, not the remaining performance
plan.** The repair preserves authored finishes while separating the model's
pinned result from the tree derived from saved STEP bytes. Final integration
and packaging evidence is recorded in
[the validation report](VALIDATION-20260910.md#saved-document-identity-repair).

## Original reproduction

[The diagnostic JSON](results/material-document-identity-20260910.json) preserves
the complete original probe, commands, implementation hashes and empty-store
import. It describes the runtime before this repair, not a current failure.

The fixture is a `Solid.make_box(2, 3, 4)` named `box`, with the same RGBA color.
Changing only `cad_material` from roughness/metalness 0.1/0.2 to 0.9/0.8 produced
the same 17,263 STEP bytes, SHA-256
`1a428e89198c16d60befc052af2ab97b4f7fcdff2f231a0b3c4a18ae899cf725`,
but different saved trees:

| Input | Previous saved tree |
| --- | --- |
| A | `bc7ad3c6dee72dfb42d13e79a282f59ecd886d2efeb939d2ef7ba08413e19688` |
| B | `b1cd6579066a68dbcc55cc410b2624fac25a20fc0f63b1379098a783f3009775` |

The document index let the last writer choose both files' finish. An empty-store
import produced a third tree, without PBR and with different grouping/names.
Removing material from the tree alone would have lost finishes and left the
hierarchy mismatch unresolved.

The repair also exposed a separate component collision: different face colors
were extracted into SURF while the component input hashed only geometry. Warm
reuse could choose the wrong color and differ from a cold import.

## Implemented boundaries

- **Canonical document tree:** generated STEP read-back and cold import share
  one parsed-scene packaging path. Hierarchy, IDs, names, native colors and
  geometry derive only from the actual STEP. Filename fallback is fixed and
  cannot change a tree when a file moves. Only this tree is entered under the
  document-byte digest.
- **Authored model result:** `record.tree` retains authored hierarchy,
  intrinsic appearance and exact child pins; `record.documentTree` separately
  names the saved tree. GC follows both. The editing preview remains distinct,
  and a saved event names the document tree. Child composition never reads a
  sidecar or substitutes a later child record.
- **Durable appearance:** schema-8 `<name>.step.json` has optional `appearance`
  and `kinematics` sections bound to the exact `documentHash`. Appearance maps
  canonical leaf IDs to the five supported PBR channels. A verified structural
  correspondence maps authored leaves and exact product nodes to the written
  document. Nested single-child groups remain distinct when mapping mates.
  Missing, ambiguous or inconsistent correspondence fails explicitly.
- **Owned metadata:** lazy and eager child materialization preserve PBR and
  face-color dictionaries per occurrence, including movement, mutation,
  pre-force overrides and deletion. Component input v2 includes normalized
  face-ordinal RGBA, exact BREP and extraction schema. All legacy component
  inputs miss, including uncolored ones. Identical BREP bytes still share one
  immutable object. Different colored components get private topology within
  each materialization so XCAF cannot overwrite another variant's styles.
- **Saved readers:** Viewer, snapshot and mesh export apply bound appearance to
  a private descriptor. They select a tree and its document hash together,
  without separately hashing a later file revision. Scanner sends its validated
  annotation snapshot inline; browser loading does not re-fetch a different
  revision through a mutable URL. A snapshot rejects mismatched topology.
- **Reuse identity:** normalized appearance, including absence, joins the
  appearance-sensitive export ledger and composed-scene identity. Geometry,
  selectors and tessellation remain reusable across finish-only edits.
- **Reemit and publication:** exact parsed bytes must match the selected input
  digest. Warm gates validate both STEP and sidecar outputs, including missing,
  corrupt or unexpected annotations. Kinematics-only edits preserve already
  remapped output appearance. Output hashes/indexes update before an owned
  record snapshot is published last. Observed conflicts fail; separate atomic
  replacements still do not form a cross-writer transaction.

No new persistent cache layout, author-managed cache/session state or required
model imports were introduced. Existing decorators and `cad_material` remain
the authoring interface. Native STEP colors stay in STEP; PBR that the writer
does not serialize travels in the one existing sidecar.

## Cutover and limits

Model records and document mappings use payload schema 2. Old entries are
misses; document keys remain the exact file-byte digest. Component input v2
invalidates old extraction entries without changing content-addressed objects.
Old sidecar schemas fail with a regeneration message, as required by the
repository's hard-cutover policy. Release `VERSION` is unchanged.

Rebuild affected authored outputs to persist their PBR in schema-8 sidecars.
Old STEP files never carried these finishes, so losing both source and old
cache made them unrecoverable. The repair cannot recreate that lost information
or infer it from whichever finish last occupied a shared document index.

The original large-hand timings predate the canonical-tree and component-input
cutovers. They remain historical coarse-load evidence, not validation of this
runtime on the hand. The nine-part workload is measured again separately.
These changes do not establish the under-250-ms preview target, full-detail hand
interaction, native-mesher visual parity or comfortable browser memory headroom.

## Regression evidence

The added small fixtures cover:

1. Identical STEP bytes with different PBR: one canonical document tree,
   independently recoverable finishes and appearance-sensitive GLB reuse.
2. Generated, warm reconstruction and cold-import equality after full store
   deletion, including labels, nested groups, transforms and face-color variants.
3. Source-free saved readers and real GLB export; all supported PBR channels,
   removed/mismatched/unsupported annotations, and owned per-consumer metadata.
4. Exact child pins, moved/modified materialized children, private XCAF styles,
   deterministic warm/cold STEP bytes and nested kinematics mapping.
5. Reemit output-pair recovery and races where a selected file is replaced
   before scene parsing, scanning, snapshot setup or mesh export.
6. Real browser material-only edits and annotation removal: WebGL materials
   change while STEP/tree identity stays fixed and no new SURF/tessellation
   response body is requested. A posed snapshot is visually checked.

The browser check was run before the final Python-only component and reader
corrections; its bundled JS is unchanged. Full integration and installed-wheel
checks cover the final Python runtime. Timing from functional checks is not
used as performance evidence.
