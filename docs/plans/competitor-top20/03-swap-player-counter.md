# 3. Swap-player counter builder

> Tier 1 · #3 · NEW · Effort L · Sources: OP (idea 1) / DD ("Even Out Trade") / DDr (offer MODIFY)

## Summary

On any suggested trade card, tap a player to swap them out: a sheet shows the rest of that player's roster with candidates in a similar **adjusted-value band** highlighted, the user picks a replacement, and the card re-scores live — fairness, mutual gain, and composite all updating through the same math that generated the card. Dynasty Daddy's "Even Out Trade" and DynastyDealer's offer MODIFY are partial precedents; neither preserves a mutual-gain guarantee through the edit. The critical constraint (operator-flagged): proximity highlighting must use the engine's adjusted values — confidence-shrunk personal Elo through `elo_to_value`, the outlook blend (`outlook_blend_mult`), and each side's own value space — **not raw consensus**, or swaps silently break the mutual-gain math the card was built on.

This is the largest build of the five: it requires factoring the scoring math out of the generation loop into a reusable `score_trade()` function, a new synchronous `POST /api/trades/rescore` endpoint (deliberately designed for reuse by the extension overlay #19 and the open/team-vs-team calculators #27/#28), and interactive card UI on both clients. The payoff is double: take-it-or-leave-it cards become negotiation starting points, and swap events are the richest preference labels FTF could collect — "removed X from give" and "added Y to receive" are explicit, asset-level statements no swipe can match.

## PRD

### Problem & user story

> As a user who likes 80% of a suggested trade, I want to swap the one player I disagree about and see instantly whether the deal still works, instead of passing on the whole card.

Today a card is atomic: like or pass. Near-miss cards — right partner, right shape, one wrong asset — generate passes that read as full rejections, polluting both the Thompson-sampling signal and the user's sense that the engine "gets" them.

### Goals / Non-goals

**Goals**
- Tap any player on a card (either side) → roster sheet for that side's team, value-proximate candidates highlighted.
- Swap → card re-scores live (fairness, both surpluses, composite, gate verdicts) with no full regeneration.
- Rescore endpoint generic enough for #19/#27/#28 (score an arbitrary two-team asset bundle).
- Every swap logged as preference signal.

**Non-goals**
- No multi-swap undo stack in v1 (one swap at a time; re-tap to swap again).
- No pick or FAAB assets (consistent with the sweetener pass: "Sweeteners are PLAYERS ONLY" — picks aren't on `LeagueMember.roster` in this code path).
- No editing the counterparty (changing teams = new generation, not a swap).
- Swapped cards don't re-enter other users' decks.

### Functional requirements

- FR1: Tapping a player on a card opens that side's full roster, sorted by |Δ adjusted value| vs the removed player, with candidates inside the proximity band visually highlighted.
- FR2: Proximity band = relative band around the removed player's adjusted value in **the owning side's value space** (give side: `user_value` — shrunk Elo + outlook blend; receive side: `elo_to_value(opp_elo[pid])`). Band width from new config key `swap_band` (default `0.15`, mirroring `sweetener_band` rather than inventing a new magic number).
- FR3: Confirming a swap calls `POST /api/trades/rescore`; the card updates in place with new `fairness_score`, `mismatch_score`, `composite_score`, and a gate report (mutual-gain pass/fail per side, fairness gate, lineup feasibility).
- FR4: A swapped trade that now fails a gate renders degraded-but-honest ("This version no longer clears mutual gain for them") — never hidden, never blocked.
- FR5: Swiping like on a swapped card persists the **edited** asset sets through the existing swipe path (the FB-46 card-context echo already carries `give_player_ids`/`receive_player_ids`, so `_reconstruct_swipe_card` handles unknown trade ids).
- FR6: Every confirmed swap writes a `trade_swap_events` row (removed id, added id, side, pre/post scores).
- FR7: Players in the trade already, and the user's untouchables (#2), are excluded from give-side swap-in candidates.
- FR8: Rescore is stateless with respect to the deck: it accepts explicit asset arrays and a `target_user_id`, so it works for cards, the extension overlay, and calculators alike.

### UX notes

- **Mobile** (`mobile/src/screens/TradesScreen.tsx`, `mobile/src/components/TradeCard.tsx`): tap player chip → bottom sheet, roster grouped "Similar value" / "Everyone else"; highlighted band rows show the adjusted-value delta ("−180" / "+240"). After swap, scores animate to new values; gate failures show as amber banner.
- **Web** (`web/js/app.js` trade deck): same interaction as a modal; keep the existing fairness meter as the live-updating element.
- Show value deltas in relative terms ("about even", "a reach for them") rather than raw value units, consistent with how cards avoid false precision.
- Latency budget: rescore is O(package size), no enumeration — target <300ms server time; optimistic UI not needed.

### Success metrics

- Swap usage: ≥10% of viewed cards get at least one swap attempt within 4 weeks.
- Like-rate on swapped cards exceeds like-rate on unswapped cards (the feature converts near-misses).
- Swap-event label volume (target: an order of magnitude past the ~20 swipe decisions the acceptance model deferral cited).
- p95 rescore latency <500ms on Render.

### Acceptance criteria

- [ ] `score_trade()` returns byte-identical fairness/surplus/composite numbers to `_consider` for the same inputs (regression test against generated cards).
- [ ] Candidate highlighting uses adjusted values: a player whose consensus value is close but outlook-blended value is far does NOT highlight (explicit test).
- [ ] Rescore reports all three gate outcomes (mutual gain per side, fairness/range overlap, v3 lineup feasibility).
- [ ] Swapped-card like persists edited asset sets to `trade_decisions` and match detection still works.
- [ ] `trade_swap_events` rows written; visible in `/api/admin/engine-metrics` (#84).
- [ ] Flag off → no UI affordance, endpoint returns 404.
- [ ] `docs/api-reference.md`, `docs/data-dictionary.md`, `docs/config-reference.md`, `docs/architecture.md` updated.

## HLD

### Components touched

`backend/trade_service.py` (extract `score_trade()` from `_consider`/`_surpluses` math), `backend/trade_optimizer.py` (share `_both_feasible` feasibility check), `backend/server.py` (rescore route + swap-event logging), `backend/database.py` (new table), `mobile/src/api/trades.ts`, `TradeCard.tsx`, `TradesScreen.tsx`, `web/js/app.js`.

### Data flow

Card tap → client already holds both rosters? No — client fetches `GET /api/trades/swap-candidates` (or derives from an enriched rescore response; see open questions) → server computes adjusted values from the session's live objects (`sess["trade_svc"]`, `sess["league"]`, opponent `elo_ratings`, user shrunk Elo + outlook from `load_league_preference`) → returns ranked candidates + band membership. Swap confirm → `POST /api/trades/rescore` → `score_trade()` over the edited sets → response updates card → `trade_swap_events` insert. Like → existing `/api/trades/swipe` with FB-46 context fields.

### Flags & config interplay

- New flag `trade.swap_builder` (default `false`; attr `FLAGS.trade_swap_builder`).
- New config keys: `swap_band` (0.15), `swap_max_highlighted` (proposal 6) in `_DEFAULT_CFG` + `model_config` seed.
- Honors `trade.marginal_value`: `score_trade()` must branch on `FLAGS.trade_marginal_value` exactly as `_surpluses` does (marginal values vs raw), or rescored numbers diverge from generated ones.
- Honors `trade.outlook_blend` for the user-side value map; opponent side benefits automatically once #1 (opponent outlook classification) lands.
- Respects #2 untouchables in give-side candidates.

## LLD

### Engine changes

1. **Extract `score_trade(give_ids, recv_ids, *, user_value, opp_value_fn, seed_value, confidence, fairness_threshold, scoring_format, user_roster, opp_roster, players) -> TradeScore`** in `trade_service.py`. Implementation is a refactor, not new math: package values via `package_value_v2` with the trade-wide max in each side's own space, waiver-slot cost (`waiver_slot_cost`) on the side receiving more players, per-side surpluses vs `min_side_surplus`/`min_side_surplus_marginal`, consensus fairness + range-overlap gate (the `_fairness` closure logic with `_value_uncertainty`), harmonic mean (`_harmonic_mean`), composite `mismatch_weight·min(hm, mutual_gain_cap)/mutual_gain_cap + fairness_weight·fairness`, tier multiplier. `_consider` (v2) and `_surpluses`/`_composite` (v3) are rewritten to call it, guaranteeing rescore ≡ generation. The v3 lineup-feasibility check (`_both_feasible`, `_pos_counts`, `_feasible_after` in `trade_optimizer.py`) is invoked when `FLAGS.trade_engine_v3` so the gate report matches what generation enforced.
2. **Swap candidates**: for removed player `r` on side S with adjusted value `v_r` in S's space, candidates = S's roster minus in-trade ids (minus untouchables on give side), `in_band = |v_c − v_r| ≤ swap_band · v_r`, sorted by |Δ|.

### API changes

```
POST /api/trades/rescore                       (session auth; also reused by #19/#27/#28)
{
  "league_id": "...",
  "target_user_id": "...",
  "give_player_ids":    ["4046", "8154"],
  "receive_player_ids": ["7564"],
  "context": {"trade_id": "ab12cd34",          // optional — links swap telemetry
              "swap": {"removed": "8154", "added": "9221", "side": "give"}}
}
→ {
  "scores": {"fairness_score": 0.81, "mismatch_score": 412.0, "composite_score": 0.642},
  "gates":  {"user_surplus": 230.4, "opp_surplus": 188.9,
             "mutual_gain": true, "fairness": true, "feasible": true},
  "verdict": "works_for_both" | "fails_their_side" | "fails_your_side" | "unfair" | "infeasible"
}

GET /api/trades/swap-candidates?league_id=...&target_user_id=...&side=give|receive&replace=<pid>&exclude=<pids>
→ {"band": 0.15, "candidates": [{"player": {...}, "adj_value_delta": -180.2, "in_band": true}, ...]}
```

For #27 (open calculator, no league context) the endpoint later accepts a consensus-only mode (`target_user_id` absent → seed values both sides); design the handler so league objects are optional.

### Schema changes

```python
trade_swap_events_table = Table("trade_swap_events", metadata,
    Column("id",                Integer, primary_key=True, autoincrement=True),
    Column("user_id",           String,  nullable=False),
    Column("league_id",         String,  nullable=False),
    Column("trade_id",          String),                  # source card, when present
    Column("target_user_id",    String),
    Column("side",              String,  nullable=False), # 'give' | 'receive'
    Column("removed_player_id", String,  nullable=False),
    Column("added_player_id",   String,  nullable=False),
    Column("pre_composite",     Float),
    Column("post_composite",    Float),
    Column("created_at",        String),
)
Index("ix_trade_swap_events_user_league",
      trade_swap_events_table.c.user_id, trade_swap_events_table.c.league_id)
```

Interpretation for #65 labels: `removed` from give ≈ "wouldn't trade him" (untouchable hint → #2 prompt); `added` to receive ≈ target hint.

### Client changes

- `mobile/src/api/trades.ts`: `rescoreTrade()`, `getSwapCandidates()` + types.
- `mobile/src/components/TradeCard.tsx`: tappable player chips, score re-render, gate banner; `TradesScreen.tsx`: swap bottom sheet; swiping a modified card sends edited arrays (already in the FB-46 echo payload).
- `web/js/app.js`: swap modal + live card update in the trade deck section.
- `extension/`: consumes `/api/trades/rescore` later under #19 — no work now beyond keeping the endpoint extension-auth-compatible (bearer token path).

### Rollout

Flag `trade.swap_builder`, default `false`. Phase A: backend (`score_trade()` refactor + endpoints) behind flag, regression-tested against generation. Phase B: web UI (faster iteration). Phase C: mobile. The refactor itself ships flag-independent (pure extraction, byte-identical outputs verified) so #19/#27/#28 can build on it regardless.

### Open questions

1. One endpoint or two? Swap candidates could ride along in an enriched rescore response to save a round trip; kept separate above because #19/#27 want rescore without candidates. Decide on payload size data.
2. Receive-side band uses the opponent's raw-Elo value space; should it instead use *their* inferred-outlook blend once #1 ships? Yes in principle (window-aware candidates) — confirm sequencing with #1.
3. Does a swapped card replace the original in the in-memory deck (`_trade_cards`) or coexist with a new `trade_id`? Coexist proposal: new id via the FB-46 reconstruction path, original stays for impression bookkeeping. (verify `record_decision` behavior with duplicate asset-set keys)
4. Rate limiting: rescore is cheap but unauthenticated-calculator reuse (#27) will need a budget — design now or at #27?

## Dependencies & sequencing

- **After #1** (opponent outlook auto-classification) ideally: swap candidates and rescore become window-aware on the opponent side for free. Functional without it (opponent priced at raw personal Elo, same as generation today).
- **After/with #2**: untouchables excluded from give-side candidates; swap events feed the same preference pipeline.
- **Enables #19** (extension overlay), **#27** (open calculator), **#28** (team-vs-team calc) — all consume `/api/trades/rescore`. Also **#11** (offer analyzer) scores received offers through the same function.
- **Pairs with #6** (verdict banner): the rescore `verdict` field is the same vocabulary; ship copy together.
- Backlog wave: Wave 3, after Wave 1 engine-correctness items.
