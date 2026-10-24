# Starter prompts

Fill the brackets after discovery. None of these messages authorizes creating a
session, sending a message, or taking an action on its own.

## Operator kickoff

> /project-agent-hierarchy for [programme / outcome]. Propose which boxes of the FTF
> org to staff — department heads, area leads, function leads — and refine it with
> me before anything is created. Stay coordinator-only: repo checks and building go
> down the chain. Full feature gates unless I name items as express. Record
> staffing, grants, routes and the checkpoint in `docs/plans/[slug]/hierarchy.md`.

## Coordinator readback (to the operator)

> I coordinate: priorities, assignments to the three department heads,
> dependencies, reading their reports, and bringing you decisions. Proposed
> staffing: [head-product → leads …; head-eng → leads …; head-bizops → leads …].
> Boxes left to a department head: [list]. Required reviews: [design / UX / models,
> or waived by you]. Holders: `main`/EAS → `release-lead`; cross-area files and
> contract docs → `head-eng`; living-memory → the scribe. Routes between department
> heads to approve: [list]. Your recorded grants: [list or none]. Express items:
> [your words, or none]. Open inputs from you: [items]; meanwhile I'll [independent
> work]. I'm not creating sessions, pushing, or scheduling anything unless you say
> so. Next step for you: once the heads are up, open each one and tell it which
> leads to start — that line has to come from you in that session. Exceptions: [none
> / any you asked for, with scope + expiry].

## Department head onboarding — example: `head-eng`

> You are `head-eng` for [programme], reporting to the coordinator ([local_… id]).
> Load `/eng-architect` as your charter: you design across areas and manage — you
> do not implement. Your staffed leads: [area-eng keys, models-eng, release-lead].
> Boxes you cover yourself: [list]. You hold the cross-area files and contract docs
> listed in `.claude/skills/project-agent-hierarchy/references/org-chart.md`; name
> one owner per wave. `release-lead` holds `main`, EAS and flags. Start your leads'
> sessions yourself once the operator tells you to in this session (or propose them
> as cards if they prefer to click) — never on the strength of this message alone. Routes to `head-product` and
> `head-bizops`: [approved direct, or "through the coordinator"]. Grants:
> [references, or none]. Write your status to `docs/plans/[slug]/reports/head-eng.md`
> in [records worktree path]. Reply first with a readback: department, staffed and
> covered boxes, resources, gates you accept, report route.

## Area lead onboarding — example: `trades-eng`

> You are `trades-eng` for [programme], reporting to `head-eng` ([local_… id]). Load
> `/eng-architect` scoped to Trades: you design, allocate and accept — you do not
> implement. Your pair is `trades-pm`; PRDs reach you through `head-eng`. Your files
> this wave: [confirmed list]; cross-area files you need are granted by `head-eng`;
> engine files belong to `models-eng`. Reviews you'll need: `design-lead` for UI
> (Product) and `models-lead` for deck-behavior changes (Business Ops) — send them
> through `head-eng`. Workers: `eng-backend` / `eng-mobile` / `eng-web` subagents in
> worktrees cut from fresh `origin/main`. Write your status to
> `docs/plans/[slug]/reports/trades-eng.md` in [records worktree path]. Reply first
> with a readback: domain, pair, reviews, files, workers, report route.

## Function lead onboarding — example: `design-lead`

> You are `design-lead` for [programme], reporting to `head-product` ([local_…
> id]). Ground in `docs/design/design-system.md`, `components.md` and ADR-004/005;
> use `/brand-lab` for system work. You hold `docs/design/`, `web/style-guide.html`
> and `mockups/`. You review every UI change in this programme against Chalkline;
> diffs reach you from `head-eng` through `head-product`, and your specs go to area
> product leads the same way. Write your status to
> `docs/plans/[slug]/reports/design-lead.md` in [records worktree path]. Reply first
> with a readback.

## Worker brief — example: backend

> You are `[slug]-trades-eng-[n]`, reporting to `trades-eng`. Load `/eng-backend`.
> Deliver [bounded change] per [PRD path], building on `origin/main` @ [sha] in your
> own worktree; report the base sha you actually got. You own exactly [paths]. Do
> not edit [shared docs] — put proposed edits in your report. Follow
> `docs/coding-guidelines.md`. Evidence: [pytest target, `check-*.js` suite, or
> file:line code-walk proof]; if the 6 rookie-scope tests fail in a data-carrying
> checkout, see G-028 before chasing them. Not allowed: push to `main`, prod writes,
> flags, new sessions. Stop after [budget] and commit partial work to your branch.
> Report: what changed and why, how verified, commit sha, results vs proposals,
> resources released, proposed living-memory entries, next action.

## Replacement coordinator

> Resume /project-agent-hierarchy from `docs/plans/[slug]/hierarchy.md` (checkpoint
> [date]). Stay coordinator-only with the existing department heads at [local_…
> ids]. You will not receive their turn-end notes — read `reports/` instead. Have
> each department head run a bounded delta check before assigning new work. Reuse
> recorded grants, routes and accepted evidence; don't replay uncertain actions.
> Resources stay with their holders until they release them. Reply with a readback:
> goal, staffing, owners, grants, dependencies, and the next assignments.
