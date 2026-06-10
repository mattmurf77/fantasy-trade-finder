# `docs/plans/`

Two kinds of artifacts live here:

1. **Flat plans** (`<slug>.md`) — single-session, single-author work. Stays flat. Fully tracked in git.
2. **Thread folders** (`<slug>/`) — multi-session, multi-agent work governed by [`docs/agent-collab-protocol.md`](../agent-collab-protocol.md). Inside each folder:
   - `plan.md` — the brief. **Tracked in git.**
   - `status.md`, `conversation.md`, `round-*.md`, `artifacts/` — agent working state. **Ignored by git** (see `.gitignore`). Local-only.

Templates for thread folders live in [`_templates/`](_templates/). Copy them into a new thread folder when converting a flat plan to a thread.

Promote a flat plan to a thread folder when **any** of these become true:
- The work will span more than one Claude Code session.
- More than one agent (primary + at least one subagent) will contribute.
- The work needs back-and-forth iteration (research → review → revise).

Otherwise leave it flat.
