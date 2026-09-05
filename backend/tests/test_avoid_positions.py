"""#360/#361 — "Avoiding" positions.

A receive-side POSITIONAL exclusion: the positional twin of #163
`not_interested`, applied at RECEIVE-POOL CONSTRUCTION on every live
generator path (v3, the v3 sweetener, v2, consensus, asset ideas, the
likes-you injector), never as a relaxable gate.

Every test below names, in its docstring, the sabotage that must turn it
RED. A test whose sabotage cannot be stated is a test that cannot fail.

Harness is the #163 sibling (`test_not_interested.py`): position-complete
rosters so the v3 lineup-feasibility hard gate does not veto every combo,
and the route half exercised through Flask's test client against an
isolated in-memory SQLite engine (`test_awaiting_dismiss.py` pattern).
"""
import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text

import backend.database as db
import backend.feature_flags as ff
import backend.server as server
import backend.trade_service as ts
from backend.trade_service import (
    League, LeagueMember, TradeService, avoid_ok, _pos_for_avoid,
)


@pytest.fixture(autouse=True)
def _isolate():
    old_flags = ff._flags_cache
    old_cfg = dict(ts._cfg)
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "trade_engine.v2": True,
                       "trade.avoid_positions": True}
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    try:
        yield
    finally:
        ff._flags_cache = old_flags
        ts._cfg.clear()
        ts._cfg.update(old_cfg)


class _Player:
    def __init__(self, pid, position="RB", team="TST", age=25, search_rank=50):
        self.id = pid
        self.name = f"Player {pid}"
        self.position = position
        self.team = team
        self.age = age
        self.search_rank = search_rank
        self.pick_value = None


# ---------------------------------------------------------------------------
# T-1 / T-2 / T-11 / T-14 — storage + HTTP contract
# ---------------------------------------------------------------------------

def test_column_defaults_to_empty_list():
    """T-1 (R-1) — a fresh row AND a pre-migration row (SQL NULL) both read
    []. No backfill; _parse_positions maps every falsy raw value to [].

    SABOTAGE: make _parse_positions return None for falsy input, or drop the
    ("league_preferences", "avoid_positions", "TEXT") migration_cols entry.
    """
    db.metadata.create_all(db.engine)
    uid, lid = "u_av_col", "L_av_col"
    db.upsert_league_preference(user_id=uid, league_id=lid,
                                team_outlook="contender")
    assert db.load_league_preference(user_id=uid, league_id=lid)[
        "avoid_positions"] == []

    # A row whose column is literally NULL — the pre-existing-row case.
    with db.engine.begin() as conn:
        conn.execute(text("UPDATE league_preferences SET avoid_positions = NULL "
                          "WHERE user_id = :u AND league_id = :l"),
                     {"u": uid, "l": lid})
    assert db.load_league_preference(user_id=uid, league_id=lid)[
        "avoid_positions"] == []

    # The migration entry itself, so dropping it is a red test rather than a
    # silent prod-only failure (SQLite create_all would still pass without it).
    assert ("league_preferences", "avoid_positions", "TEXT") in \
        _migration_cols(), "the _migrate_db() entry is missing"


def _migration_cols():
    """The literal migration_cols list inside _migrate_db, read out of the
    source. There is no _ensure_columns helper and no Alembic in this repo."""
    import inspect
    import re
    src = inspect.getsource(db._migrate_db)
    return [tuple(m) for m in re.findall(
        r'\(\s*"([^"]+)",\s*"([^"]+)",\s*"([^"]+)"\s*\)', src)]


def test_upsert_round_trip_and_clear():
    """T-1b — [] clears, a list stores, None leaves alone."""
    db.metadata.create_all(db.engine)
    uid, lid = "u_av_rt", "L_av_rt"
    db.upsert_league_preference(user_id=uid, league_id=lid,
                                team_outlook="contender",
                                avoid_positions=["QB", "TE"])
    assert db.load_league_preference(user_id=uid, league_id=lid)[
        "avoid_positions"] == ["QB", "TE"]
    db.upsert_league_preference(user_id=uid, league_id=lid,
                                team_outlook="contender", avoid_positions=[])
    assert db.load_league_preference(user_id=uid, league_id=lid)[
        "avoid_positions"] == []


