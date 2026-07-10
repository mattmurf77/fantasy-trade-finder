"""Tier 2 work item 2.3 + impressions pipeline (2.4 data side).

Covers three pieces of the match flow:

  (a) Fuzzy mirror matching (`database.check_for_match` with fuzzy=True):
      a counterparty like that differs from the user's card by one
      LOW-value bench player matches at tau=0.8; the same pair does NOT
      match under exact mode (fuzzy off / default); a similar-but-lopsided
      pair (the differing asset is a star) is rejected by the value guard.

  (b) Likes-you queue (`server._inject_likes_you_cards` + `_run_trade_job`):
      a league-mate's prior like causes the user's next generated deck to
      contain the mirrored card flagged likes_you=True at position 0;
      pre-existing equivalent cards are boosted instead of duplicated;
      injections are capped at 3.

  (c) Impressions pipeline (`database.log_trade_impressions` + the
      `_run_trade_job` call site): generating a deck writes N
      trade_impressions rows with correct position_in_deck values.

All tests run against an isolated in-memory SQLite engine patched into
backend.database (same pattern as test_db_hygiene.py) — dialect-safe, since
the schema goes through metadata.create_all().
"""

import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select, text

import backend.database as db_module
import backend.server as server
from backend.database import (
    check_for_match,
    log_trade_impressions,
    load_recent_league_likes,
    metadata,
    trade_impressions_table,
)
from backend.ranking_service import Player, RankingService
from backend.trade_service import League, LeagueMember, TradeCard, TradeService


LEAGUE = "league_t2"
ME     = "user_me"
OPP    = "user_opp"


# ---------------------------------------------------------------------------
# Fixture: isolated in-memory SQLite engine
# ---------------------------------------------------------------------------

@pytest.fixture()
def mem_engine():
    """Fresh in-memory SQLite engine with the full schema, patched in as the
    module-level engine so all database.py functions use it."""
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db_module, "engine", eng):
        yield eng


def _insert_like(conn, user_id, league_id, give_ids, recv_ids, age_days=1):
    created = (datetime.now(timezone.utc).replace(tzinfo=None)
               - timedelta(days=age_days)).isoformat()
    conn.execute(text(
        "INSERT INTO trade_decisions "
        "(user_id, league_id, give_player_ids, receive_player_ids, decision, created_at) "
        "VALUES (:uid, :lid, :give, :recv, 'like', :created)"
    ), {
        "uid": user_id, "lid": league_id,
        "give": json.dumps(give_ids), "recv": json.dumps(recv_ids),
        "created": created,
    })


def _insert_player(conn, pid, search_rank):
    conn.execute(text(
        "INSERT INTO players (player_id, full_name, position, search_rank) "
        "VALUES (:pid, :name, 'RB', :rank)"
    ), {"pid": pid, "name": pid.upper(), "rank": search_rank})


# ---------------------------------------------------------------------------
# (a) Fuzzy mirror matching
# ---------------------------------------------------------------------------
# The counterparty (OPP) liked: give = [p1..p4, bench], receive = [q1..q4].
# The user's card: give = [q1..q4], receive = [p1..p4] — the mirror minus
# one bench player. jaccard(their_give, my_receive) = 4/5 = 0.8;
# jaccard(their_receive, my_give) = 1.0.

CORE_GIVE = ["p1", "p2", "p3", "p4"]
CORE_RECV = ["q1", "q2", "q3", "q4"]


def _seed_fuzzy_like(eng, extra_player, extra_rank):
    with eng.begin() as conn:
        _insert_player(conn, extra_player, extra_rank)
        _insert_like(conn, OPP, LEAGUE,
                     give_ids=CORE_GIVE + [extra_player],
                     recv_ids=CORE_RECV)


