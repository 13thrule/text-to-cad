# Cadgen performance execution plan

## Execution status — in progress, September 11, 2026

See the [plain-language results summary](scripts/bench/cadgen-performance/SUMMARY-20260911.md)
for the measured impact, FreeCAD comparison and current play viewer.

The initial implementation below is committed on `codex/tendon-hand-performance`, based on the
reviewed `codex/tendon-hand-preview` tip `7aa3e85be`. The requested branch is
checked out in the primary workspace; this isolated worktree preserves that
checkout. No release version change is part of this work.

- Imported STEP cache compilation and canonical reconstruction: implemented;
  fresh-process hits skip text parsing, consumed-byte digests and deletion
  recovery are tested.
- Render-only cached loads and delayed selectors: implemented; exact concrete
  tessellation identity and first-pick replay are tested.
- Shared GPU/BVH/edge ownership and dirty edge uploads: implemented; last-owner
  release and shared-scene regression tests pass.
- Compatible opaque surface instancing: implemented, with picking, selection,
  clipping, transform, vertex-color and transient hover regressions. Real
  repeated-assembly browser checks pass: 24 occurrences use two surface sets;
  repeated model switches return to the same GPU allocation totals.
- Viewer memory accounting/admission: implemented and browser-validated. Idle
  workers are reclaimed after overlapping LOD jobs drain; settled worker
  estimates return to zero. This is a soft envelope for measured/estimated
  owned resources, not a hard total browser RSS cap.
- Synchronous worker cancellation: implemented. Each worker owns one request;
  active cancellation replaces only that worker, queued work stays on the
  client, and worker failure never retries accepted work on the UI thread.
  Independent concurrency review and cancellation/failure tests pass.
- Warm materialization ownership: implemented; a bounded canonical-byte LRU
  replaces cross-consumer shared mutable kernel prototypes. Fresh independent
  materialization costs about 4 ms on the nine-part fixture. Op-memo misses
  reuse their verified ephemeral reconstruction, removing one BREP read while
  storing only canonical bytes and attribute recipes.
- Bounded pinned-link publication: implemented and independently reviewed.
  Exact component bounds use the existing numeric op index. Verified bytes,
  appearance and invocation-owned native prototypes are captured before source
  publication; ordinary occurrence/group assembly can then follow it. There is
  no model-author API change. All 96 moderate comparison builds agree on actual
  STEP outputs and exact pins, and 22 focused ownership/fallback tests pass.
- Daemon memory admission: implemented; includes suspended parents, descendants,
  retiring workers and dependency headroom. Focused tests and a real three-level
  one-slot build pass.
- Preview/save separation: implemented; a real first-save browser check showed
  all nine parts before the STEP existed, then the validated saved tree.
  Follow edits uses the daemon's ordered per-output/store channel; plain saved
  file reads remain byte-addressed. Six publication tests cover early preview,
  rejected save, failed read-back, competing edits, determinism and cache loss.
  A real warm edit retains all nine parts until the complete replacement is
  ready; a failed build retains both the visible model and previous STEP bytes.
- Schema-8 sidecars: implemented; kinematics and PBR appearance bind to saved
  STEP SHA-256, stale pairs report annotation errors, and imported authored
  sidecars are preserved. Authored model results and canonical document trees
  are separate. Exact node mapping, owned material/face-color metadata and
  appearance-sensitive export identity are covered by regression tests.
- Durable build benchmark: added under `scripts/bench/cadgen-performance`.
  Native OCCT meshing is evaluated; the current JS mesher is retained.
  The later moderate-fixture study establishes a deterministic native adapter
  and a uniform margin that meets finite sampled quality targets, but curved
  workloads cost more. Native producer integration is deferred; it is not an
  unfinished prerequisite for this performance work.
  See [the measured study](scripts/bench/cadgen-performance/RESULTS-20260910.md).
  Integrated packaging and browser lifecycle validation pass. See the
  [validation record](scripts/bench/cadgen-performance/VALIDATION-20260910.md).

The matched [warm comparison](scripts/bench/cadgen-performance/WARM-COMPARISON-20260910.md)
measures the reviewed `7aa3e85be` runtime and the current source on the same
machine and input bytes, separating previously emitted edits from new values.
Repeated imported-STEP geometry/placement saves improve from 867.91 / 855.15 ms
to 387.67 / 421.54 ms. New imported saves improve from 926.84 / 869.47 ms to
649.98 / 742.61 ms; previews arrive in 153.22 / 194.59 ms. Repeated foreign
reads improve from 257.60 to 31.19 ms. A first read from an empty store instead
regresses from 256.56 to 4,200.79 ms, including compile-worker startup and
canonical publication. A separately verified already-warm daemon handles an
empty-store first read in 1,354.14 ms; its 2,270.42 ms startup is separate.

The procedural nine-part model still reruns its complete Python body. New
geometry/placement saves are 952.15 / 951.36 ms, versus 942.94 / 930.48 ms on
the original; previews are 506.83 / 496.18 ms. **The 250 ms preview target
remains unmet.** Earlier current windows were faster; exact output bytes match,
but separate windows do not isolate the cause of that variation. Profiling
locates repeated sketch/context and live shape-identity work in the model body.

A split version uses ordinary child decorators and produces identical current
STEP bytes for all nine checked variants. Repeated geometry/placement saves
improve from 574.20 / 537.33 ms to 453.56 / 379.48 ms. New values still regress
from 597.41 / 545.66 ms to 686.37 / 600.06 ms, a 14.9% / 10.0% gap. Their
previews arrive in 268.85 / 178.68 ms. Immutable syntax recipes shared within
one closure calculation and removal of an unused freshness traversal reduce
the preceding split regression. Bounded private preparation of already-pinned
siblings is now implemented for ordinary `Compound` list/tuple construction.
Its separate, controlled `children=` experiment reduces new geometry preview
median from 352.93 to 276.53 ms and complete saves from 808.20 to 760.04 ms;
placement preview is unchanged. Both conditions have substantial first-edit
stalls, and these timings do not replace the older cross-version comparison.
See [sibling preparation](scripts/bench/cadgen-performance/SIBLING-PREPARATION-20260910.md).
Each repeat/unseen category has three observations;
new-value samples are three distinct inputs, not latency confidence intervals.

