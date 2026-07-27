"""F7 (flag deck.exploration) — exploration slots & archetype audition.

docs/plans/tiktok-discovery/prds/F7-exploration-slots.md. Contract under
test:

  - Decks of ≥ exploration_min_deck cards get exactly ONE wildcard at the
    fixed slot position (exploration_slot_position, 1-indexed, clamped
    4–6); smaller decks get none; the draw is deterministic per job.
  - The wildcard comes from gate-passing candidates OUTSIDE the served
    deck: bottom prefMatch tercile (F5 taste helpers) → low-data F2 arms →
    uniform, plus auditioning-archetype candidates; provenance is logged.
  - Auditioning (test-pool) archetypes serve ONLY via the wildcard slot;
    graduation/retirement transitions follow the lazy state machine
    (n ≥ audition_min_views, like-rate vs 0.5× global base rate, 30d
    retirement then re-audition).
  - Wildcard impressions carry propensity = exploration_rate × 1/|pool|
    (replacing the Thompson multiplier) + wildcard provenance in
    features_json.
  - F3 fatigue applies to a wildcard normally once it has been seen, and
    active decline suppressions still bind on the draw pool.
  - Flag OFF ⇒ ordinary cards' payloads and impression rows are
    byte-identical (no wildcard keys anywhere).

Same isolation pattern as test_deck_fatigue.py: in-memory SQLite patched
into backend.database, flag helpers patched directly.
"""

import json
import uuid
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text

import backend.database as db_module
import backend.server as server
from backend.database import (
    load_archetype_auditions,
    metadata,
    save_deck_suppression,
    upsert_archetype_audition,
)
from backend.trade_service import TradeCard


LEAGUE = "league_f7"
ME     = "user_me"
OPP    = "user_opp"
OPP2   = "user_opp2"

SEED = {"star": 1800.0, "mid": 1500.0, "scrub": 1250.0}


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def mem_engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db_module, "engine", eng):
        yield eng


def _mk_card(give, recv, composite=5.0, likes_you=False, lane=None,
             target=OPP):
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
        lane               = lane,
    )


def _clean_deck(n, start=0):
    """n distinct archetype-less cards (statuses treat them as general)."""
    return [_mk_card([f"g{start + i}"], [f"r{start + i}"], composite=9.0 - i * 0.1)
            for i in range(n)]


def _iso_ago(days=0.0):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _insert_impression(conn, iid, *, archetype=None, shape="1x1",
                       trade_hash=None, job_id="job-x", age_days=0.0,
                       user_id=ME, league_id=LEAGUE):
    conn.execute(text(
        "INSERT INTO deck_impressions "
        "(impression_id, user_id, league_id, deck_job_id, card_index, "
        " trade_hash, propensity, archetype, shape_bucket, served_at) "
        "VALUES (:iid, :uid, :lid, :job, 0, :thash, 1.0, :arch, :shape, "
        "        :served)"
    ), {"iid": iid, "uid": user_id, "lid": league_id, "job": job_id,
        "thash": trade_hash, "arch": archetype, "shape": shape,
        "served": _iso_ago(age_days)})


def _insert_outcome(conn, iid, action, age_days=0.0):
    conn.execute(text(
        "INSERT INTO deck_outcomes (impression_id, action, acted_at) "
        "VALUES (:iid, :act, :at)"
    ), {"iid": iid, "act": action, "at": _iso_ago(age_days)})


def _seed_engagement(conn, archetype, viewed=0, likes=0, age_days=0.0,
                     shape="1x1"):
    """`viewed` viewed impressions of an archetype, `likes` of which are
    also liked (likes ≤ viewed — the writer counts liked-and-viewed)."""
    for i in range(viewed):
        iid = uuid.uuid4().hex
        _insert_impression(conn, iid, archetype=archetype, shape=shape,
                           age_days=age_days)
        _insert_outcome(conn, iid, "viewed", age_days=age_days)
        if i < likes:
            _insert_outcome(conn, iid, "like", age_days=age_days)


