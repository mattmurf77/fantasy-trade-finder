"""models-lead addendum D2: the worker keeps the quality filter's inputs on
the deck's evidence (never on the job, whose shape stays as it was), and job
done carries them into the pack's run header (`run["filter_inputs"]`), a
per-run part written once. Harness: test_packed_evidence's (the `deferred`
fixture: real synchronous organic jobs with deferred evidence)."""
import pytest

import backend.server as server
from backend import deck_quality
from backend.tests.test_i1_serve_filter import live  # noqa: F401  (fixture)
from backend.tests.test_trade_page_store import p1, run_job, status, stored  # noqa: F401
from backend.tests.test_deferred_evidence import deferred  # noqa: F401  (fixture)
from backend.tests.test_packed_evidence import pack_of, packed_deck, unpack


def _filters_on(monkeypatch):
    monkeypatch.setattr(server, "_deck_quality_filters_enabled", lambda: True)


def _evidence_of(job_id):
    with server._trade_jobs_lock:
        job = server._trade_jobs[job_id]
        return job, job["evidence"]


def test_the_worker_records_the_inputs_its_filter_used(deferred, monkeypatch):
    """A real worker: the recorded values reproduce the filter's decisions (every
    kept card passes breakup and filler on them), and the job's own keys never
    gain it."""
    _filters_on(monkeypatch)
    job, ev = _evidence_of(run_job())
    inputs = ev.filter_inputs
    assert inputs["filter_ran"] is True and inputs["v"] == 1
    assert "filter_inputs" not in job
    market = inputs["market"]
    for card in job["cards"]:
        give = [p["id"] for p in card["give"]]
        receive = [p["id"] for p in card["receive"]]
        assert set(give + receive) <= set(market)
        assert not deck_quality._breakup(give, receive, market.get)
        assert not deck_quality._filler(give, receive, market.get)


def test_flag_off_records_that_the_filter_never_ran(deferred, monkeypatch):
    monkeypatch.setattr(server, "_deck_quality_filters_enabled", lambda: False)
    _job, ev = _evidence_of(run_job())
    assert ev.filter_inputs == {"v": 1, "filter_ran": False}


def test_a_failed_filter_records_that_it_never_ran(deferred, monkeypatch):
    _filters_on(monkeypatch)
    monkeypatch.setattr(deck_quality, "filter_deck",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("filter")))
    _job, ev = _evidence_of(run_job())
    assert ev.filter_inputs == {"v": 1, "filter_ran": False}


def test_a_failed_record_never_unfilters_the_deck(deferred, monkeypatch):
    """Provenance can't change the deck: the filter's output is served and the
    run says it ran, with no inputs (the audit reads it as not auditable)."""
    _filters_on(monkeypatch)
    real = deck_quality.filter_deck

    def first_only(cards, **kw):
        out, counts = real(cards, **kw)
        return out[:1], counts
    monkeypatch.setattr(deck_quality, "filter_deck", first_only)
    monkeypatch.setattr(server, "_quality_filter_inputs",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("record")))
    job, ev = _evidence_of(run_job())
    assert ev.filter_inputs == {"v": 1, "filter_ran": True}
    assert len(job["cards"]) <= 1


def test_the_pack_run_header_carries_it(deferred, monkeypatch):
    """A real packed job: job done copies the evidence's record into the run
    metadata, and the first delivery writes it in the pack's run header."""
    _filters_on(monkeypatch)
    real = server.is_enabled
    monkeypatch.setattr(server, "is_enabled",
                        lambda key, *a, **k: True if key == "trade.packed_evidence" else real(key, *a, **k))
    client, engine, _ = deferred
    job_id = run_job()
    job, ev = _evidence_of(job_id)
    assert ev.packed and ev.filter_inputs["filter_ran"] is True
    assert ev.run_meta["filter_inputs"] == ev.filter_inputs
    status(client, job_id, 0)
    run, _cards = unpack(pack_of(engine, job_id))
    assert run["filter_inputs"] == ev.filter_inputs


