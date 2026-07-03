# Low-Level Design — Fantasy Trade Finder

> **Purpose:** the mechanic's-eye view as living memory. Schemas, contracts, naming rules at the level Claude can implement directly. Authoritative database schema and API route detail live in [`../docs/data-dictionary.md`](../docs/data-dictionary.md) and [`../docs/api-reference.md`](../docs/api-reference.md); cross-client invariants in [`../docs/cross-client-invariants.md`](../docs/cross-client-invariants.md). This file points to those and adds living-memory aspects.
>
> **Read at:** before adding/changing a database table, API route, or cross-client constant. **Write at:** when conventions actually shift.
>
> Companion files: [`../docs/data-dictionary.md`](../docs/data-dictionary.md), [`../docs/api-reference.md`](../docs/api-reference.md), [`../docs/cross-client-invariants.md`](../docs/cross-client-invariants.md), [`HLD.md`](HLD.md).

---

## Table of Contents
- [Authoritative References](#authoritative-references)
- [Directory Layout](#directory-layout)
- [Naming Conventions](#naming-conventions)
- [Database Schema (Pointer)](#database-schema-pointer)
- [API Surface (Pointer)](#api-surface-pointer)
- [Cross-Client Invariants (Pointer)](#cross-client-invariants-pointer)
- [Code Conventions](#code-conventions)
- [Living-Memory File Schemas](#living-memory-file-schemas)
- [Tooling & Constraints](#tooling--constraints)

---

## Authoritative References

| Concern | Source of truth |
|---|---|
| Database tables and columns | [`../docs/data-dictionary.md`](../docs/data-dictionary.md) |
| HTTP API routes | [`../docs/api-reference.md`](../docs/api-reference.md) |
| Constants shared across clients (tier colors, K-factors, enums) | [`../docs/cross-client-invariants.md`](../docs/cross-client-invariants.md) |
| Domain vocabulary | [`../docs/glossary.md`](../docs/glossary.md) |
| Env vars / feature flags / `model_config` keys | [`../docs/config-reference.md`](../docs/config-reference.md) |
| Module wiring + data flow | [`../docs/architecture.md`](../docs/architecture.md) |

When you change something on the left, update the doc on the right. The per-trigger table in [`../docs/CLAUDE.md`](../docs/CLAUDE.md) is the canonical update-trigger checklist.

---

## Directory Layout

```
fantasy-trade-finder/
├── CLAUDE.md                     # operator's brief; points to docs/ and living-memory/
├── README.md                     # public project description
├── context.md                    # detailed orientation
├── run.py                        # Flask dev server entry
├── build.sh                      # deployment script
├── render.yaml                   # Render hosting config
├── requirements.txt              # Python deps
├── trade_finder.db               # SQLite DB (root; legacy)
├── backend/
│   ├── server.py                 # Flask routes
│   ├── database.py               # SQLAlchemy Core schema
│   ├── ranking_service.py        # Elo (2- and 3-player)
│   ├── trade_service.py          # mutual-gain generation
│   ├── smart_matchup_generator.py # Claude-powered selection
│   └── data_loader.py            # DynastyProcess → seed Elo
├── data/
│   └── trade_finder.db           # canonical DB location
├── web/                          # vanilla HTML/CSS/JS
├── mobile/                       # React Native / Expo
├── extension/                    # MV3 browser extension
├── config/
│   └── features.json             # feature flags
├── docs/                         # reference documentation
├── living-memory/                # this folder
├── feature-evaluator/            # custom Claude Code skill
├── project-reorganizer/          # custom Claude Code skill
└── scripts/                      # one-off scripts
```

---

## Naming Conventions

### Code
- **Python:** `snake_case` for files, functions, variables. `PascalCase` for classes.
- **JavaScript/TypeScript:** `camelCase` for variables, `PascalCase` for components. `kebab-case` for filenames in web/.
- **Routes:** `/api/<resource>/<action>` pattern. Use plural resource names (`/trades`, `/notifications`). Avoid `/api/get-trades` style.
- **Database tables:** `snake_case`, singular (`user`, `player`, `league`) or plural for join/event tables (`swipe_decisions`, `trade_decisions`).
- **Env vars:** `SCREAMING_SNAKE_CASE`. Document new ones in [`../docs/config-reference.md`](../docs/config-reference.md).

### Documentation
- ADR filenames: `NNNN-kebab-title.md` in `docs/adr/` (e.g. `0001-three-player-matchups.md`).
- `docs/` files: lowercase kebab. Living-memory files: UPPERCASE for foundational, kebab for supplementary.

---

## Database Schema (Pointer)

See [`../docs/data-dictionary.md`](../docs/data-dictionary.md) for full schema. Key tables (summarized):

- **`user`** — Sleeper user identity (user_id, username, last_seen)
- **`league`** — Sleeper league + season metadata
- **`player`** — denormalized Sleeper player + DynastyProcess value seed
- **`roster`** — user-league-player ownership
- **`elo_rating`** — per-user-per-player Elo with history
- **`swipe_decisions`** — pairwise comparison events (powers ranking)
- **`trade_decisions`** — like/pass on generated trade cards
- **`trade_card`** — cached generated trade cards
- **`trade_match`** — mutual-like matches between users
- **`notification`** — inbox events

DB lives in two places (legacy): `data/trade_finder.db` (canonical) AND `trade_finder.db` at repo root. Cleanup TBD — see [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md).

---

## API Surface (Pointer)

See [`../docs/api-reference.md`](../docs/api-reference.md) for full route detail. Quick map (from `../context.md`):

- **Session/Auth:** `POST /api/session/init`, `GET /api/session/ping`
- **Ranking:** `GET /api/trio`, `POST /api/rank3`, `POST /api/rankings/submit`
- **Trades:** `POST /api/trades/generate`, `GET /api/trades`, `POST /api/trades/swipe`, `GET /api/trades/liked`
- **Trade matching:** `GET /api/trades/matches`, `POST /api/trades/matches/<id>/disposition`
- **Notifications:** `GET/POST /api/notifications`, `POST /api/notifications/read-all`
- **Admin:** `GET/PUT /api/admin/config/<key>`
- **Misc:** `GET /api/league/coverage`, `POST /api/reset`, `GET /api/debug/log?n=100`

---

## Cross-Client Invariants (Pointer)

See [`../docs/cross-client-invariants.md`](../docs/cross-client-invariants.md). Examples of values that must stay in sync across backend + web + mobile + extension:

- Tier color hex codes (Elite, Solid, Bench, Depth, etc.)
- Elo K-factors (per interaction type)
- Slot type enum strings (`STARTER`, `BENCH`, `IR`, `TAXI`)
- Notification type strings
- Trade card disposition states (`pending`, `liked`, `passed`, `matched`, `accepted`, `declined`)

Changes to any of these MUST update [`../docs/cross-client-invariants.md`](../docs/cross-client-invariants.md) AND every client.

---

## Code Conventions

### Karpathy Four Principles (per [`../docs/coding-guidelines.md`](../docs/coding-guidelines.md))
1. **Think before coding** — surface assumptions and tradeoffs; ask when unclear.
2. **Simplicity first** — minimum code that solves the problem; no speculative abstractions.
3. **Surgical changes** — every changed line traces to the request; no drive-by refactors.
4. **Goal-driven execution** — define verifiable success criteria; loop until met.

### Specific patterns
- **Layer code is pure where possible.** `ranking_service.py` and `trade_service.py` operate on inputs + return outputs; persistence is wrapped at the route layer.
- **No magic numbers in service code.** Tunables go in `config/features.json` or `model_config` table. Document new keys in [`../docs/config-reference.md`](../docs/config-reference.md).
- **Use the debug ring buffer.** Backend code logs to the in-memory ring buffer (200 entries, accessible via `GET /api/debug/log?n=100`). No persistent log files.
- **DB calls via SQLAlchemy Core (not ORM).** Stays close to SQL; no migrations framework in use.

---

## Living-Memory File Schemas

See [`FORMAT.md`](FORMAT.md) for the strict spec. Headline:

```markdown
# <FileName> — Fantasy Trade Finder

> **Purpose:** <one sentence>
> **Read at:** <trigger>
> **Write at:** <trigger>
> Companion files: <list>

---

## Table of Contents
- [Section 1](#section-1)
- ...

---

## YYYY-MM-DD  (or topical section)

content...
```

Required: H1 with project suffix, purpose blockquote, Table of Contents, ISO dates, sequential IDs.

---

## Tooling & Constraints

- **Python 3** (see `.python-version` for exact). Currently runs on system Python; venv setup not enforced.
- **Dependencies:** `pip install -r requirements.txt`. Core: `flask`, `sqlalchemy`, `anthropic`.
- **No build step for backend.** Flask dev server via `python3 run.py`.
- **Web client has no build step** — vanilla files served by Flask.
- **Mobile client uses Expo** — `npx expo start --tunnel --clear`.
- **Browser extension is MV3** — load unpacked in Chrome/Edge.
- **Tests:** ad-hoc scripts (`dump_mismatches.py`, `tmp_check_db.py`, etc.). No pytest suite yet — see [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md).
- **Port 5000 conflict on macOS:** AirPlay Receiver uses it. Kill via `lsof -ti:5000 | xargs kill -9`. See [`GOTCHAS.md`](GOTCHAS.md).
