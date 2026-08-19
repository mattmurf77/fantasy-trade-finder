# Tracking-plan addendum — `swipe_guard_blocked` (deck double-fire guards)

**Date:** 2026-08-18 · **Status:** adopted with the B4 follow-up commit
**Parent:** [2026-07-17-tracking-plan-v2.md](2026-07-17-tracking-plan-v2.md) §S3
**Origin:** [../../reviews/2026-08-18-bug-sweep/ticket.md](../../reviews/2026-08-18-bug-sweep/ticket.md) §B4 · `living-memory/DECISIONS.md` **D-068** (which deferred this event) · `living-memory/GOTCHAS.md` **G-049**
**Registries touched:** `backend/analytics_taxonomy.py` (`ALLOWED_CLIENT_EVENTS`, `CLIENT_EVENT_PROPS`). **Not** `FUNNEL_CRITICAL`, **not** `analytics_queries.NON_INTENT_EVENTS`, **not** `SERVER_FIRED_EVENTS` — each omission is argued below.

The taxonomy is **default-deny**: an unregistered client event is counted and
dropped at ingest *behind a 200*, and an allowlisted event with no
`CLIENT_EVENT_PROPS` entry raises at **import**. This addendum is the
precondition that module's docstring demands, and it lands with the
registration, ahead of the emitter in the same change.

## Why now

On 2026-08-18 a user was permanently trapped on one trade card. `advance()`'s
double-fire guard had been poisoned by a failed swipe POST, so every subsequent
✕, ✓ and swipe on that card hit a **bare `return`**. The stall produced **zero
telemetry of any kind** — fifty taps, no events — and was found only because a
human reported it. D-068 fixed the poisoning and deliberately deferred this
event; the *blind spot* it names survived the fix:

> "A `swipe_guard_blocked` analytics event (deferred … the stall consequently
> remains invisible in telemetry)." — D-068, *Alternatives considered*

The fix re-arms the guard on one known path. Any future path that re-poisons it
— or the second live strand the same ticket found in `DeclineReasonPanel` — is
still silent. This event closes that, and nothing else: it is diagnostic, it
changes no product behaviour, and it is expected to read **zero** in a healthy
build.

## The event

| Event | Class | Fires when |
|---|---|---|
| `swipe_guard_blocked` | **intent** (a real user gesture the app refused) | `TradesScreen.advance()` early-returns because a double-fire guard rejected the disposition — i.e. the user acted on the deck and *nothing happened* |

### Props

| Prop | Type | Values | Why |
|---|---|---|---|
| `guard` | string enum | `swipe_undo` \| `decline_reasons` | **Which** early-return fired. Two distinct guards, two distinct product failures (below). Closed enum; a third guard extends it here first. |
| `decision` | string enum | `like` \| `pass` | What the user was trying to do. B4's signature is *pass fails, then ✓ is dead too* — a `like` row on a card that was passed is the escape attempt, and it is the difference between "double-tapped the ✕" and "trapped". |
| `trade_id` | string | server-minted deck id | The card. Server-minted and echoed verbatim (`api/trades.ts`); not derived from anything about the user. |
| `impression_id` | string | server-minted, or the literal `none` | The **serve**, not the card. The trap is per-serve (a card re-fronted after a failed POST is a new predicament on the same `trade_id`), and this is the existing join key to `deck_impressions`. Literal `none` rather than absence — the same convention `reasonEventProps()` uses, so a missing serve is distinguishable from a stripped prop. |
| `blocked_n` | int ≥ 1 | ladder points only — see below | Consecutive blocks on this card+guard. **The trap depth.** `1` is an ordinary double-fire; `≥3` cannot be one. |
| `ms_since_render` | int ≥ 0 | ms | Card-render → block. Separates a fat-finger double-tap (tens of ms) from a user tapping again ten seconds later because nothing happened. Same field, same source (`cardRenderedAtRef`) as the `trade_pass_layer*` family. |

**No `platform` prop.** Device platform is a `user_events` **column**, derived
server-side at ingest from the batch body / `X-Device` headers — the
NULL-`platform` incident is precisely the confusion of the two, and
`test_p0_events_reject_device_platform_prop` pins it. The one registered
exception is the decline-reason family, where an operator-approved spec
(SPEC §6) made the emitter's own claim a deliberate cross-check. This event
claims no such exception: the column is authoritative and a per-OS cut of these
rows reads it. **No player ids, no names, no league identity, no free text.**
`league_id` rides the envelope column as always.

### Which guards, and why both

`advance()` has two early-returns. Both are instrumented, **distinguished by
the `guard` prop rather than by two event names**, so "how often is a user stuck
on the deck?" stays one query and the enum can grow.

- **`swipe_undo`** — `lastDispositionedRef` (flag `ux.swipe_undo`). This is the
  B4 mechanism itself. Six sites clear this ref; a seventh that forgets
  reproduces the trap exactly, and D-068 accepted that risk explicitly. Not
  instrumenting it would leave the ticket's own finding unaddressed.
- **`decline_reasons`** — `reasonBankedIdRef` (flag `feedback.decline_reasons`).
  The *second live strand* named in the same ticket (fix item b.3): collapsing
  the open tile in `DeclineReasonPanel` leaves the pass banked, the ✓ disabled
  and the swipe inert with no visible way forward. It is the same class of
  silent trap, and it is the **newer and less-proven** of the two guards — a
  flag that shipped in v1.14.0 build 116. Instrumenting only the older one
  would light the strand we already fixed and leave dark the one we have not.

