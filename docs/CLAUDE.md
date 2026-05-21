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

If you can't tell whether a doc needs updating, scan the table above against your diff. If your change touches `backend/database.py`, the data dictionary is in scope; if it touches routes in `backend/server.py`, the API reference is in scope; etc.
