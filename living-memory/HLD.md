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
- [Win Now season pipeline](#win-now-season-pipeline)

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
| **League-write adapters** | `backend/{sleeper_write,mfl_write,espn_write}.py` | Real trade proposals into the user's league. All three propose routes split pick assets out of the mixed give/receive arrays and encode/verify them server-side against their own ground truth (Sleeper: `draft_picks` grid + live `traded_picks`, 2026-09-02 D-176); an unresolvable pick refuses the whole send. |
| **Database** | `backend/database.py` + `trade_finder.db` (SQLite) | SQLAlchemy Core table defs. Schema in [`../docs/data-dictionary.md`](../docs/data-dictionary.md) |
| **Ranking engine** | `backend/ranking_service.py` | Elo with 2-player (pairwise) and 3-player (full-rank) interactions; 3-player decomposes to 3 pairwise updates for 2.6× info per interaction |
| **Trade generation** | `backend/trade_service.py` | Mutual-gain trade discovery; team-outlook modifiers; positional preference scoring; package diminishing-returns |
| **Smart matchup generator** | `backend/smart_matchup_generator.py` | Claude-powered selection of ~10 candidate pairs; algorithmic fallback if no `ANTHROPIC_API_KEY` |
| **Data loader** | `backend/data_loader.py` | DynastyProcess CSV → initial Elo (value 10000 ≈ Elo 1800; value 0 ≈ Elo 1200) |
| **Receipts (offline grading)** | `backend/receipts_service.py` | Grades PAST served suggestions against subsequent consensus movement at 14/28/56d — the measurement loop, not a serving one. Reads frozen `deck_impressions` + `player_value_history`; writes only append-only `receipts_grades` / `receipts_grade_runs`. Runs off the request path (202 + daemon, daily-tick guard, backfill script). Flags `receipts.grading` / `receipts.screen`, both default off. **Isolation is the design**: no engine module imports it and nothing in generation or ordering reads a grade — that boundary is the Goodhart line and is guarded in both directions |
| **Web client** | `web/*.html` | Vanilla HTML/CSS/JS single-page app |
| **Mobile client** | `mobile/` | React Native / Expo; entry `mobile/App.tsx` |
| **Browser extension** | `extension/` | MV3 Chrome/Edge extension; entry `extension/manifest.json` |
| **Skills** | `feature-evaluator.skill`, `project-reorganizer.skill` | Custom Claude Code skills used in this repo |

Full per-route + per-table detail in [`../docs/api-reference.md`](../docs/api-reference.md) and [`../docs/data-dictionary.md`](../docs/data-dictionary.md).

**`backend/trade_policy.py` — the trade-policy evaluator (2026-09-04, dark).** A leaf module owning the answer to *"may this trade be served, and how good is it for these two managers?"*. It encodes [D-180](DECISIONS.md): consensus value is a **non-bypassable market-plausibility guardrail** rather than 30% of a blended objective, personal rankings are the primary ordering signal among the plausible trades, and ranking confidence — applied symmetrically to **both** managers for the first time — controls how far the floor may descend. Called from three places: v2's candidate loop, v3's candidate loop, and one server-side choke point on the final deck (so every post-generation mutation is covered). Ships behind two flags, both default off: `trade.valuation_telemetry` (snapshots, canonical concept ids, shadow evaluation, proposal and match attribution — additive writes only) and `trade.personal_market_policy_v1` (the evaluator actually gates and orders). `policy_variant` is recorded **orthogonally** to `model_arm`, so the three existing generators keep generating inside both variants and no fourth arm is created ([D-181](DECISIONS.md)).

### Full-roster evaluation (2026-09-04; dark)

Two new leaves, `trade_roster.py` and `trade_roster_adapter.py`, evaluate both final rosters using exact shared-slot allocation, usable depth, capacity and observed-input provenance. The server captures one snapshot after mutations and before market composition; enforcing gates hold progressive card publication. Existing impression/shadow stores carry evidence. Estimated templates cannot pass enforcement; no weekly forecast is claimed. See `docs/plans/post-trade-roster-evaluation/`.

Whole-team benefit extension (2026-09-04): `trade_roster.Context.card` calls pure `trade_outlook_utility` for both complete rosters, then `trade_mutual_benefit` for eligibility and ordering. Explicit outlook provenance is captured before inference. Current production requires supplied fresh point data; dynasty-only evidence cannot enable the strict gate. The worker evaluates after all package mutations, withholds provisional cards in enforcement mode and preserves market lane quotas. Collection lives under existing roster telemetry; `trade.mutual_benefit_v1` remains independently dark. See `docs/plans/trade-model-activation/validation.md`.

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
4. **Evaluation layer** (2026-08-21, flags `trade.breaker` / `trade.breaker_narrative`, [D-142](DECISIONS.md)): the deck now passes through a distinct stage between generation and serving — **generator arms → breaker evaluation → presentment → serving**. `backend/trade_breaker.py` scores each finished card from the *counterparty's* seat, stamps the verdict on the card (and into `deck_impressions.features_json` for calibration), and optionally renders one "their likely hesitation" sentence. It is architecturally a peer of `suggestion_telemetry.py`, not of the generators: it reads the finished deck, writes only its own attributes, and is structurally forbidden (grep guard) from being imported by any generator — so it can never influence what was generated or in what order. Flags off ⇒ never imported. Detail: `../docs/architecture.md` (`trade_breaker.py` row + the trade-card lifecycle), plan suite `../docs/plans/counterparty-breaker/`.
4b. **Memory layer, upstream of generation** (2026-08-22, flag `trade.negmem`, [ADR-015](../docs/adr/adr-015-negmem-soft-prior-not-fourth-filter.md)): where the breaker sits *after* the deck is final, negative-results memory sits *before* it. `backend/negmem.py` is a **leaf** — stdlib + flags + database only, no engine import in either direction — that derives on read: one bulk query per job builds an in-memory map of what this viewer has already turned down, keyed `(league-mate × reason family)`, and the job hands that one frozen map to every generator arm as a kwarg. The generators consult it as a **clamped soft multiplier**, so a repeatedly-rejected family ranks lower and never disappears; it adds no candidate, removes none, and changes no gate. Nothing is persisted, so deleting the source rows deletes the memory. Two layers ride the one map (the ranking multiplier, and the aggregate acceptance counts that finally feed gen_v2's long-unfed `acceptance_prior`), and every influence is stamped into `deck_impressions.features_json` — a soft prior nobody can see would be indistinguishable from a bug. The ON-condition is flag **∧** a per-league allowlist file; either half missing ⇒ byte-identical to today. Detail: `../docs/architecture.md`, plan suite `../docs/plans/negative-results-memory/`.
5. Trade cards persisted; surfaced via `GET /api/trades`.
6. User swipes like/pass: `POST /api/trades/swipe`. Like recorded; Elo updated based on the swipe signal.

### Flow D — Real-league trade matching
1. Both users like mirrored trade cards (A-likes-trade-X, B-likes-same-trade-X-from-other-side).
2. System surfaces the match: `GET /api/trades/matches`.
3. Either side accepts or declines: `POST /api/trades/matches/<id>/disposition`.

### Flow E — Mock-draft creation (per-platform ownership resolution, 2026-08-16 #328)
`POST /api/mock-draft` resolves real order + traded-pick ownership per platform, all inside the create route (the engine `mock_draft_service.py` stays I/O-free): Sleeper via the Draft Room's cached board (`draft_board_service.build_board` — the one platform read, at creation only); ESPN via the pick-assignment grid the ESPN Draft Room renders (`_assignment_grid` → `assigned_board`, DB-only); MFL via the normalized `draft_picks` store (`_mock_owned_pick_overlay`, ownership anchored to the original owner's slot in the seeded shuffle — the order itself is never invented). Every mock is stamped `ownership_source` ∈ `platform`|`user`|`partial`|`none` so any fallback is labeled, never silent. Wiring detail: `../docs/architecture.md` (mock_draft_service row); contract: `../docs/api-reference.md` § Mock draft.

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

---

## Win Now season pipeline

Implementation checkpoint 2026-09-04, D-183 / ADR-017: external weekly forecasts feed supported league scoring and legal lineups, then full-league paired season simulations and constrained search. Durable evidence/jobs and the mobile/web Win Now flow remain separate from dynasty generators and Elo feedback. The 2026-09-05 release configuration enables all three flags under explicit operator acceptance of exploratory evidence; parent integration review is complete, hosted CI/deployment verification is in progress, and calibration remains unproven. Authoritative [architecture](../docs/architecture.md#win-now-season-pipeline) and [build limits](../docs/plans/win-now/BUILD.md).

Offline historical validation now has an outcome collector and a conditional archived-prediction evaluator. No serving model or data-store wiring changes. [Protocol and source limitations](../docs/plans/win-now/HISTORICAL-VALIDATION.md).
