# MyFantasyLeague (MFL) integration — reference

> Feeds an instrumentation build agent. Scope: the full MFL surface as it exists
> in code today (2026-08-11), not the roadmap. Primary modules:
> [`backend/mfl_service.py`](../../backend/mfl_service.py) (pure/offline-testable
> HTTP client + parsers, reads) and
> [`backend/mfl_write.py`](../../backend/mfl_write.py) (writes — "Send in MFL",
> flag `trade.send_in_mfl`). Call sites live in `backend/server.py`,
> `backend/draft_board_service.py`, `backend/draft_status.py`, and
> `backend/database.py`.

## Table of contents

1. [Endpoints used](#1-endpoints-used)
2. [Auth model](#2-auth-model)
3. [Request/response shapes](#3-requestresponse-shapes)
4. [Error modes](#4-error-modes)
5. [Call frequency / caching](#5-call-frequency--caching)
6. [Instrumentation guidance](#6-instrumentation-guidance)
7. [Write surface — "Send in MFL"](#7-write-surface--send-in-mfl)

---

## 1. Endpoints used

All MFL calls are `GET` (except `login`, which is `POST`). All export calls
carry `&JSON=1` and hit the league's assigned `wwwNN.myfantasyleague.com`
host — **never** `api.myfantasyleague.com` for league-scoped data (see §2 for
why). Base URL builder: `mfl_service.export_url(host, year, type_, league_id)`
→ `https://{host}/{year}/export?TYPE={type_}&L={league_id}&JSON=1`.

| # | Purpose | URL pattern | Method | Params | Call site(s) |
|---|---|---|---|---|---|
| 1 | Resolve a bare league id to its `wwwNN` host | `https://api.myfantasyleague.com/{year}/home/{id}` | GET (redirect only — Location header read, not followed) | none | `mfl_service.py:132` `resolve_host()`; called from `server.py:19708` (`_mfl_resolve`), `server.py:19867` (`mfl_leagues` backfill), `server.py:19916` (`mfl_import`), `server.py:20022` (`_mfl_import_league_authed`) |
| 2 | Login (authenticated flow, #177) | `https://api.myfantasyleague.com/{year}/login` | POST | body `USERNAME`, `PASSWORD`, `XML=1` | `mfl_service.py:187` `login()`; called from `server.py:20095` (`mfl_auth_link`) |
| 3 | List the signed-in user's leagues | `https://api.myfantasyleague.com/{year}/export?TYPE=myleagues&YEAR={year}&FRANCHISE_NAMES=1&JSON=1` | GET | `TYPE=myleagues`, `YEAR`, `FRANCHISE_NAMES=1`, `JSON=1` + `Cookie: MFL_USER_ID=…` | `mfl_service.py:227` `fetch_my_leagues()`; called from `server.py:20097` (`mfl_auth_link`), `server.py:20158` (`mfl_auth_import`) |
| 4 | League metadata (franchises, starters/lineup config) | `https://{host}/{year}/export?TYPE=league&L={id}&JSON=1` | GET | `TYPE=league` | `mfl_service.fetch_league_bundle()` (part of the 5-export bundle) and `fetch_scoring_inputs()` — both call the shared `_fetch_one` |
| 5 | Rosters | `https://{host}/{year}/export?TYPE=rosters&L={id}&JSON=1` | GET | `TYPE=rosters` | `fetch_league_bundle()` only |
| 6 | Future draft picks (owned-pick ledger) | `https://{host}/{year}/export?TYPE=futureDraftPicks&L={id}&JSON=1` | GET | `TYPE=futureDraftPicks` | `fetch_league_bundle()` (link/import time) AND standalone `mfl_service.py:388` `fetch_future_draft_picks()` (refresh cadence, §5) |
| 7 | Players DB (id → name/position) | `https://{host}/{year}/export?TYPE=players&L={id}&JSON=1` | GET | `TYPE=players` | `fetch_league_bundle()` only — best-effort (degrades to `{}`) |
| 8 | League rules (scoring config, for format detection #201) | `https://{host}/{year}/export?TYPE=rules&L={id}&JSON=1` | GET | `TYPE=rules` | `fetch_league_bundle()` (best-effort) and `fetch_scoring_inputs()` (best-effort) |
| 9 | Draft results (draft-completion signal, #207) | `https://{host}/{year}/export?TYPE=draftResults&L={id}&JSON=1` | GET | `TYPE=draftResults` | `mfl_service.py:357` `fetch_draft_results()`; called from `server.py:11793` (`_detect_league_draft_status`, MFL branch, function starts `server.py:11745`) and `draft_board_service.py:311` (`PlatformFetchers.mfl_draft_results`) |
| 10 | Pending trades (trade-lifecycle read, "Send in MFL" — **owner-restricted**, cookie required) | `https://{host}/{year}/export?TYPE=pendingTrades&L={id}&JSON=1` | GET | `TYPE=pendingTrades` + `Cookie: MFL_USER_ID=…` | `mfl_service.fetch_pending_trades()`; called from `server.py` `GET /api/mfl/pending-trades` (flag `trade.send_in_mfl`) — NOT best-effort: auth failures must surface as re-sign-in, not read as "no pending trades" |

**Full call-site index (`file:line`):**

- `backend/mfl_service.py:132` — `resolve_host()` hits endpoint #1.
- `backend/mfl_service.py:193` — `login()` POSTs endpoint #2.
- `backend/mfl_service.py:231` — `fetch_my_leagues()` hits endpoint #3.
- `backend/mfl_service.py:286` — `_fetch_one()`, the shared single-export GET used by endpoints #4–#9 (`export_url` at line 274–278).
- `backend/mfl_service.py:328` — `fetch_league_bundle()` fetches endpoints #4–#8 in one call (spaced ≥1s apart live).
- `backend/mfl_service.py:357` — `fetch_draft_results()` fetches endpoint #9 standalone.
- `backend/mfl_service.py:388` — `fetch_future_draft_picks()` fetches endpoint #6 standalone.
- `backend/mfl_service.py:410` — `fetch_scoring_inputs()` fetches endpoints #4 + #8 only (lightweight backfill path).
- `backend/server.py:19708` — `_mfl_resolve()` calls `resolve_host` when no host is embedded in the pasted URL.
- `backend/server.py:19744` `mfl_link` route — calls `fetch_league_bundle` (preview + import).
- `backend/server.py:19838` `mfl_leagues` route — read-only list; conditionally calls `resolve_host` + `fetch_scoring_inputs` for a one-shot #201 backfill per league per process.
- `backend/server.py:19886` `mfl_import` route — calls `resolve_host` (if host missing) + `fetch_league_bundle` (manual refresh).
- `backend/server.py:20011` `_mfl_import_league_authed()` — calls `resolve_host` (if needed) + `fetch_league_bundle`, cookie-attached.
- `backend/server.py:20069` `mfl_auth_link` route — calls `login` + `fetch_my_leagues`.
- `backend/server.py:20126` `mfl_auth_import` route — calls `fetch_my_leagues`, then `_mfl_import_league_authed` per requested league (sequential, ≥1s spaced).
- `backend/server.py:11745` `_detect_league_draft_status()` (MFL branch at line 11785–11793, inside the shared draft-status detector) — calls `fetch_draft_results`.
- `backend/server.py:11809` `_refresh_mfl_future_picks()` — calls `fetch_future_draft_picks`.
- `backend/draft_board_service.py:309` `PlatformFetchers.mfl_draft_results()` (Draft Room live board) — calls `mfl_service.fetch_draft_results`, gated by feature flag `draft.mfl`.

## 2. Auth model

**Public leagues need no credentials.** All read endpoints (league, rosters,
futureDraftPicks, players, rules, draftResults, myleagues) work unauthenticated
against a public league — this is MFL's "official, sanctioned export API"
(module docstring, `mfl_service.py:4`), the reason MFL was picked over
scraping ESPN.

**Private leagues** pass the user's MFL session cookie verbatim as
`Cookie: MFL_USER_ID=<value>` on every league-scoped export request (both the
manual/public-import flow when a stored cookie exists, and the authenticated
flow below). There is no separate "MFL API key" — the credential *is* the
session cookie MFL's own `/login` issues.

**Two linking flows coexist:**

1. **Manual/public flow** (`mfl.link` flag) — operator pastes a league URL or
   id; `POST /api/mfl/link` previews franchises, then imports on a second call
   with `franchise_id` chosen. No MFL credentials involved unless the league
   was previously auth-linked (falls back to a stored cookie via
   `_mfl_cookie_for`).
2. **Authenticated flow** (`mfl.auth_link` flag, feedback #177) —
   `POST /api/mfl/auth-link {username, password, year}` → `mfl_service.login()`
   POSTs `USERNAME`/`PASSWORD`/`XML=1` to `{api_host}/{year}/login`; MFL
   responds with `<status MFL_USER_ID="…">OK</status>`. That `MFL_USER_ID`
   value (documented by MFL as "may contain `+`, `/` and/or `=`" — i.e. it's a
   base64-shaped opaque session credential, not literally a user id) becomes
   the `Cookie` header for every subsequent request, including
   `TYPE=myleagues&FRANCHISE_NAMES=1` (endpoint #3), which returns the user's
   leagues *with the user's own franchise_id already resolved* — the reason
   the authed import (`POST /api/mfl/auth-import`) skips the manual
   choose-team step entirely.

**Password handling (hard rule, enforced by code + comments):** the password
is sent once, in a POST body (never a URL query string — server.py:19980–19986
and mfl_service.py:174 both call this out explicitly as "for better
security"), used for that single login call, and is deleted from the local
variable immediately after (`del password` at `server.py:20096`). It is never
persisted and never logged — no log line in the auth routes carries username
or password.

**What IS persisted:** the `MFL_USER_ID` cookie only, in `mfl_credentials`
(`backend/database.py:1339`) — Fernet-encrypted at rest using the same
`SLEEPER_TOKEN_KEY` as Sleeper/ESPN credentials
(`_sleeper_write.encrypt_token`/`decrypt_token`). If the encryption key isn't
configured in a deployment, storage fails closed to **session-only**: the
cookie lives in the in-memory Flask session dict (`sess["mfl_cookie"]`) and
dies with it — it is never written to the persisted-session row (which
serializes named identity fields only), and never falls back to plaintext DB
storage. `mfl_username` is stored alongside as a display-only identifier
(never a secret).

**Disconnect (`DELETE /api/mfl/auth-link`, 2026-08-12):** the user-facing
removal path for the stored sign-in, added in the same pass as
`DELETE /api/espn/link` (the ESPN incident — a captured credential with no
removal path short of a production-DB delete). Session-authed, user-scoped,
idempotent; clears BOTH storage locations — the encrypted `mfl_credentials`
row (`delete_mfl_credential`) and the key-less-deployment session-only copy
(`sess["mfl_cookie"]`) — so `GET /api/mfl/auth-link` reports
`{connected: false}` afterward whichever path stored it. No MFL egress.
Surfaced as "Disconnect MFL sign-in" in mobile Settings → Account
(`settings.mfl-disconnect`, destructive confirm). Before this route, the
only deletions were internal dead-cookie cleanup (auth-import/propose paths
on `MflAuthError`). `POST /api/mfl/link` stores no credential and needs no
DELETE.

**Franchise identification:** MFL leagues are organized around numeric
franchise ids (`f0001`, etc. — normalized to bare strings like `"1"` in
parsed output). FTF maps:
- the linking user's own franchise → their real FTF `user_id`;
- every *other* franchise in the league → a synthetic member id
  `mfl:{league_id}.f{franchise_id}` (`_mfl_member_id`, `server.py:19692`) —
  same non-identifying-id class as unlinked ESPN/Sleeper members; MFL owner
  emails/names are never harvested (MFL ToS).

**Rate-limit/registration note (auth-adjacent):** MFL asks unregistered
clients to identify themselves via a fixed `User-Agent`
(`MFL_USER_AGENT` env var, defaults to
`"FantasyTradeFinder/1.0 (+https://fantasytradefinder.app)"`) and to space
requests ≥1s apart. Registered clients (a separate MFL operator step — form +
phone validation, tracked in
`docs/plans/multi-platform-linking-plan-2026-07-17.md` §9 Q1, not yet done as
of this doc) get higher limits. This is a politeness/identification contract,
not a credentialed auth path — no token is issued for it.

> **The User-Agent is load-bearing, not just polite (observed 2026-08-11).**
> MFL has answered export requests carrying an empty `User-Agent` with an
> **empty body**, while the same request with `MFL_USER_AGENT` set returned
> data (observed against league 62846, host `www45`,
> `export?TYPE=futureDraftPicks`). Enforcement appears **intermittent** — a
> later same-day probe got data on all UA variants — which makes it worse,
> not better: a stripped header can silently blank responses at any time
> rather than erroring. Every read AND write path must send the UA.
> `qa/verify-mfl-send.py` §B re-probes this in its no-auth section and
> reports whichever behavior it sees.

## 3. Request/response shapes

### Fields consumed (per export)

- **`league`** — `league.franchises.franchise[]` → `{id, name}` (franchise
  roster of the league); `league.starters.position[]` → `{name, limit}`,
  scanned for the `QB` row's `limit` string to derive max startable QBs
  (superflex detection, #201); `league.id`, `league.name`,
  `league.franchises.count`.
- **`rosters`** — `rosters.franchise[]` → `{id, player[]}`, each
  `player` → `{id}` (MFL player id only — **no position on the roster
  entry**, hence the separate `players` export fetch).
- **`players`** — `players.player[]` → `{id, name, position}`. `name` arrives
  `"Last, First"` and is flipped to `"First Last"` by `_flip_name()` to match
  the DynastyProcess crosswalk's forename-first convention. Team defenses
  (e.g. `"Bills, Buffalo"`) flip harmlessly since they're out of the skill-
  position pool anyway.
- **`futureDraftPicks`** — `futureDraftPicks.franchise[]` → `{id,
  futureDraftPick[]}`, each pick → `{year, round, originalPickFor}`. Parsed
  into `{franchise_id, year, round, original_owner}` by
  `parse_future_picks()`.
- **`rules`** — `rules.positionRules[]` → `{positions (pipe-delimited
  string), rule[]}`, each rule → `{event, points}`. Only the `event == "CC"`
  (every reception caught) rule is read, comparing TE vs WR per-reception
  points for TE-premium detection (#201).
- **`draftResults`** — consumed by `draft_status.mfl_verdict()` (not
  `mfl_service` itself) — MFL pre-populates the entire pick grid before the
  draft, so an undrafted pick's `player` field is `""`; completion is
  `count(player != "") == len(draftPick)`. `draftUnit` is a **list** when the
  league drafts by division/conference (multi-unit), a bare dict otherwise —
  `mfl_verdict` aggregates a single verdict across all units.
- **`myleagues`** (authenticated only) — `leagues.league[]` → `{league_id,
  name, url, franchise_id, franchise_name}`. `host` is parsed out of `url`
  (`parse_host_from_url`); `league_id` falls back to parsing it out of `url`
  when the field itself is absent.

### MFL's JSON quirks handled by the parser

- **Bare-dict-vs-list collapse:** MFL's XML→JSON conversion returns a bare
  dict when a collection has exactly one member, and a list otherwise.
  Normalized everywhere via `_as_list()` (`mfl_service.py:423`).
- **Text-node wrapping:** scalar XML text nodes sometimes arrive as
  `{"$t": "1.5*"}` instead of a bare string (seen in `rules` scoring values,
  which can carry a trailing `*` for "per stat unit" annotations). Unwrapped
  by `_txt()` (`mfl_service.py:596`).

### The name-cleaning pipeline (`_clean_text`)

`mfl_service._clean_text()` (`mfl_service.py:446`) is the single normalizer
every MFL display string passes through — franchise/league names (via
`parse_bundle`, `fetch_my_leagues`) and the one-time DB backfill
(`database._backfill_mfl_name_entities()`, boots on every process start,
idempotent — a clean row is never rewritten). It runs, **in order**:

1. **Entity-unescape until stable** (up to 2 passes — covers double-escaped
   entities like `&amp;#201;`). Fixes #210/#258: MFL names can arrive with
   HTML entities, e.g. `'Éire Rebels'` served as `'&#201;ire Rebels'`.
2. **Strip a fixed markup-tag allowlist** (`_MARKUP_TAG` regex — `b`, `i`,
   `u`, `strong`, `em`, `font`, open or close, any attributes, case-
   insensitive, including malformed close tags that still carry an
   attribute like `</font color>`). Fixes #282 (a #258 reopen): MFL lets
   franchise owners style their team name with inline HTML-ish markup, and
   that markup itself arrives **entity-encoded on the wire** — step 1 must
   run first to turn `&lt;font color = Green&gt;` into the literal
   `<font color = Green>` before step 2 can strip it.
3. **Collapse whitespace runs** to single spaces, then trim.

**Real captured examples** (prod league 62846, "The Dependables League",
documented in `docs/feedback/items/258-mfl-name-entities/status.md`):

| Franchise | Raw MFL string | Cleaned |
|---|---|---|
| f0001 | `<b><font color = Green>Eir</font color><font color = White>e Reb</font color><font color = Orange>els</font color></b>` | `Eire Rebels` |
| f0012 | `<b><font color= Green>North London Rams</b>` (malformed — no closing `</font>`, only a trailing `</b>`) | `North London Rams` |

The tag allowlist is intentionally scoped (not a blanket `<[^>]*>` strip) so a
team name with a literal `<` or `>` character is never mangled — per the
runbook, if a future report shows leftover markup, extend `_MARKUP_TAG` with
the new tag rather than switching to a blanket strip.

## 4. Error modes

`mfl_service.MflError` (`kind`: `'auth' | 'not_found' | 'http' | 'parse' |
'input'`) and its subclass `MflAuthError` (`kind='auth'`, default message
"MFL rejected the request (private league or bad cookie)") are the only
exceptions the service raises. `server._platform_error_response()`
(`server.py:19671`) maps them to HTTP responses shared with the Fleaflicker
integration:

| `kind` | HTTP | JSON `error` | Trigger |
|---|---|---|---|
| `auth` | 403 | `mfl_auth_required` | HTTPError 401/403 from any authenticated/cookie call, or a `{"error": …}` body from `myleagues` |
| `not_found` | 404 | `mfl_league_not_found` | HTTPError 404 from an export call, or `resolve_host` getting no redirect Location for a league id |
| `input` | 400 | `mfl_bad_league_id` | Non-numeric league id passed to any function requiring one |
| `http` (default) | 502 | `mfl_unavailable` | Any other HTTPError/URLError, or a request that plain fails to connect |
| `parse` | (folds into the 502 branch — no dedicated JSON code) | — | Non-JSON response body (`json.loads` failure) |

**Login-specific:** `login()` maps HTTPError 401/403 to `MflAuthError`
directly; any other HTTP error is a generic `MflError(kind='http')`. A
response with no `MFL_USER_ID="…"` match (including an `<error>…</error>`
body) is also treated as `MflAuthError` — MFL doesn't always use HTTP status
codes to signal bad credentials.

**Rate limits:** MFL is "notoriously rate-limited" per the task brief, but
**MFL itself does not appear to return a distinguishable rate-limit error
code anywhere in this codebase** — a 429 or a slow-down response would fall
into the generic `http`/502 bucket like any other failure. The code's actual
defense is **prevention, not detection**:
- `_REQUEST_SPACING_SECONDS = 1.0` — every multi-export live call
  (`fetch_league_bundle`, `fetch_scoring_inputs`) sleeps 1s between exports
  when not running under test (`_opener is None`).
- `mfl_auth_import` spaces sequential per-league imports by 1.0s
  (`server.py:20177`, skipped when `app.config["TESTING"]`).
- The registered `MFL_USER_AGENT` is the other lever (§2) — no code-level
  retry/backoff exists beyond these fixed spacing waits.
- `draft_board_service` additionally documents (but per its own comment, has
  NOT restated for the multi-worker case) a "≤3 upstream fetches per rolling
  60s per draft" per-process budget for the Draft Room's MFL polling path —
  flagged as an open gap if Render's worker count ever increases
  (`server.py:10249–10257`).

**Best-effort degradation (never a hard failure):**
- `players` and `rules` exports in `fetch_league_bundle` — a failure on
  either degrades to `{}` (positions unknown for unmatched players; TEP
  scoring undetectable, format detection falls back to lineup-only signal).
  `league` and `rosters` failures still raise (they're load-bearing).
- `fetch_draft_results()` — any `MflError` degrades to `{}`; the draft-status
  detector then falls back to the roster-size heuristic instead of raising
  into a background refresh.
- `fetch_future_draft_picks()` — any `MflError` degrades to `{}`. Critically,
  the caller (`_refresh_mfl_future_picks`) distinguishes "unavailable" (no
  `futureDraftPicks` key in the response at all) from "genuinely empty" (key
  present, zero franchises) — **only a payload that actually carries the key
  gets written**, so a flaky/failed refresh never overwrites a good stored
  snapshot with an empty one. This is the direct fix for the #220 wipe class
  applied to the MFL surface.

**Known incidents:**

1. **#200 (2026-07-27) — MFL numeric league ids wiped draft picks on session
   init.** Root cause: the session-init owned-pick-sync daemon gated on
   `str(league_id).isdigit()` alone; MFL's native ids are numeric too (same
   misroute class as #149/#150). A misrouted MFL league fed Sleeper's
   rosters/traded-picks fetch, which came back empty, and
   `sync_draft_picks(roster_ids=[])` **REPLACE-synced `draft_picks` to an
   empty grid**, silently deleting the picks `_sync_mfl_owned_picks` had
   normalized at link time — every app open re-wiped them. Fix: the daemon
   now discriminates with `is_linked_platform_league()`; platform-linked ids
   skip the Sleeper grid sync entirely and re-run `_sync_mfl_owned_picks`
   instead (no network — reads the stored `platform_future_picks` JSON), and
   previously clobbered leagues self-heal on their next session init.
   `docs/feedback/items/200-summary-picks-missing/status.md`.
2. **#220 (2026-08-01) — the same wipe class on the genuine-Sleeper path**
   (not MFL-specific, but the lesson was carried into every later MFL write
   path, explicitly cited in code comments as "#220's lesson"): a flaked
   fetch producing an empty/`None` result must never be allowed to
   REPLACE-sync a store to empty. `sync_draft_picks` now no-ops on empty
   `roster_ids` instead of wiping, and `fetch_future_draft_picks`'s
   key-presence check (above) is the same principle applied to MFL.
3. **#210 → #258 → #282 (2026-08-01 → 2026-08-09) — name-cleaning saga.**
   #210 first added entity-decoding to `_clean_text`. #258 (2026-08-06)
   reported it as insufficient ("weird characters… I believe it's html") and
   added the DB backfill (`_backfill_mfl_name_entities`) to re-clean rows
   stored before #210 shipped — but diagnosed the residual junk as more
   entities. #282 (2026-08-09) reopened it: the operator confirmed entities
   were never the real problem — MFL lets franchise owners **style their
   team name with inline color/formatting markup**, and that's what survived
   #258's fix. `_MARKUP_TAG` was added to strip it (see §3 for the real
   captured strings and the full before/after).

## 5. Call frequency / caching

**What triggers a live MFL fetch:**

| Trigger | Route/function | What it fetches |
|---|---|---|
| Operator pastes a league URL/id (preview) | `POST /api/mfl/link` (no `franchise_id`) | `fetch_league_bundle` (5 exports) |
| Operator confirms a team (import) | `POST /api/mfl/link` (with `franchise_id`) | Same bundle refetched (no caching between preview and confirm) |
| Manual "refresh this league" | `POST /api/mfl/import` | `fetch_league_bundle` (5 exports), cookie-attached if auth-linked |
| MFL sign-in | `POST /api/mfl/auth-link` | `login` + `fetch_my_leagues` |
| Authenticated bulk import | `POST /api/mfl/auth-import` | `fetch_my_leagues` once, then `fetch_league_bundle` per requested league (sequential, 1s-spaced) |
| League-list read, format never detected | `GET /api/mfl/leagues` | One-shot `fetch_scoring_inputs` (2 exports: `league`+`rules`) **per league per process** — see caching below |
| App open / login (`/api/session/init`) | `_refresh_league_draft_status()` → (MFL branch) | `fetch_draft_results` (draft-status detector) + (if the cached verdict is stale) `_refresh_mfl_future_picks` → `fetch_future_draft_picks` |
| Hourly cron tick | Same `_refresh_league_draft_status()`, swept across up to `_DRAFT_STATUS_SWEEP_BUDGET` (50) stalest leagues per tick | Same as above |
| Draft Room open (mobile, flag `draft.mfl`) | `draft_board_service` → `mfl_service.fetch_draft_results` | Live draft grid for the board UI |

**Caching / staleness controls:**
- **Draft-status TTL** (`_DRAFT_STATUS_TTL_SECONDS`, `server.py:11682`) gates
  both the session-init and hourly-cron refresh paths — `drafted`: 12h,
  `not_drafted`: 3h, `unknown`: 1h. A fresh cached verdict skips the MFL
  fetch entirely (`_draft_status_is_fresh`).
- **Format-detection backfill** (`_mfl_scoring_backfill_attempted`,
  `server.py:19741`) — an **in-memory, per-process** set; each league id is
  attempted at most once per process lifetime regardless of how many times
  `/api/mfl/leagues` is called, to keep a flaky MFL from being re-hit on
  every league-list read.
- **Shared DP crosswalk** (`espn_service.get_crosswalk()`, used by
  `map_franchises`) — 24h in-memory cache with a bundled-snapshot fallback,
  shared across ESPN/MFL/Fleaflicker.
- **Draft-status sweep budget** (`_DRAFT_STATUS_SWEEP_BUDGET = 50`) bounds
  the hourly cron's per-tick MFL exposure — queue is never-checked-first
  then stalest-first, a fair rotation rather than a per-league guarantee.

**The load-bearing fact for instrumentation (#258 root cause):**
**MFL has no automatic re-import.** Every MFL-sourced field (roster, name,
future picks) is a snapshot as of the last explicit trigger above — there is
no polling/webhook path independent of session-init/cron/manual-refresh. A
league linked once and never revisited (no session-init calls, cron budget
exhausted, no manual refresh) can carry stale MFL data indefinitely. This is
literally the root cause class for two incidents: #258/#282 (names stayed
dirty until a code fix ran the backfill, since nothing re-fetches names on a
timer) and the pre-#207 futureDraftPicks staleness (a season's picks that MFL
had already dropped from its export stayed in `platform_future_picks` until
`_refresh_mfl_future_picks` started riding the draft-status cadence).

## 6. Instrumentation guidance

**Safe to log (already logged in several call sites, e.g. `mfl_link`,
`mfl_auth_import`):**
- MFL league id, franchise id (both are MFL's own numeric identifiers, not
  PII — no owner name/email is ever fetched, per MFL ToS)
- `year` / season
- Export `type_` (`league`, `rosters`, `futureDraftPicks`, `players`,
  `rules`, `draftResults`, `myleagues`, `login`)
- Host (`wwwNN.myfantasyleague.com`) — useful for host-resolution regressions
- HTTP status / `MflError.kind` (`auth`/`not_found`/`http`/`parse`/`input`)
- Latency per export call
- Match rate / report counts (`matched_by_id`, `matched_by_name`,
  `out_of_pool`, `unmatched` count) — already logged, no player names needed
  beyond what's already exposed to the client
- `storage` mode for auth-link (`"encrypted"` vs `"session"`) — signals
  whether `SLEEPER_TOKEN_KEY` is configured in a deployment, useful ops
  signal, carries no secret
- Draft-status verdict + confidence + source

**Must redact / never log:**
- **MFL password** — used once for the login POST body, already never logged
  by any existing code path; an instrumentation layer must not add a request/
  response logger that captures POST bodies on `/api/mfl/auth-link` or the
  MFL `login` call itself.
- **The `MFL_USER_ID` cookie value** (both the `Cookie` header sent on every
  authenticated export request, and the raw `auth["cookie"]` /
  `auth["mfl_user_id"]` return value from `login()`) — this is a full-session
  credential equivalent to a password; treat exactly like the Sleeper JWT and
  ESPN `espn_s2` cookie (both already Fernet-encrypted at rest and excluded
  from logs elsewhere in the codebase). Never log request headers or the
  `mfl_credentials.cookie_encrypted` column's decrypted value.
  `MflAuthError` messages are safe to log as-is (they're static strings, no
  cookie interpolated).
- **MFL username** — an identifier, not a secret, but still avoid pairing it
  with other user data in a way that expands PII surface beyond what
  `mfl_credentials.mfl_username` already stores for "connected as" display;
  don't add it to generic request-logging middleware without the same review
  applied to Sleeper usernames.
- **Full raw MFL response bodies** — franchise/player names before cleaning
  can carry the markup junk described in §3; logging raw bodies for debugging
  is fine ad hoc (as the existing `python3 -m backend.mfl_service` CLI does to
  stdout) but should not land in a persistent structured-log sink without
  going through `_clean_text` first, to avoid HTML-ish fragments in log
  storage.

## 7. Write surface — "Send in MFL"

> Added 2026-08-11 (flag `trade.send_in_mfl`, default OFF — built dark, no live
> import has been fired yet). Module: [`backend/mfl_write.py`](../../backend/mfl_write.py)
> — pure, opener-injectable, no Flask/DB imports, same design contract as
> `sleeper_write.py`. Feature scope + the operator live-verification checklist
> that gates flag graduation:
> [docs/feedback/items/177-mfl-auth-link/send-in-mfl-scope.md](../feedback/items/177-mfl-auth-link/send-in-mfl-scope.md).

### Endpoints

| # | Purpose | URL pattern | Method | Call site(s) |
|---|---|---|---|---|
| W1 | Propose a trade | `https://{host}/{year}/import?TYPE=tradeProposal&L={id}&OFFEREDTO={ffff}&WILL_GIVE_UP={a,b}&WILL_RECEIVE={c,d}&EXPIRES={unix}&JSON=1[&COMMENTS=…]` | GET | `mfl_write.propose_trade()`; called from `server.py` `POST /api/trades/propose-mfl` |
| W2 | Respond to a pending trade | `https://{host}/{year}/import?TYPE=tradeResponse&L={id}&TRADE_ID={t}&RESPONSE=accept\|reject\|revoke&JSON=1` | GET | `mfl_write.respond_trade()`; called from `server.py` `POST /api/trades/respond-mfl` (same flag + hard-verified gate as propose; revoke is the near-term use — TRADE_ID comes from export #10, pendingTrades) |

Both hit the league's assigned `wwwNN` host, same as exports (§1's gotcha —
whether imports strictly require it is a TODO(live-verify), but the wwwNN host
is correct either way). `EXPIRES` defaults to now + 7 days
(`DEFAULT_EXPIRES_SECONDS`), stated explicitly rather than leaning on MFL's
own one-week default.

### Auth

Imports require the **`MFL_USER_ID` session cookie** (§2's credential — the
one `mfl_credentials` stores Fernet-encrypted). MFL's api_info is explicit
that APIKEY auth works for exports only, **not imports** — there is no
API-key path for writes. The route decrypts via `server._mfl_cookie_for`
(encrypted row first, in-memory session fallback); a rejected cookie
(HTTP 401/403 **or** an auth-flavored `<error>` body) raises
`MflWriteAuthError`, the route drops the stored credential and returns
409 `mfl_auth_expired` → the client re-prompts the #177 sign-in.

### Asset ids (`WILL_GIVE_UP` / `WILL_RECEIVE`, comma-separated)

| Asset | Format | Example | Notes |
|---|---|---|---|
| Player | bare MFL player id | `13130` | FTF works in Sleeper-id space; the route reverse-maps via the DP crosswalk (`by_mfl_sleeper` inverted, `server._sleeper_to_mfl_map`) and **HARD-BLOCKS** (422 `mfl_asset_unmapped`) if any asset fails — an offer never silently loses an asset |
| Current-year pick | `DP_RR_SS`, **zero-based**, two-digit | `DP_02_05` = 3rd round, 6th pick | `mfl_write.encode_current_year_pick`. **Pre-encoded-only**: FTF's internal pick representation carries no draft SLOT, so no server path constructs `DP_` — only the `give_pick_assets` passthrough accepts it |
| Future pick | `FP_FFFF_YYYY_R` — **original-owner** franchise (4-digit zero-padded, matching `originalPickFor` in the §3 futureDraftPicks shape), year, 1-based round | `FP_0005_2027_1` | `mfl_write.encode_future_pick`. **Wired end-to-end**: the propose/validate routes split FTF pick ids (`{league}_{season}_{round}_{orig_franchise}`, `database.make_pick_id`) out of the mixed asset arrays and encode them via `server._mfl_encode_ftf_picks` — ground truth is the stored `leagues.platform_future_picks` snapshot, NEVER a client encoding; a pick absent from the snapshot (or any generic `generic_pick_…` rung) hard-blocks the send |
| Blind-bid dollars | `BB_10.50` | | documented by MFL, **not built** |

**Shape verification status:** the `FP_` inputs were verified against a LIVE
public `futureDraftPicks` export 2026-08-11 (league 62846, host `www45`):
`originalPickFor` arrives 4-digit zero-padded (`"0001"`), `round` 1-based
unpadded (`"1"`) — exactly what `encode_future_pick` emits. **Still
TODO(live-verify)** (operator checklist): whether a live *import* accepts
those `FP_` strings, `DP_` zero-basing in practice, and whether `JSON=1`
applies to import responses. `_parse_import_response` accepts both
`<status>OK</status>` XML and `{"status":"OK"}` JSON and **refuses to report
success on any ambiguous body**.

### v1 limitation — single-linker leagues (operator-accepted 2026-08-11)

v1 stores **one `leagues` row per MFL league**, so only the FTF user who
linked the league has a franchise binding (`platform_my_team`) and can send
from it. Any other FTF user in the same MFL league gets 404 `mfl_not_linked`
("This MFL league isn't linked to your account."); the mobile client offers
re-linking, which transfers the binding to them. Accepted for v1 — per-user
franchise bindings are a v2 concern if MFL adoption warrants it (see the
scope block §"v1 limitations").

### Error modes

`MflWriteError` (`kind`: `'auth' | 'network' | 'error' | 'input'`) +
`MflWriteAuthError`. Route mapping (`POST /api/trades/propose-mfl`): full
table in [docs/api-reference.md](../api-reference.md) § Send in MFL —
notably 422 `mfl_asset_unmapped` (crosswalk hard block, `unmapped[]` listed),
409 `mfl_auth_expired` (credential dropped), 502 `mfl_write_failed`
(carries `kind`/`detail`; HTTP 429 throttling surfaces as `kind: "network"`).

### Rate limits / hygiene

Same posture as reads: `MFL_USER_AGENT` on every request, module-level ≥1s
spacing on the live path (`_REQUEST_SPACING_SECONDS`), no retry on failure.
Client registration (§2's note) is **still pending** and matters more here —
unregistered write traffic is the most throttle-exposed. The cookie is never
logged and never an `api_call` event property; observability rides
`observe_call("mfl", "import.tradeProposal" | "import.tradeResponse")` with
the same safe props as exports (league_id, host, status, latency, error kind).

### Trade lifecycle (routes)

The full lifecycle is routed, all behind the ONE `trade.send_in_mfl` flag:

1. **Propose** — `POST /api/trades/propose-mfl` (W1). Fires the server-side
   `trade_sent` event on confirmed success.
2. **Read status** — `GET /api/mfl/pending-trades` (export #10,
   owner-restricted, cookie-attached; `mfl_service.fetch_pending_trades` +
   `parse_pending_trades`). Surfaces each pending trade's `trade_id`.
   **TODO(live-verify):** the response field vocabulary (`trade_id` /
   `offeringteam` / `offeredto` / `will_give_up` / `will_receive` /
   `comments` / `expires`) follows MFL's Request Reference; no live
   owner-restricted capture exists yet — capture one into
   `docs/references/mfl/` and align the parser if it disagrees.
3. **Respond** — `POST /api/trades/respond-mfl` (W2:
   `RESPONSE=accept|reject|revoke`). Same hard-verified gate + error codes as
   propose; fires the server-side `trade_responded` event
   (`platform`/`response`/`outcome`) on confirmed success only.

No mobile surface consumes 2–3 yet (deliberate: a pending-trades list is a
new screen, deferred as a follow-up; the API contract ships first so the
operator can verify the lifecycle live).

### Pre-flight (#180 parity)

`POST /api/trades/validate` routes MFL-linked leagues to a fresh `rosters`
export (`mfl_service.fetch_rosters` + `parse_roster_ids`, best-effort `{}`)
and reports advisory `player_moved` / `roster_not_found` findings plus
`asset_unmapped` (the advisory mirror of the propose route's hard block —
players against the crosswalk AND picks against the stored futureDraftPicks
snapshot) and `pick_moved` (the pick twin of `player_moved`: the snapshot
says the pick's current owner isn't the expected side — zero-network, reads
the stored snapshot only). Roster limits, deadlines and commissioner locks
are delegated to MFL — its import enforces league rules, same philosophy as
the Sleeper path.
