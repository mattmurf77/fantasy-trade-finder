# Decisions — Fantasy Trade Finder

> **Purpose:** day-to-day Architecture Decision Record (ADR) log. Each significant choice with: context → decision → alternatives → consequences. Formal ADRs (one-decision-per-file with author, date, and full context) live in [`../docs/adr/`](../docs/adr/); this file is the terser, cumulative version. Reference ADRs explicitly when applicable.
>
> **Read at:** before changing a major design choice. **Write at:** when you make one.
>
> Companion files: [`../docs/adr/`](../docs/adr/), [`MISTAKES.md`](MISTAKES.md), [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md).

---

## Table of Contents
- [D-001 — Sleeper as the Sole Identity Provider](#d-001--sleeper-as-the-sole-identity-provider)
- [D-002 — 3-Player Matchups Over 2-Player](#d-002--3-player-matchups-over-2-player)
- [D-003 — Elo Decomposition for 3-Player Rankings](#d-003--elo-decomposition-for-3-player-rankings)
- [D-004 — DynastyProcess CSV as Initial Elo Seed](#d-004--dynastyprocess-csv-as-initial-elo-seed)
- [D-005 — Anthropic Claude API as Optional Enhancement](#d-005--anthropic-claude-api-as-optional-enhancement)
- [D-006 — Vanilla Stack for Web Client](#d-006--vanilla-stack-for-web-client)
- [D-007 — SQLite First, Postgres-Swappable](#d-007--sqlite-first-postgres-swappable)
- [D-008 — In-Memory Ring Buffer Logger (No Log Files)](#d-008--in-memory-ring-buffer-logger-no-log-files)
- [D-009 — `docs/` as Source of Truth; Living-Memory Cross-References](#d-009--docs-as-source-of-truth-living-memory-cross-references)
- [D-010 — Karpathy Four Principles as Coding Discipline](#d-010--karpathy-four-principles-as-coding-discipline)
- [D-011 — Fix the Selector, Not the Elo Math](#d-011--fix-the-selector-not-the-elo-math)
- [D-012 — Affine Mapping of the DynastyProcess Scale onto Trade Value](#d-012--affine-mapping-of-the-dynastyprocess-scale-onto-trade-value)
- [D-013 — Blend External Value Sources onto the DP Curve, Never Replace It](#d-013--blend-external-value-sources-onto-the-dp-curve-never-replace-it)
- [D-014 — Two-Stage Layered Experiment Bucketing](#d-014--two-stage-layered-experiment-bucketing)
- [D-015 — Derive Model State on Read Rather Than Materializing It](#d-015--derive-model-state-on-read-rather-than-materializing-it)
- [D-016 — A Model Ships Dark Until It Passes an Explicit Numeric Gate](#d-016--a-model-ships-dark-until-it-passes-an-explicit-numeric-gate)
- [D-017 — Fail Loud Rather Than Serve a Plausible Wrong Answer](#d-017--fail-loud-rather-than-serve-a-plausible-wrong-answer)
- [D-018 — Unverified Sessions Keep the Short Expiry](#d-018--unverified-sessions-keep-the-short-expiry)
- [D-019 — Prepare the Trade, Never Fabricate the Execute Path](#d-019--prepare-the-trade-never-fabricate-the-execute-path)
- [D-020 — Analytics Omits Untrustworthy Data Rather Than Reporting It](#d-020--analytics-omits-untrustworthy-data-rather-than-reporting-it)
- [Decision Template (for new entries)](#decision-template-for-new-entries)

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
