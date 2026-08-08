# ADR-010 — User-asserted pick ownership is league-scoped truth in `draft_picks`

**Status:** Accepted (M-A/M-B landed dark behind `picks.assign`; M-C/M-D not built)
**Date:** 2026-08-08
**Initiative:** draft-extensions W3 — [plan §6 REVISED](../plans/draft-extensions/plan.md), [HLD](../plans/draft-extensions/hld.md), [LLD §W3](../plans/draft-extensions/lld.md), delivered contract in [build-w3-ma-mb.md](../plans/draft-extensions/build-w3-ma-mb.md).

---

## Context

ESPN has no rookie-draft concept (operator ruling, 2026-08-06). An ESPN dynasty league's rookie draft therefore necessarily runs **off-platform** — Discord, a spreadsheet, a third-party tool — and there is **no platform draft object to read, not now and not ever**. That is not a gap we can close with a better adapter or a perishable cookie; it is structural.

Two consequences follow immediately:

1. Manual entry is not a *fallback* for ESPN. It is the **only possible path**.
2. Nothing can ever supersede it. Unlike Sleeper or MFL, ESPN will never contradict a wrong grid, so there is no self-healing.

The operator then ruled that assigned picks must behave **exactly like any other league's picks** — full engine parity, tradeable, visible to leaguemates — and that **no user may ever enter a value**. That combination is what makes this decision recordable rather than obvious: it reverses two documented positions at once.

### What this reverses

| Prior position | Where it was written | Status |
|---|---|---|
| "ESPN never writes rows" | `backend/database.py` `draft_picks.platform` column comment; `docs/data-dictionary.md` | **Reversed.** ESPN rows exist and carry `platform='espn'`. |
| "The store's schema must not be *able* to express ownership" | draft-extensions plan §2 "Out" | **Reversed.** Ownership IS the feature. |
| "Assignment is standalone and does not link to league rosters" | prior §6 | **Reversed by the operator.** |
| D2 — an import-graph proof that no manual module reaches the engine | plan §1 | **Deleted.** A builder honoring it cannot build this. Replaced by D12/D13. |

## Decision

**One row per slot in the existing `draft_picks` table, with a provenance triple, and containment by read default.**

```
draft_picks:  + source       TEXT  -- NULL or 'platform' = platform-written | 'user' = asserted
              + assigned_by  TEXT  -- FTF user_id of the last editor
              + assigned_at  TEXT  -- ISO-8601 UTC; ALSO the optimistic-concurrency token
```

Added through the existing additive-column migration seam. **No backfill**: every pre-W3 row keeps `source IS NULL`.

### 1. The containment is the read default, not a table split

`load_draft_picks(..., source='platform')` **defaults to platform-only**, and `NULL` reads as platform. So all seven existing read sites return byte-identical rows in byte-identical order until one explicitly opts in — one at a time, deliberately, with an AST test enumerating every call site. Safe-by-default, greppable, testable.

This is the single most load-bearing line in the design. A parallel table would have needed its own containment story anyway *plus* a reimplementation of five pieces of shared pricing and labelling machinery.

### 2. A writer only ever deletes rows it could have written

`replace_draft_picks(..., preserve_source=None)` scopes its DELETE to one provenance. Platform callers keep the default and can no longer destroy a league's assertions; the assignment projection passes `'user'` and cannot touch a platform row. This closes the risk lens's central objection mechanically rather than by convention.

### 3. No user-entered values, ever — and the conservation bound that buys

Price is a pure server-side function of `(round, season − current_season, format)` via the **shipped** `pick_pool_value` / `compute_pick_value` — the identical functions Sleeper's sync uses. Every assignment route rejects a body carrying any value field with `400 values_not_accepted`, so there is no path — not even a buggy one — from a request to a price.

Because of that, and because every owner must be an existing `league_members` row inside a fixed `rounds × teams × seasons` grid:

> **Total asserted pick value in a league equals that of an equivalent Sleeper league of the same size. A bad or malicious assignment can REDISTRIBUTE value; it can never CREATE it.**

The only inflation lever is `rounds`, clamped to `draft_status.ROOKIE_MAX_ROUNDS` (8) **inside `seed_pick_grid` itself**, not merely in the route — a caller that forgot the clamp could not widen the bound.

This is the strongest safety property in the design and it is a direct consequence of the operator's no-values ruling.

