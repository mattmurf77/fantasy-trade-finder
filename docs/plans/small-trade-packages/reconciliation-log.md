# Small-player-package presentation — reconciliation

Date: 2026-09-06.

Planner: `cleanup_astra`, completed `ea5cc2b5` [plan](plan.md). Author: `ux_astra`, separate documentation-only pass. Runtime baseline checked: `4026ebc8`. This is not independent approval, implementation, test evidence or release status.

## Round 0 — author decisions and source reconciliation

| Concern | Disposition in completed author draft |
|---|---|
| Fixed bakeoff order currently forbids this change. | PRD §1 states the explicit narrow within-arm exposure-order exception; final post-policy slot classes and generator/draft goldens remain unchanged. Root must record the decision before activation. |
| A sort too late can expose the old order first. | Verified live `final_checks_pending` and the final-policy call. PRD §3.3 places one helper after policy handling, before `server.py:7727`'s first evaluated snapshot, regardless of impression logging. T1/T4 exercise that boundary. |
| Adjacent-only sorting would usually do nothing for three arms. | Disjoint six-absolute-position windows, equal complete class only, max five slots. T1 requires exact A/B/C movement and 16→7 first-three player load, with the real worker rather than mocked expected output. |
| Missing group metadata can be legitimate or an attribution failure. | PRD §3.2 distinguishes captured group-size-zero interleaving, expected-bakeoff missing attribution, and explicitly known organic generation. `run is None` alone cannot invent an organic/fourth arm. |
| Dark bakeoff serving also returns no group metadata. | Root explicitly agreed to exempt `bakeoff_run.served_arm != None` (dark/single-arm validation) in this author pass. Preserve that validation order; legitimate group-size-zero interleaving and real organic jobs remain supported. No broader policy exclusion inferred. |
| Picks and unknowns can falsely look simple. | Existing generic/owned-pick identity plus resolved player classification; pure picks/unknown/malformed cards lock. Mixed packages qualify, pick counts never rank ties. No hard cap or dropped assets. |
| Knob changes can split a job's order, cache and provenance. | One capture for reuse/kickoff/worker/writer; all four cache paths compare mode/version. Old-ID order frozen; #419 filtering only removes while preserving relative order. No polling re-sort. |
| New order can corrupt original source credit or logging gates. | Per-occurrence existing-column record, preserved original arm/group ranks/actual propensity and separate valuation variant. Serving suffix appended before `/bo:<arm>`, with batch-uniform column treatment and both logging flag combinations tested. |
| Scope creep from a small descriptive sample. | No causal/acceptance claim, new arm, generator/membership/value/threshold change, window knob, client reorder or speculative redesign. Existing source/refusal/safety rules remain. |

## Independent planner critique — pending

Send the exact completed author SHA to the original planner. Ask only for material algorithm/metadata, cache/publication, experiment-order, RED-proof or scope defects; then record accepted corrections/rebuttals here. The author does not self-declare zero blockers. Root gate precedes runtime implementation. Parent owns shared index, decision, docs and evidence updates; this author owns exactly `prd.md`, `scope.md`, `reconciliation-log.md`.

## Author verification

Read the completed plan/research, root/backend/docs/plans instructions, coding guidelines and feature-scope template; checked actual policy composition, publication, attribution, config, cache and impression-writer seams. Documentation validation and exact three-file commit are reported separately. No app tests, runtime edits, external writes, activation, push or deployment performed by this task.
