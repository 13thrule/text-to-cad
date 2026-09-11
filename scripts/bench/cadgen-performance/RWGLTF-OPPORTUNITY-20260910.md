# Native C++ GLB packing opportunity — 10 September 2026

`RWGltf_CafWriter` is worth a further native-adapter experiment. This probe does
**not** justify changing the production mesher: the slow component has unresolved
quality flags, and the candidate has no edge-selection metadata.

The [raw report](results/rwgltf-opportunity-20260910.json) embeds both exact helpers,
their hashes, selected runtime hashes, immutable input addresses, and output
hashes. Two existing components were processed in an isolated CPU window. All
candidate CAD files are under `models/tmp/rwgltf-opportunity-20260910`; no store
object or index was written. The successful helper run took 14.11 seconds.

| Existing component | Current JS mesh + TESS encode | Private native pipeline, two samples | C++ GLB writing alone |
| --- | ---: | ---: | ---: |
| Planetary gear, `01f668a7dd6c9203`, 75 faces | 45.06 ms | 12.01–13.47 ms | 2.95–3.15 ms |
| Slow hand part, `056f821159cb927e`, 822 faces | 6,763.42 ms | 1,687.50–1,699.26 ms | 82.92–83.06 ms |

The native pipeline includes input read/hash verification, fresh private BREP
reconstruction/cleaning, canonical face/edge maps, serial OCCT meshing, a private
XCAF document with one named leaf per face, and GLB writing. The document stage
also captures three sample triangles per face for the later audit. Neither
column includes process/kernel startup, network, browser composition, GPU work,
edge/selector generation, or conversion of native GLB into the current renderer
layout. `readDecodeAndAudit` includes exact native GProps; it is not an isolated
decoder timing. JS has one cold-process sample per component, native two fresh
reconstructions in one process; these are bounded opportunity measurements.

Both received the current L3 numeric inputs: relative chord `1.5e-4` converted
using the current JS component scale, and angle `0.35` radians. Equal numeric
settings **are not matched-quality evidence**.

| Audit | Planetary gear native | Slow hand native |
| --- | ---: | ---: |
| Triangles, native / current JS | 536 / 892 | 173,405 / 558,888 |
| Missing/extra face labels | 0 | 0 |
| Sampled original index mismatches | 0 / 153 | 0 / 2,365 |
| Maximum sampled coordinate error | 0.000000772 mm | 0.000003721 mm |
| Non-unit normals | 0 | 0 |
| Normal-orientation flags | 0 | 1 |
| Float32-collapsed triangles | 0 | 27 |
| Absolute volume error against native geometry | 0.00710% | 0.74519% |

All expected face labels and per-face node/triangle counts were verified.
Names plus `faceOrd` node extras recover canonical identity without assuming
primitive order. Both repeated native GLBs were byte-identical; original BREP
files and content-addressed inputs remained unchanged. Coordinate audit converts
standard glTF metres/Y-up back to CAD millimetres/Z-up. Appearance, mirrored
placements, full sampled surface deviation, and selector parity were not tested.

The installed OCP package is `7.9.3.1.1`. The [OCCT writer API](https://raw.githubusercontent.com/Open-Cascade-SAS/OCCT/V7_9_3/src/RWGltf/RWGltf_CafWriter.hxx)
accepts precomputed triangulation and supports disabling face merging. Its
[implementation](https://raw.githubusercontent.com/Open-Cascade-SAS/OCCT/V7_9_3/src/RWGltf/RWGltf_CafWriter.cxx)
packs binary arrays in C++ and emits names and node extras. The [face iterator](https://raw.githubusercontent.com/Open-Cascade-SAS/OCCT/V7_9_3/src/RWMesh/RWMesh_FaceIterator.hxx)
applies winding and normal orientation; its [normal evaluation](https://raw.githubusercontent.com/Open-Cascade-SAS/OCCT/V7_9_3/src/RWMesh/RWMesh_FaceIterator.cxx)
falls back to a fixed normal when an exact normal is undefined.

Stock GLB does not carry the required face-boundary edge links. The
[edge iterator](https://raw.githubusercontent.com/Open-Cascade-SAS/OCCT/V7_9_3/src/RWMesh/RWMesh_EdgeIterator.cxx)
excludes edges inside faces and consumes `Polygon3D`, whereas our boundary
association needs `PolygonOnTriangulation` from this exact mesh. A future adapter
must preserve those node-index links, seam cases, edge classes, face colors and
selection revisions while correcting collapsed triangles. Reusing unrelated
SURF edge sampling would not establish coincidence with native boundaries.

The follow-up [identical array audit](results/rwgltf-array-audit-20260910.json.gz)
reads the existing outputs only and embeds its helper. On the slow component:

| Same audit | Current JS | Native GLB |
| --- | ---: | ---: |
| Omitted face ranges | 9 | 0 |
| Float32-collapsed triangles | 5,539 | 27 |
| Normal-orientation flags | 6,675 | 1 |
| Flags on noncollapsed triangles | 6,224 | 1 |
| Absolute signed-volume error | 1.29619% | 0.74519% |

The nine JS omissions are seven tiny spherical patches and two tiny planes
(individual exact areas 0.000390–0.000756 mm²). The native cone triangle flagged
at face 647 contributes only 0.00668 mm³ to the signed-volume sum; collapsed
native triangles contribute zero. Those terms cannot explain the approximately
30.20 mm³ native deficit. Its largest area deficits occur on NURBS patches,
including face 231 at −0.298 mm² out of 134.78 mm². This supported the single
accuracy-driven follow-up below, rather than treating the isolated normal flag
as the main cause. Per-face signed-volume terms are origin-dependent attribution
terms, not independent closed-part volumes.

Native is cleaner than current JS on these measured flags; neither result is a
complete accuracy or topology proof. The remaining requirements are exact edge
association, trim/surface deviation and seam/singularity coverage, and correction
of demonstrated collapses/orientation cases. No backend, cache identity,
dependency, or public API was changed.

## One tighter native comparison

The [tighter native report](results/rwgltf-opportunity-tight-20260910.json) and
[same array audit](results/rwgltf-array-audit-tight-20260910.json.gz) contain the
single authorized follow-up at quarter chord (0.004668535 mm) and half angle
(0.175 radians). It completed in 8.70 seconds including startup and audit, on
the same private BREP. All 822 named faces and 2,379 sampled triangle index
triples remained correct; source hashes match the earlier control. Tighter
repeat-byte determinism was not tested.

| Slow component | Original native | Tighter native | Previous current JS |
| --- | ---: | ---: | ---: |
| Native pipeline / JS mesh+encode | 1,687.50–1,699.26 ms | 6,744.79 ms | 6,763.42 ms |
| C++ writing within native pipeline | 82.92–83.06 ms | 232.22 ms | — |
| Triangles | 173,405 | 672,589 | 558,888 |
| Volume error | 0.74519% | 0.22198% | 1.29619% |
| Collapsed triangles | 27 | 47 | 5,539 |
| Normal flags | 1 | 7 | 6,675 |
| Missing face ranges | 0 | 0 | 9 |

The tighter native mesh improves the measured geometric approximation but loses
the earlier large latency advantage. Quality issues remain, so neither this
setting nor these timings select a production backend. There is no further
tolerance sweep.
