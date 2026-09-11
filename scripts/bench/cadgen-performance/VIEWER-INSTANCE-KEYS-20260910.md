# Surface instance ownership and material keys — 2026-09-10

The bounded Node probe found no retained retired instance sets or LOD geometry.
It did identify repeated material-key serialization during unchanged instance
reconciliation. The patch reuses key strings after reading and comparing all
current material scalars, emission state, render order and clipping-plane
values. Custom values and custom clipping mappers keep ordinary serialization;
no caller dirty flag or persistent cache is involved.

| Same Node workload | Before key memo | After key memo |
| --- | ---: | ---: |
| 20 unchanged syncs, median of 3 batches | 7.728 ms | 2.981 ms |
| Material JSON calls per batch | 5,920 | 0 |
| Serialized characters per batch | 1,899,840 | 0 |
| Live JS after 24 replacements and yielded GC | 16.391 MB | 16.618 MB |
| Live typed-array backing after replacements | 113,827,279 B | 113,827,279 B |

The fixture uses eight real cached heavy hand components, with 32 synthetic
occurrences of each. Each replacement creates fresh position/normal/index
arrays for one component while retaining its geometry. All 24 retired component
objects, 768 records, 24 instance sets and 24 geometries became unreachable to
their WeakRefs after macrotask boundaries and explicit GC in both runs. The
key snapshots add about 220 KB of live JS for this 256-occurrence fixture.

These are isolated Node v26.7.0 measurements, with no tessellation, React,
WebGL, browser or complete model-load timing. They do not establish a browser
speedup or prove the absence of renderer-side retention. The reports contain
the exact executed helper, its SHA-256, the same cached input identities and
matching header coverage, and unchanged runtime fingerprints within each run:
[before](results/viewer-instance-ownership-before-key-memo-20260910.json) and
[after](results/viewer-instance-ownership-after-key-memo-20260910.json).
The after measurement precedes a narrow correctness follow-up preserving native
map holes when a clipping getter removes a later plane. The ordinary no-clipping
path measured here is unchanged; the report records its exact checkpoint source.

The existing full-hand failure is not a proven instance leak. Both compared
hand reports had 156 surface sets, 2,549 instance slots and 193,724 instance
attribute bytes. The diagnostic calls GC **before** a one-second settle while
queued publications can still allocate; its later 333.8 MB main-JS reading is
not a quiescent retention measurement. The 376-L1/490-L0 gate must remain
distinct from the later 390 swap events during failure collection.

A header-only census found all 866 coarse entries and only 378 canonical L1
entries. The measured mixture of those canonical entries plus the remaining
coarse entries has 281,663,436 surface-array bytes, exactly the hand report's
surface bytes minus its instance attributes. All-L1 storage for the remaining
488 components is unknown; this census cannot declare that working set feasible
or infeasible. Default LOD admission preserves current components on failure and
can coarsen under estimated pressure, but the failed run reached its 2 GiB RSS
stop while the ledger still reported available space. It is a soft estimate,
not a crash guarantee. No budget or quality threshold changed in this patch.

Validation: 46 focused scene, instance and transform tests pass, including
original key-byte parity, nonfinite numbers and negative zero, every direct
material field mutation, in-place emission/plane edits, numeric conversion
callbacks, custom serialization/mapping, unchanged nonempty clipping arrays,
getter-created sparse clipping arrays, render order, selection, deformation and
shared ownership.
