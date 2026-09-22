"""Local read-time safety fence for already-adopted prepared offers.

This is not the admission receipt. Providers are freshly resolved at admission;
reads make no network calls and detect only subsequently observed local changes.
The original artifact/card expiry and a maximum thirty-minute interactive window
still apply. Explicit board/outlook edits need the job epoch fence; ordinary
actions need disposition projection, NOT invalidation of the whole inventory.

Only server code may attach ``_prepared_guard`` to runtime cards. A JSON checksum
is an integrity check, not authentication or permission to accept client guards.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
import json
import math
import os

from sqlalchemy import select

from . import database as db
from .prepared_trade_store import InventoryScope, dependency_hash

VERSION = "prepared-read-guard-1"
MAX_AGE = timedelta(minutes=30)
FIELDS = frozenset({"schema", "scope", "captured_at", "expires_at", "receipt", "sha256"})


def _clock(value=None):
    if value is None:
        value = datetime.now(timezone.utc)
    if type(value) is str:
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("aware clock required")
    return value.astimezone(timezone.utc)


def _scope(value):
    if type(value) is not InventoryScope or value.scoring_format not in {"1qb_ppr", "sf_tep"}:
        raise ValueError("unsupported read scope")
    return value


def _copy(value):
    # dependency_hash validates exact plain JSON, finite floats and depth.
    dependency_hash(value)
    return json.loads(json.dumps(value, allow_nan=False))


def _json(value):
    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                raise ValueError("duplicate saved JSON key")
            result[key] = item
        return result
    return _copy(json.loads(value, object_pairs_hook=pairs)) if value is not None else None


def _enabled(server):
    return (server.is_enabled("trade.prepared_inventory") is True and
            server._trade_service_mod._cfg.get("prepared_trade_inventory_enabled") == 1)


def _records(scope):
    # Include pick ownership/provenance and draft state, but not ephemeral SQL
    # IDs or repeated unchanged sync times. Assignment/voiding times ARE inputs.
    specs = ((db.leagues_table, "sleeper_league_id",
              {"created_at", "updated_at", "draft_status_checked_at"},
              {"roster_data", "opponent_data", "platform_future_picks", "pick_assignment_settings", "draft_slot_order"}),
             (db.league_members_table, "league_id", {"id", "updated_at"}, {"roster_data"}),
             (db.draft_picks_table, "league_id", {"id", "synced_at"}, set()),
             (db.recorded_picks_table, "league_id", {"id"}, set()))
    result = {}
    with db.engine.connect() as conn:
        for table, key, excluded, json_fields in specs:
            columns = [column for column in table.c if column.name not in excluded]
            rows = [{str(k): v for k, v in row.items()} for row in conn.execute(select(*columns).where(
                table.c[key] == scope.league_id)).mappings()]
            for row in rows:
                for name in json_fields:
                    row[name] = _json(row[name])
            result[str(table.name)] = sorted(rows, key=dependency_hash)
    if len(result["leagues"]) != 1 or not any(
            r["user_id"] == scope.league_user_id for r in result["league_members"]):
        raise ValueError("saved league binding unavailable")
    return result


def _receipt(server, scope):
    if not _enabled(server):
        raise ValueError("prepared inventory disabled")
    pool = server.g_universal_by_format.get(scope.scoring_format)
    if type(pool) is not dict or not pool.get("players") or type(pool.get("seed")) is not dict:
        raise ValueError("current player pool unavailable")
    players = pool["players"]
    if type(players) is not list or any(not is_dataclass(p) for p in players):
        raise ValueError("invalid current players")
    identities = [p.id for p in players]
    if (any(type(pid) is not str or not pid or pid not in pool["seed"] for pid in identities)
            or len(set(identities)) != len(identities)):
        raise ValueError("incomplete current market")
    raw = server._sleeper_cache
    if type(raw) is not dict or not raw:
        raise ValueError("current availability cache unavailable")
    age = server._players_cache_age_seconds()
    if age is not None and (type(age) not in (int, float) or not math.isfinite(age) or age < 0):
        raise ValueError("invalid availability age")
    availability = {}
    for pid in identities:
        row = raw.get(pid)
        if row is not None and type(row) is not dict:
            raise ValueError("invalid player availability")
        availability[pid] = {"present": row is not None,
            "fantasy_positions": (row or {}).get("fantasy_positions"),
            "injury_status": (row or {}).get("injury_status")}
    metadata = server._FA_LEAGUE_META_CACHE.get(scope.league_id)
    if (type(metadata) not in (list, tuple) or len(metadata) != 2
            or type(metadata[1]) is not dict):
        raise ValueError("current league metadata unavailable")
    evidence = pool.get("input_evidence")
    by_id = {p.id: p for p in players}
    parts = {"scope": scope.as_dict(),
        "policy": {"schema": VERSION, "deployment": os.getenv("RENDER_GIT_COMMIT", "local"),
                   "arm": server._bakeoff.owner_arm(), "model": server._bakeoff.owner_version()},
        "trade_config": dict(server._trade_service_mod._cfg),
        "ranking_config": dict(server._ranking_service_mod._cfg), "flags": server.flags_dict(),
        "players": [asdict(p) for p in players], "seed": pool["seed"],
        "player_evidence": evidence.capture(by_id).as_dict(by_id) if evidence is not None else None,
        "availability": {"fresh": age is not None and age <= 48 * 3600, "players": availability},
        "league_metadata": metadata[1], "records": _records(scope)}
    return {key: dependency_hash(value) for key, value in parts.items()}


def capture(server, scope: InventoryScope, *, expires_at, now=None) -> dict:
    """Capture local safety after admission; never extend artifact authority.

    Parent must compare guards around publication and attach the same detached
    JSON to job and adopted runtime cards. Missing sources raise ValueError.
    """
    scope, stamp = _scope(scope), _clock(now)
    expiry = min(_clock(expires_at), stamp + MAX_AGE)
    if expiry <= stamp:
        raise ValueError("prepared artifact expired")
    try:
        result = {"schema": VERSION, "scope": scope.as_dict(), "captured_at": stamp.isoformat(),
                  "expires_at": expiry.isoformat(), "receipt": _receipt(server, scope)}
        return _copy({**result, "sha256": dependency_hash(result)})
    except (AttributeError, KeyError, TypeError, OverflowError) as exc:
        raise ValueError("read safety inputs unavailable") from exc


def valid(server, guard: dict, *, scope: InventoryScope | None = None, now=None) -> bool:
    """Fail closed; never refresh, rebuild, defer work, or mutate a stale guard."""
    try:
        if type(guard) is not dict or set(guard) != FIELDS or guard["schema"] != VERSION:
            return False
        value = _copy(guard)
        if dependency_hash({k: v for k, v in value.items() if k != "sha256"}) != value["sha256"]:
            return False
        actual = _scope(InventoryScope(**value["scope"]))
        if scope is not None and _scope(scope) != actual:
            return False
        stamp, captured, expiry = _clock(now), _clock(value["captured_at"]), _clock(value["expires_at"])
        if not captured <= stamp < expiry <= captured + MAX_AGE:
            return False
        return _receipt(server, actual) == value["receipt"]
    except Exception:
        # Database/provider-cache availability errors are a miss, not authority
        # to expose an unverified snapshot. No exception contents are logged.
        return False


def filter_cards(server, cards, *, now=None) -> list:
    """Preserve ordinary cards/order; check each distinct trusted guard once.

    Dict fields cannot opt public/client cards into this authority. The caller
    fences a public job via valid() and filters runtime cards before serializing.
    """
    stamp, checked, kept = _clock(now), {}, []
    for card in cards:
        fields = vars(card) if hasattr(card, "__dict__") else {}
        if "_prepared_guard" not in fields:
            kept.append(card)
            continue
        value = fields["_prepared_guard"]
        try:
            key = dependency_hash(value)
            if key not in checked:
                checked[key] = valid(server, value, now=stamp)
            if (checked[key] and card.proposing_user_id == value["scope"]["user_id"]
                    and card.league_id == value["scope"]["league_id"]
                    and _clock(card.expires_at) > stamp):
                kept.append(card)
        except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
            continue
    return kept
