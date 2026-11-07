"""Versioned, private paired Calibration round; never an organic serving path.

Wire aliases current/value_core keep installed clients compatible. They identify
no scientific engine here: MODEL_VERSIONS is the authoritative attribution.
"""
from __future__ import annotations

import hashlib
import json
import random
import secrets
import threading
import time
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from . import blind_grading as grading, database as db

ROUND_ID = "outlook-v2-v3-1"
MODEL_VERSIONS = {"current": "owner-v2-bilateral-2", "value_core": "owner-v2-bilateral-3"}
PER_ARM = 20
MIN_PER_ARM = 1
MAX_BATCH = 100
LEASE_SECONDS = 3600
_worker_lock = threading.Lock()
_kick_lock = threading.Lock()
_worker_thread = None


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def enabled():
    from .feature_flags import is_enabled
    return is_enabled("grading.outlook_round")


def build_enabled():
    from .feature_flags import is_enabled
    return enabled() or is_enabled("grading.outlook_prepare")


def start_session(*, user_id, league_user_id, league_id, now=None, seed=None):
    """One active/completed exercise per account/league/round; failures may retry."""
    existing = db.load_open_grading_session(user_id, league_id,
        statuses=("building", "open", "completed"), round_id=ROUND_ID)
    if existing and existing["status"] == "open" and not existing.get("first_exposed_at") and not db.grading_progress(existing["session_id"])["answered"]:
        from .outlook_calibration_adapter import is_current
        source = json.loads(existing["source_json"])
        if not is_current(source.get("snapshot") or {}, user_id=user_id,
                          league_user_id=league_user_id or source.get("seat"), league_id=league_id):
            if db.retire_grading_session(existing["session_id"], _json({"code": "comparison_stale"})):
                existing = None
    if existing:
        return {"session": grading.session_view(existing), "resumed": True,
                "needs_build": existing["status"] == "building"}
    now = now or datetime.now(timezone.utc)
    row = {"session_id": grading.new_id(), "user_id": user_id, "league_id": league_id,
        "round_id": ROUND_ID, "active_round_key": hashlib.sha256(
            _json([user_id, league_id, ROUND_ID]).encode()).hexdigest(),
        "status": "building", "seed": str(secrets.randbits(63) if seed is None else seed),
        "created_at": now.isoformat(), "completed_at": None, "counts_json": "{}",
        "source_json": _json({"version": ROUND_ID, "seat": league_user_id,
                              "model_versions": MODEL_VERSIONS, "build_stage": "queued"}),
        "error_json": None}
    try:
        db.insert_grading_session(row, [])
    except db.AccountGone:
        raise grading.GradingError("account_unavailable", 409) from None
    except IntegrityError:
        existing = db.load_open_grading_session(user_id, league_id,
            statuses=("building", "open", "completed"), round_id=ROUND_ID)
        if existing is None:
            raise
        return {"session": grading.session_view(existing), "resumed": True,
                "needs_build": existing["status"] == "building"}
    return {"session": grading.session_view(row), "resumed": False, "needs_build": True}


def current_session(*, user_id, league_id):
    row = db.load_open_grading_session(user_id, league_id,
        statuses=("building", "open", "completed", "failed"), round_id=ROUND_ID)
    if row and row["status"] == "open" and not row.get("first_exposed_at") and not db.grading_progress(row["session_id"])["answered"]:
        source = json.loads(row["source_json"])
        return {"session": start_session(user_id=user_id, league_id=league_id,
                                          league_user_id=source["seat"])["session"]}
    return {"session": grading.session_view(row) if row and row["status"] != "completed" else None}


