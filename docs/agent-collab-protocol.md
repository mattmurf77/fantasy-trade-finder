# Agent Collaboration Protocol

How the **primary agent** (the top-level Claude Code conversation that owns a work thread) and **subagents** (skill-backed or topic-dedicated conversations like `feature-evaluator`, `project-architect`, `project-reorganizer`, or any ad-hoc topic agent) exchange tasks, findings, proposals, and reviews across separate Claude Code sessions.

The conversation log for each work thread lives **inside the thread's own folder** under `docs/plans/`, so every thread is self-contained and resumable from a cold session.

This protocol is additive — it does not replace the existing systems it sits beside:

| Existing system | Role | Relationship to this protocol |
|---|---|---|
| `CLAUDE.md` + `docs/coding-guidelines.md` | Standing rules every agent follows | Unchanged. Every round implicitly inherits them. |
| `living-memory/HANDOFF.md` | One global cross-session bridge for whatever is most-recently in flight | A thread's `status.md` is its **local** equivalent. `HANDOFF.md` may *point at* the active thread folder when handing off. |
| `living-memory/NEXT.md`, `OPEN_QUESTIONS.md` | Global queues that span the whole repo | Threads can promote items to these queues; they don't replace per-thread state. |
| `docs/adr/` | Architectural decision records | Accepted architectural proposals that survive the thread are promoted into ADRs. The thread's `status.md` links the ADR id. |
| `docs/reviews/` | One-off review outputs (already multi-agent in practice) | A review round inside a thread can publish its summary into `docs/reviews/` for global discoverability. |
| `docs/feedback/` | Inbound feedback collection | Threads triggered by feedback link the source `feedback/*.md` in their plan. |

---

## 1. When a work thread gets its own folder

Convert a flat plan into a folder **as soon as** any of these is true:

- The work will span more than one Claude Code session.
- More than one agent (primary + at least one subagent) will contribute.
- The work needs back-and-forth iteration (research → review → revise).

Single-shot edits stay as flat files in `docs/plans/` like today. Don't fold trivial work into the folder schema.

---

## 2. Folder layout (per work thread)

```
docs/plans/<thread-slug>/
├── plan.md                       # The brief. Mirrors today's flat docs/plans/<name>.md.
├── status.md                     # One-screen current state, primary-owned (mutable).
├── conversation.md               # Append-only index of every round.
├── round-01-task.md              # Primary → subagent
├── round-01-findings.md          # Subagent → primary
├── round-02-review.md            # Primary → subagent (decisions + follow-ups)
├── round-02-findings.md          # Subagent → primary
├── ...
└── artifacts/                    # Diffs, screenshots, query outputs, scratch notes referenced by rounds
```

Naming rules:
- Rounds are zero-padded two-digit (`round-01`, `round-02`, …) so they sort lexically.
- Each round has exactly two files: a `*-task.md` / `*-review.md` (primary → subagent) and a `*-findings.md` (subagent → primary). If a round is a pure data lookup, use `*-question.md` / `*-answer.md`.
- A round is **never edited after it is closed**. Corrections happen in the next round. (Closing means flipping `status: open` → `answered` in frontmatter.)
- Use kebab-case slugs to match the rest of `docs/` (`tiers-drag-coord-fix`, not `TiersDragCoordFix`).

---

## 3. Roles

**Primary agent** (the orchestrator session)
- Owns `plan.md` (the initial brief) and seeds `round-01-task.md`.
- After each subagent round, writes the next `*-review.md` with: (a) accept / reject / defer on each proposed change, (b) follow-up questions, (c) new sub-tasks.
- Owns `status.md` exclusively.
- Decides when to promote outcomes to ADRs, reviews, or `living-memory/` files.
- Decides when the thread is **done** and updates `status.md` accordingly.

**Subagent** (skill-backed or topic-dedicated conversation)
- On session start, reads `status.md` → `conversation.md` → `plan.md` → the latest two round files.
- Executes the task and writes `round-NN-findings.md`.
- Never edits prior rounds. Never touches `status.md`.
- Surfaces blockers under `## Open Questions` at the top of its findings file.
- For skill-backed subagents (`feature-evaluator`, `project-architect`, `project-reorganizer`), the skill's normal output schema is captured verbatim under `## Findings`; the standard frontmatter and headers wrap around it.

---

## 4. Required frontmatter

Every round file starts with YAML so either agent can parse state without reading the body:

```yaml
---
round: 02
direction: primary->subagent          # or subagent->primary
thread: tiers-drag-coord-fix
date: 2026-05-26
author: primary                       # or: subagent | feature-evaluator | project-architect | project-reorganizer
status: open                          # open | answered | superseded
surface: mobile                       # backend | web | mobile | extension | cross-client | none
references:
  - round-01-findings.md
  - ../../adr/0007-coordinate-spaces.md
  - ../../feedback/2026-04-29-web-experience.md
---
```

