"""
test_profile.py — the operator's onboarding test profile.

Plan: docs/plans/onboarding-test-profile/ (design.md §7 Design B, scope.md).
A leaf: imports `database` only, never `server`. Routes and guards that use it
live in server.py (section "Onboarding test profile").

IDENTITY IS A PURE FUNCTION OF THE ID. The test profile of the real working
key X is the app user `qa_tp_X`. Nothing else marks it: a session rebuilt from
its durable row, a cron reading a table, an analytics filter — each can tell a
test profile from the id alone. The `qa_` prefix also inherits every existing
synthetic-user exclusion (analytics_queries.device_exclusion, the eval spine).
No sign-up path can produce it: Sleeper ids are numeric, account keys start
`acct_`, demo keys `demo_user_`, and Test Stages mints `qa_` + 8 HEX characters
(`t` is not hex). `server._extension_build_session` refuses the prefix unless
the switch route asks for it.

LEAGUES LIVE IN A PRIVATE NAMESPACE. A test profile may only ever enter a
league whose id is inside its own `qa_tp:X:` namespace (session_input and the
request fence in server.py enforce it). ESPN and MFL leagues get there through
the REAL production linking routes (operator ruling 2026-11-11, design.md
§10-11): those routes read the platform with the real league id and write
storage with `storage_league_id(session user, real id)` — identity for every
real user, `qa_tp:X:<real id>` for the test profile. Platform reads that start
from a stored id go back through `native_league_id`, called once in each
platform URL builder (espn_service.league_url, mfl_service.export_url /
resolve_host). Those two functions are the whole seam; a structural test
(tests/test_test_profile.py) fails if a new linking write site skips it.
ESPN/MFL opponents are stored with the platform's own synthetic ids
(`espn:…`, `mfl:…`), never a real app user. Sleeper linking stays unavailable
in a test profile: the Sleeper id IS the app identity.

THIS MODULE IS IMPORT-LIGHT: `database` is imported inside the reset
functions only, so the platform services can import the id helpers.

GATE. Allowed only when the flag `dev.test_profile` is on AND the real working
key is listed in the env var `TEST_PROFILE_ACCOUNTS` (comma-separated). The
real key is always derived server-side from the authenticated session.
"""

from __future__ import annotations

import os
import re


PROFILE_PREFIX = "qa_tp_"
LEAGUE_PREFIX = "qa_tp:"
OPPONENT_PREFIX = "qa_tpo_"
ENV_VAR = "TEST_PROFILE_ACCOUNTS"
FLAG = "dev.test_profile"
DISPLAY_NAME = "Test profile"

# Ids that are already synthetic can never own a test profile.
_SYNTHETIC_PREFIXES = ("qa_", "demo_", "test_", "device:", "espn:", "mfl:",
                       "flea:", "fleaflicker:", "sleeper:")

# A real working key: a Sleeper numeric id or `acct_<hex/uuid>`.
_REAL_ID = re.compile(r"^(?:\d+|acct_[A-Za-z0-9-]+)$")


# ── identity ───────────────────────────────────────────────────────────────

def is_test_profile_id(user_id) -> bool:
    return str(user_id or "").startswith(PROFILE_PREFIX)


def is_real_id(user_id) -> bool:
    uid = str(user_id or "")
    return bool(_REAL_ID.match(uid)) and not uid.startswith(_SYNTHETIC_PREFIXES)


def profile_id(real_id: str) -> str:
    """The test profile id of a REAL working key. Refuses anything else."""
    if not is_real_id(real_id):
        raise ValueError("not a real working key")
    return PROFILE_PREFIX + str(real_id)


def real_id_of(profile_uid) -> str | None:
    if not is_test_profile_id(profile_uid):
        return None
    real = str(profile_uid)[len(PROFILE_PREFIX):]
    return real if is_real_id(real) else None


def is_test_league_id(league_id) -> bool:
    return str(league_id or "").startswith(LEAGUE_PREFIX)


def league_prefix(profile_uid: str) -> str:
    real = real_id_of(profile_uid)
    if real is None:
        raise ValueError("not a test profile id")
    return f"{LEAGUE_PREFIX}{real}:"


