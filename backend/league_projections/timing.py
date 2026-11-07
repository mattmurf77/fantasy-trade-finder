"""Provider-native exact timing and verified full-schedule bye mapping.

Observed 2026-11-07 at api.sleeper.app/scores/nfl/regular/2026/{week}.
These endpoints are undocumented. Integration is gated separately from existing Sleeper behavior.
No networking, fantasy roster data, availability assumptions, or scoring here.
"""
from collections import Counter
from datetime import datetime, timezone
import math


class CoverageError(ValueError):
    pass


def exact_time(value):
    if not isinstance(value, str):
        raise CoverageError("invalid_offset_timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise CoverageError("invalid_offset_timestamp") from None
    if result.tzinfo is None:
        raise CoverageError("missing_timestamp_timezone")
    return result.astimezone(timezone.utc)


def validate_season_schedule(rows, *, games=272, teams=32, games_per_team=17, weeks=18):
    """Explicit modern-NFL full-season coverage contract; not universal constants.

    A complete known schedule establishes scheduled bye, not future cancellation
    outcomes. A canceled existing game is still a game and must never become bye.
    """
    if not isinstance(rows, list) or len(rows) != games:
        raise CoverageError("incomplete_season_schedule")
    by_id, appearances, per_week = {}, Counter(), Counter()
    for row in rows:
        gid, home, away, week = row.get("game_id"), row.get("home"), row.get("away"), row.get("week")
        if not isinstance(gid, str) or not gid or gid in by_id:
            raise CoverageError("invalid_or_duplicate_schedule_game")
        if not home or not away or home == away or type(week) is not int or not 1 <= week <= weeks:
            raise CoverageError("invalid_schedule_teams_or_week")
        by_id[gid] = row
        for team in (home, away):
            appearances[team] += 1
            per_week[week, team] += 1
    if len(appearances) != teams or set(appearances.values()) != {games_per_team} or max(per_week.values()) != 1:
        raise CoverageError("incomplete_or_ambiguous_team_schedule")
    return by_id


def normalize_week_games(season_schedule, score_rows, season, week, captured_at):
    """Return exact scheduled kickoff and observed phase, not a live projection.

    Start time is scheduled kickoff; has_started guards delayed/early starts.
    Score capture must be repeated or invalidated if ingestion crosses kickoff.
    """
    expected = {gid: x for gid, x in season_schedule.items() if x["week"] == week}
    if not isinstance(score_rows, list) or len(score_rows) != len(expected):
        raise CoverageError("weekly_score_schedule_coverage")
    actual = {x.get("game_id"): x for x in score_rows}
    if len(actual) != len(score_rows) or set(actual) != set(expected):
        raise CoverageError("weekly_score_schedule_game_id_mismatch")
    captured = exact_time(captured_at)
    result = {}
    for gid, raw in actual.items():
        m, sched = raw.get("metadata") or {}, expected[gid]
        if (str(raw.get("season")) != str(season) or raw.get("week") != week
                or raw.get("season_type") != "regular" or raw.get("sport") != "nfl"):
            raise CoverageError("score_horizon_mismatch")
        if m.get("home_team") != sched["home"] or m.get("away_team") != sched["away"]:
            raise CoverageError("score_schedule_team_mismatch")
        stamp = raw.get("start_time")
        if isinstance(stamp, bool) or not isinstance(stamp, (int, float)) or not math.isfinite(stamp):
            raise CoverageError("missing_exact_kickoff")
        # This observed endpoint uses epoch milliseconds. No magnitude guessing.
        try:
            kickoff = datetime.fromtimestamp(stamp / 1000, timezone.utc)
        except (ValueError, OverflowError, OSError):
            raise CoverageError("invalid_exact_kickoff") from None
        if kickoff.year not in {season, season + 1}:
            raise CoverageError("kickoff_outside_season")
        if m.get("date_time") is not None and abs((kickoff - exact_time(m["date_time"])).total_seconds()) > 1:
            raise CoverageError("conflicting_exact_kickoff")
        status = raw.get("status")
        if m.get("canceled") is True:
            phase = "canceled"
        elif (status == "complete" and m.get("is_over") is True
              and m.get("has_started") is True and m.get("is_in_progress") is False
              and kickoff <= captured):
            phase = "completed"  # still subject to later stat corrections
        elif (status == "pre_game" and m.get("status") == "scheduled"
              and all(m.get(k) is False for k in ("has_started", "is_in_progress", "is_over", "canceled"))
              and kickoff > captured):
            phase = "pregame"
        elif m.get("has_started") is True or m.get("is_in_progress") is True:
            phase = "started_unfinished"
        else:
            phase = "unknown_or_delayed"  # never interpret as zero or pregame
        result[gid] = {"game_id": gid, "week": week, "home": sched["home"], "away": sched["away"],
                       "kickoff_at": kickoff.isoformat(), "phase": phase,
                       "source_status": status, "source_closed": m.get("closed"),
                       "source_updated_at": raw.get("updated_at"), "captured_at": captured.isoformat()}
    return result


def classify_player_game(raw, team, season_schedule, week_games, season, week):
    """Byes require full schedule plus known NFL team; no-row/no-team is unknown.

    Caller supplies captured native NFL team identity, never a fantasy roster seat.
    Current/native and forecast team conflicts should be resolved before calling.
    """
    if raw is not None and (str(raw.get("season")) != str(season) or raw.get("week") != week
                            or raw.get("season_type") != "regular" or raw.get("category") != "proj"):
        raise CoverageError("projection_horizon_mismatch")
    known = {x[k] for x in season_schedule.values() for k in ("home", "away")}
    if team not in known:
        return {"phase": "no_known_team", "bye": False, "bye_evidence": None}
    games = [x for x in week_games.values() if team in (x["home"], x["away"])]
    if not games:
        if raw is not None and raw.get("game_id"):
            raise CoverageError("projection_contradicts_bye")
        return {"phase": "scheduled_bye", "bye": True,
                "bye_evidence": "validated_complete_season_schedule_team_absent_from_week"}
    if len(games) != 1:
        raise CoverageError("ambiguous_team_week")
    game = games[0]
    if raw is None or not raw.get("game_id"):
        raise CoverageError("missing_player_week_projection")
    opponent = game["away"] if game["home"] == team else game["home"]
    if raw.get("game_id") != game["game_id"] or raw.get("team") != team or (raw.get("opponent") is not None and raw.get("opponent") != opponent):
        raise CoverageError("projection_schedule_join_mismatch")
    return {**game, "bye": False, "bye_evidence": None}
