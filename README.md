# Fleeced — Dynasty Trade Finder

*Repo orientation. Last verified against the tree: 2026-08-18.*

A dynasty fantasy football app that builds your personal player valuations from quick
3-player matchups, then finds trades where both you and a leaguemate come out ahead.
Connect a Sleeper, ESPN, or MyFantasyLeague league; rank; get a deck of trade cards;
propose the good ones back into your real league without leaving the app.

- **Shipping name:** `Fleeced: Dynasty Trade Finder` (D-057). The repo, the backend
  service, and the iOS native folder still carry the older `fantasy-trade-finder` /
  `DTFDynastyTradeFinder` names — those are internal and deliberately not renamed.
- **Status:** backend live on Render; iOS app in TestFlight (v1.13.2). Not yet on the
  public App Store.

## How it works

1. **Connect a league** — Sleeper, ESPN, or MFL. No password for Sleeper (public API);
   ESPN and MFL use an in-app browser login with encrypted credential storage.
2. **Rank players** — order 3-player matchups. An Elo engine turns those comparisons
   into continuous valuations, seeded from DynastyProcess consensus values so there is
   no cold start. Manual drag boards, tier quick-set, and CSV import are alternatives.
3. **Find trades** — the deck engine compares your board against each leaguemate's and
   surfaces packages where both sides gain in their *own* value space.
4. **Act on it** — propose the trade directly into Sleeper or MFL, share it, or work it
   in the manual trade calculator. When both sides like the same trade it lands in Matches.

## Tech stack

| Layer | What | Where |
|---|---|---|
| Backend | Python 3.12 / Flask, SQLAlchemy Core, 182 routes | [`backend/`](backend/) |
| Database | SQLite locally (`data/trade_finder.db`); Postgres in prod via `DATABASE_URL`. 58 tables | [`backend/database.py`](backend/database.py) |
| Web | Vanilla HTML/CSS/JS, no framework or build step; served as Flask static | [`web/`](web/) |
| Mobile | React Native 0.81 + Expo SDK 54, TypeScript; EAS → TestFlight | [`mobile/`](mobile/) |
| Mobile screens | 31 screens wired through `RootNav` + `TabNav` | [`mobile/src/screens/`](mobile/src/screens/) |
| Extension | Chrome/Edge MV3, talks to `/api/extension/*` | [`extension/`](extension/) |
| Feature flags | JSON, read by backend and both clients; `FTF_FLAGS` env override | [`config/features.json`](config/features.json) |
| Optional AI | Anthropic API for smart matchup selection; algorithmic fallback if unset | `ANTHROPIC_API_KEY` |
| Data sources | Sleeper (read + GraphQL trade write), ESPN, MFL, DynastyProcess CSV | — |

## Repo layout

| Path | Files | What's in it |
|---|---|---|
| [`docs/`](docs/) | 614 | Reference layer — API, schema, config, ADRs, design system, plans, feedback items. Source of truth for *what the system is* |
| [`mobile/`](mobile/) | 448 | Expo app: 31 screens, components, state, API client, `tests/` structural checks, `.maestro/` (historical) |
| [`backend/`](backend/) | 352 | Flask app + 283 pytest files, plus `eval/`, `outlook/`, `scripts/`, `tools/` |
| [`screens/`](screens/) | 144 | Screen-capture library — PNG per screen per state, `manifest.json` is the authority. **Frozen at 2026-08-11** (D-056 retired the simulator) |
| [`mockups/`](mockups/) | 104 | Self-contained HTML design prototypes. Never shipped code, never cite as current behavior |
| [`archive/`](archive/) | 74 | Cleanup manifests, retired skill workspaces, worktree dirty-state patches |
| [`.claude/`](.claude/) | 52 | Repo-local Claude Code skills (36) + hooks/settings |
| [`qa/`](qa/) | 42 | Test-case scripts (api/db/e2e/perf), results, checklists, sim-run markers |
| [`living-memory/`](living-memory/) | 23 | Cross-session state — changelog, decisions, gotchas, handoff, next |
| [`web/`](web/) | 17 | SPA plus profile / player / FAQ / privacy / terms / style-guide pages |
| [`scripts/`](scripts/) | 17 | Offline calibration, backtests, test-data seeding |
| [`extension/`](extension/) | 12 | MV3 browser extension |
| [`config/`](config/) | 2 | `features.json`, `tester_allowlist.json` |
| [`.github/`](.github/) | 2 | CI (pytest, `tsc --noEmit`, testid-lint) + keep-warm workflow |
| [`githooks/`](githooks/) | 1 | `pre-push` gate (see CLAUDE.md § Conventions) |
| [`reference/`](reference/) | 1 | Competitor screenshots for teardowns — images gitignored |

Gitignored working dirs you will see locally but not in git: `data/` (the SQLite DB and
Sleeper player cache), `feedback-workspace/`, `staged-work/`, `secrets.local.env`.

## Entry points

| File | Runs |
|---|---|
| [`run.py`](run.py) | Flask dev server, port 5000 (`PORT` to override) |
| [`backend/server.py`](backend/server.py) | The Flask `app` itself — what gunicorn imports in prod |
| [`mobile/App.tsx`](mobile/App.tsx) | Expo entry |
| [`web/index.html`](web/index.html) | Single-page web app |
| [`extension/manifest.json`](extension/manifest.json) | MV3 extension |

## Local development

```bash
# backend
pip install -r requirements.txt -r requirements-dev.txt
python3 run.py                       # http://127.0.0.1:5000
python3 -m pytest backend/tests -q   # ~3,000 tests; see living-memory/TEST_LEDGER.md for the live count

# mobile
cd mobile && npm install
npx expo start
npx tsc --noEmit
```

Two things that bite:

- macOS AirPlay Receiver squats port 5000 — `lsof -ti:5000 | xargs kill -9`, or set `PORT`.
- Spaces in this repo's path break local `expo run:ios`; use the no-space clone.

Credentials go in `secrets.local.env` at the project root (gitignored, never committed) —
`CRON_SECRET`, `SLEEPER_TOKEN_KEY`, and friends. Never paste them into chat.

## Deployment

- **Backend:** push to `main` → Render auto-deploys per [`render.yaml`](render.yaml)
  (`build.sh` → gunicorn). Three cron services drive the push/notification ticks.
- **iOS:** `npx eas-cli build --platform ios --profile production --auto-submit` → TestFlight.

## Where to go next

| You want… | Go to |
|---|---|
| To make a change as a Claude session | [`CLAUDE.md`](CLAUDE.md) — conventions, gates, hard rules |
| Deeper product/architecture orientation | [`context.md`](context.md) |
| What the system *is* (routes, schema, config, design) | [`docs/README.md`](docs/README.md) |
| What changed recently and what's next | [`living-memory/`](living-memory/) |
| The feature/flag catalog | [`FEATURES.md`](FEATURES.md) |
| Operational how-to and failure modes | [`docs/runbook.md`](docs/runbook.md) |

## License

MIT — see [`LICENSE`](LICENSE).
