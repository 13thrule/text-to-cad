# Photographic Render — 2026-09-12

## Product contract

Render is a photography setup for the loaded document. CAD inspection retains
its separate display defaults. Global System/Light/Dark appearance remains in
the navbar; Render settings remain ephemeral per model in browser session
storage. They never enter the CAD object/index store or the model sidecar.

Render has its own renderer configuration and camera. Its scene ignores CAD
display mode, colors, clipping, exploded view, visibility, selections, inspection
pose and tessellation preferences. The browser hides inspection tools and tabs;
camera navigation and authored animations remain. Disabling Render restores the
CAD state. Snapshot output dimensions and explicit per-output cameras remain
image composition controls.

The Render panel groups settings by what the user is changing:

- **Render:** enable, Light/Dark studio, Preview/Final quality, inline
  Copy/Paste Settings and Reset.
- **Camera:** focal length in millimeters and exposure in stops.
- **Lighting:** studio rotation, softbox size and fill ratio.
- **Backdrop:** color, transparency and ground visibility.

An omitted studio follows global appearance; choosing Light or Dark pins it.
The CLI resolves the omitted studio to Light. Both studios use the same
lighting and material behavior, differing in their default backdrop color.

The old Render settings contract is deleted. There are no aliases, legacy
payload conversion or migration messages. Unsupported fields and values are
ordinary validation errors. Old per-model session state is reset.

## Rationale

Blender separates material properties, lighting, camera composition and image
exposure. Its AgX display transform compresses highlights, while exposure acts
on scene-linear values in stops. These are useful controls for handling bright
metal without applying arbitrary brightness or saturation changes to the
material itself. [Blender color management](https://docs.blender.org/manual/sr/4.5/render/color_management.html)

KeyShot likewise separates the lighting environment from the visible backdrop
and ground. Our smaller interface uses a generated studio, so users control its
orientation and shape rather than tune several overlapping ambient, hemisphere,
point, spot and directional lights independently.
[KeyShot environment settings](https://manual.keyshot.com/keyshot10/manual/environments/environment-settings/)

Authored material finishes remain authoritative. Global metalness, roughness,
clearcoat, reflection multipliers, color grading and opacity are removed from
the Render envelope. The default material for an unannotated part is a neutral
dielectric. This does not infer a physical material from a STEP color.

## Renderer boundary

This work replaces the settings model and its studio implementation. The
renderer remains WebGL raster/PBR with environment lighting and shadow maps.
It does not implement path-traced global illumination, caustics or optical
depth of field. Controls for unsupported effects are not exposed.

Three.js rectangular area lights do not support shadows in this renderer.
The studio therefore needs an explicit, shared raster approximation for its
softbox lighting rather than a nominal area-light control with no occlusion.
[Three.js RectAreaLight](https://archive.threejs.org/docs/api/en/lights/RectAreaLight.html)

Exact CAD geometry and the derived mesh-cache contract are unchanged. Final
quality chooses the existing finest bounded mesh level and higher image/shadow
resolution. Lighting and camera edits do not run model source or rebuild STEP.

An image-level A/B exposed a shadow integration defect: the CAD logarithmic
depth buffer made the transparent shadow catcher indistinguishable from no
ground at all with the installed Three.js runtime. Render now creates an ordinary
depth buffer. Its near/far camera planes follow model bounds using eight corners,
with frustum-corner intersections also including the visible foreground floor.
Fitting to the subject alone clipped the floor and exposed a sharp white band
at the bottom of the browser view; the corrected fit preserves the floor and
depth precision without scanning triangles. The CAD renderer keeps
its wide-range depth configuration. Switching modes recreates the browser
renderer while keeping the document's loaded source data.

## Validation

Validation includes 1,063 passing shared JavaScript tests, 579 passing Viewer
tests, 205 focused Python snapshot/schema/CLI tests, the docs production check, the canonical
production bundle and its generated-output freshness check. An independent
review covered state isolation, renderer/resource lifetime, animation and
session restoration. Review found and fixed inspection poses leaking from
robot and drawing views, and section/list snapshots bypassing the Render path.

Live browser testing on the warm Moonwatch fixture verified direct reload into
Render, Final geometry readiness, editable lens/exposure, Copy/Paste Settings,
CAD/Render switching, retained settings and animation playback. CAD selection,
measurement, drawing, tree and Display controls return when Render is disabled.
A persisted-Render reload initially exposed misplaced inspection-loading guards;
they now cancel only topology/edge loads, with a regression check covering both
mesh and robot document loaders.
The camera audit also fixed an inconsistent zoom percentage after pasting a
copied camera, and preserved framing when Reset returns a custom lens to 50 mm.

Real CLI images cover four fixtures in both default studios, eleven lighting,
camera and transparency variants, and three isolation/animation cases. Final
outputs are 1600 × 1200 pixels (800 × 600 requested with Final's 2× scale).
Fixtures range from a 134 KB plate to a 2.2 MB planetary assembly, plus a
material sample with polished/brushed metal, polymer, lacquer and copper.
The large Moonwatch was not regenerated for this validation.

Warm-geometry wall times from the final complete default batch, in seconds:

| Fixture | Light | Dark |
| --- | ---: | ---: |
| Mounting plate | 1.186 | 1.190 |
| Centrifugal impeller | 1.184 | 1.196 |
| Planetary assembly | 1.239 | 1.230 |
| Material samples | 1.189 | 1.163 |

These are individual end-to-end measurements, not statistical latency estimates
or before/after speedup claims. An earlier batch ranged from 1.147 to 4.403
seconds, so the final batch alone does not establish tail latency.
Geometry, cache and daemon were warm; snapshot work still includes CLI dispatch,
renderer work and image output.

Image-level checks established that hostile CAD camera, wireframe, hidden-part
and inspection-pose inputs produce an identical Render image. A different
animation time changes the rendered assembly. The repaired transparent-ground
path produces visible shadow-only alpha pixels, whereas the former logarithmic
depth configuration produced an image identical to ground disabled.

Local review images and raw timing records are under
`models/tmp/quality-refinement-20260911/review/photographic-render-20260912/`.
They are ignored local artifacts and are not included in the commit.
