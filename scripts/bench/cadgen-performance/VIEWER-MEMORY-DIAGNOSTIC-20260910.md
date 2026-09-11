# Canonical hand memory diagnosis — 2026-09-10

## Full hand all-L1 gate passes with selection identity preserved

The [isolated selection-only hand run](results/hand-canonical-l1-selection-identity-20260910.json.gz)
passes the unchanged **866 components at L1 / 3,259 occurrences / 180 seconds /
2 GiB largest-renderer** gate. All nine acceptance assertions pass. Every
component reaches L1 at 97.581 seconds; workload-only and overall renderer
peaks are both **1,482.141 MiB**, leaving 565.859 MiB below the limit.
No collection or allocation sampling occurs before grading. The
[compact summary](results/hand-canonical-l1-selection-identity-summary-20260910.json)
retains the exact gate counts, clocks, owners, source proof and harness diff.

This client is commit `2709968dc` plus only the three selection-filter files
validated by the medium snapshot below. It excludes the concurrent LOD ownership
changes in the working tree. All L0/L1 entries were already cached; no HTTP
failures or cache writes occur. This is a functional/memory acceptance result,
not an isolated latency speedup or proof of complete FreeCAD parity.
The earlier `2709968dc` all-L1 failure at 654 L1 / 212 L0 remains unchanged.

First geometry is drawn at 900 ms. Initial completeness appears in the source
publication at 15.7649 seconds, the ramp observer at 15.909 seconds, and the
launcher log at 15.920 seconds; these clocks remain distinct. Grading occurs
September 11 at 00:40:33.326 UTC, and the private browser is closed by
00:40:40.058 UTC. The services on 3262, 3267, 3273, 3274 and 3275 remain alive;
the user's frozen play viewer is unchanged.

The final ledger contains 469.556 MB displayed CPU backing and 456.820 MB GPU
estimate, with no replacement reservation, retained worker charge, limitation
or BVH. All six created workers terminate normally. After the separately
labelled diagnostics, main JS is 72.931 MB and backing storage 473.746 MB,
only 4.190 MB beyond displayed CPU ownership. The generic diagnostic does not
verify main-thread quiescence, so its flag remains false; the passing grade
precedes those collections. The final 128 recorded worker requests are all
cached, with median execution 0.4 ms and start spacing 94.6 ms. These are a
bounded tail sample, not whole-run network or CPU attribution.

The combination of the medium's concrete retaining path, isolated 503-to-9
context reduction, preserved nonempty selection behavior, and this unchanged
full-hand gate supports the narrow identity-preservation fix. The final
integrated client still needs validation after concurrent ownership changes
are included. Normal adaptive fine-detail interaction is a separate checkpoint.

## Quiescent medium snapshot: historical workspace scopes

A [nine-part diagnostic](results/viewer-nine-retainer-20260910.json.gz) repeats
20 zoom cycles between 800% and 100%, waiting for actual quality/adoption idle
on each leg. It completes 246 LOD adoptions in a 19.198-second workload, then
returns to 100% and verifies unchanged publication, adoption and level counters
across two collections and the heap snapshot. All nine parts remain displayed;
the saved screenshot shows the complete colored gear assembly and nine tree rows.
This is a retaining-path diagnostic, not a latency or acceptance comparison.

The [compact structural evidence](results/viewer-nine-retainer-paths-20260910.json)
finds **503 strongly reachable CadWorkspace contexts**, all sharing one V8
scope-info object. They hold 250 distinct `assemblyPartMap` maps and 250
`validAssemblyLeafIdSet` sets. The contexts alone occupy 774,620 shallow bytes;
this is not their transitive retained size. Medium `assemblyParts` and
copy-reference maps have only four and three distinct generations respectively,
so the hand's much larger wrapper allocation cannot be extrapolated directly.

A representative path starts at the document's ordinary React Fiber, follows
`alternate.pendingProps.onSelectEntry`, then reaches a workspace context.
It alternates through `handleHideOtherTreeNode` and
`scheduleActiveFileSessionSave` callback contexts 245 times each, visiting 491
workspace contexts over 991 edges. **Weak edges and every `__cad*` probe edge
are excluded** from this root traversal; remote object groups and console
entries were also cleared before capture. The path is not caused solely by a
benchmark-held model handle.

The identities along that path give a precise two-render pattern:

| Transition | Count | Preserved | Replaced |
| --- | ---: | --- | --- |
| Derived maps to selection update | 245 | Assembly map and valid-leaf set | Selected-part, selected-reference and hidden-part arrays |
| Selection update to next publication | 245 | All three selection arrays | Assembly map and valid-leaf set |

There are no exceptions along the sampled full path. The 250 selected-part,
251 selected-reference and 250 hidden-part arrays have no indexed elements.
The existing selection-validity effect unconditionally filters those arrays
on every valid-ID update; even unchanged empty selections receive new array
identities. Those identities invalidate the session-snapshot and save callbacks,
while the next mesh publication invalidates the assembly-selection callbacks.
Their shared lexical context connects prior generations.

This supports an identity-preserving validity filter as the next **bounded
counterfactual**, preserving real removals and avoiding the redundant render.
Merely cutting the two named callback-slot edges in the snapshot graph leaves
all 503 contexts reachable through sibling callbacks, so isolating only those
two functions would not be a proven complete fix. Real selection changes and
other independently changing callback groups still require validation.

After collection, main JS is 21.419 MB and backing storage is 19.953 MB;
`Runtime.getHeapUsage` reports backing storage separately from JS and embedder
heaps. The raw 57,395,144-byte snapshot remains local at
`/private/tmp/cadgen-performance-20260910/viewer-nine-retainer.heapsnapshot`;
the compact report records its SHA-256 and analysis-helper hashes. Capture ran
September 11, 00:24:35.966–00:24:58.436 UTC, against source/client
`151539c7…` / `ded016dc…`, with the exact served entry and four worker assets
verified before and after. The largest renderer reached 489.438 MiB including
snapshot overhead. The private browser closed; all viewer services remain.

The preceding large-hand retaining attempt is preserved in
[its failure report](results/hand-retainer-settled-tree-20260910.json.gz). It crossed
the RSS guard during recovery after unzoom, at 826 L0 / 2 L1 / 26 L2 / 12 L3,
70 adoptions and one pending worker/reservation. It never became quiescent and
produced no heap snapshot. That unsuccessful attempt is not evidence of a new
regression against differently warmed fine-detail caches.

## Isolated selection-filter counterfactual

The [candidate capture](results/viewer-nine-retainer-selection-identity-20260910.json.gz)
uses an archive of commit `2709968dc`, with exactly three changed files:
`useCadWorkspaceSelection.js`, `workbench/valueUtils.js` and its test.
All 474 archived blobs were checked against the commit before those changes;
all other current LOD-ownership work is excluded. Individual dependency links
use the same locked installs, and Vite resolves shared CAD source from the
archive. Entry and all four worker bytes match that isolated build before and
after capture. The archive-source digest is a separate 474-file inventory
scheme, so it must not be confused with the whole-runtime digest above.

The same 20 zoom cycles produce the same 246 adoptions and final
6 L0 / 1 L1 / 2 L2 state. Quiescence holds across collection and snapshot.
[Exact remapped snapshot bindings](results/viewer-nine-retainer-selection-identity-paths-20260910.json)
show:

| Retaining evidence | Original | Selection-identity patch |
| --- | ---: | ---: |
| Strongly reachable workspace contexts | 503 | 9 |
| Distinct assembly maps | 250 | 5 |
| Distinct valid-leaf sets | 250 | 5 |
| Selected-part / reference / hidden arrays | 250 / 251 / 250 | 2 / 2 / 2 |
| Main JS after collection, decimal MB | 21.419 | 16.430 |
| Backing storage after collection, decimal MB | 19.953 | 3.393 |

