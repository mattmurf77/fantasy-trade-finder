# Phase 2 — Build (parallel platform agents, per group)

Set each item `in_progress` (`fetch_feedback.py set <id> in_progress`) as its
group enters this phase.

## Agent topology

- One build agent per platform the PRD touches: **backend** (`backend/`),
  **mobile** (`mobile/`), **web** (`web/`). A group touching one platform gets
  one agent.
- **Ordering:** if backend work is a prerequisite (new/changed endpoints), the
  backend agent runs and finishes first; you review + merge its diff to the
  group branch, and only then launch mobile/web agents so they code against
  real, reviewed endpoints. Client agents run in parallel with each other.
- **Isolation:** each agent gets its own worktree (Agent tool
  `isolation: "worktree"`), branch named `feat/fb<id>-<slug>-<platform>`
  where `<id>` is the group's lowest feedback ID (matching its
  `docs/feedback/items/<id>-<slug>/` folder). File ownership comes from the
  Phase 1 ownership table — repeat it in the agent's prompt as a hard
  boundary. Disjoint ownership is what makes parallelism safe; if two groups
  both need the same file, serialize those groups instead of hoping merge
  works out.

## Build agent prompt must include

- The PRD path (and LLD delta path) — "the PRD is your spec; do not reinterpret
  the original feedback." Include the group's `docs/feedback/items/<id>-<slug>/`
  folder path for context.
- Owned paths (allowed to edit) and forbidden paths.
- Repo rules: `docs/coding-guidelines.md` (think → simplicity → surgical →
  goal-driven), Chalkline design rules for UI (`docs/design/design-system.md`,
  `docs/design/components.md`; never emoji-icons/gradients/blur, radius ≤8px,
  ice=actions flare=info-highlights only), invariants in
  `docs/cross-client-invariants.md` (tier colors/labels from
  `mobile/src/utils/tierBands.ts` — never hardcode).
- Required self-verification before returning:
  - mobile → `cd mobile && npx tsc --noEmit` clean; add `testID`s the PRD's
    Maestro flows need; write/update the Maestro YAML named in the PRD.
  - backend → targeted `pytest` for touched modules + a route smoke against a
    local server if endpoints changed.
  - web → load the page on the local Flask server (`python run.py`), confirm
    no console errors, exercise the changed interaction.
- Known hazards from `lessons.md` relevant to its area (e.g. the Tiers
  gesture-conflict rule: nothing may capture touches from
  `react-native-draggable-flatlist` — that's what broke builds #11/#12).
- Return format: summary of changes, files touched, verification evidence,
  anything it knowingly deviated from the PRD on (and why).

## Orchestrator consistency review (before Phase 3)

Read every diff yourself. You are checking what no single agent can see:

- [ ] Web and mobile implement the **same contract**: same endpoint paths,
      params, enum strings, error handling; same copy for user-facing strings
      unless the PRD says otherwise.
- [ ] No agent edited outside its ownership table.
- [ ] Deviations from the PRD are justified — if a deviation is right, update
      the PRD to match reality (the PRD must stay true; QA tests against it).
- [ ] Schema/route changes have matching doc updates queued (data-dictionary,
      api-reference — the build agent should have done them; verify).
- Merge order: backend → mobile → web onto the group branch
  `feat/fb<id>-<slug>`; run `tsc --noEmit` + backend pytest on the merged
  result. Rejected work goes back to the same agent
  (SendMessage) with your specific objections — don't silently fix it
  yourself unless the fix is trivial; agents learn nothing from silent fixes
  and the diff loses a single author.
