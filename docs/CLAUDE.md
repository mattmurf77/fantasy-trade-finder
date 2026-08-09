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
| `references/<site>/<api-name>/` | You reverse-engineer or verify the shape of an **external** API FTF calls (Sleeper, ESPN, MFL, Anthropic, …) — see `references/README.md` (human) / `references/CLAUDE.md` (agent instructions) |
| `recovery/` | You delete a branch or remove a worktree — record tip sha + evidence link in a dated file **before** deleting; procedure in `recovery/CLAUDE.md` |
| `templates/feature-scope.md` (copy, don't edit) | You start ANY feature/change touching user-visible behavior, data collection, schema, or API — copy into the feature's home and fill every section (answer or explicit waiver); mandates the HLD/LLD/api-reference rows and the Maestro + sim-gate declarations (root `CLAUDE.md` §Conventions "Feature gates") |
| `business/` | Not code work — company-ops strategy from the role skills (`/mkt-*`, `/pm-*`, `/an-*`, …); see `business/CLAUDE.md`. Skip unless you're running a role skill. |
| `design/` | Any UI change — read `design-system.md` + `components.md` FIRST, before writing markup/styles; see `design/CLAUDE.md`. |
| `reviews/` | Point-in-time audit snapshots, not current truth — read for context, don't treat as reference; see `reviews/CLAUDE.md`. |
| `plans/` | Active multi-session initiative docs (HLD/LLD/PRD per thread) — see `plans/CLAUDE.md`. Completed plans get archived, not deleted. |
| `code-audit/` | Legacy — one orphaned thread (`trade-calc-improve/`) predating `plans/`; don't add new work here. |

Loose root files: `competitor-teardown-*.md` (4 files) are competitor intel captures — see also `business/product/` for the strategy writeups built on them. `agent-collab-protocol.md` defines how primary/subagent sessions hand off work inside `plans/`.

If you can't tell whether a doc needs updating, scan the table above against your diff. If your change touches `backend/database.py`, the data dictionary is in scope; if it touches routes in `backend/server.py`, the API reference is in scope; etc.

## Not the same thing as `living-memory/`

`docs/` is **reference** — what the system is right now, written as if it had always been that way. [`../living-memory/`](../living-memory/) is **motion** — dated entries for what changed, what's next, what's still open, what bit us.

A change usually touches both: the data dictionary gains the new column (reference), and `living-memory/CHANGELOG.md` gains a dated line saying it was added and why (motion). Don't paste changelog narrative into `docs/`, and don't restate reference material in living-memory — cross-link instead.

**If the two conflict, `docs/` wins.** Fix the living-memory file, not the other way round. Session read/write triggers are in [`../CLAUDE.md`](../CLAUDE.md) §Session memory.
