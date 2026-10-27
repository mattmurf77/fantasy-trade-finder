"""The per-deck evidence lock (`ev.lock`) holds only a snapshot.

The store's evidence_blob, the shrink after a delivery's writes and a write's
plan are built from an input taken under `ev.lock` by reference
(_DeckEvidence.blob_input / plan_input), then decoded, planned and encoded
outside it (_deck_blob / _deck_plan), so a next page's delivery, which marks
its cards under `ev.lock` alone, never waits on them. Their results still go
to the DB under _deck_evidence_write_lock, as before.

Pins: no unpacking, closure or encoding while `ev.lock` is held, during a store
and a first delivery (packed and stage 1); the blob bytes and the plan equal
the pre-change implementation's (kept verbatim below as the reference) for
the same deck state; a delivery racing the store's encoding, or a write's plan,
lands (no lost boundary, no stale blob row).

Harness: test_packed_evidence's (the `deferred` fixture, real routes and
evidence writes inline).
"""
import json
import threading
import time

import pytest

import backend.database as db_module
import backend.server as server
from backend.tests.test_i1_serve_filter import live  # noqa: F401  (fixture)
from backend.tests.test_trade_page_store import p1, status, stored  # noqa: F401  (fixture)
from backend.tests.test_deferred_evidence import (  # noqa: F401  (fixture)
    archive_id, deferred, deferred_deck, rows)
from backend.tests.test_packed_evidence import deck_ids, pack_of, packed_deck, unpack


# ── The pre-change implementation, verbatim: the byte-identity reference ────

def old_closure(ev, rows, exclude=()):
    pending = set().union(*(server._diagnostic_refs(json.loads(r["features_json"] or "null"))
                            for r in rows))
    found = {}
    while pending:
        sid = pending.pop()
        if sid in ev.diagnostics and sid not in found and sid not in exclude:
            found[sid] = server._unpack_row(ev.diagnostics[sid])
            pending |= server._diagnostic_refs(json.loads(found[sid]["payload_json"]))
    return list(found.values())


def old_plan(ev):
    _unpack_row, first_n = server._unpack_row, server._EVIDENCE_FIRST_N
    at = {iid: ev.delivered_at[h] for h in ev.delivered_hashes for iid in ev.by_hash.get(h, ())}
    at.update((iid, ev.delivered_at[iid]) for iid in ev.delivered)
    delivered = at.keys()
    for iid in ev.withdrawn - delivered:
        ev.rows.pop(iid, None)
    if ev.partial:
        first = [{**_unpack_row(packed), "evidence_tier": "partial_run", "delivered_at": at[iid]}
                 for iid, (_, packed) in ev.rows.items() if iid in delivered]
        first += [{**row, "evidence_tier": "partial_run", "delivered_at": None}
                  for row in ev.ghosts.values()]
        return (first, old_closure(ev, first)), ([], []), ev.candidate_set, {}
    if ev.packed:
        first = [{**_unpack_row(packed),
                  "evidence_tier": "first30" if index < first_n else "archive",
                  "delivered_at": at.get(iid)}
                 for iid, (index, packed) in ev.rows.items() if index < first_n or ev.archive]
        first += [{**row, "evidence_tier": "ghost", "delivered_at": None}
                  for row in ev.ghosts.values()]
        upgrades = {iid: at[iid] for iid in sorted(delivered - ev.marked) if iid in ev.written}
        return (first, old_closure(ev, first)), ([], []), ev.candidate_set, upgrades
    first, rest = [], []
    for iid, (index, packed) in ev.rows.items():
        if index < first_n:
            first.append({**_unpack_row(packed), "evidence_tier": "first30",
                          "delivered_at": at.get(iid)})
        elif iid in delivered:
            first.append({**_unpack_row(packed), "evidence_tier": "delivered",
                          "delivered_at": at[iid]})
        else:
            rest.append({**_unpack_row(packed), "delivered_at": None,
                         "evidence_tier": "archive" if ev.archive else "full_interim"})
    first += [{**row, "evidence_tier": "ghost", "delivered_at": None} for row in ev.ghosts.values()]
    upgrades = {iid: at[iid] for iid in sorted(delivered - ev.marked - ev.rows.keys())}
    first_diag = old_closure(ev, first)
    rest_diag = old_closure(ev, rest, exclude={d["snapshot_id"] for d in first_diag})
    return (first, first_diag), (rest, rest_diag), ev.candidate_set, upgrades


