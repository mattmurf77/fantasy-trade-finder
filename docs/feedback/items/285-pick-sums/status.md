# #285 — Draft picks summed into the aggregate pick-equivalent label

**Status:** in-progress · 2026-08-09 · branch `worktree-agent-a18d2616a61a99ae1`
(worktree build against the live `aggregate_tier_labels` experiment, #279)

## The bug report

Operator, filed against `LeagueRankings` (the live `aggregate_tier_labels`
experiment they're testing, #279): "Draft picks should be summed into the
league/team values. Keep it simple. 1sts equal firsts, 3-4 2nds equal a
1st. No other picks included."

## What actually changed

`#279`'s team-total `total_value_label` ("≈14 firsts") was already derived
from `total_value`, which itself already includes each team's owned picks —
but priced in **dollar space** (`pick_pool_value`, the same year-discounted
generic-ladder formula that prices the picks group and every other pick
surface in the app). Converting that dollar total through
`_pick_gap_equivalent`'s firsts formula does technically fold picks in, but
not the way the operator asked for: a real 2nd-round pick's *assessed*
value doesn't land on exactly `1/3.5` firsts, and a 3rd/4th-round pick's
small-but-nonzero dollar value still nudges the label instead of
contributing nothing.

The fix implements the operator's rule **literally**, as an entirely
separate, much simpler formula, gated to the same experiment cohort as
#279, touching the **label only**:

- Every 1st-round owned pick → `1.0` firsts.
- Every 2nd-round owned pick → `1 / 3.5` firsts (operator: "3-4 2nds equal
  a 1st" — 3.5 is the documented midpoint of that range; no other rounding
  rule was specified, so the midpoint was picked as the simplest honest
  reading).
- 3rd round and later → `0` (excluded entirely, per "no other picks
  included").
- No dollar pricing, no year-discounting — a pure count over `round`.

## Where the picks came from

Reused, not re-fetched: `backend/server.py`'s `_power_picks_by_owner(league_id,
fmt)` is the exact function that already builds the draft-capital section's
per-team `picks.items` (same `load_draft_picks` call the picks group and
`/api/league/picks` use). It already had every owned pick's `round` in
scope (the raw DB row) but discarded it when building the wire-facing
`{label, value}` item — `round` now rides along as an **additive** field on
each item.

That field is otherwise inert: `power_rankings.compute_power_rankings`
builds its serialized `picks.items` from only `label`/`value` (unchanged),
so `round`'s presence in `_power_picks_by_owner`'s return value has zero
effect on the general `/api/league/power-rankings` payload for anyone — it
is only read directly off that dict, inside the new #285 experiment-gated
branch in `league_power_rankings_route`.

New helper `_pick_firsts_equivalent(pick_items)` (next to
`_aggregate_pick_label` in `backend/server.py`) walks a team's
`_power_picks_by_owner` items and applies the three-tier rule above.

## The numeric `total_value` decision

**Left unchanged — this is a label-only fix.** The operator's report says
"summed into the league/team values," which read literally could mean the
numeric `total_value` field itself. Three reasons that's the wrong surface
to touch:

1. **The experiment's whole surface is the label.** #279 was built
   specifically so non-experiment users see zero change — `total_value` is
   read by every caller (sort order, the drill-in's raw-number fallback,
   cross-team comparisons), not just the allowlisted operator. Changing it
   for the treatment cohort only would require conditionally branching the
   NUMBER itself on experiment assignment, which is a materially bigger
   and riskier change than a display-string branch, and starts to blur
   into "the experiment silently changes rankings," not "the experiment
   changes a label."
2. **It would reshuffle rank order.** `compute_power_rankings` sorts
   `teams` by `total_value` desc BEFORE the route's experiment check even
   runs. Swapping in the operator's simplified pick-count math (which
   deliberately throws away 3rd-round-and-later value and re-prices 1st/2nd
   picks off a flat count instead of the real generic-ladder curve) would
   move teams up and down the standings for the operator only — a
   different kind of leak than a label text change, and arguably a worse
   one (the operator would see a different STANDINGS ORDER than every
   leaguemate looking at the same league).
3. **`total_value` already has a well-defined meaning** (`positions_value +
   picks.value`, both dollar-priced, decomposable, documented in
   `docs/api-reference.md` and asserted by
   `test_route_totals_reconcile_with_elo_to_value`). Redefining it out from
   under every existing consumer to satisfy one label's simplified math
   would be the kind of change #279's own precedent (and this app's
   feature-gate rules around API-contract changes) exists to prevent
   without a scope block.

So: `total_value` (and `picks.value`, and every other numeric field) is
byte-identical before and after this fix, for every caller, including the
allowlisted operator. Only `total_value_label` changes shape.

## The label formula

`total_value_label` is now:

```
_aggregate_pick_label(positions_value, pick_firsts_equivalent)
```

— **not** `_aggregate_pick_label(total_value)` as #279 shipped it. The base
switched from `total_value` (positions + DOLLAR-priced picks) to
`positions_value` (players only) specifically so the operator's literal
pick-count doesn't get added on top of the picks' dollar contribution
that's already baked into `total_value` — that would double-count draft
capital. `_aggregate_pick_label` gained an optional `pick_firsts: float =
0.0` parameter (default keeps every pre-#285 call site, including the
per-position labels below, byte-identical) that's added to the value's
converted firsts BEFORE the existing half-first rounding.

## Positional subtotals: explicitly untouched

Per the task brief and confirmed by re-reading `compute_power_rankings`:
`positions.{QB,RB,WR,TE}` are **position-scoped player sums** — a QB
subtotal has no notion of "this team's draft picks," because picks aren't
tied to a position. `value_label` on each position object is unchanged:
still `_aggregate_pick_label(pv["value"])` with no pick contribution. This
mirrors #279's own scope note that per-position groups only ever summarize
players.

## League-level aggregate: none exists

The task brief said "League-level aggregate (if a league total renders)
gets the same treatment." Checked: the only cross-team aggregate on
`LeagueSummaryScreen` is the chart's `avgActive` **average** line ("Avg
9.4k"), computed **client-side** in `mobile/src/screens/
LeagueSummaryScreen.tsx` (`useMemo` over `teams`, not a server field). It
isn't a league TOTAL (a sum), and #279's own status doc already scoped it
out for the same reason ("an average across teams, not a single team's
total or a position's subtotal"). No server route emits a league-level sum
today, so there's nothing to extend — noted here rather than silently
skipped.

## Backend

- `backend/server.py`:
  - `_aggregate_pick_label(value, pick_firsts=0.0)` — new optional param,
    additive to the existing formula, defaults preserve every prior
    call site's output exactly.
  - `_pick_firsts_equivalent(pick_items)` — new helper implementing the
    operator's three-tier rule over each item's `round`.
  - `_power_picks_by_owner` — each returned item gains `round` (int,
    always present, not gated by `picks.assign_tradeable`). Inert for
    every existing consumer (see "Where the picks came from" above).
  - `league_power_rankings_route` — under the existing `aggregate_tier_labels
    == "treatment"` branch, `total_value_label` now uses
    `_aggregate_pick_label(t["positions_value"], _pick_firsts_equivalent(
    picks_by_owner.get(t["user_id"]) or []))` instead of
    `_aggregate_pick_label(t["total_value"])`. Per-position `value_label`
    computation is unchanged.

### Mobile

No code changes — `total_value_label` is still an optional `string` on
`PowerRankedTeam`, consumed as an opaque display string by
`LeagueSummaryScreen.tsx`/`TeamRow`, both of which already fall back to the
numeric `total_value` when the label is absent. Only the doc comment in
`mobile/src/api/league.ts` describing the label's derivation was corrected
to match the new formula (positions_value + literal pick count, not
total_value).

## Tests

Extended `backend/tests/test_power_rankings.py`:

- `test_pick_firsts_equivalent_counts_1sts_and_2nds_ignores_3rds_plus` —
  two 1sts + one 2nd → `2.0 + 1/3.5`; 3rd/4th round picks contribute
  nothing regardless of dollar value.
- `test_pick_firsts_equivalent_empty_and_unrecognized_round` — empty list
  and items with a missing/`None` `round` contribute `0.0`, never raise.
- `test_aggregate_pick_label_pick_firsts_defaults_to_zero_backward_compatible`
  — every pre-#285 call site (omitting `pick_firsts`) is byte-identical.
- `test_aggregate_pick_label_adds_pick_firsts_before_rounding` — the
  addition happens before the existing half-first rounding, not after.
- `test_power_picks_by_owner_carries_round_for_pick_sum_math` — confirms
  `_power_picks_by_owner`'s items carry the sourced `round` for the
  fixture's known rows (u_a: `[1, 2]`, u_b: `[3]`).
- `test_route_total_label_sums_owned_picks_1sts_and_2nds_ignores_3rd` —
  end-to-end: the allowlisted caller's `total_value_label` reconciles with
  `positions_value`'s firsts plus the literal pick count for both teams in
  the fixture, and `total_value` is confirmed unchanged (still
  `positions_value + picks.value`, dollar-priced).
- `test_route_labels_present_for_allowlisted_caller_only` (existing #279
  test) — updated to assert the new formula instead of the old
  `total_value`-based one.

Also updated `backend/tests/test_pick_assignment_tradeable.py::
test_mc_09c_provenance_disappears_entirely_with_the_flag_off` — its exact
key-set assertion on `_power_picks_by_owner`'s items (`{"label", "value"}`)
now includes the new unconditional `round` key
(`{"label", "value", "round"}`); the W3 M-C provenance fields
(`pick_id`/`season`/`source`) it's actually testing are still correctly
gated by `picks.assign_tradeable` and still disappear with the flag off —
`round` isn't one of them, so it stays present either way.

## Gates run

- `python3 -m pytest backend/tests -q` → 2078 passed, 1 skipped (baseline
  2072 passed / 1 skipped + 6 new tests in `test_power_rankings.py`, no
  regressions elsewhere save the one intentional key-set update above).
- Mobile: no client code changed (only a doc comment), so `npx tsc
  --noEmit` was not run — nothing in the type surface changed.

## Docs updated

- `docs/api-reference.md` — `/api/league/power-rankings` entry's #279
  paragraph gains a "Pick-sum label math (#285)" note describing the
  literal count, the `positions_value` base, and why `total_value` is
  unaffected.
- `docs/feedback/items/279-aggregate-tier-labels/status.md` — see below.
- This status doc.
- `docs/feedback/items/INDEX.md` — new row for #285.

Not touched (n/a): `docs/data-dictionary.md` (no schema change),
`docs/config-reference.md` (no new flag or env var — reuses the existing
`aggregate_tier_labels` experiment gate).

## Feature-scope gate note

Express-adjacent, same posture as #279: the task brief specified the exact
formula, the gating mechanism (reuse #279's experiment), and the numeric-
total decision was made explicit as a required judgment call rather than
left open. Full test gates were run; this status doc + the #279 status
doc's rule-change note stand in for a from-scratch `docs/templates/
feature-scope.md` copy, per the same reasoning #279 recorded.