def test_exact_mode_does_not_match_near_mirror(mem_engine):
    """Flag off (fuzzy=False, the default): a one-bench-player difference is
    NOT a mirror — pre-Tier-2 behavior unchanged."""
    _seed_fuzzy_like(mem_engine, "bench1", extra_rank=300)
    assert check_for_match(
        current_user_id=ME, league_id=LEAGUE, target_user_id=OPP,
        give_player_ids=CORE_RECV, receive_player_ids=CORE_GIVE,
    ) is False


def test_fuzzy_matches_near_mirror_with_low_value_diff(mem_engine):
    """Fuzzy on: same pair matches at tau=0.8 because the only differing
    asset is a low-value bench player (search_rank 300 >= guard 120)."""
    _seed_fuzzy_like(mem_engine, "bench1", extra_rank=300)
    assert check_for_match(
        current_user_id=ME, league_id=LEAGUE, target_user_id=OPP,
        give_player_ids=CORE_RECV, receive_player_ids=CORE_GIVE,
        fuzzy=True, fuzzy_tau=0.8,
    ) is True


def test_fuzzy_value_guard_rejects_lopsided_pair(mem_engine):
    """Fuzzy on: a similar-but-lopsided pair (the differing asset is a star,
    search_rank 5) is rejected by the value guard despite passing jaccard."""
    _seed_fuzzy_like(mem_engine, "star1", extra_rank=5)
    assert check_for_match(
        current_user_id=ME, league_id=LEAGUE, target_user_id=OPP,
        give_player_ids=CORE_RECV, receive_player_ids=CORE_GIVE,
        fuzzy=True, fuzzy_tau=0.8,
    ) is False


def test_fuzzy_guard_treats_unknown_player_as_high_value(mem_engine):
    """A differing asset with no players row (no search_rank) fails the
    guard — unranked hype prospects can't sneak through a fuzzy match."""
    with mem_engine.begin() as conn:
        _insert_like(conn, OPP, LEAGUE,
                     give_ids=CORE_GIVE + ["ghost1"], recv_ids=CORE_RECV)
    assert check_for_match(
        current_user_id=ME, league_id=LEAGUE, target_user_id=OPP,
        give_player_ids=CORE_RECV, receive_player_ids=CORE_GIVE,
        fuzzy=True, fuzzy_tau=0.8,
    ) is False


def test_fuzzy_below_tau_does_not_match(mem_engine):
    """Jaccard below tau (3 shared of 5 → 0.6) never matches, even when all
    differing assets are low value."""
    with mem_engine.begin() as conn:
        for pid in ("bench1", "bench2"):
            _insert_player(conn, pid, 300)
        _insert_like(conn, OPP, LEAGUE,
                     give_ids=CORE_GIVE[:3] + ["bench1", "bench2"],
                     recv_ids=CORE_RECV)
    assert check_for_match(
        current_user_id=ME, league_id=LEAGUE, target_user_id=OPP,
        give_player_ids=CORE_RECV, receive_player_ids=CORE_GIVE[:3] + ["p4"],
        fuzzy=True, fuzzy_tau=0.8,
    ) is False


def test_exact_mirror_still_matches_in_both_modes(mem_engine):
    """An exact set-equality mirror matches with fuzzy off AND on."""
    with mem_engine.begin() as conn:
        _insert_like(conn, OPP, LEAGUE, give_ids=CORE_GIVE, recv_ids=CORE_RECV)
    for fuzzy in (False, True):
        assert check_for_match(
            current_user_id=ME, league_id=LEAGUE, target_user_id=OPP,
            give_player_ids=CORE_RECV, receive_player_ids=CORE_GIVE,
            fuzzy=fuzzy,
        ) is True, f"exact mirror must match (fuzzy={fuzzy})"


# ---------------------------------------------------------------------------
# (b) Likes-you queue
# ---------------------------------------------------------------------------

def _mk_card(give, recv, target=OPP, composite=5.0):
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
    )


def _mk_trade_service(player_ids):
    players = {pid: Player(id=pid, name=pid.upper(), position="RB", team="AAA", age=25)
               for pid in player_ids}
    return TradeService(players=players)


