"""Roster fingerprint (``rfp1``) and values snapshot id (``vsn1``): the S0 serve side.

Contract: ``docs/plans/trade-time-to-suggestion/scope-eng-200ms.md`` §6.1
(trades-eng with platforms-eng; ``vsn1`` as finalized by models-eng). Every
function here reads stored rows only: no network, and no in-process cache of
roster data. The one memo is the ``vsn1`` seed part, keyed on
``(fmt, pool_generation)`` and guarded by the seed map's identity.

- ``roster_snapshot(conn, league_id)``: one snapshot of the league's stored
  ``league_members`` rosters and ``draft_picks`` ownership. ``fp`` keys the
  trade job's freshness and join checks; ``asset_owner`` drives the I-1 serve
  filter. Names, timestamps, SQL ids and values are excluded, so a display-name
  change never moves ``fp``.
- ``values_snapshot_id(conn, fmt, league_id, pool)``: the format's seed Elo and
  age per player, plus this league's pick ``pool_value``s.
- ``snapshot_ids(...)``: both from one read of each table (two indexed reads
  plus the hashes), for the serve path.
- ``on_roster_change(league_id, old_fp, new_fp)``: platforms-eng's refresh calls
  it after committing rows; trades-eng registers its handler from server.py.

Not settled yet, so marked in code:
- EXTENSION POINT ``draft``: the ``leagues`` draft-state columns platforms-eng is
  still naming. Until then the canonical form carries an empty dict.
- ``refreshed_at`` / ``status``: platforms-eng's ``league_roster_state`` table is
  not granted yet. It is read only if it exists (checked once per engine);
  otherwise ``refreshed_at=None`` and ``status="unknown"``. A league with no
  stored ``league_members`` rows has ``status="missing"``.

Any change to the inputs or the canonical form bumps the prefix (``rfp2``,
``vsn2``): old jobs and pages then miss and rebuild, which is safe.
"""
from __future__ import annotations

import hashlib
import json
import logging
import weakref
from dataclasses import dataclass
from typing import Callable, Mapping

from sqlalchemy import inspect, select, text

from .database import draft_picks_table, league_members_table

log = logging.getLogger(__name__)

RFP_PREFIX = "rfp1:"
VSN_PREFIX = "vsn1:"


@dataclass(frozen=True)
class RosterSnapshot:
    fp: str                               # "rfp1:" + 32 hex
    asset_owner: Mapping[str, frozenset]  # player_id or pick_id -> owner user_ids
    refreshed_at: str | None              # platforms-eng's refresh record, when it exists
    status: str                           # "missing" | the refresh record's status | "unknown"


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _hash32(canonical: str) -> str:
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()[:32]


def _id(value):
    return None if value is None else str(value)


def _read_members(conn, league_id):
    t = league_members_table
    return conn.execute(select(t.c.user_id, t.c.roster_data)
                        .where(t.c.league_id == league_id)).all()


def _read_picks(conn, league_id):
    t = draft_picks_table
    return conn.execute(select(t.c.pick_id, t.c.season, t.c.round, t.c.original_roster_id,
                               t.c.owner_user_id, t.c.pool_value)
                        .where(t.c.league_id == league_id)).all()


