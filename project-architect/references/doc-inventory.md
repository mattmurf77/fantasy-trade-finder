# Doc Inventory + Update Triggers

The canonical set of files produced by this skill, the source-of-truth file each derives from, and the code change that should trigger an update.

| Doc | Source of truth | Update trigger |
|---|---|---|
| `docs/data-dictionary.md` | DB schema file (e.g. `backend/database.py`, `prisma/schema.prisma`) | Add/rename/remove table or column |
| `docs/api-reference.md` | HTTP route definitions (`backend/server.py` or route modules) | Add/rename/remove route |
| `docs/glossary.md` | Code comments, UI strings, `model_config` keys | New domain term enters code or UI |
| `docs/cross-client-invariants.md` | Tokens/enums/thresholds duplicated across clients | Change a value that lives in 2+ clients |
| `docs/architecture.md` | Backend module structure, request lifecycles | Module added/removed/re-wired; data flow changes |
| `docs/config-reference.md` | Env var reads, feature-flag file, `model_config` defaults | New env var, flag, or tunable key |
| `docs/runbook.md` | Deploy config, cron config, operational endpoints | New cron job, deploy step, common failure mode |
| `docs/coding-guidelines.md` | Karpathy four principles | Team adopts a new behavioral rule |
| `docs/adr/<NNNN>-*.md` | Decision moment | Non-obvious architectural choice |
| Root `CLAUDE.md` | This inventory | Inventory changes |
| Folder `CLAUDE.md` + `README.md` | Folder contents | Folder purpose shifts |

## Self-check after Bootstrap

Pick three reader questions and confirm each is answered by exactly one doc:

- "What's in the `swipe_decisions` table?" → `data-dictionary.md`
- "Where do I add a new route?" → `api-reference.md` + `architecture.md`
- "What does K-factor mean and where's it set?" → `glossary.md` + `config-reference.md`

If a question is answered by zero docs, add a section. If answered by two with conflicting detail, one becomes the source and the other links to it.
