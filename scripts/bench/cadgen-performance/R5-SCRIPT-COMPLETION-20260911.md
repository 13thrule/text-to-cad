# R5 script-completion validation — 2026-09-11

## Status

Passed. The primary raw evidence is
[results/r5-script-completion-20260911.json](results/r5-script-completion-20260911.json.gz).

## Method

The bounded harness compares the frozen candidate package to a private copy
with only `cadgen/authoring.py` replaced by its exact pre-change file from
`4406d16148f617cbd1b5bf12a5c34f2da4e84add`. It invokes a real model file as
`python model.py --json`, then measures process creation through exit. Its
eight timed public calls cover two and 24 simple occurrences, each with an
unchanged source and a nonce-bearing placement revision. Pair order alternates.

Each package has its own private store, daemon state directory, and socket.
Before each pair, that exact package starts its worker and writes the base
source/output revision through the public `python model.py --json` door. The
unchanged timed call uses that primed revision. The nonce-bearing placement
revision is deliberately unprimed so its normal source gate must execute; its
readback cost is therefore not equalized. Model source and all
STEP outputs remain under `models/tmp/r5-script-completion`; the private package
copies and daemon state are outside the repository.

Every matched pair must produce identical STEP bytes and exit successfully with
its declared output present. A candidate bare call installs a caller-only
`build123d`/`OCP` import guard, while a candidate assigned-return control reads
the resulting volume and solid count and must materialize native geometry.
The check does not claim a build-only or browser timing.

To reproduce with a fresh baseline package, fixture directory, and result file,
set `CADGEN_PYTHON` to an environment containing cadgen's CAD dependencies:

```bash
git show 4406d1614:packages/cadgen/src/cadgen/authoring.py \
  > /private/tmp/cadgen-r5-authoring-4406d1614.py
"$CADGEN_PYTHON" \
  scripts/bench/cadgen-performance/r5_script_completion.py --run \
  --python "$CADGEN_PYTHON" \
  --baseline-authoring /private/tmp/cadgen-r5-authoring-4406d1614.py \
  --baseline-package /private/tmp/cadgen-r5-baseline-package-repro \
  --fixture-root models/tmp/r5-script-completion-repro \
  --result scripts/bench/cadgen-performance/results/r5-script-completion-repro.json
```

## Result

One alternating baseline/candidate pair was run for each bounded scenario.
The primary boundary is process start through exit, so these are individual
observations rather than stable timing estimates.

| Occurrences | Source revision | Baseline | Candidate | Ratio |
|---:|---|---:|---:|---:|
| 2 | unchanged, primed | 2,634.523 ms | 113.412 ms | 23.23× |
| 2 | new placement, unprimed | 2,713.588 ms | 188.282 ms | 14.41× |
| 24 | unchanged, primed | 2,751.938 ms | 113.458 ms | 24.26× |
| 24 | new placement, unprimed | 2,934.398 ms | 230.763 ms | 12.72× |

All eight calls exited successfully with their declared STEP present. Each
baseline/candidate pair produced identical STEP bytes. The candidate bare-call
guard observed no caller `build123d` or `OCP` modules. The assigned-return
control did materialize the two-solid, 960 mm³ result and load those modules,
preserving consumed-return semantics. The raw report records every row,
package identity, source hash, and event observation.

An earlier rounded checkpoint summary is retained in
[results/r5-script-completion-earlier-isolated-20260911.json](results/r5-script-completion-earlier-isolated-20260911.json).
It used the same frozen product source and boundaries, but is not pooled with
the primary single-pair observations. Its 24-occurrence new-placement baseline
was 5,764.2 ms (candidate 236.6 ms), illustrating baseline process variability;
the final raw above is the canonical rerun after the harness/provenance review.
