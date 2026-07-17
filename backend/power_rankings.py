"""
League power rankings (#142/#144) — rank every team in a league by summed
roster value.

Pure computation, no DB access: the route in server.py loads the member
snapshot (league_members), the consensus seed (universal pool), and — for
basis=personal — the caller's live board, then calls compute_power_rankings.
Keeping this free of Flask/DB makes the ranking math directly unit-testable
(backend/tests/test_power_rankings.py).

Value bases:
  - consensus: elo_to_value over the universal-pool seed Elo — the exact
    per-player numbers /api/trade/values serves.
  - personal:  the caller's board Elo where present, consensus seed as the
    fallback for players the caller hasn't ranked.
  - out-of-pool players (no seed, no board entry — K/DEF, deep stashes)
    contribute 0.0: they have no market value in the shared value space, and
    a 1500-Elo default would hand every deep bench ~1000 phantom points.

Redraft basis is deliberately NOT implemented here: DynastyProcess ships
dynasty values only, so the route answers basis=redraft with 501
not_available (see docs/api-reference.md).
"""

from .trade_service import elo_to_value

# Fixed display order for the core fantasy positions; anything else (K, DEF,
# picks) groups after them, alphabetically by position label.
CORE_POSITIONS = ("QB", "RB", "WR", "TE")
_POSITION_ORDER = {pos: i for i, pos in enumerate(CORE_POSITIONS)}


def compute_power_rankings(
    members: list[dict],
    seed_elo: dict[str, float],
    players: dict,
    board_elo: dict[str, float] | None = None,
) -> list[dict]:
    """
    Rank league teams by summed roster value.

    members:   [{user_id, username, display_name, player_ids: [pid, ...]}, ...]
               (load_league_members shape; works for ESPN-imported leagues too —
               synthetic `espn:` user ids carry crosswalked Sleeper player ids)
    seed_elo:  {player_id: consensus seed Elo} (universal pool)
    players:   {player_id: Player} metadata for name/position/team/age
    board_elo: {player_id: personal Elo} — basis=personal; None = consensus

    Returns teams in rank order (total_value desc, user_id asc tiebreak —
    deterministic), each:
      {rank, user_id, username, display_name, total_value,
       positions: {QB|RB|WR|TE: {count, value}},
       roster: [{player_id, name, position, team, age, value}, ...]}
    with roster grouped by position (QB→RB→WR→TE→other) and sorted by value
    desc within each group (#144).
    """

    def value_of(pid: str) -> float:
        if board_elo is not None and pid in board_elo:
            return elo_to_value(board_elo[pid])
        if pid in seed_elo:
            return elo_to_value(seed_elo[pid])
        return 0.0

    teams: list[dict] = []
    for m in members:
        user_id = str(m.get("user_id") or "")
        if not user_id:
            continue
        pos_totals = {pos: {"count": 0, "value": 0.0} for pos in CORE_POSITIONS}
        roster: list[dict] = []
        total = 0.0
        for raw_pid in m.get("player_ids") or []:
            pid = str(raw_pid)
            p = players.get(pid)
            val = round(value_of(pid), 1)
            pos = getattr(p, "position", None) or "?"
            total += val
            if pos in pos_totals:
                pos_totals[pos]["count"] += 1
                pos_totals[pos]["value"] += val
            roster.append({
                "player_id": pid,
                "name":      getattr(p, "name", None) or pid,
                "position":  pos,
                "team":      getattr(p, "team", None),
                "age":       getattr(p, "age", None),
                "value":     val,
            })
        roster.sort(key=lambda r: (
            _POSITION_ORDER.get(r["position"], len(CORE_POSITIONS)),
            r["position"],
            -r["value"],
            r["player_id"],
        ))
        for pos in pos_totals:
            pos_totals[pos]["value"] = round(pos_totals[pos]["value"], 1)
        teams.append({
            "user_id":      user_id,
            "username":     m.get("username") or "",
            "display_name": m.get("display_name") or m.get("username") or user_id,
            "total_value":  round(total, 1),
            "positions":    pos_totals,
            "roster":       roster,
        })

    teams.sort(key=lambda t: (-t["total_value"], t["user_id"]))
    for i, t in enumerate(teams):
        t["rank"] = i + 1
    return teams
