"""Sleeper trade universe crawler: discovery (research-plan §5.1, decisions 1, 3, 4).

Covers: breadth-first walk with de-duplication of users and leagues; the hop
limit; the lineage cap (and reviving cap-deferred leagues); lineage across
seasons and the season-range stop; the dynasty filter with every skip
reason; the --seasons flag (a narrow run then a wider run keeps lineage ids
and completed league-seasons); discovery state holds no raw user id.
Synthetic world only (backend/tests/support/sleeper_universe_world.py).
"""
from __future__ import annotations

import json
from collections import Counter

from backend.tests.support.sleeper_universe_world import L, U, connect, run_cli, standard_world


def _index(d):
    c = connect(d)
    rows = {r["league_id"]: dict(r) for r in c.execute("SELECT * FROM league_index")}
    c.close()
    return rows


def test_dedup_each_user_and_league_read_once(tmp_path):
    w = standard_world()
    code, _ = run_cli(w, tmp_path, "discover")
    assert code == 0
    listings = Counter(p for p in w.calls if "/leagues/nfl/" in p)
    assert listings and max(listings.values()) == 1
    rosters = Counter(p for p in w.calls if p.endswith("/rosters"))
    assert max(rosters.values()) == 1
    # user 3 sits in lineage A and league B; user 10 in B and C: listed once each
    assert listings[f"user/{U(3)}/leagues/nfl/2026"] == 1
    assert listings[f"user/{U(10)}/leagues/nfl/2025"] == 1


def test_hop_limit(tmp_path):
    idx = _index(_run(tmp_path / "h2", "--hops", "2"))
    assert idx[L(101)]["hop"] == 0 and idx[L(201)]["hop"] == 1 and idx[L(301)]["hop"] == 2
    assert L(401) not in idx
    idx3 = _index(_run(tmp_path / "h3", "--hops", "3"))
    assert idx3[L(401)]["hop"] == 3 and idx3[L(401)]["kept"] == 1


def _run(d, *extra):
    w = standard_world()
    code, _ = run_cli(w, d, "discover", *extra)
    assert code == 0
    return d


def test_cap_counts_lineages_and_defers(tmp_path):
    w = standard_world()
    # the seed also sits in lineage C, so its own listing crosses the cap
    w.listing_add(U(1), 2025, w.routes[f"league/{L(301)}"])
    run_cli(w, tmp_path, "discover", "--cap", "1")
    idx = _index(tmp_path)
    kept = {r["lineage_id"] for r in idx.values() if r["kept"]}
    assert kept == {L(103)}
    assert {lid for lid, r in idx.items() if r["kept"]} == {L(101), L(102), L(103)}
    assert idx[L(301)]["skip_reason"] == "cap_reached" and idx[L(301)]["kept"] == 0
    # a later run with room revives the deferred leagues
    w2 = standard_world()
    w2.listing_add(U(1), 2025, w2.routes[f"league/{L(301)}"])
    run_cli(w2, tmp_path, "discover", "--cap", "10")
    idx = _index(tmp_path)
    assert idx[L(201)]["kept"] == 1 and idx[L(301)]["kept"] == 1
    assert not any(r["skip_reason"] == "cap_reached" for r in idx.values())


def test_lineage_and_season_range(tmp_path):
    idx = _index(_run(tmp_path))
    assert {idx[L(n)]["lineage_id"] for n in (101, 102, 103)} == {L(103)}
    assert idx[L(201)]["lineage_id"] == L(201)
    assert L(200) not in idx       # its 2023 predecessor is outside the range


def test_dynasty_filter_records_every_skip_reason(tmp_path):
    d = _run(tmp_path)
    c = connect(d)
    skipped = {r["league_id"]: r["reason"] for r in c.execute("SELECT * FROM skipped_leagues")}
    assert skipped == {L(501): "not_dynasty", L(502): "best_ball", L(503): "team_count",
                       L(504): "not_started", L(505): "not_dynasty"}
    assert set(c.execute("SELECT * FROM skipped_leagues").fetchone().keys()) == {
        "league_id", "season", "reason"}


def test_seasons_flag_then_widening_keeps_lineage_ids_and_checkpoints(tmp_path):
    w = standard_world()
    code, _ = run_cli(w, tmp_path, "run", "--seasons", "2026")
    assert code == 0
    idx = _index(tmp_path)
    assert {r["season"] for r in idx.values() if r["kept"]} == {2026}
    lin_2026 = idx[L(103)]["lineage_id"]
    c = connect(tmp_path)
    assert json.loads(c.execute("SELECT params_json FROM runs").fetchone()[0])["seasons"] == [2026]
    done_before = {r[0] for r in c.execute("SELECT league_id FROM pull_checkpoints")}
    c.close()
    w2 = standard_world()
    code, _ = run_cli(w2, tmp_path, "run")
    assert code == 0
    idx = _index(tmp_path)
    assert idx[L(103)]["lineage_id"] == lin_2026
    assert idx[L(101)]["lineage_id"] == lin_2026 and idx[L(102)]["lineage_id"] == lin_2026
    # completed 2026 league-seasons were not pulled again
    for lid in done_before:
        assert not any(p == f"league/{lid}/users" for p in w2.calls)
    assert any(p == f"league/{L(101)}/users" for p in w2.calls)


def test_discovery_state_holds_no_raw_user_id(tmp_path):
    w = standard_world()
    run_cli(w, tmp_path, "discover")
    blob = (tmp_path / "universe.sqlite").read_bytes()
    for uid in w.all_user_ids():
        assert uid.encode() not in blob
