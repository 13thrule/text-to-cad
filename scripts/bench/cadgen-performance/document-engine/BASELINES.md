# Frozen baseline record

This record distinguishes existing trustworthy observations from runs produced
by the P0 harness. It does not invent percentile or memory evidence.

## Larger-model checkpoint

The [118-occurrence iris comparison](IRIS-20260913.md) at frozen `408e7c8b9`
passes all 24 measured saved-file geometry checks but fails the performance
gate. Old/replacement medians are 19.407/26.005 s cold, 0.076/6.224 s unchanged,
6.144/9.784 s for a mounting-hole edit and 7.310/9.725 s for placement. Three
samples per scenario establish observed medians and ranges, not p95. The
report records desktop interference, stage boundaries and raw evidence hashes.
Live provider-check overhead is the immediate optimization target; this result
does not support extrapolating the small-fixture wins to larger assemblies.

## Historic serial source-command evidence

`../FULL-REVIEW-20260912.md` measured public `python model.py --json` from
process start through exit, including IPC, declared STEP save and required
verification. The runs were serial apart from ordinary desktop activity, used
one cold sample and three warm samples, and paired byte-identical source and
STEP output across main and the optimized branch.

| Historic fixture | Boundary | main `3e4dfdeef` | optimized code at `18cc312ce` |
| --- | --- | ---: | ---: |
| Drilled plate | empty-store command | 6.278 s | 3.375 s |
| Drilled plate | unchanged warm median | 2.705 s | 0.118 s |
| Drilled plate | geometry-edit warm median | 2.690 s | 0.191 s |
| Drilled plate | placement-edit warm median | 2.679 s | 0.190 s |
| 24 drilled plates | empty-store command | 5.139 s | 2.637 s |
| 24 drilled plates | unchanged warm median | 2.609 s | 0.112 s |
| 24 drilled plates | geometry-edit warm median | 2.696 s | 0.257 s |
| 24 drilled plates | placement-edit warm median | 2.687 s | 0.259 s |

These are historical observations for closely matched workloads. One cold and
three warm samples do not establish p95. They do not include edit-to-complete
browser presentation, stage counters, or fixture-specific peak/settled memory.
They therefore anchor regression review but do not alone pass the new contract.

Checkpoint `5c4a212ca` changes only documentation relative to `18cc312ce`; its
production runtime baseline is frozen to the same code. A 2026-09-13 functional
run exercised cold, unchanged, local-geometry and placement commands for both
fixtures. All saved-file geometry, source-hidden readback, stage capture,
side-effect and cleanup checks passed. It overlapped other native correctness
work, so its command times are explicitly noncomparable and are not reproduced
here.

The frozen through-hole corpus fingerprints are:

| Fixture | SHA-256 |
| --- | --- |
| `models/performance_document/plate.py` | `e7d092e8667b70c052f7c05219d2a1adbebecdc7daba08c15d49afc7e4621ec9` |
| `models/performance_document/assembly24.py` | `7af3554142d4aa97eb8bd719cee5657de204c7b5b7876164702625c50e08ea2a` |

## Matched in-process exploratory series

This blocked-order series predates equal cold setup accounting. Its warm rows
remain comparable because both workers were already initialized before the
measured calls. Its cold ratios are withdrawn: legacy installed its operation
witness and imported build123d before the timer, while retained paid its native
imports during the timed call. The raw rows and checksums remain frozen for
provenance, but the cold values below must not be compared with the corrected
boundary.

The 2026-09-13 reserved serial run used five cold samples and ten warm samples
per scenario. Both engines measured the full in-process `run_model_argv` call
through explicit STEP completion; process launch and controller IPC were
outside both boundaries. Frozen legacy `5c4a212ca` used production-default
operation, disk and whole-call caches. The retained candidate used internal
`DocumentService.activate()` with those legacy caches disabled. Every one of
the 70 measured saved-file rows passed cross-engine label, validity, volume,
area, bounds and topology-count parity. These sample counts support medians and
observed ranges, not p95.

