"""Value-core eval bench: freeze bench leagues, run engine variants, score five guardrails.

Implements docs/plans/value-core-engine/lld.md section 8.1-8.2. Operator tooling:
unflagged, no app wiring.

* ``freeze`` is the only production touch. It reads Postgres through
  ``prod_analytics._connect_readonly`` and asserts ``transaction_read_only = on``
  before any read, plus Sleeper's public league API. It writes ONE private file
  (0600, ``O_EXCL``: never overwrites). Its return value and stdout carry
  aggregate counts only, never a user id.
* ``run`` replays every seat of every frozen league through the engine
  (``pipeline.run`` unless a stub is injected), scores the guardrails on the
  first ``TOP_WINDOW`` cards and returns pooled results plus blind-grade card
  sets. The CLI writes them into a fresh 0700 directory as 0600 files.

The engine modules (``pipeline``, ``windows``, ``adapter``) are imported lazily
inside functions, so this file imports with only the shared contract present
(specs.md section 4).
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import math
import os
import random
import re
import statistics
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Mapping, Sequence

from backend.value_core.types import (
    CORE_POSITIONS, DEFAULT_WINDOW, TOP_WINDOW, Asset, Board, CoreConfig, DeckEntry,
    LeagueSnapshot, PipelineResult, RankConfig, Request, RosterRules, Standing, Team,
)

SCHEMA = "value-core-bench-1"
TARGETS = {"insult_loss": 0.20, "insult_rate_max": 0.03, "real_piece_min": 0.70,
           "median_given_min": -0.10, "max_appearances": 3}
DEFAULT_STANDINGS_WEIGHT = 0.30   # the vc_standings_weight default (lld.md section 3)
PICKS_PER_OWNER = 6               # mirrors model_config picks_pool_cap (database.py)
SLEEPER_LEAGUE_URL = "https://api.sleeper.app/v1/league/{}"
_ORDINALS = {1: "1st", 2: "2nd", 3: "3rd"}
_VARIANT_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
_OVERRIDE_KEYS = {"core", "rank", "standings_weight"}

Engine = Callable[[LeagueSnapshot, Request, CoreConfig, RankConfig], PipelineResult]


# ---------------------------------------------------------------------------
# Private output files
# ---------------------------------------------------------------------------

def write_private_text(path: Path, text: str) -> None:
    """Create `path` with mode 0600. Refuses an existing path (O_EXCL)."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(text)


def write_private_json(path: Path, value) -> None:
    write_private_text(path, json.dumps(value, sort_keys=True, indent=1, allow_nan=False))


def fresh_dir(path: Path) -> None:
    """Create a new 0700 output directory; FileExistsError when it already exists."""
    os.makedirs(path, mode=0o700)


def parse_variants(specs: Sequence[str]) -> dict[str, dict]:
    """`["NAME=overrides.json", ...]` -> {name: overrides}; none -> {"default": {}}."""
    variants: dict[str, dict] = {}
    for spec in specs:
        name, sep, path = spec.partition("=")
        if not sep or not _VARIANT_NAME.match(name) or name in variants:
            raise ValueError(f"bad --variant {spec!r}: want a unique NAME=overrides.json")
        variants[name] = json.loads(Path(path).read_text())
    return variants or {"default": {}}


# ---------------------------------------------------------------------------
# Freeze
# ---------------------------------------------------------------------------

def assert_read_only(connection) -> None:
    """Raise ValueError unless the session reports `transaction_read_only = on`."""
    from sqlalchemy import text
    if connection.execute(text("SHOW transaction_read_only")).scalar() != "on":
        raise ValueError("read-only connection required: transaction_read_only is not on")


def _roster_ids(raw) -> list[str]:
    if isinstance(raw, str):
        raw = json.loads(raw) if raw.strip() else []
    return [str(pid) for pid in (raw or [])]


def _pick_name(season, round_) -> str:
    rnd = int(round_ or 0)
    return f"{season} {_ORDINALS.get(rnd, f'{rnd}th')}"


