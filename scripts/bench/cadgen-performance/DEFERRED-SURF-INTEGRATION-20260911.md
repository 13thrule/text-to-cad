# Geometry and display integration

The production implementation separates native geometry publication from display
surface extraction. The object/index store and decorator-only model interface
remain intact. The frozen package, installed-wheel and browser checks pass.
Public native measurements and a small procedural check are complete; the
nine-part monolithic preview target remains unresolved at its last measurement.
The coordinated implementation is committed as `ebce2a143`; its required
generated-runtime freshness hook passes.

Two follow-ups are committed and verified: `05826cfc1` removes duplicate full
closure validation on imported CLI cache hits; `c83b191cf` repairs the reported
canvas-selection regression. The final viewer entry is `index-YIbFxBO-.js`.

## Implemented contract

- Geometry-tree schema 1 and model/document schema 4 pin readable native BREP,
  its codec and effective intrinsic face colors. Normal native reads, parent
  materialization, STEP re-emission and summary inspection do not require SURF.
  Exceptional eager-only components retain explicit required display bytes.
- Surface jobs use the existing build pool and immutable artifact inputs. The
  runtime producer, derivation input and exact SURF output are distinct
  identities; stale producer recovery stages a complete replacement view.
- TESS v4 binds the derivation, exact surface, both binary64 tolerances and
  payload/mesher versions. Tessellation bytes live in `objects/`, with
  `index/mesh` holding their lookup and admission facts.
- Warm meshes render without surface records or SURF objects. A later selector
  request must reconstruct the exact surface pinned by those triangles.
- HTTP reads require an exact mesh-object hash and explicit byte allowance.
  Probes precede downloads; batches are bounded. Filesystem reads use a bounded
  descriptor read with size and digest checks across concurrent replacement.
- Python and JavaScript reject malformed rendering metadata before it reaches
  selectors. Oversized metadata requests are rejected before body allocation.
- Metadata requests verify the full required geometry closure once per request,
  releasing raw object bytes after verification. Native consumers still retain
  complete owned snapshots; no metadata snapshot persists between polls.

The release version remains 0.5.1. These internal schema changes deliberately
invalidate prior cache entries; they do not require model-source changes.

## Completed acceptance checks

The geometry/display package suite passes **1,725 Python tests** in 394.552 seconds.
The shared JavaScript suite passes 1,014 tests; the viewer client passed 511
at that checkpoint. The CLI follow-up passes 89 focused tests, including seven
new regressions. The final viewer passes all 514 client tests. These separate
follow-up checks are not a claim that the full Python suite was rerun afterward.
The latest separate viewer-backend run passes 342 tests. Real HTTP checks cover
exact-object reads, rejected admission and oversized headers arriving without
request bodies. Canonical bundling and the generated-output freshness gate pass.
The geometry/display browser checkpoint used `index-DzqA61Vg.js`; the later
canvas repair changed the viewer bundle to `index-YIbFxBO-.js`.

Independent reviews covered native ownership and codec recovery, the store
contract, metadata capture, surface-job scheduling, mesh identity/admission and
the shared filesystem provider. A hash-valid but unreadable native payload now
enters saved-document repair rather than leaking an OCP exception. The store
CLI recognizes the new surface index.

At the preceding browser checkpoint, four alternating saved-file replacements
passed all 12 lifecycle assertions. A separate copied-store experiment removed
12 surface records and their objects while retaining 21 mesh entries. All 12
assertions passed: complete display used cached meshes without requesting SURF,
then the first selector request recreated the exact pinned surface. Those
checks used a nine-part assembly and a 24-instance fixture, with no hand input.
The [final lifecycle checkpoint](results/viewer-lifecycle-geometry-v4-20260911.json.gz)
and [adaptive checkpoint](results/viewer-adaptive-geometry-v4-20260911.json.gz)
serve `index-DzqA61Vg.js` from port 3277 and pass
all 12 lifecycle assertions plus all 12 default-adaptive/resize assertions.
It verifies the served entry and worker bytes, complete nine-part display,
selector demand, animation, worker cleanup and stable per-revision GPU totals
across four alternating saved-file replacements. The lifecycle's expected
aborted mesh requests occur during supersession; neither check has page errors.

A broad intermediate run executed 1,725 package tests. Six errors occurred in
two modules while concurrent runtime edits restarted their shared test daemon;
both modules passed all 11 tests when rerun without runtime edits. The final
complete frozen run passes. Repository policy checks pass 126
tests with one skip. Documentation lint, build, asset and icon checks pass.

The [isolated installed wheel](results/installed-wheel-geometry-v12-summary-20260911.json)
passes all 21 commands. Its 187 Python files and
29 bundled runtime files exactly match source, wheel and installation. Two
ordinary decorated children preserve exact cold/warm pins and saved outputs.
Source-free reads, summary inspection, forced compilation and three native
corruption-repair paths pass, including an honestly hashed unreadable OCP
payload. STEP, STL, GLB, posed PNG and a three-frame MP4 export successfully;
the media were visually reviewed. All 22 served viewer assets match the wheel,
and provenance from the actual server confirms that it imports no CAD kernel.
That validation server exited cleanly. Its wheel SHA-256 is
`0af79097b1a4eddeec58136318e1a1c4e3d8c9949288d5d9bacba0d871775646`.

