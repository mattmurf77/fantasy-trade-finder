"""Projected slot value — the server wiring (flag `picks.projected_slot_value`).

Spec: docs/plans/pick-value-projected-slot/design.md §4.4–§4.5, §7, §8. The
pure math is pinned in `test_pick_projection.py`; this file pins what only the
server can get wrong. Most tests run FLAG ON (the intended shipped state):

  A. The reader `server._league_pick_projection`: the newest qualifying
     BASELINE run of ANY user in the league; scenario runs, other models,
     non-Sleeper leagues, the demo league and a failed read all give None;
     one DB read per TTL, knobs applied live.
  B. One number everywhere: the deck's injected Elo (seed, user and member
     boards — both sides of a trade), the calculator, eveners and power
     rankings agree on every pick; deck rules (filler, breakup) read the
     adjusted value.
  C. The projected slot on the wire (operator ruling 2026-11-11): every
     adjusted pick's name/label reads "2027 1.02 (from …) · projected" and
     carries `proj_slot` / `proj_name` at every client serialization site;
     unadjusted picks carry neither and keep today's exact name.
  D. Flag off is byte-identical to no feature at every surface, with a
     qualifying run sitting in the DB.
  E. Cache keys: vsn1 moves when, and only when, the projection key moves,
     and all three vsn1 call sites, the prepared receipt and the calibration
     provenance carry the key.
  F. The one seam, extended: no caller anywhere prices or labels an owned
     pick without the league projection; Win-Now goes through the same path.
"""
import ast
import json
import pathlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import backend.database as db
import backend.feature_flags as feature_flags
import backend.server as server
import backend.trade_service as ts
from backend import deck_quality, roster_snapshot
from backend.league_projections.core import VERSION
from backend.pick_values import priced_pool_value

REPO = pathlib.Path(__file__).resolve().parents[2]
LEAGUE = "990000000000000001"
FMT = "1qb_ppr"
FLAG = "picks.projected_slot_value"
GENERIC = 1859.5

# The design's §5 teams (12 teams, 6 playoff spots): roster 1 projected top 3,
# 2 bubble, 3 contender; 4–12 share the remaining column mass.
TOP3 = ([.40, .30, .15, .07, .03, 0], .05)
BUBBLE = ([.02, .04, .08, .12, .14, .15], .45)
CONTENDER = ([0, 0, 0, 0, .01, .02], .97)


def _result(*, model=VERSION, completed=9, future=5, season=2027, status="complete", rows=None,
            playoff=6):
    if rows is None:
        rows = {1: TOP3, 2: BUBBLE, 3: CONTENDER}
        used = [sum(r[0][k] for r in rows.values()) for k in range(6)]
        made = sum(r[1] for r in rows.values())
        for rid in range(4, 13):
            rows[rid] = ([(1 - u) / 9 for u in used], (6 - made) / 9)
    return {"status": status, "model_version": model, "completed_weeks": completed,
            "playoff_spots": playoff, "config": {"draft_season": season},
            "teams": [{"roster_id": rid, "pick_probabilities": p, "playoff_probability": m,
                       "weeks": [{}] * future} for rid, (p, m) in rows.items()]}


def _pick(rid, owner, *, season=2027, rnd=1, traded=False, original=None):
    return {"pick_id": f"{LEAGUE}_{season}_{rnd}_{rid}", "league_id": LEAGUE, "season": season,
            "round": rnd, "original_roster_id": rid, "owner_user_id": owner,
            "original_username": original or f"team{rid}", "owner_username": owner,
            "is_traded": 1 if traded else 0, "pool_value": 2117.0, "source": "platform"}


# owner u1 holds its own pick (roster 1, top 3) and roster 3's (contender, traded);
# u2 holds roster 2's (bubble) and a 2028 1st and a 2027 2nd.
PICKS = [_pick(1, "u1"), _pick(3, "u1", traded=True, original="contender"),
         _pick(2, "u2"), _pick(2, "u2", season=2028), _pick(2, "u2", rnd=2)]


