# Status — analytics instrumentation agent, #297 / #298 / #299 / #302

**Date:** 2026-08-11
**Branch / worktree:** `feedback-integration-v2` @ `.claude/worktrees/integration-v2`
**Base:** `origin/main` @ `f65bab7` + `feedback-build-trades-297-298` + `feedback-build-league-299-302` (merge commits `2837696`, `96b41cc`)
**Tracking plan:** [`analytics.md`](analytics.md) — read that first; this file is the delta owed to files I do not own.

---

## 1. Commits

| sha | What |
|---|---|
| `02dea98` | taxonomy: 2 event names + 3 props; `NON_INTENT_EVENTS` guard in the same commit |
| `a5f4168` | `#297` client emitter (`InLeagueCalculator.tsx`) |
| `6a22f49` | `#299/#302` client exit choke point (`LeagueSummaryScreen.tsx`) + 2 repointed regexes in `check-league-drill-in.js` |
| `73332e0` | `#298` `mode` prop on 3 emitters (`TradesScreen.tsx`) |
| `35303a9` | backend round-trip tests (`test_events_api.py`, +4 tests) |
| `997ba05` | client↔taxonomy cross-check test (`check-analytics-297-302.js`, new) + npm script |
| `3614a58` | tracking plan + both scope §1 rewrites |
| — | this file |

Files touched, all within stated ownership: `backend/analytics_taxonomy.py`,
`backend/analytics_queries.py`, `backend/tests/test_events_api.py`,
`mobile/src/components/InLeagueCalculator.tsx`,
`mobile/src/screens/LeagueSummaryScreen.tsx`,
`mobile/src/screens/TradesScreen.tsx`,
`mobile/tests/check-league-drill-in.js`,
`mobile/tests/check-analytics-297-302.js`, `mobile/package.json`,
`docs/feedback/items/**`.

`backend/analytics_ingest.py` was **not** touched — no ingest change was required.

### Taxonomy edits are strictly additive

| Edit | Shape |
|---|---|
| `ALLOWED_CLIENT_EVENTS` | two names **appended** after `outlook_strip_toggled`; no existing entry moved or reformatted |
| `CLIENT_EVENT_PROPS` | two entries **appended** after `outlook_strip_toggled` |
| `CLIENT_EVENT_PROPS["find_trades_tapped"]` | `frozenset()` → `frozenset({"source", "mode"})` — **a shipped entry widened.** Called out loudly per instruction. No key removed. Justification: `source` was already being sent and silently popped; see `analytics.md` §4. |
| `CLIENT_EVENT_PROPS["trade_card_viewed"]` | `+"mode"` — **a shipped entry widened.** No key removed. |
| `NON_INTENT_EVENTS` | two names appended inside the existing frozenset |

No other branch's block was reordered or reformatted. `SERVER_FIRED_EVENTS`,
`FUNNEL_CRITICAL`, `OBS_EVENT_PROPS` and the import-time asserts are untouched.

---

## 2. Proposed text for shared docs (orchestrator-owned — I did not edit these)

### 2a. `docs/cross-client-invariants.md`

**Edit 1** — in the client-event list, append to the **Trades** bullet
(currently line ~348) so the widened props are visible where the names live:

> - Trades: `find_trades_tapped`, `trade_card_viewed`, `trade_flagged`, `match_opened`. **`find_trades_tapped` and `trade_card_viewed` both carry `mode` ∈ `single_pin` | `deck`** (#298, 2026-08-11) — the pinned-surface discriminator; a `find_trades_tapped{mode:single_pin}` with no following `trade_card_viewed{mode:single_pin}` is #298 reappearing. `find_trades_tapped` also carries `source` ∈ `prefs_changed_strip` | `deck_error_retry` | absent, which the client had been sending since #257 into an empty prop registry that popped it on every row.

**Edit 2** — add a new bullet block after the P0-remediation block
(currently ends line ~358):

> - **Feedback #297/#299/#302 batch (2026-08-11 — [addendum](feedback/items/297-lineup-impact-single-pin/analytics.md)); mobile only:**
>   - Calculator: `lineup_impact_unavailable` — the honest-empty "Starting lineup" row impression. `platform` is the **LEAGUE** platform (`sleeper` | `espn` | `mfl` | `fleaflicker` | `unknown`), read from the session league cache. **Never inferred from the league id's shape: ESPN and MFL league ids CAN be numeric** (MFL `990062846` is live in this project's DB), so an `isdigit()` read labels them `sleeper`. `_sleeper_lineup_slots`' docstring implies otherwise and is wrong — those leagues fail at the meta-fetch gate, not the digit gate.
>   - League drill-in: `league_team_closed` — the EXIT half. The ENTER half is **`league_team_opened` (P0-7, above), reused unchanged**; there is deliberately **no** `league_team_focused` / `league_team_unfocused` pair, because two events for one interaction on this screen is the two-sources-of-truth bug #208/#248/#293 are a catalog of. `via` is a closed 5-value enum, one per exit control: **`header_back` | `in_card_link` | `hardware_back` | `tab_retap` | `refocus`**. Adding an exit control means adding a value here **and** a `closeTeam('<via>')` call — the screen's single choke point, pinned by `mobile/tests/check-analytics-297-302.js`. A `league_team_opened` with no matching close is "abandoned by navigating away", measured by absence on purpose.

