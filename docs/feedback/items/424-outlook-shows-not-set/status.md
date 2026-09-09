# FB-424 — Outlook row shows Not set after it was set

- **Status:** planned 2026-09-08 (operator selection; fast-track bug path)
- **Group:** G-423 — batch plan [422-win-now-ffv3-unavailable/plan.md](../422-win-now-ffv3-unavailable/plan.md)
- **Reporter:** mattmurf77, app v1.17.x, iOS 27.0

## Phase log
- 2026-09-08: Phase 0 — selected; folder created; investigation planner launched.
- 2026-09-08: Phase 1 — planner done. Root cause is NOT staleness: the merged landing's only outlook surface is the hosted calculator's fallback, which renders a literal "Outlook · Not set" whenever the receipt hides (`InLeagueCalculator.tsx:925-931`; receipt always hidden with `trade.outlook_direction` false, `OutlookBiasReceipt.tsx:49-53`); the 17:58:47 158-byte prefs GET shows the client cache already held `rebuilder`. Mini-PRD, scope and code-walk in [423-team-review-not-registering/](../423-team-review-not-registering/prd.md) (canonical). No server change.
- 2026-09-08: Phase 4 — round-1 resolution (shared branch, see [423 status](../423-team-review-not-registering/status.md)): guard `check-outlook-row-source.js` now pins the #394 rule for this row — `inferred_outlook` anywhere in the fallback expression, or a disabled prefs query, goes RED (1d, 2b). No further code change for #424. Status: in_progress — awaiting QA round 2 / ship.
- 2026-09-08: Phase 3 round 2 — QA-A PASS, QA-B PASS; ship-ready (branch feat/fb423-outlook-row-and-marker).
- 2026-09-08: Phase 5 — merged into `feat/feedback-2026-09-08` (mobile 1.17.3); awaiting operator go.
