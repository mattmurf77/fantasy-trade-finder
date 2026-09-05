# Security release ref recovery — 2026-09-05

| Tip SHA | Branch |
|---|---|
| `ab8f54d0ae86e7bc261c59b41bc1192d0ba54b28` | `codex/security-data-hardening-20260904` (local and origin) |

Removal is safe after this evidence commit: PR #279 squash-merged as `a927e3a7f3552ed48d68d3e33f370ee1636bffcf`; `git diff origin/main ab8f54d0` was empty immediately after fetching the merge. The source commit is also retained by public release tag `extension-v0.1.1`. CI and production evidence are in [deployment.md](../plans/security-data-hardening/deployment.md).

Release worktree: `/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/staged-work/security-data-hardening-20260904`. It was detached onto the merged commit for evidence-only publication; record that final detached tip before removing the worktree. The original project's checkout and unrelated edits are preserved.

Recovery: `git branch codex/security-data-hardening-20260904 ab8f54d0ae86e7bc261c59b41bc1192d0ba54b28`.