`surface:` is FTF-specific — it tells reviewers which client(s) the round touches so proposed changes can be routed against `docs/cross-client-invariants.md` when needed.

---

## 5. Standard sections

**Primary → subagent (`*-task.md` / `*-review.md`):**
1. `## Context` — what changed since last round, why this task now
2. `## Decisions on Prior Findings` — accept / reject / defer each proposal, one-line reason (omit on round 01)
3. `## New Tasks` — numbered, each with an explicit acceptance criterion
4. `## Questions` — numbered, expecting answers in the next findings
5. `## Out of Scope` — explicit non-goals
6. `## Touches` — file paths the subagent is authorized to read/write (helps surgical-change discipline from `coding-guidelines.md`)

**Subagent → primary (`*-findings.md`):**
1. `## Summary` — 3–5 bullets, TL;DR
2. `## Findings` — research/diagnosis, organized by task number
3. `## Proposed Changes` — concrete edits, each tagged with surface and target path:
   - `[BACKEND]` `backend/server.py` — <one-line description>
   - `[WEB]` `web/app.js` — <one-line description>
   - `[MOBILE]` `mobile/src/screens/TiersScreen.tsx` — <one-line description>
   - `[EXT]` `extension/content.js` — <one-line description>
   - `[CROSS-CLIENT]` `docs/cross-client-invariants.md` — <if it changes a shared invariant>
   - `[DOCS]` `docs/<file>.md` — <if a reference doc must be updated per CLAUDE.md's "keep current" table>
4. `## Answers to Questions` — numbered, matching the prior round's questions
5. `## Open Questions` — what's needed from primary to proceed
6. `## Evidence` — links to artifacts, scripts, screenshots, query outputs, transcript excerpts

---

## 6. `status.md` schema (primary-owned, mutable)

```markdown
# Status: <thread-slug>

- **Phase:** discovery | iteration | implementation | review | done
- **Current round:** 03
- **Last update:** 2026-05-26 by primary
- **Next action:** subagent to execute round-03 tasks
- **Blockers:** none | <description>
- **Surfaces touched:** backend, mobile
- **Linked feedback:** docs/feedback/2026-04-29-web-experience.md
- **Linked ADRs:** none | docs/adr/0007-coordinate-spaces.md
- **Living-memory updates pending:** none | NEXT.md, OPEN_QUESTIONS.md

## Accepted proposals
- [round-01] Use `measureInWindow` for bin layouts → shipped in commit abc123
- [round-02] Extract `coord-space` helper → queued for `mobile/src/lib/coords.ts`

## Rejected / deferred
- [round-01] Rewrite ScrollView wrapper — deferred, out of scope per coding-guidelines #3

## Doc obligations triggered (per CLAUDE.md update table)
- [ ] `docs/architecture.md` — coord-space helper changes data flow note
- [x] `docs/glossary.md` — added "screen-Y" term
```

---

## 7. `conversation.md` schema (append-only)

```markdown
# Conversation log: <thread-slug>

| Round | Direction | File | Date | Author | Status |
|-------|-----------|------|------|--------|--------|
| 01 | primary→subagent | round-01-task.md | 2026-05-20 | primary | answered |
| 01 | subagent→primary | round-01-findings.md | 2026-05-21 | project-architect | answered |
| 02 | primary→subagent | round-02-review.md | 2026-05-23 | primary | answered |
| 02 | subagent→primary | round-02-findings.md | 2026-05-25 | feature-evaluator | open |
```

---

## 8. Session boot sequence

Any agent (primary or subagent) opening a fresh Claude Code session on a thread reads, in order:

1. `CLAUDE.md` + `docs/coding-guidelines.md` (standing rules)
2. `docs/plans/<thread-slug>/status.md` (where are we?)
3. `docs/plans/<thread-slug>/conversation.md` (round history)
4. `docs/plans/<thread-slug>/plan.md` (original brief)
5. The **latest two round files** (current open round + the one it answers)
6. Older rounds only when explicitly listed in `references:` frontmatter
7. Any docs listed in `status.md` → "Linked ADRs" or "Linked feedback"

This keeps boot context bounded — a 10-round thread doesn't require reading 10 round files to resume.

---

## 9. Round lifecycle

```
[primary writes round-NN-task.md, status: open]
        │
        ▼
[subagent reads → writes round-NN-findings.md, status: open
 primary flips task file status: answered]
        │
        ▼
[primary reads → writes round-(NN+1)-review.md
 findings file status: answered
 status.md updated, conversation.md appended]
        │
        ▼
[loop until primary sets status.md → Phase: done]
```

