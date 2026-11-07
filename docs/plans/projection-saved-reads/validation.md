# Saved projection read validation

## Scope

Backend-only on main `57b8d7c3`. No production reads, load, database copies or JSON casts. Synthetic SQLite plus PostgreSQL SQL compilation; no forecast computation changes.

## Checks

- New implementation suite: **17 passed in 1.59 seconds**. Captured SELECTs exclude private snapshot/input/control columns, retain all identity predicates and fetch same/distinct latest IDs in one query. API and export response bytes match the previous full-row implementation across current, stale, queued, running, failed and distinct completed states. Shared results decode once.
- Projection, account-deletion, privacy-export and paywall suites: **526 passed, 3 skipped in 20.00 seconds**. Includes saved-input scenario reuse, version gates, stored recovery, weekly schedule and read-only GET guards.
- Independent reviewer: **38 passed in 1.62 seconds**, including 11 separately authored adversarial cases plus the new suite and scenario/version controls. The 11 independent cases are retained as `test_league_projection_saved_read_review.py`. They cover foreign target pointers, incomplete exports, deletion/recreation, cancellation without snapshot transfer, and real baseline scenario creation retaining its owned immutable snapshot.
- Named sabotage `full_row_read`: replacing the public projection with full-row gets makes the selected-column/payload guard fail. Source files were not mutated for the sabotage; an external pytest plugin performed the substitution in a separate process.

## Resource evidence and limitations

A synthetic saved run contains a 2,097,176-byte snapshot JSON string. For identical success and attempt IDs, the previous two full-row reads return 4,195,740 bytes of string values combined; the new single public-row read returns 608. These are selected application string-value counts, not database page I/O, SQL protocol bytes, peak memory or timing. Actual result sizes vary.

The public response still serializes both `run` and `attempt` for compatibility. Home still requests the same full result. No wire-byte reduction, hosted capacity gain or 200 ms claim is made. No persistent cache is introduced. The full snapshot remains available only to the existing owned scenario/worker paths that consume it.

Exact-head CI and release-owner integration remain required. This backend source change may require rebuilding unexposed Calibration decks after deployment; no deployment is performed here.
