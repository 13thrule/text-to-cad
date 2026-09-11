# cadgen-js

The shared JavaScript half of cadgen: everything the distribution and its
clients both need to turn cached geometry into pixels, meshes, and motion.
This is SOURCE; the built, stamped copies that ship live in
`packages/cadgen/src/cadgen/_runtime/` — one sentence that resolves the one
ambiguity the name carries.

**PURPOSE** — the shared dependencies between cadgen (as it relates to
rendering files) and its clients: the CAD Viewer, the docs app, and any
future client. One package, one copy of each shared primitive.

**MAY DEPEND ON** — three, three-mesh-bvh and meshoptimizer, pinned by the
package manifest and lockfile, and nothing else at runtime. **Never React, never app or
workflow state, never Python coupling.** Framework-agnostic by law,
enforced by the imports-direction policy test.

**DEPENDED ON BY** — `apps/viewer` and `apps/docs` (source, via the
`cadgen-js` specifier and each app's alias), and the bundlers
(`scripts/bundle/`), which build it into cadgen's `_runtime/` (the browser
snapshot renderer and the node builders in `bin/`).

## The laws that live here

- **Viewer three-input law**: a client renders from the file, its sidecar
  (`<name>.step.json`), its optional adjacent render module
  (`<name>.step.js`), and the cache — never source, never a build. The
  code in this package must be writable against exactly those inputs.
  An explicitly attached editing session may provide an immutable preview
  tree and resolved kinematics instead; it must not alias that tree to saved
  STEP bytes. Saved schema-8 sidecars require a matching document digest.
  Their appearance section supplies resolved PBR values for canonical leaf
  occurrences. Composition owns its material overrides and never mutates the
  stored tree or component tessellation. Session state and UI remain in the app.
- **Resource ownership**: component geometry and edge textures can have more
  than one scene owner; only the last release disposes shared GPU/BVH state.
  Full scene disposal includes host-reparented groups and records attached by
  an interrupted reconciliation. Cleanup retires completed ownership steps;
  a thrown disposal remains retryable and cannot release another scene's share
  twice. Failed initial construction cleans its partial scene before throwing,
  or transfers the still-owned scene with an explicit cleanup error for retry.
  Render-only loads do not construct selector topology until requested.
  Viewport refinement keeps this demand boundary: unused components replace
  only display arrays; a component with active topology replaces its selectors
  at the same concrete tessellation before publishing new triangles.
  Repeated compatible opaque surfaces share instanced draws and retain
  occurrence identity; mirrors, transparency and deformation use explicit
  fallback paths. Disposable resource admission never changes exact geometry
  or persistent cache identity.
  Raycast accelerators may be deferred until a ray reaches a component's local
  bounds. The first ray uses exact stock intersection; surface builds enter a
  single worker queue in idle time and are shared by occurrences. Admission
  covers private position/index copies, worker scratch, and the result before
  creating an isolate. Display arrays are never transferred. Each worker ends
  with its reservation; only serialized BVH nodes and the indirect triangle
  permutation return. Failed or pending builds keep stock picking. A result
  must match the geometry's attributes, arrays, versions, groups, draw range,
  and live ownership; the last geometry release cancels queued or active work.
  Deformation runs before the bounds test. Byte accounting includes both packed
  BVH nodes and their indirect triangle permutation.
  Recomposition may take its previous result when the descriptor and component
  inputs are immutable. It shares unchanged occurrence rows and unchanged tree
  metadata across detail swaps; changed triangle ranges, bounds, placements and
  appearance still produce the corresponding new records. Its private weak
  ownership metadata never enters saved geometry or cache identity.
  Detail publications retain compatible surface instance sets and their original
  occurrence slots. Only changed membership or render passes replace those sets;
  selected, hidden and deformed occurrences keep inactive slots until eligible
  again. Transform passes reuse each mesh's matrix while observing mutable source
  transforms and effect matrices on every update.
  Surface instance groups use aggregate frustum bounds, invalidated by instance
  matrix and slot changes. Transformed component boxes and conservative parent
  affine padding keep boundary-crossing geometry eligible, including shear.
  Culling changes draw submission only; occurrence slots and picking remain
  intact. Screen-space edge instances retain their separate drawing policy.
  Material pass keys reuse serialized strings only after comparing their current
  scalar values, emission state, render order and clipping planes. Direct material
  and plane mutations remain observable; custom values use ordinary serialization.
  Reapplying material settings preserves unchanged shader programs and owned
  emissive colors. Colour and PBR uniforms still update on every pass; feature
  changes, vertex-colour mode and transparency invalidate the appropriate program.
  Clients that apply pose, selection or material changes directly to display
  records finish with `scene.syncSurfaceInstances()`; this uses the same
  reconciliation as a source update. Clip-only viewer updates also synchronize
  the shared surface material. Reflection intensity belongs to the shared pass
  key. A distinct nonblack emissive channel, or emission over vertex colours,
  uses the ordinary material so the instance colour cannot tint that channel.