@pytest.fixture
def world(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    db.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(db.leagues_table.insert().values(sleeper_league_id=LEAGUE, user_id="u1",
                                                      platform="sleeper"))
    state = SimpleNamespace(engine=engine, now=now, n=0)

    def add_run(user, result, *, age_hours=1, baseline=True, run_id=None):
        state.n += 1
        run_id = run_id or f"run{state.n}"
        stamp = (now - timedelta(hours=age_hours)).isoformat()
        with engine.begin() as conn:
            conn.execute(db.league_projection_runs_table.insert().values(
                run_id=run_id, user_id=user, league_id=LEAGUE, status=result.get("status", "complete"),
                created_at=stamp, updated_at=stamp, expires_at=stamp, request_hash="h",
                input_json=json.dumps({"kind": "baseline" if baseline else "scenario"}),
                result_json=json.dumps(result)))
            if baseline:
                t = db.league_projection_targets_table
                conn.execute(t.delete().where(t.c.user_id == user))
                conn.execute(t.insert().values(
                    target_id=f"t-{user}", user_id=user, league_id=LEAGUE, league_user_id=user,
                    season=2026, created_at=stamp, next_due_at=stamp, last_success_id=run_id))
        server._pick_projection_cache.clear()
        return run_id

    state.add_run = add_run
    flags = dict(feature_flags.flags_dict())
    flags[FLAG] = True
    flags["picks.slot_labels"] = True
    monkeypatch.setattr(feature_flags, "_flags_cache", flags)
    state.flags = flags
    monkeypatch.setattr(ts, "_cfg", dict(ts._DEFAULT_CFG))
    monkeypatch.setattr(server, "_league_slot_order", lambda lid: None)

    def load(league_id=None, owner_user_id=None, source=None, **_):
        return [dict(p) for p in PICKS if owner_user_id in (None, p["owner_user_id"])]
    monkeypatch.setattr(server, "load_draft_picks", load)
    server._pick_projection_cache.clear()
    add_run("u2", _result())
    yield state
    server._pick_projection_cache.clear()
    engine.dispose()


def _flag_off(world, monkeypatch):
    monkeypatch.setattr(feature_flags, "_flags_cache", {**world.flags, FLAG: False})
    server._pick_projection_cache.clear()


def _no_feature_value(p):
    return priced_pool_value(p, scoring_format=FMT)


# ═══════════════════════════════════════════════════════════════════════════
# A. The reader
# ═══════════════════════════════════════════════════════════════════════════

def test_reader_returns_any_users_baseline(world):
    proj = server._league_pick_projection(LEAGUE)
    assert proj is not None and proj.season == 2027 and proj.weight == 1.0
    assert server._priced_pick_value(PICKS[0], None, FMT, proj) == 3349.3


def test_reader_takes_the_newest_baseline_and_skips_scenarios_and_old_models(world):
    """Sabotage: drop the targets join → the newer scenario run is used."""
    base = server._league_pick_projection(LEAGUE).key
    world.add_run("u3", _result(completed=4, future=10), baseline=False, age_hours=0)  # scenario
    assert server._league_pick_projection(LEAGUE).key == base
    world.add_run("u4", _result(model="older-model", completed=10, future=4), age_hours=0)
    assert server._league_pick_projection(LEAGUE).key == base
    world.add_run("u5", _result(completed=10, future=4), age_hours=0)
    assert server._league_pick_projection(LEAGUE).key != base


def test_reader_gates(world, monkeypatch):
    assert server._league_pick_projection("league_demo") is None
    assert server._league_pick_projection("") is None
    with world.engine.begin() as conn:
        conn.execute(db.leagues_table.update().values(platform="espn"))
    server._pick_projection_cache.clear()
    assert server._league_pick_projection(LEAGUE) is None
    with world.engine.begin() as conn:
        conn.execute(db.leagues_table.update().values(platform="sleeper"))
    world.add_run("u2", _result(), age_hours=24 * 9)               # too old
    assert server._league_pick_projection(LEAGUE) is None
    world.add_run("u2", _result(completed=2, future=12))            # too few weeks
    assert server._league_pick_projection(LEAGUE) is None
    world.add_run("u2", _result(status="incomplete_projections"))   # not complete
    assert server._league_pick_projection(LEAGUE) is None


def test_reader_failure_prices_generic(world, monkeypatch):
    def boom(_lid):
        raise RuntimeError("db down")
    monkeypatch.setattr(server, "_load_pick_projection_summary", boom)
    server._pick_projection_cache.clear()
    assert server._league_pick_projection(LEAGUE) is None


def test_reader_reads_once_per_ttl_and_applies_knobs_live(world, monkeypatch):
    """Sabotage: cache the gated projection → the knob write waits out the TTL."""
    calls = []
    real = server._load_pick_projection_summary
    monkeypatch.setattr(server, "_load_pick_projection_summary",
                        lambda lid: calls.append(lid) or real(lid))
    server._pick_projection_cache.clear()
    for _ in range(5):
        assert server._league_pick_projection(LEAGUE) is not None
    assert calls == [LEAGUE]
    ts._cfg["pick_projection_weight"] = 0.0
    assert server._league_pick_projection(LEAGUE) is None
    assert calls == [LEAGUE]


def test_power_rankings_resolve_the_projection_once_per_league(world, monkeypatch):
    calls = []
    real = server._league_pick_projection
    monkeypatch.setattr(server, "_league_pick_projection", lambda lid: calls.append(lid) or real(lid))
    server._power_picks_by_owner(LEAGUE, FMT)
    assert calls == [LEAGUE]


# ═══════════════════════════════════════════════════════════════════════════
# B. One number everywhere
# ═══════════════════════════════════════════════════════════════════════════

def _deck(world):
    """Run the real deck injection for both owners."""
    members = [SimpleNamespace(user_id="u1", roster=[], elo_ratings={"x": 1.0}),
               SimpleNamespace(user_id="u2", roster=[], elo_ratings={"y": 1.0})]
    league = SimpleNamespace(members=members, platform="sleeper")
    service = SimpleNamespace(_players={})
    seed, user_elo = {}, {}
    seed, roster, n = server._inject_owned_picks(
        league_id=LEAGUE, scoring_format=FMT, trade_service=service, players_dict={},
        seed_map=seed, user_elo=user_elo, user_id="u1", user_roster=[], league=league,
        picks=[dict(p) for p in PICKS])
    return seed, user_elo, members, service


def test_every_surface_prices_the_same_number(world):
    """Sabotage: drop the projection at any one surface → that surface disagrees."""
    proj = server._league_pick_projection(LEAGUE)
    expected = {p["pick_id"]: server._priced_pick_value(p, None, FMT, proj) for p in PICKS}
    assert expected[PICKS[0]["pick_id"]] == 3349.3                 # top 3
    assert expected[PICKS[1]["pick_id"]] == 1028.8                 # contender, traded
    assert expected[PICKS[2]["pick_id"]] == 1702.6                 # bubble
    e2v = ts.elo_to_value
    seed, user_elo, members, _ = _deck(world)
    for pid, value in expected.items():
        assert e2v(seed[pid]) == pytest.approx(value, abs=0.05)      # consensus / card
        assert user_elo[pid] == seed[pid]                            # the viewer's side
        assert all(m.elo_ratings[pid] == seed[pid] for m in members)  # the partner's side
    _pool, _seed, pick_vals, _rows, seed_value = server._consensus_pricing(FMT, LEAGUE)
    assert pick_vals == expected                                     # the calculator
    power = server._power_picks_by_owner(LEAGUE, FMT)
    by_label = {i["label"]: i["value"] for items in power.values() for i in items}
    assert by_label["2027 1.01 \u00b7 projected"] == 3349.3
    eveners = server._roster_eveners(LEAGUE, "u1", 2800.0, set(), [], lambda pid: 0.0,
                                     scoring_format=FMT)
    ev = {e["id"]: e["value"] for e in eveners}
    assert ev[PICKS[0]["pick_id"]] == 3349.3


def test_deck_rules_read_the_adjusted_value(world, monkeypatch):
    """Filler and breakup run on the injected Elo (`_rules_first_deck_rules`'s
    market). A contender's 1st becomes filler next to a star; a projected top-3
    1st given for a lesser player becomes a breakup."""
    seed, *_ = _deck(world)
    v2e = ts.value_to_elo
    seed = {**seed, "star": v2e(6500.0), "star2": v2e(6000.0), "mid": v2e(1900.0)}
    market = lambda pid: ts.elo_to_value(seed[pid]) if pid in seed else None
    rule = lambda give, recv: deck_quality.card_rule(give, recv, "u2", viewer_id="u1",
                                                     market=market, position=lambda p: None,
                                                     rosters={}, caps=None)
    contender, top3 = PICKS[1]["pick_id"], PICKS[0]["pick_id"]
    assert rule(["star2", contender], ["star"]) == "filler"
    assert rule([top3], ["mid"]) == "breakup"
    _flag_off(world, monkeypatch)
    seed_off, *_ = _deck(world)
    seed_off = {**seed_off, "star": v2e(6500.0), "star2": v2e(6000.0), "mid": v2e(1900.0)}
    market_off = lambda pid: ts.elo_to_value(seed_off[pid]) if pid in seed_off else None
    rule_off = lambda give, recv: deck_quality.card_rule(give, recv, "u2", viewer_id="u1",
                                                         market=market_off, position=lambda p: None,
                                                         rosters={}, caps=None)
    assert rule_off(["star2", contender], ["star"]) is None
    assert rule_off([top3], ["mid"]) is None


# ═══════════════════════════════════════════════════════════════════════════
# C. The label tag
# ═══════════════════════════════════════════════════════════════════════════

# D-257: the label slot is the team's rank by expected slot. Top 3 (E 2.36)
# ranks 1st; the nine fillers (E 6.62) 2nd-10th by roster id; bubble (E 6.70)
# 11th; contender (E 9.39) 12th.
TOP3_NAME = "2027 1.01"
CONTENDER_NAME = "2027 1.12 (from contender)"
BUBBLE_NAME = "2027 1.11"
MARK = " \u00b7 projected"


def _fields(name):
    return {"proj_slot": name.split(" ")[1], "proj_name": name}


def test_label_names_the_projected_slot_on_every_adjusted_pick(world):
    """Sabotage: drop the marker → old builds show a projection as a fact;
    gate on a threshold → the bubble pick loses its slot."""
    proj = server._league_pick_projection(LEAGUE)
    label = lambda p: server._owned_pick_label(p, None, proj, FMT)
    assert label(PICKS[0]) == TOP3_NAME + MARK
    assert label(PICKS[1]) == CONTENDER_NAME + MARK                   # "(from …)" kept
    assert label(PICKS[2]) == BUBBLE_NAME + MARK                      # −8 %, still shown
    assert label(PICKS[3]) == "2028 1st"                              # other season
    assert label(PICKS[4]) == "2027 2nd"                              # round 2
    fields = lambda p: server._owned_pick_projection_fields(p, None, proj, FMT)
    assert fields(PICKS[0]) == _fields(TOP3_NAME)
    assert fields(PICKS[1]) == {"proj_slot": "1.12", "proj_name": CONTENDER_NAME}
    assert fields(PICKS[3]) == {} and fields(PICKS[4]) == {}


def test_real_slot_wins_over_the_projection(world):
    order = {"schema": 1, "season": 2027, "teams": 12, "type": "linear",
             "slots": {str(r): 13 - r for r in range(1, 13)}}       # projection says 1.01
    proj = server._league_pick_projection(LEAGUE)
    assert server._owned_pick_label(PICKS[0], order, proj, FMT) == "2027 1.12"
    assert server._owned_pick_projection_fields(PICKS[0], order, proj, FMT) == {}


def test_every_client_surface_carries_the_fields(world, monkeypatch):
    """Deck cards (player_to_dict), eveners, power rankings items (through
    compute_power_rankings) and the Matches name strings. Sabotage: drop the
    fields at any one site."""
    seed, _u, _m, service = _deck(world)
    card = server.player_to_dict(service._players[PICKS[0]["pick_id"]])
    assert (card["name"], card["proj_slot"], card["proj_name"]) == (TOP3_NAME + MARK, "1.01", TOP3_NAME)
    plain = server.player_to_dict(service._players[PICKS[3]["pick_id"]])
    assert plain["name"] == "2028 1st" and "proj_slot" not in plain and "proj_name" not in plain
    ev = {e["id"]: e for e in server._roster_eveners(LEAGUE, "u1", 3000.0, set(), [],
                                                      lambda pid: 0.0, scoring_format=FMT)}
    top = ev[PICKS[0]["pick_id"]]
    assert (top["name"], top["proj_slot"], top["proj_name"]) == (TOP3_NAME + MARK, "1.01", TOP3_NAME)
    power = server._power_picks_by_owner(LEAGUE, FMT)
    from backend.power_rankings import compute_power_rankings
    teams = compute_power_rankings([{"user_id": u, "username": u, "player_ids": []}
                                    for u in ("u1", "u2")], {}, {}, picks_by_owner=power)
    items = {i["label"]: i for t in teams for i in t["picks"]["items"]}
    assert (items[TOP3_NAME + MARK]["proj_slot"], items[TOP3_NAME + MARK]["proj_name"]) == \
        ("1.01", TOP3_NAME)
    assert "proj_slot" not in items["2028 1st"] and "proj_name" not in items["2028 1st"]
    with world.engine.begin() as conn:
        cols = set(db.draft_picks_table.c.keys())
        conn.execute(db.draft_picks_table.insert(), [{k: v for k, v in p.items() if k in cols}
                                                     for p in PICKS])
    matches = server._pick_labels_by_id([p["pick_id"] for p in PICKS])
    assert matches[PICKS[0]["pick_id"]] == TOP3_NAME + MARK          # Matches name strings
    assert matches[PICKS[3]["pick_id"]] == "2028 1st"


@pytest.mark.parametrize("n", [8, 10, 12, 14])
def test_projected_slot_format_for_every_league_size(n, world):
    """Two-digit slots, as `pick_slots.slot_suffix` / D-090 write them."""
    rows = {r: ([1.0 if k == r - 1 else 0.0 for k in range(n - 1)], 0.0 if r < n else 1.0)
            for r in range(1, n + 1)}
    world.add_run("u2", _result(rows=rows, playoff=1))
    proj = server._league_pick_projection(LEAGUE)
    assert proj.teams == n
    for r in (1, n):
        f = server._owned_pick_projection_fields(_pick(r, "u1"), None, proj, FMT)
        assert f == {"proj_slot": f"1.{r:02d}", "proj_name": f"2027 1.{r:02d}"}


def test_nothing_keys_picks_by_display_name(server_tree):
    """Asset ids are unchanged; the deck hashes and keys use ids, never `name`."""
    for fn in ("_deck_trade_hash", "_card_concept_id", "_significance_card_key"):
        node = _func(server_tree, fn)
        names = [n for n in ast.walk(node) if isinstance(n, ast.Constant) and n.value in ("name", "label")]
        attrs = [n for n in ast.walk(node) if isinstance(n, ast.Attribute) and n.attr in ("name", "label")]
        assert not names and not attrs, fn


# ═══════════════════════════════════════════════════════════════════════════
# D. Flag off: byte-identical to no feature
# ═══════════════════════════════════════════════════════════════════════════

def test_flag_off_is_byte_identical_to_no_feature(world, monkeypatch):
    """A qualifying run sits in the DB; with the flag off every surface equals
    the pre-feature computation (`priced_pool_value` without `projection`, the
    two-argument label). Sabotage: read the flag off FLAGS at import → priced."""
    _flag_off(world, monkeypatch)
    assert server._league_pick_projection(LEAGUE) is None
    expected = {p["pick_id"]: _no_feature_value(p) for p in PICKS}
    assert set(expected.values()) >= {GENERIC}
    seed, user_elo, members, service = _deck(world)
    for p in PICKS:
        pid = p["pick_id"]
        assert ts.elo_to_value(seed[pid]) == pytest.approx(expected[pid], abs=0.05)
        assert service._players[pid].name == server._owned_pick_label(p, None)
        card = server.player_to_dict(service._players[pid])
        assert "proj_slot" not in card and "proj_name" not in card
    assert server._consensus_pricing(FMT, LEAGUE)[2] == expected
    power = server._power_picks_by_owner(LEAGUE, FMT)
    assert not any({"proj_slot", "proj_name"} & set(i) for v in power.values() for i in v)
    items = sorted((i["label"], i["value"]) for v in power.values() for i in v)
    assert items == sorted((server._owned_pick_label(p, None), round(expected[p["pick_id"]], 1))
                           for p in PICKS)
    ev = server._roster_eveners(LEAGUE, "u1", 1859.5, set(), [], lambda pid: 0.0, scoring_format=FMT)
    for e in ev:
        p = next(p for p in PICKS if p["pick_id"] == e["id"])
        assert (e["name"], e["value"]) == (server._owned_pick_label(p, None),
                                           round(expected[e["id"]], 1))
        assert "proj_slot" not in e and "proj_name" not in e


def test_weight_zero_is_the_same_as_flag_off(world):
    ts._cfg["pick_projection_weight"] = 0.0
    assert server._league_pick_projection(LEAGUE) is None
    assert server._pick_projection_key(LEAGUE) is None


# ═══════════════════════════════════════════════════════════════════════════
# E. Cache keys
# ═══════════════════════════════════════════════════════════════════════════

def _vsn(key):
    pool = {"seed": {"p1": 1600.0}, "players": []}
    with db.engine.connect() as conn:
        return roster_snapshot.values_snapshot_id(conn, FMT, LEAGUE, pool, pick_source="platform",
                                                  pick_projection_key=key)


def test_vsn_moves_iff_the_projection_key_moves(world, monkeypatch):
    monkeypatch.setattr(roster_snapshot, "_read_picks", lambda conn, lid, src: PICKS)
    pool = {"seed": {"p1": 1600.0}, "players": []}
    with db.engine.connect() as conn:
        legacy = roster_snapshot.values_snapshot_id(conn, FMT, LEAGUE, pool, pick_source="platform")
    assert _vsn(None) == legacy                       # no key: unchanged vsn1
    k1 = server._pick_projection_key(LEAGUE)
    assert k1 and _vsn(k1) != legacy and _vsn(k1) == _vsn(k1)
    world.add_run("u2", _result(completed=10, future=4))
    k2 = server._pick_projection_key(LEAGUE)
    assert k2 != k1 and _vsn(k2) != _vsn(k1)
    with db.engine.connect() as conn:
        assert roster_snapshot.snapshot_ids(conn, FMT, LEAGUE, pool, pick_source="platform",
                                            pick_projection_key=k2)[1] == _vsn(k2)


def _func(tree, name):
    return next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)


