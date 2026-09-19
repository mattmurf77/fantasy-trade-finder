# Plan — #295 / #296: the mock draft never puts the user in the draft

> **Feedback**
> **#295 (MockDraft):** "Mock draft feature still isn't letting the user pick for their team"
> **#296 (DraftRoom):** "Additionally, the mock draft when generating is simply excluding the users' team. So they can't make selections and they're not included in the generated mock."
>
> Both filed against v1.12.0, shipped 2026-08-10. Both are the **same** defect.
> Planner output — no production code. Author writes the PRD from this.

---

## 0. Headline

The orchestrator's hypothesis is **confirmed in its consequence and wrong in its
mechanism.** Nothing validates that `user_owner_id` appears in the resolved
order — that part is exactly right, and it is why the failure is silent. But the
cause is **not an id-namespace mismatch.** `sess["user_id"]`, `league.members[].user_id`
and the platform draft order all live in the *same* namespace (Sleeper user ids
for ffv3; the linking user's own id for MFL — `server.py:10489-10491` maps
`platform_my_team` to the real user id precisely so ids agree). No `acct_` key is
in play either: linking a Sleeper source re-keys the working key
(`accounts.migrate_board_data`, `accounts.py:513`).

The user is simply **never in the list**. `sess["league"].members` is, by a
convention that predates the mock draft and is load-bearing everywhere else in
the app, the list of **leaguemates — the caller excluded**. The mock-draft create
route reads that list as if it were "everyone in the league."

This is the **second time** this exact convention has bitten us. FB #41 is the
first: `backend/tests/test_league_total_teams.py:1-20` records that the League
hero tile showed 11 teams for a 12-team league because the client-side derivation
read the same opponents-only list — and it names **the same production league,
"Fantasy Football Version 3" (ffv3)**, as the reproduction.

---

## 1. Reproduction — proved, through the route's own resolution path

Two probes were run in this worktree against the **real** route
(`POST /api/mock-draft`), the **real** board resolver (`draft_board_service.build_board`
driven by `backend/tests/support/draft_replay.DraftReplay`), and the operator's own
recorded corpus `backend/tests/fixtures/draft/ffv3-predraft/`. The only thing
constructed by hand is the session — and it is constructed **the way
`/api/session/init` constructs it in production**, which is the whole point:

```python
# what every client sends, and therefore what session_init stores
members = [LeagueMember(user_id=r.owner_id, …)
           for r in rosters if r.owner_id and r.owner_id != me]   # ← me is EXCLUDED
```

### 1.1 The id values, ffv3 (Sleeper, `1312140920132497408`)

```
session user_id           : 313560442465169408          (mattmurf77, roster 1)
_mock_real_draft.order    : None
_mock_real_draft.source   : "randomized"
owners passed to engine   : 10 ids
  ['867830050538598400','869689490434908160','867953552205717504',
   '460238423161040896','867953231890898944','867952021926498304',
   '479505639769370624','867831697150996480','865989413879033856',
   '852642665873940480']
user in owners?           : False          ← THE DEFECT
ctx.rosters keys          : the same 10 — the user's own roster is absent too
```

`POST /api/mock-draft {league_id, rounds: 4}` → `200`:

```
settings_echo.teams       : 10        (the league has 12 rosters, 11 owned)
status                    : "complete"        ← immediately, on create
on_the_clock              : null
picks auto-made           : 40   |  by: "user" → 0
my_picks                  : 0
distinct owners in order[]: 10   |  operator present: False
any slot with is_user     : False
```

That is #295 and #296, verbatim: the mock is generated, the user's team is not in
it, no pick is ever the user's, and there is **no refusal, no error, no notice** —
the create returns `200` with a fully-drafted board.

Note the ids do not merely *fail to match* — they are all the same shape. Put the
session id next to any owner id: `313560442465169408` vs `867830050538598400`.
Same namespace, same format. The operator's id is not there at all.

**Why ffv3 fails 100 % of the time.** The corpus's manifest pins it
(`ffv3-predraft/manifest.json`): `draft_order: null`. `_order_from`
(`draft_board_service.py:785-791`) therefore returns `ORDER_UNSET`, so
`_mock_real_draft` (`server.py:11667-11668`) returns `order: None`, so
`build_settings` (`mock_draft_service.py:997-1000`) falls back to a seeded
shuffle **of `owners`** — a list the user is not in. There is no slot he could
land on.

