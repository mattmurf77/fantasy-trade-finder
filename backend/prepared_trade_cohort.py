"""Quiet, dependency-injected preparation discovery; never session admission.

``ready`` here means a fresh team binding, NOT a generated/prepared inventory.
Readers receive detached rows and must not turn provider failure into empty data.
No database, account, session, notification or ranking writes belong in this module.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from typing import Callable, Iterable, Mapping

from .sleeper_roster import owns_roster

VERSION = "prepared-cohort-1"
PLATFORMS = frozenset({"sleeper", "espn", "mfl", "fleaflicker"})
FORMATS = frozenset({"1qb_ppr", "sf_tep"})
VERIFIED = frozenset({"sleeper", "apple", "google", "mfl_login"})
SOURCE_REASONS = frozenset({"source_unavailable", "source_auth_failed", "source_invalid",
    "source_stale", "source_identity_mismatch", "source_unmapped_players",
    "source_credentials_missing", "source_crosswalk_missing", "unsupported_platform"})


class SourceUnavailable(Exception):
    """Safe classification only. Raw provider messages/credentials never escape."""
    def __init__(self, reason: str):
        self.reason = reason if reason in SOURCE_REASONS else "source_unavailable"
        super().__init__(self.reason)


def _id(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return ""
    return str(value).strip()


def _clock(now):
    value = now() if callable(now) else now
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(timezone.utc)


def _safe_json(value):
    """Detached JSON data, never credentials. Do not stringify arbitrary objects."""
    def check(node):
        if isinstance(node, dict):
            for key, item in node.items():
                if not isinstance(key, str) or any(secret in key.lower() for secret in
                    ("password", "cookie", "token", "secret", "encrypted", "espn_s2", "swid")):
                    raise SourceUnavailable("source_invalid")
                check(item)
        elif isinstance(node, list):
            for item in node:
                check(item)
        elif node is not None and type(node) not in (str, int, float, bool):
            raise SourceUnavailable("source_invalid")
    check(value)
    try:
        return json.loads(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError, OverflowError):
        raise SourceUnavailable("source_invalid") from None


def _source(raw, league, *, season, now, max_age):
    if not isinstance(raw, dict):
        raise SourceUnavailable("source_invalid")
    lid = _id(league.get("sleeper_league_id"))
    platform = league.get("platform") or "sleeper"
    if (_id(raw.get("league_id")) != lid or raw.get("platform") != platform
            or _id(raw.get("season")) != str(season)):
        raise SourceUnavailable("source_identity_mismatch")
    try:
        stamp = datetime.fromisoformat(raw["observed_at"].replace("Z", "+00:00"))
        age = (_clock(now) - stamp).total_seconds() if stamp.tzinfo else float("inf")
    except (KeyError, TypeError, AttributeError, ValueError, OverflowError):
        raise SourceUnavailable("source_invalid") from None
    if age < -5 or age > max_age:
        raise SourceUnavailable("source_stale")
    teams = raw.get("teams")
    if not isinstance(teams, list):
        raise SourceUnavailable("source_invalid")
    seen, owners, result = set(), set(), []
    for team in teams:
        if not isinstance(team, dict):
            raise SourceUnavailable("source_invalid")
        tid, owner = _id(team.get("team_id")), _id(team.get("owner_id"))
        players, coowners = team.get("player_ids"), team.get("co_owners", [])
        if (not tid or tid in seen or not isinstance(players, list)
                or not isinstance(coowners, list) or any(not _id(p) for p in players)
                or any(not _id(u) for u in coowners) or len(set(map(_id, players))) != len(players)):
            raise SourceUnavailable("source_invalid")
        if platform == "sleeper" and owner and owner in owners:
            raise SourceUnavailable("source_invalid")
        inactive = {key: team.get(key, []) for key in ("reserve", "taxi")}
        if any(not isinstance(ids, list) or any(not _id(p) for p in ids)
               or len(set(map(_id, ids))) != len(ids) for ids in inactive.values()):
            raise SourceUnavailable("source_invalid")
        availability_source = team.get("availability_source", "unknown")
        if availability_source not in {"observed", "unknown"}:
            raise SourceUnavailable("source_invalid")
        seen.add(tid); owners.add(owner)
        result.append({"team_id": tid, "owner_id": owner or None,
            "co_owners": list(map(_id, coowners)), "player_ids": list(map(_id, players)),
            "name": str(team.get("name") or "Team"),
            **{key: list(map(_id, ids)) for key, ids in inactive.items()},
            "availability_source": availability_source})
    metadata, limitations = raw.get("metadata", {}), raw.get("limitations", [])
    if not isinstance(metadata, dict) or not isinstance(limitations, list) or any(type(x) is not str for x in limitations):
        raise SourceUnavailable("source_invalid")
    safe = {"league_id": lid, "platform": platform, "season": str(season),
        "observed_at": stamp.isoformat(), "teams": result,
        "metadata": metadata, "limitations": limitations}
    for field in ("traded_picks", "drafts", "future_picks"):
        value = raw.get(field, [])
        if not isinstance(value, list):
            raise SourceUnavailable("source_invalid")
        safe[field] = value
    safe = _safe_json(safe)
    # Observation time is freshness evidence, not a change to roster identity.
    identity = {k: v for k, v in safe.items() if k != "observed_at"}
    safe["fingerprint"] = hashlib.sha256(json.dumps(identity, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return safe


def discover_targets(*, users: Iterable[Mapping], leagues: Iterable[Mapping],
        read_source: Callable, season: int | str, now, accounts=(), members=(),
        bindings=(), max_source_age_seconds: float = 300) -> dict:
    """Resolve existing app actors against known leagues, with exhaustive skips.

    Pass one existing league to re-resolve one target at claim/adoption. Users
    need a recognized verified_via; opponent/import-only rows are never actors.
    Explicit imported bindings: {user_id, league_id, platform, team_id,
    source: 'verified_import'}. A legacy importer/my-team binding additionally
    requires that importer still be a retained own member of the league.
    Coverage is private; ``counts`` is safe aggregate operational telemetry.
    """
    if type(max_source_age_seconds) not in (float, int) or not 0 < max_source_age_seconds <= 3600:
        raise ValueError("invalid source age bound")
    _clock(now)
    users, leagues, accounts, members, bindings = deepcopy(tuple(map(list,
        (users, leagues, accounts, members, bindings))))
    coverage, targets = [], []
    def record(reason, *, uid=None, lid=None, status="skipped"):
        coverage.append({"user_id": uid, "league_id": lid, "status": status, "reason": reason})
    aliases = {"acct_" + _id(a.get("account_id")): _id(a.get("sleeper_user_id"))
        for a in accounts if _id(a.get("account_id")) and _id(a.get("sleeper_user_id"))}
    actors = {}
    for row in users:
        uid = _id(row.get("sleeper_user_id"))
        if not uid:
            record("invalid_actor"); continue
        if row.get("deleted") or row.get("deleted_at"):
            record("deleted_actor", uid=uid); continue
        if uid.startswith(("espn:", "mfl:", "flea:", "fleaflicker:", "demo_user_", "test_")):
            record("opponent_only_actor", uid=uid); continue
        if aliases.get(uid) and aliases[uid] != uid:
            record("superseded_account_alias", uid=uid); continue
        if row.get("verified_via") not in VERIFIED:
            record("unverified_actor", uid=uid); continue
        if uid in actors and actors[uid] != row:
            raise ValueError("conflicting actor rows")
        actors[uid] = row
    member_pairs = {(_id(m.get("league_id")), _id(m.get("user_id"))) for m in members}
    seen_leagues, covered_actors, reads = {}, set(), 0
    for league in leagues:
        lid, platform = _id(league.get("sleeper_league_id")), league.get("platform") or "sleeper"
        if not lid:
            record("invalid_league"); continue
        if lid in seen_leagues:
            if seen_leagues[lid] != league:
                raise ValueError("conflicting league rows")
            continue
        seen_leagues[lid] = league
        if platform not in PLATFORMS:
            record("unsupported_platform", lid=lid); continue
        if _id(league.get("season") or league.get("espn_season") or league.get("platform_season")) != str(season):
            record("noncurrent_season", lid=lid); continue
        scoring = league.get("scoring_format") or league.get("default_scoring")
        scoring_basis = "saved" if scoring is not None else "native_default"
        # The database contract explicitly defines NULL as native 1QB PPR.
        # An invalid nonempty saved value still fails, never guessed from names.
        if scoring is None:
            scoring = "1qb_ppr"
        if scoring not in FORMATS:
            record("unsupported_format", lid=lid); continue
        try:
            reads += 1
            fresh = _source(read_source(deepcopy(league)), league, season=season,
                now=now, max_age=max_source_age_seconds)
        except SourceUnavailable as exc:
            record(exc.reason, lid=lid, status="error"); continue
        except Exception:
            record("source_unavailable", lid=lid, status="error"); continue
        teams = fresh["teams"]
        if not teams:
            record("empty_league", lid=lid); continue
        imported = {}
        if platform != "sleeper":
            for uid in actors:
                choices = {_id(b.get("team_id")) for b in bindings
                    if _id(b.get("user_id")) == uid and _id(b.get("league_id")) == lid
                    and b.get("platform") == platform and b.get("source") == "verified_import"}
                if (_id(league.get("user_id")) == uid and (lid, uid) in member_pairs):
                    choices.add(_id(league.get("espn_my_team_id") if platform == "espn"
                        else league.get("platform_my_team")))
                choices.discard("")
                if choices:
                    imported[uid] = choices
        for uid in sorted(actors):
            if platform == "sleeper":
                matches = [t for t in teams if owns_roster(t, uid)]
                if not matches:
                    if (lid, uid) in member_pairs or _id(league.get("user_id")) == uid:
                        record("no_current_team_binding", uid=uid, lid=lid); covered_actors.add(uid)
                    continue
                evidence = "fresh_owner_or_coowner"
            else:
                choices = imported.get(uid, set())
                if not choices:
                    if (lid, uid) in member_pairs or _id(league.get("user_id")) == uid:
                        record("missing_platform_binding", uid=uid, lid=lid); covered_actors.add(uid)
                    continue
                matches = [t for t in teams if t["team_id"] in choices]
                if len(choices) != 1:
                    matches = [None, None]
                evidence = "retained_verified_import"
            covered_actors.add(uid)
            if len(matches) != 1:
                record("ambiguous_team_binding" if len(matches) > 1 else "no_current_team_binding", uid=uid, lid=lid); continue
            own = matches[0]
            league_uid = own["owner_id"] if platform == "sleeper" else uid
            if not league_uid:
                record("ownerless_team", uid=uid, lid=lid); continue
            if not own["player_ids"]:
                record("empty_roster", uid=uid, lid=lid); continue
            opponents = []
            for other in teams:
                if other["team_id"] == own["team_id"]:
                    continue
                other_uid = other["owner_id"]
                if platform != "sleeper":
                    bound = [u for u, ts in imported.items() if ts == {other["team_id"]}]
                    prefix = "flea" if platform == "fleaflicker" else platform
                    other_uid = bound[0] if len(bound) == 1 else (other_uid or
                        f"{prefix}:{lid}.{'f' if platform == 'mfl' else 't'}{other['team_id']}")
                if not other_uid:
                    continue
                opponents.append({"user_id": other_uid, "team_id": other["team_id"],
                    "player_ids": list(other["player_ids"]), "name": other["name"]})
            if not any(o["player_ids"] for o in opponents):
                record("missing_opponents", uid=uid, lid=lid); continue
            targets.append({"user_id": uid, "league_id": lid, "league_user_id": league_uid,
                "platform": platform, "scoring_format": scoring, "scoring_basis": scoring_basis,
                "native_team_key": own["team_id"],
                "user_roster": list(own["player_ids"]), "opponents": opponents,
                "source": deepcopy(fresh), "binding_evidence": evidence})
            record("resolved", uid=uid, lid=lid, status="ready")
    for uid in sorted(set(actors) - covered_actors):
        record("no_known_linked_team", uid=uid)
    targets.sort(key=lambda t: (t["user_id"], t["league_id"], t["scoring_format"]))
    reasons = Counter(c["reason"] for c in coverage)
    return {"targets": targets, "coverage": coverage, "counts": {
        "eligible_actors": len(actors), "known_leagues": len(seen_leagues), "source_reads": reads,
        "resolved_targets": len(targets), "coverage_rows": len(coverage),
        "by_reason": dict(sorted(reasons.items())),
        "discovery_complete": not any(c["status"] == "error" for c in coverage)}}


def read_league_source(league, *, sleeper_get=None, credential_reader=None,
        decrypt_token=None, crosswalk=None, now, opener=None):
    """Refresh ONE known league via existing quiet adapters. No reconnect writes.

    ``credential_reader(platform, importer_user_id)`` returns existing encrypted
    credential records; ``decrypt_token(ciphertext)`` remains the secure adapter.
    Sleeper reader accepts a full public API URL and must raise on failed reads.
    No raw credentials or provider error messages are retained in the result.
    """
    league = deepcopy(league)
    lid = _id(league.get("sleeper_league_id"))
    platform = league.get("platform") or "sleeper"
    season = _id(league.get("season") or league.get("espn_season") or league.get("platform_season"))
    result = {"league_id": lid, "platform": platform, "season": season,
        "teams": [], "metadata": {}, "traded_picks": [], "drafts": [],
        "future_picks": [], "limitations": []}
    try:
        if not lid or not season:
            raise SourceUnavailable("source_invalid")
        if platform == "sleeper":
            if sleeper_get is None:
                raise SourceUnavailable("source_unavailable")
            base = f"https://api.sleeper.app/v1/league/{lid}"
            meta, rosters = sleeper_get(base), sleeper_get(base + "/rosters")
            users = sleeper_get(base + "/users")
            picks, drafts = sleeper_get(base + "/traded_picks"), sleeper_get(base + "/drafts")
            if (not isinstance(meta, dict) or _id(meta.get("league_id")) != lid
                    or _id(meta.get("season")) != season or not isinstance(rosters, list)
                    or not isinstance(users, list) or not isinstance(picks, list) or not isinstance(drafts, list)
                    or any(not isinstance(u, dict) or not _id(u.get("user_id")) for u in users)):
                raise SourceUnavailable("source_invalid")
            names = {_id(u["user_id"]): str(u.get("display_name") or u.get("username") or u["user_id"])
                for u in users}
            result["teams"] = [{"team_id": _id(r.get("roster_id")),
                "owner_id": r.get("owner_id"), "co_owners": r.get("co_owners") or [],
                "player_ids": r.get("players") or [], "name": names.get(_id(r.get("owner_id")), _id(r.get("owner_id")) or "Team"),
                "reserve": r.get("reserve") or [], "taxi": r.get("taxi") or [],
                "availability_source": "observed",
                } for r in rosters]
            result["metadata"] = {k: meta[k] for k in ("name", "settings", "scoring_settings",
                "roster_positions", "status", "total_rosters", "draft_id") if k in meta}
            result["traded_picks"], result["drafts"] = picks, drafts
        elif platform in {"espn", "mfl", "fleaflicker"}:
            if crosswalk is None:
                raise SourceUnavailable("source_crosswalk_missing")
            auth = league.get("espn_auth") if platform == "espn" else league.get("platform_auth")
            credential = {}
            if auth == "cookie":
                if credential_reader is None or decrypt_token is None:
                    raise SourceUnavailable("source_credentials_missing")
                credential = credential_reader(platform, _id(league.get("user_id"))) or {}
                if not credential:
                    raise SourceUnavailable("source_credentials_missing")
            if platform == "espn":
                from . import espn_service as provider
                encrypted = credential.get("espn_s2_encrypted")
                if auth == "cookie" and (not encrypted or not credential.get("swid")):
                    raise SourceUnavailable("source_credentials_missing")
                raw = provider.fetch_league(lid, int(season), espn_s2=decrypt_token(encrypted) if encrypted else None,
                    swid=credential.get("swid"), _opener=opener)
                if not isinstance(raw, dict) or not isinstance(raw.get("teams"), list):
                    raise SourceUnavailable("source_invalid")
                parsed = provider.parse_league(raw)
                if _id(parsed.get("season")) != season:
                    raise SourceUnavailable("source_identity_mismatch")
                if credential and _id(league.get("espn_my_team_id")):
                    mine = [t for t in parsed["teams"] if _id(t.team_id) == _id(league["espn_my_team_id"])]
                    normalize = lambda value: str(value or "").strip("{}").lower()
                    if (len(mine) != 1 or not getattr(mine[0], "owner_swid", None)
                            or normalize(mine[0].owner_swid) != normalize(credential["swid"])):
                        raise SourceUnavailable("source_identity_mismatch")
                mapped = provider.map_rosters(parsed["teams"], crosswalk)
                # Public provider owner identifiers already form the app's
                # synthetic member key. They are not the saved credential;
                # retain exact identity for boards/likes/prefs, never cookie data.
                result["teams"] = [{"team_id": str(t.team_id), "owner_id":
                    f"espn:{t.owner_swid}" if getattr(t, "owner_swid", None) else f"espn:{lid}.t{t.team_id}",
                    "co_owners": [], "player_ids": mapped["rosters"].get(t.team_id, []),
                    "name": getattr(t, "owner_display", None) or t.name} for t in parsed["teams"]]
                result["metadata"] = {"name": parsed["name"], "settings": raw.get("settings") or {}}
                result["limitations"].append("platform_pick_ledger_not_provided")
            elif platform == "mfl":
                from . import mfl_service as provider
                encrypted = credential.get("cookie_encrypted")
                if auth == "cookie" and not encrypted:
                    raise SourceUnavailable("source_credentials_missing")
                host = league.get("platform_host")
                if not host:
                    host = provider.resolve_host(lid, int(season), _opener=opener)
                raw = provider.fetch_league_bundle(lid, int(season), host,
                    cookie=decrypt_token(encrypted) if encrypted else None, _opener=opener)
                if (not isinstance(raw, dict) or not isinstance(raw.get("league"), dict)
                        or not isinstance(raw.get("rosters"), dict)
                        or not isinstance(raw["rosters"].get("rosters"), dict)
                        or not isinstance(raw.get("futureDraftPicks"), dict)
                        or "futureDraftPicks" not in raw["futureDraftPicks"]):
                    raise SourceUnavailable("source_invalid")
                parsed = provider.parse_bundle(raw)
                mapped = provider.map_franchises(parsed, crosswalk)
                result["teams"] = [{"team_id": str(t["franchise_id"]), "owner_id": None, "co_owners": [],
                    "player_ids": mapped["rosters"].get(t["franchise_id"], []), "name": t["name"]} for t in parsed["franchises"]]
                result["future_picks"] = parsed["future_picks"]
                result["metadata"] = {"name": parsed["name"], "rules": raw.get("rules") or {}}
                result["limitations"].append("platform_season_bound_by_requested_endpoint")
            else:
                from . import fleaflicker_service as provider
                raw = provider.fetch_league_bundle(lid, _opener=opener)
                if (not isinstance(raw, dict) or not isinstance(raw.get("rosters"), dict)
                        or not isinstance(raw["rosters"].get("rosters"), list)):
                    raise SourceUnavailable("source_invalid")
                parsed = provider.parse_bundle(raw)
                mapped = provider.map_teams(parsed, crosswalk)
                result["teams"] = [{"team_id": str(t["team_id"]), "owner_id": None, "co_owners": [],
                    "player_ids": mapped["rosters"].get(t["team_id"], []), "name": t["name"]} for t in parsed["teams"]]
                result["metadata"] = {"name": parsed["name"]}
                result["limitations"].extend(["platform_pick_ledger_not_provided", "platform_season_not_attested"])
            if _id(parsed.get("league_id")) != lid:
                raise SourceUnavailable("source_identity_mismatch")
            if not isinstance(mapped.get("report"), dict) or not isinstance(mapped["report"].get("unmatched"), list):
                raise SourceUnavailable("source_invalid")
            if mapped["report"]["unmatched"]:
                raise SourceUnavailable("source_unmapped_players")
        else:
            raise SourceUnavailable("unsupported_platform")
        result["observed_at"] = _clock(now).isoformat()
        return _source(result, league, season=season, now=now, max_age=300)
    except SourceUnavailable:
        raise
    except Exception as exc:
        raise SourceUnavailable("source_auth_failed" if getattr(exc, "kind", None) == "auth"
            else "source_unavailable") from None
