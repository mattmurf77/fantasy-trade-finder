"""Identity stripping: an allow-list per payload type, keyed hashes for user ids.

Rule: for every Sleeper payload type the crawler reads, ``strip_*`` keeps ONLY
the fields listed here and drops everything else. A value is kept only if it
has the expected shape (an id/enum token, a number, a list of those). Every
Sleeper user id (owner, co-owner, transaction creator, draft ``picked_by``,
draft-order keys, league members) becomes ``KeyRing.user_key(id)`` -- an
HMAC-SHA256 of the id under a secret key -- before it reaches disk. Free text
(league/team/draft names, nicknames, descriptions, notes) is never kept; the
waiver ``metadata.notes`` is reduced to a closed code (``notes_code``).

``harvest`` runs on every raw payload BEFORE stripping and records, in memory
only, the raw user ids and the name values seen, so the end-of-run leak scan
can look for them on disk. Nothing in a ``Collector`` is ever written.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import stat
from collections import Counter
from pathlib import Path

KEY_ENV = "SLEEPER_UNIVERSE_HMAC_KEY"
KEY_FILE = "hmac.key"

# Keys whose VALUES are personal free text. Harvested as leak canaries, and
# their key names must never appear in anything written (leak scan check a).
NAME_KEYS = frozenset({
    "username", "display_name", "team_name", "name", "nickname",
    "description", "avatar", "notes", "league_name", "first_name",
    "last_name", "metadata",
})
# Keys whose string values are Sleeper user ids.
USER_ID_KEYS = frozenset({"user_id", "owner_id", "creator", "picked_by"})
USER_ID_LIST_KEYS = frozenset({"co_owners", "creators"})

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.\-]{0,40}$")


class KeyRing:
    def __init__(self, key: bytes, source: str = "given"):
        if not key or len(key) < 16:
            raise ValueError("HMAC key must be at least 16 bytes")
        self._key = bytes(key)
        self.source = source

    @classmethod
    def load(cls, data_dir: Path, env=None) -> "KeyRing":
        """Env ``SLEEPER_UNIVERSE_HMAC_KEY`` wins; else ``<data_dir>/hmac.key``,
        created on first use with owner-only permissions."""
        env = os.environ if env is None else env
        val = env.get(KEY_ENV)
        if val:
            return cls(val.encode("utf-8"), "env")
        data_dir = Path(data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        path = data_dir / KEY_FILE
        if not path.exists():
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(secrets.token_hex(32) + "\n")
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            os.chmod(path, 0o600)
        return cls(path.read_bytes().strip(), "file")

    def user_key(self, user_id) -> str | None:
        if user_id is None:
            return None
        s = str(user_id).strip()
        if not s or s == "0":
            return None
        return hmac.new(self._key, b"user:" + s.encode("utf-8"),
                        hashlib.sha256).hexdigest()[:32]

    def fingerprint(self) -> str:
        """Identifies the key without revealing it (stored in meta so a pull
        with a different key is refused: it would break linkage)."""
        return hmac.new(self._key, b"fingerprint", hashlib.sha256).hexdigest()[:16]


class Collector:
    """In-memory only. Never written."""

    def __init__(self):
        self.raw_user_ids: set[str] = set()
        self.names: set[str] = set()
        self.user_keys: set[str] = set()
        self.dropped: Counter = Counter()


def harvest(obj, col: Collector | None) -> None:
    if col is None:
        return
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for k, v in cur.items():
                ks = str(k)
                if (ks in NAME_KEYS or ks.startswith("p_nick_")
                        or ks.startswith("team_name")) and isinstance(v, str) and v:
                    col.names.add(v)
                if ks in USER_ID_KEYS and isinstance(v, str) and v.isdigit():
                    col.raw_user_ids.add(v)
                if ks in USER_ID_LIST_KEYS and isinstance(v, list):
                    col.raw_user_ids.update(str(x) for x in v
                                            if isinstance(x, str) and x.isdigit())
                if ks == "draft_order" and isinstance(v, dict):
                    col.raw_user_ids.update(str(x) for x in v if str(x).isdigit())
                stack.append(v)
        elif isinstance(cur, list):
            stack.extend(cur)


# ---------------------------------------------------------------------------
# Value validators
# ---------------------------------------------------------------------------

def _token(v):
    """An id or enum: int, or a short [A-Za-z0-9_.-] string. Else None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str) and _TOKEN_RE.match(v):
        return v
    return None


