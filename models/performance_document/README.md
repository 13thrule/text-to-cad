# Document-engine benchmark fixtures

These are the small, permanent source fixtures for the P0/P1 retained-document
benchmark. `plate.py` is one plate with four through-holes and four corner
fillets. `assembly24.py` places 24 labeled occurrences of one equivalent plate
prototype. Both use ordinary `@step` source and a geometry-dependent native
query. Neither uses `@memo` or a benchmark-specific authoring utility.

The harness copies a fixture below `models/tmp/` before changing the exact
`BENCH_GEOMETRY` and `BENCH_PLACEMENT` constants. It never edits these sources
and it keeps generated STEP, stores, and readback state below `models/`.

The optional `CADGEN_DOCUMENT_BENCH_SOURCE_TRACE` side effect records that the
ordinary Python body ran. The retained engine contract requires one record for
every source command. A missing record on the legacy unchanged path is reported
as historical whole-call-gate behavior; it is not a geometry failure.
