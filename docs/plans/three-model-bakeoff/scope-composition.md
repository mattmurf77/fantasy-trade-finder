# Feature Scope — three-model bake-off, deck composition

**Date:** 2026-08-18
**Entry point:** operator decision (direct ask), amending
[PLAN.md](PLAN.md) §4 and [scope-phase3.md](scope-phase3.md) §0
**Builder:** backend build agent, branch `feat/bakeoff-composition`
**Operator sign-off on waivers:** §3's Maestro/simulator waiver is backend-only
and routine (D-056 retired both). The open items in §6 need a decision **before
Phase 5**, not before merge.

---

## 0. What this changes

Phase 3 served a bake-off deck as a plain **per-arm** team draft over three
arms. The operator's 2026-08-18 decision replaces that with a **30-card deck
built from three groups of ten**, and takes arm A out of the served rotation.

| Group | Arm | Basis | Lane split |
|---|---|---|---|
| 1 | `current` | `divergence` | 5 value / 5 outlook |
| 2 | `current` | `consensus` | 5 value / 5 outlook |
| 3 | `gen_v2` | (divergence by nature) | 5 value / 5 outlook |

**No new taxonomy.** Both axes already exist as fields on `TradeCard` and both
already reach `deck_impressions.features_json`:

| Operator's term | Existing field | Values |
|---|---|---|
| consensus vs divergence | `TradeCard.basis` → `features_json.basis` | `consensus`, `divergence` |
| value vs outlook | `TradeCard.lane` → `features_json.lane` (+ the `archetype` column) | `value`, `window`, absent |

`window` **is** the outlook lane — `trade_service.classify_lane` labels a card
`window` when the value-weighted mean now-lean of what changes hands leans
toward the user's declared window. The engine's label is kept; nothing is
renamed and nothing is duplicated into a new column.

### The groups interleave, not the arms

Arm `current` holds two of the three groups. A per-**arm** rotation would hand
it two of every three slots and leave arm `gen_v2`'s ten cards behind twenty of
arm B's — reintroducing exactly the deck-position confound team-draft exists to
remove (acceptance falls ~27% across a session from position alone). So the
three **groups** are the draft participants. Measured on identical inputs:

| Deck built by | Arm `gen_v2`'s mean served position (of 30) |
|---|---|
| composing groups then concatenating per arm | **24.5** — its whole group in the tail |
| team-drafting the three groups | **14.5** — the deck's centre of mass |

Everything Phase 3 established about the draft is kept: the rotation is
randomised per deck, seeded `sha256("<league_id>|<ISO-week>")`; a duplicate
trade is credited to the **first picker** and the loser recorded in
`also_proposed_by`; a participant that runs dry **forfeits** its slot and the
forfeit is counted.

### Arm A leaves serving by configuration, not deletion

`bakeoff_include_baseline` = 0 (default) removes arm `baseline` from the
roster: it is not generated, not drafted and not served. Everything Phase 2
built stays in the tree and stays green — `MODEL_A_PROFILE`, `model_a()`,
`test_bakeoff_arm_a_golden.py` (including the knob-inventory guard), and the
R4 bypass. Setting the knob to 1 restores arm A as a first-class arm, and with
it its own divergence and consensus groups, with no deploy.

It is also the cheapest half of the fan-out budget: arm A was measured as the
**slowest** arm (4.19 s of the 7.36 s three-arm fixture — its profile zeroes
every gate, so more candidates survive), so the two-arm roster roughly halves
the job cost [scope-phase3.md](scope-phase3.md) §6.2 told Phase 4 to watch.

### Two plumbing gaps closed, so the comparison is of generators

`_generate_trades_impl`'s `trade_gen.v2` branch does two things to gen-v2's
output that `bakeoff_runner.gen_v2_cards` was skipping, because it calls
`generate_league_suggestions` directly:

1. **the #172 intent filter** (`_filter_by_trade_intent`). Skipping it meant a
   tester with an intent chip set would have given groups 1 and 2 a filtered
   brief and group 3 an unfiltered one.
