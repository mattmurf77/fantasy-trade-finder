"""F5 (flag deck.taste_vectors) — trade-taste vectors.

docs/plans/tiktok-discovery/prds/F5-taste-vectors.md (incl. the 2026-07-26
board-derived-prior amendment). Contract under test:

  - Flag OFF ⇒ byte-identical ordering, no taste reads/writes, no
    features_json taste_attrs stamp.
  - Zero-history user (no board, no swipes) ⇒ taste_multipliers returns
    None (multiplier exactly 1.0 everywhere == flag-off ordering).
  - 20 pick-heavy likes measurably raise pick-heavy candidates' final
    multipliers for THAT user only.
  - Short-τ signal is near-neutral ~60d later; long-τ retains it.
  - Board prior: a rookie-pick-heavy board yields a positive
    pick-involvement prior before any swipe; refreshed (and clearable) on
    board saves; stored distinguishably (prior: prefix) so swipe-learned
    rows accumulate on top.
  - Taste never overrides untouchables / not-interested — it reorders
    gate-passing candidates only, clamped to [taste_clamp_lo, _hi].
  - Rows GC'd below ε on read/update; table bounded per user.

Same isolation pattern as test_deck_fatigue.py: in-memory SQLite patched
into backend.database, flag helpers patched directly.
"""

import json
import uuid
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, text

import backend.database as db_module
import backend.feature_flags as ff
import backend.server as server
import backend.taste_service as taste
import backend.trade_service as ts
from backend.database import (
    load_user_taste,
    metadata,
    replace_user_taste_prior,
    replace_user_taste_rows,
)
from backend.trade_service import League, LeagueMember, TradeCard, TradeService


LEAGUE = "league_f5"
ME     = "user_me"
OPP    = "user_opp"

SEED = {"star": 1800.0, "mid": 1500.0, "mid2": 1502.0, "scrub": 1250.0,
        "alt": 1499.0, "r1": 1490.0, "r2": 1480.0,
        "pick1": 1650.0, "pick2": 1460.0}


class _P:
    def __init__(self, pid, pos="RB", age=25, team="TST", name=None,
                 pick_value=None):
        self.id = pid
        self.name = name or f"Player {pid}"
        self.position = pos
        self.team = team
        self.age = age
        self.search_rank = 50
        self.pick_value = pick_value


PLAYERS = {
    "star":  _P("star", "WR", 24),
    "mid":   _P("mid", "RB", 27),
    "mid2":  _P("mid2", "RB", 27),
    "scrub": _P("scrub", "TE", 31),
    "alt":   _P("alt", "WR", 22),
    "r1":    _P("r1", "RB", 25),
    "r2":    _P("r2", "RB", 25),
    "pick1": _P("pick1", "PICK", 0, team="PICK", name="2027 1st", pick_value=75.0),
    "pick2": _P("pick2", "PICK", 0, team="PICK", name="2027 2nd", pick_value=40.0),
}


@pytest.fixture()
def mem_engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db_module, "engine", eng):
        yield eng


@pytest.fixture(autouse=True)
def _cfg_defaults():
    old_cfg = dict(ts._cfg)
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    try:
        yield
    finally:
        ts._cfg.clear()
        ts._cfg.update(old_cfg)


def _mk_card(give, recv, composite=5.0, likes_you=False, lane=None,
             target=OPP, give_value=None, receive_value=None):
    c = TradeCard(
        trade_id           = f"t_{uuid.uuid4().hex[:8]}",
        league_id          = LEAGUE,
        proposing_user_id  = ME,
        target_user_id     = target,
        target_username    = "opp",
        give_player_ids    = list(give),
        receive_player_ids = list(recv),
        mismatch_score     = 1.0,
        fairness_score     = 0.9,
        composite_score    = composite,
        likes_you          = likes_you,
        lane               = lane,
    )
    c.give_value = give_value
    c.receive_value = receive_value
    return c


def _iso_ago(days=0.0):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _insert_impression(conn, iid, *, features=None, user_id=ME,
                       league_id=LEAGUE, age_days=0.0):
    conn.execute(text(
        "INSERT INTO deck_impressions "
        "(impression_id, user_id, league_id, deck_job_id, card_index, "
        " features_json, propensity, shape_bucket, served_at) "
        "VALUES (:iid, :uid, :lid, 'job-x', 0, :feat, 1.0, '1x1', :served)"
    ), {"iid": iid, "uid": user_id, "lid": league_id,
        "feat": json.dumps(features or {}), "served": _iso_ago(age_days)})


