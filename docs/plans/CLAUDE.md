# `docs/plans/` — Agent instructions

You are inside the agent-collaboration workspace. Every multi-session / multi-agent work thread lives in its own folder here.

**Protocol:** [../agent-collab-protocol.md](../agent-collab-protocol.md) (read if unfamiliar).
**Templates:** [_templates/](./_templates/) — copy when creating a new thread folder.
**Folder convention:** [README.md](./README.md).

## Boot read order (any session touching an existing thread)

1. `<thread-slug>/status.md` — current phase, next action, blockers
2. `<thread-slug>/conversation.md` — round history
3. `<thread-slug>/plan.md` — original brief
4. The **latest two round files** (open round + the one it answers)
5. Older rounds only if listed in `references:` frontmatter

## While working — keep these current

- **Subagent:** write findings into a new `round-NN-findings.md` using [_templates/round-findings.template.md](./_templates/round-findings.template.md). Tag proposed changes `[BACKEND]` / `[WEB]` / `[MOBILE]` / `[EXT]` / `[CROSS-CLIENT]` / `[DOCS]`. Never edit prior rounds. Never touch `status.md`.
- **Primary:** write follow-ups into a new `round-NN-task.md` or `round-NN-review.md` using [_templates/round-task.template.md](./_templates/round-task.template.md). Update `status.md` after every round. Append a row to `conversation.md`.

## Closing a thread

Set `status.md` → `Phase: done`, add an `## Outcome` section, and promote durable changes per the "Reference docs (keep current)" table in the root [CLAUDE.md](../../CLAUDE.md) (ADRs, data-dictionary, api-reference, glossary, runbook, cross-client-invariants) plus `living-memory/` files.

## Gitignored vs tracked

- **Tracked:** `plan.md`, `_templates/`, this file, `README.md`, the root protocol doc.
- **Gitignored (local agent scratch):** `status.md`, `conversation.md`, `round-*.md`, `artifacts/`.

## When to promote a flat plan to a folder

When the work will span more than one session, involve more than one agent, or need back-and-forth iteration. Otherwise leave it flat.