# ── route harness ──────────────────────────────────────────────────────────

@pytest.fixture()
def prefs_client():
    """Isolated DB + injected session for /api/league/preferences."""
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False})
    db.metadata.create_all(eng)

    class _L:
        league_id = "L_pref"
        name = "T"
        members = []

    token = "avoid-prefs-sess"
    sess = {"verified": True, "user_id": "u_pref", "league": _L(), "players": [],
            "trade_svc": object(), "active_format": "1qb_ppr",
            "last_active": 0.0, "user_roster": []}
    server.app.config["TESTING"] = True
    client = server.app.test_client()
    with patch.object(db, "engine", eng), \
         patch.object(server, "_invalidate_trade_jobs", lambda **kw: 0):
        with server._sessions_lock:
            server._sessions[token] = sess
        try:
            yield client, token
        finally:
            with server._sessions_lock:
                server._sessions.pop(token, None)


def _get_prefs(client, token):
    return client.get("/api/league/preferences?league_id=L_pref",
                      headers={"X-Session-Token": token})


def _post_prefs(client, token, body):
    b = {"league_id": "L_pref", "team_outlook": "contender"}
    b.update(body)
    return client.post("/api/league/preferences", json=b,
                       headers={"X-Session-Token": token})


@pytest.mark.parametrize("flag_on", [True, False])
def test_prefs_route_roundtrip(prefs_client, flag_on):
    """T-2 (R-2, R-3) — GET always returns avoid_positions (array, never
    null, never absent) in BOTH flag states and whether or not a row exists;
    POST accepts and stores it in both states. The PERSISTENCE layer is
    deliberately not flag-gated: a kill-switch flip must never destroy data.

    SABOTAGE: remove avoid_positions from the GET payload dict (or from the
    no-row fallback literal), or from the upsert_league_preference call.
    """
    client, token = prefs_client
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "trade.avoid_positions": flag_on}

    # No row yet — the fallback literal.
    r = _get_prefs(client, token)
    assert r.status_code == 200
    assert r.get_json()["avoid_positions"] == []

    r = _post_prefs(client, token, {"avoid_positions": ["QB", "PICK"]})
    assert r.status_code == 200
    assert r.get_json()["avoid_positions"] == ["QB", "PICK"]

    r = _get_prefs(client, token)
    assert r.get_json()["avoid_positions"] == ["QB", "PICK"]


def test_post_normalizes_and_echoes(prefs_client):
    """T-11 (R-3) — uppercase, trim, dedupe order-preserving; tokens outside
    {QB,RB,WR,TE,PICK} are DROPPED, not rejected; the response echoes the
    NORMALIZED, STORED list so the drop is not silent.

    SABOTAGE: skip normalization — ["qb","DEF","QB"] stores verbatim and the
    echo lies about what was stored.
    """
    client, token = prefs_client
    r = _post_prefs(client, token,
                    {"avoid_positions": ["te", " QB ", "QB", "DEF", 7, None]})
    assert r.status_code == 200
    assert r.get_json()["avoid_positions"] == ["TE", "QB"]
    assert _get_prefs(client, token).get_json()["avoid_positions"] == ["TE", "QB"]


@pytest.mark.parametrize("bad", ["QB", 7, {"a": 1}, True])
def test_post_rejects_non_list(prefs_client, bad):
    """T-11b (R-3) — a non-list is a 400, matching the two siblings."""
    client, token = prefs_client
    r = _post_prefs(client, token, {"avoid_positions": bad})
    assert r.status_code == 400
    assert r.get_json()["error"] == "avoid_positions must be an array"


