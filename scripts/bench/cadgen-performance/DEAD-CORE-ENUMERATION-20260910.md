# Dead core-type Builder enumeration

The guarded prototype did not produce a meaningful improvement. A small
upstream change saved about 9.6 ms in this warmed body, which does not close
the preview target. No production code, dependency, decorator or cache changed.

| Counterfactual | Calls per condition | Stock median | Candidate median | Difference |
| --- | ---: | ---: | ---: | ---: |
| Guarded stock-builder specialization | 8 | 328.60 ms | 327.59 ms | −1.02 ms / −0.31% |
| Unguarded upstream-style two-statement change | 4 | 327.18 ms | 317.60 ms | −9.58 ms / −2.93% |

Each comparison used ABBA/BAAB ordering in one interpreter after two warmup
calls. The timer covered the unchanged planetary model body, with ordinary
cadgen determinism and operation memoization installed. BREP serialization,
attribute inspection, source checks, imports and warmup were outside the timer.
The guarded run took the specialized path for all 27 Builder calls per body.
Its 61 Python identity guards plausibly consume much of the small opportunity;
the difference between the two studies is not a separately measured guard cost.

Coordinated agent compute was held; uncoordinated external host activity and the
user's viewer cannot be excluded. These short counterfactuals establish neither
a latency distribution nor whole-build/preview performance. Earlier profiled
body timings are not a matched baseline for these unprofiled calls. Even the
317.60 ms body exceeds the 250 ms preview target before publication; the current
planning budget for the body is roughly 140 ms.

## Change and boundary

The installed `Builder._add_to_context` fills `pre[cls]` and `post` by enumerating
and hashing vertices, edges, faces and solids. For `cls == self._shape`, neither
set is consumed: core `Select.LAST` directly uses `ShapeList(typed[cls])`.
The scratch specialization changes only the two empty-set conditions from
`self._obj is None` to `self._obj is None or cls == self._shape`.
All non-core enumeration and set differences remain. The final no-argument
`self._shapes()` used to cast the result also remains.

The guarded variant accepts exact stock `BuildPart`, `BuildSketch` and
`BuildLine`, stock current/input shape types, and the creating thread. It checks
builder descriptors, enumeration/cast/hash/constructor helpers, relevant module
globals and instance overrides against captured Python identities. Custom
subclasses and the tested monkeypatches fall through to the original method.
It retains no native shape, geometry identity or deferred `LAST` value.

This is an experiment, not an acceptable production installer. It compiles two
exact textual substitutions in the installed method and temporarily dispatches
to that copy. Maintaining a copied or AST-specialized third-party builder
method would enlarge cadgen's topology-only patch boundary for negligible net
benefit. An upstream two-condition cleanup is reasonable; a cadgen runtime
source-rewriter, call-stack interception or arbitrary author-function cache is
not recommended. The guard is not a proof against arbitrary concurrent Python
rewrites, invalid native state, allocation failures or all transitive callback
changes. Such cases prevent claiming universal exception equivalence.

## Verification and retained evidence

Four alternating functional runs each captured 14 stock Builder states:
`ALL`/`LAST` sequences, pending inputs, prior/current BREP bytes and metadata.
Core `LAST` retained the original typed wrapper and its appearance/material.
Empty subtract/intersect errors matched. Subclass, instance `_shapes`, class
`_shapes` and shape-hash sentinels raised the same errors before replacement
mutated the builder. Separate results had disjoint native topology graphs;
mutating one result's vertex, curve, surface and label left the other unchanged.
An ordinary forced `@step` build produced identical saved bytes in both variants.

All 24 measured results had BREP SHA256
`135b80b75bc208412210485eb4a73dad30963eddd8241660e4814f15288b3d08`
and identical recursive appearance metadata. The public proof STEP SHA256 was
`addccc9fb6a16ed8028d038d3aba25cf414902791de74382325a6d7f98c150be`.
The model source bytes/mtime and every recorded Python runtime file hash were
unchanged; temporary method installation was restored and all owned processes
exited. The successful functional run followed one helper correction for
unsupported stock BuildLine selectors and an expected sandbox IPC retry.

- [Functional proof, exact helpers and guards](results/dead-core-enumeration-functional-20260910.json)
- [Sixteen-call guarded study](results/dead-core-enumeration-timing-20260910.json)
- [Eight-call upstream counterfactual](results/dead-core-enumeration-upstream-20260910.json)

The JSON reports embed the exact helper/specialized source, two substitutions,
installed source hashes, per-run output hashes, runtime file hashes and UTC
times. Functional: 2026-09-11 00:01:41–42 UTC; guarded body: 00:01:57–00:02:03;
upstream body: 00:03:15–18. Helpers/logs remain in
`/private/tmp/cadgen-performance-20260910`; CAD proof artifacts are under
`models/tmp/dead-core-enumeration-20260910` and are not tracked.

The embedded dependency method is from build123d `build_common.py`, copyright
2022 Gumyr, licensed under [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0).
Its installed file SHA256 is
`649b4927fb790735298f8710b431be28ca5e622313589d82dccccde6588c1d74`.
