# Tiny procedural and canvas validation

This validation covers a deliberately small procedural fixture and the final
canvas-selection regression. It does not measure the nine-part planetary target,
does not establish a 250 ms preview, and does not support a broad speedup claim.

## Tiny procedural scope

The approved fixture contains one box and two cylinders: three valid solids,
three named occurrences and 12 faces. It has an ordinary monolithic author and
an ordinary decorated-child author with three exact child pins. The fixture and
all generated STEP files lived under `models/tmp/tiny-procedural-safe`. No hand
or planetary geometry was used.

Four serial conditions compared the immutable pre-cut runtime with candidate
commit `ebce2a143`, for the monolithic (BM/CM) and decorated-child split (BS/CS)
authors. Each condition made one unmeasured initial build followed by one
measured unchanged call, one simple box-geometry edit and one placement edit.
The complete study was 16 calls, 12 measured calls and no repeated samples. The
caller/runtime imports were established before the measured calls; each
condition ran separately and cleaned up before the next one.

| Condition | Unchanged total, ms | Geometry total / preview / saved, ms | Placement total / preview / saved, ms |
| --- | ---: | ---: | ---: |
| BM, pre-cut monolithic | 9.25 | 47.17 / 25.65 / 45.74 | 40.26 / 21.95 / 38.84 |
| CM, candidate monolithic | 12.44 | 55.65 / 35.41 / 53.87 | 51.16 / 29.45 / 49.00 |
| BS, pre-cut split | 21.81 | 3,370.98 / 3,295.66 / 3,366.90 | 63.23 / 40.72 / 59.05 |
| CS, candidate split | 12.09 | 189.50 / 120.85 / 183.99 | 75.85 / 50.71 / 71.22 |

These are single observations on a shared host. In particular, the 3.37 s BS
geometry row is not evidence of an 18× implementation speedup. The daemon log
shows that the pre-cut geometry edit started a new child worker (`64523`) and
spent 3.30 s running `block.py`; its three initial child imports had used workers
`64476`–`64478`. The candidate geometry edit reused worker `64599` and its child
run took 0.12 s. The evidence therefore confirms different worker/import state
inside those measured calls, but it does not isolate why the pre-cut daemon
replaced that worker or attribute the difference solely to deferred SURF.
The candidate monolithic geometry and placement observations were mildly slower
than the pre-cut observations. More samples would be required for causal or
population claims.

The study completed in 28.898 s under its 90 s deadline. Peak owned RSS was
1,774,714,880 bytes, below the 2 GiB limit. Every call returned the expected
`current` or successful compiled result, sources were restored, split child-pin
transitions were exact, and all owned runtime/daemon processes and sockets were
closed. Parity passed for three solids, 12 faces, bounds, native BREP bytes within
each runtime pair, STEP bytes within each authoring/runtime pair, occurrence
appearance and placement across authors, and all source restorations. Geometry
tree and component IDs were not compared across the schema cut.

An initial private-path preflight produced no accepted condition or sample. Its
JSON still contains the planned `calls: 16` field, but its conditions are empty
and its elapsed time is 0.00015 s; it is retained as failed, zero-call evidence.
The next attempt completed BM, CM and BS, then stopped before creating CS. It
therefore executed 12 real build calls, nine marked measured, over 16.714 s. Its
three completed conditions restored their sources and the split daemon exited,
but the raw JSON retained no controller exception or stderr. The stop cause is
unknown. That attempt cannot supply a matched four-condition comparison or full
parity result, so none of its observations appear in the table.

The successful run used a fresh `run-20260911-v2` fixture, stores and result
path. Across the failed preflight, incomplete attempt and successful v2, the
tiny work executed 28 actual build calls, 21 marked measured; the table reports
only the complete 16-call v2. The exact failed preflight,
[`tiny-procedural-safe-failed-preflight-20260911.json`](results/tiny-procedural-safe-failed-preflight-20260911.json),
incomplete raw report,
[`tiny-procedural-safe-incomplete-v1-20260911.json`](results/tiny-procedural-safe-incomplete-v1-20260911.json.gz),
and [diagnostic record](results/tiny-procedural-safe-failed-trials-diagnostic-20260911.json)
remain available rather than being folded into the successful comparison.

The earlier proposed 128-call planetary study was rejected by automatic approval
review and never executed. Its exact pre-marker design remains private with SHA-256
`0e0146c2530ddf9ce0b3f33bbb80de260d1d9f4396ab7aeb17aaa2c8f85d8953`;
it must not be launched, adapted or treated as approved.

The exact successful study is preserved as a
[lossless gzip archive](results/tiny-procedural-safe-v2-20260911.json.gz).
Its decompressed JSON SHA-256 is
`5d5554e569c67f82c5d7b8f6310bbf7dc0cfb4046e4fda752fdfd1eb46c30412`;
the compression registry records both raw and archive hashes.
The independent parity record is
[`tiny-procedural-safe-v2-parity-20260911.json`](results/tiny-procedural-safe-v2-parity-20260911.json)
(SHA-256 `a90cb244e09040e6bd6f5ac9b95ba11c149024e2cd037c64214e5391a200b862`).

## Canvas selection

The lifecycle browser coverage had selected a STEP tree row. It never exercised
a real WebGL-canvas click after lazy selector topology loaded, so it missed an
activation-order bug: a collapsed assembly part click was deferred waiting for
optional topology that the collapsed tree intentionally never requested.
Commit `c83b191cf` now commits a valid part pick before topology deferral, treats
the empty assembly topology key as an exact value, and clears/fences pending
activations by the selected file and tree.

The final isolated browser ran the canonical `/assets/index-YIbFxBO-.js` bundle.
All nine assertions passed: a collapsed canvas click selected component `o1.3`
without a surface-resolution request or SURF body fetch; after lazy topology and
multiple hovers, canvas clicks selected face `o1.3.f5` and edge `o1.3.e237`; both
showed the exact `planetary.step#...` Copy reference; replacing the document
dropped the old reference; and no console error occurred. This was a functional
check, not a browser timing measurement. The exact browser record is
[`viewer-canvas-selection-20260911.json`](results/viewer-canvas-selection-20260911.json)
(SHA-256 `8d9317de665c38ee8cf5b36f5e490c3c960c7045d271d4b4317b3a69935244d3`).

The final edge screenshot's blank Tree pane was not intentional harness setup.
It was captured 330 ms after selecting the deep `e237` row, while that selection
also scheduled the tree's auto-reveal. A focused follow-up waited two seconds and
found 31 rendered tree rows, with `e237` active and visible at y=269–297; no
console error occurred. The Tree pane therefore settled correctly. The compact
[settled-tree record](results/viewer-edge-tree-settle-20260911.json) has SHA-256
`eef4afd2f9774c53d35855fe59ab2112e397fbea8c227ae5c142dec906cab465`.

The final client suite passed 514/514 at the same selection source commit. Its
compact record is
[`viewer-canvas-selection-tests-20260911.json`](results/viewer-canvas-selection-tests-20260911.json);
the retained 45,053-byte exact output has SHA-256
`cbe3ae32a39e8b245dfaae9fc7e8e639e6317f5987543c4579e6654c1a871b29`.
That complete output is also embedded in the
[final follow-up validation record](results/final-followups-validation-20260911.json).
