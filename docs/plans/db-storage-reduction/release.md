# Database storage recovery — 2026-09-15

The full database was recovered by increasing its Render disk from 1 GB to 5 GB and resuming it. Compute remains Basic 256 MB; disk autoscaling remains disabled. The additional storage costs $1.20/month at the verified $0.30/GB-month rate. Render storage increases cannot be reversed on this instance.

The main cause was repeated diagnostic JSON on generated recommendation records, not the number of accounts. Before the incident, 44 recent generation jobs had written 40,018 records (about 910/job), with much wider diagnostics than earlier records. `deck_impressions` accounted for most of the database allocation.

## Released changes

- Store repeated diagnostic structures once per user/job using immutable references, preserving exact JSON reconstruction while retained.
- Keep core recommendation fields, frozen valuations, outcomes and receipts unchanged.
- Expire diagnostic snapshots after 14 days; recommendations and their core data remain durable.
- Include snapshots in account export/deletion and use an owner-scoped resolver for detailed diagnostics.
- Use bounded, atomic multi-value writes for both ongoing generation and historical compaction.

## Capacity interpretation

Use approximately **350,000 additional stored recommendation records** as a conservative planning estimate on the expanded disk with a 20% reserve. At the recent average of 910 candidates/job, that is approximately **380 generation runs**. Viewing existing cards does not write another full candidate record. These numbers describe storage, not concurrent serving capacity or a supported user count.

The estimate assumes about 9 KB of incremental physical storage per recent-style record. This is inferred from measured payloads plus allocation overhead, not a guaranteed marginal size. Diagnostic expiry should improve runway; other tables, larger future payloads and WAL bursts consume it. Core recommendation rows still grow indefinitely. Reducing unused candidate persistence or setting a separate core-data retention policy would be a further product/analytics decision.

## Release and validation evidence

- [PR #293](https://github.com/mattmurf77/fantasy-trade-finder/pull/293), merge `09fe46e1`: normalization/retention live at 2026-09-15 15:54 UTC. [Exact-head CI](https://github.com/mattmurf77/fantasy-trade-finder/actions/runs/34989930181): 5,952 backend tests passed / 1 skipped; all four jobs green.
- [PR #294](https://github.com/mattmurf77/fantasy-trade-finder/pull/294), merge `82c5f118`: bounded multi-value inserts live at 16:22:39 UTC. [Exact-head CI](https://github.com/mattmurf77/fantasy-trade-finder/actions/runs/34993085988): 5,953 backend tests passed / 1 skipped; all four jobs green. [Post-merge CI](https://github.com/mattmurf77/fantasy-trade-finder/actions/runs/34994464545) also passed.
- Both deployed revisions verified through Render's exact commit status, root HTTP 200, feature-flags HTTP 200 with valid JSON, and server-enforced read-only SQL.
- Private full custom PostgreSQL backup verified by archive listing and SHA-256; PITR available. Rehearsed the complete conversion and reclamation on a local PostgreSQL restore. All 67,159 reconstructed feature hashes and other core-field hashes matched; all 1,715 outcomes remained.
- Local diagnostic tests include exact reconstruction, storage budget, user/job scope, atomic rollback, legacy compatibility, retention, private account export/deletion, cross-page sharing and bounded SQL writes. Disabling normalization made the storage-budget regression fail; no sabotage mutation retained.
- One-time maintenance used the released codec and bounded transaction loop. An independently reviewed operator variant replaced the old-text UPDATE guard with SHA-256 of the exact UTF-8 text to reduce WAN upload. Row locks, exact reconstruction, atomic snapshot writes, affected-row checks and backup gates were retained. A 100-row local PostgreSQL rollback rehearsal, Unicode checksum parity, rejection of an incorrect hash, and all 100 production read-back hashes passed before bulk use.
- Sensitive backups, per-record hashes and raw diagnostic evidence remain in protected local recovery storage, outside version control. The preserved legacy checkout and unrelated dirty current-project checkout were not altered.


## Final production measurements

After full compaction and bounded reclamation, the final read-only check again
matched all **67,159 original core-record hashes**, **1,715 outcome hashes**, and
both 100-record diagnostic reconstruction samples. There are **73,146 shared
snapshot nodes**. No recommendation/outcome rows were removed.

| Allocation | Before | Final | Reduction |
|---|---:|---:|---:|
| Whole PostgreSQL database | 895,088,319 B | 539,281,087 B | 39.8% |
| Recommendation table plus shared diagnostic table, including indexes/TOAST | 787,722,240 B | 431,964,160 B | 45.2% |

The recommendation table itself is 244,547,584 B; shared diagnostics are
187,416,576 B. VACUUM FULL operated on deck_impressions only and completed in
111.43 seconds under a 120-second statement limit, after the preservation check,
backup verification and fresh headroom guard. The table was exclusively locked
during reclamation; final application health checks passed.

At **2026-09-15 16:55 UTC**, Render reported **1,051,078,660 B used of
5,246,714,000 B (20.03%)**, with **4,195,635,340 B free** and **45.76% RAM used**.
The database was available, the exact expected application commit was LIVE,
and root / feature-flags endpoints returned HTTP 200.

The capacity calculation uses this actual volume consumption, including
transaction-log/platform overhead:

`(5,246,714,000 × 0.80 − 1,051,078,660) / 9,000 ≈ 349,588 additional records`

`349,588 / 910 ≈ 384 generation runs`

Rounded down for planning: **about 350,000 records / 380 runs**. The earlier
400,000-record estimate assumed less volume overhead and is superseded by these
measurements. This is an estimate, not a safe maximum or a load-test result.
Future record sizes, other tables and transaction logs can change the runway.

The current working checkout contains session-context tooling that is absent
from the actual origin/main base used for this fix; its --check could not run in
this isolated worktree. No unrelated organization files were copied into the
release. Final documentation was reviewed with git diff --check; code CI and
deployment evidence are linked above.


## Prevention recheck — 2026-09-16

At 04:41 UTC, Render again reported `82c5f118` LIVE, root and feature-flags
HTTP 200, and the snapshot table present through server-enforced read-only SQL.
The service has no FTF_DECK_DIAGNOSTIC_RETENTION_DAYS override, so the deployed
14-day default applies. There were no expired snapshot nodes pending cleanup.

The deployed save_deck_impressions path compacts each new page before inserting
it and writes shared snapshots in the same transaction. The running cleanup
loop invokes bounded diagnostic expiry. These changes were already released
in PRs #293/#294; another code change or deployment is not needed to enable them.
A read-only sample found no recommendation rows newer than September 15 at
17:00 UTC, so this recheck does not claim a newly observed production write.
Writer behavior is supported by the deployed code and passing regression tests.

The operator authorized publication of the final documentation on September 16.
This documentation update does not redeploy the application. Diagnostic storage
is bounded by retention; durable recommendation/core data continues to grow.