def test_league_id(profile_uid: str, real_league_id: str) -> str:
    return league_prefix(profile_uid) + str(real_league_id)


def storage_league_id(user_id, real_league_id: str) -> str:
    """WRITE seam: the id a linking route stores a platform league under for
    the calling session's user. The real id itself for every non-test user
    (byte-identical); `qa_tp:X:<id>` for the test profile `qa_tp_X`."""
    if is_test_profile_id(user_id) and not is_test_league_id(real_league_id):
        return test_league_id(user_id, real_league_id)
    return real_league_id


_NAMESPACED = re.compile(r"^qa_tp:[^:]+:(.+)$")


def native_league_id(league_id):
    """READ seam: the platform's own league id for a stored id. Identity for
    anything outside the test namespace."""
    m = _NAMESPACED.match(str(league_id or ""))
    return m.group(1) if m else league_id


def owns_test_league(profile_uid, league_id) -> bool:
    try:
        return str(league_id or "").startswith(league_prefix(profile_uid))
    except ValueError:
        return False


def profile_of_league(league_id) -> str | None:
    """The test profile that owns a namespaced league id, else None."""
    m = re.match(r"^qa_tp:([^:]+):.+$", str(league_id or ""))
    return PROFILE_PREFIX + m.group(1) if m and is_real_id(m.group(1)) else None


def masked_member_id(league_id, member_id, *, own_ids=()) -> str:
    """STORAGE re-key for a league member. Identity outside the test
    namespace. Inside it: the owning profile (or any id in `own_ids` — the
    operator's own platform identity / their roster's owner) becomes the
    profile; an id already synthetic stays; every other id becomes a
    deterministic opaque `qa_tpo_<hash>`, so no real user id or real league
    id survives in a row of a test league."""
    profile = profile_of_league(league_id)
    if profile is None:
        return member_id
    mid = str(member_id or "")
    if mid == profile or mid in {str(x) for x in own_ids if x}:
        return profile
    if mid.startswith(OPPONENT_PREFIX):
        return mid
    import hashlib
    digest = hashlib.sha256(f"{profile}|{mid}".encode()).hexdigest()[:16]
    return OPPONENT_PREFIX + digest


def mask_sleeper_rosters(league_id, rosters, own_owner_id) -> list:
    """Sleeper `/rosters` rows re-keyed for a test league (owner_id,
    co_owners). `own_owner_id` is the owner_id of the operator's roster."""
    out = []
    for r in rosters or []:
        r = dict(r)
        if r.get("owner_id"):
            r["owner_id"] = masked_member_id(league_id, r["owner_id"], own_ids=(own_owner_id,))
        if r.get("co_owners"):
            r["co_owners"] = [masked_member_id(league_id, c, own_ids=(own_owner_id,))
                              for c in r["co_owners"]]
        r["league_id"] = league_id
        out.append(r)
    return out


def mask_sleeper_users(league_id, users, own_owner_id) -> list:
    """Sleeper `/users` rows re-keyed for a test league (user_id only)."""
    out = []
    for u in users or []:
        u = {k: v for k, v in dict(u).items() if k in ("user_id", "username", "display_name")}
        u["user_id"] = masked_member_id(league_id, u.get("user_id"), own_ids=(own_owner_id,))
        out.append(u)
    return out


# ── outbound chokepoint ────────────────────────────────────────────────────
# One predicate every path that can reach another person passes (push send,
# inbox row, queued notification, match, referral credit, platform write).
# Blocked when the action touches the test world — the acting request is a
# test profile, the league is namespaced, or the payload names a test id —
# and the recipient is anyone but that test profile itself.

import contextvars

#: The acting session's app user id for the current request (server.py sets
#: it in a before_request hook and clears it at teardown).
ACTOR: contextvars.ContextVar = contextvars.ContextVar("test_profile_actor", default=None)

#: Every blocked delivery, for tests and the runbook's audit (bounded).
BLOCKED: list = []


