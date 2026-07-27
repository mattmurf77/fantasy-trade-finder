"""F3 (flag deck.fatigue) — fatigue & durable suppression.

docs/plans/tiktok-discovery/prds/F3-fatigue-suppression.md. Two layers on top
of the untouched league-level saturation caps:

  1. Soft fatigue — multiplicative ≤1.0 discount on the ordering key from
     viewed deck_impressions (trade_hash + centerpiece keys, weaker archetype
     accrual), plus a strong session demotion for centerpieces passed 2+
     times in one deck job.
  2. Decline suppression — 30d near-duplicate removal (same centerpiece +
     shape + package value within ±10%), then exactly ONE low-exposure
     retest card, re-armed lazily if the retest is passed.

Contract under test: flag OFF ⇒ byte-identical ordering/payloads and no F3
reads; suppression floor keeps the pool ≥ _DECK_MIN_CARDS and logs; refresh
clears pass-fatigue but never decline suppressions; league caps still apply
with the flag on.

Same isolation pattern as test_deck_thompson_v2.py: in-memory SQLite patched
into backend.database, flag helpers patched directly.
"""

import uuid
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, text

import backend.database as db_module
import backend.server as server
from backend.database import (
    lift_latest_deck_suppression,
    load_deck_fatigue_reset,
    load_deck_suppressions,
    metadata,
    save_deck_suppression,
    set_deck_fatigue_reset,
)
from backend.trade_service import TradeCard, elo_to_value


LEAGUE = "league_f3"
ME     = "user_me"
OPP    = "user_opp"

# Seed Elo map: star is always the centerpiece of any package containing it.
SEED = {"star": 1800.0, "mid": 1500.0, "mid2": 1502.0, "scrub": 1250.0,
        "alt": 1499.0, "r1": 1490.0, "r2": 1480.0}


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


def _iso_ago(days=0.0, hours=0.0):
    return (datetime.now(timezone.utc) - timedelta(days=days, hours=hours)).isoformat()


def _hash_for(card):
    return server._deck_trade_hash(
        list(card.give_player_ids), list(card.receive_player_ids),
        card.target_user_id)


def _insert_impression(conn, iid, *, trade_hash=None, centerpiece=None,
                       archetype=None, job_id="job-x", age_days=0.0,
                       user_id=ME, league_id=LEAGUE):
    conn.execute(text(
        "INSERT INTO deck_impressions "
        "(impression_id, user_id, league_id, deck_job_id, card_index, "
        " trade_hash, propensity, archetype, shape_bucket, served_at, "
        " centerpiece_id) "
        "VALUES (:iid, :uid, :lid, :job, 0, :thash, 1.0, :arch, '1x1', "
        "        :served, :center)"
    ), {"iid": iid, "uid": user_id, "lid": league_id, "job": job_id,
        "thash": trade_hash, "arch": archetype, "served": _iso_ago(age_days),
        "center": centerpiece})


def _insert_outcome(conn, iid, action, age_days=0.0, hours=0.0):
    conn.execute(text(
        "INSERT INTO deck_outcomes (impression_id, action, acted_at) "
        "VALUES (:iid, :act, :at)"
    ), {"iid": iid, "act": action, "at": _iso_ago(age_days, hours)})


def _seed_viewed(conn, card, n=1, age_days=0.0, job_id="job-x"):
    """n viewed impressions of `card` (hash + centerpiece + archetype keys)."""
    for _ in range(n):
        iid = uuid.uuid4().hex
        _insert_impression(
            conn, iid,
            trade_hash  = _hash_for(card),
            centerpiece = server._fatigue_centerpiece(
                card.give_player_ids, card.receive_player_ids, SEED),
            archetype   = card.lane,
            job_id      = job_id,
            age_days    = age_days,
        )
        _insert_outcome(conn, iid, "viewed", age_days=age_days)


def _seed_pass(conn, centerpiece, job_id, hours=0.0, trade_hash=None):
    iid = uuid.uuid4().hex
    _insert_impression(conn, iid, trade_hash=trade_hash,
                       centerpiece=centerpiece, job_id=job_id)
    _insert_outcome(conn, iid, "pass", hours=hours)


