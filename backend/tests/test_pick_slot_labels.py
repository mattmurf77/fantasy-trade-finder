"""D-090 — an owned pick reads as its real draft slot ("2026 1.08"), not its round.

Operator feedback 2026-08-19 (screen TradesHome, v1.15.0): *"For 2026 picks, we
should present them as actual draft pick slot rather than a generic 2026 round
pick."*

This file exists because the change has exactly two ways to be wrong, and both
of them look fine to a test that only asserts "the label contains a dot":

  **S1 — a slot invented where none exists.** The pre-draft Sleeper payload
  hands back ``slot_to_roster_id = {"1":1 … "12":12}``, an identity map that
  reads as a plausible order and is not one (the D5 rule in
  ``draft_board_service``). A resolver that reached for it would label every
  pick with its own roster id and be confidently, silently wrong for every
  league whose commissioner has not set the order. `test_unset_draft_order_*`
  and `test_identity_slot_to_roster_is_never_read` are the traps: they pass a
  draft object carrying that map and a NULL ``draft_order``, and demand None.

  **S2 — a slot on a season that has no order.** Nobody knows 2027's draft
  order in 2026, so "2027 1.08" is fiction (#273). Every future-season case
  below pins the round ordinal literally.

Plus the one that is not a bug but a bright line: **the slot must not move a
price.** `test_no_price_moves_with_or_without_an_order` pins `pool_value`
identical in both states, because "an early 1st is worth more than a mid 1st"
is a pricing question this change deliberately does not answer (Q-023).

Route isolation mirrors `test_league_picks_tier.py`: Flask test client,
injected session, patched loaders, no network and no DB.
"""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import backend.server as server
from backend import pick_slots
from backend.pick_values import pick_pool_value

LEAGUE = "league_pick_slot_test"
TOKEN = "sess-pick-slot-test"
SEASON = 2026

# A 12-team league whose order is deliberately NOT the identity map — roster 1
# drafts 8th. Under sabotage S1 (reading `slot_to_roster_id`, or defaulting to
# the roster id) roster 1 would label "1.01", so every expectation below that
# says 1.08 is load-bearing.
ROSTER_TO_USER = {str(r): f"u{r}" for r in range(1, 13)}
SLOT_BY_ROSTER = {1: 8, 2: 10, 3: 2, 4: 7, 5: 5, 6: 11,
                  7: 4, 8: 3, 9: 9, 10: 1, 11: 6, 12: 12}

#: Shaped exactly like Sleeper's `GET /v1/league/<id>/drafts` element — the
#: payload `_sync_sleeper_owned_picks` ALREADY fetches for the #228 exclusion,
#: which is why resolving a slot costs no extra upstream call. `draft_order` is
#: keyed by user_id, and `slot_to_roster_id` is present-and-ignored on purpose.
DRAFT = {
    "draft_id": "d1",
    "season": SEASON,
    "status": "pre_draft",
    "type": "linear",
    "settings": {"rounds": 4, "teams": 12, "reversal_round": 0},
    "draft_order": {f"u{rid}": slot for rid, slot in SLOT_BY_ROSTER.items()},
    "slot_to_roster_id": {str(s): s for s in range(1, 13)},   # the S1 trap
}


def _order():
    return pick_slots.order_from_sleeper_drafts(
        [DRAFT], ROSTER_TO_USER, SEASON, 12)


def _row(season, rnd, roster, *, traded=0, orig="alice"):
    return {
        "pick_id": f"{LEAGUE}_{season}_{rnd}_{roster}",
        "league_id": LEAGUE, "season": season, "round": rnd,
        "original_roster_id": str(roster),
        "owner_user_id": "u_a", "owner_username": "owner",
        "is_traded": traded, "original_username": orig,
        "pool_value": pick_pool_value(rnd, max(0, season - SEASON)),
    }


