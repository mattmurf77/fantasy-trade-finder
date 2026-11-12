"""`backend/eval/pick_projection_replay.py` — the offline replay's own pieces.

The replay itself runs on the operator's machine against the git-ignored
`data/prod-requests/`; this file pins what it computes, offline, on synthetic
inputs: pick-id parsing, synthetic forecasts that are valid leagues, re-pricing
every board consistently with league totals conserved, a fake two-way deck
comparison, and an aggregate-only summary that prints no ids.
"""
import json
from types import SimpleNamespace

import pytest

from backend import pick_projection as pp
from backend import trade_service as ts
from backend.eval import pick_projection_replay as replay

LEAGUE = "777"


def test_owned_first_parses_only_draft_season_round_one():
    assert replay.owned_first(f"{LEAGUE}_2027_1_5", LEAGUE, 2027) == "5"
    assert replay.owned_first(f"{LEAGUE}_2027_2_5", LEAGUE, 2027) is None
    assert replay.owned_first(f"{LEAGUE}_2028_1_5", LEAGUE, 2027) is None
    assert replay.owned_first("9_2027_1_5", LEAGUE, 2027) is None
    assert replay.owned_first("generic_pick_1_Mid", LEAGUE, 2027) is None
    assert replay.owned_first(None, LEAGUE, 2027) is None


@pytest.mark.parametrize("noise", list(replay.CONCENTRATIONS.values()))
def test_synthetic_forecasts_are_valid_leagues(noise):
    ids = [str(r) for r in range(1, 13)]
    result = replay.synthetic_result(ids, seed=3, noise=noise)
    assert pp.compact(result, run_id="r", created_at="2026-11-11T00:00:00+00:00") is not None
    proj = replay.projection_from(result)
    assert proj.weight == 1.0 and proj.season == 2027


def test_concentration_orders_the_spread():
    ids = [str(r) for r in range(1, 13)]
    spread = {}
    for name, noise in replay.CONCENTRATIONS.items():
        proj = replay.projection_from(replay.synthetic_result(ids, seed=5, noise=noise))
        spread[name] = max(max(d) for d in proj.dists.values())
    assert spread["week3"] < spread["week10"] < spread["week14"]


def _context(n=12):
    seed = {f"{LEAGUE}_2027_1_{r}": ts.value_to_elo(1859.5) for r in range(1, n + 1)}
    seed["player"] = ts.value_to_elo(4000.0)
    seed[f"{LEAGUE}_2028_1_1"] = ts.value_to_elo(1859.5)
    members = [SimpleNamespace(user_id=f"m{r}", roster=[], elo_ratings=dict(seed)) for r in range(2, n + 1)]
    league = SimpleNamespace(league_id=LEAGUE, members=members)
    return {"league": league, "seed_elo": dict(seed), "user_elo": dict(seed), "user_id": "m1"}


def test_reprice_moves_every_board_together_and_conserves_the_league():
    """Sabotage: re-price only `seed_elo` → the member boards disagree."""
    ctx = _context()
    proj = replay.projection_from(replay.synthetic_result([str(r) for r in range(1, 13)],
                                                          seed=1, noise=0.1))
    new, deltas = replay.reprice(ctx, proj, season=2027, scoring_format="1qb_ppr")
    assert len(deltas) == 12 and f"{LEAGUE}_2028_1_1" not in deltas
    assert new["seed_elo"]["player"] == ctx["seed_elo"]["player"]
    for pid in deltas:
        assert new["user_elo"][pid] == new["seed_elo"][pid]
        assert all(m.elo_ratings[pid] == new["seed_elo"][pid] for m in new["league"].members)
    assert ctx["seed_elo"][next(iter(deltas))] == ts.value_to_elo(1859.5)     # input untouched
    assert sum(v[1] for v in deltas.values()) == pytest.approx(sum(v[0] for v in deltas.values()),
                                                               rel=1e-3)


def test_compare_and_summary_are_aggregate_only():
    ctx = _context()
    proj = replay.projection_from(replay.synthetic_result([str(r) for r in range(1, 13)],
                                                          seed=2, noise=0.1))
    pick = f"{LEAGUE}_2027_1_1"

    def generate(**k):
        cheap = ts.elo_to_value(k["seed_elo"][pick]) < 1500
        cards = [SimpleNamespace(target_user_id="m2", give_player_ids=["player"],
                                 receive_player_ids=[pick])]
        if cheap:
            cards.append(SimpleNamespace(target_user_id="m3", give_player_ids=[pick],
                                         receive_player_ids=["player"]))
        return cards, None

    class Req:
        def __init__(self, context, slots):
            pass

        def served(self, cards):
            return cards, {"filler": 0}

    row = replay.compare(generate, Req, ctx, [], proj, season=2027, scoring_format="1qb_ppr")
    assert row["first_cards_old"] == 1 and row["complete_league"]
    assert row["conservation"] == pytest.approx(1.0, abs=1e-3)
    text = replay.summarize({"synthetic-week10": [row], "real": []})
    assert "requests replayed: 1" in text and "conservation" in text
    assert LEAGUE not in text and "m2" not in text and pick not in text


def test_main_on_an_empty_directory_is_offline_and_aggregate(tmp_path, capsys, monkeypatch):
    import socket
    for name in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, name, getattr(socket.socket, name))
    monkeypatch.setattr(socket, "create_connection", socket.create_connection)
    import backend.feature_flags as ff
    monkeypatch.setattr(ff, "_flags_cache", ff._flags_cache)
    monkeypatch.setattr(ts, "_cfg", dict(ts._cfg))
    import os
    from sqlalchemy import create_engine
    from backend import database
    monkeypatch.setattr(database, "engine", create_engine("sqlite://"))   # never the app DB
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("FTF_DP_PICK_VALUES_FILE", os.environ.get("FTF_DP_PICK_VALUES_FILE", ""))
    (tmp_path / "index.json").write_text(json.dumps([]))
    assert replay.main(["--dir", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "requests replayed: 0" in out
