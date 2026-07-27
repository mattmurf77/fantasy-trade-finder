"""F2 (flag deck.thompson_v2) — Thompson v2 bandit hygiene.

docs/plans/tiktok-discovery/prds/F2-thompson-v2.md. The v2 sampler replaces
WHAT feeds the per-arm Beta draw in server._order_deck:

  1. Pessimistic priors Beta(1, 1/p̂) at the trailing-30d global like rate
     (config fallback thompson_prior_base_rate).
  2. Lazy posterior decay γ^age_days (thompson_decay_gamma), read-time only.
  3. Cascade updates: only outcomes whose impression has a `viewed` event
     count (F1 join) — served-never-fronted cards update nothing.
  4. Arm hierarchy: archetype (lane) × shape, warm-started from the parent
     shape posterior below 5 raw observations; 120d inactivity TTL on read.

Contract under test: flag OFF ⇒ the v1 sampler path is byte-identical;
multiplier bounded [0.5, 1.5] under both; F1's propensity capture records
the multiplier actually applied under both.

Same isolation pattern as test_deck_ordering.py: in-memory SQLite patched
into backend.database, flag helpers patched directly.
"""

import json
import random
import statistics
import uuid
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, text

import backend.database as db_module
import backend.server as server
import backend.trade_service as ts_module
from backend.database import (
    load_deck_arm_events,
    load_global_like_rate,
    load_legacy_shape_counts,
    metadata,
)
from backend.trade_service import TradeCard


LEAGUE = "league_tv2"
ME     = "user_me"
OPP    = "user_opp"


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def mem_engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db_module, "engine", eng):
        yield eng


@pytest.fixture(autouse=True)
def _reset_prior_cache():
    """The p̂ cache is module-level state — never let one test's rate leak
    into another."""
    server._thompson_prior_cache.update(rate=None, at=0.0)
    yield
    server._thompson_prior_cache.update(rate=None, at=0.0)


def _flags(v1=False, v2=False, diversity=False):
    stack = ExitStack()
    stack.enter_context(patch.object(server, "_thompson_deck_enabled", lambda: v1))
    stack.enter_context(patch.object(server, "_deck_thompson_v2_enabled", lambda: v2))
    stack.enter_context(patch.object(server, "_deck_diversity_enabled", lambda: diversity))
    return stack


def _mk_card(give, recv, composite, likes_you=False, lane=None):
    return TradeCard(
        trade_id           = f"t_{uuid.uuid4().hex[:8]}",
        league_id          = LEAGUE,
        proposing_user_id  = ME,
        target_user_id     = OPP,
        target_username    = "opp",
        give_player_ids    = list(give),
        receive_player_ids = list(recv),
        mismatch_score     = 1.0,
        fairness_score     = 0.9,
        composite_score    = composite,
        likes_you          = likes_you,
        lane               = lane,
    )


def _iso_ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _insert_decision(conn, user_id, give_ids, recv_ids, decision,
                     league_id=LEAGUE, age_days=1):
    conn.execute(text(
        "INSERT INTO trade_decisions "
        "(user_id, league_id, give_player_ids, receive_player_ids, decision, created_at) "
        "VALUES (:uid, :lid, :give, :recv, :dec, :created)"
    ), {
        "uid": user_id, "lid": league_id,
        "give": json.dumps(give_ids), "recv": json.dumps(recv_ids),
        "dec": decision, "created": _iso_ago(age_days),
    })


def _insert_deck_impression(conn, impression_id, user_id, shape,
                            archetype=None, age_days=0, league_id=LEAGUE):
    conn.execute(text(
        "INSERT INTO deck_impressions "
        "(impression_id, user_id, league_id, deck_job_id, card_index, "
        " propensity, archetype, shape_bucket, served_at) "
        "VALUES (:iid, :uid, :lid, 'job-x', 0, 1.0, :arch, :shape, :served)"
    ), {"iid": impression_id, "uid": user_id, "lid": league_id,
        "arch": archetype, "shape": shape, "served": _iso_ago(age_days)})


def _insert_deck_outcome(conn, impression_id, action, age_days=0):
    conn.execute(text(
        "INSERT INTO deck_outcomes (impression_id, action, acted_at) "
        "VALUES (:iid, :act, :at)"
    ), {"iid": impression_id, "act": action, "at": _iso_ago(age_days)})


