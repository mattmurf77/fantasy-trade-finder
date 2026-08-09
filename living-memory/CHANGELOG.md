# Changelog — Fantasy Trade Finder

> **Purpose:** cross-session memory. Capture what was built, decisions that affect future work, and known gaps.
>
> Retention: last 10 entries live here; older entries are in [archive/](archive/) — grouped by quarter. Per-entry cap ~1,200 bytes; overflow detail belongs in docs/plans/ or the PR body, linked.
>
> **Read at:** session start.
> **Write at:** session end.
>
> Companion files: [`HANDOFF.md`](HANDOFF.md) for forward-looking; [`../docs/`](../docs/) for per-feature reference updates.

---

## 2026-08-09 (feedback wave 3: validation follow-ups, tier labels app-wide, sheet targeting)

- **#277/#278/#280/#281 (fable deep pass):** tier labels replace per-player numerics on every surface (28 files) — swap sheet, eveners, share image, league-summary drill-in, free agents, draft rows, rank boards; additive `tier` on /api/trade/evaluate eveners, /api/league/power-rankings, /api/league/free-agents (canonical band-walk, never derived from transformed value). Totals/deltas/FAAB stay numeric. Enumeration table: `docs/feedback/items/277-tier-labels-appwide/status.md`. League-summary key deduped (below-graph only, one line lower).
- **#273/#274/#275 (PickAssignment):** future seasons show round-ordinal pick labels with NO order UI (order is one whole-board setting server-side — the slot numbers were fiction); owner sheet sizes to all teams; sheet closes on tap (save in flight, CAS prompt intact).
- **#269/#276:** team targeting + league picker (reused LeagueSwitcherSheet) inside the edit sheet, Team/Player mode tabs removed — flag `trades.sheet_targeting` ON, flag-off byte-identical, downstream generate machinery untouched (only the opponent source changed). Scroll-to-generated-trade + TradeCard spacing tightened (unflagged, spacing-only).
- **Mockup lab (#270/#272/#279):** `mockups/polish-lab-2026-08/trades-home-inline.html` — 4 inline-spectrum variants (minimal pill strip → calculator-style canvas → maximal inline → accordion) + team/positional pick-equivalent frame; rec: minimal now, calculator-style needs a scope decision.
- **#271 answered:** solo-ranked leagues DO apply the user's board (user_gain_epsilon + junk-filler gates); divergence discovery needs a second ranked member. **#282 (MFL color markup, reopens #258) built but held for operator sign-off** — fix strips `<font color>`-style markup in `_clean_text`; branch `worktree-agent-a1dbc63e607fd3721` @ `e1144ca`, unmerged pending approval of prod-name fixtures in the commit.
- Gates: 2059 passed / 1 skipped; tsc clean; per-branch review + sequential merges.

## 2026-08-08 (feedback wave: 6 fixes/features + 2 mockup labs, operator-reviewed batch)

- **#268/#267 (PickAssignment):** saves had NEVER worked — client PUT the bare route while the server registered `/<pick_id>`, 405 on every save, masked by the generic toast; fixed client-side + repro test pinning old-fail/new-pass. Grid numbers now update optimistically on move (react-query onMutate + local progress recompute, rollback on error, CAS path untouched).
- **#265:** League-home "X more needed" used a mock-anchored threshold of 2 borrowed from the contrarian leaderboard; trade engine needs ONE ranked opponent. Extracted `mobile/src/utils/leagueUnlocks.ts` (=1) + node test.
- **#263:** Trade Calculator player rows show pick-tier labels, not raw values. `GET /api/trade/values` gains additive `tier` (canonical `RankingService.tier_for_elo` on raw seed Elo — NOT derivable from the transformed `value`); demo mode maps client-side via `tierForElo`.
- **#260:** League-summary legend explains the ▲/▼N rank-swing chips (#248).
- **#257:** Controls Card consolidated into full-height TradeDnaSheet, variant C, flag `trades.edit_full_sheet` ON (off = byte-identical). Dismiss shows "Preferences changed — refresh" strip; player mode keeps its board; legacy OutlookSheet entry gated off.
- **#172:** trade intent modes — Consolidate / Tier up / Tier down chips in the full sheet, flag `trades.intent_modes` ON. Post-generation filter on best-tier-per-side (star-tax precedent), intent in job freshness key, honest intent-named empty states. Reconciles #168's PRD objection (see `docs/feedback/items/172-trade-intents/status.md`).
- **Mockup labs (design-only):** #211 player-first trades (3 directions, rec: full merge of pin board above deck) and #169 position-impact (3 variants; ppg framing NEEDS NEW DATA — no points source exists; value framing computable today). Operator to pick variants.
- Closed: #113/#156/#168 (done), #155 (declined), #160 (declined → `docs/feedback/backlog.md`).
- Gates: 2053 passed / 1 skipped; tsc clean; per-branch review + sequential merges (all true merges, #172 built on the merged #257 base).

## 2026-08-08 (context-overload remediation shipped — PR #101)

- **Session-boot cost cut ~70–80%** (`e907c93`): zero-read boot contract (4-slice SessionStart hook: HANDOFF + NEXT + CHANGELOG top-2 + GOTCHAS index), living-memory retention policy (CHANGELOG keep-10 + quarterly [archive/](archive/), caps, FORMAT.md §Retention), 30 role-skill descriptions trimmed (5 retired), mobile screens/components CLAUDE.mds rewritten as maps (167KB→15.5KB), backend/web/extension orientation files added, TOCs on the 4 big reference docs, `docs/feedback/items/INDEX.md` (118 rows). Audit + measurements: [`../docs/reviews/2026-08-08-context-overload-audit.md`](../docs/reviews/2026-08-08-context-overload-audit.md). Deferred items in that report §Deferred. Boot measured after: ~5.4k tok vs 19–32k before.

## 2026-08-08 (feature gates + CI shipped as PR #100; express lane)

- **PR #100 squash-merged to main (`4b60440`)**: feature gates (scope block via [`../docs/templates/feature-scope.md`](../docs/templates/feature-scope.md) → Maestro delta → HLD/LLD/api-reference docs table → pre-ship sim gate w/ `githooks/pre-push`), **first real CI** (backend pytest — 1995 passed on base — + mobile tsc + testid-lint), recovery ledger (`docs/recovery/`), branch-triage report, `.gitignore` `scripts/` over-match fix (guard/ops scripts now tracked; testid-lint fixed for BSD + allowlist), feedback skill wired to the gates. **Express lane:** operator may declare "quick fix" to skip gates 1–3 + use `FTF_SKIP_SIM_GATE=1` with a one-line TEST_LEDGER note; agents never self-select; schema/API/flag/analytics changes get an are-you-sure. Operator follow-ups: branch ruleset on `main` requiring the 3 checks; `git config core.hooksPath githooks` per clone.

## 2026-08-08 (branch triage: 50 stale branches content-verified; 15 deleted)

- All 50 content-divergent branches triaged by per-file blob comparison (squash merges make `git cherry` lie): **3 RECOVER / 3 ASK / 44 DELETE** — table + recovery plans in [`../docs/reviews/2026-08-08-branch-triage.md`](../docs/reviews/2026-08-08-branch-triage.md). RECOVER: six-screen `enabled: hasToken` 401 gates + #207 docs (`teardown-remediation`); push-permission-denied banner (`mobile/yellow-followups`); `SegmentedTabs`/`Spinner` (`chalkline-primitives`, cherry-pick only). ASK: SwiftUI `DTF/` spike archive-or-drop; perf-audit-docs Q2 ×2. **15 non-worktree DELETEs executed** — tip shas in [`../docs/recovery/2026-08-08-branch-deletions.md`](../docs/recovery/2026-08-08-branch-deletions.md); 29 remain pinned by worktrees. PR #91 → close (targets deleted tier token).

## 2026-08-08 (feedback #266 + #258 fixes, build 91)

- **#266 — ESPN-path link buttons dead on LeaguePicker:** Settings' ESPN row (`espnLink: true`) triggered a synchronous mount-time `setEspnOpen(true)` while the Settings native modal was still dismissing (settings_v2's coalesced goBack+navigate), wedging the RN `<Modal>` half-presented — ESPN button became a state no-op, and the stuck Modal host blocked the sibling MFL `PlatformLinkSheet` too (iOS won't stack sibling RN Modals). Fix: auto-open deferred to the screen's `transitionEnd` (skipping `closing:true`) with an 800ms fallback for non-animating arrivals. #130 contract preserved. [`../docs/feedback/items/266-espn-link-buttons/status.md`](../docs/feedback/items/266-espn-link-buttons/status.md)
- **#258 — MFL team names with HTML entities:** all ingest paths were already clean since #210 (2026-08-01); the dirty names were rows stored *before* #210, never self-healed because MFL has no automatic re-import. Fix: idempotent startup backfill `_backfill_mfl_name_entities()` in `_migrate_db()` decodes `leagues.name`, `league_members.username/display_name`, and `draft_picks.owner_username/original_username`, scoped strictly to `platform='mfl'`. First Render boot fixed prod without re-linking. 4 tests, failing-first. [`../docs/feedback/items/258-mfl-name-entities/status.md`](../docs/feedback/items/258-mfl-name-entities/status.md)
- **Ship:** merge `b682ee2` → `main` @ `8c3c742`; suite 2041 passed / 1 skipped; tsc clean; sim gate bypassed under standing operator authority (TEST_LEDGER deviation entry). EAS build 91 (commit-verified `8c3c742`) submitted to App Store Connect — first submission FINISHED (two local retries errored as duplicates after a DNS blip killed the first watcher; harmless).

---

## 2026-08-08 (ESPN Connect WebView cookie capture — Phase 1b, flag ON)

- **Shipped `EspnConnectScreen` + `espn.webview_capture` (ON at operator order):** private-league ESPN linking no longer requires a manual cookie paste — the sheet's private section (auto-expanded on `espn_auth_required`) offers "Sign in to ESPN", an in-app WebView to ESPN's own login that captures `espn_s2`+`SWID` from the **native cookie store** (`@react-native-cookies/cookies`, new native dep — HttpOnly cookies are invisible to injected JS). Cookies are cleared on screen mount (fresh login every capture, kills the stale-cookie loop), delivered once via `state/espnConnectBus` to `EspnLinkSheet`, which auto-advances to the team preview. OTP-challenged Disney SSO logins get a presence-only detector (all frames) + native hint banner; nothing but the two cookies ever leaves the WebView. League-tab re-sync auth failures gained a "Sign in to ESPN" recovery button. Manual paste stays as fallback; flag off is byte-identical. Backend untouched (`POST /api/espn/link` already handled cookies). Independent review pass: security clean, 8 findings fixed pre-merge. Scope + TestFlight QA checklist: [`../docs/plans/espn-connect-webview/scope.md`](../docs/plans/espn-connect-webview/scope.md). Sim-gate tier-2 waived by operator (TestFlight build is the validation gate — native dep can't ship OTA). Trigger: a real user's private league (493554) failing to link.

---

## 2026-08-08 (living-memory revival, session-memory contract wired into CLAUDE.md)

- **This folder had been abandoned since 2026-07-08.** 248 commits landed with no CHANGELOG entry; `NEXT.md` was 33 days stale while [`../context.md`](../context.md) told every new session to treat it as "the live queue"; 13 of 20 files still carried their original 2026-05-21 content. Root cause: **nothing referenced `living-memory/` except one line of `context.md`** — [`../CLAUDE.md`](../CLAUDE.md) named `docs/` as the source of truth and never mentioned this folder, so the layer with an enforcement table stayed current and the layer without one died.
- **Enforcement wired in.** `../CLAUDE.md` gained a `## Session memory` section ahead of the reference-docs table: a four-file read-at-start list and a nine-row write-at-end trigger table in the same shape as the existing docs triggers, with next-free IDs inline. `../context.md` now states the write-back half and defers its Open Items list to [`NEXT.md`](NEXT.md) instead of competing with it. `../docs/CLAUDE.md` gained a "not the same thing as living-memory" section drawing the reference-vs-motion line.
- **Backfilled from git** by five parallel read-only agents, one per commit window: 17 dated CHANGELOG entries, [`DECISIONS.md`](DECISIONS.md) D-011→D-020, [`GOTCHAS.md`](GOTCHAS.md) G-013→G-023, plus [`TEST_LEDGER.md`](TEST_LEDGER.md) and [`DEPENDENCIES.md`](DEPENDENCIES.md) entries. [`HANDOFF.md`](HANDOFF.md) and `NEXT.md` rewritten against measured current state.
- **Surfaced in the process:** this checkout is **62 commits behind `origin/main`** and holds an uncommitted ESPN pick-assignment design incompatible with the one `origin/main` already shipped. That is now `NEXT.md` #1 and the top of `HANDOFF.md`. Measured here: 1466 tests passing, tsc clean — but `origin/main` is at 1685.
- **Known deviation:** `GOTCHAS.md` orders its date sections oldest-first, against `FORMAT.md`'s newest-first rule for Pattern A. Pre-existing; new entries were appended to match the file rather than reorder it.

---

*Entries from 2026-07-09 through 2026-08-06 were reconstructed on 2026-08-08 from git history, after this log went unmaintained for a month (248 commits). They are commit-grounded but coarser than same-day entries — where a detail matters, the sha is cited, go read the diff.*

## 2026-08-06 (analytics dashboard rebuild, three client fixes from prod data)

- **Analytics dashboard rebuilt** (`30492ac`): KPI cards with SVG sparklines and WoW deltas, funnel, Journeys path analysis, Retention cohort triangle, Segments, rank-quality, and a friction panel naming the top failing route×status. New `backend/tools/prod_analytics.py` reads Render Postgres read-only. Segments use a **closed grammar** (did / did_not / platform / min_events) — no user string reaches SQL.
- **Three client bugs found by reading 3,346 real prod events**, all invisible in local testing: (1) `platform` was NULL on 100% of client rows — the SDK's batch POSTs never forwarded client-info headers; (2) `api_request_failed` latency was corrupted by app backgrounding — now uses a monotonic clock, stamps `bg:true`, and **omits `ms` entirely when untrustworthy** (so latency analysis must filter on "ms present"); (3) the 401 cluster was post-session-death — `hasToken` never fell to false, plus a bounded retry for 409 `session_not_initialized`.
- **Rookie-draft HLD + LLD** (`824b18e`): `docs/plans/rookie-draft/{hld,lld}.md`, 1218 lines, from the converged dual-agent plan. Suite 1455 passed.

## 2026-08-05 (Acquire tab, stud-tax retune, rank-tab launch routing)

- **#214/#215 stud-tax retune** (`6577668`): three `market`-mode shapes in `package_value_v2` fitted to T1–T6, exposed as per-user `users.stud_tax_mode` (`market` | `heavy` | `off`) via `GET/PUT /api/settings/stud-tax`, honored by both `/api/trade/evaluate` and deck generation. `market` is the new default; `heavy` preserves pre-#214 math byte-identically and legacy suites pin to it. Suite 1445.
- **#245 Trades tab renamed Acquire** (`31c7731`, copy sweep `c795971`); hub gains Trade / Free Agency sections. **#246** unrouted the hub in favor of a guided chip strip + new `TradeDnaSheet.tsx` (`69a8ff8`).
- **#244 completion-aware Rank landing** (`deaa6b2`): no-pref default now routes all-four-quick-tiers-complete → Trios, partial → Quick Set at the next unset position (QB→RB→WR→TE). New `mobile/src/state/quicksetProgress.ts`. No backend change.
- **#250 specific-team acquire scope** (`7d259d4`): `POST /api/trades/asset-ideas` accepts `opponent_user_id`; 'acquire' pool draws only the scoped opponent's roster. **#248** combined rank bars render the other basis as dashed ghost ticks with signed delta chips at ≥2 divergence — two parallel queries, zero backend diff (`2e3f61f`).
- **#221** Settings public-profile row hidden; `profiles.user_toggle` off, web pages stay dark behind `profiles.public_pages` (`20548ff`).

## 2026-08-03 (density passes, market pulse, lineup before/after)

- **#243 vertical-density campaign** across four surfaces, each measured against a viewport budget: TradeValueBar verdict behind a "Why?" disclosure, ~56pt saved per collapsed instance at every mount (`4795a21`); single-pin Controls Card ~286pt collapses to a ~44pt summary row, ~242pt of the audit's ~839pt overflow (`b5242ea`); drill-in filter dedup, focused content 692pt → 557pt (`b2bd078`); trios 3-up mini-cards, RankScreen 747pt → 551pt against a 614pt budget (`d89a4ad`).
- **League home fold and market pulse** (`78d4bb3`): `styles.divider` marginTop removed (a double-margin bug affecting the whole screen), Explore reflowed to a 3-across tile row, new `GET /api/market/movers` behind `market.movers` backed by `database.load_value_movers_window`.
- **#238 lineup before/after** (`c5f6f9c`): `power_rankings.optimal_starter_slots()` extends the Mode B evaluate payload additively with `slots: [{slot, before, after, delta}]`. Written failing-first. Suite 1415.

## 2026-08-02 (featured-trade window, Trade DNA v3, rankings import, Universal Links)

- **#216/#209 featured-trade window** (`ba78631`): the best-difference idea renders as a read-only TradeCard with the TradeValueBar verdict; `AssetIdeasPanel` becomes an always-visible "More trades for &lt;pin&gt;" list; pin board columns swapped to TRADE AWAY left / TRADE FOR right.
- **#212/#231/#206 Trade DNA v3** (`01962ce`) plus **#236 autosave** (`9e7dfd4`): collapsed-by-default DNA panel with in-place editor; every tap POSTs `/api/league/preferences` (one request in flight, trailing coalesce, last-write-wins).
- **#232/#233 rank chooser and rankings import v1** (`2e4ca17`): shared `rankChooserModel.ts` renders 3 outcome-labeled primaries on both RankHome and RankMenu; new `backend/rankings_import.py` behind `ranks.import`, paste → match review → apply. 25 new tests, suite 1405.
- **#239 Universal Links** (`c0e99ba`): `com.apple.developer.associated-domains` was **missing from the committed native project** — bare workflow ignores app.json iOS config, so every invite link went to the browser. Same drift class as FB-131. Entitlement added, AASA route matches ref-less `/?league=<id>`.
- **#229/#230/#234 empty states** (`4ac6673`) ship unflagged: new `LeagueProgressModule`, a "Works right now" example card for low-activity leagues, always-on "Find a trade" on the mutual-match empty state.

## 2026-08-01 (pick integrity, global league switcher, notifications de-chalk)

- **Pick-integrity batch #220/#222/#227/#228** (`2b8ecca`): `sync_draft_picks` no-ops on empty `roster_ids` and the daemon step skips on an unavailable rosters read — **a flaked Sleeper read had been letting the REPLACE-sync wipe a league's picks**. New `trade_service.is_pick_asset` excludes picks from free-agent and drop-candidate lists (pool picks carry a real position, so round 1 was topping the RB free-agent list). New shared `pick_swap_ok` gate bans 1-for-1 pick-for-pick cards across all three generation paths. 13 new tests, suite 1378.
- **#223/#224 global league switcher** (`54e199e`): TopBar left cluster becomes the active league opening one global `LeagueSwitcherSheet`; `LeaguePill.tsx` deleted and every per-screen sheet mount removed.
- **#225 notifications de-chalked** (`ff6bbe7`): every `create_notification` / `_send_typed_push` title and body rewritten emoji-free and fact-first; mobile strips legacy emoji at render (no data migration); web panel now renders the title/body split it had been dropping.
- **#210/#213/#217/#226** (`572f5aa`): MFL `_clean_text` html-unescapes until stable; calculator gains a "Want ideas instead?" row; `PlayerCard` gains `badgeSlot` so OTB/UNTOUCHABLE stop overlapping the position tag.


## Archive index

- 2026-Q3 — 16 entries (2026-07-04 → 2026-07-27) — [archive/CHANGELOG-2026Q3.md](archive/CHANGELOG-2026Q3.md)
- 2026-Q2 — 4 entries (2026-05-21 → 2026-06-11) — [archive/CHANGELOG-2026Q2.md](archive/CHANGELOG-2026Q2.md)

Earlier project history (pre-changelog) lives at the bottom of [archive/CHANGELOG-2026Q2.md](archive/CHANGELOG-2026Q2.md). The "Outstanding / Known Gaps" list as it stood on 2026-08-08 was moved to the bottom of [archive/CHANGELOG-2026Q3.md](archive/CHANGELOG-2026Q3.md) — check [`NEXT.md`](NEXT.md) for the current state.
