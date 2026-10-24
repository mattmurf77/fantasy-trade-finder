"""BL-001 offline replay: what frozen trade-card swipes would have done to boards.

    python3 -m backend.eval.swipe_replay --db data/trade_finder.db \\
        --output /tmp/bl001-replay.json
    python3 -m backend.eval.swipe_replay --db "$DATABASE_URL" \\
        --allow-postgres-readonly --since 2026-08-19 --output bl001-replay.json

Packet: docs/plans/org-bringup/leads/models-lead-launch.md §BL-001-packet,
fields 5a, 5b (i), 6 and 7. Scope: docs/plans/swipe-learning/scope.md.

Since 2026-08-19 `bakeoff_runner.elo_freeze_mult` has written every trade-card
like and pass with K = 0. This tool asks what those swipes would have done to
each user's board had they carried their normal K, without writing anything.

What it rebuilds
----------------
For each (user, scoring format) board with at least --min-swipes frozen trade
swipes in the window, the board is rebuilt at every weekly boundary from
--since to --until (the last week may be short) twice, using ranking_service's
own replay and tier mapping (`RankingService.replay_from_db` -> `get_rankings`,
`RankingService.tier_for_elo`). No Elo or tier math is restated here.

  (A) as stored: every `swipe_decisions` row with its stored `k_factor`. This
      is the board prod rebuilds at session_init today.
  (B) restored: the same rows, except each frozen trade swipe in the window
      (`decision_type = 'trade'`, `k_factor = 0`, since <= created_at < until)
      gets K = `trade_k_like` or `trade_k_pass` x fit_mult x --k-scale.

Seeds are the `player_value_history` consensus snapshot for the format on or
before --until; the pool is that snapshot joined to `players` (QB/RB/WR/TE).
Generic pick assets have no `players` row, so pairs involving them are skipped
identically in (A) and (B) (counted as `restored_rows_outside_pool`). Tier
overrides (pins) are not applied: `users.tier_overrides` is replace-in-place,
so a pin's history is not stored.

Trade swipes vs trio votes
--------------------------
`swipe_decisions.decision_type`: 'rank' = trio vote (K `elo_k`), 'trade' =
trade-card like/pass, 'disposition' = match accept/decline correction. Only
'trade' rows are restored. Trio and disposition rows keep their stored K.

Like or pass: `swipe_decisions` doesn't say, and a frozen row's K is 0 either
way. The rows of one swipe share a `created_at`; the swipe is matched to the
user's latest `trade_decisions` row at or before it with the same two sides
(like: receive side won; pass: give side won). An unmatched swipe gets like
K, the larger, and is counted.

fit_mult is not recoverable. `fit_congruence_mult` reads the card's signed
`lane_shift`, which is never persisted. `deck_impressions.features_json` keeps
only the coarse `lane` label, joinable only through
`trade_decisions.impression_id` when `trade.valuation_telemetry` was on, and
for a pass on a 'value' card it can't separate neutral (1.0) from anti-window
(`fit_k_explained_mult`). The replay uses fit_mult = 1, an upper bound while
both fit multipliers are <= 1 (defaults 0.4 / 1.0).

Metric (also written to the output as `metric_definition`)
----------------------------------------------------------
For each user-week (one board, one week [start, end)):
  * top tier = the top `tier_size` players (model_config, default 24) per
    position on board (A) at week start, by positional rank: ranking_service's
    own "top tier" unit;
  * for each of those players, the band move the restored swipes caused this
    week: (band_B(end) - band_B(start)) - (band_A(end) - band_A(start)), with
    band = index in ORDERED_TIERS and unranked = one below the last band;
  * user-week band move = max |that| over the top tier;
  * user-week rank churn = mean |same difference on positional rank|.
Reported: median and p95 (nearest rank) of user-week band moves, and each
board's mean rank churn across its weeks. Bar 5a: median <= 1 and p95 <= 2.
The --k-scale result and the half-K (0.5) result are both reported.

Note: the owner's within-tier feedback contract (`_feedback_bounds` in
`RankingService._compute_elo`) clamps every trade-swipe update inside the
player's post-ranking tier band, so trade swipes can reorder players inside a
tier but cannot move them across bands. Expect band moves of 0; rank churn is
where restored swipes show up.

5b (i), reported as `check_5b_i`: restoring at K x 0 reproduces board (A)
exactly (the restore path changes nothing but frozen-window K), and board (B)
at --since equals board (A) there (no board before the re-enable time moves).

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
import statistics
import subprocess
import sys
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from sqlalchemy import create_engine, event, text

from backend import ranking_service as rs
from backend.ranking_service import ORDERED_TIERS, Player, RankingService

POSITIONS = ("QB", "RB", "WR", "TE")
DEFAULT_SCORING = "1qb_ppr"
DEFAULT_SINCE = "2026-08-19"
BAR_MEDIAN = 1.0
BAR_P95 = 2.0
HALF_K = 0.5

METRIC_DEFINITION = (
    "Per user-week (one board, one week [start, end)): top tier = the top "
    "tier_size players (model_config, default 24) per position on board A at "
    "week start, by positional rank. For each, band move = "
    "(band_B(end) - band_B(start)) - (band_A(end) - band_A(start)), band = "
    "index in ORDERED_TIERS, unranked = one below the last band. User-week "
    "band move = max |band move| over the top tier; user-week rank churn = "
    "mean |same difference on positional rank|. A = stored K; B = frozen "
    "trade swipes in the window restored to trade_k_like/trade_k_pass x "
    "fit_mult x k_scale. Bar 5a: median <= 1 and p95 (nearest rank) <= 2 "
    "across user-weeks.")


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
    return players, {p.id: seed[p.id] for p in players}, snap


def is_frozen_trade(row: dict, since: datetime, until: datetime) -> bool:
    ts = _ts(row.get("created_at"))
    return (row.get("decision_type") == "trade"
            and float(row.get("k_factor") or 0.0) == 0.0
            and ts is not None and since <= ts < until)


def load_frozen_events(conn, since: datetime, until: datetime) -> dict:
    """{(user_id, format): {created_at: (winners, losers)}} for frozen swipes."""
    events: dict = defaultdict(lambda: defaultdict(lambda: (set(), set())))
    for r in _select(conn,
            "SELECT user_id, scoring_format, winner_player_id, loser_player_id, "
            "decision_type, k_factor, created_at FROM swipe_decisions "
            "WHERE decision_type = 'trade' AND k_factor = 0"):
        if is_frozen_trade(r, since, until):
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
    """Rows for board (B): frozen window trade swipes get their K back."""
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


def band_index(tier) -> int:
    return ORDERED_TIERS.index(tier) if tier in ORDERED_TIERS else len(ORDERED_TIERS)


def top_tier(board: dict, size: int) -> set:
    return {pid for pid, (_e, _p, rank, _t) in board.items() if rank <= size}


def user_week_metrics(a0, a1, b0, b1, top) -> tuple[int, float]:
    """(max |band move|, mean |rank move|) the restored swipes caused this week."""
    bands, ranks = [], []
    for pid in top:
        bands.append(abs((band_index(b1[pid][3]) - band_index(b0[pid][3]))
                         - (band_index(a1[pid][3]) - band_index(a0[pid][3]))))
        ranks.append(abs((b1[pid][2] - b0[pid][2]) - (a1[pid][2] - a0[pid][2])))
    if not top:
        return 0, 0.0
    return max(bands), sum(ranks) / len(ranks)


def p95(values) -> float | None:
    """Nearest-rank 95th percentile."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def weekly_boundaries(since: datetime, until: datetime) -> list[datetime]:
    out, t = [], since
    while t < until:
        out.append(t)
        t += timedelta(days=7)
    return out + [until]


