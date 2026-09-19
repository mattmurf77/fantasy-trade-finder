# docs/feedback/

Durable non-code output from the in-app feedback pipeline (`/feedback` skill).
The live queue itself is the backend feedback table, not a file in here.

| Path | What it is |
|---|---|
| [items/INDEX.md](items/INDEX.md) | **Start here.** One row per item folder: id, slug, status, date, where the work lives. The duplicate-check surface — read it instead of globbing ~130 folders. **Stale below the line:** rows stop at #286; everything from #289 on is missing. |
| [items/README.md](items/README.md) | The folder convention: `<id>-<slug>/`, expected contents, multi-ID and wave/group rules, the `status.md` header format |
| [items/](items/) | The item folders themselves |
| [backlog.md](backlog.md) | Items the operator **deferred** rather than rejected — kept with enough context to pick up cold. Rows are deleted when the work is picked up. |

Historical intake/audit snapshots at this level, not the current queue:
[`inbox.md`](inbox.md) (TestFlight capture log, ids 21–48),
[`2026-04-29-web-experience.md`](2026-04-29-web-experience.md),
[`perf-audit-2026-05-21.md`](perf-audit-2026-05-21.md).

Scratch work goes in the gitignored root-level `feedback-workspace/<id>/`, never in here.
Batches before item #64 stay in [`../plans/feedback-batch-2/`](../plans/feedback-batch-2/),
[`-3/`](../plans/feedback-batch-3/), [`-4/`](../plans/feedback-batch-4/) as history.
