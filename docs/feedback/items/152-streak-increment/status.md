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

**→ Fixed 2026-07-25 — see "Residual fixes" below.**

## Files changed

- `backend/database.py` — `_RANK_STREAK_EVENTS` (+ comment).
- `backend/server.py` — tz threading on two `record_event` call sites.
- `backend/tests/test_streaks.py` — NEW (7 tests).
- `docs/data-dictionary.md` — event-taxonomy note updated.

## Residual fixes (2026-07-25, same worktree branch)

### 1. Lapsed streaks now decay to 0 on read

Display-time computation only — the stored row is never mutated, so the
write-side transition (`_recompute_streak_on_rank_event`, which keys off the
stored value + date) is untouched: a lapsed user's next rank still resets to
1 and increments normally the day after (pinned by test).

- `get_user_streak(user_id, tz=None)` — reports effective `current` = 0 when
  `last_rank_local_date` is >1 day behind local today (exactly the gap that
  would reset the counter on the next write; "yesterday" still displays).
  `longest` never decays. **Tz resolution at read time:** the viewer's
  `X-User-TZ` header (`g.user_tz` — same source the #152 write fix threads
  into `record_event`), passed by both call sites (`GET /api/me/streak`,
  `post_rank3` fallback); falls back to the stored `users.last_rank_tz` (the
  frame the date was written in), then UTC.
- Streak leaderboard (`_streak_top` / `_streak_self_rank`) — same rule per
  row, using each row's own stored `last_rank_tz` (UTC fallback; there is no
  per-viewer header for other users). Lapsed rows decay to 0 and are dropped
  (board only lists >0), so lapsed users can't squat on top spots; survivors
  keep effective == stored, so ordering needs no re-sort. A conservative SQL
  prefilter (`last_rank_local_date >= utc_today - 2` — older is lapsed in
  every tz, offsets span UTC-12..+14) bounds the fetch; Python applies the
  exact per-row tz check. `_streak_self_rank` counts only non-lapsed
  better rows and returns None for a lapsed viewer.

### 2. anchor_answered / ranking_reorder now bump `users.last_rank_at`

Added both to `_EVENT_TO_USER_COL` (→ `last_rank_at`), the same map the
other rank-class events use inside `record_event()` — notification-nudge
gating keyed off `last_rank_at` undercounted anchor-wizard and
manual-board users.

### Tests added (`backend/tests/test_streaks.py`, same frozen-clock pattern)

- `test_lapsed_user_reads_zero_longest_preserved_row_unmutated`
- `test_active_user_reads_unchanged`
- `test_read_decay_uses_stored_tz_when_no_viewer_tz`
- `test_lapsed_user_ranking_again_resets_then_increments`
- `test_leaderboard_lapsed_high_streak_ranks_below_active`
- `test_rank_surface_events_update_last_rank_at[anchor_answered|ranking_reorder]`

### Files changed (residual fixes)

- `backend/database.py` — `_EVENT_TO_USER_COL` (+2 events), new
  `_streak_lapsed()` helper, `get_user_streak(tz=...)`, `_streak_top`,
  `_streak_self_rank`.
- `backend/server.py` — `GET /api/me/streak` + `post_rank3` fallback pass
  `tz=g.user_tz` into `get_user_streak`.
- `backend/tests/test_streaks.py` — +7 tests (14 total).
- `docs/data-dictionary.md` — users streak columns documented (effective-
  streak read semantics, `last_rank_at` event set).
- `docs/api-reference.md` — `/api/me/streak` + `/api/leaderboard` rows note
  effective-streak decay.
