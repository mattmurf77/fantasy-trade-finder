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

0a. **Verify #289 on the Dependables MFL league (62846).** *(5 minutes, live now)*
   *Why now:* it is the acceptance criterion the shipped batch never executed.
   Pass = franchise + player names; escalate = a high rate of `Player <mfl_id>`
   placeholders (stale player cache, not a code defect). The originally-proposed
   10% fallback bar was removed — real corpora measure 49%, so report the rate
   rather than gating on it. Detail in [`HANDOFF.md`](HANDOFF.md).

0b. **Run a mock draft in ffv3 and judge the board.** *(5 minutes, live now)*
   *Why now:* the engine shipped unflagged. If the top still reads wrong it is a
   **consensus values** question — Tate is the board's #2 rookie, so 4th is a
   two-slot fall — and belongs in a new item, not a reopened #290.

0c. **Decide the `feature_flags.py` `_load_from_env` hardening.** *(operator)*
   *Why now:* the patch is drafted and unapplied. It makes a malformed
   `FTF_FLAGS` fail loudly instead of silently returning `{}` — but `FTF_FLAGS`
   is a live Render kill-switch lever, so this turns a typo in a prod env var
   into a boot failure. Genuinely a blast-radius call, not a code-quality one.

0d. **Make the sim gate runnable end-to-end, or stop claiming it.** *(sized, not started)*
   *Why now:* the harness is honest for the first time (three flag-pin defects
   plus a bash-3.2 `$!` bug fixed and proven this session) — but the mock flow
   still cannot execute: `seed_ui_test_db.py` writes nothing for `mock_drafts`
   or draft status, and d1/d2/d3 target a league in no profile. Either fund the
   seeder work or drop the flows so the gap is visible instead of implied.

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
