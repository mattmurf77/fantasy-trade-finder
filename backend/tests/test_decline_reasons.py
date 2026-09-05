"""Decline-reason capture (flag feedback.decline_reasons) — backend half.

Spec: docs/plans/decline-reason-capture/SPEC.md (operator-approved
2026-08-17). Covers the four things that can silently go wrong:

  • THE GATE — the flag is the ONLY condition (operator, 2026-08-17: ships
    to all users, superseding SPEC §5's allowlist scoping). Flag off ⇒ 404
    and nothing written; flag on ⇒ works for any signed-in caller, with or
    without the tester apparatus. /api/trades/swipe's pass path is untouched
    either way, which is what makes the flag a true one-line revert.
  • PROGRESSIVE WRITES (SPEC §3) — every tap commits on its own and no tap
    loses an earlier one: layer 1 alone, layer 1 → layer 2, Other → text,
    and a tile switch that records `switched_from` while keeping the first
    answer. Re-taps and out-of-order writes are idempotent; the card is
    passed exactly once.
  • ELO SUPPRESSION (SPEC §4) — the full per-code matrix, run with the
    `pass_reason_elo_suppression` knob ON and OFF.
  • ANALYTICS (SPEC §6) — both names registered, exactly the specced props,
    and no path by which free text could become one.

Harness follows test_deck_signal_v2.py: an isolated in-memory SQLite patched
into backend.database, a session registered in server module state, and the
Flask test client for the routes.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, func, select

import backend.database as db_module
import backend.ranking_service as rs_module
import backend.server as server
from backend.analytics_taxonomy import (
    ALLOWED_CLIENT_EVENTS,
    CLIENT_EVENT_PROPS,
    SERVER_FIRED_EVENTS,
)
from backend.database import (
    load_trade_pass_reason,
    metadata,
    swipe_decisions_table,
    trade_decisions_table,
    trade_pass_reasons_table,
)
from backend.ranking_service import Player, RankingService
from backend.trade_service import League, LeagueMember, TradeCard, TradeService


LEAGUE = "league_reason"
ME     = "user_me"
OPP    = "user_opp"
TOKEN  = "test-token-reason"
DEVICE = "dev_reason"
TRADE  = "trade_abc"
IMP    = "imp_abc"


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

@pytest.fixture()
def mem_engine():
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db_module, "engine", eng):
        _seed_impression(IMP, TRADE)
        yield eng


def _seed_impression(impression_id: str, trade_id: str, user_id: str = ME,
                     card_index: int = 0):
    """One F1 deck_impressions row. Required: the impression-ownership check
    (2026-08-14 LLD-review fix) rejects any id that names no impression or
    belongs to another user, on BOTH the deck-outcome write and this
    feature's upsert key."""
    db_module.save_deck_impressions([{
        "impression_id": impression_id,
        "user_id":       user_id,
        "league_id":     LEAGUE,
        "deck_job_id":   "job_reason",
        "card_index":    card_index,
        "trade_hash":    trade_id,
        "features_json": "{}",
        "propensity":    1.0,
        "base_score":    1.0,
        "final_score":   1.0,
        "archetype":     "value_move",
        "shape_bucket":  "1x1",
        "served_at":     db_module._now(),
    }])


@pytest.fixture()
def harness(mem_engine):
    """Session + one registered trade card, flag ON. The allowlist patch is
    here only to prove the feature does not CONSULT it — tests that care
    override it with an empty set."""
    pool = [Player(id=pid, name=pid.upper(), position="RB", team="AAA", age=25)
            for pid in ("g1", "g2", "r1", "r2")]
    service   = RankingService(players=list(pool))
    trade_svc = TradeService(players={p.id: p for p in pool})
    league = League(
        league_id=LEAGUE, name="Reason League", platform="sleeper",
        members=[
            LeagueMember(user_id=ME,  username="me",  roster=["g1", "g2"], elo_ratings={}),
            LeagueMember(user_id=OPP, username="opp", roster=["r1", "r2"], elo_ratings={}),
        ],
    )
    trade_svc.add_league(league)
    card = TradeCard(
        trade_id           = TRADE,
        league_id          = LEAGUE,
        proposing_user_id  = ME,
        target_user_id     = OPP,
        target_username    = "opp",
        give_player_ids    = ["g1"],
        receive_player_ids = ["r1"],
        mismatch_score     = 0.0,
        fairness_score     = 0.0,
        composite_score    = 0.0,
    )
    trade_svc._trade_cards[TRADE] = card

    sess = {
        "user_id":       ME,
        "verified":      True,
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

    server.app.config["TESTING"] = True
    client = server.app.test_client()

    with patch.object(server, "_decline_reasons_enabled", lambda: True), \
         patch.object(server, "_load_tester_allowlist",
                      lambda: {f"device:{DEVICE}", ME}), \
         patch.object(server, "_deck_signal_v2_enabled", lambda: True), \
         patch.object(server, "create_notification", MagicMock()), \
         patch.object(server, "_send_typed_push", MagicMock()):
        with server._sessions_lock:
            server._sessions[TOKEN] = sess
        try:
            yield client, service, trade_svc, mem_engine
        finally:
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)


