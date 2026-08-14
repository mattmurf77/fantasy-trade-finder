# Recovery ledger — 2026-08-13/14 feedback wave sweep

> Capture-then-delete. Verification by content against `origin/main`.

## Branches swept

| Branch | Tip | Landed as |
|---|---|---|
| `wave-backend` | `b048388` | PR #117 → `7057d86` |
| `wave-league` | `e1500d2` | PR #117 → `7057d86` |
| `wave-matches` | `41ddd53` | PR #117 → `7057d86` |
| `wave-trades` | `8c5709c` | PR #117 → `7057d86` |
| `wave-integration` | `11e468b` | PR #117 → `7057d86` |
| `ship-1.13.4` (clone-local) | `7fb1e34` | pushed directly to main |

## Worktrees removed

`.claude/worktrees/wave-backend` · `wave-league` · `wave-matches` · `wave-trades` · `wave-integration`

**NOT swept:** `wave-calc` (branch `wave-calc` @ `6b6c513`) — holds the committed
calculator-group plan, HELD on operator decision D-306-1. Sweep it with that
group's ship.

## Where the work landed

- `7057d86` (PR #117) + `7fb1e34` — eleven items, v1.13.4.
- TestFlight **build 111**, submitted 2026-08-14.
