# Feature Scope — Full sweep (`trade.full_sweep`)

**Date:** 2026-08-22
**Entry point:** direct ask (operator, 2026-08-22: "generate everything and rank globally — for all arms"), from [`docs/reviews/2026-08-22-trade-model-second-read.html`](../../reviews/2026-08-22-trade-model-second-read.html) (on branch `claude/trade-model-restrictiveness-7f3975` until that review PR merges) §03
**Builder:** lead session (Fable 5) + Opus build agents A1/A2, reviewer A3 — see [`plan.md`](plan.md) §4
**Operator sign-off on waivers:** not needed (no waivers — every section answered)

---

## 1. Analytics scope

- [ ] (a) New events specced: none.
- [x] **(b) Existing events cover it:** `trades_generated` (props `count`, `gen_ms`, `engine_version`, `lanes`) answers the two questions this change raises — *did the deck grow* and *what did it cost* — per job, already in prod (August: median 1.7 s, p90 5.3 s). Partner coverage is derived from `deck_impressions.assets_json` joined to `league_members.roster_data` (the method in the second-read report); no new property needed.
- [ ] (c) WAIVED: —

## 2. Schema & flag scope

- New/changed tables or columns: **none**.
- New/changed feature flags: **`trade.full_sweep`** → `config/features.json` (with `_comment_full_sweep`), `backend/feature_flags.py` `FLAG_KEYS`, `docs/config-reference.md`. **Default was `false` (built dark); operator lit it at merge, 2026-08-23 — the graduation checklist below is now post-flip verification.** Graduation criterion: operator runs the §3 TestFlight checklist on their own single-board league; deck reaches ≥ 9 of 11 partners and `gen_ms` p90 stays under the 60 s `_JOB_HARD_TIMEOUT` (`server.py:2230`) with comfortable margin (target ≤ 15 s). The v3 divergence pair path has no deadline of its own (`trade_optimizer.py:231`); the flag-on rail is `full_sweep_budget_s`. Kill switch = this key, deploy-free via `POST /api/feature-flags/reload`.
- New `model_config` keys: **`exploration_base_per_opp`** (default `5.0`, read clamped to ≥ 1) and **`full_sweep_budget_s`** (default `30.0`; flag-on wall-clock rail, ≤ 0 disables) → `docs/config-reference.md`. Both byte-identical at default with the flag off. Rollback lever for the whole change is the flag; for deck size it is `bakeoff_deck_limit` while serving is interleaved (prod: `bakeoff_serve_interleaved = 1`, limit 60) and `exploration_base_per_opp` × partners in dark serving.

## 3. Evidence scope

- [ ] Structural guard (`mobile/tests/check-*.js`): **n/a — no client change.** No `testID` added or renamed.
- [x] **Unit tests:** `backend/tests/test_full_sweep.py` (A1) — flag-off byte-identity (break fires at today's count), flag-on visits every member, global rank (last member's best card comes first), streaming fires N times with a non-shrinking snapshot, both loops, `exploration_base_per_opp` honoured and default reproduces today's split; each with a recorded sabotage line. `backend/tests/test_arm_sweep_parity.py` (A2) — pins that `trade_gen_v2` and `trade_gen_fit` have no opponent-level early exit, with sabotage proof. Full list in [`plan.md`](plan.md) §5.
- [x] **Code-walk proof** (A3, read-only): flag-off path byte-identical — both `break` sites cite the flag guard; `git grep trade_full_sweep` shows exactly those two reads; `exploration_base_per_opp` default `5.0` reproduces `_EXPLORATION_BASE_PER_OPP` at both read sites.
- [x] **Manual TestFlight checklist** (server-side flag; no client build required):
  1. Flip `trade.full_sweep` → `true`; `POST /api/feature-flags/reload`.
  2. In a 12-team league where only you have ranked, refresh the trade deck.
  3. Count distinct trade partners across the deck. **Expect ≥ 9 of 11** (today: 6; the same 6 every refresh).
  4. Read that job's `trades_generated.gen_ms`. **Record it.** Expect roughly 2× today's (~3 s median); a value at or near `full_sweep_budget_s` (30 s) means the rail fired and the sweep was cut short — record which partners were reached.
  5. Confirm the deck size did not exceed `bakeoff_deck_limit` (60).
  6. Flip the flag off, reload, refresh. **Expect** the deck to fall back to ~6 partners — proves the kill switch.
  Log all numbers in `living-memory/TEST_LEDGER.md`.
- [ ] WAIVED: —

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added, renamed, removed or contract-changed |
| `living-memory/LLD.md` | **updated (A2)** | generation-loop convention: the opponent sweep is complete under `trade.full_sweep`; `global_target` is a flag-off stop, never a cap; per-opponent keep is the knob `exploration_base_per_opp` |
| `docs/architecture.md` | n/a | no module added or re-wired; same call graph |
| `living-memory/HLD.md` | n/a | no architecture shift |
| `docs/cross-client-invariants.md` | n/a | no shared constant, enum or colour |
| `docs/glossary.md` | n/a | "full sweep" is descriptive, not a new domain term |
| `docs/config-reference.md` | **updated (A2)** | flag row + knob row, deck-size consequence noted |
| ADR / `DECISIONS.md` | **D-154 (lead)** | full sweep built dark; threads rejected (GIL); latency work deferred to phase 2; deck size stays the operator's `bakeoff_deck_limit` dial; narrows the `_comment_compressed_board` "displacement" consequence |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (+ `check-*.js`) + `maestro-testid-lint` on the pushed sha.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry naming the two test files, their sabotage lines, and the A3 code-walk.
- **TestFlight verification:** the §3 checklist, run by the operator after merge, outcome logged in TEST_LEDGER — this is what graduates the flag.
- **Express lane declared by the operator?** No — full gates.
