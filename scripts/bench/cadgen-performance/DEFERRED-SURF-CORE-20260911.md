# Geometry publication before surface derivation

The bounded feasibility study supports separating editable geometry from display
surfaces. On the nine-part planetary assembly, native read/publication and
edit/save/readback became substantially faster. Preparing every display surface
afterward still costs about the same total time. This is a resident core study;
it is not a public CLI, build-pool, or browser timing measurement.

Production integration is underway. The store keeps immutable objects and atomic
input indexes. Model authors still use ordinary geometry and decorators.

## Matched measurements

Two private resident interpreters compared the previous eager implementation
with the corrected geometry-only prototype. Four ABBA blocks produced 16 timed
calls, eight per implementation, after two untimed warmups. Each call used a
fresh store and cleared native/operation RAM state outside the measured region.
Component concurrency was one. Interpreter/kernel preloads of 2.31 and 2.24 s
were outside all timings.

The input was the existing 2,268,663-byte nine-part planetary STEP, SHA-256
`406dd2e19b6a4ea3a623abd19b03708b7d9e97b4402ba4161c737eb31f10fdca`.
No tendon-hand assembly or component was tested.

| Resident operation | Eager baseline median | Deferred candidate median |
|---|---:|---:|
| Cold native read and canonical publication | 1,126 ms | 342 ms |
| Warm private native reconstruction | 28.0 ms | 17.5 ms |
| Placement edit, STEP save and canonical readback | 1,295 ms | 522 ms |
| Subsequent input surface preparation | 19 ms | 836 ms |
| Subsequent saved-output surface preparation | 20 ms | 822 ms |
| Cold input through all surfaces ready | 1,146 ms | 1,180 ms |
| Edit/save through all output surfaces ready | 1,315 ms | 1,353 ms |

The final two rows are medians of each call's combined duration, not sums of
stage medians. Native cold work fell about 70%; edit/save/readback fell about
60%. Combined surface readiness was about 3% slower. Extraction moved off the
native path; it did not disappear. The placement edit moved the carrier by
0.5 mm and saved a new STEP, rather than mutating an already retained display.

All 16 calls preserved exact component BREP/SURF bytes, occurrence order and
transforms, colors, private native results and saved-document reconstruction.
Both owned workers exited successfully. Timing ran from 02:59:48 to 03:00:36 UTC
on September 11. This small interleaved study supports the architectural change,
not a latency guarantee for arbitrary inputs.

## Serialization acceptance

An initial warmup exposed inconsistent canonical ordering of numeric face-color
keys. No timed sample was collected from that failure. Canonical serialization
now converts keys to strings before sorting and rejects colliding spellings;
the corrected prototype passed 29 checks before the measurement.

The native codec gate preserves the existing binary-v4 path for ordinary
point-free geometry. Actual pathological point representations require explicit
binary-v3 or ASCII-v3 recovery. A separate exact point-record guard accepts
healthy v4 representations without overlooking the reproduced point/UV faults.
The recommended combined helper passed 20 comparisons. That later guard was
not timed here; all nine measured components take the unchanged point-free path.
No unconditional v3 fallback or approximate native-fidelity comparison was used.

## Evidence and remaining acceptance

- [Per-call raw measurements](results/deferred-surf-core-measurement-20260911.json.gz)
- [Summary, paired deltas, source hashes and cleanup](results/deferred-surf-core-summary-20260911.json)
- [Corrected native/geometry proof](results/deferred-surf-core-proof-20260911.json)
- [Preserved failed warmup](results/deferred-surf-failed-warmup-proof-20260911.json)
- [Exact point-record investigation](results/native-point-codec-proof-20260911.json)
- [Recommended combined codec proof](results/native-point-codec-combined-20260911.json)

The raw measurement SHA-256 is
`2035c56615633c98ed5d62772c1dfe3559e6e53236893b191a84541066fe7a15`.
The compressed-evidence manifest verifies both original and archived bytes.

The production cut adds typed pooled artifact jobs, deferred SURF requests,
TESS-v4 metadata admission and exact output identities across Python, Node and
the browser. Those layers still require integrated package, installed-wheel,
source-free export and moderate browser acceptance before their performance can
be reported. The resident figures above must not replace earlier public timings
or be compared directly with FreeCAD's retained edit/recompute latency.
