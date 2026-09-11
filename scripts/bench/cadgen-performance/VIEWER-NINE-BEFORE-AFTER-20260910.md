# Nine-part viewer before/after — 2026-09-10

These measurements apply to the recorded source fingerprints. The later
[medium ownership and recovery checks](VIEWER-OWNERSHIP-INTEGRATED-20260910.md)
validate `8971f760d` and the alert correction in `c07488e1d`; they are separate
functional evidence, not a replacement matched latency comparison.

## Original reviewed viewer

The original `7aa3e85be76f305437abd3d7aba26e38b28e43cb` viewer rendered the
same 2,268,663-byte STEP used by the prepared current fixture: SHA-256
`406dd2e19b6a4ea3a623abd19b03708b7d9e97b4402ba4161c737eb31f10fdca`.
Its existing document index, last written at 17:13:18 UTC, maps those bytes to
tree `d34345bdc0a7a6a030f34af8872d6ad9a6ab43f24ca5bcfa83e00edb2e298e01`.
These browser runs did not cold-compile the STEP.

| Measurement | Cold tessellation, one run | Cached tessellation, median (range), three runs |
| --- | ---: | ---: |
| First geometry on screen | 472 ms | 317 ms (311–325) |
| Sampled final-display gate | 720 ms | 673 ms (671–676) |
| Largest renderer RSS | 276.7 MiB | 200.4 MiB (199.6–202.2) |
| Largest renderer after diagnostic GC | 263.6 MiB | 185.6 MiB (184.4–188.6) |

Every run used a fresh Chromium 148.0.7778.96 profile, without allocation
sampling, and displayed nine unique components / nine occurrences with 6,452
unique triangles. Viewport refinement was disabled; all worker requests used
the original default tessellation options `{}`. The cold run made nine mesh
requests and wrote nine cache entries; each cached run read nine cached entries.
Each run created eight workers and terminated all eight. The cold run recorded
nine HTTP 404 console messages; cached runs recorded none. No run crashed or
reported an allocation failure.

The private archive's 629 original source blobs were verified unchanged, and
its Vite alias resolves the archived shared source. Original and current locks
agree on the actual installed Three 0.185.1 / BVH 0.9.14 / React 18.3.1 versions.
Served index/assets matched the archive byte for byte. Archived source
`8c733b2a2b6fbc2a74460c4dcba50cc06e52f0994e6472b9ffbd4fc1c1857b15` and client
`e3add773d6582b0282e3683dd55b9c4818f3b12da791ad7946099737c345108f`
were identical at the start and end of all four runs. Imported Python module
paths were also verified under the archive's `packages/cadgen/src`.

Original 7aa did not publish `meshCost.occurrenceCount`, and its stage text
remains `LOADING` even after final publication. The archive-only completion
adapter supplies the independently verified expected count of nine, then
requires actual rendered occurrences nine, scene records nine, final nine-part
publication and nonzero draw activity. The current completion gate is unchanged.
The legacy scene byte ledger excludes indirect BVH permutations; process RSS
is the comparable memory measurement. The completion gate is sampled and is
not a precise source-publication timestamp.

Conservative process windows were 19:07:51.624–19:08:13.711 UTC for the first
three runs and 19:09:18.058–19:09:25.462 UTC for the third cached sample.
Per-run wall-clock timestamps were not recorded by that harness revision;
future runs now record them. The other agent's completed test call preceded
the hold message and module setup at 19:07:30.585 UTC, so no compute overlap
was observed. The owned viewer on port 3272 was stopped afterward.

Raw data and provenance: [summary](results/viewer-nine-before-summary-20260910.json),
[cold and first two cached samples](results/viewer-nine-before-7aa-locked-20260910.json),
[third cached sample](results/viewer-nine-before-7aa-locked-cached3-20260910.json).
Setup failures and the exact isolated source/dependency proof are retained in
those reports.


## Matched integrated viewer checkpoint

The same STEP bytes were served from a precompiled canonical document in a
separate owned store, with fresh Chromium profiles and the same locked libraries.
Current source `2784ca70dd7f3d0308fcecc9ec70bd684df4d36d8505ff51b2c0841a4d83a155`
and client `19bb23ade1e59a31558f4cb4e9719e16392258fc8f83a18da6e9be80ab0a8035`
were unchanged throughout. Served index/assets matched disk. Runs occupied
19:20:49.742–19:21:18.290 UTC, without other timed work or allocation sampling.

| Measurement | Before cold | After cold | Before cached median (range) | After cached median (range) |
| --- | ---: | ---: | ---: | ---: |
| First geometry | 472 ms | 378 ms | 317 ms (311–325) | 272 ms (269–283) |
| Sampled final-display gate | 720 ms | 667 ms | 673 ms (671–676) | 664 ms (660–666) |
| Largest renderer RSS | 276.7 MiB | 288.1 MiB | 200.4 MiB (199.6–202.2) | 163.5 MiB (159.5–164.5) |
| Largest renderer after diagnostic GC | 263.6 MiB | 276.1 MiB | 185.6 MiB (184.4–188.6) | 154.7 MiB (153.2–156.3) |

Cached first geometry improved 14.2% and cached peak renderer RSS fell 18.4%.
Cold renderer RSS increased 4.2%; the complete-display sampled gate changed
little. These are four runs per implementation, not a broad statistical study.

All current runs rendered nine components / nine occurrences. Current default
meshing produces 6,482 triangles versus the original 6,452; this comparison keeps
identical STEP bytes and default `{}` worker options, and includes mesher changes.
Both disable viewport refinement. Current runs created and terminated four
workers versus eight originally. The current cold run had nine expected cache
404 misses; cached runs had none. There were no crashes or in-page errors.
Raw current data: [four samples](results/viewer-nine-after-locked-20260910.json).

## Matched lifecycle checkpoint

[Lifecycle report](results/viewer-lifecycle-locked-20260910.json) covers a
24-occurrence/two-component fixture, six switches to and from the nine-part
fixture, orbit, five seconds of authored animation, and six replacements of saved
STEP bytes. It excludes Python source execution. All 13 assertions passed:
canonical L1 completion, lazy selector demand, instance reuse, worker reclamation,
no limitations and stable GPU allocations. First selector demand used the tree
expansion fallback, so its 102.8 ms is not a dense ray-picking measurement.

Orbit and animation frame intervals had 9.0 ms p95 (9.4/9.3 ms maximum).
Across six edits GPU allocations stayed at 21,744 bytes and the owned-resource
ledger stayed at 385,376 bytes. Collected heap grew from 21.94 to 22.43 MB;
this bounded run does not establish an indefinitely flat JavaScript heap.
The first saved replacement completed in 1,921 ms; the following five took
372.2 ms median (352.5–378.5). The original STEP bytes were restored and verified
against SHA-256 `ab104f441544b852390825f5c7589a0815a3448024bf88b1af27fd754786e370`.
Expected stale request cancellations occurred during switching, with no page
errors. Source/client/dependency fingerprints were stable over the recorded
19:23:06.965–19:23:53.169 UTC window.
