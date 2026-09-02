"""Below-market card reason — `reason_below_market_frac`
(docs/plans/below-market-reason/scope.md; feedback #350, closes Q-035).

When a card asks the user to give up a player his OWN board prices below the
market, the card says so — because that gap is why the engine picked him. A
presentation change only: the line rides `TradeCard.reasons`, which
`server.trade_card_to_dict` already emits (only while
`trade_math.human_explanations` is on — TRUE in prod) and both clients
already render. Nothing about which cards exist, how they score, or how they
order moves at any knob value.

Four claims, four proofs:

1. **Knob 0 is byte-identical to origin/main** — `_GOLDEN_WIRE_JSON` is the
   FULL `generate_trades` deck on the engine-quality fixture, serialized by
   `trade_card_to_dict` with the explanations flag ON (prod posture),
   captured on the `02d2eac2` tree the branch forked from and re-verified
   against `e16bb487`, the tip the branch is rebased on (the intervening
   commits touch neither the engine nor the serializer).
2. **The trigger** — the give-side HEADLINER (C4b `deck_give_headliner`),
   the SHRUNK board, the exact copy, and every silent case (5% below at
   0.15, user above market, picks-only give side, zero comparisons, a
   below-market second give player that is not the headliner, knob 0).
3. **Deck invariance** — at 0.15 (and 0.5) vs 0, every card's every
   attribute except `reasons` is identical, in order, in count: on the
   engine-quality fixture and on 100 random leagues.
4. **The wire gate** — the reason reaches the payload at 0.15 with the flag
   ON and never with it OFF, at any knob value.

Capture procedure for the golden (re-run only if the fixture changes)::

    git archive origin/main | tar -x -C <scratch>/main_tree
    cp backend/tests/test_below_market_reason.py <scratch>/main_tree/backend/tests/
    (cd <scratch>/main_tree && PYTHONHASHSEED=0 python3 -m backend.tests.test_below_market_reason)

Sabotage recipes (each proven red then green on 2026-09-02; clear
`backend/**/__pycache__` after restoring — G-060):
  * pass `user_elo` (raw) instead of `shrunk_elo` at the stamp site
    → test_zero_comparisons_never_fires red;
  * fire on ANY give-side player (`any(...)` over give_ids) instead of the
    headliner → test_second_give_player_below_market_is_silent red;
  * drop the `_FLAGS.trade_math_human_explanations` gate in
    `trade_card_to_dict` → test_wire_flag_off_never_carries_the_reason red;
  * drop the `team == "PICK"` clause from `is_pick_asset` (the universal
    pool's generic picks carry a real position)
    → test_a_generic_pick_never_headlines_and_is_never_named red.
"""

import json
import math
import random
import time

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.trade_service import League, LeagueMember, TradeService

from backend.tests.test_engine_quality_golden import (
    _CONFIDENCE as _EQ_CONFIDENCE,
    _deck_fixture as _eq_fixture,
)

KNOB = "reason_below_market_frac"
FLAG = "trade_math.human_explanations"
#: The exact copy (docs/plans/below-market-reason/scope.md §0).
COPY = "You rank {name} below the market — that gap is what this trade cashes in."
#: Serializer keys that are per-run noise (uuid / clock), stripped before any
#: wire comparison. `expires_at` is the only clock field the serializer emits.
_NOISE = ("trade_id", "expires_at")


class _Player:
    def __init__(self, pid, position, name=None, age=25, team="TST"):
        self.id = pid
        self.name = f"Player {pid}" if name is None else name
        self.position = position
        self.team = team
        self.age = age
        self.ktc_value = None
        self.pick_value = None
        self.years_experience = 3
        self.search_rank = 50


class _Pick(_Player):
    def __init__(self, pid, pick_value=60.0):
        super().__init__(pid, position="PICK", team="PICK", age=0)
        self.pick_value = pick_value


class _GenericPick(_Player):
    """The universal pool's generic-pick shape: a REAL position (it mixes
    into the trio tabs) with `team == "PICK"` — caught only by the `team`
    clause of `is_pick_asset`."""
    def __init__(self, pid, position="WR", pick_value=60.0):
        super().__init__(pid, position=position, team="PICK", age=21)
        self.pick_value = pick_value


