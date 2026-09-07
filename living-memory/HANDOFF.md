# HANDOFF — Fantasy Trade Finder

> **Purpose:** current release state and remaining follow-up.
>
> **Read at:** session start. **Write at:** session end.
>
> Companion files: [TEST_LEDGER.md](TEST_LEDGER.md), [NEXT.md](NEXT.md).

## Current State — 2026-09-07

**Where I stopped:** Team overhaul v1 merged dark: PR #288 → `a8ef182e` on `main`, `overhaul.enabled=false`. iOS **1.17.2 (151)** (EAS `2e13ce3d`) uploaded to App Store Connect from the identical tree. [Status](../docs/plans/team-overhaul/status.md) · [contract](../docs/plans/team-overhaul/BUILD-CONTRACT.md) · [recovery](../docs/recovery/2026-09-07-team-overhaul-release.md).

**In flight:** Apple processing of build 151 only. CI on `main` green (run 34131511501); Render deploy verified (prod flag list carries `overhaul.enabled: false`).

**Blocked on:** operator confirmation of D1 (Sleeper-only sends, copy handoff for MFL/ESPN) and D9 (Acquire card below Team review); the [device checklist](../docs/plans/team-overhaul/QA.md) on build 151, especially the tied-offer step (Sleeper race behavior is `unverified`). Flag stays off until both.

**Don't repeat:** the Fleeced checkout (`codex/team-overhaul-discovery`) is read-only for us. This worktree is detached at `origin/main` and its branch is deleted per the recovery ledger; remove the worktree from the main checkout on the next sweep. Prepare tokens and the refresh throttle are in-process (single worker). Use the repo owner's `gh` token inline for pushes; the machine's default git credential is another account.

## Table of Contents

- [Current State — 2026-09-07](#current-state--2026-09-07)
- [Handoff Template](#handoff-template)

## Handoff Template

Replace the four current-state buckets; link durable evidence instead of accumulating history.
