"""
seed_ui_test_db.py — fixture seeder for the FTF mobile UI-testing harness.
===========================================================================

Implements C1 of docs/plans/mobile-testing/lld.md (§2.5 CLI contract, §3.1
profile schema) and prd.md R-06/R-07.

One generator, four outputs: the same in-memory synthetic-league world
produces (1) the profile SQLite DB, (2) the Sleeper fixture cassettes served
by the `_sleeper_get` seam, (3) the players warm-cache file, and (4) the
DynastyProcess values CSV served by data_loader's `FTF_DP_VALUES_FILE` seam
— so the DB, `/api/extension/auth`'s fixture view, the warm cache, and the
universal-pool membership rule (cache ∩ DP value > 0) can never disagree.

Outputs (written atomically: staging dir + rename), for `--profile <name>`:

    <out>/<name>.db                      seeded SQLite database
    <out>/sleeper/<name>/**.json         cassettes keyed by URL path relative
                                         to https://api.sleeper.app/v1/
    <out>/players-cache/<name>.json      warm cache in the shape
                                         server._load_sleeper_cache() expects
    <out>/dp-values/<name>.csv           DP-shaped values CSV for
                                         FTF_DP_VALUES_FILE (data_loader seam)
    <out>/dp-values/<name>.picks.csv     DP-shaped PICK-row CSV for
                                         FTF_DP_PICK_VALUES_FILE (M6 seam)
    <out>/<name>.manifest.json           schema hash, seed, flags, counts

Exit codes (LLD §2.5):
    0 ok · 2 io/write failure · 3 refused (token-like field in a profile, or
    --verify schema mismatch → "re-seed profiles") · 4 unknown profile ·
    5 internal cassette gap (the DB implies a Sleeper path the generator
    didn't emit).

Player pool
-----------
Synthetic leagues are drafted from `player_pool_2026.json`: 340 REAL players
(real Sleeper ids/names) chosen because their names carry a DynastyProcess
value > 0 in BOTH scoring formats. The backend's universal ranking pool
(server.build_universal_pool) drops any player whose name has no DP value,
and replayed swipe_decisions referencing a dropped player are silently
skipped — which would corrupt the seeded interaction counts that unlock
gating depends on. Under the harness the DP values are served hermetically
from this seeder's dp-values CSV (FTF_DP_VALUES_FILE, mandatory in
FTF_TEST_MODE); real names keep the fixtures valid against the live CSV too
(record-mode bootstraps, dev runs without the seam).

All writes go through backend.database helpers / SQLAlchemy table objects —
never raw SQL — so schema migrations carry the seeder (LLD §6).

Platforms and drafts
--------------------
A profile league may declare `platform: "espn"` and/or a `draft` block
(sign-off ruling C, docs/plans/mobile-testing/capture-matrix-signoff.md).

* A `draft` block (Sleeper only) generates a whole synthetic rookie draft —
  the `drafts` list, the detail object, the pick list and both traded-pick
  lists — from ONE plan (`World.draft_plan`), so the four cassettes cannot
  disagree. Rosters for such a league are drawn from the VETERAN pool only
  and the made picks are then placed on their picker's roster: the Draft
  Room's undrafted list is `rookie_ids - drafted - ROSTERED`, so a rookie
  class seeded onto rosters empties the board the profile exists to show.
* An `espn` league is DB-only — `upsert_espn_league` + a membership replace,
  plus the optional `pick_assignment` grid. It emits no Sleeper cassettes
  (an ESPN league has no Sleeper URL space) beyond one explicit
  `{"__http_error__": 404}` sentinel at `league/<id>`, because ESPN ids are
  numeric and two Sleeper helpers gate only on `isdigit()`. Both halves are
  enforced by `_verify_no_cassette_gap`.

Determinism: all randomness flows through one seeded RNG, and every
timestamp derives from a single anchored "now" (quantized to the hour for
CLI runs; injectable for tests), so re-seeding with the same seed inside the
same hour is byte-stable.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import logging
import shlex
import os
import random
import re
import shutil
import sqlite3
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

# Script-mode bootstrap: `python backend/tests/fixtures/seed_ui_test_db.py`
# needs the repo root on sys.path before `backend.*` imports resolve.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if __package__ in (None, ""):  # pragma: no cover — CLI convenience only
    sys.path.insert(0, str(_REPO_ROOT))

from sqlalchemy import create_engine, insert, select  # noqa: E402

import backend.database as db  # noqa: E402
from backend.ranking_service import RankingService  # noqa: E402

log = logging.getLogger("trade_finder.seed")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).resolve().parent
PROFILES_DIR = FIXTURES_DIR / "profiles"
FLAGS_DIR = FIXTURES_DIR / "flags"
POOL_FIXTURE = FIXTURES_DIR / "player_pool_2026.json"
DATABASE_PY = _REPO_ROOT / "backend" / "database.py"

DEFAULT_OUT_DIR = "data/ui-test"
DEFAULT_SEED = 1337
SEASON = 2026
POSITIONS = ("QB", "RB", "WR", "TE")

# Platforms a profile league may declare. 'sleeper' is the default and the
# only one that emits Sleeper cassettes; 'espn' rows are DB-only (the ESPN
# read path has no fixture seam — see the espn profile's description).
PLATFORMS = ("sleeper", "espn")

# Sleeper draft `type` values the generator can emit.
DRAFT_TYPES = ("snake", "linear")
# Sleeper draft `status` values → the board's state enum lives in
# draft_board_service.SLEEPER_STATUS_TO_STATE; these are the four real ones.
DRAFT_STATUSES = ("pre_draft", "drafting", "paused", "complete")

# `users.ranking_method` values the app writes (mobile api/rankings.ts
# setRankingMethod). NULL is also legal and is what the DEFAULT path leaves
# behind — see _validate_quickset.
RANKING_METHODS = ("trio", "manual", "tiers", "anchor", "quickset")
# Sentinel: "the profile said nothing", distinct from an explicit null.
_RANKING_METHOD_DEFAULT = object()

# The 13 flag-gated client surfaces from app-inventory-2026-07-10.md §5.
# Every profile must carry an EXPLICIT decision for each (PRD R-07) — a new
# inventory flag added here forces a per-profile decision at seed time.
INVENTORY_FLAG_KEYS: tuple[str, ...] = (
    "landing.smart_start_cta",
    "landing.try_before_sync",
    "league.activity_feed",
    "league.unlock_badges_per_member",
    "profiles.public_pages",
    "swipe.gesture_audit",
    "swipe.qc_compliments",
    "trade.finder_targeting",
    "trade.preference_lists",
    "trade.send_in_sleeper",
    "trade_math.human_explanations",
    "trades.new_partners_alerts",
    "trades.queue_2k",
)

# R-11: no Sleeper write token is representable in a profile. Any key whose
# name smells like a credential refuses the whole seed (exit 3).
_TOKEN_KEY_RE = re.compile(
    r"token|secret|password|jwt|bearer|credential|api[_-]?key", re.IGNORECASE
)

# Reserved username whose cassette is JSON null — Sleeper's real "unknown
# user" response — so TC-SGN-03-style flows have a deterministic 404 path.
UNKNOWN_USERNAME = "qa_unknown_user"

# Per-team position quotas as a share of roster_size (dynasty-typical).
_QUOTA_SHARES = {"QB": 0.15, "RB": 0.31, "WR": 0.38}  # TE takes the remainder

# Exit codes (LLD §2.5)
EXIT_OK = 0
EXIT_IO = 2
EXIT_REFUSED = 3
EXIT_UNKNOWN_PROFILE = 4
EXIT_CASSETTE_GAP = 5


class SeederError(Exception):
    """Raised for any contract failure; `code` maps to the CLI exit code."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# Profile loading & validation
# ---------------------------------------------------------------------------

def list_profiles() -> list[str]:
    """Names of the checked-in profiles (sorted)."""
    return sorted(p.stem for p in PROFILES_DIR.glob("*.json"))


