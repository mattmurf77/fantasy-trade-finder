"""Trade-relevance P0-3 (B5) — the disposition join spine.

docs/plans/trade-relevance-engine/lld.md §2.1, §4.3–4.5, §5 E4/E5/E6,
§7 T-6/T-7/T-9; HLD D2.

Sabotage-proven structural tests (house convention, LLD §7): every test names
the sabotage that must make it fail. Review checks the sabotage list, not the
green run.

THE SIDE-BINDING under test, quoted from `create_trade_match`'s docstring:
    "user_a is the user whose swipe *triggered* the match detection
     (i.e. the current user who just swiped 'like').
     user_b is the counterparty who had already swiped 'like' earlier."
So side A's impression is exact-by-construction (it rode in on the triggering
swipe) and side B's is recovered off the earlier like row, inheriting the
match's own fuzziness. Get this backwards and every accept/decline label in
the training spine is attributed to the wrong card — silently.

Covers:
  T-6  label attribution, the full 2×2 {A disposes, B disposes} ×
       {accept, decline}: first person on the DISPOSING user's impression,
       `_by_partner` on the counterpart's, exactly 2 rows on 2 different
       impressions, `source_match_id` set
  T-7  atomicity: a forced outcome-insert failure rolls the decision back
  T-9  idempotency: replay writes 0 rows; a conflicting decision 409s with
       0 rows
  plus join_quality_b exact/fuzzy/NULL, the unlabelled-side rules, and the
  swipe-time validated-id thread (`_save_deck_outcome_safe` → the like row).
"""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, insert, select, text

import backend.database as db_module
import backend.server as server
from backend.database import (
    create_trade_match,
    deck_impressions_table,
    deck_outcomes_table,
    find_matching_like,
    check_for_match,
    metadata,
    record_match_disposition,
    save_trade_decision,
    trade_decisions_table,
    trade_matches_table,
)
from backend.ranking_service import Player, RankingService
from backend.trade_service import League, LeagueMember


LEAGUE = "league_join"
USER_A = "user_a_trigger"   # the swiper whose like TRIGGERED the match
USER_B = "user_b_earlier"   # the counterparty who liked EARLIER
GIVE = ["g1", "g2"]         # from user_a's perspective
RECEIVE = ["r1", "r2"]

IMP_A = "imp-side-a"
IMP_B = "imp-side-b"


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def mem_engine():
    """Fresh in-memory SQLite with the full schema, patched in as the
    module-level engine so every database.py function uses it."""
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db_module, "engine", eng):
        yield eng


