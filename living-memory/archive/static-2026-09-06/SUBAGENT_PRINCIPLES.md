# Sub-Agent Guiding Principles — Fantasy Trade Finder

> **Purpose:** the durable rules for how sub-agents should be defined, invoked, and constrained in this project. Especially relevant because the project already ships two custom skills (`feature-evaluator.skill`, `project-reorganizer.skill`) and uses Anthropic Claude API at runtime via `smart_matchup_generator.py`.
>
> **Read at:** before defining a new sub-agent, before invoking one in a sensitive context, before adding a new skill.
> **Write at:** when a new principle emerges from experience.
>
> Companion files: [`feature-evaluator.skill`](../feature-evaluator.skill), [`project-reorganizer.skill`](../project-reorganizer.skill), [`.claude/skills/living-memory-format-check/skill.md`](../.claude/skills/living-memory-format-check/skill.md).

---

## Table of Contents
- [2026-05-21 — Core Principles](#2026-05-21--core-principles)
- [Existing Skills in This Project](#existing-skills-in-this-project)
- [Built-in Sub-Agents (Reference)](#built-in-sub-agents-reference)
- [Runtime AI: `smart_matchup_generator.py`](#runtime-ai-smart_matchup_generatorpy)
- [Checklist for Sub-Agent Reviews](#checklist-for-sub-agent-reviews)
- [Outstanding / Known Gaps](#outstanding--known-gaps)

---

## 2026-05-21 — Core Principles

### Principle 1: Tasks, not roles
Sub-agents are named for **what they do**, not **what they are**.
- ✅ `living-memory-format-check`, `project-reorganizer`, `feature-evaluator`, `dynastyprocess-name-fuzzy-matcher`
- ❌ `senior-engineer`, `dynasty-analyst`, `qa-tester`

Persona agents produce generic output; task agents produce structured output.

### Principle 2: Restrict tools to the minimum necessary
Default each sub-agent to **read-only**, then add write/execute only when the task demands.
- A code-review agent → `Read`, `Grep`, `Glob`, `Bash`. **Never** `Write` or `Edit` on production code.
- A format-check agent → `Read`, `Write`, `Edit`. Scoped to `living-memory/`. **Never** outside that folder.
- A reorganizer agent → broad access, but `isolation: worktree` so it operates on a copy.

Use `disallowed-tools` explicitly when blocking tools, even if they're not on the allow list — protects against future tool-list expansion.

### Principle 3: Match the model to the task
- **Haiku** for routine, well-scoped work: format checking, summarization, simple file reads.
- **Sonnet** for synthesis: code review, multi-file refactors, test design.
- **Opus** for high-ambiguity work: architecture decisions, plan-mode for multi-stage tasks.

The runtime smart-matchup generator (in production) uses Haiku — small cost, fast latency, good fit for the task.

### Principle 4: Sub-agents return summaries, not raw output
A sub-agent that reads 30 files **must not** dump them back to the parent. It should return:
- What it found (specific lines / files / values).
- What's wrong / what's good / what's next.
- The 1–5 highest-value findings.

Format-check agent: returns a table (file | severity | drift items), not the full markdown contents of every file.
Code-review agent: returns severity-rated findings, not file contents.

### Principle 5: Don't spawn for trivial work
A sub-agent for a single `grep` or a single file read is overhead. Rule of thumb:
- If <500 tokens of work in the parent session, do it in the parent.
- If reading >5 files or running a script that produces >500 lines of output, sub-agent it.

### Principle 6: Parallel sub-agents must work on disjoint outputs
If parallel work is needed:
- Each sub-agent writes to a uniquely-named file.
- Never both edit `backend/server.py` in parallel — corruption is deterministic.
- For same-file edits, use `git worktree` (`isolation: worktree`).

### Principle 7: Document the contract in the `.skill` or `.agent.md`
Every sub-agent file should declare:

```yaml
---
name: <kebab-case-task-name>
description: <one sentence describing trigger conditions and output>
tools: [<minimum necessary list>]
disallowed-tools: [<explicit blocks>]
model: claude-haiku  # default
permission-mode: accept-edits | default | plan
memory: project | user | none
isolation: none | worktree
---
You are <role-equivalent-in-task-terms>.

Inputs you can expect: <list>
Outputs you must return: <list>
Constraints: <list>
```

### Principle 8: Sub-agents don't ship to production code
The format-check skill can write to `living-memory/`. The reorganizer skill operates on copies via worktrees. **No sub-agent should directly modify production code** (`backend/`, `web/`, `mobile/`, `extension/`) without operator review of the diff.

### Principle 9: Sub-agents are not the right answer when…
- The task needs back-and-forth with the user → use a skill or stay in the parent.
- Two agents would need to talk to each other → use Agent Teams (experimental, rarely justified here).
- The task is naturally sequential and short → just run the steps in the parent.

### Principle 10: One feature ≠ one agent
Don't create a sub-agent per feature. Create a sub-agent per **type of repeated work**. A good sub-agent runs many times across many features; a bad one runs once and gets deleted.

---

## Existing Skills in This Project

### `feature-evaluator.skill`
**Role:** evaluates code features across 7 dimensions (structure, readability, performance, error handling, security, testability, maintainability). Produces structured markdown reports with severity-rated findings.
**Triggered by:** explicit invocation; commonly used during code review.
**Permission posture:** read-only on production code. No writes.

### `project-reorganizer.skill`
**Role:** reorganizes flat or messy project folders. 6-phase methodology (scan, propose, cross-reference, execute, update imports, verify).
**Triggered by:** explicit invocation. Benchmarked at +40pp vs ad-hoc (83% vs 43% success).
**Permission posture:** broad access, but should run with `isolation: worktree` for safety.

### `living-memory-format-check.skill`
**Role:** audits `living-memory/` files against [`FORMAT.md`](FORMAT.md). Reports drift; offers per-file fixes; never auto-edits without approval.
**Triggered by:** "check living memory format," "audit living-memory files," "verify format compliance," "fix format drift."
**Permission posture:** read on `living-memory/`; write only on user approval per file.

---

## Built-in Sub-Agents (Reference)

Anthropic ships these by default; `/agents` lists them:
- **`explore`** (Haiku) — codebase exploration; returns summaries. Useful for surveying the `docs/` folder or a new module.
- **`general-purpose`** (inherits parent model) — fallback for ad-hoc work.
- **`plan`** (inherits) — useful for planning new features.

Prefer these over custom equivalents unless a specific reason justifies a custom skill.

---

## Runtime AI: `smart_matchup_generator.py`

This is the only sub-agent equivalent that runs at *user-facing runtime* (not just at development time). Special considerations:

- **Must have a fallback.** If `ANTHROPIC_API_KEY` is unset or the API is unavailable, algorithmic fallback in `ranking_service.py` kicks in. Never let the user see an error because of missing AI.
- **Cost-aware.** Per-call cost is small (~$0.001) but aggregates. Cap by user/session if usage scales.
- **Latency budget.** Matchup selection is user-blocking — the user is waiting to swipe. Stay under ~1s round-trip; switch to fallback if it goes over.
- **Deterministic-when-possible.** If two users hit the same matchup-decision point with the same Elo state, ideally they get similar outputs (within randomness budget). Don't let Claude be wildly inconsistent on simple inputs.

---

## Checklist for Sub-Agent Reviews

Before merging a new `.skill` or `.agent.md`:

- [ ] Name is task-flavored, not role-flavored.
- [ ] Description includes trigger conditions AND output shape.
- [ ] Tools list is minimum-necessary, not "everything just in case."
- [ ] `disallowed-tools` explicitly blocks anything sensitive (especially `Edit` on `backend/`).
- [ ] Model choice matches task complexity (default Haiku unless justified).
- [ ] System prompt declares: task, expected inputs, expected outputs, constraints.
- [ ] Sub-agent returns a digest, not raw dumps.
- [ ] If invoking in parallel: file isolation verified.
- [ ] If editing files: `isolation: worktree` is set for production code.

---

## Outstanding / Known Gaps
- No formal metrics on per-skill ROI for this project (other than the project-reorganizer benchmark).
- Runtime-AI usage (smart matchup generator) is not currently rate-limited per user.
- If/when this project gets multi-user, per-user AI quotas need to be defined.
