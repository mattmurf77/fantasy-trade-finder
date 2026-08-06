# Tracking-plan addendum — Draft Room per-player actions (draft-extensions W1)

**Date:** 2026-08-06 · **Status:** adopted with the W1 build
**Parent:** [2026-07-17-tracking-plan-v2.md](2026-07-17-tracking-plan-v2.md) §S3
**Build:** [../../plans/draft-extensions/build-w1.md](../../plans/draft-extensions/build-w1.md) · plan §4 · lld §2.2
**Registries:** `backend/analytics_taxonomy.py` (`ALLOWED_CLIENT_EVENTS` + `CLIENT_EVENT_PROPS`)

The taxonomy is **default-deny**: an unregistered client event is counted and
dropped at ingest, and an allowlisted event with no `CLIENT_EVENT_PROPS` entry
raises at **import**. Both registries are required, and the name must not
collide with `SERVER_FIRED_EVENTS` (the disjointness assert refuses to import
on a collision, which crashes the app at boot). This addendum is the
tracking-plan precondition those registries' own comments demand.

## Why now

`draft.room` has been **true in prod** since the placement wave, and the Draft
Room emits **zero** `track()` calls. Not "few" — zero. The `draft-room.rank-rookies`
bridge row, the one link between rookie ranking and rookie drafting, has never
reported a single tap. W1's first deliverable (D0) is that the surface is
measurable at all; the row actions it adds are instrumented from birth rather
than retrofitted.

## Events

All four are **client**-fired from `DraftRoomScreen`, `screen: 'DraftRoom'`.

| Event | Props | Fired when |
|---|---|---|
| `draft_room_rank_rookies_tapped` | `state`, `from` | The bridge row is tapped. `state` = the board's own state (`upcoming`/`live`/`complete`/`unavailable`) — the row renders in **every** state, and pre-draft prep is exactly when the board has least to show, so the split matters. `from` = the host surface. **Unflagged** — this row shipped long before W1. |
| `draft_room_row_menu_opened` | `surface`, `player_id`, `valued`, `rank` | The long-press / a11y custom action opens the context menu on an undrafted row. `valued` mirrors the payload's `undrafted[].valued`; a `false` here is the exact case the anchor action exists for. `rank` is the row's cross-position undrafted rank — a domain value, not a list index. |
| `draft_room_action_taken` | `action`, `player_id`, `valued` | A menu row is chosen. `action` ∈ `set_value` \| `rank_rookies` \| `add_target`. |
| `draft_room_coverage_nudge_shown` | `unvalued_count`, `window` | The "N of the top 25 have no value on your board" nudge renders. `window` is the fixed top-N (25), sent explicitly so a later window change is visible in the data instead of silently re-basing the series. |

## What is deliberately NOT here

- **The anchor write itself.** `anchor_answered` stays **server-fired** and
  gains one prop, `via` ∈ `{anchors, draft_room}`, so "set a value on the fly
  in the draft room" is separable from a wizard pass. `CLIENT_EVENT_PROPS`
  filters client events only, so this needed no registry change — and keeping
  the write server-authoritative means the count of anchors set can never be
  inflated by a client.
- **A dedicated failure event.** A failed anchor save already emits
  `api_request_failed` from the shared client wrapper.

## Reading them

- **Did the bridge ever work?** `draft_room_rank_rookies_tapped` per Draft Room
  view, split by `state`. This is the number the placement mock's finding #2
  asserted without evidence.
- **Is the on-the-clock job real?** `draft_room_action_taken{action:set_value}`
  → server `anchor_answered{via:draft_room}`. The client event is intent; the
  server event is the write. A gap between them is a failure rate, not a
  preference.
- **Does the nudge do anything?** `draft_room_coverage_nudge_shown` →
  `draft_room_row_menu_opened{valued:false}`. If unvalued rows are opened at
  the same rate with and without the nudge, the nudge is decoration.

## Rollout

`draft.rank_inline` lands **OFF**, so the three action/nudge events fire for
nobody until it is flipped. `draft_room_rank_rookies_tapped` starts flowing
immediately — it instruments a row that is already live for every user with
`draft.room` + `ranks.rookie_subset` on.
