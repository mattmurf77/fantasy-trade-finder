# <Project Name> — Project Notes for Claude

<one-paragraph orientation>

## Coding guidelines

Follow [docs/coding-guidelines.md](docs/coding-guidelines.md) when writing or editing code. Four principles, in priority order:

1. **Think before coding** — surface assumptions and tradeoffs; ask when unclear.
2. **Simplicity first** — minimum code that solves the problem; no speculative abstractions.
3. **Surgical changes** — every changed line traces to the request; no drive-by refactors.
4. **Goal-driven execution** — define verifiable success criteria; loop until met.

## Stack

<bullets>

## Entry points

<bullets>

## Reference docs (keep current)

Anyone — human or Claude — making changes is expected to keep `docs/` in sync. Quick map:

| If you change… | Update… |
|---|---|
| `<schema file>` schema | [docs/data-dictionary.md](docs/data-dictionary.md) |
| `<routes file>` routes | [docs/api-reference.md](docs/api-reference.md) |
| Env vars / feature flags / runtime tunables | [docs/config-reference.md](docs/config-reference.md) |
| Tokens / enums / thresholds used by multiple clients | [docs/cross-client-invariants.md](docs/cross-client-invariants.md) |
| Backend module wiring or data flow | [docs/architecture.md](docs/architecture.md) |
| New domain term in code or UI | [docs/glossary.md](docs/glossary.md) |
| Operational issue worth recording | [docs/runbook.md](docs/runbook.md) |
| Non-obvious architectural decision | new ADR in [docs/adr/](docs/adr/) |

See [docs/CLAUDE.md](docs/CLAUDE.md) for the full update-trigger table.

## Conventions

<bullets>

## Common tasks

<bullets>
