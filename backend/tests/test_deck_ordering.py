"""Tier 2 amendments A5 + A6 — deck ordering (server._order_deck).

A5 (flag trade.thompson_deck): Thompson-sampled ordering — one Beta(1+likes,
2+passes) draw per package-shape bucket, ordering key = composite × (0.5+p),
deterministically seeded per (user, league, job).

A6 (flag trade.deck_diversity): league-wide diversification — cards whose top
receive asset already saturates >= diversity_user_cap OTHER members' recent
decks get their key × diversity_penalty; the served deck keeps at most
deck_max_per_target cards per target (never dropping likes_you cards, never
shrinking below 5 cards).

All tests run against an isolated in-memory SQLite engine patched into
backend.database (same pattern as test_trade_match_flow.py). Flag helpers are
patched directly so results don't depend on config/features.json.
"""

import json
import time
import uuid
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select, text

import backend.database as db_module
import backend.server as server
from backend.database import (
    load_recent_impression_target_user_counts,
    load_trade_decision_shape_counts,
    metadata,
    trade_impressions_table,
)
from backend.ranking_service import Player, RankingService
from backend.trade_service import League, LeagueMember, TradeCard, TradeService


LEAGUE = "league_ord"
ME     = "user_me"
OPP    = "user_opp"


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def mem_engine():
    """Fresh in-memory SQLite engine with the full schema, patched in as the
    module-level engine so all database.py functions use it."""
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db_module, "engine", eng):
        yield eng


def _flags(thompson: bool, diversity: bool):
    """Patch server's flag helpers — keeps tests independent of features.json."""
    stack = ExitStack()
    stack.enter_context(patch.object(server, "_thompson_deck_enabled", lambda: thompson))
    stack.enter_context(patch.object(server, "_deck_diversity_enabled", lambda: diversity))
    return stack


def _mk_card(give, recv, composite, likes_you=False, target=OPP):
    return TradeCard(
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
    )


def _order(cards, job_id="job-A", seed_map=None):
    return server._order_deck(
        cards, user_id=ME, league_id=LEAGUE, job_id=job_id,
        seed_map=seed_map or {},
    )


def _ids(cards):
    return [c.trade_id for c in cards]