This supports the array-identity change as a cause of the historical-context
retention in this workload. It does not establish zero retention under every
sequence of genuine selection or session changes. Pre-collection JS is
26.205 / 31.751 MB; spontaneous collection timing differs. Peak renderer RSS
of 489.438 / 340.750 MiB includes the heap-snapshot phase and must not be
reported as ordinary viewer-memory improvement. No speedup is claimed from
19.198 / 19.519-second diagnostic workloads.

A [separate functional check](results/viewer-nine-selection-identity-functional-20260910.json)
selects `carrier_plate` (`o1.1`), zooms to 800% and back, and confirms the same
selected ID, visible highlight, all nine components/occurrences, and no pending
adoption. The Hide menu action then adds that ID to the hidden list and visibly
removes the carrier plate. All seven assertions pass with no page errors.
This check is outside the matched heap workload. A [failed harness preflight](results/viewer-nine-selection-identity-functional-preflight-failed-20260910.json)
is retained: its complete-part assertion named a nonexistent telemetry field,
and its context-menu locator matched both the tree and the selected summary.
Those harness issues were corrected before the passing check.

Both private browsers closed. The isolated medium viewer remains on 3274;
3262, 3267 and 3273 are preserved. The subsequent unchanged full-hand L1/RSS gate against this isolated client
passes as recorded above.

## Allocation origins at the bounded 60-second checkpoint

The [current allocation diagnostic](results/hand-l1-allocation-settled-tree-20260910.json.gz)
stops after its 60-second milestone at 418 L1 / 448 L0, with all 866 components
/ 3,259 occurrences displayed. Peak renderer RSS is 1,796.547 MiB. This is
**not acceptance or a timing comparison**: allocation sampling runs from before
navigation at a 32,768-byte interval. No forced collection occurs before the
milestone. Five additional publications occur during diagnostics, so the later
423-event count is not the milestone count. Both the [before profile](results/hand-l1-allocation-settled-tree-20260910-before.heapprofile.gz)
and [after profile](results/hand-l1-allocation-settled-tree-20260910-after.heapprofile.gz)
retain original CDP call frames and columns; the [summary](results/hand-l1-allocation-settled-tree-20260910-summary.json.gz)
includes file hashes, complete caller chains for the largest sites, grouped
self sizes and exact frozen code excerpts.

| Observed allocation origin after collection | Sampled bytes, decimal MB |
| --- | ---: |
| All sampled self sizes | 355.632 |
| CadWorkspace render ancestry | 250.549 |
| Composition ancestry | 40.721 |
| Shared scene.update ancestry | 37.234 |
| assemblyParts node spread, grouped exact self site | 63.454 |
| Copy-reference object creation, grouped exact self site | 40.973 |
| Composition occurrence-map insertion, one exact caller site | 24.244 |

Ancestry buckets may overlap and must not be summed with their descendant self
sites. The largest app site is `index-OdfGeLCL.js:260:2124`, corresponding
structurally to CadWorkspace's `assemblyParts` node spread plus leaf IDs.
`index-OdfGeLCL.js:259:58628` creates normalized copy-reference objects, used
by the tree-reference-map memo at `260:22205`; additional large native `Map.set`
and `Set.add` sites are attributed by their recorded callers. These locations
identify **allocation origins, not retaining paths**. They do not prove which
root keeps any historical generation alive. The sampler also does not account
for all external or backing storage.

Main JS usage before/after two collections is 480.499 / 361.513 MB; backing
storage is 419.920 / 420.016 MB. After collection, displayed CPU accounts for
333.850 MB, leaving an 86.166 MB backing gap to attribute. The sampled total
changes from 354.639 to 355.632 MB. Main-thread quiescence is explicitly
unverified and a replacement reservation remains after diagnostic worker
termination. This does not establish a permanent leak or a GC-based fix.
The profiles focus the next retaining-path or bounded lifetime counterfactual
on workspace maps/derived node records and composed occurrence maps, alongside
the separate backing-store gap; batching alone has not been proven sufficient.

The scratch harness differs from `measure.mjs` only in four import destinations;
an adapter writes the two raw sampling responses from Node after grading. The
summary preserves the import-only diff and helper hashes. Shipped runtime and
harness files were unchanged. Navigation began September 11 at
00:12:12.285 UTC and private-browser cleanup ended 00:13:14.822 UTC. Current
source/client, locked dependencies, actual served entry and all four worker
assets match before/after. All L0/L1 entries were warm; no cache writes, HTTP
errors or page errors occurred. Viewers 3262 and 3267 remain running.

## Current forced-all-L1 stress still exceeds 2 GiB

The [current forced-L1 stress](results/hand-canonical-l1-settled-tree-20260910.json.gz)
on `2709968dc` **fails** the unchanged 2 GiB guard. At the last pre-diagnostic
gate snapshot, 654 CIDs are L1 and 212 remain L0. All 866 components / 3,259
occurrences remain present. The later 659 LOD events include diagnostic-period
activity and are not the gate count. Largest sampled renderer RSS reaches
2,052.109 MiB; no crash, page error, HTTP failure, cache write, denied level or
modeled memory limitation occurs. The 180-second deadline is not reached.

First geometry is on screen at 620 ms. Initial complete publication is stamped
13.757 seconds, its harness ramp is observed at 13.870 seconds, and the launcher
logs all 866 at 14.304 seconds; those clocks are intentionally distinct.
Navigation starts September 11 at 00:04:57.476 UTC and private-browser cleanup
ends 00:06:27.957 UTC. The exact guard-trigger timestamp is not retained
separately. Entry plus all four worker bytes match before and after the run;
source/client/locked dependencies are unchanged at the fingerprints below.
All L0/L1 cache entries were warm. Uncontrolled host work and user activity
remain possible, so there is no isolated latency or same-cache speedup claim.
The latest 128 retained worker requests are all cached, with 0.4 ms median
worker duration and 124.95 ms median start gap; that tail does not describe
every initial-load request.

| Owner or phase | Bytes (decimal MB) |
| --- | ---: |
| Gate modeled display CPU / GPU estimate | 403.127 / 390.453 |
| Gate worker reservation / replacement | 42.238 / 10.265 |
| Gate total modeled ownership | 846.083 |
| Diagnostic main JS before / after two collections | 713.636 / 523.558 |
| Diagnostic backing storage before / after | 530.973 / 531.300 |
| Post-diagnostic displayed CPU | 410.142 |

No BVHs exist. Collection removes 190.078 MB of JS while backing increases by
0.327 MB; this establishes disposable allocation alongside the live geometry.
After collection the largest renderer is still 1,780.688 MiB. These are
post-failure observations: the diagnostic stops one worker, main-thread
quiescence is **not verified**, and one replacement reservation remains. The
523.558 MB JS figure therefore does not establish a permanent leak. The
121.158 MB gap between backing storage and displayed CPU also needs owner
attribution. The all-L1 census's 446.683 MB display payload is only 36.541 MB
larger than this mixed-level display payload; payload size alone is insufficient
to explain the failed 2 GiB peak.

The next source target is reducing whole-publication work, rather than changing
the gate or forcing collection. Each accepted CID currently copies component
maps, composes the assembly, publishes React state, reconciles all 3,259 scene
records and runs the global visual/material passes. The composer already shares
unchanged part records, but that does not skip those full passes. A bounded set
of admitted ready replacements could compose and adopt once, retaining every
reservation and old complete view until the exact per-CID source/occurrence
set is adopted. Four items would remove up to three of four whole publications
in that counterfactual, not necessarily three quarters of bytes or elapsed time.
Cold loads must not hold an already-ready update indefinitely. This remains a
design proposal requiring lifecycle, selector, cancellation, admission and
bounded-fixture allocation evidence before implementation or another hand run.

## Settled-target and one-pass lookup checkpoint

The current `2709968dc` build passes the [nine-part default adaptive check](results/viewer-nine-adaptive-settled-tree-20260910.json.gz):
all 13 assertions, including actual resize/resample, requested quality, orbit,
selection clearing and recovery. Near view settles at five L3 / four L0;
orbit p95 is 9.2 ms and maximum 9.4 ms. Largest renderer RSS is 204.6 MiB.
Its fitted planetary screenshot was reviewed. The recorded run completed
21:40:55 UTC, before a later host suspension: all 70 sample timestamps and
cleanup precede the clock jump, with no suspended interval inside the report.