def _mults(cards, retest_ids=None):
    return server._deck_fatigue_multipliers(
        cards, user_id=ME, league_id=LEAGUE, seed_map=SEED,
        retest_ids=retest_ids)


def _apply(cards):
    return server._apply_deck_suppression(
        cards, user_id=ME, league_id=LEAGUE, seed_map=SEED)


def _decline(give, recv, days_ago=0.0):
    """Insert a suppression row the way the disposition hook would."""
    now = datetime.now(timezone.utc) - timedelta(days=days_ago)
    save_deck_suppression(
        user_id        = ME,
        league_id      = LEAGUE,
        centerpiece_id = server._fatigue_centerpiece(give, recv, SEED),
        shape_bucket   = f"{len(give)}x{len(recv)}",
        package_value  = server._fatigue_package_value(give, recv, SEED),
        declined_at    = now.isoformat(),
        expires_at     = (now + timedelta(days=30)).isoformat(),
    )


# ---------------------------------------------------------------------------
# Flag OFF — byte-identical ordering + payloads, no F3 fields
# ---------------------------------------------------------------------------

def test_flag_off_order_deck_untouched_and_no_f3_reads(mem_engine):
    """All ordering flags off + fatigue off ⇒ _order_deck returns the input
    list object untouched and no F3 loader is ever hit — the pre-F3
    early-return contract."""
    with mem_engine.begin() as conn:
        card = _mk_card(["star"], ["mid"])
        _seed_viewed(conn, card, n=5)          # data exists, must be ignored
    cards = [_mk_card(["star"], ["mid"]), _mk_card(["alt"], ["scrub"])]
    with ExitStack() as stack:
        for helper in ("_thompson_deck_enabled", "_deck_thompson_v2_enabled",
                       "_deck_diversity_enabled"):
            stack.enter_context(patch.object(server, helper, lambda: False))
        stack.enter_context(patch.object(
            server, "load_deck_fatigue_events",
            MagicMock(side_effect=AssertionError("F3 loader touched"))))
        out = server._order_deck(
            cards, user_id=ME, league_id=LEAGUE, job_id="j1",
            seed_map=SEED, fatigue_mult=None)
    assert out is cards


def test_flag_off_no_new_payload_fields(mem_engine):
    """suppression_note only appears when the worker stored one; `retest`
    only when the (flag-gated) suppression pass stamped the attribute."""
    job = {"job_id": "j", "status": "complete", "opponents_done": 1,
           "opponents_total": 1, "cards": [], "error": None}
    assert "suppression_note" not in server._trade_job_public_view(job)
    job["suppression_note"] = {"count": 2, "latest_declined_at": "2026-07-20"}
    assert server._trade_job_public_view(job)["suppression_note"]["count"] == 2

    card = _mk_card(["star"], ["mid"])
    assert "retest" not in server.trade_card_to_dict(card, {})
    card.fatigue_retest = True
    assert server.trade_card_to_dict(card, {})["retest"] is True


def test_flag_off_impression_rows_have_null_centerpiece(mem_engine):
    with patch.object(server, "_deck_fatigue_enabled", lambda: False):
        server._log_deck_signal_impressions(
            user_id=ME, league_id=LEAGUE, job_id="j-off",
            cards=[_mk_card(["star"], ["mid"])], players_dict={},
            capture=None, scoring_format="1qb_ppr", seed_map=SEED)
    with patch.object(server, "_deck_fatigue_enabled", lambda: True):
        server._log_deck_signal_impressions(
            user_id=ME, league_id=LEAGUE, job_id="j-on",
            cards=[_mk_card(["star"], ["mid"])], players_dict={},
            capture=None, scoring_format="1qb_ppr", seed_map=SEED)
    with mem_engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT deck_job_id, centerpiece_id FROM deck_impressions"
        )).fetchall()
    by_job = {r.deck_job_id: r.centerpiece_id for r in rows}
    assert by_job["j-off"] is None
    assert by_job["j-on"] == "star"