### 4. Contested and orphaned slots are withheld by ROW FILTERING

If ≥2 distinct users assign the same slot to ≥2 different owners it is **contested**; if an owner is no longer a `league_members` row it is **orphaned**. Both are excluded from every read that can reach a price, and both stay **visible** on the assignment screen — which is the one place someone fixes them.

The exclusion is a row filter, never a nulled `pool_value`. `server._power_picks_by_owner` re-derives a price when `pool_value` is NULL, so the naive implementation would silently re-price the very row the rule exists to withhold. A test asserts the naive version fails.

### 5. Two flags, deliberately

`picks.assign` gates entry, storage and the ESPN Draft Room. `picks.assign_tradeable` (M-C, **shipped dark 2026-08-08** — see [build-w3-mc.md](../plans/draft-extensions/build-w3-mc.md)) gates whether asserted picks enter trade math: all seven read sites, the one engine guard `_owned_picks_available`, `picks_supported` as a data test, and the `source` provenance field. Trade math can therefore be killed **without destroying the rows a league typed in**.

### 6. `original_roster_id` is a stable, opaque, league-local slot label

`league_members` has no `roster_id` column, so this is never resolved against a platform. A member who already holds slots keeps them; a new member takes the next free integer. (The LLD specified `index i → str(i+1)` off the passed member list; that silently re-points every `pick_id`'s "original team" the moment the roster changes, so the implementation preserves the established mapping instead.)

Draft **order** and the linear/snake toggle are stored separately (`leagues.pick_assignment_settings`) because they change slot **numbering only, never ownership** — which is what makes the toggle safe to flip at any time.

## Alternatives considered

**A parallel asserted-pick store (the risk lens's position).** Rejected. `draft_picks`' grain is *already exactly* `pick_id = {league}_{season}_{round}_{original_roster}`; seven read sites share five pieces of pricing and labelling machinery (including the inverse bridge in `_owned_pick_assets`) that a parallel store would have to reimplement or adapter-convert into `draft_picks` shape anyway. **MFL is a working precedent** — `_sync_mfl_owned_picks` already builds rows outside the Sleeper sync and calls `replace_draft_picks`. The objection that carried real weight — `pick_id`'s unique key has no user dimension, so a second writer destroys the first — was written for a **per-user** isolation model the operator has since rejected. Under shared league truth, one row per slot is *correct*, and "no user dimension" is a feature.

**A per-user asserted view.** Rejected by the operator: picks tie to league rosters, and assigned picks are tradeable and leaguemate-visible.

**Letting users type values.** Rejected by the operator, and the plan is much stronger for it — the conservation bound exists only because of that ruling.

**Nulling `pool_value` to unprice a contested slot.** Rejected on evidence; see §4.

## Consequences

**Easier.** Seven read sites, five pricing paths, the inverse-value bridge and the display labels all work unchanged the moment `picks.assign_tradeable` flips — because asserted rows are the same shape as every other row. Rollback is a flag flip and never loses data; every schema change is additive and nullable.

**Harder / riskier.**

1. **A leaguemate can change what FTF recommends to you.** Inherent to shared truth. Bounded by the conservation bound, contested-⇒-unpriced, a one-action correction and the two-flag kill structure — but not engineerable away. **Accepted knowingly by the operator**, including active "ask for their 2027 1st" sweeteners once M-C lands.
2. **There is usually no corrector.** Most ESPN leagues will have exactly one FTF user, so the realistic failure is one person's honest mistake persisting unnoticed — wiki mechanics without a wiki-sized crowd. This is why entry correctness (the pristine seed, the per-season confirm step) matters more than conflict resolution.
3. **No self-healing.** A bad assignment is wrong until a human fixes it.
4. **Spent picks linger** unless retired; current-season assigned picks should hard-retire on a fixed date in addition to the existing rosters-heuristic path.
5. **Provenance is a badge, and users skim badges.** Structural disclosure still reads as "FTF says" to some users.
6. **`pick_id` uniqueness has no provenance dimension**, so one slot cannot hold both a platform row and an asserted one. The seeder skips such a slot (the platform wins) rather than raising. Normally empty — assignment exists precisely for leagues whose platform writes no pick rows.

**Recovery.** Every write emits a `pick_assignment_changed` server-fired event, so a league's grid is reconstructible from `user_events` — see [runbook.md → Pick-assignment recovery](../runbook.md).
