# Feature Scope — Decline reasons disabled (flag parked off)

**Date:** 2026-10-02
**Entry point:** direct ask (operator: "It's becoming tedious to click through twice after every decline … shouldn't be deleted, but just disabled")
**Builder:** Claude session, branch `fix/disable-decline-reasons`
**Operator sign-off on waivers:** yes — 2026-10-05 ("Yes. I'm aligned. Proceed"), covering §1 (no new analytics) and §3 (no formal TestFlight checklist)

---

## 1. Analytics scope

- [x] **(b) Existing events cover it.** No event is added, renamed or removed. With the flag off a decline fires the same server-side `match_swiped` (`decision: pass`) it always has, plus `deck_card_viewed` and the deck-outcome row. The reason-capture events (`trade_pass_reason_*`, `trade_pass_overlay_*`) simply stop firing; they stay registered in `backend/analytics_taxonomy.py` for reintroduction. **Known consequence:** decline-reason reporting has no new data from the flip onward.

## 2. Schema & flag scope

- New/changed tables or columns: none. `trade_pass_reasons` keeps its existing rows and receives no new ones.
- New/changed feature flags: `feedback.decline_reasons` **true → false** in `config/features.json` and its mirror `backend/tests/fixtures/flags/release.json`. `FLAG_KEYS` unchanged (registered default was already false). `docs/config-reference.md` row updated. Graduation/reintroduction criterion: operator call; flip back to `true`.
- New env vars / `model_config` keys: none. `pass_reason_elo_suppression` is left at 1.0 — it is only consulted by `/api/trades/pass-reason`, which now 404s, so it is inert while the flag is off and correct again the moment the flag returns.

## 3. Evidence scope

- [x] **Structural guard:** no new suite. All 99 existing `mobile/tests/check-*.js` pass with the flag off (including `check-decline-reasons.js`, `check-card-disposition.js`, `check-canvas-results.js` 4b2 — the kill-switch fallbacks).
- [x] **Unit tests:** `backend/tests/test_decline_reasons.py` — `test_the_flag_ships_on_for_everyone` → `test_the_flag_is_parked_off_for_everyone`; `test_no_allowlist_gating_anywhere` now compares the served value to the configured one. Existing coverage that proves the off-path: `test_flag_off_leaves_the_swipe_pass_path_byte_identical` (one `trade_decisions` pass row, one Elo swipe row give-beats-receive, zero reason rows), `test_pass_cooldown.py` (the D-067 live no-resurface bind), `test_seed_ui_test_db.py::test_release_flags_mirror_features_json`.
- [x] **Code-walk proof** (flag off, one decline):
  1. `mobile/src/screens/TradesScreen.tsx:6064` — `declineReasonProps` is `undefined` when `declineReasonsOn` is false.
  2. `mobile/src/components/TradeCard.tsx:793-812` — with `disposition.reasons` absent the ✕ renders and its `onPress` is the plain `disposition.onPass`; the panel/overlay at `:844-846` do not mount.
  3. `TradesScreen.tsx:8675` — `onPass={() => advance('pass')}`; `advance` (`:5609`) skips the reasons guard, then at `:5773` holds the pass for the undo window (`ux.swipe_undo` is on) or mutates immediately; either way it advances the deck (`:5797`) and POSTs `/api/trades/swipe`.
  4. `backend/server.py:15695` `swipe_trade` — `record_decision`, then the pass branch writes the in-memory Elo signal (`record_trade_signal`, give beats receive, `trade_k_pass × fit_mult`), binds the dismissal to every live trade service (`_bind_live_trade_pass`, D-067) so the card is not re-served, and persists `save_trade_decision` + `save_trade_swipes`. Nothing in this route reads the flag.
  5. `backend/server.py:16419` — `/api/trades/pass-reason` returns 404 `feature_disabled` before any session work.
- [ ] **Manual TestFlight checklist — WAIVED pending operator check:** no new build ships (the flag is server-delivered). A 30-second look on the current build after deploy is enough: (1) open Find a Trade → the card shows ✕ and ✓, no Value/Fit/Neither tiles; (2) tap ✕ → the next card appears at once with an Undo toast; (3) regenerate → the declined trade does not come back.
- `testID`s added/renamed: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added/changed; `/api/trades/pass-reason`'s documented flag-off 404 is now the live state |
| `living-memory/LLD.md` | n/a | no convention shifted |
| `docs/architecture.md` | n/a | no wiring change |
| `living-memory/HLD.md` | n/a | no architecture change |
| `docs/cross-client-invariants.md` | n/a | no shared constant changed |
| `docs/glossary.md` | n/a | no new term |
| ADR or `DECISIONS.md` entry | updated | D-195 (Elo consequence of declining without a reason) |
| `docs/config-reference.md` | updated | `feedback.decline_reasons` row + rollback note |

## 5. Ship gate declaration

- **CI green:** required on the pushed sha.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` 2026-10-05 entry.
- Express lane declared by the operator? no.
