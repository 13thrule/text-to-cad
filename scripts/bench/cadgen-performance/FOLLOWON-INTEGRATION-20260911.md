# FreeCAD-inspired performance follow-on: integration record

This increment adds selective reuse within cadgen's existing build123d/OCP
runtime. It does not install FreeCAD, replace authored Python with a mutable
document, or claim a 100× application speedup. The measured wins come from
skipping expensive unchanged factories, preserving exact child references,
reusing browser resources, delivering previews when they become available, and
avoiding unused native return values after ordinary script builds finish.

The work continues `codex/tendon-hand-performance` from `0492c3112`, without a
release-version change. Runtime commits are `187319254` (dependencies),
`3a4ed9884` (build/cache/preview backend), `4406d1614` (viewer and bundled
renderer) and `9081de210` (discarded script returns). Measurements use small parts, a nine-part planetary
assembly and 24-occurrence fixtures. No giant hand assembly was built.

## Implemented changes

1. **Exact-reference assembly composition (R1).** Eligible ordinary
   `Compound(children=parts)` calls preserve unexposed decorated-child pins
   through source publication. Unchanged children avoid redundant native
   containers, serialization and the first XCAF document. Native access forces
   correct private geometry. The temporary internal Compound subtype and its
   exact-type introspection difference are documented. A cross-build native
   shape cache was investigated and rejected: savings were tiny and a test
   shape's BREP bytes changed after copying.
2. **Reusable pure intermediate factories (R2).** Optional `@memo` reuses
   expensive parameterized CAD helpers, including their Python/builder work.
   It uses the existing operation index and immutable BREP objects. Changed
   arguments, code, captured dependencies or globals invalidate the result.
   Unsupported code or contexts execute normally. This is an explicit pure
   function contract under an unmodified dependency runtime, not automatic
   purity certification or arbitrary Python replay. Miss, hit and disabled
   reuse return equivalent private canonical shapes.
3. **Incremental browser adoption (R3).** A new same-file revision reuses
   unchanged composition rows and assembly branches. Detached occurrence
   snapshots detect in-place input changes; provenance limits the fast path
   to internally owned rows. Scene updates touch changed static records while
   context changes, animation, clipping and external poses use the full path.
   Complete same-file plain STEP assemblies remain visible during replacement;
   pose/render-module entries keep their existing loading path. Exact selectors
   and resources remain bound to the adopted geometry.
4. **Bounded preview notifications (R4).** The viewer holds one abortable
   request instead of waiting for an idle 500 ms polling tick. A scoped daemon
   ledger cursor wakes it for relevant work; a one-second heartbeat rechecks
   disk integrity and saved bytes. Waiters are bounded, saturation backs off,
   and metadata requests cannot start workers or import source/the kernel.
5. **Faster script completion (R5).** After an ordinary bare model call finishes
   its build and checked source receipt, CPython bytecode can prove that its
   return is immediately discarded. That path avoids importing the kernel and
   reconstructing native geometry in the initiating process. Consumed returns,
   interactive/synthetic callers, tracing, profiling and monitoring retain
   their materialized geometry. No output or failure is skipped.
6. **Smaller native dependency (D1).** cadgen requires build123d 0.11.1 or later
   and `cadquery-ocp-novtk`, eliminating the redundant full-OCP/VTK route from
   fresh installs. Existing environments are not modified automatically.

The root source file is now hashed from the exact bytes compiled, with
execution dependency capture active during module initialization as well as
the model body. This closes a source-identity race exposed during integration.

## Native measurements

These are independent matched increments on the same current source, not
additive or multiplicative comparisons against the original branch. Preview
events are backend publication timestamps, separate from browser rendering.

