# Feedback queue — TestFlight captures

## 2026-06-10 fetch (ids 21–48, next_since_id=48)

**New from operator testing on v1.1.0 (2026-06-10):**

| # | Sev | Screen | Note | Disposition |
|---|---|---|---|---|
| 45 | bug | Trios | Resume/login state breaks app; player fetch only on fresh login | **FIXED 2026-06-10** — root cause: server sessions are in-memory and die on every deploy while the app restores a token from secure-store and never re-inits. Added `revalidateSession()` (cold launch + foreground resume, throttled 60s) + a 401 guard so stale responses can't clear a freshly-minted token |
| 46 | bug | TradesHome | "Swipe didn't save" on every trade acceptance | **FIXED 2026-06-10** — same root: deck predates a deploy → every `record_decision` hit "Unknown trade_id" → 400. Swipe payload now echoes card context (give/receive/target/league); server reconstructs + registers the card and the full decision flow (Elo, persistence, match check) proceeds. `trade_card_to_dict` now serializes `target_user_id`. Tests: `test_swipe_reconstruct.py` |
| 47 | idea | TradesHome | Standalone trade finder vs roster positional strength; works without league-mates | **QUEUED** — overlaps shipped consensus-basis cards + pinned-give flow; the new piece is positional-strength counterparty targeting. In `living-memory/NEXT.md` |
| 48 | bug | Portfolio | Players and leagues double-counted | **FIXED 2026-06-10** — Sleeper mints a new league_id per season; `league_members` held last season's instance of each league (verified: Lakeview + FFv3 each exist under two ids), so carried-over players counted twice. `/api/portfolio?league_ids=` now scopes to the client's current-season league list (mobile + web pass it). Tests: `test_portfolio_exposure.py` |

**Older items (06-08/06-09, ids 26–44):** 26/33 (Trios tile cleanup) shipped as #83; 41 (league team count) as #82; 22/23/27/29 (tiers drag) as #84; 44 (multi-select bulk-move) as #85; 35/36 (match accept failures) addressed by the FB-01 disposition fix. **Operator verified 2026-06-10: 16/27/29/32/43 (the whole tiers drag + multi-select cluster) confirmed working on-device → shipped.** 28/30/31/34/37/38/39/40/42 are polish/design items — 31/34 shipped, rest not yet scheduled. 21/25 are Claude probes (ignore).

Re-fetch with: `curl -sS "https://fantasy-trade-finder.onrender.com/api/feedback/admin?since_id=48&limit=100" -H "X-Cron-Secret: $SECRET" | python3 -m json.tool`

---

## 2026-05-21 fetch

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
