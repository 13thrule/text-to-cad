# Cadgen document engine: execution plan

Status: proposed replacement architecture and implementation plan, 13 September 2026. This document does not report implemented functionality or measured future speedups. The existing runtime, including @memo, remains in place until the replacement passes its cutover gates.

This plan supersedes the architectural restrictions of the earlier performance plan for future work. Historical measurements remain evidence, not acceptance of this design. The user authorizes replacing the store, daemon internals and decorator-backed caching, removing @memo, and keeping the existing @step authoring interface. No old store or runtime compatibility is required.

## 1. Outcome and scope

Build a retained, revisioned CAD document engine. Python describes geometry; the engine owns computation dependencies, native results, assembly occurrences, inspection and downstream derivations. STEP is an exchange representation of a document, rather than the interchange between every stage of our own application.

The work must improve all of these independently:

- Initial generation and cold document import.
- Unchanged calls, source edits, parameter changes and placement changes.
- Exact inspection, topology selection and measurements.
- First visible geometry, complete requested detail and subsequent viewer updates.
- CAD snapshots, photographic snapshots, animation and video.
- STEP and mesh export completion, startup cost, memory use and recovery.

FreeCAD parity here means comparable retained-document behavior and measured headless geometry performance for our supported workloads. It does not mean rebuilding FreeCAD's entire GUI, workbench catalog, sketch solver or every modeling feature. Photographic quality, browser rendering and native GLB animation have separate acceptance criteria; the earlier FreeCADCmd benchmark does not measure those systems.

### Preserve the author interface

- Keep @step signatures, parameterless model functions, child-call composition, output declarations and successful-call completion obligations. Keep the existing format decorators and CLI doors working through the new engine.
- Keep normal Python source as the durable authority for source-authored models. Keep the common cadgen.build123d authoring spelling, algebra and builder workflows as the frontend coverage target.
- Remove public @memo, its environment controls and its purity contract at cutover. No replacement cache, graph, ownership or session utility is required from model authors.
- A returned shape remains usable by supported callers. Managed internal handles do not justify silently changing native mutation or aliasing behavior.
- Imported files remain independently usable without their Python source. Opening a STEP must never quietly run source or show different geometry because a source document happens to be resident.

Keeping @step does not require preserving its current implementation. Conversely, keeping its interface does not establish transparent compatibility with every direct OCP call or every build123d implementation detail. Native escapes and the supported frontend contract are explicit gates below.

## 2. Architecture to build

~~~mermaid
flowchart TD
    A[Python source with existing step decorators] --> B[Graph-aware authoring frontend]
    B --> C[Retained document and revision scheduler]
    D[Imported STEP or mesh] --> C
    C --> E[Native geometry and topology queries]
    C --> F[Prototype meshes and occurrence deltas]
    C --> G[STEP and mesh exporters]
    F --> H[Shared scene runtime]
    H --> I[Inspect viewer]
    H --> J[Photographic Render and animation]
    H --> K[Persistent snapshot renderer]
    C <--> L[Transactional checkpoints and derived asset storage]
~~~

### 2.1 Separate Python execution from geometry execution

Initially, execute Python in a fresh authored namespace for each source revision. Supported CAD operations register typed graph computations and consume managed geometry handles. Unchanged operations reuse resident results without serializing, hashing and reconstructing their BREP on every call.

Ordinary Python loops, conditionals, I/O and callbacks still execute. Geometry-dependent queries evaluate their graph prerequisites before Python consumes the value. This allows a changed measurement to change control flow correctly. Capture the source and declared external-input versions actually consumed; do not hash one revision and execute another.

Execute source/import inputs from immutable captured bytes. Managed data readers bind bytes and dependency identity together; declaring a path and reading it later is not equivalent. Uncontrolled I/O or process-state dependencies make that authored region volatile, so an unchanged-call gate cannot skip it on an unproven dependency fingerprint. Preserve ordinary execution while still reusing managed geometry operations whose actual inputs match.

The first operator set covers primitives, rigid transforms, assembly occurrence creation, booleans, extrusion/revolution, common sketch/build contexts, fillet/chamfer and topology queries. Expand coverage from fixture evidence. Operation fusion and batching may reduce dispatch overhead, but must preserve model semantics and useful invalidation boundaries.

A later frontend increment can lower proven supported CAD regions into reusable subgraphs to avoid Python/builder replay too. AST matching is useful for reconciliation, not proof that arbitrary Python is pure. Unsupported/native regions execute normally on private inputs and publish a newly captured result. This is one execution engine with explicit opaque operations, not a permanent copy of the old cache backend.

### 2.2 Three different identities

Do not conflate these:

| Identity | Purpose |
| --- | --- |
| Logical feature/occurrence identity | Track a computation or assembly occurrence through a source edit |
| Evaluation identity | Operator and implementation version, normalized parameters, actual input revisions, tolerances and relevant runtime configuration |
| Stored representation identity | Identify the exact bytes of a checkpoint, mesh, exchange file or other stored representation |

