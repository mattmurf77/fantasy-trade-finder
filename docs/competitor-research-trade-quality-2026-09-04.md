# Competitor research and trade-quality recommendations

Research date: 2026-09-04. Product: Fleeced: Dynasty Trade Finder.

**Recommendation:** make a trade eligible only after evaluating the complete resulting roster for each manager. Then rank eligible trades by the benefit to the less-benefited manager, evaluated against that manager's outlook and preferences. Use observed proposals and responses to improve acceptance estimates as the dataset grows.

This addresses three different questions: does the manager want the assets, does the resulting roster suit their plan, and can the deal realistically get accepted? A value-balanced package does not answer all three.

## Evidence and scope

Competitor capabilities below come from public product pages, documentation, and an explicitly identified developer announcement. They are feature claims, not independently measured acceptance results. I did not run identical private leagues through paid competitors. I found no comparable, independently validated acceptance-rate benchmark in the reviewed sources.

Code findings use main commit `606e512cd87f692eced3b92ccadb4f0192ea3449`, dated 2026-09-03. `git ls-remote origin refs/heads/main` confirmed that revision on 2026-09-04. The shared checkout is older, so the review read the main revision directly with `git show`. Runtime database overrides and production flags were not queried in this research; code defaults are not evidence of deployment settings.

The existing [balance engineering brief](../TRADE_ENGINE_BALANCE_ENGINEERING_BRIEF.md) is a proposed change, not shipped behavior. It supplies useful prior internal evidence and complements this report. Its reported 598 impression-linked like/pass decisions came from only five users; those figures were not independently re-queried here. They support exploratory analysis, not a declaration that an engine arm wins.

## What competitors do and what to adopt

