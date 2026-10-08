"""value_core_recall: closeness, band calibration, fixture cases, recall with a stub pipeline.

Case construction reads only committed fixtures (offline). run_recall's engine
modules (pipeline, core, adapter) are stubbed through sys.modules as in specs.md
section 4; after integration the stubs patch the real modules.
"""
import importlib
import math
import sys
import types as _t
from pathlib import Path

import pytest

from backend.eval import value_core_recall as recall
from backend.value_core.types import (
    DEFAULT_WINDOW, Asset, CoreConfig, CoreDiagnostics, DeckEntry, FairTrade, PipelineResult,
    RankConfig, ScoredTrade, Scores, TradeVerdict,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def A(id, pos, market):
    kind = "pick" if pos == "PICK" else "player"
    return Asset(id, kind, pos, id.upper(), None, float(market))


def _trade(give, receive, assets, partner="2"):
    g = sum(assets[a].market for a in give)
    r = sum(assets[a].market for a in receive)
    return FairTrade(partner, tuple(give), tuple(receive), g, r, r / g, 0.0, None, False, (0, 0))


def test_is_close():
    assets = {a.id: a for a in (A("h", "WR", 3000), A("a", "RB", 800), A("e", "TE", 700),
                                A("c", "WR", 3500), A("d", "RB", 3200))}
    real_give, real_receive = ("h", "a"), ("c",)
    # headliner = c (3500, the max-market asset of the real trade), on the receive side
    assert recall.is_close(_trade(["h"], ["c"], assets), real_give, real_receive, assets)
    # 2 of 3 real ids, but the headliner c is missing -> not close
    assert not recall.is_close(_trade(["h", "a"], ["d"], assets), real_give, real_receive, assets)
    # headliner present but only 1 of 3 real ids (< 50%) -> not close
    assert not recall.is_close(_trade(["e"], ["c"], assets), real_give, real_receive, assets)
    # NOTE specs.md 5.4 lists give ("a",) as "not close (headliner missing)", but with c at
    # 3500 the lld 8.3 headliner is c, which ("a",) -> ("c",) carries with 2 of 3 real ids.
    assert recall.is_close(_trade(["a"], ["c"], assets), real_give, real_receive, assets)


def test_band_calibration():
    assert recall.band_calibration([0.3, 0.0, 0.2, 0.05, 0.1]) == {
        "n": 5, "p50": 0.1, "p80": 0.2, "p90": 0.3, "recommended_band": 0.22}
    assert recall.band_calibration([]) == {"n": 0, "p50": None, "p80": None, "p90": None,
                                           "recommended_band": None}
    ten = [i / 100 for i in range(1, 11)]              # 0.01 .. 0.10
    assert recall.band_calibration(ten)["p80"] == 0.08
    assert recall.band_calibration(ten)["p90"] == 0.09


def test_cases_from_fixtures_ffv3_2024():
    cases, skipped = recall.cases_from_fixtures(FIXTURES, only={("ffv3", 2024)})
    assert skipped["offseason_leg"] == 21
    assert skipped["multi_team"] == 1
    assert 0 < len(cases) <= 9
    for case in cases:
        assert (case.label, case.season, case.scoring_format) == ("ffv3", 2024, "1qb_ppr")
        assert case.leg >= 2 and case.case_id.startswith(f"ffv3-2024-w{case.leg}-")
        assert case.a_gives and case.b_gives
        assert set(case.a_gives) <= set(case.teams[case.a_team])
        assert set(case.b_gives) <= set(case.teams[case.b_team])
        assert all(case.assets[a].market > 0 for a in case.a_gives + case.b_gives)
        assert "QB" in case.lineup_slots and "DL" in case.lineup_slots   # raw roster_positions
        rostered = [a for ids in case.teams.values() for a in ids]
        assert len(rostered) == len(set(rostered)) and set(rostered) <= set(case.assets)


def test_cases_from_fixtures_account_for_every_in_season_trade():
    """lld 8.3's expected yield: 77 in-season two-team trades on 3bb981ed, minus skips."""
    cases, skipped = recall.cases_from_fixtures(FIXTURES)
    assert {(c.label, c.season) for c in cases} == {
        ("ffv3", 2022), ("ffv3", 2023), ("ffv3", 2024), ("ffv3", 2025),
        ("lakeview", 2024), ("lakeview", 2025)}
    assert (len(cases) + skipped["roster_mismatch"] + skipped["no_values"]
            + skipped["unpriced_asset"]) == 77
    assert {c.scoring_format for c in cases if c.label == "lakeview"} == {"sf_tep"}


@pytest.fixture
def vc_stubs(monkeypatch):
    mods = {}
    for name in ("adapter", "core", "pipeline"):
        full = f"backend.value_core.{name}"
        try:
            mod = importlib.import_module(full)
        except ImportError:
            mod = _t.ModuleType(full)
            monkeypatch.setitem(sys.modules, full, mod)
        mods[name] = mod
    monkeypatch.setattr(mods["adapter"], "tier_values", lambda fmt: (1492.0, 8457.0),
                        raising=False)
    return mods


def _entry(i, trade):
    return DeckEntry(i, ScoredTrade(trade, Scores(0.5, 0.5, 0.5, 0.5), {}), 0.5, ())


def test_run_recall_stub_pipeline(vc_stubs, monkeypatch):
    assets = {a.id: a for a in (A("h", "WR", 3000), A("a", "RB", 900), A("e", "TE", 800),
                                A("c", "WR", 3100), A("d", "RB", 950), A("f", "TE", 850))}
    case = recall.RecallCase(
        case_id="t-2024-w3-1", label="t", season=2024, leg=3, scoring_format="1qb_ppr",
        lineup_slots=("QB", "RB", "WR"), assets=assets,
        teams={"1": ("h", "a", "e"), "2": ("c", "d", "f")},
        a_team="1", b_team="2", a_gives=("h",), b_gives=("c",))
    real = {"1": (("h",), ("c",)), "2": (("c",), ("h",))}
    requests = []

    def fake_run(snapshot, request, core_cfg, rank_cfg, **kw):
        requests.append(request)
        viewer, partner = request.viewer_team_id, request.partner_team_id
        assert all(t.window == DEFAULT_WINDOW for t in snapshot.teams.values())
        mine = [a for a in snapshot.teams[viewer].asset_ids if a not in real[viewer][0]]
        theirs = [a for a in snapshot.teams[partner].asset_ids if a not in real[viewer][1]]
        decoys = [_trade([mine[0]], [theirs[0]], assets, partner),
                  _trade([mine[1]], [theirs[1]], assets, partner)]
        trades = decoys + [_trade(*real[viewer], assets, partner)]      # the real trade 3rd
        return PipelineResult([_entry(i, t) for i, t in enumerate(trades)], CoreDiagnostics(), 1)

    def fake_evaluate(snapshot, request, cfg, *, partner_team_id, give, receive):
        trade = _trade(give, receive, assets, partner_team_id)
        ok = abs(math.log(trade.adjusted_ratio)) <= math.log(1.02)
        return TradeVerdict(ok, None if ok else "band", trade)

    monkeypatch.setattr(vc_stubs["pipeline"], "run", fake_run, raising=False)
    monkeypatch.setattr(vc_stubs["core"], "evaluate_trade", fake_evaluate, raising=False)

    result = recall.run_recall([case], CoreConfig(), RankConfig(), top=10)
    assert (result["cases"], result["orientations"]) == (1, 2)
    assert result["exact_at_k"] == 1.0 and result["close_at_k"] == 1.0
    assert result["in_pool_rate"] == 1.0
    assert [(r["orientation"], r["rank_exact"], r["rank_close"]) for r in result["per_case"]] == [
        ("A", 3, 3), ("B", 3, 3)]
    assert result["reject_reasons"] == {"band": 2}                 # 3100/3000 is outside +-2%
    assert result["per_case"][0]["log_ratio"] == pytest.approx(math.log(3100 / 3000), abs=1e-4)
    assert result["band"]["n"] == 1                               # once per case, orientation A
    assert result["band"]["p80"] == pytest.approx(math.log(3100 / 3000))
    assert [(r.viewer_team_id, r.partner_team_id, r.board) for r in requests] == [
        ("1", "2", None), ("2", "1", None)]

    at_two = recall.run_recall([case], CoreConfig(), RankConfig(), top=2)
    assert at_two["exact_at_k"] == 0.0 and at_two["in_pool_rate"] == 1.0