def _calls(node, name):
    return [c for c in ast.walk(node) if isinstance(c, ast.Call)
            and ((isinstance(c.func, ast.Name) and c.func.id == name)
                 or (isinstance(c.func, ast.Attribute) and c.func.attr == name))]


@pytest.fixture(scope="module")
def server_tree():
    return ast.parse((REPO / "backend" / "server.py").read_text())


def test_all_vsn_sites_pass_the_same_projection_key(server_tree):
    """Sabotage: drop `pick_projection_key=` at any of the three sites → a
    stored page or job outlives a new forecast."""
    sites = _calls(server_tree, "values_snapshot_id") + _calls(server_tree, "snapshot_ids")
    assert len(sites) == 3
    for call in sites:
        kw = {k.arg: k.value for k in call.keywords}
        assert isinstance(kw.get("pick_projection_key"), ast.Name)
        assert kw["pick_projection_key"].id == "projection_key"
    for fn in ("_trade_current_snapshot", "_trade_current_fingerprints", "_share_value_snapshot"):
        assigns = [a for a in ast.walk(_func(server_tree, fn)) if isinstance(a, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "projection_key" for t in a.targets)]
        assert len(assigns) == 1 and _calls(assigns[0], "_pick_projection_key"), fn


@pytest.mark.parametrize("path,func", [("backend/prepared_trade_runtime.py", None),
                                       ("backend/outlook_calibration_adapter.py", "_input_identity")])