def test_post_omitting_avoid_preserves_stored_value(prefs_client):
    """T-14 (PRD §5.3) — a POST that OMITS avoid_positions leaves a stored
    non-empty value intact. This is what makes a web save (which sends only
    acquire/trade_away) non-destructive.

    SABOTAGE: make upsert_league_preference write [] when the field is
    absent; a web save then wipes a mobile-set avoid list.
    """
    client, token = prefs_client
    _post_prefs(client, token, {"avoid_positions": ["QB"]})
    r = _post_prefs(client, token, {"acquire_positions": ["WR"]})   # no avoid key
    assert r.status_code == 200
    assert _get_prefs(client, token).get_json()["avoid_positions"] == ["QB"]
    # null behaves like absent.
    _post_prefs(client, token, {"avoid_positions": None})
    assert _get_prefs(client, token).get_json()["avoid_positions"] == ["QB"]
    # [] clears.
    _post_prefs(client, token, {"avoid_positions": []})
    assert _get_prefs(client, token).get_json()["avoid_positions"] == []


# ---------------------------------------------------------------------------
# T-4 — no served card sends the user an avoided position, on every path
# ---------------------------------------------------------------------------

_U_ROSTER = [("uq", "QB"), ("G", "RB"), ("ur2", "RB"),
             ("uw1", "WR"), ("uw2", "WR"), ("ute", "TE")]
_O_ROSTER = [("oq", "QB"), ("R", "RB"), ("or2", "RB"),
             ("ow1", "WR"), ("ow2", "WR"), ("ote", "TE")]
_ALL = _U_ROSTER + _O_ROSTER


def _divergence_svc(extra=()):
    players = {pid: _Player(pid, pos) for pid, pos in _ALL}
    for pid, pos, team in extra:
        players[pid] = _Player(pid, pos, team=team)
    opp_elo = {pid: 1500 for pid, _ in _ALL}
    opp_elo["G"] = 1700               # opponent covets the user's G
    for pid, _pos, _t in extra:
        opp_elo[pid] = 1500
    opp = LeagueMember(user_id="opp", username="opp",
                       roster=[pid for pid, _ in _O_ROSTER] + [p for p, _, _ in extra],
                       elo_ratings=opp_elo, has_rankings=True)
    s = TradeService(players=players)
    s.add_league(League(league_id="L1", name="T", platform="demo", members=[opp]))
    return s


def _gen_divergence(svc, extra=(), **kw):
    kw.setdefault("fairness_threshold", 0.05)
    user_elo = {pid: 1500 for pid, _ in _ALL}
    user_elo["R"] = 1700              # user covets the opponent's R (an RB)
    user_elo["ow1"] = 1700            # …and ow1 (a WR), so the baseline deck
                                      # contains a WR on the RECEIVE side and
                                      # "avoid WR" has something to remove
    # Coveted receive assets are seeded at PARITY with G (1540): since
    # origin/main d42872f2 ("package pricing honesty + gap auto-sweetener",
    # 2026-08-22, #162) a 1-for-1 that loses seed value for the giver is no
    # longer admitted, so a 1500-seed receive target never surfaces against
    # the 1540-seed G and the baseline premise ("the deck offers a WR /
    # the extra asset") fails before Avoiding is ever exercised.
    seed = {pid: (1540 if pid in ("G", "R", "ow1") else 1500)
            for pid, _ in _ALL}
    for pid, _pos, _t in extra:
        user_elo[pid] = 1700
        seed[pid] = 1540
    return svc.generate_trades(
        user_id="user",
        user_elo=user_elo,
        user_roster=[pid for pid, _ in _U_ROSTER],
        league_id="L1",
        seed_elo=seed,
        **kw,
    )


def _consensus_svc():
    players = {"G": _Player("G", "RB"), "R": _Player("R", "WR"),
               "R2": _Player("R2", "WR"), "OQ": _Player("OQ", "QB")}
    opp = LeagueMember(user_id="opp", username="opp", roster=["R", "R2", "OQ"],
                       elo_ratings={}, has_rankings=False)
    s = TradeService(players=players)
    s.add_league(League(league_id="L1", name="T", platform="demo", members=[opp]))
    return s