**Edit 3** — append to the existing "INTENT is a deny-list" paragraph
(currently line ~364):

> `lineup_impact_unavailable` (impression) and `league_team_closed` (terminator/dismissal, like `quickset_abandoned`) are classified **non-intent** for the same reason, added in the same commit as their allowlist entries. `league_team_opened` **stays intent** — the enter half is the value moment and already counts the user once, which is exactly why admitting its terminator too would only ever add user-days where the opener was lost to queue overflow.

### 2b. `docs/api-reference.md`

**n/a.** No route added, renamed, removed or contract-changed. The
`POST /api/events` row already describes the always-200 accepted-and-dropped
contract; event names are not enumerated there (`analytics_taxonomy.py` is
the source of truth) so no row changes.

### 2c. `docs/config-reference.md`

**n/a.** No env var, feature flag or `model_config` key added or changed.
Neither new event is flag-gated — `lineup_impact_unavailable` rides a copy
change that shipped unflagged, and `league_team_closed` rides navigation
controls that must not be flag-gated (a back button behind an off flag is a
state with no exit).

### 2d. `mobile/src/screens/CLAUDE.md`

Append to the **Sharp edges** list:

> - `LeagueSummaryScreen`'s drill-in has exactly **one** `setSelectedId(null)`, inside `closeTeam` — every exit control (header back, in-card link, Android hardware back, active-tab re-tap) routes through it, and `openTeam` emits `via:'refocus'` when jumping team-to-team. A control that clears focus directly disappears from analytics while the UI keeps working. Pinned by `mobile/tests/check-analytics-297-302.js`.

### 2e. `mobile/src/components/CLAUDE.md`

Amend the `InLeagueCalculator` row's description:

> `InLeagueCalculator` | Calculator "In league" mode: real opponent/rosters, two-board verdict, eveners, lineup before/after, prefill. Fires `lineup_impact_unavailable` when the server omits `starter_impact` and both sides carry players; `platform` is read from the session league cache, never from the league id's shape.

### 2f. `living-memory/DECISIONS.md` — proposed new entry

> ### D-<next> — Adopt `league_team_opened` for the League drill-in; add only an exit event (2026-08-11)
>
> **Context.** Feedback #299/#302 needed the drill-in measured. A prior round, working against `origin/main` @ `ab9368f`, found no event covering the drill-in and specced a `league_team_focused` / `league_team_unfocused` pair. Between that check and its ship, `main` advanced 21 commits and the P0-7 remediation round registered 17 client events, including `league_team_opened` — fired from the single `openTeam` helper both drill-in entry points route through, with the same bar-vs-row `via` the new pair proposed re-minting.
>
> **Decision.** Adopt `league_team_opened` unchanged as the enter half. Add exactly one new name, `league_team_closed {via, dwell_ms, rank}`, for the exit — which genuinely had no signal, because the drill-in is component state and emits no `screen_left`. Do **not** mint a focused/unfocused pair.
>
> **Consequences.** One interaction has one enter event and one exit event. All five exit controls route through a single `closeTeam` choke point and the file has exactly one bare `setSelectedId(null)`; both are statically pinned, so a new exit control that forgets to fire fails CI rather than silently vanishing from the data. `league_team_closed` is NON-INTENT (added in the same commit as the allowlist entry) — the opener already counts the user, so admitting the terminator could only add user-days where the opener was lost to queue overflow. Abandonment (opened, never closed) is measured by absence; there is deliberately no unmount-cleanup emitter, which would double-fire on React strict-mode remounts and invent dwell.
>
> **Meta-consequence worth generalising:** an instrumentation gap analysis is only valid against the `origin/main` the work will land on. Two of this batch's premises were true when checked and false when shipped.

