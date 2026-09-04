# Feature Scope — Personal rankings with market-fairness guardrails (`personal_market_v1`)

**Date:** 2026-09-04
**Entry point:** direct ask — `TRADE_ENGINE_BALANCE_ENGINEERING_BRIEF.md` (2026-09-04)
**Builder:** Claude Code session `claude/fleeced-trade-engine-balance-c0c75d`
**Operator sign-off on waivers:** not needed (no waivers — every section answered)

**Stage implemented in this change:** brief Phase 1 (telemetry + confidence) and the
Phase 2 shadow scaffolding. **Nothing is enabled for production users.** Both new flags
default `false` in code *and* in `config/features.json`; no experiment allocation changed;
no migration run against production.

---

## 0. The decision this encodes

Consensus value stops being 30% of one blended objective and becomes a **non-bypassable
eligibility guardrail**. Personal rankings become the **primary selection and ordering
signal** among the trades the market already considers plausible. Ranking **confidence**
— symmetric across both managers — controls how far the engine may depart from consensus.

Generator and policy are **orthogonal** attribution dimensions:

| Dimension | Values | Question |
|---|---|---|
| `model_arm` | `baseline`, `current`, `challenger`, `gen_v2`, `fit` | Which generator produced the card? |
| `policy_variant` | `legacy`, `personal_market_v1` | Which eligibility/ranking/deck policy governed the job? |

No fourth generator is created; no arm is removed or repurposed; `MODEL_A_PROFILE` is
untouched (guarded by `backend/tests/test_bakeoff_arm_a_golden.py` and by a new explicit
assertion in `test_trade_policy.py`).

---

## 1. Analytics scope

- [x] **(b) Existing events cover the user-facing surface.** No new client event is added.
      `trades_generated`, `trade_card_swiped`, `trade_sent` / `sleeper_send_succeeded` and
      the `deck_outcomes` action set (`viewed` / `like` / `pass` / `not_interested` /
      `propose` / `undo`) already answer every question this change asks of the client.
- [x] **(a) New *stored* telemetry** — server-side only, no taxonomy entry needed because
      nothing new is emitted through `POST /api/events`:

  | Store | Contents | Written when | Writer |
  |---|---|---|---|
  | `deck_impressions.valuation_json` | frozen serve-time valuation snapshot (schema v1) | every served / shadow / ghost impression while `trade.valuation_telemetry` is on | `server._log_deck_signal_impressions` |
  | `deck_impressions.trade_concept_id` | canonical perspective-independent concept hash | same | same |
  | `deck_impressions.policy_variant` | `legacy` \| `personal_market_v1` | same | same |
  | `deck_impressions.source_like_impression_id` | the mirror-like that caused an injection | likes-you injection only | same |
  | `trade_policy_shadow` | one row per **rejected** treatment candidate: arm, variant, reason, ratio, floors | shadow evaluation, telemetry flag on | `server._evaluate_deck_policy` |
  | `trade_proposals` | durable record of a confirmed provider send | after provider success on all three send routes | `server._record_trade_proposal` |
  | `trade_matches.*` (7 new columns) | both impression links, both like times, latency, match-time snapshot | on match creation | `database.create_trade_match` |
  | `trade_decisions.impression_id` / `.trade_concept_id` | attribution for new decisions | every new like/pass write | `database.save_trade_decision` |

  → follow-through: `docs/data-dictionary.md` updated for all of the above.

  **Taxonomy note:** `analytics_taxonomy.py` is *not* touched. Every row above lands in a
  product table through an existing writer, not through the `/api/events` pipeline, so
  there is no event name to register and no `NON_INTENT_EVENTS` classification to add.

## 2. Schema & flag scope

### New / changed columns (all nullable, all additive, all in `_migrate_db`)

| Table | Column | Type | Notes |
|---|---|---|---|
| `member_rankings` | `comparison_count` | INTEGER | pairwise/trio votes behind this Elo |
| `member_rankings` | `confidence_weight` | FLOAT | `n/(n+shrink_pseudocount)` or the source constant |
| `member_rankings` | `confidence_source` | VARCHAR | `votes` \| `seed` \| `cross_format` \| `explicit` |
| `deck_impressions` | `valuation_json` | TEXT | schema-v1 snapshot |
| `deck_impressions` | `trade_concept_id` | VARCHAR | canonical mirror-join key |
| `deck_impressions` | `policy_variant` | VARCHAR | `legacy` \| `personal_market_v1` |
| `deck_impressions` | `source_like_impression_id` | VARCHAR | non-null ⇒ injected because of a mirror like |
| `trade_decisions` | `impression_id` | VARCHAR | |
| `trade_decisions` | `trade_concept_id` | VARCHAR | |
| `trade_matches` | `trade_concept_id` | VARCHAR | |
| `trade_matches` | `user_a_impression_id` | VARCHAR | |
| `trade_matches` | `user_b_impression_id` | VARCHAR | |
| `trade_matches` | `first_like_at` | VARCHAR | ISO UTC |
| `trade_matches` | `second_like_at` | VARCHAR | ISO UTC |
| `trade_matches` | `match_latency_seconds` | FLOAT | denormalized audit field |
| `trade_matches` | `match_valuation_json` | TEXT | third snapshot, re-evaluated at match time |