Execution was blocked by engine rather than interleaved: the complete frozen
legacy series finished before the complete retained-candidate series, and the
FreeCAD reference followed those cadgen runs. No other planned native or
browser workload ran during the reserved window.

| Fixture / scenario | Legacy median | Retained median | Retained / legacy |
| --- | ---: | ---: | ---: |
| Plate cold (withdrawn) | 359.905 ms | 4,778.372 ms | withdrawn |
| Plate unchanged | 7.937 ms | 45.966 ms | 5.791x |
| Plate local geometry | 83.350 ms | 1,822.536 ms | 21.866x |
| Plate placement | 57.568 ms | 53.574 ms | 0.931x |
| Assembly24 cold (withdrawn) | 370.442 ms | 5,030.834 ms | withdrawn |
| Assembly24 unchanged | 10.639 ms | 390.337 ms | 36.690x |
| Assembly24 local geometry | 116.853 ms | 2,352.838 ms | 20.135x |
| Assembly24 placement | 104.643 ms | 384.211 ms | 3.672x |

The candidate's separately timed source/geometry interval and literal
transaction counters were stable across all samples in each row:

| Fixture / scenario | Source/geometry median | Computed | Reused | Native copies | Queries | Derived computed / reused |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Plate cold | 4,189.436 ms | 11 | 3 | 14 | 2 | 0 / 0 |
| Plate unchanged | 7.268 ms | 0 | 14 | 14 | 2 | 0 / 0 |
| Plate local geometry | 1,782.804 ms | 9 | 5 | 14 | 2 | 0 / 0 |
| Plate placement | 9.287 ms | 1 | 14 | 15 | 2 | 0 / 0 |
| Assembly24 cold | 4,149.704 ms | 11 | 3 | 14 | 2 | 0 / 0 |
| Assembly24 unchanged | 11.184 ms | 0 | 14 | 14 | 2 | 0 / 0 |
| Assembly24 local geometry | 1,936.599 ms | 9 | 5 | 14 | 2 | 0 / 0 |
| Assembly24 placement | 11.093 ms | 0 | 14 | 14 | 2 | 0 / 0 |

Frozen legacy does not expose equivalent document transaction counters, so its
counter and source/geometry fields are `null`; only the common full-call times
are compared.

On the comparable warm portion, the retained prototype missed the broad P1
performance target; only the plate placement median improved. The candidate source
tree remained unchanged during measurement at SHA-256
`8734a4adda8c3bd6892b0ca0dbaf66db181081c5cd3da4c99c148f66ea54fc39`;
the checked-out Git revision was `acb22f94e20edab787d472e53a969d55c59c6d73`.
The frozen legacy archive tree SHA-256 was
`a7e9c100320abaf27134bcff8f9b24ec60f20f5cf0434c530281f3254a69ed81`.

Observed process peak / two-second settled RSS was 487.6 / 488.6 MiB for the
legacy plate, 490.5 / 491.3 MiB for legacy Assembly24, 484.8 / 486.0 MiB for the
retained plate, and 514.8 / 515.8 MiB for retained Assembly24. These are
observations below the provisional service-tree ceilings, not new ceilings.

The retained transaction counters are literal `EvaluationStats`: `computed`
includes transforms and opaque captures as well as surface/boolean operations.
Likewise, `derived_computed=0` covers document-core derivations only and does
not instrument downstream exporter or viewer mesh work. The aggregate cannot
support a zero-modeling or end-to-end zero-remesh claim without classified
operator and downstream instrumentation.

The public source-command/daemon candidate path is not integrated. The
historical public CLI timings above therefore have no candidate ratio; moving
launch or IPC work outside the measured boundary is not accepted as a speedup.

## Paired equal-setup series