- **Worker isolation**: each tessellation worker runs one request at a time;
  excess requests wait on the client. Aborting synchronous work replaces only
  its worker, preserving other callers. A failed worker request reports an
  error instead of retrying expensive tessellation on the UI thread. Inline
  execution is reserved for environments where workers cannot start.
  Pressure reclamation may release idle worker slots while active and queued
  consumers keep their work. Each live slot retains its own highest completed
  request estimate, including handled failures. Reclamation or replacement
  removes that slot's charge. Memory estimates stay on the client; they do not
  enter worker messages or cache keys, and RAM hits add no worker charge.
  A pool starts with one isolate and grows only for ready concurrent requests.
  Sequential viewport refinement reuses that isolate until the drain becomes
  idle; it does not create a maximum-size pool for each component.
- **Revision reuse**: canonical geometry trees contain no surface-producer
  selection. A runtime view binds each component's opaque surface input to a
  concrete immutable SURF object, and render/selector reuse requires that
  exact binding plus the lossless tolerance pair and payload version. Other
  snapshot source scopes remain isolated.
  Placement and appearance belong to each tree's occurrence composition.
  Viewport L0 is explicitly coarse; L1 preserves the canonical default mesh
  options and key. Changing viewport detail never changes export defaults.
- **Kinematics is data, choreography is JS, independently**: the FK
  evaluator (`kinematicsRuntime.js`) folds sidecar mate data into
  transforms and is the operation-for-operation twin of the Python
  evaluator (`cadgen/_internal/kinematics_fk.py`) — a viewer slider and an
  exported bake agree to the bit. The animation runtime
  (`animationRuntime.js`) evaluates the `clips` the render module beside the
  document (`<name>.step.js`, loaded by `renderModule.js`) exports, with the
  `m.get(target)` handle contract (premultiplying calls, reset to rest every
  frame, pure in t). That module is authored, never generated: editing it is
  a reload, never a rebuild. Neither half references the other; they
  meet only in the effect records. Flexible swept bodies use
  [tube deformation](docs/tube-deformation.md), deforming the original STEP
  tessellation through analytic centerlines in that same shared effects pass.
- **Byte determinism**: the tessellator and mesh serializers here produce
  the shipped export bytes — same geometry in, same bytes out. Deterministic
  algorithm changes advance `TESSELLATION_VERSION` and its Python mirror so
  old cached meshes cannot masquerade as current output. Meshing preserves
  shared trim references and treats Float32 transport precision explicitly,
  including periodic seams and primitive poles/apices.
- **Loud failure**: unresolved refs, unknown labels, and unknown presets
  throw with the known set listed; nothing renders a plausible wrong frame.

## The shape of the package

```
src/
  common/          # rendering + runtime entries shared by every consumer:
                   #   cadScene (scene build), renderMeshScene/renderModel/
                   #   renderOptions (stills), headlessRenderEntry (the
                   #   snapshot browser bundle's entrypoint),
                   #   kinematicsRuntime + kinematicsModule (FK + sidecar ->
                   #   pose definition), animationRuntime (clips),
                   #   stepModule/stepModuleEffects (effects application),
                   #   source (render-source loading), themeSettings,
                   #   displaySettings, stepTopology
  lib/             # subsystems: surf/ (tessellation + caches), selectors/
                   #   (ref runtime), assembly/ (package composition),
                   #   render/ (format mesh loaders), viewer/ (exploded
                   #   view, part visual state), urdf/ (robot loading),
                   #   export/ (packageMeshExport), cadRefs (grammar,
                   #   parity-tested against cad_ref_syntax.py)
bin/               # node builders the bundler ships into _runtime/node:
                   #   mesh-export.mjs (the ONE mesh path), dxf-mesh.mjs
docs/              # subsystem docs (render-pipeline.md)
```