### 1.2 The second, quieter failure — Sleeper leagues that *do* have an order

Same probe against `lakeview-complete` (assigned `draft_order`, 12 owned rosters,
55 traded picks):

```
owners passed to engine   : 11   |  user included: False
real order (from platform): 12 entries, user at index 4
settings_echo.teams       : 11        ← len(owners), not len(order)
order[] rows              : 44        ← 11 slots × 4 rounds, not 48
```

`build_settings` sets `teams = len(owners)` (`mock_draft_service.py:989`) but then
uses the 12-entry platform `order` for ownership lookups
(`owner_of`, `:944-950`). `pick_slots` only ever produces slots `1..teams`, so
**`order[11]` — the 12th draft slot — is never referenced.** One real manager is
silently deleted from every assigned-order mock, and if that manager is the user,
he is deleted. For a fully-owned 12-team Sleeper league that is roughly a 1-in-12
chance per league; for a league with an ownerless roster (ffv3 has one — roster 6,
`owner_id: null`) two slots are dropped instead of one.

So the assigned-order branch is **intermittently** broken for the user and
**always** broken for the league; the unset-order branch is **always** broken for
the user. Both branches trace to the same missing member.

### 1.3 MFL / ESPN / Fleaflicker — always broken, analytically

`_mock_real_draft` returns `{order: None, order_source: "randomized", …}` for any
non-Sleeper platform (`server.py:11650-11655`; pinned by
`test_mock_draft.py::test_w2_20_g1_a_non_sleeper_league_stays_randomized`). That
lands in the same shuffle-of-`owners` branch as §1.1. The user is never in
`owners` on those platforms either — `mobile/src/api/platformLink.ts:280` and
`mobile/src/api/espn.ts:180` filter him out exactly as the Sleeper builder does.
**Dependables (MFL 62846) fails identically and deterministically.**

### 1.4 The proposed repair, verified on the same probes

Patching `_mock_league_context` to append the session user to `owners`, and
`build_settings` to take `teams` from the resolved order when one is supplied:

| corpus | before | after |
|---|---|---|
| ffv3-predraft | teams 10 · `status: complete` · `on_the_clock: null` · user absent | teams 11 · `status: active` · `on_the_clock {pick_no: 2, slot: 2, is_user: true, roster_id: 313560442465169408}` · 1 CPU pick made |
| lakeview-complete | teams 11 · 44 order rows · 11 owners | teams 12 · 48 order rows · **all 12** owners · `on_the_clock.is_user: true` at pick 11 (its traded slot) |

---

## 2. Root cause

**Primary — `backend/server.py:11566`:**

```python
    ), [str(m.user_id) for m in members]
```

`members` is `sess["league"].members` (`:11544`), which `/api/session/init` builds
**only** from the client's `opponent_rosters` (`server.py:14353-14374`) and which
the DB-merge step explicitly refuses to add the caller to
(`:14374` `existing_member_ids = {m.user_id for m in members} | {user_id}`,
`:14380` `continue  # already in the list or is the logged-in user`). Every client
filters the caller out before sending: `mobile/src/api/auth.ts:377` and `:465`,
`mobile/src/api/espn.ts:180`, `mobile/src/api/platformLink.ts:280`,
`web/js/app.js:820` and `:2562`. So `owners` is the leaguemates, never the
league.

**Enabling — `backend/mock_draft_service.py:988-1000` + `:1061`:**

```python
988     owners = [str(o) for o in owners]
989     teams  = len(owners)
994     if order:
995         resolved_order = [str(o) for o in order]
…
998         resolved_order = list(owners)
999         (rng or random.Random(0)).shuffle(resolved_order)
…
1026        "user_owner_id": str(user_owner_id),
```

```python
1061    slot["is_user"] = owner is not None and owner == state["settings"].get("user_owner_id")
```

`build_settings` accepts a `user_owner_id` that is in neither `owners` nor
`resolved_order` and writes it into `settings` without complaint. `next_pick` then
compares it against every slot owner, never matches, and `advance_cpu`
(`:1181-1182`) never returns — it drafts the whole board.

**Secondary — the same omission, three more sites:**

