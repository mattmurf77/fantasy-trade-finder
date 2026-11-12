# Feature Scope — Next-year firsts priced by projected draft order

**Date:** 2026-11-11
**Entry point:** direct ask from the operator. Verbatim and fully reasoned in [design.md §1](design.md#1-the-ask)
**Builder:** design and build by subagents, worktree `.claude/worktrees/pick-draft-order`, branch `feat/pick-value-projected-slot`. **Built 2026-11-11, flag off; intended shipped value ON** (decision 7: the operator flips it after the replay).
**Operator sign-off on waivers:** needed. Two waivers: analytics (§1c) and the structural mobile guard (§3).

**Operator decisions (2026-11-11):** all eight in [design.md §12](design.md#12-decisions-for-the-operator--all-approved-as-recommended-2026-11-11) approved as recommended. Two rulings the same day revise them (design §0): (1) **full strength** — no weeks-played discount by default, the ramp kept behind knob `pick_projection_season_scaling` (0); (2) **show the exact projected slot** — `"2027 1.02 (from dondags) · projected"` with wire fields `proj_slot` / `proj_name`, replacing the early/late tag and its `pick_projection_tag_threshold` knob. Decision 8 (keep weekly forecasts) is built as `baseline_retention_days` (90).

Summary: a 2027 (next-season) round-1 pick's engine value becomes generic price × (1 + w·(ratio − 1)).

- The ratio is the pick's ORIGINAL team's slot distribution from the saved league forecast, over DynastyProcess's per-slot curve, normalised so that a league's total stays unchanged.
- w is the share of the regular season already played.

It goes through the one pricing seam (`priced_pool_value` / `server._priced_pick_value`), so the deck, calculator, eveners, Picks screen, power rankings, calibration and Win-Now all agree. An adjusted pick shows its projected slot: `2027 1.02 · projected`, with `proj_slot` / `proj_name` on asset payloads.

---

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [ ] **(b) Existing events cover it.** Trade impressions already store each card's assets and give/receive values (`deck_impressions` `assets_json`, `features_json.served_market`, `server.py:10618-10712`). Swipes, likes and proposals answer "do cards with a projected 2027 1st get accepted more or less". The projection key also enters `values_snapshot_id`, which is stamped on each job's `run_meta`, so a card can be tied to the forecast that priced it.
- [x] **(c) WAIVED, no new events.** This is a pricing change with no new user action to observe. Measurement is the offline replay and the end-of-season forecast backtest ([design.md §10](design.md#10-evaluation)), plus the existing impression and outcome rows above. One `log.info` line per league read (`pick-projection: league=… run=… w=… applied=N`) is a log, not an event. *Surface to the operator.*

## 2. Schema & flag scope

- **New/changed tables or columns:** none.
  - Reads `league_projection_runs` / `league_projection_targets` as they are.
  - `draft_picks.pool_value` is never written; pricing stays read-time.
  - `roster_snapshot.values_snapshot_id` gains an input. That is a hash, not schema.
- **New feature flag:** `picks.projected_slot_value`.
  - Add it to `FLAG_KEYS` and `DEFAULT_FLAGS` (False) in `backend/feature_flags.py`, and to `config/features.json` with a `_comment_picks_projected_slot_value`.
  - Mirror it in `backend/tests/fixtures/flags/release.json`, `profiles-on.json` and `onboarding-v2.json`, then document it in `docs/config-reference.md`.
  - Read **live** in `server._league_pick_projection`, the way `_slot_labels_enabled` is, so a reload turns it off without a restart.
  - **Default state:** shipped value per operator decision 7. Recommended ON once the unit tests and replay pass.
  - **Depends on:** `league.projections` (on in production only through `FTF_FLAGS`, G-076). With that off there are no runs and the feature is inert.
  - **Graduation:** the end-of-season backtest shows the weekly slot distributions beat uniform on log loss from week 6 on, and the operator has accepted a sample of before/after cards from their own league.
- **New `model_config` knobs** (Float; `database._MODEL_CONFIG_DEFAULTS` + `trade_service._DEFAULT_CFG`; `docs/config-reference.md`):
  - `pick_projection_weight` = 1.0. Strength of the adjustment. **0 is the deploy-free rollback lever**: every pick prices exactly as today.
  - `pick_projection_min_weeks` = 3: no adjustment before that many completed weeks.
  - `pick_projection_max_age_days` = 8: a run older than this is ignored, unless the run had at most one regular-season week left.
  - `pick_projection_max_round` = 1: rounds above it stay generic.
  - `pick_projection_season_scaling` = 0 (operator ruling 2026-11-11): full strength; 1 = multiply by completed ÷ regular-season weeks. (`pick_projection_tag_threshold` was designed and dropped by the same-day display ruling.)
- **Forecast retention (decision 8):** `config/league_projections.json` `baseline_retention_days` = 90 (absent = `retention_days`).
- **New env vars:** none.
- **Version / hash bumps:**
  - `DECK_PIPELINE_VERSION` 22 → 23, with a new pin.
  - `backend/pick_projection.py` is added to `_ENGINE_CODE_MODULES`.
  - The projection key is added to `values_snapshot_id` (all three call sites), the prepared-inventory receipt and the calibration provenance.

## 3. Evidence scope

- [x] **Structural guard:** WAIVED. No mobile or web source changes; the tag is a server-rendered label. *Surface to the operator.*
- [ ] **Unit tests:**
  - `backend/tests/test_pick_projection.py` (new): conservation, uninformative = generic, w = 0 byte-identical, point-mass value, monotonicity, traded pick follows the original roster, playoff-mass spread, non-12-team mapping, every gate. Each carries the sabotage target listed in [design.md §10](design.md#10-evaluation).
  - Extend `test_league_pick_value_alignment.py`:
    - the AST seam list, plus "projection hoisted once per league";
    - one value per pick across the Picks screen, power rankings, calculator, engine Elo, eveners and Win-Now.
  - Extend `test_pick_yoy_floor.py`: generic G includes the D-161 floor.
  - New vsn1 test: changes iff the projection key changes; all three sites pass the same key.
  - Label tests: tag above threshold only; byte-identical with the flag off.
  - Bump `test_deck_pipeline_digest`. Leave `test_bakeoff_arm_a_golden` unchanged and green.
- [ ] **Code-walk proof.** The trace to write after the build: pick row → `_league_pick_projection` (gates) → `_priced_pick_value` → `priced_pool_value` new step → `_owned_pick_assets` pick_value bridge → `_pick_asset_elos` → seed, user and member Elo maps → `give_value`/`receive_value` and deck rules. Plus the same row through `_owned_pick_label` → `trade_card_to_dict` name.
- [ ] **Replay:** `backend/eval/pick_projection_replay.py` (new, aggregate-only) over `data/prod-requests/`, synthetic and real-forecast arms. Pass bar in [design.md §10](design.md#10-evaluation). Result logged in TEST_LEDGER.
- [ ] **Manual TestFlight checklist.** Current build; no new build is needed. Run it in the operator's league with a complete forecast:
  1. Open Trades → calculator. Add dondags' 2027 1st on one side and a projected playoff team's 2027 1st on the other. **Expected:** the two values differ, and dondags' is higher by roughly the design §5 example. With the flag off, they are equal.
  2. Open the Picks screen. **Expected:** dondags' 2027 1st reads `2027 1.0x · projected` with a low slot such as 1.01–1.03 (or `2027 1.0x (from dondags) · projected` if you hold it), with a higher tier badge than a contender's; a contender's 1st reads e.g. `2027 1.10 · projected`. Every 2027 1st in a forecast league shows a projected slot; a new app build shows `proj_name` with a coloured PROJECTED tag instead of the `· projected` text.
  3. Swipe Find a Trade until a card with a 2027 1st appears. **Expected:** the same tag text as on the Picks screen, and the card's balance agrees with the calculator for the same assets.
  4. Check a 2028 1st and a 2027 2nd. **Expected:** no projected slot, and values unchanged from before the release.
  5. Set knob `pick_projection_weight` to 0 (`scripts/set_knob.py`) and pull to refresh. **Expected:** all 2027 1sts are equal again and read `2027 1st`. Restore the knob.
  6. In an ESPN or MFL league, or one with no forecast. **Expected:** no projected slots and no value changes.
- [ ] **WAIVED because:** n/a. Backend tests, replay and checklist above.
- `testID`s added/renamed: none.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route is added, renamed or contract-changed. `/api/league/picks`, `/api/trade/evaluate` and the trade card keep their shapes; values and the existing `label`/`name` strings change. Add one note to the `/api/league/picks` `label` description |
| `living-memory/LLD.md` | yes | The pick-pricing waterfall gains a step; the "price and label from one resolution" convention extends to the projection |
| `docs/architecture.md` | yes | The league forecast (`league_projections`) now feeds pick pricing. That is a new edge from the advisory sidecar into the trade engine, read-only and cached |
| `living-memory/HLD.md` | yes | Same edge. The sidecar is no longer "separate from trade models" (`HLD.md:245`) |
| `docs/cross-client-invariants.md` | yes | The pick-pricing waterfall table (~line 1180) gains a step, and the label gains the `· proj. early/late` suffix |
| `docs/glossary.md` | yes | "Projected slot value" and "proj. early / proj. late" |
| ADR or `DECISIONS.md` entry | yes | Partial reversal of D-146's "future picks stay default for now", for next-season firsts only. Covers zero-sum normalisation, the weeks-played shrink, and the Max PF draft-order assumption |
| `docs/config-reference.md` | yes | The flag and five knobs |
| `docs/plans/README.md` | yes | Row for this folder (status: active, not built) |

## 5. Ship gate declaration

- **CI green:** `backend-tests`, `mobile-typecheck` and `maestro-testid-lint` on the pushed sha.
- **Evidence recorded:** a `living-memory/TEST_LEDGER.md` entry naming the unit tests, the replay result (aggregate) and the checklist outcome.
- **TestFlight verification:** checklist §3, run by the operator on the current build; outcome logged in TEST_LEDGER.
- Express lane declared by the operator? **No.** And it could not be: this touches a feature-flag surface and changes engine pricing, so it is on the bright line.