def _seed_liked_impressions(eng, card, n, action="like", user_id=ME,
                            dwell_ms=None):
    """n impressions of `card` (taste_attrs frozen) + n outcome updates."""
    attrs = taste.card_taste_attrs(card, PLAYERS, SEED)
    iids = []
    with eng.begin() as conn:
        for _ in range(n):
            iid = uuid.uuid4().hex
            _insert_impression(conn, iid, features={"taste_attrs": attrs},
                               user_id=user_id)
            iids.append(iid)
    for iid in iids:
        taste.update_taste_from_outcome(iid, action, dwell_ms=dwell_ms)
    return attrs


def _mults(cards, user_id=ME):
    return taste.taste_multipliers(
        cards, user_id=user_id, players_dict=PLAYERS, seed_map=SEED)


PICK_CARD   = lambda: _mk_card(["mid"], ["pick1"])          # receives a premium pick
PLAYER_CARD = lambda: _mk_card(["mid2"], ["star"])          # pure player swap


# ---------------------------------------------------------------------------
# Flag OFF — byte-identical ordering, no reads, no writes, no stamp
# ---------------------------------------------------------------------------

def test_flag_off_order_deck_untouched(mem_engine):
    cards = [PICK_CARD(), PLAYER_CARD()]
    with ExitStack() as stack:
        for helper in ("_thompson_deck_enabled", "_deck_thompson_v2_enabled",
                       "_deck_diversity_enabled"):
            stack.enter_context(patch.object(server, helper, lambda: False))
        stack.enter_context(patch.object(
            server._taste_service, "load_user_taste",
            MagicMock(side_effect=AssertionError("taste storage touched"))))
        out = server._order_deck(
            cards, user_id=ME, league_id=LEAGUE, job_id="j1",
            seed_map=SEED, fatigue_mult=None, taste_mult=None)
    assert out is cards


def test_flag_off_no_stamp_and_no_writes(mem_engine):
    card = PICK_CARD()
    # Impression writer: no taste_attrs key while the flag is off.
    with patch.object(server, "_deck_taste_enabled", lambda: False):
        server._log_deck_signal_impressions(
            user_id=ME, league_id=LEAGUE, job_id="j-off", cards=[card],
            players_dict=PLAYERS, capture=None, scoring_format="1qb_ppr",
            seed_map=SEED)
    with mem_engine.connect() as conn:
        feat = json.loads(conn.execute(text(
            "SELECT features_json FROM deck_impressions")).scalar())
        iid = conn.execute(text(
            "SELECT impression_id FROM deck_impressions")).scalar()
    assert "taste_attrs" not in feat

    # Outcome path: flag off ⇒ zero user_taste writes.
    with ExitStack() as stack:
        stack.enter_context(patch.object(server, "_deck_signal_v2_enabled", lambda: True))
        stack.enter_context(patch.object(server, "_deck_taste_enabled", lambda: False))
        server._save_deck_outcome_safe(iid, "like", acting_user_id=ME)
    assert load_user_taste(ME) == []


def test_taste_attrs_stamped_when_flag_on(mem_engine):
    card = PICK_CARD()
    with patch.object(server, "_deck_taste_enabled", lambda: True):
        server._log_deck_signal_impressions(
            user_id=ME, league_id=LEAGUE, job_id="j-on", cards=[card],
            players_dict=PLAYERS, capture=None, scoring_format="1qb_ppr",
            seed_map=SEED)
    with mem_engine.connect() as conn:
        feat = json.loads(conn.execute(text(
            "SELECT features_json FROM deck_impressions")).scalar())
    assert feat["taste_attrs"] == taste.card_taste_attrs(card, PLAYERS, SEED)
    assert "pick:premium" in feat["taste_attrs"]
    assert "recvpos:PICK" in feat["taste_attrs"]
    assert f"partner:{OPP}" in feat["taste_attrs"]


# ---------------------------------------------------------------------------
# Zero history — multiplier exactly 1.0 everywhere (flag-on == flag-off)
# ---------------------------------------------------------------------------