# ---------------------------------------------------------------------------
# Soft fatigue — viewed-and-passed concepts score lower next generation
# ---------------------------------------------------------------------------

def test_viewed_concept_scores_lower_fresh_stays_at_one(mem_engine):
    seen  = _mk_card(["star"], ["mid"])
    fresh = _mk_card(["alt"], ["scrub"])
    with mem_engine.begin() as conn:
        _seed_viewed(conn, seen, n=1, age_days=0.0)
    m = _mults([seen, fresh])
    # w1·e^(−a·1) + w2·e^0 = .85·.8353 + .15 ≈ 0.860 with the defaults.
    assert m[id(seen)] == pytest.approx(0.860, abs=0.01)
    assert m[id(fresh)] == 1.0

    # Fatigue is a discount folded into the ordering key: the fatigued card
    # drops below an otherwise-lower-scored fresh card.
    seen.composite_score, fresh.composite_score = 10.0, 9.0
    with ExitStack() as stack:
        for helper in ("_thompson_deck_enabled", "_deck_thompson_v2_enabled",
                       "_deck_diversity_enabled"):
            stack.enter_context(patch.object(server, helper, lambda: False))
        out = server._order_deck(
            [seen, fresh], user_id=ME, league_id=LEAGUE, job_id="j",
            seed_map=SEED, fatigue_mult=m)
    assert out[0] is fresh   # 9.0×1.0 > 10.0×0.860


def test_more_impressions_more_fatigue_and_window_recovery(mem_engine):
    once   = _mk_card(["star"], ["mid"])
    lots   = _mk_card(["alt"], ["scrub"])
    stale  = _mk_card(["r1"], ["r2"])
    with mem_engine.begin() as conn:
        _seed_viewed(conn, once, n=1)
        _seed_viewed(conn, lots, n=5)
        _seed_viewed(conn, stale, n=5, age_days=45)   # outside 30d lookback
    m = _mults([once, lots, stale])
    assert m[id(lots)] < m[id(once)] < 1.0
    assert m[id(stale)] == 1.0, "impressions age out of the window entirely"
    # Floor holds even at heavy counts.
    assert m[id(lots)] >= 0.25


def test_archetype_accrual_weaker_than_item_level(mem_engine):
    seen = _mk_card(["star"], ["mid"], lane="window")
    with mem_engine.begin() as conn:
        _seed_viewed(conn, seen, n=1)
    same_arch = _mk_card(["r1"], ["r2"], lane="window")   # different players
    other     = _mk_card(["r1"], ["r2"], lane="value")
    m = _mults([seen, same_arch, other])
    assert m[id(same_arch)] < 1.0, "a passed-over shape cools the whole archetype"
    assert m[id(seen)] < m[id(same_arch)], "item-level fatigue is stronger"
    assert m[id(other)] == 1.0


def test_session_double_pass_strong_demotion(mem_engine):
    with mem_engine.begin() as conn:
        _seed_pass(conn, "star", "job-A")
        _seed_pass(conn, "star", "job-A")     # 2 in ONE job ⇒ strong
        _seed_pass(conn, "alt",  "job-A")
        _seed_pass(conn, "alt",  "job-B")     # 2 across jobs ⇒ NOT strong
    twice  = _mk_card(["star"], ["mid"])
    spread = _mk_card(["alt"], ["scrub"])
    m = _mults([twice, spread])
    assert m[id(twice)] == pytest.approx(0.2)     # fatigue_session_demotion
    assert m[id(spread)] > 0.2


def test_refresh_clears_pass_fatigue_only(mem_engine):
    seen = _mk_card(["star"], ["mid"])
    with mem_engine.begin() as conn:
        _seed_viewed(conn, seen, n=3)
        _seed_pass(conn, "star", "job-A")
        _seed_pass(conn, "star", "job-A")
    _decline(["alt"], ["scrub"])
    assert _mults([seen])[id(seen)] < 1.0

    set_deck_fatigue_reset(ME, LEAGUE)
    assert load_deck_fatigue_reset(ME, LEAGUE) is not None
    # Soft fatigue (views + session passes) fully cleared…
    assert _mults([seen])[id(seen)] == 1.0
    # …but the decline suppression still bites.
    dup = [_mk_card(["alt"], ["scrub"]) for _ in range(6)]
    with patch.object(server, "_DECK_MIN_CARDS", 2):
        kept, note, _ = _apply(dup)
    assert note is not None and note["count"] > 0