| site | consequence |
|---|---|
| `server.py:11545` (`rosters` on create) | the user's own roster is missing from `ctx.rosters`, so `rostered_ids` (`:11547`, `:11561`) omits his players and **his already-rostered players stay draftable in the mock** |
| `server.py:11582` (`rosters` on resume) | same omission — and it must be fixed in lockstep with `:11545` or create and resume compute different `consensus_pool`s and the recap's `consensus_rank` shifts (INV: `_available` is derived from `rostered_ids`, `mock_draft_service.py:415-418`) |
| `server.py:11621` (`_mock_capability`) | the G2 probe reports `teams` one short, so a genuine 4-team league (`MOCK_MIN_TEAMS = 4`) is refused `league_too_small` and a 12-team league advertises 11 |

**Third — `mock_draft_service.py:989` + `:1007`:** `teams = len(owners)` while the
slot table is indexed against a possibly-longer `order` (§1.2).

---

## 3. Blast radius

| Surface | Affected? | Detail |
|---|---|---|
| Mock draft, **any non-Sleeper** league (MFL incl. Dependables 62846, ESPN, Fleaflicker) | **100 %** | randomized branch, user never in `owners` |
| Mock draft, Sleeper with **`draft_order: null`** (ffv3, and every league pre-draft-order — the common case in August) | **100 %** | same branch |
| Mock draft, Sleeper with **assigned** `draft_order` | **partially** — user excluded when his slot index ≥ `len(owners)`; ~1 slot per league dropped regardless | §1.2 |
| Mock draft — **every** league, every platform | **100 %** on the secondary defects | `teams` off by one; user's rostered players draftable; capability probe under-reports |
| **Real Draft Room** (`GET /api/draft/board`) | **NO** | the board is built from the platform export, not from session members: `_order_from` derives owners from `rosters[].owner_id` (`draft_board_service.py:750-752, 763-779`) and `my_picks` matches on `req.user_id` (`:1248`). MFL binds `platform_my_team → link_user` for the same reason (`server.py:10489-10491`). This is exactly why the operator sees himself in the Draft Room and not in the mock, on adjacent screens. |
| Trades / Matches / League summary | **NO** | those consumers *want* leaguemates; `total_teams` already comes from Sleeper's `total_rosters` since FB #41 |

**Is every user affected?** Yes — no user has ever been able to pick in a mock on
a league whose platform order is unset or non-Sleeper, which is the large majority
of leagues in August. The residual assigned-order case spares most users but still
deletes one manager from every mock.

---

## 4. Did the previous batch cause this, or expose it?

**It exposed it. We did not break it — we shipped a fix for something that was
never the problem, on top of a feature that had never worked.**

Git evidence:

| commit | date | relevance |
|---|---|---|
| `8e146a3` draft-extensions W2 | 2026-08-06 | introduced `_mock_league_context`; `git show 8e146a3:backend/server.py` line 10277 is already `), [str(m.user_id) for m in members]`. **The defect is original to the feature.** |
| `023f747` W2d | 2026-08-07 | added `_mock_real_draft` / the four resolution inputs — did not touch `owners` |
| `6caca35` "mock draft: ON — operator override of the calibration gate" | 2026-08-08 | flipped `draft.mock` true. **This is the moment the latent defect became user-reachable.** |
| `6c304c7` feedback #289-#294 (v1.12.0) | 2026-08-10 | `git show 6c304c7 -- backend/server.py \| grep -E '^[-+].*(_mock_league_context\|owners\|user_owner_id)'` returns **one line, a comment**. The batch's server.py changes were `_mock_usernames` (D-16) and `abandon_completed_mock_drafts` (#292). |

So the batch is causally clean. What it *did* do is make the failure legible: #291
shipped the "Pick" affordance and "Tap to draft" header on rows the user can never
reach, which is why the operator's follow-up is "**still** isn't letting the user
pick." We advertised a capability the create route had already disabled.

---

## 5. Why the #291 verification missed it — the specific gap

`docs/feedback/items/290-mock-draft-engine/plan.md:104-113` states the evidence:

> "I drove the engine end-to-end with a **synthetic 12-team / 4-round league** and
> a 60-rookie priced pool. Result: `advance_cpu` stopped … `roster_id: 'u5',
> is_user: True`; the user then took **4 turns**, all 4 recorded with `by: "user"`"

Three named gaps, each of which the fix's tests must close:

1. **The drive was at the ENGINE layer, not the route.** It called
   `build_settings(owners=[…'u5'…], user_owner_id='u5')` — hand-passing an id that
   was, by construction, one of the owners. `build_settings` is the *consumer* of
   the defect; the defect is in the *producer* (`_mock_league_context`). No engine
   drive can see it.