Line numbers, call ordinals, native pointer addresses and approximate geometric signatures are insufficient universal identifiers. Reconcile source structure, call context and occurrence provenance; when correspondence is ambiguous, rebuild the affected region and invalidate ambiguous references. Reordering identical parts must not silently move a selection onto another occurrence.

Document dependencies form an execution graph. An assembly containment tree and a kinematic constraint graph are different structures. Constraint cycles belong inside solver computations; they must not create scheduler deadlocks.

### 2.3 Retained native ownership

One owning kernel process manages an active document's native results and revision lifetimes. Reuse immutable prototypes; store placements, labels, material overrides and occurrence membership separately. Placement edits do not rebuild solids or remesh their prototypes.

Co-locate a root and its called child models as a document family where possible. Separate output declarations do not require separate native processes. A child shared across independent families transfers a pinned prototype revision once into each owner, then reuses it there. Nested parent edits must not repeatedly serialize or decode unchanged children.

Operations must explicitly declare their mutation behavior. Use proven non-destructive kernel operations where available; copy at actual mutation/native-escape boundaries. Raw .wrapped access, unsupported callbacks and uncontrolled aliases receive private geometry. They cannot mutate retained graph inputs invisibly. Meshing can attach triangulation to native shapes, so it also needs an ownership policy and cannot race arbitrary geometry consumers.

Private native escape uses an execution-local arena that preserves aliases between affected wrappers. Independently copying every access can break the current execution even if it protects future revisions. Recapture or invalidate escaped results consistently; if the alias boundary cannot be established, execute the entire affected region privately. Test both current-execution mutation semantics and isolation of later revisions.

Retain native inputs/results in memory; checkpoint them once when persistence or transfer requires it. Eliminate serialization-based identity checks on every managed operation. Preserve normal native equality semantics where exposed, with a separate persistent-reference API internally; do not make coincident distinct faces equal through a global geometric-equality patch.

Default implementation: graph orchestration in Python and a small explicit OCCT adapter. Move demonstrated hot loops and bulk geometry/mesh transport into compiled code when profiling supports it. Do not assume Python threads parallelize every kernel call or that all OCCT operations are thread-safe. Parallelism must be admitted per operation and ownership boundary.

### 2.4 Transactions and storage, designed afresh

Proposed persistence is a transactional revision catalog, initially SQLite/WAL, plus immutable binary payloads. Batch metadata and use packed or range-readable mesh/topology payloads where measurements justify them. We do not inherit the current directory-per-index layout, no-lock rule, repeated transitive verification, or manual-only cache reclamation policy.

The catalog records document revisions, dependency/evaluation records, exports and leases. The schema and payload layout are selected by the first persistence benchmark, not by preserving old fields. In-memory evaluation uses managed revision identities; disk content hashes establish stored integrity and reuse.

Stage each candidate revision and atomically advance the document head only after its required computations succeed. Existing readers retain the previous revision. Snapshot, query and export jobs pin an exact revision. Late jobs cannot replace newer accepted edits. A valid resident revision may remain usable after its disposable disk checkpoint is evicted; rebuild missing persistence from its owned data or durable source.

Represent geometry-ready, exports-complete, failed and superseded states separately. Publishing the geometry head is not successful-build publication. Visual supersession cannot cancel the declared exports of an explicit call. Serialize publication for shared output paths or return an explicit conflict; older jobs may not overwrite newer accepted saves or claim success after skipping obligations. Detect external STEP/sidecar replacements against the selected prior version and keep the files' binding coherent.

Separate durable authored inputs from disposable state. Source-authoring does not require a new project file. If a later direct editor creates authoritative edits that cannot be represented in source, those edits must be persisted in an explicit project document before acknowledging durability; never hide them only in a cache or worker. Graph transactions can support revision undo internally without adding a history-editing GUI to this scope.

Use active leases, transactional reachability and bounded reclamation for derived data. Crash, interrupted writes, stale leases and concurrent readers are normal lifecycle cases. Checkpoints need source/input fingerprints and engine versioning; corrupt or incompatible checkpoints regenerate. An explicit build that loses its worker either recovers from a proven checkpoint or fails honestly. No unacknowledged background save queue.

### 2.5 One document service, multiple consumers

The same active document supplies exact queries, prototype meshes, occurrence updates and exports. Viewer/snapshot clients receive revision-bound data, not native pointers. Opening a saved artifact creates or reuses a document identified by the actual consumed file bytes. It remains distinct from the source-authored document that exported it.

An active editing preview can stream from a committed resident revision before every checkpoint or exchange file is written. Restart recovery follows durable source and saved artifacts. Snapshots explicitly pin their chosen input; a saved-file CLI continues to mean the file's bytes, even when an editing preview is available.

