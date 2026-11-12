"""Authoritative league input for verified session initialization.

Client snapshots remain accepted on the wire for older clients, but never
establish identity, league membership, profiles, or persisted rosters.
"""
from . import database as db
from .sleeper_roster import find_user_roster


class SessionInputError(ValueError):
    def __init__(self, error, status):
        self.error = error
        self.status = status
        super().__init__(error)


def resolve_session_input(sess, body, sleeper_get, raw=None, sleeper_identity=None):
    """Read membership from Sleeper or an already imported platform snapshot.

    S0: when `raw` is a dict, a successful Sleeper read fills it with the raw
    `rosters` list, the `meta` dict and `fetch_started_at`, so the session-init
    daemon reuses them instead of re-reading Sleeper (D-178). A failed Sleeper
    read is recorded in `league_roster_state` (last good rows kept).

    `sleeper_identity` is server._sleeper_identity(sess): the session's own
    user id for every real session (so this function is unchanged for them),
    the real account's Sleeper id for the onboarding test profile. It is used
    ONLY to read Sleeper; every id this function returns is re-keyed through
    test_profile.masked_member_id, which is the identity outside a test
    namespace.
    """
    if not sess:
        raise SessionInputError("session_expired", 401)
    if not sess.get("verified") or sess.get("is_demo"):
        raise SessionInputError("verification_required", 403)
    uid = str(sess.get("user_id") or "")
    if not body.get("user_id"):
        raise SessionInputError("missing_user_id", 400)
    if not uid or str(body["user_id"]) != uid:
        raise SessionInputError("identity_mismatch", 403)
    lid = body.get("league_id")
    if not isinstance(lid, str) or not lid:
        raise SessionInputError("missing_league_id", 400)
    profile = {key: sess.get(key) for key in ("username", "display_name", "avatar")}
    from .accounts import get_user_profile
    profile.update(get_user_profile(uid) or {})
    if lid == "no_league" and sess.get("account_only"):
        return dict(user_id=uid, league_id=lid, league_name="No league linked",
                    league_user_id=uid, league_display_name=profile.get("display_name") or uid,
                    user_player_ids=[], opponent_rosters=[], platform="none", **{
                        key: profile.get(key) for key in ("username", "display_name", "avatar")})

    # Onboarding test profile (backend/test_profile.py): a test profile only
    # ever enters leagues in its OWN namespace, never a real league, and nobody
    # else can enter one. A namespaced ESPN/MFL league is read like any
    # imported league; a namespaced Sleeper league is read live below.
    from . import test_profile as tp
    is_test_league = tp.is_test_league_id(lid)
    if tp.is_test_profile_id(uid) or is_test_league:
        if not tp.owns_test_league(uid, lid):
            raise SessionInputError("league_membership_required", 403)

    # Platform imports bind the caller's working identity to one stored team.
    # Native numeric IDs must be checked before the Sleeper numeric-ID path.
    if db.is_linked_platform_league(lid):
        members = db.load_league_members(lid)
        mine = next((m for m in members if str(m["user_id"]) == uid), None)
        if mine is None:
            raise SessionInputError("league_membership_required", 403)
        with db.engine.connect() as conn:
            row = conn.execute(db.select(db.leagues_table).where(
                db.leagues_table.c.sleeper_league_id == lid)).mappings().first()
        name, platform = row["name"], row["platform"] or "sleeper"
        owner_id = uid
    else:
        native = tp.native_league_id(lid)          # identity for a real id
        sleeper_uid = sleeper_identity or uid      # identity for a real session
        if not native.isdigit() or uid.startswith("acct_"):
            raise SessionInputError("league_membership_required", 403)
        from .roster_refresh import fetch_started_at, record_failure
        started = fetch_started_at()
        try:
            base = f"https://api.sleeper.app/v1/league/{native}"
            rosters = sleeper_get(base + "/rosters")
            users = sleeper_get(base + "/users")
            meta = sleeper_get(base)
            if not isinstance(rosters, list) or not isinstance(users, list) or not isinstance(meta, dict):
                raise ValueError("invalid Sleeper response")
            mine_roster = find_user_roster(rosters, sleeper_uid)
            if mine_roster is None or not mine_roster.get("owner_id"):
                raise SessionInputError("league_membership_required", 403)
            user_map = {str(u["user_id"]): u for u in users}
            if sleeper_uid in user_map and not tp.is_test_profile_id(uid):
                profile = user_map[sleeper_uid]
            own = str(mine_roster["owner_id"])
            members = [dict(user_id=tp.masked_member_id(lid, str(r["owner_id"]), own_ids=(own,)),
                            username=(user_map.get(str(r["owner_id"]), {}).get("display_name")
                                      or user_map.get(str(r["owner_id"]), {}).get("username")
                                      or tp.masked_member_id(lid, str(r["owner_id"]), own_ids=(own,))),
                            # G-004: Sleeper can send null slots; never store "None".
                            player_ids=[str(p) for p in (r.get("players") or [])
                                        if p not in (None, "")])
                       for r in rosters if r.get("owner_id")]
            owner_id = tp.masked_member_id(lid, own, own_ids=(own,))
            mine = next(m for m in members if m["user_id"] == owner_id)
            name, platform = meta.get("name") or lid, "sleeper"
            if raw is not None:
                raw.update(rosters=(tp.mask_sleeper_rosters(lid, rosters, own)
                                    if tp.is_test_league_id(lid) else rosters),
                           meta=meta, fetch_started_at=started)
        except SessionInputError:
            raise
        except Exception as exc:
            record_failure(lid, exc)
            raise SessionInputError("league_data_unavailable", 503) from exc

    def display(member):
        return member.get("display_name") or member.get("username") or str(member["user_id"])

    return dict(user_id=uid, league_id=lid, league_name=name,
                league_user_id=owner_id, league_display_name=display(mine),
                user_player_ids=[str(p) for p in mine.get("player_ids", [])],
                opponent_rosters=[dict(user_id=str(m["user_id"]), username=display(m),
                                       player_ids=[str(p) for p in m.get("player_ids", [])])
                                  for m in members if str(m["user_id"]) != owner_id],
                platform=platform, **{key: profile.get(key) for key in
                                     ("username", "display_name", "avatar")})
