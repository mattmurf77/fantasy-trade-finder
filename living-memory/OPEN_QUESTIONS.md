# Open Questions — Fantasy Trade Finder

> **Purpose:** track questions that need information, decision, or external action before work can proceed. File them here, continue around them, check back when answers arrive.
>
> **Read at:** session start (to confirm none have been answered offline). **Write at:** the instant you'd otherwise stop work to ask.

---

## Table of Contents
- [2026-08-19 — Open Items (team review)](#2026-08-19--open-items-team-review)
- [2026-08-19 — Open Items (bake-off outlook lane)](#2026-08-19--open-items-bake-off-outlook-lane)
- [2026-08-19 — Open Items (round-2 pick recalibration)](#2026-08-19--open-items-round-2-pick-recalibration)

- [2026-08-19 — Open Items (pick slot labels)](#2026-08-19--open-items-pick-slot-labels)
- [2026-08-19 — Open Items (pick ladder, rounds 3-4)](#2026-08-19--open-items-pick-ladder-rounds-3-4)
- [2026-08-19 — Open Items (pick-year valuation)](#2026-08-19--open-items-pick-year-valuation)
- [2026-08-19 — Open Items (pick horizon)](#2026-08-19--open-items-pick-horizon)
- [2026-08-15 — Open Items (compressed-board pool prune)](#2026-08-15--open-items-compressed-board-pool-prune)
- [2026-08-14 — Open Items (sleeper propose_trade)](#2026-08-14--open-items-sleeper-propose_trade)
- [2026-06-07 — Open Items (perf-optimization)](#2026-06-07--open-items-perf-optimization)
- [2026-05-21 — Open Items](#2026-05-21--open-items)
- [Closed Questions (kept for cross-reference)](#closed-questions-kept-for-cross-reference)
- [Conventions](#conventions)

---

## 2026-08-19 — Open Items (team review)

### Q-026 — `trade_gen_v2` honors NO positional preferences. Port them, or hold `bakeoff_serve_interleaved` at 0?
**Raised:** 2026-08-19 (feedback #360/#361 build, branch `feat/jon-360-362`)
**The headline is the PRE-EXISTING gap, not the new feature.** `backend/trade_gen_v2.py` reads neither `acquire_positions` nor `trade_away_positions` — **Chasing and Shopping already do not work there today.** It *does* apply `not_interested_ids` and `untouchable_ids`, which makes the omission look deliberate-by-oversight rather than by design, since Avoiding is architecturally the positional twin of `not_interested`.
**Why it is not currently a live defect:** gen-v2 is dark for normal serving. But `trade.bakeoff` is **ON** and the `gen_v2` arm calls the module directly; serving is gated by a `model_config` knob (`bakeoff_serve_interleaved = 0.0`), **not a flag**. Raising that knob above 0 today would silently stop honoring Chasing and Shopping for the served fraction — and, once #360 ships, Avoiding too. Avoiding is worse in kind: Chasing is a preference, Avoiding is a promise.
**Decision taken for now (orchestrator, #360 build):** gen-v2 is **out of scope** for #360. Avoiding must not be the feature that silently repairs an unrelated engine gap. A guardrail note was added wherever the bake-off arm is documented: **do not raise `bakeoff_serve_interleaved` above 0 until gen-v2 honors positional preferences, `not_interested_ids` and `untouchable_ids`.**
**What the operator needs to decide:** port all three preference families into gen-v2 as its own scoped piece of work, or formally accept that the knob stays at 0 until someone does. Either is fine; leaving it undecided is what is dangerous, because the knob is one edit away from a silent regression with no flag flip to audit.
**Status:** OPEN.

### Q-027 — Should `trade.avoid_positions` ship lit, making #360 live on merge?
**Raised:** 2026-08-19 (branch `feat/jon-360-362`, built and green, unmerged)
The scope block ships it **`true`**, arguing the flag is a kill switch rather than a dark launch because the feature was directly user-requested (#360/#361, tester `jonbonjourvi`). That matches precedent — `ranks.import` and `league.picks_always_counted` both graduated at ship for the same reason. Against it: this is a CLAUDE.md **bright-line** change (new schema column, new flag, engine behavior) going live to every TestFlight tester the moment it merges, with **no runtime evidence** behind it — D-056 leaves only the manual TestFlight checklist, which is unrun.
Persistence is deliberately not flag-gated, so shipping dark loses nothing but visibility: the column stores, the API serves, and only the engine read plus the sheet row are gated. Flipping it on later is deploy-free.
**Status:** OPEN — needs an operator yes/no before merge.

### Q-028 — Should the one-tap outlook confirm stop clearing the position lists?
**Raised:** 2026-08-19 (feedback #360 build)
`confirmOutlookMutation` (`mobile/src/screens/TradesScreen.tsx:1047-1058`) writes empty `acquire_positions`, `trade_away_positions` **and now `avoid_positions`** when the user taps **Confirm** on the inferred-outlook banner. So a user who set Avoiding but never declared an outlook loses that set on one tap.
**This is inherited, not introduced** — the two sibling lists have always been cleared by that call, and #360 was built as specced rather than "improved" in passing (surgical-changes rule). It is raised because Avoiding reads as a stronger promise than the other two ("never send me this"), so losing it silently is a worse failure than losing a Chasing hint.
**The fix is ~3 lines if wanted:** drop all three position keys from that mutation's payload. The backend contract already supports it — an omitted position key leaves the stored value **unchanged** (verified over HTTP during the backend build). Strictly better, but it changes existing Chasing/Shopping behavior, which is why it was not done unilaterally.
**Status:** OPEN — needs an operator call; blocks nothing.

### Q-024 — Root `CLAUDE.md` says the `check-*.js` suites "gate nothing yet". `ci.yml` says they do. Which is the contract?
- **Why it matters:** root `CLAUDE.md` §Stack states *"The `mobile/tests/check-*.js` structural suites are `npm run`-only and **gate nothing yet** (open item in NEXT.md)."* But [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)'s `mobile-typecheck` job runs `for f in tests/check-*.js; do echo "── $f"; node "$f" || exit 1; done` — a glob — and its own comment says *"a guard is live in CI the moment the file exists — no npm script needed."* The 42 existing suites therefore **do** gate `main`.
- **Why it is not just a typo to fix in passing:** under [D-056](DECISIONS.md) these suites are the **primary regression evidence for client invariants** — Maestro and the simulator are gone. An agent that believes CLAUDE.md will treat its structural guard as decorative, will not bother proving it fails under sabotage, and may skip writing one at all. It understates the repo's real evidence posture in the one direction that costs coverage.
- **What is unclear (and why an agent should not just edit it):** whether CLAUDE.md is simply stale, or whether the operator considers the glob *incidental* and wants the suites formally declared as a gate (branch-ruleset required check) before the doc claims it. Those lead to different edits. `CLAUDE.md` is the operating contract, so a session should not silently rewrite its own rules.
- **Action to unblock:** operator confirms which is true, then either (a) correct the CLAUDE.md §Stack sentence and close the NEXT.md open item, or (b) make `mobile-typecheck` a required check via the branch ruleset and *then* correct the sentence.
- **Discovered by:** the Team Review planning session, while writing [`scope.md` §3](../docs/feedback/items/357-team-review/scope.md) — see [reconciliation-log.md](../docs/feedback/items/357-team-review/reconciliation-log.md) O-4.
- **Owner:** operator.

### Q-025 — Team Review waivers — **2 of 3 RESOLVED 2026-08-19; waiver 3 still open**
- **Why it matters:** [`docs/feedback/items/357-team-review/scope.md` §6](../docs/feedback/items/357-team-review/scope.md) carries three waivers, and CLAUDE.md's feature gates require waivers to be **surfaced to the operator before build starts** — silence is not a waiver. Building without the yes would violate the gate the scope block exists to enforce.
- **The three:** (1) **forward per-player PPG is CUT** — #357's "here's 6 extra PPG this year" has no license-clean, ready-made source, and the substitute is `starter_impact` slot movement (already ON); (2) **championship odds are refused** — `title_pct` is unrenderable at any week by cross-client invariant, so no waiver can license it and this row exists so the refusal is seen rather than discovered; (3) **retrospective PPG rank ships degraded** — Sleeper-only and empty until week 1, so most users will not see it for their first six weeks with the feature.
- **Resolution so far (operator, 2026-08-19, verbatim *"Forward PPG cut"*):** waiver **(1) RATIFIED** — forward per-player PPG is cut, and #357 is answered by `starter_impact` slot movement instead. Waiver **(2) STANDS** — it was always a notification rather than a choice, and the same day's [D-094](DECISIONS.md) lighting of `outlook.odds` does **not** touch it: `title_pct` remains unrenderable at any week because the model has no demonstrated skill, and Team Review no longer even serializes it.
- **Still open — waiver (3):** retrospective PPG rank is Sleeper-only (`backend/outlook/league_state.py:295–320`) and empty until week 1. The plan ships the card in a degraded state that names the actual reason. This is the one genuine choice left, and it is small: the alternative is hiding the row entirely until it has data.
- **Owner:** operator.

## 2026-08-19 — Open Items (bake-off outlook lane)

### Q-020 — Arm `current`'s divergence cards never label `window`. Real model property, or too small a sample?
- **Why it matters:** [D-086](DECISIONS.md) fixed the deck-size loss caused by unfillable outlook quotas, but left one measurement standing: across all 18 `bakeoff_runs` rows of 2026-08-19, group `current_divergence` produced **0 `window` cards out of 23**. Every other group produced them — `current_consensus` 28.1% (114/405), `gen_v2` 16.2% (16/99) — and `gen_v2` is *also* divergence-basis, generated for the same user, the same declared window and the same week. If real, "the v3 divergence optimizer cannot build outlook-shaped packages" is exactly the kind of finding the bake-off exists to produce, and it would be a genuine generator difference between `trade_optimizer.generate_pair_trades_v3` and `trade_gen_v2`.
- **Why it cannot be called yet:** n = 23. Under `gen_v2`'s own 16.2% rate, P(0 of 23) ≈ 1.4% — suggestive, not conclusive. And the same group averages only **1.3 cards of any lane per run**, so the sample is thin because the *group* is nearly empty, which is a second confound (whatever survives that funnel may not be representative).
- **Plausible non-defect mechanism worth testing first:** divergence cards are built from board disagreement and skew toward like-for-like swaps, whose value-weighted now-lean shift sits below `lane_shift_frac` (0.10) and therefore labels `value` by `classify_lane`'s own rule (`backend/trade_service.py:2206`). That would make 0% correct rather than broken.
- **Needed to close:** either more runs (the group needs roughly 100 divergence cards before 0% is distinguishable from 16%), or a direct offline measurement — replay a seeded league through `generate_pair_trades_v3` and histogram `TradeCard.lane_shift` against the 0.10 threshold. The second is cheap and does not wait on traffic.
- **Owner:** whoever next works the bake-off track; not blocking D-086.

## 2026-08-19 — Open Items (round-2 pick recalibration)

## 2026-08-19 — Open Items (pick horizon)

### Q-022 — Should the manual pick-assignment grid adopt the derived horizon, or is `current + 3` the operator's intent?
- **Why it matters:** [D-091](DECISIONS.md) fixed the Sleeper sync so a league's pristine pick grid spans only the classes it really carries. The **manual assignment grid** (`database.seed_pick_grid`, driven by `_ASSIGNMENT_SEASONS_AHEAD = 3` at `backend/server.py:12202`) still seeds `current_season … current_season + 3` — **four** classes. If a real dynasty league never carries four, then an ESPN league that assigns its picks by hand gets the same unactionable 4th class the Sleeper path just stopped producing, and it reaches the engine through the identical `load_draft_picks` → `_inject_owned_picks` path.
- **Why it was NOT changed unilaterally:** three reasons, and each alone would have been enough. (1) The constant is annotated **"operator decision 3: current + 3"** — overturning a recorded decision needs the operator, per CLAUDE.md. (2) It is wired into the assignment **progress denominator** (`total = rounds × members × (_ASSIGNMENT_SEASONS_AHEAD + 1)`, `backend/server.py:12447`), so changing the seeded span without that line would silently make every league's progress read wrong. (3) These rows are **user-asserted** (`source='user'`, surfaced as "Member-entered — not verified with ESPN"), so a 4th class there is a league's own claim rather than an asset we invented — a different thing from the Sleeper defect.
- **Why it is not urgent:** zero exposure today. Prod holds **no ESPN rows at all** in `draft_picks` (only `sleeper` and `mfl`), so no user is currently seeing an assignment-grid phantom.
- **What would close it:** an operator ruling on one question — *does an off-platform ESPN dynasty rookie draft carry three classes like Sleeper, or four?* If three, the change is `seed_pick_grid` adopting `draft_status.pick_horizon` **plus** the progress-total line, in one commit. If four, record why the platforms differ so the next reader does not "fix" it.
- **Owner:** unassigned; not blocking D-091.
- **OPERATOR RULING 2026-08-19 — neither. Make it user-configurable, and backlog it.** Verbatim: *"The user should be able to decide how many future draft pick years to set in the espn assignment. Not critical for now, backlog item."*
  - This answers the question by rejecting its premise: the count is not a constant to be derived (Sleeper's rolling three) **or** asserted (the recorded `current + 3`) — it is a **league setting the assigning member owns**. That is coherent with why these rows exist at all: they are already `source='user'` and surfaced as "Member-entered — not verified with ESPN", so the span is the league's claim too, not just its contents.
  - **Scope when it is picked up:** a per-league setting (default = today's 4 classes, so no existing league changes), `seed_pick_grid` reading it instead of `_ASSIGNMENT_SEASONS_AHEAD`, **and** the progress denominator at `backend/server.py:12447` deriving from the same value in the same commit — reason (2) above is a real trap, and splitting them makes every league's assignment progress read wrong.
  - **Explicitly NOT adopting `draft_status.pick_horizon` here.** The Sleeper horizon is derived from platform truth; this one is a user's declaration. Keeping them separate is the point — do not "fix" this later by pointing it at the derived horizon.
  - **Status: backlogged, not blocking.** Zero exposure stands (no ESPN rows in prod). Tracked in `NEXT.md`.

## 2026-08-19 — Open Items (pick slot labels)

### Q-023 — Now that a current-year pick's slot is resolvable, should the slot drive its VALUE?
- **What changed to raise this:** [D-090](DECISIONS.md) established that a current-year pick's real draft slot **is** resolvable, from data we already fetch, for Sleeper and for user-assigned ESPN boards. That falsifies the stated premise of the **operator decision of 2026-07-18** quoted in `pick_values.pick_pool_value` — *"we can't yet resolve a pick's slot"* — for the current year only. D-090 deliberately changed the LABEL and nothing else; the pricing question is this one, and it is the operator's.
- **Why it matters, measured (DynastyProcess 2026 slot curve, `1qb_ppr`, against our flat `pick_pool_value(1,0) = 2117`):**

  | slot | value | vs ladder | slot | value | vs ladder |
  |---|---|---|---|---|---|
  | 1.01 | 4867 | **+130 %** | 1.07 | 1680 | −21 % |
  | 1.02 | 4025 | +90 % | 1.08 | 1436 | −32 % |
  | 1.03 | 3343 | +58 % | 1.09 | 1235 | −42 % |
  | 1.04 | 2793 | +32 % | 1.10 | 1070 | −49 % |
  | 1.05 | 2343 | +11 % | 1.11 | 934 | −56 % |
  | 1.06 | 1979 | −7 % | 1.12 | 821 | **−61 %** |

  A 1.01 is worth **5.9×** a 1.12 on the market curve; we price them identically. Rounds 2–4 spread too (a 2.01 is +20 % and a 2.12 −48 %).
- **What it would cost, stated bluntly:** on the operator's own league, **48 of 48** current-year picks change value and **38 of 48** change **tier badge** — a 1.12 would badge `second` rather than `first_1`, a 1.01 `firsts_2`. Tier colour is a cross-client invariant mirrored across five clients ([G-051](GOTCHAS.md)), so this is not a display tweak; it moves engine values, deck composition, evener selection and the calculator.
- **The argument for doing it:** users trade the 1.01 and the 1.12 at wildly different prices, and an engine that calls them equal is wrong in the direction users notice most — the highest-value asset class in the app (firsts are 80.9 % of pick mentions in served cards).
- **The argument for waiting:** it only ever applies to the current year, which today means **3 of 12 leagues**; the other nine hold no current-year picks at all (#228). The whole benefit is seasonal and concentrated.
- **Existing machinery it would use, not new code:** `pick_values._market_round_value` already has the documented extension point — *"NOT DONE, deliberately: pricing a pick at its TRUE slot when the Draft Room has resolved the order… the extension point is `_market_round_value`, which would take an optional `slot` and skip the tercile."* `trade.slot_pricing` / `pick_pricing_mode` (operator decision O2) is the per-user seam it would land behind, so the blast radius is already contained by design.
- **The half-measure worth pricing first:** apply slot pricing only under `market_slots` mode (already per-user, already opt-in), leaving `tier_ladder` — the default everyone is on — untouched. That gets the accuracy for anyone who asks for it and moves nobody else's badges.
- **Needed to close:** an operator ruling. Nothing is blocked on it; D-090 ships complete without it.
- **Owner:** operator (pricing call), then a backend session.

- **OPERATOR RULING 2026-08-19 — YES, the slot should drive price. Sequenced, not simultaneous.** Verbatim: *"Slot should drive price but we can push this live first and then solve for that."*
  - **Direction is decided; the question is now scheduling, not whether.** D-090's labels ship first so the operator can see correct slots in the app before any number moves behind them. This is deliberate: if labels and prices changed in one release and a value looked wrong, there would be no way to tell which half caused it.
  - **The 2026-07-18 decision then falls for the current year.** Its premise is already false (D-090); this ruling retires its substance too — but only for seasons whose order is known. Future years keep the Mid rung, because nothing else is knowable.
  - **What it costs, measured, so it is not a surprise later:** on the operator's league, **48 of 48** current-year pick values and **38 of 48** tier badges move. Tier colour is a five-client invariant (`docs/cross-client-invariants.md`), so this is a bright-line change needing its own scope block, its own evidence and its own TestFlight pass — not a follow-up commit on D-090.
  - **Open sub-questions the implementer must answer, not assume:** does slot pricing apply to every pick or only under the existing opt-in `trade.slot_pricing` / `market_slots` mode? What happens to a league whose order is unknown — Mid rung, or excluded from slot pricing entirely? And does the pick's TIER band follow its slot, or does only its trade value move? A 1.12 badging `second` is defensible; it is also a visible change to every client.
  - **Status:** direction ruled, implementation queued in `NEXT.md`. Not blocking D-090.

## 2026-08-19 — Open Items (pick ladder, rounds 3-4)

### Q-021 — Should `seed_elo_for_value`'s floor compression be re-anchored so 3rds and 4ths reach market-equivalent player ranks?
- **Why it matters:** the surviving half of Q-019. Our Mid 3rd is worth the **165th** asset against a market median of **231.5**, and our Mid 4th the 228th against 296 — errors of 67 and 68 ranks. They are unreachable from the pick ladder because the seed map has almost no resolution down there (54.9 Elo across ranks 200–300; the market-implied Elo for a Mid 4th, ≈1207, sits **inside** the `waivers` band).
- **What it would cost, stated bluntly:** re-anchoring the map moves **every player's seed Elo in the app**, not just picks — tier occupancy, deck composition, matchup selection and every user's board. It is a materially larger blast radius than D-084, which only moved two band edges.
- **The argument for leaving it parked (measured, read-only prod, 2026-08-19):** 3rd-round picks appear in **27 of 2,376 served cards — 1.1 %** — and 4th-round picks in **zero**. Picks are in 55.9 % of cards, but firsts are 80.9 % of pick mentions and 2nds 17.7 %. Deep-pick accuracy buys almost nothing in real decks today.
- **Still unresolved:** is the floor compression a **defect or a deliberate choice**? `seed_elo_for_value`'s docstring explains the *ceiling* anchor (DP 10000 → the 4-firsts rung) and says nothing about the floor. Unchanged from Q-019.
- **Cheaper middle option worth pricing first:** leave the seed map alone and give `third`/`fourth` their own band floors decoupled from the pick rungs — accepting that `_calibration`'s "floor = a rung of the ladder" invariant would then hold only for rounds 1–2, and that `test_league_picks_tier.py::test_current_year_rungs_badge_their_own_round` (D-088) would need retargeting.
- **Owner:** operator (scope call), then a backend session.


## 2026-08-19 — Open Items (pick-year valuation)

### Q-018 — We now price future 1st-round picks above every public market source. Is that the intent?
- **Why it matters:** [D-079](DECISIONS.md) made 1st-round picks hold their value across seasons (a 2029 1st = a 2026 1st = 2117.0), on the operator's explicit direction, and it does cleanly close both reported defects. But the external research done at the same time found **no source that agrees**, and three of four that run the *opposite* way:
  - **DynastyProcess** publishes an explicit rule — future picks are 80 % of the current year's value — applied **flat to every round** (2027→2028: 1st 0.7999, 2nd 0.8010, 3rd 0.8056, 4th 0.8000).
  - **FantasyCalc** (the only source publishing 2029) — 2027→2029 CAGR: 1st **0.80**, 2nd 0.91, 3rd 0.95, 4th 0.98. Their 2029 1st is 64 % of their 2027 1st.
  - **KeepTradeCut** 1QB round means (2027→2028): 1st 0.830, 2nd 0.860, 3rd 0.860, 4th 0.856.
  - **DynastyCalc** Mid rungs: 1st 0.930/0.972, 2nd 0.972/0.971, 3rd 0.987/0.975.
  So the market view is either "all rounds decay the same" or "firsts decay hardest" — never "firsts are flat".
- **The case for shipping it anyway (and why it was):** a flat rate is the **only** rate under which two 1sts of different years are worth the same, and therefore the only one that makes the first-for-first year arbitrage structurally impossible rather than filtered after the fact. That arbitrage was 99 of 2048 served cards. Any rate below 1.0 — including the market's 0.80 — leaves it open. Pricing an asset class above market in your own recommendations is also a coherent product stance if the intent is that users should hold firsts.
- **Two caveats that soften the market evidence** (both worth weighing before treating it as decisive): ratios only mean something on a zero-anchored scale, and an offset fit collapses KTC's apparent round-gradient entirely at `c ≈ 555` (flat 0.834, spread 0.011) — so **KTC's gradient is largely a scale artifact**. And the 2027 rookie class is unusually hyped, which inflates every 2027 number and makes any 2027→2028 step overstate pure time discount.
- **Needed to close:** an operator call, ideally after a TestFlight pass on the new pricing — does "a 2029 1st is worth exactly a 2026 1st" read right in the deck, or does it now overprice far-out firsts in the other direction? Middle options exist and are one config write each: all four rounds on one rate (0.85 keeps today's rounds-2–4 behaviour; 0.80 matches DP) reverts to market alignment but **re-opens the swap defect**; `pick_year_decay_r1` alone at 0.85 is the narrow revert.
- **Owner:** operator (product call), then a backend session if the rate moves.
- **Status:** OPEN — **not blocking**. The shipped default closes the reported defect; this question is about whether the calibration is right, not whether the mechanism is.

---

## 2026-08-15 — Open Items (compressed-board pool prune)

### Q-017 — Should the pool prune quantile-match the two boards instead of rescaling them?
- **Why it matters:** `trade.pool_calibration` ([D-052](DECISIONS.md)) removes a board-wide *offset* with a single multiplicative factor. That is exactly right for the pathological case it was built for, and it is enough to rescue gdubs10 (0 → 5 divergence cards on real prod boards). It is **not** enough for MangoPatti or Bcork, which still yield zero divergence cards and are only covered by the consensus fallback. The reason is structural: a floor-pinned board is closer to `value_u^a` (a < 1) than to `c · value_u`, and no single factor undoes an exponent. Those two members therefore get generic fair-value ideas where a large-enough pool finds real divergence trades (`v3_pool_size = 30` produces 5 divergence cards for each — at 26–102 s per pair, which is why it isn't the fix).
- **The candidate:** map each opponent Elo to its percentile on the opponent's own board, read the user board's Elo at that same percentile, and difference in the user's value space (histogram/quantile matching). Scale-invariant, order-sensitive, magnitude-preserving in one consistent space — strictly more general than the current factor, which it reduces to when the boards differ only by an offset.
- **Why it isn't built:** materially more machinery in a hot path (per-pair sorts of both boards), and it would want its own golden-deck comparison on healthy leagues before anyone trusts it. Not worth building until the operator has run the shipped fix and decided whether "MangoPatti gets consensus cards" is actually a problem in the product.
- **Needed to close:** an operator call on whether divergence cards for heavily-compressed boards are worth the complexity, ideally after `trade.pool_calibration` + `trade.divergence_fallback` have been live long enough to judge the consensus fallback in practice.
- **Owner:** operator (product call), then a backend session.
- **Status:** OPEN — not blocking; the shipped fix already removes the zero-card cliff.

---

## 2026-08-14 — Open Items (sleeper propose_trade)

### Q-016 — What is the element type of Sleeper's `propose_trade(waiver_budget:)`?
- **Why it matters:** `79123a0` (2026-08-13) fixed the *syntax* of the inlined FAAB arg — `json.dumps` emitted quoted object keys, which GraphQL cannot parse. That fix is correct and shipped. But it fixed the encoding of a shape **nobody has ever observed**, and if the shape itself is wrong the first FAAB trade still fails — just with a type error instead of a parse error. Two sources disagree, and neither is a capture of a non-empty value:
  - The 2026-07-02 capture runbook (§C2) asserts `[{sender, receiver, amount}]` — but the captured payload only ever showed `waiver_budget: []`. That object shape is an **inference**. `ProposeTradeRequest.waiver_budget` encodes it anyway.
  - The public `__schema` dump cited in [`../docs/plans/sleeper-pending-trades-feasibility-2026-08-12.md`](../docs/plans/sleeper-pending-trades-feasibility-2026-08-12.md) says `draft_picks` **and** `waiver_budget` are `[String]`. It is demonstrably right about `draft_picks` (matches the live capture field-for-field), which is meaningful corroboration.
  - Likely encoding by symmetry with picks: a comma-string `"<sender>,<receiver>,<amount>"` — **unproven, do not build on it.**
- **Action to unblock:** capture one real FAAB-bearing trade proposal from Sleeper's own web client (same injected-interceptor method as the 2026-07-02 capture, runbook §C2).
- **Workaround in the meantime:** none needed — **non-blocking**. No caller populates `waiver_budget`; the empty case `[]` is valid under every candidate answer and is the only shape production sends. Treat FAAB-over-Sleeper as **unimplemented** rather than merely untested, and do not wire a caller to it until this resolves.
- **Owner:** operator (needs a live capture, not a decision).
- **Asked on:** 2026-08-14.

---

## 2026-06-07 — Open Items (perf-optimization)

> Full detail + defaults: [`../docs/plans/perf-optimization/artifacts/questions-for-user.md`](../docs/plans/perf-optimization/artifacts/questions-for-user.md).
> All six are **non-blocking** — autonomous Wave-2 work proceeds on the documented defaults. Owner: operator. Asked on: 2026-06-07.

### ~~Q-010~~ — Render cold-start mitigation — **RESOLVED 2026-06-08**
- **Resolution:** upgrading to Render Starter dyno ($7/mo, always-on). Complete fix; no code change needed.

### ~~Q-011~~ — Merge audit docs — **RESOLVED 2026-06-08**
- **Resolution:** leave on `audit/perf-optimization` branch. Not merged to main.

### ~~Q-012~~ — Build/ship cadence — **RESOLVED 2026-06-08**
- **Resolution:** EAS build kicked after Wave 2 landed.

### ~~Q-013~~ — INIT-08 backend split — **RESOLVED 2026-06-08 (NOT DOING)**
- **Resolution:** Profiled with real Sleeper data (league `1181674778942836736`). Cold session_init = 519 ms; 95% (494 ms) is Dynasty Process network fetch in `_ensure_universal_pools`, not TradeService construction. Warm server = 25 ms — nothing to split. INIT-08-client (PR #73) is the correct UX fix; backend split not worth doing. See `backend/profile_session_init.py`.

### ~~Q-014~~ — INIT-10 web player payload — **RESOLVED 2026-06-08**
- **Resolution:** Shipped as PR #74. `?view=summary|detail|full` + ETag/Cache-Control added to `/api/players`.

### ~~Q-015~~ — AsyncStorage vs MMKV — **RESOLVED 2026-06-07**
- **Resolution:** AsyncStorage shipped in Wave 2 (PR #71). Upgrade path documented in ADR-001.

---

## 2026-05-21 — Open Items

### ~~Q-001~~ — Cleanup the duplicate SQLite DB — **RESOLVED 2026-06-10**
- **Resolution:** verified `backend/database.py:34` references only `data/trade_finder.db`; root copy (stale since Apr 11) archived to `data/archive/trade_finder.root-legacy-2026-04-11.db`. `.gitignore` already covers `*.db`. Root `CLAUDE.md` convention line updated.

### ~~Q-002~~ — Adopt pytest for backend services — **RESOLVED 2026-06-10 (by the v2 rebuild)**
- **Resolution:** pytest baseline now exists — 121 tests in `backend/tests/` covering trade engine v2/v3 (optimizer, deck ordering, prune equivalence), Elo memoization, DB hygiene, disposition flow, roster profile, narratives, pick values, telemetry. Coverage can deepen, but the "zero automated tests" risk is gone.

### Q-003 — Tiered matchup engine: scope and acceptance criteria
- **Why it matters:** the current matchup generator optimizes globally (tightest Elo cluster across all players). Plan in [`../context.md`](../context.md) is to tier-prioritize: top tier first, then mid, then bench. Open: what's the formal acceptance criterion? "Top-tier rankings converge faster" needs a metric.
- **Action to unblock:** define the metric (e.g. "median Elo std-dev among top 12 players after N swipes drops X%"). Set up A/B harness.
- **Workaround in the meantime:** global matchup engine is fine for general use.
- **Owner:** operator.
- **Asked on:** 2026-05-21.

### Q-004 — DynastyProcess name fuzzy-matching: should this be automated?
- **Why it matters:** `dump_mismatches.py` identifies player name mismatches between DynastyProcess CSV and Sleeper. Manual reconciliation is brittle and gets out-of-date.
- **Action to unblock:** evaluate fuzzy-match libraries (`rapidfuzz`, `Levenshtein`) on the existing mismatch dump. If >90% of mismatches can be auto-resolved, integrate.
- **Workaround in the meantime:** manual reconciliation as mismatches surface.
- **Owner:** operator.
- **Asked on:** 2026-05-21.

### Q-005 — Real-league trade matching: launch criteria — **ACTIVE (operator decision 2026-06-10)**
- **Decision:** operator chose to recruit 1–2 willing league-mates now (pre-season window) to validate the two-sided loop end-to-end on the live v2/v3 engine. Success: a single real mutual match found and surfaced correctly.
- **Supporting work shipped 2026-06-10:** cold-start invite nudge (mobile TradesScreen banner + web coverage-row Invite button → existing invite modal/share sheet) and `/api/admin/engine-metrics` telemetry to watch like/match rates as they join.
- **Owner:** operator (recruiting); engine metrics watched per session.

### ~~Q-006~~ — iPhone app completion order — **RESOLVED (overtaken by events)**
- **Resolution:** full mobile app shipped via EAS/TestFlight (build 14, 2026-06-10) — login, league select, ranking, tiers, trades, matches all live. The question's premise no longer exists.

### Q-007 — Production deployment: Render free tier vs paid?
- **Why it matters:** [`render.yaml`](../render.yaml) exists. Free tier may spin down between requests (cold starts of 30+ seconds). Paid starter (~$7/mo) keeps it warm.
- **Action to unblock:** decide. If launching publicly, paid. If personal-use only, free is fine but document the cold-start UX.
- **Workaround in the meantime:** local dev works fine; production deferred.
- **Owner:** operator.
- **Asked on:** 2026-05-21.

### Q-008 — Browser extension distribution strategy
- **Why it matters:** extension exists in `extension/` but unpublished. Chrome Web Store: $5 one-time + review. Self-hosted as `.crx` is possible but requires sideloading.
- **Action to unblock:** decide: public store (small fee, broader reach, review delay) vs distribute manually (free, friction-y).
- **Workaround in the meantime:** unpacked loading during dev works.
- **Owner:** operator.
- **Asked on:** 2026-05-21.

### Q-009 — Mascot decision (Tommy Tumble vs Ricky Rumble vs other)
- **Why it matters:** branding direction. The mascot concept (running back mid-fumble) is settled; the name isn't. Per [`../context.md`](../context.md): top candidates are "Tommy Tumble" or "Ricky Rumble."
- **Action to unblock:** pick. Maybe poll a few dynasty friends.
- **Workaround in the meantime:** no mascot in current UI.
- **Owner:** operator.
- **Asked on:** 2026-05-21.

---

## Closed Questions (kept for cross-reference)

### Q-019 — Rounds 3/4 badge above their round: do we open the seed map?
- **Resolution (2026-08-19, [D-088](DECISIONS.md)):** **No.** The badge was a wrong inverse, not a price. `GET /api/league/picks` inverted `pool_value` (stored in `elo_to_value` units) with `data_loader.seed_elo_for_value`, which inverts DynastyProcess's raw 0-10000 scale instead. The two maps agree at exactly Elo 1548.0 and diverge either side, inflating every rung below a mid-1st — Mid 3rd 1320 → **1383.5** (+63.4), Mid 4th 1240 → 1339.3 (+99.3) — so 1383.5 cleared D-084's new `second` floor of 1370. The pick's real price is Elo 1320, **45 points inside `third`**. Fixed with `trade_service.value_to_elo`; no seed, band, client mirror or stored price moved. Memo: [docs/reviews/2026-08-19-pick-badge-scale.md](../docs/reviews/2026-08-19-pick-badge-scale.md).
- **The compression half of the question was correct and survives as [Q-021](#q-021--should-seed_elo_for_values-floor-compression-be-re-anchored-so-3rds-and-4ths-reach-market-equivalent-player-ranks):** re-derived on the checked-in snapshot, ranks 200→300 span Elo 1262.9 → 1208.0 — 100 ranks inside **54.9 Elo points**, one eighth the per-rank resolution of ranks 50-100. It does make market-rank alignment for 3rds/4ths unreachable from `GENERIC_PICK_SEEDS`. It was simply not the cause of the badge.
- **Lesson:** the symptom was attributed to the nearest known structural weakness rather than traced. Both facts were true; only one was load-bearing.

### Q-010 — Render cold-start mitigation
- **Resolution (2026-06-08):** Upgraded to Render Starter dyno ($7/mo, always-on). No code change needed.

### Q-011 — Merge audit docs to main
- **Resolution (2026-06-08):** Left on `audit/perf-optimization` branch.

### Q-012 — Build/ship cadence
- **Resolution (2026-06-08):** EAS build kicked after Wave 2.

### Q-013 — INIT-08 backend session_init split
- **Resolution (2026-06-08):** Profiled — not worth doing. Warm server is already 25 ms. Cold-server bottleneck is Dynasty Process network fetch (495 ms), not TradeService build. INIT-08-client (PR #73) is the correct fix. See `backend/profile_session_init.py`.

### Q-014 — INIT-10 web player payload
- **Resolution (2026-06-08):** Shipped as PR #74 (`?view=` projection + ETag caching on `/api/players`).

### Q-015 — AsyncStorage vs MMKV
- **Resolution (2026-06-07):** AsyncStorage shipped in Wave 2 (PR #71). Upgrade path in ADR-001.

---

## Conventions

- **Sequential numbering.** Q-001, Q-002, ... — never reuse a number.
- **Each item has:** why it matters, action to unblock, workaround, owner, ask date.
- **Closed items move to the "Closed" section** with a one-line resolution.
- **Don't delete.** Even resolved questions carry information about why decisions were made.
