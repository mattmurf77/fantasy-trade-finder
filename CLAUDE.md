# Fantasy Trade Finder — Project Notes for Claude

Dynasty fantasy football trade-finding app. Elo ranking via 3-player matchups, mutual-gain trade discovery, real trade proposals written back into the user's league. Ships to users as **`Fleeced: Dynasty Trade Finder`** (D-057) — the repo, the Render service, and `mobile/ios/DTFDynastyTradeFinder/` keep their older internal names on purpose. Currently TestFlight-only (v1.13.2); backend live on Render.

Human-facing orientation (product summary, repo layout table, how to run it) is in [README.md](README.md). This file is the operating contract: conventions, gates, hard rules.

## Coding guidelines

Follow [docs/coding-guidelines.md](docs/coding-guidelines.md) when writing or editing code. Four principles, in priority order:

1. **Think before coding** — surface assumptions and tradeoffs; ask when unclear.
2. **Simplicity first** — minimum code that solves the problem; no speculative abstractions.
3. **Surgical changes** — every changed line traces to the request; no drive-by refactors.
4. **Goal-driven execution** — define verifiable success criteria; loop until met.

Bias toward caution over speed; use judgment for trivial tasks.

## Stack

- **Backend:** Python 3.12 / Flask (`backend/`), SQLAlchemy Core, 182 routes in `server.py`, 58 tables in `database.py`. SQLite at `data/trade_finder.db` locally; Postgres in prod via `DATABASE_URL`
- **Web frontend:** Vanilla HTML/CSS/JS in `web/` — no framework, no build step; Flask serves it as static
- **Mobile:** React Native 0.81 + Expo SDK 54 (TypeScript) in `mobile/`; 31 screens; EAS → TestFlight
- **Browser extension:** Chrome/Edge MV3 in `extension/`
- **League platforms:** Sleeper (read + GraphQL trade write), ESPN (`espn.*` flags, live), MyFantasyLeague (`mfl.*`, live). Fleaflicker is dark (`fleaflicker.link` false)
- **Skills:** 36 repo-local Claude Code skills in `.claude/skills/` — role skills (`eng-*`, `pm-*`, `mkt-*`, `an-*`, `ops-*`, `fin-*`) plus the `feedback`, `feature-evaluator`, `project-architect`, `project-reorganizer`, `living-memory-format-check` pipelines. `maestro-test` is present but **dead** — D-056 retired Maestro; do not invoke it. Retired skill workspaces are in `archive/skill-workspaces/`
- **CI:** `.github/workflows/ci.yml` — `pytest backend/tests`, `tsc --noEmit`, `mobile/scripts/testid-lint.sh`. The `mobile/tests/check-*.js` structural suites are `npm run`-only and **gate nothing yet** (open item in NEXT.md)
- **Optional AI:** Anthropic Claude API for smart matchup selection (env `ANTHROPIC_API_KEY`); algorithmic fallback when unset

## Entry points

- `run.py` — Flask dev server on port 5000 (`PORT` to override; macOS AirPlay squats 5000)
- `backend/server.py` — the Flask `app` object itself; what gunicorn imports in prod
- `mobile/App.tsx` — Expo entry
- `web/index.html` — single-page web app
- `extension/manifest.json` — MV3 extension
- `render.yaml` + `build.sh` — prod deploy (web service + 3 cron tick services)

## Repo map (tracked-file counts, 1,919 total)

`docs` 614 · `mobile` 448 · `backend` 352 · `screens` 144 · `mockups` 104 · `archive` 74 · `.claude` 52 · `qa` 42 · `living-memory` 23 · `web` 17 · `scripts` 17 · `extension` 12 · `config` 2 · `.github` 2 · `githooks` 1 · `reference` 1

Two of these are easy to misread — each has its own CLAUDE.md, read it before touching them:

- **`screens/`** — capture library of the real app, one PNG per screen per state. Written **only** by `mobile/scripts/screen-capture.sh`, and **frozen at 2026-08-11** since D-056 retired the simulator. `manifest.json` is the authority on what exists.
- **`mockups/`** — self-contained HTML design prototypes. **Never shipped code**; never import from it or cite it as current app behavior. A mockup revising an existing screen must embed that screen's real capture as its "before" pane.

## Session memory (`living-memory/`) — read at start, write at end

