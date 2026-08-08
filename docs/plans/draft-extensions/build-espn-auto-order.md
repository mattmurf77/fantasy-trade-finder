# Build status — ESPN auto-derived draft order

**Date:** 2026-08-08 · **Status:** landed, inside the existing `picks.assign` flag · **Scope:** backend + mobile
**Sources (binding):** [plan.md](plan.md) § "Operator decision — ESPN auto-derived draft order (2026-08-08)" · [espn-auto-draft-order-feasibility.md](espn-auto-draft-order-feasibility.md) (the live spike, real league 11896) · [build-w3-ma-mb.md](build-w3-ma-mb.md) (the assignment contract this extends)

> **This file is the delivered contract.** §5 lists every place the build departs from the feasibility doc's recommendations, and why.

---

## 1. The problem

The shipped setup step (`PickAssignmentScreen`) asks a user to drag 12–14 teams
into last season's finishing order **by hand, before the board exists at all**.
That is the first thing a new ESPN league sees, it is pure recall work, and
ESPN already knows the answer. This seeds the drag list from ESPN's own final
standings so the user corrects traded picks instead of reconstructing a season.

---

## 2. The convention, as implemented

`espn_service.derive_espn_draft_order(teams, playoff_team_count) -> list[int] | None`
returns ESPN `team_id`s in pick order (index 0 holds 1.01), or `None`. It is
pure — no I/O, no DB, no Flask.

**Who made the playoffs** is `playoff_seed <= playoff_team_count`. ESPN gives
*every* team a `playoffSeed` (it is the regular-season standing, 1..N), so
bracket size is the only thing separating the groups — which is why it is a
required argument rather than something inferred. It comes from
`settings.scheduleSettings.playoffTeamCount`, newly surfaced by `parse_league`
as `playoff_team_count`.

**Group 1 — non-playoff teams pick FIRST**, by inverse regular-season
standings. Ascending sort key:

| # | Key | Direction | Why |
|---|---|---|---|
| 1 | win percentage `(w + t/2) / games` | ascending | worst record → 1.01. Ties count as half a win, which is how ESPN computes `record.overall.percentage`; deriving it differently would silently reorder any league that ties |
| 2 | `points_for` | ascending | the operator's stated tiebreak — fewer points-for picks earlier |
| 3 | `playoff_seed` | **descending** | ESPN's own final regular-season standing, its own tiebreakers already applied. Unique 1..N, so this makes the order **total** |
| 4 | `team_id` | ascending | belt and braces — the sort stays deterministic even against a malformed payload |

**Group 2 — playoff teams pick LAST**, by `rank_calculated_final` **descending**,
so the champion (`rankCalculatedFinal == 1`) picks last. `team_id` ascending is
the deterministic fallback, though ESPN's final rank is unique in practice.

**`rankCalculatedFinal` is used for the playoff group ONLY.** That is the
operator decision, and it is the whole point: §6c of the spike verified the
field is exactly the post-playoff finish for playoff teams, while §6d found
that for non-playoff teams it encodes ESPN's consolation ladder and disagreed
with inverse regular-season standings on **5 of 8** teams in league 11896. A
single whole-league `rankCalculatedFinal` sort would move 5 of 14 slots there.

---

## 3. Refusals — `None`, never a fabricated order

A missing input never produces a guess. Any of these returns `None`:

| Condition | The real case it covers |
|---|---|
| fewer than 2 teams | malformed / empty payload |
| `playoff_team_count` missing, or outside `1..len(teams)-1` | `mSettings` absent; a bracket holding everyone leaves no non-playoff group |
| ANY team missing `wins` / `losses` / `ties` / `points_for` / `playoff_seed` | auth-degraded read, partial payload |
| duplicate or non-positive `playoff_seed` | standings unresolvable |
| every team 0-0-0 | **pre-season import** — the grid is complete and well-formed, so only this check catches it |
| ANY **playoff** team's `rank_calculated_final` missing, `< 1`, or duplicated | mid-season read (ESPN leaves it `0` until the playoffs finish) |

`rank_calculated_final` is required of the playoff group **only** — requiring it
league-wide would refuse leagues we can answer correctly.

---

## 4. What landed

