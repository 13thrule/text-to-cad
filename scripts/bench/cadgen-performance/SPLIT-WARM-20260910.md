# Split assembly warm-build comparison — September 10, 2026

The later [production sibling-preparation experiment](SIBLING-PREPARATION-20260910.md)
compares preparation enabled/disabled on the same `Compound(children=parts)`
fixture, with 44 calls and three unseen inputs per edit kind. Geometry completion
medians are 808.20 → 760.04 ms and previews 352.93 → 276.53 ms; placement preview
is effectively unchanged (179.24 → 179.66 ms, with no preparation). Both conditions
have large first-geometry stalls, retained in the report. Every actual STEP and
child pin check passes, but the 250 ms geometry-preview target remains unmet.
This separate same-runtime control does not replace the cross-version table below.

## Latest matched repeat/unseen study

The current checkpoint improves previously emitted edits but still regresses on
new values. The comparison below supersedes the earlier checkpoint:

| Complete call, median ms | BEFORE | AFTER | AFTER source preview |
| --- | ---: | ---: | ---: |
| Unchanged source | 22.46 | 16.64 | No new preview |
| Previously emitted geometry value | 574.20 | 453.56 | 254.51 |
| Previously emitted placement | 537.33 | 379.48 | 180.80 |
| New geometry value | 597.41 | 686.37 | 268.85 |
| New placement | 545.66 | 600.06 | 178.68 |

These are three observations per category, with three distinct inputs for
each new-value category. Every one of the 64 build calls succeeded, verified
its actual root and nine child STEP digests, and passed exact child-pin checks.
Geometry changes only the carrier pin; placement changes none. Current output
bytes match the monolithic current fixture for all nine variants. Original
split bytes differ because of older child representation; the earlier
directed volume comparisons remain the geometry evidence.

New geometry/placement values are 14.9% / 10.0% slower than the original,
compared with 31.0% / 17.4% in the preceding checkpoint. Removing an unused
freshness traversal and sharing immutable import syntax within one closure
calculation reduce repeated graph work. Geometry previews remain above 250 ms;
both placement medians meet that target. The source-result protocol's correctness
is separately established by blocked-child-save and exact-pin tests. The
[stage profile](results/split-stage-profile-20260910.json.gz) is nested attribution,
not an additive breakdown or an unprofiled benchmark.

Both revisions use two job slots and no spare daemon workers. Timed calls ran
without other task builds or browser work in separate frozen-runtime windows. Sources and timestamps were
restored, archive source/module provenance was checked, and both owned daemons
stopped successfully. Current runtime fingerprint:
`f28ff6af1be5d901aaff6006843a1268516ccfccea2bc41b1630b64823028150`.

[Original](results/planetary-split-before-novel-final-20260910.json.gz),
[current](results/planetary-split-after-closure-final-20260910.json.gz),
[daemon and output proof](results/planetary-split-daemons-closure-final-20260910-after.json),
[current split/monolithic identity proof](results/final-closure-pipeline-output-proof-20260910.json).

## Earlier 512 KiB extraction checkpoint

The current split fixture returns unchanged results faster, but its explicit
geometry and placement builds are about 30% slower than the reviewed baseline.
Its median placement preview is 244 ms; the geometry preview is 340 ms and
misses the 250 ms target. This study does not establish an early-child-result
speedup.

| Three measured samples per edit | BEFORE completion, ms | AFTER completion, ms | AFTER source preview, ms | AFTER saved publication, ms |
| --- | ---: | ---: | ---: | ---: |
| Unchanged | 28.91 | 16.55 | No new preview | No save |
| Carrier diameter 105 → 106 mm | 588.81 | 765.38 | 340.05 | 754.85 |
| Carrier placement 0 → −0.5 mm | 527.98 | 685.91 | 244.17 | 675.22 |

Values are medians. Completion ranges are 587–596 ms before and 740–813 ms
after for geometry, and 520–805 ms before and 668–697 ms after for placement.
Three samples establish a small matched observation, not a stable latency
distribution. BEFORE has no source-result, preview or saved-publication event;
its missing event times remain null.

The nine ordinary `@step` children each declare a real STEP output. The root
submits every child before accessing geometry; only the carrier owns the
diameter, and the root owns its placement. Both revisions use
`CADGEN_JOBS=2` and `CADGEN_DAEMON_SPARES=0`: two active job slots, with a
resident worker bound to each requested child model. The observed peak is one
active child job because these warm edits rebuild only the carrier. Kernel
startup and priming are excluded from measured calls; child IPC and every
declared save are included.

On AFTER geometry edits the carrier's median final source result arrives at
121.99 ms, its save at 145.06 ms and terminal event at 146.46 ms. BEFORE's
carrier terminal event arrives at 95.03 ms. The new source result precedes its
own save by about 23 ms, but the root preview follows that child save in all
three measured samples. This fixture therefore does not demonstrate a preview
arriving before child persistence finishes. The blocked-export regression
tests establish that scheduling behavior separately.

The root's median logged STEP assembly and read-back stages remain roughly
125 and 254 ms on AFTER. Its source preparation, canonical document packaging
and private child materialization add work beyond the older pipeline. These
rounded, nested stage logs locate costs; they are not additive profiler
measurements.

[BEFORE raw results](results/planetary-split-before-final-20260910.json.gz),
[AFTER raw results](results/planetary-split-after-final-20260910.json.gz) and
[daemon/source/output proof](results/planetary-split-daemons-final-20260910.json)
retain all 40 calls, including priming and restorations, per-child milestones,
pins, output digests and operation counts. Every call succeeds and satisfies
the child-pin assertions: geometry changes exactly the carrier pin, placement
changes none. All nine final child STEP byte hashes match their records for
each revision. Source bytes and timestamps are restored, input closures stay
unchanged, both owned daemons exit successfully, and no task build, browser
load, test or runtime edit overlaps the timed window, 17:59:41–18:00:17 UTC.

BEFORE uses the unchanged `7aa3e85be76f305437abd3d7aba26e38b28e43cb` archive,
fingerprint `cd405009b4828ccdf1edc4f555ed6ad75f6db8f59f6a25ce36fdaad245daab54`.
AFTER uses fingerprint
`b0a4ebc3c8b564817c07f7524fb7190f6bb0817b33b9e7342d87bd67a7085e97`, including
the 512 KiB cold-extraction scheduling crossover. Both fingerprints remain
fixed throughout their runs; loaded cadgen module paths are checked against
the selected revision.

The current restored STEP is byte-identical to the validated monolithic
fixture: SHA-256
`406dd2e19b6a4ea3a623abd19b03708b7d9e97b4402ba4161c737eb31f10fdca`.
BEFORE's split STEP has a different identity because its older child-result
serialization changes all nine component IDs. The retained
[baseline geometry check](results/planetary-split-before-geometry-20260910.json)
finds zero directed symmetric-difference volume for every part in both
directions; the raw identity mismatch remains recorded. This is a comparison
of the same split authoring structure across runtime semantics, not a claim
that the two STEP byte streams match.

The frozen `warm_build.py` and archived `bench/split_warm_build.py` run with
`--iterations 3 --assert-child-pins --skip-imports`,
`--geometry-model <src>/carrier_plate.py`, placement substitutions
`CARRIER_OFFSET_Z = 0.0` → `CARRIER_OFFSET_Z = -0.5`, and separate owned
`--child-daemon-socket` addresses. Exact commands, environment and daemon
identities are in the proof above; the fixture setup is documented in the
[benchmark README](README.md#the-same-assembly-split-into-child-models).