Contract mirrors that must stay in lockstep (each has a sync test):
`lib/cadRefs.js` ↔ `cadgen/cad_ref_syntax.py`;
`common/kinematicsRuntime.js` ↔ `cadgen/_internal/kinematics_fk.py`;
tessellation v4 keys, headers and mesh-index records ↔ `cadgen/store/meshes.py`.

Browser mesh-cache reads start with a bounded metadata probe. The client admits
the encoded object and conservative decoded size before fetching a body, binds
that fetch to the probed object digest and byte limit, then verifies the v4
header and content address before adoption. A validated warm entry carries the
full surface-object provenance, so rendering does not need the SURF object or
its derivation index to remain present. `createHttpTessellationCacheProvider`
takes an `origin` for hosts whose cache is not on the page's own origin. TESB
body groups remain bounded at 32 MiB; the Node export provider uses the same
immutable `objects/` and `index/mesh/` layout as Python.

Scene geometry is the tessellator's INDEXED output: a surf component's
meshData shares the tessellation's vertex, normal and index buffers by
reference (a decoded `.tess` cache entry is copied out of its one entry
buffer) and is never expanded per triangle corner. CAD edges are not a
surface shader: `surfMeshData.js` emits indexed line segments
(`cadEdgePositions` + `cadEdgeIndices` + `cadEdgeClassRanges`, from the same
tessellation's boundary polylines, ~1.5 bytes per surface triangle) and
`cadScene.js` draws them as ONE instanced screen-space line draw per
component (`cadEdgeInstances.js`): the instances are every (segment,
occurrence) pair, decoded in the vertex shader from a per-component segment
texture (32 B per drawn segment, cached on the component) and a per-set
instance texture (128 B per occurrence: matrix, colour, opacity, visibility,
highlight). `display.edges.classes` styles colour, opacity AND thickness per
class, and a thickness is a FULL width in DEVICE pixels — every line shader
normalises its extrusion by the drawing buffer, never the CSS size, and the
fragment stage then ramps coverage across ±0.75 px either side of the ink
boundary, so an edge is feathered rather than a hard-edged quad left to MSAA.
Per-occurrence highlight, dim, hide, focus, exploded placement and
selection are slots in that texture, written by the same record passes
(`applyDisplayRecordTransform`, `applyPartVisualState`,
`syncRecordEdgeMaterials`) that drive a plain line object; highlighted
occurrences draw in a second pass at the highlight render order. A deformed
tube leaves its slot for a private `GL_LINES` object (the component's
polylines with per-point class colours) that bends with the surface. GPU cost
per component: two textures, one 4-vertex quad, two materials, one draw call
(+1 while any occurrence is highlighted). Geometry built from a shared
component is cached on the component object (`part.sourceMesh`), never on the
composed package meshData: a package is re-composed on every progressive
publish and LOD swap, and every occurrence, publish and swap reuses the one
upload. A publish of the same model reaches the live scene through
`api.update({ source })`, which reconciles records by occurrence id — records
already on screen keep their mesh, materials, visual and deformation state
and BVH; only new occurrences are built and only departed ones disposed.
Effects that change vertex positions or normals acquire
writable attributes before deforming them; material refreshes leave component
data unchanged. This keeps large assemblies from duplicating these buffers for
display. Assemblies keep geometry in their component buffers; they allocate no
combined copy of all positions, normals and indices. Rendering and section
views visit the placed components directly, and the Viewer accepts that
component geometry.

## Working on cadgen-js

- `npm --prefix packages/cadgen-js test` (node:test; no browser needed).
- Anything here that the bundlers consume changes the shipped runtimes:
  run `scripts/bundle/bundle.sh` and commit the regenerated `_runtime/node`
  and `_runtime/browser`. The staleness gate in CI enforces this.
- The viewer dev server aliases this package's source, and Vite's
  transform cache can outlive HMR — if an edit doesn't show up, restart
  the dev server and delete `apps/viewer/node_modules/.vite`.