def _plant_impression(eng, impression_id, user_id, *, age_days=0.0):
    served = (datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat()
    with eng.begin() as conn:
        conn.execute(insert(deck_impressions_table).values(
            impression_id = impression_id,
            user_id       = user_id,
            league_id     = LEAGUE,
            deck_job_id   = f"job-{impression_id}",
            card_index    = 0,
            trade_hash    = "hash-1",
            features_json = "{}",
            propensity    = 1.0,
            served_at     = served,
        ))


def _plant_match(eng, *, impression_id_a=IMP_A, impression_id_b=IMP_B,
                 join_quality_b="exact", a_decision=None, b_decision=None):
    with eng.begin() as conn:
        res = conn.execute(insert(trade_matches_table).values(
            league_id       = LEAGUE,
            user_a_id       = USER_A,
            user_b_id       = USER_B,
            user_a_give     = json.dumps(GIVE),
            user_a_receive  = json.dumps(RECEIVE),
            matched_at      = "2026-08-01T00:00:00+00:00",
            status          = "pending",
            user_a_decision = a_decision,
            user_b_decision = b_decision,
            impression_id_a = impression_id_a,
            impression_id_b = impression_id_b,
            join_quality_b  = join_quality_b,
        ))
        return res.inserted_primary_key[0]


def _outcomes(eng):
    with eng.connect() as conn:
        rows = conn.execute(
            select(deck_outcomes_table).order_by(deck_outcomes_table.c.id)
        ).fetchall()
    return [dict(r._mapping) for r in rows]


def _decisions(eng, match_id):
    with eng.connect() as conn:
        return conn.execute(
            select(trade_matches_table.c.user_a_decision,
                   trade_matches_table.c.user_b_decision)
            .where(trade_matches_table.c.id == match_id)
        ).fetchone()


# ---------------------------------------------------------------------------
# T-6 — label attribution, the full 2×2
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("actor,decision,self_label,partner_label", [
    # A disposes → A's own impression is first person, B's is _by_partner.
    (USER_A, "accept",  "accepted", "accepted_by_partner"),
    (USER_A, "decline", "declined", "declined_by_partner"),
    # B disposes → the binding FLIPS: B's impression is first person now.
    (USER_B, "accept",  "accepted", "accepted_by_partner"),
    (USER_B, "decline", "declined", "declined_by_partner"),
])
def test_t6_label_attribution_2x2(mem_engine, actor, decision,
                                  self_label, partner_label):
    """T-6. The disposing actor's OWN impression gets the first-person label;
    the counterpart's gets `_by_partner`. Exactly two rows, on two different
    impressions, both stamped with source_match_id.

    SABOTAGE: swap `_DISPOSITION_SELF_LABEL` and `_DISPOSITION_PARTNER_LABEL`
    (or swap the my_imp/partner_imp binding in record_match_disposition) and
    two of these four cells fail — the labels land on the wrong user's card.
    """
    _plant_impression(mem_engine, IMP_A, USER_A)
    _plant_impression(mem_engine, IMP_B, USER_B)
    match_id = _plant_match(mem_engine)

    actor_imp   = IMP_A if actor == USER_A else IMP_B
    partner_imp = IMP_B if actor == USER_A else IMP_A

    result = record_match_disposition(match_id, actor, decision,
                                      write_outcomes=True)

    assert result["status"] == "ok"
    assert result["my_impression_id"] == actor_imp
    assert result["partner_impression_id"] == partner_imp
    assert result["outcome_rows_written"] == 2

    rows = _outcomes(mem_engine)
    assert len(rows) == 2, "one disposition event ⇒ exactly two label rows"
    by_imp = {r["impression_id"]: r for r in rows}
    assert set(by_imp) == {actor_imp, partner_imp}, \
        "the two labels must land on two DIFFERENT impressions (no double-count)"
    assert by_imp[actor_imp]["action"] == self_label
    assert by_imp[partner_imp]["action"] == partner_label
    assert all(r["source_match_id"] == match_id for r in rows)
    # Side A is exact by construction; side B carries the match's stored quality.
    assert by_imp[IMP_A]["join_quality"] == "exact"
    assert by_imp[IMP_B]["join_quality"] == "exact"


def test_t6_flag_off_writes_no_labels(mem_engine):
    """The label write is gated on write_outcomes (deck.signal_v2 at the
    route). Flag off ⇒ decision recorded, zero labels.

    SABOTAGE: drop the `if write_outcomes:` guard — this fails.
    """
    _plant_impression(mem_engine, IMP_A, USER_A)
    _plant_impression(mem_engine, IMP_B, USER_B)
    match_id = _plant_match(mem_engine)

    result = record_match_disposition(match_id, USER_A, "accept")

    assert result["status"] == "ok"
    assert result["outcome_rows_written"] == 0
    assert _outcomes(mem_engine) == []
    assert _decisions(mem_engine, match_id).user_a_decision == "accept"


def test_t6_elo_semantics_untouched_by_labels(mem_engine):
    """Labels are additive: the both-decided ELO payload is unchanged.

    SABOTAGE: fold the label write into the ELO branch (so it only fires on
    both_decided), or let it mutate elo_signals — this fails.
    """
    _plant_impression(mem_engine, IMP_A, USER_A)
    _plant_impression(mem_engine, IMP_B, USER_B)
    match_id = _plant_match(mem_engine, a_decision="accept")

    result = record_match_disposition(match_id, USER_B, "accept",
                                      write_outcomes=True)

    assert result["both_decided"] is True
    assert result["outcome"] == "accepted"
    assert [s["user_id"] for s in result["elo_signals"]] == [USER_A, USER_B]
    for sig in result["elo_signals"]:
        assert sig["decision_type"] == "disposition"
        assert sig["k_factor"] > 0
    assert result["outcome_rows_written"] == 2


# ---------------------------------------------------------------------------
# T-7 — atomicity
# ---------------------------------------------------------------------------

def test_t7_outcome_insert_failure_rolls_back_the_decision(mem_engine):
    """T-7. Decision + labels are one transaction. Force the outcome INSERT
    to raise ⇒ the decision column must be rolled back with it.

    SABOTAGE: move the label writes out of `record_match_disposition`'s
    `engine.begin()` block (e.g. to the route, or a second txn) — the
    decision would survive the failure and this fails.
    """
    _plant_impression(mem_engine, IMP_A, USER_A)
    _plant_impression(mem_engine, IMP_B, USER_B)
    match_id = _plant_match(mem_engine)

    # The ONLY insert() inside record_match_disposition is the outcome write.
    boom = MagicMock(side_effect=RuntimeError("forced outcome-insert failure"))
    with patch.object(db_module, "insert", boom):
        with pytest.raises(RuntimeError):
            record_match_disposition(match_id, USER_A, "accept",
                                     write_outcomes=True)

    assert boom.called, "the sabotage never reached the outcome insert"
    row = _decisions(mem_engine, match_id)
    assert row.user_a_decision is None, "decision must roll back with the labels"
    assert row.user_b_decision is None
    assert _outcomes(mem_engine) == []


# ---------------------------------------------------------------------------
# T-9 — idempotency / conflict
# ---------------------------------------------------------------------------

def test_t9_same_decision_twice_writes_zero_rows_the_second_time(mem_engine):
    """T-9. Replay of the SAME decision ⇒ already_decided, 0 new label rows.

    SABOTAGE: write labels before the `already_decided` short-circuit — the
    second call would duplicate both rows and this fails.
    """
    _plant_impression(mem_engine, IMP_A, USER_A)
    _plant_impression(mem_engine, IMP_B, USER_B)
    match_id = _plant_match(mem_engine)

    first = record_match_disposition(match_id, USER_A, "accept",
                                     write_outcomes=True)
    assert first["outcome_rows_written"] == 2

    second = record_match_disposition(match_id, USER_A, "accept",
                                      write_outcomes=True)
    assert second["status"] == "already_decided"
    assert second["existing_decision"] == "accept"
    assert second["outcome_rows_written"] == 0
    assert len(_outcomes(mem_engine)) == 2


def test_t9_preinsert_guard_survives_a_replay_racing_the_first_commit(mem_engine):
    """E4. The state machine makes re-disposal unreachable, so the
    `(impression_id, action, source_match_id)` existence check exists for the
    replay that races the first commit. Plant the row that race would have
    written and assert the guard suppresses the duplicate.

    SABOTAGE: delete the pre-insert SELECT — a duplicate `accepted` row on
    IMP_A appears and this fails.
    """
    _plant_impression(mem_engine, IMP_A, USER_A)
    _plant_impression(mem_engine, IMP_B, USER_B)
    match_id = _plant_match(mem_engine)
    with mem_engine.begin() as conn:
        conn.execute(insert(deck_outcomes_table).values(
            impression_id   = IMP_A,
            action          = "accepted",
            acted_at        = "2026-08-01T00:00:00+00:00",
            join_quality    = "exact",
            source_match_id = match_id,
        ))

    result = record_match_disposition(match_id, USER_A, "accept",
                                      write_outcomes=True)

    assert result["outcome_rows_written"] == 1, "only the un-raced side writes"
    rows = _outcomes(mem_engine)
    assert len(rows) == 2
    assert sum(1 for r in rows
               if r["impression_id"] == IMP_A and r["action"] == "accepted") == 1


def test_t9_conflicting_decision_409s_with_zero_rows(mem_engine):
    """T-9, second half. A CONFLICTING decision is still a 409 at the route
    and writes no labels. The whole already_decided / conflict state machine
    is untouched by P0-3.

    SABOTAGE: label on the already_decided path, or relax the 409 — fails.
    """
    _plant_impression(mem_engine, IMP_A, USER_A)
    _plant_impression(mem_engine, IMP_B, USER_B)
    match_id = _plant_match(mem_engine)

    record_match_disposition(match_id, USER_A, "accept", write_outcomes=True)
    before = len(_outcomes(mem_engine))

    with _route_harness(mem_engine, as_user=USER_A) as (client, token):
        resp = client.post(
            f"/api/trades/matches/{match_id}/disposition",
            headers={"X-Session-Token": token,
                     "Content-Type": "application/json"},
            data=json.dumps({"decision": "decline"}),
        )

    assert resp.status_code == 409, resp.get_data(as_text=True)
    assert len(_outcomes(mem_engine)) == before == 2


# ---------------------------------------------------------------------------
# Exact vs fuzzy vs unlabelled — side B's provenance
# ---------------------------------------------------------------------------

def _like(user_id, give, receive, *, impression_id=None):
    save_trade_decision(
        user_id            = user_id,
        league_id          = LEAGUE,
        trade_id           = f"t-{user_id}-{len(give)}{len(receive)}",
        give_player_ids    = give,
        receive_player_ids = receive,
        decision           = "like",
        impression_id      = impression_id,
    )


def test_exact_mirror_with_stored_impression_yields_exact_join(mem_engine):
    """B liked the exact mirror and their like row carries an impression ⇒
    impression_id_b set, join_quality_b='exact'.

    SABOTAGE: hard-code join_quality_b='fuzzy', or stop persisting
    impression_id in save_trade_decision — this fails.
    """
    _like(USER_B, RECEIVE, GIVE, impression_id=IMP_B)

    mirror = find_matching_like(USER_A, LEAGUE, USER_B, GIVE, RECEIVE)
    assert mirror is not None and mirror["exact"] is True
    assert mirror["impression_id"] == IMP_B

    match = create_trade_match(
        LEAGUE, USER_A, USER_B, GIVE, RECEIVE,
        impression_id_a = IMP_A,
        impression_id_b = mirror["impression_id"],
        join_quality_b  = ("exact" if mirror["exact"] else "fuzzy"),
    )
    with mem_engine.connect() as conn:
        row = conn.execute(select(trade_matches_table).where(
            trade_matches_table.c.id == match["id"])).fetchone()
    assert row.impression_id_a == IMP_A
    assert row.impression_id_b == IMP_B
    assert row.join_quality_b == "exact"


def test_fuzzy_mirror_join_is_born_fuzzy(mem_engine):
    """A `trade.fuzzy_match` mirror cannot share a trade_hash, so side B's
    join inherits the match's own fuzziness even though the impression id is
    exactly the one on the like row.

    SABOTAGE: derive join_quality_b from "did we find an impression?" instead
    of from the match's exactness ⇒ this reads 'exact' and fails.
    """
    # Low-consensus filler `f9` differs; everything else mirrors.
    with mem_engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO players (player_id, full_name, position, search_rank) "
            "VALUES ('f9', 'Filler Nine', 'WR', 400)"))
    _like(USER_B, RECEIVE, GIVE + ["f9"], impression_id=IMP_B)

    assert find_matching_like(USER_A, LEAGUE, USER_B, GIVE, RECEIVE) is None, \
        "no exact mirror exists"
    mirror = find_matching_like(USER_A, LEAGUE, USER_B, GIVE, RECEIVE,
                                fuzzy=True, fuzzy_tau=0.6)
    assert mirror is not None and mirror["exact"] is False
    assert mirror["impression_id"] == IMP_B

    match = create_trade_match(
        LEAGUE, USER_A, USER_B, GIVE, RECEIVE,
        impression_id_a = IMP_A,
        impression_id_b = mirror["impression_id"],
        join_quality_b  = ("exact" if mirror["exact"] else "fuzzy"),
    )
    with mem_engine.connect() as conn:
        row = conn.execute(select(trade_matches_table).where(
            trade_matches_table.c.id == match["id"])).fetchone()
    assert row.join_quality_b == "fuzzy"

    # …and the fuzzy quality rides through to the label on side B.
    _plant_impression(mem_engine, IMP_A, USER_A)
    _plant_impression(mem_engine, IMP_B, USER_B)
    record_match_disposition(match["id"], USER_A, "accept", write_outcomes=True)
    by_imp = {r["impression_id"]: r for r in _outcomes(mem_engine)}
    assert by_imp[IMP_A]["join_quality"] == "exact"
    assert by_imp[IMP_B]["join_quality"] == "fuzzy"