def _explore(cards, pool, *, taste=False, v2=False, fatigue=False,
             players=None, seed=None, job_id="job-1"):
    """Run _apply_exploration_slot with ambient flags pinned explicitly —
    config/features.json state must never leak into these tests."""
    with ExitStack() as stack:
        stack.enter_context(patch.object(
            server, "_deck_taste_enabled", lambda: taste))
        stack.enter_context(patch.object(
            server, "_deck_thompson_v2_enabled", lambda: v2))
        stack.enter_context(patch.object(
            server, "_deck_fatigue_enabled", lambda: fatigue))
        return server._apply_exploration_slot(
            list(cards), list(pool), user_id=ME, league_id=LEAGUE,
            job_id=job_id, players_dict=players or {}, seed_map=seed or SEED)


# ---------------------------------------------------------------------------
# Pool split — top-N per opponent stays the deck, overflow is the pool
# ---------------------------------------------------------------------------

def test_split_keeps_top_n_per_opponent_in_order():
    cards = []
    for i in range(7):                       # 7 for OPP (composite desc)
        cards.append(_mk_card([f"a{i}"], [f"b{i}"], composite=9.0 - i))
    for i in range(6):                       # 6 for OPP2
        cards.append(_mk_card([f"c{i}"], [f"d{i}"], composite=8.5 - i,
                              target=OPP2))
    cards.sort(key=lambda c: c.composite_score, reverse=True)

    deck, pool = server._split_exploration_pool(cards, 5)

    assert len(deck) == 10 and len(pool) == 3
    per_opp = {}
    for c in deck:
        per_opp[c.target_user_id] = per_opp.get(c.target_user_id, 0) + 1
    assert per_opp == {OPP: 5, OPP2: 5}
    # Both sides keep the incoming (composite) order.
    assert [c.trade_id for c in deck] == [
        c.trade_id for c in cards if c in deck]
    assert [c.trade_id for c in pool] == [
        c.trade_id for c in cards if c in pool]
    # Pool = each opponent's overflow beyond its top 5.
    for c in pool:
        better = [x for x in cards
                  if x.target_user_id == c.target_user_id
                  and x.composite_score > c.composite_score]
        assert len(better) >= 5


# ---------------------------------------------------------------------------
# Wildcard slot — exactly one, fixed position, deck-size gate, determinism
# ---------------------------------------------------------------------------

def test_deck_of_8_gets_exactly_one_wildcard_in_slot(mem_engine):
    deck = _clean_deck(8)
    pool = [_mk_card([f"p{i}"], [f"q{i}"], composite=3.0) for i in range(3)]

    out, wc, info = _explore(deck, pool)

    assert wc is not None
    assert len(out) == 9
    wilds = [c for c in out if getattr(c, "wildcard", False)]
    assert wilds == [wc]
    # Default slot 5 (1-indexed) ⇒ index 4; the displaced card shifted down.
    assert out[4] is wc
    assert out[:4] == deck[:4] and out[5:] == deck[4:]
    assert wc.wildcard_pool_size == 3
    assert wc.wildcard_provenance == "uniform"     # no taste, no v2 arms
    assert info["propensity"] == pytest.approx(0.125 / 3)

    # Deterministic per job: same job id redraws the same card.
    deck2 = _clean_deck(8)
    _out2, wc2, _ = _explore(deck2, pool)
    assert wc2 is wc


def test_deck_below_min_gets_no_wildcard(mem_engine):
    deck = _clean_deck(7)
    pool = [_mk_card(["p1"], ["q1"])]
    out, wc, info = _explore(deck, pool)
    assert wc is None
    assert out == deck
    assert "propensity" not in info


def test_empty_pool_gets_no_wildcard(mem_engine):
    deck = _clean_deck(10)
    out, wc, _info = _explore(deck, [])
    assert wc is None and out == deck


def test_pool_card_duplicated_in_deck_is_not_drawn(mem_engine):
    deck = _clean_deck(8)
    dupe = _mk_card(list(deck[0].give_player_ids),
                    list(deck[0].receive_player_ids))
    out, wc, _info = _explore(deck, [dupe])
    assert wc is None and out == deck