## 3. Implementation workstreams and exit gates

The assignments below are specific recommendations using models available in this session. Every spawned task sets model and reasoning_effort explicitly. The main integrator should use gpt-6-astra / xhigh, with at most three active subagents alongside it. These are engineering assignments, not promises that model choice proves correctness.

### P0 — Freeze the benchmark and contract

Owner: benchmark agent, gpt-5.6-sol / high. Contract reviewer: main, gpt-6-astra / xhigh.

- Freeze current branch 18cc312ce and main 3e4dfdeef as comparison points, including runtime/dependency fingerprints. Preserve existing reports as historical observations.
- Define the retained-document, source-command, saved-document and browser timing boundaries in section 5. Build equivalent FreeCAD scripts for the same edits, not an unrelated primitive microbenchmark.
- Inventory current @step behavior and frontend usage in the fixture corpus. Record which implementation laws this design replaces and which user-facing guarantees remain.
- Establish mutation, STEP-translation, topology-ambiguity and cache-loss correctness fixtures before altering execution.
- Freeze fixture-specific peak and settled-memory limits for kernel workers, browser processes, decoded arrays, GPU accounting, snapshot workers, queues and replacement overlap. Record a post-disposal plateau and cancellation-cleanup deadline.

Exit: a runnable bounded baseline and an agreed implementation contract in the repository. Numeric targets below become fixture-specific gates, rather than changing after seeing candidate results.

### P1 — Prove a complete small vertical slice

Owner: native/document prototype agent, gpt-6-astra / xhigh. Frontend prototype agent: gpt-5.6-sol / high. Independent mutation-test agent: gpt-5.6-terra / high.

- Build a plate with holes and fillets, then a 24-occurrence assembly, through unchanged @step syntax and no @memo.
- Support a parameter edit, a placement edit, topology inspection, viewer update and a completed STEP save through the proposed document path.
- Prove resident reuse avoids repeated BREP encode/decode for unchanged managed operations. Prove a native escape cannot corrupt the next revision.
- Include generated/modified/deleted topology history and subelement provenance in the operator-result contract now; later inspection cannot recover history discarded with a temporary kernel builder. Freeze the resource-admission protocol before downstream work creates independent pools.
- Compare a small custom document core with OCAF-backed transactions/naming where integration is uncertain. Select one ownership and naming implementation; do not maintain two production document engines.
- Measure end-to-end cost, including graph construction and Python replay. A graph that only moves time into another unmeasured stage does not pass.

Exit: exact correctness tests pass, placement edits perform zero geometry recomputation/remeshing, a local hole edit skips its unaffected upstream geometry, and the common boundary improves materially. If this fails, revise the frontend/ownership design before scaling the framework. No user decision is needed for ordinary internal choices.

### P2 — Implement the document core and scheduler

Owner: document agent, gpt-6-astra / high. Independent design/correctness review: main, gpt-6-astra / xhigh.

- Implement logical identities, typed operator signatures, dependency edges, dirty propagation, revision transactions, cancellation and exact revision pins.
- Separate prototype geometry, topology, placement, appearance and kinematics invalidation. Placement and material changes must not dirty booleans.
- Persist the operator history/provenance contract from P1. Distinguish geometry publication from export completion and enforce saved-output revision ordering.
- Keep unaffected native results resident. Bound retained history by memory and leases; share immutable inputs where proven safe.
- Schedule ready computations with document affinity and resource accounting. Avoid serializing native geometry between workers merely to schedule a tiny operation.

Exit: deterministic recomputation sets, source revision ordering, failure rollback, nested builds, multiple documents and worker-loss recovery pass. No correctness dependency on a warm process.

### P3 — Implement the Python/build123d frontend

Owner: frontend agent, gpt-6-astra / xhigh. Operator adapters: gpt-5.6-sol / high after the interface is frozen.

- Route the common algebra and builder APIs through the operator registry. Trace numeric/topology queries and builder state explicitly.
- Reconcile edited source, helper changes, inserted/reordered loops, changed branches, defaults and external data. Debug provenance is separate from evaluation identity.
- Preserve child-model declarations and output obligations even when geometry is reused or a returned value is discarded.
- Implement private native escape and opaque execution. Instrument time spent outside managed coverage, rather than claiming it is incremental.
- Add supported-region lowering only where it has measured value and a defensible semantics contract. No author-visible purity decorator replaces @memo.

Exit: all chosen plate/gear/curved/imported/assembly fixtures run without @memo. Repeated geometry operations do not reexecute, while meaningful Python side effects are not silently skipped. Cache-free and resident results agree. Every unsupported operation has tested ordinary execution or a clear unsupported-operation error.

### P4 — Implement revision persistence and fast reopening

Owner: persistence agent, gpt-5.6-sol / high. Reviewer: gpt-6-astra / high.