def _post(client, body, path="/api/trades/pass-reason",
          token=TOKEN, device=DEVICE):
    headers = {}
    if device:
        headers["X-Device-Id"] = device
    if token:
        headers["X-Session-Token"] = token
    return client.post(path, data=json.dumps(body),
                       content_type="application/json", headers=headers)


def _reason(body, **kw):
    """POST one layer of a decline reason for the standard card."""
    return {"trade_id": TRADE, "impression_id": IMP, **body, **kw}


def _swipe_rows(eng):
    with eng.connect() as conn:
        return conn.execute(select(swipe_decisions_table)).fetchall()


def _decision_rows(eng):
    with eng.connect() as conn:
        return conn.execute(select(trade_decisions_table)).fetchall()


def _row_count(eng):
    with eng.connect() as conn:
        return conn.execute(
            select(func.count(trade_pass_reasons_table.c.impression_id))
        ).scalar()


def _knob(value: float):
    """Patch the model_config knob directly — independent of the DB."""
    cfg = dict(rs_module._cfg)
    cfg["pass_reason_elo_suppression"] = value
    return patch.object(rs_module, "_cfg", cfg)


# ---------------------------------------------------------------------------
# The gate (SPEC §5)
# ---------------------------------------------------------------------------

def test_flag_off_404s_and_writes_nothing(harness):
    client, _service, _svc, eng = harness
    with patch.object(server, "_decline_reasons_enabled", lambda: False):
        r = _post(client, _reason({"reason": "value"}))
    assert r.status_code == 404
    assert r.get_json()["error"] == "feature_disabled"
    assert _row_count(eng) == 0
    assert _decision_rows(eng) == []
    assert _swipe_rows(eng) == []


def test_no_allowlist_gating_anywhere(harness):
    """Operator decision 2026-08-17, superseding SPEC §5: this ships to ALL
    users. An empty tester allowlist must change NOTHING — not the route, not
    the served flag map. The flag is the only condition, which is what makes
    it a true one-line revert."""
    client, _service, _svc, eng = harness
    with patch.object(server, "_load_tester_allowlist", lambda: set()):
        r = _post(client, _reason({"reason": "value"}))
        assert r.status_code == 200, r.get_json()
        assert _row_count(eng) == 1
        served = client.get("/api/feature-flags",
                            headers={"X-Device-Id": "some_random_device"})
        assert served.get_json()["flags"]["feedback.decline_reasons"] is True


def test_works_with_no_device_header_and_no_allowlist(harness):
    """A plain signed-in user with none of the tester apparatus."""
    client, _service, _svc, eng = harness
    with patch.object(server, "_load_tester_allowlist", lambda: set()):
        r = _post(client, _reason({"reason": "fit"}), device=None)
    assert r.status_code == 200
    assert _row_count(eng) == 1


def test_the_flag_ships_on_for_everyone(harness):
    """config/features.json carries it ON, and GET /api/feature-flags serves
    that value verbatim to every caller — the client surface and the route can
    never disagree about whether the feature is live."""
    import json as _json
    from pathlib import Path
    repo = Path(server.__file__).resolve().parents[1]
    features = _json.loads((repo / "config/features.json").read_text())
    assert features["feedback.decline_reasons"] is True

    client, _service, _svc, _eng = harness
    served = client.get("/api/feature-flags",
                        headers={"X-Device-Id": DEVICE}).get_json()["flags"]
    assert served["feedback.decline_reasons"] is server.FLAGS.feedback_decline_reasons


def test_flag_off_leaves_the_swipe_pass_path_byte_identical(harness):
    """SPEC §5 — with the feature dark, a pass through /api/trades/swipe
    behaves exactly as it does today: one trade_decisions row, the full
    Elo write, and NO trade_pass_reasons row anywhere."""
    client, service, _svc, eng = harness
    with patch.object(server, "_decline_reasons_enabled", lambda: False):
        r = _post(client, {"trade_id": TRADE, "decision": "pass",
                           "impression_id": IMP},
                  path="/api/trades/swipe")
    assert r.status_code == 200
    decisions = _decision_rows(eng)
    assert len(decisions) == 1 and decisions[0].decision == "pass"
    # give beats receive — today's unconditional pass signal.
    swipes = _swipe_rows(eng)
    assert len(swipes) == 1
    assert (swipes[0].winner_player_id, swipes[0].loser_player_id) == ("g1", "r1")
    assert len(service._trade_swipes) == 1
    assert _row_count(eng) == 0


