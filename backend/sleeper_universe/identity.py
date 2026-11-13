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

MIN_KEY_CHARS = 32
MIN_KEY_DISTINCT = 12


class KeyProblem(SystemExit):
    """A key that must not be used. Exits with the message."""

    def __init__(self, msg):
        super().__init__(f"HMAC key refused: {msg}")


def default_key_path() -> Path:
    return Path.home() / ".config" / "ftf-sleeper-universe" / KEY_FILE


def check_key_text(key: bytes, where: str) -> None:
    """Rule: at least 32 characters and at least 12 distinct characters (a
    generated key, ``secrets.token_hex(32)``, is 64 hex characters). Refuses
    empty, short and obviously low-entropy keys such as 'aaaa...' or '1212...'."""
    if len(key) < MIN_KEY_CHARS:
        raise KeyProblem(f"{where} is shorter than {MIN_KEY_CHARS} characters")
    if len(set(key)) < MIN_KEY_DISTINCT:
        raise KeyProblem(f"{where} has fewer than {MIN_KEY_DISTINCT} distinct characters "
                         "(low entropy); generate one with: python3 -c "
                         "'import secrets; print(secrets.token_hex(32))'")


class KeyRing:
    def __init__(self, key: bytes, source: str = "given"):
        if not key or len(key) < 16:
            raise ValueError("HMAC key must be at least 16 bytes")
        self._key = bytes(key)
        self.source = source
        self._mac = hmac.new(self._key, b"user:", hashlib.sha256)

    @classmethod
    def load(cls, key_path: Path | None = None, env=None, data_dir: Path | None = None
             ) -> "KeyRing":
        """The key: env ``SLEEPER_UNIVERSE_HMAC_KEY``, else the key file
        (default ``~/.config/ftf-sleeper-universe/hmac.key``), created on first
        use (directory 0700, file 0600). Never inside the data folder, so a
        copy of the data does not carry the key. Refuses, rather than fixes:
        a key file readable by group or others; a key file inside the data
        folder (or a legacy ``hmac.key`` left there); an env key set but empty
        or failing ``check_key_text``; an env key and a key file that differ."""
        env = os.environ if env is None else env
        path = Path(key_path) if key_path is not None else default_key_path()
        if data_dir is not None:
            dd = Path(data_dir).resolve()
            if (dd / KEY_FILE).exists():
                raise KeyProblem(f"a key file '{KEY_FILE}' sits in the data folder; move it to "
                                 f"{path} (or set {KEY_ENV}) so copies of the data do not "
                                 "carry the key")
            try:
                path.resolve().relative_to(dd)
                raise KeyProblem("the key file must be outside the data folder")
            except ValueError:
                pass
        file_key = None
        if path.exists():
            mode = stat.S_IMODE(path.stat().st_mode)
            if mode & 0o077:
                raise KeyProblem(f"key file {path} is readable by group or others "
                                 f"(mode {oct(mode)}); run: chmod 600 '{path}'")
            file_key = path.read_bytes().strip()
            check_key_text(file_key, f"key file {path}")
        if KEY_ENV in env:
            val = env[KEY_ENV].strip().encode("utf-8")
            check_key_text(val, f"env {KEY_ENV}")
            if file_key is not None and file_key != val:
                raise KeyProblem(f"env {KEY_ENV} and key file {path} both exist and differ; "
                                 "keep exactly one key")
            return cls(val, "env")
        if file_key is None:
            path.parent.mkdir(parents=True, exist_ok=True)
            os.chmod(path.parent, 0o700)
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(secrets.token_hex(32) + "\n")
            file_key = path.read_bytes().strip()
        return cls(file_key, "file")

    def user_key(self, user_id) -> str | None:
        if user_id is None:
            return None
        s = str(user_id).strip()
        if not s or s == "0":
            return None
        h = self._mac.copy()          # same as hmac.new(key, b"user:" + s)
        h.update(s.encode("utf-8"))
        return h.hexdigest()[:32]

    def fingerprint(self) -> str:
        """Identifies the key without revealing it (stored in meta so a pull
        with a different key is refused: it would break linkage)."""
        return hmac.new(self._key, b"fingerprint", hashlib.sha256).hexdigest()[:16]


