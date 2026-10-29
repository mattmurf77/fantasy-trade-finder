# Tracking-plan addendum — Sleeper app hand-off (2026-10-28)

**Status:** granted by analytics-lead on 2026-10-20 under conditions G1–G7, widened @ `8b63ef10`. Registered in `backend/analytics_taxonomy.py` in the same commit as the emitter (`mobile/src/utils/sleeperHandoff.ts`, `trackHandoff`), on `feat/sleeper-handoff-resolved`, stacked on #379. analytics-lead reviews this addendum in that PR. Rows start with the first iOS build that carries the branch, and only while `analytics.client_events` is on.

Source: #351's PRD §3.2 (`origin/plan/sleeper-fa-deeplink:docs/plans/sleeper-fa-deeplink/prd.md`) and #379's scope ([external-links/scope.md](../../plans/external-links/scope.md) §1).

## Questions this event answers

1. **Does the hand-off land in Sleeper?** `outcome` per `surface`: `app` (the `sleeper://` open resolved) vs `not_installed` (it rejected, and the "Sleeper isn't installed" alert showed). With the operator plus about 2 testers on TestFlight this is a smoke signal, not a metric (#351 PRD).
2. **How often does the D2 alert show?** The `not_installed` share is how often a user with no Sleeper app tapped a Sleeper control.
3. **How many Free Agents claims are handed off, and with a drop?** On the claim sheet this event is the only record of the tap: `ClaimSheet.tsx` and `FreeAgentsScreen.tsx` emit nothing else. `has_drop` says whether the user picked a player to drop first.
4. **How deep does the hand-off land?** `rung`. Every target ships `bare` today (`SLEEPER_PROVEN_RUNGS`), so every row says `bare` until device tests prove a deeper rung. The value is the rung the app actually opened, so a later config change shows up in the series with no event change.
5. **Adds vs trades.** `target` splits claim hand-offs from trade hand-offs. On `send_button`, the trade intent itself is already counted by `sleeper_send_attempted {has_target: false}`; this event adds only the outcome.

## Event

| Event | Class | Properties | Fires when |
|---|---|---|---|
| `sleeper_handoff_resolved` | **INTENT** | `surface` (`free_agents` \| `usage_trends` \| `send_button` \| `trade_queue`), `target` (`add` \| `trade`), `rung` (`add` \| `player` \| `players_tab` \| `league` \| `bare` \| `trade` \| `trades_tab`), `outcome` (`app` \| `not_installed`), `has_drop` (bool; see below) | The `sleeper://` open of a Sleeper hand-off settles. Once per hand-off |

Every value set is closed. `CLIENT_EVENT_PROPS` constrains keys only, so the enums live in its comment, in this addendum, and in `mobile/tests/check-sleeper-handoff-event.js`, which fails on a value outside them.

- **`has_drop`** rides only on a `target=add` row off `send_button`, and only when the caller passes it. The claim sheet passes it (league-eng, #509). It is **omitted, never `null`,** on `send_button` and on every `target=trade` row (G2): an absent key is the house pattern, and a `null` prop is ambiguous.
- **One per hand-off.** A Send All of N queued trades is one hand-off, so it is one event (`trade_queue`). A re-tap while an open is in flight gets the in-flight promise back and adds no open and no event.
- **Emits nothing:**
  - ESPN and MFL opens (they never reach `openInSleeperApp`);
  - a Sleeper hand-off whose surface is `unspecified` (the caller named none);
  - `target: 'league'`. It is in the helper's type (#351 PRD §3.2) but not in the granted `target` set, and nothing calls it today.
- **Not in the event:** no player id, player name or league id (G5). Client rows have a NULL `league_id` column (`analytics_ingest.py:467`). If a per-league cut is wanted later, it is a prop added then. No device `platform` prop: that is the envelope column.

## Definitions

**`not_installed` means "`Linking.openURL('sleeper://…')` rejected" (G4).** The client never calls `canOpenURL` (#351 PRD F8: it rejects for any scheme missing from `LSApplicationQueriesSchemes`, and the build adds no plist entry). So the value is the rejection, not a verified install state. In practice it is "no app on this phone handles `sleeper://`": Sleeper not installed, or offloaded.

**`app`** means the open resolved: iOS handed the URL to Sleeper. It does not say what Sleeper showed, or whether the user finished the add or trade there.

## Why INTENT, and not WAT

- Every firing follows a deliberate CTA tap.
- On the Free Agents claim sheet it is the only record of that tap.
- The `sleeper_send_*` family is the precedent: the outcome of a deliberate act stays INTENT, failure included.

So there is no `analytics_queries.NON_INTENT_EVENTS` row. It is **not** a WAT event: an FA add is not a trade opinion, and the `send_button` trade intent is already counted by `sleeper_send_attempted`.

## Timing and the residual undercount (G3)

The event fires **synchronously in the `openURL` settle handler**, before the D2 alert, with no further `await`:
- `openExternal.ts:92-94`: the scheme open settles and `onSchemeSettled` runs at once;
- `sleeperHandoff.ts:119` → `trackHandoff` `:132-149`.

`track()` persists the queue on enqueue (`mobile/src/api/events.ts:219`) and flushes on background (`:146-148`), so the switch to Sleeper doesn't lose a queued event.

**Residual bias:** if iOS suspends FTF's JS before the `openURL` promise settles, and then kills the app, that hand-off is never recorded. This slightly **undercounts `outcome=app`**. `not_installed` is not exposed the same way: a rejected open leaves FTF in the foreground.

## The seam

The event is new. **There is no history before ship** and no backfill. Each surface's series starts when its caller migrates to `openInSleeperApp`:

| Surface | Starts with |
|---|---|
| `send_button` | #379 and this branch. It fires only on #351's state A (no league or opponent id), which has no deterministic UI trigger (#351 §3.1). |
| `free_agents`, `usage_trends` | league-eng's claim-sheet migration (#509, stacked on #379) |
| `trade_queue` | trades-eng's `useTradeQueue` Send All migration. The queue is behind `trades.queue_2k`, dark today |

A first non-zero week on a surface is a migration landing, not a behaviour change.

## Not tracked

- **`external_link_opened`** (eng-external-links §4.7) is **not granted**. Its `platform` prop would also collide with the envelope column.
- **The D2 alert's buttons** (Get Sleeper / Cancel). Whether a `not_installed` user goes on to the App Store is not measured.

## Privacy (G7)

**Delta: none.** No new data category, only product interaction. No identifiers ride in props.