The corrected 2026-09-13 paired run used five cold samples and ten warm samples
per fixture/scenario. Each cold pair used fresh workers and alternated which
engine ran first. Each warm pair alternated first engine by whole persistent
scenario session; a warm session contains one unmeasured prime followed by ten
measured calls. The 32-entry chronological ledger in every report records that
actual order. No other planned native or browser workload ran during the
series.

The boundary identifier is
`in-process-run-model-argv-with-first-call-engine-setup-v2`. Cold
`processExitMs` begins before engine-specific setup and includes setup plus the
first complete `run_model_argv` call through explicit STEP completion. Warm
rows measure the complete call after the unmeasured prime. Common harness and
`run_model_argv` module imports, worker process launch, controller IPC, oracle
readback and report writing are outside both engines' timing boundary. The new
identifier prevents old unequal-setup reports from automatically producing
cold ratios against this series.

All 70 measured rows per engine passed saved-file validity, occurrence count,
volume, area, bounds and topology parity. Medians are observations from this
bounded series; there is no p95 evidence.

| Fixture / scenario | Legacy median | Retained median | Retained / legacy |
| --- | ---: | ---: | ---: |
| Plate cold | 3,058.810 ms | 2,970.885 ms | 0.971x |
| Plate unchanged | 8.525 ms | 40.468 ms | 4.747x |
| Plate local geometry | 79.592 ms | 87.802 ms | 1.103x |
| Plate placement | 57.155 ms | 49.378 ms | 0.864x |
| Assembly24 cold | 3,046.358 ms | 3,534.083 ms | 1.160x |
| Assembly24 unchanged | 14.033 ms | 209.599 ms | 14.936x |
| Assembly24 local geometry | 127.321 ms | 396.584 ms | 3.115x |
| Assembly24 placement | 100.505 ms | 373.095 ms | 3.712x |

The cold split is explicit rather than hidden. Legacy setup medians were
2,601.511 ms for plate and 2,583.069 ms for Assembly24, with corresponding
`runModelArgvMs` medians of 457.297 ms and 409.567 ms. Retained setup medians
were 8.182 ms and 8.225 ms, with call medians of 2,962.702 ms and 3,525.368 ms.
Those components sum to `processExitMs` apart from timer overhead.

The retained source/geometry medians and literal counters were:

| Fixture / scenario | Source/geometry median | Computed | Reused | Native copies | Queries | Derived computed / reused |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Plate cold | 2,385.564 ms | 11 | 3 | 14 | 2 | 0 / 0 |
| Plate unchanged | 8.183 ms | 0 | 14 | 14 | 2 | 0 / 0 |
| Plate local geometry | 38.361 ms | 9 | 5 | 14 | 2 | 0 / 0 |
| Plate placement | 9.236 ms | 1 | 14 | 15 | 2 | 0 / 0 |
| Assembly24 cold | 2,555.293 ms | 11 | 3 | 14 | 2 | 0 / 0 |
| Assembly24 unchanged | 10.707 ms | 0 | 14 | 14 | 2 | 0 / 0 |
| Assembly24 local geometry | 31.828 ms | 9 | 5 | 14 | 2 | 0 / 0 |
| Assembly24 placement | 10.493 ms | 0 | 14 | 14 | 2 | 0 / 0 |

These counters have the same qualification as the earlier table: `computed`
includes transforms and opaque captures, and document-core
`derived_computed=0` does not establish zero downstream remeshing.

Frozen legacy ran at `5c4a212cae32e834fa4d805ae778ab5ee6cd71a2`
with source-tree SHA-256
`a7e9c100320abaf27134bcff8f9b24ec60f20f5cf0434c530281f3254a69ed81`.
Retained ran at `7195802f89b3a9440323485a6d98379caf120a7a` with stable
source-tree SHA-256
`31032d36f7e231c09c2b4287cab525e52e7a9b8271d71e6b2348c189b5fbcb72`.
The first v1 attempt stopped before a usable sample because the sandbox denied
the worker's private Unix socket; its incomplete journals are diagnostic only.

