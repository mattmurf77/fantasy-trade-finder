---
name: project-architect
description: >
  Generates and maintains a project's reference-documentation layer — a `docs/`
  folder (data dictionary, API reference, architecture diagram, glossary,
  cross-client invariants, config reference, runbook, coding guidelines, ADR
  index) plus per-folder `CLAUDE.md` + `README.md` files, wired into a root
  `CLAUDE.md` so every session loads the maintenance contract. Use this skill
  when the user asks to "generate project docs", "create a data dictionary",
  "document this codebase", "build a docs folder", "set up reference docs",
  "architect the documentation", "scaffold CLAUDE.md files", or "update the
  reference docs for the latest changes". Also triggers on "doc drift",
  "review the project and refresh docs", or any request to keep reference
  files in sync with code. Not a substitute for `engineering:architecture`,
  which writes ADRs for individual design decisions.
license: MIT
---

# Project Architect

You are building or maintaining a project's structured reference layer. The
goal is a small set of high-leverage docs that any reader (human or future
Claude session) can use to answer 80% of "where does X live / what does Y
mean / what must stay in sync" questions without grepping.

## Mode selection

Three modes. Pick one based on the request:

1. **Bootstrap** — no `docs/` exists yet, or only stubs. Generate the full set.
2. **Refresh** — `docs/` exists. Diff the live codebase against the docs and
   surgically update only the files affected by changes. Do NOT rewrite docs
   that are still accurate.
3. **Folder scaffolding** — generate per-folder `CLAUDE.md` + `README.md` for
   meaningful source folders. Skip noise (`node_modules`, `__pycache__`,
   `.expo`, `.git`, eval workspaces, build outputs).

Always confirm scope with the user before doing dozens of folder docs.

## Phase 0 — Scan and orient

Before writing anything, read enough to be accurate:

- Top-level folders (skip noise dirs).
- Backend schema source of truth (e.g. `backend/database.py`,
  `prisma/schema.prisma`, `db/migrations/`). Enumerate every table.
- HTTP route definitions (grep for `@app.route`, `router.`, route files).
  Enumerate every route.
- Config sources: env var reads (`os.environ`, `process.env`), feature-flag
  files, runtime-tunable tables (`model_config`-style).
- Cross-client invariants: tier/color tokens, enum strings, K-factors,
  thresholds duplicated across backend/web/mobile/extension.
- Entry points (`run.py`, `App.tsx`, `index.html`, `manifest.json`).

If the schema file is huge, page through it — do not skim. Tables and columns
must be accurate or the doc is worse than no doc.

## Phase 1 — Generate (Bootstrap mode)

Create these files. Each links to the next; the root CLAUDE.md ties them
together.

### `docs/data-dictionary.md`
- Source of truth: `<schema file>`.
- One section per table. Column table: name, type, notes (PK / FK /
  enum values / lifecycle). Call out append-only vs. mutable tables and
  composite indexes by name.

### `docs/api-reference.md`
- Group routes by feature area (Session / Auth, Players, Ranking, Trades,
  League, Notifications, Cron, Admin, Misc, etc.).
- Method + path + one-line purpose. Note which tables each route reads/writes
  when non-obvious.

### `docs/glossary.md`
- Every domain term that isn't self-evident from its name. Pull jargon from
  code comments and UI strings.
- For tunable values, cite the live default and the config key.

### `docs/cross-client-invariants.md`
- Anything duplicated across clients that will silently break if drifted:
  color tokens, enum strings (decision types, notification types, scoring
  formats), gating thresholds, K-factors, kind→bucket maps.
- For each, list every file that must be updated together.

### `docs/architecture.md`
- Mermaid `flowchart LR` showing External → Backend modules → DB → Clients.
- Module table: file, ~lines, role.
- Request lifecycle walkthroughs for the 2–4 most important flows
  (e.g. ranking submit, trade match, push dispatch, cron tick).

