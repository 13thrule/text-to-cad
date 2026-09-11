# Standard detail after the first preview

The viewer now treats coarse geometry as a loading state. Visible components
refine to at least the standard tolerance pair, including its angular accuracy,
without requiring camera movement. Cached standard meshes take precedence over
coarse meshes on reopening. Close inspection can request finer detail; offscreen
components wait until needed. Selected occurrences receive priority.

The store remains immutable objects plus atomic input indexes. No format/version
change, new persistent cache, or author-side utility import is needed. Mesh and
export tolerances are unchanged. If a probed cache body disappears or fails
validation, the loader releases its cache-hit reservation and admits a different
cached tier or cold work afresh. It never silently starts cold tessellation under
the smaller reservation. Retry attempts are bounded.

## Measured display behavior

Fresh Chromium contexts used Metal rendering at 1400 × 900 on an M1 Max with
64 GiB RAM. Geometry/document indexes were prepared before timing. Cold runs
had no surface or tessellation indexes; warm runs had the completed mesh cache.
These are individual local measurements, not medians or cross-machine guarantees.
The independent harness samples displayed geometry and scheduler state every
100 ms. Its milestones are observed scene adoption, not GPU completion fences.

| Fixture | Unique / occurrences | Cold: first geometry | Cold: complete preview | Cold: standard detail | Warm: standard detail |
| --- | ---: | ---: | ---: | ---: | ---: |
| Finishing sampler | 8 / 8 | 5.69 s | 5.69 s | 5.69 s | 0.32 s |
| Chronograph works | 69 / 73 | 3.38 s | 7.85 s | 9.42 s | 0.61 s |
| Saved Moonwatch, 117 MB | 256 / 301 | 3.99 s | 69.05 s | 85.81 s | 1.22–1.32 s |

The sampler starts directly at standard detail. The other two show coarse
geometry while refining. A separate chronograph run starting with only its
coarse meshes cached showed the full preview at 0.71 s and standard detail at
5.61 s. Standard refinement can overlap progressive loading.

| Warm reopening | Before this fix | After this fix |
| --- | --- | --- |
| Sampler | 0.32 s; five components subsequently downgraded to coarse | 0.32 s; all eight standard |
| Chronograph | 0.62 s; all 69 coarse | 0.61 s; all 69 standard |
| Moonwatch | 1.33 s; all 256 coarse | 1.22–1.32 s; all 256 standard |

The warm differences are too small and sparsely sampled to claim a latency
speedup. The important change is standard quality at comparable opening time.
Every measured warm load used cached meshes with no new tessellation writes.

Moonwatch now displays **2,014,063 triangles**, versus **1,055,217** at the
coarse tier. All **256 standard mesh object hashes match** the earlier
standard-quality headless snapshot cache. This restores the existing standard
geometry; it does not change the tessellator to generate a different result.

Cold Moonwatch peaked at approximately 1280.5 MiB of modeled owned resources,
then settled to 135.3 MiB. These are conservative CPU/GPU/worker estimates,
not browser RSS measurements or a hard allocator cap. Its final scheduler had
no unmet targets, outstanding reservations, or staged buffers. No uncaught
browser error occurred. Cold display remains substantial work: these results
do not establish instant cold rendering or a numeric FreeCAD parity ratio.

The original 34.16-second Moonwatch measurement described coarse mesh-cache
preparation in a different run. It is not an equal-quality before-time for the
85.81-second standard display. A new 93.24-second coarse baseline overlapped
validation/build work and is retained as diagnostic evidence only, excluded
from performance comparisons.

## Functional checks

The indicator distinguishes preview, refinement, standard detail, memory limits,
and errors. It follows the displayed file/revision and requires the current
package's complete component count. A settled early progressive batch cannot
stamp the whole model complete. Current scheduler targets override stale memory
notifications; standard quality and optional finer-detail failures have different
wording. A final real-browser chronograph retry confirmed the standard timestamp
at 5604.7 ms, agreeing with the independent 5613.1 ms observation.

A selected sampler face (`o1.1.f6`) survived real L1-to-L2 component swaps. The
reference remained identical, the inspector remained populated, and the scheduler
released all staging owners. Automated suites additionally cover atomic matching
of display triangles and selector topology, pressure, offscreen reveal, actual
selection priority, failure/cancellation, and cache loss before decode.

Validation: **548 viewer tests, 1024 cadgen-js tests, and 13 snapshot-cache/package
boundary tests passed**. Production bundles were regenerated and the freshness
check passed. Release version/pins remain 0.5.1. No generated CAD or large render
artifact is committed.

The initial cold traces found and drove fixes to premature UI timestamps and a
stale limitation label. Their independent scheduler timings remain useful;
the final UI regressions and follow-up browser checks verify the corrected UI.

## Reproduction

Use a private viewer and store. Prepare the saved STEP's geometry before timing,
then select whether the store has no display indexes, coarse meshes, or standard
meshes. Do not reset the user's store. Run one benchmark at a time without
concurrent builds or tests:

```bash
node scripts/bench/cadgen-performance/viewer_quality.mjs \
  --url http://127.0.0.1:<port>/ \
  --file STEP/moonwatch.step \
  --timeout 180000 \
  --output tmp/moonwatch-quality.json \
  --screenshot models/tmp/moonwatch-quality.png
```

The harness writes detailed local telemetry. The bounded committed
[evidence summary](results/viewer-quality-20260911.json) records fixtures,
quality proof, timings, resource estimates, and qualifications.
