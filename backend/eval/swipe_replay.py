"""BL-001 offline replay: what frozen trade-card swipes would have done to boards.

    python3 -m backend.eval.swipe_replay --db data/trade_finder.db \\
        --output /tmp/bl001-replay.json
    python3 -m backend.eval.swipe_replay --db "$DATABASE_URL" \\
        --allow-postgres-readonly --since 2026-08-19 --output bl001-replay.json

Packet: docs/plans/org-bringup/leads/models-lead-launch.md §BL-001-packet,
fields 5a, 5b, 6 and 7 (bars revised 2026-10-24). Scope:
docs/plans/swipe-learning/scope.md.

Since 2026-08-19 `bakeoff_runner.elo_freeze_mult` has written every trade-card
like and pass with K = 0. This tool asks what those swipes would have done to
each user's board had they carried their normal K, without writing anything.

What it rebuilds
----------------
Boards are rebuilt with ranking_service's own replay and tier mapping
(`RankingService.replay_from_db` -> `get_rankings`, `tier_for_elo`). No Elo or
tier math is restated here. A board is one (user, scoring format) with at
least --min-swipes frozen trade swipes in the window. Weeks are 7-day windows
from --since (the last one may be short).

For each board and week [start, end), two end-of-week boards share the same
start: every row before `start` with frozen trade swipes restored to K =
`trade_k_like` or `trade_k_pass` x fit_mult x --k-scale, plus every row of
the week itself (trio votes, dispositions, everything).
  WITH:    this week's trade swipes carry their restored K.
  WITHOUT: this week's trade swipes carry K = 0.
The difference is that week's trade-swipe effect and nothing else.

The pool mirrors the live session ranking pool (`server.build_universal_pool`,
reached through `_get_universal_pool` when session_init builds each format's
RankingService):
  * players: the `player_value_history` consensus snapshot for the format on
    or before --until, joined to `players` (QB/RB/WR/TE), seeded from it;
  * the 12 generic pick rungs `generic_pick_{1..4}_{early,mid,late}`, seeded
    from `pick_values.GENERIC_PICK_SEEDS` and placed in the position tabs the
    live builder uses (GENERIC_PICK_TABS, pinned to server.py's `_PICK_POS`
    by a test, since that mapping is local to the builder).
A pair applies only when both ids are in the pool, exactly as live
(`RankingService.record_trade_signal` and `replay_from_db` skip any other
pair). Restored rows are counted by id form: `generic_pick_rows_applied`,
`skipped_league_pick_rows` (league-owned `{league}_{season}_{round}_{orig}`
ids live only in the trade engine's maps, never in the ranking pool) and
`skipped_other_rows`. Tier overrides (pins) are not applied:
`users.tier_overrides` is replace-in-place, so a pin's history is not stored.

Trade swipes vs trio votes
--------------------------
`swipe_decisions.decision_type`: 'rank' = trio vote (K `elo_k`), 'trade' =
trade-card like/pass, 'disposition' = match accept/decline correction. Only
'trade' rows are restored. Trio and disposition rows keep their stored K.

Fidelity caveats (both push churn up, so the replay is an UPPER BOUND):
  * Like or pass: `swipe_decisions` doesn't say, and a frozen row's K is 0
    either way. The rows of one swipe share a `created_at`; the swipe is
    matched to the user's latest `trade_decisions` row at or before it with
    the same two sides (like: receive side won; pass: give side won). An
    unmatched swipe gets like K, the larger, and is counted.
  * fit_mult is not recoverable. `fit_congruence_mult` reads the card's signed
    `lane_shift`, which is never persisted; `deck_impressions.features_json`
    keeps only the coarse `lane` label, which can't separate a neutral pass
    (1.0) from an anti-window one (`fit_k_explained_mult`). fit_mult = 1 is an
    upper bound while both multipliers are <= 1 (defaults 0.4 / 1.0).

Metrics (also written to the output as `metric_definition`)
-----------------------------------------------------------
Groups are (position, tier) on the WITHOUT board, ranked tiers only (an
unranked player has no tier to reorder within). Within a group, players are
ordered by board rank. Only ACTIVE board-weeks (at least one trade swipe in
the week) are scored; with none, WITH equals WITHOUT.
  * 5a-i, Kendall: discordant same-group pairs / all same-group pairs. Bar:
    median <= 0.05 and p95 <= 0.15 across active board-weeks.
  * 5a-ii, percentile move: within a group of n >= 2 (singletons skipped),
    pct = rank / (n - 1) x 100 with rank 0 = top. A board-week's score is the
    max |pct_with - pct_without| over players. Bar: p95 <= 50.
  * 5b(ii), structural: players whose tier differs WITH vs WITHOUT (unranked
    counted as a tier). Must be 0: `_feedback_bounds` in
    `RankingService._compute_elo` holds trade feedback inside each band.
  * Kill-rule indicators per week, over active boards (field 6, (b) revised
    2026-10-24 before the monitor runs): (a) p95 Kendall > 0.25; (b) at least
    2 boards AND at least 5% of active boards have a player moving >= 75
    percentile points within a group of n >= 4 (smaller groups never count);
    any qualifying board short of that is an ALERT for models-lead, not a
    kill; (d) any generic-pick inversion introduced by trade swipes. (c), an
    operator report, has no replay analogue. Each week reads KILL, ALERT or OK.
  * Pick order (BL-001 A2; `pick_order`, PICK_ORDER_DEFINITION): on every
    board-week's WITH and WITHOUT boards, the generic ladder must read Early
    >= Mid >= Late within a round and min(round r) >= max(round r + 1), i.e.
    1E..4L non-increasing in Elo. An inversion is a ladder pair (higher rung,
    lower rung) with the higher rung rated below. Pre-existing inversions
    (WITHOUT) are reported; inversions introduced by trade swipes (on WITH,
    not on WITHOUT) must be 0.
p95 is nearest rank. The --k-scale result and the half-K (0.5) result are both
reported, and `ship_rule` applies the packet's rule: full K if 5a-i, 5a-ii,
5b(i) and 5b(ii) hold and no pick inversion is introduced, else half K if
they hold there, else hold.

Monitor mode (--mode monitor, the 14-day post-flip watch)
--------------------------------------------------------
--since is the knob-flip time. Boards are every (user, format) with a trade
swipe in the window (--min-swipes defaults to 1). WITH keeps every row at its
STORED k_factor (the learning that actually happened); WITHOUT is the same
week with that week's trade rows at K = 0. Same machinery and output, minus
the replay-only parts (no restore, no 5b(i), no ship rule). 5a-i and 5a-ii
are informational; kill (a), revised (b) with its alert, and (d) introduced
pick inversions (pre-existing ones excluded) decide the per-week and overall
KILL / ALERT / OK line. Those kill metrics toggle `decision_type = 'trade'`
rows only; disposition and trio rows sit in both boards, so a match accept or
decline can never trip a kill.

Dispositions (match accept / decline rows, K `trade_k_accept` /
`trade_k_decline_correction`, never frozen) get a separate, descriptive
weekly line: accept and decline counts (told apart by the match's sides, as
the disposition signal builder writes them), and within-tier Kendall and the
largest n >= 4 move from that week's disposition rows alone (WITHOUT = those
rows at K 0, trade and trio rows in both). No bar, no kill: a DISPOSITION
ALERT for models-lead when >= 2 boards in a week show a disposition-driven
move >= 75 (BL-004: the fixed decline correction over-corrects).

5b (i), reported as `check_5b_i`: restoring at K x 0 reproduces the stored
board exactly (the restore path changes nothing but frozen-window K), and the
restored board at --since equals the stored one (no board before the
re-enable time moves).

Read-only: SQLite paths open with `mode=ro`, and every engine carries a
statement guard that raises on anything but a read. A non-SQLite URL is
refused unless --allow-postgres-readonly is passed (it then also sets
`default_transaction_read_only`). This module must never import backend.server.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import statistics
import subprocess
import sys
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from sqlalchemy import create_engine, event, text

from backend import ranking_service as rs
from backend.pick_values import (GENERIC_PICK_ID_PREFIX, GENERIC_PICK_SEEDS,
                                 generic_pick_label)
from backend.ranking_service import Player, RankingService

DEFAULT_SCORING = "1qb_ppr"
DEFAULT_SINCE = "2026-08-19"
HALF_K = 0.5
BAR_KENDALL_MEDIAN = 0.05
BAR_KENDALL_P95 = 0.15
BAR_PCT_MOVE_P95 = 50.0
KILL_KENDALL_P95 = 0.25
KILL_PCT_MOVE = 75.0
KILL_SHARE = 0.05
#: Revised kill (b), field 6 (2026-10-24): at least this many boards AND
#: KILL_SHARE of active boards, counting groups of n >= KILL_B_MIN_GROUP only.
#: Fewer qualifying boards (one, typically) raise an alert, not a kill.
KILL_B_MIN_BOARDS = 2
KILL_B_MIN_GROUP = 4

METRIC_DEFINITION = (
    "Per active board-week (one user x format board, one 7-day week from "
    "--since, at least one trade swipe in it): WITH and WITHOUT are the same "
    "end-of-week board (earlier weeks' frozen trade swipes restored, all of "
    "this week's rows included) with this week's trade swipes at restored K "
    "(trade_k_like/trade_k_pass x fit_mult x k_scale) or at K = 0. Groups = "
    "(position, tier) on WITHOUT, ranked tiers only, ordered by board rank. "
    "5a-i Kendall = discordant same-group pairs / all same-group pairs; bar "
    "median <= 0.05 and p95 <= 0.15. 5a-ii = max over players of |pct_with - "
    "pct_without|, pct = rank / (n - 1) x 100 within a group of n >= 2; bar "
    "p95 <= 50. 5b(ii) = players whose tier differs WITH vs WITHOUT; must be "
    "0. Kill indicators per week: (a) p95 Kendall > 0.25, (b) >= 2 boards AND "
    ">= 5% of active boards have a percentile move >= 75 in a group of n >= 4 "
    "(fewer such boards: ALERT, not kill), (d) any introduced generic-pick "
    "inversion. p95 is nearest rank.")

#: Position tab of each generic rung by round. A copy of the `_PICK_POS`
#: literal local to `server.build_universal_pool`, which this module can't
#: import; test_swipe_replay pins the two together.
GENERIC_PICK_TABS = {1: "RB", 2: "WR", 3: "TE", 4: "QB"}
#: The generic ladder, highest rung first: rounds 1-4, Early > Mid > Late.
GENERIC_LADDER = [f"{GENERIC_PICK_ID_PREFIX}{rnd}_{tier.lower()}"
                  for rnd in sorted(GENERIC_PICK_TABS)
                  for tier in ("Early", "Mid", "Late")]
#: A league-owned pick id: `{league_id}_{season}_{round}_{original_roster}`.
LEAGUE_PICK_ID = re.compile(r"^.+_\d{4}_\d{1,2}_[^_]+$")

PICK_ORDER_DEFINITION = (
    "Per board-week, on WITH and WITHOUT: the generic ladder (rounds 1-4, "
    "Early >= Mid >= Late within a round, min(round r) >= max(round r+1)) must "
    "be non-increasing in Elo. An inversion is a ladder pair (higher rung, "
    "lower rung) with the higher rung rated below. Pre-existing = inversions "
    "on WITHOUT; introduced = inversions on WITH that are not on WITHOUT. "
    "Zero introduced passes, and it is part of the ship rule.")

CAVEATS = [
    "Upper bound: fit_mult = 1 for every restored swipe (the signed lane_shift "
    "is never persisted, so fit_congruence_mult can't be recovered; live K is "
    "scaled down by it for window-explained swipes).",
    "Upper bound: like or pass is matched through trade_decisions; an "
    "unmatched swipe takes like K (the larger) and is counted under "
    "counts.frozen_swipes_unmatched.",
]

MONITOR_CAVEATS = [
    "Monitor mode: WITH is the live board (every trade row at its stored "
    "k_factor, i.e. the learning that happened); WITHOUT zeroes that week's "
    "trade rows. 5a-i/5a-ii are informational after the flip; the kill rules "
    "(a), (b) with its alert, and (d) introduced pick inversions are what count.",
]


# ---------------------------------------------------------------------------
# Read-only access (scripts/knockout_knob_sweep.py's guard pattern)
# ---------------------------------------------------------------------------

class ReadOnlyViolation(RuntimeError):
    """Something tried to write. The run aborts rather than continue."""


_READ_PREFIXES = ("select", "with", "pragma", "begin", "commit", "rollback",
                  "set", "show", "explain", "savepoint", "release")


def _install_readonly_guard(engine) -> None:
    @event.listens_for(engine, "before_cursor_execute")
    def _guard(conn, cursor, statement, parameters, context, executemany):
        head = statement.lstrip().lstrip("(").split(None, 1)
        word = head[0].lower() if head else ""
        if word not in _READ_PREFIXES:
            raise ReadOnlyViolation(
                f"blocked a non-read statement on {engine.url.drivername}: "
                f"{statement.strip()[:200]!r}")


def open_readonly_engine(db: str, allow_postgres_readonly: bool = False):
    """A path opens as read-only SQLite. A non-SQLite URL needs the flag."""
    if "://" not in db:
        path = os.path.abspath(db)
        if not os.path.exists(path):
            raise SystemExit(f"swipe_replay: no database file at {path}")
        engine = create_engine(f"sqlite:///file:{quote(path)}?mode=ro&uri=true",
                               future=True)
    elif db.startswith("sqlite"):
        engine = create_engine(db, future=True)
    elif not allow_postgres_readonly:
        raise SystemExit(
            "swipe_replay: refusing a non-SQLite database URL. Pass "
            "--allow-postgres-readonly to read it (reads only, enforced).")
    else:
        if db.startswith("postgres://"):     # Render's form (backend.database)
            db = db.replace("postgres://", "postgresql://", 1)
        connect_args = ({"options": "-c default_transaction_read_only=on"}
                        if db.startswith("postgresql") else {})
        engine = create_engine(db, future=True, connect_args=connect_args)
    _install_readonly_guard(engine)
    return engine


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _ts(raw) -> datetime | None:
    return rs._parse_ts(raw)


def _fmt(raw) -> str:
    return raw or DEFAULT_SCORING


def _select(conn, sql: str, **params) -> list[dict]:
    return [dict(r._mapping) for r in conn.execute(text(sql), params)]


def load_model_config(conn) -> dict[str, float]:
    return {r["key"]: float(r["value"])
            for r in _select(conn, 'SELECT "key", value FROM model_config')}


def load_pool(conn, scoring_format: str, on_or_before: str):
    """(players, seed, snapshot_date) from the consensus snapshot, or None."""
    rows = _select(conn,
        "SELECT MAX(snapshot_date) AS d FROM player_value_history "
        "WHERE scoring_format = :f AND snapshot_date <= :d",
        f=scoring_format, d=on_or_before)
    snap = rows[0]["d"] if rows else None
    if not snap:
        return None
    seed = {str(r["player_id"]): float(r["consensus_elo"]) for r in _select(conn,
        "SELECT player_id, consensus_elo FROM player_value_history "
        "WHERE scoring_format = :f AND snapshot_date = :d",
        f=scoring_format, d=snap)}
    players = []
    for r in _select(conn,
            "SELECT player_id, full_name, position, team, age FROM players "
            "WHERE position IN ('QB', 'RB', 'WR', 'TE') ORDER BY player_id"):
        pid = str(r["player_id"])
        if pid in seed:
            players.append(Player(id=pid, name=r["full_name"] or pid,
                                  position=r["position"], team=r["team"] or "FA",
                                  age=int(r["age"] or 0)))
    seeds = {p.id: seed[p.id] for p in players}
    # The 12 generic rungs, as the live builder appends them after players.
    for (rnd, tier), elo in GENERIC_PICK_SEEDS.items():
        pid = f"{GENERIC_PICK_ID_PREFIX}{rnd}_{tier.lower()}"
        players.append(Player(id=pid, name=generic_pick_label(rnd, tier),
                              position=GENERIC_PICK_TABS[rnd], team="PICK", age=0))
        seeds[pid] = float(elo)
    return players, seeds, snap


def pair_kind(row: dict, pool_ids: set) -> str:
    """How live treats one swipe row: 'applied', 'generic_pick_applied',
    'skipped_league_pick' or 'skipped_other' (both ids must be in the pool)."""
    ids = (str(row["winner_player_id"]), str(row["loser_player_id"]))
    outside = [i for i in ids if i not in pool_ids]
    if not outside:
        return ("generic_pick_applied"
                if any(i.startswith(GENERIC_PICK_ID_PREFIX) for i in ids) else "applied")
    if any(LEAGUE_PICK_ID.match(i) for i in outside):
        return "skipped_league_pick"
    return "skipped_other"


def is_frozen_trade(row: dict, since: datetime, until: datetime) -> bool:
    ts = _ts(row.get("created_at"))
    return (row.get("decision_type") == "trade"
            and float(row.get("k_factor") or 0.0) == 0.0
            and ts is not None and since <= ts < until)


def load_frozen_events(conn, since: datetime, until: datetime,
                       frozen_only: bool = True, decision_type: str = "trade") -> dict:
    """{(user_id, format): {created_at: (winners, losers)}} for frozen swipes
    in the window (every row of `decision_type` in it when `frozen_only` is
    False)."""
    events: dict = defaultdict(lambda: defaultdict(lambda: (set(), set())))
    for r in _select(conn,
            "SELECT user_id, scoring_format, winner_player_id, loser_player_id, "
            "decision_type, k_factor, created_at FROM swipe_decisions "
            "WHERE decision_type = :dt"
            + (" AND k_factor = 0" if frozen_only else ""), dt=decision_type):
        ts = _ts(r["created_at"])
        if (is_frozen_trade(r, since, until) if frozen_only
                else ts is not None and since <= ts < until):
            winners, losers = events[(r["user_id"], _fmt(r["scoring_format"]))][r["created_at"]]
            winners.add(str(r["winner_player_id"]))
            losers.add(str(r["loser_player_id"]))
    return events


def load_board_rows(conn, user_id: str, scoring_format: str) -> list[dict]:
    """The user's rows for one format, in replay order (load_swipe_decisions)."""
    legacy = " OR scoring_format IS NULL" if scoring_format == DEFAULT_SCORING else ""
    return _select(conn,
        "SELECT id, winner_player_id, loser_player_id, decision_type, k_factor, "
        "created_at FROM swipe_decisions WHERE user_id = :u AND "
        f"(scoring_format = :f{legacy}) ORDER BY id",
        u=user_id, f=scoring_format)


