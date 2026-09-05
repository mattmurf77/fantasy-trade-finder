# Win Now implementation contract

2026-09-04 — implementation authorized by the operator, using Astra subagents with parent review. Branch `codex/win-now-20260904` starts from fetched main `606e512c`; shared original checkout is preserved.

## Security integration update — 2026-09-05

Security release #279 landed concurrently on main `a927e3a7` and is now being integrated. Initial CI for `ee4f37a8` is superseded and is not validation of the merged revision. Mobile 1.17.0 build **146** is superseded; cancellation was confirmed for EAS build `c8104c6e-ed72-42e6-86e4-7ccc78002c85`. A replacement build is pending after integration. Final merged-revision CI, Render and EAS/TestFlight verification remain pending; no new passing result is claimed.

## Source decision

Use external **Sleeper weekly stat projections**, behind a provider-neutral adapter. Public live probes confirmed separate forecast weeks through 17. ADP-only placeholder rows are not projections and must not count as coverage. NFL schedule data certifies byes. The application computes league-scored player distributions, legal lineups, standings and playoff outcomes; it does not derive player points from dynasty value or claim a trained proprietary projection model. Source/method remains beta and timestamped snapshots are retained for prospective evaluation. Normalized imports support later contracted providers without a simulator rewrite. No paid source is purchased. Existing Sleeper authorization is retained; commercial provider terms are not inferred from endpoint accessibility.

## Build ownership

- Astra forecasts: `season_forecasts.py`, `season_simulator.py`, focused tests and source probe.
- Astra optimizer: `win_now_optimizer.py`, focused tests; same policy for generated/custom packages.
- Astra frontend: mobile and web season/Win Now entry, search, edited evaluation and decision UI, client tests.
- Parent: integration, routes, persistence, authorization, jobs/freshness, flags, documentation, all code review and integrated verification.

## Public contract

- `GET /api/league/season-projections?league_id=` returns `status`, `meta`, `teams`, `assets`, `buyer_roster_id`; unsupported data returns a reason, not zeros.
- `POST /api/win-now/search` accepts `league_id`, `objective` (`wins`, `playoffs`, `championship`), `max_dynasty_spend_pct`, `min_fairness`, `protected_ids`; queues a user-owned job.
- `GET /api/win-now/jobs/<job_id>` returns durable status and a result containing baseline and eligible scenarios.
- `POST /api/win-now/evaluate` evaluates an edited package through the same policy, adding `partner_roster_id`, `give_ids`, `receive_ids` to the search settings.
- `POST /api/win-now/scenarios/<scenario_id>/decision` records like/pass without creating any dynasty-ranking signal.

Fractions are 0–1; display deltas in percentage points. Wins objective means the next three remaining regular-season weeks. A dynasty budget is a percentage of a fixed baseline roster-asset value, not outgoing package size. Private boards never appear in public payloads. All user-specific access requires current initialized session, board-read authorization and correct league/team identity; decision/generation writes use the existing verified-write policy.

## Launch restrictions and flags

The implementation began with `outlook.season_projections`, `trades.win_now` and `outlook.championship_probabilities` false. On 2026-09-05 the operator explicitly authorized enabling all three as an experimental beta despite exploratory, uncalibrated evidence. The release candidate now targets true for all three; this authorization supersedes calibration as a prerequisite for this beta, without claiming forecast/title calibration. The championship flag and snapshot capability remain separate mechanical gates. No old title odds are exposed. Forecast/lineup/simulation support is explicit: unsupported live weeks, scoring/rules, incomplete contributors, playoffs already underway, stale data or missing schedule return unavailable. No retries silently relax market fairness or partner/budget policy. Preserved historical scenarios are not current recommendations.

## Evidence and delivery

Unit tests cover provider normalization, real lineup counterfactuals after week three, legality/budget/partner checks, probability accounting, caches/job authorization and no Elo feedback. Mobile uses TypeScript, structural checks and manual TestFlight instructions; web uses syntax/structural and rendered browser checks where possible. No Maestro or native simulator. Parent reviews each agent's diff and tests before integrating. Durable schema/API/architecture/config/invariant docs, scope, ledger and calibration limitations are updated with actual results. No production flag, deployment or native build occurs as an incidental tool action.

## Current implementation status

Implementation and parent review were completed on 2026-09-04. The operator authorized live experimental season/Win Now/championship release on 2026-09-05. Hosted Python 3.12 CI, Render deployment/effective-flag verification and a new mobile **1.17.0** EAS binary/processing remain pending in this record. Physical TestFlight checks and forecast calibration are also unperformed. Parent browser review with synthetic data passed at wide and 390px widths. Authorization is not deployment evidence; [2026-09-05 release record](../../business/ops/2026-09-05-win-now.md) tracks execution. [EVIDENCE.md](EVIDENCE.md) records completed client checks separately from these open gates.

The beta is narrower than the full proposal: Sleeper in-season leagues before fantasy playoffs; QB/RB/WR/TE and supported flex/scoring/bracket rules; complete published weekly forecasts; no live-game continuation. Best-ball and trade review delays are unsupported; disabled pick trading is enforced. Reserve/taxi assets are excluded from lineup/trade eligibility while retaining baseline roster value. Missing contributors or unsupported rules refuse serving. Dynasty picks have no direct points; post-trade original-team pick-price revaluation, explicit drop workflows, other platforms, real proposal preparation and learned acceptance models are deferred.

## Forecast methodology and limits