| Where | What |
|---|---|
| `backend/espn_service.py` | `EspnTeam` gains `wins` / `losses` / `ties` / `points_for` / `playoff_seed` / `rank_calculated_final`, **all defaulting to `None`** — purely additive, every existing caller sees an unchanged object. `parse_league` populates them and adds `playoff_team_count`. New `derive_espn_draft_order` + the `_int_or_none` coercion helper |
| `backend/server.py` | `_espn_standings_read` (fetch + season fallback) · `_espn_suggested_order` (derive → map ESPN team → FTF member id → validate) · `_SUGGESTED_ORDER_CACHE` · four new keys on `GET /api/league/pick-assignments` |
| `mobile/src/api/pickAssignment.ts` | `PickAssignments` gains the four optional keys; new `SuggestedOrderEntry` type |
| `mobile/src/screens/PickAssignmentScreen.tsx` | `SetupView` prefills the round-1 drag list from `suggested_order` and renders the provenance caption |
| `backend/tests/test_espn_draft_order.py` | 42 tests (derivation matrix + payload) |
| `backend/tests/fixtures/espn_league_11896_standings_2026-08-08.json` | REAL live capture — see §7 |
| — | **No new flag, no new route, no new table, no schema change** |

**`league_url` is unchanged.** The spike attributed all three fields to
`mTeam`, and a live probe during this build confirmed `view=mTeam` alone
returns `record.overall`, `playoffSeed` and `rankCalculatedFinal` for league
11896. `mSettings` (already requested) carries `playoffTeamCount`. **No extra
`view=` token and no extra request** on the import path.

### 4.1 Payload shape

Four keys, appearing **together or not at all**:

```jsonc
"suggested_order":        ["espn:{SWID-10}", "espn:{SWID-03}", …],  // index 0 = 1.01
"suggested_order_source": "espn_standings",   // OPEN set — a future platform may add one
"suggested_order_season": 2025,               // the season the standings came from
"suggested_order_detail": [                   // the caption's "why", same order
  { "user_id": "espn:{SWID-10}", "team_name": "Tyler's unimpressive Team",
    "pick": 1, "wins": 2, "losses": 12, "ties": 0, "points_for": 1536.28,
    "playoff_seed": 14, "final_rank": 14, "made_playoffs": false }
]
```

**D13 governs this payload too** — no value/price field, and a test pins it.

### 4.2 The three properties that make this flag-free

The brief allowed adding a flag if there were a concrete reason. There is not:

1. It changes a **DEFAULT** inside an already-shipped, already-gated flow
   (`picks.assign`) — no new route, no new state, no new vocabulary a client
   must learn.
2. It **writes nothing.** Only the shipped `POST .../order` persists, and only
   when the user saves.
3. It is **absent** whenever it cannot be honest, and absent *is* the shipped
   behaviour — the client orders manually, exactly as before.

A kill switch already exists: turning `picks.assign` off removes the entire
surface, this included.

### 4.3 Season selection, egress and caching

The order derives from the most recent **completed** season. The route tries
the league's linked `espn_season`, then **exactly one** season back — a league
linked pre-season carries a 0-0-0 grid for the current year, and last season's
standings are the ones a rookie draft orders off. A row with **no**
`espn_season` derives nothing and makes no request: guessing a season is how
you would read a stranger's league.

Reads go through the shipped `espn_service.fetch_league` with the same
stored-cookie handling `POST /api/espn/import` uses — same host, same auth, no
new egress pattern. **Every failure is soft**: a 403, a timeout, a parse error
or an unexpected exception leaves the payload byte-identical to today's.

Egress is bounded three ways: derivation only runs while the league has **no
stored order** (after the first save it never runs again), a 15-minute
in-process cache covers repeat screen loads before that save (a test pins four
loads → one ESPN read), and the cache stores misses too.

### 4.4 ESPN team → FTF member id, and the permutation gate

Mapping reuses the importer's own rule: the linking user's real FTF id for
their own team (`leagues.espn_my_team_id` / `leagues.user_id`), and
`_espn_member_id` for everyone else. The result must be an **exact permutation
of current `league_members`** — a team that left, or a re-link that changed the
binding, returns `None` rather than a partially-right order. Half-right reads
as a real answer and isn't one.

---

## 5. Deviations from the feasibility doc's recommendations