# ---------------------------------------------------------------------------
# Decline suppression — near-duplicates, note payload, undo
# ---------------------------------------------------------------------------

def test_decline_suppresses_near_duplicates_only(mem_engine):
    _decline(["star"], ["mid"])
    near   = _mk_card(["star"], ["mid2"])          # same center+shape, value in band
    other_shape = _mk_card(["star", "r1"], ["mid"])   # 2x1 ≠ 1x1
    off_value   = _mk_card(["star"], ["scrub"])    # value well outside ±10%
    liked  = _mk_card(["star"], ["mid2"], likes_you=True)
    fillers = [_mk_card(["r1"], ["r2"]) for _ in range(3)]

    with patch.object(server, "_DECK_MIN_CARDS", 2):
        kept, note, retests = _apply([near, other_shape, off_value, liked] + fillers)

    assert near not in kept
    assert other_shape in kept and off_value in kept
    assert liked in kept, "likes_you cards are never suppressed"
    assert retests == set()
    assert note["count"] == 1
    assert note["latest_declined_at"] is not None

    # Value-band sanity: the near-dup really is within ±10% of the declined
    # package on the shared consensus scale.
    declined_v = elo_to_value(SEED["star"]) + elo_to_value(SEED["mid"])
    near_v     = elo_to_value(SEED["star"]) + elo_to_value(SEED["mid2"])
    assert abs(near_v - declined_v) <= 0.10 * declined_v


def test_undo_lifts_newest_suppression_only(mem_engine):
    _decline(["star"], ["mid"], days_ago=5)
    _decline(["r1"], ["r2"], days_ago=1)           # newest
    assert lift_latest_deck_suppression(ME, LEAGUE) == 1
    rows = load_deck_suppressions(ME, LEAGUE)      # non-lifted only
    assert len(rows) == 1
    assert rows[0]["centerpiece_id"] == "star", "older window survives the undo"

    # The lifted concept flows again; the surviving one is still suppressed.
    lifted_dup = _mk_card(["r1"], ["r2"])
    still_dup  = _mk_card(["star"], ["mid2"])
    with patch.object(server, "_DECK_MIN_CARDS", 1):
        kept, note, _ = _apply([lifted_dup, still_dup, _mk_card(["alt"], ["scrub"])])
    assert lifted_dup in kept and still_dup not in kept
    assert lift_latest_deck_suppression(ME, LEAGUE) == 1   # second undo → older row
    assert lift_latest_deck_suppression(ME, LEAGUE) == 0   # nothing left


# ---------------------------------------------------------------------------
# Retest — exactly ONE after expiry, low exposure, re-suppress on pass
# ---------------------------------------------------------------------------

def test_expired_window_grants_exactly_one_labeled_retest(mem_engine):
    _decline(["star"], ["mid"], days_ago=31)        # expired
    dup_a = _mk_card(["star"], ["mid"], composite=9.0)
    dup_b = _mk_card(["star"], ["mid2"], composite=8.0)
    filler = [_mk_card(["r1"], ["r2"]) for _ in range(2)]

    with patch.object(server, "_DECK_MIN_CARDS", 2):
        kept, note, retests = _apply([dup_a, dup_b] + filler)

    assert dup_a in kept and dup_b not in kept, "exactly one retest card"
    assert retests == {id(dup_a)}
    assert getattr(dup_a, "fatigue_retest", False) is True
    assert server.trade_card_to_dict(dup_a, {})["retest"] is True
    # Low exposure: the retest rides a ≤ fatigue_retest_mult multiplier.
    m = _mults(kept, retest_ids=retests)
    assert m[id(dup_a)] <= 0.5

    row = load_deck_suppressions(ME, LEAGUE)[0]
    assert row["retested_at"] is not None
    assert row["retest_trade_hash"] == _hash_for(dup_a)

    # Regenerating BEFORE any verdict on the retest does not grant a second
    # retest card, and the concept is not re-suppressed either.
    dup_c = _mk_card(["star"], ["mid"], composite=7.0)
    with patch.object(server, "_DECK_MIN_CARDS", 1):
        kept2, note2, retests2 = _apply([dup_c, _mk_card(["alt"], ["scrub"])])
    assert dup_c in kept2 and retests2 == set() and note2 is None