def next_card(*, user_id, row):
    """Known changes may replace an unexposed deck, never a visible exercise."""
    sid = row["session_id"]
    if row["status"] not in {"open", "completed"}:
        raise grading.GradingError("comparison_not_ready", 409)
    if (row["status"] == "open" and not row.get("first_exposed_at")
            and not db.grading_progress(sid)["answered"] and not enabled()):
        raise grading.GradingError("round_paused", 409)
    if row["status"] == "open" and not row.get("first_exposed_at"):
        from .outlook_calibration_adapter import is_current
        source = json.loads(row["source_json"])
        if not is_current(source.get("snapshot") or {}, user_id=user_id,
                          league_user_id=source.get("seat"), league_id=row["league_id"]):
            if db.retire_grading_session(sid, _json({"code": "comparison_stale"})):
                if enabled():
                    start_session(user_id=user_id, league_user_id=source.get("seat"), league_id=row["league_id"])
                    kick_worker()
                raise grading.GradingError("comparison_not_ready", 409)
        gs = db.grading_sessions_table
        with db.engine.begin() as conn:
            conn.execute(update(gs).where(gs.c.session_id == sid, gs.c.user_id == user_id,
                gs.c.status == "open", gs.c.first_exposed_at.is_(None)).values(
                    first_exposed_at=datetime.now(timezone.utc).isoformat()))
        row = db.load_grading_session(sid, user_id)
        if row is None or row["status"] not in {"open", "completed"}:
            raise grading.GradingError("comparison_not_ready", 409)
    progress = db.grading_progress(sid)
    card = db.load_next_grading_card(sid) if row["status"] == "open" else None
    if card is None:
        return {"done": True, "session_id": sid, "progress": progress}
    return {"done": False, "session_id": sid, "progress": progress,
            "card": {"card_id": card["card_id"], "position": card["position"],
                     "trade": json.loads(card["trade_json"])}}


def _save_build(session_id, source, counts, lease_token=None):
    row = db.load_grading_session(session_id)
    if row is None:
        return False
    gs = db.grading_sessions_table
    where = [gs.c.session_id == session_id, gs.c.status == "building", gs.c.round_id == ROUND_ID]
    if lease_token is not None:
        lease = db.grading_build_leases_table
        where.append(select(lease.c.lease_key).where(lease.c.lease_key == ROUND_ID,
            lease.c.token == lease_token, lease.c.expires_at > datetime.now(timezone.utc).isoformat()).exists())
    with db.engine.begin() as conn:
        db._lock_grading_owner(conn, row["user_id"], source)
        result = conn.execute(update(gs).where(*where).values(
                source_json=_json(source), counts_json=_json(counts)))
    return bool(result.rowcount)


def balanced_order(merged, seed):
    """Exclusive arms alternate in randomized pairs; shared cards enter random slots.

    Equal quotas imply equal unique counts. Thus no exclusive-arm prefix differs
    by more than one card. Shared observations increment both exposure counts.
    """
    rng = random.Random(seed)
    buckets = {arm: [] for arm in MODEL_VERSIONS}
    shared = []
    for card in merged:
        (shared if len(card["arms"]) == 2 else buckets[next(iter(card["arms"]))]).append(card)
    for cards in [*buckets.values(), shared]:
        rng.shuffle(cards)
    if len(buckets["current"]) != len(buckets["value_core"]):
        raise ValueError("unequal selection quotas")
    order = []
    for pair in zip(buckets["current"], buckets["value_core"]):
        pair = list(pair)
        rng.shuffle(pair)
        order.extend(pair)
    for card in shared:
        order.insert(rng.randrange(len(order) + 1), card)
    return order


