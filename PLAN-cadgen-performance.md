# Cadgen performance execution plan

## Execution status — September 10, 2026

The implementation below is committed on `codex/tendon-hand-performance`, based on the
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
- Warm materialization ownership: implemented; a bounded canonical-byte LRU
  replaces cross-consumer shared mutable kernel prototypes. Fresh independent
  materialization costs about 4 ms on the nine-part fixture. Op-memo misses
  reuse their verified ephemeral reconstruction, removing one BREP read while
  storing only canonical bytes and attribute recipes.
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
- Schema-7 sidecars: implemented; kinematics bind to saved STEP SHA-256, stale
  pairs report annotation errors, imported authored sidecars are preserved.
- Durable build benchmark: added under `scripts/bench/cadgen-performance`.
  Native OCCT meshing is evaluated; the current JS mesher is retained.
  See [the measured study](scripts/bench/cadgen-performance/RESULTS-20260910.md).
  Integrated packaging and browser lifecycle validation pass. See the
  [validation record](scripts/bench/cadgen-performance/VALIDATION-20260910.md).

Current unprofiled measurements on M1 Max / 64 GiB, the nine-part fixture:
unchanged median 18.34 ms, cached geometry edit 926.20 ms, placement edit
927.67 ms; preview publication roughly 521–530 ms, saved result 919–930 ms.
The 250 ms preview objective is **not met**. Repeated unchanged 2.27 MB imports
are 28.49–30.23 ms with compile submission forbidden. A cold import including
its compile subprocess is 6.69 s; that is not kernel parse time alone. These
final measurements use committed runtime `43b233233`; the original study is
retained alongside them in the benchmark report.

Core integration gates pass: 1,804 package/skill Python tests, 922 shared JS
tests, 372 viewer tests, global policies (126 tests, one skipped), viewer/docs
builds, bundle freshness, version pins, and installed-wheel build/export/render
checks. Unchecked items below and the explicit limits remain follow-up work;
no claim is made that all original performance targets have been achieved.

Runtime commits: `9d6afe240` (imports), `1405be434` (kernel ownership),
`fac454929` (daemon admission/order), `989ed7b80` (preview/save and annotations),
`43b233233` (viewer loading, instancing and resource lifecycle).


Original target: `codex/tendon-hand-preview`; implementation branch: `codex/tendon-hand-performance`.

Reviewed baseline: `7aa3e85be76f305437abd3d7aba26e38b28e43cb`, fetched September 9, 2026.

## Remaining acceptance work

The implementation does not imply full FreeCAD parity. The measured warm model
body still takes roughly 426–455 ms, before preview packing, and arbitrary Python
still reruns at the decorated function boundary. Unsafe reuse of mutable kernel
shapes was rejected; per-consumer reconstruction adds about 4 ms on this fixture.
The changes provide earlier display and cheaper cached reads, not a demonstrated
reduction in total warm-save time.

The following items are explicit limits of this implementation:

- The under-250-ms warm-preview target is unmet. A further optimization needs a
  proven mutation boundary or finer existing decorated-model boundaries; no
  source-author cache/session helpers are introduced.
- The viewer uses existing LODs and refuses an initial component that cannot fit
  its soft budget. It does not yet partition an oversized component or create
  an additional emergency coarse representation. It preserves usable geometry
  and reports the limitation instead of claiming complete loading.
- Native meshing was compared at equal input tolerances, not proven matched
  visual quality. The experiment supports retaining JS and records its quality
  audit flags for a separate investigation.
- The very large hand has not been rerun in this work. Medium fixtures are used
  for routine validation as requested; the large-hand speed/RSS targets remain
  milestone checks, not achieved claims.
- Preview handles are ephemeral and not manual-GC roots. Source and saved STEP
  remain durable; worker/restart/cache-loss behavior is stated in STORE.md.
- Saves remain explicit builds. There is no automatic-save queue, cancellation
  of shared canonical jobs, or provisional-child pin substitution. Check/rename
  publication detects observed conflicts but is not a cross-writer transaction.

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

Introduce browser and backend memory management within the approved runtime extension. [STORE.md](packages/cadgen/STORE.md), sections 9 and 11, currently prohibits memory/worker caps; replace that policy with precise admission, ownership and reclamation rules alongside implementation. The old prohibition is a documented policy change to make, not a reason to drop these optimizations.

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
- [ ] Measure cold and cached viewer loads, orbiting, selection, animation and model switching.
- [ ] Exercise repeated edits and model switches to detect retained memory.

