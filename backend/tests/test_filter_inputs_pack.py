"""models-lead addendum D2: the worker keeps the quality filter's inputs on
the deck's evidence (never on the job, whose shape stays as it was), and job
done carries them into the pack's run header (`run["filter_inputs"]`), a
per-run part written once. Harness: test_packed_evidence's (the `deferred`
fixture: real synchronous organic jobs with deferred evidence)."""
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
