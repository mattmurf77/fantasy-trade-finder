# Living-Memory File Format Specification — Fantasy Trade Finder

> **Purpose:** the structure every file in this folder must follow. Read before creating a new memory file or editing an existing one. Enforced by the `living-memory-format-check` skill (in [`../.claude/skills/living-memory-format-check/`](../.claude/skills/living-memory-format-check/)).
>
> **Read at:** before creating or substantially editing any file in `living-memory/`.
> **Write at:** when conventions actually change. Rare.
>
> Companion files: [`README.md`](README.md), [`../docs/CLAUDE.md`](../docs/CLAUDE.md) (the existing project-doc update-trigger table).

---

## Table of Contents
- [Universal Header Structure](#universal-header-structure)
- [File Patterns](#file-patterns)
- [Relationship with `docs/`](#relationship-with-docs)
- [Markdown Conventions](#markdown-conventions)
- [Naming and IDs](#naming-and-ids)
- [Cross-References](#cross-references)
- [Per-File Required Sections](#per-file-required-sections)
- [TOC Generation Rules](#toc-generation-rules)
- [Drift Indicators](#drift-indicators)

---

## Universal Header Structure

Every file in this folder (excluding `README.md` and this `FORMAT.md`) MUST begin with:

```markdown
# <FileName> — Fantasy Trade Finder

> **Purpose:** <one sentence>
>
> **Read at:** <trigger>
> **Write at:** <trigger>
>
> Companion files: <relative links, or "none">

---

## Table of Contents
- [Section 1](#section-1)
- ...
- [Outstanding / Known Gaps](#outstanding--known-gaps)

---

## <First content section>
```

The five required elements:
1. **H1** title with `— Fantasy Trade Finder` suffix.
2. **Purpose blockquote** with three labeled fields plus companions.
3. **Horizontal rule.**
4. **`## Table of Contents`** with every other H2 section linked.
5. **Horizontal rule** before content.

---

## File Patterns

| Pattern | Files | TOC entries are |
|---|---|---|
| **A — Date-indexed** | `CHANGELOG`, `HANDOFF`, `TEST_LEDGER`, `MISTAKES`, `GOTCHAS`, `DEPENDENCIES`, `THIRD_PARTY`, `SOURCES`, `GLOSSARY`, `OPEN_QUESTIONS`, `PRACTICES` | ISO dates (most recent at top) plus trailing sections (`Outstanding`, templates, etc.) |
| **B — ID-sequenced** | `DECISIONS` (D-NNN), often nested inside Pattern A | Each `<ID> — <title>` plus trailing templates |
| **C — Reference / static** | `HLD`, `LLD`, `BRAND`, `CONTEXT`, `SUBAGENT_PRINCIPLES`, `NEXT` | Topical section names |

---

## Relationship with `docs/`

This project already maintains comprehensive reference documentation in `../docs/` (architecture, api-reference, glossary, data-dictionary, coding-guidelines, runbook, ADRs). The living-memory layer **does not duplicate** these — it cross-references them.

When the canonical content for a concept lives in `../docs/`, the living-memory file:
1. Names the docs/ file as the authoritative source in its purpose blockquote.
2. Captures only the *living-memory* aspect — recent changes, open questions, decision rationale, etc.
3. Points to `../docs/` for the static reference.

Specific mappings:

| Living-memory file | Authoritative reference in docs/ |
|---|---|
| `HLD.md` | [`../docs/architecture.md`](../docs/architecture.md) — module wiring + data flow |
| `LLD.md` | [`../docs/data-dictionary.md`](../docs/data-dictionary.md), [`../docs/api-reference.md`](../docs/api-reference.md), [`../docs/cross-client-invariants.md`](../docs/cross-client-invariants.md) |
| `GLOSSARY.md` | [`../docs/glossary.md`](../docs/glossary.md) — *primary glossary lives in docs/; living-memory glossary is supplementary* |
| `DECISIONS.md` | [`../docs/adr/`](../docs/adr/) — ADRs are the formal decision record; DECISIONS.md mirrors with terser entries |
| `GOTCHAS.md` | [`../docs/runbook.md`](../docs/runbook.md) — operational issues |
| `BRAND.md` | [`../docs/coding-guidelines.md`](../docs/coding-guidelines.md) — voice and engineering discipline |

If `docs/` and `living-memory/` ever conflict, `docs/` wins. Update both.

---

## Markdown Conventions

- **H1** for file title only. **H2** for major sections, **H3** for sub-sections.
- **Tables** for ≥3-item comparisons; bullets for shorter lists.
- **Code blocks** for paths, schemas, commands.
- **No emojis.**
- **Horizontal rules** between top-level sections, not in prose.

---

## Naming and IDs

- **Sequential IDs**: `D-001`, `Q-007`, `M-014`, `G-002`. Zero-padded 3-digit. Never reused. Superseded items get `**SUPERSEDED by D-NNN**` in place.
- **Dates**: ISO `YYYY-MM-DD`.
- **Anchors**: lowercase, spaces → hyphens, special chars stripped. Em-dashes flanked by spaces produce double-hyphens.
- **ADR IDs in `docs/adr/`** follow their own convention; the project hasn't yet established whether `D-NNN` here mirrors ADR numbers or is separate. **Convention chosen 2026-05-21:** `D-NNN` here is independent of ADR numbering; reference ADRs explicitly when relevant.

---

## Cross-References

- Sibling files (same folder): bare filename. `[DECISIONS.md](DECISIONS.md)`.
- Parent-folder files: `../` prefix. `[../docs/architecture.md](../docs/architecture.md)`, `[../context.md](../context.md)`.
- Cite IDs and dates explicitly: `DECISIONS.md §D-005`, `CHANGELOG §2026-05-21`.
- When citing ADRs, use the ADR filename (e.g. *"see `../docs/adr/0001-three-player-matchups.md`"*).

---

## Per-File Required Sections

Beyond the universal header, these sections are required:

| File | Required body sections |
|---|---|
| `CHANGELOG.md` | ≥1 date-indexed entry; `## Outstanding / Known Gaps` |
| `HANDOFF.md` | One "Current State" section; `## Handoff Template (for future sessions)` |
| `NEXT.md` | One "Priority Queue" section; `## Queue Hygiene Rules` |
| `DECISIONS.md` | ≥1 `D-NNN` entry; `## Decision Template (for new entries)` |
| `MISTAKES.md` | ≥1 entry; `## Mistake Template`; `## Cross-cutting Lessons` (optional) |
| `GOTCHAS.md` | ≥1 entry; `## Gotcha Template` |
| `OPEN_QUESTIONS.md` | ≥1 open Q-NNN; `## Closed Questions (kept for cross-reference)`; `## Conventions` |
| `TEST_LEDGER.md` | ≥1 date-indexed entry; `## Tests Planned but Not Yet Run`; `## Verification Discipline` |
| `DEPENDENCIES.md` | ≥1 date-indexed entry; `## Outstanding / Known Gaps` |
| `THIRD_PARTY.md` | ≥1 vendor entry; `## Cost Posture`; `## Renewal / Review Cadence`; `## Outstanding / Known Gaps` |
| `SOURCES.md` | ≥1 source tier; `## Citation Conventions`; `## Outstanding / Known Gaps` |
| `GLOSSARY.md` | Pointer to `../docs/glossary.md`; ≥1 supplementary term group; `## Outstanding / Known Gaps` |
| `PRACTICES.md` | ≥1 practices block; `## The 60-Second Pre-Session Checklist`; `## The 60-Second Post-Session Checklist`; `## Outstanding / Known Gaps` |
| `HLD.md` | `## What This Is`, `## Scope`, `## Non-Goals`, `## System Architecture`, `## Major Components`, `## Key Flows`, `## Design Trade-offs at the System Level` |
| `LLD.md` | Project structural sections; `## Tooling & Constraints` |
| `CONTEXT.md` | `## What This Project Is For`, `## Stakeholders`, `## Boundaries`; `## Outstanding / Known Gaps` |
| `BRAND.md` | `## Voice Charter`, `## Terminology Rules`, `## Formatting Conventions`; `## Outstanding / Known Gaps` |
| `SUBAGENT_PRINCIPLES.md` | `## Core Principles`, `## Checklist for Sub-Agent Reviews`; `## Outstanding / Known Gaps` |

---

## TOC Generation Rules

1. List every H2 in the file (document order) EXCEPT the Table of Contents itself.
2. Anchors: GitHub-auto-rules. `## 2026-05-21 — Voice Charter` → `#2026-05-21--voice-charter`.
3. **Exclude H2s inside code blocks.** Templates are examples, not navigable sections.
4. **Group long ID lists.** >10 IDs → single TOC line linking to the first.
5. Always end TOC with `Outstanding / Known Gaps` when the section exists.

---

## Drift Indicators

A file is **out of compliance** if any of these are true:
1. Missing H1 title or filename mismatch.
2. Missing purpose blockquote, or missing `Purpose:` / `Read at:` / `Write at:` / `Companion files:` labels.
3. No `## Table of Contents` section, or TOC entries don't match actual H2s.
4. TOC anchor links don't resolve (broken anchors).
5. Per-file required sections missing.
6. ID-sequenced gaps/duplicates without `SUPERSEDED` marker.
7. Out-of-order dates in date-indexed file, or non-ISO format.
8. Sibling-file cross-references use absolute paths or `./` prefixes.

Run the `living-memory-format-check` skill to scan and report all drift in one pass.