class Collector:
    """In-memory only. Never written."""

    def __init__(self):
        self.raw_user_ids: set[str] = set()
        self.names: set[str] = set()
        # name -> {source field, e.g. 'draft.picks.first_name'}: reported with a
        # leak-scan hit instead of the name itself.
        self.name_sources: dict = {}
        self.user_keys: set[str] = set()
        self.dropped: Counter = Counter()


def harvest(obj, col: Collector | None, kind: str = "payload") -> None:
    """``kind``: the endpoint class the payload came from (for name sources)."""
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
                    field = "p_nick_*" if ks.startswith("p_nick_") else ks
                    col.name_sources.setdefault(v, set()).add(f"{kind}.{field}")
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
# Value validators. Every kept value must have the shape of what the field
# holds; anything else becomes None (or is dropped from a list or dict) and is
# counted in ``Collector.dropped``. No validator accepts free text: ids are
# digits of bounded length, enums come from closed vocabularies, settings and
# scoring keys from known lists, numbers are bounded so an 18-digit id cannot
# pass as a setting value.
# ---------------------------------------------------------------------------

_ID_RE = re.compile(r"^\d{1,20}$")              # league / draft / transaction ids
_PLAYER_RE = re.compile(r"^(\d{1,8}|[A-Z]{2,3})$")  # player id, or a team DEF ('TB', 'LAR')
_SEASON_RE = re.compile(r"^(19|20|21)\d\d$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_SMALL = 10_000           # roster ids, weeks, rounds, slots, bracket fields
MAX_SETTING = 1_000_000_000  # settings values (an id is ~1e18)
MAX_POINTS = 1_000_000

LEAGUE_STATUS = frozenset({"pre_draft", "drafting", "in_season", "post_season", "complete"})
SEASON_TYPE = frozenset({"regular", "pre", "post", "off"})
SPORT = frozenset({"nfl"})
TXN_TYPES = frozenset({"trade", "waiver", "free_agent", "commissioner"})
TXN_STATUS = frozenset({"complete", "failed", "pending"})
DRAFT_STATUS = frozenset({"pre_draft", "drafting", "paused", "complete"})
DRAFT_TYPE = frozenset({"snake", "linear", "auction"})
SLOTS = frozenset({"QB", "RB", "WR", "TE", "K", "DEF", "FLEX", "SUPER_FLEX", "REC_FLEX",
                   "WRRB_FLEX", "WRTE_FLEX", "RBTE_FLEX", "IDP_FLEX", "DL", "LB", "DB", "DE",
                   "DT", "CB", "S", "BN", "TAXI", "IR"})
POSITIONS = frozenset({"QB", "RB", "WR", "TE", "K", "DEF", "DL", "LB", "DB", "DE", "DT",
                       "CB", "S", "OL", "LS", "P"})
LEAGUE_SETTINGS = frozenset({
    "bench_lock", "best_ball", "capacity_override", "commissioner_direct_invite",
    "daily_waivers", "daily_waivers_base", "daily_waivers_days", "daily_waivers_hour",
    "daily_waivers_last_ran", "disable_adds", "disable_trades", "divisions", "draft_rounds",
    "faab_suggestions", "last_report", "last_scored_leg", "league_average_match", "leg",
    "max_keepers", "max_subs", "num_teams", "offseason_adds", "pick_trading",
    "playoff_round_type", "playoff_seed_type", "playoff_teams", "playoff_type",
    "playoff_week_start", "reserve_allow_cov", "reserve_allow_dnr", "reserve_allow_doubtful",
    "reserve_allow_na", "reserve_allow_out", "reserve_allow_sus", "reserve_slots", "squads",
    "start_week", "sub_lock_if_starter_active", "sub_start_time_eligibility",
    "taxi_allow_vets", "taxi_deadline", "taxi_slots", "taxi_years", "trade_deadline",
    "trade_review_days", "type", "veto_auto_poll", "veto_show_votes", "veto_votes_needed",
    "waiver_bid_min", "waiver_budget", "waiver_clear_days", "waiver_day_of_week",
    "waiver_type", "was_auto_archived"})
ROSTER_SETTINGS = frozenset({
    "division", "fpts", "fpts_against", "fpts_against_decimal", "fpts_decimal", "losses",
    "ppts", "ppts_decimal", "ties", "total_moves", "waiver_adjusted", "waiver_budget_used",
    "waiver_position", "wins"})
DRAFT_SETTINGS = frozenset({
    "alpha_sort", "autopause_enabled", "autopause_end_time", "autopause_start_time",
    "autostart", "cpu_autopick", "enforce_position_limits", "nomination_timer", "pick_timer",
    "player_type", "reversal_round", "rounds", "teams", "budget"}) | frozenset(
    "slots_" + s.lower() for s in SLOTS)
# Scoring keys are '_'-joined segments ('pass_td', 'bonus_rec_te', 'pts_allow_14_20');
# each segment must be a known word or a number (optionally with 'p', as '40p').
SCORING_WORDS = frozenset("""
    0 2pt allow ast att bonus blk blkd cmp comp def down fd ff fg fga fgm fgmiss first
    fum half hit idp in20 inc int k kick ko kr lng loss lost made miss misc opp own pass pd
    pick pick6 pr pts punt qb rb rec ret rush sack safe sk solo st tb td te tgt tkl tm wr
    xp xpm xpmiss yd yds att lost rec own cmp qb_hit opp_own
""".split())
_SCORE_NUM = re.compile(r"^\d{1,3}p?$")


def _s(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return str(v)
    return v if isinstance(v, str) else None


def _id(v):
    s = _s(v)
    return s if s is not None and _ID_RE.match(s) else None


def _player(v):
    s = _s(v)
    return s if s is not None and _PLAYER_RE.match(s) else None


def _season(v):
    s = _s(v)
    return s if s is not None and _SEASON_RE.match(s) else None


def _enum(v, vocab, other=None):
    if isinstance(v, str) and v in vocab:
        return v
    return other if v is not None else None


def _small(v):
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, str) and v.isdigit() and len(v) <= 5:
        v = int(v)
    return v if isinstance(v, int) and -MAX_SMALL < v < MAX_SMALL else None


def _ts(v):
    """An epoch-ms timestamp (1973..5138)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return v if 10 ** 11 <= v < 10 ** 14 else None


def _pts(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return v if abs(v) < MAX_POINTS else None


def _setting(v):
    if isinstance(v, bool):
        return int(v)
    if v is None:
        return None
    return v if isinstance(v, (int, float)) and abs(v) < MAX_SETTING else False


def _list(v, f) -> list:
    if not isinstance(v, list):
        return []
    return [x for x in (f(i) for i in v) if x is not None]


def _settings(d, known, col=None, kind="settings") -> dict:
    if not isinstance(d, dict):
        return {}
    out = {}
    for k, v in d.items():
        val = _setting(v)
        if k in known and val is not False:
            out[k] = val
        elif col is not None:
            col.dropped[f"{kind}_key_or_value"] += 1
    return out


def scoring_key_ok(k) -> bool:
    if not isinstance(k, str) or not 0 < len(k) <= 40:
        return False
    return all(seg in SCORING_WORDS or _SCORE_NUM.match(seg) for seg in k.split("_"))


def _scoring(d, col=None) -> dict:
    if not isinstance(d, dict):
        return {}
    out = {}
    for k, v in d.items():
        if scoring_key_ok(k) and _pts(v) is not None:
            out[k] = v
        elif col is not None:
            col.dropped["scoring_key_or_value"] += 1
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


def strip_league(obj, ring: KeyRing | None = None, col=None) -> dict | None:
    """Also used by discovery on every listed league, before anything is written."""
    if not isinstance(obj, dict):
        return None
    _note_dropped(col, "league", obj, LEAGUE_FIELDS)
    return {
        "league_id": _id(obj.get("league_id")),
        "previous_league_id": _id(obj.get("previous_league_id")),
        "season": _season(obj.get("season")),
        "season_type": _enum(obj.get("season_type"), SEASON_TYPE),
        "sport": _enum(obj.get("sport"), SPORT),
        "status": _enum(obj.get("status"), LEAGUE_STATUS),
        "total_rosters": _small(obj.get("total_rosters")),
        "draft_id": _id(obj.get("draft_id")),
        "bracket_id": _id(obj.get("bracket_id")),
        "loser_bracket_id": _id(obj.get("loser_bracket_id")),
        "roster_positions": _list(obj.get("roster_positions"),
                                  lambda x: _enum(x, SLOTS, "OTHER")),
        "scoring_settings": _scoring(obj.get("scoring_settings"), col),
        "settings": _settings(obj.get("settings"), LEAGUE_SETTINGS, col, "league_settings"),
    }


ROSTER_FIELDS = ("roster_id", "league_id", "owner_id", "co_owners", "players",
                 "starters", "reserve", "taxi", "keepers", "settings")


def strip_rosters(rows, ring: KeyRing, col=None) -> list:
    out = []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        _note_dropped(col, "roster", r, ROSTER_FIELDS)
        out.append({
            "roster_id": _small(r.get("roster_id")),
            "league_id": _id(r.get("league_id")),
            "owner_key": _ukey(ring, col, r.get("owner_id")),
            "co_owner_keys": [k for k in (_ukey(ring, col, u) for u in
                                          (r.get("co_owners") or [])) if k],
            "players": _list(r.get("players"), _player),
            "starters": _list(r.get("starters"), _player),
            "reserve": _list(r.get("reserve"), _player),
            "taxi": _list(r.get("taxi"), _player),
            "keepers": _list(r.get("keepers"), _player),
            "settings": _settings(r.get("settings"), ROSTER_SETTINGS, col, "roster_settings"),
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


def _player_map(d, col=None) -> dict:
    if not isinstance(d, dict):
        return {}
    out = {}
    for k, v in d.items():
        p, r = _player(k), _small(v)
        if p is not None and r is not None:
            out[p] = r
        elif col is not None:
            col.dropped["player_map_entry"] += 1
    return out


def strip_transactions(rows, ring: KeyRing, col=None) -> list:
    """``type``: one of TXN_TYPES, anything else 'other' (counted in the
    report, so a new type is visible without its text being stored)."""
    out = []
    for t in rows if isinstance(rows, list) else []:
        if not isinstance(t, dict):
            continue
        _note_dropped(col, "transaction", t, TXN_FIELDS)
        settings = t.get("settings") if isinstance(t.get("settings"), dict) else {}
        out.append({
            "transaction_id": _id(t.get("transaction_id")),
            "type": _enum(t.get("type"), TXN_TYPES, "other"),
            "status": _enum(t.get("status"), TXN_STATUS, "other"),
            "leg": _small(t.get("leg")),
            "roster_ids": _list(t.get("roster_ids"), _small),
            "consenter_ids": _list(t.get("consenter_ids"), _small),
            "adds": _player_map(t.get("adds"), col),
            "drops": _player_map(t.get("drops"), col),
            "draft_picks": [{
                "season": _season(p.get("season")),
                "round": _small(p.get("round")),
                "roster_id": _small(p.get("roster_id")),
                "previous_owner_id": _small(p.get("previous_owner_id")),
                "owner_id": _small(p.get("owner_id")),
            } for p in (t.get("draft_picks") or []) if isinstance(p, dict)],
            "waiver_budget": [{
                "sender": _small(w.get("sender")),
                "receiver": _small(w.get("receiver")),
                "amount": _pts(w.get("amount")),
            } for w in (t.get("waiver_budget") or []) if isinstance(w, dict)],
            "settings": {k: _pts(settings.get(k)) for k in ("seq", "waiver_bid")
                         if _pts(settings.get(k)) is not None},
            "notes_code": notes_code(t.get("metadata")),
            "created": _ts(t.get("created")),
            "status_updated": _ts(t.get("status_updated")),
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
            "roster_id": _small(m.get("roster_id")),
            "matchup_id": _small(m.get("matchup_id")),
            "points": _pts(m.get("points")),
            "custom_points": _pts(m.get("custom_points")),
            "players": _list(m.get("players"), _player),
            "starters": _list(m.get("starters"), _player),
            "starters_points": _list(m.get("starters_points"), _pts),
            "players_points": {_player(k): _pts(v) for k, v in pp.items()
                               if _player(k) is not None and _pts(v) is not None},
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
            "draft_id": _id(d.get("draft_id")),
            "league_id": _id(d.get("league_id")),
            "season": _season(d.get("season")),
            "season_type": _enum(d.get("season_type"), SEASON_TYPE),
            "status": _enum(d.get("status"), DRAFT_STATUS, "other"),
            "type": _enum(d.get("type"), DRAFT_TYPE, "other"),
            "start_time": _ts(d.get("start_time")),
            "last_picked": _ts(d.get("last_picked")),
            "settings": _settings(d.get("settings"), DRAFT_SETTINGS, col, "draft_settings"),
            "slot_to_roster_id": {str(_small(k)): _small(v) for k, v in s2r.items()
                                  if _small(k) is not None and _small(v) is not None},
            "draft_order": {k: _small(v) for k, v in
                            ((_ukey(ring, col, u), s) for u, s in order.items())
                            if k and _small(v) is not None},
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
            "draft_id": _id(p.get("draft_id")),
            "pick_no": _small(p.get("pick_no")),
            "round": _small(p.get("round")),
            "draft_slot": _small(p.get("draft_slot")),
            "roster_id": _small(p.get("roster_id")),
            "player_id": _player(p.get("player_id")),
            "is_keeper": bool(p.get("is_keeper")),
            "picked_by_key": _ukey(ring, col, p.get("picked_by")),
            # The only metadata field kept: the drafted player's position.
            "position": _enum(md.get("position"), POSITIONS),
        })
    return out


def strip_traded_picks(rows, ring: KeyRing, col=None) -> list:
    fields = ("season", "round", "roster_id", "owner_id", "previous_owner_id")
    out = []
    for p in rows if isinstance(rows, list) else []:
        if not isinstance(p, dict):
            continue
        _note_dropped(col, "traded_pick", p, fields)
        out.append({"season": _season(p.get("season")), "round": _small(p.get("round")),
                    "roster_id": _small(p.get("roster_id")),
                    "owner_id": _small(p.get("owner_id")),
                    "previous_owner_id": _small(p.get("previous_owner_id"))})
    return out


def strip_bracket(rows, ring: KeyRing, col=None) -> list:
    fields = ("r", "m", "t1", "t2", "w", "l", "p", "t1_from", "t2_from")
    out = []
    for b in rows if isinstance(rows, list) else []:
        if not isinstance(b, dict):
            continue
        _note_dropped(col, "bracket", b, fields)
        row = {k: _small(b.get(k)) for k in ("r", "m", "t1", "t2", "w", "l", "p")}
        for k in ("t1_from", "t2_from"):
            v = b.get(k)
            row[k] = ({kk: _small(vv) for kk, vv in v.items() if kk in ("w", "l")}
                      if isinstance(v, dict) else None)
        out.append(row)
    return out


def strip_state(st) -> dict | None:
    """``/state/nfl``: only these fields, each shape-checked."""
    if not isinstance(st, dict):
        return None
    out = {"season": _season(st.get("season")), "week": _small(st.get("week")),
           "season_type": _enum(st.get("season_type"), SEASON_TYPE),
           "leg": _small(st.get("leg")), "display_week": _small(st.get("display_week")),
           "previous_season": _season(st.get("previous_season")),
           "league_season": _season(st.get("league_season")),
           "season_start_date": (st.get("season_start_date")
                                 if isinstance(st.get("season_start_date"), str)
                                 and _DATE_RE.match(st["season_start_date"]) else None)}
    return {k: v for k, v in out.items() if v is not None}