class OutboundBlocked(Exception):
    """Raised by a writer that must not create a cross-user record."""


_OPPONENT_ID = re.compile(r"^qa_tpo_[0-9a-f]{16}$")


def is_test_world_id(value) -> bool:
    """An exact test-world id: a test profile `qa_tp_<real key>`, a namespaced
    league `qa_tp:<real key>:<id>` or a re-keyed opponent `qa_tpo_<16 hex>`.
    Structural, never a substring match, so a real league name or username
    that happens to contain the text is not one (review L1)."""
    v = str(value or "")
    return (real_id_of(v) is not None or profile_of_league(v) is not None
            or bool(_OPPONENT_ID.match(v)))


def _id_field(key) -> bool:
    k = str(key).lower()
    return k == "id" or k.endswith("_id") or k.endswith("_ids") or k in ("user", "league")


def names_test_id(obj) -> bool:
    """Does an id FIELD of this payload (a bare id, or a dict/list holding
    `*_id` / `*_ids` fields at any depth) carry a test-world id? Free text —
    titles, bodies, names — is never inspected."""
    if isinstance(obj, dict):
        return any((_id_field(k) and _value_names_test_id(v))
                   or (isinstance(v, (dict, list, tuple)) and names_test_id(v))
                   for k, v in obj.items())
    if isinstance(obj, (list, tuple, set)):
        return any(names_test_id(x) for x in obj)
    return is_test_world_id(obj)


def _value_names_test_id(v) -> bool:
    if isinstance(v, (list, tuple, set)):
        return any(is_test_world_id(x) for x in v)
    return is_test_world_id(v)


def outbound_blocked(recipient, *, league_id=None, payload=None, kind="") -> bool:
    """`payload`: a bare id or a structured dict/list (never pre-serialized
    JSON); only its id fields are inspected."""
    actor = ACTOR.get()
    rec = str(recipient or "")
    touched_by_test = (
        is_test_profile_id(actor)
        or is_test_league_id(league_id)
        or names_test_id(payload)
        or is_test_profile_id(rec) or rec.startswith(OPPONENT_PREFIX)
    )
    if not touched_by_test:
        return False
    owner = actor if is_test_profile_id(actor) else profile_of_league(league_id)
    if is_test_profile_id(rec) and (owner is None or rec == owner):
        return False          # the test profile's own inbox
    if len(BLOCKED) < 1000:
        BLOCKED.append({"kind": kind, "recipient": rec})
    return True


# ── write fence (default-deny at the database) ─────────────────────────────
# Review M1: request-shape scanning alone cannot be complete, so every
# INSERT/UPDATE/DELETE executed while a test profile is the request's ACTOR is
# checked where league ids finally land — the bound values of the statement's
# own `*league_id` columns. Any league id outside the actor's namespace is
# refused. Real requests (ACTOR not a test profile) pay one contextvar read.

class TestProfileWriteRefused(Exception):
    """A test-profile request tried to write under a league it does not own."""


def _bound_values(stmt, multiparams, params) -> list[tuple[str, object]]:
    out = []
    try:
        out += list(stmt.compile().params.items())
    except Exception:
        pass

    def walk(x):
        if isinstance(x, dict):
            out.extend(x.items())
        elif isinstance(x, (list, tuple)):
            for y in x:
                walk(y)
    walk(multiparams)
    walk(params)
    return out


def check_write(stmt, multiparams=(), params=None) -> None:
    actor = ACTOR.get()
    if not is_test_profile_id(actor):
        return
    from sqlalchemy.sql.dml import UpdateBase
    if not isinstance(stmt, UpdateBase):
        return
    table = getattr(stmt, "table", None)
    names = {c.name for c in getattr(table, "columns", ()) if c.name.endswith("league_id")}
    if not names:
        return
    for key, value in _bound_values(stmt, multiparams, params):
        if re.sub(r"_\d+$", "", str(key)) not in names:
            continue
        for v in (value if isinstance(value, (list, tuple, set)) else [value]):
            if v in (None, "", "no_league"):
                continue
            if not owns_test_league(actor, v) and not str(v) == league_prefix(actor):
                raise TestProfileWriteRefused(f"{getattr(table, 'name', '?')}.{key}")


