# DTF Trade Calculator — Mockup Plan (2026-07-02)

*Condensed plan doc for the standalone iPhone mockup. The real feature's plan lives at
[docs/plans/manual-trade-calculator-plan.md](../../docs/plans/manual-trade-calculator-plan.md).*

## Vision & premise

A single-screen dynasty trade calculator that demonstrates FTF's core differentiator:
**trades are scored on both owners' boards, not one consensus list**. Because two owners
rank the same players differently (positional leans, youth vs. win-now bias), a trade can
be a genuine win for both sides — and the calculator surfaces exactly those packages.

## Scope

**In:** manual trade building (send/receive), live dual-perspective fairness verdict,
fair-offer suggestions (1–3 player packages), player picker with search + position filter,
partner switching across 3 mock leaguemates with distinct board personalities.

**Out (mocked or excluded by design):** Sleeper login, league sync, ranking/Elo building
(mock boards stand in), the trade finder, draft picks, persistence, backend calls.

## Mechanics

- **Boards:** each owner's value for a player = consensus base × positional lean ×
  age bias × deterministic per-owner jitter (±4%) — a stable, personal "ranking set".
- **Package value:** sorted values weighted [1, 0.88, 0.78, 0.70, …] — a consolidation
  premium so depth pieces can't buy a stud (mirrors the engine's package_value idea).
- **Verdict:** computed from each side's percent gain *on their own board*:
  Win–win / Fair / You win big — they likely decline / You're overpaying / Uneven.
- **Suggestions:** exhaustive 1–3 player combos from the open side's roster, kept only if
  Fair or Win–win, ranked by `min(bothGains) − 0.5·|gainGap|` (maximize mutual benefit,
  penalize lopsidedness).

## Mock league

"Lakeview Dynasty": Murph's Turf (you, near-consensus), Gridiron Gurus (RB premium),
Youth Movement (youth bias), Win Now Willy (vet bias). 48 players, 12 per roster,
Elo-like values ~900–2600.

## Tech

Expo SDK 54 / React Native 0.81 / TypeScript, matching `mobile/`. No navigation lib —
one screen + native modals. Theme mirrors `mobile/src/theme` (FTF dark palette).
TestFlight path: EAS build/submit with bundle id `com.fantasytradefinder.tradecalc`.

## Success criteria (all verified in web preview 2026-07-02)

- [x] Type-checks clean (`tsc --noEmit`)
- [x] Add/remove players on both sides; one-sided state shows both boards' package value
- [x] Verdict panel renders both perspectives with gains/losses
- [x] Suggestions update live and apply on tap
- [x] Partner switch clears the receive side and recomputes
