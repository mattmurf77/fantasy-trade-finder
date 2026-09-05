"""Win Now forecast foundation: immutable, provider-neutral player/week stat vectors.

Sleeper's experimental projections endpoint currently carries RotoWire revisions.
A revision timestamp is NOT evidence that this content existed historically at
that time. Only snapshots actually captured before a game can be used in replay.
No dynasty prices, rankings, or personal Elo enter this module.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Callable

SCHEMA_VERSION = 1
PROVIDER = "sleeper_weekly_experimental"
MODEL_VERSION = "player_week_normal_v1_experimental"
# Verified stat-vector fields, NOT fantasy-point aggregate columns. Unsupported
# scoring (e.g. yardage thresholds, IDP, kicking) must not silently become zero.
SUPPORTED_SCORING_KEYS = frozenset("""
pass_yd pass_td pass_int pass_2pt pass_att pass_cmp pass_inc pass_sack pass_fd
pass_cmp_40p pass_int_td rush_yd rush_td rush_2pt rush_att rush_fd rush_40p
rec rec_yd rec_td rec_2pt rec_tgt rec_fd rec_0_4 rec_5_9 rec_10_19 rec_20_29
rec_30_39 rec_40p fum fum_lost def_fum_td pr pr_td pr_yd def_kr_td def_kr_yd
bonus_rec_rb bonus_rec_wr bonus_rec_te bonus_rush_td_qb
""".split())
POSITION_BONUSES = {"bonus_rec_rb": ("RB", "rec"), "bonus_rec_wr": ("WR", "rec"),
                    "bonus_rec_te": ("TE", "rec"), "bonus_rush_td_qb": ("QB", "rush_td")}


# Sleeper retains these team-defense and kicker defaults in offense-only leagues.
# Finite lists deliberately exclude player special teams (st_*), miscellaneous
# fum_rec_td, and IDP: defensive events can also be credited to offensive players.
# Categories: https://support.sleeper.com/en/articles/3998131-what-scoring-options-are-available
KICKER_SCORING_KEYS = frozenset("""
fgm fgm_0_19 fgm_20_29 fgm_30_39 fgm_40_49 fgm_50p fgm_yds fgm_yds_over_30
fgmiss fgmiss_0_19 fgmiss_20_29 fgmiss_30_39 fgmiss_40_49 fgmiss_50p xpm xpmiss
""".split())
TEAM_DEFENSE_SCORING_KEYS = frozenset("""
blk_kick def_td ff fum_rec int sack safe qb_hit sack_yd int_ret_yd fum_ret_yd
tkl_loss tkl_ast tkl_solo tkl pass_def def_2pt def_4_and_stop
pts_allow pts_allow_0 pts_allow_1_6 pts_allow_7_13 pts_allow_14_20
pts_allow_21_27 pts_allow_28_34 pts_allow_35p
yds_allow yds_allow_0_100 yds_allow_100_199 yds_allow_200_299 yds_allow_300_349
yds_allow_350_399 yds_allow_400_449 yds_allow_450_499 yds_allow_500_549 yds_allow_550p
def_st_td def_st_ff def_st_fum_rec def_st_tkl_solo def_pr_yd
""".split())


def normalize_scoring_for_slots(scoring_settings, roster_slots):
    """Remove only known coefficients for absent kicker/team-defense slots.

    Unknown, player special-teams, IDP and bonus rules survive for the scorer to
    reject when its provider cannot model them. Never infer support from a prefix.
    Lineup validation still rejects active K/DEF/IDP slots independently.
    """
    slots = set(roster_slots)
    irrelevant = set()
    if "K" not in slots:
        irrelevant.update(KICKER_SCORING_KEYS)
    if not slots.intersection({"DEF", "DST", "D/ST"}):
        irrelevant.update(TEAM_DEFENSE_SCORING_KEYS)
    return {key: value for key, value in scoring_settings.items() if key not in irrelevant}


class ForecastValidationError(ValueError):
    """A forecast cannot support the requested scoring or horizon."""


def timestamp(value) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        parsed = datetime.fromtimestamp(value / 1000 if value > 1e11 else value, timezone.utc)
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ForecastValidationError("timestamp_timezone_required")
    return parsed.astimezone(timezone.utc)


def _iso(value):
    return timestamp(value).isoformat().replace("+00:00", "Z")


def _game_date(value):
    if not isinstance(value, str) or len(value) != 10:
        raise ForecastValidationError("invalid_game_date")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ForecastValidationError("invalid_game_date") from exc
    if parsed.strftime("%Y-%m-%d") != value:
        raise ForecastValidationError("invalid_game_date")
    return value


def content_hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ForecastValidationError(f"invalid_{name}")
    return float(value)


def import_projection_snapshot(season, weeks, forecasts, *, provider, captured_at,
                               published_at=None, supported_scoring_keys=None,
                               provenance=None, earliest_game_date=None,
                               earliest_game_dates=None, earliest_kickoff_at=None) -> dict:
    """Import external weekly forecasts without coupling downstream code to a vendor.

    Each row requires player_id, season, week, positions, stats, availability,
    and bye. Stats describe conditional-on-playing expected events; availability
    is a week-specific probability (None means unknown). Zero bye rows must be
    independently certified by the provider/caller. Optional point_stddev is a
    league-scoring-specific residual scale; absent scales use a disclosed,
    uncalibrated heuristic. An import must never backdate captured_at.

    Optional full-feed cutoff fields survive filtered snapshot reimports. Dates
    remain dates; only timezone-bearing exact kickoff timestamps become UTC.
    We retain the earliest of supplied global and row-derived evidence. Offline
    imports may omit cutoff evidence; serving policy must require it separately.
    """
    season = int(season)
    weeks = sorted(set(int(w) for w in weeks))
    if not weeks or any(w < 1 or w > 18 for w in weeks):
        raise ForecastValidationError("invalid_horizon")
    captured = _iso(captured_at)
    published = _iso(published_at) if published_at is not None else None
    if published and timestamp(published) > timestamp(captured):
        raise ForecastValidationError("publication_after_capture")
    dates = {}
    if earliest_game_dates is not None:
        if not isinstance(earliest_game_dates, dict):
            raise ForecastValidationError("invalid_cutoff_weeks")
        for key, value in earliest_game_dates.items():
            if isinstance(key, bool) or str(key) not in {str(w) for w in weeks}:
                raise ForecastValidationError("cutoff_horizon_mismatch")
            dates[int(key)] = _game_date(value)
    global_date = _game_date(earliest_game_date) if earliest_game_date is not None else None
    global_kickoff = _iso(earliest_kickoff_at) if earliest_kickoff_at is not None else None
    rows, seen = [], set()
    for raw in forecasts:
        row = dict(raw)
        pid, week = str(row["player_id"]), int(row["week"])
        if not pid or int(row["season"]) != season or week not in weeks:
            raise ForecastValidationError("forecast_horizon_mismatch")
        if (pid, week) in seen:
            raise ForecastValidationError("duplicate_player_week")
        seen.add((pid, week))
        positions = sorted(set(row.get("positions") or []))
        if not positions or any(p not in {"QB", "RB", "WR", "TE"} for p in positions):
            raise ForecastValidationError("unsupported_player_position")
        primary = row.get("primary_position") or row["positions"][0]
        if primary not in positions:
            raise ForecastValidationError("invalid_primary_position")
        row["primary_position"] = primary
        stats = {k: _number(v, "stat") for k, v in row.get("stats", {}).items()}
        available = row.get("availability")
        if available is not None:
            available = _number(available, "availability")
            if not 0 <= available <= 1:
                raise ForecastValidationError("invalid_availability")
        bye = row.get("bye", False)
        if not isinstance(bye, bool):
            raise ForecastValidationError("invalid_bye")
        if bye and (available != 0 or any(stats.values())):
            raise ForecastValidationError("nonzero_bye_projection")
        if not stats and not bye and available != 0:
            raise ForecastValidationError("missing_stat_vector")
        if row.get("point_stddev") is not None:
            row["point_stddev"] = _number(row["point_stddev"], "point_stddev")
            if row["point_stddev"] < 0:
                raise ForecastValidationError("invalid_point_stddev")
        if row.get("kickoff_at") is not None:
            row["kickoff_at"] = _iso(row["kickoff_at"])
        if row.get("game_date") is not None:
            row["game_date"] = _game_date(row["game_date"])
            if not bye:
                dates[week] = min(dates.get(week, row["game_date"]), row["game_date"])
        row.setdefault("confidence", "experimental_uncalibrated")
        row.setdefault("provenance", {"provider": str(provider)})
        row.update(player_id=pid, season=season, week=week, positions=positions,
                   stats=stats, availability=available, bye=bye)
        rows.append(row)
    rows.sort(key=lambda x: (x["week"], x["player_id"]))
    missing = sorted(set(weeks) - {r["week"] for r in rows})
    snapshot = {"schema_version": SCHEMA_VERSION, "provider": str(provider),
                "model_version": MODEL_VERSION, "season": season, "weeks": weeks,
                "captured_at": captured, "published_at": published,
                "forecasts": rows,
                "earliest_kickoff_at": min(([global_kickoff] if global_kickoff else []) +
                    [r["kickoff_at"] for r in rows if r.get("kickoff_at") and not r["bye"]], default=None),
                "earliest_game_dates": {str(w): d for w, d in sorted(dates.items())},
                "earliest_game_date": min(([global_date] if global_date else []) + list(dates.values()), default=None),
                "supported_scoring_keys": sorted(supported_scoring_keys or SUPPORTED_SCORING_KEYS),
                "supported": not missing,
                "reasons": [f"missing_forecast_week:{w}" for w in missing],
                "provenance": provenance or {},
                "quality": {"experimental": True, "calibrated": False,
                            "historical_as_of": False,
                            "availability_unknown_count": sum(r["availability"] is None for r in rows),
                            "uncertainty": "Monte Carlo error excludes projection/model uncertainty"}}
    snapshot["snapshot_id"] = content_hash(snapshot)
    return snapshot


def fetch_projection_snapshot(season, weeks, fetch_json: Callable, captured_at,
                              player_ids=None, *, bye_weeks=None) -> dict:
    """Fetch actual weekly projections; never manufacture a missing future horizon.

    fetch_json(url) is the injected transport (caller owns timeouts/test isolation).
    bye_weeks optionally maps NFL team -> independently verified bye week. An
    ADP-only placeholder is not a zero projection and is omitted as missing.
    """
    season, weeks = int(season), sorted(set(int(w) for w in weeks))
    wanted = set(map(str, player_ids)) if player_ids is not None else None
    rows, reasons, source_times, urls = [], [], [], []
    game_dates = {}
    for week in weeks:
        url = (f"https://api.sleeper.app/projections/nfl/{season}/{week}"
               "?season_type=regular&position[]=QB&position[]=RB&position[]=WR"
               "&position[]=TE&order_by=pts_ppr")
        urls.append(url)
        try:
            payload = fetch_json(url)
        except Exception:
            reasons.append(f"projection_fetch_failed:{week}")
            continue
        if not isinstance(payload, list):
            reasons.append(f"invalid_projection_response:{week}")
            continue
        for raw in payload:
            if not isinstance(raw, dict):
                reasons.append(f"invalid_projection_row:{week}")
                continue
            pid = str(raw.get("player_id", ""))
            # Week-start evidence covers the entire feed, even if no rostered
            # player appears in the first NFL game. It is a conservative DATE
            # boundary, not an invented kickoff timestamp.
            if (raw.get("category") == "proj" and str(raw.get("season")) == str(season)
                    and raw.get("week") == week and raw.get("season_type") == "regular"
                    and raw.get("game_id") and raw.get("date")):
                game_date = str(raw["date"])
                try:
                    _game_date(game_date)
                    game_dates[week] = min(game_dates.get(week, game_date), game_date)
                except ValueError:
                    reasons.append(f"invalid_game_date:{week}")
            if wanted is not None and pid not in wanted:
                continue
            player = raw.get("player") or {}
            positions = player.get("fantasy_positions") or [player.get("position")]
            if not positions or any(p not in {"QB", "RB", "WR", "TE"} for p in positions):
                continue
            if (raw.get("category") != "proj" or str(raw.get("season")) != str(season)
                    or raw.get("week") != week or raw.get("season_type") != "regular"):
                reasons.append(f"projection_horizon_mismatch:{week}")
                continue
            stats = {k: v for k, v in (raw.get("stats") or {}).items() if k in SUPPORTED_SCORING_KEYS}
            team = raw.get("team") or player.get("team")
            bye = bool(team and bye_weeks and bye_weeks.get(team) == week)
            if not bye and (not stats or not raw.get("game_id") or not raw.get("opponent")):
                continue
            updated = raw.get("updated_at") or raw.get("last_modified")
            source_time = _iso(updated) if updated else None
            if source_time:
                source_times.append(source_time)
            injury = player.get("injury_status")
            # Current IR/Out/Questionable says nothing reliable about a future
            # return week. Avoid quietly treating this as a full-season injury.
            available = 0.0 if bye else (1.0 if not injury else None)
            rows.append({"player_id": pid, "season": season, "week": week,
                         "positions": positions, "primary_position": player.get("position") if player.get("position") in positions else positions[0],
                         "stats": {} if bye else stats,
                         "availability": available, "bye": bye, "team": team,
                         "opponent": raw.get("opponent"), "game_date": raw.get("date"),
                         "source_updated_at": source_time, "injury_status": injury,
                         "confidence": "unknown_availability" if available is None else "experimental",
                         "source_company": raw.get("company"),
                         "availability_basis": "verified_bye" if bye else "current_status_only"})
    try:
        result = import_projection_snapshot(season, weeks, rows, provider=PROVIDER,
                    captured_at=captured_at, published_at=max(source_times) if source_times else None,
                    provenance={"urls": urls, "revision_is_historical_as_of": False,
                                "bye_source": "caller_verified_schedule" if bye_weeks else None},
                    earliest_game_dates=game_dates)
    except (ForecastValidationError, TypeError, ValueError, KeyError) as exc:
        return {"supported": False, "reasons": [str(exc)], "forecasts": [],
                "season": season, "weeks": weeks, "captured_at": _iso(captured_at),
                "provider": PROVIDER}
    result["reasons"] = sorted(set(result["reasons"] + reasons))
    result["supported"] = not result["reasons"]
    result["snapshot_id"] = content_hash({k: v for k, v in result.items() if k != "snapshot_id"})
    return result


def score_stat_vector(row, scoring_settings, supported_scoring_keys=None) -> float:
    """Exact linear league scoring; reject unavailable event/threshold models."""
    allowed = set(supported_scoring_keys if supported_scoring_keys is not None else SUPPORTED_SCORING_KEYS)
    result = 0.0
    for key, coefficient in scoring_settings.items():
        coefficient = _number(coefficient, "scoring_coefficient")
        if not coefficient:
            continue
        if key not in allowed:
            raise ForecastValidationError(f"unsupported_scoring:{key}")
        if key in POSITION_BONUSES:
            position, stat = POSITION_BONUSES[key]
            primary = row.get("primary_position")
            if not primary:
                positions = row.get("positions") or []
                if len(positions) != 1:
                    raise ForecastValidationError("position_bonus_requires_primary_position")
                primary = positions[0]
            # Position premiums are exact event multipliers, even when a paid
            # provider omits Sleeper's convenience bonus_* vector columns.
            events = row["stats"].get(stat, 0.0) if primary == position else 0.0
        else:
            events = row["stats"].get(key, 0.0)
        result += coefficient * events
    return result


def snapshot_freshness(snapshot, now, max_age_hours=24) -> dict:
    """Explicit clock input keeps forecast scoring/simulation replayable."""
    try:
        age = (timestamp(now) - timestamp(snapshot["captured_at"])).total_seconds() / 3600
    except (KeyError, ValueError, TypeError, OverflowError):
        return {"fresh": False, "reason": "invalid_capture_time", "age_hours": None}
    fresh = 0 <= age <= max_age_hours
    return {"fresh": fresh, "reason": None if fresh else "stale_forecast", "age_hours": age}