The [full-hand checkpoint](results/hand-default-adaptive-settled-tree-20260910.json.gz)
still **fails** its 30-second near-view convergence gate. It preserves all
866 components / 3,259 occurrences, stays below 2 GiB, and passes orbit,
unzoom, selection clearing and final quality recovery. A default-view result
does not change the earlier failed forced-all-L1 stress result.

| Observation | Current checkpoint |
| --- | --- |
| First geometry / observed initial complete | 791 ms / 13.962 seconds |
| Initial stable, requested quality satisfied | 16.525 seconds; 864 L0 / 2 L1 |
| Orbit frame intervals | p95 25.0 ms, maximum 26.5 ms; strict p95 <33 ms passes |
| Near phase at its deadline | 827 L0 / 4 L2 / 35 L3; 63 pending quality targets |
| Near visibility | 265 visible / 601 excluded CIDs; 457 visible / 2,802 excluded occurrences |
| Returned stable, requested quality satisfied | 65.385 seconds; 828 L0 / 11 L1 / 27 L2 |
| Final stable, requested quality satisfied | 78.342 seconds; same levels, no unmet targets |
| Largest renderer peak | 1,613.516 MiB; GPU process separately 349.641 MiB |
| Final adoption ownership | 86 requested / 86 adopted / zero rejected or pending |

Near refinement has no failed levels, denied attempts, pressure limitation or
camera resampling loop. At its final sample one adoption is pending; the
harness records the soft timeout and continues recovery. All seven workers
terminate, no reservation/upload remains, and all 36 HTTP errors are expected
cache misses. Cache writes total 93,856,004 bytes. The [post-grade screenshot](../../../models/tmp/performance-hand-20260910/hand-default-adaptive-settled-tree.png)
shows the fitted, coherent whole forearm/hand, populated tree and clear
selection, with no error dialog. Collections used for failure diagnostics occur
only after grading; their numbers cannot turn this failure into a pass.

The [numeric attribution summary](results/hand-default-adaptive-settled-tree-summary-20260910.json)
shows a different workload from the earlier mostly cached CPU profile. In the
29.777-second sampled near interval, 35 worker requests complete: two cached
requests take 0.55 ms median, while 33 uncached requests take 518.7 ms median
and 22.790 seconds total. The largest, CID `056f821159cb927e`, takes 6.348
seconds. These worker intervals include worker-owned SURF fetch/body,
parsing, tessellation, mesh construction and encoding; they are not mesher CPU
alone. Window Resource Timing does not capture that worker-owned fetch.
The 33 cache-miss responses take 1.1 ms median. Distinct sampled main-scene
updates take 29.8 ms median, adoption waits 110.25 ms, and publication gaps
690.2 ms. These overlapping intervals are not additive CPU measurements.
No performance improvement is inferred from comparing their medians with
the different, frozen `8640d6902` workload below. A bounded uncached-component
phase diagnostic can now distinguish fetch, parse, tessellation/build/encode
and remaining adoption cost before choosing another change or hand run.

Both current reports identify unchanged source/client fingerprints
`151539c77b7ac7b628354072c102ae1e5497550118f7cecf5b73797e32e88aa6` /
`ded016dcd5cf2b6fa5ee26755b055a7d8f22b7c1592d978e9c48e7a733da9124`.
Actual served entry and all four workers match the current dist; Three
0.185.1, BVH 0.9.14 and React 18.3.1 match locks. The hand navigation starts
23:59:12.349 UTC on September 10, grading ends 00:00:30.771 UTC on September
11, and private-browser cleanup finishes 00:00:32.540 UTC. All L0/L1 entries
were warm; higher levels were only partly warm from previous studies and the
user's frozen play viewer. Unrelated host compute was observed and user play
could continue, so this is functional acceptance with latency observations,
not an isolated or matched speedup study. No STEP was reparsed or cache
cleared. A [sandbox preflight failure](results/hand-default-adaptive-settled-tree-sandbox-preflight-failed-20260910.json)
is preserved separately: Node's localhost connection returned EPERM before
browser launch. The successful permission-enabled invocation is the graded
run. User viewer 3262 and benchmark viewer 3267 remain running.

## CPU profile: repeated assembly lookups dominate publication work

The [frozen play-viewer diagnostic](results/play-hand-cpu-8640d6902-20260910.json.gz)
captured an 8.157-second page interval at 800% zoom after initial complete
866-component / 3,259-occurrence display. The [CDP CPU profile](results/play-hand-cpu-8640d6902-20260910.cpuprofile.gz)
brackets that interval with 8.360 seconds including protocol overhead. The
[compact profile/stack summary](results/play-hand-cpu-8640d6902-20260910-summary.json)
retains self/inclusive times, exact frozen bundle locations and excerpts.
This is a diagnostic, not isolated performance acceptance: the user could be
using the same server and other functional work could overlap.

| Captured work | Observation |
| --- | ---: |
| DFS node lookup `_l` self time | 2,887.5 ms, 34.5% of profile duration |
| Parent selectable-node memo inclusive time | 3,583.9 ms |
| Garbage collection self time | 189.6 ms |
| Idle samples | 26.0 ms |
| Main-scene updates | 37; median 33.2 ms, maximum 40.1 ms |
| Distinct sampled adoption completions | 25; wait median 149.3 ms, maximum 170.1 ms |
| All adoption completions / rejections | 37 / 0 |
| Publication gaps | 36; median 220.1 ms |
| Cached worker requests | 37/37; median 0.5 ms |

The largest self-time frame is frozen `index-Dq-FAf-c.js:257:61527`; its body
walks the tree depth-first to find one normalized ID. Its parent at
`index-Dq-FAf-c.js:260:2079` maps every requested ID through that lookup before
adding descendant leaf IDs. The current source's corresponding `assemblyParts`
memo has the same structure; this source correspondence is an inference from
the frozen code, not a rebuilt source map. React inclusive frames contain that
work and must not be added to its self/inclusive time as independent costs.

Thirty-seven cache requests started and ended within the page interval, all
HTTP200. Resource Timing measured median duration51.7 ms, request-to-first-byte
1.2 ms and first-to-last-byte49.8 ms. These are browser phases, not wire-only or
server CPU measurements. A chronological join by CID and nearest preceding
cache response matches all37 worker requests: median response-end to worker
postMessage2.2 ms, and worker reply to next cache-request start165.0 ms. The join
is inferred, not a shared request ID. It localizes most serial delay to the
post-worker app/React/adoption interval; those nested intervals and their
medians are not independent additive CPU costs.

Served entry and all worker bytes matched the explicit frozen
`play-viewer-dist-8640d6902` snapshot at start/end. The successful run was
21:32:44.406–21:33:08.936 UTC; profiling occurred within
21:33:00.067–21:33:08.434 UTC. No page/console errors, allocation sampling or
forced collections occurred. The private browser closed; user viewer3262 and
benchmark viewer3267 stayed running. The 800% close-up was visually coherent.
Two earlier preflights are preserved as failed: the harness checked literal
`800` while the UI exposes `800%`; neither started a CPU profile. The successful
attempt uses the normal zoom field and parses its formatted value. Existing
L0/L1 and partially warmed higher-level caches, changed camera orientation and
concurrent user activity prevent a matched comparison to earlier hand timings.

The bounded fix replaces per-ID DFS in `assemblyParts` with one call-local
traversal. It preserves query normalization, requested order and duplicates,
missing/root behavior, first DFS duplicate-ID match and existing leaf-ID
shaping. There is no persistent identity cache. Tests include a2,048-node exact
visit bound, a10,000-node deep tree, mutable-tree replacement and lookup parity.
All17 focused assembly tests pass. The [actual saved-hand-tree Node counterfactual](results/viewer-assembly-lookup-hand-micro-20260910.json)
uses the same3,259 IDs and exact result, with eight ABBA samples per path after
warmup: repeated DFS median96.06 ms (94.29–97.44), one pass0.978 ms
(0.768–1.452). Input parsing/proof checks are excluded; raw saved nodes lack
display enrichment, so this is not a browser speedup measurement.