def _gen_consensus(svc, **kw):
    kw.setdefault("fairness_threshold", 0.55)
    return svc.generate_trades(
        user_id="user",
        user_elo={"G": 1540, "R": 1590, "R2": 1585, "OQ": 1590},
        user_roster=["G"],
        league_id="L1",
        seed_elo={"G": 1540, "R": 1590, "R2": 1585, "OQ": 1590},
        **kw,
    )


@pytest.mark.parametrize("path", ["v3", "v2", "consensus"])
def test_no_avoided_position_received(path):
    """T-4 (R-4) — parameterized over the generator paths so a single-seam
    miss is visible. Avoiding WR ⇒ no card sends the user a WR, on any path;
    other returns still surface.

    SABOTAGE: remove `and avoid_ok(...)` from any ONE of the receive-pool
    comprehensions (trade_optimizer.known_opp, _generate_for_pair_v2's
    _known_opp, _generate_consensus_for_pair's _opp_pool).
    """
    if path == "consensus":
        pos = {"G": "RB", "R": "WR", "R2": "WR", "OQ": "QB"}
        base = _gen_consensus(_consensus_svc())
        guarded = _gen_consensus(_consensus_svc(), avoid_positions=["WR"])
    else:
        pos = dict(_ALL)
        ff._flags_cache = {**ff.DEFAULT_FLAGS, "trade_engine.v2": True,
                           "trade_engine.v3": path == "v3",
                           "trade.avoid_positions": True}
        base = _gen_divergence(_divergence_svc())
        guarded = _gen_divergence(_divergence_svc(), avoid_positions=["WR"])

    def _recv_positions(cards):
        return {pos.get(p) for c in cards for p in c.receive_player_ids}

    assert "WR" in _recv_positions(base), f"{path} fixture must offer a WR"
    assert "WR" not in _recv_positions(guarded)
    assert guarded, f"{path}: other returns must still surface"


def test_v3_sweetener_never_adds_an_avoided_position():
    """T-4b (R-4, seam 2) — the v3 sweetener adds ONE cheap player from the
    under-paying side. When that side is `receive`, an avoided position must
    not be eligible.

    SABOTAGE: drop the `side == "receive" and not avoid_ok(...)` clause from
    _try_sweeten's candidate comprehension; the QB sweetener comes back.
    """
    from backend import trade_optimizer as topt
    players = {"ug": _Player("ug", "RB"), "orb": _Player("orb", "RB"),
               "oq": _Player("oq", "QB")}
    vals = {"ug": 100.0, "orb": 60.0, "oq": 30.0}

    def _seed(pid):
        return vals[pid]

    kw = dict(user_roster=["ug"], opp_roster=["orb", "oq"], seed_value=_seed,
              fairness_threshold=0.5, min_side=1,
              surpluses=lambda g, r: (1.0, 1.0), gap_ok=lambda g, r: True,
              both_feasible=lambda g, r: True, players=players)
    # Receive side under-pays (60 < 100), so the sweetener comes from the
    # OPPONENT's roster — i.e. onto the user's RECEIVE side.
    base = topt._try_sweeten(["ug"], ["orb"], **kw)
    assert base is not None and base[0] == "oq" and base[1] == "receive", base
    guarded = topt._try_sweeten(["ug"], ["orb"], avoid_positions={"QB"}, **kw)
    assert guarded is None, "an avoided position must never be a sweetener"


# ---------------------------------------------------------------------------
# T-3 — the feature's headline case
# ---------------------------------------------------------------------------

def test_shop_and_avoid_same_position_still_generates():
    """T-3 (D-360-2) — "I'm selling my RB and I don't want another one back".
    Shopping gates give_ids; Avoiding gates the receive pool. They are
    disjoint sides of the same trade and MUST be co-selectable — the naive
    "make all three mutually exclusive" implementation makes the single most
    common real usage unexpressible. THIS TEST IS THE FEATURE.

    SABOTAGE: make Shopping and Avoiding mutually exclusive server-side
    (drop avoided positions from trade_away_positions). The deck goes empty.
    """
    cards = _gen_divergence(_divergence_svc(),
                            trade_away_positions=["WR"],
                            avoid_positions=["WR"])
    assert cards, "shopping WR + avoiding WR must still produce cards"
    pos = {pid: p for pid, p in _ALL}
    # EVERY card still sends a WR out — Shopping is still enforced. This is
    # the assertion the sabotage breaks: dropping the avoided position from
    # trade_away_positions turns Shopping off, and cards that give only RBs
    # come back.
    assert all(any(pos.get(p) == "WR" for p in c.give_player_ids)
               for c in cards)
    # … and none brings one back — Avoiding is enforced on the other side.
    assert all(all(pos.get(p) != "WR" for p in c.receive_player_ids)
               for c in cards)