def classify_dispositions(events: dict, matches: list[dict], user_id: str) -> dict:
    """{created_at: 'accept' | 'decline' | None} for one board's disposition
    rows. Mirrors `database` (the disposition signal builder): an accept
    writes receive > give from the user's side of the match, a decline
    give > receive. Both default to K 20, so the side, not K, tells them
    apart. user_b's sides are user_a's mirrored."""
    sides = []
    for m in matches:
        try:
            a_give = set(map(str, json.loads(m["user_a_give"] or "[]")))
            a_recv = set(map(str, json.loads(m["user_a_receive"] or "[]")))
        except (TypeError, ValueError):
            continue
        sides.append((a_give, a_recv) if m["user_a_id"] == user_id else (a_recv, a_give))
    out = {}
    for created_at, (winners, losers) in events.items():
        kind = None
        for give, recv in sides:
            if (winners, losers) == (recv, give):
                kind = "accept"
            elif (winners, losers) == (give, recv):
                kind = "decline"
            if kind:
                break
        out[created_at] = kind
    return out


def classify_events(events: dict, decisions: list[dict]) -> dict:
    """{created_at: 'like' | 'pass' | None} for one board's frozen swipes."""
    parsed = []
    for d in decisions:
        try:
            give = set(map(str, json.loads(d["give_player_ids"] or "[]")))
            recv = set(map(str, json.loads(d["receive_player_ids"] or "[]")))
        except (TypeError, ValueError):
            continue
        parsed.append((_ts(d["created_at"]), d["decision"], give, recv))
    out = {}
    for created_at, (winners, losers) in events.items():
        at = _ts(created_at)
        best = None
        for when, decision, give, recv in parsed:
            if when is None or at is None or when > at + timedelta(seconds=1):
                continue
            sides = (recv, give) if decision == "like" else (give, recv)
            if decision in ("like", "pass") and sides == (winners, losers):
                if best is None or when > best[0]:
                    best = (when, decision)
        out[created_at] = best[1] if best else None
    return out