def test_like_row_without_impression_leaves_side_b_null_and_unlabelled(mem_engine):
    """A like row with no impression_id (web, pre-P0-3) ⇒ impression_id_b
    NULL, join_quality_b NULL, and NO side-B label on disposition. Never
    guessed.

    SABOTAGE: fall back to the trade_hash / the partner's newest impression
    at match time — a second label row appears and this fails.
    """
    _like(USER_B, RECEIVE, GIVE)   # no impression_id — the web swipe

    mirror = find_matching_like(USER_A, LEAGUE, USER_B, GIVE, RECEIVE)
    assert mirror is not None and mirror["impression_id"] is None

    _mirror_imp = mirror["impression_id"]
    match = create_trade_match(
        LEAGUE, USER_A, USER_B, GIVE, RECEIVE,
        impression_id_a = IMP_A,
        impression_id_b = _mirror_imp,
        join_quality_b  = (None if not _mirror_imp
                           else "exact" if mirror["exact"] else "fuzzy"),
    )
    with mem_engine.connect() as conn:
        row = conn.execute(select(trade_matches_table).where(
            trade_matches_table.c.id == match["id"])).fetchone()
    assert row.impression_id_b is None
    assert row.join_quality_b is None

    _plant_impression(mem_engine, IMP_A, USER_A)
    result = record_match_disposition(match["id"], USER_A, "accept",
                                      write_outcomes=True)
    assert result["outcome_rows_written"] == 1
    rows = _outcomes(mem_engine)
    assert [(r["impression_id"], r["action"]) for r in rows] == \
        [(IMP_A, "accepted")]


