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
