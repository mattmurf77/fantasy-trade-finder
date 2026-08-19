# Feature Scope — C4b give-side headliner cap (`deck_give_headliner_cap`)

**Date:** 2026-08-19
**Entry point:** operator report — "If there's a specific player that the model likes for trading, Davante Adams… the model will spit out 4 or 5 varieties of offers with Davante included."
**Builder:** session agent (branch `fix/deck-give-headliner-cap`)
**Operator sign-off on waivers:** not needed — the one waiver (§1c) is the same one C4 took.

---

## 0. The defect, measured

Production deck `deck_job_id = 2740a7fc5ac04988b3d42237f9a974a6`, 22 cards, all
1-for-1:

| Give player | Cards |
|---|---|
| `2133` (Davante Adams) | 6 |
| `1466` | 6 |
| `4892` (Baker Mayfield) | 5 |
| three others | 5 combined |

**17 of 22 cards were three players.**

C4 (`deck_headliner_cap`, default 2) was ON — no `model_config` row exists, so
the code default governs — and killed **nothing**. Root cause, confirmed against
the `deck_impressions.centerpiece_id` actually stamped on that deck (22 cards,
**20 distinct centerpieces**):

`trade_service.deck_centerpiece` maxes over **give + receive combined**, and
unknown assets default to 1500.0. On "give Adams, receive a 2028 1st" the *pick*
outranks Adams, so the **pick** is the centerpiece — and every card offers a
**different pick slot**, so every card gets a unique key and a cap of 2 can never
fire:

```
centerpiece=1312140920132497408_2028_1_1   give=['2133'] recv=['1312140920132497408_2028_1_1']
centerpiece=1312140920132497408_2028_1_4   give=['2133'] recv=['1312140920132497408_2028_1_4']
…6 Adams cards, 6 distinct centerpieces
```

This was getting worse, not better: `8b7689a` (D-079, same night) lifted every
1st to Elo ~1650, so picks now out-Elo *more* players and headline more often.

## 0.1 Design decisions

**(1) `deck_centerpiece` is left byte-for-byte untouched.** It is THE shared
definition — `deck_impressions.centerpiece_id` is written with it and
`server._fatigue_centerpiece` delegates to it for decline-time fatigue
suppression (`fatigue_decline_suppress_days`, the ±`fatigue_decline_value_band`
match). Re-keying it would silently re-key fatigue matching against every row
already written, changing which past declines suppress which future cards, for a
reason that has nothing to do with this bug. C4b is an **additional** cap on an
**additional** function, `deck_give_headliner`. Pinned by
`test_deck_centerpiece_definition_is_untouched_by_c4b`.

**(2) Give-side headliner = highest seed Elo among the give assets, players
preferred over picks, id tie-break.** Two departures from `deck_centerpiece`:

* *Give side only* — "what am I being asked to send" is the repetition the user
  feels, and it is what the operator described.
* *Players outrank picks* — a pick headlines only an all-pick give side. Letting
  a pick headline is precisely what made C4 inert; without this rule a
  "give Adams + a 2028 1st" card would key on the pick again. Measured cost of
  the preference across 66 live candidate pools: **0.4 pp** of card loss (most
  give sides are all players anyway) — so it is free insurance against the
  failure mode that produced this ticket.

**(3) Default 3.** Measured across the 66 live candidate pools ≥20 cards (see
§0.2): a cap of 2 costs 23.8 % of served cards; 4 barely touches the complaint
("4 or 5 varieties" survives at 4); 3 costs 10.1 % and takes the per-deck worst
case from a median of 6 (max 13) to exactly 3. C4's default is 2, but C4 keys on
a near-unique-per-card definition and therefore almost never binds — a give-side
cap binds hard and needs more headroom.

**(4) Knob `deck_give_headliner_cap`, kill value `0`.** Same naming shape and
same kill semantics as `deck_headliner_cap`: `0` returns the input list
unchanged, so pre-C4b behaviour is byte-identical. Pinned by
`test_give_headliner_cap_kill_value_leaves_every_card` and by `_KILL_ALL` in
`test_engine_quality_golden.py`. Also inert when the job carries no seed map —
with no consensus every asset ties at 1500 and "headliner" would degenerate to
"largest player id", exactly the rule C4 already follows.

