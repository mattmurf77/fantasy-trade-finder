# Feedback 419–421 — selected fixes and open-backlog audit

**Date:** 2026-09-06. **Build base:** freshly fetched `origin/main` at `4026ebc81eaae50b345b42421641125c5b8d413e` (rechecked during finishing review). **Status:** G419 backend/mobile, G420 and bounded package presentation passed root review, both complete independent round-2 reviews and all four PR #283 CI jobs on `d97459dc` (5,645 backend passed / one optional skip in 717.99s). Root also passed all 95 mobile guards, TypeScript/testID and 190 web checks. PR #283 merged as `988fa2d6` at 17:16:56 UTC; Render was live at 17:21:19.905609 UTC. Only `simple_player_presentment=1` was activated at 17:23:58 UTC and verified by readback at 17:24:18 UTC. iOS 1.17.1 (149) build/submission are FINISHED; Apple processing/tester availability and physical-device verification remain outstanding. Backlog audit and package research are complete. The owner explicitly authorized this reviewed release and public GitHub destination. [Release evidence](release.md).

## Selected groups

| Group | Items | Work | Ownership before integration |
|---|---|---|---|
| G419 | 419 | Prevent a rejected exact offer from resurfacing as current counterparty interest | Trade-disposition worktree; exact backend/client boundaries to be pinned by reviewed PRD |
| G420 | 420, 421 | Repair Win Now initialization/loading behavior and distinguish request timeout from hosting claims | Win Now worktree; exact client/backend boundaries to be pinned by reviewed PRD |
| Audit | All 45 open records | Research which are actually implemented and released, with per-item evidence | Independent reviewer; audit report only, no status changes or unrelated fixes |
| Package research | New owner request, no feedback ID | Compare completed trades in the owner's linked Sleeper leagues with recorded viewed/generated chips; derive a bounded preference for smaller packages if supported | Read-only research first; any implementation receives its own reviewed scope and regression evidence. Never block an explicit owner-selected package as a side effect. |

## Execution gates

The owner selected 419–421. These three production records were initially changed from new to planned via the existing admin API and read back individually. After verified delivery they were set to `fixed` and read back at 17:41:48.077159, 17:41:51.397001 and 17:41:56.234037 UTC respectively on 2026-09-06. No other feedback record was closed; the all-45 audit remains research-only. The initial read-only production snapshot at 04:03:22 UTC contained 45 open records. The original checkout remains dirty and untouched; build lanes started from the fetched main, not that checkout.

Each fix group follows planner → separate author → planner critique/reconciliation → parent gate → build → independent QA. Scope, numbered requirements, regression tests proven RED against the defect, code-walk evidence and concrete manual TestFlight steps precede release. D-056 forbids Maestro and simulator use. Shared reference docs, index and living-memory updates belong to the parent at integration; agents own only their scoped item docs and assigned runtime/test files.

Preserve all live policy/experiment settings, original package/identity semantics outside the defects, privacy redaction and existing telemetry. No production trade regeneration, real-user action, schema migration, ranking rewrite or new data collection is presumed. Any required expansion must be explicit in the reviewed scope.

## Release boundary

The owner, before leaving for the night, explicitly authorized merge/push/live delivery and TestFlight where needed for the selected fixes and the package-size follow-up. This is a current-batch preauthorization, not an inference from an earlier release and not an express-lane waiver. All specification, independent QA, fresh-main overlap, CI, docs and release-verification gates remain required. Unrelated backlog fixes, status closures, flag activations and real-user/provider trade actions remain out of scope. If research does not justify a safe package adjustment, retain the recommendation/evidence rather than force a policy change.

Code presence, enabled server flags, binary upload and verified tester availability remain distinct facts. The backlog audit must not close a report solely from a plan, stale index status, code resemblance or unverified native delivery. Manual physical-device QA is not fabricated by shipping authorization.
