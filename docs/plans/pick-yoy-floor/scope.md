# Feature Scope — Pick YoY floor (`market_r1_yoy_floor`)

**Date:** 2026-08-24 · **Entry point:** direct ask (operator: "I'm aligned. The ideal solution is the D-079 ruling") · **Builder:** lead + one Opus builder, Fable reviewer · **Operator sign-off on waivers:** not needed (none)

## 1. Analytics scope
- [x] **(b) Existing events cover it** — pick values surface through served-card `features_json` (`give_value`/`receive_value`, `involves_pick`) and the pass-reason capture; no new event.

## 2. Schema & flag scope
- Tables/columns: none. Flags: none. `model_config` key: **`market_r1_yoy_floor`** (default 1.0; 0 = pure market, deploy-free revert) → `docs/config-reference.md`.

## 3. Evidence scope
- [ ] Structural guard: n/a — no client change.
- [x] Unit tests: `backend/tests/test_pick_yoy_floor.py` (plan §3, sabotage lines recorded).
- [x] Code-walk (Fable): knob-0 byte-identity; step-1/rounds-2-4/ladder-mode untouched; fallback chain intact.
- [x] Measured verification (lead, post-merge): re-run the injector probe against live prod — the FFV3 2027/2028 firsts price at ≥ the current-year mid (expected 2,184.6 in 1qb); note in TEST_LEDGER with the MangoPatti card as the reference case.
- [x] Manual TestFlight checklist (operator, post-deploy): refresh the FFV3 deck; find a card carrying a 2027/2028 1st; its displayed pick value should read ≈ a current mid-first, not a fringe starter; the A.J.-Brown-for-three-firsts family should now score the pick side ≈ 6,55x raw before package adjustment.

## 4. Docs scope
| Doc | Status |
|---|---|
| api-reference / architecture / HLD / LLD / invariants / glossary | n/a |
| `docs/config-reference.md` | **updated (builder)** — knob row + future-year sentence correction |
| DECISIONS | **D-161 (lead)** — D-079 re-asserted under market_slots; Q-018 closed by operator re-ruling |

## 5. Ship gate declaration
CI green; `FTF_SKIP_SIM_GATE=1`; TEST_LEDGER entry with tests + code-walk + the live probe numbers. Express: no — full gates; merge authority = the operator's alignment ruling.