- Build the transactional catalog, payload storage, checkpoint loader, leases, corruption handling, version reset and bounded reclamation.
- Capture source/input revisions and export bindings atomically with their metadata. Verify payload integrity at trust boundaries, not through repeated whole-assembly serialization.
- Persist hot prototype geometry, compact topology maps and frequently requested display assets in bulk. Benchmark individual blobs against packed segments before choosing thresholds.
- Ensure source removal does not break saved-file readers. Ensure deleting all disposable state loses no authored work.

Exit: clean restart, cold load, corrupt/truncated storage, interrupted commit, simultaneous readers/writers, GC with active readers and disk-pressure tests pass. Warm reopen does not fan out into thousands of small metadata requests.

### P5 — Assemblies, imported STEP and exports

Owner: import/export agent, gpt-5.6-sol / high. Native translation reviewer: gpt-6-astra / xhigh.

- Import STEP once into a resident assembly with reusable prototypes and compact occurrence tables. Retain hierarchy, units, labels, colors and intrinsic materials.
- Apply assembly changes by reference, including nested subassemblies, repeated parts, appearance overrides and mirrors. Only changed ancestors require composition work.
- Reuse an XCAF export representation or equivalent preparation data where valid. Stream deterministic STEP output; do not invent an incremental STEP text patcher as a prerequisite.
- Keep readback/translation verification off the preview path. Preserve current successful @step completion guarantees initially: declared outputs and required verification finish before success. Optimize repeated verified exports by their exact inputs/bytes.
- Do not bind saved STEP bytes to the source-native revision merely because our writer produced them. A known repository regression demonstrates that STEP translation can change geometry. Establish correspondence through a tested writer contract or actual import before saved readers reuse native data.
- Revisit completion-time verification policy only as an explicit product-contract change, with separate validation evidence. A faster preview is not evidence of a faster completed save.

Exit: imported and source documents remain distinct; fresh independent readers agree with saved-file readers; hierarchy, topology, placements, appearance and same-runtime deterministic bytes pass. Whole-file export time is reported separately.

### P6 — Stable topology and exact inspection

Owner: topology/inspection agent, gpt-6-astra / high. Reviewer: a separate gpt-6-astra / xhigh task.

- Capture operator-generated, modified and deleted subshape relationships. Evaluate OCAF/TNaming as machinery, not as a universal solution to topological naming.
- Consume the history captured by P1/P2/P3 operators; P6 implements reference resolution and consumer behavior rather than retroactively recreating that history.
- Bind persistent references to feature, occurrence, revision and semantic subelement. Split/merge/deletion/ambiguity must produce explicit outcomes; never guess a nearby face.
- Include compact triangle-to-face and edge mappings in display payloads. Resolve basic selection immediately; query exact geometry only when needed.
- Batch measure, bounds, align, frame, properties and topology-list operations against the resident document. Cache immutable query results by the relevant geometry/placement revision.
- Share query semantics between viewer and CLI. Preserve correct picking across repeated occurrences, mirrors, clipping and LOD changes. Define posed/deformed-query limitations separately from rest-pose exact CAD queries.

Exit: fillet edits, face splits/merges, coincident duplicates, reordered instances and imported STEP cannot silently redirect references. Viewer and CLI measurements agree. Inspection does not tessellate or enumerate unrelated components.

### P7 — Meshing and the display data path

Owner: meshing/data agent, gpt-5.6-sol / high. Quality/native-boundary review: gpt-6-astra / high.

- Benchmark direct OCCT meshing plus packed extraction against the existing JS route at equal verified surface error and identical consumer boundaries. The previous native experiment was mixed; neither backend is predetermined by this plan.
- Choose one default producer, or a deterministic per-shape policy if a hybrid earns its complexity. Mesh identity includes producer, quality and input version. Hardware timing must not decide export bytes.
- Mesh each unique prototype once per required quality. Transport binary positions, normals, indices, boundaries and compact topology mappings without repeated SURF/JSON/GLB conversions just to draw.
- Pipeline cold import/preparation/meshing/transfer/upload. Use byte- and cost-based scheduling; measure first useful geometry and complete requested detail independently.
- Use screen-error refinement for interactive display with a defined quality floor. Snapshot quality derives from its output resolution and explicit requested policy. No silent coarse completion or omitted small parts to meet a timing target.
- Validate analytic seams, poles, trims, thin features, NURBS, normals, face colors and Float32 transport precision. Preserve exact BREP separately from display approximation.

Exit: complete requested-quality loading improves, not just partial visibility. Matched quality and topology gates pass before adopting a producer. Mesh/export reuse works across processes and all consumers.

### P8 — Shared scene engine and viewer updates

Owner: scene/viewer agent, gpt-5.6-sol / high. UI integration after contracts: gpt-5.6-terra / high.

