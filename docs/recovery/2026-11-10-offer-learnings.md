# 2026-11-10 — Offer learnings and fast deck: build, integration and release branches

Deleted 2026-11-11 (reflog recovery expires about 2027-02-09).

## Builder branches and worktrees

| tip sha | branch | worktree |
|---|---|---|
| `43478baa` | `feat/bilateral-revision-4` | `.claude/worktrees/agent-a3f664ef30fe46cfc` |
| `393b54ce` | `feat/revision-4-round` | `.claude/worktrees/agent-a488da2b93eeda168` |
| `85a3085d` | `feat/trade-outcomes` | `.claude/worktrees/agent-ac5a3cb9ad0788448` |
| `20f8df33` | `feat/sleeper-offer-read` | `.claude/worktrees/agent-ad1079d3e6583cb11` |
| `b69aa951` | `feat/pass-reason-cadence` | `.claude/worktrees/agent-af24d5c993a5c7723` |
| `73eddaf5` | `feat/fit-first-copy` | `.claude/worktrees/agent-ab44fab7aae9094da` |
| `b0a2b4a7` | `feat/fit-block-v3` | `.claude/worktrees/agent-a04660023616346c4` |
| `14beafc0` | `feat/next-move` | `.claude/worktrees/agent-a8299aedcb73d753a` |
| `7b5cea62` | `feat/partner-activity` | `.claude/worktrees/agent-a7a01d5abd9a4bdfe` |
| `0787e8fe` | `docs/send-on-platform` | `.claude/worktrees/agent-a06f963e292527627` |
| `c2dc233b` | `mockups/fit-copy` | `.claude/worktrees/agent-ac8cb7936d1c3c9a9` |

All eleven worktrees were clean (`git status --porcelain` empty apart from gitignored
`mobile/node_modules` where installed); none needed `--force` for uncommitted files.

## Agent scratch branches (no commits of their own)

Created with each builder worktree at the `main` or integration commit of the moment.

| tip sha | branch |
|---|---|
| `462d47f0` | `worktree-agent-a04660023616346c4`, `worktree-agent-a488da2b93eeda168`, `worktree-agent-ac8cb7936d1c3c9a9`, `worktree-agent-ad1079d3e6583cb11` |
| `6017d64b` | `worktree-agent-a06f963e292527627`, `worktree-agent-a3f664ef30fe46cfc`, `worktree-agent-a8299aedcb73d753a`, `worktree-agent-ab44fab7aae9094da`, `worktree-agent-ac5a3cb9ad0788448`, `worktree-agent-af24d5c993a5c7723` |
| `9b14c47b` | `worktree-agent-a7a01d5abd9a4bdfe` |

## Integration and release branches

| tip sha | branch | worktree | remote |
|---|---|---|---|
| `9dca6048` | `feat/trade-engine-rearch` (PR #638) | `.claude/worktrees/trade-engine-rearch` | `origin/feat/trade-engine-rearch` deleted |
| `2fa889ff` | `feat/offer-learnings` (PR #641) | `.claude/worktrees/offer-learnings` | `origin/feat/offer-learnings` deleted |
| `6df59c3f` | `feat/offer-learnings-on` (PR #643) | `.claude/worktrees/offer-learnings-on` | `origin/feat/offer-learnings-on` deleted |
| `6df59c3f` | `feat/offer-import-terms` (local only; fast-forwarded into `feat/offer-learnings-on`) | none | none |
| `13865d73` | detached (`origin/main` at the build) | `.claude/worktrees/release-1.22.0`, the EAS build checkout; clean apart from gitignored `mobile/node_modules` | none |

**Why it was safe:** #641 and #643 merged into `main` with merge commits (`0baf6360`,
`13865d73`), not squashes, so the branch commits themselves are on `main`.
`git merge-base --is-ancestor <tip> origin/main` is true for every sha in the three tables
(checked 2026-11-11 against `origin/main` = `13865d73`), and `13865d73`'s tree equals
`6df59c3f`'s. Each builder branch was merged into `feat/offer-learnings` with a merge commit
before that. Evidence: [TEST_LEDGER](../../living-memory/TEST_LEDGER.md) 2026-11-10 entries for
the integration and the turn-on; [release record](../business/ops/2026-11-10-offer-learnings.md);
PRs #638, #641, #643.

**Not in this sweep:** `docs/offer-learnings-release` in `.claude/worktrees/offer-import-terms`
(the branch carrying this file); `worktree-agent-*` branches and worktrees that belong to other
sessions.

**Recover:** `git branch <name> <sha>`.
