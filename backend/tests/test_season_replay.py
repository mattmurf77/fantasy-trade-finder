"""Win-now season signal WI-4: the offline replay tool (`backend/eval/season_replay.py`).

Spec: docs/plans/win-now-season-signal/validation.md §3 (arms, metrics, bars), §6
(guardrails), §7 (stage 2); lld.md §8; build-plan.md WI-4.

World: the committed fixture league with its real Sleeper-projection capture
(`season_replay.fixture_world` / `fixture_evidence`), synthetic owners and boards. No
network, no database, no recorded production request.

Covered (each proven red against the named sabotage, then green on revert):
- test_report_has_no_player_user_league_id_or_name. Sabotage: print a card's identity
  from `summarize`.
- test_arms_run_and_arm_1_is_revision_2s_own_output. Sabotage: pass the season
  evidence to arm 1 (generate it with revision 5).
- test_bars_on_a_constructed_result (and its edge cases). Sabotage: flip the All-in
  points comparison (`>=` to `<=`).
- test_requests_without_evidence_report_no_evidence_and_fail_the_sample.
"""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import re

import pytest

from backend import feature_flags as ff, trade_service as ts
from backend import trade_gen_bilateral_candidate as r2
from backend.eval import season_replay as sr


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setattr(ff, "_flags_cache", dict(ff.DEFAULT_FLAGS))
    monkeypatch.setattr(ts, "_cfg", dict(ts._DEFAULT_CFG))


@lru_cache(maxsize=None)
def _replayed():
    """(row, deck cache, request) for the All-in fixture request: arms 1-4, no flip, no stage 2."""
    request = sr.synthetic_requests(0, sr.fixture_evidence())[0]
    assert request.saved == "championship"
    cache = {}
    row = sr.replay(request, flip=False, stage2=False, cache=cache, key="t")
    return row, cache, request


def _terms(card):
    return sr._terms(card)


def test_arms_run_and_arm_1_is_revision_2s_own_output():
    row, cache, request = _replayed()
    arms = {arm: cache[("t", "championship", arm)] for arm in ("arm1", "no_evidence", "arm2", "arm3", "arm4")}
    direct, _ = r2.generate_bilateral_trades(**sr.fixture_world("championship", 0))
    assert [_terms(c) for c in arms["arm1"]["cards"]] == [_terms(c) for c in direct]
    assert row["no_forecast_identical"] is True
    # The season arms run on usable evidence and do change the deck.
    for arm in ("arm2", "arm3", "arm4"):
        assert arms[arm]["cards"] and arms[arm]["served"]
        assert [_terms(c) for c in arms[arm]["cards"]] != [_terms(c) for c in direct]
        assert all(sr._proof(c)["season_signal"]["evidence"]["state"] == "usable" for c in arms[arm]["cards"][:5])
    assert set(row["metrics"]) == {"arm1", "arm2", "arm3", "arm4"}
    assert row["push_down_removes_nothing"] is True and row["floor_unchanged"] is True


def test_report_has_no_player_user_league_id_or_name():
    row, cache, request = _replayed()
    text, _ = sr.summarize([row], synthetic=True)
    context = request.context
    users = {m.user_id for m in context["league"].members}            # "u00".. ("me" is too short to test)
    names = {p.name for p in context["players"].values() if p.position != "PICK"}
    picks = {pid for pid, p in context["players"].items() if p.position == "PICK"}
    numeric = {pid for pid, p in context["players"].items() if p.position != "PICK"}
    for token in users | picks | {context["league"].league_id}:
        assert not re.search(rf"\b{re.escape(token)}\b", text), "an id reached the report"
    for name in names:
        assert name not in text, "a player name reached the report"
    for pid in numeric:   # a printed id list or card would quote them
        assert f"'{pid}'" not in text and f'"{pid}"' not in text
    assert "requests replayed: 1" in text and "bars:" in text


# ── the bars on a constructed result ─────────────────────────────────────────

def _metrics(pts=0.0, starter=.4, cost=.3, matched=.1, support=.6, served=200):
    return {"n": 30, "served": served, "pts": pts, "starter": starter, "cost": cost, "starter_received": .9,
            "conflicts_in_view": 0.0, "matched": matched, "matched_partner_saved": 0,
            "matched_partner_unsaved": 0, "support": support}


def _row(saved, pair, *, gain=2.0, start=.3, cost=-.2, table=0.0, served=(200, 200), cpu=(3.0, 3.1),
         stage2_matched=.05):
    base = _metrics()
    new = _metrics(pts=gain, starter=base["starter"] + start, cost=base["cost"] + cost, served=served[1])
    if saved not in sr.SCORED:
        new = dict(base)
    row = {"saved": saved, "pair": pair, "evidence": "usable", "usable": True, "pinned": False,
           "served_arm1": served[0], "served_arm2": served[1], "cpu_arm1": cpu[0], "cpu_arm2": cpu[1],
           "no_forecast_identical": True, "push_down_removes_nothing": True, "floor_unchanged": True,
           "below_floor": 0, "conflicts": 0, "conflict_kinds": {}, "clip": (1, 10),
           "metrics": {"arm1": base, "arm2": new, "arm3": dict(new), "arm4": dict(new, pts=new["pts"] - table),
                       "stage2": dict(new, matched=new["matched"] + stage2_matched)},
           "flip": {"r2": dict.fromkeys(sr.OUTLOOKS, 0.0),
                    "r5": {"championship": 2.0, "contender": 1.5, "not_sure": 0.0, "rebuilder": 0.0, "jets": 0.0}}}
    if saved == "not_sure":
        row["not_sure_identical"] = True
        row["metrics"]["stage2"] = dict(base)
    if saved in sr.MIRROR:
        row["mirror_same_terms"] = row["mirror_order_at_zero"] = True
    return row


