# Feature Scope — BL-004: a declined match nets −12 at any like K

**Date:** 2026-10-27
**Entry point:** models-eng backlog. BL-004, logged by models-lead on 2026-10-24 (`docs/plans/org-bringup/leads/models-lead-launch.md` §BL-004, with the dispositions ruling above it).
**Builder:** models-eng (session `local_d96dadc8-c2a6-4ded-a228-f3c254c71a57`)
**Operator sign-off on waivers:** not needed. §1's waiver is analytics-only; nothing user-visible ships.

**The change:**
- **Before:** `trade_k_decline_correction` (20) was a fixed K designed against a +8 'Interested' swipe. It netted −20 while trade swipes were frozen (bake-off on, K 0), −16 at half K, and −12 only at full K.
- **Now:** `database._decline_signals` gives a decliner one correction per (give, receive) pair, at K = `trade_k_decline_net` (12) + the K the user's like on that pair was stored with (`swipe_decisions`, the latest `trade` row with winner = receive and loser = give; 0 when none). So like + decline nets −12 at every like K.
- **Accept is unchanged.**
- **models-lead's bar:** the net decline effect is −12 ± 1 at every like K, as a unit test.
- **Sign-off:** models-lead's packet signs before merge (this is a model change).

---

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [ ] **(b) Existing events cover it:** none needed.
- [x] **(c) WAIVED — no analytics needed because:** the change is a ranking-math K on an existing signal. The persisted `swipe_decisions` rows (`decision_type 'disposition'`, per pair, with the K applied) already record it. BL-001's weekly monitor (`swipe_replay --mode monitor`, #374) reads disposition rows separately.

## 2. Schema & flag scope

- New/changed tables or columns: none.
- New/changed feature flags: none.
- New `model_config` keys: **`trade_k_decline_net`** = 12.0 (DB-seeded, `_MODEL_CONFIG_DEFAULTS`, mirrored in `ranking_service._DEFAULT_CFG`) → `docs/config-reference.md` § Match-decline correction. `trade_k_decline_correction` stays registered but unused.
  - **Rollback:** a code revert restores the fixed 20. The knob scales the net without a deploy.

## 3. Evidence scope

- [x] **Unit tests:** `backend/tests/test_decline_net.py` (new):
  - the net is −12 at like K 0, 2, 4, 4.8 (fit-scaled) and 8;
  - per-pair K, with an unliked pair at 12;
  - the latest like wins; a pass, another user's row or a disposition row is not the like;
  - each decliner is corrected from their own likes;
  - accept is unchanged;
  - the knob is read;
  - on a `RankingService` board, a like then the decline lands within 1 Elo of a single K-12 decline.

  `backend/tests/test_disposition_route.py`: the decline now persists one signal per pair (count 5).
- [x] **Code-walk proof:** the route applies each signal in turn (`server.py` `disposition_trade_match`, the `for sig in result["elo_signals"]` loop: `record_disposition_signal` then `save_trade_swipes`), so per-pair signals need no route change. Replay reads the persisted per-pair rows with their K.
- [x] **WAIVED (TestFlight checklist):** backend-only. No client change, and no user-visible surface beyond ranking order.
- `testID`s: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | the route and its response contract are unchanged (`elo_signals` was never in the response body) |
| `living-memory/LLD.md` | n/a | no convention shift |
| `docs/architecture.md` | n/a | no module wiring change |
| `living-memory/HLD.md` | n/a | no architecture shift |
| `docs/cross-client-invariants.md` | updated | § K-factors (the decline row and the key list) |
| `docs/glossary.md` | updated | K-factor list |
| ADR or `DECISIONS.md` entry | n/a | models-lead's BL-004 ruling is the record; the D-entry is the scribe's at merge |

## 5. Ship gate declaration

- **CI green:** `backend-tests`, `mobile-typecheck`, `maestro-testid-lint` on the pushed sha.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` at merge (release-lead).
- **TestFlight verification:** none (waived).
- Express lane declared by the operator? no.