def test_swipe_pass_is_unchanged_even_with_the_flag_on(harness):
    """The new route is additive: turning the feature ON does not alter the
    shipped ✓/✕ route at all (nothing in swipe_trade reads the flag)."""
    client, service, _svc, eng = harness
    r = _post(client, {"trade_id": TRADE, "decision": "pass",
                       "impression_id": IMP},
              path="/api/trades/swipe")
    assert r.status_code == 200
    assert len(_swipe_rows(eng)) == 1
    assert len(service._trade_swipes) == 1
    assert _row_count(eng) == 0


# ---------------------------------------------------------------------------
# One pass disposition per impression (2026-08-29 prod audit)
#
# The shipped mobile client fires BOTH halves for one tile tap:
# handleReasonLayer1 → postDeclineReason (POST /api/trades/pass-reason, no
# dwell_ms in its payload) AND advance('pass') → the unchanged swipe POST
# (impression_id + dwell_ms), ~20-90ms apart. Each route writes the pass
# disposition — pass-reason via _apply_reasoned_pass, swipe via its own
# _save_deck_outcome_safe call — which put 2-3 action='pass' rows on 120 of
# 410 passed impressions in prod (one NULL-dwell, one dwell-set).
# deck_pass_outcome_recorded now makes the second write a counted skip.
# ---------------------------------------------------------------------------

def _outcome_rows(eng):
    with eng.connect() as conn:
        return conn.execute(
            select(db_module.deck_outcomes_table)
            .order_by(db_module.deck_outcomes_table.c.id)).fetchall()


def test_tile_tap_then_swipe_writes_one_pass_outcome(harness):
    """The prod double-write, client order: reason POST lands first (its
    payload carries no dwell), the swipe POST arrives ~20-90ms later with
    dwell set. One pass row survives — the first."""
    client, _service, _svc, eng = harness
    r1 = _post(client, _reason({"reason": "value"}))
    assert r1.status_code == 200 and r1.get_json()["passed"] is True
    r2 = _post(client, {"trade_id": TRADE, "decision": "pass",
                        "impression_id": IMP, "dwell_ms": 4300},
               path="/api/trades/swipe")
    assert r2.status_code == 200
    rows = _outcome_rows(eng)
    assert [(r.impression_id, r.action, r.dwell_ms) for r in rows] == \
        [(IMP, "pass", None)]
    # The reason row and the decision are still single too, and layer-1-only
    # Elo suppression survives the swipe replay (dedupe skips its Elo write).
    assert _row_count(eng) == 1
    assert len(_decision_rows(eng)) == 1
    assert _swipe_rows(eng) == []


def test_swipe_then_tile_tap_writes_one_pass_outcome(harness):
    """The same double-write with the network race reversed: the swipe POST
    lands first (dwell set), then the reason POST. Still one pass row — the
    swipe's — and the reasoned path still banks the reason on its own row."""
    client, _service, _svc, eng = harness
    r1 = _post(client, {"trade_id": TRADE, "decision": "pass",
                        "impression_id": IMP, "dwell_ms": 2100},
               path="/api/trades/swipe")
    assert r1.status_code == 200
    r2 = _post(client, _reason({"reason": "fit"}))
    assert r2.status_code == 200
    rows = _outcome_rows(eng)
    assert [(r.impression_id, r.action, r.dwell_ms) for r in rows] == \
        [(IMP, "pass", 2100)]
    assert load_trade_pass_reason(IMP)["reason"] == "fit"
    assert len(_decision_rows(eng)) == 1
    # The swipe path (first) wrote its unconditional Elo signal; the reason
    # path must not add a second (save_trade_decision dedupe).
    assert len(_swipe_rows(eng)) == 1


def test_retapped_layer1_does_not_write_a_second_pass_outcome(harness):
    """Re-sending layer 1 (retry, re-tap) was already pass-once at the
    trade_pass_reasons upsert; the deck_outcomes row is now pass-once too."""
    client, _service, _svc, eng = harness
    _post(client, _reason({"reason": "value"}))
    _post(client, _reason({"reason": "value"}))
    rows = _outcome_rows(eng)
    assert [r.action for r in rows] == ["pass"]


# ---------------------------------------------------------------------------
# Progressive writes (SPEC §3)
# ---------------------------------------------------------------------------

def test_layer1_alone_leaves_a_complete_row(harness):
    """The non-negotiable one: a tester who taps a tile and stops has
    passed the card AND told us why, in one gesture."""
    client, _service, trade_svc, eng = harness
    r = _post(client, _reason({"reason": "value"}))
    assert r.status_code == 200
    body = r.get_json()
    assert body["passed"] is True
    assert body["reason"] == "value" and body["detail"] is None

    row = load_trade_pass_reason(IMP)
    assert row["reason"] == "value"
    assert row["detail"] is None
    assert row["switched_from"] is None
    assert row["user_id"] == ME and row["league_id"] == LEAGUE
    assert row["trade_id"] == TRADE
    assert row["created_at"] and row["updated_at"]

    # The disposition rode along: trade_decisions + a deck_outcomes 'pass'.
    decisions = _decision_rows(eng)
    assert len(decisions) == 1 and decisions[0].decision == "pass"
    with eng.connect() as conn:
        outcomes = conn.execute(
            select(db_module.deck_outcomes_table)).fetchall()
    assert [o.action for o in outcomes] == ["pass"]
    # …and the in-memory card is marked passed, exactly as the ✕ marked it.
    assert trade_svc._trade_cards[TRADE].decision == "pass"


