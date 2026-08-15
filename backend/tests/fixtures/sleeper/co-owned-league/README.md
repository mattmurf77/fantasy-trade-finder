# Fixture — Sleeper league with a co-owned roster

Captured from the real case that motivated co-owner support, 2026-08-15:
league `1338231586314780672` ("Bush League"), where `mattmurf77`
(`313560442465169408`) is a **co-owner** of `roster_id 3` — `owner_id` is
`460238423161040896` and their id appears in `co_owners`.

```
roster_id 3   owner_id 460238423161040896   co_owners ["313560442465169408"]
```

**Real:** the league id, all twelve `owner_id`s, and the co-ownership. Those are
the fixture's whole point.
**Synthetic:** the player lists — three per roster, globally unique
(`p<roster>_<n>`), so a test can answer "whose roster did we resolve?" from the
player ids alone. Roster contents are irrelevant to an identity bug.

Modeled on the shape of the other real `co_owners` example in
`backend/tests/fixtures/draft/ffv3-predraft/league/1312140920132497408/rosters.json`
(roster 2 there is co-owned) — that one exists for draft-order tests and keeps
full rosters.

Used by `backend/tests/test_co_owner_rosters.py`. Background:
`docs/plans/sleeper-co-owner-rosters/scope.md`.
