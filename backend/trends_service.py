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
# 0. Rank derivation (shared helper)
# ---------------------------------------------------------------------------
#
# Rank is a pure presentation view of the ELOs the backend already has: sort
# players by ELO (highest = rank 1) and read off the 1-based index.  We expose
# two views:
#
#   • Overall rank  — position in the whole pool.
#   • Positional rank — position within the player's own position group
#                       (RB rank, WR rank, …).
#
# "Previous rank" is the same computation applied to a prior-ELO snapshot
# (reconstructed from elo_history).  A rank DELTA is previous_rank - current_rank
# so that a player who climbed from #10 to #7 reports +3 (moved UP 3 spots),
# matching the up/down direction of the ELO delta.  Players missing from a
# snapshot get no rank there, and downstream callers degrade to None ("—").
# ---------------------------------------------------------------------------


def _rank_map(elo_by_id: dict[str, float]) -> dict[str, int]:
    """Return { player_id: overall_rank } (1-based) sorted by ELO desc.

    Ties broken by player_id for a stable, deterministic ordering.  Non-numeric
    ELOs are skipped (player simply has no rank).
    """
    cleaned: list[tuple[str, float]] = []
    for pid, elo in (elo_by_id or {}).items():
        try:
            cleaned.append((pid, float(elo)))
        except (TypeError, ValueError):
            continue
    cleaned.sort(key=lambda t: (-t[1], t[0]))
    return {pid: i + 1 for i, (pid, _) in enumerate(cleaned)}


def _pos_rank_map(
    elo_by_id: dict[str, float],
    players_by_id: dict[str, dict] | None,
) -> dict[str, int]:
    """Return { player_id: positional_rank } (1-based) within each position.

    Players whose position is unknown (no enrichment) are omitted — there is
    no position group to rank them in.
    """
    by_pos: dict[str, list[tuple[str, float]]] = {}
    for pid, elo in (elo_by_id or {}).items():
        pos = ((players_by_id or {}).get(pid) or {}).get("position")
        if not pos:
            continue
        try:
            val = float(elo)
        except (TypeError, ValueError):
            continue
        by_pos.setdefault(pos, []).append((pid, val))

    out: dict[str, int] = {}
    for rows in by_pos.values():
        rows.sort(key=lambda t: (-t[1], t[0]))
        for i, (pid, _) in enumerate(rows):
            out[pid] = i + 1
    return out


def _rank_delta(prev_rank: int | None, curr_rank: int | None) -> int | None:
    """previous_rank - current_rank → positive = moved UP (toward #1)."""
    if prev_rank is None or curr_rank is None:
        return None
    return prev_rank - curr_rank


# ---------------------------------------------------------------------------
# 0b. Community mean ELO (shared helper)
# ---------------------------------------------------------------------------


