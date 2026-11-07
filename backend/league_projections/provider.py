"""Immutable Sleeper league snapshot adapter. Experimental forecasts are replaceable.

Permission for this capability and coverage of its consumed fields are separate
launch gates. Neither changes existing Sleeper behavior elsewhere in the app.
"""
from __future__ import annotations

from collections import defaultdict, Counter
from datetime import datetime, timezone
from typing import Protocol

from ..sleeper_roster import owns_roster
from .core import SLOTS, IDP, Unavailable, decimal, digest, idp_bye_fill, optimize, score, split_points, semantic_facts

API = "https://api.sleeper.app/v1"
# Finite adapter-owned expected-event contract. New provider fields do not
# automatically authorize nonlinear threshold scoring.
from ..season_forecasts import SUPPORTED_SCORING_KEYS, KICKER_SCORING_KEYS, normalize_scoring_for_slots
from .scoring import normalize as normalize_scoring
LINEAR_PROJECTED_EVENTS = SUPPORTED_SCORING_KEYS | KICKER_SCORING_KEYS | frozenset("""
idp_blk_kick idp_def_td idp_ff idp_fum_rec idp_fum_ret_yd idp_int idp_int_ret_yd
idp_pass_def idp_qb_hit idp_sack idp_sack_yd idp_safe idp_tkl idp_tkl_ast
idp_tkl_loss idp_tkl_solo blk_kick ff fum_rec fum_rec_td int sack safe st_ff
st_fum_rec st_td def_td def_st_ff def_st_fum_rec def_st_td
""".split())


def now():
    return datetime.now(timezone.utc).isoformat()


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise Unavailable("missing_exact_kickoff", state="incomplete_projections") from None
    if parsed.tzinfo is None:
        raise Unavailable("missing_exact_kickoff", state="incomplete_projections")
    return parsed


class WeeklyFeed(Protocol):
    """Backend-owned provider adapter; never supplied by a client request.

    Rows attest exact kickoff, bye evidence, availability and stat applicability.
    Historical Max PF reconstruction requires the actual historical eligible pool,
    not a replay of current rosters. An absent history remains absent.
    """
    def weeks(self, season: int, weeks: list[int], player_ids: set[str]) -> dict: ...


