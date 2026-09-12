# CAD Viewer

A local-filesystem CAD review app. This directory is the React CLIENT; the
backend is `cadgen viewer` — the `cadgen.viewer` package in the cadgen Python
distribution — and the built client ships inside that same wheel. One instance
serves ONE directory, fixed at start; the page is always the bare origin and
`?file=` selects an artifact inside that root. There is no hosted deployment.

**PURPOSE** — the application: all UI, workflow, and session state for
reviewing CAD artifacts (catalog, tabs, selection, pose, animation,
measurements, Display controls, and Render settings).

**MAY DEPEND ON** — `cadgen-js` (the shared CAD render/runtime package at
`packages/cadgen-js`, imported by the `cadgen-js` specifier) and its own npm
dependencies, all bundled into the client AT BUILD TIME. At run time it talks
to `cadgen viewer` over `/__cad` and `/__tess_cache`, and to nothing else.

**DEPENDED ON BY** — the cadgen wheel, which carries this client's build
(`cadgen/_runtime/viewer`). No code imports from this app.

## The laws that bind the app

- **One boundary**: the client imports `cadgen-js` by name and nothing else
  from outside this directory (`scripts/selfContained.test.mjs` is the fence).
  The backend is not here: its code, its tests and its laws live with cadgen.
- **Three-input law**: everything renders from the artifact file, its
  sidecar (`<name>.step.json`), its optional adjacent render module
  (`<name>.step.js`), and the cache. The viewer never reads
  source code and never rebuilds on source changes — generated outputs are
  detached, and a stale artifact stays stale until someone runs its script.
  Generated STEP entries default to **Follow edits**: the runtime announces
  complete immutable preview trees while an already-running decorated build
  saves its outputs. The viewer consumes those trees and resolved kinematics,
  never source or model/output records. **Inspect saved STEP** in the file
  breadcrumb, or `?mode=saved`, selects the artifact read-back instead.
- **Kinematics/animation independence**: the Kinematics tab drives the sidecar's
  mate data through the shared FK runtime; the Animation tab evaluates the
  `clips` the authored render module beside the artifact (`<name>.step.js`)
  exports, fetched live — an edit to it is a reload, never a rebuild. They
  compose in the effect records and nowhere else.
- **Loud failure**: a missing entry, an unresolvable ref, or a failed
  compile surfaces as an alert — never a silently wrong scene.
- **Geometry and display readiness are separate**: a `compiled` artifact owns
  a complete immutable geometry tree. Display may still be waiting for an
  exact surface derivation or tessellation. A validated warm tessellation can
  render directly from its immutable object binding; selectors and a cache
  miss resolve the pinned surface asynchronously without recompiling geometry.

## Appearance, Display, and Render

App appearance is a global **System / Light / Dark** preference. System follows
the live OS preference. A host-scoped `cad-viewer-appearance` cookie remembers
the choice across browser sessions and viewer ports; a localStorage mirror
notifies other tabs on the same origin and provides a fallback when cookies
are blocked. The synchronous startup script applies the preference before the
app mounts. The navbar shows the resolved Sun or Moon icon; System appears only
as a dropdown choice. Neutral light and charcoal panel tokens remain independent from
the model's lighting and materials.

**Display** owns the CAD inspection projection, style, edges, grid, origin axes,
part colors, clipping, and exploded view. **Shaded with edges** shows shaded
surfaces with CAD edges; **Shaded** shows those surfaces without edges. Grid and
origin axes remain world references.

The navbar's **Viewing mode** icon menu switches between **Inspect** and
**Render**, showing the active mode's cube or clapperboard icon. Inspect shows only
CAD inspection tabs and restores their saved split, order, and active selection unchanged.
Render enters an isolated photographic view with **Studio** first and active;
**Animation** follows when the model provides clips. The Render tabs start in
one row on each entry. Dragging and splitting them is temporary and never
overwrites the durable per-kind CAD arrangement. The default Light or Dark
studio follows global app appearance. Backdrop customizations remain local to the model session.
The compact editor controls lens and exposure, softbox rotation, size and fill,
plus backdrop color, transparency, and ground. Khronos PBR Neutral tone mapping and a generated
softbox environment provide the Render lighting. The overhead side key models
depth, while a rear fill retains detail on dark and polished surfaces. Defaults
are checked against colored assemblies, mechanical models, and material samples
in both studios. Authored material properties
remain intact. The existing toolbar owns image capture.

