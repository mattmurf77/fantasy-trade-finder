# 4. Fairness threshold control + "ask for more"

> Tier 1 · #4 · ENH · Effort M · Sources: OP (idea 2) / DTC (anti-fairness framing) / DD (gap quantification) / DDr (fairness-as-product)

## Summary

Two halves. First, extend the existing per-job `fairness_threshold` control (already a `POST /api/trades/generate` body param with a web slider — `fairness-slider` / `fairness-equal-chk` in `web/js/app.js`) to allow **disabling fairness entirely**: threshold → 0 degrades the range-overlap gate to a no-op and ranking to mismatch-dominated scoring (`mismatch_weight` 0.70 vs `fairness_weight` 0.30 — fairness keeps a residual say in ordering but stops vetoing). Competitors validate both poles: DTC explicitly refuses to referee fairness ("prices are determined by you and your league mates"), DynastyDealer sells fairness as the product. FTF's position: fairness is the *user's* dial, not the app's verdict.

Second, the differentiating half: **"ask for more."** The v3 sweetener pass (`_try_sweeten` in `trade_optimizer.py`, config `sweetener_band` 0.15 / `sweetener_max_cards` 2) currently rescues near-miss trades by adding a cheap player from the under-paying side. Invert it: when a trade clears all gates *with headroom*, list opponent players the user could **also request** while the deal still clears — surfaced with advocate copy ("room to negotiate"), never "you're losing" (the trade is already mutual-gain; the framing is leverage, not deficit). No competitor occupies the agent-on-your-side position; this is the cheapest feature that makes it tangible.

## PRD

### Problem & user story

> As a user who knows my league mates trade loose, I want to drop or remove the fairness gate so I see aggressive deals — and when a suggested deal has slack in it, I want FTF to tell me what else I could ask for instead of leaving value on the table.

The fairness gate was a v2 watch item (tune via `trade_impressions`); making it user-adjustable converts a tuning liability into user agency.

### Goals / Non-goals

**Goals**
- `fairness_threshold = 0` ("off") accepted end-to-end: API validation, gate degrade, job-cache freshness, web + mobile controls.
- Verified clean degrade: gate-off changes *which* trades surface, never crashes or distorts scoring.
- "Ask for more" annotations on qualifying cards: up to N opponent players the user could additionally request with each one's effect on the deal.
- Advocate tone codified in copy and in `docs/glossary.md` ("headroom", "ask").