**(5) Leave-short, never backfill.** A dropped card is not replaced. Backfilling
from the same pool would put the same headliner straight back, which is the
defect; backfilling from elsewhere would hide the shortfall from
`bakeoff_runs.groups_json[...].short`. Same policy `compose_group` already uses
for lane quotas (D-078). The deck-size cost is measured and stated below rather
than papered over.

## 0.2 Deck-size impact — measured, not asserted

Read-only against prod `deck_candidate_sets.candidates_json` (the post-gate pool
each deck was actually drawn from), 66 pools of ≥20 candidates, 1,925 served
cards. Simulation replays the cap over each pool in `base_score` order and takes
the first `served_n`:

| Cap | Cards lost | Deck size (median) | Per-deck max repeat (median → after) | Decks below `_DECK_MIN_CARDS` (5) |
|---|---|---|---|---|
| 2 | 458 / 1925 (23.8 %) | 29 → 24 | 6 → 2 | 0 |
| **3 (shipped)** | **194 / 1925 (10.1 %)** | **29 → 26.5** | **6 → 3** | **0** |
| 4 | 62 / 1925 (3.2 %) | 29 → 28 | 6 → 4 | 0 |

At the shipped default: 19 of 66 decks are unchanged; the worst single deck loses
12 cards (36 → 24); 3 decks fall below 20 cards; **none** approaches the
`_DECK_MIN_CARDS = 5` floor `server.py` enforces downstream. Per-deck max repeat
before: `{3:1, 4:13, 5:16, 6:14, 7:7, 8:1, 9:4, 10:2, 11:3, 12:2, 13:3}`. After:
`{3:66}`.

**Group starvation:** the cap runs inside generation (`_dedup_and_sort` /
`gen_v2_cards`), *upstream* of `bakeoff_runner.compose_group`, so a thinner arm
list shows up as a smaller group `pool` and a larger `short` — recorded, not
silent. Groups are 10 cards / 5 value / 5 outlook with the leave-short default
already in force; a 10 % thinner supply raises `short` and that is the intended,
observable outcome. Nothing backfills.

---

## 1. Analytics scope

- **(c) WAIVED — no analytics needed because:** this is a generation-side
  filter with no new user-visible surface and no new event. Its effect is
  already measurable on existing columns: `deck_impressions.assets_json`
  (give-side asset ids, which is exactly how the defect was quantified above),
  `deck_job_id`, `card_index`, `model_arm`, `group_key`, plus
  `bakeoff_runs.groups_json[...].short` for the deck-size cost. Same waiver C4
  took for the same reason.

## 2. Schema & flag scope

- New/changed tables or columns: **none.**
- New/changed feature flags: **none.** Consistent with D-076's rule for this
  wave — every change gets its own `model_config` knob whose disable value is
  byte-identical to prior behaviour, no group flag.
- New `model_config` keys: **`deck_give_headliner_cap`** (default `3.0`, in
  `trade_service._DEFAULT_CFG`) → `docs/config-reference.md` updated. **Ship-the-knob
  rollback lever:** `PUT /api/admin/config` with `deck_give_headliner_cap = 0`
  restores pre-C4b behaviour with no deploy; `= 4` or `= 5` loosens it if decks
  read too thin.

## 3. Evidence scope

