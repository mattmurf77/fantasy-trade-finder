# Feature Scope — Sleeper co-owned roster resolution

**Date:** 2026-08-15
**Entry point:** direct ask (operator-reported dead league)
**Builder:** claude/epic-hellman-6af20f
**Operator sign-off on waivers:** **yes, 2026-08-15** — all three §6 waivers signed off
as written, and the additive `POST /api/session/init` fields explicitly approved (the
CLAUDE.md bright-line confirmation for an API-contract change).

---

## 0. Problem, confirmed

Sleeper rosters carry an optional `co_owners: string[] | null` next to `owner_id`.
FTF has never read it: `git grep -n co_owners -- backend/*.py mobile/src web extension`
returns **nothing outside test fixtures**. Every roster→user match in the product is
`owner_id == user_id`.

Live confirmation, 2026-08-15, operator's own account
(`mattmurf77`, `user_id 313560442465169408`):

```
GET /v1/user/313560442465169408/leagues/nfl/2026   → 4 leagues, incl. 1338231586314780672 "Bush League"
GET /v1/league/1338231586314780672/rosters         → roster_id 3:
                                                       owner_id  460238423161040896
                                                       co_owners ["313560442465169408"]
                                                       players   19
```

So the league **does** appear in the picker (Sleeper's `/user/{id}/leagues` counts
co-ownership), the user selects it, and then roster resolution finds nothing.

Two failures, not one:

1. **No team.** `myRoster` is `undefined` → `user_player_ids: []` → the session has an
   empty roster; trade generation, rankings target, League Summary "You" row and the
   untouchables picker all have nothing to work with.
2. **Own team served as an opponent.** The opponent filter is
   `r.owner_id !== user.user_id`, and `460238… !== 313560…`, so roster 3 is posted as a
   *leaguemate*. The app will happily generate trades between the user and himself.

Failure 2 is the reason a naive one-line client fix is not enough — see §0.2.

### 0.1 Full trace — every roster→user resolution site

Grouped by what breaks. `✅` = already correct once the canonical identity below is
adopted; `⚠️` = needs a change.

**Line numbers are as-of the PRE-FIX tree (`origin/main` @ `21df73f`)** — they locate
the defect, not the current code. After the fix they have shifted; grep the symbol.

**A. Client-side "which roster is mine" (the load-bearing ones — session_init's
payload is entirely client-built, so these poison everything downstream).**

| Site | What it does | |
|---|---|---|
| [mobile/src/api/auth.ts:374](mobile/src/api/auth.ts:374) | `initLeagueSession` — `myRoster` + opponent filter | ⚠️ |
| [mobile/src/api/auth.ts:462](mobile/src/api/auth.ts:462) | `buildSessionInitBody` (league switch) — same pair | ⚠️ |
| [web/js/app.js:806](web/js/app.js:806) | first login | ⚠️ |
| [web/js/app.js:906](web/js/app.js:906) | reload | ⚠️ |
| [web/js/app.js:2548](web/js/app.js:2548) | league switch | ⚠️ |
| [mobile/src/components/TradeDnaSheet.tsx:311](mobile/src/components/TradeDnaSheet.tsx:311) | untouchables picker reads `rosters.find(owner_id === userId)` | ⚠️ |
| [mobile/src/components/InLeagueCalculator.tsx:267](mobile/src/components/InLeagueCalculator.tsx:267) | `rosterByOwner[userId]` = your side of the calculator | ⚠️ |
| [mobile/src/screens/TradesScreen.tsx:2016](mobile/src/screens/TradesScreen.tsx:2016) | `rosterByOwner`; `ownerId === userId` excludes your own roster from the acquire pool | ⚠️ |

**B. Backend, caller-identity comparisons.**

| Site | What it does | |
|---|---|---|
| [backend/server.py:12546](backend/server.py:12546) `_roster_id_for_owner` | Send-in-Sleeper: which roster proposes the trade. A co-owner cannot send. | ⚠️ |
| [backend/server.py:15398](backend/server.py:15398) | `league_members` row for the caller, keyed on session `user_id` | ⚠️ |
| [backend/server.py:20706](backend/server.py:20706) | power rankings `is_you` → false for every team | ⚠️ |
| [backend/server.py:21419](backend/server.py:21419) | free agents: `my_roster_count` / `my_roster_ids` from the snapshot | ⚠️ |
| [backend/server.py:21446](backend/server.py:21446) | free agents: same, from the live Sleeper read (`owner_id == g_user_id`) | ⚠️ |
| [backend/server.py:11804](backend/server.py:11804) `_mock_owner_ids` / [:11825](backend/server.py:11825) `_mock_rosters` | mock-draft owner set = session members + caller | ⚠️ |
| [backend/draft_board_service.py:750](backend/draft_board_service.py:750) | `roster_by_user` for draft-order composition | ⚠️ (alias-only) |

