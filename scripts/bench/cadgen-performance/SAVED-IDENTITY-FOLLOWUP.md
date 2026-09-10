# Saved document identity follow-up

**Not implemented. This is a confirmed remaining correctness item, not a
passing performance-plan validation.** No runtime behavior changed during this
investigation. The repair spans publication, appearance persistence and readers;
it must preserve existing finishes instead of removing them to make an identity
test pass.

## Reproduction and evidence

[The diagnostic JSON](results/material-document-identity-20260910.json) contains
the complete probe source, command, implementation file hashes, versions, both
trees and an empty-store import. The runtime fingerprint stayed unchanged during
the probe. All CAD outputs and isolated stores were created under `models/tmp`
and removed afterwards. This was a tiny functional probe, not a timing study.

The fixture is a `Solid.make_box(2, 3, 4)` named `box`, with the same RGBA color.
Only `cad_material` changes:

| Input | Roughness | Metalness | Saved tree |
| --- | ---: | ---: | --- |
| A | 0.1 | 0.2 | `bc7ad3c6dee72dfb42d13e79a282f59ecd886d2efeb939d2ef7ba08413e19688` |
| B | 0.9 | 0.8 | `b1cd6579066a68dbcc55cc410b2624fac25a20fc0f63b1379098a783f3009775` |

Both STEP files are exactly the same 17,263 bytes, with SHA-256
`1a428e89198c16d60befc052af2ab97b4f7fcdff2f231a0b3c4a18ae899cf725`.
The generated trees differ only in `occurrences`, specifically `material`;
their component is the same `e12ffa49f0b8a1fc`. Publishing B through
`note_document_tree` overwrites A's document entry. Either identical file then
resolves B's finish. The preview trees correctly differ too.

Loading those bytes as text STEP in an empty store, then applying the imported
scene packaging path, produces
`60a4cbb4cdf6eb150373b2c62d7f4872798b1bec31713d1a2e54734170c26258`.
It has no PBR material. The same component and RGBA also appear under different
grouping and names: generated `o1` / `box`, versus imported leaf `o1.1` /
`=>[0:1:1:2]` under an assembly root. Therefore removing `material` alone would
not establish generated/cold-import tree equality. This comparison uses the
low-level imported-scene packaging functions, not a full daemon integration run.

## Cause and compatibility choices

`component_package._occurrence_material` copies the five supported PBR channels
from the shape into an occurrence. `build_tree_through_step` replaces component
geometry after STEP read-back but retains source grouping, names and material.
`materialize_descriptor` applies placement, label and color; it does not apply
`cad_material`. The STEP exporter writes names, colors and per-face colors, with
no PBR write path. Schema-7 sidecars carry only kinematics and the document digest.

The viewer and GLB exporter already consume occurrence material. Keeping that
source-only value under `index/document/<STEP digest>` makes the rendered finish
depend on the last writer and loses it on cache deletion. Silently stripping it
would instead change saved renders and exported GLBs. Neither is acceptable.

Two compatible approaches require deliberate implementation:

1. Persist authored finish in the existing, digest-bound sidecar; separate a
   canonical document tree from the authored model result. This is recommended
   because it uses the existing artifact annotation boundary and does not depend
   on unimplemented exchange-format support.
2. Implement complete STEP serialization and read-back for every supported finish
   channel, including repeated occurrences and all consumers. Only bytes that
   actually carry those values could justify putting them in the document tree.
   Support and interoperability are unproven; this investigation does not claim
   that the current writer or chosen STEP representation can carry all channels.

## Recommended responsibilities and invariants

- **Document tree:** derive its geometry, hierarchy, names, colors and occurrence
  IDs through one canonical path from the actual STEP read-back. Generated saves
  and cold imports use that same path. The document index maps only the STEP
  digest to this tree. Deduplicate immutable component objects by content as
  before; do not reuse a source-shaped link graph as the document's hierarchy.
- **Model result:** retain canonical saved geometry plus the authored grouping
  and intrinsic appearance needed by decorated child composition. Keep this
  result distinct from the document tree in internal return values and model
  records. A child's exact result tree remains the pin; no child record reread
  or substitution of a later result is allowed during parent publication.
- **Early preview:** retain its authored geometry, grouping and appearance, with
  complete transitive pins. It remains a separate editing input. No preview or
  authored result tree is entered under a saved STEP digest. The saved event
  identifies the canonical document tree, while child completion identifies the
  model result. Explicit save still waits for every declared output.
- **Materials and pins:** materializing a model result must reconstruct its leaf
  `cad_material` as owned metadata, so a subsequently modified child does not
  lose finish when it stops qualifying as a link. Preserve the existing geometry
  and descendant-metadata integrity checks. Treat intrinsic appearance as part
  of the pinned result, not as a reason to read a child's sidecar. Parent
  kinematics remain the parent's own declarations.