def old_blob(ev, stored_count=None):
    if stored_count is None:
        stored_count = ev.stored_count
    rows = [server._unpack_row(packed) for iid, (_, packed) in ev.rows.items()
            if ev.stored_ids is None or iid in ev.stored_ids]
    held = ev.trade_impressions or ev.generated or ev.bakeoff_slim
    if not (rows or ev.ghosts or ev.candidate_set or held):
        return None
    impressions = None
    if ev.trade_impressions is not None:
        impressions = server._unpack_row(ev.trade_impressions)
        impressions["cards"] = impressions["cards"][:stored_count]
    return db_module.CompressedJSON.encode({
        "v": server._EVIDENCE_BLOB_FORMAT, "deck_job_id": ev.job_id,
        "pages_bytes": ev.pages_bytes, "rows": rows,
        "ghosts": list(ev.ghosts.values()), "diagnostics": old_closure(ev, rows),
        "candidate_set": ev.candidate_set, "trade_impressions": impressions,
        "bakeoff_run": ev.bakeoff_slim,
        "generated": ev.generated, "served_at": ev.served_at,
        "truncated": ev.truncated,
        "packed": ev.packed, "page_store": ev.page_store, "league_id": ev.league_id,
        "built_at": ev.built_at, "run_meta": ev.run_meta,
        "pack_written": ev.pack is not None, "deck_source": ev.deck_source})


# ── Helpers ─────────────────────────────────────────────────────────────────

class _HeldLock:
    """ev.lock, knowing which thread holds it."""

    def __init__(self, lock):
        self.lock, self.owner = lock, None

    def __enter__(self):
        self.lock.acquire()
        self.owner = threading.get_ident()
        return self

    def __exit__(self, *exc):
        self.owner = None
        self.lock.release()

    def mine(self):
        return self.owner == threading.get_ident()


def build(kind):
    """An unstored, complete deck of 120 cards (a ghost after every 9th)."""
    if kind == "packed":
        return packed_deck(120, ghost_every=9, store=False)
    if kind == "archive":
        return deferred_deck(120, ghost_every=9, store=False, job_id=archive_id(True))
    return deferred_deck(120, ghost_every=9, store=False)


# ── No heavy work under ev.lock ─────────────────────────────────────────────

@pytest.mark.parametrize("kind", ["packed", "stage1"])
def test_no_unpacking_closure_or_encoding_while_ev_lock_is_held(deferred, monkeypatch, kind):
    """A store and a first delivery: every row unpack, snapshot closure and
    blob encode runs with `ev.lock` free (and each does run)."""
    client, engine, _ = deferred
    job_id, _served, _ghosts, ev, _players = build(kind)
    lock = _HeldLock(ev.lock)
    ev.lock = lock
    calls = {"unpack": [], "closure": [], "encode": []}

    def watch(name, fn):
        def watched(*args, **kwargs):
            calls[name].append(lock.mine())
            return fn(*args, **kwargs)
        return watched
    monkeypatch.setattr(server, "_unpack_row", watch("unpack", server._unpack_row))
    monkeypatch.setattr(server, "_diagnostic_closure", watch("closure", server._diagnostic_closure))
    monkeypatch.setattr(db_module.CompressedJSON, "encode",
                        staticmethod(watch("encode", db_module.CompressedJSON.encode)))
    assert server._store_trade_page(job_id)
    assert deck_ids(status(client, job_id, 0).get_json())   # the first delivery: the first write
    assert all(calls.values()), {k: len(v) for k, v in calls.items()}   # each ran
    assert not any(any(v) for v in calls.values()), {k: sum(v) for k, v in calls.items()}


# ── Byte for byte the old path's ────────────────────────────────────────────

