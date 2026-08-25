# 2026-08-24 — Wave A + Wave B0 ship (onboarding-tour-merge; built by Opus subagents, Fable-reviewed)

| tip sha | branch | merged as |
|---|---|---|
| `274a0ea9` | `feat/tour-wave-a` (Opus build + lead's review fixes A1–A4/A6) | squash PR [#197](https://github.com/mattmurf77/fantasy-trade-finder/pull/197) → `7452650` |
| `15dd6cd3` | `feat/inline-home-b0` (Opus build, rebased over #197, + lead's review fix B1) | squash PR [#199](https://github.com/mattmurf77/fantasy-trade-finder/pull/199) → `14a4ce4` |

Verified by content: `git diff feat/inline-home-b0 origin/main` was **EMPTY** at `14a4ce4` (B0 was
rebased onto the merged Wave A, so its tree IS main's); Wave A's content is a strict subset of
that same tree (`check-calc-tour` §45, the converted beats, `calc.action.clear` all on `main`).
CI green on both PRs. EAS production build **1.16.4 (130)** cut from this content and submitted to
App Store Connect (submission `a7b08771`). Remote branches deleted 2026-08-24. Recovery:
`git branch feat/tour-wave-a 274a0ea9` · `git branch feat/inline-home-b0 15dd6cd3`.

Also removed the same day, after their branches' content reached `main`: the three agent worktrees
(`.claude/worktrees/agent-ac4a220e21b34a3e5` = Wave A builder, `agent-a9109c29833f6639c` = Wave B0
builder, `agent-a1af464342020396f` = the Fable reviewer, whose local `scratch-merge-review` branch
was throwaway composition evidence, never pushed).

Same pattern as this file's siblings: the docs branch carrying THIS file (`docs/wave-a-b0-ship`,
scratch worktree `wt-docs7`) is single-commit docs-only, recoverable from its own PR's squash
diff. Deleted same day, worktree removed.