def _scan_for_token_fields(obj, path: str = "$") -> None:
    """Recursively refuse any credential-shaped key in a profile (R-11)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if _TOKEN_KEY_RE.search(str(k)):
                raise SeederError(
                    EXIT_REFUSED,
                    f"refused: profile contains a token-like field {path}.{k!r} "
                    "— Sleeper write credentials are unrepresentable in fixtures (R-11)",
                )
            _scan_for_token_fields(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _scan_for_token_fields(v, f"{path}[{i}]")


def load_flag_set(name: str) -> dict[str, bool]:
    """Load a flag set from fixtures/flags/<name>.json (comment key dropped)."""
    path = FLAGS_DIR / f"{name}.json"
    if not path.exists():
        raise SeederError(EXIT_REFUSED, f"refused: unknown flags_base {name!r} "
                                        f"(no {path.name} in {FLAGS_DIR})")
    raw = json.loads(path.read_text())
    return {k: bool(v) for k, v in raw.items() if not k.startswith("_")}


def load_profile(name_or_path: str) -> dict:
    """Load + validate a profile by name (profiles dir) or explicit .json path.

    Raises SeederError(4) for unknown names, (3) for contract violations.
    """
    if name_or_path.endswith(".json"):
        path = Path(name_or_path)
        if not path.exists():
            raise SeederError(EXIT_UNKNOWN_PROFILE, f"unknown profile: {name_or_path}")
    else:
        path = PROFILES_DIR / f"{name_or_path}.json"
        if not path.exists():
            raise SeederError(
                EXIT_UNKNOWN_PROFILE,
                f"unknown profile: {name_or_path!r} (have: {', '.join(list_profiles())})",
            )

    try:
        profile = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise SeederError(EXIT_REFUSED, f"refused: profile {path.name} is not valid JSON: {e}")

    _scan_for_token_fields(profile)
    _validate_profile(profile)
    return profile


def _validate_profile(p: dict) -> None:
    """Schema-level checks (LLD §3.1). Raises SeederError(3) on violation."""
    def _refuse(msg: str):
        raise SeederError(EXIT_REFUSED, f"refused: profile {p.get('name')!r}: {msg}")

    if p.get("schema_version") != 1:
        _refuse(f"unsupported schema_version {p.get('schema_version')!r}")
    if not p.get("name"):
        _refuse("missing name")
    if p.get("season") != SEASON:
        _refuse(f"season must be {SEASON}")

    # Flags: base must resolve; overrides must be an EXPLICIT decision for
    # all inventory keys, and must not invent unknown flags.
    base = load_flag_set(p.get("flags_base", "release"))
    overrides = p.get("flag_overrides") or {}
    missing = [k for k in INVENTORY_FLAG_KEYS if k not in overrides]
    if missing:
        _refuse(f"flag_overrides must decide every inventory flag; missing {missing}")
    unknown = [k for k in overrides if k not in base]
    if unknown:
        _refuse(f"flag_overrides contains unknown flag keys {unknown}")

    app = p.get("app_user") or {}
    if not app.get("username") or not app.get("user_id"):
        _refuse("app_user needs username + user_id")
    rankings = app.get("rankings")
    if app.get("unlocked") and not rankings:
        _refuse("unlocked:true requires a rankings block")
    if rankings is not None:
        for key in ("positions", "trios_per_position", "history_days", "formats"):
            if key not in rankings:
                _refuse(f"app_user.rankings missing {key!r}")
        bad_fmt = [f for f in rankings["formats"] if f not in db.SCORING_FORMATS]
        if bad_fmt:
            _refuse(f"unknown scoring formats {bad_fmt}")
    _validate_quickset(app, _refuse)

    for lg in p.get("leagues", []):
        for key in ("league_id", "name", "total_rosters", "format", "roster_size"):
            if key not in lg:
                _refuse(f"league missing {key!r}")
        if lg["format"] not in db.SCORING_FORMATS:
            _refuse(f"league {lg['league_id']}: unknown format {lg['format']!r}")
        platform = lg.get("platform", "sleeper")
        if platform not in PLATFORMS:
            _refuse(f"league {lg['league_id']}: unknown platform {platform!r} "
                    f"(have: {', '.join(PLATFORMS)})")
        if platform == "espn" and not str(lg["league_id"]).isdigit():
            _refuse(f"league {lg['league_id']}: an ESPN league id must be numeric "
                    "(the PK column holds the platform-native id)")
        _validate_draft(lg, _refuse)
        _validate_assignment(lg, _refuse)
        for m in lg.get("members", []):
            if not m.get("username") or not m.get("user_id"):
                _refuse(f"league {lg['league_id']}: member needs username + user_id")
            roster = m.get("roster", "generated:balanced")
            if roster != "generated:balanced":
                _refuse(f"roster archetype {roster!r} not implemented in MVP "
                        "(balanced only; qb-heavy/thin/deep-32 are Phase 2)")


def _validate_quickset(app: dict, _refuse) -> None:
    """`app_user.ranking_method` + `app_user.quickset` (audit P0-1, capture
    request #8).

    The pairing is the whole point, so it is validated as a pair. Quick Set
    commits a board through `/api/tiers/save`, which writes `tiers_saved` +
    `tier_overrides` and never touches the trio interaction counter; the
    default route never visits the chooser that writes `ranking_method`. The
    ring on LeagueScreen counts a position ranked when it is TIER-SAVED, so it
    reads 4/4 — while `/api/rankings/progress`, seeing `ranking_method` NULL,
    falls to the trio branch, finds 0 interactions, and answers
    `unlocked: false`. 4/4 and locked.

    That state only survives if `ranking_method` stays NULL: setting it to
    tiers/quickset/manual makes the backend compute `unlocked: true` and the
    fixture would quietly stop reproducing the bug it exists to show. Refused
    rather than allowed to rot.
    """
    method = app.get("ranking_method", _RANKING_METHOD_DEFAULT)
    if method is not _RANKING_METHOD_DEFAULT and method is not None \
            and method not in RANKING_METHODS:
        _refuse(f"app_user.ranking_method {method!r} "
                f"(have: null, {', '.join(RANKING_METHODS)})")

    qs = app.get("quickset")
    if qs is None:
        return
    if not isinstance(qs, dict):
        _refuse("app_user.quickset must be an object")
    positions = qs.get("positions") or list(POSITIONS)
    bad = [p for p in positions if p not in POSITIONS]
    if bad:
        _refuse(f"app_user.quickset unknown positions {bad}")
    formats = qs.get("formats") or list(db.SCORING_FORMATS)
    bad_fmt = [f for f in formats if f not in db.SCORING_FORMATS]
    if bad_fmt:
        _refuse(f"app_user.quickset unknown scoring formats {bad_fmt}")
    try:
        per_pos = int(qs.get("players_per_position", 12))
    except (TypeError, ValueError):
        per_pos = 0
    if per_pos < 1:
        _refuse("app_user.quickset players_per_position must be >= 1")

    # THE guard. `server.get_rankings_progress` unlocks on tiers/quickset when
    # every position is saved, and unconditionally on manual.
    resolved = None if method is _RANKING_METHOD_DEFAULT else method
    if not app.get("unlocked") and resolved in ("tiers", "quickset", "manual"):
        if resolved == "manual" or set(positions) >= set(POSITIONS):
            _refuse(
                f"quickset with ranking_method {resolved!r} and unlocked:false is "
                "incoherent — /api/rankings/progress would answer unlocked:true, "
                "so the profile would not reproduce the 4/4-but-locked state "
                "(audit P0-1). Use ranking_method:null, or set unlocked:true."
            )


def _validate_draft(lg: dict, _refuse) -> None:
    """Optional `league.draft` block (the `draft` profile's whole point).

    A Sleeper-only concept here: an ESPN league has no readable draft object,
    which is exactly why pick-assignment exists (see `_validate_assignment`).
    """
    spec = lg.get("draft")
    if spec is None:
        return
    lid = lg["league_id"]
    if lg.get("platform", "sleeper") != "sleeper":
        _refuse(f"league {lid}: a draft block is Sleeper-only "
                f"(this league is {lg.get('platform')!r})")
    if not isinstance(spec, dict):
        _refuse(f"league {lid}: draft must be an object")
    for key in ("rounds", "status", "picks_made"):
        if key not in spec:
            _refuse(f"league {lid}: draft missing {key!r}")
    if spec["status"] not in DRAFT_STATUSES:
        _refuse(f"league {lid}: draft status {spec['status']!r} "
                f"(have: {', '.join(DRAFT_STATUSES)})")
    dtype = spec.get("type", "snake")
    if dtype not in DRAFT_TYPES:
        _refuse(f"league {lid}: draft type {dtype!r} (have: {', '.join(DRAFT_TYPES)})")
    rounds = int(spec["rounds"])
    teams = int(lg["total_rosters"])
    if rounds < 1 or rounds > 8:
        # draft_status.ROOKIE_MAX_ROUNDS — above it the draft reads as a
        # STARTUP and #207's rookie-shape test flips, which is a different
        # fixture than the one anyone asking for `draft` wants.
        _refuse(f"league {lid}: draft rounds must be 1..8 (rookie-shaped)")
    made = int(spec["picks_made"])
    if made < 0 or made > rounds * teams:
        _refuse(f"league {lid}: picks_made {made} outside 0..{rounds * teams}")
    if spec["status"] == "pre_draft" and made:
        _refuse(f"league {lid}: pre_draft draft cannot have picks_made > 0")
    if spec["status"] == "complete" and made != rounds * teams:
        _refuse(f"league {lid}: a complete draft must have all "
                f"{rounds * teams} picks made")
    traded = int(spec.get("traded_picks", 0))
    if traded < 0 or traded > rounds * teams:
        _refuse(f"league {lid}: traded_picks {traded} outside 0..{rounds * teams}")
    if spec.get("draft_order", True) is False and spec["status"] != "pre_draft":
        _refuse(f"league {lid}: draft_order:false is only honest on a pre_draft draft")


def _validate_assignment(lg: dict, _refuse) -> None:
    """Optional `league.pick_assignment` block (ESPN pick-assignment grid)."""
    spec = lg.get("pick_assignment")
    if spec is None:
        return
    lid = lg["league_id"]
    if not isinstance(spec, dict):
        _refuse(f"league {lid}: pick_assignment must be an object")
    for key in ("rounds", "order_type"):
        if key not in spec:
            _refuse(f"league {lid}: pick_assignment missing {key!r}")
    if spec["order_type"] not in ("linear", "snake"):
        _refuse(f"league {lid}: pick_assignment order_type must be linear|snake")
    if not (1 <= int(spec["rounds"]) <= 8):
        _refuse(f"league {lid}: pick_assignment rounds must be 1..8")


def _resolve_trios(spec, threshold: int) -> int:
    """Resolve 'threshold±N' sentinels against the REAL backend threshold."""
    if isinstance(spec, int):
        return spec
    m = re.fullmatch(r"threshold([+-]\d+)?", str(spec))
    if not m:
        raise SeederError(EXIT_REFUSED, f"refused: bad trios_per_position {spec!r}")
    return threshold + int(m.group(1) or 0)


# ---------------------------------------------------------------------------
# Player pool
# ---------------------------------------------------------------------------

def _load_pool() -> dict[str, dict]:
    """{player_id: record} from the static real-player fixture."""
    doc = json.loads(POOL_FIXTURE.read_text())
    return doc["players"]


def _value_key(fmt: str) -> str:
    return "dp_value_2qb" if fmt == "sf_tep" else "dp_value_1qb"


def _seed_elo(value: float) -> float:
    """DynastyProcess value → seed Elo, mirroring data_loader's formula."""
    return round(1200.0 + (min(float(value), 10000.0) / 10000.0) * 600.0, 1)


def _pool_by_position(pool: dict[str, dict], fmt: str) -> dict[str, list[str]]:
    """Position → player_ids sorted by that format's DP value (desc)."""
    out: dict[str, list[str]] = {pos: [] for pos in POSITIONS}
    for pid, rec in pool.items():
        out[rec["position"]].append(pid)
    vk = _value_key(fmt)
    for pos in POSITIONS:
        out[pos].sort(key=lambda pid: (-pool[pid][vk], pid))
    return out


def _roster_quotas(roster_size: int) -> dict[str, int]:
    q = {pos: max(2, round(roster_size * share)) for pos, share in _QUOTA_SHARES.items()}
    q["TE"] = roster_size - sum(q.values())
    if q["TE"] < 2:
        raise SeederError(EXIT_REFUSED, f"refused: roster_size {roster_size} too small")
    return q


def _draft_rosters(pool: dict[str, dict], fmt: str, team_ids: list[str],
                   roster_size: int,
                   exclude: set[str] | None = None) -> dict[str, list[str]]:
    """Positional snake draft: balanced rosters, deterministic given inputs.

    `exclude` withholds player ids from the draw. Its one caller is a league
    with a `draft` block: a league mid-ROOKIE-draft has, by definition, not
    yet placed this year's rookie class on rosters, and the Draft Room's
    undrafted list is `rookie_ids - drafted - ROSTERED`. Seeding the class
    onto rosters would therefore empty the very board this profile exists to
    show, while looking like a working fixture.
    """
    by_pos = _pool_by_position(pool, fmt)
    if exclude:
        by_pos = {pos: [pid for pid in ids if pid not in exclude]
                  for pos, ids in by_pos.items()}
    quotas = _roster_quotas(roster_size)
    for pos, per_team in quotas.items():
        need = per_team * len(team_ids)
        if need > len(by_pos[pos]):
            raise SeederError(
                EXIT_REFUSED,
                f"refused: pool has {len(by_pos[pos])} {pos}s but the league "
                f"needs {need} — shrink total_rosters/roster_size or grow the pool",
            )
    rosters: dict[str, list[str]] = {uid: [] for uid in team_ids}
    for pos in POSITIONS:
        picks = iter(by_pos[pos])
        for rnd in range(quotas[pos]):
            order = team_ids if rnd % 2 == 0 else list(reversed(team_ids))
            for uid in order:
                rosters[uid].append(next(picks))
    return rosters


# ---------------------------------------------------------------------------
# World model — one generator for DB + cassettes + cache
# ---------------------------------------------------------------------------

class World:
    """The in-memory synthetic state every artifact is derived from."""

    def __init__(self, profile: dict, seed: int, now: datetime):
        self.profile = profile
        self.seed = seed
        self.now = now
        self.rng = random.Random(seed)
        self.pool = _load_pool()
        self.flags = self._effective_flags()
        self.threshold = RankingService.POSITION_THRESHOLDS.get("QB", 10)

        app = profile["app_user"]
        self.app_uid: str = app["user_id"]
        self.app_username: str = app["username"]

        # users: uid → {username, display_name, joined(bool), leagues:[ids]}
        self.users: dict[str, dict] = {}
        self._add_user(self.app_uid, self.app_username, joined=True)
        for xu in profile.get("extra_users", []):
            self._add_user(xu["user_id"], xu["username"], joined=False)

        # leagues: league_id → {spec, member_order:[uid], rosters:{uid:[pid]},
        #                        ranked:[uid]}
        self.leagues: dict[str, dict] = {}
        for lg in profile.get("leagues", []):
            self._build_league(lg)
        self._place_drafted_rookies()

    # -- construction helpers ------------------------------------------------

    def _add_user(self, uid: str, username: str, joined: bool) -> dict:
        rec = self.users.setdefault(uid, {
            "user_id": uid,
            "username": username,
            "display_name": username,
            "joined": joined,
            "leagues": [],
        })
        rec["joined"] = rec["joined"] or joined
        return rec

    def _build_league(self, spec: dict) -> None:
        lid = spec["league_id"]
        platform = spec.get("platform", "sleeper")
        member_order = [self.app_uid]
        ranked: list[str] = []
        n_league = len(self.leagues) + 1
        # Non-app members. On ESPN the counterparties are `espn:` synthetic
        # ids — the SAME shape server._espn_member_id writes — and they are
        # deliberately NOT registered in `self.users`: a synthetic ESPN
        # manager has no Sleeper account, so emitting a `user/<name>`
        # cassette for one would be a fixture that lies about the platform.
        names: dict[str, str] = {}
        for m in spec.get("members", []):
            member_order.append(m["user_id"])
            names[m["user_id"]] = m["username"]
            if platform == "sleeper":
                self._add_user(m["user_id"], m["username"], joined=True)
            if m.get("rankings") == "generated":
                ranked.append(m["user_id"])
        # Fill the remaining seats with generated (not-signed-up) members.
        i = len(member_order)
        while len(member_order) < int(spec["total_rosters"]):
            i += 1
            if platform == "espn":
                uid = f"espn:{lid}.t{i:02d}"
                names[uid] = f"ESPN Team {i:02d}"
                member_order.append(uid)
                continue
            uid = f"9000000000000{n_league:02d}0{i:02d}"
            self._add_user(uid, f"qa_l{n_league}_member_{i:02d}", joined=False)
            member_order.append(uid)

        rosters = _draft_rosters(
            self.pool, spec["format"], member_order, int(spec["roster_size"]),
            exclude=(set(self.rookie_ids(spec["format"])) if spec.get("draft")
                     else None),
        )
        if platform == "sleeper":
            for uid in member_order:
                self.users[uid]["leagues"].append(lid)
        self.leagues[lid] = {
            "spec": spec,
            "platform": platform,
            "member_order": member_order,
            # user_id → display name, for the members whose name does not
            # live in `self.users` (ESPN synthetics).
            "names": names,
            "rosters": rosters,
            "ranked": ranked,
        }

    def _place_drafted_rookies(self) -> None:
        """Put every MADE pick on the picker's roster.

        Sleeper does this the instant a pick lands, so a mid-draft league whose
        rosters lacked its own completed picks would be a state no real league
        can be in — and #207's rosters heuristic reads exactly this signal.
        Runs after every league is built because `draft_plan` needs the seat
        order the build establishes.
        """
        for lid, lg in self.leagues.items():
            plan = self.draft_plan(lid)
            if not plan:
                continue
            for pick in plan["picks"]:
                roster = lg["rosters"][pick["picked_by"]]
                if pick["player_id"] not in roster:
                    roster.append(pick["player_id"])

    # -- naming ---------------------------------------------------------------

    def member_name(self, lid: str, uid: str) -> str:
        """Display name for a league member on any platform."""
        if uid in self.users:
            return self.users[uid]["username"]
        return self.leagues[lid]["names"].get(uid, uid)

    def sleeper_leagues(self) -> dict[str, dict]:
        return {lid: lg for lid, lg in self.leagues.items()
                if lg["platform"] == "sleeper"}

    def espn_leagues(self) -> dict[str, dict]:
        return {lid: lg for lid, lg in self.leagues.items()
                if lg["platform"] == "espn"}

    def _effective_flags(self) -> dict[str, bool]:
        flags = load_flag_set(self.profile.get("flags_base", "release"))
        flags.update({k: bool(v) for k, v in
                      (self.profile.get("flag_overrides") or {}).items()})
        return flags

    # -- derived data ---------------------------------------------------------

    def app_rankings(self) -> dict | None:
        return self.profile["app_user"].get("rankings")

    def ranking_method(self) -> str | None:
        """`users.ranking_method`, or None when the profile leaves it unset.

        Default preserves the pre-P0-1 behavior: a profile with a rankings
        block ranked by trios, so it says so. A profile may override with an
        explicit `null` — which is what the DEFAULT app route actually leaves
        behind, and the whole point of the `quickset-done` profile.
        """
        app = self.profile["app_user"]
        method = app.get("ranking_method", _RANKING_METHOD_DEFAULT)
        if method is _RANKING_METHOD_DEFAULT:
            return "trio" if app.get("rankings") else None
        return method

    def quickset(self) -> dict | None:
        """Normalised `app_user.quickset` (positions / formats / per-position)."""
        qs = self.profile["app_user"].get("quickset")
        if not qs:
            return None
        return {
            "positions": list(qs.get("positions") or POSITIONS),
            "formats": list(qs.get("formats") or db.SCORING_FORMATS),
            "players_per_position": int(qs.get("players_per_position", 12)),
        }

    def trios_per_position(self) -> int:
        r = self.app_rankings()
        return _resolve_trios(r["trios_per_position"], self.threshold) if r else 0

    def unlocked_formats(self) -> list[str]:
        app = self.profile["app_user"]
        if not app.get("unlocked"):
            return []
        return list(self.app_rankings()["formats"])

    def elo_map(self, uid: str, fmt: str, top_n: int = 120) -> dict[str, float]:
        """A member's personal Elo snapshot: seed Elo + deterministic jitter
        over the top `top_n` pool players of the format plus their rosters."""
        by_pos = _pool_by_position(self.pool, fmt)
        pids: list[str] = []
        per_pos = max(1, top_n // len(POSITIONS))
        for pos in POSITIONS:
            pids.extend(by_pos[pos][:per_pos])
        for lg in self.leagues.values():
            if uid in lg["rosters"]:
                pids.extend(lg["rosters"][uid])
        vk = _value_key(fmt)
        # rng is shared/sequential — iteration order (sorted) keeps it stable.
        return {
            pid: round(_seed_elo(self.pool[pid][vk]) + self.rng.uniform(-40, 40), 1)
            for pid in sorted(set(pids))
        }

    def adp_map(self) -> dict[str, float]:
        ordered = sorted(
            self.pool,
            key=lambda pid: (-(self.pool[pid]["dp_value_1qb"] +
                               self.pool[pid]["dp_value_2qb"]), pid),
        )
        return {pid: float(i + 1) for i, pid in enumerate(ordered)}

    # -- rookie class + draft -------------------------------------------------

    def rookie_ids(self, fmt: str) -> list[str]:
        """The pool's `season` rookie class, best consensus first.

        Mirrors `database.load_rookie_player_ids` / `draft_status.is_rookie_row`
        on the same rows `sync_players` will write — BOTH legs, in the same
        order: the exact `metadata.rookie_year == season` test first (the pool
        fixture backfilled that field for its 56-player class on 2026-08-06),
        then the `years_exp == 0 AND team` proxy for rows Sleeper never
        carried a class year for. If these predicates diverge, the board shows
        picks of players the backend does not consider rookies and the
        undrafted list stops shrinking as picks land —
        `test_drafted_players_are_rookies_by_the_BACKENDS_predicate` pins them
        together against the seeded DB.
        """
        vk = _value_key(fmt)

        def is_rookie(rec: dict) -> bool:
            meta = rec.get("metadata")
            year = str((meta or {}).get("rookie_year") or "").strip()
            if len(year) == 4 and year.isdigit() and year != "0000":
                return year == str(SEASON)      # exact test wins outright
            return rec.get("years_exp") == 0 and bool(rec.get("team") or "")

        ids = [pid for pid, rec in self.pool.items() if is_rookie(rec)]
        ids.sort(key=lambda pid: (-self.pool[pid][vk], pid))
        return ids

    def draft_plan(self, lid: str) -> dict | None:
        """The full synthetic Sleeper draft for a league, or None.

        Everything downstream (the `drafts` list, the detail object, the pick
        list and both traded-pick lists) is derived from this one dict, so the
        cassettes cannot disagree with each other the way four hand-authored
        files would.
        """
        lg = self.leagues[lid]
        spec = lg["spec"].get("draft")
        if not spec:
            return None
        teams = len(lg["member_order"])
        rounds = int(spec["rounds"])
        made = int(spec["picks_made"])
        dtype = spec.get("type", "snake")
        status = spec["status"]

        # slot → member. A ROTATION, not the identity: `slot_to_roster_id`
        # below must not accidentally reproduce the ffv3 identity trap the
        # draft corpora exist to pin (see fixtures/draft/README.md §2.1) —
        # an identity map here would let a slot/roster confusion pass.
        rotate = 5 % teams
        uid_by_slot = {s: lg["member_order"][(s - 1 + rotate) % teams]
                       for s in range(1, teams + 1)}
        roster_id_by_uid = {uid: i + 1 for i, uid in enumerate(lg["member_order"])}

        def slot_of(overall: int) -> int:
            rnd = (overall - 1) // teams + 1
            idx = (overall - 1) % teams
            if dtype == "snake" and rnd % 2 == 0:
                idx = teams - 1 - idx
            return idx + 1

        rookies = self.rookie_ids(lg["spec"]["format"])
        if made > len(rookies):
            raise SeederError(
                EXIT_REFUSED,
                f"refused: league {lid} draft wants {made} picks but the pool "
                f"holds only {len(rookies)} {SEASON} rookies — lower picks_made "
                "or grow player_pool_2026.json",
            )

        # Timestamps: Sleeper's are epoch-ms ints. Anchored to the world's
        # `now` so a re-seed inside the same hour is byte-identical.
        created_ms = int((self.now - timedelta(days=45)).timestamp() * 1000)
        start_ms = (None if status == "pre_draft"
                    else int((self.now - timedelta(hours=2)).timestamp() * 1000))

        picks = []
        for overall in range(1, made + 1):
            slot = slot_of(overall)
            uid = uid_by_slot[slot]
            pid = rookies[overall - 1]
            rec = self.pool[pid]
            picks.append({
                "draft_id":   "",          # filled below (needs draft_id)
                "draft_slot": slot,
                "is_keeper":  None,
                "metadata": {
                    "first_name":      rec["first_name"],
                    "injury_status":   "",
                    "last_name":       rec["last_name"],
                    "news_updated":    str(created_ms),
                    "number":          "",
                    "player_id":       pid,
                    "position":        rec["position"],
                    "sport":           "nfl",
                    "status":          rec.get("status") or "Active",
                    "team":            rec.get("team") or "",
                    "team_abbr":       "",
                    "team_changed_at": "",
                    "years_exp":       "0",
                },
                "pick_no":   overall,
                "picked_by": uid,
                "player_id": pid,
                "reactions": None,
                "roster_id": roster_id_by_uid[uid],
                "round":     (overall - 1) // teams + 1,
            })

        # Traded picks. Sleeper's league-level rows carry no draft_id; the
        # draft-level ones do, and both are emitted because both URLs exist.
        n_traded = int(spec.get("traded_picks", 0))
        traded = []
        for i in range(n_traded):
            orig_rid = (i % teams) + 1
            new_rid = ((i + 3) % teams) + 1
            if new_rid == orig_rid:                     # a self-trade is not a trade
                new_rid = (new_rid % teams) + 1
            traded.append({
                "round":             (i % rounds) + 1,
                "season":            str(SEASON),
                "roster_id":         orig_rid,
                "owner_id":          new_rid,
                "previous_owner_id": orig_rid,
            })

        draft_id = str(int(lid) + 1)
        for p in picks:
            p["draft_id"] = draft_id

        # `draft_order` is THE order gate (draft_board_service D5): non-null
        # ⇒ order_confidence "assigned". A profile may set draft_order:false
        # to reproduce the pre-draft "no order yet" board.
        has_order = bool(spec.get("draft_order", True))
        return {
            "draft_id":   draft_id,
            "league_id":  lid,
            "teams":      teams,
            "rounds":     rounds,
            "type":       dtype,
            "status":     status,
            "created_ms": created_ms,
            "start_ms":   start_ms,
            "last_picked": (int((self.now - timedelta(minutes=8)).timestamp() * 1000)
                            if made else None),
            "draft_order": ({uid: s for s, uid in uid_by_slot.items()}
                            if has_order else None),
            "slot_to_roster_id": {str(s): roster_id_by_uid[uid_by_slot[s]]
                                  for s in range(1, teams + 1)},
            "picks":      picks,
            "traded":     traded,
            "undrafted":  rookies[made:],
        }


# ---------------------------------------------------------------------------
# Engine / clock plumbing
# ---------------------------------------------------------------------------

class _TickClock:
    """Deterministic replacement for database._now(): monotonic 1s ticks
    starting 15 minutes before the anchored now, so helper-stamped rows are
    'recent' yet byte-stable across runs sharing an anchor."""

    def __init__(self, anchor: datetime):
        self._t = anchor - timedelta(minutes=15)

    def __call__(self) -> str:
        self._t += timedelta(seconds=1)
        return self._t.isoformat()


@contextmanager
def _use_engine(db_path: Path, anchor: datetime):
    """Point backend.database (and its import-time engine consumers) at a
    dedicated SQLite engine for `db_path`, with a deterministic clock.

    wrapped_collector binds `engine` at import time AND stamps wall-clock
    timestamps, so it is (a) re-pointed defensively and (b) silenced —
    activity-feed rows are seeded explicitly for full control.
    """
    import backend.wrapped_collector as wc

    eng = create_engine(f"sqlite:///{db_path}", future=True,
                        connect_args={"check_same_thread": False})
    url = f"sqlite:///{db_path}"
    try:
        with patch.object(db, "engine", eng), \
                patch.object(db, "DATABASE_URL", url), \
                patch.object(db, "_now", _TickClock(anchor)), \
                patch.object(wc, "engine", eng), \
                patch.object(wc, "record_event", lambda *a, **k: None):
            db.init_db()
            yield eng
    finally:
        eng.dispose()


# ---------------------------------------------------------------------------
# DB seeding
# ---------------------------------------------------------------------------

def _seed_pick_assignment(world: World, lid: str, lg: dict) -> int:
    """Seed the ESPN pick-assignment grid (draft-extensions W3 M-A).

    Writes the STORED numbering settings first, deliberately: with an order
    already saved, `server.pick_assignments_route` skips
    `_espn_suggested_order` entirely — and that helper is the one code path on
    this screen that would reach live ESPN. ESPN has no fixture seam, so a
    profile without a stored order would make the pick-assignment screen the
    only surface in the harness capable of real egress.

    Returns the number of grid slots written.
    """
    spec = lg["spec"].get("pick_assignment")
    if not spec:
        return 0
    # `_assignment_members` sorts member ids, and `_assignment_settings`
    # appends any member missing from the stored order — so a stored order
    # that is already the full membership is the only one that round-trips
    # unchanged.
    member_ids = sorted(lg["member_order"])
    names = {uid: world.member_name(lid, uid) for uid in member_ids}
    order = [uid for uid in lg["member_order"]]     # league seat order, not sorted
    db.save_pick_assignment_settings(lid, {
        "rounds":     int(spec["rounds"]),
        "order_type": spec["order_type"],
        "order":      order,
    })
    result = db.seed_pick_grid(
        lid, member_ids, names,
        actor_user_id=world.app_uid,
        current_season=SEASON,
        rounds=int(spec["rounds"]),
        seasons_ahead=int(spec.get("seasons_ahead", 3)),
        league_size=len(lg["member_order"]),
        scoring_format=lg["spec"]["format"],
        platform="espn",
    )
    return int(result.get("total") or result.get("seeded") or 0)


def _seed_recorded_picks(world: World, lid: str, lg: dict) -> int:
    """Offline pick recording (flag `draft.manual_picks`) — the rows the
    record-picks screen resumes from. Runs AFTER `sync_players`, because
    `record_draft_picks` rejects any row whose player_id is unknown."""
    spec = lg["spec"].get("pick_assignment") or {}
    n = int(spec.get("recorded_picks", 0))
    if not n:
        return 0
    teams = len(lg["member_order"])
    rookies = world.rookie_ids(lg["spec"]["format"])
    rows = []
    for overall in range(1, n + 1):
        slot = (overall - 1) % teams + 1
        rows.append({
            "overall":         overall,
            "round":           (overall - 1) // teams + 1,
            "slot":            slot,
            "player_id":       rookies[overall - 1],
            "picking_team_id": lg["member_order"][slot - 1],
        })
    res = db.record_draft_picks(lid, SEASON, rows, recorded_by=world.app_uid)
    if res.get("rejected"):
        raise SeederError(EXIT_REFUSED,
                          f"refused: league {lid} recorded picks rejected: "
                          f"{res['rejected']}")
    return int(res.get("accepted") or 0)


def _seed_db(world: World, eng) -> dict[str, int]:
    """Write the world into the (already-pointed) engine. Returns row counts."""
    rng = world.rng
    profile = world.profile
    app = profile["app_user"]
    anchor = world.now

    # -- users ---------------------------------------------------------------
    for uid, u in world.users.items():
        if u["joined"]:
            db.upsert_user(sleeper_user_id=uid, username=u["username"],
                           display_name=u["display_name"], avatar=None)

    rankings = world.app_rankings()
    method = world.ranking_method()
    if method:
        db.set_ranking_method(world.app_uid, method)
    for fmt in world.unlocked_formats():
        db.mark_format_unlocked(world.app_uid, fmt)

    # -- Quick Set commit (tiers_saved + tier_overrides), audit P0-1 ---------
    quickset_positions = 0
    quickset_overrides = 0
    qs = world.quickset()
    if qs:
        for fmt in qs["formats"]:
            by_pos = _pool_by_position(world.pool, fmt)
            overrides: dict[str, float] = {}
            for pos in qs["positions"]:
                for pid in by_pos[pos][: qs["players_per_position"]]:
                    # Quick Set's commit is a REORDER of the consensus board,
                    # so the stored Elo is the seed with a small deterministic
                    # nudge — enough that the board is genuinely the user's
                    # (and the public profile's contrarian takes have
                    # something to find) without inventing a wild ranking.
                    seed = _seed_elo(world.pool[pid][_value_key(fmt)])
                    overrides[pid] = round(seed + rng.uniform(-25, 25), 1)
            db.save_tier_overrides(world.app_uid, overrides, scoring_format=fmt)
            quickset_overrides += len(overrides)
            for pos in qs["positions"]:
                db.save_tiers_position(world.app_uid, pos, scoring_format=fmt)
                quickset_positions += 1

    # -- leagues + members ----------------------------------------------------
    pick_slots = 0
    for lid, lg in world.leagues.items():
        spec = lg["spec"]
        members = [
            {"user_id": uid,
             "username": world.member_name(lid, uid),
             "display_name": world.member_name(lid, uid),
             "player_ids": lg["rosters"][uid]}
            for uid in lg["member_order"]
        ]
        if lg["platform"] == "espn":
            # The ESPN importer's own write path — platform='espn' + the
            # espn_* binding columns, then a full membership replace. NOTHING
            # here writes an espn_credentials row: `espn_auth: "public"` is
            # the only auth mode representable in a fixture (R-11), and it is
            # also the mode that keeps every ESPN read out of the harness.
            db.upsert_espn_league(
                lid, world.app_uid, spec["name"],
                espn_season=SEASON,
                espn_auth=spec.get("espn_auth", "public"),
                espn_my_team_id=int(spec.get("espn_my_team_id", 1)),
                total_rosters=int(spec["total_rosters"]),
            )
            db.replace_espn_league_members(lid, members)
            db.set_league_scoring(lid, spec["format"])
            pick_slots += _seed_pick_assignment(world, lid, lg)
            continue

        opponents = [m for m in members if m["user_id"] != world.app_uid]
        db.upsert_league(lid, world.app_uid, spec["name"], str(SEASON),
                         lg["rosters"][world.app_uid], opponents)
        db.set_league_scoring(lid, spec["format"])
        db.set_league_total_rosters(lid, int(spec["total_rosters"]))
        db.upsert_league_members(lid, members)

    # -- app-user swipe history (drives replayed Elo + unlock counts) ---------
    swipe_rows = 0
    if rankings:
        trios = world.trios_per_position()
        for fmt in rankings["formats"]:
            by_pos = _pool_by_position(world.pool, fmt)
            for pos in rankings["positions"]:
                # Trios come from the top-24 of the position (the backend's
                # pre-unlock serving tier), ordered mostly by consensus with
                # deterministic upsets so personal Elo diverges a little.
                top = by_pos[pos][:24]
                for _ in range(trios):
                    trio = rng.sample(top, 3)
                    trio.sort(key=lambda pid: -world.pool[pid][_value_key(fmt)])
                    if rng.random() < 0.25:  # occasional contrarian take
                        trio[0], trio[1] = trio[1], trio[0]
                    db.save_ranking_swipes(world.app_uid, trio,
                                           k_factor=32.0, scoring_format=fmt)
                    swipe_rows += 3

    # -- member_rankings snapshots ---------------------------------------------
    mr_rows = 0
    for lid, lg in world.leagues.items():
        ranked_uids = list(lg["ranked"])
        if app.get("unlocked"):
            ranked_uids.append(world.app_uid)
        for uid in ranked_uids:
            fmts = (rankings["formats"] if uid == world.app_uid and rankings
                    else db.SCORING_FORMATS)
            for fmt in fmts:
                elo = world.elo_map(uid, fmt)
                db.upsert_member_rankings(
                    uid, lid,
                    [{"player_id": pid, "elo": e} for pid, e in elo.items()],
                    scoring_format=fmt,
                )
                mr_rows += len(elo)

    # -- Elo history (Trends risers/fallers), timestamps relative to now ------
    hist_rows = 0
    if rankings:
        days = int(rankings["history_days"])
        offsets = [d for d in (29, 22, 15, 8, 3, 1) if d < days] or [1]
        for fmt in rankings["formats"]:
            by_pos = _pool_by_position(world.pool, fmt)
            movers = [pid for pos in POSITIONS for pid in by_pos[pos][:6]]
            hist = []
            for i, pid in enumerate(movers):
                base = _seed_elo(world.pool[pid][_value_key(fmt)])
                drift = rng.uniform(40, 140) * (1 if i % 2 == 0 else -1)
                steps = len(offsets)
                for j, day in enumerate(sorted(offsets, reverse=True)):
                    frac = (j + 1) / steps
                    hist.append({
                        "user_id": world.app_uid,
                        "league_id": None,
                        "player_id": pid,
                        "scoring_format": fmt,
                        "elo": round(base + drift * frac, 1),
                        "snapshot_at": (anchor - timedelta(days=day)).isoformat(),
                    })
            with eng.begin() as conn:
                conn.execute(insert(db.elo_history_table), hist)
            hist_rows += len(hist)

    # -- matches: mutual trade_matches + one-sided awaiting likes -------------
    matches = 0
    awaiting = 0
    for lid, lg in world.leagues.items():
        seed_spec = lg["spec"].get("matches_seed") or {}
        partners = [uid for uid in lg["member_order"] if uid != world.app_uid]
        my_roster = lg["rosters"][world.app_uid]
        for i in range(int(seed_spec.get("mutual", 0))):
            partner = partners[i % len(partners)]
            give = [my_roster[4 + 2 * i], my_roster[12 + 2 * i]]
            receive = [lg["rosters"][partner][5 + 2 * i]]
            if i % 2 == 0:  # app user triggered the match
                db.create_trade_match(lid, world.app_uid, partner, give, receive)
            else:           # counterparty triggered it (b-side perspective)
                db.create_trade_match(lid, partner, world.app_uid, receive, give)
            db.create_notification(
                world.app_uid, "trade_match", "New trade match",
                f"You and @{world.member_name(lid, partner)} liked the same trade.",
                {"league_id": lid,
                 "partner_username": world.member_name(lid, partner)},
            )
            matches += 1
        for i in range(int(seed_spec.get("awaiting", 0))):
            partner = partners[(i + 1) % len(partners)]
            give = [my_roster[8 + i]]
            receive = [lg["rosters"][partner][9 + i]]
            db.save_trade_decision(world.app_uid, lid, f"seed-awaiting-{lid}-{i}",
                                   give, receive, "like")
            awaiting += 1

    # -- activity feed (wrapped_events narrative types), backdated ------------
    n_activity = int(profile.get("activity_seed", 0))
    if n_activity and world.leagues:
        lid = next(iter(world.leagues))
        lg = world.leagues[lid]
        actor = (lg["ranked"] or [world.app_uid])[0]
        fmt = lg["spec"]["format"]
        templates = [
            (actor, "league_sync", {}),
            (actor, "tier_save", {"position": "WR", "scoring_format": fmt}),
            (world.app_uid, "trade_match", {"other_user_id": actor}),
        ]
        rows = []
        for i in range(n_activity):
            uid, etype, payload = templates[i % len(templates)]
            rows.append({
                "user_id": uid,
                "league_id": lid,
                "season": SEASON,
                "event_type": etype,
                "payload_json": json.dumps(payload),
                "created_at": (anchor - timedelta(hours=3 * (i + 1))).isoformat(),
            })
        with eng.begin() as conn:
            conn.execute(insert(db.wrapped_events_table), rows)

    # -- feedback with an operator reply (status chip in the inbox) -----------
    n_feedback = int(profile.get("feedback_reply_seed", 0))
    if n_feedback:
        rows = []
        for i in range(n_feedback):
            rows.append({
                "client_id": f"seed-{profile['name']}-fb-{i}",
                "user_id": world.app_uid,
                "username": world.app_username,
                "screen": "Trades",
                "severity": "idea",
                "text": "Seeded feedback note — the deck could surface more TE trades.",
                "app_version": "1.5.3",
                "platform": "ios",
                "device_type": "iphone",
                "os_version": "18.4",
                "client_created_at": (anchor - timedelta(days=3)).isoformat(),
                "created_at": (anchor - timedelta(days=3)).isoformat(),
                "status": "fixed",
                "status_updated_at": (anchor - timedelta(days=1)).isoformat(),
            })
        with eng.begin() as conn:
            conn.execute(insert(db.app_feedback_table), rows)

    # -- players reference table ----------------------------------------------
    players_written = db.sync_players(_cache_shape(world), adp_map=world.adp_map())

    # -- recorded picks (AFTER sync_players — the writer validates player ids) -
    recorded = 0
    for lid, lg in world.leagues.items():
        recorded += _seed_recorded_picks(world, lid, lg)

    return {
        "users": sum(1 for u in world.users.values() if u["joined"]),
        "leagues": len(world.leagues),
        "league_members": sum(len(lg["member_order"]) for lg in world.leagues.values()),
        "pick_assignment_slots": pick_slots,
        "recorded_picks": recorded,
        "quickset_positions_saved": quickset_positions,
        "quickset_tier_overrides": quickset_overrides,
        "players": players_written,
        "swipe_rows": swipe_rows,
        "member_ranking_rows": mr_rows,
        "elo_history_rows": hist_rows,
        "trade_matches": matches,
        "awaiting_likes": awaiting,
        "activity_events": n_activity,
        "feedback_rows": n_feedback,
    }


# ---------------------------------------------------------------------------
# Sleeper cassettes + players cache
# ---------------------------------------------------------------------------

def _cache_shape(world: World) -> dict[str, dict]:
    """The players warm-cache payload: Sleeper bulk shape, trimmed to the
    fields server.py/build_universal_pool/sync_players actually read."""
    out = {}
    for pid, rec in world.pool.items():
        p = {k: v for k, v in rec.items() if not k.startswith("dp_value_")}
        p["active"] = True
        p["sport"] = "nfl"
        p["fantasy_positions"] = [rec["position"]]
        out[pid] = p
    return out


def _dp_csv_text(world: World) -> str:
    """DP-shaped values CSV (columns: player, pos, value_1qb, value_2qb) for
    the data_loader FTF_DP_VALUES_FILE seam.

    Rows carry each pool player's REAL Sleeper full_name, so data_loader's
    normalise_name(player) is byte-identical to what build_universal_pool
    computes from the players cache — pool membership stays exactly
    cache ∩ value>0 with no dependency on the live DynastyProcess CSV.
    Ordered by value_1qb desc (like the real file), deterministically.
    """
    ordered = sorted(
        world.pool.values(),
        key=lambda rec: (-rec["dp_value_1qb"], rec["player_id"]),
    )
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\n")
    writer.writerow(["player", "pos", "value_1qb", "value_2qb"])
    for rec in ordered:
        writer.writerow([rec["full_name"], rec["position"],
                         int(rec["dp_value_1qb"]), int(rec["dp_value_2qb"])])
    return buf.getvalue()


def _dp_pick_csv_text() -> str:
    """DP-shaped *combined* values CSV carrying only `pos == "PICK"` rows, for
    the data_loader FTF_DP_PICK_VALUES_FILE seam (rookie-draft M6).

    `values.csv` is a SECOND live DynastyProcess egress, so `backend/server`
    refuses to start in test mode without this file pinned. The world does not
    model draft picks, so the curve is synthetic-but-shaped: a geometric decay
    over the 12-team slots of rounds 1-5, plus the three 2027 first-round
    rungs. Values only need to be positive, monotone and DP-scaled — the
    harness renders them, it does not calibrate against them.
    """
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\n")
    writer.writerow(["player", "pos", "value_1qb", "value_2qb"])
    n = 0
    for round_no in range(1, 6):
        for slot in range(1, 13):
            n += 1
            v1 = max(1, round(5600 * (0.82 ** (n - 1))))
            writer.writerow([f"{SEASON} Pick {round_no}.{slot:02d}", "PICK",
                             v1, round(v1 * 1.25)])
    for label, v1 in ((f"{SEASON + 1} Early 1st", 3347),
                      (f"{SEASON + 1} Mid 1st", 1554),
                      (f"{SEASON + 1} Late 1st", 754)):
        writer.writerow([label, "PICK", v1, round(v1 * 1.25)])
    return buf.getvalue()


def _league_meta(world: World, lid: str) -> dict:
    lg = world.leagues[lid]
    spec = lg["spec"]
    sf = spec["format"] == "sf_tep"
    starters = (["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "FLEX"]
                + (["SUPER_FLEX"] if sf else []))
    bench = ["BN"] * (int(spec["roster_size"]) - len(starters))
    return {
        "league_id": lid,
        "name": spec["name"],
        "season": str(SEASON),
        "sport": "nfl",
        "status": "in_season",
        "avatar": None,
        "previous_league_id": None,
        "total_rosters": int(spec["total_rosters"]),
        "roster_positions": starters + bench,
        "scoring_settings": {
            "rec": 1.0,
            "bonus_rec_te": 0.5 if sf else 0.0,
            "pass_td": 4.0,
            "rush_td": 6.0,
            "rec_td": 6.0,
        },
        "settings": {
            "num_teams": int(spec["total_rosters"]),
            "type": 2,           # dynasty
            "taxi_slots": 4,
            "reserve_slots": 3,
            "leg": 1,
        },
    }


def _sleeper_user_obj(u: dict) -> dict:
    return {
        "user_id": u["user_id"],
        "username": u["username"],
        "display_name": u["display_name"],
        "avatar": None,
        "is_bot": False,
    }


def _draft_summary(world: World, plan: dict) -> dict:
    """The draft object as it appears BOTH in `league/<id>/drafts` and at
    `draft/<id>` — Sleeper serves the same document at both URLs (verified
    against fixtures/draft/lakeview-complete), so one builder emits both and
    they cannot drift."""
    lg = world.leagues[plan["league_id"]]
    spec = lg["spec"]
    sf = spec["format"] == "sf_tep"
    return {
        "created": plan["created_ms"],
        "creators": [world.app_uid],
        "draft_id": plan["draft_id"],
        "draft_order": plan["draft_order"],
        "last_message_id": None,
        "last_message_time": None,
        "last_picked": plan["last_picked"],
        "league_id": plan["league_id"],
        "metadata": {
            "description": "",
            "name": spec["name"],
            "scoring_type": "dynasty_2qb" if sf else "dynasty_ppr",
            "show_team_names": "0",
        },
        "season": str(SEASON),
        "season_type": "regular",
        "settings": {
            "alpha_sort": 0,
            "autopause_enabled": 1,
            "autostart": 0,
            "cpu_autopick": 1,
            "enforce_position_limits": 0,
            "nomination_timer": 60,
            "pick_timer": 14400,
            "player_type": 0,
            "reversal_round": 0,
            "rounds": plan["rounds"],
            "teams": plan["teams"],
        },
        "slot_to_roster_id": plan["slot_to_roster_id"],
        "sport": "nfl",
        "start_time": plan["start_ms"],
        "status": plan["status"],
        "type": plan["type"],
    }


def build_cassettes(world: World) -> dict[str, object]:
    """URL-path (relative to api.sleeper.app/v1/, no extension) → JSON doc.

    ESPN leagues emit NOTHING here on purpose: an ESPN league has no Sleeper
    URL space, and inventing one would make the fixture claim a read the real
    client never performs.
    """
    cassettes: dict[str, object] = {}

    league_meta = {lid: _league_meta(world, lid) for lid in world.sleeper_leagues()}

    for u in world.users.values():
        cassettes[f"user/{u['username']}"] = _sleeper_user_obj(u)
        cassettes[f"user/{u['user_id']}/leagues/nfl/{SEASON}"] = [
            league_meta[lid] for lid in u["leagues"]
        ]
    # Deterministic "unknown user" — Sleeper answers JSON null, which the
    # backend maps to 404 (TC-SGN-03-style flows).
    cassettes[f"user/{UNKNOWN_USERNAME}"] = None

    for lid, lg in world.sleeper_leagues().items():
        cassettes[f"league/{lid}"] = league_meta[lid]
        rosters = []
        for i, uid in enumerate(lg["member_order"]):
            players = lg["rosters"][uid]
            wins = (7 + i * 3) % 12
            rosters.append({
                "roster_id": i + 1,
                "owner_id": uid,
                "league_id": lid,
                "players": players,
                "starters": players[:10],
                "reserve": [],
                "taxi": [],
                "settings": {"wins": wins, "losses": 11 - wins, "ties": 0},
                "metadata": {},
            })
        cassettes[f"league/{lid}/rosters"] = rosters
        cassettes[f"league/{lid}/users"] = [
            {**_sleeper_user_obj(world.users[uid]),
             "league_id": lid,
             "is_owner": i == 0,
             "metadata": {"team_name": f"Team {world.users[uid]['display_name']}"}}
            for i, uid in enumerate(lg["member_order"])
        ]
        # Owned-picks + draft-status features (both added after this fixture
        # set was written) fetch these on every league load. Empty arrays are
        # the honest seeded answer for a league with no `draft` block — no
        # picks have been traded and no draft exists — and they hold
        # vcr_misses at 0 for EVERY profile. With `drafts` empty the backend
        # falls back to its rosters_heuristic for draft status, which is what
        # the seeded rosters already imply.
        plan = world.draft_plan(lid)
        if plan is None:
            cassettes[f"league/{lid}/traded_picks"] = []
            cassettes[f"league/{lid}/drafts"] = []
            continue

        summary = _draft_summary(world, plan)
        did = plan["draft_id"]
        cassettes[f"league/{lid}/drafts"] = [summary]
        cassettes[f"draft/{did}"] = summary
        cassettes[f"draft/{did}/picks"] = plan["picks"]
        # League-level rows carry no draft_id; the draft-level ones do. Both
        # URLs exist upstream, so both are emitted even though
        # draft_board_service only reads the league-level list today — a
        # future read must not become the harness's first vcr_miss.
        cassettes[f"league/{lid}/traded_picks"] = plan["traded"]
        cassettes[f"draft/{did}/traded_picks"] = [
            {**t, "draft_id": int(did)} for t in plan["traded"]
        ]

    # ESPN league ids are NUMERIC, and two Sleeper-side helpers gate only on
    # `league_id.isdigit()` (server._fetch_sleeper_league_meta and, behind
    # `sleeper.trade_block`, trade_block_service.sync_league_trade_block —
    # both docstrings claim to no-op for ESPN imports; neither does). So
    # session-init on an ESPN league DOES reach for
    # `https://api.sleeper.app/v1/league/<espn id>`, and without an answer
    # here every ESPN run books a vcr_miss and the guardrail can't tell it
    # from a real fixture gap. Sleeper answers 404 for an id that is not one
    # of its leagues; the `__http_error__` sentinel replays exactly that, so
    # the harness reproduces production rather than papering over it. NOT a
    # league object — emitting one would claim an ESPN league exists on
    # Sleeper, and `_verify_no_cassette_gap` refuses any other league/<id>
    # path for an ESPN league.
    for lid in world.espn_leagues():
        cassettes[f"league/{lid}"] = {"__http_error__": 404}

    cassettes["players/nfl/adp"] = world.adp_map()
    # players/nfl is fetched outside the _sleeper_get seam today (raw urllib
    # in _ensure_sleeper_cache_populated) — the warm-cache file covers it.
    # Emitted anyway so a future seam widening can never gap.
    cassettes["players/nfl"] = _cache_shape(world)
    return cassettes


def _verify_no_cassette_gap(world: World, cassettes: dict[str, object]) -> None:
    """Exit-5 invariant: every Sleeper path the DB implies must be emitted."""
    needed: list[str] = ["players/nfl/adp"]
    for u in world.users.values():
        needed.append(f"user/{u['username']}")
        needed.append(f"user/{u['user_id']}/leagues/nfl/{SEASON}")
    for lid in world.sleeper_leagues():
        needed += [f"league/{lid}", f"league/{lid}/rosters", f"league/{lid}/users",
                   f"league/{lid}/traded_picks", f"league/{lid}/drafts"]
        plan = world.draft_plan(lid)
        if plan is not None:
            did = plan["draft_id"]
            needed += [f"draft/{did}", f"draft/{did}/picks",
                       f"draft/{did}/traded_picks"]
    # An ESPN league must NOT have leaked into the Sleeper URL space — the
    # other half of the gap guard: a cassette nobody can legitimately request
    # is as much a lie as a missing one. The single exception is the explicit
    # 404 sentinel at `league/<id>`, which is what Sleeper really answers for
    # an id that is not one of its leagues (see build_cassettes).
    stray = []
    for lid in world.espn_leagues():
        for p in cassettes:
            if not p.startswith(f"league/{lid}"):
                continue
            doc = cassettes[p]
            if p == f"league/{lid}" and isinstance(doc, dict) \
                    and set(doc) == {"__http_error__"}:
                continue
            stray.append(p)
    if stray:
        raise SeederError(EXIT_CASSETTE_GAP,
                          f"internal cassette gap — ESPN leagues emitted Sleeper "
                          f"cassettes: {stray}")
    missing = [p for p in needed if p not in cassettes]
    if missing:
        raise SeederError(EXIT_CASSETTE_GAP,
                          f"internal cassette gap — generator did not emit: {missing}")


# ---------------------------------------------------------------------------
# Manifest / hashing
# ---------------------------------------------------------------------------

def schema_hash() -> str:
    """sha256 of backend/database.py — the schema fingerprint --verify pins."""
    return hashlib.sha256(DATABASE_PY.read_bytes()).hexdigest()


def db_content_hash(db_path: Path) -> str:
    """Logical (dump-level) hash of the SQLite content — stable across
    identical row sets regardless of page-level layout."""
    con = sqlite3.connect(str(db_path))
    try:
        dump = "\n".join(con.iterdump())
    finally:
        con.close()
    return hashlib.sha256(dump.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Seeding orchestration (atomic)
# ---------------------------------------------------------------------------

def seed_profile(name_or_path: str, out_dir: str | Path = DEFAULT_OUT_DIR,
                 seed: int = DEFAULT_SEED, now: datetime | None = None) -> dict:
    """Seed one profile. Returns the manifest dict.

    `now` anchors every fabricated timestamp; the CLI quantizes to the top
    of the current hour so two runs inside one hour are byte-identical.
    """
    profile = load_profile(name_or_path)
    name = profile["name"]
    if now is None:
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    out_dir = Path(out_dir).resolve()
    world = World(profile, seed, now)
    cassettes = build_cassettes(world)
    _verify_no_cassette_gap(world, cassettes)

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "sleeper").mkdir(exist_ok=True)
        (out_dir / "players-cache").mkdir(exist_ok=True)
        (out_dir / "dp-values").mkdir(exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".seed-{name}-", dir=out_dir))
    except OSError as e:
        raise SeederError(EXIT_IO, f"io failure preparing {out_dir}: {e}")

    try:
        # 1) database
        db_path = staging / f"{name}.db"
        with _use_engine(db_path, now) as eng:
            counts = _seed_db(world, eng)

        # 2) sleeper cassettes
        sleeper_dir = staging / "sleeper" / name
        for rel, doc in cassettes.items():
            path = sleeper_dir / f"{rel}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(doc, indent=1, sort_keys=True))

        # 3) players warm cache
        cache_path = staging / "players-cache" / f"{name}.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(_cache_shape(world), sort_keys=True))

        # 4) DynastyProcess values CSV (FTF_DP_VALUES_FILE seam)
        dp_path = staging / "dp-values" / f"{name}.csv"
        dp_path.parent.mkdir(parents=True, exist_ok=True)
        dp_path.write_text(_dp_csv_text(world))

        # 4b) DynastyProcess PICK values CSV (FTF_DP_PICK_VALUES_FILE seam) —
        #     the second remote file, pinned so test mode has no egress hole.
        dp_picks_path = staging / "dp-values" / f"{name}.picks.csv"
        dp_picks_path.write_text(_dp_pick_csv_text())

        # 5) manifest (last — its presence marks a complete seed)
        counts["sleeper_fixtures"] = len(cassettes)
        manifest = {
            "schema_version": 1,
            "profile": name,
            "seed": seed,
            "season": SEASON,
            "created_at": now.isoformat(),
            "schema_hash": schema_hash(),
            "db_content_hash": db_content_hash(db_path),
            "flags": dict(sorted(world.flags.items())),
            "counts": counts,
            "outputs": {
                "db": f"{name}.db",
                "sleeper_dir": f"sleeper/{name}",
                "players_cache": f"players-cache/{name}.json",
                "dp_values": f"dp-values/{name}.csv",
                "dp_pick_values": f"dp-values/{name}.picks.csv",
            },
            "pool_fixture": POOL_FIXTURE.name,
        }
        manifest_path = staging / f"{name}.manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True))

        # Promote: rename into place (manifest last).
        final_sleeper = out_dir / "sleeper" / name
        if final_sleeper.exists():
            shutil.rmtree(final_sleeper)
        os.replace(sleeper_dir, final_sleeper)
        os.replace(db_path, out_dir / f"{name}.db")
        os.replace(cache_path, out_dir / "players-cache" / f"{name}.json")
        os.replace(dp_path, out_dir / "dp-values" / f"{name}.csv")
        os.replace(dp_picks_path, out_dir / "dp-values" / f"{name}.picks.csv")
        os.replace(manifest_path, out_dir / f"{name}.manifest.json")
    except SeederError:
        raise
    except OSError as e:
        raise SeederError(EXIT_IO, f"io failure writing {out_dir}: {e}")
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    log.info("seeded profile %r → %s (%s)", name, out_dir,
             ", ".join(f"{k}={v}" for k, v in counts.items()))
    return manifest


def verify_profile(name: str, out_dir: str | Path = DEFAULT_OUT_DIR) -> None:
    """--verify: refuse (exit 3) when the seeded artifacts predate a backend
    schema change (manifest schema_hash != current backend/database.py)."""
    out_dir = Path(out_dir)
    manifest_path = out_dir / f"{name}.manifest.json"
    if not manifest_path.exists():
        raise SeederError(EXIT_REFUSED,
                          f"verify failed: no manifest at {manifest_path} — re-seed profiles")
    manifest = json.loads(manifest_path.read_text())
    current = schema_hash()
    if manifest.get("schema_hash") != current:
        raise SeederError(
            EXIT_REFUSED,
            f"verify failed: schema drift for profile {name!r} "
            f"(manifest {str(manifest.get('schema_hash'))[:12]}… != "
            f"backend/database.py {current[:12]}…) — re-seed profiles",
        )
    for rel in manifest.get("outputs", {}).values():
        if not (out_dir / rel).exists():
            raise SeederError(EXIT_REFUSED,
                              f"verify failed: missing output {rel} — re-seed profiles")


def print_env(name: str, out_dir: str | Path = DEFAULT_OUT_DIR,
              manifest: dict | None = None, stream=None) -> None:
    """--print-env: the env block sim-run.sh sources (LLD §2.5b)."""
    stream = stream or sys.stdout
    out_dir = Path(out_dir).resolve()
    if manifest is None:
        manifest_path = out_dir / f"{name}.manifest.json"
        if not manifest_path.exists():
            raise SeederError(EXIT_IO, f"no manifest at {manifest_path} — seed first")
        manifest = json.loads(manifest_path.read_text())
    flags_json = json.dumps(manifest["flags"], sort_keys=True, separators=(",", ":"))
    # shlex.quote: the block is `source`d/eval'd by sim-run.sh, and this repo's
    # path contains spaces ("Fantasy Trade Finder") — unquoted values word-split.
    q = shlex.quote
    lines = [
        f"DATABASE_URL={q('sqlite:///' + str(out_dir / (name + '.db')))}",
        f"FTF_SLEEPER_FIXTURES_DIR={q(str(out_dir / 'sleeper' / name))}",
        f"FTF_PLAYERS_CACHE_FILE={q(str(out_dir / 'players-cache' / (name + '.json')))}",
        f"FTF_DP_VALUES_FILE={q(str(out_dir / 'dp-values' / (name + '.csv')))}",
        f"FTF_DP_PICK_VALUES_FILE={q(str(out_dir / 'dp-values' / (name + '.picks.csv')))}",
        f"FTF_FLAGS={q(flags_json)}",
        "FTF_TEST_MODE=1",
        f"FTF_TEST_PROFILE={q(name)}",
    ]
    print("\n".join(lines), file=stream)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="seed_ui_test_db.py",
        description="Seed a UI-test fixture profile (DB + Sleeper cassettes + "
                    "players cache + manifest). LLD: docs/plans/mobile-testing/lld.md §2.5",
    )
    parser.add_argument("--profile", help="profile name (see --list) or a .json path")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR,
                        help=f"output directory (default: {DEFAULT_OUT_DIR})")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED,
                        help=f"RNG seed (default: {DEFAULT_SEED})")
    parser.add_argument("--list", action="store_true",
                        help="list available profiles and exit")
    parser.add_argument("--verify", action="store_true",
                        help="verify existing outputs against the current backend "
                             "schema instead of seeding (exit 3 on drift)")
    parser.add_argument("--print-env", action="store_true",
                        help="print the env block sim-run.sh sources")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    try:
        if args.list:
            for p in list_profiles():
                print(p)
            return EXIT_OK

        if not args.profile:
            parser.error("--profile is required (or use --list)")

        # Resolve the canonical profile name for verify/print-env paths.
        name = (json.loads(Path(args.profile).read_text())["name"]
                if args.profile.endswith(".json") and Path(args.profile).exists()
                else args.profile)

        if args.verify:
            verify_profile(name, args.out_dir)
            log.info("verify ok: profile %r matches backend/database.py", name)
            manifest = None
        else:
            manifest = seed_profile(args.profile, args.out_dir, args.seed)

        if args.print_env:
            print_env(name, args.out_dir, manifest=manifest)
        return EXIT_OK
    except SeederError as e:
        log.error("%s", e)
        return e.code
    except OSError as e:
        log.error("io failure: %s", e)
        return EXIT_IO


if __name__ == "__main__":
    sys.exit(main())