def _int(v):
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str) and v.lstrip("-").isdigit() and len(v) < 12:
        return int(v)
    return None


def _num(v):
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return v
    return None


def _tokens(v) -> list:
    if not isinstance(v, list):
        return []
    return [t for t in (_token(x) for x in v) if t is not None]


def _ints(v) -> list:
    if not isinstance(v, list):
        return []
    return [i for i in (_int(x) for x in v) if i is not None]


def _numeric_dict(d) -> dict:
    if not isinstance(d, dict):
        return {}
    out = {}
    for k, v in d.items():
        if not (isinstance(k, str) and _TOKEN_RE.match(k)):
            continue
        if v is None or isinstance(v, (bool, int, float)):
            out[k] = v
    return out


def _note_dropped(col, kind, obj, kept):
    if col is not None and isinstance(obj, dict):
        for k in obj:
            if k not in kept:
                col.dropped[f"{kind}.{k}"] += 1


def _ukey(ring: KeyRing, col, uid):
    key = ring.user_key(uid) if isinstance(uid, (str, int)) and not isinstance(uid, bool) else None
    if key and col is not None:
        col.user_keys.add(key)
    return key


# ---------------------------------------------------------------------------
# Allow-lists, one per payload type. Documented field-by-field in
# backend/sleeper_universe/README.md (§ What is stored).
# ---------------------------------------------------------------------------

LEAGUE_FIELDS = ("league_id", "previous_league_id", "season", "season_type",
                 "sport", "status", "total_rosters", "draft_id", "bracket_id",
                 "loser_bracket_id", "roster_positions", "scoring_settings",
                 "settings")


def strip_league(obj, ring: KeyRing, col=None) -> dict | None:
    if not isinstance(obj, dict):
        return None
    _note_dropped(col, "league", obj, LEAGUE_FIELDS)
    out = {k: _token(obj.get(k)) for k in LEAGUE_FIELDS[:10]}
    out["roster_positions"] = _tokens(obj.get("roster_positions"))
    out["scoring_settings"] = _numeric_dict(obj.get("scoring_settings"))
    out["settings"] = _numeric_dict(obj.get("settings"))
    return out


ROSTER_FIELDS = ("roster_id", "league_id", "owner_id", "co_owners", "players",
                 "starters", "reserve", "taxi", "keepers", "settings")


def strip_rosters(rows, ring: KeyRing, col=None) -> list:
    out = []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        _note_dropped(col, "roster", r, ROSTER_FIELDS)
        out.append({
            "roster_id": _int(r.get("roster_id")),
            "league_id": _token(r.get("league_id")),
            "owner_key": _ukey(ring, col, r.get("owner_id")),
            "co_owner_keys": [k for k in (_ukey(ring, col, u) for u in
                                          (r.get("co_owners") or [])) if k],
            "players": _tokens(r.get("players")),
            "starters": _tokens(r.get("starters")),
            "reserve": _tokens(r.get("reserve")),
            "taxi": _tokens(r.get("taxi")),
            "keepers": _tokens(r.get("keepers")),
            "settings": _numeric_dict(r.get("settings")),
        })
    return out


def strip_users(rows, ring: KeyRing, col=None) -> list:
    """``/league/<id>/users`` is never stored raw: only the member's key and
    whether Sleeper marks them as the league's owner (commissioner)."""
    out = []
    for u in rows if isinstance(rows, list) else []:
        if not isinstance(u, dict):
            continue
        _note_dropped(col, "user", u, ("user_id", "is_owner"))
        key = _ukey(ring, col, u.get("user_id"))
        if key:
            out.append({"user_key": key, "is_owner": bool(u.get("is_owner"))})
    return out


