# Recovery ledger — 2026-08-24 feedback wave (PR #198)

> Captured BEFORE deletion per docs/recovery/CLAUDE.md. Status: **CAPTURED; sweep in
> progress this session** — each row flips to SWEPT as it is verified + removed.
> Containment evidence: PR #198 squash-merged to `origin/main` as `fa945925`
> ("Feedback wave 2026-08-24: 5 groups / 11 items"). Verification is BY CONTENT:
> every branch below is an ancestor of the wave branch tip `f7833d56`, whose tree
> the squash `fa945925` reproduces (`git diff f7833d56 fa945925` = empty), so
> ancestry containment in the wave branch = content containment in `main`.

## Wave branch

| Branch | Tip sha | Where | Evidence |
|---|---|---|---|
| `claude/new-user-feedback-55320e` | `f7833d56` | this worktree + origin | squashed to `fa945925`; keep until TestFlight pass, then delete local+remote |

## Build branches (each an ancestor of `f7833d56` via its merge commit)

| Branch | Tip | Merge commit into wave branch |
|---|---|---|
| `feat/fb397-swipe-tour-mobile` | `d42b2a68` | `8576910e` |
| `feat/fb395-rank-chip-mobile` | `71d70153` | `3e403274` |
| `feat/fb386-guide-layout-notify-mobile` | `f39dc359` | `6f7d5a0f` |
| `feat/fb376-outlook-filters-row-mobile` | `f449b1ad` | `dd4329d2` |
| `feat/fb346-quickset-hold-backend` | `259f1e90` | `396fb9c5` |
| `feat/fb395-lineup-impact-backend` | `3e75494e` | `00524c9e` |
| `feat/fb346-quickset-hold-mobile` | `b7742a87` | `c8b0e224` |

## Agent worktrees (hold the build branches above + throwaway `worktree-agent-*` branches)

`.claude/worktrees/agent-ae024cf9f71419eb0` (B build) · `agent-aab468fc28adbf253` (C mobile) ·
`agent-a0746142f0bb36e71` (D build) · `agent-acf3a1f061a2a2bcf` (A build) ·
`agent-a75f033cbdba4f85f` (F backend) · `agent-a552deddf0e710b14` (F mobile) ·
`agent-a69ec9f0959127701` (QA A) · `agent-aded20550541fd84a` (QA B, holds only qa reports —
committed into wave branch at `48f0a043`? NO: QA reports were committed by the orchestrator
in the session worktree; QA worktrees hold no unique content, verified by their agents'
"tree clean" reports).

Scratch (no git content): `<scratchpad>/base-check` temporary worktree — remove with
`git worktree remove --force`.
