# App-open trade preparation

Date: 2026-09-20. Direct user request. No waivers; normal release gates.

## 1. Analytics scope
Existing `trades_generated` records completed worker time and source; `app_opened` records launches. No new events or emitters.

## 2. Schema & flag scope
No schema, flags, environment or model knobs. Session init accepts optional `trade_fairness_threshold`; default 0.5 matches native Find a Trade. Native sends the persisted choice. Existing safety/presentation rules, TTL, uncapped offers and durable evidence remain.

## 3. Evidence scope
Backend regression tests for session-init warm-up defaults, explicit choice, failed-job retry and cache parameter mismatch. Native executable checks for persisted fairness and session payload wiring; typecheck and existing structural suites. No visual changes or new testIDs. Runtime checklist: cold open a real league, remain on Rank, then open untargeted Find a Trade; verify the same background job is adopted. Repeat with fairness on, league switch, foreground resume, and after changing rankings with the existing forced refresh. Custom player/opponent/shape searches must retain their requested settings. Offline startup must remain usable and manual generation retry must recover. Device checks remain explicitly unrun until executed.

## 4. Docs scope
Update API reference (session-init field), architecture (startup preparation), and API module map. HLD/LLD n/a: compatibility pointers, no new architecture. Invariants/glossary/ADR n/a: no new shared enum or domain concept, existing pregen design repaired.

## 5. Ship gates
Green exact-head CI including backend, mobile and web; ledger evidence and code trace. No express lane. Native preference transport requires a new native release; backend default benefits installed clients after deployment. This removes wasted startup work, not a claim of three-second fresh generation.