# ---------------------------------------------------------------------------
# T-5 / T-6 — picks
# ---------------------------------------------------------------------------

def test_avoid_qb_keeps_pick_rungs():
    """T-5 (R-5) — a PLAYER-position avoid must NEVER delete a draft pick.
    The generic pick rungs carry a deliberately FAKE position (_PICK_POS =
    {1:"RB",2:"WR",3:"TE",4:"QB"}) so they distribute across the trio tabs;
    a raw p.position read would let "avoid QB" delete every 4th-round rung.

    SABOTAGE: replace _pos_for_avoid with a raw `p.position` read.
    """
    rung = _Player("generic_pick_4_mid", position="QB", team="PICK")
    owned = _Player("L1_2027_1_3", position="PICK", team="PICK")
    pool = {"generic_pick_4_mid": rung, "L1_2027_1_3": owned,
            "realqb": _Player("realqb", "QB")}
    assert _pos_for_avoid(rung) == "PICK"
    assert _pos_for_avoid(owned) == "PICK"
    assert _pos_for_avoid(pool["realqb"]) == "QB"
    assert avoid_ok("generic_pick_4_mid", pool, {"QB"}) is True
    assert avoid_ok("L1_2027_1_3", pool, {"QB"}) is True
    assert avoid_ok("realqb", pool, {"QB"}) is False

    # End-to-end on a generator path: an owned pick on the opponent's roster
    # survives an "avoid QB" and can still be received.
    extra = (("L1_2027_1_9", "PICK", "PICK"),)
    cards = _gen_divergence(_divergence_svc(extra), extra=extra,
                            avoid_positions=["QB"])
    assert any("L1_2027_1_9" in c.receive_player_ids for c in cards), \
        "avoid QB must not delete a pick from the receive pool"


def test_avoid_pick_removes_pick_assets():
    """T-6 (R-5) — avoiding PICK, one of the five DNA chips, is the ONLY way
    to exclude pick assets, and it excludes BOTH kinds (owned-pick
    pseudo-assets and generic ladder rungs).

    SABOTAGE: drop the is_pick_asset arm of _pos_for_avoid, so "PICK"
    matches only position=="PICK" and generic rungs survive.
    """
    rung = _Player("generic_pick_4_mid", position="QB", team="PICK")
    owned = _Player("L1_2027_1_3", position="PICK", team="PICK")
    pool = {"generic_pick_4_mid": rung, "L1_2027_1_3": owned}
    assert avoid_ok("generic_pick_4_mid", pool, {"PICK"}) is False
    assert avoid_ok("L1_2027_1_3", pool, {"PICK"}) is False

    extra = (("L1_2027_1_9", "PICK", "PICK"),)
    cards = _gen_divergence(_divergence_svc(extra), extra=extra,
                            avoid_positions=["PICK"])
    assert all("L1_2027_1_9" not in c.receive_player_ids for c in cards)


def test_unknown_ids_and_empty_avoid_pass():
    """T-5b — an unknown id passes (it cannot be scored anyway), and an
    empty/None avoid set is a no-op."""
    assert avoid_ok("nope", {}, {"QB"}) is True
    assert avoid_ok("anything", {}, None) is True
    assert avoid_ok("anything", {}, set()) is True
    assert _pos_for_avoid(None) is None


# ---------------------------------------------------------------------------
# T-7 — asset ideas
# ---------------------------------------------------------------------------

