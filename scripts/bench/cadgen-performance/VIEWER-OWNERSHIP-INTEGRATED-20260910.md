# Integrated medium viewer validation

Committed `8971f760d` passed the planetary adaptive check and seven bounded functional ownership checks: **90 assertions passed**. No tendon-hand workload was run. The user’s existing viewers stayed running, and the current verified planetary viewer is [port 3276](http://127.0.0.1:3276/?file=planetary.step).

The successful restoration screenshot exposed one presentation defect: the restored scene still carried the earlier “being restored” alert. Geometry, selectors, selection and memory ownership had recovered correctly. The narrow alert fix, committed as `c07488e1d`, is now verified: the one moderate restoration follow-up passed all 15 assertions, including clearing the obsolete overlay after actual adoption. The earlier 90 assertions retain their original client identity.

## Identity and scope

The new server captured its own loaded `cadgen` and viewer module paths before launch, with no CAD kernel imported. It runs the primary Python environment against this worktree’s package, serves the existing `models/tmp/viewer-matched-nine-after` directory and canonical store, and owns PID 73240. Ports 3262, 3267, 3273, 3274 and 3275 were preserved.

Every successful report proves unchanged source, HTML, referenced client assets and actual emitted worker bytes before and after its private browser. The integrated source fingerprint is `e375623ab5dddd082e6113635b2fab861943547accc11c97d390f7e59cbeb77a`; the client fingerprint is `5cf47abe1c444dbfa742acadb51486126ae634d6ebf6e8895baf6646b3e19cc4`, with entry `index-Zgn0he5b.js`. Locked and installed Three 0.185.1, BVH 0.9.14 and React 18.3.1 agree.

The [compact summary](results/viewer-ownership-integrated-summary-20260910.json) records raw report hashes, exact server provenance, assertion counts and preserved failed preflights. The earlier isolated selection-only client is a separate result. These checks neither amend it nor claim a matched speedup against it.

## Results

| Check | Result and evidence |
| --- | --- |
| [Planetary default adaptive](results/viewer-nine-adaptive-ownership-integrated-20260910.json.gz) | All 13 gates passed. Nine parts stayed complete; every settle phase reached quality satisfaction with no unmet targets. Resize, orbit, zoom, return and selection clearing passed. Peak renderer RSS was 210.56 MiB; orbit frame-interval p95 was 8.7 ms. |
| [Planetary selected face](results/viewer-nine-selection-ownership-integrated-v2-20260910.json.gz) | Face `topology\|o1.1\|face\|o1.1.f1` remained selected through 800% and 100% zoom. Selector face-run coverage matched the displayed component triangle counts. Hide and Reveal worked. |
| [Required-selector load failure](results/viewer-nine-selector-failure-ownership-integrated-v2-20260910.json.gz) | One protocol-correct worker failure rejected the concrete L3 request before publication. The policy’s permitted intermediate L2 fallback retained a matching mesh/selector pair, complete view and selected face. Failed L3 remained parked; leases drained without restoration or a retry loop. |
| [Partial-scene restoration](results/viewer-repeated24-restore-ownership-integrated-20260910.json.gz) | Failure on the second changed material proved a new geometry was already attached. The reservation remained held, teardown occurred, and all 24 occurrences and the selected part returned. |
| [Exact selected-component restoration](results/viewer-repeated24-restore-selectors-ownership-integrated-v2-20260910.json.gz) | The actual old cylinder source-mesh identity was restored, its selected face persisted, and old-level selector coverage matched the displayed triangles. The failed candidate did not remain displayed. |
| [Restoration also fails](results/viewer-repeated24-fatal-ownership-integrated-20260910.json.gz) | Both injected failures fired. Full teardown left zero scene records, the scheduler stopped with `sceneFailed` and unmet quality, the lease released after disposal, and no retry loop followed. The prior-view survival claim is intentionally false for this case. |
| [Delayed reply and model replacement](results/viewer-nine-delayed-replacement-ownership-integrated-20260910.json.gz) | A real successful worker reply was delayed by 1.5 seconds. Switching to repeated24 completed; the stale reply could not overwrite its scene or introduce planetary CIDs. Ownership drained and quality settled. |
| [Cleanup failure and retry](results/viewer-repeated24-cleanup-ownership-integrated-20260910.json.gz) | One instance-material disposal failure kept the pending owner and reservation charged. Switching to planetary retried disposal successfully, released the old lease and produced a complete settled nine-part view. |

The healthy adaptive run used a coordinated window. Later fault cases are functional checks and could overlap installed-wheel validation or small prototype tests; their durations are not isolated performance measurements. Each private context had a 40-second and 2 GiB guard. No forced GC, heap snapshot or allocation sampling was used. Frame intervals measure browser cadence, not GPU completion.

## Visual review and completed alert fix

[Healthy planetary](../../../models/tmp/viewer-matched-nine-after/adaptive-ownership-integrated.png) and [selected face](../../../models/tmp/viewer-matched-nine-after/ownership-integrated-selected-v2.png) show the expected complete assembly and selection. The [restored cylinder](../../../models/tmp/viewer-matched-nine-after/ownership-integrated-restore-selectors-v2.png) retains the selected face but still shows the obsolete recovery-in-progress overlay. The [fatal case](../../../models/tmp/viewer-matched-nine-after/ownership-integrated-fatal.png) correctly shows an empty view and a reload message. The [cleanup retry](../../../models/tmp/viewer-matched-nine-after/ownership-integrated-cleanup.png) returns to the complete planetary model.

In the measured source, `CadViewer.js:4070` clears local error state after success; lines 4077–4079 confirm adoption. Lines 4104–4107 set the runtime recovery alert, which `CadWorkspace.js:3025–3026` keeps until explicitly changed. The success path does not retire that alert. The correction stores the exact failure alert object and clears it only after actual successful adoption, via a functional state update that preserves any different newer alert. Fatal and unresolved cleanup failures do not reach that success path. Independent source review found no issue with this guard.

The [alert follow-up](results/viewer-repeated24-restore-alert-ownership-integrated-20260910.json.gz) and [fixed screenshot](../../../models/tmp/viewer-matched-nine-after/ownership-integrated-restore-alert-fixed.png) prove successful recovery with the obsolete overlay removed. Its source fingerprint is `79d372a2556ea7834e16d1fb76626238becc0387d4f6da57e3dbcea27967c374`, client fingerprint `e92d1df1dae49813e7602c336fa054738701637b5a8fc77bed009b752d494567`, and actual served entry `index-C3AyN2uh.js`. No full adaptive run was repeated.

Root independently reviewed all six linked screenshots, including the selected planetary face and the final restored cylinder without the stale alert. This agent inspected the healthy, selected, original restoration, fatal and fixed restoration screenshots; root additionally reviewed cleanup. The exact review boundaries are recorded in the summary.

## Reproduction and failed preflights

The durable healthy command is `scripts/bench/viewer-memory/adaptive.mjs`, with the current server on port 3276, `planetary.step`, 9 components/9 occurrences, a 60-second deadline, the unchanged 2048 MiB bound and resize to 1100×800. Set `PLAYWRIGHT_FROM` to `/Users/jakefitzgerald/robots/text-to-cad/apps/viewer/node_modules/playwright` in this lightweight checkout. The raw report records the complete arguments and harness hashes.

The functional scripts are private diagnostic helpers under `/private/tmp/cadgen-performance-20260910/`: `integrated-medium-common.mjs`, `integrated-medium-proof.mjs`, `integrated-selection-v2.mjs`, `integrated-selector-fault-v2.mjs`, `integrated-scene-fault.mjs`, `integrated-paired-restore-v2.mjs`, `integrated-replacement.mjs` and `integrated-cleanup-retry.mjs`. They inject faults only in their own browser contexts and never alter served assets, canonical cache bytes or other viewers. Exact successful helper sources, byte hashes and commands are embedded in the [reproduction artifact](results/viewer-ownership-integrated-harness-20260910.json); the alert follow-up uses separately frozen proof and helper copies.

Four preserved preflights are qualified in the summary: missing local Playwright before browser launch; Show versus the real Reveal action; an overly strict assertion rejecting permitted intermediate LOD fallback; and an untriggered material fault that initially inspected old React props instead of the in-progress Three scene. None is silently reported as a passing path.
