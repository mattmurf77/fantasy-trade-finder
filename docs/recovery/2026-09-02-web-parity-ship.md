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
reached `origin/main` through PR
[#263](https://github.com/mattmurf77/fantasy-trade-finder/pull/263), squashed as
`1eb520bd`.

**Verified by content 2026-09-02, after the merge.** Every file the branch
carried exists on `origin/main`:

```
for f in $(git ls-tree -r --name-only fix/web-phase0 -- web/ qa/web/); do
  git cat-file -e "origin/main:$f" || echo "MISSING: $f"
done      # printed nothing
```

**A plain `git diff origin/main fix/web-phase0` is NOT the check here, and an
earlier draft of this file wrongly said to expect it empty.** It never will be:
`main` is a strict superset. Eight files differ, each for a named reason —
`backend/server.py` (main moved 48+ commits), and seven changed *after* the
resync by the same ship: `qa/web/check_web_structure.py` (+2 guards),
`web/js/events.js` (the `X-Source` fix, [G-068](../../living-memory/GOTCHAS.md)),
`web/index.html` + `web/css/styles.css` (P2-3), `web/robots.txt` +
`web/sitemap.xml` (the 401-in-sitemap fix), and `web/CLAUDE.md`. Absence of a
file, not inequality of a file, is the failure signal.

**Evidence trail:** `docs/plans/web-parity/` (plan + scope, waivers W1-W7),
`docs/reviews/2026-08-19-web-parity-audit.md`, and the
`living-memory/TEST_LEDGER.md` entries dated 2026-08-26, 2026-09-02, 2026-09-02b
and 2026-09-02c.

**Recovery:** `git branch fix/web-phase0 40390013` (reflog expiry ~2026-11-30).

**Deliberately NOT deleted.** It is local-only, costs nothing, and is the only
place phases 0-2 exist as discrete reviewable commits — the squash flattened
them into one. Delete it only if someone wants the tidiness more than the
history; the sha above is the way back either way.
