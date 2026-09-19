# Multi-Platform League Linking — MFL / Fleaflicker / Yahoo / FFPC (2026-07-17)

*Decision doc for adding league-linking beyond Sleeper + ESPN. Research only — no app code changed. Follows the format and quality bar of [espn-league-linking-plan-2026-07-11.md](espn-league-linking-plan-2026-07-11.md): facts with citations, measured crosswalk coverage, live endpoint probes, phased conditional-GO. The integration pattern being extended is `backend/espn_service.py` (fetch → parse → crosswalk to Sleeper `player_id`s → `league_members` with synthetic counterparty ids → `leagues.platform` column), which shipped Phase 1 on 2026-07-12.*

**Recommendation up front (full rationale §7):**

1. **MFL — GO next.** Official, documented, sanctioned API; public-league reads need **zero auth** (verified live); crosswalk is effectively perfect (DP `db_playerids.csv` is *keyed* on `mfl_id`); heaviest dynasty skew of the four; and — unlike ESPN — MFL exposes **future draft picks** (`futureDraftPicks`, verified live), making it the first linked platform where pick-inclusive trades can work.
2. **Fleaflicker — GO, fast-follow (cheapest of the four).** Documented public JSON API, zero auth for reads (verified live), league discovery by user email, rosters carry sportradar ids 348/348 in the live probe → 96.4% value-pool crosswalk via `sportradar_id`. Real-but-small dynasty niche; platform-stagnation risk.
3. **Yahoo — DEFER behind a demand gate.** Official OAuth2 API = lowest App Store risk but the highest infra bill (operator app registration, redirect URI, 1-hour access tokens + refresh-token store), the weakest crosswalk of the viable three (70.1% value-pool `yahoo_id`, rookie-shaped holes), and the lowest dynasty share. Build when ≥2 real users ask — same gate the ESPN plan used for mutual features.
4. **FFPC — NO-GO for now.** The "FFPC = MFL-hosted, so MFL support covers it free" hypothesis is **false today**: FFPC runs its own proprietary ASP.NET platform (myffpc.com) with an **undocumented** internal API (`api.myffpc.com` serves a bare ASP.NET template page — probed 2026-07-17); no developer docs, no community reference client, no FFPC id column in DynastyProcess. Supporting it means ESPN-class reverse engineering *without* ESPN's decade of community tooling. Revisit only if FFPC publishes an API or paying-user demand appears.

---

## 1. Player-ID crosswalk — measured, not guessed (shared across platforms)

