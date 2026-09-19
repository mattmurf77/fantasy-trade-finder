# Database storage reduction — status

2026-09-15: released; full historical compaction and physical reclamation completed.

- Database recovered from suspension / 98.3% disk use by expanding storage 1→5 GB
  and resuming. Compute remains Basic 256 MB; disk autoscaling remains disabled.
- Normalized diagnostics and 14-day debug-only retention are live through PR #293;
  bounded multi-value snapshot inserts are live through PR #294 (`82c5f118`).
- Both exact-head and post-merge CI runs passed. Latest exact-head backend result:
  **5,953 passed / 1 skipped**; web, mobile and test-ID checks also green.
- Verified private full backup and complete local PostgreSQL rehearsal before
  production changes. All 67,159 rows scanned; 45,733 compacted; 73,146 shared nodes.
- After full compaction, every original core-row hash and all 1,715 outcome hashes
  matched; 100 recent and 100 normalized diagnostic samples reconstructed exactly.
  The checksum-guarded operator batch also had all 100 records read back exactly.
- Bounded VACUUM FULL of deck_impressions succeeded in 111.43 seconds. Database
  allocation fell from 895,088,319 to 539,281,087 bytes (39.8% smaller).
  Deck plus shared diagnostics fell from 787,722,240 to 431,964,160 bytes
  (45.2% smaller). Core records, valuations and outcomes were retained.
- Final post-reclamation preservation checks passed again. Render at 16:55 UTC:
  available, 20.03% disk used, 45.76% RAM used, deployed commit verified LIVE,
  root and feature-flags HTTP 200. Illustrative headroom: about 350,000 additional
  stored records / 380 generation runs with a 20% reserve. Core records keep growing.

[Release evidence and capacity assumptions](release.md) · [Scope](scope.md)

2026-09-16 prevention recheck: deployed writer/cleanup revision remains LIVE;
14-day retention default active, zero expired nodes pending, health checks pass.
No new records available for a post-cleanup write sample. No additional code
release needed; final documentation publication authorized. See release evidence.