def league_record(*, league_row: Mapping, members: Sequence[Mapping], picks: Sequence[Mapping],
                  rankings: Sequence[Mapping], players: Mapping[str, Mapping],
                  consensus_elo: Mapping[str, float], declared: Mapping[str, str | None],
                  meta: Mapping | None, state: object | None) -> dict:
    """Pure transform: prod rows in, one frozen league record (lld.md section 8.1) out.

    `meta`/`state` are the Sleeper league meta and outlook LeagueState; both are
    None for a non-Sleeper league (default lineup, no roster cap, no standings).
    """
    from backend.trade_service import elo_to_value, value_to_elo

    fmt = league_row.get("default_scoring") or "1qb_ppr"
    positions = list((meta or {}).get("roster_positions") or [])
    if positions:
        # Mirrors the serving path: lineup = roster_positions filtered to the
        # fillable slots, capacity = slots + IR + taxi.
        from backend.power_rankings import LINEUP_SLOT_ELIGIBILITY
        settings = meta.get("settings") or {}
        lineup_slots = [s for s in positions if s in LINEUP_SLOT_ELIGIBILITY]
        max_players = (len(positions) + int(settings.get("reserve_slots") or 0)
                       + int(settings.get("taxi_slots") or 0))
    else:
        from backend.value_core import adapter
        lineup_slots, max_players = list(adapter.default_lineup_slots(fmt)), None

    team_ids = [str(m["user_id"]) for m in members]
    member_set = set(team_ids)

    # Pick capital share over every platform pick, on the legacy pick_value scale
    # (the same arithmetic the trade job feeds infer_team_outlook).
    totals: dict[str, float] = {}
    grand = 0.0
    for pk in picks:
        pv = float(pk.get("pick_value") or 0.0)
        owner = pk.get("owner_user_id")
        if owner:
            totals[str(owner)] = totals.get(str(owner), 0.0) + pv
        grand += pv

    picks_by_owner: dict[str, list[Mapping]] = {}
    for pk in picks:
        owner = str(pk.get("owner_user_id") or "")
        if owner in member_set:
            picks_by_owner.setdefault(owner, []).append(pk)

    assets: dict[str, dict] = {}
    seed_elo: dict[str, float] = {}
    teams: list[dict] = []
    for m in members:
        tid = str(m["user_id"])
        asset_ids: list[str] = []
        other = 0
        for pid in _roster_ids(m.get("roster_data")):
            if pid in assets:
                continue                   # co-owner / duplicate guard: first owner keeps it
            p = players.get(pid)
            if p is None or p.get("position") not in CORE_POSITIONS:
                other += 1
                continue
            elo = consensus_elo.get(pid)
            assets[pid] = {"kind": "player", "position": p["position"],
                           "name": p.get("full_name") or pid,
                           "age": float(p["age"]) if p.get("age") else None,
                           "market": elo_to_value(float(elo)) if elo is not None else 0.0,
                           "search_rank": p.get("search_rank"), "pick_value": None}
            if elo is not None:
                seed_elo[pid] = float(elo)
            asset_ids.append(pid)
        owned = sorted(picks_by_owner.get(tid, []),
                       key=lambda pk: (-float(pk.get("pool_value") or 0.0), str(pk["pick_id"])))
        for pk in owned[:PICKS_PER_OWNER]:
            pool = float(pk.get("pool_value") or 0.0)
            if pool <= 0:
                continue
            aid = str(pk["pick_id"])
            # pick_value is the inverse of dynasty_value's PICK bridge, as the
            # serving path's pick pseudo-players carry it.
            assets[aid] = {"kind": "pick", "position": "PICK",
                           "name": _pick_name(pk.get("season"), pk.get("round")),
                           "age": None, "market": pool, "search_rank": None,
                           "pick_value": round((value_to_elo(pool) - 1200.0) / 6.0, 3)}
            asset_ids.append(aid)
        teams.append({"team_id": tid,
                      "name": m.get("display_name") or m.get("username") or tid,
                      "asset_ids": asset_ids, "other_players": other,
                      "declared_outlook": declared.get(tid),
                      "pick_share": totals.get(tid, 0.0) / grand if grand > 0 else 0.0})

    boards: dict[str, dict] = {}
    for r in rankings:
        uid, pid = str(r["user_id"]), str(r["player_id"])
        if uid not in member_set or pid not in assets:
            continue
        board = boards.setdefault(uid, {"elo": {}, "comparisons": {}})
        board["elo"][pid] = float(r["elo"])
        if r.get("comparison_count") is not None:
            board["comparisons"][pid] = int(r["comparison_count"])

    standings: dict[str, dict] = {}
    for t in (getattr(state, "teams", None) or []):
        uid = str(getattr(t, "user_id", "") or "")
        if uid in member_set:
            standings[uid] = {"wins": int(t.wins), "losses": int(t.losses),
                              "ties": int(t.ties), "points_for": float(t.points_for)}

    return {"league_id": str(league_row["sleeper_league_id"]),
            "name": league_row.get("name") or str(league_row["sleeper_league_id"]),
            "platform": league_row.get("platform") or "sleeper",
            "scoring_format": fmt, "lineup_slots": lineup_slots, "max_players": max_players,
            "completed_weeks": int(getattr(state, "completed_weeks", 0) or 0),
            "standings": standings, "assets": assets, "teams": teams, "boards": boards,
            "seed_elo": seed_elo}


