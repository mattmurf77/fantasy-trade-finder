# Tracking plan addendum — feedback #297 / #298 / #299 / #302

**Date:** 2026-08-11
**Status:** built, verified statically; **deploy-then-probe gate NOT yet run** (§7 — it needs a deploy and is above the build agent's authority).
**Base:** `feedback-integration-v2` = `origin/main` @ `f65bab7` + both build branches.
**Owner:** analytics instrumentation agent, `/feedback` batch #297/#298/#299/#302.
**Supersedes:** the `league_team_focused` / `league_team_unfocused` pair proposed on branch `feedback-integration-297-302` (`e1dba6a`…`49e48ef`). See §6.

This is the tracking-plan addendum `backend/analytics_taxonomy.py`'s own module
docstring requires before a new client event name may be registered.

---

## 1. What is added, in one table

| # | Event | New? | Client | Trigger moment | Props | Intent? |
|---|---|---|---|---|---|---|
| 1 | `lineup_impact_unavailable` | **new name** | mobile (`InLeagueCalculator.tsx`) | The honest-empty "Starting lineup" row renders — i.e. an evaluation returned with `starter_impact` absent **and** both sides carry players | `platform` | **NON-INTENT** |
| 2 | `league_team_opened` | **no — adopted, already shipped** | mobile (`LeagueSummaryScreen.tsx`) | A team drill-in opens (chart bar or list row) | `via`, `rank`, `basis`, `subset`, `filter_count` (unchanged) | INTENT (unchanged) |
| 3 | `league_team_closed` | **new name** | mobile (`LeagueSummaryScreen.tsx`) | The drill-in focus ends through any of its five controls | `via`, `dwell_ms`, `rank` | **NON-INTENT** |
| 4 | `find_trades_tapped` | **no — props widened** | mobile + web (web unaffected) | unchanged | **+`mode`**, **+`source`** (see §4) | INTENT (unchanged) |
| 5 | `trade_card_viewed` | **no — props widened** | mobile | unchanged | **+`mode`** | INTENT (unchanged) |

**Two new event names, three new properties.** No server-fired event is added
or changed. No route, no schema, no flag.

---

## 2. `lineup_impact_unavailable` (#297)

**Fires from:** `mobile/src/components/InLeagueCalculator.tsx`, inside
`LeagueVerdict`, in an effect gated on `both && !ev.starter_impact` and keyed
on `ev`. One event per **evaluation that rendered the row** — not one per
mount (which would under-count a user re-evaluating), and not one per render.

**Screen prop:** `TradeCalculator`.

### Properties

| Prop | Type | Values | Notes |
|---|---|---|---|
| `platform` | string | `sleeper` · `espn` · `mfl` · `fleaflicker` · `unknown` | The **LEAGUE** platform, read from `useSession.getState().leagues`. |

`platform` here carries the same sense as `league_selected.platform` and
`league_view.platform`. It is **not** the device platform: device platform is
a server-derived *column* stamped in `analytics_ingest.py` from the batch
body / `X-Device` headers. That distinction is the NULL-`platform` incident,
and it is pinned by `test_p0_events_reject_device_platform_prop`.

`unknown` is a real value, not a placeholder: the calculator is reachable for
a league that is not in the session's cached list (deep link, cold start
before the switcher hydrates).

### Why a new event and not a property on an existing one

The obvious alternative is a `lineup_impact` cause prop on the server-fired
`calc_trade_evaluated`. Rejected, because the two count different things:

* The server knows it **omitted** `starter_impact`. It does not know the
  client reached the both-sides-populated state that draws the row — and it
  omits the field in Mode A too, where this component never runs. A server
  prop would therefore be a **superset**: Mode A evaluations, half-built
  trades, and responses the user navigated away from before render.
* #297's fix *is* a copy change — a silent `null` became a sentence. The
  question the fix creates is "how many users read that sentence", which is
  an impression, and only the client can witness an impression.

### Why `reason` was dropped

