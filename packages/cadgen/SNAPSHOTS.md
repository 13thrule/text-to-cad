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

Video frames use one page for the sequence. Encoding uses the same ffmpeg
options and atomic output publication, with bounded stderr retention. A timeout
or cancellation terminates, kills if necessary, and reaps the encoder before
removing its staged output and releasing the job context.
