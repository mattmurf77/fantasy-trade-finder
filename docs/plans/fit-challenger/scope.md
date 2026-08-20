# Feature Scope — Fit challenger

**Date:** 2026-08-19
**Entry point:** direct ask (operator: thin knockouts + dual 0–100 scores as a new bake-off arm; “write a plan to build and PRD”)
**Builder:** unassigned — EM tasks from [PRD.md](PRD.md) / [PLAN.md](PLAN.md)
**Operator sign-off on waivers:** needed on §5 (new arm, new payload). Knockout list is operator-closed in PRD §3.

Parent: [PRD.md](PRD.md). Does **not** change organic `_generate_trades_impl`.

---

## 0. What this builds

A fourth bake-off generator (`backend/trade_gen_fit.py`, arm id `fit`) that knocks out only K0–K7, scores every survivor 0–100 per team (board, vs-consensus, consensus), ranks by sum, then applies preference filters.

What it is not: live serving, landability knobs, `trade_gen.v2`, dual R5 (F7), likes-you, PPG, card UI.

---

## 1. Analytics scope

- [x] **(b) Existing bake-off events cover the arm** once `model_arm=fit` is stamped on `deck_impressions` (same as `current` / `gen_v2`). Like-rate by arm is the question.
- [x] **(a) Arm diagnostics** (required, F5) on `bakeoff_runs.arms_json[fit].diagnostics` — schema in PRD §7. No new client event for v1.

## 2. Schema & flag scope

- New tables: **none.** Diagnostics ride existing `bakeoff_runs.arms_json`.
- New columns: **none** required. `fit` object lives in card JSON / `features_json`.
- New flags: **none** on the serving path. `bakeoff_include_fit` model_config (float 0/1), default 0.
- New knobs: PRD §9. All in `model_config` + `docs/config-reference.md`.
- Rollback: `bakeoff_include_fit=0`. Organic path never imports the module.

## 3. Evidence scope

- [x] **Unit tests (F6):** K1 legal/illegal shapes; K2 identical to `pick_swap_ok` on a shared fixture (2026 1st vs 2027 1st dead; 2-late-2nds-for-1st live); K3 kills a trade that leaves a team with 0 RB; negative consensus surplus still scores (them < 50, not dropped); unranked partner has `board: null`; untouchable still **enumerated** and dropped only in F4; pool cap respected (`enumerated ≤ fit_max_packages_per_pair`).
- [x] **Code-walk:** `_generate_trades_impl` does not reference `trade_gen_fit` unless a test greps it as forbidden on the organic branch.
- [ ] **Bake-off dry run:** one fixture league, arm off-roster then on, TEST_LEDGER: ms, enumerated vs Arm B prune size, `one_sided_pct`.
- Structural mobile guards: **WAIVED v1** — no client render of `fit` required. Additive JSON.

## 4. Docs scope

| Doc | Updated? |
|---|---|
| `docs/config-reference.md` | F5 knobs + `bakeoff_include_fit` |
| `docs/api-reference.md` | additive `fit` on TradeCard (bake-off only) |
| `docs/data-dictionary.md` | diagnostics keys |
| `docs/plans/three-model-bakeoff/PLAN.md` | addendum: arm `fit` |
| `living-memory/LLD.md` | one convention: preferences filter after score in this arm |
| ADR | D-095 (proposed): fit-challenger is a generator, not a profile |

## 5. Ship gate

- CI: `backend-tests` including `tests/test_trade_gen_fit.py`.
- Organic byte-identical: grep + a fixture generate with bakeoff off.
- TEST_LEDGER dry run before `bakeoff_include_fit=1` in any prod-like env.
- Express lane: **no.**
- Diffs under live `_generate_trades_v2` **gates** fail review (wrappers of `overpay_ok` etc. are OK; changing their math is not).

## 6. Open

- F7 dual R5 — not v1.
- C4 on/off for this arm — default on.
- ~~Fail bar for generation ms — after first dry run.~~ **Closed 2026-08-20 (operator):** fit per-arm gen_ms ≤ **8 s** at the 5,000 package cap (fixture measured 1.8 s — 4.4× headroom); job p95 ≤ **30 s** (PLAN-v2 S2 bar). Breach → halve `fit_max_packages_per_pair`; repeat breach → `bakeoff_include_fit = 0`.
