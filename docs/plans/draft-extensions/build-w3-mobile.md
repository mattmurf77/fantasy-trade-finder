# Build status — W3 M-A: ESPN pick-assignment grid (MOBILE half)

**Date:** 2026-08-08 · **Wave:** draft-extensions W3 M-A · **Status:** mobile half complete, gates green, **blocked on the backend half for anything to render**
**Scope owned:** `mobile/` ONLY. A parallel agent owns every backend file (routes, schema, seeder, flag registration).
**Spec:** [plan.md](plan.md) §6 (REVISED) + the "Operator decisions — ESPN pick assignment (2026-08-06)" block · [lld.md](lld.md) §2.4, §4.3.7, §4.3.8
**Contract source:** `build-w3-ma-mb.md` **did not exist** at build time, so everything here is coded against the LLD's specified routes. Every place the specified contract does not support the designed UI is enumerated in "Contract gaps" below.

---

## Headline

The mobile half of ESPN pick assignment is built: an API module, a screen, a
League-tab entry section, a root-stack registration with its deep link, and the
P-1 `connectLeague` bug fix the LLD marks BLOCKING for this milestone.

Nothing is visible today. `picks.assign` is not yet a key in
`config/features.json` (backend-owned, the parallel agent's 4-touch), and
`useFlag` on an absent key is falsy — so the League tab is byte-identical, no
request is issued, and the route is reachable only by a deep link that renders
its honest unavailable state. That is the intended flag-off posture, arrived at
fail-closed rather than by a client default.

**No value entry exists anywhere in this half, and none may be added (D13).**
There is no price input, and prices are not even displayed on the screen —
ownership is the whole surface. The API module carries no value field on any
request.

---

## What shipped

| File | Change |
|---|---|
| `mobile/src/api/pickAssignment.ts` | **NEW.** `getPickAssignments` · `assignPick` · `seedPickGrid`, the payload types, `staleAssignment(err)` / `pickAssignmentErrorCode(err)` narrowers, and the shared `pickAssignmentSubline` formatter |
| `mobile/src/screens/PickAssignmentScreen.tsx` | **NEW.** Setup step (rounds stepper · linear/snake · drag-to-reorder round-1 order) and the grid (traded-picks summary · season tabs · collapsible rounds · owner sheet · CAS conflict sheet · per-season confirm) |
| `mobile/src/screens/LeagueScreen.tsx` | Dedicated **"Draft picks"** section below Explore (`league.draft-picks-row`), gated on `picks.assign` AND `isEspn`; shared-key query so the push renders warm |
| `mobile/src/navigation/RootNav.tsx` | `PickAssignment` root-stack registration + `AuthStack` param type. `FreeAgents` options block verbatim, **including** the #151 `headerBackVisible:false` + custom `HeaderBack` workaround |
| `mobile/src/utils/deepLinks.ts` | `PickAssignment: 'app/league/pick-assignments'` — exactly one path, root stack only |
| `mobile/src/state/useSession.ts` | **P-1 fix.** `connectLeague` MERGES instead of replacing (see below) |
| `mobile/src/{api,screens,navigation,state}/CLAUDE.md` | Registry rows |

---

## How the 192-slot review burden is handled

Operator decision 3 puts **current + 3 seasons** on the board. A 12-team,
4-round league is ~192 slots. Five mechanisms, in the plan's priority order:

1. **The pristine grid is the default.** The server seeds every team owning its
   own picks. A league with 3 trades leaves 189 slots untouched, so the user
   records **deviations**, not the board. Nothing here is a giant dirty form.
2. **Order is set ONCE, not per slot.** One drag list of the league's teams for
   round 1, a rounds stepper (1–8, default 4) and a **linear/snake** toggle
   cover the numbering of all 192. The toggle changes NUMBERING ONLY, never
   ownership — so it is safe at any time and cannot raise a CAS conflict.
   Numbering is computed client-side from `settings.order` + `order_type`
   rather than stored, because the server's grain cannot express a slot and
   `overall` must never reach a `draft_picks` row (D18).
3. **Edit only the traded ones.** Rounds are collapsible (round 1 open, the
   rest closed). A deviating slot gets a flare tick and floats into the
   **"Traded picks"** summary pinned at the top — which is **cross-season**,
   because a traded 2029 first is precisely the slot nobody would scroll to.
   Contested and orphaned slots join it; both are open questions the engine has
   withheld a price from.
4. **Current season by default, the other three behind season tabs.** A tab
   carries a check once its board is confirmed.
5. **The confirm-the-board step is PER SEASON.** There is deliberately **no
   "review everything" view** — one 192-row scroll is the failure mode this
   design exists to avoid.

Saves are **per slot**. There is no submit button on the grid and therefore no
work to lose.

---

## Concurrency, provenance, flag posture

- **CAS.** Every PUT carries the `assigned_at` this client read. A 409
  `stale_assignment` opens the conflict sheet built from the 409 body's current
  row: "*&lt;Name&gt; changed this pick 4 minutes ago — keep theirs, or use
  yours?*" with the row rendered. **Use mine** re-issues as another
  compare-and-swap against the row just shown, so a third editor in between
  conflicts again rather than losing. A silent overwrite is not reachable from
  this screen.
- **Provenance (D17).** Every `source: 'user'` slot carries a MEMBER-ENTERED tag
  on the row, in the summary and in the conflict sheet, plus the plain
  statement that ESPN never confirms these. The correction path is one action:
  tap the row. `focusPickId` is accepted as a route param so M-C's priced
  surfaces can deep-link straight to the slot in dispute — the screen switches
  season, expands the round and highlights the row.
- **Flag.** `picks.assign` gates the League-tab section only. The route is
  registered unconditionally (the `DraftRoom`/`MockDraft` rule) so an in-flight
  push survives a flag revalidation. Flag off ⇒ no section, **no query**, no
  entry point; League tab byte-identical.

---

## P-1 — `connectLeague` merge fix (BLOCKING, unflagged)

`getLeagues()` hits `/api/sleeper/leagues/<user_id>`, whose local-league append
filters to **non-numeric** ids, while a platform-imported league carries its
numeric platform-native id. That response therefore can never contain an
ESPN/MFL/Fleaflicker row, and the wholesale `setLeagues(lgs)` replace dropped
every one of them whenever a user connected any Sleeper league mid-session.
This is already why the ESPN re-sync button disappears; the new ESPN-gated
"Draft picks" section would have inherited it.

Fixed by carrying forward prior rows whose `platform` is not `'sleeper'` and
whose id is absent from the fresh list; a fresh row for the same `league_id`
still wins. **[RV-5] caveat recorded in the registry:** `platform` is only
trustworthy while `draft.room` is on (it is), because the server stamps it
inside that flag's block and `api/sleeper.ts` coerces the absent case to
`'sleeper'`.

---

## Contract gaps — where the LLD's routes do not support the designed UI

`build-w3-ma-mb.md` was absent, so these are measured against lld §2.4. All are
worked around in the client rather than hidden; each names what would remove it.

| # | Gap | What the client does | Fix |
|---|---|---|---|
| **G1** | **An unseeded board has no team names.** The setup step needs a drag list of the league's teams with names, but `settings.order` is ids only and `seasons[].slots` is empty before seeding, so the GET cannot answer "who is in this league". | Reads `GET /api/league/members` for that one purpose (shipped route, already used by the League tab). | Return `members: [{user_id, username}]` on the assignment GET, or document the members route as the sanctioned source. |
| **G2** | **`GET` documents a `season=` query param but the payload is always current + 3.** Two readings — a filter that the "always four seasons" sentence contradicts, or a no-op. | Does not send it. | Delete the param from the doc, or specify it. |
| **G3** | **`assigned_by` is a bare user_id.** The 409 copy the plan mandates names a person ("Dana changed this pick…"), but nothing on the row resolves that id to a display name. | Resolves it against the grid's own original-team pairs; falls back to "A leaguemate" when the editor is not a current member — which is exactly the orphan case, so the fallback is load-bearing, not cosmetic. | Add `assigned_by_username` to the slot object. |
| **G4** | **No review/confirmation field exists.** The operator requires a per-season confirm-the-board step; the schema has three additive columns and none of them is "reviewed". | Persists marks client-side under `ftf_pick_board_confirmed_v1` (per league, per season). It is a reading aid and never an input to pricing — a confirmed season and an unconfirmed one are the same rows to the engine. | Leave as-is unless the operator wants confirmation to be league-visible, which would need a real field and a second writer on `draft_picks`. |
| **G5** | **`POST …/order` is both the seeder and the settings setter**, and its OK response carries `seeded`/`reseeded_over`/`progress` but not the new settings echo. | Invalidates the assignments query after a successful save rather than patching the cache — one extra round trip on a rare action. | Echo `settings` in the response. |
| **G6** | **`reseed: true` has no client surface.** The route supports it and reports `reseeded_over`, but a gesture that silently overwrites entered rows has no safe home on this screen. | Never sends `reseed: true`. | If a "start over" is wanted it needs its own destructive-confirm spec; it is not in the plan. |
| **G7** | **No analytics.** `pick_assignment_changed` is server-fired (correctly — a client-forgeable audit row is a forgeable audit trail), and `backend/analytics_taxonomy.py` is default-deny with no client-side pick-assignment events. | Fires **no** `track()` calls. A call here would be dropped server-side while reading like working instrumentation. | Register client events first (entry-section tap, setup completion, per-season confirm) if adoption is to be measured — and §6.8's adoption abort ("<50% of started grids reach 100% within 72h") **cannot be measured without them**. |
| **G8** | **`MockDraft` (W2) has no deep-link path** in `V2_SCREENS`, though lld §4.2 specifies `app/league/mock-draft`. Noted, not fixed — W2's file, not this wave's. | — | W2 follow-up. |

**Flag registration is NOT done and is not mine to do.** `picks.assign` is absent
from `backend/feature_flags.py`, `config/features.json`,
`backend/tests/fixtures/flags/release.json` and `docs/config-reference.md`. All
four are backend-owned files under the 4-touch convention (lld §6.1). The mobile
half is correct either way — an absent key reads falsy — but **nothing renders
until the parallel agent lands the flag and the three routes.**

`mobile/src/state/useFeatureFlags.ts` → `LAUNCHED_FLAG_DEFAULTS` is deliberately
**untouched**: that list is only for flags that ship ON, and this one ships dark.

---

## Gates

| Gate | Result |
|---|---|
| `cd mobile && tsc --noEmit` | **clean** (exit 0; both new files confirmed in `--listFiles`) |
| `python3 -m pytest backend/tests -q` | **1887 passed, 1 skipped** — baseline exactly, no backend file touched |
| Backend files changed | **zero** |

*(The worktree has no `mobile/node_modules`; the typecheck ran against the main
checkout's install via a symlink, removed afterwards.)*

---

## Not built here (by scope)

- The three routes, the schema columns, `seed_pick_grid`, `assign_draft_pick`,
  `contested_pick_ids`, the `replace_draft_picks` provenance scoping and the
  index — parallel agent, M-A backend.
- **M-B** (the ESPN `GET /api/draft/board` branch, `picks_not_assigned` notice,
  the `NoticeCode` union extension and the `DraftRoomScreen` branch). Its mobile
  touch is one union member and one if-else branch, but it depends on the server
  emitting the code, and `DraftRoomScreen.tsx` is a single-writer resource across
  W1/W2/W3 — so it is left to whoever lands M-B's server half.
- **M-C** provenance labels on the five priced surfaces. This screen already
  accepts the `focusPickId` correction link those labels will point at.
- **M-D** live offline recording (separate flag, separate wave).
- Maestro flows. Every interactive element carries a `pick-assignment.*` testID
  in the shipped grammar (stable domain ids, never list indices), so the flows
  are writable the moment the backend answers.
