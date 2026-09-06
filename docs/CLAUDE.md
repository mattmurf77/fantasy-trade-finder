# Documentation routing and maintenance

Follow [the shared agent contract](../AGENTS.md). Current document ownership is listed in [README.md](README.md); update the owning reference when its source changes. Avoid repeating current facts in session memory, plans, business context or provider instructions.

- Schema changes update `data-dictionary.md`; route changes update `api-reference.md`.
- Environment, flags and tuning changes update `config-reference.md`; shared client values update `cross-client-invariants.md`.
- Architecture changes update `architecture.md`; conventions update `engineering-notes.md` or `coding-guidelines.md`. Historical HLD/LLD memory copies are not update targets.
- UI work reads `design/design-system.md` and `design/components.md` before changing source.
- Use `templates/feature-scope.md` for the changes covered by the feature gate; evidence requirements are in `agent-workflow.md`.
- Each initiative/item owns one status source; indexes are generated with `python3 scripts/project_hygiene.py --write` from the repository root.
- Closed or superseded initiatives may move to `plans/archive/<year>/` with a successor/evidence link. Preserve reasoning and recovery history; do not infer completion from age.
- Durable feedback output belongs in `feedback/items/<id>-<slug>/`; private scratch belongs in `_local/feedback/<id>/` at the repository root.
- `research/` and `reviews/` contain observations, not binding current requirements. Read them only when relevant.
- `recovery/` is append-only. Preserve old records and add corrections or migration notices as new dated records.

Maestro and simulator execution remain retired (D-056). Historical flows live in `archive/retired-tooling/mobile/maestro/` at the repository root for testID lint only. The pre-push hook is intentionally a no-op; CI and recorded evidence are the checks. Never run archived capture scripts.
