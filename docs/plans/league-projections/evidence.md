# Evidence and limits

Date: November 7, 2026 UTC (November 6 Eastern). Synthetic fixtures only in tests; no production mutations, outreach, database copy, simulator or Maestro.

## Current v3 mean-contract correction

Local projection/account-deletion/flag-mirror checks: **216 passed in6.67s**. TypeScript, stored-read structural guard,3 web DOM assertions and test-ID lint passed. Independent review: **142 tests plus3 actual DOM assertions**, with runtime source hashes unchanged before/after. These include90-digit root-oracle comparisons, zero/deterministic/negative-gap cases, mean/variance/correlation checks, extreme-location/gap numerical stability, subcent rounding, exact actual-outcome RNG parity and old-engine baseline comparison rejection. Test data is synthetic; no predictive calibration is inferred.

[Source-bound v3 benchmark](benchmark-synthetic-result-v3.json):250000 scenarios,12 synthetic teams,six weeks/36games, **34.916seconds**, **156368896-byte peakRSS** on Python3.14.4/Mac. Core/simulation/joint helper hashes match the reviewed candidate. Local targeted tests were also running during the beginning of this measurement; this is an observed local wall-time/CPU-memory sample, not an isolated throughput comparison or hosted p95. The pure simulation does not measure provider ingestion.

