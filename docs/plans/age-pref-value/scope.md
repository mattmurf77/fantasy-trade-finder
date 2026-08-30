# Feature Scope — Age-preference consensus value multiplier

**Date:** 2026-08-29
**Entry point:** direct ask (operator, following docs/business/analytics/2026-08-29-trade-disposition-review.md)
**Builder:** Claude session (trade-disposition-review worktree)
**Operator sign-off on waivers:** not needed (no waivers)

---

## What & why (one paragraph)

The 2026-08-29 trade-disposition review measured a strong, consistent age
preference across all serving arms: cards asking the user to **give an
under-23 player run a 9% like rate** (1/11) and cards **delivering a 30+
player run 14%** (2/14), while the mirror shapes (receive youth 49%, ship age
58%) are the deck's best performers. Operator decision: do **not** filter
these shapes — multiply the players' *values* so the disliked shapes price
themselves out ("treated higher value"), **with a maximum on the value
increase**. Implemented as a symmetric age multiplier on the **consensus
value accessor** used by deck generation: u23 assets ×`age_pref_mult_u23`
(boost capped at `age_pref_boost_cap` value points), 30+ assets
×`age_pref_mult_30plus`, ages 23–29 and picks untouched. One multiplier
produces all four measured preferences: giving u23 requires more back,
receiving 30+ credits less gain, receiving u23 and shipping 30+ get easier.

**Scope of application:** the three deck-generation consensus accessors —
`trade_service._generate_trades_impl._vs` (arms current + challenger, v2
pair path), `trade_optimizer.generate_pair_trades_v3._sv` (v3 package path),
`trade_gen_v2.generate_league_suggestions.cval` (arm gen_v2). **Not**
applied to: user/opponent board values (a user's own board is their stated
opinion; we don't editorialize it), the likes-you injector (user-driven
mutual likes, arm NULL), asset-ideas / fair-packages / calculator surfaces,
and the dark fit arm. Age bands reuse the taste_service cut points
(u23 = age<23, 30plus = age≥30) so the knob tunes against the same buckets
the evidence was measured in.

## 1. Analytics scope

- [x] **(b) Existing events cover it:** the F1 impression spine already
  freezes `taste_attrs` age buckets (`giveage:*`/`recvage:*`) into
  `deck_impressions.features_json` at serve time, and dispositions land in
  `deck_outcomes` / `trade_pass_reasons`. The exact query set in
  docs/business/analytics/2026-08-29-trade-disposition-review.md re-measures
  the effect after this ships — no new events needed.

## 2. Schema & flag scope

- New/changed tables or columns: **none**
- New/changed feature flags: **none** (deliberate — the kill lever is the
  knobs themselves, hot-reloadable via `PUT /api/admin/config/<key>`)
- New `model_config` keys (all three registered in `trade_service._DEFAULT_CFG`,
  `database._MODEL_CONFIG_DEFAULTS`, `_PINNED_KNOBS`, `docs/config-reference.md`):

  | Key | Default | Meaning |
  |---|---|---|
  | `age_pref_mult_u23` | 1.10 | consensus-value multiplier for players under 23 |
  | `age_pref_mult_30plus` | 0.90 | consensus-value multiplier for players 30+ |
  | `age_pref_boost_cap` | 500.0 | max absolute value-space INCREASE from an age boost (≈ half a mid-1st); ≤0 = uncapped; never caps decreases |

  **Ship-the-knob rollback:** set both mults to 1.0 → the helper
  short-circuits and every accessor is byte-identical to pre-feature
  (deploy-free revert). Arm A (baseline) pins both mults at 1.0 in
  `MODEL_A_PROFILE` — the pre-wave engine had no age preference; the cap is
  deliberately absent from the profile (unread while both mults are 1.0 —
  same rule as `package_floor_cross`).

## 3. Evidence scope

- [x] **Unit tests:** `backend/tests/test_age_pref.py` — band boundaries
  (22/23/29/30), boost cap engagement, decrease-never-capped, identity at
  kill values (exact float equality), pick/no-age pass-through, and the
  arm-A profile pin. Plus the existing `test_bakeoff_arm_a_golden.py` suite
  proving arm A is unmoved (golden stands un-recaptured — pins are identity
  values).
- [x] **Code-walk proof:** the three accessor seams —
  `backend/trade_service.py` `_vs` (consensus accessor built from `seed_elo`,
  feeds every v2 gate incl. the #108 `rv - gv >= user_gain_epsilon` consensus
  user-gain gate at `eval_consensus_package` and the `_emit` closures),
  `backend/trade_optimizer.py` `_sv` (v3 twin), `backend/trade_gen_v2.py`
  `cval` (gen_v2 twin). Each wraps `elo_to_value(seed_elo.get(pid, 1500.0))`
  with `age_pref_value(v, players.get(pid))`. Boost on the give side raises
  `gv` → the gate `rv - gv < user_gain_epsilon` kills more give-u23 shapes;
  discount on the receive side lowers `rv` → same for 30+-receive shapes.
  Cards are *re-priced*, never filtered — exactly the operator's ask.
- [ ] Manual TestFlight checklist: **not needed** — backend-only scoring
  change; the deck renders identically, only which cards clear gates and
  their displayed values shift.
- `testID`s added/renamed: none

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added/changed |
| `living-memory/LLD.md` | n/a | no schema/route/invariant convention shift; knob registration follows the existing five-registration discipline |
| `docs/architecture.md` | n/a | no module wiring change |
| `living-memory/HLD.md` | n/a | no architecture shift |
| `docs/cross-client-invariants.md` | n/a | backend-only; no shared constant/enum/color |
| `docs/glossary.md` | n/a | no new domain term (age bands already defined by taste_service) |
| `docs/config-reference.md` | updated | three new model_config rows |
| `DECISIONS.md` | updated | D-entry: symmetric consensus-side multiplier, not a filter; user boards untouched |
| `docs/plans/three-model-bakeoff/scope-phase2.md` | updated | arm-A disposition sentence for the three knobs |

## 5. Ship gate declaration

- **CI green:** backend-tests + mobile-typecheck + testid-lint on the pushed sha
- **Evidence recorded:** TEST_LEDGER entry naming `test_age_pref.py` + arm-A golden result
- **TestFlight verification:** n/a (no checklist — backend-only)
- Express lane declared by the operator? **no** — full gates run
