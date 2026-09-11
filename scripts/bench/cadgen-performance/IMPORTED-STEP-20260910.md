# Imported STEP edits — 2026-09-10

## Latest matched repeat/unseen study

The current checkpoint includes verified exact-byte readback reuse, 768 KiB inline
component extraction and operation-cache version 6. Its matched results
supersede the intermediate timing table below:

| Complete call, median ms | BEFORE | AFTER | AFTER source preview |
| --- | ---: | ---: | ---: |
| Unchanged source | 15.70 | 11.34 | No new preview |
| Previously emitted geometry value | 867.91 | 387.67 | 140.09 |
| Previously emitted placement | 855.15 | 421.54 | 167.87 |
| New geometry value | 926.84 | 649.98 | 153.22 |
| New placement | 869.47 | 742.61 | 194.59 |

Each category has three observations; new-value observations use three distinct
inputs. All nine actual STEP variants match between runtimes. New output bytes
still require STEP parsing, so the repeated-output gain must not be attributed
to every edit. Repeated public reads improve from 257.60 to 31.19 ms. First
empty-store public reads are 256.56 versus 4,200.79 ms, including the current
compile worker's startup and canonical publication. First empty-store builds
are 6,892.95 versus 6,199.21 ms; both are single observations with the root
kernel already imported.

[Original](results/imported-before-unseen-final-20260910.json.gz),
[current](results/imported-after-unseen-closure-final-20260910.json.gz), and the
[cross-task comparison](WARM-COMPARISON-20260910.md) retain the complete call
logs, restored-source proof, output identities and runtime fingerprints.

## Earlier source-result checkpoint

The same nine-part STEP and ordinary model source were run on reviewed commit
`7aa3e85be76f305437abd3d7aba26e38b28e43cb` and the working runtime preserved
at commit `ff6ff1679`.
The model calls public `read_step`, changes only the carrier, and saves the
whole assembly. It contains no gear-generation code. Geometry, names, colors
and saved STEP bytes match across both revisions for every variant.

| Warm operation | Reviewed baseline ms | Current ms |
| --- | ---: | ---: |
| Unchanged source, complete call | 12.08 | 10.16 |
| Carrier diameter 105 → 106 mm, complete saved build | 745.69 | 560.83 |
| Carrier placement −0.5 mm Z, complete saved build | 778.00 | 588.99 |
| Diameter edit, source preview available | Not emitted | 126.25 |
| Placement edit, source preview available | Not emitted | 148.48 |

These are medians of three measurements after the normal harness priming
schedule. Diameter completion ranges are 727.03–810.89 ms before and
553.45–590.39 ms after; placement ranges are 769.29–800.61 ms before and
585.85–600.08 ms after. Current preview ranges are 122.41–140.98 ms and
147.32–168.88 ms. Preview is the server's source-tree event, not a browser
frame. The older revision has no such event, so its completion time is not
an observed preview time.

The body, including public STEP loading and the local edit, fell from
243 to 27 ms for diameter and 268 to 51 ms for placement (rounded stage-log
medians). Complete saved builds improved by about 25%. Whole-assembly STEP
publication remains the largest cost: current assembly/write medians are
147/148 ms and saved-STEP readback is 247/250 ms for diameter/placement.
These stages are nested in the full call; do not add them to its duration.

The first empty-store build took **4,590.14 ms before and 8,106.00 ms after**.
These are single observations with the root kernel already imported. The
current reader's first import compiles and publishes the foreign document,
including a compile process's startup, before later reads can materialize
it from the store. The reviewed baseline reparses this foreign input on
executed edits. Both first-build costs are retained; the warm speedup does
not imply a cold-start speedup. These timings precede the subsequent
[small-batch extraction scheduling change](COMPONENT-EXTRACTION-20260910.md).

Raw records: [before](results/warm-imported-before-7aa-20260910.json.gz),
[after](results/warm-imported-after-20260910.json.gz). The sibling `-logs/`
directories preserve all 20 build calls per revision, including priming
and restoration. Every call exits zero with zero operation-cache errors.
Every measured diameter edit has 12 baseline or 21 current operation-cache
hits; placement has 9 or 18. No measured edit has a miss. Observed root-process
peak RSS is 564.89 MiB before and 553.36 MiB after; those figures exclude
separate compile-worker peaks.