**C. Backend, roster-keyed — correct as written, and the reason the canonical
identity below is `owner_id` rather than the caller's id.**

| Site | Why it's fine | |
|---|---|---|
| [backend/server.py:16564](backend/server.py:16564) `_sleeper_roster_history_on_sync` | `owner_id → roster_id` map; strong `team_key` = `sleeper:{lid}.r{rid}` | ✅ |
| [backend/server.py:16667](backend/server.py:16667) weekly snapshot | iterates rosters, keys by `roster_id` | ✅ |
| [backend/server.py:9586](backend/server.py:9586) `_sync_sleeper_owned_picks` | `roster_id → owner_id`; pick ownership is a roster fact | ✅ |
| [backend/trade_block_service.py:154](backend/trade_block_service.py:154) | block entries keyed on the flagging roster's `owner_id` | ✅ |
| [backend/outlook/league_state.py:191](backend/outlook/league_state.py:191) | `TeamState.user_id = owner_id` | ✅ |
| [backend/power_rankings.py:201](backend/power_rankings.py:201) | consumes `league_members` verbatim | ✅ |

**D. Explicitly account-level — must NOT be re-keyed.** Swipes, tier overrides,
`member_rankings`, entitlements, notifications, feedback, `user_events`. These belong
to a person, not a team.

### 0.2 Why the one-line fix is wrong

Suppose the client only widens the predicate and keeps posting the caller's own id as
the league-member key. `league_members` is a **league-shared** table written by every
member's session_init. Roster 3 then gets two rows:

- the operator's session writes `(1338…, 313560…)` — "my team"
- any *other* leaguemate's session writes `(1338…, 460238…)` — "an opponent"

Result: a 12-team league with 13 member rows and one roster duplicated. Downstream:
power rankings renders 13 teams with two identical ones; session_init's DB-member merge
([server.py:14899](backend/server.py:14899)) injects the `460238…` row as a league member
because it isn't in `existing_member_ids`, so the engine generates trades against a
phantom copy of the user's own team; leaguemate counts, coverage and unlock fanout all
inflate. That is worse than today's failure, which at least fails visibly.

A single key that every observer agrees on is required. `roster_id` would work but is a
schema change; `owner_id` is already that key everywhere in group C.

## 0.3 Decision — canonical league identity is the roster's `owner_id`

> **D-xxx (see DECISIONS.md).** A Sleeper roster belongs to a user when
> `user_id == owner_id` **or** `user_id ∈ co_owners`. A co-owner is an **alias** of the
> roster's primary `owner_id` within that league, never a separate team.

Two identities per session, deliberately distinct:

| | value | governs |
|---|---|---|
| **account identity** — `sess["user_id"]` | the real Sleeper user (`313560…`) | rankings, swipes, tier overrides, entitlements, analytics, notifications, feedback |
| **league identity** — `sess["league_user_id"]` (new) | the resolved roster's `owner_id` (`460238…`); **equals `user_id` for a sole owner** | `league_members` key, `is_you`, "my roster" lookups, mock-draft owner set |

Consequences, stated plainly:

- **Both co-owners see the same team.** That is the intent — it is one team. Their
  *boards* stay personal, so their trade suggestions differ in ordering. Correct.
- **Exactly one `league_members` row per roster**, whichever co-owner logs in. Power
  rankings stay at 12 teams. No phantom opponent.
- **The team is labeled with the primary owner's Sleeper display name**, not the
  co-owner's, because that row is league-shared and every other member sees it. The
  caller's own team is marked by `is_you`, which is what the "You" badge already reads.
- **Known limitation, accepted, not fixed here:** two tables are account-keyed
  (`(league_id, user_id)`) while leaguemates read them by the roster's `owner_id` —
  `member_rankings` (the team's board) and `league_preferences` (its declared outlook,
  read under `trade_outlook_infer`). `member_rankings` also feeds cross-league Trends
  aggregation ([server.py:8770](backend/server.py:8770), [:18634](backend/server.py:18634)),
  so re-keying it would attribute one person's board to another person's Sleeper id in
  community data. A co-owned team therefore reads to its leaguemates as having no board
  and no declared outlook unless the **primary owner** uses FTF. Honest degradation, not
  corruption; logged as a follow-up in `NEXT.md`.
- **Trust model unchanged.** `league_user_id` is client-asserted, exactly like the
  `user_id`, `user_player_ids` and `opponent_rosters` it arrives beside — a client that
  wanted to write another member's `league_members` row can already do so today via
  `opponent_rosters`. No new surface. Resolving server-side instead would add an
  uncached live Sleeper call ([`_sleeper_get`](backend/server.py:535) has no cache) to
  session_init's critical path; rejected on latency.

---

## 1. Analytics scope

