# Platform parity: capability matrix and parity procedure

> What each league platform (Sleeper, ESPN, MFL, Fleaflicker) can do in FTF today, and how
> an area PM fills scope-block §7 "Platform scope" for a change. Owner: `platforms-pm`.
> Cells verified against `origin/main` @ `678834ab` on 2026-10-15.

## Contents

- [A. When to use it](#a-when-to-use-it)
- [B. Capability matrix](#b-capability-matrix)
- [C. Per-feature parity procedure](#c-per-feature-parity-procedure)
- [D. Known parity defects](#d-known-parity-defects)
- [E. Keeping it current](#e-keeping-it-current)

## A. When to use it

- Every scope block §7 (`docs/templates/feature-scope.md`). The §7 table has one row per
  platform: reads and writes used, then the behavior (parity, honest
  `platform_unsupported`, fallback copy, or n/a).
- Any PRD whose feature reads league data (rosters, picks, drafts, transactions,
  settings, stats) or writes to a platform.
- Reviewing another area's diff for platform behavior.

`platforms-pm` owns this file and reviews §7 rows. Area PMs send §7 to `platforms-pm`
through `head-product`.

## B. Capability matrix

How to read it:

- Paths are under `backend/` unless they start with `mobile/`, `docs/` or `config/`.
  `server.py:N` is `backend/server.py` line N at the sha above. Lines drift; re-grep
  the symbol before you cite it.
- "unverified" means no code proves it. Code-walk it before a spec relies on it.
- The last column names the kill-switch flags (`config/features.json`, documented in
  `docs/config-reference.md`). Flag values change; read the file, not this table.
- Fleaflicker is dark: `fleaflicker.link` is false, so every Fleaflicker route 404s.
- ToS, ban and rate-limit posture is not here. See `/pm-partnerships` → platform risk
  register (being written on branch `skill/pm-partnerships`).

### B1. Identity, entry and auth

| Capability | Sleeper | ESPN | MFL | Fleaflicker (dark) | Kill switch |
|---|---|---|---|---|---|
| Sign-in / entry | Username claim, no password (D-001); `POST /api/extension/auth` `server.py:25792` | Sessionless team claim, `POST /api/entry/platform` `server.py:25874` (D-164) | Same route; id `entry:mfl:<league>.f<fid>` (D-164) | None. Entry accepts only `espn`/`mfl` (`server.py:25937`) | `landing.platform_options` + the platform's link flag |
| Credential for reads | None; public REST (`docs/integrations/sleeper.md` §1.1) | Public league: none. Private: `espn_s2` + SWID (`server.py:28369` docstring) | Public: none. Private: MFL sign-in cookie (`server.py:31679`) | None; zero auth (`fleaflicker_service.py:15`) | `espn.link`, `mfl.link`, `mfl.auth_link`, `fleaflicker.link` |
| Credential capture | JWT from Sleeper's login page in a WebView (`mobile/src/screens/SleeperConnectScreen.tsx`); proven by a live probe in `POST /api/sleeper/link` (`server.py:19245`) | WebView, read from the native cookie store (D-021; `mobile/src/utils/espnCookies.ts`); paste is the fallback | Username + password for one login call; password never stored (`database.py:2428` comment) | n/a | `trade.send_in_sleeper`, `espn.webview_capture` (client-only), `mfl.auth_link` |
| Server-side store | `sleeper_credentials`, Fernet (`database.py:2374`) | `espn_credentials`, Fernet + `verified_at` (`database.py:2413`) | `mfl_credentials`, Fernet (`database.py:2439`) | Nothing held | — |
| On-device store | JWT in `mobile/src/transport/credentialVault.ts` (envelope is `platform: 'sleeper'` only, `:27-31`) | None in the vault | None in the vault | None | — |
| Disconnect | `DELETE /api/sleeper/link` (`server.py:19269`); Settings row (`mobile/src/screens/settings/sections/PlatformDisconnectSection.tsx:45`) | `DELETE /api/espn/link`; row (`PlatformDisconnectSection.tsx:46`) | `DELETE /api/mfl/auth-link`; row (`PlatformDisconnectSection.tsx:48`) | Nothing to disconnect | `account.sleeper_disconnect`, `espn.link`, `mfl.auth_link` |

### B2. League discovery and link

| Capability | Sleeper | ESPN | MFL | Fleaflicker (dark) | Kill switch |
|---|---|---|---|---|---|
| Find my leagues | `GET /api/sleeper/leagues/<user_id>` (`server.py:21807`). Never for an `acct_` id (G-032); the guard is client-side only (`mobile/src/screens/LeaguePickerScreen.tsx:320`) | Fan-profile list, `GET /api/espn/my-leagues` (`server.py:28813`), or type a league id | `myleagues` via `POST /api/mfl/auth-link` (`server.py:31679`), or league id / URL | By account email, `POST /api/fleaflicker/discover` (`server.py:33370`) | `espn.league_picker`, `mfl.auth_link`, `fleaflicker.link` |
| Link sheet (mobile) | `mobile/src/components/LinkSleeperSheet.tsx`: identity link → `POST /api/account/link-sleeper` (`server.py:27755`) | `mobile/src/components/EspnLinkSheet.tsx` | `mobile/src/components/PlatformLinkSheet.tsx`; `MflSignInSheet.tsx` signs in mid-send | `PlatformLinkSheet.tsx` (`:63`) | `auth.accounts` + link flags |
| Import route | None; membership is read live (B3) | `POST /api/espn/link` (`server.py:28369`) | `POST /api/mfl/link` (`server.py:31335`), `POST /api/mfl/auth-import` (`:31814`) | `POST /api/fleaflicker/link` (`server.py:33264`) | link flags |

### B3. League data reads

| Capability | Sleeper | ESPN | MFL | Fleaflicker (dark) | Kill switch |
|---|---|---|---|---|---|
| Rosters: source | Live at each session init (`session_input.py:53-79`; D-178) | DB snapshot written at import (`session_input.py:42-51`) | Same as ESPN | Same as ESPN | — |
| Rosters: refresh | Every session init | Manual "Re-sync ESPN rosters" → `POST /api/espn/import` (`mobile/src/screens/LeagueScreen.tsx:888`; `server.py:28874`) | `POST /api/mfl/import` exists (`server.py:31484`) but has no mobile caller (note 1) | Same as MFL (`server.py:33389`) | — |
| Co-owned rosters | `owner_id` or `co_owners`; a co-owner aliases the primary owner (D-051; `sleeper_roster.py:12`) | Team binds to `primaryOwner`, else first `owners` entry (`espn_service.py:484`); co-owner sign-in unverified | unverified | unverified | — |
| Scoring format | Auto-detected from league meta (`server.py:750`, `:22759`) | Not detected; reads `1qb_ppr` until set by hand (`database.py:8555`; `POST /api/league/scoring` `server.py:21239`) | Detected at import (#201; `mfl_service.py:776`; `server.py:31303`) | Same as ESPN | — |
| Lineup slots | Live `roster_positions` (`server.py:29130`) | Standard template, plus `SUPER_FLEX` when `sf_tep` (`server.py:29154`; #311) | Same as ESPN | Same as ESPN | — |
| Settings read | League meta: `roster_positions`, `scoring_settings`, `total_rosters` (`server.py:730`, `:22752`) | `mTeam`, `mRoster`, `mSettings` views only (`docs/integrations/espn.md` §1.1) | `TYPE=league` + `TYPE=rules` (`docs/integrations/mfl.md` §1) | Rosters + standings only (`FetchLeagueRosters`, `FetchLeagueStandings` in `fleaflicker_service.py`) | — |

### B4. Draft picks

| Capability | Sleeper | ESPN | MFL | Fleaflicker (dark) | Kill switch |
|---|---|---|---|---|---|
| Owned picks | Grid + live `traded_picks` (`server.py:14267`, `:17127`); three-class horizon (`draft_status.py:92`; `database.py:11383`) | No platform source. User-asserted rows (ADR-010) via `/api/league/pick-assignments` (`server.py:17674`) | `futureDraftPicks` snapshot (`server.py:14149`; refresh `:19142`) | None; no pick read in `fleaflicker_service.py` | `picks.owned_sync`, `picks.league_horizon`, `picks.assign` |
| Picks priced in trades | Platform rows | Only while `picks.assign_tradeable` is on (`config/features.json` `_comment_pick_assign_tradeable`) | Platform rows | n/a | `picks.assign_tradeable` |
| Drafted season's picks | Dropped once the rookie draft is complete (#228, D-189; `server.py:22883-22884`) | unverified | Dropped on a `drafted` verdict (#207; `server.py:14161-14170`) | n/a | `picks.owned_sync` |
| Rookie-draft status | Platform verdict (`draft_status.py:464`) | Roster heuristic only (`draft_status.py:468`) | Platform verdict from `draftResults` (`draft_status.py:466`) | Roster heuristic only (`draft_status.py:468`) | — |

### B5. Draft Room (platform × draft slice, for `draft-pm`)

| Capability | Sleeper | ESPN | MFL | Fleaflicker (dark) | Kill switch |
|---|---|---|---|---|---|
| Board source | Live `/drafts`, `/draft/{id}`, `/draft/{id}/picks`, `traded_picks` (`server.py:18052`; `docs/integrations/sleeper.md` §1.1) | Assignment grid, zero platform egress (`server.py:18180`; ADR-010) | `TYPE=draftResults` (`server.py:18146`; `_mfl_board_binding` `:17218`) | `platform_unsupported` notice (`server.py:18206`) | `draft.room`; ESPN `picks.assign`; MFL `draft.mfl` |
| Flag off or unbound | `draft.room` off → 404 (`server.py:18102`) | `picks.assign` off → `platform_unsupported` | `draft.mfl` off, or no stored host → `platform_unsupported` (`server.py:17218` docstring) | Always `platform_unsupported` | — |
| Player names | Native Sleeper ids | Crosswalked roster ids from the DB | Four ordered tiers, never a bare id (D-022; #289) | n/a | `draft.mfl` |
| Record off-platform picks | n/a; the platform records them | `POST /api/league/recorded-picks` (`server.py:17935`) | n/a | n/a | `draft.manual_picks` |
| Reconnect state | n/a; public reads | n/a | `mfl_reconnect` notice when a private cookie expires (`draft_board_service.py:122`) | n/a | — |
| Deep link out | `sleeper.com/draft/nfl/<draft_id>` (`draft_board_service.py:1062`) | None (`draft_board_service.py:1458`) | MFL `static_url` (`draft_board_service.py:1259`) | None | — |
| Mock draft order | The real board's order (`server.py:18560`) | The assigned grid (`server.py:18530-18535`) | Seeded shuffle + owned-pick overlay, labelled (`server.py:18864`; #328) | Seeded shuffle, labelled `randomized` (`server.py:18553-18555`) | `draft.mock` |

### B6. Transactions, offers and stats

| Capability | Sleeper | ESPN | MFL | Fleaflicker (dark) | Kill switch |
|---|---|---|---|---|---|
| Completed trades | Captured from `transactions/{week}` (`sleeper_trades_service.py:170`; called at `server.py:22918`, note 2) | None; reads three views only (`docs/integrations/espn.md` §1.1) | None; no transactions export (`docs/integrations/mfl.md` §1) | None | `market.trade_capture` |
| Pending platform offers | No read. `reject_trade` exists, unwired (`sleeper_write.py:414`) | No read. `cancel_trade` exists, unwired (`espn_write.py:440`) | `GET /api/mfl/pending-trades` (`server.py:32834`) | None | `trade.send_in_mfl` |
| Weekly player stats (Usage Trends) | Sleeper's stats feed (D-203); league join from live rosters (`server.py:30801-30803`) | Same stats; join from the DB snapshot (`server.py:30794`) | Same as ESPN | Same as ESPN | `usage_trends.enabled` |
| Matchups / outlook | Yes (`outlook/league_state.py:147`) | Stub → 501 `not_supported` (`outlook/league_state.py:314`; `server.py:30335`) | Same (`outlook/league_state.py:306`) | Same (`outlook/league_state.py:310`) | `outlook.odds` |
| Roster-history snapshot | At session init (`server.py:22964-22968`) | At import / refresh (`server.py:24071`) | Same as ESPN | Same as ESPN | `market.roster_history` |

### B7. Writes

| Capability | Sleeper | ESPN | MFL | Fleaflicker (dark) | Kill switch |
|---|---|---|---|---|---|
| Propose a trade | `POST /api/trades/propose` (`server.py:19419`) | `POST /api/trades/propose-espn` (`server.py:32962`) | `POST /api/trades/propose-mfl` (`server.py:32449`) | None | `trade.send_in_sleeper`, `espn.send`, `trade.send_in_mfl` |
| Picks in a sent trade | Encoded server-side; any miss refuses the whole send (D-176, D-189; `server.py:32233`) | Hard block, 422 `espn_pick_unsupported` (D-039, note 3; `server.py:33109`) | Encoded `FP_…` from the snapshot (`server.py:32169`); miss → 422 `mfl_asset_unmapped` (`:32616`) | n/a | — |
| Players in a sent trade | Native ids | Reverse crosswalk; miss → 422 `espn_asset_unmapped` (`server.py:33122`) | Reverse crosswalk (`server.py:32083`); miss → `mfl_asset_unmapped` | n/a | — |
| Respond to an offer | None | None | `POST /api/trades/respond-mfl` (`server.py:32712`) | None | `trade.send_in_mfl` |
| Send button | `SendInSleeperButton` routes by `resolveSendPlatform` (`mobile/src/components/SendInSleeperButton.tsx:131`) | `SendInEspnButton` (`SendInSleeperButton.tsx:468`) | `SendInMflButton` (`SendInSleeperButton.tsx:448`) | Copy fallback, `NO_SEND_REASON` (`mobile/src/utils/tradeText.ts:50-54`) | send flags |
| Add a free agent | Deep link to Sleeper (`mobile/src/components/ClaimSheet.tsx:144`) | "Can't add in ESPN leagues yet" (`ClaimSheet.tsx:67`) | Same, MFL copy | Same, Fleaflicker copy | — |

### B8. Player ids and platform-limited features

| Capability | Sleeper | ESPN | MFL | Fleaflicker (dark) | Kill switch |
|---|---|---|---|---|---|
| Player-id crosswalk | Native ids | DP `db_playerids.csv` `espn_id`, then name+position (`espn_service.py:651-657`) | DP `mfl_id`, its primary key (`espn_service.py:653`; `mfl_service.py:16`) | `sportradar_id`; DP `fleaflicker_id` is a decoy (`fleaflicker_service.py:19-21`) | — |
| Trade block (`on_block`) | Synced each session init (`server.py:22843`) | n/a; guarded out (`trade_block_service.py:176-178`) | n/a; same guard | n/a; same guard | `sleeper.trade_block`, `trade.block_boost` |
| Team-overhaul sends | Send (`overhaul_service.py:54`) | Send, players only; pick offers refused at prepare (`overhaul_service.py:709`) | Send, picks allowed (`overhaul_service.py:55`) | Copy handoff (`overhaul_service.py:59-60`) | `overhaul.enabled` + send flags |
| Team review "PPG this year" | Yes (`server.py:29686-29700`) | `scoring_unavailable_reason: platform_unsupported` (`server.py:29685`) | Same | Same | `trades.team_review` |
| Season projections (win-now) | Yes | `platform_unsupported` (`win_now_service.py:116`) | Same | Same | `outlook.season_projections`, `trades.win_now` |

### Notes

1. `importPlatformLeague` (`mobile/src/api/platformLink.ts:138`) has no caller. An MFL or
   Fleaflicker roster refreshes only on re-link, or on MFL sign-in import.
2. The trade-capture call is gated on `str(league_id).isdigit()` only, with no
   `is_linked_platform_league` check. See D, last rows.
3. `living-memory/DECISIONS.md` has two D-039 entries. The ESPN one is "ESPN Trade-Write Is
   No Longer Categorically Prohibited" (line 638). `config/features.json`'s
   `_comment_espn_send` still calls it D-026, its pre-renumber draft ID.
4. No route removes a linked league on any platform (searched `@app.route` with DELETE).
5. Stale docs disagree with this matrix; code wins. `docs/integrations/espn.md` §1 says
   ESPN is read-only. `mobile/src/api/CLAUDE.md`, `mobile/src/components/CLAUDE.md` and
   a comment at `SendInSleeperButton.tsx:463` say `espn.send` is off. D-188's status
   line says `overhaul.enabled` is false. The integration docs' line numbers are stale.

## C. Per-feature parity procedure

1. **List every read and write** the feature makes, by data type: identity, league list,
   rosters, settings / scoring / lineup, picks, draft object, transactions, offers,
   stats, player ids, writes.
2. **Look each one up** in section B. Copy the cell into your notes. If the cell says
   "unverified", the code-walk in step 3 must settle it.
3. **Code-walk each platform branch,** file:line, and show how the code decides the
   platform. Use the platform field, never the id's shape:
   - Backend: `is_linked_platform_league` (`database.py:9140`; NULL `platform` means
     Sleeper); `get_league_draft_context(league_id)["platform"]` (draft board, outlook,
     team review); `get_platform_league(league_id, platform)` (`database.py:13863`); the
     session league's `.platform` (`overhaul_api.py:118`, `server.py:18511`).
   - Mobile: `resolveSendPlatform` (`mobile/src/utils/tradeText.ts:28`; fails open to
     Sleeper on a cold cache); `isEspnLeague` (`mobile/src/api/espn.ts:205`);
     `isMflLeague` / `isFleaflickerLeague` (`mobile/src/api/platformLink.ts:263-264`).
   - Known traps; read the entries in `living-memory/GOTCHAS.md`:
     - **G-014:** `isdigit()` is not a platform test. An MFL league's picks were wiped
       on every app open.
     - **G-030:** MFL and Fleaflicker ids are numeric too. A Send in Sleeper button went
       live on MFL leagues.
     - **G-032:** an account-only session (`acct_<id>`, `no_league` sentinel) must never
       fetch Sleeper leagues. Treat the D-164 entry ids (`entry:espn:…`,
       `entry:mfl:…`) the same way: they are not Sleeper ids.
4. **Choose per platform:** parity, honest `platform_unsupported`, fallback copy, or n/a.
   Reuse an existing shape; do not invent one.

   | Shape | Where | Use it for |
   |---|---|---|
   | 200, `state: "unavailable"` + `notice.code`: `platform_unsupported`, `picks_not_assigned`, `mfl_reconnect` (open set; client falls back on unknown codes) | `draft_board_service.py:119-128`, `:1462`; `mobile/src/screens/DraftRoomScreen.tsx:1108-1133` | A read surface that renders a state |
   | `meta.scoring_unavailable_reason: "platform_unsupported" \| "preseason"` | `server.py:29681-29712`; `mobile/src/api/teamReview.ts:31` | One enrichment inside a payload that otherwise works |
   | 200, `{status: "unavailable", reason: "platform_unsupported", message}` | `win_now_service.py:116`; `win_now_api.py:48-49` | A whole feature that is Sleeper-only |
   | 422, `{error, picks[], message, detail}` (`sleeper_pick_unmapped` / `_untradable` / `_not_owned`) | `server.py:19573-19590` | The model for a new write refusal |
   | 422, `espn_pick_unsupported` + `picks[]`; `mfl_asset_unmapped` + `unmapped[]` | `server.py:33109-33114`, `:32616-32620` | Asset classes a platform cannot carry. These bodies lack `detail`; add it if you reuse them |
   | Overhaul blockers `pick_unsupported_on_platform`, `reconnect_required`; `handoff_mode` → `copy` | `overhaul_service.py:50-60`, `:709-737` | Multi-offer flows |
   | Client copy `NO_SEND_REASON`, `NO_ADD_REASON` | `mobile/src/utils/tradeText.ts:50-54`; `mobile/src/components/ClaimSheet.tsx:67` | Client-only fallback copy |
   | Do not copy: 501 `{error: "not_supported", message}` | `server.py:30335-30336` | A 5xx with no `detail`, for a known product limit |

   **Any new error body carries `detail`.** Fielded builds render `detail` in their
   catch-all; without it a refusal reads "Please try again" (`server.py:19573-19574`;
   `.claude/skills/feedback/lessons.md` 2026-09-02 [plan] entry). Check new shapes against
   the oldest build still installed.
5. **Fill §7,** one row per platform. Fleaflicker is n/a unless the change lights it.
   Example, Usage Trends as shipped: Sleeper reads the stats feed and live rosters,
   parity. ESPN and MFL read the same stats with snapshot rosters, parity. Fleaflicker
   n/a (dark).
6. **Evidence (D-056: no Maestro, no simulator, no captures).** Name each of these:
   - **Backend tests per platform.** Patterns: `test_sleeper_write_route.py`,
     `test_sleeper_pick_tradability.py`; `test_espn_link_route.py`,
     `test_espn_propose_route.py`, `test_espn_identity_binding.py`;
     `test_mfl_link_route.py`, `test_mfl_propose_route.py`,
     `test_mfl_trade_lifecycle.py`; `test_fleaflicker_link_route.py`. Cross-platform:
     `test_draft_board.py::test_unsupported_platform_is_unavailable_not_an_error`,
     `test_owned_picks.py::test_numeric_mfl_id_detected_as_platform_league`,
     `test_outlook_odds.py::test_endpoint_uses_requested_league_platform_not_session_league`,
     `test_overhaul_api.py::test_copy_handoff_platform_gets_no_send`. Each new platform
     branch gets a test that fails if the branch is removed.
   - **Mobile guards:** `mobile/tests/check-send-button-platform.js` (send routing),
     `check-trade-text.js` (`NO_SEND_REASON`), `check-landing-platform-options.js`,
     `check-espn-*.js`. CI runs every `check-*.js` (`.github/workflows/ci.yml:47`).
   - **A code-walk per platform branch,** file:line, from the request to the platform
     decision to the response.
   - **TestFlight checklist steps per platform,** each naming its league:
     Sleeper "Fantasy Football Version 3" (`1312140920132497408`), MFL "Dependables"
     (`62846`). No ESPN test league is recorded in the repo; name one and record it.
     Any step that makes a real Sleeper, ESPN or MFL write needs the operator's
     approval when it runs. Never script one.
7. **Review route:** §7 goes to `platforms-pm` through `head-product`. A new platform
   read or write also goes to `platforms-eng` through `head-product` → `head-eng`.
   New events go to `analytics-lead`.

## D. Known parity defects

Worked examples. Each shows what broke and what the parity answer was.

| Case | Doc | What broke | Parity answer |
|---|---|---|---|
| #311 | `docs/feedback/items/311-lineup-values-nonsleeper/` | ESPN/MFL leagues had no lineup template, so starter impact was omitted | Standard template, plus `SUPER_FLEX` for `sf_tep` (`_league_lineup_slots`) |
| #207 | `docs/feedback/items/207-rookie-draft-detection/mfl-parity-status.md` | Sleeper hid a drafted season's picks (#228); MFL kept them | MFL twin at the same layer: `draftResults` verdict + verdict-gated exclusion |
| #289 | `docs/feedback/items/289-mfl-draft-room-ids/` | MFL Draft Room showed raw ids | Four-tier name resolution, never a bare id (D-022) |
| #210, #258 | `docs/feedback/items/210-mfl-name-entities/`, `258-mfl-name-entities/` | MFL team names showed HTML entities, then markup (#282) | Clean MFL strings at parse (`docs/integrations/mfl.md` §3) |
| #321 | `docs/feedback/items/321-espn-token-bleed/` | The shared native cookie jar handed one person's ESPN session to another FTF user on the same device | Clear the jar on connect, verify the pair, refuse the wrong account |
| #201 | `docs/feedback/items/201-mfl-format-detection/` | No MFL code wrote `default_scoring`; an SF TEP league read as 1QB | Detect at import. ESPN and Fleaflicker still have no detection (B3) |
| Overhaul sends | `docs/plans/team-overhaul/owner-decisions.md`; D-188 | v1 sent on Sleeper only | Owner revised D1: Sleeper, MFL and ESPN (players only) send (#290); Fleaflicker copies |
| Picks horizon (#355) | `docs/feedback/items/355-phantom-pick-years/` | Sleeper's fixed grid showed phantom 2029 picks | Sleeper-only fix (`picks.league_horizon`). MFL lists real picks; ESPN has none. "Already right" is a valid answer |
| G-014 / #200 | `living-memory/GOTCHAS.md` G-014 | `isdigit()` sent an MFL league into the Sleeper pick sync, wiping its picks | `is_linked_platform_league` at routes and daemon |
| Open: trade capture | `server.py:22918` | Gated on `isdigit()` only. By code-walk, each session init on a numeric ESPN/MFL/Fleaflicker league makes up to 18 Sleeper `transactions` reads. Not runtime-confirmed | Untriaged (found 2026-10-15). Add the `_platform_linked` guard; `platforms-pm` raises it to `platforms-eng` via `head-product` → `head-eng` |
| Open: Sleeper propose guard | `server.py:19512`; G-030 "Related" | The route checks `isdigit()`, not platform. The client routes correctly, so this is defense in depth | Untriaged; same route as the row above |

## E. Keeping it current

- Update the matrix in the same PR as any change that alters a platform capability: a
  new read or write, a new honest-unsupported shape, a flag added or retired, a
  platform lit or darkened. Re-verify the cells you touch and update the sha line.
- `platforms-pm` re-checks the whole file each July, before the season, alongside the
  platform risk register.
- When a cell stops being "unverified", replace it with the citation that proves it.