def build_session(*, session_id, capture=None, lease_token=None):
    """Called only under the durable serial worker lease; no fallback or recapture.

    A crash after capture leaves an immutable interrupted snapshot. A fresh
    exercise can then retry; it cannot silently bind old answers to new inputs.
    """
    row = db.load_grading_session(session_id)
    if not row or row.get("round_id") != ROUND_ID or row["status"] != "building":
        return
    source, counts = json.loads(row["source_json"]), json.loads(row["counts_json"])
    if source.get("build_stage") != "queued":
        db.fail_grading_session(session_id, _json({"code": "comparison_interrupted"}), lease_token=lease_token)
        return
    try:
        if capture is None:
            from .outlook_calibration_adapter import capture
        source["build_stage"] = "capturing"
        if not _save_build(session_id, source, counts, lease_token):
            return
        frozen = capture(user_id=row["user_id"], league_user_id=source["seat"], league_id=row["league_id"])
        source.update(snapshot=frozen.source, build_stage="captured")
        source["seat"] = frozen.source.get("league_user_id") or source["seat"]
        if not _save_build(session_id, source, counts, lease_token):
            return
        inventories, full_keys = {}, {}
        counts.update(arms={}, selection_policy="equal_top_n_max20_min1", total=0)
        # Randomized execution order avoids a systematic warm-cache arm advantage.
        arms = list(MODEL_VERSIONS)
        random.Random(int(row["seed"]) ^ 0xA3).shuffle(arms)
        source["execution_order"] = arms
        for arm in arms:
            version = MODEL_VERSIONS[arm]
            try:
                cards, diagnostics = frozen.run_arm(version)
                unique_keys, selected = set(), []
                card = proof = None
                for rank, card in enumerate(cards):
                    proof = card.owner_evaluation
                    if proof.model_identity[1] != version or not proof.matches(card):
                        raise ValueError("comparison proof identity mismatch")
                    partner, give, receive = str(card.target_user_id), tuple(card.give_player_ids), tuple(card.receive_player_ids)
                    key = (partner, frozenset(give), frozenset(receive))
                    if not (set(give) <= frozen.catalog.holdings.get(source["seat"], frozenset())
                            and set(receive) <= frozen.catalog.holdings.get(partner, frozenset())):
                        raise ValueError("comparison ownership mismatch")
                    if key not in unique_keys and len(selected) < PER_ARM:
                        selected.append(grading.ArmCard(arm, partner, give, receive,
                            {"model_version": version, "rank": rank, "proof": proof.as_dict(),
                             "roster": getattr(card, "roster_evaluation", None)}))
                    unique_keys.add(key)
                inventories[arm], full_keys[arm] = selected, unique_keys
                counts["arms"][version] = {"final_occurrences": len(cards), "unique_inventory": len(unique_keys),
                    "duplicate_occurrences": len(cards) - len(unique_keys), "selected": 0,
                    "diagnostics": diagnostics, "status": "complete"}
                # Full inventories were generated and checked. Only the bounded
                # review selection needs expanded proof dictionaries retained.
                del cards, card, proof
            except Exception as err:
                counts["arms"][version] = {"status": "error", "error_type": type(err).__name__, "selected": 0}
            finally:
                cards = card = proof = None
            if not _save_build(session_id, source, counts, lease_token):
                return
        if len(inventories) != 2:
            raise grading.GradingError("comparison_failed", 409)
        counts["inventory_shared"] = len(full_keys["current"] & full_keys["value_core"])
        counts["inventory_unique"] = {MODEL_VERSIONS[a]: len(keys - full_keys[b])
            for a, b in (("current", "value_core"), ("value_core", "current"))
            for keys in [full_keys[a]]}
        n = min(PER_ARM, *(len(c) for c in inventories.values()))
        counts["comparison_available"] = n >= MIN_PER_ARM
        counts["sample_size_status"] = "limited" if n < 10 else "descriptive_only"
        if n < MIN_PER_ARM:
            _save_build(session_id, source, counts, lease_token)
            raise grading.GradingError("comparison_too_few", 409)
        selected = [c for a in MODEL_VERSIONS for c in inventories[a][:n]]
        order = balanced_order(grading.merge_cards(selected), int(row["seed"]))
        cards = []
        source["proofs"] = {}
        for i, c in enumerate(order, 1):
            cid = grading.new_id()
            proofs = {arm: {k: v for k, v in provenance.items() if k in {"proof", "roster"}}
                      for arm, provenance in c["arms"].items()}
            source["proofs"][cid] = proofs
            attribution = {arm: {"model_version": provenance["model_version"], "rank": provenance["rank"],
                                "proof_hash": hashlib.sha256(_json(proofs[arm]).encode()).hexdigest()}
                           for arm, provenance in c["arms"].items()}
            cards.append({"card_id": cid, "session_id": session_id, "user_id": row["user_id"],
                "partner_user_id": c["partner_id"], "position": i, "arms_json": _json(attribution),
                "trade_json": _json(grading.neutral_trade(c["partner_id"], c["give"], c["receive"], frozen.catalog)),
                "grade": None, "skipped": 0, "tags_json": "[]", "graded_at": None})
        counts.update(total=len(cards), shared=sum(len(c["arms"]) == 2 for c in order))
        for arm in MODEL_VERSIONS:
            counts["arms"][MODEL_VERSIONS[arm]]["selected"] = n
            counts["arms"][MODEL_VERSIONS[arm]]["selected_unique"] = n - counts["shared"]
        source["build_stage"] = "complete"
        db.finish_grading_session_build(session_id, cards, counts_json=_json(counts), source_json=_json(source), lease_token=lease_token)
    except db.AccountGone:
        db.fail_grading_session(session_id, _json({"code": "comparison_inputs_unavailable"}), lease_token=lease_token)
    except grading.GradingError as err:
        db.fail_grading_session(session_id, _json({"code": err.code}), lease_token=lease_token)
    except Exception:
        db.fail_grading_session(session_id, _json({"code": "comparison_failed"}), lease_token=lease_token)