Quality is independent of the studio. Normal CAD uses its Interactive policy;
Render offers **Preview** and **Final**, and defaults to Final. Preview and Final
share the tessellation ladder, cache entries, and memory budget. Preview uses
a 1-pixel screen-error target, 2048-pixel shadow maps, and a 256-pixel softbox
environment. Final requests a 0.25-pixel screen-error target, 4096-pixel shadow maps, and a 512-pixel softbox
environment. Quality changes refine the view without rebuilding exact CAD
geometry or the model scene. Entering Render creates an ordinary-depth WebGL
runtime so the photographic ground can receive shadows; returning to CAD restores
its wide-range logarithmic-depth runtime while decoded geometry stays cached. The
filename badge reports Reduced detail when memory limits prevent requested detail. Snapshots use the same policy:
Final selects the existing finest L3 STEP tessellation and 2× capture scale unless
an explicit output scale overrides it. CAD tessellation controls cannot be combined
with a photographic snapshot request.

Normal CAD settings and Render settings are separate per-model session state.
Entering Render applies its perspective camera and fixed presentation view
(shaded authored colors; guides, edges, clipping, exploded transforms, and
selection effects are off). Animation playback remains available. Returning to
CAD restores the CAD camera and inspection state; returning to Render restores
the photographic view.
These settings use sessionStorage with other per-model
ephemeral state; they are not written beside models, into the geometry cache,
or into global app appearance. A normal geometry rebuild preserves the
render setup. Closing the browser tab ends its session.

The top **Setup** section in Studio contains Quality. Reset sits at the bottom
of the tab and clears photographic customizations, restoring defaults for the
current global light/dark appearance while keeping the current camera pose.
The viewer has no studio preset selector or settings clipboard. Viewer and
snapshot commands resolve photographic scenes through the same cadgen-js
implementation; snapshots choose their studio and custom settings with `--render`.

## Launching

All commands run from this app's directory. Dev (Vite serves the client
from source with HMR; edits to `src/` and `packages/cadgen-js` show live):

```bash
npm run dev -- --host 127.0.0.1
# open http://127.0.0.1:5173/?file=<path relative to the served root>
```

Dev spawns the real backend — `python -m cadgen.viewer --api-only` on an
ephemeral port — and proxies `/__cad` and `/__tess_cache` to it, so there is one
implementation, not two, and Vite owns the client. `VIEWER_PYTHON` names the
interpreter that has cadgen installed (it defaults to `python3`, which on macOS
is still 3.9 — below the server's floor of 3.11 — and rarely the one with
cadgen); `VIEWER_BACKEND_URL` attaches to a backend you started yourself. No
build is needed first.

Prod is `cadgen viewer`, run FROM the directory to serve (there is no directory
flag, the cwd IS the served directory). In a checkout it serves this app's
`dist/` — build it first — and an installed wheel serves the copy it carries:

```bash
npm run build
cd <the directory to serve> && cadgen viewer --host 127.0.0.1 --json
```

The launcher is unconditional and prints the URL it serves: a live instance
already serving that realpath with the same code on disk is REUSED
(`action:"reused"`); otherwise it binds the first free port from 3245 upward.
`--new` forces a fresh instance of the same code; an explicit `--port` is
strict; `--dist DIR` (or `CADGEN_VIEWER_DIST`) names another built client. The
URL line (and the `--json` line) is written only after the socket is bound and
listening with the app attached, so the first request after reading it answers
— no poll, no retry, no grace period. `cadgen viewer list` shows every running
instance; `cadgen viewer stop --port <n>` ends one. Do not stop instances you
did not start. Dev lives on Vite's port (5173, strict) and never enters the
instance registry.

Reuse keys on realpath(served directory) × an identity token — the cadgen
version salted with the newest mtime across the server's `.py` files and the
built client — so an instance serving a different directory, the same directory
from another install, or code that has since been edited, pulled, or rebuilt is
never handed back by mistake. In a checkout, a server that finds `src/` beside
the `dist/` it serves also warns once on stderr when any source is newer than
the build — detection only; it keeps serving.

## Behaviours worth knowing before concluding something is broken

