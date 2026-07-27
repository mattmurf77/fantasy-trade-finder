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

# League Analyzer replication (2026-07-26) — which Sleeper roster_positions
# slots the value pool can fill, and what each accepts. Dedicated core slots
# accept exactly their position; flex slots accept the listed set. Everything
# else (K, DEF, IDP slots, BN, IR, TAXI) is ignored: those players are out of
# the value pool, so they carry no value and never belong in the derived
# starters split.
LINEUP_SLOT_ELIGIBILITY: dict[str, tuple[str, ...]] = {
    "QB":         ("QB",),
    "RB":         ("RB",),
    "WR":         ("WR",),
    "TE":         ("TE",),
    "WRRB_FLEX":  ("RB", "WR"),
    "REC_FLEX":   ("WR", "TE"),
    "FLEX":       ("RB", "WR", "TE"),
    "SUPER_FLEX": ("QB", "RB", "WR", "TE"),
}


def optimal_starters(roster: list[dict], lineup_slots: list[str]) -> list[str]:
    """Derive the VALUE-OPTIMAL starting lineup for one team (2026-07-26).

    Starters/bench are a function of dynasty value only — no per-week lineup
    data is read (real lineup arrays are stale/empty preseason). Fill the
    league's starting-slot template with the team's highest-value eligible
    players: dedicated position slots first (top-N of that position), then
    flex slots narrowest-eligibility-first (WRRB/REC → FLEX → SUPER_FLEX),
    each taking the highest-value remaining eligible player. Greedy over the
    nested eligibility sets; deterministic (value desc, player_id asc tie).

    roster: compute_power_rankings' serialized rows ({player_id, position,
    value, ...}). lineup_slots: the relevant slots (LINEUP_SLOT_ELIGIBILITY
    keys) from the league's roster_positions. Returns starter player ids;
    unfillable slots are simply left empty (never padded).
    """
    by_pos: dict[str, list[dict]] = {}
    for r in roster:
        if r["position"] in CORE_POSITIONS:
            by_pos.setdefault(r["position"], []).append(r)
    for rows in by_pos.values():
        rows.sort(key=lambda r: (-r["value"], r["player_id"]))

    dedicated = [s for s in lineup_slots if s in CORE_POSITIONS]
    flexes = [s for s in lineup_slots
              if s in LINEUP_SLOT_ELIGIBILITY and s not in CORE_POSITIONS]
    flexes.sort(key=lambda s: len(LINEUP_SLOT_ELIGIBILITY[s]))

    starters: list[str] = []
    taken: set[str] = set()
    for slot in dedicated:
        for r in by_pos.get(slot, []):
            if r["player_id"] not in taken:
                taken.add(r["player_id"])
                starters.append(r["player_id"])
                break
    for slot in flexes:
        best = None
        for pos in LINEUP_SLOT_ELIGIBILITY[slot]:
            for r in by_pos.get(pos, []):
                if r["player_id"] in taken:
                    continue
                if best is None or (-r["value"], r["player_id"]) < (-best["value"], best["player_id"]):
                    best = r
                break  # rows are value-sorted — only the top untaken matters
        if best is not None:
            taken.add(best["player_id"])
            starters.append(best["player_id"])
    return starters


def compute_power_rankings(
    members: list[dict],
    seed_elo: dict[str, float],
    players: dict,
    board_elo: dict[str, float] | None = None,
    picks_by_owner: dict[str, list[dict]] | None = None,
    lineup_slots: list[str] | None = None,
) -> list[dict]:
    """
    Rank league teams by summed roster value (players + draft capital).

    members:   [{user_id, username, display_name, player_ids: [pid, ...]}, ...]
               (load_league_members shape; works for ESPN-imported leagues too —
               synthetic `espn:` user ids carry crosswalked Sleeper player ids)
    seed_elo:  {player_id: consensus seed Elo} (universal pool)
    players:   {player_id: Player} metadata for name/position/team/age
    board_elo: {player_id: personal Elo} — basis=personal; None = consensus
    picks_by_owner: {owner_user_id: [{label, value}, ...]} — owned draft picks
               already priced in value space (the route prices them via
               pick_values.pick_pool_value; this module stays DB-free).
               None/missing owner → empty picks group, total unchanged.
    lineup_slots: the league's starting-slot template (relevant
               roster_positions entries — LINEUP_SLOT_ELIGIBILITY keys), or
               None when the template is unknown (non-Sleeper platform, meta
               fetch failed). When given, each team carries `starters`: its
               DERIVED value-optimal lineup ids (optimal_starters — a
               function of the SAME values this call ranks with, so a
               personal-basis board reshapes the split too). None → every
               team's `starters` is None and clients hide the filter
               (2026-07-26 League Analyzer replication).

    Returns teams in rank order (total_value desc, user_id asc tiebreak —
    deterministic), each:
      {rank, user_id, username, display_name, total_value, positions_value,
       positions: {QB|RB|WR|TE: {count, value}},
       picks: {count, value, items: [{label, value}, ...]},
       starters: [pid, ...] | None,
       roster: [{player_id, name, position, team, age, value}, ...]}
    where positions_value is the players-only sum, picks.value the draft
    capital sum, and total_value = positions_value + picks.value (FR1) so
    clients can decompose. Roster is grouped by position (QB→RB→WR→TE→other)
    and sorted by value desc within each group (#144). Roster ids with no
    entry in `players` (IDP / team-DST ids outside the pool) are omitted from
    the roster listing (#183) — they hold zero value, so totals don't move.
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
            # #183 — roster ids with no metadata at all (IDP players — LB/DB/
            # DL — and team-DST ids are excluded from the player pool) used to
            # serialize as id-only rows that clients rendered as "Other"
            # entries with a nonsensical id and no name/position. Hide them:
            # they carry no seed and no board entry, so their value is 0.0 by
            # construction and totals are unchanged. Known players with a
            # non-core position (K, DEF with metadata) still serialize.
            if p is None:
                continue
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
        starters = (optimal_starters(roster, lineup_slots)
                    if lineup_slots is not None else None)
        pick_items = [
            {"label": str(i.get("label") or ""),
             "value": round(float(i.get("value") or 0.0), 1)}
            for i in (picks_by_owner or {}).get(user_id) or []
        ]
        picks_value = round(sum(i["value"] for i in pick_items), 1)
        positions_value = round(total, 1)
        teams.append({
            "user_id":         user_id,
            "username":        m.get("username") or "",
            "display_name":    m.get("display_name") or m.get("username") or user_id,
            "total_value":     round(positions_value + picks_value, 1),
            "positions_value": positions_value,
            "positions":       pos_totals,
            "picks":           {"count": len(pick_items),
                                "value": picks_value,
                                "items": pick_items},
            "starters":        starters,
            "roster":          roster,
        })

    teams.sort(key=lambda t: (-t["total_value"], t["user_id"]))
    for i, t in enumerate(teams):
        t["rank"] = i + 1
    return teams
