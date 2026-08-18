# .claude/skills/ — project skill index

36 project-local Claude Code skills. Each is a directory with a `SKILL.md`
(`living-memory-format-check` uses lowercase `skill.md`); a few carry `references/`,
`templates/`, `evals/`, or `scripts/` alongside.

Invoke by name (`/eng-backend`) or let the description trigger it. Retired skills live in
[`archive/skill-workspaces/`](../../archive/skill-workspaces/README.md) — restoring one is
a move, not a copy.

## Workflow skills — these *do* things

| Skill | What it runs |
|---|---|
| `feedback` | The full in-app-feedback delivery pipeline: triage → operator selection → dual-agent planning → parallel build agents → QA → ship. Largest skill here: `references/{plan,build,qa,ship}-phase.md` + `lessons.md` |
| `maestro-test` | Runs Maestro UI flows on the simulator. **See the D-056 warning below — this skill is superseded and should not be run** |
| `living-memory-format-check` | Audits `living-memory/` against `FORMAT.md`; reports drift, offers per-file fixes, never auto-edits |
| `feature-evaluator` | Reviews a feature area and emits a structured improvement report. Has `references/code-quality-principles.md` + evals |
| `project-architect` | Generates/maintains the `docs/` reference layer. Carries the `root-CLAUDE.md`, `docs-CLAUDE.md`, `docs-README.md` templates and a `doc-inventory.md` reference |
| `project-reorganizer` | Restructures a flat/messy project tree |

## Role skills — 30 company roles

One skill per role, each grounded in [`docs/business/context.md`](../../docs/business/context.md);
index at [`docs/business/README.md`](../../docs/business/README.md). They produce documents,
not code — a role skill's job is the analysis, the spec, the plan.

| Prefix | Roles |
|---|---|
| `eng-` (7) | `architect`, `backend`, `mobile`, `web`, `integrations`, `qa`, `security` |
| `pm-` (7) | `technical`, `pfo`, `growth`, `retention`, `monetization`, `competitor`, `partnerships` |
| `mkt-` (8) | `brand`, `writer`, `content`, `seo`, `aso`, `lifecycle`, `partners`, `adops` |
| `an-` (5) | `data-architect`, `funnel`, `experiment`, `market`, `user-data` |
| `ops-` (2) | `release`, `support` |
| `fin-` (1) | `pnl` |

Five more role skills (`legal-privacy`, `ux-design`, `ux-research`, `fin-budget`,
`fin-forecast`) were retired 2026-08-08 for producing zero deliverables in a month —
see [`archive/skill-workspaces/retired-2026-08-08/README.md`](../../archive/skill-workspaces/retired-2026-08-08/README.md).

## ⚠ Known drift: D-056 vs the QA-shaped skills

Operator decision **D-056** (2026-08-15, Active — `living-memory/DECISIONS.md`) retired
Maestro and the simulator **entirely**: no flow authoring, no execution, no screen captures,
in any pipeline. Several skills still instruct otherwise. Status as of **2026-08-18**:

| Skill / file | D-056 aware? |
|---|---|
| `feedback/lessons.md`, `feedback/references/plan-phase.md`, `feedback/references/build-phase.md` | yes — rewritten 2026-08-16 |
| `feedback/references/ship-phase.md` | fine — only references the `maestro-testid-lint` CI job, which D-056 explicitly keeps |
| `feedback/references/qa-phase.md` | **no** — still opens with "boot a simulator, install the build, run flows" |
| `maestro-test` | **no** — the skill's entire purpose is superseded |
| `eng-mobile` | **no** — step 4 is "verify on the simulator" via `sim-build.sh` / `sim-run.sh` |
| `eng-qa` | **no** — names Maestro smoke flows as the mobile E2E lane |
| `pm-pfo`, `pm-technical` | **partly** — treat `mobile/.maestro/flows/` as live inputs and seed test plans as Maestro flow sketches |

If a skill tells you to run Maestro or take a simulator capture, **D-056 wins**. Substitute:
structural `mobile/tests/check-*.js` suites + unit tests, a file:line code-walk proof, and a
manual TestFlight checklist for the operator. Current QA regime:
[`qa/README.md`](../../qa/README.md).

## Other `.claude/` contents

| Path | What it is |
|---|---|
| `.claude/settings.json` | Tracked. Holds the `SessionStart` memory-injection hook and the `Stop` living-memory-staleness warning. **Documentation agents do not edit this** |
| `.claude/settings.local.json` | Per-machine permission overrides |
| `.claude/launch.json` | Dev-server definitions for the preview tooling |
| `.claude/worktrees/` | Agent worktrees — gitignored, and excluded from EAS builds via `.easignore`. Deleting one goes through [`docs/recovery/`](../../docs/recovery/CLAUDE.md) |
| `.claude/skills/feedback/scripts/fetch_feedback.py` | **Untracked** — used by the `feedback` skill. Commit it or ignore it deliberately |
