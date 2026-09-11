# Preview delivery and first renderer draw — 2026-09-11

This bounded study compares the previous preview poll schedule with the held
preview feed on the same runtime. It measures source edits through publication,
HTTP receipt, actual scene adoption, the first main-scene renderer draw and STEP
save. It does not measure compositor presentation or claim all FreeCAD behavior
has reached parity.

## Method

The durable [harness](r4-preview-delivery.mjs) creates 2- and 24-occurrence fixtures
under `models/tmp/r4-preview-delivery`. One box moves for the placement case; one
box changes width for the geometry case. Remaining occurrences keep the same
geometry and placement. Each scenario has one paired legacy/held observation;
condition order alternates. Both baseline and target outputs, including their
STEP readbacks, are warmed before either condition. A source nonce ensures that
each timed run actually executes the source path rather than taking a whole-model
no-op. Both conditions must publish identical preview TREE and saved STEP hashes.

The counterfactual changes only the browser's served `observeEditingPreview`
module: no `after` cursor, 100 ms after submitted/queued/building responses and
500 ms otherwise. Production files are unchanged. Both conditions receive the
same passive served-source hook immediately after CadViewer computes its actual
adoption receipt. The hook requires the requested occurrence count, target box
bounds and target placement. A draw counts only after adoption, when
`runtime.cadScene.source` still equals that exact source and `renderer.render`
draws `runtime.scene`. A generic scene-sync counter, a requestAnimationFrame
callback or a HUD draw cannot satisfy the measurement.

The isolated fixture worker has one idempotent observer of its existing
`emit_event` function. It prints the clock and publication metadata before
delegating to the original function. This measures the **worker publication
event**, not when the supervisor ledger receives it. The observer and browser
hooks are present in both conditions. Snapshot accounting adds some instrument
overhead between adoption and drawing; these are instrumented observations.

Node/browser use epoch-based monotonic clocks; the worker uses the same host's
wall clock. Each browser context records five clock round trips and applies the
minimum-RTT offset estimate, retaining its uncertainty. Raw data includes worker
event relay receipt separately. The STEP-saved event is emitted after writing
the document and publishing its checked record; Python process exit is a later,
separate point.

Edits target 125 or 375 ms after an idle preview response, alternating by
scenario. Actual intervals from the latest idle response were 129–406 ms in
the accepted final observations. Waiting for a complete baseline scene can
extend the requested interval. An in-flight idle request also changes the following
poll deadline. Raw data records these intervals and requests. These phases and
the small sample count cannot establish a
universal 500 ms saving, a median, a tail latency or a cold-start improvement.
Exact topology selection and failed-replacement recovery are exercised by the
separate [R3 browser study](INCREMENTAL-SCENE-20260911.md); this probe measures the
first new geometry draw, without forcing lazy face selectors to hydrate.

## Reproduction

