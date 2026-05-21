# Fantasy Trade Finder — Project Notes for Claude

Dynasty fantasy football trade-finding app. Sleeper-based login, Elo ranking via 3-player matchups, mutual-gain trade discovery.

## Coding guidelines

Follow [docs/coding-guidelines.md](docs/coding-guidelines.md) when writing or editing code. Four principles, in priority order:

1. **Think before coding** — surface assumptions and tradeoffs; ask when unclear.
2. **Simplicity first** — minimum code that solves the problem; no speculative abstractions.
3. **Surgical changes** — every changed line traces to the request; no drive-by refactors.
4. **Goal-driven execution** — define verifiable success criteria; loop until met.

Bias toward caution over speed; use judgment for trivial tasks.

## Stack

- **Backend:** Python 3 / Flask (`backend/`), SQLAlchemy Core, SQLite (`trade_finder.db`), swappable to Postgres via `DATABASE_URL`
- **Web frontend:** Vanilla HTML/CSS/JS in `web/`
- **Mobile:** React Native / Expo in `mobile/`
- **Browser extension:** Chrome/Edge MV3 in `extension/`
- **Skills:** `feature-evaluator/` and `project-reorganizer/` (Claude Code skills used in this repo)
- **Optional AI:** Anthropic Claude API for smart matchup selection (env `ANTHROPIC_API_KEY`)

## Entry points

- `run.py` — Flask dev server on port 5000
- `mobile/App.tsx` — Expo entry
- `web/index.html` — single-page web app
- `extension/manifest.json` — MV3 extension

## Reference docs (keep current)

Anyone — human or Claude — making changes is expected to keep `docs/` in sync. Quick map:

| If you change… | Update… |
|---|---|
| `backend/database.py` schema | [docs/data-dictionary.md](docs/data-dictionary.md) |
| `backend/server.py` routes | [docs/api-reference.md](docs/api-reference.md) |
| Env vars / `config/features.json` / `model_config` keys | [docs/config-reference.md](docs/config-reference.md) |
| Tier colors, K-factors, thresholds, enum strings used by multiple clients | [docs/cross-client-invariants.md](docs/cross-client-invariants.md) |
| Backend module wiring or data flow | [docs/architecture.md](docs/architecture.md) |
| New domain term in code or UI | [docs/glossary.md](docs/glossary.md) |
| Operational issue worth recording | [docs/runbook.md](docs/runbook.md) |
| Non-obvious architectural decision | new ADR in [docs/adr/](docs/adr/) |

See [docs/CLAUDE.md](docs/CLAUDE.md) for the full table of update triggers.

## Conventions

- Read `context.md` for project orientation; `docs/` is the source of truth for details.
- DB lives in `data/trade_finder.db` (and a duplicate at root for legacy reasons).
- `config/features.json` drives feature flags consumed by both backend and clients.
- Eval workspaces (`feature-evaluator-workspace/`, `project-reorganizer-workspace/`) are throwaway scaffolds — do not document or commit changes there casually.

## Common tasks

- Add API route → `backend/server.py`
- Tweak ranking math → `backend/ranking_service.py`
- Tweak trade generation → `backend/trade_service.py`
- Add mobile screen → `mobile/src/screens/` + register in `mobile/src/navigation/`
- Add web page → `web/*.html` (link from `index.html`)
