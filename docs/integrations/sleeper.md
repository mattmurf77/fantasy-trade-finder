# Sleeper Integration Reference

> Full inventory of every call FTF makes to Sleeper — REST v1, undocumented GraphQL,
> and the WebView JWT-capture flow. Written to seed an instrumentation build (event
> naming, sampling, redaction rules). Source of truth is the code; this doc cites
> `file:line` for every claim so it can be re-verified as the code moves.
>
> Scope: backend (`backend/server.py` + service modules) and the mobile client
> (`mobile/src/`). The web app (`web/app.js`) and the browser extension
> (`extension/`) also call Sleeper but were out of scope for this pass — see
> `backend/server.py:16656-16810` (`/api/extension/auth`) for the extension's auth
> reuse of the same backend code path documented below.

## Table of contents

1. [Endpoints used](#1-endpoints-used)
2. [Auth model](#2-auth-model)
3. [Request/response shapes](#3-requestresponse-shapes)
4. [Error modes](#4-error-modes)
5. [Call frequency / caching](#5-call-frequency--caching)
6. [Instrumentation guidance](#6-instrumentation-guidance)

---

## 1. Endpoints used

Every network call FTF makes toward Sleeper. "Side" = which process actually opens
the socket. The mobile app **never** calls `api.sleeper.app` or `sleeper.com`
directly for JSON data — every read/write goes through the FTF backend, which
proxies and caches. The two exceptions are pure browser navigation (the WebView
login page load) and `Linking.openURL` deep links (handing off to Sleeper's own
app/site) — neither is an API call and neither carries any FTF data.

### 1.1 Public REST v1 (`https://api.sleeper.app/v1/...`) — unauthenticated

| # | Method + path | Purpose | Server call site | Client-facing route |
|---|---|---|---|---|
| 1 | `GET /user/{username}` | Resolve a Sleeper username → `user_id` (login) | `backend/server.py:13652` (`/api/sleeper/user/<username>`); also `backend/server.py:16776` (`_extension_build_session` / `/api/extension/auth` — **this is the route mobile sign-in actually calls**, `mobile/src/api/auth.ts:34-40`); also `backend/server.py:18022` (`/api/account/link-sleeper`, account-merge username resolution) | `/api/sleeper/user/<username>`, `/api/extension/auth`, `/api/account/link-sleeper` |
| 2 | `GET /user/{user_id}/leagues/nfl/2026` | List a user's leagues for the season | `backend/server.py:13705` (`/api/sleeper/leagues/<user_id>`); also `backend/server.py:16792` (bundled into `/api/extension/auth`'s login response) | `/api/sleeper/leagues/<user_id>` |
| 3 | `GET /league/{league_id}` | League metadata: `roster_positions`, `scoring_settings`, `settings` (playoff weeks/teams, status) | `backend/server.py:666-682` (`_fetch_sleeper_league_meta`, used for scoring-format detection + `/api/trades/validate`'s `league_archived` check); `backend/outlook/league_state.py:130,133` (outlook pipeline) | not directly routed — internal helper, consumed by several routes |
| 4 | `GET /league/{league_id}/rosters` | Roster → owner_id → player_ids, starters, W/L | `backend/server.py:13781` (`/api/sleeper/rosters/<league_id>`); `backend/server.py:10178-10184` (`_fetch_league_rosters`, send-in-sleeper roster resolution); `backend/server.py:19351-19353` (free-agents live rostered-player exclusion); `backend/draft_board_service.py:302-303`; `backend/outlook/league_state.py:146`; `backend/trade_block_service.py:90-99` (`_fetch_rosters`, ownership validation) | `/api/sleeper/rosters/<league_id>` |
| 5 | `GET /league/{league_id}/users` | League member list: user_id, display_name, avatar, team-name metadata | `backend/server.py:13812` (`/api/sleeper/league_users/<league_id>`); `backend/draft_board_service.py:305-306`; `backend/outlook/league_state.py:147` | `/api/sleeper/league_users/<league_id>` |
| 6 | `GET /league/{league_id}/traded_picks` | Which roster currently owns each future pick | `backend/server.py:10187-10200` (`_fetch_sleeper_traded_picks`); `backend/draft_board_service.py:299-300`; since #413 also `/api/trades/propose` + `/api/trades/validate` (pick sends only — the live holder check in `_sleeper_encode_ftf_picks`) | not directly routed — feeds Draft Room / owned-pick sync / pick-send holder check |
| 7 | `GET /league/{league_id}/drafts` | Draft list for a league: `draft_id`, `status`, `season`, `type` | `backend/server.py:10203-10219` (`_fetch_sleeper_drafts`); `backend/draft_board_service.py:289-290` | feeds `/api/draft/board` and `#228`'s current-season-drafted exclusion |
| 8 | `GET /draft/{draft_id}` | Single draft detail | `backend/draft_board_service.py:292-294` | feeds `/api/draft/board` |
| 9 | `GET /draft/{draft_id}/picks` | Picks already made in a live/complete draft | `backend/draft_board_service.py:296-297` | feeds `/api/draft/board` |
| 10 | `GET /league/{league_id}/matchups/{week}` | Weekly scores/pairings, one call per regular-season week — **cached per league+season+week** since 2026-08-09 (`_outlook_sleeper_fetch()`, `backend/server.py`; completed weeks never refetch — see §5.4) | `backend/outlook/league_state.py:218` via the injected fetch | feeds `/api/league/outlook` |
| 11 | `GET /league/{league_id}/transactions/{week}` | Completed transactions for one leg/week; filtered to `type=trade, status=complete` | `backend/sleeper_trades_service.py:53-68` (`fetch_week_transactions`; the 1–18 sweep is the one-time backfill for a league with no captured rows, otherwise only the live leg and the one before it — see §5.2) | not directly routed — session-init background capture only |
| 12 | `GET /players/nfl` | **Bulk player dump, ~5 MB raw / ~4.8 MB filtered.** All NFL players; FTF keeps only QB/RB/WR/TE with a `full_name` | `backend/server.py:1593,1672-1684` (`_PLAYERS_BULK_URL` / `_fetch_players_bulk`); called from `_ensure_sleeper_cache_populated` (`backend/server.py:13920-13969`) and the M0 refresh daemon (`backend/server.py:1795-1823`) | `/api/sleeper/players`, `/api/sleeper/players/warm` |
| 13 | `GET /players/nfl/adp` | Average draft position — **undocumented**, best-effort | `backend/server.py:586-615` (`_fetch_sleeper_adp`) | not routed — feeds player-DB sync only |

### 1.2 GraphQL (`https://sleeper.com/graphql`) — undocumented private API

Single endpoint; the operation is selected per-call via `operationName` +
`x-sleeper-graphql-op` header. None of this is in Sleeper's published API docs —
every shape here was captured from live browser traffic (see
`docs/plans/sleeper-write-capture-runbook.md`).

| # | Operation | Purpose | Auth | Call site |
|---|---|---|---|---|
| 14 | `league_players` | Public read: `{player_id, settings}` for every rostered player in a league — `settings.otb` flags "on the block" | none (public) | `backend/trade_block_service.py:65-87` (`fetch_league_players`) |
| 15 | `propose_trade` | **Write**: submit a real trade proposal into the user's Sleeper league. Since #413 emits a non-empty `draft_picks` list on pick trades, produced server-side by `server._sleeper_encode_ftf_picks` → `sleeper_write.encode_draft_pick` (never client-supplied) | JWT (raw, no `Bearer` prefix) | `backend/sleeper_write.py:203-273,331-337` (`build_propose_trade_body` / `propose_trade`) |
| 16 | `reject_trade` | **Write**: reject a pending proposal | JWT | `backend/sleeper_write.py:340-351` |
| 17 | `ftf_token_probe` | No-op (`{ __typename }`) — proves a captured JWT is real by exercising Sleeper's own auth middleware | JWT | `backend/sleeper_write.py:168-193` (`verify_token_live`) |

**17 distinct Sleeper endpoints/operations total** (13 REST v1 + 4 GraphQL).

### 1.3 Client-side, non-API (mobile)

These touch Sleeper's domains but are **not** JSON API calls — no FTF instrumentation
can see inside them beyond "did the WebView load" / "did the OS open the link."

| Interaction | URL | Call site | Notes |
|---|---|---|---|
| WebView page load | `https://sleeper.com/login` | `mobile/src/screens/SleeperConnectScreen.tsx:22,138-147` | Full browser navigation inside an in-app WebView; the user types their Sleeper password directly into Sleeper's own page — FTF never sees it. An injected JS poller (`INJECTED_POLLER`, lines 27-46) reads `window.localStorage.getItem('token')` from the loaded page every 800 ms and `postMessage`s it back to React Native once present. This is DOM/localStorage inspection, not a network call. |
| Deep link | `https://sleeper.com/leagues/{league_id}/trade?add_receiver_id=...` | `mobile/src/screens/TradesScreen.tsx:5171,5186` | `Linking.openURL` fallback — hands a pre-filled trade off to Sleeper's own app/site when Send-in-Sleeper isn't used/available |
| Deep link | `https://sleeper.com/leagues/{league_id}` | `mobile/src/components/SendInSleeperButton.tsx:107-108` | |
| Deep link | `https://sleeper.com/leagues/{league_id}/players` | `mobile/src/screens/FreeAgentsScreen.tsx:320` | "Add to your Sleeper roster" hand-off |

All *data* calls from mobile go through the backend proxy in
`mobile/src/api/sleeper.ts` (`getLeagues`, `getLeagueRosters`, `getLeagueUsers`,
`warmPlayerCache`) and `mobile/src/api/sendInSleeper.ts` (`getSleeperLinkStatus`,
`linkSleeperToken`, `unlinkSleeper`, `proposeTradeToSleeper`, `validateTradeSend`) —
never `api.sleeper.app` directly (confirmed: no `api.sleeper.app` or GraphQL string
literal exists anywhere under `mobile/src/`).

---

## 2. Auth model

Three distinct trust tiers:

### 2.1 Public reads (endpoints 1–14)
No credential. Sleeper's v1 REST API and the `league_players` GraphQL query are
both openly readable by anyone who knows the league id — this is how username
lookup, roster sync, draft board, trade-block import, and market-data capture all
work without the user ever authenticating to Sleeper through FTF.

### 2.2 The captured JWT — "Send in Sleeper" (flag `trade.send_in_sleeper`, default ON in `config/features.json`)
- **What it is:** Sleeper's own 365-day HS256 session JWT, the same token
  `sleeper.com`'s web client stores in `localStorage['token']` after a normal
  login. It is a **full-account credential** — whoever holds it can act as that
  Sleeper user, not just propose trades (`backend/sleeper_write.py:1-9`).
- **How it's captured:** `SleeperConnectScreen` loads `sleeper.com/login` in a
  WebView and the user logs in directly against Sleeper's page (FTF never
  handles the password). An injected poller extracts the token from
  `localStorage` and posts it to the app (`mobile/src/screens/SleeperConnectScreen.tsx:9-46`).
- **How it's proven:** `POST /api/sleeper/link` (`backend/server.py:11905-12034`)
  runs two hard gates before storing anything:
  1. **Claim match** — the JWT's `user_id` claim (decoded, unverified — JWTs are
     never signature-checked client-side since Sleeper's signing key is
     private) must equal the FTF session's `user_id`, or `403 token_user_mismatch`.
  2. **Live oracle probe** — the token is fired once at the real
     `ftf_token_probe` GraphQL no-op. Sleeper's own auth middleware is the
     signature oracle: a forged/dead/expired token gets `401`, which FTF
     surfaces as `403 token_rejected` (`backend/sleeper_write.py:164-193`).
  Only a token that clears both gates marks the session `verified` and stamps
  `users.verified_via='sleeper'` — this doubles as FTF's own account-verification
  mechanism (account-auth P1), not just a Sleeper-write credential.
- **Where it lives:**
  - **Server:** encrypted at rest with Fernet (`backend/sleeper_write.py:93-127`),
    key `SLEEPER_TOKEN_KEY` from environment/`secrets.local.env`. Stored in the
    `sleeper_credentials` table (`backend/database.py:1289-1306`,
    `token_encrypted` column). Never logged — `_post_graphql` logs status codes
    and truncated error bodies, never headers or the token itself
    (`backend/sleeper_write.py:280-328`).
  - **Client:** persisted in the iOS Keychain via `expo-secure-store` under key
    `sleeper.link.jwt` (`mobile/src/api/sendInSleeper.ts:72-110`) — **never**
    AsyncStorage, never logged. Used only to silently re-present the same proof
    to `POST /api/sleeper/link` on a fresh session (`_runReplay`,
    `mobile/src/api/sendInSleeper.ts:135-196`) so the user isn't asked to log
    into Sleeper again after every app reinstall/session eviction.
- **Lifecycle:** 365-day expiry (`token_expiry` reads the JWT's `exp` claim,
  `backend/sleeper_write.py:144-150`). `/api/trades/propose` checks
  `is_expired()` before every send and deletes the stored credential on
  `409 sleeper_expired` (`backend/server.py:12088-12090`). A Sleeper-side
  rejection at send time (`SleeperAuthError`) also deletes the credential
  (`backend/server.py:12116-12128`) — reconnecting would just recapture the
  same rejected token, so the client is told `sleeper_rejected`, not routed
  back into the login WebView. `DELETE /api/sleeper/link` (disconnect) drops
  both the server row and the Keychain copy
  (`mobile/src/api/sendInSleeper.ts:50-58`).
- **The write route itself** (`POST /api/trades/propose`,
  `backend/server.py:12036-12149`) requires `sess.get("verified")` —
  **no grace period** (`backend/server.py:12066-12069`) — because it writes
  directly into a real user's real Sleeper league; the highest blast-radius
  route in the app.

### 2.3 `SLEEPER_TOKEN_KEY` reuse
The same Fernet helper module (`sleeper_write.py`) also encrypts ESPN `espn_s2`
cookies and MFL auth cookies (`backend/server.py:10545,18407,18461,18573,19998,20112`)
— it's a generic "encrypt a third-party platform credential" utility despite the
module name. Relevant for instrumentation: a `SLEEPER_TOKEN_KEY`-unset outage
degrades ESPN/MFL cookie storage too, not just Sleeper.

---

## 3. Request/response shapes

### 3.1 Player bulk dump (`GET /players/nfl`)
- **Raw size:** ~5 MB JSON, one object per NFL player keyed by `player_id`.
- **Filtered:** `_filter_bulk_players` (`backend/server.py:1663-1669`) keeps only
  `position in {QB,RB,WR,TE}` with a non-null `full_name` — cuts ~80% of the
  payload. The filtered result is what's cached and served
  (`/api/sleeper/players` response is ~4.8 MB).
- **Cache file:** `data/.sleeper_players_cache.json` (`CACHE_DIR / ".sleeper_players_cache.json"`,
  `backend/server.py:417-422`), overridable via `FTF_PLAYERS_CACHE_FILE` for the
  UI-test harness. Written atomically — temp file in the same directory +
  `os.replace` — so no reader ever observes a partial file
  (`_atomic_write_players_cache`, `backend/server.py:1687-1709`).
- **Fields consumed:** `position`, `full_name`, plus whatever `sync_players`
  reads into the `players` table (team, `years_exp`/`rookie_year` — load-bearing
  for the rookie predicate, see §4).

### 3.2 League/roster shapes
- `GET /league/{id}` → `{settings:{playoff_week_start, playoff_teams, divisions,
  type, ...}, roster_positions:[...], scoring_settings:{bonus_rec_te,...}, season, status}`.
  FTF derives `scoring_format` (`1qb_ppr` vs `sf_tep`) from `roster_positions`
  containing `SUPER_FLEX` (or ≥2 `QB` slots) OR `scoring_settings.bonus_rec_te > 0`
  (`backend/server.py:685-721`).
- `GET /league/{id}/rosters` → `[{roster_id, owner_id, players:[...], starters:[...],
  settings:{wins, losses, ties, fpts, fpts_decimal, fpts_against, fpts_against_decimal, division}}]`.
  Null entries can appear inside `players` for empty slots — handled defensively
  (living-memory G-004).
- `GET /league/{id}/users` → `[{user_id, display_name, username, avatar,
  metadata:{team_name}}]`.
- `GET /league/{id}/traded_picks` → `[{round, season(str), roster_id(orig),
  owner_id(current), previous_owner_id}]` (`backend/server.py:10187-10200`).
  Consumers: the owned-pick sync daemon, the Draft Room, and since #413 the
  propose + validate routes on pick sends (`_sleeper_pick_holder_index` — an
  absent `(season, round, orig)` key means the original roster still holds it).
- `GET /league/{id}/drafts` → `[{draft_id, status: pre_draft|drafting|complete,
  season(str), type, ...}]` (`backend/server.py:10203-10219`).

### 3.3 GraphQL shapes
- `league_players` rows: `{player_id, settings:{otb: <roster_id>|null,
  otb_added_at: <epoch_ms>|absent}}` (`backend/trade_block_service.py:10-24`). A
  flag only counts if the flagging roster still owns the player — Sleeper never
  clears `otb` on trade/drop (stale-flag caveat, same file lines 18-21).
- `propose_trade` variables: parallel arrays `k_adds/v_adds` (player_id →
  receiving roster_id) and `k_drops/v_drops` (player_id → giving roster_id) —
  **every traded player appears in both arrays**, paired positionally
  (`backend/sleeper_write.py:18-21,244-257`). `draft_picks` and `waiver_budget`
  are inlined into the query string, not sent as GraphQL variables. Inlined
  object args must be GraphQL **literals** (bare keys — `{sender:1}`), not JSON;
  `_graphql_object_literal()` does that encoding. `draft_picks` is unaffected —
  a list of strings is spelled identically in both syntaxes.
- `draft_picks` elements (#413, `sleeper_write.encode_draft_pick`):
  `"<orig>,<season>,<round>,<from>,<to>"` — `orig` = the pick's ORIGINAL-owner
  roster id (the `draft_picks` grid row's `original_roster_id`), `from` = the
  roster giving the pick up, `to` = the roster receiving it. Give side encodes
  `from = my roster, to = theirs`; receive side flips them. Both live captures
  (`"11,2026,1,1,2"`, `"1,2027,4,2,1"`, runbook §C2) are original-owner picks,
  so field 1 is **captured, not confirmed, on a pick that has changed hands**
  (living-memory Q-037; closed by the #413 TestFlight step 3). If Sleeper wants
  the current holder there, only acquired picks fail — visibly, as a GraphQL
  error → 502 `sleeper_write_failed` with `detail`.
- ⚠️ **`waiver_budget`'s element type is unresolved — FAAB is unimplemented,
  not merely untested.** The 2026-07-02 capture only ever showed
  `waiver_budget: []`, so the `[{sender, receiver, amount}]` shape in
  `ProposeTradeRequest` is an **inference**, never an observation. The public
  `__schema` dump cited in
  [`../plans/sleeper-pending-trades-feasibility-2026-08-12.md`](../plans/sleeper-pending-trades-feasibility-2026-08-12.md)
  says both `draft_picks` and `waiver_budget` are `[String]` — and it is
  demonstrably right about `draft_picks`, which corroborates it. If it is right
  about `waiver_budget` too, the shape is wrong at the *type* level, which the
  bare-key encoding fix does not address. No caller populates FAAB today;
  resolve against a real capture before one does (living-memory Q-016).

---

## 4. Error modes

| Failure | Where handled | Client-visible result |
|---|---|---|
| Username not found / null response | `backend/server.py:13661-13664` | `404 User not found` |
| Sleeper `5xx` on user lookup | `backend/server.py:13687-13690` | `503 sleeper_unavailable` (distinguished from "genuinely no such user" so the UI doesn't send the user down a dead end retyping their name) |
| Sleeper unreachable (`URLError`) | `backend/server.py:13693-13696`, and per-endpoint elsewhere | `503 sleeper_unavailable` |
| Empty leagues list because Sleeper failed vs. genuinely no leagues | `backend/server.py:13724-13730` | `503` only when BOTH the live fetch failed AND no locally-cached leagues exist — an empty-but-successful response is not conflated with an outage |
| Rosters/`traded_picks`/`drafts`/`league_players` fetch failure (best-effort helpers) | `backend/server.py:10178-10219`, `backend/trade_block_service.py`, `backend/sleeper_trades_service.py` | Fail-soft to `[]` / `None` — the caller degrades to "previous snapshot kept" or "nothing to show," never a fabricated result |
| SSL cert store unavailable (macOS dev) | `backend/server.py:447-471,557-569` | One-time fallback to an unverified SSL context with a logged warning; retried automatically on the same request |
| Fixture miss in `FTF_TEST_MODE`/replay mode | `backend/server.py:527-539` | Raises `HTTPError(599, "ftf-fixture-miss")` — a **test bug**, never routed as a real Sleeper failure |
| JWT expired (`exp` claim past) | `backend/server.py:11960-11961` (link), `12088-12090` (propose) | `400 token_expired` (link) / `409 sleeper_expired` (propose, credential deleted) |
| JWT claim doesn't match session user | `backend/server.py:11967-11970` | `403 token_user_mismatch` |
| Live oracle rejects the token (forged/dead) | `backend/server.py:11982-11985` | `403 token_rejected` |
| Oracle unreachable (network/config) — inconclusive | `backend/server.py:11986-11988` | Link stores but `verified` stays `false`; not treated as rejection |
| Sleeper rejects `propose_trade` at send time | `backend/server.py:12116-12128` | `409 sleeper_rejected` + truncated detail; credential deleted (recapturing would just replay the same rejected token, so the client is told NOT to reopen the login WebView) |
| GraphQL error surfaced as HTTP 200 with an `errors` array | `backend/sleeper_write.py:318-325` | Classified by keyword sniffing (`auth`/`unauth`/`token`/`forbidden`/`login` → `SleeperAuthError`; everything else → generic `SleeperWriteError`) |
| Cloudflare 1010 ban (bot-signature detection) | Mitigated proactively, not caught reactively — `sleeper_write.py:43-59`, `trade_block_service.py:51-62`, `sleeper_trades_service.py:42-50` all send a real Chrome UA + `origin`/`referer` headers on every write/GraphQL call. Plain `urllib` UAs (`Python-urllib/x.y`) trip this instantly | N/A (prevention, not error handling) |
| No `cryptography` package / no `SLEEPER_TOKEN_KEY` set | `backend/sleeper_write.py:93-104` | `503 sleeper_unconfigured` — feature goes dark rather than storing plaintext |
| Numeric league id misrouted to Sleeper-only code for an ESPN/MFL/Fleaflicker league | living-memory `G-014` (`living-memory/GOTCHAS.md:23,135-142`) — **real historical incident**: an MFL league's `draft_picks` were wiped on every app open because a numeric MFL id (all platform-native ids are numeric, not Sleeper-exclusive) fell into the Sleeper roster-sync path, whose empty REPLACE deleted real data on a Sleeper fetch flake. Fixed by routing on `is_linked_platform_league()`, not `.isdigit()` alone (`backend/server.py:13777`, `19342-19343`, and the M0 owned-picks guard at `14652-14661`) | — |
| `roster.players` containing `null` entries | living-memory `G-004` | Filtered defensively wherever roster player lists are consumed |
| Sleeper username lookup returns different casing than typed | living-memory `G-006` | FTF preserves the user-typed username for display, uses the Sleeper-returned id for lookups |
| Stale `.sleeper_players_cache.json` (pre-M0, no refresh path) | living-memory `G-008` | Superseded by the M0 refresh daemon (§5) — this gotcha predates the daily-tick fallback guard |

---

## 5. Call frequency / caching

### 5.1 Player bulk dump — the expensive one
- **TTL:** `_PLAYERS_CACHE_TTL_SECONDS = 20 * 3600` (20 h — deliberately under 24 h
  "so a daily tick never skips on jitter," `backend/server.py:1592`).
- **Primary refresh trigger:** `POST /api/cron/players-refresh`
  (`backend/server.py:15999-16016`) — external cron (Render), `X-Cron-Secret`
  auth, `?force=1` to bypass TTL. Always responds `202` immediately; the fetch
  runs on a daemon thread (Render's "cron" is an HTTP POST into the single web
  worker — a ~45 s inline fetch would stall a request worker,
  `backend/server.py:1575-1577`).
- **Fallback trigger:** the daily-tick handler checks cache age and starts the
  same async refresh if the dedicated cron was missed — **prod only**
  (`_IS_PROD_ENV`); a local/SQLite dev run never auto-refreshes the shared dev
  cache (`backend/server.py:15938-15957`).
- **Cold-start trigger:** `_ensure_sleeper_cache_populated`
  (`backend/server.py:13920-13969`) — any request that needs the cache and finds
  it empty fetches synchronously. Shared by `/api/sleeper/players`,
  `/api/sleeper/players/warm`, and the browser extension's cold-start path so
  the extension can work even as the very first hit on a fresh instance.
- **Kill switch:** `FTF_PLAYERS_REFRESH=0` env var disables all refresh
  (`backend/server.py:1595`), no deploy required.
- **Single-flight:** a lock (`_players_refresh_lock`) ensures only one refresh
  runs at a time; concurrent triggers no-op rather than stacking fetches
  (`backend/server.py:1825-1853`).
- **Invalidation on a successful refresh** is a strict 6-step order — disk
  write → in-memory cache swap → players-table resync → DP value-map clear →
  pool rebuild (build-new-then-rebind, never clear-in-place) → generation bump
  — documented in full at `backend/server.py:1712-1734`. Getting this order
  wrong was explicitly called out as a real regression risk (D1 in the
  surrounding comments).
- **Mobile client-side:** `warmPlayerCache()` is called once per app launch
  (`mobile/src/api/sleeper.ts:52-85`, `warmedThisLaunch` guard) hitting
  `/api/sleeper/players/warm` — a tiny `{ok, count}` response, not the 4.8 MB
  body, since mobile never reads player data from this call (the web app uses
  the full `/api/sleeper/players` body instead).

### 5.2 Per-session-init background sync (best-effort, non-blocking)
Fired from `/api/session/init`'s background daemon on every league switch/login,
each independently flag-gated. Payloads that are **immutable for the length of
one init** — the v1 `rosters` list and the `/league/{id}` meta blob — are
fetched ONCE by the daemon and handed to every consumer; everything else is a
fresh live fetch with no shared cache.

| Sync | Flag | Endpoints hit | Site |
|---|---|---|---|
| Shared rosters fetch | `sleeper.trade_block` \| `market.roster_history` \| `picks.owned_sync` | 1× `rosters`, reused by all four consumers below | `_session_init_background_writes`, `backend/server.py` |
| Shared league meta | (unconditional for numeric, non-platform-linked ids) | 1× `/league/{id}`, reused by scoring auto-detect, the FB #41 team-count persist and the owned-pick sync | `_league_meta()` in the same daemon |
| Trade-block import | `sleeper.trade_block` | 1× `league_players` GraphQL (rosters shared) | `sync_league_trade_block`, `backend/trade_block_service.py` |
| Owned draft-pick sync | `picks.owned_sync` | 1× `traded_picks` + 1× `drafts` (rosters + meta shared); MFL leagues re-derive with no Sleeper reads | `_sync_sleeper_owned_picks`, `backend/server.py` |
| Trade-transaction capture | `market.trade_capture` | **≤2 calls** — `transactions/{week}` for the live leg and the one before it. The full `1..18` sweep runs ONCE, as the first-time backfill for a league with no captured rows; in the offseason an already-swept league fetches **1** (leg 1, where Sleeper books every offseason trade) | `sweep_weeks` / `sync_league_trades`, `backend/sleeper_trades_service.py` |
| Executed-trade matcher | `suggestion.telemetry` | 0 — takes the shared rosters map | `match_league_trades(roster_map=…)`, `backend/suggestion_telemetry.py` |
| Rookie-draft status refresh | (unflagged) | 0 in steady state; up to 3 (`/league/{id}`, `drafts`, `rosters`) when the per-status TTL has expired — 12 h once a league reads `drafted` | `_refresh_league_draft_status`, `backend/server.py` |

**Per-init upstream budget for a Sleeper league** (steady state, all flags ON,
draft-status TTL warm): **7 calls in season, 6 in the offseason** — meta,
rosters, GraphQL `league_players`, `traded_picks`, `drafts`, and ≤2
`transactions/{week}`. Before 2026-09-03 the same init cost **26** (29 on a
draft-status refresh): 18 transaction legs, 3 rosters reads and 2 meta reads.

All of these are wrapped in bare `try/except` so a Sleeper flake just leaves the
previous snapshot in place — "best-effort" is load-bearing language throughout
these modules, not a suggestion. A shared fetch that fails is handed on as
`None`, and every consumer falls back to fetching for itself.

### 5.3 Draft Room polling (`GET /api/draft/board`, flag `draft.room`)
Server-side cache with a state-dependent TTL and a circuit breaker
(`backend/draft_board_service.py:161-167`):

| State | Refresh TTL |
|---|---|
| `UPCOMING` | 300 s |
| `LIVE` | 20 s |
| `COMPLETE` | 86,400 s (1 day) |
| `UNAVAILABLE` | 60 s |

- League metadata (`drafts`/`rosters`/`users`/`traded_picks`) has its own
  slower-moving TTL: 300 s (`_LEAGUE_META_TTL_SECONDS`).
- **Circuit breaker:** opens after 3 consecutive fetch failures
  (`_BREAKER_FAILS`), stays open 120 s (`_BREAKER_OPEN_SECONDS`), then
  half-opens.
- **Budget:** max 3 upstream refresh cycles per minute per draft
  (`_BUDGET_PER_MIN=3`, `_BUDGET_WINDOW_SECONDS=60`) — caps how fast client
  polling can translate into upstream Sleeper load.
- **Client poll:** mobile polls its OWN `/api/draft/board` endpoint (not
  Sleeper) every 15 s, gated by `draft.live_poll`, only while focused +
  foregrounded + `state:live` (`config/features.json` comment at
  `_comment_rookie_draft`).

### 5.4 Outlook weekly fan-out (`GET /api/league/outlook`, flag `outlook.odds`)
Phase 1 walks EVERY regular-season week (`matchups/{week}`, up to 14 calls), so
this was the worst uncached surface in the app. Since 2026-08-09 the fan-out
goes through `_outlook_sleeper_fetch()` (`backend/server.py`, next to the
route), which sits in the `fetch=` seam `build_league_state` already injects —
`backend/outlook/` is untouched, and every MISS still goes through
`_sleeper_get`, so the cache's effect is visible in apihealth as `league.matchups`
`api_call` events that stop happening.

Tiered by the grain of the data, keyed `(league_id, season, week)`:

| Week | Rule | TTL |
|---|---|---|
| Below the scored high-water mark | A later week has already scored ⇒ the rows can never change | **none** (immutable, cached for the process's life) |
| At the high-water mark (or week 1 preseason) | The live/in-progress week | 900 s |
| Above it | Not yet played — pairings/schedule only | 3,600 s |

Both tiers are bounded at `_OUTLOOK_WEEK_CACHE_MAX` (250) entries, evicted
oldest-inserted-first; matchup rows carry per-player point maps, so the bound is
memory, not correctness. Steady state per league: one short-TTL call for the
live week, a few hourly schedule calls, and **exactly one upstream call per week
that completes** — free forever after.

The league-meta / `rosters` / `users` reads stay live **on purpose**: `rosters`
carries the W/L/points-for standings the odds are computed FROM, and a stale
standing is a wrong answer, not a slow one.

### 5.5 Uncached, live-per-request
- `GET /api/trades/validate` (pre-send warnings) — live `league` meta + `rosters`
  fetch on every call, by design ("Sleeper remains the authority" — the point is
  freshness right before a send), `backend/server.py:20225-20284`.
- `POST /api/trades/propose` — live `rosters` fetch to resolve both roster_ids
  server-authoritatively (never trusts a stale client-supplied roster_id for the
  proposer), `backend/server.py:12095-12107`.
- `/api/sleeper/rosters/<id>` and `/api/sleeper/league_users/<id>` — no caching
  layer visible in `backend/server.py:13768-13817`; every call is a live proxy
  (Sleeper-side leagues only — platform-imported leagues serve DB snapshots
  instead, no Sleeper call at all).

---

## 6. Instrumentation guidance

### 6.1 Safe to log
- HTTP status code, latency, endpoint **class** (not the raw URL with ids —
  bucket by route template, e.g. `sleeper.rosters`, `sleeper.graphql.propose_trade`)
- `league_id` (not PII — Sleeper league ids are not tied to a person off-platform)
- Player-cache dump size (byte count) and age-in-seconds (`_players_cache_age_seconds`,
  `backend/server.py:1627-1632`, already logged today)
- Circuit-breaker state transitions (open/half-open/closed) and budget-exceeded events
  for the Draft Room poller
- Error **kind** on `SleeperWriteError` (`auth`/`network`/`config`/`error` —
  `backend/sleeper_write.py:66-77`) — a closed, small enum, safe to log verbatim
- `verified` boolean and `verified_via` string on session events — these are
  outcomes, not credentials
- Sleeper `sleeper_user_id` claim (it's the same value as FTF's `user_id` for
  Sleeper-origin accounts — already the join key everywhere)
- Transaction/draft/roster **counts** (e.g. "2 week-sweeps returned N trade rows")

### 6.2 Must redact / never log
- **The JWT itself**, in any form — full, truncated, or hashed-without-a-salt-pepper
  scheme that could be reversed by a small ~365-day-token search space. The
  codebase's own convention: `_sleeper_record`'s cassette scrubber blanks any
  field whose key contains `"token"` (`backend/server.py:509-517`); `_post_graphql`
  logs response bodies truncated to 500 chars but never request headers
  (`backend/sleeper_write.py:280-328`). Any new instrumentation must follow the
  same rule — **redact by key name, not by hoping the value never appears.**
- The `authorization` header value on any GraphQL call (raw JWT, no `Bearer` prefix —
  `backend/sleeper_write.py:288-293`)
- The Fernet ciphertext AND the `SLEEPER_TOKEN_KEY` itself
- The full player-cache payload body (4.8 MB — log size/age, never contents, in
  any event pipeline with a payload-size budget)
- Sleeper usernames/display names in analytics events beyond what's already
  covered by existing PII rules for `users` table data — this doc doesn't
  change that policy, just flags that usernames flow through several of these
  call sites (`/api/sleeper/user/<username>`, `/api/extension/auth`,
  `/api/account/link-sleeper`)
- Raw GraphQL error bodies beyond the existing 500-char truncation — they can
  echo back request variables in some Sleeper error formats

### 6.3 Client-side vs. server-side — where can instrumentation even see the call?

**Server can see (backend-side events, all 17 endpoints in §1.1–1.2):** every
REST v1 read, every GraphQL op (`league_players`, `propose_trade`, `reject_trade`,
`ftf_token_probe`). All of it already funnels through two chokepoints —
`_sleeper_get` (`backend/server.py:524-579`, REST) and `_post_graphql`
(`backend/sleeper_write.py:280-328`, GraphQL) — plus three smaller siblings that
don't share the chokepoint (`trade_block_service.fetch_league_players`,
`sleeper_trades_service.fetch_week_transactions`, and `_fetch_rosters` in
`trade_block_service.py`). **A single instrumentation seam in `_sleeper_get` and
`_post_graphql` would cover the large majority of calls**; the three siblings
need their own hook or a refactor to share the chokepoint — flag this as a
prerequisite decision for the build, not an oversight to patch around silently.

**Server CANNOT see (client-side-only, needs client events):**
- The WebView loading `sleeper.com/login` — FTF has no visibility into that
  page load, any redirects, MFA challenges, or failed-login attempts on
  Sleeper's side. The only observable signal is downstream: whether
  `POST /api/sleeper/link` was ever called and what it returned.
- Whether the injected `localStorage` poller ever fires (i.e., whether the user
  successfully logged in) before the 800 ms-interval timeout — if a user abandons
  the WebView without logging in, the client has this signal and the server does
  not. Worth a client event (`sleeper_connect.abandoned` or similar) if funnel
  visibility into this step matters.
- The three `Linking.openURL` deep-link hand-offs
  (`SendInSleeperButton.tsx:107-108`, `TradesScreen.tsx:5171-5186`,
  `FreeAgentsScreen.tsx:320`) — the OS opens Sleeper's app/site and FTF gets no
  callback on what the user did there. Only "the deep link was tapped" is
  observable, client-side only.
- Keychain read/write outcomes for the persisted JWT (`getPersistedSleeperToken`,
  `persistSleeperToken`, `mobile/src/api/sendInSleeper.ts:72-110`) — these are
  device-local and fail silently by design (`catch {}`); if failure-rate
  visibility is wanted, it needs an explicit client event, since today a
  Keychain write failure is deliberately invisible ("non-fatal; worst case is
  one manual recapture").

---

*Compiled 2026-08-09 by grepping `api.sleeper.app`, `sleeper.com`, and
`sleeper.app` across `backend/` and `mobile/src/`, then reading every call site.
Re-run the grep before trusting line numbers after any Sleeper-adjacent change —
`backend/server.py` alone is ~20k lines and routes move.*
