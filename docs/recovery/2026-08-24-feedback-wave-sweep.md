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
`agent-a69ec9f0959127701` (QA A) · `agent-aded20550541fd84a` (QA B). The QA worktrees held the
ten `qa-round-1-agent-*.md` reports as untracked files — recovered pre-sweep, merged `c3791051`
(see Sweep results below).

Scratch (no git content): `<scratchpad>/base-check` temporary worktree — remove with
`git worktree remove --force`.
## Sweep results (same session, post-ship)

- PR #198 squash-merged as `fa945925`; Render deploy `dep-da6apgbncjis73d3lsag` verified LIVE on
  that sha via the Render API (created + status polled — not an uptime probe). EAS 1.16.5
  uploaded to App Store Connect (Apple processing).
- QA reports were NOT in the wave branch (written in the QA agents' worktrees) — recovered
  before removal and merged as `c3791051` (PR #201). The ledger's earlier "committed by the
  orchestrator" note was wrong; corrected here.
- **SWEPT:** all 8 agent worktrees + the scratch `base-check` worktree removed; the 7 `feat/fb*`
  build branches (all ancestry-verified into `f7833d56`, whose tree `fa945925` reproduces
  byte-identically) and the 8 `worktree-agent-*` branches (all at base `cce3895f`) deleted.
  `docs/qa-reports-feedback-wave-0824` deleted locally after merge.
- **KEPT:** `claude/new-user-feedback-55320e` local+remote (delete after the operator's
  TestFlight pass) and its worktree `trading-engine-eval-8ab7bc` (this session's cwd — next
  session removes it).
- **Incident (M-005):** a pattern-based deletion took out 8 HISTORICAL `worktree-agent-*`
  branches beyond this wave's scope before being stopped by pipe buffering. All 8 tips captured:
  `a001577c06e787e27@ff6bbe7d` `a003570b9b30c442c@5c290646` `a020c27835001fa28@5326f78a`
  `a02624f706e100949@803a908e` `a03655cb82e1f8838@8bee7f7d` `a03d44942e7798ff0@6da3dad5`
  `a047fa94@f93c76af` — all seven ancestors of `origin/main` (content-contained, no restore
  needed) — and `a05d00e6@dddb1ff8` (2026-04-29, NOT contained) which was **restored** as a
  branch and remains for the standing branch-triage backlog.
