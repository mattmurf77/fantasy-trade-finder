# HANDOFF — Fantasy Trade Finder

> **Purpose:** current release state and remaining follow-up.
>
> **Read at:** session start. **Write at:** session end.
>
> Companion files: [TEST_LEDGER.md](TEST_LEDGER.md), [NEXT.md](NEXT.md).

## Current State — 2026-09-08

**Where I stopped:** two workstreams. (a) **Team overhaul v1** on `main` twice over: `a8ef182e` (feature, dark) and `8cacc1f2` (sends on Sleeper, MFL and ESPN per the owner's D1 revision; D2–D9 owner-confirmed). `overhaul.enabled` is still **false** in production. iOS 1.17.2 (151) uploaded earlier; **1.17.2 (152)** (EAS `032d7ed2`, the all-platform build) submitted to App Store Connect (submission f2719564). [Status](../docs/plans/team-overhaul/status.md) · [owner decisions](../docs/plans/team-overhaul/owner-decisions.md) · [recovery](../docs/recovery/2026-09-07-team-overhaul-release.md). (b) **Owner-only outage:** production has been owner-only since PR #287 (2026-09-07 05:29 UTC) and its first two searches OOM-killed Postgres ([G-072](GOTCHAS.md)). Interim mitigation at 13:55 UTC: `owner_pair_budget` 300, `owner_total_budget` 3000. The fix — paged `save_deck_impressions` — is [PR #289](https://github.com/mattmurf77/fantasy-trade-finder/pull/289) from `claude/owner-only-impression-chunking` (worktree `happy-golick-345cf1`), rebased onto `0d65d1a3`; full suite 5,813 passed / 1 skipped on the pre-rebase tree.

**In flight:** PR #289: exact-head CI, squash-merge, verify Render LIVE on the merge sha, then restore `owner_pair_budget` 4096 and `owner_total_budget` 60000 via `scripts/set_knob.py` and confirm one real search logs `bake-off run … roster=owner_v1` with no `impression logging failed` after it. No TestFlight build needed for it — 1.17.2 (150+) already carries the owner contract. Team overhaul: Render deploy of `8cacc1f2`; Apple processing of 152.

**Blocked on (operator):** the overhaul flag flip so the Acquire card shows — the two-file change (`config/features.json` + `backend/tests/fixtures/flags/release.json`, mirror test passes) is staged uncommitted in the throwaway checkout `/private/tmp/claude-501/ftf-flagflip`; commit there and push to `main`, then run the [device checklist](../docs/plans/team-overhaul/QA.md) on 152. The mitigated owner-only config has not yet been exercised by a real search.

**Don't repeat:** do not read prod Postgres directly (the auto-mode classifier blocks it; the Render logs API is enough). Do not roll back to the comparison arms — the operator chose to keep owner-only live. Do not turn a deck cap back on as the fix: the paged insert is the fix, the budgets are a stopgap. Per-row duplication of `owner_generation` / the `config` block is a NEXT follow-up, not this PR. The Fleeced checkout (`codex/team-overhaul-discovery`) is read-only for us. Both overhaul release branches are deleted per the recovery ledger; that detached worktree holds nothing unique — remove it (and `ftf-flagflip` once pushed) on the next sweep. Never interpolate shell variables into a heredoc that contains backticks. Pushes: `gh` on this Mac is switched to `mattmurf77` with `gh auth setup-git` (2026-09-08); the allow rules for `git push` / `gh pr` / `gh auth switch` are in `.claude/settings.local.json`, and compound `&&` commands still get classified — run each as its own command. Prepare tokens and the refresh throttle are in-process (single worker).

## Table of Contents

- [Current State — 2026-09-08](#current-state--2026-09-08)
- [Handoff Template](#handoff-template)

## Handoff Template

Replace the four current-state buckets; link durable evidence instead of accumulating history.

**Where I stopped:** …

**In flight:** …

**Blocked on:** …

**Don't repeat:** …