def test_receipt_and_provenance_carry_the_key(path, func):
    """Sabotage: delete the `pick_projection` entry → a prepared deck or a
    graded calibration keeps last week's prices."""
    tree = ast.parse((REPO / path).read_text())
    scope = _func(tree, func) if func else tree
    keyed = [d for d in ast.walk(scope) if isinstance(d, ast.Dict)
             and any(isinstance(k, ast.Constant) and k.value == "pick_projection" for k in d.keys)]
    assert keyed, "no pick_projection entry"
    assert _calls(scope, "_pick_projection_key")


def test_new_module_is_in_the_engine_code_hash():
    assert "pick_projection.py" in server._ENGINE_CODE_MODULES
    assert server.DECK_PIPELINE_VERSION >= 23
    for name in ("_league_pick_projection", "_load_pick_projection_summary"):
        assert name in server.DECK_PIPELINE_FUNCTIONS


# ═══════════════════════════════════════════════════════════════════════════
# F. The one seam, extended
# ═══════════════════════════════════════════════════════════════════════════

_SEAM_CALLERS = {"_roster_eveners", "_consensus_pricing", "get_league_picks", "_owned_pick_assets",
                 "_power_picks_by_owner", "_build_trade_roster_context"}
_LABEL_SITES = {"_roster_eveners", "get_league_picks", "_owned_pick_assets", "_power_picks_by_owner",
                "_pick_labels_by_id"}


