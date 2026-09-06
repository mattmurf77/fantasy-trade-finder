# Feedback item documents

Start with the generated [active index](INDEX.md) for work in progress. Search the
[full catalog](CATALOG.md) for prior fixes and duplicate reports. A resolved item can
be absent from the active index and still exist in the catalog.

## Naming and scope

Use `<id>-<slug>/` for a feedback ID. Date-keyed operator asks and named programs are
allowed when no feedback ID exists. These names are distinct identities: retain both
folders when an old ID collision exists and resolve the collision explicitly.

For a fix covering multiple IDs, put the shared plan and evidence in the lowest-ID
canonical folder. Satellite folders retain a `status.md` that names and links the
canonical. Include every covered ID in its summary or evidence. The historical flat
`403-shop-a-player-README.md` pointer is also indexed.

Keep durable scope, PRD, design, review, code-walk, and manual TestFlight evidence here.
Production code belongs in the application tree. Disposable logs and local test data
belong in gitignored scratch, after promoting any assets needed to reproduce findings.
Pre-#64 batches remain in `docs/plans/feedback-batch-2..4/`.

## Status and indexes

Each folder has exactly one current status source: the `project-status` JSON block in
`status.md`. A flat item document carries its own block. Use
[`../../templates/status.md`](../../templates/status.md). Older status prose is retained
as historical evidence; do not keep maintaining competing status variants.

```sh
python3 scripts/project_hygiene.py --write
python3 scripts/project_hygiene.py --check
```

Run these after creating a folder or changing status. CI checks that sources and
generated indexes agree. The generator discovers untracked new homes, initializes
missing status blocks as `needs-review`, and computes counts from the same rows.
Never hand-edit index rows or counts. The old manual index is preserved in
[`../../reviews/2026/2026-09-06-project-status-migration/`](../../reviews/2026/2026-09-06-project-status-migration/).

`needs-review` means missing, conflicting, or unverified disposition; it does not
mean unbuilt. Keep prior merge/flag claims in the evidence text until reconciled.
Record platform-specific release state and unfinished QA honestly; an uploaded iOS
build alone is not proof it reached testers.

## History

The full catalog includes inactive records. If an item is verified inactive, it may
move as a complete folder into `archive/<year>/`, preserving its status and evidence;
update inbound/relative links before regenerating. Do not archive an unresolved item
merely because it is old, and do not remove the only copy of an unmerged fix.
