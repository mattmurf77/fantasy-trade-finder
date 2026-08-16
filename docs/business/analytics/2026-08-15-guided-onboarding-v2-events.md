# Tracking-plan addendum — Guided Onboarding v2 (2026-08-15)

> Required by the taxonomy docstring for every new-client-name batch. Plan: `docs/plans/guided-onboarding-v2/{PRD.md,scope.md}`; event-state audit in `DELTA-2026-08-15.md` §E. All rows mobile-only, flag-gated on `onboarding.guide_v2` (emitters inert while false).

| Event / prop | Class | Props | Fires when | Answers |
|---|---|---|---|---|
| `guide_step_suppressed` | **non-intent** (system) | `step`, `blocked_by` (client union `GuideBlockedBy`, 9 values — see `useGuide.ts`) | `requestStep` refuses a beat; once per deferral episode | Is a beat being starved (M4)? Was a moment consumed (`matched`)? |
| `guide_step_shown` + **`spotlight`** prop | existing event | `spotlight ∈ measured\|degraded\|none` | existing emit, deferred until the spotlight resolves for targeted beats | Release-build degrade rate (M3), split by platform/app_version |
| `outlook_saved` | intent | `source ∈ guide\|sheet\|strip` | first preference write in a TradeDnaSheet session | N2 retirement receipt; outlook adoption |
| `finder_target_pinned` | intent | `side ∈ give\|receive`, `source` | targeting-board pin recorded | N4 adoption/retirement receipt |
| `quickset_started` | intent | `position` (QB\|RB\|WR\|TE), `source ∈ guide\|organic` | QuickSetTiers mounted with intent | N1/s3.2 funnel top; pairs with server-fired `quickset_completed` |
| `awaiting_segment_viewed` | **non-intent** (impression) | `source ∈ guide\|tab\|push` | Matches "Awaiting them" segment focused | N6.1 funnel step (NOT its adoption event — that is the send-attempt family) |

Notes: `trio_session_started` was already registered (empty prop allowlist matches its emitter) — pinned by test, no change. `quickset_completed` stays server-fired only; client retirement re-sources to persisted `quicksetCompletedPositions`. Phase-2 rows deliberately absent: MFL/ESPN send-attempt, trio submit receipt, `trades.send-control.guide` beats. `NON_INTENT_EVENTS` updated in `backend/analytics_queries.py` in the same change (INTENT is a deny-list; omission would step-change DAU at emitter ship).