def test_zero_history_user_is_exactly_neutral(mem_engine):
    cards = [PICK_CARD(), PLAYER_CARD()]
    assert _mults(cards) is None, "no board + no swipes ⇒ taste layer stays out"
    # The worker passes None ⇒ _order_deck path identical to flag-off.
    with ExitStack() as stack:
        for helper in ("_thompson_deck_enabled", "_deck_thompson_v2_enabled",
                       "_deck_diversity_enabled"):
            stack.enter_context(patch.object(server, helper, lambda: False))
        out = server._order_deck(
            cards, user_id=ME, league_id=LEAGUE, job_id="j",
            seed_map=SEED, taste_mult=None)
    assert out is cards


# ---------------------------------------------------------------------------
# Learning — 20 pick-heavy likes raise pick-heavy candidates, that user only
# ---------------------------------------------------------------------------

def test_20_pick_likes_raise_pick_cards_for_that_user_only(mem_engine):
    _seed_liked_impressions(mem_engine, PICK_CARD(), 20)
    pick_card, player_card = PICK_CARD(), PLAYER_CARD()
    m = _mults([pick_card, player_card])
    assert m is not None
    assert m[id(pick_card)] > 1.0, "liked profile boosts matching cards"
    assert m[id(pick_card)] > m[id(player_card)], \
        "pick-heavy cards outrank non-matching cards"
    # Other users are untouched.
    assert _mults([PICK_CARD()], user_id="user_other") is None


def test_reward_signs_like_pass_not_interested_and_dwell(mem_engine):
    # One like ⇒ +1 on each frozen attr, both vectors.
    attrs = _seed_liked_impressions(mem_engine, PICK_CARD(), 1)
    rows = {r["attr"]: r for r in load_user_taste(ME)}
    assert rows[attrs[0]]["w_short"] == pytest.approx(1.0)
    assert rows[attrs[0]]["w_long"] == pytest.approx(1.0)

    # not_interested ⇒ −4 net −3 after the like.
    _seed_liked_impressions(mem_engine, PICK_CARD(), 1, action="not_interested")
    rows = {r["attr"]: r for r in load_user_taste(ME)}
    assert rows[attrs[0]]["w_short"] == pytest.approx(-3.0, abs=0.01)

    # Long-dwell pass: −0.5 + 0.3 bonus = −0.2 (hesitation is interest).
    _seed_liked_impressions(mem_engine, PLAYER_CARD(), 1, action="pass",
                            dwell_ms=9000)
    p_attrs = taste.card_taste_attrs(PLAYER_CARD(), PLAYERS, SEED)
    rows = {r["attr"]: r for r in load_user_taste(ME)}
    only = [a for a in p_attrs if a not in attrs]
    assert rows[only[0]]["w_short"] == pytest.approx(-0.2, abs=0.01)

    # viewed without a long dwell carries zero reward ⇒ no new writes.
    before = len(load_user_taste(ME))
    _seed_liked_impressions(mem_engine, PLAYER_CARD(), 1, action="viewed")
    assert len(load_user_taste(ME)) == before


# ---------------------------------------------------------------------------
# Decay — March signal near-neutral in short-τ by ~60d, retained in long-τ
# ---------------------------------------------------------------------------

def test_short_tau_decays_long_tau_persists(mem_engine):
    replace_user_taste_rows(ME, {
        "recvpos:RB": (5.0, 5.0, _iso_ago(days=60)),
    })
    short, long_ = taste.load_taste_vectors(ME)
    # exp(-60/21) ≈ 0.057 ⇒ ~0.29 of the original 5 — near-neutral.
    assert short["recvpos:RB"] == pytest.approx(5.0 * 0.0574, rel=0.05)
    assert short["recvpos:RB"] < 0.35
    # exp(-60/180) ≈ 0.717 ⇒ ~3.6 — retained.
    assert long_["recvpos:RB"] == pytest.approx(5.0 * 0.7165, rel=0.05)
    assert long_["recvpos:RB"] > 3.0


# ---------------------------------------------------------------------------
# GC — rows below ε vanish on read/update; table bounded per user
# ---------------------------------------------------------------------------