def test_layer1_then_layer2_keeps_both(harness):
    client, _service, _svc, eng = harness
    _post(client, _reason({"reason": "value"}))
    r = _post(client, _reason({"detail": "value_getting"}))
    assert r.status_code == 200
    assert r.get_json()["passed"] is False      # the pass already happened

    row = load_trade_pass_reason(IMP)
    assert row["reason"] == "value"             # layer 1 NOT lost
    assert row["detail"] == "value_getting"
    assert _row_count(eng) == 1                 # one row per impression
    assert len(_decision_rows(eng)) == 1        # passed exactly once


def test_other_then_text_upgrades_without_losing_the_code(harness):
    """SPEC §3.3 — 'Other' writes its code BEFORE the box opens, so a
    tester who opens the box and bails still leaves 'none of the listed
    reasons'; the text then upgrades the same row."""
    client, _service, _svc, eng = harness
    _post(client, _reason({"reason": "fit"}))
    _post(client, _reason({"detail": "fit_other"}))
    assert load_trade_pass_reason(IMP)["detail"] == "fit_other"
    assert load_trade_pass_reason(IMP)["free_text"] is None

    _post(client, _reason({"detail": "fit_other", "text": "  roster is full  "}))
    row = load_trade_pass_reason(IMP)
    assert row["reason"] == "fit"
    assert row["detail"] == "fit_other"
    assert row["free_text"] == "roster is full"     # trimmed, stored here only
    assert _row_count(eng) == 1


def test_neither_tile_free_text_lands_as_other_text(harness):
    client, _service, _svc, _eng = harness
    _post(client, _reason({"reason": "other"}))
    assert load_trade_pass_reason(IMP)["detail"] is None
    _post(client, _reason({"reason": "other", "text": "just a bad vibe"}))
    row = load_trade_pass_reason(IMP)
    assert row["reason"] == "other"
    assert row["detail"] == "other_text"
    assert row["free_text"] == "just a bad vibe"


# ---------------------------------------------------------------------------
# Player preference under "Neither" (SPEC §2 amendment 2026-08-19, D-080)
# ---------------------------------------------------------------------------
# The "Neither" tile was free-text-only and became 47% of the first production
# burst, almost all of it one un-coded reason: "I don't want to trade THIS
# player". It now carries two structured codes. These tests pin the pair as a
# PAIR — a refactor that collapses them into one code, or reparents either to
# `value`, fails here.

_PLAYER_PREF = ("other_player_keep", "other_player_avoid")


@pytest.mark.parametrize("detail", _PLAYER_PREF)
def test_player_preference_codes_are_children_of_other(harness, detail):
    """Both live under "Neither" — not under Value, which is the tempting
    mis-parent for `other_player_keep` ("won't give up my guy")."""
    assert db_module.PASS_REASON_PARENT[detail] == "other"
    assert detail in db_module.PASS_REASON_LAYER2["other"]

    client, _service, _svc, eng = harness
    r = _post(client, _reason({"reason": "other", "detail": detail}))
    assert r.status_code == 200, r.get_json()
    row = load_trade_pass_reason(IMP)
    assert row["reason"] == "other"
    assert row["detail"] == detail
    assert row["free_text"] is None          # a fixed option, never a text row
    assert _row_count(eng) == 1


@pytest.mark.parametrize("detail", _PLAYER_PREF)
@pytest.mark.parametrize("wrong", ["value", "fit"])
def test_player_preference_rejects_a_foreign_layer1(harness, detail, wrong):
    client, _service, _svc, eng = harness
    r = _post(client, _reason({"reason": wrong, "detail": detail}))
    assert r.status_code == 400
    assert r.get_json()["error"] == "detail_reason_mismatch"
    assert _row_count(eng) == 0


@pytest.mark.parametrize("detail", _PLAYER_PREF)
def test_player_preference_arriving_alone_still_names_its_reason(harness, detail):
    """Layer-2-first (dropped layer-1 request, app restart): the row must
    derive `reason='other'` from the prefix rather than store a half row."""
    client, _service, _svc, _eng = harness
    _post(client, _reason({"detail": detail}))
    row = load_trade_pass_reason(IMP)
    assert row["reason"] == "other"
    assert row["detail"] == detail