# ---------------------------------------------------------------------------
# Resolving an order — Sleeper
# ---------------------------------------------------------------------------

def test_sleeper_order_composes_draft_order_with_rosters():
    order = _order()
    assert order is not None
    assert order["season"] == SEASON
    assert order["teams"] == 12
    assert order["type"] == "linear"
    assert order["source"] == pick_slots.SRC_SLEEPER_DRAFT_ORDER
    # Literal, not a round-trip of the input: roster 1 drafts EIGHTH.
    assert order["slots"] == {str(r): s for r, s in SLOT_BY_ROSTER.items()}


def test_unset_draft_order_resolves_nothing():
    """S1 — the common pre-draft state. Never an invented order (D5)."""
    d = {**DRAFT, "draft_order": None}
    assert pick_slots.order_from_sleeper_drafts([d], ROSTER_TO_USER, SEASON, 12) is None
    assert pick_slots.order_from_sleeper_drafts(
        [{**DRAFT, "draft_order": {}}], ROSTER_TO_USER, SEASON, 12) is None


def test_identity_slot_to_roster_is_never_read():
    """S1, stated as the sabotage. `slot_to_roster_id` here is a PERFECT
    identity map and would resolve all 12 rosters if anything read it; with
    `draft_order` null the honest answer is still None."""
    d = {**DRAFT, "draft_order": None,
         "slot_to_roster_id": {str(s): s for s in range(1, 13)}}
    assert pick_slots.order_from_sleeper_drafts([d], ROSTER_TO_USER, SEASON, 12) is None


def test_no_draft_for_the_season_resolves_nothing():
    assert pick_slots.order_from_sleeper_drafts([DRAFT], ROSTER_TO_USER, 2027, 12) is None
    assert pick_slots.order_from_sleeper_drafts([], ROSTER_TO_USER, SEASON, 12) is None


def test_partial_resolution_is_kept_not_discarded():
    """A co-owner-keyed team resolves no roster. Eleven real slots plus one
    generic label beats twelve generic labels."""
    partial = {k: v for k, v in ROSTER_TO_USER.items() if k != "3"}
    order = pick_slots.order_from_sleeper_drafts([DRAFT], partial, SEASON, 12)
    assert order is not None
    assert "3" not in order["slots"] and len(order["slots"]) == 11
    assert pick_slots.slot_for(order, SEASON, 1, "3") is None
    assert pick_slots.slot_for(order, SEASON, 1, "1") == 8


def test_every_key_unresolvable_yields_none():
    assert pick_slots.order_from_sleeper_drafts([DRAFT], {}, SEASON, 12) is None


# ---------------------------------------------------------------------------
# Resolving an order — user-assigned (ESPN)
# ---------------------------------------------------------------------------

def test_assignment_settings_order_indexes_from_one():
    settings = {"rounds": 4, "order_type": "linear",
                "order": ["uA", "uB", "uC"]}
    order = pick_slots.order_from_assignment_settings(
        settings, SEASON, {"uA": "7", "uB": "3", "uC": "9"})
    assert order["slots"] == {"7": 1, "3": 2, "9": 3}
    assert order["teams"] == 3
    assert order["source"] == pick_slots.SRC_ASSIGNMENT_SETTINGS


def test_assignment_settings_snake_shape_is_carried():
    order = pick_slots.order_from_assignment_settings(
        {"order": ["uA", "uB"], "order_type": "snake"}, SEASON,
        {"uA": "1", "uB": "2"})
    assert order["type"] == "snake"
    assert pick_slots.slot_for(order, SEASON, 1, "1") == 1
    assert pick_slots.slot_for(order, SEASON, 2, "1") == 2     # reversed


