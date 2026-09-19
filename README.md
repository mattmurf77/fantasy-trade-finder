# Fleeced — Dynasty Trade Finder

Fleeced helps dynasty fantasy football managers build personal player valuations and find actionable trades. The [product overview](docs/product/overview.md) explains its goals and surfaces. Internal package/service names retain “Fantasy Trade Finder” where renaming would disrupt integrations.

## Start here

| Need | Read |
|---|---|
| Work with an LLM | [AGENTS.md](AGENTS.md), then `python3 scripts/session_context.py` |
| Session and priorities | [HANDOFF](living-memory/HANDOFF.md), [NEXT](living-memory/NEXT.md) |
| Architecture, API, schema, config | [Reference index](docs/README.md) |
| Initiatives | [Plans](docs/plans/README.md), [feedback index](docs/feedback/items/INDEX.md) |
| Operations/releases | [Runbook](docs/runbook.md), [workflow](docs/agent-workflow.md) |
| Flags | [config/features.json](config/features.json), [config reference](docs/config-reference.md) |

## Repository map

| Path | Purpose |
|---|---|
| `backend/` | Flask services, database access, ranking/trade engines, pytest |
| `mobile/` | React Native/Expo client and structural checks |
| `web/` | Vanilla HTML/CSS/JavaScript client, served by Flask |
| `extension/` | Chrome/Edge Manifest V3 extension |
| `config/` | Shared feature configuration |
| `docs/` | References, product/design material, initiative records |
| `living-memory/` | Compact session state and searchable decision/evidence logs |
| `scripts/`, `qa/` | Operator utilities/verification; read their instructions first |
| `screens/`, `mockups/` | Historical captures/design prototypes, never imported product code |
| `archive/` | Historical assets and retired tooling |

Use `git ls-files` for the tracked inventory; omit dependencies, generated data and scratch from routine discovery. [Historical feature waves](docs/plans/archive/2026/competitor-feature-waves.md) explain two older builds; current flags come from configuration.

## Local development

Use the version in [.python-version](.python-version). Keep Python dependencies in a project environment:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
PORT=5001 python3 run.py
```

`run.py` defaults to port 5000; `PORT` avoids the macOS AirPlay conflict. Local SQLite is `data/trade_finder.db`; production uses `DATABASE_URL`. Required credentials belong in gitignored `secrets.local.env`, never chat or commits. Native integrations require the appropriate development build; consult [mobile instructions](mobile/CLAUDE.md).

```sh
cd mobile
npm ci
npx expo start
```

## Verification and deployment

```sh
python3 -m pytest backend/tests -q
python3 qa/web/check_web_structure.py
python3 scripts/session_context.py --check
```

Mobile typecheck, test-ID lint, and `tests/check-*.js` suites run in [CI](.github/workflows/ci.yml), the executable check list. Manual runtime evidence refers to a specific TestFlight build. Maestro/simulator tooling is retired.

Pushing `main` triggers backend/web deployment through [render.yaml](render.yaml) and [build.sh](build.sh). iOS production builds go through EAS and App Store Connect. Follow [release gates](docs/agent-workflow.md#release-and-recovery); a build alone does not establish deployment or tester availability.

MIT — see [LICENSE](LICENSE).
