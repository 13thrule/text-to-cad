# Viewer detail and lifecycle follow-up

The medium fixture checks pass at forced L2 detail, above canonical L1. They
do not establish full-hand performance or FreeCAD GUI parity.

## Changes

- Viewport refinements keep selector topology lazy. An already-used component
  prepares its selectors at the replacement tessellation before publishing new
  triangles; a demand arriving during the render worker is reconciled too.
- The admission reservation includes replacement arrays and worker scratch
  memory, and estimates the coarse tier's angular as well as chord change.
  Display arrays shared with asset caches receive one CPU charge.
- Initial framing is sampled after installing component summaries. Previously
  a stationary camera could leave new components coarse indefinitely. A
  progressive batch also restarts a settled refinement queue.
- Worker pools start with one isolate and grow for ready concurrent requests.
  Sequential LOD jobs reuse their worker until the queue settles. Topology-only
  picks release idle workers after sibling consumers drain.
- An LOD swap releases obsolete ownership in both the SURF payload and initial
  display caches. Surface instance dirty checks share their upload arrays;
  immutable source colors no longer need an extra baseline copy.

## Measurements

Apple M1 Max, 64 GiB, Chromium Metal, 1400×900. The viewer serves copied STEP
files without source scripts. Its preexisting server cache was retained.
These are bounded single runs; model execution and preview publication are
excluded from the replacement timings.

| Check | Result |
|---|---|
| 24 occurrences, two components, forced L2 | Complete in 649 ms; both leaves L2; scheduler idle |
| Actual workers for initial load + two refinements | Three created, peak two live, all three terminated |
| Peak largest renderer, forced L2 load | 164.39 MiB |
| Retained heap after explicit GC | 15.23 MiB |
| Five-second moving-occurrence animation | 603 frame samples; p95 8.5 ms |
| Active orbit | 599 frame samples; p95 8.9 ms |
| Six same-path STEP replacements | All complete; owned bytes 442,464 and GPU bytes 26,544 on every cycle |
| Retained JS heap across six replacements | 22,221,364 → 22,859,575 bytes, +0.61 MiB |

The lifecycle alternates repeated24 and the nine-part planetary assembly,
demands topology through selection, returns to repeated24, animates all 24
occurrences, then alternates a 12 mm / 13 mm box variant through the same saved
path. It restores original target bytes/timestamps in `finally`. All 13 checks
pass, including delayed selectors, no errors/limitations, fixed GPU allocation
counts, reclaimed workers and the requested L2 floor. Frame intervals measure
browser presentation cadence, not GPU execution time. A six-edit heap trend
does not prove that an indefinitely long session is leak-free.

Reports: [lifecycle](results/viewer-headroom-lifecycle-20260910.json),
[detail and worker accounting](results/viewer-headroom-detail-20260910.json).
The built-client fingerprint remained
`0f82fd2a2ec45ae729c63bb6c9c8b4256e6a4edc17e12dc5105e5c8cfb10c8cc`.
The lifecycle report records an aggregate source-fingerprint change while other
work continued; its built client did not change. The later detail run's source
and client fingerprints both remain unchanged.

Fixture STEP SHA-256 values:

- repeated24: `ab104f441544b852390825f5c7589a0815a3448024bf88b1af27fd754786e370`
- planetary2: `6147bba14136cc25255b5d5c2c2d6e12c0c691fe3a6665a488e81faee7d1abeb`
- box-width variant: `77ff39d8f565d16f7c2ee835d3641160dce81ec61800dee09448f06bfae7cf95`

## Acceptance gate for the large assembly

`measure.mjs --min-lod 1` requires every component to reach canonical detail,
an idle scheduler, complete component/occurrence counts and scene synchronization
after the latest publication. `--max-renderer-mib` adds an external RSS stop;
renderer probes are also bounded from Node. The floor affects display only;
export defaults and mesh identities are unchanged.

The next integration must freeze all runtime sources and use the current
canonical saved hand tree. A suggested single run uses `--min-lod 1 --runs 1
--timeout-ms 180000 --max-renderer-mib 2048`. No large-hand run is included in
this report. The older 67.86 / 18.77 second coarse results remain insufficient
for final full-detail acceptance.

Validation: 58 targeted worker/cache/revision/scheduler tests, all 402 viewer
tests, scene/instancing/accounting regressions, quality-completion harness tests,
and the production viewer build pass. The parent integration still owns bundled
runtime regeneration and the complete repository validation.