NOTE_CODES = (
    ("outbid", lambda s: s.strip() == "This player was claimed by another owner."),
    ("roster_full", lambda s: s.rstrip().endswith("too many players after this transaction.")),
    ("already_played", lambda s: s.rstrip().endswith("already started playing.")),
    ("processed", lambda s: s.strip() == "Your waiver claim was processed successfully!"),
)


def notes_code(metadata) -> str | None:
    """Sleeper's fixed waiver reasons as a closed code; any other text is
    'other'. The text itself is never kept."""
    if not isinstance(metadata, dict):
        return None
    s = metadata.get("notes")
    if not isinstance(s, str) or not s:
        return None
    for code, match in NOTE_CODES:
        if match(s):
            return code
    return "other"


TXN_FIELDS = ("transaction_id", "type", "status", "leg", "roster_ids",
              "consenter_ids", "adds", "drops", "draft_picks", "waiver_budget",
              "settings", "metadata", "created", "status_updated", "creator")


def _player_map(d) -> dict:
    if not isinstance(d, dict):
        return {}
    out = {}
    for k, v in d.items():
        kt, vi = _token(str(k)), _int(v)
        if kt is not None and vi is not None:
            out[str(kt)] = vi
    return out


def strip_transactions(rows, ring: KeyRing, col=None) -> list:
    out = []
    for t in rows if isinstance(rows, list) else []:
        if not isinstance(t, dict):
            continue
        _note_dropped(col, "transaction", t, TXN_FIELDS)
        settings = t.get("settings") if isinstance(t.get("settings"), dict) else {}
        out.append({
            "transaction_id": _token(t.get("transaction_id")),
            "type": _token(t.get("type")),
            "status": _token(t.get("status")),
            "leg": _int(t.get("leg")),
            "roster_ids": _ints(t.get("roster_ids")),
            # Roster ids. An entry that is not a small int is dropped.
            "consenter_ids": [i for i in _ints(t.get("consenter_ids")) if abs(i) < 1000],
            "adds": _player_map(t.get("adds")),
            "drops": _player_map(t.get("drops")),
            "draft_picks": [{
                "season": _token(p.get("season")),
                "round": _int(p.get("round")),
                "roster_id": _int(p.get("roster_id")),
                "previous_owner_id": _int(p.get("previous_owner_id")),
                "owner_id": _int(p.get("owner_id")),
            } for p in (t.get("draft_picks") or []) if isinstance(p, dict)],
            "waiver_budget": [{
                "sender": _int(w.get("sender")),
                "receiver": _int(w.get("receiver")),
                "amount": _num(w.get("amount")),
            } for w in (t.get("waiver_budget") or []) if isinstance(w, dict)],
            "settings": {k: _num(settings.get(k)) for k in ("seq", "waiver_bid")
                         if _num(settings.get(k)) is not None},
            "notes_code": notes_code(t.get("metadata")),
            "created": _num(t.get("created")),
            "status_updated": _num(t.get("status_updated")),
            "creator_key": _ukey(ring, col, t.get("creator")),
        })
    return out


def strip_matchups(rows, ring: KeyRing, col=None) -> list:
    fields = ("roster_id", "matchup_id", "points", "custom_points", "players",
              "starters", "starters_points", "players_points")
    out = []
    for m in rows if isinstance(rows, list) else []:
        if not isinstance(m, dict):
            continue
        _note_dropped(col, "matchup", m, fields)
        pp = m.get("players_points") if isinstance(m.get("players_points"), dict) else {}
        out.append({
            "roster_id": _int(m.get("roster_id")),
            "matchup_id": _int(m.get("matchup_id")),
            "points": _num(m.get("points")),
            "custom_points": _num(m.get("custom_points")),
            "players": _tokens(m.get("players")),
            "starters": _tokens(m.get("starters")),
            "starters_points": [x for x in (_num(v) for v in (m.get("starters_points") or [])) if x is not None],
            "players_points": {str(k): _num(v) for k, v in pp.items()
                               if _token(str(k)) is not None and _num(v) is not None},
        })
    return out