Memo invalidation is not safely solved by ignoring geometry changes. The
composer preserves tree nodes only when their bounds/transform/color metadata
stays equal; changed children also change ancestor identity. Read-only decoding
of cached L0/L1 pairs for the first five distinct profiled CIDs found different
bounds in every pair. Those actual bounds changes propagate into `assemblyRoot`
and selectable-ID memo dependencies. The fix makes recomputation linear while
retaining the correct current bounds and topology; the five-pair evidence is
included in the profile summary and does not claim to enumerate every React
dependency.

## Publication gaps: transport counterfactual and next-run timing

The 218.4 ms publication-gap median cannot be attributed to meshing from the
existing report. `loadSurfComponentInWorker` first awaits the window's HTTP
cache provider, which uses `fetch(..., {cache: "no-store"})` and `arrayBuffer()`.
Only afterward does dispatch call `worker.postMessage`, where the existing
worker probe starts its clock. That clock excludes cache HTTP/body delivery,
dispatch waiting, payload cache bookkeeping, composition and all later scene
work. The scheduler's 200 ms camera debounce is not a per-rung pause: its
settled drain calls `evaluate()` directly after each asynchronous apply, and
the sampled near phase has no pending evaluation timer. The report predates
the new actual-adoption acknowledgment, so its LOD event is a logical state
publication rather than proof that the scene has adopted that payload.

A [bounded HTTP counterfactual](results/viewer-http-nagle-ab-20260910.json.gz)
did **not** reproduce a delayed-ACK/Nagle-sized stall. It used the actual
`CadHTTPServer`, request handler and `Response` header/body writer, with
preloaded exact cached TESS bytes to isolate transport from store reads. Two
independent ephemeral servers differed only in the handler's NODELAY setting;
both used the same fixed Date value so headers could be compared. Four fresh
Chromium contexts ran default/NODELAY/NODELAY/default, each with 12 serial and
12 concurrency-six fetches per payload after an unmeasured warmup.

| Payload | Serial median, default / NODELAY | Concurrency-six request median, default / NODELAY |
| --- | ---: | ---: |
| 1 KiB synthetic opaque control | 0.60 / 0.65 ms | 1.35 / 1.30 ms |
| 32,832-byte real TESS | 0.60 / 0.60 ms | 1.05 / 1.20 ms |
| 407,652-byte real TESS | 1.10 / 1.00 ms | 3.50 / 3.95 ms |
| 2,233,568-byte real TESS | 3.35 / 3.30 ms | 14.75 / 16.95 ms |

Each cell pools 24 requests across its two passes. Fetch timing ends after
`arrayBuffer()`; SHA-256 validation runs outside the timed cell. All source/body
hashes and browser-normalized response headers match. Loaded module paths and
unchanged source hashes identify this checkout, and imports remained kernel
free. The isolated window was 21:22:26.794–21:22:28.625 UTC; both owned servers
and the private browser closed with server exit zero. The original outcome
`failed-proof` remains: its socket assertion expected literal 1, while Darwin
returned 4 for enabled NODELAY and 0 for disabled. A post-grade assessment
records the correct nonzero/zero distinction without replacing the samples or
original outcome. This controlled result gives no reason to change production
socket settings; it excludes real store I/O and main-thread rendering load.

