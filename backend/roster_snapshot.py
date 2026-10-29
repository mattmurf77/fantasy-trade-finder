"""Roster fingerprint (``rfp1``) and values snapshot id (``vsn1``): the S0 serve side.

Contract: the roster fingerprint contract v0.4 (FINAL), copied into
``docs/plans/trade-time-to-suggestion/scope-eng-200ms.md`` §6.1 (trades-eng with
platforms-eng; ``vsn1`` is models-eng's). Every function here reads stored rows
only: no network, and no in-process cache of roster data. The process state is
the ``vsn1`` seed memo (keyed on ``(fmt, pool_generation)`` and the seed map's
identity) and a "the state table exists" marker per engine, both under one
module lock.

- ``roster_snapshot(conn, league_id, *, pick_source)``: one snapshot of the
  league's stored rosters, the pick rows the engine prices, and the draft state.
  ``fp`` keys the trade job's freshness and join checks; ``asset_owner`` drives
  the I-1 serve filter; ``status``, ``refreshed_at`` and ``age_s`` drive the
  serve rules (contract §3, §3b). Names, timestamps, SQL ids and values are not
  fingerprint inputs, so a display-name change never moves ``fp``.
- ``values_snapshot_id(conn, fmt, league_id, pool, *, pick_source)``: the
  format's seed Elo and age per player, plus the league's pick ``pool_value``s.
- ``snapshot_ids(...)``: ``(rfp1, vsn1)`` from one read of each input, for the
  freshness and join checks.
- ``on_roster_change(league_id, old_fp, new_fp)``: platforms-eng's refresh
  calls it after committing rows; trades-eng registers its handler from
  server.py.

Picks are exactly the rows the engine prices: ``database.load_draft_picks(
league_id, source=pick_source)``, which applies the contested/orphaned row
filter itself (``database._excluded_pick_ids``). The caller passes
``server._pick_read_source()``, because this module never imports server.
That read uses its own connection, so the inputs aren't one transaction.

Any change to the inputs or the canonical form bumps the prefix (``rfp2``,
``vsn2``): old jobs and pages then miss and rebuild, which is safe.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import weakref
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Mapping

from sqlalchemy import inspect, select

from . import database as _db

log = logging.getLogger(__name__)

RFP_PREFIX = "rfp1:"
VSN_PREFIX = "vsn1:"

# Player ids a roster can carry by accident (G-004): never an asset.
_NOT_PLAYER_IDS = frozenset(("", "None"))


@dataclass(frozen=True)
class RosterSnapshot:
    fp: str                               # "rfp1:" + 32 hex
    asset_owner: Mapping[str, frozenset]  # player_id or pick_id -> owner user_ids
    refreshed_at: str | None              # contract §3: the state row's, or a linked league's newest row
    status: str                           # "missing" | "fresh" | "stale" | "unknown" (contract §3)
    # Additive to contract §3, for the §3b serve rules:
    linked: bool = False                  # ESPN/MFL/Fleaflicker (database.is_linked_platform_league)
    age_s: float | None = None            # seconds since the roster bound's stamp; None = no stamp
    # Why I-1 must not drop cards on this serve, or None. "c_e": the last
    # session write failed (C-e), so the stored rows may be outdated and would
    # cause false drops. A plain `unknown` (no state row) still filters.
    lenient_reason: str | None = None


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _hash32(canonical: str) -> str:
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()[:32]


def _id(value):
    return None if value is None else str(value)


def _player_ids(roster_data) -> list[str]:
    # Malformed JSON reads as an empty roster, as load_league_members does.
    try:
        ids = json.loads(roster_data or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(ids, list):
        return []
    return sorted({str(pid) for pid in ids if pid is not None and str(pid) not in _NOT_PLAYER_IDS})


def _parse_stamp(stamp) -> datetime | None:
    if not stamp:
        return None
    try:
        when = datetime.fromisoformat(str(stamp))
    except ValueError:
        return None
    return when if when.tzinfo is not None else when.replace(tzinfo=timezone.utc)


def _read_members(conn, league_id):
    t = _db.league_members_table
    return conn.execute(select(t.c.user_id, t.c.roster_data, t.c.updated_at)
                        .where(t.c.league_id == league_id)).all()


def _read_picks(conn, league_id, pick_source):
    # The engine's row set and filter. `conn` is unused: load_draft_picks
    # opens its own connection.
    return _db.load_draft_picks(league_id, source=pick_source)


def _read_drafted(conn, league_id) -> bool:
    t = _db.leagues_table
    status = conn.execute(select(t.c.draft_status)
                          .where(t.c.sleeper_league_id == league_id)).scalar()
    # NULL, 'unknown' and 'not_drafted' mean the same for tradability.
    return status == "drafted"


def _roster_fp(members, picks, drafted: bool) -> tuple[str, dict]:
    owners: dict[str, set] = {}
    canon_members = []
    for user_id, roster_data, _updated_at in members:
        uid = str(user_id)
        ids = _player_ids(roster_data)
        canon_members.append([uid, ids])
        for pid in ids:
            # A shared roster (two rows) gives the asset two owners.
            owners.setdefault(pid, set()).add(uid)
    canon_picks = []
    for pick in picks:
        owner = _id(pick.get("owner_user_id"))
        canon_picks.append([str(pick["pick_id"]), pick.get("season"), pick.get("round"),
                            _id(pick.get("original_roster_id")), owner,
                            pick.get("source") or _db.PICK_SOURCE_PLATFORM])
        if owner is not None:
            owners.setdefault(str(pick["pick_id"]), set()).add(owner)
    canonical = _canonical({
        "v": 1,
        "members": sorted(canon_members, key=lambda row: row[0]),
        "picks": sorted(canon_picks, key=lambda row: row[0]),
        "draft": {"drafted": drafted},
    })
    return RFP_PREFIX + _hash32(canonical), {k: frozenset(v) for k, v in owners.items()}


# Engines known to have `league_roster_state`. Positives only: a missing table
# is re-checked on the next read (release-lead's #367 note).
_lock = threading.Lock()
_state_table_seen: "weakref.WeakSet" = weakref.WeakSet()


def _has_state_table(conn) -> bool:
    engine = conn.engine
    with _lock:
        if engine in _state_table_seen:
            return True
    if not inspect(conn).has_table("league_roster_state"):
        return False
    with _lock:
        _state_table_seen.add(engine)
    return True


def _read_state(conn, league_id):
    if not _has_state_table(conn):
        return None
    t = _db.league_roster_state_table
    return conn.execute(select(t.c.refreshed_at, t.c.status, t.c.last_error_code)
                        .where(t.c.league_id == league_id)).first()


def roster_snapshot(conn, league_id: str, *, pick_source: str,
                    import_fresh_s: float = 86400.0, now: datetime | None = None) -> RosterSnapshot:
    """The league's stored rosters, priced pick rows and serve status, read now.

    ``status`` follows contract §3:
      - no ``league_members`` rows: ``missing``;
      - a linked platform: ``fresh`` while its newest row is within
        ``import_fresh_s`` (model_config ``trade_import_roster_fresh_s``), else
        ``stale``, with ``refreshed_at`` = that newest row's ``updated_at``;
      - Sleeper with a ``league_roster_state`` row: that row's status, except a
        failed session write (``write_failed``) reads ``unknown`` with
        ``lenient_reason="c_e"`` (C-e: serve without I-1 drops);
      - Sleeper without a row, or without the table: ``unknown`` (I-1 still
        filters against the stored rows).
    ``age_s`` measures the roster bound (§3b): from ``refreshed_at``, else from
    the newest ``league_members.updated_at``.
    """
    lid = str(league_id)
    members = _read_members(conn, lid)
    fp, owners = _roster_fp(members, _read_picks(conn, lid, pick_source), _read_drafted(conn, lid))
    if not members:
        return RosterSnapshot(fp, owners, None, "missing")
    now = now or datetime.now(timezone.utc)
    stamps = [(when, raw) for when, raw in ((_parse_stamp(m[2]), m[2]) for m in members) if when]
    newest = max(stamps)[1] if stamps else None

    def age(stamp):
        when = _parse_stamp(stamp)
        return None if when is None else max(0.0, (now - when).total_seconds())

    if _db.is_linked_platform_league(lid):
        newest_age = age(newest)
        status = ("fresh" if newest_age is not None and newest_age <= float(import_fresh_s)
                  else "stale")
        return RosterSnapshot(fp, owners, _id(newest), status, linked=True, age_s=newest_age)
    row = _read_state(conn, lid)
    if row is None:
        return RosterSnapshot(fp, owners, None, "unknown", age_s=age(newest))
    refreshed_at, status, error_code = row
    lenient_reason = None
    if status == _db.ROSTER_STATE_STALE and error_code == "write_failed":
        status, lenient_reason = "unknown", "c_e"
    return RosterSnapshot(fp, owners, _id(refreshed_at), status or "unknown",
                          age_s=age(refreshed_at or newest), lenient_reason=lenient_reason)


# fmt -> (pool generation, the seed map it was computed from, canonical seed JSON)
_seed_memo: dict = {}


def _seed_json(fmt: str, pool: Mapping, generation) -> str:
    seed = pool.get("seed") or {}
    with _lock:
        hit = _seed_memo.get(fmt)
    if generation is not None and hit is not None and hit[0] == generation and hit[1] is seed:
        return hit[2]
    ages = {str(p.id): getattr(p, "age", None) for p in pool.get("players") or ()}
    rows = sorted(([str(pid), elo, ages.get(str(pid))] for pid, elo in seed.items()),
                  key=lambda row: row[0])
    out = _canonical(rows)
    if generation is not None and seed:
        with _lock:
            _seed_memo[fmt] = (generation, seed, out)
    return out


def _values_snapshot_id(fmt: str, pool: Mapping, picks, generation) -> str:
    pick_rows = sorted(([str(p["pick_id"]), p.get("pool_value")] for p in picks),
                       key=lambda row: row[0])
    # Byte-identical to _canonical({"v": 1, "fmt": fmt, "seed": [...], "picks": [...]})
    # (sort_keys order: fmt, picks, seed, v), so the memoized seed JSON is reused
    # as-is. test_roster_snapshot pins the equality.
    canonical = ('{"fmt":' + _canonical(fmt) + ',"picks":' + _canonical(pick_rows)
                 + ',"seed":' + _seed_json(fmt, pool, generation) + ',"v":1}')
    return VSN_PREFIX + _hash32(canonical)


def values_snapshot_id(conn, fmt: str, league_id: str, pool: Mapping, *,
                       pick_source: str, generation=None) -> str:
    """``vsn1`` for (fmt, league): the pool's seed Elo and age per player, plus
    the ``pool_value`` of the pick rows the engine prices.

    ``pool`` is ``g_universal_by_format[fmt]`` as server.py holds it, read only.
    ``generation`` is ``pool_generation()``; with it, the seed part is memoized.
    """
    return _values_snapshot_id(fmt, pool, _read_picks(conn, str(league_id), pick_source), generation)


def snapshot_ids(conn, fmt: str, league_id: str, pool: Mapping, *,
                 pick_source: str, generation=None, parts: dict | None = None) -> tuple[str, str]:
    """``(rfp1, vsn1)`` from one read of each input: members, picks, draft state.

    ``parts`` (a job's kickoff): filled from the same read with ``picks_key``
    (``picks_key``), and, when it carries ``member_rows``, ``expected_fp``
    (``expected_fp``) (#484 QA P2-1)."""
    lid = str(league_id)
    picks = _read_picks(conn, lid, pick_source)
    drafted = _read_drafted(conn, lid)
    fp, _owners = _roster_fp(_read_members(conn, lid), picks, drafted)
    if parts is not None:
        parts["picks_key"] = picks_key(picks, drafted)
        if parts.get("member_rows"):
            parts["expected_fp"] = _roster_fp(_stored_member_rows(parts["member_rows"]),
                                              picks, drafted)[0]
    return fp, _values_snapshot_id(fmt, pool, picks, generation)


def picks_key(picks, drafted: bool = False) -> str:
    """rfp1's pick and draft-state part: the rfp1 of no members with these pick
    rows and this draft verdict. Two equal keys mean the same picks and draft
    state, as the stamp hashes them (#486 QA P3-5)."""
    return _roster_fp((), picks, drafted)[0]


def _stored_member_rows(member_rows) -> list:
    """``[{user_id, player_ids}]`` (the rows session init writes) as
    ``replace_espn_league_members`` stores them, in ``_read_members``' shape."""
    return [(str(m["user_id"]), json.dumps(m.get("player_ids", [])), None)
            for m in member_rows if m.get("user_id")]


def expected_fp(conn, league_id: str, member_rows, *, pick_source: str) -> str:
    """The rfp1 the league's stored rows will have once ``member_rows`` replace
    its members (``[{user_id, player_ids}]``, the rows session init writes,
    stored as ``replace_espn_league_members`` stores them), with its pick rows
    and draft state as they are now. Equal to a stamp only when that stamp
    hashes exactly these members and these picks (#484 QA P1-1)."""
    lid = str(league_id)
    return _roster_fp(_stored_member_rows(member_rows), _read_picks(conn, lid, pick_source),
                      _read_drafted(conn, lid))[0]


# ── on_roster_change: platforms-eng notifies, trades-eng reacts ───────────────
_roster_change_handlers: list[Callable[[str, str | None, str], None]] = []


def register_roster_change_handler(handler: Callable[[str, str | None, str], None]) -> None:
    with _lock:
        if handler not in _roster_change_handlers:
            _roster_change_handlers.append(handler)


def on_roster_change(league_id: str, old_fp: str | None, new_fp: str) -> None:
    """Tell trades-eng a league's stored rosters moved (contract §4.3).

    Call contract (A3):
      - Call it after the refreshed rows are committed, and after the
        compare-and-set on ``league_roster_state.roster_fp`` succeeds.
      - Call it from the session-init daemon thread, never the request thread.
      - The caller holds no app locks and no open DB transaction.
      - ``old_fp`` is None on a league's first stamp. Equal fps are a no-op.
      - A double call (two concurrent inits) is safe: handlers debounce.
    Handlers must never raise; each is also caught and logged here, so one
    failure never blocks the others or the caller's refresh.
    """
    if old_fp == new_fp:
        return
    with _lock:
        handlers = list(_roster_change_handlers)
    for handler in handlers:
        try:
            handler(league_id, old_fp, new_fp)
        except Exception:
            log.exception("on_roster_change handler %r failed for league %s",
                          handler, league_id)
