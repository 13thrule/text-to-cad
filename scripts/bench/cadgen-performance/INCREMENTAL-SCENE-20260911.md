# Incremental scene update validation — 2026-09-11

## Scope

This run exercises a 24-occurrence STEP assembly with two shared components. It
starts from a saved scene, attaches editing preview, moves one occurrence, and
then replaces the geometry of the component shared by twelve occurrences. The
browser check covers retained rendering, exact face/edge picking, hover,
selector adoption, resource ownership, absence of partial scene publishes, and
terminal replacement failure followed by recovery on a new revision.

The production renderer has no FreeCAD dependency. FreeCAD's retained-update
behavior is used only as the design target.

## Reproduction

Start a source Viewer against an isolated cache and daemon state/socket, then
run:

```sh
VIEWER_PYTHON=/path/to/python \
node scripts/bench/cadgen-performance/r3-incremental-browser.mjs \
  --root "$PWD" \
  --browser-root /path/to/checkout/apps/viewer \
  --url http://127.0.0.1:4173
```

The harness creates its Python fixture under `models/tmp/r3-browser`, restores
an existing fixture source on exit, and writes raw results to
`results/r3-incremental-browser.json`. The Viewer and every model child must use
the same explicit `CADGEN_CACHE_DIR`, `CADGEN_DAEMON_STATE_DIR`, and short
`CADGEN_DAEMON_SOCKET`.

## Result

The final run passed.

- All 219 placement samples and 225 component-replacement samples retained 24
  displayed occurrences. No zero-record or partial scene was published.
- Placement visibly moved `o1.15` by about 61 screen pixels. The following
  geometry revision visibly changed its selected-pixel area.
- Exact canvas picks remained available after both revisions: `o1.15.e5` and
  `o1.15.f3` after placement, then `o1.15.e5` and `o1.15.f6` after component
  replacement. Candidate pixels were restricted to the unobscured 3D viewport.
- Face hover changed 2,004 viewport pixels initially, 1,819 after placement,
  and 2,082 after replacement.
- At every interaction boundary, loading and reference-pending flags were
  false, the selector exposed 6 faces and 12 edges, and all 24 display records
  were bound to the selector runtime passed to the viewer.
- After normalizing all stages to the same hydrated topology state, retained
  renderer resources returned to 24 occurrences, 5 geometries, 16 buffers, 30
  materials, 2 surface instance sets, and 2 edge instance sets. No reservation,
  replacement, or in-flight ownership remained. The browser reported no error.
- The failure probe aborted the changed component's `SURF` payload. The old
  scene kept 24 display records, picking switched to `none`, selectors and
  pickable topology were absent, and the viewer surfaced `Failed to load render
  mesh: Failed to fetch`. The request count did not advance during a further
  1.2-second observation. A different component revision then loaded normally
  and restored exact picking and hover without leaked ownership.

## Fixes found by the browser check

The retained package scene was still being cleared by an outer workspace gate:
the entry hash changed before the replacement mesh hash arrived, so the
workspace passed `null` plus loading state to the renderer even though
`useCadAssets` correctly retained the old complete scene. The workspace now
keeps only a complete, same-file, changed-hash assembly STEP predecessor
renderable when no pose or render module is active. Reference matching stays
hash-strict, so old selectors cannot be picked while the new pair stages. A
failed target is recorded by file and hash, preventing an automatic retry of
that exact revision while allowing a different file or hash to recover. During
staging or terminal failure, canvas and tree selection, hover, measurement,
context actions, and copying are fenced from the retained revision.

Pointer activation also trusted a hover ID that could belong to a previous
point or selector revision. Pointer-down, double-click, and context activation
now perform a fresh raycast at the gesture coordinates. The listener lifetime
is bound to the selector runtime, which clears pending activation, hover, and
cached measurement edge geometry when a replacement selector is adopted.

## Microbenchmarks

The source-only composition/scene microbenchmark, run on tiny and moderate
repeated-instance inputs, measured:

| Occurrences | Composition before | Composition after | Scene before | Scene after |
|---:|---:|---:|---:|---:|
| 24 | 0.173 ms | 0.066 ms | 0.582 ms | 0.147 ms |
| 240 | 0.998 ms | 0.499 ms | 2.460 ms | 0.536 ms |

These numbers cover synchronous composition and scene update work. They do not
include preview delivery, the browser frame boundary, compositor presentation,
or STEP generation. The current-path workload is reproducible with
`r3-incremental-cpu.mjs`. The original before-source snapshot and stdout were
not preserved, so the before/after table is historical context rather than a
primary performance claim; this limitation is recorded in
`results/r3-incremental-cpu-20260911.json`.