def _claim_lease(token, now):
    table = db.grading_build_leases_table
    expiry = (now + timedelta(seconds=LEASE_SECONDS)).isoformat()
    try:
        with db.engine.begin() as conn:
            conn.execute(table.insert().values(lease_key=ROUND_ID, token=token, expires_at=expiry))
        return True
    except IntegrityError:
        with db.engine.begin() as conn:
            res = conn.execute(update(table).where(table.c.lease_key == ROUND_ID,
                table.c.expires_at <= now.isoformat()).values(token=token, expires_at=expiry))
        return bool(res.rowcount)


def _renew_lease(token):
    table = db.grading_build_leases_table
    now = datetime.now(timezone.utc)
    with db.engine.begin() as conn:
        result = conn.execute(update(table).where(table.c.lease_key == ROUND_ID,
            table.c.token == token, table.c.expires_at > now.isoformat()).values(
                expires_at=(now + timedelta(seconds=LEASE_SECONDS)).isoformat()))
    return bool(result.rowcount)


def _heartbeat(token, stop, lost):
    while not stop.wait(30):
        try:
            if _renew_lease(token):
                continue
        except Exception:
            pass
        lost.set()
        return


def drain_queue(*, capture=None, max_jobs=MAX_BATCH):
    """At most one cross-process builder, bounded batch/time, durable pending rows."""
    if not _worker_lock.acquire(blocking=False):
        return {"busy": True}
    token, processed, started = secrets.token_hex(16), 0, time.monotonic()
    stop, lost = threading.Event(), threading.Event()
    try:
        if not _claim_lease(token, datetime.now(timezone.utc)):
            return {"busy": True}
        threading.Thread(target=_heartbeat, args=(token, stop, lost),
                         name="calibration-lease", daemon=True).start()
        while (processed < min(max_jobs, MAX_BATCH) and time.monotonic() - started < 900
               and build_enabled() and not lost.is_set()):
            gs = db.grading_sessions_table
            with db.engine.connect() as conn:
                sid = conn.execute(select(gs.c.session_id).where(gs.c.round_id == ROUND_ID,
                    gs.c.status == "building").order_by(gs.c.created_at, gs.c.session_id).limit(1)).scalar()
            if sid is None:
                break
            build_session(session_id=sid, capture=capture, lease_token=token)
            processed += 1
        return {"processed": processed, **({"busy": True} if lost.is_set() else {})}
    finally:
        stop.set()
        table = db.grading_build_leases_table
        try:
            with db.engine.begin() as conn:
                conn.execute(table.delete().where(table.c.lease_key == ROUND_ID, table.c.token == token))
        finally:
            _worker_lock.release()


def _pending_work():
    gs = db.grading_sessions_table
    with db.engine.connect() as conn:
        return conn.execute(select(gs.c.session_id).where(gs.c.round_id == ROUND_ID,
            gs.c.status == "building").limit(1)).scalar() is not None


def _worker_main():
    global _worker_thread
    result = None
    try:
        result = drain_queue()
    finally:
        # Recheck after dropping the old worker reference under the same lock
        # used by request kickoffs: an enqueue at the last empty read cannot
        # strand work. A lease owned elsewhere does not trigger a retry spin.
        with _kick_lock:
            _worker_thread = None
            if result is not None and not result.get("busy") and build_enabled() and _pending_work():
                _launch_worker_locked()


def _launch_worker_locked():
    global _worker_thread
    _worker_thread = threading.Thread(target=_worker_main, name="outlook-calibration", daemon=True)
    _worker_thread.start()


