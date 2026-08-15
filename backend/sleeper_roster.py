"""Sleeper roster → FTF user resolution.

Sleeper rosters carry an optional ``co_owners`` array beside ``owner_id``.
Everything in FTF used to match on ``owner_id`` alone, so a co-owner's league
resolved to no team at all *and* served their own roster back to them as an
opponent. See ``docs/plans/sleeper-co-owner-rosters/scope.md``.

THE RULE (one place, so backend/mobile/web cannot drift — the predicate is
mirrored in ``mobile/src/api/sleeper.ts`` and ``web/js/app.js`` and listed in
``docs/cross-client-invariants.md``):

    a roster belongs to a user iff  user_id == owner_id  OR  user_id ∈ co_owners

A co-owner is an ALIAS of the roster's primary ``owner_id`` within that league,
never a second team. The roster's ``owner_id`` is therefore the canonical
*league identity* — the key `league_members` rows, `is_you` and every "my
roster" lookup use — while the caller's own Sleeper id stays their *account
identity* (rankings, swipes, entitlements, analytics). For a sole owner the two
are the same string, which is why every existing sole-owned path is unchanged.

Keeping ``owner_id`` canonical is what makes the league-shared
``league_members`` table single-valued: whichever co-owner logs in, the roster
lands on ONE row. Keying on the caller instead would give a 12-team league 13
member rows with one roster duplicated, and session_init's DB-member merge
would then hand the engine a phantom copy of the user's own team to trade with.
"""

from __future__ import annotations

__all__ = ["co_owner_ids", "owns_roster", "find_user_roster",
           "canonical_owner_id"]


def co_owner_ids(roster: object) -> list[str]:
    """``co_owners`` as a list of strings. ``None``/absent/garbage → ``[]``.

    Sleeper sends ``null`` for the overwhelmingly common sole-owned case and a
    list of user-id strings otherwise; ids are coerced because nothing
    guarantees the wire type stays string forever (``owner_id`` is compared
    str-wise everywhere else in the codebase for the same reason).
    """
    if not isinstance(roster, dict):
        return []
    raw = roster.get("co_owners")
    if not isinstance(raw, (list, tuple)):
        return []
    return [str(c) for c in raw if c not in (None, "")]


def owns_roster(roster: object, user_id: object) -> bool:
    """True when ``user_id`` owns or co-owns ``roster``.

    Empty/None ``user_id`` is never a match — an ownerless roster
    (``owner_id: null`` after a manager leaves) must not resolve to a caller
    with no id, which ``str(None) == str(None)`` would otherwise allow.
    """
    uid = str(user_id or "")
    if not uid or not isinstance(roster, dict):
        return False
    owner = str(roster.get("owner_id") or "")
    return uid == owner or uid in co_owner_ids(roster)


def find_user_roster(rosters: object, user_id: object) -> dict | None:
    """The roster ``user_id`` owns or co-owns, or ``None``.

    First match wins. Sleeper does not allow one user on two rosters in a
    league, so the ordering is not load-bearing.
    """
    if not isinstance(rosters, (list, tuple)):
        return None
    for r in rosters:
        if owns_roster(r, user_id):
            return r
    return None


def canonical_owner_id(rosters: object, user_id: object) -> str:
    """The caller's LEAGUE identity: the ``owner_id`` of the roster they own or
    co-own, falling back to their own id.

    The fallback covers the two cases where there is nothing to alias to — the
    user has no roster in this league, or the rosters fetch failed — and keeps
    the return value byte-identical to today's behavior for every sole owner.
    """
    hit = find_user_roster(rosters, user_id)
    if hit is not None:
        owner = str(hit.get("owner_id") or "")
        if owner:
            return owner
    return str(user_id or "")
