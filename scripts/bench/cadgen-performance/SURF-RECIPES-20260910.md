# Immutable SURF face-color recipes — September 10, 2026

Four warm interleaved samples favored retaining normalized face-color tuples,
while rereading and SHA-256 verifying the complete SURF payload on every lookup.
Each exposure receives a new dictionary. No native shape or decoded geometry
index is retained by this recipe cache.

| Complete boundary | Existing median | Recipe median | Change |
| --- | ---: | ---: | ---: |
| Nine real child results | 117.39 ms | 77.25 ms | −34.2% |
| Nested, curved, rotated assembly | 3.38 ms | 2.50 ms | −26.0% |

The measured boundary includes child materialization, initial mutation baselines,
fresh live integrity verification, and private root-document materialization.
It excludes STEP persistence and job transport. Samples share one interpreter;
the initial cold sample is retained separately and excluded from these medians.
This probe establishes a local saving, not an end-to-end build claim.

An instrumented nine-child pass spent 35.29 ms parsing SURF JSON, 18.06 ms
capturing initial baselines, and 18.12 ms verifying exposed shapes. Instrumented
stages nest: geometry fingerprint and object-read rows must not be added again.
The immutable recipe avoids parsing geometry arrays solely to recover colors.

BREP bytes and metadata matched across existing/candidate, cold, RAM-hit and
reset paths. Exposed face-map mutation stayed private; missing or corrupted SURF
objects failed even after a recipe hit. The shipping implementation also charges
the actual retained tuple/scalar sizes with conservative entry overhead, caps
entry count at 1,024, and verifies BREP bytes before first memo admission. Those
admission and memory-accounting changes are covered by focused regressions; they
were not part of this scratch timing. Saved-scene color parsing is unchanged.

The final recipe budget charges only retained tuples/scalars and entry overhead;
unretained payload bytes do not exclude a large, uncolored SURF's tiny recipe.
An [untimed access replay](results/surf-recipe-occupancy-20260910.json.gz) of the
retained nine-part study's child forcing and document preparation sequences
produced identical decisions under the former payload floor and final policy:
509 hits, 13 misses, no evictions, and 13 entries. Accounted occupancy fell from
1,952,085 bytes to 8,541 bytes. These are replay counters, not instrumentation
inside the timed process. No native geometry was decoded during the replay.

[Raw results](results/surf-recipe-boundary-20260910.json) contain every sample,
stage, runtime fingerprint, correctness result, and the exact scratch helper
with its hash. CAD fixtures remain under `models/tmp` and are not embedded.