def kick_worker():
    with _kick_lock:
        if build_enabled() and (_worker_thread is None or not _worker_thread.is_alive()):
            _launch_worker_locked()


def results(row):
    cards = db.load_grading_cards(row["session_id"])
    arms, shared = grading.arm_summaries(cards)
    return {"session_id": row["session_id"], "league_id": row["league_id"],
        "completed_at": row["completed_at"], "total": len(cards), "shared": shared,
        "target_mean": grading.TARGET_MEAN, "arms": arms, "round_id": ROUND_ID,
        "model_versions": MODEL_VERSIONS,
        "sample_size_status": json.loads(row["counts_json"]).get("sample_size_status", "descriptive_only"),
        "arm_labels": {"current": "Today's engine", "value_core": "New engine"}}


def report(*, since=None, include_open=False):
    if since is not None:
        from datetime import date
        try:
            date.fromisoformat(since)
        except (TypeError, ValueError):
            raise grading.GradingError("invalid_since", 400) from None
    all_sessions, all_cards = db.load_grading_report_rows(None, True, round_id=ROUND_ID)
    sessions = [s for s in all_sessions if since is None or s["created_at"] >= since]
    selected_ids = {s["session_id"] for s in sessions}
    cards = [c for c in all_cards if c["session_id"] in selected_ids]
    statuses = Counter(s["status"] for s in sessions)
    answered = Counter(c["session_id"] for c in all_cards if c["graded_at"] is not None)
    targets, coverage = connected_targets()
    connected = {(t["user_id"], t["league_id"]) for t in targets}
    latest = {}
    for s in all_sessions:  # database orders by created_at/session_id
        pair = (s["user_id"], s["league_id"])
        if pair in connected:
            latest[pair] = s
    readiness = Counter({"not_queued": len(connected) - len(latest)})
    for s in latest.values():
        state = s["status"]
        if state == "building":
            state = "queued"
        elif state == "open":
            state = "started" if s.get("first_exposed_at") or answered[s["session_id"]] else "ready"
        readiness[state] += 1
    revisions = Counter(json.loads(s["source_json"]).get("snapshot", {}).get("code_revision", "unrecorded")
                        for s in sessions)
    by_id = {s["session_id"]: s for s in sessions}
    groups = {}
    for status_group, statuses_in in (("completed", {"completed"}), ("partial", {"open"})):
        relevant = [s for s in sessions if s["status"] in statuses_in
                    and (s["status"] == "completed" or s.get("first_exposed_at") or answered[s["session_id"]])]
        relevant_ids = {s["session_id"] for s in relevant}
        rows = [c for c in cards if c["session_id"] in relevant_ids]
        arms, shared = grading.arm_summaries(rows)
        groups[status_group] = {"sessions": len(relevant),
            "distinct_accounts": len({s["user_id"] for s in relevant}),
            "distinct_graders": len({s["user_id"] for s in relevant if answered[s["session_id"]]}),
            "distinct_leagues": len({s["league_id"] for s in relevant}),
            "selected_cards": len(rows), "shared": shared,
            "answered_observations": sum(c["graded_at"] is not None for c in rows),
            "arms": {MODEL_VERSIONS[a]: arms[a] for a in MODEL_VERSIONS}}
    # No personal boards, names, or user identifiers in the aggregate admin report.
    return {"round_id": ROUND_ID, "model_versions": MODEL_VERSIONS,
        "status_counts": dict(statuses), "status_counts_scope": "historical_attempts_in_report_period",
        "readiness_counts": dict(readiness), "readiness_scope": "latest_attempt_per_current_connected_pair_all_time",
        "coverage": coverage,
        "source_revision_counts": dict(revisions),
        "interpretation": "descriptive_only_shared_cards_are_one_observation_with_dual_credits",
        "completed": groups["completed"],
        **({"partial": groups["partial"]} if include_open else {}),
        "failures": dict(Counter(json.loads(s["error_json"] or "{}").get("code", "unknown")
                                  for s in sessions if s["status"] == "failed")),
        "inventory_totals": {key: sum(json.loads(s["counts_json"]).get(key, 0) for s in sessions)
                             for key in ("inventory_shared", "total", "shared")},
        "arm_inventory_totals": {v: {k: sum(json.loads(s["counts_json"]).get("arms", {}).get(v, {}).get(k, 0)
                                          for s in sessions)
                                    for k in ("final_occurrences", "unique_inventory", "duplicate_occurrences", "selected", "selected_unique")}
                                 for v in MODEL_VERSIONS.values()}}


