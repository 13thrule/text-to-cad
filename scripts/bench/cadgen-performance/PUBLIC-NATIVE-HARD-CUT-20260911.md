# Public native geometry/read validation

The nine-part planetary public paths benefit from deferred SURF: median cold
`read_step` fell from 1,180 to 407 ms, and placement edit/write/public readback
from 1,441 to 615 ms. Completing every display surface afterward increased the
combined totals by 5–10%. Current CLI compile also regressed. These results
support faster native editing/readback; they do not establish faster first
display or eliminate surface extraction.

| Public boundary | Before median [range], ms | After median [range], ms | Median change |
|---|---:|---:|---:|
| Empty-store public read, including compile IPC and private reconstruction | 1,179.9 [1,169.2–1,250.1] | 406.7 [381.0–411.1] | −65.5% |
| Current public read, compile forbidden | 28.9 [27.9–29.5] | 23.8 [22.9–27.8] | −17.5% |
| Placement edit + STEP write + public saved readback | 1,440.8 [1,408.1–1,485.1] | 614.6 [600.7–654.2] | −57.3% |
| Empty-store CLI compile | 1,278.5 [1,271.6–1,392.2] | 486.6 [482.3–491.0] | −61.9% |
| Current CLI compile | 138.8 [134.1–141.6] | 195.3 [191.1–205.8] | +40.7% |
| Forced CLI compile | 1,259.7 [1,251.4–1,322.3] | 487.1 [481.0–508.0] | −61.3% |
| Empty-store public read + all nine SURFs ready | 1,200.6 [1,188.9–1,268.9] | 1,317.9 [1,280.2–1,380.1] | +9.8% |
| Placement edit/write/readback + all saved SURFs ready | 1,461.8 [1,429.1–1,504.6] | 1,536.2 [1,488.5–1,584.9] | +5.1% |
| Forced CLI compile + all nine SURFs ready | 1,280.6 [1,273.1–1,342.9] | 1,404.5 [1,396.2–1,475.8] | +9.7% |

Each combined observation is the sum of its own measured phases; the table
uses the median of those sums. The separate SURF phase was 19.96 ms before
versus 910.58 ms after for input, 20.57 versus 908.71 ms for saved output, and
20.95 versus 914.93 ms after forced compile. The before condition had already
extracted SURF in its native phase and only verified readiness afterward.
The after condition performed real typed, artifact-only pool requests. These
phase timings are different boundaries, so their ratio is not a mesher
speed comparison. This study includes no TESS, browser, rendering or selector
latency. The edit copied the public native result, moved only `carrier_plate`
by 0.5 mm, used the canonical STEP writer, then called public `read_step`;
it was not a decorated-source rebuild measurement.

Eight measured samples ran serially in ABBA/BAAB order, four per condition,
at 04:00:47.894–04:01:40.458 UTC on September 11. One complete warm-up per
condition passed and remains in the evidence. The pre-cut 183-file Python
runtime was the immutable private baseline from the core study; the candidate
was a fresh 187-file copy of the integrated runtime. Their complete source
manifests matched before/after, and candidate bytes matched the working tree.
The input STEP digest was
`406dd2e19b6a4ea3a623abd19b03708b7d9e97b4402ba4161c737eb31f10fdca`.

Both callers and daemon kernels were resident before warm-up. Caller imports
cost 2,561/2,318 ms and daemon readiness 3,419/2,952 ms, excluded from the phase
timers. Each sample used fresh disk stores. Caller op/native memos were cleared
outside timing; daemon-internal RAM remained warm. Matching 2,048 MiB pool and
worker reservations, zero dependency reservation and one component worker
kept one warm worker per daemon instead of replenishing borrowed workers.
That is a constrained one-worker policy, not a default multi-worker throughput
measurement. Every phase checked idle state and unchanged daemon/worker PIDs
and import count outside timing; the largest observed readiness check/wait
was 71.6 ms. CLI phases include each CLI process's startup and public dispatch.

The ten-logical-CPU host was shared. Observed load averages ranged
5.11–6.07 / 10.63–11.54 / 13.47–13.94. Recent `ps` CPU percentages included
unrelated Chrome/Codex/WindowServer and Python processes reaching 65–93% of a
core. The aggregate process percentages ranged 234–449%; these snapshots are
averages, not an uncontended-host utilization guarantee. No unrelated process
was stopped and no sample was discarded or retried. Small differences and
regressions need attribution before further optimization.

All warm-up and measured rows passed exact cross-condition BREP/SURF object
bytes, private native STEP serialization, saved/reconstructed STEP bytes,
face/edge counts, nine occurrences, placements, names, intrinsic/occurrence
appearance, bounds and hierarchy checks. Native trees were complete before
any candidate surface index existed. Cold/current/force compiled the same
tree within each condition; only the current call skipped. Surface artifact
jobs left code-side indexes unchanged. The saved geometry's canonical
component bytes can differ from the original imported document after native
serialization; exact parity was checked between conditions at each boundary.
All six owned caller/daemon/worker PIDs exited, confirmed by process census;
cleanup finished at 04:01:42.592 UTC.

The [compact evidence](results/public-native-hard-cut-summary-20260911.json.gz)
retains every sample and warm-up, phase/readiness/host observations, exact
source manifests, helper/design bytes and parity fingerprints. Its raw report
is preserved unchanged in the [lossless raw archive](results/public-native-hard-cut-measurement-20260911.json.gz)
(108,086,016 bytes; SHA256
`c42e34f8503bfc9986292288171940b9d9c202f9f7b5cb87126e766074117587`).
The 108 MB raw report compresses to 3.33 MB; its full daemon status snapshots
account for most of the repetition. Current CLI overhead was subsequently
traced to three full closure captures per imported hit. A call-local snapshot
correction is a separate follow-up to this measured checkpoint; these timings
must not be relabeled as measurements of that later change. The extra surface
boundary remains a tradeoff, not a demonstrated first-display improvement.
