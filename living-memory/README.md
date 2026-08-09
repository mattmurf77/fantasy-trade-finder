# `living-memory/` — Cross-Session Memory Layer

The 20-file durable-memory layer for this project (17 patterns + the seed CHANGELOG, plus FORMAT.md and this README — the count grew as the layer matured; see [`FORMAT.md`](FORMAT.md) for the current file list and each file's retention policy). Files here capture state, decisions, and discipline so Claude (or future-you) can pick up cold across sessions. Older entries that have rotated out of the live files live in `archive/` — immutable, grouped by quarter or date range; see [`FORMAT.md`](FORMAT.md) §Retention & Rotation.

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

Plus `archive/` — a sixth, non-conceptual bucket: immutable, rotated-out entries from the Motion/Reality files above (e.g. `archive/CHANGELOG-2026Q3.md`, `archive/TEST_LEDGER-pre-2026-06.md`). Not read at session start; only consulted when the live file's pointer sends you there. See [`FORMAT.md`](FORMAT.md) §Retention & Rotation.

---

## Read-at / write-at quick reference

Retention policy (max live entries/age, per-entry cap, archive target, index style) is specified per file in [`FORMAT.md`](FORMAT.md) §Retention & Rotation — the column below just flags whether a file rotates at all.

| File | Read at | Write at | Retention |
|---|---|---|---|
| [`CHANGELOG.md`](CHANGELOG.md) | Session start | Session end | Rotates — last 10 entries live; older in `archive/CHANGELOG-*.md` |
| [`HANDOFF.md`](HANDOFF.md) | Session start | Session end (overwrite, don't accumulate) | Capped — 2,000 bytes, one live entry |
| [`NEXT.md`](NEXT.md) | Session start, after CHANGELOG + HANDOFF | When priority order shifts | Capped — 1.5KB queue, 7 active items |
| [`PRACTICES.md`](PRACTICES.md) | Session start (cheat sheet) | When patterns solidify | Rotates once >~15KB |
| [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) | Session start (any answers?) | The instant you'd otherwise block | Rotates once >~15KB |
| [`HLD.md`](HLD.md) | Before structural changes | Quarterly at most | Reference, not rotated |
| [`LLD.md`](LLD.md) | Before schema / template changes | When conventions shift | Reference, not rotated |
| [`CONTEXT.md`](CONTEXT.md) | New agent onboarding | Major scope shifts | Reference, not rotated |
| [`GLOSSARY.md`](GLOSSARY.md) | When an unfamiliar term appears | When a term is coined | Rotates once >~15KB |
| [`DECISIONS.md`](DECISIONS.md) | Before changing a major design choice | When you make one | Not archived — bottom index table, never deleted |
| [`MISTAKES.md`](MISTAKES.md) | Before proposing a new approach | When you abandon a path | Rotates once >~15KB |
| [`GOTCHAS.md`](GOTCHAS.md) | Before debugging weirdness | After wasting >30 min on a quirk | Marker-delimited top index; rotates once >~20KB |
| [`TEST_LEDGER.md`](TEST_LEDGER.md) | Before claiming a result | After running a test | Rotates — last 2 months live; older in `archive/TEST_LEDGER-*.md` |
| [`DEPENDENCIES.md`](DEPENDENCIES.md) | Before any integration change | When a quirk is discovered | Rotates once >~15KB |
| [`THIRD_PARTY.md`](THIRD_PARTY.md) | Before vendor decisions | When vendor terms change | Rotates once >~15KB |
| [`SOURCES.md`](SOURCES.md) | When a claim needs grounding | When authoritative refs change | Rotates once >~15KB |
| [`BRAND.md`](BRAND.md) | Before generating output | When voice evolves | Reference, not rotated |
| [`SUBAGENT_PRINCIPLES.md`](SUBAGENT_PRINCIPLES.md) | Before defining/invoking a sub-agent | When a principle emerges | Reference, not rotated |

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
