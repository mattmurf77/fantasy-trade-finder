# Fleeced — shared agent contract

Fleeced is a dynasty fantasy football product. [README.md](README.md) has commands and the repository map; read the [product overview](docs/product/overview.md) when product context is needed.

## Start and navigate

- Check `git status` and the current branch before editing. Start new work from freshly fetched `origin/main`; preserve unrelated changes. Never assume this checkout is current main.
- If a **Session brief** was injected, use it without rereading the same files. Otherwise run `python3 scripts/session_context.py` once. Missing or omitted sections are labelled; follow only the references needed for this task.
- Search with `rg` in relevant directories or `git grep`; use `git ls-files` for inventories. Exclude dependencies, archives, generated outputs and nested worktrees from ordinary discovery.
- Current behavior comes from code/configuration and its reference docs. Plans and archives explain intent/history; they do not prove deployment. Update the relevant reference when evidence reveals drift.

## Change rules

- Follow [coding guidelines](docs/coding-guidelines.md). Keep changes scoped, state assumptions, and validate the behavior affected.
- Before a behavioral, schema, API, or analytics change, read [agent workflow](docs/agent-workflow.md): scope, evidence, canonical docs, and release gates apply. Operator-declared express work is defined there; agents do not self-select it.
- Read [design tokens](docs/design/design-system.md) and [components](docs/design/components.md) before UI work. Existing captures are historical; prototypes are not shipped code.
- **Maestro and simulator work are retired (D-056).** Use automated checks, cited code traces, and concrete manual TestFlight checklists. Current CI is in `.github/workflows/ci.yml`.
- **Secrets:** use `secrets.local.env` only when required; never print, commit, or place credentials in docs/chat. Never point test/seeding scripts at production.
- Before deleting a branch or worktree, follow [recovery procedure](docs/recovery/CLAUDE.md): record the tip and verify content first. Preserve explicit operator exclusions. The organization cleanup does not authorize touching existing nested worktrees.

## Finish

Update one canonical reference per changed concern, the initiative's status/evidence, and session memory as needed. HLD/LLD compatibility stubs are not update targets. Keep `HANDOFF.md` at **2,000 UTF-8 bytes** and `NEXT.md` at **1,500 bytes / seven items**; archive history rather than append it. Run `python3 scripts/session_context.py --check` after memory changes. Report changes, verification, and remaining limits; never equate a build or plan with a release.
