"""E2 small responses: opt-in `page=1` on /generate and `cursor` on /status.

Scope: docs/plans/trade-time-to-suggestion/scope-eng-200ms.md §0b row 2, §3
(`test_trade_responses_small.py`), §6.6 (on branch plan/trades-200ms-eng-scope).

Pinned here:
  * legacy (no `page` / no `cursor`) bodies are byte-identical to the base;
  * the paged first page is at most `trade_page_size` cards and ≤ 64 KB;
  * the cursor indexes the RAW job list: a card filtered after delivery never
    shifts a later card's index;
  * a replacing worker path answers with `replace: true` and the full list;
  * an errored job never pages its partial cards (head-eng rule);
  * validation and the `trade_page_size` clamp.

Legacy method: each legacy body is compared with
`jsonify(_trade_job_public_view(copy.deepcopy(job)))`, which is the base
handlers' exact return expression over an unchanged `_trade_job_public_view`,
AND with a sha256 golden captured by running this same fixture on the base
commit 53caa439 (see LEGACY_GOLDEN_SHA256).

Harness: test_fair_packages' isolated in-memory SQLite + registered session;
the real owner-serve worker test reuses test_owner_only_routes'
`large_exclusive` and test_owner_batch_publication's batch observer.
"""
import copy
import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import insert

from backend import database as db, server, trade_service as ts
from backend.tests.test_fair_packages import harness, ME, OPP, LEAGUE, TOKEN
from backend.tests.test_owner_generator_routes import owner_harness, worker
from backend.tests.test_owner_only_routes import exclusive, large_exclusive
from backend.tests.test_owner_batch_publication import observe_batches
from backend.trade_service import TradeCard


GOLDEN_CARD = json.loads((Path(__file__).parent / "fixtures" / "bakeoff"
                          / "flag_off_golden.json").read_text())["cards"][0]
HEADERS = {"X-Session-Token": TOKEN}
JOB_ID = "e2-job"
# sha256 of the legacy /status and /generate bodies for legacy_job(3), captured
# by running test_legacy_bodies_match_base_golden on base 53caa439.
LEGACY_GOLDEN_SHA256 = "132e19a70221a950648d61c78ad9a1d8b51b7576d2ef191f45d41b4b8f12e46e"


def card(i, *, owner=True):
    """The flag-off golden card plus the fields a production owner card carries."""
    row = copy.deepcopy(GOLDEN_CARD)
    row.update(trade_id=f"e2-trade-{i:05d}", league_id=LEAGUE, target_user_id=OPP,
               impression_id=f"{i:032x}", expires_at="2026-10-27T12:00:00+00:00",
               model_arm="owner_v2_bilateral", generator_version="owner-v2-bilateral-2")
    row["give"][0]["id"] = f"give-{i}"
    row["receive"][0]["id"] = f"recv-{i}"
    if owner:
        row["preserve_server_order"] = True
    return row


def seed_job(cards, *, status="complete", **extra):
    job = dict(job_id=JOB_ID, key=(ME, LEAGUE, "1qb_ppr"), status=status,
               started_at=time.monotonic(), finished_at=time.monotonic(),
               opponents_done=2, opponents_total=2, cards=cards, error=None,
               fairness_threshold=.75, outlook_value=None, is_pinned=False,
               safety_policy=server._trade_safety_signature(), **extra)
    server._trade_jobs[JOB_ID] = job
    server._trade_jobs_by_key[job["key"]] = JOB_ID
    return job


@pytest.fixture
def e2(harness, monkeypatch):
    monkeypatch.setattr(server, "_trade_jobs", {})
    monkeypatch.setattr(server, "_trade_jobs_by_key", {})
    monkeypatch.setattr(server, "load_league_preference", lambda **kw: None)
    monkeypatch.setattr(server, "_infer_user_outlook", lambda *a, **k: (None, None))
    spawned = []
    monkeypatch.setattr(server, "_start_trade_job_thread", lambda **kw: spawned.append(kw))
    client, engine, *_ = harness
    yield client, engine, spawned


def status(client, cursor=None, job_id=JOB_ID):
    query = f"/api/trades/status?job_id={job_id}"
    if cursor is not None:
        query += f"&cursor={cursor}"
    return client.get(query, headers=HEADERS)


def generate(client, **body):
    return client.post("/api/trades/generate", headers=HEADERS,
                       json={"league_id": LEAGUE, "fairness_threshold": .75, **body})


