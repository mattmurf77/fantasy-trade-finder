# Feature Scope — Knockout refine (R5 / R1 / R2 / shape knob)

**Date:** 2026-08-23 · **Entry point:** direct ask (operator 2026-08-23: aligned on verdict items 1–4; "Build with Opus subagents, review the changes with a Fable subagent, then you merge") · **Builder:** lead + B1/B2 (Opus), Fable reviewer · **Operator sign-off on waivers:** not needed (none)

## 1. Analytics scope
- [x] **(b) Existing events cover it:** `trades_generated` (count/gen_ms) plus per-card `features_json` (`shape`, `fairness_score`, `give_value`/`receive_value`, `need_fit`) already answer the questions this raises — volume, shape mix, honest-offer share. The presentment kill counters (`_presentment_kills`) already log R1/R2/R5 kills per job.

## 2. Schema & flag scope
- Tables/columns: **none**. Feature flags: **none** — all four switches are `model_config` knobs (deploy-free): `need_gate_dual_rescue` (1.0), `overpay_adjusted` (1.0), `pos_net_starter_relief` (1.0), `v3_shape_max_delta` (1.0). Prod-flip values after merge (operator-aligned bundle): `filler_min_frac` 0.15 (450 floor held), `trade_elo_gap_max` 0, `v3_shape_max_delta` 2. Rollback: any knob individually via admin config API; code knobs to 0 restore byte-identical behavior.

## 3. Evidence scope
- [ ] Structural guard: n/a — no client change, no testID.
- [x] **Unit tests:** `test_knockout_refine.py` (B1) + `test_shape_knob.py` (B2), plan §5, each with recorded sabotage lines.
- [x] **Code-walk proof** (Fable reviewer): all four knobs at their byte-identical settings reproduce today's verdicts; `opp_ctx=None` callers unchanged; no import-time binding of the new reads.
- [x] **Measured delta** (lead, post-merge): the §6 replay sweep, or the defence-certified fallback, numbers in TEST_LEDGER.
- [x] **Manual TestFlight checklist** (post-flip): (1) refresh FFV3 deck; (2) confirm 3-for-1 / 1-for-3 cards appear; (3) confirm NO card strips a position below startable depth on either side (spot-check 5 multi-RB cards — the operator's #341 concern); (4) pass-rate eyeball vs yesterday; (5) revert one knob, reload, confirm the change unwinds.

## 4. Docs scope
| Doc | Status |
|---|---|
| `docs/api-reference.md` | n/a — no route change |
| `living-memory/LLD.md` | n/a — gate *conventions* unchanged (knob-gated predicate variants; the per-member ctx threading is documented in plan §2, linked from D-159) |
| `docs/architecture.md` / `HLD.md` | n/a |
| `docs/cross-client-invariants.md` | n/a — no shared constant |
| `docs/config-reference.md` | **updated (B2)** — 4 knob rows + the bundle-flip note |
| `docs/glossary.md` | n/a |
| DECISIONS | **D-159 (lead)** — the four refinements, the operator's shape-rule intent clarification (R2 owns positional protection), the bundle-flip protocol |

## 5. Ship gate declaration
- CI green (backend-tests, mobile-typecheck, testid-lint) on the pushed sha; `FTF_SKIP_SIM_GATE=1` (D-056 posture).
- TEST_LEDGER entry: gates, sabotages, Fable code-walk, the measured (or fallback) bundle numbers.
- Express: **no** — full gates; the merge+flip authority is the operator's 2026-08-23 instruction.