def _seed_arm_events(conn, user_id, shape, likes, passes,
                     archetype=None, age_days=0, viewed=True):
    """likes+passes viewed-gated (unless viewed=False) deck events for one
    arm — one impression + outcome rows per event."""
    for i in range(likes + passes):
        iid = uuid.uuid4().hex
        _insert_deck_impression(conn, iid, user_id, shape,
                                archetype=archetype, age_days=age_days)
        if viewed:
            _insert_deck_outcome(conn, iid, "viewed", age_days=age_days)
        _insert_deck_outcome(conn, iid, "like" if i < likes else "pass",
                             age_days=age_days)


def _order(cards, job_id="job-A", capture=None):
    return server._order_deck(
        cards, user_id=ME, league_id=LEAGUE, job_id=job_id,
        seed_map={}, capture=capture,
    )


def _mults_for(card_or_cards, user_id=ME, jobs=300):
    """Draw the v2 multiplier for the given card(s) across `jobs`
    deterministic per-job seeds; returns the flat list of multipliers."""
    cards = card_or_cards if isinstance(card_or_cards, list) else [card_or_cards]
    out = []
    for i in range(jobs):
        rng = random.Random(server._deck_rng_seed(user_id, LEAGUE, f"job-{i}"))
        m = server._thompson_v2_multipliers(
            cards, rng=rng, user_id=user_id, league_id=LEAGUE)
        out.extend(m[id(c)] for c in cards)
    return out


# ---------------------------------------------------------------------------
# Flag OFF — v1 sampler byte-identical, v2 loaders never touched
# ---------------------------------------------------------------------------

def test_v2_off_v1_sampler_byte_identical(mem_engine):
    """With deck.thompson_v2 OFF the v1 path must consume the same rng in
    the same sequence and produce the same order + captured propensities as
    a literal reimplementation of the v1 math — and never touch a v2
    loader."""
    with mem_engine.begin() as conn:
        for _ in range(6):
            _insert_decision(conn, ME, ["a", "b"], ["c"], "like")   # 2x1
            _insert_decision(conn, ME, ["a"], ["c"], "pass")        # 1x1
    cards = [
        _mk_card(["g1"], ["r1"], composite=10.0),
        _mk_card(["g2", "g3"], ["r2"], composite=9.5),
        _mk_card(["g4"], ["r3", "r4"], composite=9.0),
    ]
    shape_counts = {"2x1": (6, 0), "1x1": (0, 6)}

    for job in ("job-1", "job-2", "job-3"):
        # Literal v1 reimplementation.
        rng = random.Random(server._deck_rng_seed(ME, LEAGUE, job))
        sample = {}
        for shape in sorted({server._card_shape(c) for c in cards}):
            likes, passes = shape_counts.get(shape, (0, 0))
            sample[shape] = rng.betavariate(1 + likes, 2 + passes)
        key = {id(c): c.composite_score * (0.5 + sample[server._card_shape(c)])
               for c in cards}
        expected = sorted(cards, key=lambda c: (bool(c.likes_you), key[id(c)]),
                          reverse=True)
        expected_prop = {id(c): 0.5 + sample[server._card_shape(c)] for c in cards}

        capture = {}
        with _flags(v1=True, v2=False), \
             patch.object(server, "load_deck_arm_events",
                          MagicMock(side_effect=AssertionError("v2 loader touched"))), \
             patch.object(server, "load_legacy_shape_counts",
                          MagicMock(side_effect=AssertionError("v2 loader touched"))), \
             patch.object(server, "load_global_like_rate",
                          MagicMock(side_effect=AssertionError("v2 loader touched"))):
            out = _order(cards, job_id=job, capture=capture)

        assert [c.trade_id for c in out] == [c.trade_id for c in expected]
        assert capture["propensity"] == pytest.approx(expected_prop)


# ---------------------------------------------------------------------------
# Pessimistic prior — zero data ⇒ expected multiplier ≈ 1.0, no junk boost
# ---------------------------------------------------------------------------

def test_zero_data_expected_multiplier_near_one(mem_engine):
    card = _mk_card(["g1"], ["r1"], composite=5.0)
    with patch.object(server, "_thompson_prior_base_rate", lambda: 0.25):
        mults = _mults_for(card, jobs=400)
    assert all(0.5 <= m <= 1.5 for m in mults)
    mean = statistics.mean(mults)
    # Analytic E[clamp(Beta(1,4)/0.2, .5, 1.5)] ≈ 0.92: neutral-to-slightly-
    # pessimistic — nothing like v1's optimistic junk-exploration boost.
    assert 0.85 < mean < 1.05, mean


