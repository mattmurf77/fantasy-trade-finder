# In-season projections and Win Now trades

**Build status (2026-09-04):** Operator-authorized restricted implementation is under review; see [BUILD.md](BUILD.md), [scope.md](scope.md) and [EVIDENCE.md](EVIDENCE.md). This proposal remains the broader design; no rollout or statistical validation is implied.
**Status:** Proposed, not implemented. **Date:** 2026-09-04.

**Recommendation:** Add a season-outcome model and a dedicated **Win Now** trade objective. The requesting manager buys an improvement in this season's results within a dynasty-value budget. The other manager receives a market-plausible package that benefits them according to their own dynasty valuations and team objective.

This is an extension of Fleeced's two-manager trade model. It permits the managers to benefit on different timelines. It does not require the buyer to lose dynasty value; a trade that improves both timelines remains preferable when its season benefit is comparable.

This proposal was checked against freshly fetched `origin/main`, commit `606e512cd87f692eced3b92ccadb4f0192ea3449`. The shared working checkout is older. Source citations below refer to that commit, not local line numbers. No application behavior, data collection, flags, or production data changed during this design work. The accompanying [scope](scope.md) covers the proposed build.

## 1. What users get

On the league page, show current record alongside projected final record, a likely finish range, weekly matchup win probabilities, playoff probability, bye probability, and championship probability. Give all probabilities a common forecast date and model version. Show distributions or ranges rather than implying an expected finish of 3.8 is a guaranteed fourth place.

In Trade Finder, add **Win Now** as an explicit search objective alongside dynasty trade discovery. Within it, support **Championship**, **Make playoffs**, and **Next few weeks** priorities. Default to Championship only after that model passes validation. Do not silently replace a selected objective when data is unavailable.

Keep the existing player targets and protected assets. Add a visible maximum dynasty sacrifice. Each card explains the season benefit, the dynasty cost, and why the other team might want the deal. The trade calculator should use the same evaluator when users modify a package.

Illustrative card, using invented figures rather than an evaluated real trade:

> **You send:** a younger bench receiver and a future second. **You receive:** a productive veteran who starts over your current RB2.
>
> Championship chance: **12% → 17% (+5 percentage points)**. Playoff chance: **68% → 77%**. Expected final wins: **8.1 → 8.7**. Dynasty package value: **−8% by your valuations**.
>
> **Why they might do it:** They have selected Rebuild, and their rankings value the assets they receive 14% above what they give up. Market package ratio: 0.90. Their own championship chance falls from 2% to 1%; that cost is shown alongside their dynasty gain.

“Market package ratio” is the smaller adjusted package value divided by the larger. A ratio of 0.90 is neither a 90% chance of acceptance nor proof of fairness. Product copy should present the actual value difference and a clear explanation. Partner rankings can support a reason to trade; they cannot guarantee agreement.

## 2. Existing foundation and required changes

| Area | What exists on the inspected main commit | Required for this feature |
|---|---|---|
| League simulation | Sleeper standings/schedule ingestion, seeded Monte Carlo, median games, divisions, playoff byes and bracket logic | Finalized-week detection, exact scoring, weekly forecasts, complete rule support, and real postseason progress |
| Trade impact | Both rosters are changed and playoff/seed deltas are calculated against a cached baseline | Both teams' wins/playoff/bye/title deltas, forecast uncertainty, strict asset validation, and trade-effective timing |
| In-season strength | After three completed weeks, `auto` uses historical team scores | Player-sensitive forecasts throughout the season |
| Trade discovery | v2/v3 and gen_v2 favor positive personal dynasty surplus; an experimental fit generator offers looser candidate screening | Generate candidates for season improvement before applying a buyer dynasty-gain gate |
| Championship display | API computes a title estimate; current product policy withholds it for lack of demonstrated forecasting skill | A separately validated model and an explicit update to the display policy |
| Personal rankings | Personal boards, consensus fallback, ranking signals and package valuation machinery | Symmetric confidence handling, partner-intent checks, and objective-aware feedback |
| Caching | Trade and impact caches already exist | Search objective and full input revision identity; immutable forecast snapshots |

