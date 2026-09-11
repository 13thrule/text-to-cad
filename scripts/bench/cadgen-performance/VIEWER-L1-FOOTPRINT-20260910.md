# Complete hand L1 geometry footprint — 2026-09-10

The [complete census](results/hand-l1-footprint-20260910.json.gz) verified all **866
unique components** of the canonical hand tree, using the production JS
tessellator at L1 (`chordTolerance=0.0015`, `angleTolerance=0.35`, mesher v2,
TESS v3). It read existing immutable SURF objects; it did not parse STEP, execute
author source, load the native CAD kernel, compose a scene, or create a WebGL
context. The report embeds the exact helpers and runtime fingerprints.

| Allocation | Bytes | MiB | Meaning |
| --- | ---: | ---: | --- |
| Surface position, normal and index views | 433,947,408 | 413.844 | Surface upload inputs |
| CAD-edge input arrays | 12,735,700 | 12.146 | CPU inputs used to build edge textures |
| Unique display backing buffers | 446,683,108 | 425.990 | Full CPU allocations, counted once per buffer |
| Padded segment textures, all drawable edge classes | 21,343,296 | 20.355 | Additional CPU texture data and potential GPU texture payload |
| Display backing plus those textures | 468,026,404 | 446.345 | Geometry-related CPU allocation measured here |
| Encoded canonical TESS cache | 691,701,520 | 659.658 | Serialized storage, not automatically resident display memory |

The display arrays produced by `buildMeshDataFromSurf` owned their allocations:
their full backing size equalled the sum of their views. The census nevertheless
measured backing and view sizes independently. Encoded TESS includes face/side
ordinals and polylines that need not remain in display buffers. Retaining a view
into encoded storage elsewhere can retain that whole allocation; this census
does not assume every browser path has the same ownership.

L1 contains **16,886,908 unique triangles** and **9,637,688 vertices**. Applying
the tree's 3,259 occurrences gives **91,333,931 occurrence-weighted triangles**
before culling; it does not multiply shared CPU geometry by that amount. All
866 component results contained **zero vertex-color bytes**. STEP part colors
remain material data rather than vertex-color buffers.

GPU upload inputs are distinct from physical GPU/driver memory. The surface
views above and edge texture payloads do not include instance arrays, driver
copies, framebuffers or other renderer allocations. Likewise, this CPU total
excludes JS records, materials, selectors, BVHs, worker scratch and transient
publication data. The measured geometry payload alone is below 2 GiB; that
neither proves the complete browser view fits nor establishes that the stress
target is intrinsically impossible.

The run began with **414 valid L1 hits** and derived/persisted **452 misses**
through the existing object/index HTTP cache routes. Every consumed SURF and
cache object was hash-verified, and each write was read back. **All 866 L1 entries
are now cached.** Later browser runs must state this changed cache condition;
they cannot be presented as repeats of earlier partially cached refinement.

One fresh Node process handled each component. The sampled aggregate of the
supervisor, server and current child peaked at **337.234 MiB**; the largest
child's OS-reported peak was **283.625 MiB**. No guard fired. Limits were a
512 MiB V8 heap, 1 GiB sampled aggregate RSS stop, 30 seconds per component and
600 seconds of work. The successful run took 240.5 seconds while functional
wheel validation could overlap; this duration is **not performance comparison
evidence**. The initial sandbox socket denial occurred before component work.
All owned processes stopped, and runtime fingerprints stayed unchanged.
