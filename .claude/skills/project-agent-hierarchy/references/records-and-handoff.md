# Records and continuity

FTF already has a memory layer: `living-memory/` for motion, `docs/` for reference
(docs win on conflict — update both). The org adds one programme folder on top of
it; it does not create a parallel memory system.

## Where records live

| Record | FTF home | Writer |
|---|---|---|
| Staffing, registry, authority, tasks, resources, checkpoint | `docs/plans/<slug>/hierarchy.md` (template below) | Scribe |
| Manager status | `docs/plans/<slug>/reports/<role-key>.md`, overwritten each report | That department head or lead |
| Scope blocks, PRDs, design notes, UX and model specs | `docs/plans/<slug>/`, or `docs/feedback/items/<id>-<slug>/` for feedback work | The owning lead's workers |
| Non-obvious decisions | `living-memory/DECISIONS.md`; an ADR in `docs/adr/` if architectural | Scribe; ADRs by `head-eng`'s worker |
| Open questions | `living-memory/OPEN_QUESTIONS.md` | Scribe |
| Session checkpoint | `living-memory/HANDOFF.md` (overwrite) | Scribe |
| Shipped / tested | `living-memory/CHANGELOG.md` / `TEST_LEDGER.md` | Scribe |
| Branch and worktree removal | `docs/recovery/<date>-<slug>.md`, before deleting | Scribe |
| Scratch | gitignored `feedback-workspace/`, or a session scratchpad | Anyone |

The programme folder lives in one **records worktree** the scribe cuts from freshly
fetched `origin/main`; its path goes in the registry. Only the scribe runs git
there; each manager writes only its own report file; the coordinator reads.
`release-lead` lands the records on `main` at each checkpoint — a push like any
other, so it needs the operator's go-ahead or a recorded standing grant for
docs-only pushes. Re-check D-/G-/M-/Q- IDs against `origin/main` before every
landing. Creating the folder also means adding its row to `docs/plans/README.md` in
the same session (`docs/plans/CLAUDE.md`).

Living-memory files follow `living-memory/FORMAT.md` (purpose blockquote, TOC
matching H2s, ISO dates); run `living-memory-format-check` after a large write-back.
Secrets, tokens and private league data are referenced by name, never copied.

## `hierarchy.md` template

```markdown
# <Programme> — agent org

> **Purpose:** live coordination record for <programme>. Written only by the scribe
> (<identity>); manager status lives in `reports/`. Last checkpoint: YYYY-MM-DD HH:MM.

## Objective
- Outcome, success evidence, date:
- Lanes: full gates | express items (operator's words quoted, dated)

## Staffing
- Staffed: <role keys>
- Covered by a department head: <area → head>
- Required reviews waived: <review, operator's words, date>

## Registry
| Role key | Layer | Manager | Charter skill + scope | Identity | Persistence | Current task | Report file | Readback |

## Routes
| From | To | Approved by operator (date) |

## Authority
| Grant | Exact scope | Operator's words + date | Expires |

Structural exceptions (e.g. a lead started by the coordinator): purpose · scope · expiry · return path · context cost

## File map
Confirmed area file ownership, and corrections to org-chart.md's starting map.

## Tasks
| Task ID | Manager | Worker | State | Since | Evidence | Next owner |

## Resources
| Resource | Holder | Scope | sha / value at grant | Pending writes | Released when |

## Decisions and assumptions
| # | Question | Status / answer | Evidence | Impact | Living-memory ID |

## Checkpoint
- Active owners and tasks:
- Current shas (`origin/main`, open branches, records worktree):
- Waiting on the operator:
- Reviews owed (design / UX / models):
- Unverified or out of evidence:
- Next actions (owner → action):

## History
- YYYY-MM-DD — staffing changes, renames, supersessions, coordinator handoffs, swept worktrees
```

## Sources of truth

| What | Authoritative source | Currency check |
|---|---|---|
| Code | `origin/main` after a fetch — never this checkout's branch | Compare shas; content-compare for squash merges |
| Prod data | Render Postgres (`DATABASE_URL_PROD`, read-only for analysis) | Query + timestamp; `data/trade_finder.db` is local, not prod |
| Feedback items | Prod admin API via `.claude/skills/feedback/scripts/fetch_feedback.py` | `list --json` at time of use |
| Feature flags | `config/features.json` on `origin/main` | A flag in the file is not proof it is live — observe it (G-016) |
| Mobile build | EAS / TestFlight build number | EAS build record, not a local version bump (G-012) |
| Event names | `backend/analytics_taxonomy.py` + `analytics_queries.NON_INTENT_EVENTS` | Both in the same commit as the emitter (G-031) |
| Design rules | `docs/design/` + ADR-004 / ADR-005 | `design-lead` owns changes |
| Decisions | `living-memory/DECISIONS.md`, `docs/adr/` on `origin/main` | IDs on `origin/main`, not the working tree |

Keep prepared, attempted and confirmed apart. A derived view (a summary, a report)
is not a new source of truth. Unknown stays unknown.

## Resume or compaction

1. The SessionStart hook has injected living-memory — don't re-read it. Read the
   `hierarchy.md` checkpoint and `reports/` (records worktree, or `origin/main` if
   landed).
2. Re-derive identities from the registry, not from a compacted summary. Confirm
   which managers are live in "Linked sessions now".
3. Have the department heads run bounded delta checks through their leads and
   workers: has `origin/main` moved, are branch bases current, what changed in
   flags, feedback status, holders, or owed reviews.
4. Reuse recorded grants and accepted evidence; never replay an accepted task.
5. The scribe records changed shas, gaps and next owners; resume through the
   existing managers. Ask the operator only what is genuinely new.

## Planned coordinator handoff

- The scribe writes a checkpoint; managers finish an atomic stage or commit partial
  state.
- List held, released and pending resources, uncertain actions, owed reviews, and
  every route.
- A replacement coordinator does **not** inherit linked-session notes — those go to
  the session that started each manager. It reads report files and messages the
  department heads by `local_…` id. Creating the replacement
  session needs the operator's ask.
- Grants made to the old coordinator by role carry over if their scope covers the
  new one; a grant tied to the old session does not. Routes approved by the
  operator stay valid.
- Get a readback from the replacement (goal, staffing, owners, grants, dependencies)
  and settle on exactly one coordinator.
- Changing coordinators does not move resources or managers. `main`, flags,
  worktrees and file allocations stay with their holders until those holders
  release them.

Replacing a department head works the same way one level down: the coordinator
checkpoints it, the new department head reads the old one's report file and its area leads'
reports, and the area leads keep their allocations.

## Abrupt failure

Start from report files and a bounded delta check. Reconcile any uncertain
consequential action before retrying it: read the `origin/main` log before
re-pushing, the EAS build list before resubmitting, the feedback status before
re-setting it. Never seize `main`, a worktree, or another area's files because an
acknowledgment is missing. If the coordinator is gone, the operator names the single
new coordinator; resource holders are unchanged. Missing evidence is not proof of
failure.
