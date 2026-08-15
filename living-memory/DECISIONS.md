# Decisions — Fantasy Trade Finder

> **Purpose:** day-to-day Architecture Decision Record (ADR) log. Each significant choice with: context → decision → alternatives → consequences. Formal ADRs (one-decision-per-file with author, date, and full context) live in [`../docs/adr/`](../docs/adr/); this file is the terser, cumulative version. Reference ADRs explicitly when applicable.
>
> The index is at the bottom of this file; newest content stays at the top.
>
> **Read at:** before changing a major design choice. **Write at:** when you make one.
>
> Companion files: [`../docs/adr/`](../docs/adr/), [`MISTAKES.md`](MISTAKES.md), [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md).

---

## D-001 — Sleeper as the Sole Identity Provider
**Date:** Pre-changelog (foundational)
**Context:** Need a user-identification mechanism. Dynasty fantasy football is Sleeper-dominated; building separate accounts adds friction.
**Decision:** Use Sleeper username as login. No app-side account creation. Sleeper's public API provides user lookup, league data, and rosters.
**Alternatives considered:** Email/password accounts; OAuth (Yahoo, ESPN, Google).
**Consequences:** Massive UX win (no signup). Hard dependency on Sleeper API. Users without Sleeper accounts can't use the app — acceptable for dynasty focus.
**Status:** Active.

## D-002 — 3-Player Matchups Over 2-Player
**Date:** Pre-changelog
**Context:** Choosing the ranking-interaction primitive. Pairwise comparisons are simplest; full-rank-N is most information-dense per click.
**Decision:** 3-player matchups (rank the 3 in order). Each interaction decomposes into 3 pairwise Elo updates — 2.6× information per swipe vs pure pairwise.
**Alternatives considered:** Pure pairwise (simpler UX); 5-player rank (more info but slower per swipe).
**Consequences:** 2.6× info gain per interaction. Slightly higher cognitive load per swipe. Decomposition keeps Elo math unchanged.
**Status:** Active.
**Related ADR:** consider creating `docs/adr/0001-three-player-matchups.md` if not already there.

## D-003 — Elo Decomposition for 3-Player Rankings
**Date:** Pre-changelog
**Context:** Need an Elo-update rule for 3-player full-rank inputs.
**Decision:** Decompose into 3 pairwise updates per ranking event: rank1>rank2, rank2>rank3, rank1>rank3. Each is a standard Elo update.
**Alternatives considered:** Custom 3-player Plackett-Luce update; Bradley-Terry extensions.
**Consequences:** Reuses standard Elo math. Information theory: each ranking event yields the equivalent of 2.6 pairwise comparisons (vs 1 for pure pairwise). Implementation in `ranking_service.py`.
**Status:** Active.

## D-004 — DynastyProcess CSV as Initial Elo Seed
**Date:** Pre-changelog
**Context:** Need initial Elo ratings for the player base before any user interaction.
**Decision:** Use DynastyProcess GitHub CSV as seed. Mapping: value 10000 ≈ Elo 1800 (elite); value 5000 ≈ Elo 1500 (solid starter); value 0 ≈ Elo 1200 (bench/depth). 660 player rows, 636 with value > 0.
**Alternatives considered:** Other consensus sources (Sleeper trends, KeepTradeCut, FantasyCalc); flat 1500 baseline for all.
**Consequences:** New users get reasonable starting rankings. Hard dependency on DynastyProcess's update cadence and naming conventions. Name mismatches (DynastyProcess ↔ Sleeper) require manual reconciliation via `dump_mismatches.py`.
**Status:** Active. Long-term: evaluate alternative consensus sources or weighted blends.

## D-005 — Anthropic Claude API as Optional Enhancement
**Date:** Pre-changelog
**Context:** Smart matchup selection (picking the most-informative trio) benefits from natural-language reasoning over candidate options.
**Decision:** Use Anthropic Claude API in `smart_matchup_generator.py` when `ANTHROPIC_API_KEY` is set. Fall back to algorithmic selection (tightest Elo cluster) when not.
**Alternatives considered:** OpenAI / Gemini APIs; no AI at all.
**Consequences:** App works fully without an API key. AI is enhancement, not dependency. Per-decision cost is small (~$0.001 with Haiku).
**Status:** Active.

## D-006 — Vanilla Stack for Web Client
**Date:** Pre-changelog
**Context:** Web client choice: framework (React, Vue, Svelte) vs vanilla.
**Decision:** Vanilla HTML/CSS/JS in `web/`. No build step. Files served directly by Flask.
**Alternatives considered:** React (consistency with mobile); Svelte (smaller bundles).
**Consequences:** Trade-off: no component abstraction, more imperative DOM manipulation. Pay-back: zero build tooling, fast iteration, no `node_modules` in `web/`. Mobile diverges intentionally because React Native demands it.
**Status:** Active. Re-evaluate if web UI complexity grows substantially.

## D-007 — SQLite First, Postgres-Swappable
**Date:** Pre-changelog
**Context:** DB choice for personal-use + future-production.
**Decision:** SQLite for local dev (file-based, zero ops). Code uses SQLAlchemy Core with `DATABASE_URL` env var. Switching to Postgres requires only env-var change + smoke test.
**Alternatives considered:** Postgres from day one (more setup); pure JSON files (no querying).
**Consequences:** Easy local dev. WAL mode not enabled — single-process for now. Migration path documented but untested. **Side effect:** the DB file ended up at two paths (`data/trade_finder.db` and `trade_finder.db` at root). Cleanup pending — see [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) Q-001.
**Status:** Active.

## D-008 — In-Memory Ring Buffer Logger (No Log Files)
**Date:** Pre-changelog
**Context:** Need debugging signal without committing to persistent log files.
**Decision:** In-memory ring buffer of last 200 backend events, accessible via `GET /api/debug/log?n=100`. Everything else to stdout.
**Alternatives considered:** Persistent log files (rotated); third-party logging service.
**Consequences:** No disk I/O for logging. Easy forensics during a running session. **Lost on restart** — post-crash forensics is hard. Acceptable for personal-use scale.
**Status:** Active. Reconsider for production.

## D-009 — `docs/` as Source of Truth; Living-Memory Cross-References
**Date:** 2026-05-21
**Context:** Adopting the 17-pattern living-memory layer alongside the existing `docs/` folder. Risk: duplication, conflicting sources of truth.
**Decision:** `docs/` remains authoritative for architecture, schemas, glossary, ADRs, runbook. Living-memory files cross-reference `docs/` rather than duplicating. Specific mappings documented in [`FORMAT.md`](FORMAT.md) §Relationship-with-docs.
**Alternatives considered:** Migrate `docs/` into `living-memory/`; treat `living-memory/` as the new source of truth.
**Consequences:** Two folders to keep in sync — but they have different read triggers and different update cadences (`docs/` = stable reference; `living-memory/` = active state). The `docs/CLAUDE.md` update-trigger table remains authoritative.
**Status:** Active.

## D-010 — Karpathy Four Principles as Coding Discipline
**Date:** Pre-changelog (per [`../docs/coding-guidelines.md`](../docs/coding-guidelines.md))
**Context:** Need a shared discipline for code changes, especially when working with Claude.
**Decision:** Four principles in priority order: (1) Think before coding; (2) Simplicity first; (3) Surgical changes; (4) Goal-driven execution. Bias toward caution over speed; use judgment for trivial tasks.
**Alternatives considered:** No explicit discipline (vibes-only); more granular ruleset.
**Consequences:** Sets the expected posture for every code change. Codified as the project's "engineering brand" — see [`BRAND.md`](BRAND.md).
**Status:** Active.

---

