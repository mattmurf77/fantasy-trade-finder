# #152 — Streak always stays at 1 — status

**State:** fixed (2026-07-25, worktree branch off `teardown-remediation`).
**Owner ask (mattmurf77, League, v1.9.1):** "It doesn't look like streaks is
actually working. My streak always stays at 1."

## Root cause

The streak counter (`users.current_streak`, advanced inside
`backend/database.py::record_event` → `_recompute_streak_on_rank_event`)
only moves on `_RANK_STREAK_EVENTS`, which was
`{trio_swipe, tier_save, ranking_complete_first_time}`. The date math
itself is correct (verified by simulation: day-1 → 1, day-2 → 2, gap → 1).

The operator's daily ranking surface is the **Pick Anchor wizard** — the dev
DB shows 405 `anchor_answered` events and ZERO `trio_swipe`/`tier_save`
rows. `anchor_answered` (Anchors) and `ranking_reorder` (manual board, which
Quick Rank also posts through) were never in the qualifying set, so daily
anchor/reorder ranking left the streak frozen at whatever an earlier
qualifying day wrote — i.e. permanently "1". Their `record_event` call sites
also didn't pass `tz`, so even as qualifying events they'd have used UTC
local-days instead of the client's.

## Fix

- `backend/database.py` — `_RANK_STREAK_EVENTS` += `anchor_answered`,
  `ranking_reorder`. (Deliberately shared with the "Ranks" leaderboard
  metric, which counts rank-class events: anchor/reorder users were also
  invisible there.) `quickset_completed`/`quickrank_completed` ride along
  with the `tier_save`/`ranking_reorder` fired in the same request, so they
  are not added separately.
- `backend/server.py` — the `anchor_answered` and `ranking_reorder`
  `record_event` calls now pass `tz=getattr(g, "user_tz", None)` (the
  `X-User-TZ` header), matching `trio_swipe`/`tier_save`.

## Tests (`backend/tests/test_streaks.py`, new — frozen clock, no sleeps)

- `test_day1_then_day2_increments_to_2[anchor_answered|ranking_reorder|trio_swipe]`
  — the task's regression shape; anchor/reorder variants fail pre-fix.
- `test_gap_day_resets_to_1_and_keeps_longest`
- `test_same_day_re_rank_is_noop`
- `test_local_day_uses_client_tz_not_utc`
- `test_non_rank_events_do_not_advance_streak`

## Known residual (out of scope, worth a follow-up)

Reads never decay: `get_user_streak` / the streak leaderboard report the
STORED `current_streak` even after the streak has lapsed (last rank > 1 local
day ago). A user who stops ranking shows their old streak forever until the
next rank-class event resets it. Display-side "0 when lapsed" would make the
chip honest between sessions.

## Files changed

- `backend/database.py` — `_RANK_STREAK_EVENTS` (+ comment).
- `backend/server.py` — tz threading on two `record_event` call sites.
- `backend/tests/test_streaks.py` — NEW (7 tests).
- `docs/data-dictionary.md` — event-taxonomy note updated.
