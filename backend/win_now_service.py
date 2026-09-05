"""Win Now application layer: authoritative facts, frozen valuations and jobs.

The existing dynasty generator is deliberately not called. Player projections
and the season model never receive a personal dynasty ranking.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import copy
import json
import logging
import math
import os
import threading

from sqlalchemy import select

from . import database as db
from . import win_now_store as store
from .feature_flags import is_enabled
from .sleeper_roster import owns_roster
from .season_forecasts import normalize_scoring_for_slots

log = logging.getLogger(__name__)
MODEL_VERSION = "win-now-season-v1-beta"
SNAPSHOT_TTL_SECONDS = 900
_cache = {}
_cache_lock = threading.Lock()
_worker_lock = threading.Lock()
_worker_running = False


class Unavailable(ValueError):
    def __init__(self, reason, message=None):
        self.reason = reason
        self.message = message or reason.replace("_", " ").capitalize()
        super().__init__(reason)


def now_utc():
    return datetime.now(timezone.utc)


def timestamp(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def validate_params(body):
    if not isinstance(body, dict):
        raise ValueError("invalid_request")
    objective = body.get("objective", "wins")
    if objective not in ("wins", "playoffs", "championship"):
        raise ValueError("invalid_objective")
    def number(key, default, lo, hi):
        value = body.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
            raise ValueError(f"invalid_{key}")
        return float(value)
    result = {"objective": objective,
              "max_dynasty_spend_pct": number("max_dynasty_spend_pct", 3, 0, 10),
              "min_fairness": number("min_fairness", .9, .75, 1)}
    protected = body.get("protected_ids", [])
    if not isinstance(protected, list) or len(protected) > 100 or any(not isinstance(p, str) or not p for p in protected):
        raise ValueError("invalid_protected_ids")
    result["protected_ids"] = sorted(set(protected))
    return result


def _fetch(fetch, url, ttl=30):
    """Cache successful source responses only; never fall back after expiry."""
    now = now_utc()
    with _cache_lock:
        hit = _cache.get(url)
        if hit and (now - hit[0]).total_seconds() < ttl:
            return copy.deepcopy(hit[1])
    try:
        data = fetch(url)
    except Exception as exc:
        raise Unavailable("source_unavailable") from exc
    if not isinstance(data, (dict, list)):
        raise Unavailable("source_unavailable")
    with _cache_lock:
        if len(_cache) > 1024:
            _cache.clear()
        _cache[url] = (now, copy.deepcopy(data))
    return data


def load_league(actor, fetch):
    """Use settled records to find the checkpoint; nonzero points never settle it."""
    league_id = actor["league_id"]
    if actor.get("platform") != "sleeper":
        raise Unavailable("platform_unsupported", "Season projections currently support Sleeper leagues.")
    base = f"https://api.sleeper.app/v1/league/{league_id}"
    meta = _fetch(fetch, base)
    rosters = _fetch(fetch, base + "/rosters")
    users = _fetch(fetch, base + "/users", 300)
    if not isinstance(meta, dict) or not isinstance(rosters, list) or not rosters:
        raise Unavailable("league_unavailable")
    if meta.get("status") not in ("in_season",):
        raise Unavailable("season_not_active", "Season projections need a drafted league with a published schedule.")
    settings = meta.get("settings") or {}
    if settings.get("best_ball"):
        raise Unavailable("best_ball_unsupported")
    if int(settings.get("start_week") or 1) != 1:
        raise Unavailable("custom_start_week_unsupported")
    mine = [r for r in rosters if owns_roster(r, actor["league_user_id"])]
    if len(mine) != 1:
        raise Unavailable("league_membership_unavailable")
    if not meta.get("scoring_settings"):
        raise Unavailable("missing_scoring_settings")
    decisions = 2 if settings.get("league_average_match") else 1
    completed_set = set()
    for r in rosters:
        rs = r.get("settings") or {}
        total = sum(int(rs.get(k) or 0) for k in ("wins", "losses", "ties"))
        if total % decisions:
            raise Unavailable("standings_not_final")
        completed_set.add(total // decisions)
    if len(completed_set) != 1:
        raise Unavailable("standings_not_final")
    completed = completed_set.pop()
    regular = int(settings.get("playoff_week_start") or 15) - 1
    if completed >= regular:
        raise Unavailable("postseason_in_progress_unsupported", "This beta supports projections before the fantasy playoffs begin.")
    playoff_slots = int(settings.get("playoff_teams") or 6)
    rounds = math.ceil(math.log2(max(2, playoff_slots)))
    # Sleeper round-type values other than the standard one-week bracket need
    # an explicit adapter, rather than silently playing a shorter tournament.
    if int(settings.get("playoff_round_type") or 0) != 0:
        raise Unavailable("multiweek_playoffs_unsupported")
    user_names = {str(u.get("user_id")): u.get("display_name") or u.get("username") for u in users}
    teams, all_ids = [], set()
    for r in rosters:
        rs = r.get("settings") or {}
        players = [str(p) for p in r.get("players") or []]
        if len(players) != len(set(players)) or all_ids.intersection(players):
            raise Unavailable("ambiguous_roster_ownership")
        all_ids.update(players)
        inactive = {str(p) for p in (r.get("reserve") or []) + (r.get("taxi") or [])}
        teams.append({"roster_id": int(r["roster_id"]), "user_id": str(r.get("owner_id") or ""),
                      "username": user_names.get(str(r.get("owner_id"))) or f"Team {r['roster_id']}",
                      "player_ids": [p for p in players if p not in inactive],
                      "inactive_ids": sorted(inactive), "all_player_ids": players,
                      "starters": [str(p) for p in r.get("starters") or [] if str(p) not in ("0", "") and str(p) not in inactive],
                      "wins": int(rs.get("wins") or 0), "losses": int(rs.get("losses") or 0),
                      "ties": int(rs.get("ties") or 0), "division": rs.get("division"),
                      "points_for": float(rs.get("fpts") or 0) + float(rs.get("fpts_decimal") or 0) / 100})
    schedule = {}
    for week in range(completed + 1, regular + 1):
        rows = _fetch(fetch, base + f"/matchups/{week}", 30 if week == completed + 1 else 300)
        if not isinstance(rows, list) or len(rows) != len(teams):
            raise Unavailable("incomplete_schedule")
        grouped = defaultdict(list)
        for row in rows:
            if row.get("matchup_id") is None:
                raise Unavailable("incomplete_schedule")
            grouped[row["matchup_id"]].append(int(row["roster_id"]))
            if week == completed + 1 and float(row.get("custom_points") if row.get("custom_points") is not None else row.get("points") or 0) != 0:
                raise Unavailable("live_week_unsupported", "Refresh after this week's matchups settle; live-game forecasts are not available yet.")
        if any(len(pair) != 2 for pair in grouped.values()):
            raise Unavailable("schedule_format_unsupported")
        schedule[week] = list(grouped.values())
    slots = [s for s in meta.get("roster_positions") or [] if s not in ("BN", "IR", "TAXI", "RESERVE")]
    deadline = int(settings.get("trade_deadline") or 0)
    league = {"league_id": league_id, "season": str(meta["season"]), "teams": teams,
              "roster_slots": slots, "scoring_settings": normalize_scoring_for_slots(meta["scoring_settings"], slots),
              "source_scoring_settings": copy.deepcopy(meta["scoring_settings"]),
              "schedule": schedule, "completed_weeks": completed,
              "regular_season_weeks": regular, "playoff_slots": playoff_slots,
              "num_byes": 2 ** rounds - playoff_slots, "num_divisions": int(settings.get("divisions") or 0),
              "median_match": decisions == 2, "playoff_seed_type": int(settings.get("playoff_seed_type") or 0),
              "playoff_start_week": regular + 1, "playoff_round_weeks": 1,
              "current_week_started": False, "status": meta.get("status"),
              "pick_trading": settings.get("pick_trading", 1) != 0,
              "trade_review_days": int(settings.get("trade_review_days") or 0),
              "roster_capacity": len([s for s in meta.get("roster_positions") or [] if s not in ("IR", "TAXI", "RESERVE")]),
              "trades_allowed": (not deadline or completed < deadline) and not bool(settings.get("disable_trades"))}
    return league, int(mine[0]["roster_id"]), meta


def _forecast_batch(league, fetch, now):
    from .season_forecasts import fetch_projection_snapshot
    from .season_simulator import required_forecast_weeks
    from .outlook.bye_weeks import fetch_byes
    weeks = required_forecast_weeks(league)
    ids = sorted({p for t in league["teams"] for p in t["player_ids"]})
    # Explicit normalized imports are useful for licensed providers and replay.
    # Read once per invocation and preserve the source's original captured_at.
    path = os.environ.get("FTF_SEASON_FORECAST_FILE")
    if path:
        from .season_forecasts import import_projection_snapshot
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle)
        return import_projection_snapshot(raw["season"], raw["weeks"], raw["forecasts"],
                    provider=raw["provider"], captured_at=raw["captured_at"],
                    published_at=raw.get("published_at"),
                    supported_scoring_keys=raw.get("supported_scoring_keys"), provenance=raw.get("provenance"),
                    earliest_game_date=raw.get("earliest_game_date"), earliest_game_dates=raw.get("earliest_game_dates"),
                    earliest_kickoff_at=raw.get("earliest_kickoff_at"))
    try:
        byes = fetch_byes().get(league["season"], {})
    except Exception:
        # No bundled stale schedule fallback. Missing bye certification becomes
        # explicit missing coverage in the provider, never fabricated zeroes.
        byes = {}
    return fetch_projection_snapshot(league["season"], weeks,
                 lambda url: _fetch(fetch, url, 300), now.isoformat(), player_ids=ids, bye_weeks=byes)


def load_bundle(actor, fetch):
    from .season_simulator import simulate_season
    league, buyer, meta = load_league(actor, fetch)
    # Polling and decisions re-read source facts without projection transforms.
    league_revision = store.identity(league)
    now = now_utc()
    forecasts = _forecast_batch(league, fetch, now)
    if not forecasts.get("supported", True):
        raise Unavailable((forecasts.get("reasons") or ["forecast_unavailable"])[0])
    expires = now + timedelta(seconds=SNAPSHOT_TTL_SECONDS)
    # Full-feed cutoff survives roster filtering: an unrostered Thursday
    # participant still starts the week for the entire league.
    cutoffs = [forecasts.get("earliest_game_date"), forecasts.get("earliest_kickoff_at")]
    cutoffs.extend((forecasts.get("earliest_game_dates") or {}).values())
    if not any(cutoffs) and not any(r.get("kickoff_at") or r.get("game_date") for r in forecasts.get("forecasts", [])):
        raise Unavailable("game_start_cutoff_unavailable")
    for value in filter(None, cutoffs):
        cutoff = timestamp(value if "T" in value else value + "T00:00:00+00:00")
        if cutoff <= now:
            raise Unavailable("live_week_unsupported", "Current-week play may have started. Refresh after official results settle.")
        expires = min(expires, cutoff)
    for row in forecasts.get("forecasts", []):
        if int(row["week"]) <= league["completed_weeks"] or row.get("bye"):
            continue
        value = row.get("kickoff_at") or row.get("game_date")
        if not value:
            continue
        # The feed's date-only rows carry no kickoff time. Midnight UTC is a
        # conservative serving cutoff, never presented as an actual kickoff.
        cutoff = timestamp(value if "T" in value else value + "T00:00:00+00:00")
        if cutoff <= now:
            raise Unavailable("live_week_unsupported", "Current-week play may have started. Refresh after official results settle.")
        expires = min(expires, cutoff)
    captured = timestamp(forecasts["captured_at"])
    if captured > now + timedelta(minutes=1) or (now - captured).total_seconds() > SNAPSHOT_TTL_SECONDS:
        raise Unavailable("stale_forecasts")
    expires = min(expires, captured + timedelta(seconds=SNAPSHOT_TTL_SECONDS))
    n_sims = max(256, min(4000, int(os.environ.get("FTF_SEASON_SIM_COUNT", "1000"))))
    # Explicit beta approximation, not provider support or a zero event forecast.
    # Preserve raw and effective rules in the immutable league/snapshot identity.
    rare_player_events = {"st_ff", "st_fum_rec", "st_td", "fum_rec_td"}
    supported_keys = set(forecasts.get("supported_scoring_keys", []))
    exclusions = {key: value for key, value in league["scoring_settings"].items()
                  if key in rare_player_events and key not in supported_keys
                  and isinstance(value, (int, float)) and not isinstance(value, bool)
                  and math.isfinite(value) and value != 0}
    league["scoring_exclusions"] = exclusions
    league["scoring_settings"] = {key: value for key, value in league["scoring_settings"].items()
                                   if key not in exclusions}
    baseline = simulate_season(league, forecasts, n_sims=n_sims, seed=42)
    if not baseline.get("meta", {}).get("supported"):
        raise Unavailable((baseline.get("meta", {}).get("reasons") or ["model_unavailable"])[0])
    sid = store.identity({"league": league, "forecast": forecasts["snapshot_id"],
                          "model": MODEL_VERSION, "n_sims": n_sims})
    from .season_simulator import required_forecast_weeks
    roster_ids = {p for t in league["teams"] for p in t["player_ids"]}
    horizon = set(required_forecast_weeks(league))
    expected_rows = len(roster_ids) * len(horizon)
    covered_rows = len({(str(r["player_id"]), int(r["week"])) for r in forecasts.get("forecasts", [])
                       if r.get("availability") is not None and str(r["player_id"]) in roster_ids and int(r["week"]) in horizon})
    metadata = {**baseline["meta"], "snapshot_id": sid, "as_of": now.isoformat(),
                "expires_at": expires.isoformat(), "source": forecasts.get("provider"),
                "model_version": MODEL_VERSION, "championship_available": is_enabled("outlook.championship_probabilities"),
                "coverage": min(1, covered_rows / expected_rows) if expected_rows else None,
                "quality": forecasts.get("quality", {}), "forecast_snapshot_id": forecasts["snapshot_id"],
                "league_revision": league_revision,
                "cutoff_basis": "source_game_date_or_kickoff", "beta": True,
                "scoring_exclusions": exclusions,
                "scoring_warning": "Rare special-teams/fumble bonuses are not projected." if exclusions else None}
    store.save_forecasts(forecasts)
    store.save_projection(sid, league["league_id"], forecasts["snapshot_id"],
                          {"league": league, "baseline": baseline}, now.isoformat(), expires.isoformat())
    return {"league": league, "buyer_roster_id": buyer, "forecasts": forecasts,
            "baseline": baseline, "meta": metadata, "n_sims": n_sims, "league_meta": meta}


def build_context(actor, bundle, params, fetch):
    from . import trade_service as pricing
    from .trade_service import elo_to_value
    from .outlook.strength import eligible_positions
    from .pick_values import priced_pool_value
    league = copy.deepcopy(bundle["league"])
    if league.get("trade_review_days"):
        raise Unavailable("trade_review_delay_unsupported", "Standings are available, but this league's trade review delay is not modeled yet.")
    buyer = bundle["buyer_roster_id"]
    by_user = {t["user_id"]: t["roster_id"] for t in league["teams"]}
    assets = {}
    for team in league["teams"]:
        for pid in team["all_player_ids"]:
            pm = actor["players"].get(pid, {})
            value = actor["market_values"].get(pid, 0)
            assets[pid] = {"id": pid, "name": pm.get("name") or pid,
                           "position": pm.get("position") or "?", "market_value": value,
                           "owner_roster_id": team["roster_id"], "is_pick": False,
                           "tradeable": bool(value > 0 and pid not in team["inactive_ids"]),
                           "locked": pid in team["inactive_ids"],
                           "lineup_ineligible": pid in team["inactive_ids"]}
    # Platform-owned picks only, checked against the fresh traded-pick overlay.
    picks = db.load_draft_picks(league["league_id"], source=db.PICK_SOURCE_PLATFORM)
    transfers = _fetch(fetch, f"https://api.sleeper.app/v1/league/{league['league_id']}/traded_picks", 30)
    if not isinstance(transfers, list):
        raise Unavailable("pick_ownership_unavailable")
    owners = {(int(p["season"]), int(p["round"]), str(p["roster_id"])): int(p["owner_id"]) for p in transfers}
    for p in picks:
        if int(p["season"]) <= int(league["season"]):
            continue
        original = str(p["original_roster_id"])
        owner = owners.get((int(p["season"]), int(p["round"]), original), int(original))
        if owner != by_user.get(str(p.get("owner_user_id"))):
            continue
        value = priced_pool_value(p, scoring_format=actor["scoring_format"])
        assets[p["pick_id"]] = {"id": p["pick_id"], "name": f"{p['season']} Round {p['round']} · {p.get('original_username') or original}",
                                "position": "PICK", "owner_roster_id": owner, "is_pick": True,
                                "market_value": value, "tradeable": value > 0 and league.get("pick_trading", True),
                                "original_roster_id": int(original), "season": p["season"], "round": p["round"]}
    owner_ids = list(by_user)
    preferences = db.load_league_preferences_bulk(owner_ids, league["league_id"])
    asset_prefs = db.load_asset_preferences_bulk(owner_ids, league["league_id"])
    partners = db.load_member_rankings(league["league_id"], actor["user_id"], actor["scoring_format"])
    table = db.member_rankings_table
    with db.engine.connect() as conn:
        rows = conn.execute(select(table.c.user_id, table.c.player_id, table.c.updated_at)
                              .where(table.c.league_id == league["league_id"],
                                     table.c.scoring_format == actor["scoring_format"])).mappings().all()
    dates = {(r["user_id"], r["player_id"]): r["updated_at"] for r in rows}
    partner_values, evidence, rank_revisions = {}, {}, {}
    now = now_utc()
    for uid, rid in by_user.items():
        board = partners.get(uid, {}).get("elo_ratings", {})
        personal = {pid: elo_to_value(elo) for pid, elo in board.items() if pid in assets}
        counts = defaultdict(int)
        placements, stamps = {}, {}
        if personal:
            swipes = db.swipe_decisions_table
            with db.engine.connect() as conn:
                comparisons = conn.execute(select(swipes).where(swipes.c.user_id == uid,
                    swipes.c.scoring_format == actor["scoring_format"], swipes.c.decision_type == "rank")).mappings().all()
            for comparison in comparisons:
                for pid in (comparison["winner_player_id"], comparison["loser_player_id"]):
                    if pid in personal and str(comparison["created_at"]) <= str(dates.get((uid, pid), "")):
                        counts[pid] += 1
            placements = db.load_tier_overrides(uid, actor["scoring_format"])
            stamps = db.load_tier_override_stamps(uid, actor["scoring_format"])
        source_assets = {}
        # Hash the source revision; never persist or disclose partner boards.
        rank_revisions[uid] = store.identity({"board": board, "counts": dict(counts), "placements": placements,
                        "stamps": stamps, "dates": {p: dates.get((uid, p)) for p in personal}})
        for pid, val in personal.items():
            try:
                age = max(0, (now - timestamp(dates[(uid, pid)])).total_seconds() / 86400)
                # Only actual rank comparisons or a timestamped placement
                # support personalization. Market drift cannot turn a seed
                # into evidence of a manager's preference.
                placed = pid in placements and pid in stamps and timestamp(stamps[pid]) <= timestamp(dates[(uid, pid)])
                w = (1 if placed else counts[pid] / (counts[pid] + 4)) * math.exp(-age / 30)
            except (KeyError, TypeError, ValueError):
                w = 0
            source_assets[pid] = {"confidence": w}
        meaningful = {p: d for p, d in source_assets.items() if d["confidence"] > .01}
        if meaningful:
            partner_values[rid] = personal
        evidence[rid] = {"basis": "personal" if meaningful else "market",
                         "confidence": sum(d["confidence"] for d in meaningful.values()) / max(1, len(meaningful)),
                         "coverage": len(meaningful) / max(1, len(assets)), "assets": source_assets,
                         "intent": preferences.get(uid, {}).get("team_outlook") or "not_sure",
                         "declared": bool(preferences.get(uid, {}).get("team_outlook")),
                         "confidence_source": "rank_comparisons_and_placements" if meaningful else "none"}
        for pid in asset_prefs.get(uid, {}).get("untouchables", []):
            if pid in assets and assets[pid]["owner_roster_id"] == rid:
                assets[pid]["locked"] = True
    buyer_values = {pid: actor["personal_values"].get(pid, a["market_value"]) for pid, a in assets.items()}
    buyer_evidence = {"basis": "personal", "confidence": 0, "coverage": 1,
                      "assets": {pid: {"confidence": actor.get("confidence", {}).get(pid, 0)} for pid in assets}}
    # Reserve/taxi players are not movable/usable in this beta, but retain their
    # value in the fixed buyer budget and their physical roster allocation.
    league["roster_capacity"] = {t["roster_id"]: league["roster_capacity"] + len(t["inactive_ids"]) for t in league["teams"]}
    league["lineup_slots"] = [list(eligible_positions(s)) for s in league["roster_slots"]]
    context = {**params, "league": league, "buyer_roster_id": buyer, "assets": assets,
               "buyer_values": buyer_values, "buyer_evidence": buyer_evidence,
               "partner_values": partner_values, "partner_evidence": evidence,
               "championship_supported": bundle["meta"]["championship_available"],
               "baseline": bundle["baseline"], "snapshot_id": bundle["meta"]["snapshot_id"],
               "pricing_config": dict(pricing._cfg), "pricing_crown_enabled": bool(pricing.FLAGS.trade_crown_asset),
               "max_simulated": 8}
    context["valuation_revision"] = store.identity({"assets": assets, "rank_revisions": rank_revisions,
        "preferences": preferences, "asset_preferences": asset_prefs, "buyer_revision": store.identity(actor),
        "pricing_config": context["pricing_config"], "pricing_crown_enabled": context["pricing_crown_enabled"]})
    for pid in params["protected_ids"]:
        if pid not in assets or assets[pid]["owner_roster_id"] != buyer:
            raise ValueError("invalid_protected_asset")
    return context


def public_payload(value, championship=None):
    """Hide title metrics recursively, including deltas/uncertainty on cards."""
    championship = is_enabled("outlook.championship_probabilities") if championship is None else championship
    if isinstance(value, dict):
        return {k: (bool(v and championship) if k == "championship_available" else
                    None if not championship and ("championship" in k or k == "title_probability")
                    else public_payload(v, championship)) for k, v in value.items()}
    if isinstance(value, list):
        return [public_payload(v, championship) for v in value]
    return value


def public_assets(context):
    return [{**{k: a[k] for k in ("id", "name", "position", "owner_roster_id", "is_pick") if k in a},
             "tradable": bool(a.get("tradeable", True) and not a.get("locked"))}
            for a in context["assets"].values()]


def evaluate_callback(bundle, context):
    from .season_simulator import evaluate_trade, projected_lineup_points
    projection_baseline = projected_lineup_points(bundle["league"], bundle["forecasts"])
    def evaluate(buyer, partner, give, receive):
        gp = [p for p in give if not context["assets"][p]["is_pick"]]
        rp = [p for p in receive if not context["assets"][p]["is_pick"]]
        result = evaluate_trade(bundle["league"], bundle["forecasts"], buyer, partner, gp, rp,
                                 n_sims=bundle["n_sims"], seed=42, baseline=bundle["baseline"])
        if not result.get("supported"):
            return result
        confirmation = evaluate_trade(bundle["league"], bundle["forecasts"], buyer, partner, gp, rp,
                                         n_sims=bundle["n_sims"], seed=99173)
        if not confirmation.get("supported"):
            return confirmation
        for side in ("buyer", "partner"):
            for metric, uncertainty in result[side]["uncertainty"].items():
                uncertainty["confirmation_delta"] = confirmation[side]["delta"][metric]
        return result
    return evaluate, projection_baseline


def scenario_payload(row, context):
    row = dict(row)
    row.update(buyer=row["season"]["buyer"], partner=row["season"]["partner"])
    assets = context["assets"]
    partner = row["partner_roster_id"]
    row["give"] = [{k: assets[p][k] for k in ("id", "name", "position", "is_pick", "owner_roster_id")} for p in row["give_ids"]]
    row["receive"] = [{k: assets[p][k] for k in ("id", "name", "position", "is_pick", "owner_roster_id")} for p in row["receive_ids"]]
    row["partner_username"] = next(t["username"] for t in context["league"]["teams"] if t["roster_id"] == partner)
    row["buyer_roster_id"] = context["buyer_roster_id"]
    ev = row["partner_evidence"]
    row["valuation"] = {"buyer_dynasty_cost": row["buyer_dynasty_cost"], "buyer_budget": row["dynasty_budget"],
        "buyer_package_loss_fraction": max(0, -row["buyer_dynasty_delta"]) / max(row["buyer_give_value"], 1e-9),
        "partner_gain_fraction": row["partner_dynasty_surplus"] / max(row["partner_give_value"], 1e-9),
        "market_ratio": row["market_ratio"], **{f"partner_{k}": ev.get(k) for k in ("basis", "confidence", "coverage", "intent")}}
    row["reasons"] = (row.get("rejection_reasons") or ["Improves your selected season objective within your dynasty budget.",
        "Passes market fairness and your partner's dynasty and season checks."])
    return row


def _prepare_marginals(bundle, context, baseline):
    """Buyer-only legal package lineups shortlist exchanges; paired sims gate them."""
    from .season_simulator import select_projected_lineup
    buyer = context["buyer_roster_id"]
    before = next(t for t in baseline["teams"] if t["roster_id"] == buyer)
    league = bundle["league"]
    team = next(t for t in league["teams"] if t["roster_id"] == buyer)
    weeks = sorted(int(w) for w in before["weekly_points"])
    if context["objective"] == "wins":
        weeks = [w for w in weeks if w <= league["regular_season_weeks"]][:3]
    elif context["objective"] == "playoffs":
        weeks = [w for w in weeks if w <= league["regular_season_weeks"]]
    else:
        weeks = [w for w in weeks if w > league["regular_season_weeks"]]
    indexed = {w: {} for w in weeks}
    for row in bundle["forecasts"]["forecasts"]:
        if int(row["week"]) in indexed:
            indexed[int(row["week"])][row["player_id"]] = row
    def points(ids):
        return sum(select_projected_lineup(ids, league["roster_slots"], indexed[w], league["scoring_settings"],
                        bundle["forecasts"].get("supported_scoring_keys"))["projected_points"] for w in weeks)
    base = points(team["player_ids"])
    cache = {}
    def marginal(_buyer, give, receive):
        key = (tuple(sorted(give)), tuple(sorted(receive)))
        if key not in cache:
            ids = [p for p in team["player_ids"] if p not in give]
            ids += [p for p in receive if not context["assets"][p]["is_pick"]]
            cache[key] = points(ids) - base
        return cache[key]
    context["marginal_lineup_gain"] = marginal


def run_search(actor, params, fetch, *, job_id=None):
    from .win_now_optimizer import generate_candidates
    from . import trade_service as pricing
    bundle = load_bundle(actor, fetch)
    context = build_context(actor, bundle, params, fetch)
    if params["objective"] == "championship" and not context["championship_supported"]:
        raise Unavailable("championship_not_validated", "Championship search will unlock after separate model validation.")
    callback, lineup = evaluate_callback(bundle, context)
    _prepare_marginals(bundle, context, lineup)
    diagnostics = {}
    with pricing._cfg_override(context["pricing_config"]):
        rows = generate_candidates(context, callback, diagnostics=diagnostics)
    if timestamp(bundle["meta"]["expires_at"]) <= now_utc():
        raise Unavailable("stale_forecasts")
    meta = {**bundle["meta"], "objective": params["objective"], "policy_version": "win-now-v1",
            "valuation_revision": context["valuation_revision"], "params": params,
            "pricing_revision": store.identity(context["pricing_config"]),
            "input_revision": store.identity({k: v for k, v in context.items() if not callable(v)})}
    persistence_guard = {"require_user": True, "job_id": job_id} if job_id else {}
    trades = [store.save_scenario(actor["user_id"], actor["league_id"], params["objective"], scenario_payload(r, context), meta,
                                  **persistence_guard) for r in rows]
    return public_payload({"meta": meta, "baseline": {"meta": meta, "teams": bundle["baseline"]["teams"]},
                           "assets": public_assets(context), "buyer_roster_id": bundle["buyer_roster_id"],
                           "trades": trades, "diagnostics": diagnostics})


def process_pending(fetch):
    from . import user_data_lifecycle
    # Capture before reading queued inputs. Deletion drains admitted searches
    # and invalidates stale queued work, matching the dynasty worker protocol.
    started = user_data_lifecycle.snapshot()
    store.expire_jobs()
    for job in store.pending_jobs():
        lease = user_data_lifecycle.capture(job["user_id"], started=started)
        with lease.active() as active:
            if not active:
                continue
            if not store.claim_job(job["job_id"]):
                continue
            try:
                if timestamp(job["expires_at"]) <= now_utc():
                    raise Unavailable("job_expired")
                if not is_enabled("trades.win_now") or not is_enabled("outlook.season_projections"):
                    raise Unavailable("feature_disabled")
                inputs = json.loads(job["input_json"])
                result = run_search(inputs["actor"], inputs["params"], fetch, job_id=job["job_id"])
                store.finish_job(job["job_id"], result=result)
            except Unavailable as exc:
                store.finish_job(job["job_id"], reason=exc.reason)
            except Exception:
                log.exception("Win Now job failed job_id=%s", job["job_id"])
                store.finish_job(job["job_id"], reason="generation_failed")


def start_worker_on_startup(fetch):
    """Resume queued work only in the serving process, never the cache bake."""
    if os.environ.get("FTF_TEST_MODE") or os.environ.get("FTF_BUILD_MODE"):
        return
    store.recover_interrupted_jobs()
    if store.pending_jobs(1):
        wake_worker(fetch)


def wake_worker(fetch):
    global _worker_running
    with _worker_lock:
        if _worker_running:
            return
        _worker_running = True
    def work():
        global _worker_running
        try:
            store.prune_history()
            while True:
                process_pending(fetch)
                with _worker_lock:
                    if not store.pending_jobs(1):
                        break
        finally:
            with _worker_lock:
                _worker_running = False
            # A submission can arrive between the last queue read and this
            # flag release. Its wake saw a running worker; resume it here.
            if store.pending_jobs(1):
                wake_worker(fetch)
    threading.Thread(target=work, name="win-now-worker", daemon=True).start()
