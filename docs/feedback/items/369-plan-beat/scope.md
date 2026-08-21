# Feature Scope — #369 the plan beat becomes the full adjustment surface

**Date:** 2026-08-20
**Entry point:** feedback #369 (operator `mattmurf77`, screen TeamReview)
**Builder:** agent-a7bed877f805980b0 (worktree off `origin/main` @ `bc43b6f`)
**Operator sign-off on waivers:** not needed (no waivers)

> *"The plan summary page only shows window.. it's a good page intent but needs more
> detail. I think we just show the full set of adjustments a user can make with the
> trade finder."*

---

## 0. What this actually is

The plan beat shipped as a **session receipt** — it rendered only what the user
changed during *this* mount, gated on a `useRef` set (`done.current`). Two
independent facts made that receipt render essentially one row:

1. **The positions write could never succeed.** The depth beat's footer posted
   `{acquire_positions, trade_away_positions}` with **no `team_outlook`**, and
   `POST /api/league/preferences` rejects a body without one
   (`backend/server.py:15788-15790`, `if not outlook or outlook not in valid: → 400`).
   `apiRequest` throws on non-2xx (`mobile/src/api/client.ts:553`), so the
   `await` in `savePrefs` threw, `done.current.add('positions_set')` on the next
   line never ran, the `catch` swallowed it, and no analytics event fired.
   `positions_set` has therefore **never** been true — so the plan beat could
   only ever show the window. The operator's report is a symptom of this, not
   only of the receipt design.
2. **The scoped partner was inert.** The partners beat set local state and
   emitted an event but never touched the #330 handoff store, so the plan beat's
   copy *"I've already pointed the finder at it"* was false.

The operator's words rewrite the page's job: not "what you just changed" but
**"every lever the trade finder has, and where you stand on each"**, sourced from
saved preferences rather than session-local React state.

## 0.1 Lever inventory (verified against `origin/main` @ `bc43b6f`, not guessed)