Engine v3 preserves the requested unrounded Max PF mean with a shifted positive-gap construction; latent dependence is distinct from realized dependence. Rounding adds at most half a scoring unit to the expectation and finite simulation averages have Monte Carlo error. Old v2 output remains historical. See [mathematical contract](decoder-evidence.md#mean-preserving-joint-policy--corrected-engine-v3). Source coverage, licensing, historical as-of calibration and device/runtime gates remain unresolved and disabled.

## Coverage follow-up — historical v2 candidate

The finite offense decoder, policy admission/execution gates, explicit provenance, model-v2 floor diagnostics and source-contract scenario compatibility are implemented. See [decoder evidence](decoder-evidence.md). Local targeted backend/account-deletion/flag checks: **165 passed**,6.33 seconds; TypeScript passed. Both stored-read structural guards and3 actual web DOM assertions passed. Independent current-source review is recorded below after binding. No production gate was enabled.

## Initial implementation evidence (historical)

- `python3 -m pytest backend/tests/test_league_projection*.py backend/tests/test_account_deletion_coverage.py backend/tests/test_seed_ui_test_db.py::test_release_flags_mirror_features_json -q`: **135 passed**, 5.39 seconds. Projection cases include exact assignment against200 brute-force cases, Decimal/negative/custom scoring, lock/hindsight pools, joint probability/record/ownership invariants, source mismatch/incomplete history, weekly DST boundaries, account deletion/recreation, queue crash windows, atomic last-success publication, worker fencing, one recovery, immutable recovery input, retention beyond weekly boundary, read-only GETs, owned saved-input scenarios, and flag mirror.
- Independent reviewer: **52 pytest cases and3 actual JavaScript DOM assertions passed**, with runtime hashes unchanged before/after evaluation. The independent run and synthetic joint output are retained in the parent audit's projection-capability-evaluation folder. Builder-imported copies make regression cases part of repository CI.
- `tsc --noEmit`: passed. All160 mobile structural suites passed after updating the existing guard to require stored-mode exclusion of the old standings query. The added web DOM guard verifies first render, retention on same-context transport failure including working comparison controls, and clearing on league change.
- Web structural gate: **260/260**. Mobile test-ID lint passed. No native rendering was executed; device evidence remains below.

## Engine v2 synthetic performance (historical)

[Updated source-bound artifact](benchmark-synthetic-result-v2.json):250000 scenarios,12 synthetic teams,six future weeks/36games: **30.119 seconds**, **154861568-byte peakRSS**. Core/simulation hashes match the historical v2 candidate, not the v3 correction. The artifact's provider hash precedes a later boolean-`gp` validation edit; provider code is not executed by this pure simulation benchmark. This is CPU/memory evidence on Python3.14.4/Mac, not hosted p95, source ingestion, full-cohort throughput or forecast accuracy.

## Initial engine synthetic performance (historical)

[Reproducible harness](benchmark-synthetic.py), [source-bound result](benchmark-synthetic-result.json). Twelve synthetic teams, six future weeks/36 games,250000 scenarios: **27.132 seconds**, peak process RSS **157319168 bytes**, Python3.14.4 on this Mac. Playoff sum6 and each of six pick-column sums1. The initial04d034f implementation core.py/simulation.py SHA256 values matched this artifact; this is historical and does not bind the later v2 engine. Other API/store edits after the measurement do not enter this pure benchmark.

An earlier unbound exploratory run took27.32 seconds; the later run was repeated to capture exact engine hashes and memory. Neither measurement is hosted p95, cohort throughput, source ingestion latency, source accuracy or a device result. CI uses Python3.12, so its full run remains the parent's ship gate.

## Code-walk proof

- `backend/league_projections/core.py:120` consumes only native eligible assignment edges and distinct players, preserves locked actuals, and uses actual outcomes for hindsight. `:172` gives real-player cardinality priority before bye-only hypothetical additions, allowing dual-position reassignment without replacing real coverage.
- `backend/league_projections/simulation.py:64` draws actual and Max PF in the same season, derives playoff membership before sorting non-playoff picks, and maps ownership after original-team assignment. Expected/modal/distribution and conditional sample semantics are separate.
- `backend/league_projections/provider.py:51` normalizes observed provider-native exact timestamps, schedule completeness and future participation scenarios. `:145` validates original league/roster identity, actual viewer owner/co-owner binding, official totals and immutable consumed inputs; unknown projected scoring stays explicit and capture crossing kickoff fails.
- `backend/league_projections/store.py:32` atomically inserts a baseline and consumes that weekly slot under the live-user/target-generation fence. `:83` claims a worker token. `:100` atomically publishes completion and last-success under the same fence. Old workers cannot publish after recovery/deletion.
- `backend/league_projections/batch.py:45` registers only a future weekly target. `:96` dispatches due work under bounded leases. `:136` reads state without enqueue, provider access or simulation.
- Mobile Standings `:76` and League Summary `:575` exclude legacy compute queries in stored-batch mode. The shared section's only ordinary action checks saved data; scenario mutations are explicit button presses. Existing parent navigation/FAB ownership remains unchanged.

## Manual TestFlight checklist — not executed

Use a staging/test backend with synthetic stored results; do not activate unreviewed production source/policy gates merely to perform UI checks.

1. With the new feature off, verify Current/Projected and League Summary preserve their existing behavior. With it on, enter Projected and League Summary and confirm network traffic contains saved-result GETs only; no provider/run POST occurs on entry, focus, league switch or ordinary refresh.
2. Select a newly connected synthetic league with no run. Current records remain accessible; no fabricated probabilities appear. Its next weekly eligibility is displayed when registered; unknown completion time is explicit.
3. Seed queued, running, current, stale, incomplete, unsupported and failed-refresh states. A failed refresh retains the last successful timestamp/model/result. Lose network after a valid display: retain that same-context result. Switch leagues/accounts: never retain another context's result.
4. Inspect all teams at large Dynamic Type and with VoiceOver. Fixed-width playoff/pick columns scroll horizontally and align; expected/modal W-L-T, null low-sample conditional picks, original/current owner, and projected-Max-PF sorting labels remain distinct. Verify team/week lineups, gaps, hypothetical bye replacements and requested versus simulated Max PF mean, expanded latent/realized diagnostics, rounding bound and uncalibrated-uncertainty labels. Confirm an old-model baseline remains readable but cannot queue a supposedly weight-only comparison on the new engine.
5. Explicitly queue40/60/80 saved-input comparisons on staging. Verify the baseline remains unchanged; the same snapshot is used and updates appear only after background processing. Verify web retained controls still work after a failed read and exported CSV/manifest contain the same run assumptions.
6. Observe one staging weekly batch across a due boundary and inspect provider/job logs without private payloads. Confirm one baseline per target/weekly slot, bounded interruption recovery, no duplicate publication, and retained prior success on failed replacement. Record device/build/environment/timestamps and actual outcomes before rollout.

## Unmet evidence

Full-roster real-league coverage outside the admitted finite offense contract; complete reference custom-IDP/kicker forecasts; permission evidence for new feed use; original prototype parity; leakage-free historical calibration; actual deployed batch/DB-memory throughput; native device usability. These are explicit release gates, not hidden passes.