class SleeperExperimentalFeed:
    """Observed native feed shape, with explicit conditional availability scenario.

    Sparse expected stats remain unknown unless the key is actually supplied.
    Actual-stat sparse-zero evidence does not license zero-filled forecasts.
    """
    def __init__(self, fetch_json, *, metadata=None, captured_at=None, availability_scenario="require_verified", scoring=None, scoring_contract="strict_supplied_v1"):
        self.fetch, self.metadata = fetch_json, metadata or {}
        self.captured_at = captured_at or now()
        self.availability_scenario = availability_scenario
        self.scoring = scoring or {}
        self.scoring_contract = scoring_contract

    def weeks(self, season, weeks, player_ids):
        from .timing import CoverageError, validate_season_schedule, normalize_week_games, classify_player_game
        if not weeks:
            return {"source": "sleeper_weekly_experimental", "weeks": {}, "captured_at": self.captured_at, "coverage": {"future_weeks": 0}}
        try:
            schedule = validate_season_schedule(self.fetch(f"https://api.sleeper.app/schedule/nfl/regular/{season}"))
            result, source_hashes = {}, []
            for week in weeks:
                score_rows = self.fetch(f"https://api.sleeper.app/scores/nfl/regular/{season}/{week}")
                games = normalize_week_games(schedule, score_rows, season, week, self.captured_at)
                payload = self.fetch(f"https://api.sleeper.app/projections/nfl/{season}/{week}?season_type=regular")
                if not isinstance(payload, list):
                    raise Unavailable("invalid_weekly_feed", state="incomplete_projections")
                source_hashes.append({"week": week, "scores": digest(score_rows), "projections": digest(payload)})
                # Each supplied expected event is a linear scoring input. The
                # client cannot provide these contracts or choose arbitrary URLs.
                globally_present = {key for raw in payload for key in (raw.get("stats") or {})}
                by_id = {}
                for raw in payload:
                    pid = str(raw.get("player_id"))
                    if pid in player_ids:
                        if pid in by_id:
                            raise Unavailable("duplicate_projection_row", state="incomplete_projections")
                        by_id[pid] = raw
                rows = {}
                for pid in sorted(player_ids):
                    meta, raw = self.metadata.get(pid, {}), by_id.get(pid)
                    team = meta.get("team")
                    if raw and raw.get("team") and team and raw["team"] != team:
                        raise Unavailable("player_team_changed", state="incomplete_projections")
                    game = classify_player_game(raw, team, schedule, games, season, week)
                    if game["bye"]:
                        rows[pid] = {**game, "availability": 0, "stats": {}, "supported_keys": [], "availability_basis": "verified_schedule_bye"}
                        continue
                    if game["phase"] != "pregame":
                        raise Unavailable("live_or_unknown_game_not_supported", state="incomplete_projections", details={"week": week, "phase": game["phase"]})
                    stats = dict((raw or {}).get("stats") or {})
                    if isinstance(stats.get("gp"), bool) or stats.get("gp") != 1:
                        raise Unavailable("missing_projection_stats", state="incomplete_projections", details={"week": week})
                    if self.availability_scenario != "conditional_provider_forecast":
                        raise Unavailable("future_availability_scenario_required")
                    normalized = normalize_scoring(raw, {k for k, v in self.scoring.items() if decimal(v)},
                        globally_present & LINEAR_PROJECTED_EVENTS, policy=self.scoring_contract,
                        positions=meta.get("fantasy_positions") or [], primary_position=meta.get("position"))
                    # Preserve missing fields explicitly; the Decimal scorer rejects
                    # them instead of turning unknown projected events into zero.
                    rows[pid] = {**game, **normalized, "inapplicable_keys": [], "availability": 1,
                                 "availability_basis": "conditional_on_provider_forecast_not_verified_health",
                                 "current_injury_status": meta.get("injury_status"),
                                 "source_updated_at": (raw or {}).get("updated_at")}
                result[str(week)] = rows
            return {"source": "sleeper_weekly_experimental", "weeks": result, "captured_at": self.captured_at,
                    "coverage": {"contract": "observed_native_timing_sparse_expected_events_v1", "source_hashes": source_hashes,
                                 "availability_scenario": self.availability_scenario, "scoring_contract": self.scoring_contract, "schedule_hash": digest(schedule)}}
        except CoverageError as exc:
            raise Unavailable(str(exc), state="incomplete_projections") from None


def _league_revision(league, rosters, state):
    return digest({"league": {k: league.get(k) for k in ("season", "settings", "scoring_settings", "roster_positions", "status", "bracket_overrides_id")},
                   "rosters": sorted(({k: r.get(k) for k in ("roster_id", "owner_id", "co_owners", "players", "reserve", "taxi", "settings")}
                                      for r in rosters), key=lambda r: r["roster_id"]),
                   "state": {k: state.get(k) for k in ("season", "season_type", "week", "leg")}})


def _games(rows, ids):
    if not isinstance(rows, list) or {r.get("roster_id") for r in rows} != ids or len(rows) != len(ids):
        raise Unavailable("missing_weekly_matchups", state="incomplete_projections")
    pairs = defaultdict(list)
    for row in rows:
        if row.get("matchup_id") is None:
            raise Unavailable("missing_matchup_id", state="incomplete_projections")
        pairs[row["matchup_id"]].append(row["roster_id"])
    if any(len(pair) != 2 for pair in pairs.values()):
        raise Unavailable("unsupported_matchup_structure")
    return sorted(sorted(pair) for pair in pairs.values())