Use an otherwise idle machine. Start a dedicated development viewer from the
repository root on an available port with these environment values (replace the
Python path with the environment containing the checkout's dependencies):

```sh
PORT=4174 \
VIEWER_PYTHON=/path/to/python \
PYTHONPATH="$PWD/packages/cadgen/src" \
CADGEN_CACHE_DIR="$PWD/models/tmp/r4-preview-delivery/cache" \
CADGEN_DAEMON_STATE_DIR="$PWD/models/tmp/r4-preview-delivery/daemon" \
CADGEN_DAEMON_SOCKET=/private/tmp/cadgen-r4-preview.sock \
npm --prefix apps/viewer run dev -- --host 127.0.0.1 --strictPort
```

Then run:

```sh
node scripts/bench/cadgen-performance/r4-preview-delivery.mjs \
  --url http://127.0.0.1:4174 --python /path/to/python \
  --browser-root /path/to/viewer-with-playwright
```

The separate authored-baseline check adds `--counts 24 --scenarios placement
--baseline-source authored --timeout-sec 90 --output /tmp/r4-authored.json`.
It requires the worker's exact baseline TREE to match the live workspace mesh
hash and the actual displayed source object before writing the edit; it also
records component LOD keys and array sizes.

The browser and model clients must use the same store, daemon state and socket.
The harness reads the viewer's served root and records runtime source content
fingerprints before and after. A changed commit id alone does not invalidate a
run. The default deadline is 180 seconds; there are eight timed edits and no
large assembly stress tests. Generated sources and CAD assets remain under
`models/`; only the small JSON evidence is kept with this report.

## Results

All eight accepted final edits passed. Values below are milliseconds from completed
source write, **legacy polling → held feed**. These are individual paired
observations, not medians.

| Assembly / edit | Worker preview event | Browser JSON receipt | New scene adopted | First main-scene draw | STEP saved |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2 occurrences / placement | 128.0 → 138.8 | 377.5 → 144.9 | 402.7 → 179.3 | **409.1 → 186.4** | 138.7 → 151.3 |
| 2 occurrences / one-part geometry | 131.2 → 131.0 | 237.1 → 142.8 | 340.9 → 282.8 | **348.9 → 290.3** | 142.8 → 142.9 |
| 24 occurrences / placement | 147.6 → 155.6 | 305.4 → 197.8 | 338.9 → 231.2 | **350.9 → 244.5** | 169.5 → 177.2 |
| 24 occurrences / one-part geometry | 145.5 → 148.8 | 243.3 → 204.1 | 347.7 → 315.4 | **369.1 → 338.2** | 165.4 → 168.0 |

The direct delivery stage, from worker preview event to browser JSON receipt,
fell from 249 → 6 ms, 106 → 12 ms, 158 → 42 ms and 98 → 55 ms, respectively.
First-draw improvements were about 223, 59, 106 and 31 ms. Geometry changes still
spent 104–140 ms between HTTP receipt and adoption in this study, so reducing
notification delay alone does not remove mesh loading and scene work. The
placement cases showed the largest visible improvement here. Different polling
phases and browser scheduling can produce different gains.

Every STEP save completed before the new scene's first draw in these small
cases. Preview-before-save is an architectural capability, not a guarantee
that the browser always displays the result before a fast save finishes.
Python process exit was 185–226 ms in these final observations. The earlier
pre-R5 checkpoint measured 2.8–3.7 seconds despite already-completed STEP saves.
That invocation tail prompted the [discarded-return fix](R5-SCRIPT-COMPLETION-20260911.md).
The final comparison runs both poll modes with R5 enabled, isolating notification
delivery; it is not a before/after R5 browser measurement.

The known target bounds and placement matched on adoption, the first counted
draw used that exact adopted source in the main model scene, and all samples
had worker → HTTP → adoption → draw ordering within recorded clock uncertainty.
Each pair produced identical preview TREE and saved document hashes. The latter
was also checked against actual STEP bytes. No page errors occurred. Placement
preserved all 2/24 component identities; geometry changed exactly one.

The first final-runtime run took 22.8 seconds for eight edits. Its two
24-occurrence placement baselines sampled the initial loading transition before
the live renderer had complete records. Those two observations are retained as
diagnostics and excluded from the table. A 4.0-second replacement pair required
all 24 live records, nonnull geometry/row identities and an actual completed
baseline main-scene draw immediately before writing the edit. All sampled
postwrite main-scene frames in that pair retained 24 records. The other six
observations already had complete before/after identities.

The 2-occurrence placement retained both GPU geometries and display records,
and one unchanged composition row. Geometry edits retained 1/2 and 23/24 rows,
source meshes, display records and GPU geometries. The accepted first-edit
24-placement pair retained all component identities but replaced all display
mesh objects: surface/edge bytes changed from 19,460/10,196 to 18,212/8,148,
and an intermediate source with unchanged placement was drawn before the target.
This is evidence of a display-payload transition. The raw snapshot did not bind
the baseline to an exact authored TREE/LOD, so it cannot distinguish a catalog
transition from adaptive refinement. It is not steady-edit GPU reuse evidence.

A separate [authored-baseline pair](results/r4-preview-delivery-final-authored-placement-20260911.json.gz)
resolves the resource question with exact TREE bindings and LOD keys. At stable
LOD 0, all 24 source meshes, display records, GPU geometries and position
attributes survived the placement change; 23 unchanged composition rows also
survived. The other observation started at LOD 1 and ended at LOD 0 for all
three components. Their `surfaceInput` and `surfaceObject` hashes stayed equal,
but mesh keys changed from `:l1` to `:l0`; the cylinder changed from 439 vertices /
478 triangles to 409 / 434. Replacing these different tessellations is expected.
The reuse path preserves a retained component's selected level and verifies its
exact tessellation key; the viewport scheduler can subsequently choose a
different level. Every sampled frame retained 24 records. This pair's draws
were 413.0 → 260.1 ms; those separate conditions are not substituted into the
first-edit table or pooled with it.

The accepted final data uses macOS arm64, Node 26.7.0 and Chromium 148.0.7778.96
on commit `9081de210e285b1e778079d602ec523cf72d2a1a`. All 630 product source files
were clean and unchanged; their aggregate SHA256 is
`b047608467a1831b744f2e0a6db00f87e85be3dea97fc71b7b70048278b06649`.
Browser clock uncertainty was 0.13–0.18 ms, with a further 2 ms tolerance for
host clock alignment. The [combined raw evidence](results/r4-preview-delivery-20260911.json.gz)
retains stage clocks, actual polling phases, preview requests/responses and
output proofs. The [initial final-runtime run](results/r4-preview-delivery-final-initial-20260911.json.gz)
and [corrected placement pair](results/r4-preview-delivery-final-placement-correction-20260911.json.gz)
preserve their separate harness fingerprints and provenance.

The [pre-R5 checkpoint](results/r4-preview-delivery-pre-r5-20260911.json.gz)
remains separate: its first draws were 413.8 → 208.3 ms, 462.9 → 406.6 ms,
562.4 → 302.7 ms and 374.9 → 346.6 ms. It used commit `4406d1614` and took
84.6 seconds. Its optional reuse counts lacked a reliable baseline and are
excluded from conclusions. None of these separate runs are pooled into medians.

The first-draw endpoint means the completed CPU invocation of
`renderer.render(runtime.scene, camera)` for that source. GPU completion and
compositor presentation remain unmeasured. No FreeCAD backend was timed in this
study, so these improvements must not be presented as a direct FreeCAD speedup
or a general parity result.