**Non-goals**
- No per-league persistent fairness preference (web already persists per-league in `localStorage` via `_fairnessStorageKey()`; server-side persistence is #8-adjacent and out of scope).
- No change to default `0.75` (or `0.50` pinned) — defaults stay tuned.
- "Ask for more" never *auto-adds* the player to the card (that's the user's call; one-tap add lands with #3's swap machinery).
- Not the verdict banner itself (#6) — this supplies the data #6 renders.

### Functional requirements

- FR1: `POST /api/trades/generate` accepts `fairness_threshold: 0` (and `null` → coerced to `0.0`); values clamped to `[0, 1]` with out-of-range rejected 400 (currently `float(body.get(...))` with no validation — add it).
- FR2: With threshold 0, the v2 `_fairness` gate and v3 `_fairness_v3` never return `None` for fairness reasons: the gate condition `not overlap and fairness < fairness_threshold` is unreachable since `fairness ∈ [0,1] ≥ 0`. Fairness is still computed and still contributes `fairness_weight · fairness` to the composite. **(verify with a unit test on both paths; also verify `_fairness_v3` returns a well-formed `ratio` for the near-miss tuple when gating is impossible)**
- FR3: With threshold 0, the sweetener near-miss window `fairness_threshold - sweetener_band ≤ ratio < fairness_threshold` is empty → sweetener pass naturally idle (no special-casing).
- FR4: Mutual-gain gates (`min_side_surplus` / `min_side_surplus_marginal`) remain active regardless — "fairness off" does not mean "bad trades on"; both sides still must gain.
- FR5: "Ask for more": for each surfaced card, compute additional-request candidates — opponent-roster players outside the trade whose addition to the user's receive side keeps (a) consensus ratio ≥ the job's fairness_threshold, (b) both surpluses ≥ the gate (opponent surplus is the binding constraint), (c) lineup feasibility (v3), (d) the Elo-gap guard. Rank by user value, prefer `position_needs` matches, cap at `ask_more_max_candidates`.
- FR6: Annotation serialized only when non-empty (the `likes_you`/`sweetener` serialization pattern keeps ordinary payloads byte-identical).
- FR7: Copy never frames the base trade negatively. Approved register: "Room to negotiate — this deal still works if you also ask for {player}." Banned register: "you're losing", "they win this trade".
- FR8: Cache freshness: `_trade_job_is_fresh` already compares thresholds with ±0.01 wiggle — confirm `0` vs absent (`or 0` coalescing in the comparison) doesn't false-hit a cached 0.75 job. **(verify: `job.get("fairness_threshold") or 0` treats a stored 0.0 as 0 — correct by accident; add explicit test)**

### UX notes

- **Web**: extend the existing fairness slider with an "Off" stop at the far end (or repurpose `fairness-equal-chk` semantics); helper text updates to "showing all mutual-gain trades, regardless of balance". Ask-for-more renders as a card footer: "💬 Room to negotiate: you could also ask for {A} or {B}".
- **Mobile** (`TradesScreen.tsx` generation options + `TradeCard.tsx`): fairness control gains an Off state; ask-for-more is a collapsed row on the card, expanding to the candidate list. With #3 shipped, tapping a candidate adds it via the rescore flow.
- **Extension** (#19, later): ask-for-more candidates are the overlay's negotiation hints — keep the payload self-contained.
- Threshold-off decks may skew lopsided; pair with #6's verdict banner so each card still states its balance plainly.

### Success metrics

- % of generation jobs run with non-default threshold (agency uptake); % at 0.
- Ask-for-more impression→expand rate; expanded→(eventual) like rate vs baseline cards.
- No regression in like-rate at default threshold (guard metric: annotations shouldn't make fair cards feel worse).
- Slider position distribution captured in `/api/admin/engine-metrics` (#84 explicitly lists fairness-slider positions + ask-for-more uptake).

### Acceptance criteria

- [ ] Unit tests: threshold 0 on v2 and v3 paths yields gate-never-fires, fairness still in composite, sweeteners idle.
- [ ] API rejects threshold &lt; 0 or &gt; 1; accepts 0 and null.
- [ ] Cache test: 0.75-job not returned for a 0-request and vice versa.
- [ ] Ask-for-more candidates each independently re-verify all gates (property test: adding the candidate then calling #3's `score_trade()` reports all gates pass).
- [ ] Copy review: no deficit framing anywhere (web, mobile, push later).
- [ ] Flag off → payloads byte-identical.
- [ ] `docs/api-reference.md`, `docs/config-reference.md`, `docs/cross-client-invariants.md` (threshold range + copy register are cross-client), `docs/glossary.md` updated.

## HLD

### Components touched

`backend/server.py` (param validation, annotation plumbing), `backend/trade_service.py` (verification only on the gate; ask-for-more helper), `backend/trade_optimizer.py` (`_try_sweeten` sibling: `_find_asks`), `web/js/app.js` + `web/index.html` (slider Off stop, card footer), `mobile/src/screens/TradesScreen.tsx`, `mobile/src/components/TradeCard.tsx`, `mobile/src/api/trades.ts`.

### Data flow

Threshold flows unchanged: client → `/api/trades/generate` body → `_kickoff_trade_job` → `_run_trade_job` → `generate_trades(..., fairness_threshold=...)`. Ask-for-more runs as a post-pass in the generation worker after cards are final (post dedup/diversity, pre `log_trade_impressions` so impressions can record that an ask was shown): for each card, `_find_asks()` walks the opponent roster sorted by user value desc, re-checking gates per candidate; results attach to the card and serialize via `trade_card_to_dict`.

### Flags & config interplay

- New flag `trade.ask_for_more` (default `false`). The threshold range extension ships **without** a flag — it's parameter plumbing on an existing user control; clients gate the new "Off" UI on the flag too so the whole feature lights up together. (Cheap option: gate both halves on the one flag; decide at implementation.)
- New config keys in `_DEFAULT_CFG` + `model_config` seed: `ask_more_max_candidates` (3.0), `ask_more_min_value` (proposal 0.0 — floor to skip dust players; tune later).
- Interplay with `sweetener_band`/`sweetener_max_cards`: shared concept, opposite direction; no shared state. A card can theoretically carry both a `sweetener` (it was rescued) and asks — mutually exclusive in practice since a rescued card sits at the threshold with no headroom; assert rather than assume. **(verify)**
- #2 untouchables: asks add to the user's *receive* side, so untouchables are unaffected.
- `trade.marginal_value`: ask validation must use the same marginal/raw branch as generation (via #3's `score_trade()` once it exists; until then a local `_surpluses` call).

## LLD

### Engine changes

1. **Validation** (`server.py` `generate_trades` route): replace the bare `float(...)` at the `fairness_threshold` read with parse + clamp/400; treat `None` as `0.0` only when explicitly present, else default (`0.50` pinned / `0.75` otherwise — unchanged).
2. **Gate verification** (no code change expected): v2 `_fairness` returns `None` only on `not overlap and fairness < fairness_threshold` (trade_service.py); with threshold 0.0 this is unreachable. Same for `_fairness_v3` and the near-miss window in `generate_pair_trades_v3`. Deliverable is tests, not edits.
3. **`_find_asks(card, opp_roster, ...)`** in `trade_optimizer.py` (sibling of `_try_sweeten`, reusing its closures: `surpluses`, `gap_ok`, `both_feasible`, `_consensus_packages`): candidates = opponent roster − in-trade ids, sorted by user value desc (best ask first — the inverse of sweetener's cheapest-first), keep while all gates pass, stop at `ask_more_max_candidates`. Position-needs matches (from the user's `analyze_roster_strengths` profile, already computed in the orchestration loop) sort first within equal-value bands.
4. **Card field**: `TradeCard.asks: Optional[list[dict]] = None`, entries `{"player_id": pid, "post_ratio": 0.78, "needs_match": true}`.

### API changes

No new routes. Payload delta on `/api/trades/generate`, `/api/trades/status`, `/api/trades` cards (via `trade_card_to_dict`):

```json
{
  "...": "existing card fields",
  "asks": [
    {"player": {"id": "9221", "name": "...", "position": "WR"},
     "post_ratio": 0.78, "needs_match": true}
  ]
}
```

Serialized only when the flag is on and the list is non-empty. Request delta: `fairness_threshold` documented range becomes `0–1` with `0 = off` (api-reference update; the `generate_trades` docstring in `trade_service.py` currently documents 0.5–1.0).

### Schema changes

None required. Telemetry rides existing rails: `log_trade_impressions` cards already snapshot scores; add `had_asks` is **not** worth a column — record ask-shown/ask-expanded via `record_event` (`user_events`) with event types `ask_more_shown` / `ask_more_expanded`, which #84's engine-metrics expansion can aggregate.

### Client changes

- `web/js/app.js`: slider Off stop + persisted per-league via existing `_fairnessStorageKey()`; ask footer on cards.
- `mobile/src/api/trades.ts`: `asks` on the card type; `TradeCard.tsx` collapsed ask row; `TradesScreen.tsx` fairness Off state in generation options.
- Copy strings centralized (both clients) so the advocate register is reviewable in one place each.

### Rollout

Flag `trade.ask_for_more`, default `false`. Order: validation + tests → `_find_asks` dark → web UI → mobile. Watch `opponents`-loop latency: asks add one roster walk per surfaced card (~30 cards × ~25 players, each a cheap gate re-check) — budget within the existing job deadline; if tight, compute asks only for top-`N` deck positions. Ship with #6 (verdict banner) per the backlog ("Pairs with #4; ship together").

### Open questions

1. One flag or two for threshold-off vs asks? (Single flag is simpler; threshold-off alone is also independently shippable.)
2. Should threshold-off be available in the pinned-player flow (which already defaults looser at 0.50)? No reason against — confirm UX doesn't double-expose sliders.
3. Asks against *which* threshold when the job ran at 0? Proposal: validate asks at the default 0.75 anyway, so asks remain meaningful when the gate is off. Needs a product call.
4. Mobile fairness control parity: does mobile currently expose the threshold at all? **(verify `TradesScreen.tsx` — web has the slider; mobile may only have defaults)** If absent, mobile scope grows by the base slider.
5. Once #1 ships, opponent-side surplus in ask validation becomes window-aware — re-tune `ask_more_max_candidates` then?

## Dependencies & sequencing

- **Ships with #6** (verdict banner): asks are the "you could ask for a sweetener" half of #6's copy; same payload reviews.
- **Feeds #3** (swap builder): one-tap "add this ask" uses `/api/trades/rescore`; until #3 lands, asks are display-only.
- **Feeds #19** (extension overlay): asks render as negotiation hints on the Sleeper trade screen.
- **#7** (rejection reasons): "Unfair to me" rejections are the calibration signal for whether users want the gate looser or tighter — instrument both, tune together.
- **#84**: engine-metrics expansion explicitly includes fairness-slider positions and ask-for-more uptake.
- Wave 2 in the backlog sequencing (after Wave 1 engine-correctness items, alongside #2/#7/#13).