def legacy_bytes(job):
    """The base handlers' return expression, verbatim."""
    with server.app.app_context():
        return server.jsonify(server._trade_job_public_view(copy.deepcopy(job))).get_data()


def ids(cards):
    return [c["trade_id"] for c in cards]


def record_pass(engine, row):
    """An exact pass on `row`'s package, inside the 14-day cooldown."""
    with engine.begin() as conn:
        conn.execute(insert(db.trade_decisions_table).values(
            user_id=ME, league_id=LEAGUE, trade_id="other-id-same-package",
            give_player_ids=json.dumps([p["id"] for p in row["give"]]),
            receive_player_ids=json.dumps([p["id"] for p in row["receive"]]),
            decision="pass",
            created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))


# ── Legacy: no `page`, no `cursor` ⇒ byte-identical ─────────────────────────

@pytest.mark.parametrize("owner", [True, False])
@pytest.mark.parametrize("status_value", ["complete", "running"])
def test_legacy_status_and_generate_are_byte_identical(e2, owner, status_value):
    client, _engine, spawned = e2
    job = seed_job([card(i, owner=owner) for i in range(75)], status=status_value)
    expected = legacy_bytes(job)
    response = status(client)
    assert response.status_code == 200
    assert response.get_data() == expected
    assert len(response.get_json()["cards"]) == 75
    assert not {"cursor", "total_ready", "replace", "search_id"} & set(response.get_json())
    if status_value == "complete":
        # Cache hit; a search_id without `page` is not read, as today.
        for body in ({}, {"search_id": "x" * 100}):
            response = generate(client, **body)
            assert response.status_code == 200
            assert response.get_data() == expected
    assert not spawned


def legacy_job():
    return seed_job([card(i) for i in range(3)])


def test_legacy_bodies_match_base_golden(e2):
    client, *_ = e2
    legacy_job()
    bodies = [status(client).get_data(), generate(client).get_data()]
    assert bodies[0] == bodies[1]
    assert hashlib.sha256(bodies[0]).hexdigest() == LEGACY_GOLDEN_SHA256


def test_legacy_timed_out_job_still_returns_partial_cards(e2):
    """Head-eng: the legacy path is unchanged (S0 owns it), even for errors."""
    client, *_ = e2
    job = seed_job([card(i) for i in range(12)], status="running")
    # The cleanup sweep's own writes (server.py _cleanup_loop, "timeout").
    job.update(status="error", error="timeout", finished_at=time.monotonic())
    response = status(client)
    assert response.get_data() == legacy_bytes(job)
    assert response.get_json()["status"] == "error"
    assert len(response.get_json()["cards"]) == 12


# ── Paged /generate ─────────────────────────────────────────────────────────

def test_paged_generate_first_page_is_bounded_and_small(e2):
    client, _engine, spawned = e2
    raw = [card(i) for i in range(2354)]   # B15's measured production deck
    job = seed_job(raw)
    search_id = str(uuid.uuid4())
    response = generate(client, page=1, search_id=search_id)
    assert response.status_code == 200
    body = response.get_json()
    assert ids(body["cards"]) == ids(raw[:30])
    assert body["cards"] == raw[:30]
    assert (body["cursor"], body["total_ready"], body["replace"]) == (30, 2354, False)
    assert body["search_id"] == search_id
    assert (body["job_id"], body["status"], body["error"]) == (JOB_ID, "complete", None)
    assert (body["opponents_done"], body["opponents_total"]) == (2, 2)
    assert len(response.get_data()) <= 64 * 1024
    assert len(legacy_bytes(job)) > 2_000_000   # what the same request costs today
    assert not spawned


def test_paged_generate_without_search_id_and_on_a_fresh_job(e2):
    client, _engine, spawned = e2
    response = generate(client, page=1)      # cache miss → a new running job
    body = response.get_json()
    assert response.status_code == 200 and len(spawned) == 1
    assert body["status"] == "running" and body["cards"] == []
    assert (body["cursor"], body["total_ready"], body["replace"]) == (0, 0, False)
    assert "search_id" not in body


def test_paged_generate_keeps_optional_envelope_fields(e2):
    client, *_ = e2
    note = {"count": 2, "latest_declined_at": "2026-10-19T00:00:00Z"}
    seed_job([card(i) for i in range(40)], suppression_note=note, first_deck=True)
    body = generate(client, page=1).get_json()
    assert body["suppression_note"] == note and body["first_deck"] is True
    assert len(body["cards"]) == 30


