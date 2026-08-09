# Next — Fantasy Trade Finder

> **Purpose:** forward priority queue. 3–7 items, ordered, each with a one-line *why now*.
>
> **Read at:** session start, after CHANGELOG and HANDOFF. **Write at:** when something finishes or priorities shift.
>
> Companion files: [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) for items blocked on external input; [`CHANGELOG.md`](CHANGELOG.md) for what was done.

---

## Table of Contents
- [2026-08-08 — Priority Queue](#2026-08-08--priority-queue)
- [Queue Hygiene Rules](#queue-hygiene-rules)

---

## 2026-08-08 — Priority Queue

*(Refreshed during the living-memory revival pass; the 2026-06-10 queue was fully overtaken and lives in git history.)*

### Immediate

1. **Resolve the two conflicting ESPN pick-assignment designs.** *(author/operator decision, not a merge)* — `teardown-remediation` reimplements a problem `origin/main` already shipped differently. Detail: [`HANDOFF.md`](HANDOFF.md).
2. **Execute the branch-triage verdicts.** *([`../docs/reviews/2026-08-08-branch-triage.md`](../docs/reviews/2026-08-08-branch-triage.md))* — 3 RECOVER are real gaps, 3 ASK need operator calls, 29 DELETEs pinned by worktrees.

### Near-term

3. **Decide `trade.finder_config_consolidated` (flag false).** +716 lines of `TradesScreen.tsx` sit uncommitted; docs already updated as though shipped.
4. **Graduate or kill `deck.value_model`.** The F8 replay harness runs nightly — the gate is checkable now.
5. **Wire up `outlook.odds` or delete it.** Built on both ends, but unreachable — flag absent from defaults.

### Medium-term

6. **First public App Store release.** Checklist in `docs/business/ops/`; TestFlight-only through v1.11.0.
7. **Worktree/disk hygiene.** ~40+ worktrees (8.6 GB) already broke one EAS upload.

### Reserved

- **Browser-extension Chrome Web Store submission** — distribution strategy first (Q-008).
- **Mascot naming (Q-009)** — branding, no code dependency.
- **PR #91** (Depth tier color) — stale since 2026-07-04.

---

## Queue Hygiene Rules
- **Cap at 7 active items.** If you'd be adding an 8th, archive an old one or move it to "Reserved."
- **Each item has a clear *why now*.** Not a wish-list; an actionable next step.
- **Time-horizon labels** ("Immediate / Near-term / Medium-term") make commitment level explicit.
- **"Reserved" items have prerequisites** — note them.
- **After completing an item,** move it to [`CHANGELOG.md`](CHANGELOG.md) with the date and outcome; don't leave checkmarks here.
- **Queue caps at 1.5KB.** Delete superseded items outright (don't mark and keep them); trim any item's prose past ~3 lines while keeping its links.
