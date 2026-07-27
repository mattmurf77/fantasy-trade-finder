"""F9 (flag deck.first_session) — first-session win engineering.

docs/plans/tiktok-discovery/prds/F9-first-session-win.md (incl. the
2026-07-26 board-sourced amendment). Contract under test:

  - First-deck detection: no deck_impressions AND no legacy
    trade_impressions rows for the user+league. Either kind of prior row
    ⇒ NOT a first deck (existing-user no-op contract).
  - Confidence bar (_first_session_confidence_ok): simple shape (per side
    ≤ 2, total ≤ 3 at defaults), every asset consensus-seeded ≥
    first_session_min_seed_elo, and margin — divergence cards need
    mismatch_score ≥ first_session_min_margin, consensus cards need
    fairness_score ≥ first_session_min_fairness.
  - Shaping (_apply_first_session_shaping): first decks clamp to
    first_session_deck_max cards (truncate only), then a STABLE PARTITION
    floats confidence-passing cards into the first first_session_top_k
    UNLOCKED slots. Locked slots (F7 wildcard, likes-you pins, F3 retest)
    keep their exact index — with the wildcard at served slot 5 the
    confidence region is positions 1-4 + 6.
  - Board-refresh header (_first_session_board_refresh): the additive
    payload appears ONLY when the user's board updated after their
    previous F1-spine deck; omitted when deck.signal_v2 is off, when no
    previous deck exists, or when the board is older.
  - Flag OFF ⇒ byte-identical: the public job view carries no F9 keys and
    features_json gets no first_deck stamp.

Same isolation pattern as test_deck_exploration.py: in-memory SQLite
patched into backend.database, flag helpers patched directly.
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
from backend.database import load_deck_serve_history, metadata
from backend.trade_service import TradeCard


LEAGUE = "league_f9"
ME     = "user_me"
OPP    = "user_opp"

# Every fixture asset is seeded well above the default 1250 bar unless a
# test explicitly wants a thin-data player.
SEED_HI = 1600.0


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def mem_engine():
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db_module, "engine", eng):
        yield eng


def _mk_card(give, recv, *, composite=5.0, mismatch=100.0, fairness=0.9,
             basis="divergence", likes_you=False, target=OPP):
    return TradeCard(
        trade_id           = f"t_{uuid.uuid4().hex[:8]}",
        league_id          = LEAGUE,
        proposing_user_id  = ME,
        target_user_id     = target,
        target_username    = "opp",
        give_player_ids    = list(give),
        receive_player_ids = list(recv),
        mismatch_score     = mismatch,
        fairness_score     = fairness,
        composite_score    = composite,
        basis              = basis,
        likes_you          = likes_you,
    )


def _seed_for(cards, value=SEED_HI):
    seed = {}
    for c in cards:
        for pid in (*c.give_player_ids, *c.receive_player_ids):
            seed[pid] = value
    return seed


def _passing(i, composite=5.0):
    """A card that clears the confidence bar (1x1, high margin, seeded)."""
    return _mk_card([f"pg{i}"], [f"pr{i}"], composite=composite)


def _failing_shape(i, composite=9.0):
    """Gate-passing but complex (3-for-2) — fails the simplicity check."""
    return _mk_card([f"fg{i}a", f"fg{i}b", f"fg{i}c"], [f"fr{i}a", f"fr{i}b"],
                    composite=composite)


def _iso_ago(days=0.0):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _insert_deck_impression(conn, *, age_days=0.0, user_id=ME,
                            league_id=LEAGUE):
    conn.execute(text(
        "INSERT INTO deck_impressions "
        "(impression_id, user_id, league_id, deck_job_id, card_index, "
        " propensity, served_at) "
        "VALUES (:iid, :uid, :lid, 'job-old', 0, 1.0, :served)"
    ), {"iid": uuid.uuid4().hex, "uid": user_id, "lid": league_id,
        "served": _iso_ago(age_days)})


def _insert_legacy_impression(conn, *, user_id=ME, league_id=LEAGUE):
    conn.execute(text(
        "INSERT INTO trade_impressions "
        "(user_id, league_id, give_player_ids, receive_player_ids, shown_at) "
        "VALUES (:uid, :lid, '[]', '[]', :at)"
    ), {"uid": user_id, "lid": league_id, "at": _iso_ago(10.0)})


def _insert_member_ranking(conn, *, age_days=0.0, user_id=ME,
                           league_id=LEAGUE, fmt="1qb_ppr", n=1):
    for i in range(n):
        conn.execute(text(
            "INSERT INTO member_rankings "
            "(user_id, league_id, player_id, elo, updated_at, scoring_format) "
            "VALUES (:uid, :lid, :pid, 1500.0, :at, :fmt)"
        ), {"uid": user_id, "lid": league_id, "pid": f"mr{uuid.uuid4().hex[:6]}",
            "at": _iso_ago(age_days), "fmt": fmt})


# ---------------------------------------------------------------------------
# Confidence bar
# ---------------------------------------------------------------------------

def test_confidence_bar_simple_seeded_high_margin_passes():
    card = _mk_card(["a"], ["b"], mismatch=100.0)
    assert server._first_session_confidence_ok(card, {"a": SEED_HI, "b": SEED_HI})


def test_confidence_bar_rejects_complex_shapes():
    seed = {f"x{i}": SEED_HI for i in range(6)}
    # 3 on one side — per-side cap.
    c3x1 = _mk_card(["x0", "x1", "x2"], ["x3"])
    assert not server._first_session_confidence_ok(c3x1, seed)
    # 2x2 — total-asset cap (4 > 3).
    c2x2 = _mk_card(["x0", "x1"], ["x2", "x3"])
    assert not server._first_session_confidence_ok(c2x2, seed)
    # 2x1 and 1x2 stay simple.
    assert server._first_session_confidence_ok(_mk_card(["x0", "x1"], ["x2"]), seed)
    assert server._first_session_confidence_ok(_mk_card(["x0"], ["x1", "x2"]), seed)


def test_confidence_bar_rejects_thin_data_assets():
    # Unseeded receive asset — no consensus price, thin data.
    card = _mk_card(["a"], ["deep_stash"])
    assert not server._first_session_confidence_ok(card, {"a": SEED_HI})
    # Seeded but below the floor (fringe consensus value).
    assert not server._first_session_confidence_ok(
        card, {"a": SEED_HI, "deep_stash": 1210.0})


def test_confidence_bar_margin_by_basis():
    seed = {"a": SEED_HI, "b": SEED_HI}
    # Divergence: mismatch bar (default 40).
    assert not server._first_session_confidence_ok(
        _mk_card(["a"], ["b"], mismatch=10.0), seed)
    # Consensus: mismatch is 0 by construction — fairness bar instead.
    assert server._first_session_confidence_ok(
        _mk_card(["a"], ["b"], basis="consensus", mismatch=0.0, fairness=0.92),
        seed)
    assert not server._first_session_confidence_ok(
        _mk_card(["a"], ["b"], basis="consensus", mismatch=0.0, fairness=0.7),
        seed)


# ---------------------------------------------------------------------------
# Shaping — confidence partition of the top region
# ---------------------------------------------------------------------------

def test_first_deck_positions_1_to_5_pass_the_bar():
    # 4 complex high-composite cards lead the served order; 5 simple
    # passing cards trail. The partition floats the passing cards into the
    # top 5 slots, preserving relative order on both groups.
    failing = [_failing_shape(i, composite=9.0 - i * 0.1) for i in range(4)]
    passing = [_passing(i, composite=5.0 - i * 0.1) for i in range(5)]
    deck = failing + passing
    seed = _seed_for(deck)

    out = server._apply_first_session_shaping(deck, seed_map=seed)

    assert len(out) == 9
    assert [c.trade_id for c in out[:5]] == [c.trade_id for c in passing]
    for c in out[:5]:
        assert server._first_session_confidence_ok(c, seed)
    # Displaced complex cards follow, original order preserved.
    assert [c.trade_id for c in out[5:]] == [c.trade_id for c in failing]
    # Membership unchanged (reorder only — quality gates untouched).
    assert sorted(c.trade_id for c in out) == sorted(c.trade_id for c in deck)


def test_partition_is_stable_and_best_effort_when_few_pass():
    failing = [_failing_shape(i, composite=9.0 - i) for i in range(4)]
    passing = [_passing(0, composite=1.0), _passing(1, composite=0.9)]
    deck = failing[:2] + [passing[0]] + failing[2:] + [passing[1]]
    seed = _seed_for(deck)

    out = server._apply_first_session_shaping(deck, seed_map=seed)

    # Both passing cards lead (served order between them preserved) and
    # the failing cards keep their relative order after them.
    assert [c.trade_id for c in out[:2]] == [c.trade_id for c in passing]
    assert [c.trade_id for c in out[2:]] == [c.trade_id for c in failing]


def test_no_passing_cards_leaves_order_unchanged():
    deck = [_failing_shape(i) for i in range(6)]
    out = server._apply_first_session_shaping(deck, seed_map=_seed_for(deck))
    assert [c.trade_id for c in out] == [c.trade_id for c in deck]


# ---------------------------------------------------------------------------
# Shaping — F7 wildcard / likes-you interaction (locked slots)
# ---------------------------------------------------------------------------

def test_wildcard_slot_keeps_position_region_becomes_1_4_and_6():
    # Served deck of 9 with the F7 wildcard at index 4 (served slot 5).
    failing = [_failing_shape(i, composite=9.0 - i * 0.1) for i in range(4)]
    wildcard = _failing_shape(99, composite=2.0)
    wildcard.wildcard = True
    passing = [_passing(i, composite=5.0 - i * 0.1) for i in range(5)]
    deck = failing + [wildcard] + passing[:4] + [passing[4]]
    deck = deck[:9]  # 4 failing + wildcard + 4 passing
    seed = _seed_for(deck + passing)

    out = server._apply_first_session_shaping(deck, seed_map=seed)

    # The wildcard NEVER moves — slot 5 (index 4) is its fixed position.
    assert out[4] is wildcard
    # The confidence region is the first 5 UNLOCKED slots: indices
    # 0,1,2,3,5 — all filled by the passing cards (4 available here).
    unlocked_top = [out[i] for i in (0, 1, 2, 3, 5)]
    assert [c.trade_id for c in unlocked_top[:4]] == [
        c.trade_id for c in passing[:4]]
    for c in unlocked_top[:4]:
        assert server._first_session_confidence_ok(c, seed)


def test_likes_you_pin_never_moves_and_counts_as_top_slot():
    pin = _failing_shape(50, composite=99.0)   # complex, but counterparty-liked
    pin.likes_you = True
    failing = [_failing_shape(i, composite=9.0 - i * 0.1) for i in range(3)]
    passing = [_passing(i, composite=5.0 - i * 0.1) for i in range(5)]
    deck = [pin] + failing + passing
    seed = _seed_for(deck)

    out = server._apply_first_session_shaping(deck, seed_map=seed)

    assert out[0] is pin                       # pinned slot untouched
    # Region = 5 unlocked slots (indices 1-5) → filled by passing cards.
    assert [c.trade_id for c in out[1:6]] == [c.trade_id for c in passing]


# ---------------------------------------------------------------------------
# Shaping — first-deck size clamp
# ---------------------------------------------------------------------------

def test_size_clamp_truncates_to_max_only_when_larger():
    deck = [_passing(i, composite=9.0 - i * 0.1) for i in range(15)]
    seed = _seed_for(deck)
    out = server._apply_first_session_shaping(deck, seed_map=seed)
    assert len(out) == 10                       # first_session_deck_max
    assert [c.trade_id for c in out] == [c.trade_id for c in deck[:10]]

    small = [_passing(i, composite=9.0 - i * 0.1) for i in range(8)]
    out2 = server._apply_first_session_shaping(small, seed_map=_seed_for(small))
    assert len(out2) == 8                       # never padded, never shrunk


# ---------------------------------------------------------------------------
# First-deck detection — second decks / existing users are a no-op
# ---------------------------------------------------------------------------

def test_history_empty_means_first_deck(mem_engine):
    has_prior, last = load_deck_serve_history(ME, LEAGUE)
    assert has_prior is False and last is None


def test_spine_row_means_not_first_deck(mem_engine):
    with mem_engine.begin() as conn:
        _insert_deck_impression(conn, age_days=2.0)
    has_prior, last = load_deck_serve_history(ME, LEAGUE)
    assert has_prior is True
    assert last is not None


def test_legacy_pre_f1_rows_mean_not_first_deck(mem_engine):
    # Existing users whose decks predate the F1 spine: trade_impressions
    # rows exist, deck_impressions is empty. Shaping must never fire.
    with mem_engine.begin() as conn:
        _insert_legacy_impression(conn)
    has_prior, last = load_deck_serve_history(ME, LEAGUE)
    assert has_prior is True
    assert last is None       # no spine timestamp ⇒ board_refresh omitted


def test_history_is_scoped_per_user_and_league(mem_engine):
    with mem_engine.begin() as conn:
        _insert_deck_impression(conn, user_id="someone_else")
        _insert_deck_impression(conn, league_id="other_league")
        _insert_legacy_impression(conn, user_id="someone_else")
    has_prior, last = load_deck_serve_history(ME, LEAGUE)
    assert has_prior is False and last is None


# ---------------------------------------------------------------------------
# Board-refresh header (amendment 2026-07-26)
# ---------------------------------------------------------------------------

def _board_refresh(last_served_at, *, signal_v2=True, fmt="1qb_ppr"):
    with patch.object(server, "_deck_signal_v2_enabled", lambda: signal_v2):
        return server._first_session_board_refresh(ME, LEAGUE, fmt, last_served_at)


def test_board_refresh_present_when_board_newer_than_previous_deck(mem_engine):
    with mem_engine.begin() as conn:
        _insert_member_ranking(conn, age_days=1.0, n=7)   # board updated 1d ago
    payload = _board_refresh(_iso_ago(2.0))               # prior deck 2d ago
    assert payload == {
        "updated_since_last_deck": True,
        "ranked_player_count": 7,
        "basis": "personal",
    }


def test_board_refresh_omitted_when_board_older_than_previous_deck(mem_engine):
    with mem_engine.begin() as conn:
        _insert_member_ranking(conn, age_days=5.0, n=3)
    assert _board_refresh(_iso_ago(2.0)) is None


def test_board_refresh_omitted_without_previous_deck_or_board(mem_engine):
    # No previous F1 deck ⇒ nothing to compare against.
    with mem_engine.begin() as conn:
        _insert_member_ranking(conn, age_days=1.0)
    assert _board_refresh(None) is None
    # Previous deck but no board rows ⇒ no update timestamp.
    with mem_engine.begin() as conn:
        conn.execute(text("DELETE FROM member_rankings"))
    assert _board_refresh(_iso_ago(2.0)) is None


def test_board_refresh_omitted_when_signal_v2_off(mem_engine):
    # PRD fallback: without the F1 spine there is no previous-deck
    # timestamp — the field is omitted rather than guessed.
    with mem_engine.begin() as conn:
        _insert_member_ranking(conn, age_days=1.0)
    assert _board_refresh(_iso_ago(2.0), signal_v2=False) is None


# ---------------------------------------------------------------------------
# Public job view + features_json — flag-off byte-identical
# ---------------------------------------------------------------------------

_BASE_JOB = {
    "job_id": "j1", "status": "complete", "opponents_done": 3,
    "opponents_total": 3, "cards": [], "error": None,
}


def test_public_view_carries_no_f9_keys_without_worker_stamps():
    # Pre-F9 job dicts (flag off ⇒ the worker never sets the fields)
    # serialize with exactly the pre-F9 key set.
    out = server._trade_job_public_view(dict(_BASE_JOB))
    assert set(out.keys()) == {
        "job_id", "status", "opponents_done", "opponents_total",
        "cards", "error",
    }


def test_public_view_passes_through_f9_fields_when_stamped():
    job = dict(_BASE_JOB)
    job["first_deck"] = True
    job["board_refresh"] = {
        "updated_since_last_deck": True, "ranked_player_count": 12,
        "basis": "personal",
    }
    out = server._trade_job_public_view(job)
    assert out["first_deck"] is True
    assert out["board_refresh"]["ranked_player_count"] == 12


def test_features_json_first_deck_stamp_only_when_marked(mem_engine):
    players = {
        "a": SimpleNamespace(id="a", position="RB", age=25, team="T", name="a"),
        "b": SimpleNamespace(id="b", position="WR", age=25, team="T", name="b"),
    }
    seed = {"a": SEED_HI, "b": SEED_HI}

    def _log(first_deck):
        card = _mk_card(["a"], ["b"])
        with ExitStack() as stack:
            stack.enter_context(patch.object(
                server, "_deck_taste_enabled", lambda: False))
            stack.enter_context(patch.object(
                server, "_deck_fatigue_enabled", lambda: False))
            imp = server._log_deck_signal_impressions(
                user_id=ME, league_id=LEAGUE, job_id=f"job-{uuid.uuid4().hex[:6]}",
                cards=[card], players_dict=players, capture=None,
                scoring_format="1qb_ppr", seed_map=seed,
                first_deck=first_deck,
            )
        assert len(imp) == 1
        with mem_engine.connect() as conn:
            row = conn.execute(text(
                "SELECT features_json FROM deck_impressions "
                "WHERE impression_id = :iid"
            ), {"iid": list(imp.values())[0]}).first()
        return json.loads(row[0])

    features_default = _log(first_deck=False)
    assert "first_deck" not in features_default   # byte-identical to pre-F9

    features_first = _log(first_deck=True)
    assert features_first["first_deck"] is True
    # The stamp is the ONLY difference.
    features_first.pop("first_deck")
    assert features_first == features_default
