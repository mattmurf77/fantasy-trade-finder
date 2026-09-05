# Activation evidence and remaining gates

## Implemented and reviewed

Original item 2 is `trade_outlook_utility.evaluate_outlook_utility`: explicit manager intent wins, complete lineups are re-optimized in supplied fantasy points, and whole-roster dynasty assets form a separate component. Slot assignment cannot reuse a player. Missing production remains null and disables strict eligibility; dynasty values are not point projections.

Original item 3 is `trade_mutual_benefit.evaluate_mutual_benefit`: both normalized gains must be meaningful, complete and sufficiently evidenced. The weaker manager benefit ranks first, total benefit second, then package simplicity. Core/Conviction lane quotas remain presentation constraints. A new dark flag `trade.mutual_benefit_v1` implies final roster and market enforcement; turning it on alone cannot publish unchecked cards.

`Context.card` caches only exact final packages. The worker resolves explicit intent before inference and supplies each manager separately. All package mutations finish before roster/utility/market evaluation. Shadow mode preserves the existing deck and records uncertainty. The HTML mockup is not mounted or changed in this rollout.

## Executed checks

- Outlook subagent: 49 focused tests passed, plus sabotage checks that whole-lineup loss and readiness guards fail when deliberately broken (changes restored).
- Mutual-benefit subagent: 101 focused tests passed.
- Integration: 4 tests passed, covering both complete rosters, mutation invalidation, lost backup depth despite fit, missing projections, shadow ordering, weaker-benefit priority and a market veto.
- PostgreSQL telemetry contracts: four passed against the isolated upgraded PostgreSQL database: duplicate proposal event/provider IDs, edited-origin hashes, recording after snapshot failure, and exactly one impression-linked propose outcome. Provider sends were simulated; no offer was sent. See `postgres-contracts.json`.
- Static gates: TypeScript passed, all 90 mobile structural suites passed, testID lint passed, and 175/175 web structure checks passed.
- Existing roster/policy regression cluster: 126 passed before the final diagnostics addition. Full-suite result is recorded below when complete.
- PostgreSQL: recreated the deployed `606e512c` schema in an isolated local Postgres database on port 55439. Ran current `init_db()` twice. All 16 additive columns and both tables appeared. Existing ranking Elo and NULL confidence were preserved; an operator-set `shrink_pseudocount` survived; cross-format confidence round-tripped as 0.75. No production migration was run manually. See `postgres-migration.json`.

## Live read-only evidence

The production readback was transaction-read-only (`SHOW transaction_read_only = on`). Render was serving `606e512c`; new columns and flags were absent before this rollout. There were 63 impressions on September 4 at the read time, and 18 linked leagues: 16 Sleeper, one ESPN, one MFL. These are counts at a moment, not sample-size claims about acceptance.

Three recently updated Sleeper leagues were sampled using public provider settings. One has K/DL/LB/DB/IDP_FLEX and is outside the evaluator's supported template. Another has three co-owned teams; the third has a supported offensive lineup. Do not generalize percentages from three leagues. See `coverage-readback.json` (aggregate only; raw identifiers remain outside the repository).

## What the evidence permits

Collection-only deployment: `trade.valuation_telemetry=true`, `trade.roster_evaluation=true`; `trade.personal_market_policy_v1=false`, `trade.roster_protection=false`, `trade.mutual_benefit_v1=false`. This records the new model alongside existing serving. It does not claim better acceptance or activate strict filtering.

The user requested execution and activation. The earlier TestFlight checklist remains **unexecuted**; backend route tests exercise owned/stale/edited impression linkage and confirmed-provider recording without sending another manager a trade. This collection-only stage has no native UI change or user-visible eligibility change. Its evidence is backend regression, exact-SHA CI and production schema/readback; a live controlled-send check remains a gate for proposal-funnel graduation and enforcement. This is a narrower rollout than the earlier broad activation checklist, not a claim of native verification.

## Hard gates still open for broad enforcement

1. Current-season point data: registered projection providers are stubs (`backend/outlook/strength.py`). Complete format/horizon/freshness coverage must be supplied before `ready_for_enforcement` can be true in live jobs.
2. Provider coverage: unhandled starting slots and missing observed ESPN/MFL settings currently yield unknown. Do not enable the global roster gate across unsupported leagues.
3. Confidence provenance: copy-from-format is persisted as cross_format (0.75), while live viewer placements can be interpreted as explicit (1.0); later publication can also lose that distinction. Durable per-player origin and requester/opponent round-trip parity remain required before market enforcement.
4. Co-owner identity (Q-039): account-keyed board/concept IDs versus provider primary owner need a scoped identity decision before those teams enter comparison cohorts.
5. Observed telemetry quality and latency: >=99% parseable new divergence snapshots, ratio tolerance 0.001, and <=5% p95 end-to-end generation overhead. Local CPU/fixture timing cannot satisfy the production latency gate. G-070's synthesized likes-you fairness uses a legacy display basis; report it separately until corrected, never silently count it as agreement.
6. Controlled live proposal attribution and a deck-job-level crossover allocation/readout. Unviewed offers are not negative labels, and no acceptance uplift has been measured.

## Reproduction

Run `python3 -m pytest backend/tests -q` after all agents stop editing. CI uses Python 3.12; the local Python is 3.14.4. Run mobile TypeScript, all mobile/tests/check-*.js suites, testid-lint and qa/web/check_web_structure.py. PostgreSQL validation initializes an isolated cluster and loads the base schema before the current upgrade; it must never point at DATABASE_URL_PROD.

## Full-suite execution record

The frozen local run was interrupted for diagnosis after 3,933 passed / one existing opt-in skip, 562.63 seconds, with no failures. It was still progressing through CPU-intensive existing generator tests; no infinite loop was established. This is not recorded as a complete suite pass. The remaining modules then passed: 983 tests in 57.39 seconds, including 17 overlapping cases. Against 4,900 collected tests this covers **4,899 unique passes and one existing skip**. Backend source hashes remained unchanged across both runs. A complete uninterrupted pushed-revision Python 3.12 CI run remains the release gate.

## Main integration

While this PR was being opened, `db6b3a17` (#277, request scoring/captured execution context) landed on main. It was merged into the requested branch. The auto-merge revealed a semantic seam: the worker's reduced session no longer carried league identity. `_TradeExecutionContext` now freezes `league_user_id`, and the reduced session keeps both the account and provider owner IDs. A delayed-job regression changes the live session after kickoff and proves roster evaluation retains the original owner and roster.

After integration: 104 focused tests passed in 9.81 seconds (scoring context, policy/roster wiring, mutual integration and pick assignment). Complete CI must run on this merged revision; earlier local counts describe the pre-merge revision. No production setting has been changed at this point.