def _insert_decision(conn, user_id, give_ids, recv_ids, decision,
                     league_id=LEAGUE, age_days=1):
    created = (datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat()
    conn.execute(text(
        "INSERT INTO trade_decisions "
        "(user_id, league_id, give_player_ids, receive_player_ids, decision, created_at) "
        "VALUES (:uid, :lid, :give, :recv, :dec, :created)"
    ), {
        "uid": user_id, "lid": league_id,
        "give": json.dumps(give_ids), "recv": json.dumps(recv_ids),
        "dec": decision, "created": created,
    })


def _insert_impression(conn, user_id, recv_ids, league_id=LEAGUE, age_days=1):
    shown = (datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat()
    conn.execute(text(
        "INSERT INTO trade_impressions "
        "(user_id, league_id, give_player_ids, receive_player_ids, shown_at) "
        "VALUES (:uid, :lid, '[]', :recv, :shown)"
    ), {"uid": user_id, "lid": league_id,
        "recv": json.dumps(recv_ids), "shown": shown})


# ---------------------------------------------------------------------------
# Flags off — ordering untouched
# ---------------------------------------------------------------------------

def test_flags_off_preserves_input_order(mem_engine):
    cards = [
        _mk_card(["g1"], ["r1"], composite=1.0),
        _mk_card(["g2"], ["r2"], composite=9.0),   # deliberately NOT sorted
        _mk_card(["g3"], ["r3"], composite=5.0),
    ]
    with _flags(thompson=False, diversity=False):
        out = _order(cards)
    assert out is cards, "both flags off must return the input untouched"


# ---------------------------------------------------------------------------
# A5 — deterministic seeding
# ---------------------------------------------------------------------------

def _multi_shape_deck():
    """Cards spread across shape buckets with near-equal composites, so
    cross-bucket Beta draws can plausibly reorder them."""
    shapes = [(1, 1), (2, 1), (1, 2), (2, 2), (3, 2)]
    cards = []
    for i in range(10):
        ng, nr = shapes[i % len(shapes)]
        give = [f"g{i}_{k}" for k in range(ng)]
        recv = [f"r{i}_{k}" for k in range(nr)]
        cards.append(_mk_card(give, recv, composite=10.0 - i * 0.1))
    return cards


def test_same_job_id_yields_stable_order(mem_engine):
    cards = _multi_shape_deck()
    with _flags(thompson=True, diversity=False):
        first  = _ids(_order(cards, job_id="job-stable"))
        second = _ids(_order(cards, job_id="job-stable"))
    assert first == second, "same (user, league, job) must produce identical order"


def test_different_job_id_can_reorder(mem_engine):
    cards = _multi_shape_deck()
    with _flags(thompson=True, diversity=False):
        baseline = _ids(_order(cards, job_id="job-0"))
        others   = {tuple(_ids(_order(cards, job_id=f"job-{i}"))) for i in range(1, 21)}
    assert any(o != tuple(baseline) for o in others), \
        "20 different job ids should produce at least one different order"


def test_same_bucket_higher_composite_always_wins(mem_engine):
    """Within one bucket the Beta sample is shared, so the bounded multiplier
    can never invert quality: composite order is preserved for every seed."""
    cards = [
        _mk_card(["g1"], ["r1"], composite=10.0),
        _mk_card(["g2"], ["r2"], composite=5.0),
        _mk_card(["g3"], ["r3"], composite=1.0),
    ]
    expected = _ids(cards)
    with _flags(thompson=True, diversity=False):
        for i in range(25):
            assert _ids(_order(cards, job_id=f"job-{i}")) == expected


def test_thompson_uses_decision_history(mem_engine):
    """Bucket posteriors come from trade_decisions package shapes: a bucket
    with many likes (Beta(1+20, 2)) reliably outdraws one with many passes
    (Beta(1, 2+20)), lifting a slightly-lower-composite card above a
    slightly-higher one from the disliked bucket."""
    with mem_engine.begin() as conn:
        for _ in range(20):
            _insert_decision(conn, ME, ["a", "b"], ["c"], "like")    # 2x1 loved
            _insert_decision(conn, ME, ["a"], ["c"], "pass")         # 1x1 hated
    liked_shape  = _mk_card(["g1", "g2"], ["r1"], composite=9.0)
    hated_shape  = _mk_card(["g3"], ["r3"], composite=10.0)
    with _flags(thompson=True, diversity=False):
        wins = sum(
            _order([hated_shape, liked_shape], job_id=f"job-{i}")[0] is liked_shape
            for i in range(25)
        )
    # E[mult] ≈ 1.45 vs ≈ 0.55: 9.0×~1.45 ≫ 10.0×~0.55 — wins essentially always.
    assert wins >= 23


# ---------------------------------------------------------------------------
# likes_you pinned at the top under both flags
# ---------------------------------------------------------------------------

def test_likes_you_stays_pinned_under_both_flags(mem_engine):
    with mem_engine.begin() as conn:
        # Saturate the likes-you card's target so even the A6 penalty applies.
        for u in ("u1", "u2", "u3"):
            _insert_impression(conn, u, ["star"])
    ly = _mk_card(["g0"], ["star"], composite=0.5, likes_you=True)
    cards = [
        _mk_card(["g1"], ["r1"], composite=10.0),
        ly,
        _mk_card(["g2"], ["r2"], composite=8.0),
    ]
    with _flags(thompson=True, diversity=True):
        for i in range(10):
            out = _order(cards, job_id=f"job-{i}")
            assert out[0] is ly, "likes_you card must stay at position 0"


# ---------------------------------------------------------------------------
# A6 — league-wide diversification penalty
# ---------------------------------------------------------------------------

def test_diversity_penalty_demotes_saturated_target(mem_engine):
    """3 distinct OTHER users were shown 'star' (cap default 3) → the card
    targeting star gets key 10×0.6 = 6 < 9 and sorts below the other card."""
    with mem_engine.begin() as conn:
        for u in ("u1", "u2", "u3"):
            _insert_impression(conn, u, ["star"])
    saturated = _mk_card(["g1"], ["star"],  composite=10.0)
    fresh     = _mk_card(["g2"], ["other"], composite=9.0)
    with _flags(thompson=False, diversity=True):
        out = _order([saturated, fresh])
    assert out[0] is fresh
    assert out[1] is saturated


def test_diversity_below_cap_no_penalty(mem_engine):
    """Only 2 other users shown the target (< cap 3) → no penalty applied."""
    with mem_engine.begin() as conn:
        for u in ("u1", "u2"):
            _insert_impression(conn, u, ["star"])
    a = _mk_card(["g1"], ["star"],  composite=10.0)
    b = _mk_card(["g2"], ["other"], composite=9.0)
    with _flags(thompson=False, diversity=True):
        out = _order([a, b])
    assert out[0] is a


# ---------------------------------------------------------------------------
# A6 — intra-deck per-target cap
# ---------------------------------------------------------------------------

def test_intra_deck_cap_keeps_best_per_target(mem_engine):
    star_cards  = [_mk_card([f"g{i}"], ["star"], composite=10.0 - i) for i in range(4)]
    other_cards = [_mk_card([f"h{i}"], [f"r{i}"], composite=6.0 - i) for i in range(3)]
    with _flags(thompson=False, diversity=True):
        out = _order(star_cards + other_cards)
    assert len(out) == 6, "worst star card dropped (cap 3 per target)"
    kept_star = [c for c in out if c.receive_player_ids == ["star"]]
    assert kept_star == star_cards[:3], "the best 3 star cards are kept, in order"
    assert star_cards[3] not in out


def test_intra_deck_cap_never_drops_below_five(mem_engine):
    """6 cards, all the same target: cap 3 would leave 3 — the best dropped
    cards are restored so the deck never shrinks below 5."""
    cards = [_mk_card([f"g{i}"], ["star"], composite=10.0 - i) for i in range(6)]
    with _flags(thompson=False, diversity=True):
        out = _order(cards)
    assert len(out) == 5
    assert _ids(out) == _ids(cards[:5]), "kept the 5 best, in score order"


def test_intra_deck_cap_skips_small_decks(mem_engine):
    """A deck of <= 5 cards is never trimmed, even when one target saturates it."""
    cards = [_mk_card([f"g{i}"], ["star"], composite=10.0 - i) for i in range(5)]
    with _flags(thompson=False, diversity=True):
        out = _order(cards)
    assert len(out) == 5


def test_intra_deck_cap_never_drops_likes_you(mem_engine):
    ly      = _mk_card(["g9"], ["star"], composite=1.0, likes_you=True)
    normals = [_mk_card([f"g{i}"], ["star"], composite=10.0 - i) for i in range(6)]
    with _flags(thompson=False, diversity=True):
        out = _order([ly] + normals)
    assert out[0] is ly, "likes_you card pinned top and never dropped"
    assert len(out) == 5


# ---------------------------------------------------------------------------
# database.py helpers — query shape
# ---------------------------------------------------------------------------

def test_load_trade_decision_shape_counts(mem_engine):
    with mem_engine.begin() as conn:
        _insert_decision(conn, ME, ["a"], ["b"], "like")
        _insert_decision(conn, ME, ["c"], ["d"], "like")
        _insert_decision(conn, ME, ["e"], ["f"], "pass")
        _insert_decision(conn, ME, ["a", "b"], ["c"], "pass")
        _insert_decision(conn, ME, ["x"], ["y"], "like", league_id="other")  # wrong league
        _insert_decision(conn, OPP, ["x"], ["y"], "like")                    # wrong user
    counts = load_trade_decision_shape_counts(ME, LEAGUE)
    assert counts == {"1x1": (2, 1), "2x1": (0, 1)}


def test_load_trade_decision_shape_counts_since_days(mem_engine):
    with mem_engine.begin() as conn:
        _insert_decision(conn, ME, ["a"], ["b"], "like", age_days=1)
        _insert_decision(conn, ME, ["c"], ["d"], "pass", age_days=40)
    assert load_trade_decision_shape_counts(ME, LEAGUE, since_days=30) == {"1x1": (1, 0)}
    assert load_trade_decision_shape_counts(ME, LEAGUE) == {"1x1": (1, 1)}


def test_load_recent_impression_target_user_counts(mem_engine):
    with mem_engine.begin() as conn:
        _insert_impression(conn, "u1", ["star", "x"])
        _insert_impression(conn, "u2", ["star"])
        _insert_impression(conn, "u2", ["star"])          # same user — still 1 distinct
        _insert_impression(conn, ME,   ["star"])          # excluded user
        _insert_impression(conn, "u3", ["star"], age_days=30)   # outside window
        _insert_impression(conn, "u4", ["star"], league_id="other")  # wrong league
    counts = load_recent_impression_target_user_counts(LEAGUE, exclude_user_id=ME, days=7)
    assert counts == {"star": 2, "x": 1}


# ---------------------------------------------------------------------------
# Integration — _run_trade_job orders BEFORE logging impressions
# ---------------------------------------------------------------------------

@pytest.fixture()
def job_harness(mem_engine):
    """Slim copy of test_trade_match_flow's harness: session + job registered
    in server module state, DB-independent side effects patched, likes-you +
    both ordering flags forced on."""
    pool = [Player(id=pid, name=pid.upper(), position="RB", team="AAA", age=25)
            for pid in ("g1", "g2", "r1", "r2")]
    service   = RankingService(players=list(pool))
    trade_svc = TradeService(players={p.id: p for p in pool})
    league = League(
        league_id=LEAGUE, name="Ord League", platform="sleeper",
        members=[
            LeagueMember(user_id=ME,  username="me",  roster=["g1", "g2"], elo_ratings={}),
            LeagueMember(user_id=OPP, username="opp", roster=["r1", "r2"], elo_ratings={}),
        ],
    )
    trade_svc.add_league(league)

    token  = "test-token-ord"
    job_id = "job-ord"
    sess = {
        "user_id":       ME,
        "league":        league,
        "user_roster":   ["g1", "g2"],
        "players":       pool,
        "services":      {"1qb_ppr": service},
        "trade_svcs":    {"1qb_ppr": trade_svc},
        "service":       service,
        "trade_svc":     trade_svc,
        "active_format": "1qb_ppr",
        "last_active":   0.0,
    }
    job = {
        "job_id": job_id, "key": (ME, LEAGUE, "1qb_ppr"), "status": "running",
        "started_at": time.monotonic(), "finished_at": None,
        "opponents_done": 0, "opponents_total": 1, "cards": [],
        "error": None, "fairness_threshold": 0.75,
        "outlook_value": None, "is_pinned": False,
    }

    with patch.object(server, "load_member_rankings", MagicMock(return_value={})), \
         patch.object(server, "load_league_preference", MagicMock(return_value=None)), \
         patch.object(server, "_likes_you_enabled", lambda: True), \
         patch.object(server, "_thompson_deck_enabled", lambda: True), \
         patch.object(server, "_deck_diversity_enabled", lambda: True):
        with server._sessions_lock:
            server._sessions[token] = sess
        with server._trade_jobs_lock:
            server._trade_jobs[job_id] = job
        try:
            yield job_id, token, job
        finally:
            with server._sessions_lock:
                server._sessions.pop(token, None)
            with server._trade_jobs_lock:
                server._trade_jobs.pop(job_id, None)
                server._trade_jobs_by_key.pop((ME, LEAGUE, "1qb_ppr"), None)


def test_run_trade_job_impressions_match_served_order(mem_engine, job_harness):
    """With both ordering flags on, the job completes and trade_impressions
    positions reflect the FINAL served order (ordering ran before logging),
    with the likes-you card still at position 0."""
    job_id, token, job = job_harness
    with mem_engine.begin() as conn:
        _insert_decision(conn, OPP, ["r1"], ["g1"], "like")

    server._run_trade_job(job_id, token, LEAGUE, 0.75, [])

    assert job["status"] == "complete", job.get("error")
    cards = job["cards"]
    assert len(cards) >= 1
    assert cards[0]["likes_you"] is True

    with mem_engine.connect() as conn:
        rows = conn.execute(
            select(trade_impressions_table)
            .where(trade_impressions_table.c.user_id == ME)
            .order_by(trade_impressions_table.c.position_in_deck)
        ).fetchall()

    assert len(rows) == len(cards)
    for pos, (row, card) in enumerate(zip(rows, cards)):
        assert row.position_in_deck == pos
        assert json.loads(row.give_player_ids) == [p["id"] for p in card["give"]]
        assert json.loads(row.receive_player_ids) == [p["id"] for p in card["receive"]]