def _mk_league(my_roster, opp_roster):
    return League(
        league_id=LEAGUE, name="T2 League", platform="sleeper",
        members=[
            LeagueMember(user_id=ME,  username="me",  roster=list(my_roster),  elo_ratings={}),
            LeagueMember(user_id=OPP, username="opp", roster=list(opp_roster), elo_ratings={}),
        ],
    )


def test_inject_likes_you_synthesizes_mirrored_card_at_top(mem_engine):
    """OPP liked give=[r1] / receive=[g1]. The user's deck (one organic card)
    gains a synthesized mirror — give=[g1], receive=[r1], target=OPP,
    likes_you=True — sorted to position 0 above the organic card."""
    with mem_engine.begin() as conn:
        _insert_like(conn, OPP, LEAGUE, give_ids=["r1"], recv_ids=["g1"])

    svc = _mk_trade_service(["g1", "g2", "r1", "r2"])
    organic = _mk_card(give=["g2"], recv=["r2"], composite=7.5)
    deck = server._inject_likes_you_cards(
        cards=[organic], trade_service=svc, user_id=ME, league_id=LEAGUE,
        league=_mk_league(my_roster=["g1", "g2"], opp_roster=["r1", "r2"]),
        user_roster=["g1", "g2"], seed_map={},
    )

    assert len(deck) == 2
    top = deck[0]
    assert top.likes_you is True
    assert top.give_player_ids == ["g1"]
    assert top.receive_player_ids == ["r1"]
    assert top.target_user_id == OPP
    assert top.composite_score > organic.composite_score
    # Synthesized card must be swipeable — registered by trade_id.
    assert svc._trade_cards[top.trade_id] is top


def test_inject_likes_you_boosts_existing_equivalent_card(mem_engine):
    """If the generated deck already contains the mirrored card (same sets,
    same opponent), it is flagged + boosted to the top — not duplicated."""
    with mem_engine.begin() as conn:
        _insert_like(conn, OPP, LEAGUE, give_ids=["r1"], recv_ids=["g1"])

    svc = _mk_trade_service(["g1", "g2", "r1", "r2"])
    equivalent = _mk_card(give=["g1"], recv=["r1"], composite=2.0)
    better     = _mk_card(give=["g2"], recv=["r2"], composite=9.0)
    deck = server._inject_likes_you_cards(
        cards=[better, equivalent], trade_service=svc, user_id=ME, league_id=LEAGUE,
        league=_mk_league(my_roster=["g1", "g2"], opp_roster=["r1", "r2"]),
        user_roster=["g1", "g2"], seed_map={},
    )

    assert len(deck) == 2, "must boost in place, not duplicate"
    assert deck[0] is equivalent
    assert equivalent.likes_you is True
    assert equivalent.composite_score == pytest.approx(10.0)  # max(9.0) + 1.0


def test_inject_likes_you_skips_stale_and_caps_at_three(mem_engine):
    """Likes whose packages are no longer on the right rosters are skipped;
    at most 3 likes-you cards are injected per deck."""
    with mem_engine.begin() as conn:
        # Stale: r9 is not on OPP's roster any more.
        _insert_like(conn, OPP, LEAGUE, give_ids=["r9"], recv_ids=["g1"])
        # Stale: g9 is not on the user's roster.
        _insert_like(conn, OPP, LEAGUE, give_ids=["r1"], recv_ids=["g9"])
        # Five valid likes — only 3 may land.
        for i in range(1, 6):
            _insert_like(conn, OPP, LEAGUE, give_ids=[f"r{i}"], recv_ids=[f"g{i}"])

    ids = [f"g{i}" for i in range(1, 6)] + [f"r{i}" for i in range(1, 6)]
    svc = _mk_trade_service(ids)
    deck = server._inject_likes_you_cards(
        cards=[], trade_service=svc, user_id=ME, league_id=LEAGUE,
        league=_mk_league(my_roster=[f"g{i}" for i in range(1, 6)],
                          opp_roster=[f"r{i}" for i in range(1, 6)]),
        user_roster=[f"g{i}" for i in range(1, 6)], seed_map={},
    )

    assert len(deck) == 3
    assert all(c.likes_you for c in deck)
    # None of the stale packages made it through.
    for c in deck:
        assert "g9" not in c.give_player_ids
        assert "r9" not in c.receive_player_ids


