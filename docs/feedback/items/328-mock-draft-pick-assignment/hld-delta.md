# FB-328 — HLD delta: per-platform mock-draft pick-ownership resolution

> Author-round deliverable for group **G3** (2026-08-16 wave). Delta against
> [`docs/architecture.md`](../../../architecture.md) (the `mock_draft_service.py`
> row, `docs/architecture.md:135`) as of `origin/main` @ `d3fe3ac`.
> Plan: [`plan.md`](plan.md). Contracts: [`lld-delta.md`](lld-delta.md).
> Operator decisions honored (batch plan §G3): MFL ownership from the API-fed
> store; ESPN from the existing manual assignment tool; applies to **both**
> auto (cpu) and manual modes; the fallback is **labeled, never silent**.

## 1. What changes, in one paragraph

The mock-draft create path today resolves real order + traded-pick ownership
for **Sleeper only** (`_mock_real_draft`, `backend/server.py:12084`; guard at
`:12110`), and every other platform silently falls back to "every team drafts
its own slot" — the exact #328 report. This delta extends **create-time
resolution** to ESPN (via the pick-assignment grid the Draft Room already
renders) and MFL (via the normalized `draft_picks` store the link/import paths
already maintain), and makes the remaining fallback **honest**: a new closed
settings key `ownership_source` (`platform` | `user` | `partial` | `none`) is
persisted,
echoed in `settings_echo`, and rendered as one caption line on the mobile mock
screen. The engine (`mock_draft_service.py`) is untouched except for carrying
the label — `owner_of` already serves the ownership overlay in both cpu and
manual modes, so fixing the create-time inputs fixes both modes with zero
mode-specific code.

## 2. Components touched

| Component | Change class |
|---|---|
| `backend/server.py` — `_mock_real_draft`, new `_mock_platform` + `_mock_owned_pick_overlay` helpers, mock create route | Resolution logic (the substance of the fix) |
| `backend/mock_draft_service.py` — constants, `build_settings`, `state_payload` | Carry + echo the label only; no engine-behavior change |
| `mobile/src/api/mockDraft.ts`, `mobile/src/screens/MockDraftScreen.tsx` | Type + one disclosure caption (two mounts, never co-rendered) |
| `mobile/src/screens/DraftRoomScreen.tsx`, `backend/analytics_taxonomy.py` | `mock_started` gains an `ownership_source` property |
| No new modules, routes, tables, columns, or feature flags | — |

## 3. Data flow — per-platform pick-ownership resolution at create

All four paths run **once, at create time**, inside the `POST /api/mock-draft`
route; ownership is snapshotted into `mock_drafts.settings` and never re-read
(existing invariant, `mock_draft_service.py:973-976`). Zero platform egress is
preserved on every new path: ESPN reads only our DB grid, MFL reads only our
normalized store.

```
POST /api/mock-draft
  └─ _mock_real_draft(sess, league_id, season)
       ├─ Sleeper + draft.room ON   → draft_board_service.build_board (UNCHANGED path)
       │    order_confidence == assigned ⇒ order (order_source "assigned")
       │    + traded_slots {(round,slot): owner} ⇒ ownership_source "platform"
       ├─ ESPN + picks.assign ON    → _assignment_grid → dbs.assigned_board (NEW branch)
       │    same row shapes (slot / round-1 original_user_id / is_traded /
       │    owner_user_id, ORDER_ASSIGNED) ⇒ the SAME downstream row-reader,
       │    verbatim ⇒ order = the stored round-1 assignment order
       │    ("assigned") + user-asserted traded_slots ⇒ ownership_source "user"
       └─ anything else             → honest empty (order None, "randomized",
            {}, ownership_source "none")
  └─ create route, MFL only (order still None):
       pre-shuffle the seeded randomized order (same recipe build_settings
       uses), then _mock_owned_pick_overlay(league_id, season, rounds, order)
       → load_draft_picks (normalized store; rows carry original_user_id /
         owner_user_id / is_traded from MFL's futureDraftPicks export)
       → traded_slots anchored to the ORIGINAL owner's shuffled slot
       ⇒ order_source stays "randomized" (KD-6), ownership_source "platform"
  └─ build_settings(..., ownership_source=…)  → settings JSON (+ echo)
```

**Why the MFL overlay survives a randomized order:** "your 2nd belongs to team
X" is a fact about the *original owner*, not about a slot number. Anchoring
each traded row to wherever the shuffle placed its original owner keeps
ownership true under any order; `build_settings` already translates
`(round, slot)` through its own slot table including snake numbering
(`mock_draft_service.py:1074-1082`).

**The honest-fallback rule (operator requirement):** the label degrades to
`"none"` *at the same point the overlay is dropped* — round-1 slot-map gap
(existing drop at `server.py:12146-12149`), short explicit order (engine rule
at `mock_draft_service.py:1049-1056`), identity drop-all, or an empty store.
A league whose data was consulted, **covers every slot of the mock**, and
simply has zero traded picks keeps `"platform"`/`"user"` — "no trades" is a
fact, not a fallback. In between sits **`"partial"`** (review OBJ-2, HD-8):
data applied but not covering every `(round, slot)` of the mock —
contested/orphaned ESPN slots at round ≥ 2 (grid-excluded), mock `rounds`
deeper than the grid/board/store, or identity-dropped rows. The applied rows
still apply; the caption says so honestly.

## 4. Decisions

