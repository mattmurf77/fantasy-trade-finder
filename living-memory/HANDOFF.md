# Handoff — Fantasy Trade Finder

> **Purpose:** forward-looking session handoff. Where am I right now, what's half-done, what's next, what's blocking. Like a doctor's shift handoff sheet — different from CHANGELOG (which is backward-looking).
>
> **Read at:** session start. **Write at:** session end (or before stopping for the day).
>
> Companion files: [`CHANGELOG.md`](CHANGELOG.md), [`NEXT.md`](NEXT.md).

---

## Table of Contents
- [2026-08-10 — Feedback batch #289-#294 shipped; two verification gaps left open](#2026-08-10--feedback-batch-289-294-shipped-two-verification-gaps-left-open)
- [Handoff Template (for future sessions)](#handoff-template-for-future-sessions)

---

## 2026-08-10 — Feedback batch #289-#294 shipped; two verification gaps left open

### Where I am right now

**Everything shipped.** `main` @ `7553874`. Six feedback items merged as `6c304c7`
(PR #103), CI green; native version bump as `7553874` (PR #104). Backend and web
are **live and verified in production by content** — `/api/feature-flags` serves
`league.picks_always_counted = true`, which only the new build can produce.
iOS **1.12.0 build 98** uploaded to App Store Connect (submission `0095a36f`),
processing at Apple. All six items set `fixed`.

### The two things a next session should actually do

1. **Verify #289 against the Dependables MFL league (62846).** This is the
   acceptance criterion the batch never executed — it is live now and checkable.
   Open its Draft Room. **Pass** = franchise names, not `mfl:62846.f0001`; player
   names, not bare numbers. **Escalate** = a high rate of `Player <mfl_id>`
   placeholders, which indicates a stale player cache, **not** a code defect (the
   fallback is deliberate and greppable: `^Player \d+$`). The 10 %-fallback bar
   the PRD originally proposed was removed — replaying all four corpora measured
   **49 %**, five times that bar, so a rate gate would have failed on first
   contact with real data. Report the measured rate; the three absolute FAILs
   (empty name, bare id, raw `mfl:` in an owner cell) remain hard stops.
2. **Run a mock draft in ffv3 and judge the top of the board.** The engine is
   live and unflagged. If it still reads wrong, that is now a **consensus values**
   question (Carnell Tate is the board's **#2** rookie — his going 4th is a
   two-slot *fall*, not a reach), not a draft-logic one. Open it as a new item
   rather than reopening #290.

### What is NOT verified (do not read the green suite as covering these)

- **No end-to-end simulator run on any of it** — operator-directed bypass,
  recorded in [`TEST_LEDGER.md`](TEST_LEDGER.md).
- `mobile/.maestro/flows/rookie/d3-mock-draft-loop.yaml` is **authored but
  unrunnable**: `backend/tests/fixtures/profiles/standard.json` declares one
  league (`990000000000000001`) while d1/d2/d3 target `1312140920132497408`,
  which is in no profile, and `seed_ui_test_db.py` writes **nothing** for
  `mock_drafts` or draft status. A build agent's "one `leagues[]` entry" estimate
  was checked and is **wrong** — this is real seeder work.
- G3's **R-5** and **R-0.4** have no automated coverage, and the kill-switch
  drill **T-S6c** is manual.
- #289 has no Maestro flow by design (the harness has no MFL seam at all —
  zero MFL refs in `test_users.py` / `qa/`).

### Traps this session cost real time to find — don't re-learn them

- **`mobile/app.json` does not ship a version.** Bare workflow: EAS reads the
  native Xcode project. Build 97 shipped as 1.11.0 with `app.json` saying 1.12.0.
  Bump **all three**: two `MARKETING_VERSION` in `project.pbxproj` +
  `CFBundleShortVersionString` in `Info.plist`. `eas build:version:set` sets the
  **build number only**.
- **The pre-ship sim gate had never once run.** Every prior ledger entry says
  "NOT PERFORMED", which is why three flag-pin defects survived plus a bash-3.2
  `$!` bug that fired the stale-Flask assertion on a **clear** port every time
  and orphaned Flask between runs. All repaired this session, each proven by
  constructing the failure first. The gate is now honest — and untried.
- **Never symlink the main checkout's `mobile/node_modules` into a worktree.**
  It is ~190 commits stale and lacks `@react-native-cookies/cookies`, producing
  a phantom `tsc` error. Run `npm ci` in the worktree.
- **`origin/main` moved four times during this batch** (`7cea1fa` → `16b1dcb` →
  `36618be` → merged). One agent worktree came up carrying four commits from a
  concurrent session. **Check every agent branch's base before merging.**
  A concurrent session also rewrote `LeagueSummaryScreen.tsx` — the same file
  G3 rewrote — and git auto-merged it cleanly. Clean ≠ correct: the
  71-assertion AST check is what proved the merge was actually sound.
- **Commit each group's spec at its Phase 1 exit, not on a shared timer.** G2's
  build agent branched from a commit holding only Round 1 of its own PRD and had
  to reconstruct the contract from code. It did so correctly, but that was
  diligence covering an orchestrator sequencing error.

### Active environment state

- `python3 -m pytest backend/tests/ -q` → **2329 passed, 1 skipped** on merged
  `main`. `npx tsc --noEmit` → clean. `testid-lint.sh` → exit 0. **9/9**
  `mobile/tests/check-*.js` pass.
- Flags now ON in prod: `league.picks_always_counted` (new, kill switch),
  plus the pre-existing `draft.mock` / `draft.mfl` / `draft.room` / `draft.tab`.
- Worktrees for this batch are swept; shas captured in
  [`../docs/recovery/2026-08-10-feedback-289-294-deletions.md`](../docs/recovery/2026-08-10-feedback-289-294-deletions.md)
  **before** removal, verified by content (each agent branch an ancestor of
  `feedback-289-294`, whose tree is byte-identical to `origin/main`).

### Open, not blocking

- `all-on.json` pins **41 of 154** flags — the name is misleading for anyone
  choosing it as a flag-boundary baseline. Reported, unfixed.
- `backend/feature_flags.py` `_load_from_env` swallows a malformed `FTF_FLAGS`
  and returns `{}`. Hardening it is drafted but **unapplied**: `FTF_FLAGS` is a
  live Render kill-switch lever, so raising turns a typo in a prod env var into
  a boot failure. **Operator decision, deliberately left open.**
- Only `maestro-testid-lint` runs the `check-*.js` family in CI; the other eight
  are local-only.
- #205 (design-tenets interview) still parked awaiting operator answers.

---
