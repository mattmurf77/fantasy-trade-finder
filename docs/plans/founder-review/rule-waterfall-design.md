# Founders' review, use case 2: the decline waterfall

**Date:** 2026-11-11 · **Status:** built and **wired** (routes, run, app page; see
[§11 As built](#11-as-built-the-wiring-pass) for what differs from §6-§8) · **Branch:** `feat/founder-rule-waterfall`, cut from `release/2026-11-12-train` @
`e8fd4480` · **Scope block:** [rule-waterfall-scope.md](rule-waterfall-scope.md)

The operator's ask: a table of every yes/no rule, as a decline waterfall, showing how many
trades the engine started with and how many passed every decision, with a free-text comment or
question per rule, and a plain name and description for each rule.

Read with [ADR-030](../../adr/adr-030-rules-first-deck.md) (rules-first construction),
[fast-deck v2 design](../realtime-trade-engine/fast-deck-v2-design.md) and
[card-logic assessment §1](../card-logic-grades/assessment.md). Every number below was measured
offline on this laptop against the committed 12-team fixture league and synthetic leagues. No
production data, network or user ids.

- [1. What the founder sees](#1-what-the-founder-sees)
- [2. The rule catalog](#2-the-rule-catalog)
- [3. How the counts are obtained](#3-how-the-counts-are-obtained)
- [4. Example waterfalls with the sum check](#4-example-waterfalls-with-the-sum-check)
- [5. Notes](#5-notes)
- [6. The page](#6-the-page)
- [7. Routes to wire](#7-routes-to-wire)
- [8. Cost and run model](#8-cost-and-run-model)
- [9. Rules flagged for the founder](#9-rules-flagged-for-the-founder)
- [10. What is not measured, and open questions](#10-what-is-not-measured-and-open-questions)
- [11. As built: the wiring pass](#11-as-built-the-wiring-pass)

## 1. What the founder sees

Header line (one line, on the page as written):

> **Started with 45,056 candidate trades → 215 served.** "Started with" = every 1-for-1,
> 2-for-1 and 1-for-2 trade between you and each other team that can be built from the up-to-16
> players per side the search considers.

The 12-team fixture league (revision 2, viewer Contending, fairness 75%), rows with a removal
(the page shows all rows; zero rows collapse under "Rules that removed nothing"):

| Rule | What it checks | Removed | Remaining |
|---|---|---:|---:|
| **Not worth adding a piece** | A 2-for-1 or 1-for-2 is only tried when its core 1-for-1 passed, or failed for a reason an extra piece could fix (price, fairness, or one side not gaining enough). If the core 1-for-1 failed anything else, every larger version of it is skipped untested. | 23 | 45,033 |
| **Fair by market value** | By consensus market value, the cheaper side must be worth at least 65% of the dearer side, or your fairness setting if it is stricter. This is the fairness check both managers rely on. | 41,224 | 3,809 |
| **Good for you** | Your fit score for the trade must be above 0.35, on a 0-to-1 scale where 0.5 is neutral. The score mixes how you rank the players (45%), market value (35%) and your team plan (20%). | 326 | 3,483 |
| **Good for them** | The other manager's fit score must also be above 0.35, judged from their rankings (or market value when they have none), market value and their team plan. | 310 | 3,173 |
| **Something you want** | The trade must match something you showed you want: a player you rank clearly above market coming in (or below market going out), a player or position you asked for, a player on your trade block, a stated team plan it helps, or, if you have not ranked players yet, a small market or plan gain. | 581 | 2,592 |
| **Not against their rankings** | If either manager's own rankings say the trade clearly moves them the wrong way (net lean below -0.15) and it does little for their team plan (plan gain under 0.20), it is dropped. | 46 | 2,546 |
| **Tanking teams skip older RBs** | A team marked Tanking does not take on a running back unless it ranks him in its top three tiers, or he is 24 or younger, it rates him above market and it gains at least 5% in market value. | 169 | 2,377 |
| **Has a real centrepiece** | At least one player in the trade must be worth a second-round tier or better on your board or the consensus, or the trade must include a first-round pick. Several small pieces never add up to a centrepiece. | 558 | 1,819 |
| **Keeps your best player** | The best player you get must be worth at least 70% of the best player you give. Stops trades that break up your top asset for lesser pieces. | 30 | 1,789 |
| **No filler pieces** | Every piece in the trade must be worth at least 450, and at least a quarter of the trade's best player. Stops trades padded with bench players or late picks. | 1,484 | 305 |
| **No extra QB or TE** | Neither side gets a QB or TE when it already keeps as many comparable ones (worth at least 70% of the incoming player) as it has starting spots for that position. Skipped when the league's lineup is unknown. | 90 | 215 |

Sum check: 45,056 − 44,841 = 215. Every candidate is counted once, at the first rule that
stops it, so the removals add up to exactly the difference.

Two things jump out, and both are for the founder to question (§9): **"Fair by market value"
removes 9 in 10 candidates** before anything else is judged, and **"No filler pieces" removes
more than the other three deck rules together** (1,484 of the 2,377 trades that reach the deck
rules here, against 678).

## 2. The rule catalog

`backend/rule_catalog.py` holds it as data (pure, no engine imports): 45 entries in waterfall
order. 40 are waterfall rows (31 of them live today) (`kind` `rule` or `search_limit`); the others say what the
waterfall starts with (`scope`), add cards after the deck is built (`addition`), put removed
cards back (`exception`) or only reorder (`reorder`). "Live" = can fire on an organic deck with
today's production configuration. Revision 5 (the win-now season signal) adds **no rule**: its
season lineup changes the inputs of "Good for you" / "Good for them" and its conflict demotion
only reorders.

**Order.** Stages run in the order shown. Inside the both-sides check the owner evaluator's
checks are strictly first-failure (`trade_gen_owner.py:504-579`). The six bilateral checks
(`viewer_intent_unfulfilled` … `tanking_favored_young_asset`, `trade_gen_bilateral.py:271-302`)
run together after those pass, and **when a trade fails several of them the engine records the
last one in the listed order**; the waterfall counts the reason the engine records, so it still
counts each candidate once (flagged in §9).

`test_rule_catalog` fails when the engine gains a rejection reason the catalog does not list: it
walks the served generators' search classes by AST (every `finish("…")` literal, the computed
`finish(name + "_no_benefit")` resolved from its loop, every `reason = "…"` / `reason="…"`), the
reasons `deck_quality.card_rule` returns and `DeckRules.reason` assigns; an argument it cannot
resolve fails too. It also fails on a catalog row the engine no longer produces, on drift
between the generator's inline list of fixable reasons and the page search's copy, and lints
every name (at most five words) and description (one to three sentences, no snake_case,
camelCase, calls or file names).

| # | Key | Name | Description | Stage | Kind | Live | Protects | User setting | Source | Counted today |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `pool` | Players the search considers | For each other team, the search only builds trades from 16 of your players and 16 of theirs, picked for interest, value spread and position mix. Players with no market value are never included. The waterfall starts with every 1-for-1, 2-for-1 and 1-for-2 trade that can be built from those players. | candidate building | scope | yes | deck quality | Fixed (16 per side per team) | trade_gen_owner.py:633-653 (pool), :231 and database.py owner_pool_size (16) | Not counted; the waterfall reports the number of possible trades from full rosters for context |
| 2 | `not_expanded` | Not worth adding a piece | A 2-for-1 or 1-for-2 is only tried when its core 1-for-1 passed, or failed for a reason an extra piece could fix (price, fairness, or one side not gaining enough). If the core 1-for-1 failed anything else, every larger version of it is skipped untested. | candidate building | search_limit | yes | deck quality | Fixed | trade_gen_bilateral.py:377-381 (the list of fixable reasons; trade_first_page.py:162 repeats it) | Not counted |
| 3 | `search_budget` | Search time limit | The full search stops after 4,096 trades per other team and 60,000 in total. On the deck served today the fast search does not stop there; the waterfall raises the limit to 120,000, so this only removes trades in leagues of about 30 teams or more. | candidate building | search_limit | yes | deck quality | Fixed | trade_gen_owner.py:49-50, :751-757; database.py owner_pair_budget / owner_total_budget | Generation report budget_exhausted (true/false), no count |
| 4 | `invalid_fairness` | Fairness setting is usable | If the fairness setting sent with the request is not a number between 0 and 1, every trade is rejected. A safety check; it should never fire. | both-sides check | rule | yes | both | Trade settings: fairness | trade_gen_owner.py:504-505 | evaluator report, gated full solve only |
| 5 | `invalid_partner` | Partner is in your league | The other team must be a different team in this league (and the chosen team, when you picked one). A safety check; it should never fire. | both-sides check | rule | yes | both | Fixed | trade_gen_owner.py:506-509 | evaluator report, gated full solve only |
| 6 | `invalid_assets` | Trade pieces are valid | Both sides must send at least one piece, no piece twice, no piece on both sides, and every piece must have a market value. A safety check. | both-sides check | rule | yes | both | Fixed | trade_gen_owner.py:510-513 | evaluator report, gated full solve only |
| 7 | `assets_not_owned` | Pieces on the right rosters | Everything you send must be on your roster and everything you get must be on theirs. A safety check against stale rosters. | both-sides check | rule | yes | both | Fixed | trade_gen_owner.py:514-517 | evaluator report, gated full solve only |
| 8 | `exact_give_mismatch` | Sends exactly what you chose | Only when you search with 'send exactly these players': the trade must send exactly that set. | both-sides check | rule | no | you | Targeted search: send exactly | trade_gen_owner.py:518-519 | evaluator report, gated full solve only |
| 9 | `selection_mismatch` | Includes the players you chose | Only on a targeted search: the trade must include the players you picked to send or to get (or at least one of them on the 'closest alternative' pass). | both-sides check | rule | no | you | Targeted search: chosen players | trade_gen_owner.py:520-523 | evaluator report, gated full solve only |
| 10 | `avoided_position` | Avoids positions you avoid | You never get a player at a position you marked as 'Avoiding'. The setting is hidden today (switched off), so this never fires. | both-sides check | rule | no | you | Trade settings: Avoiding positions (switched off today) | trade_gen_owner.py:524-525; server.py _owner_generation_context avoid_positions; config/features.json trade.avoid_positions false | evaluator report, gated full solve only |
| 11 | `previous_disposition` | Not one you already answered | A trade you passed on in the last 14 days, liked in the last 7, or that is waiting on the other manager or already agreed is not shown again. | both-sides check | rule | yes | you | Fixed (pass cooldown 14 days, like window 7 days) | trade_gen_owner.py:526-527; server.py _load_trade_disposition_keys, _load_presentment_exclusions; database.py pass_cooldown_days (14) | evaluator report, gated full solve only |
| 12 | `organic_shape` | Small trades only | Suggested trades are 1-for-1, 2-for-1 or 1-for-2. Bigger trades appear only when you pick several players yourself. | both-sides check | rule | yes | deck quality | Fixed | trade_gen_owner.py:528-529 | evaluator report, gated full solve only |
| 13 | `tier_direction` | Matches your requested move | Only when you ask to move up, move down or stay level: your best incoming player must be in a higher, lower or the same tier as your best outgoing one on your own board (or 5% better or worse in the same tier). | both-sides check | rule | no | you | Trade intent (move up / down / level) | trade_gen_owner.py:530-536 | evaluator report, gated full solve only |
| 14 | `selected_position` | Gets the position you chose | Only when you ask for a position swap: your best incoming player must play one of the positions you chose. | both-sides check | rule | no | you | Trade intent (position swap) | trade_gen_owner.py:537-540 | evaluator report, gated full solve only |
| 15 | `invalid_market_value` | Trade can be priced | The market price of both sides must be computable. A safety check. | both-sides check | rule | yes | both | Fixed | trade_gen_owner.py:541-543 | evaluator report, gated full solve only |
| 16 | `market_floor` | Fair by market value | By consensus market value, the cheaper side must be worth at least 65% of the dearer side, or your fairness setting if it is stricter. This is the fairness check both managers rely on. | both-sides check | rule | yes | both | Trade settings: fairness (only above 65% has an effect) | trade_gen_owner.py:236 (floor), :551-552; database.py market_floor_absolute (0.65) | evaluator report, gated full solve only |
| 17 | `market_overpay` | No big overpay either way | A trade is dropped when one side pays at least 500 more in market value and that gap is at least a quarter of the bigger side. This applies in both directions, including trades where you are the one being overpaid. | both-sides check | rule | yes | both | Fixed (not affected by the fairness setting) | trade_gen_owner.py:553-554; trade_service.py overpay_ok; database.py max_overpay_frac (0.25), max_overpay_min_value (500) | evaluator report, gated full solve only |
| 18 | `viewer_no_benefit` | Good for you | Your fit score for the trade must be above 0.35, on a 0-to-1 scale where 0.5 is neutral. The score mixes how you rank the players (45%), market value (35%) and your team plan (20%). | both-sides check | rule | yes | you | Indirectly: your rankings and team outlook | trade_gen_owner.py:562-564; trade_gen_bilateral.py:23-24 (weights), :244 (score minus 0.35) | evaluator report, gated full solve only |
| 19 | `counterparty_no_benefit` | Good for them | The other manager's fit score must also be above 0.35, judged from their rankings (or market value when they have none), market value and their team plan. | both-sides check | rule | yes | the other manager | Fixed | trade_gen_owner.py:562-564; trade_gen_bilateral.py:244 | evaluator report, gated full solve only |
| 20 | `untouchable` | Keeps players marked Keep | A suggested trade never sends a player either manager marked Keep (untouchable), unless you chose to send that player yourself. | both-sides check | rule | yes | both | Roster setup: Keep | trade_gen_owner.py:565-575; database.py owner_untouchable_hard (1 = hard rule) | evaluator report, gated full solve only |
| 21 | `untouchable_return` | Keep players need a premium | Only if the hard Keep rule is switched off: a Keep player may leave only for more market value and a player at the same position coming back. | both-sides check | rule | no | both | Roster setup: Keep (old rule, switched off) | trade_gen_owner.py:576-579; database.py owner_untouchable_hard | evaluator report, gated full solve only |
| 22 | `viewer_intent_unfulfilled` | Something you want | The trade must match something you showed you want: a player you rank clearly above market coming in (or below market going out), a player or position you asked for, a player on your trade block, a stated team plan it helps, or, if you have not ranked players yet, a small market or plan gain. | both-sides check | rule | yes | you | Indirectly: your rankings, targets, trade block, outlook | trade_gen_bilateral.py:196-201, :271-272 | evaluator report, gated full solve only |
| 23 | `expired_draft_asset` | No used draft picks | No trade may include a draft pick from a draft that has already happened. | both-sides check | rule | yes | both | Fixed | trade_gen_bilateral.py:277-278 | evaluator report, gated full solve only |
| 24 | `known_preference_harm` | Not against their rankings | If either manager's own rankings say the trade clearly moves them the wrong way (net lean below -0.15) and it does little for their team plan (plan gain under 0.20), it is dropped. | both-sides check | rule | yes | both | Indirectly: rankings | trade_gen_bilateral.py:279-280 | evaluator report, gated full solve only |
| 25 | `tanking_own_next_draft_pick` | Tanking teams keep next pick | A team marked Tanking never sends its own next-year draft pick, unless you chose to send it yourself. | both-sides check | rule | yes | both | Team outlook: Tanking | trade_gen_bilateral.py:281-284 | evaluator report, gated full solve only |
| 26 | `tanking_rb_without_long_term_exception` | Tanking teams skip older RBs | A team marked Tanking does not take on a running back unless it ranks him in its top three tiers, or he is 24 or younger, it rates him above market and it gains at least 5% in market value. | both-sides check | rule | yes | both | Team outlook: Tanking | trade_gen_bilateral.py:285-294 | evaluator report, gated full solve only |
| 27 | `tanking_favored_young_asset` | Tanking teams keep young favourites | A team marked Tanking does not give away a young QB (27 or under) or WR or TE (25 or under) it rates above market when the trade as a whole leans against its rankings. | both-sides check | rule | yes | both | Team outlook: Tanking | trade_gen_bilateral.py:295-302 | evaluator report, gated full solve only |
| 28 | `unnecessary_compensation` | No needless extra pieces | Revision 1 only (not served today): a 2-for-1 is dropped when the same trade without the extra piece is just as good for both managers. | both-sides check | rule | no | both | Fixed | trade_gen_bilateral.py:308-334 | evaluator report, gated full solve only |
| 29 | `duplicate` | Same trade listed once | If the same two-sided trade with the same team turns up twice in the search, it is kept once. | both-sides check | rule | yes | deck quality | Fixed | trade_gen_bilateral.py:496-499 | Not counted |
| 30 | `significance` | Has a real centrepiece | At least one player in the trade must be worth a second-round tier or better on your board or the consensus, or the trade must include a first-round pick. Several small pieces never add up to a centrepiece. | deck rules | rule | yes | deck quality | Fixed | deck_rules.py:58-59; server.py _evaluate_trade_significance; trade_significance.py; database.py significance_mode (2 = enforce in production), significance_player_min_tier (2 = second) | Counted in the rules-first log line (rules_rejected) as distinct packages checked; downstream copy counted in the job's significance diagnostics |
| 31 | `breakup` | Keeps your best player | The best player you get must be worth at least 70% of the best player you give. Stops trades that break up your top asset for lesser pieces. | deck rules | rule | yes | you | Fixed | deck_quality.py:49-54, :92-93; BREAKUP_MIN_RATIO (0.70) at :26 | rules_rejected in the rules-first log line; downstream copy in the deck quality filters log line |
| 32 | `filler` | No filler pieces | Every piece in the trade must be worth at least 450, and at least a quarter of the trade's best player. Stops trades padded with bench players or late picks. | deck rules | rule | yes | deck quality | Fixed | deck_quality.py:57-63, :94-95; FILLER_FLOOR (450), FILLER_FRAC (0.25) at :27-28 | rules_rejected in the rules-first log line; downstream copy in the deck quality filters log line |
| 33 | `redundant` | No extra QB or TE | Neither side gets a QB or TE when it already keeps as many comparable ones (worth at least 70% of the incoming player) as it has starting spots for that position. Skipped when the league's lineup is unknown. | deck rules | rule | yes | both | Indirectly: your league's lineup | deck_quality.py:66-80, :96-99; REDUNDANT_MIN_RATIO (0.70) at :29 | rules_rejected in the rules-first log line; downstream copy in the deck quality filters log line |
| 34 | `likes_you_added` | Trades they already liked | Up to 3 trades another manager already liked are added to the top of your deck, or flagged if already there. They skip the deck rules and must pass their own checks: still on both rosters, nothing you marked Keep or Not interested, you gain value, no overpay against you and no filler. | after the deck is built | addition | yes | both | Fixed (cap 3) | server.py _inject_likes_you_cards_impl (gates), _LIKES_YOU_CAP (3); likes_you_gate_level (2) | Log line 'liked cards proven/consensus/errors' |
| 35 | `standing_offer_added` | Standing offers | Standing offers from other managers can be added the same way, sharing the cap of 3. | after the deck is built | addition | yes | both | Fixed (shares the cap of 3) | server.py _inject_likes_you_cards_impl standing-offer branch | Cap drops counted in the likes-you log line |
| 36 | `decline_window` | Not like one you declined | For 30 days after you decline a trade, near-copies are hidden: same main player, same shape and a package value within 10%. One near-copy may come back once the 30 days end, as a retest. | after the deck is built | rule | yes | you | Fixed (30 days, 10%) | server.py _apply_deck_suppression; database.py fatigue_decline_suppress_days (30), fatigue_decline_value_band (0.10) | Job suppression_note count (after the floor) |
| 37 | `decline_floor` | Never fewer than five | If hiding near-copies of declined trades would leave fewer than 5 cards, the best hidden ones are put back until there are 5. | after the deck is built | exception | yes | you | Fixed (5) | server.py _apply_deck_suppression floor; _DECK_MIN_CARDS (5) | Warning log line 'suppression floor engaged' |
| 38 | `revised_offer_replaced` | Replaced by revised offer | When one of your own declined offers has a revised version, it leads the deck (up to 3) and any identical suggested trade is removed so it is not shown twice. | after the deck is built | rule | yes | deck quality | Fixed (cap 3) | server.py _inject_revised_offer_cards; trade_revised_offers.py build | Not counted |
| 39 | `revalidation` | Still valid at serve time | Each suggested trade is checked again with the same evaluator just before it is served. It only fails if something changed while the deck was being built. | after the deck is built | rule | yes | both | Fixed | server.py _owner_cards_valid | Not counted |
| 40 | `roster_protection` | Roster stays legal | Would check that both rosters stay legal and keep a full lineup after the trade. Switched off today. | after the deck is built | rule | no | both | Fixed | server.py _evaluate_deck_rosters; trade.roster_protection | Job roster_evaluation diagnostics |
| 41 | `market_policy` | Personal-market policy | Would apply a second market-value floor and two-sided gain check. Switched off today. | after the deck is built | rule | no | both | Fixed | server.py _evaluate_deck_policy; trade.personal_market_policy_v1 | trade_policy_shadow rows |
| 42 | `significance_recheck` | Centrepiece checked again | The centrepiece rule runs again on the finished deck. On today's deck it removes nothing; a removal here would mean the two copies disagree. | after the deck is built | rule | yes | deck quality | Fixed | server.py _run_trade_job significance block | Warning log line 'rules-first guard' when it removes anything |
| 43 | `dispositions` | Not answered meanwhile | Just before serving, trades you passed on in the meantime are removed, and liked trades whose like was withdrawn are removed. | after the deck is built | rule | yes | you | Fixed | server.py _project_trade_dispositions | Not counted |
| 44 | `quality_recheck` | Quality rules checked again | The keeps-your-best-player, filler and extra-QB/TE rules run again on the finished deck. On today's deck they remove nothing. | after the deck is built | rule | yes | deck quality | Fixed | server.py _run_trade_job quality block | Deck quality filters log line; 'rules-first guard' warning |
| 45 | `repeat_cap` | Variety in the first 30 | No player appears in more than 5 of the first 30 cards; extra repeats move to just after card 30. Nothing is removed. | after the deck is built | reorder | yes | deck quality | Fixed (5 of 30) | deck_quality.py:128-143; REPEAT_CAP (5), REPEAT_WINDOW (30) at :30-31 | Deck quality filters log line (deferred) |

## 3. How the counts are obtained

### 3.1 Why a diagnostic full solve, not the served page's counts

The served deck is built by the page search to exhaustion (ADR-030). It never evaluates most
candidates: its price envelope (`trade_first_page._Member.can_clear`) drops a package it can
prove is below the market floor without evaluating it, `admit` drops a package failing a deck
rule before pricing, and evaluation is ordered by bounds. Those skips are honest (each provably
removes only cards a rule would remove) but they record no per-rule count, so the page cannot
say which rule each skipped candidate fails. Counting from it would present pruned candidates as
unexplained, or attribute them to whichever check happened to run.

So the waterfall runs a **diagnostic full solve** for the founder's selected league
(`rule_waterfall.diagnostic_solve`): the served generator's own search, over the same universe,
with every candidate it enumerates evaluated by the unmodified evaluator, then:

| Step | Rows | How |
|---|---|---|
| Started with | header | `universe`: every 1×1, 2×1 and 1×2 package of each opponent's two pools (`_pool`, up to 16 per side). Equals `PageSearch`'s `universe` count. |
| Candidate building | `not_expanded`, `search_budget` | universe − evaluated. A 2-asset side whose every parent 1×1 failed an incurable reason was never generated (`trade_gen_bilateral.py:377-381`); anything else unevaluated is the stream budget. Budgets are raised to the evaluator's maxima (120,000 total, 16,384 per pair), as the served page ignores them, so `search_budget` is 0 below about 30 teams. |
| Both-sides check | the evaluator's reasons, then `duplicate` | The recorded reason of each evaluation. Must equal the generator's own `report["rejections"]` (checked on every run; it raises otherwise). |
| Deck rules | `significance`, `breakup`, `filler`, `redundant` | `DeckRules.reason` (the job's own predicate, first failing rule) on each evaluator survivor. |
| After the deck is built | `decline_window` … `quality_recheck` | The worker's stages, passed in as `after` (§7.3), each counted by the generated cards it removes. Cards a stage adds (liked trades, standing offers) are `added`, never netted into a row. |

Identity, checked on every run: **started − Σ removed = served from the engine**, and
**served = that + added**.

### 3.2 Attribution order and its one known difference from the served path

On the served page path a 2-asset package failing a deck rule is dropped before it is
evaluated, so a package that fails both a deck rule and a both-sides check is "removed" by the
deck rule there; the waterfall, evaluating first, names the both-sides check. Both orders remove
the same packages and serve the same deck; the waterfall's order is the logical one (is it a
legal, fair trade both managers gain from, then is it a good card) and is the order the
generator's own report counts. The header line says which basis is used.

### 3.3 Is the waterfall honest about what was served?

- **The deck the diagnostic ranks is the rules-first deck the worker serves**, card for card and
  proof for proof, whenever the page serves (`test_the_diagnostic_ranks_the_deck_the_worker_serves`:
  synthetic 5/12 teams, revisions 1 and 2, and the fixture league under revision 5).
- **Through the real worker**, the waterfall's served count equals the size of the published
  deck (`test_served_count_equals_the_workers_published_deck`): `server._run_trade_job` with
  production's flags (rules-first, likes-you, decline suppression, significance enforced,
  quality filters), the waterfall computed inside the same job at the construction call with
  `server_stages`, and a league with two liked trades added (one with no centrepiece, which the
  job exempts from the significance re-check), one liked trade flagged in place and one
  declined near-copy suppressed. Both significance tiers.
- **Not replayed: revised offers** (`trade.next_move`, on in production). Building one writes a
  `revised_offer_cards` row, so the waterfall shows that row as "not measured". Effect: up to 3
  revised cards added and up to 3 identical suggested trades removed are not in the counts.
  Personal-market policy and roster protection are dark; if either is switched on, its row
  shows "not measured" too.

### 3.4 Instrumentation neutrality

No engine module changes. The only engine-facing code is `_Recorded`, a subclass of the
generator's own search class (`_GenerationSearch` or `_Search`) whose `evaluate` calls the
original and records the result's reason, the same subclassing the page search
(`_private_search`) and gated full solve (`_Gated`) use. The worker never imports
`rule_waterfall`. Tests: the evaluator rows equal the un-instrumented generator's own
rejection counts over the same universe; a waterfall run changes neither the request's inputs
nor the served deck built after it (cards, order, terms); a sabotage that makes the recorder
reject about 1 in 7 eligible cards turns the deck-equality test red. The frozen and golden suites
(`test_bilateral_generation_freeze`, `test_bakeoff_arm_a_golden`, `test_engine_quality_golden`,
`test_trade_first_page`, `test_rules_first_deck`, `test_trade_fast_deck`) run unchanged and
green.

### 3.5 Aggregates only

The output holds counts, shares, rule names and descriptions, the generator and rules versions
and timing. No player, user, roster or league id (`test_output_is_aggregate_only` checks every
id of the fixture league against the serialized output).

## 4. Example waterfalls with the sum check

Fairness 75% (the organic default), significance enforced at the second tier (production's
capture), deck quality filters on, no liked trades or decline history (so nothing after the
deck is built fires; §3.3 covers that path through the worker).

### Fixture league (12 teams, revision 2, viewer Contending)

Started with **45,056** candidate trades → **215** served (241,472 possible from full rosters; generator `owner-v2-bilateral-2`).

| Stage | Rule | Removed | Remaining | Share of started |
|---|---|---:|---:|---:|
| candidate building | Not worth adding a piece | 23 | 45,033 | 0.1% |
| both-sides check | Fair by market value | 41,224 | 3,809 | 91.5% |
| both-sides check | Good for you | 326 | 3,483 | 0.7% |
| both-sides check | Good for them | 310 | 3,173 | 0.7% |
| both-sides check | Something you want | 581 | 2,592 | 1.3% |
| both-sides check | Not against their rankings | 46 | 2,546 | 0.1% |
| both-sides check | Tanking teams skip older RBs | 169 | 2,377 | 0.4% |
| deck rules | Has a real centrepiece | 558 | 1,819 | 1.2% |
| deck rules | Keeps your best player | 30 | 1,789 | 0.1% |
| deck rules | No filler pieces | 1,484 | 305 | 3.3% |
| deck rules | No extra QB or TE | 90 | 215 | 0.2% |

Sum check: 45,056 − 44,841 = 215 served (+0 added). Rules with 0 removed (29): Search time limit, Fairness setting is usable, Partner is in your league, Trade pieces are valid, Pieces on the right rosters, Sends exactly what you chose, Includes the players you chose, Avoids positions you avoid, Not one you already answered, Small trades only, Matches your requested move, Gets the position you chose, Trade can be priced, No big overpay either way, Keeps players marked Keep, Keep players need a premium, No used draft picks, Tanking teams keep next pick, Tanking teams keep young favourites, No needless extra pieces, Same trade listed once, Not like one you declined, Replaced by revised offer, Still valid at serve time, Roster stays legal, Personal-market policy, Centrepiece checked again, Not answered meanwhile, Quality rules checked again.

### Fixture league (12 teams, revision 5 with season evidence)

Started with **45,056** candidate trades → **287** served (241,472 possible from full rosters; generator `owner-v2-bilateral-5`).

| Stage | Rule | Removed | Remaining | Share of started |
|---|---|---:|---:|---:|
| candidate building | Not worth adding a piece | 27 | 45,029 | 0.1% |
| both-sides check | Fair by market value | 41,352 | 3,677 | 91.8% |
| both-sides check | Good for you | 413 | 3,264 | 0.9% |
| both-sides check | Good for them | 309 | 2,955 | 0.7% |
| both-sides check | Something you want | 612 | 2,343 | 1.4% |
| both-sides check | Not against their rankings | 45 | 2,298 | 0.1% |
| both-sides check | Tanking teams skip older RBs | 152 | 2,146 | 0.3% |
| deck rules | Has a real centrepiece | 379 | 1,767 | 0.8% |
| deck rules | Keeps your best player | 67 | 1,700 | 0.1% |
| deck rules | No filler pieces | 1,291 | 409 | 2.9% |
| deck rules | No extra QB or TE | 122 | 287 | 0.3% |

Sum check: 45,056 − 44,769 = 287 served (+0 added). Rules with 0 removed (29): Search time limit, Fairness setting is usable, Partner is in your league, Trade pieces are valid, Pieces on the right rosters, Sends exactly what you chose, Includes the players you chose, Avoids positions you avoid, Not one you already answered, Small trades only, Matches your requested move, Gets the position you chose, Trade can be priced, No big overpay either way, Keeps players marked Keep, Keep players need a premium, No used draft picks, Tanking teams keep next pick, Tanking teams keep young favourites, No needless extra pieces, Same trade listed once, Not like one you declined, Replaced by revised offer, Still valid at serve time, Roster stays legal, Personal-market policy, Centrepiece checked again, Not answered meanwhile, Quality rules checked again.

### Synthetic 12-team league (seed 7, revision 2)

Started with **45,056** candidate trades → **580** served (152,064 possible from full rosters; generator `owner-v2-bilateral-2`).

| Stage | Rule | Removed | Remaining | Share of started |
|---|---|---:|---:|---:|
| candidate building | Not worth adding a piece | 33 | 45,023 | 0.1% |
| both-sides check | Fair by market value | 39,006 | 6,017 | 86.6% |
| both-sides check | Good for you | 504 | 5,513 | 1.1% |
| both-sides check | Good for them | 523 | 4,990 | 1.2% |
| both-sides check | Something you want | 773 | 4,217 | 1.7% |
| both-sides check | Not against their rankings | 43 | 4,174 | 0.1% |
| both-sides check | Tanking teams skip older RBs | 238 | 3,936 | 0.5% |
| both-sides check | Tanking teams keep young favourites | 13 | 3,923 | 0.0% |
| deck rules | Has a real centrepiece | 496 | 3,427 | 1.1% |
| deck rules | Keeps your best player | 250 | 3,177 | 0.6% |
| deck rules | No filler pieces | 2,141 | 1,036 | 4.8% |
| deck rules | No extra QB or TE | 456 | 580 | 1.0% |

Sum check: 45,056 − 44,476 = 580 served (+0 added). Rules with 0 removed (28): Search time limit, Fairness setting is usable, Partner is in your league, Trade pieces are valid, Pieces on the right rosters, Sends exactly what you chose, Includes the players you chose, Avoids positions you avoid, Not one you already answered, Small trades only, Matches your requested move, Gets the position you chose, Trade can be priced, No big overpay either way, Keeps players marked Keep, Keep players need a premium, No used draft picks, Tanking teams keep next pick, No needless extra pieces, Same trade listed once, Not like one you declined, Replaced by revised offer, Still valid at serve time, Roster stays legal, Personal-market policy, Centrepiece checked again, Not answered meanwhile, Quality rules checked again.

### Synthetic 14-team league (seed 3, revision 2, viewer Rebuilding)

Started with **53,248** candidate trades → **391** served (179,712 possible from full rosters; generator `owner-v2-bilateral-2`).

| Stage | Rule | Removed | Remaining | Share of started |
|---|---|---:|---:|---:|
| candidate building | Not worth adding a piece | 37 | 53,211 | 0.1% |
| both-sides check | Fair by market value | 46,538 | 6,673 | 87.4% |
| both-sides check | Good for you | 486 | 6,187 | 0.9% |
| both-sides check | Good for them | 576 | 5,611 | 1.1% |
| both-sides check | Something you want | 826 | 4,785 | 1.6% |
| both-sides check | Not against their rankings | 31 | 4,754 | 0.1% |
| both-sides check | Tanking teams skip older RBs | 299 | 4,455 | 0.6% |
| both-sides check | Tanking teams keep young favourites | 14 | 4,441 | 0.0% |
| deck rules | Has a real centrepiece | 563 | 3,878 | 1.1% |
| deck rules | Keeps your best player | 373 | 3,505 | 0.7% |
| deck rules | No filler pieces | 2,289 | 1,216 | 4.3% |
| deck rules | No extra QB or TE | 825 | 391 | 1.5% |

Sum check: 53,248 − 52,857 = 391 served (+0 added). Rules with 0 removed (28): Search time limit, Fairness setting is usable, Partner is in your league, Trade pieces are valid, Pieces on the right rosters, Sends exactly what you chose, Includes the players you chose, Avoids positions you avoid, Not one you already answered, Small trades only, Matches your requested move, Gets the position you chose, Trade can be priced, No big overpay either way, Keeps players marked Keep, Keep players need a premium, No used draft picks, Tanking teams keep next pick, No needless extra pieces, Same trade listed once, Not like one you declined, Replaced by revised offer, Still valid at serve time, Roster stays legal, Personal-market policy, Centrepiece checked again, Not answered meanwhile, Quality rules checked again.

`market_overpay` ("No big overpay either way") removed 0 in all four: at 75% fairness the
market floor already rejects every trade it would (§9).

## 5. Notes

Storage: one additive table, `founder_rule_notes` (`backend/database.py`; data dictionary
§`founder_rule_notes`): `id`, `rule_key`, `user_id` (the founder's ACCOUNT id), `body`,
`created_at`. **Append-only**: a save adds a row; the newest row per rule is the current note;
saving an empty text clears the note and keeps its history, so a question is never lost to an
edit. Created by `metadata.create_all` on existing databases; no existing row is rewritten.
Deleted and exported with the author's account (`accounts._ADDITIONAL_PRIVATE_TABLES`).

Accessors (no routes):

| Function | Returns / raises |
|---|---|
| `save_founder_rule_note(rule_key, body, author_id, *, now=None)` | The rule's current note (shape below, for the author). Raises `FounderNoteError` with `code` `unknown_rule` (key not in `rule_catalog`), `too_long` (over 2,000 characters after trimming), `invalid_body`, `no_author`; nothing is written on a raise. |
| `load_founder_rule_notes(*, viewer_id=None, include_empty=False)` | Current notes in catalog order: `{rule_key, rule_name, body, author, updated_at, created_at, versions}`. `author` is `"you"` when `viewer_id` wrote the current version, else `"founder"`; with no viewer (the future cron-secret operator read) every author is `"founder"`. Rules with no note or a cleared note are omitted unless `include_empty`. |
| `load_founder_rule_note_history(rule_key, *, viewer_id=None)` | Every version, oldest first: `{body, author, created_at}`. |

Notes attach to catalog keys, not to a run, so they stay with a rule across waterfall runs and
leagues; every catalog entry can carry one, including the non-waterfall ones (the 16-player
pool, liked trades, the five-card floor, the repeat cap). Account ids never leave the server.

## 6. The page

Founder-only, inside the Founders' review area (the first use case's gate: flag
`founder.review`, env allow-list `FOUNDER_ACCOUNTS`). Chalkline tokens and components only.

1. **Title** "Rule waterfall", the league picker the area already uses, and the action
   **Run for this league**. While a run is in progress the button reads "Running…" and is
   disabled, a spinner row replaces the table body, and the page polls every 2 s (§7.1). A
   failed or unsupported run shows its one-line reason and the button again.
2. **Header line**, exactly: "Started with **N** candidate trades → **M** served", then, in
   smaller text, the one-line definition of "started with" (§1), the run time ("Run 3 min ago,
   generator owner-v2-bilateral-2") and, when `added` > 0, "(+A added after the deck was built:
   trades another manager already liked)".
3. **Table**, one row per waterfall rule in order, grouped under four section headers (the
   stages: Candidate building · Both-sides check · Deck rules · After the deck is built), each
   header showing its stage total removed. Columns:
   - **Rule**: the name (bold). Rules that are off today carry a muted "off" tag; search limits
     carry a muted "search limit" tag.
   - **What it checks**: the description, two lines then "more" to expand.
   - **Removed**: count; **Remaining**: count after the rule.
   - **Share**: a horizontal bar of `share_of_started` (flare, informational), with the
     percentage; hover/long-press shows `share_of_reaching` ("removed 41% of the trades that
     reached it").
   - **Notes**: a multi-line text field with the current note and a **Save** button (enabled
     when the text changed; shows "Saved" for 2 s; an error string on `too_long`). Under it, in
     muted text, "you · 2 h ago" or "founder · 2 h ago", and "3 earlier versions" when
     `versions` > 1 (expands the history, read-only).
   Rows with a status of `not_measured` show "not measured" in Removed and a one-line reason;
   `not_run` rows show "—". Zero rows collapse under "Rules that removed nothing (N)".
4. **Other rules** (below the table, collapsed): the non-waterfall catalog entries (the pool,
   liked trades, standing offers, the five-card floor, the repeat cap), each with name,
   description and its notes field, so the founder can comment on them too.
5. Before any run, the table renders from the catalog alone (names, descriptions, notes, empty
   counts) so notes can be written without running anything.

## 7. Routes to wire

### 7.1 `GET` / `POST /api/founder/rule-waterfall` (founder-gated read and run)

Gate: the founder gate of use case 1 (404 when `founder.review` is off or the session's account
is not in `FOUNDER_ACCOUNTS`). Session-authenticated (`@_gate_unverified_read` / `_write`).

`POST` body `{"league_id": str}` → starts a run for the caller's own deck request in that
league, in the background (§8); `202 {"status": "running", "run_id": str}`. `409
{"error": "run_in_progress"}` when this process already runs one (one at a time, any founder).
`400 {"error": "league_required"}`.

`GET ?league_id=…` →

```json
{
  "status": "none | running | complete | failed | unsupported",
  "error": "null | short reason (failed / unsupported)",
  "run_at": "ISO UTC of the latest completed run, or null",
  "waterfall": "null | rule_waterfall.compute(...) output, as below",
  "catalog": "rule_catalog.as_rows() minus `source` and `counted`",
  "notes": "database.load_founder_rule_notes(viewer_id=<account>)"
}
```

`waterfall` is exactly `rule_waterfall.compute`'s return:

```json
{
  "version": "rule-waterfall-1", "catalog_version": "rule-catalog-1",
  "generator_version": "owner-v2-bilateral-2", "rules_version": "deck-rules-1",
  "basis": "diagnostic_full_solve", "started_definition": "Every 1-for-1, ...",
  "teams": 12, "possible_full_roster": 241472,
  "started": 45056, "served_generated": 215, "added": 0, "served": 215, "admitted": 215,
  "stages": [{"stage": "candidate building", "removed": 23}, "..."],
  "rows": [{"key": "market_floor", "name": "Fair by market value", "description": "...",
            "stage": "both-sides check", "kind": "rule", "status": "measured",
            "started": 45033, "removed": 41224, "remaining": 3809,
            "share_of_started": 0.914952, "share_of_reaching": 0.915417}, "..."],
  "elapsed_ms": 4400.0
}
```

`status` per row: `measured`, `not_measured` (live but not replayable without writes),
`not_run` (the stage does not run for this request, e.g. a dark flag). Results are kept in
process memory per (account, league), latest only (a restart loses them; re-run).

### 7.2 `PUT /api/founder/rule-notes/<rule_key>` (notes write)

Same gate. Body `{"body": str}` (empty clears). → `200` with
`save_founder_rule_note(rule_key, body, <account id>)`'s return:
`{"rule_key", "rule_name", "body", "author": "you", "updated_at", "created_at", "versions"}`.
`404 {"error": "unknown_rule"}`, `400 {"error": "too_long" | "invalid_body"}`. Rate limit: the
area's existing limiter if it has one; the table is append-only, so a cap of 60 saves an hour
per account is enough.

Later (operator tool, not this pass): `GET /api/admin/founder-rule-notes` with `X-Cron-Secret`,
returning `load_founder_rule_notes()` (no viewer: author "founder") plus each rule's history,
so future engineering sessions can pull the founder's questions.

### 7.3 Wiring the run (thin)

The run needs exactly what the trade job passes to the rules-first construction:
`(generate, owner_context, deck_rules)`. Recommended wiring:

1. A module-level, default-`None` probe in `server.py`, called once in `_gen_owner` right
   before `trade_fast_deck.serve(_generate, owner_context, deck_rules, ...)`:
   `if _rule_waterfall_probe is not None: _rule_waterfall_probe(_generate, owner_context, deck_rules)`.
   With the probe unset nothing changes (the same reasoning and tests as
   `test_served_count_equals_the_workers_published_deck`, which installs exactly this hook by
   wrapping `trade_fast_deck.serve`). Make it a per-job value (on the job dict), not a global,
   so a user's concurrent job never runs it.
2. The run route builds a trade job for the founder's own request in that league with
   preparation semantics (`prepare_sink` with a no-op sink: no impressions, no exposure events,
   suppression into a private sink, no revised-offer build) and the probe set to:
   `rule_waterfall.compute(generate, context, rules, after=rule_waterfall.server_stages(server,
   context=context, rules=rules, league=context["league"], league_id=league_id,
   significance_capture=job_capture))`, storing the result. A request outside the rules-first
   scope (no rules-first construction, or a pinned/targeted request) stores
   `{"status": "unsupported"}`.
3. Alternatively, factor the job's prelude (session capture → `owner_context`,
   `_rules_first_deck_rules`) into a helper both use; more code, no probe.

## 8. Cost and run model

One run is one full solve plus the deck rules and downstream on a few hundred cards. Measured
on this laptop, one process, synthetic leagues (revision 2), one run per process:

| Teams | Seed | Candidates | Wall | CPU | Peak process memory (baseline ~98 MB) |
|---|---|---:|---:|---:|---:|
| 12 | 7 | 45,056 | 3.4 s | 3.2 s | 412 MB |
| 12 | 11 | 45,056 | 4.3 s | 4.2 s | 422 MB |
| 14 | 7 | 53,248 | 5.2 s | 5.0 s | 457 MB |
| 14 | 11 | 53,248 | 5.0 s | 4.9 s | 484 MB |
| 16 | 7 | 61,440 | 4.7 s | 4.6 s | 498 MB |
| 16 | 11 | 61,440 | 5.2 s | 5.1 s | 515 MB |

On Render's single 4-thread worker, assuming the CPU is 3–4× slower (fast-deck v2 §8.2), a run
is **about 10–20 s of CPU holding the interpreter lock and about 300–420 MB of extra memory**.
That is too long for a request thread and would stall the other three threads' users.
Decision: **a background job with polling** (§7.1), and caps:

- **One run at a time in the process** (a lock; a second request gets 409), founder-only.
- **Wall cap 60 s** through the job's `check` (cancellation), then `failed: "timed_out"`.
- **No automatic runs**: only the button. Results are cached per (account, league) until the
  next run.
- Leagues above 16 teams (none in production) cost more roughly in proportion to candidates.

## 9. Rules flagged for the founder

From the catalog's `question` field (shown to the founder on the page next to the rule):

- **Players the search considers** (`pool`): 16 is a speed limit, not a judgement; a player outside the 16 never appears in any trade with that team.
- **Not worth adding a piece** (`not_expanded`): A shortcut, not a proven rule: adding a player more valuable than the core player changes which player counts as the main one, which can change the outcome of the skipped checks.
- **Fair by market value** (`market_floor`): A fairness setting below 65% does nothing (the fixed 65% floor wins), and between 65% and 75% it only matters for trades with a gap under 500 (see 'No big overpay either way'). It removes about 87-92% of all candidates.
- **No big overpay either way** (`market_overpay`): Overlaps 'Fair by market value': for gaps of 500 or more it acts as a 75% floor. At the default fairness setting (75%) it removed nothing in any measured league; below 75% it overrides the setting for every trade with a gap of 500 or more. Two rules, two thresholds, one idea.
- **Good for you** (`viewer_no_benefit`): 0.35 and the 45/35/20 weights are hand-set launch values, not calibrated on accepted trades.
- **Something you want** (`viewer_intent_unfulfilled`): The bar for 'rank clearly above market' is small (0.025 of a tier); in tests most served cards qualify through it.
- **Has a real centrepiece** (`significance`): Code default is off (significance_mode 0); production enforces it. A first-round pick always qualifies, any second-round pick never does.
- **No filler pieces** (`filler`): The 450 floor is a hand-set number, and the likes-you path uses a different filler rule (25% of the side's best player, plus its own floor).
- **Trades they already liked** (`likes_you_added`): Liked trades bypass every deck rule and both-sides check by design; one the engine finds unfair is still shown as a plain consensus card.
- **Never fewer than five** (`decline_floor`): With rules-first, the floor counts cards that already passed every rule, so heavy decliners can see up to 5 near-copies of declined trades.
- **Variety in the first 30** (`repeat_cap`): In 232 of 247 recorded decks the window never fills, so it pulls the lowest-ranked distinct trades forward.

Found while building the catalog (not rule rows, for the founder and engineering):

- **"Not interested" is soft on the deck the owner generator builds.** The worker comments call
  it a hard receive-side filter (`server.py` near "#163"), and the likes-you path enforces it
  as hard (`_inject_likes_you_cards_impl`), but the owner evaluator only uses it as a
  preference: −0.3 on a player's interest when choosing pools and in `preference_priority`
  (`trade_gen_owner.py:588`, `trade_gen_bilateral.py:157-158`). A player you marked Not
  interested can still be offered to you on a suggested card. Contradictory with the setting's
  promise; not a catalog row because no rule removes those cards.
- **The six bilateral checks report the last failing check, not the first** (§2). Harmless for
  counting, but a founder reading "Tanking teams skip older RBs" should know the same trade may
  also have failed "Something you want".
- **Evaluator counts exist only on the fallback path.** The generation report's `rejections`
  is filled by the gated full solve; the page search that normally serves keeps no per-reason
  count, so production cannot answer "how many did each rule remove" today without this tool.
- **Significance is off in code (`significance_mode` 0) and on in production (2).** A fresh
  environment silently serves a different deck from production's.
- **Two filler rules.** The deck's (`deck_quality`, every piece ≥ max(450, 25% of the trade's
  best player)) and the likes-you / legacy one (`trade_service.filler_ok`, 25% of the side's
  best piece plus `asset_floor_abs`) differ.
- **Liked trades bypass everything.** A liked trade the owner evaluator finds ineligible is
  still served as a consensus card (ADR-030 decision 3), and is exempt from the significance
  and quality re-checks.

## 10. What is not measured, and open questions

- **Revised offers** are not replayed (building writes); their row is "not measured" (§3.3).
- **The page's own pruning** (envelope, `admit`) is not shown: by design, the waterfall shows
  the rules, and the pruning provably removes only what a rule removes.
- **Partial/targeted requests** (pinned players, a chosen opponent, a move intent) are out of
  scope, as they are for rules-first construction: the run returns `unsupported`.
- **Render memory**: the plan's memory limit is not recorded in the repo; a 300–420 MB transient
  on top of the serving process needs the operator to confirm headroom before wiring.
- **Production numbers**: every number here is the fixture or synthetic leagues. The first real
  run will show production's shape; the 247 recorded requests could be replayed offline with
  this module if the operator wants a pooled table.

## 11. As built: the wiring pass

Wired on the same branch (2026-11-11). What follows is what shipped; **deviations** from §6-§8
are marked.

### 11.1 Routes

As §7, behind `_founder_session` (flag `founder.review` + `FOUNDER_ACCOUNTS` + a verified,
non-demo session; anything else 404 with no state change). Full shapes in
[api-reference](../../api-reference.md).

| Route | As §7? |
|---|---|
| `GET /api/founder/rule-waterfall?league_id=` | yes. A failed or unsupported run keeps the last completed `waterfall` / `run_at` (a failed run never replaces a result). |
| `POST /api/founder/rule-waterfall` `{league_id}` | 202 / 409 / 400 as §7. **Deviation:** an out-of-scope deck answers **200** `{status: "unsupported", error}` at once (the route checks owner-only serving and `deck.rules_first` before starting anything), and **400 `league_not_selected`** when the league is not the one the founder's session has selected (the run uses the session's loaded league, as a real deck request does). |
| `PUT /api/founder/rule-notes/<rule_key>` `{body}` | yes, plus **429 `rate_limited`** at 60 saves an hour per account (in memory; §7.2 asked for this cap). |
| `GET /api/founder/rule-notes/<rule_key>` | **Added**: the history accessor as a route, so the page can show earlier versions. |
| `GET /api/admin/founder/rule-notes` | §7.2's "later" operator read, built now (path `/api/admin/founder/rule-notes`, not `founder-rule-notes`, to sit beside the other admin reads). Cron secret; every rule ever noted with its current note and history; author always "founder". |

Every route is classified in `backend/paywall_gate.py` (the four founder routes `FREE`, the admin
read `NEVER_GATE`). Not decorated with `@_gate_unverified_*` (§7.1 suggested it): the founder
gate already requires a verified session, as the label routes do.

### 11.2 The run, and why it cannot touch a real request

`server._rule_waterfall_job` on a daemon thread (`_start_trade_job_thread`, the trade jobs'
own launcher). It builds a **private** trade job and runs `_run_trade_job` with:

- `execution_context` captured from the founder's session on the request thread
  (`_capture_trade_execution`: a deep copy of the league, a shallow copy of the trade service),
  with the copy's `_trade_cards` and `_significance_exemptions` replaced by fresh dicts, as the
  prepared runtime does for its private sessions;
- `prefs_preload` from `_trade_job_preferences` (what `/api/trades/generate` passes); fairness
  from `sess["trade_fairness_threshold"]` (the founder's last organic deck request; 0.75, the
  organic default, if none);
- the job's own `significance_capture` / `presentation_capture`, taken on the request thread;
- `prepare_sink=_NoPrepareSink()`: preparation mode (the value core is skipped, no exposure
  events, suppression into a private sink), with a sink whose every attribute access raises, so
  a job that ever got past the probe fails instead of doing preparation work;
- `work_check`: raises `TradeWorkCancelled("diagnostic_timed_out")` after 60 s (the job calls
  it from every `check_current`, including inside the search via `_check_current`);
- `rule_waterfall_probe`: the new per-job keyword (default None).

The job is registered in `_trade_jobs` (so `check_current` sees it live and the founder's own
input changes revoke it) with `source: "founder_rule_waterfall"`, **never** in
`_trade_jobs_by_key` / `_selected_trade_jobs`, so no request can find, reuse, poll or supersede
it; it is popped when the run ends. Its `run_id` is not a job id.

**The probe** (`_run_trade_job`, one guarded call): after the rules-first rules are built and
before `_fit_league_context` and any generation, `rule_waterfall_probe(owner_context,
deck_rules, check_current)`. **Deviation from §7.3.1:** §7.3 placed it inside `_gen_owner` before
`trade_fast_deck.serve`; it sits one level up instead, after the scope decision, so it fires on
every path the job can take (owner path or not, rules or none) and the job can never continue
into generation for a founder run. The probe takes the generator from
`_bakeoff.owner_generator(owner_context["config"])` (the call `_gen_owner` makes), computes
`rule_waterfall.compute(generate, owner_context, deck_rules, after=server_stages(...),
check=check_current)` and **always raises** `TradeWorkCancelled("diagnostic_complete")` (two
new reasons in `trade_work_control`). Out-of-scope requests (no owner context, no rules,
unsupported generator) record `unsupported`; a measurement error records `failed`. The job's
`TradeWorkCancelled` handler finishes it with that reason; nothing after the probe runs: no
generation, no card registration, no first page, no prepared inventory, no impressions, no
dispositions, no `trades_generated` event.

What runs before the probe is the real job's prelude for the same founder and league (reads:
rankings, preferences, drafts and picks, forecasts, negative memory; owned-pick injection into
the private copies; the job dict's own fields). `test_a_run_writes_nothing_a_real_request_reads`
compares every database table, the job tables, the session's card store and significance
provenance, the session, the league members and `record_event` before and after a run (equal),
and then shows the founder's next real deck is the same deck as before the run.

**Pipeline 29.** The probe is in `_run_trade_job`, a pinned function: `DECK_PIPELINE_VERSION`
28 → 29, digest `02e724a78ba569ee`. A bump makes stored pages from 28 fall through once. A
probe-free install was possible (the job's `work_check` is called at the start of
`_gen_owner`, and could read `owner_context` / `deck_rules` off the caller's frame) and was
rejected: it reads another function's locals and would break silently on a rename. With the
probe None a real job is byte-identical: the freeze and golden suites pass unchanged, a real
job's published deck on the production-flag harness is byte-for-byte the same under this
`server.py` and under the branch's previous one (every card field but the minted
`trade_id` / `impression_id` / `expires_at`), and the generate route and prepared runtime pass
no probe (`test_a_real_job_without_the_probe_is_byte_identical`).

### 11.3 Cost, and what a concurrent user's deck request sees

One run at a time per process (lock, then 409); results cached per (account, league), latest
only, lost on restart. Measured on this laptop (synthetic 12-team leagues, revision 2): a
waterfall run alone 3.4 s, peak process memory 172 → 398 MB (+226 MB). A real deck
construction for another league took 0.35–0.40 s alone (median 0.38 s) and **0.56–2.84 s while
a run was in progress** (median 0.63 s; the 2.84 s was the first one, overlapping the run's
heaviest stretch). Python shares the interpreter lock between threads every 5 ms, so a real
request is slowed, not blocked: expect roughly 1.5–7x on its CPU-bound part for the run's
10–20 s on Render, and nothing after the run ends. Prepared-inventory work and forecast batches
defer while a run is live (they already defer to any interactive job). Only the founder's
button starts a run: there is no cron, no automatic run and no other caller of
`_rule_waterfall_job`.

### 11.4 The page (Calibration › Founders' review › Trade rules)

`FounderReview` shows "Player labels | Trade rules" only when `GET /api/founder/rule-waterfall`
answers (null on 404: an older server keeps the label page alone). `RuleWaterfallReview`:

- Header: league name, the line "Started with N candidate trades → M served", the server's
  `started_definition`, "Run 3m ago · 12 teams · generator", the additions note when `added` >
  0, and **Run for this league** (reads "Running…", disabled, with a progress line; polls GET
  every 2 s only while `running`). A failed or unsupported run shows the server's reason.
- **Deviation from §6.1:** while a run is in progress the table stays (with the previous counts,
  or none) instead of being replaced by a spinner row, so notes can be written during a run.
- Table grouped by stage (headers with the stage total), one row per rule in the server's
  order: name, description (two lines, tap the row for the whole description and the note),
  "off today" / "search limit" tags, Removed, Remaining, share of started with a flare bar,
  "Removed x% of the trades that reached it". `not_measured` / `not_run` rows say so in words.
  Zero rows are shown by default, on a quieter surface, with "Hide rules that removed nothing
  (N)". Additions are a separate dashed "Added after the deck was built" line, never in a row.
  Below the table, "Other rules (not in the waterfall)": the pool, liked trades, standing
  offers, the five-card floor, the repeat cap, with notes.
- **Deviation from §6.3 (Notes column):** on a phone the note field lives in the expanded row,
  not a column; a saved note marks the collapsed row ("Note"), an edited one "Unsaved". Each
  expanded row: the catalog's "Worth questioning" line when it has one, a multi-line field
  (2,000-character cap, counter from 1,800), Save (enabled when changed; "Saved" for 2 s; the
  server's error), "Last edited by you · 2h ago", and "N earlier versions" (the history route).
  Drafts live in one page-level map, so text survives scrolling, collapsing and expanding;
  leaving through Player labels, Grading or a navigator removal with unsaved notes asks first.
- Before any run the table renders from the catalog alone with empty counts.
- VoiceOver: each row reads "rule name, removed N, remaining M" (or "not measured", "not run
  for this deck", "not counted yet"), plus ", has a note". Counts use thousands separators.