# ---------------------------------------------------------------------------
# Draw pool provenance — bottom taste tercile, then low-data arms
# ---------------------------------------------------------------------------

def test_wildcard_from_bottom_pref_match_tercile(mem_engine):
    players = {}
    for i in range(3):
        players[f"rb{i}"] = SimpleNamespace(id=f"rb{i}", position="RB",
                                            age=25, team="T", name=f"rb{i}")
        players[f"wr{i}"] = SimpleNamespace(id=f"wr{i}", position="WR",
                                            age=25, team="T", name=f"wr{i}")
    # The user's taste vector loves acquiring RBs.
    db_module.replace_user_taste_rows(
        ME, {"recvpos:RB": (5.0, 5.0, _iso_ago(0.0))}, [])

    deck = _clean_deck(8)
    pool = ([_mk_card([f"g{i + 50}"], [f"rb{i}"]) for i in range(3)]      # on-taste
            + [_mk_card([f"g{i + 60}"], [f"wr{i}"]) for i in range(3)])   # off-taste
    out, wc, info = _explore(deck, pool, taste=True, players=players)

    assert wc is not None
    assert wc.receive_player_ids[0].startswith("wr")   # bottom tercile only
    assert wc.wildcard_provenance == "taste_tercile"
    assert info["provenance"] == "taste_tercile"
    # Bottom tercile of 6 = 2 candidates ⇒ propensity = rate × 1/2.
    assert info["pool_size"] == 2
    assert info["propensity"] == pytest.approx(0.125 / 2)
    assert len(out) == 9 and out[4] is wc


def test_low_data_arm_fallback_when_taste_cold(mem_engine):
    # "value" is an established lane (general pool). Its 1x1 arm has 5
    # viewed-gated like observations for ME (n_raw counts like/pass events,
    # not bare views — _THOMPSON_V2_WARM_MIN_OBS = 5); its 2x1 arm has none.
    with mem_engine.begin() as conn:
        _seed_engagement(conn, "value", viewed=5, likes=5, shape="1x1")

    deck = _clean_deck(8)
    warm = _mk_card(["p1"], ["q1"], lane="value")               # 1x1, warm arm
    cold = _mk_card(["p2", "p3"], ["q2"], lane="value")         # 2x1, no data
    out, wc, info = _explore(deck, [warm, cold], v2=True)

    assert wc is cold
    assert wc.wildcard_provenance == "low_data_arm"
    assert info["pool_size"] == 1
    assert info["propensity"] == pytest.approx(0.125 / 1)
    assert len(out) == 9 and out[4] is wc


# ---------------------------------------------------------------------------
# Archetype audition — test pool serves only via the wildcard slot
# ---------------------------------------------------------------------------

def test_auditioning_archetype_appears_only_via_wildcard(mem_engine):
    deck = _clean_deck(8) + [_mk_card(["nx"], ["ny"], composite=6.0,
                                      lane="newshape")]
    pool = [_mk_card(["nz"], ["nw"], lane="newshape")]

    out, wc, _info = _explore(deck, pool)

    assert wc is not None
    assert wc.wildcard_provenance == "audition"
    assert server._card_archetype(wc) == "newshape"
    # No newshape card serves outside the wildcard slot.
    for c in out:
        if c is not wc:
            assert server._card_archetype(c) != "newshape"
    assert len(out) == 9 and out[4] is wc
    # The lazy pass created the audition row.
    row = load_archetype_auditions()["newshape"]
    assert row["status"] == "test"


def test_established_lanes_enter_general_not_test(mem_engine):
    statuses = server._audition_statuses({"window", "value"})
    assert statuses == {"window": "general", "value": "general"}
    rows = load_archetype_auditions()
    assert rows["window"]["status"] == "general"
    assert rows["value"]["status"] == "general"


