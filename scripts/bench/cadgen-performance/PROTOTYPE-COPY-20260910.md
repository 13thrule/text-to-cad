# Private prototype copying experiment

A hidden native prototype followed by a full geometry copy for every consumer did not improve the measured boundary. Keep the current private BREP reconstruction. No production cache changed.

| Complete operation, median ms | Current BREP reconstruction | Hidden prototype + full copy | Change |
|---|---:|---:|---:|
| Nine child materializations, initial baselines, fresh integrity verification and private document preparation |110.93|117.20|+5.65%|
| Nine operation-result replays, initial baselines and fresh integrity verification |43.65|45.31|+3.80%|
| Nested curved/rotated materialization, baselines, verification and document preparation |2.91|3.01|+3.36%|

Each row uses four warm interleaved samples after one cold sample on each path. The probe uses the real nine-part authored BREP payloads and a four-solid sphere/torus/box/cylinder fixture with nested, rotated and mirrored placement, face colors and PBR metadata. It times the whole consumer boundary, excluding imports, fixture preparation, child IPC and STEP saving. The original capture and exposed-shape verification remain active; timing only the native Copy call would miss their cost.

Every candidate consumer, including the first, receives `BRepBuilderAPI_Copy(copyGeom=True, copyMesh=False)` of a never-exposed prototype reconstructed from canonical bytes. Cold, RAM and cache-reset paths have equal BREP bytes, wrapper metadata and STEP exports within that scheme. Candidate BREP bytes differ from current reconstruction, an allowed comparison; the real nine-part STEP stays byte-identical (`406dd2e19b6a4ea3a623abd19b03708b7d9e97b4402ba4161c737eb31f10fdca`). Native vertex, curve, surface and compound mutations, meshing, metadata changes, cache reset and deleted pinned BREP checks passed without contaminating another consumer or the hidden prototype.

These are bounded checks, not a proof over all OCCT geometry. Cache reset simulates fresh disk reconstruction in one process; no separate fresh-process or broad downstream-operation corpus was run, and no production native-memory admission policy was implemented. The negative total-boundary result stopped expansion. A first scratch attempt failed before timing because its face-color ordinal was zero; the corrected fixture uses positive ordinals, and both logs are retained.

The [raw result](results/prototype-full-copy-20260910.json) embeds the exact executed scratch helper, its SHA-256, individual samples, isolation results, artifact paths and environment. The successful run began at 19:16:06 UTC on September 10, 2026 with runtime fingerprint `187df07eeae0de97674b43bd65ca08617b33fa80ec952d8b4e0bc1ed8a7d9313`, unchanged through the run. No other task's build, browser or tests overlapped the granted compute window. STEP artifacts remain under the reported `models/tmp` directory and are not part of this report.