### `docs/config-reference.md`
- Env vars table.
- Feature flags table (every key in the flags file with default + notes).
- Runtime DB-tunable defaults (every row of the seed array with default +
  one-line description).

### `docs/runbook.md`
- Local dev commands.
- Deploy summary (Render / Vercel / etc.).
- DB backup/restore.
- Cron schedule table if applicable.
- Common failure modes + fixes.
- Reset/wipe endpoints.

### `docs/coding-guidelines.md`
- The Karpathy four principles (Think Before Coding / Simplicity First /
  Surgical Changes / Goal-Driven Execution). See
  `references/karpathy-guidelines.md` in this skill for the canonical text.

### `docs/adr/README.md`
- ADR template + empty index. Don't backfill ADRs unless asked.

### `docs/README.md` and `docs/CLAUDE.md`
- README: table of contents linking every doc above.
- CLAUDE.md: the **update-trigger table** — for each doc, what diff in code
  should prompt an update.

### Root `CLAUDE.md`
- Reference the coding guidelines first (priority).
- Project orientation: stack, entry points, conventions.
- Embed the update-trigger table from `docs/CLAUDE.md` (or link to it) so the
  maintenance contract loads every session.

## Phase 2 — Refresh mode

When docs exist, do not regenerate from scratch. Diff live code against docs
and edit only what changed:

| If code changed… | Update… |
|---|---|
| `<schema file>` — new/renamed/removed tables or columns | `data-dictionary.md` |
| Route definitions — new/renamed/removed routes | `api-reference.md` |
| Env var reads, feature-flag files, runtime-tunable defaults | `config-reference.md` |
| Backend modules added/removed/re-wired | `architecture.md` |
| Cross-client duplicated values | `cross-client-invariants.md` |
| New domain term in code or UI | `glossary.md` |
| Operational behavior (cron, push, deploy) | `runbook.md` |

Use `Edit` for targeted changes. Use `Write` only when rewriting an entire
doc is genuinely cheaper than a series of edits (e.g. architecture diagram
needs restructuring).

After updating, run a quick consistency pass: are the same enum strings used
in glossary, cross-client-invariants, and data-dictionary? Are K-factors
quoted the same in glossary and config-reference?

## Phase 3 — Folder scaffolding (optional)

For each meaningful source folder (backend, web, mobile/src/*, extension,
config, data, scripts, skill folders):

- `CLAUDE.md` — folder-specific rules and gotchas. What goes here, what
  doesn't. Cross-cutting invariants to respect.
- `README.md` — reader-facing summary. File inventory with one-line
  purposes.

Skip auto-generated, vendored, or throwaway dirs.

## Discipline

- **Accuracy beats completeness.** A wrong column type in the data
  dictionary is worse than an absent one. Verify before writing.
- **Cite source of truth.** Every doc names the file it derives from.
- **No duplication.** If the same fact lives in two places, one must point
  to the other.
- **Update triggers are the product.** The maintenance contract in root
  CLAUDE.md is what keeps these docs alive. Don't ship docs without it.
- **Surgical edits.** When refreshing, never touch a section that didn't
  change. Per `references/karpathy-guidelines.md` — every changed line
  traces to the diff.

## What this skill does NOT do

- Write individual ADRs. Use `engineering:architecture` for that.
- Design new systems. Use `engineering:system-design`.
- Reorganize folder structure. Use `anthropic-skills:project-reorganizer`.
- Review code quality. Use the project's `feature-evaluator` skill if one
  exists, or `engineering:code-review`.
- Generate test plans. Use `engineering:testing-strategy`.

## References

- `references/karpathy-guidelines.md` — the four behavioral principles to
  follow while writing docs (Think Before Coding / Simplicity First /
  Surgical Changes / Goal-Driven Execution).
- `references/doc-inventory.md` — the canonical list of doc files this skill
  produces and the update triggers per file.
- `templates/` — starter skeletons for each doc.