def _elo(value: float) -> float:
    """Inverse of elo_to_value at the shipped curve (k=0.005, ref 1500)."""
    return 1500.0 + math.log(value / 1000.0) / 0.005


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    old_flags, old_cfg = ff._flags_cache, dict(ts._cfg)
    # G-065 — the generators carry wall-clock deadlines; freeze them so two
    # decks in one test are the same deck.
    monkeypatch.setattr(time, "monotonic", lambda: 1.0e6)
    try:
        yield
    finally:
        ff._flags_cache = old_flags
        ts._cfg.clear()
        ts._cfg.update(old_cfg)


def _setup(frac, *, explanations=True, **flags):
    cache = dict(ff.DEFAULT_FLAGS)
    cache.update({"trade_engine.v2": True, FLAG: explanations})
    cache.update(flags)
    ff._flags_cache = cache
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    # The knob does not exist on the capture tree; only set it when asked
    # for a non-default value so the same file runs on both trees.
    if frac:
        ts._cfg[KNOB] = float(frac)


def _snapshot(card):
    """Every attribute of a card except the per-run noise and `reasons`."""
    d = dict(vars(card))
    for k in ("trade_id", "created_at", "expires_at", "reasons"):
        d.pop(k, None)
    return d


def _wire(cards, players):
    from backend.server import trade_card_to_dict
    out = []
    for c in cards:
        d = trade_card_to_dict(c, players)
        for k in _NOISE:
            d.pop(k, None)
        out.append(d)
    return out


# ── the Adams-shaped fixture (unit level, the helper called directly) ──────

def _adams(user_value=2300.0, seed_value=3000.0, *, name="Davante Adams"):
    """Give side `[adams, filler]`; adams is the headliner on seed. Returns
    (give_ids, seed_elo, shrunk_elo, players)."""
    players = {
        "adams": _Player("adams", "WR", name=name, age=32),
        "fill": _Player("fill", "RB"),
        "pk": _Pick("pk"),
        # generic pick: real position "WR", team "PICK", priced 30% BELOW
        # the market on the user's board — must never headline or be named
        "gpk": _GenericPick("gpk", "WR"),
    }
    seed = {"adams": _elo(seed_value), "fill": _elo(1000.0),
            "pk": _elo(2400.0), "gpk": _elo(5000.0)}
    shrunk = {"adams": _elo(user_value), "fill": _elo(1000.0),
              "pk": _elo(2400.0), "gpk": _elo(3500.0)}
    return ["adams", "fill"], seed, shrunk, players


def test_adams_case_fires_with_the_exact_copy():
    give, seed, shrunk, players = _adams(2300.0, 3000.0)   # 23.3% below
    line = ts.below_market_reason(give, seed, shrunk, players, 0.15)
    assert line == "You rank Davante Adams below the market — that gap is what this trade cashes in."
    assert line == COPY.format(name="Davante Adams")


def test_copy_is_one_short_line():
    for name in ("Davante Adams", "Marvin Harrison Jr.", "Ja'Marr Chase"):
        line = COPY.format(name=name)
        assert "\n" not in line and len(line) <= 90, (name, len(line))


def test_five_percent_below_is_silent_at_015():
    give, seed, shrunk, players = _adams(2850.0, 3000.0)   # 5% below
    assert ts.below_market_reason(give, seed, shrunk, players, 0.15) is None
    # ...and fires once the bar is under the gap.
    assert ts.below_market_reason(give, seed, shrunk, players, 0.04) is not None


def test_user_above_market_is_silent():
    give, seed, shrunk, players = _adams(3600.0, 3000.0)   # 20% ABOVE
    assert ts.below_market_reason(give, seed, shrunk, players, 0.15) is None
    assert ts.below_market_reason(give, seed, shrunk, players, 0.0001) is None


def test_picks_only_give_side_is_silent():
    _, seed, shrunk, players = _adams()
    shrunk["pk"] = _elo(1200.0)               # the pick itself 50% below
    assert ts.below_market_reason(["pk"], seed, shrunk, players, 0.15) is None
    # ...and the generic-pick shape (real position, team "PICK", 30% below)
    assert ts.below_market_reason(["gpk"], seed, shrunk, players, 0.15) is None
    assert ts.below_market_reason(["pk", "gpk"], seed, shrunk, players,
                                  0.15) is None