def capture(league_id, league_user_id, cfg, fetch_json, *, feed=None, captured_at=None, clock=None, viewer_user_id=None):
    if not str(league_id).isdigit() or len(str(league_id)) > 30:
        raise ValueError("invalid_league_id")
    captured_at = captured_at or (clock or now)()
    state = fetch_json(f"{API}/state/nfl")
    league = fetch_json(f"{API}/league/{league_id}")
    rosters = fetch_json(f"{API}/league/{league_id}/rosters")
    if not isinstance(league, dict) or not isinstance(rosters, list) or not isinstance(state, dict):
        raise Unavailable("missing_league_inputs", state="incomplete_projections")
    if str(league.get("league_id")) != str(league_id):
        raise Unavailable("league_identity_mismatch", state="incomplete_projections")
    if league.get("total_rosters") != len(rosters):
        raise Unavailable("incomplete_roster_set", state="incomplete_projections")
    mine = [r for r in rosters if owns_roster(r, viewer_user_id or league_user_id)]
    if len(mine) != 1 or not owns_roster(mine[0], league_user_id):
        raise PermissionError("not_a_league_member")
    revision = _league_revision(league, rosters, state)
    settings = league.get("settings", {})
    if league.get("sport") != "nfl" or league.get("season_type") != "regular":
        raise Unavailable("unsupported_sport_or_season")
    if any(settings.get(k, 0) for k in ("divisions", "league_average_match", "best_ball", "playoff_seed_type")) or league.get("bracket_overrides_id"):
        raise Unavailable("unsupported_divisions_median_bestball_or_manual_seeding")
    if settings.get("start_week", 1) != 1:
        raise Unavailable("nonstandard_start_week")
    season = int(league["season"])
    if str(state.get("season")) != str(season) or state.get("season_type") != "regular":
        raise Unavailable("season_state_mismatch")
    end = int(settings.get("playoff_week_start", 0)) - 1
    week = int(state.get("week", 0))
    if not 1 <= week <= 18 or not 1 <= end <= 18:
        raise Unavailable("invalid_regular_season_horizon")
    completed = min(week - 1, end)
    future = list(range(completed + 1, end + 1))
    slots = [s for s in league.get("roster_positions", []) if s not in {"BN", "IR", "TAXI"}]
    if not slots or any(s not in SLOTS for s in slots):
        raise Unavailable("unsupported_lineup")
    ids = {r["roster_id"] for r in rosters}
    if len(ids) != len(rosters) or len(ids) > 32 or len(ids) < 2:
        raise Unavailable("invalid_team_set")
    playoff = int(settings.get("playoff_teams", 0))
    # Standard single-elimination bracket: e.g. six teams need two first-round
    # byes. Nonstandard rounds are outside this capability's initial policy.
    if settings.get("playoff_round_type", 0) or settings.get("playoff_type", 0):
        raise Unavailable("unsupported_playoff_bracket")
    byes = (1 << (playoff - 1).bit_length()) - playoff if playoff > 1 else 0
    history, actual_records, historical_pa = defaultdict(list), {rid: [0, 0, 0] for rid in ids}, defaultdict(lambda: decimal(0))
    occupied = defaultdict(list)
    incomplete_idp_history = False
    for w in range(1, completed + 1):
        rows = fetch_json(f"{API}/league/{league_id}/matchups/{w}")
        games = _games(rows, ids)
        by_id = {r["roster_id"]: r for r in rows}
        for row in rows:
            if row.get("custom_points") is not None:
                raise Unavailable("manual_score_adjustment_requires_policy")
            points = decimal(row.get("points"))
            history[row["roster_id"]].append(str(points))
            starters, starter_points = row.get("starters", []), row.get("starters_points", [])
            if any(slot in IDP for slot in slots) and (len(starters) != len(slots) or len(starter_points) != len(slots)):
                incomplete_idp_history = True
            if len(starters) == len(slots) and len(starter_points) == len(slots):
                for slot, pid, value in zip(slots, starters, starter_points):
                    if slot in IDP and pid not in (None, "0", 0):
                        occupied[slot].append(decimal(value))
        for a, b in games:
            av, bv = decimal(by_id[a].get("points")), decimal(by_id[b].get("points"))
            outcome = 0 if av > bv else 1 if av < bv else 2
            actual_records[a][outcome] += 1
            actual_records[b][1 - outcome if outcome < 2 else 2] += 1
            historical_pa[a] += bv
            historical_pa[b] += av
    # Only slot-specific occupied starts contribute; zero performances count.
    replacement = {} if incomplete_idp_history else {slot: str(sum(values) / len(values)) for slot, values in occupied.items() if values}
    player_ids = {str(pid) for r in rosters for key in ("players", "taxi", "reserve") for pid in (r.get(key) or [])
                  if cfg["ir_maxpf"] == "include" or str(pid) not in set(map(str, r.get("reserve") or []))}
    metadata = fetch_json(f"{API}/players/nfl") if future else {}
    active_scoring = normalize_scoring_for_slots(league["scoring_settings"], slots)
    weekly = (feed or SleeperExperimentalFeed(fetch_json, metadata=metadata, captured_at=captured_at,
                availability_scenario=cfg.get("availability_scenario", "require_verified"),
                scoring=active_scoring, scoring_contract=cfg.get("scoring_contract", "strict_supplied_v1"))).weeks(season, future, player_ids)
    try:
        raw_users = fetch_json(f"{API}/league/{league_id}/users")
        names = {str(u.get("user_id")): (u.get("metadata") or {}).get("team_name") or u.get("display_name")
                 for u in raw_users if isinstance(u, dict)} if isinstance(raw_users, list) else {}
    except Exception:
        names = {}  # Labels are optional; missing scores/teams never are.
    teams = []
    for roster in sorted(rosters, key=lambda r: r["roster_id"]):
        rid, values = roster["roster_id"], roster.get("settings", {})
        # Max PF's ppts fields are not guaranteed by the public docs; require
        # actual evidence, never substitute fpts or current-roster reconstruction.
        if "ppts" not in values:
            raise Unavailable("official_maxpf_unavailable", state="incomplete_projections")
        pf = split_points(values.get("fpts"), values.get("fpts_decimal", 0))
        pa = split_points(values.get("fpts_against"), values.get("fpts_against_decimal", 0))
        record = [int(values.get(k, -1)) for k in ("wins", "losses", "ties")]
        if record != actual_records[rid] or pf != sum(map(decimal, history[rid]), decimal(0)) or pa != historical_pa[rid]:
            raise Unavailable("standings_include_unfinalized_or_adjusted_points", state="incomplete_projections")
        teams.append({"roster_id": rid, "name": str(names.get(str(roster.get("owner_id"))) or f"Team {rid}")[:150], "wins": record[0], "losses": record[1], "ties": record[2],
                      "points_for": str(pf), "points_against": str(pa),
                      "maxpf": str(split_points(values["ppts"], values.get("ppts_decimal", 0))),
                      "actual_history": history[rid], "maxpf_history": [],
                      "roster": {key: sorted(map(str, roster.get(key) or [])) for key in ("players", "reserve", "taxi")}})
    result_weeks = []
    normalized_inputs = []
    for w in future:
        games = _games(fetch_json(f"{API}/league/{league_id}/matchups/{w}"), ids)
        week_teams = {}
        for team in teams:
            pool, bye, excluded, max_pool = [], [], [], []
            roster = team["roster"]
            for pid in sorted(set(roster["players"] + roster["taxi"] + roster["reserve"])):
                if pid in roster["reserve"] and cfg["ir_maxpf"] == "exclude":
                    excluded.append({"player_id": pid, "reason": "reserve"})
                    continue
                meta = metadata.get(pid)
                if not meta or not meta.get("fantasy_positions"):
                    raise Unavailable("missing_native_player_eligibility", state="incomplete_projections")
                row = weekly.get("weeks", {}).get(str(w), {}).get(pid)
                if row is None:
                    raise Unavailable("missing_player_week", state="incomplete_projections", details={"week": w})
                positions = meta["fantasy_positions"]
                normalized_inputs.append({"season": season, "week": w, "player_id": pid, "positions": positions,
                                          "source_hash": digest(semantic_facts(row)), "input": {**row, "stats": {k: v for k, v in row.get("stats", {}).items() if k in league["scoring_settings"]}}})
                if row.get("bye"):
                    if not row.get("bye_evidence"):
                        raise Unavailable("unverified_bye", state="incomplete_projections")
                    if pid not in roster["reserve"] and pid not in roster["taxi"]:
                        bye.append({"player_id": pid, "positions": positions})
                    excluded.append({"player_id": pid, "reason": "bye"})
                    continue
                if timestamp(row.get("kickoff_at")) <= timestamp(captured_at):
                    raise Unavailable("live_remaining_projection_not_supported", state="incomplete_projections")
                availability = row.get("availability")
                if availability not in (0, 1):
                    raise Unavailable("unknown_weekly_availability", state="incomplete_projections")
                if not availability:
                    excluded.append({"player_id": pid, "reason": "provider_unavailable"})
                    continue
                points = score(row.get("stats", {}), active_scoring, row.get("supported_keys", []),
                               inapplicable_keys=row.get("inapplicable_keys", []))
                player = {"player_id": pid, "name": meta.get("full_name") or pid, "positions": positions, "points": str(points), "availability_basis": row.get("availability_basis"), "current_injury_status": row.get("current_injury_status")}
                if pid not in roster["reserve"] and pid not in roster["taxi"]:
                    pool.append(player)
                else:
                    excluded.append({"player_id": pid, "reason": "reserve" if pid in roster["reserve"] else "taxi"})
                if pid not in roster["reserve"] or cfg["ir_maxpf"] == "include":
                    max_pool.append(player)
            actual = idp_bye_fill(slots, pool, bye, replacement, empty_policy=cfg["empty_slots"])
            maximum = optimize(slots, max_pool, empty_policy=cfg["empty_slots"], hindsight=True)
            hypothetical = any(r["player"] and r["player"].get("hypothetical") for r in actual["lineup"])
            week_teams[str(team["roster_id"])] = {"actual": actual, "maxpf": maximum, "exclusions": excluded,
                                                "maxpf_dominates_actual": not hypothetical,
                                                "replacement_means": replacement}
        result_weeks.append({"week": w, "games": games, "teams": week_teams})
    picks = fetch_json(f"{API}/league/{league_id}/traded_picks")
    if not isinstance(picks, list):
        raise Unavailable("missing_pick_ownership", state="incomplete_projections")
    ownership = [{"season": int(p["season"]), "round": int(p["round"]), "original_roster_id": int(p["roster_id"]), "owner_roster_id": int(p["owner_id"])} for p in picks]
    if len({(p["season"], p["round"], p["original_roster_id"]) for p in ownership}) != len(ownership):
        raise Unavailable("duplicate_pick_ownership", state="incomplete_projections")
    final_state = fetch_json(f"{API}/state/nfl")
    final_league = fetch_json(f"{API}/league/{league_id}")
    final_rosters = fetch_json(f"{API}/league/{league_id}/rosters")
    if _league_revision(final_league, final_rosters, final_state) != revision:
        raise Unavailable("inputs_changed_during_capture", state="stale")
    finished = (clock or now)()
    if any(not entry["input"].get("bye") and timestamp(entry["input"].get("kickoff_at")) <= timestamp(finished)
           for entry in normalized_inputs):
        raise Unavailable("game_started_during_capture", state="incomplete_projections")
    provenance_counts = defaultdict(Counter)
    for entry in normalized_inputs:
        for key, value in entry["input"].get("stat_provenance", {}).items():
            provenance_counts[key][value["basis"]] += 1
    return {"league_id": str(league_id), "league_name": str(league.get("name") or "League")[:150], "season": season, "completed_weeks": completed, "playoff_spots": playoff, "playoff_byes": byes,
            "player_week_inputs": normalized_inputs, "slots": slots, "scoring": league["scoring_settings"], "scoring_hash": digest(league["scoring_settings"]),
            "teams": teams, "weeks": result_weeks, "pick_ownership": ownership, "captured_at": captured_at, "capture_completed_at": finished,
            "source": weekly["source"], "source_captured_at": weekly["captured_at"], "league_revision": revision,
            "coverage": {**weekly.get("coverage", {}), "historical_maxpf_by_week": False, "live_weeks": False,
                         "inactive_slot_coefficients": {k: v for k, v in league["scoring_settings"].items() if k not in active_scoring},
                         "scoring_contract": cfg.get("scoring_contract", "strict_supplied_v1"),
                         "stat_provenance_counts": {k: dict(v) for k, v in sorted(provenance_counts.items())},
                         "model_assumed_zero_keys": sorted(k for k, v in provenance_counts.items() if v["model_assumed"]),
                         "model_assumed_player_fields": sum(p["basis"] == "model_assumed" for entry in normalized_inputs for p in entry["input"].get("stat_provenance", {}).values())},
            "warnings": ["Provider forecasts are conditional scenarios; current injury labels do not establish future availability.",
                         "IR eligibility and tie treatment are configured scenarios, not verified league policy.",
                         "Historical weekly Max PF is unavailable; official aggregate Max PF is preserved."] +
                        (["Missing common offense events are modeled as zero after aggregate reconciliation; rare events remain unknown and this is not predictive accuracy evidence."] if cfg.get("scoring_contract") == "sleeper_sparse_offense_v1" else [])}