- Replace whole-scene reconciliation on local edits with occurrence/component/property deltas and dirty buffer ranges. Retain prototype GPU geometry, materials and acceleration structures.
- Use instancing and spatial bounds for repeated components; support mirrors, transparency and deformation explicitly. Culling must respect each render pass, including shadow/reflection contributors.
- Keep React responsible for UI intent, not rebuilding thousands of scene objects per edit. Replace fixed component-count batching with measured time/byte budgets.
- Preserve Inspect/Render separation: Inspect owns CAD edges, grids, selection and exact queries; Render owns photographic camera/material/lighting and keeps animation. Share geometry and presentation primitives across viewer/snapshot paths.
- Compile animation and tendon-path data once; update dirty transforms and use GPU/worker deformation where correct. Do not traverse every unrelated occurrence on each LOD publication or frame.
- Preserve native GLB hierarchy, textures, PBR, skins, morphs and clips for both static and animated files. Support actual 3MF capabilities and geometry-only STL explicitly.

Exit: placement edits allocate no new prototype geometry; local component edits update only affected resources; no full-model traversal for each small refinement. Verify both modes, colors, edge policy, topology clicks and animated GLB. Repeated failed replacements and mode switches reclaim their resources.

Freeze a shared format-capability schema before producer/export and scene work diverge:

| Format | Direct viewing and still snapshots | Export target | Appearance/hierarchy | Clip, time and video |
| --- | --- | --- | --- | --- |
| STEP | Inspect and Render; exact CAD queries | Exact geometry plus supported durable annotations | Components, placements, colors and supported intrinsic finishes | Adjacent choreography/kinematics; no claim that STEP embeds glTF-style clips |
| STL | Inspect and Render; mesh measurements | Static tessellation | Geometry only; no invented authored units/colors/materials | No embedded animation |
| 3MF | Inspect and Render; mesh measurements | Static geometry and implemented material channels | Core components/build transforms/units/base materials; explicitly scoped color/texture support | No embedded animation in this scope |
| GLB | Inspect and Render; native glTF scene for static and animated inputs | Static scenes and supported baked animation | Hierarchy, PBR, UVs/tangents, color spaces, textures, alpha modes, skins and morphs | Embedded clips, time selection, video through the same playback path |

For 3MF, the first scope is Core 1.2 plus color-group and 2D-texture visualization from Materials and Properties 1.2.1. Composite/multiproperty/display-property resources require implemented mixing semantics before acceptance; unsupported required resources fail explicitly, with no claim of full extension conformance. Freeze the exact import/export matrix and intended losses in P0. For GLB, test metallic-roughness, normal/occlusion/emissive channels, UV transforms where supported, alpha modes and double-sided surfaces. Validate format outputs with independent glTF/3MF tools and compare viewer/snapshot pixels and animation timelines.

### P9 — Persistent snapshots and video

Owner: snapshot agent, gpt-5.6-sol / high. Isolation/pixel comparison: gpt-5.6-terra / high.

- Reuse a bounded Chromium/render-worker pool across CLI calls, not only within one snapshot packet. Retain reusable modules and immutable decoded assets.
- Start with browser-process reuse and a fresh context/page per job. Add page or decoded-asset reuse only after its stronger lifecycle proof passes. Never share mutable Three scenes, GLB graphs, mixers, textures or render targets between jobs.
- Give each job a pinned document revision, camera, output resolution, rendering policy and animation time. Reset all mutable scene, lighting, selection and animation state between jobs; discard a context when teardown cannot be proven.
- Use immutable job-scoped asset roots/capability URLs, never a mutable server-wide active root. Pool identity includes the packaged runtime, browser and relevant GPU configuration. Cancellation/timeout destroys the affected context and releases its leases.
- Use exactly the shared mesh, scene, material and animation paths. Add GLB clip/time/video snapshot coverage through the native glTF animation path.
- Batch image packets and video frames without reimporting the document. Reuse framing bounds where valid instead of scanning every instance's vertices unnecessarily.
- Measure GPU/readback/encoding and atomic output writing separately from browser startup. Completion waits for all required geometry and the requested quality.

Exit: warm repeated commands avoid process/import overhead; results match fresh-context controls. Alternate files, roots, settings, formats, clips and failures without leakage. Final Render uses a measured quality/convergence policy, not a fixed sleep or an incomplete preview.

### P10 — Cold generation, scheduling and resource control

Owner: runtime/resource agent, gpt-5.6-sol / high. Independent lifecycle reviewer: gpt-6-astra / high.

