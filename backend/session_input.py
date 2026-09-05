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


def resolve_session_input(sess, body, sleeper_get):
    """Read membership from Sleeper or an already imported platform snapshot."""
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
        name, platform = row["name"], row["platform"]
        owner_id = uid
    else:
        if not lid.isdigit() or uid.startswith("acct_"):
            raise SessionInputError("league_membership_required", 403)
        try:
            base = f"https://api.sleeper.app/v1/league/{lid}"
            rosters = sleeper_get(base + "/rosters")
            users = sleeper_get(base + "/users")
            meta = sleeper_get(base)
            if not isinstance(rosters, list) or not isinstance(users, list) or not isinstance(meta, dict):
                raise ValueError("invalid Sleeper response")
            mine_roster = find_user_roster(rosters, uid)
            if mine_roster is None or not mine_roster.get("owner_id"):
                raise SessionInputError("league_membership_required", 403)
            user_map = {str(u["user_id"]): u for u in users}
            if uid in user_map:
                profile = user_map[uid]
            members = [dict(user_id=str(r["owner_id"]),
                            username=(user_map.get(str(r["owner_id"]), {}).get("display_name")
                                      or user_map.get(str(r["owner_id"]), {}).get("username")
                                      or str(r["owner_id"])),
                            player_ids=[str(p) for p in (r.get("players") or [])])
                       for r in rosters if r.get("owner_id")]
            owner_id = str(mine_roster["owner_id"])
            mine = next(m for m in members if m["user_id"] == owner_id)
            name, platform = meta.get("name") or lid, "sleeper"
        except SessionInputError:
            raise
        except Exception as exc:
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