- Generated STEP entries open in **Follow edits** by default, showing the root
  preview before its STEP save. Choose **Inspect saved STEP** from the file
  breadcrumb menu (or open `?file=part.step&mode=saved`) to inspect the artifact
  read-back; choose **Follow edits** there to return to the live preview. The
  compact badge beside the filename reports loading, edits, save outcomes and
  detail failures or limits in one or two words. Orbit-driven refinement stays
  in the background without changing the badge. Loading uses an inline spinner;
  warnings and errors use their own icons. Tooltips explain the state.
  Run the model normally; existing decorators need no new imports. The daemon
  must be running for live updates. The prior model stays visible while the
  next request builds; save errors or a disconnected feed remain visible.
  Updates arrive through a held request that wakes when this output's build
  ledger changes. Unrelated jobs do not wake the tab. The server admits 32
  waiters independently of kernel workers; excess tabs retry every 500 ms.
  An idle heartbeat revalidates saved bytes and missing geometry;
  closing or switching the tab cancels the request.
  Complete plain STEP assemblies also remain visible while replacement meshes
  load. Selection, measurements and reference copying wait for matching new
  geometry. A failed replacement preserves the view and reports its error;
  only that file/hash stops retrying automatically. STEP pose/render modules
  use their normal loading path, without a promise to retain the previous pose.
  Restarting the daemon expires the ephemeral session, and rerunning the model
  reconnects it. Source files hold authored changes; there is no hidden durable
  preview document. Every explicit model run still waits for declared outputs.
  A successful save leaves that revision's authored preview displayed, labelled
  **Saved**. Choose **Inspect saved STEP** to inspect the STEP read-back
  and its bound sidecar. A later successful no-op run without a new preview, or
  an expired preview with a validated saved result, uses the saved file instead.
  Complete displayed component arrays remain available while a replacement
  stages or fails. Reuse requires the same runtime surface input, concrete
  surface object and tessellation; placements and appearance come from the new
  tree. Snapshot source isolation is unchanged.
- Assemblies with at least 64 unique components can start at a coarser display
  tessellation when standard meshes are not cached. Cached standard meshes are
  preferred immediately, subject to their probed decode size and admission.
  Smaller assemblies start at the standard level, except an individually
  oversized component may start coarse if its estimate fits. Coarse geometry
  is a temporary preview: visible components automatically reach at least the
  standard level, preserving its angular smoothness even when projected chord
  error alone would permit a coarser mesh. Close inspection can request finer
  detail. The top bar distinguishes preview, refinement, standard detail and
  limited or failed refinement; STEP save status remains separate.
  Refinement uses the camera and disposable memory budget; exact geometry,
  measurements and explicit mesh-export tolerances remain unchanged.
  Static assemblies sample full transformed occurrence bounds against the camera
  frustum, refining a component when at least one occurrence is on screen.
  Offscreen components stay displayed. Ordinary camera sampling retains their
  existing detail; memory pressure can coarsen them before visible components.
  Unknown or not-yet-adopted bounds remain eligible.
  A stationary camera requests the final level implied by the existing
  hysteresis thresholds directly. If admission refuses that level, strictly
  intermediate levels can supply measured replacement sizes for another try.
  Failed loads stay parked; denied admission retries only after the displayed
  level or camera intent changes. Pressure-driven coarsening caps subsequent
  refinement until the camera or viewport changes, preventing upgrade/downgrade
  loops. Mesh-bound and clip-plane updates do not reset that cap. An idle
  scheduler reports memory-limited targets separately from settled quality.
  Scenes with joints, render modules, drawing poses or an active/collapsing
  exploded view keep conservative eligibility, including paused/disabled pose
  capabilities. Authored visibility and material flags are not LOD filters.
  Admission can reclaim idle tessellation workers and retry while preserving
  active consumers. Its ledger samples each live worker's own retained estimate
  before admission; a large component does not inflate every worker's charge.
  Refinement reserves both replacement arrays and worker scratch space, and
  includes the coarse tier's relaxed angular tolerance in its estimate.
  The scheduler holds at most four distinct replacement CIDs across loading,
  ready payloads and actual scene adoption. Its render and late-selector
  preparation share one loader lane, and only one atomic mesh/reference
  publication awaits adoption. A 32 ms first-ready collection deadline may
  publish a ready subset beside one unfinished carryover; it does not guarantee
  selector, worker or scene readiness. No fifth replacement starts. Pressure
  coarsening remains singleton. Separate user-driven topology requests keep
  their existing worker admission and cache/picking accounting; they are not
  included in the scheduler's occupied-CID count.
  Actual payload backing allocations are reconciled before another sibling is
  admitted. Temporary sibling-capacity denials flush and retry after ownership
  changes; they do not permanently park a target. Displayed levels and measured
  current sizes remain unchanged until the complete exact batch adopts.
  Replacement admission stays held until the viewer adopts each current
  component payload at every occurrence and accounts for its scene ownership.
  This acknowledgment schedules rendering; it is not a GPU upload-completion
  fence. Modeled upload ownership remains separate. A superseding progressive
  publication can satisfy it only with the same context, revision, occurrence
  set and exact payload. Cancellation requests cleanup: switch, abort or unmount
  retains an outstanding reservation until actual replacement, restoration or
  complete disposal proves that the renderer has released its previous owner.
  Pending component maps remain separate from adopted maps. Display geometry
  and demanded selectors publish as one matching state pair, with commit receipts
  fencing abandoned or replayed React updates. A failed scene update clears its
  partial records before rebuilding the last adopted mesh/selector pair; it never
  reconciles against already-disposed records. Restoration preserves unrelated
  progressive components and completed selector loads. A second construction
  failure stops detail work and reports an error. Cleanup failure keeps ownership
  charged until a real cleanup retry succeeds. A cancelled batch that actually
  adopted remains a displayed payload owner even though its scheduler levels
  are not promoted, so cancellation does not evict its exact cache entries.
  Diagnostic snapshots identify scheduler-only ownership, batch sizes and seal
  reasons. The internal size-one control uses the same admission/publication
  path as groups of four.
  A static component publication can reuse the main adoption's completed reset
  only in that same React render. Later visual or clipping changes still run
  normally, as do transitions out of modules, animation, drawings or poses.
  Display arrays shared with asset caches have one CPU charge for the entire
  backing allocation, including unused sections of packed buffers. GPU charges
  use uploaded view sizes; CPU-only edge inputs and picking allocations remain
  accounted for separately. Topology-only
  interactions also release idle workers after their sibling requests drain.
  Display raycast accelerators are requested only when a picking ray reaches
  component bounds, then queued during idle time for one worker at a time.
  Admission covers private input copies, worker scratch and the returned tree;
  displayed arrays stay attached and unchanged. Releasing the last geometry
  owner cancels its build, and stale results cannot attach to replacement
  geometry. The first pick remains exact and may cost more on a dense component;
  merely loading or refining an assembly does not build an accelerator for every
  component. Inputs with a separate merged face-selection proxy still build
  that proxy's accelerator on the main thread during idle time. Canonical STEP
  selectors use the display meshes and do not enter that separate path.
  Progressive display and later detail swaps share unchanged occurrence rows
  and tree metadata; changing tessellation alone does not rebuild every tree
  leaf. Placement, appearance and changed bounds still update their records.
  Selection pruning preserves unchanged selected, referenced and hidden ID
  arrays, preventing detail publications from retaining historical workspace
  render contexts through unnecessary selection updates.
  A component that cannot fit even at the coarse level
  reports a limitation and preserves the current view. Estimates and sampled
  resource totals are a soft budget, not a hard browser RSS limit.