def test_passed_retest_rearms_the_window(mem_engine):
    _decline(["star"], ["mid"], days_ago=31)
    retest = _mk_card(["star"], ["mid"])
    with patch.object(server, "_DECK_MIN_CARDS", 1):
        kept, _n, retests = _apply([retest, _mk_card(["alt"], ["scrub"])])
    assert retests == {id(retest)}

    # User passes the retest card (viewed impression + pass outcome on its hash).
    with mem_engine.begin() as conn:
        iid = uuid.uuid4().hex
        _insert_impression(conn, iid, trade_hash=_hash_for(retest),
                           centerpiece="star")
        _insert_outcome(conn, iid, "pass")

    dup = _mk_card(["star"], ["mid2"])
    with patch.object(server, "_DECK_MIN_CARDS", 1):
        kept2, note2, retests2 = _apply([dup, _mk_card(["alt"], ["scrub"])])
    assert dup not in kept2, "passed retest re-suppresses near-duplicates"
    assert note2["count"] == 1 and retests2 == set()
    row = load_deck_suppressions(ME, LEAGUE)[0]
    assert row["retested_at"] is None, "re-armed row owes a fresh retest next window"
    assert row["expires_at"] > datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Floor — suppression never starves the deck, and never silently
# ---------------------------------------------------------------------------

def test_suppression_floor_keeps_deck_min_and_logs(mem_engine, caplog):
    _decline(["star"], ["mid"])
    dups = [_mk_card(["star"], ["mid2"], composite=float(10 - i)) for i in range(6)]
    with caplog.at_level("WARNING"):
        kept, note, _ = _apply(dups)
    assert len(kept) == server._DECK_MIN_CARDS
    # The best suppressed cards were restored (worst one stays hidden).
    assert min(dups, key=lambda c: c.composite_score) not in kept
    assert note["count"] == 1
    assert any("suppression floor engaged" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# League caps unchanged — A6 intra-deck cap still enforced with fatigue on
# ---------------------------------------------------------------------------

def test_league_caps_still_apply_with_fatigue_on(mem_engine):
    # 6 cards target the same top receive asset, 3 a different one.
    same = [_mk_card([f"g{i}"], ["star"], composite=float(20 - i)) for i in range(6)]
    other = [_mk_card([f"h{i}"], ["mid"], composite=float(5 - i)) for i in range(3)]
    cards = same + other
    fatigue = {id(c): 1.0 for c in cards}
    with ExitStack() as stack:
        stack.enter_context(patch.object(server, "_thompson_deck_enabled", lambda: False))
        stack.enter_context(patch.object(server, "_deck_thompson_v2_enabled", lambda: False))
        stack.enter_context(patch.object(server, "_deck_diversity_enabled", lambda: True))
        stack.enter_context(patch.object(
            server, "load_recent_impression_target_user_counts",
            MagicMock(return_value={})))
        out = server._order_deck(
            cards, user_id=ME, league_id=LEAGUE, job_id="j",
            seed_map=SEED, fatigue_mult=fatigue)
    per_target = sum(1 for c in out if c.receive_player_ids == ["star"])
    assert per_target == 3, "deck_max_per_target unchanged by the fatigue layer"


# ---------------------------------------------------------------------------
# Fatigue state read failure — generation must degrade, never break
# ---------------------------------------------------------------------------

def test_fatigue_read_failure_degrades_to_neutral(mem_engine):
    card = _mk_card(["star"], ["mid"])
    with patch.object(server, "load_deck_fatigue_events",
                      MagicMock(side_effect=RuntimeError("db down"))):
        m = _mults([card])
    assert m[id(card)] == 1.0
