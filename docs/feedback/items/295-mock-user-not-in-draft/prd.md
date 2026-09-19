# PRD — #295 / #296: the mock draft never puts the user in the draft

> **Feedback (both v1.12.0, shipped 2026-08-10; both the same defect)**
> **#295 (MockDraft):** "Mock draft feature still isn't letting the user pick for their team"
> **#296 (DraftRoom):** "Additionally, the mock draft when generating is simply excluding the users' team. So they can't make selections and they're not included in the generated mock."
>
> Author output, Phase 1. **No production code.** Built on
> [`plan.md`](./plan.md); departures are recorded in
> [`reconciliation-log.md`](./reconciliation-log.md). Companion:
> [`scope.md`](./scope.md).
>
> **Base:** `origin/main` @ `2e0b2c7` · worktree `.claude/worktrees/fb-295-296`.

---

## Table of Contents

- [1. Context — this feature has never worked](#1-context--this-feature-has-never-worked)
- [2. Root cause, at file:line](#2-root-cause-at-fileline)
- [3. Requirements — the repair](#3-requirements--the-repair)
- [4. Requirements — fail loudly](#4-requirements--fail-loudly)
- [5. Behavioral contract for `user_not_in_draft`](#5-behavioral-contract-for-user_not_in_draft)
- [6. Requirements — docs](#6-requirements--docs)
- [7. Out of scope — guardrails](#7-out-of-scope--guardrails)
- [8. Test plan](#8-test-plan)
- [9. Done criteria](#9-done-criteria)
- [10. Open items for the operator](#10-open-items-for-the-operator)

---

## 1. Context — this feature has never worked

**The mock draft has never let any user pick, on any league, since it was
enabled.** That is not a regression from the #289–#294 batch. Stating it plainly
changes three things, so it belongs at the top rather than in an appendix:

1. **There is no "before" to restore.** Every verification must show the user
   drafting, not show the diff behaving the way the previous build did.
2. **The release note is "the mock draft now works", not "fixed a bug in the
   mock draft."** Anyone who tried it since 2026-08-08 saw a fully-CPU-drafted
   board with no turn of their own, and got no error explaining why.
3. **A green suite was not evidence.** 40-odd route tests and eleven engine
   tests passed on this defect for four days (§8.0).

Timeline, verified by `git show`:

| commit | date | what it did |
|---|---|---|
| `8e146a3` | 2026-08-06 | introduced `_mock_league_context`; the defective line is present at birth (`git show 8e146a3:backend/server.py` line 10277 is already `), [str(m.user_id) for m in members]`) |
| `023f747` | 2026-08-07 | added `_mock_real_draft` and the four resolution inputs; did not touch `owners` |
| `6caca35` | 2026-08-08 | flipped `draft.mock` ON by operator override — **the latent defect becomes user-reachable here** |
| `6c304c7` | 2026-08-10 | feedback #289–#294 (v1.12.0). Causally clean: its `server.py` changes were `_mock_usernames` (D-16) and `abandon_completed_mock_drafts` (#292) |

What `6c304c7` *did* do is make the failure legible: #291 shipped the "Pick"
affordance and the "Tap to draft" header onto rows the user can never reach.
We advertised a capability the create route had already disabled — which is why
the operator's follow-up says "**still** isn't letting the user pick."

**Reproduction (from [`plan.md`](./plan.md) §1, re-verified against the
committed corpora).** ffv3 (Sleeper `1312140920132497408`,
`backend/tests/fixtures/draft/ffv3-predraft/`) has **12 rosters, 11 owned**
(roster index 6 carries `owner_id: null`) and the operator
(`313560442465169408`) is roster 1. `POST /api/mock-draft` returns `200` with
`settings_echo.teams: 10`, `status: "complete"` **on create**,
`on_the_clock: null`, 40 CPU picks, **zero** picks with `by: "user"`, and
`my_picks: []`. No refusal, no error, no notice.

**There is no id-namespace mismatch.** `sess["user_id"]`,
`league.members[].user_id` and the platform draft order share one namespace —
`313560442465169408` and `867830050538598400` are the same shape from the same
issuer. The operator's id is simply **not in the list**.

---

## 2. Root cause, at file:line

### 2.1 Primary — `backend/server.py:11566`

```python
    ), [str(m.user_id) for m in members]        # _mock_league_context, :11533
```

`members` is `sess["league"].members` (`server.py:11544`). By an app-wide
convention that predates the mock draft, **that list is the leaguemates — the
caller excluded**:

| site | what it does |
|---|---|
| `mobile/src/api/auth.ts:377` | `.filter((r) => r.owner_id && r.owner_id !== user.user_id)` |
| `mobile/src/api/auth.ts:465` | identical filter (second builder) |
| `mobile/src/api/espn.ts:180` | `.filter((m) => m.user_id !== user.user_id)` |
| `mobile/src/api/platformLink.ts:280` | `.filter((m) => m.user_id !== user.user_id)` |
| `web/js/app.js:820`, `:915`, `:2562` | same filter, three call sites |
| `backend/server.py:14353` | `session_init` builds `members` only from `opponent_rosters` |
| `backend/server.py:14374`, `:14380` | the DB-merge step **explicitly refuses** to re-add the caller: `existing_member_ids = {m.user_id for m in members} \| {user_id}` … `continue  # already in the list or is the logged-in user` |

`_mock_league_context` reads that list as "everyone in the league." It is not.

### 2.2 Enabling — `backend/mock_draft_service.py:988-1000`, `:1026`, `:1061`

```python
988     owners = [str(o) for o in owners]
989     teams  = len(owners)
994     if order:
995         resolved_order = [str(o) for o in order]
998     else:
999         resolved_order = list(owners)
1000        (rng or random.Random(0)).shuffle(resolved_order)
…
1026        "user_owner_id": str(user_owner_id),
```

```python
1061    slot["is_user"] = owner is not None and owner == state["settings"].get("user_owner_id")
```

`build_settings` accepts a `user_owner_id` that is in neither `owners` nor
`resolved_order` and writes it into `settings` without complaint (`:1026`).
`next_pick` (`:1052`) then compares it against every slot owner, never matches,
and `advance_cpu` (`:1146`) — which returns only on `slot["is_user"]` or on
exhaustion — drafts the entire board and sets `status: "complete"`.

**Why ffv3 fails 100 % of the time.** Its manifest pins `draft_order: null`, so
`_order_from` (`backend/draft_board_service.py:740-793`) returns `ORDER_UNSET`,
so `_mock_real_draft` (`server.py:11624`) returns `order: None`, so
`build_settings` falls back to a seeded shuffle **of `owners`** — a list the
user is not in. There is no slot he could land on.

**Non-Sleeper is the same branch, deterministically.** `_mock_real_draft`
returns `{order: None, order_source: "randomized", …}` for any non-Sleeper
platform (`server.py:11646-11655`). The caller is filtered out of
`opponent_rosters` on those platforms too (`platformLink.ts:280`,
`espn.ts:180`), so **Dependables (MFL 62846) fails identically.**

### 2.3 Secondary — the same omission, three more sites

| site | consequence |
|---|---|
| `server.py:11545` (`rosters`, create) | the caller's own roster is absent from `ctx.rosters`, so `rostered_ids` (`:11547`, `:11561`) omits his players and **his already-rostered rookies stay draftable in the mock** |
| `server.py:11582` (`rosters`, resume — `_mock_context_from_row`, `:11569`) | the same omission; it must move **in lockstep** with `:11545` or create and resume compute different `rostered_ids`, hence different `consensus_pool`s, and every `consensus_rank`/`consensus_delta` in the recap shifts between `POST` and `GET` (`mock_draft_service._available`, `:1071`) |
| `server.py:11621` (`_mock_capability`, `:11605`) | the G2 probe counts teams off the same short list, so a 12-team league advertises 11 and a genuine 4-owner league is refused `league_too_small` against `MOCK_MIN_TEAMS = 4` (`mock_draft_service.py:91`) |

`:11621` is not cosmetic: it must be fixed **together with** `:11566`, or the
probe and the create route disagree about a 4-owner league — which is exactly
the G2 invariant `start_refusal`'s docstring exists to protect
(`mock_draft_service.py:431-435`).

### 2.4 Third — `teams` is the wrong quantity (`mock_draft_service.py:989`, `:1007`)

`teams = len(owners)`, but `owner_of` (`:933-951`) resolves a pick by indexing
`settings["order"]` at `slot - 1`, and `pick_slots(rounds, teams, type)`
(`:1007`, `:915`) only ever emits slots `1..teams`. When an explicit `order` is
supplied, `teams` and `order` describe the same draft only by coincidence.

Measured on `lakeview-complete` **before** the §3 repair: `owners` 11,
platform `order` 12 entries, `settings_echo.teams` 11, `order[]` 44 rows
(11 × 4) instead of 48 — **`order[11]`, the 12th draft slot, is never
referenced**, deleting one real manager from the mock. The traded-pick overlay
is mis-keyed with it, because `traded_slots` `(round, slot)` pairs are
translated to `pick_no` through that same 11-wide slot table
(`mock_draft_service.py:1008-1014`).

> **Honest scoping, and a departure from the plan.** After R1 (§3),
> `len(owners) == len(order)` on both committed corpora, so on *today's data*
> R1 alone restores lakeview to 12 teams / 48 rows. The `teams` rule is
> therefore a **structural invariant**, not a second reproduced failure: it is
> what stops the fix from being correct-by-coincidence when the session member
> snapshot and the platform order legitimately differ (a manager joins or
> leaves between `session_init` and mock-create; a co-owned roster). The plan's
> claim that ffv3 "will hit this the moment its commissioner sets a draft
> order" is **wrong** — with an ownerless roster the slot map is
> non-contiguous, `_mock_real_draft` (`server.py:11681-11687`) drops the order
> entirely, and the mock falls back to `randomized`. See
> [`reconciliation-log.md`](./reconciliation-log.md) § B-2.

---

## 3. Requirements — the repair

All requirements are numbered and mechanically verifiable. "Verified by"
names the test in §8.

### R1 — the caller is in the owner set (`server.py:11566`)

`_mock_league_context` MUST return an owner list containing
`str(sess["user_id"])` in addition to every member id, de-duplicated,
preserving the existing members' relative order (position is irrelevant: the
randomized branch shuffles, the assigned branch indexes off `order`).

- R1.1 The caller MUST be appended **only when `str(sess.get("user_id") or "")`
  is non-empty.** An empty id must never become a phantom owner — it would
  create a team nobody controls and would make the §4 guard unreachable.
- R1.2 The returned list MUST contain no duplicate ids, including when a future
  `session_init` change starts including the caller in `members`.
- R1.3 No other element of `MockContext` construction changes in this
  requirement.

*Verified by:* T-295-01, T-295-02, T-295-04, T-295-11.

### R2 — the caller's roster is in `ctx.rosters` on create (`server.py:11545`)

`rosters` MUST additionally carry `{str(sess["user_id"]): [str(p) for p in
sess.get("user_roster") or []]}`, so `rostered_ids` (`:11547`, `:11561`) covers the
caller's players and his already-rostered rookies are not offered in the mock.

- R2.1 Source is `sess["user_roster"]` (written at `server.py:14612`), which is
  filtered to the active pool exactly as opponents' `roster` lists are
  (`server.py:14356`) — the two sides stay symmetric.
- R2.2 When `sess["user_roster"]` is absent or empty the entry is an empty
  list, never a missing key: `ctx.rosters` must contain one entry per owner.

*Verified by:* T-295-07.

### R3 — the identical roster addition on resume (`server.py:11582`)

`_mock_context_from_row` MUST make the same addition as R2, from the same
source.

- R3.1 **Correctness requirement, not polish.** For the same session and row,
  `rostered_ids` from `_mock_league_context` and from `_mock_context_from_row`
  MUST be equal. If only one is fixed, the pool differs between `POST` and
  `GET`/`/pick` and every recap `consensus_rank` shifts.

*Verified by:* T-295-07.

### R4 — the capability probe counts the same owners (`server.py:11621`)

`_mock_capability` MUST build its owner list with the **same** construction as
R1, so `capability.teams` equals the create route's `settings_echo.teams` for
the same session and league, and neither can refuse a league the other allows.

*Verified by:* T-295-08.

### R5 — `teams` derives from the resolved order (`mock_draft_service.py:989`, `:1007`)

When `build_settings` receives a non-empty explicit `order`, `teams` and the
slot table MUST derive from `len(resolved_order)`, not `len(owners)`. When no
`order` is supplied, `resolved_order` is the shuffled `owners` and the two are
equal by construction, so behaviour is unchanged.

- R5.1 `len(settings["order"]) == settings["teams"]` MUST hold for every
  settings dict `build_settings` returns, in both branches.
- R5.2 `len(settings["slots"]) == settings["rounds"] * settings["teams"]` MUST
  hold.
- R5.3 `resolved_personas` continues to be keyed on `owners`
  (`mock_draft_service.py:1002-1006`). An owner present in `order` but absent
  from `owners` therefore has no persona entry; `advance_cpu` already defaults
  it (`:1191-1192`), and that path MUST NOT be changed.

*Verified by:* **T-295-06 only.** — R5's sole failing-first coverage is a
synthetic `build_settings` unit test, **because no committed corpus reproduces
the divergence**: post-R1, `len(owners) == len(order)` on both `ffv3-predraft`
and `lakeview-complete`, so T-295-03 cannot go red on R5's absence — it verifies
R1. Claiming otherwise (Round 2 J-4) is the same self-deception that shipped
three times in the last batch, and it is corrected here rather than defended.
R5's **live** trigger is the cross-league path in §7.2 (J-7), which is out of
scope; R5 is what makes that path structurally consistent rather than silently
truncated.

### R6 — the caller's team renders as a name, not an id

`order[].owner_username` for the caller's own slots MUST be a human name and
MUST NOT contain the substring `mfl:`.

- R6.1 **No code change is expected.** `_mock_usernames` (`server.py:11488`)
  merges `load_league_members(league_id)` over the session member list, and
  `session_init` writes the caller as the **first** row of
  `all_members_for_db` (`server.py:14853-14860`), so the caller resolves
  through the `stored` branch (`:11524-11529`). This requirement exists so a
  builder verifies it rather than "fixing" it, and so the D-16 no-raw-id
  guarantee is asserted on the newly-visible slot.
- R6.2 When `load_league_members` fails, `owner_username` is `null` and the
  client's existing fallback renders. That is the honest degradation and MUST
  NOT be replaced by an id string.

*Verified by:* T-295-01 (Sleeper), operator Tier-2 check on Dependables (§9).

---

## 4. Requirements — fail loudly

The repair fixes today's leagues. The guards are what make the *next*
divergence a visible refusal instead of a silently CPU-drafted board. **A
silent exclusion is the defect class here** — it is how #291 got the wrong
answer and shipped — and both halves are required.

### R7 — a fourth `start_refusal` rung (`mock_draft_service.py:426-443`)

- R7.1 New module constant `REASON_USER_NOT_IN_DRAFT = "user_not_in_draft"`,
  beside the existing reasons (`:81-86`).
- R7.2 `start_refusal` gains a **keyword-only** parameter with a `None`
  default: `start_refusal(ctx, owners, *, user_owner_id: str | None = None)`.
  The existing two-positional-argument call signature MUST keep working
  unchanged — the route (`server.py:11826`), `capability` (`:446`, body `:475`) and the
  ~8 tests that call it positionally must not need edits to *compile*.
- R7.3 The new rung is checked **last**, after `league_too_small`. Rationale is
  the shipped ladder's own (`:431-435`): a 2-team league should hear its size
  problem first, and `user_not_in_draft` joins `league_too_small` as a state
  the user cannot act on.
- R7.4 The rung fires **only** when `user_owner_id is not None` and
  `str(user_owner_id) not in {str(o) for o in owners or ()}`. Passing `None`
  preserves today's three-rung behaviour exactly.
- R7.5 `capability()` (`:446`) MUST accept and forward the same argument, and
  `mock_draft_route`'s create arm (`server.py:11826`) MUST pass
  `user_owner_id=user_id`. Probe and create must produce the identical
  `reason` for the identical inputs — the G2 invariant.
- R7.6 **The rung is reachable through a shipped route, not just a malformed
  session.** After R1.1 it fires exactly when the session carries no `user_id`
  (`server.py:11782` coerces a missing id to `""`, and R1.1 declines to append
  an empty string). That state is **mintable**: `session_init`'s
  `missing_user_id` guard only fires when a session token is present
  (`server.py:14294` — `if request.headers.get("X-Session-Token") and not
  body.get("user_id")`), while the id itself comes from
  `body.get("user_id", DEMO_USER_ID)` (`:14297`), which returns `""` for a
  **present-but-empty** key. A tokenless `POST /api/session/init` with
  `{"user_id": ""}` therefore mints a session with `user_id == ""`. The rung is
  a real path, not ceremony. *(Citation supplied by the Planner in Round 2 and
  verified here.)*

*Verified by:* T-295-05, T-295-09, T-295-11.

### R8 — an engine backstop in `build_settings`

- R8.1 New exception `class UserNotInDraft(MockDraftError)` with
  `code = REASON_USER_NOT_IN_DRAFT`, beside `NotYourTurn` (`:310`) and
  `PlayerUnavailable` (`:314`).
- R8.2 `build_settings` MUST raise it when the resolved draft gives the user no
  turn — i.e. when `str(user_owner_id)` is in **neither** `resolved_order`
  **nor** the values of `resolved_ownership`.
- R8.3 **The ownership clause is a contract guard, not a reproduced shape.**
  `owner_of` (`:940-943`) lets the traded-pick overlay win over the slot order,
  so ownership alone can put a user on the clock. **No current resolver emits
  an ownership entry for an id absent from `order`** — measured on
  `lakeview-complete`, both difference sets are empty, because
  `_mock_real_draft` builds `order` from round 1's **original** owners across
  all N slots (`server.py:11670-11678`), so every rostered manager is in it by
  construction. But `build_settings` is public and `owner_of` lets ownership
  win, so the invariant is stated where the lookup happens. The check runs
  **after** `resolved_ownership` is built (`:1016`) and before the `return`
  (`:1017`). *(Round 1 justified this clause with the operator's lakeview
  traded pick. That was wrong — being on the clock via an acquired pick and
  being absent from `resolved_order` are different properties. Retracted in
  Round 3; the clause stands on the contract argument alone.)*
- R8.4 This states the precondition R7 structurally cannot see: the user **is**
  in `owners` but the resolved order does not name him. `resolved_order` is
  what `next_pick` actually reads, so the invariant belongs at the point of
  truth. **After R15, the route can no longer produce this state** — R7 refuses
  "not in `owners`" before `build_settings` is called, and R15 degrades "in
  `owners`, absent from an assigned order" upstream of it. R8 therefore guards
  **direct callers** of a public function (tests, the calibration harness,
  future callers), and R7/R8/R15 cover three disjoint states.
- R8.5 The create route (`server.py:11841`) MUST still catch it and return
  `jsonify(mds.empty_payload(mds.REASON_USER_NOT_IN_DRAFT))` — the **same**
  typed-empty body the ladder produces. No 4xx, no 5xx.
  **Why keep a mapping for an unreachable state:** `server.py:2071` registers
  `@app.errorhandler(Exception)`, which converts any unmapped engine exception
  into a generic **500** that nothing asserts on. If a future change removes or
  reorders the R7 rung, or R15's predicate drifts, the state becomes reachable
  again — and without the mapping it surfaces as a silent 500 rather than a
  refusal. Two lines of defence-in-depth against exactly the class of silent
  failure this batch exists to remove. *(Rejected alternative: drop the mapping
  because the ladder makes it unreachable. Rejected because "unreachable today"
  is precisely the assumption that produced this defect.)*

*Verified by:* **T-295-06** (the raise) and **T-295-13** (the route mapping).
Round 2 J-1 is accepted in full: Round 1 claimed T-295-10 covered R8.5, and it
does not — T-295-10 is a mobile JSX check and T-295-06 is a pure unit test, so
**nothing exercised the route's `except` arm.** The requirement most likely to
be half-implemented had the least coverage.

### R15 — degrade, do not refuse, when the caller is in `owners` but absent from an assigned order

> **Numbered out of sequence deliberately.** R9–R14 were already reviewed in
> Round 2; renumbering to insert this would break every cross-reference in the
> scope block and the reconciliation log. The number is a label, not an order.

**Operator/orchestrator ruling (Round 3).** A caller who is in `owners` but not
in the platform's assigned order gets a **working, honestly-labelled mock**, not
a refusal.

- R15.1 `_mock_real_draft` (`server.py:11624-11689`) MUST drop the resolved
  order **and the traded-pick overlay together** — returning
  `{order: None, order_source: "randomized", traded_slots: {}, type: <unchanged>}`
  — when `str(sess["user_id"])` is non-empty and appears in **neither**
  `by_slot.values()` **nor** `out["traded_slots"].values()`.
- R15.2 **The degrade lives in the resolver, not in `build_settings`.** Three
  reasons: (a) the idiom already exists at that site, twice, and is documented —
  `:11655` (non-Sleeper stays randomized) and `:11684-11687` (*"A partial slot
  map is not an order. Drop the overlay with it: a traded pick is meaningless
  without the slots it trades between"*), which is the **same** rule R15 needs;
  (b) dropping an order requires dropping the overlay, and doing that inside
  `build_settings` would silently discard a caller-supplied `ownership`, which
  is surprising for a public pure function; (c) it keeps the session-shaped
  question ("who is the caller?") in the layer that holds the session, and keeps
  `build_settings` a pure function with a strict precondition.
- R15.3 **The two layers MUST use the identical predicate.** R15.1's test
  (`in by_slot.values() or in traded_slots.values()`) and R8.2's test
  (`in resolved_order or in resolved_ownership.values()`) are the same question
  asked of the same data in two representations. If they drift, the resolver
  either degrades cases `build_settings` would have accepted (lossy) or fails to
  degrade one it rejects (a 500). Any change to one MUST change the other.
- R15.4 The degraded mock MUST report `settings_echo.order_source ==
  "randomized"`, which is the shipped disclosure channel (KD-6) — the client
  already renders it. No new field, no notice code, no silent substitution.

**Why this ruling rather than refusal.** The refusal fires on a **real, working
manager**: `ffv3-predraft/…/rosters.json` roster 2 carries
`co_owners: ["867866820202364928"]`, and that id is `lofman` in the same
league's `users.json` — a user who can sign into FTF. `git grep -n "co_owners"
-- backend mobile web extension` returns **fixture hits only**: nothing in the
product reads the field. Every client's roster lookup keys on `owner_id`
(`mobile/src/api/auth.ts:377`), so a co-owner matches no roster, is filtered out
of nobody's `opponent_rosters`, and post-R1 lands in `owners` — but an assigned
`draft_order` names only primary owners, so he is absent from `resolved_order`.
Pre-fix he got a silent CPU-drafted board. Under a refusal he would get a
**permanent, un-actionable wall** — strictly worse, because we would be trading
a silent failure for a loud one he can never clear. Under R15 he gets a mock.

*Verified by:* T-295-14.

### R16 — co-owner support is unimplemented app-wide, and R15 does not implement it

Stated as a finding, not fixed here. Under R15 a signed-in co-owner gets a
working mock that is **one team wider than his league**, and his roster is
represented twice — once by the primary owner's seat and once by his own —
because nothing in the product resolves `co_owners` to a roster. On ffv3 that
means a primary owner sees an 11-team mock and the co-owner sees a 12-team one,
for the same league.

- R16.1 This is a **pre-existing, app-wide** gap (`git grep co_owners` →
  fixtures only), not something R1 or R15 introduces; R15 merely makes it
  visible by giving the co-owner a mock at all.
- R16.2 It MUST NOT be fixed in this batch — resolving co-ownership touches
  `session_init`, every client's roster lookup, the trade engine's member list
  and the League summary's team count. That is a feature.
- R16.3 It MUST be raised as a follow-up item (§7.2) with this citation, so the
  next person to meet it does not re-derive it.

---

---

## 5. Behavioral contract for `user_not_in_draft`

### 5.1 Payload

Both layers emit the shipped typed-empty verbatim
(`mock_draft_service.empty_payload`, `:1348`):

```json
{"schema": 1, "empty": true, "reason": "user_not_in_draft"}
```

HTTP **200**, on `POST /api/mock-draft`. On `GET /api/mock-draft` with no
active row the same string appears inside the capability block:

```json
{"schema": 1, "empty": true, "reason": "no_active_mock",
 "capability": {"can_start": false, "reason": "user_not_in_draft",
                "teams": 10, "min_teams": 4, "rounds_default": 4,
                "rounds_max": 8, "type": null, "order_source": null}}
```

No new key, no new route, no schema bump. `SCHEMA` stays `1`.

### 5.2 Backward compatibility with shipped clients — confirmed

The reason enum is **open by construction** (plan D10), and this is verified in
the shipped 1.12.0 client, not assumed:

- `mobile/src/api/mockDraft.ts:35-39` types it
  `'no_active_mock' | 'class_not_loaded' | 'cpu_model_unvalidated' | (string & {})`
  — an unknown string is a legal value of the type, so no `tsc` break and no
  parse failure.
- `MockDraftScreen.tsx:785-795` (`emptyCopy`) has a `default:` arm returning
  *"This mock draft isn't available right now."*
- `checked()` (`mockDraft.ts:119-122`) rejects only an unknown `schema`, which
  is unchanged.

**A shipped 1.12.0 build therefore degrades gracefully** to generic copy. The
mobile delta below is what turns that generic message into an honest one; it is
optional for correctness and required for quality.

### 5.3 When this fires — the complete list

A refusal whose trigger conditions are not enumerated is a refusal nobody can
review. There are exactly **two** states after R15, and one of them was a
product decision (Round 2 J-6):

| # | State | Reachable? | Handled by |
|---|---|---|---|
| 1 | The session carries **no `user_id`** — mintable via a tokenless `POST /api/session/init` with `{"user_id": ""}` (`server.py:14294`, `:14297`) | **yes**, through a shipped route | R7 rung → typed-empty. This is the entire user-facing surface of the refusal. |
| 2 | The caller **is** in `owners` but absent from an **assigned** `resolved_order` — the co-owner path (`ffv3-predraft` roster 2's `co_owners: ["867866820202364928"]` = `lofman`), a mid-season roster takeover, a commissioner-rebuilt draft | **yes**, on any assigned-order league | **NOT a refusal.** R15 degrades to the randomized branch and labels it. |
| 3 | A direct caller passes `build_settings` an `order`/`ownership` pair that places nobody | not from the route | R8 raise → R8.5 route mapping (defence-in-depth) |

So in practice a user only ever *sees* `user_not_in_draft` in state 1. That is
what sets the copy's register below: there is no action he can take, so the copy
must not invent one.

### 5.4 What the client renders (mobile delta)

| file | change |
|---|---|
| `mobile/src/api/mockDraft.ts:35-39` | add `\| 'user_not_in_draft'` to the union (documentation of a known value; the `(string & {})` arm already admits it) |
| `mobile/src/screens/MockDraftScreen.tsx:785-795` | one `case 'user_not_in_draft':` arm — copy: **"We couldn't find your team in this league's draft, so there's no seat for you to draft from."** |
| `mobile/src/screens/DraftRoomScreen.tsx:298-354` | one `mockBlock` arm keyed on `postRefusal === 'user_not_in_draft'`, testID **`mock-entry.blocked.user_not_in_draft`**, title "Mock draft", body as above, cta **"Your team isn't in this draft"** — matching the five shipped arms exactly |

> **Copy changed in Round 3.** The Round 1 draft read *"Re-sync the league from
> the League tab and try again."* That is an instruction that **cannot
> succeed** — re-syncing reproduces the same owner set every time — and with
> the probe unwired (R9.4) this copy is the *entire* user-facing surface of the
> refusal, so a false remedy is the whole experience. The five shipped arms all
> state a fact and offer no remedy (`startup_draft`: *"This looks like a startup
> draft, not a rookie draft — mocks only cover rookie classes."*); the new arm
> matches that register.

- R9.1 The new arm MUST be placed **after** the `cpu_model_unvalidated` and
  `class_not_loaded` arms and **before** the derived `board.*` arms, so the
  server's own answer keeps winning over anything derived — the ordering the
  block's comment already states (`DraftRoomScreen.tsx:296-297`).
- R9.2 The copy MUST NOT blame the user, MUST NOT expose an id, and **MUST NOT
  prescribe an action that cannot resolve the state** (§5.4's callout).
- R9.3 The new testID MUST pass `mobile/scripts/testid-lint.sh`.
- R9.4 **Known limitation, stated rather than fixed here:** the mobile client
  does not read the `capability` block at all — `git grep capability --
  mobile/src` finds no consumer, and `mobile/src/api/CLAUDE.md:18` still
  describes the probe as a contract gap that W2d in fact closed. So the user
  sees this refusal only *after* POSTing a create. The server-side G2 invariant
  (R7.5) still holds and is still worth having; wiring the probe into the entry
  card is a **separate backlog item** (§7).

*Verified by:* T-295-09, T-295-10.

---

## 6. Requirements — docs

### R10 — `docs/api-reference.md:426` is false and was missed by the batch that claimed to fix exactly this class of staleness

**Own the miss.** The #289–#294 scope block ([`290/scope.md` §2.2](../290-mock-draft-engine/scope.md)) enumerated
**six** stale "the mock is cut / `CPU_MODEL_VALIDATED` is `False`" locations
and corrected all six (`config/features.json:155`,
`docs/config-reference.md:310` and `:566`, `backend/feature_flags.py:473`,
`docs/architecture.md:135`, `docs/glossary.md:30`/`:42`). It missed the
seventh — and the seventh is the **route contract document**, the one a client
author reads. `git grep -n "CPU_MODEL_VALIDATED" -- docs config` today returns
exactly one wrong hit: `docs/api-reference.md:426`.

That is not a trivia point. The batch's method was to grep for the phrasing it
already knew about rather than to enumerate every doc that describes the mock's
*behaviour*; the same method is why the batch verified an engine it never ran
through the route. Both misses have the same shape: **checking the places you
expect to be wrong instead of the places that would be wrong if you were.**

`docs/api-reference.md:426` is **orchestrator-owned — propose, do not apply.**
Exact replacement for the whole blockquote:

> **Status: LIVE, by operator override rather than by the calibration gate
> passing.** `mock_draft_service.CPU_MODEL_VALIDATED` is `True` since
> 2026-08-08 (`6caca35`), when the operator specified CPU reach behaviour
> directly as a product rule (W2e round-tiered caps) and declined further
> validation. The recorded statistical verdict in
> [mock-calibration-2026-08d.md](plans/draft-extensions/mock-calibration-2026-08d.md)
> is **still FAILED** — three of six bars (all three paired-mean; all three KS
> pass) — and `test_w2_16_calibration_gate` asserts that verdict independently,
> so a change that makes the model pass turns the suite red and forces a
> deliberate artifact re-publish. The two facts are kept visible together on
> purpose. With `draft.mock` ON, `POST /api/mock-draft` creates a real mock;
> turning the flag off is the kill switch. **Fixed 2026-08-10 (#295/#296):**
> from `8e146a3` until this batch the create route built its owner set from
> `sess["league"].members`, which by app-wide convention excludes the caller,
> so **no user was ever in his own mock** — every mock returned
> `status: "complete"` on create with zero `by: "user"` picks. See the
> `user_not_in_draft` refusal below.

### R11 — the capability-probe ladder is now four rungs

`docs/api-reference.md:441` (**Capability probe (W2d)**) lists the ladder as
`class_not_loaded → cpu_model_unvalidated → league_too_small`. It MUST become
`class_not_loaded → cpu_model_unvalidated → league_too_small → user_not_in_draft`,
with one sentence: *"`user_not_in_draft` means the session user could not be
placed in the resolved draft at all; after #295 it fires only for a session
carrying no user id, and `build_settings` raises `UserNotInDraft` for the case
the ladder cannot see (the user is an owner but the platform order does not
name him)."*

### R12 — the typed-empty reason list

`docs/api-reference.md:448` enumerates the typed-empty reasons
(`class_not_loaded`, `no_active_mock`, `cpu_model_unvalidated`,
`league_too_small`). Add `user_not_in_draft`.

### R13 — living-memory

- A `GOTCHAS.md` entry: **"`sess["league"].members` never contains the caller"**
  — with the five client filter sites and the two `session_init` sites from
  §2.1, and the note that this is the **second** time the convention has bitten
  us (FB #41 is the first: `backend/tests/test_league_total_teams.py:1-20`
  records the League hero tile reading 11 teams for a 12-team league, on **this
  same ffv3 league**).
- A `DECISIONS.md` entry: **repair + guard together; the leaguemates convention
  is not widened** (§7.1).
- `TEST_LEDGER.md`: the suite result, the Tier-2 live-league result, and the
  sim-gate posture (§9).

Next IDs are `max + 1` — grep first, do not assume.

### R14 — no other doc row changes

Full row-by-row table in [`scope.md` §4](./scope.md#4-docs-scope-mandatory--hld--lld--api).
No schema change, no new route, no new flag, no new analytics event, no new
cross-client constant.

---

## 7. Out of scope — guardrails

Per [`docs/coding-guidelines.md`](../../../coding-guidelines.md) §2 (simplicity
first) and §3 (surgical changes), the following are **explicitly excluded** and
a build agent may not drift into them.

### 7.1 The `league.members`-excludes-the-caller convention itself

**Recommendation, stated as the plan asked, and kept out of this fix.**

I believe the convention is a genuine latent hazard: the field is named
`members` but means *opponents*, and it has now produced two user-visible
defects (FB #41's team count; this one). The honest long-term fix is to **rename
the concept** — `League.members` → `League.leaguemates`, or a derived
`League.all_owner_ids` property that includes the caller — so the next consumer
cannot make the same reading error.

**Blast radius, measured:** `git grep -n "\.members" -- backend/server.py`
returns ~20 references; `TradeService.add_league`, match generation, power
rankings, free-agent computation and the League summary all read it, plus the
five client builders and `session_init`'s two merge sites. That is a repo-wide
refactor with a real regression surface across the trade engine.

**Verdict: not in this fix.** Widening `league.members` to fix a mock-draft bug
inverts the guideline, and FB #41's fix deliberately went the other way —
persist `total_rosters` rather than redefine the member list. Backlog item,
with this PRD's §2.1 table as its evidence.

### 7.2 Also out of scope

| item | why |
|---|---|
| Changing any client's `opponent_rosters` builder | five sites, the field's name and contract both say *opponents*, and every already-installed 1.12.0 build would keep the bug forever. The server fix is one place and repairs shipped clients. |
| Reading owners from `load_league_members()` as the source of truth | `backend/tests/test_league_total_teams.py:8-16` records that this table is a per-login snapshot that both under-counts (ownerless rosters) and over-counts (departed managers, never pruned). Fine as a *name* source (R6), not as the owner set. |
| Deriving owners from the platform draft order | ffv3 — the reported league — has no draft order. This fixes the case that mostly works and not the case that always fails. |
| Giving ownerless rosters a "vacant" CPU seat | operator question O-1 (§10). ffv3's post-fix mock is an 11-team draft in a 12-roster league. |
| `MOCK_MIN_TEAMS` client/server disagreement (client `6`, `MockEntryPanel.tsx:41`; server `4`, `mock_draft_service.py:91`) | already a named backlog item from the #290 batch ([`290/scope.md` §6](../290-mock-draft-engine/scope.md)). Untouched. |
| Wiring the `capability` probe into the mobile entry card | R9.4. Real, worth doing, and a different change. Backlog. |
| Registering the mock analytics event family | [`scope.md` §1](./scope.md#1-analytics-scope). Backlog, and this bug is the strongest argument yet for it. |
| Adding the caller to `_mock_personas` (`server.py:11691`) | after R1 the caller gets the default persona from `build_settings` (`:1002-1006`), and `advance_cpu` returns at his slot without ever reading it. Inferring an outlook for a bot that never runs is dead work. |
| **The cross-league create path** — `_mock_resolve_league` (`server.py:11734-11744`) accepts **any** league with a `get_league_draft_context` row, and that function (`backend/database.py:7458-7476`) selects on `sleeper_league_id` with **no user or session scoping**, while `_mock_league_context` (`:11543-11544`) reads `sess["league"].members` regardless of which league was asked for. So `POST /api/mock-draft {league_id: B}` on a session initialized for league A builds owners from **A** and the order from **B**. | **Named out-of-scope. Decision, with reasons — see below.** |
| **Co-owner resolution** (R16) | `git grep co_owners` → fixtures only. Resolving it touches `session_init`, every client's roster lookup, the trade engine's member list and the League summary's team count. A feature, not a fix. R15 makes it *survivable*, R16 states the residue. |
| Any change to `backend/draft_board_service.py` | the real Draft Room is **not** defective — it derives owners from `rosters[].owner_id` (`:750-752`) and matches `my_picks` on `req.user_id`, which is why the operator sees himself in the room and not in the mock on adjacent screens. It must be byte-identical after this fix. |

### 7.3 The cross-league path (J-7) — decision and reasons

**Decision: named follow-up item, NOT a guard in this fix.** The Planner offered
two options (a one-line `league_id != session league → 404` guard, or a named
out-of-scope item) and asked for an explicit justification either way. I verified
the claim — it is exact, and it is the same class the repo fixed three commits
ago in `5cf81e5` (*"outlook: resolve platform from the requested league_id, not
the session"*). I am still declining to guard it here, on evidence the Planner
did not have:

1. **The guard would be dead code today.** No shipped caller passes a differing
   `league_id`. `DraftRoomScreen.tsx:160-164` reads
   `paramLeagueId ?? sessionLeagueId`, and the only registration that could set
   the param passes none — `TabNav.tsx:496-503` says so explicitly (*"No
   `leagueId`: the room reads the session's active league"*). Every other entry
   point passes nothing, per the screen's own comment at `:152-160`.
2. **The guard would pre-emptively break a documented design.**
   `DraftRoomScreen.tsx:153-155`: *"the seasonal Draft tab's multi-league rule
   lands on a SPECIFIC league's room, **which may not be the session's active
   one** (switching the active league would reset rankings, the deck and the
   format; reading one league's board must not cost that)."* A 404 is the wrong
   answer for that case. The right answer is to resolve owners for the
   **requested** league — which needs a member source, and the only candidate
   (`load_league_members`) is rejected in §7.2 as a source of truth. That is a
   design decision, not a one-liner.
3. **It changes an API contract on the route this fix is already changing**, in
   a regression-critical repair whose blast radius we have worked to keep small.
4. **`GET /api/draft/board` has the identical property** and is explicitly
   untouchable here (§7.2, last row). Fixing one and not the other leaves the
   two draft surfaces disagreeing about which league they serve.

**What I accept from J-7:** it is R5's only **live** trigger, and R5's
justification is amended to say so (§3 R5, "Verified by"). To be precise about
what R5 buys on that path: it makes a cross-league mock **structurally
consistent** — `teams == len(order)`, no silently truncated slot — it does **not**
make it correct, because the owners still come from the wrong league. Correctness
needs the follow-up. Overclaiming here would be the same error as J-4.

**Follow-up item to file:** *"Mock draft + Draft Room: resolve the league from
the request, or reject a non-session league_id — `server.py:11734-11744` vs
`:11543-11544`; precedent `5cf81e5`; blocks the seasonal Draft tab's documented
multi-league rule."*

---

## 8. Test plan

### 8.0 Why the previous suite could not see this — the specific gap

Three named holes, each of which the new tests close. This is not a
post-mortem; it is the design brief for §8.1.

1. **#291's drive was at the ENGINE layer.**
   [`290/plan.md`](../290-mock-draft-engine/plan.md) records driving
   `build_settings(owners=[…'u5'…], user_owner_id='u5')` — hand-passing an id
   that was, *by construction*, one of the owners. `build_settings` is the
   **consumer** of the defect; the producer is `_mock_league_context`. No
   engine drive can see it.
2. **The route fixture reproduces the same coincidence, inverted.**
   `backend/tests/test_mock_draft.py:940-945`:
   ```python
   league = League(league_id=LAKEVIEW_LEAGUE, name="Lakeview", platform="sleeper",
                   members=[LeagueMember(user_id=OPERATOR, username="op", …)])
   sess = {"user_id": OPERATOR, "league": league, …}
   ```
   The session user **is** the league's only member — the exact inverse of the
   production shape, where he is the one id guaranteed absent. Every
   route-level mock test in the file inherits this fixture. It also caps the
   league at one member, so those tests are answered by `league_too_small`
   before order resolution is reached at all.
3. **The engine tests pin the opposite property.** `make_state(…, user=…)`
   (`test_mock_draft.py:101`) is called with `user="zz"`/`"nobody"` —
   deliberately *not* an owner — in a dozen tests, and with `user="b"` (an
   owner) in the rest. The suite proves the engine handles **both** branches
   correctly. It never asserts which one the route produces.

**One sentence:** *every existing test supplies `owners` and `user_owner_id`
from the same hand-built literal; nothing in the suite runs the resolution that
derives them from a session, so the one place they can disagree was never
executed.*

### 8.1 Required tests

Organising principle, binding on the builder: **no test in this set may
hand-pass both `owners` and `user_owner_id`. At least one must derive them the
way the route does.**

**Every row states its red-first condition explicitly, and the column
distinguishes two kinds.** A *pre-fix regression* goes red on `2e0b2c7`. A
*half-implementation tripwire* cannot — the code it exercises does not exist
yet — so its red-first condition is a **named plausible wrong fix**. Conflating
the two is how a test that can never fail gets shipped as evidence.

| id | Level | Test | Red-first condition — what fails, on what code |
|---|---|---|---|
| **T-295-01** | **Route, end-to-end, real corpus — this is the test** | Session built in the **production shape**: `members` = the owned rosters of `ffv3-predraft/league/1312140920132497408/rosters.json` **minus** `OPERATOR`; `sess["user_id"] = OPERATOR`; `sess["user_roster"]` populated. `DraftReplay("ffv3-predraft")` installed (`backend/tests/support/draft_replay.py:77`). `POST /api/mock-draft {league_id, rounds: 4}`. Assert: `settings_echo.teams == 11`; `OPERATOR` appears in `order[].owner_user_id`; `status == "active"` (**never** `"complete"` on create); `on_the_clock["is_user"] is True` at his slot; then `POST /api/mock-draft/pick` succeeds and the pick records `by: "user"` and appears in `my_picks`. **R6 clause — and the seeding it requires (J-3):** the test MUST monkeypatch `server.load_league_members` to return the shape `session_init` writes (`server.py:14853-14860`) — the caller's row **first** (`{"user_id": OPERATOR, "username": …, "display_name": …, "player_ids": …}`), then the opponents — and only then assert his `order[]` rows carry a non-null `owner_username` containing no `mfl:`. Without that seeding the assertion **fails on a correct implementation**: against a fixture league id `load_league_members` returns `[]`, so the caller is in neither `_mock_usernames` loop (`server.py:11506-11530`) and `state_payload` emits `owner_username: None` — and the builder's nearest "fix" is to edit `_mock_usernames`, which R6.1 forbids. Monkeypatch rather than a real DB row: the #289–#294 batch was burned by two mock tests accumulating rows in the persistent SQLite DB. A self-clearing seeded row is an acceptable alternative. **R6.2 negative half:** with `load_league_members` raising, `owner_username` is `None`, the response is still `200`, and no id string is substituted (`_mock_usernames`'s `except` at `:11507-11512` is the documented degradation). | **pre-fix:** `teams: 10`, `status: "complete"`, `on_the_clock: None`, `my_picks: []`, operator absent from `order[]`. **R6 clause tripwire:** delete `_mock_usernames`'s second loop (`:11524-11529`) — a plausible "simplification" — and `owner_username` goes `None`. |
| **T-295-02** | Fixture contract | The route tests' session league MUST NOT contain `sess["user_id"]` among `league.members`, and MUST carry ≥ `MOCK_MIN_TEAMS` other members. Implemented as a rewritten shared `session` fixture (`test_mock_draft.py:936-945`) **plus a standing assertion** so it cannot drift back. **The rewrite has exactly two casualties and BOTH repairs are specified — a builder must not improvise them (J-2):** **(a)** `test_w2_20_g2_the_capability_probe_answers_without_starting_a_mock` (`:1232-1249`) **fails loudly** — `can_start` (`:1242`) becomes `True` and `reason` (`:1247`) becomes `None` on a ≥4-owner league. Flip those two assertions **and relocate the route-level `league_too_small` coverage to a new dedicated small-league fixture (T-295-15) — never delete it.** Narrowing the Planner's framing: the *service*-level rung coverage is already fixture-independent (`test_w2_20_g2_a_two_team_league_is_refused_as_too_small`, `:1269-1285`, builds owners via `make_ctx`), so only the route-level assertion needs a new home. **(b)** `test_the_abort_criterion_is_enforced_at_the_route` (`:1036-1051`) **keeps passing while its stated premise becomes false** — its comment at `:1048` reads *"this fixture league is under MOCK_MIN_TEAMS"*, which the rewrite falsifies, yet its two assertions (`reason != "cpu_model_unvalidated"`, `schema == 1`) are satisfied by a successfully created mock. Repair by **strengthening**: keep the `reason` assertion, add `body.get("empty") is not True` and `body["mock_id"] is not None` (the create now genuinely succeeds), and rewrite the comment to the new premise. | **pre-fix:** the shipped fixture violates both clauses. **Casualty (b) is the dangerous one and has no red-first state at all** — it passes before and after; it is caught only by the §8.2 status-diff rule. |
| **T-295-03** | Route, real corpus | Same construction against `lakeview-complete` (assigned `draft_order`, 55 traded picks, 12 owned rosters): `settings_echo.teams == 12`; `len(order[]) == 48`; 12 distinct `original_user_id`s; `OPERATOR` present; `on_the_clock` reaches him. **Derive his expected first pick from the fixture, do not hard-code blindly** — `draft_order` puts him at slot 6, the round-1 traded-pick overlay moves his turn to **pick 10** (his own 1.06 went to roster 7; he holds roster 4's slot-10 pick). Assert that number as a tripwire with the derivation in a comment. | `teams: 11`, 44 order rows, 11 owners, operator absent |
| **T-295-04** | Route | Non-Sleeper session (`get_league_draft_context → platform: "mfl"`): the randomized branch still contains the user; `order_source == "randomized"`; `on_the_clock["is_user"]` reachable. | user absent — the deterministic 100 % Dependables failure |
| **T-295-05** | Service | `start_refusal(ctx, owners, user_owner_id=<not in owners>) == REASON_USER_NOT_IN_DRAFT`; `capability(ctx, owners, user_owner_id=<same>)["reason"]` is the **same string** and `can_start is False`; the three existing rungs still outrank it (a class-less ctx returns `class_not_loaded`, a 2-owner league returns `league_too_small`); and `start_refusal(ctx, owners)` with two positional args is byte-identical to today. | R7.2/R7.3/R7.5 |
| **T-295-06** | Service | `build_settings(ctx, owners=[a,b,c,d], user_owner_id="zz", order=[a,b,c,d])` raises `UserNotInDraft`; the same call with `ownership={"3": "zz"}` (or the equivalent `traded_slots`) **does not raise** — labelled in the test as a **contract** test, not a regression test: no current resolver emits that shape (R8.3). And `build_settings(..., order=[a,b,c,d,e], owners=[a,b,c,d])` returns `teams == 5` with `len(slots) == rounds * 5` — **this is R5's only failing-first coverage** (J-4). | **half-implementation tripwire.** R5 arm: omit R5 and `teams` is 4 with 4-wide slots while `order` is 5 — red. R8 arm: omit the raise and the call returns a settings dict that places nobody — red. |
| **T-295-07** | Route | For the same session and mock row, `rostered_ids` from `_mock_league_context` and from `_mock_context_from_row` are **equal**, and both contain every id in `sess["user_roster"]`. Additionally: a rookie on the caller's roster does not appear in `undrafted[]`. | both omit the caller; only-one-fixed silently shifts every recap rank |
| **T-295-08** | Route | `_mock_capability(...)["teams"]` equals the create route's `settings_echo.teams` for the same session; a session whose league has 3 other members (4 owners with the caller) reports `can_start: true`, not `league_too_small`. | probe reports 3 → `league_too_small`; create would report 3 too, so the off-by-one is uniform — this test pins that they stay uniform *and* correct |
| **T-295-09** | Route → client contract | `POST` on a session with `user_id == ""` (minted the shipped way — tokenless `session_init` with `{"user_id": ""}`, `server.py:14294`/`:14297`) returns `200 {"schema": 1, "empty": true, "reason": "user_not_in_draft"}` and **no other keys**. | **half-implementation tripwire.** Implement R1 without R1.1 and `""` becomes a phantom owner: the create succeeds, `teams` is one too many, and the assertion on the typed-empty goes red. Implement R1.1 without R7 and the create still succeeds with the user unplaceable — also red. |
| **T-295-10** | Mobile (node check, `mobile/tests/check-*.js` style) | `MockEmptyReason` admits `'user_not_in_draft'`; `emptyCopy('user_not_in_draft')` is not the `default:` string; `DraftRoomScreen`'s `mockBlock` has an arm with testID `mock-entry.blocked.user_not_in_draft` positioned after the two `postRefusal` arms. Assertion must be constructed to **fail on the current tree first** — the #289–#294 batch found a check that passed because the JSX comment contained the grepped string. | R9 |
| **T-295-11** | Route | The owner list returned by `_mock_league_context` contains no duplicates when `sess["user_id"]` is *also* present in `league.members` (forward-compat, R1.2), and does **not** contain `""` when `sess["user_id"]` is missing (R1.1). | R1.1, R1.2 |
| **T-295-12** | Maestro `d3` | On the mock board, **before any tap**, `assertVisible` the on-the-clock card naming the user's own team. | #291's flow asserted the *affordance* was visible; it never asserted the user was ever **on the clock**. That assertion is the UI-level statement of this bug. **Blocked** — see §8.3. |
| **T-295-13** | **Route — the exception mapping (J-1)** | Monkeypatch `server.mds.build_settings` to raise `mds.UserNotInDraft("x")`, then `POST /api/mock-draft` on the production-shape session. Assert exactly `200 {"schema": 1, "empty": true, "reason": "user_not_in_draft"}` and no other keys. **Mechanism deliberately changed from the Planner's proposal** (which monkeypatched `_mock_real_draft` to return an assigned order missing the caller): after R15 that input **degrades instead of raising**, so the proposed test would silently exercise the degrade path and assert the wrong thing. Patching `build_settings` tests R8.5 and nothing else, and cannot be defeated by R15. | **half-implementation tripwire, and this is the whole point.** Implement R8.1/R8.2 (the raise) and omit R8.5 (the route `try/except`) → the `@app.errorhandler(Exception)` at `server.py:2071-2077` returns a generic **500**. Red must be a 500, not a wrong `reason` string. Without this test, that half-implementation is invisible. |
| **T-295-14** | **Route — the co-owner degrade (J-6, R15)** | Production-shape session on `lakeview-complete` (assigned order) where `sess["user_id"]` is a **co-owner** id — one that appears in no roster's `owner_id`, mirroring `ffv3-predraft` roster 2's `co_owners: ["867866820202364928"]`. Assert: `200`, **not** a typed-empty; `settings_echo.order_source == "randomized"` (R15.4); the co-owner appears in `order[].owner_user_id`; `on_the_clock["is_user"]` becomes `True` within the mock; `settings_echo.teams == len(owners)`; and `settings_echo` carries **no** traded-pick ownership (R15.1 drops the overlay with the order). Add the R15.3 assertion: the resolver's degrade predicate and `build_settings`'s raise predicate agree — the same session that degrades here does **not** raise when its resolved inputs are passed to `build_settings` directly. | **half-implementation tripwire.** Implement R8 without R15 → the route returns `200 {"empty": true, "reason": "user_not_in_draft"}` — a wall for a working manager. Implement R15 but drop only the order and keep `traded_slots` → the overlay assertion goes red (a traded pick without its slots). |
| **T-295-15** | Route — relocated `league_too_small` (J-2a) | A **dedicated small-league fixture**: session whose `league.members` holds 2 leaguemates (3 owners with the caller, below `MOCK_MIN_TEAMS = 4`). Assert `GET` → `capability.can_start is False` and `capability.reason == REASON_LEAGUE_TOO_SMALL`, and `POST` → the same typed-empty reason. This is the route-level coverage that T-295-02's fixture rewrite would otherwise **delete**. | **pre-fix:** passes today via the 1-member fixture; after the rewrite it is the only route-level home for this rung. Red-first is demonstrated by deleting the new fixture and watching the rung lose route coverage entirely — i.e. the test's absence is the failure it guards against. |

### 8.2 Failing-first is mandatory

Every behavioural test above MUST be demonstrated red before the fix and green
after, with both outputs recorded in `TEST_LEDGER.md`. The #289–#294 batch found
**three separate lanes** where a test passed on the very defect it named; a test
that has never been seen to fail is not evidence here.

**Two kinds of red, and the builder must state which each one is.** A
*pre-fix regression* (T-295-01, -02, -03, -04, -07, -08) goes red on `2e0b2c7`.
A *half-implementation tripwire* (T-295-05, -06, -09, -13, -14) cannot — the
code it exercises does not exist on `2e0b2c7` — so its red-first evidence is the
**named plausible wrong fix** in its table row, built deliberately and shown
red. "Could not be demonstrated red because the feature is new" is not
acceptable; every tripwire above names the specific half-implementation to
construct.

**Three rules added in Round 3, each from a defect found in review:**

- **R-8.2a — a test whose comment states a premise the rewritten fixture no
  longer satisfies must be re-pointed or rewritten, never left passing.**
  `test_the_abort_criterion_is_enforced_at_the_route` (`:1048`) is the live
  example: it survives T-295-02 while its stated premise silently becomes false.
  This is the §8.0 disease arriving through the fix's own largest diff.
- **R-8.2b — the fixture rewrite lands as its own commit, and the full suite is
  run immediately before and after it, with every test whose status changes
  enumerated in `TEST_LEDGER.md`.** A status **diff** is the only reliable
  detector of a test that breaks by passing; no assertion can catch it, because
  by construction there is nothing to assert on.
- **R-8.2c — no route-level coverage may be deleted to make a rewritten fixture
  pass.** Coverage that the new fixture invalidates is **relocated** to a
  fixture that still satisfies its premise (T-295-15), and the relocation is
  named in the commit message.

Also required by the gates:

- `bash mobile/scripts/testid-lint.sh` — exit 0 (CI job `maestro-testid-lint`).
- `cd mobile && npm run test:mock-lifecycle` — not in CI, run by hand.
- `npx tsc --noEmit` — real `npm ci` **in this worktree**; never symlink the
  main checkout's `node_modules`.
- Full pytest suite green (baseline to re-measure at build time; the last
  recorded figure is 2326 passed / 1 skipped).

### 8.3 Maestro `d3` is still blocked, and this fix does not unblock it

**Stated honestly rather than optimistically.** `d3-mock-draft-loop.yaml` exists
and already carries the blocking precondition in its own header (lines 24–32):
`backend/tests/fixtures/profiles/standard.json` declares exactly one league
(`990000000000000001`), while `d1`, `d2` and `d3` all target
`1312140920132497408`, which appears in no profile.

The #289–#294 ledger entry (2026-08-10) records that this was investigated and
**"the build agent's 'one `leagues[]` entry' estimate was checked and does not
hold; this is real seeder work."** I agree, and can size why: the profile
seeder (`backend/tests/fixtures/seed_ui_test_db.py:383-399`) synthesises leagues
with generated members and rosters, whereas ffv3 is a recorded Sleeper corpus
that the Draft Room reaches through the `FTF_SLEEPER_FIXTURES_DIR` seam
(`seed_ui_test_db.py:1048`). Making d3 runnable means either merging the
recorded corpus into a profile's fixture dir (the step the flow headers assume
and that is unimplemented) or giving the synthetic profile league a synthetic
Sleeper draft object. Either is its own piece of work with its own tests, and
it is **not** in this fix's blast radius.

**Consequence, which the operator must see:** the Tier-1 gate's "feature's own
flow" cannot run, for the second batch running, on the same feature. The
Tier-2 live-league verification in §9 is therefore **load-bearing evidence, not
a nice-to-have.** The T-295-12 assertion is still authored into `d3` in this
batch so it is ready the moment the profile work lands.

---

## 9. Done criteria

The fix is **not done** when the tests pass.

1. All of §8.1 green, each demonstrated red first (§8.2).
2. `testid-lint.sh`, `tsc --noEmit`, `npm run test:mock-lifecycle` and the full
   pytest suite green.
3. `d1-draft-room-complete.yaml` / `d2-draft-room-order-not-set.yaml` remain the
   no-regression check for the shared `UndraftedRowView`; the real Draft Room's
   `GET /api/draft/board` payload for ffv3 MUST be **byte-identical** before and
   after (§7.2, last row).
4. **Sign-off condition — the operator has started a mock on ffv3 AND on
   Dependables (MFL 62846) and taken a pick in each.** This is a hard
   done-criterion, carried from [`plan.md`](./plan.md) §9. Specifically, on each:
   - the on-the-clock card names **his own team**, by name, at his slot;
   - the order rail lists every team **including him** (ffv3: 11; Dependables:
     its full franchise count);
   - the board does **not** arrive `complete`;
   - a pick lands, records `by: "user"`, leaves the undrafted list, and appears
     in the recap's "My picks";
   - on Dependables, no rendered string contains `mfl:` (D-16).

   **The report must be falsifiable, not a thumbs-up** (Round 2 K-6). Because
   `d3` cannot run (§8.3), this is the batch's only end-to-end evidence, so the
   operator reports **two numbers per league** — the **team count on the order
   rail** and the **pick number of his first turn** — not "it worked". A number
   can be checked against the fixture and can be wrong; an approval cannot.
   Expected: ffv3 **11 teams** (12 rosters, one ownerless — see O-1), first turn
   at whatever slot the shuffle gave him; Dependables, its full franchise count.
5. A third Sleeper league with an **assigned** draft order, if the operator
   still holds one (Lakeview): the order rail shows all 12 teams and the team
   that used to occupy draft slot 12 is present.
6. Negative control: the **real** Draft Room on ffv3, opened immediately before
   and after, is unchanged.
7. `TEST_LEDGER.md`, `GOTCHAS.md`, `DECISIONS.md`, `CHANGELOG.md` written; the
   §6 doc corrections applied by the orchestrator.

That is the evidence standard #291 did not meet, and the reason we are here.

---

## 10. Open items for the operator

**O-1 — ffv3's ownerless roster.** Roster 6 has `owner_id: null`. Post-fix its
mock is an **11-team** draft in a 12-roster league. **Recommendation: leave it
at 11** and let `order_source: "randomized"` carry the disclosure — inventing a
manager is worse than omitting an empty chair, and the alternative (a "vacant"
CPU seat) needs a name, a persona and a rendering decision it does not have
today. Flagged because it is a visible number on the operator's own league.

**O-2 — accept the analytics waiver?** No `mock_*` event exists in
`backend/analytics_taxonomy.py` (verified: zero hits). This fix adds none, for
the same reason the #290 batch's waiver was accepted. **Recommendation: accept,
and note that this bug is the strongest argument yet for the backlogged mock
funnel** — a 100 % silent failure ran for two days and the only signal we ever
got was two typed feedback reports. Details in
[`scope.md` §1](./scope.md#1-analytics-scope).

**O-3 — accept that `d3` stays blocked (§8.3), making the live-league checks in
§9.4 the batch's real gate?** **Recommendation: accept, and schedule the
profile-seeder work as its own item.** The alternative is to widen this fix into
QA-harness work, which delays a 100 %-broken feature's repair. If you would
rather block the ship on `d3`, say so now — it changes the batch's shape.

**O-4 — is `docs/api-reference.md:426` (R10) mine to propose only, or should the
build agent apply it?** It is orchestrator-owned by the batch convention, so
this PRD **proposes exact replacement text and does not apply it**. Confirm the
handoff so it does not get missed a second time.
