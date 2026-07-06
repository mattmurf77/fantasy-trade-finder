# docs/ — Notes for Claude

Reference docs for the project. **Treat these as part of the codebase — keep them updated.**

| File | Update when… |
|---|---|
| `data-dictionary.md` | You add/change/remove a table or column in `<schema file>` |
| `api-reference.md` | You add/rename/remove a route in `<routes file>` |
| `glossary.md` | A new domain term appears in code, comments, or UI |
| `cross-client-invariants.md` | You change a value that exists in multiple clients |
| `architecture.md` | You add/remove/re-wire a backend module or change data flow |
| `config-reference.md` | You add an env var, feature flag, or runtime-tunable key |
| `runbook.md` | You hit (or fix) an operational issue worth recording |
| `coding-guidelines.md` | The team adopts a new behavioral rule |
| `adr/` | You make a non-obvious architectural choice |

If you can't tell whether a doc needs updating, scan the table above against your diff.