def test_gc_below_epsilon_on_read_and_bounded_table(mem_engine):
    replace_user_taste_rows(ME, {
        "recvpos:TE": (0.04, 0.04, _iso_ago()),        # both below ε=0.05
        "recvpos:WR": (2.0, 2.0, _iso_ago(days=700)),  # both decay under ε on read
                                                       # (2·e^(−700/180) ≈ 0.041)
    })
    short, long_ = taste.load_taste_vectors(ME)
    assert "recvpos:TE" not in short and "recvpos:TE" not in long_
    assert "recvpos:WR" not in short and "recvpos:WR" not in long_
    assert load_user_taste(ME) == [], "GC'd rows are deleted, not just hidden"

    # Bounded: 20 identical-card likes create exactly |attrs| rows.
    attrs = _seed_liked_impressions(mem_engine, PICK_CARD(), 20)
    assert len(load_user_taste(ME)) == len(attrs)


# ---------------------------------------------------------------------------
# Board-derived prior (amendment) — positive pick prior before any swipe
# ---------------------------------------------------------------------------

def _stub_service(elos: dict):
    rankings = [SimpleNamespace(player=PLAYERS[pid], elo=e)
                for pid, e in elos.items()]
    return SimpleNamespace(
        _seed=dict(SEED),
        get_rankings=lambda position=None: SimpleNamespace(rankings=rankings),
    )


def test_board_prior_pick_heavy_board_boosts_picks_pre_swipe(mem_engine):
    # Board systematically values rookie picks above consensus; players at seed.
    svc = _stub_service({
        "pick1": 1800.0, "pick2": 1600.0,   # >> seed (1650 / 1460)
        "star": SEED["star"], "mid": SEED["mid"], "alt": SEED["alt"],
    })
    with patch.object(server, "_deck_taste_enabled", lambda: True):
        server._refresh_taste_board_prior(ME, svc)

    rows = {r["attr"]: r for r in load_user_taste(ME)}
    assert rows, "board save materialized a prior"
    assert all(a.startswith("prior:") for a in rows), \
        "prior rows are stored distinguishably (prefix)"
    assert rows["prior:pick:premium"]["w_long"] > 0
    assert rows["prior:recvpos:PICK"]["w_long"] > 0
    assert rows["prior:pick:premium"]["w_short"] == 0.0, \
        "prior is a long-interest warm start only"

    # Positive pick-involvement prior before the FIRST swipe boosts pick cards.
    pick_card, player_card = PICK_CARD(), PLAYER_CARD()
    m = _mults([pick_card, player_card])
    assert m is not None
    assert m[id(pick_card)] > 1.0
    assert m[id(pick_card)] > m[id(player_card)]

    # Swipe-learned weights accumulate ON TOP: prior rows are never touched
    # by outcome updates.
    _seed_liked_impressions(mem_engine, PICK_CARD(), 3)
    rows_after = {r["attr"]: r for r in load_user_taste(ME)}
    assert rows_after["prior:pick:premium"]["w_long"] == \
        pytest.approx(rows["prior:pick:premium"]["w_long"])
    assert rows_after["pick:premium"]["w_long"] == pytest.approx(3.0)

    # A later board save REFRESHES the prior — a now-neutral board clears it.
    with patch.object(server, "_deck_taste_enabled", lambda: True):
        server._refresh_taste_board_prior(ME, _stub_service({
            "pick1": SEED["pick1"], "star": SEED["star"],
        }))
    rows_final = {r["attr"]: r for r in load_user_taste(ME)}
    assert not any(a.startswith("prior:") for a in rows_final), \
        "board save rewrites the prior block wholesale"
    assert "pick:premium" in rows_final, "swipe-learned rows survive the refresh"


def test_board_prior_flag_off_or_failure_never_throws(mem_engine):
    with patch.object(server, "_deck_taste_enabled", lambda: False):
        server._refresh_taste_board_prior(ME, _stub_service({"pick1": 1800.0}))
    assert load_user_taste(ME) == []
    broken = SimpleNamespace(_seed=dict(SEED),
                             get_rankings=MagicMock(side_effect=RuntimeError("boom")))
    with patch.object(server, "_deck_taste_enabled", lambda: True):
        server._refresh_taste_board_prior(ME, broken)   # must not raise
    assert load_user_taste(ME) == []


# ---------------------------------------------------------------------------
# Envelope — taste never overrides untouchables / not-interested / gates
# ---------------------------------------------------------------------------

_U_ROSTER = [("uq", "QB"), ("G", "RB"), ("ur2", "RB"),
             ("uw1", "WR"), ("uw2", "WR"), ("ute", "TE")]
