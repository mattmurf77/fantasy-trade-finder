"""Universal pool build resilience against transient DP fetch failures.

A failed DynastyProcess CSV fetch at boot used to permanently cache an empty
pool ({"players": [], "seed": {}}) — the truthy dict passed the idempotency
check in _ensure_universal_pools, degrading that scoring format (no consensus
values, no trade values, no tier seeds) until process restart. An empty
values map must instead be treated as fetch failure: nothing cached, short
backoff, retry on a later access.

Also pins _get_universal_pool's unknown-format behavior: the 1qb_ppr
fallback still serves data, but an unknown key logs an error instead of
silently masquerading as 1QB.
"""

import logging

import pytest

import backend.server as srv


_FAKE_SLEEPER = {
    "100": {"full_name": "Stud Man", "position": "WR", "team": "CIN",
            "age": 26, "years_exp": 4},
    "200": {"full_name": "Good Guy", "position": "RB", "team": "DET",
            "age": 24, "years_exp": 2},
}


def _dp_maps():
    """(elo, vals, pos) triple in load_consensus_maps' return order."""
    vals = {srv.normalise_name(p["full_name"]): 5000.0 for p in _FAKE_SLEEPER.values()}
    elo  = {srv.normalise_name(p["full_name"]): 1700.0 for p in _FAKE_SLEEPER.values()}
    pos  = {srv.normalise_name(p["full_name"]): p["position"] for p in _FAKE_SLEEPER.values()}
    return elo, vals, pos


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Fresh pool globals per test; no network, no DB."""
    monkeypatch.setattr(srv, "g_universal_by_format", {})
    monkeypatch.setattr(srv, "dp_values_by_format", {})
    monkeypatch.setattr(srv, "dp_elo_by_format", {})
    monkeypatch.setattr(srv, "dp_pos_by_format", {})
    monkeypatch.setattr(srv, "_dp_fetch_retry_at", {})
    monkeypatch.setattr(srv, "g_universal_players", [])
    monkeypatch.setattr(srv, "g_universal_seed", {})
    monkeypatch.setattr(srv, "dp_values", {})
    monkeypatch.setattr(srv, "_load_sleeper_cache", lambda: dict(_FAKE_SLEEPER))
    monkeypatch.setattr(srv, "load_players", lambda position=None: [])
    yield


def test_failed_fetch_not_cached_then_recovers(monkeypatch):
    # Boot-time outage: DP fetch yields empty maps (data_loader's failure mode).
    monkeypatch.setattr(srv, "load_consensus_maps", lambda scoring: ({}, {}, {}))

    srv._ensure_universal_pools()

    # The failure must not be cached — no empty pool, no empty DP maps.
    assert srv.g_universal_by_format == {}
    assert srv.dp_values_by_format == {}
    assert srv.dp_elo_by_format == {}

    # GitHub is back: same process, next access rebuilds successfully.
    elo, vals, pos = _dp_maps()
    monkeypatch.setattr(srv, "load_consensus_maps",
                        lambda scoring: (dict(elo), dict(vals), dict(pos)))
    srv._dp_fetch_retry_at.clear()  # backoff window elapsed

    srv._ensure_universal_pools()

    for fmt in ("1qb_ppr", "sf_tep"):
        pool = srv.g_universal_by_format[fmt]
        ids = {p.id for p in pool["players"]}
        assert {"100", "200"} <= ids
        assert pool["seed"]["100"] == 1700.0
    # Legacy 1qb_ppr aliases repopulated too.
    assert srv.g_universal_players and srv.dp_values


def test_fetch_exception_not_cached(monkeypatch):
    def _boom(scoring):
        raise OSError("github down")

    monkeypatch.setattr(srv, "load_consensus_maps", _boom)

    srv._ensure_universal_pools()

    assert srv.g_universal_by_format == {}
    assert srv.dp_values_by_format == {}


def test_backoff_skips_refetch_within_window(monkeypatch):
    calls = []

    def _failing_maps(scoring):
        calls.append(scoring)
        return {}, {}, {}

    monkeypatch.setattr(srv, "load_consensus_maps", _failing_maps)

    srv._ensure_universal_pools()
    assert sorted(calls) == ["1qb_ppr", "sf_tep"]

    # Immediately again (e.g. next request thread): inside the backoff
    # window, so no refetch — but still no cached empty pool either.
    srv._ensure_universal_pools()
    assert sorted(calls) == ["1qb_ppr", "sf_tep"]
    assert srv.g_universal_by_format == {}


def test_unknown_format_logs_error_but_serves_fallback(monkeypatch, caplog):
    elo, vals, pos = _dp_maps()
    monkeypatch.setattr(srv, "load_consensus_maps",
                        lambda scoring: (dict(elo), dict(vals), dict(pos)))

    with caplog.at_level(logging.ERROR, logger="trade_finder"):
        players, seed = srv._get_universal_pool("2qb_typo")

    assert any("Unknown scoring format" in r.getMessage() for r in caplog.records)
    assert players and seed  # fallback still serves the 1qb_ppr pool


def test_known_format_does_not_log_error(monkeypatch, caplog):
    elo, vals, pos = _dp_maps()
    monkeypatch.setattr(srv, "load_consensus_maps",
                        lambda scoring: (dict(elo), dict(vals), dict(pos)))

    with caplog.at_level(logging.ERROR, logger="trade_finder"):
        players, seed = srv._get_universal_pool("sf_tep")

    assert not [r for r in caplog.records if "Unknown scoring format" in r.getMessage()]
    assert players and seed
