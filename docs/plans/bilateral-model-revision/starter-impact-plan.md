# Starter-impact evidence: season-long outlook and weekly lineup value

2026-09-22. **Research and implementation plan, not an activated projection pipeline.** This follows the owner's authorized [production-learning release](production-learning-release.md). Once deployed, the new bilateral model must continue reporting quantitative starter impact as Unknown until this work qualifies real evidence. Neither deployment nor this plan establishes acceptance uplift or the three-second first-action goal.

## Recommendation

Build a provider-neutral, immutable **weekly raw-stat forecast layer**, initially qualifying Sleeper, and use it to calculate both managers' legal before/after starting lineups. Preserve a separate season-long/remaining-season view. Start in evaluation-only shadow; later use the qualified evidence in outlook and needs scoring, without replacing personal target preferences or dynasty market pricing.

Reuse our existing Win Now forecast importer, point-lineup assignment and immutable snapshot patterns. Do not directly adopt its current injury assumptions, incomplete-bench warnings, fixed-lineup injury simulations or experimental championship probabilities. The [internal audit](starter-impact-internal-audit.md) identifies exact code seams and limitations.

There are four distinct inputs, not one interchangeable ranking:

| Input | What it can establish | What it cannot establish alone |
| --- | --- | --- |
| Dynasty market values and personal tiers | Long-term price, favored targets and assets to move | Expected in-season fantasy points |
| Season-long / ROS redraft rankings | Relative in-season quality and a useful coverage/target prior | Numeric points, bye-week replacement or a probability of acceptance |
| Full-season / ROS stat projections | Expected production over an explicitly defined horizon | Exact weekly starter displacement without a weekly allocation model |
| Weekly stat projections plus schedule and legal rosters | Weekly lineup change, bench replacement and aggregate remaining-season starter gain | Certain health, actual lineup decisions or calibrated title odds |

“Year long” explicitly means retaining full-season evidence **as well as** weekly evidence. After the season begins, trade-created benefit is remaining-season benefit: past points cannot be improved by a new trade. Preserve preseason full-season forecasts, explicitly defined updated full-season estimates, and ROS forecasts as different types. Never silently substitute one for another.

## 1. Source decision and remaining research

### First candidate: Sleeper

Bounded public probes on September 22 found actual projected stat vectors for 406 player rows in week 3 and 442 in week 17; most other returned rows were placeholders. This establishes sampled future-week availability, **not complete horizon or league-roster coverage**. The season response has no verified ROS/full-season interpretation. Historical week-1 data had postgame updates and cannot certify what a pregame model knew. See the [probe report, primary URLs and retained evidence](starter-impact-sleeper-research.md).

Sleeper's projection endpoints are observable but undocumented in its [official API reference](https://docs.sleeper.com/). Existing owner permission to pull Sleeper data is acknowledged; record whether it covers projection provenance, storage and commercial derivative use. Returned rows identify RotoWire, so this is not necessarily an independent forecast from a direct RotoWire feed. Do not expand this approval to other vendors or purchase a feed without authority.

Before model use, verify:

1. Every included future fantasy week, relevant offensive/defensive position and deep-roster player—not only the next week or traded assets.
2. Whether weekly means already account for missed-game risk; what omitted stat fields mean; injury/return-to-play semantics; per-row update and availability times.
3. The season endpoint's exact horizon and whether completed games are included. Until resolved, retain it as ambiguous research data, not a qualified year-long or ROS number.
4. A verified current-season NFL schedule and exact kickoffs. Missing forecast/opponent is not proof of a bye. Fantasy-team matchup endpoints are not the NFL schedule.

### Alternative sources and fallback roles