def _fetch_json(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": "FantasyTradeFinder/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read())


def read_league_inputs(conn, league_id: str, today: date) -> dict:
    """The DB half of a freeze: dialect-neutral reads on ANY SQLAlchemy connection — the app's
    own engine or the read-only prod one. No network, no prod tooling, no writes.
    Returns league_record's keyword arguments minus meta/state:
    {"league_row", "members", "picks", "rankings", "players", "consensus_elo", "declared"}.
    Raises ValueError when the league has no `leagues` row or no `league_members` rows."""
    from sqlalchemy import bindparam, text

    def rows(sql: str, **params) -> list[dict]:
        return [dict(r) for r in conn.execute(text(sql), params).mappings()]

    found = rows("SELECT sleeper_league_id, name, platform, default_scoring FROM leagues "
                 "WHERE sleeper_league_id = :lid", lid=league_id)
    if not found:
        raise ValueError(f"league {league_id} is not in the leagues table")
    league_row = found[0]
    fmt = league_row.get("default_scoring") or "1qb_ppr"
    members = rows("SELECT user_id, username, display_name, roster_data FROM league_members "
                   "WHERE league_id = :lid ORDER BY user_id", lid=league_id)
    if not members:
        raise ValueError(f"league {league_id} has no league_members rows; it cannot be benched")
    # Platform rows have `source` NULL (sync_draft_picks never sets it; database.py's
    # _pick_source_predicate reads NULL as platform). is_traded / original_username feed the
    # blind-grading neutral pick label (docs/plans/blind-grading/lld.md §6.2).
    picks = rows("SELECT pick_id, season, round, owner_user_id, pick_value, pool_value, "
                 "is_traded, original_username "
                 "FROM draft_picks WHERE league_id = :lid "
                 "AND (source IS NULL OR source = 'platform') "
                 "ORDER BY pick_id", lid=league_id)
    rankings = rows("SELECT user_id, player_id, elo, comparison_count FROM member_rankings "
                    "WHERE league_id = :lid AND COALESCE(scoring_format, '1qb_ppr') = :fmt "
                    "ORDER BY user_id, player_id", lid=league_id, fmt=fmt)
    declared = {str(r["user_id"]): r["team_outlook"]
                for r in rows("SELECT user_id, team_outlook FROM league_preferences "
                              "WHERE league_id = :lid ORDER BY user_id, id", lid=league_id)}
    ids = sorted({pid for m in members for pid in _roster_ids(m.get("roster_data"))})
    players: dict[str, dict] = {}
    consensus: dict[str, float] = {}
    if ids:
        players_sql = text("SELECT player_id, full_name, position, team, age, search_rank "
                           "FROM players WHERE player_id IN :ids"
                           ).bindparams(bindparam("ids", expanding=True))
        players = {str(r["player_id"]): dict(r)
                   for r in conn.execute(players_sql, {"ids": ids}).mappings()}
        history_sql = text(
            "SELECT player_id, consensus_elo FROM player_value_history "
            "WHERE scoring_format = :fmt AND player_id IN :ids AND snapshot_date = "
            "(SELECT MAX(snapshot_date) FROM player_value_history "
            " WHERE scoring_format = :fmt AND snapshot_date <= :today)"
        ).bindparams(bindparam("ids", expanding=True))
        consensus = {str(r["player_id"]): float(r["consensus_elo"])
                     for r in conn.execute(history_sql, {"fmt": fmt, "ids": ids,
                                                         "today": today.isoformat()}).mappings()}
    return {"league_row": league_row, "members": members, "picks": picks, "rankings": rankings,
            "players": players, "consensus_elo": consensus, "declared": declared}


