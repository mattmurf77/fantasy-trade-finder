# Outlook × age machinery — code map

> **Purpose:** file:line-cited inventory of the built (mostly dark) outlook/age machinery, for the
> outlook-age plan. Companion to [outlook-age-grounding.md](outlook-age-grounding.md) (measured
> facts). Everything is code-verified against this worktree's checkout of `main` (`69dc0cae`)
> unless marked assumed.

## Contents

- [Flag inventory](#flag-inventory)
- [`trade.outlook_blend` — the age×window value multiplier (dark)](#tradeoutlook_blend--the-agewindow-value-multiplier-dark)
- [`trade.outlook_direction` (#175) — the pick-flow reranker (dark since 08-20)](#tradeoutlook_direction-175--the-pick-flow-reranker-dark-since-08-20)
- [The two classifier-only flags](#the-two-classifier-only-flags)
- [Live outlook plumbing](#live-outlook-plumbing)
- [Pick-direction machinery — the gap](#pick-direction-machinery--the-gap)
- [Age data quality caveats](#age-data-quality-caveats)
- [Bake-off / golden / test interactions](#bake-off--golden--test-interactions)
- [Prior docs and rulings](#prior-docs-and-rulings)
- [Lighting requirements per flag](#lighting-requirements-per-flag)

## Flag inventory

| Flag | State | Note |
|---|---|---|
| `trade.outlook_blend` | **dark** (features.json:31) | The age lever |
| `trade.outlook_direction` | **dark** (features.json:62) — was LIVE until 2026-08-20, operator flip-off as "experiment #1" | The pick-flow reranker |
| `trade.outlook_net_firsts` | dark (features.json:77) | Classifier input only |
| `trade.outlook_composite` | dark (features.json:81, D-140) | Classifier re-weighting only |
| `trade.outlook_infer` / `trade.outlook_seed` | **live** | Opponent labels / user outlook seed |
| `trade.lanes` / `trades.intent_modes` / `trade.picks_in_pool` | live | Labels / tier-shape intents / pick pseudo-assets |

## `trade.outlook_blend` — the age×window value multiplier (dark)

Tier-2 item 2.2 (plan: docs/plans/trade-engine-tier2-models.md:70–96).
`outlook_blend_mult(pos, age, α) = α·age_now_mult + (1−α)·age_future_mult`
(trade_service.py:3180–3184). Curves are code constants, deliberately not config
(trade_service.py:3114–3120):

- `_AGE_NOW_CURVE` (3124–3136): QB 0.95 <23 else 1.0; RB 0.95 <23, 1.05 23–26, then
  `max(0.60, 1.05 − 0.12·(a−26))`; WR 0.92 <23, 1.0 23–29, then `max(0.65, 1.00 − 0.10·(a−29))`;
  TE 0.90 <24, 1.0 24–31, then decay.
- `_AGE_FUTURE_CURVE` (3138–3144): QB 1.05 ≤25 then −0.05/yr; RB 1.10 ≤23 then −0.12/yr (floor
  0.40); WR 1.10 ≤24 then −0.09/yr; TE 1.05 ≤25 then −0.08/yr.
- Missing age / unknown pos ⇒ 1.0 (3147–3160).

α from `outlook_alpha(outlook)` — five `model_config` knobs (trade_service.py:284–288;
database.py:2413–2417): championship **1.00**, contender **0.75**, not_sure/None **0.50**,
rebuilder **0.25**, jets **0.10**.

**Application when lit:** user side — multiplies the whole shrunk personal value map
(trade_service.py:5651–5665); opponent side — `alpha_opp` resolved per member
(declared-else-inferred, 5809–5821, gated on `_blend_values` 5718–5719) and applied inside `_vo` in
both v2 (6196–6212) and v3 (trade_optimizer.py:310–326), propagating into marginal-value math.

**Not touched:** consensus/fairness values (`_vs`, 5667–5674; golden
`test_fairness_gate_golden.py:224–245` "FR8 — outlook moves surpluses, not fairness"); consensus
generator (`_consensus_kw` passes no alpha, 5825–5848 — **so the blend never reaches
consensus-basis cards, ~62% of decided cards**); gen_v2 (no `outlook_alpha` import — the
features.json comment citing gen_v2:986 is stale); **picks** (curves key QB/RB/WR/TE only, and
pick pseudo-assets carry age=0 → 1.0 both curves; server.py:11355–11365, trade_service.py:3149–3158)
— so the blend re-prices players only, and any pro-pick rebuilder tilt is *relative* (players
deflate, picks hold).

## `trade.outlook_direction` (#175) — the pick-flow reranker (dark since 08-20)

`outlook_direction_mult(give, recv, players, outlook, value_of)` (trade_service.py:3303–3403), on
**consensus** values. `shift` = value-weighted mean now-lean of what changes hands (received +,
given −); `_now_lean(pos, age) = now_mult − future_mult`, and **PICK is a fixed −0.25 now-lean**
(3198–3206) — the only pick-timeline encoding in the engine.

- not_sure/None ⇒ 1.0 (3351–3353).
- Contend side: mild mirror `max(0, 1 + 0.5·shift)` only (3368–3369).
- Rebuild side: acquiring win-now ⇒ `max(0.05, 1 − 3.0·shift)`; acquiring picks/youth ⇒
  `1 + 1.0·(−shift)`; plus the ~1-year age-gap rule (3377–3402): older primary return with no
  pick/young rescue component ⇒ ×0.15.
- **Composite multiplier, never a kill** (3342–3343). Knobs `outlook_dir_*`
  (database.py:2488–2493).
- Deck half (5971–5993): applied uniformly to divergence AND consensus cards after all gates,
  `c.composite_score *= mult`, stamped `c.outlook_dir` (QA-only).

Status doc: docs/feedback/items/175-outlook-directional-suggestions/ ("built + tested, DARK" —
merge-state prose stale, code is on main). D-060 left a folding TODO (dedupe shift arithmetic into
`signed_lane_shift`).

## The two classifier-only flags

- **`trade.outlook_net_firsts` (#365):** adds `−infer_w_net_firsts × net_share` (selling firsts
  reads as contending) to `infer_team_outlook`, **only when a caller supplies a first-round
  ledger** — today only `GET /api/league/team-review` builds one (server.py:25547–25551). Flip
  alone moves the Team Review beat, zero decks (tested invariants, test_window_signals.py:176–180).
- **`trade.outlook_composite` (#372, D-140):** re-weights the classifier (vet/youth 1.0→0.4, +
  starter-value 0.6 and playoff 0.4 indices) **only when a `starter_signal` is supplied** — again
  Team Review only. Prod-verified to fix the operator's all-in-called-rebuilder case
  (features.json:80). Wiring either into the engine callers is an explicit second change with full
  deck blast radius.

## Live outlook plumbing

- Declared: `league_preferences.team_outlook`, enum {championship, contender, rebuilder, jets,
  not_sure} (database.py:8974); written by `POST /api/league/preferences` + four Team Review beat
  actions.
- User at job time (server.py:5854–5898): declared, else `trade.outlook_seed` infers.
- Opponents (server.py:5915–5946; loop trade_service.py:5809–5821): declared wins, else
  `infer_team_outlook` — today label-only (`match_ctx["opponent_outlook"]`, 5821).
- `infer_team_outlook` (3634–3865): score = `vet_share − youth_share − 2·(pick_share − 1/teams)`;
  cuts ±0.08; **never infers championship/jets** (declaration-only extremes).
- R5 reads outlook (2422–2423, 2484–2487): rebuilder/jets/unresolved ⇒ gate off; and R5 judges
  received **players** only — picks skipped, pick-primary cards exempt (2425–2434).
- `classify_lane` (3187–3266): labels only; `lane_shift` stamped unconditionally (5994–6004);
  fit-congruence K-weighting reuses the shift (D-060).

## Pick-direction machinery — the gap

**No live code path biases pick direction by outlook.** R3 is outlook-blind and symmetric; R2
excludes picks; v3 `_try_sweeten` adds players only (trade_optimizer.py:786–787); the gap
auto-sweetener can use a pick as equalizer but chooses the side by value gap, never outlook;
gen_v2's outlook usage is rationale-label only (`_timeline_fit`, trade_gen_v2.py:951–959);
`trade_intent` values (consolidate / tier_up / tier_down) are pick-blind (4371–4400). The only
pick-direction-aware scorer is dark `outlook_direction_mult` — and grounding Finding 5 shows
reordering alone never fixed the served mix.

## Age data quality caveats

- `players.age` from the Sleeper dump, None on failure (database.py:9312–9316).
- **Pool hydration defaults missing age to 25** (`or 25`, server.py:1599, 1618) — an ageless
  player is priced near-peak on every curve; the curves' "no age ⇒ 1.0" branch is mostly
  unreachable through the pool. Real caveat for any age-bias lighting.
- Picks carry age=0 (server.py:11355–11365); their only timeline encoding is the −0.25 now-lean
  constant and the pick ladder's year pricing.

## Bake-off / golden / test interactions

- `MODEL_A_PROFILE` / challenger profile pin **no** outlook knobs; the arm-A knob-inventory guard
  dispositions the classifier weights as double-gated (test_bakeoff_arm_a_golden.py:462–469).
- **The bake-off goldens are pinned to `trade.outlook_direction: True`**
  (tests/support/bakeoff_harness.py:80–91; test_negmem_seams.py:111–115) — captured while the flag
  was lit. Re-lighting matches the pinned state; changing its knobs or lighting `outlook_blend`
  needs re-capture review.
- Retarget/review list if lighting: test_trade_tier2.py, test_opponent_outlook_infer.py,
  test_outlook_direction.py (full #175 suite), test_trade_phase2.py:177 (label-only contract —
  rewritten if blend lights), test_fairness_gate_golden.py FR8 (must KEEP passing — safety
  property), flags fixtures (release-300.json / release-espn-send-off.json still carry
  outlook_direction: true).

## Prior docs and rulings

| Doc | Status |
|---|---|
| docs/plans/trade-engine-tier2-models.md | Originating blend design (2.2); built as specced |
| docs/feedback/items/175-outlook-directional-suggestions/ | #175 PRD/status; dark |
| docs/feedback/items/365-window-signals/ · 372-window-composite/ | Classifier flags; graduation owes the #365 TestFlight checklist |
| D-060 / D-093 / D-094 / D-110 / D-140 | Fit-congruence; odds dark→lit; net-firsts; composite |
| **2026-07-17 operator interview ("age = tiebreak")** | The standing ruling that keeps value-editing OFF — encoded at trade_service.py:5710–5716. **Lighting `outlook_blend` reverses it and needs an explicit operator overturn recorded in DECISIONS** |
| 2026-08-20 direction flip-off | CHANGELOG entry (experiment #1, `fit_outlook` share) — readout now in grounding Finding 6 |

## Lighting requirements per flag

- **`outlook_blend`:** flip alone re-prices every divergence-basis deck for non-not_sure outlooks
  (user + opponent sides); consensus cards, fairness, picks untouched. Tests exist; **no offline
  replay or deck-quality read exists**; reverses the age-tiebreak ruling (operator overturn
  required); age-default-25 caveat applies.
- **`outlook_direction`:** flip restores pre-08-20 behavior exactly; strongest evidence base (full
  suite + 3+ weeks live) but its own experiment metric argues against as-is re-light (grounding
  Finding 6), and Finding 5 shows it cannot fix pick flow alone. Pure reranker ⇒ F8-replayable
  offline.
- **`outlook_net_firsts` / `outlook_composite`:** flip alone = Team Review only; engine wiring is
  a second, full-gates change. Composite-into-engine would improve rebuilder *detection* (the
  operator's own team was misclassified rebuilder by the legacy vector) — a prerequisite worth
  weighing before any outlook-conditioned engine behavior leans harder on inferred outlooks.
