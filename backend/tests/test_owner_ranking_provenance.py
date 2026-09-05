"""Per-entry evidence survives publishing and internal policy wiring."""
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, insert

from backend import database as db
from backend import server
from backend import trade_policy as tp
from backend.ranking_service import Player, RankingService
from backend.trade_service import elo_to_value


@pytest.fixture
def database(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    db.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    yield engine
    engine.dispose()


def test_mixed_snapshot_preserves_each_row_source_without_migrating_weights(database):
    # Historical values are read, not rewritten: sources supersede old
    # method-weighting for new recommendations, never historical snapshots.
    with database.begin() as conn:
        conn.execute(insert(db.member_rankings_table), [
            {"league_id": "L", "user_id": "other", "player_id": pid,
             "elo": 1700.0, "scoring_format": "1qb_ppr",
             "confidence_source": source, "confidence_weight": weight,
             "comparison_count": count}
            for pid, source, weight, count in [
                ("s1", "seed", 0.0, 0), ("s2", "seed", 0.0, 0),
                ("v", "votes", 0.2, 1), ("c", "cross_format", 0.25, 0),
                ("e", "explicit", 1.0, 0), ("legacy", None, None, None)]])
    board = db.load_member_rankings("L", "me")["other"]
    assert board["confidence_source"] == "seed"
    assert board["confidence_sources"] == {
        "s1": "seed", "s2": "seed", "v": "votes",
        "c": "cross_format", "e": "explicit"}
    assert board["confidence_weights"]["v"] == 0.2
    weights = tp.confidence_map(board["comparison_counts"],
                                source=board["confidence_source"],
                                weights=board["confidence_weights"],
                                sources=board["confidence_sources"])
    assert weights == {"s1": 0.0, "s2": 0.0, "v": 1.0, "c": 1.0, "e": 1.0}


def test_copy_only_marks_the_players_actually_copied(database):
    players = [Player(id=p, name=p, position="WR", team="T", age=25)
               for p in ("copied", "below", "untouched")]
    svc = RankingService(players, seed_ratings={"copied": 1100.0, "below": 1600.0,
                                               "untouched": 1500.0})
    svc.apply_value_map("WR", ["copied", "below"])
    conf = server._ranking_confidence(svc, source="cross_format")
    payload = server._confidence_payload(
        [{"player_id": "copied", "elo": 1600.0},
         {"player_id": "untouched", "elo": 1500.0},
         {"player_id": "below", "elo": 1100.0}], conf)
    assert payload[0]["confidence_source"] == "cross_format"
    assert payload[1].get("confidence_source") is None
    assert payload[2].get("confidence_source") is None
    assert not any(key.startswith("_") for key in conf)
    db.upsert_member_rankings("other", "L", payload, "1qb_ppr", **conf)
    board = db.load_member_rankings("L", "me")["other"]
    weights = tp.confidence_map(board["comparison_counts"],
                                weights=board["confidence_weights"],
                                sources=board["confidence_sources"])
    assert weights["copied"] == 1.0
    assert weights["untouched"] == 0.0
    assert weights["below"] == 0.0

    # Copy mapped "below" away from consensus into no tier. Until source
    # markers are disambiguated durably, both perspectives consistently use
    # consensus, and an ordinary republish does not flip that interpretation.
    def context_for(board):
        return server._policy_context(
            user_id="me", user_elo={r["player_id"]: r["elo"] for r in payload},
            seed_elo=svc._seed, players_dict={p.id: p for p in players},
            league=SimpleNamespace(members=[SimpleNamespace(user_id="other",
                has_rankings=True, **board)]), confidence=svc.comparison_counts(),
            placements=svc.placement_bands(), scoring_format="1qb_ppr",
            requested_floor=None)

    for iteration in range(2):
        if iteration:
            conf = server._ranking_confidence(svc)
            clean_payload = [{"player_id": row["player_id"], "elo": row["elo"]}
                             for row in payload]
            ordinary = server._confidence_payload(clean_payload, conf)
            db.upsert_member_rankings("other", "L", ordinary, "1qb_ppr", **conf)
            board = db.load_member_rankings("L", "me")["other"]
        context = context_for(board)
        assert context["viewer_effective"]("below") == elo_to_value(1600.0)
        assert context["partners"]["other"]["effective"]("below") == elo_to_value(1600.0)


def test_policy_context_uses_per_player_provenance_not_snapshot_majority():
    player = Player(id="target", name="target", position="WR", team="T", age=25)
    partner = SimpleNamespace(user_id="other", has_rankings=True,
                              elo_ratings={"target": 1700.0},
                              comparison_counts={"target": 1},
                              confidence_weights={"target": 0.2},
                              confidence_source="seed",
                              confidence_sources={"target": "votes"})
    context = server._policy_context(
        user_id="me", user_elo={"target": 1700.0}, seed_elo={"target": 1500.0},
        players_dict={"target": player}, league=SimpleNamespace(members=[partner]),
        confidence={"target": 1}, placements={}, scoring_format="1qb_ppr",
        requested_floor=None)
    assert context["partners"]["other"]["effective"]("target") == elo_to_value(1700.0)
    assert context["viewer_effective"]("target") == elo_to_value(1700.0)