def connected_targets():
    """Known own-account league actions, never the imported opponent roster list.

    Membership alone is not a connection. Existing app users must be verified;
    provider capture revalidates the actual current seat and supported platform.
    """
    u, lg = db.users_table, db.leagues_table
    with db.engine.connect() as conn:
        users = set(conn.execute(select(u.c.sleeper_user_id).where(u.c.verified_via.is_not(None))).scalars())
        league_platforms = dict(conn.execute(select(lg.c.sleeper_league_id, lg.c.platform)).tuples().all())
        leagues = set(league_platforms)
        pairs = set(conn.execute(select(lg.c.user_id, lg.c.sleeper_league_id)).tuples())
        for table in (db.league_preferences_table, db.member_rankings_table, db.grading_sessions_table):
            pairs.update(conn.execute(select(table.c.user_id, table.c.league_id)).tuples())
        events = db.user_events_table
        pairs.update(conn.execute(select(events.c.user_id, events.c.league_id).where(
            events.c.event_type == "league_synced", events.c.source == "api")).tuples())
        ov = db.overhauls_table
        pairs.update(conn.execute(select(ov.c.account_user_id, ov.c.league_id)).tuples())
        seats = {(r.account_user_id, r.league_id): r.league_user_id for r in conn.execute(
            select(ov.c.account_user_id, ov.c.league_id, ov.c.league_user_id).order_by(ov.c.created_at))}
        gs = db.grading_sessions_table
        for row in conn.execute(select(gs.c.user_id, gs.c.league_id, gs.c.source_json).order_by(gs.c.created_at)):
            seat = json.loads(row.source_json or "{}").get("seat")
            if seat:
                seats[row.user_id, row.league_id] = seat
    targets = [{"user_id": uid, "league_id": lid, "league_user_id": seats.get((uid, lid))}
               for uid, lid in sorted((u, l) for u, l in pairs if u is not None and l is not None)
               if uid in users and lid in leagues and lid != "league_demo"]
    return targets, {"registered_verified_users": len(users), "connected_pairs": len(targets),
                     "users_without_connected_league": len(users - {t["user_id"] for t in targets}),
                     "connected_platform_pairs": dict(Counter(league_platforms[t["league_id"]] or "sleeper" for t in targets))}


def pregenerate(*, offset=0, limit=MAX_BATCH, targets=None):
    """Queue only authorized connected pairs. Generation runs sequentially elsewhere."""
    if not build_enabled():
        raise grading.GradingError("round_disabled", 409)
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise grading.GradingError("invalid_body", 400)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_BATCH:
        raise grading.GradingError("invalid_body", 400)
    connected, coverage = connected_targets()
    if targets is not None:
        if not isinstance(targets, list) or not targets or len(targets) > MAX_BATCH:
            raise grading.GradingError("invalid_body", 400)
        wanted = {(str(t.get("user_id", "")), str(t.get("league_id", ""))) for t in targets if isinstance(t, dict)}
        available = {(t["user_id"], t["league_id"]) for t in connected}
        if len(wanted) != len(targets) or not wanted <= available:
            raise grading.GradingError("unconnected_target", 400)
        connected = [t for t in connected if (t["user_id"], t["league_id"]) in wanted]
    selected = connected[offset:offset + limit]
    statuses, skipped = Counter(), Counter()
    for target in selected:
        try:
            result = start_session(**target)
            statuses[result["session"]["status"]] += 1
        except grading.GradingError as err:
            skipped[err.code] += 1
    next_offset = offset + len(selected)
    return {"round_id": ROUND_ID, **coverage, "batch_pairs": len(selected),
        "batch_status_counts": dict(statuses), "skipped_reasons": dict(skipped), "next_offset": next_offset if next_offset < len(connected) else None,
        "remaining_pairs": max(0, len(connected) - next_offset)}
