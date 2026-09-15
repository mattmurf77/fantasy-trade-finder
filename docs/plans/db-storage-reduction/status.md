# Database storage reduction — status

2026-09-15: production service recovered; normalization and retention are live; historical compaction in progress.

- Verified database suspension and 98.3% disk usage. Expanded 1→5 GB, resumed;
  Render available/read-only SQL passed, actual disk approximately 19.1%.
  Basic 256 MB compute and disabled autoscaling preserved.
- Private full custom-format backup verified with pg_restore listing and SHA256;
  PITR also available. Backup and sensitive row hashes stay outside this repository.
- Full-job real-data codec benchmark: 67.9–76.9% serialized feature reduction,
  exact roundtrips. These are not physical storage savings; actual writer uses
  bounded pages.
- Full local PostgreSQL backup rehearsal: 67,159 impression rows and 1,715
  outcomes preserved; every reconstructed feature SHA and every other core-field
  MD5 matched. 45,733 rows normalized, 73,146 unique snapshot nodes. After local
  reclamation: combined deck/snapshot relations 432,029,696 bytes versus
  742,465,536 before (41.8% smaller); whole local DB 530,347,711 versus
  840,472,255 bytes (36.9% smaller). Physical production results remain to measure.
- Optimized maintenance to one bounded PostgreSQL UPDATE FROM VALUES per page,
  avoiding one network round trip per row. Verified on 100 actual local restored
  records with exact roundtrip; rehearsal transaction rolled back.
- Local full backend run: 5,950 passed / 1 skipped (376.61s, Python 3.14.4).
  Focused regression run: 83 passed (includes owner/roster consumers and codec).
  Final cross-page/selective-reader changes will also run on Python 3.12 hosted CI.
- Named sabotage `DIAGNOSTIC_KEYS=()` makes the storage-budget regression fail;
  restoring the production codec passes. No source mutation retained.
- Independent subagent review found no blocking data-loss, privacy, or atomicity
  issue. Added cross-page coverage and changed resolver to fetch only reachable
  nodes in bounded queries in response to review.

Release: [PR #293](https://github.com/mattmurf77/fantasy-trade-finder/pull/293),
merge `09fe46e144f70ed0c8cbbebfbdc75970b97cdd15`, verified LIVE on Render
2026-09-15 15:54 UTC. Root and feature-flags HTTP 200; schema present.
[Exact-head CI](https://github.com/mattmurf77/fantasy-trade-finder/actions/runs/34989930181)
passed all four jobs; backend 5,952 passed / 1 skipped on Python 3.12.
[Post-merge CI](https://github.com/mattmurf77/fantasy-trade-finder/actions/runs/34991453398)
also passed.

First production batch: 37 rows normalized, all 67,159 core-row hashes and 1,715
outcomes preserved; 100 recent and 37 normalized diagnostic reconstructions match.
Bulk compaction found psycopg2 ON CONFLICT executemany performs per-node network
round trips. Follow-up uses explicit bounded multi-VALUES inserts (100 nodes /
500 parameters per statement), preserving conflict handling and transaction scope.
Ten focused tests passed; 100 restored PostgreSQL rows roundtripped exactly in a
rolled-back transaction. Bulk maintenance resumed from its last committed cursor.
Follow-up hosted CI, final production compaction, reclamation and metrics pending.
Scope: [scope.md](scope.md).
