"""
trends_service.py — Fantasy Trade Finder
=========================================
Computation layer for the Trends tier-2 tab (Rank Players → Trends).

Exposes three pure-functional helpers consumed by the new
`/api/trends/*` endpoints in `server.py`:

  1. compute_contrarian_score      — single 0-100 score measuring how much
                                     the user's rankings diverge from the
                                     league-wide community consensus, plus
                                     Top-5-above / Top-5-below splits.

  2. compute_consensus_gap         — per-player gap = user_elo - community_elo.
                                     Surfaces "easiest sells from your roster"
                                     (user values > market) and "easiest buys
                                     not on your roster" (user values > owner).

  3. compute_risers_fallers        — thin wrapper over the raw elo_history
                                     rows from database.load_elo_history;
                                     picks the biggest 30-day swings per
                                     position.

All three are deliberately kept as pure functions operating on plain
dicts / lists so they are trivially testable.  No DB I/O lives here —
the caller passes data in.  Heavy lifting in the v1 is O(N) over the
player pool, easily well under one second even for 600-player pools.
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# 1. Contrarian meter
# ---------------------------------------------------------------------------
#
# Community consensus ELO for a player = mean of that player's ELO across all
# OTHER users in the league who have submitted rankings in this format.  We
# then compute, per player:
#
#     delta_i = user_elo_i - community_elo_i
#
# Contrarian score = 100 * (mean |delta| / calibration_scale), clamped to
# [0, 100].  The calibration scale is the typical spread we see in practice
# (~200 ELO points), so a user whose average deviation is 200+ scores 100,
# a user whose rankings match the mean exactly scores 0.
#
# Alongside the single score we return the Top-5 players where the user is
# ABOVE consensus and the Top-5 where the user is BELOW consensus — this is
# what fills the "You love / You fade" split on the UI.
# ---------------------------------------------------------------------------

_CONTRARIAN_CALIBRATION = 200.0      # ELO-point spread that maps to score 100
_MIN_BASELINE_USERS      = 3          # ≥ 3 community rankers required per plan
_MIN_PLAYERS_COMPARED    = 10         # need at least this many overlap players


def compute_contrarian_score(
    user_elo: dict[str, float],
    community_rankings: dict[str, dict],
    players_by_id: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """
    Args:
        user_elo:             { player_id: elo }  — the logged-in user's ELO.
        community_rankings:   { user_id: { "username": str,
                                           "elo_ratings": { pid: elo } } }
                              — output shape of load_member_rankings().
        players_by_id:        { player_id: {name, position, team, ...} } for
                              enriching the above/below lists.  Optional —
                              the endpoint layer enriches if omitted.

    Returns:
        {
          "has_baseline":      bool,
          "baseline_user_count": int,
          "score":             float (0-100) or None,
          "compared_players":  int,
          "above_consensus":   [ {player_id, name, position, user_elo, community_elo, delta}, ... ],
          "below_consensus":   [ ... ],
        }

        When has_baseline is False (< 3 other rankers), score + lists are
        empty and the frontend should render a polite empty-state.
    """
    baseline_n = len(community_rankings or {})
    if baseline_n < _MIN_BASELINE_USERS:
        return {
            "has_baseline":         False,
            "baseline_user_count":  baseline_n,
            "score":                None,
            "compared_players":     0,
            "above_consensus":      [],
            "below_consensus":      [],
        }

    # Community mean ELO per player
    community_elo: dict[str, float] = {}
    counts: dict[str, int]          = {}
    for uid, data in community_rankings.items():
        ratings = (data or {}).get("elo_ratings") or {}
        for pid, elo in ratings.items():
            try:
                e = float(elo)
            except (TypeError, ValueError):
                continue
            community_elo[pid] = community_elo.get(pid, 0.0) + e
            counts[pid]        = counts.get(pid, 0) + 1
    for pid, total in list(community_elo.items()):
        n = counts.get(pid) or 1
        community_elo[pid] = total / n

    deltas: list[dict[str, Any]] = []
    for pid, u_elo in (user_elo or {}).items():
        if pid not in community_elo:
            continue
        try:
            u_val = float(u_elo)
        except (TypeError, ValueError):
            continue
        c_val = community_elo[pid]
        row = {
            "player_id":     pid,
            "user_elo":      round(u_val, 1),
            "community_elo": round(c_val, 1),
            "delta":         round(u_val - c_val, 1),
        }
        if players_by_id and pid in players_by_id:
            p = players_by_id[pid]
            row["name"]     = p.get("name") or p.get("full_name") or pid
            row["position"] = p.get("position")
            row["team"]     = p.get("team")
        deltas.append(row)

    if len(deltas) < _MIN_PLAYERS_COMPARED:
        # Not enough overlap — treat like no baseline.
        return {
            "has_baseline":         False,
            "baseline_user_count":  baseline_n,
            "score":                None,
            "compared_players":     len(deltas),
            "above_consensus":      [],
            "below_consensus":      [],
        }

    mean_abs = sum(abs(d["delta"]) for d in deltas) / len(deltas)
    score    = max(0.0, min(100.0, 100.0 * mean_abs / _CONTRARIAN_CALIBRATION))

    above = sorted(deltas, key=lambda d: d["delta"], reverse=True)[:5]
    below = sorted(deltas, key=lambda d: d["delta"])[:5]

    return {
        "has_baseline":         True,
        "baseline_user_count":  baseline_n,
        "score":                round(score, 1),
        "compared_players":     len(deltas),
        "above_consensus":      above,
        "below_consensus":      below,
    }


# ---------------------------------------------------------------------------
# 2. Consensus gap (per-player 0-99 score)
# ---------------------------------------------------------------------------
#
# For every player with both a user ELO and a community ELO, compute:
#
#     gap = user_elo - community_elo
#
# Rendered two ways:
#   • Easiest sells from roster: players you own whose user_elo > community.
#     Sell before market catches up.
#   • Easiest buys not on roster: players on OPPONENT rosters whose
#     user_elo > that specific owner's ELO (not the community mean).
#     Target the owner that undervalues them most.
#
# The 0-99 score is a normalised magnitude so the UI can render a bar.
# ---------------------------------------------------------------------------


def _normalise_gap(gap: float, scale: float = 400.0) -> int:
    """Map an ELO-point gap onto 0-99 for UI rendering."""
    pct = min(99.0, max(0.0, abs(gap) / scale * 100.0))
    return int(round(pct))


def compute_consensus_gap(
    user_elo: dict[str, float],
    community_rankings: dict[str, dict],
    user_roster: list[str],
    league_members: list[dict],
    players_by_id: dict[str, dict] | None = None,
    top_n: int = 5,
) -> dict[str, Any]:
    """
    Args:
        user_elo:           { player_id: elo }.
        community_rankings: { user_id: { username, elo_ratings } }.
        user_roster:        list of player_ids owned by the logged-in user.
        league_members:     list of { user_id, username, roster } — owner
                            lookup for "easiest buys not on your roster".
        players_by_id:      enrichment data (name, position, team).
        top_n:              how many rows to surface per side.

    Returns:
        {
          "has_baseline":      bool,
          "baseline_user_count": int,
          "easiest_sells":     [ {player_id, name, position, user_elo, community_elo, gap, score}, ... ],
          "easiest_buys":      [ {player_id, name, position, user_elo, owner_elo, owner_username, gap, score}, ... ],
        }
    """
    baseline_n = len(community_rankings or {})
    if baseline_n < _MIN_BASELINE_USERS:
        return {
            "has_baseline":        False,
            "baseline_user_count": baseline_n,
            "easiest_sells":       [],
            "easiest_buys":        [],
        }

    # Community mean ELO
    community_elo: dict[str, float] = {}
    counts: dict[str, int]          = {}
    for uid, data in community_rankings.items():
        ratings = (data or {}).get("elo_ratings") or {}
        for pid, elo in ratings.items():
            try:
                e = float(elo)
            except (TypeError, ValueError):
                continue
            community_elo[pid] = community_elo.get(pid, 0.0) + e
            counts[pid]        = counts.get(pid, 0) + 1
    for pid, total in list(community_elo.items()):
        n = counts.get(pid) or 1
        community_elo[pid] = total / n

    # Owner index — pid → (owner_user_id, owner_username)
    owner_of: dict[str, tuple[str, str]] = {}
    for m in (league_members or []):
        owner_uid   = m.get("user_id")
        owner_uname = m.get("username") or m.get("display_name") or owner_uid
        for pid in (m.get("roster") or m.get("player_ids") or []):
            owner_of[pid] = (owner_uid, owner_uname)

    roster_set = set(user_roster or [])

    def _enrich(pid: str, row: dict) -> dict:
        if players_by_id and pid in players_by_id:
            p = players_by_id[pid]
            row["name"]     = p.get("name") or p.get("full_name") or pid
            row["position"] = p.get("position")
            row["team"]     = p.get("team")
        return row

    # ── Easiest sells from your roster ──────────────────────────────────
    sells: list[dict[str, Any]] = []
    for pid in roster_set:
        if pid not in user_elo or pid not in community_elo:
            continue
        try:
            u = float(user_elo[pid])
        except (TypeError, ValueError):
            continue
        c   = community_elo[pid]
        gap = u - c
        if gap <= 0:
            # Only surface players where YOU value them ABOVE the market.
            continue
        sells.append(_enrich(pid, {
            "player_id":     pid,
            "user_elo":      round(u, 1),
            "community_elo": round(c, 1),
            "gap":           round(gap, 1),
            "score":         _normalise_gap(gap),
        }))
    sells.sort(key=lambda d: d["gap"], reverse=True)
    sells = sells[:top_n]

    # ── Easiest buys not on your roster ─────────────────────────────────
    buys: list[dict[str, Any]] = []
    for pid, u_elo in user_elo.items():
        if pid in roster_set:
            continue
        if pid not in owner_of:
            # Nobody on the league owns them → waiver wire, skip.
            continue
        owner_uid, owner_uname = owner_of[pid]
        owner_data = (community_rankings or {}).get(owner_uid)
        if not owner_data:
            # Owner hasn't submitted rankings — fall back to community mean
            owner_elo = community_elo.get(pid)
        else:
            owner_elo = (owner_data.get("elo_ratings") or {}).get(pid)
            if owner_elo is None:
                owner_elo = community_elo.get(pid)
        if owner_elo is None:
            continue
        try:
            u = float(u_elo)
            o = float(owner_elo)
        except (TypeError, ValueError):
            continue
        gap = u - o
        if gap <= 0:
            continue
        buys.append(_enrich(pid, {
            "player_id":       pid,
            "user_elo":        round(u, 1),
            "owner_elo":       round(o, 1),
            "owner_user_id":   owner_uid,
            "owner_username":  owner_uname,
            "gap":             round(gap, 1),
            "score":           _normalise_gap(gap),
        }))
    buys.sort(key=lambda d: d["gap"], reverse=True)
    buys = buys[:top_n]

    return {
        "has_baseline":        True,
        "baseline_user_count": baseline_n,
        "easiest_sells":       sells,
        "easiest_buys":        buys,
    }


# ---------------------------------------------------------------------------
# 3. Risers / Fallers past 30 days
# ---------------------------------------------------------------------------
#
# Given the raw history rows (one per player per snapshot) plus the current
# ELO map, compute per-player delta = current_elo - earliest_elo_in_window.
# Return the Top-N risers and Top-N fallers per position.
# ---------------------------------------------------------------------------


def compute_risers_fallers(
    current_elo: dict[str, float],
    history_rows: list[dict],
    players_by_id: dict[str, dict] | None = None,
    top_n: int = 5,
    window_days: int = 30,                # reserved for future windowing
) -> dict[str, Any]:
    """
    Args:
        current_elo:    { player_id: elo }  — present ELO snapshot.
        history_rows:   list of {player_id, elo, snapshot_at} rows, ordered
                        oldest-first.  Caller decides the window — this fn
                        just computes (current - earliest) per player.
        players_by_id:  enrichment (name, position).
        top_n:          rows returned per side per position.

    Returns:
        {
          "risers": {"QB": [...], "RB": [...], "WR": [...], "TE": [...], "ALL": [...]},
          "fallers": {...},
          "window_days": 30,
          "sample_size": int,    # distinct players with history
        }
    """
    # Earliest snapshot per player within supplied history
    earliest: dict[str, float] = {}
    for row in (history_rows or []):
        pid = row.get("player_id")
        if not pid:
            continue
        try:
            e = float(row.get("elo"))
        except (TypeError, ValueError):
            continue
        # history_rows arrive oldest-first, so the first one wins.
        if pid not in earliest:
            earliest[pid] = e

    moves: list[dict[str, Any]] = []
    for pid, curr in (current_elo or {}).items():
        if pid not in earliest:
            continue
        try:
            c = float(curr)
        except (TypeError, ValueError):
            continue
        delta = c - earliest[pid]
        if abs(delta) < 1e-3:
            continue
        row = {
            "player_id":     pid,
            "current_elo":   round(c, 1),
            "previous_elo":  round(earliest[pid], 1),
            "delta":         round(delta, 1),
        }
        if players_by_id and pid in players_by_id:
            p = players_by_id[pid]
            row["name"]     = p.get("name") or p.get("full_name") or pid
            row["position"] = p.get("position")
            row["team"]     = p.get("team")
        moves.append(row)

    by_pos_up:   dict[str, list] = {"QB": [], "RB": [], "WR": [], "TE": [], "ALL": []}
    by_pos_down: dict[str, list] = {"QB": [], "RB": [], "WR": [], "TE": [], "ALL": []}
    for m in moves:
        by_pos_up["ALL"].append(m)
        by_pos_down["ALL"].append(m)
        pos = m.get("position")
        if pos in by_pos_up:
            by_pos_up[pos].append(m)
            by_pos_down[pos].append(m)

    risers  = {k: sorted(v, key=lambda r: r["delta"], reverse=True)[:top_n]
               for k, v in by_pos_up.items()}
    fallers = {k: sorted(v, key=lambda r: r["delta"])[:top_n]
               for k, v in by_pos_down.items()}

    return {
        "risers":       risers,
        "fallers":      fallers,
        "window_days":  window_days,
        "sample_size":  len(moves),
    }
