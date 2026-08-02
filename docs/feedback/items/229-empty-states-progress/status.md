# #229/#230/#234 — Empty states lead with value; one progress module owns every unlock

**Status: built (worktree branch `worktree-agent-af4b9c0445be5f5a5`, pending merge) — 2026-08-02. Ships live, no feature flag.**

Covers three findings:
- **#229** — League home's zeros are honest but demotivating; lead with solo value.
- **#230** — ranking is the foundation; incomplete ranking should be prominent and motivating.
- **#234** — say plainly what leaguemates ranking unlocks ("X of 12 ranked → unlocks Y").

Approved mock: `mockups/polish-lab-2026-08/empty-states-progress-v3.html`
(COMBINED layout — v2's action row + in-section buttons folded together),
with one operator tweak on top of v3: **the in-section buttons are BOTH
solid ice** (v3 drew the in-section "Rank players" as outlined-secondary).
The top action row keeps v3's treatment exactly: Rank players LEFT /
outlined-secondary, Find a trade RIGHT / solid ice.

## What was built

| Piece | File |
|---|---|
| `LeagueProgressModule` (full + `compact` variants) | `mobile/src/components/LeagueProgressModule.tsx` (new) |
| League home low-activity layout + zero-folds + "Works right now" | `mobile/src/screens/LeagueScreen.tsx` |
| Matches mutual empty state (shared module, new copy/CTA) | `mobile/src/screens/MatchesScreen.tsx` |

### League home (low-activity) section order — per the v3 mock

League hero card → **action row** (Rank players | Find a trade) →
**Explore rows** → **League progress module** → **"Works right now"**
card. (Activity feed, when its flag is on, keeps its slot after Explore;
returned zero-sections re-enter at their classic positions.)

### League progress module

- **Ring** = positions ranked 0–4. A position counts once its trio
  interaction count clears `/api/rankings/progress`'s threshold **or** it
  has saved tiers (`/api/tiers/status` — Quick set and Tiers commit through
  the same save contract); `progress.unlocked` (manual method + the
  monotonic unlock floor) short-circuits to 4/4. Deviation from the mock:
  the in-ring 8px "positions" caption violates the 11px type floor
  (design-system rule, teardown S2 PRD-04), so the caption renders OUTSIDE
  the ring as a standard 11px label ("Positions ranked") above the
  in-section CTA.
- **Segmented bar** = one 8px slot per team (`summary.total_teams`,
  fallback `leaguemates_total + 1`); ice slots = you + each leaguemate with
  stored rankings (`/api/league/coverage` `ranked`). Label
  `N/M (you)` — you are counted and labeled honestly, per the mock.
- **Unlock line** = `"X more ranked leaguemates unlocks mutual matches —
  trades both sides already like."` X = `max(0, 2 − rankedLeaguemates)`,
  hidden at 0. The threshold **2 ranked leaguemates** is mock-anchored
  (mock state: 0 ranked leaguemates → "2 more") and consistent with the
  fold line: you + 2 = the 3 ranked members `/api/league/contrarian`
  requires.
- **Invite leaguemates** (ghost) = OS share sheet with the same referral
  URL `InviteLeaguematesBanner` builds (`?league=<id>&ref=<username>`).
- **Fold line** (only while contrarian/leaderboards are folded):
  "Leaderboards and contrarian ranks appear here once 3 leaguemates have
  ranked." — states the backend's real 3-ranked-members threshold.

### Zero-row collapse / return conditions (wired, per section)

A section folds **only once its own data confirms it is empty** (loading
or error ⇒ render as today — a possibly-populated section is never
hidden), and returns automatically the moment its counts move:

| Section | Folds when | Returns when |
|---|---|---|
| Matches tiles | summary loaded ∧ `matches_mutual = 0` ∧ `matches_awaiting = 0` | either count > 0 |
| Hero "joined" chip | summary loaded ∧ `leaguemates_joined = 0` | ≥ 1 joined |
| Coverage card | coverage loaded ∧ `ranked = 0` | `ranked` > 0 |
| Contrarian ranks | server `insufficient_data = true` (needs 3 ranked members) | server returns data |
| Leaderboards (league + global) | same `insufficient_data` flag | same |

Note: folding the hero joined chip makes the FB-38 members overlay
unreachable while 0 leaguemates have joined — accepted (the overlay would
only list "Not joined" rows; the module's Invite action covers the useful
verb; the chip and overlay return the moment anyone joins). Folding the
Leaderboards section also hides the (populated) GLOBAL board in the
day-one state — deliberate, per the approved mock's proposed layout; it
returns with the league board at the 3-ranked-members threshold.

### Populated-state rule (chosen + documented)

- **Progress module + action row** render while ANY unlock is outstanding:
  ring < 4/4, OR no matches yet (both counts 0), OR contrarian/leaderboards
  locked (`insufficient_data`). Once all three are live the module and
  action row disappear entirely — nothing left to unlock — and the page
  renders **exactly today's populated layout**. ("Compact vs hide": hide
  was chosen; a completed checklist is dead weight.)
- **"Works right now" card** renders only while the league has no real
  matches (both counts 0) — the moment a real match exists, the example
  retires (an EXAMPLE trade next to real ones is noise).

### "Works right now" card

Flare label **EXAMPLE — NOT FROM YOUR LEAGUE** (flare = informational
highlight, ADR-005), two-column You send / You get rows with position
rails, and the **real `TradeValueBar` component** with static props
(`favors: 'receive'`, `gap: {value: 380, firsts: 0.6, pick_equivalent:
Mid 2nd}`) → renders the genuine "You win / by +380 · a Mid 2nd
(≈ 0.6 firsts)" verdict language. In-section CTA is a solid-ice
"Find a trade" (operator tweak) → Trades hub (`TradesHome`).

### Matches mutual empty state

Title "No mutual matches yet" (league-filtered variant keeps
"No matches in <league> yet"), mechanic-explaining body, always-on
solid-ice **Find a trade** primary (→ Trades hub), the **compact
progress module** (bar + short unlock line; active league only — hidden
when a different league's filter chip is selected or league data hasn't
arrived), ghost Refresh, and the flag-gated "How matching works" link.

Documented decisions vs. prior flags/mock:
- The S4 PRD-05 (`ux.empty_state_ctas`) "Go to Trades" primary on THIS
  state is superseded by the always-on "Find a trade" (same destination
  family; testID `matches.go-to-trades` kept so existing flows pass). The
  **awaiting** segment's empty state is untouched and still honors the flag.
- The mock drops "Refresh" ("pull-to-refresh covers it") — **kept as a
  ghost** here because the empty state is a plain centered View with no
  scroll, so pull-to-refresh cannot cover it. Documented deviation.

## testIDs (registered in `mobile/src/components/CLAUDE.md`)

`league.progress-module` · `league.works-now` · `league.action.rank` ·
`league.action.find` · `matches.progress-module` (+ `matches.empty-text`
copy change, `matches.go-to-trades` relabeled).

## Verification

- `cd mobile && npx tsc --noEmit` — clean (2026-08-02).
- Backend untouched — no server code or schema changes (pytest not run;
  nothing in `backend/` changed).

## Data sources (no new endpoints)

`/api/league/summary` (match counts, joined, total teams) ·
`/api/league/coverage` (ranked leaguemates) · `/api/league/contrarian`
(insufficient_data — fold authority for contrarian + leaderboards) ·
`/api/rankings/progress` + `/api/tiers/status` (positions ring). Matches
reuses LeagueScreen's react-query keys, so the module is usually cache-fed.