**No backfill.** Historical board state no longer exists; a fabricated confidence or
valuation would be misleading. Legacy NULL confidence reads as **low confidence**
(`confidence_source = "legacy"`, weight 0.0), never as full trust.

### New tables

- `trade_proposals` — durable final-package record, idempotent on `proposal_event_id`
  (unique) and, when present, `provider_transaction_id` (unique).
- `trade_policy_shadow` — rejected-candidate ledger so the treatment's denominator does
  not silently shrink.

### New feature flags — both default `false` everywhere

| Flag | Governs | Graduation criterion |
|---|---|---|
| `trade.valuation_telemetry` | valuation snapshots, concept ids, policy-variant stamping, shadow evaluation, proposal records, match attribution | ≥99% of new divergence impressions carry parseable `valuation_json`; recomputed ratio within 0.001 of stored fairness; p95 generation latency +≤5% |
| `trade.personal_market_policy_v1` | the evaluator actually **gates and orders** (Phase 3) | only after the telemetry flag's criteria pass and an operator-approved crossover schedule exists |

Splitting the brief's single `trade.personal_market_policy_v1` into two is deliberate:
the brief's own rollout has telemetry (Phase 1) shipping *before* any eligibility change
(Phase 3), and a single flag cannot express "measure but do not change".

### New `model_config` keys (Float only — the table has no other type)

| Key | Default | Meaning |
|---|---:|---|
| `market_floor_absolute` | 0.65 | no finder card may ever fall below this ratio |
| `market_floor_one_board` | 0.85 | floor when the opponent has no real board |
| `market_floor_two_board_base` | 0.80 | starting floor for two real boards |
| `market_floor_confidence_discount` | 0.10 | max floor relief bought by confidence |
| `market_floor_surplus_discount` | 0.05 | max floor relief bought by two-sided gain |
| `market_core_ratio` | 0.80 | Core / Conviction lane boundary |
| `personal_gain_min_frac` | 0.0 | min weaker-side gain fraction for the Conviction lane |
| `conviction_deck_share` | 0.20 | max share of a deck that may be Conviction |
| `deck_core_lead_cards` | 3.0 | the deck's first N cards must be Core |
| `deck_core_min_share` | 0.70 | min Core share of a deck |
| `policy_surplus_norm` | 0.25 | gain fraction that counts as "full" personal strength |
| `conf_source_seed` | 0.0 | confidence for an unchanged consensus seed |
| `conf_source_cross_format` | 0.75 | confidence for a cross-format copied ranking |
| `conf_source_explicit` | 1.0 | confidence for tier / manual order / import / anchor |
| `policy_confidence_band_high` | 0.66 | trade confidence at/above which `confidence_band` reads `high` |
| `policy_confidence_band_med` | 0.33 | …and `medium` (below it, `low`) |
| `policy_shadow_log_cap` | 40.0 | max shadow-rejection rows per deck job |

**Seventeen keys**, all `Float`, all declared in `trade_service._DEFAULT_CFG` **and** seeded
in `database._MODEL_CONFIG_DEFAULTS` with identical values. `_DEFAULT_CFG` is not optional:
`trade_service._c` falls back to `_DEFAULT_CFG[key]`, so a key the policy reads but the map
does not declare would `KeyError` the first time a bake-off arm evaluated a candidate.
**None enters `MODEL_A_PROFILE`** — reasoning recorded in
`docs/plans/three-model-bakeoff/scope-phase2.md`, asserted by
`test_trade_policy.py::test_the_pinned_historical_model_a_profile_is_not_modified`.

**Deploy-free rollback lever:** every knob above is a `model_config` row reachable through
`PUT /api/admin/config/<key>` (`X-Cron-Secret`), which re-runs `reload_config()`. Setting
`trade.personal_market_policy_v1` false in `config/features.json` + `POST
/api/feature-flags/reload` is the flag-level lever.