# ── /status?cursor=K ────────────────────────────────────────────────────────

def test_cursor_returns_only_cards_after_the_cursor_and_advances(e2):
    client, *_ = e2
    raw = [card(i) for i in range(75)]
    seed_job(raw)
    held, cursor, cursors = [], 0, []
    for _ in range(4):
        body = status(client, cursor).get_json()
        assert body["replace"] is False and body["total_ready"] == 75
        assert ids(body["cards"]) == ids(raw[cursor:cursor + 30])
        held += body["cards"]
        cursor = body["cursor"]
        cursors.append(cursor)
    assert cursors == [30, 60, 75, 75]
    assert held == raw


def test_filtered_card_never_shifts_later_indices(e2):
    client, engine, *_ = e2
    raw = [card(i) for i in range(75)]
    seed_job(raw)
    first = status(client, 0).get_json()
    assert ids(first["cards"]) == ids(raw[:30])
    # Passes land after delivery: one delivered card, one in the next page.
    record_pass(engine, raw[5])
    record_pass(engine, raw[35])
    legacy = status(client).get_json()["cards"]
    assert ids(legacy) == [c for i, c in enumerate(ids(raw)) if i not in (5, 35)]
    second = status(client, 30).get_json()
    assert ids(second["cards"]) == [r["trade_id"] for i, r in enumerate(raw) if 30 <= i < 60 and i != 35]
    assert second["cursor"] == 60          # the raw index, not 59
    third = status(client, 60).get_json()
    assert ids(third["cards"]) == ids(raw[60:])
    assert third["cursor"] == 75
    again = status(client, 0).get_json()
    assert ids(again["cards"]) == [r["trade_id"] for i, r in enumerate(raw[:30]) if i != 5]
    assert again["cursor"] == 30


def test_value_core_publish_pages_without_replace(e2):
    client, *_ = e2
    raw = [card(i, owner=False) for i in range(45)]
    seed_job(raw, value_core={"served": 45})
    body = status(client, 30).get_json()
    assert ids(body["cards"]) == ids(raw[30:])
    assert (body["cursor"], body["replace"]) == (45, False)


def test_replacing_progress_snapshots_return_full_list_with_replace(e2, harness):
    """The real progress callback re-sorts the cumulative list, so indices move."""
    client, *_ = e2
    _client, _engine, sess, _svc, _league = harness
    seed_job([], status="running")
    players = {p.id: p for p in sess["players"]}

    def tc(trade_id, give, receive):
        return TradeCard(trade_id=trade_id, league_id=LEAGUE, proposing_user_id=ME,
                         target_user_id=OPP, target_username="opp",
                         give_player_ids=[give], receive_player_ids=[receive],
                         mismatch_score=0., fairness_score=.8, composite_score=.5)
    a, b, c = tc("A", "a1", "b1"), tc("B", "a2", "b2"), tc("C", "a1", "b3")
    publish = server._make_progress_cb(JOB_ID, players, {OPP}, None, LEAGUE)
    publish(1, 2, [a, b])
    first = status(client, 0).get_json()
    assert ids(first["cards"]) == ["A", "B"]
    assert (first["cursor"], first["replace"]) == (2, False)
    publish(2, 2, [c, a, b])           # C sorts above what was delivered
    second = status(client, 2).get_json()
    assert ids(second["cards"]) == ["C", "A", "B"]
    assert (second["cursor"], second["total_ready"], second["replace"]) == (3, 3, True)
    assert ids(status(client).get_json()["cards"]) == ["C", "A", "B"]   # legacy unchanged
    # Complete: a cursor from the running phase still cannot be vouched for.
    server._trade_jobs[JOB_ID]["status"] = "complete"
    third = status(client, 3).get_json()
    assert ids(third["cards"]) == ["C", "A", "B"] and third["replace"] is True


def test_cursor_past_the_end_replaces(e2):
    client, *_ = e2
    raw = [card(i) for i in range(10)]
    seed_job(raw)
    body = status(client, 40).get_json()
    assert ids(body["cards"]) == ids(raw)
    assert (body["cursor"], body["total_ready"], body["replace"]) == (10, 10, True)