def _backend_trees():
    for path in sorted((REPO / "backend").rglob("*.py")):
        if "tests" in path.parts:
            continue
        yield path, ast.parse(path.read_text())


def test_every_owned_pick_price_carries_the_projection():
    """No caller in the backend prices an owned pick without the league
    projection: `_priced_pick_value` always gets its 4th positional argument,
    and `priced_pool_value` (outside pick_values) always gets `projection=`.
    Sabotage: drop the argument at any site."""
    seen = 0
    for path, tree in _backend_trees():
        for call in _calls(tree, "_priced_pick_value"):
            assert len(call.args) == 4, f"{path.name}:{call.lineno}"
            seen += 1
        if path.name != "pick_values.py":
            for call in _calls(tree, "priced_pool_value"):
                assert "projection" in {k.arg for k in call.keywords}, f"{path.name}:{call.lineno}"
    assert seen >= 7


def test_every_seam_caller_hoists_the_projection(server_tree):
    for name in _SEAM_CALLERS | _LABEL_SITES:
        fn = _func(server_tree, name)
        assert len(_calls(fn, "_league_pick_projection")) == 1, name
        loops = [n for n in ast.walk(fn) if isinstance(n, (ast.For, ast.comprehension))]
        for loop in loops:
            inner = loop.body if isinstance(loop, ast.For) else []
            for stmt in inner:
                if name != "_pick_labels_by_id":    # one per DISTINCT league, memoised
                    assert not _calls(stmt, "_league_pick_projection"), name


