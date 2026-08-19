# Open Questions — Fantasy Trade Finder

> **Purpose:** track questions that need information, decision, or external action before work can proceed. File them here, continue around them, check back when answers arrive.
>
> **Read at:** session start (to confirm none have been answered offline). **Write at:** the instant you'd otherwise stop work to ask.

---

## Table of Contents
- [2026-08-19 — Open Items (pick ladder, rounds 3-4)](#2026-08-19--open-items-pick-ladder-rounds-3-4)
- [2026-08-19 — Open Items (pick-year valuation)](#2026-08-19--open-items-pick-year-valuation)
- [2026-08-15 — Open Items (compressed-board pool prune)](#2026-08-15--open-items-compressed-board-pool-prune)
- [2026-08-14 — Open Items (sleeper propose_trade)](#2026-08-14--open-items-sleeper-propose_trade)
- [2026-06-07 — Open Items (perf-optimization)](#2026-06-07--open-items-perf-optimization)
- [2026-05-21 — Open Items](#2026-05-21--open-items)
- [Closed Questions (kept for cross-reference)](#closed-questions-kept-for-cross-reference)
- [Conventions](#conventions)

---

## 2026-08-19 — Open Items (pick ladder, rounds 3-4)

### Q-020 — Should `seed_elo_for_value`'s floor compression be re-anchored so 3rds and 4ths reach market-equivalent player ranks?
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
- **The compression half of the question was correct and survives as [Q-020](#q-020--should-seed_elo_for_values-floor-compression-be-re-anchored-so-3rds-and-4ths-reach-market-equivalent-player-ranks):** re-derived on the checked-in snapshot, ranks 200→300 span Elo 1262.9 → 1208.0 — 100 ranks inside **54.9 Elo points**, one eighth the per-rank resolution of ranks 50-100. It does make market-rank alignment for 3rds/4ths unreachable from `GENERIC_PICK_SEEDS`. It was simply not the cause of the badge.
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