| # | The doc recommended (§1.5 / §4) | Shipped | Why |
|---|---|---|---|
| 1 | Persist the proposed order in "a new nullable set of columns or a small side table" | **Nothing is persisted.** A transient field on the existing payload | A proposal the user is about to accept or discard needs no storage. Not storing it is also what keeps `draft_picks`' "ESPN never writes rows" invariant (#158) entirely untouched — there is no new writer to reason about |
| 2 | "a route under `/api/espn/*` … that returns the *proposed* order" | The existing `GET /api/league/pick-assignments` | The only consumer is the screen that already calls that route on mount. A second route would be a second round-trip for one array |
| 3 | Land behind `espn.link` "or a child flag" | No new flag — inside `picks.assign` | §4.2 |
| 4 | Compute in "a neutral module, not `espn_service.py`" so Sleeper/MFL could reuse it | `espn_service.py`, beside `parse_league` | The function is ESPN-named and takes ESPN-shaped teams; `playoffSeed` / `rankCalculatedFinal` have no equivalent elsewhere. A neutral home would be a speculative abstraction with one caller (coding-guidelines §2). Moving it later is a rename |
| 5 | "surface it as a labeled choice (regular-season vs ESPN's final rank) rather than silently picking one" | One rule, labeled in the caption | Superseded by the operator ruling, which picked. Two ordering methods on a first-run setup step is a question most users cannot answer; the list is fully editable either way |
| 6 | Add `view=mStandings` / `mMatchupScore` | `league_url` unchanged | Live-verified during this build that `mTeam` alone carries all three fields for league 11896 |

---

## 6. Mobile behaviour

`SetupView` prefills the round-1 `DraggableFlatList` from `suggested_order`
when it is present, falling back to the stored order and then to the members
list exactly as before. The prefill only fills an **empty** list, so a drag in
progress is never rewritten by a background refetch.

**A client-side coverage check gates the prefill**: the suggestion is used only
if it is the same length as the members list and every id is a known member.
Otherwise the shipped path runs. Without it a partially-resolvable order would
render a derived prefix followed by an alphabetical tail — which looks authored
and isn't.

**Caption** (testID `pick-assignment.espn-derived-note`), under the "Round 1
order" label, as a flare tick + dim body — the informational-highlight
vocabulary the deviation marker already uses, never an action color (ADR-005):

> Filled in from your 2025 ESPN standings — playoff teams by where they
> finished, everyone else in reverse regular-season order. Drag anything
> that's wrong; nothing is saved until you confirm below.

### 6.1 Already-saved orders — the behaviour chosen

**Nothing is offered, and there is no "reset to the ESPN-derived order"
affordance.**

This is enforced **on the server**, not by client politeness: the four keys are
emitted only while the league has no stored order, so after the first save they
never appear again and no ESPN read is made at all. "Never overwrite a saved
order" is therefore structural — a client that tried could not, because it has
nothing to overwrite with. A reset affordance would require the server to keep
offering a suggestion it has no reason to compute, on a screen whose entire
design is "the pristine default is right, record deviations."

---

## 7. Tests — `backend/tests/test_espn_draft_order.py` (42)

**The fixture is real.** `fixtures/espn_league_11896_standings_2026-08-08.json`
is a trimmed **verbatim** capture of the public v3 `mTeam`+`mSettings` response
for league 11896, taken live during this build (`_provenance` key records the
exact URL). Every wins/losses/ties/pointsFor/playoffSeed/rankCalculatedFinal
value is ESPN's. The only synthesized field is `primaryOwner` — real SWIDs
identify real people.

That matters: the derived order reproduces the spike's published §6d table
**exactly, with nothing invented**, including the three-way 4-10 tie
(Chubby → Barry → Conor), which the real points-for values resolve on their
own.

