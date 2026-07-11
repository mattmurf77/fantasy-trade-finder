# ESPN League Linking — Plan (#101, 2026-07-11)

*"I want to link my ESPN account and leagues." Decision-ready plan + spike for importing ESPN Fantasy Football leagues into an app that is keyed end-to-end on Sleeper `player_id`s. Spike code: `backend/espn_service.py` (isolated — nothing imports it yet) + `backend/tests/test_espn_service.py` + two fixtures. This doc is the go/no-go artifact; wiring happens only if the recommendation below is accepted.*

**Recommendation up front: conditional GO** — ship Phase 1 (read-only import, feature-flagged) and Phase 2 (consensus-basis trade tools on ESPN rosters). **NO-GO indefinitely** on any ESPN write path ("Send in ESPN") and on mutual-match features until ≥2 real users ask. Rationale in §6.

---

## 1. ESPN API research (facts as of 2026-07-11)

There is **no official ESPN fantasy API** — ESPN retired its public developer API in 2014; everything below is the community-reverse-engineered v3 API that ESPN's own web/app clients use.

| Fact | Detail | Source (date) |
|---|---|---|
| Read endpoint | `https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{yr}/segments/0/leagues/{id}?view=mTeam&view=mRoster&view=mSettings` (composable `view=` params: `mTeam`, `mRoster`, `mSettings`, `mMatchup`, `kona_player_info`, …) | [stmorse v3 guide](https://stmorse.github.io/journal/espn-fantasy-v3.html) (2019, still-canonical shape); **verified live by us 2026-07-11** |
| Endpoint churn | v2→v3 migration Feb 2019; host moved from `fantasy.espn.com` to `lm-api-reads.fantasy.espn.com` in the 2023→2024 window, silently breaking every client until they chased it. Expect ~one breaking change per season. | [ffscrapr get-endpoint vignette](https://ffscrapr.ffverse.com/articles/espn_getendpoint.html); [espn-api #539 (403s)](https://github.com/cwendt94/espn-api/issues/539) |
| Private-league auth | Two cookies from a logged-in espn.com session: `espn_s2` (long, URL-encoded — must be replayed **verbatim**) + `SWID` (braced GUID, doubles as the member ID in league payloads). No OAuth, no scoped tokens, no official sanction. | [espn-api README](https://github.com/cwendt94/espn-api) (accessed 2026-07-11); [ffscrapr auth vignette](https://ffscrapr.ffverse.com/articles/espn_authentication.html) |
| Cookie lifetime | Not documented. Community consensus ≈ 1 year for `espn_s2`; `SWID` is effectively permanent. Treat expiry as undocumented and handle 401 → reconnect gracefully (same posture as our 365-day Sleeper JWT). | [GameDayBot help](https://www.gamedaybot.com/help/espn_s2-and-swid/); [espn-api discussion #150](https://github.com/cwendt94/espn-api/discussions/150) |
| Public leagues | Readable with **no auth at all** when the league is set "viewable to public". 401/403 = private; 404 = league absent that season. **Verified live 2026-07-11**: endpoint returns exactly these semantics. | our probes; [espn-api README](https://github.com/cwendt94/espn-api) |
| Data purging | ESPN deletes/expires old leagues: the public test leagues the espn-api suite used for years (`1234`, `368876`, `48153503`) all 404 now, on both the season and `leagueHistory` endpoints (**verified 2026-07-11**). Off-season imports of last-season leagues may vanish. | our probes 2026-07-11 |
| How existing tools cope | [cwendt94/espn-api](https://github.com/cwendt94/espn-api) (Python, active, the de-facto standard) takes `espn_s2`/`swid` constructor args and since 2025-08-20 ships a Chrome extension to harvest the cookies; [mkreiser/ESPN-Fantasy-Football-API](https://github.com/mkreiser/ESPN-Fantasy-Football-API) (JS) notes private leagues **only work from Node** — browsers can't set the Cookie header cross-origin (relevant: our web SPA can't do private-league reads client-side; backend must proxy). ffscrapr wraps the same cookies for R. | repos, accessed 2026-07-11 |
| Rate limits / ToS | No published limits; community tools poll politely (single-league reads, no fan-out) and survive. Non-browser User-Agents intermittently get 403'd (espn-api #539) — the spike sends browser-signature headers, the same lesson as our Sleeper Cloudflare-1010 fix. ToS-wise this is unsanctioned scraping of a Disney property: low practical enforcement (a decade of public tools, GameDayBot et al. operate openly), but **zero contractual protection** — ESPN can break or block us any season with no notice. | [espn-api #539](https://github.com/cwendt94/espn-api/issues/539); [zuplo hidden-API guide](https://zuplo.com/learning-center/espn-hidden-api-guide) (2024) |

### Live probes run for this plan (2026-07-11)

- `GET …/seasons/2025/segments/0/leagues/1086064?view=mTeam` → **401** (private league, endpoint + auth semantics alive)
- Known historical public leagues (`1245163`, `1234`, `368876`, 2017–2019) → **404** on both season and `leagueHistory` endpoints (purged)
- Consequence: the spike's tests run on a **recorded-shape fixture** with real ESPN player IDs (see §5), and Phase 1 must include a "point it at a real public league" smoke step before merge.

---

## 2. Mapping ESPN concepts onto our model

Everything in the app keys on Sleeper IDs: `users.sleeper_user_id` (PK), `leagues.sleeper_league_id` (PK), `players.player_id` (Sleeper), rosters as Sleeper-ID arrays in `league_members.roster_data`.

| ESPN concept | Our model | Fit |
|---|---|---|
| League (`id`, `settings.name`, `settings.size`, `seasonId`) | `leagues` row. **Needs a `platform` column** (`'sleeper'` default / `'espn'`) — cleaner than magic-prefix IDs (`espn:123`) because `sleeper_league_id` is a PK that other tables join on as opaque text; a prefix would silently flow everywhere (accepted: PK column name becomes slightly a lie; rename is not worth the migration). ESPN league IDs are numeric and collide with nothing today, but `platform` makes that explicit. `total_rosters` ← `settings.size`. | Clean, one ALTER |
| Team/roster (`teams[].roster.entries[].playerId`) | `league_members.roster_data` as **crosswalked Sleeper IDs** (§3). K/D-ST dropped (outside our QB/RB/WR/TE pool — same as Sleeper leagues today). | Clean once crosswalked |
| Owner (`teams[].primaryOwner` = SWID, `members[].displayName`) | `league_members.user_id`. Counterparties are not FTF users: store `espn:{SWID}` synthetic IDs + displayName. The **linking** user maps to their real FTF `user_id` by matching their own SWID (we hold it from auth). | OK; synthetic IDs must never leak into push/notification paths |
| Player (`playerId`, `fullName`, `defaultPositionId`) | `players.player_id` via crosswalk — **the hard part**, solved in §3 (99.2% on the pool that matters). | Solved |
| Future draft picks | **Gap.** ESPN dynasty/keeper leagues don't expose tradeable future picks the way Sleeper's `traded_picks` endpoint does. `draft_picks` stays empty for ESPN leagues → pick-inclusive trade suggestions and Pick Anchor pricing of league picks silently degrade to players-only. Acceptable for v1; must be stated in UI copy. | Gap, accept |
| Credentials | New `espn_credentials` table (`user_id` PK, `swid`, `espn_s2_encrypted`, `expires_hint_at`, timestamps) reusing the **exact** Fernet pattern of `sleeper_credentials` / `sleeper_write.py`. Folds into the auth epic's `linked_sources` when that lands, same as the Sleeper row. | Clean |

### Feature matrix

| Feature | ESPN status | Why |
|---|---|---|
| League import, roster view, Tiers/Ranks per league | ✅ **read-only, works** | Just needs rosters in Sleeper-ID space |
| Trade Finder — consensus-basis cards | ✅ **works** | Engine already serves consensus-basis cards for opponents with no rankings (v2 path); ESPN counterparties are exactly that |
| Trade Finder — divergence cards, mutual matching, likes-you, match inbox | ⚠️ **only if the counterparty is also an FTF user linked to the same ESPN league** — realistically dead until multi-user ESPN adoption; the plumbing works platform-agnostically once `league_members.user_id` is real | Requires both sides ranked in-app |
| Push notifications to counterparties | ❌ synthetic `espn:{SWID}` members have no devices | Same as unlinked Sleeper members |
| Pick-inclusive trades / league pick assets | ❌ v1 (no ESPN pick data) | §2 gap |
| **Send in ESPN** (write) | ❌ **never on this plan** | Write mutations are a separate un-reverse-engineered surface; doing unsanctioned *writes* against a Disney property from our server is a categorically worse legal/ban posture than reads. Manual "copy trade to clipboard" is the ceiling. |

---

## 3. Player-ID crosswalk (the hard part — measured, not guessed)

**Source: DynastyProcess [`db_playerids.csv`](https://github.com/dynastyprocess/data)** — 12,468 rows, columns include `sleeper_id`, `espn_id`, `merge_name`, `position`, `team`. Decisive advantages: (a) we **already trust and fetch DynastyProcess at boot** (`data_loader.py` pulls `values-players.csv` from the same repo — same operational surface, same failure mode, same license posture); (b) it's maintained daily by the ffverse team; (c) it also carries MFL/Yahoo/etc. IDs, so Yahoo league linking later reuses this design unchanged.

**Measured coverage (2026-07-11 snapshot vs our live `players` table, 2,684 skill players):**

| Pool | espn_id via `sleeper_id` join | + name+pos fallback | Total |
|---|---|---|---|
| A: all 2,684 app skill players | 62.9% | +1.1% | **64.0%** |
| **B: the 615 value-relevant players** (DP `value_1qb > 0` — the universal ranking pool, i.e. every player that can appear in a trade) | **98.4%** | +0.8% | **99.2%** |

Pool A's misses are almost entirely teamless deep-bench/practice-squad bodies that never appear on an ESPN roster *or* in a trade. Pool B's 5 residual misses are deep rookies/UDFAs (e.g. Joey Aguilar, RJ Maryland) plus one name-collision artifact — all sub-1% of value volume. **Verdict: the crosswalk is a solved problem via DP; do not build name-matching as the primary mechanism** (keep normalised `name+position` only as the fallback tier, reusing `data_loader.normalise_name` and its suffix-mapping lessons).

**Design (Phase 1):**
1. Nightly + boot: fetch `db_playerids.csv` alongside the values CSV; build `{espn_id → sleeper_id}` in memory (12k rows, trivial). No schema change needed; if we later want persistence, an `espn_id` column on `players` is a one-line ALTER, but in-memory matches how consensus values already work.
2. Import path: ESPN roster entry → espn_id lookup → fallback name+pos → else **drop the player and log** (`espn_import` event with unmatched list). Never invent placeholder players.
3. Store only Sleeper IDs downstream — zero changes to ranking/trade/tier code, which is the whole point.

---

## 4. Auth UX (no OAuth exists — options, honestly)

ESPN login is Disney SSO (email + password/OTP, `registerdisney` iframe). The only credentials worth holding are the two cookies.

**Option 1 — WebView cookie capture (recommended, mirrors `SleeperConnectScreen.tsx`):** in-app WebView to espn.com login; on success read `espn_s2` + `SWID` **from the native cookie store** (`@react-native-cookies/cookies` over WKHTTPCookieStore) — *not* injected-JS `document.cookie`, since `espn_s2` can be HttpOnly; the native store reads it regardless. POST to `/api/espn/link`, encrypt at rest (Fernet, `sleeper_write.py` pattern). Differences from the Sleeper screen: cookie store instead of localStorage JWT, and Disney SSO renders some flows (OTP emails) that the banner copy must warn about. We never see the password — same honest claim as the Sleeper screen.

**Option 2 — manual paste:** "open espn.com in Safari, devtools/extension, paste two strings." Fine on web/desktop as a **fallback row in Settings**; hostile on iOS as the primary path (Safari on iOS has no devtools; users would need a desktop). cwendt94 shipping a dedicated Chrome extension for this (2025-08) is evidence that even technical users find manual capture painful.

**Option 3 — public-league-only v1 (zero auth):** link by pasting a league ID; works only if the league is set publicly viewable. Worth shipping *inside* Phase 1 as the free tier of the feature (it's ~20 lines on top of the same import path) but most real leagues are private, so it can't be the whole story.

**App Store review risk — honest assessment: moderate, and we've already accepted this class of risk.** The shipped Sleeper JWT capture is the same pattern (third-party login inside a WebView, harvesting a session credential). Specific exposure: Guideline 5.2.2 (third-party content without authorization) is enforced sporadically and complaint-driven — Disney is exactly the kind of rights-holder that files complaints; ESPN league importers do exist on the App Store (Fantasy Life, FantasyPros importers), which is helpful precedent but not protection. Mitigations: read-only scope, explicit consent copy ("we read your leagues and rosters; we never post or change anything"), feature flag + server kill switch so a rejection or ESPN block doesn't strand the app, and never mentioning "scraping ESPN" in App Store copy. Residual risk we cannot mitigate: an ESPN C&D or targeted block ends the feature; the flag makes that a config flip, not an emergency release.

---

## 5. Spike results (done, this branch)

`backend/espn_service.py` — isolated module, no server wiring:
- `fetch_league()` — v3 reads endpoint, browser-signature headers, verbatim cookie passthrough, 401/403→auth, 404→not_found, injected `_opener` (offline-testable, same as `sleeper_write.py`).
- `parse_league()` — mTeam+mRoster+mSettings → teams/owners/players.
- `load_crosswalk()` + `map_rosters()` — DP crosswalk → Sleeper IDs + match-rate report (id-tier, name-fallback-tier, unmatched, K/D-ST out-of-pool).
- CLI: `python3 -m backend.espn_service <league_id> [season]` (env `ESPN_S2`/`SWID` for private) for the Phase-1 live smoke.

Fixtures (`backend/tests/fixtures/`): `dp_playerids_snapshot_2026-07-11.csv` (trimmed real crosswalk, 3,564 rows) and `espn_league_snapshot_2026-07-11.json` (shape-accurate v3 payload, real ESPN player IDs; live public test leagues are purged — §1). Tests: `test_espn_service.py`, 15 tests, no network; fixture-roster crosswalk = **24/24 skill players (100%), K/D-ST correctly out-of-pool**; real-pool measurement in §3 = **99.2%**. Full suite: **417 passed**.

---

## 6. Phases, sizes, go/no-go

| Phase | Scope | Size | Gate |
|---|---|---|---|
| **0 — Spike** | This module + fixtures + measurements | S — **done** | — |
| **1 — Read-only import** (flag `espn.link`) | `platform` column on `leagues`; `espn_credentials` table (Fernet); routes `POST /api/espn/link`, `GET /api/espn/leagues`, `POST /api/espn/import`; nightly crosswalk fetch; mobile `EspnConnectScreen` (WebView + native cookie read) + manual-paste fallback + public-league-by-ID path; platform badge in league picker; live-public-league smoke via the CLI before merge. Docs: data-dictionary, api-reference, architecture, config-reference updates land **here**, with the wiring. | **M** (backend S–M, mobile M) | GO now, behind flag |
| **2 — Roster-dependent features** | Consensus-basis Trade Finder + Tiers/Ranks/Calculator on ESPN leagues; re-sync on league open + cron; 401→"reconnect ESPN" UX; players-only copy where picks are hidden | **M** | After Phase 1 dogfood on the owner's own ESPN league |
| **3 — Mutual features** | Divergence cards/matching when ≥2 linked FTF users share an ESPN league | **S–M** (mostly already platform-agnostic) | **Hold** until real demand (≥2 users asking) |
| **✗ — Send in ESPN** | Write path | — | **Never on this plan** (§2) |

**Recommendation: GO for Phases 1–2, flagged.** The three questions that could have killed this all came back favorable: (1) crosswalk risk is retired — 99.2% measured on the pool that matters, via a data source we already ship on; (2) the API works today with clean semantics (verified live) and a mature reference implementation to crib from; (3) auth UX has a shipped in-house precedent (Sleeper capture) and the same encrypted-at-rest plumbing. The honest costs — unsanctioned API with ~annual breakage, undocumented ~1-year cookie expiry, no picks, no counterparty features, moderate 5.2.2 exposure — are all bounded by the feature flag and by ESPN leagues being additive (worst case: the flag goes off and the app is exactly what it is today). Kill criteria: ESPN blocks server-side reads or Apple rejects the capture screen → flip flag off, archive Phase 3.

---

*Sources: [stmorse — Using ESPN's new Fantasy API (v3)](https://stmorse.github.io/journal/espn-fantasy-v3.html) · [cwendt94/espn-api](https://github.com/cwendt94/espn-api) · [espn-api #539](https://github.com/cwendt94/espn-api/issues/539) · [espn-api discussion #150](https://github.com/cwendt94/espn-api/discussions/150) · [ffscrapr: ESPN authentication](https://ffscrapr.ffverse.com/articles/espn_authentication.html) · [ffscrapr: get endpoint](https://ffscrapr.ffverse.com/articles/espn_getendpoint.html) · [mkreiser/ESPN-Fantasy-Football-API](https://github.com/mkreiser/ESPN-Fantasy-Football-API) · [GameDayBot: espn_s2 & SWID](https://www.gamedaybot.com/help/espn_s2-and-swid/) · [zuplo: ESPN hidden API guide](https://zuplo.com/learning-center/espn-hidden-api-guide) · [dynastyprocess/data](https://github.com/dynastyprocess/data) · live endpoint probes + crosswalk measurement run 2026-07-11 (this repo, §1/§3).*
