# Dependencies and source ownership

This is a navigation map, not a second dependency lockfile, price list, API manual, or current release snapshot.

| Concern | Canonical source |
|---|---|
| Python dependency versions | `requirements.txt`, `requirements-dev.txt`, `.python-version` |
| Mobile dependency versions/build config | `mobile/package.json`, lockfile, `mobile/eas.json`, `mobile/app.json` |
| Runtime feature/environment configuration | [config reference](../config-reference.md), source configuration |
| Third-party call shapes/auth/errors | [integrations](../integrations/README.md) |
| Local/prod database behavior and deploy procedures | [schema](../data-dictionary.md), [runbook](../runbook.md), [architecture](../architecture.md) |
| Vendor costs/renewals | Current operator invoices/contracts and dated [finance records](../business/finance/) |
| Product/business claims | [overview](overview.md), [business context](../business/context.md) |
| Domain terminology | [glossary](../glossary.md) |

Sleeper, ESPN, MFL, DynastyProcess, Anthropic, Expo, and other providers have distinct contracts. Verify the integration used by the actual caller; do not infer sole-provider dependence from the old Sleeper-only design. Model APIs and external data are optional or gated where the implementation says so.

For external claims, record source, observation date, and scope. Prefer official provider documentation for documented APIs and captured wire evidence for undocumented behavior. Community posts are leads, not sole authority. Methodology names such as Elo, Bradley–Terry, or Plackett–Luce are not citations by themselves; retain the specific paper/source if it informs a decision.

Historical inventories and unresolved observations remain in [DEPENDENCIES](../../living-memory/archive/static-2026-09-06/DEPENDENCIES.md), [THIRD_PARTY](../../living-memory/archive/static-2026-09-06/THIRD_PARTY.md), and [SOURCES](../../living-memory/archive/static-2026-09-06/SOURCES.md). Their prices, row counts, deployment claims, and local-machine paths are dated evidence. Validate a relevant observation against code/current sources before promoting it into the references above.
