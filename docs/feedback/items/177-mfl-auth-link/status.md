# #177 — MFL authenticated linking + import-all-leagues

**Status:** Built, dark behind `mfl.auth_link` (default OFF). 2026-07-25.

Operator ask: "Linking an mfl league should offer auth via mfl similar to
sleeper to import settings, rosters, picks, and teams. By default it should
allow a user to import all leagues at once. We should also explore send a
trade functionality directly back to mfl."

## What shipped

- **Backend** (`backend/mfl_service.py`, `backend/server.py` MFL region):
  - `mfl_service.login()` — POST to MFL's sanctioned
    `https://api.myfantasyleague.com/{year}/login` (USERNAME/PASSWORD/XML=1;
    POST per MFL's own security recommendation, so the password never rides
    a URL). Parses the `MFL_USER_ID="…"` cookie out of the `<status>` body;
    anything else → auth error.
  - `mfl_service.fetch_my_leagues()` — `export?TYPE=myleagues&FRANCHISE_NAMES=1`
    with the cookie; returns per-league `{league_id, name, host, franchise_id,
    franchise_name}` (tolerates id-only-in-URL and MFL's scheme-mangled
    homeURLs).
  - `POST /api/mfl/auth-link` — login + league list. **Password handling:**
    transient (the one login call), never persisted, never logged (no log
    line in these routes carries username or password; test-asserted via
    caplog). Stored artifact = the MFL cookie only, Fernet-encrypted in the
    new `mfl_credentials` table using the deployment's existing
    `SLEEPER_TOKEN_KEY`; key absent → **session-only** fallback (cookie in
    the in-memory session dict — which the persistent-sessions store never
    serializes — response says `storage:"session"`).
  - `POST /api/mfl/auth-import` — default **ALL** leagues from myleagues;
    optional `league_ids` subset. Sequential imports (MFL's ≥1s spacing
    guidance; `fetch_league_bundle` already self-spaces its four exports).
    Franchise **auto-detected** from myleagues' per-league `franchise_id` —
    no choose-team step; a league without one lands in `failed`
    (`mfl_franchise_unknown`) and remains linkable via the manual flow.
    Bundle fetches carry the cookie → **private leagues import**. Leagues
    persist with `platform_auth='cookie'`, and `POST /api/mfl/import`
    re-syncs those with the stored cookie.
  - Dead cookie on import → 409 `mfl_auth_expired`, stored credential
    dropped, client re-prompts sign-in.
- **Mobile** (`PlatformLinkSheet.tsx`, `api/platformLink.ts`, flag-gated via
  `useFlag('mfl.auth_link')`): "Or sign in with MFL to import all your
  leagues" path on the MFL sheet — username + password (secureTextEntry,
  cleared from state the moment the call returns, never logged/echoed) →
  league list with every auto-bindable league pre-checked → one-tap import →
  per-league success/failure summary. Honest error states for bad
  credentials / MFL down / expired sign-in.
- **Flag**: `mfl.auth_link` registered in `backend/feature_flags.py`,
  `config/features.json`, `backend/tests/fixtures/flags/release.json`,
  `docs/config-reference.md` — default false everywhere.

## Verified vs assumed (MFL API)

Verified against `api.myfantasyleague.com/2026/api_info` (2026-07-25): login
endpoint/params/POST recommendation, cookie name + Base64 value + Cookie
header format, myleagues params (`YEAR`, `FRANCHISE_NAMES`) and per-league
response fields, private-league access restricted to league owners.
Assumed (coded defensively): exact XML attribute quoting of the login
response (regex tolerates whitespace), myleagues JSON envelope
`{"leagues":{"league":[…]}}` following MFL's universal single-item-is-a-dict
convention (normalized via `_as_list`), and error bodies as `<error>` /
`{"error": …}` (both treated as auth failures on the authed paths).

## Send-trade-to-MFL

Exploration only — see [send-trade-feasibility.md](send-trade-feasibility.md).
Not built.

## Tests

`backend/tests/test_mfl_auth_link_route.py` (mocked MFL HTTP, no live creds):
flag-off 404s, bad-credentials 403, encrypted-at-rest round-trip, password
never logged/persisted, session-only fallback, import-all default with
auto-franchise, subset/unknown-league/missing-franchise/fetch-failure
per-league failures, expired-cookie 409 + credential drop, cookie reaching
bundle fetches, plus service-level login/myleagues parse tests (injected
opener, POST body asserted, password absent from the URL).