def _freeze_league(conn, league_id: str, today: date, fetch_json) -> dict:
    inputs = read_league_inputs(conn, league_id, today)
    meta = state = None
    if (inputs["league_row"].get("platform") or "sleeper") == "sleeper":
        from backend.outlook.league_state import SleeperLeagueState
        meta = fetch_json(SLEEPER_LEAGUE_URL.format(league_id))
        state = SleeperLeagueState(fetch=fetch_json).load(league_id)
    return league_record(**inputs, meta=meta, state=state)


def freeze(*, secrets: Path, league_ids: Sequence[str], output: Path, today: date | None = None,
           fetch_json: Callable[[str], object] | None = None) -> dict:
    """Write ONE private frozen file (O_CREAT|O_EXCL, mode 0600) holding every requested
    league. Returns an aggregate summary with no user ids."""
    from backend.tools import prod_analytics

    output = Path(output)
    if output.exists():
        raise FileExistsError(f"{output} already exists; freeze never overwrites")
    today = today or date.today()
    prod_analytics.SECRETS = Path(secrets)
    engine = prod_analytics._connect_readonly(prod_analytics._load_prod_url(), 15000)
    records: list[dict] = []
    try:
        with engine.connect() as conn:
            assert_read_only(conn)
            for league_id in league_ids:
                records.append(_freeze_league(conn, str(league_id), today,
                                              fetch_json or _fetch_json))
    finally:
        engine.dispose()
    write_private_json(output, {"schema": SCHEMA, "frozen_on": today.isoformat(),
                                "leagues": records})
    return {"leagues": len(records),
            "teams": sum(len(r["teams"]) for r in records),
            "assets": sum(len(r["assets"]) for r in records),
            "boards": sum(len(r["boards"]) for r in records),
            "standings_leagues": sum(1 for r in records if r["standings"])}