### 2g. `living-memory/CHANGELOG.md` — proposed entry line

> **Analytics — #297/#298/#299/#302 instrumentation.** Two new client events (`lineup_impact_unavailable`, `league_team_closed`), three new props (`mode` on `find_trades_tapped` + `trade_card_viewed`, `source` on `find_trades_tapped` — the last a bug fix for a prop the client had been sending into an empty registry since #257). Both new names guarded in `NON_INTENT_EVENTS` in the same commit, so no DAU/WAU seam. The League drill-in adopts the shipped `league_team_opened` rather than minting a duplicate enter event; the `league_team_focused`/`unfocused` pair proposed on `feedback-integration-297-302` was discarded. Deploy-then-probe gate owed before any report reads these names.

### 2h. `living-memory/TEST_LEDGER.md` — proposed entry

> **2026-08-11 — #297/#298/#299/#302 analytics.** `pytest backend/tests` 2452 passed / 1 skipped. `tsc --noEmit` clean. `testid-lint OK`. `check-league-drill-in.js` 30/30 (count unchanged; two regexes repointed at the new choke point). `check-analytics-297-302.js` new, all pass, **12 executed sabotage proofs**. `test_events_api.py` +4 tests, **8 executed sabotage proofs**. `check-single-pin-actions.js` 4 PASS / 4 FAIL — **pre-existing and unchanged by this work**; #169 moved `trades.pass-btn`/`trades.like-btn` into `TradeCard.tsx` and the test's file assumption is stale (owned by the trades build agent). **No simulator / Maestro run** — static verification only.

### 2i. `docs/glossary.md` — proposed entries

> **drill-in (League)** — the focused-team state of `LeagueSummaryScreen`: component state (`selectedId`), not a stack push, so it produces no navigation or `screen_left` event. Entered via `league_team_opened`, left via `league_team_closed`.
>
> **exit choke point** — a single helper every control that ends an interaction must route through, so the interaction's terminating event cannot be forgotten by a new control. `closeTeam` in `LeagueSummaryScreen.tsx` is the reference implementation.

---

## 3. Owed at ship — do not skip

1. **Deploy-then-probe** (`analytics.md` §7). After merge and deploy, before any
   dashboard, report or experiment reads these names: one hand-rolled
   `POST /api/events` per new name with its **full** property set, asserting
   `dropped == 0` **and** every property echoed back from `user_events.props`.
   Assertion 1 alone is insufficient — an unknown prop is popped while the
   envelope still reports `dropped: 0`. **Not run here; needs a deploy.**
   Do not substitute `GET /api/admin/analytics/health`: its counters are
   in-process and reset on deploy, so "counters stayed flat" is not evidence.
2. **CI wiring gap (pre-existing, not caused here).** None of the ten
   `mobile/tests/check-*.js` invariant tests run in `.github/workflows/ci.yml`
   — they are `npm run`-only, so `test:analytics-297-302` and
   `test:league-drill-in` are only as good as someone remembering to run them.
   `ci.yml` is shared this batch so I did not edit it. Proposed job:
   `- run: cd mobile && npm ci && npm run test:analytics-297-302 && npm run test:league-drill-in`.
3. **Maestro / simulator.** No flow delta owed by this agent — no event here
   adds a user-visible control. The #298 and #302 flows authored by the build
   agents already traverse every emitter's trigger.

## 4. Known-failing test I did not touch

`node mobile/tests/check-single-pin-actions.js` → **4 PASS / 4 FAIL**, the same
count as before my changes (verified before and after every commit).
Cause is understood and is not mine: it asserts `trades.pass-btn` /
`trades.like-btn` live in `TradesScreen.tsx`, but #169 moved them into
`TradeCard.tsx`. The behaviour is correct; the test's file assumption is stale.
The trades build agent owns the fix.
