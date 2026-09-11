# Sibling preparation — September 10, 2026

Production now prepares bounded, already-pinned siblings while an earlier child
is still producing its source result. The measured geometry median improves,
but the 250 ms preview target remains unmet and both conditions contain a large
first unseen-edit stall. This is a same-runtime enabled/disabled comparison;
it does not replace the older cross-version split comparison.

## Production boundary

`cadgen.store._ready_children` installs one idempotent `Compound` constructor
hook. It activates only inside a model build frame, with constructor state local
to its thread. Exact list/tuple inputs qualify through `obj=`, or through
`children=` when `obj`/`parent` are absent or `None` and every input is a distinct,
unparented exact `LazyCompound`. AnyTree's original validation, attachment and
rollback still run. Nested constructors, reparenting, subclasses and iterators
receive no new preparation path.

Preparation starts at the original force point, before yielding the parent's
job slot. It reads no unresolved sibling result or authored wrapper metadata.
Each admitted input gets fresh private native geometry from its verified root
snapshot. Admission verifies actual canonical BREP/SURF lengths and limits the
constructor to eight preparations, 768 KiB BREP and 4 MiB SURF, with additional
tree/count limits. These are work/retention limits, not a native RSS guarantee.
Ordinary force retains its complete-pin check and re-verifies current objects
before consuming its own preparation; placement, metadata and partner baselines
remain ordered. Failure clears unused geometry and retries the normal path at
the same pin. No native prototype cache, background thread or author API was
added. Persisted schemas and output semantics are unchanged.

The 87 focused tests pass, including 28 new tests for both constructors,
concurrent/nested builds, attachment and error rollback, list mutation, object
swap/repair and admission races, cold/RAM/disk STEP/BREP/appearance equivalence,
and independent native vertex/curve/surface/topology ownership. A real one-slot
decorated build consumes a prepared current sibling, finishes all outputs and
preserves the current child's bytes/mtime. Existing blocked-save, failure and
exact-job-pin tests also pass. Both constructor increments received separate
independent reviews.

## Matched production experiment

Two independent warm root interpreters and fresh stores each own a daemon with
two slots and zero spares. Both use the same nine-child fixture rewritten to
plain `Compound(children=parts)`. The control disables only `prepare_for`; the
other host uses production preparation and verified sizing. Two lightweight
wrappers count preparations/consumptions without retaining geometry.

Each host performs 22 calls: priming, one repeated-edit block, then three unseen
diameters (107/108/109 mm) and placements (−0.6/−0.7/−0.8 mm), with restores.
The driver alternates conditions at barriers **before** the original timer;
only one complete call runs at once. Kernel/daemon startup, source changes,
barriers and post-timer digest checks are excluded. Child IPC, all declared
saves and source publication are included. No other task compute overlaps.

| Three unseen inputs; median ms | Control | Prepared |
| --- | ---: | ---: |
| Geometry complete call | 808.20 | 760.04 |
| Geometry source preview | 352.93 | 276.53 |
| Geometry root body | 136 | 127 |
| Placement complete call | 611.05 | 599.47 |
| Placement source preview | 179.24 | 179.66 |
| Placement root body | 48 | 49 |

Every prepared geometry call consumes eight preparations; placement consumes
zero. All 44 calls succeed, match the prior validated root STEP variant exactly,
and verify all nine child pins and actual child output digests. The 22 paired
root outputs match each other. All six unseen digests are new within each host.
Both hosts and owned daemons exit zero; source bytes/mtime are restored.

**Keep the stalls.** Geometry complete-call samples are 1566/692/808 ms for the
control and 1206/719/760 ms prepared; previews are 948/268/353 and 746/277/245 ms.
The first control sample spends 339 ms in source-result preparation and 366 ms
in STEP readback. The first prepared sample is already delayed before constructor
preparation: current-child milestones arrive at 336–404 ms, versus 46–55 ms in
the control, and the carrier source result arrives at 639 ms. The underlying
cause is unproven. Nested stage times must not be added or attributed wholly to
preparation. All prepared carrier-source-to-parent-preview gaps are 98–107 ms;
control gaps are 805/130/216 ms. These are observed milestone gaps, not exclusive
CPU costs. Every root preview still follows its child's save; the blocked-save
tests establish the earlier-preview capability separately. Three samples and
these stalls do not establish a stable latency distribution.

The run spans 21:03:02–21:03:53 UTC. Runtime fingerprint at start and end:
`9990b0e4f5880998596472ee02c28bf0fbd2360e86f5750b7934b04a5646a413`.
The [paired proof](results/ready-sibling-production-children-paired-proof-20260910.json),
[control report](results/ready-sibling-production-children-ordinary-20260910.json.gz),
[prepared report](results/ready-sibling-production-children-prepared-20260910.json.gz),
[control cleanup proof](results/ready-sibling-production-children-ordinary-proof-20260910.json)
and [prepared cleanup proof](results/ready-sibling-production-children-prepared-proof-20260910.json)
retain all calls, source/module provenance, actual hashes, child save milestones,
limits, executed helper/harness source and owned process identities.

This optimization helps split models with a pending child and current siblings.
The monolithic body's expensive build123d enumeration/wrapper and `Select.LAST`
bookkeeping remain. Their nested profiles are not additive; the earlier one-hash
ordered-set experiment showed no useful gain. Reducing that bookkeeping needs
its own exact semantics design, not mutable-shape signature caching or arbitrary
author-function memoization.