| Scenario | Before | After | Change |
|---|---:|---:|---:|
| R1: planetary placement, preview | 142.8 ms | 92.4 ms | 35% less time |
| R1: planetary placement, complete STEP | 374.1 ms | 322.2 ms | 14% less time |
| R1: 24 repeated occurrences, preview | 60.9 ms | 40.4 ms | 34% less time |
| R2: 3 drilled plates, placement preview | 171.6 ms | 49.0 ms | 3.50× |
| R2: 9 drilled plates, placement preview | 583.8 ms | 123.6 ms | 4.72× |
| R2: 24 drilled plates, placement preview | 1,603.1 ms | 235.3 ms | 6.81× |
| R2: 24 drilled plates, complete STEP | 1,704.0 ms | 309.0 ms | 5.51× |
| R2: one changed part out of 9, preview | 578.3 ms | 140.1 ms | 4.13× |
| R2: one changed part out of 9, complete STEP | 675.2 ms | 190.6 ms | 3.54× |

R1 compares the reference path enabled/disabled, with exact revision readback
prewarmed for both members. R2 compares feature reuse enabled/disabled, with
ordinary operation caching enabled for both and three alternating pairs per
case. Novel R2 output revisions are not individually readback-prewarmed: the
first member can pay new STEP readback, so complete-save medians have a run-order
limitation. Both reports preserve individual observations. Source writes and
startup are excluded from these native tables.

Every matched native pair produced identical TREE addresses and actual STEP
bytes. R1's 24-occurrence preview reduced BREP decodes from 27 to 6, BREP
serializations from 48 to 0 and authored child materializations from 24 to 0.
The local R2 geometry edit recorded exactly eight feature hits and one miss;
the other eight components, BREP identities and placements remained unchanged.

A 12-hole BuildPart helper alone improved from 75.0 to 4.8 ms (15.7×), while a
cheap two-hole algebra helper became slower (2.3 to 5.3 ms). `@memo` is for
costly repeated helpers, not every primitive. A factory/helper source-file edit
conservatively invalidates the factories in that file; arbitrary monolithic
Python does not acquire a feature graph automatically.

Details and raw samples: [R1](REFERENCE-ASSEMBLIES-20260911.md),
[R2](FEATURE-FACTORIES-20260911.md).

## Public command completion

The browser timing investigation found commands still running seconds after
their STEP files were saved. The cause was native reconstruction of the bare
call's discarded return in the initiating process. R5 removes that work.

| Actual `python model.py --json` command | Before R5 | After R5 | Speedup |
|---|---:|---:|---:|
| 2 occurrences, unchanged | 2,634.5 ms | 113.4 ms | 23.2× |
| 2 occurrences, new placement | 2,713.6 ms | 188.3 ms | 14.4× |
| 24 occurrences, unchanged | 2,751.9 ms | 113.5 ms | 24.3× |
| 24 occurrences, new placement | 2,934.4 ms | 230.8 ms | 12.7× |

These are single alternating-order pairs, including process creation through
exit, on the same Python/dependencies with separate stores and warm daemons.
Both modes prime their base source/output; a new placement revision remains
unprimed. The baseline differs only by the pre-R5 `authoring.py`. All paired
STEP bytes match. Candidate bare callers successfully prohibit kernel imports;
an assigned-return control still reports two actual solids and volume 960 mm³.
This is a command-exit gain, not an additional factor to multiply into native
publication or browser latency. See the [R5 study](R5-SCRIPT-COMPLETION-20260911.md).

## Browser measurements and interaction

The final 24-occurrence live-browser check passed. Across 219 placement and
225 component-replacement samples, every observed scene retained 24 occurrences.
Actual viewport pixels confirmed the moved and resized part; exact face/edge
picking and hover worked after both changes. Equivalent hydrated states returned
to 5 geometries, 16 buffers and 30 materials without pending ownership.

An injected SURF fetch failure kept the prior 24-part scene, disabled all
reference picking, displayed its error and made no retry during the following
1.2 seconds. A new revision then loaded and restored exact picking. The failure
fence includes the file identity, so another file with the same mesh hash can
still load. See the [R3 report and reproducible harness](INCREMENTAL-SCENE-20260911.md).