| # | Lever | Stored where | Reachable today | Plan-beat treatment |
|---|---|---|---|---|
| 1 | `team_outlook` (Window) | `league_preferences.team_outlook` (`backend/database.py:991`) | yes | **edit in place** |
| 2 | `acquire_positions` (Chasing) | `league_preferences.acquire_positions` | yes | **edit in place** |
| 3 | `trade_away_positions` (Shopping) | `league_preferences.trade_away_positions` | yes | **edit in place** |
| 4 | Untouchable players | `asset_preferences.list_type='untouchable'` | yes, flag `trade.preference_lists`=true | count, named home |
| 5 | Target players | `asset_preferences.list_type='target'` | yes, same flag | count, named home |
| 6 | Not-interested players | `asset_preferences.list_type='not_interested'` (#163) | yes, same flag | count, named home |
| 7 | Trade fairness | AsyncStorage `ftf:trades:fairness_on` (`mobile/src/api/tradePregen.ts:24`) | yes | value read, named home |
| 8 | Scoped trade partner | TradesScreen sheet state; crossed into via `useFinderTargets.setHandoff` (#330) | yes, flag `trades.sheet_targeting`=true | value shown **and now actually applied** |
| 9 | Trade idea / intent | `TradesScreen` `useState` (`:512`), sent as `trade_intent` | yes, flag `trades.intent_modes`=true | named, home named (unreadable from here) |
| 10 | Focus / lane filter | `TradesScreen` `useState` (`:506`) | yes (deck-dependent) | named, home named (unreadable from here) |
| 11 | Pinned specific players + package mode | `useFinderTargets` zustand, session-only | yes | count read from the store |
| 12 | Active league | session | yes | out of scope — the whole review is league-scoped |

**`trade.avoid_positions` is NOT on `origin/main`.** `git grep avoid_positions`
over tracked files hits exactly one line — the plan doc that names it
(`docs/feedback/items/364-team-review-fixes/plan-remaining.md:106`). It lives on
`feat/jon-360-362` and nothing in `backend/` or `mobile/` references it. The
"Chasing / Shopping" block is laid out as a labelled position line per direction
precisely so a third "Avoiding" line drops in as one more `PosLine` when that
branch lands — **no dependency taken on it**.

## 0.2 Build decision: hybrid — in-place editing for 1–3, display + named home for the rest

The parent asked for the live view with edit affordances and told me to say so if
in-place editing turned out materially riskier for part of the surface. It does,
and the line is sharp:

- **Levers 1–3 are edited in place.** They are exactly what the flow already
  writes, through the existing `saveLeaguePreferences` → `POST /api/league/preferences`
  path. Zero new write surface, and the same autosave-per-tap contract Trade DNA
  already uses (#236). This is also what repairs the reported defect for a user
  who *skipped* the window or depth beat: the plan beat is now where they can
  still set it.
- **Levers 4–11 are shown, not edited.** Editing them from here would mean
  either a second writer for `asset_preferences` (4–6, duplicating the deck's
  lock/target/not-interested toggles) or writing into another screen's React
  state across a navigation boundary (7, 9, 10, 11), which is not possible
  without inventing a shared store — a new cross-screen state layer for a
  closing beat. Both are materially riskier than naming the lever and where it
  lives, and neither is what the operator asked for.

The one exception is **lever 8**: the plan beat does not edit it, but its footer
now *applies* what the partners beat already recorded, via the existing #330
handoff store — the mechanism `LeagueSummaryScreen:1193` already uses. That is a
correction to a false claim in shipped copy, not a new lever.

Result: **every** lever the finder exposes is on the page, the three the flow
owns are adjustable there, and nothing is invented.

---

## 1. Analytics scope

- [x] **(b) Existing events cover it.** `team_review_action_taken`
  (`backend/analytics_taxonomy.py:1140`, props `{league_id, beat, action}`) is
  reused verbatim with the existing `action` values `outlook_set` and
  `positions_set`. The `beat` property is already `plan` when the emit fires
  from this beat, so plan-beat edits are separable in the funnel without a new
  event name and without a new `action` string. `team_review_exited{outcome}`
  remains the terminator.
  Question it answers: *"do users adjust their levers on the closing beat, and
  which ones?"* → `team_review_action_taken WHERE beat='plan' GROUP BY action`.
- **No taxonomy or `NON_INTENT_EVENTS` change.** The taxonomy comment block at
  `analytics_taxonomy.py:413-423` warns that splitting a series is harmful; a
  `team_review_plan_edited` peer would split `team_review_action_taken` exactly
  that way.
- **A behavioural note, not a change:** `positions_set` has never once fired in
  production (see §0.1); repairing the write means this series starts producing
  data now. Reading its history as a baseline would be wrong.

## 2. Schema & flag scope

- New/changed tables or columns: **none**. No schema touched; `docs/data-dictionary.md` n/a.
- New/changed feature flags: **none**.
  **Flag call, stated per the constraint:** every change here is confined to the
  `plan` beat and its footer, inside a screen that only mounts under the
  already-lit `trades.team_review`. The `savePrefs` `team_outlook` backfill is in
  `TeamReviewScreen.tsx` and reached only from that screen. Nothing outside the
  Team Review flow changes behaviour for anyone, so **no new default-OFF flag**.
  `trades.team_review` itself remains the kill switch: off ⇒ the route 404s, the
  screen is unregistered, and none of this code is reachable.
  Read-only flag *consumption* is added: `trade.preference_lists` (gates the
  player-rules card) and `trades.intent_modes` (gates the trade-idea row), so a
  lever that is dark is not advertised.
- New env vars / `model_config` keys: **none**.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-team-review.js` extended from 7
  to 13 assertions (existing 1–5c untouched). New: 6 (plan beat reads saved
  prefs, not the session ref), 7 (plan beat never gates a lever on
  `done.current`), 8 (every inventoried lever appears on the beat), 9 (no second
  `asset_preferences` writer), 10 (`savePrefs` always sends `team_outlook`), 11
  (the plan footer hands the scoped partner to the #330 store). Every one
  sabotage-proven — table in `code-walk.md` §6.
- [x] **Unit tests:** backend `backend/tests/test_team_review.py` unchanged — no
  backend code changed. One test added to
  `backend/tests/test_league_prefs_authz.py`?  **No** — see the waiver below.
  **Why none:** the contract this build depends on (`POST /api/league/preferences`
  rejects a body with no `team_outlook`) is already asserted by the route's own
  400 branch and exercised by `backend/tests/test_league_prefs_authz.py`; adding
  a test for a backend behaviour nothing changed would be coverage theatre. The
  *client's* obligation to send the field is what regressed, and that is pinned
  by structural assertion 10, which is where the bug actually lived.
- [x] **Code-walk proof:** `docs/feedback/items/369-plan-beat/code-walk.md`,
  file:line cited throughout — including the 400-then-swallow trace that is the
  root cause.
- [x] **Manual TestFlight checklist:**
  `docs/feedback/items/369-plan-beat/testflight-checklist.md` — 9 numbered steps.
  Runtime proof genuinely matters here: the central claim ("the beat shows what
  is actually saved") is a network read whose failure mode is a *stale but
  plausible* page, which no static check can see.
- `testID`s added: `team-review.plan.levers`, `team-review.plan.assets`,
  `team-review.plan.search`, `team-review.plan.save-error`,
  `team-review.plan.outlook.<option>` (×5), `team-review.plan.chase.<POS>` (×5),
  `team-review.plan.shop.<POS>` (×5). None renamed, none removed —
  `team-review.beat.plan` and `team-review.finish` are unchanged, so
  `check-team-review.js` assertion 4 keeps its grip. Passes `mobile/scripts/testid-lint.sh`.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route added, renamed, removed, or contract-changed. The beat *reads* `GET /api/league/preferences` and `GET /api/league/asset-prefs` and *writes* `POST /api/league/preferences` — all three exactly as documented today, with the documented body. |
| `living-memory/LLD.md` | n/a | No schema, route, or invariant convention shifted. |
| `docs/architecture.md` | n/a | No module wiring or data-flow change; one existing client screen reads two existing endpoints. |
| `living-memory/HLD.md` | n/a | No new module, client, or major flow. |
| `docs/cross-client-invariants.md` | n/a | No shared constant, enum or colour introduced. The outlook enum, position strings and `asset_prefs` list names are consumed as-is. |
| `docs/glossary.md` | n/a | No new domain term — "window", "chasing", "shopping", "untouchable", "target" all already defined. |
| `DECISIONS.md` entry | **updated** | D-130 (the plan beat is a standing summary, not a receipt) and D-131 (hybrid edit surface: `league_preferences` in place, everything else named-not-edited). |
| `mobile/src/screens/CLAUDE.md` | **updated** | The `TeamReviewScreen` row's plan-beat description was wrong after this change. |
| `docs/feedback/items/364-team-review-fixes/plan-remaining.md` §3 | **updated** | Its diagnosis was incomplete — it attributed the symptom to the receipt design alone and did not know the positions write was 400ing. Corrected in place with a pointer here. |

## 5. Ship gate declaration

- **CI green on this worktree:** `python3 -m pytest backend/tests -q` →
  3606 passed, 1 skipped · `tsc --noEmit` → clean · all 64 `mobile/tests/check-*.js`
  → pass · `mobile/scripts/testid-lint.sh` → OK. Counts and the sabotage table
  are in `living-memory/TEST_LEDGER.md`.
- **Evidence recorded:** TEST_LEDGER entry dated 2026-08-20.
- **TestFlight verification:** checklist written (§3); operator to run, outcome
  to be logged in TEST_LEDGER. **Requires a client release** — this is mobile
  code and is not in any existing build.
- Express lane declared by the operator? **no** — full gates.
