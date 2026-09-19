# Competitor-Inspired Feature Ideas — 2026-06-10

Operator ideas sparked by the competitor teardowns ([DynastyGM](../competitor-teardown-dynastygm.md), [DynastyDealer](../competitor-teardown-dynastydealer.md), [web tools](../competitor-teardown-web-tools.md)). Status: captured, not yet scheduled. Engine references are to `backend/trade_service.py` config keys as of branch `trade-engine-v2`.

---

## 1. "Swap Player" on suggested trades (counter / revise)

**Idea (operator):** On a suggested trade card, a swap-player button lets the user counter or slightly revise the offer. Clicking a player in the trade shows the rest of that roster, **highlighting players in similar value proximity** to the one being replaced.

**Competitor precedent:** Dynasty Daddy's "Even Out Trade" recommends balancing players filtered to the two teams in the trade; DynastyDealer's offer inbox has a MODIFY action on real offers.

**Engine mapping:**
- Candidate list = roster of the same team, ranked by |Δ adjusted value| vs the removed player (use the same user/opponent valuation the engine scored the trade with — including outlook blend and positional multipliers — not raw consensus, so swaps preserve the mutual-gain math).
- Re-score the revised trade through the existing scoring path so the card's fairness/mismatch read updates live.
- Surfacing: value-proximity highlight band (e.g. ±15%, reuse `sweetener_band`-style config rather than a new magic number).
- New API surface: likely a `POST /api/trades/rescore` (take a trade payload, return scores) + a swap-candidates endpoint or client-side filter over already-fetched rosters.

**Why it matters:** turns suggestions from take-it-or-leave-it cards into a negotiation starting point; also generates strong preference signal (swap events are richer labels than swipes for the deferred acceptance model).

---

## 2. Adjustable / removable fairness threshold + "you could ask for more"

**Idea (operator):** Web UX already exposes a fairness-threshold adjustment (`fairness_threshold` param on the trade-job API). Add the ability to **remove the threshold entirely**. Synergy with #1: when a trade is a good fit for both teams *and* headroom exists, tell the user — "this trade works for both sides, but honestly you could also ask for one of these players and still get it through."

**Competitor precedent:** DTC explicitly disclaims fairness verdicts ("prices are determined by you and your league mates"); Dynasty Daddy quantifies the gap ("add a player with 1,478 value to even trade"); DynastyDealer paywalls 'fairness' as the product.

**Engine mapping:**
- Threshold removal = allow `fairness_threshold` → 0 / None so the gate degrades to pure mismatch ranking (`mismatch_weight` already dominates at 0.70; fairness is only 0.30 of score). Check the range-overlap gate (`trade_service.py:333` — degrades to point gate) handles the disabled case.
- "Ask for more" is the **existing sweetener mechanism inverted**: sweeteners currently fill a fairness *shortfall* (`sweetener_band` 0.15, `sweetener_max_cards` 2); this reuses the same candidate search to surface *surplus* headroom on the user's side. Likely a small extension: compute headroom = how far the trade sits inside the acceptance band, list opponent players whose value ≤ headroom (filtered by user position needs).
- Copy matters: frame as "room to negotiate," not "you're losing" — the trade is already mutual-gain.

**Why it matters:** the fairness gate was a v2 watch item (tune via trade_impressions); making it user-adjustable converts a tuning liability into agency, and "ask for more" makes FTF feel like an agent on the user's side rather than a neutral referee — a positioning no competitor occupies (they referee; FTF can advocate).

---

## 3. Power-ranking tiers (contend/rebuild) as a trade-engine multiplier — for BOTH teams

**Idea (operator):** Tiers are a must for useful suggestions: a rebuilder doesn't need an aging veteran even if their rankings say they value him. Another multiplier for the engine — and this was the original intent of the first-run config on the web find-a-trade flow.

**Competitor precedent:** Dynasty Daddy tiers every team (Contender / Frisky / Rebuilding) and simulates post-trade ranks; Dynasty Dealmaker detects "rebuilding phases and competitive windows" to pick realistic partners; DynastyDealer surfaces avg age/experience per league team.

**Engine mapping — the gap is the *opponent* side:**
- Already built for the user: `team_outlook` pref → `outlook_alpha_*` now/future value blend (championship 1.00 / contender 0.75 / not_sure 0.50 / rebuilder 0.25) behind `trade.outlook_blend` (default ON). Sourced from user prefs in `server.py:1494`.
- Opponents currently default to the not_sure 50/50 blend — so the engine can offer an aging vet to a rebuilding opponent and call it mutual gain.
- Fix: **auto-classify every league team's outlook** from observables (roster avg age vs `vet_age`/`youth_age` thresholds, value concentration in 27+ players, pick-capital share, league record/standing) and run the opponent's valuation through their inferred alpha. Keep user self-declaration as an override of the inference for their own team.
- Display tier chips on opponents in the UI (steal the Contender/Frisky/Rebuilding personality framing) so users understand *why* a trade targets that team.

**Why it matters:** acceptance realism. The engine's mutual-gain claim is only credible if "gain" is window-aware on both sides. Also likely the cheapest big win — the alpha-blend machinery already exists; this is an inference function + applying an existing multiplier to the other side.

---

## Suggested sequencing

3 → 2 → 1. (#3 improves every suggestion silently and reuses existing machinery; #2 is mostly config/UX plus an inverted sweetener pass; #1 is the largest new surface — endpoint + interactive card UI — and benefits from #3's opponent outlooks being in place so swap candidates are window-aware.)