| Competitor | Documented approach | Implication for Fleeced |
|---|---|---|
| **FantasyPros My Playbook** | Matches potential partners using their team needs and the user's roster surplus. | Generate candidates from complementary roster needs, including when the partner has no personal rankings. Public documentation does not establish comprehensive protection against new weaknesses. [Trade Help documentation](https://support.fantasypros.com/hc/en-us/articles/26338614597915-What-Tools-Do-You-Have-for-Trade-Help) |
| **Dynasty Daddy** | Lets managers select assets to move, choose a valuation market, filter positions and tier changes, and include/exclude partners. Proposal cards show the partner's tier and roster needs. | Treat the manager's willingness to sell and preferred trade shape as strong inputs. Show the other team's reason to participate. The help page does not disclose a complete post-trade safety model. [Trade Finder documentation](https://dynasty-daddy.com/help/trade-finder), read in the live browser because the text fetch omitted its content. |
| **DynastyCalc** | The developer describes separate Smart Trades for starter improvements and Strategy Trades for differing competitive windows, with strategy overrides. The current calculator supports contender/rebuilder valuation modes and actual free-agent inputs. | Separate immediate lineup benefit from future-building benefit; use real replacement options. Smart/Strategy descriptions are from a developer announcement, not an independent current-UI test. [Developer announcement](https://www.reddit.com/r/DynastyFF/comments/1skl5ao/dynastycalc_updated_its_trade_finder_to_factor_in/), [current calculator](https://www.dynastycalc.com/) |
| **AdvantEdgeHQ** | Describes FLEX-aware need assessment and rechecking both resulting rosters so a surplus cannot be spent twice or leave an unfilled startable slot. | This is the closest documented approach to goal 3. Adopt a complete-package, post-trade check for both teams. The public explanation does not establish the accuracy of its projections or injury modeling. [Methodology](https://advantedgehq.com/trade-finder) |
| **FantasyCalc** | Learns market prices from completed trades, removes outliers, adjusts for league settings, weights recent trades, and accounts for roster spots in uneven deals. | Use empirical trade prices as a plausibility reference. Price actual cuts and replacements locally. Completed trades alone cannot establish the probability that an arbitrary offer will be accepted. [FAQ](https://fantasycalc.com/frequently-asked-questions) |
| **KeepTradeCut** | Uses crowd valuations and package adjustments for star concentration and roster spots; explicitly frames its calculator as a contextual gut check. | Preserve a market check and consolidation treatment. Personal preferences and roster impact need their own evaluation. [Calculator](https://keeptradecut.com/trade-calculator), [FAQ](https://keeptradecut.com/frequently-asked-questions) |
| **Dynasty Nerds / DynastyGM** | Advertises league-synced trade discovery, positional league analysis, custom values, expert valuations, and balancing suggestions. | Personal rankings alone are not an exclusive differentiator. Fleeced should emphasize learning each manager's preferences and showing measurable benefits to both resulting teams. [Product description](https://www.dynastynerds.com/dynasty-tools/trade-calculator/) |
| **Dynasty Dealer** | Generates balanced proposals from synced rosters using a market model built from real trades and community votes; advises adjusting for manager needs. | Use market plausibility to narrow the search, then require a manager-specific reason for the exchange. Its published fairness rationale is not an acceptance guarantee. [Trade Assistant](https://www.dynastydealer.com/trade-assistant) |

A useful historical engineering reference is IBM/ESPN's trade-recommendation research: it models the cost of losing a player in the context of roster depth and slot requirements, pairs complementary teams, and evaluates trade quality with experts. Its reported 97.3% high-quality figure is an expert assessment from the 2021 deployment, not an offer acceptance rate or a benchmark for today's competitors. The reusable lesson is contextual removal cost and structured error review. [Research paper](https://arxiv.org/abs/2111.02859)

## Where our implementation falls short

Fleeced already has meaningful foundations: personal boards, mutual-surplus gates, marginal replacement values, need scoring, outlook inference, package hygiene, and multiple experiment arms. Improving their shared decision contract should take priority over adding another loosely connected multiplier.

| Verified finding on main | Why it matters | Code evidence |
|---|---|---|
| `_feasible_after` checks position body counts against fixed QB/RB/WR/TE requirements. It excludes FLEX and does not receive the real slot template or player availability. | A roster can satisfy the predicate while lacking a required WR3, usable RB, or FLEX option. It can also reject a legal superflex arrangement by treating a second QB as mandatory. | [trade_optimizer.py:159](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/backend/trade_optimizer.py#L159) |
| `replacement_levels` uses the pre-trade roster; `need_fit_score` uses pre-trade positional profiles. | Several outgoing players can consume the same apparent surplus. Static per-player contributions miss package interactions. | [trade_service.py:3072](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/backend/trade_service.py#L3072), [replacement_levels:3172](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/backend/trade_service.py#L3172) |
| The newer need gate has any-received-asset and partner-need rescue logic. The positional net cap also has startable-depth relief. These are useful but incomplete checks. | An incoming upgrade can pass without proving that all other positions remain healthy. Startable-depth relief is conditional on an over-cap move; it is not a universal roster invariant. | [trade_service.py:2425](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/backend/trade_service.py#L2425), [need_gate_ok:2530](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/backend/trade_service.py#L2530) |
| Targeted jobs skip the discovery need gate; rebuilding or unresolved outlooks also pass that gate. | Preference-based exceptions must not bypass a separate structural roster-protection check. | [trade_service.py:6185](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/backend/trade_service.py#L6185) |
| The calculator's `_starter_impact` already compares both rosters before and after using resolved league slots. It uses consensus dynasty values. | Reuse its roster/slot plumbing and explanation contract, but do not label its value deltas as projected fantasy points. It is not the generation-wide safety check. | [server.py:1172](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/backend/server.py#L1172) |
| The `fit` arm's dual scores derive from personal/consensus package surpluses; its ranking uses their sum. `gen_v2` ranks joint gain times an acceptance prior, with symmetry as a tie-break. | Neither a “fit” label nor a positive combined score proves both full rosters improve. The acceptance prior is manager-level, not a trade-specific calibrated probability. | [trade_gen_fit.py:735](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/backend/trade_gen_fit.py#L735), [trade_gen_v2.py:287](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/backend/trade_gen_v2.py#L287), [joint ranking:819](https://github.com/mattmurf77/fantasy-trade-finder/blob/606e512cd87f692eced3b92ccadb4f0192ea3449/backend/trade_gen_v2.py#L819) |

I exercised the extracted, unmodified feasibility predicate without importing the application or accessing its database:

| Synthetic case | Predicate result | Interpretation |
|---|---|---|
| Start-three-WR league; a trade reduces WR count from three to two | Pass | Real league slot requirements cannot be enforced by this signature. |
| Three rostered RBs, only one usable; trade away the usable RB | Pass | The predicate cannot distinguish starter quality, injury, or availability. |
| An existing one-RB deficit; unrelated one-for-one WR upgrade | Fail | Existing deficits can suppress trades even when the trade does not worsen them. |

These are isolated predicate checks, not claims that the complete production pipeline serves these exact offers. Other gates can reject a candidate for other reasons.

## Priority 1: protect both complete rosters

Create one reusable evaluator that receives the actual league settings, both rosters, the whole trade package, and a dated player/valuation snapshot. It returns before/after lineup assignments, positional health, replacement depth, roster-space cost, and uncertainty for both sides.

1. **Resolve the real lineup.** Account for dedicated slots, FLEX, superflex, eligibility, active/IR/taxi restrictions, and league-specific scoring. Separate legal eligibility from acceptable competitive strength: a non-QB can legally fill superflex without being a good QB replacement.
2. **Apply the complete package and necessary cuts.** Remove all outgoing assets together, add all incoming assets, then choose feasible cuts under the roster limit. Picks do not fill starting slots. If an open spot adds value, use a realistic available replacement and acquisition assumption.
3. **Reassign the lineup and backups.** A player can fill only one slot. Shared FLEX coverage must not be counted independently at RB and WR. The existing slot resolver is useful; the current lineup filler is greedy, so verify its supported slot combinations and use maximum-weight assignment where overlapping eligibility requires it.
4. **Check every position and shared-slot requirement.** For an initially legal roster, require a legal resulting lineup. Add quality floors and usable backup coverage so nominal player counts cannot mask a new weakness. If a roster starts deficient, preserve or improve each existing deficit and create none elsewhere; return a repair-oriented result rather than requiring one trade to solve every existing problem.
5. **Check plausible adverse scenarios.** Evaluate relevant byes and a small set of injury/availability scenarios, starting with the next few weeks and the playoff window. For missing projections or status, report uncertainty and avoid a confident safety label.

A proposed quality invariant, with thresholds to calibrate:

```text
deficit(team, position_or_slot_group)
    = max(0, required_health - observed_health)

For BOTH teams and EACH position / shared-slot requirement:
    deficit_after <= deficit_before + measurement_tolerance
```

This permits spending genuine depth while a position remains healthy. It does not require every position's total value to increase. A small WR downgrade can fund a worthwhile RB upgrade if WR remains adequately covered; a collapse from a dependable WR starter to an unusable replacement cannot be hidden by the RB gain.

**Example, hypothetical weekly projections:** an offer improves RB2 from 10 to 15 points but reduces WR3 from 14 to 5. Total starter output falls by four points and WR becomes a weakness. Reject it for the default recommendations. If a different offer leaves WR3 at 13, preserves backup coverage, and gives the partner a valid benefit, it is a much stronger candidate.

Apply this evaluator to every generated recommendation after sweeteners, package edits, fallback generation, and injections. Revalidate stale offers before suggesting submission. User-authored proposals can display the same findings without being mislabeled as model-endorsed safe recommendations.

## Priority 2: score benefit against each manager's outlook

Use separate time horizons for the two managers, with explicit user intent taking precedence over inference. Give inferred outlooks a confidence and timestamp; refresh after meaningful roster, injury, draft, or standings changes. A roster's average age alone is insufficient.

| Outlook | Reward | Protect |
|---|---|---|
| Contender | Marginal projected starter points now, useful near-term depth, eventually calibrated playoff/championship improvement | Starting coverage, near-term availability, adequate injury insurance |
| Rebuilder | Future productive value, suitably timed picks, durable assets and optionality | A viable roster and excessive concentration in one position or draft class |
| Retool / uncertain | Balanced immediate and future benefit; a few distinct feasible directions | Expensive irreversible bets based on a low-confidence outlook estimate |

Keep current-season projections, future asset value, and personal preferences distinguishable. Dynasty value is not a current-season projection, and age alone is not future production. Normalize component scales and fit or validate weights to avoid counting the same underlying value multiple times.

For each team calculate the change in utility between its whole pre-trade and post-trade roster. After eligibility, the first experiment should rank by the **smaller normalized utility gain**, then total gain and package simplicity. This builds on the existing harmonic mutual-surplus concept while extending benefit beyond package prices.

Contender/rebuilder trades can work even when the rebuilder gives up current points. The default still protects against creating new severe positional holes. A future product option for deliberately accepting a new weakness should be explicit and separate from these protected recommendations; simply choosing “rebuilder” should not silently opt the user into that sacrifice.

Candidate search must also change. Build candidate pools from a union of personal-value differences, safely expendable surplus, partner needs, time-horizon exchanges, and expressed targets. Reranking cannot recover a useful player excluded from the pool. Keep a modest quota from each source, then evaluate complete packages. Do not multiply the same need bonus through several stages.

## Priority 3: learn what both managers will actually consider

Preserve personal ranking signals, with symmetric confidence and provenance for both managers. The existing balance brief proposes this well. A missing opponent board should produce an estimated fit, not a claim that the opponent personally values the offer positively.

Collect and use distinct feedback:

- **Player preference:** “I value the outgoing player more.” Update personal valuation when justified.
- **Roster objection:** “This leaves me short at RB.” Update roster constraints or fit calibration, not the player's global ranking.
- **Strategy objection:** “I am rebuilding.” Update outlook/preference signals.
- **Package objection:** “Too many pieces,” “I need an RB back,” or “I want to retain this pick.” Restrict package shape or identify a useful counteroffer.
- **Partner response:** viewed, declined, countered, accepted, expired, or not seen. Distinguish lack of exposure from rejection.

Use actual offer-and-response data to estimate `P(partner accepts | offer, context, exposure)`. Predict viewer willingness to propose separately. Initially retain a strongly shrunk prior and qualitative confidence; five active users cannot support reliable per-manager, per-player acceptance probabilities. Completed public trades can anchor plausible prices and shapes, but contain no denominator of rejected or unseen offers.

When sufficient data exists, evaluate a small calibrated acceptance model using features such as both roster gains, personal surplus, outgoing starter loss, timeline compatibility, preferences, package size, and recent responses. An LLM can explain computed facts; it should not invent the utility score or override a roster failure.

For a good core exchange, return two or three materially different, eligible alternatives: immediate production, younger asset plus pick, or a simpler package. Each alternative must clear both teams' checks. Prefer the smallest acceptable package and add a sweetener only if it produces a meaningful improvement. Avoid filling the deck with repeated offers for the same outgoing favorite.

## Show users the reason to like a trade

Each card should explain four facts drawn from the same calculation used to rank it:

- **Your benefit:** which starter, future asset, or depth requirement improves.
- **Their benefit:** why the partner can use the outgoing assets, including the confidence of that inference.
- **What it costs:** the replacement for outgoing starters and any lost backup coverage.
- **Roster check:** positions remain covered, or a specific uncertainty prevents that conclusion.

Example: “Your RB2 improves while your three starting WRs remain covered. Their incoming WR becomes a starter; their remaining RBs still cover both RB slots. Their preference for this package is estimated from roster fit.” Use points only when sourced from projections; otherwise identify the result as a value estimate.

## Implementation order and evaluation

Treat the improvements as a shared policy/evaluation layer around the existing generators. Preserve the current experiment arms and their identities; do not infer that the `fit` module is active just because it exists. Avoid fragmenting the small sample across several new arm combinations at once.

| Sequence | Concrete deliverable | Evidence needed before promotion |
|---|---|---|
| **1. Roster evaluation in shadow** | Shared full-roster evaluator, actual slots, explicit cut/replacement logic, before/after feature logging | Synthetic boundary cases; replay of frozen historical rosters; human review of disagreements; latency and candidate-loss measurement |
| **2. Roster protection in recommendations** | Final non-bypassable eligibility check across generation paths | Zero known new lineup holes in the supported fixtures; reduced new-deficiency incidence on reviewed offers; acceptable supply and latency |
| **3. Outlook-aware utility ranking** | Per-side normalized utility deltas and protected trade alternatives | Blinded manager preference comparisons; gains for both outlook pairings; improvement not driven by one manager or one league |
| **4. Response learning** | Attributed proposal/response outcomes and calibrated acceptance ranking | Enough exposed offers and responses, calibration tests, later-time and held-out-manager evaluation |

Use the existing evaluation infrastructure and the balance brief's frozen-state, canonical-trade, and delayed-response attribution design. Log actual impression, roster/settings version, both board versions, scoring policy, threshold, experiment arm, both utility deltas, per-position deficits, and the reasons for eligibility failures. Store the exact offer shown and distinguish it from an edited or countered offer that later closes.

**Primary product outcome:** accepted suggested trades per active manager, accompanied by acceptance per delivered proposal. **Earlier indicators:** manager-rated willingness to send, proposal rate, counteroffer rate, and mutual interest conditional on both people seeing the offer. **Guardrails:** new-deficiency rate, strategic mismatch, repetitive packages, appropriate trade supply, and response latency. Like rate remains diagnostic because one-sided offers can attract likes.

Evaluate independently at manager/league level, use time splits, and account for repeated observations from the same people. Predefine a useful effect size and collect sufficient independent participation; do not use hundreds of cards from five people as hundreds of independent users. For offline analysis, unshown candidates have unknown preference outcomes. Historical replay can verify constraints and coverage, but does not establish their counterfactual acceptance rate.

Required regression scenarios include three-WR and multiple-FLEX leagues; legal non-QB superflex fills; trading the last usable RB while injured bodies remain; two-for-one deals that exhaust depth; forced valuable cuts; picks-only rebuild exchanges; already-deficient rosters; missing opponent preferences; stale injury/bye data; sweeteners; targeted searches; fallback/injected cards; and an otherwise high-total-gain trade that harms one team.

**First build recommendation:** the shared post-trade roster evaluator and protection policy. It directly targets goal 3, supplies the missing inputs for goal 2, and gives goal 1 a defensible basis for two-sided recommendations. This research changed no application code or production settings.