Use the existing nine-part planetary assembly for routine development. Add an inexpensive assembly with many occurrences of a few components to expose draw-call and object-count costs, plus a curved component to exercise tessellation. Store CAD fixtures and generated artifacts under `models/`.

Record:

- Model execution, cache lookup/key construction, BREP reconstruction, packaging, STEP writing and STEP read-back.
- Fetch, cache decode, tessellation, render packing, selector construction, publication and GPU upload.
- First visible geometry, interaction readiness and full loading.
- Unique component triangles versus occurrence triangles.
- CPU buffers, GPU allocations, BVHs, worker memory and largest individual renderer RSS.
- Orbit frame-time distributions and picking latency.

Record the commit, fixture, hardware, rendering settings and cache state with every result. Keep startup and daemon IPC separate from in-process warm-build timings. Distinguish first browser paint from first model geometry.

The large hand is a bounded milestone check using its existing artifacts, not an everyday rebuild. Routine development should use small and medium fixtures.

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
- [ ] Add cancellation that can stop expensive synchronous worker jobs. Use worker replacement where cooperative interruption is impractical, without cancelling unrelated requests.
- [ ] Avoid routing a failed large worker job into synchronous main-thread tessellation.
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
- [ ] A cheaper initial tessellation level for large assemblies.
- [x] Refinement and coarsening within the budget.
- [x] Eviction of unused detail and selector data.
- [ ] Safe handling of a single oversized component through coarser geometry or partitioning.
- [x] Explicit release of obsolete levels when a replacement becomes active.
- [ ] Keep every LOD, BVH and selector eviction confined to disposable display/process data. Do not mutate exact component objects, change canonical tree identity, or trigger on-disk store GC.
- [ ] Ensure a partially displayed model never publishes a tree with missing components. Do not report exact measurements or full export completion from a coarse/partial display representation.

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
- [ ] Reuse immutable component identities across builds where ownership makes that safe.
- [ ] Carry known component identity through unchanged placements instead of rediscovering it by serialization.
- [ ] Give the existing process-global live materialization cache explicit ownership and lifecycle. Its `reset_memo()` comment does not establish build-scoped behavior: production currently never calls it. Treat retained component prototypes as immutable and integrate accounting/reclamation with step 8.
- [ ] Optimize canonical `_StoredShape` bytes, attribute recipes and redundant work, retaining fresh operation-result reconstruction as the proven default. A measured internal live-reuse design may replace that mechanism only after demonstrating equivalent geometry, subshape behavior and Python attributes across misses, RAM/disk hits and mutation sequences. Shallow copying alone is not sufficient evidence. No ownership or cache helpers may be required in agent-authored code.
- [ ] Preserve canonical reconstruction wherever component reuse cannot be proven equivalent. Releasing a materialization-cache reference must not invalidate geometry still owned by an active or suspended build.
- [ ] Build on decorated-child dependencies so a local edit invalidates the smallest supported subgraph.
- [ ] Capture dependencies and reuse internally through existing decorated calls and runtime observation. Do not require a new feature-graph builder or explicit dependency-registration utility; arbitrary Python control flow still limits the granularity we can safely infer.
- [ ] Retain the existing gate and dependency semantics: discover children from calls, retain execution-time source hashes and constant-value dependencies, and honor frozen child pins even if a newer child finishes.
- [ ] Verify that measurements, tessellation, booleans and wrapper metadata changes cannot invalidate a carried identity or mutate shared cached shapes. Reconstruct/copy when that proof does not hold.

Preserve the branch's determinism protections. Returning shared mutable cached shapes directly would reintroduce previously fixed geometry bugs. Some component shapes already survive across builds; this step formalizes and extends safe reuse rather than assuming every shape is currently discarded.

**Acceptance:** unchanged and placement-only components avoid unnecessary reconstruction and hashing. Cold, RAM-cache and disk-cache execution produce equivalent geometry, topology, colors, wrapper behavior and deterministic outputs; mutation or meshing in one build cannot change the next build's cached component identity or bytes. Any replacement for canonical reconstruction must pass the same regression cases and mutation tests before adoption.

## 8. Bound backend memory without breaking dependency scheduling

Add memory-aware admission to the daemon and component-extraction pool.