def test_real_owner_worker_cursor_deltas_are_append_only(large_exclusive, monkeypatch):
    """The production owner-serve path: batches of 30 then 34, polled by cursor."""
    client, engine, *_ = large_exclusive
    held, cursor, seen = [], 0, []

    def poll(job, batch):
        nonlocal cursor
        while True:
            response = client.get(f"/api/trades/status?job_id=owner-route-worker&cursor={cursor}",
                                  headers={"X-Session-Token": TOKEN})
            body = response.get_json()
            assert response.status_code == 200 and body["status"] == "running"
            assert body["replace"] is False
            held.extend(body["cards"])
            seen.append((cursor, body["cursor"], body["total_ready"]))
            if body["cursor"] == cursor:
                return
            cursor = body["cursor"]

    observe_batches(monkeypatch, engine, poll)
    job = worker(large_exclusive, monkeypatch)
    assert seen == [(0, 30, 30), (30, 30, 30), (30, 60, 64), (60, 64, 64), (64, 64, 64)]
    assert held == job["cards"] and len(held) == 64
    assert all(c["preserve_server_order"] for c in held)
    final = client.get(f"/api/trades/status?job_id=owner-route-worker&cursor={cursor}",
                       headers={"X-Session-Token": TOKEN}).get_json()
    assert (final["status"], final["cards"], final["replace"]) == ("complete", [], False)


# ── Errored jobs never page (head-eng rule) ─────────────────────────────────

@pytest.mark.parametrize("cursor", [0, 5, 30])
def test_timed_out_job_in_cursor_mode_returns_no_cards(e2, cursor):
    client, *_ = e2
    job = seed_job([card(i) for i in range(40)], status="running")
    job.update(status="error", error="timeout", finished_at=time.monotonic())
    body = status(client, cursor).get_json()
    assert (body["status"], body["error"], body["cards"]) == ("error", "timeout", [])
    assert (body["cursor"], body["total_ready"], body["replace"]) == (cursor, 0, False)
    assert len(status(client).get_json()["cards"]) == 40   # legacy unchanged


def test_revoked_job_in_cursor_mode_returns_no_cards(e2):
    client, *_ = e2
    job = seed_job([card(i) for i in range(40)], status="running")
    with server._trade_jobs_lock:
        server._revoke_trade_job_locked(job, "superseded")
    body = status(client, 30).get_json()
    assert (body["status"], body["error"], body["cards"]) == ("error", "superseded", [])


# ── Validation and the page-size clamp ──────────────────────────────────────

@pytest.mark.parametrize("page", [0, 2, -1, "1", 1.0, True, None, [1]])
def test_bad_page_is_400_before_any_side_effect(e2, page):
    client, _engine, spawned = e2
    response = generate(client, page=page, refresh_fatigue=True)
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_page"
    assert not spawned and not server._trade_jobs


@pytest.mark.parametrize("search_id", ["x" * 65, "", "has space", "<script>", "é" * 4, 123, ["a"]])
def test_bad_search_id_is_400(e2, search_id):
    client, _engine, spawned = e2
    response = generate(client, page=1, search_id=search_id)
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_search_id"
    assert not spawned


def test_longest_valid_search_id_is_echoed(e2):
    client, *_ = e2
    seed_job([card(i) for i in range(3)])
    sid = "A-z_9" * 12 + "abcd"
    assert len(sid) == 64
    assert generate(client, page=1, search_id=sid).get_json()["search_id"] == sid


@pytest.mark.parametrize("cursor", ["-1", "abc", "", "1.5", "１", "1234567890", "+1", " 1"])
def test_bad_cursor_is_400(e2, cursor):
    client, *_ = e2
    seed_job([card(i) for i in range(3)])
    response = client.get("/api/trades/status", query_string={"job_id": JOB_ID, "cursor": cursor},
                          headers=HEADERS)
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_cursor"


@pytest.mark.parametrize("value,expected", [(30., 30), (5., 5), (0., 1), (-3., 1), (1., 1),
                                            (200., 200), (500., 200), (float("nan"), 30),
                                            (float("inf"), 30)])
def test_trade_page_size_is_clamped(e2, value, expected):
    client, *_ = e2
    ts._cfg["trade_page_size"] = value
    assert server._trade_page_size() == expected
    seed_job([card(i) for i in range(250)])
    body = status(client, 0).get_json()
    assert len(body["cards"]) == expected and body["cursor"] == expected


def test_trade_page_size_is_seeded_at_30():
    assert ("trade_page_size", 30.0) in [row[:2] for row in db._MODEL_CONFIG_DEFAULTS]
    with patch.dict(ts._cfg, {}, clear=True):
        assert server._trade_page_size() == 30