def summarize(user_weeks: list[dict], per_board_churn: dict) -> dict:
    bands = [w["band_move"] for w in user_weeks]
    means = list(per_board_churn.values())
    if not bands:
        verdict = "NO DATA"
    else:
        verdict = ("PASS" if statistics.median(bands) <= BAR_MEDIAN
                   and p95(bands) <= BAR_P95 else "FAIL")
    return {
        "user_weeks": len(bands),
        "band_move": {"median": statistics.median(bands) if bands else None,
                      "p95": p95(bands), "max": max(bands) if bands else None},
        "rank_churn_per_board_mean": {
            "median": statistics.median(means) if means else None,
            "p95": p95(means), "max": max(means) if means else None},
        "bar_5a": verdict,
    }


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

def run(engine, since: datetime, until: datetime, min_swipes: int = 10,
        k_scale: float = 1.0) -> dict:
    scales = [k_scale] + ([HALF_K] if k_scale != HALF_K else [])
    with engine.connect() as conn:
        model_config = load_model_config(conn)
        events = load_frozen_events(conn, since, until)
        with ranking_config(model_config):
            k_like, k_pass = rs._c("trade_k_like"), rs._c("trade_k_pass")
            size = int(rs._c("tier_size"))
            pools, counts = {}, defaultdict(int)
            user_weeks = {s: [] for s in scales}
            churn = {s: {} for s in scales}
            check = {"boards": 0, "a_equals_restore_at_k0": 0,
                     "b_equals_a_at_since": 0}
            per_board = []
            for (user_id, fmt), board_events in sorted(events.items()):
                counts["boards_with_frozen_swipes"] += 1
                if len(board_events) < min_swipes:
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
                kinds = classify_events(board_events, _select(conn,
                    "SELECT created_at, decision, give_player_ids, "
                    "receive_player_ids FROM trade_decisions WHERE user_id = :u",
                    u=user_id))
                frozen = [r for r in rows if is_frozen_trade(r, since, until)]
                counts["boards_included"] += 1
                counts["frozen_swipes"] += len(board_events)
                for kind in kinds.values():
                    counts[f"frozen_swipes_{kind or 'unmatched'}"] += 1
                counts["restored_rows"] += len(frozen)
                counts["restored_rows_outside_pool"] += sum(
                    1 for r in frozen if str(r["winner_player_id"]) not in pool_ids
                    or str(r["loser_player_id"]) not in pool_ids)

                cuts = weekly_boundaries(since, until)
                a = [build_board(players, seed, fmt, rows_before(rows, t)) for t in cuts]
                check["boards"] += 1
                k0 = restore_rows(rows_before(rows, until), since, until, kinds,
                                  k_like, k_pass, 0.0)
                check["a_equals_restore_at_k0"] += int(
                    build_board(players, seed, fmt, k0) == a[-1])
                row = {"board": _hash(f"{user_id}|{fmt}"), "scoring_format": fmt,
                       "frozen_swipes": len(board_events), "weeks": len(cuts) - 1}
                for s in scales:
                    restored = restore_rows(rows, since, until, kinds, k_like, k_pass, s)
                    b = [build_board(players, seed, fmt, rows_before(restored, t))
                         for t in cuts]
                    if s == k_scale:
                        check["b_equals_a_at_since"] += int(b[0] == a[0])
                    weeks = []
                    for i in range(len(cuts) - 1):
                        band, rank = user_week_metrics(a[i], a[i + 1], b[i], b[i + 1],
                                                       top_tier(a[i], size))
                        weeks.append({"week_start": cuts[i].isoformat(),
                                      "band_move": band, "rank_churn": rank})
                    user_weeks[s].extend(weeks)
                    churn[s][row["board"]] = (sum(w["rank_churn"] for w in weeks)
                                              / len(weeks)) if weeks else 0.0
                    row[f"k_scale_{s}"] = {
                        "max_band_move": max((w["band_move"] for w in weeks), default=0),
                        "mean_rank_churn": churn[s][row["board"]],
                        "weeks": weeks}
                per_board.append(row)

    check["pass"] = (check["a_equals_restore_at_k0"] == check["boards"]
                     and check["b_equals_a_at_since"] == check["boards"])
    return {
        "metric_definition": METRIC_DEFINITION,
        "window": {"since": since.isoformat(), "until": until.isoformat()},
        "k": {"trade_k_like": k_like, "trade_k_pass": k_pass, "fit_mult": 1.0,
              "fit_mult_note": "not recoverable (signed lane_shift is never "
                               "persisted); 1.0 is an upper bound",
              "k_scale": k_scale, "tier_size": size},
        "min_swipes": min_swipes,
        "counts": dict(counts),
        "seed_snapshots": {f: (p[2] if p else None) for f, p in pools.items()},
        "model_config_sha256": hashlib.sha256(json.dumps(
            model_config, sort_keys=True).encode()).hexdigest(),
        "results": {str(s): summarize(user_weeks[s], churn[s]) for s in scales},
        "check_5b_i": check,
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
    k, c = report["k"], report["counts"]
    lines = [
        "BL-001 swipe replay (read-only)",
        f"  window {report['window']['since']} -> {report['window']['until']}",
        f"  K like/pass {k['trade_k_like']:g}/{k['trade_k_pass']:g}, fit_mult 1.0 "
        "(not recoverable; upper bound)",
        f"  boards: {c.get('boards_included', 0)} included of "
        f"{c.get('boards_with_frozen_swipes', 0)} with frozen swipes "
        f"(min {report['min_swipes']}); frozen swipes "
        f"{c.get('frozen_swipes', 0)} (like {c.get('frozen_swipes_like', 0)}, "
        f"pass {c.get('frozen_swipes_pass', 0)}, unmatched "
        f"{c.get('frozen_swipes_unmatched', 0)} -> like K)",
        f"  metric: {report['metric_definition']}",
    ]
    def n(x):
        return "n/a" if x is None else f"{x:.3g}"

    for scale, res in report["results"].items():
        band, churn = res["band_move"], res["rank_churn_per_board_mean"]
        lines.append(
            f"  k_scale {scale} (K {k['trade_k_like'] * float(scale):g}/"
            f"{k['trade_k_pass'] * float(scale):g}): {res['user_weeks']} user-weeks, "
            f"band move median {n(band['median'])} p95 {n(band['p95'])} "
            f"max {n(band['max'])}; rank churn per board median {n(churn['median'])} "
            f"p95 {n(churn['p95'])} -> bar 5a {res['bar_5a']}")
    chk = report["check_5b_i"]
    lines.append(
        f"  5b(i): restore at K x 0 == A on {chk['a_equals_restore_at_k0']}/"
        f"{chk['boards']} boards; B == A at --since on {chk['b_equals_a_at_since']}/"
        f"{chk['boards']} -> {'PASS' if chk['pass'] else 'FAIL'}")
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
    ap.add_argument("--since", type=_parse_day, default=_parse_day(DEFAULT_SINCE))
    ap.add_argument("--until", type=_parse_day,
                    default=datetime.now(timezone.utc))
    ap.add_argument("--min-swipes", type=int, default=10)
    ap.add_argument("--k-scale", type=float, choices=(1.0, 0.5), default=1.0)
    ap.add_argument("--output", required=True, help="JSON report path")
    args = ap.parse_args(argv)

    engine = open_readonly_engine(args.db, args.allow_postgres_readonly)
    report = run(engine, args.since, args.until, args.min_swipes, args.k_scale)
    report["provenance"] = _provenance(args.db, engine, args)
    with open(args.output, "w") as fh:
        json.dump(report, fh, indent=2, default=str)
    print(summary_text(report))
    print(f"  report: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
