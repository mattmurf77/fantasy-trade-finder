# Initiative documents

Start with the generated [active index](README.md). Use the [full catalog](CATALOG.md)
only for duplicate checks or historical research. A plan records intent; shipped code,
API/schema references, and release evidence establish actual behavior.

## One status source

Every initiative folder has `status.md` with one `project-status` JSON block.
A flat Markdown plan carries the block in the document itself. Copy the format from
[`../templates/status.md`](../templates/status.md). Historical prose below the block
is evidence, not a second live status. Never edit an index row manually.

After adding an initiative or updating its status:

```sh
python3 scripts/project_hygiene.py --write
python3 scripts/project_hygiene.py --check
```

The generator includes new and untracked folders/files, initializes missing records
as `needs-review`, and produces both indexes from those records. It never infers
release state from a flag name, document title, file date, or a legacy "built" claim.
Unknown dates stay blank. Check the evidence before resolving a migrated status.
The previous manual index is preserved in
[`../reviews/2026/2026-09-06-project-status-migration/`](../reviews/2026/2026-09-06-project-status-migration/).

## New work

- Prefer one initiative folder with `status.md`, `scope.md`, `plan.md` or `prd.md`,
  and supporting evidence only when needed. Do not create HLD/LLD variants by default.
- For user-visible, schema, API, or data-collection changes, complete
  [`../templates/feature-scope.md`](../templates/feature-scope.md) before building.
- Per-feedback-item fixes belong in [`../feedback/items/`](../feedback/items/).
  Pre-#64 feedback batches remain here as historical groups.
- Strategy belongs in `docs/business/`; point-in-time reviews in `docs/reviews/`;
  product contracts and runtime reference details belong in their canonical docs.
- `_templates/` and `docs/agent-collab-protocol.md` describe a retired round protocol.
  Do not initiate new work through that protocol.

## Closing and archiving

Record the actual outcome and evidence in `status.md`, promote lasting decisions and
reference changes, and update session memory. A shipped claim requires release/merge
evidence and must preserve remaining platform or QA limitations in the evidence text.

Verified inactive initiatives may move to `archive/<year>/<slug>/` (flat plans to
`archive/<year>/<slug>.md`). Preserve the status source and reasoning trail, update
relative and inbound links, and regenerate both indexes. Archive status is independent
of release status: abandoned work was not shipped. Do not bulk-archive plans whose
current disposition is uncertain, or delete unmerged implementation evidence.

Archived homes appear only in the full catalog. `shipped`, `deferred`, `superseded`,
`abandoned`, `declined`, and `reference` records are also excluded from normal active
retrieval. `needs-review` remains visible until evidence resolves the uncertainty.
