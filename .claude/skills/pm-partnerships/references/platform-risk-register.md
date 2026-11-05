# Platform risk register

> **Purpose:** one place that says, for every league platform FTF touches, what the
> platform's terms say today, what FTF actually reads and writes, who agreed to what, how
> to switch it off, and what the first sign of trouble looks like. Owned by `platforms-pm`
> (`/pm-partnerships`). Updated on every ToS watch run (SKILL.md § ToS watch) and before
> any write feature ships (SKILL.md § Write-feature gate).
>
> **Why it exists:** Sleeper revised its Terms on 2026-07-24 and FTF found out three
> weeks later, by accident, inside an unrelated feasibility memo
> (`docs/plans/sleeper-pending-trades-feasibility-2026-08-12.md` § ADDENDUM 2). The
> revision described a feature that was already live. A dated register with a watch
> cadence is the fix.
>
> **Honesty rule:** `platforms-pm` is not a lawyer and nothing here is legal advice.
> Anything with real legal exposure is marked **review with a professional**. Quotes from
> terms pages are short and partial; read the live page before relying on a row.

## Contents

- [How to maintain this file](#how-to-maintain-this-file)
- [Escalation E2: Sleeper Terms revision of 2026-10-06](#escalation-e2-sleeper-terms-revision-of-2026-10-06)
- [Sleeper](#sleeper)
- [ESPN](#espn)
- [MyFantasyLeague (MFL)](#myfantasyleague-mfl)
- [Fleaflicker (dark)](#fleaflicker-dark)
- [Not integrated: Yahoo, FFPC](#not-integrated-yahoo-ffpc)
- [Non-platform data sources (not yet registered)](#non-platform-data-sources-not-yet-registered)
- [Change log](#change-log)

## How to maintain this file

- One block per platform, same fields in the same order. Dates are ISO. "Last checked"
  names the run (`platforms-pm` worker + date), never a person.
- A cell you could not verify says **not verified YYYY-MM-DD** and why (fetch failed,
  page truncated, Wayback unreachable). Never carry a value forward silently.
- Every repo claim cites a path that exists on `origin/main`; every web claim cites the
  URL and the date it was read.
- Escalations get an id (E1, E2, ...) and sit at the top until the operator closes them.
  Closing one records the operator's words, the date, and where the answer is filed.
- Add a change-log line for every edit.

---

## Escalation E2: Sleeper Terms revision of 2026-10-06

**Opened:** 2026-10-15. **Status:** open, **operator decision**. `platforms-pm` takes no
outbound action: no message to Sleeper, no form, no request for a copy of anything.

**What changed.** Sleeper's Terms of Use
(https://support.sleeper.com/en/articles/5486620-terms-of-use) show **Last Updated:
October 6, 2026**. Verified on the live page 2026-10-15 by this run. The page is long and
was read in two passes; §11 was read in full on the second pass.

What the live §11 says (summary, read 2026-10-15):
- **§11.1** bars, without Sleeper's express written consent: crawling or scraping the
  Services; accessing, querying or extracting data by any automated means (plus
  human access at a non-human scale or pattern); giving third parties login credentials,
  access tokens or session identifiers; connecting an account to a third-party product
  that retrieves data for that party's commercial purposes; and using the Services for
  "any commercial or business purpose".
- **§11.2** lets Sleeper suspend accounts, revoke sessions or credentials, and take
  technical measures to block a third party, whether or not it is a user.
- **§11.3** says no third party is authorized to access, scrape, crawl, query or
  retrieve Sleeper data "whether directly, through automated means," or through a
  user's account or credentials, except under a separate written agreement executed by
  Sleeper or other express approval. A user's handing over credentials "does not
  constitute authorization from Sleeper".
- **§2.9** names the sanctioned route: an Approved Integration Partner with a separate
  written agreement.

Sleeper's developer docs (https://docs.sleeper.com/, read 2026-10-15) say the free API
is for non-commercial purposes and send commercial users to Sleeper to discuss a
licence. No date appears on that page.

**What could not be verified.** Whether §11 changed between the 2026-07-24 and
2026-10-06 revisions. The Wayback Machine was unreachable from this run's fetch tool on
2026-10-15, and no copy of the 2026-07-24 text is filed in the repo. One hint: in-tree
notes dated 2026-08-12 already refer to §11.1's crawl and scrape bullets and §11.3's
"whether directly" wording (`docs/plans/device-side-platform-auth-prd-2026-08-12.md`
reconciliation log, ~L240). So the broad automated-access language may predate October.
Treat that as unconfirmed.

**Why it matters.** §11.3 as written today is not limited to credentialed access. It
reaches automated unauthenticated reads too, and those are most of FTF's Sleeper traffic:
the daily bulk player dump, per-session background reads, cron sweeps, and the organic
trade corpus backfill (see the Sleeper block below).

**What FTF has on file.**
- The operator stated on 2026-08-12 that FTF has explicit agreement from Sleeper to use
  the GraphQL surface (`docs/plans/sleeper-pending-trades-feasibility-2026-08-12.md`,
  § RESOLVED 2026-08-12). No copy, scope, date or counterparty is filed anywhere in the
  repo (checked 2026-10-15).
- The device-side-auth PRD made filing that agreement's scope a **P0 precondition**,
  with a clause-to-requirement map (`docs/plans/device-side-platform-auth-prd-2026-08-12.md`
  ~L117).
- **OQ-1** in that PRD (~L166) asked whether the agreement covers automated
  *unauthenticated* access. The PRD's own operator amendment **A1** (~L180, same day)
  withdrew it ("public-read coverage is not a concern"). OQ-1 was never logged in
  `living-memory/OPEN_QUESTIONS.md`, and the scope was never filed. The 2026-10-06 text
  is a new fact that may reopen the question. Reopening it is the operator's call.
- Sleeper separately warned the operator that its automated systems may block FTF's
  calls (same PRD ~L13, ~L23).

**Blast radius of a block.** Every live Sleeper feature: sign-in by username,
session-init reads, trade capture, trade-block import, owned-pick sync, Usage Trends,
outlook, Send in Sleeper and team-overhaul sends. Beyond Sleeper leagues, the player
database itself comes from Sleeper's bulk dump, and ESPN, MFL and Fleaflicker rosters
are crosswalked *to Sleeper player ids*. A Sleeper block degrades every platform once
the cached player data ages out.

**Decisions needed (operator only).**
1. Does the agreement cover automated unauthenticated reads, the commercial use that
   paid tiers would bring, and the 2026-10-06 terms? File its form, date, counterparty
   and scope beside the feasibility memo, or say where it lives.
2. Reopen OQ-1 and log it in `OPEN_QUESTIONS.md` (through `head-product` and the
   scribe), or close it again with today's text in view.
3. Until 1 is answered, are new Sleeper automated reads or writes paused, or do they
   proceed on the operator's existing call?

**Review with a professional:** yes. This is a contract-scope and terms question with
real exposure.

---

## Sleeper

| Field | Value |
|---|---|
| **Terms URLs** | User terms: https://support.sleeper.com/en/articles/5486620-terms-of-use. Developer: https://docs.sleeper.com/ (usage guidance inside the docs; no separate API terms page). |
| **Last checked** | 2026-10-15, `platforms-pm` worker (skill refresh). Both fetches worked; the terms page needed two passes. |
| **Terms "last updated" + change** | **October 6, 2026** (seen 2026-10-15). Earlier revisions on record: 2026-07-24 (found 2026-08-12, three weeks late, by accident) and a 2022-05-26 Wayback baseline. The diff from 2026-07-24 to 2026-10-06 is **not verified 2026-10-15** (Wayback unreachable, no in-tree copy). Current §11 summary: see E2. |
| **Rate limits** | Published (docs, 2026-10-15): stay under 1,000 calls a minute or risk an IP block. Call the bulk players endpoint at most once a day. Observed: Cloudflare 1010 bans on non-browser User-Agents, so three server modules impersonate desktop Chrome (`sleeper_write.py`, `trade_block_service.py`, `sleeper_trades_service.py`; PRD §2.1). Sleeper also warned that its automated systems may block FTF (PRD ~L13). FTF volume: 7 calls per session init in season and 6 off-season (D-178); bulk dump on a 20 h TTL from a daily cron; cron sweeps limited to leagues active in the last 30 days (D-178). |
| **Auth model** | Sign-in is a Sleeper username claim with no password (D-001, still live). v1 REST needs no auth. GraphQL (`sleeper.com/graphql`) is undocumented. Writes use the user's own 365-day, full-account JWT, captured in a WebView on `sleeper.com/login` (`SleeperConnectScreen`), proven against a no-op probe, stored Fernet-encrypted in `sleeper_credentials` with a Keychain copy for replay (`docs/integrations/sleeper.md` §2.2). |
| **What FTF reads** | 13 v1 REST endpoints (user, leagues, league, rosters, users, traded_picks, drafts, draft, picks, matchups, transactions, `/players/nfl` bulk, undocumented `/players/nfl/adp`); GraphQL `league_players` (public); the weekly projections and stats feeds (`sleeper.md` §1, § Weekly feeds). Automated reads with no user action: the daily bulk dump cron, session-init background syncs, cron trade and draft sweeps, and the 2026-08-16 organic trade corpus backfill (`scripts/backfill_sleeper_trades.py`; `docs/business/analytics/2026-08-16-organic-trade-corpus.md`). The extension's content script reads page text on sleeper.com to overlay tiers. It is unpacked-only and has never been published (`extension/CLAUDE.md`). |
| **What FTF writes + posture** | GraphQL `propose_trade` through `POST /api/trades/propose` (Send in Sleeper) and team-overhaul sends through the same core (`_sleeper_propose_core`; overhaul ON since 2026-09-07). Overhaul sends are all-platform: #290 (`8cacc1f2`) revised D-188, whose status text still says Sleeper-only and is stale; `backend/overhaul_service.py` ~L50-60 maps each platform to its send flag. Pick sends are encoded server-side (D-176) and refused outside the tradable window (D-189). `reject_trade` is built but not routed. Posture: the operator-stated agreement of 2026-08-12 (see E2), plus D-019 (prepare the trade, never fabricate the execute path). Every write runs from Render today. The device-side transport (PRD 2026-08-12) is not past its S3 gate (`living-memory/NEXT.md`). **Free-agent add/drop and waiver claims: planned, not built.** Approved by the operator on 2026-10-20 (#351 decision D1, relayed by the coordinator to `head-product`): "Yes. With User authorization to do so. (A checkbox for the first attempt every 7 days)". Each user ticks a consent checkbox on their first add/drop in any rolling 7-day window. The server enforces it and records it in an append-only table (spec: `docs/plans/sleeper-fa-deeplink/consent.md` on draft PR #351). The mutation shapes are not yet captured. That work is the `platforms-eng` spike in `docs/plans/sleeper-fa-write/`, and any live write probe needs the operator's approval at the time it runs. |
| **Kill switches** | `trade.send_in_sleeper` (writes), `overhaul.enabled` (overhaul send routes), `sleeper.trade_block`, `market.trade_capture`, `picks.owned_sync`, `usage_trends.enabled`, `account.sleeper_disconnect`, `sleeper.fa_write` (planned, default OFF; stops FTF-performed add/drops; users fall back to the #351 hand-off); env `FTF_PLAYERS_REFRESH=0` stops bulk refreshes. Flags hot-reload deploy-free via `POST /api/feature-flags/reload`. No flag switches off the core v1 reads (sign-in, rosters), because those reads are the app. |
| **Agreement status** | Operator-stated explicit agreement, 2026-08-12. **Not filed**: no copy, scope, date or counterparty in the repo (2026-10-15). See E2. |
| **Earliest warning signs** | `api_call` rows for service `sleeper` (flag `obs.api_events`, ask `analytics-lead`) showing 403, 1010, 429 or a jump in error rate; a rise in `sleeper_rejected` or `token_rejected` on link or send; a message from Sleeper to the operator; the terms page date moving; news of a competitor using the same pattern (e.g. Dynasty Daddy) being blocked. |
| **Pre-planned response** | Writes: flip `trade.send_in_sleeper` and `overhaul.enabled` off. Writes are server-executed, so the stop is immediate. The deep-link hand-off (`sleeper.com/leagues/{id}/trade?add_receiver_id=...`, `TradesScreen.tsx`) remains. **Correction (2026-10-20):** that link is broken on iPhone. sleeper.com's mobile redirect drops the league, the page and the parameters, and lands on the Sleeper app's home screen (verified 2026-10-15; `docs/plans/sleeper-fa-deeplink/feasibility.md`, PR #351). The working fallback is the #351 `sleeper://` hand-off plus clipboard steps, once built. `sleeper.fa_write` off stops add/drops. Reads: reads fail soft to cached snapshots (`sleeper.md` §4), and the cached player DB keeps every platform running for a while. Never evade a deliberate block: rotating egress (PRD §9, "held in reserve") is an operator decision, not a mitigation. Escalate to `head-product` the same day. |
| **Open questions** | **Open defect, avoidable automated Sleeper volume (relevant to E2):** session-init trade capture (`backend/server.py:22918` on `origin/main`, `678834ab`) is gated on `str(league_id).isdigit()` alone, without `is_linked_platform_league`. By code-walk, each session init on a numeric ESPN, MFL or Fleaflicker league may make up to 18 Sleeper `transactions` reads, because the first-time backfill never finds captured rows. Not runtime-confirmed. Found by the platform-parity worker; routed to `platforms-eng`. E2 (agreement scope, OQ-1, commercial use). Whether the 2026-10-06 revision changed §11. Chrome-UA impersonation against an honest User-Agent (PRD §8, a gated probe). Commercial use once `monetize.*` flags light (all dark 2026-10-15): the developer docs' non-commercial line and §11.1 both bite. **Review with a professional.** |

## ESPN

| Field | Value |
|---|---|
| **Terms URLs** | User terms: Disney Terms of Use, https://disneytermsofuse.com/english/ (ESPN's footer "Terms of Use" link resolves there; checked 2026-10-15 from https://www.espn.com/fantasy/football/). Developer/API terms: **none exist**. ESPN retired its public developer API in 2014, and FTF uses the unofficial v3 API that ESPN's own clients use (`docs/plans/espn-league-linking-plan-2026-07-11.md` §1). |
| **Last checked** | 2026-10-15, `platforms-pm` worker. Fetch worked. |
| **Terms "last updated" + change** | **May 24, 2024** (seen 2026-10-15). No prior reading is recorded in the repo (the device-side PRD ~L117 noted none existed), so this run is the baseline. Summary: §2(B)(x) bars access "using a robot, spider, script, or other automated means", plus data mining and scraping; §2(B)(viii) bars commercial or business use and enabling third parties to do it; §6 limits use to personal, noncommercial use; §1(F) says don't share account information; §1(H) lets Disney terminate or suspend access. |
| **Rate limits** | None published. Observed in the community: non-browser User-Agents get intermittent 403s; the read host moves about once a season; old leagues are purged (`espn-league-linking-plan` §1). |
| **Auth model** | Public leagues need no auth. Private leagues need `espn_s2` + `SWID` cookies, captured from the native cookie store in an in-app WebView (D-021), or pasted on web (D-179). Stored Fernet-encrypted in `espn_credentials`, verified by a fan-API probe before `verified_at` is stamped. Platform entry can mint an `entry:espn:` session with no Sleeper or Apple account (D-164, `landing.platform_options`). |
| **What FTF reads** | `lm-api-reads.fantasy.espn.com` league read (`mTeam`/`mRoster`/`mSettings` only); `fan.api.espn.com` fan profile for the league picker. Reads are user-triggered (link, import, re-sync, picker), plus standings reads for draft order behind a 15-minute cache (`docs/integrations/espn.md` §1, §5). |
| **What FTF writes + posture** | `TRADE_PROPOSAL` POST to `lm-api-writes` (`backend/espn_write.py`) through `POST /api/trades/propose-espn`, flag `espn.send` ON. Team-overhaul sends go through the same ESPN propose core (`overhaul.enabled` ON; #290). Players only: picks are hard-blocked on send, and overhaul offers carrying a pick are refused at prepare (`overhaul_service.py` ~L709). Posture: **D-039** (the ESPN trade-write entry; note that DECISIONS.md also has a tier-board-share entry numbered D-039) reversed the earlier NO-GO on 2026-08-12. The operator accepted the residual Disney ToS and ban risk. `docs/integrations/espn.md` (2026-08-09) predates the write path and still says ESPN is read-only. |
| **Kill switches** | `espn.send` (writes), `overhaul.enabled` (overhaul send routes, all platforms), `espn.link` (every ESPN route), `espn.webview_capture`, `espn.league_picker`, `landing.platform_options` (entry chips + `POST /api/entry/platform`). Server routes 404 as soon as a flag goes off. `espn.link` is compiled `true` into the mobile `LAUNCHED_FLAG_DEFAULTS`, so the client UI hides only after its next flag revalidate (30-minute throttle). |
| **Agreement status** | None. Unsanctioned use of a Disney property, accepted by the operator (D-039, ESPN entry). |
| **Earliest warning signs** | `api_call` rows for service `espn` showing 403s; a spike in `espn_auth_required`; `TRAN_*` errors on send; a read-host or write-host move; a Disney cease-and-desist or an App Store 5.2.2 complaint; the terms date moving. |
| **Pre-planned response** | `espn.send` off first, because writes carry the higher exposure; that also stops ESPN overhaul sends (`SEND_FLAGS`). `overhaul.enabled` off stops overhaul sends on every platform. Then `espn.link` if reads are being targeted. Fallbacks are copy-trade and the ESPN app hand-off. Never evade a block. Any Disney contact goes straight to the operator. |
| **Open questions** | **Disclosure mismatch:** `mobile/src/components/EspnLinkSheet.tsx` (~L450) still says the import is read-only and that FTF never posts or changes anything in ESPN, while `espn.send` is ON. ~L706 says ESPN trade features "come later". Route to `platforms-eng` through `head-product`. Device-side release-2 gates (an ESPN reachability probe and a terms read) are open; this row is the terms read. **Review with a professional** before monetization. |

## MyFantasyLeague (MFL)

| Field | Value |
|---|---|
| **Terms URLs** | API terms: inside https://api.myfantasyleague.com/2026/api_info (no separate API terms page). Site terms: https://home.myfantasyleague.com/terms.html. The site footer also links an Acceptable Use Policy, which this run did **not** read. |
| **Last checked** | 2026-10-15, `platforms-pm` worker. Both fetches worked. |
| **Terms "last updated" + change** | API page: no terms date (its release notes say last updated 2022-07-25). Site terms: **effective June 1, 2024**. Prior recorded reading: api_info, 2026-07-17 (`docs/plans/multi-platform-linking-plan-2026-07-17.md` §2). Change from that reading: same substance. Details not in the 07-17 record: throttled calls return 429; a failed request should not be retried; terms may change at any time; the service may be discontinued without warning. Site terms grant use for "noncommercial and personal use only" and bar screen scraping and data mining without permission. MFL may terminate with or without cause. |
| **Rate limits** | Published: per-IP limits for unregistered clients; registered clients get about 2.5× more; "Wait one second between making requests". FTF spaces live calls ≥1 s apart (`_REQUEST_SPACING_SECONDS`) and sends `MFL_USER_AGENT`. **Client registration** (a form plus phone validation) was still pending per `docs/integrations/mfl.md` (2026-08-11) and the device-side PRD §10(e). Not confirmed done since. |
| **Auth model** | Public leagues need no auth. Private leagues and `myleagues` go through the login API. The user's MFL password transits `POST /api/mfl/auth-link`; device-side PRD goal G2 is to stop that. The `MFL_USER_ID` cookie is stored Fernet-encrypted in `mfl_credentials`. An `APIKEY` alternative exists for exports only. Entry sessions use `entry:mfl:` (D-164). |
| **What FTF reads** | Exports: `league`, `rosters`, `futureDraftPicks`, `players`, `rules`, `draftResults`, `myleagues`, owner-restricted `pendingTrades`, plus host resolution (`docs/integrations/mfl.md` §1). |
| **What FTF writes + posture** | Imports: `tradeProposal` (`POST /api/trades/propose-mfl`) and `tradeResponse` accept, reject or revoke (`POST /api/trades/respond-mfl`; no mobile surface yet), flag `trade.send_in_mfl` ON. This is MFL's sanctioned import API acting on the user's own franchise with the user's own cookie. MFL forbids changing someone's team without permission, and FTF writes only the signed-in user's proposals. Team-overhaul sends also go through the MFL propose core, picks allowed (`overhaul.enabled` ON; #290 revised D-188, whose status text is stale). |
| **Kill switches** | `trade.send_in_mfl`, `overhaul.enabled` (overhaul send routes, all platforms), `mfl.link`, `mfl.auth_link`, `draft.mfl`, `landing.platform_options`. |
| **Agreement status** | None needed beyond the published API terms. Registration is pending (an operator step). |
| **Earliest warning signs** | 429s (these surface as `kind: network` / 502 `mfl_write_failed`); a rise in `mfl_auth_expired`; changes to the api_info page; `api_call` rows for service `mfl`. |
| **Pre-planned response** | `trade.send_in_mfl` off, which also stops MFL overhaul sends (`SEND_FLAGS`); `overhaul.enabled` off stops overhaul sends on every platform. The operator completes registration; cut call cadence. |
| **Open questions** | Registration. Whether the site terms' noncommercial clause bites once FTF charges, given that the API page invites third-party developers (**review with a professional**). The `pendingTrades` field vocabulary is unverified live. |

## Fleaflicker (dark)

| Field | Value |
|---|---|
| **Terms URLs** | Site terms: https://www.fleaflicker.com/terms. API docs: https://www.fleaflicker.com/api-docs/index.html. |
| **Last checked** | 2026-10-15, `platforms-pm` worker. Terms page read in full. API docs read only partly: the first 100k of ~268k characters. |
| **Terms "last updated" + change** | **No date shown** on either page (the API docs say "Version: 1.0"). The terms say nothing about automated access, API use or commercial use. The part of the API docs that was read has no rate-limit or terms language. No earlier terms reading is on record; this run is the baseline. |
| **Rate limits** | None published. The docs list `info@fleaflicker.com` as the contact. Writing to it is the operator's call, not ours (multi-platform plan §9 Q4). |
| **Auth model** | None for reads. League discovery uses `FetchUserLeagues` with an email the user types. No credentials are held. |
| **What FTF reads** | When lit: rosters, standings and leagues through `/api/Fetch*`, with the crosswalk joined on `sportradar_id` (multi-platform plan §3, §8b). |
| **What FTF writes + posture** | Nothing; no write path is built. Team-overhaul offers on any platform without a send flag get a copy handoff only (`handoff_mode`, `overhaul_service.py`). |
| **Kill switches** | `fleaflicker.link` = **false**. Phase 1 was built 2026-07-18 (multi-platform plan §8b) and has been dark ever since. |
| **Agreement status** | None. |
| **Earliest warning signs** | n/a while dark. If lit: changes to the API docs, `api_call` errors for service `fleaflicker`. |
| **Pre-planned response** | Keep dark. |
| **Open questions** | The go/no-go is the open add-a-platform instance (`references/add-a-platform.md`). |

## Not integrated: Yahoo, FFPC

- **Yahoo:** deferred behind a demand gate (≥2 real user requests). Yahoo has an official
  OAuth2 API, the weakest crosswalk of the viable platforms (70.1% on the value pool), and
  low dynasty share (multi-platform plan §4, §7). Terms not checked this run.
- **FFPC:** NO-GO. There is no public API (`api.myffpc.com` serves a bare template) and no
  crosswalk column. Revisit if FFPC publishes an API or paying users ask (multi-platform
  plan §5, §7). Terms not checked this run.

## Non-platform data sources (not yet registered)

Not league platforms, but they are data-source and ToS risks this role owns. Add rows
on the next watch run: **KeepTradeCut**, an unsanctioned HTML scrape once per boot
(`backend/data_loader.py` ~L151; kill switch `model_config ktc_blend_weight = 0`), and
**DynastyProcess**, a community CSV on GitHub with no SLA
(`docs/integrations/dynastyprocess.md`). Terms not checked 2026-10-15.

## Change log

- 2026-10-20: Sleeper add/drop write recorded as operator-approved and planned (PR #351 D1); kill switch sleeper.fa_write; trade deep-link fallback marked broken on iPhone.
- 2026-10-15: follow-up on PR #345. Team-overhaul sends recorded as all-platform (#290) in the ESPN, MFL and Fleaflicker blocks, with `overhaul.enabled` added to kill switches and responses; D-188 status flagged stale. The session-init trade-capture defect (`server.py:22918`) was added to Sleeper's open questions.
- 2026-10-15: register created by a `platforms-pm` worker (skill refresh). Live terms
  read for Sleeper, ESPN/Disney, MFL (API + site) and Fleaflicker. E2 opened. ESPN
  disclosure mismatch found.
