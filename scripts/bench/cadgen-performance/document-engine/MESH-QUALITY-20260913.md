# Native and JavaScript mesh quality comparison

The bounded comparison uses six moderate native solids and one acceptance gate
for both producers. It measures numerical mesh quality, not rendered pixels or
a global Hausdorff bound. The [harness methodology](README.md#native-mesh-quality-comparison)
defines the sampling, topology checks and timing boundary.

The common distance ceiling is 0.15% of each exact native bounding diagonal;
the normal-angle ceiling is 0.35 radians. Internal tolerances are calibrated
independently through three fixed refinement rungs. An elapsed time cannot pick
the accepted quality. Every face and nondegenerate edge must be represented;
the gate also checks orientation, numerical closure, per-face area and volume.

The reserved serial run qualified plate, cylinder and torus.
JS needed finer internal settings for the plate and cylinder to meet the angular
ceiling. Sphere failed the angular ceiling in both producers. The JS trimmed
and curved solids retained structural failures after all three rungs. No speed
ratio is valid for those three unqualified cases.

| Fixture | Common distance ceiling (mm) | Native passing relative chord | JS passing chord | Quality match |
| --- | ---: | ---: | ---: | --- |
| Drilled, filleted plate | 0.141796 | 0.0015 | 0.000375 | Yes |
| Translated cylinder | 0.051962 | 0.0015 | 0.00075 | Yes |
| Sphere | 0.051962 | None in three rungs | None in three rungs | No |
| Torus | 0.081498 | 0.0015 | 0.0015 | Yes |
| Trimmed fillet/cut solid | 0.040389 | 0.0015 | None in three rungs | No |
| Curved boolean solid | 0.067949 | 0.0015 | None in three rungs | No |

The qualified native settings are chord 0.0015 and angle 0.35. The selected JS
`chord / loop / angle` settings are `0.000375 / 0.000125 / 0.175` for the plate,
`0.00075 / 0.00025 / 0.247487` for the cylinder, and
`0.0015 / 0.0005 / 0.35` for the torus.

## Qualified production timings

Each pair has one explicit primer followed by five measured samples, alternating
which producer runs first. Every measured packet passed the frozen common gate
and matched its calibrated bytes; the shared original native bytes remained
unchanged. These are the medians and observed sample ranges in milliseconds:

| Fixture | Native median (range) | JS median (range) | JS / native |
| --- | ---: | ---: | ---: |
| Plate | 9.367 (9.157–9.416) | 48.862 (48.120–80.830) | 5.217× |
| Cylinder | 2.175 (2.155–2.261) | 8.000 (7.774–9.367) | 3.678× |
| Torus | 32.366 (31.767–32.961) | 29.594 (28.233–30.537) | 0.914× |

Native is faster for the plate and cylinder; its torus median is 2.772 ms, or
approximately 9.4%, slower than JS. The plate's JS range includes one 80.830 ms
sample. These five-sample results from one reserved window do not establish a
whole-model or rendering speedup.

Both boundaries start from the same retained native shape and include a fresh
native copy. Native measures tessellation plus CGMESH extraction/encoding; JS
measures SURF extraction/encoding plus JS decode, tessellation and TESS encoding.
The independent copy-history proof, fixture construction, artifact IO, IPC and
quality oracle are excluded on both sides. Node process/module setup was
70.871 ms and Python CAD module import was 512.961 ms, separately recorded and
excluded from these warm production medians. Python interpreter launch is not
measured. The full six-case run, including calibration and repeated quality
verification, spent approximately 13.0 seconds in fixture work.

## Quality failures

The native sphere's initial packet has a sampled triangle-edge midpoint error of
0.0802374 mm against the 0.0519615 mm common ceiling. Finer rungs reduce the
distance error, but maximum triangle-to-analytic-normal angles remain
0.478792 and 0.477122 radians. The default maximum-angle triangle has area
0.00400334 mm²; it is not a zero-area transport remnant. These values were also
checked directly from the saved packed coordinates against the radius-10 sphere.
JS sphere pole triangles reach approximately π/2 radians. This finding is not
masked by accurate smooth vertex normals or by small aggregate volume error.

JS `trimmed_cut` initially has 96 coordinate-welded segments without exactly two
incident triangles, plus zero-area and reversed triangles. Finer settings close
those segments but retain reversed triangles. The curved case also retains
reversed triangles through the bounded search, with a new degenerate/closure
failure at the finest rung. The raw report records every individual gate failure.
Three failed refinement rungs do not prove that every possible parameter choice
must fail.

The initial plate/cylinder smoke exposed a harness error: two fillet cylinders
use left-handed native parametric frames. The analytic normal oracle now accounts
for that frame handedness and checks its result against native surface derivatives.
The discarded smoke is not quality or timing evidence.

## Evidence

The measured report is
`models/tmp/p7-quality-measured/20260913T191621.554288Z/report.json`, SHA-256
`1c7aeded5392c223cfc0c9e873e948eed7613995d6fd69a6db1cd4ee8a964f0f`.
It records all calibration failures, 15 qualified measured pairs, selected
parameters, copy correspondence, source/packet hashes, and stable code
fingerprints. Runtime: Python 3.13.13, OCP 7.9.3.1, NumPy 2.5.2, Node 26.7.0,
Three 0.185.1; repository head `762fde21745fe4248d040a50f104c7cc27b71601`.
The benchmark utilities were uncommitted and are identified by their exact hashes:
Python harness `ebfb5b9aa0d2383b3b25d8184f940ebe18a8e8a5c716659af9d2ba71230a6fe3`,
Node worker `6dbe2263a83e009695f117281810d52b864c3c63355c08a4a590ae5c9cd4d49c`.
The native mesher fingerprint is
`441ca0f9f942c5b0ea8fe70c246068629c96fd200600e779da25e07e4cba4a61`.
The report also fingerprints JS tessellation, evaluation, codecs, dependencies
and actual loaded Three modules. The native normal oracle passed its check
against exact parametric derivatives for every examined face.

Earlier correctness-only calibration is in
`models/tmp/p7-quality-calibration/20260913T191231.264987Z/report.json`;
none of its diagnostic times are used above. The independent numerical
point/triangle oracle passes 16 pure checks covering interiors, plane distance,
edges, vertices, reversal, translation and degenerate triangles.

This completes the bounded six-fixture comparison. The full P7 quality and
performance gate remains open: sphere has an unmatched quality target, two JS
fixtures retain structural failures, and native torus production regresses in
this measured boundary. No production mesher or render behavior was changed.

## Native quality correction follow-up

The subsequent native correction preserves the original acceptance gate. The
sphere's bad facets already exist in OCCT's double-precision Watson output;
copying and Float32 transport do not explain them. The producer now checks
facet direction against the mean native vertex normal during extraction. Only
failed meshes retry OCCT's Delabella algorithm at bounded finer settings.
This internal check is narrower than the independent numerical oracle above;
it does not establish a global surface-distance bound.

All six default native fixtures now pass that unchanged oracle. Only the sphere
retries: its 3,936 triangles have a maximum analytic normal error of 0.1010224
radians and sampled radial error of 0.0311385 mm. The other five fixtures keep
their original triangle counts and use one native pass.

Five alternating pairs measured the prior and corrected native producers, with
private copying, tessellation and extraction/packing included. The new internal
quality checks are included; the independent oracle and artifact I/O are excluded
on both sides. These warm medians are milliseconds:

| Fixture | Prior native | Corrected native |
| --- | ---: | ---: |
| Plate | 9.427 | 10.218 |
| Cylinder | 2.111 | 2.033 |
| Torus | 32.468 | 35.808 |
| Trimmed cut | 18.740 | 20.294 |
| Curved boolean | 13.794 | 15.788 |
| Sphere | 25.834, fails quality | 50.253, passes quality |

The correction costs about 8–14% on four already passing fixtures; the cylinder
difference is too small to claim an improvement. The sphere has no valid speed
ratio because the prior output fails the common quality gate. This is a quality
correction with a measured cost, not an assembly performance improvement.

The local report is `models/tmp/p7-sphere-investigation/retry-final.json`, SHA-256
`abfdda2fd9f5c99bd2c33561dc2a93277266017eb6153f9c50c5d5d66ac374e6`.
It identifies the measured new mesher by source SHA-256
`1256e4bd5cd0aae10fefad69946c42698e4bb017403a1e57f46ae08849a9758f`.
Subsequent dependency hardening authenticates held native math inputs and the
actual OCCT algorithm enum, and freezes producer proofs before source execution.
The final mesher source is
`9a88153ce33e5f924fad30fe80ed968df867c6eaa0e6c1fa1d98e439c8e40197`.
All six fixture packets are byte-identical to the quality-checked correction;
the equivalence report is
`models/tmp/p7-sphere-investigation/hardening-byte-equivalence.json`, SHA-256
`674db5496925f15b47fa3df92d4b37ca6be24b4cd1226d1e44b1deef9ff2ca44`.
The focused meshing, dependency, consumer and checkpoint gate passes 64 tests.
The timing table predates that hardening and is not a remeasurement of it.

The earlier native/JS comparison remains unchanged historical evidence. A new
quality-qualified native/JS series and broader assembly/browser checks remain
open; fixing the native sphere does not resolve the JS failures.
