# mobile/src/api/

26 HTTP client modules. Every request goes through `client.ts` — nothing in the app calls `fetch` directly.

The annotated per-module map (contracts, error codes, flag gates, known contract gaps) is [CLAUDE.md](CLAUDE.md); it is the doc to read before touching any of these. This file is the orientation.

## Grouping

| Group | Modules |
|---|---|
| Foundation | `client.ts` (base fetch, `X-Session-Token`, device id, 401 handling), `_queue.ts` (shared offline-write-queue primitives) |
| Identity & account | `auth.ts`, `accountPrefs.ts` |
| League platforms | `sleeper.ts`, `espn.ts`, `platformLink.ts` (MFL + Fleaflicker), `league.ts` |
| Rankings & values | `rankings.ts`, `market.ts`, `calc.ts`, `leaderboard.ts` |
| Trades | `trades.ts`, `tradePregen.ts`, `declineReasons.ts` |
| Trade send | `sendInSleeper.ts`, `sendInMfl.ts`, `sendInEspn.ts` |
| Rookie draft | `draft.ts`, `mockDraft.ts`, `pickAssignment.ts`, `recordedPicks.ts` |
| App plumbing | `flags.ts`, `events.ts` (analytics), `notifications.ts`, `feedback.ts` |

## Conventions

- **One module per backend surface.** Named exports only; no default export.
- **Wire types live next to the call** that returns them, unless they're used by screens *and* components — those go in `../shared/types.ts`.
- **Errors are typed, narrowed by a helper, never by `err.status` at the call site.** Examples: `staleAssignment(err)` (409 conflict → the current row), `pickAssignmentErrorCode(err)`, `espnCredentialsRejected(err)`, `DraftSchemaError` (unknown payload `schema` ⇒ "update the app", never a best-effort parse).
- **Open vs closed enums matter.** `notice.code`, typed-empty `reason`, and `suggested_order_source` are OPEN — an unknown value must degrade to generic copy, not crash. `state`, `kind`, `order_confidence` are CLOSED.
- **Two offline write queues exist** — `events.ts` (analytics) and `recordedPicks.ts` (live draft picks). They share the pure primitives in `_queue.ts` (uuid idempotency keys, backoff ladder, accepted/deduped/rejected purge) but keep their own flush loops on purpose. A third queue copies that contract; it does not invent a new one.
- **Backend contract of record:** [docs/api-reference.md](../../../docs/api-reference.md). Route changes there and here move together.

## Adding a module

1. Import `api` from `./client.ts`; never `fetch`.
2. Export the request functions plus their response interfaces.
3. If the endpoint is flag-gated, the *caller* checks the flag — the client stays dumb.
4. Add a row to [CLAUDE.md](CLAUDE.md) describing the contract, not the history.
5. Update [docs/api-reference.md](../../../docs/api-reference.md) if the route is new.
