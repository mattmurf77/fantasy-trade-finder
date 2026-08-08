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

*(Refreshed during the living-memory revival pass. The 2026-06-10 queue was fully overtaken and is preserved in git history: FB-47 shipped as finder targeting 07-10, the Android `versionName` item was superseded by the bare-workflow native-version fix, engine-threshold tuning was absorbed into the Thompson v2 / deck-engine work of 07-26.)*

### Immediate

1. **Resolve the two conflicting ESPN pick-assignment designs.** *(needs an author/operator decision, not a merge strategy)*
   *Why now:* `teardown-remediation` is 62 commits behind `origin/main` and holds uncommitted work that reimplements a problem `origin/main` already shipped differently. Every day this sits, the rebase gets worse. Detail in [`HANDOFF.md`](HANDOFF.md) §What's-half-done #1.

2. **Reconcile the branch topology.** *(follows from #1)*
   *Why now:* the 4 commits ahead of `origin/main` are already-cherry-picked twins, local `main` is 354 behind, and `feedback-fixes-2026-08-08` has 10 unmerged commits. Nothing in flight is safe to reason about until it's clear which branch is the trunk.

### Near-term

3. **Decide `trade.finder_config_consolidated` (flag false).**
   *Why now:* +716 lines of `TradesScreen.tsx` and a backend filter are sitting uncommitted behind an off flag; docs are already updated as though it shipped.

4. **Graduate or kill `deck.value_model`.**
   *Why now:* the F8 replay harness exists and runs nightly — the gate (replay win on both metrics, ESS≥100, calibration deciles ±20%, then interleave) is checkable now rather than theoretical.

5. **Wire up `outlook.odds` or delete it.**
   *Why now:* `backend/outlook/` and the mobile OddsSection are both built, but the flag is in neither `LAUNCHED_FLAG_DEFAULTS` nor `config/features.json`, so `GET /api/league/outlook` is unreachable dead weight.

### Medium-term

6. **First public App Store release.** Pre-launch checklist is drafted in the untracked `docs/business/ops/`; the app has been TestFlight-only through v1.11.0.

7. **Worktree/disk hygiene.** ~40+ agent worktrees (8.6 GB) already broke one EAS upload and forced `.easignore`. Needs a purge policy, not another one-off.

### Reserved

- **Browser-extension Chrome Web Store submission.** Decide distribution strategy first (Q-008).
- **Mascot naming (Q-009)** — branding, no code dependency.
- **PR #91** (Depth tier color) — open and stale since 2026-07-04; close or merge.

---

## Queue Hygiene Rules
- **Cap at 7 active items.** If you'd be adding an 8th, archive an old one or move it to "Reserved."
- **Each item has a clear *why now*.** Not a wish-list; an actionable next step.
- **Time-horizon labels** ("Immediate / Near-term / Medium-term") make commitment level explicit.
- **"Reserved" items have prerequisites** — note them.
- **After completing an item,** move it to [`CHANGELOG.md`](CHANGELOG.md) with the date and outcome; don't leave checkmarks here.
