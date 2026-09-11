# Warm edits and the FreeCAD comparison

New edits to an imported STEP complete about 15–30% faster in the matched backend
study. Returning to an already-built value is faster again because the emitted
STEP bytes can reuse their verified canonical readback. Full procedural model
edits are about 1–2% slower in this window; new edits to the split-model fixture
still regress by about 10–15%. These are distinct workloads, and the cached-output benefit must not be
presented as the latency of every new edit.

## Matched study and boundaries

Apple M1 Max, 10 logical CPUs, 64 GiB RAM, macOS 26.5.1. The reviewed original is
`7aa3e85be76f305437abd3d7aba26e38b28e43cb`. The full matched study uses
fingerprint `f28ff6af1be5d901aaff6006843a1268516ccfccea2bc41b1630b64823028150`:
source/document schema 3, operation-cache salt 6, exact-output readback reuse,
private native ownership, the 768 KiB extraction cutoff, SURF recipe reuse,
call-scoped import syntax and removal of an unused freshness traversal. Browser worker code
was under development but frozen and unused during these STEP-only studies.

Later commit `a862c3d1e` moves the op cache to scheme 7, binding disk reuse to
actual OCP/distribution versions and enforcing the existing RAM entry limit on
disk hits. The tables below retain their original measured runtime and cache
state; they are not a fresh benchmark of that compatibility cutover.
The later [interleaved bounds study](DEFERRED-ASSEMBLY-FEASIBILITY-20260911.md#final-private-implementation-and-comparison)
compares three private variants with identical scheme-7 operation caching.
Its integrated candidate improves split-model preview medians from
221/191/235/186 ms to 206/164/215/161 ms for repeated geometry, repeated
placement, new geometry and new placement respectively. Complete saves are
approximately neutral for repeated geometry and 6–23 ms lower in the other
categories. All 96 calls and 32 cross-condition output/pin comparisons pass.
These are small, interleaved samples with imperfectly balanced order; they do
not retroactively change the original-versus-current tables below or establish
a procedural-model speedup. Newly emitted STEP bytes still require readback.

Every study starts with a fresh private store. Python and OCCT are already
imported; source writes, initial kernel import, browser transport and rendering
are outside the timer. Complete-build timing includes every declared STEP save.
The split fixture additionally includes child IPC through its own two-slot
warm daemon. No task tests, browser loads, builds or runtime edits overlap the
measured windows. Reports verify loaded runtime paths, source restoration,
unchanged runtime fingerprints, actual output bytes and exact child pins.

Repeated rows are medians of three returns to a primed value (106 mm diameter
or −0.5 mm placement), with baseline restoration between calls. Unseen rows
summarize three distinct values, each used once: diameters 107/108/109 mm or
placements −0.6/−0.7/−0.8 mm. All six produce STEP digests not emitted earlier in
the study. They are not three repetitions of one unseen edit, so their median
is a compact workload summary rather than a latency confidence interval.

## Complete builds

Milliseconds, including STEP persistence:

| Task | Original | Current | Current preview ready |
| --- | ---: | ---: | ---: |
| Procedural model, unchanged | 18.81 | 15.97 | No rebuild |
| Procedural model, repeated diameter | 1,020.17 | 688.56 | 482.75 |
| Procedural model, repeated placement | 939.14 | 686.37 | 482.92 |
| Procedural model, unseen diameter | 942.94 | 952.15 | 506.83 |
| Procedural model, unseen placement | 930.48 | 951.36 | 496.18 |
| Imported STEP, unchanged | 15.70 | 11.34 | No rebuild |
| Imported STEP, repeated diameter | 867.91 | 387.67 | 140.09 |
| Imported STEP, repeated placement | 855.15 | 421.54 | 167.87 |
| Imported STEP, unseen diameter | 926.84 | 649.98 | 153.22 |
| Imported STEP, unseen placement | 869.47 | 742.61 | 194.59 |
| Split model, unchanged | 22.46 | 16.64 | No rebuild |
| Split model, repeated diameter | 574.20 | 453.56 | 254.51 |
| Split model, repeated placement | 537.33 | 379.48 | 180.80 |
| Split model, unseen diameter | 597.41 | 686.37 | 268.85 |
| Split model, unseen placement | 545.66 | 600.06 | 178.68 |

Preview times are backend publication events, not visible browser frames.
The original has no early-preview event; complete-save time is not a substitute
for an unobserved first-frame time. The **250 ms procedural preview target
remains unmet**. Imported edits meet the backend target; both placement
medians meet it for the split fixture, while geometry remains above it. The split regression remains
an implementation target, not a completed optimization.

The original procedural repeated-diameter samples span 913–1,500 ms, versus
674–702 ms currently. Current unseen placement spans 947–960 ms. All samples
remain in the reports; the small sample counts and those outliers limit exact
speedup claims. Earlier checkpoints measured original procedural builds near
840 ms and current builds near 854 ms before readback reuse. Those observations
remain valid for their recorded runtime and timing window. The preceding current
checkpoint measured unseen procedural saves at 864 / 839 ms, compared with
952 / 951 ms here. The exact output bytes still match; these separate windows
do not establish that the syntax change caused that variation. The split
fixture improved from 782 / 641 ms in that checkpoint to 686 / 600 ms here.
A separate interleaved syntax-only probe measured closure calculation at
24.48 → 10.28 ms with identical closure results.

All nine actual STEP variant digests match between original and current in
each monolithic and imported study. Current split outputs also match the
current monolithic outputs for all nine variants. Original split output bytes
differ because of its older child-result representation; the retained baseline
geometry check finds zero directed difference volume for all nine parts.

Raw reports: [procedural original](results/mono-before-unseen-final-20260910.json.gz),
[procedural current](results/mono-after-unseen-closure-final-20260910.json.gz),
[imported original](results/imported-before-unseen-final-20260910.json.gz),
[imported current](results/imported-after-unseen-closure-final-20260910.json.gz),
[split original](results/planetary-split-before-novel-final-20260910.json.gz),
[split current](results/planetary-split-after-closure-final-20260910.json.gz),
[split/monolithic byte proof](results/final-closure-pipeline-output-proof-20260910.json).
The [imported fixture report](IMPORTED-STEP-20260910.md) verifies the eight
untouched parts retain exact native topology, names and colors.

## Where the time goes

### Later split-only checkpoint, September 11

A [new frozen-runtime comparison](results/split-frozen-siblings-summary-20260911.json)
includes the bounded sibling preparation in `2709968dc`, using the same nine-part
source against `7aa3e85be`. It runs 32 calls per version in fresh private stores.
All calls, declared saves, exact child pins, source restoration and runtime
checks pass. All nine output variants match the bytes in each version's earlier
study. The current archive verifies 451 runtime files, so concurrent viewer
implementation cannot affect the executed backend.

| Split workload, milliseconds | Original in this window | `2709968dc` | Preview ready |
| --- | ---: | ---: | ---: |
| Unchanged | 25.45 | 16.47 | No rebuild |
| Repeated diameter | 759.47 | 420.07 | 227.52 |
| Repeated placement | 712.61 | 413.16 | 183.11 |
| New diameter | 691.81 | 950.01 | 267.40 |
| New placement | 802.77 | 674.77 | 232.69 |

This window does **not** close the new-geometry regression. It also does not
isolate the cause of the larger timing variation: new current geometry saves
range from 751.59 to 999.85 ms, with source publication, native model execution,
STEP assembly and readback each showing different outliers. Other agents in
this task paused CPU work, but user activity and unrelated host processes were
not controlled. This sequential comparison is not an interleaved causal test.
The three new values remain distinct inputs, not latency confidence intervals.
It supplements the earlier full comparison rather than replacing its other
workloads or establishing a precise isolated sibling-preparation speedup.

### Stage attribution from the earlier full comparison

Rounded logged medians below are nested stage observations, not additive
profiler totals. Geometry / placement values are shown in that order.

| Stage | Original procedural | Current repeated | Current unseen |
| --- | ---: | ---: | ---: |
| Python model body | 428 / 433 | 376 / 370 | 387 / 379 |
| Source preparation + publication | Absent | 9+23 / 9+23 | 9+30 / 9+24 |
| STEP assembly and write | 140 / 132 | 130 / 125 | 131 / 134 |
| STEP readback | 259 / 259 | 26 / 28 | 260 / 270 |
| Canonical document publication | Different older path | 32 / 32 | 38 / 35 |

The exact-output cache saves roughly 0.23 seconds of readback only when those
STEP bytes have been seen before. New outputs still pass through the native
STEP reader and authored-to-saved correspondence checks. Imported model bodies
improve from about 272–300 ms to 30–60 ms by reusing their input's canonical
BREP. Arbitrary procedural Python still reruns at the decorated model boundary.

Three diagnostic profiles locate that remaining body cost. The
[operation profile](results/mono-body-profile-summary-20260910.json) attributes
only 8.5 ms to three unmemoized booleans in one new-value body. The
[context profile](results/mono-context-profile-20260910.json.gz) puts most work in
build123d's `_add_to_context`, which enumerates shapes and computes before/after
selections even when the model never reads `Select.LAST`. Constructing the five
polygon wires takes only 2.3 ms; caching that factory would not address the main
cost.

A separate [enumeration profile](results/mono-enumeration-profile-20260910.json)
measures three unchanged, warmed body calls with identical BREP digests and
unchanged source/runtime hashes. Its median instrumented body is 383.9 ms:
`Shape.get_shape_list` accounts for 123.1 ms including 30.0 ms of native
enumeration; live signature hashing takes 67.0 ms and full signature comparisons
40.6 ms. These are nested, instrumented attribution figures, not additional save
costs or an unseen-edit speedup. Reusing mutable native identities between calls
would invalidate cache-state equivalence. A future context optimization must
preserve the builder's actual selection and native-mutation semantics.

## Cold builds and public imports

These are single empty-store observations, with kernel import already complete:

| Task | Original ms | Current ms |
| --- | ---: | ---: |
| Empty-store procedural build | 6,778.14 | 2,598.81 |
| Empty-store imported-model build | 6,892.95 | 6,199.21 |
| First public STEP read in an empty store | 256.56 | 4,200.79 |
| Repeated public STEP read, median of three | 257.60 | 31.19 |

Small extraction batches avoid new interpreter pools. The first public read
has a real regression: current code compiles and publishes canonical artifacts
through the build pool, including worker startup, while the old reader only
parses text STEP in its existing process. Later current reads forbid compile
submission and reconstruct binary objects. The old reader still parses STEP
on every call, even when compile submission is forbidden. This is not a
claim that cold import improved or that an already-resident daemon has the
same startup cost as this transient-process study.

The later [raw compilation cleanup](COLD-COMPILE-CLEANUP-20260911.md) removes
unused workspace discovery, adaptive classification and compound construction.
Its resident-interpreter nine-part compile median moves from 1,094.86 to
1,079.46 ms; no daemon IPC or fresh interpreter startup is included. All 36
calls preserve exact canonical outputs. This does not revise the public-read
table above. Measured surface extraction still takes about 758 ms and STEP
parsing about 255 ms, motivating a separate geometry/display publication review.

## FreeCAD on the same STEP

[The FreeCAD report](results/freecad-final-20260910.json) uses FreeCAD 1.1.1,
OCCT 7.8.1 and its bundled Python 3.11.14. Cadgen uses build123d 0.11.1,
OCCT 7.9.3.1.1 and Python 3.13.13. Both run headlessly on the same machine
and use the same 2,268,663-byte input, SHA-256
`406dd2e19b6a4ea3a623abd19b03708b7d9e97b4402ba4161c737eb31f10fdca`.
The FreeCAD medians use five measured samples after priming, in a private
document that retains the eight unchanged parts.

| FreeCAD stage | Diameter edit ms | Placement edit ms |
| --- | ---: | ---: |
| Change the retained part and recompute | 6.43 | 0.042 |
| Generate a new mesh of the changed part, separately | 4.14 | 4.16 |
| Export the whole assembly to STEP | 222.41 | 221.74 |
| Read the exported STEP back | 207.45 | 208.30 |

The initial FreeCAD STEP import took 365.58 ms; peak whole-process RSS was
135.78 MiB, including imports and all samples. A placement edit can retain
triangles; the separately measured mesh extraction is not required to move a
retained display object. Mesh tolerances here are explicit but are not a
matched-quality comparison with cadgen. See the [meshing study](MESHER-V2-20260910.md)
for that separate experiment.

FreeCAD retains document objects and recomputes touched features. Its view
providers retain display nodes and expose separate transformation and visual
update paths. Those are architectural advantages for local edits.
[Document API](https://freecad.github.io/SourceDoc/d8/d3e/classApp_1_1Document.html),
[Part view provider](https://freecad.github.io/SourceDoc/d6/d68/classPartGui_1_1ViewProviderPartExt.html).

Cadgen now retains unchanged browser components, caches imported geometry,
publishes source results before saving, and lets parents consume completed
child geometry before child STEP persistence. Arbitrary Python still executes
at its decorated model boundary. Fresh private kernel materializations and
native mutation checks preserve equivalent behavior after cache loss and
prevent one consumer from changing another's geometry.

The remaining gap is primarily execution granularity and ownership, plus
browser transport and memory management. **Headless OCCT does not impose that
gap:** the FreeCAD measurements themselves are headless. This study measures
neither FreeCAD GUI frame latency nor a matched large-assembly browser/FreeCAD
rendering comparison, and it does not claim complete FreeCAD parity.