The [final installed-wheel follow-up](results/installed-wheel-cli-canvas-v15-summary-20260911.json)
verifies the later CLI and viewer changes
with 25 expected command outcomes: 24 successes and deliberate rejection of an
annotation sidecar bound to replaced STEP bytes. It checks cold/current/forced
compilation, missing BREP/tree and corrupt-tree recovery, a distinct same-path
document replacement, source-free reads and summary inspection, and restoration
of the exact original STEP/sidecar pair. All 187 Python and 29 runtime files
match source, wheel and isolated installation. All 22 served assets match the
final wheel, including `index-YIbFxBO-.js`; the actual server imports no CAD
kernel and exits cleanly. Wheel SHA-256 is
`c4e668e48a45210a6e96b868db42e108c63463854a0e8b52511c5f9f8bef7d4d`.
The media/export paths were unchanged from the full installed-wheel check.
Two helper-only failed trials are [preserved separately](results/installed-wheel-cli-canvas-v13-v14-diagnostics-20260911.json):
one incorrectly expected whole-root translation to change a normalized tree;
the other incorrectly expected a stale annotation sidecar to remain accepted.
The final fixture changes one child's relative placement and checks the
expected sidecar rejection explicitly. No runtime fix was needed for either.

### Canvas-selection repair

The user reported working hover feedback but no selected references from canvas
clicks. This was reproduced in the actual in-app viewer: tree-driven selection
worked, but a collapsed component click was deferred while waiting for topology
that only expansion would request. An empty assembly composition key was also
treated as missing. Earlier lifecycle checks covered tree-driven selection and
missed this path.

The viewer now resolves a valid component before deferring topology-dependent
selection, handles the empty key explicitly, and clears superseded pending
clicks. Deferred picks remain fenced by file and tree identity. In the actual
in-app tab, a collapsed canvas click selects `o1.3`; after expansion, a canvas
click selects face `o1.3.f5`. An isolated regression passes all nine assertions:
component selection causes no SURF request, expanded face/edge selection produces
the exact copy references, switching files drops old references, and no console
errors occur. The [canvas and small-fixture report](TINY-PROCEDURAL-AND-CANVAS-20260911.md)
preserves the final served bundle and browser evidence.

The [validation log archive](results/geometry-v4-final-validation-20260911.json)
preserves exact command output and hashes. The
[follow-up record](results/final-followups-validation-20260911.json) preserves
the final bundle/freshness logs and direct in-app confirmation. The earlier lifecycle attempt with
two edit cycles did not have enough repeated observations of each revision to
assess a plateau; its [failed result](results/viewer-lifecycle-insufficient-samples-20260911.json.gz)
is preserved. The corrected harness requires at least four cycles and checks
both revisions separately. The [mesh-without-SURF experiment](results/viewer-warm-mesh-without-surf-20260911.json)
is a separate copied-store test, not a deletion of the user's viewer cache.

## Measurement boundaries

The [resident core study](DEFERRED-SURF-CORE-20260911.md) measured cold native
read/publication at 1,126 → 342 ms and placement edit/save/readback at
1,295 → 522 ms. Those prototype timings exclude public dispatch and browser
work; preparing every surface afterward was about 3% slower overall.

The [final public read/compile study](PUBLIC-NATIVE-HARD-CUT-20260911.md) measures
native empty-store read at 1,180 → 407 ms and placement edit/write/readback at
1,441 → 615 ms with warm kernels. Complete surface readiness is 5–10% slower,
and unchanged CLI compile regresses from 139 → 195 ms. Startup boundaries,
constrained worker policy and shared-host activity are disclosed in that report.
The later [CLI correction](results/imported-compile-snapshot-20260911.json)
reduces three closure validations per imported hit to one coherent, call-local
snapshot and rechecks the STEP digest before returning it. Its 89 focused tests
verify work count, file replacement, generated gates and declared-export repair;
elapsed CLI latency was not remeasured.

Automatic approval review rejected the proposed 128-call planetary procedural
study as sustained assembly stress testing. It did not start. A separate
three-part check completed 16 calls in 28.9 seconds, with exact geometry, STEP
bytes, appearance, placement and child-pin parity; its owned processes exited.
An earlier incomplete 12-call attempt is retained separately; its recorded
stop cause is unknown and it lacks the fourth comparison condition.
Single observations and baseline child-worker startup prevent a stable speedup
claim. That check cannot close the nine-part target: the previous approximately
500 ms monolithic preview remains an unmet 250 ms target. Functional test
durations are not performance measurements.

FreeCAD's retained document remains a different execution model from arbitrary
Python model replay and immutable native publication. Its measured headless
edit/recompute and STEP export results remain in the
[matched workload comparison](WARM-COMPARISON-20260910.md#freecad-on-the-same-step).
