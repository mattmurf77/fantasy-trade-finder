# Feedback items — per-item work folders

One folder per in-app feedback item, holding **all durable non-code output** for
that item's fix. Prod code never lives here — it flows through branches and PRs
as usual.

**Start at [INDEX.md](INDEX.md), not at a directory listing.** There are ~130 folders;
the index is the duplicate-check and status surface.

## Naming

`<id>-<slug>/` where `<id>` is the feedback item's ID from the feedback table
and `<slug>` is a short kebab-case description, e.g. `62-quick-tier-move/`.
The slug makes directory listings self-describing; the ID keys it back to the
feedback record.

**Two exceptions exist in the tree, both intentional:**

- **Date-keyed folders** (`2026-07-26-asset-trade-ideas/`, `2026-08-02-rankings-import/`, …)
  — operator asks captured in-session that never got a feedback-table row. Keyed by the
  date they were filed. Listed in `INDEX.md` with `—` in the id column.
- **Named programs** (`api-observability/`, `espn-webview-escape/`) — operator-directed
  work with no feedback id at all, run through the same pipeline. Same rule: a `status.md`
  and an INDEX row.

Prefer a real id when one exists; these forms are for work that genuinely has none.

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

### Wave/group folders (the current shape)

Large waves group items and nominate a **group canonical folder** — the lowest id in
the group, holding the full doc set (`scope.md`, `plan.md`, `prd.md`, `hld-delta.md`,
`lld-delta.md`, `reconciliation-log.md`, `review-round-N.md`, `status.md`). Every other
member of the group gets a folder with a `status.md` only, whose header names the group:

```
# FB-323
- **Status:** planned 2026-08-16
- **Group:** G2 — Mock draft room UI
```

The 2026-08-16 wave is the reference example: canonicals `304` (G6), `321` (G5), `322` (G2),
`328` (G3), `330` (G4), `334` (G9); satellites `323`–`327`, `335`, `336`, `339`–`341`.
Its branch/worktree ledger is `docs/recovery/2026-08-16-feedback-wave-sweep.md` — written on the wave's own branch and not yet on `main`, so it is absent here until that merges.

## Scratch space

Throwaway work (subagent scratch files, test DBs, temp builds) goes in the
gitignored root-level `feedback-workspace/<id>/`, mirrored by the same ID —
never in here.

## History

Work before this convention (items ≤ #63) lives in
`docs/plans/feedback-batch-2/`, `feedback-batch-3/`, and `feedback-batch-4/`.
Those folders stay as-is; don't migrate them.

## Status line format

To keep [INDEX.md](INDEX.md) generatable by reading only the first ~15 lines
of each folder's `status.md`, every **new or updated** `status.md` must open
with a status line as its first non-title line:

```
**Status:** <shipped|built-dark|in-progress|planned|mockup-only|research-only|open|declined> · YYYY-MM-DD · <branch/PR/flag>
```

- Exactly one status token from the enum above. (`planned` was added 2026-08-18 —
  the 2026-08-16 wave introduced it for "spec written, build not started", which
  `open` didn't cleanly cover.)
- Date is the date that status became true (build date, ship date, decision
  date) — not the file's last-edit date if they differ.
- Last field is whatever locates the work: a branch name, a PR number, a
  flag key, or `n/a` if none applies.

**INDEX.md must be updated in the same session** as any status.md change —
new item, status flip, merge confirmed, flag flipped. A stale INDEX.md
defeats the whole point of Phase-0 reading it instead of the folders.

This format applies going forward only. The ~105 existing `status.md` files
predate it and are **not** being rewritten — their prose stays as history.
`INDEX.md`'s rows for those items were derived by reading their existing
(non-conforming) first lines, not by requiring this format retroactively.

### Known drift (2026-08-18)

`INDEX.md`'s last row is **#286**. Every folder from **#289 onward has no row** —
roughly 35 items, including the whole 2026-08-16 wave (#304, #321–#341) and the
`#289`–`#300` mock-draft/league-rankings set. The "update in the same session"
rule above has not been held since 2026-08-09, so the index's row count and its
status-distribution table both understate the tree. Anyone doing a Phase-0
duplicate check on an id above 286 must fall back to `ls docs/feedback/items/`
until it is regenerated.
