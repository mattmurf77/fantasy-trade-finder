# Feature Scope — Package-benchmark fix + gap auto-sweetener

**Date:** 2026-08-21
**Entry point:** direct ask — operator approved 2026-08-21 ("I'm aligned. Let's fix that")
off the evidence memo [docs/reviews/2026-08-21-market-curve-comparison.md](../../reviews/2026-08-21-market-curve-comparison.md) §3b.
**Builder:** isolated worktree agent, branch `fix/package-benchmark-sweetener`.
**Merge posture:** built now, **MERGE HELD** for the operator's Monday window
boundary (change-control rule, trade-engine-accuracy PLAN Phase 0.4). Nothing
here is pushed or served until the main session ships it.
**Operator sign-off on waivers:** not needed (no waivers — every section answered)

> **STATUS 2026-08-21 (mid-build re-delegation).** Items 1 (benchmark fix)
> and 2 (gap auto-sweetener) are BUILT, test-green and committed on this
> branch. Item 3 (`ghost_holdout_one_in` → 0) is **NOT started** — the §2
> row below describes the intent, not the state. Also still owed by the
> successor session: the manual TestFlight checklist file
> (`testflight-checklist.md` referenced in §3 does not exist yet), the
> W0-style deck-size / gap-distribution measurement, the TEST_LEDGER entry,
> and the DECISIONS/CHANGELOG entries at ship time.

Three changes, one branch:

1. **Benchmark fix** — `_package_value_market` depth-discounts a multi-asset
   side that does not hold the trade's best asset against the TRADE's best
   asset (`package_bench_trade_wide`, default ON; cross-side floor
   `package_floor_cross` 0.40). Kills the mid-package-buys-stud defect: the
   served Rice+Etienne+Swift+Corum → Nacua card moves 0.939 (served fair) →
   ~0.71 (blocked), between FantasyCalc (0.734) and pre-#214 heavy (0.692).
