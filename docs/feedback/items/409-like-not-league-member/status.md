# FB-409 — "error when liking trades that a user isn't in this league"

**Status:** open · 2026-08-30 · triage only, no branch (fix not yet built)

- **Reporter:** mattmurf77, 2026-08-30T13:17, app v1.16.12 (EAS build 140), screen `TradesHome`
- **Operator note (decisive):** *"It's new behavior I started noticing yesterday"* → 2026-08-29
- **Verdict:** **(b) PRE-EXISTING** — a backend defect that has been in `main` since
  **2026-08-22 (`80dee425`, #384 W6-A / D-152)**. **Not** a regression from today's
  ship (`287aed09`, #406 + #407). It became *reachable on the front door* on
  2026-08-28/29, which is exactly when the operator started seeing it.
- **Severity:** the ✓ "queue this trade for the other manager" control has **never
  worked in production, for any user, in any league.** 100% refusal rate.
- **Recommendation:** **HOTFIX — ship ahead of the cosmetic #410/#412 work.** Backend
  only, no client build, no TestFlight round trip (Render auto-deploy fixes every
  fielded build at once).

---

## 1. What the tester actually saw

The ✓ cell returns the server's `not_league_member` refusal, which
`mobile/src/utils/queueCalcTrade.ts:43-44` renders as:

> `@<partner> isn't in this league.`

That is the string in the report ("liking trades that a user isn't in this league").
It is a `200 {queued: false, reason: "not_league_member"}`, not a crash — the toast
is a warn, and **nothing is recorded**: no `trade_decisions` row, no Elo, no
likes-you mirror.

## 2. Root cause — the caller-exclusion trap, 4th bite

`POST /api/trades/queue` resolves BOTH sides of the trade out of the session
league's member list:

```
backend/server.py:13313   members_by_id = {m.user_id: m for m in g_league.members}
backend/server.py:13314   caller_member = members_by_id.get(caller_league_id)
backend/server.py:13315   opponent      = members_by_id.get(opponent_user_id)
```

`sess["league"].members` is **caller-excluded by app-wide convention.** Proof, at
both ends:

- Server, `/api/session/init`: members are built from the client's
  `opponent_rosters` (`backend/server.py:18928-18944`), and the DB-member merge
  explicitly refuses to re-add the caller —
  `existing_member_ids = {m.user_id for m in members} | {user_id, league_user_id}`
  (`backend/server.py:18952`).
- Client: `buildSleeperRosterPayload` filters the user's own roster out by
  `roster_id` before posting (`mobile/src/api/auth.ts:366-367`); ESPN/MFL do the
  same by `user_id` (`mobile/src/api/espn.ts:232-233`,
  `mobile/src/api/platformLink.ts:279-280`).
- The convention is documented at `backend/server.py:15168-15172` and
  `backend/trade_breaker.py:326`.

So in production `caller_member` is **always `None`**, and the very first branch of
the mirror predicate fires:

```
backend/server.py:13139   if caller_member is None:
                              return "not_league_member", "caller is not a member of this league"
```

`_inject_owned_picks` does not help: it rewrites existing members' rosters in place
and returns the caller's pick-injected roster as a *separate* value
(`backend/server.py:11500-11504`) — which the queue route **discards** into `_ur`
(`backend/server.py:13300`). Nothing ever creates a member object for the caller.

### Why the tests are green

`backend/tests/test_calc_trade_queue.py:98-105` builds its fixture league with
**`ME` inside `members`** — a shape production never produces. Every refusal test,
the happy path, and the idempotency test run against that impossible session.
`test_cannot_queue_a_trade_with_yourself` (`:315`) can only reach its branch because
of it. This is the same fixture-shape failure the mock-draft defect had
(`docs/feedback/items/295-mock-user-not-in-draft/hld-2026-08-13.md:433-445`).

### Runtime proof (executed 2026-08-30, this checkout, `bd83fe94`)

The shipped route was driven twice through the Flask test client with identical
bodies, changing only whether the caller is in `league.members`:

```
TEST-SHAPE (caller IN members):  200 {'queued': True,  'trade_id': 'calcq_e86045a71bc43bb7'}
PROD-SHAPE (caller EXCLUDED):    200 {'queued': False, 'reason': 'not_league_member',
                                      'detail': 'caller is not a member of this league'}
```

No files were written for this; it was an inline harness copied from
`test_calc_trade_queue.py` with `ME` dropped from `members`.

## 3. Why it surfaced on 2026-08-29, not 2026-08-22

The defect is the same age as the ✓ cell; its **reachability** changed twice this week.

| Date | Change | Effect on the ✓ |
|---|---|---|
| 2026-08-22 | `80dee425` — #384 ✓ cell ships, `calc.merged_layout` LIT | ✓ exists only on the *pushed* In-league calculator page. Rarely tapped. |
| 2026-08-28 | `380126a3` — `calc.inline_home` LIT | The calculator canvas — and its ✓ — becomes the **guided landing itself**, on TradesHome. |
| 2026-08-28 | `a9d96435` — #402/#403 shop window LIT | A second ✓ surface (`ShopOffersBody.tsx:701`), same helper, same refusal. |
| 2026-08-29 | `21989cda` — v1.16.11 / build 138: canvas-results browse + `nav.trades_landing` | Trades is the **front door**; every found idea is browsed *in the canvas* with the ✓ as its accept control. |
| 2026-08-30 | `287aed09` — #406/#407 (v1.16.12 / build 140) | **No effect on this path** — see §4. |

That table is the operator's "started noticing yesterday", exactly.

## 4. Today's ship (#406/#407) is cleared

Both changes were audited against the like path and neither can send a null, stale,
or wrong `opponent_user_id`:

- **#407 `opponentChosenRef`** (`InLeagueCalculator.tsx:364`, `:1288`) gates only the
  **Find-a-Trade** payload's `opponent`. The ✓ cell's payload is a separate literal
  at `:1337-1341` and reads `opponent.user_id` unconditionally.
- **#406 `partnerAny`** (`:375`) sets `opponentId` to `null` — but the ✓ is then
  **disabled**: `disabled={!onLikeTrade || !bothSides || !opponent || queueing}`
  (`:1331`), with the same guard repeated inside `onPress` (`:1333`). Under "Anyone"
  the ✓ cannot fire at all, so it cannot send a null opponent.
- **#406 `seededPrefill`** (`:289`, `:364`, `TradeBuildCanvas.tsx:184`) only flips
  *chosen-ness*; the browse seed still sets `opponentId` from
  `rawTopCard.opponent_user_id` (`TradesScreen.tsx:5818`), a real league member id.
- A partner change wiping `receiveIds` leaves `bothSides` false ⇒ ✓ disabled.

The three surviving ✓ paths (inline canvas `TradesScreen.tsx:3083`, browse session
via the same handler at `:7438-7440`, shop tiles `ShopOffersBody.tsx:701`) all call
the one helper `utils/queueCalcTrade.ts:52` → `POST /api/trades/queue`, so all three
fail identically. The deck swipe-like (`POST /api/trades/swipe`) is a different route
and is **not** affected — `not_league_member` exists only on the queue route.

## 5. Proposed minimal fix (backend only, ~10 lines)

Synthesize the caller's `LeagueMember` from session state when — as always in
production — they are absent from `g_league.members`. This is the #295 pattern
(`_mock_owner_ids` / `_mock_rosters`, `backend/server.py:15167-15200`): session
first, members list for everyone else.

In `queue_trade_for_opponent` (`backend/server.py:13290-13315`):

1. Keep the caller's pick-injected roster instead of discarding it — capture the
   second return value of `_inject_owned_picks` (currently `_ur` at `:13300`) into a
   `caller_roster`, initialised to `list(sess.get("user_roster") or [])` so the
   no-picks and exception paths still have a value.
2. Fall back to a synthetic member:

```python
caller_member = members_by_id.get(caller_league_id) or LeagueMember(
    user_id     = caller_league_id,
    username    = str(sess.get("username") or caller_league_id),
    roster      = list(caller_roster),
    elo_ratings = {},
)
```

`LeagueMember` needs exactly `user_id / username / roster / elo_ratings`
(`backend/trade_service.py`, `has_rankings` defaults False). The route reads only
`caller_member.roster` (give-side actionability, `:13135`) and
`caller_member.user_id` (the self-trade guard, `:13142`), so nothing else changes.
`elo_ratings` is unread here — the D-096 ladder is measured from the *opponent's*
side under their pinned stud-tax mode (`:13153-13176`).

**Do not** "fix" this by adding the caller to `sess["league"].members` — that list is
consumed by the trade engine, the mock draft, power rankings and the likes-you
injector, all of which assume the exclusion.

### Test change that must ride with it

`backend/tests/test_calc_trade_queue.py` must gain a **production-shape** fixture
(caller NOT in `members`) and run the happy path + `assets_not_on_roster` against it.
Without that, the same class of defect re-lands silently. Keep the existing
fixture too — a session that *did* carry the caller must still work.

### Verification (D-056 posture)

- `pytest backend/tests/test_calc_trade_queue.py` (new prod-shape cases red before
  the fix, green after — sabotage-prove the fixture).
- Code-walk proof: no client change, so no `tsc`/testid exposure; the mobile
  structural suites (`check-calc-merged-behavior.js`, `check-any-partner.js`,
  `check-canvas-results.js`, `check-shop-deck.js`) are untouched.
- Manual TestFlight check on the CURRENT build (140) after the Render deploy —
  no app update needed: TradesHome → build any two-sided trade with a real partner
  → ✓ → expect *"Queued for @X — it'll show in their suggestions."*

## 6. Blast radius of the defect while unfixed

- Every ✓ queue on TradesHome, the shop window, and the pushed calculator refuses.
- **The likes-you mirror surface has been starved**: `_inject_likes_you_cards_impl`
  reads exactly the rows this route was supposed to write, so no calculator-built
  proposal has ever reached a counterparty's deck.
- Analytics: every `calc_trade_queued` since 2026-08-22 carries
  `{queued: false, reason: "not_league_member"}` — any read of that event as a
  product signal (partner-not-in-league rate) is measuring this bug.
- G22 activation moments (`recordCanvasQueueLike`, `TradesScreen.tsx:3096`) never
  fire, so the canvas host has recorded **no** like moments at all.

## 7. Housekeeping notes for whoever ships this

- `docs/feedback/items/INDEX.md` has no rows past #286 (documented drift); this
  folder was not added to it — do so if the index is regenerated.
- Worth a `living-memory/GOTCHAS.md` entry: the caller-excluded `league.members`
  convention has now bitten **four** times (FB #41 → #291 → #295/#296/#305 → #409),
  and three of the four were hidden by a fixture that put the caller in `members`.
  See `.claude/skills/feedback/lessons.md:155-158`.

---

# Build report — 2026-08-30

**Status:** BUILT, NOT COMMITTED. Working tree left for orchestrator review.
**Base:** `bd83fe94` on `claude/fb-410-412-trade-card-polish` (tree clean at start apart from this folder).
**Scope block:** [`scope.md`](scope.md) — full gates, no express lane.

## What changed

| File | +/- | What |
|---|---:|---|
| `backend/server.py` | +19 / −2 | The fix, in `queue_trade_for_opponent` |
| `backend/tests/test_calc_trade_queue.py` | +143 / −8 | Production-shape fixture + 7 cases |
| `living-memory/GOTCHAS.md` | +12 / −0 | G-063 — the caller-exclusion trap, 4th bite |
| `docs/feedback/items/409-like-not-league-member/scope.md` | new | Scope block |
| `docs/feedback/items/409-like-not-league-member/status.md` | this section | Build report |

Nothing else touched. **No `mobile/` files** (see § Follow-up).

## The fix

Exactly as specced in §5, two hunks in `queue_trade_for_opponent`:

1. `caller_roster` is initialised to `list(sess.get("user_roster") or [])` **before** the pick-injection
   block and receives `_inject_owned_picks`'s second return value in place of the discarded `_ur`, so it
   is correct whether the block runs, is skipped, or raises (the tuple-unpack only rebinds on a clean
   return, and `_inject_owned_picks` rebinds `user_roster` locally rather than mutating the list passed in).
2. `caller_member` falls back to a synthesized `LeagueMember` when the members lookup misses.

The synthesized member is **local to the route**. `g_league.members` is never appended to — asserted by
`test_prod_shape_does_not_mutate_league_members`.

### Fields the route actually consumes from `caller_member` — confirmed, not assumed

`git grep -n "caller_member" backend/` returns six hits; after the two construction/pass sites, the
consumers are exactly **three**, all inside `_calc_queue_mirror_reason`, which has **one** caller
(`:13317`):

| Site | Read | Purpose |
|---|---|---|
| `backend/server.py:13138` | identity (`is None`) | membership branch |
| `backend/server.py:13142` | `.user_id` | self-trade guard |
| `backend/server.py:13151` | `.roster` | give-side actionability |

`.username` is **not** read for the caller anywhere (only `opponent.username` is, at `:13157` and
`:13353`), and `.elo_ratings` / `.has_rankings` are unread on this path — the D-096 ladder is measured
from the opponent's side under their pinned stud-tax mode (`:13153-13176`). `username` is still supplied
because `LeagueMember` is a dataclass whose first four fields have no defaults. **The diagnosis's field
list was correct; the object was not widened.**

## Verification

### Targeted — `pytest backend/tests/test_calc_trade_queue.py -q`

```
.................................                                        [100%]
33 passed in 3.05s
```

26 before, 33 after (+7).

### Sabotage proof (this is the evidence that counts)

Sabotage: revert **only** the synthesized fallback back to `caller_member = members_by_id.get(caller_league_id)`,
leaving everything else — including `caller_roster` — in place.

**RED:**

```
E       AssertionError: {'detail': 'caller is not a member of this league', 'queued': False, 'reason': 'not_league_member'}
E       assert 'not_league_member' == 'assets_not_on_roster'

=========================== short test summary info ============================
FAILED backend/tests/test_calc_trade_queue.py::test_prod_shape_queue_succeeds
FAILED backend/tests/test_calc_trade_queue.py::test_prod_shape_does_not_mutate_league_members
FAILED backend/tests/test_calc_trade_queue.py::test_prod_shape_give_side_still_checked_against_my_roster
FAILED backend/tests/test_calc_trade_queue.py::test_prod_shape_receive_side_still_checked_against_their_roster
FAILED backend/tests/test_calc_trade_queue.py::test_prod_shape_like_reaches_the_opponents_deck
5 failed, 28 passed in 3.23s
```

Every failure reports the production symptom verbatim: `not_league_member` /
*"caller is not a member of this league"*. The 2 new cases that stay green under sabotage
(`…_cannot_queue_a_trade_with_yourself`, `…_unknown_opponent_still_refused`) are the ones that
*expect* `not_league_member`; they exist to prove the fix did not over-permit, so green there is
the correct result. **Every case in the original 26 also stays green under sabotage — which is the
whole point of this report.**

**GREEN on restore:** `33 passed in 3.05s`.

### Full suite — `pytest backend/tests -q`

```
4478 passed, 1 skipped in 360.66s (0:06:00)
```

Baseline with the change stashed (`git stash push -- backend/server.py backend/tests/test_calc_trade_queue.py`):

```
4471 passed, 1 skipped in 354.00s (0:05:53)
```

**+7 passed, 0 failed, delta exactly accounted for.**

### One flake seen and run down — NOT this change, but worth knowing

The **first** full run with the change red-flagged
`test_rookie_scope.py::test_m2_11c_qc_branch_is_skipped_under_scope` with a 401 `session_expired`.
It did not reproduce on the second full run, passes 34/34 in isolation, and passes when run
immediately after `test_calc_trade_queue.py`. **Mechanism found:** `server._cleanup_loop`
(`backend/server.py:2688-2704`) is a background thread that `time.sleep(300)`s and then evicts every
entry in `server._sessions` whose `last_active` is older than `time.time() - 4*3600`. **Every session
fixture in the repo sets `"last_active": 0.0`**, so at roughly the 5-minute mark of any full-suite run
the cleanup tick wipes the entire in-memory session store, and whichever session-holding test is
executing at that instant fails. Full runs here land at 5:53–6:00, so the tick fires mid-suite every
time; which test it lands on is a race. The captured log on the failure is the smoking gun — it shows
the tick's very next step (`persisted-session purge failed: no such table: sessions`) logged inside
that test.

This is latent and pre-existing, affects the whole suite rather than any one file, and is a plausible
explanation for some historical `test_rookie_scope` flakiness attributed to Python-version skew
(G-028 / G-030). **It is not filed as a gotcha here** — out of this item's owned paths, and it deserves
its own item (the fix is small: have session fixtures set `last_active` to `time.time()`, or make the
cleanup interval injectable). Flagging it for the orchestrator.

## Deviations from the specced fix

**None.** Both hunks are as written in §5. Two things were checked rather than assumed:

- The field list was re-derived from the code (table above) and matches the diagnosis, so the
  synthesized object was **not** widened.
- `_calc_queue_mirror_reason`'s `caller_member is None` branch (`:13139`) is now unreachable **from this
  route**, its only caller. It was left in place: it is a deliberate mirror of one of
  `_inject_likes_you_cards_impl`'s `continue`s and the function's docstring is written as that mapping.
  Removing it would break the documented correspondence for a dead-code cleanup nobody asked for.

## One correction to the diagnosis's test plan, found during the build

§5's "test change that must ride with it" says to run the happy path **and** the mirror assertion
against the production-shape fixture. The mirror assertion needs one extra step the diagnosis did not
call out: `_inject_likes_you_cards_impl` resolves the **liker** through
`members_by_id.get(like["user_id"])` on the league it is handed
(`backend/server.py:3405`, against the map built at `:3376`). Caller-exclusion is **per-perspective** — the opponent's own session
excludes *them* and includes the caller — so handing it the caller's league object (which now correctly
omits the caller) makes the injector skip the like and the test fails for the wrong reason.
`test_prod_shape_like_reaches_the_opponents_deck` therefore builds the opponent's-perspective league
explicitly, `members=[ME]`. Worth noting because the existing
`test_the_queued_like_reaches_the_opponents_deck` only works by reusing a fixture that happens to hold
both members — the same shortcut that hid the bug.

## For the orchestrator, before merging

1. **Not committed.** Tree left dirty on `claude/fb-410-412-trade-card-polish` alongside the concurrent
   #410/#411/#412 docs work. `backend/server.py` and `backend/tests/test_calc_trade_queue.py` are the
   only code files touched, so the merge should be clean against a mobile-only sibling change.
2. **TEST_LEDGER not written** — outside this agent's owned paths. Numbers to log: targeted 33 passed;
   full suite 4478 passed / 1 skipped / 0 failed vs a 4471 baseline; sabotage name = *"revert the
   synthesized `caller_member` fallback"* → 5 red, all `not_league_member` → restored green.
3. **Backend-only deploy fixes every fielded build**, including the reporter's v1.16.12 / build 140.
   No EAS build, no TestFlight round trip. Post-deploy confirmation steps are in `scope.md` §3.
4. **Follow-up, deliberately not built** (`mobile/`, forbidden here, and needs a TestFlight round trip):
   `mobile/src/utils/queueCalcTrade.ts:43-44` renders `not_league_member` as
   **"@\<partner> isn't in this league."** — but that one reason string covers three causes and **two are
   caller-side**. That mismatch is exactly why the tester reported a *user* not being in the league when
   the server was complaining about the tester. Neutral copy is the cheap fix; splitting the enum is the
   thorough one and **is** a cross-client contract change. Detail in `scope.md` §6.
5. **`docs/feedback/items/INDEX.md`** still has no rows past #286 (documented drift). This folder was
   not added — carry it forward if the index is regenerated.
6. **The suite-wide `_cleanup_loop` session-eviction race** above is worth its own item.
