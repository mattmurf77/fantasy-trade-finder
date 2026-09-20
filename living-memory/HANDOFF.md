# HANDOFF

## Current state
App-open trade preparation implemented on `codex/app-open-trades` from production 57c37c26. Server warm-up already existed but used 0.75 instead of native default 0.5; failed cached jobs prevented retries. Fixed default/persisted preference transport, error retry and compatible-running reuse; removed duplicate onboarding-gated native POST. [Scope/evidence](../docs/plans/app-open-trades/status.md).

## In flight
Full checks and release. 116 focused backend tests, 39 native lifecycle checks, fairness/ownership guards, TypeScript and web 195/195 passed. Device checklist unrun. Native changes require a build; backend default can help installed clients. Fresh generation itself remains too slow (recent larger jobs 37–42 seconds).

## Blocked on
No implementation blocker. Release state must be recorded before claiming live behavior.

## Do not repeat
Preserve unrelated team-overhaul checkout and legacy worktrees. No candidate/offer caps, safety bypass or removed durable evidence. No simulator. Do not equate pre-generation with measured three-second fresh generation.
