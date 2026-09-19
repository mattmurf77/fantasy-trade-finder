# FB-291 — "The mock draft should be interactive"

- **Type:** bug (reproduction unverified) · **Status:** planned 2026-08-10
- **Group:** G2 — Mock draft: engine, lifecycle, interactivity
- **Canonical folder:** [`290-mock-draft-engine/`](../290-mock-draft-engine/) —
  plan, PRD and design deltas for #290/#291/#292 all live there.
- **Batch plan:** [`289-mfl-draft-room-ids/batch-plan.md`](../289-mfl-draft-room-ids/batch-plan.md)
- **Branch:** `feedback-289-294` (base `origin/main` @ `7cea1fa`)

## Reported

Screen `MockDraft`, app 1.11.0, 2026-08-10, mattmurf77:

> "The mock draft should be interactive. The user should get to draft their own
> players at the very least."

## Triage note — likely already built

`mobile/src/screens/MockDraftScreen.tsx` documents itself as "the only surface
in this app where a pick can be made" and carries a user pick path
(`pickMutation.mutate(selected)`, ~L471). The read-only surface is the *Draft
Room* (`DraftRoomScreen.tsx` ~L369, "Read-only on purpose").

So the report probably describes something other than a missing feature: a
typed-empty refusal state, an auto-advanced turn, an entry-point/discoverability
failure, or the tester being on the Draft Room rather than the mock session.
Phase 1 answers this before any code is written — per pipeline lessons, two
prior agents correctly shipped zero production code for reports that no longer
reproduced.
