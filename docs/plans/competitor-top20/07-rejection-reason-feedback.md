# 7. Rejection-reason feedback on swipes

> Tier 1 · #7 · ENH · Effort S · Sources: FTF (trade_impressions loop, deferred acceptance model)

## Summary

The swipe loop already writes one `trade_impressions` row per served card and a `trade_decisions` row per swipe — but a left-swipe is an opaque label: the engine can't distinguish "too lopsided" from "wrong position" from "I'd never trade him" from "they'd never take it." Add an optional one-tap reason chip row after a pass: **Unfair to me · Don't need that position · Wouldn't trade him · Don't believe they'd accept**. Skippable, never blocking, gone in a second.

Each reason maps to a distinct engine adjustment: fairness recalibration (the v2 fairness-gate watch item's missing tuning signal), positional preference (feeds the existing `acquire_positions`/`trade_away_positions` hard filter), an auto-prompt to add the player to Untouchables (#2), and an acceptance prior for the Thompson-sampling deck (and the deferred learned model, #65, whose blocker is label quantity *and* quality — ~20 undifferentiated decisions at deferral time). Trivial UI, disproportionate data value: one tap multiplies the information per label roughly fourfold.

## PRD

### Problem & user story

> As a user passing on a bad suggestion, I want to tell the app *why* in one tap, so the next deck stops making the same mistake.

Today the pass also writes an Elo signal (`trade_k_pass` = 4.0 via `save_trade_swipes`, treating the give side as "winners"), which is only correct when the rejection was a value statement — a "they'd never accept" pass is not one.

### Goals / Non-goals

**Goals**
- Optional reason capture after pass swipes, ≤1 extra tap, auto-dismissing.
- Reasons persisted joined to the decision row and queryable for tuning (#84) and training (#65).
- Each reason wired to (at least a v1 of) its engine adjustment.
- Reason enum strings identical across web/mobile and documented as a cross-client invariant.

**Non-goals**
- No reasons on like swipes (v1; positive labels are already less ambiguous).
- No free-text input (moderation + parsing cost; chips only).
- No immediate per-swipe regeneration — adjustments apply from the next job.
- Not the learned acceptance model itself (#65 stays deferred; this feeds it).

### Functional requirements

- FR1: After a pass swipe resolves, show 4 reason chips + implicit dismiss (tap-away/timeout ~4s). Reason keys (cross-client enum): `unfair_to_me`, `dont_need_position`, `wouldnt_trade_him`, `wouldnt_accept`.
- FR2: Reason write is a separate, non-blocking call after the existing `/api/trades/swipe` — swipe latency and the FB-46 reconstruction path are untouched; a lost reason write loses only the reason.
- FR3: `wouldnt_trade_him` → follow-up prompt listing the card's give-side players → one tap adds to Untouchables (#2). With #2 not yet shipped, the reason is still stored (prompt lights up later).
- FR4: `dont_need_position` → follow-up chip per received position → one tap removes it from `acquire_positions` / adds context to `league_preferences` (the existing prefs the job path reads via `load_league_preference`).
- FR5: `unfair_to_me` → logged for fairness recalibration: per-user counts surface in `/api/admin/engine-metrics`; v1 adjustment is a client nudge ("Want stricter balance? Raise your fairness setting") linking to #4's control, not an automatic threshold change.
- FR6: `wouldnt_accept` → acceptance prior: recorded against the card's `package_shape` bucket (the `f"{len(give)}x{len(receive)}"` bucket the Thompson deck already uses — see the server.py deck-ordering comment) so realism-rejections can be weighted differently from value-rejections in the Beta posteriors. v1: store + dashboard; posterior weighting behind its own config key.
- FR7: Elo-signal hygiene: when the reason is `wouldnt_accept`, the pass's Elo update is *not* a clean value statement. v1 keeps the existing `trade_k_pass` write (reason arrives after the swipe transaction); flag a follow-up to downweight retroactively or defer the Elo write briefly. (Open question 2.)
- FR8: Reason rows join cleanly to both the decision and the impression: store `trade_decisions.id` FK-style reference plus the give/receive sets (the impressions↔decisions join on asset sets is documented in code as fragile — carry the sets so the reason is self-contained).

### UX notes

- **Mobile** (`mobile/src/screens/TradesScreen.tsx`): chip row slides in where the card was, in the card's vacated space — not a modal; next card is already visible behind it. Haptic on chip tap; toast confirms consequence ("Got it — we'll show fewer WR-heavy offers").
- **Web** (`web/js/app.js` trade deck): identical chips inline under the deck after a pass.
- Frequency guard: after a user has answered N times in a session (proposal 5), show chips on a sampled basis to avoid fatigue — sampling rate as config, not hardcoded.
- Chips must not cover the next card's swipe affordances (gesture-audit flag `swipe.gesture_audit` precedent: respect existing gesture telemetry).
- Copy is neutral about the engine ("Why pass?") — never defensive.

### Success metrics

- Reason attach rate ≥40% of pass swipes in week 1 (novelty), settling ≥20%.
- Labeled-rejection volume: 5× the pre-feature decision count within a month.
- Distribution itself is the deliverable: e.g. if `unfair_to_me` dominates, that's the fairness-gate watch item answered with data.
- Downstream: untouchable adds originating from FR3 prompts (ties to #2's metric).

### Acceptance criteria

- [ ] Pass swipe with reason → `trade_rejection_reasons` row with correct decision linkage and asset sets.
- [ ] Reason call failure does not affect swipe success (fault-injection test).
- [ ] `wouldnt_trade_him` prompt → `asset_preferences` row (#2 integration test, when both flags on).
- [ ] Enum strings byte-identical web/mobile and listed in `docs/cross-client-invariants.md`.
- [ ] `/api/admin/engine-metrics` reports reason counts by league/window (#84).
- [ ] Flag off → no chips, no endpoint exposure, swipe path byte-identical.
- [ ] `docs/api-reference.md`, `docs/data-dictionary.md`, `docs/glossary.md` (reason terms) updated.

## HLD

### Components touched

`backend/database.py` (new table + accessor), `backend/server.py` (one new route; engine-metrics extension), `backend/trade_service.py` (none in v1 — adjustments land via prefs/#2/#4 surfaces), `mobile/src/screens/TradesScreen.tsx`, `mobile/src/api/trades.ts`, `web/js/app.js`.

### Data flow

Pass swipe → existing `/api/trades/swipe` transaction (record_decision → Elo signal → `save_trade_decision` → `save_trade_swipes` → `record_event`) completes unchanged → client shows chips → tap → `POST /api/trades/swipe/reason` → `trade_rejection_reasons` insert (+ `record_event("rejection_reason")` for streak-pipeline-style aggregation) → consequence routing: #2 prompt (client-side), prefs nudge (client-side), metrics (server-side). Next `_run_trade_job` is unaffected in v1 except through prefs/untouchables the user accepted.

### Flags & config interplay

- New flag `trade.rejection_reasons` (default `false`). Lives in the `trade.*` namespace (it tunes the trade loop) even though the UI is swipe-adjacent; `swipe.*` flags are ranking-swipe UX (per `feature_flags.py` grouping).
- Config keys: `rejection_chip_sample_rate` (1.0 = always, tune down on fatigue), `rejection_accept_prior_weight` (0.0 = posterior untouched; the FR6 dial, dark until #65 revisit).
- Interplay: `trade.thompson_deck` (ON) consumes FR6 data when the weight key is raised; `trade.preference_lists` (#2) gates the FR3 prompt; #4's control is the FR5 destination.

## LLD

### Engine changes

None to generation math in v1 — deliberate. The four adjustments route through existing, already-consumed inputs:

- `dont_need_position` → `league_preferences.acquire_positions` / `trade_away_positions` (hard filter `_positions_ok` in both `trade_service.py` and `trade_optimizer.py` — already enforced every job).
- `wouldnt_trade_him` → `asset_preferences` untouchables (#2's give-side pool filter).
- `unfair_to_me` → user-driven `fairness_threshold` change (#4).
- `wouldnt_accept` → stored against `package_shape`; consumed later by the Thompson Beta posteriors behind `rejection_accept_prior_weight` (the deck-ordering code already buckets by shape, so the join is trivial).

This keeps every changed line traceable and the engine deterministic while the label corpus grows.

### API changes

```
POST /api/trades/swipe/reason
{
  "trade_id": "ab12cd34",
  "reason": "wouldnt_trade_him",            // enum, see cross-client-invariants
  "decision_ref": 1742,                     // trade_decisions.id echoed from swipe response
  "give_player_ids": ["4046"],              // FB-46-style self-containment
  "receive_player_ids": ["7564"],
  "league_id": "...", "target_user_id": "..."
}
→ {"ok": true, "prompt": {"type": "add_untouchable", "player_ids": ["4046"]} | null}
```

Requires the swipe response to start returning the created `trade_decisions` row id (small, additive change to `/api/trades/swipe`'s response; `save_trade_decision` must return the insert id — currently returns None **(verify)**). `prompt` tells the client which follow-up to render, keeping consequence logic server-side.

### Schema changes

```python
trade_rejection_reasons_table = Table("trade_rejection_reasons", metadata,
    Column("id",                 Integer, primary_key=True, autoincrement=True),
    Column("user_id",            String,  nullable=False),
    Column("league_id",          String,  nullable=False),
    Column("decision_id",        Integer),                 # trade_decisions.id (soft ref)
    Column("trade_id",           String),
    Column("target_user_id",     String),
    Column("give_player_ids",    Text,    nullable=False), # JSON array
    Column("receive_player_ids", Text,    nullable=False), # JSON array
    Column("reason",             String,  nullable=False), # enum, 4 values
    Column("package_shape",      String),                  # "2x1" — precomputed for Thompson joins
    Column("created_at",         String),
)
Index("ix_trade_rejection_reasons_user_league",
      trade_rejection_reasons_table.c.user_id,
      trade_rejection_reasons_table.c.league_id)
```

A separate table rather than a `reject_reason` column on `trade_decisions`: the reason arrives in a second request after the decision transaction committed (FR2), reasons are optional/sparse, and `trade_impressions` rows are written at deck-serve time before any swipe exists — so neither existing table is the natural single home. The asset sets + `package_shape` are denormalized in (per the code's own warning that the impressions→decisions set-join is fragile). SQLite/Postgres compatible; created by `metadata.create_all()` like `trade_impressions`' table+index pairing.

### Client changes

- `mobile/src/api/trades.ts`: `sendRejectionReason()`; swipe response type gains `decision_id`.
- `mobile/src/screens/TradesScreen.tsx`: chip row component (new `mobile/src/components/RejectionChips.tsx`), prompt handling (untouchable add via #2's API; prefs nudge linking to the outlook/positions sheet — `OutlookSheet.tsx` is the precedent).
- `web/js/app.js`: inline chips + prompt handling in the trade deck section.
- Shared enum strings: add to `docs/cross-client-invariants.md` next to existing enum inventories.

### Rollout

Flag `trade.rejection_reasons`, default `false`. Ship dark → operator league → watch attach rate + chip-position misfires (`swipe.gesture_audit`-style telemetry) → on by default. The `rejection_accept_prior_weight` dial stays 0.0 until the #65 revisit has enough rows to validate against.

### Open questions

1. Reason on like swipes ("Why'd you like it?") — symmetric data, but doubles prompt load. Defer pending pass-side attach rates.
2. Elo hygiene (FR7): retroactively reverse the `trade_k_pass` update when reason = `wouldnt_accept`? `record_disposition_signal`-style explicit-K updates exist in `ranking_service.py`, so a compensating write is feasible — but adds replay complexity (`save_ranking_swipes`/`save_trade_swipes` history is replayed from DB on `_compute_elo`). Needs a small design note before building.
3. Is 4 chips the right set? `Already tried it in my league` came up in feedback triage **(verify against the feedback inbox)** — keep the enum extensible, cap visible chips at 4.
4. Sampling (`rejection_chip_sample_rate`) vs always-on at launch: start always-on, tune with data?

## Dependencies & sequencing

- **After #2** (preference lists) ideally — the `wouldnt_trade_him` chip's payoff is the one-tap untouchable add; backlog Wave 2 order is #2 → #7. Storable without it.
- **Pairs with #4**: `unfair_to_me` rates are the calibration evidence for fairness-control defaults; instrument together.
- **Feeds #65** (acceptance model): reasons are the label-quality multiplier the deferral asked for; also feeds Thompson (`trade.thompson_deck`) via FR6.
- **Feeds #84**: reason counts are explicitly listed in the engine-metrics dashboard expansion.
- No dependency on #1/#3/#13.