2. **the lane label** (`classify_lane`), which runs *after* that branch
   returns, so **no gen-v2 card has ever carried a `lane`**. Left alone, group
   3's outlook quota would under-fill 100% of the time for a plumbing reason
   and the result would read as "arm C cannot produce outlook ideas" — a false
   finding of precisely the kind this composition exists to test for.

Both are post-generation **presentment** treatment, not model behaviour. Arms
A/B get them, so arm C gets them, and the lane/basis comparison compares
generators. `lane_shift` is stamped alongside `lane` for the same parity
reason.

---

## 1. Analytics scope

- [x] **(b) Existing events cover it.** No new client events, no new
  `user_events` rows, no new route. The measurement extends the Phase-3
  attribution rather than reinventing it:

  | Question | Field |
  |---|---|
  | which arm produced this card | `deck_impressions.model_arm` (existing) |
  | its rank in that arm's own list | `deck_impressions.arm_rank` (existing) |
  | its basis / its lane | `features_json.basis` / `features_json.lane` (existing) |
  | **which group's quota it filled** | `deck_impressions.group_key` (new) |
  | **its rank within that group** | `deck_impressions.group_rank` (new) |
  | **which quota slot it took** | `deck_impressions.lane_slot` (new) — `value` \| `outlook` \| `fill` |
  | where it sat in the deck | `deck_impressions.card_index` (existing) |
  | **what per-(group, lane) quota went unfilled** | `bakeoff_runs.groups_json[key].short` (new) |
  | what supply each group had to draw on | `bakeoff_runs.groups_json[key].pool` (new) |
  | **what intent lens the deck was generated under** | `deck_impressions.trade_intent` (new) + `bakeoff_runs.arms_json[arm].trade_intent` |
  | what configuration produced it | `bakeoff_runs.config_json` (existing — the new knobs live in `_DEFAULT_CFG`, so they are captured by construction) |

  `trades_generated` is unchanged: still one event per completed job, so
  per-deck rates keep an honest denominator.

## 2. Schema & knob scope

- **New columns** — `deck_impressions.group_key` (VARCHAR),
  `.group_rank` (INTEGER), `.lane_slot` (VARCHAR), `.trade_intent` (VARCHAR);
  `bakeoff_runs.groups_json` (TEXT). All additive/nullable via the established
  `_migrate_db` pattern, no backfill (no group produced pre-composition rows).
  → `docs/data-dictionary.md`.
- **No new flag.** `trade.bakeoff` stays the one switch, still **false**.
- **New `model_config` keys** (`trade_service._DEFAULT_CFG`, read via
  `bakeoff_runner._cfg`): `bakeoff_group_size` 10, `bakeoff_group_value_slots`
  5, `bakeoff_fill_policy` 0, `bakeoff_include_baseline` 0. **Changed default:**
  `bakeoff_deck_limit` 0 → **30**. → `docs/config-reference.md`. Every one is
  also added to `_PINNED_KNOBS` in the arm-A knob-inventory guard.
- **Kill values restore Phase 3 exactly:** `bakeoff_group_size` = 0 +
  `bakeoff_deck_limit` = 0 + `bakeoff_include_baseline` = 1 ⇒ the uncapped
  three-arm draft, asserted by
  `test_bakeoff_composition.py::test_phase3_kill_values_restore_the_uncapped_three_arm_draft`
  and by the whole pre-existing Phase-3 suite, which now runs pinned to those
  values.
- **No route added, renamed or contract-changed.**

## 3. Evidence scope

- [x] **Unit tests** — `backend/tests/test_bakeoff_composition.py` (31 new):
  roster derivation and the arm-A-stays-intact assertion, group quotas, lane
  alternation and its seeding, the absent-lane rule in all three of its cases,
  under-fill recording, the backfill policy and its flagging, the three-group
  interleave asserted as a **distribution over 300 decks** (per-group mean
  position and per-lane mean position), the per-arm-vs-per-group burial
  comparison, agreement across groups, the deck cap, the kill values, and a
  **measured under-fill sweep** across realistic supply.
