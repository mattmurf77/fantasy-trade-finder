"""P1: the server-held first-page store (flag `trade.first_page_store`).

Scope: docs/plans/trade-time-to-suggestion/scope-eng-200ms.md §2, §6.2, §6.8, §7
(on branch plan/trades-200ms-eng-scope); `test_trade_page_store.py` in §3.

Pinned here:
  * the write: only a complete organic job stores pages, with the job's stamps;
    error, timeout, revoked, superseded, ceiling-hit, None stamps, pinned,
    intent, replenish and prepared jobs never do; the kickoff stamps the scope;
  * the supersede guard, two concurrent writers, and a serve during a rebuild;
  * restart survival: an empty job registry still serves the page;
  * every §6.2 branch on /generate `page: 1`, dispositions, last_served_at,
    expiry, and /status cursors into a page-served deck;
  * every page serve goes through S0's serve rules: strict I-1, the two gate
    misses and their knobs (trade_i1_mode, trade_gate_miss_mode), the admin
    gate-miss hook, the C-a log line and the floor kick after the response;
  * ruling 29: "updating" only while a rebuild runs, never on ESPN/MFL;
  * the kill knob first_page_store_enabled (on at any finite value ≥ 1; the
    +1 re-enable) and the paging kill switch; /status at trade_i1_mode 0;
  * the store needs trade.packed_evidence (#370) on; experiment_digest: a page
    serves only under the experiment variants it was built under;
  * a roster change rebuilds lazily (S0: no proactive rebuild from a live
    session's old rosters); session-init (U5);
  * eviction by age and by the byte ceiling; account deletion and export;
  * the measured `stored_bytes` of a realistic deck's stored pages.

Harness: test_i1_serve_filter's `live` (real synchronous worker, stored
`league_members` and `draft_picks`, in-memory SQLite), with the flag on.
"""
import collections
import copy
import itertools
import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, delete, event, insert, select, update

import backend.database as db_module
import backend.feature_flags as ff
import backend.server as server
from backend import accounts, roster_snapshot
from backend.database import draft_picks_table, league_members_table, metadata
from backend.tests.test_i1_serve_filter import (  # noqa: F401  (fixture)
    KEY, LEAGUE, OPP, PK_MINE, PK_OPP, THIRD, TOKEN, UID, live)
from backend.tests.test_trade_fingerprint_reads_unlocked import (  # noqa: F401  (fixture)
    PLATFORM_LEAGUE, PLATFORM_USER, INIT_TOKEN, init_harness)

FLAG = "trade.first_page_store"
EVIDENCE = "trade.packed_evidence"   # #370's flag; the store needs it on
SCOPE = "organic:f=0.50"
HEADERS = {"X-Session-Token": TOKEN}
GOLDEN_CARD = json.loads((Path(__file__).parent / "fixtures" / "bakeoff"
                          / "flag_off_golden.json").read_text())["cards"][0]
REAL_KICKOFF = server._kickoff_trade_job
PAGES = server._trade_pages_stored() * server._trade_page_size()     # 90 at the defaults

# Packages the stored rows allow: UID gives g2 or PK_MINE, OPP gives r2, g1 or PK_OPP.
GIVES = (["g2"], [PK_MINE])
RECEIVES = (["r2"], ["g1"], [PK_OPP])


def page_card(i):
    expires = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    return {"trade_id": f"p1-{i:03d}", "league_id": LEAGUE, "target_user_id": OPP,
            "target_username": "opp", "give": [{"id": pid} for pid in GIVES[i % 2]],
            "receive": [{"id": pid} for pid in RECEIVES[i % 3]], "decision": None,
            "impression_id": f"{i:032x}", "expires_at": expires}


def ids(cards):
    return [c["trade_id"] for c in cards]


@pytest.fixture()
def p1(live, monkeypatch):
    client, engine, sess = live
    monkeypatch.setattr(ff, "_flags_cache", {**ff.flags_dict(), FLAG: True, EVIDENCE: True})
    monkeypatch.setattr(server, "_trade_jobs", {})
    monkeypatch.setattr(server, "_trade_jobs_by_key", {})
    monkeypatch.setattr(server, "_trade_input_epochs", {})
    monkeypatch.setattr(server, "_experiment_digest_memo", collections.OrderedDict())
    monkeypatch.setattr(server, "_deck_withdrawn_cache", {})   # C-b sticky drops, per process
    monkeypatch.setattr(server, "_deck_live_stamped", {})      # live decks' stamped ids (#417 P2-1)
    # F4's awaited ids, per test: a test that stubs the evidence thread out
    # leaves its delivery's ids pending forever (#419 QA: the F4 test failed
    # after the page suites).
    monkeypatch.setattr(server, "_deck_evidence_pending", {})
    # The code default (ruling 19: 50), not a model_config row a local DB
    # seeded earlier (seeds are insert-if-absent).
    monkeypatch.delitem(server._trade_service_mod._cfg, "trade_prefetch_remaining", raising=False)
    # Flag on, organic jobs defer their evidence to delivery (ADR-025 stage 1).
    # Write it inline, never on a thread that could outlive this test's engine.
    monkeypatch.setattr(server, "_start_deck_evidence_thread", lambda *, target, args: target(*args))
    # Production's knob values, whatever a local DB seeded.
    for knob, value in (("first_page_store_enabled", 1.0), ("trade_paged_responses", 1.0),
                        ("trade_i1_mode", 2.0), ("trade_gate_miss_mode", 0.0)):
        monkeypatch.setitem(server._trade_service_mod._cfg, knob, value)
    yield client, engine, sess


@pytest.fixture()
def spawned(monkeypatch):
    """Capture new worker threads instead of running them."""
    calls = []
    monkeypatch.setattr(server, "_start_trade_job_thread", lambda **kw: calls.append(kw))
    return calls


@pytest.fixture()
def statements(p1):
    _, engine, _ = p1
    seen = []
    listener = lambda conn, cursor, statement, *a: seen.append(statement)
    event.listen(engine, "before_cursor_execute", listener)
    yield seen
    event.remove(engine, "before_cursor_execute", listener)


def run_job(**kwargs):
    """A real synchronous organic job (its completion stores the real deck)."""
    args = dict(sess_token=TOKEN, user_id=UID, league_id=LEAGUE, scoring_format="1qb_ppr",
                fairness_threshold=0.5, opponents_total=1, synchronous=True)
    args.update(kwargs)
    return REAL_KICKOFF(**args)


def build_page():
    """Run a job, give it a known 95-card deck, store it again (same built_at,
    so it replaces the row its completion wrote)."""
    job_id = run_job()
    with server._trade_jobs_lock:
        job = server._trade_jobs[job_id]
        assert job["status"] == "complete" and job["page_scope"] == SCOPE
        job["cards"] = [page_card(i) for i in range(95)]
    assert server._store_trade_page(job_id) is True
    return job_id


def stored():
    return db_module.load_trade_page(UID, LEAGUE, "1qb_ppr", SCOPE, evidence=True)


def set_row(engine, **values):
    t = db_module.trade_page_store_table
    with engine.begin() as conn:
        conn.execute(update(t).values(**values))


def generate(client, **body):
    return client.post("/api/trades/generate", headers=HEADERS,
                       json={"league_id": LEAGUE, "fairness_threshold": 0.5, **body})


def status(client, job_id, cursor):
    return client.get(f"/api/trades/status?job_id={job_id}&cursor={cursor}", headers=HEADERS)


def page_queries(seen):
    return [s for s in seen if "trade_page_store" in s]


# ── The write ───────────────────────────────────────────────────────────────

