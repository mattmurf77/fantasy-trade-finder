# #214/#215 — Stud-Tax Retune (market shapes) + `stud_tax_mode` Toggle — Build Status

Built 2026-08-05 on branch `teardown-remediation` (worktree). Implements
`tuning-proposal.md` §1–4 plus the #215 toggle (ship-vehicle recommendation:
"do both"). #252 is a third confirming report of the same complaint.

## The three shape changes (`backend/trade_service.py`)

All three live in the new `market` stud-tax mode (`_package_value_market`,
branched inside `package_value_v2`); the pre-#214 math is preserved
byte-identically as the `heavy` mode.

1. **Crown phase-out** (proposal §1): the crown credit is scaled by
   `max(0, 1 − |naive_skew| / skew_phaseout)`, `skew_phaseout = 0.5`
   (new `model_config` key). `naive_skew` = the sides' naive-sum gap over
   the SMALLER side's sum (symmetric; equals results.md's stud-side
   denominated skew in the stud-vs-package case). T3-class trades (already
   ~66% lopsided naively) now earn zero crown — KTC's observed shape.
2. **Elite credit for BOTH sides** (proposal §2): the crown credit applies
   per elite asset (value ≥ `crown_elite_value`, unchanged at 6000) on
   EITHER side, count-independent, at `crown_rate_market = 0.08`/piece
   (new key; below the legacy single-crown 0.12). Gibbs+Achane-class
   sides now earn offsetting credit — DynastyDealer's per-side STUD BONUS
   shape. Kill-switch stays flag `trade.crown_asset`.
3. **Own-best-asset depth benchmark + cap** (proposal §3):
   `contribution(v) = v · (floor + (1−floor) · (v/own_max)^γ)` with
   `own_max` = the package's OWN best asset (never the trade-wide `v_max`),
   `package_floor_market = 0.70`, `package_adj_gamma_market = 0.5` (new
   keys), and the side's TOTAL discount capped at
   `package_discount_cap = 0.35` × naive sum (new key). A single-asset
   side is never depth-discounted.

