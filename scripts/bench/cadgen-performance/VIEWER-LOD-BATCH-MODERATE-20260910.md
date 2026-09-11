# Moderate LOD batch comparison

Grouping four replacements reduced six scene publications to two in both zoom
directions on the nine-part planetary assembly. Compared with the same candidate
configured to size one, the last component adopted about 42 ms sooner. The first
refined draw arrived about 7–11 ms later. All nine alternating measured runs
preserved identical final component arrays, concrete tessellation keys, occurrence
counts, and selected-face coverage, and released all reservations and staged
buffers.

This is a small browser study, with three samples per condition. It compares the
validated `c07488e1d` client with a private candidate at sizes one and four, before
main integration. It does not measure CAD generation or saved STEP latency, and
uses no tendon-hand input. The candidate's lower publication count is directly
observed; these samples do not establish a general latency or memory improvement.

| Metric, median | Old size one | Candidate size one | Candidate size four |
| --- | ---: | ---: | ---: |
| Zoom in: first refined WebGL submission | 295.3 ms | 227.8 ms | 239.1 ms |
| Zoom in: last component adoption | 368.5 ms | 297.9 ms | 256.0 ms |
| Zoom in: main scene synchronization | 6.8 ms | 6.8 ms | 4.0 ms |
| Return: first refined WebGL submission | 219.7 ms | 219.6 ms | 226.5 ms |
| Return: last component adoption | 285.7 ms | 289.0 ms | 246.9 ms |
| Return: main scene synchronization | 5.7 ms | 6.3 ms | 2.7 ms |
| Publications per zoom phase | 6 | 6 | 2 |
| Largest renderer peak | 213.3 MiB | 216.7 MiB | 202.9 MiB |

The near-view input-to-first-adoption interval varied by roughly 75 ms in the old
and candidate-size-one samples. For example, candidate size one's last-adoption
range was 289.7–370.9 ms, while size four's was 254.7–256.6 ms. Retain that spread
when interpreting the median. Return last-adoption ranges were 278.2–289.0 ms old,
282.3–292.2 ms candidate one, and 246.6–250.5 ms candidate four.

Adoption means the matching CPU/Three scene and memory accounting are in place.
A WebGL submission is not a GPU completion timestamp. The harness also records
observed stable settlement using identical 75 ms polling and a 300 ms confirmation
window; those values include that confirmation delay. Composition notifications
provide a call count, but composition duration was not separately instrumented.
Renderer peaks include the bounded workload and small after-grade numeric/hash
collection; there was no heap snapshot, allocation sampler, or forced GC.

The sequence was candidate one / candidate four / old, candidate four / old /
candidate one, then old / candidate one / candidate four. It ran from
2026-09-11 01:25:10 to 01:25:41 UTC after two explicit warmups and three passing
smoke checks. Every measured render-worker request received cached bytes, and no
measured tessellation-cache HTTP request missed. Each fresh Chromium 148.0.7778.96
context used the same 1400 × 900 viewport, STEP bytes, canonical store, current
Python backend, and locked dependencies (Three 0.185.1, BVH 0.9.14, React 18.3.1).
The team held other compute; unrelated user applications and the user's existing
viewer were left alone.

Each run checked its private frontend source, actual served entry assets, and all
emitted workers against disk before opening the model. Backend module paths were
recorded inside each exact server process, separately from the private frontend
fingerprint. The candidate is not represented as having a private Python tree.
The old client does not store every concrete mesh key on its display wrapper;
its keys were reconstructed from the explicit displayed level, actual server
origin, immutable descriptor identity, verified shared key implementation, and
array hashes. Candidate stored keys also matched that reconstruction.

Both zoom directions retained `topology|o1.1|face|o1.1.f1`, and selector face-run
coverage matched the displayed triangles. All eight shared mesh-array fields
were hash-compared across conditions. The descriptor and occurrence placement
inputs matched exactly. The three smoke screenshots show the same complete
assembly, selected carrier face, matching reference inspector, and no error
overlay. No uncaught page exception occurred; arbitrary console messages were
not collected by this harness.

Two harness preflights remain as evidence. The first stopped before zoom because
it looked for a text-only face row instead of the actual `Face …` label. The
second completed the workload but rejected its after-grade key proof because
Node omitted the browser origin; all 18 keys matched once resolved against the
actual server. Neither is included in the medians. The smoke warm-cache boolean
also used the wrong capability field; the final measured gate uses `render`.
A separate audit confirmed all 27 render requests in each smoke received cached
bytes.

The result supports integrating size four with its first-draw tradeoff visible.
The private measurement servers and browsers closed at 01:25:41.966 UTC; existing
user viewers remained alive.

The combined main client, committed as `9be4f5424`, subsequently passed two short functional checks against
the verified `index-CoxYL4aV.js` bundle: 21 assertions for a real two-CID partial
scene failure and 11 for a delayed worker reply across a model switch. Both
staged components remained charged through teardown. A microtask after actual
restoration captured all 24 old source-mesh identities and levels together with
the selected face and exact selector coverage. The successful-adoption alert
cleared, and every lease, staging owner, and worker drained. A separately admitted
lower level may follow restoration; the first functional preflight incorrectly
required final idle to remain at the old levels, and is preserved as a harness
qualification. The corrected check separates exact restoration from that valid
fallback. The stale reply could not replace the new complete model.

These follow-ups are functional, with no timing claim and possible overlap with
other private functional tests. Their source digest is
`ce9037b2438a320a40cc75bfe00f2663d89f2eeb387ca6346a11b50840aefac7`
and built-client digest is
`7baac3ae3579a2765ee040c196f6ba87aa4f4a1e6eb0ffbc8897bdc676a84a52`.
The private browsers closed, while the user's server on 3276 stayed running.
Root visually reviewed the complete candidate-size-four planetary view and the
combined restoration close-up: the expected geometry and selected reference are
present, with no obsolete restoration alert. The integrated client passes 506
viewer and 1,015 shared JavaScript tests, plus canonical bundling and freshness.

- [Summary, ranges, exact source scopes, and raw report hashes](results/viewer-lod-batch-moderate-summary-20260910.json)
- [Exact successful measurement helper sources](results/viewer-lod-batch-moderate-harness-20260910.json)
- [Old smoke screenshot](../../../models/tmp/viewer-matched-nine-after/viewer-batch-v2-smoke-old-3-20260910.png)
- [Candidate size-one smoke screenshot](../../../models/tmp/viewer-matched-nine-after/viewer-batch-v2-smoke-candidate1-4-20260910.png)
- [Candidate size-four smoke screenshot](../../../models/tmp/viewer-matched-nine-after/viewer-batch-v2-smoke-candidate4-5-20260910.png)
- [Combined two-CID restoration report](results/viewer-repeated24-restore-batch-integrated-v2-20260910.json.gz)
- [Combined delayed-reply switch report](results/viewer-nine-delayed-replacement-batch-integrated-20260910.json.gz)
- [Combined restoration close-up and selected reference](../../../models/tmp/viewer-matched-nine-after/batch-integrated-restore-selected-v2.png)
