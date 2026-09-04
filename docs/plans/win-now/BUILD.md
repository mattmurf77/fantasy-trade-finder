# Win Now implementation contract

2026-09-04 — implementation authorized by the operator, using Astra subagents with parent review. Branch `codex/win-now-20260904` starts from fetched main `606e512c`; shared original checkout is preserved.

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

`outlook.season_projections`, `trades.win_now`, `outlook.championship_probabilities` begin false. New title computation stays internal until the independent championship graduation flag is enabled following calibration. No old title odds are exposed. Forecast/lineup/simulation support is explicit: unsupported live weeks, scoring/rules, incomplete contributors, playoffs already underway, stale data or missing schedule return unavailable. No retries silently relax market fairness or partner/budget policy. Preserved historical scenarios are not current recommendations.

## Evidence and delivery

Unit tests cover provider normalization, real lineup counterfactuals after week three, legality/budget/partner checks, probability accounting, caches/job authorization and no Elo feedback. Mobile uses TypeScript, structural checks and manual TestFlight instructions; web uses syntax/structural and rendered browser checks where possible. No Maestro or native simulator. Parent reviews each agent's diff and tests before integrating. Durable schema/API/architecture/config/invariant docs, scope, ledger and calibration limitations are updated with actual results. No production flag, deployment or native build occurs as an incidental tool action.

## Current implementation status

Implementation and parent review are complete on 2026-09-04. Physical TestFlight execution, hosted Python 3.12 CI, forecast calibration and rollout remain **pending**. Parent browser review of the shipped module with synthetic data passed at wide and 390px widths. No merge, deployment or flag enablement is claimed. [EVIDENCE.md](EVIDENCE.md) records completed client checks separately from these open gates.

The beta is narrower than the full proposal: Sleeper in-season leagues before fantasy playoffs; QB/RB/WR/TE and supported flex/scoring/bracket rules; complete published weekly forecasts; no live-game continuation. Best-ball and trade review delays are unsupported; disabled pick trading is enforced. Reserve/taxi assets are excluded from lineup/trade eligibility while retaining baseline roster value. Missing contributors or unsupported rules refuse serving. Dynasty picks have no direct points; post-trade original-team pick-price revaluation, explicit drop workflows, other platforms, real proposal preparation and learned acceptance models are deferred.

## Forecast methodology and limits

The adapter reads Sleeper's experimental weekly stat feed (`sleeper_weekly_experimental`), which carries RotoWire revisions, and retains source company/update fields. It does not buy a provider license or infer redistribution rights from a successful request. ADP-only future-week rows are missing coverage, not zero points. Independently verified byes may produce explicit zero rows.

Fleeced scores the stat vectors with supported league scoring, chooses legal lineups **before** sampled outcomes, and simulates the remaining schedule and supported bracket for all teams. Dynasty rankings affect trade sacrifice/partner attraction only; they never create fantasy-point forecasts. Counterfactuals reuse player/week random worlds and finalists receive an independent-seed check.

Current availability is a limited source input: an injury designation without a week-specific availability estimate is unknown, not a dated return forecast. The simulator withholds results when unknown availability can affect a contributor. Healthy current status is not a model of future injury risk. Independent player/week normal residuals use explicit imported scales or the disclosed heuristic `max(3, 0.6 * abs(mean))`; shared NFL game/team correlation and multiweek injury correlation are **not modeled**. Sampling precision is not forecast calibration.

A snapshot expires at the short serving TTL or the earliest known source game boundary, whichever is earlier. A date-only feed is cut off conservatively at midnight UTC on the game's date; this is not represented as an actual kickoff time. Captured/publication timestamps are retained; fetching a historical URL today is not an as-of historical forecast. Source feeds, model/rule coverage and title calibration must be reviewed before any rollout.

## Boundaries shared by API and clients

`wins` optimizes expected wins over the next three remaining regular-season weeks. API budget is 0–10 percent of the fixed baseline roster value (omitted default 3); fairness is a fraction from 0.75–1 (omitted default 0.90), and the shared policy may impose a tighter floor. Clients submit the same defaults: 3% / 90%. Edited packages allow at most three assets per side; the optimizer also enforces total package limits. Protected IDs belong to the buyer and never bypass legality.

Cards retain server order and display both teams' next matchup, next-three-week wins, remaining/final wins, playoff/bye impacts, dynasty cost, market balance and partner evidence. Public provenance exposes confidence/coverage/intent summaries, not raw boards. Requests and expiry cancel local polling; errors and empty results have manual recovery. Win Now uses separate state and decision endpoints, without changing dynasty sorting, caches or Elo feedback.

## Review corrections and operating limits

Parent review corrected paired confirmation nesting, public scenario/asset contracts, exact package lineup screening, fair candidate coverage across targets, source-wide game cutoffs, source-age expiry and post-evaluation expiry. Completed cards and decisions recheck league, pick, preference and valuation revisions. No-cutoff imports cannot be served. Published consensus seeds and trade-only decisions do not become personal dynasty evidence. TE/RB/WR reception and QB rushing premiums derive from projected base events.

Jobs retain the requesting user’s private input for 7 days; scenarios/decisions retain package evidence for 180 days; forecast/projection batches retain replay evidence for 400 days. No complete partner boards are persisted. Account export/deletion covers the user-owned tables, and short persistence guards prevent worker writes after deletion. The durable queue resumes interrupted jobs on the existing single-worker server. Client cancellation stops local polling, not the server computation.

A local synthetic 12-team, 25-player, 9-slot, 14-week benchmark (1,000 draws, 8 finalists, real paired and independent confirmation runs) took 1.14 seconds baseline plus 46.11 seconds search, screening 11,990 packages and returning one frontier row. This measures local latency only; production load and model accuracy require separate evidence. Bounded search can miss valid packages outside the shortlist.
