"""Authenticated Win Now routes, installed on the existing Flask application."""
from __future__ import annotations

import json

from flask import jsonify, request
from sqlalchemy import func, select

from . import database as db
from . import win_now_service as service
from . import win_now_store as store
from .feature_flags import is_enabled


def install(app, *, require_session, read_denial, write_denial, active_format,
            league_user_id, pool_provider, fetch_json):
    def session(write=False):
        if not is_enabled("outlook.season_projections"):
            return None, (jsonify({"error": "feature_disabled"}), 404)
        sess = require_session()
        denial = read_denial(sess) or (write_denial(sess) if write else None)
        return sess, denial

    def actor(sess, league_id):
        from .trade_service import elo_to_value
        league = sess["league"]
        if not isinstance(league_id, str) or league_id != str(league.league_id):
            raise PermissionError("league_mismatch")
        fmt = active_format(sess)
        pool, seed = pool_provider(fmt)
        players = {p.id: {"name": p.name, "position": p.position} for p in pool}
        players.update({p.id: {"name": p.name, "position": p.position} for p in sess.get("players") or []})
        ranking = sess.get("service")
        personal = ({rp.player.id: elo_to_value(rp.elo) for rp in ranking.get_rankings(position=None).rankings}
                    if ranking else {})
        counts = ranking.comparison_counts() if ranking else {}
        placements = ranking.placement_bands() if ranking else {}
        confidence = {pid: (1.0 if pid in placements else max(0, n) / (max(0, n) + 4.0))
                      for pid, n in counts.items()}
        for pid in placements:
            confidence[pid] = 1.0
        return {"user_id": str(sess["user_id"]), "league_user_id": str(league_user_id(sess)),
                "league_id": league_id, "platform": (db.get_league_draft_context(league_id) or {}).get("platform") or getattr(league, "platform", "sleeper"),
                "scoring_format": fmt, "players": players,
                "market_values": {str(pid): elo_to_value(v) for pid, v in seed.items()},
                "personal_values": personal, "confidence": confidence}

    def unavailable(exc):
        return jsonify({"status": "unavailable", "reason": exc.reason, "message": exc.message})

    def guarded(fn):
        # Keep auth exceptions owned by the existing global handlers.
        from functools import wraps
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except service.Unavailable as exc:
                return unavailable(exc)
            except PermissionError:
                return jsonify({"error": "forbidden"}), 403
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
        return wrapper

    def body():
        result = request.get_json(silent=True)
        if not isinstance(result, dict):
            raise ValueError("invalid_request")
        return result

    def trade_enabled():
        if not is_enabled("trades.win_now"):
            raise service.Unavailable("feature_disabled")

    @app.route("/api/league/season-projections", methods=["GET"])
    @guarded
    def season_projections_route():
        sess, denial = session()
        if denial is not None:
            return denial
        who = actor(sess, request.args.get("league_id") or str(sess["league"].league_id))
        bundle = service.load_bundle(who, fetch_json)
        assets = []
        if is_enabled("trades.win_now"):
            try:
                context = service.build_context(who, bundle, service.validate_params({}), fetch_json)
                assets = service.public_assets(context)
            except service.Unavailable:
                pass  # Standings availability is independent of pick ownership.
        return jsonify(service.public_payload({"status": "available", "meta": bundle["meta"],
                       "teams": bundle["baseline"]["teams"], "buyer_roster_id": bundle["buyer_roster_id"],
                       "assets": assets}))

    @app.route("/api/win-now/search", methods=["POST"])
    @guarded
    def win_now_search_route():
        trade_enabled()
        sess, denial = session(write=True)
        if denial is not None:
            return denial
        data = body()
        params = service.validate_params(data)
        if params["objective"] == "championship" and not is_enabled("outlook.championship_probabilities"):
            raise service.Unavailable("championship_not_validated")
        who = actor(sess, data.get("league_id"))
        store.expire_jobs()
        t = db.win_now_jobs_table
        with db.engine.connect() as conn:
            pending = conn.execute(select(func.count()).select_from(t)
                                   .where(t.c.user_id == who["user_id"], t.c.status.in_(("queued", "running")))).scalar()
        if pending >= 2:
            return jsonify({"error": "too_many_jobs", "message": "A search is already running. Please wait for it to finish."}), 429
        job = store.create_job(who["user_id"], who["league_id"], {"actor": who, "params": params}, require_user=True)
        device = request.headers.get("X-Device") or "web"
        db.record_event(who["user_id"], "win_now_objective_selected", source="api", league_id=who["league_id"],
                        device_type=device, os_version=request.headers.get("X-OS-Version"),
                        app_version=request.headers.get("X-App-Version"), tz=request.headers.get("X-User-TZ"),
                        props={**params, "protected_ids": None, "job_id": job["job_id"],
                               "platform": "ios" if device in ("iphone", "ipad", "macos") else "android" if device == "android" else "web",
                               "league_platform": who["platform"]})
        service.wake_worker(fetch_json)
        return jsonify({"job_id": job["job_id"], "status": "queued"}), 202

    @app.route("/api/win-now/jobs/<job_id>", methods=["GET"])
    @guarded
    def win_now_job_route(job_id):
        trade_enabled()
        sess, denial = session()
        if denial is not None:
            return denial
        job = store.get_job(job_id, str(sess["user_id"]))
        if not job or str(sess["league"].league_id) != job["league_id"]:
            return jsonify({"error": "not_found"}), 404
        if service.timestamp(job["expires_at"]) <= service.now_utc():
            raise service.Unavailable("stale_forecast", "These forecasts have expired. Run a new search.")
        response = {"job_id": job_id, "status": job["status"]}
        if job["status"] == "complete":
            result = json.loads(job["result_json"])
            if result["meta"].get("objective") == "championship" and not is_enabled("outlook.championship_probabilities"):
                raise service.Unavailable("championship_not_validated")
            current = actor(sess, job["league_id"])
            previous = json.loads(job["input_json"])["actor"]
            if store.identity(current) != store.identity(previous):
                raise service.Unavailable("ranking_inputs_changed", "Your rankings changed. Run a new search.")
            # Fresh authoritative facts, including week finality and transactions.
            league, _, _ = service.load_league(current, fetch_json)
            if store.identity(league) != result["meta"].get("league_revision"):
                raise service.Unavailable("league_inputs_changed", "League rosters or results changed. Run a new search.")
            context = service.build_context(current, {"league": league, "buyer_roster_id": result["buyer_roster_id"],
                        "baseline": result["baseline"], "meta": result["meta"]},
                        json.loads(job["input_json"])["params"], fetch_json)
            if context["valuation_revision"] != result["meta"].get("valuation_revision"):
                raise service.Unavailable("valuation_inputs_changed", "Pick ownership, preferences or valuations changed. Run a new search.")
            response["result"] = service.public_payload(result)
        elif job["status"] == "failed":
            response.update(reason=job["reason"], message=(job["reason"] or "Search failed").replace("_", " ").capitalize())
        elif job["status"] == "queued":
            service.wake_worker(fetch_json)
        return jsonify(response)

    @app.route("/api/win-now/evaluate", methods=["POST"])
    @guarded
    def win_now_evaluate_route():
        trade_enabled()
        sess, denial = session(write=True)
        if denial is not None:
            return denial
        data = body()
        params = service.validate_params(data)
        if params["objective"] == "championship" and not is_enabled("outlook.championship_probabilities"):
            raise service.Unavailable("championship_not_validated")
        for key in ("give_ids", "receive_ids"):
            if not isinstance(data.get(key), list) or len(data[key]) > 3 or any(not isinstance(p, str) or not p for p in data[key]):
                raise ValueError(f"invalid_{key}")
        partner = data.get("partner_roster_id")
        if isinstance(partner, bool) or not isinstance(partner, int):
            raise ValueError("invalid_partner_roster_id")
        who = actor(sess, data.get("league_id"))
        bundle = service.load_bundle(who, fetch_json)
        context = service.build_context(who, bundle, params, fetch_json)
        bundle["meta"].update(valuation_revision=context["valuation_revision"], params=params)
        callback, _ = service.evaluate_callback(bundle, context)
        from .win_now_optimizer import evaluate_candidate
        from . import trade_service as pricing
        with pricing._cfg_override(context["pricing_config"]):
            row = evaluate_candidate(context, partner, data["give_ids"], data["receive_ids"], callback)
        if service.timestamp(bundle["meta"]["expires_at"]) <= service.now_utc():
            raise service.Unavailable("stale_forecasts")
        scenario = None
        if row.get("season") and row["season"].get("buyer"):
            scenario = store.save_scenario(who["user_id"], who["league_id"], params["objective"],
                         service.scenario_payload(row, context), bundle["meta"], require_user=True)
        return jsonify(service.public_payload({"status": "available", "eligible": row["eligible"],
                       "rejection_reasons": row["rejection_reasons"], "scenario": scenario, "meta": bundle["meta"]}))

    @app.route("/api/win-now/scenarios/<scenario_id>/decision", methods=["POST"])
    @guarded
    def win_now_decision_route(scenario_id):
        trade_enabled()
        sess, denial = session(write=True)
        if denial is not None:
            return denial
        row = store.get_scenario(scenario_id, str(sess["user_id"]))
        if not row or row["league_id"] != str(sess["league"].league_id):
            return jsonify({"error": "not_found"}), 404
        if service.timestamp(row["expires_at"]) <= service.now_utc():
            raise service.Unavailable("stale_forecast")
        data = body()
        if data.get("decision") not in ("like", "pass"):
            raise ValueError("invalid_decision")
        payload = json.loads(row["payload_json"])
        if row["objective"] == "championship" and not is_enabled("outlook.championship_probabilities"):
            raise service.Unavailable("championship_not_validated")
        if not payload.get("eligible"):
            raise ValueError("ineligible_scenario")
        who = actor(sess, row["league_id"])
        league, buyer, _ = service.load_league(who, fetch_json)
        meta = payload["meta"]
        if store.identity(league) != meta.get("league_revision"):
            raise service.Unavailable("league_inputs_changed")
        context = service.build_context(who, {"league": league, "buyer_roster_id": buyer, "baseline": {}, "meta": meta},
                                        meta["params"], fetch_json)
        if context["valuation_revision"] != meta.get("valuation_revision"):
            raise service.Unavailable("valuation_inputs_changed")
        store.save_decision(str(sess["user_id"]), scenario_id, data["decision"], require_user=True)
        return jsonify({"ok": True})