`other_values` (the opposite side's raw values) was added to
`package_value_v2`'s signature and threaded through every call site
(`trade_optimizer._consensus_packages` / `_fairness_v3` / `_surpluses` /
sweeteners; `trade_service` v2 pair, consensus pair, asset-ideas,
aggression-reweight paths; `server._evaluate_adjustments`).

## Constant re-fit (proposal §4)

Harness: `feedback-workspace/214/fit_matrix.py` (extends `run_matrix.py`;
in-process Flask test client over a worktree copy of the dev DB).
Competitor medians pool ALL per-cell observations from BOTH captures —
`research/competitor-values.md` (2026-08-02: KTC, DD×3 sources,
FantasyCalc, DynastyDealer) + `research/side-by-side-live.md` (2026-08-04:
live KTC, Dynasty Nerds) — e.g. T1 SF median +62.0% over 7 observations.
Per-trade delta = mean of the available format-cell deltas (results.md
convention); T5 1QB has no competitor sources and is excluded.

### Fit table (constants tried → per-trade mean deltas, pp; + = FTF lighter on the package than market)

72-point coarse sweep (floor × γ × rate × phase-out × cap) then a 24-point
refinement around the leaders. Representative rows:

| floor | γ | rate | phase | cap | T1 | T2 | T3 | T4 | T5 | T6 | ≤15pp | mean\|Δ\| |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.15 | 1.5 | 0.08 | 0.5 | 0.35 (first guess) | 36.1 | 1.6 | 13.4 | 24.7 | 12.9 | 8.2 | 4/6 | 16.2 |
| 0.60 | 0.75 | 0.03 | 0.5 | 0.35 (coarse best) | 32.9 | −3.0 | 9.1 | 20.9 | 12.5 | 3.9 | 4/6 | 13.7 |
| 0.80 | 0.5 | 0.06 | 0.5 | 0.35 (refine best) | 29.6 | −4.3 | 4.3 | 17.3 | 12.1 | 1.9 | 4/6 | 11.6 |
| **0.70** | **0.5** | **0.08** | **0.5** | **0.35 (SHIPPED)** | **30.7** | **−2.7** | **5.6** | **18.8** | **12.2** | **3.7** | **4/6** | **12.3** |

Shipped constants trade ~0.7pp of mean error vs the sweep's numeric best
for a still-visible depth discount (max −30%/piece vs −20%) and the
proposal's 0.08/elite-piece rate. The metric monotonically rewards weaker
adjustments (FTF's naive curve already sits near the medians), so the
sweep's asymptote is 'off' — the shipped point keeps the mechanisms real.

### Acceptance gate — PASS

- **Within ±15pp of the competitor median on ≥4/6 trades:** 4/6 (T2 −2.7,
  T3 +5.6, T5 +12.2, T6 +3.7). Baseline before this change: **0/6**
  (deltas +34.8 to +68.4pp, results.md §4).
- **T1 SF lands package-favored:** final skew **+51.3%** (was +3.2%;
  market median +62.0%, Δ only 10.7pp on that cell).
- The two misses are **naive-value-curve gaps no adjustment retune can
  close** — verified by replaying with adjustments fully OFF:
  - **T1** (mean Δ +30.7): driven entirely by the T1-1QB cell (median
    +60.6 vs FTF naive +14.6 — FTF prices Bo Nix far below market in 1QB;
    also the cell competitor-values.md flags low-confidence). The SF cell
    passes.
  - **T4** (mean Δ +18.8): the generic-Mid-1st substitution for the dated
    2027 1st (results.md's flagged limitation) + the same Lamb/pick
    curve gap; naive-only deltas are already +12.5/+16.5.

### Final per-cell table (shipped constants)

| Trade | Fmt | FTF final skew | Median | Δ (pp) | Adjustments applied |
|---|---|---|---|---|---|
| T1 | 1QB | +9.9% | +60.6% | +50.7 | give crown +426, recv depth −260 + crown +387 |
| T1 | SF | +51.3% | +62.0% | +10.7 | recv depth −189 (crown phased out) |
| T2 | 1QB | −18.8% | −21.3% | −2.5 | give crown +502, recv depth −209 |
| T2 | SF | −26.4% | −29.2% | −2.8 | give crown +282, recv depth −175 |
| T3 | 1QB | +62.8% | +71.8% | +8.9 | recv depth −308 (crown phased out) |
| T3 | SF | +58.5% | +60.8% | +2.3 | recv depth −317 (crown phased out) |
| T4 | 1QB | +14.2% | +31.4% | +17.2 | give crown +370, recv depth −281 + crown +336 |
| T4 | SF | +14.0% | +34.5% | +20.5 | give crown +343, recv depth −262 + crown +303 |
| T5 | SF | +55.5% | +67.7% | +12.2 | recv depth −27 (crown phased out) |
| T6 | 1QB | −3.5% | +8.3% | +11.8 | give crown +473, recv depth −225 |
| T6 | SF | +0.7% | −3.7% | −4.3 | recv depth −166 (Nabers sub-elite in SF) |

Note the structure the proposal asked for: crown credit now appears on
package sides (T1/T4 recv), phases out on lopsided trades (T3/T5), and the
depth discounts run −2% to −8% of naive sums (was −25% to −62%).

## Deck sanity diff (`feedback-workspace/214/deck_diff.py`)

Operator's real league (Lakeview `1312076055586050048`), 1QB board
(503 member_rankings rows → 338 in-pool overrides), 11 opponents at
consensus (the production common case), same inputs per mode:

| | heavy (pre-#214) | market (default) | off |
|---|---|---|---|
| cards (cap 5/opp) | 30 | 30 | 30 |
| shapes | 1for1 ×30 | 1for1 ×30 | 1for1 ×30 |
| fairness min/med/max | .760/.822/1.000 | .751/.840/1.000 | .751/.840/1.000 |
| widened cap 30/opp | 180 ×1for1 | 180 ×1for1 | 180 ×1for1 |

- **No stud-for-package flood**: deck composition is shape-identical; the
  consensus generator fills with 1-for-1s before 2-for-1s in this league
  under every mode, and every card clears the unchanged 0.75 fairness bar.
  Card *selection* shifts (heavy∩market overlap 7/30 at cap 5 — ordering
  churn from the value changes), which is the intended retune effect.
- **Forced consolidation probe** (pin the user's #2+#3 assets as an
  'all'-mode package → only 2-for-1 shapes allowed): heavy surfaces **1**
  card, and only via the #189 relaxed pass (fairness 0.558 — the old tax
  made consolidations near-impossible, the #214 complaint); market
  surfaces **4** cards through the NORMAL gates (fairness 0.910–0.966);
  off surfaces 0 (the #108 naive-gain gate binds). Fairness +
  `consolidation_raw_loss_frac` (unchanged, raw-sum-based) still bind.

## #215 toggle wiring

- **Storage:** `users.stud_tax_mode` (new column + idempotent migration;
  `get/set_stud_tax_mode` in `database.py`; NULL/unknown → `market`).
- **API:** `GET/PUT /api/settings/stud-tax` (verified-write gated like
  `/api/ranking-method`; fires `stud_tax_mode_changed`).
- **Engine plumbing:** thread-local mode context in `trade_service`
  (`stud_tax_override` / `current_stud_tax_mode`, the #189 `_cfg_override`
  pattern). Entry points resolve the user's stored mode and pin it:
  `TradeService.generate_trades` + `generate_asset_ideas` (wrappers over
  the renamed `_*_impl` bodies), `server._inject_likes_you_cards`, and
  `/api/trade/evaluate` (session OPTIONAL — Mode A stays public, anonymous
  = market; response echoes `stud_tax_mode`). An already-pinned mode wins
  over the stored setting (test hook; prod never nests).
- **Modes:** `market` = the shapes above; `heavy` = pre-#214 code path
  byte-identical (constants untouched: `crown_rate` 0.12,
  `crown_share_floor`, `package_adj_gamma` 1.5, trade-wide `v_max`);
  `off` = naive sums (both adjustments zeroed → `adjustments` omitted).
- **Mobile:** Settings gains a TRADE VALUES section with the 3-option
  "Stud tax" segmented row (`settings.stud-tax.<mode>`; Market — matches
  market consensus (recommended) / Heavy — favors the single-stud side /
  Off — no value adjustments; optimistic PUT, revert + toast on error).
  `evaluateTrade` now sends the session token when present (endpoint
  stays public). `AdjustmentsDisclosure` unchanged structurally; mode
  `off` renders the one-line "Value adjustments off" note
  (`calc.adjustments.off`) in both calculator verdict mounts.

## Tests

- `backend/tests/test_stud_tax_modes.py` (new, 24 tests): the three
  shapes (phase-out full/zero/linear/monotone; both-sides elite credit,
  per-piece, count-independent, sub-elite earns nothing; own-best
  benchmark incl. single-asset immunity; total-discount cap), the three
  modes (off = naive; heavy = legacy formula byte-identical; context
  nesting/restore), end-to-end `/api/trade/evaluate` under all three modes
  (anonymous default, stored-mode respect, off omits adjustments,
  heavy < market < off receive-value ordering), the settings route
  (GET default / PUT validate+persist / 401), and `generate_trades`' mode
  resolution + pin-respect.
- **Deliberate expectation updates** in `test_trade_evaluate.py`
  (old → new stated in comments): 1-for-1 gap `Early 1st` → `Mid 1st`
  (no lighter-side shrink under market); the 1-for-1 depth-on-weaker-side
  pin now runs as an explicit heavy-mode test with a new market twin
  (no adjustments on 1-for-1); the 2-for-1 consolidation test uses new
  elite-tier fixtures (market credit requires value ≥ 6000 inside the
  phase-out window); values-endpoint order includes the new fixtures.
- **Legacy pins preserved, not loosened:** the 11 suites authored against
  the pre-#214 math (`test_crown_asset`, `test_fairness_gate_golden`,
  `test_trade_engine_v2`, `test_trade_optimizer`, `test_filler_threshold`,
  `test_finder_targeting`, `test_relaxed_fallback`,
  `test_consensus_consolidation_gate`, `test_block_boost`,
  `test_asset_ideas`, `test_trade_tier2`) pin `stud_tax_override("heavy")`
  in their isolation fixtures — they are now the heavy-mode byte-identity
  guard, assertions untouched.
- Full suite: **1445 passed, 1 skipped** (baseline 1420+1; +24 new +1
  split heavy-twin). `cd mobile && npx tsc --noEmit` clean.

## Docs updated

`config-reference.md` (5 new `model_config` keys), `api-reference.md`
(settings route + evaluate `stud_tax_mode`), `data-dictionary.md`
(`users.stud_tax_mode`), `cross-client-invariants.md` (§ Stud-tax mode
strings), `glossary.md` ("Stud tax"), mobile `components/` + `api/` +
`screens/` CLAUDE.md registries (incl. testIDs `settings.stud-tax.<mode>`,
`calc.adjustments.off`).

## Open follow-ups (not in scope)

- T1-1QB / T4 residuals are consensus **value-curve** gaps (Nix/young-QB
  1QB pricing; dated-pick discounting in Mode A) — a seed/blend question,
  not an adjustment question.
- Web calculator (`web/`) doesn't render the adjustments disclosure today;
  if it grows one, it needs the same `stud_tax_mode === 'off'` note.
- `model_config` DB rows for the 5 new keys seed on next boot
  (`_MODEL_CONFIG_DEFAULTS`); production values live-tunable via
  `PUT /api/admin/config/<key>` as usual.
