# Tracking plan — bell inbox instrumentation

> Companion to [`scope.md`](scope.md). Referenced by the inline comments in
> `backend/analytics_taxonomy.py` and `backend/analytics_queries.py`.
>
> **Registration lands before any emitter.** The registry is default-deny behind
> a 200 (`analytics_ingest.py:404` scrubs unregistered props; an unregistered
> `event_type` is dropped entirely), so a name that arrives after its `track()`
> call is silent, unrecoverable loss with a success-shaped response.

## Contents

- [1. Why these three](#1-why-these-three)
- [2. Event specs](#2-event-specs)
- [3. Classification](#3-classification)
- [4. The `surface` enum extension](#4-the-surface-enum-extension)
- [5. Measurement caveats](#5-measurement-caveats)

---

## 1. Why these three

`mobile/src/components/TopBar.tsx` has **zero** `track()` calls today. The bell
has never been measured: open rate, tap rate and per-type tap rate are all
unknown and none of it is recoverable retroactively. Every claim about which
notification types earn a slot in the inbox is currently a guess.

`notif_row_tapped{type}` is the load-bearing one. Without `type` the exercise
that produced this build repeats in six months on the same absence of evidence.

## 2. Event specs

### `notif_inbox_opened`

| | |
|---|---|
| **Fires** | the bell sheet opens (`openSheet`), once per open |
| **Client** | mobile only |
| **Screen arg** | `'TopBar'` — the bar is global, above the tab navigator, so no single route owns it |
| **`unread_count`** | int ≥ 0. The badge count **at the moment of the tap**, read before `markAllRead()` runs. Reading it after is always 0 |
| **`row_count`** | int ≥ 0. Rows in the store at open time. This is the **pre-hydration** count — the server fetch is async and lands after |

`row_count` being pre-hydration is a deliberate honesty choice: the alternative
is firing after the network settles, which loses every open that happens
offline or while the fetch is in flight. Read it as "rows the user saw
immediately", not "rows the server holds".

### `notif_row_tapped`

| | |
|---|---|
| **Fires** | a row is tapped, **before** the routing decision |
| **Client** | mobile only |
| **`type`** | the row's `data.type` string, verbatim — `''` if the row carries none |
| **`position`** | 0-indexed position in the rendered list |
| **`age_hours`** | int, `floor((now - receivedAt) / 3600000)`, clamped at 0 |

Fired **before** `resolveNotificationTarget`, so an unroutable kind still
records the tap. A row that is tapped and goes nowhere is the single most
useful signal this event can carry — it is exactly the `referral_joined` bug
this batch fixes, and the only way to catch the next one.

### `notif_empty_state_shown`

| | |
|---|---|
| **Fires** | the sheet opens onto an empty list, once per open |
| **Client** | mobile only |
| **`not_joined`** | int \| **null**. Leaguemates who have not joined |
| **`total_mates`** | int \| **null**. League size |
| **`invite_offered`** | bool — whether the penetration gate opened and the invite action rendered |

**NULL IS HONEST, 0 IS A LIE** — same rule the invite events already carry. The
bell is global and can be opened with no active league, or before
`/api/league/summary` lands. Both counts are `null` in that case, and
`invite_offered` is `false`. Never substitute 0.

## 3. Classification

`INTENT_EVENTS` is derived by subtraction (`analytics_queries.py:140`), so
taxonomy growth is **intent-by-default**. A passive name registered and left out
of `NON_INTENT_EVENTS` step-changes DAU/WAU on ship day, silently and
permanently, and breaks every retention series at that seam.

| Event | Class | Reasoning |
|---|---|---|
| `notif_inbox_opened` | **NON_INTENT** | Navigation-class, same family as `tab_selected` and `league_view`. Opening the bell is a glance, not a decision. It is also the **denominator** for the other two |
| `notif_empty_state_shown` | **NON_INTENT** | An impression. The user did nothing; the surface rendered. Same class as `invite_cta_shown`, which is already NON_INTENT |
| `notif_row_tapped` | **INTENT** | A real decision on a real object. This is the number the batch exists to produce |

Both NON_INTENT names go into `NON_INTENT_EVENTS` in the same commit that adds
them to `ALLOWED_CLIENT_EVENTS`.

## 4. The `surface` enum extension

`InviteSurface` (`mobile/src/components/InviteLeaguematesBanner.tsx`) is a
**closed** four-value set and a registered prop domain on `invite_shared`,
`invite_cta_shown` and `invite_cta_tapped`. GD-1 puts an invite ask in the bell's
empty state, which is a fifth surface:

```
league_home | matches_empty | trades_banner | members_overlay | notif_empty
```

The values are carried by the taxonomy's prop-row **comments**, not enforced by
code (`CLIENT_EVENT_PROPS` constrains prop *keys*, not values), so the edit is a
comment update plus the TS union. Both land in commit 1, before the client change
that can emit the new value.

## 5. Measurement caveats

1. **Web is unmeasured.** `web/js/app.js` has no analytics SDK — no `track()`, no
   `/api/events` caller. Everything here is the mobile bell. Do not read these
   numbers as a product-wide bell open rate.
2. **`invite_cta_shown{notif_empty}` is a mount counter**, not an impression
   counter, under the same D-P1-04 caveat the `matches_empty` surface carries:
   the empty state renders inside a plain `<View>` with no scroll ancestry. The
   sheet is short and clipping is unlikely, but the event witnesses a mount.
3. **3–5 users.** None of G-N1…G-N5 in the source doc will reach significance.
   These are **directional reads, not experiments**, and should be reported as
   such. The instrumentation ships anyway because it is retroactively
   unrecoverable.
4. **`row_count` is pre-hydration** — see §2.
