# CAD Viewer

A local-filesystem CAD review app. This directory is the React CLIENT; the
backend is `cadgen viewer` — the `cadgen.viewer` package in the cadgen Python
distribution — and the built client ships inside that same wheel. One instance
serves ONE directory, fixed at start; the page is always the bare origin and
`?file=` selects an artifact inside that root. There is no hosted deployment.

**PURPOSE** — the application: all UI, workflow, and session state for
reviewing CAD artifacts (catalog, tabs, selection, pose, animation,
measurements, themes).

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
  **Follow edits** is an explicit alternative input: the runtime announces
  complete immutable preview trees while an already-running decorated build
  saves its outputs. The viewer consumes those trees and resolved kinematics,
  never source or model/output records. Plain links remain saved-file views.
- **Kinematics/animation independence**: the Kinematics tab drives the sidecar's
  mate data through the shared FK runtime; the Animation tab evaluates the
  `clips` the authored render module beside the artifact (`<name>.step.js`)
  exports, fetched live — an edit to it is a reload, never a rebuild. They
  compose in the effect records and nowhere else.
- **Loud failure**: a missing entry, an unresolvable ref, or a failed
  compile surfaces as an alert — never a silently wrong scene.

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

- Choose **Follow edits** in the file toolbar, or open
  `?file=part.step&mode=editing`, to see the root preview before its STEP save.
  Run the model normally; existing decorators need no new imports. The daemon
  must be running for live updates. The prior model stays visible while the
  next request builds; save errors or a disconnected feed remain visible.
  Restarting the daemon expires the ephemeral session, and rerunning the model
  reconnects it. Source files hold authored changes; there is no hidden durable
  preview document. Every explicit model run still waits for declared outputs.
  A successful save leaves that revision's authored preview displayed, labelled
  **Preview · STEP saved**. Choose **Saved file** to inspect the STEP read-back
  and its bound sidecar. A later successful no-op run without a new preview, or
  an expired preview with a validated saved result, uses the saved file instead.
  Complete displayed component arrays remain available while a replacement
  stages or fails. An unchanged immutable surface at the same tessellation
  reuses those arrays across revisions; placements and appearance come from
  the new tree. Snapshot source isolation is unchanged.
- Assemblies with at least 64 unique components start at a coarser display
  tessellation. Smaller assemblies keep the standard level, except an
  individually oversized component may start coarse if its estimate fits.
  Refinement uses the camera and disposable memory budget; exact geometry,
  measurements and explicit mesh-export tolerances remain unchanged.
  Admission can reclaim idle tessellation workers and retry while preserving
  active consumers. Its ledger samples each live worker's own retained estimate
  before admission; a large component does not inflate every worker's charge.
  Refinement reserves both replacement arrays and worker scratch space, and
  includes the coarse tier's relaxed angular tolerance in its estimate.
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