def test_a_complete_organic_job_stores_its_first_pages_with_its_stamps(p1):
    job_id = build_page()
    job = server._trade_jobs[job_id]
    row = stored()
    assert row["deck_job_id"] == job_id and row["state"] == "ready"
    assert (row["roster_fp"], row["values_snapshot_id"]) == (job["roster_fp"], job["values_snapshot_id"])
    assert row["roster_fp"].startswith("rfp1:") and row["values_snapshot_id"].startswith("vsn1:")
    assert row["config_signature"] == job["request_signature"]
    assert row["engine_version"] == server._trade_page_engine_version(
        server._trade_engine_name(False), job.get("safety_policy", []), job["presentation_capture"])
    assert row["card_count"] == PAGES == 90
    assert row["pages_blob"] == {"v": 1, "opponents_total": job["opponents_total"],
                                 "cards": job["cards"][:PAGES]}
    # ADR-025 stage 1: the deferred deck's unwritten evidence rides along (the
    # replaced cards are not the deck's, so only its candidate set is left).
    evidence = row["evidence_blob"]
    assert evidence["deck_job_id"] == job_id and evidence["rows"] == []
    assert row["stored_bytes"] == (len(db_module.CompressedJSON.encode(row["pages_blob"]))
                                   + len(db_module.CompressedJSON.encode(evidence)))
    assert row["last_served_at"] is None
    assert row["built_at"] <= db_module.page_store_iso(time.time())
    assert row["expires_at"] == min(db_module.page_store_iso(
        datetime.fromisoformat(c["expires_at"]).timestamp()) for c in job["cards"][:PAGES])


def test_the_worker_completion_writes_the_page(p1, statements):
    """_run_leased_job stores the page once _run_trade_job completes the job."""
    job_id = run_job()
    assert stored()["deck_job_id"] == job_id
    assert any(s.startswith("INSERT INTO trade_page_store") for s in statements)


REFUSALS = {
    "error": lambda job: job.update(status="error", error="boom"),
    "timeout": lambda job: job.update(status="error", error="timeout"),
    "running": lambda job: job.update(status="running"),
    "revoked": lambda job: server._revoke_trade_job_locked(job),
    "inputs_changed": lambda job: setattr(job["input_epochs"][0], "revoked", True),
    "superseded": lambda job: job.update(superseded=True),
    "ceiling_flat": lambda job: job.update(safety_ceiling_hit=True),
    "ceiling_value_core": lambda job: job.update(value_core={"safety_ceiling_hit": True}),
    "ceiling_diag": lambda job: job.update(value_core={"diag": {"safety_ceiling_hit": True}}),
    "roster_fp_none": lambda job: job.update(roster_fp=None),
    "values_snapshot_none": lambda job: job.update(values_snapshot_id=None),
    "signature_none": lambda job: job.update(request_signature=None),
    "experiment_digest_none": lambda job: job.pop("experiment_digest"),   # its read failed
    "pinned": lambda job: job.update(is_pinned=True),
    "intent": lambda job: job.update(trade_intent="consolidate"),
    "replenish": lambda job: job.update(source="replenish"),
    "prepared": lambda job: job.update(prepared_inventory_id="inv-1"),
    "presentation_exempt": lambda job: job.update(presentation_exempt=True),
    "not_organic": lambda job: job.pop("page_scope"),
}


@pytest.mark.parametrize("reason", sorted(REFUSALS))
def test_the_store_refuses_every_ineligible_job(p1, reason):
    job_id = run_job()
    _, engine, _ = p1
    with engine.begin() as conn:
        conn.execute(delete(db_module.trade_page_store_table))
    with server._trade_jobs_lock:
        job = server._trade_jobs[job_id]
        job["cards"] = [page_card(i) for i in range(5)]
        REFUSALS[reason](job)
    assert server._store_trade_page(job_id) is False
    assert stored() is None


def test_the_store_refuses_with_the_flag_off(p1, monkeypatch):
    job_id = build_page()
    monkeypatch.setattr(ff, "_flags_cache", {**ff.flags_dict(), FLAG: False})
    with server._trade_jobs_lock:
        server._trade_jobs[job_id]["cards"] = [page_card(i) for i in range(3)]
    assert server._store_trade_page(job_id) is False
    assert stored()["card_count"] == PAGES


@pytest.mark.parametrize("kwargs, scope", [
    ({}, SCOPE),
    ({"fairness_threshold": 0.75}, "organic:f=0.75"),
    ({"force_fresh": True}, SCOPE),                      # the newest organic deck
    ({"pinned_give": ["g2"]}, None),
    ({"pinned_receive": ["r2"]}, None),
    ({"opponent_user_id": OPP}, None),
    ({"trade_intent": "tier_up"}, None),
    ({"presentation_exempt": True}, None),
    ({"source": "replenish"}, None),
])
def test_the_kickoff_stamps_only_organic_jobs(p1, spawned, kwargs, scope):
    job_id = run_job(synchronous=False, **kwargs)
    assert server._trade_jobs[job_id].get("page_scope") == scope


def test_the_kickoff_stamps_nothing_with_the_flag_off(p1, spawned, monkeypatch):
    monkeypatch.setattr(ff, "_flags_cache", {**ff.flags_dict(), FLAG: False})
    assert "page_scope" not in server._trade_jobs[run_job(synchronous=False)]


def test_value_core_pages_carry_the_core_engine_version():
    from backend.value_core.types import ENGINE_VERSION
    assert server._trade_engine_name(True) == "value_core:" + ENGINE_VERSION
    assert server._trade_engine_name(False) in ("v1", "v2", "v3")


# ── Supersede guard and concurrency ─────────────────────────────────────────

def _row(built_at, job_id, **extra):
    blob = db_module.CompressedJSON.encode({"v": 1, "opponents_total": 1, "cards": [job_id]})
    row = dict(user_id=UID, league_id=LEAGUE, scoring_format="1qb_ppr", request_scope=SCOPE,
               roster_fp="rfp1:x", values_snapshot_id="vsn1:x", engine_version="v3+x",
               config_signature="c", experiment_digest="e", deck_job_id=job_id,
               built_at=db_module.page_store_iso(built_at),
               expires_at=db_module.page_store_iso(built_at + 86400), card_count=1,
               pages_blob=blob, evidence_blob=None, stored_bytes=len(blob), state="ready")
    row.update(extra)
    return row


@pytest.fixture()
def file_db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'p1.db'}")
    metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)
    yield engine
    engine.dispose()


def test_an_older_build_never_replaces_a_newer_row(file_db):
    assert db_module.save_trade_page(_row(200, "new"))
    assert not db_module.save_trade_page(_row(100, "old"))
    assert stored()["deck_job_id"] == "new"
    assert db_module.save_trade_page(_row(200, "same-time"))
    assert db_module.save_trade_page(_row(300, "newer"))
    assert stored()["deck_job_id"] == "newer"


def test_a_rebuild_keeps_last_served_at(file_db):
    db_module.save_trade_page(_row(100, "a"))
    db_module.touch_trade_page(stored()["id"], "2026-10-20T00:00:00.000000+00:00")
    db_module.save_trade_page(_row(200, "b"))
    row = stored()
    assert (row["deck_job_id"], row["last_served_at"]) == ("b", "2026-10-20T00:00:00.000000+00:00")