The new source-result protocol removes child STEP persistence from the
parent's preview path. Every called child, including discarded calls, still
finishes its declared outputs before the parent saves. Source/document records
use schema 3. Cold compile now forbids prior code-index reads, and focused
regressions cover exact job results, no-op gate races, one-slot scheduling,
failed saves and source-free document recovery.

The [mesher v2 study](scripts/bench/cadgen-performance/MESHER-V2-20260910.md)
fixes the reproduced trim, winding, short-edge and pole defects. It compares
JS and private native OCCT extraction on the planetary and curved corpora,
including sampled surface error and reference/edge audits. It supports
retaining JS; it does not prove visual equivalence for arbitrary STEP files
or a continuous geometric error bound.

## Remaining implementation and acceptance work

The plan remains **in progress**. Passing correctness suites does not complete
every performance target, and the final installed-wheel check must follow the
last runtime changes.

- Complete integrated viewer loading, interaction, detail refinement and memory
  checks on the **nine-part planetary assembly and modest repeated-parts
  fixtures**. The user explicitly stopped further tendon-hand stress tests on
  September 11; full-hand acceptance is no longer a required iteration gate.
  Preserve its existing results as historical diagnostic evidence.
  The integrated `8971f760d` medium adaptive checkpoint passes all 13 assertions,
  including every settled-detail target, with 210.56 MiB peak renderer RSS and
  orbit frame interval p95 of 8.7 ms. These successive checkpoints are not a
  matched speedup measurement. Subsequent runtime changes require another
  bounded medium check.
  Identity-preserving selection pruning is implemented and independently
  reviewed. The same 246 detail adoptions retain 9 workspace contexts rather
  than 503, and backing storage after collection falls from 19.953 to 3.393 MB.
  Nonempty selection and hiding pass actual browser checks. The final isolated
  hand run also passed all 866 L1 components / 3,259 occurrences at 1,482 MiB
  peak renderer RSS, before collection; that recorded result does not require
  further hand runs. See the [selection investigation](scripts/bench/cadgen-performance/VIEWER-SELECTION-RETENTION-20260911.md).
  Full cleanup and failed-publication recovery are committed in `8971f760d`;
  independent review, 1,015 shared tests and 486 viewer tests pass. Separate
  browser checks pass 90 assertions, and the restored-alert fix in `c07488e1d`
  passes 15 further assertions. Bounded grouping is committed in `9be4f5424`:
  at most four component replacements, one scheduler loader and one publication
  awaiting actual adoption. The combined client passes 32 more browser assertions
  covering two-component rollback with selected-face preservation and stale
  replies across model switches; 506 viewer tests pass. The
  [alternating moderate comparison](scripts/bench/cadgen-performance/VIEWER-LOD-BATCH-MODERATE-20260910.md)
  reduces six scene publications to two. Against the same candidate at size one,
  refinement completes about 42 ms sooner, while first refined draw arrives
  7–11 ms later. Three samples per condition do not establish a general speedup.
  Cold fine-detail meshing is a separate investigation, now using the planetary
  and small curved corpora. Browser probes continue to verify actual served
  client/worker bytes and installed dependency versions.
