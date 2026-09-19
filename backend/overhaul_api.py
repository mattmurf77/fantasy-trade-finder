"""Team overhaul routes (`/api/overhauls`), installed on the existing Flask app.

Contract: docs/plans/team-overhaul/BUILD-CONTRACT.md §7. Every route needs an
initialized session plus the verified read/write gates; every overhaul is
scoped to (account_user_id, league_id) and anything else is 404 `not_found`.
The flag `overhaul.enabled` gates only create / generate / assemble / send.
Server-private helpers arrive as keyword callables from `server.py`, the
same seam `win_now_api.install` uses. `fetch_json` (the Sleeper GET) is
optional: with it the snapshot reads current pick holders live; without it
picks come from the DB table and refresh refuses to terminalize on them.

Sends (2026-09-07, all platforms): each attempt dispatches through the
platform's extracted propose core — `sleeper_propose` / `mfl_propose` /
`espn_propose` — behind that platform's own send flag (`service.SEND_FLAGS`).
`platform_rosters` is the fresh MFL/ESPN roster read; when it is absent or
fails the snapshot is stamped `roster_source: session` and refresh never
terminalizes an attempt from it.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from functools import wraps

from flask import jsonify, request

from . import overhaul_service as service
from . import overhaul_store as store
from .feature_flags import is_enabled

log = logging.getLogger(__name__)

# In-process only (one gunicorn worker on purpose): prepare tokens and the
# per-overhaul refresh throttle. Neither survives a restart, by design.
_PREPARES: dict[str, dict] = {}
_REFRESH_AT: dict[str, float] = {}
_PREPARE_TTL_S = 120.0
_REFRESH_MIN_INTERVAL_S = 15.0

_400 = frozenset(("bad_request", "asset_not_owned", "generic_pick_not_allowed"))


class _Conflict(Exception):
    def __init__(self, code, detail=None, status=409, **extra):
        super().__init__(code)
        self.code, self.detail, self.status, self.extra = code, detail, status, extra


def _error(code, detail=None, status=409, **extra):
    body = {"error": code}
    if detail is not None:
        body["detail"] = detail
    body.update(extra)
    return jsonify(body), status


def _past(stamp) -> bool:
    """True when an ISO timestamp is in the past; unparseable/naive -> False
    (the same leniency GET /api/espn/link applies to `expires_hint_at`)."""
    if not stamp:
        return False
    try:
        return datetime.fromisoformat(str(stamp)) <= datetime.now(timezone.utc)
    except Exception:
        return False


def install(app, *, require_session, read_denial, write_denial, active_format, league_user_id,
            owner_generation_context, generate, roster_context, sleeper_propose, fetch_rosters,
            roster_id_for_owner, load_picks, pick_source_platform, draft_context, card_to_dict,
            is_pick_asset, owned_picks_available, inject_owned_picks, pick_label, slot_order,
            priced_pick_value, elo_to_value, sleeper_credential, sleeper_write, record_event,
            fetch_json=None, mfl_propose=None, espn_propose=None, mfl_credential=None,
            espn_credential=None, platform_rosters=None):

    # ── plumbing ────────────────────────────────────────────────────────
    def guarded(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except service.ValidationError as exc:
                return _error(exc.code, exc.detail, 400 if exc.code in _400 else 409)
            except _Conflict as exc:
                return _error(exc.code, exc.detail, exc.status, **exc.extra)
        return wrapper

    def session(write=False):
        sess = require_session()
        denial = read_denial(sess) or (write_denial(sess) if write else None)
        return sess, denial

    def flag():
        if not is_enabled("overhaul.enabled"):
            raise _Conflict("feature_disabled", status=404)

    def body():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise service.ValidationError("bad_request", "invalid json body")
        return data

    def load(sess, overhaul_id):
        row = store.get_overhaul(overhaul_id)
        if (row is None or row["account_user_id"] != str(sess["user_id"])
                or row["league_id"] != str(sess["league"].league_id)):
            raise _Conflict("not_found", status=404)
        return row

    def check_revision(row, data):
        if data.get("revision") != row["revision"]:
            raise _Conflict("stale_revision", {"revision": row["revision"]})

    def league_platform(sess):
        return str(getattr(sess["league"], "platform", "sleeper") or "sleeper").lower()

    def is_pick(league_id):
        return lambda a: bool(is_pick_asset(league_id, a))

    def fire(sess, name, props):
        try:
            record_event(str(sess["user_id"]), name, source="api", league_id=str(sess["league"].league_id),
                         device_type=request.headers.get("X-Device") or "web", props=props)
        except Exception as exc:  # pragma: no cover — analytics must never break the route
            log.warning("record_event(%s) failed: %s", name, exc)

    # ── snapshot / recovery / capabilities ──────────────────────────────
    def pick_rows(league_id):
        if league_id == "league_demo":
            return []
        try:
            return list(load_picks(league_id, source=pick_source_platform) or [])
        except Exception as exc:
            log.warning("overhaul: pick load failed: %s", exc)
            return []

    def live_pick_owners(league_id, rows, raw):
        """pick_id -> current holder's user id, or None when unavailable.

        Same ground truth the propose route uses (`_sleeper_encode_ftf_picks`):
        the public traded_picks list overlaid on "original roster holds by
        default", holder roster -> owner via the live rosters. A failed fetch
        is None, never [] — an empty list would make every pick look untraded
        and let a recovery (own-original) pick confirm itself.
        """
        if fetch_json is None or not rows or not raw:
            return None
        try:
            traded = fetch_json(f"https://api.sleeper.app/v1/league/{league_id}/traded_picks")
        except Exception as exc:
            log.warning("overhaul: traded_picks unavailable for %s: %s", league_id, exc)
            return None
        if not isinstance(traded, list):
            return None
        index = {}
        for tp in traded:
            try:
                index[(int(tp["season"]), int(tp["round"]), str(tp["roster_id"]))] = str(int(tp["owner_id"]))
            except (TypeError, ValueError, KeyError):
                continue
        owner_of = {str(r.get("roster_id")): str(r.get("owner_id") or "") for r in raw}
        out = {}
        for r in rows:
            try:
                key = (int(r["season"]), int(r["round"]), str(r["original_roster_id"]))
            except (TypeError, ValueError, KeyError):
                continue
            out[str(r.get("pick_id"))] = owner_of.get(index.get(key, key[2]), "")
        return out

    def capture_snapshot(sess):
        league = sess["league"]
        league_id = str(league.league_id)
        platform = league_platform(sess)
        lu_id = str(league_user_id(sess))
        rosters, my_players, my_roster_id = {}, None, None
        raw = None
        if league_id != "league_demo":
            if platform == "sleeper":
                raw = fetch_rosters(league_id)
            elif platform in service.SEND_FLAGS and platform_rosters is not None:
                raw = platform_rosters(sess, league_id, platform)   # None when no fresh read is possible
        if raw:
            for r in raw:
                owner = str(r.get("owner_id") or "")
                if owner:
                    rosters[owner] = [str(p) for p in (r.get("players") or []) if p]
            my_roster_id = roster_id_for_owner(raw, lu_id)
            if my_roster_id is not None:
                for r in raw:
                    if str(r.get("roster_id")) == str(my_roster_id):
                        my_players = [str(p) for p in (r.get("players") or []) if p]
        else:
            for m in getattr(league, "members", []) or []:
                rosters[str(m.user_id)] = [str(p) for p in (m.roster or [])]
        if my_players is None:
            my_players = [str(p) for p in (sess.get("user_roster") or []) if not is_pick_asset(league_id, p)]
        rosters[lu_id] = list(my_players)
        rows = pick_rows(league_id)
        live = live_pick_owners(league_id, rows, raw) if raw and platform == "sleeper" else None
        my_picks = []
        for r in rows:
            pid = str(r.get("pick_id"))
            owner = live.get(pid, "") if live is not None else str(r.get("owner_user_id") or "")
            if owner:
                rosters.setdefault(owner, []).append(pid)
            if owner == lu_id:
                my_picks.append(pid)
        ctx = draft_context(league_id) or {}
        snapshot = {"captured_at": store.db._now(), "season": ctx.get("season"),
                    "my_roster_ids": my_players, "my_pick_ids": my_picks, "rosters": rosters,
                    "picks_supported": platform != "espn", "source": platform,
                    "pick_ownership_source": "live" if live is not None else "db",
                    "roster_source": "live" if raw else "session",
                    "my_roster_id": my_roster_id}
        return snapshot, rows

    def compute_recovery(sess, settings, snapshot, rows):
        return service.recovery_requirement(
            outlook=settings.get("outlook"), season=snapshot.get("season"), picks=rows,
            my_user_id=league_user_id(sess), my_roster_id=snapshot.get("my_roster_id"),
            picks_supported=bool(snapshot.get("picks_supported")))

    def owned_ids(snapshot):
        return list(snapshot.get("my_roster_ids") or []) + list(snapshot.get("my_pick_ids") or [])

    def auth_state(sess):
        """Per-platform link state, mirroring each platform's link-status GET."""
        platform = league_platform(sess)
        user_id = str(sess["user_id"])
        if platform == "sleeper":
            cred = sleeper_credential(user_id)
            if not cred:
                return "unlinked"
            try:
                token = sleeper_write.decrypt_token(cred["token_encrypted"])
            except Exception:
                return "unlinked"
            if sleeper_write.is_expired(token):
                return "expired"
        elif platform == "mfl":
            # GET /api/mfl/auth-link: a stored cookie row OR the key-less
            # session-only copy. MFL stamps no expiry — a dead cookie surfaces
            # as `mfl_auth_expired` from the core at send time.
            cred = None
            if mfl_credential is not None:
                try:
                    cred = mfl_credential(user_id)
                except Exception:
                    cred = None
            if not cred and not sess.get("mfl_cookie"):
                return "unlinked"
        elif platform == "espn":
            # GET /api/espn/link: both cookie halves AND a verified_at stamp;
            # an `expires_hint_at` in the past reads as expired.
            cred = espn_credential(user_id) if espn_credential is not None else None
            if not cred or not cred.get("swid") or not cred.get("verified_at"):
                return "unlinked"
            if _past(cred.get("expires_hint_at")):
                return "expired"
        else:
            return "n/a"
        return "linked" if sess.get("verified") else "unverified"

    def capabilities(sess):
        platform = league_platform(sess)
        state = auth_state(sess)
        flag = service.SEND_FLAGS.get(platform)
        return {"platform": platform,
                "can_propose": state == "linked" and flag is not None and is_enabled(flag),
                "can_propose_picks": platform in service.PICK_SEND_PLATFORMS,
                "can_read_terminal_status": False, "can_withdraw": False,
                # Owner-confirmed 2026-09-07: Sleeper accepts the same asset in
                # concurrent offers to different teams. MFL/ESPN unexercised.
                "supports_conflicting_offer_race": "supported" if platform == "sleeper" else "unverified",
                "auth_state": state, "checked_at": store.db._now()}

    def send_core(platform):
        return {"sleeper": sleeper_propose, "mfl": mfl_propose, "espn": espn_propose}.get(platform)

    # ── generation inputs (built the way the deck / asset-ideas routes do) ──
    def generation_inputs(sess):
        league = sess["league"]
        league_id = str(league.league_id)
        fmt = active_format(sess)
        ranking = (sess.get("services") or {}).get(fmt) or sess.get("service")
        trade_svc = (sess.get("trade_svcs") or {}).get(fmt) or sess.get("trade_svc")
        players = sess.get("players")
        roster = sess.get("user_roster")
        if not (ranking and trade_svc and players and roster):
            raise _Conflict("bad_request", "session_missing_state", status=400)
        rankings = ranking.get_rankings(position=None)
        user_elo = {rp.player.id: rp.elo for rp in rankings.rankings}
        seed_map = dict(getattr(ranking, "_seed", None) or {})
        players_dict = {p.id: p for p in players}
        roster = list(roster)
        if owned_picks_available(league_id, league):
            try:
                seed_map, roster, _n = inject_owned_picks(
                    league_id=league_id, scoring_format=fmt, trade_service=trade_svc,
                    players_dict=players_dict, seed_map=seed_map, user_elo=user_elo,
                    user_id=str(sess["user_id"]), user_roster=roster, league=league)
            except Exception as exc:
                log.warning("overhaul: owned-pick injection failed (continuing): %s", exc)
        return {"service": ranking, "players": players_dict, "seed_map": seed_map, "user_elo": user_elo,
                "user_roster": roster, "scoring_format": fmt, "fairness_threshold": 0.5, "league": league}

    def build_context(sess, inputs, settings):
        try:
            ctx = owner_generation_context(
                sess=sess, service=inputs["service"], league=inputs["league"], players=inputs["players"],
                seed_map=inputs["seed_map"], user_elo=inputs["user_elo"], user_roster=inputs["user_roster"],
                scoring_format=inputs["scoring_format"], fairness_threshold=inputs["fairness_threshold"])
        except Exception as exc:
            log.exception("overhaul: generation context unavailable")
            raise _Conflict("bad_request", "generation_context_unavailable", status=400) from exc
        # Plan-scoped overrides live in the ctx dict only; league preferences are never written.
        ctx["outlook"] = service.OUTLOOK_TO_ENGINE.get(settings.get("outlook"))
        ctx["acquire_positions"] = list(settings.get("preferred_positions") or [])
        return ctx

    def legality_fn(sess, inputs, settings, rows, chosen):
        """(check, capacity): final-union legality per counterparty via trade_roster.

        `chosen` is [(package_id, offer)]. Returns (None, None) when the
        roster context cannot be built — the receipt then reports
        `capacity_unknown` rather than a false pass.
        """
        try:
            ctx = roster_context(sess=sess, league=inputs["league"], players=inputs["players"],
                                 seed_map=inputs["seed_map"], scoring_format=inputs["scoring_format"],
                                 outlook=service.OUTLOOK_TO_ENGINE.get(settings.get("outlook")),
                                 opponent_outlooks={}, picks=rows,
                                 explicit_outlook=service.OUTLOOK_TO_ENGINE.get(settings.get("outlook")))
        except Exception as exc:
            log.warning("overhaul: roster context unavailable: %s", exc)
            return None, None
        if ctx is None:
            return None, None
        from dataclasses import replace
        from .trade_roster import evaluate

        def check(cp, give, receive):
            viewer, partner = ctx.teams.get(ctx.viewer_id), ctx.teams.get(str(cp))
            if viewer is None or partner is None:
                return {"unknowns": ["missing_team"]}
            # A tie partner is an alternative to this counterparty's offer, not
            # an additional trade: only OTHER packages' offers shape the union.
            own = {pid for pid, o in chosen if str(o["counterparty_user_id"]) == str(cp)}
            others = [o for pid, o in chosen if str(o["counterparty_user_id"]) != str(cp) and pid not in own]
            others_out = {a for o in others for a in o["give_ids"]}
            others_in = {a for o in others for a in o["receive_ids"]}
            union = replace(viewer, roster=tuple(sorted((set(viewer.roster) - others_out) | others_in)))
            res = evaluate(viewer=union, partner=partner, give=list(give), receive=list(receive),
                           assets=ctx.assets, rules=ctx.rules)
            blockers, unknowns = [], list(res.get("unknowns") or [])
            for team in (res.get("teams") or {}).values():
                blockers += team.get("blockers") or []
                unknowns += team.get("unknowns") or []
            return {"blockers": blockers, "unknowns": unknowns}
        return check, getattr(ctx.rules, "capacity", None)

    # ── views ───────────────────────────────────────────────────────────
    def offer_view(o):
        return {"offer_id": o["offer_id"], "is_recovery": bool(o["is_recovery"]), "decision": o["decision"],
                "availability": o["availability"], "counterparty_user_id": o["counterparty_user_id"],
                "counterparty_username": o.get("counterparty_username") or "",
                "give_ids": list(o["give_ids"]), "receive_ids": list(o["receive_ids"]), "card": o["card"]}

    def attempt_view(a):
        return {"attempt_id": a["attempt_id"], "batch_id": a["batch_id"], "package_id": a["package_id"],
                "tier": a["tier"], "offer_id": a["offer_id"], "state": a["state"],
                "state_source": a["state_source"], "provider_transaction_id": a.get("provider_transaction_id"),
                "provider_status": a.get("provider_status"),
                "error": a.get("error"), "created_at": a["created_at"], "updated_at": a["updated_at"],
                "observed_at": a.get("observed_at")}

    def progress(offers):
        fresh = [o for o in offers if o["availability"] == "fresh"]
        return {"decided": sum(1 for o in fresh if o["decision"] != "undecided"), "total": len(fresh),
                "liked": sum(1 for o in fresh if o["decision"] == "like")}

    def roadmap_view(rm, offers_by_id, attempts):
        packages = []
        for pkg in rm["packages"]:
            packages.append(dict(pkg, status=service.package_status(pkg, offers_by_id, attempts)))
        ids = [oid for pkg in packages for t in pkg["tiers"] for oid in t["offer_ids"]]
        summary = {k: rm["summary"].get(k) for k in
                   ("outgoing_ids", "incoming_ids", "counterparties", "unused_eligible_ids", "score", "diversity_key")}
        return {"roadmap_id": rm["roadmap_id"], "version": rm["version"], "packages": packages,
                "compat": rm["compat"], "summary": summary, "rank": int(rm["summary"].get("rank") or 0),
                "offers": {oid: offer_view(offers_by_id[oid]) for oid in ids if oid in offers_by_id}}

    def recovery_view(row, roadmaps, offers_by_id):
        rec = dict(row.get("recovery") or service.recovery_requirement(
            outlook=None, season=None, picks=[], my_user_id=""))
        resolved = False
        selected = next((r for r in roadmaps if r["roadmap_id"] == row.get("selected_roadmap_id")), None)
        if rec.get("applicable") and selected:
            for pkg in selected["packages"]:
                for t in pkg["tiers"]:
                    for oid in t["offer_ids"]:
                        o = offers_by_id.get(oid)
                        if o and o["is_recovery"] and o["decision"] == "like" and o["availability"] == "fresh":
                            resolved = True
        rec["resolved"] = resolved
        return rec

    def eligible_assets(sess, row):
        league_id = row["league_id"]
        snapshot = row.get("snapshot") or {}
        settings = row["settings"]
        fmt = active_format(sess)
        ranking = (sess.get("services") or {}).get(fmt) or sess.get("service")
        seed = dict(getattr(ranking, "_seed", None) or {}) if ranking else {}
        players = {p.id: p for p in (sess.get("players") or [])}
        out = []
        for pid in snapshot.get("my_roster_ids") or []:
            p = players.get(pid)
            if p is None:
                continue
            out.append({"id": pid, "kind": "player", "name": p.name, "position": p.position, "team": p.team,
                        "age": getattr(p, "age", None) or None,
                        "value": round(float(elo_to_value(seed.get(pid, 1500.0))), 1)})
        mine = set(snapshot.get("my_pick_ids") or [])
        pick_meta = {}
        if mine:
            order = slot_order(league_id)
            for r in pick_rows(league_id):
                pid = str(r.get("pick_id"))
                if pid not in mine:
                    continue
                pick_meta[pid] = {"round": r.get("round"), "season": r.get("season")}
                out.append({"id": pid, "kind": "pick", "name": pick_label(r, order), "position": "PICK",
                            "team": None, "age": None, "value": round(float(priced_pick_value(r, order, fmt) or 0.0), 1),
                            "label": pick_label(r, order)})
        return service.recommend_assets(out, outlook=settings.get("outlook"), pick_budget=settings.get("pick_budget"),
                                        pick_meta=pick_meta, scoring_format=fmt)

    def generation_view(row):
        gen = row.get("generation")
        if not gen:
            return {"state": "idle", "revision": row["revision"], "new_offers": 0, "total_offers": 0,
                    "pool_rejections": 0, "shortfall_reason": None, "budget_exhausted": False}
        return gen

    def overhaul_view(sess, row):
        offers = store.list_offers(row["overhaul_id"])
        by_id = {o["offer_id"]: o for o in offers}
        attempts = store.list_attempts(row["overhaul_id"])
        roadmaps = store.current_roadmaps(row["overhaul_id"])
        snap = row.get("snapshot") or {}
        return {"overhaul_id": row["overhaul_id"], "league_id": row["league_id"], "platform": row["platform"],
                "status": row["status"], "revision": row["revision"], "settings": row["settings"],
                "snapshot": {"captured_at": snap.get("captured_at"), "season": snap.get("season"),
                             "picks_supported": bool(snap.get("picks_supported"))},
                "recovery": recovery_view(row, roadmaps, by_id), "generation": generation_view(row),
                "selected_roadmap_id": row.get("selected_roadmap_id"),
                "roadmaps": [roadmap_view(r, by_id, attempts) for r in roadmaps],
                "progress": progress(offers), "attempts": [attempt_view(a) for a in attempts],
                "capabilities": capabilities(sess), "eligible_assets": eligible_assets(sess, row)}

    def live_attempts(overhaul_id):
        return [a for a in store.list_attempts(overhaul_id) if a["state"] in service.LIVE_ATTEMPT_STATES]

    def effective_pool(row):
        return [a for a in row["settings"].get("eligible_asset_ids") or [] if a in set(owned_ids(row.get("snapshot") or {}))]

    # ── routes ──────────────────────────────────────────────────────────
    @app.route("/api/overhauls", methods=["POST"])
    @guarded
    def overhaul_create_route():
        flag()
        sess, denial = session(write=True)
        if denial is not None:
            return denial
        data = body()
        league_id = str(data.get("league_id") or "")
        client_key = data.get("client_key")
        if league_id != str(sess["league"].league_id) or not isinstance(client_key, str) or not client_key:
            raise service.ValidationError("bad_request", "league_id and client_key required")
        user_id = str(sess["user_id"])
        existing = store.find_by_client_key(user_id, league_id, client_key)
        if existing is not None:
            return jsonify(overhaul_view(sess, existing)), 200
        active = store.find_active(user_id, league_id)
        if active is not None:
            if live_attempts(active["overhaul_id"]):
                raise _Conflict("active_sends_exist", overhaul_id=active["overhaul_id"])
            store.update_overhaul(active["overhaul_id"], status="archived")
        snapshot, rows = capture_snapshot(sess)
        settings = service.default_settings()
        row = store.create_overhaul(account_user_id=user_id, league_user_id=league_user_id(sess),
                                    league_id=league_id, platform=league_platform(sess),
                                    scoring_format=active_format(sess), client_key=client_key,
                                    settings=settings, snapshot=snapshot,
                                    recovery=compute_recovery(sess, settings, snapshot, rows))
        return jsonify(overhaul_view(sess, row)), 201

    @app.route("/api/overhauls", methods=["GET"])
    @guarded
    def overhaul_active_route():
        sess, denial = session()
        if denial is not None:
            return denial
        league_id = request.args.get("league_id") or str(sess["league"].league_id)
        if league_id != str(sess["league"].league_id):
            raise _Conflict("not_found", status=404)
        row = store.find_active(str(sess["user_id"]), league_id)
        return jsonify({"active": overhaul_view(sess, row) if row else None})

    @app.route("/api/overhauls/<overhaul_id>", methods=["GET"])
    @guarded
    def overhaul_get_route(overhaul_id):
        sess, denial = session()
        if denial is not None:
            return denial
        return jsonify(overhaul_view(sess, load(sess, overhaul_id)))

    @app.route("/api/overhauls/<overhaul_id>/settings", methods=["PUT"])
    @guarded
    def overhaul_settings_route(overhaul_id):
        sess, denial = session(write=True)
        if denial is not None:
            return denial
        row = load(sess, overhaul_id)
        data = body()
        check_revision(row, data)
        settings = service.merge_settings(row["settings"], data.get("settings") or {},
                                          owned_ids=owned_ids(row.get("snapshot") or {}))
        fields = {}
        if service.settings_invalidate_offers(row["settings"], settings):
            store.mark_undecided_stale(row["overhaul_id"])
            if row.get("generation"):
                # A new outlook / pool is a new search: nothing is exhausted yet.
                fields["generation"] = dict(row["generation"], exhausted_subsets=[])
        recovery = compute_recovery(sess, settings, row.get("snapshot") or {}, pick_rows(row["league_id"]))
        store.update_overhaul(row["overhaul_id"], settings=settings, recovery=recovery, revision=row["revision"] + 1,
                              **fields)
        return jsonify(overhaul_view(sess, store.get_overhaul(row["overhaul_id"])))

    @app.route("/api/overhauls/<overhaul_id>/generate", methods=["POST"])
    @guarded
    def overhaul_generate_route(overhaul_id):
        flag()
        sess, denial = session(write=True)
        if denial is not None:
            return denial
        row = load(sess, overhaul_id)
        data = body()
        check_revision(row, data)
        settings = row["settings"]
        if settings.get("outlook") not in service.OUTLOOKS:
            raise service.ValidationError("bad_request", "outlook_required")
        snapshot, rows = capture_snapshot(sess)
        recovery = compute_recovery(sess, settings, snapshot, rows)
        store.update_overhaul(row["overhaul_id"], snapshot=snapshot, recovery=recovery)
        row = store.get_overhaul(row["overhaul_id"])
        pool = effective_pool(row)
        league_id = row["league_id"]
        user_id = str(sess["user_id"])
        prev = row.get("generation") or {}
        exhausted = [tuple(s) for s in prev.get("exhausted_subsets") or []]
        gen = {"state": "completed", "revision": row["revision"], "new_offers": 0, "total_offers": 0,
               "pool_rejections": 0, "exhausted_subsets": [list(s) for s in exhausted],
               "shortfall_reason": None, "budget_exhausted": False}
        if not pool:
            gen["shortfall_reason"] = "stale_ownership" if settings.get("eligible_asset_ids") else "budget_restriction"
            gen["total_offers"] = len(store.list_offers(row["overhaul_id"]))
            store.update_overhaul(row["overhaul_id"], generation=gen)
            return jsonify({"generation": gen, "offers": []})
        inputs = generation_inputs(sess)
        ctx = build_context(sess, inputs, settings)
        pick_fn = is_pick(league_id)
        pick_meta = {str(r.get("pick_id")): {"round": r.get("round"), "season": r.get("season")} for r in rows}
        values = {a: float(elo_to_value(inputs["seed_map"].get(a, 1500.0))) for a in pool}
        subsets = service.enumerate_subsets(pool, values=values, outlook=settings["outlook"], is_pick=pick_fn,
                                            pick_budget=settings.get("pick_budget"), pick_meta=pick_meta,
                                            exhausted=exhausted)
        by_hash = {o["package_hash"]: o for o in store.list_offers(row["overhaul_id"])}
        known = set(by_hash)
        deadline = time.monotonic() + service.OVERHAUL_GENERATION_BUDGET_S
        players_dict = inputs["players"]
        new_offers = 0

        def normalize(cards, *, is_recovery):
            nonlocal new_offers
            kept, rejected = service.filter_cards(cards, pool=pool, seller_user_id=user_id)
            gen["pool_rejections"] += rejected
            kept = [c for c in kept if service.receive_side_allowed(
                c.receive_player_ids, outlook=settings["outlook"], rebuild_return=settings.get("rebuild_return"),
                is_pick=pick_fn)]
            if settings.get("outlook") == "blow_it_up" and settings.get("rebuild_return") == "young_players":
                kept.sort(key=lambda c: (service.average_age(c.receive_player_ids, players_dict) is None,
                                         service.average_age(c.receive_player_ids, players_dict) or 0.0))
            for card in kept:
                h = service.package_hash(platform=row["platform"], league_id=league_id, seller_user_id=user_id,
                                         counterparty_user_id=card.target_user_id,
                                         give_ids=card.give_player_ids, receive_ids=card.receive_player_ids)
                if h in known:
                    prior = by_hash.pop(h, None)
                    if prior and prior["decision"] == "undecided" and prior["availability"] == "stale":
                        # Same package, new revision: re-surface it instead of dropping the card.
                        store.refresh_offer(prior["offer_id"], row["revision"])
                        new_offers += 1
                    continue
                evidence = getattr(card, "owner_evaluation", None)
                inserted = store.insert_offer(
                    overhaul_id=row["overhaul_id"], revision=row["revision"], package_hash=h,
                    counterparty_user_id=card.target_user_id, counterparty_username=card.target_username,
                    give_ids=card.give_player_ids, receive_ids=card.receive_player_ids,
                    card=card_to_dict(card, players_dict),
                    evidence=evidence.as_dict() if evidence is not None else None, is_recovery=is_recovery)
                known.add(h)
                if inserted is not None:
                    new_offers += 1

        def run(subset, **overrides):
            try:
                result = generate(**dict(ctx, pinned_give_players=list(subset), exact_give=True, max_cards=3, **overrides))
            except Exception as exc:
                log.warning("overhaul: generator failed for %s: %s", subset, exc)
                return []
            cards = result[0] if isinstance(result, tuple) else result
            return list(cards or [])

        remaining = list(subsets)
        for subset in subsets:
            if time.monotonic() > deadline:
                gen["budget_exhausted"] = True
                break
            normalize(run(subset), is_recovery=False)
            exhausted.append(tuple(subset))
            remaining.remove(subset)
            if new_offers >= service.OVERHAUL_BATCH_SIZE:
                break
        if recovery.get("state") == "missing_with_known_holder" and time.monotonic() <= deadline:
            for subset in subsets[:6]:
                normalize(run(subset, opponent_user_id=recovery["holder_user_id"],
                              pinned_receive_players=[recovery["pick_id"]]), is_recovery=True)
        offers = store.list_offers(row["overhaul_id"])
        gen.update(new_offers=new_offers, total_offers=len(offers), exhausted_subsets=[list(s) for s in exhausted])
        if new_offers == 0:
            gen["shortfall_reason"] = ("budget_restriction" if gen["budget_exhausted"]
                                       else "search_exhausted" if not remaining else "no_return_supply")
        store.update_overhaul(row["overhaul_id"], generation=gen,
                              status="reviewing" if row["status"] == "setup" else row["status"])
        compatible, _ = service.assemble_roadmaps(offers, pool=pool, target_package_count=settings.get("target_package_count"))
        fire(sess, "overhaul_generation_completed",
             {"overhaul_id": row["overhaul_id"], "candidate_count": new_offers,
              "compatible_roadmap_count": len(compatible), "shortfall_reason": gen["shortfall_reason"]})
        fresh = [offer_view(o) for o in offers if o["decision"] == "undecided" and o["availability"] == "fresh"
                 and o["revision"] == row["revision"]]
        return jsonify({"generation": gen, "offers": fresh})

    @app.route("/api/overhauls/<overhaul_id>/offers", methods=["GET"])
    @guarded
    def overhaul_offers_route(overhaul_id):
        sess, denial = session()
        if denial is not None:
            return denial
        row = load(sess, overhaul_id)
        which = request.args.get("decision") or "undecided"
        if which not in ("undecided", "like", "pass", "all"):
            raise service.ValidationError("bad_request", "invalid decision filter")
        offers = store.list_offers(row["overhaul_id"])
        if which == "undecided":
            picked = [o for o in offers if o["decision"] == "undecided" and o["availability"] == "fresh"]
        elif which == "all":
            picked = offers
        else:
            picked = [o for o in offers if o["decision"] == which]
        return jsonify({"offers": [offer_view(o) for o in picked], "progress": progress(offers)})

    @app.route("/api/overhauls/<overhaul_id>/decisions", methods=["POST"])
    @guarded
    def overhaul_decisions_route(overhaul_id):
        sess, denial = session(write=True)
        if denial is not None:
            return denial
        row = load(sess, overhaul_id)
        data = body()
        check_revision(row, data)
        decisions = data.get("decisions")
        if not isinstance(decisions, list):
            raise service.ValidationError("bad_request", "decisions must be a list")
        by_id = {o["offer_id"]: o for o in store.list_offers(row["overhaul_id"])}
        for item in decisions:
            if not isinstance(item, dict):
                raise service.ValidationError("bad_request", "invalid decision")
            offer = by_id.get(str(item.get("offer_id") or ""))
            decision, key = item.get("decision"), item.get("client_key")
            if offer is None or decision not in service.DECISIONS or not isinstance(key, str) or not key:
                raise service.ValidationError("bad_request", "invalid decision")
            if offer["decision_client_key"] == key and offer["decision"] == decision:
                continue  # idempotent replay
            # Plan review is not taste learning: no swipe / Elo path here.
            store.set_decision(offer["offer_id"], decision, key)
        return jsonify({"progress": progress(store.list_offers(row["overhaul_id"]))})

    @app.route("/api/overhauls/<overhaul_id>/assemble", methods=["POST"])
    @guarded
    def overhaul_assemble_route(overhaul_id):
        flag()
        sess, denial = session(write=True)
        if denial is not None:
            return denial
        row = load(sess, overhaul_id)
        data = body()
        check_revision(row, data)
        if live_attempts(row["overhaul_id"]):
            raise _Conflict("active_sends_exist", overhaul_id=row["overhaul_id"])
        offers = store.list_offers(row["overhaul_id"])
        by_id = {o["offer_id"]: o for o in offers}
        pool = effective_pool(row)
        recovery = row.get("recovery") or {}
        roadmaps, shortfall = service.assemble_roadmaps(
            offers, pool=pool, target_package_count=row["settings"].get("target_package_count"), recovery=recovery)
        if not roadmaps:
            return jsonify({"roadmaps": [], "shortfall": shortfall})
        store.retire_roadmaps(row["overhaul_id"])
        snapshot = row.get("snapshot") or {}
        stored = []
        for rm in roadmaps:
            selected = service.default_send_selection(rm["packages"], by_id, [])
            receipt = service.validate_prepare(
                selected=selected, packages=rm["packages"], offers_by_id=by_id,
                my_roster_ids=snapshot.get("my_roster_ids") or [], my_pick_ids=snapshot.get("my_pick_ids") or [],
                pool=pool, rosters=snapshot.get("rosters") or {}, reserved_asset_ids=[], capacity=None,
                recovery=recovery, package_states={}, legality=None, checked_at=store.db._now(),
                is_pick=is_pick(row["league_id"]))
            summary = dict(rm["summary"], rank=rm["rank"])
            stored.append(store.insert_roadmap(overhaul_id=row["overhaul_id"], roadmap_id=service.new_id("rm_"),
                                               version=1, revision=row["revision"], packages=rm["packages"],
                                               compat=receipt, summary=summary))
        store.update_overhaul(row["overhaul_id"], selected_roadmap_id=None,
                              status="reviewing" if row["status"] == "assembled" else row["status"])
        attempts = store.list_attempts(row["overhaul_id"])
        return jsonify({"roadmaps": [roadmap_view(r, by_id, attempts) for r in stored], "shortfall": None})

    def load_roadmap(row, roadmap_id, data):
        rm = store.get_roadmap(row["overhaul_id"], roadmap_id)
        if rm is None:
            raise _Conflict("not_found", status=404)
        if data.get("version") != rm["version"]:
            raise _Conflict("stale_version", {"version": rm["version"]})
        return rm

    @app.route("/api/overhauls/<overhaul_id>/roadmaps/<roadmap_id>/select", methods=["PUT"])
    @guarded
    def overhaul_select_route(overhaul_id, roadmap_id):
        sess, denial = session(write=True)
        if denial is not None:
            return denial
        row = load(sess, overhaul_id)
        rm = load_roadmap(row, roadmap_id, body())
        status = row["status"] if row["status"] in ("executing", "complete") else "assembled"
        store.update_overhaul(row["overhaul_id"], selected_roadmap_id=rm["roadmap_id"], status=status)
        return jsonify(overhaul_view(sess, store.get_overhaul(row["overhaul_id"])))

    @app.route("/api/overhauls/<overhaul_id>/roadmaps/<roadmap_id>/priorities", methods=["PUT"])
    @guarded
    def overhaul_priorities_route(overhaul_id, roadmap_id):
        sess, denial = session(write=True)
        if denial is not None:
            return denial
        row = load(sess, overhaul_id)
        data = body()
        rm = load_roadmap(row, roadmap_id, data)
        package = next((p for p in rm["packages"] if p["package_id"] == data.get("package_id")), None)
        if package is None:
            raise service.ValidationError("bad_request", "unknown package_id")
        by_id = {o["offer_id"]: o for o in store.list_offers(row["overhaul_id"])}
        tiers = service.validate_priorities(package, data.get("tiers"), by_id)
        packages = [dict(p, tiers=tiers) if p["package_id"] == package["package_id"] else p for p in rm["packages"]]
        new = store.insert_roadmap(overhaul_id=row["overhaul_id"], roadmap_id=rm["roadmap_id"],
                                   version=rm["version"] + 1, revision=rm["revision"], packages=packages,
                                   compat=rm["compat"], summary=rm["summary"])
        return jsonify(roadmap_view(new, by_id, store.list_attempts(row["overhaul_id"])))

    def receipt_for(sess, row, rm, selected, by_id, *, with_legality, caps):
        snapshot = row.get("snapshot") or {}
        attempts = store.list_attempts(row["overhaul_id"])
        states = {p["package_id"]: service.package_status(p, by_id, attempts) for p in rm["packages"]}
        reserved = [r["asset_id"] for r in store.active_reservations(row["league_id"], row["league_user_id"])]
        legality, capacity = None, None
        if with_legality:
            package_of = {oid: p["package_id"] for p in rm["packages"] for t in p["tiers"] for oid in t["offer_ids"]}
            chosen = [(package_of[o], by_id[o]) for o in selected if o in by_id and o in package_of]
            try:
                legality, capacity = legality_fn(sess, generation_inputs(sess), row["settings"],
                                                 pick_rows(row["league_id"]), chosen)
            except _Conflict:
                legality, capacity = None, None
        pick_fn = is_pick(row["league_id"])
        receipt = service.validate_prepare(
            selected=selected, packages=rm["packages"], offers_by_id=by_id,
            my_roster_ids=snapshot.get("my_roster_ids") or [], my_pick_ids=snapshot.get("my_pick_ids") or [],
            pool=effective_pool(row), rosters=snapshot.get("rosters") or {}, reserved_asset_ids=reserved,
            capacity=capacity, recovery=row.get("recovery") or {}, package_states=states,
            legality=legality, checked_at=store.db._now(), is_pick=pick_fn)
        return service.with_blockers(receipt, service.platform_blockers(
            selected=selected, packages=rm["packages"], offers_by_id=by_id, platform=caps["platform"],
            auth_state=caps["auth_state"], picks_sendable=caps["can_propose_picks"], is_pick=pick_fn))

    def handoff_text(selected, by_id):
        lines = []
        for oid in selected:
            o = by_id.get(oid)
            if not o:
                continue
            names = lambda side: ", ".join(str(p.get("name") or p.get("id")) for p in (o["card"].get(side) or []))
            lines.append(f"To {o.get('counterparty_username') or o['counterparty_user_id']}: "
                         f"I give {names('give')}; I get {names('receive')}.")
        return "\n".join(lines)

    @app.route("/api/overhauls/<overhaul_id>/roadmaps/<roadmap_id>/prepare-send", methods=["POST"])
    @guarded
    def overhaul_prepare_route(overhaul_id, roadmap_id):
        sess, denial = session(write=True)
        if denial is not None:
            return denial
        row = load(sess, overhaul_id)
        data = body()
        rm = load_roadmap(row, roadmap_id, data)
        snapshot, rows = capture_snapshot(sess)   # R8.7 — refresh ownership before the preview
        store.update_overhaul(row["overhaul_id"], snapshot=snapshot,
                              recovery=compute_recovery(sess, row["settings"], snapshot, rows))
        row = store.get_overhaul(row["overhaul_id"])
        by_id = {o["offer_id"]: o for o in store.list_offers(row["overhaul_id"])}
        attempts = store.list_attempts(row["overhaul_id"])
        selected = data.get("offer_ids")
        if selected is None:
            selected = service.default_send_selection(rm["packages"], by_id, attempts)
        if not isinstance(selected, list) or not selected:
            raise service.ValidationError("bad_request", "offer_ids required")
        selected = [str(o) for o in selected]
        caps = capabilities(sess)
        receipt = receipt_for(sess, row, rm, selected, by_id, with_legality=True, caps=caps)
        package_of = {oid: p["package_id"] for p in rm["packages"] for t in p["tiers"] for oid in t["offer_ids"]}
        packages = {package_of[o] for o in selected if o in package_of}
        race_rows = []
        for r in service.races(selected, rm["packages"]):
            r["counterparties"] = sorted({by_id[o]["counterparty_user_id"] for o in r["offer_ids"] if o in by_id})
            race_rows.append(r)
        digest = service.summary_hash(selected, roadmap_version=rm["version"], revision=row["revision"])
        token = uuid.uuid4().hex
        expires = time.time() + _PREPARE_TTL_S
        _PREPARES[token] = {"overhaul_id": row["overhaul_id"], "roadmap_id": rm["roadmap_id"],
                            "version": rm["version"], "offer_ids": selected, "summary_hash": digest,
                            "expires": expires}
        mode = service.handoff_mode(caps["platform"])
        handoff = {"mode": mode}
        if mode == "copy":
            handoff["text"] = handoff_text(selected, by_id)
        return jsonify({"prepare_token": token,
                        "expires_at": datetime.fromtimestamp(expires, timezone.utc).isoformat(),
                        "summary_hash": digest, "receipt": receipt,
                        "counts": {"offers": len(selected), "packages": len(packages), "max_accepted": len(packages)},
                        "races": race_rows, "capabilities": caps, "handoff": handoff})

    @app.route("/api/overhauls/<overhaul_id>/send", methods=["POST"])
    @guarded
    def overhaul_send_route(overhaul_id):
        flag()
        sess, denial = session(write=True)
        if denial is not None:
            return denial
        row = load(sess, overhaul_id)
        data = body()
        key = data.get("idempotency_key")
        if not isinstance(key, str) or not key:
            raise service.ValidationError("bad_request", "idempotency_key required")
        existing = store.batch_by_key(row["overhaul_id"], key)
        if existing:
            digest = service.summary_hash([a["offer_id"] for a in existing],
                                          roadmap_version=existing[0]["roadmap_version"], revision=row["revision"])
            if digest != data.get("summary_hash"):
                raise _Conflict("idempotency_conflict")
            return jsonify({"batch_id": existing[0]["batch_id"], "attempts": [attempt_view(a) for a in existing]})
        prep = _PREPARES.get(str(data.get("prepare_token") or ""))
        if prep is None or prep["expires"] < time.time() or prep["overhaul_id"] != row["overhaul_id"]:
            raise _Conflict("prepare_expired")
        rm = store.get_roadmap(row["overhaul_id"], prep["roadmap_id"])
        if rm is None or data.get("version") != rm["version"] or prep["version"] != rm["version"]:
            raise _Conflict("stale_version", {"version": rm["version"] if rm else None})
        if data.get("summary_hash") != prep["summary_hash"]:
            raise _Conflict("summary_mismatch")
        caps = capabilities(sess)
        core = send_core(caps["platform"])
        if core is None or service.handoff_mode(caps["platform"]) != "send":
            raise _Conflict("capability_unavailable")
        if caps["auth_state"] in ("unlinked", "expired"):
            raise _Conflict("reconnect_required", caps["auth_state"])
        if caps["auth_state"] == "unverified":
            raise _Conflict("verification_required", status=403)
        if not caps["can_propose"]:
            raise _Conflict("capability_unavailable", "send_disabled")
        selected = list(prep["offer_ids"])
        by_id = {o["offer_id"]: o for o in store.list_offers(row["overhaul_id"])}
        receipt = receipt_for(sess, row, rm, selected, by_id, with_legality=False, caps=caps)
        if receipt["blockers"]:
            raise _Conflict(receipt["blockers"][0]["code"], receipt=receipt)
        package_of = {oid: p["package_id"] for p in rm["packages"] for t in p["tiers"] for oid in t["offer_ids"]}
        tier_of = {oid: t["tier"] for p in rm["packages"] for t in p["tiers"] for oid in t["offer_ids"]}
        batch_id = service.new_id("bt_")
        claims = {a: package_of[oid] for oid in selected for a in by_id[oid]["give_ids"]}
        try:
            store.claim_reservations(league_id=row["league_id"], seller_user_id=row["league_user_id"],
                                     claims=list(claims.items()), overhaul_id=row["overhaul_id"], batch_id=batch_id)
        except store.ReservationConflict as exc:
            raise _Conflict("asset_reserved", assets=exc.asset_ids)
        digest = service.request_hash(selected, roadmap_version=rm["version"])
        rows = [{"attempt_id": service.new_id("at_"), "batch_id": batch_id, "overhaul_id": row["overhaul_id"],
                 "roadmap_id": rm["roadmap_id"], "roadmap_version": rm["version"], "package_id": package_of[oid],
                 "tier": tier_of[oid], "offer_id": oid, "idempotency_key": key, "request_hash": digest,
                 "proposal_event_id": uuid.uuid4().hex} for oid in selected]
        store.insert_attempts(rows)   # persisted BEFORE any provider call
        _PREPARES.pop(str(data.get("prepare_token")), None)
        counts = {"sent": 0, "failed": 0, "unknown": 0}
        for a in rows:
            offer = by_id[a["offer_id"]]
            if not store.transition_attempt(a["attempt_id"], "queued", "sending", source="server"):
                continue
            try:
                # Same keyword contract on every core (Sleeper / MFL / ESPN).
                payload, status = core(
                    sess, league_id=row["league_id"], their_user_id=offer["counterparty_user_id"],
                    give_ids=list(offer["give_ids"]), receive_ids=list(offer["receive_ids"]),
                    proposal_event_id=a["proposal_event_id"], source="overhaul")
            except Exception as exc:
                log.warning("overhaul send transport error: %s", exc)
                store.transition_attempt(a["attempt_id"], "sending", "outcome_unknown", source="server",
                                         error={"code": "transport_error", "message": str(exc)[:200]})
                counts["unknown"] += 1
                continue
            payload = payload or {}
            if status == 200:
                # MFL confirms with a status word and no transaction id; ESPN
                # returns both. Store whatever the provider actually said.
                store.transition_attempt(a["attempt_id"], "sending", "proposed", source="provider",
                                         provider_transaction_id=payload.get("transaction_id"),
                                         provider_status=payload.get("mfl_status") or payload.get("espn_status"),
                                         observed=True)
                counts["sent"] += 1
            else:
                store.transition_attempt(a["attempt_id"], "sending", "send_failed", source="provider",
                                         error={"code": payload.get("error") or "send_failed",
                                                "message": payload.get("detail") or payload.get("message")})
                counts["failed"] += 1
                release_if_idle(row["overhaul_id"], a["package_id"])
        store.update_overhaul(row["overhaul_id"], status="executing")
        fire(sess, "overhaul_batch_reconciled",
             {"overhaul_id": row["overhaul_id"], "batch_id": batch_id, "sent_count": counts["sent"],
              "failed_count": counts["failed"], "unknown_count": counts["unknown"]})
        attempts = [a for a in store.list_attempts(row["overhaul_id"]) if a["batch_id"] == batch_id]
        return jsonify({"batch_id": batch_id, "attempts": [attempt_view(a) for a in attempts]})

    def release_if_idle(overhaul_id, package_id):
        if not any(a["package_id"] == package_id for a in live_attempts(overhaul_id)):
            store.release_reservations(overhaul_id=overhaul_id, package_id=package_id)

    def attempt_age_s(attempt, now_utc):
        try:
            stamp = datetime.fromisoformat(str(attempt.get("updated_at") or ""))
        except ValueError:
            return 0.0
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return max(0.0, (now_utc - stamp).total_seconds())

    @app.route("/api/overhauls/<overhaul_id>/refresh", methods=["POST"])
    @guarded
    def overhaul_refresh_route(overhaul_id):
        sess, denial = session(write=True)
        if denial is not None:
            return denial
        row = load(sess, overhaul_id)
        last = _REFRESH_AT.get(row["overhaul_id"])
        now = time.monotonic()
        if last is not None and now - last < _REFRESH_MIN_INTERVAL_S:
            raise _Conflict("rate_limited", status=429)
        _REFRESH_AT[row["overhaul_id"]] = now
        snapshot, rows = capture_snapshot(sess)
        store.update_overhaul(row["overhaul_id"], snapshot=snapshot,
                              recovery=compute_recovery(sess, row["settings"], snapshot, rows))
        offers = store.list_offers(row["overhaul_id"])
        by_id = {o["offer_id"]: o for o in offers}
        mine = owned_ids(snapshot)
        # Zombie sweep: `queued`/`sending` rows a crashed batch left behind.
        now_utc = datetime.now(timezone.utc)
        for a in store.list_attempts(row["overhaul_id"]):
            outcome = service.stuck_outcome(a["state"], attempt_age_s(a, now_utc))
            if outcome and store.transition_attempt(a["attempt_id"], a["state"], outcome, source="server",
                                                    error={"code": "worker_lost", "message": "no worker finished this attempt"}):
                if outcome == "stale":
                    release_if_idle(row["overhaul_id"], a["package_id"])
        # Picks: the DB table lags the platform. Only a live traded_picks read
        # (snapshot.pick_ownership_source == 'live') may confirm a pick arrived.
        pick_fn = is_pick(row["league_id"])
        mine_set = set(mine)
        holder = (lambda a: a in mine_set) if snapshot.get("pick_ownership_source") == "live" else None
        # Players: only a live platform read (snapshot.roster_source == 'live')
        # is evidence. A session fallback (MFL/ESPN read failed, or no reader)
        # never terminalizes an attempt.
        fresh = snapshot.get("roster_source") == "live"
        outcomes = []
        for a in store.list_attempts(row["overhaul_id"]):
            if a["state"] not in ("proposed", "outcome_unknown"):
                continue
            offer = by_id.get(a["offer_id"])
            outcome = (service.reconcile_attempt(offer, my_assets=mine, is_pick=pick_fn, live_pick_holder=holder,
                                                 roster_fresh=fresh)
                       if offer else None)
            if outcome is not None:
                outcomes.append((a, outcome))
        # Accepted first: it invalidates its package's tie partners, whose own
        # ownership reading would otherwise race it (invariant 6).
        for a, outcome in sorted(outcomes, key=lambda pair: pair[1] != "accepted"):
            moved = store.transition_attempt(a["attempt_id"], a["state"], outcome, source="ownership_refresh", observed=True)
            if not moved:
                continue
            if outcome == "accepted":
                for other in live_attempts(row["overhaul_id"]):
                    if other["package_id"] == a["package_id"] and other["attempt_id"] != a["attempt_id"]:
                        store.transition_attempt(other["attempt_id"], other["state"], "invalidated",
                                                 source="ownership_refresh", observed=True)
                store.release_reservations(overhaul_id=row["overhaul_id"], package_id=a["package_id"])
            else:
                release_if_idle(row["overhaul_id"], a["package_id"])   # terminal: free the package if nothing is live
        stale = [o["offer_id"] for o in offers if o["availability"] == "fresh" and not set(o["give_ids"]) <= set(mine)]
        store.mark_stale(row["overhaul_id"], stale)
        selected = store.get_roadmap(row["overhaul_id"], row["selected_roadmap_id"]) if row.get("selected_roadmap_id") else None
        if selected:
            attempts = store.list_attempts(row["overhaul_id"])
            by_id = {o["offer_id"]: o for o in store.list_offers(row["overhaul_id"])}
            if all(service.package_status(p, by_id, attempts) == "complete" for p in selected["packages"]):
                store.update_overhaul(row["overhaul_id"], status="complete")
        return jsonify(overhaul_view(sess, store.get_overhaul(row["overhaul_id"])))

    @app.route("/api/overhauls/<overhaul_id>/attempts/<attempt_id>/status", methods=["POST"])
    @guarded
    def overhaul_attempt_status_route(overhaul_id, attempt_id):
        sess, denial = session(write=True)
        if denial is not None:
            return denial
        row = load(sess, overhaul_id)
        data = body()
        state = data.get("state")
        if state not in service.USER_REPORTABLE_STATES:
            raise service.ValidationError("bad_request", "state must be declined|withdrawn|expired")
        attempt = store.get_attempt(row["overhaul_id"], attempt_id)
        if attempt is None:
            raise _Conflict("not_found", status=404)
        if attempt["state"] not in ("proposed", "outcome_unknown"):
            raise _Conflict("bad_request", {"state": attempt["state"]}, status=400)
        note = data.get("note")
        error = {"code": "user_reported", "message": str(note)[:200]} if note else None
        if not store.transition_attempt(attempt["attempt_id"], attempt["state"], state, source="user_reported",
                                        error=error, observed=True):
            raise _Conflict("bad_request", "attempt moved", status=400)
        release_if_idle(row["overhaul_id"], attempt["package_id"])
        return jsonify(attempt_view(store.get_attempt(row["overhaul_id"], attempt_id)))
