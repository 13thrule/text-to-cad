# Small component extraction batches — 2026-09-10

Fresh extraction processes dominate the cost of small empty-cache builds.
On the nine-part fixture, extracting the same private BREP payloads in the
already imported root process took 726 ms; starting four extraction workers,
performing the work and shutting them down took 3,127 ms.

| Workload | Components | BREP bytes | Serial median ms | Fresh four-worker median ms |
| --- | ---: | ---: | ---: | ---: |
| Nine-part planetary assembly | 9 | 393,300 | 726.13 | 3,127.00 |
| Nine parts plus curved corpus | 16 | 427,430 | 764.82 | 3,140.06 |
| Nine-part payloads repeated twice | 18 | 786,600 | 1,465.81 | 3,309.49 |
| Authored nine-part source result | 9 | 608,098 | 391.51 | 3,070.29 |

Two samples per schedule were taken in alternating order, with other workers
paused. The root kernel was imported before timing. Pool timing includes
process creation, worker imports and shutdown; output hashing is outside
the timer. These are extraction-stage measurements, not complete model-build
timings. The doubled workload repeats payloads for a bounded scaling check;
it is not a separately modeled 18-part fixture.

Every BREP and SURF output is byte-identical across all four runs of each
workload. The [raw report](results/component-extraction-crossover-20260910.json)
contains all 12 trials, output hashes, input hashes and the exact temporary
probe source. The measured runtime fingerprint is
`e9ac022fc868e9f4e557bd7da8175ad992a5b74dd022b163979342d2353776a3`,
preserved at commit `ff6ff1679`.

The first three rows use saved STEP-derived geometry. The authored source
result contains 608,098 BREP bytes, so the initial 512 KiB cutoff covered
only the canonical document half of a cold build. The final row measures
that exact authored workload in a second isolated window, after discarding
an earlier potentially contended run. Serial samples were 399.86 and
383.15 ms; four-worker samples were 3,043.78 and 3,096.80 ms. All BREP/SURF
output hashes match across the four trials. The [authored raw report](results/component-authored-extraction-crossover-20260910.json)
records the source tree, each input digest and every output digest; the
input tree comes from the first run of
[the 512 KiB cold-build checkpoint](results/warm-after-small-batch-20260910.json.gz).

The revised default component scheduler uses the existing serial path for batches
of at most **768 KiB of serialized BREP**. This conservative cutoff also
covers the authored nine-part workload. Larger or unknown batches keep the
existing CPU/work-count policy and memory cap. BREP size is a work estimate;
these observations do not establish a universal crossover for every surface
type or machine. Explicit `CADGEN_COMPONENT_WORKERS` values retain their
existing meaning and work-count/memory limits, including an explicit request
to spawn workers for a small batch.

Both paths reconstruct private shapes from the same BREP bytes and invoke
the same extraction function. The change adds no persistent pool and changes
no geometry, output format, cache key, error handling or progress phases/counts.
Warm component hits do not perform extraction. Existing daemon accounting
continues to count the parent and any extraction descendants.

The initial 512 KiB focused 41-test batch passed, including an actual two-process comparison
of tree/SURF/BREP bytes, per-face colors, unchanged caller BREP bytes, override
semantics and memory caps. It also includes the existing document packaging,
component appearance and daemon memory suites. The scheduling source
fingerprint at that initial checkpoint is
`b0a4ebc3c8b564817c07f7524fb7190f6bb0817b33b9e7342d87bd67a7085e97`.

The final 768 KiB boundary and explicit-worker parity tests also passed after
the saved-readback change. Two focused validation batches passed 50 tests
in 3.964 s and 19 tests in 24.489 s. They cover canonical document identity,
source-independent saved readers, exact readback cache hits versus forced
raw parsing, corrupt/missing object recovery, and the real serial/spawn
comparison. These validation durations are not performance measurements.

```sh
PYTHONPATH="$PWD/packages/cadgen/src" PYTHONDONTWRITEBYTECODE=1 \
  "$CAD_PYTHON" -m unittest \
  tests.python.packages.cadgen.test_component_worker_scheduling \
  tests.python.packages.cadgen.test_component_face_color_identity \
  tests.python.packages.cadgen.test_document_tree_packaging \
  tests.python.packages.cadgen.test_daemon_memory
```
