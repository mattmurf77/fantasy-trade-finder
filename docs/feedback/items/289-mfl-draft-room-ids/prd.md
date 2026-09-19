# PRD — FB-289: MFL Draft Room renders raw IDs instead of names

- **Item:** #289 · screen `DraftRoom` · severity **bug** · app 1.11.0 ·
  mattmurf77 · filed 2026-08-10
- **Group:** G1 — MFL identity in the Draft Room (fast-track bug path)
- **Branch:** `feedback-289-294` (base `origin/main` @ `7cea1fa`)
- **Inputs:** [`plan.md`](./plan.md) (Planner) · [`batch-plan.md`](./batch-plan.md)
- **Scope block:** [`scope.md`](./scope.md)
- **Reconciliation:** [`reconciliation-log.md`](./reconciliation-log.md)
- **Phase:** 1 (PRD only — no production code written)

## Reported (verbatim)

> "Mfl names and teams need to be translated from IDs to actual names."

---

## Table of Contents
- [1. Summary](#1-summary)
- [2. Root cause (file:line)](#2-root-cause-fileline)
- [3. Requirements](#3-requirements)
- [4. Payload contract after the fix](#4-payload-contract-after-the-fix)
- [5. The DP-crosswalk coverage question](#5-the-dp-crosswalk-coverage-question)
- [6. Implementation seam (non-negotiable boundaries)](#6-implementation-seam-non-negotiable-boundaries)
- [7. Out of scope](#7-out-of-scope)
- [8. Test plan](#8-test-plan)
- [9. Live-league QA acceptance procedure (Dependables, 62846)](#9-live-league-qa-acceptance-procedure-dependables-62846)
- [10. Cross-group finding (G2, do not act)](#10-cross-group-finding-g2-do-not-act)
- [11. Citation corrections to the plan](#11-citation-corrections-to-the-plan)

---

## 1. Summary

On an MFL league's Draft Room, **both** identity axes render as machine ids.
This is two independent defects in one function, and the reporter's "names
**and** teams" is literal.

| Axis | Should read | Reads today | Cause |
|---|---|---|---|
| Franchise / owner row | `Eire Rebels` | `mfl:62846.f0001` | `order[].owner_username` is structurally always `null` on the MFL path |
| Drafted player row | `WR Cam Skattebo · ARI` | `— 17472` | `picks[].name` / `.position` / `.team` are hard-coded empty on the MFL path |

Reproduction is confirmed on `7cea1fa` (verification re-run independently for
this PRD — every citation in §2 was read from the base commit, not inherited
from the plan).

**The fix is backend-only and lives entirely in
`draft_board_service._render_mfl` plus the route binding that feeds it.** The
payload *shape* does not change; only the *values* do, from `null` / `""` to
real strings. `schema` stays `1`. No client rebuild is required for the fix to
take effect — but a build is required to *see* it, so the QA path in §9 runs
against a build pointed at the fixed backend.

Not a duplicate of #210 / #258 / #282. Those were display-string hygiene on
names we *do* store (`mfl_service._clean_text`, `backend/mfl_service.py:475`).
#289 is the opposite failure: names we hold, already cleaned, that never reach
the payload. Nothing in `_clean_text` can fix an empty dict.

---

## 2. Root cause (file:line)

All four verified against `7cea1fa` on this worktree.

| # | Defect | File:line | Evidence |
|---|---|---|---|
| **RC-1** | The `username` map is initialised empty and never populated on the MFL render path | `backend/draft_board_service.py:1049` | `username = {}  # MFL has no display-name export here` |
| **RC-2** | `owner_username` therefore resolves `None` for **every** MFL order row | `backend/draft_board_service.py:1072` | `"owner_username": username.get(owner) if owner else None` — `username` is provably empty at this point |
| **RC-3** | `picks[].name` / `.position` / `.team` hard-coded, with no `fetchers.players` hydration | `backend/draft_board_service.py:1087-1089` | `"name": ""`, `"position": ""`, `"team": None` |
| **RC-4** | The route binding loads `league_members` — which **holds** the franchise names — and discards every column but `user_id` / `player_ids` | `backend/server.py:10462-10476` | `members = load_league_members(lid)`; the loop reads only `m["user_id"]` and `m["player_ids"]` |

**Why RC-1's comment is wrong as a conclusion.** MFL's `TYPE=draftResults`
export genuinely carries no names — the committed corpus's pick objects have
exactly `{comments, franchise, player, pick, round, timestamp}` (verified
against `backend/tests/fixtures/draft/mfl-complete/draftResults.json`). But the
names are already in **our** database, written at link time and at every
re-sync, for **every** franchise including non-linking ones under their
synthetic ids, already `_clean_text`-scrubbed:

- link: `backend/server.py:20188-20191` — `{"user_id": mid, "username": fr["name"], "display_name": fr["name"], …}`
- re-sync: `backend/server.py:20326-20329` (and a third writer at `:20428-20431`)

**The in-repo precedent the Draft Room skipped.** The sibling MFL surface
`_sync_mfl_owned_picks` already does exactly this lookup, with the fallback this
PRD adopts:

`backend/server.py:9201-9207`
```python
members_by_uid = {str(m.get("user_id")): m for m in load_league_members(league_id)}

def _name(uid: str, fid: str) -> str:
    m = members_by_uid.get(uid)
    if m:
        return m.get("username") or m.get("display_name") or f"Team {fid}"
    return f"Team {fid}"
```

That is why MFL rows in `draft_picks` carry correct owner names while the Draft
Room does not. This is an omission with shipped precedent, not a design
constraint.

**Client fallbacks that expose it** (unchanged by this fix, deliberately):
`mobile/src/screens/DraftRoomScreen.tsx:1140`
(`slot.owner_username ?? slot.owner_user_id ?? 'Unassigned'`), `:1152` and
`:1176` (`pick.name || pick.player_id`, position chip `pick.position || '—'`).

**Corroboration that the reporter was on a rendered board:** `draft.mfl` is
`true` in `config/features.json:151` on the base commit. With the flag off, or
with no stored `platform_host`, the screen shows `platform_unsupported` and no
rows at all. Seeing ids means the binding worked.

---

## 3. Requirements

Every requirement has a mechanically verifiable pass criterion. "Assertion"
criteria are pytest; "observation" criteria are §9's live run.

### Franchise / owner half

**R-1 — `order[].owner_username` carries the MFL franchise name.**
For an MFL board, each `order[]` entry whose `owner_user_id` resolves to a
`league_members` row emits that row's `username`, falling back to
`display_name`.
*Pass:* unit test renders the `mfl-complete` corpus with a franchise-name map
and asserts every `order[]` entry's `owner_username` equals the mapped name.
Route test asserts the same through `GET /api/draft/board`.

**R-2 — A franchise with no usable stored name falls back to `Team <franchise_id>`, never to a synthetic id.**
Fallback ladder, in order: member `username` → member `display_name` →
`f"Team {fid}"` where `fid` is the MFL franchise id **as it appears in the
grid** (zero-padded, e.g. `0003`). Matches `_sync_mfl_owned_picks`
(`backend/server.py:9206`), `mfl_service.py:556` and `database.py:8095`.
*Pass:* assertion — for every `order[]` and `my_picks[]` entry,
`"mfl:" not in (entry["owner_username"] or "")`. A franchise absent from the
member map renders exactly `"Team 0003"`.

**R-3 — A slot with no franchise at all stays `null`.**
When the grid carries no `franchise` for a pick (`fid == ""`), `owner_username`
stays `None` so the client renders `Unassigned`. A fabricated `Team ` (the
empty-fid concatenation) is a defect.

> **Two distinct cases — do not conflate them.** R-2 covers *"the grid names a
> franchise, but we hold no member row for it"* → `owner_user_id is None`,
> `owner_username == "Team 0003"`. R-3 covers *"the grid names no franchise at
> all"* → both `None`. The discriminator is `fid`, not `owner`. R-2's case must
> **not** cause the build agent to invent an `owner_user_id` to accompany the
> name — it stays `None`, which is what protects the `my_picks` slice at
> `draft_board_service.py:1151`. The client renders `Team 0003` correctly
> today via `slot.owner_username ?? slot.owner_user_id ?? 'Unassigned'`
> (`DraftRoomScreen.tsx:1140`).

*Pass:* assertion — for an entry built from a franchise-less pick,
`owner_user_id is None and owner_username is None`, **and** the payload's
`order_confidence == "unknown"`.

> **Enum correction (Planner objection 2a, verified).** An MFL board never
> emits `order_confidence: "unset"`. `_render_mfl` emits
> `ORDER_ASSIGNED if assigned else ORDER_UNKNOWN`
> (`draft_board_service.py:1133`); `ORDER_UNSET` is produced only by the
> **Sleeper** path `_order_from` (`:783`). An earlier draft of this PRD said
> `"unset"` — a build agent writing the test from that would have asserted the
> wrong string.

**R-4 — `my_picks[]` inherits the same names.**
`my_picks` is sliced from `order` (`draft_board_service.py:1151`), so this is a
consequence, not a separate code path — but it is asserted, because
`test_m5_07` reads `my_picks` and it is the row the operator looks at first.
*Pass:* assertion — every `my_picks[]` entry has a non-null `owner_username`
containing no `mfl:`.

### Player half

**R-5 — `picks[].name` / `.position` / `.team` are hydrated from our own player table.**
Primary source is `fetchers.players(...)` — the same source
`_recorded_picks_projection` uses (`draft_board_service.py:1226-1243`):
`name = full_name or name`, `position = str(position).upper()`,
`team = team or None`.
*Pass:* assertion — with `mfl_player_ids={"17472": "ours-x"}` and a `players`
row for `ours-x`, `picks[0]["name"]`, `["position"]` and `["team"]` are the
row's values.

**R-6 — Exactly ONE batched `fetchers.players` call for pick hydration.**
Batch the lookup after the pick loop; never per pick.
*Pass:* **one** assertion, not a choice — the hydration call receives an id
list whose set is exactly
`{req.mfl_player_ids[mfl_pid] for picks whose mfl_pid crosswalked}`. That single
assertion proves R-6 (one batched call) and R-7 (no raw MFL id was ever
queried) simultaneously, and is strictly stronger than counting calls.

> Do **not** assert `players.call_count == 1`. A non-suppressed MFL render makes
> **two** `fetchers.players` calls — the new hydration plus the pre-existing
> `_undrafted` call at `draft_board_service.py:934` — so a naive count assertion
> fails for the wrong reason. Record the id list of each call and assert on the
> hydration one.

**R-7 — Tier 1 is gated per pick, and the hydration result is keyed by the crosswalked id — never by `pick["player_id"]`.**

*The hazard, measured.* MFL player ids and Sleeper player ids are both bare
numeric strings drawn from **different epochs that overlap densely in exactly
the band a rookie draft touches**: MFL `13xxx` is 2017–18 veterans, Sleeper
`13xxx` is 2025–26 rookies. In the committed crosswalk snapshot alone
(`backend/tests/fixtures/dp_playerids_snapshot_2026-07-11.csv`, 3563 MFL ids),
**255 MFL ids are also a *different* player's Sleeper id** — independently
re-measured for this revision:

| Raw MFL id | Is actually | But as a Sleeper id it is |
|---|---|---|
| `13674` | Dallas Goedert | **Chris Hilton Jr.** |
| `13189` | Evan Engram | **Luke Floriea** |
| `13595` | Mason Rudolph | **Cash Jones** |

*Why constraining the query list is necessary but NOT sufficient.*
`load_players_by_ids` returns `{player_id: row}` (`backend/database.py:7318-7333`),
so the obvious consumption `rows.get(pick["player_id"])` cross-contaminates
**inside a fully legal query**:

- Pick A: `mfl_pid = "17472"` → crosswalks to our id `"13287"`. Legally queried.
  (Both ids are real and adjacent in the corpus: snapshot row 11 is
  `Jeremiyah Love,…,sleeper_id=13287,…,mfl_id=17472`.)
- Pick B: `mfl_pid = "13287"` → **not** in the crosswalk, so
  `player_id = pid_map.get(mfl_pid, mfl_pid)` leaves it `"13287"`
  (`draft_board_service.py:1086`).
- `rows` legitimately contains key `"13287"` — fetched for pick A.
- `rows.get(pick_B["player_id"])` → **pick B renders pick A's player.**

*The requirement.* A pick may take tier 1 **only if its own `mfl_pid` is a key
in `req.mfl_player_ids`**, and its row must be looked up by **that pick's
crosswalked id** (`req.mfl_player_ids[mfl_pid]`), never by `pick["player_id"]`
— the two differ precisely when the crosswalk missed. An uncrosswalked pick
skips tier 1 **entirely**; it is not merely "unmatched".

*Pass:* T-289-06's discriminating assertion (§8) — it **fails** on
`rows.get(pick["player_id"])` and passes on the per-pick-gated implementation.
Plus R-6's id-list assertion.

> This is the single most consequential paragraph in the PRD. The failure mode
> it prevents is a **confidently wrong player name** on a pick — strictly worse
> than the bug #289 reports, and silent.

**R-8 — A crosswalk miss falls back to the DP name/position, never to nothing.**
When the MFL player id is absent from `by_mfl_sleeper` (or the crosswalked id
has no `players` row), resolve from the DP crosswalk's
`by_mfl_id` map (`backend/espn_service.py:583` — `mfl_id → (DP name, position)`).
`team` is `None` in this tier; DP's crosswalk carries no team.
*Pass:* assertion — with `mfl_player_ids={}` and a DP-name map containing
`"17472": ("Cam Skattebo", "RB")`, `picks[0]["name"] == "Cam Skattebo"` and
`["position"] == "RB"`, `["team"] is None`.

**R-9 — Terminal fallback is `Player <mfl_player_id>`; a bare numeric id must never render.**
When neither tier resolves **and the id is a real MFL player id** (i.e. R-15's
sentinel does not apply), emit `name = f"Player {mfl_pid}"` (the raw MFL id, the
only identifier we hold), `position = ""`, `team = None`. This mirrors the
`Team <fid>` convention exactly: an honest placeholder that names its own
uncertainty and stays diagnosable, rather than a fabricated player name or a
bare number the user reads as garbage.
*Pass:* assertion — with both maps empty, `picks[0]["name"] == "Player 17472"`
and `picks[0]["player_id"] == "17472"` (unchanged).
Global assertion across every corpus: **every** `picks[]` entry's `name`
contains at least one ASCII letter (`re.search(r"[A-Za-z]", name)`). That is the
property actually wanted — it subsumes "never empty", "never a bare id", and
"never the `0000` sentinel's digits" in one check, and cannot be satisfied by a
numeric string the way a `^Player \d+$` regex could. Live: §9's count reports
zero letter-less rows.

**R-15 — MFL's all-zeros player id is a slot sentinel, not a player, and is the ONE documented exception to R-9.**
`mfl-multi-unit` carries a pick with `"player": "0000"` (round 05, pick 11 —
verified; it is the only such pick across all four corpora, and the corpus is
`"provenance": "recorded-live"`, so this is production-real, not a fixture
artifact). `_render_mfl` gates pick emission on `if mfl_pid:`
(`draft_board_service.py:1080`) and `"0000"` is **truthy**, so the row is
already emitted as a made pick today.

*Sentinel definition (exact, so the build agent does not improvise):* after
`.strip()`, the MFL player id is non-empty **and** consists solely of the
character `0` — `mfl_pid and set(mfl_pid) == {"0"}`. This matches `0`, `0000`,
`00000` and can never collide with a real MFL player id. MFL's convention for a
genuinely *unmade* pick is `player: ""` (`mfl_service.fetch_draft_results`
docstring, `backend/mfl_service.py:375`); an all-zeros id is a **distinct**
sentinel for a slot that passed without a selection.

*Required treatment:* `name = "No selection"`, `position = ""`, `team = None`.
`player_id` is unchanged (`"0000"`), and `picked_by_user_id` / `pick_no` /
`slot` / `round` are unchanged.

*Pick inclusion does NOT change.* `_mfl_counts` counts this pick as **made**
(`str(p.get("player") or "").strip()` is truthy — `draft_board_service.py:656`),
and `test_m5_mfl_grid_states_through_the_injected_opener` asserts
`len(payload["picks"]) == man["made"]` (= 192 for `mfl-multi-unit`,
`test_draft_board.py:640`). Dropping the row from `picks[]` would break that
test and would require touching `_mfl_counts`, which moves `made`/`state` — out
of scope per §6.2.

*Pass:* assertion — rendering `mfl-multi-unit` with both maps empty,
**exactly one** `picks[]` entry has `name == "No selection"`, its `player_id`
is `"0000"`, its `position` is `""`, and `len(picks) == 192` is unchanged. It
satisfies R-9's letter-containing global assertion. It is counted on its own
line in §9 and excluded from the tier-3 denominator.

> *Why not the Planner's `name = ""`?* See §11's disagreement note — `""` sends
> the client straight back to `pick.name || pick.player_id`, rendering the bare
> string `0000`. That is the exact failure class this PRD exists to eliminate,
> on a row we know about in advance. *Why not `Player 0000`?* It asserts a
> player exists. `"No selection"` claims only what we can defend: the slot
> produced no pick. It is a single-producer server-side display string, same
> class as `Team <fid>` — no cross-client-invariants entry needed.

### Invariants (no-regression)

**R-10 — `owner_user_id` is untouched.**
It is the identity key: `my_picks` slices on it
(`draft_board_service.py:1151`), and `MockDraftScreen.tsx:283` /
`RecordPicksScreen.tsx:191` compare on it. The synthetic
`mfl:<league>.f<fid>` scheme (`server._mfl_member_id:20085`) does not change.
*Pass:* assertion — `owner_user_id` values for the corpus are byte-identical
before and after.

**R-11 — `original_user_id` / `original_username` stay `null` for MFL.**
MFL's grid states the *current* owner; provenance survives only as prose in
`comments`. Parsing prose is rejected (§7).
*Pass:* assertion — every MFL `order[]` entry has both `None`.

**R-12 — `schema` stays `1`; the payload key set is unchanged; no other platform's output moves.**
*Pass:* `set(payload) == EXPECTED_KEYS` still holds; `test_m5_06` (flag-off
byte-identical payload) and `test_m5_10` (no Sleeper league's response changes)
still pass unmodified.

**R-13 — No new upstream egress and no new DB read on the franchise half.**
Exactly one MFL export call per refresh (`TYPE=draftResults`) — unchanged.
`members` is already loaded by the binding, so R-1/R-2 add **zero** queries.
R-5 adds exactly one bounded `load_players_by_ids`, the same kind `_undrafted`
already performs on the same request (`draft_board_service.py:934`). When the
crosswalk is empty, R-7's guard makes the id list empty and **no** query is
issued at all.
*Pass:* assertion — `len(mfl_league) == 1 and "TYPE=draftResults" in mfl_league[0]`
(the existing `test_m5_07` assertion) still holds.

**R-14 — Mobile is not touched.**
No file under `mobile/` changes. The existing fallbacks
(`owner_username ?? owner_user_id`, `pick.name || pick.player_id`) stay in
place as the honest last resort and simply stop firing.
*Pass:* `git diff --name-only origin/main...HEAD` lists no path under `mobile/`.

---

## 4. Payload contract after the fix

Authoritative. A build agent must not have to infer any of this.

### `order[]` (and therefore `my_picks[]`)

| Field | Type | Value after the fix |
|---|---|---|
| `owner_user_id` | `str \| null` | **unchanged** — our user id (the linking user's real id for their own franchise, else `mfl:<league_id>.f<fid>`), `null` when the grid carries no franchise |
| `owner_username` | `str \| null` | `members[owner_user_id].username` → `.display_name` → `"Team <fid>"`. `null` **only** when `fid` is empty. Never contains `"mfl:"`. |
| `original_user_id` | `null` | unchanged — MFL states current ownership only |
| `original_username` | `null` | unchanged (see R-11 / §7) |
| `slot`, `round`, `pick_no`, `is_traded` | — | unchanged |

Resolution, expressed once and exactly:

```
owner_username := ( mfl_usernames.get(owner_user_id) if owner_user_id else None )
                  or ( f"Team {fid}" if fid else None )
```

`mfl_usernames` holds only non-empty strings, so an empty stored name falls
through to `Team <fid>` rather than emitting `""`.

### `picks[]`

| Field | Type | Value after the fix |
|---|---|---|
| `player_id` | `str` | **unchanged** — `mfl_player_ids.get(mfl_pid, mfl_pid)`; still the raw MFL id when the crosswalk misses |
| `name` | `str` | four-row resolution below; **always contains at least one letter** — never `""`, never a bare number |
| `position` | `str` | uppercased position from tier 1 or tier 2; `""` in tier 3 and tier S |
| `team` | `str \| null` | NFL team abbreviation from tier 1; `null` in tiers 2, 3 and S |
| `round`, `pick_no`, `slot`, `picked_by_user_id`, `picked_at` | — | unchanged |

**Resolution, evaluated in this order, first hit wins, total precedence:**

| Tier | Condition | `name` | `position` | `team` |
|---|---|---|---|---|
| **S** | `mfl_pid` is the all-zeros sentinel — `set(mfl_pid) == {"0"}` (R-15) | `"No selection"` | `""` | `None` |
| 1 | `mfl_pid in mfl_player_ids` **and** `players[mfl_player_ids[mfl_pid]]` exists | `full_name` or `name` | `str(position).upper()` | `team or None` |
| 2 | tier 1 missed **and** `mfl_pid in mfl_player_names` | DP name | DP position, uppercased | `None` |
| 3 | none of the above | `f"Player {mfl_pid}"` | `""` | `None` |

**Tier S is evaluated first**, before the crosswalk is consulted at all — the
sentinel is not a player and must never enter the id list R-6 asserts on.

**Keying is load-bearing (R-7).** Tier 1's row is fetched and read by
`mfl_player_ids[mfl_pid]` — the pick's **own crosswalked id**. Tiers 2, 3 and S
key on the **raw MFL** id. For an uncrosswalked pick, tier 1 is skipped
*entirely*, not merely unmatched: its raw id is never queried and the returned
`{player_id: row}` map is never indexed by `pick["player_id"]`. Those two ids
diverge precisely when the crosswalk missed, and 255 measured collisions in the
committed snapshot make that divergence a wrong-player renderer, not a miss.

Pseudocode, normative:

```python
crosswalked = mfl_player_ids.get(mfl_pid)          # None ⇒ tier 1 ineligible
if mfl_pid and set(mfl_pid) == {"0"}:              # tier S
    name, position, team = "No selection", "", None
elif crosswalked and (row := player_rows.get(crosswalked)):        # tier 1
    name = row.get("full_name") or row.get("name") or ""
    position = str(row.get("position") or "").upper()
    team = row.get("team") or None
elif (dp := mfl_player_names.get(mfl_pid)):                        # tier 2
    name, position, team = dp[0], str(dp[1] or "").upper(), None
else:                                                              # tier 3
    name, position, team = f"Player {mfl_pid}", "", None
```

`player_rows` is the single batched `fetchers.players(...)` result, whose id
list is exactly `{mfl_player_ids[p] for non-sentinel picks that crosswalked}`.
A tier-1 row that exists but yields an empty `full_name`/`name` falls through to
tier 2 then tier 3 rather than emitting `""`.

### New `BoardRequest` fields (route-injected)

Added beside the existing `mfl_franchise_to_user` / `mfl_player_ids`
(`backend/draft_board_service.py:213-218`), same injection discipline the module
has always used (docstring I-7, lines 12-18: the module imports `database` for
nothing but the two lazy player/rookie-id reads):

```python
#: MFL only — our user id → franchise display name (from league_members).
mfl_usernames: Mapping[str, str] | None = None
#: MFL only — MFL player id → (DP name, DP position); the crosswalk's own
#: name map, used only when the id/players lookup cannot resolve a row.
mfl_player_names: Mapping[str, tuple[str, str]] | None = None
```

### Route binding delta (`backend/server.py`, G1's owned region)

Inside `_mfl_board_binding` (`:10411-10493`), which G1 owns per the batch
plan's region split:

- In the existing `for m in members:` loop (`:10468-10472`), also collect
  `usernames[uid] = (m.get("username") or m.get("display_name") or "").strip()`,
  keeping only non-empty values. **Zero extra queries** — `members` is already
  in hand.
- In the existing crosswalk `try` (`:10478-10482`), bind the object once and
  read both maps off it, so a crosswalk failure degrades both together:
  `player_ids = xw.by_mfl_sleeper`, `player_names = xw.by_mfl_id`; the `except`
  sets both to `{}` and keeps today's `log.warning`, never a 5xx.
- Add `"mfl_usernames"` and `"mfl_player_names"` to `request_fields`
  (`:10485-10491`).

Roughly 8 added lines, no deletions, no signature change. G2's `/api/mock-draft`
shims begin at `:11380` — ~900 lines away, no shared helper.

---

## 5. The DP-crosswalk coverage question

The Planner raised this as blocking spike **S-2**: player-name hydration depends
on DP crosswalk hits for MFL player ids, and rookies are the crosswalk's weakest
segment — which is exactly the population a rookie draft board shows.

**Decision: the spike is NOT required before build.** The §4 contract makes
coverage a *quality* variable, not a *correctness* one: every MFL player id
falls into exactly one of tiers S/1/2/3, and all four emit a name containing a
letter, so no measurement can change the code that must be written. The
measurement is still required, but it moves into the live QA run against real
data (§9), where it is a count over the actual Dependables board rather than an
estimate.

> An earlier draft of this section claimed "there is no input for which the
> payload emits a bare id or an empty name" while the contract had only three
> tiers. The Planner found a counterexample the contract never enumerated —
> MFL's `"player": "0000"` sentinel, live in `mfl-multi-unit` — which would have
> rendered `Player 0000`. Tier S (R-15) closes it. The claim above is now scoped
> to the enumerated tiers and is exhaustive by construction, since tier 3 is the
> unconditional `else`.

**Why tier 2 (`by_mfl_id`) exists, against the Planner's recommendation.** The
plan proposed leaving `name: ""` on a crosswalk miss and letting the client's
`pick.name || pick.player_id` fallback show the raw id — explicitly accepting
that "the fix may not be 100% on the names half". That leaves the reported
defect live on the most likely rows. Tier 2 removes most of that gap for
essentially nothing:

- `Crosswalk.by_mfl_id` is **already on the object the binding already fetches**
  (`_shared_crosswalk()`, `server.py:10479`). No new query, no new network call,
  no new module dependency.
- Its coverage is **a superset in practice, with zero counterexamples measured**.
  Reading `_parse_crosswalk_rows` (`backend/espn_service.py:590-632`):
  `by_mfl_id` is inserted at `:612` from any DP row carrying a name, a position
  and an `mfl_id`; the `sleeper_id` guard (`if sid in ("", "NA"): continue`)
  sits **after** it at `:613-614`, and `by_mfl_sleeper` is only filled at
  `:619`. Measured on the committed snapshot and independently re-measured for
  this revision: **`by_mfl_id` = 3563 ids vs `by_mfl_sleeper` = 2828, with 735
  ids reachable only through tier 2 and 0 counterexamples.** The relationship is
  *not* structurally guaranteed — `by_mfl_id` additionally requires
  `raw_name and pos` (`:610`), so a DP row with an `mfl_id` and a `sleeper_id`
  but a blank name would land in `by_mfl_sleeper` only. That case is immaterial:
  tier 1 wins on any row that has a `sleeper_id`. A brand-new rookie present in
  DP but not yet mapped to a Sleeper id is precisely the row tier 1 misses and
  tier 2 catches.
- The Planner's objection — "a second name source on one screen" — dissolves
  under total precedence: tier 2 is consulted **only** when tier 1 produced
  nothing, so the two can never disagree about a rendered row.

**Cost accepted:** tier 2 rows carry no `team`, so the row reads
`RB Cam Skattebo` without the ` · ARI` suffix. The client already handles that
(`pick.team ? \` · ${pick.team}\` : ''`, `DraftRoomScreen.tsx:1153`).

**No numeric pass bar on tier-3 rate — report, then the operator decides.**
An earlier draft set a `< 10%` bar. That was an invented number, and the
Planner disproved it with data: replaying all four corpora's 111 distinct MFL
player ids against the committed snapshot gives **tier 1 = 51, tier 2 = 6,
tier 3 = 54 (49%)** — five times the bar. That figure does not predict
production (the committed CSV is a *trimmed* test snapshot, and its tier-3 ids
are a contiguous `17550`+ block, i.e. a 2026 rookie cohort absent from a
July-2026 trim), but it proves the bar was a guess, and a QA gate that fails on
first contact with real data teaches the operator to ignore gates.

§9 therefore **records** the tier-3 count and rate and escalates it to the
operator with the number; it does **not** auto-fail on it. The three absolute
FAIL conditions (a letter-less name, a bare id, `mfl:` in an owner) stay hard —
those are correctly absolute. First remedy for a high tier-3 rate remains the
player-cache refresh in `docs/runbook.md:482` § Player-cache refresh, then a
re-count.

---

## 6. Implementation seam (non-negotiable boundaries)

1. **One function, one binding.** All render logic lands in
   `draft_board_service._render_mfl`. All sourcing lands in
   `server._mfl_board_binding`. Nothing else in either file changes.
2. **No refactor of the MFL service or of `_render_mfl`'s structure.** Per
   `docs/coding-guidelines.md` §3 (surgical changes), the pick loop keeps its
   shape; the hydration is a batch pass added after it. `backend/mfl_service.py`
   is assigned to G1 and G1 **formally releases it** — names arriving from MFL
   are already parsed and cleaned there (`parse_bundle:526`, `_clean_text:475`);
   the defect is downstream.
3. **No `database` import inside `draft_board_service`.** The module's
   structural discipline (I-7, docstring lines 12-18) holds: names arrive by
   injection, never by a direct read.
4. **`members_fn` / defaulted-fetcher approach is REJECTED** (orchestrator
   ruling, `batch-plan.md` § `backend/server.py` — REGION ownership). It costs a
   redundant `load_league_members` per render and adds a seam whose only purpose
   is dodging a merge — the speculative abstraction
   `docs/coding-guidelines.md` §2/§3 prohibits.
5. **Region ownership of `backend/server.py`:** G1 edits only
   `_mfl_board_binding` (~L10411-10493). Any other line in that file is raised
   to the orchestrator, not taken.
6. **Failing-first is mandatory** for the two headline assertions (T-289-01 and
   T-289-03). Run each against `7cea1fa` and record the failure text in
   `status.md` before the fix lands.

---

## 7. Out of scope

Named so the adversarial review can hold the line.

1. **`original_username` for MFL stays `null`.** MFL's grid states current
   ownership; provenance is free prose in `comments` (e.g.
   `"[Pick traded from Kings of the Empire.]"`), not a contract. Traded MFL rows
   keep rendering `from —` at `DraftRoomScreen.tsx:1143`. *Noted as a visible
   artifact:* if the operator reads #289 as covering that, it is a separate
   item, and the honest fix is client-side (suppress the ` from —` suffix when
   `original_username` is null) — which would drag this change to sim Tier 1.
2. **The identical bug in the mock draft** — G2's lane (§10).
3. **Any change to `owner_user_id`, `_mfl_member_id`, or the synthetic-id
   scheme.**
4. **MFL live polling** — `draft.live_poll` and the mid-draft latency probe are
   untouched.
5. **A prettifier in the mobile fallback.** Keeping `DraftRoomScreen.tsx`
   untouched is a deliberate scope and sim-tier decision.
6. **A healing / backfill pass.** Not needed: `_render_mfl` runs per request
   (only the raw upstream `_Entry` is cached — `build_board`/`_refresh` cache
   the fetched export and `_render` runs after the cache lookup on every
   request), so the first request after deploy is correct. Stored MFL data is
   already right: `draft_picks.owner_username` is written with resolved names by
   `_sync_mfl_owned_picks` (`server.py:9229/9232`), and `league_members.username`
   holds cleaned franchise names. No migration, no backfill, no cache
   invalidation.
7. **Building MFL support into the mobile QA harness** — real, valuable, and
   far larger than this fix. Named as a backlog item in `scope.md` §3.

---

## 8. Test plan

### Backend pytest — the primary gate

All fixtures committed and hermetic (no network):
`backend/tests/fixtures/draft/mfl-complete/` (league `10005`, host `www48…`,
1 unit, 30/30 picks made, franchises `0001`–`0010`, first three MFL player ids
`17472` / `17473` / `17497`), `mfl-partial/` (36/72, carries
`"[Pick traded from …]"` comments), `mfl-made0/`, `mfl-multi-unit/`. **None
carry franchise names** — the export has none — which is exactly why the tests
must supply the map.

File: `backend/tests/test_draft_board.py` (claimed for G1; G2's mock tests live
in `backend/tests/test_mock_draft.py`, G3 is mobile-only — disjoint).

| ID | Level | Requirement | Assertion | Anchor |
|---|---|---|---|---|
| T-289-01 | unit | R-1 | `mfl-complete` + `mfl_usernames={"user-7": "Eire Rebels", …}` ⇒ every `order[]` entry's `owner_username` is the mapped name | extend `test_m5_mfl_franchise_and_player_maps_are_honoured`, `test_draft_board.py:657` |
| T-289-02 | unit | R-2 | A franchise present in the grid but absent from `mfl_usernames` ⇒ `owner_username == "Team 0003"`; **no** entry's `owner_username` contains `"mfl:"`; never `None` while `fid` is set | same file |
| T-289-03 | unit | R-5 | `mfl_player_ids={"17472": "ours-x"}` + a `players` row for `ours-x` ⇒ `picks[0]["name"]` / `["position"]` / `["team"]` populated from that row | same test (it already injects both maps at `:665-666`) |
| T-289-04 | unit | R-8 | `mfl_player_ids={}` + `mfl_player_names={"17472": ("Cam Skattebo", "RB")}` ⇒ `name == "Cam Skattebo"`, `position == "RB"`, `team is None`, `player_id == "17472"` | same file |
| T-289-05 | unit | R-9 | On `mfl-complete` with both maps empty ⇒ every `picks[]` entry's `name` matches `^Player \d+$`. **Separately, across all four corpora and in every map configuration ⇒ `re.search(r"[A-Za-z]", p["name"])` for every entry.** The second is the durable global assertion; the first is corpus-specific and must not be applied to `mfl-multi-unit` (see T-289-14) | same file |
| **T-289-06** | unit | **R-7 (discriminating)** | **The wrong-player guard. Spec'd in full below the table — a build agent must implement it exactly.** | same file |
| T-289-07 | unit | R-6 | Record the id list of every `fetchers.players` call. The **hydration** call's id set is exactly `{mfl_player_ids[pid] for non-sentinel picks whose pid crosswalked}`; with `mfl_player_ids={}` the hydration call is **not made at all**. Do **not** assert a global `call_count` — `_undrafted` makes its own call at `draft_board_service.py:934` | same file |
| T-289-08 | unit | R-3 / R-11 | **Inline synthetic `draftResults` dict** (spec'd below) with one pick carrying `"franchise": ""` ⇒ that entry has `owner_user_id is None and owner_username is None`, the payload's `order_confidence == "unknown"`, and every entry's `original_user_id` / `original_username` are `None` | same file |
| **T-289-14** | unit | **R-15** | `mfl-multi-unit` with both maps empty ⇒ **exactly one** `picks[]` entry has `name == "No selection"`, with `player_id == "0000"`, `position == ""`, `team is None`; `len(picks) == 192` unchanged; that entry satisfies the letter-containing assertion | same file |
| T-289-09 | route | R-1 / R-4 | `test_m5_07`'s payload has non-`null` `owner_username` on `my_picks` **and** on at least one non-linking franchise — **requires extending the `mfl_league` fixture** (below) | `test_draft_board.py:991` |
| T-289-10 | regression | R-12 | `test_m5_06` flag-off byte-identical payload still passes (flag off ⇒ zero MFL reads, unchanged bytes) | `test_draft_board.py:952` |
| T-289-11 | regression | R-12 | `test_m5_10` — no Sleeper league's response changes (D10); `EXPECTED_KEYS` unchanged | `test_draft_board.py:1109` |
| T-289-12 | regression | R-13 | `test_m5_07`'s `len(mfl_league) == 1 and "TYPE=draftResults" in mfl_league[0]` still holds | `test_draft_board.py:1022` |
| T-289-13 | hermeticity | — | `test_the_whole_matrix_is_replayed_never_live` still reports zero live egress | `test_draft_board.py:695` |

### T-289-06 — the discriminating wrong-player test (spec'd in full)

An earlier draft of this test was **non-discriminating**: its fetcher raised on
any uncrosswalked id, so the colliding row was never fetched, never landed in
the returned map, and `rows.get(raw_mfl_id)` returned `None` — the buggy
implementation passed. Credit to the Planner for catching it. The test must
construct the collision **inside the returned rows**, using corpus-native ids.

`mfl-complete`'s first two picks are MFL ids `17472` and `17473`
(`test_draft_board.py:910`, `MFL_TAKEN`). Set up:

- `mfl_player_ids = {"17472": "17473"}` — pick A's MFL id crosswalks onto a
  value that is **also pick B's raw MFL id**.
- The `players` fetcher holds exactly one row: `{"17473": <row named "WRONG">}`.
- `mfl_player_names = {}` (so pick B must land in tier 3).

Assert:

1. Pick A (`mfl 17472`) resolves to `"WRONG"` — tier 1, correct behaviour.
2. Pick B (`mfl 17473`, **uncrosswalked**) resolves to `"Player 17473"` — and
   **never** `"WRONG"`.
3. The hydration call's id list is exactly `["17473"]` (pick A's crosswalked id
   only) — pick B's raw id was never queried.

This **fails** on `rows.get(pick["player_id"])` (pick B would adopt `"WRONG"`)
and passes only on the per-pick-gated, crosswalked-id-keyed implementation.
It is the assertion that makes R-7 real.

### T-289-08 — the synthetic franchise-less grid (spec'd in full)

**No committed corpus can drive this test.** Verified across all four:

| corpus | picks | franchise-less |
|---|---|---|
| `mfl-complete` | 30 | **0** |
| `mfl-made0` | 60 | **0** |
| `mfl-multi-unit` | 192 | **0** |
| `mfl-partial` | 72 | **0** |

That is by design — every manifest pins *"franchise populated on EVERY pick,
made or not (D8's premise)"*. An earlier draft said "`mfl-made0` or a trimmed
grid", which was both wrong and an unspecified fixture job handed to the build
agent.

Use an **inline synthetic `draftResults` dict** in the test body. Do **not** add
or hand-edit a corpus file: corpora carry `"provenance": "recorded-live"` and
editing one would falsify that. Minimum shape:

```python
{"draftResults": {"draftUnit": {
    "unit": "LEAGUE", "draftType": "SAME",
    "draftPick": [
        {"franchise": "0001", "player": "17472", "pick": "01", "round": "01",
         "timestamp": "1785589226", "comments": ""},
        {"franchise": "",     "player": "",      "pick": "02", "round": "01",
         "timestamp": "",     "comments": ""},
    ]}}, "version": "1.0", "encoding": "utf-8"}
```

Assert: the franchise-less entry has `owner_user_id is None` and
`owner_username is None`; the payload's `order_confidence == "unknown"` (**not**
`"unset"` — that value is Sleeper-only); and every `order[]` entry's
`original_user_id` / `original_username` are `None`.

**Fixture change required — the plan's R-5 risk, confirmed.** The route fixture
`mfl_league` (`backend/tests/test_draft_board.py:931-934`) stubs
`load_league_members` with rows that have **no** `username` key:

```python
monkeypatch.setattr(server, "load_league_members", lambda lid: [
    {"user_id": OPERATOR, "player_ids": []},
    {"user_id": f"mfl:{MFL_LEAGUE}.f0010", "player_ids": ["ours-rostered"]},
])
```

Both rows must gain `username` values, or T-289-09 is vacuous — it would pass on
the `Team <fid>` fallback and prove nothing about the real lookup. Keep at least
one franchise **without** a member row so the fallback stays covered by the same
fixture.

**Failing-first (mandatory, pipeline standing rule):** run T-289-01 and T-289-03
against `7cea1fa` and paste the failure text into `status.md`.

**Suite:** `python3 -m pytest backend/tests/ -q` — baseline on this worktree is
**2297 passed, 1 skipped**; the count rises by the number of new test functions.
Log the result in `living-memory/TEST_LEDGER.md`.

### Mobile typecheck

`cd mobile && npx tsc --noEmit` — must stay clean (baseline: exit 0). No mobile
file changes; this is a guard, not a target. Note: this worktree has real
`node_modules` installed — do **not** symlink the main checkout's, it lacks
`@react-native-cookies/cookies`.

### Maestro

**No new or extended `mobile/.maestro/` flow is authored.** The mobile QA
harness is Sleeper-fixture-driven (`FTF_SLEEPER_FIXTURES_DIR`) and has no MFL
seam: `backend/test_users.py`, `backend/test_support.py`, `qa/` and
`mobile/.maestro/*.yaml` contain zero MFL references (the only `mfl` hits under
`.maestro/` are unrelated screenshot filenames). MFL's only test seam is the
`server._mfl_draft_opener()` monkeypatch, which pytest uses and Maestro cannot
reach. An MFL Maestro flow is therefore not authorable without first building
harness support — out of scope for this item, named as a backlog item in
`scope.md` §3.

**Substituted coverage, which is stronger than a fixture flow would be:**
1. The fourteen backend tests above (T-289-01…14), two of them failing-first,
   including the discriminating wrong-player guard T-289-06.
2. **A live-league verification against the operator's Dependables MFL league
   (62846)** — the real league where #289 was observed. Full procedure in §9.
3. The two existing Draft Room flows as no-regression checks:
   `mobile/.maestro/flows/rookie/d1-draft-room-complete.yaml` and
   `d2-draft-room-order-not-set.yaml` (Sleeper corpus, harness user
   `qa_standard`) — the sim-gate Tier 3 subset.

---

## 9. Live-league QA acceptance procedure (Dependables, 62846)

**Operator ruling: this is the acceptance surface for both halves of the fix.**
It is a first-class deliverable, not a footnote. It supplements the backend
tests; it does not replace them.

### Preconditions

- Backend under test carries the fix (local `python run.py`, a Render preview,
  or `main` post-deploy — record which in `status.md`).
- The operator's account is linked to MFL league **62846** ("Dependables") and
  the league row carries a `platform_host` (if it did not, the Draft Room would
  render `platform_unsupported` and the original report could not exist).
- `draft.mfl` and `draft.room` are `true` (both are, on the base commit —
  `config/features.json:149,151`).
- Any credential needed comes from `secrets.local.env`, never from chat.

### Steps

1. Launch a dev build (or TestFlight build) pointed at the backend under test.
2. Sign in as the operator.
3. Make **Dependables (62846)** the active league — League tab → league
   switcher.
4. Open the Draft Room: the **Draft** tab (`draft.tab` is true, so it is the
   third tab), or the deep link `app/league/draft-room`.
5. Capture a full-screen screenshot of the order list and one of the made-picks
   list into `docs/feedback/items/289-mfl-draft-room-ids/`.

### Per-requirement pass criteria, observable on 62846

| Req | What must be true on screen | Fail signature |
|---|---|---|
| R-1 | Every order row's owner cell reads a **franchise name** (e.g. `Eire Rebels`) | any row reading `mfl:62846.f0001` — the exact string from the report |
| R-2 | A franchise with no stored name reads `Team 0007`-style | any `mfl:` prefix anywhere on the screen |
| R-3 | Rows the grid leaves unassigned read `Unassigned` | a bare `Team ` with no number |
| R-4 | The operator's own rows (My picks) read their franchise name | `mfl:62846.f<their fid>` |
| R-5 | Every made pick reads a **player name** with a **coloured position chip** (QB orange / RB green / WR blue / TE purple — `docs/cross-client-invariants.md` § Position color tokens, applied by `positionOf`, `mobile/src/components/draft/DraftRows.tsx:51`) and, where known, ` · TEAM` | a bare number, or the dim `—` chip on a row that also has a real name |
| R-8 | Rows resolved from the DP tier read a real name with a coloured chip but **no** ` · TEAM` suffix | a name with a `—` chip (means position was lost, not just team) |
| R-9 | Any unresolvable row reads `Player 17472`-style | **a bare numeric id — this is the original bug and is an automatic FAIL** |
| R-15 | A passed/forfeited slot reads `No selection` with a dim `—` chip | `0000`, or `Player 0000` |
| R-11 | Traded rows read `from —` | (known, accepted — §7 item 1) |

### Crosswalk-coverage count (folded-in spike S-2)

The tier-3 fallback is deliberately greppable (`^Player \d+$`), which makes the
count mechanical. The tier-S sentinel is counted **separately** and excluded
from the tier-3 denominator — it is not a coverage failure, it is a slot that
had no pick.

**Capture the payload.** Preferred, hermetic-ish: if the local DB already holds
the league —

```bash
sqlite3 data/trade_finder.db \
  "SELECT sleeper_league_id, platform, platform_host FROM leagues
   WHERE sleeper_league_id='62846';"
```

— boot the QA harness against a **scratch copy** (`qa/lib/harness.py`
`make_scratch_db` + `boot_server`; the live DB is never written) and
`GET /api/draft/board?league_id=62846` with an authenticated session, saving the
JSON to `feedback-workspace/289/board-62846.json` (gitignored scratch).

If the league lives only in prod, capture the same response from the
authenticated dev build (Expo network inspector → save response body) rather
than pointing a local server at prod.

**Count.**

```bash
python3 - <<'EOF'
import json, re
b = json.load(open('feedback-workspace/289/board-62846.json'))
picks = b['picks']
# `my_picks` is a subset of `order`; unioning them double-counts the operator's
# rows. That is harmless here because this list feeds only the `mfl:` scan,
# where any hit at all is a failure — len(owner_rows) is NOT a meaningful total.
owner_rows = b['order'] + b.get('my_picks', [])

sentinel = [p for p in picks if p['name'] == 'No selection']
scored   = [p for p in picks if p not in sentinel]          # tier 3 denominator
fallback = [p for p in scored if re.fullmatch(r'Player \d+', p['name'] or '')]

# HARD FAILS. "A rendered name must contain at least one letter" is the property
# actually wanted: it subsumes empty names, bare ids, and stray sentinels like
# "0000" that an equality-to-player_id check would miss.
letterless = [p for p in picks if not re.search(r'[A-Za-z]', p['name'] or '')]
mfl_owner  = [o for o in owner_rows if 'mfl:' in (o.get('owner_username') or '')]

nochip = [p for p in scored if not (p['position'] or '').strip()]

print(f"made picks: {len(picks)}  (sentinel 'No selection': {len(sentinel)})")
print(f"tier-3 fallback: {len(fallback)} / {len(scored)} "
      f"({len(fallback)/max(len(scored),1):.1%})  -> REPORT to operator, not a gate")
print(f"HARD FAILS -> letter-less name: {len(letterless)}  mfl: in owner: {len(mfl_owner)}")
print(f"no position chip: {len(nochip)} / {len(scored)}")
if letterless: print("  offenders:", [(p['player_id'], p['name']) for p in letterless[:10]])
EOF
```

**Verdict rules.**

- **Two absolute FAILs, no judgement involved.** `letter-less name` **> 0** or
  `mfl: in owner` **> 0** ⇒ **FAIL. Do not ship.** These are the reported bug,
  unfixed.
- **`tier-3 fallback` has NO pass bar — report it.** Record the count and rate
  and hand them to the operator, who decides ship / refresh-and-recount. A high
  rate is not a code defect: it points at a stale player cache or a stale DP
  crosswalk file, and the first remedy is `docs/runbook.md:482` § Player-cache
  refresh followed by a re-count. (An earlier draft set a `< 10%` bar; the
  Planner measured 49% against the committed corpora, which proved the bar was
  a guess. A gate that fails on first contact with real data trains people to
  ignore gates — see §5.)
- `no position chip` is likewise **reported, not gated** — it is the tier-2 and
  tier-3 share, and it tells the operator how much of the board is resolving
  below tier 1.
- Record every count verbatim in `status.md` and in the
  `living-memory/TEST_LEDGER.md` entry. **Do not claim "names are fixed" without
  the numbers** — the fix's coverage on the player half is an empirical
  property, not an assertion.

### Sim gate

Tier **3** (backend route consumed by mobile) — run
`mobile/.maestro/flows/rookie/d1-draft-room-complete.yaml` and
`d2-draft-room-order-not-set.yaml`, log in `TEST_LEDGER.md`, write
`qa/sim-runs/last-sim-run.json`. See `scope.md` §5 for the matrix reading.

---

## 10. Cross-group finding (G2, do not act)

Recorded for the orchestrator. **G1 must not touch either file.**

The same name-vs-id defect exists in the mock draft, verified on `7cea1fa`:

- `backend/mock_draft_service.py:1013` —
  `"owner_username": ctx.usernames.get(str(owner)) if owner else None`
- fed from `backend/server.py:11438` —
  `usernames = {str(m.user_id): m.username for m in members}`, built off the
  **session league object**, not `league_members`. For an MFL league those
  member usernames are whatever the session carries, not the franchise names
  the Draft Room fix will now resolve.
- rendered at `mobile/src/screens/MockDraftScreen.tsx:284` —
  `slot?.owner_username ?? String(onClock.roster_id)`.

Both files are G2's (`batch-plan.md` § File ownership). Consequence worth
flagging: after G1 ships, an MFL league's **Draft Room** shows franchise names
while its **Mock Draft** may still show ids — a visible inconsistency between
two adjacent surfaces. Orchestrator's call whether G2 absorbs it.

---

## 11. Citation corrections to the plan

Every load-bearing citation in `plan.md` was re-read against `7cea1fa`. All
substantive claims hold. Four line references drift by one or two:

| Plan says | Actual | Impact |
|---|---|---|
| §1(b) heading: `draft_board_service.py:1086-1088` | `1087-1089` (the plan's own §3 table has it right) | none — cosmetic inconsistency inside the plan |
| §3: link/re-sync member writes at `server.py:20188-20190` / `20326-20328` | the `members.append({...})` statements span `20188-20191` and `20326-20329`; a **third** writer exists at `20428-20431` | none for the fix; the third writer is worth knowing (all three write `username` = franchise name) |
| §6 R-8: mock shim `server.py:11437` | `11438` | none |
| §9: `_undrafted`'s players read | confirmed at `draft_board_service.py:934` (`rows = fetchers.players(remaining)`), and it runs **only** when `undrafted` is not suppressed | supports R-13's "no query when the crosswalk is empty" |

Two plan claims this PRD **changes** rather than corrects — see
`reconciliation-log.md`: the crosswalk-miss behaviour (§4 F2's `name: ""`) and
the rejection of `by_mfl_id`. A third item is **new**, not in the plan at all:
the id-space collision hazard behind R-7.

### Corrections to THIS PRD, made in Round 3 after the Planner's review

Recorded here so the diff between revisions is auditable. Full argument in
`reconciliation-log.md` § Round 3.

| Was | Now | Why |
|---|---|---|
| R-7 constrained only the *query list* | R-7 gates tier 1 **per pick** and mandates keying by the crosswalked id | The query list can be fully legal and still cross-contaminate via `rows.get(pick["player_id"])` — `load_players_by_ids` returns `{player_id: row}` (`database.py:7318-7333`) |
| T-289-06 used a raising fetcher | T-289-06 constructs the collision **inside** the returned rows (`mfl_player_ids={"17472": "17473"}`) | The old form could not fail on the buggy implementation — the colliding row was never fetched |
| R-3 said `order_confidence: "unset"` | `"unknown"` | MFL emits `ORDER_ASSIGNED if assigned else ORDER_UNKNOWN` (`draft_board_service.py:1133`); `ORDER_UNSET` is Sleeper-only (`:783`) |
| T-289-08 anchored on "`mfl-made0` or a trimmed grid" | Inline synthetic `draftResults` dict, spec'd in full | All four corpora have **0** franchise-less picks; "or a trimmed grid" was an unspecified fixture job |
| Contract had three tiers | Four rows — tier **S** for MFL's all-zeros sentinel (new R-15) | `mfl-multi-unit` carries `"player": "0000"` (recorded-live); the three-tier contract would have rendered `Player 0000` |
| T-289-05 asserted `^Player \d+$` globally | Global assertion is now "the name contains a letter" | The regex blessed `Player 0000`; the letter check subsumes empty, bare-id and sentinel-digit cases |
| R-6 offered "count them independently **or** assert on the id list" | One assertion: the hydration call's id set | An `or` in a test spec produces two different tests; and a global `call_count` assertion fails for the wrong reason because `_undrafted` calls `players` too |
| §5 said "strict superset" | "a superset in practice, 0 counterexamples measured (3563 vs 2828, 735 tier-2-only)" | `by_mfl_id` additionally requires `raw_name and pos` (`espn_service.py:610`), so strictness is not structurally guaranteed |
| §9 gated on `< 10%` tier-3 | Tier-3 rate is reported to the operator, never auto-failed; the letter-less and `mfl:` FAILs stay absolute | 10% was invented; the corpora measure 49% |
| §9 script used `name == player_id` as the bare-id check | `re.search(r'[A-Za-z]', name)` | The equality check misses `0000` and any other non-name string |
