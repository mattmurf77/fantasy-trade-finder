# HANDOFF — Fantasy Trade Finder

> **Purpose:** current release state and remaining follow-up.
>
> **Read at:** session start. **Write at:** session end.
>
> Companion files: [TEST_LEDGER.md](TEST_LEDGER.md), [NEXT.md](NEXT.md).

## Current State — 2026-09-07

**Where I stopped:** Team overhaul v1 on `main` twice over: `a8ef182e` (feature, dark) and `8cacc1f2` (sends on Sleeper, MFL and ESPN per the owner's D1 revision; D2–D9 owner-confirmed). `overhaul.enabled` is still **false** in production. iOS 1.17.2 (151) uploaded earlier; **1.17.2 (152)** (EAS `032d7ed2`, the all-platform build) submitted to App Store Connect (submission f2719564). [Status](../docs/plans/team-overhaul/status.md) · [owner decisions](../docs/plans/team-overhaul/owner-decisions.md) · [recovery](../docs/recovery/2026-09-07-team-overhaul-release.md).

**In flight:** CI on `main` for `8cacc1f2`; Render deploy of it; Apple processing of 152.

**Blocked on (operator):** the flag flip so the Acquire card shows — the two-file change (`config/features.json` + `backend/tests/fixtures/flags/release.json`, mirror test passes) is staged uncommitted in the throwaway checkout `/private/tmp/claude-501/ftf-flagflip`; commit there and push to `main`. The session's permission classifier refused that push. Then run the [device checklist](../docs/plans/team-overhaul/QA.md) on 152.

**Don't repeat:** the Fleeced checkout (`codex/team-overhaul-discovery`) is read-only for us. Both release branches are deleted per the recovery ledger; this worktree is detached at `origin/main` and holds nothing unique — remove it (and `ftf-flagflip` once pushed) from the main checkout on the next sweep. Never interpolate shell variables into a heredoc that contains backticks (an unquoted heredoc executed a backticked command on 2026-09-07). Use the repo owner's `gh` token inline for pushes. Prepare tokens and the refresh throttle are in-process (single worker).

## Table of Contents

- [Current State — 2026-09-07](#current-state--2026-09-07)
- [Handoff Template](#handoff-template)

## Handoff Template

Replace the four current-state buckets; link durable evidence instead of accumulating history.