_O_ROSTER = [("oq", "QB"), ("R", "RB"), ("or2", "RB"),
             ("ow1", "WR"), ("ow2", "WR"), ("ote", "TE")]
_ALL = _U_ROSTER + _O_ROSTER


def _engine_cards(**kw):
    players = {pid: _P(pid, pos) for pid, pos in _ALL}
    opp_elo = {pid: 1500 for pid, _ in _ALL}
    opp_elo["G"] = 1700
    opp = LeagueMember(user_id="opp", username="opp",
                       roster=[pid for pid, _ in _O_ROSTER],
                       elo_ratings=opp_elo, has_rankings=True)
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo", members=[opp]))
    user_elo = {pid: 1500 for pid, _ in _ALL}
    user_elo["R"] = 1700
    kw.setdefault("fairness_threshold", 0.05)
    cards = svc.generate_trades(
        user_id="user",
        user_elo=user_elo,
        user_roster=[pid for pid, _ in _U_ROSTER],
        league_id="L1",
        seed_elo={pid: (1540 if pid in ("G", "R") else 1500) for pid, _ in _ALL},
        **kw,
    )
    return cards, players


def test_taste_never_overrides_untouchables_or_not_interested(mem_engine):
    old_flags = ff._flags_cache
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "trade_engine.v2": True}
    try:
        # A taste vector that LOVES exactly what the hard filters exclude.
        replace_user_taste_rows("user", {
            "recvpos:RB": (50.0, 50.0, _iso_ago()),
            "cpos:RB":    (50.0, 50.0, _iso_ago()),
            "partner:opp": (50.0, 50.0, _iso_ago()),
        })

        # not-interested: R never comes back, no matter the taste boost.
        guarded, players = _engine_cards(not_interested_ids={"R"})
        assert guarded, "gate-passing candidates still exist"
        seeds = {pid: 1500.0 for pid, _ in _ALL}
        m = taste.taste_multipliers(
            guarded, user_id="user", players_dict=players, seed_map=seeds)
        with ExitStack() as stack:
            for helper in ("_thompson_deck_enabled", "_deck_thompson_v2_enabled",
                           "_deck_diversity_enabled"):
                stack.enter_context(patch.object(server, helper, lambda: False))
            ordered = server._order_deck(
                guarded, user_id="user", league_id="L1", job_id="j",
                seed_map=seeds, taste_mult=m)
        assert set(id(c) for c in ordered) == set(id(c) for c in guarded), \
            "taste reorders — it never adds or removes cards"
        assert all("R" not in c.receive_player_ids for c in ordered)

        # untouchables: G never leaves the roster, taste or no taste.
        locked, players = _engine_cards(untouchable_ids={"G"})
        m2 = taste.taste_multipliers(
            locked, user_id="user", players_dict=players, seed_map=seeds)
        assert all("G" not in c.give_player_ids for c in locked)
        if m2:
            assert all("G" not in c.give_player_ids for c in locked)
    finally:
        ff._flags_cache = old_flags


def test_multiplier_clamped_to_config_band(mem_engine):
    replace_user_taste_rows(ME, {
        a: (1000.0, 1000.0, _iso_ago()) for a in
        taste.card_taste_attrs(PICK_CARD(), PLAYERS, SEED)
    })
    card = PICK_CARD()
    m = _mults([card])
    assert m[id(card)] == pytest.approx(1.4), "clamped at taste_clamp_hi"

    replace_user_taste_rows(ME, {
        a: (-1000.0, -1000.0, _iso_ago()) for a in
        taste.card_taste_attrs(PICK_CARD(), PLAYERS, SEED)
    })
    card = PICK_CARD()
    m = _mults([card])
    assert m[id(card)] == pytest.approx(0.7), "clamped at taste_clamp_lo"


# ---------------------------------------------------------------------------
# Failure paths — outcome hook and serving must never break their callers
# ---------------------------------------------------------------------------