- A schema-8 STEP sidecar includes the STEP byte digest. A mismatch displays
  **Annotations unavailable** while permitting saved geometry to render.
  Rebuild or re-annotate the pair to repair it; importing a file never rewrites
  its authored sidecar.

- **The catalog scan skips dot-directories.** A buildable entry under
  `.review/` (or any dotted path) never appears, even when the server is
  launched from inside it.
- **Verify a link by loading the page**, never by curling `/__cad/asset` —
  that route serves raw files; generated entries render through a
  different route, so probing it 404s whether or not anything is wrong.
- **Vite's transform cache can outlive HMR and hard reloads.** If a source
  edit does not show up, restart the dev server and delete
  `node_modules/.vite`.
- Never invoke the export routes from automation — they open native save-as
  dialogs.

## The shape of the app

```
src/client/ # React app: CadWorkspace (state root), CadViewer (scene +
            #   effects application), workbench/ (tabs, sections, session
            #   state, playback), render/ (viewport)
scripts/    # app tooling incl. e2e helpers and selfContained.test.mjs
            #   (the boundary fence) and the dev-backend spawn helpers
docs/       # subsystem docs; settings-ui.md is the CURATED design-system
            #   reference for all settings UI work — binding, read it
            #   before touching controls
dist/       # built client (gitignored); what `cadgen viewer` serves in a
            #   checkout and what the wheel bundles
```

## Testing

```bash
npm run test    # client + app tooling (node:test, beside the code)
```

The backend's suite lives with cadgen and is not collected here; running only
`npm run test` leaves that half unchecked.

Headless UI verification uses Playwright with `--use-angle=metal` —
the default software WebGL renderer is not what users see.