2. **The route's own test fixture reproduces the same coincidence.**
   `backend/tests/test_mock_draft.py:938-942`:
   ```python
   league = League(league_id=LAKEVIEW_LEAGUE, …,
                   members=[LeagueMember(user_id=OPERATOR, …)])
   sess = {"user_id": OPERATOR, "league": league, …}
   ```
   The session user **is** the only league member — the exact inverse of the
   production shape. Every route-level mock test in the file inherits this fixture.
   That fixture is why 40-odd passing route tests say nothing about this bug. (It
   also caps the league at one member, so every one of those tests is answered by
   `league_too_small` before order resolution is reached at all.)

3. **The two "pinning tests" cited in the plan pin the opposite property.**
   `test_mock_draft.py`'s `make_state(…, user=…)` helper is called with `user="zz"`
   / `user="nobody"` — *deliberately not an owner* — in a dozen tests, and with
   `user="b"` (an owner) in the rest. The suite proves the engine handles **both**
   cases correctly. It never asserts which one the route produces.

4. **The UI check that would have caught it could not run.** `d3-mock-draft-loop.yaml`
   carries a blocking precondition (its header, lines 24-32): ffv3 appears in no
   fixture profile, so the flow cannot find the league row. And the pre-ship sim
   gate for the batch was **NOT PERFORMED** (operator-directed bypass, recorded in
   the commit message and `TEST_LEDGER.md`). Note that the QA `standard.json`
   profile *would* have reproduced it — `seed_ui_test_db.py:529-535` builds
   `opponents` with `if uid != world.app_uid`, i.e. the production shape, and fills
   to `total_rosters: 12`.

**One-line statement of the gap:** *every existing test supplies `user_owner_id`
and `owners` from the same hand-built literal; nothing in the suite runs the
resolution that derives them from a session, so the one place they can disagree
was never executed.*

---

## 6. Approach — repair the membership **and** fail loudly

Both halves ship together. The repair fixes today's leagues; the guard is what
makes the *next* divergence a visible refusal instead of a silently CPU-drafted
board. **A silent exclusion is the actual defect class here**, and it must be made
structurally impossible, not merely fixed once.

### 6.1 The repair (four sites, all in `backend/server.py`)

| # | Site | Change |
|---|---|---|
| R1 | `_mock_league_context` `:11566` | `owners` = member ids **plus** `str(sess["user_id"])`, de-duplicated, caller appended (order is irrelevant — the randomized branch shuffles, the assigned branch indexes off `order`) |
| R2 | `_mock_league_context` `:11545` | `rosters` gains `{sess["user_id"]: sess["user_roster"]}` so `rostered_ids` covers the caller's players |
| R3 | `_mock_context_from_row` `:11582` | **identical** roster addition — create and resume must compute the same `rostered_ids`, or the pool and every `consensus_rank` shift between POST and GET |
| R4 | `_mock_capability` `:11621` | same owners construction as R1, so the G2 probe and the create route count teams identically |

R1 alone fixes #295/#296. R2–R4 are the same omission at three more sites and are
in scope because leaving them makes the fix internally inconsistent (R3 in
particular is a correctness requirement, not polish).

### 6.2 The `teams`/`order` consistency rule (`mock_draft_service.build_settings`)

When an explicit `order` is supplied, `teams` and the slot table derive from
`len(resolved_order)`, not from `len(owners)` (`:989`, `:1007`). Without this,
R1 fixes the missing user but the assigned-order branch still truncates the last
slot whenever `len(owners) != len(order)` — which ffv3 (one ownerless roster) will
hit the moment its commissioner sets a draft order.

### 6.3 The fail-loud guard — a fourth `start_refusal` rung *and* an engine-level raise

