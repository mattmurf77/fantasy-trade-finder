# Sources — Fantasy Trade Finder

> **Purpose:** the catalog of *authoritative* external materials this project draws from. The "where the truth lives" file. When a claim needs grounding or a dispute needs settling, consult this list before inventing or guessing.
>
> **Read at:** when a claim needs citation, before quoting external material, when an outside reference is needed.
> **Write at:** when a new authoritative source is discovered or an existing one becomes stale.
>
> Companion files: [`THIRD_PARTY.md`](THIRD_PARTY.md), [`DEPENDENCIES.md`](DEPENDENCIES.md).

---

## Table of Contents
- [2026-05-21 — Source Inventory](#2026-05-21--source-inventory)
- [Citation Conventions](#citation-conventions)
- [Outstanding / Known Gaps](#outstanding--known-gaps)

---

## 2026-05-21 — Source Inventory

### Tier 1 — Internal records (authoritative for this project)

| Source | Role |
|---|---|
| [`../README.md`](../README.md) | Public project description |
| [`../CLAUDE.md`](../CLAUDE.md) | Operator's brief for Claude — convention/scope rules |
| [`../context.md`](../context.md) | Detailed orientation (overview, stack, architecture, current state, open items) |
| [`../docs/CLAUDE.md`](../docs/CLAUDE.md) | The update-trigger table for `docs/` files |
| [`../docs/architecture.md`](../docs/architecture.md) | Authoritative module wiring and data flow |
| [`../docs/data-dictionary.md`](../docs/data-dictionary.md) | Authoritative DB schema |
| [`../docs/api-reference.md`](../docs/api-reference.md) | Authoritative HTTP route reference |
| [`../docs/cross-client-invariants.md`](../docs/cross-client-invariants.md) | Constants that must stay in sync across clients (colors, K-factors, enums) |
| [`../docs/glossary.md`](../docs/glossary.md) | Domain vocabulary |
| [`../docs/runbook.md`](../docs/runbook.md) | Operational runbook |
| [`../docs/coding-guidelines.md`](../docs/coding-guidelines.md) | Karpathy four principles + project-specific discipline |
| [`../docs/adr/`](../docs/adr/) | Formal architecture decision records |
| [`../docs/plans/`](../docs/plans/) | In-flight design plans |
| [`../docs/feedback/`](../docs/feedback/) | Captured user feedback |

### Tier 2 — External providers (truth for data they publish)

| Source | URL pattern | Authoritative for |
|---|---|---|
| **Sleeper API** | `api.sleeper.app/v1/...` | User profiles, leagues, rosters, players, traded picks |
| **DynastyProcess GitHub CSV** | github.com/dynastyprocess/data | Consensus dynasty trade values |
| **Anthropic Claude API docs** | docs.anthropic.com | Model availability, pricing, API behaviors |
| **Sleeper public docs** | docs.sleeper.app | Sleeper API contracts and changelog |

### Tier 3 — Methodology references (academic / industry)

| Source | Topic |
|---|---|
| Elo rating system (Arpad Elo) | Foundational pairwise rating math |
| Bradley-Terry model | Extension of pairwise to N-player ranking |
| Plackett-Luce model | Alternative N-player rank-distribution model |
| Information theory (KL divergence per swipe) | Quantifying info gain per matchup |

### Tier 4 — Community / public sources (lower authority; cross-check)

| Source | Topic |
|---|---|
| Reddit `/r/DynastyFF` | Community-discussed trade values; sanity-check our own output |
| KeepTradeCut / FantasyCalc | Alternative consensus-value sources for sanity-checking DynastyProcess |
| Dynasty-focused Twitter accounts | Player news, depth chart movements (especially during the season) |

### Tier 5 — Sister projects / pattern source

| Source | Role |
|---|---|
| [`../../Master Claude Code Best Practices/`](../../Master%20Claude%20Code%20Best%20Practices/) | Source of the living-memory pattern (HLD, LLD, FORMAT, SESSION_PROTOCOL, MEMORY_SWEEP) |
| [`../../pga-championship-ownership-2026/living-memory/`](../../pga-championship-ownership-2026/living-memory/) | Reference adoption of the pattern in a sister project |

---

## Citation Conventions
- **Internal docs:** relative markdown link. If the doc's title doesn't make its claim obvious, summarize the claim in the sentence that links it.
- **External provider data:** name the endpoint and the date observed when possible. Sleeper data can shift in-season.
- **Methodology refs:** cite by author/year if known; link to an implementation (e.g. SciPy's Bradley-Terry) otherwise.
- **Community refs:** treat as informal; never use as sole authority for a claim.

---

## Outstanding / Known Gaps
- DynastyProcess methodology page link not captured here; the CSV is the data, but the project's stated methodology lives on a webpage we should link.
- No structured Sleeper API contract — we operate on observed behavior + sparse docs. Versioning policy unclear.
- Methodology references (Elo, Bradley-Terry, Plackett-Luce) are stub citations; if any becomes load-bearing for a real algorithm choice, capture the specific reference.
