# FB-289 — MFL Draft Room renders raw IDs instead of names (G1 plan)

- **Item:** #289 · screen `DraftRoom` · severity **bug** · app 1.11.0 ·
  mattmurf77 · filed 2026-08-10
- **Group:** G1 — MFL identity in the Draft Room (fast-track bug path)
- **Branch:** `feedback-289-294` (base `origin/main` @ `7cea1fa`)
- **Batch plan:** [`batch-plan.md`](./batch-plan.md)
- **Phase:** 1 (plan only — no production code written)

## Reported (verbatim)

> "Mfl names and teams need to be translated from IDs to actual names."

---

## Table of Contents
- [1. Reproduction verdict](#1-reproduction-verdict)
- [2. Problem statement](#2-problem-statement)
- [3. Root cause](#3-root-cause)
- [4. Approach](#4-approach)
- [5. Platforms touched](#5-platforms-touched)
- [6. Risks](#6-risks)
- [7. File-ownership proposal](#7-file-ownership-proposal)
- [8. Spike needs](#8-spike-needs)
- [9. Test plan seed](#9-test-plan-seed)
- [10. Explicitly out of scope](#10-explicitly-out-of-scope)

---

## 1. Reproduction verdict

**YES — #289 still reproduces on current `origin/main` @ `7cea1fa`.** Verified
against `git show HEAD:` content, not just the working tree (the worktree is
clean apart from untracked feedback folders).

Two independent defects, both live:

**(a) Franchise/owner names — the board never carries one for MFL.**

`backend/draft_board_service.py:1049`

```python
fr_to_user = req.mfl_franchise_to_user or {}
username = {}                                   # MFL has no display-name export here
```

That empty dict is the whole story. Ten lines later,
`backend/draft_board_service.py:1072` does
`"owner_username": username.get(owner) if owner else None` — which is
**structurally always `None` on the MFL path**. The client then falls back at
`mobile/src/screens/DraftRoomScreen.tsx:1140`:

```tsx
{slot.owner_username ?? slot.owner_user_id ?? 'Unassigned'}
```

`owner_user_id` for a non-linking MFL franchise is the synthetic member id minted
by `server._mfl_member_id` (`backend/server.py:20085`), i.e.
`mfl:62846.f0001`. **That string is what the tester is looking at.**

The comment on line 1049 is *narrowly* true (MFL's `TYPE=draftResults` export
carries no names — verified against the committed corpus: pick objects have keys
`comments/franchise/pick/player/round/timestamp` only, and the unit has
`draftPick/draftType/round1DraftOrder/static_url/unit`) but it is *wrong as a
conclusion*: the names are already in our own database and are already resolved
this way by the sibling MFL surface (§3).

**(b) Player names — the board never carries one for MFL either.**

`backend/draft_board_service.py:1086-1088`

```python
"player_id": str(pid_map.get(mfl_pid, mfl_pid)),
"name": "",
"position": "",
"team": None,
```

Hard-coded empties. The Sleeper path fills these from pick metadata
(`_picks_from`, `backend/draft_board_service.py:894-902`) and the ESPN path fills
them from `fetchers.players(...)` (`_recorded_picks_projection`,
`backend/draft_board_service.py:1229-1243`) — MFL fills neither. The client
falls back at `mobile/src/screens/DraftRoomScreen.tsx:1152` (and again at
`:1176` in `PickRow`):

```tsx
{pick.name || pick.player_id}
```

so every made pick on an MFL board renders as **a bare numeric player id** —
our Sleeper id when the DP crosswalk matched, the raw MFL id when it did not —
with the position chip stuck on `'—'` and the neutral position colour, because
`pick.position` is `''`.

**Corroborating evidence that the tester really was on a rendered MFL board:**
if `_mfl_board_binding` had returned `None` (no stored `platform_host`) or
`draft.mfl` were off, the screen would show the `platform_unsupported` copy
("Draft rooms aren't available for this platform yet.",
`DraftRoomScreen.tsx:1020`) and no rows at all. `draft.mfl` is **true** in
`config/features.json` on this base commit. Seeing IDs means the binding worked
and the board rendered — consistent with the report.

**Not a duplicate of #210/#258/#282.** Those were MFL *display-string hygiene* —
HTML entities and franchise colour markup inside a name that we did store
(`mfl_service._clean_text`, `backend/mfl_service.py:475-498`; healing pass
`database._backfill_mfl_name_entities`, `backend/database.py:2340+`). #289 is the
opposite failure: a name we hold, cleaned and correct, that never reaches the
payload at all. Nothing in `_clean_text` can fix an empty dict.

---

## 2. Problem statement

On an MFL league's Draft Room, **both** identity fields render as machine ids:

| What the user should see | What renders today | Source of the defect |
|---|---|---|
| Franchise/team name, e.g. `Eire Rebels` | `mfl:62846.f0001` (synthetic member id) | `owner_username` is always `null` on the MFL board payload |
| Drafted player name, e.g. `Cam Skattebo` | `4034` / `17472` (Sleeper id, or raw MFL id when uncrosswalked) | `picks[].name` / `.position` / `.team` are hard-coded empty on the MFL board payload |

So the tester's "names **and** teams" is literal and covers two distinct code
paths, both inside `draft_board_service._render_mfl`. **Player names are
affected, not just franchise names** — this is the scoping answer the
orchestrator asked for, and it roughly doubles the fix from the one-line
hypothesis.

Sleeper boards are unaffected (`_order_from` builds a real `username` map from
`fetchers.users`, `backend/draft_board_service.py:749-750`; `_picks_from` reads
Sleeper pick metadata). ESPN boards are unaffected (`assigned_board` reads
`owner_username` straight off the assignment grid,
`backend/draft_board_service.py:1296`, and hydrates picks via
`_recorded_picks_projection`). **MFL is the only platform with this hole**, and
it has it on both axes.

Severity is real but contained: the board is *correct*, only illegible. No
ownership, ordering, value or trade math is wrong.

---

## 3. Root cause

| # | Defect | File:line |
|---|---|---|
| R1 | `username` map is initialised empty and never populated on the MFL render path | `backend/draft_board_service.py:1049` |
| R2 | `owner_username` therefore always resolves `None` | `backend/draft_board_service.py:1072` |
| R3 | `picks[].name` / `.position` / `.team` hard-coded to `""`/`""`/`None`, with no `fetchers.players` hydration | `backend/draft_board_service.py:1087-1089` |
| R4 | The route's MFL binding loads `league_members` — which holds the franchise names — and **discards everything except `user_id` and `player_ids`** | `backend/server.py:10462-10476` |

R4 is the interesting one. `_mfl_board_binding` already does this:

```python
members = load_league_members(lid)            # server.py:10462
...
for m in members:
    uid = str(m.get("user_id") or "")
    rostered.extend(...)
    if uid.startswith(prefix):
        franchise_to_user[uid[len(prefix):]] = uid
```

The `m["username"]` / `m["display_name"]` columns on those same rows are the
MFL franchise names, written at link/import time from `parse_bundle` —
`backend/server.py:20188-20190` (link) and `20326-20328` (re-sync) — for **every**
franchise, including non-linking ones under their synthetic ids, and already
run through `_clean_text` (so #210/#282's entity+markup cleanup is inherited for
free).

**The exact same lookup already exists, three thousand lines up, for the sibling
MFL surface:** `_sync_mfl_owned_picks`, `backend/server.py:9201-9207`

```python
members_by_uid = {str(m.get("user_id")): m for m in load_league_members(league_id)}

def _name(uid: str, fid: str) -> str:
    m = members_by_uid.get(uid)
    if m:
        return m.get("username") or m.get("display_name") or f"Team {fid}"
    return f"Team {fid}"
```

That is why MFL owned-pick rows in `draft_picks` carry correct
`owner_username`/`original_username` while the Draft Room does not. **The Draft
Room is the one MFL surface that skipped this step.** So this is a genuine
omission with a shipped in-repo precedent to copy — not a design constraint.

For R3, the analogous precedent is `_recorded_picks_projection`
(`backend/draft_board_service.py:1213-1246`): crosswalked ids →
`fetchers.players(ids)` → `full_name`/`position`/`team`. `_render_mfl` already
crosswalks MFL player ids into our id space via `req.mfl_player_ids`
(`backend/server.py:10479`, `_shared_crosswalk().by_mfl_sleeper`); it simply
never takes the second step of looking the resulting ids up.

---

## 4. Approach

### The seam: `_render_mfl`, backend, for both defects

`draft_board_service._render_mfl` is the single function that produces the MFL
board payload for **every** consumer (mobile `DraftRoomScreen`, any future web
or extension surface, and anything that re-renders `order[]`/`picks[]` entries —
`mockDraft.ts` documents that it deliberately reuses these exact entry shapes).
Fixing it there means no client can see the raw ids again and no second client
has to learn a fallback rule. Fixing it in `DraftRoomScreen.tsx` is not even
possible for the player names — the payload does not carry them.

### F1 — franchise/owner names

Populate the `username` map that line 1049 leaves empty, keyed by **user id**
(so it mirrors the Sleeper path's `username.get(owner_user)` exactly), and use
it for `owner_username`. Illustrative shape only:

```python
names = req.mfl_usernames or {}
...
"owner_username": names.get(owner) or None,
```

Two ways to get that map into `_render_mfl`. **Recommend Option A; Option B is
the zero-collision fallback** (see §7 — Option A needs a `backend/server.py`
edit the batch plan currently assigns exclusively to G2).

**Option A (recommended) — route-injected, mirrors every other MFL input.**
Add `mfl_usernames: Mapping[str, str] | None = None` to `BoardRequest`
(`backend/draft_board_service.py:213-218`, beside `mfl_franchise_to_user` /
`mfl_player_ids`), and fill it in `_mfl_board_binding` inside the loop that
already walks `members` (`backend/server.py:10466-10476`) —
`{uid: m["username"] or m["display_name"]}` — plus the linking user's own row.

*Why:* every MFL input to this module is route-bound by design (host, year,
franchise map, player map, rostered ids). The module's own docstring records
that `Fetchers` gained `users` precisely because "the payload's
`owner_username` has no source in the LLD's fetcher list"
(`backend/draft_board_service.py:37-42`) — this closes the MFL half of exactly
that gap, with the same injection discipline. Zero extra DB reads: `members`
is already in hand. ~5 lines in `server.py`, ~3 in `draft_board_service.py`.

**Option B (fallback, avoids `server.py` entirely) — a defaulted fetcher.**
Add `def database_league_members(league_id)` beside `database_players`
(`backend/draft_board_service.py:259-261`), a `members()` method on `Fetchers`
/ `PlatformFetchers` with a default binding (exactly the
`rookie_ids_fn`/`players_fn` pattern at `:278-279`), and call it from
`_render_mfl`.

*Cost:* one extra `load_league_members` query per MFL board render, duplicating
the read the route already performed in `_mfl_board_binding` — small (≤ ~14
rows), but genuinely redundant, and it puts a second name-resolution source in
the tree. *Benefit:* the entire change lands in `backend/draft_board_service.py`
+ tests, so G1 never touches `server.py` and the parallel lanes stay provably
disjoint.

**Fallback string when a member row is missing.** Use `f"Team {fid}"` — the
convention already used by `_sync_mfl_owned_picks` (`server.py:9206`),
`mfl_service.parse_bundle` (`mfl_service.py:556`) and
`database.py:8095`. **Never** fall through to the synthetic id. Note the MFL
render loop has the franchise id (`fid`) in hand at that point, so the fallback
is `Team 0001`, not `Team mfl:62846.f0001`.

### F2 — player names

After the crosswalk, hydrate from our own player table, copying
`_recorded_picks_projection`:

```python
rows = fetchers.players([p["player_id"] for p in picks]) if picks else {}
# then fill name / position / team per pick
```

`fetchers` is already a parameter of `_render_mfl` and is already used further
down for `_undrafted`. One extra bounded DB read per MFL render; `_undrafted`
already makes one of the same kind on the same request.

An MFL id the DP crosswalk did not resolve stays uncrosswalked and its row
resolves to nothing — leave `name: ""` in that case. That is honest, it is what
the ESPN path already does for an unknown id, and the client's existing
`pick.name || pick.player_id` fallback keeps the row visible. Do **not**
fabricate a name.

### Alternatives considered and rejected

| Alternative | Why rejected |
|---|---|
| **Fix in `DraftRoomScreen.tsx`** (e.g. prettify the fallback) | Impossible for player names — the payload has no name to render. For franchise names it would hard-code MFL id-parsing into one client and leave every other consumer broken. Also drags the change from Tier 4/3 to Tier 1 on the sim-gate matrix for zero benefit. |
| **Fetch MFL `TYPE=league` (franchise names) or `TYPE=players` in the board path** | Breaks the binding's explicit one-export-per-refresh budget and the `_REQUEST_SPACING_SECONDS` ≥1 s rule that `_mfl_board_binding`'s docstring calls out (`server.py:10425-10429`), against a platform that asks clients to space requests. And it is redundant: we already store these names locally. |
| **Parse names out of MFL `comments` prose** (`"[Pick traded from Kings of the Empire.]"`) | The corpus really does carry franchise names there, but only on traded picks, in free prose, in MFL's wording. Not a contract. Fragile by construction. |
| **Use `Crosswalk.by_mfl_id` (mfl_id → (DP name, pos)) for player names** (`backend/espn_service.py:583`) | Tempting — it covers players missing from our `players` table and needs no DB read. But it carries no `team`, uses DP's name formatting rather than ours (a second name source on one screen), and requires threading a third map through `BoardRequest`. `fetchers.players` is the shipped precedent. Worth revisiting only if §8's spike shows poor crosswalk coverage on real MFL rookie ids. |
| **Change `_mfl_member_id` to embed the name** | Would corrupt a stable identity key used across `league_members`, `draft_picks`, and every MFL surface. Never. |
| **Read `league_members` directly inside `draft_board_service`** (no fetcher indirection) | Violates the module's structural no-`database`-import discipline (I-7, docstring lines 12-18); the two existing DB reads go through defaulted callables for exactly this reason. Option B respects that; a bare import would not. |

### Success criteria (goal-driven, per `docs/coding-guidelines.md` §4)

1. A test that renders the committed `mfl-complete` corpus with a member-name
   map asserts `order[].owner_username` is the franchise name — **failing
   first** against `7cea1fa`.
2. The same for `picks[].name` / `.position`.
3. No MFL order row's `owner_username` is ever a string containing `mfl:`.
4. `test_m5_06`'s byte-identical flag-off payload and `test_m5_10`'s
   Sleeper-unchanged assertion still pass.
5. Full backend suite green.

---

## 5. Platforms touched

**Backend only.** No mobile, no web, no extension, no schema, no new route, no
new feature flag, no analytics event.

- The payload **shape** is unchanged — `owner_username` and `picks[].name` are
  already declared non-optional-nullable in the contract
  (`docs/api-reference.md:414`) and already typed in
  `mobile/src/api/draft.ts:48` / `:61`. Only the *values* change, from
  `null`/`""` to real strings. `schema` stays `1`; no client needs a rebuild.
- `mobile/src/screens/DraftRoomScreen.tsx` needs **no** edit: `owner_username ??
  owner_user_id` and `pick.name || pick.player_id` both start rendering the good
  value automatically. Leaving the fallbacks in place is correct — they remain
  the honest last resort for a league whose member rows are missing.
- Keeping this backend-only is a deliberate, load-bearing choice: it holds the
  change at sim-gate **Tier 3** ("backend route/schema consumed by mobile") or
  arguably Tier 4, instead of Tier 1's full 11-flow smoke suite
  (`docs/runbook.md` §Pre-ship simulator gate). It also keeps
  `githooks/pre-push` (which gates on `mobile/src` changes) out of the way.
- `backend/mfl_service.py` — **no change needed**, despite being in G1's
  assigned lane. Names arriving from MFL are already parsed and cleaned there
  (`parse_bundle:526`, `_clean_text:475`); the defect is downstream.

---

## 6. Risks

**R-1 — Does any consumer depend on the ID-valued field? No.**
Full sweep of `owner_username` / `owner_user_id` across `backend/`, `mobile/`,
`web/`:
- `owner_user_id` is the identity key and **is not being changed** — `my_picks`
  is sliced on it (`draft_board_service.py:1151`), and
  `MockDraftScreen.tsx:283` / `RecordPicksScreen.tsx:191` compare on it. All
  untouched.
- `owner_username` is display-only everywhere it is read
  (`DraftRoomScreen.tsx:1140`, `RecordPicksScreen.tsx:428/201`,
  `PickAssignmentScreen.tsx:1324`, `TrendsScreen.tsx:400`,
  `web/js/app.js:6134`) and every read already handles both a name and a
  `null`. Going from `null` → a name is strictly additive.
- The synthetic id is *currently* leaking into the UI as a side effect; nothing
  keys off seeing it there.

**R-2 — Stored data needing a healing pass? No.** This is the sharpest contrast
with #210/#258/#282, which needed `_backfill_mfl_name_entities`
(`backend/database.py:2340+`). #289 lives entirely in a **computed** payload:
`_render_mfl` runs per request (only the raw upstream `_Entry` is cached —
`build_board`/`_refresh` cache the fetched export, and `_render` is called after
the cache lookup on every request), so the first request after deploy is
correct. The stored side is already right: `draft_picks.owner_username` for MFL
is written with resolved names by `_sync_mfl_owned_picks`
(`server.py:9229/9232`), and `league_members.username` holds cleaned franchise
names. **No migration, no backfill, no cache invalidation.**

**R-3 — Per-request render means no cross-user leak.** Since names would be
injected per request (Option A) or read per render (Option B), and the render is
not cached, there is no risk of one league's/user's names being served from
another's cache entry. Verified against `_refresh`/`_store`
(`draft_board_service.py:454-522`) — the cache holds `_Entry` (raw upstream
payloads) keyed by `(platform, league_id, draft_id)`, never a rendered payload.

**R-4 — Player-name coverage is crosswalk-dependent.** Rookies are the weakest
segment of the DP crosswalk (newly added ids), and a rookie draft is exactly
where they appear. A pick whose MFL id did not crosswalk keeps rendering its raw
id. Mitigation: honest empty name + existing client fallback; §8's spike
measures the real coverage on the operator's league before we decide whether the
`by_mfl_id` fallback is worth adding. **This means the fix may not be 100% on
the "names" half** — the build agent must not claim otherwise in QA.

**R-5 — Test-fixture drift.** The route-level `mfl_league` fixture
(`backend/tests/test_draft_board.py:931-934`) stubs `load_league_members` with
rows that have **no** `username` key. Under Option A those rows must gain names
or the new route-level assertion is vacuous; under Option B the same. A build
agent that adds an assertion without touching the fixture will get a green test
that proves nothing.

**R-6 — `original_username` stays `null` for MFL** (see §10). Traded MFL rows
will keep rendering `from —` at `DraftRoomScreen.tsx:1143`. If the operator
reads #289 as covering that too, scope grows; this plan says it does not.

**R-7 — File collision with G2 on `backend/server.py`** — see §7. This is the
one thing that needs an orchestrator decision before the build agent starts.

**R-8 — `mock_draft_service.py` has the same class of bug and is G2's.**
`backend/mock_draft_service.py:1013` (`ctx.usernames.get(...)`) fed from
`server.py:11437` (`{m.user_id: m.username}` off the *session* league object,
not `league_members`) plus `MockDraftScreen.tsx:284`
(`slot?.owner_username ?? String(onClock.roster_id)`) means an MFL-league mock
would show the same raw ids. **G1 must not touch either file.** Flagged to the
orchestrator as a G2 observation, not a G1 change.

---

## 7. File-ownership proposal

### Requested for G1 (build agent owns these outright)

| File | What changes |
|---|---|
| `backend/draft_board_service.py` | `_render_mfl` — populate the `username` map (F1) and hydrate `picks[]` name/position/team (F2); `BoardRequest.mfl_usernames` under Option A, or `database_league_members` + `Fetchers.members` under Option B |
| `backend/tests/test_draft_board.py` | Extend the MFL unit + route tests and the `mfl_league` fixture (§9) |
| `docs/feedback/items/289-mfl-draft-room-ids/` | This plan, the PRD, `status.md` |

`backend/tests/test_draft_board.py` is **not** currently in the batch plan's
ownership table. Claiming it for G1 is low-risk: G2's mock tests live in
`backend/tests/test_mock_draft.py` and G3 is mobile-only. Confirming this is a
one-line orchestrator ack.

`backend/mfl_service.py` is assigned to G1 but **will not be touched** — G1
formally releases it.

### ⚠️ COLLISION — `backend/server.py` (raise immediately)

The batch plan states: *"`backend/server.py` is touched only by G2 (the
mock-draft route shims). If G1 finds it needs a `server.py` edit, that is a
collision — it routes through the orchestrator."*

**G1's recommended fix (Option A) needs a `server.py` edit.** Scope, precisely:

- **Function:** `_mfl_board_binding`, `backend/server.py:10411-10493`
- **Lines:** ~`10466-10476` (add a `usernames` dict inside the existing
  `for m in members` loop) and ~`10485-10491` (one new key in the returned
  `request_fields`)
- **Size:** ~5 added lines, no deletions, no signature change

Distance from G2's lane: the `/api/mock-draft` shims start at
`backend/server.py:11380` (`_mock_league_context` at `:11424`) — roughly **900
lines away**, in a different section, with no shared helper. A textual merge
conflict is very unlikely; the batch plan's rule is nonetheless explicit, so
this is escalated rather than assumed.

**Three ways to resolve — orchestrator picks one:**

1. **Grant G1 a scoped exception** on `_mfl_board_binding` (lines 10411-10493),
   with G2 confined to ≥ line 11380. Cleanest engineering; near-zero merge risk.
   *Recommended.*
2. **G1 hands the `server.py` hunk to the orchestrator** as a diff in
   `status.md`, applied at integration (the mechanism the batch plan already
   defines for shared docs).
3. **G1 takes Option B** (§4), which eliminates the `server.py` edit entirely at
   the cost of one redundant `load_league_members` query per MFL board render.
   Acceptable, and the right call if the orchestrator wants provable lane
   isolation over the marginally cleaner design.

### Orchestrator-owned, G1 proposes text only

- `docs/api-reference.md` — the `/api/draft/board` row (line 414) currently
  documents `order[]`/`picks[]` shapes without stating that MFL's are
  name-less. Proposed delta: in the **Platforms** sentence for MFL, add
  *"MFL franchise names and drafted-player names are resolved server-side from
  `league_members` and the DP crosswalk respectively; a franchise with no
  stored member row falls back to `Team <franchise_id>`, and an uncrosswalked
  MFL player id renders with an empty `name` rather than a fabricated one."*
- `living-memory/CHANGELOG.md`, `TEST_LEDGER.md` — at ship.
- No `docs/cross-client-invariants.md` change: the `Team <id>` fallback is a
  single-producer server-side string, not a cross-client enum. No
  `docs/data-dictionary.md`, `docs/config-reference.md` or
  `docs/architecture.md` change (no schema, no flag, no module rewiring).

### Confirmed disjoint from the other lanes

| Group | Their files | Overlap with G1 |
|---|---|---|
| G2 | `backend/mock_draft_service.py`, `mobile/src/screens/MockDraftScreen.tsx`, `/api/mock-draft` shims in `server.py` (≥ L11380) | **`server.py` only** — see above. G1 does not touch `mock_draft_service.py` even though it has the sibling bug (R-8) |
| G3 | `mobile/src/screens/LeagueSummaryScreen.tsx` | None |

G1 touches **no** mobile file.

---

## 8. Spike needs

Two questions cannot be answered from committed fixtures. Both need a read
against the operator's MFL league **"Dependables", id 62846** — read-only, no
writes, no new credentials in chat (`CRON_SECRET` / `DATABASE_URL_PROD` from
`secrets.local.env` per CLAUDE.md §Conventions).

**S-1 (blocking for F1 confidence, ~10 min) — are the franchise names actually
stored for 62846?**
Query prod `league_members` for `league_id = 62846`: confirm every row has a
non-empty `username`/`display_name`, that the synthetic ids match
`mfl:62846.f<NNNN>`, and that the #282 markup strip actually landed on the
stored strings (f0001 should read `Eire Rebels`, not `<b><font color = Green>…`).
If any row is blank, the fallback path (`Team <fid>`) becomes the common case
rather than the edge case and the PRD should say so. Also confirm the league row
carries a `platform_host` (else the binding returns `None` and the tester could
not have seen a board at all — a contradiction worth catching early).

**S-2 (sizing for F2, ~15 min) — what fraction of the drafted MFL player ids
crosswalk?**
Fetch `TYPE=draftResults` for 62846 through `mfl_service.fetch_draft_results`
(zero-auth, verified for public leagues; one export call, respect the ≥1 s
spacing) and intersect the `player` ids against
`_shared_crosswalk().by_mfl_sleeper`, then against `load_players_by_ids`.
Output: `% of made picks that will render a real name`. If that number is low
(say < 90%), promote the `by_mfl_id` fallback (§4, rejected-alternatives table)
from "revisit" to "in scope".

Neither spike gates *starting* the build (F1's code path is the same either
way); both gate the PRD's acceptance-criteria numbers and the QA claim.

---

## 9. Test plan seed

### Backend — pytest (the primary gate; this fix is verifiable without a simulator)

Fixtures available, all committed and hermetic (no network):
`backend/tests/fixtures/draft/mfl-complete/` (10 franchises `0001`–`0010`,
30/30 picks made, league `10005`, host `www48…`), `mfl-partial/` (36/72,
carries `"[Pick traded from …]"` comments → `is_traded` rows), `mfl-made0/`
(upcoming), `mfl-multi-unit/` (2 units). Each has a `manifest.json` with
`made`/`total`/`units`. Note: **none of these carry franchise names** — the
export genuinely has none, which is why the names must come from
`league_members` and why the tests must supply that map.

| ID | Level | Assertion | Anchor |
|---|---|---|---|
| T-289-01 | unit | `mfl-complete` + a franchise-name map ⇒ every `order[]` entry's `owner_username` is the mapped name; **no** value contains `mfl:` | extend `test_m5_mfl_franchise_and_player_maps_are_honoured`, `test_draft_board.py:657` |
| T-289-02 | unit | A franchise with **no** member row ⇒ `owner_username == "Team 0003"`, never the synthetic id, never `None` | same file |
| T-289-03 | unit | `mfl-complete` + `mfl_player_ids={"17472": "ours-x"}` + a `players` row for `ours-x` ⇒ `picks[0]["name"]`/`["position"]`/`["team"]` are populated | same test (already injects both maps at `:665-666`) |
| T-289-04 | unit | An MFL pick id **absent** from the crosswalk ⇒ `name == ""`, `player_id` unchanged — honest, never fabricated | same file |
| T-289-05 | route | `test_m5_07`'s payload has non-`null` `owner_username` on `my_picks` **and** on at least one non-linking franchise — **requires extending the `mfl_league` fixture at `test_draft_board.py:931-934` with `username` values** (R-5) | `test_draft_board.py:991` |
| T-289-06 | regression | `test_m5_06` flag-off byte-identical payload still passes (`draft.mfl` off ⇒ zero MFL reads, unchanged bytes) | `test_draft_board.py:952` |
| T-289-07 | regression | `test_m5_10` — no Sleeper league's response changes (D10); plus the Sleeper golden-key set `EXPECTED_KEYS` is unchanged | `test_draft_board.py` |
| T-289-08 | hermeticity | `test_the_whole_matrix_is_replayed_never_live` still reports zero live egress | `test_draft_board.py:695` |

**Failing-first is mandatory** for T-289-01/03 (the pipeline's standing rule and
the reason #282's writeup records `git stash` verification): run each new
assertion against `7cea1fa` and record the failure text in `status.md`.

Full suite: `python3 -m pytest backend/tests -q` — must stay green (last
recorded baseline in `living-memory/TEST_LEDGER.md`; the count rises by the
number of new test functions).

### Simulator / Maestro

- **Relevant existing flows:** `mobile/.maestro/flows/rookie/d1-draft-room-complete.yaml`
  and `d2-draft-room-order-not-set.yaml`. Both drive the Draft Room through the
  QA harness user `qa_standard` on the **Sleeper** Lakeview corpus
  (`1312076055586050048`). They are the right *no-regression* check and prove
  nothing about MFL.
- **There is no MFL league in the mobile QA harness.** Grepped `backend/test_users.py`
  and `qa/` — zero MFL references; the harness is Sleeper-fixture-driven
  (`FTF_SLEEPER_FIXTURES_DIR`), and MFL has no equivalent env seam (only the
  `_mfl_draft_opener()` monkeypatch seam used by pytest). **A Maestro flow that
  asserts MFL names is not authorable without first building MFL support into
  the harness — which is far larger than this fix.**
- **Proposed Maestro delta: a written waiver**, reason = "no MFL league is
  seedable in the mobile QA harness; the payload change is covered by eight
  backend tests including two failing-first, and by a manual dev-build check
  against the operator's Dependables league." Operator decides; per CLAUDE.md
  agents never self-select express, so this waiver is surfaced, not assumed.
- **Sim tier:** backend-only change to a route mobile consumes ⇒ **Tier 3**
  ("smoke subset that exercises the route") — run `rookie/d1` + `rookie/d2` and
  log them in `TEST_LEDGER.md` + `qa/sim-runs/last-sim-run.json`. A Tier-4
  reading ("backend-only, no sim run") is defensible since no `mobile/src` file
  changes and `githooks/pre-push` would not block; Tier 3 is the conservative
  call and costs two flows. Operator's decision, recorded in the scope block.

### Manual verification (the only thing that truly closes #289)

On a dev build pointed at a backend with the fix, open the Draft Room for MFL
league 62846 and confirm: every order row shows a franchise name (no `mfl:`
prefix anywhere on screen), and every made pick shows a player name plus a
coloured position chip instead of a bare number. Screenshot into
`docs/feedback/items/289-mfl-draft-room-ids/`.

---

## 10. Explicitly out of scope

Named here so the Author's PRD and the adversarial review can hold the line.

1. **`original_username` for MFL stays `null`.** `_render_mfl:1075-1076`
   documents why: MFL's grid states the *current* owner and provenance survives
   only as prose in `comments`. Traded rows keep rendering `from —`
   (`DraftRoomScreen.tsx:1143`). Parsing the prose is rejected in §4. If the
   operator wants "from <team>" on MFL traded picks, that is a separate item.
2. **The identical bug in the mock draft** (`mock_draft_service.py:1013`,
   `MockDraftScreen.tsx:284`) — G2's files, G2's lane (R-8).
3. **Any change to `owner_user_id`** or to `_mfl_member_id`'s scheme.
4. **MFL live polling** — `draft.live_poll` and the mid-draft latency probe are
   untouched.
5. **A `Team <id>`-style prettifier in the mobile fallback.** Keeping
   `DraftRoomScreen.tsx` untouched is a deliberate scope and sim-tier decision
   (§5).
