"""ADR-025 stage 1: deferred evidence, full rows at delivery (flag trade.first_page_store).

Spec: docs/plans/org-bringup/adr-025-draft.md "Decision"; models-lead's C1-C9
(docs/plans/org-bringup/leads/models-lead-launch.md, Confirmation).

Pinned here:
  * C2: a deferred job that completes and is never delivered writes no
    deck_impressions or deck_candidate_sets row; publication waits on no commit;
  * C4: the first delivery of a 10-card page writes full rows for the first 30;
  * C3: a later cursor page changes exactly its newly delivered cards;
  * C6: written rows equal the build-time snapshot, whatever moves after build;
  * C5: ghost rows are narrow (assets_json and the compact inputs only);
  * idempotent retries, evidence_tier per row, C8 selection and retention;
  * the budget rule (the stored evidence_blob shrinks after delivery);
  * the blob path once the job has left the process, partial runs, the lease;
  * evidence mode per path; flag off is today's write; deferred rows equal the
    rows the logger writes live (the real owner path, structured features);
  * the measured evidence_blob bytes for a 2,354-card deck.

Harnesses: test_trade_page_store's `p1` (real worker and routes over stored
rosters, in-memory SQLite, flag on) with a synthetic deck assembled by the real
logger; test_owner_batch_publication's `sized_exclusive` (the real owner path).
Evidence writes run inline here (the production thread starter is replaced).
"""
import copy
import hashlib
import json
import random
import threading
import time
import zlib

import pytest
from sqlalchemy import delete, insert, select, update

import backend.database as db_module
import backend.feature_flags as ff
import backend.server as server
from backend import trade_service as ts, user_data_lifecycle
from backend.database import league_members_table
from backend.ranking_service import Player
from backend.tests.test_i1_serve_filter import LEAGUE, OPP, UID, live  # noqa: F401  (fixture)
from backend.tests.test_trade_page_store import (  # noqa: F401  (fixture)
    HEADERS, generate, p1, run_job, status, stored)
from backend.tests.test_owner_generator_routes import (  # noqa: F401  (fixtures)
    ME, harness, owner_harness, worker)
from backend.tests.test_owner_only_routes import exclusive  # noqa: F401  (fixture)
from backend.tests.test_owner_batch_publication import sized_exclusive  # noqa: F401  (fixture)

TIERS = ("first30", "delivered", "ghost", "archive", "full_interim")
COMPACT = set(server._COMPACT_FEATURE_KEYS) | set(server._INJECTED_FEATURE_KEYS)
VOLATILE = ("impression_id", "served_at", "candidate_set_id", "evidence_tier")


def archive_id(selected=True):
    """A job id the C8 rule selects (or not)."""
    return next(f"deck-{i:04d}" for i in range(100000)
                if server._deck_archive_selected(f"deck-{i:04d}") is selected)


def rows(engine, table=db_module.deck_impressions_table):
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(select(table))]


def by_index(engine):
    return {(r["is_ghost"] or 0, r["card_index"]): r for r in rows(engine)}


@pytest.fixture()
def deferred(p1, monkeypatch):
    """p1 (flag on) with F1 and telemetry on, and rosters a 120-card deck can
    draw from: UID owns mine0.., OPP owns theirs0.."""
    client, engine, sess = p1
    monkeypatch.setattr(server, "_deck_signal_v2_enabled", lambda: True)
    monkeypatch.setattr(server, "_suggestion_telemetry_enabled", lambda: True)
    with engine.begin() as conn:
        for uid, prefix, base in ((UID, "mine", ["g2"]), (OPP, "theirs", ["r2", "g1"])):
            conn.execute(update(league_members_table).where(league_members_table.c.user_id == uid)
                         .values(roster_data=json.dumps(base + [f"{prefix}{i}" for i in range(400)])))
    yield client, engine, sess


def synthetic_cards(n):
    players = {}
    cards = []
    for i in range(n):
        give, recv = f"mine{i}", f"theirs{i}"
        players[give] = Player(id=give, name=give, position=("QB", "RB", "WR", "TE")[i % 4], team="AAA", age=25)
        players[recv] = Player(id=recv, name=recv, position=("WR", "TE", "QB", "RB")[i % 4], team="BBB", age=24)
        card = ts.TradeCard(trade_id=f"t-{i:04d}", league_id=LEAGUE, proposing_user_id=UID,
                            target_user_id=OPP, target_username="opp", give_player_ids=[give],
                            receive_player_ids=[recv], mismatch_score=10.0 + i,
                            fairness_score=0.8 + i / 10000, composite_score=1.0 - i / 1000)
        card.give_value, card.receive_value = 1000.0 + i, 1100.0 + i
        card.lane = ("value", "window")[i % 2]
        cards.append(card)
    return cards, players


def public(card, iid):
    return {"trade_id": card.trade_id, "league_id": LEAGUE, "target_user_id": OPP,
            "target_username": "opp", "give": [{"id": p} for p in card.give_player_ids],
            "receive": [{"id": p} for p in card.receive_player_ids], "decision": None,
            "impression_id": iid, "expires_at": card.expires_at}


