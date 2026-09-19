"""Local seeding keeps profile identities, ranked pairs and dry-run isolation."""
from types import SimpleNamespace

import pytest
from sqlalchemy import Column, Float, Integer, MetaData, String, Table, create_engine, insert, select

from scripts.fixtures.seed_rankings import find_player_id, generate_swipes, load_profile, seed_user


@pytest.fixture
def database():
    metadata = MetaData()
    users = Table("users", metadata,
                  Column("sleeper_user_id", String, primary_key=True),
                  Column("username", String), Column("display_name", String),
                  Column("avatar", String), Column("created_at", String))
    players = Table("players", metadata, Column("player_id", String, primary_key=True),
                    Column("full_name", String))
    swipes = Table("swipe_decisions", metadata, Column("id", Integer, primary_key=True),
                   Column("user_id", String), Column("winner_player_id", String),
                   Column("loser_player_id", String), Column("decision_type", String),
                   Column("k_factor", Float), Column("created_at", String))
    engine = create_engine("sqlite://")
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(insert(players), [
            {"player_id": "may", "full_name": "Drake Maye"},
            {"player_id": "all", "full_name": "Josh Allen"},
            {"player_id": "dan", "full_name": "Jayden Daniels"},
            {"player_id": "wil", "full_name": "Caleb Williams"},
        ])
        conn.execute(insert(swipes), [
            {"user_id": "test_user_fp_1", "winner_player_id": "old", "loser_player_id": "row"},
            {"user_id": "unrelated", "winner_player_id": "keep", "loser_player_id": "me"},
        ])
    yield SimpleNamespace(engine=engine, users_table=users, players_table=players,
                          swipe_decisions_table=swipes)
    engine.dispose()


def rows(database, table):
    with database.engine.connect() as conn:
        return [dict(row) for row in conn.execute(select(table)).mappings()]


def test_dry_run_with_clear_preserves_existing_rows_and_creates_no_user(database):
    before = rows(database, database.swipe_decisions_table)
    seed_user(load_profile("fantasypros-2025"), database, dry_run=True, clear=True)
    assert rows(database, database.swipe_decisions_table) == before
    assert rows(database, database.users_table) == []


@pytest.mark.parametrize("name,user_id,username,display_name,expected", [
    ("fantasypros-2025", "test_user_fp_1", "fp_ranker_1", "FP Ranker 1",
     [("may", "all"), ("all", "dan"), ("dan", "wil")]),
    ("fantasypros-2026", "test_user_fp_2", "fp_ranker_2", "FP Ranker 2",
     [("may", "all"), ("all", "wil"), ("wil", "dan")]),
])
def test_profiles_preserve_distinct_ranked_pairs_and_only_clear_their_own_rows(
        database, name, user_id, username, display_name, expected):
    profile = load_profile(name)
    seed_user(profile, database, clear=True)
    users = rows(database, database.users_table)
    assert [(u["sleeper_user_id"], u["username"], u["display_name"]) for u in users] == [
        (user_id, username, display_name)]
    swipes = rows(database, database.swipe_decisions_table)
    seeded = [r for r in swipes if r["user_id"] == user_id]
    assert [(r["winner_player_id"], r["loser_player_id"]) for r in seeded] == expected
    assert all(r["decision_type"] == "rank" and r["k_factor"] == 32.0 for r in seeded)
    assert any(r["user_id"] == "unrelated" and r["winner_player_id"] == "keep" for r in swipes)
    if user_id == "test_user_fp_2":
        assert any(r["user_id"] == "test_user_fp_1" and r["winner_player_id"] == "old" for r in swipes)
    # Replacing an existing profile does not create a duplicate user or append pairs.
    seed_user(profile, database, clear=True)
    assert len(rows(database, database.users_table)) == 1
    assert len([r for r in rows(database, database.swipe_decisions_table)
                if r["user_id"] == user_id]) == 3


def test_matching_retains_punctuation_alias_suffix_and_initial_fallbacks():
    profile = load_profile("fantasypros-2025")
    index = {"amonra st brown": "alias", "luther burden": "suffix", "nicholas chubb": "initial"}
    assert find_player_id("Amon-Ra St. Brown", index, profile["aliases"]) == "alias"
    assert find_player_id("Amon Ra St Brown", index, profile["aliases"]) == "alias"
    assert find_player_id("Luther Burden III", index, profile["aliases"]) == "suffix"
    assert find_player_id("Nick Chubb", index, profile["aliases"]) == "initial"
    assert find_player_id("Unknown Person", index, profile["aliases"]) is None


def test_swipes_keep_best_to_worst_order_and_complete_interactions():
    assert generate_swipes([]) == []
    assert generate_swipes(["a", "b"]) == []
    assert generate_swipes(["a", "b", "c"]) == [("a", "b"), ("b", "c"), ("a", "c")]
    ordered = [str(n) for n in range(50)]
    pairs = generate_swipes(ordered)
    assert len(pairs) == 48
    assert pairs == [(str(n), str(n + 1)) for n in range(48)]