DRAFT_FIELDS = ("draft_id", "league_id", "season", "season_type", "status",
                "type", "start_time", "last_picked", "settings",
                "slot_to_roster_id", "draft_order")


def strip_drafts(rows, ring: KeyRing, col=None) -> list:
    out = []
    for d in rows if isinstance(rows, list) else []:
        if not isinstance(d, dict):
            continue
        _note_dropped(col, "draft", d, DRAFT_FIELDS)
        s2r = d.get("slot_to_roster_id") if isinstance(d.get("slot_to_roster_id"), dict) else {}
        order = d.get("draft_order") if isinstance(d.get("draft_order"), dict) else {}
        out.append({
            "draft_id": _token(d.get("draft_id")),
            "league_id": _token(d.get("league_id")),
            "season": _token(d.get("season")),
            "season_type": _token(d.get("season_type")),
            "status": _token(d.get("status")),
            "type": _token(d.get("type")),
            "start_time": _num(d.get("start_time")),
            "last_picked": _num(d.get("last_picked")),
            "settings": _numeric_dict(d.get("settings")),
            "slot_to_roster_id": {str(k): _int(v) for k, v in s2r.items()
                                  if _int(k) is not None and _int(v) is not None},
            "draft_order": {k: _int(v) for k, v in
                            ((_ukey(ring, col, u), s) for u, s in order.items())
                            if k and _int(v) is not None},
        })
    return out


PICK_FIELDS = ("draft_id", "pick_no", "round", "draft_slot", "roster_id",
               "player_id", "is_keeper", "picked_by", "metadata")


def strip_draft_picks(rows, ring: KeyRing, col=None) -> list:
    out = []
    for p in rows if isinstance(rows, list) else []:
        if not isinstance(p, dict):
            continue
        _note_dropped(col, "draft_pick", p, PICK_FIELDS)
        md = p.get("metadata") if isinstance(p.get("metadata"), dict) else {}
        out.append({
            "draft_id": _token(p.get("draft_id")),
            "pick_no": _int(p.get("pick_no")),
            "round": _int(p.get("round")),
            "draft_slot": _int(p.get("draft_slot")),
            "roster_id": _int(p.get("roster_id")),
            "player_id": _token(p.get("player_id")),
            "is_keeper": bool(p.get("is_keeper")),
            "picked_by_key": _ukey(ring, col, p.get("picked_by")),
            # The only metadata field kept: the drafted player's position.
            "position": _token(md.get("position")),
        })
    return out


def strip_traded_picks(rows, ring: KeyRing, col=None) -> list:
    fields = ("season", "round", "roster_id", "owner_id", "previous_owner_id")
    out = []
    for p in rows if isinstance(rows, list) else []:
        if not isinstance(p, dict):
            continue
        _note_dropped(col, "traded_pick", p, fields)
        out.append({"season": _token(p.get("season")), "round": _int(p.get("round")),
                    "roster_id": _int(p.get("roster_id")),
                    "owner_id": _int(p.get("owner_id")),
                    "previous_owner_id": _int(p.get("previous_owner_id"))})
    return out


def strip_bracket(rows, ring: KeyRing, col=None) -> list:
    fields = ("r", "m", "t1", "t2", "w", "l", "p", "t1_from", "t2_from")
    out = []
    for b in rows if isinstance(rows, list) else []:
        if not isinstance(b, dict):
            continue
        _note_dropped(col, "bracket", b, fields)
        row = {k: _int(b.get(k)) for k in ("r", "m", "t1", "t2", "w", "l", "p")}
        for k in ("t1_from", "t2_from"):
            v = b.get(k)
            row[k] = ({kk: _int(vv) for kk, vv in v.items() if kk in ("w", "l")}
                      if isinstance(v, dict) else None)
        out.append(row)
    return out
