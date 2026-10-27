"""models-lead addendum D2: job done carries the quality filter's inputs into
the pack's run header (`run["filter_inputs"]`), a per-run part written once.
Harness: test_packed_evidence's (the `deferred` fixture, real routes)."""
import backend.server as server
from backend.tests.test_i1_serve_filter import live  # noqa: F401  (fixture)
from backend.tests.test_trade_page_store import p1, status, stored  # noqa: F401  (fixtures)
from backend.tests.test_deferred_evidence import deferred  # noqa: F401  (fixture)
from backend.tests.test_packed_evidence import pack_of, packed_deck, unpack


def test_the_pack_run_header_carries_it(deferred, monkeypatch):
    monkeypatch.setattr(server, "_deck_quality_filters_enabled", lambda: True)
    client, engine, _ = deferred
    job_id, *_ = packed_deck(40)
    with server._trade_jobs_lock:
        recorded = server._trade_jobs[job_id]["filter_inputs"]
    status(client, job_id, 0)
    run, _cards = unpack(pack_of(engine, job_id))
    assert run["filter_inputs"] == recorded and recorded["v"] == 1


def test_a_deck_without_a_record_has_none_in_its_header(deferred):
    """A job from before D2 (no filter_inputs on it) writes none: absent means
    not recorded, never a run the filter skipped."""
    client, engine, _ = deferred
    job_id, *_ = packed_deck(40)
    with server._trade_jobs_lock:
        server._trade_jobs[job_id]["evidence"].run_meta.pop("filter_inputs", None)
    status(client, job_id, 0)
    run, _cards = unpack(pack_of(engine, job_id))
    assert "filter_inputs" not in run