- Profile Python capture, kernel work, import, export, meshes and browser startup separately. Prewarming may improve an interactive request but must not be presented as an empty-process cold improvement.
- Remove duplicate frontend work, combine suitable kernel operations, batch IPC and persist useful checkpoints. Optimize expensive modeling algorithms where the corpus reveals them; a feature graph cannot skip genuinely new geometry.
- Coordinate document workers, meshing, exact queries, bulk exports and snapshot jobs under one resource policy. Give short interactive work priority without starving required saves.
- Reserve memory and preserve dependency headroom. Use operation-safe parallelism, document affinity and cancellation that actually releases work. Bound queues and retain warm processes only when useful.
- Audit package/browser/native dependency size and startup on macOS, Linux and Windows. Introduce compiled helpers only with a tested wheel/distribution story.

Exit: no parent/child resource deadlock, unbounded queue, monotonic retained-resource growth or runaway worker churn. Record measured RSS and GPU-accounting limitations; do not claim a hard RSS limit from estimates.

### P11 — Cutover, deletion and final parity review

Owner: integration lead, gpt-6-astra / xhigh. Test/packaging agent: gpt-5.6-terra / high. Documentation cleanup: gpt-5.6-luna / medium, reviewed by gpt-5.6-sol / medium.

- Switch the existing public decorators and document doors to the new engine. Delete @memo, old purity machinery, old op-memo interception/equality patches and obsolete materialization/cache paths once their callers have moved.
- Replace the old store schema and reset incompatible derived data. Do not ship a compatibility alias, migration UI, or two user-selectable execution engines. A frozen old checkout is a benchmark oracle, not a shipped fallback.
- Keep reusable renderer/CLI code that passes the new contracts; replacement freedom is not a requirement to rewrite sound code.
- Update package laws, source authoring docs, CLI references, viewer docs and shipping tests to the final design. Rewrite durable contracts concisely; consolidate benchmark reporting instead of adding dozens of overlapping narratives.
- Run the installed wheel outside the checkout across supported platforms. Refresh generated runtimes through the canonical bundle entry point. Keep release VERSION unchanged during implementation; release separately through the repository workflow.
- Complete the matched performance/correctness matrix and manual viewer/CLI review. Every unresolved target remains explicitly open.

Exit: no public @memo, no dependency on old stores, no loss of @step outputs/semantics, source-independent saved documents, passing shipping checks, and measured acceptance of every in-scope performance path.

## 4. Delegation order and ownership

Work in dependency waves, not twelve simultaneous implementations. The four-slot limit means the main integrator plus at most three active agents.

| Wave | Parallel work | Required handoff |
| --- | --- | --- |
| A | P0 baseline/contracts; P1 ownership prototype; frontend coverage audit | Operation/revision/ownership/history and resource-admission contracts; passing vertical slice |
| B | P2 document core; P3 frontend; P4 persistence | Stable engine API, provenance persistence, revision protocol and recovery contract |
| C | P5 STEP assemblies/import/export; P6 topology; P7 meshing | Component/reference/binary mesh/material interfaces; shared resource protocol already defined |
| D | P8 scene/viewer; P10 resource implementation; P5 mesh-format export | Shared scene lifecycle and material/animation behavior, with coordinated resource ownership |
| E | P9 persistent snapshots; integration/performance fixes; format validation | Integrated source-to-query/draw/save/capture pipeline |
| F | P11 cutover; independent correctness review; documentation/packaging | Final performance matrix and deletion of obsolete paths |

Prototype measurement code can run before its production workstream. Benchmark timings always run serially without other native, browser or build workloads. A long-lived test viewer is not allowed to contaminate a claimed idle-host comparison.

Suggested file ownership is separate frontend, document, persistence, inspection and display/export modules inside packages/cadgen; shared scene/rendering work in packages/cadgen-js; UI integration in apps/viewer. Main owns public authoring/CLI integration and cross-package schemas. Final module names follow the P1 contract; do not reorganize the repository first as a substitute for proving the engine.

Every delegated prompt must specify: model and effort, one bounded deliverable, owned paths, prerequisites, preserved public behavior, acceptance tests, benchmark boundaries and a concise handoff. Use fork_turns=none with a complete task brief when setting explicit model/effort in this environment. Do not silently change a model assignment or let multiple agents edit the same ownership boundary concurrently.

For native ownership, graph invalidation, topology naming and saved-document identity, a different agent must review the implementation. Main reviews the integrated behavior and runs real workflows; an agent's passing unit tests are not the integration gate. Smaller models handle bounded fixtures, test adaptation and documentation, not the ownership proof.

The plan was informed by read-only architectural review using gpt-6-astra / high and display/snapshot review using gpt-5.6-sol / high. The recommended implementation effort is higher where ownership or source semantics remain unresolved. Model tiers follow the available tool catalog and [official model guidance](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.6); exact assignments are our engineering judgment.

## 5. Measurement and acceptance

### Comparable boundaries

Record separately: source capture, graph reconciliation, dirty computation, native readiness, topology readiness, mesh derivation, transfer/decode, scene adoption, GPU completion, complete requested detail, exchange export, saved-file verification and actual process exit. A renderer call returning is not proof of a presented frame; label GPU fences, frame-capture evidence and compositor observations accurately.