def test_player_preference_is_distinguishable_from_plain_neither_free_text(harness):
    """The whole point of the amendment: the two directions and the residual
    free text are three different stored answers, not one bucket."""
    client, _service, trade_svc, _eng = harness
    seen = {}
    for i, detail in enumerate(_PLAYER_PREF + ("other_text",)):
        tid = f"pref_trade_{i}"
        trade_svc._trade_cards[tid] = TradeCard(
            trade_id=tid, league_id=LEAGUE, proposing_user_id=ME,
            target_user_id=OPP, target_username="opp",
            give_player_ids=["g1"], receive_player_ids=["r1"],
            mismatch_score=0.0, fairness_score=0.0, composite_score=0.0,
        )
        _seed_impression(f"pref_imp_{i}", tid, card_index=i + 1)
        body = {"trade_id": tid, "impression_id": f"pref_imp_{i}",
                "reason": "other", "detail": detail}
        if detail == "other_text":
            body["text"] = "some other thing entirely"
        assert _post(client, body).status_code == 200
        seen[detail] = load_trade_pass_reason(f"pref_imp_{i}")["detail"]
    assert seen == {"other_player_keep": "other_player_keep",
                    "other_player_avoid": "other_player_avoid",
                    "other_text": "other_text"}


def test_switching_tiles_records_switched_from_and_keeps_the_first_answer(harness):
    """SPEC §3 — switching is a refinement, not a reset."""
    client, _service, _svc, eng = harness
    _post(client, _reason({"reason": "value"}))
    _post(client, _reason({"detail": "value_giving"}))
    r = _post(client, _reason({"reason": "fit"}))
    assert r.status_code == 200
    assert r.get_json()["switched_from"] == "value"

    row = load_trade_pass_reason(IMP)
    assert row["reason"] == "fit"
    assert row["switched_from"] == "value"
    assert row["detail"] == "value_giving"      # NOT wiped — never lose a write
    assert len(_decision_rows(eng)) == 1        # still one pass


def test_switching_twice_names_the_most_recent_prior(harness):
    client, _service, _svc, _eng = harness
    _post(client, _reason({"reason": "value"}))
    _post(client, _reason({"reason": "fit"}))
    _post(client, _reason({"reason": "other"}))
    row = load_trade_pass_reason(IMP)
    assert row["reason"] == "other"
    assert row["switched_from"] == "fit"


def test_retapping_the_same_tile_is_a_no_op_pass_wise(harness):
    client, _service, _svc, eng = harness
    _post(client, _reason({"reason": "value"}))
    r = _post(client, _reason({"reason": "value"}))
    assert r.get_json()["passed"] is False
    assert load_trade_pass_reason(IMP)["switched_from"] is None
    assert len(_decision_rows(eng)) == 1
    assert _row_count(eng) == 1


def test_layer2_arriving_first_still_passes_and_names_its_reason(harness):
    """A dropped layer-1 request (or an app restart mid-flow) must not cost
    us the pass: the first write for an impression is always the pass, and
    a layer-2 code implies its parent."""
    client, _service, _svc, eng = harness
    r = _post(client, _reason({"detail": "fit_duplicate"}))
    assert r.get_json()["passed"] is True
    row = load_trade_pass_reason(IMP)
    assert row["reason"] == "fit"
    assert row["detail"] == "fit_duplicate"
    assert len(_decision_rows(eng)) == 1


def test_two_impressions_are_two_rows(harness):
    client, _service, trade_svc, eng = harness
    other = TradeCard(
        trade_id="trade_two", league_id=LEAGUE, proposing_user_id=ME,
        target_user_id=OPP, target_username="opp",
        give_player_ids=["g2"], receive_player_ids=["r2"],
        mismatch_score=0.0, fairness_score=0.0, composite_score=0.0,
    )
    trade_svc._trade_cards["trade_two"] = other
    _seed_impression("imp_two", "trade_two", card_index=1)
    _post(client, _reason({"reason": "value"}))
    _post(client, {"trade_id": "trade_two", "impression_id": "imp_two",
                   "reason": "fit"})
    assert _row_count(eng) == 2
    assert load_trade_pass_reason("imp_two")["reason"] == "fit"


def test_missing_impression_id_still_records_both(harness):
    """Operator decision 2026-08-17 — a client that sends no `impression_id`
    (deck.signal_v2 off, or a legacy card) must still be RECORDED, never
    refused. The surrogate key keeps the pass AND the reason."""
    client, _service, _svc, eng = harness
    r = _post(client, {"trade_id": TRADE, "reason": "value"})
    assert r.status_code == 200 and r.get_json()["passed"] is True
    row = load_trade_pass_reason(f"local:{ME}:{TRADE}")
    assert row["reason"] == "value"
    assert row["key_source"] == "local"      # degraded-but-recorded, marked
    assert len(_decision_rows(eng)) == 1


def test_key_source_marks_impression_linked_rows(harness):
    """The two paths must be tellable apart in analysis without inferring
    anything from the key's shape: only `impression` rows join the F1 spine
    and are usable for off-policy evaluation."""
    client, _service, _svc, _eng = harness
    _post(client, _reason({"reason": "value"}))
    assert load_trade_pass_reason(IMP)["key_source"] == "impression"


