# docs/

Project reference material. Start here when you need to look something up.

**Anyone changing the project (humans or Claude):** keep these docs current with your code changes. See [CLAUDE.md](CLAUDE.md) for the per-file update triggers.

## Root reference docs

| Doc | What it covers |
|---|---|
| [data-dictionary.md](data-dictionary.md) | Every DB table, column, type, and lifecycle |
| [api-reference.md](api-reference.md) | All `/api/*` routes by feature area |
| [glossary.md](glossary.md) | Domain terms (Elo, K-factor, tier bands, outlook, etc.) |
| [cross-client-invariants.md](cross-client-invariants.md) | Values that must stay in sync across backend/web/mobile/extension |
| [architecture.md](architecture.md) | Component diagram + request lifecycles |
| [config-reference.md](config-reference.md) | Env vars, feature flags, runtime `model_config` |
| [runbook.md](runbook.md) | Local dev, deploy, debug, common failures |
| [coding-guidelines.md](coding-guidelines.md) | Behavioral guardrails (Karpathy four principles) |
| [agent-collab-protocol.md](agent-collab-protocol.md) | How primary/subagent Claude sessions hand off work inside `plans/` |
| [web-feedback.html](web-feedback.html) | Standalone form that ingests operator feedback into `feedback/` |
| [competitor-teardown-dynastydealer.md](competitor-teardown-dynastydealer.md) | DynastyDealer iOS app teardown |
| [competitor-teardown-dynastygm.md](competitor-teardown-dynastygm.md) | DynastyGM (Dynasty Nerds) mobile app teardown |
| [competitor-teardown-ti-calc.md](competitor-teardown-ti-calc.md) | Friend's TI-CALC trade calculator teardown |
| [competitor-teardown-web-tools.md](competitor-teardown-web-tools.md) | FantasyCalc, Dynasty Daddy, and 3 other web trade-tool teardowns |

## Subdirectories

| Dir | What's in it |
|---|---|
| [adr/](adr/) | Architecture decision records |
| [business/](business/) | Company-ops strategy deliverables from the role skills — not code work |
| [code-audit/](code-audit/) | Legacy, mostly superseded by `plans/` — one orphaned thread remains |
| [design/](design/) | Chalkline design system: tokens, component specs, brand doc — read before any UI work |
| [feedback/](feedback/) | In-app feedback queue + per-item fix folders (`items/`) |
| [plans/](plans/) | Active multi-session initiative docs (HLD/LLD/PRD per thread) |
| [recovery/](recovery/) | Branch/worktree deletion ledger — capture tip sha before deleting |
| [references/](references/) | Reverse-engineered shape of external APIs FTF consumes (Sleeper, ESPN, MFL, …) |
| [reviews/](reviews/) | Point-in-time audit snapshots — dated, not current truth |
| [templates/](templates/) | `feature-scope.md` — copy into a feature's home before building |
