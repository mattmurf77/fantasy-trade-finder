# docs/recovery/ — deletion recovery records

This folder is the ledger of deleted git refs. **Before deleting any branch or
removing any worktree whose work is old, merged, or verified-redundant, record its
tip sha here first.** Reflog retention (~90 days) is the only other recovery path,
and it is silent and temporary — this ledger is the durable one.

## Required procedure for every branch/worktree deletion

1. **Capture, then delete — never the reverse.** For each ref about to be deleted:
   `git rev-parse --short <branch>` (for a worktree, also note its path and whether
   `git worktree remove` needed `--force` because of uncommitted files — if it did,
   say what was discarded).
2. **Write a dated file** in this folder: `YYYY-MM-DD-<short-topic>.md` — or append
   to the same day's existing file for one cleanup pass.
3. Each entry needs:
   - a table of `tip sha | branch name` (plus worktree path where applicable)
   - one line on **why** deletion was safe, linking the verification evidence
     (e.g. a triage/review doc in `docs/reviews/`) — "merged via squash PR #NN"
     beats "was old"
   - the deletion date (reflog recovery expires ~90 days after it)
4. **Recovery instructions are one line** — include it: `git branch <name> <sha>`.

## Rules

- Deleting without a ledger entry is the failure mode this folder exists to prevent.
  If you find a deletion happened without one, reconstruct it from `git reflog` /
  session logs immediately while the commits are still reachable.
- Ancestry checks (`git branch -d` refusing, ahead-counts) are NOT verification in
  this repo — PRs are squash-merged, so verify by content and cite the evidence doc.
- This ledger is append-only history. Don't rewrite old entries; add corrections as
  new dated lines.