# ---------------------------------------------------------------------------
# Lazy decay — an old posterior is wider than a fresh equal-count one
# ---------------------------------------------------------------------------

def test_decayed_posterior_wider_than_fresh(mem_engine):
    fresh_user, old_user = "u_fresh", "u_old"
    with mem_engine.begin() as conn:
        _seed_arm_events(conn, fresh_user, "1x1", likes=25, passes=25, age_days=0)
        _seed_arm_events(conn, old_user,   "1x1", likes=25, passes=25, age_days=90)

    a0, b0 = 1.0, 1.0 / 0.3
    cf, pf = server._thompson_v2_arm_stats(fresh_user, LEAGUE)
    co, po = server._thompson_v2_arm_stats(old_user, LEAGUE)
    af, bf = server._thompson_v2_posterior(None, "1x1", cf, pf, a0, b0)
    ao, bo = server._thompson_v2_posterior(None, "1x1", co, po, a0, b0)

    # γ=0.995^90 ≈ 0.637 — the old arm's effective mass must have shrunk.
    assert ao + bo < af + bf
    assert ao == pytest.approx(1.0 + 25 * 0.995 ** 90, rel=0.02)

    # Fixed-seed statistical assertion: same seed, same draw count — the
    # decayed posterior's samples must spread wider.
    rng_f, rng_o = random.Random(1234), random.Random(1234)
    draws_fresh = [rng_f.betavariate(af, bf) for _ in range(4000)]
    draws_old   = [rng_o.betavariate(ao, bo) for _ in range(4000)]
    assert statistics.pstdev(draws_old) > statistics.pstdev(draws_fresh)


# ---------------------------------------------------------------------------
# Cascade rule — served-but-never-viewed outcomes move NOTHING
# ---------------------------------------------------------------------------

def test_served_never_viewed_updates_nothing(mem_engine):
    with mem_engine.begin() as conn:
        _seed_arm_events(conn, ME, "1x1", likes=10, passes=0,
                         archetype="window", viewed=False)
    assert server._thompson_v2_arm_stats(ME, LEAGUE) == ({}, {})

    # Late `viewed` labels self-heal on the next read: add the views and the
    # same outcomes now count.
    with mem_engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT impression_id FROM deck_impressions WHERE user_id = :u"
        ), {"u": ME}).fetchall()
        for r in rows:
            _insert_deck_outcome(conn, r.impression_id, "viewed")
    child, parent = server._thompson_v2_arm_stats(ME, LEAGUE)
    assert parent["1x1"][0] == pytest.approx(10.0, rel=0.01)
    assert child[("window", "1x1")][2] == 10          # n_raw


def test_arm_stats_read_failure_degrades_to_prior(mem_engine):
    card = _mk_card(["g1"], ["r1"], composite=5.0)
    rng = random.Random(7)
    with patch.object(server, "_thompson_prior_base_rate", lambda: 0.3), \
         patch.object(server, "load_deck_arm_events",
                      MagicMock(side_effect=RuntimeError("db down"))):
        m = server._thompson_v2_multipliers(
            [card], rng=rng, user_id=ME, league_id=LEAGUE)
    assert 0.5 <= m[id(card)] <= 1.5


# ---------------------------------------------------------------------------
# Arm hierarchy — child <5 obs warm-starts from (samples near) the parent
# ---------------------------------------------------------------------------

def test_child_below_min_obs_uses_parent_posterior(mem_engine):
    with mem_engine.begin() as conn:
        # Frozen legacy: 40 likes on 1x1, created BEFORE the first impression.
        for _ in range(40):
            _insert_decision(conn, ME, ["a"], ["b"], "like", age_days=10)
        # F1-era child arm with only 2 viewed likes.
        _seed_arm_events(conn, ME, "1x1", likes=2, passes=0,
                         archetype="window", age_days=0)

    a0, b0 = 1.0, 1.0 / 0.3
    child, parent = server._thompson_v2_arm_stats(ME, LEAGUE)
    assert child[("window", "1x1")][2] == 2           # below warm-start bar

    post_child  = server._thompson_v2_posterior("window", "1x1", child, parent, a0, b0)
    post_parent = server._thompson_v2_posterior(None,     "1x1", child, parent, a0, b0)
    assert post_child == post_parent, "child <5 obs must return the parent posterior"
    # Parent carries the decayed legacy mass + the child's 2 likes.
    assert post_parent[0] == pytest.approx(1.0 + 40 * 0.995 ** 10 + 2.0, rel=0.02)

    # Behavioral: the strong parent (all likes) pins the child card's
    # multiplier near the 1.5 cap; a no-data arm stays near 1.0.
    warm_card = _mk_card(["g1"], ["r1"], composite=5.0, lane="window")
    cold_card = _mk_card([f"g{i}" for i in range(5)],
                         [f"r{i}" for i in range(5)], composite=5.0, lane="window")
    with patch.object(server, "_thompson_prior_base_rate", lambda: 0.3):
        warm_mean = statistics.mean(_mults_for(warm_card, jobs=200))
        cold_mean = statistics.mean(_mults_for(cold_card, jobs=200))
    assert warm_mean > 1.4, warm_mean
    assert cold_mean < 1.1, cold_mean