def test_inject_likes_you_skips_untouchable_give(mem_engine):
    """Feedback #95 — a leaguemate's like whose mirror would send one of the
    user's untouchables away is not injected; other likes still are."""
    with mem_engine.begin() as conn:
        # OPP wants g1 (the user's untouchable) — must be filtered.
        _insert_like(conn, OPP, LEAGUE, give_ids=["r1"], recv_ids=["g1"])
        # OPP wants g2 — fine.
        _insert_like(conn, OPP, LEAGUE, give_ids=["r2"], recv_ids=["g2"])

    svc = _mk_trade_service(["g1", "g2", "r1", "r2"])
    deck = server._inject_likes_you_cards(
        cards=[], trade_service=svc, user_id=ME, league_id=LEAGUE,
        league=_mk_league(my_roster=["g1", "g2"], opp_roster=["r1", "r2"]),
        user_roster=["g1", "g2"], seed_map={},
        untouchable_ids={"g1"},
    )

    assert len(deck) == 1
    assert deck[0].give_player_ids == ["g2"]


# ---------------------------------------------------------------------------
# (b+c) Full job flow: _run_trade_job — likes-you at position 0 + impressions
# ---------------------------------------------------------------------------

@pytest.fixture()
def job_harness(mem_engine):
    """Session + job registered in server's module state, side-effects
    patched. Opponents have no elo_ratings, so organic generation yields no
    cards — every card in the final deck comes from the likes-you queue,
    making position assertions deterministic."""
    pool = [Player(id=pid, name=pid.upper(), position="RB", team="AAA", age=25)
            for pid in ("g1", "g2", "r1", "r2")]
    service   = RankingService(players=list(pool))
    trade_svc = TradeService(players={p.id: p for p in pool})
    league    = _mk_league(my_roster=["g1", "g2"], opp_roster=["r1", "r2"])
    trade_svc.add_league(league)

    token  = "test-token-t2"
    job_id = "job-t2"
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
         patch.object(server, "_likes_you_enabled", lambda: True):
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


def test_run_trade_job_serves_likes_you_card_at_position_0(mem_engine, job_harness):
    """A league-mate's prior like → the user's next generated deck contains
    the mirrored card flagged likes_you=True at position 0."""
    job_id, token, job = job_harness
    with mem_engine.begin() as conn:
        _insert_like(conn, OPP, LEAGUE, give_ids=["r1"], recv_ids=["g1"])

    server._run_trade_job(job_id, token, LEAGUE, 0.75, [])

    assert job["status"] == "complete", job.get("error")
    cards = job["cards"]
    assert len(cards) >= 1
    top = cards[0]
    assert top["likes_you"] is True
    assert [p["id"] for p in top["give"]] == ["g1"]
    assert [p["id"] for p in top["receive"]] == ["r1"]
    assert top["target_username"] == "opp"


