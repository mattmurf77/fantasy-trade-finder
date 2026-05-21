# Feedback queue — TestFlight captures

Pulled from `GET /api/feedback/admin` on 2026-05-21. 18 real notes (ids 3–20).

## Auto-fix in progress (subagent batches)

| Batch | Ids | Screens | Notes |
|---|---|---|---|
| A | 7, 8, 9, 10 | Matches | Empty-state bubble overflow, accept/decline 500, FA/FLX positions, bubble height clipping |
| B | 13, 18, 20 | Trios | Stale "10/10" counter, "more rank options" affordance, rookies link |
| C | 11 | Portfolio | Per-league double-counting of player exposures |
| D | 17 | League | "Opponents you've ranked vs" empty |

Each batch lands as its own PR for review.

## Queued for your decision (not auto-fixing)

| # | Sev | Screen | Note | Why queued |
|---|---|---|---|---|
| 3 | polish | TradesHome | View liked trades awaiting other owner | New surface; needs design + likely backend column |
| 4 | bug | TradesHome | Replace fairness slider with on/off toggle | UX direction change — not a bug, an opinion shift |
| 5 | polish | TradesHome | Remove "only equal trades" button | Tied to #4 redesign; ship together |
| 6 | bug | TradesHome | Every trade shows 100% match | Symptom not root cause — needs backend dig into `match_score` calc |
| 12 | polish | General | Slow to load between pages | Needs profiling; not a one-PR fix |
| 14 | polish | Tiers | Drop-zone visual separation while dragging | Worklet/gesture work — careful surgery after the recent crash fix |
| 15 | polish | Tiers | Long-press to enter multi-select | Conflicts with the 220ms long-press drag activation; needs gesture arbitration design |
| 16 | bug | Tiers | Select button doesn't visually mark tiles | Tied to #15 multi-select rework |
| 19 | polish | Trios | "Obvious" rank sets trigger too often | Threshold tuning — needs you to set "1 per 50 rankings/pos" or similar exact number |

## Recurring poll

Re-fetch with: `curl -sS "https://fantasy-trade-finder.onrender.com/api/feedback/admin?since_id=20&limit=100" -H "X-Cron-Secret: $SECRET" | python3 -m json.tool`