- **One durable sidecar:** add an appearance section to `<name>.step.json`, with
  the next sidecar schema and the existing exact `documentHash` binding. Store
  resolved PBR numbers keyed by canonical document occurrence IDs, never source
  paths, model records or a preview-tree hash. The exporter must provide a
  verified mapping from authored occurrences to the written document's leaves;
  the box probe proves that copying existing IDs without mapping is unsafe.
  Ambiguous or missing mappings must fail, not misapply a finish.
- **Artifact readers:** compose a private copy of the byte-derived descriptor
  with its matching sidecar appearance for rendering, snapshots and mesh export.
  Never mutate a shared immutable tree or consult model/output records. Two
  files with identical STEP bytes and different bound appearance sidecars must
  share geometry and still render their own finishes. Geometry-only consumers
  keep geometry independent of optional appearance annotations.
- **Export and render identity:** include a canonical appearance digest, including
  the absence case, in appearance-sensitive export variants and composed-scene
  identity. Current mesh keys contain format, tolerances and optional animation,
  but no appearance. Preserve geometry/tessellation reuse across finish edits.
  Both declared and bare-door exports use the same appearance resolver and key.
- **Deletion and races:** file plus sidecar must fully reproduce a saved render
  after deleting the store and Python source. Stage the sidecar alongside STEP;
  preserve stale-build decisions, output-pair conflict checks and current-job
  fencing. Separate file replacements are not a transaction. A material-only
  save has the same STEP digest, so reader invalidation must observe sidecar
  content too; the STEP binding alone cannot signal that appearance changed.

These distinctions preserve immutable source-free objects and input-addressed
indexes. Authoring stays decorator-only with the existing `cad_material`
attribute; no session/cache helpers or new required imports belong in models.
Contracts must explicitly distinguish authored result appearance from the
byte-derived document tree before this change ships.

The canonical-tree change also needs a cache-schema cutover so an old document
entry cannot masquerade as the new representation. Existing STEP files never
persisted these PBR values, so a source-free file whose old cache is gone cannot
recover them retroactively. Rebuild affected authored outputs into the new file
pair while their sources are available. Do not attempt recovery from whichever
material last won the shared document index. Sidecar migration/cutover policy
must be explicit; this proposal does not claim that legacy artifacts already
contain enough information for a lossless upgrade.

## Implementation touchpoints

| Surface | Required work |
| --- | --- |
| `packages/cadgen/src/cadgen/store/build.py` | Separate model-result and document-tree publication; canonical read-back packaging and occurrence correspondence; preserve early preview. |
| `packages/cadgen/src/cadgen/_internal/step_scene_loader.py`, `_internal/step_scene_mesh.py`, `_internal/step_scene_package.py`, `step_export.py` | Unify generated/cold document hierarchy and names; expose verified correspondence; keep warm geometry reads equivalent to raw STEP. |
| `packages/cadgen/src/cadgen/store/materialize.py`, `store/trees.py`, `store/lazy.py` | Preserve owned material metadata through exact pinned composition and mutation; avoid source or sidecar lookup during child materialization. |
| `packages/cadgen/src/cadgen/_internal/generation.py`, `store/records.py`, daemon result/event plumbing | Carry both result identities without overloading one `tree`; publish the canonical document index and bound sidecar under existing ordering rules. |
| `packages/cadgen/src/cadgen/_internal/source_sidecar.py` | Appearance schema, validation and warranting/removal policy; preserve imported annotations. |
| `packages/cadgen/src/cadgen/viewer/scanner.py`, `snapshot_cli.py`; `packages/cadgen-js/src/common/kinematicsModule.js`, `source.js`; viewer loading/session code | Shared annotation validation and appearance composition; refresh on appearance-only edits without modifying the canonical descriptor. |
| `packages/cadgen/src/cadgen/_internal/mesh_export.py`, `step_export_target.py`; shared JS mesh export | Pass resolved appearance to the common exporter and include its digest in the shared variant gate. |

## Required regression coverage

1. Same exact box STEP bytes with different PBR values produce one document tree
   and two independently recoverable finishes; no last-writer cross-file bleed.
2. Generated document tree equals cold-import tree after deleting the complete
   store. Check grouping, IDs, labels, colors, face colors and geometry, including
   the single-part wrapper/name repro and repeated nested occurrences.
3. Source removed and store empty: viewer, snapshot and bare GLB export preserve
   appearance from the file pair. Missing sidecar gives documented defaults;
   mismatched binding and unsupported schema fail explicitly.
4. Every supported PBR channel survives save/reopen and GLB export. A finish-only
   sidecar edit invalidates the appearance-sensitive mesh gate while sharing
   component objects and tessellation. Removing finish clears a stale section.
5. Warm, disk and fresh child materializations retain equivalent finish and owned
   metadata. Moved and modified children keep it; nested pins cannot substitute a
   newer child or silently drop a missing object. Child kinematics do not leak.
6. Preview/result/document identities remain distinct across success, failed
   persistence, stale builds and coalesced children. Late events cannot reopen a
   finished revision. All declared exports are complete before save success.
7. Concurrent material-only saves, output-pair conflicts and interruption between
   STEP/sidecar replacements obey the documented old-or-new file behavior;
   annotation identity is never inferred solely from the unchanged STEP digest.