def _player_ids(roster_data) -> list[str]:
    # Malformed JSON reads as an empty roster, as load_league_members does.
    try:
        ids = json.loads(roster_data or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(ids, list):
        return []
    return sorted({str(pid) for pid in ids if pid is not None})


# league_roster_state existence, per engine, checked once.
_roster_state_exists: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def _refresh_state(conn, league_id):
    engine = conn.engine
    exists = _roster_state_exists.get(engine)
    if exists is None:
        exists = _roster_state_exists[engine] = inspect(conn).has_table("league_roster_state")
    if not exists:
        return None, "unknown"
    # Column names per contract §4 (league_id, refreshed_at, status). The table
    # is platforms-eng's and not granted yet; revisit when it lands.
    row = conn.execute(text("SELECT refreshed_at, status FROM league_roster_state "
                            "WHERE league_id = :league_id"), {"league_id": league_id}).first()
    if row is None:
        return None, "unknown"
    return _id(row[0]), row[1] or "unknown"


def _roster_snapshot_from_rows(conn, league_id, members, picks) -> RosterSnapshot:
    owners: dict[str, set] = {}
    canon_members = []
    for user_id, roster_data in members:
        uid = str(user_id)
        ids = _player_ids(roster_data)
        canon_members.append([uid, ids])
        for pid in ids:
            # A shared roster (co-owners on two rows) gives the asset two owners.
            owners.setdefault(pid, set()).add(uid)
    canon_picks = []
    for pick_id, season, rnd, original_roster_id, owner_user_id, _pool_value in picks:
        canon_picks.append([str(pick_id), season, rnd, _id(original_roster_id), _id(owner_user_id)])
        if owner_user_id is not None:
            owners.setdefault(str(pick_id), set()).add(str(owner_user_id))
    canonical = _canonical({
        "v": 1,
        "members": sorted(canon_members, key=lambda row: row[0]),
        "picks": sorted(canon_picks, key=lambda row: row[0]),
        # EXTENSION POINT: platforms-eng names the `leagues` draft-state columns
        # that decide pick tradability (contract §2, open item FP). Until then
        # this stays empty; adding them is an rfp2 bump.
        "draft": {},
    })
    refreshed_at, status = _refresh_state(conn, league_id)
    if not members:
        status = "missing"
    return RosterSnapshot(fp=RFP_PREFIX + _hash32(canonical),
                          asset_owner={k: frozenset(v) for k, v in owners.items()},
                          refreshed_at=refreshed_at, status=status)


def roster_snapshot(conn, league_id: str) -> RosterSnapshot:
    """The league's stored rosters and pick ownership, read now."""
    return _roster_snapshot_from_rows(conn, league_id, _read_members(conn, league_id),
                                      _read_picks(conn, league_id))


# fmt -> (pool generation, the seed map it was computed from, canonical seed JSON)
_seed_memo: dict = {}


def _seed_json(fmt: str, pool: Mapping, generation) -> str:
    seed = pool.get("seed") or {}
    hit = _seed_memo.get(fmt)
    if generation is not None and hit is not None and hit[0] == generation and hit[1] is seed:
        return hit[2]
    ages = {str(p.id): getattr(p, "age", None) for p in pool.get("players") or ()}
    rows = sorted(([str(pid), elo, ages.get(str(pid))] for pid, elo in seed.items()),
                  key=lambda row: row[0])
    out = _canonical(rows)
    if generation is not None and seed:
        _seed_memo[fmt] = (generation, seed, out)
    return out


def _values_snapshot_id_from_rows(fmt: str, pool: Mapping, picks, generation) -> str:
    pick_rows = sorted(([str(row[0]), row[5]] for row in picks), key=lambda row: row[0])
    # Byte-identical to _canonical({"v": 1, "fmt": fmt, "seed": [...], "picks": [...]})
    # (sort_keys order: fmt, picks, seed, v), so the memoized seed JSON is reused
    # as-is. test_roster_snapshot pins the equality.
    canonical = ('{"fmt":' + _canonical(fmt) + ',"picks":' + _canonical(pick_rows)
                 + ',"seed":' + _seed_json(fmt, pool, generation) + ',"v":1}')
    return VSN_PREFIX + _hash32(canonical)


def values_snapshot_id(conn, fmt: str, league_id: str, pool: Mapping, *,
                       generation=None) -> str:
    """``vsn1`` for (fmt, league): the pool's seed Elo and age per player, plus
    this league's ``draft_picks`` pool values.

    ``pool`` is ``g_universal_by_format[fmt]`` as server.py holds it, read only.
    ``generation`` is ``pool_generation()``; with it, the seed part is memoized.
    """
    return _values_snapshot_id_from_rows(fmt, pool, _read_picks(conn, league_id), generation)


def snapshot_ids(conn, fmt: str, league_id: str, pool: Mapping, *,
                 generation=None) -> tuple[RosterSnapshot, str]:
    """``(roster_snapshot, values_snapshot_id)`` from one read of each table."""
    picks = _read_picks(conn, league_id)
    snap = _roster_snapshot_from_rows(conn, league_id, _read_members(conn, league_id), picks)
    return snap, _values_snapshot_id_from_rows(fmt, pool, picks, generation)


# ── on_roster_change: platforms-eng notifies, trades-eng reacts ───────────────
_roster_change_handlers: list[Callable[[str, str | None, str], None]] = []


def register_roster_change_handler(handler: Callable[[str, str | None, str], None]) -> None:
    if handler not in _roster_change_handlers:
        _roster_change_handlers.append(handler)


def on_roster_change(league_id: str, old_fp: str | None, new_fp: str) -> None:
    """Call after committing refreshed rows, with the fp before and after.

    Handlers run in registration order. A failing handler is logged and never
    blocks the others or the caller's refresh.
    """
    if old_fp == new_fp:
        return
    for handler in list(_roster_change_handlers):
        try:
            handler(league_id, old_fp, new_fp)
        except Exception:
            log.exception("on_roster_change handler %r failed for league %s",
                          handler, league_id)
