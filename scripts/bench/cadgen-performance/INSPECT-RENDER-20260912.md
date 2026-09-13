# Inspect/Render boundary and CAD line review — 2026-09-12

This review uses the centrifugal impeller, planetary assembly,
static GLB fixture and Khronos animated Fox. It does not repeat the full hand
benchmark. Local Chromium runs use Metal, a 1280 × 900 viewport, and warm STEP
assets. Review images and recordings are ignored under
`models/tmp/viewer-transition-20260912/`.

## Changes verified

The Render transition previously exposed the newly allocated, empty WebGL
canvas. A Fox transition recording captured six completely black frames out
of 49 delivered screencast frames. With the fix, a repeated recording captured
zero black frames out of 50. The viewer covers the canvas with the destination
backdrop until geometry and studio lighting have drawn a frame. Light, dark
and customized backdrops were checked. Orbit and animation do not restart the
loading screen. No duplicate GPU scene or framebuffer capture is retained.

Render no longer receives STEP selector proxies or DXF bend guides. Animation
uses the model records independently of those selectors. Wheel pivot anchoring
uses model bounds in Render; Inspect retains exact surface anchoring. A second
leak existed in the pointer dispatcher: it raycast the model before checking
that picking was disabled. Hover and pointer-down now exit before that work,
and Render does not install demand-built CAD raycast accelerators.

| Browser check | Result |
| --- | --- |
| Impeller Render, after hover/zoom/orbit | BVH allocation reduced from 325,440 bytes to zero |
| Impeller and planetary Render | Zero edge, pick-proxy, face-ID and BVH bytes in CAD record accounting |
| All four fixtures | Inspect → Render → Inspect completed without a page error |
| Planetary and Fox | Play/pause works in Render; Animation tab retained |
| Static GLB | Studio tab only; no Animation tab |

These are interaction checks, not end-to-end build benchmarks or a process-RSS
measurement. Fox's native scene does not use CAD display records, so a zero in
that record accounting must not be interpreted as zero GLB memory.

## Fixed CAD line policy

Feature edges use 1 device pixel, seams 0.8 and tangent boundaries 0.65;
degenerate edges are hidden. Each type has a fixed light/dark color. The shared
coverage filter preserves those widths below one pixel instead of forcing an
opaque center and inflating fine lines. Both instanced and deformed edges use
the same filter. Appearance changes update materials/uniforms while retaining
geometry, segment textures and occurrence slots.

The viewer removes edge styling controls and exposes only a Grid switch for
the grid. Shaded versus Shaded with edges still controls edge visibility. The
snapshot schema rejects retired style keys. The per-model session version is
reset; global appearance remains in its cookie.

Impeller screenshots were reviewed in light and dark mode at DPR 1 and in light
mode at DPR 2. The packaged snapshot CLI produced an 800 × 600 Inspect image
with the same fixed edge/grid policy, without warnings (reported packet time
1.07 seconds, one operational run).

Validation: 1,081 shared JS tests, 619 viewer tests, 15 Python snapshot schema
tests, production bundle and generated-runtime freshness checks passed.

## Remaining optimization headroom

- `useCadAssets` can retain composed selectors while Render is active, and LOD
  replacement keeps them compatible for a quick return to Inspect. They are
  no longer installed in the Render scene. Releasing/deferring this retained
  state would trade memory for work when returning to Inspect.
- Direct GLB documents bypass the flattened-mesh worker/cache path. Static
  documents could reuse immutable normalized meshes; animated documents need
  isolated mutable scene/mixer ownership. Animated documents also retain a
  normalized rest mesh beside their native scene, and native GLB allocations
  need broader memory accounting before large animated-GLB stress testing.
- Mode switches recreate the WebGL runtime because Inspect uses logarithmic
  depth and Render uses ordinary depth for studio shadows. Geometry remains
  cached. Keeping both GPU scenes alive would increase memory rather than
  remove the underlying tradeoff.

The two paths are better isolated, but these findings do not establish that
either path has exhausted its optimization opportunities or reached FreeCAD
performance parity.