## Full-request boundary functional smoke

The in-process series above remains valid evidence for
`in-process-run-model-argv-with-first-call-engine-setup-v2`. It is now an
obsolete development comparison for the direct document worker: it excludes
the new worker process bridge and enters retained cadgen through the legacy
runner. The raw reports, medians, and checksums remain unchanged. Their
versioned boundary must never be automatically combined with the new series.

The replacement harness boundary is
`captured-entry-to-attested-step-full-request-v1`. It compares the current
direct `DocumentWorker` request with a benchmark-only frozen adapter. The old
runtime has no captured-input API, so that adapter writes the exact accepted
entry bytes immediately before invoking the old runner. This changes the old
path-only door semantics and is recorded in every baseline report. Its write
cost remains inside the full-request headline and is exposed separately.
Both the frozen baseline and the exact candidate HEAD are extracted as
code-only runtime archives before dispatch; the common source-hidden readback
uses that candidate archive too. A later checkout edit cannot change either
runtime during the series.

The isolated functional smoke on 2026-09-13 froze baseline
`5c4a212cae32e834fa4d805ae778ab5ee6cd71a2` and candidate
`834a0818b9bee347286cbb4f29b6721b969428db`. All 28 measured requests, 28
saved-byte oracles, exact-entry checks, STEP byte receipts, and owner shutdowns
passed. The comparison admitted all 14 paired rows at the same boundary. With
only one cold and two warm samples, these medians validate the harness and
request contract only; they are not percentile evidence or performance claims.

| Fixture / scenario | Frozen baseline | Candidate |
| --- | ---: | ---: |
| Plate cold | 2511.254 ms | 2408.360 ms |
| Plate unchanged | 9.355 ms | 31.056 ms |
| Plate local geometry | 76.433 ms | 69.035 ms |
| Plate placement | 58.061 ms | 49.825 ms |
| Assembly24 cold | 2624.698 ms | 2446.010 ms |
| Assembly24 unchanged | 10.588 ms | 32.832 ms |
| Assembly24 local geometry | 115.349 ms | 75.918 ms |
| Assembly24 placement | 93.765 ms | 54.852 ms |

The ignored local reports and SHA-256 values are:

- `models/tmp/performance-document-full-paired-smoke-20260913-v1-baseline.json`:
  `6cc4867419bdff4be78c853f573d7b85c7bb6cb5d989f9cb2e71132b27997aa1`
- `models/tmp/performance-document-full-paired-smoke-20260913-v1-candidate.json`:
  `e4c10236a2702228b450e172807e54fac98b8c60a5f95130eba965306be344ff`
- `models/tmp/performance-document-full-paired-smoke-20260913-v1-comparison.json`:
  `2107acc78a18748609f5794918c0f69fd4a027939db7737dc357f30f9ca6a5be`

The five-cold/ten-warm matrix below supersedes this smoke for performance
assessment. Resident display and saved STEP reopen remain separate diagnostics
with no ratio.

The unchanged current path reported zero computed geometry, zero native
copies, 14 reused operations, zero STEP writes/parses, and one verified product
reuse. A bounded owner-process cProfile diagnostic then replayed each fixture
five times against the same frozen candidate. It excludes worker IPC and
profiler overhead makes its wall values unsuitable for ratios. The dominant
five-call cumulative attribution was:

| Function | Plate | Assembly24 | Observation |
| --- | ---: | ---: | --- |
| `StockBuilderEffects.__init__` | 156.825 ms | 160.806 ms | Reconstructed the provider proof every replay. |
| `inspect.getattr_static` | 111.993 ms | 117.930 ms | 25,340 / 26,260 calls within that proof. |
| `SourceSession` enter + restore | 29.052 ms | 29.275 ms | Module isolation scans and restoration. |
| STEP `_runtime_identity` | 12.800 ms | 13.466 ms | Rehashed loaded writer/runtime identity. |
| STEP product prune | 2.772 ms | 27.690 ms | Two live-root traversals per request; Assembly24 scales with its tree. |