Two layers, because they catch different things and the G2 invariant ("the probe
may never say something the create route contradicts") requires them to agree.

**(a) Ladder rung — `mock_draft_service.start_refusal` (`:426-443`).** New constant
`REASON_USER_NOT_IN_DRAFT = "user_not_in_draft"`, checked when the caller supplies
the id:

```python
def start_refusal(ctx, owners, *, user_owner_id: str | None = None) -> str | None:
    …existing three rungs…
    if user_owner_id is not None and str(user_owner_id) not in {str(o) for o in owners or ()}:
        return REASON_USER_NOT_IN_DRAFT
```

Keyword-only with a `None` default, so the existing call sites and the ~8 tests
that call `start_refusal(ctx, owners)` positionally are untouched. Placed **last**,
after `league_too_small`, on the shipped ladder's own logic (`:430-435`): a
2-team league should hear its size problem first; `user_not_in_draft` joins
`league_too_small` as a state the user cannot act on. `capability()` (`:446-475`)
forwards the same argument so probe and create cannot diverge.

**(b) Engine backstop — `build_settings`.** New `UserNotInDraft(MockDraftError)`
(alongside `NotYourTurn` `:310` / `PlayerUnavailable` `:314`), raised when
`str(user_owner_id) not in resolved_order`. This catches what (a) structurally
cannot: the assigned-order case where the user **is** in `owners` but the platform
order does not name him (a mid-season roster takeover, a commissioner-rebuilt
draft, an id we resolved to a stale roster). `resolved_order` is what `next_pick`
actually reads, so this is the invariant stated at the point of truth.

The route (`server.py:11841`) wraps the `build_settings` call and maps
`UserNotInDraft` to `jsonify(mds.empty_payload(mds.REASON_USER_NOT_IN_DRAFT))` —
the **same** typed-empty body the ladder produces, so the two layers are
indistinguishable to the client.

**Client compatibility:** the reason enum is open by construction (D10) —
`mobile/src/api/mockDraft.ts:36-40` types it as `… | (string & {})` and
`MockDraftScreen.tsx:785-796` has a `default:` arm. A new reason is therefore
**backward compatible with shipped builds**, which fall back to "This mock draft
isn't available right now." A one-line copy arm plus a
`mock-entry.blocked.user_not_in_draft` testID in `DraftRoomScreen.tsx:296-345` is
the mobile delta — small, and it is what turns a generic message into an honest
one.

### 6.4 Alternatives considered and rejected

| Alternative | Verdict |
|---|---|
| **Fix in the clients** — have each client include the caller in `opponent_rosters` | **Rejected.** Four builders (`auth.ts` ×2, `espn.ts`, `platformLink.ts`) plus `web/js/app.js`, the field's name and contract both say *opponents*, `session_init` carries the caller separately as `user_player_ids`, and every already-installed 1.12.0 build keeps the bug forever. Server-side is one site and fixes shipped clients. |
| **Change `session_init` to append the caller to `league.members`** | **Rejected.** `league.members` is the app's "leaguemates" list: `TradeService.add_league`, matches, power rankings, free-agent computation and the League summary all read it, ~20 `.members` references in `server.py` alone. Widening it repo-wide to fix a mock-draft bug is the opposite of a surgical change (coding-guidelines §3), and FB #41's fix deliberately went the other way — persist `total_rosters` rather than redefine the member list. |
| **Read owners from `load_league_members(league_id)`** (the DB table *does* include the caller — `server.py:14853-14876`) | **Rejected as the primary source, kept as a possible cross-check.** `test_league_total_teams.py:8-16` records that this table is a per-login snapshot that both under-counts (ownerless rosters) and over-counts (departed managers never pruned). It is already loaded in `_mock_usernames` (`:11506-11508`), so it costs nothing to *assert* against — but it must not be the source of truth. |
| **Derive owners from the platform draft order** | **Rejected.** ffv3 — the reported league — has no draft order. This fixes the case that mostly works and not the case that always fails. |
| **Guard only, no repair** (refuse every mock the user is not in) | **Rejected.** It is honest but it turns a broken feature into a disabled one on ~every league. Ship both. |
| **Repair only, no guard** | **Rejected.** This is precisely how #291 got the wrong answer: the feature *looked* fine on a context where the ids happened to line up. The class of defect is "silently produced a mock the user is not in"; a repair without a guard leaves the class intact. |

---

## 7. Platforms touched · file ownership

| Owner | Files | Scope |
|---|---|---|
| **Backend** | `backend/server.py` (`_mock_league_context`, `_mock_context_from_row`, `_mock_capability`, `mock_draft_route` create arm — `:11533-11622`, `:11841-11853`) | R1–R4, the `UserNotInDraft` → typed-empty mapping |
| **Backend** | `backend/mock_draft_service.py` (`:81-91` constants, `:306-320` exceptions, `:426-475` ladder + probe, `:958-1030` `build_settings`) | new reason + exception, 4th rung, `teams`/`order` rule |
| **Backend (tests)** | `backend/tests/test_mock_draft.py` | §8 — including **replacing** the `session` fixture's league shape |
| **Mobile** | `mobile/src/api/mockDraft.ts` (reason union), `mobile/src/screens/MockDraftScreen.tsx` (`emptyCopy` arm), `mobile/src/screens/DraftRoomScreen.tsx` (`mockBlock` arm + testID) | copy for the new refusal only — **no behavior change**, and it is optional-by-D10 |
| **Docs** | `docs/api-reference.md` (§ Mock draft: capability-probe ladder now four rungs; **and the stale "the CPU-bot mock is CUT" status blockquote at `:426`, which has been false since `6caca35`**), `living-memory/DECISIONS.md` (new D-0NN), `living-memory/GOTCHAS.md` (new G-0NN: "`league.members` never contains the caller"), `docs/feedback/items/295-mock-user-not-in-draft/` | |
| **Maestro** | `backend/tests/fixtures/profiles/standard.json` (+ ffv3 league entry), `mobile/.maestro/flows/rookie/d3-mock-draft-loop.yaml` | clear the blocking precondition so the flow can run at all; extend d3 to assert the user is on the clock |
| **Untouched** | `backend/draft_board_service.py`, every client session-init builder, `web/` | the Draft Room is not defective; the clients' contract is correct |

No schema change. No new route. One new value on an already-open enum.

---

## 8. Test plan — the tests that would have caught this

The organising principle: **no test in this set may hand-pass both `owners` and
`user_owner_id`.** At least one test must derive them the way the route does.

| id | Level | Test | What it sees that the old suite could not |
|---|---|---|---|
| **T-295-01** | **Route, end-to-end, real corpus** | Session built in the **production shape** (members = owned rosters **minus** the caller, from `ffv3-predraft/league/…/rosters.json`), `DraftReplay("ffv3-predraft")` installed, `POST /api/mock-draft`. Assert: `settings_echo.teams == 11`; the operator id appears in `order[].owner_user_id`; `status == "active"` (never `"complete"` on create); `on_the_clock.is_user is True` at his slot; then `POST /pick` succeeds and the pick records `by: "user"`. | **This is the test.** It runs `_mock_league_context` → `_mock_real_draft` → `build_settings` → `advance_cpu` in one call, so the producer/consumer disagreement is executed. Every existing route test short-circuits at `league_too_small` because the fixture league has one member. |
| **T-295-02** | Fixture contract | An assertion (or a rewritten shared fixture) that the route tests' session league **never** contains `sess["user_id"]` among `league.members`. | Pins the production shape into the harness so it cannot drift back to the coincidence that produced #291's wrong answer. Without this, T-295-01 rots the first time someone "simplifies" the fixture. |
| **T-295-03** | Route | Same as T-295-01 against `lakeview-complete` (assigned order, 55 traded picks): `teams == 12`, `len(order[]) == 48`, all 12 distinct owners present, the user among them. | Catches the `teams = len(owners)` truncation, which is invisible unless the platform order and the member list differ in length. |
| **T-295-04** | Route | Non-Sleeper (`get_league_draft_context → platform: "mfl"`): randomized branch still contains the user. | Dependables (62846) — the deterministic 100 % failure on the other platform. |
| **T-295-05** | Service | `start_refusal(ctx, owners, user_owner_id=<not in owners>) == REASON_USER_NOT_IN_DRAFT`, **and** `capability(...)["reason"]` is the same string, **and** the three existing rungs still outrank it. | The G2 shared-ladder invariant, extended. Also asserts the positional 2-arg call signature is unbroken. |
| **T-295-06** | Service | `build_settings(..., order=[a,b,c], user_owner_id="zz")` raises `UserNotInDraft`; the route maps it to `200 {"empty": true, "reason": "user_not_in_draft"}`. | The backstop for the case the ladder cannot see: user in `owners`, absent from the platform order. |
| **T-295-07** | Route | `rostered_ids` from `_mock_league_context` and from `_mock_context_from_row` are **equal** for the same session+row, and both include the caller's `user_roster`. | Guards R2/R3 as a pair — if only one is fixed, the pool silently differs between create and resume and every `consensus_rank` in the recap shifts. |
| **T-295-08** | Route | `_mock_capability(...)["teams"]` equals the real owned-roster count; a 4-owner league reports `can_start: true`, not `league_too_small`. | The off-by-one refusal on genuinely-4-team leagues. |
| **T-295-09** | Maestro `d3` | After the profile blocker is cleared: on the mock board, **before any tap**, `assertVisible` the on-the-clock card naming the user's own team, then tap a rookie and confirm. | #291's flow asserted the *affordance* was visible; it never asserted the user was ever **on the clock**. That assertion is the UI-level statement of this bug. |

**What the previous suite structurally could not see, stated plainly:** it tested
the engine with ids the test itself chose, and it tested the route with a league
whose only member was the caller. The engine was correct in both branches; the
route was wrong; and no test ever put the route's real inputs into the engine.
Passing tests were true statements about code that has never worked in production.

Also required by the gates: `mobile/scripts/testid-lint.sh` for any new testID,
and `npm run test:mock-lifecycle` (not in CI — run by hand).

---

## 9. Verification against the operator's real leagues

Synthetic evidence is not acceptable for this fix. Three tiers, in order:

**Tier 1 — recorded-real corpora, in CI.** T-295-01/03 run against
`ffv3-predraft` and `lakeview-complete`, which are `provenance: recorded-live`
captures of the operator's own leagues. This is as close to production as an
automated test gets, and it is where the regression bar sits permanently.

**Tier 2 — live backend, operator's session.** Before merge, against a running
backend with the operator's real session (Sleeper token, not a QA user):

- **ffv3 (Sleeper, `1312140920132497408`) — the reported league.** Start a mock.
  Required: the on-the-clock card names **mattmurf77's** team at his slot; the
  order rail lists **11** teams including him; the board does **not** arrive
  complete. Make a pick; confirm it lands with `by: "user"` and that the player
  leaves the undrafted list. Complete the mock; the recap's "My picks" is
  non-empty.
- **Dependables (MFL, 62846).** Same checks. Additionally, per D-16, no rendered
  string may contain `mfl:` — this is the platform where the user's own franchise
  id is the one non-synthetic id in the league, so it is the sharpest test that
  the caller is resolved and not fabricated.
- **A third Sleeper league with an assigned draft order** (Lakeview if the
  operator still holds it). Required: the order rail shows **all 12** teams, and
  the team that used to occupy draft slot 12 is present.
- **Negative control:** open the **real** Draft Room on ffv3 immediately before
  and after. It must be byte-identical — it was never broken, and it shares
  `UndraftedRowView` with the mock.

**Tier 3 — the flow that should have caught it.** Clear the `standard.json`
profile blocker (one league entry — it repairs `d1`/`d2` as a side effect) and run
`d3-mock-draft-loop.yaml` with the T-295-09 assertion added. Log it in
`living-memory/TEST_LEDGER.md` and write `qa/sim-runs/last-sim-run.json`. **This
batch does not ship on an express lane** — it touches an API contract (a new
`reason` value on the typed-empty) and a feature-flagged surface, which the
bright-line rule in `CLAUDE.md` explicitly excludes from "quick fix", and the last
batch's sim gate was already bypassed on this same feature.

**Sign-off condition.** The fix is not "done" when the tests pass. It is done when
the operator has started a mock on **ffv3 and on Dependables** and taken a pick in
each. That is the evidence standard #291 did not meet, and the reason we are here.

---

## 10. Open questions for the Author / operator

1. **ffv3 has an ownerless roster** (roster 6, `owner_id: null`). Post-fix, its
   mock is an 11-team draft in a 12-roster league. Honest, or should an ownerless
   roster get a "vacant" CPU seat so the mock's shape matches the real draft's?
   Recommendation: leave it at 11 and let `order_source: "randomized"` carry the
   disclosure — inventing a manager is worse than omitting an empty chair. Flagging
   because it is a visible number.
2. **Should `user_not_in_draft` be reachable at all after the repair?** Post-R1 the
   ladder rung can only fire on a session with no `user_id`. That is fine — the
   guard's job is to be unreachable — but the Author should confirm the rung is not
   dead code from the reviewer's perspective, and that T-295-05/06 force both
   layers.
3. **`docs/api-reference.md:426`** still declares the mock CUT and
   `CPU_MODEL_VALIDATED` False. It has been false since `6caca35` (2026-08-08); the
   #289-#294 commit claimed five such doc locations were corrected and this one was
   missed. Correct it in this batch.