- **Structural guard:** n/a — backend-only, no mobile surface.
- **Unit tests:** `backend/tests/test_engine_quality.py` — 11 new tests:
  - `test_centerpiece_cap_is_blind_to_the_measured_flood` — the root cause:
    six "one player for one pick" cards are six distinct centerpieces and C4 at
    its default removes nothing.
  - `test_give_headliner_cap_bounds_the_flood_c4_cannot` — C4b trims it to 3 and
    keeps each headliner's best cards.
  - `test_give_headliner_cap_is_per_headliner_not_per_deck`
  - `test_give_headliner_cap_leaves_short_and_never_backfills`
  - `test_give_headliner_cap_kill_value_leaves_every_card`
  - `test_give_headliner_cap_is_inert_without_a_seed_map`
  - `test_give_headliner_prefers_the_player_over_the_pick`
  - `test_give_headliner_ignores_the_receive_side`
  - `test_deck_centerpiece_definition_is_untouched_by_c4b`
  - `test_both_generation_paths_apply_the_give_cap`
  - `test_arm_a_disables_the_give_cap`

  Updated: `test_engine_quality_golden.py` `_KILL_ALL` (byte-identity proof now
  covers the new knob), `test_bakeoff_arm_a_golden.py` `_PINNED_KNOBS` +
  per-knob non-vacuity loop. `_flood_deck` and `_ORTHOGONAL_GATES_OPEN` pin
  C4b **off** so the pre-existing C4 cases still isolate C4 — every card in the
  C4 flood fixture gives `hub`, so C4b would otherwise bind first.

- **Code-walk proof:** file:line trace in §3.1 below.
- **Proven-to-fail:** two sabotages, each applied, observed RED, reverted —
  (a) default `3.0 → 0.0`: 3 behaviour tests fail; (b) delete the
  `cap_give_headliners` call from `_dedup_and_sort`: 4 tests fail (the three
  above plus the both-paths guard).
- **Manual TestFlight checklist:** §3.2.
- `testID`s added/renamed: none.

### 3.1 Code-walk proof

1. **Knob** — `backend/trade_service.py:695-705`: `deck_give_headliner_cap: 3.0`
   in `_DEFAULT_CFG`, read live through `_c()` so `PUT /api/admin/config` moves
   it with no deploy.
2. **Definition** — `backend/trade_service.py` `deck_give_headliner(give_ids,
   seed_elo, players)`: give ids only; when a `players` map is supplied, any
   asset for which `is_pick_asset(players.get(pid))` is true is dropped from
   contention *unless every give asset is a pick*; then `max` on
   `(seed_elo.get(p, 1500.0), p)` — the same deterministic id tie-break
   `deck_centerpiece` uses.
3. **Filter** — `cap_give_headliners(cards, seed_elo, players, cap)`: returns
   `cards` unchanged when `cap <= 0` **or** `seed_elo` is empty; otherwise walks
   the list in the order given, counting per headliner, skipping past the cap.
   Order-preserving and subtractive-only: it never reorders, never invents.