def test_missing_or_empty_assignment_settings_resolve_nothing():
    assert pick_slots.order_from_assignment_settings(None, SEASON, {}) is None
    assert pick_slots.order_from_assignment_settings({}, SEASON, {}) is None
    assert pick_slots.order_from_assignment_settings(
        {"order": []}, SEASON, {}) is None
    # An order none of whose ids reach a roster resolves no slots at all.
    assert pick_slots.order_from_assignment_settings(
        {"order": ["ghost"]}, SEASON, {"uA": "1"}) is None


# ---------------------------------------------------------------------------
# Reading an order
# ---------------------------------------------------------------------------

def test_linear_slot_is_the_same_every_round():
    order = _order()
    for rnd in (1, 2, 3, 4):
        assert pick_slots.slot_for(order, SEASON, rnd, "1") == 8


def test_snake_reverses_even_rounds_exactly_as_the_client_does():
    """Must agree with `PickAssignmentScreen.draftPosition` (teams + 1 - base),
    or the picks screen and the trade card disagree about the same pick."""
    order = {**_order(), "type": "snake"}
    assert pick_slots.slot_for(order, SEASON, 1, "1") == 8
    assert pick_slots.slot_for(order, SEASON, 2, "1") == 5      # 12 + 1 - 8
    assert pick_slots.slot_for(order, SEASON, 3, "1") == 8
    assert pick_slots.slot_for(order, SEASON, 4, "1") == 5


def test_snake_with_reversal_round_refuses_rather_than_guesses():
    """Mirrors `draft_board_service._pick_no`: third-round reversal changes the
    parity in a way we have no payload to verify against."""
    order = {**_order(), "type": "snake", "reversal_round": 3}
    assert pick_slots.slot_for(order, SEASON, 1, "1") is None
    assert pick_slots.slot_for(order, SEASON, 2, "1") is None
    # A LINEAR draft carrying a stale reversal_round is unaffected — Lakeview
    # is exactly that shape (draft_board_service._pick_no's docstring).
    assert pick_slots.slot_for({**_order(), "reversal_round": 3},
                               SEASON, 2, "1") == 8


def test_future_season_never_resolves_a_slot():
    """S2 / #273 — nobody knows next year's order."""
    order = _order()
    for season in (2027, 2028, 2029):
        assert pick_slots.slot_for(order, season, 1, "1") is None
    assert pick_slots.slot_for(order, 2025, 1, "1") is None     # and not the past


def test_unknown_roster_and_malformed_blobs_resolve_nothing():
    order = _order()
    assert pick_slots.slot_for(order, SEASON, 1, "99") is None
    assert pick_slots.slot_for(order, SEASON, 1, None) is None
    assert pick_slots.slot_for(order, SEASON, 0, "1") is None
    assert pick_slots.slot_for(None, SEASON, 1, "1") is None
    assert pick_slots.slot_for({}, SEASON, 1, "1") is None
    assert pick_slots.slot_for({**order, "schema": 99}, SEASON, 1, "1") is None
    assert pick_slots.slot_for({**order, "slots": "nope"}, SEASON, 1, "1") is None
    # A slot outside the league's own width is corrupt, not a 13th team.
    assert pick_slots.slot_for({**order, "slots": {"1": 13}},
                               SEASON, 1, "1") is None


def test_slot_suffix_is_zero_padded():
    assert pick_slots.slot_suffix(1, 8) == "1.08"
    assert pick_slots.slot_suffix(1, 12) == "1.12"
    assert pick_slots.slot_suffix(4, 1) == "4.01"


# ---------------------------------------------------------------------------
# The label
# ---------------------------------------------------------------------------

def test_current_year_pick_reads_as_its_slot():
    order = _order()
    assert server._owned_pick_label(_row(SEASON, 1, 10), order) == "2026 1.01"
    assert server._owned_pick_label(_row(SEASON, 1, 1), order) == "2026 1.08"
    assert server._owned_pick_label(_row(SEASON, 4, 12), order) == "2026 4.12"


