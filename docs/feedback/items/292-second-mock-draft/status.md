# FB-292 — "Can't do a second mock draft"

- **Type:** bug · **Status:** planned 2026-08-10
- **Group:** G2 — Mock draft: engine, lifecycle, interactivity
- **Canonical folder:** [`290-mock-draft-engine/`](../290-mock-draft-engine/) —
  plan, PRD and design deltas for #290/#291/#292 all live there.
- **Batch plan:** [`289-mfl-draft-room-ids/batch-plan.md`](../289-mfl-draft-room-ids/batch-plan.md)
- **Branch:** `feedback-289-294` (base `origin/main` @ `7cea1fa`)

## Reported

Screen `DraftRoom`, app 1.11.0, 2026-08-10, mattmurf77:

> "Can't do a second mock draft"

## Triage hypothesis

The mock session lifecycle in `backend/mock_draft_service.py` carries
`STATUS_ACTIVE` / `STATUS_ABANDONED` (~L54-56) and the routes include a
`load_current_mock_draft` shim. A finished or stale session likely still
answers as the league's "current" mock, so creating a second one is refused or
silently returns the first. Phase 1 locates the actual guard.

Serialization note: #292 and #290 both edit `mock_draft_service.py`, so they
share one build owner. #292's lifecycle fix lands before #290's engine change —
the engine work needs a repeatable second-mock loop to iterate against.
