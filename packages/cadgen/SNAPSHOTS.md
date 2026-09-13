# Snapshot diagnostics

`cadgen step snapshot part.step review.png --debug --json` adds diagnostics to
`SnapshotResult.debug`. The same flag is available on the other snapshot doors
and as `debug=True` in Python. Every diagnostic entry identifies its input;
existing artifact-resolution information remains alongside `stageTimings`.
Normal results keep their file, warning and aggregate timing fields.

Still view renders report these measured browser durations in milliseconds:

| Field | Measured work |
| --- | --- |
| `loadSourceMs` | Source fetch, cached-mesh decoding or tessellation, and source composition |
| `preparePoseMs` | Requested animation loading/frame resolution and kinematics runtime preparation |
| `buildModelMs` | Render context and model/display-record construction |
| `prepareViewportMs` | Viewport, renderer and scene setup; this is not a draw |
| `waitViewportMs` | Waiting for the prepared viewport's asynchronous readiness |
| `captureMs` | Entire capture call, including readiness and all output stages below |

Exact-surface packages also report `stageTimings.sourceLoad`. Counts distinguish
`componentCount`, `cacheBatchCount`, `cacheHitCount` and `cacheMissCount`.
Measured durations are `probeMs` (metadata), `cacheReadMs` (bounded body fetch
and integrity validation), `cacheDecodeMs` (component views and metadata),
`meshBuildMs` (owned render arrays), and `composeMs` (occurrence composition).
Misses additionally measure `surfaceReadMs` (fetch and parse), `tessellateMs`
and `cacheWriteMs`. Miss-stage times sum per-component intervals across the
small concurrent pool, so they can overlap; absent stages are omitted.

`stageTimings.outputs` contains one measured entry per image, in output order,
with its `path` and these durations:

| Field | Measured work |
| --- | --- |
| `updateModelMs` | Output sizing, model pose/effects, exploded placement, topology edges and line resolution |
| `frameCameraMs` | Camera selection/fitting, including visible-vertex tight framing when enabled |
| `prepareStudioMs` | Camera depth and photographic studio setup; absent without a studio |
| `drawSubmitMs` | The renderer's synchronous draw call |
| `encodeImageMs` | Image readback, optional view label and PNG/data-URL encoding |

WebGL submission may return before GPU work finishes. `encodeImageMs` can
include waiting for that work; these fields are browser wall times, not GPU
profiler measurements. `captureMs` contains `waitViewportMs` and the output
stages, so do not add those overlapping durations together.

Only stages actually reported by the runtime are included. List, section and
video results do not invent still-image measurements. Invalid/nonfinite
values and image payloads are excluded from diagnostic output. Measurements
belong to one render call and cannot carry over from a previous job.

The ordinary `timings.total_ms` covers the render packet and writing its outputs.
It includes browser startup and shutdown when the call owns that browser. Input resolution happens before
that interval. The browser stages cover narrower work and need not add up to
that total or to the complete CLI process time. Use this attribution to choose
a targeted profile; a small model's stage proportions do not establish where
a larger assembly spends its time.

The runtime can retain one Chromium process through an explicitly owned
`BatchSnapshotRenderer` on one event loop. Every still or video job creates a
fresh browser context and page, then releases both before returning. Jobs on
that owner run serially; page state, GPU resources and unfinished JavaScript
cannot become the next job's state. A failed job discards its browser too.
The owner closes an idle browser after 30 seconds and bounds each browser or
driver close attempt to five seconds. The service owning it must close the
owner before closing its event loop.
Failed driver shutdown retains its handles and refuses further work until an
explicit close acknowledges cleanup. Idle expiry records that failure for the
next caller. These receipts prove public API acknowledgement, not independent
OS process-death observation; worker reclamation remains the service's boundary.

Each job gets an independent loopback asset server with a random URL capability
and captured absolute model and store roots. Requests cannot acquire another
job's roots through an environment change or a late fetch. Completion revokes
the capability and closes its listener and registered connections. A request
worker already reading bytes may finish in the background against its captured
roots; it cannot register a new connection after revocation. Bulk assets and cache
bodies still travel over loopback HTTP, with the same cache admission rules.

Snapshot CLI entries resolve source-independent artifacts on the calling thread,
then submit a closed render operation to a worker in the existing daemon pool.
That worker explicitly owns one `SnapshotService`, whose event-loop thread
retains Chromium across commands. Only resolved JSON values and captured model,
store and encoder paths cross into that thread; it executes no Python source or
CAD kernel work. The worker accepts the browser bundle from its own installation.
Existing explicit development-bundle overrides remain caller-owned.

Render admission is serial, with at most four waiting/active operations and a
64 MiB aggregate conservative JSON charge. The packet has one absolute deadline
covering admission, transfer, startup, rendering and cleanup: the sum of its job
timeouts plus a 30-second cleanup reserve, capped at 24 hours. Progress callbacks
and output streams remain on the calling thread. A completed operation returns
one typed receipt after its contexts and pages are released. A cancelled queued
operation releases its reservation without claiming a worker; active cancellation
cooperatively stops and reaps that worker. Missing browser shutdown acknowledgement
poisons render admission until the owning daemon is restarted, so an uncertain
teardown cannot be followed by more browser launches.