def test_a_deck_without_a_record_has_none_in_its_header(deferred):
    """A deck from before D2 (no record on its evidence) writes none: absent
    means not recorded, never a run the filter skipped."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(40)
    _job, ev = _evidence_of(job_id)
    with ev.lock:
        ev.run_meta.pop("filter_inputs", None)
    status(client, job_id, 0)
    run, _cards = unpack(pack_of(engine, job_id))
    assert "filter_inputs" not in run



# ── #492 QA follow-ups: only with deferred evidence; the record against the
# filter's own call (QA's sabotage probes, ported); repeat_head ─────────────

def _spy_filter(monkeypatch):
    """Every deck_quality.filter_deck call the worker makes: its kwargs, the
    cards it returned and its counts."""
    calls = []
    real = deck_quality.filter_deck

    def spy(cards, **kw):
        out, counts = real(cards, **kw)
        calls.append({**kw, "in": list(cards), "out": list(out), "counts": dict(counts)})
        return out, counts
    monkeypatch.setattr(deck_quality, "filter_deck", spy)
    return calls


def test_a_deck_without_deferred_evidence_never_builds_the_record(deferred, monkeypatch):
    """#492 QA P3-1: it would be thrown away, so it isn't computed; the deck
    is still filtered."""
    _filters_on(monkeypatch)
    calls = _spy_filter(monkeypatch)
    built = []
    real = server._quality_filter_inputs
    monkeypatch.setattr(server, "_quality_filter_inputs",
                        lambda *a, **k: built.append(1) or real(*a, **k))
    monkeypatch.setattr(server, "_trade_page_store_enabled", lambda: False)
    job_id = run_job()
    with server._trade_jobs_lock:
        job = server._trade_jobs[job_id]
    assert job.get("evidence") is None and calls and built == []


@pytest.mark.parametrize("cap", [None, 1], ids=["default_cap", "cap_1_reorders"])
def test_the_record_is_exactly_what_the_filter_was_handed(deferred, monkeypatch, cap):
    """#492 QA P3-3 (QA's probe S1-S9): built from the cards the filter
    RETURNED, with the very callables it was given, so a record taken from
    the pre-filter cards or another market callable fails here, not only on
    the digest pin."""
    _filters_on(monkeypatch)
    if cap is not None:                   # the cap defers, so the order it returns differs
        monkeypatch.setattr(deck_quality, "REPEAT_CAP", cap)
    calls = _spy_filter(monkeypatch)
    handed = []
    real = server._quality_filter_inputs

    def record(cards, **kw):
        handed.append((cards, kw))
        return real(cards, **kw)
    monkeypatch.setattr(server, "_quality_filter_inputs", record)
    job, ev = _evidence_of(run_job())
    rec = ev.filter_inputs
    [call] = calls
    out = call["out"]
    assert rec["filter_ran"] is True and "filter_inputs" not in job
    # The record is built from the very objects the filter used: its returned
    # cards (identity, in order), its callables and rosters, its viewer and
    # its deferred count (the harness's markets are all unseeded, so values
    # alone couldn't tell another callable apart).
    [(cards, kw)] = handed
    if cap is not None:
        assert [id(c) for c in call["in"]] != [id(c) for c in out], "the probe needs a reorder"
    assert [id(c) for c in cards] == [id(c) for c in out]
    assert all(kw[k] is call[k] for k in ("market", "position", "rosters", "lineup_slots"))
    assert (kw["viewer_team"], kw["deferred"]) == (call["viewer_id"], call["counts"]["deferred"])
    teams = {call["viewer_id"]} | {str(c.target_user_id) for c in out}
    assert set(rec["qb_te"]) == teams & set(call["rosters"])
    for team, held in rec["qb_te"].items():
        assert held == [str(a) for a in call["rosters"][team] if call["position"](a) in ("QB", "TE")]
    assets = {str(a) for c in out for a in (*c.give_player_ids, *c.receive_player_ids)}
    holdings = {a for held in rec["qb_te"].values() for a in held}
    assert set(rec["market"]) == assets | holdings == set(rec["position"])
    for a, v in rec["market"].items():
        want = call["market"](a)
        assert v == (None if want is None else float(want)), a
        assert rec["position"][a] == call["position"](a), a
    assert rec["protected"] == sorted({
        server._deck_trade_hash(c.give_player_ids, c.receive_player_ids, c.target_user_id)
        for c in out if deck_quality.is_protected(c)})
    assert rec["lineup_slots"] == (None if call["lineup_slots"] is None
                                   else list(call["lineup_slots"]))


@pytest.mark.parametrize("cap", [None, 1], ids=["default_cap", "cap_1_defers"])
def test_repeat_head_names_the_cards_the_real_cap_kept(deferred, monkeypatch, cap):
    """models-eng #503, on a real worker: the filter's own head (its returned
    cards ahead of the deferred ones) when shorter than REPEAT_WINDOW. With
    the cap at 1 the real cap defers cards, so the worker must pass its
    count."""
    _filters_on(monkeypatch)
    if cap is not None:
        monkeypatch.setattr(deck_quality, "REPEAT_CAP", cap)
    calls = _spy_filter(monkeypatch)
    _job, ev = _evidence_of(run_job())
    [call] = calls
    if cap is not None:
        assert call["counts"]["deferred"] > 0, "the probe needs a deck the cap defers"
    head = call["out"][:len(call["out"]) - call["counts"]["deferred"]]
    want = ([server._deck_trade_hash(c.give_player_ids, c.receive_player_ids, c.target_user_id)
             for c in head] if len(head) < deck_quality.REPEAT_WINDOW else None)
    assert ev.filter_inputs["repeat_head"] == want
