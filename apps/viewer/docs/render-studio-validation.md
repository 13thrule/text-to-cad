# Render studio validation — 2026-09-12

The planetary assembly exposed a shared studio problem: colors lost saturation,
light-colored surfaces collapsed toward gray, and the near-camera key made
adjacent assembly faces look flat. Moonwatch alone was not an adequate fixture.

## Shared correction

- Use **Khronos PBR Neutral** instead of AgX. Neutral targets color-faithful
  product visualization while compressing bright specular highlights. See
  [the Khronos rationale](https://www.khronos.org/news/press/khronos-pbr-neutral-tone-mapper-released-for-true-to-life-color-rendering-of-3d-products).
- Move the key above and to the side of the default isometric camera. This
  reveals cylinder curvature, gear depth, bores, and separation between parts.
- Calibrate direct key illumination and environment radiance together at 0 EV:
  direct illumination is 2.1 rather than 2.4; key-card radiance is 8 rather than
  12 at default size. Both sources contribute diffuse illumination.
- Keep a broad rear fill in the reflection direction of horizontal surfaces.
  A fill nearer the camera was rejected because polished plates and black iris
  blades reflected the dark room and lost detail. A dim neutral enclosure keeps
  metal surfaces readable outside the bright cards.

Light and Dark studios still differ only in backdrop defaults. Authored color,
roughness, metalness, clearcoat, and opacity are unchanged. The fallback remains
satin plastic; a color-only STEP does not acquire an invented metal finish.
Normal Inspect rendering is unchanged. Viewer and snapshot exports use the same
rig and tone mapper. The change adds no lights, shadow maps, geometry, or
per-frame passes, and does not alter the cache or tessellation policy.

## Comparison set

All six models were rendered with both default studios, Final quality, 0 EV,
default isometric camera, and 900×675 requested size (Final captures at 2×).
The existing local STEP documents were used; no source assemblies were rebuilt.

| Fixture | What it exercises | Final warm snapshot wall time, light / dark |
| --- | --- | --- |
| Planetary gear assembly, 2.2 MiB | Pastel part colors, flat faces, gears and bores | 2.06 / 1.86 s |
| Six-axis industrial robot, 1.7 MiB | 99 parts, cylinders, white/gray materials, colored accents | 1.90 / 2.19 s |
| Mechanical iris, 12 MiB | Dense layered parts, black blades, small fasteners | 2.30 / 2.26 s |
| Centrifugal impeller, 0.87 MiB | Unannotated material, thin walls, deep recesses | 1.88 / 1.77 s |
| Moonwatch, 112 MiB | Large detailed artifact, dial marks and bracelet | 5.46 / 5.25 s |
| Material sampler | Authored polished/brushed metal, plastic, clearcoat, copper | 1.77 / 1.83 s |

These are single-run local CLI wall times, including process/browser startup,
with warm geometry and mesh caches. They are validation timings, not a speedup
claim or browser first-load measurement. The first Moonwatch baseline needed
38.66 seconds to fill missing derivations; its subsequent baseline took 5.44 s.

The local comparison artifacts are under
`models/tmp/quality-refinement-20260911/review/render-balance-20260912/`:
`before/`, `neutral/`, `sidekey/`, `balanced/`, `reflector/`, and `final/` record
the inspected iterations. Each final PNG has stdout/stderr and a timings record;
`planetary-before-after.png` and `final/contact.png` provide visual comparisons.
They remain ignored local review assets, not repository additions.

Reproduce a studio capture with the source checkout's cadgen installation:

```bash
cadgen step snapshot path/to/model.step path/to/output.png \
  --render '{"studio":"dark"}' --width 900 --height 675 --json
```

Use `"light"` for the other studio and keep the camera, model, dimensions,
exposure, and quality fixed when comparing changes. Visually inspect colored
parts, white and black surfaces, and both metal spheres and flat metal plates;
a setting that works only for a curved metal watch is insufficient.

The real viewer was also checked on planetary and the robot arm. The new
lighting reached the interactive Render path without browser errors. Tests:
1,064 shared-runtime tests and 595 viewer tests passed, including scale/placement
invariance of key illumination. Production bundling and freshness checks passed.
The placement conformance script's obsolete Render-tab/Enabled selectors were
updated to the current Viewing mode menu; that separate fixture-specific script
was not part of this lighting validation.

## Fixture geometry issues discovered

These exist in the STEP geometry and are not lighting or normal-generation bugs.
They were not changed as part of studio calibration.

- **Impeller:** `models/examples/src/centrifugal_impeller.py` uses five straight
  polygon segments per blade wall. Final tessellation cannot turn those authored
  planes into a continuous curved face.
- **Robot:** `models/assemblies/src/six_axis_industrial_robot_arm/` gives shoulder
  lugs and the motor coincident radius-22 cylindrical faces over 12 mm of their
  length. Their different colors compete for depth and form a striped band.
  These also appear in the normal CAD snapshot.
- **Iris:** `models/assemblies/src/mechanical_iris_aperture/` uses 1.2 mm blades
  staggered by only 0.15 mm. The blades intersect one another and the actuator;
  the base and retaining ring also meet over a coincident annulus. This creates
  seam/sliver artifacts in both studios and normal CAD views.

Color conversion and authored material propagation were independently audited:
STEP colors round-trip through linear OCCT values, sRGB presentation colors,
and Three's linear working space; per-occurrence PBR survives composition and
instancing. The renderer preserves analytic per-face normals. No correction to
these paths was indicated by the review.
