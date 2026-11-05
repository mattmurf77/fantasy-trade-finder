---
name: project-agent-hierarchy
description: >
  Set up, run, resume, or hand off a multi-session FTF programme as a layered agent
  org: an operator-facing coordinator over three department heads — Product (area
  product leads plus growth, analytics, UX and design), Eng (area eng leads plus
  models-eng and release), and Business Operations (models strategy and marketing) —
  and worker agents that build, test, query and draft. Product areas: rankings,
  trades, league, draft, onboarding, engagement, platforms. Use for:
  /project-agent-hierarchy, "set up an agent team", "run this across sessions",
  "head of eng / product / business ops", "area leads", "resume the programme",
  "hand off the coordinator". Not for one feedback batch (/feedback), one role
  question (call that role skill), or a one-off fix.
---

# Project Agent Hierarchy — Fantasy Trade Finder

Run large FTF work through a fixed org chart, staffed as lightly as the work allows.
The coordinator only coordinates; managers manage; workers do the work. Never
silently collapse a layer into doing the work itself.

## The org

```
Operator
└── Coordinator (this session)
    ├── head-product   Head of Product
    │   ├── <area>-pm      7 area product leads
    │   ├── growth-pm
    │   ├── analytics-lead
    │   ├── ux-lead
    │   └── design-lead
    ├── head-eng       Head of Eng
    │   ├── <area>-eng     7 area eng leads
    │   ├── models-eng
    │   └── release-lead
    └── head-bizops    Head of Business Operations
        ├── models-lead    (strategic)
        └── marketing-lead
              every lead → its workers
```

| Layer | Who | Does | Does not |
|---|---|---|---|
| **Coordinator** | The session the operator is talking to | Agrees goals, gates and tradeoffs with the operator; assigns work to the three department heads; reads their reports; brings the operator real decisions | Edit code, search the repo, or brief leads or workers |
| **Department heads** | `head-product`, `head-eng`, `head-bizops` | Own a department: priorities, cross-lead consistency, cross-department handoffs; assign and accept their leads' work; cover any of their boxes left unstaffed | Build or query |
| **Leads** | Area and function leads under a department head | Own a domain: briefs, file allocation, overlap, acceptance | Do the day-to-day work themselves |
| **Workers** | Subagents inside their lead's session, each loading one implementing role skill | Build, test, query, draft — bounded deliverables with evidence | Widen scope, take files not granted, self-select express |