def test_a_generic_pick_never_headlines_and_is_never_named():
    """Universal-pool generic pick: `position == "WR"`, `team == "PICK"`,
    out-seeding every player on the give side (5000 vs 3000) and priced 30%
    below the market on the user's board. Only the `team` clause of
    `is_pick_asset` knows it is a pick. With Adams AT market it must stay
    silent (the pick may not headline); with Adams below market the line
    must name Adams, never the pick. Removing the `team` clause from
    `is_pick_asset` turns both assertions red."""
    give, seed, shrunk, players = _adams(3000.0, 3000.0)   # adams at market
    assert ts.below_market_reason(["gpk", "adams"], seed, shrunk, players,
                                  0.15) is None
    give, seed, shrunk, players = _adams(2300.0, 3000.0)   # adams 23% below
    line = ts.below_market_reason(["gpk", "adams", "fill"], seed, shrunk,
                                  players, 0.15)
    assert line == COPY.format(name="Davante Adams")
    assert "gpk" not in line and "Player gpk" not in line


def test_a_pick_never_headlines_a_mixed_give_side():
    """C4b rule: players outrank picks. The pick out-seeds Adams here (2400
    vs 3000 is not — so make the pick the top seed), yet Adams headlines and
    the line names HIM; the pick's own gap is irrelevant."""
    give, seed, shrunk, players = _adams(2300.0, 3000.0)
    seed["pk"], shrunk["pk"] = _elo(5000.0), _elo(5000.0)
    line = ts.below_market_reason(["pk", "adams"], seed, shrunk, players, 0.15)
    assert line == COPY.format(name="Davante Adams")


def test_second_give_player_below_market_but_not_headliner_is_silent():
    """Headliner ONLY: `fill` is 40% below the market but Adams (at
    consensus) is the headliner, so nothing fires."""
    give, seed, shrunk, players = _adams(3000.0, 3000.0)   # adams at market
    seed["fill"], shrunk["fill"] = _elo(1000.0), _elo(600.0)
    assert ts.below_market_reason(give, seed, shrunk, players, 0.15) is None


def test_knob_zero_never_fires_regardless_of_gap():
    give, seed, shrunk, players = _adams(300.0, 3000.0)    # 90% below
    assert ts.below_market_reason(give, seed, shrunk, players, 0.0) is None
    assert ts.below_market_reason(give, seed, shrunk, players, None) is None


def test_missing_name_yields_no_reason_not_a_placeholder():
    give, seed, shrunk, players = _adams(2300.0, 3000.0, name="")
    assert ts.below_market_reason(give, seed, shrunk, players, 0.15) is None
    players["adams"].name = None
    assert ts.below_market_reason(give, seed, shrunk, players, 0.15) is None


def test_headliner_absent_from_the_user_board_is_consensus():
    give, seed, shrunk, players = _adams(2300.0, 3000.0)
    del shrunk["adams"]
    assert ts.below_market_reason(give, seed, shrunk, players, 0.15) is None


# ── the shrunk board, through the real generator ───────────────────────────

def _board_fixture():
    """A league where the user's RAW board prices his headliner `hub` 23%
    below the market. Whether that gap survives to the stamp depends only
    on `confidence` — the shrink weight `n / (n + 4)`."""
    pos = {"uq": "QB", "ur1": "RB", "ur2": "RB", "uw1": "WR", "uw2": "WR",
           "ut": "TE"}
    players = {pid: _Player(pid, p) for pid, p in pos.items()}
    players["hub"] = _Player("hub", "WR", name="Davante Adams")
    seed = {pid: 1500.0 for pid in pos}
    seed["hub"] = _elo(3000.0)
    user_elo = dict(seed)
    user_elo["hub"] = _elo(2300.0)
    opp_pos = {"oq": "QB", "or1": "RB", "or2": "RB", "ow1": "WR",
               "ow2": "WR", "ot": "TE"}
    for pid, p in opp_pos.items():
        players[pid] = _Player(pid, p)
        seed[pid] = user_elo[pid] = 1500.0
    players["star"] = _Player("star", "WR")
    seed["star"], user_elo["star"] = _elo(3000.0), _elo(3400.0)
    opp_elo = {pid: 1500.0 for pid in list(pos) + list(opp_pos)}
    opp_elo.update({"hub": _elo(3600.0), "star": _elo(2700.0)})
    opp = LeagueMember(user_id="opp", username="opp",
                       roster=["star"] + list(opp_pos), elo_ratings=opp_elo,
                       has_rankings=True)
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[opp]))
    return svc, user_elo, ["hub"] + list(pos), seed