# ---------------------------------------------------------------------------
# Boards
# ---------------------------------------------------------------------------

def restore_rows(rows, since, until, kinds, k_like, k_pass, k_scale,
                 fit_mult=1.0) -> list[dict]:
    """Frozen trade swipes in [since, until) get their K back."""
    out = []
    for r in rows:
        if is_frozen_trade(r, since, until):
            k = k_pass if kinds.get(r["created_at"]) == "pass" else k_like
            r = {**r, "k_factor": k * fit_mult * k_scale}
        out.append(r)
    return out


def rows_before(rows, cutoff: datetime) -> list[dict]:
    """Rows written before `cutoff`, in replay order. Unstamped rows count
    as history (they predate everything)."""
    out = []
    for r in rows:
        ts = _ts(r.get("created_at"))
        if ts is None or ts < cutoff:
            out.append(r)
    return out


def in_week(row: dict, start: datetime, end: datetime) -> bool:
    ts = _ts(row.get("created_at"))
    return row.get("decision_type") == "trade" and ts is not None and start <= ts < end


def without_dispositions(rows, start, end) -> list[dict]:
    """The week's disposition rows at K 0; trade and trio rows untouched."""
    return [{**r, "k_factor": 0.0}
            if r.get("decision_type") == "disposition"
            and (ts := _ts(r.get("created_at"))) is not None and start <= ts < end
            else r for r in rows]


