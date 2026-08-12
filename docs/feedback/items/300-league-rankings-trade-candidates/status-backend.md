# #300 backend — build status

> Branch `build-300-backend`, based on `origin/main` @ `62ff8d6`. Scope block:
> [`scope.md`](scope.md). Frozen design:
> [`operator-answers-2026-08-12.md`](operator-answers-2026-08-12.md).

---

## Table of Contents

- [1. What shipped](#1-what-shipped)
- [2. The three recorded decisions](#2-the-three-recorded-decisions)
- [3. Proposed docs text (orchestrator to apply)](#3-proposed-docs-text-orchestrator-to-apply)
- [4. Verification](#4-verification)

---

## 1. What shipped

**One additive field** on `GET /api/league/power-rankings`, at the top level of
the response beside `starters_available`:

```json
"medians": {
  "QB": {"value": 1000.0, "value_label": "≈0.5 firsts"},
  "RB": {"value": 0.0,    "value_label": "≈0 firsts"},
  "WR": {"value": 0.0,    "value_label": "≈0 firsts"},
  "TE": {"value": 0.0,    "value_label": "≈0 firsts"}
}
```

- Always all four core positions, or `{}` when `teams` is empty (no list ⇒ no
  divider; never a fabricated 0.0 across four positions).
- `value` is 1dp, like every other value on this wire.
- `value_label` is the existing `_aggregate_pick_label` string — the same
  generic-Mid-1st denomination already shown as "a Late 2nd" on trade cards,
  rounded to the nearest half-first.
- Served **unflagged**. Implementation: `_position_medians` in
  `backend/server.py`, immediately above `league_power_rankings_route`.

**Two feature flags**, both default OFF, registered in `FLAG_KEYS`
(`backend/feature_flags.py`), `config/features.json`, and the three
release-mirrored test fixtures: `league.pos_candidates`,
`league.player_trade_handoff`.

## 2. The three recorded decisions

1. **Median population = every team in the payload, the caller included.** The
   divider is drawn on the very list `teams` serializes and the frozen design
   keeps the caller in that list as the anchor. Excluding them would put the
   line somewhere other than the list it is drawn across.
2. **Even team counts take the MEAN of the two middle values**; odd counts take
   the middle value. The textbook median — and what a naive client-side
   implementation computes, so the server's `value` and the client's agree. It
   also preserves the property §4.1 of the frozen design depends on: an odd
   league leaves exactly one team *on* the line, an even one leaves none.
3. **`value_label` is ungated.** No restructuring was needed. The
   `aggregate_tier_labels` experiment gates only *whether the route attaches*
   `value_label` to each team; `_aggregate_pick_label` itself is a pure function
   of the value with no experiment dependency. `_position_medians` calls it
   directly. Frozen design §3's "the experiment has to graduate, or #300 has to
   read the same computation directly. Unresolved." is resolved by the second
   branch, and the experiment is no longer a #300 blocker.

**Subset scope — ALL only.** `teams[].positions[P].value` is the whole-roster
positional subtotal. Starters/Bench are derived client-side from `roster` +
`starters`, and the frozen field shape has no room for a per-subset median.
**The client must render the divider only while the subset is All**, and must
never label a Starters or Bench line with this value. Extending to subsets is a
contract change (additive sibling keys), not a client-side fix.

## 3. Proposed docs text (orchestrator to apply)

Deliberately NOT applied on this branch — both #300 build branches would
collide on the same lines.

### 3a. `docs/api-reference.md`, the `GET /api/league/power-rankings` row

**Edit 1 — response shape.** In that row, replace

```
→ `{league_id, basis, scoring_format, updated_at, starters_available, teams:[{rank,
```

with

```
→ `{league_id, basis, scoring_format, updated_at, starters_available, medians:{QB\|RB\|WR\|TE:{value,value_label}}, teams:[{rank,
```

**Edit 2 — description.** Insert the following immediately before the row's
closing `Math: ` sentence:

> **Positional medians (#300, additive, UNFLAGGED):** `medians` = the LEAGUE
> MEDIAN of `teams[].positions[P].value` for each core position, plus that
> median's pick-equivalent label — `{QB\|RB\|WR\|TE: {value, value_label}}`.
> Exists because the mobile League-rankings median divider (flag
> `league.pos_candidates`, docs/feedback/items/300-league-rankings-trade-
> candidates/) can compute the median VALUE client-side but cannot LABEL it;
> labelling is server-side. **Population** is every team in the payload, the
> CALLER INCLUDED — the divider is drawn across that same list and the design
> keeps the caller's team in it as the anchor. **Even team counts take the mean
> of the two middle values** (textbook median, matching a naive client-side
> implementation, so server and client agree on where the line falls); odd
> counts take the middle value, leaving exactly one team ON the line.
> `value` is rounded to 1dp like every other value on this wire.
> `value_label` reuses `_aggregate_pick_label` (the same generic-Mid-1st
> "≈N firsts" denomination as `total_value_label`) and is **deliberately NOT
> gated by the `aggregate_tier_labels` experiment** that gates the per-team
> `value_label` above — a divider labelled for one caller and blank for another
> would be worse than no divider; the helper is a pure function of the value, so
> it is read directly. Basis-aware for free: the medians are computed over the
> SAME `teams` the request priced, so `basis=personal` yields personal-basis
> medians. **ALL SUBSET ONLY** — `positions[P].value` is the whole-roster
> subtotal, and the client's Starters/Bench subsets are derived client-side from
> `roster` + `starters`; there is no per-subset median on the wire, so the
> divider may render only while the subset is All. Empty `teams` ⇒ `medians:{}`
> (no list, no divider — never a fabricated 0.0). Served unflagged: additive
> (changes no existing key), one sort per core position per request.

**Edit 3 — the `Math:` list.** Append `_position_medians` to it:

```
Math: `backend/power_rankings.py`, `backend/server.py` (`_aggregate_pick_label`, `_pick_firsts_equivalent`, `_power_picks_by_owner`, `_position_medians`) |
```

### 3b. `docs/config-reference.md` — two new flag rows

| Flag | Default | Effect |
|---|---|---|
| `league.pos_candidates` | `false` | Mobile League rankings: with exactly ONE core position selected, draw the labelled league-median divider (playoff-cutline pattern) plus the 33% Buyer/Seller band labels, and open the stacked-roster drill-in whose side is chosen by the team's side of the line. OFF = the list renders as it does today. The backend's `medians` field is additive and ships unflagged either way. |
| `league.player_trade_handoff` | `false` | The drill-in's row actions — "Offer" on your own players (pins `give`), "Target" on the other team's (pins `receive`) — routing to the trade finder and REPLACING existing pins. OFF = rows carry no action. Separate key so the divider can graduate without the write-side handoff. |

### 3c. `docs/cross-client-invariants.md` — **no edit proposed**

Reasoned waiver, not an omission: the 33% band size
(`round(team_count * 0.33)`) and the "line, not the label, is the direction
rule" ruling live only in the mobile client — no backend constant encodes
either, and no second client renders this surface. The doc's trigger is "a value
that exists in multiple clients". **It will qualify the moment web or the
extension renders this divider**, at which point the band size has to move
server-side or be recorded here.

### 3d. `living-memory/` — orchestrator, at ship

- `CHANGELOG.md`: new dated H2 covering the field + the two flags.
- `TEST_LEDGER.md`: the pytest number below, plus the Tier-2 sim run.
- `DECISIONS.md`: one candidate entry — **the ALL-subset scope of `medians`**
  (§2 above). It is the decision most likely to be re-litigated, and the one
  whose reversal is a contract change rather than a client fix.
- `LLD.md` / `HLD.md`: no entry — no convention or architecture shift.

## 4. Verification

`python3 -m pytest backend/tests -q` → **2596 passed, 1 skipped in 376.09s**
(base `62ff8d6`: 2588 passed, 1 skipped — +8, exactly the new tests). 8 new tests (`-k median`), each proven to FAIL on at least one
deliberately sabotaged build across 9 sabotages, including the named trap
(**S3**: `medians` present and its `value` correct, but the label computed from
the mean).
