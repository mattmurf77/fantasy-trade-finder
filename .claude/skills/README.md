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
| `maestro-test` | **RETIRED (D-056) — do not invoke.** Ran Maestro UI flows on the simulator; carries a retirement banner and is kept only as a historical record. See the sweep table below |
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

## D-056 sweep — the QA-shaped skills (completed 2026-08-18)

Operator decision **D-056** (2026-08-15, Active — [`living-memory/DECISIONS.md`](../../living-memory/DECISIONS.md))
retired Maestro and the simulator **entirely**: no flow authoring, no execution, no screen
captures, in any pipeline. Every skill that still instructed otherwise was rewritten on
**2026-08-18**:

| Skill / file | State |
|---|---|
| `maestro-test` | **RETIRED banner** at the top + `description:` leads with `RETIRED (D-056)`. Not deleted — that's the operator's call; the body is kept as a historical record of how the harness worked |
| `feedback/references/qa-phase.md` | rewritten — sim/Maestro prep replaced by `tsc` + `check-*.js` + pytest, code-walk proofs per requirement, the proven-to-fail sabotage rule, and an operator TestFlight checklist as the batch's only runtime evidence |
| `feedback/SKILL.md` (body) | Phase 3/5 descriptions, work-type table, scope-block row, and express lane no longer name Maestro or `FTF_SKIP_SIM_GATE`. Frontmatter `description:` deliberately untouched — it still says "Maestro test plan" / "redundant Maestro QA" |
| `feedback/references/ship-phase.md` | corrected — it was **not** clean: it required fresh `qa/sim-runs/last-sim-run.json` evidence and claimed `githooks/pre-push` enforces it. That hook is now a deliberate no-op. The `maestro-testid-lint` CI reference stays (D-056 keeps it) |
| `eng-mobile` | "verify on the simulator" → guards + code-walk proof + TestFlight checklist; test-hooks and handoff bullets repointed at `mobile/tests/` |
| `eng-qa` | the mobile E2E lane is now the `check-*.js` guard set; runtime evidence is the operator's TestFlight pass. Frontmatter trigger phrase still reads "Maestro flow" |
| `pm-pfo`, `pm-technical` | `mobile/.maestro/flows/` no longer cited as live coverage; test-plan seeds are guards + code-walk + checklist, not flow sketches |
| `feedback/lessons.md`, `feedback/references/plan-phase.md`, `feedback/references/build-phase.md` | already D-056-correct — verified, left untouched. **But:** those rewrites exist only as *uncommitted* edits in the operator's main checkout; a fresh clone of `origin/main` still shows the pre-D-056 text |

If any skill still tells you to run Maestro or take a simulator capture, **D-056 wins**.
Substitute: structural `mobile/tests/check-*.js` suites + unit tests
([`mobile/tests/README.md`](../../mobile/tests/README.md)), a file:line code-walk proof, and
a manual TestFlight checklist for the operator. The live evidence contract is
[`docs/templates/feature-scope.md`](../../docs/templates/feature-scope.md) §3 and §5; the
backend QA charter is [`qa/README.md`](../../qa/README.md).

## Other `.claude/` contents

| Path | What it is |
|---|---|
| `.claude/settings.json` | Tracked. Holds the `SessionStart` memory-injection hook and the `Stop` living-memory-staleness warning. **Documentation agents do not edit this** |
| `.claude/settings.local.json` | Per-machine permission overrides |
| `.claude/launch.json` | Dev-server definitions for the preview tooling |
| `.claude/worktrees/` | Agent worktrees — gitignored, and excluded from EAS builds via `.easignore`. Deleting one goes through [`docs/recovery/`](../../docs/recovery/CLAUDE.md) |
| `.claude/skills/feedback/scripts/fetch_feedback.py` | **Untracked** — used by the `feedback` skill. Commit it or ignore it deliberately |