- [x] **Integration tests** — 10 new in `backend/tests/test_bakeoff_serving.py`
  driving the real `server._run_trade_job`: group columns on every impression
  row, arm A absent end to end, per-group under-fill in the real
  `bakeoff_runs` row, dark-mode group columns NULL (with the accounting still
  written), the effective-vs-requested `trade_intent` capture, arm C receiving
  the same intent lens and the same lane labeller, and the clean-comparison
  query.
- [x] **Captured golden, extended not weakened** —
  `backend/tests/fixtures/bakeoff/flag_off_golden.json` is **unchanged**. The
  flag-off test still asserts byte-identity against it; the four new columns
  join the admitted-additive list and are asserted **NULL on every row**,
  exactly as Phase 3's three were.
- [x] **Code-walk proof — arm A really is gone from serving.**
  `run_bakeoff` iterates `(a for a in GENERATION_ORDER if a in roster)`
  (`backend/bakeoff_runner.py`), `arm_roster()` returns `("current",
  "gen_v2")` at the default knob, and `groups_for()` derives groups from that
  roster. Asserted at both levels:
  `test_default_run_generates_only_the_rostered_arms` counts engine
  invocations (1, not 2) and
  `test_arm_baseline_never_reaches_a_served_deck` drives the real job and
  checks no impression row carries `model_arm = 'baseline'`. Phase 2's own
  suite is untouched and still green.
- [x] **WAIVED — Maestro / simulator / `screens/` captures:** retired entirely
  by D-056, and this is backend-only with no user-visible surface while
  `trade.bakeoff` is off. No mobile `check-*.js` guard and no `testID` changes
  for the same reason.
- [x] **WAIVED — manual TestFlight checklist:** nothing user-visible ships.
  The checklist belongs to Phase 5.
- `testID`s added/renamed: none. Sim gate: **Tier 4** (backend-only) —
  `FTF_SKIP_SIM_GATE=1` is the standing posture under D-056.

## 4. The decisions, and why

### 4.1 Fill policy — **leave short** (default), backfill available and flagged

`window` is only ~19% of live divergence supply (798 value / 193 window /
0 unlabelled over 3,163 recent cards), so a divergence group needs roughly
5 / 0.195 ≈ **26 surviving cards** before it can expect to fill five outlook
slots. Groups 1 and 3 will therefore miss outlook slots routinely, and arm
`gen_v2` has never served, so whether it produces *any* outlook-basis
divergence ideas is unknown.

That is not a defect to be smoothed over — it is one of the more interesting
things this test can reveal, and a silent value-lane backfill would erase it
while leaving the deck looking full. So:

- **`bakeoff_fill_policy` = 0 (default): the group serves short.** The
  shortfall is recorded per (group, lane) in `groups_json[key].short`,
  alongside the supply it had (`.pool`) and what it managed (`.filled`).
- **= 1: backfill** from the same **group**'s own leftovers — the other lane's
  unused tail first, then its unlabelled remainder — in arm-rank order. Every
  substitute is stamped `deck_impressions.lane_slot = 'fill'`, and `short` is
  **still** recorded, so the backfill hides nothing. A fill never crosses the
  group's arm or basis: it is a lane substitution and nothing more.

Measured under-fill (outlook slots left empty of 5, at the live lane ratios,
varying per-deck supply):

| Surviving cards in the group's pool | divergence group | consensus group |
|---|---|---|
| 10 | 3.0 | 3.0 |
| 15 | 2.0 | 1.0 |
| 20 | 1.0 | 0.0 |
| 25 | 0.0 | 0.0 |
| 30+ | 0.0 | 0.0 |

The consensus group clears its outlook quota at ~20 surviving cards; the
divergence groups need ~25. Pinned by
`test_measured_under_fill_across_realistic_divergence_supply`.