def _ideas_svc():
    players = {pid: _Player(pid, pos) for pid, pos in _ALL}
    opp = LeagueMember(user_id="opp", username="opp",
                       roster=[pid for pid, _ in _O_ROSTER],
                       elo_ratings={pid: 1500 for pid, _ in _ALL},
                       has_rankings=True)
    s = TradeService(players=players)
    s.add_league(League(league_id="L1", name="T", platform="demo", members=[opp]))
    return s


def _ideas(svc, **kw):
    return svc.generate_asset_ideas(
        user_id="user",
        user_roster=[pid for pid, _ in _U_ROSTER],
        league_id="L1",
        seed_elo={pid: 1500 for pid, _ in _ALL},
        asset_id=kw.pop("asset_id", "G"),
        fairness_threshold=0.05,
        **kw,
    )


def test_asset_ideas_honor_avoid():
    """T-7 (R-6) — the /api/trades/asset-ideas return pools are receive-side
    guards, and #163 IS applied there, so Avoiding applies there too
    (D-360-3(a)). Avoiding WR ⇒ no idea returns a WR.

    SABOTAGE: remove the new load_league_preference call in the asset-ideas
    route (the kwarg then silently defaults to []) — or drop the predicate
    from any of the three receive-side guards in _generate_asset_ideas_impl.
    """
    pos = {pid: p for pid, p in _ALL}
    # Pin a WR to trade away. #198 constrains the Upgrade and Lateral groups
    # to the pin's OWN position, so the baseline returns WRs — and avoiding
    # WR empties those two groups by construction, which is PRD R-6
    # consequence 1 ("what can I get for my WR?" while avoiding WR returns
    # Downgrade only). Exactly what the user asked for.
    base = _ideas(_ideas_svc(), asset_id="uw1")
    flat = [i for g in base.values() for i in g]
    assert any(pos.get(p) == "WR" for i in flat for p in i["receive_player_ids"]), \
        "fixture must return a WR at baseline"
    guarded = _ideas(_ideas_svc(), asset_id="uw1", avoid_positions=["WR"])
    gflat = [i for g in guarded.values() for i in g]
    assert all(pos.get(p) != "WR" for i in gflat for p in i["receive_player_ids"])
    assert guarded["upgrade"] == [] and guarded["lateral"] == []


def test_asset_ideas_receive_direction_pinned_avoided_is_empty():
    """T-7b (R-6.2, D-360-3(b)) — pinning an asset to ACQUIRE whose position
    the user avoids returns the empty result, mirroring #163's identical
    guard. An exclusion beats a pin.

    SABOTAGE: drop the `if not avoid_ok(asset_id, ...): return empty` guard.
    """
    out = _ideas(_ideas_svc(), asset_id="ow1", direction="receive",
                 avoid_positions=["WR"])
    assert out == {"upgrade": [], "lateral": [], "downgrade": []}


# ---------------------------------------------------------------------------
# T-8 — likes-you injection
# ---------------------------------------------------------------------------

def test_likes_you_injection_refuses_avoided_position(monkeypatch):
    """T-8 (R-7) — a counterparty's liked trade is MIRRORED, so their give
    side IS the user's receive side. A boosted, deck-position-1 card that
    sends the user an avoided position is the most visible possible way to
    break the promise. This is a USER CONSTRAINT, so the G6 Q21 likes-you
    exemption does not reach it.

    SABOTAGE: remove the position-set intersection beside the #163 line in
    _inject_likes_you_cards_impl.
    """
    players = {"A": _Player("A", "RB"), "B": _Player("B", "QB")}
    svc = TradeService(players=players)
    opp = LeagueMember(user_id="opp", username="opp", roster=["B"],
                       elo_ratings={}, has_rankings=False)
    league = League(league_id="L1", name="T", platform="demo", members=[opp])
    like = {"user_id": "opp", "give_player_ids": ["B"],
            "receive_player_ids": ["A"]}
    monkeypatch.setattr(server, "load_recent_league_likes", lambda **kw: [like])

    common = dict(cards=[], trade_service=svc, user_id="user", league_id="L1",
                  league=league, user_roster=["A"],
                  seed_map={"A": 1500.0, "B": 1500.0})
    base = server._inject_likes_you_cards(**common)
    assert any("B" in c.receive_player_ids for c in base)
    guarded = server._inject_likes_you_cards(avoid_positions={"QB"}, **common)
    assert guarded == []