def test_web_swipe_with_no_impression_still_matches_and_disposes(mem_engine):
    """The whole lifecycle for a client that echoes no impression_id at all:
    the like still matches, the match is still created, and BOTH users can
    still dispose — the side is simply unlabelled.

    SABOTAGE: make impression_id required anywhere on the path (a NOT NULL,
    an early return, a raise) — this fails.
    """
    _like(USER_B, RECEIVE, GIVE)   # B: no impression
    mirror = find_matching_like(USER_A, LEAGUE, USER_B, GIVE, RECEIVE)
    match = create_trade_match(
        LEAGUE, USER_A, USER_B, GIVE, RECEIVE,
        impression_id_a = None,    # A: web swipe, no impression either
        impression_id_b = mirror["impression_id"],
        join_quality_b  = None,
    )

    r1 = record_match_disposition(match["id"], USER_A, "accept",
                                  write_outcomes=True)
    r2 = record_match_disposition(match["id"], USER_B, "decline",
                                  write_outcomes=True)

    assert r1["status"] == "ok" and r2["status"] == "ok"
    assert r2["both_decided"] is True and r2["outcome"] == "declined"
    assert r1["outcome_rows_written"] == 0
    assert r2["outcome_rows_written"] == 0
    assert _outcomes(mem_engine) == []


