# Moonwatch generation, editing and rendering

The 117 MB saved Moonwatch exposed work that the smaller assembly tests did not:
repeated whole-tree validation, native workers discarded between requests, and
a concurrent channel-close race. The new browser run completed all 256 meshes
in **34.16 seconds**, with no viewer error. The user's original load was still
incomplete after 3–4 minutes; that failed run is not a completed timing baseline.

This is a September 11 follow-up to the [branch summary](SUMMARY-20260911.md).
It uses the existing Moonwatch and ignored benchmark copies of its source.
The tendon-hand project remains on its separate branch. No generated CAD files
or large render assets are added by this work.

The bounded [checkpoint evidence](results/moonwatch-checkpoints-20260911.json)
records the raw timings and fixture identities behind this report.

## Fixtures and measurement boundaries

- **Saved document:** `models/moonwatch/STEP/moonwatch.step`, 116,985,855 bytes;
  SHA-256 `92fdfb8aaff125ebd60fecae095045a16aa8949fdec8f794b6e40ed56bec0059`.
  Its imported tree has 256 distinct components and 301 occurrences.
- **Authored models:** ignored copies of `models/moonwatch/src` and `lib`, using
  real decorated model calls through a persistent daemon. The rebuilt authored
  root has 192 component occurrences. Its representation differs from the saved
  document above; component counts and geometry-diff proofs are not interchangeable.
- **Machine/runtime:** Apple M1 Max, 64 GiB RAM, macOS 26.5.1, Python 3.13.13,
  build123d 0.11.1, OCP 7.9.3.1.1 and Playwright 1.62.0. These are local wall
  times, not cross-machine guarantees. Each reported full-assembly case is a
  bounded individual run.
- Cold display runs start with the exact geometry objects and document index,
  but no surface or tessellation cache. Their times exclude the separately
  measured **21.88-second STEP import**. Completion means the last of 256 mesh
  cache writes; browser screenshots separately confirmed a complete scene.
- Warm browser times below are upper bounds from UI observations, not instrumented
  first-frame timestamps. Snapshot timings include the command's browser startup
  and teardown. Build timings include the client process unless stated otherwise.

## Interactive rendering

| Checkpoint | All meshes cached | Native worker imports | Result |
|---|---:|---:|---|
| Original attempted load | Still incomplete at 3–4 min | 89 by job 88 in the captured run | Channel failure; no complete baseline |
| Metadata reuse and borrowed-worker capacity correction | About 75 s | 56 | Complete scene |
| Also read only requested component BREP payloads | 61.65 s | 66 | Complete scene |
| Also retain surplus workers briefly between request waves | **34.16 s** | **15** | Complete scene; two settled idle workers |

The last two checkpoints are a **1.80×** improvement in complete cold display
preparation. Their native worker import counts explain part of the remaining
variation: keeping a warm worker across an asynchronous polling gap is cheaper
than starting another OpenCascade process. The pool still obeys memory admission,
reclaims idle workers under pressure, and returns to its configured spare count.
An explicit zero-spare configuration still retires borrowed workers immediately.

The final run recorded one client-disconnect cancellation. Two log messages
refer to the same active request and worker; the worker was removed before it
could be reused. The pool's generic `crashes` counter includes that forced
retirement. The log shows no native/kernel crash, and the viewer completed.

At the preceding checkpoint, repeated browser loading showed initial geometry
within about 0.6 seconds and the complete watch within 3–4 seconds. The final
production viewer showed the complete watch by **2.904 seconds** after reload.
Selecting the case resolved assembly reference `o1.1` and displayed its 29 parts.
With the crystal expanded, a canvas click resolved spherical face `o1.1.5.f1`
and its 969.89 mm² area. Tree selection also resolved circular edge `o1.1.5.e3`
and its 110.27 mm length. These are functional checks, not a measured picking
latency study. The viewer remains available at
`http://127.0.0.1:3257/?file=STEP%2Fmoonwatch.step`.

## What changed in the store and daemon

| Operation on this saved document | Before | After | Ratio |
|---|---:|---:|---:|
| Verified metadata capture, median | 282 ms | 19.6 ms | 14.4× |
| Surface request for 64 components, median | 368 ms | 32.9 ms | 11.2× |
| Pinned surface GET admission, median | 291 ms | 20.4 ms | 14.3× |
| Forced surface extraction for a selected 18.7 KB BREP, warm median | 317 ms | 61.1 ms | 5.2× |

Metadata capture keeps a bounded process-local cache of compact JSON. A hit
requires unchanged file identities for every object in the verified closure;
deletion, in-place corruption and atomic replacement trigger full verification.
Each caller receives a private parsed descriptor. Native consumers still own
the complete verified byte closure. Surface extraction admits the whole graph,
then reads and verifies only the selected component payload before decoding it.

The persisted contract is unchanged: immutable content-addressed objects and
atomic input indexes. There is no second disk-cache layout, retained mutable
native document, or new utility for model authors to import. Concurrent channel
close now has a single owner so cancellation cannot close a reused file descriptor.

## Actual source generation and editing

