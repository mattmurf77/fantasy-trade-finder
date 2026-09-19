# ESPN One-Click Trade Send — Research Report (2026-08-11)

> Subagent research: how to give ESPN users the same one-click trade send Sleeper users have today. Companion report: [send-in-mfl-research-2026-08-11.md](send-in-mfl-research-2026-08-11.md). Research only — no code written.

## 1. How "Send in Sleeper" works today (codebase)

**Mechanism: server-side replay of Sleeper's private GraphQL write API — not a deep link.** The user's Sleeper JWT is captured once in an in-app WebView, stored encrypted on the FTF backend, and the backend POSTs the reverse-engineered `propose_trade` mutation on the user's behalf.

Data flow:

1. **Token capture** — `mobile/src/screens/SleeperConnectScreen.tsx`: in-app WebView of sleeper.com login; reads the JWT out of the webview's localStorage (365-day HS256 token). Never sees the password.
2. **Link/store** — `POST /api/sleeper/link` (`backend/server.py:12163`): validates the token's claims, proves it live against Sleeper's GraphQL (`verify_token_live`, a `__typename` no-op probe), stores it Fernet-encrypted in `sleeper_credentials` (`backend/database.py:1273`). Key = env `SLEEPER_TOKEN_KEY`. Device Keychain copy enables silent re-link (`mobile/src/api/sendInSleeper.ts`).
3. **Send** — `SendInSleeperButton` (`mobile/src/components/SendInSleeperButton.tsx`, mounted in `TradesScreen`, `TradeCard`, `InLeagueCalculator`) → advisory `POST /api/trades/validate` (`server.py:20751`) → `POST /api/trades/propose` (`server.py:12294`) → `backend/sleeper_write.py`.
4. **The write** — `backend/sleeper_write.py`: POST `https://sleeper.com/graphql` with op `propose_trade`, raw JWT in `authorization` (no `Bearer`), plus spoofed browser UA/origin/referer headers to clear Cloudflare (error 1010 otherwise). Payload pairs every player in both `k_adds`/`k_drops` with receiving/giving `roster_ids`; draft picks inlined as `"orig,season,round,from,to"` strings; FAAB via `waiver_budget`. Returns `{transaction_id, status:"proposed"}`; the trade appears as a normal pending proposal in Sleeper.
5. **Gating & posture** — feature flag `trade.send_in_sleeper` (default OFF, `backend/feature_flags.py:112`), labeled "FLAGGED-BETA / ToS-adverse" throughout; disclosed in `web/privacy.html` / `web/terms.html`. Errors map to reconnect / deep-link fallback (`sleeper://` scheme nudge exists only as a share fallback in `web/js/app.js:5643`).

Key fact for parity thinking: **the entire UX is one tap because the backend holds a durable write credential and a captured payload spec.**

## 2. Current ESPN integration state (codebase)