def test_find_matching_like_prefers_the_newest_mirror(mem_engine):
    """Newest mirror wins (LLD §2.1) — a re-like from a fresher deck is the
    impression that should carry the label.

    SABOTAGE: drop the ORDER BY created_at DESC — the stale impression wins
    and this fails.
    """
    old = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    with mem_engine.begin() as conn:
        conn.execute(insert(trade_decisions_table).values(
            user_id=USER_B, league_id=LEAGUE, trade_id="t-old",
            give_player_ids=json.dumps(RECEIVE),
            receive_player_ids=json.dumps(GIVE),
            decision="like", created_at=old, impression_id="imp-stale"))
    _like(USER_B, RECEIVE, GIVE, impression_id="imp-fresh")

    mirror = find_matching_like(USER_A, LEAGUE, USER_B, GIVE, RECEIVE)
    assert mirror["impression_id"] == "imp-fresh"


def test_check_for_match_still_returns_a_bool(mem_engine):
    """`check_for_match` survives as a thin `is not None` wrapper — other
    callers (and four existing test modules) depend on the bool contract.

    SABOTAGE: return the dict from check_for_match — `is True` fails.
    """
    assert check_for_match(USER_A, LEAGUE, USER_B, GIVE, RECEIVE) is False
    _like(USER_B, RECEIVE, GIVE, impression_id=IMP_B)
    assert check_for_match(USER_A, LEAGUE, USER_B, GIVE, RECEIVE) is True


