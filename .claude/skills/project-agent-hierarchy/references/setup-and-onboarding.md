# Setup and onboarding

## Discovery — ask only what changes the plan

The SessionStart hook has already injected HANDOFF, NEXT, the top CHANGELOG entries
and the GOTCHAS index. Infer from those and from the operator's message before
asking anything. Then ask, in one bundle, only for what is genuinely missing:

- **Outcome and success evidence** — what "done" looks like (shipped to `main`, a
  TestFlight build, a decision memo, a number moved) and any date it is tied to.
- **Areas touched** — which product areas and function leads the work reaches. This
  sets the staffing list.
- **Lanes** — full gates by default; which items, if any, the operator declares
  express. Never propose express yourself.
- **Sessions** — every head and lead gets its own session. Confirm the operator is
  ready for the coordinator to start the heads, and whether they will start leads
  with a line in each head's session or by clicking the head's cards. An existing
  session can be reused only if its context is clean for the role.
- **Routes** — whether the three department heads may message each other
  directly, and whether any leads in the same department may.
- **Standing grants** — e.g. "push to `main` after my go/no-go", "flip `<flag>` in
  prod". Record each with its exact scope; anything not granted stays action-time.
- **Retired charters** — whether to restore `ux-design` / `ux-research` if
  `ux-lead` is staffed.
- **Visibility** — how often and how briefly the operator wants status.

Propose the staffing list while answers are pending: a department head for each
department with work, area leads only for areas with sustained work, and function
leads (growth, analytics, UX, design, models, marketing, release) only where their
work or review is needed.

## Delegated inventory

The coordinator does not inventory the repo. `head-eng` (or `head-product`, for
product-only work) assigns a bounded inventory worker — an `Explore` subagent is
enough — to report:

- `origin/main` sha after a fresh fetch, and how far this checkout lags it.
  Concurrent sessions are normal here; the checked-out branch is often stale.
- Whether the starting file map in [org-chart.md](org-chart.md) still holds for the
  areas being staffed — new modules, moved screens, renamed files.
- Existing work on the topic: `docs/plans/<slug>/`, `docs/feedback/items/`, NEXT
  items, open branches and worktrees, linked sessions.
- Whether each reported problem still reproduces on current `origin/main` (G-023:
  testers report against the shipped binary, which lags the repo).
- Current holders: anything mid-ship, flags mid-rollout, experiments running,
  worktrees not yet swept.
- Settled calls in `living-memory/DECISIONS.md`, abandoned approaches in
  `MISTAKES.md`, and questions already in `OPEN_QUESTIONS.md` that touch the work.

Search with `git grep` or scoped paths, never repo-wide. Do not run builds, imports,
deploys, EAS, or prod writes to learn state. Label historical snapshots as history
and current observations with their time.

## Role charter

One per staffed box; the scribe writes them into the programme record.

- **Role key, layer, manager:** e.g. `trades-eng`, area lead, `head-eng`
- **Charter skill and scope:** e.g. `/eng-architect`, scoped to Trades
- **Owns / does not own:** decisions and files, from [org-chart.md](org-chart.md)
  as confirmed by inventory
- **Pairs with / reviews needed from:** e.g. `trades-pm`; `design-lead` for UI
- **Inputs:** PRD or scope-block path, `origin/main` sha, relevant D-/G- IDs
- **Outputs and acceptance evidence:**
- **Permitted actions; operator grants referenced; excluded actions:**
- **Resources held:** files, shared docs, `main`, flags — with grant scope
- **Identity:** session `local_…` id + name, and the manager session that started it
- **Report file and triggers:** what events send a report (accepted, blocked, needs
  the operator)
- **Assumptions, structural exceptions, expiry:**

Role keys route responsibilities; `local_…` ids and agent ids route tools. Session
titles are labels, not identities — keep rename history in the record.

## Provisioning order

1. The coordinator starts the department heads on the operator's ask — each its own
   session, `use_worktree: false`, onboarded with its charter and staffing list.
2. The operator opens each head's session and tells it which leads to start — one
   line per head (e.g. "start trades-pm, trades-eng and release-lead"). That is the
   operator's own ask in that session, so the head starts its leads itself and each
   lead is linked to its own head: the lead's turn-end notes and wake-ups go to the
   head, never to the coordinator. If the operator prefers clicking, the head
   proposes its leads as cards instead. Confirm the links in the head's "Linked
   sessions now" note.
3. Each lead spins up its workers as subagents inside its own session (code workers
   in worktrees).
4. The scribe (a worker under `release-lead`) cuts the records worktree and writes
   the registry.

Proposed, started and onboarded are separate states — record each.

## Routes

| Sender | Recipient | What must be true |
|---|---|---|
| Coordinator | Department head | A session it started, or one the operator named |
| Department head | Its leads | A session it started on the operator's word in its own session, or a card of its that the operator started |
| Any lead | Its workers | Subagent results return to the lead directly |
| Worker / lead | Its manager | A result, a turn-end note, or the report file the manager reads |
| Department head | Another department head | Only on a route the operator approved at setup; otherwise via the coordinator |
| Lead | Another lead in its department | Through its department head, unless the operator approved a direct route |
| Lead | A lead in another department | Always through both department heads |

An agent asking to be messaged back is not the operator's permission. Creating a
session, messaging a session and taking an action are three separate authorities.

## Onboarding acceptance

Ask each new role for a readback before assigning work:

- A **department head** restates its department, staffed and unstaffed boxes (which
  it covers itself), resources held, the gates it accepts, and its report route.
- A **lead** restates its domain, pair, required reviews, workers, resources held,
  and report route.
- A **worker** restates its deliverable, manager, files owned, evidence required,
  stop conditions, and where its report goes.

A successful send is delivery, not comprehension. Correct a wrong readback through
the same route — each manager corrects its own reports.