The most consequential defect is architectural: `TrailingScoresStrength` reads historical team scores and ignores player ownership. Applying a trade preserves that history. Under the default source after week three, before/after strengths therefore remain identical. This is a source-code inference, not a new runtime test. The current “window” lane is also an age/value orientation, not measured season improvement. Sources: [strength estimator](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/backend/outlook/strength.py#L303), [source selection](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/backend/outlook/strength.py#L392), [trade application](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/backend/outlook/trade_delta.py#L117), [lane classification](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/backend/trade_service.py#L3429).

Reuse the pipeline and counterfactual structure, but extend its forecast contract beyond one static mean and standard deviation per team. Merely adding a provider behind the existing interface would still miss week-specific lineups and playoff matchups. [Current simulator](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/backend/outlook/simulator.py#L111).

## 3. Forecast this season independently of dynasty rankings

Create a swappable player-projection adapter that produces expected stat lines, availability and uncertainty for **every remaining NFL week through the fantasy championship**. Apply each league's actual scoring rules to those stats. An SF/TEP label alone is insufficient: passing touchdowns, bonuses, receptions, premiums and defensive scoring can differ by league.

Personal dynasty rankings price the trade. They must not directly change the estimated probability that an NFL player scores points. Users in the same league should see the same baseline season forecast for a given snapshot, while their dynasty trade valuations may differ.

For future weeks, combine a preseason/current role prior with observed usage and production, shrinking small samples. A near-term weekly projection can anchor the upcoming matchup; later weeks need explicit rest-of-season forecasts, with byes, role uncertainty, injuries and return scenarios. Do not divide a stale preseason season total by games remaining or repeat this week's projection through Week 17. Historical team scores are useful for validation and residual calibration, but cannot replace roster-sensitive forecasts.

For each future week, select the best **legal projected lineup** from available players. Use an assignment optimizer that respects all slot eligibility and lineup locks, then simulate realized points. Never pick starters using the simulated scores after the games: that would project best-ball performance for a managed league. Future pregame availability may inform the lineup; future realized performance may not.

Bench depth contributes through replacement opportunities and injury scenarios, not by adding all bench points to the starting total. Apply roster/IR/taxi constraints and any required drops to both teams. A future draft pick has zero direct current-season points.

Preserve relevant player correlations, such as QB/receiver performances in the same NFL game, and persistent availability across weeks. Estimate residual variability from historical forecasting errors rather than attaching an arbitrary confidence interval to an average. Retain explicit model assumptions for unknown future injuries and roles.

### Projection source recommendation

Keep the source replaceable. First run a bounded source-validation spike for a licensed weekly plus rest-of-season stat feed; if the chosen vendor lacks later-week forecasts, pair its weekly feed with the explicit internal rest-of-season model above.

- **Sleeper league facts:** documented rosters, matchup results and playoff-bracket endpoints fit the existing adapter. The current API documentation states non-commercial use is free and directs commercial users to discuss licensing. Confirm the product's existing arrangement covers the added use; public accessibility alone is not a commercial grant. The reviewed public documentation does not list a projections endpoint. [Sleeper documentation](https://docs.sleeper.com/).
- **Commercial projection candidate:** SportsDataIO documents weekly NFL projections. Its NFL workflow guide explicitly says legacy season-long projections stop being maintained for regular-season performance after Week 1. Validate the exact contracted endpoint, forecast horizon, historical snapshot access and usage rights rather than assuming “season-long” means rest-of-season. No vendor purchase is part of this proposal. [NFL workflow guide](https://sportsdata.io/developers/workflow-guide/nfl).
- **Historical modeling inputs:** nflreadpy documents player statistics, schedules, roster/ID mappings and retrospective expected-points data. Those support fitting and validation; they are not a turnkey forward player-projection model. Observe the dataset-specific licenses. [nflreadpy](https://nflreadpy.nflverse.com/), [load functions](https://nflreadpy.nflverse.com/api/load_functions/).

Capture forecasts at publication time. A historical endpoint that revises old projections cannot establish what the model knew before a game. This was already identified in the repository's [projection-source diagnostic](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/docs/feedback/items/169-outlook-league-summary/calibration-report-2026-08-09.md#L366).

## 4. Simulate standings and the championship correctly

1. Freeze a consistent snapshot of actual records, points, schedule, rosters, scoring and playoff rules. Completed games stay completed. Reconcile commissioner corrections and official standings before publishing.
2. Draw future player/week outcomes and select legal lineups using prospective information. Score each team once per week, reusing that score for all decisions, including median games and doubleheaders when supported.
3. Add future wins/losses/ties to actual records, apply exact qualification and tiebreak rules, and retain the full regular-season finish distribution.
4. Play out the actual fantasy playoff format using projections for those weeks. Support fixed/reseeded brackets and multiweek rounds explicitly. Once playoffs begin, condition on the real bracket and settled winners; eliminated teams have zero championship probability.
5. Retain weekly win probabilities, expected final W/L/T, expected win credit where ties/median games apply, finish distributions, playoff/bye/title probabilities and model uncertainty.

Do not infer that a week is final because someone has scored points. The current ingestion does that, so a live Thursday week can disappear from the remainder. Replace it with explicit game/week finalization. For launch, refresh at settled weekly checkpoints and identify the forecast date. If a week is already underway and current-week conditioning is unsupported, mark that snapshot stale and stop generating fresh season recommendations until reconciliation. A later live model can condition on already-scored points and locked starters. [Current ingestion](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/backend/outlook/league_state.py#L249).

Start with Sleeper and fully tested rule combinations. The other outlook adapters are currently stubs even though those platforms support other app features. Missing future matchups, unsupported scoring/IDP slots, uncertain asset ownership or unsupported playoff formats must return an availability reason, not a confident synthetic probability. Expand supported formats deliberately. [Outlook adapters](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/backend/outlook/league_state.py#L295).

## 5. Generate Win Now candidates before dynasty filtering

Build a dedicated objective in candidate search. Reuse package construction, canonical asset IDs, ownership, protected-player, pick, roster-fit and package-pricing functions. Audit all generator arms and late sweetener/filler passes; no path may reintroduce the buyer-positive-dynasty requirement or bypass the final eligibility checks.

Discover incoming players by their marginal effect on the buyer's weekly starting lineup and championship-week lineup, not simply by age or gross projected points. Construct outgoing packages from assets the buyer can spare that the partner values: picks, prospects, surplus depth and targeted personal-ranking differences. Include balanced player swaps where both teams improve current-season lineup fit.

The experimental fit generator is a candidate-construction reuse point, but still scores dynasty lenses and requires a new season objective. The standard generators cannot simply be filtered afterward because useful dynasty-sacrificing candidates may already have been discarded. [gen_v2 screening](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/backend/trade_gen_v2.py#L550), [fit scoring](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/backend/trade_gen_fit.py#L735).

For every surviving candidate, move assets between both teams and recompute legal weekly lineups from the trade's actual effective week. Simulate the **entire league** again: changing the partner changes schedule strength, seeding and potential playoff opponents.

Use identical simulated worlds for before and after, keyed by snapshot, replicate, player and week. A player retains the same performance draw after switching fantasy teams. Include the same game and injury scenarios. A single sequential random seed is insufficient if changed brackets change draw order. An unchanged scenario must return exactly zero delta.

## 6. Eligibility and ranking: season gains with a defensible other side

Let the buyer send package G and receive R. Let `M` be the common market package valuation and `D_A` / `D_B` each manager's effective dynasty package valuation. Reuse the shared market/package rules, including concentration premiums and replacement/roster costs. Package utilities must use a consistent cardinal scale; do not sum ordinal ranks or describe raw Elo-point changes as economic percentages.

```text
market_ratio = min(M(G), M(R)) / max(M(G), M(R))
buyer_dynasty_gain = D_A(R) - D_A(G)
buyer_dynasty_cost = max(0, -buyer_dynasty_gain)
buyer_package_loss_fraction = buyer_dynasty_cost / max(D_A(G), epsilon)
buyer_budget = fixed valuation-unit amount at the search snapshot
partner_dynasty_gain = D_B(G) - D_B(R)
partner_gain_fraction = partner_dynasty_gain / max(D_B(R), epsilon)
season_delta = outcome_after_trade - outcome_before_trade
```

Use context-adjusted package utilities after required drops; reject unpriceable packages rather than exploiting the epsilon denominator. Also display the market cost separately. A private board should not conceal a large market overpayment.

The hard spending test is `buyer_dynasty_cost <= buyer_budget`. If the UI expresses that budget as a percentage, calculate it from a fixed pre-trade roster/asset valuation captured at search time, not from the candidate package. Keep the baseline and its valuation policy constant across candidates. The package-loss fraction is descriptive overpay information only: adding equal-value filler to both packages must not increase the user's spending allowance. Reject noncontributing filler through the shared package-quality rules.

Apply these gates before ordering:

| Gate | Required behavior |
|---|---|
| Feasible trade | Both teams can legally execute the trade, including pick ownership, deadline, roster space, drops and locked assets |
| Meaningful season gain | A positive, sufficiently reliable improvement in the selected objective and a credible roster/lineup contribution; reject noise-only gains |
| Buyer spending limit | Dynasty sacrifice stays below the displayed budget; protected assets and the user's market-fairness setting remain hard constraints |
| Market plausibility | `market_ratio >= max(user_floor, policy_floor)` using the shared fairness policy; no retry may relax that floor |
| Partner valuation | Incoming package gives a real dynasty benefit on the partner's confidence-adjusted values; market balance cannot compensate for a negative personal result |
| Partner objective | The package is compatible with their stated plan and does not create an unacceptable current-season loss or roster hole |

An explicit rebuilder may trade title probability for future value. An explicit contender requires a plausible competitive benefit as well, or should not appear in the default seller pool. An unknown manager's poor record is evidence of opportunity, not consent to rebuild. With unknown intent, require a conservative competitive outcome and show weaker partner-fit confidence. Do not silently relax these conditions to fill the deck.

Use the partner's actual rankings where authorized and available. Shrink sparse, stale or narrowly covered comparisons toward market values, with provenance and confidence per asset, symmetrically for both managers. Explicit manual rankings need different confidence treatment from unchanged consensus seeds. Missing rankings stay a **market-based estimate**, never “their rankings.” Use tighter eligibility for that fallback and expose board coverage without revealing private raw ranking data.

Fairness and personal valuations both influence partner suitability: fairness determines plausibility, personal surplus determines attraction, and team intent determines whether the sacrifice fits. Keep those components inspectable. A weighted average cannot rescue a failed gate. This aligns with, but does not presume implementation of, the separate personal-ranking / market-fairness proposal (separate design context; its engineering brief is not included in this branch).

Among eligible trades, retain the frontier of season benefit versus dynasty cost. Rank primarily by a conservative estimate of the selected season delta; for materially equivalent improvements prefer lower dynasty cost, then stronger partner benefit and fairness. Do not add wins, probabilities and dynasty units into an unexplained composite score. The budget and materiality tolerances are versioned product/model settings, to be tuned in shadow evaluation.

Show next-matchup win change, expected remaining wins and title change separately. A championship-focused trade may sacrifice an upcoming matchup for playoff upside; label that tradeoff. Offer **Also protect remaining-season wins** as a stricter constraint. No player trade needs to improve every weekly matchup to be useful.

Where the league's actual draft-order rules support it, revalue near-term picks using the original team's post-trade finish distribution. A buyer making itself stronger may make its own traded first less valuable to the seller. Use the original roster ID, not the new pick owner. For max-points-for draft order, simulate that rule separately; do not substitute win/loss standings. Far-future picks retain wider, horizon-appropriate uncertainty.

## 7. Three linked datasets

These are proposed logical datasets; choose physical tables/materialized views during schema design. Player forecasts and league baselines are reusable. Trade rows are personalized and directional.

| Dataset and grain | Essential fields | Purpose |
|---|---|---|
| `player_week_forecasts`: one player × season × week × source/model revision × publication time | Canonical/provider IDs, expected stat vector, residual model/correlation references, availability/return scenarios, opponent/bye, forecast horizon, `published_at`, `ingested_at`, provenance and quality | Scoring-specific weekly lineups; reproducible historical forecasts |
| `league_season_projections`: one league × team × immutable season snapshot | Actual W/L/T/PF, weekly win probabilities, expected final W/L/T, win credit, regular-season finish distribution, playoff/bye/title probabilities, lineup assumptions, uncertainty and input hashes | Standings/championship page and common baseline |
| `win_now_trade_scenarios`: one directed buyer/partner asset exchange × input snapshot × objective/policy | Assets and required drops, baseline/after metrics for both teams, deltas, dynasty/market package values and costs, fairness, partner surplus, confidence/coverage/intent, eligibility reasons, uncertainty, simulation counts and ranking | Searchable Win Now inventory, calculator detail and decision attribution |

All datasets retain source/model/schema versions and immutable snapshot IDs. A scenario references league state, scoring/rules, projection, roster, pick-ownership, market-value, both ranking revisions, intent revisions, effective week, objective and policy version. Store event time and ingestion time separately. Probability fields use 0–1 internally; a displayed percentage-point delta is `100 * (after - before)`. Seed improvement uses a lower number; do not mix its sign with probability improvements.

Keep the scenario asset identity separate from its forecast revision so a recalculation does not erase likes or produce duplicate proposals. The same exchange viewed by the other manager requires its own objective and explanation. Existing mutual-like/match mechanics still require their actual action.

Recommended flow:

```text
League facts + frozen player forecasts
    → common baseline season simulation
    → season-oriented package search
    → legality / spending / fairness / partner checks
    → paired full-league trade simulations
    → versioned Win Now scenario dataset
    → Trade Finder + calculator + league season view
```

## 8. Serving, feedback and compute cost

Extend the existing generation/job API with a versioned objective and sacrifice budget. Add a scenario reference/season-impact object to trade payloads. Extend the league outlook contract additively or version it for distributions and confidence. Keep authentication and ranking-access boundaries intact. Exact routes and migrations belong in the build LLD.

Both the server cache and the mobile pre-generation cache must distinguish objective, budget and complete input revisions. An existing job for the same user/league/format cannot satisfy a different Win Now request. Cancellation, cache hits and stale jobs must preserve the requested objective. Today the deck cache is keyed by user/league/format and the impact cache by league/basis; neither is adequate. [Trade cache](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/backend/server.py#L2906), [impact cache](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/backend/server.py#L1389), [job reuse](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/backend/server.py#L12183).

Preserve the server's season ordering in every client. Existing client-side dynasty-score sorting must not reorder Win Now cards when fairness controls change. Treat the objective as separate from package shape, personal/consensus valuation basis and generator experiment arm. Retain existing dynasty experiments; do not silently convert one into the new mode.

Use a durable background worker with one baseline per league snapshot, reusable player/week worlds and lineup memoization. Screen many packages cheaply by projected lineup gain and partner utility, simulate a smaller shortlist, then confirm finalists with additional independent paired simulations. This limits selection of lucky simulation outliers. Bound per-league work, deduplicate refreshes, stream only validated rows and benchmark before setting simulation counts or promising latency.

Recompute when projections/availability, results, rules, rosters or relevant rankings change. Public league forecasts can be shared; personal scenario caches are viewer-scoped. Revalidate ownership, deadline and material forecast changes when a user opens or prepares a proposal. Preserve the historical impression instead of rewriting its evidence.

When an unsupported live week makes a snapshot stale, also remove its scenarios from current recommendations and disable new Win Now calculator evaluations against it. Cached cards remain available only as clearly dated history. Preparing a current Win Now recommendation requires a fresh, supported recomputation; a cache hit is not an exception. Ordinary dynasty trade discovery remains governed by its existing availability rules.

**Do not train dynasty Elo from Win Now likes, passes or acceptances.** These actions express a season tradeoff. Tag the objective at impression time and preserve it through decisions, matches, proposal outcomes and replay. Route these signals to season intent/offer-quality learning unless the user separately makes an explicit dynasty ranking decision. The current like path treats received assets as dynasty winners, although a bakeoff currently supplies a separate freeze mechanism. The new guarantee must not depend on that experiment remaining enabled. [Ranking signal path](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/backend/server.py#L12899).

Measure proposal and partner response rates, not just buyer likes. Keep acceptance propensity separate from forecasted championship improvement until there is enough outcome data to calibrate it. A hypothetical trade's realized causal championship effect is unobservable; do not label simulation deltas as proven treatment effects.

## 9. Validation and phased delivery

| Phase | Deliverable | Exit evidence |
|---|---|---|
| 1. Forecast foundation | Source/horizon validation, immutable snapshots, player ID/scoring coverage, finalized league state and legal weekly lineups | No hindsight data; known fixtures match platform scoring/standings; supported-format coverage explicit |
| 2. Season projections | Roster-sensitive schedule/bracket simulation and league standings distributions | Held-out forecast accuracy, calibration and rule fixtures; uncertainty and unsupported-state behavior verified |
| 3. Win Now in shadow | New candidate objective, partner gates, dynasty budgets, paired trade evaluation and scenario storage | Sensitivity tests, no invalid packages, no budget/fairness bypass, stable finalists and measured compute cost |
| 4. User beta and championship graduation | Search mode, calculator explanation and validated championship probabilities | Separate title-model validation, reviewed new display policy, outcome attribution, client checks and manual TestFlight pass |

Validation must cover an in-season starter upgrade after week three; bench depth; a bye replacement; injured players; picks with no direct points; mandatory drops; strict ownership; deadline/effective week; partial Thursday games; median/doubleheader scoring; custom scoring; reseeding/multiweek playoffs; clinched/eliminated teams; and both teams' changed lineups. An unchanged trade returns zero. Exactly one champion per simulation implies title probabilities sum to one; finish distributions and playoff-slot totals must reconcile too.

Use rolling historical evaluation grouped by league and season, with forecasts frozen before the games. Compare player errors, weekly win calibration, expected-win errors, finish-interval coverage, and playoff/title Brier scores and reliability against simple baselines. Account for teams within a league sharing one champion. Do not inflate the sample by treating every team/week as independent.

Separate Monte Carlo sampling error from uncertainty in the player model. More simulation draws fix only the former. Use independent finalist runs and projection sensitivity checks; withhold tiny gains whose sign is unstable. Historical frozen projection coverage may require prospective collection before strong championship claims are justified.

The current championship number must not simply be exposed: existing product policy explicitly suppresses it because prior evaluation did not demonstrate skill. Define championship graduation before evaluating the new model, and publish only after it clears that standard. Until then the Championship priority is unavailable; a separately labeled wins/playoff mode may launch only if its own evidence is sufficient. [Current display invariant](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/docs/cross-client-invariants.md#L368).

Proposed independent kill switches: forecast reads, Win Now serving and championship display/optimization. All start off. Follow the repository's structural/unit checks, code-walk evidence and manual TestFlight policy; no simulator or Maestro work. Before implementation, use a fresh branch from current `origin/main` and resolve the physical schemas/contracts in the LLD. The source contract and championship evidence are the principal delivery dependencies; no unsupported calendar estimate is implied here.