| Model/task | Time | Qualification |
|---|---:|---|
| Finishing sampler, cold generation | 18.27 s | Eight shapes; includes daemon startup |
| Finishing sampler, unchanged run | 0.13 s | Actual process completion |
| Finishing sampler, 50 → 52 wheel teeth | 5.51 s | Geometry change |
| Chronograph works, cold generation | 57.18 s | 69 unique shapes / 73 occurrences |
| Chronograph works, 21 → 22 star teeth | 7.69 s | Exactly one of 73 occurrences changed |
| Chronograph works, unchanged run after edit | 0.17 s | Actual process completion |
| Chronograph works, reverse edit | 6.66 s | 22 → 21 teeth |
| Whole authored watch, build with child models already current | 63.47 s | Not a fully cold source build |
| Whole authored watch, unchanged run | 0.56 s | 0.60 s after the edit |
| Whole authored watch, one changed column wheel: preview published | 18.93 s | Backend publication; excludes browser display |
| Whole authored watch, same edit: command complete | 46.07 s | STEP saved at 44.79 s |

The one-part edit changed only the chronograph, movement and root tree hashes.
Case, dial/hands, bracelet, movement base and keyless-work child trees remained
identical. Exactly one of the authored root's 192 component occurrences changed.
The unchanged-run check retained the edited tree and saved STEP digest.

A fully cold root was deliberately not run: a required movement-base child
alone hit the roughly 100-second cap, and cold bracelet and chronograph children
each took about 58 seconds. Retrying the capped child with its partially warmed
operation cache completed in 28.29 seconds. Its large multi-cutter boolean is
still expensive; successful low-level operations survive an unpublished run.

Validation passed for all eight sampler shapes, including self-intersection;
all 73 chronograph occurrences were valid, closed and had positive volume. The
changed column wheel also passed the targeted self-intersection check. The
whole chronograph self-intersection pass was skipped because the changed shape
received that full check. These checks do not constitute validation of every
solid in the full authored watch.

A follow-up matched parent build isolated duplicate kinematics resolution.
Reusing its successful result within the same build reduced complete command
time from **36.54 to 32.15 seconds (12%)**, with the STEP-saved milestone moving
from 35.73 to 30.90 seconds. Both runs used hot children and a new parent worker;
the output basenames differed to require a parent build. This is separate from
the earlier 46.07-second one-part edit, not a matched after-time for that edit.

The paired STEP files differ only in their header/root product names; every
line after line 19 is identical. Appearance and all kinematics match exactly
(50 mates, two couplings and eight poses). The saved sidecar's document hash
correctly differs with the document basename. Independent copies prevent a
preview consumer from mutating the result later used for the saved sidecar.

The patched profile still spends 6.06 seconds assembling STEP, 12.86 seconds
rereading it and 1.82 seconds creating its canonical document. Those stages are
not incremental yet. A source-only change that preserved more child links was
also tried in the ignored fixture; it was slower and was not adopted.

## Headless snapshots

The full saved watch's first 1024 × 768 snapshot took **25.68 seconds**; a repeat
took **23.61 seconds**, despite persistent tessellation entries being present.
Stage profiling placed about **21.1 seconds in source loading**, versus 54 ms
building the scene, 16 ms rendering and 164 ms capturing the image. Both PNGs
were produced successfully, and the full-watch image was visually inspected.

The browser trace found that every cached mesh was downloaded but rejected,
causing another 256 surface downloads, tessellations and cache writes. The
intercepted headless page used an origin where Chromium did not expose
`crypto.subtle`, which the shared cache provider requires for hash verification.
Using the fully intercepted `localhost` origin restores that API without
weakening cache validation or changing the shared mesh format.

| Matched direct renderer measurement | Before | After | Ratio |
|---|---:|---:|---:|
| Entire warm renderer call, including browser lifecycle | 22.64 s | 2.16 s | 10.5× |
| Load cached source geometry | 21.11 s | 0.493 s | 42.8× |
| Build scene | 54 ms | 51 ms | Essentially unchanged |
| Render / capture | 16 / 164 ms | 16 / 161 ms | Essentially unchanged |

A repeat finished in 2.17 seconds with no mesh index writes. The direct-render
pair uses the same raw job options. A separate render normalized with the CLI's
theme/options produced a PNG **byte-identical** to the prior CLI image:
250,259 bytes, SHA-256
`d248714a9627d4c56b6130dabe0f83d1e60691b5a172e3708fb03590b0bb5afa`.
The new real-browser regression renders once, deletes its only source surface,
then proves a second render succeeds from the persisted mesh alone.

## Verification

Focused metadata/geometry checks pass (32 tests), as do the complete viewer
backend (348), pool/memory/channel/artifact checks (82), and package/sidecar
boundary checks (seven). Integrated kinematics, reemit and snapshot checks pass
(153). Two direct test launches with incomplete runtime paths failed; the
canonical test loader with absolute paths and an isolated daemon passed. Bundle
freshness and the unchanged release version/pins pass. A separate in-process
namespace cleanup defect found during testing is fixed: an owned nested
namespace can now be classified and evicted after its foreign parent was
removed. Its namespace/source-closure checks pass (22). There are **644 passing
tests across these sets**. No JavaScript source changed, so the committed
bundled runtimes remain current.

## Limits of the FreeCAD comparison

These changes adopt the relevant performance mechanisms—reusing derived geometry,
keeping kernel workers warm and separating display preparation from STEP saving.
No matched FreeCADCmd Moonwatch benchmark was run in this follow-up, so there is
no defensible numeric FreeCAD parity ratio. The current full-watch edit still
spends substantial time exporting and rereading STEP; warm geometry reuse does
not make that file serialization incremental. A complete source edit and a
resident-document preview are distinct performance targets.
