# Recovery ledger — mock-draft repair sweep, 2026-08-13

> Capture-then-delete. Tip shas recorded before removal; verification by
> content against `origin/main` (squash-merge repo — ahead counts are not
> evidence).

## Branches swept

| Branch | Tip sha | Landed as | Verified |
|---|---|---|---|
| `mock-draft-fix` | `73c2d7e`+bump (see PR) | PR #114 → `e71a654` | content on main |
| `fb-295-296` (worktree only, branch `feedback-295-296` @ `2e0b2c7`) | `2e0b2c7` | its untracked 2026-08-10 spec landed via `b62a581` inside PR #114 | spec files on main |

## Worktrees removed

`.claude/worktrees/mock-draft-fix` · `.claude/worktrees/fb-295-296`

The `fb-295-296` worktree held the never-committed Phase-1 corpus for three
days; it was landed verbatim (`b62a581`) before any build began, then swept
here. Its branch `feedback-295-296` carried no unique commits (tip = the old
#289-#294 ship record already on main).

## Where the work landed

- **`e71a654`** (PR #114) — membership repair, manual mode, analytics, docs.
- **TestFlight build 110**, v1.13.3, submitted 2026-08-13.
