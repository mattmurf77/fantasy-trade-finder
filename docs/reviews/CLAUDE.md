# docs/reviews/ — Notes for Claude

Point-in-time audit snapshots — not current truth. Check the date before trusting a claim; re-verify against the live code/docs.

- `2026-05-22-*` (SUMMARY, api-layer, backend, mobile-render, silent-bugs) + `REVIEW_BRIEF.md` — historical deep code review, largely acted on.
- `2026-08-08-branch-triage.md` + `2026-08-08-context-overload-audit.md` — current ops references (branch/worktree backlog, context-load remediation this file is part of). Branch/worktree *deletions* since then are ledgered in `docs/recovery/`, not here.
- `2026-08-16-p0-remediation-status.md` — seven independent verifiers checking the `docs/plans/audit-p0-remediation/` specs against the **`origin/main` tree**, not a working checkout. The closest thing to ground truth on what the P0 batch actually landed.
- `2026-08-18-valuation-age-audit.md` — read-only investigation into age penalties in the value ladder (triggered by the Davante Adams reports). No engine code changed.
- `trade-engine-deep-dive.md` + `trade-engine-external-research.md` — trade-engine proposal history; see `docs/adr/adr-002-trade-engine-v2-v3-rebuild.md` for what actually shipped.

Add a row here when you add a review. An unlisted audit in this folder is indistinguishable from a stale one.
