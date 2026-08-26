# Status — #369, the plan beat

**Item:** #369 (`mattmurf77`, screen `TeamReview`) — *"The plan summary page only shows
window.. it's a good page intent but needs more detail. I think we just show the full set of
adjustments a user can make with the trade finder."*

**State:** built, gates green, **committed but NOT pushed and NOT merged** — the parent agent
integrates. Requires a client release; nothing here is in build 122.

| | |
|---|---|
| Branch | `worktree-agent-a7bed877f805980b0` (off `origin/main` `bc43b6f`) |
| Flag | none added — confined to the `plan` beat inside the already-lit `trades.team_review` |
| Backend | **untouched** |
| Docs | [scope.md](scope.md) · [code-walk.md](code-walk.md) · [testflight-checklist.md](testflight-checklist.md) |
| Decisions | [D-130](../../../../living-memory/DECISIONS.md), [D-131](../../../../living-memory/DECISIONS.md) |
| Ledger | `living-memory/TEST_LEDGER.md` § 2026-08-20b |

## What shipped

1. The `plan` beat is a **standing summary of every trade-finder lever**, read from saved
   preferences (`GET /api/league/preferences`, `GET /api/league/asset-prefs`, the fairness
   AsyncStorage key, the `useFinderTargets` store) instead of session-local React state. The
   three `league_preferences` levers are editable in place through the existing write path.
2. **Root-cause fix:** `savePrefs` backfills `team_outlook`. Without it the depth beat's write
   400'd on every call since the feature shipped, which is the actual reason the page showed
   only the window.
3. **Third defect fixed:** the scoped partner is now handed to the deck via the #330 handoff
   store on exit, so the beat's "I've already pointed the finder at it" is true.

## Owed

- Operator runs [testflight-checklist.md](testflight-checklist.md) (9 steps) on the next build;
  outcome into TEST_LEDGER. Steps 2, 3 and 7 are the load-bearing ones.
- Integrator: the handoff auto-run emits `find_trades_tapped{source:'league_offer'}`
  (`TradesScreen.tsx:2408`), so a Team-Review-originated auto-run is misattributed. Fixing it
  means extending the handoff shape and editing `TradesScreen.tsx`, outside this agent's
  ownership.
- When `feat/jon-360-362` lands `trade.avoid_positions`, add an "Avoiding" line to the
  positions block and the matching lever string to `check-team-review.js` assertion 8, in the
  same commit.