def test_run_trade_job_logs_impressions_with_positions(mem_engine, job_harness):
    """Completing a generation job writes one trade_impressions row per
    served card, position_in_deck matching the deck order."""
    job_id, token, job = job_harness
    with mem_engine.begin() as conn:
        _insert_like(conn, OPP, LEAGUE, give_ids=["r1"], recv_ids=["g1"])
        _insert_like(conn, OPP, LEAGUE, give_ids=["r2"], recv_ids=["g2"])

    server._run_trade_job(job_id, token, LEAGUE, 0.75, [])

    assert job["status"] == "complete", job.get("error")
    # The deck holds the two likes-you mirrors at the top, plus however many
    # organic cards generation produced (depends on the trade_engine.v2 flag —
    # the consensus fallback can yield cards for unranked opponents).
    n_served = len(job["cards"])
    assert n_served >= 2
    assert job["cards"][0].get("likes_you") is True
    assert job["cards"][1].get("likes_you") is True

    with mem_engine.connect() as conn:
        rows = conn.execute(
            select(trade_impressions_table)
            .order_by(trade_impressions_table.c.position_in_deck)
        ).fetchall()

    assert len(rows) == n_served
    for pos, (row, card) in enumerate(zip(rows, job["cards"])):
        assert row.position_in_deck == pos
        assert row.user_id == ME
        assert row.league_id == LEAGUE
        assert row.likes_you == (1 if card.get("likes_you") else 0)
        assert json.loads(row.give_player_ids) == [p["id"] for p in card["give"]]
        assert json.loads(row.receive_player_ids) == [p["id"] for p in card["receive"]]
        assert row.shown_at  # ISO timestamp present


# ---------------------------------------------------------------------------
# (c) log_trade_impressions — direct unit coverage
# ---------------------------------------------------------------------------

def test_log_trade_impressions_batches_rows_in_deck_order(mem_engine):
    cards = [
        _mk_card(give=["g1"], recv=["r1"], composite=9.0),
        _mk_card(give=["g2"], recv=["r2"], composite=5.0),
        _mk_card(give=["g1", "g2"], recv=["r1", "r2"], composite=1.0),
    ]
    cards[0].likes_you = True

    log_trade_impressions(ME, LEAGUE, cards)

    with mem_engine.connect() as conn:
        rows = conn.execute(
            select(trade_impressions_table)
            .order_by(trade_impressions_table.c.position_in_deck)
        ).fetchall()

    assert len(rows) == 3
    assert [r.position_in_deck for r in rows] == [0, 1, 2]
    assert [r.likes_you for r in rows] == [1, 0, 0]
    assert [r.composite_score for r in rows] == [9.0, 5.0, 1.0]
    assert rows[2].basis == "divergence"
    assert json.loads(rows[2].give_player_ids) == ["g1", "g2"]
    assert rows[0].target_user_id == OPP


def test_log_trade_impressions_never_raises(mem_engine):
    """Garbage input must be swallowed — impression logging can never break
    trade generation."""
    log_trade_impressions(ME, LEAGUE, [object()])   # no usable fields → no raise
    log_trade_impressions(ME, LEAGUE, [])           # empty deck → no-op


# ---------------------------------------------------------------------------
# load_recent_league_likes — query shape
# ---------------------------------------------------------------------------

def test_load_recent_league_likes_filters_self_old_and_passes(mem_engine):
    with mem_engine.begin() as conn:
        _insert_like(conn, OPP, LEAGUE, ["r1"], ["g1"], age_days=1)     # ✓
        _insert_like(conn, ME,  LEAGUE, ["x"],  ["y"],  age_days=1)     # self → excluded
        _insert_like(conn, OPP, LEAGUE, ["r2"], ["g2"], age_days=95)    # too old
        _insert_like(conn, OPP, "other_league", ["r3"], ["g3"], age_days=1)  # wrong league
        conn.execute(text(
            "INSERT INTO trade_decisions "
            "(user_id, league_id, give_player_ids, receive_player_ids, decision, created_at) "
            "VALUES (:u, :l, :g, :r, 'pass', :c)"
        ), {"u": OPP, "l": LEAGUE, "g": json.dumps(["r4"]),
            "r": json.dumps(["g4"]),
            "c": datetime.now(timezone.utc).replace(tzinfo=None).isoformat()})

    likes = load_recent_league_likes(LEAGUE, exclude_user_id=ME, days=90)
    assert len(likes) == 1
    assert likes[0]["user_id"] == OPP
    assert likes[0]["give_player_ids"] == ["r1"]
    assert likes[0]["receive_player_ids"] == ["g1"]