- [x] **(b) Existing events cover it.** `league_synced` (S3, fired at session_init) and
  `signup`/`app_open` already record the league; nothing about co-ownership changes when
  or whether they fire, and none of their properties encode roster ownership.
- [ ] (a) new events — none.
- [ ] (c) waived — n/a, answered by (b).

One deliberate non-addition: no `is_co_owner` property. It would be a new taxonomy field
on a hot event for a population we cannot yet size, and the backend log line at
session_init records the resolution for debugging. Revisit if co-ownership turns out to
be common enough to segment on.

## 2. Schema & flag scope

- **New/changed tables or columns:** none. `league_members` keeps `(league_id, user_id)`;
  the change is *which* id is written, not the shape. → `docs/data-dictionary.md` n/a.
- **New/changed feature flags:** none. This is a correctness fix to a path that is
  already broken for the affected users; a flag would leave those leagues dead behind a
  default-off gate and doubles the states to test. Rollback is `git revert`.
- **New env vars / `model_config` keys:** none.
- **API surface:** `POST /api/session/init` gains two **optional, additive** body fields,
  `league_user_id` and `league_display_name`, both defaulting to the caller's own values.
  Omitting them reproduces today's behavior byte-for-byte, so old clients are unaffected.
  → `docs/api-reference.md` updated.

## 3. Test scope (mobile test platform)

- [x] **Backend pytest (primary):** `backend/tests/test_co_owner_rosters.py` —
  the resolution helper (owner match, co-owner match, `None`/absent/int-vs-str
  `co_owners`, no match), plus a session_init regression asserting that a co-owner's
  init writes **12** `league_members` rows with roster 3 keyed on `460238…` and the
  caller's `user_player_ids` non-empty. Fixture:
  `backend/tests/fixtures/sleeper/co-owned-league/rosters.json`, modeled on the real
  `co_owners` example in
  `backend/tests/fixtures/draft/ffv3-predraft/league/1312140920132497408/rosters.json`.
- [x] **Extended flow:** none needed — see waiver.
- [x] **WAIVED (Maestro):** no new screen, no new control, no changed copy, no new
  `testID`. The change is invisible on a sole-owned league (every existing flow's
  fixtures are sole-owned, and the assertion is that they stay byte-identical), and a
  Maestro flow cannot exercise the co-owned case without a co-owned fixture league —
  the hermetic harness seeds rosters from `FTF_SLEEPER_FIXTURES_DIR`, so the meaningful
  assertion lives in pytest against that same fixture, not in the UI driver.
  **Operator sign-off required on this waiver.**
- `testID`s added/renamed: none.
- **Capture delta:** none — no visual change.
- **Smoke-suite impact:** the sign-in → league-select → Trades path crosses
  `initLeagueSession`. Those flows run against sole-owned fixtures where the new code
  takes the `owner_id` branch, so they must stay green unchanged — that is the
  regression assertion for this surface.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | route-table row + new "§ `/api/session/init` — league identity (co-owned rosters)" |
| `living-memory/LLD.md` | updated | § Code Conventions — "A league-SHARED table is keyed on the team, not on whoever synced it": the two-identity rule and the exclude-by-`roster_id` corollary |
| `docs/architecture.md` | n/a | no module wiring change; one new leaf helper module (`backend/sleeper_roster.py`) with no new data flow |
| `living-memory/HLD.md` | n/a | no architectural shift — an identity is disambiguated, no new component or client |
| `docs/cross-client-invariants.md` | updated | new "§ Sleeper roster ownership — the co-owner predicate": three implementations + locations-to-change-together |
| `docs/glossary.md` | updated | **Co-owner**, **League identity** |
| ADR / `DECISIONS.md` | both | [ADR-012](../../adr/adr-012-co-owned-roster-identity.md) + `D-051`. `docs/adr/README.md` re-indexed (it was also missing ADR-011). |

## 5. Ship gate declaration

- **Simulator-gate tier: 2** — feature flow + affected smoke subset. Rationale: the
  change touches the session_init path every mobile launch runs, so the sign-in →
  league-select → Trades smoke subset must prove no regression on sole-owned leagues;
  there is no new feature flow to add (see the §3 waiver), so tier 2 collapses to the
  affected smoke subset plus the backend suite.
- Evidence: `living-memory/TEST_LEDGER.md` entry + `qa/sim-runs/last-sim-run.json`.
- Operator deviation from the matrix: none proposed.

## 6. Waivers requiring operator sign-off

1. **Maestro delta waived** (§3) — no UI-visible change and no co-owned fixture league in
   the mobile harness; covered by pytest against the fixture instead.
2. **No feature flag** (§2) — a correctness fix to an already-broken path; flagging it
   would keep affected leagues dead by default.
3. **`member_rankings` left account-keyed** (§0.3) — a co-owned team's board is invisible
   to leaguemates unless the primary owner uses FTF. Follow-up, not a blocker.