def test_update_and_serving_never_throw(mem_engine):
    with patch.object(taste, "load_deck_impression",
                      MagicMock(side_effect=RuntimeError("db down"))):
        taste.update_taste_from_outcome("iid", "like")   # must not raise

    with patch.object(taste, "load_user_taste",
                      MagicMock(side_effect=RuntimeError("db down"))):
        assert taste.taste_multipliers(
            [PICK_CARD()], user_id=ME, players_dict=PLAYERS,
            seed_map=SEED) is None

    # The full outcome route helper stays never-throwing with taste on.
    with ExitStack() as stack:
        stack.enter_context(patch.object(server, "_deck_signal_v2_enabled", lambda: True))
        stack.enter_context(patch.object(server, "_deck_taste_enabled", lambda: True))
        server._save_deck_outcome_safe("nonexistent-impression", "like",
                                       acting_user_id=ME)


def test_unknown_impression_or_zero_reward_writes_nothing(mem_engine):
    taste.update_taste_from_outcome(uuid.uuid4().hex, "like")   # unknown iid
    assert load_user_taste(ME) == []
    _seed_liked_impressions(mem_engine, PICK_CARD(), 1, action="undo")
    assert load_user_taste(ME) == []


# ---------------------------------------------------------------------------
# Impression-ownership validation — a client-supplied impression_id only
# writes when it exists, belongs to the ACTING user, and is recent. Anything
# else is counted-and-dropped: no deck_outcomes row, no taste write.
# ---------------------------------------------------------------------------

def _outcome_count(eng):
    with eng.connect() as conn:
        return conn.execute(text("SELECT COUNT(*) FROM deck_outcomes")).scalar()


def _call_outcome_safe(iid, acting_user_id):
    with ExitStack() as stack:
        stack.enter_context(patch.object(server, "_deck_signal_v2_enabled", lambda: True))
        stack.enter_context(patch.object(server, "_deck_taste_enabled", lambda: True))
        server._save_deck_outcome_safe(iid, "like", acting_user_id=acting_user_id)


def test_foreign_impression_rejected_writes_nothing(mem_engine):
    attrs = taste.card_taste_attrs(PICK_CARD(), PLAYERS, SEED)
    iid = uuid.uuid4().hex
    with mem_engine.begin() as conn:
        _insert_impression(conn, iid, features={"taste_attrs": attrs},
                           user_id=OPP)   # owned by the OTHER user
    before = server.deck_outcome_reject_counters()

    _call_outcome_safe(iid, acting_user_id=ME)

    assert _outcome_count(mem_engine) == 0, "foreign id must not label anyone"
    assert load_user_taste(OPP) == [], "owner's taste vector stays untouched"
    assert load_user_taste(ME) == []
    after = server.deck_outcome_reject_counters()
    assert after["foreign"] == before["foreign"] + 1


def test_unknown_stale_and_unauthenticated_rejected(mem_engine):
    before = server.deck_outcome_reject_counters()

    # Unknown impression_id ⇒ counted, nothing written.
    _call_outcome_safe(uuid.uuid4().hex, acting_user_id=ME)
    # Stale impression (own, but past the recency bound) ⇒ counted-and-dropped.
    stale_iid = uuid.uuid4().hex
    with mem_engine.begin() as conn:
        _insert_impression(conn, stale_iid, user_id=ME,
                           age_days=server._DECK_OUTCOME_MAX_AGE_DAYS + 15)
    _call_outcome_safe(stale_iid, acting_user_id=ME)
    # No route-resolved user (e.g. /api/events with a dead token) ⇒ dropped.
    fresh_iid = uuid.uuid4().hex
    with mem_engine.begin() as conn:
        _insert_impression(conn, fresh_iid, user_id=ME)
    _call_outcome_safe(fresh_iid, acting_user_id=None)

    assert _outcome_count(mem_engine) == 0
    assert load_user_taste(ME) == []
    after = server.deck_outcome_reject_counters()
    assert after["unknown"] == before["unknown"] + 1
    assert after["stale"] == before["stale"] + 1
    assert after["no_user"] == before["no_user"] + 1


def test_own_recent_impression_still_writes_outcome_and_taste(mem_engine):
    attrs = taste.card_taste_attrs(PICK_CARD(), PLAYERS, SEED)
    iid = uuid.uuid4().hex
    with mem_engine.begin() as conn:
        _insert_impression(conn, iid, features={"taste_attrs": attrs},
                           user_id=ME)
    _call_outcome_safe(iid, acting_user_id=ME)

    assert _outcome_count(mem_engine) == 1, "the legitimate path is unchanged"
    rows = {r["attr"]: r for r in load_user_taste(ME)}
    assert rows[attrs[0]]["w_short"] == pytest.approx(1.0)
