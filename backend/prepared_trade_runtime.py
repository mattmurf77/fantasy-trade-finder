"""Silent preparation orchestration; the HTTP worker supplies its existing seams.

No server import: importing this module cannot boot Flask, create sessions or
start work. Operational state is aggregate-only; private records stay in SQL.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import copy
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import uuid

from sqlalchemy import select, or_

from . import database as db, user_data_lifecycle as lifecycle
from . import prepared_trade_store as store
from . import prepared_trade_read_guard as read_guard
from .prepared_trade_cohort import discover_targets, read_league_source
from .prepared_trade_payload import PreparedEvidenceCapture, restore_inventory, restore_runtime_card

VERSION = "prepared-inventory-2"
_lock = threading.Lock()
_active = False
_state = {"status": "idle"}
_last_tick = 0.0
_last_prune = 0.0
_ARTIFACT_PHASES = frozenset({"receipt_before", "cache_lookup", "receipt_after", "inventory_save",
                            "inventory_begin", "inventory_capture", "inventory_seal"})
_CAPTURE_FAILURE_REASONS = {
    "prepared_payload_v2:record_bytes": "inventory_record_limit",
    "prepared_payload_v2:record_complexity": "inventory_record_complexity",
    "prepared_payload_v2:json_bytes": "inventory_record_limit",
    "prepared_payload_v2:json_complexity": "inventory_record_complexity",
    "prepared_payload_v2:snapshot_amplification": "inventory_diagnostic_amplification",
    "prepared_payload_v2:snapshot_cycle_or_depth": "inventory_diagnostic_depth",
    "prepared_payload_v2:snapshot_depth": "inventory_diagnostic_depth",
    "prepared_payload_v2:snapshot_checksum": "inventory_diagnostic_checksum",
    "prepared_payload_v2:closure_bytes": "inventory_diagnostic_closure_limit",
    "prepared_payload_v2:snapshot_closure_bytes": "inventory_diagnostic_closure_limit",
    "prepared_payload_v2:batch_record_bytes": "inventory_batch_record_limit",
    "prepared_payload_v2:admission_binding": "inventory_admission_invalid",
    "prepared_payload_v2:admission_count": "inventory_admission_invalid",
    "prepared_payload_v2:incomplete_evidence": "inventory_completion_invalid",
    "prepared_payload_v2:expired_card": "inventory_card_expired",
}


@contextmanager
def _artifact_phase(phase):
    """Attach only a fixed operational stage; never disclose exception text."""
    if type(phase) is not str or phase not in _ARTIFACT_PHASES:
        raise ValueError("unknown_preparation_phase")
    try:
        yield
    except ValueError as exc:
        exc.prepared_phase = phase
        raise


def _artifact_failure_details(exc):
    from .prepared_trade_payload_v2 import PreparedPayloadError
    details = store.safe_failure_details(exc)
    if type(exc) in (ValueError, PreparedPayloadError) and len(exc.args) == 1 and type(exc.args[0]) is str:
        details["reason"] = _CAPTURE_FAILURE_REASONS.get(exc.args[0], "preparation_failed")
    phase = getattr(exc, "prepared_phase", None)
    details["phase"] = phase if type(phase) is str and phase in _ARTIFACT_PHASES else "unknown"
    return details


def utcnow():
    return datetime.now(timezone.utc)


def enabled(server):
    return bool(server.is_enabled("trade.prepared_inventory") and
                server._trade_service_mod._cfg.get("prepared_trade_inventory_enabled", 0) == 1)


def supported(server, league_id):
    """The first persistence contract is audited for exclusive Bilateral2.

    A later arm/model release must explicitly qualify its input contract.
    Never persist a silently degraded mix of unreviewed model branches.
    """
    cfg = server._trade_service_mod._cfg
    return (enabled(server) and league_id != "league_demo" and
            server._owner_enabled(league_id) and server._bakeoff.owner_only() and
            server._bakeoff.serve_owner() and server._bakeoff.owner_revision_enabled(cfg))


def model_identity(server):
    # Render supplies the immutable deployment commit. Local evidence also
    # binds implementation bytes, so an uncommitted change cannot restore an
    # inventory made by another checkout with the same HEAD.
    paths = ("server.py", "trade_gen_owner.py", "trade_gen_bilateral.py",
             "trade_gen_bilateral_candidate.py", "trade_bilateral_presentment.py",
             "trade_service.py", "trade_significance.py", "trade_input_evidence.py",
             "ranking_service.py", "trade_breaker.py", "trade_policy.py", "pick_values.py",
             "prepared_trade_payload.py", "prepared_trade_runtime.py", "prepared_trade_store.py",
             "prepared_trade_payload_v2.py", "prepared_trade_store_v2.py", "prepared_trade_runtime_v2.py",
             "prepared_trade_read_guard.py", "deck_diagnostics.py", "trade_roster.py")
    digest = hashlib.sha256()
    for name in paths:
        path = Path(__file__).with_name(name)
        if path.is_file():
            digest.update(name.encode())
            digest.update(path.read_bytes())
    return {"schema": VERSION, "deployment": os.getenv("RENDER_GIT_COMMIT", "local"),
            "implementation": digest.hexdigest(),
            "model": server._bakeoff.owner_version(server._trade_service_mod._cfg)}


def scope_for(user_id, league_id, league_user_id, scoring_format, fairness):
    return store.InventoryScope(str(user_id), str(league_id), str(league_user_id),
        scoring_format, store.dependency_hash({"fairness": float(fairness),
            "give": [], "receive": [], "partner": None, "intent": None}))


def _rows(conn, table, condition=None, columns=None):
    query = select(*(columns or list(table.c)))
    if condition is not None:
        query = query.where(condition)
    if len(table.primary_key.columns):
        query = query.order_by(*table.primary_key.columns)
    return [{str(k): v for k, v in r.items()} for r in conn.execute(query).mappings()]


def cohort_rows(league_id=None):
    with db.engine.connect() as conn:
        leagues = _rows(conn, db.leagues_table,
            db.leagues_table.c.sleeper_league_id == league_id if league_id else None)
        lids = [r["sleeper_league_id"] for r in leagues]
        return {"users": _rows(conn, db.users_table), "accounts": _rows(conn, db.accounts_table),
                "leagues": leagues, "members": _rows(conn, db.league_members_table,
                    db.league_members_table.c.league_id.in_(lids))}


def read_source(server, league):
    from .sleeper_write import decrypt_token

    def credential_reader(platform, user_id):
        reader = {"espn": db.get_espn_credential, "mfl": db.get_mfl_credential}.get(platform)
        return reader(user_id) if reader else None

    return read_league_source(league, sleeper_get=server._sleeper_get,
        credential_reader=credential_reader, decrypt_token=decrypt_token,
        crosswalk=server._shared_crosswalk() if (league.get("platform") or "sleeper") != "sleeper" else None,
        now=utcnow)


def discover(server, league_id=None):
    return discover_targets(**cohort_rows(league_id),
        read_source=lambda league: read_source(server, league),
        season=utcnow().year, now=utcnow)


def refresh_target(server, scope):
    result = discover(server, scope.league_id)
    for target in result["targets"]:
        if (str(target["user_id"]) == scope.user_id and
                str(target["league_user_id"]) == scope.league_user_id and
                target["scoring_format"] == scope.scoring_format):
            return target
    raise ValueError("source_or_binding_unavailable")


def build_session(server, target):
    """Read-only ranking replay, deliberately not extension/session auth."""
    uid, fmt = target["user_id"], target["scoring_format"]
    pool, seed = server._get_universal_pool(fmt)
    if not pool or not seed:
        raise ValueError("player_pool_unavailable")
    ranking = server.RankingService(players=pool, matchup_generator=server.matchup_gen,
                                    seed_ratings=seed)
    ranking._user_id, ranking._scoring_format = uid, fmt
    historical = server.load_swipe_decisions(user_id=uid, scoring_format=fmt)
    if historical:
        ranking.replay_from_db(historical)
    ranking._elo_overrides = {pid: float(v) for pid, v in
        server.load_tier_overrides(user_id=uid, scoring_format=fmt).items()}
    ranking._elo_override_at = server.load_tier_override_stamps(user_id=uid, scoring_format=fmt)
    players = {p.id: p for p in pool}
    roster = [str(p) for p in target["user_roster"] if str(p) in players]
    members = [server.LeagueMember(user_id=m["user_id"], username=m["name"],
        roster=[str(p) for p in m["player_ids"] if str(p) in players],
        elo_ratings={str(p): seed.get(str(p), 1500) for p in m["player_ids"] if str(p) in players})
        for m in target["opponents"]]
    if not roster or not members:
        raise ValueError("empty_roster_or_opponents")
    league = server.League(league_id=target["league_id"],
        name=target["source"]["metadata"].get("name") or "League",
        platform=target["platform"], members=members)
    decisions, passes = server._load_trade_disposition_keys(uid, target["league_id"])
    trades = server.TradeService(players=players, past_decision_keys=decisions, dismissed_keys=passes)
    trades.add_league(league)
    server._FA_LEAGUE_META_CACHE[league.league_id] = (time.time(), copy.deepcopy(target["source"]["metadata"]))
    return {"user_id": uid, "league_user_id": target["league_user_id"],
        "league": league, "players": list(pool), "user_roster": roster,
        "services": {fmt: ranking}, "service": ranking,
        "trade_svcs": {fmt: trades}, "trade_svc": trades, "active_format": fmt}


def _semantic_source(source):
    result = copy.deepcopy(source)
    result.pop("observed_at", None)
    result.pop("fingerprint", None)
    return result


def active_dependency_receipt(server, scope, session, target, *, exclude_job_id=None,
                              own_mutations=(), served_at=None):
    """Explicit/source inputs that must remain fixed during one adoption.

    Admission still uses the full receipt. Ordinary trade feedback can change
    computed Elo and history without repricing an already accepted inventory;
    the runtime must separately project current exact dispositions/source likes
    and awaiting/matched packages. Persisted explicit inputs remain guarded for
    every consumed manager, even when another process performed the write.
    """
    return dependency_receipt(server, scope, session, target,
        exclude_job_id=exclude_job_id, own_mutations=own_mutations,
        served_at=served_at, _active_inputs=True)


def dependency_receipt(server, scope, session, target, *, exclude_job_id=None,
                       own_mutations=(), served_at=None, _active_inputs=False):
    """Conservative exact scope receipt, independent of process epoch tokens.

    Keep non-input login/device/activity columns out: preparing or opening the
    app must not invalidate the board. Rows influencing eligibility/history
    are included, not just maxima (edits/deletes can preserve a row count).
    """
    uid, lid = scope.user_id, scope.league_id
    participants = sorted({uid, scope.league_user_id,
        *(str(m["user_id"]) for m in target["opponents"])})
    records = {}
    scoped = ("member_rankings", "league_preferences", "asset_preferences", "draft_picks",
              "recorded_picks", "trade_decisions", "trade_matches", "trade_proposals",
              "standing_offers", "deck_suppressions", "deck_fatigue_resets", "trade_block")
    if _active_inputs:
        scoped = tuple(name for name in scoped if name not in {"trade_decisions", "trade_matches"})
    with db.engine.connect() as conn:
        for name in scoped:
            table = getattr(db, name + "_table")
            records[name] = _rows(conn, table, table.c.league_id == lid)
            # These receipts bind content, not a provider poll time or the
            # surrogate row IDs allocated by replace-sync. Exact source/proof
            # observation timestamps remain in the captured evidence bundle.
            if name in {"draft_picks", "member_rankings", "trade_block"}:
                for row in records[name]:
                    for key in ("id", "synced_at", "updated_at"):
                        row.pop(key, None)
                records[name].sort(key=lambda row: json.dumps(row, sort_keys=True))
        swipes = db.swipe_decisions_table
        swipe_condition = swipes.c.user_id.in_(participants)
        if _active_inputs:
            # NULL/unknown types are NOT assumed to be harmless feedback.
            swipe_condition = swipe_condition & (swipes.c.decision_type.is_(None)
                | swipes.c.decision_type.notin_(("trade", "disposition")))
        records["swipes"] = _rows(conn, swipes, swipe_condition)
        user_cols = [db.users_table.c[k] for k in ("sleeper_user_id", "created_at",
            "ranking_method", "tiers_saved", "tier_overrides", "anchor_scale", "stud_tax_mode")]
        records["users"] = _rows(conn, db.users_table,
            db.users_table.c.sleeper_user_id.in_(participants), user_cols)
        records["leagues"] = _rows(conn, db.leagues_table, db.leagues_table.c.sleeper_league_id == lid)
        for row in records["leagues"]:
            for key in ("updated_at", "created_at", "draft_status_checked_at"):
                row.pop(key, None)
        # Bilateral's full constructor bypasses Thompson/taste reranking, but
        # history and fatigue still change eligibility and first-deck labels.
        if not _active_inputs:
            impressions = db.deck_impressions_table
            condition = (impressions.c.league_id == lid) & (impressions.c.user_id == uid)
            if exclude_job_id:
                condition = condition & (impressions.c.deck_job_id != exclude_job_id)
            impression_cols = [impressions.c[k] for k in ("impression_id", "user_id", "league_id",
                "deck_job_id", "trade_hash", "served_at", "card_index")]
            records["impressions"] = _rows(conn, impressions, condition, impression_cols)
            impression_ids = [r["impression_id"] for r in records["impressions"]]
            records["outcomes"] = _rows(conn, db.deck_outcomes_table,
                db.deck_outcomes_table.c.impression_id.in_(impression_ids))
            records["legacy_impressions"] = _rows(conn, db.trade_impressions_table,
                (db.trade_impressions_table.c.league_id == lid) & (db.trade_impressions_table.c.user_id == uid))
    if served_at:
        normalize_own_mutations(records["deck_suppressions"], own_mutations, served_at)
    ranking = session["services"][scope.scoring_format]
    players = session["players"]
    pool = server.g_universal_by_format.get(scope.scoring_format) or {}
    evidence = pool.get("input_evidence")
    evidence_rows = (evidence.capture({p.id: p for p in players}).as_dict({p.id: p for p in players})
                     if evidence is not None else None)
    raw_players = server._load_sleeper_cache() or {}
    availability_age = server._players_cache_age_seconds()
    from .data_loader import load_pick_slot_values
    receipt = {"version": VERSION + "-active-inputs-1" if _active_inputs else VERSION, "scope": scope.as_dict(),
        "source": _semantic_source(target["source"]),
        "binding": target["binding_evidence"], "records": records,
        **({"ratings": {r.player.id: r.elo for r in ranking.get_rankings(position=None).rankings}}
           if not _active_inputs else {}),
        "comparisons": ranking.comparison_counts(), "placements": ranking.placement_bands(),
        "overrides": dict(ranking._elo_overrides),
        "override_stamps": dict(getattr(ranking, "_elo_override_at", {})),
        "seed": ranking._seed, "players": [server.player_to_dict(p) for p in players],
        "current_global_pool": {"seed": (server.g_universal_by_format.get(scope.scoring_format) or {}).get("seed"),
            "players": [server.player_to_dict(p) for p in
                (server.g_universal_by_format.get(scope.scoring_format) or {}).get("players", [])]},
        "input_evidence": evidence_rows, "pick_curve": load_pick_slot_values(scope.scoring_format),
        "lineup_metadata": ((server._FA_LEAGUE_META_CACHE.get(lid) or (None, {}))[1]).get("roster_positions") or [],
        "availability": {"fresh": availability_age is not None and availability_age <= 48 * 3600,
            "players": {p.id: {k: (raw_players.get(p.id) or {}).get(k)
                for k in ("fantasy_positions", "injury_status")} for p in players}},
        "ranking_config": dict(server._ranking_service_mod._cfg),
        "rank_confidence": server._ranking_confidence(ranking),
        **({"dispositions": server._load_trade_disposition_keys(uid, lid),
            "presentment_exclusions": server._load_presentment_exclusions(uid, lid)}
           if not _active_inputs else {}),
        "live_standing_offers": server.load_standing_offers(league_id=lid),
        "suppression_active": {str(r["id"]): _unexpired(r.get("expires_at"))
            for r in records["deck_suppressions"]},
        "pick_read_source": server._pick_read_source(),
        "slot_order": server._league_slot_order(lid),
        "preferences": server._trade_job_preferences(uid, lid, session, session["league"]),
        "config": dict(server._trade_service_mod._cfg), "flags": server.flags_dict()}
    # Hash each private component, not private values, in the lookup receipt.
    return {k: store.dependency_hash(server._owner_canonical(v)) for k, v in receipt.items()}


def _unexpired(value):
    if not isinstance(value, str) or not value:
        return False
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc) > utcnow()


def normalize_own_mutations(rows, mutations, served_at):
    """Only the exact committed effect of THIS publication may be normalized.

    A pass/undo/different retest remains a dependency mismatch. This permits a
    crash-resumed adoption to validate its original inputs after its own first
    batch legitimately consumes a retest opportunity.
    """
    by_id = {r["id"]: r for r in rows}
    for mutation in mutations:
        row = by_id.get(mutation["id"])
        if row is None:
            continue
        before = mutation["before"]
        after = {**before, **({"retested_at": served_at, "retest_trade_hash": mutation["trade_hash"]}
            if mutation["kind"] == "retest" else {"declined_at": mutation["passed_at"],
                "expires_at": mutation["expires_at"], "retested_at": None, "retest_trade_hash": None})}
        if all(row.get(k) == v for k, v in after.items()):
            row.update(before)


def _interactive_busy(server):
    with server._trade_jobs_lock:
        return any(server._job_live(j) and j.get("source") != "prepared_inventory"
                   for j in server._trade_jobs.values())


def _fairness(server, user_id, league_id):
    with server._sessions_lock:
        values = [(s.get("last_active", 0), s.get("trade_fairness_threshold", .5))
            for s in server._sessions.values() if s.get("user_id") == user_id and
            getattr(s.get("league"), "league_id", None) == league_id]
    value = max(values, default=(0, .5))[1]
    return float(value)


def prepare_target(server, claim):
    from . import prepared_trade_store_v2 as paged_store
    from .prepared_trade_payload_v2 import PagedPreparedEvidenceCapture
    scope = store.InventoryScope(**claim["scope"])
    if not supported(server, scope.league_id):
        raise ValueError("unsupported_policy_or_disabled")
    target = refresh_target(server, scope)
    fairness = claim["binding"].get("fairness", .5)
    participants = sorted({scope.user_id, scope.league_user_id,
                           *(m["user_id"] for m in target["opponents"])})
    with ExitStack() as stack:
        for uid in participants:
            if not stack.enter_context(lifecycle.capture(uid, started=claim["work_started"]).active()):
                raise ValueError("account_deleted")
        sync_source_picks(server, target)
        session = build_session(server, target)
        with _artifact_phase("receipt_before"):
            before = dependency_receipt(server, scope, session, target)
        identity = model_identity(server)
        with _artifact_phase("cache_lookup"):
            cached = paged_store.peek_inventory(scope, now=utcnow())
        if (cached is not None and store.dependency_hash(cached.header["dependency_receipt"]) == store.dependency_hash(before)
                and store.dependency_hash(cached.header["model_identity"]) == store.dependency_hash(identity)):
            store.complete_target(claim, status="reused", now=utcnow())
            return
        if _interactive_busy(server):
            store.complete_target(claim, status="deferred", reason="interactive_work",
                                  retry_at=utcnow() + timedelta(seconds=30), now=utcnow())
            return
        job_id = uuid.uuid4().hex
        prefs = server._trade_job_preferences(scope.user_id, scope.league_id, session, session["league"])
        context = server._capture_trade_execution(session, scope.user_id, scope.league_id, scope.scoring_format)
        if target["platform"] == "sleeper":
            context = replace(context, prepared_roster_snapshot=tuple(_source_rosters(target["source"])))
        # This session is unregistered and private. Explicit isolation remains
        # mandatory if callers later supply an existing interactive service.
        context.trade_service._trade_cards = {}
        context.trade_service._significance_exemptions = {}
        epochs = server._capture_trade_input_epochs(scope.user_id, scope.league_id, participant_ids=participants)
        job = {"job_id": job_id, "key": (scope.user_id, scope.league_id, scope.scoring_format),
            "status": "running", "started_at": time.monotonic(), "finished_at": None,
            "cards": [], "error": None, "source": "prepared_inventory", "is_pinned": False,
            "input_epochs": epochs, "owner_model": server._bakeoff.owner_arm(),
            "owner_model_version": server._bakeoff.owner_version(),
            "opponents_done": 0, "opponents_total": len(target["opponents"]),
            "final_checks_pending": True, "fairness_threshold": fairness}
        with server._trade_jobs_lock:
            server._trade_jobs[job_id] = job  # Never register a shared/user cache pointer.
        stage, sealed = None, False
        try:
            now = utcnow()
            with _artifact_phase("inventory_begin"):
                stage = paged_store.begin_inventory(claim, dependency_receipt=before,
                    model_identity=identity, participants=participants, created_at=now,
                    expires_at=now + timedelta(hours=24), now=now)
            sink = PagedPreparedEvidenceCapture(stage=stage, user_id=scope.user_id,
                                                league_id=scope.league_id, job_id=job_id)
            with _artifact_phase("inventory_capture"):
                server._run_trade_job(job_id, "", scope.league_id, fairness, [],
                    prefs_preload=prefs, execution_context=context, prepare_sink=sink)
                if job["status"] != "complete" or "prepared_bundle" not in job:
                    if isinstance(job.get("prepared_failure"), Exception):
                        raise job["prepared_failure"]
                    raise ValueError(job.get("error") or "preparation_incomplete")
            fresh = refresh_target(server, scope)
            after_session = build_session(server, fresh)
            with _artifact_phase("receipt_after"):
                after = dependency_receipt(server, scope, after_session, fresh)
            if store.dependency_hash(after) != store.dependency_hash(before):
                raise ValueError("inputs_changed")
            if (not supported(server, scope.league_id)
                    or store.dependency_hash(identity) != store.dependency_hash(model_identity(server))):
                raise ValueError("model_changed")
            completion = job["prepared_bundle"]
            metadata = {**completion, "generation_job_id": job_id,
                "mutations": job["prepared_mutations"], "target": target,
                "job_fields": {k: job[k] for k in ("first_deck", "board_refresh", "suppression_note",
                    "outlook_value", "safety_policy", "owner_model", "owner_model_version") if k in job}}
            with _artifact_phase("inventory_save"):
                paged_store.finish_metadata(stage, metadata=metadata, now=utcnow())
            with _artifact_phase("inventory_seal"):
                paged_store.seal_inventory(stage, completion=completion,
                    dependency_receipt=before, model_identity=identity)
            sealed = True
        finally:
            if stage is not None and not sealed:
                try:
                    paged_store.abort_inventory(stage, now=utcnow())
                except Exception:
                    server.log.warning("prepared staging cleanup deferred to retention")
            with server._trade_jobs_lock:
                server._trade_jobs.pop(job_id, None)


def sync_source_picks(server, target):
    """Quiet source sync from the *validated* snapshot, never a fail-soft read.

    ESPN/Fleaflicker have no provider pick ledger: their existing user-asserted
    ledger remains authoritative, with that limitation preserved in evidence.
    """
    source = target["source"]
    if target["platform"] == "sleeper":
        if not server.is_enabled("picks.owned_sync"):
            raise ValueError("source_pick_sync_disabled")
        rosters = _source_rosters(source)
        result = server._sync_sleeper_owned_picks(target["league_id"],
            {t["owner_id"]: t["name"] for t in source["teams"] if t["owner_id"]},
            target["scoring_format"], rosters=rosters,
            meta={**source["metadata"], "season": source["season"]},
            traded_picks=source["traded_picks"], drafts=source["drafts"])
        if result is None:
            raise ValueError("source_pick_sync_unavailable")
    elif target["platform"] == "mfl":
        league = db.get_platform_league(target["league_id"], "mfl")
        if not league or str(league.get("user_id")) != target["user_id"] or str(
                league.get("platform_my_team")) != target["native_team_key"]:
            raise ValueError("source_binding_changed")
        server._sync_mfl_owned_picks(target["league_id"], source_picks=source["future_picks"],
            expected_binding={k: league.get(k) for k in ("user_id", "platform_my_team", "platform_season")})


def _source_rosters(source):
    return [{"roster_id": int(t["team_id"]), "owner_id": t["owner_id"],
             "co_owners": t["co_owners"], "players": t["player_ids"],
             "reserve": t.get("reserve", []), "taxi": t.get("taxi", [])} for t in source["teams"]]


def _session_for_context(context):
    return {"user_id": context.user_id, "league_user_id": context.league_user_id,
            "league": context.league, "user_roster": list(context.user_roster),
            "players": list(context.players), "service": context.service,
            "services": {context.scoring_format: context.service}}


def _guard_expiry(cached):
    values = [cached["expires_at"], *(row["runtime"]["expires_at"]
        for row in cached["payload"]["inventory"]["cards"])]
    dates = [datetime.fromisoformat(value.replace("Z", "+00:00")) for value in values]
    if any(value.tzinfo is None for value in dates):
        raise ValueError("invalid_original_expiry")
    return min(dates)


def try_adopt(server, *, job_id, context, fairness, prefs):
    """Worker-side cache admission. False means run ordinary generation.

    The HTTP request is already holding a normal job ID; upstream freshness
    checks do not park the request thread. There is no second public cache API.
    """
    if not supported(server, context.league_id):
        return False
    from .prepared_trade_runtime_v2 import try_adopt as try_adopt_paged
    paged_result = try_adopt_paged(server, job_id=job_id, context=context,
                                  fairness=fairness, prefs=prefs)
    if paged_result is not None:
        return paged_result
    scope = scope_for(context.user_id, context.league_id, context.league_user_id,
                      context.scoring_format, fairness)
    claim = None
    published = 0
    inventory = None
    try:
        cached = store.peek_inventory(scope, now=utcnow())
        if cached is None:
            return False
        identity = model_identity(server)
        if identity != cached["model_identity"]:
            return False
        target = refresh_target(server, scope)
        # The accepted interactive context must describe this actual team,
        # not merely a previously valid provider binding.
        if (set(context.user_roster) != set(p for p in target["user_roster"]
                if p in context.trade_service._players) or
                {m.user_id: set(m.roster) for m in context.league.members
                 if m.user_id not in {scope.user_id, scope.league_user_id}} !=
                {m["user_id"]: {p for p in m["player_ids"] if p in context.trade_service._players}
                 for m in target["opponents"]}):
            return False
        session = _session_for_context(context)
        guard = read_guard.capture(server, scope, expires_at=_guard_expiry(cached))
        receipt = dependency_receipt(server, scope, session, target,
            exclude_job_id=cached["payload"]["generation_job_id"],
            own_mutations=cached["payload"]["mutations"],
            served_at=(cached.get("publication") or {}).get("served_at"))
        if receipt != cached["dependency_receipt"]:
            return False
        inventory = restore_inventory(cached["payload"]["inventory"],
            user_id=scope.user_id, league_id=scope.league_id, now=utcnow())
        survivors = server._project_trade_dispositions(inventory.cards, scope.user_id, scope.league_id)
        if len(survivors) != len(inventory.cards):
            return False  # Time-window or unresolved source-link change: regenerate.
        claim = store.claim_adoption(cached["inventory_id"], dependency_receipt=receipt,
            model_identity=identity, publication={"served_at": utcnow().isoformat(),
                "first_deck": bool(cached["payload"]["job_fields"].get("first_deck")),
                "board_state": list(server.load_board_state(scope.user_id, scope.league_id, scope.scoring_format))},
            now=utcnow())
        if claim is None:
            return False
        publication = claim["publication"]
        def still_current():
            with server._trade_jobs_lock:
                live = server._job_live(server._trade_jobs.get(job_id))
            return (live and supported(server, scope.league_id) and
                read_guard.valid(server, guard, scope=scope) and
                model_identity(server) == identity and utcnow().isoformat() < cached["expires_at"] and
                dependency_receipt(server, scope, session, target,
                    exclude_job_id=cached["payload"]["generation_job_id"],
                    own_mutations=cached["payload"]["mutations"], served_at=publication["served_at"]) == receipt)
        with ExitStack() as stack:
            for uid in cached["participants"]:
                if not stack.enter_context(lifecycle.capture(uid, started=claim["work_started"]).active()):
                    raise ValueError("account_deleted")
            with server._trade_jobs_lock:
                job = server._trade_jobs.get(job_id)
                if not server._job_live(job):
                    return True
                job.update(copy.deepcopy(cached["payload"]["job_fields"]))
                job.update(prepared_inventory_id=cached["inventory_id"],
                    prepared_expires_at=cached["expires_at"], prepared_guard=guard,
                    final_checks_pending=True)
            runtime_records = {r["runtime"]["trade_id"]: r
                               for r in cached["payload"]["inventory"]["cards"]}
            for batch in inventory.batches(**publication):
                if not still_current():
                    raise ValueError("inputs_changed")
                with server._trade_jobs_lock:
                    if not server._job_live(server._trade_jobs.get(job_id)):
                        raise ValueError("inputs_changed")
                for card, row in zip(batch["cards"], batch["impression_rows"]):
                    row["features_json"]["prepared_runtime"] = runtime_records[card.trade_id]
                    row["features_json"]["prepared_inventory_id"] = cached["inventory_id"]
                    row["features_json"]["deck_source"] = "prepared_adoption"
                store.ensure_adoption_evidence(claim, candidate_set=batch["candidate_set"],
                                               rows=batch["impression_rows"], now=utcnow())
                next_prefix = published + len(batch["cards"])
                # A recovered claim may already have this durable prefix. It
                # must hydrate the same cards, not reserve new impression IDs.
                previous = claim["published_count"]
                if next_prefix > previous:
                    store.checkpoint_adoption(claim, published_count=next_prefix,
                        expected_prefix=previous, now=utcnow(), complete=next_prefix == len(inventory.cards))
                    claim["published_count"] = next_prefix
                if not still_current():
                    raise ValueError("inputs_changed")
                with server._trade_jobs_lock:
                    job = server._trade_jobs.get(job_id)
                    if not server._job_live(job):
                        raise ValueError("inputs_changed")
                    for card in batch["cards"]:
                        card._prepared_guard = guard
                        if getattr(card, "owner_evaluation", None) is not None:
                            card.owner_published = True
                        context.trade_service._trade_cards[card.trade_id] = card
                        exemption = inventory.significance_by_trade_id.get(card.trade_id)
                        if exemption is not None:
                            server._significance_exemptions_for(context.trade_service)[
                                server._significance_card_key(card)] = exemption
                    job["cards"] = [*job["cards"], *copy.deepcopy(batch["public_cards"])]
                    job["final_checks_pending"] = False
                published = next_prefix
            if not inventory.cards:
                if not still_current():
                    raise ValueError("inputs_changed")
                store.ensure_adoption_evidence(claim, candidate_set=inventory.candidate_set,
                                               rows=[], now=utcnow())
                store.checkpoint_adoption(claim, published_count=0,
                    expected_prefix=claim["published_count"], now=utcnow(), complete=True)
                if not still_current():
                    raise ValueError("inputs_changed")
            with server._trade_jobs_lock:
                job = server._trade_jobs.get(job_id)
                if server._job_live(job):
                    job["final_checks_pending"] = False
                    job["opponents_done"] = job["opponents_total"]
            server._finish_trade_job(job_id)
            server.log.info("prepared inventory adopted: cards=%d", published)
            return True
    except Exception as exc:
        server.log.warning("prepared inventory adoption unavailable (%s)", type(exc).__name__)
        if str(exc) in {"inputs_changed", "account_deleted"} or isinstance(exc, store.StaleWork):
            with server._trade_jobs_lock:
                job = server._trade_jobs.get(job_id)
                if job is not None:
                    for public in job.get("cards", ()):
                        card = context.trade_service._trade_cards.get(public["trade_id"])
                        if card is not None and inventory is not None and any(
                                card is candidate for candidate in inventory.cards):
                            context.trade_service._trade_cards.pop(card.trade_id, None)
                    server._revoke_trade_job_locked(job, "inputs_changed")
            return True
        if published:
            server._finish_trade_job(job_id, error="prepared_adoption_incomplete")
            return True
        with server._trade_jobs_lock:
            job = server._trade_jobs.get(job_id)
            if job is not None:
                for key in ("prepared_inventory_id", "prepared_expires_at", "prepared_guard", "first_deck", "board_refresh",
                            "suppression_note"):
                    job.pop(key, None)
        return False
    finally:
        if claim is not None:
            try:
                store.release_adoption(claim)
            except Exception:
                server.log.warning("prepared adoption lease release failed; expiry will recover")


def restore_action_card(server, *, body, user_id, league_id):
    """Recover only committed owner-bound runtime evidence, never client proof."""
    iid = body.get("impression_id")
    if not isinstance(iid, str):
        return None
    row = server.load_deck_impression(iid)
    if not row or row.get("user_id") != user_id or row.get("league_id") != league_id:
        return None
    features = row.get("features_json") or {}
    if isinstance(features, str):
        try:
            features = json.loads(features)
        except (ValueError, TypeError):
            return None
    record = features.get("prepared_runtime") if isinstance(features, dict) else None
    if record is None:
        return None  # Ordinary legacy cards keep their existing fallback.
    try:
        card = restore_runtime_card(record, user_id=user_id, league_id=league_id)
        if card.trade_id != body.get("trade_id") or record["public"]["impression_id"] != iid:
            raise ValueError("prepared_trade_unavailable")
        if datetime.fromisoformat(card.expires_at.replace("Z", "+00:00")) <= utcnow():
            raise ValueError("prepared_trade_unavailable")
        if getattr(card, "owner_evaluation", None) is not None:
            card.owner_published = True
        return card
    except (KeyError, ValueError, TypeError):
        # A known prepared card cannot fall through to lower-fidelity client
        # reconstruction when its trusted evidence is expired or malformed.
        raise ValueError("prepared_trade_unavailable") from None


def status(sweep_id=None):
    if sweep_id:
        return store.sweep_status(sweep_id)
    with _lock:
        return copy.deepcopy(_state)


def start(server, *, idempotency_key, dry_run=False, user_id=None, league_id=None, resume_sweep_id=None):
    """Start one asynchronous discovery/sweep, without public identity output."""
    global _active, _state
    if not enabled(server) and not dry_run:
        raise ValueError("prepared_inventory_disabled")
    with _lock:
        if _active:
            return copy.deepcopy(_state)
        _active = True
        _state = {"status": "discovering", "request_id": idempotency_key, "dry_run": dry_run}

    def run():
        global _active, _state
        try:
            started = lifecycle.snapshot()
            sweep_id = resume_sweep_id
            if not dry_run and sweep_id is None:
                with db.engine.connect() as conn:
                    sweep_id = conn.execute(select(db.prepared_trade_sweeps_table.c.sweep_id).where(
                        db.prepared_trade_sweeps_table.c.idempotency_key == idempotency_key)).scalar_one_or_none()
            if sweep_id is None:
                cohort = discover(server, league_id)
                targets = [t for t in cohort["targets"] if user_id is None or t["user_id"] == user_id]
                specs = []
                for t in targets:
                    fairness = _fairness(server, t["user_id"], t["league_id"])
                    scope = scope_for(t["user_id"], t["league_id"], t["league_user_id"], t["scoring_format"], fairness)
                    specs.append({"scope": scope.as_dict(), "participants": sorted({t["user_id"],
                        t["league_user_id"], *(m["user_id"] for m in t["opponents"])}),
                        "binding": {"fairness": fairness}})
                if dry_run:
                    with _lock:
                        _state = {**_state, "status": "complete", "coverage": cohort["counts"],
                                  "eligible_targets": len(specs)}
                    return
                sweep_id = store.create_sweep(idempotency_key, specs, started=started, now=utcnow(),
                                             coverage=cohort["counts"])
            sweep_status = store.sweep_status(sweep_id)
            with _lock:
                _state = {**_state, "status": "running", "sweep_id": sweep_id,
                          "coverage": sweep_status.get("coverage", {}),
                          "eligible_targets": sweep_status["target_count"]}
            while enabled(server):
                state = store.sweep_status(sweep_id)
                if state["status"] != "running":
                    break
                if _interactive_busy(server):
                    time.sleep(5)
                    continue
                claim = store.claim_target(sweep_id, now=utcnow(), lease_seconds=300)
                if claim is None:
                    state = store.sweep_status(sweep_id)
                    if state["remaining_count"] and state["status"] == "running":
                        time.sleep(5)
                        continue
                    break
                try:
                    prepare_target(server, claim)
                except Exception as exc:
                    # Only known reason codes leave logs/status. Providers may
                    # put credential-bearing URLs in exception messages.
                    reason = str(exc) if str(exc) in {"inputs_changed", "account_deleted",
                        "model_changed", "source_or_binding_unavailable", "empty_roster_or_opponents",
                        "player_pool_unavailable", "unsupported_policy_or_disabled",
                        "source_pick_sync_unavailable", "source_pick_sync_disabled",
                        "source_binding_changed"} else "preparation_failed"
                    if isinstance(exc, store.InvalidArtifact) or _artifact_failure_details(exc)["reason"] != "preparation_failed":
                        details = _artifact_failure_details(exc)
                        reason = details["reason"]
                        server.log.warning("prepared inventory artifact rejected: %s",
                                           json.dumps(details, sort_keys=True))
                    server.log.warning("prepared inventory target failed: %s (%s)", reason, type(exc).__name__)
                    transient = reason in {"inputs_changed", "source_or_binding_unavailable", "source_pick_sync_unavailable"}
                    store.complete_target(claim, status="stale" if reason == "inputs_changed" else "error",
                        reason=reason, retry_at=utcnow() + timedelta(seconds=30) if transient else None, now=utcnow())
            result = store.sweep_status(sweep_id)
            with _lock:
                _state = {**_state, "status": result["status"] if enabled(server) else "stopped", "result": result}
        except Exception as exc:
            server.log.warning("prepared inventory sweep failed (%s)", type(exc).__name__)
            with _lock:
                _state = {**_state, "status": "error", "reason": "sweep_failed"}
        finally:
            with _lock:
                _active = False

    threading.Thread(target=run, name="prepared-trade-inventory", daemon=True).start()
    return status()


def tick(server):
    """Existing maintenance loop calls this: silent hourly refresh/resume."""
    global _last_tick, _last_prune
    current = time.monotonic()
    if current - _last_prune >= 3600:
        # The rollout kill switch stops creation/adoption, not privacy cleanup.
        store.prune(now=utcnow())
        _last_prune = current
    if _active:
        return
    if not enabled(server):
        return
    pending = store.resumable_sweeps(now=utcnow())
    if pending:
        start(server, idempotency_key="resume-" + pending[0], resume_sweep_id=pending[0])
        return
    if time.monotonic() - _last_tick < 3600:
        return
    _last_tick = time.monotonic()
    start(server, idempotency_key="scheduled-" + utcnow().strftime("%Y%m%d%H"))
