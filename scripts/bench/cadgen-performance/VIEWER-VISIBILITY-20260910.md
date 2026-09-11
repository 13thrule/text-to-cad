# Viewport visibility work — September 10, 2026

The [default hand run](results/hand-default-adaptive-locked-20260910.json.gz)
revealed a visibility gap in detail scheduling. At 800% zoom the camera stopped
moving, but refinement continued beyond the 30-second settling deadline. The
old sampler considered every occurrence center; orthographic projected error
does not depend on its distance. Consequently, a component could request more
detail while every occurrence was outside the viewport. The report did not
record camera matrices or visible-component counts, so it cannot identify which
individual completed requests were offscreen.

The new static-scene sampler tests complete transformed occurrence boxes and
retains the nearest eligible occurrence per component. It preserves finite
distances separately from visibility so memory pressure can coarsen offscreen
detail first. Ordinary visibility changes do not unload geometry. Unknown and
not-yet-adopted records remain eligible, as do scenes with any pose capability.
Resize and placement changes resample independently of saved camera preferences.
The forced canonical-detail benchmark floor still includes every component.
The [full-hand checkpoint](results/hand-default-adaptive-visibility-20260910.json.gz)
retains all 866 components / 3,259 occurrences and excludes 597 offscreen
components during close zoom. It passes the 2 GiB largest-renderer limit and
orbit cadence, but refinement remains busy after the 30-second near-view
deadline. Unzoom, selection/clear and final idle pass afterward. That failed
phase keeps adaptive acceptance open; the later scheduler and tree-lookup
changes require their own integrated browser run.

The [nine-part adaptive browser check](results/viewer-nine-adaptive-visibility-20260910.json.gz)
passes all 13 required checks. At close zoom, five visible components refine to
L3 while four components outside the viewport remain at L0; all nine occurrences
remain present. Returning the camera makes all nine components eligible again.
Selection, resize to 1400 × 900 and restoration to 1600 × 900 also pass.
First geometry appears at 314.8 ms and initial complete publication at 721.1 ms;
orbit cadence is p95 8.7 ms, with 209.1 MiB peak largest-renderer RSS. The saved
complete assembly frame was visually inspected. This uses adaptive LOD, so its
load timing is not a matched comparison with the earlier LOD-disabled medium
study. Exact served entry/worker bytes and installed dependencies were verified.

## Surface draw submission

Surface instance groups previously disabled Three's frustum culling. They now
use a sphere enclosing their transformed component boxes. Matrix and active-slot
changes invalidate it; unchanged transforms retain it. The sphere is padded by
`sqrt(3)` so Three's largest-column world-matrix scaling remains conservative
under an externally sheared parent. Screen-space edge draws retain their existing
policy. This changes neither instance slots nor picking or saved geometry.

The [bounded WebGL counterfactual](results/viewer-surface-culling-ab-20260910.json)
uses the actual shared instance builder, locked Three 0.185.1 and Apple M1 Max
Metal renderer. Its 48 clusters have four occurrences each and 4,800 triangles
per component: 921,600 occurrence triangles. Four clusters intersect the camera;
44 are offscreen. A directional shadow pass uses the same culling mechanism.
After six shader-warmup frames, eight interleaved frames toggle only culling.

| Per rendered frame, including shadow pass | Disabled | Enabled |
| --- | ---: | ---: |
| Draw calls | 97 | 9 |
| Submitted triangles | 1,843,202 | 153,602 |
| Framebuffer SHA-256 | Identical | Identical |

All eight frames have identical pixel bytes. Separate contribution checks prove
that the inside, boundary-crossing and sheared-parent groups produce visible
pixels. Occurrence IDs, display-array bytes and GPU resource counts remain
unchanged after warmup. The saved frame was visually inspected. All sets were
disposed and the owned browser/server closed; exact imported source and lockfile
hashes did not change. The raw report embeds its helpers and source manifest.

These are draw-count and pixel-equivalence results, not timings or a measured
full-hand speedup. Shared-runtime tests pass 1,008 cases, including four new
culling regressions for movement, affine transforms, boundary crossings and
slot reactivation. App integration and large-model acceptance are tracked in
[VALIDATION-20260910.md](VALIDATION-20260910.md).
