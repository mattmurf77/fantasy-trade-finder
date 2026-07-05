"""Manual Trade Calculator endpoints (docs/plans/manual-trade-calculator-plan.md).

Pins the open consensus seam: POST /api/trade/evaluate and
GET /api/trade/values run over an injected universal pool, reuse the
engine's elo_to_value transform, drop unknown ids gracefully, and gate
fairness with the point ratio when confidence is absent.
"""

from dataclasses import dataclass

import pytest

import backend.server as srv


@dataclass
class _P:
    id: str
    name: str
    position: str
    team: str | None = None
    age: int | None = None


_POOL_PLAYERS = [
    _P("stud",  "Stud Man",    "WR", "CIN", 26),
    _P("good",  "Good Guy",    "RB", "DET", 24),
    _P("mid",   "Mid Player",  "TE", "SF",  27),
    _P("bench", "Bench Body",  "RB", "NYJ", 28),
]

# Seed Elos chosen so values are clearly ordered: stud >> good > mid > bench.
_SEED = {"stud": 1800.0, "good": 1650.0, "mid": 1500.0, "bench": 1350.0}


@pytest.fixture(autouse=True)
def _pool(monkeypatch):
    monkeypatch.setattr(srv, "_ensure_universal_pools", lambda: None)
    monkeypatch.setitem(
        srv.g_universal_by_format, "1qb_ppr",
        {"players": _POOL_PLAYERS, "seed": dict(_SEED)},
    )
    yield


def _post(body):
    with srv.app.test_client() as c:
        return c.post("/api/trade/evaluate", json=body)


def test_symmetric_trade_is_even():
    r = _post({"give_player_ids": ["stud"], "receive_player_ids": ["stud"]})
    assert r.status_code == 200
    d = r.get_json()
    assert d["verdict"] == "even" and d["favors"] == "even"
    assert d["point_ratio"] == 1.0
    assert d["give_value"] == d["receive_value"] > 0


def test_lopsided_trade_is_unfair_and_reports_favored_side():
    r = _post({"give_player_ids": ["stud"], "receive_player_ids": ["bench"]})
    d = r.get_json()
    assert d["verdict"] == "unfair"
    assert d["fairness"] is None            # gate failed (no confidence → point gate)
    assert d["favors"] == "give"            # give side carries the value
    assert d["give_value"] > d["receive_value"]


def test_values_match_engine_transform():
    r = _post({"give_player_ids": ["mid"], "receive_player_ids": ["good"]})
    d = r.get_json()
    by_id = {p["player_id"]: p["value"] for p in d["per_player"]}
    e2v = srv._trade_service_mod.elo_to_value
    assert by_id["mid"] == round(e2v(_SEED["mid"]), 1)
    assert by_id["good"] == round(e2v(_SEED["good"]), 1)


def test_unknown_ids_dropped_and_reported():
    r = _post({"give_player_ids": ["stud", "ghost"], "receive_player_ids": ["good"]})
    d = r.get_json()
    assert d["dropped_player_ids"] == ["ghost"]
    assert {p["player_id"] for p in d["per_player"]} == {"stud", "good"}


def test_one_sided_package_values_without_verdict():
    r = _post({"give_player_ids": ["stud", "good"], "receive_player_ids": []})
    d = r.get_json()
    assert d["give_value"] > 0 and d["receive_value"] == 0
    assert d["verdict"] is None and d["fairness"] is None


def test_empty_request_rejected():
    assert _post({"give_player_ids": [], "receive_player_ids": []}).status_code == 400


def test_unknown_format_falls_back_to_default():
    r = _post({"give_player_ids": ["stud"], "receive_player_ids": ["good"],
               "scoring_format": "bogus"})
    assert r.get_json()["scoring_format"] == "1qb_ppr"


def test_values_endpoint_shape_and_etag():
    with srv.app.test_client() as c:
        r = c.get("/api/trade/values?scoring_format=1qb_ppr")
        assert r.status_code == 200
        d = r.get_json()
        rows = d["players"]
        assert [p["id"] for p in rows[:2]] == ["stud", "good"]   # value-desc
        assert set(rows[0]) == {"id", "name", "position", "team", "age", "value"}
        etag = r.headers["ETag"]
        r2 = c.get("/api/trade/values?scoring_format=1qb_ppr",
                   headers={"If-None-Match": etag})
        assert r2.status_code == 304