def test_unknown_archetype_with_enough_alltime_views_is_general(mem_engine):
    with mem_engine.begin() as conn:
        _seed_engagement(conn, "oldshape", viewed=30, likes=10)
    assert server._audition_statuses({"oldshape"}) == {"oldshape": "general"}


# ---------------------------------------------------------------------------
# Audition transitions — graduation, retirement, re-entry
# ---------------------------------------------------------------------------

def test_graduation_at_min_views_and_healthy_like_rate(mem_engine):
    upsert_archetype_audition(
        "hotshape", status="test", viewed_impressions=0, likes=0,
        entered_at=_iso_ago(10.0), retired_at=None)
    with mem_engine.begin() as conn:
        _seed_engagement(conn, "hotshape", viewed=30, likes=20)

    with patch.object(server, "_thompson_prior_base_rate", lambda: 0.6):
        statuses = server._audition_statuses({"hotshape"})

    assert statuses == {"hotshape": "general"}   # 20/30 ≥ 0.5 × 0.6
    row = load_archetype_auditions()["hotshape"]
    assert row["status"] == "general"
    assert row["viewed_impressions"] == 30 and row["likes"] == 20
    assert row["retired_at"] is None


def test_retirement_then_reentry_after_window(mem_engine):
    upsert_archetype_audition(
        "coldshape", status="test", viewed_impressions=0, likes=0,
        entered_at=_iso_ago(10.0), retired_at=None)
    with mem_engine.begin() as conn:
        _seed_engagement(conn, "coldshape", viewed=30, likes=1)

    with patch.object(server, "_thompson_prior_base_rate", lambda: 0.6):
        statuses = server._audition_statuses({"coldshape"})

    assert statuses == {"coldshape": "retired"}   # 1/30 < 0.5 × 0.6
    row = load_archetype_auditions()["coldshape"]
    assert row["status"] == "retired" and row["retired_at"] is not None

    # Inside the window it stays retired.
    assert server._audition_statuses({"coldshape"}) == {"coldshape": "retired"}

    # Past the 30d window it re-enters test with a fresh counting window.
    upsert_archetype_audition(
        "coldshape", status="retired", viewed_impressions=30, likes=1,
        entered_at=_iso_ago(45.0), retired_at=_iso_ago(31.0))
    assert server._audition_statuses({"coldshape"}) == {"coldshape": "test"}
    row = load_archetype_auditions()["coldshape"]
    assert row["status"] == "test"
    assert row["viewed_impressions"] == 0 and row["likes"] == 0


def test_sub_min_views_keeps_testing_without_verdict(mem_engine):
    upsert_archetype_audition(
        "slowshape", status="test", viewed_impressions=0, likes=0,
        entered_at=_iso_ago(10.0), retired_at=None)
    with mem_engine.begin() as conn:
        _seed_engagement(conn, "slowshape", viewed=10, likes=0)
    assert server._audition_statuses({"slowshape"}) == {"slowshape": "test"}
    row = load_archetype_auditions()["slowshape"]
    assert row["viewed_impressions"] == 10   # counts refreshed, no verdict


def test_retired_archetype_excluded_from_wildcard_draw(mem_engine):
    upsert_archetype_audition(
        "deadshape", status="retired", viewed_impressions=30, likes=0,
        entered_at=_iso_ago(10.0), retired_at=_iso_ago(1.0))
    deck = _clean_deck(8)
    pool = [_mk_card(["p1"], ["q1"], lane="deadshape")]
    out, wc, _info = _explore(deck, pool)
    assert wc is None and out == deck


# ---------------------------------------------------------------------------
# Propensity + provenance on the F1 impression spine
# ---------------------------------------------------------------------------