def test_child_at_min_obs_stands_alone(mem_engine):
    with mem_engine.begin() as conn:
        for _ in range(10):
            _insert_decision(conn, ME, ["a"], ["b"], "like", age_days=10)
        _seed_arm_events(conn, ME, "1x1", likes=0, passes=6,
                         archetype="value", age_days=0)
    a0, b0 = 1.0, 1.0 / 0.3
    child, parent = server._thompson_v2_arm_stats(ME, LEAGUE)
    assert child[("value", "1x1")][2] == 6
    post_child  = server._thompson_v2_posterior("value", "1x1", child, parent, a0, b0)
    post_parent = server._thompson_v2_posterior(None,    "1x1", child, parent, a0, b0)
    assert post_child != post_parent
    assert post_child[0] == pytest.approx(1.0)        # no likes of its own
    assert post_child[1] == pytest.approx(b0 + 6.0, rel=0.01)


# ---------------------------------------------------------------------------
# 120d inactivity TTL — applied on read
# ---------------------------------------------------------------------------

def test_ttl_expires_inactive_arms_on_read(mem_engine):
    with mem_engine.begin() as conn:
        _seed_arm_events(conn, ME, "1x1", likes=30, passes=0,
                         archetype="window", age_days=130)
        for _ in range(20):
            _insert_decision(conn, ME, ["a"], ["b"], "like", age_days=130)
    assert server._thompson_v2_arm_stats(ME, LEAGUE) == ({}, {})


# ---------------------------------------------------------------------------
# F1 capture — the logged propensity is the multiplier actually applied
# ---------------------------------------------------------------------------

def test_capture_records_actual_v2_multiplier(mem_engine):
    with mem_engine.begin() as conn:
        _seed_arm_events(conn, ME, "2x1", likes=8, passes=0, archetype="window")
    cards = [
        _mk_card(["g1"], ["r1"], composite=10.0),
        _mk_card(["g2", "g3"], ["r2"], composite=9.0, lane="window"),
        _mk_card(["g4"], ["r4"], composite=1.0, likes_you=True),
    ]
    capture = {}
    with _flags(v2=True), \
         patch.object(server, "_thompson_prior_base_rate", lambda: 0.3):
        out = _order(cards, job_id="job-cap", capture=capture)

    assert out[0].likes_you, "likes_you stays pinned under v2"
    prop, fkey = capture["propensity"], capture["final_key"]
    for c in cards:
        assert 0.5 <= prop[id(c)] <= 1.5
        # final key = composite × captured multiplier ⇒ the capture is the
        # multiplier ACTUALLY drawn/applied, not a recomputation.
        assert fkey[id(c)] == pytest.approx(c.composite_score * prop[id(c)])

    # Deterministic per-job seed, as in v1.
    with _flags(v2=True), \
         patch.object(server, "_thompson_prior_base_rate", lambda: 0.3):
        again = _order(cards, job_id="job-cap")
    assert [c.trade_id for c in again] == [c.trade_id for c in out]


# ---------------------------------------------------------------------------
# database.py loaders — seam, viewed gate, global rate
# ---------------------------------------------------------------------------

def test_legacy_seam_freezes_at_first_impression(mem_engine):
    with mem_engine.begin() as conn:
        _insert_decision(conn, ME, ["a"], ["b"], "like", age_days=20)   # pre-seam
        _insert_decision(conn, ME, ["c"], ["d"], "pass", age_days=15)   # pre-seam
        _insert_deck_impression(conn, uuid.uuid4().hex, ME, "1x1", age_days=10)
        _insert_decision(conn, ME, ["e"], ["f"], "like", age_days=5)    # post-seam
    counts = load_legacy_shape_counts(ME, LEAGUE)
    assert set(counts) == {"1x1"}
    likes, passes, last_at = counts["1x1"]
    assert (likes, passes) == (1, 1)
    assert last_at.startswith(_iso_ago(15)[:10])