def deferred_deck(n, *, ghost_every=0, job_id=None, store=True, complete=True, **kickoff):
    """A complete deferred organic job whose deck is `n` cards (plus a ghost
    after every `ghost_every`), assembled by the real logger into the job's
    _DeckEvidence, published with its minted ids, then stored (P1).
    complete=False: the job is still running (assembled, not finished)."""
    real = run_job(**kickoff)
    with server._trade_jobs_lock:
        job = server._trade_jobs.pop(real)
        assert job["evidence_mode"] == "deferred" and job["status"] == "complete"
        job_id = job_id or archive_id(False)               # deterministic, not a C8 deck
        job.update(job_id=job_id, append_only=True)
        server._trade_jobs[job_id] = job
        server._trade_jobs_by_key[job["key"]] = job_id
    cards, players = synthetic_cards(n + (n // ghost_every if ghost_every else 0))
    final = cards
    ghosts = [(pos, c) for pos, c in enumerate(final) if ghost_every and pos % (ghost_every + 1) == ghost_every]
    ghost_ids = {id(c) for _, c in ghosts}
    served = [c for c in final if id(c) not in ghost_ids]
    ev = server._DeckEvidence(job_id, UID)
    imp = server._log_deck_signal_impressions(
        user_id=UID, league_id=LEAGUE, job_id=job_id, cards=served, players_dict=players,
        capture=None, scoring_format="1qb_ppr", ghost_cards=ghosts, candidate_pool=[],
        policy_version="pv-test", evidence_sink=ev)
    ev.seal()
    with server._trade_jobs_lock:
        job.update(cards=[public(c, imp[id(c)]) for c in served], evidence=ev)
        if not complete:
            job.update(status="running", finished_at=None)
            return job_id, served, ghosts, ev, players
    server._deck_evidence_job_done(job_id)
    if store:
        assert server._store_trade_page(job_id)
    return job_id, served, ghosts, ev, players


def deliver_job(job_id, cursor):
    """E2/P2's live-job page at `cursor` (the deck path past the stored pages)."""
    with server._trade_jobs_lock:
        snapshot = dict(server._trade_jobs[job_id])
    return server._trade_job_page_view(snapshot, cursor)


def tiers(engine):
    return {r["impression_id"]: r["evidence_tier"] for r in rows(engine)}


def held(ev):
    """The deck's held (not yet written) full rows, unpacked."""
    with ev.lock:
        return {iid: server._unpack_row(packed) for iid, (_, packed) in ev.rows.items()}


# ── C2: never delivered, nothing written ────────────────────────────────────

def test_c2_a_completed_deferred_job_never_delivered_writes_no_rows(deferred):
    client, engine, _ = deferred
    job_id = run_job()                                     # a real organic deck, flag on
    job = server._trade_jobs[job_id]
    assert job["status"] == "complete" and job["evidence_mode"] == "deferred"
    ev = job["evidence"]
    assert ev.rows and ev.candidate_set is not None and ev.complete
    assert all(c["impression_id"] in ev.rows for c in job["cards"])   # published, never committed
    assert rows(engine) == [] and rows(engine, db_module.deck_candidate_sets_table) == []
    blob = stored()["evidence_blob"]                       # held in the page store instead
    assert {r["impression_id"] for r in blob["rows"]} == {c["impression_id"] for c in job["cards"]}
    assert blob["candidate_set"]["deck_job_id"] == job_id


PARTIAL_ENDINGS = {
    "superseded": lambda job: server._revoke_trade_job_locked(job, "superseded"),
    "timeout": lambda job: job.update(status="error", error="timeout"),
    "error": lambda job: job.update(status="error", error="boom"),
    # The run completed, but its logger raised mid-deck (never sealed).
    "assembly_failed": lambda job: (job.update(status="complete"),
                                    setattr(job["evidence"], "sealed", False)),
}


@pytest.mark.parametrize("ending", sorted(PARTIAL_ENDINGS))
def test_a_partial_run_writes_exactly_its_delivered_cards_as_partial_run(deferred, ending):
    """F1 (head-eng ruling 9): the first 30 went out while the run was live (an
    owner batch), then the run ended partial. Swipes on those cards must land,
    so exactly they are written, with the assembled ghosts and candidate set,
    every row 'partial_run' (replay excludes the deck)."""
    _, engine, _ = deferred
    job_id, _, ghosts, ev, _ = deferred_deck(40, ghost_every=9, store=False, complete=False)
    seen = server._trade_jobs[job_id]["cards"][:30]
    server._deck_evidence_delivered(ev, seen)
    assert rows(engine) == []                              # recorded, not yet written
    with server._trade_jobs_lock:
        PARTIAL_ENDINGS[ending](server._trade_jobs[job_id])
    server._deck_evidence_job_done(job_id)
    written = rows(engine)
    assert {r["impression_id"] for r in written if not r["is_ghost"]} == {c["impression_id"] for c in seen}
    assert len([r for r in written if r["is_ghost"]]) == len(ghosts)
    assert {r["evidence_tier"] for r in written} == {"partial_run"}
    assert len(rows(engine, db_module.deck_candidate_sets_table)) == 1
    server._deck_evidence_delivered(ev, seen, partial=True)   # a retried poll
    assert len(rows(engine)) == len(written)


@pytest.mark.parametrize("ending", sorted(PARTIAL_ENDINGS))
def test_a_partial_run_with_nothing_delivered_writes_nothing(deferred, ending):
    _, engine, _ = deferred
    job_id, _, _, ev, _ = deferred_deck(40, ghost_every=9, store=False, complete=False)
    with server._trade_jobs_lock:
        PARTIAL_ENDINGS[ending](server._trade_jobs[job_id])
    server._deck_evidence_job_done(job_id)
    assert rows(engine) == [] and rows(engine, db_module.deck_candidate_sets_table) == []


def test_a_timed_out_jobs_batches_served_later_on_the_legacy_path_are_written_as_partial_run(deferred):
    """Ruling 9: the legacy path keeps serving a timed-out job's published
    batches; each such delivery writes its cards as 'partial_run'."""
    _, engine, _ = deferred
    job_id, _, _, ev, _ = deferred_deck(40, store=False, complete=False)
    with server._trade_jobs_lock:
        server._trade_jobs[job_id].update(status="error", error="timeout")
    server._deck_evidence_job_done(job_id)
    assert rows(engine) == []
    out = server._trade_job_public_view(dict(server._trade_jobs[job_id]))   # a legacy poll
    assert out["status"] == "error" and len(out["cards"]) == 40
    assert tiers(engine) == {c["impression_id"]: "partial_run" for c in out["cards"]}
    assert server._trade_job_page_view(dict(server._trade_jobs[job_id]), 0)["cards"] == []


def test_a_ceiling_hit_run_writes_nothing_even_after_its_cards_were_seen(deferred):
    _, engine, _ = deferred
    job_id, _, _, ev, _ = deferred_deck(40, store=False, complete=False)
    server._deck_evidence_delivered(ev, server._trade_jobs[job_id]["cards"][:30])
    with server._trade_jobs_lock:
        server._trade_jobs[job_id].update(status="complete", safety_ceiling_hit=True)
    server._deck_evidence_job_done(job_id)
    assert ev.discarded and not ev.rows and ev.candidate_set is None
    server._deck_evidence_delivered(ev, server._trade_jobs[job_id]["cards"][:30])
    assert rows(engine) == [] and rows(engine, db_module.deck_candidate_sets_table) == []


def test_deliveries_made_while_the_run_was_live_are_written_at_completion(deferred):
    _, engine, _ = deferred
    job_id, _, _, ev, _ = deferred_deck(40, store=False, complete=False)
    first30 = [c["impression_id"] for c in server._trade_jobs[job_id]["cards"][:30]]
    server._deck_evidence_delivered(ev, server._trade_jobs[job_id]["cards"][:30])
    server._trade_jobs[job_id]["status"] = "complete"
    server._deck_evidence_job_done(job_id)
    written = tiers(engine)
    assert {written[i] for i in first30} == {"delivered"} and len(written) == 40


# ── F3: the build-time writes wait for the first delivery ──────────────────

@pytest.fixture()
def generated_events(monkeypatch):
    """trades_generated emits, captured (every other event passes through)."""
    events = []
    real = server.record_event

    def record(user_id, name, *args, **kwargs):
        if name == "trades_generated":
            events.append({"user_id": user_id, **kwargs})
            return None
        return real(user_id, name, *args, **kwargs)

    monkeypatch.setattr(server, "record_event", record)
    return events


def build_writes(engine):
    return (len(rows(engine, db_module.trade_impressions_table)),
            len(rows(engine, db_module.bakeoff_runs_table)))


def test_f3_a_never_served_deferred_deck_writes_none_of_its_build_time_rows(deferred, generated_events):
    _, engine, _ = deferred
    job_id = run_job()
    assert server._trade_jobs[job_id]["cards"] and server._trade_jobs[job_id]["status"] == "complete"
    assert build_writes(engine) == (0, 0) and generated_events == []
    assert rows(engine) == []


def test_f3_the_first_delivery_writes_them_once_with_todays_props(deferred, generated_events, monkeypatch):
    client, engine, _ = deferred
    monkeypatch.setattr(ff, "_flags_cache", {**ff.flags_dict(), "trade.first_page_store": False})
    live_job = run_job()                                   # today's run: written at build
    today = (build_writes(engine), [e["props"] for e in generated_events])
    assert today[0] == (len(server._trade_jobs[live_job]["cards"]), 1) and len(today[1]) == 1
    with engine.begin() as conn:
        conn.execute(delete(db_module.trade_impressions_table))
        conn.execute(delete(db_module.bakeoff_runs_table))
    generated_events.clear()
    monkeypatch.setattr(ff, "_flags_cache", {**ff.flags_dict(), "trade.first_page_store": True})
    job_id = run_job(force_fresh=True)
    cards = server._trade_jobs[job_id]["cards"]
    assert build_writes(engine) == (0, 0) and generated_events == []
    assert generate(client, page=1).get_json()["job_id"] == job_id    # page 1 from the store
    status(client, job_id, 0)                              # a retry
    generate(client, page=1)                               # another tap
    server._deck_evidence_delivered(server._trade_jobs[job_id]["evidence"], cards)
    assert build_writes(engine) == (len(cards), 1)
    assert len(generated_events) == 1
    event = generated_events[0]
    assert (event["user_id"], event["league_id"], event["source"]) == (UID, LEAGUE, "api")
    strip = lambda props: {k: v for k, v in props.items() if k != "gen_ms"}
    assert strip(event["props"]) == strip(today[1][0]) and event["props"]["count"] == len(cards)


def test_f3_after_the_job_left_the_process_the_blob_carries_them(deferred, generated_events):
    client, engine, _ = deferred
    job_id = run_job()
    n = len(server._trade_jobs[job_id]["cards"])
    blob = stored()["evidence_blob"]
    assert blob["generated"]["props"]["count"] == n and len(blob["trade_impressions"]["cards"]) == n
    assert "bakeoff_run" not in blob                       # megabytes on an owner run: in process only
    server._trade_jobs.clear()
    server._trade_jobs_by_key.clear()
    status(client, job_id, 0)
    status(client, job_id, 0)
    assert build_writes(engine) == (n, 0) and len(generated_events) == 1
    assert stored()["evidence_blob"] is None


def test_f3_a_partial_run_writes_its_held_rows_at_its_delivery_but_never_trades_generated(
        deferred, generated_events):
    _, engine, _ = deferred
    job_id, served, _, ev, _ = deferred_deck(40, store=False, complete=False)
    ev.defer_trade_impressions(LEAGUE, served)             # the worker reached it, then timed out
    with server._trade_jobs_lock:
        server._trade_jobs[job_id].update(status="error", error="timeout")
    server._deck_evidence_job_done(job_id)
    assert build_writes(engine) == (0, 0)                  # nothing delivered yet
    server._trade_job_public_view(dict(server._trade_jobs[job_id]))
    assert build_writes(engine) == (40, 0) and generated_events == []


# ── F4: an action on a card whose row is still being written waits for it ──

@pytest.fixture()
def threaded(deferred, monkeypatch):
    """Evidence writes on real threads, as in production; joined at teardown.
    The in-memory database moves to one shared connection (StaticPool), since
    SQLite's default pool gives each thread its own empty database."""
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    _, engine, _ = deferred
    shared = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    db_module.metadata.create_all(shared)
    with engine.connect() as source, shared.begin() as target:
        for table in db_module.metadata.sorted_tables:
            data = [dict(r._mapping) for r in source.execute(select(table))]
            if data:
                target.execute(insert(table), data)
    monkeypatch.setattr(db_module, "engine", shared)
    threads = []

    def start(*, target, args):
        thread = threading.Thread(target=target, args=args, daemon=True)
        threads.append(thread)
        thread.start()

    monkeypatch.setattr(server, "_start_deck_evidence_thread", start)
    yield shared
    for thread in threads:
        thread.join(10)


def delay_flush(monkeypatch, seconds):
    real = server._deck_evidence_flush
    monkeypatch.setattr(server, "_deck_evidence_flush",
                        lambda ev: (time.sleep(seconds), real(ev))[1])


def outcomes(engine):
    return rows(engine, db_module.deck_outcomes_table)


def test_f4_an_outcome_on_a_card_whose_row_is_in_flight_waits_for_it(deferred, threaded, monkeypatch):
    client, engine = deferred[0], threaded
    job_id, *_ = deferred_deck(40)
    delay_flush(monkeypatch, 0.5)
    iid = status(client, job_id, 0).get_json()["cards"][0]["impression_id"]
    assert db_module.load_deck_impression(iid) is None    # the delivery write is in flight
    started = time.monotonic()
    server._save_deck_outcome_safe(iid, "like", acting_user_id=UID)   # /api/trades/swipe's writer
    waited = time.monotonic() - started
    assert 0.2 < waited < server._DECK_EVIDENCE_AWAIT_S
    assert [o["impression_id"] for o in outcomes(engine)] == [iid]
    assert server._pass_reason_key(iid, UID, "t-0000") == (iid, "impression")
    assert server._deck_evidence_pending == {}


def test_f4_the_wait_is_bounded(deferred, threaded, monkeypatch):
    client, engine = deferred[0], threaded
    monkeypatch.setattr(server, "_DECK_EVIDENCE_AWAIT_S", 0.3)
    job_id, *_ = deferred_deck(40)
    delay_flush(monkeypatch, 1.5)
    iid = status(client, job_id, 0).get_json()["cards"][0]["impression_id"]
    started = time.monotonic()
    server._save_deck_outcome_safe(iid, "like", acting_user_id=UID)
    waited = time.monotonic() - started
    assert 0.25 < waited < 1.0 and outcomes(engine) == []   # proceeds, as an unknown id did


def test_f4_an_unknown_id_with_no_pending_write_never_waits(deferred, monkeypatch):
    _, engine, _ = deferred
    for iid in ("not-an-impression", "f" * 32):
        started = time.monotonic()
        server._save_deck_outcome_safe(iid, "like", acting_user_id=UID)
        assert time.monotonic() - started < 0.1
    assert outcomes(engine) == []


# ── F5: memory ──────────────────────────────────────────────────────────────

def test_f5_a_decks_payload_is_freed_once_its_evidence_is_written(deferred):
    client, engine, _ = deferred
    job_id, _, _, ev, _ = deferred_deck(120, ghost_every=9)
    assert ev.rows and ev.ghosts and ev.candidate_set and ev.by_hash
    status(client, job_id, 0)
    assert (ev.rows, ev.ghosts, ev.diagnostics, ev.by_hash, ev.candidate_set) == ({}, {}, {}, {}, None)
    status(client, job_id, 30)                             # later pages still mark delivered
    assert len({iid for iid, t in tiers(engine).items() if t == "delivered"}) == 60


def test_f5_an_undelivered_deck_past_the_fresh_window_is_dropped_and_no_longer_served(deferred):
    client, engine, _ = deferred
    job_id, *_ = deferred_deck(120)
    job = server._trade_jobs[job_id]
    assert server._drop_stale_deck_evidence() == 0         # inside the window
    job["finished_at"] = time.monotonic() - server._PREGEN_TTL_SECONDS - 1
    assert server._drop_stale_deck_evidence() == 1
    assert "evidence" not in job and job["evidence_mode"] == "deferred" and server._trade_job_revoked(job)
    assert rows(engine) == []                              # still C2: nothing was written
    assert deliver_job(job_id, 90)["cards"] == []          # its in-process cards no longer serve
    page = status(client, job_id, 0).get_json()["cards"]   # its stored pages do, through the blob
    assert len(page) == 30 and {tiers(engine)[c["impression_id"]] for c in page} == {"delivered"}
    assert len(rows(engine)) == 90                         # the stored cards only


def test_f5_delivered_and_running_decks_are_kept(deferred):
    client, engine, _ = deferred
    job_id, *_ = deferred_deck(40)
    status(client, job_id, 0)
    running, *_ = deferred_deck(40, job_id="deck-running", store=False, complete=False,
                               force_fresh=True)
    for jid in (job_id, running):
        server._trade_jobs[jid]["finished_at"] = time.monotonic() - server._PREGEN_TTL_SECONDS - 1
    assert server._drop_stale_deck_evidence() == 0
    assert all("evidence" in server._trade_jobs[jid]
               and not server._trade_job_revoked(server._trade_jobs[jid]) for jid in (job_id, running))


# ── F6: replenishment ───────────────────────────────────────────────────────

def replenished(source):
    return [j for j in server._trade_jobs.values() if j.get("source") == source]


def test_f6_an_unopened_replenished_deck_writes_nothing(deferred, generated_events):
    _, engine, _ = deferred
    assert server._replenish_deck_for(UID, LEAGUE) is not None
    [job] = replenished("replenish")
    assert job["evidence_mode"] == "deferred" and job["cards"] and "page_scope" not in job
    assert rows(engine) == [] and build_writes(engine) == (0, 0) and generated_events == []
    assert rows(engine, db_module.trade_page_store_table) == []   # never page-stored


def test_f6_an_opened_replenished_deck_writes_at_its_delivery(deferred, generated_events):
    client, engine, _ = deferred
    server._replenish_deck_for(UID, LEAGUE)
    [job] = replenished("replenish")
    body = generate(client).get_json()                     # the tap that opens it: a cache hit
    assert body["job_id"] == job["job_id"] and body["cards"]
    written = rows(engine)
    assert {r["impression_id"] for r in written} == {c["impression_id"] for c in job["cards"]}
    assert {json.loads(r["features_json"])["deck_source"] for r in written} == {"replenish"}
    assert [e["props"]["deck_source"] for e in generated_events] == ["replenish"]
    assert build_writes(engine)[0] == len(job["cards"])


def test_f6_calibrations_targeted_refresh_keeps_its_rows_at_build(deferred):
    """_pregenerate_grading_targets refreshes through source "grading_refresh":
    a live job, never a reused undelivered deferred deck, so start_session's
    read (load_grading_legacy_deck) finds the refreshed deck's rows."""
    _, engine, _ = deferred
    organic = run_job()                                    # fresh, deferred, undelivered
    assert rows(engine) == []
    assert server._replenish_deck_for(UID, LEAGUE, source="grading_refresh") is not None
    [job] = replenished("grading_refresh")
    assert job["job_id"] != organic and job["evidence_mode"] == "live" and "evidence" not in job
    deck_job_id, _served_at, deck = db_module.load_grading_legacy_deck(UID, LEAGUE)
    assert deck_job_id == job["job_id"] and len(deck) == len(job["cards"]) > 0
    assert {json.loads(r["features_json"])["deck_source"] for r in deck} == {"grading_refresh"}


def test_f6_calibrations_refresh_reuses_a_delivered_deferred_deck(deferred):
    client, engine, _ = deferred
    organic = run_job()
    status(client, organic, 0)                             # delivered: its rows exist
    assert server._replenish_deck_for(UID, LEAGUE, source="grading_refresh") is not None
    assert replenished("grading_refresh") == []
    assert db_module.load_grading_legacy_deck(UID, LEAGUE)[0] == organic


# ── C4 and C3: first delivery, later pages ──────────────────────────────────

def test_c4_the_first_delivery_of_a_10_card_page_writes_full_rows_for_the_first_30(deferred, monkeypatch):
    client, engine, _ = deferred
    monkeypatch.setattr(server, "_trade_page_size", lambda: 10)
    job_id, served, _, ev, _ = deferred_deck(120)
    body = status(client, job_id, 0).get_json()            # page 1 of the stored deck
    sent = [c["impression_id"] for c in body["cards"]]
    assert len(sent) == 10 and body["serve_source"] == "page"
    written = by_index(engine)
    assert [written[(0, i)]["evidence_tier"] for i in range(30)] == ["delivered"] * 10 + ["first30"] * 20
    full = [written[(0, i)] for i in range(30)]
    assert all(r["features_json"] and json.loads(r["features_json"])["give_value"] is not None for r in full)
    # Stage 1: the rest of the served deck is written too, marked for packing to stop.
    assert {written[(0, i)]["evidence_tier"] for i in range(30, 120)} == {"full_interim"}
    assert len(rows(engine, db_module.deck_candidate_sets_table)) == 1


def test_c3_later_cursor_pages_change_exactly_the_newly_delivered_cards(deferred, monkeypatch):
    client, engine, _ = deferred
    monkeypatch.setattr(server, "_trade_page_size", lambda: 10)
    job_id, served, _, _, _ = deferred_deck(120)
    status(client, job_id, 0)
    before = tiers(engine)
    page2 = [c["impression_id"] for c in status(client, job_id, 10).get_json()["cards"]]
    after = tiers(engine)
    assert {iid for iid in after if after[iid] != before[iid]} == set(page2)
    assert {after[iid] for iid in page2} == {"delivered"} and len(after) == len(before)
    # Past the stored pages (30 at this page size): the live job's page.
    page5 = [c["impression_id"] for c in deliver_job(job_id, 40)["cards"]]
    final = tiers(engine)
    assert {iid for iid in final if final[iid] != after[iid]} == set(page5)
    assert {after[iid] for iid in page5} == {"full_interim"} and {final[iid] for iid in page5} == {"delivered"}


def test_served_impression_ids_are_the_rows_written(deferred):
    client, engine, _ = deferred
    job_id, *_ = deferred_deck(60)
    body = generate(client, page=1).get_json()             # P1: page 1 from the store
    assert body["serve_source"] == "page" and body["job_id"] == job_id
    written = {r["impression_id"]: r for r in rows(engine)}
    assert body["cards"] and all(written[c["impression_id"]]["evidence_tier"] == "delivered"
                                 and written[c["impression_id"]]["trade_hash"] == c["trade_hash"]
                                 for c in body["cards"])


# ── C6: the build-time snapshot ─────────────────────────────────────────────

def test_c6_written_rows_equal_the_build_time_snapshot(deferred, monkeypatch):
    client, engine, _ = deferred
    job_id, served, _, ev, players = deferred_deck(40)
    snapshot = held(ev)
    # Everything the logger read moves after the build: cards, players, board, flags.
    for card in served:
        card.give_value, card.fairness_score, card.lane = -1.0, 0.0, "moved"
        card.give_player_ids.append("g2")
    for p in players.values():
        p.position = "K"
    monkeypatch.setattr(server, "load_board_state", lambda *a: (999, "2030-01-01"))
    monkeypatch.setattr(server, "_deck_taste_enabled", lambda: False)
    status(client, job_id, 0)
    written = {r["impression_id"]: r for r in rows(engine)}
    assert set(written) == set(snapshot)
    for iid, frozen in snapshot.items():
        row = written[iid]
        assert {k: row[k] for k in frozen} == frozen


# ── C5: narrow ghosts ───────────────────────────────────────────────────────

def test_c5_ghost_rows_are_narrow_at_every_rank_and_inside_the_first_30(deferred):
    client, engine, _ = deferred
    job_id, served, ghosts, ev, _ = deferred_deck(60, ghost_every=9)   # ghosts at ranks 9, 19, ... 59
    assert {c["impression_id"] for c in server._trade_jobs[job_id]["cards"]}.isdisjoint(ev.ghosts)
    status(client, job_id, 0)
    ghost_rows = sorted((r for r in rows(engine) if r["is_ghost"] == 1), key=lambda r: r["card_index"])
    assert [r["card_index"] for r in ghost_rows] == [pos for pos, _ in ghosts] == [9, 19, 29, 39, 49, 59]
    for r, (_, card) in zip(ghost_rows, ghosts):
        assert r["evidence_tier"] == "ghost" and r["valuation_json"] is None
        assert json.loads(r["assets_json"]) == {"give": card.give_player_ids, "receive": card.receive_player_ids}
        features = json.loads(r["features_json"])
        assert set(features) <= COMPACT
        assert set(server._COMPACT_FEATURE_KEYS) | {"partner_user_id"} <= set(features)
        assert features["give_value"] == card.give_value and features["partner_user_id"] == OPP
    full = json.loads(next(r for r in rows(engine) if r["is_ghost"] == 0)["features_json"])
    assert "give_value_band" in full and set(full) > COMPACT   # full rows keep the wide shape


def test_ghost_rows_still_serve_the_matcher_and_the_value_model(deferred):
    """Readers of ghost rows: the executed-trade matcher reads partner_user_id
    and assets_json; replay's value_model reads extract_features' keys, which
    the narrow row keeps with the wide row's values."""
    from backend import value_model
    client, engine, _ = deferred
    job_id, _, ghosts, ev, _ = deferred_deck(20, ghost_every=9)
    status(client, job_id, 0)
    matched = [m for m in db_module.load_impressions_for_matching(LEAGUE, "2000-01-01", "2100-01-01")
               if m["is_ghost"] == 1]
    assert len(matched) == len(ghosts) and all(m["partner_user_id"] == OPP and m["assets"]["give"]
                                               for m in matched)
    by_pos = dict(ghosts)
    for r in (r for r in rows(engine) if r["is_ghost"] == 1):
        card, narrow = by_pos[r["card_index"]], json.loads(r["features_json"])
        x = value_model.extract_features(narrow)
        assert x["value_delta"] == pytest.approx((card.receive_value - card.give_value) / 1000.0)
        assert x["fairness"] == pytest.approx(card.fairness_score) and x[f"lane:{card.lane}"] == 1.0


# ── Idempotency ─────────────────────────────────────────────────────────────

def test_a_retried_delivery_writes_nothing_twice(deferred, monkeypatch):
    client, engine, _ = deferred
    job_id, _, _, ev, _ = deferred_deck(60, ghost_every=9)
    # The first write commits, but the process loses track of it (as if it
    # died between the commit and the bookkeeping).
    monkeypatch.setattr(server._DeckEvidence, "wrote", lambda self, *a, **k: None)
    status(client, job_id, 0)
    once = sorted(rows(engine), key=lambda r: r["impression_id"])
    cand = rows(engine, db_module.deck_candidate_sets_table)
    status(client, job_id, 0)                              # the client's retry
    with server._deck_evidence_write_lock:
        server._deck_evidence_flush(ev)                    # a replayed write
    assert sorted(rows(engine), key=lambda r: r["impression_id"]) == once
    assert rows(engine, db_module.deck_candidate_sets_table) == cand and len(cand) == 1


def test_a_retried_delivery_after_the_job_left_the_process_writes_nothing_twice(deferred):
    client, engine, _ = deferred
    job_id, *_ = deferred_deck(60, ghost_every=9)
    server._trade_jobs.clear()
    server._trade_jobs_by_key.clear()
    status(client, job_id, 0)
    once = sorted(rows(engine), key=lambda r: r["impression_id"])
    status(client, job_id, 0)
    assert sorted(rows(engine), key=lambda r: r["impression_id"]) == once


# ── evidence_tier, C8 ───────────────────────────────────────────────────────

def test_evidence_tiers_on_an_archive_deck(deferred, monkeypatch):
    client, engine, _ = deferred
    monkeypatch.setattr(server, "_trade_page_size", lambda: 10)
    job_id, served, ghosts, ev, _ = deferred_deck(120, ghost_every=9, job_id=archive_id(True))
    assert ev.archive
    status(client, job_id, 0)
    expected = {(0, i): "delivered" if i < 10 else "first30" if i < 30 else "archive" for i in range(120)}
    expected.update({(1, pos): "ghost" for pos, _ in ghosts})
    assert {k: r["evidence_tier"] for k, r in by_index(engine).items()} == expected
    # A delivered archive card is no longer an archive extra: retention keeps it.
    page = [c["impression_id"] for c in deliver_job(job_id, 50)["cards"]]
    assert page and {tiers(engine)[iid] for iid in page} == {"delivered"}


def test_a_non_archive_deck_marks_its_rest_full_interim(deferred):
    client, engine, _ = deferred
    job_id, *_ = deferred_deck(120, job_id=archive_id(False))
    status(client, job_id, 0)
    assert {r["evidence_tier"] for r in rows(engine) if r["card_index"] >= 30} == {"full_interim"}


def test_the_c8_selection_is_deterministic_by_deck_and_about_2_percent():
    ids = [hashlib.md5(str(i).encode()).hexdigest() for i in range(20000)]   # job-id shaped
    picks = [server._deck_archive_selected(i) for i in ids]
    assert picks == [server._deck_archive_selected(i) for i in ids]
    assert 0.017 < sum(picks) / len(picks) < 0.023
    for i in ids[:200]:
        assert server._deck_archive_selected(i) == (
            int(hashlib.sha256(f"c8-archive-v1|{i}".encode()).hexdigest(), 16) % 10000 < 200)
    job = archive_id(True)
    assert (server._DeckEvidence(job, "a").archive, server._DeckEvidence(job, "b").archive) == (True, True)


def old_row(iid, tier, days_ago):
    return {"impression_id": iid, "user_id": UID, "league_id": LEAGUE, "deck_job_id": "old",
            "card_index": 0, "features_json": "{}", "propensity": 1.0,
            "served_at": db_module.page_store_iso(time.time() - days_ago * 86400), "evidence_tier": tier}


def test_archive_retention_deletes_only_archive_rows_older_than_90_days(deferred, monkeypatch):
    _, engine, _ = deferred
    seeded = [old_row(f"{tier}-{age}", tier, age) for tier in (*TIERS, None) for age in (91, 89)]
    with engine.begin() as conn:
        conn.execute(insert(db_module.deck_impressions_table), seeded)
    monkeypatch.setattr(server, "_archive_purge_last", 0.0)
    server._purge_archive_evidence()
    assert {r["impression_id"] for r in rows(engine)} == {r["impression_id"] for r in seeded} - {"archive-91"}
    with engine.begin() as conn:                            # throttled: once an hour
        conn.execute(insert(db_module.deck_impressions_table), [old_row("archive-92", "archive", 92)])
    server._purge_archive_evidence()
    assert "archive-92" in {r["impression_id"] for r in rows(engine)}


def test_archive_retention_is_off_with_the_flag(deferred, monkeypatch):
    _, engine, _ = deferred
    with engine.begin() as conn:
        conn.execute(insert(db_module.deck_impressions_table), [old_row("archive-91", "archive", 91)])
    monkeypatch.setattr(ff, "_flags_cache", {**ff.flags_dict(), "trade.first_page_store": False})
    monkeypatch.setattr(server, "_archive_purge_last", 0.0)
    server._purge_archive_evidence()
    assert [r["impression_id"] for r in rows(engine)] == ["archive-91"]


# ── The budget rule ─────────────────────────────────────────────────────────

def test_the_budget_rule_shrinks_the_stored_evidence_blob(deferred):
    client, engine, _ = deferred
    job_id, _, ghosts, _, _ = deferred_deck(120, ghost_every=9)
    row = stored()
    blob = row["evidence_blob"]
    assert len(blob["rows"]) == row["card_count"] == 90 and len(blob["ghosts"]) == len(ghosts)
    assert blob["candidate_set"]["deck_job_id"] == job_id
    pages = len(db_module.CompressedJSON.encode(row["pages_blob"]))
    assert row["stored_bytes"] == pages + len(db_module.CompressedJSON.encode(blob))
    status(client, job_id, 0)
    row = stored()
    assert row["evidence_blob"] is None and row["stored_bytes"] == pages   # stage 1: all written


def test_the_budget_rule_keeps_exactly_the_snapshots_not_yet_written(deferred, monkeypatch):
    """If the rest of the deck fails to write, the blob keeps exactly the stored
    cards whose rows are missing; the written first 30, ghosts and candidate set go."""
    client, engine, _ = deferred
    job_id, *_ = deferred_deck(120, ghost_every=9)
    real = db_module.save_deck_evidence

    def flaky(rows_, **kw):
        if rows_ and rows_[0]["evidence_tier"] == "full_interim":
            raise RuntimeError("injected")
        return real(rows_, **kw)

    monkeypatch.setattr(db_module, "save_deck_evidence", flaky)
    status(client, job_id, 0)
    blob = stored()["evidence_blob"]
    assert sorted(r["card_index"] for r in blob["rows"]) == list(range(30, 90))
    assert blob["ghosts"] == [] and blob["candidate_set"] is None
    monkeypatch.setattr(db_module, "save_deck_evidence", real)
    status(client, job_id, 30)                             # the next delivery writes the rest
    assert stored()["evidence_blob"] is None
    written = by_index(engine)
    assert {written[(0, i)]["evidence_tier"] for i in range(30, 60)} == {"delivered"}
    assert {written[(0, i)]["evidence_tier"] for i in range(60, 120)} == {"full_interim"}


# ── Once the job has left the process ───────────────────────────────────────

def test_the_first_delivery_after_the_job_left_the_process_writes_from_the_blob(deferred):
    client, engine, _ = deferred
    job_id, served, ghosts, _, _ = deferred_deck(120, ghost_every=9)
    server._trade_jobs.clear()                             # restart, or the 4 h job eviction
    server._trade_jobs_by_key.clear()
    page1 = [c["impression_id"] for c in status(client, job_id, 0).get_json()["cards"]]
    written = by_index(engine)
    assert {written[(0, i)]["impression_id"] for i in range(30)} == set(page1)
    assert {written[(0, i)]["evidence_tier"] for i in range(30)} == {"delivered"}
    assert {written[(0, i)]["evidence_tier"] for i in range(30, 90)} == {"full_interim"}
    assert not any((0, i) in written for i in range(90, 120))   # only the lost job held them
    assert {k for k in written if k[0] == 1} == {(1, pos) for pos, _ in ghosts}
    assert len(rows(engine, db_module.deck_candidate_sets_table)) == 1
    assert stored()["evidence_blob"] is None
    page2 = [c["impression_id"] for c in status(client, job_id, 30).get_json()["cards"]]
    assert page2 and {tiers(engine)[iid] for iid in page2} == {"delivered"}


def test_evidence_built_before_an_account_deletion_is_never_written(deferred):
    client, engine, _ = deferred
    job_id, _, _, ev, _ = deferred_deck(40)
    with user_data_lifecycle.hold([UID]):
        user_data_lifecycle.invalidate([UID])
    server._deck_evidence_delivered(ev, server._trade_jobs[job_id]["cards"][:10])
    assert rows(engine) == []


# ── The evidence mode per path ──────────────────────────────────────────────

@pytest.mark.parametrize("kwargs,mode", [
    ({}, "deferred"),
    ({"force_fresh": True}, "deferred"),
    ({"pinned_give": ["g2"]}, "live"),
    ({"pinned_receive": ["r2"]}, "live"),
    ({"opponent_user_id": OPP}, "live"),
    ({"trade_intent": "consolidate"}, "live"),
    ({"presentation_exempt": True}, "live"),
    ({"source": "replenish"}, "live"),
])
def test_the_evidence_mode_per_path(deferred, kwargs, mode):
    _, engine, _ = deferred
    job_id = run_job(**kwargs)
    job = server._trade_jobs[job_id]
    assert job["evidence_mode"] == mode and ("evidence" in job) == (mode == "deferred")
    built = {r["deck_job_id"] for r in rows(engine)}
    assert job["cards"] and (job_id in built) == (mode == "live")


def test_a_value_core_job_keeps_live_evidence(deferred, monkeypatch):
    monkeypatch.setattr(server, "_value_core_live", lambda **kw: True)

    def value_core(*, job_id, **kw):
        server._finish_trade_job(job_id)
        return True

    monkeypatch.setattr(server, "_run_value_core_job", value_core)
    job = server._trade_jobs[run_job()]
    assert job["evidence_mode"] == "live" and "evidence" not in job


def test_flag_off_jobs_write_todays_rows_at_build(deferred, monkeypatch):
    client, engine, _ = deferred
    monkeypatch.setattr(ff, "_flags_cache", {**ff.flags_dict(), "trade.first_page_store": False})
    batches = []
    real = server.save_deck_impressions
    monkeypatch.setattr(server, "save_deck_impressions",
                        lambda batch: (batches.append(copy.deepcopy(batch)), real(batch))[1])
    job_id = run_job()
    job = server._trade_jobs[job_id]
    assert not {"evidence", "evidence_mode", "page_scope"} & set(job)
    written = rows(engine)
    assert job["cards"] and batches
    assert all("evidence_tier" not in r for batch in batches for r in batch)
    assert {r["impression_id"] for r in written} == {c["impression_id"] for c in job["cards"]}
    assert {r["evidence_tier"] for r in written} == {None}
    client.get(f"/api/trades/status?job_id={job_id}", headers=HEADERS)
    key = lambda r: r["impression_id"]
    assert sorted(rows(engine), key=key) == sorted(written, key=key)


def test_deferred_rows_are_the_rows_the_logger_writes_live(deferred):
    """The same deck through the same logger: written at build (live), or
    assembled and written at delivery (deferred). Equal row for row but the
    per-run identities, served_at and evidence_tier; ghosts narrowed."""
    client, engine, _ = deferred
    cards, players = synthetic_cards(66)
    ghosts = [(pos, c) for pos, c in enumerate(cards) if pos % 10 == 9]
    ghost_ids = {id(c) for _, c in ghosts}
    served = [c for c in cards if id(c) not in ghost_ids]

    def log(sink):
        return server._log_deck_signal_impressions(
            user_id=UID, league_id=LEAGUE, job_id="same-deck", cards=served, players_dict=players,
            capture=None, scoring_format="1qb_ppr", ghost_cards=ghosts, candidate_pool=[],
            policy_version="pv-test", **({"evidence_sink": sink} if sink else {}))

    log(None)
    live_rows = by_index(engine)
    with engine.begin() as conn:
        conn.execute(delete(db_module.deck_impressions_table))
        conn.execute(delete(db_module.deck_candidate_sets_table))
    ev = server._DeckEvidence("same-deck", UID)
    log(ev)
    ev.seal()
    ev.complete = True
    assert rows(engine) == []
    server._deck_evidence_delivered(ev, [{"impression_id": iid} for iid in list(ev.rows)[:10]])
    deferred_rows = by_index(engine)
    assert set(deferred_rows) == set(live_rows)
    strip = lambda r: {k: v for k, v in r.items() if k not in VOLATILE}
    for key, live_row in live_rows.items():
        if key[0] == 1:
            narrow = server._narrow_ghost_row(live_row)
            assert strip(deferred_rows[key]) == {**strip(narrow), "valuation_json": None}
        else:
            assert strip(deferred_rows[key]) == strip(live_row)


# ── The real owner path: structured features, batch publication ────────────

def owner_deck(fixture, monkeypatch, *, deferred_mode):
    """test_owner_generator_routes' worker (the real owner worker over a real
    owner deck), with the job deferred when asked, then its completion step."""
    engine = fixture[1]
    ev = server._DeckEvidence("owner-route-worker", ME) if deferred_mode else None
    real = server._run_trade_job

    def run(job_id, *args, **kwargs):
        if ev is not None:
            server._trade_jobs[job_id].update(evidence_mode="deferred", evidence=ev)
        return real(job_id, *args, **kwargs)

    monkeypatch.setattr(server, "_run_trade_job", run)
    job = worker(fixture, monkeypatch)
    monkeypatch.setattr(server, "_run_trade_job", real)
    server._deck_evidence_job_done(job["job_id"])
    return job, ev, engine


def owner_rows(engine):
    out = {}
    for r in rows(engine):
        r = dict(r)
        out[r["card_index"]] = r
    return out


@pytest.mark.parametrize("sized_exclusive", [160], indirect=True)
def test_the_owner_path_publishes_without_commits_and_writes_nothing_until_delivery(
        sized_exclusive, monkeypatch):
    fixture, count = sized_exclusive
    monkeypatch.setattr(server, "_start_deck_evidence_thread", lambda *, target, args: target(*args))
    published = []
    real_publish_log = server._log_deck_signal_impressions

    def observe(**kwargs):
        on_batch = kwargs["on_batch_committed"]

        def committed(batch, identities):
            assert rows(fixture[1]) == []                  # nothing committed, still published
            on_batch(batch, identities)
            published.append(len(batch))
        return real_publish_log(**{**kwargs, "on_batch_committed": committed})

    monkeypatch.setattr(server, "_log_deck_signal_impressions", observe)
    job, ev, engine = owner_deck(fixture, monkeypatch, deferred_mode=True)
    assert published == [30, 100, 30] and len(job["cards"]) == count
    assert rows(engine) == [] and rows(engine, db_module.deck_diagnostic_snapshots_table) == []
    assert {c["impression_id"] for c in job["cards"]} == set(ev.rows)
    server._trade_job_public_view(dict(job))               # a legacy poll delivers every card
    written = owner_rows(engine)
    assert len(written) == count and {r["evidence_tier"] for r in written.values()} == {"delivered"}
    assert all(r["valuation_json"] for r in written.values())


@pytest.mark.parametrize("sized_exclusive", [64], indirect=True)
def test_owner_rows_written_at_delivery_equal_the_rows_written_live(sized_exclusive, monkeypatch):
    fixture, count = sized_exclusive
    monkeypatch.setattr(server, "_start_deck_evidence_thread", lambda *, target, args: target(*args))
    _, _, engine = owner_deck(fixture, monkeypatch, deferred_mode=False)
    live = owner_rows(engine)
    live_diag = rows(engine, db_module.deck_diagnostic_snapshots_table)
    with engine.begin() as conn:
        for table in (db_module.deck_impressions_table, db_module.deck_diagnostic_snapshots_table,
                      db_module.deck_candidate_sets_table):
            conn.execute(delete(table))
    job, ev, _ = owner_deck(fixture, monkeypatch, deferred_mode=True)
    assert rows(engine) == []
    server._deck_evidence_delivered(ev, job["cards"][:10])
    deferred_rows = owner_rows(engine)
    assert len(deferred_rows) == len(live) == count
    deferred_diag = rows(engine, db_module.deck_diagnostic_snapshots_table)

    def comparable(row, diag):
        """The row with its diagnostics expanded; the one per-run value, the
        owner request's capture clock, set aside (it differs between runs)."""
        from backend.deck_diagnostics import expand_features
        out = {k: v for k, v in row.items() if k not in VOLATILE}
        features = expand_features(json.loads(row["features_json"]),
                                   {d["snapshot_id"]: d["payload_json"] for d in diag})
        features["owner_request"].pop("captured_at")
        out["features_json"] = features
        return out

    assert ({i: comparable(r, deferred_diag) for i, r in deferred_rows.items()}
            == {i: comparable(r, live_diag) for i, r in live.items()})
    assert ([r["evidence_tier"] for _, r in sorted(deferred_rows.items())]
            == ["delivered"] * 10 + ["first30"] * 20 + ["full_interim"] * (count - 30))
    assert len(deferred_diag) == len(live_diag)
    for r in deferred_rows.values():                       # every reference resolves
        assert "expired_or_missing" not in json.dumps(db_module.load_deck_diagnostics(r["impression_id"], ME))


# ── Measured: evidence_blob bytes for a production-size deck ───────────────

def kib(n):
    return f"{n / 1024:.1f} KiB"


@pytest.mark.parametrize("sized_exclusive", [2354], indirect=True)   # B15's measured production deck
def test_measured_evidence_blob_bytes_for_a_production_size_owner_deck(sized_exclusive, monkeypatch):
    """The real owner path (structured features, owner valuation evidence) with
    the candidate set on: the stored row's bytes (pages + evidence_blob) before
    and after page 1's delivery, against scope §7's ≤ ~0.2 MB per pair."""
    fixture, count = sized_exclusive
    monkeypatch.setattr(server, "_start_deck_evidence_thread", lambda *, target, args: target(*args))
    original = server._ghost_holdout_active

    def telemetry_on(*args):                               # the worker helper turns it off
        monkeypatch.setattr(server, "_suggestion_telemetry_enabled", lambda: True)
        return original(*args)

    monkeypatch.setattr(server, "_ghost_holdout_active", telemetry_on)
    started = time.perf_counter()
    job, ev, engine = owner_deck(fixture, monkeypatch, deferred_mode=True)
    build_s = time.perf_counter() - started
    assert len(job["cards"]) == count and ev.candidate_set is not None and rows(engine) == []
    stored_cards = job["cards"][:90]
    stored_ids = {c["impression_id"] for c in stored_cards}
    pages = db_module.CompressedJSON.encode({"v": 1, "opponents_total": 0, "cards": stored_cards})
    deck = held(ev)
    with ev.lock:
        ev.stored_ids = stored_ids
        ev.stored_count = len(stored_cards)
        ev.pages_bytes = len(pages)
        before = ev.blob()
        held_z = sum(len(packed) for _, packed in ev.rows.values())
    held_raw = sum(len(json.dumps(r)) for r in deck.values())
    stored_rows = [r for iid, r in deck.items() if iid in stored_ids]
    rest_of_stored = db_module.CompressedJSON.encode([r for r in stored_rows if r["card_index"] >= 30])
    blob = json.loads(zlib.decompress(before))
    parts = {name: len(db_module.CompressedJSON.encode(blob[name]))
             for name in ("rows", "diagnostics", "candidate_set", "trade_impressions", "generated")}
    run_row = server._unpack_row(ev.bakeoff_run)            # held in process, never in the blob
    run_raw, run_z = len(json.dumps(run_row)), len(ev.bakeoff_run)
    row_raw = statistics_mean([len(json.dumps(r)) for r in deck.values()])
    varied = db_module.CompressedJSON.encode(vary(blob, random.Random(20261020)))
    diag_count = len(ev.diagnostics)
    with ev.lock:   # F5: the payload held in process from build to the first delivery
        peak = {"rows (packed)": held_z,
                "diagnostics": sum(len(d["payload_json"]) for d in ev.diagnostics.values()),
                "ghosts": sum(len(json.dumps(g)) for g in ev.ghosts.values()),
                "candidate set": len(json.dumps(ev.candidate_set)),
                "trade_impressions (packed)": len(ev.trade_impressions),
                "bakeoff_runs row (packed)": len(ev.bakeoff_run)}
    started = time.perf_counter()
    server._deck_evidence_delivered(ev, job["cards"][:30])
    write_s = time.perf_counter() - started
    with ev.lock:
        after = ev.blob()
    print(f"\n[evidence measure] owner deck cards={count} build_s={build_s:.1f} write_s={write_s:.2f} "
          f"mean_row_raw={row_raw:.0f} B\n"
          f"  pages_blob (90 cards)            {kib(len(pages))}\n"
          f"  evidence_blob before delivery    {kib(len(before))} (rows {kib(parts['rows'])}, "
          f"diagnostics {kib(parts['diagnostics'])} x{len(blob['diagnostics'])}, "
          f"candidate set {kib(parts['candidate_set'])}, trade_impressions {kib(parts['trade_impressions'])}, "
          f"trades_generated {kib(parts['generated'])})\n"
          f"  bakeoff_runs row (in process only) raw {run_raw / 2**20:.1f} MiB, packed {kib(run_z)}\n"
          f"  per pair before delivery         {kib(len(pages) + len(before))}\n"
          f"  evidence_blob before, varied     {kib(len(varied))} (every value randomized: an upper bound)\n"
          f"  evidence_blob after page 1       {kib(len(after or b''))} (stage 1: every row written)\n"
          f"  per pair after page 1            {kib(len(pages) + len(after or b''))}\n"
          f"  packing-stage proxy after page 1 {kib(len(rest_of_stored))} (stored rows 30-89 only)\n"
          f"  in-process rows held (whole deck) raw {held_raw / 2**20:.1f} MiB, "
          f"packed {held_z / 2**20:.1f} MiB, diagnostics {diag_count} snapshots\n"
          f"  peak in-process payload          {sum(peak.values()) / 2**20:.1f} MiB "
          f"({', '.join(f'{k} {v / 2**20:.2f}' for k, v in peak.items())} MiB)")
    assert after is None and len(rows(engine)) == count
    with ev.lock:   # F5: freed once written
        assert (ev.rows, ev.ghosts, ev.diagnostics, ev.by_hash, ev.candidate_set,
                ev.trade_impressions, ev.bakeoff_run, ev.generated) == (
                    {}, {}, {}, {}, None, None, None, None)
    assert len(pages) + len(before) <= 200_000                # scope §7: ≤ about 0.2 MB per pair


def statistics_mean(values):
    return sum(values) / len(values)


def vary(value, rng, key=None):
    """The same JSON shape with values drawn at random (nested JSON strings
    too): numbers, ids, hashes and names unique per card, short enum strings
    kept. Much less compressible than any real deck."""
    if isinstance(value, dict):
        return {k: vary(v, rng, k) for k, v in value.items()}
    if isinstance(value, list):
        return [vary(v, rng) for v in value]
    if isinstance(value, bool) or value is None or key in ("card_index", "v", "evidence_tier"):
        return value
    if isinstance(value, float):
        return round(rng.uniform(0, 10000), 3)
    if isinstance(value, int):
        return rng.randint(0, 10 ** 6)
    if isinstance(value, str):
        if value[:1] in "[{":
            try:
                return json.dumps(vary(json.loads(value), rng))
            except ValueError:
                pass
        return value if len(value) <= 6 else "".join(rng.choice("0123456789abcdef") for _ in value)
    return value