**Design requirement:** replace STORE.md's backend memory/worker-cap prohibition with precise process-memory admission/reclamation and worker-limit rules. Preserve manual-only persistent-store GC and keep reader freshness independent of locks. Land the contract update with its implementation; the user's extension direction covers this policy change.

- [x] Include resident worker memory and extraction subprocesses in accounting.
- [x] Reclaim idle caches/workers under pressure before admitting more work.
- [x] Preserve CPU-slot coalescing and parent/child scheduling.
- [x] Account for suspended parents: yielding a CPU slot does not release their geometry.
- [x] Reserve enough capacity for dependency progress to avoid memory-budget deadlocks.
- [ ] Run oversized jobs alone when feasible; otherwise fail predictably before uncontrolled allocation.
- [x] Keep disk-cache deletion and in-memory reclamation as separate policies.
- [ ] Reclaim only disposable state. Retain active parent snapshots and all consumers of coalesced jobs; eviction or subscriber cancellation must not substitute newer child geometry or cancel work still required by another parent or explicit request.

**Acceptance:** concurrent builds remain within the configured operating envelope, nested builds still complete under a one-job configuration, and memory pressure cannot deadlock the pool.

Steps 2, 7 and 8 complete the warm-build milestone.

## 9. Introduce revision-based editing previews

This is the main step toward FreeCAD-like edit latency.

A build produces an immutable editing revision containing component identities, occurrences, placements, appearance and required derived assets.

**Design requirement:** define the internal preview input and any derived index entries. Decorated execution publishes immutable preview results automatically, and the viewer subscribes through cadgen's runtime. Ordinary saved-file rendering retains the current artifact-only contract. For code edits, existing project source is authoritative; runtime-owned revision snapshots support pending explicit saves. No separate preview artifact, session import or persistence utility is required from the agent. Recovery belongs to the editing/build runtime and must not teach saved-artifact readers to execute source.

- [x] Publish changed components and occurrence changes to an explicitly attached editing session.
- [ ] Retain unchanged backend shapes and browser resources.
- [ ] Discard superseded revision results before publication.
- [x] Continue whole-function execution for arbitrary Python models; finer invalidation uses existing explicit model boundaries.
- [ ] Reconcile placement and appearance changes onto retained geometry when decorated results establish that underlying component geometry is unchanged; do not require agents to call a separate editing API.
- [ ] Record authored changes in project source or an editor-owned document outside the disposable cache and evictable workers. Specify crash/restart behavior and ownership for unsaved state before offering these edits.
- [ ] Keep preview roots distinct from canonical STEP-model result roots. Preview publication does not replace `record.tree`, canonical child pins, or `index/document` before successful saved-result publication.
- [ ] Keep session identifiers, revision counters, provenance and save status outside geometry objects and geometry sidecars. Session controls must not require the viewer to read model/output records.
- [ ] Define any new preview/revision index's input identity, object references, reachability and recovery after deletion or a crash. Keep it within the existing object/index layout; it must not be the only record of an authored change or the only owner of a promised explicit-save revision.
- [ ] Freeze transitive child pins and annotation inputs for each accepted preview. A cache miss or newer child build must not silently alter that revision.
- [x] Keep ordinary file opening tied to the saved document.
- [x] Keep kernel work in build workers; the viewer server only brokers revision events and derived assets.
- [x] Distinguish the current preview from the saved file with understandable saving/error states.
- [x] Update package, store and viewer contracts for the explicit preview input.

**Acceptance:** a preview update can appear before the root's own STEP export completes. Unchanged components are neither retransmitted nor reuploaded. A session rejects superseded preview results. Authored edits survive cache deletion and worker eviction under the editor's stated durability contract. Existing child jobs may still await their own STEP persistence; eliminating that dependency requires a separate decision about provisional child results and cannot silently change canonical pin semantics.

## 10. Move STEP persistence behind preview publication

Retain the branch's read-back consistency check for saved files.

**Design requirement:** specify and document the publication, failure-recovery and competing-writer protocol within the expanded runtime. A strict promise that an older or external writer can never win cannot be derived from a digest check followed by rename. Keep any required save coordination internal, preserve ordinary build completion guarantees and update the concurrency contract alongside implementation.

