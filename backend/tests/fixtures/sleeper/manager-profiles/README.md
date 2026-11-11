# Fixture — Sleeper league history for manager profiles

**Fully synthetic** (ids, players, timestamps), shaped field-for-field on the
public `GET /v1/league/<id>/transactions/<week>` payload as observed on
2026-11-10: every row carries `type, status, transaction_id, leg, roster_ids,
creator, consenter_ids, adds, drops, draft_picks, waiver_budget, settings,
metadata, created, status_updated`; a FAAB claim's bid is
`settings.waiver_bid`; a failed claim's reason is `metadata.notes`.

| File | What it pins |
|---|---|
| `league.json` | FAAB league (`settings.waiver_type` 2, budget 100) |
| `rosters.json` | roster 1 sole owner · roster 2 **co-owned** (`co_owners` = `…022`) · roster 3 **no history** · roster 4 **ownerless** |
| `players.json` | position + birth_date for the player ids involved (`TB` is a team defense, deliberately absent) |
| `transactions_1.json` | one completed trade (player + 1st-round pick + $10 FAAB), one pending trade, a won $30 claim, the co-owner's **outbid** $25 claim on the same player in the same run, a $5 claim failed for roster size, a pending claim, a free-agent DEF add, and a free-agent add by a **non-owner** (commissioner) |
| `transactions_2.json` | a won $50 claim (remaining budget 100 − 30 + 10 = 80) |

Used by `backend/tests/test_manager_profiles.py`. Design:
`docs/plans/manager-profiles/design.md`.