def _board_deck(frac, confidence, **flags):
    _setup(frac, **flags)
    svc, ue, ur, seed = _board_fixture()
    return svc.generate_trades(
        user_id="user", user_elo=ue, user_roster=ur, league_id="L1",
        seed_elo=seed, fairness_threshold=0.6, max_per_opponent=10,
        confidence=confidence)


def _hub_cards(cards):
    return [c for c in cards if "hub" in c.give_player_ids]


def test_zero_comparisons_never_fires():
    """`comparison_counts` is `{}` for a user with no board (the job thread
    passes `service.comparison_counts()`, never None): every weight is 0,
    the shrunk board IS the seed, and the raw 23% gap never reaches the
    stamp. The sabotage that reads the raw board turns this red."""
    cards = _board_deck(0.15, {})
    assert _hub_cards(cards), "fixture must produce hub-give cards"
    assert all(c.reasons == [] for c in cards)


def test_well_sampled_board_fires_on_every_hub_give_card():
    cards = _board_deck(0.15, {"hub": 10_000})     # w ≈ 1: shrunk == raw
    hub = _hub_cards(cards)
    assert hub
    assert all(c.reasons == [COPY.format(name="Davante Adams")] for c in hub)
    assert all(c.reasons == [] for c in cards if c not in hub)


def test_lightly_sampled_board_is_shrunk_below_the_bar():
    """n = 1 ⇒ w = 0.2 ⇒ the 23% raw gap shrinks to ~5%: silent at 0.15,
    audible at 0.04 — the knob reads the SHRUNK gap, not the raw one."""
    assert all(c.reasons == [] for c in _board_deck(0.15, {"hub": 1}))
    assert all(c.reasons for c in _hub_cards(_board_deck(0.04, {"hub": 1})))


def test_reason_is_stamped_on_both_bases():
    """Divergence card (boarded partner) and consensus card (unboarded
    partner) both carry the line — the stamp sits after generation in the
    loop every basis flows through."""
    _setup(0.15)
    svc, ue, ur, seed = _board_fixture()
    svc._leagues["L1"].members[0].has_rankings = False
    svc._leagues["L1"].members[0].elo_ratings = {}
    cards = svc.generate_trades(
        user_id="user", user_elo=ue, user_roster=ur, league_id="L1",
        seed_elo=seed, fairness_threshold=0.6, max_per_opponent=10,
        confidence={"hub": 10_000})
    assert cards and all(c.basis == "consensus" for c in cards)
    hub = _hub_cards(cards)
    assert hub and all(c.reasons == [COPY.format(name="Davante Adams")]
                       for c in hub)
    div = _hub_cards(_board_deck(0.15, {"hub": 10_000}))
    assert div and all(c.basis == "divergence" for c in div)


def test_knob_is_read_at_call_time_through_the_overlay():
    """A process-global 0.15 under `_cfg_override({KNOB: 0.0})` stamps
    nothing; the reverse stamps — the read happens inside the job, on the
    calling thread, never at import (D-098 / G-058 cause 3)."""
    _setup(0.15)
    svc, ue, ur, seed = _board_fixture()
    kw = dict(user_id="user", user_elo=ue, user_roster=ur, league_id="L1",
              seed_elo=seed, fairness_threshold=0.6, max_per_opponent=10,
              confidence={"hub": 10_000})
    with ts._cfg_override({KNOB: 0.0}):
        assert all(c.reasons == [] for c in svc.generate_trades(**kw))
    _setup(0.0)
    with ts._cfg_override({KNOB: 0.15}):
        assert all(c.reasons for c in _hub_cards(svc.generate_trades(**kw)))


# ── registration ───────────────────────────────────────────────────────────

def test_default_registered_in_both_stores_at_the_identity():
    from backend.database import _MODEL_CONFIG_DEFAULTS
    seeded = {k: v for k, v, _ in _MODEL_CONFIG_DEFAULTS}
    assert ts._DEFAULT_CFG[KNOB] == 0.0
    assert seeded[KNOB] == 0.0


def test_arm_a_excludes_the_knob_and_the_drift_alarm_knows_it():
    from backend.bakeoff_profiles import MODEL_A_PROFILE, MODEL_CHALLENGER_PROFILE
    from backend.tests.test_bakeoff_arm_a_golden import _PINNED_KNOBS
    assert KNOB in _PINNED_KNOBS
    assert KNOB not in MODEL_A_PROFILE
    assert KNOB not in MODEL_CHALLENGER_PROFILE


# ── deck invariance ────────────────────────────────────────────────────────

