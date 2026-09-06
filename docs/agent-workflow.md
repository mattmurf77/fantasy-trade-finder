# Agent workflow

Read for changes and releases; [AGENTS.md](../AGENTS.md) is the shared entry contract. This replaces repeated root/context/static-memory rules. Historical records do not override this workflow or the operator's current instructions.

## Scope, evidence, documentation

The default for changes to user-visible behavior, data collection, schema, or API is **scope → evidence → canonical docs → ledger**.

1. Copy [feature-scope.md](templates/feature-scope.md) into the initiative and fill each applicable section. Record waivers with reasons and surface them before build. Specify analytics against the taxonomy before adding emitters.
2. Validate mechanically checkable behavior with unit tests and/or structural checks. Record file/line-cited code traces where inspection is the evidence. For runtime uncertainty, write a concrete manual TestFlight checklist with actions and expected results. D-056 retires all Maestro authoring/execution and simulator captures; historical plans do not revive them.
3. Update each affected canonical reference once, using the table below. Record relevant `n/a` reasons in the scope. `living-memory/HLD.md` and `LLD.md` are compatibility pointers, not parallel update targets.
4. Record results and evidence in the initiative and [TEST_LEDGER](../living-memory/TEST_LEDGER.md). Distinguish run/passed/waived/unexecuted. A code trace is not runtime evidence.

**Operator-declared express lane:** “quick fix,” “just ship it,” or an explicit request to skip gates may waive the scope block, evidence delta, and docs table. Leave `express: <what shipped> — gates skipped by operator` in the ledger. Agents never self-select express; resolve a genuinely ambiguous declaration with the operator. CI, secrets rules, and recovery still apply. Schema, API contracts, feature-flag surfaces, and analytics events exceed a routine quick fix: if express is requested, explain that scope and obtain explicit confirmation. Existing explicit authorization persists; do not ask again for an already confirmed choice.

## Canonical update targets

| Change | Update |
|---|---|
| Database tables/columns | [data-dictionary.md](data-dictionary.md) |
| API route/contract | [api-reference.md](api-reference.md) |
| Module wiring, lifecycle, data flow | [architecture.md](architecture.md) |
| Env vars, flags, runtime knobs | [config-reference.md](config-reference.md) and source configuration |
| Shared constants/enums | [cross-client-invariants.md](cross-client-invariants.md) and consumers |
| Domain vocabulary | [glossary.md](glossary.md) |
| External-service call shape | [integrations](integrations/README.md) |
| Operations | [runbook.md](runbook.md) |
| Architectural choice | [ADR](adr/README.md); link it from the decision log rather than repeating it |
| Product/business decision | [overview](product/overview.md) or [business context](business/context.md) |
| UI/copy | [design](design/design-system.md), [components](design/components.md), [voice](product/voice.md) |

Settled contracts belong in canonical references; implementation evidence and unresolved questions stay with the initiative. [Engineering notes](engineering-notes.md) routes older contracts to their owners.

## Engineering conventions

- Follow the four [coding principles](coding-guidelines.md): think before coding, simplicity, surgical changes, verifiable goals. Source-adjacent instructions describe local patterns.
- Flags are shared through `config/features.json`; do not invent independent client flags. Register analytics events in `backend/analytics_taxonomy.py` and classify them in `analytics_queries.NON_INTENT_EVENTS` in the same change as the emitter.
- Local DB is `data/trade_finder.db`; production uses `DATABASE_URL`. Use SQLAlchemy Core. Keep tunables in established configuration. Consult manifests and [integration docs](integrations/README.md) before dependency changes.
- UI uses Chalkline tokens/specs. No emoji icons, decorative gradients/blur, generic system-font substitutions, or new accent palette. Ice signals actions; flare highlights information; position/tier colors encode data. Radius limits and mascot exceptions are defined in design/component instructions.
- Mobile tab screens inherit one global `FeedbackFAB`; root-stack pushes mount their own with `aboveTabBar={false}`. A second tab FAB recreates #196/#197. Pinned bottom bars use `setPinnedBottomBarHeight`. Modals/sheets and onboarding are exceptions.
- Mockups are prototypes, never imported product code. Captures are dated historical evidence, not proof of current rendering. Label comparison baselines; current visual acceptance comes from relevant device/build evidence.

## Files, credentials, collaboration

- Durable feedback output: `docs/feedback/items/<id>-<slug>/`; groups use the lowest ID and satellites link to the owner. Initiative docs: `docs/plans/`. Gitignored `feedback-workspace/<id>/` is scratch, never the sole home of decisions or release results.
- Give parallel collaborators bounded tasks, canonical references, and one owner per edited file. Review their diffs and evidence. The same gates apply to agent-generated and direct work.
- Credentials belong in gitignored `secrets.local.env`; read only required keys, never print or commit them. If needed values are missing, have the operator fill that file. Never copy credential backups/local settings into review artifacts. Synthetic seed/demo scripts must not target production.
- Search tracked files or relevant directories. Exclude dependencies, archives, and nested worktrees by default. Historical local paths are breadcrumbs, not portable commands.

## Release and recovery

Start new work from freshly fetched `origin/main`; inspect for other sessions' work. Preserve unrelated dirty state and use isolation when needed. Pushing `main` deploys backend/web through Render; EAS/App Store Connect distributes mobile separately. Honor the operator's scope for merge, deployment, TestFlight submission, flag flips, and cleanup.

Before merge/push, require green current CI and record evidence. CI includes backend pytest, mobile typecheck/test-ID/structural guards, and web checks; `.github/workflows/ci.yml` is authoritative, not copied test counts. The retired simulator pre-push hook is a no-op; no bypass variable is needed.

Before deleting a branch/worktree, record its tip SHA in [recovery](recovery/CLAUDE.md), verify content against `origin/main`, and cite evidence. Squash merges mean ancestry/ahead-counts alone do not establish safety. Capture first; inspect uncommitted files before considering a forced operation. Complete authorized post-ship sweeps, but preserve operator-excluded worktrees. The 2026-09-06 organization cleanup explicitly excludes existing nested worktrees.

## Session write-back

Keep HANDOFF to four current-state buckets and NEXT to seven linked actionable items. [Memory format](../living-memory/FORMAT.md) defines byte caps/history retention. Log meaningful changes/checks before context runs out. Decisions/gotchas/questions allocate `max + 1` IDs; check first and coordinate writers. Promote settled knowledge into its canonical reference rather than another static memory copy.
