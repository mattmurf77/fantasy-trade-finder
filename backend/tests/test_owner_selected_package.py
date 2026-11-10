"""Full and partial selected-give packages through the ordinary Flask routes."""
import math

import pytest

from backend import feature_flags as ff, server, trade_service as ts
from backend.tests.test_fair_packages import LEAGUE, ME, TOKEN
from backend.tests.test_owner_generator_routes import harness, owner_harness
from backend.tests.test_owner_only_routes import exclusive, large_exclusive


@pytest.mark.parametrize("bilateral", [False, True])
@pytest.mark.parametrize("second_player_market", [10.0, 1.0])
def test_trade_as_package_keeps_each_give_pin(large_exclusive, monkeypatch, bilateral, second_player_market):
    client, _, sess, _, league = large_exclusive
    move = "r3-15"
    for member in league.members:
        if member.user_id == ME:
            member.roster.append(move)
        elif member.user_id == "opponent-3":
            member.roster.remove(move)
    sess["user_roster"] = ["g", move]
    ranking = sess["service"]
    ranking._seed[move] = 1500 + math.log(second_player_market) / .005
    ff._flags_cache["trade.finder_targeting"] = True
    ts._cfg.update(owner_bilateral_enabled=float(bilateral), owner_bilateral_revision_enabled=float(bilateral))
    for name in ("_deck_exploration_enabled", "_deck_first_session_enabled", "_likes_you_enabled",
                 "_suggestion_telemetry_enabled", "_deck_fatigue_enabled", "_deck_taste_enabled",
                 "_deck_diversity_enabled", "_thompson_deck_enabled"):
        monkeypatch.setattr(server, name, lambda: False)
    # Execute the ordinary background target inline so the test has no wait.
    monkeypatch.setattr(server, "_start_trade_job_thread",
                        lambda *, target, args, kwargs: target(*args, **kwargs))
    headers = {"X-Session-Token": TOKEN}
    for mode in ("any", "all"):
        response = client.post("/api/trades/generate", headers=headers, json={
            "league_id": LEAGUE, "fairness_threshold": .5, "pinned_give_players": ["g", move],
            "pinned_give_mode": mode, "pinned_receive_players": ["r0-0"],
            "opponent_user_id": "opponent-0",
        })
        assert response.status_code == 200, response.json
        polled = client.get("/api/trades/status", query_string={"job_id": response.json["job_id"]}, headers=headers)
        assert polled.status_code == 200 and polled.json["status"] == "complete", polled.json
        cards = polled.json["cards"]
        partial_only = second_player_market > 1
        if mode == "all" and partial_only:
            assert cards == []
            continue
        assert cards
        for card in cards:
            give = {p["id"] for p in card["give"]}
            assert card["selection_coverage"] == ("partial" if partial_only else "full")
            assert bool(card.get("selection_notice")) is partial_only
            assert len(give & {"g", move}) == (1 if partial_only else 2)
