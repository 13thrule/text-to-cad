# Native quality and one safety margin — moderate fixtures

A uniform native chord margin of **requested chord ÷ 2**, with angle unchanged,
meets the original chord target at every tested sample on all seven moderate/
small fixtures. Face/edge/selector coherence passes, and two fresh derivations
produce identical GLB, boundary-metadata and TESS bytes for every fixture.
The captured costs do **not** justify integrating a second canonical producer
now. Retain JS and prioritize publication/build overhead. The native profile
is a useful quality/identity prototype, not a continuous tolerance guarantee
or an established end-to-end performance improvement.

The [unadjusted comparison](results/rwgltf-common-quality-moderate-20260910.json.gz)
and [single-margin candidate](results/rwgltf-margin2-moderate-20260910.json.gz)
embed the helpers, exact input/output hashes, query coordinates, per-face
results and phase observations. Six small fixtures plus the 75-face planetary
gear were used. No hand component or assembly was read for this comparison,
remeshed or stress-tested. The earlier [seven-fixture adapter proof](RWGLTF-ADAPTER-PROTOTYPE-20260910.md)
remains a separate completed record.

## Quality method and results

Both meshes receive the same BREP/SURF and numeric L3 request: relative chord
`1.5e-4`, angle `0.35` radians. The candidate changes only the native meshing
chord to half that request; acceptance still uses the original chord.

For surface-to-mesh coverage, each exact face supplies a fixed shifted Halton
UV sample set, UV corners and exact edge endpoints/two irrational fractions.
The exact face classifier rejects samples outside trims. Each accepted XYZ
point is tested against **all triangles of that same face**, identically for
both meshes. Candidate queries are loaded from the saved unadjusted query set;
their hashes match. There are no missing faces or empty exact-query faces in
either implementation across this fixture set.

The reciprocal test samples triangle-side midpoints and centroids, using up to
257 triangles per face and a nominal 3,000-triangle budget per component. It
uses exact bounded-face distance directly, avoiding the UV-limited projection
artifact found in the earlier study. Facets differ, so reciprocal query points
are not identical between meshes. The point-to-triangle helper includes tests
for interior, edge, vertex, degenerate and extremely thin triangles.

An initial dyadic grid coincided with JS subdivision vertices on some analytic
surfaces, making its surface-to-mesh results unrepresentative. Those summaries
are preserved in the raw report; the table uses the shifted sample set.

Each error cell is **surface→mesh / mesh→bounded face**, in millimetres.

| Fixture | Requested chord mm | Angle rad | Current JS error | Native unadjusted error | Native half-chord error |
| --- | ---: | ---: | ---: | ---: | ---: |
| Box | 0.00343693 | 0.35 | 0 / 0 | 0 / 0 | 0 / 0 |
| Perforated plate | 0.01917009 | 0.35 | 0.00418868 / 0.01810976 | 0.00951636 / 0.00951809 | 0.00476442 / 0.00477420 |
| Sphere | 0.00335410 | 0.35 | 0.00219233 / 0.00229284 | 0.00224339 / 0.00312415 | 0.00113928 / 0.00126892 |
| Cone | 0.00300000 | 0.35 | 0.00006989 / 0.00087288 | 0.00218304 / 0.00227679 | 0.00110053 / 0.00115398 |
| Torus | 0.00360000 | 0.35 | 0.00212480 / 0.00277458 | 0.00329159 / 0.00354026 | 0.00145095 / 0.00179167 |
| Trimmed NURBS | 0.00281425 | 0.35 | 0.00159704 / 0.00254268 | 0.00247384 / **0.00387578** | 0.00124298 / 0.00177625 |
| Planetary gear | 0.00873374 | 0.35 | 0.00297427 / 0.00409537 | 0.00434749 / 0.00436405 | 0.00213586 / 0.00216655 |

Unadjusted native and current JS both stay below the requested chord at the
tested samples on six fixtures. The unadjusted trimmed-NURBS exceedance is the
concrete reason for the one uniform safety-margin experiment. With that margin,
both directions fall below the original target on all seven. Pointwise
dominance over JS is unnecessary when both satisfy the requested quality
target; cone and plate samples still illustrate different valid triangulations.
The angular input is recorded, but this study does not prove a continuous
angular-error bound, continuous chord bound or complete trim containment.

## Cost and deterministic identity

The JS observations come from `rows[].jsGeneration.stagesMs` in the unadjusted
report. Each is one fresh Node process running the current production mesher
and TESS encoder. **Mesh + encode** includes component-scale estimation inside
the tessellator; it excludes input reading/verification and SURF parsing
(another 0.52–1.40 ms in these samples), process/module startup, render/selector
construction and codec decoding. These were earlier functional preparation
runs: concurrent functional work was permitted, and absence of contention was
not established. They are not an isolated A/B against the native candidate.

The repeated half-chord derivations ran later in an isolated approximately
14.2-second window. Each fixture has two fresh native→JS-adapter process pairs;
the native child exits before the adapter child starts. The phase total,
`rows[].samples[].derivationStageSumMs`, includes native input verification,
private reconstruction, maps, meshing, sparse extraction, face-document construction,
C++ GLB writing, metadata encoding, JS reading/conversion/edge mapping, render
and selector construction, and TESS encode/decode. It also includes prototype
boundary/relation validation absent from the JS observation. It excludes process
startup, separate scale preparation, exact GProps and final audit/assertion/report work.
Raw reports include all these phases and native/adapter process-pair wall times.
Thus the columns below are **different measured boundaries**, not speedup ratios.

