# mobile/src/api/

HTTP clients only. No React, no state, no side effects beyond fetch.

| File | Wraps |
|---|---|
| `client.ts` | Base fetch wrapper (URL, auth headers, JSON) |
| `auth.ts` | Sign in / session endpoints + account auth (`/api/auth/apple`, GET/DELETE `/api/account`, POST `/api/account/link-sleeper`) |
| `sleeper.ts` | Sleeper public API |
| `league.ts` | League data + members |
| `rankings.ts` | Submit/fetch personal rankings |
| `trades.ts` | Trade card fetch + decisions |
| `tradePregen.ts` | Onboarding item 4 pregen: fire-and-forget `maybePregenTrades()` kicked from session-init success paths (LeaguePicker pick, `revalidateSession`) — flag `onboarding.trades_first`, per-launch dedupe; also the single source for the shared fairness-pref constants |
| `events.ts` | First-party analytics SDK (`POST /api/events`, P1 contract — flag `analytics.client_events`) — `track(type, props?, screen?)` + batched offline queue (`{v:1}` shape, funnel-critical drop-last), per-session `seq`, response-driven purge + backoff. Device id (`dev_`) is minted in `client.ts` (`getDeviceId`) and re-exported here to avoid a flag-store import cycle |
| `flags.ts` | Feature flags (`/api/flags`) |
| `notifications.ts` | Notifications inbox |
| `calc.ts` | Trade Calculator consensus endpoints (`/api/trade/values`, `/api/trade/evaluate`) — public, no session |
| `sendInSleeper.ts` | Link Sleeper account + propose trades directly (flagged beta) |
| `espn.ts` | ESPN league linking (flag `espn.link`): `/api/espn/link|leagues|import` + `buildEspnSessionInitBody` (ESPN leagues source session-init rosters from the backend snapshot, never Sleeper proxies) + `isEspnLeague` (platform check against the cached league list, used by auth.ts's builders) |
| `platformLink.ts` | Zero-auth multi-platform linking — MFL (`mfl.link`) + Fleaflicker (`fleaflicker.link`): generic `/api/{platform}/link|leagues|import` (+ Fleaflicker `/discover` by email) + `buildPlatformSessionInitBody` (backend snapshot, never Sleeper proxies) + `isMflLeague`/`isFleaflickerLeague` (used by auth.ts's builders) + `parseMflLeagueInput`/`parseFleaflickerLeagueInput`. ESPN keeps its own `espn.ts` (private-league cookie flow) |