def test_two_concurrent_writers_leave_one_consistent_row(file_db):
    for attempt in range(10):
        barrier = threading.Barrier(2)
        errors = []

        def write(built_at, job_id):
            try:
                barrier.wait()
                db_module.save_trade_page(_row(built_at, job_id))
            except Exception as err:   # pragma: no cover - surfaced below
                errors.append(err)

        threads = [threading.Thread(target=write, args=(1000 + attempt * 10 + n, f"w{attempt}-{n}"))
                   for n in (1, 2)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        assert not errors
        with file_db.connect() as conn:
            rows = conn.execute(select(db_module.trade_page_store_table)).mappings().all()
        assert len(rows) == 1
        row = rows[0]
        assert row["deck_job_id"] == f"w{attempt}-2"                       # the newer build
        assert row["pages_blob"]["cards"] == [row["deck_job_id"]]          # its own pages
        assert row["stored_bytes"] == len(db_module.CompressedJSON.encode(row["pages_blob"]))


def test_a_read_during_a_rebuild_sees_the_old_row_until_it_commits(file_db):
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    db_module.save_trade_page(_row(100, "old"))
    t = db_module.trade_page_store_table
    new = _row(200, "new")
    stmt = sqlite_insert(t).values(**new)
    stmt = stmt.on_conflict_do_update(
        index_elements=[t.c.user_id, t.c.league_id, t.c.scoring_format, t.c.request_scope],
        set_={name: stmt.excluded[name] for name in db_module._PAGE_STORE_REPLACED},
        where=t.c.built_at <= stmt.excluded.built_at)
    with file_db.connect() as writer:
        tx = writer.begin()
        writer.execute(stmt)
        assert stored()["deck_job_id"] == "old"
        tx.commit()
    assert stored()["deck_job_id"] == "new"


def test_a_serve_during_a_running_rebuild_returns_the_stored_page(p1, spawned):
    client, _, _ = p1
    build_page()
    server._trade_jobs.clear()
    server._trade_jobs_by_key.clear()
    first = generate(client, page=1).get_json()            # kicks the rebuild
    assert first["serve_source"] == "page" and len(spawned) == 1
    rebuild_id = server._trade_jobs_by_key[KEY]
    assert server._trade_jobs[rebuild_id]["status"] == "running"
    second = generate(client, page=1).get_json()
    assert second["serve_source"] == "page" and second["cards"] == first["cards"]
    assert len(spawned) == 1                               # the running rebuild is joined


# ── Restart survival and §6.2 ───────────────────────────────────────────────

def test_all_equal_serves_page_one_inline(p1, spawned):
    client, _, _ = p1
    job_id = build_page()
    response = generate(client, page=1, search_id="s-1")
    assert response.status_code == 200
    body = response.get_json()
    # P2 adds each card's trade_hash at serve (test_trade_pages_p2); the rest is the stored card.
    assert [{k: v for k, v in c.items() if k != "trade_hash"}
            for c in body["cards"]] == stored()["pages_blob"]["cards"][:30]
    assert ids(body["cards"]) == [f"p1-{i:03d}" for i in range(30)]
    assert {k: body[k] for k in ("job_id", "status", "error", "cursor", "total_ready", "replace",
                                 "serve_source", "freshness_state", "search_id",
                                 "prefetch_remaining")} == {
        "job_id": job_id, "status": "complete", "error": None, "cursor": 30, "total_ready": 90,
        "replace": False, "serve_source": "page", "freshness_state": "fresh", "search_id": "s-1",
        "prefetch_remaining": 50}
    assert not spawned                       # a fresh job backs the page: no rebuild
    assert stored()["last_served_at"] is not None


def test_restart_survival_serves_the_page_and_refreshes(p1, spawned):
    client, _, _ = p1
    job_id = build_page()
    server._trade_jobs.clear()               # the daily worker kill
    server._trade_jobs_by_key.clear()
    body = generate(client, page=1).get_json()
    assert body["serve_source"] == "page" and body["job_id"] == job_id
    assert ids(body["cards"]) == [f"p1-{i:03d}" for i in range(30)]
    assert body["freshness_state"] == "fresh"
    assert len(spawned) == 1                 # nothing in this process backs it: rebuild


def test_a_roster_move_serves_the_filtered_page_updating_and_rebuilds(p1, spawned):
    client, engine, _ = p1
    build_page()
    with engine.begin() as conn:             # g2 leaves the viewer's roster
        conn.execute(update(league_members_table).where(league_members_table.c.user_id == UID)
                     .values(roster_data=json.dumps([])))
        conn.execute(update(league_members_table).where(league_members_table.c.user_id == THIRD)
                     .values(roster_data=json.dumps(["r1", "g2"])))
    body = generate(client, page=1).get_json()
    expected = [c for c in (page_card(i) for i in range(30)) if c["give"][0]["id"] != "g2"]
    assert ids(body["cards"]) == ids(expected) and len(expected) == 15
    assert body["cursor"] == 30                       # the raw index, not the filtered count
    assert (body["serve_source"], body["freshness_state"]) == ("page", "updating")
    assert len(spawned) == 1


def test_a_values_move_serves_the_page_updating_and_rebuilds(p1, spawned):
    client, engine, _ = p1
    build_page()
    with engine.begin() as conn:             # a pick reprices: vsn1 moves, rfp1 does not
        conn.execute(update(draft_picks_table).where(draft_picks_table.c.pick_id == PK_MINE)
                     .values(pool_value=99.0))
    body = generate(client, page=1).get_json()
    assert ids(body["cards"]) == [f"p1-{i:03d}" for i in range(30)]
    assert (body["serve_source"], body["freshness_state"]) == ("page", "updating")
    assert len(spawned) == 1


@pytest.mark.parametrize("column", ["engine_version", "config_signature"])
def test_an_engine_or_config_move_blocks_the_page(p1, spawned, column):
    client, engine, _ = p1
    build_page()
    set_row(engine, **{column: "moved"})
    server._trade_jobs.clear()
    server._trade_jobs_by_key.clear()
    body = generate(client, page=1).get_json()
    assert "serve_source" not in body and body["status"] == "running" and body["cards"] == []
    assert len(spawned) == 1                 # today's path: a fresh job
    assert stored()["last_served_at"] is None


def test_expired_stored_cards_are_never_served(p1, spawned):
    client, engine, _ = p1
    build_page()
    set_row(engine, expires_at=db_module.page_store_iso(time.time() - 1))
    body = generate(client, page=1).get_json()
    assert "serve_source" not in body        # today's path: the in-process fresh job


def test_a_failed_fingerprint_read_falls_through(p1, spawned):
    """A failed read can't prove a page fresh (S0's A2): today's path."""
    client, _, _ = p1
    build_page()
    with patch.object(roster_snapshot, "values_snapshot_id", MagicMock(side_effect=RuntimeError("db"))):
        body = generate(client, page=1).get_json()
    assert "serve_source" not in body


@pytest.mark.parametrize("gate_mode", [0.0, 1.0])
def test_a_failed_s0_check_on_the_page_follows_trade_gate_miss_mode(p1, spawned, monkeypatch,
                                                                    gate_mode):
    """0 (until 1.22.0): held, the cards serve unchecked. 1: roster_check_unavailable.
    (Knobs are part of the config signature, so set before the page is built.)"""
    client, _, _ = p1
    monkeypatch.setitem(server._trade_service_mod._cfg, "trade_gate_miss_mode", gate_mode)
    build_page()
    with patch.object(server, "_roster_serve_check", MagicMock(side_effect=RuntimeError("db"))):
        body = generate(client, page=1).get_json()
    assert body["serve_source"] == "page"
    if gate_mode:
        assert (body["status"], body["error"], body["cards"]) == ("error", "roster_check_unavailable", [])
        assert (body["cursor"], body["total_ready"]) == (0, 0)
    else:
        assert body["status"] == "complete" and len(body["cards"]) == 30


@pytest.mark.parametrize("gate_mode", [0.0, 1.0])
def test_a_league_without_stored_rosters_follows_trade_gate_miss_mode(p1, spawned, monkeypatch,
                                                                     gate_mode):
    """Strict `missing` (ruling 30) only at gate mode 1; held at 0, as S0's job views."""
    client, engine, _ = p1
    monkeypatch.setitem(server._trade_service_mod._cfg, "trade_gate_miss_mode", gate_mode)
    build_page()
    with engine.begin() as conn:
        conn.execute(delete(league_members_table))
    body = generate(client, page=1).get_json()
    if gate_mode:
        assert (body["status"], body["error"], body["cards"]) == ("error", "roster_check_unavailable", [])
        assert not spawned                   # a gate miss kicks no deck rebuild
    else:
        assert body["status"] == "complete" and len(body["cards"]) == 30


def test_dispositions_apply_to_the_served_page(p1, spawned):
    client, engine, _ = p1
    build_page()
    with engine.begin() as conn:             # an exact pass on g2 -> r2
        conn.execute(insert(db_module.trade_decisions_table).values(
            user_id=UID, league_id=LEAGUE, trade_id="elsewhere",
            give_player_ids=json.dumps(["g2"]), receive_player_ids=json.dumps(["r2"]),
            decision="pass", created_at=datetime.now(timezone.utc).isoformat()))
    body = generate(client, page=1).get_json()
    passed = {c["trade_id"] for c in (page_card(i) for i in range(30))
              if c["give"][0]["id"] == "g2" and c["receive"][0]["id"] == "r2"}
    assert passed and not passed & set(ids(body["cards"]))
    assert len(body["cards"]) == 30 - len(passed)


@pytest.mark.parametrize("body", [
    {"pinned_give_players": ["g2"]}, {"pinned_receive_players": ["r2"]},
    {"opponent_user_id": OPP}, {"trade_intent": "tier_up"}, {"force": True},
    {"refresh_fatigue": True}, {},          # the last: unpaged
])
def test_other_requests_never_read_the_store(p1, spawned, statements, body):
    client, _, _ = p1
    build_page()
    statements.clear()
    paged = {"page": 1} if body else {}
    response = generate(client, **body, **paged)
    assert response.status_code == 200
    assert "serve_source" not in response.get_json()
    assert not [s for s in page_queries(statements) if s.startswith("SELECT")]


def test_the_serve_path_reads(p1, spawned, statements, monkeypatch):
    """The page serve's own statements: one page read; one S0 roster snapshot
    (league_members, draft_picks, leagues, league_roster_state) shared by the
    fingerprint compare and S0's serve check, plus the vsn1 pick read; the
    disposition read; one last_served_at write. Everything else is
    /generate's existing preamble (session touch, preference/outlook reads).
    The delivery's evidence write runs on its own thread (not run here).
    """
    client, _, _ = p1
    monkeypatch.setattr(server, "_start_deck_evidence_thread", lambda **kw: None)
    build_page()
    statements.clear()
    assert generate(client, page=1).get_json()["serve_source"] == "page"
    selects = [" ".join(s.split()) for s in statements if s.startswith("SELECT")]
    assert sum("FROM trade_page_store" in s for s in selects) == 1
    assert sum(s.startswith("UPDATE trade_page_store") for s in statements) == 1
    assert sum("FROM league_members" in s for s in selects) == 1   # the check reuses it
    assert sum("FROM league_roster_state" in s for s in selects) == 1
    assert sum("FROM trade_decisions" in s for s in selects) == 1


# ── The page serve goes through S0's serve rules (pre-merge pass) ───────────

OLD = "2026-01-01T00:00:00.000000+00:00"


@pytest.fixture()
def floor_kicks(monkeypatch):
    """S0's P41 floor kick, recorded instead of run."""
    calls = []
    monkeypatch.setattr(server._roster_refresh, "maybe_refresh_async",
                        lambda league_id, max_age_s: calls.append((league_id, max_age_s)) or False)
    return calls


def _sleeper_roster_failed_past_bound(engine):
    """league_roster_state: the last refresh failed, long past trade_roster_bound_s."""
    with engine.begin() as conn:
        conn.execute(insert(db_module.league_roster_state_table).values(
            league_id=LEAGUE, status="stale", refreshed_at=OLD, last_error_code="timeout",
            updated_at=OLD))


@pytest.mark.parametrize("gate_mode", [0.0, 1.0])
def test_a_past_bound_failed_roster_withholds_the_page_like_s0(p1, spawned, monkeypatch,
                                                               floor_kicks, gate_mode):
    """§3b: at gate mode 1 the page gets S0's withhold shape (the client keeps
    polling); at 0 it's held and the I-1-filtered cards serve. Either way the
    floor kick runs once, after the response is built."""
    client, engine, _ = p1
    monkeypatch.setitem(server._trade_service_mod._cfg, "trade_gate_miss_mode", gate_mode)
    job_id = build_page()
    _sleeper_roster_failed_past_bound(engine)
    body = generate(client, page=1).get_json()
    assert body["serve_source"] == "page" and body["job_id"] == job_id
    if gate_mode:
        assert (body["status"], body["wait_reason"], body["cards"]) == ("running", "roster_check", [])
        assert (body["cursor"], body["total_ready"]) == (0, 0)
        assert stored()["last_served_at"] is None
    else:
        assert body["status"] == "complete" and "wait_reason" not in body
        assert len(body["cards"]) == 30
    assert floor_kicks == [(LEAGUE, 300.0)]


def test_the_admin_gate_miss_hook_applies_to_page_serves(p1, spawned, monkeypatch, caplog):
    client, _, _ = p1
    job_id = build_page()
    caplog.set_level(logging.INFO, logger="trade_finder")
    monkeypatch.setitem(server._gate_miss_tests, LEAGUE, ("withhold", time.monotonic() + 60))
    body = generate(client, page=1).get_json()
    assert (body["status"], body["wait_reason"], body["cards"]) == ("running", "roster_check", [])
    assert any(r.getMessage() == f"[i1] gate-miss test applied league={LEAGUE} kind=withhold "
               f"job={job_id}" for r in caplog.records)


def _s0_lines(caplog):
    return [r for r in caplog.records if r.getMessage().startswith("[i1] serve ")]


def test_each_page_serve_logs_one_s0_line(p1, spawned, caplog):
    """C-a: one `[i1] serve` line per serve, on the page path too, with
    `job=` the page's deck job."""
    client, _, _ = p1
    job_id = build_page()
    caplog.set_level(logging.INFO, logger="trade_finder")
    generate(client, page=1)
    lines = [r.getMessage() for r in _s0_lines(caplog)]
    assert len(lines) == 1 and f"league={LEAGUE} job={job_id} mode=strict" in lines[0]
    assert "outcome=served " in lines[0] and "cards=30 kept=30" in lines[0]


def test_a_c_e_league_page_serve_lets_every_card_through(p1, spawned, floor_kicks, caplog):
    """S0's C-e: the last session write failed (Sleeper `stale` + `write_failed`),
    so the stored rows may be outdated. The page serve drops nothing, even for
    an asset the stored rows say moved, and logs `unchecked_c_e` at warning."""
    client, engine, _ = p1
    job_id = build_page()
    with engine.begin() as conn:
        conn.execute(insert(db_module.league_roster_state_table).values(
            league_id=LEAGUE, status="stale", refreshed_at=OLD, last_error_code="write_failed",
            updated_at=OLD))
        conn.execute(update(league_members_table).where(league_members_table.c.user_id == UID)
                     .values(roster_data=json.dumps([])))     # strict would drop every g2 card
    caplog.set_level(logging.INFO, logger="trade_finder")
    body = generate(client, page=1).get_json()
    assert body["serve_source"] == "page" and body["status"] == "complete"
    assert ids(body["cards"]) == [f"p1-{i:03d}" for i in range(30)]
    (line,) = _s0_lines(caplog)
    assert line.levelno == logging.WARNING
    assert f"job={job_id}" in line.getMessage() and "outcome=unchecked_c_e" in line.getMessage()


def test_lenient_mode_serves_every_page_card(p1, spawned, monkeypatch, caplog):
    client, engine, _ = p1
    monkeypatch.setitem(server._trade_service_mod._cfg, "trade_i1_mode", 1.0)
    build_page()
    with engine.begin() as conn:             # g2 leaves the viewer's roster
        conn.execute(update(league_members_table).where(league_members_table.c.user_id == UID)
                     .values(roster_data=json.dumps([])))
    caplog.set_level(logging.INFO, logger="trade_finder")
    body = generate(client, page=1).get_json()
    assert body["serve_source"] == "page" and len(body["cards"]) == 30
    (line,) = _s0_lines(caplog)
    assert "mode=lenient" in line.getMessage() and "outcome=served_lenient" in line.getMessage()


def test_mode_0_never_reads_the_store(p1, spawned, statements, monkeypatch):
    """trade_i1_mode 0 is the pre-S0 path: without its reads the stamps can't be compared."""
    client, _, _ = p1
    build_page()
    monkeypatch.setitem(server._trade_service_mod._cfg, "trade_i1_mode", 0.0)
    statements.clear()
    body = generate(client, page=1).get_json()
    assert "serve_source" not in body
    assert not [s for s in page_queries(statements) if s.startswith("SELECT")]


# ── Ruling 29: "updating" only while a rebuild runs, never on ESPN/MFL ───────

def test_a_stale_page_with_no_rebuild_running_is_not_updating(p1, spawned, monkeypatch):
    client, _, _ = p1
    build_page()
    _vote(client)
    monkeypatch.setattr(server, "_kickoff_trade_job", lambda **kw: "no-such-job")
    body = generate(client, page=1).get_json()
    assert (body["serve_source"], body["freshness_state"]) == ("page", "fresh")


def test_a_linked_league_never_shows_updating(p1, spawned):
    client, engine, _ = p1
    with engine.begin() as conn:
        conn.execute(insert(db_module.leagues_table).values(
            sleeper_league_id=LEAGUE, user_id=UID, name="ESPN league", platform="espn"))
    build_page()
    _vote(client)
    body = generate(client, page=1).get_json()
    assert body["serve_source"] == "page" and len(spawned) == 1     # the rebuild runs
    assert body["freshness_state"] == "fresh"


# ── Kill switches ───────────────────────────────────────────────────────────

def test_the_kill_knob_stops_every_store_read_write_and_serve(p1, spawned, statements, monkeypatch):
    """first_page_store_enabled 0, with the flag on: no store read, write, serve or mark."""
    client, _, _ = p1
    job_id = build_page()
    monkeypatch.setitem(server._trade_service_mod._cfg, "first_page_store_enabled", 0.0)
    assert not server._trade_page_store_enabled()
    statements.clear()
    body = generate(client, page=1).get_json()
    assert not {"serve_source", "freshness_state", "prefetch_remaining"} & set(body)
    assert status(client, job_id, 30).get_json().get("serve_source") is None
    run_job(force_fresh=True)                          # a completion
    server._invalidate_trade_jobs(user_id=UID)         # an input change
    server._evict_trade_page_store()
    assert page_queries(statements) == []


def test_the_paging_kill_switch_keeps_the_store_out(p1, spawned, statements, monkeypatch):
    """trade_paged_responses 0: `page` and `cursor` are ignored, so no store serve."""
    client, _, _ = p1
    job_id = build_page()
    monkeypatch.setitem(server._trade_service_mod._cfg, "trade_paged_responses", 0.0)
    statements.clear()
    body = generate(client, page=1).get_json()
    assert not {"serve_source", "cursor"} & set(body)
    body = status(client, job_id, 30).get_json()
    assert not {"serve_source", "cursor"} & set(body)
    assert not [s for s in page_queries(statements) if s.startswith("SELECT")]


@pytest.mark.parametrize("value, on", [
    (1.0, True), (2.0, True), (7.0, True), (0.0, False), (0.5, False), (-1.0, False),
    (float("nan"), False), (float("inf"), False), ("not a number", False), (None, False),
])
def test_the_kill_knob_is_on_at_any_finite_value_of_at_least_1(p1, monkeypatch, value, on):
    monkeypatch.setitem(server._trade_service_mod._cfg, "first_page_store_enabled", value)
    assert server._trade_page_store_enabled() is on


def test_the_kill_knob_missing_reads_as_on(p1, monkeypatch):
    monkeypatch.delitem(server._trade_service_mod._cfg, "first_page_store_enabled")
    assert server._trade_page_store_enabled() is True


def test_re_enabling_with_the_knob_plus_one_makes_old_pages_fall_through(p1, spawned, monkeypatch):
    """1 → 0 → 2: while off, input changes weren't marked; the bumped knob is in
    every config_signature, so the page stored at 1 never serves again."""
    client, _, _ = p1
    build_page()
    monkeypatch.setitem(server._trade_service_mod._cfg, "first_page_store_enabled", 0.0)
    _vote(client)                                       # missed: the store is off
    assert stored()["state"] == "ready"
    monkeypatch.setitem(server._trade_service_mod._cfg, "first_page_store_enabled", 2.0)
    body = generate(client, page=1).get_json()
    assert "serve_source" not in body                   # today's path: a new job
    assert len(spawned) == 1


def test_status_at_i1_mode_0_takes_the_job_path(p1, spawned, statements, monkeypatch):
    """No stored-page serve at trade_i1_mode 0, on /status as on /generate."""
    client, _, _ = p1
    job_id = build_page()
    monkeypatch.setitem(server._trade_service_mod._cfg, "trade_i1_mode", 0.0)
    statements.clear()
    body = status(client, job_id, 30).get_json()
    assert "serve_source" not in body and body["job_id"] == job_id    # the in-process job
    server._trade_jobs.clear()
    server._trade_jobs_by_key.clear()
    assert status(client, job_id, 30).status_code == 404               # no job, no page
    assert not [s for s in page_queries(statements) if s.startswith("SELECT")]


# ── trade.packed_evidence gates the store (head-eng, flag order) ────────────

@pytest.mark.parametrize("evidence", [None, False])
def test_the_store_needs_packed_evidence_on(p1, spawned, statements, monkeypatch, evidence):
    """Without #370's flag the store can't take effect, whatever
    trade.first_page_store says: P1 never registers the key, so it reads False."""
    flags = {**ff.flags_dict(), FLAG: True}
    flags.pop(EVIDENCE, None)
    if evidence is not None:
        flags[EVIDENCE] = evidence
    monkeypatch.setattr(ff, "_flags_cache", flags)
    assert server._trade_page_store_enabled() is False
    client, _, _ = p1
    statements.clear()
    run_job()                                          # a complete organic job
    body = generate(client, page=1).get_json()
    assert "serve_source" not in body
    assert page_queries(statements) == []             # no store read or write at all
    assert stored() is None


# ── experiment_digest (head-eng, the experiment gap) ────────────────────────

RUNNING_AGGRESSION = {"key": "trade.aggression", "layer": "trade", "version": 3,
                      "variants": [{"name": "light"}, {"name": "generous"}]}


_GENERATIONS = itertools.count(1)


def _assign(monkeypatch, variant, overlay=None, version=3, generation=None):
    """The user's trade.aggression assignment, as experiments reports it, under
    a new experiments cache generation unless one is given. Returns a list
    that records every variant_overlay call (a spy)."""
    from backend import experiments
    calls = []
    generation = next(_GENERATIONS) if generation is None else generation

    def variant_overlay(unit_id, key, header_attrs=None):
        calls.append((unit_id, key))
        return (variant, overlay or {}) if variant else (None, {})

    monkeypatch.setattr(experiments, "variant_overlay", variant_overlay)
    monkeypatch.setattr(experiments, "_load_cache",
                        lambda: {"at": generation,
                                 "running": [dict(RUNNING_AGGRESSION, version=version)]})
    return calls


@pytest.mark.parametrize("built, now, served", [
    (("light", {"aggression_weight": 0.2}), ("light", {"aggression_weight": 0.2}), True),
    ((None, None), (None, None), True),                     # a fallback user round-trips
    (("light", None), ("generous", None), False),           # moved to another variant
    (("light", {"aggression_weight": 0.2}), ("light", {"aggression_weight": 0.4}), False),
    (("light", None), (None, None), False),                 # enrolled -> fallback
    ((None, None), ("light", None), False),                 # fallback -> enrolled
])
def test_a_page_serves_only_under_the_variant_it_was_built_under(p1, spawned, monkeypatch, caplog,
                                                                built, now, served):
    client, _, _ = p1
    _assign(monkeypatch, *built)
    build_page()
    _assign(monkeypatch, *now)
    caplog.set_level(logging.INFO, logger="trade_finder")
    body = generate(client, page=1).get_json()
    assert (body.get("serve_source") == "page") is served
    blocked = [r for r in caplog.records if "blocked (experiment variant moved)" in r.getMessage()]
    assert bool(blocked) is not served


def test_a_new_experiment_version_mismatches(p1, spawned, monkeypatch):
    client, _, _ = p1
    _assign(monkeypatch, "light", version=3)
    build_page()
    _assign(monkeypatch, "light", version=4)
    assert "serve_source" not in generate(client, page=1).get_json()


def test_the_page_carries_the_digest_read_at_job_start(p1, spawned, monkeypatch):
    """Release-lead #368 QA P3 (c): the variant moves while the engine runs.
    The page stores the start-time digest, so the serve after the move falls
    through instead of serving a light-built deck as generous."""
    client, _, _ = p1
    _assign(monkeypatch, "light")
    at_start = server._trade_experiment_digest(UID)
    real_run = server._run_trade_job

    def run_then_move(*args, **kwargs):
        real_run(*args, **kwargs)
        _assign(monkeypatch, "generous")              # after the engine, before the store

    monkeypatch.setattr(server, "_run_trade_job", run_then_move)
    job_id = run_job()
    moved = server._trade_experiment_digest(UID)
    assert moved != at_start
    assert server._trade_jobs[job_id]["experiment_digest"] == at_start
    assert stored()["deck_job_id"] == job_id and stored()["experiment_digest"] == at_start
    assert "serve_source" not in generate(client, page=1).get_json()


def test_the_digest_is_read_on_the_worker_not_the_request(p1, spawned, monkeypatch):
    """Read once, at job start on the worker; never on the request thread, and
    the store reuses the job's value instead of reading it again."""
    client, _, _ = p1
    _assign(monkeypatch, "light")
    expected = server._trade_experiment_digest(UID)
    reads = []
    real = server._trade_experiment_digest
    monkeypatch.setattr(server, "_trade_experiment_digest", lambda uid: reads.append(uid) or real(uid))
    generate(client)
    (start,) = spawned
    job_id = start["args"][0]
    assert reads == [] and "experiment_digest" not in server._trade_jobs[job_id]
    start["target"](*start["args"], **start["kwargs"])          # the worker thread's body
    assert reads == [UID]
    assert server._trade_jobs[job_id]["experiment_digest"] == expected
    assert stored()["deck_job_id"] == job_id and stored()["experiment_digest"] == expected


def test_the_digest_marks_a_fallback_user(p1, monkeypatch):
    _assign(monkeypatch, None)
    fallback = server._trade_experiment_digest(UID)
    _assign(monkeypatch, "fair")
    enrolled = server._trade_experiment_digest(UID)
    assert fallback != enrolled and len(fallback) == 16
    assert server._DECK_EXPERIMENT_LAYERS == ("trade.aggression",)


# ── The digest memo: no DB work per serve inside a cache generation ─────────

def test_two_serves_in_one_generation_evaluate_once(p1, spawned, monkeypatch):
    client, _, _ = p1
    calls = _assign(monkeypatch, "light", generation=7)
    build_page()
    server._experiment_digest_memo.clear()       # e.g. another process built the page
    calls.clear()
    for _ in range(2):
        assert generate(client, page=1).get_json()["serve_source"] == "page"
    assert len(calls) == 1


def test_a_generation_change_recomputes(p1, monkeypatch):
    calls = _assign(monkeypatch, "light", generation=7)
    first = server._trade_experiment_digest(UID)
    assert server._trade_experiment_digest(UID) == first and len(calls) == 1
    calls = _assign(monkeypatch, "light", generation=8)
    assert server._trade_experiment_digest(UID) == first and len(calls) == 1


def test_a_variant_change_after_a_refresh_still_falls_through(p1, spawned, monkeypatch):
    client, _, _ = p1
    _assign(monkeypatch, "light", generation=7)
    build_page()
    assert generate(client, page=1).get_json()["serve_source"] == "page"
    _assign(monkeypatch, "generous", generation=8)
    assert "serve_source" not in generate(client, page=1).get_json()


def test_the_memo_is_bounded(p1, monkeypatch):
    calls = _assign(monkeypatch, "light", generation=7)
    monkeypatch.setattr(server, "_EXPERIMENT_DIGEST_MEMO_MAX", 3)
    for n in range(5):
        server._trade_experiment_digest(f"user-{n}")
    assert list(server._experiment_digest_memo) == ["user-2", "user-3", "user-4"]
    server._trade_experiment_digest("user-0")    # evicted: evaluated again
    assert len(calls) == 6 and len(server._experiment_digest_memo) == 3


def test_with_the_engine_off_no_experiment_state_is_read(p1, monkeypatch):
    from backend import experiments
    monkeypatch.setattr(ff, "_flags_cache", {**ff.flags_dict(), "experiments.engine": False})
    monkeypatch.setattr(experiments, "_load_cache",
                        lambda: pytest.fail("the experiments cache was read with the engine off"))
    digest = server._trade_experiment_digest(UID)
    assert digest == server._trade_experiment_digest(UID)


# ── /status cursors into a page-served deck ─────────────────────────────────

def test_status_cursors_walk_the_stored_pages(p1, spawned):
    client, _, _ = p1
    job_id = build_page()
    first = generate(client, page=1).get_json()
    second = status(client, job_id, first["cursor"]).get_json()
    assert ids(second["cards"]) == [f"p1-{i:03d}" for i in range(30, 60)]
    assert (second["cursor"], second["total_ready"], second["serve_source"]) == (60, 90, "page")
    third = status(client, job_id, 60).get_json()
    assert ids(third["cards"]) == [f"p1-{i:03d}" for i in range(60, 90)]
    # Past the stored pages: the live job (E2's view of the full deck).
    past = status(client, job_id, 90).get_json()
    assert "serve_source" not in past and past["prefetch_remaining"] == 50
    server._trade_jobs.clear()
    server._trade_jobs_by_key.clear()
    gone = status(client, job_id, 90)
    assert gone.status_code == 200
    assert gone.get_json() == {
        "job_id": job_id, "status": "complete", "opponents_done": 1, "opponents_total": 1,
        "cards": [], "error": None, "cursor": 90, "total_ready": 90, "replace": False,
        "serve_source": "page", "freshness_state": "fresh", "prefetch_remaining": 50}


def test_status_page_goes_through_s0_after_a_roster_move(p1, spawned, monkeypatch):
    client, engine, _ = p1
    job_id = build_page()
    server._trade_jobs.clear()
    server._trade_jobs_by_key.clear()
    with engine.begin() as conn:
        conn.execute(update(league_members_table).where(league_members_table.c.user_id == UID)
                     .values(roster_data=json.dumps([])))
    body = status(client, job_id, 30).get_json()
    assert all(c["give"][0]["id"] != "g2" for c in body["cards"]) and body["cards"]
    assert body["freshness_state"] == "fresh"        # stale, but no rebuild runs (ruling 29)
    rebuild = run_job(synchronous=False)             # now one runs
    assert server._trade_jobs[rebuild]["status"] == "running"
    assert status(client, job_id, 30).get_json()["freshness_state"] == "updating"
    monkeypatch.setitem(server._trade_service_mod._cfg, "trade_gate_miss_mode", 1.0)
    with engine.begin() as conn:
        conn.execute(delete(league_members_table))
    body = status(client, job_id, 30).get_json()
    assert (body["status"], body["error"], body["cards"]) == ("error", "roster_check_unavailable", [])
    assert (body["cursor"], body["total_ready"]) == (30, 0)       # the cursor holds


def test_status_for_another_users_job_is_not_served_from_the_store(p1, spawned):
    client, _, sess = p1
    job_id = build_page()
    server._trade_jobs.clear()
    sess["user_id"] = "someone_else"
    try:
        assert status(client, job_id, 30).status_code == 404
    finally:
        sess["user_id"] = UID


# ── Triggers ────────────────────────────────────────────────────────────────

def test_a_roster_change_rebuilds_lazily_at_the_next_serve(p1, spawned):
    """S0's handler kicks nothing (a live session holds its last init's rosters);
    the next serve sees the roster_fp move and kicks the rebuild."""
    client, engine, _ = p1
    build_page()
    with engine.begin() as conn:
        conn.execute(update(league_members_table).where(league_members_table.c.user_id == UID)
                     .values(roster_data=json.dumps(["g2", "x9"])))
    roster_snapshot.on_roster_change(LEAGUE, "rfp1:old", "rfp1:new")
    assert not spawned
    body = generate(client, page=1).get_json()
    assert (body["serve_source"], body["freshness_state"]) == ("page", "updating")
    assert len(spawned) == 1


def test_session_init_warm_up_is_page_eligible(init_harness, monkeypatch, spawned):
    """U5 (a)/(d): session/init (also the step after a platform league import)
    kicks the organic warm-up whose completion stores the page."""
    client, kickoff, key = init_harness
    monkeypatch.setattr(ff, "_flags_cache", {**ff.flags_dict(), FLAG: True, EVIDENCE: True})
    resp = client.post("/api/session/init", content_type="application/json",
                       headers={"X-Session-Token": INIT_TOKEN},
                       data=json.dumps({"user_id": PLATFORM_USER, "league_id": PLATFORM_LEAGUE}))
    assert resp.status_code == 200, resp.get_json()
    kickoff.assert_called_once()
    job_id = REAL_KICKOFF(**kickoff.call_args.kwargs)
    try:
        assert server._trade_jobs[job_id]["page_scope"] == SCOPE
    finally:
        with server._trade_jobs_lock:
            server._trade_jobs.pop(job_id, None)
            server._trade_jobs_by_key.pop(key, None)


# ── Input changes make pages stale (lead review A) ──────────────────────────
# Every _invalidate_trade_jobs call marks rows stale after the job lock is
# released (user scope: the user's rows; league scope: the league's rows), and
# a board publish also marks the league, whose decks read that board.

def _vote(client):
    response = client.post("/api/rank3", headers=HEADERS, json={"ranked": ["g1", "g2", "r1"]})
    assert response.status_code == 200, response.get_json()


def _other_league_row():
    db_module.save_trade_page({**_row(time.time(), "elsewhere"), "league_id": "league_other"})


def _state(league_id=LEAGUE):
    row = db_module.load_trade_page(UID, league_id, "1qb_ppr", SCOPE)
    return row["state"]


def test_a_vote_makes_the_next_serve_updating_until_a_rebuild_lands(p1, spawned):
    client, _, _ = p1
    build_page()
    _vote(client)
    assert _state() == "stale"
    body = generate(client, page=1).get_json()
    assert (body["serve_source"], body["freshness_state"]) == ("page", "updating")
    assert ids(body["cards"]) == [f"p1-{i:03d}" for i in range(30)]
    assert len(spawned) == 1                          # the rebuild
    rebuilt = run_job(force_fresh=True)               # a deck on the voted board lands
    assert _state() == "ready" and stored()["deck_job_id"] == rebuilt
    body = generate(client, page=1).get_json()
    assert (body["job_id"], body["freshness_state"]) == (rebuilt, "fresh")


def test_the_stale_mark_survives_a_restart(p1, spawned):
    client, _, _ = p1
    build_page()
    _vote(client)
    server._trade_jobs.clear()                        # the daily worker kill
    server._trade_jobs_by_key.clear()
    server._trade_input_epochs.clear()
    body = generate(client, page=1).get_json()
    assert (body["serve_source"], body["freshness_state"]) == ("page", "updating")
    assert len(spawned) == 1


def test_a_league_scoped_change_marks_only_that_league(p1, spawned):
    """The awaiting-dismiss shape: a partner's league-scoped invalidation."""
    client, _, _ = p1
    build_page()
    _other_league_row()
    server._invalidate_trade_jobs(user_id=OPP, league_id=LEAGUE)
    assert (_state(), _state("league_other")) == ("stale", "ready")
    assert generate(client, page=1).get_json()["freshness_state"] == "updating"


def test_a_partners_board_publish_marks_the_league(p1, spawned):
    build_page()
    _other_league_row()
    server._publish_member_rankings_for_trade_refresh(
        user_id=OPP, league_id=LEAGUE, rankings=[{"player_id": "r1", "elo": 1510.0}],
        scoring_format="1qb_ppr")
    assert (_state(), _state("league_other")) == ("stale", "ready")


def test_a_user_scoped_change_marks_every_league_of_that_user(p1, spawned):
    build_page()
    _other_league_row()
    server._invalidate_trade_jobs(user_id=UID)
    assert (_state(), _state("league_other")) == ("stale", "stale")


def test_a_rebuild_in_flight_at_the_mark_never_writes(p1, spawned):
    client, _, _ = p1
    build_page()
    inflight = run_job(synchronous=False, force_fresh=True)   # admitted before the vote
    admitted = server._trade_jobs[inflight]["page_built_at"]
    _vote(client)
    # In process: the epoch fence revoked it, so its completion stores nothing.
    assert server._store_trade_page(inflight) is False
    # In the DB: the mark advanced built_at, so even a write that slipped past
    # the in-process check before the vote is refused by the supersede guard.
    late = {**_row(admitted, inflight), "roster_fp": stored()["roster_fp"]}
    assert db_module.save_trade_page(late) is False
    assert _state() == "stale" and stored()["deck_job_id"] != inflight
    run_job(force_fresh=True)                                  # admitted after it
    assert _state() == "ready"


def test_stale_marks_never_run_under_the_job_lock(p1, spawned, monkeypatch):
    """T4-style audit: every mark records whether _trade_jobs_lock was held."""
    client, _, _ = p1
    build_page()
    seen = []
    real = db_module.mark_trade_pages_stale

    def audited(**kwargs):
        seen.append((kwargs.get("user_id"), kwargs.get("league_id"),
                     server._trade_jobs_lock.locked()))
        return real(**kwargs)

    monkeypatch.setattr(db_module, "mark_trade_pages_stale", audited)
    _vote(client)                                                    # user + publish
    server._invalidate_trade_jobs(user_id=OPP, league_id=LEAGUE)     # league scope
    roster_snapshot.on_roster_change(LEAGUE, "rfp1:old", "rfp1:new")  # S0's handler
    assert {(user, league) for user, league, _ in seen} >= {(UID, None), (None, LEAGUE)}
    assert [entry for entry in seen if entry[2]] == []


# ── Engine identity across deploys (lead review B) ──────────────────────────

@pytest.mark.parametrize("change", ["deck_pipeline_version", "engine_code_hash"])
def test_an_engine_code_or_deck_pipeline_change_blocks_the_page(p1, spawned, monkeypatch, change):
    client, _, _ = p1
    build_page()
    if change == "deck_pipeline_version":
        monkeypatch.setattr(server, "DECK_PIPELINE_VERSION", server.DECK_PIPELINE_VERSION + 1)
    else:
        monkeypatch.setattr(server, "_engine_code_hash_value", "0" * 12)
    server._trade_jobs.clear()
    server._trade_jobs_by_key.clear()
    body = generate(client, page=1).get_json()
    assert "serve_source" not in body and len(spawned) == 1   # today's path


def test_every_backend_module_value_core_imports_is_hashed():
    """value_core's own imports of app modules (trade_service, ranking_service,
    power_rankings, trade_policy) all decide its decks, so all are hashed."""
    import re
    root = Path(server.__file__).resolve().parent
    hashed = {path.relative_to(root).as_posix()
              for pattern in server._ENGINE_CODE_MODULES for path in root.glob(pattern)}
    imported = set()
    for source in (root / "value_core").glob("*.py"):
        for name in re.findall(r"from \.\.(\w+) import|from \.\. import (\w+)", source.read_text()):
            imported.add((name[0] or name[1]) + ".py")
    assert imported and imported <= hashed, imported - hashed


def test_the_engine_code_hash_covers_the_module_set_once_per_process(tmp_path, monkeypatch):
    root = Path(server.__file__).resolve().parent
    for pattern in server._ENGINE_CODE_MODULES:
        assert list(root.glob(pattern)), f"engine module set: nothing matches {pattern}"
    files = sorted({path for pattern in server._ENGINE_CODE_MODULES for path in root.glob(pattern)})
    assert "server.py" not in {path.name for path in files}
    for path in files:
        copy_to = tmp_path / path.relative_to(root)
        copy_to.parent.mkdir(parents=True, exist_ok=True)
        copy_to.write_bytes(path.read_bytes())
    assert server._engine_code_hash_of(tmp_path) == server._engine_code_hash_of(root)
    (tmp_path / "server.py").write_text("# a deploy that only touches server.py\n")
    assert server._engine_code_hash_of(tmp_path) == server._engine_code_hash_of(root)
    narrative = tmp_path / "trade_narrative.py"
    narrative.write_bytes(narrative.read_bytes() + b"\n# engine change\n")
    assert server._engine_code_hash_of(tmp_path) != server._engine_code_hash_of(root)
    narrative.write_bytes((root / "trade_narrative.py").read_bytes())
    tiers = tmp_path / "tier_config.json"           # ruling 25: the tier bands are engine input
    assert tiers.exists()
    tiers.write_bytes(tiers.read_bytes().replace(b"1", b"2", 1))
    assert server._engine_code_hash_of(tmp_path) != server._engine_code_hash_of(root)
    calls = []
    monkeypatch.setattr(server, "_engine_code_hash_value", None)
    monkeypatch.setattr(server, "_engine_code_hash_of", lambda path: calls.append(path) or "c0ffee000000")
    assert server._trade_engine_code_hash() == server._trade_engine_code_hash() == "c0ffee000000"
    assert len(calls) == 1


def test_value_cores_standings_module_is_hashed_and_the_rest_of_outlook_is_not(tmp_path):
    """models-eng (e): outlook/league_state.py loads the W/L/T, points_for and
    completed_weeks value core reads, so its bytes are in the hash. The rest
    of outlook/ and trade_input_evidence.py are excluded on purpose."""
    root = Path(server.__file__).resolve().parent
    files = sorted({path for pattern in server._ENGINE_CODE_MODULES for path in root.glob(pattern)})
    hashed = {path.relative_to(root).as_posix() for path in files}
    assert {name for name in hashed if name.startswith("outlook/")} == {"outlook/league_state.py"}
    assert "trade_input_evidence.py" not in hashed
    for path in files:
        copy_to = tmp_path / path.relative_to(root)
        copy_to.parent.mkdir(parents=True, exist_ok=True)
        copy_to.write_bytes(path.read_bytes())
    assert server._engine_code_hash_of(tmp_path) == server._engine_code_hash_of(root)
    (tmp_path / "outlook" / "simulator.py").write_text("# an Outlook-only edit\n")
    (tmp_path / "trade_input_evidence.py").write_text("# a provenance edit\n")
    assert server._engine_code_hash_of(tmp_path) == server._engine_code_hash_of(root)
    standings = tmp_path / "outlook" / "league_state.py"
    standings.write_bytes(standings.read_bytes() + b"\n# a standings change\n")
    assert server._engine_code_hash_of(tmp_path) != server._engine_code_hash_of(root)


# ── Eviction ────────────────────────────────────────────────────────────────

def _days_ago(days):
    return db_module.page_store_iso(time.time() - days * 86400)


def test_eviction_by_age_uses_last_served_else_built(file_db):
    rows = {
        "served-recently": _row(time.time() - 40 * 86400, "a", last_served_at=_days_ago(1)),
        "served-long-ago": _row(time.time() - 40 * 86400, "b", last_served_at=_days_ago(31)),
        "built-long-ago": _row(time.time() - 31 * 86400, "c"),
        "built-recently": _row(time.time() - 1 * 86400, "d"),
    }
    for scope, row in rows.items():
        db_module.save_trade_page({**row, "request_scope": scope})
    assert db_module.evict_trade_pages(evict_days=30, max_bytes=10 ** 9) == (2, 0)
    with file_db.connect() as conn:
        left = {r.request_scope for r in conn.execute(select(db_module.trade_page_store_table))}
    assert left == {"served-recently", "built-recently"}


def test_eviction_by_the_byte_ceiling_drops_least_recently_served(file_db):
    for n in range(5):
        db_module.save_trade_page({**_row(time.time(), f"j{n}", stored_bytes=100,
                                          last_served_at=_days_ago(5 - n)),
                                   "request_scope": f"s{n}"})
    assert db_module.evict_trade_pages(evict_days=30, max_bytes=250) == (0, 3)
    with file_db.connect() as conn:
        left = sorted(r.request_scope for r in conn.execute(select(db_module.trade_page_store_table)))
    assert left == ["s3", "s4"]


def test_eviction_is_bounded_per_pass(file_db):
    for n in range(7):
        db_module.save_trade_page({**_row(time.time() - 60 * 86400, f"j{n}"), "request_scope": f"s{n}"})
    assert db_module.evict_trade_pages(evict_days=30, max_bytes=10 ** 9, batch_size=3) == (3, 0)
    assert db_module.evict_trade_pages(evict_days=30, max_bytes=10 ** 9, batch_size=3) == (3, 0)
    assert db_module.evict_trade_pages(evict_days=30, max_bytes=10 ** 9, batch_size=3) == (1, 0)


def test_the_cleanup_pass_evicts_only_with_the_flag_on(file_db, monkeypatch):
    db_module.save_trade_page(_row(time.time() - 60 * 86400, "old"))
    monkeypatch.setattr(ff, "_flags_cache", {**ff.flags_dict(), FLAG: False})
    server._evict_trade_page_store()
    assert stored() is not None
    monkeypatch.setattr(ff, "_flags_cache", {**ff.flags_dict(), FLAG: True, EVIDENCE: True})
    server._evict_trade_page_store()
    assert stored() is None


# ── Account deletion and export ─────────────────────────────────────────────

def test_account_deletion_removes_page_rows_and_export_stays_json(file_db):
    db_module.save_trade_page(_row(time.time(), "mine"))
    db_module.save_trade_page({**_row(time.time(), "theirs"), "user_id": "someone_else"})
    archive = accounts.export_user_data(UID)
    assert [r["deck_job_id"] for r in archive["tables"]["trade_page_store"]] == ["mine"]
    assert archive["tables"]["trade_page_store"][0]["pages_blob"]["cards"] == ["mine"]
    json.dumps(archive)                      # the export route jsonifies it
    accounts.delete_user_data(UID)
    with file_db.connect() as conn:
        assert [r.user_id for r in conn.execute(select(db_module.trade_page_store_table))] == [
            "someone_else"]


# ── Measured size (scope §7, AC-L8) ─────────────────────────────────────────

def replicated_card(i):
    """The flag-off golden card replicated with varied ids (the E2 sizing method)."""
    row = copy.deepcopy(GOLDEN_CARD)
    row.update(trade_id=f"{i:032x}", league_id="1180091726382297088", impression_id=f"{i * 7919:032x}",
               expires_at=(datetime.now(timezone.utc) + timedelta(days=7)).isoformat())
    row["give"][0]["id"], row["receive"][0]["id"] = f"g{i}", f"r{i}"
    return row


def varied_card(i, rng):
    """The golden card's shape with every value drawn at random: unique player
    names, ids, prices and copy per card, and two-player sides a third of the
    time. Much less compressible than any real deck (real names, teams and
    templated copy repeat); an upper bound for the per-pair bytes."""
    def word(lo=4, hi=9):
        return "".join(rng.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(rng.randint(lo, hi)))

    def player():
        return {"age": rng.randint(21, 34), "id": str(rng.randint(1000, 99999)),
                "name": f"{word().title()} {word().title()}", "position": rng.choice("QB RB WR TE".split()),
                "team": word(2, 3).upper(), "years_experience": rng.randint(0, 12)}

    row = copy.deepcopy(GOLDEN_CARD)
    row.update(
        trade_id=f"{rng.getrandbits(128):032x}", impression_id=f"{rng.getrandbits(128):032x}",
        league_id="1180091726382297088", target_user_id=str(rng.randint(10 ** 17, 10 ** 18)),
        target_username=word(5, 12), expires_at=(datetime.now(timezone.utc) + timedelta(
            days=7, seconds=rng.random())).isoformat(),
        composite_score=round(rng.random(), 3), fairness_score=round(rng.random(), 3),
        mismatch_score=round(rng.random(), 3), need_fit=round(rng.random(), 2),
        give_value=round(rng.uniform(300, 9000), 1), receive_value=round(rng.uniform(300, 9000), 1),
        give=[player() for _ in range(rng.choice((1, 1, 2)))],
        receive=[player() for _ in range(rng.choice((1, 1, 2)))],
        narrative=" ".join(word() for _ in range(rng.randint(8, 16))).capitalize() + ".")
    row["gap"] = {"add_to": rng.choice(("give", "receive")), "firsts": round(rng.random(), 2),
                  "pick_equivalent": {"label": f"{word().title()} {rng.randint(1, 4)}th Round Pick",
                                      "pick_id": f"generic_pick_{rng.randint(1, 4)}_{word(3, 5)}",
                                      "value": round(rng.uniform(50, 900), 1)},
                  "value": round(rng.uniform(0, 900), 1)}
    row["match_context"]["positional_rationale"] = " ".join(word() for _ in range(rng.randint(6, 12))) + "."
    row["match_context"]["user_needs"] = rng.sample(["QB", "RB", "WR", "TE"], rng.randint(1, 4))
    return row


@pytest.mark.parametrize("deck_kind", ["replicated", "varied"])
def test_measured_stored_bytes_for_a_production_size_deck(p1, deck_kind):
    import random
    rng = random.Random(20261020)
    deck = [replicated_card(i) if deck_kind == "replicated" else varied_card(i, rng)
            for i in range(2354)]                            # B15's measured production deck
    job_id = run_job()
    with server._trade_jobs_lock:
        server._trade_jobs[job_id]["cards"] = deck
    assert server._store_trade_page(job_id)
    row = stored()
    raw = len(json.dumps(row["pages_blob"], separators=(",", ":")).encode())
    print(f"\n[P1 measure] deck={deck_kind} cards stored={row['card_count']} raw_json={raw} B "
          f"stored_bytes={row['stored_bytes']} B ({row['stored_bytes'] / 1024:.1f} KiB)")
    assert row["card_count"] == 90
    assert row["stored_bytes"] <= 200_000                     # scope §7: ≤ about 0.2 MB per pair