Cumulative rows overlap and must not be summed. The largest non-recursive
`tottime` rows were `inspect._shadowed_dict` (61.996 / 64.887 ms),
`inspect.getattr_static` (25.087 / 26.263 ms), and `inspect._check_class`
(24.681 / 26.203 ms) for plate / Assembly24. Assembly24's recursive
`build123d.geometry.Location.__init__` row reports 217.669 ms total against
46.688 ms cumulative; that cProfile recursion artifact is retained in the raw
report and is not used to allocate wall time. Safe follow-up work can split
the immutable stock provider discovery from per-request live identity guards,
while still checking every author-visible hook on every replay. It can also
track only modules actually evicted or loaded by `SourceSession`, retain a
process-stable identity for already-loaded STEP implementation code, and avoid
duplicating a live-root digest/prune traversal within one request. None of
these changes may skip authored Python, provider-hook validation, captured
input semantics, or actual destination-byte verification. The ignored local
diagnostic reports are
`models/tmp/performance-document-profile-unchanged-20260913-v1-plate.json`
(SHA-256 `f62c35dcc694207dea505182063711d4a06067c6fbb376c44d6ad0bb735a11f6`)
and
`models/tmp/performance-document-profile-unchanged-20260913-v1-assembly24.json`
(SHA-256 `de30aa9385fe6767721113253d48dae801ec78b3b4080ce07707ee3515a1a78a`).

## Full-request paired series at 801057d1b

The 2026-09-13 series froze baseline
`5c4a212cae32e834fa4d805ae778ab5ee6cd71a2` and candidate
`801057d1b4d10667bfe23d42f9fdc720f4a1e31e`. Both code-only archives remained
unchanged throughout the run. This uses the same
`captured-entry-to-attested-step-full-request-v1` boundary as the smoke above:
startup on cold requests, source replay, native work, required STEP save and
actual destination-byte verification. No stage is subtracted from the headline.

All 140 measured requests passed their byte receipts and independent saved-file
geometry checks. Each fixture has five cold samples and ten samples per warm
scenario, with an unmeasured warm prime. Native execution was serial, and the
first engine alternated by cold sample or complete warm scenario. JavaScript
unit checks and source review also ran on this development host during parts
of the series; these are exploratory medians and observed ranges, not controlled
lab or p95 evidence.

| Fixture / scenario | Baseline median (range), ms | Candidate median (range), ms | Candidate / baseline |
| --- | ---: | ---: | ---: |
| Plate cold | 2677.719 (2634.000–2749.900) | 2637.128 (2567.565–2764.365) | 0.985× |
| Plate unchanged | 9.297 (8.620–10.822) | 20.143 (19.298–21.125) | 2.167× |
| Plate local geometry | 79.248 (77.610–82.317) | 59.603 (58.949–60.769) | 0.752× |
| Plate placement | 57.818 (56.157–59.548) | 40.348 (39.549–42.152) | 0.698× |
| Assembly24 cold | 2691.798 (2610.297–2988.191) | 2638.687 (2585.303–2831.505) | 0.980× |
| Assembly24 unchanged | 11.221 (10.826–12.709) | 22.500 (21.820–24.373) | 2.005× |
| Assembly24 local geometry | 120.888 (118.898–123.616) | 74.020 (70.039–80.709) | 0.612× |
| Assembly24 placement | 95.312 (92.389–97.668) | 45.697 (44.950–47.907) | 0.479× |

Geometry and placement edits improve on these two bounded fixtures. Cold time
is similar; unchanged calls remain about twice as slow and fail the performance
gate. This is not evidence for large-assembly or FreeCAD parity. Assembly24's
placement case changes one occurrence while reusing its prototype: the candidate
reports zero computed geometry, 14 reused operations and two queries. It still
encodes, independently parses and writes a new STEP product. Unchanged calls
report zero geometry computations/native copies, zero STEP writes/parses and one
verified product reuse; ordinary Python still executes once per request.

