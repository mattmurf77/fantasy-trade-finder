# P0-1 — The default path never completes its own progression

> Remediation plan for finding **P0-1** of the 2026-08-09 mobile UX audit.
> Source spec: `docs/business/product/2026-08-09-mobile-ux-audit/07-build-handoff-prompt.md` §P0-1,
> backed by `04-priority-backlog.md` §P0-1 and `06-resolutions.md` §P0-1.
>
> **Status:** PLAN ONLY — no code written. Worktree `ftf-p0-remediation`, branch
> `p0-remediation-2026-08-10`, off `origin/main @ ab9368f`.

## Contents

- [1. Verified current state](#1-verified-current-state)
- [2. Design](#2-design)
- [3. Exact change list](#3-exact-change-list)
- [4. Surface changes](#4-surface-changes)
- [5. Backfill strategy](#5-backfill-strategy)
- [6. Maestro delta](#6-maestro-delta)
- [7. Docs impact table](#7-docs-impact-table)
- [8. Test plan](#8-test-plan)
- [9. Risks and open questions](#9-risks-and-open-questions)

---

## 1. Verified current state

Re-verified line-by-line against **this** worktree (`ab9368f`). The audit pinned
`72a0770`; line numbers below are current, and where they differ from the audit
the difference is noted. **Every substantive claim in the audit holds.**

### 1.1 `ranking_method` is written from exactly two places, both off the default path

| Writer | Where | Reached by |
|---|---|---|
| `POST /api/ranking-method` → `set_ranking_method` | `backend/server.py:6288-6330`, `backend/database.py:3358-3365` | `mobile/src/screens/RankHomeScreen.tsx:58-61` (`choose()` → `setRankingMethod(m.pref)`) — the Rank Home chooser |
| same route | same | `mobile/src/screens/SettingsScreen.tsx:229-238` (`onRankingPrefChange`) — Settings ranking-preference row |
| `set_ranking_method(user_id, "quickset")` | `backend/test_users.py:153` | **QA-only** `/api/test-users` seeding (`board_owner`+ stages). Not a production path. |

The audit cited `RankHomeScreen.tsx:64` / `SettingsScreen.tsx:231`; the calls have
drifted to `:59` / `:231` respectively. Substance unchanged: **no save handler
writes the column.**

Launch routing for a fresh user goes Rank tab → Quick Set, never through the
chooser: `mobile/src/navigation/TabNav.tsx:195-215` (`useSession.rankingMethodPref`;
null pref ⇒ next unset QuickSetTiers position), documented at
`mobile/src/navigation/CLAUDE.md:7`.

### 1.2 NULL falls to the trio branch

`backend/database.py:3368-3376` — `get_ranking_method` returns `None` when unset
(audit cited `3362-3370`; +6 lines of drift).

`backend/server.py:6155-6175` — the unlock ladder in `get_rankings_progress`:

```
6157    ranking_method = None
6163    if ranking_method == "manual":          → unlocked = True   (unconditional)
6165    elif ranking_method in ("tiers","quickset"):
                                                → unlocked = all 4 positions in tiers_saved
6174    else:   # 'trio' or null
6175        unlocked = all(counts[p] >= threshold for p in POSITIONS)   # 10 × 4 = 40
```

`'anchor'` is **not** handled and also falls to the trio branch — that is audit
finding **A-16**, out of scope here (see §9.3).

### 1.3 Tier saves never touch the interaction counter

`POST /api/tiers/save` (`backend/server.py:7238-7425`) writes Elo overrides
(`service.apply_tiers` → `save_tier_overrides`), marks `tiers_saved`
(`save_tiers_position`, `:7361`), publishes `member_rankings`, records
`tier_save` / `quickset_completed` events — and never increments the trio
interaction count that the else-branch measures. Confirmed.

### 1.4 The consequences chain

- `mobile/src/navigation/RootNav.tsx:259-283` — `progressQuery` tails
  `/api/rankings/progress`; `pushEnabled = everUnlockedRef.current || data?.unlocked === true`
  (`:266-267`) and is the third argument to `usePushNotifications(...)` (`:279-283`).
  **`unlocked:false` ⇒ the push primer never fires.** (Audit cited `:264`; now `:267`.)
- `mobile/src/screens/RankScreen.tsx:356, 685-697` — the payoff banner
  ("Your board now prices your trades — see the Acquire tab", flag
  `ux.outlook_inline_default` = true in release) renders only on
  `progress.unlocked`.
- `mobile/src/screens/LeagueScreen.tsx:826-836` — leaguemates render the
  member badge `'Unlocked'` vs `'in progress'` from `unlocked_count`; the web
  twin at `web/js/app.js:5165-5177` shows `Signed up · ranking` vs `Signed up`
  off `has_ranking_method`.

### 1.5 The per-position ring is already correct — operator note confirmed

`mobile/src/screens/LeagueScreen.tsx:326-334`:

```ts
const positionsRanked = progress
  ? progress.unlocked ? 4
    : (['QB','RB','WR','TE'] as const).filter(
        (p) => num(progress[p]) >= num(progress.threshold, 10) || tiersSaved.includes(p)).length
  : null;
```

`tiersSaved` comes from `/api/tiers/status`, never from `ranking_method`. So the
ring reads **4/4** while `unlocked` is **false** — exactly the sharp edge the
operator flagged. Only the global unlock is broken.

### 1.6 The bug already has a first-class fixture in the repo

`backend/tests/fixtures/profiles/quickset-done.json` exists **solely** to
reproduce this state (capture request #8), and `backend/tests/fixtures/seed_ui_test_db.py:314-366`
(`_validate_quickset`) actively **refuses** any profile that would un-reproduce
it. `mobile/.maestro/capture/league@quickset-done.yaml` photographs it as
`league__progress-ring--4-4-locked`.

**This is load-bearing for the change list:** the fix inverts the premise of a
fixture, a seeder guard, and a capture flow. All three must move with it, or the
seeder will start refusing coherent profiles and the screen library will ship a
capture whose name asserts the opposite of runtime behaviour.

### 1.7 Nothing in current code contradicts the audit

Specifically checked for the audit's own falsifiers:

- **No server-side backfill exists.** `_migrate_db` (`backend/database.py:1834-2230`)
  runs `_backfill_dual_format` and `_backfill_mfl_name_entities` only; neither
  touches `ranking_method`.
- **No independent push path.** `usePushNotifications` is mounted once, in
  `RootNav.tsx`, gated on `pushEnabled`.
- The monotonic floor at `server.py:6177-6187` (`unlocked_formats`) can rescue a
  user only *after* they were once computed unlocked — it cannot rescue a
  never-unlocked Quick Set user.

---

## 2. Design

**Write the method at the point of use, conditionally, never overwriting a
working one.** Four save handlers gain one guarded line each; one new DB helper
does the write atomically; one startup backfill covers users already stuck.

### 2.1 The write rule — first-use wins, with one targeted upgrade

New helper in `backend/database.py`:

```python
def set_ranking_method_if_unset(user_id, method, allow_over=()) -> bool
```

A single conditional `UPDATE … WHERE sleeper_user_id = :uid AND (ranking_method
IS NULL OR ranking_method = '' OR ranking_method IN :allow_over)`, returning
`rowcount > 0`. One statement ⇒ race-free under concurrent saves; no
read-then-write window.

**Why first-use wins and not last-use wins.** The unlock rule is
method-dependent, so overwriting an established method can *re-lock* a user who
already qualified under the old one. That regression is not hypothetical — it is
documented in the code at `server.py:6177-6183` ("Users who already qualified via
one method … and later switched … were getting re-locked here"), which is why the
monotonic `unlocked_formats` floor exists. First-use-wins means a method is only
ever written where there was nothing, so the change can never subtract an unlock.

**The one exception (`allow_over=("anchor",)`).** `'anchor'` is the only method
string whose unlock rule cannot succeed at all (§1.2 — it falls to the trio
branch). Letting it shadow a later completed Quick Set board would create a *new*
failure mode: anchor-first users permanently locked while quickset-first users
unlock, purely on ordering. So a completeness-marking tiers/quickset save is
allowed to overwrite `'anchor'`, and only `'anchor'`. This is strictly
improving — it can only turn a guaranteed-locked state into a possibly-unlocked
one — and it does **not** fix A-16 (anchors alone still never unlock).

This is the one deliberate addition to the handoff's literal spec; see open
question **Q1**.

### 2.2 Method per route

| Route | Method written | Guard |
|---|---|---|
| `POST /api/tiers/save` | `via` (`'quickset'` or `'tiers'`) | only when `scope != "rookie"` and `via in ("tiers","quickset")`, i.e. only a **completeness-marking** save; `allow_over=("anchor",)` |
| `POST /api/rank3` | `'trio'` | after `record_ranking` succeeds |
| `POST /api/rankings/reorder` | `'manual'` | skip `via == "rookie_ranks"` |
| `POST /api/anchor/save` | `'anchor'` | only `via == "anchors"` (skip `"draft_room"`) |

**Rookie-scope exclusions.** A `scope=rookie` tier save deliberately does *not*
mark a position complete (`server.py:7352-7362` — "`tiers_saved`/`all_done` are
COMPLETENESS markers, and a rookies-only save does not complete a position"), and
`via: 'rookie_ranks'` is the editable consolidated rookie board. Tagging a method
off a subset save would pin a user to an unlock rule they never opted into.
Skipping them costs nothing: their next full-board save writes the method.

**`draft_room` exclusion.** `_ANCHOR_VIA = ("anchors", "draft_room")`
(`server.py:1283`). Answering an anchor inside the Draft Room is not "choosing
the Pick Anchor wizard as my ranking method" and must not pin the user into the
branch that cannot unlock.

### 2.3 Placement inside each handler

The call goes **after** the mutation has succeeded and inside the existing
`try:` body, next to the other best-effort side effects (`record_event`,
`_invalidate_league_members_cache`, `_refresh_taste_board_prior`), wrapped so it
can never fail the request. A failed save must never leave a method behind.

Thin server-side wrapper so the four call sites stay one line each:

```python
def _note_ranking_method(sess, method, *, allow_over=()) -> None:
    """P0-1: record the method at the point of USE. Never raises."""
```

It also drops the 60-second league-members cache
(`_invalidate_league_members_cache`, `server.py:5789-5798`) **only when it
actually wrote**, so the `has_ranking_method` projection leaguemates see is not
stale — mirroring what `set_ranking_method_route` already does at `:6318-6326`.

### 2.4 Why no client change is needed

`useSession.rankingMethodPref` is a **device-local** routing pref read from
AsyncStorage (`mobile/src/state/useSession.ts:194-220`); it is never hydrated
from the server. Writing the server column therefore cannot perturb launch
routing, the chooser, or Settings. The mobile change list is limited to one
`testID` for the Maestro assertion (§3.4).

### 2.5 What this deliberately does not do

- Does not change the unlock ladder itself (`server.py:6163-6175`).
- Does not add `'anchor'` to the tiers branch (**A-16**).
- Does not add an evidence requirement to the manual branch (**A-17**).
- Does not touch the onboarding sub-flags (**P0-9**, operator's call).

---

## 3. Exact change list

### 3.1 `backend/database.py`

1. **Add `set_ranking_method_if_unset(user_id, method, allow_over=()) -> bool`**
   beside `set_ranking_method` (~`:3358`). Single conditional `UPDATE`; returns
   whether a row was written. Docstring states the first-use-wins contract and
   why (re-lock hazard, cross-ref `server.py:6177`).
2. **Add `backfill_ranking_method_from_tiers() -> int`** (§5). Python-side, reuses
   `_parse_per_format_json` so the per-format `tiers_saved` shape is read the same
   way `get_tiers_saved` reads it (`:3573-3585`).
3. **Call the backfill from `_migrate_db()`**, immediately after
   `_backfill_mfl_name_entities()` (`:1970-1971`) — same slot, same
   idempotent-every-boot contract as the two existing backfills.
4. **Update the column comment at `:181`** — `# null | 'trio' | 'manual' |
   'tiers' | 'anchor' | 'quickset'` (it is stale today: it omits `anchor` and
   `quickset`, both shipped and both accepted by
   `set_ranking_method_route`). Trivially in scope; a comment that contradicts
   runtime behaviour is exactly the A-33 class the handoff warns about.

### 3.2 `backend/server.py`

5. **Import** `set_ranking_method_if_unset` alongside the existing
   `set_ranking_method, get_ranking_method` (`:148`).
6. **Add `_note_ranking_method(sess, method, *, allow_over=())`** near
   `_invalidate_league_members_cache` (`:5789`). Never raises; invalidates the
   members cache only on an actual write.
7. **`post_rank3`** (`:5874`) — after `rank_set = service.record_ranking(...)`
   (`:5910`), inside the `try`: `_note_ranking_method(sess, "trio")`.
8. **`save_tiers_route`** (`:7238`) — after `all_done` is computed (`:7365`),
   using the already-computed `via` (`:7383-7387`; move the `via` assignment a
   few lines up or read `body.get("via")` again — prefer moving it, one
   definition):
   `if scope != "rookie" and via in ("tiers", "quickset"): _note_ranking_method(sess, via, allow_over=("anchor",))`
9. **`save_anchor_route`** (`:7435`) — after `apply_anchor` succeeds (`:7479`):
   `if via == "anchors": _note_ranking_method(sess, "anchor")`
10. **`reorder_rankings`** (`:7800`) — after `apply_reorder` succeeds (`:7822`):
    `if body.get("via") != "rookie_ranks": _note_ranking_method(sess, "manual")`
11. **Comment the unlock ladder** (`:6155-6175`) with a one-line pointer that
    `ranking_method` is now written at the point of use, so `NULL` means
    "no ranking action taken since the P0-1 fix" rather than "never chose".

### 3.3 Test fixtures — the `quickset-done` profile inverts

12. **`backend/tests/fixtures/profiles/quickset-done.json`** — set
    `app_user.ranking_method: "quickset"` and `app_user.unlocked: true`; rewrite
    the `description` so the profile now means **"4/4 AND unlocked — the P0-1
    fixed state"**, retaining one sentence of history. Without this the profile
    describes a state the backfill destroys at Flask boot.
13. **`backend/tests/fixtures/seed_ui_test_db.py:314-366` (`_validate_quickset`)** —
    invert THE guard. Post-fix the incoherent combination is
    *all-four-positions Quick Set + `unlocked:false`* **regardless of
    `ranking_method`**, because the startup backfill tags a NULL method as
    `'quickset'`. Refuse that; drop the "use `ranking_method:null`" escape hatch
    from the message. Update the docstring to describe the fixed contract.

### 3.4 Mobile — one `testID`, no behaviour change

14. **`mobile/src/screens/RankScreen.tsx:686`** — add
    `testID="rank.unlocked-banner"` to the `unlockedBanner` `View`. Needed
    because the Maestro assertion for "the payoff surfaced" would otherwise be a
    full-match text regex on flag-dependent copy (law 1 + law 12). No visual
    change.
15. **`mobile/src/components/CLAUDE.md`** — register the new id in the testID
    registry so `mobile/scripts/testid-lint.sh` passes.

### 3.5 Maestro / screen library

16. New flow `mobile/.maestro/flows/p0-1-quickset-unlock.yaml` (§6).
17. `mobile/.maestro/capture/league@quickset-done.yaml` — rename the capture
    `progress-ring--4-4-locked` → `progress-ring--4-4-unlocked`, rewrite the
    header rationale, and swap the `league.works-now` assertion for the
    unlocked reading (§6.2).
18. `screens/` library index entry for the renamed capture (whatever
    `screens/CLAUDE.md` indexes — re-check at build time; the capture rename is
    the trigger).

### 3.6 Backend tests

19. New `backend/tests/test_ranking_method_point_of_use.py` (§8.1).

### 3.7 Docs + living memory

20. Per §7.
21. `living-memory/CHANGELOG.md`, `TEST_LEDGER.md`, `DECISIONS.md` (D-011:
    first-use-wins + the `'anchor'` upgrade exception), `GOTCHAS.md` only if the
    build loses time to something new.

---

## 4. Surface changes

Answered explicitly because these drive the project's bright-line gates.

| Surface | Changed? | Detail |
|---|---|---|
| **Schema** | **No.** | `users.ranking_method` already exists (`database.py:181`, migration entry `:1861`). No column added, no type changed, no index. |
| **API contract (shape)** | **No.** | No route added, removed, renamed. No request field added. No response key added or removed. |
| **API contract (values)** | **Yes — value domain only.** | `/api/rankings/progress` → `ranking_method` is now non-null far more often, and `unlocked` flips `false → true` for the Quick Set cohort (that *is* the fix). `/api/account/link-sleeper` 409 `board_summary.ranking_method` likewise. No consumer parses the value as an enum with a closed set — mobile does not read it at all (§2.4); `web/js/app.js:866` reads it for truthiness only. |
| **Feature flags** | **No.** | No new flag, no flag default changed. Deliberate: the change removes a wrong answer rather than adding a surface, and flag-gating it would mean shipping a knob whose OFF position is a known bug. See **Q2** — if the operator wants a rollback lever, the honest one is the backfill sentinel, not a client flag. |
| **Analytics events** | **No new event name.** | No `record_event` call added, so nothing to register against the default-deny taxonomy (`backend/analytics_taxonomy.py:110`). See **Q3**: the implicit writes deliberately do **not** fire `ranking_method_changed`, because that event means "the user chose a method" and inflating it would corrupt a shipped funnel metric. |
| **Analytics *dimensions*** | **Yes — flagged.** | `ranking_method` is a registered **experiment targeting attribute**: `backend/experiments.py:59` `"ranking_method": (_USERS, {"account"})`, read into assignment attrs at `:258`. Any live experiment targeting on `ranking_method` will see its eligible population change (mostly NULL → `'quickset'`). Must be checked before merge — see **Q4**. It is also a segmentation dimension for every downstream analytics read. |
| **Feature-flag surfaces** | No. | |
| **Push behaviour** | **Yes — intended.** | The push primer starts firing for the Quick Set cohort. That is the acceptance criterion, not a side effect. Also `league_member_unlocked_trades` pushes fan out to leaguemates on the first unlock transition (`server.py:6221-6255`) — see **R2**. |
| **Web client** | **Yes — incidental, benign.** | `web/js/app.js:856-870` stops showing the ranking-method chooser to a user who already has a method (more correct); `:5173` shows `Signed up · ranking` for backfilled leaguemates (more accurate, and usually superseded by the `Unlocked` branch). |

**Bright-line verdict:** this touches an experiment-targeting attribute and
changes analytics dimension values, so it is **not** a "quick fix". Per
`CLAUDE.md` §Conventions the **full gates apply** unless the operator explicitly
declares express — and an agent never self-selects express. Plan assumes full
gates.

---

## 5. Backfill strategy

### 5.1 Recommendation — startup migration inside `_migrate_db()`

Ship as a Python backfill called from `_migrate_db()`, immediately after the two
existing backfills (`database.py:1968-1971`).

**Cohort (deliberately narrow):**

> rows where `ranking_method IS NULL` **and** `tiers_saved` names **all four**
> of QB/RB/WR/TE **for at least one scoring format** → set `ranking_method = 'quickset'`.

**Why that predicate and not "any saved tiers".** A user with a *partial* tier
board and a full trio board is a real shape (users mix methods). Tagging them
`'quickset'` would move them from the trio branch (unlocked at 40 interactions)
to the tiers branch (needs all four positions saved) and could **re-lock** them.
Restricting to all-four-saved makes the backfill *strictly improving*: for every
row it touches, the tiers branch returns `True`, which is ≥ whatever the trio
branch returned. The narrower cohort costs nothing — a partial-board user's next
save writes the method at the point of use anyway.

**Why Python and not raw SQL.** `tiers_saved` is a per-format JSON blob
(`{"1qb_ppr": ["QB","RB"], "sf_tep": [...]}`, parsed by `_parse_per_format_json`).
Expressing "all four positions in at least one format" as portable
SQLite+Postgres SQL over a TEXT column is fragile; the `users` table is small
enough that a single `SELECT sleeper_user_id, tiers_saved WHERE ranking_method
IS NULL`, a Python filter, and one bulk `UPDATE … WHERE sleeper_user_id IN (…)`
is both clearer and safer. Idempotent by predicate: after the first run the
cohort is empty.

**Shape:** one `try/except` around the whole thing, logging the count, matching
`_backfill_dual_format`'s "never break boot" posture (`database.py:2233-2280`).

### 5.2 Rejected: lazy on-read repair

Repairing inside `get_rankings_progress` would put a write on a hot, cached GET
that is polled by every mounted `RootNav` and is decorated `@_gate_unverified_read`.
It also heals nobody the point-of-use write wouldn't heal on their next action,
and it makes the endpoint's behaviour depend on read order. Rejected.

### 5.3 Rejected: one-shot script

A `scripts/` one-shot would need `DATABASE_URL_PROD` from `secrets.local.env`
and a deliberate operator step against the live Postgres. Render auto-deploys on
push to `main`, so the script would lag the code that depends on it, leaving a
window where new binaries assume a backfilled column. It is also the option most
likely to be forgotten. Rejected — with one exception: if the operator wants a
dry-run count before merging, the same function can be invoked from a REPL
against a prod replica. Recommended as a pre-merge sanity check, not as the
delivery mechanism.

### 5.4 Consequence that must be handled (not optional)

`init_db()` runs at `server.py:407`, i.e. on **every** Flask boot including the
seeded UI-test backend. The backfill will therefore rewrite the `quickset-done`
seed user's NULL method to `'quickset'` on boot. Change-list items **12** and
**13** exist for exactly this. Skipping them leaves a fixture asserting a state
the server no longer produces, and a seeder guard refusing the only coherent
post-fix configuration.

### 5.5 Value choice: `'quickset'` vs `'tiers'`

The handoff specifies `'quickset'` and this plan follows it. They are
behaviourally identical at the unlock ladder (`server.py:6165`). The only
difference is the analytics/segmentation label, and `'quickset'` is the honest
guess: the default route lands on QuickSetTiers (`TabNav.tsx:195-215`), so the
overwhelming majority of NULL-method tier boards were built there. Recorded as a
DECISIONS entry so the labelling assumption is on the record for anyone reading
a method-segmented chart later.

---

## 6. Maestro delta

Conventions: `mobile/.maestro/README.md` — flow-authoring laws 1-23. The laws
that bind this delta are called out inline.

### 6.1 New flow — `mobile/.maestro/flows/p0-1-quickset-unlock.yaml`

Header block per convention: `appId`, `# tc:`, `# profile: quickset-done`,
`# flags: release` (law 16 — a resolved fixture filename under
`backend/tests/fixtures/flags/`), `# source:`, `tags: [p0-1, unlock]`.

Profile is **`quickset-done`** post-update (item 12): a Quick Set board across
all four positions, zero trio interactions. That is precisely the acceptance
cohort, already seeded — no new profile needed.

Steps:

1. `launchApp: {clearState: true, clearKeychain: true, stopApp: true}` — cold
   start is mandatory (law 6: the react-query cache is persisted, and
   `RootNav`'s progress query would otherwise answer from disk).
2. Retry-hardened sign-in preamble as `qa_quickset`, **asserting the typed
   username before Continue** (law 10), then `leagues.row.*` → tap.
3. `extendedWaitUntil: id: tab.trades`, then settle on `id: rank.more-ways`
   before any tab tap (law 8 — #244 launch routing steals early tab taps).
4. **Assertion A — the ring.** `tapOn: tab.league` → `league-summary.league-home`
   → `league.hero` → `scrollUntilVisible: {element: {id: league.progress-module},
   direction: DOWN, visibilityPercentage: 100}` (law 2; **no** `centerElement`
   before a shutter/assert on a tall card) → `assertVisible: text:
   ".*4 of 4 positions ranked.*"`. Matching the accessibilityLabel, not the
   in-ring "4/4" numeral, is mandatory: `PositionsRing`'s wrapper is
   `accessible`, which collapses its subtree on iOS (law 3, and the RUN-1
   finding already recorded in `capture/league@quickset-done.yaml`).
5. **Assertion B — the unlock, same session.** `tapOn: tab.rank` →
   `rank.more-ways` → open Trios → `assertVisible: id: "rank.unlocked-banner"`
   (the new testID from change 14). This banner renders on
   `progress.unlocked === true` (`RankScreen.tsx:685`) and is the same boolean
   that gates `pushEnabled` in `RootNav.tsx:267` — so it is the observable proxy
   for the push gate. Asserting the id rather than the copy sidesteps the
   `ux.outlook_inline_default` copy fork (laws 1 and 12).
6. `takeScreenshot: p0-1__quickset-unlocked` and **eyeball it** (law 23).

**Why A and B in one flow.** The acceptance criterion is "4/4 **and**
`unlocked:true` **together**". Two separate flows could each pass on different
sessions and never prove simultaneity.

**Explicitly NOT asserted: the iOS push permission dialog.** It is a SpringBoard
alert outside the app's hierarchy; Maestro cannot reliably assert it, and
`usePushNotifications` additionally short-circuits when permission was already
granted on the device. Waived with the proxy above (`rank.unlocked-banner` ⇔
`progress.unlocked` ⇔ `pushEnabled`), plus the pytest assertion on the raw
`unlocked` boolean (§8.1). Recorded in the scope block §3.

No `fail_next` / `latency` injections: every state here is the fixture's resting
answer (laws 11-13 do not apply).

### 6.2 Amended capture — `mobile/.maestro/capture/league@quickset-done.yaml`

The file's entire header argues the 4/4-but-locked contradiction. Post-fix that
contradiction is gone and the capture would silently keep passing under a name
asserting a bug that no longer exists.

- Rename `# captures:` / `# interactive-stop:` / `takeScreenshot:` from
  `progress-ring--4-4-locked` → `progress-ring--4-4-unlocked`.
- Rewrite the header: the profile now shows a Quick Set user whose ring reads
  4/4 **and** whose account is unlocked; keep two sentences of history pointing
  at this plan.
- Keep the `".*4 of 4 positions ranked.*"` assertion (unchanged, still correct).
- **Re-examine the `league.works-now` assertion.** It renders while mutual
  matches are zero (`matches_seed {mutual: 0, awaiting: 0}`), which is still
  true, so the step will still pass — but its stated justification ("pins the
  frame to the locked reading") becomes false. Either re-justify it or drop it;
  do not leave the comment.

### 6.3 Smoke-suite impact

Crossing surfaces: `flows/smoke/04-tiers.yaml` (tier save path),
`09-league.yaml` (the ring), `06-trades-deck.yaml` (unlock-gated deck).
Expectation: all unchanged and green — the fix only flips `unlocked` for
profiles that complete a Quick Set board, and the smoke profiles do not.
Verify rather than assume.

### 6.4 `testID` lint

One new id (`rank.unlocked-banner`), a literal string, so
`mobile/scripts/testid-lint.sh` covers it once registered in
`mobile/src/components/CLAUDE.md` (law 4 does not apply — not a template
literal).

---

## 7. Docs impact table

Row-by-row per `docs/CLAUDE.md` triggers and the scope template §4.

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **Updated** | `/api/rankings/progress` row — document that `ranking_method` is now written at the point of use by the four save routes, so it is non-null for any user who has taken a ranking action, and that `unlocked` for tier-based users no longer depends on visiting the chooser. Also annotate the four save routes with the side effect. No route added/renamed/removed and no request/response key changes. |
| `docs/data-dictionary.md` | **Updated** | `:105` `users.ranking_method` — the enum listed there (`null / 'trio' / 'manual' / 'tiers'`) is already stale (missing `'anchor'`, `'quickset'`); correct it and add "written implicitly at first use by `/api/tiers/save`, `/api/rank3`, `/api/rankings/reorder`, `/api/anchor/save`; backfilled to `'quickset'` for pre-fix all-four tier boards". Column itself unchanged. |
| `docs/cross-client-invariants.md` | **Updated** | `:205` (Ranking method strings) — the string set is unchanged, but the *contract* changes from "the chooser records the user's preference" to "written at the point of use, first-use wins, `'anchor'` upgradable by a completeness-marking tiers save". This is exactly the cross-client shared-enum semantics the doc governs. |
| `living-memory/LLD.md` | **Updated** | A convention shifts: implicit column writes from save handlers, and the `set_ranking_method_if_unset` conditional-write idiom. One short entry. |
| `docs/architecture.md` | **n/a** | No module wiring or data-flow change — same routes, same services, same DB. |
| `living-memory/HLD.md` | **n/a** | No new module, client, or major flow. |
| `docs/glossary.md` | **n/a** | No new domain term; `ranking_method`, `quickset`, `unlock` all already defined. |
| `docs/config-reference.md` | **n/a** | No env var, no `config/features.json` key, no `model_config` key added. |
| `docs/runbook.md` | **Updated** | Short operational note: the backfill runs at boot inside `_migrate_db`, what it touches, its expected one-time row count, and how to confirm it ran (`SELECT count(*) FROM users WHERE ranking_method IS NULL AND tiers_saved IS NOT NULL`). Also note the seed-fixture interaction from §5.4. |
| ADR | **n/a** | No architectural decision of ADR weight. |
| `living-memory/DECISIONS.md` | **Updated** | **D-011** — first-use-wins over last-use-wins (re-lock hazard), the single `'anchor'` upgrade exception, the rookie/`draft_room` exclusions, and the `'quickset'` labelling assumption in the backfill. |
| `living-memory/CHANGELOG.md` | **Updated** | Dated H2 at ship. |
| `living-memory/TEST_LEDGER.md` | **Updated** | pytest + `tsc` + the sim-gate run. |
| `living-memory/DEPENDENCIES.md` | **n/a** | No dependency added, bumped, or removed. |
| `screens/CLAUDE.md` (screen library) | **Updated** | The `league@quickset-done` capture is renamed (§6.2); its index entry follows. |
| `docs/business/product/2026-08-09-mobile-ux-audit/*` | **n/a** | The audit is a dated artifact — record the outcome in CHANGELOG, don't rewrite the audit. |

---

## 8. Test plan

### 8.1 Backend — `backend/tests/test_ranking_method_point_of_use.py` (new)

Follow the in-repo pattern (`backend/tests/test_rookie_scope.py`): in-memory
SQLite via `monkeypatch.setattr(db_module, "engine", engine)`, an injected fake
`RankingService`, a real Flask test client with a seeded session token.

**Point-of-use writes**

| # | Case | Assert |
|---|---|---|
| T-1 | NULL method → `POST /api/tiers/save {via:'quickset'}` | `users.ranking_method == 'quickset'` |
| T-2 | NULL method → `POST /api/tiers/save` with no `via` | `'tiers'` (the route's own default, `server.py:7383-7387`) |
| T-3 | NULL method → `POST /api/rank3` | `'trio'` |
| T-4 | NULL method → `POST /api/rankings/reorder` | `'manual'` |
| T-5 | NULL method → `POST /api/anchor/save {via:'anchors'}` | `'anchor'` |
| T-6 | NULL method → `POST /api/anchor/save {via:'draft_room'}` | still `NULL` |
| T-7 | NULL method → `POST /api/tiers/save {scope:'rookie', via:'rookie_quickset'}` (flag `ranks.rookie_subset` on) | still `NULL` |
| T-8 | NULL method → `POST /api/rankings/reorder {via:'rookie_ranks'}` | still `NULL` |

**Idempotence / precedence**

| # | Case | Assert |
|---|---|---|
| T-9 | method `'trio'` → tiers/save | **still `'trio'`** (first-use wins; the re-lock guard) |
| T-10 | method `'manual'` → rank3 | still `'manual'` |
| T-11 | method `'anchor'` → tiers/save `via:'quickset'` | upgraded to `'quickset'` (the one exception) |
| T-12 | method `'anchor'` → tiers/save `scope:'rookie'` | still `'anchor'` (rookie saves never upgrade) |
| T-13 | two tiers/saves in a row | second is a no-op write; value unchanged |
| T-14 | a save that **fails** (invalid position → 400) | method unchanged |

**The acceptance criterion, end to end**

| # | Case | Assert |
|---|---|---|
| **T-15** | Fresh user, NULL method, zero trio interactions. `POST /api/tiers/save` for QB, RB, WR, TE with `via:'quickset'`. Then `GET /api/rankings/progress`. | `unlocked is True` **and** `ranking_method == 'quickset'` **and** all four per-position counts still `0` (proving the ring's `tiersSaved` path and the unlock agree without any trio interaction). This is the machine-checkable half of the acceptance criterion. |
| T-16 | Same, but only QB/RB/WR saved | `unlocked is False` — the fix must not unlock a partial board |
| T-17 | T-15 then `GET /api/rankings/progress` twice | `ranking_complete_first_time` recorded exactly once (`was_first` gating, `server.py:6218-6232`) |

**Backfill**

| # | Case | Assert |
|---|---|---|
| T-18 | User with `tiers_saved = {"1qb_ppr": ["QB","RB","WR","TE"]}`, method NULL → run backfill | `'quickset'` |
| T-19 | User with `tiers_saved = {"1qb_ppr": ["QB","RB"]}`, method NULL → run backfill | **still NULL** (narrow cohort; must not re-lock a mixed-method user) |
| T-20 | User with method `'trio'` and a full tier board → run backfill | still `'trio'` |
| T-21 | Backfill run twice | second run reports 0 rows; no value churn |
| T-22 | `tiers_saved` NULL / `''` / `'{}'` / malformed JSON | no crash, no write |

**Regression guard**

| # | Case | Assert |
|---|---|---|
| T-23 | User with method `'trio'`, 40 interactions, `unlocked_formats` already containing the active format, then a tiers/save | `/api/rankings/progress` still `unlocked: True` (the monotonic floor at `server.py:6177-6187` still carries them) |

**Existing suites that must stay green** (they touch the same column or the
unlock ladder): `test_test_users.py`, `test_seed_ui_test_db.py`,
`test_account_first.py`, `test_verified_sessions.py`, `test_verified_reads.py`,
`test_trio_cross_position.py`, `test_rookie_scope.py`, `test_accounts.py`
(board-merge `ranking_method` in `board_data_summary`), `test_deck_first_session.py`.

Command: `python3 -m pytest backend/tests/ -q`.

### 8.2 Mobile

`cd mobile && npx tsc --noEmit` — expected clean; the only mobile edit is a
`testID` prop. Plus `mobile/scripts/testid-lint.sh`.

### 8.3 Simulator gate

Change class spans two tiers: backend route behaviour consumed by mobile
(**Tier 3**) plus a mobile file edit (**Tier 2**, logic-only, no visual change).
Take the stricter: **Tier 2** — the new `p0-1-quickset-unlock.yaml` flow plus
the affected smoke subset (`04-tiers`, `06-trades-deck`, `09-league`), and run
`mobile/scripts/screen-freshness.sh`, re-capturing only what it flags. The
`league@quickset-done` capture is re-run regardless because it is being renamed.
Evidence: `TEST_LEDGER.md` entry + `qa/sim-runs/last-sim-run.json`.

### 8.4 Manual verification (the acceptance criterion, end to end, by eye)

1. Seed `quickset-done` (post-update), boot the UI-test backend on :5001
   (kill orphans first — law 19), install the build.
2. Sign in as `qa_quickset`, open League → progress module → ring reads **4/4**.
3. Rank tab → Trios → the payoff banner is present.
4. Confirm the push primer: on a simulator that has never been asked, the iOS
   permission alert appears once `pushEnabled` flips. If the sim has stale
   permission state, `xcrun simctl privacy <udid> reset all <bundle>` first;
   otherwise verify by proxy at the network layer (`/api/rankings/progress`
   returning `unlocked:true`) and record which was used.
5. **Pre-fix control:** run step 2-3 against the *pre-fix* build with the same
   fixture and confirm 4/4 + no banner. A test that never observed the bug
   proves nothing.
6. Prod-shaped check before merge: against a copy of prod (or a replica), count
   the backfill cohort and eyeball a handful of affected users.

---

## 9. Risks and open questions

### Risks

**R1 — A trio user gets re-locked by a later tiers save.**
First-use-wins prevents the common case, but a user with a *pre-fix* NULL method
who has 40 trio interactions and then does a full Quick Set save will be tagged
`'quickset'` and re-evaluated on the tiers branch. *Mitigation, already in the
code:* the monotonic `unlocked_formats` floor (`server.py:6177-6187`) was added
for exactly this transition. *Residual:* a user who qualified under the trio rule
but never once polled `/api/rankings/progress` while qualifying, so the floor was
never persisted. `RootNav` polls that endpoint at the root of the authed tree, so
this requires never having had the app open while qualified — effectively
unreachable, but non-zero. Covered by T-23; note it in the ledger.

**R2 — First-unlock fan-out fires for the backfilled cohort.**
The first `/api/rankings/progress` call after the backfill takes the
`was_first` branch: it records `ranking_complete_first_time` and sends
`league_member_unlocked_trades` pushes to every joined leaguemate
(`server.py:6218-6255`). At current TestFlight scale that is a handful of
notifications; at larger scale it would be a burst of "@user just unlocked Trade
Finder" the same day. *It is also arguably correct* — those users genuinely
became unlocked. Flagged for the operator (**Q5**), with the cheap mitigation
available: have the backfill also insert the qualifying format into
`unlocked_formats` so `was_first` is already spent, suppressing both the event
and the push. Recommend deciding this explicitly rather than by default.

**R3 — Analytics discontinuity.** Method-segmented charts will show a step
change: NULL collapses, `'quickset'` jumps. Anyone reading a
`ranking_method`-segmented series across the deploy boundary sees an artifact.
Mitigated by the CHANGELOG + DECISIONS entries; there is no way to backfill
"which method did they actually use" retroactively.

**R4 — `board_data_summary` "any" flag.** `backend/accounts.py:484-511` computes
`any` partly from `ranking_method`, and it drives the link-Sleeper merge-choice
prompt. In practice every user this change touches already had
`swipes`/`tiers_saved`/`tier_overrides` set (the action that wrote the method
also wrote board data), so `any` was already `True`. No behaviour change
expected; worth one assertion if the merge tests are cheap to extend.

**R5 — Concurrent sessions in this repo.** `CLAUDE.md` warns the working tree
mutates. `server.py` is being touched by sibling P0 agents (P0-2 touches
`TradesScreen.tsx`, P0-3 touches routes + `deepLinks.ts`, P0-5 touches
`RootNav.tsx`). This plan's `RootNav.tsx` interaction is read-only, but re-diff
`server.py` line numbers immediately before editing.

### Open questions

**Q1 — Approve the `'anchor'` upgrade exception?** (§2.1)
The handoff's literal spec is "set it from the action if unset". This plan adds
one transition: a completeness-marking tiers/quickset save may overwrite
`'anchor'`. **Recommendation: yes** — without it, a user who answers one anchor
before doing Quick Set is permanently pinned to a branch that cannot unlock,
which is a *new* failure mode created by this change. It is strictly improving
and does not fix A-16. **Default if no answer: implement it** (build is not
blocked).

**Q2 — Any rollback lever wanted?** (§4)
No feature flag is proposed. If the operator wants one, the honest lever is over
the *backfill* (a `model_config` sentinel that skips it), not over the
point-of-use writes — flag-gating the writes would ship a knob whose OFF position
is the bug. **Recommendation: no flag.** Operator call.

**Q3 — Should implicit writes emit an analytics event?** (§4)
Plan: **no**. `ranking_method_changed` means "the user chose a method"
(`server.py:6306-6317`) and is a shipped funnel event; firing it from every first
tier save would corrupt it. The action events (`tier_save`, `trio_swipe`,
`ranking_reorder`, `anchor_answered`) plus `ranking_complete_first_time` already
cover the behaviour. If `an-data-architect` wants an implicit-write signal it
needs a **new** event name registered server-side first (default-deny taxonomy).
**Operator/orchestrator call; not blocking.**

**Q4 — Are any live experiments targeting `ranking_method`?** (§4)
`backend/experiments.py:59` registers it as an account-scope targeting
attribute. If a running experiment targets it, this change moves its eligible
population mid-flight. **This must be checked before merge** — not answerable
from the code alone; it needs a read of live experiment definitions. Blocking on
*merge*, not on build.

**Q5 — Suppress the first-unlock push fan-out for the backfilled cohort?** (R2)
Yes/no from the operator. Cheap either way; the decision should be deliberate.

**Q6 — Fixture ownership.** Change-list items 12-13 rewrite a fixture and a
seeder guard authored days ago specifically to *preserve* this bug. That is the
correct move once the bug is fixed, but it deletes the only reproduction of the
4/4-but-locked state. **Recommendation:** keep the pre-fix capture PNG in the
screen library (renamed with a `--historic` suffix or referenced from this plan)
so the audit's evidence survives the fix. Cheap; worth confirming.

---

## Acceptance criterion — how it is proved

> *A fresh account that only ever uses Quick Set reaches 4/4 on the per-position
> ring AND `unlocked:true` together, and the push primer fires.*

| Half | Proof |
|---|---|
| `unlocked:true` from Quick Set alone, with zero trio interactions | **T-15** (pytest): four `/api/tiers/save` calls, then `/api/rankings/progress` returns `unlocked:true`, `ranking_method:'quickset'`, all per-position counts `0` |
| 4/4 and unlocked **together**, in one session, on device | `flows/p0-1-quickset-unlock.yaml`: `".*4 of 4 positions ranked.*"` **and** `rank.unlocked-banner` in the same run (§6.1) |
| Push primer fires | Proxy: `rank.unlocked-banner` ⇔ `progress.unlocked` ⇔ `pushEnabled` (`RootNav.tsx:267`). Direct check is the manual step §8.4.4 on a permission-reset simulator. The system alert is not Maestro-assertable — waived in the scope block with this reason. |
| Not over-unlocked | **T-16**: a three-position board stays locked |
| Nobody loses an unlock | **T-9/T-19/T-20/T-23** |