def synthetic_league(seed: int = 7, n_teams: int = 12, scoring_format: str = "1qb_ppr") -> dict:
    """A frozen-format bench file holding one synthetic league (for tests and the smoke run).

    22 core players and 4 picks per team, ln-normal markets (median 1200, sigma 1.0)
    clamped to [100, 9500], ages 21-33, two boards and PF standings at week 4.
    """
    from backend.trade_service import value_to_elo

    rng = random.Random(seed)

    def market() -> float:
        return round(min(9500.0, max(100.0, math.exp(rng.gauss(math.log(1200.0), 1.0)))), 1)

    positions = ("QB",) * 3 + ("RB",) * 7 + ("WR",) * 8 + ("TE",) * 4
    assets: dict[str, dict] = {}
    seed_elo: dict[str, float] = {}
    teams: list[dict] = []
    standings: dict[str, dict] = {}
    for t in range(n_teams):
        tid = f"team{t:02d}"
        ids = []
        for k, pos in enumerate(positions):
            aid = f"{tid}_{pos.lower()}{k:02d}"
            value = market()
            assets[aid] = {"kind": "player", "position": pos, "name": f"{pos} {t:02d}-{k:02d}",
                           "age": round(rng.uniform(21.0, 33.0), 1), "market": value,
                           "search_rank": None, "pick_value": None}
            seed_elo[aid] = round(value_to_elo(value), 4)
            ids.append(aid)
        for rnd in range(1, 5):
            aid = f"{tid}_2027_{rnd}"
            value = market()
            assets[aid] = {"kind": "pick", "position": "PICK",
                           "name": f"{_pick_name(2027, rnd)} (Team {t:02d})", "age": None,
                           "market": value, "search_rank": None,
                           "pick_value": round((value_to_elo(value) - 1200.0) / 6.0, 3)}
            ids.append(aid)
        wins = rng.randint(0, 4)
        standings[tid] = {"wins": wins, "losses": 4 - wins, "ties": 0,
                          "points_for": round(rng.gauss(480.0, 60.0), 1)}
        teams.append({"team_id": tid, "name": f"Team {t:02d}", "asset_ids": ids,
                      "other_players": 2, "declared_outlook": None,
                      "pick_share": round(1.0 / n_teams, 6)})
    by_value = sorted((a for a, v in assets.items() if v["kind"] == "player"),
                      key=lambda a: (-assets[a]["market"], a))
    for rank, aid in enumerate(by_value, 1):
        assets[aid]["search_rank"] = rank
    boards = {}
    for team in teams[:2]:
        elo = {a: round(seed_elo[a] + rng.gauss(0.0, 60.0), 2) for a in sorted(seed_elo)}
        boards[team["team_id"]] = {"elo": elo,
                                   "comparisons": {a: rng.randint(0, 12) for a in sorted(elo)}}
    slots = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX"]
    if scoring_format == "sf_tep":
        slots.append("SUPER_FLEX")
    league = {"league_id": f"synthetic-{seed}", "name": f"Synthetic {seed}",
              "platform": "synthetic", "scoring_format": scoring_format,
              "lineup_slots": slots, "max_players": 30, "completed_weeks": 4,
              "standings": standings, "assets": assets, "teams": teams, "boards": boards,
              "seed_elo": seed_elo}
    return {"schema": SCHEMA, "frozen_on": "synthetic", "leagues": [league]}


# ---------------------------------------------------------------------------
# Run and guardrails
# ---------------------------------------------------------------------------

def load_frozen(path: Path) -> dict:
    frozen = json.loads(Path(path).read_text())
    if not isinstance(frozen, dict) or frozen.get("schema") != SCHEMA:
        raise ValueError(f"{path} is not a {SCHEMA} frozen bench file")
    return frozen