A subsequent owner-process cProfile diagnostic replayed each fixture five times
against the same frozen candidate. Frontend installation accounted for about
92 ms cumulative per five calls; provider construction about 40.5 ms and final
guard installation about 43 ms, including eager unused builder/sketch auditors.
These overlapping profiler rows are attribution only, not request benchmarks.
The safe next target is deferred validation of unused providers, with canonical
proof discovery before authored execution and validation before every used
provider. The benchmark does not authorize skipping Python or mutable hooks.

Ignored local reports and SHA-256:

- `models/tmp/performance-document-full-paired-20260913-v2-baseline.json`:
  `e145f95d92594722f8873ea5e91a17ab3f592f60f68cb88f9b1b0bee98e19efd`
- `models/tmp/performance-document-full-paired-20260913-v2-candidate.json`:
  `a987e8cb54d1f06453bd99c627474c8e07c8a044c8a10f3657a9dbe8861bdafe`
- `models/tmp/performance-document-full-paired-20260913-v2-comparison.json`:
  `7202c0e92bfa6c49ffa12295c29c2452374eca0807c04a0040806b9e02601481`

Candidate runtime archive: 229 files, tree SHA-256
`b37ed2410798a6357fc30f69a264be84aba294f82c5928fabe7e335718563514`.
Profiles are `models/tmp/performance-document-profile-20260913-v2-plate.json`
and `models/tmp/performance-document-profile-20260913-v2-assembly24.json`.

## Paired STEP-companion contract smoke

Checkpoint `abc5b7bf0` adds required publication receipts for both STEP and the
sole companion, including verified absence when the model needs no companion.
The harness therefore uses a new common boundary,
`captured-entry-to-attested-step-pair-full-request-v2`. Both engines check the
actual STEP bytes and actual companion absence before the timer ends. The
older v1 measurements above keep their original qualification; these series
must not be combined into a speedup ratio.

A short serial run on 2026-09-13 used two measured unchanged requests per
fixture/engine, following an unmeasured prime. All eight measured requests and
the four primes passed their output and saved-geometry checks. The plate
medians were 9.943 ms baseline and 15.711 ms candidate; Assembly24 was 12.106 ms
and 18.009 ms. This is a functional smoke with too few samples for a performance
claim. It still shows the unresolved unchanged-request regression.

Five-call owner-process profiles of the same frozen candidate attribute remaining
warm costs to import-session bookkeeping, repeated package metadata discovery,
and frontend eligibility checks. Profiling ran alongside other development
checks and excludes worker IPC; its instrumented elapsed times are not request
benchmarks.

Ignored local reports and SHA-256:

- `models/tmp/performance-document-unchanged-paired-20260913-v3-baseline.json`:
  `f0e174f038d7d574048642d16726ef9d5480ef8bad58e65c77ab90c2446c6f4b`
- `models/tmp/performance-document-unchanged-paired-20260913-v3-candidate.json`:
  `b87802b031989943530e9f179056798155dd67af3bc46ae7c5bc328f3dec03bb`
- `models/tmp/performance-document-unchanged-paired-20260913-v3-comparison.json`:
  `cfcd707f15095a53365299bf5e98df54c4b9f4137c31329e3242ce396491d0a8`

Candidate runtime archive: 230 files, tree SHA-256
`a63dda2d8aa6f68ee906b5c752efabb880185e9cf0beaac0b07b703c5f9434d3`.
Profiles are `models/tmp/performance-document-profile-20260913-v3-plate.json`
and `models/tmp/performance-document-profile-20260913-v3-assembly24.json`.

## Paired unchanged requests after setup reduction