A round is **closed** only by its recipient (the one whose turn it is to respond).

---

## 10. Closing a thread — promote outcomes

When primary sets `status.md` → `Phase: done`:

1. Add a final `## Outcome` section to `status.md` summarizing what shipped, what was rejected, and where (commits, files).
2. **Promote**, per CLAUDE.md's "keep current" table:
   - Architectural decisions → new ADR in `docs/adr/`
   - Schema changes → `docs/data-dictionary.md`
   - Route changes → `docs/api-reference.md`
   - Cross-client invariants → `docs/cross-client-invariants.md`
   - New terms → `docs/glossary.md`
   - Operational lessons → `docs/runbook.md` and/or `living-memory/GOTCHAS.md`, `MISTAKES.md`
3. Update `living-memory/` where appropriate:
   - `HANDOFF.md` if another thread is taking the baton
   - `NEXT.md` for any follow-up work this surfaced
   - `OPEN_QUESTIONS.md` for anything intentionally left unresolved
   - `CHANGELOG.md` for user-visible behavior changes
4. If the work produced a notable review (security, perf, cross-client), publish a summary into `docs/reviews/` with a date-prefixed filename matching existing convention (`YYYY-MM-DD-<topic>.md`).
5. Leave the thread folder in place. Do not rename or delete — it's the audit trail. Folder rename to `_done-<thread-slug>` only happens with explicit user confirmation.

---

## 11. Cross-thread references

When one thread's findings affect another (e.g. a `feature-evaluator` finding informs a `project-reorganizer` thread):

- Use relative paths in `references:` frontmatter: `../other-thread/round-02-findings.md`.
- Do not copy content between folders.
- The primary surfaces the cross-link in the affected thread's next `*-review.md` under a `## Cross-thread inputs` section.

For *active asks* across threads (not just FYI links), see the future cross-agent bus extension — out of scope for v1 of this protocol.

---

## 12. Skill-backed subagents (FTF-specific notes)

| Skill | Typical task | Author field |
|---|---|---|
| `feature-evaluator` | Score a proposed feature against existing rubrics | `author: feature-evaluator` |
| `project-architect` | Produce or critique an architecture/HLD-LLD slice | `author: project-architect` |
| `project-reorganizer` | Propose folder/file restructures | `author: project-reorganizer` |

When a skill is invoked inside a round, its native output (whatever the skill normally returns) goes verbatim under `## Findings`. The round file's frontmatter + standard sections wrap around it so the thread reads consistently regardless of which skill produced the round.

---

## 13. Templates

Reusable starters live in `docs/plans/_templates/`:

- `status.template.md`
- `conversation.template.md`
- `round-task.template.md`
- `round-findings.template.md`

Copy these into a new thread folder when converting a flat plan to a multi-round thread.

---

## 14. Migration from existing flat plans

For each current file under `docs/plans/`:

- If the work is **done or single-shot** → leave it flat. No migration needed.
- If the work is **in flight and multi-round** → convert to a folder:
  1. `mkdir docs/plans/<thread-slug>/`
  2. Move the flat `<thread-slug>.md` to `docs/plans/<thread-slug>/plan.md`
  3. Create `status.md` and `conversation.md` from templates
  4. Synthesize any prior cross-session work (`.handoff.md`, related `docs/reviews/*`, `docs/feedback/*`) into `round-01-task.md` + `round-01-findings.md`, keeping originals in their current locations and linking via `references:`

Current candidates (as of 2026-06-07) to evaluate for conversion:

| Flat plan | Convert? | Why |
|---|---|---|
| `docs/plans/feedback-backend-sync.md` | Evaluate — likely yes if multi-round expected | Feedback ingestion typically iterates |
| `docs/plans/mobile-feature-parity.md` | Yes | Multi-surface, long-running |
| `docs/plans/mobile-feature-parity-architecture.md` | Fold into the parity thread as `round-01-findings.md` from `project-architect` | Architecture slice of the same work |

Do not migrate without primary-agent + user confirmation per plan.

---

## 15. What this protocol intentionally does NOT do

- Does not replace `.handoff.md` for single-session handoff bridges — `.handoff.md` is global / most-recent-only; `status.md` is per-thread.
- Does not replace `docs/reviews/` for standalone review deliverables — reviews can still live there directly. The protocol only formalizes review *rounds inside* a thread.
- Does not introduce cross-agent message routing (mailboxes, registries, service-agents). That's a v2 extension; see the design notes in the project's planning conversation.
- Does not lint itself. Convention + the boot sequence are enforcement; a lint script can come later if drift becomes a problem.