The adapter reads Sleeper's experimental weekly stat feed (`sleeper_weekly_experimental`), which carries RotoWire revisions, and retains source company/update fields. It does not buy a provider license or infer redistribution rights from a successful request. ADP-only future-week rows are missing coverage, not zero points. Independently verified byes may produce explicit zero rows.

Fleeced scores the stat vectors with supported league scoring, chooses legal lineups **before** sampled outcomes, and simulates the remaining schedule and supported bracket for all teams. Dynasty rankings affect trade sacrifice/partner attraction only; they never create fantasy-point forecasts. Counterfactuals reuse player/week random worlds and finalists receive an independent-seed check.

Current availability is a limited source input: an injury designation without a week-specific availability estimate is unknown, not a dated return forecast. The simulator withholds results when unknown availability can affect a contributor. Healthy current status is not a model of future injury risk. Independent player/week normal residuals use explicit imported scales or the disclosed heuristic `max(3, 0.6 * abs(mean))`; shared NFL game/team correlation and multiweek injury correlation are **not modeled**. Sampling precision is not forecast calibration.

A snapshot expires at the short serving TTL or the earliest known source game boundary, whichever is earlier. A date-only feed is cut off conservatively at midnight UTC on the game's date; this is not represented as an actual kickoff time. Captured/publication timestamps are retained; fetching a historical URL today is not an as-of historical forecast. Source feeds and model/rule coverage retain explicit availability gates. Title calibration remains outstanding; the 2026-09-05 operator authorization permits this experimental beta before calibrated evidence exists.

## Boundaries shared by API and clients

`wins` optimizes expected wins over the next three remaining regular-season weeks. API budget is 0–10 percent of the fixed baseline roster value (omitted default 3); fairness is a fraction from 0.75–1 (omitted default 0.90), and the shared policy may impose a tighter floor. Clients submit the same defaults: 3% / 90%. Edited packages allow at most three assets per side; the optimizer also enforces total package limits. Protected IDs belong to the buyer and never bypass legality.

Cards retain server order and display both teams' next matchup, next-three-week wins, remaining/final wins, playoff/bye impacts, dynasty cost, market balance and partner evidence. Public provenance exposes confidence/coverage/intent summaries, not raw boards. Requests and expiry cancel local polling; errors and empty results have manual recovery. Win Now uses separate state and decision endpoints, without changing dynasty sorting, caches or Elo feedback.

## Review corrections and operating limits

Parent review corrected paired confirmation nesting, public scenario/asset contracts, exact package lineup screening, fair candidate coverage across targets, source-wide game cutoffs, source-age expiry and post-evaluation expiry. Completed cards and decisions recheck league, pick, preference and valuation revisions. No-cutoff imports cannot be served. Published consensus seeds and trade-only decisions do not become personal dynasty evidence. TE/RB/WR reception and QB rushing premiums derive from projected base events.

Jobs retain the requesting user’s private input for 7 days; scenarios/decisions retain package evidence for 180 days; forecast/projection batches retain replay evidence for 400 days. No complete partner boards are persisted. Account export/deletion covers the user-owned tables, and short persistence guards prevent worker writes after deletion. The durable queue resumes interrupted jobs on the existing single-worker server. Client cancellation stops local polling, not the server computation.

A local synthetic 12-team, 25-player, 9-slot, 14-week benchmark (1,000 draws, 8 finalists, real paired and independent confirmation runs) took 1.14 seconds baseline plus 46.11 seconds search, screening 11,990 packages and returning one frontier row. This measures local latency only; production load and model accuracy require separate evidence. Bounded search can miss valid packages outside the shortlist.

## Historical validation tooling

The [historical validation guide](HISTORICAL-VALIDATION.md) documents the bounded Sleeper outcome collector, offline calibration evaluator and actual source-provenance audit. This completes the outcome collection/evaluation workflow, not the calibration of the new player model. Historical URLs contain post-game revision timestamps; valid full-horizon pregame input archives and supported league configurations are still needed.

The operator subsequently authorized an exploratory run with the available revised data. [Results](EXPLORATORY-RESULTS.md) contain actual model/evaluator measurements and exclusions; strict archived-input evaluation remains unchanged. That exploratory run made no production changes; subsequent beta-release authorization is recorded separately above.

## Release scoring boundaries — 2026-09-05

Known kicker/team-defense scoring coefficients are removed only when the league has no corresponding active K or DEF/DST/`D/ST` slot. This uses finite allowlists, never broad prefixes; active K/DEF/IDP formats remain unsupported. Raw `source_scoring_settings` are retained alongside effective rules in the immutable league/snapshot identity.

Separately, nonzero finite coefficients for exactly `st_ff`, `st_fum_rec`, `st_td` and `fum_rec_td` are omitted when the forecast provider does not declare support. This is an explicit beta approximation for offensive-player special-teams/fumble events, not an unused-position normalization or a zero-event forecast. Metadata preserves the exact excluded coefficients in `scoring_exclusions` and supplies the warning **“Rare special-teams/fumble bonuses are not projected.”** Provider-supported keys remain in scoring. Unknown scoring rules and invalid values still fail validation; no general unsupported-scoring bypass is authorized.

## Release rollback

Set all three serving flags false and verify the running process. Prior main commit `a927e3a7` is the code rollback target; preserve evidence tables and raw historical artifacts. Mobile 1.17.0 is planned, not yet proven installed or available in TestFlight. [2026-09-05 release record](../../business/ops/2026-09-05-win-now.md) owns release status.
