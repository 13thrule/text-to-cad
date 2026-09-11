# Cold document compilation cleanup

The implementation, committed as `d706cf1f0`, removes work whose result
raw-document compilation does not use.
It avoids a workspace-wide model-source scan, an adaptive face/edge/bounds scan,
and a discarded Python compound. The nine-part compile improves modestly:
1,094.86 → 1,079.46 ms by median. This does not close cold-import latency or the
roughly 500 ms procedural preview gap; generated model execution is unchanged.

| Document, median ms | Baseline | Source scan removed | Full cleanup |
|---|---:|---:|---:|
| Planetary, nine parts | 1,094.86 | 1,096.01 | 1,079.46 |
| Tiny nested assembly | 19.69 | 16.25 | 15.36 |
| Tiny repeated assembly | 23.73 | 18.83 | 17.65 |
| Two free STEP roots | 19.76 | 14.02 | 14.55 |

Each cell contains three calls. Rounds use baseline/scan/full,
scan/full/baseline, then full/baseline/scan, so each condition occupies every
position for every document. All 36 observations remain in the
[raw report](results/cold-compile-cleanup-20260911.json.gz), including the first
baseline planetary call at 1,336.31 ms. Separate documents are not averaged.
The scan-only nine-part median is slightly slower; that table does not establish
a complete-call improvement from scanning alone. Other team workloads paused,
but unrelated host and user activity was not controlled.

The timer covers `build_step_artifact` in resident private interpreters after
normal worker preload. Preload took 2,279.57 / 2,263.50 / 2,263.78 ms, outside the
timer. Every call starts with an empty private store and cleared operation RAM;
STEP hashing, setup, complete-object verification and module/source checks are
outside the timer. Stage wrappers instrument each condition equally. There is
no daemon IPC or fresh interpreter startup in these compile timings. They must
not be presented as a reduction from the earlier 4.2-second transient public
read or as an exact rerun of the 1.35-second ready-daemon public read.

For the planetary fixture, baseline stage medians are 4.96 ms for discovery,
11.08 ms for adaptive classification and 1.04 ms for discarded composition.
Those calls disappear in the full candidate. Raw STEP snapshot/parse remains
255.37 ms, and SURF extraction remains 758.01 ms. Extraction is nested in
canonical publication; these stage medians are attribution, not an additive
breakdown of a representative call. The remaining cold cost is principally
native parse and mandatory first-time canonical surface derivation.

## Boundary and correctness

`step_artifact_cli` previously discovered every model beneath its `repo_root`
to construct `entries_by_step_path`; `_generate_part_outputs` only copied that
map and never consumed it. A raw compile now passes only the requested spec.
The study workspace includes ten readable existing planetary model files, with
cache stores outside the discovery root. The focused audit rejects and records
any attempt to read or traverse an unrelated source directory, so an internal
exception handler cannot hide an attempted access.

The native cleanup accepts only raw imported scenes, excluding generated specs,
Python-backed scenes and annotated re-emits. The canonical document builder
already fixes its edge metadata and consumes the parsed scene directly.
Generated/re-emitted preparation and public `read_step` construction remain
unchanged. No cache domain, native identity rule, schema, author API, STEP
parser, surface extraction or canonical writer changes.

Nine focused tests pass. They compare complete tree/BREP/SURF closures through
cold/current/force and corruption repair; verify original prototype BREP bytes
and Free flags before/after the discarded wrapper on single, nested, repeated
and real multiple-root STEP inputs; and check independent public-reader owners.
Bound PBR/kinematics sidecars stay byte-identical and remain export overlays.
Foreign sidecars retain their existing distinction: cold/forced geometry
compilation preserves them, while current-result/declaration reading fails
loudly on the binding. Generated and annotated-reemit sentinels retain their
preparation paths. Every measured condition produces the same canonical tree
and complete verified object closure for each document, with unchanged input
STEP bytes. The planetary input is 2,268,663 bytes, SHA-256
`406dd2e19b6a4ea3a623abd19b03708b7d9e97b4402ba4161c737eb31f10fdca`.

The private runtime was captured at `35307d532` plus the reviewed six-file
descriptor-bounds working delta. All 183 Python files were independently checked
against their content-equivalent commit `47b2f94e6`; bare `35307d532` is not the
measured baseline. The raw report embeds the executed helper, portable tests,
module paths, source/object hashes, all stages and cleanup proof. The complete
window was September 11, 2026, 02:13:19.016–02:13:38.042 UTC; measured calls ran
02:13:25.994–02:13:36.768. All three owned worker processes exited zero. No main
worktree, bundle or user viewer changed during this private comparison.

After integration, all 1,628 package tests and 13 focused/boundary tests pass;
the [raw validation record](results/package-cold-compile-20260911.json) preserves
logs and source hashes. The [isolated installed-wheel check](results/installed-wheel-cold-compile-20260911.json.gz)
also passes, including source-free STEP/mesh/image/video exports and actual
serving-process/HTTP asset identity. These checks are functional, not additional
performance samples.
