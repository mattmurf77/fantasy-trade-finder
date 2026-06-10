# Status: perf-optimization

- **Phase:** done — Wave 2 fully shipped
- **Current round:** 03 (closed)
- **Last update:** 2026-06-07 by primary
- **Next action:** user review of open questions (see below); Wave 3 or INIT-08-backend when Q4 resolved
- **Blockers:** none
- **Surfaces touched:** mobile, backend
- **Linked ADRs:** `docs/adr/adr-001-query-cache-persistence.md` (INIT-07 AsyncStorage decision)

## Outcome

Wave 2 shipped in full on 2026-06-07. All 8 autonomous items done:

| INIT | Title | PR | Status |
|------|-------|----|--------|
| 12b | GET retry | #67 | ✅ merged |
| 09 | Trade-gen prune | #68 | ✅ merged |
| 11a + 13 | Render memo + poll backoff | #69 | ✅ merged |
| 14b | DB hygiene | #70 | ✅ merged |
| 07 | Persisted cache + key scoping | #71 | ✅ merged |
| 15 | Docs | #72 | ✅ merged |
| 08-client | Optimistic session shell | #73 | ✅ merged |

Final verification: 41 backend tests pass (28 baseline + 13 new). Mobile TypeScript clean.

## Wave 3 candidates (deferred)

| INIT | Title | Blocker |
|------|-------|---------|
| 08-backend | session_init split | Q4: profiling needs auth token |
| 10 | Web player payload | Q5: user prioritization |
| 11b | Tiers virtualization | risk: preserve PR #60 coord fix |
| 08-OptB | Snapshot-replay ELO | Q: golden test gate |
| 16 | League activity double-fetch | RICE-P 0.8, low value |

## Open questions for user

| # | Question | Default applied |
|---|----------|----------------|
| Q3 | When to kick next EAS TestFlight build? | Not kicked — user decides |
| Q4 | Auth token for session_init profiling? | Blocked — needs token |
| Q5 | Web payload prioritization? | Deprioritized |
| Q6 | MMKV upgrade timing? | AsyncStorage used; upgrade documented in ADR-001 |

## Known cleanup items

- `datetime.utcnow()` deprecation in `backend/database.py:_COMMUNITY_ELO_CACHE` (Python 3.12 warning)
- Audit docs on branch `audit/perf-optimization` NOT merged to main (Q2)
- Mobile TestFlight build not kicked since Wave 1 (Q3)