| Criterion | Test |
|---|---|
| The 11896 order, verbatim from §6d | `test_11896_reproduces_the_spikes_published_order_exactly` |
| **THE OPERATOR DECISION, executable** | `test_11896_non_playoff_ordering_disagrees_with_rank_calculated_final` — pins that picks 4–8 differ from a whole-league `rankCalculatedFinal` sort, that picks 1–3 and 9–14 agree, and that the 4-10 consolation-ladder winner still gets pick 1.04 |
| Champion picks last / worst picks first | `test_11896_champion_picks_last_and_worst_record_picks_first` |
| Points-for tiebreak | `test_points_for_breaks_a_record_tie_fewer_points_picks_earlier` |
| Seed tiebreak (the documented third key) | `test_playoff_seed_breaks_a_record_and_points_for_tie` |
| Ties = half a win | `test_a_tie_game_counts_as_half_a_win` |
| Determinism / permutation | `test_the_order_is_a_permutation_and_is_deterministic` |
| Missing / zero / duplicate `rankCalculatedFinal` ⇒ None | `test_missing_…`, `test_zero_…`, `test_duplicate_…` |
| Non-playoff team without a final rank is still derivable | `test_a_non_playoff_team_without_a_final_rank_is_still_derivable` |
| Partial records ⇒ None | `test_a_partial_record_on_any_team_returns_none` (×5 fields) |
| Pre-playoff-season league ⇒ None | `test_a_pre_playoff_season_league_returns_none` |
| Bad / missing `playoff_team_count` ⇒ None | `test_a_missing_or_impossible_playoff_team_count_returns_none` (×7) |
| Duplicate / non-positive seeds ⇒ None | `test_duplicate_playoff_seeds_return_none`, `test_non_positive_…` |
| Brand-new league, all fields None ⇒ None | `test_a_brand_new_league_with_no_standings_at_all_returns_none` |
| Parse is additive (legacy fixture, new fields None) | `test_parse_league_is_additive_for_a_payload_without_standings` |
| Payload present + correct + mapped to member ids | `test_payload_carries_the_suggested_order_for_an_espn_league` |
| Breakdown complete, and carries no price | `test_the_breakdown_explains_every_pick` |
| **Saved order ⇒ absent AND no ESPN read** | `test_a_saved_order_is_never_overwritten_and_costs_no_espn_read` |
| Non-ESPN league never carries it, no request | `test_a_non_espn_league_never_carries_a_suggested_order` |
| Never-linked league makes no request | `test_an_espn_league_that_was_never_linked_makes_no_request` |
| ESPN down ⇒ 200, exact shipped key set | `test_espn_being_down_leaves_the_board_working` |
| Pre-season snapshot falls back one season | `test_a_pre_season_snapshot_falls_back_one_season` |
| Membership mismatch suppresses it | `test_a_membership_mismatch_suppresses_the_suggestion` |
| Shipped keys unchanged | `test_the_existing_payload_is_unchanged_apart_from_the_new_keys` |
| 4 loads = 1 ESPN read | `test_the_derivation_is_cached_so_repeat_loads_do_not_hammer_espn` |

ESPN is never contacted by the suite — `fetch_league` is monkeypatched (the
seam `test_espn_service.py` already uses), and an `espn_no_network` fixture
makes an unexpected call a hard failure rather than a silent network hit.

**Verify-failing-first.** Three mutations were applied and each confirmed
**red** before the guard was accepted:

| Mutation | Went red |
|---|---|
| derivation replaced by a single whole-league `rankCalculatedFinal` sort | the operator-decision test + the 11896 exactness test (5 failures) |
| the all-0-0-0 pre-season guard removed | `test_a_pre_playoff_season_league_returns_none` |
| the playoff-group `rankCalculatedFinal` validity guard removed | all 3 `rankCalculatedFinal` refusal tests |

---

## 8. Gates

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q` | **2037 passed, 1 skipped, exit 0** (baseline 1995/1 — +42, and **no existing test changed**) |
| `cd mobile && npx tsc --noEmit` | clean (node_modules symlinked from the main checkout for the run, then removed) |
| `mobile/tests/*.js` (4 AST/behaviour checks) | all pass |

---

## 9. What this does NOT do

- **It does not know about traded picks.** ESPN exposes no future-pick ledger
  (§6e, #158). A derived order is the *pristine* order; the user still records
  every trade. That is unchanged and is the whole reason the assignment grid
  exists.
- **It does not touch `draft_picks`.** No row is written by this feature at
  all — the "ESPN never writes rows" invariant is untouched.
- **It does not reorder an existing board.** `order` changes slot NUMBERING
  only (build-w3-ma-mb §2.3), and this never even reaches that path unless the
  user saves.
- **It does not read prior seasons beyond one back.** ESPN purges old leagues
  (§3.4) and a two-season-stale order is not a better default than a manual one.
