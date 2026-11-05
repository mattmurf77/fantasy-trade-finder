# Native Find a Trade preparation

Base: `dd5058ba`. Scope: native empty-canvas organic calculator entry;
no feature/config/production activation, UI copy or pinned-intent change.

The observed Wi-Fi first tap timed out at 10,007 ms and its server job took
64.8 seconds. This change does **not** establish a 200 ms physical-device
result or turn a cold engine run into an instant card.

## Cause and resulting behavior

Before this change, hydration and refresh began only after Acquire landing
focus. A returning user spending time in Home/Rank gained no device-page
head start. A running first response was discarded and the same key's
60-second refresh throttle prevented adopting its later completed page.

`TabNav` now mounts `useTradePagePrewarm` once. Its effect hydrates stored
pages, reads the shared persisted fairness preference, joins session
revalidation, and prepares exactly the active user/league/scoring-format
organic request. Demo/account-only/switching/tokenless/background/flag-off
contexts do not start it. Late storage or session responses recheck the
current context before requesting or retaining a page.

`refreshDevicePage` follows the same running paged job, starting at 500 ms
and backing off to 3 seconds. Polling stops at 40 polls or a 90-second
window, without starting another generation. Every iteration checks
foreground, identity callback, epoch and current scope. Canceled work can
be replaced immediately; its finalizer cannot erase the replacement's
throttle. Distinct fairness scopes have distinct throttles, and old scopes
cannot overwrite a newer scope. Ranking/format/roster invalidation also
clears the obsolete request throttle.

Only the existing `devicePageFrom` complete/fresh/ownership-checked paged
envelope can be persisted. Running provisional cards are never kept. The
same five-minute page bound, keyed identity, unseen-card removal,
invalidation and whole-deck revalidation remain in force.

## Required server companion and preview safety

**Deploy the server's `X-FTF-Prewarm: 1` guard before distributing this
mobile change.** Both passive generation and status calls send that header
through the normal request-headers facility. A server response
`409 {"error":"prewarm_requires_tap"}` discards a held page and grants
nothing. The companion refuses passive free-preview delivery before serve
or preview recording. Client `background: true` alone only suppresses gate
UI and does not make a delivery safe; the header is required.

Real user taps, normal deck polling and revalidation retain their existing
requests. The calculator cache branch skips the stored page for a known
enforcing non-Pro session, so a cached card is not treated as a preview
grant. Its actual tap follows the normal server gate. Server enforcement
remains authoritative. No optimistic client receipt adds permission.

## Verification and remaining device check

`check-device-first-page.js` executes completed/running/stale/invalidated
pages, a simulated 64.8-second job, bounded wedged jobs, cancellation and
replacement races, scope transitions, passive preview refusal and no
background requests. `check-trade-prewarm.js` executes delayed storage and
session resolution across user/league/format/token/flag/foreground changes.
Existing fairness, first-card analytics, canvas/results navigation,
paywall and entry-identity guards remain relevant. Typecheck is required.

Negative controls remove completion polling, current-context checks, the
preview header or the free-session cache guard; corresponding regressions
must fail before restoration. These are code/effect tests, not native
render timings.

On the approved physical TestFlight build, use the dedicated test account:
spend time on Home and Rank, then Acquire with an empty canvas and tap Find
a Trade. Record tap-to-first-card from existing analytics/readout, first
and repeat taps, exact build, source, network and launch state. Repeat
after rank/format/league/account changes and foregrounding. A free
enforcing user must retain its preview until the actual tap. Pinned,
opponent/intent, genuinely cold and slow-network searches must keep their
honest wait/gate states. The existing 600 ms cold page-push deadline and
possible duplicate generate after that deadline remain separate work;
neither is reported as a usable first card under 200 ms.