- **RotoWire:** documented weekly, full-season and [remaining-season stat feeds](https://rotowire.readme.io/reference/get_football-nfl-restofseasonprojections-php). Best next contract/sample inquiry if Sleeper season semantics or coverage remain insufficient. Verify IR/returning players, future weeks, conditionality, retention and commercial automated-use rights.
- **SportsDataIO:** documented weekly/IDP workflow; its legacy season feed freezes at season start and is **not ROS**. Its final historical archive is not an as-of revision archive. Candidate for weekly coverage, not an assumed solution to both horizons. [Official workflow](https://sportsdata.io/developers/workflow-guide/nfl), [history limitations](https://sportsdata.io/help/historical-data-integration-guide).
- **FantasyPros:** advertises weekly/preseason/ROS projections and ECR, but requires a commercial agreement and resolution of its direct-competition restriction for Fleeced. Rank-only use remains ordinal. [API offering](https://www.fantasypros.com/api-data/), [access policy](https://support.fantasypros.com/hc/en-us/articles/49749297704475-How-do-I-request-access-to-the-FantasyPros-API).
- **nflverse / ffverse / DynastyProcess:** reuse ID crosswalks, schedule/history and rank research infrastructure where rights permit. These are not automatically licensed forward projections. A rank-to-points model would be a separately calibrated estimated prior, never observed provider evidence.

The [alternative-source report](starter-impact-alternative-sources.md) contains detailed primary documentation and source-specific questions. Qualify coverage, semantics, accuracy and rights before cost comparison. Do not assume that blending correlated providers improves predictions. No new subscription, license, procurement contact or production ingestion was performed for this plan.

## 2. The calculation: both managers, every relevant week

For each manager `m`, week `w`, and captured information set:

`delta[m,w] = best_legal_expected_lineup(after_roster[m], w) - best_legal_expected_lineup(before_roster[m], w)`

Use the same forecasts, scoring, information cutoff and lineup decision policy for both states. Each player may occupy at most one compatible slot. Include FLEX/Superflex competition, existing bench replacements, reserve/taxi rules, trade processing/locks, and explicit cuts or activations. Do not invent free waiver replacements or count an incoming bench player while ignoring the valuable player that must be cut.

**Bye example:** before a trade, a manager's usual RB is on a verified bye and their eligible backup projects for 9 points. An incoming RB projects for 13. That week's gain is 4, not 13. If the outgoing player filled FLEX, reoptimize FLEX too; the gain may be smaller or negative. Calculate the partner independently using their actual roster.

Keep numerical projected zero, confirmed bye/out, missing projection, unknown availability, unsupported stat category and ambiguous player ID distinct. A missing potentially useful bench player means the optimum is not known unless a defensible bound proves irrelevance. Do not simply exclude them because known players fill all slots.

Availability needs a versioned contract: conditional-on-playing forecasts require a justified participation model applied once; already risk-adjusted forecasts must not be discounted again. No injury label does not prove 100% participation. Pre-lock known absences may permit bench substitution; midgame injuries generally do not. Never select a lineup using subsequently realized scores. The first implementation may qualify known-state expected lineups and return uncertainty for unresolved future-health scenarios; it must not claim complete injury-risk modeling.

### Season and near-term views without double counting

Retain a vector: next eligible week, next three eligible weeks, remaining fantasy regular season, fantasy playoff weeks, and explicitly defined season-long evidence. Eligible weeks are a shared fixed fantasy-calendar horizon after trade effectiveness and applicable locks; never skip a player's bye, injury or missing row to choose a different horizon. Use the league's actual scoring weeks—not a universal 17-game divisor or assumed week-18 championship.

- ROS starter gain is the sum of weekly deltas across a fixed included-week set. Mean weekly gain divides by that same set's size. Missing weeks remain missing; do not shrink the denominator and call the result complete.
- Weekly byes already reduce availability. Do not subtract another bye from the ROS total. Player season-total ranks cannot establish simultaneous byes or bench replacement.
- Completed production is unchanged history. Show it separately if presenting full-season actual-plus-future totals; never count it as a trade gain.
- A direct vendor ROS forecast can be a separate comparison/prior, but do not add it to weekly totals. Reconcile mismatches, games included and freshness before adopting an allocation scheme.
- Playoff-week lineup strength is conditional on reaching that stage. Title probability is separate work requiring qualified full-league schedule, standings, correlations and calibration.

Preserve user-selected outlook precedence. All-in and contending may trade dynasty value for defensible season/starter improvement within existing fairness rules; rebuild/tank need not gain current points. Preserve favored young players, picks and the recorded RB preferences. A single bye must not automatically authorize a substantial dynasty overpay. Picks have future utility and no fabricated current-season points. Forecasts do not overwrite user-set tiers or turn unknown partner preferences into known intent.

## 3. League scoring and evidence contract

Score raw expected event counts under the league's actual rules. PPR/TEP use the player's primary position and eligible scoring events; SF changes slots, not QB projected points. League size and start/bench requirements affect replacement value through actual rosters and slots, not a universal multiplier.

Create a scoring-support matrix for each provider/schema. An absent event is zero only under an explicit omission-means-zero contract. For yardage thresholds and nonlinear bonuses, use expected bonus-event counts or a validated outcome distribution; applying a threshold to mean yardage is not an expected bonus. Unsupported IDP/K/DST or custom categories remain unsupported. Current Win Now exclusions cannot silently become “exact scoring.”

Freeze one shared, provider-neutral context with:

- Provider and model/schema versions; original source IDs, deterministic crosswalk/version, raw-body/content hashes and allowed retention scope.
- Row-level source revision times; our fetched/available/captured times; included season/weeks, forecast type, cutoff, expiry and conditionality. A hash or latest row timestamp alone proves neither freshness nor historical availability.
- Raw/effective scoring, unsupported categories, slot/eligibility definitions, schedule/kickoff version, roster ownership/capacity/reserve/taxi and explicit cut/activation assumptions.
- Full relevant player-week coverage, unknown reasons and qualified/estimated/unsupported states for each manager before and after.

Each offer references that immutable context plus both managers' before/after lineups, weekly deltas, horizon aggregates and evaluator versions. Store the full grid once, not on every card. Public cards may explain the resulting benefit without revealing the partner's private rankings or internal Elo.

When manager A likes Monday and B views Thursday, retain Monday's original terms/evidence. Store Thursday's fresh evaluation separately; do not rewrite history, extend interest expiry or infer continued interest after withdrawal. Projection/roster/scoring changes need explicit invalidation across provider updates and processes, beyond today's personal-input job epochs. Required proof must be durable before a card becomes visible.

## 4. Delivery and performance design

No provider request belongs inside Find a Trade's tap-to-first-card path or its candidate loop. Proposed cadence, subject to actual source refresh/rights: nightly refresh all remaining-week and season/ROS contexts; more frequent upcoming-week refresh after provider updates and injury/lineup news. Measure meaningful content changes before invalidating all prepared work. Keep rate limits, bounded retries, single-flight refresh, source-specific TTLs and last-good expiry explicit.

Precompute league-scored player-week grids and each manager's baseline weekly lineups on refresh/app warmup. Candidate evaluation reuses immutable baseline context and caches exact roster/slot/cut/scoring/horizon/version keys, scoped to the exact forecast-context content identity rather than model/schema version alone; reoptimize only affected teams. Keep full-league Monte Carlo away from exhaustive candidate generation. First use deterministic weekly expected points; test any optimization for exact candidate/output parity.

Do not reduce candidate or offer counts to meet the three-second target. Measure actual client tap-to-action separately from server first durable batch and full search, including cold/warm/stale-cache/concurrent workloads and errors. Target first visible actionable card within 3 seconds; initial 20–30 durable cards where available, then continued results. This is a target requiring measurement, not a result of this plan.

For missing/stale source data, keep the current dynasty/personal path available with starter impact Unknown and no invented point claim. Record fallback/error/empty outcomes. A freshness failure must not silently reuse stale “known” impact; nor should a provider outage necessarily disable all valid trades.

## 5. Implementation work packages and gates

| Phase / owner lane | Main seams and deliverables | Exit condition |
| --- | --- | --- |
| A — source/data | Extend `season_forecasts` contract; prospective bounded capture; schedule and ID validation; provider rights/semantics register | Both full-season/ROS semantics and weekly coverage explicitly classified; every supported scoring field and missing state documented; raw/as-of evidence retained |
| B — pure impact | Extract/reuse point assignment from `season_simulator`; join `trade_roster` legality/cuts; versioned weekly bilateral evaluator | Exact fixture oracles below pass; both sides' points/coverage emitted; no experimental title odds or hidden roster assumptions |
| C — snapshot/serving | Reuse `win_now_store` patterns; extend detached owner context/proof; shared immutable references, cache/invalidation and publication fences | Replayable before/after evidence, no private board leak; provider updates invalidate new generation; historical likes untouched; no network in candidate loop |
| D — independent evaluation | Shadow grader extension and prospective holdouts in `backend/eval`; source/format/outlook segments | Known/Unknown coverage plus accuracy and impact diagnostics reported; no construction self-grading, historical lookahead or acceptance claims from generated counts |
| E — controlled integration | Separately version/gate use in generator needs/outlook score versus presentation evaluator | Predeclared quality/coverage/latency margins and reviewed shadow results; reversible rollout, exact model/context attribution and readback |

Write scope/specs for each behavioral change before implementation. The present request authorizes this plan, not those runtime phases. Reuse infrastructure after addressing the [audit gaps](starter-impact-internal-audit.md); a new giant parallel forecast stack is unnecessary.

Required deterministic tests: no-op trade, side reversal, positive bye replacement, simultaneous byes, outgoing FLEX displacement, SF assignment, duplicate IDs, negative points, missing useful bench, threshold bonus, conditionality/double-discount, IR return with mandatory cut, both-side capacity, mixed horizons, completed-game locks, stale input publication and failed evidence persistence. Include 8/16-team and start-8/start-12 contexts, contender/rebuilder pairings and unsupported scoring. An Unknown result can be correct; a fake precise score cannot.

## 6. Proving improvement and learning from the authorized release

Use the existing [six-dimensional scorecard](../model-evaluation-framework/scorecard-spec.md). Improve outlook and needs evidence while continuing to grade fairness, personal-rank direction, meaningfulness and stud compensation independently for both managers' give/receive sides. Starter points are not the acceptance objective by themselves.

Predeclare development/validation/test splits by future time and connected league/manager groups. Archive pregame forecasts prospectively; revised historical endpoints cannot be used as if known at offer time. Evaluate player-point error/calibration, coverage/staleness, expected-lineup policy performance and modeled before/after utility; the counterfactual benefit of a rejected trade is not directly observed. Report rank-only and unknown populations separately. Freeze margins before examining holdouts; do not repeatedly tune against the owner's fixed examples.

For production learning once the authorized model is live, distinguish generation, eligibility, durable serve, qualified view, effective like/pass/undo, overlapping mutual interest, and exact confirmed platform completion. Keep original and later valuations, expired/withdrawn interest and missing observation windows. Existing transaction overlap matching is not sufficient for exact offer-attributed completion; missing follow-up is not a failure. Audit these links before publishing rates, and report observed subsets if complete framework denominators are unavailable.

All-traffic activation is not a randomized comparison. Use historical results descriptively with confounders disclosed; choose any future experiment's assignment/cohort and minimum evidence requirements before exposure. Segment by outlook pairing, board coverage, format, meaningful-value tier, shape, bye/injury state and source confidence; retain empty/error requests and cluster repeated cards/manager episodes. No calendar date or generated-offer count alone proves improvement.

The release receipt owns exact deployed SHA/config/timestamps. This plan establishes the next evidence work, not a monitoring automation, a new TestFlight release, a purchased data feed or an already integrated projection model.