The next frozen candidate, `aa601ff151247b49794f47ed2a40ea4925c1f5fa`, was
measured with ten unchanged requests per fixture/engine after an unmeasured
prime. This uses the same v2 STEP-plus-companion boundary above. All 40 measured
requests and four primes passed saved-output and independent geometry checks.
Native and Chromium work was reserved serially; other agents performed source
review and lightweight fake/socket tests. The first engine alternated by fixture.

| Fixture | Baseline median (range), ms | Candidate median (range), ms | Candidate / baseline |
| --- | ---: | ---: | ---: |
| Plate | 9.164 (8.292–11.102) | 12.032 (11.348–13.550) | 1.313× |
| Assembly24 | 11.776 (10.642–13.057) | 13.510 (13.014–14.498) | 1.147× |

Both fixtures reuse all 14 evaluations and their encoded STEP product, with
zero native copies, new geometry computations, STEP parses or file writes.
They still replay ordinary Python, answer two native queries, verify existing
STEP bytes and attest companion absence. The candidate remains slower for this
unchanged-request workload; the remaining gap is about 2–3 ms. These ten-sample
medians/ranges do not establish p95, public CLI latency or browser presentation.

Reports and SHA-256:

- `models/tmp/performance-document-unchanged-paired-20260913-v4-baseline.json`:
  `977245a3eb177f27d85b91570a32048741004894ac3f49b10e1fc1f6198a995d`
- `models/tmp/performance-document-unchanged-paired-20260913-v4-candidate.json`:
  `6f89483414e867a1158e4b91a4beb4a398278b250c35b8d5669012835499a293`
- `models/tmp/performance-document-unchanged-paired-20260913-v4-comparison.json`:
  `61ec7d1a9e00c5e50568086286578d93b9d5af761f236df77992f410985796f2`

Candidate runtime archive: 231 files, tree SHA-256
`017af4019433c62c804333ddbb6c62a8de298f3fc3f66cd522353fd500bf0661`.
The actual four-session ledger records all adapter exits and is preserved in
every report under series `full-paired-1789322841766039000`.

## FreeCAD probe qualification

On 2026-09-13, a sandboxed `FreeCADCmd --version` probe aborted with exit 134
and `Incompatible processor. This Qt build requires the following features:
neon`. The same installed executable run outside that sandbox exited 0 and
reported `FreeCAD 1.1.1 Revision: 20260414 (Git shallow)`. The first result was
therefore an environment-induced CPU-feature detection failure and is not
performance evidence.

The later reserved serial FreeCAD reference used that 1.1.1 build with OCCT
7.8.1 and five measured samples per scenario. All 15 plate and 360 Assembly24
occurrence comparisons matched the cadgen saved-file labels, validity, volume,
area, bounds and topology counts. Its stage medians were:

| Fixture / scenario | Edit + recompute | Native query | Prototype mesh | STEP export | Cold readback |
| --- | ---: | ---: | ---: | ---: | ---: |
| Plate unchanged | 0.006 ms | 0.629 ms | 5.279 ms | 2.459 ms | 5.532 ms |
| Plate whole-factory geometry | 15.017 ms | 0.611 ms | 5.254 ms | 2.532 ms | 5.564 ms |
| Plate placement | 0.017 ms | 0.619 ms | 5.354 ms | 2.384 ms | 5.478 ms |
| Assembly24 unchanged | 0.018 ms | 13.954 ms | 5.391 ms | 4.735 ms | 6.191 ms |
| Assembly24 whole-factory geometry | 15.057 ms | 13.937 ms | 5.026 ms | 4.703 ms | 6.387 ms |
| Assembly24 placement | 0.027 ms | 13.915 ms | 5.240 ms | 4.440 ms | 6.212 ms |

Peak worker RSS was 111.3 MiB for plate and 119.6 MiB for Assembly24. These
stage values are not a source-command total and exclude process launch and GUI
latency. The geometry stage rebuilds the whole plate factory and assigns it to
the retained occurrences; it is not evidence of feature-level dirty-hole
recomputation.