# ---------------------------------------------------------------------------
# T-9 — an exclusion beats a pin
# ---------------------------------------------------------------------------

def test_exclusion_beats_pinned_receive():
    """T-9 (R-8, D-360-3(b)) — a pinned receive target at an avoided position
    does NOT re-enter the pool. The re-add loops iterate the ALREADY-FILTERED
    list, which is the shipped house rule stated in the consensus path's own
    comment ("so an exclusion always wins"). This test exists so that a build
    agent does not "helpfully" add a pin exemption.

    SABOTAGE: re-add pinned_recv_set / target_ids members from the UNFILTERED
    opponent roster.
    """
    for v3 in (False, True):
        ff._flags_cache = {**ff.DEFAULT_FLAGS, "trade_engine.v2": True,
                           "trade_engine.v3": v3,
                           "trade.avoid_positions": True}
        cards = _gen_divergence(_divergence_svc(),
                                pinned_receive_players=["ow1"],   # a WR
                                avoid_positions=["WR"])
        assert all("ow1" not in c.receive_player_ids for c in cards), \
            f"v3={v3}: the pin must not beat the exclusion"
        # and the same for the Backlog-#2 target re-add
        cards = _gen_divergence(_divergence_svc(), target_ids={"ow1"},
                                avoid_positions=["WR"])
        assert all("ow1" not in c.receive_player_ids for c in cards)


# ---------------------------------------------------------------------------
# T-10 — the silent-zero-deck guard
# ---------------------------------------------------------------------------

def test_avoid_and_chase_same_position_is_not_a_silent_zero_deck():
    """T-10 (R-9) — avoid ⊕ chase is unsatisfiable and fails SILENTLY: the
    pool exclusion empties every receive pool of the position while
    _positions_ok still demands at least one received player at it, so every
    opponent yields zero cards with no error. The server guard drops the
    avoided positions from acquire BEFORE anything downstream sees the pair.
    AVOID WINS.

    SABOTAGE: remove the guard from _run_trade_job. The first assertion
    (unguarded ⇒ empty) documents the failure mode; the second (guarded ⇒
    non-empty, and no WR received) is what the guard buys.
    """
    # Without the guard the deck is empty — this is the failure mode.
    unguarded = _gen_divergence(_divergence_svc(),
                                acquire_positions=["WR"],
                                avoid_positions=["WR"])
    assert unguarded == [], \
        "fixture premise: chase+avoid of the same position empties the deck"

    # The guard, as _run_trade_job applies it.
    acquire, avoid = ["WR"], ["WR"]
    dropped = [p for p in acquire if p in set(avoid)]
    assert dropped == ["WR"]
    acquire = [p for p in acquire if p not in set(avoid)]
    guarded = _gen_divergence(_divergence_svc(),
                              acquire_positions=acquire or None,
                              avoid_positions=avoid)
    assert guarded, "with the guard the deck must not be empty"
    pos = {pid: p for pid, p in _ALL}
    assert all(all(pos.get(p) != "WR" for p in c.receive_player_ids)
               for c in guarded)


def test_run_trade_job_guard_source_is_present():
    """T-10b — the guard actually lives in _run_trade_job, not only in this
    test's re-derivation. Structural, so deleting the server-side block is
    red even though the engine test above re-implements it.

    SABOTAGE: delete the `#360 R-9` block from _run_trade_job.
    """
    import inspect
    src = inspect.getsource(server._run_trade_job)
    assert "avoid⊕chase" in src, "the R-9 guard is missing from _run_trade_job"
    assert "if avoid_positions and acquire_positions:" in src


# ---------------------------------------------------------------------------
# T-12 / T-13 / T-16 — flag off, avoid-everything
# ---------------------------------------------------------------------------