def _eq_deck(frac, **flags):
    _setup(frac, **flags)
    svc, ue, ur, seed = _eq_fixture()
    cards = svc.generate_trades(
        user_id="user", user_elo=ue, user_roster=ur, league_id="L1",
        seed_elo=seed, fairness_threshold=0.6, max_per_opponent=10,
        confidence=dict(_EQ_CONFIDENCE))
    return svc, cards


def test_deck_is_invariant_on_the_engine_quality_fixture():
    _, base = _eq_deck(0.0)
    for frac in (0.15, 0.5, 1.0):
        _, cards = _eq_deck(frac)
        assert [_snapshot(c) for c in cards] == [_snapshot(c) for c in base]
        assert len(cards) == len(base)
    # Non-vacuity: hub is priced 1600 vs seed 1700 with n = 2 (w = 1/3 ⇒
    # shrunk 1666.7 ⇒ 15.4% below in value space), so its give cards DO
    # carry the line at 0.15.
    _, cards = _eq_deck(0.15)
    hub = [c for c in cards if "hub" in c.give_player_ids]
    assert hub and all(c.reasons == [COPY.format(name="Player hub")]
                       for c in hub)
    assert all(c.reasons == [] for c in base)


def _random_league(rng, n):
    """A random 4-team league: 24-player pool (6 a side), random seed Elos,
    the user's raw board a noisy copy of the seed with random comparison
    counts, each partner boarded or not at random, one owned pick per team."""
    positions = ["QB", "RB", "WR", "WR", "TE", "RB"]
    players, seed, user_elo, conf = {}, {}, {}, {}
    pool = []
    for i in range(24):
        pid = f"p{n}_{i}"
        players[pid] = _Player(pid, positions[i % len(positions)],
                               age=rng.randint(21, 33))
        seed[pid] = rng.uniform(1380.0, 1800.0)
        user_elo[pid] = seed[pid] + rng.gauss(0.0, 90.0)
        conf[pid] = rng.choice([0, 0, 1, 2, 4, 8, 16])
        pool.append(pid)
    rng.shuffle(pool)
    rosters = [pool[k * 6:(k + 1) * 6] for k in range(4)]
    for k in range(4):
        pk = f"pk{n}_{k}"
        players[pk] = _Pick(pk)
        seed[pk] = user_elo[pk] = rng.uniform(1520.0, 1660.0)
        rosters[k].append(pk)
    members = []
    for k in range(1, 4):
        boarded = rng.random() < 0.6
        opp_elo = ({pid: seed[pid] + rng.gauss(0.0, 90.0) for pid in seed}
                   if boarded else {})
        members.append(LeagueMember(
            user_id=f"opp{k}", username=f"opp{k}", roster=rosters[k],
            elo_ratings=opp_elo, has_rankings=boarded))
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=members))
    return svc, user_elo, rosters[0], seed, conf


def test_deck_is_invariant_at_every_knob_value_on_100_random_leagues():
    """Property: for 100 random leagues, the deck at 0.15 equals the deck at
    0 in every attribute but `reasons` — ids, composite, fairness, order,
    count, basis, values, every stamp. Run under the LIVE flag set (v3,
    presentment rules, need fit, lanes...) so every prod generation path is
    exercised, not just the v2 pair generator."""
    live = {k: v for k, v in json.load(open("config/features.json")).items()
            if isinstance(v, bool)}
    live.update({"trade.bakeoff": False, FLAG: True})
    rng = random.Random(350)
    fired = 0
    for n in range(100):
        svc, ue, ur, seed, conf = _random_league(rng, n)
        decks = {}
        for frac in (0.0, 0.15):
            _setup(frac, **live)
            svc._trade_cards.clear()
            decks[frac] = svc.generate_trades(
                user_id="user", user_elo=dict(ue), user_roster=list(ur),
                league_id="L1", seed_elo=dict(seed), fairness_threshold=0.6,
                max_per_opponent=5, confidence=dict(conf))
        base, moved = decks[0.0], decks[0.15]
        assert len(base) == len(moved), n
        assert [_snapshot(c) for c in base] == [_snapshot(c) for c in moved], n
        assert all(c.reasons == [] for c in base), n
        for c in moved:
            assert len(c.reasons) <= 1, n
            if c.reasons:
                fired += 1
                head = ts.deck_give_headliner(c.give_player_ids, seed,
                                              svc._players)
                assert c.reasons == [COPY.format(name=svc._players[head].name)]
    assert fired > 0, "the property is vacuous if no random league fires"