4. **v1/v3 engine path** — `TradeService._dedup_and_sort`, immediately after the
   C4 centerpiece block and after `sorted(..., key=composite_score,
   reverse=True)`, so each headliner keeps its **best** cards. Called at
   `trade_service.py:3193` (streaming snapshot), `:3206` (end of the v1 sweep),
   `:4221` / `:4229` (the v2 engine's own sweep) — so the cap binds on the final
   served set and on every progressive snapshot, exactly like C4 and the R4
   exclusion.
5. **`trade_gen.v2` serving path** — `_generate_trades_impl`'s
   `if FLAGS.trade_gen_v2:` branch `return`s **before** `_dedup_and_sort` ever
   runs, so it needed the call explicitly; added after
   `_filter_by_trade_intent`, on the pipeline's own ranked survivor set.
6. **Bake-off arm C** — `backend/bakeoff_runner.py` `gen_v2_cards` calls
   `generate_league_suggestions` directly and bypasses `_generate_trades_impl`
   entirely, so it needed the call a third time; added alongside the two
   post-generation steps already applied there for the identical reason (§ the
   function's own docstring: arms A/B get it, so arm C gets it).
7. **Arm A** — `bakeoff_profiles.MODEL_A_PROFILE["deck_give_headliner_cap"] =
   0.0`. See §6.
8. **Untouched** — `deck_centerpiece` and `server._fatigue_centerpiece` have no
   diff.

### 3.2 Manual TestFlight checklist (operator)

Runtime proof matters here because the visible outcome is "how the deck reads",
which no unit test can judge.

1. Open the app on a league with a full personal board and pull a fresh deck
   (pull-to-refresh on the Trades screen, or Generate).
2. Swipe through the **entire** deck, noting the give side of each card.
3. **Expected:** no single player appears on the give side of more than **3**
   cards. Before this change the operator's own deck had one player on 6.
4. **Expected:** the deck is noticeably shorter than before — median 29 → ~27
   cards, and a badly-concentrated league can land near 20. That is the trade,
   not a bug.
5. **Expected:** the deck is never *empty* and never fewer than 5 cards.
6. **Regression check:** decline a card, regenerate, and confirm the declined
   card's near-siblings are still suppressed (fatigue is keyed on the
   *centerpiece*, which this change does not touch).
7. If decks read too thin: `deck_give_headliner_cap = 4` or `5`. To revert
   entirely: `0`.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route added, renamed, removed, or contract-changed. `PUT /api/admin/config` already accepts arbitrary `model_config` keys; its contract is unchanged. |
| `living-memory/LLD.md` | n/a | No schema, route, or invariant *convention* shifted. One new knob in an existing table of knobs, applied at an existing hook. |
| `docs/architecture.md` | n/a | No module wiring or data-flow change — the new helper lives in `trade_service.py` and is called from the two sites that already call `_filter_by_trade_intent`. |
| `living-memory/HLD.md` | n/a | No new module, client, or major flow. |
| `docs/cross-client-invariants.md` | n/a | Nothing shared across clients — a server-side generation filter; no client reads the knob. |
| `docs/glossary.md` | **updated** | New term **Give-side headliner**; **Headliner cap** amended to say why it does not bind on player-for-pick cards. |
| `docs/config-reference.md` | **updated** | New `deck_give_headliner_cap` row in the model-config table; `MODEL_A_PROFILE` row extended. |
| `docs/plans/three-model-bakeoff/scope-phase2.md` | **updated** | New row in the *Included* table — arm A's decision on the new knob (§6). |
| `DECISIONS.md` entry | **updated** | D-082. |

## 5. Ship gate declaration

- **CI green:** `pytest backend/tests` — **3427 passed, 1 skipped** (baseline on
  `8b7689a`: 3416 passed, 1 skipped; +11 = the new tests). `tsc --noEmit` and
  `mobile/scripts/testid-lint.sh` unaffected — no mobile files touched.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md`.
- **TestFlight verification:** checklist in §3.2, to be run by the operator.
- Express lane declared by the operator? **no** — full gates.

## 6. Bake-off knob-inventory resolution

`test_no_generation_knob_was_added_without_an_arm_a_decision` flags any new key
in `trade_service._DEFAULT_CFG`. Its own message gives the two options:
generation logic post-dating `MODEL_A_REFERENCE_SHA` (`92c31d5`) → pin the kill
value in `MODEL_A_PROFILE` and re-capture the golden; anything else → record the
exclusion.

**Resolved as INCLUDED, not excluded.** `deck_give_headliner_cap` is v1-path
deck-assembly logic added at the same hook as C4, three days after the reference
sha; arm A is "the engine as it behaved before the waves", so it must not have
it. `MODEL_A_PROFILE` gains `"deck_give_headliner_cap": 0.0`.

**No golden re-capture was needed** — and that is a property, not luck: the kill
value returns the input list unchanged, so arm A's deck is byte-identical to the
captured one. `test_bakeoff_arm_a_golden.py` passes unmodified apart from
`_PINNED_KNOBS`. The knob was also added to the per-knob non-vacuity loop in
`test_every_pinned_rule_actually_bites_on_this_fixture`, which is the guard that
would catch it silently ceasing to do anything; it bites on that fixture today.

This is deliberately **not** the `pass_cooldown_days` precedent. That knob was
excluded because it is not generation logic (a shared, upstream, user-owned
exclusion set). This one *is* generation logic, so it takes the same treatment
its sibling `deck_headliner_cap` took.

**Arm consistency across all three arms:** arms A/B reach the cap through
`_dedup_and_sort`; arm C bypasses that method entirely, so `gen_v2_cards` calls
`cap_give_headliners` itself. Without that, group 3 would be the only group
allowed to flood one give headliner and the bake-off would compare arms under
different deck-assembly rules — the exact failure the intent-filter and lane-label
lines in that function already exist to prevent. Pinned by
`test_both_generation_paths_apply_the_give_cap`.