def snapshot_for_seat(league: Mapping, seat_team_id: str, *, standings_weight: float
                      ) -> tuple[LeagueSnapshot, Board | None]:
    """Build windows (windows.infer_windows with SimpleNamespace players from assets)
    and the snapshot from frozen data; board = shrink(boards[seat]) via
    trade_service._shrink_user_elo(elo, seed_elo, comparisons, None) -> elo_to_value."""
    from backend.trade_service import _shrink_user_elo, elo_to_value
    from backend.value_core import adapter, windows

    raw_assets = league["assets"]
    players = {aid: SimpleNamespace(id=aid, name=a["name"], position=a["position"],
                                    age=a.get("age"), search_rank=a.get("search_rank"),
                                    pick_value=a.get("pick_value"))
               for aid, a in raw_assets.items()}
    team_windows = windows.infer_windows(
        team_rosters={t["team_id"]: list(t["asset_ids"]) for t in league["teams"]},
        players=players,
        pick_shares={t["team_id"]: float(t.get("pick_share") or 0.0) for t in league["teams"]},
        standings={tid: Standing(int(s["wins"]), int(s["losses"]), int(s["ties"]),
                                 float(s["points_for"]))
                   for tid, s in (league.get("standings") or {}).items()},
        completed_weeks=int(league.get("completed_weeks") or 0),
        declared={t["team_id"]: t.get("declared_outlook") for t in league["teams"]},
        standings_weight=standings_weight)
    fmt = league["scoring_format"]
    first_round_value, elite_value = adapter.tier_values(fmt)
    assets = {aid: Asset(aid, a["kind"], a["position"], a["name"], a.get("age"), float(a["market"]))
              for aid, a in raw_assets.items()}
    teams = {t["team_id"]: Team(t["team_id"], t["name"], tuple(t["asset_ids"]),
                                int(t.get("other_players") or 0),
                                team_windows.get(t["team_id"], DEFAULT_WINDOW))
             for t in league["teams"]}
    # Every other seat's frozen board, shrunk exactly as the server shrinks a partner's.
    partner_boards = {}
    for tid, raw in (league.get("boards") or {}).items():
        if tid == seat_team_id or tid not in teams or not raw.get("elo"):
            continue
        pb = adapter.partner_board_from(
            elo_ratings=raw["elo"], seed_elo=league.get("seed_elo") or {},
            comparison_counts={a: int(n) for a, n in (raw.get("comparisons") or {}).items()},
            confidence_source="votes")
        if pb is not None:
            values = {a: v for a, v in pb.values.items() if a in assets}
            partner_boards[tid] = Board(values, {a: pb.comparisons.get(a, 0) for a in values})
    snapshot = LeagueSnapshot(league["league_id"], fmt, assets, teams,
                              RosterRules(tuple(league["lineup_slots"]), league.get("max_players")),
                              first_round_value, elite_value, partner_boards)

    board = None
    raw_board = (league.get("boards") or {}).get(seat_team_id)
    if raw_board and raw_board.get("elo"):
        comparisons = {a: int(n) for a, n in (raw_board.get("comparisons") or {}).items()}
        shrunk = _shrink_user_elo(dict(raw_board["elo"]), dict(league.get("seed_elo") or {}),
                                  comparisons or None, None)
        values = {a: elo_to_value(shrunk[a]) for a in assets if a in shrunk}
        board = Board(values=values, comparisons={a: comparisons.get(a, 0) for a in values})
    return snapshot, board


def _card_metrics(entries: Sequence[DeckEntry], snapshot: LeagueSnapshot, top: int) -> list[dict]:
    """Per-card guardrail inputs for the first `top` entries."""
    out = []
    for entry in list(entries)[:top]:
        trade = entry.scored.trade
        value = entry.scored.detail["value"]
        give, receive = trade.give_market, trade.receive_market
        out.append({
            "insult": receive > 0 and (receive - give) / receive > TARGETS["insult_loss"],
            "real_piece": bool(value["best_in_starter"])
                          or float(value["best_in_market"]) >= snapshot.first_round_value,
            "given": (receive - give) / give if give > 0 else 0.0,
            "assets": tuple(trade.give) + tuple(trade.receive),
            "partner": trade.partner_team_id,
        })
    return out


def _rates(metrics: Sequence[dict]) -> tuple[float | None, float | None, float | None]:
    if not metrics:
        return None, None, None
    n = len(metrics)
    return (sum(m["insult"] for m in metrics) / n,
            sum(m["real_piece"] for m in metrics) / n,
            statistics.median(m["given"] for m in metrics))


def _passes(insult, real_piece, median_given, appearances, near_duplicates) -> dict:
    return {"insult": insult is not None and insult < TARGETS["insult_rate_max"],
            "real_piece": real_piece is not None and real_piece >= TARGETS["real_piece_min"],
            "median_given": median_given is not None and median_given >= TARGETS["median_given_min"],
            "appearances": appearances <= TARGETS["max_appearances"],
            "near_duplicates": near_duplicates == 0}


def _r4(x: float | None) -> float | None:
    return None if x is None else round(x, 4)