def test_every_label_site_passes_the_projection(server_tree):
    for name in _LABEL_SITES:
        for call in _calls(_func(server_tree, name), "_owned_pick_label"):
            assert len(call.args) >= 3, f"{name}:{call.lineno}"


def test_every_client_asset_site_attaches_the_fields(server_tree):
    """The client contract: every site that serializes an owned pick AS AN
    ASSET carries `proj_slot` / `proj_name`. `_pick_labels_by_id` returns bare
    name strings (Matches arrays), so it carries the marker text only.
    Sabotage: drop `_owned_pick_projection_fields` at any site."""
    for name in _LABEL_SITES - {"_pick_labels_by_id"}:
        assert _calls(_func(server_tree, name), "_owned_pick_projection_fields"), name
    overhaul = ast.parse((REPO / "backend" / "overhaul_api.py").read_text())
    assert _calls(overhaul, "pick_projection_fields")


def test_win_now_and_overhaul_use_the_same_projection(server_tree):
    tree = ast.parse((REPO / "backend" / "win_now_service.py").read_text())
    build = _func(tree, "build_context")
    assert _calls(build, "_pick_projection")
    assert _calls(_func(tree, "_pick_projection"), "_league_pick_projection")
    install = [c for c in _calls(server_tree, "_install_overhaul")] or \
        [c for c in ast.walk(server_tree) if isinstance(c, ast.Call)
         and any(k.arg == "priced_pick_value" for k in c.keywords)]
    kw = {k.arg: k.value for k in install[0].keywords}
    assert isinstance(kw.get("pick_projection"), ast.Name)
    assert kw["pick_projection"].id == "_league_pick_projection"
    assert kw["pick_projection_fields"].id == "_owned_pick_projection_fields"
