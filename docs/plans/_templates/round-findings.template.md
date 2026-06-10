---
round: 01
direction: subagent->primary
thread: <thread-slug>
date: YYYY-MM-DD
author: <subagent | feature-evaluator | project-architect | project-reorganizer>
status: open
surface: <backend | web | mobile | extension | cross-client | none>
references:
  - round-01-task.md
---

## Summary
- <3–5 bullet TL;DR>

## Findings
### Task 1: <restate task>
<Diagnosis / research output, organized by task number from the task file. Skill-backed subagents paste their native output here verbatim.>

### Task 2: <restate task>
...

## Proposed Changes
- `[BACKEND]` `backend/<file>.py` — <one-line description and why>
- `[WEB]` `web/<file>` — <one-line description>
- `[MOBILE]` `mobile/src/<file>` — <one-line description>
- `[EXT]` `extension/<file>` — <one-line description>
- `[CROSS-CLIENT]` `docs/cross-client-invariants.md` — <if it changes a shared invariant>
- `[DOCS]` `docs/<file>.md` — <if a reference doc must update per CLAUDE.md table>

## Answers to Questions
1. <Answer to Q1>
2. <Answer to Q2>

## Open Questions
1. <What the subagent needs from primary to proceed>

## Evidence
- `artifacts/<file>` — <what it shows>
- `../../../scripts/<script>` — <what it does>
- `../../reviews/<file>.md` — <related prior review>
