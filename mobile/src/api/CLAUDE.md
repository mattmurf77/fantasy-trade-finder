# mobile/src/api/

HTTP clients only. No React, no state, no side effects beyond fetch.

| File | Wraps |
|---|---|
| `client.ts` | Base fetch wrapper (URL, auth headers, JSON) |
| `auth.ts` | Sign in / session endpoints |
| `sleeper.ts` | Sleeper public API |
| `league.ts` | League data + members |
| `rankings.ts` | Submit/fetch personal rankings |
| `trades.ts` | Trade card fetch + decisions |
| `flags.ts` | Feature flags (`/api/flags`) |
| `notifications.ts` | Notifications inbox |