## Geometry and identity checks

The [fixture](../../../models/examples/performance/planetary_imported/README.md)
uses the same carrier operation as `freecad_edit.py`: a cylinder from Z = −5
to −1 mm, cut by three 6.4 mm holes on a 42 mm radius. Placement moves the
original imported carrier. The other eight parts retain their native
topology (`IsSame`) in an independent source-body check. Both revisions'
[before validation](results/imported-before-validation-20260910.json) and
[after validation](results/imported-after-validation-20260910.json) verify:

- Nine valid solids, identical names/colors, and expected volume, area,
  bounds and topology counts for all three source results.
- The same facts from fresh-store reads of each saved STEP.
- Exactly equal saved STEP SHA-256 values across revisions for baseline,
  diameter and placement variants.
- Unchanged input bytes and restored source bytes/timestamps.

The measured-run checker additionally passes for every priming, measured
and restoration call: nine occurrences and nine components; diameter
replaces exactly one component; placement retains all nine. Its per-call
results are embedded in each raw report's `importedStepStudy.componentChecks`.
The source closure contains the fixed foreign STEP. Both reports confirm
closure restoration and unchanged runtime fingerprints during measurement.

## Provenance and reproduction

The baseline uses the verified read-only archive described in
[BEFORE-7AA-20260910.md](BEFORE-7AA-20260910.md). Its runtime fingerprint is
`cd405009b4828ccdf1edc4f555ed6ad75f6db8f59f6a25ce36fdaad245daab54`;
every loaded cadgen module was asserted to come from that archive.
The current measured fingerprint is
`e9ac022fc868e9f4e557bd7da8175ad992a5b74dd022b163979342d2353776a3`.
Both use Python 3.13.13, build123d 0.11.1 and cadquery-ocp 7.9.3.1.1 on the
same Apple M1 Max host. Other workers paused compute for both timed runs.

The exact fixture source SHA-256 is
`9d2e0ce1173ce891e7579875d61d1d3a3ceff1f3835cfd2c8c2bd3495b3f6a25`.
The foreign input is 2,268,663 bytes, SHA-256
`406dd2e19b6a4ea3a623abd19b03708b7d9e97b4402ba4161c737eb31f10fdca`,
the same input used by the retained-document FreeCAD diagnostic. The
baseline saved output is 2,473,275 bytes with SHA-256
`1750dc61e08ba5429dfa773258cb0548acd0b57abb14a56a59221f57994dbf3d`.
The extra output bytes are identical across runtimes, with matching geometry.

Use `imported_step_edit.py prepare` and `validate` as shown in the fixture's
README. Current measurements used:

```sh
PYTHONPATH="$PWD/packages/cadgen/src" PYTHONDONTWRITEBYTECODE=1 \
  "$CAD_PYTHON" scripts/bench/cadgen-performance/warm_build.py \
  --model models/tmp/planetary-imported-study/src/planetary_gear_assembly.py \
  --store models/tmp/planetary-imported-study/study-store \
  --report scripts/bench/cadgen-performance/results/warm-imported-after-20260910.json \
  --iterations 3 --skip-imports \
  --placement-from 'CARRIER_OFFSET_Z = 0.0' \
  --placement-to 'CARRIER_OFFSET_Z = -0.5'
```

For the baseline, the same prepared source and input bytes live under
`/private/tmp/cadgen-before-7aa.3YIWp2/models/imported-study`. Its unchanged
`bench/split_warm_build.py` adapter accepts the same flags; use that archive's
`packages/cadgen/src` on `PYTHONPATH` and its own `study-store`. The adapter
adds archive/module provenance only; no split-child flags are used here.
Both raw reports embed the executed timing harness and fixture source.
The measurement excludes root Python/kernel startup, source writes and
browser work. STEP loading, local editing, source-tree publication and
whole saved-STEP completion remain inside each executed edit's call.

FreeCAD's corresponding headless diagnostic retains the imported document
in memory. Its local edit, native changed-part mesh, whole STEP export and
readback are separate stages. Compare those boundaries explicitly with
this public-read-and-save workflow; this study adds no FreeCAD GUI or
matched mesh-quality measurement.