### Env vars

None added.

## 3. Evidence scope

- [x] **Unit tests:** new `backend/tests/test_trade_policy.py` (evaluator: symmetry,
      dynamic floors, user-preference semantics, missing confidence, range-overlap
      non-rescue, monotonicity, absolute floor, `MODEL_A_PROFILE` immutability) and
      `backend/tests/test_trade_policy_wiring.py` (v2 + v3 + every mutation/injection
      path routed through the evaluator, deck composition, concept identity, timing
      attribution, stale revalidation, proposal idempotency + editing, telemetry
      completeness, and **flag-off byte-identity** for impression rows, card payloads and
      generated decks).
- [x] **Structural guard:** WAIVED — there is no mobile surface in this change. Nothing
      new is serialized to a client while both flags are off, and the mobile client is
      not modified, so a `mobile/tests/check-*.js` pin would have nothing to pin.
- [x] **Code-walk proof:** [code-walk.md](code-walk.md) — file:line trace of the single
      choke point, every bypass path it closes, the flag-off identity argument, and §8's
      record of the one place the two value bases deliberately differ.
- [x] **Analysis contract:** [two-user-funnel.md](two-user-funnel.md) — how each of the
      nine states (never eligible / never generated / rejected / never served / never
      viewed / undecided / passed / liked / matched) is identified, so "A liked and B did
      not" can never again be read as a rejection without confirming B's exposure.
- [x] **Manual TestFlight checklist:** written, **not yet run** —
      [testflight-checklist.md](testflight-checklist.md). Not required to merge (both flags
      off ⇒ no runtime behavior to verify); **required before `trade.valuation_telemetry`
      is enabled in production**, and again before `trade.personal_market_policy_v1`.
      Stage A carries the brief's own release blocker: a successful controlled proposal
      that fails to produce an owned, non-stale impression-linked row.
- `testID`s added/renamed: none (no mobile change).

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | no route added or removed and **no request or response field changes**; the three `/api/trades/propose*` routes gain an additive `trade_proposals` write and `/api/trades/swipe` an additive `trade_decisions` stamp — documented in their entries |
| `living-memory/LLD.md` | updated | §"Trade policy evaluator" — new leaf module + the one-choke-point convention |
| `docs/architecture.md` | updated | `backend/trade_policy.py` added to the module map and to the trade-generation data flow |
| `living-memory/HLD.md` | updated | new backend module + the policy/generator orthogonality |
| `docs/cross-client-invariants.md` | updated | `value_basis`, `confidence_band`, `opportunity_label` enum strings reserved for the Phase-3 client contract; fairness terminology fixed |
| `docs/glossary.md` | updated | market ratio, personal opportunity, package confidence, policy floor, Core / Conviction / Fallback, trade concept id |
| ADR / `DECISIONS.md` | updated | `D-180` — consensus is a constraint, not an objective; `D-181` — policy is an orthogonal experiment dimension, not a fourth arm |
| `docs/data-dictionary.md` | updated | all 16 new columns + 2 new tables |
| `docs/config-reference.md` | updated | 17 new `model_config` keys + 2 new flags, with the rollback ladder |
| `docs/runbook.md` | updated | telemetry health counters + what to do when they climb |
| `living-memory/OPEN_QUESTIONS.md` | updated | `Q-038` (the policy and the generators judge "both managers gain" on two different value bases), `Q-039` (concept-id identity in a co-owned league) |
| `docs/plans/README.md` | updated | index row, status **built, DARK** |
| `docs/plans/three-model-bakeoff/scope-phase2.md` | updated | the arm-A exclusion decision for all 17 knobs, as its `_PINNED_KNOBS` guard demands |
| `backend/CLAUDE.md` / `backend/tests/CLAUDE.md` | updated | module-map row + test-cluster row |

## 5. Ship gate declaration

- **CI green:** `backend-tests` (`python -m pytest backend/tests -q`) must pass on the
  pushed sha. `mobile-typecheck` and `maestro-testid-lint` are unaffected (no mobile
  change) but still gate the merge.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry naming the suites run and
  what they proved, including the flag-off byte-identity assertions.
- **TestFlight verification:** not required at this stage (both flags off). Required
  before the telemetry flag is enabled — checklist written, not yet run.
- **Express lane declared by the operator?** No. Full gates apply — this change touches
  schema, API semantics, feature-flag surface and stored telemetry, which the root
  CLAUDE.md bright line explicitly excludes from express.
- **Production migration:** `_migrate_db()` is idempotent and runs at boot. It is **not**
  run manually against production by this session. The operator deploys when ready.