The previous round specced `reason ∈ {not_sleeper, sleeper_incomplete}`
alongside `platform`. Dropped: the client's only honest derivation of that
enum is `platform === 'sleeper'`, i.e. a pure function of the prop next to
it. Two encodings of one fact is the two-sources-of-truth bug this surface's
history (#208, #248, #293) is a catalog of. One prop, one fact.

### Deliberately NOT instrumented

The finer server-side split — `no_slot_template` (the league-meta fetch
returned no usable `roster_positions`) versus `roster_missing` (a caller or
opponent roster absent from `league_members`) — is knowable **only** inside
`_starter_impact` (`backend/server.py:1123`). It is not instrumented here.
Reasons, in order: it needs a `server.py` edit outside this agent's ownership;
`platform` already answers the product question ("should we build lineup
impact for ESPN/MFL?"); and the residual — a `sleeper` row on this event — is
itself the signal that the finer split is worth adding. Cost to add later:
one prop on one server `record_event` call.

**Correction to a shipped docstring, recorded here because a reason-enum
would have got it wrong:** `_sleeper_lineup_slots`' docstring says `None` is
returned "for non-Sleeper league ids (ESPN/MFL/Fleaflicker imports, demo)",
implying non-Sleeper ids are non-numeric. **ESPN and MFL league ids CAN be
numeric** — MFL `990062846` is live in this project's local DB. Those leagues
fail at the **meta-fetch** gate, not the `isdigit()` gate. This is why the
client reads `platform` from the session league cache and never from the
league id's shape, and why `check-analytics-297-302.js` asserts no
digit-shape heuristic exists in that file (sabotage J7).

---

## 3. `league_team_closed` (#299/#302) — and why the enter half is NOT new

### The finding

`league_team_opened` **already exists**. It shipped in the P0-7 nav+League
instrumentation round (`b904ff2`, `origin/main`), is registered at
`analytics_taxonomy.py:122` with props
`{via, rank, basis, subset, filter_count}`, and is fired from exactly one
place: the `openTeam` helper at `LeagueSummaryScreen.tsx`, which both
drill-in entry points (chart bar and list row) route through.

**It fully covers the drill-in ENTER.** There is nothing #299/#302 needed
from an enter event that it does not already provide — including `via`
(`bar` | `row`, the same bar-vs-row distinction the previous round proposed
as `chart_bar` | `list_row`) and the on-screen rank.

**Verdict: adopt it. No `league_team_focused` is minted.** Two events for one
interaction on this screen would be exactly the class of bug #208/#248/#293
are a catalog of, and `check-analytics-297-302.js` now fails if either name
reappears in the screen or the taxonomy (sabotage J12).

### The genuine gap

There is **no exit signal**. The drill-in is component state (`selectedId`),
not a stack push, so it produces no `screen_left` and no navigation event. So
today it is impossible to know:

* whether a user ever leaves the drill-in deliberately at all — which is
  literally the claim #302 makes;
* **which** of the five exits they use — which is the only way to learn
  whether #302's new header control is the one people find, versus the
  Android hardware back they always had, versus the tab re-tap;
* how long a drill-in lasts.

That is one gap, and it takes one event.

### The event

**Fires from:** `emitTeamClosed(via)` in `LeagueSummaryScreen.tsx` — the
single choke point. `closeTeam(via)` = `emitTeamClosed(via)` +
`setSelectedId(null)`, and **the only bare `setSelectedId(null)` in the file
is the one inside `closeTeam`** (asserted; sabotage J1).

**Screen prop:** `route.name` (`LeagueRankings` on the tab root,
`LeagueSummary` on the legacy root-stack push).

| Prop | Type | Values | Notes |
|---|---|---|---|
| `via` | string | closed enum, 5 values (below) | Which control ended the focus. |
| `dwell_ms` | int | ms | `Date.now() - focusRef.at`. Terminates the focus interval the way `screen_left` terminates `screen_viewed`. |
| `rank` | int | 1-based | The on-screen rank **at open**, carried in the focus ref — so it joins to `league_team_opened.rank` even if the user changes basis mid-focus. |

`via` enum — one value per control, each asserted to appear exactly once:

| Value | Control | Site |
|---|---|---|
| `header_back` | #302's fixed stack-header "‹ All teams" (tab root only) | `setOptions` `headerLeft` |
| `in_card_link` | The #243 in-card link (legacy root-stack push only; mutually exclusive with the above) | slim strip |
| `hardware_back` | **RESERVED — no emitter.** #302's Android `BackHandler` was withdrawn before ship (iOS-only release; unverifiable on Android). Kept registered so re-enabling is one effect, not a taxonomy migration | *(none — pinned absent)* |
| `tab_retap` | #302's re-tap of the already-active League tab | `registerScrollToTop('League', …)` |
| `refocus` | Opened a *different* team without leaving the panel (chart bars stay tappable while focused) | `openTeam` |

### The sixth case, measured by absence — deliberately

A `league_team_opened` with **no** `league_team_closed` before the next
`screen_left` / `app_backgrounded` is "abandoned by navigating away". There
is deliberately no sixth `via` for it and no unmount-cleanup emitter:

* an unmount cleanup double-fires on React strict-mode remounts and would
  invent dwell intervals that never happened;
* absence is *informative here* — "opened it and left the tab" is precisely
  the stranded-user state #302 exists to fix, so it should be visible as a
  missing terminator, not laundered into a normal exit.

Report definition: **exit rate** = `count(league_team_closed) /
count(league_team_opened)` per user-day; the shortfall is the abandon rate.

### Interval bookkeeping

* `openTeam` on a **different** team emits `refocus` first, then opens — or
  the first interval silently absorbs the second team's dwell.
* `openTeam` on the **same** team (a no-op re-tap) does **not** close, and
  keeps the original `at`, so dwell still measures from the first open.
  (`league_team_opened` re-fires on a same-team re-tap; that is shipped
  behaviour, unchanged by this work.)
* The focus interval lives in a **ref**, not state. Two of the five controls
  are registered inside effects whose dep arrays deliberately exclude
  `selectedId` (the tab-retap handler, deps `[isTabRoot, retapOn]`; the
  `BackHandler`, registered once per focus). A state closure would report
  the focus that was live when the handler was **registered**, not when it
  fired. A ref cannot go stale.

---

## 4. `mode` and `source` (#298) — properties, not a new name

#298 is a regression in **where existing controls render**, not a new
interaction. The question is therefore "do the events that always fired on
this path still fire from the pinned surface", and only a property on those
same events can answer it — a new name has no pre-fix baseline.

| Event | New prop | Values | Why |
|---|---|---|---|
| `find_trades_tapped` | `mode` | `single_pin` · `deck` | Before the fix a pinned surface could not fire this **at all** — the CTA was gated out. A non-zero `mode:single_pin` count *is* the fix's telemetry. |
| `find_trades_tapped` | `source` | `prefs_changed_strip` · `deck_error_retry` · absent | **A bug fix, not an addition.** `handleFindTrades` has sent `source` since #257 and the empty prop registry popped it on **every row** — the live twin of `trade_card_shared`'s discarded `landing`. |
| `trade_card_viewed` | `mode` | `single_pin` · `deck` | The outcome half. A `find_trades_tapped{mode:single_pin}` with no following `trade_card_viewed{mode:single_pin}` is #298 reappearing: a deck generated with nowhere to render and no disposition path. |

**Three emitters, one derivation.** `TradesScreen.tsx` has *two*
`find_trades_tapped` call sites (`handleFindTrades`, and an inline `track` in
the `!consolidateOn` legacy CTA arm that does not route through it). Both —
plus `trade_card_viewed` — read the single
`const deckMode = singlePinFeatured ? 'single_pin' : 'deck'`, so the two CTA
arms cannot disagree. Asserted; sabotage J11.

**#169 check, since the brief flagged it:** `#169` moved the Pass/Like
*controls* into `TradeCard.tsx` (`trades.pass-btn`), wired
`disposition.onPass` → `TradesScreen` → `advance()`. It did **not** move the
`trade_card_viewed` emitter, which still fires from `TradesScreen.tsx` on the
top-card effect, and it did not change `advance()`'s server-fired `swipe`.
The property placement is therefore unaffected. Verified by call-site grep,
not assumed.

---

## 5. Intent vs non-intent — decided per event, in the same commit

`analytics_queries.py:65`:
`INTENT_EVENTS = (SERVER_FIRED_EVENTS | ALLOWED_CLIENT_EVENTS) - NON_INTENT_EVENTS`.

**Taxonomy growth is intent-by-default.** Any name added to the allowlist
becomes an INTENT event unless also added to `NON_INTENT_EVENTS`, and
`INTENT_EVENTS` feeds DAU/WAU across ~10 call sites in that module.
Registering a passive event without the guard step-changes DAU/WAU with no
error, no log, and no way to tell the artifact from real growth afterwards.

Both new names are in `NON_INTENT_EVENTS`, **added in the same commit** as
their allowlist entries.

| Event | Verdict | Reasoning |
|---|---|---|
| `lineup_impact_unavailable` | **NON-INTENT** | A passive impression — the user did nothing. The evaluation that produced it already counts the user via the server-fired `calc_trade_evaluated`, which is INTENT *and* a `WAT_LIVE` feeder, so admitting this row adds no user DAU has not already seen. |
| `league_team_closed` | **NON-INTENT** | A terminator, and dismissal-class like `quickset_abandoned`. Every close is preceded by a `league_team_opened`, which is INTENT and already counts the user. The only user-days this could add are ones where the **opener** was lost to SDK queue overflow — an artifact, never signal. |
| `league_team_opened` | **INTENT — unchanged, untouched** | A deliberate drill-in on a real surface. It has been INTENT since P0-7; nothing here promotes or demotes it. |
| `find_trades_tapped`, `trade_card_viewed` | **INTENT — unchanged** | #298 added no event name. A property on an event that already fires cannot perturb the series at all. |

`FUNNEL_CRITICAL` is not touched: neither new event is worth retaining over a
`signin_attempted` under queue overflow, and the mobile mirror in
`mobile/src/api/events.ts` therefore needs no edit.

---

## 6. What in the previous round is now wrong

Branch `feedback-integration-297-302`, commits `e1dba6a`…`49e48ef`.

| Previous conclusion | Status now | Why |
|---|---|---|
| "No registered event covers the League drill-in at all" (299 scope §1) | **FALSE** | True when written; `origin/main` gained 17 client events between that check and its ship, including the whole P0-7 League family. `league_team_opened` covers the enter half. |
| Mint `league_team_focused` + `league_team_unfocused` | **DISCARDED** | The enter half duplicates a shipped event. Replaced by: adopt `league_team_opened`, add one exit event. |
| `exit_method` prop name | **RENAMED to `via`** | Matches `league_team_opened.via` and `guide_step_advanced.via`; the pair is now readable as one vocabulary. |
| `team_count` prop on the enter event | **DROPPED** | `league_team_opened` already carries the filter context it needs; league size is available from `league_view.team_count` on the same session. |
| `reason` on `lineup_impact_unavailable` | **DROPPED** | Pure function of `platform` — see §2. |
| `lineup_impact` cause split on server-fired `calc_trade_evaluated` (`5895488`) | **NOT CARRIED FORWARD** | Outside this agent's ownership (`server.py`), and `platform` answers the product question. Recorded as deliberately-not-instrumented in §2. |
| `mode` on `find_trades_tapped` / `trade_card_viewed` | **KEPT** | Re-verified against `TradesScreen.tsx` post-#169: `trade_card_viewed` still fires from `TradesScreen.tsx`, so the property placement holds. Extended: `mode` is now also sent from the second (legacy-arm) emitter, which the previous round left un-moded. |
| Registering `source` on `find_trades_tapped` | **KEPT** | Independently re-verified: `handleFindTrades` sends it, the registry popped it. Genuine live data loss. |
| ESPN/MFL ids can be numeric; read `platform` from the cache, not id shape | **KEPT and re-verified** | Correct, and now pinned by a sabotage (J7) rather than by comment. |

---

## 7. Verification, and the deploy-then-probe gate

### Run here (all green)

| Command | Result |
|---|---|
| `python3 -m pytest backend/tests -q` | 2452 passed, 1 skipped |
| `npx tsc --noEmit` (mobile) | clean, exit 0 |
| `bash mobile/scripts/testid-lint.sh` | `testid-lint OK`, exit 0 |
| `node mobile/tests/check-league-drill-in.js` | 30 PASS / 0 FAIL (unchanged count) |
| `node mobile/tests/check-analytics-297-302.js` | all pass |
| `node mobile/tests/check-single-pin-actions.js` | 4 PASS / 4 FAIL — **unchanged**, pre-existing, owned by the trades build agent (`trades.pass-btn` moved to `TradeCard.tsx` in #169; the test's file assumption is stale, the behaviour is correct) |

### Sabotage matrix — every behavioural assertion falsified on a broken build

Backend (`backend/tests/test_events_api.py`):

| # | Sabotage | Detected by |
|---|---|---|
| S1 | Drop `lineup_impact_unavailable` from `ALLOWED_CLIENT_EVENTS` (name survival) | `…_new_events_land_with_every_prop` |
| S2 | Drop `dwell_ms` from `league_team_closed` props (prop survival) | same |
| S3 | Keep the name, rename its prop `via` → `exit_via` | same |
| S4 | Mint a duplicate `league_team_focused` enter name | `…_reuses_league_team_opened_for_the_enter_half` |
| S5 | Revert `find_trades_tapped` to `frozenset()` (the live strip bug) | `…_mode_and_source_survive_on_existing_events` |
| S6 | Drop `mode` from `trade_card_viewed` props | same |
| S7 | Drop `league_team_closed` from `NON_INTENT_EVENTS` | `…_events_are_not_intent` |
| S8 | Drop `lineup_impact_unavailable` from `NON_INTENT_EVENTS` | same |

Client (`mobile/tests/check-analytics-297-302.js`):

| # | Sabotage | Notes |
|---|---|---|
| J1 | Hardware back reverts to a bare `setSelectedId(null)` | 2 assertions flip |
| J2 | `dwell_ms` hardcoded to `0` — emitter present, value wrong | value-level, not presence-level |
| J3 | Send an **unregistered** prop (`league_id`) on `league_team_closed` | the §4 cross-check |
| J4 | Stop sending a **registered** prop (`rank`) | the §4 cross-check, other direction |
| J5 | Remove the `refocus` guard | dwell would absorb the next team's |
| J6 | **Keep the platform lookup line, swap the returned value to `'sleeper'`** | this is the exact false-pass shape the previous round's platform test survived |
| J7 | Infer platform from the league id's digit shape | |
| J8 | `#297` gate loses the both-sides check | would count impressions that never rendered |
| J9 | `#297` effect deps lose `ev` | would fire once per mount and under-count |
| J10 | `trade_card_viewed` drops `mode` | |
| J11 | Legacy CTA arm drops `mode` | the two emitters disagreeing is the failure |
| J12 | A duplicate `league_team_focused` emitter is reintroduced | |

Every sabotage was applied to the real tree one at a time, the test run, and
the file restored. All 20 flipped their test to FAIL.

### Deploy-then-probe gate — REQUIRED before wiring any report, NOT run here

Static tests prove the registry and the call sites agree. They cannot prove
the deployed backend agrees, because the drop paths are silent and the health
endpoint's counters are **in-process and reset on deploy** (so "counters
stayed flat" is not evidence of anything).

**After merge and deploy, before any dashboard, report, or experiment reads
these names**, hand-roll one `POST /api/events` per new name carrying its
**full** property set, then assert **both**:

1. the response reports `dropped == 0` (proves NAME survival), **and**
2. every property is echoed back at the destination — read the row out of
   `user_events.props` (proves PROP survival).

Assertion 1 alone is insufficient: an unknown prop is popped while the
envelope still reports `dropped: 0`.

```
POST /api/events   { "events": [
  { "event_type": "lineup_impact_unavailable", "screen": "TradeCalculator",
    "props": { "platform": "mfl" }, … },
  { "event_type": "league_team_closed", "screen": "LeagueRankings",
    "props": { "via": "header_back", "dwell_ms": 41200, "rank": 4 }, … },
  { "event_type": "find_trades_tapped",
    "props": { "source": "prefs_changed_strip", "mode": "single_pin" }, … },
  { "event_type": "trade_card_viewed",
    "props": { "trade_id": "probe", "card_index": 0, "mode": "single_pin" }, … }
] }
```

Not run: it needs a deploy, and it is above this agent's authority.

### Seam date

`lineup_impact_unavailable` and `league_team_closed` first appear on the ship
date of this batch. Both are NON-INTENT, so **no DAU/WAU/retention series has
a seam** — that is the entire point of §5. `find_trades_tapped.source` gains
values from the same date after having been silently discarded since #257;
any historical read of that prop is empty by construction, not by absence of
the behaviour.