@pytest.mark.parametrize("kind", ["packed", "stage1", "archive"])
def test_the_blob_bytes_and_the_plan_equal_the_old_paths(deferred, monkeypatch, kind):
    """For the same deck state (each input taken in the same `ev.lock`
    section as the reference): the store's blob, the shrink's blob after the
    first and second deliveries, and each delivery's plan equal the
    pre-change implementation's, byte for byte and row for row."""
    client, engine, _ = deferred
    job_id, _served, _ghosts, ev, _players = build(kind)
    blobs, plans = [], []
    real_blob_input, real_plan_input = ev.blob_input, ev.plan_input

    def blob_input(stored_count=None):
        snapshot = real_blob_input(stored_count)
        blobs.append((snapshot, old_blob(ev, stored_count)))
        return snapshot

    def plan_input():
        reference = old_plan(ev)                           # pops the C-b drops first, as before
        plans.append((real_plan_input(), reference))
        return plans[-1][0]
    monkeypatch.setattr(ev, "blob_input", blob_input)
    monkeypatch.setattr(ev, "plan_input", plan_input)
    assert server._store_trade_page(job_id)
    for cursor in (0, 30):
        assert deck_ids(status(client, job_id, cursor).get_json())
    assert len(blobs) >= 2 and len(plans) >= 2
    assert blobs[0][1] is not None and plans[0][1][0][0]   # a real blob, a real first write
    for snapshot, reference in blobs:
        assert server._deck_blob(snapshot) == reference
    for snapshot, reference in plans:
        assert server._deck_plan(snapshot) == reference


def _ref(sid):
    from backend.deck_diagnostics import REFERENCE_KEY
    return {REFERENCE_KEY: sid}


def hand_built(kind):
    """A deck whose rows and ghosts reference shared diagnostic snapshots
    (chained: d-c -> d-a -> d-b), with held build-time writes, part of it
    stored, three cards delivered (one already written), one withdrawn."""
    ev = server._DeckEvidence("deck-hand", "user-hand")
    ev.diagnostics = {
        sid: server._pack_row({"snapshot_id": sid, "payload_json": json.dumps(
            {"nested": [_ref(r) for r in refs]})})
        for sid, refs in (("d-a", ["d-b"]), ("d-b", []), ("d-c", ["d-a"]), ("d-z", []))}
    for i in range(60):
        iid = f"deck-hand:{i}"
        row = {"impression_id": iid, "card_index": i, "served_at": "2026-10-27T00:00:00+00:00",
               "features_json": json.dumps({"debug": _ref("d-c" if i >= 30 else "d-b"), "i": i})}
        ev.rows[iid] = (i, server._pack_row(row))
    ev.ghosts = {"g-1": {"impression_id": "g-1", "is_ghost": 1,
                         "features_json": json.dumps({"debug": _ref("d-a")})}}
    ev.candidate_set = {"candidate_set_id": "cs-1", "deck_job_id": "deck-hand"}
    ev.trade_impressions = server._pack_row({"league_id": "L", "cards": [{"n": i} for i in range(60)]})
    ev.generated = {"league_id": "L", "props": {"count": 60}}
    ev.stored_ids, ev.stored_count, ev.pages_bytes = {f"deck-hand:{i}" for i in range(45)}, 45, 1234
    ev.delivered = {"deck-hand:3", "deck-hand:31", "deck-hand:40"}
    ev.delivered_at = {iid: "2026-10-27T00:01:00+00:00" for iid in ev.delivered}
    ev.withdrawn, ev.written = {"deck-hand:50"}, {"deck-hand:31"}
    ev.run_meta = {"values_snapshot_id": "v", "config_ref": "c"}
    ev.packed, ev.archive, ev.partial = kind == "packed", kind == "archive", kind == "partial"
    return ev


@pytest.mark.parametrize("kind", ["stage1", "packed", "archive", "partial"])
def test_a_hand_built_decks_blob_and_plan_equal_the_old_paths(kind):
    """Shared, chained snapshots (the rest's closure excludes the first's), a
    truncated trade_impressions (45 of 60 stored) and a C-b drop: the same
    bytes, the same plan."""
    ev = hand_built(kind)
    with ev.lock:
        reference_blob = old_blob(ev, 45)
        snapshot = ev.blob_input(45)
    assert server._deck_blob(snapshot) == reference_blob
    with ev.lock:
        reference = old_plan(ev)                           # pops the withdrawn card first
        plan_input = ev.plan_input()
    assert server._deck_plan(plan_input) == reference
    if kind == "stage1":
        (first, first_diag), (rest, rest_diag), _cs, _up = reference
        assert first_diag and rest and not rest_diag       # the rest's snapshots were the first's


