# MFL One-Click "Send in MFL" — Research Report (2026-08-11)

> Subagent research: how to give MFL users the same one-click trade send Sleeper users have today. Companion report: [send-in-espn-research-2026-08-11.md](send-in-espn-research-2026-08-11.md). Research only — no code written.

## 1. How "Send in Sleeper" works today in FTF

**Mechanism: server-side authenticated API write, not a deep link.** FTF captures the user's Sleeper JWT via a login webview, stores it Fernet-encrypted, and the Flask backend replays Sleeper's **private, undocumented GraphQL `propose_trade` mutation** (captured from live web traffic 2026-07-02). It is flag-gated (`trade.send_in_sleeper`, default OFF) and explicitly marked ToS-adverse.

Data flow:

1. **Mobile UI** — `mobile/src/components/SendInSleeperButton.tsx` mounts on every real trade surface (`TradesScreen.tsx`, `TradeCard.tsx`, `InLeagueCalculator.tsx`). One button, two paths: linked → pre-flight validate → confirm → propose; unlinked → `SleeperConnectScreen` login webview to capture the JWT.
2. **Client API** — `mobile/src/api/sendInSleeper.ts`: `POST /api/sleeper/link` (store/verify token, also silently replayed from iOS Keychain per #126), `POST /api/trades/validate` (#180 advisory pre-send checks), `POST /api/trades/propose` (payload: `league_id`, `their_user_id`, `give_player_ids[]`, `receive_player_ids[]` — **players-only v1**; the route accepts pre-encoded `draft_picks[]` `"orig,season,round,from,to"` strings but mobile never sends them).
3. **Backend route** — `backend/server.py:12294` `propose_trade_to_sleeper()`: requires a **verified** session (proof-of-control via the token oracle), decrypts the stored token, resolves both `roster_id`s server-authoritatively from a public rosters fetch, then calls the adapter. Structured error codes (`sleeper_not_linked`, `sleeper_expired`, `sleeper_rejected`, `verification_required`, …) drive reconnect/fallback UX client-side.
4. **Adapter** — `backend/sleeper_write.py`: pure, opener-injectable module; POSTs `https://sleeper.com/graphql` with the raw JWT in `authorization` plus spoofed browser headers to clear Cloudflare (error 1010). Also has `reject_trade`, token introspection/expiry, and `verify_token_live` (the auth oracle).
5. **Fallbacks** — web (`web/js/app.js:5632`) only uses share-sheet/clipboard + a bare `sleeper://` scheme nudge; there is no trade-prefill deep link because Sleeper has none.

**Notable gap found:** `SendInSleeperButton` self-gates on ESPN leagues only (`platform === 'espn'`, #146) — it does **not** hide on MFL/Fleaflicker leagues. Since MFL league ids are numeric, they pass the route's `league_id.isdigit()` check and a send would fire against Sleeper's API and fail at roster resolution. An MFL send feature would naturally fix this by making the button platform-aware.

## 2. Current MFL integration state in the codebase

Files: `backend/mfl_service.py` (742-line pure adapter), routes in `backend/server.py` (`/api/mfl/link|leagues|import|auth-link|auth-import`), reference doc `docs/integrations/mfl.md`, mobile client `mobile/src/api/platformLink.ts` + `PlatformLinkSheet`.

- **Read-only today.** Nine endpoints, all official sanctioned `export` API calls: `league`, `rosters`, `futureDraftPicks`, `players`, `rules`, `draftResults`, `myleagues`, plus host resolution and `login`. All league-scoped calls hit the league's assigned `wwwNN.myfantasyleague.com` host (the `api.` host returns empty for league data — verified gotcha).
- **Auth we already hold:** flag `mfl.auth_link` (#177) does `POST https://api.myfantasyleague.com/{year}/login` with USERNAME/PASSWORD (password transient, never stored/logged), and persists the returned **`MFL_USER_ID` session cookie**, Fernet-encrypted in `mfl_credentials` (`backend/database.py:1339`), reusing `SLEEPER_TOKEN_KEY`. This is exactly the credential MFL's write API requires. Cookie lifetime is undocumented; 401/403 → reconnect UX.
- **Franchise mapping:** the linking user's franchise is persisted (`platform_my_team`, from `myleagues`' `franchise_id`); every other franchise is stored as synthetic member id `mfl:{league_id}.f{franchise_id}` — so the counterparty's `OFFEREDTO` franchise id is parseable today.
- **Player-ID mapping:** DynastyProcess crosswalk where **`mfl_id` is the primary key** (~100% skill-player coverage; `Player <mfl_id>` name fallback for unmatched). Reverse mapping (Sleeper id → MFL id) exists in the same crosswalk (`data_loader.py` builds `by_mfl_id`).
- **Picks:** raw `futureDraftPicks` snapshots stored per league (`leagues.platform_future_picks`), refreshed on the draft-status cadence (#207/#228) — this holds the ground truth needed to construct MFL pick-asset ids.
- **Rate-limit posture:** ≥1s spacing between calls, `MFL_USER_AGENT` env (client registration with MFL **not yet done** — tracked in `docs/plans/multi-platform-linking-plan-2026-07-17.md` §9 Q1).
- **Prior art:** `docs/feedback/items/177-mfl-auth-link/send-trade-feasibility.md` already scoped this exact feature (2026-07-25, exploration only). The web research below independently confirms its claims and resolves one of its unknowns.

## 3. MFL's write surface (verified against official docs)

From `https://api.myfantasyleague.com/2026/api_info` and the Request Reference (`?STATE=details`):

- **`import?TYPE=tradeProposal`** exists and is first-class. Params (exact): `L` (league id), `OFFEREDTO` ("Target franchise id of the trade proposal"), `WILL_GIVE_UP` / `WILL_RECEIVE` ("Comma-separated list of player ids or other assets"), optional `COMMENTS`, `EXPIRES` ("Unix time… default is one week"), `FRANCHISE_ID` (commissioner impersonation). "Access restricted to league owners."
- **Asset formats (documented, resolving the prior doc's biggest unknown):** current-year draft picks `DP_02_05` (round/slot, **zero-based** — "3rd round, 6th pick"); future picks `FP_0005_2018_2` (**original-owner franchise id, year, round**); blind-bid dollars `BB_10.50`. Players are bare MFL player ids.
- **`import?TYPE=tradeResponse`** — `L`, `TRADE_ID`, `RESPONSE=accept|reject|revoke`, optional `COMMENTS` — enables later revoke/accept flows. **`export?TYPE=pendingTrades`** returns pending trades (owner-restricted) for status display.
- **Auth model:** three options — login cookie (`Cookie: MFL_USER_ID=…`), or `APIKEY` param, **but APIKEY works for exports only, "not imports or commissioner operations"** → writes require the session cookie FTF already stores. Login should be HTTPS POST.
- **Rate limits/registration:** throttled requests return **HTTP 429**; limits are unpublished and variable; registered clients (form + cell-phone validation + fixed User-Agent) get ~2.5× higher limits; guidance: 1s spacing, cache, don't retry on failure.
- **ToS:** the api_info page forbids collecting user info without permission or "attempt[ing] to make changes to someone's fantasy league/team **without their permission**" — a user proposing their own trade through their own credentials is squarely permitted; MFL even publishes a public per-league test harness for `tradeProposal` (e.g. `www76.myfantasyleague.com/2020/api_info?CCAT=import&L=33393&STATE=test&TYPE=tradeProposal`), i.e. third-party writes are sanctioned by design.
- **Deep links:** league pages are `https://{wwwNN}.myfantasyleague.com/{year}/options?L={id}&O={module}` (`O=07` is Rosters; the owner-action modules bounce to Login when unauthenticated). **No documented querystring prefill of a trade-proposal form was found** — a deep link can land on the league site but cannot carry the trade contents, and FTF's mobile users are typically not logged into MFL in Safari. Ecosystem tools (ffscrapr/ffverse etc.) are read-focused; the official MFL Mobile app does trades first-party.

## 4. Ranked options

| # | Option | Mechanism | Auth needed | Effort | Reliability / ToS risk |
|---|---|---|---|---|---|
| **A** | **Authenticated API `tradeProposal` import** (recommended) | Backend GETs/POSTs `import?TYPE=tradeProposal&L=…&OFFEREDTO=f…&WILL_GIVE_UP=…&WILL_RECEIVE=…&EXPIRES=…` against the league's `wwwNN` host with the stored `MFL_USER_ID` cookie | Already held for auth-linked users (#177); manual/public-linked users must add MFL sign-in first | ~2–3 days: adapter fn + route + reverse-crosswalk guardrails + platform-aware send button + tests | **High reliability, sanctioned API, low ToS risk** — the inverse of the Sleeper path. Risks: undocumented cookie lifetime; unverified import response shape; unregistered-client throttling (429) |
| B | Deep link to the MFL trade page | Open `https://{wwwNN}.myfantasyleague.com/{year}/options?L={id}&O=<trade module>` in browser | None (user's own browser session) | Hours | Degraded UX: no prefill support found, user re-enters the whole trade, likely hits a login wall. Zero ToS risk. Good as the **fallback** path (mirroring Sleeper's error-path handoff) |
| C | Extension-assisted autofill | MV3 extension content script fills MFL's trade form from FTF data | User's browser session | Days; desktop-web only; brittle against MFL markup churn | Medium risk (scraping-adjacent), tiny reach vs. the mobile app where the feature matters |
| D | Instructions/clipboard fallback | Copy a formatted trade summary + open MFL | None | Hours | No risk, no magic — only as last-resort copy on failure |

## 5. Recommended approach

**Option A**, sequenced behind a new flag (e.g. `trade.send_in_mfl`), with **B as the in-flow fallback** on auth/write failure — structurally identical to the existing Sleeper pattern, so most scaffolding (encrypted credential storage, verified-session gating, structured error → reconnect UX, opener-injected adapter + fixture tests, `#180`-style pre-flight against a fresh `rosters` export) is reusable. Reasoning: unlike Sleeper, this rides a documented, sanctioned write API using a credential FTF already stores; the DP crosswalk's `mfl_id` primary key makes reverse player mapping near-total; and stored `platform_future_picks` provides ground truth for pick-asset construction. Guardrails: hard-block the send if any asset fails reverse-mapping (never silently drop an asset), default `EXPIRES` (~7 days), keep ≥1s spacing, and make the send button platform-aware (also fixing the current "Sleeper button renders on MFL leagues" gap).

**Key unknowns needing a spike (live probe against a sandbox/test league before building):**
1. **Import response shape** — success/error body for `tradeProposal` (`<status>OK</status>` XML? does `JSON=1` apply?) is undocumented; build fixtures from a live capture.
2. **Import host** — confirm imports must hit the league's `wwwNN` host like exports (the docs don't say; FTF verified exports fail on `api.` host).
3. **Pick-asset ids in practice** — confirm `FP_{franchise}_{year}_{round}` zero-padding and `DP_` zero-based indexing against a real league's `assets`/`futureDraftPicks` exports; map FTF pick rows → MFL notation.
4. **Cookie durability and season boundary** — does a `{year}`-minted `MFL_USER_ID` cookie survive into the next season path? (Prior doc flags this; field data from `mfl_auth_expired` rates will answer it.)
5. **Commissioner-locked / trade-disabled leagues** — what error the import returns so it can surface cleanly.
6. **Client registration** — complete MFL's client registration (form + phone validation) before shipping; unregistered write traffic is the most throttle-exposed.

**Key files:** `backend/sleeper_write.py`, `backend/server.py:12294` (`/api/trades/propose`), `backend/mfl_service.py`, `backend/database.py:1324–1339` (`mfl_credentials`), `mobile/src/components/SendInSleeperButton.tsx`, `mobile/src/api/sendInSleeper.ts`, `mobile/src/api/platformLink.ts`, `docs/integrations/mfl.md`, `docs/feedback/items/177-mfl-auth-link/send-trade-feasibility.md`.

## Sources

- [MFL Developers Program — api_info 2026](https://api.myfantasyleague.com/2026/api_info) — auth methods (login POST, `MFL_USER_ID` cookie, APIKEY exports-only), registration (~2.5× limits, phone validation, fixed User-Agent), 429 throttling, 1s-spacing guidance, ToS clause on unauthorized changes
- [MFL Request Reference 2026 (`?STATE=details`)](https://api.myfantasyleague.com/2026/api_info?STATE=details) — `tradeProposal` / `tradeResponse` / `pendingTrades` parameters, access restrictions, `DP_`/`FP_`/`BB_` asset formats
- [MFL tradeProposal test harness (2026)](https://api.myfantasyleague.com/2026/api_info?STATE=test&CCAT=import&TYPE=tradeProposal) — public per-request test form confirming the import surface
- [Example league-scoped tradeProposal test page](https://www76.myfantasyleague.com/2020/api_info?CCAT=import&L=33393&STATE=test&TYPE=tradeProposal) — third-party writes sanctioned per-league
- [MFL league options URL pattern, e.g. `O=07` Rosters](https://www46.myfantasyleague.com/2026/options?L=42046&O=07); owner-action module `O=05` [bounces to Login](https://www46.myfantasyleague.com/2026/options?L=42046&O=05) — no querystring trade prefill found
- [ffscrapr MFL endpoint article (ffverse)](https://ffscrapr.ffverse.com/articles/mfl_getendpoint.html) — community tooling is read-focused; auth/API-key injection supported
- [MFL Mobile (official app)](https://apps.apple.com/app/id639397317) — first-party trade support
