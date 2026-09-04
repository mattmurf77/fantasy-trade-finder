"""Build a roster snapshot from already resolved league/provider inputs."""
from datetime import datetime, timezone

from .trade_roster import Asset, Context, Rules, Team, UNAVAILABLE


def build_context(*, viewer_id, league, players, consensus_value, startable,
                  slots, platform, raw_rosters=None, player_metadata=None,
                  outlooks=None, owned_picks=None, capacity=None,
                  availability_fresh=False, viewer_roster=None):
    """No I/O. Only Sleeper's raw slots/reserve/taxi are currently observed.

    Unknown platforms/templates remain useful shadow evidence. Fresh roster
    ownership wins over a session's stale membership; unresolved IDs are kept
    so they make coverage unknown instead of disappearing from the check.
    """
    metadata, outlooks = player_metadata or {}, outlooks or {}
    raw_by_owner = {str(r.get("owner_id")): r for r in raw_rosters or [] if r.get("owner_id")}
    known_rosters = platform == "sleeper" and bool(raw_by_owner)
    source = "observed" if platform == "sleeper" and slots else "estimated" if slots else "unknown"
    assets = {}
    for pid, p in players.items():
        position = getattr(p, "position", "") or ""
        raw = metadata.get(pid) or {}
        injury = str(raw.get("injury_status") or getattr(p, "injury_status", "") or "").upper()
        positions = raw.get("fantasy_positions") or [position]
        assets[pid] = Asset(pid, frozenset(positions), float(consensus_value(pid)),
                            startable=bool(startable(pid, p)),
                            available=injury not in UNAVAILABLE,
                            is_pick=position == "PICK")
    teams = {}
    roster_by_owner = {str(m.user_id): list(m.roster) for m in league.members}
    # Session leagues normally contain opponents ONLY (G-063). Do not
    # require the viewer to appear as a LeagueMember; their current provider
    # roster is authoritative, with session IDs only as an unknown fallback.
    roster_by_owner.setdefault(viewer_id, list(viewer_roster or []))
    for uid, fallback_roster in roster_by_owner.items():
        raw = raw_by_owner.get(uid)
        roster = [str(pid) for pid in raw.get("players") or [] if pid] if raw is not None else fallback_roster
        inactive = frozenset((raw.get("reserve") or []) + (raw.get("taxi") or [])) if raw else frozenset()
        # Picks have no active roster-slot cost, but remain part of the
        # dynasty-value delta and must belong to the sending team.
        roster += [pid for pid in (owned_picks or {}).get(uid, []) if pid not in roster]
        teams[uid] = Team(uid, tuple(roster), inactive, outlooks.get(uid) or "balanced",
                          availability_known=known_rosters and raw is not None and availability_fresh)
    uncertainties = () if availability_fresh else ("availability_stale_or_unknown",)
    return Context(viewer_id, teams, assets,
                   Rules(tuple(slots or ()), source, capacity,
                         datetime.now(timezone.utc).isoformat(), uncertainties))
