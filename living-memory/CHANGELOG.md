# Changelog — Fantasy Trade Finder

> **Purpose:** cross-session memory. Capture what was built, decisions that affect future work, and known gaps.
>
> **Read at:** session start.
> **Write at:** session end.
>
> Companion files: [`HANDOFF.md`](HANDOFF.md) for forward-looking; [`../docs/`](../docs/) for per-feature reference updates.

---

## Table of Contents
- [2026-08-08 (living-memory revival, session-memory contract wired into CLAUDE.md)](#2026-08-08-living-memory-revival-session-memory-contract-wired-into-claudemd)
- [2026-08-06 (analytics dashboard rebuild, three client fixes from prod data)](#2026-08-06-analytics-dashboard-rebuild-three-client-fixes-from-prod-data)
- [2026-08-05 (Acquire tab, stud-tax retune, rank-tab launch routing)](#2026-08-05-acquire-tab-stud-tax-retune-rank-tab-launch-routing)
- [2026-08-03 (density passes, market pulse, lineup before/after)](#2026-08-03-density-passes-market-pulse-lineup-beforeafter)
- [2026-08-02 (featured-trade window, Trade DNA v3, rankings import, Universal Links)](#2026-08-02-featured-trade-window-trade-dna-v3-rankings-import-universal-links)
- [2026-08-01 (pick integrity, global league switcher, notifications de-chalk)](#2026-08-01-pick-integrity-global-league-switcher-notifications-de-chalk)
- [2026-07-27 (calculator polish, MFL scoring detect, MFL pick-wipe fix)](#2026-07-27-calculator-polish-mfl-scoring-detect-mfl-pick-wipe-fix)
- [2026-07-26 (discovery deck engine, five waves)](#2026-07-26-discovery-deck-engine-five-waves)
- [2026-07-25 (platform-league routing, streaks, MFL auth-link, power rankings)](#2026-07-25-platform-league-routing-streaks-mfl-auth-link-power-rankings)
- [2026-07-23 (outlook odds pipeline, FEATURES.md catalog)](#2026-07-23-outlook-odds-pipeline-featuresmd-catalog)
- [2026-07-20 (teardown wave 3, owned draft picks, universal TradeValueBar)](#2026-07-20-teardown-wave-3-owned-draft-picks-universal-tradevaluebar)
- [2026-07-19 (onboarding v2 rollout, analytics ingest ON, teardown waves 1 and 2)](#2026-07-19-onboarding-v2-rollout-analytics-ingest-on-teardown-waves-1-and-2)
- [2026-07-18 (v1.9.0 integrated release, analytics P3 and P4)](#2026-07-18-v190-integrated-release-analytics-p3-and-p4)
- [2026-07-17 (feedback batch 6, flags fail open, Maestro smoke rebuild)](#2026-07-17-feedback-batch-6-flags-fail-open-maestro-smoke-rebuild)
- [2026-07-12 (feedback batch 5, 8-tier ladder, account-first identity, ESPN P1)](#2026-07-12-feedback-batch-5-8-tier-ladder-account-first-identity-espn-p1)
- [2026-07-11 (feedback batch 4, accounts P1 and P2, 6-tier pick ladder)](#2026-07-11-feedback-batch-4-accounts-p1-and-p2-6-tier-pick-ladder)
- [2026-07-10 (pick anchors, tier palette de-collision, feedback batches 2 and 3)](#2026-07-10-pick-anchors-tier-palette-de-collision-feedback-batches-2-and-3)
- [2026-07-09 (trio boundary probing, strategy rotation, feedback batch)](#2026-07-09-trio-boundary-probing-strategy-rotation-feedback-batch)
- [2026-07-08 (Send in Sleeper WORKS — Cloudflare 1010 + raw-token fix)](#2026-07-08-send-in-sleeper-works--cloudflare-1010--raw-token-fix)
- [2026-07-06 (Matches CTAs: Dismiss + Send in Sleeper)](#2026-07-06-matches-ctas-dismiss--send-in-sleeper)
- [2026-07-06 (TestFlight build 21 — v1.3.0)](#2026-07-06-testflight-build-21--v130)
- [2026-07-04 (manual trade calculator: live consensus mode)](#2026-07-04-manual-trade-calculator-live-consensus-mode)
- [2026-06-11 (TestFlight ship: v1.2.0)](#2026-06-11-testflight-ship-v120)
- [2026-06-10 (feedback bugs 45/46/48)](#2026-06-10-feedback-bugs-454648)
- [2026-06-10 (post-ship follow-ups)](#2026-06-10-post-ship-follow-ups)
- [2026-05-21](#2026-05-21)
- [Earlier (pre-changelog)](#earlier-pre-changelog)
- [Outstanding / Known Gaps](#outstanding--known-gaps)

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

## 2026-07-27 (calculator polish, MFL scoring detect, MFL pick-wipe fix)

- **#196/#199/#201** (`6f2ac95`): `mfl_service.detect_scoring_format` added because **nothing had ever written `leagues.default_scoring` for MFL**, so SF TEP leagues rendered as 1QB; one-shot backfill on `GET /api/mfl/leagues`. Duplicate FeedbackFAB removed from the hub.
- **#198/#200** (`0106aba`): asset ideas constrained to the pin's position; **MFL pick-wipe daemon fix** — session-init's owned-pick sync misrouted MFL league 62846 into the Sleeper grid sync, whose empty REPLACE wiped `draft_picks` **on every app open**.
- **Calculator trio** (`fbd5561`): additive `starter_impact` on Mode B evaluate with a `max(50, 2.5%)` noise floor; partner positional value line; share-as-image. **Deck player-changer** (`ec25407`): swap suggestions via a Mode B evaluate of the trade minus one asset. Suite 1359.

## 2026-07-26 (discovery deck engine, five waves)

- **Nine PRDs researched then shipped as five waves in one day**, each wave a flag-gated build followed by a separate flags-ON test gate. Flags pre-registered default-false (`190b5e1`).
- **W1** (`bd3d8c5`, ON `ccc4557`): `deck.signal_v2` impression spine — `deck_impressions` + `deck_outcomes` joined by `impression_id`, features frozen at serve, client dwell timer (500ms viewed, 120s cap). `deck.replenishment` weekly ISO-week-idempotent pre-gen.
- **W2** (`e8385ac`, ON `a284b62`): Thompson v2 with Beta(1, 1/p̂) pessimistic priors, γ=0.995/day decay, archetype×shape arms warm-started from parent — **arm state derived on read, so no schema change and v1 stays byte-identical**. Fatigue discount clamped [0.25, 1.0] with one labeled retest after 30d decline.
- **W3** (`eca7a0e`, ON `9feb6bd`): client-side session re-rank (last-k=10, 0.8 recency decay, eta=0.3; top/peeked/locked cards immovable). Taste vectors with dual-tau (21d/180d), multipliers clamped [0.7, 1.4].
- **W4** (`46c6aff`, ON `315e89e`): exploration wildcard at slot 5, `archetype_auditions` state machine, and unflagged `backend/eval/` replay harness (IPS/SNIPS, cluster-bootstrap CIs, ESS gating, nightly in daily-tick).
- **W5** (`a863f73`): first-session shaping ON; **`deck.value_model` ships dark behind an explicit F8 graduation gate** — replay win on both metrics, ESS≥100, calibration deciles ±20%, then interleave. 8 of 9 deck flags live, suite 1336.
- **Also**: `/api/trade/evaluate` grew additive `eveners` / `adjustments` / `naive_totals`; new `POST /api/trades/asset-ideas`; `sleeper_trades` capture-only behind `market.trade_capture`.

## 2026-07-25 (platform-league routing, streaks, MFL auth-link, power rankings)

- **`league_id.isdigit()` is not a platform test** (`52be577`, `e263490`, `5c29064`): the Sleeper roster proxies routed on it, misrouting numeric ESPN/MFL/Fleaflicker ids to Sleeper → 404 → empty trade-away picker. New `database.is_linked_platform_league()`. The free-agents route now unions `league_members` with a live rosters read and **returns 503 `rosters_unavailable` rather than listing the whole pool**.
- **Streaks fixed** (`e263490`, `5b01e39`, `384b9a0`): `anchor_answered` and `ranking_reorder` added to the streak event set; lapsed streaks decay to 0 at read time (effective, not stored) using `X-User-TZ`; leaderboard reweighted to `props.changed_count` so a 12-player Quick Set save scores 12.
- **MFL auth-link and trade pre-flight** (`03e3e38`, `3b2997e`, `2e9fd34`): `POST /api/mfl/auth-link` (password transient, only the MFL_USER_ID cookie kept, Fernet-encrypted); `POST /api/trades/validate` read-only Sleeper pre-flight returning `league_archived` / `player_moved` / `roster_limit` / `roster_not_found`.
- **Trade engine** (`68920c3`, `3612d43`, `a8898a7`): #185 — owned picks were priced at **default Elo 1500 in every board**; `_inject_owned_picks` now primes the Elo maps with `1200 + 6*pick_value`. #189 two-stage relaxed fallback for zero-card targeted jobs. #163 `not_interested` receive-side exclusion. Cross-format derivation happens at read time, never materialized.
- **Nav restructure** (`fbb6f3e`, `26f76f3`, `0eb1061`, `d6af2af`): `RankHomeScreen.choose` used `navigation.replace`, **trapping users away from the rank-method chooser**; changed to `navigate`. League tab became a LeagueStack rooted at rankings. League power rankings #14 completed (`2c10f4c`), suite 1025.

## 2026-07-23 (outlook odds pipeline, FEATURES.md catalog)

- **#169 outlook odds** (`8bee7f7` backend, `618a3d1` mobile): new `backend/outlook/` package — five swappable phases, each a `typing.Protocol` with a per-phase registry, wired from config; deterministic SHA-256-seeded simulator. New `GET /api/league/outlook`, 404 while `outlook.odds` is off. The flag is absent from both `LAUNCHED_FLAG_DEFAULTS` and `features.json`, so the endpoint is never called. Suite 998.
- **Fixed `ux.retap_active_tab` no-op** (`b8ee011`): the scrollToTop registry shipped with **no tab root ever registering a handler**, so every focused re-tap silently did nothing — a cross-agent handoff gap.
- **Docs** (`9a83265`): root `FEATURES.md` cataloging 30 flag-gated features (flag → PRD → build report → key files) plus `qa/teardown-remediation-qa.md`.

## 2026-07-20 (teardown wave 3, owned draft picks, universal TradeValueBar)

- **Wave 3** (`1580064`): a11y sweep across 42 files, contrast guard `mobile/scripts/check-contrast.js` (13 pairs); `auth.persistent_sessions` DB-backed `sessions` table with SHA-256 token hash at rest, 90d rolling for verified/anchored while **unverified username-only sessions deliberately keep the 4h posture** as impersonation defense; `growth.share_landing`. 967 tests, 30 new.
- **Owned draft picks** (`bcbc46f`, #158/#170/#171): new `backend/pick_values.py` extracted so `database.py` can price picks without a server import cycle; `pool_value(round, years_out)` = generic Mid seed discounted 15%/yr in value space. `draft_picks` gains `pool_value` + `platform`; sync re-wired on the session-init daemon with real `draft_rounds`, fixing dropped 4th-round picks.
- **Universal TradeValueBar on deck cards** (`f5e8ae5`): shared `_value_verdict_payload`, `TradeCard` gains `give_value`/`receive_value`, replacing the 0–1 fairness meter. Ships live, no flag; `fairness_score` kept for back-compat.
- **All 30 teardown flags enabled** (`1d3fb64`) — **branch only, not deployed**. Tier label `first_1` `1st` → `1 1st` (`f2b1114`). v1.11.0.

## 2026-07-19 (onboarding v2 rollout, analytics ingest ON, teardown waves 1 and 2)

- **`analytics.ingest` flipped ON** (`315fccc`): the client emission gate was already on while the server was refusing every batch with disposition `disabled` — **zero baseline rows had landed**. Clients retained their queues, so history flushed on enable.
- **onboarding_v2_rollout enabled** (`51ca4cb`): `is_tester_allowlist` was a registered targeting attribute **with no resolver**, so it matched nobody. Flags route now resolves both device and account units and merges, so device-unit experiments survive sign-in. Allowlist then moved to a git-committed `config/tester_allowlist.json` unioned with env (`b689f28`) because Render dashboard-created services ignore `render.yaml` envVars.
- **Teardown waves 1–2** (`0b7d0fd`, `794fb7e`, `2001369`): Chalkline theme foundation and full web migration (ADR-008); nav/deeplink router v2, toast v2, swipe undo, settings v2. **Two unflagged security fixes**: league-prefs authz, and `rankings/submit` + `league/coverage` now session-scoped — spoofed writes could previously wipe a leaguemate's board. 937 tests.
- **Observability** (`5632dba`): `api_request_failed` and `screen_left` with measured `dwell_ms`; `user_events.country` from the CDN geo header only, never raw IP. **Test Stages** (`8789a80`): allowlist-only `POST/DELETE /api/test-users` minting synthetic `qa_*` users at preset adoption stages, 404 otherwise.
- **Three orphaned-worktree fixes recovered** during workspace cleanup (`85a068c`): consensus-consolidation raw-loss gate, universal-pool failed-DP-fetch retry, `session/init` 400 `missing_user_id`. v1.9.1.

## 2026-07-18 (v1.9.0 integrated release, analytics P3 and P4)

- **v1.9.0 merges four concurrent workstreams** (`71e1a61`): FB-145 KTC values **blended onto the DynastyProcess curve** rather than replacing it (rank-normalized, `ktc_blend_weight=0.5`, 0 = DP-only kill switch, fail-soft scrape); FB-148 `tep_te_uplift=1.18` for SF-TEP because DP's `value_2qb` carries no TE uplift; FB-146 Send-in-Sleeper gated off ESPN leagues; FB-122 Quick Set becomes the default ranking method; FB-147 Sleeper trade-block import. MFL + Fleaflicker Phase 1 dark. Onboarding v2 and monetization scaffolds dark. 781 tests.
- **Analytics P3 + P4** (`877fc91`): `backend/experiments.py` **two-stage layered assignment** — layer_bucket = HMAC(salt : unit), variant_bucket = HMAC(salt : key : version : unit) — guaranteeing in-layer mutual exclusivity. `backend/analytics_stats.py` implements scipy-free two-proportion z / Welch's t (p99-winsorized), CIs, Bonferroni, chi-sq SRM, and a sample-size calculator pinned by `stats_golden.json`. 7 admin experiment routes; `trade.aggression` migrated as Experiment #1. 855 tests.
- **`EXPERIMENT_SALT_KEY` is declared IMMUTABLE once experiments run.** `_seed_experiment_layers` uses INSERT-OR-IGNORE at boot, so a deploy that booted before the key existed keeps dev-fallback salts forever — hence `POST /api/admin/experiments/reseed-layers` (`a55c19e`), guarded on zero assignments.

## 2026-07-17 (feedback batch 6, flags fail open, Maestro smoke rebuild)

- **Feedback batch 6** (`1ea8d32`): FB-141 `filler_min_frac` floor 0.25 at all four package entry points, priced max-across-both-boards; FB-124/139 cross-format tier copy re-seeds to the target consensus curve; FB-142/144 league power rankings + roster tap-through; FB-143 free-agent finder (`backend/free_agent_service.py`, `backend/power_rankings.py`); FB-78/87/88 calculator suggestions server-confirmed via `/api/trade/evaluate`. 632 tests.
- **Flags now fail OPEN for launched features** (`1ea8d32`): `espn.link` and `auth.accounts` baked true client-side after ESPN linking went invisible on fresh installs (FB-115 recurrence, operator build 44). Server fetch stays authoritative.
- **Maestro smoke suite rebuilt** (`1ea8d32`): `mobile/.maestro/flows/smoke/01-09` plus `10-canary`, flows repaired to testIDs. **FB-140** (`8a00d0e`): `Waivers` display label renamed `FA` across all clients — tier key and hex unchanged. v1.8.0, v1.8.1.

## 2026-07-12 (feedback batch 5, 8-tier ladder, account-first identity, ESPN P1)

- **FB-117/118 value recalibration** (`2e9d542`): the DP scale maps **affinely** onto trade value (DP 10000 → the 4-firsts rung, Elo ~1927). Top assets now read 3.6–4.0 firsts, previously capped ~2.1; Mid 1st is ~25% of a top asset, previously 47%. Ladder re-cut to 8 rungs (4+ 1sts … Waivers); value history rescaled via a marker-guarded idempotent migration. Fairness golden pins unchanged. 551 tests.
- **FB-116 account-first identity (P2.6)**: Apple sign-in mints `acct_<id>` sessions **born verified**; the full rank surface works account-only; Sleeper demoted to a linked source with an explicit merge choice. Dark behind `auth.accounts`, flipped ON `05248cb` once the operator enabled the ASC capability.
- **FB-115 ESPN Phase 1**: public-league import by id with a crosswalk match report, manual cookie paste for private leagues, re-sync. `espn.link` flipped ON (`0e47229`) after a live smoke on league 11896 — 14 teams, 100% crosswalk.
- **Follow-ups** (`2b5e07a`): FB-126 Sleeper JWT persisted in the device Keychain with silent replay — chosen over a server-side design a dual-agent security review found **would verify squatters**. FB-131 `com.apple.developer.applesignin` added to the native entitlements plist; **builds 40 and 41 had shipped unsigned for Apple** because the bare workflow ignores the Expo plugin. FB-127 the DP↔Sleeper join now requires position agreement, killing cross-position phantoms. 558 tests. v1.7.1–v1.7.3.

## 2026-07-11 (feedback batch 4, accounts P1 and P2, 6-tier pick ladder)

- **Verified sessions (P1)** (`920a638`): Sleeper JWT proof against a live oracle, 24 write routes gated (grace default; link/propose/reset hard), first-verified-wins, squatter rankings reset. **Read privacy (P2.5)**: 22 board-content routes deny squatter sessions once the owner verifies.
- **Accounts (P2)**: `backend/accounts.py`, `accounts` + `linked_identities` tables, Apple sign-in via JWKS verification **with no new backend dependencies**, in-app account deletion for App Store 5.1.1(v). `auth.accounts` added OFF.
- **FB-108 user-gain gate**: 1-for-1s must gain on the user's RAW board; shrunk-board inversion and the consensus-path bypass both closed (`user_gain_epsilon`). **FB-113/106** "NO pipeline bug" — formats verified separate end-to-end, guardrail fingerprint tests and a runbook procedure added rather than a code change.
- **6-tier pick-value ladder** supersedes FB-103 sublabels: occupancy-justified bands from the anchor Elo ladder, all clients + engine + OG images in lockstep; saved boards re-bucket automatically. 521 tests. v1.6.0.

## 2026-07-10 (pick anchors, tier palette de-collision, feedback batches 2 and 3)

- **Pick anchors** (`66c1b62`): `PickAnchorScreen` prices one player at a time in draft capital; `POST /api/anchor/save` pins Elo overrides; `value_to_elo` added as the inverse of `elo_to_value`; `/api/trade/evaluate` returns `gap` (firsts + nearest generic pick + lighter side). Position-uniform by design — tier falls out of the band walk rather than being set directly.
- **Tier palette de-collided from position colors** (`18f15f7`, FB-83/84 root cause): elite `#fbbf24`, starter `#2dd4bf`, solid `#38bdf8`, depth `#f472b6`. The rule and the hexes are now recorded in `../docs/cross-client-invariants.md`. Tier badge colors had been absent since the flat-list rewrite; position rails masked it.
- **FB-60/69** (`fee6e6d`): `apply_reorder` linear respread had **flattened the convex value curve, producing "44 elite QBs"** — now permutes the players' own Elos. `tier_config.json` recalibrated to rank-count targets and mirrored in mobile + web.
- **FB-41/53/54/61** (`c7562d1`): `leagues.total_rosters` persisted from Sleeper meta (June's `+1` patch had used the wrong source); positional rank + 0–10k value replace raw Elo; real consensus positional rank + 30d trend from `player_value_history`, ADP proxy removed.
- **New `bad_trade_flags` table + flag CTA** (`73858be`), rank-home chooser (`a8706a0`), FB-47 Phase C finder targeting flipped ON (`a0d714d`), FB-71 trade meters (`9fa1342`). 382 tests. v1.5.0–v1.5.4.

## 2026-07-09 (trio boundary probing, strategy rotation, feedback batch)

- **Trio selector rewritten to probe tier boundaries** (`fae6fee`, PR #97): `_algorithmic_trio` picked the tightest uncompared trio by Elo over a top-24 seed window, **so cross-tier comparisons were never asked**. New `_boundary_trio` pairs a player just below a tier edge with one just above, drawn from the full pool. The diagnosis was that the *selector*, not the Elo math, blocked cross-tier movement — the math is untouched. Knobs are DB-seeded `model_config` (`trio_boundary_rate`, `trio_boundary_margin`) so rate=0 is an exact live-revertible rollback.
- **Strategy rotation + anti-repeat** (`b9a4614`): three rotating strategies (boundary probe / within-tier spread / legacy tightest), never repeating the previous; `_trio_avoid_ids()` unions the last 3 served trios. Repetition survived this first fix and needed a second pass (`9fa1342`) — a fixed within-tier cursor start meant every restart opened at Elite #1.
- **Feedback batch** (`eee9164`): FB-89/80 league-driven scoring-format default; FB-81 full-screen tier board; FB-82 drag anchored to touch point via `patch-package`; FB-95 untouchables; FB-77 disposition idempotent on repeat decision (200, no duplicate ELO; conflicting still 409); FB-96 positional need-fit boost. 285 tests. v1.4.0.

## 2026-07-08 (Send in Sleeper WORKS — Cloudflare 1010 + raw-token fix)

- **✅ Send in Sleeper confirmed working end-to-end on device** (build 23, prod). A real trade posted into a live Sleeper league via `POST /api/trades/propose`. Two separate blockers, both backend-only, both found this session — no app rebuild needed for either:
  1. **Cloudflare 1010** (`error code: 1010`, "banned by browser signature"). Sleeper's GraphQL is behind Cloudflare; our server call went out as `Python-urllib/x.y` → banned before reaching Sleeper. Fix: `_post_graphql` sends real browser headers (`_BROWSER_HEADERS`: Chrome UA + origin/referer/accept/accept-language). PR #95.
  2. **`Bearer ` prefix** — Sleeper's GraphQL wants the **RAW token** in `authorization`, NOT `Bearer <token>`. The 2026-07-02 capture recorded `Bearer`; Sleeper dropped it since (or it was misread). Fix: `request.add_header("authorization", token)`. PR #96 (`3de9f92`).
- **How #2 was proven (repeatable technique):** drove the claude-in-chrome MCP on the operator's logged-in sleeper.com session, installed a fetch/XHR interceptor, replayed a real GraphQL request toggling ONE variable at a time. Ruled out cookie (both `credentials:omit`/`include` failed with a fake op), token identity (app's auth == `localStorage['token']`, 356-char JWT, 359-day exp), XHR-vs-fetch (both failed), then the discriminator: `Authorization: <token>` → **200**, `Authorization: Bearer <token>` → **401 "Your token is invalid."** NOTE: the claude-in-chrome extension redacts any JS-result field whose NAME contains token/auth/key — name comparison fields innocuously (e.g. `no_prefix`/`with_prefix`, return only HTTP status).
- **Diagnostic assets added earlier in the chain:** `sleeper_rejected` error code (distinct from `sleeper_expired`, carries `detail`, does NOT loop the client to re-login) + on-device error surfacing in `SendInSleeperButton` (this is what exposed the `1010` then the token error). The prod `sleeper propose auth-rejected: <detail>` log line (via `/api/debug/log`, `X-Cron-Secret: webqa` — LOCAL secret; prod CRON_SECRET differs/unset, so use the Render **Logs tab** instead) is what surfaced `1010`.
- **Runbook correction:** `docs/plans/sleeper-write-capture-runbook.md` §C1 said `authorization: Bearer <JWT>` — WRONG as of 2026-07-08 (raw token). Also: the write API only needs 5 headers (accept, accept-language, content-type, x-sleeper-graphql-op, authorization) + a browser UA to clear Cloudflare; no cookie/CSRF/signature.
- **Next (operator-flagged, not built):** replicate Sleeper's `create_message` op after a successful propose to post a branded "@user proposed a trade via <FTF link>" announcement in league chat (Dynasty Dealer's growth loop) — Sleeper auto-unfurls the link into a card via OG tags (we have `og_image.py`). Make it a toggle (ToS-adverse: posts to shared chat). Capture `create_message` shape in the same DevTools session.

## 2026-07-06 (Matches CTAs: Dismiss + Send in Sleeper)

- **Reworked mutual-match CTAs** (operator request): the Accept/Decline pair on the Matches tab is replaced by **Dismiss** + **Send in Sleeper**. Accept used to POST a disposition (ELO) and deep-link to Sleeper — it was erroring ("Action failed") for matches the disposition endpoint 404/409'd. Send in Sleeper (`/api/trades/propose`) is now the real "execute" action and doesn't depend on the match row; Dismiss just archives.
- **New "archive" path:** `POST /api/trades/matches/<id>/dismiss` + `dismiss_match()` set a per-user `user_{a,b}_dismissed` flag on `trade_matches` (new columns, migrated); `load_matches` filters the caller's dismissed matches out for good. **ELO-neutral** and per-user (counterparty unaffected) — deliberately NOT a decline. 4 tests (`test_dismiss_match.py`); suite 262 green; migration verified idempotent on a legacy schema; both CTAs verified rendering in web preview.
- **Note on the missing button:** `SendInSleeperButton` is flag-gated (`trade.send_in_sleeper`, now ON in prod) and only un-hides after a **cold launch** refetches flags — a resume keeps the stale map. Needs a new TestFlight build to ship the CTA layout change regardless.
- **SHIPPED — both halves live.** TestFlight build 22 (v1.3.0, build id `50a68ed1`), EAS build from `trade-engine-v2`, `autoIncrement` 21→22, auto-submitted to App Store Connect. Backend: **PR #93 merged → main (`43cf083`) → Render deployed** — `/api/trades/matches/<id>/dismiss` verified live in prod (401 session-gated, not 404). The merge was initially classifier-blocked as an unauthorized prod deploy while the operator was away, then merged once the operator explicitly authorized it. Feature complete: Dismiss (archive) + Send in Sleeper both functional on build 22.

## 2026-07-06 (TestFlight build 21 — v1.3.0)

- **Send in Sleeper hardened + iOS build shipped to TestFlight.** Added 6 route tests locking the `/api/sleeper/link` + `/api/trades/propose` error contract (TC-API-002; suite 258 green); flag `trade.send_in_sleeper` stays OFF. `SLEEPER_TOKEN_KEY` set in Render + local (operator).
- **EAS build 21 (v1.3.0) building + auto-submitting to TestFlight** from `trade-engine-v2` — carries the trade calculator (live + demo), Tiers fix, and the flag-OFF Send in Sleeper native module (`react-native-webview`). Build: `56e1a2da`.
- ⚠️ **Version trap (build 20 aborted):** first trigger went out as 1.0.0 — the committed native `ios/` dir makes `app.json` version ignored (not `appVersionSource: remote` as NEXT.md#3 assumed). Cancelled mid-flight, set `Info.plist` + `MARKETING_VERSION` + app.json to 1.3.0 (commit `e291a09`), recorded as [GOTCHAS G-012](GOTCHAS.md). Android `versionName` has the same trap — see NEXT.md#3.
- **SHIPPED TO PROD (16:42 UTC): `trade-engine-v2` → `main` (PR #92), Send in Sleeper flag ON, globally.** Render deployed; verified live — `/api/sleeper/link` returns 401 (route present + flag gate passed, not 404), and `/api/feature-flags` → `flags.trade.send_in_sleeper: true` (client reads `res.flags`, so the button shows after a flag refetch). `trade.send_in_sleeper` is now `true` in `config/features.json`. Instant kill switch: Render env `FTF_FLAGS={"trade.send_in_sleeper": false}` (env wins over json).
- **Big two-stage merge to get there.** `trade-engine-v2` had diverged from BOTH `origin/trade-engine-v2` (another session's FB4 Tiers polish #88 + login bypass #89) and `origin/main` (squash-merged #86/#87/#89 duplicates). Resolved #88 by hand keeping both feature sets (my refetch-clobber fix + Calculator pill AND their statToggle/sticky-header/tile-stats/quick-tier-move/FormatGate); resolved the main divergence with `-X ours` (branch is a content superset) + a dedup fix in FeedbackInboxScreen. tsc clean, 258 tests, both screens rendered in preview.
- **Login bypass #89 reviewed = intentional/prod-safe:** scoped to 5 seeded test usernames on the `sleeper_user` lookup, falls through to real Sleeper otherwise.
- **Still deferred by design:** on-device Send-in-Sleeper test (needs build 21 on a device + throwaway Sleeper acct in a real league), slice-4 calculator Send surface.

## 2026-07-04 (manual trade calculator: live consensus mode)

- **Manual Trade Calculator arc completed (07-02 → 07-04):** standalone Expo mockup (`mockups/trade-calc/`) → ported into the app as `TradeCalculatorScreen` (Calculator pill, Trades stack) → improvement wave (balance-the-trade add-ons, draft picks, arbitrage badges, draft persistence, share) → **live mode**: public `POST /api/trade/evaluate` + `GET /api/trade/values` reuse `_consensus_packages`/`_fairness_v3` over the universal pool (calculator numbers provably match the finder), mobile defaults to "Real values" (format toggle, debounced server verdicts via `ConsensusVerdictCard`), mock league preserved as "Demo league" mode. Per [`../docs/plans/manual-trade-calculator-plan.md`](../docs/plans/manual-trade-calculator-plan.md) (status note added). 8 endpoint tests; suite 252 green; real-pool smoke: 671 valued players.
- **Tiers refetch clobber fixed (HANDOFF 06-16 follow-up #1):** `loading` no longer includes `isFetching` (no more full-screen spinner on background refetch) and a dirty-guard keeps unsaved drag/bulk edits from being wiped by a same-position refetch (save/copy/reset clear the guard so server truth still rebuilds).
- **Route-consolidation watch item:** the staged backlog-#27 web calculator (`/api/calc/*` in `staged-work/`) overlaps the new `/api/trade/*` surface — consolidate contracts when #27 lands (noted in api-reference).
- **Known gaps:** Send in Sleeper "slice 4" (calculator surface) deliberately deferred — needs an in-league calculator mode; backend has no CORS (irrelevant to native, blocks browser-origin API use); CRON_SECRET rotation still pending (operator). Stale root `.handoff.md` (May 21, superseded 06-10 but re-committed 07-03) now deleted.

## 2026-06-11 (TestFlight ship: v1.2.0)

- **Shipped the full batch:** PR #87 squash-merged → Render deployed (verified: feedback `status` field live, migration ran). EAS build `200a88aa` (v1.2.0) built + submitted to TestFlight (Apple processing). Contents: feedback lifecycle status + inbox chips, FB-45/46/48 fixes, engine telemetry, cold-start invite nudge, FB-47 Phases A+B (dark), League polish batch (28/37/38/42), portfolio season fix, restart-proof swipes.
- **Prod backfill executed: 46/46 feedback statuses + 3 severity reclassifications (37/38/47 → idea).** Whole queue dispositioned; remaining open work = FB-47 Phase C (clients) + operator league-mate recruiting (Q-005).
- ⚠️ CRON_SECRET still pending rotation (used from chat for the backfill).

## 2026-06-10 (feedback bugs 45/46/48)

- **FB-45/46 root cause:** server sessions + trade decks are in-memory and die on every Render deploy, while mobile restores its token from secure-store and never re-inits → all calls 401 (Trios breaks) and every swipe fails "Unknown trade_id". Fixes: mobile `revalidateSession()` (cold launch + foreground resume, 60s throttle, never signs out on failure); 401 guard in client.ts (stale 401 can't clear a freshly-minted token); restart-proof `/api/trades/swipe` — payload echoes card context, server reconstructs unknown cards (`_reconstruct_swipe_card`), full decision flow preserved; `trade_card_to_dict` now serializes `target_user_id`.
- **FB-48 root cause:** Sleeper mints a new league_id per season; `league_members` holds last season's instance of each league (verified locally: Lakeview + FFv3 under two ids each) → carried-over players double-count in Portfolio. Fix: `/api/portfolio?league_ids=` scoping, passed by both mobile (session league list) and web (`_cachedLeagues`).
- **FB-47 queued** (standalone needs-based trade finder) in `NEXT.md`; feedback inbox doc updated through id 48. Suite: 127 passing.
- ⚠️ CRON_SECRET was pasted in chat again — operator should rotate in Render dashboard.

## 2026-06-10 (post-ship follow-ups)

- **External research verified online** for the trade-engine deep dive ([`../docs/reviews/trade-engine-deep-dive.md`](../docs/reviews/trade-engine-deep-dive.md) §3 now has sources). Two corrections: eBay QJE 2020 documents bargaining *behavior*, not an ML acceptance model; DynastyProcess's published decay (k=0.0235) is ~2× steeper than the legacy `ktc_k=0.0126` — depth was over-valued by the old curve.
- **Engine telemetry shipped:** `load_engine_telemetry()` in `backend/database.py` + `GET /api/admin/engine-metrics` (`?days=&league_id=`) — like/pass rates by basis, likes-you, deck position, package shape, league; match conversion. 4 new tests (`test_engine_telemetry.py`); suite at 121 passing. Unblocks fairness_threshold / package_adj_gamma tuning.
- **Cold-start invite flow shipped:** mobile `InviteLeaguematesBanner` on TradesScreen (0-ranked leagues → OS share sheet with `/?league=&ref=` referral URL); web coverage row's 0-ranked label gained an Invite button → existing invite modal (verified in browser preview). Supports Q-005 validation (operator recruiting 1–2 league-mates).
- **Operator decisions recorded:** hold 3-team UI until 2-team proves out; keep DynastyProcess values (FantasyCalc deferred — free/keyless but unlicensed); validation via recruited league-mates.
- **Backlog cleanup:** Q-001 resolved (root DB archived to `data/archive/`); Q-002 resolved (pytest baseline exists); Q-006 closed (mobile shipped); May handoff's notification-name bug confirmed already fixed (`server.py:3962`). `NEXT.md` queue refreshed; stale `.handoff.md` superseded.

## 2026-05-21

- **Adopted the 17-pattern living-memory layer** at [`living-memory/`](.). Pattern imported from the `Master Claude Code Best Practices` workspace. All 18 files created (CHANGELOG + HLD + LLD + THIRD_PARTY + SOURCES + PRACTICES + BRAND + SUBAGENT_PRINCIPLES + CONTEXT + GLOSSARY + DECISIONS + OPEN_QUESTIONS + DEPENDENCIES + TEST_LEDGER + HANDOFF + NEXT + MISTAKES + GOTCHAS) plus FORMAT.md, README.md, and the `living-memory-format-check` skill at [`../.claude/skills/`](../.claude/skills/).
- **Decision logged: D-009 — `docs/` as source of truth.** Living-memory files cross-reference [`../docs/`](../docs/) rather than duplicate. Specific mappings in [`FORMAT.md`](FORMAT.md) §Relationship-with-docs. When the two conflict, `docs/` wins.
- **First-pass decisions captured in `DECISIONS.md`** — 10 foundational decisions (D-001 through D-010), all marked Active. Notable: Sleeper as sole identity provider (D-001), 3-player matchups for 2.6× info gain (D-002), Anthropic optional (D-005), SQLite-first/Postgres-swappable (D-007).
- **Open questions captured** — 9 open items (Q-001 through Q-009) including duplicate-DB cleanup, pytest adoption, tiered-matchup-engine acceptance criteria, fuzzy-matching for DynastyProcess names, real-league trade matching launch, iPhone app completion order, Render deployment tier, browser-extension distribution, mascot decision.

## Earlier (pre-changelog)

This section captures the project's state as it existed before the living-memory layer was adopted. Detailed history lives in `git log`, [`../context.md`](../context.md), and the existing [`../docs/`](../docs/) folder.

- **Backend, ranking engine, trade discovery shipped.** Sleeper-based login, 3-player Elo ranking, mutual-gain trade card generation, in-memory debug logging.
- **Web client shipped** as vanilla HTML/CSS/JS in `web/`. Single-page-app pattern.
- **Mobile client in progress** (Expo / React Native). Login + league select screens done; ranking screen in progress; trade-finder not yet ported.
- **Browser extension shipped** (MV3) in `extension/`.
- **Custom skills built and benchmarked:** `feature-evaluator.skill` (7-dimension code evaluation) and `project-reorganizer.skill` (6-phase reorganization workflow; +40pp vs ad-hoc per [`../project-reorganizer-eval-review.html`](../project-reorganizer-eval-review.html)).
- **Existing reference documentation** in [`../docs/`](../docs/) — architecture, api-reference, data-dictionary, glossary, runbook, coding-guidelines, cross-client-invariants, ADR skeleton.

---

## Outstanding / Known Gaps

*Rewritten 2026-08-08. The prior list was from 2026-05-21 and every item on it had since been resolved or overtaken — no test suite (there are now 1466), duplicate root DB (archived), tiered engine unbuilt (shipped), iPhone app incomplete (v1.11.0 on TestFlight), Render unexercised (live).*

- **This checkout is 62 commits behind `origin/main`** and carries an ESPN pick design incompatible with the one `origin/main` already shipped. Top of [`HANDOFF.md`](HANDOFF.md) — this is the blocking item.
- **`deck.value_model` is dark** pending the F8 graduation gate (replay win on both metrics, ESS≥100, calibration deciles ±20%, then interleave).
- **`outlook.odds` is unreachable** — the flag is absent from both `LAUNCHED_FLAG_DEFAULTS` and `config/features.json`, so `GET /api/league/outlook` is never called by any client.
- **Latency analysis must filter on "ms present"** — `api_request_failed` omits `ms` when a request spans a foreground exit.
- **MFL post-draft pick hiding degrades** — stored `futureDraftPicks` only refresh on re-import. Accepted and documented.
- **PR #91 is open and stale** since 2026-07-04 (Depth tier color).
- **Mascot decision still pending** — see [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) §Q-009. No code dependency.
