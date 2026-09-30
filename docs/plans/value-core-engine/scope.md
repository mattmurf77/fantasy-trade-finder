# Feature Scope — Value-core trade engine (rebuild)

**Date:** 2026-09-30
**Entry point:** direct ask. The operator decided on 2026-09-30 to rebuild the trade-suggestion engine from scratch. It supersedes the in-place repair plan `docs/plans/trade-suggestion-quality/plan.md` of 2026-09-29, which was never committed to `main`. Two decisions carry over from that plan: which leagues form the bench, and that prod DB reads are authorized.
**Builder:** spec author (this folder); build by 5 parallel work packages per [specs.md](specs.md)
**Operator sign-off on waivers:** **pending.** §3 waives the structural-guard row because there is no mobile or web code change. That waiver must be shown to the operator before build.

Companion docs: [prd.md](prd.md) · [hld.md](hld.md) · [lld.md](lld.md) · [specs.md](specs.md)

---

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [x] **(b) Existing events cover it.** No new event names. Nothing is added to `backend/analytics_taxonomy.py` or `analytics_queries.NON_INTENT_EVENTS`.

  | Existing surface | What the value core writes | Question it answers |
  |---|---|---|
  | `deck_impressions` row per served card (`_log_deck_signal_impressions`, `server.py:5039`) | `model_arm = "value_core"`, `policy_variant = "value_core"`, `policy_version = "value-core-1"`, `arm_rank` = served position, `base_score` = priority, `final_score` = effective priority after repeat penalties, `valuation_json` = the value-core evidence (three scores, weights, market ratio, both windows, per-asset values; schema in [lld.md §7.3](lld.md#73-evidence-schema-deck_impressionsvaluation_json)) | Which score combination produced each served card, so a like, pass or send can be tied back to value, outlook and ranking |
  | `trades_generated` (server-fired, props `count, gen_ms, engine_version, lanes`) | `engine_version = "value_core"`, a new *value* of an existing free-form prop (`server.py:8983` builds the legacy values) | Supply and latency per engine |
  | `match_swiped` / `trade_proposed` / `trade_pass_reasons` | unchanged; joined to the impression through the existing `impression_id` | Outcome per card, including pass reason tags |

  → follow-through: `docs/data-dictionary.md` §`deck_impressions` documents the value-core `valuation_json` shape and the new `model_arm`/`policy_variant` values. §analytics events records `engine_version = "value_core"`. Both are owned by WP5.

## 2. Schema & flag scope

- **New/changed tables or columns: none.** The three scores and weights go into the existing `deck_impressions.valuation_json` Text column. That column already holds per-generator JSON: the policy snapshot at `trade_policy.py:900` and the owner evidence at `server.py:5528`. Nothing here needs a new column, because nothing queries the scores in SQL.
- **New feature flag:** `trade.value_core`, default **false**.
  - Registered in `backend/feature_flags.py` `FLAG_KEYS`, `config/features.json` (with `_comment_value_core`) and `backend/tests/fixtures/flags/release.json`. The last is required by the mirror test `test_seed_ui_test_db.py:107`.
  - Documented in `docs/config-reference.md`.
  - **Graduation criterion**, all four required:
    1. The bench guardrails ([prd.md §6](prd.md#6-success-metrics)) pass on every frozen bench league.
    2. The operator's blind grade averages **≥ 4.0**.
    3. The blind grade beats the incumbent's served cards on the same bench.
    4. Two weeks of tester-only serving with no rise in trade-job errors.
- **New `model_config` keys:** 12 keys, all Float, seeded in `database._MODEL_CONFIG_DEFAULTS` and documented in `docs/config-reference.md`. Full table in [lld.md §3](lld.md#3-configuration).
  - Core: `vc_band`, `vc_stud_premium`, `vc_untouchable_min_ratio`, `vc_max_assets_per_side`, `vc_max_per_partner`.
  - Ranking (the operator's "about 5 settings"): `vc_w_value`, `vc_w_outlook`, `vc_w_rank`, `vc_repeat_penalty`, `vc_player_cap`.
  - Outlook and rollout: `vc_standings_weight`, `vc_testers_only`.
  - Existing keys are reused read-only, not duplicated: `asset_floor_abs`, `filler_min_frac`, `shrink_pseudocount`, `user_elo_shrink`, `placement_tier_clamp`, `infer_contender_cut`, `infer_rebuilder_cut`.
  - **None goes into `trade_service._DEFAULT_CFG`.** That keeps the arm-A golden inventory test (`test_bakeoff_arm_a_golden.py:897`) untouched.
- **Ship-the-knob (deploy-free rollback):**
  1. `trade.value_core` → false, then `POST /api/feature-flags/reload`. The next `/api/trades/generate` runs the old engine: the safety signature changes, so cached value-core decks are not reused.
  2. Rollout lever `vc_testers_only` (default **1**): only the tester allowlist (`experiments.load_tester_allowlist`) is served while the flag is on. Set with `PUT /api/admin/config/vc_testers_only`.

## 3. Evidence scope

- [ ] **Structural guard: WAIVED.** No mobile or web source changes. The value core reuses the card payload clients already render: `give`/`receive`, `give_value`/`receive_value`, `reasons`, `preserve_server_order`, `basis`. Needs operator sign-off.
- [x] **Unit tests.** Full list with fixtures in [specs.md](specs.md):
  - WP1: `backend/tests/test_value_core_core.py`, `test_value_core_perf.py`
  - WP2: `test_value_core_ranking.py`, `test_value_core_deck.py`, `test_value_core_windows.py`
  - WP3: `test_value_core_adapter.py`, `test_value_core_serving.py`
  - WP4: `test_value_core_bench.py`, `test_value_core_recall.py`, `test_blind_grade.py`, `test_value_core_e2e.py`
  - WP5: none (reference docs only)
- [x] **Code-walk proof** (WP3 writes it into this folder as `code-walk.md` at build time). It must cite file:line for three things:
  1. **Flag off leaves the path byte-identical.** The branch in `_run_trade_job` returns False before any work. The safety-signature entry is filtered when off. The impression-logger kwarg defaults to `None`. `prepared_trade_runtime.supported()` is unchanged when off. The owner request hash ignores the new `vc_*` config keys.
  2. **Clients render value-core cards with no change.**
     - `reasons` is shown when `trade_math.human_explanations` is on: `mobile/src/components/TradeCard.tsx:323-325`, `:960`, and `web/js/app.js:4073`.
     - `preserve_server_order` turns off the client session re-rank: `mobile/src/screens/TradesScreen.tsx:2778`, `:4084`.
     - Lane chips hide when no card carries a lane: `TradesScreen.tsx:7332`.
     - `basis` is normalised client-side: `mobile/src/api/trades.ts:183`.
  3. **Swipes on value-core cards resolve.** Cards are registered in `trade_service._trade_cards` (the lookup is at `server.py:16617`) and reconstruct from echoed context (`server.py:15660`).
- [x] **Manual TestFlight checklist** (operator runs it with the flag on and `vc_testers_only = 1`):
  1. Open **Trades** for La Resistance. Expected: the deck loads in under 10 s. In the first 30 cards no trade idea repeats (the same partner and headliners with only minor pieces or pick years swapped), no acquisition is shown twice (the same player, or "a pick", from the same partner), and no partner has more than its share (4 of 30 in a 12-team league). The prod baseline was one player in 27 of 30.
  2. Scroll the first 10 cards. Expected: each card shows 1–3 reason lines in the value · outlook · ranking style, e.g. "Fair on value", "Fits their rebuild", "You rank X 12 spots above market". The value bar shows "give" and "get" totals.
  3. Like one card, then pass one with the reason "I'm giving up too much". Expected: no error toast. Reopen Trades and confirm the passed card does not return.
  4. On one card, open **Send in Sleeper** without sending. Expected: the package pre-fills exactly as on the card.
  5. Open Trades for Newton Dynasty (ESPN, no standings). Expected: the deck still loads, and outlook reasons still appear from roster age and picks.
  6. Use "What can I get for X?" on one of your players. Expected: every card includes X.
  7. Set a trade intent (e.g. Consolidate). Expected: the deck comes from the **legacy** engine, and no value-core reason style appears. This is a v1 limitation, and this step checks it.
  8. Flip `trade.value_core` off and reload flags, then reopen Trades. Expected: the legacy deck returns within one regenerate.
- `testID`s added or renamed: **none.**

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated (WP5).** No route added or renamed, but the card payload contract changes additively. | §`### Trade card object` (`api-reference.md:440`): add a "Value-core cards" paragraph: `trade_id` prefix `vc_`, `basis: "consensus"`, `preserve_server_order: true`, `reasons` built from the three scores, no `lane`/`narrative`/`match_context`. §Trades route table row for `/api/trades/generate` (`:357`): note that the engine is chosen by `trade.value_core` + `vc_testers_only`, and that intent-mode requests stay legacy. |
| `living-memory/LLD.md` | **updated (WP5)** | New section "Value-core engine seams". The rules to record: it is a leaf package that never imports `server`; flag off means it is never imported; one branch point in `_run_trade_job`; evidence schema v1 on every row; no silent legacy fallback. |
| `docs/architecture.md` | **updated (WP5)** | New section before "Data flow" (`architecture.md:258`), plus a row in the Components/Backend table (`:376`). |
| `living-memory/HLD.md` | **updated (WP5)** | Major Components row (`HLD.md:80-99`), plus a "Flow C′ — value-core deck" paragraph under Key Flows (`:140`). |
| `docs/cross-client-invariants.md` | **n/a.** No constant, enum or color shared with clients changes. `basis` values stay within the existing `"consensus"`/`"divergence"` set. | — |
| `docs/glossary.md` | **updated (WP5)** | New terms: value core, fair pool, fairness band (value core), stud premium, irreducible trade, priority, value score, outlook score, rank score, repeat penalty, trade idea, acquisition round, bench guardrails, blind grade. |
| ADR or `DECISIONS.md` entry | **ADR by WP5; DECISIONS entry by the lead at integration** | `docs/adr/adr-024-value-core-engine.md` records the choices: value-only core plus a separate 3-weight ranking; the new deck bypasses the stacked legacy gates; no silent fallback. `living-memory/DECISIONS.md` gets **D-195** (grep for max+1 first). It records the operator's 2026-09-30 rebuild decision and that, while the flag is on, it supersedes D-193's ordering for value-core decks. |
| `docs/data-dictionary.md` | **updated (WP5)** | `## deck_impressions` (`data-dictionary.md:490`): the value-core `valuation_json` v1 shape and the `model_arm`/`policy_variant`/`policy_version` values. The `trades_generated` props line (`:1357`): add `engine_version = "value_core"`. |
| `docs/runbook.md` | **updated (WP5)** | New section "Value-core bench (freeze / run / recall / blind grade)". |

## 5. Ship gate declaration

- **CI green:** `backend-tests`, `mobile-typecheck` (which also runs the `check-*.js` suites) and `maestro-testid-lint`, all passing on the pushed sha. The mobile jobs are unaffected, since no mobile files change.
- **Evidence recorded:** a `living-memory/TEST_LEDGER.md` entry, written by the lead. It names:
  - the pytest counts;
  - the flag-off byte-identity check ([specs.md §6](specs.md#6-integration-checklist-lead));
  - the flag-on smoke run on the synthetic 12-team league;
  - the bench guardrail numbers on the frozen bench leagues, once the operator has frozen them.
- **TestFlight verification:** the checklist in §3, run by the operator with the flag on for testers only. The outcome is logged in TEST_LEDGER.
- **Express lane declared by the operator?** **No.** This change touches a feature-flag surface, model_config keys and the analytics payload, so full gates apply.
