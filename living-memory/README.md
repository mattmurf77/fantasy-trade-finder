# `living-memory/` — Cross-Session Memory Layer

The 18-file durable-memory layer for this project (17 patterns + the seed CHANGELOG). Files here capture state, decisions, and discipline so Claude (or future-you) can pick up cold across sessions.

Pattern source: `Master Claude Code Best Practices` workspace's `HLD.md`. Complements (does not replace) the existing reference docs in [`../docs/`](../docs/).

---

## Table of Contents
- [Relationship with `docs/`](#relationship-with-docs)
- [What goes where](#what-goes-where)
- [Read-at / write-at quick reference](#read-at--write-at-quick-reference)
- [Conventions](#conventions)
- [Project-level companions (outside this folder)](#project-level-companions-outside-this-folder)

---

## Relationship with `docs/`

This project already maintains comprehensive reference documentation in `../docs/` (architecture, api-reference, glossary, data-dictionary, coding-guidelines, runbook, ADRs). The living-memory layer **does not duplicate** these — it cross-references them and adds the *living* pieces: dated work logs, decisions in flight, open questions, mistakes, gotchas, priorities.

| Concept | Authoritative location | Living-memory file |
|---|---|---|
| Architecture (modules, data flow) | [`../docs/architecture.md`](../docs/architecture.md) | [`HLD.md`](HLD.md) — references and adds living context |
| Database schema | [`../docs/data-dictionary.md`](../docs/data-dictionary.md) | [`LLD.md`](LLD.md) — references |
| API routes | [`../docs/api-reference.md`](../docs/api-reference.md) | [`LLD.md`](LLD.md) — references |
| Cross-client constants | [`../docs/cross-client-invariants.md`](../docs/cross-client-invariants.md) | [`LLD.md`](LLD.md) — references |
| Glossary of domain terms | [`../docs/glossary.md`](../docs/glossary.md) | [`GLOSSARY.md`](GLOSSARY.md) — supplements with project-internal jargon |
| Architecture decisions | [`../docs/adr/`](../docs/adr/) | [`DECISIONS.md`](DECISIONS.md) — terser day-to-day log; ADRs are formal |
| Operational runbook | [`../docs/runbook.md`](../docs/runbook.md) | [`GOTCHAS.md`](GOTCHAS.md) — overlap but different framings |
| Coding guidelines | [`../docs/coding-guidelines.md`](../docs/coding-guidelines.md) | [`BRAND.md`](BRAND.md) — voice/style; PRACTICES expands |

If `docs/` and `living-memory/` ever conflict, `docs/` wins.

---

## What goes where

The five conceptual columns from the workspace pattern:

```
INTENT             REALITY              MOTION            AUTHORITY        IDENTITY
──────────         ────────────         ──────────────    ───────────      ──────────────
CONTEXT.md         HLD.md               CHANGELOG.md      SOURCES.md       BRAND.md
GLOSSARY.md        LLD.md               HANDOFF.md        PRACTICES.md     SUBAGENT_PRINCIPLES.md
DECISIONS.md       DEPENDENCIES.md      NEXT.md
OPEN_QUESTIONS.md  TEST_LEDGER.md       MISTAKES.md
                   THIRD_PARTY.md       GOTCHAS.md
```

- **Intent** — why we exist, what the words mean, what we've decided, what we're waiting on.
- **Reality** — what the system *is* right now: architecture, schemas, dependencies, vendors, test history.
- **Motion** — what changed, what's next, what's in-flight, what we got wrong.
- **Authority** — where truth comes from (sources of record, distilled practices).
- **Identity** — how we sound, how our agents behave.

---

## Read-at / write-at quick reference

| File | Read at | Write at |
|---|---|---|
| [`CHANGELOG.md`](CHANGELOG.md) | Session start | Session end |
| [`HANDOFF.md`](HANDOFF.md) | Session start | Session end (overwrite, don't accumulate) |
| [`NEXT.md`](NEXT.md) | Session start, after CHANGELOG + HANDOFF | When priority order shifts |
| [`PRACTICES.md`](PRACTICES.md) | Session start (cheat sheet) | When patterns solidify |
| [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) | Session start (any answers?) | The instant you'd otherwise block |
| [`HLD.md`](HLD.md) | Before structural changes | Quarterly at most |
| [`LLD.md`](LLD.md) | Before schema / template changes | When conventions shift |
| [`CONTEXT.md`](CONTEXT.md) | New agent onboarding | Major scope shifts |
| [`GLOSSARY.md`](GLOSSARY.md) | When an unfamiliar term appears | When a term is coined |
| [`DECISIONS.md`](DECISIONS.md) | Before changing a major design choice | When you make one |
| [`MISTAKES.md`](MISTAKES.md) | Before proposing a new approach | When you abandon a path |
| [`GOTCHAS.md`](GOTCHAS.md) | Before debugging weirdness | After wasting >30 min on a quirk |
| [`TEST_LEDGER.md`](TEST_LEDGER.md) | Before claiming a result | After running a test |
| [`DEPENDENCIES.md`](DEPENDENCIES.md) | Before any integration change | When a quirk is discovered |
| [`THIRD_PARTY.md`](THIRD_PARTY.md) | Before vendor decisions | When vendor terms change |
| [`SOURCES.md`](SOURCES.md) | When a claim needs grounding | When authoritative refs change |
| [`BRAND.md`](BRAND.md) | Before generating output | When voice evolves |
| [`SUBAGENT_PRINCIPLES.md`](SUBAGENT_PRINCIPLES.md) | Before defining/invoking a sub-agent | When a principle emerges |

---

## Conventions

For the full format specification — required header structure, TOC rules, per-file required sections, drift indicators — see [`FORMAT.md`](FORMAT.md). The [`living-memory-format-check` skill](../.claude/skills/living-memory-format-check/skill.md) audits files against the spec on demand and offers per-file fixes.

Quick rules:

- **All paths in these files are relative to this folder.** Links to project-level files use `../` (e.g. `../docs/architecture.md`, `../CLAUDE.md`); sibling files in `living-memory/` use bare filenames.
- **ISO dates.** `2026-05-21`, not `5/21/26`.
- **Table of Contents required** in every file (after the purpose blockquote). See [`FORMAT.md`](FORMAT.md) for the spec.
- **Date-based H2 sections** in any file that accumulates entries.
- **Bullets > paragraphs.** Brevity is the point.
- **Sequential IDs** for traceable items: `D-NNN` (decisions), `Q-NNN` (questions), `M-NNN` (mistakes), `G-NNN` (gotchas).

---

## Project-level companions (outside this folder)

| File | Role |
|---|---|
| [`../README.md`](../README.md) | Public project description |
| [`../CLAUDE.md`](../CLAUDE.md) | Operator's brief for Claude — points to this folder + `docs/` |
| [`../context.md`](../context.md) | Detailed project orientation (overview, stack, architecture, open items) |
| [`../docs/`](../docs/) | Reference documentation (architecture, glossary, runbook, ADRs, etc.) |