def test_key_source_is_not_rewritten_by_later_taps(harness):
    """The key a row was minted under is a fact about the row, not a field a
    later tap gets to revise."""
    client, _service, _svc, _eng = harness
    _post(client, {"trade_id": TRADE, "reason": "value"})           # local
    _post(client, {"trade_id": TRADE, "impression_id": IMP,
                   "detail": "value_giving"})                        # imp key
    assert load_trade_pass_reason(f"local:{ME}:{TRADE}")["key_source"] == "local"


def test_signal_v2_off_uses_the_surrogate_even_with_an_id(harness):
    """With no F1 spine the id is unverifiable, so it does not get to be a
    key — but the answer is still recorded."""
    client, _service, _svc, eng = harness
    with patch.object(server, "_deck_signal_v2_enabled", lambda: False):
        r = _post(client, _reason({"reason": "fit"}))
    assert r.status_code == 200
    assert load_trade_pass_reason(IMP) is None
    row = load_trade_pass_reason(f"local:{ME}:{TRADE}")
    assert row["reason"] == "fit" and row["key_source"] == "local"
    assert len(_decision_rows(eng)) == 1


def test_foreign_impression_id_never_becomes_a_key(harness):
    """A client-supplied impression_id belonging to someone else must not
    key this user's row (the 2026-08-14 ownership fix). The answer is still
    banked — under the caller's own surrogate key."""
    client, _service, _svc, eng = harness
    _seed_impression("imp_theirs", "trade_theirs", user_id=OPP, card_index=9)
    r = _post(client, {"trade_id": TRADE, "impression_id": "imp_theirs",
                       "reason": "value"})
    assert r.status_code == 200
    assert load_trade_pass_reason("imp_theirs") is None
    assert load_trade_pass_reason(f"local:{ME}:{TRADE}")["reason"] == "value"


def test_unknown_impression_id_never_becomes_a_key(harness):
    client, _service, _svc, _eng = harness
    r = _post(client, {"trade_id": TRADE, "impression_id": "imp_nope",
                       "reason": "fit"})
    assert r.status_code == 200
    assert load_trade_pass_reason("imp_nope") is None
    assert load_trade_pass_reason(f"local:{ME}:{TRADE}")["reason"] == "fit"


# ---------------------------------------------------------------------------
# Validation — junk codes are refused, never stored
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("body,err", [
    ({"impression_id": IMP, "reason": "value"},          "missing_field"),   # no trade_id
    ({"trade_id": TRADE, "impression_id": IMP},          "missing_field"),   # nothing to write
    ({"trade_id": TRADE, "impression_id": IMP, "reason": "price"},
     "invalid_reason"),
    ({"trade_id": TRADE, "impression_id": IMP, "detail": "value_meh"},
     "invalid_detail"),
    ({"trade_id": TRADE, "impression_id": IMP,
      "reason": "fit", "detail": "value_giving"}, "detail_reason_mismatch"),
    ({"trade_id": TRADE, "impression_id": IMP, "text": 17}, "invalid_text"),
])
def test_invalid_payloads_are_400s_and_write_nothing(harness, body, err):
    client, _service, _svc, eng = harness
    r = _post(client, body)
    assert r.status_code == 400
    assert r.get_json()["error"] == err
    assert _row_count(eng) == 0
    assert _decision_rows(eng) == []


def test_mobile_payload_shape_is_accepted_verbatim(harness):
    """The exact body `feat/decline-reasons-mobile` sends — including the
    fields this route derives for itself (`layer`, client `switched_from`)
    and its `free_text` spelling. Nothing here may 400, and nothing may be
    silently dropped."""
    client, _service, _svc, eng = harness
    r1 = _post(client, {"trade_id": TRADE, "impression_id": IMP,
                        "league_id": LEAGUE, "layer": 1, "reason": "value",
                        "switched_from": "none"})
    assert r1.status_code == 200, r1.get_json()
    assert r1.get_json()["passed"] is True

    r2 = _post(client, {"trade_id": TRADE, "impression_id": IMP,
                        "league_id": LEAGUE, "layer": 2, "reason": "value",
                        "detail": "value_other", "switched_from": "none",
                        "free_text": "priced off my own board"})
    assert r2.status_code == 200, r2.get_json()
    row = load_trade_pass_reason(IMP)
    assert row["reason"] == "value"
    assert row["detail"] == "value_other"
    assert row["free_text"] == "priced off my own board"
    assert len(_decision_rows(eng)) == 1


def test_text_is_accepted_as_an_alias_for_free_text(harness):
    client, _service, _svc, _eng = harness
    _post(client, _reason({"reason": "other", "text": "via the alias"}))
    assert load_trade_pass_reason(IMP)["free_text"] == "via the alias"


