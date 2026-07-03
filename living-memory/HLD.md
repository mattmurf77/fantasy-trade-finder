# High-Level Design — Fantasy Trade Finder

> **Purpose:** the architectural bird's-eye view as living memory. *What the system is, what it does, what's in scope, what isn't.* Authoritative module-wiring detail lives in [`../docs/architecture.md`](../docs/architecture.md); this file is the cross-session summary.
>
> **Read at:** before architectural changes (new module, new client, restructuring data flow). **Write at:** when the architecture genuinely shifts.
>
> Companion files: [`../docs/architecture.md`](../docs/architecture.md), [`LLD.md`](LLD.md), [`../context.md`](../context.md).

---

## Table of Contents
- [What This Is](#what-this-is)
- [Scope](#scope)
- [Non-Goals](#non-goals)
- [System Architecture](#system-architecture)
- [Major Components](#major-components)
- [External Dependencies (technical)](#external-dependencies-technical)
- [Deployment Topology](#deployment-topology)
- [Key Flows](#key-flows)
- [Living-Memory Layer (this project)](#living-memory-layer-this-project)
- [Design Trade-offs at the System Level](#design-trade-offs-at-the-system-level)
- [Out-of-Scope / Won't Do](#out-of-scope--wont-do)

---

## What This Is
A dynasty fantasy football trade-finding app. Users log in via their Sleeper username, import their league rosters, rank players through a 3-player swipe interface (Elo-based), and then receive personalized trade card suggestions based on valuation mismatches between themselves and their leaguemates. Built for solo dynasty managers; the same engine supports both simulated and real-league trade matching.

## Scope
- **In scope:** Sleeper-based session/auth, league/roster import, 3-player Elo ranking, trade card generation, trade matching with real leaguemates, web + mobile + browser-extension clients.
- **In scope (planned):** tiered matchup engine (prioritize top ranks first), Postgres migration, production deployment.
- **Out of scope:** other sports, redraft leagues, in-tournament live tracking, sportsbook integration.

## Non-Goals
- Not a full Sleeper replacement — uses Sleeper as identity + data source.
- Not a full draft tool — trade-focused.
- Not a paid product yet — personal-use first, productization later.

---

## System Architecture

```
                     ┌────────────────────────────┐
                     │  Clients                   │
                     │  • Web (vanilla HTML/JS)   │
                     │  • Mobile (React Native /  │
                     │    Expo)                   │
                     │  • Browser ext (MV3)       │
                     └─────────────┬──────────────┘
                                   │ HTTP / JSON
                                   ▼
                     ┌────────────────────────────┐
                     │  Backend (Flask, port 5000)│
                     │  backend/server.py routes  │
                     └─────────────┬──────────────┘
                                   │
        ┌──────────────────────────┼───────────────────────────┐
        ▼                          ▼                            ▼
┌────────────────┐       ┌────────────────────┐      ┌─────────────────────┐
│ ranking_       │       │ trade_service.py   │      │ smart_matchup_      │
│ service.py     │       │ Mutual-gain trade  │      │ generator.py        │
│ Elo (2-player  │       │ generation + pack  │      │ (Anthropic Claude)  │
│ + 3-player)    │       │ weighting          │      │                     │
└────────┬───────┘       └─────────┬──────────┘      └──────────┬──────────┘
         │                         │                            │
         └──────────┬──────────────┴──────────────┬─────────────┘
                    ▼                              ▼
            ┌──────────────────┐         ┌─────────────────────┐
            │ database.py      │         │ data_loader.py      │
            │ SQLAlchemy Core  │         │ Sleeper API +       │
            │ → trade_finder   │         │ DynastyProcess CSV  │
            │   .db (SQLite)   │         │ → seed Elo ratings  │
            └──────────────────┘         └─────────────────────┘
```

---

## Major Components

| Component | Path | Role |
|---|---|---|
| **Flask app + routes** | `backend/server.py` | All API endpoints, Sleeper integration, session management, in-memory ring-buffer debug logger (200 entries) |
| **Database** | `backend/database.py` + `trade_finder.db` (SQLite) | SQLAlchemy Core table defs. Schema in [`../docs/data-dictionary.md`](../docs/data-dictionary.md) |
| **Ranking engine** | `backend/ranking_service.py` | Elo with 2-player (pairwise) and 3-player (full-rank) interactions; 3-player decomposes to 3 pairwise updates for 2.6× info per interaction |
| **Trade generation** | `backend/trade_service.py` | Mutual-gain trade discovery; team-outlook modifiers; positional preference scoring; package diminishing-returns |
| **Smart matchup generator** | `backend/smart_matchup_generator.py` | Claude-powered selection of ~10 candidate pairs; algorithmic fallback if no `ANTHROPIC_API_KEY` |
| **Data loader** | `backend/data_loader.py` | DynastyProcess CSV → initial Elo (value 10000 ≈ Elo 1800; value 0 ≈ Elo 1200) |
| **Web client** | `web/*.html` | Vanilla HTML/CSS/JS single-page app |
| **Mobile client** | `mobile/` | React Native / Expo; entry `mobile/App.tsx` |
| **Browser extension** | `extension/` | MV3 Chrome/Edge extension; entry `extension/manifest.json` |
| **Skills** | `feature-evaluator.skill`, `project-reorganizer.skill` | Custom Claude Code skills used in this repo |

Full per-route + per-table detail in [`../docs/api-reference.md`](../docs/api-reference.md) and [`../docs/data-dictionary.md`](../docs/data-dictionary.md).

## External Dependencies (technical)
See [`DEPENDENCIES.md`](DEPENDENCIES.md). High-level: Sleeper API (free, public), DynastyProcess GitHub CSV (free), Anthropic Claude API (optional, paid).

## Deployment Topology
- **Local dev:** `python3 run.py` → Flask on `http://0.0.0.0:5000`; SQLite at `data/trade_finder.db` (with legacy duplicate at root).
- **Mobile dev:** `cd mobile && npx expo start --tunnel --clear`; scan QR via Expo Go.
- **Production (planned):** Postgres via `DATABASE_URL` env var, hosted backend (Render config exists in `render.yaml`).

---

## Key Flows

### Flow A — User onboarding
1. User submits Sleeper username via web/mobile/ext client.
2. Backend `POST /api/session/init` fetches Sleeper user profile + dynasty leagues.
3. League/roster data persisted to SQLite via `database.py`.
4. Player cache (`.sleeper_players_cache.json`) refreshed if empty or >24h old.
5. Initial Elo ratings seeded from DynastyProcess CSV via `data_loader.py`.

### Flow B — Ranking a player trio
1. Client requests next matchup: `GET /api/trio`.
2. `smart_matchup_generator.py` proposes ~10 candidate trios; Claude (or fallback) picks the most informative one.
3. User submits a 3-player ranking: `POST /api/rank3`.
4. Ranking decomposes into 3 pairwise Elo updates; persisted to `swipe_decisions` table.

### Flow C — Trade card generation
1. Client requests: `POST /api/trades/generate`.
2. `trade_service.py` compares the user's ranking set against each leaguemate's roster.
3. Mutual-gain trades discovered (each side improves by their own valuation).
4. Trade cards persisted; surfaced via `GET /api/trades`.
5. User swipes like/pass: `POST /api/trades/swipe`. Like recorded; Elo updated based on the swipe signal.

### Flow D — Real-league trade matching
1. Both users like mirrored trade cards (A-likes-trade-X, B-likes-same-trade-X-from-other-side).
2. System surfaces the match: `GET /api/trades/matches`.
3. Either side accepts or declines: `POST /api/trades/matches/<id>/disposition`.

---

## Living-Memory Layer (this project)

```
INTENT             REALITY              MOTION                AUTHORITY           IDENTITY
──────────         ────────────         ──────────────        ───────────         ──────────────
CONTEXT.md ✓       HLD.md (here) ✓      CHANGELOG.md ✓        SOURCES.md ✓        BRAND.md ✓
GLOSSARY.md ✓      LLD.md ✓             HANDOFF.md ✓          PRACTICES.md ✓      SUBAGENT_PRINCIPLES.md ✓
DECISIONS.md ✓     DEPENDENCIES.md ✓    NEXT.md ✓
OPEN_QUESTIONS.md  TEST_LEDGER.md ✓     MISTAKES.md ✓
   ✓               THIRD_PARTY.md ✓     GOTCHAS.md ✓
```

All 17 patterns adopted on 2026-05-21. Cross-references existing [`../docs/`](../docs/) rather than duplicating. Pattern source: [Master Claude Code Best Practices](../../Master%20Claude%20Code%20Best%20Practices/HLD.md).

---

## Design Trade-offs at the System Level

- **SQLite first, Postgres later.** SQLite is fast for local dev and contains 3,888-player + multi-league data without overhead. Postgres migration via `DATABASE_URL` is unblocked but not exercised.
- **Sleeper as identity provider.** Trade-off: no account creation needed (huge UX win); we lose users without Sleeper accounts. Acceptable — dynasty is Sleeper-heavy.
- **DynastyProcess CSV for seeding.** Trade-off: depends on a third-party GitHub repo's update cadence. Mitigated by treating it as initial-seed only — user rankings drift from initial values via Elo.
- **Elo over more sophisticated models.** Trade-off: simpler math; less expressiveness. Pays back as the interaction model fits the UX (binary swipes / 3-player ranks).
- **3-player matchups over 2-player.** 2.6× more information per swipe; UX is slightly more cognitive load. Decomposes cleanly into pairwise updates, so the underlying math doesn't change.
- **Claude API optional.** App works without an API key (algorithmic matchup fallback). Pays back as a clean separation: AI is enhancement, not dependency.
- **In-memory debug logger only.** No persistent log files; everything via stdout + ring buffer. Trade-off: post-hoc forensics on crashed sessions is hard. Acceptable for personal-use scale.

---

## Out-of-Scope / Won't Do

- Other sports (basketball, baseball, etc.).
- Redraft / season-long leagues without dynasty assets.
- In-tournament live tracking or DFS lineup optimization.
- Direct sportsbook / FanDuel / DK API integration.
- Public productization (multi-tenant SaaS, billing, etc.) — re-evaluate post-launch of personal-use version.