- **`backend/espn_service.py`** — *read-only* adapter for ESPN's unofficial v3 API, base `https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl`. Browser-signature headers (same edge-filter lesson as Sleeper). Crosswalk to Sleeper player IDs via DynastyProcess `db_playerids.csv` (98–99% coverage of trade-relevant players per the plan doc).
- **Auth** — private leagues need `espn_s2` + `SWID` cookies; stored Fernet-encrypted in `espn_credentials` (`backend/database.py:1299`). `canonical_espn_s2`/`canonical_swid` normalize percent-encoding (2026-08-09 field failure: iOS cookie store surfaces espn_s2 decoded; the decoded form fails ESPN auth).
- **Routes** (all 404 dark unless `espn.link` is on): `POST /api/espn/link` (`server.py:18619`), `GET /api/espn/leagues`, `GET /api/espn/my-leagues` (fan.api.espn.com, behind `espn.league_picker`), `POST /api/espn/import`.
- **Flags**: `espn.link` (master + kill switch), `espn.webview_capture` (native cookie-store capture, mirrors SleeperConnectScreen), `espn.league_picker` — all default OFF (`backend/feature_flags.py:144-168`).
- **Trade surfaces**: ESPN leagues are read-only; `SendInSleeperButton` deliberately returns null for ESPN leagues (#146 — with a known UX gap: no copy explains why; see `backend/tests/fixtures/profiles/espn.json`).
- **Standing decision**: `docs/plans/espn-league-linking-plan-2026-07-11.md` §2/§7 says **"Send in ESPN (write) — ❌ never on this plan"** — rationale: writes against a Disney property are a categorically worse legal/ban posture than reads; "copy trade to clipboard is the ceiling." Also notes ESPN dynasty leagues don't expose tradeable future picks the way Sleeper's `traded_picks` does → any ESPN send is players-only. Reversing this requires a DECISIONS.md check per project rules.

## 3. ESPN's surface (external research)

**No official public API.** ESPN's fantasy API is undocumented and reverse-engineered; the community standard is the v3 API at `lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{yr}/segments/0/leagues/{id}`, with `espn_s2` + `SWID` cookies for private leagues ([Steven Morse's v3 writeup](https://stmorse.github.io/journal/espn-fantasy-v3.html), [cwendt94/espn-api](https://github.com/cwendt94/espn-api), [ffscrapr auth guide](https://ffscrapr.ffverse.com/articles/espn_authentication.html)).

**Trades CAN be proposed programmatically — a write host exists and the payload has been captured.** This is the headline finding:

- Write host: **`lm-api-writes.fantasy.espn.com`** — same path as reads, single endpoint `POST .../leagues/{id}/transactions/`; only the JSON body varies per operation.
- Verified (live-captured, fantasy *baseball*, 2026) trade-proposal envelope, from [garavitgabriel/espn-fantasy-claude-openclaw](https://github.com/garavitgabriel/espn-fantasy-claude-openclaw) (`docs/writes/00-BRIEF.md`, `docs/writes/wt-c-trades.md`, `espn_api/baseball/league.py`, `espn_api/requests/espn_requests.py`):
  - Body: `{isLeagueManager:false, teamId, type:"TRADE_PROPOSAL", memberId:<SWID>, scoringPeriodId, executionType:"EXECUTE", items:[{playerId, type:"TRADE", fromTeamId, toTeamId} …], expirationDate:"%Y-%m-%dT%H:%M:%S.000Z" (~2 days out), comment}` — give-items are `fromTeamId:me → toTeamId:other`, receive-items mirrored.
  - Headers: cookies `espn_s2`+`SWID`, plus `x-fantasy-platform: espn-fantasy-web`, `x-fantasy-source: kona`, `origin`/`referer: https://fantasy.espn.com`.
  - Response: PENDING + a proposal `id`; cancel = same endpoint, `executionType:"CANCEL"`, empty items, `relatedTransactionId`. Accept/reject payloads were never captured.
  - Independent corroboration of the write host + transactions endpoint for other sports: [AbdulsaboorS/fantasybasketballbot](https://github.com/AbdulsaboorS/fantasybasketballbot) (`espn_transactions.py`, `espn_lineup.py`), [mcolen5050/FantasyFootballAutomation_public](https://github.com/mcolen5050/FantasyFootballAutomation_public) (lineup writes for *football*).
- Mainline [cwendt94/espn-api](https://github.com/cwendt94/espn-api) remains read-only — no propose-trade support has been merged; [mkreiser/ESPN-Fantasy-Football-API #132](https://github.com/mkreiser/ESPN-Fantasy-Football-API/issues/132) is a long-open transactions request. So this is community-proven-but-not-in-a-mature-library territory: the football trade payload specifically has **not** been independently verified live (the capture above is baseball; football uses the same host/envelope but the pool/slot IDs differ).

**Deep links.** No verifiable pre-filled trade-proposal URL exists. ESPN's own docs describe only UI flows ("go to the opposing team's page, tap Propose Trade" — [ESPN Fan Support](https://support.espn.com/hc/en-us/articles/360039546211-Propose-Trade-on-the-ESPN-Fantasy-App)). Real URLs are league/team-scoped, e.g. `https://fantasy.espn.com/football/team?leagueId={id}&teamId={t}&seasonId={yr}` and `https://fantasy.espn.com/football/tradereview` — these land the user at the right league/team but do **not** pre-fill a trade. No documented `espn://` deep-link scheme for a specific trade proposal.

**Browser-extension route.** FTF's MV3 extension (`extension/manifest.json`) is today scoped **only** to `sleeper.com`/`sleeper.app` (content script decorates player rows with tiers). Extending it to drive fantasy.espn.com would require adding `https://fantasy.espn.com/*` host permissions and a content script that clicks through the trade UI. Viable in principle, but ESPN's fantasy front end is a React SPA with no stable public DOM contract — selectors break on any redesign, and the flow spans multiple async-rendered screens.

**Risks (external):**
- **ToS/automation.** ESPN/Disney terms direct automated use to official channels and specific properties prohibit "harvesting bots, robots, spiders, or scrapers" ([ESPN Fan Advisors terms](https://espnfanadvisors.com/terms-conditions/)). *Writes* from a server carry materially higher ban/legal risk than reads — the exact reason FTF's own plan said NO-GO.
- **Cookie fragility.** No source documents a definitive `espn_s2` lifetime; it persists across sessions but expires/rotates on logout or session reset, and downstream tools stop working until the user re-pastes fresh cookies ([League Loom](https://leagueloom.com/espn), [ffscrapr](https://ffscrapr.ffverse.com/articles/espn_authentication.html)). Treat it as opaque and refreshable, not long-lived like Sleeper's 365-day JWT. Disney SSO also injects OTP/2FA flows during capture (already noted in FTF's ESPN plan).
- **Precedent of breakage.** ESPN has repeatedly broken unofficial consumers — mass HTTP 403 ([cwendt94/espn-api #547](https://github.com/cwendt94/espn-api/issues/547)), auth-flow changes ([#58](https://github.com/cwendt94/espn-api/issues/58)), and the read↔leagueHistory endpoint-format fallback baked into the library from prior breakage.

## 4. Ranked options for ESPN one-click send

### Option A — Server-side unofficial write API (true parity with Sleeper) — RECOMMENDED with caveats
- **Mechanism:** backend POSTs `TRADE_PROPOSAL` to `lm-api-writes.fantasy.espn.com/.../transactions/` using stored `espn_s2`+`SWID`. Direct analogue of `sleeper_write.py`; FTF already stores the cookies encrypted and has the crosswalk to translate its Sleeper player IDs → ESPN `playerId`.
- **Auth needed:** existing `espn_credentials` (espn_s2 + SWID). No new capture surface.
- **Effort:** **M.** New `espn_write.py` mirroring `sleeper_write.py`; a `/api/trades/propose` ESPN branch; unmap Sleeper→ESPN player IDs; extend `SendInSleeperButton` (or a sibling) to un-null for ESPN. Payload spec is largely known.
- **Reliability/ToS:** highest reliability *while it works* (one tap, no user context switch); **highest ToS/ban risk** (server writes to Disney) and directly contradicts the current plan's NO-GO — needs an operator/DECISIONS reversal. **Football trade payload is unverified live** — the captured spec is baseball; needs a spike.
- **Degrades when ESPN changes:** if the write host/envelope changes → hard failure (blank error / 403); if cookies rotate → auth error, prompt reconnect. No graceful partial. Players-only (no ESPN pick support).

### Option B — Browser-extension-assisted autofill (desktop web only)
- **Mechanism:** extend the MV3 extension to `fantasy.espn.com`; content script navigates the user to the counterparty's team page and programmatically fills/clicks the native Propose Trade UI with the FTF-selected players. The *user's own browser session* performs the write — no stored server credential, arguably a lighter ToS posture (it's automating the user's own authenticated clicks).
- **Auth needed:** none server-side; relies on the user being logged into espn.com in that browser.
- **Effort:** **L.** New host permissions, a multi-step DOM automation against an undocumented React SPA, player-name→row matching, plus the fact FTF's primary client is mobile (extension is desktop-only, so this doesn't cover the mobile app at all).
- **Reliability/ToS:** medium ToS risk (client-side automation of the user's session); **low reliability** — DOM selectors break on any ESPN redesign with no version contract.
- **Degrades when ESPN changes:** silent mis-clicks or dead flow on any markup change; brittle by nature. Desktop-only.

### Option C — Deep link to the right team/trade screen + clipboard hand-off
- **Mechanism:** copy a formatted trade summary to clipboard and open `https://fantasy.espn.com/football/team?leagueId=…&teamId=…&seasonId=…` (or the app if installed) at the counterparty's team; user taps Propose Trade and re-picks the players manually. This is the "copy trade to clipboard is the ceiling" the plan endorses.
- **Auth needed:** none.
- **Effort:** **S.** Build the deep-link URL from data FTF already has; reuse the existing clipboard/toast pattern from `web/js/app.js`.
- **Reliability/ToS:** **zero ToS risk, highest durability.** Not one-click (user re-enters the trade), so not true parity.
- **Degrades when ESPN changes:** worst case the URL 404s and the app opens home; clipboard text always survives. Most robust option.

### Option D — Pre-filled instructions fallback
- **Mechanism:** show a step-by-step card ("Trade with Team X: give A, B; receive C") with a Copy button and a "How to propose on ESPN" link. Pure content.
- **Effort:** **XS.** No auth, no external calls.
- **Reliability/ToS:** none/none. This is the guaranteed fallback under every other option.

## 5. Recommendation

**Ship C (deep link + clipboard) now as the shipped "Send to ESPN" — with D as its always-present fallback — and run a scoped spike on A before committing to true parity.**

Reasoning:
- Option A is the only path to genuine one-tap parity, and it is *more feasible than the codebase's current NO-GO assumes*: the write host and `TRADE_PROPOSAL` envelope are community-captured, and FTF already stores the exact credentials and owns the player-ID crosswalk. But it (a) reverses a logged plan decision, (b) is the highest ban-risk action against a Disney property, and (c) rests on a baseball-captured payload never verified for football. That combination is a spike, not a build.
- Option C delivers real user value immediately at zero platform risk and zero decision reversal, and it doubles as the mandatory fallback for A anyway. It closes the current UX gap (#146: ESPN cards show only "Dismiss" with no explanation).
- Option B is dominated: desktop-only (misses FTF's mobile-first users), brittlest, and not clearly lower ToS risk than A.

Suggested sequence: C+D behind an `espn.send` flag → spike A (see unknowns) → if the spike is clean and the operator reverses the NO-GO in DECISIONS.md, layer A on top with C/D as automatic fallback.

## 6. Key unknowns needing a spike

1. **Football write payload.** Verify `TRADE_PROPOSAL` against `lm-api-writes.fantasy.espn.com` for `ffl` on a real dynasty league — confirm `scoringPeriodId`/`seasonId` handling, `playerId` space (does the crosswalk's `espn_id` equal the write-API `playerId`?), and item direction. The only live capture is baseball.
2. **Auth sufficiency for writes.** Do read cookies (`espn_s2`+`SWID`) authorize writes, or does ESPN require an additional CSRF/session token or `x-fantasy-*` header not in the read path? Capture a real browser propose-trade request to confirm.
3. **`espn_s2` lifetime & refresh UX.** Measure actual expiry on a live token; design silent re-auth (FTF's Sleeper Keychain-replay pattern won't transfer since ESPN cookies rotate more aggressively).
4. **Dynasty pick handling.** ESPN doesn't expose tradeable future picks like Sleeper — confirm whether picks can even be included in an ESPN `TRADE_PROPOSAL` item, or whether every ESPN send is players-only (and word the UI accordingly).
5. **League-vote / approval mechanics.** ESPN leagues route proposals through league vote/veto and (in some settings) commissioner review — confirm the proposal lands as PENDING correctly and that "proposed" means the same thing it does on Sleeper.
6. **ToS/decision reversal.** Operator sign-off + DECISIONS.md entry required before any A work, given the explicit NO-GO in `docs/plans/espn-league-linking-plan-2026-07-11.md`.

## Sources

- FTF codebase: `backend/sleeper_write.py`, `backend/espn_service.py`, `backend/server.py` (routes 12163/12294/18619/20751), `backend/database.py` (1273/1299), `backend/feature_flags.py`, `mobile/src/components/SendInSleeperButton.tsx`, `mobile/src/screens/SleeperConnectScreen.tsx`, `web/js/app.js`, `extension/manifest.json`, `docs/plans/espn-league-linking-plan-2026-07-11.md`, `backend/tests/fixtures/profiles/espn.json`
- https://github.com/cwendt94/espn-api and issues [#547](https://github.com/cwendt94/espn-api/issues/547), [#58](https://github.com/cwendt94/espn-api/issues/58); [mkreiser/ESPN-Fantasy-Football-API #132](https://github.com/mkreiser/ESPN-Fantasy-Football-API/issues/132)
- https://github.com/garavitgabriel/espn-fantasy-claude-openclaw (write API brief + trade payload)
- https://github.com/AbdulsaboorS/fantasybasketballbot, https://github.com/mcolen5050/FantasyFootballAutomation_public
- https://stmorse.github.io/journal/espn-fantasy-v3.html, https://ffscrapr.ffverse.com/articles/espn_authentication.html, https://leagueloom.com/espn
- https://support.espn.com/hc/en-us/articles/360039546211-Propose-Trade-on-the-ESPN-Fantasy-App, https://support.espn.com/hc/en-us/articles/4408412998804-League-ID
- https://espnfanadvisors.com/terms-conditions/, https://www.semaphorepartners.com/post/when-apis-dont-exist-we-make-our-own-a-fantasy-football-data-integration-story