# ---------------------------------------------------------------------------
# Swipe-time leg: the id persisted is the id that PASSED validation
# ---------------------------------------------------------------------------

def test_save_deck_outcome_safe_returns_only_the_validated_id(mem_engine):
    """LLD §4.3 — the swipe route threads `_save_deck_outcome_safe`'s RETURN
    into save_trade_decision, so the like row can only ever carry an
    impression this validation accepted: owned by the acting user, fresh.

    SABOTAGE: return the raw body field (or `impression_id` before the
    ownership/staleness checks) — the foreign and stale cases stop being
    None and this fails.
    """
    _plant_impression(mem_engine, "imp-mine", USER_A)
    _plant_impression(mem_engine, "imp-theirs", USER_B)
    _plant_impression(mem_engine, "imp-old", USER_A, age_days=40)

    with patch.object(server, "_deck_signal_v2_enabled", lambda: True), \
         patch.object(server, "_deck_taste_enabled", lambda: False):
        assert server._save_deck_outcome_safe(
            "imp-mine", "like", acting_user_id=USER_A) == "imp-mine"
        assert server._save_deck_outcome_safe(
            "imp-theirs", "like", acting_user_id=USER_A) is None   # foreign
        assert server._save_deck_outcome_safe(
            "imp-old", "like", acting_user_id=USER_A) is None      # stale
        assert server._save_deck_outcome_safe(
            "imp-nope", "like", acting_user_id=USER_A) is None     # unknown
        assert server._save_deck_outcome_safe(
            None, "like", acting_user_id=USER_A) is None           # absent

    # Only the validated one produced a label row.
    assert [r["impression_id"] for r in _outcomes(mem_engine)] == ["imp-mine"]


def test_save_trade_decision_persists_the_impression_on_the_like_row(mem_engine):
    """The exact-recovery key for side B lives on the like row.

    SABOTAGE: drop the impression_id column from the insert — side B can
    never be recovered exactly and this fails.
    """
    _like(USER_B, RECEIVE, GIVE, impression_id=IMP_B)
    _like(USER_A, GIVE, RECEIVE)
    with mem_engine.connect() as conn:
        rows = conn.execute(
            select(trade_decisions_table.c.user_id,
                   trade_decisions_table.c.impression_id)
            .order_by(trade_decisions_table.c.id)).fetchall()
    assert [(r.user_id, r.impression_id) for r in rows] == [
        (USER_B, IMP_B), (USER_A, None)]


