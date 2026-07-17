# ---------------------------------------------------------------------------
# Free-agent finder (feedback #143)
# ---------------------------------------------------------------------------
# Pure logic for GET /api/league/free-agents (route in server.py):
#
#   FA pool        = universal pool minus every rostered player in the league
#                    (all league_members rosters, caller included — works the
#                    same for Sleeper-, ESPN-imported and demo leagues since
#                    the route feeds it whichever roster snapshot it has).
#   Ranking basis  = the CALLER'S board: their personal Elo where they have
#                    one, consensus seed Elo otherwise, mapped through the
#                    same elo_to_value transform every other surface prices
#                    with. A player unranked by the caller is therefore
#                    priced at consensus — never dropped, never zeroed.
#   Drop rule      = for each surfaced FA, suggest the caller's LOWEST-valued
#                    same-position rostered player, and only when that
#                    player's value is strictly BELOW the FA's. No same-
#                    position rostered player below the FA → no suggestion.
#                    delta = fa_value - drop_value (always > 0 when present).
#
# Kept import-light and side-effect free (players in, dicts out) so the
# ranking rules are directly unit-testable without Flask or a DB.
# ---------------------------------------------------------------------------

from __future__ import annotations

from typing import Iterable

from .trade_service import elo_to_value

# Fantasy positions the finder surfaces. PICK pseudo-players (and any other
# non-lineup asset in the universal pool) are never "free agents".
FA_POSITIONS = ("QB", "RB", "WR", "TE")

# Default cap on returned rows (applied AFTER the position filter, so a
# position-filtered call gets a full page of that position).
DEFAULT_LIMIT = 50


def board_value(player_id: str,
                user_elo: dict[str, float],
                seed_elo: dict[str, float]) -> float:
    """The caller's dynasty value for a player: personal Elo when the board
    has one, consensus seed otherwise (1500 floor for a pool player somehow
    absent from both — same default every other pricing path uses)."""
    elo = user_elo.get(player_id)
    if elo is None:
        elo = seed_elo.get(player_id, 1500.0)
    return round(elo_to_value(float(elo)), 1)


def board_is_personalized(user_elo: dict[str, float],
                          seed_elo: dict[str, float],
                          tolerance: float = 1e-6) -> bool:
    """True when the caller's board has diverged from consensus at all —
    any swipe, tier save, anchor or manual reorder moves at least one Elo
    off its seed. A fresh (never-ranked) board is byte-identical to the
    seed and returns False; clients use this for the 'unranked' notice."""
    return any(abs(float(elo) - seed_elo.get(pid, 1500.0)) > tolerance
               for pid, elo in user_elo.items())


def compute_free_agents(pool_players: list,
                        seed_elo: dict[str, float],
                        user_elo: dict[str, float],
                        rostered_ids: Iterable[str],
                        user_roster: Iterable[str],
                        position: str | None = None,
                        limit: int = DEFAULT_LIMIT) -> list[dict]:
    """Rank the league's free agents by the caller's board value.

    pool_players : universal pool for the active format (ranking_service
                   Player dataclasses — id/name/position/team/age used).
    seed_elo     : consensus seed Elo for the same pool.
    user_elo     : caller's personal Elo map (sparse maps fall back to seed
                   per-player; the live route passes the full board).
    rostered_ids : every player id rostered by ANY league member.
    user_roster  : the caller's own roster (also excluded from the FA pool;
                   the drop-suggestion candidates come from here).
    position     : optional 'QB'|'RB'|'WR'|'TE' filter.
    limit        : max rows returned (after the position filter).

    Returns dicts: {player_id, name, position, team, age, value, pos_rank,
    drop_suggestion: {player_id, name, position, value, delta} | None}.
    pos_rank is the FA's 1-based rank within its position across the WHOLE
    FA pool (not the filtered page), so "FA RB3" reads the same under every
    filter.
    """
    user_roster = list(user_roster)
    rostered = set(rostered_ids) | set(user_roster)
    players_by_id = {p.id: p for p in pool_players}

    ranked = sorted(
        ((p, board_value(p.id, user_elo, seed_elo))
         for p in pool_players
         if p.position in FA_POSITIONS and p.id not in rostered),
        key=lambda t: t[1], reverse=True,
    )

    # Positional rank over the full FA pool, before any position filter.
    pos_rank: dict[str, int] = {}
    seen_per_pos: dict[str, int] = {}
    for p, _v in ranked:
        seen_per_pos[p.position] = seen_per_pos.get(p.position, 0) + 1
        pos_rank[p.id] = seen_per_pos[p.position]

    # The caller's lowest-valued rostered player per position — the only
    # ever-suggested drop candidate. Roster entries outside the universal
    # pool (no consensus value on any board) can't be priced and are skipped.
    worst_by_pos: dict[str, tuple] = {}
    for pid in user_roster:
        rp = players_by_id.get(pid)
        if rp is None or rp.position not in FA_POSITIONS:
            continue
        v = board_value(pid, user_elo, seed_elo)
        cur = worst_by_pos.get(rp.position)
        if cur is None or v < cur[1]:
            worst_by_pos[rp.position] = (rp, v)

    if position:
        ranked = [t for t in ranked if t[0].position == position]

    rows = []
    for p, v in ranked[:limit]:
        drop = None
        worst = worst_by_pos.get(p.position)
        if worst is not None and worst[1] < v:
            drop = {
                "player_id": worst[0].id,
                "name":      worst[0].name,
                "position":  worst[0].position,
                "value":     worst[1],
                "delta":     round(v - worst[1], 1),
            }
        rows.append({
            "player_id":       p.id,
            "name":            p.name,
            "position":        p.position,
            "team":            getattr(p, "team", None),
            "age":             getattr(p, "age", None),
            "value":           v,
            "pos_rank":        pos_rank[p.id],
            "drop_suggestion": drop,
        })
    return rows