The production viewer was separately loaded from its final bundle with the
nine-part planetary model. Its served assets matched the bundle, all nine parts
rendered, no page error occurred, and the screenshot was visually reviewed.

On the final runtime, the held preview feed improves source-write-to-first
main-scene renderer draw as follows. These are individual legacy/held pairs at
recorded polling phases, not medians or GPU/compositor presentation timings.

| Scenario | Previous polling | Held feed |
|---|---:|---:|
| 2 occurrences, placement | 409.1 ms | 186.4 ms |
| 2 occurrences, one-part geometry | 348.9 ms | 290.3 ms |
| 24 occurrences, placement | 350.9 ms | 244.5 ms |
| 24 occurrences, one-part geometry | 369.1 ms | 338.2 ms |

Worker publication, HTTP receipt, exact scene adoption and main-scene draw are
separate verified timestamps. Every pair has identical TREE and actual STEP
bytes. All saves finished before drawing in these small cases. Six observations
came from the 22.8-second final run; a four-second replacement pair corrected
an initial-loading baseline in the other two. The diagnostics remain preserved.

The first-edit 24-placement case changes display payloads even though component
identities stay equal. A separate exact authored-baseline check confirms all
24 GPU geometries/records survive when LOD stays equal; LOD 1 → 0 correctly
replaces different tessellations. No sampled frame loses any of the 24 records.
The reuse helper preserves a retained level and the viewport scheduler can
subsequently coarsen/refine it. The [R4 report](PREVIEW-DELIVERY-20260911.md)
keeps those observations and the earlier pre-R5 study separate.

Exploratory synchronous composition/scene timings are retained in the R3 report.
Their original baseline artifact was not preserved, so they are not used as
primary performance evidence. The 240-occurrence CPU fixture is tiny synthetic
JS geometry, not a CAD build.

## Cache and execution review

The public laws remain: immutable content-addressed payloads, atomic input
indexes, exact child pins, source-authoritative builds and source-free saved
artifact readers. No retained RAM handle can hide missing required objects.
All explicitly declared outputs still complete before a build succeeds, even
when a newer preview supersedes it. Disk GC remains manual.

Reference reuse is scoped to private verified snapshots, with fresh validation
at subsequent consumers and publication. Feature hits verify disk objects and
reconstruct private geometry. The daemon ledger is ephemeral status data, not
an additional persisted document/cache framework. Model authors need no keys,
sessions, persistence calls or ownership utilities.

Independent review found and corrected concrete edge cases around native child
escape/hierarchy mutations, tuple identity and NaN feature inputs, covered
runtime descriptors, preview ledger adoption/cursor races and duplicate
scene-placement work. It also found an expired-preview recovery gap after a
failed save: the viewer now uses the last retained saved result only when the
current catalog proves both its exact tree and document-byte identities. A
pending revision still preserves its usable preview, and the failure remains
visible. The explicit pure-factory contract does not support
arbitrary dependency monkeypatching or observable factory side effects.

Source review during browser validation also found that pointer-down and
activation unconditionally preferred a cached hover result. That result could
belong to an earlier position or selector revision. Activation now raycasts the
current coordinates with the existing pointer-specific thresholds and retains
that fresh pointer-down reference through OrbitControls' hover reset.
Selector replacement also clears pending activation and cached measurement
geometry. A retained predecessor has no active topology or part picking until
the replacement is adopted. Failed replacement reports its error and suppresses
automatic retry only for that exact file and target hash; a later revision or
another file can load normally.

Early browser-probe failures are not evidence of mismatched topology or timing
gains: the probe initially read selection after 100 ms, shorter than the
viewer's 220 ms double-click activation window, and incorrectly expected old
selection to survive every changed geometry tree. The final probe respects the
activation window, checks conservative selection reset, and keeps pointer move
and down/up atomic to exercise the fresh-click path.