def test_client_switched_from_is_ignored_in_favour_of_the_stored_row(harness):
    """Derived server-side so it can never disagree with the row it
    describes — a lying client cannot forge a switch that did not happen."""
    client, _service, _svc, _eng = harness
    _post(client, _reason({"reason": "value", "switched_from": "fit"}))
    assert load_trade_pass_reason(IMP)["switched_from"] is None


def test_free_text_is_capped_at_storage(harness):
    client, _service, _svc, _eng = harness
    _post(client, _reason({"reason": "other", "text": "x" * 900}))
    assert len(load_trade_pass_reason(IMP)["free_text"]) == \
        db_module.PASS_REASON_TEXT_MAX


def test_every_specced_code_is_accepted(harness):
    """SPEC §2's taxonomy, exactly — no code missing, no code invented."""
    assert db_module.PASS_REASON_LAYER1 == ("value", "fit", "other")
    assert set(db_module.PASS_REASON_PARENT) == {
        "value_giving", "value_getting", "value_other",
        "fit_outlook", "fit_new_weakness", "fit_duplicate", "fit_other",
        "other_player_keep", "other_player_avoid", "other_text",
    }
    client, _service, trade_svc, _eng = harness
    for i, detail in enumerate(sorted(db_module.PASS_REASON_PARENT)):
        tid = f"trade_{i}"
        trade_svc._trade_cards[tid] = TradeCard(
            trade_id=tid, league_id=LEAGUE, proposing_user_id=ME,
            target_user_id=OPP, target_username="opp",
            give_player_ids=["g1"], receive_player_ids=["r1"],
            mismatch_score=0.0, fairness_score=0.0, composite_score=0.0,
        )
        _seed_impression(f"imp_{i}", tid, card_index=i + 1)
        r = _post(client, {"trade_id": tid, "impression_id": f"imp_{i}",
                           "detail": detail})
        assert r.status_code == 200, (detail, r.get_json())
        assert load_trade_pass_reason(f"imp_{i}")["detail"] == detail


# ---------------------------------------------------------------------------
# Elo suppression (SPEC §4) — the full per-code matrix, knob ON and OFF
# ---------------------------------------------------------------------------

# (writes as the terminal layer-2 answer under the default knob)
_ELO_MATRIX = [
    ("value_giving",     True),    # the user DID say their side is worth more
    ("value_getting",    False),   # they said the opposite — writing inverts it
    ("value_other",      False),
    ("fit_outlook",      False),
    ("fit_new_weakness", False),
    ("fit_duplicate",    False),
    ("fit_other",        False),
    # SPEC §2 amendment 2026-08-19 (D-080). `other_player_keep` is the
    # near-miss: "won't trade one of my players" LOOKS like value_giving but
    # it is attachment, not a price claim — "not this player at any price"
    # is the opposite of a statement about price. Both suppress.
    ("other_player_keep", False),
    ("other_player_avoid", False),
    ("other_text",       False),
]


@pytest.mark.parametrize("detail,writes", _ELO_MATRIX)
def test_elo_matrix_knob_on(harness, detail, writes):
    client, service, _svc, eng = harness
    parent = db_module.PASS_REASON_PARENT[detail]
    with _knob(1.0):
        _post(client, _reason({"reason": parent}))
        # Layer 1 alone NEVER writes Elo under the rule — no valuation claim.
        assert _swipe_rows(eng) == []
        assert service._trade_swipes == []
        _post(client, _reason({"detail": detail}))

    rows = _swipe_rows(eng)
    assert bool(rows) is writes
    assert bool(service._trade_swipes) is writes
    if writes:
        assert (rows[0].winner_player_id, rows[0].loser_player_id) == ("g1", "r1")
        assert load_trade_pass_reason(IMP)["elo_signal_at"]
    else:
        assert load_trade_pass_reason(IMP)["elo_signal_at"] is None
    # The DISPOSITION is written either way — suppression is about ranking
    # math, never about whether the pass happened.
    assert len(_decision_rows(eng)) == 1


@pytest.mark.parametrize("detail,_writes", _ELO_MATRIX)
def test_elo_matrix_knob_off_every_code_writes(harness, detail, _writes):
    """The kill switch: with `pass_reason_elo_suppression` at 0 every
    reasoned pass writes Elo at the layer-1 tap, exactly like today's ✕."""
    client, service, _svc, eng = harness
    parent = db_module.PASS_REASON_PARENT[detail]
    with _knob(0.0):
        _post(client, _reason({"reason": parent}))
        assert len(_swipe_rows(eng)) == 1
        assert len(service._trade_swipes) == 1
        _post(client, _reason({"detail": detail}))
    # …and only once: the layer-2 write cannot double-count the same pass.
    assert len(_swipe_rows(eng)) == 1
    assert len(service._trade_swipes) == 1