2. **Gap auto-sweetener** — `sweetener_gap_threshold` (default 1539 = one
   late 1st, the operator's agreed line): at generation time, per arm, a
   card whose absolute consensus gap exceeds the threshold gets the smallest
   sufficient equalizer asset ADDED from the richer side's roster, re-earning
   every gate; unclosable cards are kept unsweetened.
3. **Ghost holdout dies in code** — `ghost_holdout_one_in` default 10 → 0
   (operator ruling 2026-08-21, batch-wide; the prod DB row is already 0).

## Which engines get the sweetener in v1 — decided, not silently skipped

| Path | v1? | Reason |
|---|---|---|
| v2 divergence pair generator (`trade_service._generate_for_pair_v2`) | **yes** | gap cards measured live from arm D, which overlays this path |
| consensus generator (`trade_service._generate_consensus_for_pair`) | **yes** | 84.5% of served cards; arm D's `consensus_both_ways` overlay runs through it |
| v3 optimizer (`trade_optimizer.generate_pair_trades_v3`) | **yes** | `trade_engine.v3` is ON in prod; the 3.4 sweetener machinery lives here and was generalized (`close_value_gap`) rather than duplicated |
| arm C (`trade_gen_v2`) | **follow-up** | decided by effort: arm C has its own value math (`consolidated_value`, `gen2_consol_*`), its own candidate pipeline (`_pair_survivors`) and its own gate stack — the pass would need its own integration and re-verification of the gen2 goldens, for an arm that serves only quota-capped bake-off slots. Its gap cards are real (CHANGELOG 2026-08-21 names C), so this is a named follow-up, not a skip. |
| fit arm (`trade_gen_fit`) | **follow-up** | same effort call: fit has its own enumerator/scorer/presentment pipeline and is not yet rostered for serving (`bakeoff_include_fit` 0). NOTE the fit arm **does** inherit the benchmark fix automatically — its `_surplus` calls `ts.package_value_v2` with a trade-wide `v_max` through the module namespace (verified at `backend/trade_gen_fit.py:640-649`). |

Arm A pins BOTH knobs at 0.0 (`MODEL_A_PROFILE`) — it reconstructs the
pre-wave engine, which had own-max math and no sweetener. The arm-A golden
did **not** need re-capturing: the kill values are proven byte-identical
no-ops (see §3), which is strictly better for D-075 than a moved baseline.

---

## 1. Analytics scope

- [x] **(b) Existing events cover it.** No new client events. The
  measurement split rides `deck_impressions.features_json.gap_sweetener` —
  a server-side frozen feature key (the F1 spine), stamped on EVERY row
  (null when unsweetened) per the fit-arm uniform-key precedent, NOT an
  analytics event, so the taxonomy (`backend/analytics_taxonomy.py`) is
  untouched — confirmed against its rules: nothing here is a client-emitted
  event. Questions it answers: sweetened-card share, like/pass split on
  sweetened vs unsweetened, gap distribution before/after.
  Card payloads additionally carry `gap_sweetener` (only when present,
  same convention as the 3.4 `sweetener` key) for client inspection.

## 2. Schema & flag scope

- New/changed tables or columns: **none.** (`features_json` is an existing
  Text column; a new key inside it is not schema.)
- New/changed feature flags: **none.** Knob-gated, not flag-gated.
- New `model_config` keys — all three follow the five-registration rule
  (`trade_service._DEFAULT_CFG` + `database._MODEL_CONFIG_DEFAULTS` +
  `_PINNED_KNOBS` + disposition sentence in
  `docs/plans/three-model-bakeoff/scope-phase2.md` + `docs/config-reference.md` row):

  | Knob | Default | Deploy-free rollback |
  |---|---|---|
  | `package_bench_trade_wide` | 1.0 | set to 0 ⇒ pre-fix own-max math byte-identically |
  | `package_floor_cross` | 0.40 | inert while the knob above is ≤ 0 |
  | `sweetener_gap_threshold` | 1539.0 | set to 0 ⇒ pass skipped byte-identically |

- Changed default (**NOT YET DONE — successor item**): `ghost_holdout_one_in`
  10 → 0 in `trade_service._DEFAULT_CFG` AND `database._MODEL_CONFIG_DEFAULTS`
  (and align the `suggestion_telemetry.py:103` inline fallback), with a
  comment recording the operator ruling 2026-08-21 (batch-wide; prod row
  already 0 — the default change makes code agree with the ruling).

## 3. Evidence scope

- [x] **Structural guard:** WAIVED-equivalent — backend-only change; no
  mobile file touched, no testID added. (Mobile renders sweetened cards
  through the existing value-bar/id-list contract; see the checklist below.)
- [x] **Unit tests:**
  - `backend/tests/test_package_benchmark.py` (new, 8 tests) — the Nacua
    regression (serves under legacy math at the pinned literals, falls OUT
    of the ±15% band under the fix), kill-value byte-identity across four
    shapes, single-asset exemption, own-max path preservation, cap
    preservation, cross-floor isolation.
  - `backend/tests/test_gap_sweetener.py` (new, 12 tests) — helper unit
    (direction, smallest-sufficient, untouchables, unclosable→None, extra
    gates), consensus path on/off, v3 path on/off, v2 divergence path
    on/off. The "off" tests ARE the sabotage-verify: knob 0 ⇒ the exact
    gap cards reappear unsweetened with their full gap.
  - Updated with dated comments where a golden isolates a different claim:
    `test_stud_tax_modes.py` (own-max shape now pinned at the kill value +
    a new default-shape direction pin), `test_bakeoff_challenger.py` /
    `test_engine_quality_golden.py` / `test_asset_ideas.py` (kill-value
    pins), `test_bakeoff_arm_a_golden.py` (R4 victim from arm B's own
    deck), `test_engine_gates_config.py` (surplus sweep widened).
  - Re-captured: `backend/tests/fixtures/bakeoff/flag_off_golden.json`
    (flag-off parity golden — its contract is "flag off == non-bake-off
    path", which survives; the engine underneath moved deliberately).
- [x] **Code-walk proof:** [code-walk.md](code-walk.md) — the benchmark
  threading trace, callsite by callsite.
- [ ] **Manual TestFlight checklist:** `testflight-checklist.md` — **NOT YET
  WRITTEN (successor item).** Must cover: value bars on sweetened cards
  (give/receive totals include the equalizer; gap reads ≤ one late 1st) and
  deck-size impact on a real league.
- `testID`s added/renamed: none.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route added/renamed/removed. TradeCard payloads gain the optional `gap_sweetener` key following the documented optional-key convention of `sweetener` (Tier 3 3.4); no contract changed — clients that ignore it see the same shape |
| `living-memory/LLD.md` | n/a | No schema/route/invariant convention shifted; the knob follows the existing five-registration convention rather than changing it |
| `docs/architecture.md` | n/a | No module wiring change — `close_value_gap` lives in `trade_optimizer` next to `_try_sweeten` (its prior art) and `trade_service` lazy-imports it exactly as it already lazy-imports `_consensus_packages` |
| `living-memory/HLD.md` | n/a | Same — no new component |
| `docs/cross-client-invariants.md` | n/a | No shared constant/enum/color; 1539 is a backend knob, not a client constant |
| `docs/glossary.md` | n/a | "Sweetener" already exists as a term (Tier 3 3.4); this is a second kind of the same thing, discoverable from config-reference |
| `docs/config-reference.md` | **updated** | Rows for all three knobs + `package_floor_market`/`package_adj_gamma_market`/`package_discount_cap` amendments + `ghost_holdout_one_in` default 0 |
| ADR / `DECISIONS.md` entry | deferred to ship session | The merge is held; the D-entry (benchmark fix + arm-A pin-instead-of-recapture + sweetener line) belongs to the session that ships to `main`, alongside the CHANGELOG entry — noted in the final report so the operator can ratify |

## 5. Ship gate declaration

- **CI green:** `pytest backend/tests` full suite on this branch (counts in
  `living-memory/TEST_LEDGER.md`); `tsc --noEmit` / `check-*.js` /
  `testid-lint` unaffected — zero mobile files touched, mobile CI is
  byte-identical to `origin/main`'s green.
- **Evidence recorded:** TEST_LEDGER entry with the measured deck-size and
  gap-distribution deltas (W0-style fixture measurement) — **successor
  item, not yet written.**
- **TestFlight verification:** checklist to be written (§3) and run by the
  operator after the Monday merge.
- Express lane declared by the operator? **No — full gates.**
