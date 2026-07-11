# mobile/src/api/

HTTP clients only. No React, no state, no side effects beyond fetch.

| File | Wraps |
|---|---|
| `client.ts` | Base fetch wrapper (URL, auth headers, JSON) |
| `auth.ts` | Sign in / session endpoints + account auth (`/api/auth/apple`, GET/DELETE `/api/account`) |
| `sleeper.ts` | Sleeper public API |
| `league.ts` | League data + members |
| `rankings.ts` | Submit/fetch personal rankings |
| `trades.ts` | Trade card fetch + decisions |
| `flags.ts` | Feature flags (`/api/flags`) |
| `notifications.ts` | Notifications inbox |
| `calc.ts` | Trade Calculator consensus endpoints (`/api/trade/values`, `/api/trade/evaluate`) — public, no session |
| `sendInSleeper.ts` | Link Sleeper account + propose trades directly (flagged beta) |
