# 2026-09-02 — web-parity ship: `fix/web-phase0` ledgered before delete

| tip sha | branch | worktree |
|---|---|---|
| `40390013` | `fix/web-phase0` | none — its worktree (`.claude/worktrees/wait-instructions-ef2095`) was already removed in an earlier session |

**What it held.** Web parity phases 0-2 plus the four operator rulings of
2026-08-26 (posture B/Companion, admin shell blocked in prod, `[STATE]` left as
a TODO, no support email). Built 2026-08-19, last synced 2026-08-26, then
parked — **unmerged for 14 days** while `main` moved 48 commits.

**Why deletion is safe (verification by content):** the branch is an ancestor of
the shipping branch, not a re-implementation of it —

```
git merge-base --is-ancestor fix/web-phase0 claude/website-updates-continue-c7942b   # exit 0
```

— so every commit it carries is reachable from the merge, and its content
reaches `origin/main` through PR
[#263](https://github.com/mattmurf77/fantasy-trade-finder/pull/263). Verify by
content after the squash lands (this repo squash-merges, so ahead/behind counts
and a `git branch -d` refusal are NOT evidence):

```
git diff origin/main fix/web-phase0 -- web/ backend/server.py qa/web/   # expect empty
```

Two files will legitimately differ outside that path set — `living-memory/` and
`docs/plans/web-parity/` gained this session's write-back on top.

**Do NOT delete before that diff is empty.** The branch is the only place phases
0-2 exist as discrete, reviewable commits; the squash flattens them.

**Evidence trail:** `docs/plans/web-parity/` (plan + scope, waivers W1-W7),
`docs/reviews/2026-08-19-web-parity-audit.md`, and the
`living-memory/TEST_LEDGER.md` entries dated 2026-08-26, 2026-09-02 and
2026-09-02b.

**Recovery:** `git branch fix/web-phase0 40390013` (reflog expiry ~2026-11-30).

**Not yet deleted.** Recorded here first, per `docs/recovery/CLAUDE.md` — capture,
then delete, never the reverse.