The adaptive harness now enlarges the native window Resource Timing buffer
to a bounded 8,192 entries and collects at most 4,096 matching same-origin
cache/SURF entries after grading, with a grade-time cutoff and explicit overflow.
It stores bounded route/key identifiers plus numeric phases/status/byte sizes,
without wrapping production fetch or copying response bodies. Three focused
tests cover route filtering, preserved zeros/unsupported fields, duplicates,
cutoff and truncation; eight existing adaptive-helper tests still pass.
[Resource Timing](https://www.w3.org/TR/resource-timing/) records requests on
the initiating global's timeline, so worker-owned SURF fetches are explicitly
outside this window-only capture. HTTP methods, server CPU, JS body
materialization and GPU completion are not inferred. Comparing cache response
completion with worker start, adoption wait and the next request can narrow the
remaining gap in the next authorized checkpoint; it cannot reconstruct missing
network timing for historical runs.

## Visibility-aware adaptive checkpoint: recovery passes, near settling fails

The [recovery-aware hand checkpoint](results/hand-default-adaptive-visibility-20260910.json.gz)
is **failed overall**: close-up refinement remained busy after its 30-second
phase limit. All 866 components / 3,259 occurrences stayed present, and the
browser stayed below the unchanged 2 GiB largest-renderer limit. Unlike the
first default study, this run continued after that soft timeout and verified
unzoom, stable returned detail, selection/clearing and final idle. Every required
assertion except `stableAllPhases` passed; `requestedDetailSatisfied` was also
false. This is neither an all-L1 pass nor complete adaptive acceptance.

| Observation | Result |
| --- | --- |
| First geometry / initial complete scene | 799 ms / 16.315 seconds |
| Initial stable idle | 18.861 seconds; 864 L0 / 2 L1 |
| Orbit frame intervals | p50 16.7 ms, p95 25.1 ms, max 25.9 ms; passes strict p95 <33 ms |
| Zoom-in frame intervals | p95 125.0 ms, max 125.1 ms; reported separately |
| Near phase after 30 seconds | 821 L0 / 6 L1 / 37 L2 / 2 L3; still refining |
| Near frustum sample | 269 visible / 597 excluded components; 461 visible / 2,798 excluded occurrences |
| Returned stable idle | 71.272 seconds; 832 L0 / 9 L1 / 25 L2 |
| Final stable idle | 83.986 seconds; same detail, no workers/reservations/uploads |
| Largest renderer peak | 1,651.875 MiB; GPU process separately 337.656 MiB |

The 100-step orbit took 8.691 seconds in this browser, with at least 50 ms
between requested steps. Its maximum-frame guard was the separate, explicit
250 ms limit. Four -250 wheel deltas reached 800% zoom; the reversed sequence
returned to 100%. The returned view settled 9.757 seconds after its phase began.
All far-view occurrences became eligible again. The frustum sampler reported
zero fallback or dynamic exclusions. The final 115 LOD events comprised 87
refinements and 28 coarsenings, with no failed levels or memory limitation.

The [post-grade screenshot](../../../models/tmp/performance-hand-20260910/hand-default-adaptive-visibility.png)
was visually reviewed: a coherent fitted whole forearm/hand, populated assembly
tree, no selected-surface highlight or copy overlay, and an inspector prompting
for geometry selection. The focused palm tree row was separately confirmed
`aria-selected=false`. Seven workers were created and all seven terminated;
peak concurrency was four. Twenty-one writes totaled 49.13 MB. All 21 HTTP
failures were expected tessellation-cache misses; there were no page errors.

This fresh browser reused the canonical source-free document/store on port
3267, without parsing STEP. **All L0/L1 entries were warm**, including the
census-populated 866 L1 entries; L2/L3 were partially warm from prior adaptive
work. It is not a matched speedup comparison. Source/client fingerprints were
unchanged at
`c93e4e3fac3a77860071cbba98e235ef93e1a2b928f76e6849df39f341f15569` /
`5ad5281da8fccd8fb742f87f3813eed465790aa1cd962256af97321c1c78f069`.
Served entry and emitted SURF/BVH worker bytes matched; Three 0.185.1, BVH
0.9.14 and React 18.3.1 matched their locks. Navigation began 21:00:31.755 UTC,
grading occurred 21:01:55.834 UTC, and diagnostic cleanup ended 21:01:57.497 UTC.
The private browser closed; the root-owned viewer stayed running.

Near-phase samples show ongoing serial refinement, not an observed
cancellation/coarsening loop: camera count stayed at 108 and 78 further
refinements occurred, with zero coarsenings. The retained 64-event publication
tail has median gap 218.4 ms (99.5–1,232.8 ms). Seventy-eight worker requests
started and finished inside the same 29.810-second sampled window, 58 from
cached bytes; their median duration was 1.25 ms (0.3–1,029.6 ms), versus median
request-start gap 213.7 ms. Sampled main-scene updates took median 30.0 ms,
maximum 39.5 ms. These overlapping observations do not attribute composition,
later effects, uploads or frames independently, and the publication tail is
truncated. They support reducing per-publication work and avoidable ladder
steps before adding mesher concurrency.

The follow-up acknowledgment keeps replacement admission held through actual
CPU/Three scene adoption and accounting. It is a lifetime/backpressure fix,
not a measured throughput improvement or GPU-completion fence. Its focused
regressions cover exact payload/occurrences, progressive supersession, stale
context/revision, abort/unmount/failure and refused-apply parking. A separate
static-effect counterfactual and unchanged-hysteresis target-level study are
appropriate bounded next steps before another hand checkpoint. Post-grade GC
reported 252.0 MB JS and 339.9 MB backing, but quiescence was not formally
verified; it does not establish a retained-object leak or alter the grade.

## Clipping and material update: unchanged all-L1 stress failure

[Latest integrated run](results/hand-canonical-l1-clipping-locked-20260910.json.gz)
still fails the 180-second / 2 GiB largest-renderer limit. The last sampled
quality gate is **412 L1 / 454 L0**, with all 866 components / 3,259 occurrences
present and no failed levels. The **425 LOD events** were captured later, after
the gate stopped; they are not the accepted-detail count. The browser did not
crash. Its largest sampled renderer crossed the limit at 2,053.953 MiB, before
the time deadline. This is not a completed canonical-detail result.

The first complete-component publication was recorded at 15.432 seconds in the
raw publication ramp. The launcher's next component-progress poll observed
866/866 at 15.612 seconds; these are different observations, not interchangeable
clocks. First geometry was rendered at 783 ms. The existing canonical document
tree remained `9822de20097b9a213e64b6d4655ef8cbf9ed1c6eeb1ae2322605802b37cc1951`.
The fresh browser reused its existing store on port 3267, without a STEP parse.
Cache warmth was mixed: 34 writes / 28.41 MB had completed at the sampled gate,
and 36 / 32.11 MB by the final diagnostic. All 37 HTTP failures were expected
tessellation-cache 404 misses; there were no in-page errors.

Source fingerprint
`64624f20219129f30c7f30623b0d079dab7c03f03414ad86f7d967db83787e53`
and built-client fingerprint
`3f4b3d5d2aa6362f5079c4613139969e6737f4d24982cfca0b527ee21be1e5c9`
match at start/end. The index and six referenced assets matched served bytes,
including `index-BmZCCn_Z.js`. Chromium 148.0.7778.96 ran on Apple M1 Max with
Three 0.185.1 and BVH 0.9.14. Run timestamps are
20:01:39.692–20:03:14.455 UTC. No allocation sampling or forced collection took
place during the acceptance gate.

| Measurement | Before failure diagnostics collect | After two diagnostic collections |
| --- | ---: | ---: |
| Main page JS heap | 550.7 MB | 103.8 MB |
| Main page array backing | 449.9 MB | 417.7 MB |
| Browser-managed embedder heap | 9.0 MB | 5.9 MB |
| DOM nodes | 716 | 716 |
| Largest renderer RSS | Peak 2,054.0 MiB | 1,296.5 MiB |

Diagnostic collection stops the remaining worker, collects once, allows a
one-second settle, then collects again. This improves on the prior single-GC
sample, but `mainThreadQuiescenceVerified` is still false: it is not a formal
retained-heap census. Consequently the prior 333.8 MB single-GC value and current
103.8 MB value do not establish an equally sized retention improvement. The
current 446.9 MB JS reduction does show substantial disposable allocations at
the point of failure. Chromium's `performance.memory` includes different bytes
from CDP's JS heap and is not a fresh portable RSS limit; its 521.6 MB final
reading must not be substituted for the 103.8 MB CDP figure.

Displayed CPU resources were 318.6 MB, including 296.2 MB of surfaces and
22.4 MB of edges, with **zero BVH bytes**. There were still 156 surface instance
sets / 2,549 slots / 193,724 instance bytes. One worker remained before shutdown
(39.0 MB used JS, 86.0 MB committed JS heap, 2.59 MB backing); all nine created
workers were then terminated. Uploads peaked at one request / 4.99 MB and were
drained. These observations do not support a worker/upload or obsolete-instance
leak as the dominant missing owner. The sampled admission ledger estimated
685.5 MB owned and 656.7 MB available; its modeled buffer budget did not detect
the process RSS limit, and it claims no hard RSS cap.

At this checkpoint the next step was the bounded serial canonical-L1 footprint
census, followed by a separately graded default adaptive interaction study.
The later census completed all 866 L1 entries: 425.99 MiB unique CPU backing,
20.355 MiB padded edge textures, 16.887 million unique component triangles,
91.334 million occurrence-weighted triangles and zero vertex colors. This
payload alone fits 2 GiB, so the process overhead remains actionable.
Neither the smaller post-GC heap nor progress farther through the component list
justifies rerunning the same stress test or declaring all-L1 memory parity.

## Default adaptive study: complete far view, near settling incomplete

The [first default study](results/hand-default-adaptive-locked-20260910.json.gz)
is **failed overall**, because close-up refinement did not reach stable idle
within its explicit 30-second phase limit. It did not hit the 2 GiB RSS stop,
crash, lose occurrences, or report a failed/denied component level. Unzoom,
selection and final idle were not reached; they remain unverified on the hand.

All 866 components / 3,259 occurrences reached the complete-scene milestone
at 15.696 seconds; the first geometry observation was 699 ms. The ordinary
100% view reached verified stable idle at 18.332 seconds with 864 L0 / 2 L1,
no pending scheduler work, reservations, uploads or workers. This is a complete
adaptive far view, explicitly distinct from the failed forced all-L1 test.

| Observed stage | Result |
| --- | --- |
| Orbit frame intervals | p50 24.9 ms, p95 25.5 ms, max 34 ms |
| Orbit target/guard | Pass: p95 <33 ms and max <=250 ms |
| Zoom-in frame intervals | p50 25.3 ms, p95/max 133.4 ms |
| Near view after 30 seconds | 828 L0 / 16 L1 / 22 L2; scheduler still busy |
| Near refinement events | 60 total; all 866 components / 3,259 occurrences still present |
| Largest renderer peak before grading | 1,430.953 MiB (about 1.40 GiB) |

The input script requested 100 orbit steps with at least 50 ms between them;
browser input processing extended the actual orbit to 12.322 seconds. It is
not an exactly five-second wall-clock measurement. As in the medium lifecycle
method, the first two rAF intervals are excluded and the remaining raw intervals
are retained. Four -250 wheel deltas reached 800% zoom; those close-up transitions
are reported separately from the orbit cadence target. The last scene update
took 46.6 ms and still represented every occurrence. Its modeled admission
headroom was 867.0 MB, with no limitation; the near-stage timeout is ongoing
refinement, not evidence that a budget rejected this view.

This run started after the serial census populated **all 866 canonical L1
entries**. Existing L0 entries were also warm; L2/L3 were not prefilled. During
the observed run, 22 writes / 45.92 MB completed, and all 24 HTTP failures were
expected tessellation-cache misses. Ordinary pointer interaction created lazy
BVHs totaling 2.68 MB. All 36 created workers were terminated after the run.
No allocation sampling or forced GC occurred before grading. Failure diagnostics
afterward are explanatory only.

The source/client fingerprints remained
`a8374a8130a9908d95a654f6a0426402ee795610a5ccac4b2d1cb1d6ff6bd1aa` /
`02657d64e2164e0622c9f0a275b76a4666d5c258a3397daf81d869d81184af1b`.
Served entry and emitted SURF/BVH worker bytes matched, installed Three 0.185.1,
BVH 0.9.14 and React 18.3.1 matched their locks, and Chromium was 148.0.7778.96.
The navigation/grade window was 20:32:07.506–20:33:10.859 UTC; diagnostic cleanup
finished at 20:33:12.648 UTC. The browser was closed; the root-owned port 3267
server remained running.

The post-grade screenshot at
`models/tmp/performance-hand-20260910/hand-default-adaptive.png` shows a populated,
coherent 800% close-up and the 3,259-occurrence assembly tree. It is not a fitted
whole-hand visual proof. A future bounded recovery study should retain this
near-settling failure and continue unzoom/selection within the remaining total
deadline, rather than terminating all later checks at the soft phase timeout.
That would fill missing recovery coverage; it must not relabel this run a pass.

The harness now records a near/returned-view soft settle timeout and continues
unzoom/selection recovery within the same total deadline. The failed phase
still makes `stableAllPhases` false and the overall grade failed. Initial-load,
RSS, overall deadline and browser failures still abort immediately. Seven
focused helper tests and the entrypoint syntax check pass; this recovery
extension has not been rerun against the hand.

The saved near-phase telemetry supports ongoing refinement, rather than an
observed cancellation/coarsening loop. Between page times 33,274.2 and 62,842.8
ms, camera input stayed at 108 events, the scheduler stayed busy with no pending
evaluation timer, and 53 further refinements occurred with zero coarsenings.
Their publication gaps had median 321.1 ms (138.9–1,154.9 ms). The retained worker
request tail contains 53 requests both started and finished within that window:
31 used cached bytes, and worker duration had median 1.4 ms (0.3–995.3 ms), while
request start gaps had median 275.75 ms (115.8–1,275.2 ms). Sampled main-scene
updates had median 40.4 ms and maximum 46.6 ms. These nested observations do not
attribute all remaining time; composition, other React effects, worker startup,
upload and drawing are not individually timed by this run.

Source inspection identifies a concrete planning gap: `useViewportLod` samples
the nearest center across every occurrence without a frustum test, and the
orthographic error formula ignores distance. Thus components outside the
close-up can still qualify for refinement by projected size. The saved report
does not contain camera matrices or visible occurrence counts, so it cannot
prove which recorded requests were offscreen. A candidate should use conservative
full occurrence bounds, preserve repeated visible instances and fail open for
unknown/dynamic bounds. It must also preserve forced minimum detail and account
for pose changes under a stationary camera before applying exclusion there.
No LOD runtime change or repeat hand run follows from this source inference alone.

The subsequent conservative static-view sampler and surface aggregate culling
passed the [nine-part adaptive check](results/viewer-nine-adaptive-visibility-20260910.json.gz).
All 13 numeric checks passed, including actual viewport widening to 1,600×900
and restoration to 1,400×900: both produced an observed scheduler reevaluation
and a stable complete view. At close zoom, five components were visible and
four excluded from ordinary refinement; all nine occurrences remained present,
with five L3 / four L0. Returning to 100% made all nine eligible and settled at
six L0 / one L1 / two L2. Orbit p95/max were 8.7/9.2 ms; peak renderer RSS was
209.125 MiB. The returned-view screenshot is coherent and selection is cleared.
This is functional acceptance of the new policy on the small fixture, not an
all-hand result or a matched timing comparison with the earlier smoke.

This 20:53:38.455–20:54:11.970 UTC run used a fresh browser and the existing
nine-part canonical store, with L0–L3 cache entries warmed by earlier adaptive
smokes. Source/client hashes stayed
`b966f5fcb0a4c3e0cc4646b49d6cbf70874b67f725461ec44ef3a13752cab533` /
`5ad5281da8fccd8fb742f87f3813eed465790aa1cd962256af97321c1c78f069`;
served entry and emitted worker bytes and locked dependencies were verified.
The private browser and owned port 3273 viewer (PID 23712) were closed. The
report explicitly distinguishes its reused module-path proof from this actual
launcher log. Its all-true assertions remain valid after the later harness
correction that makes every required boolean affect the overall grade.

The preceding [nine-part harness smoke](results/viewer-nine-default-adaptive-smoke-v2-20260910.json.gz)
passed all 12 numeric checks, with orbit p95 9.0 ms, max 9.3 ms, peak 213.4 MiB,
real near refinement/coarsening, and visual confirmation of cleared selection.
Its 20:30:08.716–20:30:37.203 UTC window used the same frozen source/client.
The [initial smoke](results/viewer-nine-default-adaptive-smoke-20260910.json.gz)
is retained as invalid: Escape closed the tree while leaving selection active,
which its original assertion mistook for deselection. The corrected harness
toggles the same row and requires it to remain present with aria-selected=false.
The first launch also lacked local Playwright; it failed before opening a browser.
The successful runs explicitly used the existing `PLAYWRIGHT_FROM` installation.

## Default adaptive harness design and remaining recovery coverage

Use the same canonical STEP/store, a fresh browser, default viewer worker and
memory settings, LOD enabled, and no minimum-detail override. Keep the unchanged
2 GiB largest-renderer stop and a 180-second total deadline covering loading
and interaction. Record cache misses/writebacks, served main and worker asset
hashes, loaded Python module paths, and runtime/dependency identities. Monitor
RSS from Node throughout every phase; an unresponsive page cannot bypass the
limit. Do not collect garbage or sample allocations before grading the run.

The existing `measure.mjs --min-lod 0` completion gate is only an initial
complete-publication gate; its five-second settle is insufficient for this
study. A harness-only extension must preserve that gate as a milestone and then:

1. Verify all 866 components / 3,259 occurrences reached actual scene records,
   followed by a draw. With the camera stationary, wait for a two-second stable
   window: no scheduler work/evaluation, no pending reservations or uploads, no
   new LOD publications, and unchanged component/occurrence counts. Record an
   explicit memory limitation or failed levels separately; idle does not prove
   requested detail was admitted. Allow at most 60 seconds including initial
   loading for this phase; the total run deadline remains 180 seconds.
2. Orbit with 100 ordinary pointer steps, each waiting at least 50 ms, recording
   the actual duration, then zoom in using a
   recorded fixed wheel sequence. Capture frame intervals and draw progress
   during motion, then allow at most 30 seconds for the camera-driven policy
   to settle. Record level counts and per-component LOD events. At least one
   actual refinement or explicit denied request is needed to claim the
   adaptive path was exercised; otherwise report that subcheck as inconclusive.
   Preserve a soft settle timeout as a failure while continuing recovery under
   the unchanged total deadline.
3. Reverse the wheel sequence, refit using the ordinary control if necessary,
   and wait at most 30 seconds for idle. Record coarsening and worker/reservation
   release. Compare repeated far-view states, but do not require identical
   levels across the policy's documented hysteresis band.
4. Select one identified occurrence using ordinary UI, check its visible
   selection, clear it, and retain complete scene counts throughout. If a
   naturally requested detail level is denied, verify the previous complete
   view stays drawn and interactive; report the limitation rather than calling
   that detail complete. Do not hide components or inject a smaller budget to
   manufacture this outcome. Finish with a ten-second ordinary idle observation.

Grade complete scene, adaptive refinement outcome, interaction cadence and
peak RSS independently. Orbit must meet PLAN's strict p95 below 33 ms; the
additional explicit maximum-frame guard is 250 ms. Zoom cadence is reported
separately. Any timeout, allocation error, crash, missing occurrence
or RSS-limit violation fails its corresponding gate. A default adaptive pass
does not pass or replace the forced all-L1 stress test. Post-gate diagnostic
collections may explain a failure but cannot change its result. This source-free
hand has no authored animation clip; animation/repeated-edit lifecycle evidence
remains the separate bounded fixture study.

## Instance reuse and worker bundle: unsampled acceptance

[Final integrated run](results/hand-canonical-l1-instance-reuse-locked-20260910.json.gz)
still failed the unchanged 2 GiB renderer stop. Initial 866/866 display took
16.425 seconds, with geometry first on screen at 878 ms. The last complete
quality gate had 376 L1 / 490 L0, with no failed component levels; the later
390 asynchronous LOD events are not a completion count. The browser closed
normally after collecting failure diagnostics. The runtime remained frozen:
source `2784ca70dd7f3d0308fcecc9ec70bd684df4d36d8505ff51b2c0841a4d83a155`,
client `19bb23ade1e59a31558f4cb4e9719e16392258fc8f83a18da6e9be80ab0a8035`.
The recorded run window was 19:17:06.268–19:19:08.700 UTC.

| Measurement | Before diagnostic GC | After diagnostic GC |
| --- | ---: | ---: |
| Main page JS heap | 618.7 MB | 333.8 MB |
| Main page backing storage | 436.8 MB | 397.4 MB |
| Largest renderer RSS | Peak 2,163.9 MiB | 1,723.3 MiB |

There was no allocation sampling during this run, and no full heap snapshot
was retained. Scene display resources were 304.2 MB, with zero BVH bytes and
156 surface instance sets for 2,549 repeated occurrences. The DOM remained at
716 nodes. One tessellation worker was live before diagnostic shutdown; cache
uploads peaked at 12.93 MB. All recorded HTTP failures were expected
tessellation-cache 404 misses, with no in-page allocation error or crash.
Collection preceded a one-second diagnostic settle while queued React/LOD
publications continued. The later 333.8 MB reading can include new allocations
after collection; it is not a quiescent retained-heap census or proof of regression.
The increase versus the earlier sampled run needs targeted ownership analysis. The source-level reuse tests and small-model results do not establish
full-hand memory parity.

## Production worker picking check

[Actual served-worker probe](results/viewer-bvh-worker-picking-locked-20260910.json)
used the existing canonical 783,535-triangle / 463,830-vertex component, current
shared picking source and the production Vite worker. Its served 138,869 bytes
matched the local asset exactly: SHA-256
`501d2dcdd14e8d37fe41505b7676dadf93e108fbc3c2f46d90957262b07d2c19`.
Source/client/dependency fingerprints stayed unchanged. Chromium was
148.0.7778.96 with Three 0.185.1 / BVH 0.9.14; the isolated run occupied
19:31:22.029–19:31:23.159 UTC.

The first exact stock fallback took 52.5 ms. The BVH was ready 348.6 ms after
that ray began; the only observed main-thread long task in that window was the
52 ms fallback itself. A 5 ms heartbeat continued while the worker built the
tree. The previous locked Node inline build took 301.75 ms synchronously; its
elapsed time is not interchangeable with browser worker wall time. This probe
shows that construction moved off the main thread, while the first exact dense
pick still costs roughly 50 ms.

All six accelerated ray face-index multisets matched exact stock raycasting,
including coincident hits and misses. Accelerated rays took 0.1–0.9 ms versus
49.5–52.5 ms for the later stock reference rays. Display position/index identities
and hashes were unchanged. The worker copied 14,968,380 input bytes after a
132,038,076-byte admission estimate and installed an 11,321,244-byte BVH. A denied
request created no worker; disposal cancelled an active request, installed no
stale tree and released its reservation. Both created workers were terminated.

This is one isolated component CPU/picking check, without WebGL or whole-scene
picking, allocation sampling, or an end-to-end application interaction claim.
The worker build does not help untouched full-hand load memory: the failed
hand run already had zero BVH bytes. The owned viewer on port 3273 was stopped
following this study; the parent's hand viewer was left running.

## Allocation-sampled lazy-BVH diagnostic

[Lazy-BVH diagnostic](results/hand-canonical-l1-lazy-bvh-locked-diagnostic-20260910.json.gz)
used actual Three 0.185.1 / three-mesh-bvh 0.9.14 and Chromium 148.0.7778.96.
Served assets matched the frozen client
`4bce2ddde85aaa934ccacccd86afee72d1b8c4a7d6589b2fc939ecd5ea6c5fbd`.
Coordinated Python-only fixes changed the aggregate source fingerprint during
the run; the JavaScript source, built client and installed dependencies did not
change. Allocation sampling makes elapsed values diagnostic, not ordinary
performance comparisons. It used the existing canonical document and populated
tessellation cache, with a fresh browser profile and no STEP parse.

Initial display finished in 18.852 seconds. The unchanged 2 GiB renderer stop
failed near 103 seconds, with 338 L1 / 528 L0 at the last complete gate sample.
All 866 components / 3,259 occurrences remained displayed. Lazy acceleration
worked: scene BVH bytes were zero. Display arrays and edge resources accounted
for 285.2 MB, excluding GPU duplication; 9,859,877 unique triangles were present.

| Measurement | Before collection | After collection |
| --- | ---: | ---: |
| Main page JS heap | 824.2 MB | 92.9 MB |
| Main page backing storage | 428.2 MB | 369.7 MB |
| Largest renderer RSS | Peak 2,073.1 MiB | 1,251.6 MiB |
| Retained sampled allocations | 89.3 MB | 89.0 MB |

The large JS reduction, with nearly unchanged retained samples, supports
temporary allocation churn rather than an additional 280 MB retained JS owner.
The current DOM stayed at 716 nodes. Cache uploads peaked at 5.6 MB and finished;
one worker remained before diagnostic shutdown. These do not explain the peak.
The largest retained sites are shared scene materials, Three object/matrix
state and instance setup. Source inspection found that every source/LOD update
dissolved all surface instance sets before the existing compatibility reconciler
could reuse them, and allocated a new transform matrix per occurrence.

[Locked first-pick study](results/viewer-lazy-bvh-first-pick-locked-20260910.json)
used the existing 783,535-triangle component and six fixed rays, without browser
rendering or tessellation. Exact hit/face multisets matched; coincident-hit order
can differ. Cold-ray median was 45.88 ms, warmed stock median 44.56 ms, and
accelerated median 0.087 ms. Building its 11.32 MB indirect BVH still took
301.75 ms on the main thread. Deferral removes eager load cost but does not
resolve that eventual interaction stall.

The subsequent source patch preserves unchanged instance sets through LOD
reconciliation and composes placements into the mesh's existing matrix. A
single `scene.syncSurfaceInstances()` boundary now completes the viewer's
direct pose, animation, selection, material and clipping passes too. These
passes previously changed picking proxies without consistently updating shared
draws. Compatibility includes reflection intensity; distinct emissive channels
use their ordinary material rather than acquiring an instance-colour tint.
The 100 focused tests passed after the final source edit, including LOD
replacement/last-owner disposal, ordering, selected/hidden/deformed inactive
slots, direct animation/pose, mirrors, clip-only changes, reflections and
emission. This is correctness and allocation-identity evidence; a new bounded
hand run is still required to establish the resulting RSS headroom.

## Original failure

The original full-hand forced-L1 run failed at its 2 GiB renderer bound. Its
866 components finished initial display, but only five had reached L1 when the
bound stopped the run. The roughly 933 MB `performance.memory` reading is not
the same quantity as its 321 MB owned-resource ledger. The original failure
did not collect garbage or query page/worker heap usage afterward.

## Source-free heavy-eight subset

The subset contains the eight largest unique SURF components, each once, with
the original first occurrence's placement, name and color. It was exported as
an actual 58,298,201-byte STEP and canonical-compiled from its own bytes; it does
not use a fabricated document mapping. Its SHA-256 is
`8164276426559664f2f0732599dbf66880722cd545efcc60817b7f89094fbd00` and tree is
`d69a8e979b90f2beab8c3fe9bfe148cbea19e50c38de5b67697213be0e1c4f0c`.
The prepared store has no model/output indexes.

[Current diagnostic](results/hand-heavy8-current-memory-diagnostic-20260910.json)
verified the imported Python modules under this worktree's
`packages/cadgen/src`, then checked the served index and its six referenced
assets byte for byte against the built client before starting Chromium.
The client fingerprint remained `bdb112288e470382e5a5c1cb4e96ba7bd05ff186061997523524ae0f361fb1cc`.

With a 60-second load limit and 1.5 GiB renderer bound, all eight components
reached canonical L1. There were ten cold tessellation requests: eight initial
loads and two coarse-to-canonical refinements. At most two workers were live;
four were created and all four terminated. Both final refinements reused one
worker. The elapsed 17.728 seconds is diagnostic only: a targeted Python test
suite overlapped, and allocation sampling was enabled.

| Measurement | Before collection | After collection |
| --- | ---: | ---: |
| Main page JS heap | 24.9 MB | 11.5 MB |
| Main page array backing storage | 162.1 MB | 86.9 MB |
| Live workers | 0 | 0 |
| Largest renderer RSS | Peak 961.6 MiB | 625.7 MiB |

The final owned ledger was 115.8 MB, including the GPU estimate. Cache uploads
peaked at one pending request / 32.9 MB and were finished before collection.
This subset passes but does not explain the full assembly's additional memory.
It provides no evidence for changing worker policy or relaxing the L1 gate.

## Current full-hand failure with heap diagnostics

[Full-hand diagnostic](results/hand-canonical-l1-memory-diagnostic-20260910.json.gz)
used the existing canonical store on port 3267, a fresh browser profile, a
90-second deadline, and the unchanged 2 GiB renderer stop. Served client bytes
matched and the runtime fingerprint stayed stable. Tessellation entries were
mostly already cached: only three requests missed and wrote 706,672 bytes in
total. It remains a failed canonical-detail run, not a successful acceptance.
The last complete sample had 866 components / 3,259 occurrences displayed,
with only nine L1 and 857 L0. Initial display completed in 24.604 seconds;
the renderer crossed the stop around 31 seconds without crashing.

| Measurement | Before collection | After collection |
| --- | ---: | ---: |
| Main page JS heap | 677.7 MB | 296.1 MB |
| Main page array backing storage | 193.0 MB | 222.5 MB |
| Browser-managed embedder heap | 149.7 MB | 153.9 MB |
| Live worker JS heap | 15.5 MB | Workers stopped |
| Live worker committed heap | 43.3 MB | Workers stopped |
| Largest renderer RSS | Peak 2,056.0 MiB | 1,406.2 MiB |

The highest retained allocation sites include React elements in `StepFileSheet`,
row contexts/icons, occurrence composition and full assembly-tree enrichment.
The worker's backing storage was only 0.28 MB; cache uploads peaked at 0.43 MB.
Those worker/upload values do not explain this failure. The main-thread UI and
composition allocations are the supported targets. Embedder heap includes
browser-managed objects; it is not an exact DOM-only byte count.

The diagnostic collects asynchronously after the completion sample. Additional
LOD events can arrive before its worker stop, so its event count is not the
number of components that passed the last sampled L1 gate.

## Preserved invalid setup probe

[Invalid primary-checkout diagnostic](results/hand-heavy8-invalid-primary-diagnostic-20260910.json)
is excluded from current-runtime conclusions. Its launcher omitted `/src` from
`PYTHONPATH`, imported the primary checkout and served its older client. Its
worktree disk fingerprint did not prove the served runtime. The report now
names the actual imported modules and observed asset names. The harness's
new served-byte check prevents this mismatch from reaching the browser test.

## UI reuse acceptance and remaining gap

[UI reuse acceptance](results/hand-canonical-l1-ui-reuse-20260910.json.gz) checked
served client bytes against build `4861dc1bfe78257d79a681f71450611fae73303d4618a0401a362a2b3e4914ba`;
source fingerprint `1aff771bd06cbc38754fedd5e3fb378cbba8e8e4cca041a098285f0d8a5c54f3`
was unchanged. It used a fresh Chromium profile, the existing canonical store,
a 180-second deadline and the same 2 GiB stop. Cache warmth was mixed: initial
coarse entries were warm, while 286 cache writebacks totaling 275.0 MB completed
during refinement/diagnostic collection. This is not a matched cold timing.

All 866 components / 3,259 occurrences initially displayed in 16.841 seconds;
first geometry reached the screen at 838 ms. The last sampled gate reached
293 L1 / 573 L0, then exceeded the renderer bound around 137 seconds. It did
not crash, but it **did not pass canonical completion**. The 313 LOD event
count includes progress outside the last grade sample.

| Measurement | Before collection | After collection |
| --- | ---: | ---: |
| Main page JS heap | 482.5 MB | 282.5 MB |
| Main page array backing storage | 513.5 MB | 463.0 MB |
| Browser-managed embedder heap | 13.8 MB | 6.0 MB |
| DOM nodes | 716 | 716 |
| Live worker JS heap | 23.5 MB | Workers stopped |
| Live worker committed heap | 82.3 MB | Workers stopped |
| Largest renderer RSS | Peak 2,062.4 MiB | 1,637.6 MiB |

Virtualization removes the previous browser-managed tree retention, while the
assembly can refine much farther. Post-collection display CPU buffers are
268.1 MB and reported BVH roots are 90.1 MB. One worker and drained uploads do
not explain the remaining main-page memory. Source inspection found BVH
accounting omitted each indirect triangle permutation, up to another 36.6 MB
at the measured 9.16 million unique triangles. Accounting now includes these
buffers; this correction alone does not reduce memory or establish acceptance.

The viewer also now defers display BVHs until a ray reaches local component
bounds after deformation preparation. Exact stock picking handles that first
ray, and one admitted geometry build runs per idle callback. Initial display
and detail swaps alone no longer queue every component. Shared geometry,
mirrored/nonuniform transforms, near/far range, denied admission and queued
geometry release have focused coverage.

[First-pick diagnostic](results/viewer-lazy-bvh-first-pick-20260910.json) reads
the largest currently cached canonical component (783,535 triangles), without
STEP parsing, tessellation, browser rendering or other timed workloads. Across
six axis rays, first stock picks took 44.6–55.6 ms; three subsequent batches had
median 44.8 ms. After one 287.5 ms idle BVH build, median ray time was 0.075 ms
(maximum 0.98 ms). Its complete BVH owns 11.32 MB. Thus first-pick cost remains
material, and an idle build can still block for a dense component. This is a
single-component CPU measurement, not whole-assembly interaction acceptance.
The six rays have identical triangle-hit multisets before/after acceleration;
coincident-hit ordering differs. An initial stricter ordered-hit probe failed
and its log is preserved at `/private/tmp/viewer-first-pick.log`; the successful
probe records that qualification explicitly. Only 296 of 866 canonical entries
were cached during inventory, so their bytes do not establish the final full
L1 payload requirement. No full-hand run has yet validated the lazy-BVH change.

A separate [Node ownership probe](results/viewer-coarse-scene-ownership-20260910.json)
read all 866 existing L0 cache entries and built the actual 3,259-occurrence
reference composition and shared Three scene, without React, WebGL or BVHs.
Post-GC JavaScript heap was 12.0 MB after component payloads, 16.3 MB after
composition, and 69.8 MB after scene construction. Array backing grew from
126.3 MB to 148.4 MB during scene construction. These stages help isolate
shared scene overhead; they use a different V8 host and detail state from the
browser failure, so they do not subtract directly from browser heap totals.
The first temporary invocation used an incorrect `buildModel` call signature
and failed before scene construction; the corrected public API produced all
3,259 records. The probe changed no CAD, caches or shipped runtime.

Dependency qualification discovered after the probes: both dependency paths
used installed `three` 0.185.1 and `three-mesh-bvh` 0.8.0. The latter differs
from the package's declared 0.9.14 pin. Neither probe changed dependencies;
these timings and tests describe installed 0.8.0. Served-client byte checks
still prove which artifact ran, but final validation must address this
installation mismatch. The raw Node reports record the actual versions.
