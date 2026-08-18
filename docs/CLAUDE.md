# docs/ — Notes for Claude

Reference docs for the project. **Treat these as part of the codebase — keep them updated.**

| File | Update when… |
|---|---|
| `data-dictionary.md` | You add/change/remove a table or column in `backend/database.py` |
| `api-reference.md` | You add/rename/remove a route in `backend/server.py` |
| `glossary.md` | A new domain term appears in code, comments, or UI |
| `cross-client-invariants.md` | You change a value that exists in multiple clients (tier colors, K-factors, gating thresholds, enum strings) |
| `architecture.md` | You add/remove/re-wire a backend module or change the data flow |
| `config-reference.md` | You add an env var, feature flag, or `model_config` key |
| `runbook.md` | You hit (or fix) an operational issue worth recording |
| `coding-guidelines.md` | The team adopts a new behavioral rule worth codifying alongside the Karpathy four principles |
| `adr/` | You make a non-obvious architectural choice |
| `feedback/items/<id>-<slug>/` | You produce durable non-code output for a feedback item's fix (PRD, plan, status, QA findings) — see `feedback/items/README.md`; scratch goes to gitignored `feedback-workspace/<id>/` |
| `integrations/<service>.md` | You add, remove, or change the shape of a call to an **external** service (Sleeper, ESPN, MFL, DynastyProcess, nflverse, Anthropic, Expo push) — one file per service, incl. the safe-to-log / must-redact split the `obs.api_events` instrumentation enforces; see `integrations/README.md` |
| `recovery/` | You delete a branch or remove a worktree — record tip sha + evidence link in a dated file **before** deleting; procedure in `recovery/CLAUDE.md` |
| `templates/feature-scope.md` (copy, don't edit) | You start ANY feature/change touching user-visible behavior, data collection, schema, or API — copy into the feature's home as `scope.md` and fill every section (answer or explicit waiver); mandates the HLD/LLD/api-reference doc rows (root `CLAUDE.md` §Conventions "Feature gates"). **Its §Maestro delta and §Simulator-gate tier are dead sections — skip them** (see below) |
| `business/` | Not code work — company-ops strategy from the role skills (`/mkt-*`, `/pm-*`, `/an-*`, …); see `business/CLAUDE.md`. Skip unless you're running a role skill. |
| `design/` | Any UI change — read `design-system.md` + `components.md` FIRST, before writing markup/styles; see `design/CLAUDE.md`. |
| `reviews/` | Point-in-time audit snapshots, not current truth — read for context, don't treat as reference; see `reviews/CLAUDE.md`. |
| `plans/` | Initiative docs (plan/scope/PRD/HLD/LLD per thread) — see `plans/CLAUDE.md`. **A plan is not evidence anything shipped**; `plans/README.md` carries a status per folder. Nothing here is deleted or archived. |
| `code-audit/` | Legacy — one orphaned thread (`trade-calc-improve/`) predating `plans/`; don't add new work here. |

Loose root files: `competitor-teardown-*.md` (4 files) are competitor intel captures — see also `business/product/` for the strategy writeups built on them. `agent-collab-protocol.md` defines a round-based primary/subagent handoff protocol inside `plans/` that is now legacy — only one thread ever ran it (see `plans/CLAUDE.md`). `web-feedback.html` is a standalone operator feedback form.

## Maestro and the simulator gate are retired (D-056, 2026-08-15)

No Maestro flow authoring, extension, or execution, and no simulator captures — for any change,
in any pipeline. Evidence is now: structural `check-*.js` suites + unit tests; a written,
file:line-cited code-walk proof where a sim capture would have gone; and a concrete manual
TestFlight checklist for the operator where runtime proof matters. `testid-lint` stays in CI;
`FTF_SKIP_SIM_GATE=1` is the standing posture for the pre-push hook. `mobile/.maestro/` flows
are kept, never run.

**Docs in this tree that still mandate the old regime — do not follow them:**
`templates/feature-scope.md` §Maestro delta + §Simulator-gate tier;
`runbook.md` § Pre-ship simulator gate (its 4-tier matrix) and § Mobile UI-test harness;
`plans/mobile-testing/` in full. Any plan or PRD that budgets Maestro work pre-dates 2026-08-15.

**`references/` is empty.** Earlier versions of this file and `README.md` pointed at `references/<site>/<api-name>/` with a `README.md` and `CLAUDE.md` inside. None of those files exist — the directory holds nothing tracked. External-API shape notes go in `integrations/`. (`docs/integrations/README.md` still cross-links `references/`; that pointer is dead too.)

If you can't tell whether a doc needs updating, scan the table above against your diff. If your change touches `backend/database.py`, the data dictionary is in scope; if it touches routes in `backend/server.py`, the API reference is in scope; etc.

## Not the same thing as `living-memory/`

`docs/` is **reference** — what the system is right now, written as if it had always been that way. [`../living-memory/`](../living-memory/) is **motion** — dated entries for what changed, what's next, what's still open, what bit us.

A change usually touches both: the data dictionary gains the new column (reference), and `living-memory/CHANGELOG.md` gains a dated line saying it was added and why (motion). Don't paste changelog narrative into `docs/`, and don't restate reference material in living-memory — cross-link instead.

**If the two conflict, `docs/` wins.** Fix the living-memory file, not the other way round. Session read/write triggers are in [`../CLAUDE.md`](../CLAUDE.md) §Session memory.