**Source: DynastyProcess [`db_playerids.csv`](https://github.com/dynastyprocess/data)** — the same file the ESPN integration already fetches at boot with a 24h TTL (`espn_service.get_crosswalk()`). Live copy pulled 2026-07-17: 12,467 data rows; columns include `mfl_id`, `sleeper_id`, `espn_id`, `yahoo_id`, `fleaflicker_id`, `sportradar_id`, `fantasypros_id`, `merge_name`, `position`. **Note:** the file is *keyed on `mfl_id`* (first column, always present) — MFL is DynastyProcess's native id space.

**Checked-in snapshot gap:** `backend/tests/fixtures/dp_playerids_snapshot_2026-07-11.csv` was trimmed to `name, merge_name, position, team, sleeper_id, espn_id` only. Any new platform build must **re-cut the snapshot** with the extra id columns (`mfl_id`, `sportradar_id`, `yahoo_id`) — one-time fixture refresh, not a data problem.

**Measured coverage (2026-07-17).** Method: live `values-players.csv` (643 rows) filtered to skill-position players with `value_1qb > 0` → **639-player value-relevant pool** (the ESPN plan's "Pool B" analog — every player that can realistically appear in a trade), joined to `db_playerids` via `fp_id → fantasypros_id` with `merge_name+position` fallback (622 joined; the 17 unjoined are deep 2026 rookies/UDFAs — same residue class the ESPN spike found).

| ID column | Value pool (639) | All rows with `sleeper_id` (6,352) | Verdict |
|---|---|---|---|
| `mfl_id` | **97.3%** | **100.0%** | Solved — DP's primary key |
| `espn_id` (shipped baseline) | 97.2% | 97.6% | (matches the 2026-07-11 spike) |
| `sportradar_id` (= Fleaflicker join key, see §3) | **96.4%** | **99.7%** | Solved — every sportradar hit also has a `sleeper_id` |
| `yahoo_id` | **70.1%** | 83.8% | Weak — holes are rookie-shaped; name+pos fallback becomes load-bearing |
| `fleaflicker_id` | 0.6% | 8.2% | Dead column — **do not use**; Fleaflicker maps via `sportradar_id` instead |
| *(FFPC)* | *no column exists* | — | No public crosswalk at all |

The `name+position` fallback tier (already implemented in `espn_service._parse_crosswalk_rows` / `map_rosters`) recovers a further slice on every platform; for Yahoo it would be doing ~30% of the work on the value pool, which is outside the ESPN plan's "fallback only" comfort zone — flagged in §4.

---

## 2. MyFantasyLeague (MFL)

### API surface (facts as of 2026-07-17)

| Fact | Detail | Source |
|---|---|---|
| Official API | Yes — long-standing, documented, **sanctioned** developer program ("export"/"import" commands, `protocol://host/{year}/export?TYPE=…&L=…&JSON=1`) | [MFL API info](https://api.myfantasyleague.com/2026/api_info), accessed 2026-07-17 |
| Read endpoints we need | `league` (settings/franchises), `rosters`, `players` (global id→name/pos db), `myleagues` (user's league list), `futureDraftPicks`, `assets`, `leagueSearch`, `tradeBait` (`INCLUDE_DRAFT_PICKS=1`) | [API request reference](https://api.myfantasyleague.com/2026/api_info?STATE=details) |
| Auth model | Public leagues: **no auth** for `league`/`rosters`/`futureDraftPicks` (**verified live 2026-07-17**, league 10005). Private leagues: user cookie from the login API ("Authorization is handled via cookies. Your request must pass in the cookie of the user") or the documented **`APIKEY` parameter** (export-only alternate). `myleagues` requires the user's cookie. | [API info](https://api.myfantasyleague.com/2026/api_info); our probes |
| Per-league hosts | League-scoped requests must hit the league's assigned host (`www48.myfantasyleague.com` etc.), not the `api.` host — `api.…/export?TYPE=league&L=10005` returned empty; `www48.…` returned full JSON (**verified live**). `leagueSearch`/`myleagues` return each league's `homeURL`; resolve host from there. | our probes 2026-07-17; [ffscrapr MFL endpoint vignette](https://ffscrapr.ffverse.com/articles/mfl_getendpoint.html) |
| Rate limits | Real and documented-in-prose since 2020: per-IP limits for unregistered clients; **registered clients get ≈2.5× higher limits** (registration = client form + phone validation + fixed User-Agent header on every request). Official guidance: "Wait one second between making requests." | [API info](https://api.myfantasyleague.com/2026/api_info) |
| ToS / restrictions | Harvesting user data and league manipulation forbidden; raw NFL player stats can't be re-shared (licensing). Otherwise MFL *encourages* third-party developers — the opposite of ESPN's posture. | [API info](https://api.myfantasyleague.com/2026/api_info) |

**Live probes (2026-07-17):** `leagueSearch?SEARCH=dynasty` → hundreds of live 2026 dynasty leagues, no auth. `league`/`rosters`/`futureDraftPicks` for public league 10005 on `www48` → full JSON, no auth; rosters are franchise → MFL player-id arrays; `futureDraftPicks` returns per-franchise `{year, round, originalPickFor}` through 2029.

### Crosswalk
`mfl_id`: 97.3% value pool, 100% of all sleeper-mapped rows (§1). MFL's `players` export also serves the full id→name/pos table for the fallback tier. **Solved — best of any platform including ESPN.**

### Dynasty relevance
MFL is the perennial #2 dynasty platform behind Sleeper and the consensus "power user / maximum customization" choice: FantasyPros' 2026 dynasty-platform review covers exactly three platforms — League Tycoon, Sleeper, MFL ("nearly every dynasty format imaginable") — and DLF's annual dynasty platform guides likewise center Sleeper/MFL. MFL also hosts large paid contest ecosystems (e.g. the "Masters"/"Apex" dynasty league families visible in our probe). High-stakes + old-guard dynasty = users with many leagues and real trade volume. ([FantasyPros 2026](https://www.fantasypros.com/2026/05/best-dynasty-fantasy-football-platforms/); [DLF dynasty platform guide](https://dynastyleaguefootball.com/dynasty-draft-guide-2026-dynasty-platforms/); [Draft Sharks review](https://www.draftsharks.com/kb/best-fantasy-football-websites))

### Auth UX / App Store risk — **low**
Public-league-by-URL linking works with zero credentials (paste league URL → we parse host + league id — richer than ESPN's public path because most contest/dynasty MFL leagues are publicly viewable). For private leagues + `myleagues` discovery: WebView cookie capture of the MFL session cookie, identical in shape to the shipped Sleeper/planned ESPN capture (never handle the password itself), or the documented per-user `APIKEY`. Because the API is official and third-party clients are explicitly sanctioned (a whole ecosystem exists), Guideline 5.2.2 exposure is **low** — materially better than ESPN.

### Effort vs ESPN precedent
- **Phase 1 (read-only import): M** — same shape as ESPN Phase 1 (platform enum value, routes, import sheet) plus two MFL-specific costs: per-league host resolution and client registration/User-Agent plumbing; minus ESPN's cookie-verbatim fragility for the public path.
- **Phase 1b (picks): M** — new work no platform has needed yet: map `futureDraftPicks` into `draft_picks` so Pick Anchor pricing and pick-inclusive suggestions work on MFL leagues. This is MFL's killer feature; scope it as its own flag.
- **Phase 2 (roster features): S–M** — same as ESPN Phase 2 (consensus-basis engine already platform-agnostic).
- **Phase 3 (mutual): S** — plumbing exists; demand-gated as ever.

---

## 3. Fleaflicker

### API surface

| Fact | Detail | Source |
|---|---|---|
| Official API | Yes — documented public JSON API (`/api/Fetch*` GET endpoints, `sport=NFL` param): `FetchUserLeagues`, `FetchLeagueStandings`, `FetchLeagueRosters`, `FetchLeagueDraftBoard`, **future draft picks**, `FetchTrades`, `FetchLeagueTransactions` | [Fleaflicker API docs](https://www.fleaflicker.com/api-docs/index.html), accessed 2026-07-17 |
| Auth model | **None for reads** — no API key, no OAuth, no cookies (**verified live 2026-07-17**: `FetchLeagueRosters?sport=NFL&league_id=312861` returns full rosters, no auth). League discovery: `FetchUserLeagues` by user email/id — the user types their own Fleaflicker email, zero credentials held. | docs + our probe; [ffscrapr Fleaflicker vignette](https://ffscrapr.ffverse.com/articles/fleaflicker_basics.html) |
| Player ids | `proPlayer.id` (Fleaflicker-internal) + `externalIds` when `external_id_type=SPORTRADAR` is requested — **348/348 roster players carried a sportradar id in our live probe** | our probe 2026-07-17 |
| Rate limits / ToS | None published; contact `info@fleaflicker.com`. Community tools (ffscrapr) poll politely and survive. | [API docs](https://www.fleaflicker.com/api-docs/index.html) |
| Platform health | Staleness risk: Fleaflicker is widely described as "the forgotten platform," in maintenance mode relative to Sleeper; API is stable but evolution is unlikely. | [Bleacher Nation dynasty sites 2025](https://www.bleachernation.com/fantasy-football/2025/07/30/dynasty-sites/) |

### Crosswalk
Ignore DP's near-empty `fleaflicker_id` column; join on **`sportradar_id`** (ffscrapr's own approach): 96.4% value pool, 99.7% of sleeper rows, and every sportradar hit carries a `sleeper_id` (§1). Name+pos fallback on `nameFull`+`position` covers the rest. **Solved.**

### Dynasty relevance
A real dynasty niche — deep rosters, taxi squads, keeper support, a dedicated [dynasty leagues surface](https://www.fleaflicker.com/nfl/dynasty-fantasy) — but small and shrinking share versus Sleeper; DLF's guides list it, FantasyPros' 2026 review no longer does. Think "long-tail of old dynasty leagues that never migrated."

### Auth UX / App Store risk — **lowest of all four**
No credential ever touches our servers: email → league list → pick league → import. Official public API ⇒ 5.2.2 exposure effectively nil.

### Effort vs ESPN precedent
- **Phase 1: S** — no credentials table, no cookie plumbing, no host routing; a `fleaflicker_service.py` clone of the espn_service shape with an email-based discovery step. Smallest Phase 1 of any platform, ESPN included.
- **Picks: S–M** — the API exposes future draft picks (endpoint in official docs); same `draft_picks` mapping work as MFL once that pipeline exists.
- **Phase 2: S–M; Phase 3: S** — as ESPN.

---

## 4. Yahoo

### API surface

| Fact | Detail | Source |
|---|---|---|
| Official API | Yes — the only one of the four with a formal developer program: Fantasy Sports API over OAuth2, resources `game → league → team → player` with `settings`/`standings`/`roster` subresources; XML default, `?format=json` available. Player ids are `player_key = {game_id}.p.{player_id}`; DP's `yahoo_id` is the season-stable `player_id`. | [Yahoo Fantasy Sports API guide](https://developer.yahoo.com/fantasysports/guide/), accessed 2026-07-17 |
| Auth model | 3-legged OAuth2 (authorization-code flow) for anything user-specific — league discovery is `users;use_login=1/games;game_keys=nfl/leagues`. Requires an **operator-registered developer app** (App ID, Client ID/Secret, exact redirect URI + scope). **Access tokens live 1 hour** (`expires_in: 3600`); long-lived refresh tokens must be stored and rotated server-side. | [Yahoo OAuth2 auth-code flow](https://developer.yahoo.com/oauth2/guide/flows_authcode/); [OAuth2 guide](https://developer.yahoo.com/oauth2/guide/) |
| Rate limits | Unpublished; Yahoo throttles/blocks per registered app id on "excessive" use — community clients report opaque temporary blocks. | [yfpy issue #51](https://github.com/uberfastman/yfpy/issues/51); [yahoo-fantasy-sports-api issue #81](https://github.com/whatadewitt/yahoo-fantasy-sports-api/issues/81) |
| ToS | Sanctioned use behind OAuth consent — the cleanest legal posture of the four. | developer portal terms |

### Crosswalk
`yahoo_id`: **70.1%** on the value pool (83.8% overall) — the misses skew exactly where trades happen in dynasty (recent rookie classes). Name+pos fallback would have to carry ~30% of the value pool as a *primary* mechanism, which the ESPN plan explicitly ruled out as a design center ("do not build name-matching as the primary mechanism"). Workable, but the weakest crosswalk of the viable three; would want a measured re-check at build time (DP backfills yahoo ids over time).

### Dynasty relevance — **lowest**
Yahoo is a redraft/keeper giant but a dynasty non-entity: absent from FantasyPros' and DLF's dynasty platform guides; no future-draft-pick trading model comparable to Sleeper/MFL/Fleaflicker (keeper mechanics only — verify at build time). Linking Yahoo mostly imports redraft leagues, which our dynasty-centric value model (DP dynasty values, pick ladder) prices wrongly out of the box — a *product* mismatch, not just an integration cost. ([FantasyPros 2026](https://www.fantasypros.com/2026/05/best-dynasty-fantasy-football-platforms/); [PFN platform comparison](https://www.profootballnetwork.com/which-dynasty-fantasy-platform-is-right-for-you/))

### Auth UX / App Store risk — **lowest risk, highest ceremony**
OAuth in the system browser/ASWebAuthenticationSession is the Apple-blessed pattern; 5.2.2 exposure ≈ nil. But the bill: operator app registration (with use-case description), redirect-URI plumbing across web+mobile, a server-side token store with hourly refresh (new infra class — nothing in the app refreshes third-party tokens today), and XML/JSON response quirks.

### Effort vs ESPN precedent
- **Phase 1: L** — OAuth infra dominates (registration, callback routes, token store + refresh worker, revocation handling) before any fantasy logic runs.
- **Phase 2: M** (redraft-value mismatch adds product work, e.g. redraft-mode valuations — out of scope for linking per se); **Phase 3: S–M.**

---

## 5. FFPC — verifying the "MFL-hosted" hypothesis

**Finding: the hypothesis is false today.** Facts:

| Fact | Detail | Source |
|---|---|---|
| Current platform | FFPC runs on its **own proprietary ASP.NET platform** at myffpc.com (`*.aspx` league pages: `LeagueHome.aspx`, `MyAccount.aspx`, …) with its own iOS app | [myffpc.com](https://myffpc.com/cms/public/); [FFPC on the App Store](https://apps.apple.com/us/app/ffpc/id1399810018) |
| API | `api.myffpc.com` exists but serves a **default ASP.NET template landing page** — no documentation, no endpoint reference, no developer program (**probed 2026-07-17**). The iOS app implies an internal API, but nobody has published a reverse-engineering of it: no ffscrapr module, no Dynasty Daddy support, no community client found. | our probe; [ffscrapr platform list](https://ffscrapr.ffverse.com/); search 2026-07-17 |
| Crosswalk | **No FFPC id column** in DP `db_playerids.csv` (checked live file 2026-07-17). Third parties that surface FFPC data (e.g. [FFPC Data Warehouse](https://www.fantasymojo.com/)) scrape ADP pages, not league APIs. | §1 column check |
| History | Community memory says FFPC leagues ran *on* MFL in earlier years; we could not find a citable record of the migration (searches 2026-07-17 came up empty). Whatever the history, it is operationally irrelevant: **current FFPC league data lives only on myffpc.com.** Staleness note: this paragraph is community-sourced and low-confidence by construction. | searches 2026-07-17 |
| Dynasty relevance | High per-capita: FFPC pioneered high-stakes dynasty (dynasty format since 2010, Empire leagues, $250–$2,500 entries) — small league count, wallet-heavy users. | [FFPC history](https://myffpc.com/cms/public/about/ffpc-history); [FFPC dynasty](https://myffpc.com/cms/public/play/dynasty-leagues); [DLF intro to FFPC dynasty](https://dynastyleaguefootball.com/2024/08/06/an-intro-to-ffpc-dynasty-leagues/) |

**Consequence:** FFPC support would mean reverse-engineering an undocumented private API (or scraping authenticated `.aspx` pages) with **zero community reference implementation** — strictly worse than the ESPN posture (ESPN at least has a decade of maintained community clients absorbing endpoint churn) — plus building a bespoke player-id crosswalk from scratch, for the smallest league count of the four. **Effort: L–XL, fragility: highest, App Store risk: ESPN-class or worse. NO-GO** until FFPC publishes an API or concrete paying-user demand appears; if their historical MFL ties ever resurface as an MFL-hosted product line, MFL support would cover it automatically.

---

## 6. Comparison table

| | **MFL** | **Fleaflicker** | **Yahoo** | **FFPC** |
|---|---|---|---|---|
| Official API | ✅ documented + sanctioned | ✅ documented public JSON | ✅ official OAuth2 program | ❌ none public (`api.myffpc.com` = bare stub) |
| Auth for reads | None (public lg, **verified live**); cookie or `APIKEY` for private / `myleagues` | **None** (verified live); email-based league discovery | 3-legged OAuth2, 1h tokens + refresh infra | Unknown / account scraping |
| Crosswalk id in DP | `mfl_id` — **97.3% / 100%** (DP's key) | via `sportradar_id` — **96.4% / 99.7%** (live payload carries it 348/348) | `yahoo_id` — **70.1% / 83.8%**, rookie holes | none |
| Future draft picks | ✅ `futureDraftPicks` (**verified live**, 2027–29) | ✅ endpoint in official docs | ❌ (keeper only — verify) | n/a |
| Dynasty share | High — consensus #2 dynasty platform | Niche, long-tail, shrinking | Minimal (redraft giant) | Small count, high-stakes |
| Effort P1 (vs ESPN P1 = M) | **M** (+M for picks) | **S** | **L** (OAuth infra) | **L–XL** |
| App Store 5.2.2 risk | Low (sanctioned) | Lowest (no creds at all) | Lowest (OAuth) | High (ESPN-class+) |
| Gotchas | Per-league `wwwNN` hosts; client registration + phone validation; 1 rps guidance; no raw-stats re-sharing | Platform stagnation; `fleaflicker_id` column is a decoy — use sportradar; no published rate limits | Operator app registration; hourly token refresh; XML-first API; redraft value mismatch | Everything |

---

## 7. Ranked recommendation

**1. MFL — build next (Phase 1 GO, flag `mfl.link`).** It wins on every axis that killed or capped ESPN: official sanctioned API instead of unsanctioned scraping (low App Store risk, no annual-breakage treadmill), a *perfect* crosswalk through the very file we already fetch daily, the strongest dynasty user base of the four, and — the strategic unlock — **future draft picks over the API**, which ESPN structurally cannot give us. An MFL link is the first place "pick-inclusive trade suggestions on a linked league" becomes real, exercising the Pick Anchor/tier-ladder work on external leagues. Costs are known and bounded: host routing, client registration, polite pacing.

**2. Fleaflicker — fast-follow in the same release train (Phase 1 GO, flag `fleaflicker.link`).** At S-size Phase 1 with zero credential handling it's nearly free once the multi-platform seams from MFL exist (generalized `Crosswalk` with per-platform id maps, re-cut snapshot fixture, platform enum). Small audience, but the cost/risk is so low the option is worth holding; its stagnation risk argues against building it *first*, not against building it.

**3. Yahoo — defer behind a demand gate (≥2 real user requests), then Phase 1 = L.** Nothing is broken about Yahoo — it's simply the worst dynasty-return-per-effort of the viable three: the only one needing new token-refresh infrastructure and operator app registration, the weakest value-pool crosswalk (70.1%), and a mostly-redraft catch that our dynasty value model would misprice without additional product work. If/when demand appears, re-measure `yahoo_id` coverage first (DP backfills over time).

**4. FFPC — NO-GO (revisit on API publication or paid demand).** The collapse-into-MFL shortcut does not exist today (§5); standing it up honestly is the most effort, most fragility, and most review risk for the fewest leagues. The FFPC audience overlap we care about (high-stakes dynasty players) is largely reachable anyway: those users typically also hold Sleeper/MFL leagues.

**Sequencing note:** do MFL Phase 1 → Fleaflicker Phase 1 → MFL picks (Phase 1b) → Phase 2 (roster features) for both together, since Phase 2 is platform-agnostic engine surface. Mutual/Phase-3 features stay demand-gated everywhere, as in the ESPN plan.

---

## 8. Phase-1 sketch — MFL (mirrors `espn_service.py` / ESPN Phase 1)

**Spike first (S, gate for GO):** `backend/mfl_service.py`, isolated, CLI-driven, fixture-tested — same contract as the ESPN spike:
- `fetch_league(host, league_id, year, cookie|apikey=None, _opener=…)` → `export?TYPE=league|rosters|futureDraftPicks&L=…&JSON=1` against the **league's host** (resolve via `leagueSearch`/pasted URL; note `homeURL` values can come back scheme-mangled — normalize). Fixed registered User-Agent; ≥1s spacing between the 3 calls.
- `parse_league()` → franchises (id, name, owner name if exposed), rosters as MFL player-id arrays, `futureDraftPicks` → `{franchise, year, round, original_owner}`.
- Crosswalk: generalize `espn_service.Crosswalk` → per-platform id maps built from the *same* cached DP fetch (`get_crosswalk()` grows `by_mfl_id`, `by_sportradar_id`, …); re-cut the snapshot fixture with `mfl_id`+`sportradar_id`+`yahoo_id` columns. Fallback tier unchanged (`normalise_name`+position). Target: reproduce ≥97% on a real dynasty league via the CLI.
- Live smoke: `python3 -m backend.mfl_service <league_url_or_id> [year]` against a public dynasty league (e.g. the Masters/Apex families surfaced by `leagueSearch` — league 10005 verified readable today).

**Phase 1 wiring (M, behind `mfl.link`, default OFF):**
- Schema (additive): reuse `leagues.platform` (`'mfl'`) + `espn_season`-style columns generalized (`platform_season`, `platform_host`) — or MFL-specific columns if renaming is churn; `mfl_credentials` only when the private-league path lands (public-URL linking needs **no credentials table at all** — ship that first, exactly like the ESPN plan's Option-3 free tier, except on MFL it covers *most* contest dynasty leagues).
- Routes: `POST /api/mfl/link` (preview → choose-franchise → import), `GET /api/mfl/leagues`, `POST /api/mfl/import` — same idempotent re-link + unmatched-report contract as `/api/espn/*`; synthetic counterparties `mfl:{league_id}.f{franchise_id}` (owner emails/names are restricted data — never harvest, per MFL ToS).
- Mobile: `MflLinkSheet` clone of `EspnLinkSheet` (paste league URL → franchise pick → import summary with match rate); platform badge "MFL".
- Registration (operator): MFL client registration + phone validation; the registered User-Agent goes in config, not code.
- Docs on landing, per CLAUDE.md: api-reference, data-dictionary, config-reference, architecture, cross-client-invariants (platform enum), glossary.

**Phase 1b (M, flag `mfl.picks`):** map `futureDraftPicks` into `draft_picks` so the trade engine's pick assets light up on MFL leagues — the first non-Sleeper platform where that's possible; validate Pick Anchor pricing against league pick ownership before enabling suggestions that include picks.

---

## 8b. Phase-1 implementation record (SHIPPED 2026-07-18)

**MFL + Fleaflicker Phase 1 are built and green** (flags `mfl.link` / `fleaflicker.link`, both default OFF). ESPN suite unchanged.

- **Crosswalk generalization:** `espn_service.Crosswalk` now carries per-platform external-id → sleeper maps (`by_mfl_sleeper`, `by_sportradar_id`, `by_yahoo_id`) built from the one cached DP fetch, plus the shared position-strict name fallback (#127) and a generic `map_generic_rosters(teams, id_map, xwalk)` used by both new services. ESPN's `by_espn_id`/`map_rosters` and the KTC-blend `by_mfl_id`/`by_ktc_id` maps are untouched. The snapshot fixture `dp_playerids_snapshot_2026-07-11.csv` was **re-cut additively** (existing columns byte-preserved; appended `mfl_id` 3564/3564, `sportradar_id` 3199, `yahoo_id` 2559).
- **MFL** (`backend/mfl_service.py`): host resolved from a pasted URL (un-mangles MFL's scheme-less `https//www48…` homeURLs) or via `api.myfantasyleague.com/{year}/home/{id}` 302 `Location`. Fetches `league`/`rosters`/`players`/`futureDraftPicks` (≥1s spacing live; `players` degrades gracefully). **futureDraftPicks stored raw** in `leagues.platform_future_picks` — not engine-wired (the +M follow-up). **Live smoke:** league 10005 → 186/186 by id (**100%**), 90 picks stored.
- **Fleaflicker** (`backend/fleaflicker_service.py`): zero-auth; crosswalk via `sportradar_id` from `externalIds`; email discovery via `FetchUserLeagues`. **Live smoke:** league 312861 → 347/348 by id (**99.7%**; lone miss Rondale Moore, a DP-snapshot residue).
- **Storage seam:** generic `upsert_platform_league` / `get_platform_league` / `load_platform_leagues_for_user` + reused `replace_espn_league_members`; new `leagues` columns `platform_season/host/auth/my_team/future_picks`. Synthetic ids `mfl:{L}.f{franchise}` / `flea:{L}.t{team}`.
- **Routes** (append-only in `server.py`): `POST/GET /api/mfl/{link,leagues,import}`, `POST/GET /api/fleaflicker/{link,leagues,discover,import}`.
- **Mobile:** `api/platformLink.ts` + `components/PlatformLinkSheet.tsx` (platform-aware, zero-auth flow); LeaguePicker merges + badges (`ESPN`/`MFL`/`FLEA`) + per-platform link buttons; Settings adds a zero-auth link row; `api/auth.ts` routes MFL/Fleaflicker session-init through their snapshots. `tsc --noEmit` clean.
- **Tests:** `test_crosswalk_generalized.py`, `test_mfl_service.py`, `test_mfl_link_route.py`, `test_fleaflicker_service.py`, `test_fleaflicker_link_route.py` (~50 tests) + recorded fixtures `mfl_league_snapshot_2026-07-17.json`, `fleaflicker_league_snapshot_2026-07-17.json`. Full backend suite green (ESPN suite unmodified).

**Deferred (unchanged from the plan):** Yahoo (demand-gated), FFPC (NO-GO), MFL/Fleaflicker private-league auth, pick-inclusive engine wiring (Phase 1b), Phase-2 roster features, Phase-3 mutual.

## 9. Open questions for the operator

1. **MFL client registration** (form + phone validation) — operator step before any real traffic; also decide the registered User-Agent string.
2. **MFL private-league auth choice:** WebView cookie capture (Sleeper-pattern) vs asking users to paste their per-league `APIKEY` from MFL's site. Cookie capture is smoother; APIKEY avoids holding session cookies. Spike should verify cookie name/lifetime — undocumented.
3. **Yahoo demand gate:** agree the trigger (≥2 organic user requests?) and, if ever triggered, the operator owns Yahoo developer-app registration (App ID/secret, redirect URI, use-case blurb).
4. **Fleaflicker rate limits:** none published — email `info@fleaflicker.com` for blessing/limits before launch, or accept polite-pacing risk as ffscrapr does?
5. **Pick valuation on linked leagues (Phase 1b):** MFL exposes picks through 2029; our pick ladder prices 8 tiers — confirm how deep future years should price before suggestions include them.
6. **Snapshot fixture re-cut:** approve regenerating `dp_playerids_snapshot_*.csv` with the extra id columns (test-fixture-only change, but it touches the shipped ESPN fallback path).

---

*Sources: [MFL Developers API info + request reference](https://api.myfantasyleague.com/2026/api_info) · [ffscrapr: MFL get-endpoint](https://ffscrapr.ffverse.com/articles/mfl_getendpoint.html) · [Fleaflicker API docs](https://www.fleaflicker.com/api-docs/index.html) · [ffscrapr: Fleaflicker basics](https://ffscrapr.ffverse.com/articles/fleaflicker_basics.html) · [Yahoo Fantasy Sports API guide](https://developer.yahoo.com/fantasysports/guide/) · [Yahoo OAuth2 authorization-code flow](https://developer.yahoo.com/oauth2/guide/flows_authcode/) · [yfpy #51 (rate limits)](https://github.com/uberfastman/yfpy/issues/51) · [myffpc.com](https://myffpc.com/cms/public/) + [FFPC history](https://myffpc.com/cms/public/about/ffpc-history) + api.myffpc.com probe · [FantasyPros: Best Dynasty Platforms 2026](https://www.fantasypros.com/2026/05/best-dynasty-fantasy-football-platforms/) · [Bleacher Nation: Best Dynasty Sites 2025](https://www.bleachernation.com/fantasy-football/2025/07/30/dynasty-sites/) · [DLF Dynasty Platforms guide](https://dynastyleaguefootball.com/dynasty-draft-guide-2026-dynasty-platforms/) · [dynastyprocess/data](https://github.com/dynastyprocess/data) · live probes + crosswalk measurements run 2026-07-17 (this doc, §1/§2/§3/§5).*
