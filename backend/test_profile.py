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


def outbound_blocked(recipient, *, league_id=None, payload=None, kind="") -> bool:
    actor = ACTOR.get()
    rec = str(recipient or "")
    touched_by_test = (
        is_test_profile_id(actor)
        or is_test_league_id(league_id)
        or "qa_tp" in str(payload or "")
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
# column whose name ends in `user_id`, plus these.
_EXTRA_USER_COLUMNS = frozenset({"owner_id", "actor"})


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


def reset_profile(profile_uid: str) -> dict[str, int]:
    """Delete every row the test profile can have written: any row whose
    user-id column equals `profile_uid`, or whose league-id column is inside
    the profile's own `qa_tp:X:` namespace. Refuses any id that is not a
    test profile id. One transaction."""
    from sqlalchemy import delete, or_

    from . import database as db
    real = real_id_of(profile_uid)
    if real is None or profile_id(real) != profile_uid:
        raise ValueError("reset refused: not a test profile id")
    prefix = league_prefix(profile_uid)
    counts: dict[str, int] = {}
    tables = {t.name: t for t in db.metadata.sorted_tables}
    with db.engine.begin() as conn:
        for name, ucols, lcols in reversed(reset_scope()):
            t = tables[name]
            preds = [t.c[c] == profile_uid for c in ucols]
            preds += [t.c[c].startswith(prefix, autoescape=True) for c in lcols]
            n = conn.execute(delete(t).where(or_(*preds))).rowcount or 0
            if n:
                counts[name] = n
    return counts
