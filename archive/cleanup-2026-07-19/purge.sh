#!/bin/bash
# Workspace purge — 2026-07-19 cleanup, phase 2 (DELETION).
#
# DO NOT RUN until the next release has been pushed to main, deployed on
# Render, and validated (archive-first policy, operator decision 2026-07-19).
#
# Everything this deletes is recoverable from, in order of preference:
#   1. archive/cleanup-2026-07-19/all-refs-2026-07-19.bundle  (every ref + stash tags)
#      restore:  git fetch archive/cleanup-2026-07-19/all-refs-2026-07-19.bundle <ref>:<ref>
#   2. archive/stash-{0..8} tags (stash commits, survive `git stash clear`)
#   3. worktree-dirty-state/  (uncommitted diffs + untracked files per worktree)
#
# KEEPS: trade-engine-v2, main, chalkline-primitives, audit/perf-optimization,
#        claude/stoic-mccarthy-e56da9 (delete manually after PR #91 is closed),
#        the archive/ tree itself, staged-work/, feedback-workspace/.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
HERE="archive/cleanup-2026-07-19"

if [ "${1:-}" != "--release-validated" ]; then
  echo "Refusing to run. Re-invoke as:  $0 --release-validated"
  echo "(only after the next release is pushed AND validated)"
  exit 1
fi

echo "== 1/5 removing ${1:+}$(wc -l < "$HERE/purge-worktrees.txt" | tr -d ' ') worktrees =="
while IFS= read -r wt; do
  [ -d "$wt" ] || continue
  git worktree unlock "$wt" 2>/dev/null || true
  git worktree remove --force "$wt" && echo "  removed ${wt##*/}"
done < "$HERE/purge-worktrees.txt"
git worktree prune

echo "== 2/5 deleting local branches =="
while IFS= read -r b; do
  git branch -D "$b" 2>/dev/null && echo "  deleted $b" || echo "  (already gone) $b"
done < "$HERE/purge-local-branches.txt"

echo "== 3/5 deleting stale origin branches =="
while IFS= read -r b; do
  git push origin --delete "$b" 2>/dev/null && echo "  origin deleted $b" || echo "  (already gone) origin/$b"
done < "$HERE/purge-remote-branches.txt"

echo "== 4/5 clearing stashes (preserved as archive/stash-* tags) =="
git stash clear

echo "== 5/5 removing root QA screenshots =="
rm -f 0[1-6]-*.png 66-*.png smoke-11a-apple-signin-no-error.png

echo "Done. Kept: trade-engine-v2, main, chalkline-primitives, audit/perf-optimization,"
echo "claude/stoic-mccarthy-e56da9 (delete after PR #91 close), archive tags + bundle."
