"""value-core WP2: team windows (docs/plans/value-core-engine/lld.md section 5.1, specs.md 5.2)."""
from types import SimpleNamespace

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.value_core import windows as win
from backend.value_core.types import DEFAULT_WINDOW, Standing


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Flags and trade_service._cfg at defaults (backend/tests/CLAUDE.md harness patterns 3 and 4)."""
    monkeypatch.setattr(ff, "_flags_cache", dict(ff.DEFAULT_FLAGS))
    monkeypatch.setattr(ts, "_cfg", dict(ts._DEFAULT_CFG))


def _pf(**pfs):
    return {t: Standing(0, 0, 0, float(pf)) for t, pf in pfs.items()}


def _run(**kw):
    args = dict(team_rosters={"A": [], "B": [], "C": [], "T": []}, players={}, pick_shares={},
                standings=_pf(A=100, B=200, C=300, T=400), completed_weeks=8, declared={},
                standings_weight=0.3)
    args.update(kw)
    return win.infer_windows(**args)


def _flat(monkeypatch):
    monkeypatch.setattr(win, "infer_team_outlook", lambda *a, **k: ("not_sure", 0.0, {}))


def test_standings_weight_ramp():
    assert win.standings_weight_for(0, 0.3) == 0
    assert win.standings_weight_for(3, 0.3) == pytest.approx(0.1125)
    assert win.standings_weight_for(8, 0.3) == 0.3
    assert win.standings_weight_for(12, 0.3) == 0.3
    assert win.standings_weight_for(5, -1) == 0


def test_pf_indices():
    got = win.pf_indices(_pf(a=100, b=200, c=300, d=400))
    assert [got[t] for t in "abcd"] == pytest.approx([-1, -1 / 3, 1 / 3, 1])
    assert win.pf_indices(_pf(a=150, b=150)) == {"a": 0.0, "b": 0.0}
    assert win.pf_indices(_pf(a=150)) == {}


def test_standings_move_middle_team(monkeypatch):
    _flat(monkeypatch)
    t = _run(completed_weeks=8)["T"]
    assert t.window == "contender"
    assert t.score == pytest.approx(0.3)
    assert t.pf_index == 1.0
    assert t.standings_weight == pytest.approx(0.3)
    assert t.source == "inferred"

    t0 = _run(completed_weeks=0)["T"]
    assert t0.window == "middle"
    assert t0.standings_weight == 0.0
    assert t0.pf_index is None


def test_declared_overrides(monkeypatch):
    _flat(monkeypatch)
    t = _run(declared={"T": "jets"})["T"]
    assert t.window == "rebuilder"
    assert t.source == "declared"


def _player(age, rank):
    return SimpleNamespace(position="WR", age=age, search_rank=rank, pick_value=None)


def test_outlook_flags_do_not_move_windows(monkeypatch):
    players = {"old1": _player(30, 5), "old2": _player(31, 12), "kid1": _player(21, 8),
               "kid2": _player(22, 20), "mid1": _player(25, 30), "mid2": _player(29, 40)}
    kw = dict(team_rosters={"A": ["old1", "old2"], "B": ["kid1", "kid2"], "C": ["mid1", "mid2"]},
              players=players, pick_shares={"A": 0.1, "B": 0.5, "C": 0.4},
              standings=_pf(A=300, B=100, C=200), completed_weeks=4)
    off = win.infer_windows(declared={}, standings_weight=0.3, **kw)
    monkeypatch.setattr(ff, "_flags_cache", {**ff.DEFAULT_FLAGS, "trade.outlook_composite": True,
                                             "trade.outlook_net_firsts": True})
    on = win.infer_windows(declared={}, standings_weight=0.3, **kw)
    assert on == off
    assert {w.source for w in off.values()} == {"inferred"}
    assert off["A"].window == "contender" and off["B"].window == "rebuilder"


def test_infer_exception_defaults(monkeypatch):
    def fake(roster, players, **kw):
        if roster == ["boom"]:
            raise RuntimeError("bad roster")
        return "not_sure", 0.0, {}

    monkeypatch.setattr(win, "infer_team_outlook", fake)
    got = _run(team_rosters={"A": [], "B": [], "C": [], "T": ["boom"]})
    assert got["T"] == DEFAULT_WINDOW
    assert got["A"].source == "inferred" and got["A"].window == "rebuilder"
    assert got["A"].pf_index == -1.0
    assert got["C"].window == "contender"