def test_a_partial_runs_plan_equals_the_old_paths(deferred, monkeypatch):
    """A run that ended partial (a timeout) after its first 30 went out."""
    job_id, _served, _ghosts, ev, _players = deferred_deck(40, ghost_every=9, store=False,
                                                           complete=False)
    plans = []
    real_plan_input = ev.plan_input

    def plan_input():
        reference = old_plan(ev)
        plans.append((real_plan_input(), reference))
        return plans[-1][0]
    monkeypatch.setattr(ev, "plan_input", plan_input)
    server._deck_evidence_delivered(ev, server._trade_jobs[job_id]["cards"][:30])
    with server._trade_jobs_lock:
        server._trade_jobs[job_id].update(status="error", error="timeout")
    server._deck_evidence_job_done(job_id)
    [(snapshot, reference)] = plans
    assert {r["evidence_tier"] for r in reference[0][0]} == {"partial_run"}
    assert server._deck_plan(snapshot) == reference


# ── A delivery racing the store or the plan ─────────────────────────────────

@pytest.fixture()
def shared_db(deferred, monkeypatch):
    """`deferred`, with its in-memory DB reachable from a second thread: its one
    sqlite connection behind a StaticPool (the fixture's pool gives each
    thread a new, empty in-memory DB). The racing serve's deck_i1_check emit is
    stubbed: its own thread would write mid-transaction on the shared
    connection."""
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    client, engine, sess = deferred
    with engine.connect() as conn:
        raw = conn.connection.dbapi_connection
    shared = create_engine("sqlite://", creator=lambda: raw, poolclass=StaticPool)
    monkeypatch.setattr(db_module, "engine", shared)
    monkeypatch.setattr(server, "_emit_deck_i1_check", lambda *a, **k: None)
    return client, shared, sess


def racing_delivery(client, job_id, cursor, ev, arrived):
    """Serve page `cursor` on another thread; `arrived` is set once its
    delivery is marked on `ev` (under ev.lock alone)."""
    def serve():
        status(client, job_id, cursor)
    thread = threading.Thread(target=serve, name=f"race-{cursor}")
    thread.start()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and not arrived():
        time.sleep(0.005)
    return thread


def test_a_delivery_racing_the_stores_encoding_lands_and_shrinks_the_blob(shared_db, monkeypatch):
    """While the store encodes its blob (outside ev.lock, inside the write
    lock), the first page is served: its delivery is marked at once, its write
    waits for the store and lands after it, and the stored blob then holds no
    row it wrote (packed: the first 30 are written, rows 30..89 stay)."""
    client, engine, _ = shared_db
    job_id, _served, _ghosts, ev, _players = packed_deck(120, store=False)
    real_blob = server._deck_blob
    race = {}

    def blob(snapshot):
        if "thread" not in race:
            race["thread"] = racing_delivery(client, job_id, 0, ev, lambda: bool(ev.delivered))
            race["marked_while_encoding"] = bool(ev.delivered)
        return real_blob(snapshot)
    monkeypatch.setattr(server, "_deck_blob", blob)
    assert server._store_trade_page(job_id)
    race["thread"].join(10)
    assert race["marked_while_encoding"]                   # ev.lock was free while encoding
    run = unpack(pack_of(engine, job_id))[0]
    assert [d[0] for d in run["deliveries"]] == [29]
    written = {r["impression_id"] for r in rows(engine) if not r["is_ghost"]}
    blob_rows = {r["impression_id"] for r in stored()["evidence_blob"]["rows"]}
    assert len(written) == 30 and not written & blob_rows
    assert sorted(r["card_index"] for r in stored()["evidence_blob"]["rows"]) == list(range(30, 90))


def test_a_delivery_racing_a_writes_plan_keeps_its_boundary(shared_db, monkeypatch):
    """While the first delivery's write builds its plan (outside ev.lock), page
    2 is served: its boundary is recorded at once, and once the first write
    lands its header write adds it. No boundary is lost."""
    client, engine, _ = shared_db
    job_id, _served, _ghosts, ev, _players = packed_deck(120)
    real_plan = server._deck_plan
    race = {}

    def plan(snapshot):
        if "thread" not in race:
            race["thread"] = racing_delivery(
                client, job_id, 30, ev, lambda: any(d[0] == 59 for d in ev.deliveries))
            race["marked_while_planning"] = any(d[0] == 59 for d in ev.deliveries)
        return real_plan(snapshot)
    monkeypatch.setattr(server, "_deck_plan", plan)
    assert deck_ids(status(client, job_id, 0).get_json())
    race["thread"].join(10)
    assert race["marked_while_planning"]                   # ev.lock was free while planning
    run = unpack(pack_of(engine, job_id))[0]
    assert [d[0] for d in run["deliveries"]] == [29, 59]
    assert sorted(r["card_index"] for r in rows(engine) if not r["is_ghost"]) == list(range(30))
