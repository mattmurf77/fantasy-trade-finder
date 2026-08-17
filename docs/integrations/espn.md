# ESPN Integration Reference

> Written for the instrumentation program — this doc feeds a build agent adding
> logging/metrics around FTF's ESPN calls. It documents what's on `origin/main`
> as of 2026-08-09. **A fix agent is concurrently editing `backend/espn_service.py`
> on another branch** (cookie-encoding normalization + WebView fixes) — noted
> inline wherever it's relevant, but this doc does not describe that branch's
> code.

Source of truth: `backend/espn_service.py` (all HTTP egress to ESPN lives here)
plus every call site that imports it. Core module doc comment:
`backend/espn_service.py:1-26`.

## Contents

1. [Endpoints used](#1-endpoints-used)
2. [Auth model](#2-auth-model)
3. [Request/response shapes](#3-requestresponse-shapes)
4. [Error modes](#4-error-modes)
5. [Call frequency / caching](#5-call-frequency--caching)
6. [Instrumentation guidance](#6-instrumentation-guidance)

---

## 1. Endpoints used

FTF calls **two** ESPN hosts (as of 2026-08-09; one until then), for two
resource shapes — the league-read API (§1.1) and, additively, a fan-profile
lookup for league discovery (§1.7). There is no ESPN write path anywhere in
the codebase (read-only integration, stated explicitly in the module
docstring and in every route's docstring).

### 1.1 League read — the only ESPN endpoint

| | |
|---|---|
| Host | `lm-api-reads.fantasy.espn.com` |
| Path | `/apis/v3/games/ffl/seasons/{season}/segments/0/leagues/{league_id}` |
| Method | `GET` |
| Query params | `view=mTeam&view=mRoster&view=mSettings` (always all three, always together — no call site ever requests a subset) |
| URL builder | `backend/espn_service.py:87-91` (`league_url`) |
| Call function | `backend/espn_service.py:94-134` (`fetch_league`) |
| Constant | `ESPN_READS_BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"` — `backend/espn_service.py:47` |

**View names in use:** `mTeam` (team/owner/record/standings data), `mRoster`
(player entries per team), `mSettings` (league name, size, playoff bracket
size). No other ESPN view (`mDraftDetail`, `mMatchup`, `mBoxscore`, `kona_*`,
etc.) is ever requested — see §1.2.

### 1.2 Endpoints deliberately NOT used

- **`mDraftDetail` / any draft view** — `draft_board_service.py:1252-1261`
  documents an explicit operator ruling: "ESPN has no rookie-draft concept, so
  an ESPN board is built entirely from the assignment grid" (FTF's own
  pick-ownership data, `/api/league/pick-assignments`). The ESPN branch of
  `GET /api/draft/board` makes **zero platform egress** — don't mistake the
  presence of "ESPN" in `draft_board_service.py`/`draft_status.py` for a new
  call site; it's read from FTF's own tables (`draft_status.py:23-25,315`).
- **Any write endpoint** — ESPN issues no writes; confirmed by the module
  docstring (`backend/espn_service.py:4` "Read-only adapter") and repeated in
  every route's docstring (e.g. `backend/server.py:18293-18296`).

### 1.3 Call sites that invoke `fetch_league` (all hit the endpoint in §1.1)

| Call site | `file:line` | Purpose |
|---|---|---|
| `_espn_import_payload` | `backend/server.py:18332-18339` | Fetch + parse + crosswalk one league (used by both link and re-sync below) |
| `POST /api/espn/link` → `espn_link` | `backend/server.py:18358-18507` | Preview (no `team_id`) or import (with `team_id`) |
| `POST /api/espn/import` → `espn_import` | `backend/server.py:18536-18626` | Manual re-sync of an already-linked league |
| `_espn_standings_read` | `backend/server.py:10526-10570` | Reads current + prior season, looking for one where standings support a draft-order derivation |
| CLI spike `_main` | `backend/espn_service.py:626-657` | `python3 -m backend.espn_service <league_id> [season]` — manual debug tool, not reachable from any client |

### 1.4 A second, non-ESPN URL lives in the same module

`fetch_crosswalk` (`backend/espn_service.py:465-473`) fetches
`https://raw.githubusercontent.com/dynastyprocess/data/master/files/db_playerids.csv`
(GitHub, not ESPN) — the DynastyProcess player-id crosswalk that maps
ESPN/MFL/Fleaflicker/KTC ids into FTF's Sleeper `player_id` space. It lives in
`espn_service.py` because ESPN was the first platform to need it, but every
linked platform (ESPN, MFL, Fleaflicker) and the KTC consensus blend
(`backend/data_loader.py:243-252`) shares this one cached fetch via
`get_crosswalk()` (`backend/espn_service.py:476-498`). Not an ESPN egress —
included here because an instrumentation pass touching "ESPN call sites" will
otherwise miss it, and because it fails-soft into ESPN-adjacent behavior (see
§4).

### 1.5 Backend routes that front these calls (client-facing surface)

| Route | Method | `file:line` | Flag |
|---|---|---|---|
| `/api/espn/link` | POST | `backend/server.py:18358` | `espn.link` |
| `/api/espn/link` | GET / DELETE | `backend/server.py` (`espn_link` — status read 2026-08-11; disconnect 2026-08-12, no ESPN egress on either) | `espn.link` |
| `/api/espn/leagues` | GET | `backend/server.py:18510-18511` | `espn.link` |
| `/api/espn/import` | POST | `backend/server.py:18536-18538` | `espn.link` |
| `/api/espn/my-leagues` | GET | `backend/server.py` (`espn_my_leagues`, added 2026-08-09) | `espn.league_picker` |

The first three 404 (`{"error": "feature_disabled"}`) while `espn.link` is
off; `/api/espn/my-leagues` 404s the same way while `espn.league_picker` is
off (independently of `espn.link`, though the picker is pointless without
it — see §1.7). All three flags are **ON** in `config/features.json`
(`espn.link: true` line 59, `espn.webview_capture: true` line 61,
`espn.league_picker: true`).

### 1.6 Mobile client call sites (consume the routes in §1.5, never ESPN directly)

| File | Role |
|---|---|
| `mobile/src/api/espn.ts` | Thin wrappers: `linkEspnLeague`, `getEspnLeagues`, `importEspnLeague`, `getMyEspnLeagues` (§1.7) |
| `mobile/src/components/EspnLinkSheet.tsx` | 3-step link UI (input → team pick → done); calls `linkEspnLeague` on Continue and on team-pick. Step 1's league-id text field is replaced by a league-SELECTION list (`getMyEspnLeagues`, flag `espn.league_picker`) whenever the account's stored cookies resolve to ≥1 football league; manual entry stays one tap away |
| `mobile/src/screens/EspnConnectScreen.tsx` | In-app WebView to `https://www.espn.com/login` (URL decision + cold-load fix: 2026-08-09, see the ESPN_LOGIN_URL comment) — captures cookies from the **native store**, never calls any FTF or ESPN API itself. One automatic warm-up reload after the first load completes, a manual reload control, and a wedge-detection hint (§ below) |
| `mobile/src/utils/espnCookies.ts` | Pure cookie-store read/clear helpers backing the WebView screen |

The mobile client never talks to `lm-api-reads.fantasy.espn.com` OR
`fan.api.espn.com` directly — all ESPN reads happen server-side.

### 1.7 Fan profile — league discovery (2026-08-09, flag `espn.league_picker`)

A second ESPN host, added to answer the feedback "can't we fetch all their
ESPN leagues and let them pick, instead of asking for a league ID?"

| | |
|---|---|
| Host | `fan.api.espn.com` (**separate from** `lm-api-reads.fantasy.espn.com`, §1.1) |
| Path | `/apis/v2/fans/{SWID}?showAirings=true&showFantasy=true` |
| Method | `GET` |
| URL builder | `backend/espn_service.py` (`fan_leagues_url`) |
| Call function | `backend/espn_service.py` (`fetch_fan_leagues` → list; `probe_fan_profile` → verification verdict; both over one `_fetch_fan_payload` chokepoint) |
| Route | `GET /api/espn/my-leagues` (`backend/server.py`, `espn_my_leagues`) — flag `espn.league_picker` |
| Second caller | `POST /api/espn/link`'s credential-only store uses `probe_fan_profile` as its **fallback** verification oracle, only when no auth-gated linked league is available — see §2.4 item 1b |

**⚠ NOT PROVEN TO BE AN AUTHENTICATION ORACLE.** The claim once recorded
here and in code — "the fan API has no anonymous success mode" — is
**evidenced only against an UNKNOWN SWID** (the 404 below). That is a
SWID-*existence* result, not proof that ESPN validates `espn_s2` on this
route: the SWID travels in the URL **path**, ESPN issues SWIDs to anonymous
visitors, and no session here has ever observed what this host returns for a
*known* SWID presented with a missing/invalid `espn_s2`. Until someone runs
that specific experiment live (known SWID, no/garbage `espn_s2`, record the
status and body), treat a fan-profile success as **corroborating evidence,
not authentication**, and prefer an authenticated league read (§1.1 against
a private league) whenever one is available. This is why the credential
store demotes this probe to a fallback and records which oracle it used —
the 2026-08-12 incident is what the over-claim cost.

**Auth:** always cookie-mode — there is no "public" fan profile. Reads the
session user's already-**stored** `espn_credentials` row (same
`canonical_espn_s2`/`canonical_swid` normalizers, same decrypt path as every
other espn.py route); this route never accepts pasted/POSTed cookies itself.
A brand-new WebView capture that hasn't linked any league yet has NOTHING
stored server-side (cookies only persist inside `espn_link`'s import path),
so the mobile client's first attempt right after a capture will ordinarily
403 — this is expected, not a bug, and the client falls back to the
text-field flow silently. From the second link onward (or for an account
that linked ESPN before), the stored credential is already there and this
route works immediately.

**UNVERIFIED response shape.** This endpoint is not documented by ESPN.
Confirmed LIVE (2026-08-09): an unauthenticated request with a
syntactically-valid but unknown SWID returns `404 {"message":"fan not
found"}` — the host resolves and answers JSON, so this is a real endpoint,
not a guess. The AUTHENTICATED shape for a real fan is unverified from any
build session to date (no live cookies available, and the endpoint is
essentially undocumented outside community reverse-engineering).
`espn_service._parse_fan_leagues` follows the best-known shape — a
top-level `preferences[]`, each entry's `metaData.entry` carrying `groups[]`
(one row per league/group across ALL ESPN fantasy games), filtered to
football via `entry.abbrev == "ffl"` (the same game slug used at
`apis/v3/games/ffl`, §1.1) — and is written to **degrade to an
empty/partial list on any shape mismatch, never raise**. Needs a TestFlight
run against a real account to confirm or correct the parse
(`docs/feedback/items/espn-webview-escape/status.md`).

**Response (as parsed by FTF, not ESPN's raw shape):**
`{"leagues": [{"league_id", "league_name", "season", "team_name"}]}`, newest
season first. `[]` is a legitimate, honest answer (the account has no
fantasy football leagues) — never fabricated.

**`[]` is ambiguous, and that ambiguity is load-bearing.** Because the parse
degrades instead of raising, an empty list means *either* "no football
leagues" *or* "this payload wasn't recognised". For the picker that
distinction doesn't matter; for **credential verification it is the whole
question**, which is why verification calls `probe_fan_profile` instead —
it also reports `fantasy_entries` (fantasy teams of ANY sport, so an account
with only baseball/hockey leagues is not falsely rejected) and `recognized`.
Verification never reads emptiness as success.

Errors: 404 `feature_disabled` (flag off) · 403 `espn_auth_required` (no
stored ESPN session yet, or ESPN rejects the stored one — same code as the
existing link-flow 403, same recovery UX: sign in again) · 503
`espn_unconfigured` (stored cookie undecryptable).

---

## 2. Auth model

### 2.1 Public vs. private leagues

- **Public leagues** need no credentials. `fetch_league` sends no `Cookie`
  header when `espn_s2`/`swid` are absent (`backend/espn_service.py:111-115`;
  pinned by `test_fetch_sends_browser_headers_and_no_cookie_for_public` in
  `backend/tests/test_espn_service.py:70-83`).
- **Private leagues** need **both** `espn_s2` and `swid` cookies from a
  logged-in espn.com session. The backend enforces both-or-neither: 400
  `espn_cookies_incomplete` if only one is supplied
  (`backend/server.py:18396-18398`).

### 2.2 Cookie shapes (wire format — verified live 2026-08-09)

| Cookie | Shape | Notes |
|---|---|---|
| `espn_s2` | Percent-encoded, roughly **~350 characters** | Must be replayed **exactly as captured** — re-encoding it breaks auth. The module docstring calls this out explicitly (`backend/espn_service.py:18-19`), and the fetch code passes it through verbatim in the `Cookie` header (`backend/espn_service.py:112-115`) |
| `SWID` | Braced GUID, **38 characters** (`{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}`) | Doubles as the user's ESPN member id inside league payloads (`owner_swid` / `primaryOwner`) — kept plaintext at rest for that reason (§2.3) |

Both are sent in a single `Cookie` header: `f"espn_s2={espn_s2}; SWID={swid}"`
(`backend/espn_service.py:115`; pinned by
`test_fetch_passes_cookies_verbatim_for_private`,
`backend/tests/test_espn_service.py:86-97`).

**Known field failure (2026-08-09):** a private-league link rejected freshly
captured cookies with an encoding mismatch — the WebView-captured `espn_s2`
didn't round-trip byte-identically through storage/replay. This is exactly the
class of bug the concurrent fix-agent branch (cookie-encoding normalization)
is addressing; not yet fixed on `origin/main` as of this doc.

### 2.3 Storage (schema)

Table `espn_credentials` — `backend/database.py:1314-1321`:

| Column | Type | Notes |
|---|---|---|
| `user_id` | String, PK | One credential row per FTF user — a re-link overwrites |
| `swid` | String | Braced GUID, stored **plaintext** (it's the ESPN member id, not a secret on its own) |
| `espn_s2_encrypted` | Text, NOT NULL | **Fernet ciphertext** — the full-session credential, never stored plaintext |
| `expires_hint_at` | String (ISO UTC) | Best-effort guess (~1 year community consensus); NULL = unknown. Actual expiry is discovered via a 401/403 (see §4), not this hint |
| `verified_at` | String (ISO UTC) | **Credential-honesty fix (2026-08-12):** when this pair last PROVED itself via a live authenticated ESPN read — stamped by both store paths (§2.4). NULL = never proven (legacy rows): `GET /api/espn/link` reports such a row as **not** connected, so the client re-runs the verifying sign-in flow |
| `created_at` / `updated_at` | String | Standard audit columns |

Encryption key: `SLEEPER_TOKEN_KEY` (Fernet, base64) — **shared across every
linked platform's credentials** (Sleeper, ESPN, MFL), not ESPN-specific. Key
handling lives in `backend/sleeper_write.py` (`_ENV_KEY` at line 41,
`token_encryption_available()` line 107, `encrypt_token`/`decrypt_token` lines
116/120), reused by `espn_service`/`server.py` rather than duplicated.

Related league-binding columns on the `leagues` table (`backend/database.py:254-257`):
`platform` (`'espn'` for ESPN rows), `espn_season`, `espn_auth`
(`'public'|'cookie'`), `espn_my_team_id`.

### 2.4 Request-to-request flow

1. **Link (private):** client pastes or WebView-captures `espn_s2`+`swid` →
   `POST /api/espn/link` → cookies persisted first via `upsert_espn_credential`
   (`backend/database.py`, encrypted at rest), *then* the league +
   membership snapshot is written — order
   matters so a later re-import can reuse the cookies even if the league write
   fails. The store stamps `verified_at` only when the league is genuinely
   auth-gated — one anonymous probe settles that. If the read needed the
   cookies, the league fetch that just succeeded ran WITH this pair attached
   and is itself authenticated proof; no second probe is made.
   **Former public-league residual (2026-08-12), closed by #321 on
   2026-08-16:** a paste against a **public** league used to stamp
   `verified_at` on a pair ESPN never validated, since that fetch would have
   succeeded anonymously. That path no longer self-stamps — the anonymous
   probe classifies the league, and a public league's pair is judged by
   `_espn_verify_credential` instead. A failing or unjudgeable pair never
   fails the import: 200 with the additive `credential_stored: false` +
   `credential_reason` (`"unverified"|"unavailable"`). See
   `docs/api-reference.md` § `POST /api/espn/link`.
1b. **Credential-only store (send-auth lazy flow, 2026-08-11; verification
   added 2026-08-12, oracle corrected the same day):** `POST /api/espn/link`
   with `espn_s2`+`swid` and NO `espn_league_id` — the ESPN Connect WebView
   entered from the trade-send path (the league is already imported; only the
   account credential is missing). The route **verifies before storing**, via
   `server._espn_verify_credential`, and the probe's **result is bound and
   asserted** — "no exception" is not a pass:

   | Oracle | When used | What counts as proof |
   |---|---|---|
   | `league_read` (**strong**, preferred) | the user already has a linked league whose stored `espn_auth == 'cookie'` | one `fetch_league` (§1.1) with this pair returning a 200 that **parses into that league's teams**. ESPN refuses these without a valid member session, so this is a genuine authenticated read — it is the same pre-flight the send path runs, and the read that exposed the bad pair as a 409 in the 2026-08-12 incident |
   | `fan_profile` (**weak**, fallback) | no linked league, or only PUBLIC ones (a public league reads with no cookies at all, so a 200 proves nothing) | `probe_fan_profile` (§1.7) returning **account-specific fantasy data**: football leagues, or fantasy entries of any other sport. Recorded as the weaker oracle on success — see the §1.7 warning |

   Success → pair stored encrypted with `verified_at` stamped, `{connected:
   true, stored:"credential", verified:true, verified_via:
   "league_read"|"fan_profile"}`. Rejected pair, or a read that came back
   with nothing to prove it → **403 `espn_bad_credentials`, nothing stored**
   — the user learns at sign-in time, not at their next trade send. Any
   other failure (transport, ESPN 5xx, non-JSON edge page, a 200 that
   doesn't parse) → **502 `espn_unavailable`, nothing stored** —
   deliberately distinct: an outage is not a verdict on the cookies, so a
   user with a good sign-in is told to retry, never to re-authenticate. A
   404 on the linked league (ESPN purges old leagues) means the *oracle* is
   gone, not that the credential is bad: it falls back to the fan probe.

   **No false rejects:** an ESPN account with zero *football* leagues
   (baseball/hockey only, or new to fantasy) is legitimate, so the weak
   oracle's rule is "the read returned this account's fantasy data", never
   "there is at least one football league".

   **Deliberate refusal (not a false reject):** when the strong oracle
   401/403s, the pair may well be a valid sign-in for *some* ESPN account —
   just not one that can open this user's linked private league (the
   incident's shape: cookies captured from someone else's account). Storing
   it would only defer the failure to the send, so it is refused, with copy
   that names the recovery: sign in with the account that owns your team.

   **What `verified_at` means:** the SERVER observed a successful
   AUTHENTICATED read using this pair. Not "the client captured cookies",
   not "the user looked signed in", not "ESPN answered 200". Any
   device-reported signal added later needs its own column.

   This closed the one credential-honesty gap among the platforms: MFL
   proves credentials via `login` + `fetch_my_leagues` and Sleeper via
   `verify_token_live` before storing; ESPN previously stored the pair blind
   and reported `connected: true`. The first version of the fix still did,
   in effect: it called the fan read for its exceptions alone and discarded
   the value, and since `_parse_fan_leagues` never raises, an unrecognised
   200 stamped `verified_at` anyway.
2. **Re-link without pasting:** if the client sends no `espn_s2` on a repeat
   `POST /api/espn/link`, the backend falls back to the previously stored
   credential (`backend/server.py:18400-18412`) via `get_espn_credential`
   (`backend/database.py:9437-9453`).
3. **Re-sync (`POST /api/espn/import`):** always uses the stored credential
   when `espn_auth == 'cookie'` (`backend/server.py:18565-18576`) — the client
   never re-sends cookies on this route.
4. **Standings read for draft-order derivation** (`_espn_standings_read`,
   `backend/server.py:10526-10570`): decrypts and replays the same stored
   credential — "same host, same auth, no new egress pattern" per its own
   docstring.
5. **Decryption failures fail closed, not loud:** a corrupt/undecryptable
   stored credential is treated as "no credential" (falls through to a public
   fetch attempt, which then 401/403s normally) rather than raising — see
   `backend/server.py:18406-18412` and `10544-10548`.
6. **Deletion:** `delete_espn_credential` (`backend/database.py`) — called
   two ways:
   - **Automatic dead-cookie cleanup:** the propose route drops a credential
     ESPN rejects at send time.
   - **User-initiated disconnect (`DELETE /api/espn/link`, 2026-08-12):**
     session-authed, user-scoped, idempotent — mirrors
     `DELETE /api/sleeper/link`; the subsequent `GET` reports
     `{connected: false}`. Surfaced as "Disconnect ESPN account" in mobile
     Settings → Account (`settings.espn-disconnect`, destructive confirm).
     Added after the 2026-08-12 incident: cookies captured from someone
     else's ESPN sign-in had no user-facing removal path and had to be
     deleted straight from the production DB.
7. **Account switching (the other half of that incident):** deleting the
   stored row is not enough on its own — the connect WebView's persistent
   web session would silently re-authenticate the SAME account (Disney SSO
   session survives). `EspnConnectScreen` therefore clears the ESPN/Disney
   web session (`clearEspnCookies`, `mobile/src/utils/espnCookies.ts`)
   BEFORE the WebView is allowed to mount: enumerate-and-clear every cookie
   on `www.espn.com` / `fantasy.espn.com` / `registerdisney.go.com` /
   `cdn.registerdisney.go.com` (both native stores), plus named
   `espn_s2`/`SWID` clears as belt-and-braces. Scoped to those domains
   only — never `clearAll` (the native store is app-wide). Pinned by
   `mobile/tests/check-espn-connect-clear.js`.

---

## 3. Request/response shapes

### 3.1 What we send

- `GET` request, no body.
- Headers: `User-Agent` (a real Chrome-on-macOS signature — bare `urllib`
  signatures get filtered by ESPN's edge, same lesson as the Sleeper write
  path's Cloudflare 1010 issue) + `Accept: application/json`
  (`BROWSER_HEADERS`, `backend/espn_service.py:51-57`) + optionally `Cookie`
  (§2.2).
- Timeout: 15s default (`fetch_league(..., timeout: int = 15, ...)`).

### 3.2 What we parse from the response

`parse_league` (`backend/espn_service.py:185-237`) normalizes the raw
`mTeam+mRoster+mSettings` JSON into a small stable shape. Fields actually
consumed:

**Top level:** `id`, `seasonId`, `settings.name`, `settings.size`,
`settings.scheduleSettings.playoffTeamCount`, `members[].id`/`displayName`,
`teams[]`.

**Per team (`EspnTeam`, `backend/espn_service.py:148-172`):** `id`, `name`
(or `location`+`nickname` fallback for older payload shapes), `primaryOwner`
(or first entry of `owners[]`), `roster.entries[].playerPoolEntry.player`
(`id`, `fullName`, `defaultPositionId`), `record.overall.{wins,losses,ties,
pointsFor}`, `playoffSeed`, `rankCalculatedFinal`.

The last four fields (`wins`/`losses`/`ties`/`points_for`/`playoff_seed`/
`rank_calculated_final`) are **additive** — added 2026-08-08 for the
standings-derived draft-order feature, read from the SAME `mTeam` response the
roster import already fetches (no extra view token, no extra request; see
comment block at `backend/espn_service.py:155-161`).

**Position mapping:** `defaultPositionId` → label via `ESPN_POSITION_BY_ID`
(`backend/espn_service.py:60`): `1→QB, 2→RB, 3→WR, 4→TE, 5→K, 16→DST`. Only
QB/RB/WR/TE (`POOL_POSITIONS`, line 63) are in FTF's ranking/trade pool; K/DST
are counted and reported separately, never treated as crosswalk failures.

### 3.3 Payload sizes (from recorded test fixtures)

| Fixture | Size | Shape |
|---|---|---|
| `backend/tests/fixtures/espn_league_snapshot_2026-07-11.json` | ~10.7 KB | Full `mTeam+mRoster+mSettings`, 3 teams × ~10 players |
| `backend/tests/fixtures/espn_league_11896_standings_2026-08-08.json` | ~5.7 KB | Same view set, standings-focused live capture |

A real ~12-14-team dynasty league (20-30 roster spots each) will run
meaningfully larger — these are small fixture leagues. Rough order of
magnitude: tens of KB per fetch, not hundreds.

### 3.4 Downstream mapping (not part of the ESPN wire shape, but the next hop)

`map_rosters` (`backend/espn_service.py:501-553`) and the generic
`map_generic_rosters` (`backend/espn_service.py:570-619`, shared with
MFL/Fleaflicker) convert ESPN player ids → Sleeper player ids via the
DynastyProcess crosswalk (§1.4), producing a `{rosters, report}` shape where
`report` carries `pool_players`/`matched_by_id`/`matched_by_name`/
`unmatched`/`out_of_pool`/`match_rate`. This report is echoed to the client
(`_espn_report_json`, `backend/server.py:18342-18355`) so a partial match is
visible, never silently dropped.

---

## 4. Error modes

### 4.1 `EspnError` taxonomy (`backend/espn_service.py:70-81`)

`EspnError` carries a `kind` ∈ `{'auth', 'not_found', 'http', 'parse',
'input'}`. `EspnAuthError` is a subclass fixed to `kind='auth'`.

| ESPN response / condition | Raised as | `kind` | Route-level mapping (`backend/server.py:18308-18329`) |
|---|---|---|---|
| HTTP 401 or 403 | `EspnAuthError` | `auth` | 403 `espn_auth_required` — "private league or bad cookies", tells the user to paste fresh cookies |
| HTTP 404 | `EspnError` | `not_found` | 404 `espn_league_not_found` — "ESPN purges old leagues" |
| Any other HTTP error status | `EspnError` | `http` | 502 `espn_unavailable` — logged via `log.warning`, generic "try again shortly" |
| Non-numeric `league_id` | `EspnError` | `input` | 400 `espn_bad_league_id` |
| Response body isn't valid JSON | `EspnError` | `parse` | Falls into the generic `http`-kind 502 branch (parse isn't special-cased in `_espn_error_response`) |
| `urllib` timeout / connection error | Propagates as the underlying `urllib.error`/`socket` exception — **not** wrapped in `EspnError` | n/a | Uncaught by `_espn_error_response`; bubbles to the route's generic exception handling |

Tests pinning this table: `backend/tests/test_espn_service.py:100-124`
(`test_fetch_error_mapping`, `test_fetch_rejects_non_numeric_league_id`,
`test_fetch_non_json_raises_parse`).

### 4.2 Other failure paths outside `fetch_league` itself

| Condition | Handling | `file:line` |
|---|---|---|
| Stored cookie undecryptable (Fernet key rotated/wrong) | Caught, logged as a warning, treated as "no credential" (falls through to unauthenticated fetch) | `backend/server.py:18406-18412`, `10544-10548` |
| Credential-encryption key entirely missing (`SLEEPER_TOKEN_KEY` unset) | 503 `espn_unconfigured` before attempting to store a pasted cookie | `backend/server.py:18456-18458` |
| Re-sync (`/api/espn/import`) target league never linked | 404 `espn_not_linked` | `backend/server.py:18560-18563` |
| Re-sync target league is private but has no stored credential | 403 `espn_auth_required` | `backend/server.py:18568-18571` |
| User's team no longer present in the league on re-sync | 409 `espn_team_missing` — "re-link to pick a team" | `backend/server.py:18584-18588` |
| Chosen `team_id` not present in the fetched teams | 400 `espn_bad_team_id` | `backend/server.py:18448-18450` |
| Missing/malformed view (e.g. `mSettings` absent from a payload) | Handled defensively field-by-field with `.get()`/fallbacks throughout `parse_league`, not a distinct error path — a missing `playoff_team_count` degrades `derive_espn_draft_order` to a refusal (§4.3), it does not raise | `backend/espn_service.py:225-237` |
| DynastyProcess crosswalk fetch fails (GitHub, not ESPN — §1.4) | Falls back to (a) last good in-memory copy, then (b) the bundled snapshot CSV fixture; logs a warning; **never raises** — an import is always possible, just possibly with a stale crosswalk | `backend/espn_service.py:487-497` |

### 4.3 Known field failure — private-league cookie encoding mismatch (2026-08-09)

A private-league link rejected cookies that had just been captured by the
WebView flow (§1.6/§2.2) — the round-trip through capture → storage → replay
did not preserve `espn_s2`'s exact percent-encoding, so ESPN's edge rejected
the replayed cookie as if it were bad auth (indistinguishable, from FTF's
error taxonomy, from an `EspnAuthError`/`espn_auth_required`). This is the
specific bug the concurrent fix-agent branch is targeting; not resolved on
`origin/main` as of this doc.

### 4.4 `derive_espn_draft_order` — a distinct "refusal," not an error

Not an HTTP/parse error, but worth flagging for instrumentation: this
function (`backend/espn_service.py:244-343`) returns `None` — never raises,
never fabricates a partial answer — whenever the standings data can't support
an honest derivation (fewer than 2 teams, no/invalid
`playoff_team_count`, any team missing standings fields, duplicate/invalid
`playoff_seed`, an unplayed 0-0-0 season, or any playoff team missing/
duplicating `rankCalculatedFinal`). Full refusal list:
`backend/espn_service.py:291-303`. Each refusal is silent to the end user
(the client just doesn't get a `suggested_order` and orders manually) — an
instrumentation signal here (refusal reason) would be genuinely new
visibility, not duplicating an existing log line.

---

## 5. Call frequency / caching

| Cache | TTL | Scope | `file:line` |
|---|---|---|---|
| Suggested-order cache | **15 min** (`900s`), both hits AND misses cached | Per `league_id`, in-process dict | `backend/server.py:10521-10523` (`_SUGGESTED_ORDER_CACHE`, `_SUGGESTED_ORDER_TTL_SECONDS`) |
| DynastyProcess crosswalk | **24h** normally; **1h** retry when serving the bundled-snapshot fallback | Global, in-process, one shared cache for every platform (ESPN/MFL/Fleaflicker/KTC) | `backend/espn_service.py:457-498` (`_CROSSWALK_TTL_SECONDS`, `get_crosswalk`) |
| Standings read for draft order | No separate cache of its own — relies on the 15-min suggested-order cache above; tries the linked season, then one season back, stopping at the first that supports a derivation | — | `backend/server.py:10526-10570` |
| Roster import (`/api/espn/link`, `/api/espn/import`) | **No caching** — every call is a live fetch | — | `backend/server.py:18332-18339` |

### What triggers an ESPN call

1. **Link (preview)** — user pastes/detects a league ID in `EspnLinkSheet` and
   taps Continue → one `fetch_league` call.
2. **Link (import)** — user picks their team → **one more** `fetch_league`
   call (the preview's fetch is not reused/cached across the two-step flow;
   each `POST /api/espn/link` call is independent).
3. **Manual re-sync** — user (or an automated re-sync action) hits
   `POST /api/espn/import` → one `fetch_league` call, uncached.
4. **Draft-order derivation** — `GET /api/league/pick-assignments` (behind
   `picks.assign`) triggers `_espn_suggested_order`, which is the ONLY reader
   gated by the 15-min cache: within the window, repeat screen loads make
   zero ESPN calls; outside it, up to 2 `fetch_league` calls (current season,
   then one season back) per league. **Only fires while the league has no
   stored pick order** — after the first `seedPickGrid` save, the keys the
   client would trigger this off never return and no ESPN read happens again
   at all (structural, not a client-side check — see
   `mobile/src/api/pickAssignment.ts`'s CLAUDE.md entry).
5. **Crosswalk refresh** — any of the above (or an MFL/Fleaflicker
   link/import, or a routine KTC-blend recompute) can trigger a crosswalk
   fetch, but only once per 24h globally regardless of how many leagues/users
   are active.

No polling, no webhooks, no background job hits ESPN — every call is
synchronously triggered by a user action (or the 15-min-bounded derivation
above) inside an HTTP request/response cycle.

---

## 6. Instrumentation guidance

Per call class, what's safe to log vs. what must never appear in logs/traces.

### 6.1 `fetch_league` (the one ESPN endpoint, §1.1)

**SAFE to log:**
- HTTP status code returned by ESPN
- Latency (request start → response parsed)
- `league_id` (numeric, not PII — it's ESPN's league identifier, not a user identifier)
- `season`
- The view-name query string (`mTeam,mRoster,mSettings`) — currently constant, but log it so a future view-set change is visible in the data
- Whether the call carried a `Cookie` header at all — as a **boolean**
  (`auth_mode: 'public'|'cookie'`), matching the existing `espn_auth` column
  vocabulary already used in logs (`backend/server.py:18491-18494` logs
  `auth=%s`)
- Response payload size (bytes) and/or team count — useful for the "tens of KB"
  sizing question without touching content
- `EspnError.kind` when a call fails (`auth`/`not_found`/`http`/`parse`/`input`)
- Crosswalk match-rate report fields (`pool_players`, `matched_by_id`,
  `matched_by_name`, `match_rate`, `out_of_pool`, unmatched **count**) — these
  are already logged today at `backend/server.py:18491-18494`

**MUST-REDACT — never log, trace, or include in error payloads:**
- `espn_s2` value, in any form — full, truncated, or hashed-and-labeled-as-if-safe
  (its exact percent-encoding IS the credential; even a "safe-looking" partial
  reveals meaningful bytes given ESPN's cookie format is narrow)
- `SWID` value — it's both a credential component and a real user identifier
  (ESPN member GUID); do not log even though it's stored plaintext at rest —
  storage plaintext ≠ log-safe
- The full `Cookie` request header (contains both of the above concatenated)
- Any `Set-Cookie` response header ESPN returns (not currently read by the
  code, but if a future change reads one, it must be redacted by default)
- Full player/team/owner names or the raw response body — team/owner names are
  end-user-authored ESPN display data (arguably low-sensitivity, but not
  needed for instrumentation purposes; log counts, not content)
- The player-level `unmatched` list's actual names (log the **count** only,
  as the code already does in the `match_rate`/`unmatched` count logging —
  don't extend that to a name dump)

**Safe cookie-shape fingerprints** (useful for debugging the §4.3 encoding
issue without handling the secret): log booleans/lengths, never values —
e.g. `s2_len: int`, `s2_percent_encoded: bool` (does it contain a literal
`%` in a decodable position), `swid_len: int` (expect 38),
`swid_has_braces: bool`. A length or shape check is exactly what would have
caught the 2026-08-09 encoding mismatch (§4.3) without ever touching the
credential's contents.

### 6.2 `/api/espn/link` and `/api/espn/import` routes

**SAFE:** everything in §6.1, plus: `status: 'choose_team'|'imported'`
(preview vs. import), `teams_imported` count, `auth_mode` transition (e.g.
"pasted fresh cookie" vs. "reused stored cookie" vs. "public, no cookie" — as
an enum, not the cookie itself), whether the request came with `espn_s2` in
the body (boolean) vs. relied on the stored credential fallback (§2.4 step 2).

**MUST-REDACT:** the raw request body (`espn_s2`/`swid` fields) — if request
bodies are ever logged wholesale for debugging, these two keys need an
explicit strip/mask before that happens, the same way password fields would.

### 6.3 `GET /api/espn/leagues`

**SAFE:** league count returned, per-league `platform`/`season`/`espn_auth`
mode, member count. **MUST-REDACT:** nothing sensitive flows through this
route (it returns already-crosswalked Sleeper player ids and display names,
no cookies) — but the response is a full roster snapshot, so avoid logging
full response bodies in generic request-logging middleware; a size/count
summary is sufficient.

### 6.4 Draft-order derivation (`_espn_standings_read` / `_espn_suggested_order`)

**SAFE:** cache hit/miss, which season was used (current vs. one-back),
`derive_espn_draft_order`'s refusal reason when it returns `None` (§4.4) —
this is new, genuinely useful visibility and contains no PII (it's a
structural fact about the standings data shape, e.g. "missing
rank_calculated_final on N playoff teams").

**MUST-REDACT:** same credential rules as §6.1 apply — this path decrypts and
replays the same stored `espn_s2`/`swid`.

### 6.5 DynastyProcess crosswalk fetch (§1.4, GitHub not ESPN)

**SAFE:** fetch success/failure, whether serving live/cached/snapshot-fallback
data (`_xwalk_is_snapshot` boolean), row counts per id-map
(`by_espn_id`/`by_mfl_sleeper`/`by_sportradar_id`/`by_yahoo_id` sizes),
age of the cached copy. **MUST-REDACT:** n/a — this is a public CSV fetch with
no credentials involved; the only reason to be careful here at all is not to
confuse it with an ESPN egress in dashboards (tag it as `source: dynastyprocess`,
not `source: espn`).

### 6.6 Mobile WebView cookie capture (`EspnConnectScreen`)

This surface already has analytics events specced and shipping (not new
instrumentation to add, but relevant context for the build agent so it
doesn't duplicate them): `espn_connect_opened`, `espn_connect_otp_step`,
`espn_connect_captured` (`{saw_otp: bool}`), `espn_connect_abandoned`
(`{saw_otp: bool}`) — `backend/analytics_taxonomy.py:89-98,239-246`,
fired from `mobile/src/screens/EspnConnectScreen.tsx:95,107,111,149`. These
events carry **zero cookie content by design** — the injected JS
(`INJECTED_OTP_DETECT`, `EspnConnectScreen.tsx:44-69`) is presence-only
detection of the OTP form field, never reads field values, DOM text, or the
code itself. Any new instrumentation on this surface must preserve that
invariant: the two cookies are the only data that ever leaves the WebView
screen, and they go to `POST /api/espn/link`, never to analytics.

The 2026-08-09 reload additions (automatic warm-up reload, manual reload
control, wedge-detection hint) fire NO new analytics events — they're pure
client-side WebView chrome with no server round-trip, so there's nothing to
instrument at the `obs.api_events` layer; a future pass could add a client
event for reload taps if the field-failure rate needs tracking, but none was
specced for this iteration.

### 6.7 `fetch_fan_leagues` (fan-profile lookup, §1.7)

Same redaction posture as §6.1 — this is the SAME credential pair
(`espn_s2`/`SWID`) replayed against a different host, so the rules don't
change, only the endpoint class.

**SAFE to log:** everything in §6.1's safe list except `league_id` (not
meaningful here — this call discovers league ids, it doesn't take one) —
`service`/`endpoint` (`"espn"`/`"fan_profile"`), latency, HTTP status,
`auth_mode` (always `"cookie"`), the `s2_encoded`/`swid_braced` cookie-SHAPE
booleans (same fingerprint as §6.1, still zero bytes of the credential
itself), response size, `EspnError.kind` on failure. The COUNT of leagues
returned would be a reasonable addition if a future pass wants adoption
visibility (not currently in `OBS_EVENT_PROPS["api_call"]` — would need a
taxonomy addition first, per `backend/analytics_taxonomy.py`'s own rule that
new props are spec'd before they're sent).

**MUST-REDACT:** identical to §6.1 — `espn_s2`/`SWID` values in any form, the
full `Cookie` header, any `Set-Cookie` response header. Additionally: the
PARSED league list itself (`league_name`, `team_name`) is end-user-authored
ESPN display data — not logged by `observe_call` (which only ever sees the
raw HTTP call, never the parsed return value), and no call site should start
logging it either; a league/team NAME is exactly the same class of
low-sensitivity-but-unnecessary data §6.1 already excludes for `fetch_league`.
