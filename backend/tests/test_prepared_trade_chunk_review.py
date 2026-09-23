"""Independent chunk qualification: real telemetry and bounded SQL publication.

Synthetic sources, isolated SQL, actual constructor/receipts/logger/adoption.
These small controls are not the dense-constructor memory qualification.
"""
from copy import deepcopy
import json
import time

import pytest

from sqlalchemy import event, insert, update

from backend import database as db, server
from backend import prepared_trade_runtime as runtime
from backend.tests.test_prepared_trade_runtime_review import (
    headless, large_exclusive, exclusive, owner_harness, harness, new_claim,
)
from backend.tests.test_prepared_trade_runtime import adopt
from backend.tests.test_owner_generator_routes import rows, TOKEN


def _parameter_bytes(value):
    """Independent observed bind-value accounting; never log bound values."""
    if value is None:
        return 0
    if isinstance(value, str):
        return len(value.encode("utf-8"))
    if isinstance(value, (bytes, bytearray, memoryview)):
        return len(value)
    if isinstance(value, dict):
        return sum(_parameter_bytes(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return sum(_parameter_bytes(item) for item in value)
    if type(value) in (bool, int, float):
        return len(str(value).encode("ascii"))
    raise AssertionError(f"unexpected SQL parameter type: {type(value).__name__}")


def test_real_telemetry_candidate_dependency_is_quiet_exact_and_retryable(headless, monkeypatch):
    fixture, target = headless
    client, engine, _, original_service, _ = fixture
    monkeypatch.setattr(server, "_suggestion_telemetry_enabled", lambda: True)
    candidate_records, originals, proof_strings, statements = [], {}, {}, []
    retained_public_snapshots = []
    commit_failures = []
    original_worker = server._run_trade_job

    def worker(*args, **kwargs):
        sink = kwargs["prepare_sink"]
        save_candidate, save_impressions = sink.candidate_set, sink.impressions

        def candidate(record):
            candidate_records.append(deepcopy(record))
            return save_candidate(record)

        def impressions(records):
            for record in records:
                assert record["impression_id"] not in originals
                originals[record["impression_id"]] = deepcopy(record)
            return save_impressions(records)

        monkeypatch.setattr(sink, "candidate_set", candidate)
        monkeypatch.setattr(sink, "impressions", impressions)
        result = original_worker(*args, **kwargs)
        for card in kwargs["execution_context"].trade_service._trade_cards.values():
            if getattr(card, "owner_evaluation", None) is not None:
                proof_strings[card.trade_id] = card.owner_evaluation.snapshot_json
        return result

    def observe(_conn, _cursor, statement, parameters, _context, _many):
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE")):
            # Bound the whole execute/executemany, not merely each row.
            statements.append(_parameter_bytes(parameters))

    monkeypatch.setattr(server, "_run_trade_job", worker)
    event.listen(engine, "before_cursor_execute", observe)
    try:
        scope, _, claim = new_claim(target)
        runtime.prepare_target(server, claim)
        assert len(candidate_records) == 1
        candidate = candidate_records[0]
        members = json.loads(candidate["candidates_json"])
        assert candidate["size"] == len(members) >= 64
        assert len(candidate["candidates_json"].encode("utf-8")) > 0
        for table in (db.deck_candidate_sets_table, db.deck_impressions_table,
                      db.deck_diagnostic_snapshots_table, db.user_events_table,
                      db.trade_decisions_table, db.trade_impressions_table):
            assert rows(engine, table) == []
        assert not original_service._trade_cards

        fresh = runtime.build_session(server, deepcopy(target))
        adopted_fixture = (client, engine, fresh, fresh["trade_svc"], fresh["league"])
        from backend import prepared_trade_store_v2 as paged_store
        original_commit = paged_store.ensure_adoption_evidence

        def commit(*args, **kwargs):
            # The /generate route can retain a shallow job snapshot outside
            # its lock. Later publication must replace, not extend, that list.
            job = server._trade_jobs.get("telemetry-review")
            if job and job.get("cards"):
                retained_public_snapshots.append((job["cards"], deepcopy(job["cards"])))
            try:
                return original_commit(*args, **kwargs)
            except Exception as exc:
                commit_failures.append(str(exc))  # Synthetic fixture only.
                raise

        monkeypatch.setattr(paged_store, "ensure_adoption_evidence", commit)
        handled, job = adopt((adopted_fixture, None, scope, None), monkeypatch, "telemetry-review")
        assert handled and job["status"] == "complete", (job, commit_failures)
        assert len(job["cards"]) >= 64
        durable_candidates = [dict(row) for row in rows(engine, db.deck_candidate_sets_table)]
        assert durable_candidates == [candidate]
        durable = [dict(row) for row in rows(engine, db.deck_impressions_table)]
        assert len(durable) == len(originals)
        for row in durable:
            original = originals[row["impression_id"]]
            for key in ("valuation_json", "assets_json", "trade_hash", "candidate_set_id",
                        "candidate_set_size", "source_like_impression_id", "card_index"):
                assert row.get(key) == original.get(key)
        for public in job["cards"]:
            card = fresh["trade_svc"]._trade_cards[public["trade_id"]]
            assert card.owner_evaluation.snapshot_json == proof_strings[card.trade_id]
        assert retained_public_snapshots
        assert all(current == frozen for current, frozen in retained_public_snapshots)
        assert statements and max(statements) <= 2 * 1024 * 1024
        # A new process-like service recovers original candidate/evidence IDs and
        # first-adoption clocks; an exact retry must not append duplicate rows.
        again = runtime.build_session(server, deepcopy(target))
        retry_fixture = (client, engine, again, again["trade_svc"], again["league"])
        handled, retried = adopt((retry_fixture, None, scope, None), monkeypatch, "telemetry-review-retry")
        assert handled and retried["status"] == "complete", retried
        assert retried["cards"] == job["cards"]
        assert durable == [dict(row) for row in rows(engine, db.deck_impressions_table)]
        assert durable_candidates == [dict(row) for row in rows(engine, db.deck_candidate_sets_table)]
        assert max(statements) <= 2 * 1024 * 1024
        assert not rows(engine, db.trade_decisions_table) and not rows(engine, db.user_events_table)
    finally:
        event.remove(engine, "before_cursor_execute", observe)


@pytest.mark.parametrize("change", ["local_source", "second_write_failure"])
def test_paged_runtime_never_publishes_an_uncommitted_or_stale_suffix(headless, monkeypatch, change):
    fixture, target = headless
    client, engine, _, _, _ = fixture
    scope, _, claim = new_claim(target)
    runtime.prepare_target(server, claim)
    fresh = runtime.build_session(server, deepcopy(target))
    adopted_fixture = (client, engine, fresh, fresh["trade_svc"], fresh["league"])
    from backend import prepared_trade_store_v2 as paged_store
    original_commit = paged_store.ensure_adoption_evidence
    attempts, published_prefixes = [], []

    def commit(*args, **kwargs):
        job = server._trade_jobs.get("boundary-review")
        attempts.append(len(kwargs["rows"]))
        if len(attempts) == 2:
            published_prefixes.append(deepcopy(job["cards"]))
            assert len(job["cards"]) == 30
            if change == "second_write_failure":
                raise RuntimeError("synthetic second evidence failure")
        result = original_commit(*args, **kwargs)
        if len(attempts) == 2 and change == "local_source":
            # Current read safety changes after durability, before the next
            # publication. The frozen request itself remains untouched.
            seed = server.g_universal_by_format["1qb_ppr"]["seed"]
            seed[next(iter(seed))] += 1.
        return result

    monkeypatch.setattr(paged_store, "ensure_adoption_evidence", commit)
    handled, job = adopt((adopted_fixture, None, scope, None), monkeypatch, "boundary-review")
    assert handled and len(attempts) == 2 and attempts[0] == 30
    assert published_prefixes and job["status"] == "error"
    if change == "local_source":
        assert job["error"] == "inputs_changed"
        assert not job["cards"] and not fresh["trade_svc"]._trade_cards
        assert len(rows(engine, db.deck_impressions_table)) > 30
        assert server._trade_job_public_view(deepcopy(job))["cards"] == []
    else:
        assert job["error"] == "prepared_adoption_incomplete"
        assert job["cards"] == published_prefixes[0]
        assert len(fresh["trade_svc"]._trade_cards) == 30
        assert len(rows(engine, db.deck_impressions_table)) == 30
        assert paged_store.peek_inventory(scope) is not None
        original_rows = {row["impression_id"]: dict(row) for row in rows(engine, db.deck_impressions_table)}
        retry = runtime.build_session(server, deepcopy(target))
        retry_fixture = (client, engine, retry, retry["trade_svc"], retry["league"])
        handled_again, recovered = adopt((retry_fixture, None, scope, None), monkeypatch, "boundary-review-retry")
        assert handled_again and recovered["status"] == "complete"
        assert recovered["cards"][:30] == published_prefixes[0]
        assert len(recovered["cards"]) > 30
        final_rows = {row["impression_id"]: dict(row) for row in rows(engine, db.deck_impressions_table)}
        assert {key: final_rows[key] for key in original_rows} == original_rows
    assert not rows(engine, db.trade_decisions_table) and not rows(engine, db.user_events_table)


def test_runtime_retires_exact_corrupt_inventory_after_valid_prefix_and_next_job_misses(headless, monkeypatch):
    fixture, target = headless
    client, engine, _, _, _ = fixture
    from backend import prepared_trade_store_v2 as paged_store, prepared_trade_payload_v2 as codec
    monkeypatch.setattr(codec, "PAGE_TARGET_BYTES", 1)
    scope, _, claim = new_claim(target)
    runtime.prepare_target(server, claim)
    cached = paged_store.peek_inventory(scope).header
    assert cached["card_count"] >= 64
    page = next(row for row in rows(engine, paged_store.P)
        if row["inventory_id"] == cached["inventory_id"] and row["kind"] == "cards"
        and row["ordinal_start"] == 40)
    damaged = paged_store._decode(page)
    damaged[0]["owner_evaluation"]["snapshot_json"] = "{}"
    with engine.begin() as conn:
        conn.execute(update(paged_store.P).where(
            paged_store.P.c.inventory_id == cached["inventory_id"],
            paged_store.P.c.kind == "cards", paged_store.P.c.page_index == page["page_index"])
            .values(**paged_store._encode(damaged)))
    fresh = runtime.build_session(server, deepcopy(target))
    actual_fixture = (client, engine, fresh, fresh["trade_svc"], fresh["league"])
    handled, job = adopt((actual_fixture, None, scope, None), monkeypatch, "corrupt-prefix-review")
    assert handled and job["status"] == "error" and job["error"] == "prepared_adoption_incomplete"
    assert len(job["cards"]) == len(fresh["trade_svc"]._trade_cards) == 30
    original_rows = [dict(row) for row in rows(engine, db.deck_impressions_table)]
    assert len(original_rows) == 30
    manifest = next(row for row in rows(engine, paged_store.M) if row["inventory_id"] == cached["inventory_id"])
    assert manifest["state"] == "retired" and manifest["active_scope_key"] is None
    assert manifest["adoption_token"] is None and manifest["adoption_lease_until"] is None
    assert manifest["root_sha256"] == cached["root_sha256"] and manifest["adoption_prefix"] == 30
    assert paged_store.peek_inventory(scope) is None
    assert len(server._trade_job_public_view(deepcopy(job))["cards"]) == 30
    retry = runtime.build_session(server, deepcopy(target))
    retry_fixture = (client, engine, retry, retry["trade_svc"], retry["league"])
    handled_again, next_job = adopt((retry_fixture, None, scope, None), monkeypatch, "after-corrupt-retirement")
    assert not handled_again and next_job["cards"] == [] and not retry["trade_svc"]._trade_cards
    assert original_rows == [dict(row) for row in rows(engine, db.deck_impressions_table)]
    assert not rows(engine, db.trade_decisions_table) and not rows(engine, db.user_events_table)


@pytest.mark.parametrize("decision", ["like", "pass"])
def test_real_first_prefix_action_does_not_revoke_unrelated_prepared_suffix(headless, monkeypatch, decision):
    """Real Flask feedback is history, not an explicit reprice of this deck."""
    fixture, target = headless
    client, engine, _, _, _ = fixture
    from backend import prepared_trade_store_v2 as paged_store
    scope, _, claim = new_claim(target)
    runtime.prepare_target(server, claim)
    cached = paged_store.peek_inventory(scope).header
    assert cached["card_count"] >= 64
    fresh = runtime.build_session(server, deepcopy(target))
    fresh.update(verified=True, last_active=time.time())
    monkeypatch.setitem(server._sessions, TOKEN, fresh)
    # Preparation above still used the no-activity fixture. This is now an
    # explicit synthetic human action; event transport remains isolated.
    events = []
    monkeypatch.setattr(server, "record_event", lambda *a, **k: events.append((a, k)))
    original_commit = paged_store.ensure_adoption_evidence
    actions, attempts, responses = [], [], []
    initial_board = rows(engine, db.member_rankings_table)

    def commit(*args, **kwargs):
        attempts.append(True)
        if len(attempts) == 2:
            job = server._trade_jobs["first-action-review"]
            assert len(job["cards"]) == 30
            public = deepcopy(job["cards"][0])
            card = fresh["trade_svc"]._trade_cards[public["trade_id"]]
            original_proof = card.owner_evaluation.snapshot_json
            # Exercise the real janitor's four-hour inactivity boundary at
            # this exact interleaving, without waiting for its daemon tick.
            with server._sessions_lock:
                current = server._sessions.get(TOKEN)
                if current is not None and current.get("last_active", 0) < time.time() - 4 * 3600:
                    server._sessions.pop(TOKEN)
            response = client.post("/api/trades/swipe", headers={"X-Session-Token": TOKEN},
                json={"trade_id": public["trade_id"], "impression_id": public["impression_id"],
                      "decision": decision})
            responses.append((response.status_code, response.json))
            assert response.status_code == 200, response.json
            assert card.owner_evaluation.snapshot_json == original_proof
            actions.append(public)
            assert rows(engine, db.trade_decisions_table)
            assert any(row["decision_type"] == "trade" for row in rows(engine, db.swipe_decisions_table))
            assert fresh["service"]._trade_swipes
            assert rows(engine, db.member_rankings_table) == initial_board
        return original_commit(*args, **kwargs)

    monkeypatch.setattr(paged_store, "ensure_adoption_evidence", commit)
    actual_fixture = (client, engine, fresh, fresh["trade_svc"], fresh["league"])
    handled, job = adopt((actual_fixture, None, scope, None), monkeypatch, "first-action-review")
    assert actions and events, responses
    assert handled and job["status"] == "complete", job
    assert len(job["cards"]) == cached["card_count"]
    assert len(rows(engine, db.deck_impressions_table)) == cached["card_count"]
    visible = server._trade_job_public_view(deepcopy(job))["cards"]
    assert visible
    if decision == "pass":
        assert actions[0]["trade_id"] not in {card["trade_id"] for card in visible}
    assert paged_store.peek_inventory(scope) is not None  # Ordinary history is not corruption.


@pytest.mark.parametrize("explicit_input", ["member_board", "declared_outlook"])
def test_other_process_counterparty_explicit_input_still_revokes_active_prepared_job(headless, monkeypatch, explicit_input):
    """SQL input changes must be seen even without a process-local epoch call."""
    fixture, target = headless
    client, engine, _, _, _ = fixture
    from backend import prepared_trade_store_v2 as paged_store
    scope, _, claim = new_claim(target)
    runtime.prepare_target(server, claim)
    fresh = runtime.build_session(server, deepcopy(target))
    original_commit = paged_store.ensure_adoption_evidence
    attempts = []

    def commit(*args, **kwargs):
        attempts.append(True)
        result = original_commit(*args, **kwargs)
        if len(attempts) == 2:
            assert len(server._trade_jobs["explicit-input-review"]["cards"]) == 30
            opponent = target["opponents"][0]
            # Direct isolated SQL deliberately bypasses invalidation helpers:
            # this models the persistent write from another worker process.
            with engine.begin() as conn:
                if explicit_input == "member_board":
                    conn.execute(insert(db.member_rankings_table).values(
                        user_id=opponent["user_id"], league_id=scope.league_id,
                        player_id=opponent["player_ids"][0], elo=1801.,
                        scoring_format=scope.scoring_format, confidence_source="explicit"))
                else:
                    conn.execute(insert(db.league_preferences_table).values(
                        user_id=opponent["user_id"], league_id=scope.league_id,
                        team_outlook="contender"))
        return result

    monkeypatch.setattr(paged_store, "ensure_adoption_evidence", commit)
    actual_fixture = (client, engine, fresh, fresh["trade_svc"], fresh["league"])
    handled, job = adopt((actual_fixture, None, scope, None), monkeypatch, "explicit-input-review")
    assert handled and len(attempts) == 2
    assert job["status"] == "error" and job["error"] == "inputs_changed"
    assert not job["cards"] and not fresh["trade_svc"]._trade_cards
    assert len(rows(engine, db.deck_impressions_table)) > 30  # Original history retained.
    assert not server._trade_job_public_view(deepcopy(job))["cards"]


def test_current_disposition_callback_miss_never_quarantines_valid_inventory(headless, monkeypatch):
    fixture, target = headless
    client, engine, _, _, _ = fixture
    from backend import prepared_trade_store_v2 as paged_store
    scope, _, claim = new_claim(target)
    runtime.prepare_target(server, claim)
    cached = paged_store.peek_inventory(scope).header
    before = rows(engine, paged_store.M)
    fresh = runtime.build_session(server, deepcopy(target))
    actual_fixture = (client, engine, fresh, fresh["trade_svc"], fresh["league"])
    original_project = server._project_trade_dispositions
    callbacks = []

    def resolved(cards, user_id, league_id, **kwargs):
        assert kwargs.get("prepared") is True
        callbacks.append(len(cards))
        return []  # Read-time eligibility result, not a bad stored record.

    with monkeypatch.context() as local:
        local.setattr(server, "_project_trade_dispositions", resolved)
        handled, job = adopt((actual_fixture, None, scope, None), local, "current-history-miss")
    assert callbacks and not handled and not job["cards"]
    assert rows(engine, paged_store.M) == before
    assert not rows(engine, db.deck_impressions_table)
    assert paged_store.peek_inventory(scope).header == cached
    assert server._project_trade_dispositions is original_project
    handled, retried = adopt((actual_fixture, None, scope, None), monkeypatch, "current-history-retry")
    assert handled and retried["status"] == "complete"
    assert len(retried["cards"]) == cached["card_count"]
