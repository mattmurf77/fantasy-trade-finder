# .github/ — Notes for Claude

Two workflows. Nothing else lives here — no issue templates, no CODEOWNERS, no Dependabot.

## `workflows/ci.yml` — the only merge gate that runs automatically

Triggers on every `pull_request` and every push to `main`. Three cheap Ubuntu jobs:

| Job | Command |
|---|---|
| `backend-tests` | `python -m pytest backend/tests -q` (Python 3.12, `requirements.txt` + `requirements-dev.txt`) |
| `mobile-typecheck` | `npx tsc --noEmit` in `mobile/` (Node 20, `npm ci`) |
| `maestro-testid-lint` | `bash mobile/scripts/testid-lint.sh` |

Notes for anyone adding a job:

- **There is no iOS-simulator job and there will not be one** — no free macOS runner, and operator decision **D-056** (2026-08-15) retired Maestro/simulator work entirely. `maestro-testid-lint` is a static lint of `testID` references and was explicitly kept.
- The `mobile/tests/check-*.js` structural suites (~22 of them, `npm run test:<name>`) are **not** wired into CI. They are run by hand. Wiring them up is an open improvement, not a documented decision.
- Making these required checks on `main` is a repo-settings branch ruleset — an operator action, not something a workflow file can do.

## `workflows/keep-warm.yml` — production, not CI

Cron ping against the Render free-tier service so the next real request doesn't pay a
30–60s cold start (which would blow the onboarding time-to-first-trade-card budget).

**This workflow is the keep-warm switch.** Turn it off by disabling the workflow in the
GitHub Actions UI. The `onboarding.keep_warm` flag in `config/features.json` does **not**
gate it — that flag is reserved for future server-side warm affordances. Best-effort only:
Actions cron drifts, and scheduled workflows auto-disable after 60 days of repo inactivity.
Background: [`docs/runbook.md`](../docs/runbook.md) → "Render cold starts — keep-warm cron".

## Related, elsewhere

- Local pre-push enforcement: [`githooks/pre-push`](../githooks/) — install once per clone with `git config core.hooksPath githooks`.
- Current QA regime and what replaced the simulator lane: [`qa/README.md`](../qa/README.md).
