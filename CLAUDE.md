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
- **Skills:** project Claude Code skills live in `.claude/skills/` (feedback pipeline, feature-evaluator, project-reorganizer, project-architect, …); retired skill workspaces/bundles are in `archive/skill-workspaces/`
- **Optional AI:** Anthropic Claude API for smart matchup selection (env `ANTHROPIC_API_KEY`)

## Entry points

- `run.py` — Flask dev server on port 5000
- `mobile/App.tsx` — Expo entry
- `web/index.html` — single-page web app
- `extension/manifest.json` — MV3 extension

## Session memory (`living-memory/`) — read at start, write at end

`living-memory/` is the cross-session state layer. `docs/` is reference (what the system *is*); living-memory is motion (what changed, what's next, what bit us). **If the two ever conflict, `docs/` wins — and update both.**

**At session start, read these four** (2 minutes, no exceptions):

| File | Why |
|---|---|
| [living-memory/HANDOFF.md](living-memory/HANDOFF.md) | Where the last session stopped, what's half-done, what's blocking |
| [living-memory/NEXT.md](living-memory/NEXT.md) | The live priority queue |
| [living-memory/CHANGELOG.md](living-memory/CHANGELOG.md) | Top 2–3 entries only — recent shipped work |
| [living-memory/GOTCHAS.md](living-memory/GOTCHAS.md) | Skim before debugging anything weird |

**At session end, write back.** A session that changed code and left living-memory untouched is an incomplete session:

| If this happened… | Update… |
|---|---|
| You shipped, merged, or deployed anything | [CHANGELOG.md](living-memory/CHANGELOG.md) — new dated H2 at the top |
| You are stopping with work in flight | [HANDOFF.md](living-memory/HANDOFF.md) — **overwrite**, don't accumulate |
| Priorities moved, or you finished a queue item | [NEXT.md](living-memory/NEXT.md) — cap 7 active items |
| You made a non-obvious design choice | [DECISIONS.md](living-memory/DECISIONS.md) — next ID `D-011` |
| You lost >30 min to a quirk | [GOTCHAS.md](living-memory/GOTCHAS.md) — next ID `G-013` |
| You abandoned an approach | [MISTAKES.md](living-memory/MISTAKES.md) — next ID `M-005` |
| You hit something you can't resolve alone | [OPEN_QUESTIONS.md](living-memory/OPEN_QUESTIONS.md) — next ID `Q-016` |
| You ran the suite or a manual QA pass | [TEST_LEDGER.md](living-memory/TEST_LEDGER.md) |
| You added/bumped/removed a dependency | [DEPENDENCIES.md](living-memory/DEPENDENCIES.md) |

Format is specified in [living-memory/FORMAT.md](living-memory/FORMAT.md) — every file needs the purpose blockquote, a TOC matching its H2s, and ISO dates. Audit compliance with the `living-memory-format-check` skill. Full read-at/write-at table in [living-memory/README.md](living-memory/README.md).

**Long sessions:** don't bank the whole write-back for the end. After any merge, deploy, or hard-won debug, log it then — context runs out before sessions do.

**Two hooks in `.claude/settings.json` back this up.** A `SessionStart` hook injects HANDOFF + NEXT into context automatically, so the read half happens whether or not anyone remembers. A `Stop` hook warns once per session if any code file is newer than every file in `living-memory/` — it stays silent when memory is current. Neither blocks; they nudge. Review or disable via `/hooks`.

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
| Any UI in `web/`, `mobile/`, `extension/` | follow [docs/design/design-system.md](docs/design/design-system.md) + [docs/design/components.md](docs/design/components.md) |

See [docs/CLAUDE.md](docs/CLAUDE.md) for the full table of update triggers.

## Conventions

- **Always branch from `origin/main`** (2026-08-08): every new piece of work — bug fixes, features, agent worktrees — starts from a freshly fetched `origin/main`, never from whatever branch this checkout happens to be sitting on. Multiple sessions run concurrently in this repo and the checked-out branch is often stale. Ship = merge/push to `main` (Render auto-deploys; EAS → TestFlight).
- Read `context.md` for project orientation; `docs/` is the source of truth for details.
- DB lives in `data/trade_finder.db` (the stale legacy root copy was archived to `data/archive/` on 2026-06-10).
- `config/features.json` drives feature flags consumed by both backend and clients.
- **UI rules (Chalkline design system, ADR-004 + ADR-005):** all UI work uses the tokens in `docs/design/design-system.md` and the specs in `docs/design/components.md`; live reference at `web/style-guide.html`. Never: emoji as icons, gradients, glassmorphism/blur, Inter/Roboto/system font stacks, radius >8px (except specced pills), accents other than ice (actions) and flare (informational highlights only). Position/tier hexes are data encodings governed by `docs/cross-client-invariants.md`.
- **Credentials live in `secrets.local.env`** (project root, gitignored, never commit). Read keys from there (`CRON_SECRET` for `/api/feedback/admin` + `/api/cron/*`, optional `DATABASE_URL_PROD`, etc.) instead of asking the operator to paste secrets into chat. If a needed key is blank, ask the operator to fill it in that file.
- **Feedback button on every screen (#188):** every new user-facing mobile screen mounts `FeedbackFAB` by default — tab-stack screens are covered by the RootNav mount; root-stack pushes render their own `<FeedbackFAB activeScreen="<RouteName>" aboveTabBar={false} />`. Exceptions: modals/sheets and onboarding flows.
- **Feedback outputs:** durable non-code output for a feedback item's fix (PRD, plan, status, QA findings, screenshots) lives in `docs/feedback/items/<id>-<slug>/` (see its README; multi-ID fixes → lowest ID). Throwaway scratch goes in gitignored `feedback-workspace/<id>/`. Batches before item #64 remain in `docs/plans/feedback-batch-2..4/` as history.

## Common tasks

- Add API route → `backend/server.py`
- Tweak ranking math → `backend/ranking_service.py`
- Tweak trade generation → `backend/trade_service.py`
- Add mobile screen → `mobile/src/screens/` + register in `mobile/src/navigation/`
- Add web page → `web/*.html` (link from `index.html`)
