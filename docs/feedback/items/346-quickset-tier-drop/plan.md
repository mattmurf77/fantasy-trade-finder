# Batch plan — feedback wave 2026-08-24

> Batch-level plan for the 2026-08-24 feedback run (orchestrated by the
> `/feedback` pipeline). Lives here because #346 is the lowest selected item.
> Selection recorded in chat 2026-08-24: operator approved groups A, B, C, D, F
> plus the status-anomaly corrections. No express declared — full gates per
> group path.

## Selected items and groups

| Group | Items | Canonical folder | Path | Platforms | One-line scope |
|---|---|---|---|---|---|
| A | #376 #379 #394 (+#333 verify) | `376-finder-filters-regression/` | Fast-track bug → escalate if layout work grows | mobile (poss. backend flags) | Outlook & preferences / finder filters entry missing from TradesHome on 1.16.2 — regression of the #376 class after the #384 merged-calculator rebuild. #394 is operator-flagged most critical. |
| B | #397 #398 | `397-swipe-tour-placement/` | Fast-track bug | mobile | Swipe right/left tour step placement → top of screen above trade chip section (#398 supersedes #397). |
| C | #395 #396 | `395-lineup-impact-superflex/` | Fast-track bug | backend | Starting-lineup impact: superflex slot attribution wrong (Daniels→SF), and flex slots mislabeled ("WR3" in a 2-WR+flex league). |
| D | #386 #391 | `386-analyst-playoff-odds/` | Fast-track bug | mobile | Analyst pop-up broken when playoff-odds section expanded on LeagueRankings; #391 is the minimized-state observation (context). |
| F | #346 #381 | `346-quickset-tier-drop/` | Fast-track bug | mobile (poss. backend) | QuickSet tiers: downgrading / not re-selecting a previously-tiered player drops them to FA/zero instead of holding or stepping one tier. #381 has the detailed repro. |

Groups are independent — Phases 1–4 run per group in parallel where possible.
Shared-file risk: A, B and D all touch mobile Trades/League surfaces;
A and B both touch `TradesScreen`/tour components — build agents for A and B
must have explicit disjoint file ownership or serialize (B after A if overlap
is found at plan time).

## Not selected this run (recorded dispositions)

- Parked ideas: #331 #332 #352 #362 #385 (player cards, breakout finder,
  like/dislike, cycling labels, quick stats). #205 needs an operator
  interview, not a build. #310 verify-and-close against 1.16.x (#384+D-158
  delivered the substance). #393 routes to the fit-challenger program.
- Status corrections applied to prod 2026-08-24: `fixed` — #355 #357 #358
  #359 #364 #366 #367 #368 #373 #374 #375; `in_progress` — #344 #365 #369
  #371 #372 (built behind dark flags / graduation pending).
- #360/#361 (in_progress, no work trace) — likely folds into Group A's
  outlook & prefs surface; flagged in A's plan as a check, not built here.
- #363 — expected addressed by D-159 knockout refine (merged 2026-08-24);
  verify on next build before any new work.

## Evidence posture (D-056)

No Maestro, no simulator. Per group: structural `mobile/tests/check-*.js`
guards and/or pytest where mechanically checkable, a file:line code-walk
proof per requirement, and a manual TestFlight checklist for the operator.

## Ship gate

Batch ships as one wave (Phase 5): CI green (pytest, tsc, testid-lint),
TEST_LEDGER entry, docs-sync, then explicit operator go/no-go.