def test_flag_off_deck_is_byte_identical():
    """T-12 (R-11) — with trade.avoid_positions off, a populated column is
    never read: the flag gate lives at the single point of entry
    (_run_trade_job's preference load), so the engine sees [] and every
    generation path produces the deck it produces today.

    SABOTAGE: read the column unconditionally instead of behind
    FLAGS.trade_avoid_positions.
    """
    import inspect
    src = inspect.getsource(server._run_trade_job)
    assert "if FLAGS.trade_avoid_positions:" in src, \
        "the flag gate is missing from the trade job's preference load"

    baseline = _gen_divergence(_divergence_svc())
    flag_off = _gen_divergence(_divergence_svc(), avoid_positions=[])
    key = lambda cs: [(c.give_player_ids, c.receive_player_ids,
                       c.composite_score) for c in cs]
    assert key(baseline) == key(flag_off)


def test_avoid_all_positions_yields_empty_deck_no_exception():
    """T-13 (R-16) — avoiding all five positions is allowed and HONEST: the
    backend does not silently treat "avoid everything" as "avoid nothing".
    Silently disobeying a saved preference to dodge an awkward empty state is
    the invented-state-change failure the repo's own feedback lesson names.

    SABOTAGE: add an "avoid everything ⇒ treat as unset" override.
    """
    cards = _gen_divergence(_divergence_svc(),
                            avoid_positions=["QB", "RB", "WR", "TE", "PICK"])
    assert cards == []


def test_avoid_is_never_relaxed():
    """T-12b (D-360-4) — the #189 relaxed pass re-runs _generate_trades_v2 with
    the SAME kwargs and relaxes only the fairness band and the surplus floor,
    so a pool-construction filter is structurally un-relaxable. Pinned as a
    behavioral test: a targeted job whose normal pass is empty still returns
    nothing containing the avoided position.

    SABOTAGE: move the filter out of pool construction into a package gate.
    """
    cards = _gen_divergence(_divergence_svc(),
                            fairness_threshold=0.999,      # forces the retry
                            pinned_receive_players=["ow1"],
                            avoid_positions=["WR"])
    assert all("ow1" not in c.receive_player_ids for c in cards)
    assert "avoid_positions" in ts.TradeService._relaxed_targeted_pass.__doc__


# ---------------------------------------------------------------------------
# Flag + docs registration
# ---------------------------------------------------------------------------

def test_flag_registered_in_both_files():
    """The key must exist in FLAG_KEYS and config/features.json with the same
    value the release fixture mirrors. A key in only one place disagrees with
    itself across the first two client paints."""
    from pathlib import Path
    assert "trade.avoid_positions" in ff.FLAG_KEYS
    repo = Path(__file__).resolve().parents[2]
    features = json.loads((repo / "config/features.json").read_text())
    assert features["trade.avoid_positions"] is False, (
        "Q-032 (operator, 2026-08-19): #360 ships DARK. Persistence is not "
        "flag-gated, so shipping dark costs only visibility — the column "
        "stores and the API serves in both states. Lighting it later is a "
        "deploy-free flip of this key plus the three fixtures that mirror it "
        "(G-062).")
    release = json.loads(
        (repo / "backend/tests/fixtures/flags/release.json").read_text())
    assert release["trade.avoid_positions"] == features["trade.avoid_positions"], (
        "the release fixture must mirror what config/features.json ships")


def test_gen_v2_guardrail_note_present():
    """PRD §5.1 — the bake-off arm is documented in two places and both must
    carry the guardrail, because bakeoff_serve_interleaved flips without a
    deploy and trade_gen_v2 honors no positional preference at all."""
    from pathlib import Path
    import inspect
    repo = Path(__file__).resolve().parents[2]
    cfg = (repo / "docs/config-reference.md").read_text()
    assert cfg.count("bakeoff_serve_interleaved") >= 3
    assert "GUARDRAIL (#360" in cfg
    flags_src = Path(inspect.getsourcefile(ff)).read_text()
    assert "GUARDRAIL (#360" in flags_src