def _community_mean_elo(community_rankings: dict[str, dict]) -> dict[str, float]:
    """{ player_id: mean elo across all community rankers }.

    community_rankings has the load_member_rankings() shape:
    { user_id: { "username": str, "elo_ratings": { pid: elo } } }.
    Non-numeric ELOs are skipped.
    """
    community_elo: dict[str, float] = {}
    counts: dict[str, int] = {}
    for uid, data in (community_rankings or {}).items():
        ratings = (data or {}).get("elo_ratings") or {}
        for pid, elo in ratings.items():
            try:
                e = float(elo)
            except (TypeError, ValueError):
                continue
            community_elo[pid] = community_elo.get(pid, 0.0) + e
            counts[pid] = counts.get(pid, 0) + 1
    for pid, total in list(community_elo.items()):
        n = counts.get(pid) or 1
        community_elo[pid] = total / n
    return community_elo


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
    community_elo = _community_mean_elo(community_rankings)

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
    community_elo = _community_mean_elo(community_rankings)

    # Owner index — pid → (owner_user_id, owner_username)
    owner_of: dict[str, tuple[str, str]] = {}
    for m in (league_members or []):
        owner_uid   = m.get("user_id")
        owner_uname = m.get("username") or m.get("display_name") or owner_uid
        for pid in (m.get("roster") or m.get("player_ids") or []):
            owner_of[pid] = (owner_uid, owner_uname)

    roster_set = set(user_roster or [])

    # Rank views — express the gap as "your rank vs the comparison rank".
    #   • user ranks come from the user's own ELO pool.
    #   • community ranks come from the community-mean pool (sells comparison).
    #   • owner ranks are derived per-owner on demand (buys comparison),
    #     memoised so each owner is sorted at most once.
    user_overall  = _rank_map(user_elo)
    user_pos      = _pos_rank_map(user_elo, players_by_id)
    comm_overall  = _rank_map(community_elo)
    comm_pos      = _pos_rank_map(community_elo, players_by_id)

    _owner_rank_cache: dict[str, tuple[dict[str, int], dict[str, int]]] = {}

    def _owner_ranks(owner_uid: str) -> tuple[dict[str, int], dict[str, int]]:
        if owner_uid not in _owner_rank_cache:
            ratings = ((community_rankings or {}).get(owner_uid) or {}).get("elo_ratings") or {}
            _owner_rank_cache[owner_uid] = (
                _rank_map(ratings),
                _pos_rank_map(ratings, players_by_id),
            )
        return _owner_rank_cache[owner_uid]

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
        u_rank = user_overall.get(pid)
        c_rank = comm_overall.get(pid)
        u_prank = user_pos.get(pid)
        c_prank = comm_pos.get(pid)
        sells.append(_enrich(pid, {
            "player_id":     pid,
            "user_elo":      round(u, 1),
            "community_elo": round(c, 1),
            "gap":           round(gap, 1),
            "score":         _normalise_gap(gap),
            # Rank view: positive rank_gap = you rank them nearer #1 than market.
            "user_rank":          u_rank,
            "comparison_rank":    c_rank,
            "rank_gap":           _rank_delta(c_rank, u_rank),
            "user_pos_rank":      u_prank,
            "comparison_pos_rank": c_prank,
            "pos_rank_gap":       _rank_delta(c_prank, u_prank),
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
        # Owner rank comparison mirrors the ELO fallback: use the owner's own
        # ranking when present, else the community-mean ranking.
        if owner_data:
            o_overall, o_pos = _owner_ranks(owner_uid)
        else:
            o_overall, o_pos = comm_overall, comm_pos
        u_rank  = user_overall.get(pid)
        o_rank  = o_overall.get(pid)
        u_prank = user_pos.get(pid)
        o_prank = o_pos.get(pid)
        buys.append(_enrich(pid, {
            "player_id":       pid,
            "user_elo":        round(u, 1),
            "owner_elo":       round(o, 1),
            "owner_user_id":   owner_uid,
            "owner_username":  owner_uname,
            "gap":             round(gap, 1),
            "score":           _normalise_gap(gap),
            # Rank view: positive rank_gap = you rank them nearer #1 than owner.
            "user_rank":          u_rank,
            "comparison_rank":    o_rank,
            "rank_gap":           _rank_delta(o_rank, u_rank),
            "user_pos_rank":      u_prank,
            "comparison_pos_rank": o_prank,
            "pos_rank_gap":       _rank_delta(o_prank, u_prank),
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
# 2b. Tile trade meters — Tradeability / Acquirability (TestFlight #71)
# ---------------------------------------------------------------------------
#
# Per-player 0-1 score for the horizontal meter on each Tiers tile, derived
# from EXACTLY the same gaps compute_consensus_gap surfaces on Trends:
#
#   • Owned player (on the user's roster in the selected league):
#       TRADEABILITY — gap = user_elo - community_mean_elo.  Positive gap
#       means you value them above the market → easy/profitable to trade
#       away; negative means the market values them more than you do.
#   • Unowned player rostered by a leaguemate:
#       ACQUIRABILITY — gap = user_elo - owner_elo (that owner's own board;
#       falls back to the community mean when the owner hasn't published
#       rankings, mirroring the "easiest buys" fallback).
#
# Scaling: score = clamp01(0.5 + gap / (2 × 400)).  400 ELO points is the
# same span _normalise_gap calibrates the Trends bars to, so gap +400 → 1.0,
# gap −400 → 0.0, gap 0 → 0.5 (a half-full, neutral bar).  Because the
# ranking service seeds every pool player from the consensus seed, a player
# the user has never actually ranked carries user_elo ≈ consensus → gap ≈ 0
# → neutral bar.  That is honest: no signal about a player you haven't
# formed an opinion on.
#
# Free agents (rostered by nobody in the league) get NO score — they can't
# be acquired via trade.  Same ≥3-ranker community baseline as the rest of
# this module; below it the function returns {} and clients omit the bars.
# ---------------------------------------------------------------------------

_TILE_SCORE_SPAN = 400.0   # ELO span mapping gap ±400 → score 0/1


def compute_tile_trade_scores(
    user_elo: dict[str, float],
    community_rankings: dict[str, dict],
    user_roster: list[str],
    league_members: list[dict],
) -> dict[str, dict[str, Any]]:
    """
    Args:
        user_elo:           { player_id: elo } — the logged-in user's board.
        community_rankings: { user_id: { username, elo_ratings } }.
        user_roster:        player_ids owned by the logged-in user.
        league_members:     list of { user_id, username, roster } for owner
                            lookup (same shape compute_consensus_gap takes).

    Returns:
        { player_id: { "owned": bool, "score": float 0-1 } }

        Empty dict when the community baseline is too thin (< 3 rankers).
        Players with no comparison basis (owned but absent from the
        community pool; unowned and rostered by nobody) are omitted.
    """
    if len(community_rankings or {}) < _MIN_BASELINE_USERS:
        return {}

    community_elo = _community_mean_elo(community_rankings)

    # Owner index — pid → owner_user_id
    owner_of: dict[str, str] = {}
    for m in (league_members or []):
        for pid in (m.get("roster") or m.get("player_ids") or []):
            owner_of[pid] = m.get("user_id")

    roster_set = set(user_roster or [])

    def _score(gap: float) -> float:
        return round(max(0.0, min(1.0, 0.5 + gap / (2.0 * _TILE_SCORE_SPAN))), 2)

    out: dict[str, dict[str, Any]] = {}
    for pid, u_elo in (user_elo or {}).items():
        try:
            u = float(u_elo)
        except (TypeError, ValueError):
            continue

        if pid in roster_set:
            # TRADEABILITY vs the community mean (the "easiest sells" gap).
            c = community_elo.get(pid)
            if c is None:
                continue
            out[pid] = {"owned": True, "score": _score(u - c)}
        else:
            # ACQUIRABILITY vs the owner's board (the "easiest buys" gap).
            owner_uid = owner_of.get(pid)
            if owner_uid is None:
                continue          # free agent — not acquirable via trade
            owner_data = (community_rankings or {}).get(owner_uid)
            owner_elo = ((owner_data or {}).get("elo_ratings") or {}).get(pid)
            if owner_elo is None:
                owner_elo = community_elo.get(pid)
            if owner_elo is None:
                continue
            try:
                o = float(owner_elo)
            except (TypeError, ValueError):
                continue
            out[pid] = {"owned": False, "score": _score(u - o)}
    return out


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

    # Rank derivation (pure view of the ELOs we already have).
    #   • current  ranks come from the full current_elo pool.
    #   • previous ranks come from a reconstructed prior snapshot: each player's
    #     earliest in-window ELO, falling back to their current ELO when there
    #     is no history for them so the prior ranking stays complete/comparable.
    prev_snapshot: dict[str, float] = {}
    for pid, curr in (current_elo or {}).items():
        try:
            prev_snapshot[pid] = earliest[pid] if pid in earliest else float(curr)
        except (TypeError, ValueError):
            continue

    curr_overall = _rank_map(current_elo)
    prev_overall = _rank_map(prev_snapshot)
    curr_pos     = _pos_rank_map(current_elo, players_by_id)
    prev_pos     = _pos_rank_map(prev_snapshot, players_by_id)

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
        # Previous rank only meaningful when this player had real history;
        # `earliest` membership guarantees that here.
        overall_rank = curr_overall.get(pid)
        pos_rank     = curr_pos.get(pid)
        row = {
            "player_id":        pid,
            "current_elo":      round(c, 1),
            "previous_elo":     round(earliest[pid], 1),
            "delta":            round(delta, 1),
            "overall_rank":       overall_rank,
            "overall_rank_delta": _rank_delta(prev_overall.get(pid), overall_rank),
            "pos_rank":           pos_rank,
            "pos_rank_delta":     _rank_delta(prev_pos.get(pid), pos_rank),
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


# ---------------------------------------------------------------------------
# 4. Consensus positional ranks + 30-day deltas (FB4-61 tile stats)
# ---------------------------------------------------------------------------
#
# The Tiers tile-stat strip shows the same two stats for both sides: rank +
# 30d trend.  The "You" side comes from compute_risers_fallers above (personal
# elo_history).  This is its CONSENSUS twin: rank within position by the
# universal-pool consensus seed Elo, and the 30-day delta of that rank versus
# a dated consensus snapshot (player_value_history baseline).
# ---------------------------------------------------------------------------


def compute_consensus_pos_ranks(
    current_elo: dict[str, float],
    baseline_elo: dict[str, float],
    players_by_id: dict[str, dict] | None,
) -> dict[str, dict[str, int]]:
    """
    Args:
        current_elo:   { player_id: consensus seed elo } — today's pool.
        baseline_elo:  { player_id: consensus_elo } from the oldest in-window
                       snapshot (load_value_snapshot_baseline). Empty dict →
                       no history accrued yet → ranks only, no deltas.
        players_by_id: { player_id: {"position": ...} } enrichment.

    Returns:
        { "pos_rank":       { player_id: int },     # 1-based, per position
          "pos_rank_delta": { player_id: int } }    # prev - curr; + = moved UP

    Mirrors compute_risers_fallers' rank view: the prior ranking is
    reconstructed over the FULL current pool (players missing from the
    baseline fall back to their current elo so prior ranks stay comparable),
    but a delta is only reported for players actually present in the baseline.
    Ties break on player_id via _pos_rank_map for deterministic ranks.
    """
    curr_pos = _pos_rank_map(current_elo, players_by_id)
    if not baseline_elo:
        return {"pos_rank": curr_pos, "pos_rank_delta": {}}

    prev_snapshot: dict[str, float] = {}
    for pid, curr in (current_elo or {}).items():
        try:
            prev_snapshot[pid] = (float(baseline_elo[pid])
                                  if pid in baseline_elo else float(curr))
        except (TypeError, ValueError):
            continue
    prev_pos = _pos_rank_map(prev_snapshot, players_by_id)

    deltas: dict[str, int] = {}
    for pid, curr_rank in curr_pos.items():
        if pid not in baseline_elo:
            continue
        d = _rank_delta(prev_pos.get(pid), curr_rank)
        if d is not None:
            deltas[pid] = d
    return {"pos_rank": curr_pos, "pos_rank_delta": deltas}