def test_legacy_seam_no_impressions_means_all_legacy(mem_engine):
    with mem_engine.begin() as conn:
        _insert_decision(conn, ME, ["a"], ["b"], "like", age_days=3)
        _insert_decision(conn, ME, ["a", "b"], ["c"], "pass", age_days=2)
    counts = load_legacy_shape_counts(ME, LEAGUE)
    assert counts["1x1"][:2] == (1, 0)
    assert counts["2x1"][:2] == (0, 1)


def test_load_deck_arm_events_viewed_gate_and_scope(mem_engine):
    with mem_engine.begin() as conn:
        viewed_iid, blind_iid = uuid.uuid4().hex, uuid.uuid4().hex
        _insert_deck_impression(conn, viewed_iid, ME, "1x1", archetype="window")
        _insert_deck_outcome(conn, viewed_iid, "viewed")
        _insert_deck_outcome(conn, viewed_iid, "like")
        _insert_deck_impression(conn, blind_iid, ME, "2x1")
        _insert_deck_outcome(conn, blind_iid, "like")            # never viewed
        other_iid = uuid.uuid4().hex
        _insert_deck_impression(conn, other_iid, OPP, "1x1")     # other user
        _insert_deck_outcome(conn, other_iid, "viewed")
        _insert_deck_outcome(conn, other_iid, "pass")
    events = load_deck_arm_events(ME, LEAGUE)
    assert len(events) == 1
    arch, shape, action, _ = events[0]
    assert (arch, shape, action) == ("window", "1x1", "like")


def test_prior_base_rate_computed_cached_and_fallback(mem_engine):
    with mem_engine.begin() as conn:
        for i in range(8):
            _insert_decision(conn, f"u{i}", ["a"], ["b"], "like", age_days=5)
        for i in range(4):
            _insert_decision(conn, f"v{i}", ["a"], ["b"], "pass", age_days=5)
        _insert_decision(conn, "w0", ["a"], ["b"], "like", age_days=45)  # outside window
    assert load_global_like_rate(days=30) == (8, 12)
    assert server._thompson_prior_base_rate() == pytest.approx(8 / 12)

    # Cached: new rows don't change the rate within the cache TTL.
    with mem_engine.begin() as conn:
        for i in range(20):
            _insert_decision(conn, f"x{i}", ["a"], ["b"], "pass", age_days=1)
    assert server._thompson_prior_base_rate() == pytest.approx(8 / 12)


def test_prior_base_rate_thin_window_uses_config_fallback(mem_engine):
    with mem_engine.begin() as conn:
        for i in range(3):    # < _THOMPSON_PRIOR_MIN_N
            _insert_decision(conn, f"u{i}", ["a"], ["b"], "like", age_days=5)
    with patch.dict(ts_module._cfg, {"thompson_prior_base_rate": 0.42}):
        assert server._thompson_prior_base_rate() == pytest.approx(0.42)
    server._thompson_prior_cache.update(rate=None, at=0.0)
    with patch.dict(ts_module._cfg, {"thompson_prior_base_rate": 0.001}):
        assert server._thompson_prior_base_rate() == pytest.approx(0.05)  # clamped


# ---------------------------------------------------------------------------
# _order_deck integration — v2 alone orders the deck, bounds always hold
# ---------------------------------------------------------------------------

def test_v2_flag_alone_enables_ordering(mem_engine):
    with mem_engine.begin() as conn:
        _seed_arm_events(conn, ME, "2x1", likes=20, passes=0)
        _seed_arm_events(conn, ME, "1x1", likes=0, passes=20)
    liked = _mk_card(["g1", "g2"], ["r1"], composite=9.0)
    hated = _mk_card(["g3"], ["r3"], composite=10.0)
    with _flags(v1=False, v2=True), \
         patch.object(server, "_thompson_prior_base_rate", lambda: 0.3):
        wins = sum(
            _order([hated, liked], job_id=f"job-{i}")[0] is liked
            for i in range(25)
        )
    # Liked arm pins ≈1.5, hated arm ≈0.5: 9.0×1.5 ≫ 10.0×0.5.
    assert wins >= 23