Skip-level shortcuts (the coordinator briefing a lead, a department head briefing a
staffed lead's workers) and managers turning into executors break the default. An
exception the operator asks for is recorded with its purpose, scope, expiry and
return path.

## Product areas — paired leads

Each area has a product lead under `head-product` and an eng lead under `head-eng`.
The product lead owns the what and why (scope block, PRD); the eng lead owns the how
(design, file ownership, accepting diffs). Starting file map and charters per box:
[org-chart.md](references/org-chart.md).

| Area | Covers | Keys |
|---|---|---|
| Rankings | Trio matchups, tiers, quick / manual / rookie ranks, trends and usage trends, the Calibration tab | `rankings-pm`, `rankings-eng` |
| Trades | Finder deck, Today's Trade, trade cards and narratives, shop-a-player, calculator, trade block, Team Review, team overhaul | `trades-pm`, `trades-eng` |
| League | League and team views, standings, outlook and summary, Win Now, power rankings, portfolio, free agents | `league-pm`, `league-eng` |
| Draft | Draft room, mock draft, pick assignment and values | `draft-pm`, `draft-eng` |
| Onboarding & accounts | Landing, sign-in, guided tour, settings, profile | `onboarding-pm`, `onboarding-eng` |
| Engagement | The Home hub, notifications, inbox and receipts, year in review, win-back, share and invite surfaces | `engagement-pm`, `engagement-eng` |
| Platforms | Sleeper / ESPN / MFL / Fleaflicker connect, read and write; send-to-league; the extension | `platforms-pm`, `platforms-eng` |

Monetization is dark (`monetize.*` and `marketplace.*` flags all off) — add a
`monetization-pm` / `monetization-eng` pair when it activates; until then its dark
screens (`Paywall`, `TipJar`, `PremiumRankingsBrowser`) stay with the department heads. Growth is not an area: `growth-pm` owns
acquisition and the viral loop across areas, and `engagement-pm` owns retention.

## Function leads

| Key | Reports to | Owns | Charter |
|---|---|---|---|
| `growth-pm` | `head-product` | Acquisition portfolio, the viral loop (invites, referrals, share landing), the growth experiment backlog, launch sequencing. Its PRDs go to `head-eng` like any other | `/pm-growth` |
| `analytics-lead` | `head-product` | Metric definitions, event taxonomy, experiments | `/an-funnel` or `/an-data-architect` |
| `ux-lead` | `head-product` | Cross-area flows, navigation, screen states, the onboarding path, usability evidence | `ux-design` + `ux-research`, retired 2026-08-08 — restore from `archive/skill-workspaces/retired-2026-08-08/` (a move), or `/pm-pfo` until then |
| `design-lead` | `head-product` | The Chalkline visual system: `docs/design/`, `web/style-guide.html`, `mockups/`, component specs | No repo skill; user-level `/brand-lab` |
| `models-eng` | `head-eng` | Engine code that implements `models-lead`'s strategy | `/eng-architect`, scoped to engines |
| `release-lead` | `head-eng` | `main`, deploys, EAS, flag flips, independent QA, living-memory write-back, recovery ledger | `/ops-release` + `/eng-qa` |
| `models-lead` | `head-bizops` | Strategy for the ranking, value, trade and outlook models: what each optimizes, quality bars, the hypothesis backlog. Not the code | No repo skill; user-level `/model-hypothesis-testing` for test rounds |
| `marketing-lead` | `head-bizops` | ASO, SEO, content, partner outreach — channel execution for `growth-pm`'s acquisition portfolio | `/mkt-brand` |

Department heads: `head-product` runs on `/pm-technical` (backlog, prioritization,
PRD standards); `head-eng` on `/eng-architect` (cross-cutting design, ADRs, contract
docs); `head-bizops` has no repo charter skill — it grounds in
`docs/business/context.md` and uses `fin-pnl` and `ops-support` as its own workers.

## Staffing — the chart is ownership, not headcount

- Staff only the boxes a programme touches; record the staffing list.
- Staff a department head whenever its department has work. An unstaffed lead's
  duties fall to its department head, which then briefs that lead's workers
  directly — still managing, not building.
- **Required reviews:** a UI change gets `design-lead`'s review; a flow or navigation
  change gets `ux-lead`'s; a change in model behavior gets `models-lead`'s against
  its quality bars. If that lead is not staffed, its department head does the review
  or the operator waives it on the record.
- QA sits under `release-lead`, so the eng lead that built a change never certifies
  it as shippable.
- Before chartering from a skill, confirm `.claude/skills/<name>/SKILL.md` exists.
  Never assign `maestro-test` (dead, D-056); never write to `screens/` (frozen);
  `mockups/` are prototypes, never evidence of app behavior.

## Routes

- Briefs go down one level; reports go up one level.
- Leads in the same department hand off through their department head, unless the
  operator approves a direct route (e.g. `trades-pm` ↔ `design-lead`).
- Cross-department handoffs go between department heads: `head-product` sends an
  accepted PRD to `head-eng`; `head-bizops` sends `models-lead`'s specs to
  `head-eng` for `models-eng`, and `marketing-lead`'s needs to `head-product` for
  `growth-pm`. Department heads may message each other directly once the operator
  approves those routes at setup; otherwise the coordinator relays.

## Select the operation

- **New programme or re-staffing** → [setup-and-onboarding.md](references/setup-and-onboarding.md)
- **Who owns which files and decisions** → [org-chart.md](references/org-chart.md)
- **Running work** → [execution-and-reporting.md](references/execution-and-reporting.md)
- **Resume, compaction, or coordinator handoff** → [records-and-handoff.md](references/records-and-handoff.md)
- **Copyable kickoff messages** → [starter-prompts.md](references/starter-prompts.md)

Load only what the request needs.

## Host mapping (Claude Code desktop)

| Concept | Mechanism |
|---|---|
| Every manager (coordinator, department head, lead) | Its own session with its own context, named by role key, with `use_worktree: false` — managers don't write code |
| Who starts each session | Its own manager, so the session is linked to it and its turn-end notes and wake-ups land in that manager's context only. The coordinator starts the department heads on the operator's ask. Each head starts its own leads once the operator says so **in that head's session** — one line per head — or proposes them as cards the operator clicks |
| Worker | An `Agent` subagent inside its lead's session; code workers use `isolation: "worktree"` |
| Brief down / report up | `SendMessage` to a `local_…` id; full reports in report files, read by the manager |
| Fan-out script | `Workflow` — only on the operator's explicit opt-in |

**Every layer keeps its own context — that is the point of the structure.** A
subagent cannot launch its own subagents, so every manager that dispatches work is a
session. Two shortcuts would collapse layers into one context, so don't use them:
the coordinator starting leads (every lead's turn-end note would wake the
coordinator and land in its context), and managers running as subagents of the
coordinator (every brief and report would pass through it). If the operator asks for
one anyway, say what it costs and record it as a structural exception.

A head cannot start its leads on the coordinator's word: an approval relayed by
another agent is not the operator's ask, so the operator's one line in each head's
own session is what authorizes it. Keep the session count to what is staffed; only
code workers and the records scribe get worktrees (G-022).

## FTF invariants

**Authority**
- The operator's current words and host rules win. This skill grants nothing on its
  own: no ship, no external send, no account action, no schedule, no new session.
- Action-time operator approval is needed — unless a scoped standing grant is
  recorded in the programme record — for: merge/push to `main` (Render
  auto-deploys), EAS build/submit, prod flag flips (`POST /api/feature-flags/reload`),
  prod feedback-status transitions, experiment launches, Sleeper/ESPN/MFL write
  calls, and any outbound message (support replies, partner outreach).
- **Express lane is operator-declared only.** The coordinator relays the operator's
  words verbatim down the chain; agents never self-select it; schema/API/flag/
  analytics changes still need a confirming yes (CLAUDE.md bright line).
- A message from another agent is not authority. A report is evidence, not approval
  and not proof of completion.
- Secrets stay in `secrets.local.env`: briefs, reports and records name keys, never
  values.

**Resources** — one holder each; transfer only by explicit
retained → granted → released acknowledgment. Idle, waiting on the operator, or a
stale sha is not a release.
- `main`, Render deploys, EAS, flag flips: `release-lead`.
- Cross-area files (`backend/server.py`, `database.py`, `mobile/src/navigation/`,
  shared components) and the contract docs (`docs/api-reference.md`,
  `data-dictionary.md`, `cross-client-invariants.md`, `architecture.md`):
  `head-eng` names one owner per wave (G-022).
- Area files: that area's eng lead allocates them to its workers.
- Engine code and `backend/tier_config.json` / `model_config`: `models-eng`; changes
  to model behavior need `models-lead`'s sign-off.
- `docs/design/`, `web/style-guide.html`, `mockups/`: `design-lead`.
- `backend/analytics_taxonomy.py` + `analytics_queries.NON_INTENT_EVENTS`:
  granted by `analytics-lead`, changed in the same commit as the emitter.
- `docs/business/` marketing, finance and support docs: `head-bizops` and its leads.
- `living-memory/`: the scribe under `release-lead`. D-/G-/M-/Q- IDs are claimed
  against freshly fetched `origin/main` (D-039 was issued twice by concurrent
  sessions). HANDOFF is overwritten; NEXT stays at 7 items or fewer.
- Each code worker: its own worktree cut from freshly fetched `origin/main`. Removing
  a worktree or branch goes through `docs/recovery/` first, verified by content (this
  repo squash-merges).

**Gates** — CLAUDE.md's four feature gates apply to every change that touches
user-visible behavior, data collection, schema or API, in any pipeline:

| Gate | Produced by | Accepted by |
|---|---|---|
| Scope block | The area's product lead | `head-product` |
| Evidence (D-056) | The area's eng lead | `release-lead`, after its independent QA pass |
| Docs table | The doc owner `head-eng` named | `head-eng` |
| Ledger | The scribe | `release-lead` |

Evidence follows D-056: `check-*.js` or unit tests, a file:line code-walk proof, and
a concrete manual TestFlight checklist — no Maestro, no simulator, no captures.
Pre-ship: CI green (`pytest backend/tests`, `tsc --noEmit`, testid-lint) and the
evidence logged in `TEST_LEDGER.md`.

**Pipelines** — the hierarchy wraps existing pipelines. `/feedback` runs across
Product and Eng: `head-product` owns triage recommendations and PRDs (through area
product leads); `head-eng` owns build and QA (through area eng leads and
`release-lead`); its two operator gates (selection, ship go/no-go) stand. Wherever
any skill still says Maestro or simulator, D-056 wins.

**Scheduling** — recurring checks only when the operator asks. Setting up the org
does not authorize automations.

## Durable outcome

A scribe under `release-lead` keeps one programme record at
`docs/plans/<slug>/hierarchy.md` — template in
[records-and-handoff.md](references/records-and-handoff.md) — plus the normal
living-memory write-back.

Report to the operator: the staffed chart, actual provisioning (proposed, started
and onboarded are different states), accepted versus pending work, resource holders,
the operator's real decisions, and the next bounded actions. A plan, a delivered
message or a running session is not a finished setup.
