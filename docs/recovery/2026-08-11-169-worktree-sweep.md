# 2026-08-11 — #169 build sweep (branches + worktrees)

Squash-merge of PR #107 landed as `f27c0f5` on `origin/main`. This repo
squash-merges, so verification below is **by content against `origin/main`**,
not by ancestry (`git grep` hits on `origin/main` for each branch's
distinctive symbols — recorded before any deletion).

| Ref | Tip sha | Content evidence on `origin/main` |
|---|---|---|
| branch `worktree-agent-a64b29ab24545069f` (W1, worktree `.claude/worktrees/agent-a64b29ab24545069f`) | `22e8d2b` | `OutlookStrip` ×11 in `LeagueSummaryScreen.tsx`; `outlook_strip_toggled` ×2 in `backend/analytics_taxonomy.py`; `mobile/src/state/outlookStrip.ts` tracked |
| branch `worktree-agent-a70f9c4009d7581bf` (W2+W3, worktree `.claude/worktrees/agent-a70f9c4009d7581bf`) | `3672efa` | `disposition` ×26 in `TradeCard.tsx`; `mobile/tests/check-card-disposition.js` tracked; extended `06-trades-deck.yaml` |
| branch `feedback-169-e-and-card` (local + `origin/feedback-169-e-and-card`) | `a4ad96f` | PR #107 squash = `f27c0f5`; doc set present (`docs/feedback/items/169-outlook-league-summary/plan-e-and-card-2026-08-11.md` etc.); "Deck disposition" section in `docs/cross-client-invariants.md` |
| branch `feedback-169-decisions` (other session's, merged into the work branch pre-PR) | `2bd86eb` | `operator-frame-decisions-2026-08-11.md` tracked on `origin/main` — **left for its owning session to sweep** |

Tips confirmed by `git rev-parse` at ledger time: `a4ad96f` / `22e8d2b` /
`3672efa`.
