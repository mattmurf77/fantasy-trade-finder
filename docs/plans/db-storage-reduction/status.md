# Database storage reduction — status

2026-09-15: production service recovered; code built, validation/release in progress.

- Verified database suspension and 98.3% disk usage. Expanded 1→5 GB, resumed;
  Render available/read-only SQL passed, actual disk approximately 19.1%.
  Basic 256 MB compute and disabled autoscaling preserved.
- Private full custom-format backup verified with pg_restore listing and SHA256;
  PITR also available. Backup and sensitive row hashes stay outside this repository.
- Full-job real-data codec benchmark: 67.9–76.9% serialized feature reduction,
  exact roundtrips. These are not physical storage savings; actual writer uses
  bounded pages. Local full-backup PostgreSQL rehearsal in progress.
- Local full backend run: 5,950 passed / 1 skipped (376.61s, Python 3.14.4).
  Focused regression run: 83 passed (includes owner/roster consumers and codec).
  Final cross-page/selective-reader changes will also run on Python 3.12 hosted CI.
- Named sabotage `DIAGNOSTIC_KEYS=()` makes the storage-budget regression fail;
  restoring the production codec passes. No source mutation retained.
- Independent subagent review found no blocking data-loss, privacy, or atomicity
  issue. Added cross-page coverage and changed resolver to fetch only reachable
  nodes in bounded queries in response to review.

Release gates: current-SHA hosted CI, local PostgreSQL full-data reconstruction,
production deployment verification, bounded maintenance, physical reclamation
and final metrics remain pending. Scope: [scope.md](scope.md).