The **control** that was refused (button vs. swipe gesture vs. VoiceOver action)
is deliberately **not** a prop: all three funnel through one `onLike`/`onPass`
pair before `advance()` sees them, so the emitter cannot honestly tell them
apart, and a guessed prop is worse than a missing one (`is_self` precedent,
HLD S-33). `decision` carries the part that is actually known.

## Volume — the ladder

A trapped user tapping repeatedly is the *phenomenon*, so collapsing to one row
per card would delete the measurement. Firing on every block, however, is
unbounded: a stuck user in a tight loop could fill the 500-event SDK queue and
evict real funnel rows.

Emission is therefore on a **ladder** of `blocked_n` — `1, 2, 3, 5, 10, 25` —
per (card, guard), with a hard **session cap of 50 rows** across all cards.
Maximum six rows per trapped card; a pathological session is bounded at 50.

**Read `max(blocked_n)` per `(trade_id, impression_id, guard)`, never
`count(rows)`.** Row counts are ladder artefacts. The ladder is chosen so the
decisions the event exists to support survive it:

- `max(blocked_n) = 1` → an ordinary double-fire. The guard did its job.
- `max(blocked_n) ≥ 3` → a trap. A tap/gesture race cannot produce three
  consecutive blocks on one card.
- `max(blocked_n) ≥ 10` → a user who kept trying. The B4 user's fifty taps
  would land as six rows topping out at `blocked_n = 25`, which is the same
  conclusion at 12% of the volume.

The counter resets on a new `(card, guard)` pair, so it measures *consecutive*
blocks on one predicament and never accumulates across a session.

## Registry decisions

**Not `FUNNEL_CRITICAL`.** That set is the SDK's overflow drop-**last** policy,
hand-mirrored into `mobile/src/api/events.ts`. Two reasons, and the second is
the stronger one:

1. It is diagnostic, not a pre-auth funnel primitive. The current members are
   `app_opened`, `signin_attempted`, `signin_succeeded`, `experiment_exposed`.
2. Promoting it would **invert the priority under exactly the conditions it
   fires**: a trapped user is the one most likely to overflow the queue, and
   drop-last would make their guard rows evict the sign-in and exposure events.
   This is the event that *should* be dropped first when the queue is full.

The SDK mirror in `events.ts` is consequently **unchanged** — no desync.

**Not `NON_INTENT_EVENTS`, i.e. deliberately INTENT.**
`INTENT = (SERVER_FIRED ∪ ALLOWED_CLIENT) − NON_INTENT`, so taxonomy growth is
intent-by-default and the question is whether admitting this name step-changes
DAU/WAU at the emitter's ship date. It does not, on two independent grounds:

- **It is a real user gesture.** The user deliberately tapped or swiped; the app
  refused. That is the class of `sleeper_send_failed`, which is INTENT — a
  failed intent is still an intent, and this one is *more* deliberate than most
  because the user is repeating it.
- **No new user-days.** Every emission is preceded, on the same card in the same
  session, by `trade_card_viewed` — INTENT, and fired unconditionally on every
  card that reaches the top of the deck (`TradesScreen.tsx`, the
  `topTradeId` effect). There is no reachable state where a user fires this
  event without already being counted that day. The decline-reason family was
  admitted to INTENT on exactly this argument.

`backend/analytics_queries.py` is therefore **not edited**. If the operator
prefers the conservative reading (a *blocked* action is an outcome, not an
intent), the change is one line in `NON_INTENT_EVENTS` and this paragraph is the
record of why it was not taken.

**Not server-fired, and it cannot be.** The server never learns that a tap was
swallowed — that is the entire finding. The disjointness assert also means the
name may never appear in `SERVER_FIRED_EVENTS`.

## What this is deliberately not

- **Not a Sentry `captureException`.** The ticket notes Sentry is initialized
  and never called on the swipe path. A guard block is not an exception: it is a
  measurable rate with a denominator (`trade_card_viewed`), and it needs to be
  countable, not alertable-on-per-instance.
- **Not a user-visible change.** No toast, no copy, no flag. `track()` is
  no-throw, fire-and-forget, and dark unless `analytics.client_events` is on;
  the early-return's behaviour is byte-identical either way.
- **Not an event on the *poisoning*.** The failed POST that re-arms the guard is
  already visible as `api_request_failed{route:/api/trades/swipe}` — the one
  usable signal the ticket identified. This event is the *consequence* half, and
  the join between the two is what proves a specific mechanism.
- **No prop for the free text, the roster, the partner, or the user.** Nothing
  here identifies a person.

## Reading it

- **Is anyone trapped?** `swipe_guard_blocked` with `max(blocked_n) ≥ 3`, split
  by `guard`. In a healthy build this is **zero rows**; a non-zero count is a
  regression of D-068's fix or a new poisoning path.
- **Which strand?** `guard = swipe_undo` is the B4 mechanism (a `lastDispositionedRef`
  clear site was missed); `guard = decline_reasons` is the panel-collapse strand.
- **Benign or not?** `blocked_n = 1` with a small `ms_since_render` is a
  double-fire the guard exists to absorb. The same card with `decision` values on
  *both* sides — a `pass` then a `like` — is a user hunting for an escape.
- **Did the fix hold?** Row count per 1k `trade_card_viewed`, over the D-068 ship
  date. The pre-fix series does not exist, so this is a forward baseline only:
  the honest statement is "zero known trapped sessions since instrumentation",
  never "the rate fell".