# ── the wire ───────────────────────────────────────────────────────────────

def test_wire_carries_the_reason_at_015_with_the_flag_on():
    svc, cards = _eq_deck(0.15)
    wire = _wire(cards, svc._players)
    hub = [d for d in wire if any(p["id"] == "hub" for p in d["give"])]
    assert hub and all(d["reasons"] == [COPY.format(name="Player hub")]
                       for d in hub)
    assert all("reasons" not in d for d in wire if d not in hub)


def test_wire_flag_off_never_carries_the_reason():
    """`trade_math.human_explanations` off ⇒ no `reasons` key on any card at
    any knob value (the in-process stamp still happens; the wire gate is
    the serializer's). Dropping that gate turns this red."""
    for frac in (0.10, 0.15):
        svc, cards = _eq_deck(frac, explanations=False)
        assert any(c.reasons for c in cards)          # stamped in-process...
        assert all("reasons" not in d                 # ...never on the wire
                   for d in _wire(cards, svc._players))


def test_wire_at_knob_zero_is_byte_identical_to_origin_main():
    svc, cards = _eq_deck(0.0)
    assert json.dumps(_wire(cards, svc._players), sort_keys=True) == \
        json.dumps(GOLDEN_WIRE, sort_keys=True)
    assert all("reasons" not in d for d in GOLDEN_WIRE)


def test_the_wire_golden_is_not_vacuous():
    svc, cards = _eq_deck(0.15)
    assert json.dumps(_wire(cards, svc._players), sort_keys=True) != \
        json.dumps(GOLDEN_WIRE, sort_keys=True)


# ── golden: full generate_trades deck → trade_card_to_dict, flag ON,
#    captured on origin/main @ 02d2eac2, re-verified against e16bb487 ──────

