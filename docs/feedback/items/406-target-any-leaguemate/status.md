# FB-406
- **Status:** planned 2026-08-30
- **Group:** G-406 (canonical — batch plan for the 2026-08-30 run lives here: [plan.md](plan.md))
- **Reported:** `jonbonjourvi`, screen `TradesHome`, v1.16.10, filed 2026-08-29T02:42Z
- **Report:** "Let you select any league mate as well as individual ones. So that it shows you all options for the player you're trying to move"
- **Related prior work:** [403-shop-a-player](../402-more-offers-shop/) (shop shipped lit, canonical in 402), [250-team-targeting](../250-team-targeting/status.md) (team-scope correctness), [374-partners-copy-and-finder-conditions](../374-partners-copy-and-finder-conditions/)
- **Planner verdict (2026-08-30):** POLISH — the report maps to the merged landing's canvas Team dropdown (`InLeagueCalculator.tsx:538-541, :1451-1494`), which forces one league mate; the league-wide sweep already ships end-to-end (`POST /api/trades/fair-packages` with `opponent_user_id` omitted, `server.py:12398-12399` → `trade_service.py:5797-5803`, tested in `test_fair_packages.py`). Fix = client-only "Any league mate" picker row, zero backend diff; serialize behind #407 (same file, same root behavior). Plan: [plan-g406.md](plan-g406.md).
