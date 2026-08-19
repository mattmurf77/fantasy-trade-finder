# archive/skill-workspaces/

Frozen skill artifacts. **The live skills are in [`.claude/skills/`](../../.claude/skills/README.md)** —
nothing in this folder is loaded by Claude Code.

Two separate archiving events landed here.

## 2026-07-12 — eval workspaces + packaged bundles moved out of the repo root

Throwaway A/B eval workspaces and the packaged `.skill` bundles that had been sitting
loose at the repo root during skill development.

| Item | What it is |
|---|---|
| `feature-evaluator-workspace/` | `iteration-1/` with/without-skill eval runs across three subjects (ranking screen UI, ranking system, trade generation) |
| `project-reorganizer-workspace/` | Eval runs against **synthetic fixture projects** (`flat-flask-api/`, `flat-express-api/`, `mixed-python-project/`). Their `docs/` folders are test inputs — not FTF history |
| `feature-evaluator.skill`, `project-architect.skill`, `project-reorganizer.skill` | Packaged bundles. `*.skill` is gitignored, so these exist on disk only |

## 2026-08-08 — five role skills retired

`retired-2026-08-08/` — `legal-privacy`, `ux-design`, `ux-research`, `fin-budget`,
`fin-forecast`, pulled from the active skill set during the context-overload remediation
pass because they produced zero deliverables in a month while the other 30 role skills
did. Rationale and the restore command:
[`retired-2026-08-08/README.md`](retired-2026-08-08/README.md).

Restoring one is a **move back** into `.claude/skills/`, followed by re-verifying that
the `SKILL.md` frontmatter still parses and the skill still triggers.