def guardrails(entries: Sequence[DeckEntry], snapshot: LeagueSnapshot, *, top: int = TOP_WINDOW
               ) -> dict:
    """The five guardrails (lld.md section 8.2) on the first `top` entries."""
    from backend.value_core.deck import acquisition_key, idea_key
    metrics = _card_metrics(entries, snapshot, top)
    insult, real_piece, median_given = _rates(metrics)
    counts = Counter(a for m in metrics for a in m["assets"])
    most, appearances = (min(counts.items(), key=lambda kv: (-kv[1], kv[0]))
                         if counts else (None, 0))
    trades = [e.scored.trade for e in list(entries)[:top]]
    ideas = Counter(idea_key(t, snapshot) for t in trades)
    acquisitions = Counter(acquisition_key(t, snapshot) for t in trades)
    per_partner = Counter(t.partner_team_id for t in trades)
    near_duplicates = sum(c - 1 for c in ideas.values())
    acquired = Counter(a for t in trades for a in t.receive)
    most_acquired, acquired_appearances = (min(acquired.items(), key=lambda kv: (-kv[1], kv[0]))
                                           if acquired else (None, 0))
    return {"cards": len(metrics),
            "insult_rate": _r4(insult),
            "real_piece_back_share": _r4(real_piece),
            "median_value_given": _r4(median_given),
            "max_acquired_appearances": acquired_appearances,
            "most_acquired_asset": most_acquired,
            "max_asset_appearances": appearances,          # both sides; reported, not a guardrail
            "most_repeated_asset": most,
            "partners": len({m["partner"] for m in metrics}),
            "max_partner_cards": max(per_partner.values(), default=0),
            "near_duplicates": near_duplicates,
            "acquisition_repeats": sum(c - 1 for c in acquisitions.values()),
            "pass": _passes(insult, real_piece, median_given, acquired_appearances, near_duplicates)}


def _card(entry: DeckEntry, snapshot: LeagueSnapshot, league_name: str, seat: str) -> dict:
    """One blind-grade card (blind_grade CardSet format, lld.md section 8.4)."""
    def side(ids):
        return [{"id": a, "name": snapshot.assets[a].name,
                 "position": snapshot.assets[a].position,
                 "market": round(snapshot.assets[a].market, 1)} for a in ids]
    trade = entry.scored.trade
    return {"league": league_name, "seat": seat, "partner": trade.partner_team_id,
            "give": side(trade.give), "receive": side(trade.receive),
            "reasons": list(entry.reasons)}