## Validation

- Full package Python sweep: **1,796 tests** in 792.7 seconds. One stale test
  mocked `ledger.adopt` after atomic job start moved to `ledger.start`; its
  expectation was corrected and the entire affected **23-test module passed**.
  All other modules passed the full sweep. This was a test-fixture correction,
  not a runtime change after the suite.
- Focused public feature suites: **23 tests**; reference/native ownership suites:
  **90 tests**; source identity/preview/daemon integration: **45 tests**.
- The later R5 change passes **7 real-file subprocess tests**, **24 existing
  public/source-result tests** and **4 package-boundary tests**, plus the native
  command benchmark and consumed-return control. The earlier broad Python
  sweep predates this narrow authoring change.
- Remaining Python skill sweep: **434 tests** across eight suites. Eight errors
  came from stale CAD-generation mocks publishing structurally invalid empty
  or fake-SURF trees. The mocks now use a tiny complete native component; all
  **45 tests in that affected module passed** on rerun. Runtime validation was
  kept intact, and the other seven skill suites passed their original run.
- Shared JavaScript: **1,021 tests**. Final viewer client: **522 tests**.
- Repository policy: **126 tests, one skip**. Documentation check, canonical
  bundle, bundle freshness and release-version checks passed.
- A clean installed wheel matched **223 payload files** to source. Fresh
  workers recorded cold misses, disk hits after restart and disabled misses,
  all with identical saved STEP bytes. After removing source and model/output
  indexes, inspection, native STL export, a visually checked PNG snapshot and
  artifact-only viewer routes succeeded. `pip check` passed without VTK,
  matplotlib or the full OCP distribution. See the
  [installed-wheel record](FOLLOWON-WHEEL-20260911.md).

Logs are under `/private/tmp/cadgen-followon-20260911` for this session. Reports,
small raw results and reusable benchmark harnesses are committed; generated CAD,
screenshots, environments and caches are not.

## Dependency size and FreeCAD comparison

The matched OCP-provider download closure falls from **184.09 to 59.41 MiB**
(68% smaller). The clean required Python dependency closure occupies 623.83 MiB.
The earlier development environment used about 1.07 GiB, but different resolved
versions prevent an exact whole-environment comparison. VTK alone accounted for
about 591 MiB there. These are packaging measurements, not startup/RAM/modeling
speed claims. See the [dependency audit](DEPENDENCY-AUDIT-20260911.md).

The earlier headless FreeCAD reference on the same nine-part STEP replaced one
known object's shape in an already-loaded document: **6.43 ms** geometry
edit/recompute, **0.042 ms** placement update, and **4.15 ms** changed-part mesh
generation measured separately. Whole-assembly STEP export still took about
**222 ms**, followed by **208 ms** to read it back. FreeCAD 1.1.1 used OCCT 7.8.1
and Python 3.11.14; cadgen used OCP 7.9.3.1.1 and Python 3.13.13. These are not
equal engine-version or end-to-end browser comparisons.

Cadgen now adopts more of the useful mechanisms: reusable computations,
unchanged component references, display deltas and preview delivery before
saving. It still executes the parent Python model, validates and publishes
portable canonical data, reconstructs private native shapes, and delivers data
to a browser. FreeCAD's already-resident known-object update avoids much of that
work. Headless OCCT does not force the remaining architectural gap.

This increment does not establish full FreeCAD parity. The earlier arbitrary
monolithic nine-part model's roughly 500 ms preview remains its last observation
against a 250 ms target. The new decorated nine-part local-edit case reaches
140 ms, but it is a different workload and cannot retroactively satisfy that
test. Whole STEP serialization and cold unique geometry also remain substantive
work. The native-mesher experiment remains deferred after worse complete
extraction costs; no unsupported meshing speedup is claimed.

The broader branch's previous before/after results are preserved in the
[summary](SUMMARY-20260911.md) and its linked checkpoint reports.