def test_layer1_only_suppresses_under_every_reason(harness):
    """A tester who never opens layer 2 has made no value claim, whichever
    tile they tapped."""
    client, service, trade_svc, eng = harness
    with _knob(1.0):
        for i, reason in enumerate(db_module.PASS_REASON_LAYER1):
            tid = f"trade_l1_{i}"
            trade_svc._trade_cards[tid] = TradeCard(
                trade_id=tid, league_id=LEAGUE, proposing_user_id=ME,
                target_user_id=OPP, target_username="opp",
                give_player_ids=["g1"], receive_player_ids=["r1"],
                mismatch_score=0.0, fairness_score=0.0, composite_score=0.0,
            )
            _seed_impression(f"imp_l1_{i}", tid, card_index=i + 1)
            _post(client, {"trade_id": tid, "impression_id": f"imp_l1_{i}",
                           "reason": reason})
    assert _swipe_rows(eng) == []
    assert service._trade_swipes == []
    assert len(_decision_rows(eng)) == 3


def test_value_giving_writes_elo_exactly_once_across_retries(harness):
    """claim_trade_pass_elo is the once-only guard: re-taps and client
    retries cannot double-count one pass into the ranking math."""
    client, service, _svc, eng = harness
    with _knob(1.0):
        _post(client, _reason({"reason": "value"}))
        _post(client, _reason({"detail": "value_giving"}))
        _post(client, _reason({"detail": "value_giving"}))
        _post(client, _reason({"detail": "value_giving", "text": "ignored"}))
    assert len(_swipe_rows(eng)) == 1
    assert len(service._trade_swipes) == 1


def test_switching_away_from_value_giving_does_not_re_write_elo(harness):
    """Documented one-way behavior: the Elo signal a `value_giving` answer
    earned is not retracted when the tester later switches tiles (there is
    no negative-K correction path on this route). It must at least never
    write a SECOND time."""
    client, service, _svc, eng = harness
    with _knob(1.0):
        _post(client, _reason({"reason": "value"}))
        _post(client, _reason({"detail": "value_giving"}))
        _post(client, _reason({"reason": "fit"}))
        _post(client, _reason({"detail": "fit_outlook"}))
    assert len(_swipe_rows(eng)) == 1
    assert len(service._trade_swipes) == 1


def test_pass_reason_writes_elo_rule_is_pure(harness):
    """The rule itself, independent of routing."""
    with _knob(1.0):
        assert rs_module.pass_reason_writes_elo("value_giving") is True
        for code in ("value", "fit", "other", "value_getting", "value_other",
                     "fit_outlook", "fit_new_weakness", "fit_duplicate",
                     "fit_other", "other_player_keep", "other_player_avoid",
                     "other_text", None, ""):
            assert rs_module.pass_reason_writes_elo(code) is False, code
    with _knob(0.0):
        for code in ("value", "value_getting", "fit_other", None, ""):
            assert rs_module.pass_reason_writes_elo(code) is True, code


def test_knob_default_is_on():
    assert rs_module._DEFAULT_CFG["pass_reason_elo_suppression"] == 1.0
    assert rs_module.PASS_REASON_ELO_KEEP == frozenset({"value_giving"})


# ---------------------------------------------------------------------------
# Analytics registration (SPEC §6)
# ---------------------------------------------------------------------------

_SHARED_PROPS = {"impression_id", "trade_id", "ms_since_render", "platform"}


def test_both_events_are_registered_client_side():
    for name in ("trade_pass_layer1", "trade_pass_layer2"):
        assert name in ALLOWED_CLIENT_EVENTS, name
        assert name in CLIENT_EVENT_PROPS, name
        assert name not in SERVER_FIRED_EVENTS, name


def test_layer1_props_are_exactly_the_spec():
    assert CLIENT_EVENT_PROPS["trade_pass_layer1"] == frozenset(
        {"reason", "switched_from"} | _SHARED_PROPS)


def test_layer2_props_are_exactly_the_spec():
    assert CLIENT_EVENT_PROPS["trade_pass_layer2"] == frozenset(
        {"reason", "detail", "has_free_text", "switched_from"} | _SHARED_PROPS)


def test_no_free_text_prop_exists_anywhere_in_the_family():
    """SPEC §3.4 — free text is stored on the row and is never an analytics
    property. `has_free_text` is a boolean; nothing carries the text."""
    for name in ("trade_pass_layer1", "trade_pass_layer2"):
        for prop in CLIENT_EVENT_PROPS[name]:
            assert prop not in ("text", "free_text", "other_text", "comment"), \
                (name, prop)


def test_route_never_records_free_text_in_an_event(harness):
    """Belt and braces on the server side: whatever the route emits, no
    event property may carry the tester's words."""
    client, _service, _svc, _eng = harness
    with patch.object(server, "record_event") as rec:
        _post(client, _reason({"reason": "other",
                               "text": "secret words here"}))
    for call in rec.call_args_list:
        blob = json.dumps(call.kwargs.get("props") or {})
        assert "secret words here" not in blob