def test_acquired_from_suffix_survives_the_slot():
    """A slot says WHERE the pick picks; the suffix says WHOSE it was. Only a
    leaguemate who has memorised the order can read the second off the first,
    so the suffix is kept, not replaced."""
    row = _row(SEASON, 1, 1, traded=1, orig="mattmurf77")
    assert server._owned_pick_label(row, _order()) == "2026 1.08 (from mattmurf77)"


def test_future_year_keeps_its_round_ordinal():
    order = _order()
    assert server._owned_pick_label(_row(2027, 1, 1), order) == "2027 1st"
    assert server._owned_pick_label(_row(2029, 3, 5), order) == "2029 3rd"
    assert (server._owned_pick_label(_row(2027, 2, 1, traded=1, orig="bob"), order)
            == "2027 2nd (from bob)")


def test_no_order_reproduces_the_pre_d090_string_byte_for_byte():
    """The kill-switch contract. `None` is what a flag-off request, an
    unresolvable league and an MFL league all pass."""
    assert server._owned_pick_label(_row(SEASON, 1, 1), None) == "2026 1st"
    assert (server._owned_pick_label(_row(SEASON, 2, 10, traded=1, orig="bob"), None)
            == "2026 2nd (from bob)")
    assert server._owned_pick_label(_row(2029, 4, 3), None) == "2029 4th"


def test_default_argument_is_the_generic_label():
    """`_owned_pick_label(p)` with no second argument must still be the old
    function — anything that calls it positionally is unchanged."""
    assert server._owned_pick_label(_row(SEASON, 1, 1)) == "2026 1st"


def test_label_never_contains_the_package_separator():
    """`TradesScreen.tsx` splits an evener's name on ' + ' to recover the
    per-piece labels. A slot label must not introduce a second separator."""
    assert " + " not in server._owned_pick_label(
        _row(SEASON, 1, 1, traded=1, orig="mattmurf77"), _order())


# ---------------------------------------------------------------------------
# The bright line: no price moves
# ---------------------------------------------------------------------------

def test_no_price_moves_with_or_without_an_order():
    """Whether an early 1st should outprice a mid 1st is Q-023, not this
    change. The slot is a label input and nothing else."""
    order = _order()
    for rnd in (1, 2, 3, 4):
        for roster in ("1", "10", "12"):
            row = _row(SEASON, rnd, roster)
            before = row["pool_value"]
            server._owned_pick_label(row, order)
            assert row["pool_value"] == before          # not mutated
        # Every slot of a round prices identically — the Mid rung, as
        # `pick_pool_value` has since the 2026-07-18 operator decision.
        assert (_row(SEASON, rnd, "1")["pool_value"]
                == _row(SEASON, rnd, "10")["pool_value"]
                == pick_pool_value(rnd, 0))


# ---------------------------------------------------------------------------
# Route level — GET /api/league/picks
# ---------------------------------------------------------------------------

PICK_ROWS = [_row(SEASON, 1, 1, traded=1, orig="mattmurf77"),
             _row(SEASON, 1, 10),
             _row(SEASON, 3, 5),
             _row(2027, 1, 1),
             _row(2029, 4, 12)]


def _mk_sess():
    return {
        "user_id": "u_a", "active_format": "1qb_ppr", "last_active": 0.0,
        "league": SimpleNamespace(league_id=LEAGUE, platform=None, members=[]),
        "players": [], "trade_svc": object(),
        "trade_svcs": {"1qb_ppr": object()}, "services": {},
        "service": None, "user_roster": [],
    }


@pytest.fixture()
def client(request):
    """`request.param` is the `picks.slot_labels` state; every other flag off."""
    slot_labels = getattr(request, "param", True)
    server.app.config["TESTING"] = True
    server._slot_order_cache.clear()
    c = server.app.test_client()
    with patch.object(server, "is_enabled",
                      lambda k: k == "picks.slot_labels" and slot_labels), \
         patch.object(server, "touch_user_activity", MagicMock()), \
         patch.object(server, "load_draft_slot_order",
                      lambda lid: _order() if lid == LEAGUE else None), \
         patch.object(server, "load_pick_assignment_settings", lambda lid: None), \
         patch.object(server, "load_draft_picks",
                      lambda league_id=None, **kw:
                      [dict(p) for p in PICK_ROWS] if league_id == LEAGUE else []):
        try:
            yield c
        finally:
            server._slot_order_cache.clear()
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)


