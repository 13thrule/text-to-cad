# CAD and Render separation — 2026-09-11

## Implementation

App appearance is a System/Light/Dark preference remembered in a host cookie.
The Display tab owns inspection controls, including camera projection, edges,
guides and part colors. The final inspector tab, Render, opts each model into
customizable studio lighting, materials and higher quality. CAD and Render
camera/display settings are separate sessionStorage state.

The viewer and snapshot CLI resolve the same sparse Render envelope through
cadgen-js. `--render` replaces `--theme`; explicit camera/display arguments win.
Normal snapshots use light CAD settings. Copy/Paste Settings transfers the
Render envelope, including orthographic framing. The adaptive appearance
follows the app in the viewer and the deterministic light default in the CLI.

Quality is a policy over the existing renderer and tessellation ladder:

| Policy | Visible screen-error target | Idle pixel-ratio cap | Snapshot mesh rung | Snapshot scale |
| --- | ---: | ---: | --- | ---: |
| CAD / Interactive | 1.25 px | 1.5 | L1 | 1× |
| Standard | 1 px | 2 | L1 | 1× |
| High (Render default) | 0.5 px | 2 | L2 | 2× |

The viewport refines visible components within its existing memory budget;
High does not force an entire assembly to its finest tessellation. Its status
reports whether the visible target is reached or limited. Existing meshes
cannot gain missing geometric detail through this policy.

Material edits update existing scene materials, including records added during
later refinement. Quality changes reuse the scheduler and geometry cache.
Neither setting requires rerunning model code or rebuilding exact geometry.
Studio settings remain outside the derived object/index store. No cache format
or version changed for this work.

## Snapshot integration measurements

Single warm runs on the development machine, using the existing local fixture
store. These measure the complete CLI invocation and PNG output; they are smoke
measurements, not controlled before/after speedup benchmarks. Other development
work was running concurrently. No giant assembly was cold-built or forced
through a full retessellation.

| Input and scene | Output pixels | Wall time |
| --- | --- | ---: |
| Mounting plate, CAD | 800 × 600 | 1.642 s |
| Mounting plate, High Render | 1600 × 1200 | 2.195 s |
| Mounting plate, custom Render + front camera override | 800 × 600 | 1.684 s |
| Impeller, High Bright studio | 1600 × 1200 | 1.683 s |
| Planetary assembly, CAD | 800 × 600 | 1.754 s |
| Planetary assembly, Standard Render | 800 × 600 | 1.784 s |
| Mounting plate GLB, High Dark studio | 1600 × 1200 | 1.074 s |
| Four-hole DXF plate, High Bright studio | 1600 × 1200 | 1.152 s |

All eight outputs were checked for successful exit, expected dimensions,
nonempty image content and visual correctness. Automatic perspective framing
was corrected during review to fill the output consistently; explicit camera
poses remain unchanged. The impeller's segmented blades are authored as a
five-segment polygon, so visible facets there are part of the source geometry.

Example reproduction after compiling the fixture into the local store:

```bash
cadgen snapshot models/examples/STEP/mounting_plate.step /tmp/plate-cad.png \
  --width 800 --height 600 --json
cadgen snapshot models/examples/STEP/mounting_plate.step /tmp/plate-render.png \
  --width 800 --height 600 --render default --json
```

## Integration review

Browser checks cover global appearance and reload, per-model isolation, Render
disable/reenable, exact camera framing across model switches, clipboard
validation, explicit camera application, material edits and quality changes.
Moonwatch's existing cached view reached High detail with the new Render setup;
assembly references remained selectable. That check is not a timed Moonwatch
generation benchmark.

Validation passed: 1,041 shared JavaScript tests, 571 viewer tests, and a
combined 239 Python snapshot/video/cache/parity tests. The docs build, six
package-boundary tests, release metadata check and generated runtime freshness
gate also pass. Generated browser/runtime assets are refreshed through the
repository's bundle entrypoint.

This change separates interactive inspection from presentation quality. It
uses the existing raster/PBR renderer; it does not add a path tracer or establish
a new generation-performance comparison against FreeCAD.