def week_rows(rows, since, start, end, kinds, k_like, k_pass, k_scale,
              restore=True):
    """(WITH rows, WITHOUT rows, trade swipes in the week) for one week.
    `restore=False` (monitor mode) keeps every row at its stored K."""
    with_rows = rows_before(
        restore_rows(rows, since, end, kinds, k_like, k_pass, k_scale)
        if restore else rows, end)
    without = [{**r, "k_factor": 0.0} if in_week(r, start, end) else r
               for r in with_rows]
    swipes = len({r["created_at"] for r in with_rows if in_week(r, start, end)})
    return with_rows, without, swipes


def build_board(players, seed, scoring_format, rows) -> dict:
    """{player_id: (elo, position, positional rank, tier)} via ranking_service."""
    svc = RankingService(players=players, seed_ratings=seed)
    svc._scoring_format = scoring_format
    svc.replay_from_db(rows)
    board, pos_rank = {}, defaultdict(int)
    for rp in svc.get_rankings(position=None).rankings:
        pos = rp.player.position
        pos_rank[pos] += 1
        board[rp.player.id] = (rp.elo, pos, pos_rank[pos],
                               RankingService.tier_for_elo(rp.elo, pos, scoring_format))
    return board


def tier_groups(board: dict) -> list[list]:
    """Players per (position, ranked tier), ordered by board rank."""
    groups = defaultdict(list)
    for pid, (_e, pos, rank, tier) in sorted(board.items(), key=lambda kv: kv[1][2]):
        if tier is not None:
            groups[(pos, tier)].append(pid)
    return list(groups.values())


def within_tier_moves(with_board: dict, without_board: dict) -> tuple[int, int, float]:
    """(discordant pairs, same-group pairs, max percentile move) over the
    WITHOUT board's (position, tier) groups."""
    discordant = pairs = 0
    max_move = 0.0
    for members in tier_groups(without_board):
        n = len(members)
        if n < 2:
            continue
        seq = [with_board[pid][2] for pid in members]      # WITH ranks, WITHOUT order
        pairs += n * (n - 1) // 2
        discordant += sum(1 for i in range(n) for j in range(i + 1, n)
                          if seq[i] > seq[j])
        with_pos = {i: k for k, i in enumerate(sorted(range(n), key=seq.__getitem__))}
        for i in range(n):
            max_move = max(max_move, abs(with_pos[i] - i) / (n - 1) * 100)
    return discordant, pairs, max_move