The supervisor owns one control reader from admission onward. Upload and response
writers each allow one outstanding frame, bounded to the same conservative
64 MiB charge; they cannot queue unbounded progress. Work deadlines interrupt
blocked transfers while preserving the cleanup reserve. Completion delivery then
has its own remaining slice of that original deadline. An interrupted partial
frame makes its channel unusable: failed receipt delivery is recorded, never
reported as acknowledged cleanup. Each I/O thread must join before releasing
its charged request and channel. Failed joins retain the handles and poison
admission until the owning daemon exits. A stalled final response does not itself
invalidate a browser whose completed job was already acknowledged.

Each CLI request owns a small transport process around the daemon's authenticated
channel. This bounds even a stalled authentication handshake without duplicating
the channel protocol. Its termination and reap are reported separately from the
supervisor's worker/browser cleanup receipt; losing the connection does not prove
that render cleanup finished. The transport process owns no browser. Worker EOF,
shutdown and cooperative termination close the service and join its event-loop
thread; the pool retains its final process-reclamation boundary.

An injected renderer remains owned by its caller across `render_snapshot` or
`run_snapshot_async` calls. Ordinary library calls without an injected or explicitly
bound service create and close one renderer for their packet. Their synchronous
wrapper still uses `asyncio.run` and creates no hidden process-global pool.
`CADGEN_DAEMON=0` also gives the CLI this standalone ownership. Browser reuse
across CLI processes exists only while their explicit daemon worker is retained;
idle expiry, worker recycling and memory admission may retire it. No authoring
helper or additional CLI flag is required.
Each job copies only closed JSON values before its first await, so later caller
mutation cannot change a queued job's payload or asset authority.

The native document preparation door accepts a value-only `DisplayProduct` or
captures a saved STEP and its sole companion once, including companion absence.
Saved imports submit those exact buffers to an explicitly owned document
dispatcher; they never resolve source or reuse a resident source revision by
filename. A saved file overwritten after preparation cannot change the packet.
The internal prepared-input door is implemented; the public STEP CLI cutover and
native motion/selection support remain separate work.

The resident preparation door requires the exact engine-attested `DisplayProduct`;
constructing a lookalike dataclass is not a native revision receipt. The saved
STEP door independently captures its dispatcher response bytes.
Native still jobs carry a closed manifest binding, complete mesh inventory and
mesh policy. The manifest is at most 16 MiB, each packed CGMESH asset at most
128 MiB, and unique mesh assets total at most 256 MiB. Only those hash-named files
are served by the job's random capability. Reads require regular files and
bounded lengths, and verify SHA-256; a substituted pipe or symlink cannot become
a blocking asset stream. The browser independently verifies the manifest and
mesh membership before scene adoption. These jobs have no package, SURF, old
artifact-cache or source-module fallback.

One native still job adopts its scene once for all requested cameras. Inspect
retains CAD edges and revision-scoped picking intervals. Photographic Render
does not construct those resources; it keeps the same face RGBA and PBR inputs
and uses the shared camera, studio and image capture pipeline. Its final mesh
rung is relative chord 0.00015 and angle 0.35 radians; preview and ordinary
Inspect use 0.0015 and 0.35. Explicit Inspect tessellation overrides must match
the producer's packet policy. Native selection, poses, kinematics, animation,
video and non-view modes fail at admission until their consumers are integrated.

Preparation, import, meshing, transfer and rendering consume one monotonic
deadline established before capture, plus its original 30-second cleanup
reserve. Native staging has four atomic persistent slots under the captured
cache root's `runtime/native-snapshot-staging`, each admitting at most 400 MiB:
272 MiB of input assets and 128 MiB reserved for PNG outputs. This bounds admitted
payload bytes across independent callers to 1,600 MiB in
that catalog, excluding filesystem allocation overhead. A slot has a random
ownership token and is released only after a
context-owner cleanup or supervisor worker-reclamation receipt. Reaping the
small transport process alone is insufficient. An interrupted or uncertain
slot remains occupied after caller exit; PID death and age do not authorize
deletion. Exhausted admission fails until those consumers can be proven
reclaimed. This slice provides no speculative stale-slot recovery.

The worker writes numbered private PNGs in that same slot. Final target paths
stay on the caller. Admission allows at most 256 distinct still targets, each
dimension within 1..8192 pixels, within the aggregate 128 MiB conservative PNG
bound. All output membership, PNG framing/checksums, bounded complete image
decompression and requested dimensions must validate after cleanup acknowledgement
before any requested target is published through the shared atomic writer.
All final targets are read back against the verified bytes before success.
Results and output timing paths are then remapped to those final targets.
Uncertain cleanup retains private inputs and outputs; a late worker cannot write
the requested public image. Failed publication rolls back acknowledged writes
only while their length and SHA-256 still match; an observed replacement is
preserved. These checks do not lock final paths against concurrent writers.

Video frames use one page for the sequence. Encoding uses the same ffmpeg
options and atomic output publication, with bounded stderr retention. A timeout
or cancellation terminates, kills if necessary, and reaps the encoder before
removing its staged output and releasing the job context.
