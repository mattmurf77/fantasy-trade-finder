# Status — team overhaul

```project-status
{
  "status": "built dark",
  "updated": "2026-09-07",
  "summary": "v1 built on branch claude/team-overhaul-scoping-ea1c72 behind overhaul.enabled=false: backend (5 tables, 14 routes, solver, Sleeper send via extracted propose core, ownership-derived refresh) + iOS flow (Acquire entry card, 8 Trades-stack screens) + structural guard. Not merged, not deployed, no TestFlight build.",
  "evidence": "BUILD-CONTRACT.md is the binding v1 contract; D-188 records the nine adopted defaults (not owner-approved). Backend: 45 overhaul tests + existing propose tests green; independent review findings 1-12 fixed with regression tests; full-suite result in living-memory/TEST_LEDGER.md. Mobile: tsc clean, all check-*.js guards incl. check-team-overhaul.js (18 assertions) pass, testid-lint OK. QA.md device checklist UNRUN. Owner must confirm D1 (Sleeper-only sends) and D9 (Acquire placement) before the flag flips."
}
```