Complete usable preview means every required occurrence is present at the requested display quality; first partial geometry and on-demand exact topology readiness are separate milestones. Every edit records preview presentation, complete requested detail, STEP saved and process exit.

Run these distinct loading cases: source-cold build through first frame and complete standard detail; saved-STEP cold import through complete standard detail; geometry-warm but tessellation-cold; tessellation-warm but browser-cold; and resident-service reopen. Record generation plus display together as an additional total, never as a replacement for these boundaries.

Compare headless FreeCAD for import, retained recompute, placement, exact queries, meshing and export on equivalent models and edits. Align kernel versions where possible; if not, report both versions and qualify attribution. Compare source-command workflows separately from direct document-parameter changes. FreeCADCmd operation timings do not provide a browser or photographic snapshot baseline. A FreeCAD GUI/offscreen image comparison, if used, gets a separate clearly labeled harness.

Match geometry, units, requested quality and visible component coverage. Equal numeric tessellation parameters or equal triangle counts alone do not prove equivalent image quality. Validate face/edge coverage, exact-surface error, materials and silhouettes. Preserve same-runtime deterministic outputs while evaluating cross-kernel results with geometric criteria.

### Corpus and run budget

- Tiny: primitive, plate/hole/fillet, curved seam/pole/trimmed-surface regressions.
- Moderate: 9-part planetary, 24 repeated plates, 73-part chronograph and 118-occurrence iris.
- Large but cheap to generate: nested repeated assemblies with 300, 1,000 and 3,000+ occurrences and controlled counts of unique prototypes.
- Complex checkpoints: Moonwatch and bounded tendon-hand subassemblies; use existing full-hand artifacts for display after earlier gates pass.
- Formats: STEP source/import, STL, colored/textured 3MF, static PBR GLB, animated/skinned/morph GLB; maintain DXF and robot-description smoke coverage for shared-runtime consumers.

Record occurrence count, unique prototypes, faces, triangles, file/payload bytes and changed dependency fraction. Do not rank workload size by STEP megabytes alone. Keep routine generation jobs below 60 seconds and bounded integration jobs below 120 seconds; an over-budget fixture is recorded and investigated, not repeatedly retried for minutes. No routine full-hand cold rebuild. Giant optional cases remain separate from the bounded acceptance corpus.

Exploratory small/moderate timing uses at least five cold and ten warm samples, with interleaved or randomized baseline/candidate order, medians and observed ranges/maxima. A p95 gate requires a larger cheap-case series, approximately 40–60 samples, with uncertainty reported; ten observations do not establish a stable tail. For expensive checkpoints, start with one capped diagnostic, then choose a bounded repeat budget and gate medians/observed maxima without claiming p95. Cold means empty relevant derived storage and new owned workers/browser; filesystem cache state is separately described.

### Initial target bands

These are proposed acceptance targets to freeze against the P0 corpus, not predicted outcomes. Medium means up to roughly 300 occurrences in the chosen corpus; large means the controlled 1,000–3,000+ occurrence assemblies. Complexity limits and exact hardware/quality are recorded with each fixture.

P0 names the exact reference behind each baseline comparison and identifies the overhead-dominated fixtures before candidate timing. Where repeat budgets cannot support a p95 estimate, use an explicitly labeled median/observed-maximum gate for that fixture instead of reporting an unsupported percentile.

| Path | Proposed gate |
| --- | --- |
| Matched retained native recompute, import and exact query stages | Target median within 1.25x and p95 within 1.5x of the matched headless reference, with fixed overhead reported separately for sub-millisecond operations |
| Unchanged source command | p95 <=200 ms medium; <=500 ms controlled large |
| Warm placement edit to complete usable preview | p95 <=250 ms medium; <=1 s controlled large; zero prototype recomputation/remeshing |
| Local geometry edit to complete usable preview | Changed kernel and mesh critical-path time plus <=500 ms medium / <=1.5 s controlled large; unrelated prototypes remain untouched |
| Warm topology selection and scalar queries | Visual identification within a frame when the display map is resident; exact query p95 <=100 ms medium / <=250 ms large, excluding genuinely expensive requested algorithms |
| Warm complete viewer opening at standard detail | p95 <=1 s medium / <=3 s controlled large, with all required occurrences present |
| Cold generation plus complete first display | No regression against the stronger valid baseline at matched quality; target >=2x improvement on overhead-dominated complex fixtures, reported individually |
| Warm CAD snapshot, 1200x900, complete requested quality | p95 <=750 ms medium / <=3 s controlled large through the warm service; process-cold runs separate |
| Photographic snapshot and animation/video | Same geometry/material/time as the shared viewer path; latency reported by quality and resolution; no universal subsecond Final claim |
| STEP export | Target <=1.5x comparable headless export-stage time; verification cost remains separately visible and part of command completion where required |
| Interactive display | Target <=16.7 ms p95 medium and <=33 ms controlled large Inspect frame intervals; complex deformation/photographic workloads profiled separately |
| Resource lifecycle | Meet P0 peak/settled-memory budgets, post-disposal plateau and cleanup deadline across all processes; bounded retained history/queues and recovery |