`living-memory/` is the cross-session state layer. `docs/` is reference (what the system *is*); living-memory is motion (what changed, what's next, what bit us). **If the two ever conflict, `docs/` wins — and update both.**

**Session start requires zero reads.** The `SessionStart` hook already injects HANDOFF, NEXT, the CHANGELOG top-2 entries, and the GOTCHAS index into context automatically. That injection is complete for orienting a session — never re-read HANDOFF.md, NEXT.md, or CHANGELOG.md at boot; you already have them.

**Pull on demand — read only when a specific need arises:**

| File | Read when… |
|---|---|
| [living-memory/GOTCHAS.md](living-memory/GOTCHAS.md) (full entry) | The injected index has a row matching your symptom — grep the file by ID |
| [living-memory/CHANGELOG.md](living-memory/CHANGELOG.md) (older entries) / `living-memory/archive/` | You need history past the injected top 2 |
| [living-memory/DECISIONS.md](living-memory/DECISIONS.md) | Before overturning a design choice |
| [living-memory/MISTAKES.md](living-memory/MISTAKES.md) | Before retrying an approach that may have been abandoned |
| [living-memory/OPEN_QUESTIONS.md](living-memory/OPEN_QUESTIONS.md) | Before asking the operator something — check it isn't already logged |
| [living-memory/TEST_LEDGER.md](living-memory/TEST_LEDGER.md) | Before claiming test posture (pass counts, coverage) |
| [living-memory/DEPENDENCIES.md](living-memory/DEPENDENCIES.md) | Before adding, bumping, or removing a dependency |
| [living-memory/HLD.md](living-memory/HLD.md) / [living-memory/LLD.md](living-memory/LLD.md) | Before architecture, schema, or route work — both also have `docs/` counterparts |

**At session end, write back.** A session that changed code and left living-memory untouched is an incomplete session. For ID'd files (D-/G-/M-/Q-), next ID = max existing + 1 — grep first:

| If this happened… | Update… |
|---|---|
| You shipped, merged, or deployed anything | [CHANGELOG.md](living-memory/CHANGELOG.md) — new dated H2 at the top |
| You are stopping with work in flight | [HANDOFF.md](living-memory/HANDOFF.md) — **overwrite**, don't accumulate |
| Priorities moved, or you finished a queue item | [NEXT.md](living-memory/NEXT.md) — cap 7 active items |
| You made a non-obvious design choice | [DECISIONS.md](living-memory/DECISIONS.md) |
| You lost >30 min to a quirk | [GOTCHAS.md](living-memory/GOTCHAS.md) |
| You abandoned an approach | [MISTAKES.md](living-memory/MISTAKES.md) |
| You hit something you can't resolve alone | [OPEN_QUESTIONS.md](living-memory/OPEN_QUESTIONS.md) |
| You ran the suite or a manual QA pass | [TEST_LEDGER.md](living-memory/TEST_LEDGER.md) |
| You added/bumped/removed a dependency | [DEPENDENCIES.md](living-memory/DEPENDENCIES.md) |

Format is specified in [living-memory/FORMAT.md](living-memory/FORMAT.md) — every file needs the purpose blockquote, a TOC matching its H2s, and ISO dates. Audit compliance with the `living-memory-format-check` skill. Full read-at/write-at table in [living-memory/README.md](living-memory/README.md).

**Long sessions:** don't bank the whole write-back for the end. After any merge, deploy, or hard-won debug, log it then — context runs out before sessions do.

**Two hooks in `.claude/settings.json` back this up.** A `SessionStart` hook injects four capped slices — HANDOFF (up to the template), NEXT (up to the hygiene rules), the CHANGELOG top-2 entries, and the GOTCHAS index — into context automatically, so the read half happens whether or not anyone remembers. A `Stop` hook warns once per session if any code file is newer than every file in `living-memory/` — it stays silent when memory is current. Neither blocks; they nudge. Review or disable via `/hooks`.

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
- **Feature gates (2026-08-08; evidence rules rewritten 2026-08-15 per D-056): scope block → evidence → docs → ledger. All four, every feature.** Before building anything that adds/changes user-visible behavior, data collection, schema, or API surface — through *any* pipeline (feedback item, NEXT.md, staged-work, direct ask):
  1. **Scope block first:** copy [docs/templates/feature-scope.md](docs/templates/feature-scope.md) into the feature's home and fill it. Every section is answered or explicitly waived with a reason — silence is not a waiver, and waivers are surfaced to the operator before build. Analytics events are specced against the taxonomy up front (the NULL-`platform` incident is why).
  2. **Evidence delta — NOT Maestro.** [D-056](living-memory/DECISIONS.md) (2026-08-15) retired Maestro and the simulator **entirely**: no flow authoring, no flow execution, no `screens/` captures, for any change in any pipeline. What replaces them: a structural `mobile/tests/check-*.js` suite and/or unit tests for anything mechanically checkable; a written **code-walk proof** (file:line-cited trace) for behavior that would once have gotten a sim capture; and a concrete **manual TestFlight checklist** for the operator when runtime proof genuinely matters — specific enough to actually catch a regression, because it is now the only runtime evidence mobile gets. `mobile/scripts/testid-lint.sh` stays in CI. Existing `mobile/.maestro/` flows are historical artifacts: kept, never run.
  3. **Mandatory doc updates:** any route change updates `docs/api-reference.md`; convention shifts update `living-memory/LLD.md`; genuine architecture shifts update `docs/architecture.md` + `living-memory/HLD.md`. The scope block's Docs table is filled row-by-row ("updated" or "n/a because"), on top of the existing trigger tables below.
  4. **Pre-ship gate:** before merge/push to `main`, CI must be green (`pytest backend/tests`, `tsc --noEmit`, testid-lint) and the evidence from item 2 logged in `living-memory/TEST_LEDGER.md`. `githooks/pre-push` still enforces the old simulator marker (`qa/sim-runs/last-sim-run.json`); under D-056 **`FTF_SKIP_SIM_GATE=1` is the standing posture** — set it and note the evidence you ran instead. Install the hooks once per clone: `git config core.hooksPath githooks`. (`docs/runbook.md` § Pre-ship simulator gate still describes the retired tier matrix — treat it as history.)

  **Rigor is an operator decision — express lane.** The four gates are the *default*, not a straitjacket. At flow start the operator may declare **express** ("quick fix", "just ship it", "skip the gates") — then skip the scope block, the evidence delta, and the docs table, leaving a one-line TEST_LEDGER note: `express: <what shipped> — gates skipped by operator`. What still applies even on express: CI must be green, the secrets rules, and the recovery ledger. Two rules keep this honest:
  - **Agents never self-select express.** No operator declaration → full gates. Genuinely ambiguous → ask.
  - **Bright line:** a change touching schema, API contracts, feature-flag surfaces, or analytics events is not a "quick fix" — if the operator declares express on one of those, say so explicitly and get a confirming yes before proceeding; the operator's confirmed call stands.
- **Branch/worktree deletion goes through the recovery ledger** (2026-08-08): before deleting any branch or removing any worktree, record its tip sha in a dated file in `docs/recovery/` per [docs/recovery/CLAUDE.md](docs/recovery/CLAUDE.md) — capture, then delete, never the reverse. Verification must be **by content** against `origin/main` (this repo squash-merges, so `git branch -d` refusals and ahead-counts are not evidence); cite the evidence doc in the ledger entry. At the end of any session that shipped work from a worktree, sweep it: once the branch's content is verified on `origin/main`, ledger the sha, `git worktree remove` it (a `--force` refusal means uncommitted files — inspect before discarding), and delete the branch. Don't leave merged worktrees behind — 91 of them (8.6 GB) once broke an EAS upload. Current backlog + verdicts: `docs/reviews/2026-08-08-branch-triage.md`.
- **Search tracked files only:** use `git grep -n "pattern"` (1,919 tracked files) or constrain Glob/Grep to specific dirs — never bare `grep -r` or repo-wide Glob from root. The filesystem holds 400k+ files of worktree/`node_modules` noise. Use `git grep --untracked` when new files matter.

## Common tasks

| Task | Where |
|---|---|
| Add/change an API route | `backend/server.py` → update `docs/api-reference.md` |
| Change the schema | `backend/database.py` → update `docs/data-dictionary.md` |
| Tweak ranking math | `backend/ranking_service.py`; tier bands in `backend/tier_config.json` |
| Tweak trade generation | `backend/trade_service.py` (v2 scoring) / `backend/trade_optimizer.py` (v3 package search) |
| Change trade card copy | `backend/trade_narrative.py` (deterministic templates, no LLM) |
| Touch a league platform | `backend/{sleeper_write,espn_service,espn_write,mfl_service,mfl_write,fleaflicker_service}.py` |
| Add/flip a feature flag | `config/features.json` → update `docs/config-reference.md`; hot-reload via `POST /api/feature-flags/reload` |
| Add an analytics event | Register in `backend/analytics_taxonomy.py` **and** classify in `analytics_queries.NON_INTENT_EVENTS`, in the *same commit* as the emitter |
| Add a mobile screen | `mobile/src/screens/` + register in `mobile/src/navigation/`; mount `FeedbackFAB` (see #188 above) |
| Add a web page | `web/*.html`, link from `index.html` |
| Add a backend test | `backend/tests/` (pytest) |
| Add a mobile structural check | `mobile/tests/check-*.js` + an `npm run` script in `mobile/package.json` |