- [ ] Export from one immutable transitive revision snapshot, including its pinned child hashes and annotation inputs. Do not resolve current child records again at export time.
- [ ] Coalesce superseded editor-session automatic exports only when no explicit save or other consumer still requires that revision. Do not change canonical same-model build/coalescing rules implicitly.
- [x] Make an explicit save await the requested revision.
- [x] Export and read back a private temporary document, without replacing the user's target during tree construction. Keep staging outside the persistent store layout.
- [ ] Publish complete immutable components and the read-back tree, then their mapping under the validated document-byte hash. After validation and the publication decision, atomically replace the target document; publish validated sidecar/output state and the model record in the specified order, with the record last.
- [ ] Treat file replacement, sidecar writes and index updates as separate atomic operations, not a multi-file transaction. Specify recovery for a crash or cache deletion between each boundary; readers must resolve the bytes actually present and compile missing derived state.
- [x] Preserve the last valid saved file if export fails.
- [ ] Specify output-path ownership, expected previous document digest, explicit-save completion and behavior under competing CLI/editor/external writers. Detect external changes without claiming that check-then-rename provides atomic exclusion.
- [ ] If STEP translation changes the geometry, publish a distinct saved identity and reconcile selection and resolved kinematics explicitly. Never mutate the preview tree or map the saved STEP bytes to the pre-export geometry.

**Acceptance:** root-preview publication does not wait for that root's STEP write/read-back. A successful save identifies the validated persisted revision under the agreed concurrency guarantee, and cached saved-file geometry agrees with a cold import. Injected failures between publication stages never expose partial STEP bytes or require source/record reads to recover a saved artifact.

Steps 9–10 complete the editing milestone. Revision-based preview must land before asynchronous persistence.

## 11. Benchmark native OCCT display meshing

Run this as a measured architectural experiment after avoidable buffer and loading costs are removed.

- [ ] Compare native OCCT triangulation with the JS mesher at matched visual quality.
- [ ] Cover curved and trimmed surfaces, seams, normals and watertightness.
- [ ] Verify face/reference mapping and edge display.
- [ ] Measure cold meshing, cached loading, transport size and memory.
- [ ] Exercise component instances and LODs.
- [ ] Mesh worker-owned reconstructions so OCCT triangulation cannot mutate a shared prototype or change its canonical BREP/component identity. Verify determinism across fresh processes and cache states for each effective mesh key.
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
| Large-hand first geometry | Preserve approximately 5-second performance |
| Large-hand full load | Beat the former 86–90-second baseline |
| Large-hand memory | Under 2 GiB peak in the largest renderer, with headroom |
| Orbiting | p95 frame time under 33 ms at agreed settings |
| Repeated model switches | No continuing growth in retained resources |

- [ ] Validate colors, assemblies, references, mirrored instances, clipping, deformation, animation, measurements and exports.
- [x] Exercise the viewer, snapshots, video and the packaged wheel.
- [ ] Test cold caches, RAM hits, disk hits, cache deletion, failed work, cancellation and superseded revisions.
- [ ] Exercise existing decorated model scripts unchanged. Verify the new caching, dependency, preview and persistence behavior requires no added utility imports or author-managed cache/session state.
- [ ] Validate each added index namespace's input identity, atomic publication, complete object references, GC reachability and recovery; assert no parallel persistent-cache layout is introduced.
- [ ] Extend the existing store-invariant tests to forbid model/output-record reads in saved readers; remove those records and verify rendering/export still work; move/copy documents and verify byte-based reuse.
- [ ] Test whole-store deletion, missing transitive objects, worker eviction and GC during retained revisions. Prove no authored data loss, pin substitution or cache-dependent geometry.
- [ ] Inject failures after each save publication boundary and race older/newer revisions, concurrent child updates and competing writers. Assert only the concurrency guarantees actually specified by the accepted design.
- [ ] Verify source paths, timestamps and session metadata never enter geometry objects, and that camera/LOD/memory decisions do not change exact tree hashes or canonical export bytes.
- [x] Use focused Python and JS suites during development.
- [x] Run shared checks before final handoff, including affected viewer-backend tests.
- [x] Build the viewer production client and run affected documentation checks.
- [ ] Regenerate consumed runtime outputs with `scripts/bundle/bundle.sh` and verify with `scripts/bundle/bundle.sh --check`.
- [ ] Include generated runtime changes in the relevant commits; keep `VERSION` unchanged.
- [ ] Update the performance handoff with final-commit measurements and remaining limitations.

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
