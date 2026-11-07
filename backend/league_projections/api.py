"""Authenticated advisory routes on the existing Flask app."""
from functools import wraps
import csv
import io
import json

from flask import Response, jsonify, request

from ..feature_flags import is_enabled
from .. import database as db
from . import batch, store
from .core import Unavailable, VERSION
from .simulation import config


def install(app, *, require_session, read_denial, write_denial, league_user_id, fetch_json):
    def guarded(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not is_enabled("league.projections"):
                return jsonify(error="feature_disabled"), 404
            sess = require_session()
            denial = read_denial(sess) or (write_denial(sess) if request.method == "POST" else None)
            if denial is not None:
                return denial
            try:
                return fn(sess, *args, **kwargs)
            except Unavailable as exc:
                return jsonify(status=exc.state, reason=exc.reason, details=exc.details), 429 if exc.state == "busy" else 422
            except ValueError as exc:
                return jsonify(error=str(exc)), 400
        return wrapper

    def identity(sess):
        return str(sess["user_id"]), str(sess["league"].league_id)

    def platform(sess):
        context = db.get_league_draft_context(str(sess["league"].league_id)) or {}
        return context.get("platform") or getattr(sess["league"], "platform", "sleeper")

    def public(row):
        return {"run_id": row["run_id"], "status": row["status"], "created_at": row["created_at"],
                "updated_at": row["updated_at"], "input_hash": row.get("input_hash"),
                "reason": row.get("reason"), "details": json.loads(row.get("details_json") or "{}"),
                "result": json.loads(row["result_json"]) if row.get("result_json") else None}

    def load(sess, run_id, *, with_snapshot=False):
        if len(run_id) != 32 or any(c not in "0123456789abcdef" for c in run_id):
            return None
        if with_snapshot:
            return store.get(run_id, *identity(sess))
        return store.public_rows((run_id,), *identity(sess)).get(run_id)

    @app.route("/api/leagues/<league_id>/projection-runs", methods=["POST"])
    @guarded
    def league_projection_create(sess, league_id):
        uid, current_league = identity(sess)
        if league_id != current_league:
            return jsonify(error="not_found"), 404
        if request.content_length is None or request.content_length > 8192:
            return jsonify(error="payload_too_large"), 413
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or ("config" not in data or set(data) - {"config", "baseline_run_id"}):
            raise ValueError("configuration_required")
        cfg = config(data["config"])
        if not is_enabled("league.projections_provider_approved"):
            raise Unavailable("new_projection_provider_approval_pending")
        if not batch.settings()["policy_approved"]:
            raise Unavailable("projection_policy_approval_pending")
        if platform(sess) != "sleeper":
            raise Unavailable("sleeper_only")
        baseline_id = data.get("baseline_run_id")
        snapshot = None
        if baseline_id is not None:
            if not isinstance(baseline_id, str):
                raise ValueError("invalid_baseline_run")
            baseline = load(sess, baseline_id, with_snapshot=True)
            if not baseline or baseline["status"] != "complete" or not baseline.get("snapshot_json"):
                raise ValueError("baseline_unavailable")
            baseline_result = json.loads(baseline["result_json"])
            if baseline_result.get("model_version") != VERSION:
                raise ValueError("comparison_requires_current_model_baseline")
            original = baseline_result["config"]
            for key in ("ir_maxpf", "reserve_activation", "empty_slots", "availability_scenario", "scoring_contract"):
                if cfg[key] != config(original)[key]:
                    raise ValueError("scenario_requires_new_eligibility_snapshot")
            snapshot = json.loads(baseline["snapshot_json"])
        row = store.create(uid, league_id, {"league_user_id": str(league_user_id(sess)), "config": cfg,
                           "kind": "scenario", "baseline_run_id": baseline_id}, snapshot=snapshot)
        return jsonify(public(row)), 202

    @app.route("/api/leagues/<league_id>/projection-runs/latest", methods=["GET"])
    @guarded
    def league_projection_latest(sess, league_id):
        uid, current_league = identity(sess)
        if league_id != current_league:
            return jsonify(error="not_found"), 404
        result = batch.view(uid, league_id)
        if platform(sess) != "sleeper":
            result.update(state="unsupported_policy", reason="sleeper_only", run=None, attempt=None, next_attempt_not_before=None)
        run = public(result["run"]) if result["run"] else None
        attempt = run if result["attempt"] is result["run"] else (public(result["attempt"]) if result["attempt"] else None)
        return jsonify({**result, "run": run, "attempt": attempt})

    @app.route("/api/projection-runs/<run_id>", methods=["GET"])
    @guarded
    def league_projection_get(sess, run_id):
        row = load(sess, run_id)
        if not row:
            return jsonify(error="not_found"), 404
        return jsonify(public(row))

    @app.route("/api/projection-runs/<run_id>/cancel", methods=["POST"])
    @guarded
    def league_projection_cancel(sess, run_id):
        if not load(sess, run_id):
            return jsonify(error="not_found"), 404
        store.cancel(run_id, *identity(sess))
        return jsonify(public(load(sess, run_id)))

    @app.route("/api/projection-runs/<run_id>/teams", methods=["GET"])
    @app.route("/api/projection-runs/<run_id>/draft", methods=["GET"])
    @app.route("/api/projection-runs/<run_id>/teams/<int:roster_id>/weeks", methods=["GET"])
    @guarded
    def league_projection_details(sess, run_id, roster_id=None):
        row = load(sess, run_id)
        if not row:
            return jsonify(error="not_found"), 404
        if row["status"] != "complete":
            return jsonify(public(row)), 409
        result = json.loads(row["result_json"])
        if roster_id is not None:
            team = next((t for t in result["teams"] if t["roster_id"] == roster_id), None)
            return (jsonify(weeks=team["weeks"]) if team else (jsonify(error="not_found"), 404))
        return jsonify(teams=result["teams"], config=result["config"], model_version=result["model_version"])

    @app.route("/api/projection-runs/<run_id>/export/<kind>", methods=["GET"])
    @guarded
    def league_projection_export(sess, run_id, kind):
        row = load(sess, run_id)
        if not row or kind not in {"manifest", "csv"}:
            return jsonify(error="not_found"), 404
        if row["status"] != "complete":
            return jsonify(public(row)), 409
        result = json.loads(row["result_json"])
        if kind == "manifest":
            return jsonify({"run_id": run_id, "input_hash": row["input_hash"],
                            "projection_coverage": [{"roster_id": t["roster_id"], "weeks": [{"week": w["week"], **w.get("projection_coverage", {})} for w in t["weeks"]]} for t in result["teams"]],
                            "joint_model_diagnostics": [{"roster_id": t["roster_id"], "weeks": [{"week": w["week"], **w.get("maxpf_floor", {})} for w in t["weeks"]]} for t in result["teams"]],
                            **{key: result[key] for key in ("schema", "model_version", "config", "seed", "iterations", "snapshot_hash", "source", "captured_at", "coverage", "warnings")}})
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["original_roster_id", "current_owner_roster_id", "playoff_probability", "nonplayoff_probability", "maxpf_mean", "conditional_expected_pick", "nonplayoff_samples"])
        for team in result["teams"]:
            writer.writerow([team[k] for k in ("roster_id", "pick_owner_roster_id", "playoff_probability", "nonplayoff_probability", "maxpf_mean", "conditional_expected_pick", "nonplayoff_samples")])
        return Response(out.getvalue(), mimetype="text/csv", headers={"Content-Disposition": 'attachment; filename="league-projections.csv"'})
