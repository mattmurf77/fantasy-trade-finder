# Feedback items — per-item work folders

One folder per in-app feedback item, holding **all durable non-code output** for
that item's fix. Prod code never lives here — it flows through branches and PRs
as usual.

## Naming

`<id>-<slug>/` where `<id>` is the feedback item's ID from the feedback table
and `<slug>` is a short kebab-case description, e.g. `62-quick-tier-move/`.
The slug makes directory listings self-describing; the ID keys it back to the
feedback record.

## Expected contents

| File | Purpose |
|---|---|
| `prd.md` | The PRD (contract for build agents), incl. Maestro test plan |
| `plan.md` | Plan for this item (or the batch — see below) |
| `hld-delta.md`, `lld-delta.md` | Feature-path design deltas (vs `docs/architecture.md`); lighter paths fold these into `plan.md` |
| `reconciliation-log.md` | Dual-agent review rounds: objections + resolutions |
| `status.md` | Current state, covered feedback IDs, links to branch/PR |
| `qa-*.md` | QA findings from each QA agent/round |
| screenshots, findings, misc | Anything durable worth keeping |

Not every item needs every file — fast-track bugs may only have a mini-PRD and
QA notes.

## Multi-ID fixes and batches

- A fix spanning several feedback IDs lives under the **lowest** ID; the other
  IDs are listed in that folder's `status.md`.
- Batch runs get one folder per selected item. Batch-level notes (the shared
  `plan.md`, groupings, ship summary) go in the **lowest selected item's**
  folder; every other item's `status.md` cross-links to it.

## Scratch space

Throwaway work (subagent scratch files, test DBs, temp builds) goes in the
gitignored root-level `feedback-workspace/<id>/`, mirrored by the same ID —
never in here.

## History

Work before this convention (items ≤ #63) lives in
`docs/plans/feedback-batch-2/`, `feedback-batch-3/`, and `feedback-batch-4/`.
Those folders stay as-is; don't migrate them.