| Fixture | Current JS mesh + encode ms, one sample | Native half-chord mesh alone ms, two samples | Native half-chord adapter phase total ms, two samples |
| --- | ---: | ---: | ---: |
| Box | 7.30 | 0.65–0.68 | 5.69–5.79 |
| Perforated plate | 84.79 | 10.57–10.61 | 24.72–25.83 |
| Sphere | 171.18 | 748.55–775.89 | 845.53–865.52 |
| Cone | 33.16 | 25.61–30.40 | 43.87–48.13 |
| Torus | 277.40 | 467.22–472.06 | 554.48–564.41 |
| Trimmed NURBS | 136.34 | 132.16–134.06 | 181.18–189.83 |
| Planetary gear | 46.86 | 8.79–9.24 | 31.23–32.09 |

| Fixture | JS triangles | Native unadjusted triangles | Native half-chord triangles | Half-chord TESS KiB |
| --- | ---: | ---: | ---: | ---: |
| Box | 12 | 12 | 12 | 2.5 |
| Perforated plate | 3,096 | 1,160 | 1,636 | 94.2 |
| Sphere | 42,766 | 29,946 | 60,050 | 2,233.9 |
| Cone | 638 | 2,855 | 5,023 | 196.7 |
| Torus | 40,204 | 27,300 | 53,970 | 2,017.5 |
| Trimmed NURBS | 7,474 | 10,168 | 20,146 | 763.5 |
| Planetary gear | 892 | 536 | 640 | 66.1 |

Native child peaks range from 259.4 to 388.2 MiB, including kernel baseline;
JS adapter child peaks range from 74.8 to 110.7 MiB. Children run sequentially.
A resident kernel worker plus simultaneous Node decoder would need a combined
budget; these separate peaks do not measure that arrangement. The uniform
margin substantially raises triangle count, processing and payload size for
curved surfaces. The JS generation processes peaked at 71.0–151.2 MiB; their
different work boundary and process baseline also preclude a matched memory
comparison.

Plate and gear show potentially useful lower native phase costs. The same
uniform profile has higher observed phase costs for sphere, cone, torus and
trimmed NURBS. For sphere and torus, native meshing alone already exceeds the
captured JS mesh+encode cost, so extra adapter validation does not explain the
entire difference. These observations support retaining the prototype, but
not paying the integration cost on a general performance claim.

Missing measurements are a repeated isolated JS/native comparison at the same
output boundary, JS render/selector and decoder costs for these samples, and
either producer's admitted job-to-reader latency. Native process-pair wall
times including startup and audits were 0.740–1.667 seconds; the report has no
matching JS process-wall measurement. Those private-helper walls do not predict
a warm production pool. Provider scheduling, network, browser adoption/GPU and
a resident native-worker/Node memory budget remain unmeasured here.

Every repeated native result preserves all face/edge IDs, both seam sequences,
same-array edge proxies and face selectors, face colors and codec behavior.
GLB, sparse JSON and TESS hashes match between both fresh derivations. Positions
are finite and normals are finite/unit; no normal-orientation flags appear.
Two sphere pole triangles and one cone apex triangle remain exactly zero-area
after Float32 transport. They were retained and explicitly counted. A production
adapter must resolve those degenerate facets while preserving their topology
metadata; this experiment did not silently change triangles.

## Decision and deferred integration requirements

**Defer native producer implementation and prioritize the measured publication
and build overhead.** Finite-sample quality and deterministic topology transport
are established for this candidate; a useful general producer-to-reader cost
benefit is not. The plate/gear observations alone do not justify a second
canonical producer, while the curved fixtures show substantial cost and size
tradeoffs. No additional geometry experiments are needed for this decision.

If later workload evidence justifies revisiting native production, the bounded
integration must still cover one explicit uniform profile and deterministic
backend/algorithm identity across all readers. The requirements below are
preserved as design constraints, not an approved implementation step:

1. Finish the pure shared decoder/normalizer, including a narrowly tested rule
   for exact-zero-area facets, preserving face ranges, edge IDs and selector
   coherence. Add native located/mirrored-carrier cases and retain repeat-byte
   checks. Its version is part of the native tessellation identity.
2. Add one lazy, memory-admitted cadgen build-pool job over verified immutable
   BREP/SURF pins. It reconstructs private native state, emits the carrier,
   invokes the packaged adapter, validates the complete TESS, and atomically
   publishes one derived object/index result. Verify force, missing/corrupt
   objects, cancellation, concurrent derivation and source deletion; never
   mutate or persist triangulation on canonical BREP.
3. Route the same explicit native identity through viewer cache misses, Node
   mesh exports and snapshot providers. Render-first/selector-later requests
   must retain identical concrete arrays. The HTTP server stays kernel-free;
   failure cannot publish JS triangles under a native key.
4. Extend static docs asset preparation to include the supported native TESS
   closure and exact identities. Static readers only decode it. A native miss
   cannot silently invoke JS; incomplete assets must fail the build or require
   a separately declared backend decision.
5. Exercise the installed wheel and all reader doors on the moderate planetary
   assembly, including saved source-free access, before changing the default.
   Measure admitted producer-to-first-render latency and combined process/RAM
   cost. The existing adapter timings omit provider/job scheduling, network,
   browser adoption and GPU work.

The [full producer design](RWGLTF-ADAPTER-DESIGN-20260910.md) describes the same
ownership, cache and static-host constraints. No production implementation or
default change is part of these results.