**HD-1 — Resolution lives in the server create path; the engine stays pure.**
The engine's "zero platform egress after creation" property is structural
(frozen `MockContext`, no I/O — `docs/architecture.md:135`). Alternatives
rejected: (a) teaching `mock_draft_service` to read `draft_picks` — breaks the
no-I/O module contract for no gain; (b) migrating the Sleeper path off the
board onto the store — gratuitous churn on the one path that already works
(plan's surgical rule: Sleeper byte-identical except the label).

**HD-2 — ESPN reads the assignment *board*, not the raw stored JSON.**
`_assignment_settings` pads missing members onto the stored order
(`server.py:11005-11008`) and the grid excludes contested/orphaned slots by
row filter (`database.py:8516-8526`); the board (`assigned_board`,
`draft_board_service.py:1373`) is what the **ESPN Draft Room** renders, so
the mock and the Draft Room can never disagree. (Corrected per review OBJ-3:
`PickAssignmentScreen` renders the pick-assignments **GET**, which
deliberately *includes* contested/orphaned slots — that is the screen where
someone fixes them, `docs/api-reference.md:484` — so the assignment screen
and the mock **can** diverge on exactly those slots. A round-1 divergence
drops the whole resolution to `"none"`; a round-≥2 divergence is disclosed
as `"partial"` per HD-8 — never silent.) Alternative rejected: reading
`leagues.pick_assignment_settings` + `draft_picks` directly — re-implements
padding and exclusion, and the surfaces can drift. Note: **no extraction is
needed** — the grid construction is already the shared helper
`_assignment_grid` (`server.py:11208`), which the board route already calls
(`server.py:11784`); the mock becomes its second caller. (The plan's
"share/extract" step is already satisfied on `d3fe3ac`.)

**HD-3 — MFL: ownership yes, order no.** MFL's `futureDraftPicks` export
states current + original owner (`_sync_mfl_owned_picks`, `server.py:9519`)
but **no slot sequence**, so the order stays a seeded shuffle labeled
`randomized` (KD-6: never invent an order). Alternatives rejected: deriving an
order from standings (an invented order, exactly what KD-6 forbids); fetching
MFL live at create (the store is already maintained by the link/import/refresh
paths — `server.py:12627`, `:15623`, `:22072`, `:22214`, `:22318` — and a live
read would add egress to a path that has none). The stale guard comment at
`server.py:12111-12114` ("MFL … never the original") is removed with the
guard; it has been false since `_sync_mfl_owned_picks` began persisting
`original_user_id`.

**HD-4 — One closed label, open on clients, nullable for old rows.**
`ownership_source` follows the exact conventions `order_source` and `mode`
already set: closed vocabulary server-side (coerced in `build_settings`,
mirroring `mode` at `mock_draft_service.py:1093`), open set + `null`-tolerant
client-side, `null` echoed for rows persisted before this change (same
read-time convention as #305's pre-mode rows). Alternative rejected: backfill
or infer a label for old rows — inventing provenance is the bug class this
item fixes.

**HD-5 — Identity-space guard on the MFL overlay** (the 2026-08-13 lessons.md
membership audit). Overlay rows are validated against `resolved_order` (which
includes the caller; raw `league.members` does not). Unknown
`original_user_id`/`owner_user_id` rows are dropped and counted; drop-all
degrades the label to `"none"`. A dropped row degrades honesty, never crashes
or misassigns. MFL synthetic ids (`mfl:<league>.f<fid>`, `_mfl_member_id`
`server.py:21943`) are the same scheme session members carry, so matches are
the normal case and drops are the co-owner/stale-membership edge.

**HD-6 — Capability probe unchanged.** The `GET` typed-empty's `capability`
payload deliberately omits board-derived fields (`type`/`order_source` pass as
`None` — `_mock_capability` `server.py:12062-12081`, comment at
`server.py:12262-12269`); `ownership_source` needs the board/store, so it is
omitted for the identical zero-egress reason. (Plan cite correction: the
probe comment lives at `:12262-12269`, not `:12040-12050`.)

**HD-7 — Flags consulted, none added.** Sleeper branch keeps `draft.room`;
the ESPN branch is gated on `picks.assign`, matching the board route's ESPN
branch (`server.py:11763`); the MFL overlay is an ungated DB read (`draft.mfl`
gates the *board*, not the store). Route-level gating (`draft.mock`) is
untouched.

**HD-8 — Partial coverage is a labeled state, not a silent one and not a
total degrade** (review OBJ-2 disposition). Two real cases produce a partly
real mock: grid-excluded contested/orphaned ESPN slots at round ≥ 2, and
mock `rounds` deeper than the grid/board/store (the plan's risk table named
the second and the round-1/round-≥2 asymmetry falls out of the existing
order rules). The vocabulary gains `"partial"`: applied rows still apply,
uncovered slots draft at slot order, and the caption discloses it.
Alternatives rejected: (a) a documented-limitation bullet with a
full-coverage label — a smaller #328, silence about a known gap; (b)
degrading the whole mock to `"none"`/fallback — destroys the real data we
hold to satisfy label purity, strictly worse for the user. Cost accepted:
`"partial"` carries no platform-vs-user provenance distinction (one label,
one caption); the client set is open if that ever needs to split.

## 5. Docs this delta obligates (beyond this folder)

- `docs/architecture.md:135` — the mock row's create-path wiring sentence
  ("this is the one place the mock touches a platform") and the api-reference
  claim that MFL "cannot distinguish a slot order from an ownership overlay"
  are now wrong for ESPN/MFL; rewrite per §3.
- `docs/api-reference.md:520-536` — `settings_echo` field list + the
  "Resolution inputs (W2d)" paragraph ("Sleeper only: …" must go).
- `docs/cross-client-invariants.md` — new `ownership_source` vocabulary
  section next to "Mock-draft mode + typed-empty reason" (`:645`).
- `docs/data-dictionary.md:1179` — `mock_drafts.settings` JSON key list.
- Full row-by-row table in [`scope.md`](scope.md) §4.