- Resolve the measured new-value split-build regression. A later frozen
  `2709968dc` comparison passes all 64 calls and exact-output/pin checks, but
  new-geometry saves still regress in that window; its preview median is 267 ms.
  See the [qualified split checkpoint](scripts/bench/cadgen-performance/WARM-COMPARISON-20260910.md#later-split-only-checkpoint-september-11).
  The bounded exact-bounds provider and internal publication increment are now
  integrated after independent review. They preserve owned geometry/appearance
  snapshots, native prevalidation and child-output waiting. A separate interleaved
  study with identical operation-cache v7 code reduces new geometry preview from
  235.4 to 214.8 ms and new placement from 185.6 to 160.7 ms. Save medians improve
  by only 6–15 ms for these new values, with mixed individual results. This does
  not remove new-output STEP readback or causally resolve the older cross-version
  save regression. See the
  [feasibility analysis](scripts/bench/cadgen-performance/DEFERRED-ASSEMBLY-FEASIBILITY-20260911.md).
  Current package validation passes
  1,597 Python tests, 1,015 shared JS tests and 506 viewer tests. The
  `8971f760d` installed wheel/source-free export checks pass, with 182 Python
  files and 29 runtime files matching source, wheel and installation. Later
  runtime changes require their relevant checks again.
  The `9be4f5424` viewer also passes an isolated installed-wheel check: all
  22 assets match source build, staging, wheel, installation and HTTP, with
  module provenance captured inside the actual serving process.
  Subsequent backend commit `a862c3d1e` makes operation-cache disk hits honor
  the existing RAM limit and binds scheme-7 keys to actual installed kernel
  identities. The integrated bounds implementation is committed in `47b2f94e6`;
  all 1,619 package tests pass, including the 22 new focused tests, and package
  boundary checks pass. The commit's bundle freshness hook also passes.
  The [final full wheel proof](scripts/bench/cadgen-performance/results/installed-wheel-descriptor-bounds-20260911.json.gz)
  passes with 217 installed package files exactly matching the wheel and source.
  Its two decorated children exercise all-link composition, exact pins and
  unchanged cold/warm outputs. After deleting source and the build store, saved
  STEP inspection/re-export, STL, GLB, posed PNG and animated MP4 work with
  code-index reads forbidden. All 22 served viewer assets and actual serving
  process provenance match the isolated installation.
  The subsequent [raw compile cleanup](scripts/bench/cadgen-performance/COLD-COMPILE-CLEANUP-20260911.md)
  is integrated after independent review: source discovery, unused adaptive
  metadata and discarded compound construction are skipped for raw documents.
  All 36 resident-worker compiles preserve exact trees and object closures;
  the nine-part median moves from 1,094.86 to 1,079.46 ms. Nine focused tests
  and four package-boundary tests pass. Committed as `d706cf1f0`, it passes all
  1,628 package tests and a fresh isolated-wheel export/viewer check. This modest
  gain does not remove process startup or surface extraction.
  Manual GC also now retains current-schema document-index trees and their
  complete linked closure after source records are forgotten. External mesh
  output hashes are not mistaken for store-object roots. Eleven focused tests
  cover cleanup, forgetting and package boundaries; this removes an avoidable
  recompilation path without changing geometry or display outputs.
  The medium repeated-assembly lifecycle already exercises selection, orbit,
  animation, file switches and six saved-file replacements with stable owned
  geometry/GPU allocation totals.
- Validate final small cold builds and exact-output readback reuse. Missing
  component BREP batches up to 768 KiB now use the same extraction code inline,
  respecting explicit worker overrides. Previously seen exact STEP bytes may
  reuse a verified canonical document scene; unseen outputs still parse STEP.
  Atomic repair replaces only invalid derived bytes with their correct content.
  Actual source-free reader tests cover corrupt tree, BREP and SURF objects,
  including hash-valid unreadable SURF data, without consulting code indexes.
- Keep the procedural preview target visible. Finer invalidation uses existing
  decorated model boundaries; multiple functions in one file still share that
  file's source hash. No cache/session helpers are added to model authors.
- Evaluate separating exact geometry publication from display-surface derivation.
  The resident cold-compile study attributes about 758 ms to first-time SURF
  extraction and 255 ms to STEP parsing. The architectural review must define
  complete BREP-backed identity, immutable intrinsic face appearance, lazy
  artifact-derived surface jobs, deletion recovery and compatibility cutover
  before implementation. Store expansion is authorized; incomplete native
  geometry, source-dependent saved readers and author-managed cache utilities
  remain unacceptable. Measure actual public read/edit savings separately from
  work merely deferred until the first display request. The
  [concrete contract and proof gates](scripts/bench/cadgen-performance/DEFERRED-SURF-CONTRACT-20260911.md)
  now authorize a bounded private prototype; no production schema change has
  landed. A separate tiny native-codec study investigates the real unreadable
  BREP fallback, and a client review maps surface and tessellation identities.
- Shared mutable backend prototypes were rejected after native mutation tests.
  The runtime retains canonical bytes and reconstructs private shapes for each
  consumer. That preserves cache-state equivalence and is not a headless-kernel
  requirement. It also does not turn arbitrary Python into a retained FreeCAD
  feature document.
- Saves remain explicit builds. There is no separate automatic-save queue to
  coalesce, cancellation of shared canonical jobs, or provisional-child pin
  substitution. Check/rename publication detects observed conflicts but is not
  a cross-writer transaction. Preview handles remain ephemeral rather than
  manual-GC roots; authoritative source and saved STEP stay outside the cache.

The old large-hand reports measured initial coarse detail with refinement
disabled: 67.86 seconds cold and 18.77 seconds cached, with peak largest-renderer
RSS of 1,965 / 1,890 MiB. They predate the current canonical document and mesher
cutovers and are retained as historical evidence, not final acceptance.

Implementation branch: `codex/tendon-hand-performance`; reviewed baseline:
`7aa3e85be76f305437abd3d7aba26e38b28e43cb`. The separate hand project is safely
extracted into `models/tendon_hand` on `codex/tendon-hand-project`, one commit
above `main`, with no generated large artifacts. Its legacy R13 assets require
the documented, separately preserved local checkpoint. The original hand
project folders have been removed from the performance branch.

## Objective

Make building, editing and rendering STEP assemblies responsive and memory-safe. Preserve exact geometry, deterministic outputs, assembly structure, appearance, selection, measurements, animation and deformation.

Deliver the work in three milestones:

1. **Finish the viewer improvements:** reduce cached-load CPU work, complete resource ownership, manage scene memory and instance repeated surfaces.
2. **Reduce warm-build overhead:** populate imported-document caches, reduce repeated serialization and bound backend memory.
3. **Introduce persistent edit previews:** publish editing revisions before STEP persistence completes, while preserving saved-file consistency.

Use separate reviewable commits for each step. Build on the branch's existing indexed geometry, progressive publication, component-level GPU reuse, disposal, cache/admission controls and instanced edges.

## Architecture decisions

### Approved extension boundary

The user clarified that expanding cadgen's cache store and runtime is welcome provided the clean object/index model remains and model authors need no additional utilities beyond decorators. This supersedes the earlier assumption that the existing index namespaces and runtime policies must remain fixed. The decisions below are engineering work within that direction, not repeated permission requests.

- Immutable, content-addressed objects hold reusable derived payloads. Mutable, atomically published index entries identify inputs and point to complete object graphs.
- New derived object types and index namespaces are allowed when their key, payload, ownership, reachability and recovery rules are explicit. Preview/revision results can use this model; do not create a parallel cache directory structure or a second persistence framework.
- Agent-authored models continue using ordinary CAD code and the existing decorators. Do not require new cache/session imports, cache keys, manual invalidation, persistence calls, ownership wrappers or explicit dependency-registration helpers. Decorators and cadgen's internal runtime own those mechanisms.
- Authored Python remains authoritative for code edits. No extra project document is required merely to enable previews. Any future direct editing must retain its authoritative changes outside the disposable cache under an explicit editor durability contract.
- Preserve byte-deterministic saved outputs, cache-state-independent modeling behavior and source-independent saved-file readers. Mechanisms may evolve when the replacement satisfies these properties and is tested.

### Memory is a managed resource

Browser and backend memory management now use the approved runtime extension.
[STORE.md](packages/cadgen/STORE.md), sections 9 and 11, replaced the former
memory/worker-cap prohibition with admission, ownership and reclamation rules.

Any accepted backend policy must distinguish reclaiming in-memory resources from deleting persistent derived cache entries. On-disk GC remains explicit through `cadgen store gc`; browser or worker pressure must not start a disk sweeper.

### Editing previews can precede STEP persistence

Saved-file viewing retains the guarantee that its geometry matches the actual STEP bytes. Add an explicit preview input representing the current editing revision before export finishes, using derived objects and suitable index entries. Steps 9–10 define the internal input, ownership, recovery and publication contracts before dependent implementation; agents do not construct sessions or invoke a preview utility.

Keep the branch's STEP read-back validation for saved documents. Do not restore the discrepancy between cached pre-export shapes and geometry actually contained in a STEP file.

Ordinary file opening remains tied to saved artifacts. Kernel work stays in build workers; the viewer server remains a lightweight broker and does not import model source or the CAD kernel to render a preview.

Record any accepted contract changes explicitly in `packages/cadgen/README.md`, `packages/cadgen/STORE.md`, `packages/cadgen-js/README.md` and `apps/viewer/README.md`. Do not rewrite a law merely to describe an implementation that violated it.

## Store-contract review

Reviewed September 9, 2026 against the store laws, current publication/cache implementation and existing store invariant tests, with independent subagent reviews. This is design-level validation; unimplemented behavior has not been runtime-validated.

**Verdict:** the original plan required changes to existing policies and clearer correctness guarantees. The user's subsequent clarification authorizes store/runtime expansion within the object/index model and decorator-only authoring interface. Preserve the core invariants below while deliberately updating the affected contracts; the earlier policy conflicts are not a blanket prohibition on the optimizations.

| Scope | Assessment |
|---|---|
| Measurements, lazy selectors, GPU ownership and instancing | Compatible when they only change derived work and process state. |
| Imported-document caching and component reuse | Compatible with byte-keyed document identity, canonical reconstruction, immutable ownership and existing dependency gates. |
| Browser memory and LOD policy | Proceed with a precise update to the existing cap prohibition; display budgets must not change exact trees, authored geometry, export semantics or on-disk GC. |
| Backend memory admission | Proceed with a documented daemon-policy change and dependency-progress guarantees. |
| Pre-export editor previews | Add derived objects/index entries and an internal preview input; preserve authoritative source and the saved document's separate identity. |
| Asynchronous persistence | Requires a specified publication/recovery protocol; file replacement and index updates are not a single atomic transaction. |
| Native meshing experiment | Compatible as an experiment. Shipping a second mesh backend requires explicit determinism, cache-key and export-contract decisions. |

Non-negotiable store invariants:

1. **Derived and deletable.** Authoritative edits live in project source or an editor-owned document outside the cache and outside evictable build workers. Deleting the store must not lose authored edits, change which revision an explicit save means, or require an artifact reader to execute source code.
2. **Stable addressing.** `objects/<sha256(bytes)>` and `index/document/<sha256(actual document bytes)>` keep their meanings. No source path, source/closure hash, timestamp, session ID, revision counter or machine state enters a tree/component object. New derived index namespaces are permitted with documented input keys, complete referenced objects and deletion/recovery semantics; contextual lookup belongs in an index, not geometry bytes. Do not introduce store-generation directory/name salts. Algorithm and payload-format validation must remain explicit and consistent across producers and readers.
3. **Artifact-only saved readers.** The catalog, saved-file viewer, inspect and export doors do not read `index/model` or `index/output`. Saved document lookup remains bytes → document index → complete objects; a miss compiles those bytes. Deleting model/output records must not affect artifact rendering.
4. **Immutable geometry and complete publication.** Published objects are never edited. Camera state, memory pressure and LOD selection do not change the exact tree. A reference is published only after its complete transitive object graph exists; progressive display is a partial client composition of a complete tree, not a partially published store tree.
5. **Dependency and snapshot semantics.** Preserve all five freshness-gate clauses, hashes captured at execution, children recorded from calls (including modified/discarded children), and child hashes pinned for the whole build. Missing pinned data must not be substituted with the latest child result. A retained RAM handle cannot make an incomplete disk tree appear current.
6. **Equivalent cache outcomes.** Miss, RAM hit, disk hit, worker recycling and store deletion must preserve geometry and downstream modeling behavior, including wrapper attributes, labels, face colors and subshape/reference behavior. A TShape pointer is only a reuse hint under a proven ownership/mutation invariant, not a replacement for canonical content identity.
7. **Process state stays outside persistent geometry.** Queues, allocation reservations, ownership counts, save progress and session ordering are process/editor state. They do not enter content hashes, geometry sidecars or store freshness. Keep the manual GC policy and recovery from missing cache objects; a long-lived preview must not depend on the GC grace period to retain its only authoritative data.
8. **No implied transaction or lock.** Atomic object/index writes and an atomic file rename are separate operations. Do not add correctness locks, cancellation of shared canonical jobs, or global output serialization under the label of cache optimization. Any stronger publication guarantee requires its own design decision and race/crash tests.
9. **Transparent authoring.** Existing decorated models receive the improvements without new required imports or explicit caching, session, dependency, save or memory-management utilities. Internal APIs are allowed; model authors do not orchestrate them.

Existing implementation/documentation discrepancies must not be treated as permission to extend them. In particular, the generated STEP is currently replaced and its sidecar written before the late publication decision (`store/build.py`, `step_export.py`, `_internal/generation.py`); `store/publish.py` also explicitly acknowledges a check-then-rename race. The new save path must stage before the decision and state its concurrency guarantee accurately. Existing cache-schema comments and component/tessellation versioning do not change the document index's raw-byte key contract.

## Execution order and dependencies

| Step | Work | Dependencies | Milestone |
|---|---|---|---|
| 1 | Reproducible measurements | None | Foundation |
| 2 | Imported STEP caching | 1 | Warm builds |
| 3 | Cached viewer-load CPU work | 1 | Viewer |
| 4 | Resource ownership and cancellation | 1 | Viewer |
| 5 | Complete viewer memory policy | 3, 4; document the browser memory contract | Viewer |
| 6 | Surface instancing | 4; integrate with 5 | Viewer |
| 7 | Warm-build serialization and selection overhead | 1, 2 | Warm builds |
| 8 | Backend memory admission | 1, 7; define daemon admission and dependency progress | Warm builds |
| 9 | Revision-based editing previews | 4, 7; define internal preview/index/recovery contract; coordinate with 8 | Editing |
| 10 | STEP persistence after preview publication | 9; publication/concurrency decision | Editing |
| 11 | Native OCCT display-meshing experiment | Viewer improvements and measurements | Decision |
| 12 | Integrated validation and packaging | Applicable implementation steps | Completion |

Step 11 is an evidence-gathering experiment. Replacing the mesher is not a prerequisite for completing the other improvements.

## Delegation and model selection

The user has authorized subagent delegation with explicit model and reasoning-effort choices appropriate to each task. This policy records the execution setup; implementation is underway.

Use **GPT-6 Astra (`gpt-6-astra`) with `xhigh` reasoning** for the main task. If Astra is unavailable in the main task's model picker, use **GPT-5.6 Sol (`gpt-5.6-sol`) with `xhigh` reasoning**. These are task-specific recommendations, not requirements imposed by the repository.

The main task owns architecture decisions, shared contracts, task boundaries, integration, performance interpretation and final acceptance. Delegate bounded work with explicit model and effort settings rather than having every subagent inherit the main task's settings.

| Assignment | Model | Effort | Scope |
|---|---|---|---|
| Architecture and difficult correctness review | `gpt-6-astra` | `xhigh` | Preview/save semantics, OCCT mutation and cache equivalence, memory-admission deadlocks, major cross-package changes |
| Substantial implementation | `gpt-5.6-sol` | `high` | Import caching, worker protocols, ownership, lazy selectors, instancing and bounded backend changes |
| Especially difficult implementation | `gpt-5.6-sol` | `xhigh` | Complex rendering/picking interactions or concurrency bugs after narrowing the problem |
| Benchmark instrumentation and bounded test work | `gpt-5.6-terra` | `medium` | Harness changes, fixture plumbing, focused regression tests and measurement collection |
| Independent implementation review | `gpt-5.6-sol` | `high` | Review an integrated patch against its invariants and acceptance criteria; escalate architectural questions to Astra |
| Mechanical documentation and result formatting | `gpt-5.6-luna` | `low` or `medium` | Approved documentation updates, result tables and checklist maintenance; no geometry or concurrency design decisions |

Start with at most three subagents alongside the main task, matching the current session's four total agent slots. Use fewer when dependencies or overlapping files prevent useful concurrent work. Independent work can proceed concurrently; dependent changes wait for their prerequisite interfaces and tests.

Every delegated brief must specify:

- The plan step, concrete objective and prerequisite decisions.
- Owned files and boundaries the agent must not change independently.
- Required invariants, acceptance criteria and targeted checks.
- Whether the assignment is investigation, design, implementation or independent review.
- A required return summary: changed files, validation evidence, measurements where applicable, failures and unresolved questions.

Execution rules:

- Give concurrent implementation agents non-overlapping file ownership. The agents share a workspace; ownership is coordination, not filesystem isolation.
- Keep shared schema changes and interfaces under the main task's control before assigning dependent implementations.
- Keep global Git operations and generated-runtime bundling with the main task. Do not have multiple agents regenerate bundles or manipulate branches concurrently.
- Run timed CAD/browser benchmarks without competing benchmark or build workloads. Parallel code work must not invalidate performance comparisons.
- Delegate complex patches for independent review before milestone acceptance. The main task inspects the patch and evidence instead of treating a subagent's success summary as sufficient.
- Escalate model or effort when evidence shows the task exceeds its original scope. Routine work does not automatically receive maximum effort.
- Update this plan after each accepted step with results and remaining work.

The initial assignments are measurement instrumentation and fixture support, a bounded import-cache design, and a bounded render/selector protocol design. Implementation of the latter two follows the baseline measurements and agreed interfaces. Later assignments follow the dependency table rather than launching all twelve steps together.

Model selection is informed by the [OpenAI model guidance](https://developers.openai.com/api/docs/guides/latest-model) and [subagent configuration guidance](https://learn.chatgpt.com/docs/agent-configuration/subagents), checked September 9, 2026. Actual availability and supported effort levels must be checked when spawning agents.

## 1. Establish reproducible performance measurements

- [x] Extend the existing harness under `scripts/bench/viewer-memory/` and add durable build-stage measurements where needed.
- [x] Measure unchanged builds, placement-only edits, one-component geometry edits and repeated imports of unchanged vendor STEP files separately.
- [x] Measure cold and cached viewer loads, orbiting, selection, animation and model switching on the medium fixtures. Earlier hand measurements remain historical evidence.
- [x] Exercise repeated edits and model switches to detect retained memory; distinguish the measured resource plateau from proof about all browser heap allocations.

Use the existing nine-part planetary assembly for routine development. Add an inexpensive assembly with many occurrences of a few components to expose draw-call and object-count costs, plus a curved component to exercise tessellation. Store CAD fixtures and generated artifacts under `models/`.

Record:

- Model execution, cache lookup/key construction, BREP reconstruction, packaging, STEP writing and STEP read-back.
- Fetch, cache decode, tessellation, render packing, selector construction, publication and GPU upload.
- First visible geometry, interaction readiness and full loading.
- Unique component triangles versus occurrence triangles.
- CPU buffers, GPU allocations, BVHs, worker memory and largest individual renderer RSS.
- Orbit frame-time distributions and picking latency.

Record the commit, fixture, hardware, rendering settings and cache state with every result. Keep startup and daemon IPC separate from in-process warm-build timings. Distinguish first browser paint from first model geometry.

Use small and medium fixtures for both iteration and remaining acceptance.
The user stopped further large-hand testing; it is no longer a milestone gate.

**Acceptance:** every expensive stage is attributable, results can be reproduced, and cold/warm comparisons describe the same workload and settings.

## 2. Fix imported STEP caching

Primary areas: `packages/cadgen/src/cadgen/_internal/step_scene_package.py`, the existing STEP compilation path and build-pool coordination.

- [x] Unify `read_step()` cache misses with document compilation.
- [x] Preserve document lookup by the SHA-256 of the exact bytes parsed. Handle concurrent file replacement so an index entry cannot associate one byte sequence with another sequence's geometry.
- [x] Use existing payload-format and algorithm compatibility checks; do not append kernel/schema versions to `index/document` keys or invent a new store generation naming scheme.
- [x] Parse once, publish the derived document tree, and return the same canonical representation as the hit path. Reuse the loaded scene for publication, but do not return uncanonicalized parser objects on a miss if the hit returns reconstructed BREP wrappers with different modeling behavior.
- [x] Factor out a shared publish-from-loaded-scene operation so populating the cache does not trigger another STEP parse.
- [x] Preserve assembly structure, placements, labels and face colors.
- [x] Record the same imported-file dependency on every hit and miss, using the bytes actually consumed. Preserve dependency closure tracking even when parsing is skipped; never share a mutable parsed shape between build consumers.
- [x] Coalesce concurrent compilation through the existing build pool.
- [x] Support calls inside a running model without exhausting parent/child execution slots.
- [x] Treat incomplete or deleted cache entries as recoverable misses.
- [x] Keep import compilation as a cache action: do not rewrite the imported STEP, remove its authored sidecar, or make later readers depend on an import record.

**Acceptance:** the second unchanged import performs zero text-STEP parses, including in a fresh process. Changed file contents invalidate the result. Cold and cached geometry agree.

## 3. Remove unnecessary work from cached viewer loads

Primary areas: `surfWorker.js`, `surfWorkerClient.js`, `renderAssetClient.js` and the viewer's `useCadAssets.js`.

- [x] Split render loading from selector loading in the worker protocol.
- [x] Request geometry, display edges, bounds and appearance for ordinary initial loading.
- [x] Construct full selector bundles only when selection, measurements, inspection or a render module requires them.
- [x] Resolve capabilities explicitly: a module that needs topology receives it before running.
- [x] Key selector results by component identity and the concrete mesh identity, including effective chord/angular tolerances and algorithm/payload compatibility. An LOD label alone is insufficient when its effective settings can change. Invalidate mesh-dependent face mappings when that identity changes.
- [x] Investigate a direct cached-render path that avoids fetching/parsing `.surf` when the tessellation entry contains everything required for display.
- [x] Keep exports and reference resolution on their complete-data paths.
- [x] Preserve the artifact-side mesh ledger and input-addressed tessellation cache semantics. Cache representations must identify every effective tolerance/algorithm input they depend on and reject incompatible payloads; camera or scheduling state must not silently change bytes for the same effective inputs.

**Acceptance:** ordinary initial loads perform no unnecessary selector construction. Cached display loads demonstrably skip the stages they no longer need. Picking remains correct after refinement, deformation and progressive publication.

## 4. Complete resource ownership and cancellation

The branch fixes normal scene disposal; shared resources need ownership across all consumers.

- [x] Track ownership of component geometry, edge textures, BVHs and worker tasks across scenes.
- [x] Release GPU resources after their last consumer releases them.
- [x] Separate decoded CPU-cache retention from scene/GPU ownership.
- [x] Release unpublished results promptly on model switches and superseded revisions.
- [x] Add cancellation that can stop expensive synchronous worker jobs. Use worker replacement where cooperative interruption is impractical, without cancelling unrelated requests.
- [x] Avoid routing a failed large worker job into synchronous main-thread tessellation.
- [x] Update edge-instance textures only when their contents change.

**Acceptance:** repeated load/unload cycles reach a stable memory plateau. Closing one scene does not invalidate another scene's shared resources. Superseded work stops consuming substantial CPU and memory.

## 5. Introduce a complete viewer memory policy

Extend the existing decoded-cache and admission controls into one policy covering the displayed working set.

**Design requirement:** update STORE section 11 to explicitly permit disposable browser resource budgets with the ownership, admission and reclamation rules below. Resource ownership fixes can proceed independently.

Account separately for:

- Resident component geometry.
- In-flight decode/tessellation and temporary buffers.
- Selector data and BVHs.
- GPU geometry and textures.
- Deformation copies and retained LODs.

Implement:

- [x] Allocation reservations before admitting expensive work.
- [x] Visibility- and screen-size-based loading priority.
- [x] A cheaper initial tessellation level for large assemblies.
- [x] Refinement and coarsening within the budget.
- [x] Eviction of unused detail and selector data.
- [x] Try the explicit coarse tier for an individually oversized component; refuse it with a preserved view if even that tier cannot fit. Arbitrary component partitioning is not implemented.
- [x] Explicit release of obsolete levels when a replacement becomes active.
- [x] Keep every LOD, BVH and selector eviction confined to disposable display/process data. Do not mutate exact component objects, change canonical tree identity, or trigger on-disk store GC.
- [x] Ensure a partially displayed model never publishes a tree with missing components. Do not report exact measurements or full export completion from a coarse/partial display representation.

All parts remain represented. Orbiting must not make geometry or edges disappear. Measurements and exports continue to use exact geometry or their explicitly selected export tolerance.

**Acceptance:** the complete scene fits the selected budget with documented headroom for browser overhead. An oversized request preserves the last usable view and reports its limitation instead of crashing the tab.

## 6. Instance repeated surface meshes

The branch instances edges; surfaces still create a mesh/material per occurrence.

- [x] Group compatible occurrences by concrete component/mesh identity, material and render pass; do not assume an LOD label uniquely identifies tessellation settings.
- [x] Store transforms and per-occurrence visual state in instance data.
- [x] Preserve stable occurrence IDs independently of instance-buffer positions.
- [x] Support selection, highlighting, visibility, opacity, exploded views and clipping.
- [x] Handle mirrored placements and normal transforms correctly.
- [x] Keep explicit separate paths where transparency ordering or individual deformation requires them.
- [x] Resolve picking through the instance ID into the component's shared geometry and topology.

**Acceptance:** repeated-part surface draw calls scale primarily with compatible component groups. Visual and selection behavior matches the existing renderer. Measure both draw-call reduction and actual frame-time improvement.

Steps 3–6 complete the viewer milestone.

## 7. Reduce warm-build serialization and selection overhead

Profile and improve the existing operation and component caches before introducing a new document model.

- [x] Measure BREP key construction, reconstruction, subshape equality/hashing and assembly traversal independently.
- [x] Reuse immutable component identities across builds after verifying native geometry and hierarchy metadata. Native pointer identity alone is insufficient.
- [x] Carry known component identity through unchanged placements instead of rediscovering it by serialization. A full native/metadata integrity check remains; forced extraction reads the pinned BREP, and missing assets take the canonical derivation path.
- [x] Give materialization caching explicit ownership and lifecycle. Replace the process-global live prototypes with a 64 MiB canonical-byte LRU; each independent consumer reconstructs its own kernel shapes, and resetting the memo leaves active geometry valid. Integrate process reclamation with step 8.
- [x] Optimize canonical `_StoredShape` bytes, attribute recipes and redundant work, retaining fresh operation-result reconstruction as the proven default. A measured internal live-reuse design may replace that mechanism only after demonstrating equivalent geometry, subshape behavior and Python attributes across misses, RAM/disk hits and mutation sequences. Shallow copying alone is not sufficient evidence. No ownership or cache helpers may be required in agent-authored code.
- [x] Preserve canonical reconstruction wherever component reuse cannot be proven equivalent. Releasing a materialization-cache reference must not invalidate geometry still owned by an active or suspended build.
- [x] Build on decorated-child dependencies so a local edit invalidates the smallest supported subgraph.
- [x] Capture dependencies and reuse internally through existing decorated calls and runtime observation. Do not require a new feature-graph builder or explicit dependency-registration utility; arbitrary Python control flow still limits the granularity we can safely infer.
- [x] Retain the existing gate and dependency semantics: discover children from calls, retain execution-time source hashes and constant-value dependencies, and honor frozen child pins even if a newer child finishes.
- [x] Verify that measurements, tessellation, booleans and wrapper metadata changes cannot invalidate a carried identity or mutate shared cached shapes. Reconstruct/copy when that proof does not hold.

Preserve the branch's determinism protections. Returning shared mutable cached shapes directly would reintroduce previously fixed geometry bugs. The implementation retains reusable canonical bytes and gives each consumer independent geometry. Native identity reuse requires a fresh integrity check after arbitrary mutation. The verified link avoids repackaging unchanged children, but checking mutable leaf geometry still requires serialization; eliminating that check remains unproven.

**Acceptance:** unchanged and placement-only components avoid unnecessary reconstruction and hashing. Cold, RAM-cache and disk-cache execution produce equivalent geometry, topology, colors, wrapper behavior and deterministic outputs; mutation or meshing in one build cannot change the next build's cached component identity or bytes. Any replacement for canonical reconstruction must pass the same regression cases and mutation tests before adoption.

## 8. Bound backend memory without breaking dependency scheduling

Add memory-aware admission to the daemon and component-extraction pool.

**Design requirement:** replace STORE.md's backend memory/worker-cap prohibition with precise process-memory admission/reclamation and worker-limit rules. Preserve manual-only persistent-store GC and keep reader freshness independent of locks. Land the contract update with its implementation; the user's extension direction covers this policy change.

- [x] Include resident worker memory and extraction subprocesses in accounting.
- [x] Reclaim idle caches/workers under pressure before admitting more work.
- [x] Preserve CPU-slot coalescing and parent/child scheduling.
- [x] Account for suspended parents: yielding a CPU slot does not release their geometry.
- [x] Reserve enough capacity for dependency progress to avoid memory-budget deadlocks.
- [x] Run known oversized reservations alone when feasible; otherwise fail admission. Future native allocation remains a soft-budget limitation, not a promised hard RSS cap.
- [x] Keep disk-cache deletion and in-memory reclamation as separate policies.
- [x] Reclaim only disposable state. Retain active parent snapshots and all consumers of coalesced jobs; eviction or subscriber cancellation must not substitute newer child geometry or cancel work still required by another parent or explicit request.

**Acceptance:** concurrent builds remain within the configured operating envelope, nested builds still complete under a one-job configuration, and memory pressure cannot deadlock the pool.

Steps 2, 7 and 8 complete the warm-build milestone.

## 9. Introduce revision-based editing previews

This is the main step toward FreeCAD-like edit latency.

A build produces an immutable editing revision containing component identities, occurrences, placements, appearance and required derived assets.

**Design requirement:** define the internal preview input and any derived index entries. Decorated execution publishes immutable preview results automatically, and the viewer subscribes through cadgen's runtime. Ordinary saved-file rendering retains the current artifact-only contract. For code edits, existing project source is authoritative; runtime-owned revision snapshots support pending explicit saves. No separate preview artifact, session import or persistence utility is required from the agent. Recovery belongs to the editing/build runtime and must not teach saved-artifact readers to execute source.

- [x] Publish changed components and occurrence changes to an explicitly attached editing session.
- [x] Retain canonical backend bytes with private reconstruction, and retain unchanged browser resources. Shared mutable backend prototypes were rejected by native mutation tests; literal live-shape retention is superseded by this ownership design.
- [x] Discard superseded revision results before preview publication; explicit saves still complete under the specified competing-writer guarantee.
- [x] Continue whole-function execution for arbitrary Python models; finer invalidation uses existing explicit model boundaries.
- [x] Reconcile placement and appearance changes onto retained geometry when decorated results establish that underlying component geometry is unchanged; do not require agents to call a separate editing API.
- [x] Record authored changes in project source or an editor-owned document outside the disposable cache and evictable workers. Specify crash/restart behavior and ownership for unsaved state before offering these edits.
- [x] Make the complete authored preview the final source-model result, with schema-3 records invalidating the former STEP-translated own-component semantics. Exact child jobs publish and replay this result before persistence. `record.tree` is updated only after save publication checks; `index/document` remains exclusively byte-derived.
- [x] Keep session identifiers, revision counters, provenance and save status outside geometry objects and geometry sidecars. Session controls must not require the viewer to read model/output records.
- [x] Define any new preview/revision index's input identity, object references, reachability and recovery after deletion or a crash. Keep it within the existing object/index layout; it must not be the only record of an authored change or the only owner of a promised explicit-save revision.
- [x] Freeze transitive child pins and annotation inputs for each accepted preview. A cache miss or newer child build must not silently alter that revision.
- [x] Keep ordinary file opening tied to the saved document.
- [x] Keep kernel work in build workers; the viewer server only brokers revision events and derived assets.
- [x] Distinguish the current preview from the saved file with understandable saving/error states.
- [x] Update package, store and viewer contracts for the explicit preview input.

**Acceptance:** a preview update can appear before the root's own STEP export completes and before its children's STEP persistence. Parents consume each job's complete final authored result, never a provisional pin or a later model-record lookup. Every called child still completes all declared outputs before its parent saves; failures preserve the parent's prior saved file. One-slot nesting yields and resumes correctly. Unchanged components are neither retransmitted nor reuploaded. A session rejects superseded preview results. Authored edits survive cache deletion and worker eviction under the editor's stated durability contract.

## 10. Move STEP persistence behind preview publication

Retain the branch's read-back consistency check for saved files.

**Design requirement:** specify and document the publication, failure-recovery and competing-writer protocol within the expanded runtime. A strict promise that an older or external writer can never win cannot be derived from a digest check followed by rename. Keep any required save coordination internal, preserve ordinary build completion guarantees and update the concurrency contract alongside implementation.

- [x] Export from one immutable transitive revision snapshot, including its pinned child hashes and annotation inputs. Do not resolve current child records again at export time.
- Automatic-export coalescing is not applicable to the implemented explicit-build flow: there is no automatic-save queue. All requested outputs remain required. Any future queue must distinguish dispensable automatic exports from explicit saves and other consumers without changing canonical build coalescing implicitly.
- [x] Make an explicit save await the requested revision.
- [x] Export and read back a private temporary document, without replacing the user's target during tree construction. Keep staging outside the persistent store layout.
- [x] Publish complete immutable components and the read-back tree, then their mapping under the validated document-byte hash. After validation and the publication decision, atomically replace the target document; publish validated sidecar/output state and the model record in the specified order, with the record last.
- [x] Treat file replacement, sidecar writes and index updates as separate atomic operations, not a multi-file transaction. Specify recovery for a crash or cache deletion between each boundary; readers must resolve the bytes actually present and compile missing derived state.
- [x] Preserve the last valid saved file if export fails.
- [x] Specify output-path ownership, expected previous document digest, explicit-save completion and behavior under competing CLI/editor/external writers. Detect external changes without claiming that check-then-rename provides atomic exclusion.
- [x] If STEP translation changes the geometry, publish a distinct saved identity and reconcile selection and resolved kinematics explicitly. Never mutate the preview tree or map the saved STEP bytes to the pre-export geometry.

**Acceptance:** root-preview publication does not wait for that root's STEP write/read-back. A successful save identifies the validated persisted revision under the agreed concurrency guarantee, and cached saved-file geometry agrees with a cold import. Injected failures between publication stages never expose partial STEP bytes or require source/record reads to recover a saved artifact.

Steps 9–10 complete the editing milestone. Revision-based preview must land before asynchronous persistence.

## 11. Benchmark native OCCT display meshing

Run this as a measured architectural experiment after avoidable buffer and loading costs are removed.

- [x] Compare native OCCT triangulation with the JS mesher using explicit sampled geometric quality criteria. Equal visual quality and continuous error bounds remain unproven; they are adoption requirements for a future native renderer.
- [x] Cover curved and trimmed surfaces, seams, normals and welded-edge diagnostics on the two bounded corpora.
- [x] Audit face/reference and edge ranges. Native interactive picking and edge display were not integrated; production JS behavior retains its renderer tests.
- [x] Measure uncached meshing, cached decode, transport size and process memory, with startup and delivery boundaries stated.
- [x] Exercise both LODs and component reuse in the experiment. Native interactive instancing remains an adoption requirement, not a prerequisite for retaining JS.
- [x] Mesh private reconstructions so OCCT triangulation cannot mutate shared inputs. Verify fresh-process byte determinism and record native mutation of the private shape's BREP serialization.
- [x] Record a decision with the measured benefits, maintenance costs and contract implications.

Adopt native display meshing only if the measured benefit justifies the change. If viewport meshes differ from export meshes, specify that distinction explicitly and preserve exact selection/measurement semantics.

**Adoption requirement:** README law 5 currently specifies one deterministic tessellator. Use the benchmark to choose a replacement canonical mesher or an explicit display-only derivation, and update that contract if adopting the change. Different algorithms or effective parameters must not share a mesh-cache entry or export-ledger identity; scheduling, hardware, cache hits and memory pressure must not silently select different export bytes. Cadgen chooses and runs the backend internally; no new meshing utility is required in model scripts.

**Acceptance:** an evidence-backed decision. Replacing the mesher is not required to complete the other improvements.

## 12. Validate and package the completed branch

These are proposed targets to confirm on fixed reference hardware, not claims about achieved performance.

| Workload | Proposed target |
|---|---|
| Unchanged nine-part build | Under 50 ms, excluding startup |
| Repeated vendor import | Zero text-STEP parsing |
| Warm local-edit preview | Under 250 ms for the nine-part fixture |
| Orbiting | p95 frame time under 33 ms at agreed settings |
| Repeated model switches | No continuing growth in retained resources |

The original large-hand first-geometry, full-load and 2 GiB targets are retained
only in the historical measurement reports. The user's September 11 direction
replaces further hand acceptance runs with moderate assemblies; it does not
establish those targets for later runtimes.

- [x] Validate colors, assemblies, references, mirrored instances, clipping, deformation, animation, measurements and exports.
- [x] Exercise the viewer, snapshots, video and the packaged wheel.
- [x] Test cold caches, RAM hits, disk hits, cache deletion, failed work, cancellation and superseded revisions.
- [x] Exercise existing decorated model scripts unchanged. Verify the new caching, dependency, preview and persistence behavior requires no added utility imports or author-managed cache/session state.
- [x] Validate each added index namespace's input identity, atomic publication, complete object references, GC reachability and recovery; assert no parallel persistent-cache layout is introduced.
- [x] Extend the existing store-invariant tests to forbid model/output-record reads in saved readers; remove those records and verify rendering/export still work; move/copy documents and verify byte-based reuse.
- [x] Repair the confirmed identical-STEP/different-PBR document-index collision and generated/cold-import names/grouping mismatch. Follow the saved-identity repair design; preserve appearance durably and validate appearance-sensitive export keys.
- [x] Test whole-store deletion, missing transitive objects, worker eviction and GC during retained revisions. Prove no authored data loss, pin substitution or cache-dependent geometry.
- [x] Inject failures after each save publication boundary and race older/newer revisions, concurrent child updates and competing writers. Assert only the concurrency guarantees actually specified by the accepted design.
- [x] Verify source paths, timestamps and session metadata never enter geometry objects, and that camera/LOD/memory decisions do not change exact tree hashes or canonical export bytes.
- [x] Use focused Python and JS suites during development.
- [x] Run shared checks before final handoff, including affected viewer-backend tests.
- [x] Build the viewer production client and run affected documentation checks.
- [x] Regenerate consumed runtime outputs with `scripts/bundle/bundle.sh` and verify with `scripts/bundle/bundle.sh --check`.
- [x] Include generated runtime changes in the relevant commits; keep `VERSION` unchanged.
- [x] Record frozen-runtime measurements, identify later correctness changes, and retain explicit unvalidated targets. Repeat the nine-part study after the saved-document repair; the earlier hand result is historical evidence.

Relevant repository commands:

```bash
npm --prefix packages/cadgen-js test
npm --prefix apps/viewer run test
npm --prefix apps/viewer run build
scripts/test/test-python.sh
npm --prefix apps/docs run check
scripts/bundle/bundle.sh
scripts/bundle/bundle.sh --check
scripts/test/test.sh
```

Use the smallest relevant checks during each step and the shared checks for integrated validation. Do not repeatedly run the large assembly or broad suites without a change or unresolved concern that justifies them.

## Completion criteria

The branch is ready when the selected performance targets are verified, correctness and package checks pass, and the viewer/build contracts describe the implemented behavior. Store/runtime expansion is authorized within the object/index and decorator-only boundaries. Resolve and document internal schema, ownership and publication designs before dependent implementation; verify existing model scripts benefit unchanged.

The highest-value immediate work is imported-document caching, lazy selector construction, complete memory ownership and surface instancing. Persistent editing revisions and asynchronous STEP persistence then address the remaining architectural difference between a fast viewport update and a complete saved-file rebuild.