Fresh result JSON belongs in `results/`. Every report embeds exact revisions,
runtime/dependency fingerprints, source hashes, commands, sample counts, timing
qualification, oracles and cleanup status. A smoke report must remain labeled
`functional-smoke`; it must not be quoted as percentile evidence.

The exact valid local reports are `results/checkpoint-functional-v11.json`,
`results/legacy-inprocess-full-v2.json`, `results/candidate-full-v6.json`,
`results/retained-vs-legacy-inprocess-full.json`,
`results/freecad-plate-v1.json`, and `results/freecad-assembly24-v2.json`.
The corrected paired reports are `results/paired-legacy-v2.json`,
`results/paired-retained-v2.json`, and `results/paired-comparison-v2.json`.
Their completed-sample journals use the same names with `.samples.jsonl`
appended, except the derived comparison report. `RESULTS-20260913.sha256`
freezes the exact report and journal bytes while these machine-local results
remain ignored by Git.

## Iris118 coverage failure — 13 September 2026

The first moderate real-model probe qualifies the earlier small-fixture results:
those improvements do not yet generalize. The mechanical iris has 118 labeled
occurrences and produces roughly 13 MB of STEP. These initial complete-request
samples use the same accepted source bytes and STEP-plus-absent-companion checks:

| Task | Frozen old engine | Internal retained engine | Samples per engine |
| --- | ---: | ---: | ---: |
| Cold build | 19.690 s | 22.120 s | 1 |
| Unchanged build | 0.073 s | 20.683 s | 1 |

These are diagnostic observations, not a repeated paired performance baseline.
The current engine was a live worktree, with concurrent engineering work during
part of its probe. Its unchanged result recomputed 1,646 evaluations and made
1,772 native copies, so the regression is not explained by timer noise. The old
unchanged gate executes no model body; the new path executes the body and is
expected to reuse matching managed CAD operations. Both archived STEP outputs
independently agree on all 118 occurrence labels, topology counts, volume, area
and bounds. Different STEP byte counts are therefore not themselves evidence of
missing geometry. Appearance parity was not measured by this geometry oracle.

The first unintended native escape was stock Cone insertion into BuildPart.
The guarded Cone fix at `27a7c5a23` removes that boundary, but the next escape is
the second Polygon in a multi-polygon BuildSketch. A subsequent in-process
probe still takes about 18.4 seconds unchanged; it has a different timing
boundary and is not an after value for the table. Coverage remains a cutover
blocker, including ordinary selected-edge queries and modifiers.

A separate old-engine series in a reserved serial compute window changed only
the base-ring mounting holes to 5.05, 5.10 and 5.15 mm. Complete warm requests
took **5.893, 5.943 and 5.960 seconds** (median **5.943 seconds**), with source
execution on every edit. All three saved geometry oracles passed, including the
117 unchanged parts. There is no matched new-engine edit result yet. The
repeatable `full-paired --models iris118` workload now supports these hole edits
and exact base-ring placement edits without changing the original algorithms.

Local raw evidence (not committed CAD artifacts):

- `models/tmp/document-iris-legacy-probe-20260913-v2/report.json`, SHA-256
  `0b7d13b600749103bdce37fa1c58f4ca4c04fb173228008f4542a5d7a1f411f2`.
- `models/tmp/document-iris-candidate-probe-20260913/report.json`, SHA-256
  `a380267237805cc55e8ad0d53465387e18aa5d9ddb0851a5d30247481b050121`.
- `models/tmp/document-iris-readback-probe-20260913/comparison.json` and
  `readback.json`, the independent 118-part geometry comparison.
- `models/tmp/document-iris-legacy-edit-series-20260913-v2/report.json`, SHA-256
  `2289ce45164e27a651fccc50d0f212569df735d826c123717421abd021d9e038`.
