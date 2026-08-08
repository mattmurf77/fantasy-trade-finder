# Handoff — Fantasy Trade Finder

> **Purpose:** forward-looking session handoff. Where am I right now, what's half-done, what's next, what's blocking. Like a doctor's shift handoff sheet — different from CHANGELOG (which is backward-looking).
>
> **Read at:** session start. **Write at:** session end (or before stopping for the day).
>
> Companion files: [`CHANGELOG.md`](CHANGELOG.md), [`NEXT.md`](NEXT.md).

---

## Table of Contents
- [2026-08-08 — Current State (branch 62 behind origin/main; conflicting ESPN pick designs)](#2026-08-08--current-state-branch-62-behind-originmain-conflicting-espn-pick-designs)
- [Handoff Template (for future sessions)](#handoff-template-for-future-sessions)

---

## 2026-08-08 — Current State (branch 62 behind origin/main; conflicting ESPN pick designs)

*This entry was written during a living-memory revival pass, not at the end of the session that did the work. The environment facts below were measured on 2026-08-08; the narrative is reconstructed from git.*

### Where I am right now
- **Branch `teardown-remediation` @ `30492ac`, no upstream configured.** Versus
  `origin/main`: **4 ahead, 62 behind**. All four "ahead" commits have
  cherry-picked twins already on `origin/main` (`c961b7d`, `fb18308`, `9a22432`),
  so there is nothing unique to preserve in them. Local `main` is 354 behind
  `origin/main` and effectively abandoned.
- **`origin/main` @ `e2d0e9e` carries the whole 08-06→08-08 rookie-draft /
  draft-extensions program (W1–W3)** — none of which is in this checkout.
- The last month's work (248 commits, 2026-07-09 → 2026-08-06) is now logged in
  [`CHANGELOG.md`](CHANGELOG.md).

### What's half-done
1. **ESPN pick assignment — TWO INCOMPATIBLE DESIGNS. Reconcile before merging.**
   This is the single highest-risk item in the tree.
   - *Uncommitted here:* new `espn_draft_order` + `espn_pick_overrides` tables,
     routes `GET/PUT /api/espn/draft-order` and `PUT/DELETE /api/espn/picks/override`,
     flag `picks.espn_manual_assign` (**false**), `sync_espn_owned_picks()`,
     `EspnDraftOrderScreen.tsx`.
   - *Already shipped on `origin/main`:* a provenance triple on `draft_picks`
     (`source` / `assigned_by` / `assigned_at`), route `/api/league/pick-assignments`,
     flags `picks.assign` + `picks.assign_tradeable` (**both true**).
   - A rebase onto `origin/main` will collide. Someone has to pick a design.
2. **`trade.finder_config_consolidated`** (flag false) — `trade_type`
   (`1-for-1`…`3-for-2`) and `target_position` as a post-generation filter
   `_filter_by_finder_config` in `generate_trades()`; either field set bypasses
   the shared job cache. Client side is +716 lines in `TradesScreen.tsx`. Docs
   already updated (`api-reference`, `config-reference`, `data-dictionary`).
3. **Untracked, grouped:** `docs/business/{product,marketing,ops}/` (growth-loop
   strategy, App Store pre-launch checklist, ASO reference, competitor
   teardowns); `docs/plans/draft-extensions/` (research only); rookie-draft
   handoff prompts; feedback items 257/260/263; 7 polish-lab mockups; an SVG icon
   contact sheet; `feedback-workspace/` scratch; **12 loose PNG screenshots at
   repo root**; two new backend test files; `.easignore`.
4. **Parallel branch `feedback-fixes-2026-08-08`** — 10 commits ahead of
   `origin/main` (#208, #253–#256/#259, #261, #262, #264), unmerged, living in a
   scratchpad worktree.

### What's blocking me
- **The ESPN design collision needs an operator/author decision** — it cannot be
  resolved by merge strategy.
- Both new flags are default-OFF "until operator review" per `config/features.json`.
- ESPN auto-derived draft order is deferred pending the `rankCalculatedFinal` spike.
- PR #91 (Depth tier color) has been open and stale since 2026-07-04.

### Active environment state
- `python3 -m pytest backend/tests/ -q` → **1466 passed, 1 skipped** (41.7s).
- `cd mobile && npx tsc --noEmit` → **clean, exit 0**.
- ⚠️ **That 1466 is the 62-commits-behind base.** The rookie-draft QA handoff
  cites **1685 passed / 1 skipped on `origin/main` @ `cee4324`**. Don't quote this
  checkout's count as the project's test posture.
- ⚠️ **The working tree mutates during inspection** — tracked-modified count went
  24 → 27 between two `git status` calls. Other agents write here concurrently;
  re-diff before acting on any file list.
- ~40+ agent worktrees under `.claude/worktrees/`. Every one lacks
  `mobile/node_modules` and agents keep independently symlinking the main
  checkout's. `.easignore` exists because 71 worktrees (8.6 GB) pushed the EAS
  archive from 228 MB to 1.2 GB and the upload 400'd.
- App is TestFlight-only: `DTF - Dynasty Trade Finder`, bundle
  `com.fantasytradefinder.app`, ascAppId 6771488431, team N5Y4N2Q49A, v1.11.0.
  Render free tier. First public App Store release is planned, not executed.
- EAS one-shot: `cd mobile && npx eas-cli build --platform ios --profile
  production --auto-submit --non-interactive`. Spaces in the repo path break
  local `expo run:ios` — use the no-space clone at `../ftf-test-clone`. Feedback
  readback: `GET /api/feedback/admin` with `X-Cron-Secret` from `secrets.local.env`.

---

## Handoff Template (for future sessions)

```markdown
## YYYY-MM-DD — Current State

### Where I am right now
- <one or two-bullet snapshot of project state>

### What's half-done
- <each in-flight item, with where the next person picks up>

### What I was about to do next
1. <ordered list, top is highest priority>

### What's blocking me
- <open questions / external waits / decisions pending>

### Active environment state
- <git status, data freshness, env vars, anything that affects "can I just run things">
```

Overwrite each day; do not let this file accumulate. (The history lives in [`CHANGELOG.md`](CHANGELOG.md).)