def kill_b_move(with_board: dict, without_board: dict) -> float:
    """Revised kill (b)'s per-board number: the max within-tier percentile
    move, counting only groups of n >= KILL_B_MIN_GROUP (one swap in a 2- or
    3-player tier scores 50-100, so small tiers never count)."""
    best = 0.0
    for members in tier_groups(without_board):
        n = len(members)
        if n < KILL_B_MIN_GROUP:
            continue
        seq = [with_board[pid][2] for pid in members]
        with_pos = {i: k for k, i in enumerate(sorted(range(n), key=seq.__getitem__))}
        best = max(best, max(abs(with_pos[i] - i) / (n - 1) * 100 for i in range(n)))
    return best


def tier_violations(with_board: dict, without_board: dict) -> int:
    """5b(ii): players whose tier differs WITH vs WITHOUT (must be 0)."""
    return sum(1 for pid, v in without_board.items() if with_board[pid][3] != v[3])


def pick_inversions(board: dict) -> set:
    """Generic-ladder pairs (higher rung, lower rung) rated the wrong way
    round on this board: Early >= Mid >= Late within a round and every
    round-r rung >= every round-(r+1) rung, i.e. 1E..4L non-increasing."""
    rungs = [pid for pid in GENERIC_LADDER if pid in board]
    return {(hi, lo) for i, hi in enumerate(rungs) for lo in rungs[i + 1:]
            if board[hi][0] < board[lo][0]}


def pick_order(board_weeks: list[dict]) -> dict:
    """Pre-existing and trade-swipe-introduced ladder inversions; 0 introduced passes."""
    introduced = sum(w["pick_inversions_introduced"] for w in board_weeks)
    return {
        "preexisting_inversions": sum(w["pick_inversions_without"] for w in board_weeks),
        "board_weeks_with_preexisting": sum(1 for w in board_weeks
                                            if w["pick_inversions_without"]),
        "introduced_inversions": introduced,
        "board_weeks_with_introduced": sum(1 for w in board_weeks
                                           if w["pick_inversions_introduced"]),
        "verdict": "PASS" if introduced == 0 else "FAIL",
    }