def run(frozen: Mapping, *, variants: Mapping[str, Mapping], seats: str = "all",
        engine: Engine | None = None) -> dict:
    """Every variant x league x seat through the engine. Returns
    {"schema", "seats", "variants": {name: pooled + per-seat}, "card_sets": {name: CardSet}}."""
    if seats not in ("all", "boarded"):
        raise ValueError(f"seats must be 'all' or 'boarded', not {seats!r}")
    if engine is None:
        from backend.value_core import pipeline
        engine = pipeline.run

    results: dict[str, dict] = {}
    card_sets: dict[str, dict] = {}
    for name, overrides in variants.items():
        overrides = dict(overrides or {})
        unknown = set(overrides) - _OVERRIDE_KEYS
        if unknown:
            raise ValueError(f"variant {name!r}: unknown override keys {sorted(unknown)}")
        core_cfg = dataclasses.replace(CoreConfig(), **(overrides.get("core") or {}))
        rank_cfg = dataclasses.replace(RankConfig(), **(overrides.get("rank") or {}))
        standings_weight = float(overrides.get("standings_weight", DEFAULT_STANDINGS_WEIGHT))

        pooled: list[dict] = []
        seat_rows: list[dict] = []
        cards: list[dict] = []
        for league in frozen["leagues"]:
            boards = league.get("boards") or {}
            for team in league["teams"]:
                seat = team["team_id"]
                if seats == "boarded" and seat not in boards:
                    continue
                snapshot, board = snapshot_for_seat(league, seat,
                                                    standings_weight=standings_weight)
                result = engine(snapshot, Request(viewer_team_id=seat, board=board),
                                core_cfg, rank_cfg)
                pooled.extend(_card_metrics(result.entries, snapshot, TOP_WINDOW))
                seat_rows.append({"league": league["name"], "team": team["name"],
                                  "pool": len(result.entries),
                                  **guardrails(result.entries, snapshot),
                                  "core": dataclasses.asdict(result.core),
                                  "elapsed_ms": result.elapsed_ms})
                cards.extend(_card(e, snapshot, league["name"], seat)
                             for e in result.entries[:TOP_WINDOW])

        insult, real_piece, median_given = _rates(pooled)
        worst = max((s["max_acquired_appearances"] for s in seat_rows if s["cards"]), default=0)
        worst_dups = max((s["near_duplicates"] for s in seat_rows if s["cards"]), default=0)
        worst_acq = max((s["acquisition_repeats"] for s in seat_rows if s["cards"]), default=0)
        passes = _passes(insult, real_piece, median_given, worst, worst_dups)
        results[name] = {"overrides": overrides, "cards": len(pooled),
                         "insult_rate": _r4(insult), "real_piece_back_share": _r4(real_piece),
                         "median_value_given": _r4(median_given),
                         "worst_seat_acquired_appearances": worst, "worst_seat_near_duplicates": worst_dups,
                         "worst_seat_acquisition_repeats": worst_acq, "pass": passes,
                         "verdict": "PASS" if all(passes.values()) else "FAIL",
                         "seats": seat_rows}
        card_sets[name] = {"variant": name, "source": "value_core_bench", "cards": cards}
    return {"schema": SCHEMA, "seats": seats, "variants": results, "card_sets": card_sets}


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def markdown_table(results: Mapping) -> str:
    lines = ["| variant | cards | insult rate | real-piece share | median value given "
             "| worst-seat acquired-asset appearances | worst-seat near-duplicates "
             "| worst-seat repeat acquisitions "
             "| verdict |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---|"]
    for name, v in results["variants"].items():
        lines.append(f"| {name} | {v['cards']} | {_pct(v['insult_rate'])} "
                     f"| {_pct(v['real_piece_back_share'])} | {_pct(v['median_value_given'])} "
                     f"| {v['worst_seat_acquired_appearances']} | {v['worst_seat_near_duplicates']} "
                     f"| {v['worst_seat_acquisition_repeats']} | {v['verdict']} |")
    lines.append("")
    lines.extend(f"verdict {name}: {v['verdict']}" for name, v in results["variants"].items())
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.eval.value_core_bench",
                                     description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p_freeze = sub.add_parser("freeze", help="read bench leagues from prod (read-only)")
    p_freeze.add_argument("--secrets", type=Path, required=True)
    p_freeze.add_argument("--league", action="append", required=True)
    p_freeze.add_argument("--output", type=Path, required=True)
    p_run = sub.add_parser("run", help="run variants over a frozen file")
    p_run.add_argument("--frozen", type=Path, required=True)
    p_run.add_argument("--output", type=Path, required=True)
    p_run.add_argument("--variant", action="append", default=[])
    p_run.add_argument("--seats", choices=("all", "boarded"), default="all")
    args = parser.parse_args(argv)

    if args.command == "freeze":
        try:
            summary = freeze(secrets=args.secrets, league_ids=args.league, output=args.output)
        except (ValueError, FileExistsError) as exc:
            raise SystemExit(f"freeze failed: {exc}") from None
        except Exception as exc:     # a driver error can echo query parameters: name the type only
            raise SystemExit(f"freeze failed: {type(exc).__name__}") from None
        print(json.dumps(summary, sort_keys=True))
        return 0

    if args.output.exists():
        raise SystemExit(f"{args.output} already exists; run never overwrites")
    results = run(load_frozen(args.frozen), variants=parse_variants(args.variant),
                  seats=args.seats)
    card_sets = results.pop("card_sets")
    fresh_dir(args.output)
    write_private_json(args.output / "results.json", results)
    for name, card_set in card_sets.items():
        write_private_json(args.output / f"cards-{name}.json", card_set)
    print(markdown_table(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
