# Batch plan — 2026-09-02 weekly run (operator items from this week)

> Batch-level plan for the 2026-09-02 `/feedback` run. Lowest selected ID is #413, so
> batch notes live here. Operator selection (chat, 2026-09-02): *"Start working on all
> feedback that's open from me from this week"* — read as every open `mattmurf77` item
> filed Sun 2026-08-30 (local) onward: #413, #414, #415, #416. #408 (Sat 2026-08-29
> local, TeamReview) is adjacent and NOT selected.

## Groups

| Group | Items | Path | One-line scope |
|---|---|---|---|
| G-413 | #413 | Feature (API contract: new 422 reason; taxonomy enum value) | Send in Sleeper has no draft-pick handling — picks go to Sleeper as player ids and the pre-send validator flags every pick as a moved player. Server-side split + encode (MFL precedent), validator fix, mobile error branch. [investigation.md](investigation.md) |
| G-414 | #414 | Bug/polish in the trade engine (planner decides) | A lopsided 1-for-1 (Drake London for CeeDee Lamb straight up) served where user-side filler would balance it. |
| — | #415, #416 | Verify-closed | Shipped by D-170 (server, 2026-08-31T21:29Z) + D-171 (v1.16.14 build 143). Statuses set `fixed`; runtime proof = finder-results-push scope §7 steps 1/5/6. |

Groups are split: G-413 is the Sleeper write adapter + validate route; G-414 is the
generation/fairness engine. No shared files expected (G-413 owns `backend/server.py`
propose/validate regions + `SendInSleeperButton.tsx`; G-414 owns the engine modules).
If G-414 needs `server.py`, its region must be disjoint from `:16155-16277` and
`:27715-27840` — check before parallel build.

## Status corrections applied this run

- #415, #416 → `fixed` (shipped outside this pipeline on 2026-08-31, never flipped).
- `docs/feedback/items/INDEX.md` lagged from #402 onward — rows added this run.

## Phase log

- 2026-09-02: Phase 0 complete — statuses set, folders created, investigation traces
  captured, Phase 1 planners launched (G-413 feature loop; G-414 pending its trace).