For stages with effectively zero reference cost, report absolute overhead instead of unstable ratios. Runtime/kernel limits or expensive geometric operations remain visible; targets are not met by redefining quality or excluding a required save.

### Correctness and recovery matrix

Require equivalent cold, warm, restarted and checkpoint-free results; source/input changes during execution; helper/branch/loop edits; native and wrapper mutation; duplicate geometry; topology splits/merges; mirrors; materials; child-output failures; export translation changes; cancelled/superseded revisions; worker death; concurrent saves; external file replacement; storage corruption/GC; WebGL context loss; and repeated model/mode switches.

Use direct kernel recomputation and independent file import as oracles, not only the old cache backend. Compare shapes, topology validity, placements, appearance, references and deterministic bytes where appropriate. Require visual review of complete scenes in both modes and snapshot/animation parity. Do not lower required coverage to make a rewrite appear correct.

## 6. Scope, sizing and decisions

The earlier 8–16 engineer-week estimate concerned a constrained feature graph. This broader program also replaces persistence/ownership, import/export preparation, inspection, the display data path and snapshot orchestration. A preliminary planning allowance is 24–40 engineer-weeks, with significant uncertainty until P1 passes. With three experienced parallel workstreams and integration, think roughly 12–20 calendar weeks, not a promise or an agent-runtime estimate. Native ownership, frontend coverage and topology naming are the schedule risks.

The first commitment is a bounded P0/P1 proof, approximately one to two engineering weeks. It must show that the chosen design improves a real source-to-visible workflow without @memo and preserves native semantics. After that, revise sizing from measured implementation work. Subagents shorten independent work; they do not remove serial design, integration or benchmark constraints.

Default decisions are explicit: retain build123d-compatible authoring through a managed frontend; keep OCCT; use a retained document with replaceable persistence; remove @memo; preserve @step completion semantics; share the renderer; benchmark mesher alternatives; use FreeCAD as a reference rather than adding it as a production dependency. OCAF components are available to evaluate without adopting the FreeCAD application. If a native integration alternative materially changes dependency/distribution scope, document its measured benefit and cost before choosing it.

The program is complete only when the supported authoring corpus, saved-file consumers, exact inspection, both viewer modes, snapshots/animation, export completion and lifecycle gates pass together. A fast retained parameter edit, a first partial mesh or a checked-off graph implementation is not complete FreeCAD parity.

## 7. Evidence and technical references

- [Final branch review](scripts/bench/cadgen-performance/FULL-REVIEW-20260912.md): measured command, snapshot and complete-display boundaries and remaining regressions.
- [Moonwatch](scripts/bench/cadgen-performance/MOONWATCH-20260911.md): expensive changed-part preview, export and readback stages.
- [Tendon hand](scripts/bench/cadgen-performance/TENDON-HAND-20260912.md): native identity churn, large-scene update and snapshot bottlenecks.
- [Reference composition](scripts/bench/cadgen-performance/REFERENCE-ASSEMBLIES-20260911.md): demonstrated reuse and rejected native-copy assumptions.
- [Native mesher comparison](scripts/bench/cadgen-performance/RWGLTF-MODERATE-QUALITY-20260910.md): mixed producer/quality costs, not evidence that switching meshers automatically wins.
- [Saved STEP regression](tests/python/packages/cadgen/test_tree_reflects_written_step.py): source geometry cannot stand in for independently translated file bytes without proof.
- [FreeCAD Document API](https://freecad.github.io/SourceDoc/d8/d3e/classApp_1_1Document.html): retained document operations, touched-feature recomputation and transactions.
- [OCCT OCAF](https://occt3d.com/dev/doc/overview/html/occt_user_guides__ocaf.html): document, function-dependency and topological-naming machinery to assess in P1/P6.
- [OCCT shape history](https://occt3d.com/dev/doc/refman/html/class_b_rep_builder_a_p_i___make_shape.html) and [boolean ownership controls](https://occt3d.com/dev/doc/refman/html/class_b_rep_algo_a_p_i___builder_algo.html): native adapter building blocks whose behavior needs operation-specific validation.
- [OCCT meshing](https://occt3d.com/dev/doc/overview/html/occt_user_guides__mesh.html): meshing pipeline and parallelism opportunities, not a guarantee of faster end-to-end display.
- [glTF 2.0](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html) and [3MF Materials and Properties](https://github.com/3MFConsortium/spec_materials/blob/master/3MF%20Materials%20Extension.md): format capability and fidelity references for shared viewer/snapshot/export behavior.
