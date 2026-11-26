# 2026-11-25: skip-by-area CI proof branches

Deleted 2026-11-25 (local and `origin`). Reflog recovery expires about 90 days after that.

| Tip sha | Branch | Closed PR |
|---|---|---|
| `19d924b9` | `ci/skip-proof-docs` | 736 |
| `17a6a4f4` | `ci/skip-proof-mobile` | 737 |
| `39da56dc` | `ci/skip-proof-backend` | 738 |

Why deletion was safe: each branch is `ci/skip-by-area` (commit `702d4e41`, PR 735) plus one
throwaway commit that appends a single comment line to one file (`docs/runbook.md`,
`mobile/CLAUDE.md`, `backend/tests/__init__.py`). They existed only to trigger CI runs that
prove the skip-by-area rule, were never meant to merge, and their PRs were closed unmerged.
The run links are recorded in the PR 735 description. No worktrees were involved.

Recovery: `git branch <name> <sha>`.
