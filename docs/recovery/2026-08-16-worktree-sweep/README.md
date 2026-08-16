# Worktree sweep — 2026-08-16

> Worktrees with no commit since the [2026-08-08 branch triage](../../reviews/2026-08-08-branch-triage.md).
> Deletion date: **2026-08-16**. Reflog recovery expires ~90 days after this date.

Motivation: 40 registered worktrees holding 8,258 MB — approaching the 8.6 GB that
previously broke an EAS upload. 23 of the 40 had no commit since the 2026-08-08
triage; filesystem mtimes matched their commit dates, confirming genuine disuse.

---

## Section 1 — Worktrees removed, branches KEPT (20)

**Why this was safe:** every tip below is an ancestor of `origin/main`, verified by
`git merge-base --is-ancestor <tip> origin/main` returning 0 — i.e. the commit is
literally reachable from `main`, which is stronger than patch-equivalence and is not
subject to the squash-merge caveat. **The branch refs still exist**, so nothing needs
recovering: only the on-disk working copy was removed.

Uncommitted work was captured to `patches/` **before** removal. `.claude/settings.local.json`
(per-clone config) was treated as disposable and is not in the patches.

| Tip sha | Branch | Last commit | Freed | Uncommitted captured |
|---|---|---|---|---|
| `37d74b2b` | `claude/cool-hermann` | 2026-04-15 | 2 MB | — |
| `49cf21e5` | `claude/compassionate-goldstine-410636` | 2026-04-19 | 3 MB | — |
| `49cf21e5` | `claude/nice-lovelace-83e5e8` | 2026-04-19 | 3 MB | — |
| `49cf21e5` | `claude/sad-brown-d5ef76` | 2026-04-19 | 3 MB | — |
| `49cf21e5` | `claude/sharp-hamilton-2ec655` | 2026-04-19 | 3 MB | — |
| `a93e5d86` | `claude/zealous-rubin` | 2026-04-19 | 3 MB | — |
| `bc340607` | `claude/crazy-noyce-6cdea0` | 2026-04-26 | 4 MB | — |
| `66cd2eac` | `feat/feedback-mobile-sync` | 2026-05-20 | 5 MB | 4 files |
| `c22e7311` | `worktree-agent-a6f676d19f96310cd` | 2026-05-21 | 2 MB | — (see note) |
| `33496d82` | `claude/magical-cerf-7cfaca` | 2026-06-23 | 6 MB | 5 files |
| `0edc7de7` | `claude/pensive-kilby-d53555` | 2026-07-04 | 7 MB | 7 files |
| `0edc7de7` | `main` (second checkout) | 2026-07-04 | 6 MB | — |
| `0ad2fe9b` | `claude/cranky-hofstadter-251429` | 2026-07-10 | 11 MB | 3 files |
| `0ad2fe9b` | `claude/magical-hofstadter-40cf12` | 2026-07-10 | 11 MB | 3 files |
| `cfe93001` | `claude/festive-mccarthy-b10c3a` | 2026-07-10 | 9 MB | — |
| `968d9a8e` | `claude/awesome-northcutt-0a5093` | 2026-07-17 | 434 MB | 4 files |
| `1580064c` | `worktree-agent-a064c586eb5fd3310` | 2026-07-20 | 26 MB | 7 files |
| `d44200f2` | `worktree-agent-ac919199823a00f48` | 2026-07-20 | 27 MB | 8 files |
| `16a9b51d` | `claude/keen-varahamihira-8986d4` | 2026-08-01 | 489 MB | 7 files |
| `a40eee89` | `claude/nifty-shtern-6dbae1` | 2026-08-02 | 24 MB | 2 files |

**Total freed: ~1,078 MB.** All removals used `--force`; what `--force` discarded is
exactly what `patches/` captured, plus `.claude/settings.local.json`.

**Note on `worktree-agent-a6f676d19f96310cd`:** its 138 "modified" entries were *all
deletions* — the directory had been emptied on disk at some earlier point, leaving only
the registration. Nothing was discarded.

**Recovery:** the branches were never deleted, so no action is needed to recover code.
To restore a working copy: `git worktree add <path> <branch>`. To re-apply captured
uncommitted work: `git apply docs/recovery/2026-08-16-worktree-sweep/patches/<branch>.patch`.

---

## Section 2 — Branch DELETED: the April SwiftUI spike

| Tip sha | Branch | Worktree path |
|---|---|---|
| `9758691439b63a9b9c856f252868daef33629505` | `claude/loving-wright-c2e9e2` | `.claude/worktrees/loving-wright-c2e9e2` |

The three commits that were **not** on `origin/main`:

| Sha | Date | Subject |
|---|---|---|
| `9758691` | 2026-04-21 | Phase 4: Trios + Tiers + Trades + Matches features |
| `f802f5b` | 2026-04-20 | Phase 3: DTF SwiftUI foundation — Login, LeaguePicker, nav shell |
| `a587456` | 2026-04-20 | Archive React Native `mobile/` to Reference Files |

**What was lost:** the only copy of a 54-file, ~5.6k-line SwiftUI client (`DTF/` —
iOS 17 + macOS 14; APIClient, Keychain, ViewModels, four view trees), plus 7
uncommitted files in the worktree (3 modified services/views, 4 untracked:
`SessionInitAPI.swift`, `SleeperAPI.swift`, `LeagueInitGate.swift`).

**Why deletion was safe — this one is a judgement call, not a content verification.**
Unlike Section 1, this content is genuinely absent from `main`. The
[2026-08-08 triage](../../reviews/2026-08-08-branch-triage.md) marked it **ASK** and
the verdict stayed open for 8 days. Operator decision, 2026-08-16: *drop it entirely* —
the April architecture pivot was abandoned (the product shipped on React Native), the
branch's own commit message records that Trades/Matches 500'd, and the app has diverged
far enough since April that the spike has no forward value. The branch also carried
`a587456`, which deletes all of `mobile/` — a standing hazard if ever merged by mistake.

**Recovery (time-limited):** `git branch claude/loving-wright-c2e9e2 9758691439b63a9b9c856f252868daef33629505`
— valid only while the objects remain reachable via reflog (~90 days from 2026-08-16,
sooner if `git gc --prune` runs). After that the SwiftUI spike is unrecoverable, which
is the accepted outcome. If it should be kept permanently at zero disk cost, tag it
**before** that window closes: `git tag archive/swiftui-spike-2026-04 9758691`.

---

## Section 3 — Held back, still needing a verdict (2)

| Tip sha | Branch | Why held |
|---|---|---|
| `2b7eb33f` | `worktree-agent-ac3579d0fd8f1d2d8` | 1 commit not on `origin/main`, 1 file differs; 413 MB on disk |
| `dc781ff5` | `feat/mobile-b5-trade-queue` | 1 commit not on `origin/main`, 3 files differ; 3 MB on disk |

Not swept: 17 worktrees with commits dated 2026-08-08 or later are still active work.
The largest are `ux-audit-p0-remediation` (2,908 MB) and `feat/finder-config-and-draft-order`
(1,508 MB) — together the majority of remaining disk, and out of scope for a staleness sweep.