# ---------------------------------------------------------------------------
# Route harness (only the 409 conflict path needs Flask)
# ---------------------------------------------------------------------------

from contextlib import contextmanager   # noqa: E402  (harness-local)


@contextmanager
def _route_harness(engine, *, as_user):
    """Minimal disposition-route harness: real session, real DB, mocked
    notification/push/persistence side-effects. Pattern from
    test_disposition_route.py."""
    pool = [Player(id=pid, name=pid.upper(), position="RB", team="AAA", age=25)
            for pid in (GIVE + RECEIVE)]
    service = RankingService(players=pool)
    league = League(
        league_id=LEAGUE, name="Join League", platform="sleeper",
        members=[LeagueMember(user_id=USER_A, username="a", roster=[], elo_ratings={}),
                 LeagueMember(user_id=USER_B, username="b", roster=[], elo_ratings={})],
    )
    token = "test-token-p0-3"
    sess = {"user_id": as_user, "league": league, "players": pool,
            "services": {"1qb_ppr": service}, "service": service,
            "active_format": "1qb_ppr", "last_active": 0.0}
    server.app.config["TESTING"] = True
    client = server.app.test_client()
    with patch.object(db_module, "engine", engine), \
         patch.object(server, "save_trade_swipes", MagicMock()), \
         patch.object(server, "load_matches", MagicMock(return_value=[])), \
         patch.object(server, "record_event", MagicMock()), \
         patch.object(server, "create_notification", MagicMock()), \
         patch.object(server, "_send_typed_push", MagicMock()):
        with server._sessions_lock:
            server._sessions[token] = sess
        try:
            yield client, token
        finally:
            with server._sessions_lock:
                server._sessions.pop(token, None)


# ---------------------------------------------------------------------------
# Taste-reward / action-enum coherence (P0-3 follow-through)
# ---------------------------------------------------------------------------

def test_taste_rewards_keys_are_legal_actions():
    """SABOTAGE: add a reward keyed on an action string that no writer can
    produce — e.g. "accept" (the real label is "accepted") — and this fails.

    The dict carried exactly that pair before P0-3: "accept": 4.0 and
    "decline": -2.0, neither of which is in DECK_OUTCOME_ACTIONS, so
    save_deck_outcome would raise on them and the rewards were unreachable
    while reading as configured behavior. That is a live trap for the later
    taste-reward PR, which has to wire the four NEW disposition labels: an
    author copying the old spelling gets a silent 0.0. Pin the invariant so
    the near-miss is a red test, not a quiet no-op.
    """
    from backend.database import DECK_OUTCOME_ACTIONS
    from backend.taste_service import TASTE_REWARDS
    unknown = sorted(set(TASTE_REWARDS) - set(DECK_OUTCOME_ACTIONS))
    assert unknown == [], (
        f"TASTE_REWARDS keys that are not legal deck outcome actions: "
        f"{unknown}. Rewards on an unwritable action are dead code that "
        f"looks live; use the exact DECK_OUTCOME_ACTIONS spelling.")


def test_new_disposition_labels_score_zero_taste_until_their_own_pr():
    """SABOTAGE: quietly add disposition rewards here instead of in the
    dedicated PR — this fails, which is the point. P0-3 lands the LABELS;
    what they are WORTH to taste is a separate decision with its own
    before/after evidence (LLD §6.2: unknown-action -> 0.0 is the correct
    fail-safe, not an oversight)."""
    from backend.taste_service import TASTE_REWARDS
    for label in ("accepted", "declined",
                  "accepted_by_partner", "declined_by_partner"):
        assert TASTE_REWARDS.get(label, 0.0) == 0.0
