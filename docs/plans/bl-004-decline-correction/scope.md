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
  - **What holds exactly:** the net in K is −12 at every like K, and the unit tests pin it.
  - **What holds only approximately (release-lead's QA, 2026-11-02; for models-lead's R-G):** the Elo result of like + decline equals a single K-12 decline within 1 Elo only for near-equal ratings and packages up to 2×2. At full K a 3×3 package is off by 1.57. A 200-point rating gap is off by 3.9 (1×1) to 10.4 (3×3). When the give player is rated about 200 above, like + decline leaves the received player up 1.0–1.7. At full K that's identical to main; at K 0 it's exact; at K 4 it's better than main except in that case. The board test covers 1×1 at equal ratings.
- **The like is looked up on the decline's board:** the caller's active scoring format, which is where the route saves the signals (a legacy NULL row reads as `1qb_ppr`). Without it, a 1qb like at K 8 and a later sf_tep like at K 0 would net the 1qb board −4.
- **Residuals, recorded:**
  - only the latest like on a pair is netted, which matters only if K changed between two likes on one pair (for example across BL-001);
  - the route saves each per-pair signal in its own `save_trade_swipes` call, so a DB failure mid-loop can persist part of a correction (before, one call per decliner could already split the two users);
  - `trade_k_decline_correction` is no longer read: if prod's value had been tuned away from 20, that tuning is dropped (release-lead can check it read-only on the operator's word).
- **Sign-off:** models-lead's packet signs before merge (this is a model change).

---

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [ ] **(b) Existing events cover it:** none needed.
- [x] **(c) WAIVED — no analytics needed because:** the change is a ranking-math K on an existing signal. The persisted `swipe_decisions` rows (`decision_type 'disposition'`, per pair, with the K applied) already record it. BL-001's weekly monitor (`swipe_replay --mode monitor`, #374) reads disposition rows separately.

## 2. Schema & flag scope

- New/changed tables or columns: none.
- New/changed feature flags: none.
- New `model_config` keys: **`trade_k_decline_net`** = 12.0 (DB-seeded, `_MODEL_CONFIG_DEFAULTS`) → `docs/config-reference.md` § Match-decline correction. It's not mirrored in `ranking_service._DEFAULT_CFG`: nothing there reads it, and that module is engine-hashed, so touching it would cold every stored page once (release-lead's QA P2). `trade_k_decline_correction` stays registered but unused.
  - **Rollback:** only a code revert restores the fixed 20. The knob changes the net without a deploy.

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