def _passing_rows():
    rows = [_row("championship" if i % 2 else "contender", f"p{i % 6}") for i in range(40)]
    rows += [_row("not_sure", "p0"), _row("rebuilder", "p1"), _row("jets", "p2")]
    return rows


def _status(bars, needle):
    found = [status for _, check, status, _ in bars if needle in check]
    assert len(found) == 1, needle
    return found[0]


def test_bars_on_a_constructed_result():
    bars = sr.evaluate_bars(_passing_rows())
    assert sr.passed(bars), [b for b in bars if b[2] not in ("PASS", "n/a")]
    assert _status(bars, "Pinned") == "n/a"


def test_all_in_points_bar_edge():
    rows = _passing_rows()
    for row in rows:
        if row["saved"] == "championship":
            row["metrics"]["arm2"]["pts"] = 1.0          # exactly at the bar
    assert _status(sr.evaluate_bars(rows), "All-in lineup points") == "PASS"
    for row in rows:
        if row["saved"] == "championship":
            row["metrics"]["arm2"]["pts"] = 0.99
    bars = sr.evaluate_bars(rows)
    assert _status(bars, "All-in lineup points") == "FAIL" and not sr.passed(bars)


def test_costs_bar_counts_requests_not_cards():
    rows = _passing_rows()
    allin = [r for r in rows if r["saved"] == "championship"]
    for row in allin[:3]:                                 # 3 of 20 higher: 85% < 90%
        row["metrics"]["arm2"]["cost"] = row["metrics"]["arm1"]["cost"] + .1
    assert _status(sr.evaluate_bars(rows), "All-in costs points") == "FAIL"
    allin[2]["metrics"]["arm2"]["cost"] = allin[2]["metrics"]["arm1"]["cost"]   # 2 of 20: 90%
    assert _status(sr.evaluate_bars(rows), "All-in costs points") == "PASS"


def test_deck_size_lists_a_request_under_30():
    rows = _passing_rows()
    rows[4]["served_arm1"], rows[4]["served_arm2"] = 30, 29
    _, check, status, detail = next(b for b in sr.evaluate_bars(rows) if "Deck size" in b[1])
    assert status == "FAIL" and "requests [5]" in detail


def test_flip_table_and_identity_bars():
    rows = _passing_rows()
    rows[0]["flip"]["r5"]["contender"] = 2.5             # All-in below Contending on 1 of 43: still >= 80%
    assert _status(sr.evaluate_bars(rows), "Outlook flip") == "PASS"
    for row in rows[:10]:
        row["flip"]["r5"]["contender"] = 0.0             # Contending not above Not sure
    assert _status(sr.evaluate_bars(rows), "Outlook flip") == "FAIL"
    rows = _passing_rows()
    for row in rows:
        row["metrics"]["arm4"]["pts"] = row["metrics"]["arm2"]["pts"] + .31
    assert _status(sr.evaluate_bars(rows), "Label table") == "FAIL"
    rows = _passing_rows()
    rows[-3]["not_sure_identical"] = False
    rows[-1]["mirror_order_at_zero"] = False
    rows[0]["no_forecast_identical"] = False
    bars = sr.evaluate_bars(rows)
    assert {_status(bars, k) for k in ("Not sure: identical", "Rebuilding/Tanking: same", "No forecast")} == {"FAIL"}


def test_sample_bar_needs_40_requests_from_5_pairs():
    rows = _passing_rows()
    assert _status(sr.evaluate_bars(rows), "sample") == "PASS"
    assert _status(sr.evaluate_bars(rows, synthetic=True), "sample") == "n/a"
    bars = sr.evaluate_bars(rows[1:])                     # 39 scored requests
    assert _status(bars, "sample") == "INSUFFICIENT" and not sr.passed(bars)
    for index, row in enumerate(rows):
        row["pair"] = f"p{index % 4}"                     # 43 requests, 4 pairs
    assert _status(sr.evaluate_bars(rows), "sample") == "INSUFFICIENT"


def test_requests_without_evidence_report_no_evidence_and_fail_the_sample():
    rows = [{"saved": "championship", "pair": f"p{i}", "evidence": "not recorded", "usable": False,
             "pinned": False, "served_arm1": 100, "served_arm2": 100, "cpu_arm1": 1.0, "cpu_arm2": 1.0,
             "no_forecast_identical": True} for i in range(6)]
    text, bars = sr.summarize(deepcopy(rows))
    assert "season evidence: not recorded 6" in text
    assert _status(bars, "No forecast") == "PASS"
    assert _status(bars, "sample") == "INSUFFICIENT"
    assert _status(bars, "All-in lineup points") == "INSUFFICIENT"
    assert not sr.passed(bars)