def test_wildcard_impression_carries_exploration_propensity(mem_engine):
    deck = _clean_deck(8)
    pool = [_mk_card([f"p{i}"], [f"q{i}"]) for i in range(4)]
    out, wc, info = _explore(deck, pool)
    assert wc is not None
    expected_prop = 0.125 / 4
    assert info["propensity"] == pytest.approx(expected_prop)

    # The worker stamps the exploration propensity into the F1 capture —
    # it REPLACES the Thompson multiplier for the wildcard card.
    capture = {"propensity": {id(wc): info["propensity"]}}
    with ExitStack() as stack:
        stack.enter_context(patch.object(
            server, "_deck_taste_enabled", lambda: False))
        stack.enter_context(patch.object(
            server, "_deck_fatigue_enabled", lambda: False))
        server._log_deck_signal_impressions(
            user_id=ME, league_id=LEAGUE, job_id="job-1", cards=out,
            players_dict={}, capture=capture, scoring_format="1qb_ppr")

    with mem_engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT card_index, propensity, features_json "
            "FROM deck_impressions ORDER BY card_index")).fetchall()
    assert len(rows) == 9
    wc_row = rows[4]
    assert wc_row.propensity == pytest.approx(expected_prop)
    feats = json.loads(wc_row.features_json)
    assert feats["wildcard"] is True
    assert feats["wildcard_pool_size"] == 4
    assert feats["wildcard_provenance"] == "uniform"
    # Every other row is byte-identical to pre-F7: no wildcard keys, and
    # the no-ordering default propensity of 1.0.
    for r in rows:
        if r.card_index == 4:
            continue
        assert r.propensity == 1.0
        other = json.loads(r.features_json)
        assert "wildcard" not in other
        assert "wildcard_pool_size" not in other
        assert "wildcard_provenance" not in other


# ---------------------------------------------------------------------------
# F3 interplay — fatigue after the wildcard is seen; suppressions bind
# ---------------------------------------------------------------------------

def test_fatigue_applies_to_wildcard_after_it_is_viewed(mem_engine):
    wc = _mk_card(["star"], ["mid"])
    wc.wildcard = True
    thash = server._deck_trade_hash(["star"], ["mid"], OPP)
    with mem_engine.begin() as conn:
        for _ in range(3):
            iid = uuid.uuid4().hex
            _insert_impression(conn, iid, trade_hash=thash)
            _insert_outcome(conn, iid, "viewed")
        # centerpiece key rides a separate column — cover it too
        conn.execute(text(
            "UPDATE deck_impressions SET centerpiece_id = 'star'"))
    mults = server._deck_fatigue_multipliers(
        [wc], user_id=ME, league_id=LEAGUE, seed_map=SEED)
    assert mults[id(wc)] < 1.0


def test_active_decline_suppression_binds_on_the_draw_pool(mem_engine):
    give, recv = ["star"], ["mid"]
    now = datetime.now(timezone.utc)
    save_deck_suppression(
        user_id        = ME,
        league_id      = LEAGUE,
        centerpiece_id = server._fatigue_centerpiece(give, recv, SEED),
        shape_bucket   = "1x1",
        package_value  = server._fatigue_package_value(give, recv, SEED),
        declined_at    = now.isoformat(),
        expires_at     = (now + timedelta(days=30)).isoformat(),
    )
    deck = _clean_deck(8)
    pool = [_mk_card(give, recv)]
    out, wc, _info = _explore(deck, pool, fatigue=True)
    assert wc is None and out == deck
    # With the fatigue flag off the same pool card is eligible (the filter
    # itself is F3-gated; F3 off ⇒ no suppression reads).
    out2, wc2, _ = _explore(_clean_deck(8), [_mk_card(give, recv)])
    assert wc2 is not None


# ---------------------------------------------------------------------------
# Flag OFF — payloads byte-identical
# ---------------------------------------------------------------------------

def test_ordinary_card_payload_has_no_wildcard_key():
    card = _mk_card(["g1"], ["r1"])
    out = server.trade_card_to_dict(card, {})
    assert "wildcard" not in out


def test_wildcard_card_payload_is_additive():
    card = _mk_card(["g1"], ["r1"])
    card.wildcard = True
    base = {k for k in server.trade_card_to_dict(_mk_card(["g1"], ["r1"]), {})}
    out = server.trade_card_to_dict(card, {})
    assert out["wildcard"] is True
    assert set(out.keys()) - base == {"wildcard"}