### 4.2 Absent `lane` — its own bucket, never a lane, never an empty deck

`classify_lane` returns `None` precisely when the **outlook axis is undefined**
for that deck: the user has no window direction (outlook `None` or `not_sure`,
via `_LANE_SIGN`), or the flag `trade.lanes` is off. It does **not** mean the
card is value-shaped. 132 of 3,163 recent live cards (4.2%, all
consensus-basis) land here.

The rule, in three parts:

1. **Own bucket.** `LANE_NONE` fills **neither** lane quota. Counting it as
   value would inflate the value lane with cards nobody classified and would
   make the value-vs-outlook comparison depend on how many users happened to
   declare a window — a property of the user base, not of the models.
2. **Reachable only as flagged fill.** Under `bakeoff_fill_policy` = 1 an
   unlabelled card may take a residual slot, stamped `lane_slot = 'fill'`. It
   is never served as though it earned a lane slot.
3. **A wholly unlabelled pool turns the split off** rather than emptying the
   deck. If *no* card in a group's pool carries a label, there is no axis to
   quota on, so the group takes its top `size` by arm rank and records
   `lane_split_active: false`. Without this, every `not_sure`-outlook user
   would be served an **empty deck** under the leave-short default — real user
   harm, and a measurement artefact rather than a model property. One labelled
   card is enough to keep the split live.

Rejected alternatives: counting `(none)` as value (see 1); dropping those cards
entirely (throws away 4% of consensus supply and empties the deck for
`not_sure` users).

### 4.3 `trade_intent` — record the gate that APPLIED, not the one requested

The operator decided the user-facing trade settings stay visible during the
bake-off (testers are briefed verbally instead, because re-adding removed UI
later costs more than it saves). Testers can therefore change the #172 intent
chip mid-test, and `trade_intent` was persisted **nowhere** — not a column, not
one of the `features_json` keys.

**The requested and effective values genuinely diverge**, so this follows
Phase 3's `fairness_threshold` rule rather than merely storing the request:

- `trade_service._generate_trades_impl` resolves
  `_intent = trade_intent if FLAGS.trades_intent_modes else None` — with
  `trades.intent_modes` off, a client that sent `consolidate` was served an
  **unfiltered** deck;
- `server.py`'s route already narrows anything outside
  `{consolidate, tier_up, tier_down}` to `None`, so a stale or misspelled
  client value is not an intent;
- `_filter_by_trade_intent` is a **post-generation** filter, so the recorded
  value describes the served set, not a generator setting.

`bakeoff_runner.effective_trade_intent()` applies all three, and the result is
written per card (`deck_impressions.trade_intent`, on **every** row — the
`executemany` first-row-keys lesson) and per arm
(`bakeoff_runs.arms_json[arm].trade_intent`). Arms cannot currently differ,
because arm C now runs the same filter (§0), but it is recorded per arm rather
than assumed to match — the same discipline as the threshold.

### 4.4 Within-group ordering — lanes alternate, on a seeded lead

Inside a group the two lanes **alternate** (`v, o, v, o, …`), each keeping its
own arm-rank order, and which lane takes slot 0 is seeded per deck **and per
group** (`outlook_leads_for`). Blocking the lanes would have given the leading
lane the whole front half of every group; a constant lead would have put the
value lane in slot 0 of every group in every deck. Measured over 300 decks the
two lanes' mean served positions are 14.52 and 14.48 of 30.

Backfilled cards append after the alternation — they are the residue, they are
flagged, and the default policy produces none.

### 4.5 Dark mode composes but does not serve

In Phase-4 dark validation the served deck is still arm B's own list in arm B's
own order, so `group_key` / `group_rank` / `lane_slot` are **NULL** on every
row: those cards filled nobody's quota and a `group_rank` would describe a deck
nobody saw. The composition is still computed and its accounting still written
to `groups_json` — measuring the per-(group, lane) under-fill *before* Phase 5
lights interleaved serving is exactly what dark validation is for.

