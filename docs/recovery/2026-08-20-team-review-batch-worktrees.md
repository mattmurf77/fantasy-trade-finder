# Recovery ledger — 2026-08-20 Team Review batch worktrees

> Per [docs/recovery/CLAUDE.md](CLAUDE.md): capture the tip sha, verify the content
> is on `origin/main`, **then** delete. Never the reverse.

## Session summary

Feedback #364–#376 (operator `mattmurf77`, v1.15.0) worked across one direct session
and four subagents in isolated worktrees. Everything below is merged.

## Verification method

`git merge-base --is-ancestor <branch> origin/main` for each branch — these landed via
**merge commits** (PRs #152/#155/#156/#157/#158), not squashes, so ancestry is valid
evidence here. Run at `origin/main` = `25cc699`.

| Worktree | Branch | Tip sha | Landed via | Ancestor of `main`? |
|---|---|---|---|---|
| `agent-a3ea3b1d38e084930` | `worktree-agent-a3ea3b1d38e084930` | `f7430c4` | PR #155 | ✅ |
| `agent-a4ab94c51456abb78` | `worktree-agent-a4ab94c51456abb78` | `5ccffbe` | PR #155 | ✅ |
| `agent-a7bed877f805980b0` | `worktree-agent-a7bed877f805980b0` | `0a7f791` | PR #155 | ✅ |
| `agent-a85e51536ad1e6eda` | `claude/372-window-composite` | `ba4a6ad` | PR #158 | ✅ |

Integration branches (this worktree), all merged and recorded for completeness:
`claude/team-outlook-experience-27a7a1` `b3f7d92` (PR #152) ·
`claude/team-outlook-ship-record` `3e7e25c` (PR #153) ·
`feat/team-review-batch-2` `f56216e` (PR #155) ·
`fix/finder-conditions-and-partners-copy` `bda0d51` (PR #156) ·
`feat/light-tier-flags` (PR #157) · `feat/window-composite` `bbc2e4b` (PR #158).

## What shipped from them

- **#364/#367/#368** — the inverted sell list (fixed upstream, so Trends moved too), the
  starved partners beat, the IDP disclaimer. PR #152, build 124.
- **#365/#371/#366/#369** — net-firsts signal, playoff-band informing, position-relative
  tiers + RB Handcuff, the rebuilt plan beat. PR #155. `trade.position_tiers` and
  `trade.rb_handcuff` **lit** by operator call in PR #157; the two window flags stay dark.
- **#374/#376** — partners copy defined, and the finder's Filters entry restored on the
  row that replaces the mode bar. PR #156, build 125.
- **#372** — the re-weighted composite window. PR #158, **dark**, no build carries it.

## Not deleted

`jolly-leakey-d20295` is left in place: this session's typechecks symlink
`mobile/node_modules` from it, and removing it would dangle those links. It holds only
untracked docs and is safe to remove once no sibling session depends on it.
