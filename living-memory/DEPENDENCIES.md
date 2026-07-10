# Technical Dependencies & Their Quirks — Fantasy Trade Finder

> **Purpose:** the catalog of external systems this project depends on, plus their known weirdness. Where DEPENDENCIES asks "what does this break in surprising ways?", [`THIRD_PARTY.md`](THIRD_PARTY.md) asks "who do we call when it breaks and what's it costing?"
>
> **Read at:** before designing a new integration, before debugging an external-data issue, before any unattended run that hits an external API.
> **Write at:** the moment a quirk is discovered.
>
> Companion files: [`THIRD_PARTY.md`](THIRD_PARTY.md), [`../docs/runbook.md`](../docs/runbook.md), [`GOTCHAS.md`](GOTCHAS.md).

---

## Table of Contents
- [2026-05-21](#2026-05-21)
- [Local Conventions That Become Dependencies If Violated](#local-conventions-that-become-dependencies-if-violated)
- [Outstanding / Known Gaps](#outstanding--known-gaps)

---

## 2026-05-21

### Python runtime
- **Python 3** required (see `.python-version` for exact). Earlier minor versions can fail on type hints used in newer modules.
- **`requirements.txt`** is not pinned to exact versions. Flask + SQLAlchemy minor updates can shift behavior; if a query suddenly returns differently, check pip freeze.
- **No virtualenv enforced.** System Python or any venv works; reproducibility relies on `requirements.txt` accuracy.

### Sleeper API
**Role:** identity provider + league/roster/player data source.
- **Public API, no auth required.** All endpoints are GET-only and don't need API keys.
- **Rate limits not documented.** In practice, generous; we haven't hit limits at single-user scale.
- **Player database is 3,888+ entries.** Cached locally in `.sleeper_players_cache.json`. Refresh: empty cache OR >24h old.
- **Player IDs are stable strings**, but display names occasionally have non-ASCII characters (accents); persist exactly as received.
- **Roster `players` field is a list of player IDs as strings.** Don't assume integers.
- **Traded picks**: `/v1/league/<id>/traded_picks` returns picks that have moved. Must overlay onto the full pick grid; raw response doesn't include picks that haven't moved.
- **League rosters can have null entries** for empty slots. Handle defensively.
- **Username case-sensitivity:** lookups via `/v1/user/<username>` are case-insensitive on Sleeper's end, but downstream code may treat the response username as canonical (lowercased). Don't assume the user typed it the way Sleeper returns it.

### DynastyProcess CSV (consensus dynasty trade values)
**Role:** initial Elo seeding for the player base.
- **Source:** GitHub-hosted CSV from the DynastyProcess project.
- **660 player rows, 636 with value > 0.** Bench/depth players have value 0.
- **Player name mismatches with Sleeper.** DynastyProcess uses different naming conventions for some players (apostrophes, abbreviated initials, edge cases). The script `dump_mismatches.py` identifies these; manual mapping needed.
- **Update cadence is external** — the CSV updates weekly during the season, less frequently in offseason. Our cache doesn't auto-refresh; refresh manually before each major data event.
- **Value scaling:** value 10000 ≈ Elo 1800 (elite); value 5000 ≈ Elo 1500 (solid starter); value 0 ≈ Elo 1200 (bench/depth). Mapping in `data_loader.py`.

### Anthropic Claude API (optional)
**Role:** smart matchup selection in `smart_matchup_generator.py`.
- **Optional.** App works without `ANTHROPIC_API_KEY` — falls back to algorithmic selection.
- **Per-call cost is small** (~$0.001 per matchup decision with Haiku); aggregates if heavy usage.
- **Rate limits:** standard Anthropic API limits apply. Single-user app doesn't approach them.
- **Model choice:** code currently uses a specific model; verify the model name is still valid before subscribing or running heavily.

### SQLite (`trade_finder.db`)
**Role:** local persistence.
- **Two file locations** — `data/trade_finder.db` (canonical) AND `trade_finder.db` at repo root (legacy duplicate). Code currently reads from `data/`; root file is residual. Cleanup pending — see [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) Q-001.
- **No migration framework.** Schema changes require manual ALTER or DROP/CREATE in `database.py`. Don't ship schema changes without coordinating with anyone else who has a local DB.
- **WAL mode not enabled.** Concurrent reader/writer access can lock — single-process for now.
- **Postgres-swappable** via `DATABASE_URL` env var. Untested in production; will need at least one full run-through before relying on it.

### macOS port 5000
- **AirPlay Receiver occupies port 5000** by default on macOS Monterey+.
- **Kill via:** `lsof -ti:5000 | xargs kill -9` (or disable AirPlay Receiver in System Settings).
- **Flask doesn't fail with a clear message** — it just hangs or errors cryptically. Easy to misdiagnose.

### Expo / React Native
- **Mobile dev:** `cd mobile && npx expo start --tunnel --clear`. Tunnel mode is slower but works around local-network firewall issues.
- **Mac IP for direct LAN testing:** `192.168.1.88` (check current via `ifconfig en0 | grep "inet "`).
- **Expo Go app:** scan QR. Iteration is fast but native modules can drift.
- **No EAS Build configured** — production iOS/Android deployment pending.

### Browser extension (MV3)
- **Manifest V3 required** by both Chrome and Edge.
- **Service worker (not background page).** Long-running operations need persisted state.
- **Sleeper page DOM is the integration surface.** If Sleeper updates their DOM, extension content scripts break — no API contract.

---

## Local Conventions That Become Dependencies If Violated

- **DB at `data/trade_finder.db`.** Don't move it; multiple modules hardcode the path.
- **`.sleeper_players_cache.json` at repo root.** Don't move; `server.py` looks here.
- **`config/features.json`** drives feature flags consumed by both backend AND clients. Don't rename or relocate without coordinating all clients.
- **Port 5000 is the dev contract.** Mobile + web + extension all assume `http://0.0.0.0:5000` (or `localhost:5000` / `192.168.1.88:5000`).
- **`docs/CLAUDE.md` update-trigger table.** Any change that touches the listed files must update the corresponding doc.

---

## Outstanding / Known Gaps

- Anthropic model name pinning — currently hardcoded; revisit when newer models release.
- DynastyProcess update workflow — no automated refresh; relies on manual.
- Postgres migration: every quirk above is SQLite-specific; the Postgres equivalents need their own audit when that switch happens.
- Sleeper API doesn't expose rate limit headers; we operate on blind faith. If they tighten, add backoff logic.