def p95(values) -> float | None:
    """Nearest-rank 95th percentile."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def _median(values):
    return statistics.median(values) if values else None


def weekly_boundaries(since: datetime, until: datetime) -> list[datetime]:
    out, t = [], since
    while t < until:
        out.append(t)
        t += timedelta(days=7)
    return out + [until]


def kill_indicators(board_weeks: list[dict]) -> dict:
    """Per week, over active boards (field 6, revised 2026-10-24):
      (a) p95 Kendall > 0.25;
      (b) >= 2 boards AND >= 5% of active boards have a player moving >= 75
          percentile points within a group of n >= 4. Any qualifying board
          short of that is an ALERT for models-lead, not a kill;
      (d) any generic-pick inversion introduced by trade swipes.
    `status` is KILL, ALERT or OK."""
    by_week = defaultdict(list)
    for w in board_weeks:
        by_week[w["week_start"]].append(w)
    weeks = []
    for start in sorted(by_week):
        active = by_week[start]
        kendall = p95([w["kendall"] for w in active if w["kendall"] is not None])
        hits = [w["board"] for w in active if w["max_pct_move_n4"] >= KILL_PCT_MOVE]
        share = len(hits) / len(active)
        fires_a = kendall is not None and kendall > KILL_KENDALL_P95
        fires_b = len(hits) >= KILL_B_MIN_BOARDS and share >= KILL_SHARE
        alert_b = bool(hits) and not fires_b
        introduced = sum(w["pick_inversions_introduced"] for w in active)
        fires_d = introduced > 0
        weeks.append({"week_start": start, "active_boards": len(active),
                      "p95_kendall": kendall, "boards_ge75_n4": len(hits),
                      "share_ge75_n4": share, "boards_ge75_n4_hashes": hits,
                      "introduced_pick_inversions": introduced,
                      "fires_a": fires_a, "fires_b": fires_b, "alert_b": alert_b,
                      "fires_d": fires_d,
                      "status": ("KILL" if fires_a or fires_b or fires_d
                                 else "ALERT" if alert_b else "OK")})
    statuses = {w["status"] for w in weeks}
    return {"weeks": weeks,
            "would_have_fired": "KILL" in statuses,
            "status": ("KILL" if "KILL" in statuses
                       else "ALERT" if "ALERT" in statuses else "OK")}


def disposition_summary(board_weeks: list[dict]) -> dict:
    """Monitor-only, descriptive: match accept/decline rows per week. No bar
    and no kill. ALERT when >= KILL_B_MIN_BOARDS boards show a disposition-
    driven move >= 75 in a group of n >= 4 (catches BL-004's over-correction)."""
    by_week = defaultdict(list)
    for w in board_weeks:
        if w.get("disposition_events"):
            by_week[w["week_start"]].append(w)
    weeks = []
    for start in sorted(by_week):
        ws = by_week[start]
        kendall = [w["disposition_kendall"] for w in ws
                   if w["disposition_kendall"] is not None]
        hits = [w["board"] for w in ws
                if w["disposition_max_pct_move_n4"] >= KILL_PCT_MOVE]
        weeks.append({
            "week_start": start, "boards": len(ws),
            "accepts": sum(w["disposition_accepts"] for w in ws),
            "declines": sum(w["disposition_declines"] for w in ws),
            "unmatched": sum(w["disposition_unmatched"] for w in ws),
            "kendall_median": _median(kendall), "kendall_p95": p95(kendall),
            "max_pct_move_n4": max(w["disposition_max_pct_move_n4"] for w in ws),
            "boards_ge75_n4": len(hits), "boards_ge75_n4_hashes": hits,
            "alert": len(hits) >= KILL_B_MIN_BOARDS})
    return {"weeks": weeks, "alert": any(w["alert"] for w in weeks)}


def summarize(board_weeks: list[dict]) -> dict:
    """5a-i, 5a-ii, 5b(ii) and the kill indicators for one k_scale."""
    active = [w for w in board_weeks if w["trade_swipes"] > 0]
    kendall = [w["kendall"] for w in active if w["kendall"] is not None]
    moves = [w["max_pct_move"] for w in active]
    violations = sum(w["tier_violations"] for w in board_weeks)
    return {
        "board_weeks_active": len(active),
        "board_weeks_inactive": len(board_weeks) - len(active),
        "kendall": {"median": _median(kendall), "p95": p95(kendall),
                    "max": max(kendall) if kendall else None},
        "max_pct_move": {"median": _median(moves), "p95": p95(moves),
                         "max": max(moves) if moves else None},
        "bar_5a_i": ("NO DATA" if not kendall else "PASS"
                     if _median(kendall) <= BAR_KENDALL_MEDIAN
                     and p95(kendall) <= BAR_KENDALL_P95 else "FAIL"),
        "bar_5a_ii": ("NO DATA" if not moves else "PASS"
                      if p95(moves) <= BAR_PCT_MOVE_P95 else "FAIL"),
        "check_5b_ii": {"tier_membership_violations": violations,
                        "verdict": "PASS" if violations == 0 else "FAIL"},
        "kill_rule": kill_indicators(active),
        "pick_order": pick_order(board_weeks),
    }


def ship_rule(results: dict, check_5b_i_pass: bool) -> str:
    """The packet's rule: full K if every bar holds, else half K, else hold."""
    def holds(r):
        if r["pick_order"]["verdict"] != "PASS":      # A2: no introduced inversions
            return False
        return (check_5b_i_pass and r["bar_5a_i"] == "PASS"
                and r["bar_5a_ii"] == "PASS" and r["check_5b_ii"]["verdict"] == "PASS")
    full, half = results.get("1.0"), results.get(str(HALF_K))
    if full is not None and holds(full):
        return "ship at full K"
    if half is not None and holds(half):
        return "ship at half K (4/2)"
    if full is None and half is None:
        return "no result"
    return "hold: fails at half K (fidelity fix or hold, per field 7)"


@contextmanager
def ranking_config(values: dict):
    """Apply the DB's model_config to ranking_service for this run only."""
    saved = dict(rs._cfg)
    rs._cfg.update({k: float(v) for k, v in values.items() if k in rs._DEFAULT_CFG})
    try:
        yield
    finally:
        rs._cfg.clear()
        rs._cfg.update(saved)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------

MONITOR_KEY = "stored"


def run(engine, since: datetime, until: datetime, min_swipes: int = 10,
        k_scale: float = 1.0, mode: str = "replay") -> dict:
    """mode 'replay': frozen swipes restored to K x k_scale (and half K).
    mode 'monitor' (post-flip watch): every trade row keeps its STORED K —
    the learning that actually happened — against the same week at K = 0."""
    monitor = mode == "monitor"
    scales = ([MONITOR_KEY] if monitor
              else [k_scale] + ([HALF_K] if k_scale != HALF_K else []))
    with engine.connect() as conn:
        model_config = load_model_config(conn)
        events = load_frozen_events(conn, since, until, frozen_only=not monitor)
        # Monitor only: match accept/decline rows, reported descriptively.
        # A board with dispositions but no trade swipe is still watched.
        disp_events = (load_frozen_events(conn, since, until, frozen_only=False,
                                          decision_type="disposition")
                       if monitor else {})
        for key in disp_events:
            events.setdefault(key, {})
        with ranking_config(model_config):
            k_like, k_pass = rs._c("trade_k_like"), rs._c("trade_k_pass")
            pools, counts = {}, defaultdict(int)
            counts.update(generic_pick_rows_applied=0, skipped_league_pick_rows=0,
                          skipped_other_rows=0)
            board_weeks = {s: [] for s in scales}
            check = {"boards": 0, "a_equals_restore_at_k0": 0,
                     "b_equals_a_at_since": 0}
            per_board = []
            for (user_id, fmt), board_events in sorted(events.items()):
                disp = disp_events.get((user_id, fmt), {})
                if board_events:
                    counts["boards_with_trade_swipes" if monitor
                           else "boards_with_frozen_swipes"] += 1
                if disp:
                    counts["boards_with_dispositions"] += 1
                if len(board_events) < min_swipes and not disp:
                    counts["boards_below_min_swipes"] += 1
                    continue
                if fmt not in pools:
                    pools[fmt] = load_pool(conn, fmt, until.date().isoformat())
                if pools[fmt] is None:
                    counts["boards_without_seed_snapshot"] += 1
                    continue
                players, seed, _snap = pools[fmt]
                pool_ids = {p.id for p in players}
                rows = load_board_rows(conn, user_id, fmt)
                kinds = {} if monitor else classify_events(board_events, _select(conn,
                    "SELECT created_at, decision, give_player_ids, "
                    "receive_player_ids FROM trade_decisions WHERE user_id = :u",
                    u=user_id))
                window = [r for r in rows if in_week(r, since, until)
                          and (monitor or is_frozen_trade(r, since, until))]
                counts["boards_included"] += 1
                counts["trade_swipes" if monitor else "frozen_swipes"] += len(board_events)
                for kind in kinds.values():
                    counts[f"frozen_swipes_{kind or 'unmatched'}"] += 1
                dkinds = classify_dispositions(disp, _select(conn,
                    "SELECT user_a_id, user_a_give, user_a_receive FROM trade_matches "
                    "WHERE user_a_id = :u OR user_b_id = :u", u=user_id),
                    user_id) if disp else {}
                for kind in dkinds.values():
                    counts[f"dispositions_{kind or 'unmatched'}"] += 1
                counts["window_trade_rows" if monitor else "restored_rows"] += len(window)
                for r in window:
                    kind = pair_kind(r, pool_ids)
                    if kind != "applied":
                        counts[{"generic_pick_applied": "generic_pick_rows_applied",
                                "skipped_league_pick": "skipped_league_pick_rows",
                                "skipped_other": "skipped_other_rows"}[kind]] += 1

                def board(rs_rows):
                    return build_board(players, seed, fmt, rs_rows)
                if not monitor:
                    # 5b(i): restoring at K x 0 is the stored board; nothing
                    # before --since moves.
                    stored_until = rows_before(rows, until)
                    check["boards"] += 1
                    check["a_equals_restore_at_k0"] += int(board(restore_rows(
                        stored_until, since, until, kinds, k_like, k_pass, 0.0))
                        == board(stored_until))
                    check["b_equals_a_at_since"] += int(board(rows_before(restore_rows(
                        rows, since, until, kinds, k_like, k_pass, k_scale), since))
                        == board(rows_before(rows, since)))

                cuts = weekly_boundaries(since, until)
                key = _hash(f"{user_id}|{fmt}")
                row = {"board": key, "scoring_format": fmt,
                       "trade_swipes" if monitor else "frozen_swipes": len(board_events),
                       "weeks": len(cuts) - 1}
                for s in scales:
                    weeks = []
                    for start, end in zip(cuts, cuts[1:]):
                        with_rows, without_rows, swipes = week_rows(
                            rows, since, start, end, kinds, k_like, k_pass,
                            1.0 if monitor else s, restore=not monitor)
                        with_b, without_b = board(with_rows), board(without_rows)
                        discordant, pairs, move = within_tier_moves(with_b, without_b)
                        inv_without = pick_inversions(without_b)
                        weeks.append({
                            "board": key,
                            "pick_inversions_without": len(inv_without),
                            "pick_inversions_introduced": len(
                                pick_inversions(with_b) - inv_without),
                            "week_start": start.isoformat(), "trade_swipes": swipes,
                            "kendall": discordant / pairs if pairs else None,
                            "discordant_pairs": discordant, "same_tier_pairs": pairs,
                            "max_pct_move": move,
                            "max_pct_move_n4": kill_b_move(with_b, without_b),
                            "tier_violations": tier_violations(with_b, without_b)})
                        if monitor:
                            # Descriptive only: toggle this week's disposition
                            # rows; trade and trio rows stay in both boards.
                            week_disp = [kind for at, kind in dkinds.items()
                                         if (ts := _ts(at)) is not None
                                         and start <= ts < end]
                            d_disc = d_pairs = 0
                            d_move = 0.0
                            if week_disp:
                                wd_b = board(without_dispositions(with_rows, start, end))
                                d_disc, d_pairs, _ = within_tier_moves(with_b, wd_b)
                                d_move = kill_b_move(with_b, wd_b)
                            weeks[-1].update({
                                "disposition_events": len(week_disp),
                                "disposition_accepts": week_disp.count("accept"),
                                "disposition_declines": week_disp.count("decline"),
                                "disposition_unmatched": week_disp.count(None),
                                "disposition_kendall": (d_disc / d_pairs
                                                        if week_disp and d_pairs else None),
                                "disposition_max_pct_move_n4": d_move})
                    board_weeks[s].extend(weeks)
                    row[f"k_scale_{s}"] = weeks
                per_board.append(row)

    check["pass"] = (check["a_equals_restore_at_k0"] == check["boards"]
                     and check["b_equals_a_at_since"] == check["boards"])
    results = {str(s): summarize(board_weeks[s]) for s in scales}
    if monitor:
        results[MONITOR_KEY]["dispositions"] = disposition_summary(
            board_weeks[MONITOR_KEY])
    return {
        "mode": mode,
        "metric_definition": METRIC_DEFINITION,
        "pick_order_definition": PICK_ORDER_DEFINITION,
        "caveats": MONITOR_CAVEATS if monitor else CAVEATS,
        "window": {"since": since.isoformat(), "until": until.isoformat()},
        "k": ({"trade_k_like": k_like, "trade_k_pass": k_pass, "k": "stored"}
              if monitor else
              {"trade_k_like": k_like, "trade_k_pass": k_pass, "fit_mult": 1.0,
               "k_scale": k_scale}),
        "min_swipes": min_swipes,
        "counts": dict(counts),
        "seed_snapshots": {f: (p[2] if p else None) for f, p in pools.items()},
        "model_config_sha256": hashlib.sha256(json.dumps(
            model_config, sort_keys=True).encode()).hexdigest(),
        "results": results,
        "check_5b_i": None if monitor else check,
        "ship_rule": None if monitor else ship_rule(results, check["pass"]),
        "boards": per_board,
    }


def _provenance(db: str, engine, args) -> dict:
    database = engine.url.render_as_string(hide_password=True)
    out = {"ran_at": datetime.now(timezone.utc).isoformat(),
           "args": {**vars(args), "db": database},   # never the password
           "rng": "none on the replay path", "database": database}
    if "://" not in db:
        digest = hashlib.sha256()
        with open(db, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
        out["database_sha256"] = digest.hexdigest()
    try:
        out["code_sha"] = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
            cwd=os.path.dirname(os.path.abspath(__file__)), timeout=10,
        ).stdout.strip() or None
    except Exception:
        out["code_sha"] = None
    return out


def summary_text(report: dict) -> str:
    def n(x):
        return "n/a" if x is None else f"{x:.3g}"

    k, c = report["k"], report["counts"]
    monitor = report.get("mode") == "monitor"
    if monitor:
        head = [
            "BL-001 swipe monitor (read-only; post-flip, stored K)",
            f"  window {report['window']['since']} -> {report['window']['until']}",
            f"  model_config K like/pass now {k['trade_k_like']:g}/{k['trade_k_pass']:g}",
            f"  boards: {c.get('boards_included', 0)} included of "
            f"{c.get('boards_with_trade_swipes', 0)} with trade swipes "
            f"(min {report['min_swipes']}); trade swipes {c.get('trade_swipes', 0)}",
            f"  window trade rows {c.get('window_trade_rows', 0)}: generic-pick pairs "
            f"applied {c.get('generic_pick_rows_applied', 0)}, skipped league-pick "
            f"{c.get('skipped_league_pick_rows', 0)}, skipped other "
            f"{c.get('skipped_other_rows', 0)}",
        ]
    else:
        head = [
            "BL-001 swipe replay (read-only)",
            f"  window {report['window']['since']} -> {report['window']['until']}",
            f"  K like/pass {k['trade_k_like']:g}/{k['trade_k_pass']:g}",
            f"  boards: {c.get('boards_included', 0)} included of "
            f"{c.get('boards_with_frozen_swipes', 0)} with frozen swipes "
            f"(min {report['min_swipes']}); frozen swipes "
            f"{c.get('frozen_swipes', 0)} (like {c.get('frozen_swipes_like', 0)}, "
            f"pass {c.get('frozen_swipes_pass', 0)}, unmatched "
            f"{c.get('frozen_swipes_unmatched', 0)})",
            f"  restored rows {c.get('restored_rows', 0)}: generic-pick pairs applied "
            f"{c.get('generic_pick_rows_applied', 0)}, skipped league-pick "
            f"{c.get('skipped_league_pick_rows', 0)}, skipped other "
            f"{c.get('skipped_other_rows', 0)} (live skips the same pairs)",
        ]
    lines = head + [
        *(f"  caveat: {line}" for line in report["caveats"]),
        f"  metric: {report['metric_definition']}",
    ]
    for scale, res in report["results"].items():
        kd, mv, kill = res["kendall"], res["max_pct_move"], res["kill_rule"]
        fired = [w["week_start"][:10] for w in kill["weeks"] if w["status"] == "KILL"]
        alerts = [w["week_start"][:10] for w in kill["weeks"] if w["alert_b"]]
        title = ("  stored K" if monitor else
                 f"  k_scale {scale} (K {k['trade_k_like'] * float(scale):g}/"
                 f"{k['trade_k_pass'] * float(scale):g})")
        lines += [
            f"{title}, {res['board_weeks_active']} active board-weeks:",
            f"    5a-i  Kendall median {n(kd['median'])} p95 {n(kd['p95'])} "
            f"max {n(kd['max'])} -> {res['bar_5a_i']}",
            f"    5a-ii pct move median {n(mv['median'])} p95 {n(mv['p95'])} "
            f"max {n(mv['max'])} -> {res['bar_5a_ii']}",
            f"    5b(ii) tier-membership violations "
            f"{res['check_5b_ii']['tier_membership_violations']} -> "
            f"{res['check_5b_ii']['verdict']}",
            f"    kill rule (a)/(b)/(d) would have fired: "
            f"{'yes, weeks ' + ', '.join(fired) if fired else 'no'}; (b) alert weeks: "
            f"{', '.join(alerts) if alerts else 'none'}",
            (f"    (d) introduced pick inversions "
             f"{res['pick_order']['introduced_inversions']}" if monitor else
             f"    pick order: pre-existing inversions "
             f"{res['pick_order']['preexisting_inversions']}, introduced "
             f"{res['pick_order']['introduced_inversions']} -> "
             f"{res['pick_order']['verdict']}"),
        ]
        if monitor:
            for w in kill["weeks"]:
                why = [r for r, on in (("a", w["fires_a"]), ("b", w["fires_b"]),
                                       ("d", w["fires_d"])) if on]
                lines.append(
                    f"    week {w['week_start'][:10]}: {w['status']}"
                    + (f" (kill {', '.join(why)})" if why else "")
                    + (f" (alert b: boards {', '.join(w['boards_ge75_n4_hashes'])})"
                       if w["alert_b"] else "")
                    + f"; active boards {w['active_boards']}, p95 Kendall "
                    f"{n(w['p95_kendall'])}, boards >=75 in n>=4 "
                    f"{w['boards_ge75_n4']}, introduced pick inversions "
                    f"{w['introduced_pick_inversions']}")
            lines.append(f"  overall: {kill['status']}")
            disp = res["dispositions"]
            for w in disp["weeks"]:
                lines.append(
                    f"    dispositions week {w['week_start'][:10]} (descriptive, no "
                    f"kill): accepts {w['accepts']}, declines {w['declines']}, "
                    f"unmatched {w['unmatched']}; Kendall median "
                    f"{n(w['kendall_median'])} p95 {n(w['kendall_p95'])}; largest "
                    f"move (n>=4) {n(w['max_pct_move_n4'])}; DISPOSITION ALERT: "
                    + (f"yes (boards {', '.join(w['boards_ge75_n4_hashes'])})"
                       if w["alert"] else "no"))
            if not disp["weeks"]:
                lines.append("    dispositions: none in the window")
            lines.append(f"  disposition alert (models-lead review, not a kill): "
                         f"{'ALERT' if disp['alert'] else 'none'}")
    if not monitor:
        chk = report["check_5b_i"]
        lines += [
            f"  5b(i): restore at K x 0 == stored on {chk['a_equals_restore_at_k0']}/"
            f"{chk['boards']} boards; restored == stored at --since on "
            f"{chk['b_equals_a_at_since']}/{chk['boards']} -> "
            f"{'PASS' if chk['pass'] else 'FAIL'}",
            f"  ship rule: {report['ship_rule']}",
        ]
    return "\n".join(lines)


def _parse_day(value: str) -> datetime:
    ts = _ts(value)
    if ts is None:
        raise argparse.ArgumentTypeError(f"not an ISO date: {value!r}")
    return ts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--db", required=True, help="SQLite path or database URL")
    ap.add_argument("--allow-postgres-readonly", action="store_true",
                    help="permit a non-SQLite URL (reads only, enforced)")
    ap.add_argument("--since", type=_parse_day, default=None,
                    help=f"window start (replay default {DEFAULT_SINCE}; "
                         "monitor: required, the knob-flip time)")
    ap.add_argument("--until", type=_parse_day,
                    default=datetime.now(timezone.utc))
    ap.add_argument("--mode", choices=("replay", "monitor"), default="replay",
                    help="replay: frozen swipes restored (13b); monitor: the "
                         "post-flip watch at stored K, --since = the flip time")
    ap.add_argument("--min-swipes", type=int, default=None,
                    help="boards need this many trade swipes in the window "
                         "(default 10 for replay, 1 for monitor)")
    ap.add_argument("--k-scale", type=float, choices=(1.0, 0.5), default=1.0)
    ap.add_argument("--output", required=True, help="JSON report path")
    args = ap.parse_args(argv)
    if args.since is None:
        if args.mode == "monitor":
            ap.error("--mode monitor needs --since: the bakeoff_freeze_trade_k "
                     "flip time (model_config_changes.changed_at)")
        args.since = _parse_day(DEFAULT_SINCE)
    if args.min_swipes is None:
        args.min_swipes = 1 if args.mode == "monitor" else 10

    engine = open_readonly_engine(args.db, args.allow_postgres_readonly)
    report = run(engine, args.since, args.until, args.min_swipes, args.k_scale,
                 mode=args.mode)
    report["provenance"] = _provenance(args.db, engine, args)
    with open(args.output, "w") as fh:
        json.dump(report, fh, indent=2, default=str)
    print(summary_text(report))
    print(f"  report: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