_GOLDEN_WIRE_JSON = """\
[
{"basis":"divergence","composite_score":1.297,"decision":null,"fairness_score":0.67,"favors":"give","gap":{"add_to":"receive","firsts":0.42,"pick_equivalent":{"label":"Early 2nd Round Pick","pick_id":"generic_pick_2_early","value":860.7},"value":896.2},"give":[{"age":24,"id":"hub","name":"Player hub","position":"WR","search_rank":50,"team":"TST","years_experience":3}],"give_value":2718.3,"league_id":"L1","match_context":{"league_settings":{"dynasty":false,"scoring":"ppr","superflex":false,"te_premium":false},"opponent_surplus":[],"positional_rationale":"Roster profiles align without a single standout gap.","user_needs":[]},"mismatch_score":1692.5,"narrative":"Player star3 comes back in a uneven on paper package.","receive":[{"age":24,"id":"star3","name":"Player star3","position":"WR","search_rank":50,"team":"TST","years_experience":3}],"receive_value":1822.1,"target_user_id":"opp3","target_username":"opp3"},
{"basis":"divergence","composite_score":1.252,"decision":null,"fairness_score":0.878,"favors":"give","gap":{"add_to":"receive","firsts":0.16,"pick_equivalent":{"label":"Late 3rd Round Pick","pick_id":"generic_pick_3_late","value":332.9},"value":330.4},"give":[{"age":24,"id":"hub","name":"Player hub","position":"WR","search_rank":50,"team":"TST","years_experience":3}],"give_value":2718.3,"league_id":"L1","match_context":{"league_settings":{"dynasty":false,"scoring":"ppr","superflex":false,"te_premium":false},"opponent_surplus":[],"positional_rationale":"Roster profiles align without a single standout gap.","user_needs":[]},"mismatch_score":2036.7,"narrative":"Player star3 comes back in a balanced package.","receive":[{"age":24,"id":"star3","name":"Player star3","position":"WR","search_rank":50,"team":"TST","years_experience":3},{"age":24,"id":"o3t","name":"Player o3t","position":"TE","search_rank":50,"team":"TST","years_experience":3}],"receive_value":2387.9,"target_user_id":"opp3","target_username":"opp3"},
{"basis":"divergence","composite_score":0.911,"decision":null,"fairness_score":0.938,"favors":"give","gap":{"add_to":"receive","firsts":0.09,"pick_equivalent":{"label":"Late 4th Round Pick","pick_id":"generic_pick_4_late","value":246.6},"value":181.6},"give":[{"age":0,"id":"PKu","name":"Player PKu","pick_value":60.0,"position":"PICK","search_rank":50,"team":"PICK","years_experience":3},{"age":24,"id":"uq","name":"Player uq","position":"QB","search_rank":50,"team":"TST","years_experience":3},{"age":24,"id":"ur2","name":"Player ur2","position":"RB","search_rank":50,"team":"TST","years_experience":3}],"give_value":2926.0,"league_id":"L1","match_context":{"league_settings":{"dynasty":false,"scoring":"ppr","superflex":false,"te_premium":false},"opponent_surplus":[],"positional_rationale":"Roster profiles align without a single standout gap.","user_needs":[]},"mismatch_score":825.9,"narrative":"Player star3 comes back in a balanced package. Pick value reflects league depth.","receive":[{"age":24,"id":"star3","name":"Player star3","position":"WR","search_rank":50,"team":"TST","years_experience":3},{"age":24,"id":"o3r2","name":"Player o3r2","position":"RB","search_rank":50,"team":"TST","years_experience":3}],"receive_value":2744.4,"target_user_id":"opp3","target_username":"opp3"},
{"basis":"divergence","composite_score":0.911,"decision":null,"fairness_score":0.938,"favors":"give","gap":{"add_to":"receive","firsts":0.09,"pick_equivalent":{"label":"Late 4th Round Pick","pick_id":"generic_pick_4_late","value":246.6},"value":181.6},"give":[{"age":0,"id":"PKu","name":"Player PKu","pick_value":60.0,"position":"PICK","search_rank":50,"team":"PICK","years_experience":3},{"age":24,"id":"uq","name":"Player uq","position":"QB","search_rank":50,"team":"TST","years_experience":3},{"age":24,"id":"ur1","name":"Player ur1","position":"RB","search_rank":50,"team":"TST","years_experience":3}],"give_value":2926.0,"league_id":"L1","match_context":{"league_settings":{"dynasty":false,"scoring":"ppr","superflex":false,"te_premium":false},"opponent_surplus":[],"positional_rationale":"Roster profiles align without a single standout gap.","user_needs":[]},"mismatch_score":825.9,"narrative":"Player star3 comes back in a balanced package. Pick value reflects league depth.","receive":[{"age":24,"id":"star3","name":"Player star3","position":"WR","search_rank":50,"team":"TST","years_experience":3},{"age":24,"id":"o3r2","name":"Player o3r2","position":"RB","search_rank":50,"team":"TST","years_experience":3}],"receive_value":2744.4,"target_user_id":"opp3","target_username":"opp3"},
{"basis":"divergence","composite_score":0.887,"decision":null,"fairness_score":0.938,"favors":"give","gap":{"add_to":"receive","firsts":0.09,"pick_equivalent":{"label":"Late 4th Round Pick","pick_id":"generic_pick_4_late","value":246.6},"value":181.6},"give":[{"age":0,"id":"PKu","name":"Player PKu","pick_value":60.0,"position":"PICK","search_rank":50,"team":"PICK","years_experience":3},{"age":24,"id":"uq","name":"Player uq","position":"QB","search_rank":50,"team":"TST","years_experience":3},{"age":24,"id":"ur2","name":"Player ur2","position":"RB","search_rank":50,"team":"TST","years_experience":3}],"give_value":2926.0,"league_id":"L1","match_context":{"league_settings":{"dynasty":false,"scoring":"ppr","superflex":false,"te_premium":false},"opponent_surplus":[],"positional_rationale":"Roster profiles align without a single standout gap.","user_needs":[]},"mismatch_score":796.0,"narrative":"Player star2 comes back in a balanced package. Pick value reflects league depth.","receive":[{"age":24,"id":"star2","name":"Player star2","position":"WR","search_rank":50,"team":"TST","years_experience":3},{"age":24,"id":"o2r2","name":"Player o2r2","position":"RB","search_rank":50,"team":"TST","years_experience":3}],"receive_value":2744.4,"target_user_id":"opp2","target_username":"opp2"},
{"basis":"divergence","composite_score":0.887,"decision":null,"fairness_score":0.938,"favors":"give","gap":{"add_to":"receive","firsts":0.09,"pick_equivalent":{"label":"Late 4th Round Pick","pick_id":"generic_pick_4_late","value":246.6},"value":181.6},"give":[{"age":0,"id":"PKu","name":"Player PKu","pick_value":60.0,"position":"PICK","search_rank":50,"team":"PICK","years_experience":3},{"age":24,"id":"uq","name":"Player uq","position":"QB","search_rank":50,"team":"TST","years_experience":3},{"age":24,"id":"ur1","name":"Player ur1","position":"RB","search_rank":50,"team":"TST","years_experience":3}],"give_value":2926.0,"league_id":"L1","match_context":{"league_settings":{"dynasty":false,"scoring":"ppr","superflex":false,"te_premium":false},"opponent_surplus":[],"positional_rationale":"Roster profiles align without a single standout gap.","user_needs":[]},"mismatch_score":796.0,"narrative":"Player star2 comes back in a balanced package. Pick value reflects league depth.","receive":[{"age":24,"id":"star2","name":"Player star2","position":"WR","search_rank":50,"team":"TST","years_experience":3},{"age":24,"id":"o2r2","name":"Player o2r2","position":"RB","search_rank":50,"team":"TST","years_experience":3}],"receive_value":2744.4,"target_user_id":"opp2","target_username":"opp2"},
{"basis":"divergence","composite_score":0.46,"decision":null,"fairness_score":0.95,"favors":"even","gap":{"add_to":"give","firsts":0.07,"pick_equivalent":{"label":"Late 4th Round Pick","pick_id":"generic_pick_4_late","value":246.6},"value":153.4},"give":[{"age":0,"id":"PKu","name":"Player PKu","pick_value":60.0,"position":"PICK","search_rank":50,"team":"PICK","years_experience":3},{"age":24,"id":"uw2","name":"Player uw2","position":"WR","search_rank":50,"team":"TST","years_experience":3},{"age":24,"id":"ut","name":"Player ut","position":"TE","search_rank":50,"team":"TST","years_experience":3}],"give_value":2926.0,"league_id":"L1","match_context":{"league_settings":{"dynasty":false,"scoring":"ppr","superflex":false,"te_premium":false},"opponent_surplus":[],"positional_rationale":"Roster profiles align without a single standout gap.","user_needs":[]},"mismatch_score":262.3,"narrative":"Player star1 comes back in a perfectly balanced package. Pick value reflects league depth.","receive":[{"age":24,"id":"star1","name":"Player star1","position":"WR","search_rank":50,"team":"TST","years_experience":3},{"age":0,"id":"PKo1","name":"Player PKo1","pick_value":60.0,"position":"PICK","search_rank":50,"team":"PICK","years_experience":3}],"receive_value":3079.4,"target_user_id":"opp1","target_username":"opp1"},
{"basis":"divergence","composite_score":0.46,"decision":null,"fairness_score":0.95,"favors":"even","gap":{"add_to":"give","firsts":0.07,"pick_equivalent":{"label":"Late 4th Round Pick","pick_id":"generic_pick_4_late","value":246.6},"value":153.4},"give":[{"age":0,"id":"PKu","name":"Player PKu","pick_value":60.0,"position":"PICK","search_rank":50,"team":"PICK","years_experience":3},{"age":24,"id":"uw1","name":"Player uw1","position":"WR","search_rank":50,"team":"TST","years_experience":3},{"age":24,"id":"ut","name":"Player ut","position":"TE","search_rank":50,"team":"TST","years_experience":3}],"give_value":2926.0,"league_id":"L1","match_context":{"league_settings":{"dynasty":false,"scoring":"ppr","superflex":false,"te_premium":false},"opponent_surplus":[],"positional_rationale":"Roster profiles align without a single standout gap.","user_needs":[]},"mismatch_score":262.3,"narrative":"Player star1 comes back in a perfectly balanced package. Pick value reflects league depth.","receive":[{"age":24,"id":"star1","name":"Player star1","position":"WR","search_rank":50,"team":"TST","years_experience":3},{"age":0,"id":"PKo1","name":"Player PKo1","pick_value":60.0,"position":"PICK","search_rank":50,"team":"PICK","years_experience":3}],"receive_value":3079.4,"target_user_id":"opp1","target_username":"opp1"}
]
"""

GOLDEN_WIRE = (json.loads(_GOLDEN_WIRE_JSON) if _GOLDEN_WIRE_JSON.strip()
               else None)


if __name__ == "__main__":            # capture mode — see the module docstring
    time.monotonic = lambda: 1.0e6    # freeze the clock as the fixture does
    svc, cards = _eq_deck(0.0)
    print(json.dumps(_wire(cards, svc._players), sort_keys=True,
                     separators=(",", ":")))
