# Memory format and retention

Purpose: keep session orientation small while retaining decisions and evidence. This supersedes the [old format](archive/static-2026-09-06/FORMAT.md), including its conflicting universal-TOC rules.

## Enforced current-state limits

`python3 scripts/session_context.py --check` validates:

- `HANDOFF.md`: at most **2,000 UTF-8 bytes**, one `## Current State` section, with **Where I stopped**, **In flight**, **Blocked on**, and **Don't repeat** buckets. Replace; do not accumulate dated handoffs.
- `NEXT.md`: at most **1,500 UTF-8 bytes**, one `## Priority Queue`, and at most **seven** items in a flat numbered list. Start each item at column one with `1. action` (incrementing numbers are allowed); bullets, `1)` markers, and nested lists are rejected. Indented continuation text is allowed; fenced examples are not queue entries. Each item is one next action with its reason/evidence link. Do not append old queues or completed work.
- Hook output: at most **6,000 UTF-8 bytes including JSON envelope and newline**. Emit complete sections only. Missing/oversized sections yield labelled source pointers. Do not truncate paragraphs, code fences, or a multibyte character to fit.

The default text command and `--hook` use the same content selection. The hook reads only its explicit memory-file allowlist and never executes document text. No credentials, environment dumps, or source-tree scan are part of startup.

## History and retrieval

- CHANGELOG keeps the newest ten dated entries; use brief outcomes and durable evidence links. Rotate older entries into a dated archive with original headings/anchors. Preserve a pointer to the archive.
- HANDOFF/NEXT are replaceable summaries. Before a large consolidation, preserve the full source snapshot; unresolved queue entries are not canceled or implicitly approved by rotation.
- DECISIONS remain addressable by D-ID; supersede explicitly instead of deleting a decision. Keep formal choices in ADRs and link rather than repeat their content.
- GOTCHAS/MISTAKES remain searchable on demand. A large index is not automatically injected; the brief points to it. Put the symptom, scope, and resolving evidence together.
- TEST_LEDGER contains evidence, not unsupported pass counts. Older evidence may rotate by date with stable archive pointers; no historical run is upgraded to current proof.
- OPEN_QUESTIONS records operator answers and unresolved decisions. A summary does not replace the original answer or grant authorization.
- Static memory files are compatibility pointers. New architecture/API/schema/config material goes into canonical docs; voice into `docs/product/voice.md`; dependency details into manifests/integration references.

## Writing conventions

Use H1 titles, descriptive H2 sections, ISO dates, and relative links. Long reference logs benefit from an index; short briefs and pointers do **not** require a TOC, boilerplate purpose block, or template. H2-like lines inside fenced code are examples, not sections. IDs allocate `max + 1` after checking existing entries; coordinate concurrent writers.

Archived snapshots are historical evidence, excluded from default retrieval. Their README states original locations; old links and machine paths may describe that original setting. Current instructions come from AGENTS.md and docs/agent-workflow.md.