# ── gate ───────────────────────────────────────────────────────────────────

def allowed_accounts() -> frozenset[str]:
    raw = os.environ.get(ENV_VAR, "") or ""
    return frozenset(x.strip() for x in raw.split(",") if x.strip())


def enabled_for(real_id, is_enabled) -> bool:
    """The whole gate: flag on AND the real key allow-listed. `is_enabled` is
    passed in so server.py's (monkeypatchable) flag reader decides."""
    real = str(real_id or "")
    return bool(is_real_id(real) and is_enabled(FLAG) and real in allowed_accounts())


# ── reset ──────────────────────────────────────────────────────────────────

# Column names that hold an app-user id. Derived from database.py: every
# column whose name ends in `user_id`, plus these (review 2026-11-12 found the
# last six missing). tests/test_test_profile.py enumerates the schema
# independently and fails on any identity-like column that is neither here
# nor listed there as not user-keyed.
_EXTRA_USER_COLUMNS = frozenset({"owner_id", "actor", "user_a_id", "user_b_id",
                                 "created_by", "recorded_by", "assigned_by",
                                 "creator", "username"})


def _is_user_column(name: str) -> bool:
    return name.endswith("user_id") or name in _EXTRA_USER_COLUMNS


def reset_scope() -> list[tuple[str, list[str], list[str]]]:
    """(table, user-id columns, league-id columns) for every table in the
    schema that has either — the reset's whole reach, derived, not listed."""
    from . import database as db
    scope = []
    for t in db.metadata.sorted_tables:
        ucols = [c.name for c in t.columns if _is_user_column(c.name)]
        lcols = [c.name for c in t.columns if c.name.endswith("league_id")]
        if ucols or lcols:
            scope.append((t.name, ucols, lcols))
    return scope


def profile_league_ids(profile_uid: str, extra=()) -> set[str]:
    """Every namespaced league the profile has: a namespaced id only comes
    into existence as a `leagues` row (linking writes one, a first Sleeper
    session init upserts one) or a `league_members` row. Both tables are
    small; this is the reset's only prefix scan."""
    from sqlalchemy import select

    from . import database as db
    prefix = league_prefix(profile_uid)
    ids = {str(x) for x in extra if owns_test_league(profile_uid, x)}
    with db.engine.connect() as conn:
        for col in (db.leagues_table.c.sleeper_league_id, db.league_members_table.c.league_id):
            ids.update(str(x) for x in conn.execute(
                select(col).where(col.startswith(prefix, autoescape=True)).distinct()).scalars())
    return ids


def reset_profile(profile_uid: str, extra_league_ids=()) -> dict[str, int]:
    """Delete every row the test profile can have written: any row whose
    user-id column equals `profile_uid`, or whose league-id column is one of
    the profile's own namespaced leagues. Refuses any id that is not a test
    profile id.

    Cost on Postgres (review L4): every predicate is an equality or an IN
    list, so indexed user/league columns are used; unindexed ones are scanned
    once. Each table is its own short transaction, so no lock outlives one
    table's DELETE and only the deleted rows are ever locked. Re-running is
    harmless."""
    from sqlalchemy import delete, or_

    from . import database as db
    real = real_id_of(profile_uid)
    if real is None or profile_id(real) != profile_uid:
        raise ValueError("reset refused: not a test profile id")
    leagues = sorted(profile_league_ids(profile_uid, extra_league_ids))
    counts: dict[str, int] = {}
    tables = {t.name: t for t in db.metadata.sorted_tables}
    for name, ucols, lcols in reversed(reset_scope()):
        t = tables[name]
        preds = [t.c[c] == profile_uid for c in ucols]
        if leagues:
            preds += [t.c[c].in_(leagues) for c in lcols]
        if not preds:
            continue
        with db.engine.begin() as conn:
            n = conn.execute(delete(t).where(or_(*preds))).rowcount or 0
        if n:
            counts[name] = n
    return counts
