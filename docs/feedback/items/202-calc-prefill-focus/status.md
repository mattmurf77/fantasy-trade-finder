# #202 — Prefill arrival is disorienting (scoped fix)

**Operator:** "I navigated from a suggested trade → to wanting to edit a
trade… and the UI is presenting me which team to trade even though I've
already made that distinction… It's disorienting for the top of the UI to
present team selection rather than the trade I'm trying to edit."
**Status:** BUILT 2026-07-27 (branch `teardown-remediation`, isolated
worktree). Scoped fix only — the broader calculator redesign awaits the #205
interview; nothing else about the layout changed.

## What shipped

- `mobile/src/components/InLeagueCalculator.tsx`: when the calculator mounts
  WITH a prefill (`initialOpponentId` set — the #190 deck "Edit in
  calculator" path), the opponent picker section renders COLLAPSED to one
  compact row at the very top — "Trading with @username · Change" — so the
  trade sides + verdict are immediately visible. Tapping "Change" expands
  today's full partner-chip picker (chips + ranked note), which then stays
  expanded for the session.
- No-prefill mounts are pixel-identical to before (state initializes from
  `!!initialOpponentId`). If a prefilled opponent id doesn't resolve against
  the league's members, the full picker renders (collapse requires the
  resolved opponent).
- testIDs: `calc.partner-collapsed` (the row) · `calc.partner-change` (the
  expand control). Registered in `mobile/src/components/CLAUDE.md`.

## Verification

- `cd mobile && npx tsc --noEmit` → clean.
- Backend untouched: `python3 -m pytest backend/tests -q` → 1346 passed,
  1 skipped (branch baseline).