## D-011 — Fix the Selector, Not the Elo Math
**Date:** 2026-07-09 (`fae6fee`, PR #97)
**Context:** Players never moved across tier boundaries. The obvious suspects were the K-factor and the Elo ceiling.
**Decision:** The *selector* was at fault, not the math. `_algorithmic_trio` picked the tightest uncompared trio within a top-24 seed window, so cross-tier comparisons were literally never asked. Added `_boundary_trio` (pairs a player just below a tier edge with one just above, drawn from the full pool). The Elo math is untouched.
**Alternatives considered:** Raise K; raise the Elo ceiling; ordinal anchor placement (Lever B); K-boost (Lever C) — B and C deliberately deferred unless A proved too slow.
**Consequences:** Tier mobility without destabilizing established ratings. All knobs are DB-seeded `model_config` (`trio_boundary_rate`, `trio_boundary_margin`, `trio_within_tier_rate`, `trio_repeat_avoid`), so `rate=0` is an exact, live-revertible rollback to legacy behavior.
**Status:** Active.

## D-012 — Affine Mapping of the DynastyProcess Scale onto Trade Value
**Date:** 2026-07-12 (`2e9d542`, FB-117/118)
**Context:** Top assets capped around 2.1 firsts, which didn't match how the market actually prices elite dynasty players; a Mid 1st read as 47% of a top asset.
**Decision:** Map the DP scale **affinely** onto trade value — DP 10000 lands on the 4-firsts rung (Elo ~1927). Ladder re-cut to 8 rungs. Value history rescaled by a marker-guarded idempotent migration.
**Alternatives considered:** Rescaling the ladder only (leaves the underlying curve wrong); a non-linear fit (harder to reason about and to revert).
**Consequences:** Top assets read 3.6–4.0 firsts; Mid 1st ~25% of a top asset. `top_tier_firsts` default moved 2→4 with defaults byte-identical, and fairness golden pins were unchanged — so the recalibration is provably value-scale-only.
**Status:** Active.

## D-013 — Blend External Value Sources onto the DP Curve, Never Replace It
**Date:** 2026-07-18 (`71e1a61`, FB-145)
**Context:** KTC is a second consensus source. Swapping to it wholesale would silently move every user's board.
**Decision:** Rank-normalize KTC onto the existing DP curve and blend at `ktc_blend_weight=0.5`. Weight 0 is a DP-only kill switch. The scrape is fail-soft.
**Alternatives considered:** Replace DP with KTC; run them as a user-selectable source (more surface, more support burden).
**Consequences:** One tunable knob and an instant rollback path. The curve shape stays DP's, so downstream calibration (tiers, fairness gates) holds. Same pattern later reused for `tep_te_uplift=1.18`, which exists because DP's `value_2qb` carries no TE uplift.
**Status:** Active.

## D-014 — Two-Stage Layered Experiment Bucketing
**Date:** 2026-07-18 (`877fc91`)
**Context:** Concurrent experiments must not silently interact.
**Decision:** Two independent hashes — `layer_bucket = HMAC(salt : unit)` then `variant_bucket = HMAC(salt : key : version : unit)`. This guarantees mutual exclusivity within a layer while keeping variant assignment independent across layers.
**Alternatives considered:** Single-hash assignment (cheaper, but no exclusivity guarantee); a manual do-not-overlap registry (doesn't scale).
**Consequences:** `EXPERIMENT_SALT_KEY` is **immutable once assignments exist** — changing it rebuckets everyone. See [GOTCHAS G-019](GOTCHAS.md). Statistics are deliberately scipy-free (`backend/analytics_stats.py`), pinned by `stats_golden.json`, to avoid the dependency.
**Status:** Active.

## D-015 — Derive Model State on Read Rather Than Materializing It
**Date:** 2026-07-26 (`e8385ac`, Thompson v2)
**Context:** Thompson v2 needed per-arm posterior state for archetype×shape arms.
**Decision:** Derive arm state on read from the F1 impression tables instead of materializing it. No schema change, and v1 behavior stays byte-identical.
**Alternatives considered:** A materialized arm-state table (faster reads, but a migration plus a second source of truth to keep consistent).
**Consequences:** Rollback is a flag flip with no data to unwind. The same read-time principle was applied to cross-format board derivation (`a8898a7`) — never materialized, explicit rows always win.
**Status:** Active.

## D-016 — A Model Ships Dark Until It Passes an Explicit Numeric Gate
**Date:** 2026-07-26 (`a863f73`, deck F6)
**Context:** The learned value model was built and testable, but shipping it on subjective judgment would have been indistinguishable from guessing.
**Decision:** `deck.value_model` ships **dark** behind a pre-committed graduation gate: a replay win on *both* metrics, ESS≥100, calibration deciles within ±20%, then an interleave test. The unflagged `backend/eval/` replay harness (IPS/SNIPS, cluster-bootstrap CIs, ESS gating) runs nightly to evaluate it.
**Alternatives considered:** Ship behind a flag and watch production metrics (contaminates the baseline); hold the code unmerged (it rots).
**Consequences:** 8 of 9 deck features went live the same day; the ninth is still dark and still gated. The gate is checkable *now* — see [`NEXT.md`](NEXT.md) #4.
**Status:** Active — gate not yet evaluated.

## D-017 — Fail Loud Rather Than Serve a Plausible Wrong Answer
**Date:** 2026-07-25 (`5c29064`)
**Context:** When every roster source came back empty, the free-agents route listed the entire player pool — a confident, completely wrong answer.
**Decision:** Return **503 `rosters_unavailable`** instead. The route now unions `league_members` with a live rosters read, and if both are empty it errors.
**Alternatives considered:** Return an empty list (indistinguishable from "this league has no free agents"); serve the unfiltered pool (the bug).
**Consequences:** The free-agents exclusion had regressed three times in three days (#151 default-pool filtering, #178 `owner_id:null` orphan rosters) because both exclusion sources descended from the client-built session payload. An explicit failure mode stops the class.
**Status:** Active.

## D-018 — Unverified Sessions Keep the Short Expiry
**Date:** 2026-07-20 (`1580064`)
**Context:** `auth.persistent_sessions` moved sessions into a DB table with SHA-256 token hashes at rest and 90-day rolling expiry.
**Decision:** 90-day rolling applies **only** to verified or anchored sessions. Unverified username-only sessions deliberately keep the 4-hour posture.
**Alternatives considered:** Uniform 90-day expiry (simpler, but hands a squatter three months of access to someone else's board).
**Consequences:** Impersonation window stays small for exactly the sessions that can't prove identity. Consistent with the first-verified-wins and squatter-reset rules from the P1 verified-sessions work.
**Status:** Active.

## D-019 — Prepare the Trade, Never Fabricate the Execute Path
**Date:** 2026-07-25 (`5c29064`, `d6e867d`)
**Context:** Sleeper has a real write API; MFL and the other platforms do not, and FAAB claims have no API at all.
**Decision:** Where a real write API exists, use it (Send in Sleeper). Where it doesn't, FTF **prepares the claim and deep-links out** rather than simulating an execution it can't perform. `POST /api/trades/validate` runs a read-only pre-flight (`league_archived`, `player_moved`, `roster_limit`, `roster_not_found`) so the handoff isn't into a dead end.
**Alternatives considered:** Screen-scraping writes for non-Sleeper platforms (fragile and ToS-adverse); hiding the feature on unsupported platforms (worse UX than a prepared handoff).
**Consequences:** No feature claims to do something it can't. The pre-flight catches the common failure cases before the user leaves the app.
**Status:** Active.

## D-020 — Analytics Omits Untrustworthy Data Rather Than Reporting It
**Date:** 2026-08-06 (`30492ac`)
**Context:** `api_request_failed` latency was corrupted whenever a request spanned the app being backgrounded — wall-clock time included the time the phone was in a pocket.
**Decision:** Use a monotonic clock, stamp `bg:true`, and **omit `ms` entirely** when it can't be trusted.
**Alternatives considered:** Report the wall-clock value (poisons every latency percentile); report a sentinel like -1 (someone will average it).
**Consequences:** Latency analysis must filter on "ms present" — a real constraint on every query, recorded in [`CHANGELOG.md`](CHANGELOG.md) §Outstanding. Related: analytics Segments use a **closed grammar** (did / did_not / platform / min_events) so no user string reaches SQL.
**Status:** Active.

## D-021 — Capture ESPN's HttpOnly Cookie From the Native Store, Not Injected JS
**Date:** 2026-08-08 (ESPN Connect WebView, Phase 1b — flag `espn.webview_capture`)
**Context:** Private ESPN leagues need `espn_s2` + `SWID`. Phase 1 shipped a manual paste; Phase 1b adds an in-app WebView login (modeled on `SleeperConnectScreen`) so users don't have to hand-extract cookies. But `SleeperConnectScreen`'s technique — inject JS and poll `localStorage`/`document.cookie` — cannot work here: `espn_s2` is issued **HttpOnly**, so page JavaScript never sees it.
**Decision:** Read the cookies from the **native cookie store** (WKHTTPCookieStore) via `@react-native-cookies/cookies` (`CookieManager.get`), polling `www.espn.com` + `fantasy.espn.com` and delivering once BOTH are present. Injected JS is limited to a MutationObserver that signals the Disney SSO **one-time-code step** so a native hint can render — it never reads the code, any field value, or any DOM content. The only data that leaves the WebView is the two cookie strings, handed to `POST /api/espn/link` (never to analytics — the events carry `saw_otp`, never a credential). OTP assist is **detect + hint only**.
**Alternatives considered:** Injected-JS cookie poller like the Sleeper screen (blind to HttpOnly — the credential is literally unreadable); scrape the OTP to autofill it (needs reading the code — a credential we deliberately never touch, and iOS already autofills it from Mail/Messages); stay paste-only (the friction Phase 1b exists to remove).
**Consequences:** Adds a native dependency (`@react-native-cookies/cookies`), so the flag can only be validated in a real build — it ships **OFF** and flips after a TestFlight build validates against a real private league (friend's league 493554). Caveat: the package is **deprecated upstream** (6.2.1's npm notice names `@preeternal/react-native-cookie-manager` / `react-native-nitro-cookies` as successors); kept because the used surface is two calls wrapped in one utils module — see [`DEPENDENCIES.md`](DEPENDENCIES.md) §2026-08-08 for the migration path. Manual paste stays as the fallback; flag off ⇒ the sheet is byte-identical. The pure extractor (`mobile/src/utils/espnCookies.ts` `pickEspnCookies`) is unit-tested; the in-WebView login leg is un-automatable and is covered by manual TestFlight QA. Establishes the mobile pattern for any future HttpOnly third-party credential capture (recorded in `LLD.md` §Specific patterns).
**Status:** Active.
**Related ADR:** — (rides the ESPN linking plan `docs/plans/espn-league-linking-plan-2026-07-11.md` §4 + scope `docs/plans/espn-connect-webview/scope.md`)

---

## D-022 — MFL Draft Room Names Resolve in Four Ordered Tiers, and Never Render a Bare Id
**Date:** 2026-08-10 (feedback #289, `draft.mfl` already ON)
**Context:** MFL Draft Room boards rendered raw ids on both axes. `_render_mfl` set `username = {}` ("MFL has no display-name export here"), so `owner_username` was structurally `null` on every MFL row and the client fell back to the synthetic member id (`mfl:62846.f0001`); and it hard-coded `name: ""`, `position: ""`, `team: None` on every pick, so made picks rendered a bare numeric id with an empty position chip. MFL's export genuinely carries no names — but **ours does**: `league_members` has held the cleaned franchise name for every franchise since link time, and `_mfl_board_binding` was already loading those rows and discarding everything but the ids.
**Decision:** Resolve identity server-side at the single producer (`_render_mfl`), so every board consumer benefits. Franchise names come from the already-loaded `league_members` rows, falling back to `Team <fid>` (matching the sibling `_sync_mfl_owned_picks` convention). Player names resolve in four tiers with **total precedence**: the all-zeros slot sentinel (`player: "0000"`) → `No selection`; our own `players` row for a crosswalked id (the only tier carrying `team`); the DP crosswalk's own `by_mfl_id` name/position map; then the placeholder `Player <mfl_id>`. Total precedence means the two name sources can never disagree about a rendered row.
**Alternatives considered:** Stop at tier 1 and leave `name: ""` on a miss, letting the client's `pick.name || pick.player_id` fallback show the number — **rejected**: rookies are the crosswalk's weakest segment and a rookie draft is exactly where they appear, so that variant leaves the reported defect live on the most likely rows. (Vindicated in the route smoke: against a cold player cache, tier 1 resolved *nothing* and all 30 names came from tier 2 — without it the board would have been 30 rows of `Player 17472`.) Also rejected: a defaulted `members_fn` fetcher to avoid a shared-file edit (a redundant query per render plus a seam whose only purpose is dodging a merge); `Player 0000` for the sentinel (asserts a player exists); dropping the sentinel row (would break a passing test — `_mfl_counts` counts it as made and the suite asserts `len(picks) == man["made"]`).
**Consequences:** The load-bearing guard is **the keying, not the query list.** MFL and Sleeper player ids are numeric strings from different epochs that overlap densely in the rookie band — 255 MFL ids in the committed snapshot are also a *different* player's Sleeper id (`13674` = Dallas Goedert as MFL, Chris Hilton Jr. as Sleeper). A pick may take tier 1 only if its own MFL id crosswalked, and its row must be read by **that pick's crosswalked id**, never by `pick["player_id"]`, which still holds the raw MFL id on a miss. Consuming `load_players_by_ids`' `{player_id: row}` result with the raw id renders one pick's player on another pick — inside a query that is itself entirely legal, and silently. Pinned by `T-289-06`, which was verified to FAIL on the naive keying before being accepted. Zero added queries (names ride objects already fetched); one batched player read per board, none when nothing crosswalked. No schema, route, or flag change — `draft.mfl → false` remains the rollback lever. Known gap, accepted: `original_username` stays `null`, so traded MFL rows still render `from —` (the honest fix is client-side and would escalate the sim gate from Tier 3 to Tier 1).
**Status:** Active.
**Related ADR:** — (feedback item `docs/feedback/items/289-mfl-draft-room-ids/`)

---

## D-023 — Draft-Pick Value Is Subset- and Filter-Independent, Behind a Kill Switch
**Date:** 2026-08-10 (feedback #293/#294, flag `league.picks_always_counted`, default OFF)
**Context:** The League rankings chart counted a team's draft capital only in the All subset with no position filter. Tapping Starters, Bench, or any position pill silently dropped it, so a rebuilding team holding four 1sts ranked like a team holding none. This was *deliberate* and documented in eight comment sites — "Picks are neither starters nor bench" — and it became visible only after #285 summed picks into team values, which created the expectation that pick value is part of a team's worth everywhere. Operator ruling: *"I'm talking about picks for value."*
**Decision:** Pick value is **subset-independent and filter-independent** — the team total includes the full `picks.value` in All, Starters and Bench, and whenever `PICKS` is in the position filter, with the first position tap auto-adding `PICKS` as a visibly lit pill that one tap removes. Shipped behind `league.picks_always_counted` (default OFF, byte-identical to 1.11.0) at operator direction, overriding the orchestrator's unflagged recommendation: this reverses live behavior on a surface the operator uses daily, and a config flip is a cheaper rollback than a TestFlight round-trip.
**Alternatives considered:** Caption-only ("+X from picks" without counting) — rejected, the operator asked for the value *counted*, and it leaves bars, sort order and rank numerals wrong. Proportional allocation of pick value across positions — rejected as fabrication (`cross-client-invariants.md`). Keeping picks out of position filters on the "a position filter shows one position" reading — rejected: it re-creates the reported defect for the filter half.
**Consequences:** **Starters + Bench no longer partition All** — pick value is counted in both. That is intrinsic to the ruling, not a bug; the UI states it rather than letting the user discover it by arithmetic, and the two are never summed on screen. The flag gates **fourteen** expressions and must switch them **atomically**: bar segment heights are percentages of their own sum while a bar's height comes from the team total, so a partially-gated build grows the bar by the pick value while silently stretching the four position segments to fill it — right-looking and wrong, and invisible to a screenshot diff. Two module-scope consumers therefore take the flag as a **required, undefaulted** binding (`activeTotal`'s 4th param, threaded at BOTH call sites; `BarColumn`'s prop), so `tsc` catches an unthreaded caller. Threading only the bars would leave the #248 other-basis overlay short by exactly the pick value, flipping `boardsDifferInView` true and drawing a fabricated tick and rank-swing chip on every column — #208's reported symptom, reintroduced by the fix for #293. Pulling the switch mid-session needed its own reconciliation (R-0.4): flag ON makes `(subset != all AND PICKS in posFilter)` routine, and that state under OFF strands an invisible, unremovable filter member that renders **no bars at all**. Guarded by a 71-assertion AST check (`mobile/tests/check-picks-subset-invariance.js`) whose assertions 13 and 14 were each verified to fail on a sabotaged build that still compiled clean. Graduating the flag to `true` must add the key to `LAUNCHED_FLAG_DEFAULTS` in the same change.
**Status:** Active (dark — flag OFF pending operator flip).
**Related ADR:** — (feedback item `docs/feedback/items/293-picks-in-subsets/`)

---

## D-024 — The Mock-Draft "Run" Is Engine-Internal, and Two Constants Are Load-Bearing in Opposite Directions
**Date:** 2026-08-10 (feedback #290, flag `draft.mock` already ON)
**Context:** The CPU pick model scored `rank - need_bonus - noise` where `rank` is *list position*; `row["value"]` was never read. A 3-slot reach therefore cost the same across a 5-Elo gap or a 300-Elo cliff, which is why the operator saw an implausible early pick. Measured on the shipped engine: 45.5% of round-1 CPU picks reach, and at pick 4 the modal consensus rank was only ~19% likely — near-flat across ranks 1-7.
**Decision:** Partition the consensus pool by a **locally-significant value gap** (a "run": adaptive, vs a local median — not a fixed Elo threshold, because the value curve flattens in the tail) and compose it at the existing `reach_cap` seam via `min(round_reach_cap, run_offset)`, so the rule can only ever **tighten** the operator's verbatim W2e round-tiered policy and that policy's literal test stays untouched. "Tight groups of 4-5" is a target the gap rule *produces* (measured median 5.0 on both scoring formats), **not** a hard size clamp — a clamp would manufacture boundaries where the values have none.
**Alternatives considered:** Reuse the 8-tier ladder — **rejected**, its bands are 200-300 Elo wide and it is a governed cross-client enum; #279 set the precedent for refusing exactly this, so this is the second time. A single tuned `m` — **rejected on measurement**: 27 configurations were swept and **none** clears the collapse on both formats while holding a 4-5 median. `m` was doing two unrelated jobs (where the runs are, a property of the data; how tight a wall may be, a behavioral choice), so the fix was to separate them, not to keep tuning.
**Consequences:** `MOCK_RUN_GAP_MULTIPLE = 2.5` sets run tightness; `MOCK_RUN_MIN_OFFSET = 1` stops a singleton run from making the pick deterministic. **At `MIN_OFFSET = 0`, `sf_tep` forces pick 1.01 in 100% of mocks while `1qb_ppr` looks fine** — a parameter validated on one board and catastrophic on the other. `MIN_OFFSET` must also stay strictly below `round_reach_cap(1)` or the rule is inert in round 1 (`= 3` is a silent no-op). Both bounds are pinned by tests that fail on unfixed code. Separately, aggregating positional need with `max()` is **inert**: TE's `(S,B) = (1,0)` makes `severity("TE") == 1.0` for almost every August roster, so `need_pressure` is denominator-weighted. The guarding tests are two-sided by construction — the original one-sided bars (`P(#1 at 1.01) >= 0.43`, `>= 12 distinct orderings`) both **passed on the fully collapsed board** (1.000 and 24), and a collapsed `sf_tep` even scored *higher* variety than a healthy `1qb_ppr`. N is pinned at 1500 because the distinct-orderings statistic scales with N. The calibration tripwire (`test_w2_16` asserts `all_pass is False`) did not fire.
**Status:** Active.
**Related ADR:** — (feedback item `docs/feedback/items/290-mock-draft-engine/`)

---

## D-025 — The Trade Card Owns Its Disposition, and Absence Is the Card's Odds Design
**Date:** 2026-08-11 (feedback #169 frame decisions, third pass)
**Context:** The operator reviewed the #169 outlook-odds mockups and chose League-Summary frames B+C1+E and card frame C, with two placement corrections. Card frame D (week-6+ odds via a with-trade re-sim) was first selected, then dropped on seeing its backend cost. That left no frame covering week 6+ on the card; the IDP coverage caption's fate had been asked twice without an answer.
**Decision:** Four rulings, all operator-explicit. (1) **The trade card shows no odds block at all, in any week, for now** — week 6+ is *deferred, not designed*; absence is the design year-round. (2) **Pass / Like is the deck disposition vocabulary** in every string surface including VoiceOver (the shipped "Accept this trade" labels violate it and were renamed), and the pair renders **inside the card directly beneath the player tiles** — with `TradeValueBar` below the pair and any future card odds block below the bar. (3) The League-Summary section defaults to a **collapsed one-line "your outlook" strip** (per-league, per-user persisted) with the full section one tap away. (4) The IDP coverage caption **stays**. Additionally the operator **rejected** the dark-flag analytics waiver: `outlook_strip_toggled` ships specced and wired on day one even though `outlook.odds` is dark.
**Alternatives considered:** Card frame B (percentage framing, week 6+) — rejected with C1 chosen league-wide. Card frame D — dropped for its re-sim cost. Flagging the button move — rejected: a pure client reorder where `git revert` is the cheaper lever and a flag would be a dead surface. Deferring the analytics spec to lighting time — operator-rejected (NULL-`platform` lesson: instrumentation exists from day one).
**Consequences:** The card change is client-only and off the bright line's schema/API/flag surfaces (the analytics allowlist is the one backend touch). "Value bar above the playoff outlook" is vacuous today and **binding on whoever designs the deferred week-6+ card treatment** — recorded in `docs/cross-client-invariants.md` § Deck disposition. Lighting `outlook.odds` owes a Maestro flow covering section + strip states and a seeded harness fixture (NEXT.md item 5); the strip's testID is unlintable until that flow exists.
**Status:** Active (build 2026-08-11, branch `feedback-169-e-and-card`).
**Related ADR:** — (feedback item `docs/feedback/items/169-outlook-league-summary/`, decisions record + doc set rev 2)
## D-026 — `ranking_method` Is Written at the Point of Use, First-Use Wins
**Date:** 2026-08-11 (P0-1, mobile UX audit 2026-08-09)
**Context:** `users.ranking_method` was only ever written by the rank-home chooser. The unlock rule in `get_rankings_progress` branches on it, so a Quick Set user who finished all four positions without visiting the chooser fell to the trio branch and stayed locked out of the Trade Finder forever — along with the push primer that rides the unlock. The default path never completed its own progression.
**Decision:** Four save routes record the method as a side effect of a successful save (`/api/tiers/save`, `/api/rank3`, `/api/rankings/reorder`, `/api/anchor/save`), through `set_ranking_method_if_unset` — a single conditional `UPDATE`, race-free, that writes **only where the column is unset**. **First-use wins, not last-use wins.** One exception: a completeness-marking tiers/quickset save may overwrite `'anchor'` and only `'anchor'`. Subset boards write nothing (rookie-scope saves, `via:'rookie_ranks'`, `via:'draft_room'`). A one-time boot backfill tags the pre-fix cohort `'quickset'`.
**Alternatives considered:** **Last-use wins** — rejected: the unlock rule is method-dependent, so overwriting an established method can **re-lock** a user who already qualified, the exact regression the monotonic `unlocked_formats` floor was added for (`server.py:6177-6187`). **A feature flag** — rejected: the OFF position would be the known bug, which is not a rollback lever worth shipping. **Lazy on-read repair** or a one-shot script instead of a startup migration — rejected: on-read repair puts a write in a hot GET, and a script is a thing someone has to remember to run.
**Consequences:** `'anchor'` is the only upgradable value, because it is the only method whose unlock rule can never succeed. The backfill labels the cohort **`'quickset'`** even though which flow they actually used is unrecoverable — an explicit, recorded assumption, and method-segmented analytics show a step change (NULL collapses, `'quickset'` jumps) across the deploy boundary that cannot be backfilled away. The backfill **pre-seeds `unlocked_formats`**, which suppresses the retroactive push fan-out; permanent consequence: that cohort never receives the unlock push for the backfilled format. The backfill also rewrites the seeded `quickset-done` UI-test user on every boot, so the fixture, the seeder guard and the capture all ship inverted **in the same commit** as the fix.
**Status:** Active.
**Related ADR:** — (`docs/plans/audit-p0-remediation/lld-p0-1.md`)

---

## D-027 — A Failed Trade Search Renders a Named, Persistent Deck State; `job.error` Is Mapped, Never Echoed
**Date:** 2026-08-11 (P0-2, mobile UX audit 2026-08-09)
**Context:** A trade search that failed looked identical to one that had never been run: same empty deck, same copy, no error, and a toast that was gone in seconds. Users had no way to tell "nothing found" from "it broke", and no retry.
**Decision:** One named, **persistent** deck failure state with a working retry, driven by a single `deckFailure` state variable — one funnel, set from every failure path — rather than a render-time read of `job.status`. The backend's `job.error` is **mapped to app copy through `jobErrorCopy`, never echoed**.
**Alternatives considered:** **Render the backend message** (the handoff's suggestion) — rejected on reading the field: `job.error` is `str(e)` of a server-side Python exception, or the literal string `"timeout"`. Showing it leaks internals and says nothing useful. **Read `job.status` at render time** — rejected: recency. The poll-abandon path sets `job` to `null`, so a render-time read cannot see the failure that just happened.
**Consequences:** Partial decks keep their cards — the failure state is additive, not a replacement. The toast's existing wording is untouched. `trades-generation-failure.yaml` and `capture/trades.yaml` asserted the *old* behaviour and had to move in the same commit. Closes defect G-029.
**Status:** Active.
**Related ADR:** — (`docs/plans/audit-p0-remediation/lld-p0-2.md`)

---

## D-028 — The Legacy `?league=` Invite Form Is Parsed Forever; the New Path 302s Into the Existing Landing
**Date:** 2026-08-11 (P0-3, mobile UX audit 2026-08-09)
**Context:** The invite loop was broken at both ends — mobile never parsed the `?league=` parameter it emitted, and `invitedBy` lived in memory only, so an invite that required a sign-in (most of them) lost its context on the next launch.
**Decision:** Three parts. (1) The legacy `/?league=<id>&ref=<u>` form is **parsed forever** by both clients and is not deprecated. (2) The new `/app/league/join/<id>` path **302s into the existing web landing** rather than getting its own page. (3) Invite context is a **14-day persisted intent** (`ftf_invite_intent`), not an in-memory value.
**Alternatives considered:** **Deprecate the legacy form** — rejected: links live in group chats and screenshots indefinitely, and removing the parser silently breaks every invite already shared. **A new web join page** — rejected: the existing funnel already converts and already stores the referral; a second page is a second thing to keep correct. **Keep `invitedBy` in memory** — rejected, that *is* the bug.
**Consequences:** Two accepted URL forms forever, recorded as a two-client contract in `cross-client-invariants.md`. The reader, the route and the AASA claim ship **unflagged and first**; only the emitter is behind `growth.invite_join_link`, because Apple's AASA CDN cache (~24 h) makes the natural order actively worse than shipping nothing (see D-028's runbook sequence). 302 not 301 — a permanent redirect would outlive any future landing-page change. TTL is evaluated on read, never by a timer.
**Status:** Active (emitter dark).
**Related ADR:** — (`docs/plans/audit-p0-remediation/lld-p0-3.md`)

---

## D-029 — Post-Auth Routing Keys Off the `no_league` Sentinel, Never Off a User Flag
**Date:** 2026-08-11 (P0-5, mobile UX audit 2026-08-09)
**Context:** A whole sign-in branch — Apple/Google account-only, no linked Sleeper — landed in the tab stack with the `no_league` sentinel pinned, i.e. on empty tabs with no way forward. A live stranding bug in TestFlight.
**Decision:** Route on the **sentinel**: if the pinned league is `no_league`, send the user to the league choice with a companion state that explains it. Extract the Sleeper-identity-link form from `SettingsScreen` into a single-owner `LinkSleeperSheet` component so the picker can offer it. **No new flag.**
**Alternatives considered:** **Key off `user.account_only`** — rejected: a user who has since linked ESPN/MFL/Fleaflicker is no longer stranded, and a flag-keyed predicate would send them back to the picker forever. The sentinel is the *fact*; the flag is a *label*. **A non-dismissible sheet over `Main`** — rejected: it leaves the user technically inside a stack that has nothing in it, and every back gesture becomes a special case. **A skip affordance** — rejected, it recreates the dead end.
**Consequences:** Retroactive for existing TestFlight account-only users — anyone sitting on empty tabs lands on the picker at next launch. That is the fix working, and it is a release-notes line. The `LinkSleeperSheet` move carries the 409 `merge_choice_required` alert whose failure mode is deleting the wrong ranking board, so it moved **verbatim**, keeping `testID="settings.link-sleeper-input"` so the existing capture and the testID lint keep pointing at it. The picker's companion state ships with `invitedBy` / `invitedLeagueName` props that nothing supplied in wave 1 — that is the seam P0-3 renders into.
**Status:** Active.
**Related ADR:** — (`docs/plans/audit-p0-remediation/lld-p0-5.md`)

---

## D-030 — RN-Core `Clipboard` Over `expo-clipboard`; Delete the Mobile Disposition Wrapper, Keep the Route
**Date:** 2026-08-11 (P0-6, mobile UX audit 2026-08-09)
**Context:** `SendInSleeperButton` self-gated on `league_id.isdigit()`, which is true for MFL and Fleaflicker ids too — so those users got a live Send button that always 400s, and matched ESPN users got a match with no action and no explanation.
**Decision:** A **platform-generic gate**: Sleeper leagues send; ESPN/MFL/Fleaflicker get a stated reason plus a working **Copy trade**. The clipboard write goes through React Native core's `Clipboard`, isolated behind a one-function `mobile/src/utils/clipboard.ts`. Separately, delete the unused mobile `setMatchDisposition` wrapper while **keeping the route** — it has a live web caller and ELO consequences.
**Alternatives considered:** **`expo-clipboard`** — rejected on constraints, not preference: `npm install` is unavailable to this build (`mobile/node_modules` is a symlink), and adding a native module would put a DEPENDENCIES entry and a native-build risk into a Bug/effort-S item. **Delete the disposition route with the wrapper** — rejected: web still calls it. **Build accept/decline match UX now** — deferred with the evaluation on the record (see `NEXT.md`).
**Consequences:** RN-core `Clipboard` is deprecated and will be removed from react-native; because the whole surface is one function, migrating is a one-file edit at the next scheduled native rebuild. This change is **not purely additive** — a currently-tappable control disappears for MFL/Fleaflicker users. It always 400s today, so no capability is lost, but it is named in the CHANGELOG rather than discovered. The gate **fails open** on an uncached league id (pre-existing #146 contract): failing closed would hide Send on real Sleeper leagues whenever the platform cache is cold, which is strictly worse.
**Status:** Active.
**Related ADR:** — (`docs/plans/audit-p0-remediation/lld-p0-6.md`)

---

## D-031 — The Reserved `sleeper_send_*` Names, and the Client/Server Split of the Send Funnel
**Date:** 2026-08-11 (P0-7, mobile UX audit 2026-08-09)
**Context:** Launch-day instrumentation was missing across navigation, the League surfaces and the entire send funnel — the north-star leg. Two candidate namings existed: `send_in_sleeper_*` (descriptive) and `sleeper_send_*` (reserved in `analytics_queries` on 2026-07-17 and never fired).
**Decision:** Adopt the **reserved `sleeper_send_*` names**. Split the funnel: **success is server-fired** on `POST /api/trades/propose`; **attempt and failure are client-fired**.
**Alternatives considered:** **`send_in_sleeper_*`** — rejected: `WAT_DARK`, `FUNNEL_STAGES` stage 8 and `FEATURE_VERTICALS["send_in_sleeper"]` already reference the reserved strings, so the reserved spelling lights all three up with zero query edits, and the alternative would have meant renaming them anyway. **All three client-fired** — rejected: a client-forgeable success would sit in WAT and funnel stage 8 next to server-authoritative `trade_ratified`. **All three server-fired** — impossible: a tap that never reaches the server, a network timeout, and the pre-identity refusals (`feature_disabled`, `no_user`, `test_mode_propose_disabled`) are invisible server-side.
**Consequences:** The two namespaces are disjoint by an import-time assertion, so `sleeper_send_succeeded` can never be added to the client allowlist. `sleeper_send_succeeded` is deliberately **not** in `database._EVENT_TO_USER_COL` — bumping `last_trade_proposed_at` would change notification gating, out of scope for an instrumentation item. `tab_selected`, `league_view`, `experiment_exposed` and `quickset_abandoned` had to be added to `NON_INTENT_EVENTS` in the **same commit**, or DAU/WAU would step-change on ship day and break every retention series at that seam. `is_self` on `league_team_opened` was deliberately omitted — the identity was never proven, and a guessed prop is worse than a missing one.
**Status:** Active.
**Related ADR:** — (`docs/plans/audit-p0-remediation/lld-p0-7.md`, `docs/business/analytics/2026-08-11-p0-7-addendum.md`)

---

## D-032 — The Tour's Sign-Off Gate Is Beat Identity, Not Step Count
**Date:** 2026-08-11 (P0-8, mobile UX audit 2026-08-09)
**Context:** The guided tour told users it was over before it had begun — the `s8.1` sign-off beat could fire on a session that had reached almost none of the tour. The audit counted 9 of 15 steps unreachable; the build's own sweep found **16 of 20**.
**Decision:** Gate `s8.1` on **beat identity** — the S2.2 beat must actually have been seen — not on a count of steps seen.
**Alternatives considered:** **A step-count threshold (`stepsSeenCount >= N`)** — rejected for three independent reasons: `stepsSeenCount` is in-memory zustand and resets on launch; `guideSeen` only records `once:true` steps, so a real tour that ended at `s5.5` records 7 keys while an empty release-flag session with two leagues records 3; and any `N` is a magic number whose meaning changes silently the next time a beat is added, removed, or has its `once` flag edited.
**Consequences:** The gate is legible and survives script edits. `err.burst` was deleted from the implementation in the same pass (design intent kept in the script doc, marked unbuilt).
**Status:** Active.
**Related ADR:** — (`docs/plans/audit-p0-remediation/lld-p0-8-9.md`)

---

## D-033 — Request the Celebration First, Consume It Only on Success
**Date:** 2026-08-11 (P0-8/9 defect D1)
**Context:** The first-like celebration was consumed from its one-shot store *before* the bubble slot was checked for availability. When the slot was occupied, the celebration was silently spent and never shown again — the user's first-like moment vanished with no error anywhere.
**Decision:** Request-first, consume-on-success: check the slot, render, and only then mark the one-shot as consumed. If the slot is busy, nothing is spent.
**Alternatives considered:** Queue the celebration for a later slot — rejected as scope: it introduces a lifetime question ("later" meaning what?) for a moment whose whole value is immediacy.
**Consequences:** Generalizable idiom for every one-shot moment gated on a shared UI slot. `celebration_shown` starts landing at the same time (it was firing as `celebration_fired` and being dropped).
**Status:** Active.
**Related ADR:** — (`docs/plans/audit-p0-remediation/lld-p0-8-9.md` §D1)

---

## D-034 — #298 Single-Pin Recovery: the Deck Takes the Lead Slot, It Does Not Stack
**Date:** 2026-08-11 (feedback #298, variant V1 — operator-decided)
**Context:** Pinning one asset removed the Find-a-Trade CTA and the entire deck wrapper, and with it every accept/decline path — swipe, the Pass/Like row and the VoiceOver actions, all of which funnel into `advance()`. Two `singlePin ? null` gates caused it, and they fired identically in the `trades_home_inline` experiment's control group, so the experiment was never the cause.
**Decision:** In single-pin mode the deck renders **only once it has cards** (`singlePinDeckActive`), and `FeaturedTradeWindow` hides while it does. One trade card in the lead slot at all times: the featured window before a generate, the deck card after. The alternates rail follows whichever is leading.
**Alternatives considered:** Simply deleting both null-gates (variant V2) — rejected: it puts the featured window's calculator trade and the deck's top card on screen together, which is exactly the confusion #241 removed. #241's invariant is preserved, not reverted.
**Consequences:** `deck.length`, not `topCard`, is the switch, so the surface does not snap back to the featured window when the deck is swiped out mid-session. After #169 moved the disposition controls into `TradeCard.tsx`, this fix and #169 compose: ungating the deck is what makes the card — and therefore Pass/Like — reachable when pinned.
**Status:** Active.

## D-035 — #298 Ships Without a New Feature Flag
**Date:** 2026-08-11
**Context:** The default for a behaviour change on a live surface is a kill-switch flag. This one is a documented exception, signed off by the operator.
**Decision:** No new flag.
**Alternatives considered:** Adding one — rejected on three grounds. (1) `useFeatureFlags.revalidateFlags` **replaces** the flag map rather than merging it, so a key living only in `LAUNCHED_FLAG_DEFAULTS` is `true` at first paint and `false` a second later — a flickering feature, worse than FB-115's hidden one. (2) Registering it properly requires `backend/feature_flags.py`; `config/features.json` alone is a no-op because `_load_from_json` drops unknown keys. (3) `trade.asset_ideas` is already a real, server-side, deploy-free kill switch for 100% of the diff — with it off, `singlePin` is `null` and every changed line falls back to the unconditional CTA + deck.
**Consequences:** Rollback lever is `trade.asset_ideas → false`. **Generalisable:** "add a kill-switch flag" is not free in this codebase — it is a five-file change spanning `backend/`, and a half-registered flag is a live footgun because of the map-replace semantics. Check both before promising one.
**Status:** Active.

## D-036 — League Roster Tiles: 32pt via an Opt-In Prop, Not the Literal 30pt
**Date:** 2026-08-11 (feedback #299)
**Context:** The operator asked to cut the League roster tiles "to about half" their height.
**Decision:** 32pt (−47%), delivered through a new `denseSingleLine` prop on `PlayerCard` that defaults to `false`.
**Alternatives considered:** Literal 30pt — rejected: it needs `paddingVertical 2 → 1` on the shared `Badge` primitive, which renders position, tier, rookie and injury badges on every screen in the app. 32pt is the natural floor of the existing primitive (badge 20pt + 6pt above and below). Two points of gain is not worth an app-wide component fork.
**Consequences:** The Tiers board — pressable, drag-liftable, and needing its `statsSlot` — is untouched, as is the FA list; both keep the 60pt two-line row. Draft-capital rows (`pickRow`) came down 40 → 32 in the same pass so the picks group doesn't read tall beside the roster. 728pt reclaimed on a 26-man roster; 4 → 8 players above the fold.
**Status:** Active.

## D-037 — League Drill-In Back Affordance Lives on the Stack Header, Tab-Root Only
**Date:** 2026-08-11 (feedback #302, variant V2)
**Context:** The drill-in is component state (`selectedId`), not a stack push, so **no** system back worked anywhere: no stack back (LeagueRankings is the stack root), no iOS edge-swipe, and no `BackHandler` was registered. A back control did exist, but it sat in the chart-card header above ~1,600pt of roster, top-right against an app convention of top-left, at 11px beside a 16px title.
**Decision:** Move the exit into the already-fixed stack header (`headerLeft` + title swap) at zero vertical cost. **The Android `BackHandler` was built and then WITHDRAWN before ship** (operator, 2026-08-11): no Android device or emulator was available at any point in the batch, and this release is iOS/TestFlight-only, so shipping it would have put unverified code down a path no tester could reach. It returns with the first non-App-Store release. `'hardware_back'` stays a **reserved** `via` value with no emitter — kept registered so re-enabling is one `useEffect` rather than a taxonomy migration (the `sleeper_send_*` precedent, D-031) — and both halves are pinned: the value stays allowed, and nothing emits it.
**Alternatives considered:** A 38pt sticky bar (variant V1) — rejected as costing vertical space on the screen #299 is simultaneously compressing. Making the drill-in a real route push — rejected: it breaks the 2026-07-26 Analyzer treatment (chart stays visible above the roster) and #237's shared filter state.
**Consequences:** **Scoped to the tab-root registration.** The legacy root-stack `LeagueSummary` (deep-link entry, `RootNav.tsx:508-530`) already owns its `headerLeft` — the explicit JS back that exists because native back is dead over `headerShown: false` (RNS#3294) — and `setOptions` cannot restore what it overwrites. That variant keeps the in-card link; the two are mutually exclusive, so there are never two back controls and never a duplicate testID.
**Status:** Active.

## D-038 — Adopt `league_team_opened` for the League Drill-In; Add Only an Exit Event
**Date:** 2026-08-11 (feedback #299/#302 analytics)
**Context:** A prior instrumentation round, working against `origin/main` @ `ab9368f`, found no event covering the drill-in and specced a `league_team_focused` / `league_team_unfocused` pair. Between that check and its ship, `main` advanced 21 commits and the P0-7 round registered 17 client events — including `league_team_opened`, fired from the single `openTeam` helper both drill-in entry points route through, carrying the same bar-vs-row `via` the new pair proposed re-minting.
**Decision:** Adopt `league_team_opened` unchanged as the enter half. Add exactly one new name, `league_team_closed {via, dwell_ms, rank}`, for the exit — which genuinely had no signal, because the drill-in is component state and emits no `screen_left`.
**Alternatives considered:** Shipping the focused/unfocused pair — rejected: two events for one interaction on this screen is the two-sources-of-truth bug #208/#248/#293 are a catalog of.
**Consequences:** All five exit controls route through one `closeTeam` choke point, and the file has exactly one bare `setSelectedId(null)`; both are statically pinned, so a new exit control that forgets to fire fails a check rather than silently vanishing from the data. `league_team_closed` is NON-INTENT, added in the same commit as its allowlist entry. Abandonment (opened, never closed) is measured by absence; there is deliberately no unmount-cleanup emitter, which would double-fire on React strict-mode remounts and invent dwell. **Meta-consequence worth generalising: an instrumentation gap analysis is only valid against the `origin/main` the work will land on.** Two of this batch's premises were true when checked and false when shipped.
**Status:** Active.

## D-039 — Tier-Board Share Routes Get a Flag Whose Resting State Is OFF
**Date:** 2026-08-11 (P1 remediation, operator decision D-P1-12)
**Context:** `GET /og/tiers/<pos>/<username>.png` and `GET /s/tiers/<pos>/<username>` shipped with **no guard of any kind** — no session, no in-app link, no flag. Any user's tier board, with their username in the page title, was fetchable by guessing the URL. The operator believed this had already been disabled; what had actually been disabled was the public *profile* surface (`profiles.public_pages` / `profiles.user_toggle`, #221) — a different surface entirely. The neighbouring package routes had always closed behind `growth.share_landing`, which never covered these two.
**Decision:** Add `growth.tier_board_share`, default OFF in both `feature_flags.py` and `config/features.json`, guarding both routes to 404 exactly as the package routes do. Operator decision D-P1-12 rules that sharing of rankings / tier boards is **not a product surface**, so **OFF is the resting state, not a dark launch** — flipping it requires an explicit reversal, and the code, config and docs all say so.
**Alternatives considered:** Deleting the routes outright — rejected: a flag is reversible in one line and the renderer (`og_image.render_tier_card`) has other potential callers. Reusing `growth.share_landing` — rejected: it is ON in production and gates the trade/package loop, which the operator wants to keep; one switch for two products with opposite intent is how this exposure survived in the first place.
**Consequences:** Blast radius is nil — `web/js/app.js` `buildTierShareUrl()` is dead code (defined, never invoked), and no mobile, extension or Maestro reference exists. Three flag fixtures needed updating, not one: `release.json` is an enforced mirror of `config/features.json`, and `profiles-on.json` / `onboarding-v2.json` assert an **exact key set** against it. **Generalisable:** "is this surface gated?" must be answered by reading the route, not by recalling which flag was flipped — an adjacent, similarly-named surface being closed is not evidence.
**Status:** Active.

## D-040 — T1 Registers Four Analytics Names and Defers Four; the File Is Not Final
**Date:** 2026-08-11 (P1 remediation, commit T1; operator decision AN-4)
**Context:** `ALLOWED_CLIENT_EVENTS` is default-deny **and silent** (G-031): an unregistered name is dropped behind a 200, an unregistered prop is popped off a row that otherwise lands. Registration must therefore precede every emitter. Five workstreams claimed this one file.
**Decision:** Register exactly four names — `calc_trade_shared` (INTENT), `share_package_created` (NON_INTENT), `invite_cta_shown` (NON_INTENT), `invite_cta_tapped` (INTENT) — plus two prop-row **extensions in place** (`invite_shared` +4 props; `trade_card_shared` +`landing` +`surface`). Classification is explicit in `NON_INTENT_EVENTS` because `INTENT_EVENTS` is a **deny-list**: silence ships an event as INTENT and step-changes DAU/WAU on the day its emitter goes live. Defer the four `sleeper_connect_*` names pending naming decision AN-1; cancel `tier_board_shared` (D-P1-12) and `email_captured` (AN-6).
**Alternatives considered:** Registering `sleeper_connect_*` with a guessed name — rejected: a wrong name in a default-deny registry is worse than a missing one, because it looks live. Waiting for AN-1 before landing any of T1 — rejected: it blocks two other items for one item's open question.
**Consequences:** **A T1 amendment commit is required** before P1-10's client wiring ships; the taxonomy file is not final and assertions pin all three absences so nobody "fixes" them by accident. Prop-row extensions are the dangerous half — a three-way merge resolving one back to its pre-existing value keeps the name working and hollows out every row — so both are asserted in two separate test files.
**Status:** Active.

---

## D-039 — ESPN Trade-Write Is No Longer Categorically Prohibited; It Ships Through a Verification Gate
**Date:** 2026-08-12
**Context:** `docs/plans/espn-league-linking-plan-2026-07-11.md` §2/§7 recorded a hard "Send in ESPN (write) — ❌ never on this plan": server writes to a Disney property were judged a categorically worse legal/ban posture than reads, and "copy trade to clipboard is the ceiling." A 2026-08-11 spike found the ban-risk judgement still sound but the *infeasibility* assumption too strong — the write host and `TRADE_PROPOSAL` envelope were community-captured, and FTF already stored the exact cookies and owned the player crosswalk. The operator reviewed the spike and elected to proceed.
**Decision:** The categorical NO-GO is **reversed to a conditional GO**, operator-explicit, and both gating probes have since **passed**, so `espn.send` is now **ON** in `config/features.json`. Probe 1: the DynastyProcess crosswalk's `espn_id` **is** the write-API `playerId` (live-verified 4/4 across two real `ffl` proposals). Probe 2: a POST carrying **only** `espn_s2`+`SWID` and the static `x-fantasy-*` headers — **no CSRF or per-session token** — returned **409 `TRAN_INVALID_TRADE_TEAM_COUNT`**, a trade-domain validation error only reachable *after* auth and authorization succeed; probed with `items: []` so nothing could be created. Evidence: [`../docs/plans/espn-send-live-capture-2026-08-11.md`](../docs/plans/espn-send-live-capture-2026-08-11.md).
**Alternatives considered:** Keep the NO-GO and ship only deep-link + clipboard — rejected as the ceiling the operator chose to raise, though it remains the automatic fallback and the flag-OFF path. Ship on the community-captured *baseball* payload without football verification — rejected; the `playerId`-space assumption was load-bearing and the live capture corrected three scaffold errors (ISO vs **epoch-ms** `expirationDate`, four missing `items[]` fields, a hardcoded `scoringPeriodId`).
**Consequences:** Supersedes the §2/§7 NO-GO in the ESPN plan. Inherits D-019's posture and mirrors Sleeper's: per-user own-credentials/own-trade framing, terms/privacy disclosure, default-OFF flag retained as the kill switch. Residual Disney ToS/ban risk is an accepted operator call. Draft picks stay **hard-blocked** — and 2026-08-12 research clarified *why*: ESPN models only current-draft slots (`DRAFT_TRADE` + `overallPickNumber`), which has no counterpart for FTF's multi-season future rungs, so the block is correct on modelling grounds, not merely "encoding unverified."
**Status:** Active (`espn.send` ON; shipped `main` @ `2fa1ff2`, TestFlight 1.13.0 build 103+).
**Related ADR:** — (spike: `docs/plans/espn-send-spike-verification-2026-08-11.md`; reversal draft: `docs/plans/espn-send-decision-reversal-draft-2026-08-11.md`)

**Numbering note:** this entry was first drafted as *D-026* against a stale checkout. `origin/main` had meanwhile issued D-026 through D-038 from concurrent sessions, so it was renumbered to D-039 on write-back. Same lesson as D-038's meta-consequence: **claim an ID against `origin/main`, not your working tree.**
## D-041 — Unlock Is Per-Method and Reads the Board, Not the Event Stream
**Date:** 2026-08-11 (P1 remediation, P1-7; audit A-16/A-17; operator decision D-P1-10)
**Context:** `get_rankings_progress`'s ladder branches on `ranking_method`. `'anchor'` had **no arm** and fell to the trio rule, which needs 10 swipe interactions per position — and `apply_anchor` writes Elo overrides and never a swipe, so that cohort could **never** unlock. `'manual'` had the opposite defect: `unlocked = True`, unconditionally, which post-P0-1 is reached by one drag on Manual Ranks or one Quick Rank step.
**Decision:** Every method gets an explicit arm. `'anchor'` and `'manual'` unlock at `>= RankingService.{ANCHOR,MANUAL}_UNLOCK_MIN` **pool-resident** entries in the persisted board (`users.tier_overrides`, via the new `board_override_count()`), **or** the tiers rule. Both bars are 40, matching the trio bar so the product has one number to explain. `_tiers_rule()` is extracted as the shared seam. **`MANUAL_UNLOCK_MIN`'s value is a stated assumption awaiting operator confirmation; its shape is not.**
**Alternatives considered:** *Add `'anchor'` to the tiers/quickset arm* — **inert**: that arm reads `tiers_saved`, which the anchor lane never writes and is forbidden from writing (`_ANCHOR_VIA`'s contract; `save_tiers_position` does not occur in `save_anchor_route`). *Bump the interaction counter in `apply_anchor`* — **non-durable**: `_interactions` is overwritten from persisted swipes at session build, so unlock on Tuesday, re-locked on Wednesday; and it would grant credit to the `via:'draft_room'` path P0-1 deliberately excludes, plus to NULL-method users, while mixing units (a trio *orders* three players, an anchor *prices* one). *An Elo fingerprint* recognising the eight rung values — rejected as a comment waiting to lie.
**Consequences:** A draft-room-only anchorer **stays locked** — designed, not a bug: their method stays NULL so the arm is never entered, and their overrides count later if they ever answer one wizard question, because the predicate reads the board rather than the event stream. `ranking_complete_first_time` begins firing for the anchor cohort, a **step change in a shipped funnel series**. The manual arm is a tightening, made safe by the monotonic floor; a *strong* A-17 gate needs a product decision and a client payload change (the client posts the whole visible list on every drag) and remains P1-8's.
**Status:** Active.

---

## D-042 — First-Unlock Fan-Out Is Suppressed by a Backfill, Not a Special Case
**Date:** 2026-08-11 (P1 remediation, P1-7 RL-5)
**Context:** Crossing the unlock bar takes a `was_first` branch that emits `ranking_complete_first_time` and pushes "@user just unlocked Trade Finder" to **every joined leaguemate**. Giving `'anchor'` a rule flips a pre-existing cohort locked→unlocked on their first poll after deploy, which would fan out retroactively for work nobody did that day. P0-1 faced the identical question.
**Decision:** Match what P0-1 **did**, read from the merged code rather than from any plan: leave the `was_first` branch untouched and add a boot-time backfill (`database.backfill_anchor_unlocked_formats`) that pre-seeds `users.unlocked_formats` for the qualifying anchor cohort, so `mark_format_unlocked` short-circuits and neither the event nor the push fires. Not done for `'manual'`, which P1-7 only ever tightens.
**Alternatives considered:** Suppressing inside the `was_first` branch for anchor users — rejected: it makes a permanent code special case out of a one-deploy problem, and it would also suppress *genuine* future unlocks. Doing nothing — rejected: the burst is the kind of thing that reads as spam to a whole league at once.
**Consequences:** The backfill's cohort predicate is a deliberate **superset** of the runtime one — it counts stored overrides, while the runtime rule counts pool-resident ones, because the player pool is not a database concept. The direction is generous (grants an unlock a hair early, never locks), which is the right side to err on for a suppression pass. The affected user ids are logged, per the same rule P0-1's backfill set, so a scoped SQL undo stays expressible.
**Status:** Active.

---

## D-043 — Shared Display Vocabularies Are Derived From One Constant and Pinned Structurally
**Date:** 2026-08-11 (P1 remediation, P1-7; operator decision RL-6/RL-7)
**Context:** The Pick Anchor rung grid authored its own eight label strings beside `TIER_LABEL`, which says the same eight things for the rest of the app. **Five of the eight had drifted** — a user tapped "1 2nd" and read back "2nd" inside one interaction.
**Decision:** `TIER_LABEL` is canonical (~21 occurrences across four clients and the docs, versus `ANCHOR_ROWS`' one). Anchor labels are **derived** via `ANCHOR_TIER` + `anchorLabel()`, never authored. `no_value` displays **FA** (borrowing `TIER_LABEL.waivers`) while `ANCHOR_TIER['no_value']` stays **null**, so the display agrees with the badge the player wears on the Tiers board without the code asserting an equivalence the backend does not make. The guarantee is scoped **in writing** to the default `anchor_scale`.
**Alternatives considered:** Conforming `TIER_LABEL` to the grid — rejected on weight of evidence. A ninth vocabulary item for `no_value` — rejected: it re-forks the thing being unified.
**Consequences:** A change to the ladder's vocabulary now flows into the wizard automatically, which is the point. `mobile/tests/check-anchor-labels.js` (`npm run test:anchor-labels`) enforces it with five independently-failing AST assertions. **Its first cut was defeated by `label: key === '1_second' ? '1 2nd' : anchorLabel(key)`** — it inspected only the root of each initializer — and was fixed to walk the whole subtree; see G-035. Three copies of the ladder vocabulary remain in mobile (`TIER_LABEL`, `TierBadge.tsx`, `chalkline/Badge.tsx`); they agree today but are not derived, and are filed to `NEXT.md` together with the `tierForElo` floor gap.
**Status:** Active.

## D-044 — A Position Filter Means That Position: Rules A and B Removed
**Date:** 2026-08-12 (feedback #300; reverses part of #293/#294)
**Context:** `league.picks_always_counted` shipped 2026-08-10 with two toggle rules. **Rule A** auto-added `PICKS` on the first position tap so draft capital never silently vanished under a filter. **Rule B** cleared the filter to All when removing a position left no core position, "instead of stranding the user in a picks-only ranking they never asked for". #300's median divider then found rule A load-bearing in the wrong direction: with it live, tapping WR ranked the league by **WR + capital** while any median measures WR alone, so no honest line could be drawn — and in a pick-carrying league (i.e. all of them) the feature sat one undiscoverable tap from invisible.
**Decision:** Remove both. A position filter means that position; pick value is an explicit opt-in. Operator ruling: *"All leagues have picks. They should not be selected along with a position filter. Only by explicit user action."*
**Alternatives considered:** Keeping rule A and gating the divider on `PICKS` absent — built first, and rejected: it left the natural path (tap WR from All) reaching nothing, which is the #205 tenet failure of requiring the user to know how the app works. Narrowing rule B — impossible: with rule A gone, every `PICKS` is hand-chosen, so rule B's trigger set and the case the ruling protects are the same states.
**Consequences:** Reversibility becomes structural (a plain toggle is its own inverse) and strictly better — `{PICKS}` + RB − RB now returns to `{PICKS}` rather than costing the extra tap #294 accepted. #294's "hidden hand-chosen state axis" objection is obsolete. **What #293 originally complained about can return**: a rebuilding team's capital is no longer counted under a position filter unless the user asks. That is the intended trade, not an oversight. The flag still governs picks in all subsets, the bar segment, legend, pill, drill-in group and hint strings — only the auto-add is gone. Two Maestro flows and one structural suite were re-pinned; the original reasoning is preserved in the code comments and the `features.json` block rather than deleted.
**Status:** Active. Shipped `5139b45`, v1.13.1 build 106.

## D-045 — An Inbox Row Is Written Beside the Push, Never Inside the Dispatcher
**Date:** 2026-08-13 (notif-inbox-growth; operator decisions GD-1…GD-8)
**Context:** Six notification types that push today left no trace in the bell inbox, and `_send_typed_push` has never written one for any kind — 11 of 14 kinds had no inbox row at all. The obvious economy was to add `create_notification` inside the dispatcher and get all 14 at once.
**Decision:** Rows are written **at the call site, beside the push**, via a thin `_write_inbox_row()`. The dispatcher stays push-only. Idempotency is the caller's job and may **not** borrow the push's.
**Alternatives considered:** Writing the row inside `_send_typed_push` — rejected: its five gates (prefs → bucket → frequency cap → quiet hours → Expo) are each a statement about *interrupting* the user, and none is a statement about what belongs in a list the user chose to open. A row inheriting them would inherit `deck_replenished`'s: that kind sits in the `reengagement` bucket, which `notif.reengagement_default_off` forces to 0 for every user without a stored pref, so its push reaches **zero** users — and its inbox row would have reached zero users too, silently. Writing rows in a post-dispatch hook — rejected for the same reason plus a worse one: the hook only runs when a push leaves.
**Consequences:** The inbox is now a surface with its own rules rather than a push mirror, which is what lets phase 1 ship to **every** user while push stays operator-only — nothing here waits on the push rollout. The cost is one extra line per call site and an explicit idempotency decision each time. `_freq_cap_blocks` reads `notification_events_log`, which is only written when a push **actually leaves**, so a suppressed push logs nothing: the 15-minute `match_expiring` cron would have re-written its row ~96×/day per match on a shared gate. It uses `notification_exists_with_meta`, keyed off the inbox's own rows; the other three sites are structurally once-only. Recorded in `living-memory/LLD.md` and `docs/cross-client-invariants.md`.
**Status:** Active.

## D-046 — The Bell Carries Receipts, Not Prompts; the Invite Ask Lives in the Empty State
**Date:** 2026-08-13 (operator decisions GD-1, GD-3)
**Context:** The operator asked to use the notification list for things we want users to *do* — invite leaguemates, re-rank players, learn about new members. The inbox today is an event log: everything in it is news. A prompt list is a different object, and prompts are always available while news is not, so mixing them without a rule converts the log into the prompt list.
**Decision:** v1 ships **six receipt/social rows and zero prompt rows**. The invite ask goes in the bell's **empty state**, gated at the shipped <50%-penetration rule (`MatchesScreen.tsx`, D-P1-13 PR-6) — never a standing row. Ordering stays recency-only; no `priority`/`expires_at` columns until the first prompt row is approved.
**Alternatives considered:** A standing invite row — rejected: it fails the slot test by construction (true for every user every day, therefore not news), and five in-screen invite surfaces already exist. A single-lifetime invite row fired at a moment of demonstrated need — defensible, and left on the table if the operator wants it. A pinned "for you" section — rejected: two lists in one sheet, solving a crowding problem six rows a month do not create.
**Consequences:** What is protected is that **opening the bell is currently always worth it**. The empty state is structurally incapable of burying a receipt — it exists only when there is nothing to bury, and disappears the moment the surface has content. The honest cost of recency-only: unread rows never age out (`get_notifications` returns all unread), so a row can sit for weeks. Fine for receipts, not for prompts — a second, independent reason prompts wait. Phase 3 prompts are gated on `notif_row_tapped` showing the bell is used at all.
**Status:** Active. Reasoning: `docs/business/product/2026-08-12-notification-inbox-growth-surface.md`.

---

## Decision index

| ID | Title | Date |
|---|---|---|
| D-001 | Sleeper as the Sole Identity Provider | Pre-changelog |
| D-002 | 3-Player Matchups Over 2-Player | Pre-changelog |
| D-003 | Elo Decomposition for 3-Player Rankings | Pre-changelog |
| D-004 | DynastyProcess CSV as Initial Elo Seed | Pre-changelog |
| D-005 | Anthropic Claude API as Optional Enhancement | Pre-changelog |
| D-006 | Vanilla Stack for Web Client | Pre-changelog |
| D-007 | SQLite First, Postgres-Swappable | Pre-changelog |
| D-008 | In-Memory Ring Buffer Logger (No Log Files) | Pre-changelog |
| D-009 | `docs/` as Source of Truth; Living-Memory Cross-References | 2026-05-21 |
| D-010 | Karpathy Four Principles as Coding Discipline | Pre-changelog |
| D-011 | Fix the Selector, Not the Elo Math | 2026-07-09 |
| D-012 | Affine Mapping of the DynastyProcess Scale onto Trade Value | 2026-07-12 |
| D-013 | Blend External Value Sources onto the DP Curve, Never Replace It | 2026-07-18 |
| D-014 | Two-Stage Layered Experiment Bucketing | 2026-07-18 |
| D-015 | Derive Model State on Read Rather Than Materializing It | 2026-07-26 |
| D-016 | A Model Ships Dark Until It Passes an Explicit Numeric Gate | 2026-07-26 |
| D-017 | Fail Loud Rather Than Serve a Plausible Wrong Answer | 2026-07-25 |
| D-018 | Unverified Sessions Keep the Short Expiry | 2026-07-20 |
| D-019 | Prepare the Trade, Never Fabricate the Execute Path | 2026-07-25 |
| D-020 | Analytics Omits Untrustworthy Data Rather Than Reporting It | 2026-08-06 |
| D-021 | Capture ESPN's HttpOnly Cookie From the Native Store, Not Injected JS | 2026-08-08 |
| D-022 | MFL Draft Room Names Resolve in Four Ordered Tiers, and Never Render a Bare Id | 2026-08-10 |
| D-023 | Draft-Pick Value Is Subset- and Filter-Independent, Behind a Kill Switch | 2026-08-10 |
| D-024 | The Mock-Draft "Run" Is Engine-Internal, and Two Constants Are Load-Bearing in Opposite Directions | 2026-08-10 |
| D-025 | The Trade Card Owns Its Disposition, and Absence Is the Card's Odds Design | 2026-08-11 |
| D-026 | `ranking_method` Is Written at the Point of Use, First-Use Wins | 2026-08-11 |
| D-027 | A Failed Trade Search Renders a Named, Persistent Deck State; `job.error` Is Mapped, Never Echoed | 2026-08-11 |
| D-028 | The Legacy `?league=` Invite Form Is Parsed Forever; the New Path 302s Into the Existing Landing | 2026-08-11 |
| D-029 | Post-Auth Routing Keys Off the `no_league` Sentinel, Never Off a User Flag | 2026-08-11 |
| D-030 | RN-Core `Clipboard` Over `expo-clipboard`; Delete the Mobile Disposition Wrapper, Keep the Route | 2026-08-11 |
| D-031 | The Reserved `sleeper_send_*` Names, and the Client/Server Split of the Send Funnel | 2026-08-11 |
| D-032 | The Tour's Sign-Off Gate Is Beat Identity, Not Step Count | 2026-08-11 |
| D-033 | Request the Celebration First, Consume It Only on Success | 2026-08-11 |
| D-034 | #298 Single-Pin Recovery: the Deck Takes the Lead Slot, It Does Not Stack | 2026-08-11 |
| D-035 | #298 Ships Without a New Feature Flag | 2026-08-11 |
| D-036 | League Roster Tiles: 32pt via an Opt-In Prop, Not the Literal 30pt | 2026-08-11 |
| D-037 | League Drill-In Back Affordance Lives on the Stack Header, Tab-Root Only | 2026-08-11 |
| D-038 | Adopt `league_team_opened` for the League Drill-In; Add Only an Exit Event | 2026-08-11 |
| D-039 | Tier-Board Share Routes Get a Flag Whose Resting State Is OFF | 2026-08-11 |
| D-040 | T1 Registers Four Analytics Names and Defers Four; the File Is Not Final | 2026-08-11 |
| D-041 | Unlock Is Per-Method and Reads the Board, Not the Event Stream | 2026-08-11 |
| D-042 | First-Unlock Fan-Out Is Suppressed by a Backfill, Not a Special Case | 2026-08-11 |
| D-044 | A Position Filter Means That Position: Rules A and B Removed | 2026-08-12 |
| D-043 | Shared Display Vocabularies Are Derived From One Constant | 2026-08-11 |
| D-045 | An Inbox Row Is Written Beside the Push, Never Inside the Dispatcher | 2026-08-13 |
| D-046 | The Bell Carries Receipts, Not Prompts; the Invite Ask Lives in the Empty State | 2026-08-13 |
| D-047 | Device-Auth Programme: The Five Operator Defaults Ratified | 2026-08-13 |
| D-048 | `expo-updates` Is Not Adopted; the Carve-Out It Assumed Does Not Exist | 2026-08-13 |
| D-049 | Roster-History Capture Runs On-Sync as Co-Primary; the Table Is the Contract | 2026-08-14 |
| D-050 | Foreign/Stale Deck Impression IDs Are Counted-and-Dropped, Never 4xx'd | 2026-08-14 |

---

## Decision Template (for new entries)

```markdown
## D-NNN — <Short title>
**Date:** YYYY-MM-DD
**Context:** Why this came up — what triggered the choice.
**Decision:** What was chosen.
**Alternatives considered:** The 1–3 paths not taken and why.
**Consequences:** What follows. What it costs. What it enables.
**Status:** Active | Superseded by D-NNN | Reversed
**Related ADR:** (optional, if a formal `docs/adr/NNNN-*.md` exists or is planned)
```

Number sequentially. Never reuse a number even if a decision is fully superseded — mark it `SUPERSEDED by D-NNN` and keep the original.

For substantial decisions (large refactors, vendor changes, API surface changes), also create a formal ADR in [`../docs/adr/`](../docs/adr/) and cross-reference from here.

## D-047 — Device-Auth Programme: The Five Operator Defaults Ratified
**Date:** 2026-08-13 (operator, in chat: "Aligned with the recommendations. Proceed")
**Context:** The Plan (`docs/plans/device-side-platform-auth-plan-2026-08-13.md` §1) put five open items to the operator with recommended defaults, so a single yes could start work.
**Decision:** All five defaults ratified: **OI-9** — run the expo-updates evaluation spike now, in parallel with S0/S1; the spike's written memo owns the Gate C decision (this ratification is *not* the OI-9 decision itself). **OI-3** — single-holder device model. **OI-14** — accept the LLD's deviation from PRD:144: `readEnvelope` returns `null` on a `user_id` mismatch; only session establishment wipes. **OI-4** — accept-and-monitor the old-build-reinstall custody downgrade; M1 non-zero is "investigate," never "page." **OI-15** — revocation stays behind a verified session for release 1; documented recovery is "sign back in, then disconnect"; revisit before public release.
**Alternatives considered:** Per the Plan §1's table, each row names the rejected alternative and its cost.
**Consequences:** S0 starts immediately (three lanes per Plan §13). OI-3/OI-4/OI-15 must be **re-confirmed in writing at Gate F** before the allowlist widens beyond the operator — ratified defaults may not silently stand in for that later call (Plan §1). The OI-9 spike session's prompt excludes Plan §10's recommendation, and its memo must name what evidence would have concluded "adopt first" (Plan §10 hygiene rules).
**Status:** Active.

## D-048 — `expo-updates` Is Not Adopted; the Carve-Out It Assumed Does Not Exist
**Date:** 2026-08-13 (Gate C, OI-9 — independent spike)
**Context:** The PRD listed OTA as a thing to evaluate **first**, and three artifacts repeated that it "addresses R1–R6 as a class" while the device-credential programme addresses only R1–R2. That sentence is what gave OI-9 its standing as upstream of the whole programme.
**Decision:** **Do not adopt.** Not before S3, not in release 1. Full reasoning: [`../docs/plans/device-side-platform-auth-oi9-expo-updates-memo-2026-08-13.md`](../docs/plans/device-side-platform-auth-oi9-expo-updates-memo-2026-08-13.md). Adoption would delete PRD §8's non-negotiable "compiled into the binary, never read from a server response," so it is a **PRD amendment, not a config change**.
**Alternatives considered:** *Adopt first* — rejected; see the memo's four disconfirming facts, each checkable, any one of which flips the verdict. *Adopt later with a transport carve-out* — **rejected as impossible**: the unit of replacement is the whole JS bundle, and the only real carve-out (moving the allowlist and op set to native) would destroy the §6.1 test harness.
**Consequences:** Gate C's OI-9 box is discharged. **Three corrections to the Plan's own §10**, which the orchestrator authored and the independent evaluation overturned: the predicted carve-out is impossible; the trusted-computing-base argument was overstated (Render is the adversary, Expo/EAS is a different trust domain — the accurate cost is that OTA makes the operator's existing build-time reach *instant, silent, and invisible in the version string*, and signing cannot help because it is the same principal on the same laptop, nor stop a signed rollback); and OTA obsoletes **none** of the old-binary machinery, because `EXUpdatesEnabled` is `false` in every shipped build so it can never reach `1.13.2`. Sequencing: OTA is native, so it could not benefit anything before S6 and never belonged on Gate C at all. Re-open trigger: **the first public App Store release**, where the memo's disconfirming fact 3 flips; memo §9 makes that re-open executable. Provenance gap logged as **OI-22** — the R-list cannot be verified against any source in the repo.
**Status:** Active.

## D-049 — Roster-History Capture Runs On-Sync as Co-Primary, and the Table Is the Contract
**Date:** 2026-08-14 (ADR-011, #46 Wrapped P0; operator decisions YR-1…YR-8)
**Context:** YR-1 ruled "the weekly job is the contract and the thing that must not be allowed to miss," reading on-sync capture as an optional extra. But whether the declared Render crons actually fire is an **open question** (`docs/architecture.md:230` claimed a cron that was reverted same-day; the operative value-snapshot mechanism is the hourly-tick guard), and a cron reading `league_members` would stamp client-posted, possibly months-old rosters with this week's period key — fabricating history.
**Decision:** **The table is the contract, not either writer.** Three triggers feed one precedence-aware upsert: on-sync (co-primary — the only mechanism whose correctness is independent of the scheduler question), the daily-tick weekday `>=` gate on a daemon thread, and a manual CRON_SECRET route. `source='weekly'` rows double as the cron liveness detector. Precedence not recency: `weekly` (server-fetched, orphans included) outranks `sync` (client-posted, ownerless teams dropped).
**Alternatives considered:** *Weekly-only via a new dedicated cron, gated on the cron migration* — rejected: would eat the Week-1 window, on this repo's documented history of dedicated crons getting reverted or never provisioned (twice). *An hourly-tick fallback guard as a third scheduled trigger* — dropped in the final reconciliation: hourly and daily ticks are the same blueprint, perfectly correlated; the guard buys zero coverage. *Last-write-wins upsert* — rejected: a Friday app-open would silently delete the swept week's orphan teams and break YR-6.
**Consequences:** Capture ships now, before Gate 0's scheduler answer, and degrades honestly under either outcome. The deviation from YR-1's literal reading is operator-blessed via the build brief (which also added YR-8: the sweep fetches server-side on all four platforms, and an expired ESPN-private cookie becomes a visible `espn_reconnect` bell row, never a silent gap). Full record: [`adr-011`](../docs/adr/adr-011-league-state-history-is-append-only.md); premise checks in [`../docs/plans/dynasty-year-in-review/scope.md`](../docs/plans/dynasty-year-in-review/scope.md).
**Status:** Active.

## D-050 — Foreign/Stale Deck Impression IDs Are Counted-and-Dropped, Never 4xx'd
**Date:** 2026-08-14
**Context:** LLD review found `_save_deck_outcome_safe` wrote a `deck_outcomes` row (and, under `deck.taste_vectors`, mutated the *impression owner's* taste vector) for any client-supplied ≤64-char `impression_id` — a stale or foreign id poisoned another user's personalization. The fix had to pick a rejection style and a recency bound.
**Decision:** The helper takes a required `acting_user_id` (route-resolved, never a body field) and writes only when the impression exists, is owned by the acting user, and was served ≤30 days ago (`_DECK_OUTCOME_MAX_AGE_DAYS`, code constant). Everything else is **silently dropped and counted** — routes keep their exact status codes (always-200 for the /api/events side-channel, unchanged 200/201 elsewhere); rejects surface as `deck_outcome_rejects` on `GET /api/admin/analytics/health` (in-process, reset-on-deploy, same pattern as the ingest health counters).
**Alternatives considered:** *4xx on invalid ids* — rejected: `impression_id` is an optional additive telemetry field; failing the parent action (a swipe, a real Sleeper/MFL/ESPN send) over telemetry inverts priorities, and the analytics convention here is accept-and-drop. *Config-key recency bound* — rejected: no operational reason to tune it without a deploy; a constant is greppable and simpler.
**Consequences:** One extra indexed-PK SELECT per outcome write (trivial at FTF QPS; the taste path already did this read). `/api/events` outcome side-channel now requires a live session token — dead-token batches drop their deck signals (counted as `no_user`) instead of writing unattributed labels. Late-arriving offline signals older than 30 days are lost by design. Supersedable by the fuller trade-relevance-engine P0-3 work when that initiative lands.
**Status:** Active.

## D-051 — Nightly Work Is a Registered Pass With a Durable Row; Kill Switches Live in `model_config`, Not `features.json`
**Date:** 2026-08-14 (trade-relevance P0, build step B1; HLD D1)
**Context:** `daily-tick` ran **seven** inline blocks — push scans, replenishment, F8 eval, F6 refit, the players-refresh guard, a class-load monitor, and (as of today) the ADR-011 roster snapshot — in one function on the single web worker. An exception mid-way silently skipped everything after it, and nothing durable recorded which passes ran: "did eval run last night?" was answerable only by reading logs. The retention endpoint that P0 planned to prune the new ledger with **does not exist**.
**Decision:** Each block becomes a registered `PassSpec` writing one `cron_pass_runs` row per `(pass, run_date)`, claimed through `uq_pass_run`. Stale-`running` recovery is mandatory (a mid-pass OOM must not wedge the pass for the day). Kill switches are `cron.pass_disabled.<name>` rows in **`model_config`**, read by `relevance.config.valve()` — deliberately exempt from the D10 resolver, absent ⇒ the pass runs. Retention ships as `database.prune_cron_pass_runs()` wired into `_cleanup_loop`.
**Alternatives considered:** *More try/except blocks around the inline bodies* — rejected: that is the current pattern and its failure mode is precisely silent partial execution. *Kill flags in `config/features.json`* — rejected on two counts: `feature_flags.py` silently drops undeclared keys and defaults every flag False, so a "default ON" pass flag would either break the all-False convention or, on one missing declaration, silently stop the **pushes** pass; and `features.json` is baked into a deploy, while a kill switch must act now. Inverted polarity (`pass_disabled`, absent ⇒ runs) means a typo fails safe.
**Consequences:** Ledger failures **fail open** — the pass runs anyway — because a bookkeeping bug must never silence nightly pushes; what makes that safe is a registration-time assert that every push kind a pass dispatches carries a frequency cap or a dedup key. The Aug-25 `season_start` fan-out is now its own `must_complete_today` pass, and `pushes` keeps a mirrored `is_aug25` early-return so a kickoff recipient still gets nothing else that day — without that mirror the split would have double-sent on one day a year, which the T-1 equivalence fixtures now pin. A second same-day tick POST legitimately omits `replenish` (documented in `api-reference.md` + runbook). Two spec errors recorded in the LLD as ⟨BUILD-AMENDED⟩.
**Status:** Active. Branch `feat/trade-relevance-p0`, unmerged; both user-affecting flags dark.

## D-052 — Aggregated Flag Signal Demotes, It Never Gates — and a Zero Global Rate Must Short-Circuit
**Date:** 2026-08-14 (trade-relevance P0, build step B6; HLD D11)
**Context:** A "bad trade" flag helped exactly one user once: it suppressed that card for that person while the same *class* of suggestion kept serving to everyone else. Exposure-normalised aggregation fixes that, but a rate computed on tiny exposure counts is noise, and this repo's standing guardrail is that quality gates stay hand-authored and editorial.
**Decision:** Nightly aggregation writes `deck_class_stats` per (archetype, shape_bucket, receive_value_band); serving applies it as a **bounded multiplier clamped to [0.5, 1.0]**, never a veto. Classes under 200 trailing-30d viewed impressions get exactly 1.0. Attribution rides the impression-keyed `not_interested` outcome row, **not** `bad_trade_flags` (which carries neither `impression_id` nor `trade_hash`); the flag route was verified to be that action's sole writer, pinned by a source-scan test. The applied multiplier is frozen into `features_json` per HLD §2.3 so replay never reconstructs table state.
**Alternatives considered:** *Hard-dropping high-flag classes* — rejected: that is a gate change decided by noise (3 flags on 40 exposures would silence an archetype league-wide), and gates are editorial by guardrail. The operator report instead lists demoted classes **with their n**, so a human can promote one to a real hand-authored gate in `_consider`.
**Consequences:** A load-bearing guard the formula did not originally have: **ρ ≤ 0 must short-circuit to 1.0**. With a zero global flag rate, `ρ/shrunk` evaluates `0/1e-9` and pins *every class on the platform* at the floor — a fleet-wide silent demotion from a healthy input. Aggregation is keyset-paginated with a 500k-impression ceiling; truncation is safe because `impression_id` is uuid4, so ordering by it samples uniformly at random — a truncated run under-demotes and can never over-demote. Empty or corrupt stats ⇒ every multiplier 1.0 ⇒ byte-identical serving.
**Status:** Active. Flag `deck.class_demotion` dark; ships only after the pass runs ≥7 days and the operator reviews the demoted-class report.