## 5. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added, renamed, removed or contract-changed — generation path only |
| `living-memory/LLD.md` | updated | the composition convention + the record-the-gate-that-applied rule generalised past `fairness_threshold` |
| `docs/architecture.md` | n/a | no architectural shift: the same flag-gated branch inside the same worker, one module deeper |
| `living-memory/HLD.md` | n/a | no new client, service or flow |
| `docs/cross-client-invariants.md` | n/a | group keys and lane slots are server-side only; no client reads them |
| `docs/glossary.md` | updated | group, group quota, lane slot, under-fill, fill policy, arm roster |
| `docs/data-dictionary.md` | updated | the four `deck_impressions` columns, `bakeoff_runs.groups_json`, and the clean-comparison query |
| `docs/config-reference.md` | updated | all five knobs (four new + the changed `bakeoff_deck_limit` default) |
| `config/features.json` | updated | the `trade.bakeoff` comment now describes the composed deck |
| ADR / `DECISIONS.md` | updated | fill policy, absent-lane rule, arm-A-by-configuration |

## 6. Open items for the operator

1. **Group 2 is a reference slice, not an arm comparison — make sure the read
   reflects that.** The design implies its own analysis shape and the report
   surface must not imply a three-way contest:
   - **Groups 1 vs 3 is the clean head-to-head.** Both divergence, both ten
     cards, both quota'd 5/5, interleaved together in one rotation with
     position balanced across decks. Pair within user, slice by
     `fairness_threshold` and `trade_intent`, and compare `model_arm`
     `current` vs `gen_v2` **restricted to `group_key IN
     ('current_divergence', 'gen_v2')`**.
   - **Group 2 has no arm-C counterpart.** Arm `gen_v2` is divergence-only by
     construction, so nothing generates a consensus arm-C card and none ever
     will. Group 2 is a **consensus reference slice**: it says how consensus
     supply performs against divergence supply *within arm `current`*, and it
     keeps the deck realistic. Reading `current` vs `gen_v2` across all three
     groups silently compares arm `current`'s consensus cards against arm
     `gen_v2`'s divergence cards and attributes the difference to the model.
     The documented query in `docs/data-dictionary.md` §`bakeoff_runs` groups
     by `(model_arm, group_key)` for exactly this reason.
2. **Deck size before Phase 5.** `bakeoff_deck_limit` is now 30 and three
   groups of ten fill it exactly. With `bakeoff_include_baseline` = 1 there are
   **five** groups (50 cards' worth of composition) against the same 30-card
   cap, so two groups' tails would be truncated by the draft; raise the cap or
   lower `bakeoff_group_size` if arm A is ever restored.
3. **Fan-out cost is now roughly half of what §6.2 of scope-phase3 measured**,
   since the slowest arm no longer runs (arm A was 4.19 s of 7.36 s on the
   12-team fixture). Phase 4 should still watch p95 job duration against
   `server._JOB_HARD_TIMEOUT` = 60 s, but the headroom concern is materially
   reduced.
4. **`trade.lanes` is load-bearing now.** It is `true` in `config/features.json`
   and the composition depends on it: with the flag off, no card carries a lane,
   every group's pool is wholly unlabelled and §4.2 rule 3 turns the split off
   for every group — the deck still fills (top-N by arm rank) but the whole
   value/outlook comparison is inert. Not a crash, but it would quietly answer
   a different question. Do not flip `trade.lanes` off while the bake-off runs.

## 7. Ship gate declaration

- **CI green:** `backend-tests` — full suite **3404 passed, 1 skipped,
  0 failed** (Phase 3's baseline on this branch point was 3363 passed,
  1 skipped; +41 tests, zero regressions). `mobile-typecheck` and
  `maestro-testid-lint` untouched — no mobile files changed.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md`.
- **TestFlight verification:** n/a — nothing user-visible ships.
- **Express lane declared by the operator?** No — full gates.