def _get_picks(c):
    with server._sessions_lock:
        server._sessions[TOKEN] = _mk_sess()
    r = c.get(f"/api/league/picks?league_id={LEAGUE}",
              headers={"X-Session-Token": TOKEN})
    return r.status_code, json.loads(r.data)


@pytest.mark.parametrize("client", [True], indirect=True)
def test_route_serves_slot_labels_for_the_current_year(client):
    code, body = _get_picks(client)
    assert code == 200
    labels = {p["pick_id"]: p["label"] for p in body["all_picks"]}
    assert labels[f"{LEAGUE}_2026_1_1"] == "2026 1.08 (from mattmurf77)"
    assert labels[f"{LEAGUE}_2026_1_10"] == "2026 1.01"
    assert labels[f"{LEAGUE}_2026_3_5"] == "2026 3.05"
    # …and the future years are untouched in the same payload.
    assert labels[f"{LEAGUE}_2027_1_1"] == "2027 1st"
    assert labels[f"{LEAGUE}_2029_4_12"] == "2029 4th"


@pytest.mark.parametrize("client", [False], indirect=True)
def test_route_is_byte_identical_with_the_flag_off(client):
    code, body = _get_picks(client)
    assert code == 200
    labels = {p["pick_id"]: p["label"] for p in body["all_picks"]}
    assert labels == {
        f"{LEAGUE}_2026_1_1":  "2026 1st (from mattmurf77)",
        f"{LEAGUE}_2026_1_10": "2026 1st",
        f"{LEAGUE}_2026_3_5":  "2026 3rd",
        f"{LEAGUE}_2027_1_1":  "2027 1st",
        f"{LEAGUE}_2029_4_12": "2029 4th",
    }


@pytest.mark.parametrize("client", [False], indirect=True)
def test_flag_off_never_reads_the_order(client):
    """The kill switch must short-circuit BEFORE the lookup, not after — a
    disabled feature should not be paying for a DB read per league."""
    with patch.object(server, "load_draft_slot_order",
                      side_effect=AssertionError("read while disabled")):
        code, _ = _get_picks(client)
    assert code == 200


@pytest.mark.parametrize("client", [True], indirect=True)
def test_order_lookup_is_cached_per_league(client):
    """One lookup per league per TTL, not one per pick — the label path runs
    per card when a deck is served."""
    calls = []

    def _counting(lid):
        calls.append(lid)
        return _order()

    with patch.object(server, "load_draft_slot_order", _counting):
        _get_picks(client)
        _get_picks(client)
    assert calls == [LEAGUE]


@pytest.mark.parametrize("client", [True], indirect=True)
def test_a_failing_lookup_degrades_to_generic_labels(client):
    """Display-only enrichment must never fail a route."""
    server._slot_order_cache.clear()
    with patch.object(server, "load_draft_slot_order",
                      side_effect=RuntimeError("db down")), \
         patch.object(server, "load_pick_assignment_settings",
                      side_effect=RuntimeError("db down")):
        code, body = _get_picks(client)
    assert code == 200
    labels = {p["label"] for p in body["all_picks"]}
    assert labels == {"2026 1st (from mattmurf77)", "2026 1st", "2026 3rd",
                      "2027 1st", "2029 4th"}


@pytest.mark.parametrize("client", [True], indirect=True)
def test_demo_league_resolves_nothing(client):
    assert server._league_slot_order("league_demo") is None
    assert server._league_slot_order("") is None
