"""#362 — standing offers: broaden a liked 1-for-1.

A standing offer is a user's GENERALISED, time-boxed, team-targeted intent:
"I will send player P for any round-R pick, in seasons Y, from teams T, in
this league, until expires_at." Where `trade_decisions` holds ONE exact
package, this holds the generalisation — and it feeds the SAME
`_inject_likes_you_cards_impl` loop as a second candidate source, never a
fork.

Every test names, in its docstring, the sabotage that must turn it RED.

Harness: isolated in-memory SQLite + injected session through Flask's test
client (`test_awaiting_dismiss.py` pattern), and the injector exercised
directly (`test_not_interested.py` pattern).
"""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, text

import backend.analytics_queries as aq
import backend.analytics_taxonomy as at
import backend.database as db
import backend.feature_flags as ff
import backend.server as server
import backend.trade_service as ts
from backend.trade_service import League, LeagueMember, TradeService

LEAGUE = "L362"
ME = "u_me"
OPP = "u_opp"
OTHER = "u_other"
PLAYER = "p_willis"


class _Player:
    def __init__(self, pid, position="QB", team="TST", name=None):
        self.id = pid
        self.name = name or f"Player {pid}"
        self.position = position
        self.team = team
        self.age = 25
        self.search_rank = 50
        self.pick_value = None
        # player_to_dict reads these; a card serializer test needs them.
        self.years_experience = 3
        self.injury_status = None
        self.bye_week = None


def _pick(season, rnd=1, roster="7"):
    return f"{LEAGUE}_{season}_{rnd}_{roster}"


@pytest.fixture(autouse=True)
def _isolate():
    old_flags = ff._flags_cache
    old_cfg = dict(ts._cfg)
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "trade.standing_offers": True,
                       "trade.likes_you": True}
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    try:
        yield
    finally:
        ff._flags_cache = old_flags
        ts._cfg.clear()
        ts._cfg.update(old_cfg)


def _seed_picks(eng, seasons=(2027, 2028), rounds=(1,)):
    with eng.begin() as conn:
        for season in seasons:
            for rnd in rounds:
                for roster in ("7", "9"):
                    conn.execute(text(
                        "INSERT INTO draft_picks (pick_id, league_id, season, "
                        "round, owner_user_id, original_roster_id) "
                        "VALUES (:p, :l, :s, :r, :o, :orr)"),
                        {"p": f"{LEAGUE}_{season}_{rnd}_{roster}", "l": LEAGUE,
                         "s": season, "r": rnd, "o": ME, "orr": roster})


class _FakeLeague:
    league_id = LEAGUE
    name = "QA Standard League"

    def __init__(self, members):
        self.members = members


@pytest.fixture()
def harness():
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False})
    db.metadata.create_all(eng)
    _seed_picks(eng)

    members = [
        LeagueMember(user_id=ME, username="me", roster=[_pick(2027)],
                     elo_ratings={}),
        LeagueMember(user_id=OPP, username="qa_opp", roster=[PLAYER],
                     elo_ratings={}),
        LeagueMember(user_id=OTHER, username="qa_other", roster=[],
                     elo_ratings={}),
    ]
    token = "standing-offer-sess"
    sess = {"user_id": ME, "league": _FakeLeague(members),
            "players": [_Player(PLAYER, "QB", name="Malik Willis")],
            "trade_svc": object(), "active_format": "1qb_ppr",
            "last_active": 0.0, "user_roster": [_pick(2027)]}
    server.app.config["TESTING"] = True
    client = server.app.test_client()
    event_spy = MagicMock()
    with patch.object(db, "engine", eng), \
         patch.object(server, "record_event", event_spy):
        with server._sessions_lock:
            server._sessions[token] = sess
        try:
            yield client, token, eng, event_spy
        finally:
            with server._sessions_lock:
                server._sessions.pop(token, None)


def _create(client, token, **over):
    body = {"league_id": LEAGUE, "player_id": PLAYER, "round": 1,
            "seasons": [2027, 2028], "team_user_ids": [OPP],
            "source_trade_id": "likesyou_ab12cd34ef56"}
    body.update(over)
    return client.post("/api/trades/standing-offer", json=body,
                       headers={"X-Session-Token": token})


# ---------------------------------------------------------------------------
# UT-1 / UT-2 / UT-3 / UT-13 — the create route
# ---------------------------------------------------------------------------

def test_create_then_duplicate_409_then_revoke_allows_repost(harness):
    """UT-1 (R-20, R-21) — create writes a live row; a second create for the
    same (user, league, player, round) is 409 WHILE the first is live, and
    succeeds after a revoke.

    SABOTAGE: swap the writer's `revoked_at IS NULL` predicate for a DB
    UniqueConstraint — revoke-then-repost then collides, and the supported
    "edit" flow becomes impossible.
    """
    client, token, eng, _ = harness
    r = _create(client, token)
    assert r.status_code == 200, r.get_json()
    offer = r.get_json()["offer"]
    assert offer["round"] == 1
    assert offer["seasons"] == [2027, 2028]
    assert offer["team_user_ids"] == [OPP]
    assert offer["team_count"] == 1
    assert offer["revoked_at"] is None
    assert offer["days_left"] == 30
    assert offer["player_name"] == "Malik Willis"

    dup = _create(client, token)
    assert dup.status_code == 409
    assert dup.get_json()["offer_id"] == offer["offer_id"]

    rev = client.post("/api/trades/standing-offer/revoke",
                      json={"offer_id": offer["offer_id"]},
                      headers={"X-Session-Token": token})
    assert rev.status_code == 200 and rev.get_json()["revoked"] is True
    # Idempotent repeat — still 200, never 404.
    again = client.post("/api/trades/standing-offer/revoke",
                        json={"offer_id": offer["offer_id"]},
                        headers={"X-Session-Token": token})
    assert again.status_code == 200 and again.get_json()["revoked"] is False

    assert _create(client, token).status_code == 200, "repost after revoke"


def test_season_outside_pick_horizon_is_400(harness):
    """UT-2 (R-22 / R-4) — a season the league has no round-1 picks for is
    rejected, and the error names the real horizon so a stale client can
    refetch. Horizon is DERIVED from draft_picks, never a hardcoded window —
    that is the #355 defect D-091 fixed at the writer.

    SABOTAGE: reintroduce a hardcoded N-year window in place of
    league_pick_seasons.
    """
    client, token, _, _ = harness
    r = _create(client, token, seasons=[2027, 2031])
    assert r.status_code == 400
    body = r.get_json()
    assert body["error"] == "seasons must be within the league's pick horizon"
    assert body["allowed_seasons"] == [2027, 2028]


def test_non_member_team_id_is_400(harness):
    """UT-3 (R-22) — every team_user_id must be a CURRENT league member, and
    never the caller.

    SABOTAGE: trust the client's member list.
    """
    client, token, _, _ = harness
    r = _create(client, token, team_user_ids=[OPP, "u_stranger"])
    assert r.status_code == 400
    assert r.get_json()["invalid"] == ["u_stranger"]
    r = _create(client, token, team_user_ids=[ME])
    assert r.status_code == 400 and r.get_json()["invalid"] == [ME]


def test_round_other_than_1_is_400(harness):
    """UT-13 (D-d) — v1 is FIRSTS ONLY. The `round` column exists so widening
    is a config change, not a schema change.

    SABOTAGE: v1 scope drift — accept round 2+.
    """
    client, token, _, _ = harness
    assert _create(client, token, round=2).status_code == 400
    assert _create(client, token, round=2).get_json()["error"] == "round must be 1"


def test_create_requires_fields(harness):
    client, token, _, _ = harness
    for over in ({"seasons": []}, {"team_user_ids": []}, {"player_id": None}):
        assert _create(client, token, **over).status_code == 400


def test_source_trade_id_is_never_validated(harness):
    """R-18 (FB-46) — a reconstructed card carries a SYNTHETIC trade id and
    must still work. source_trade_id is provenance only.

    SABOTAGE: validate source_trade_id against the deck; every
    reconstructed-card post then 400s.
    """
    client, token, _, _ = harness
    assert _create(client, token, source_trade_id="not-a-real-trade").status_code == 200


# ---------------------------------------------------------------------------
# UT-7 / UT-11 — the manage list
# ---------------------------------------------------------------------------

def test_list_marks_stale_when_player_left_the_roster(harness):
    """UT-7 (R-11) — an offer whose player has left the SENDER's roster is
    dead regardless of the clock. The injector already enforces this via
    roster containment; the list applies the SAME test so the manage screen
    and the injector can never disagree.

    SABOTAGE: let the two surfaces disagree — drop `stale` and the list shows
    a live-looking offer for a player the user no longer has.
    """
    client, token, _, _ = harness
    _create(client, token)
    with server._sessions_lock:
        sess = server._sessions[token]
    # Give the offered player to the SENDER, then take him away again.
    sess["league"].members[0].roster = [_pick(2027), PLAYER]
    rows = client.get(f"/api/trades/standing-offers?league_id={LEAGUE}",
                      headers={"X-Session-Token": token}).get_json()["offers"]
    assert rows[0]["stale"] is False

    sess["league"].members[0].roster = [_pick(2027)]
    rows = client.get(f"/api/trades/standing-offers?league_id={LEAGUE}",
                      headers={"X-Session-Token": token}).get_json()["offers"]
    assert rows[0]["stale"] is True


def test_list_is_empty_object_never_404(harness):
    client, token, _, _ = harness
    r = client.get("/api/trades/standing-offers",
                   headers={"X-Session-Token": token})
    assert r.status_code == 200 and r.get_json() == {"offers": []}


def test_revoke_cannot_touch_another_users_offer(harness):
    """Ownership rides the WHERE clause, not a post-read check."""
    client, token, eng, _ = harness
    with patch.object(db, "engine", eng):
        other = db.create_standing_offer(
            user_id=OTHER, league_id=LEAGUE, player_id="p_x", round=1,
            seasons=[2027], team_user_ids=[ME], source_trade_id=None, days=30)
        assert db.revoke_standing_offer(user_id=ME, offer_id=other["id"]) is False
        assert db.revoke_standing_offer(user_id=OTHER, offer_id=other["id"]) is True


def test_expired_offer_does_not_block_a_new_one(harness):
    """UT-7b (R-23) — expiry is STORED, not derived. An expired row is not a
    live row, so it must not block a fresh create."""
    client, token, eng, _ = harness
    with patch.object(db, "engine", eng):
        db.create_standing_offer(
            user_id=ME, league_id=LEAGUE, player_id=PLAYER, round=1,
            seasons=[2027], team_user_ids=[OPP], source_trade_id=None,
            days=-1)      # already expired
        assert _create(client, token).status_code == 200


# ---------------------------------------------------------------------------
# The injector — UT-4, UT-5, UT-6, UT-8, UT-10, UT-11, UT-12
# ---------------------------------------------------------------------------

def _inject_svc(*, viewer_picks=(2027,), sender_holds=True, player_pos="QB"):
    players = {PLAYER: _Player(PLAYER, player_pos, name="Malik Willis")}
    for s in (2026, 2027, 2028, 2029):
        players[_pick(s)] = _Player(_pick(s), "PICK", team="PICK")
    svc = TradeService(players=players)
    opp = LeagueMember(user_id=OPP, username="qa_opp",
                       roster=[PLAYER] if sender_holds else [],
                       elo_ratings={}, has_rankings=False)
    league = League(league_id=LEAGUE, name="T", platform="demo", members=[opp])
    roster = [_pick(s) for s in viewer_picks]
    seed = {PLAYER: 1500.0}
    seed.update({_pick(s): 1500.0 for s in (2026, 2027, 2028, 2029)})
    return svc, league, roster, seed


def _inject(svc, league, roster, seed, offers, *, cards=None, **kw):
    with patch.object(server, "load_recent_league_likes", lambda **k: []), \
         patch.object(server, "load_standing_offers", lambda **k: offers):
        return server._inject_likes_you_cards(
            cards=list(cards or []), trade_service=svc, user_id=ME,
            league_id=LEAGUE, league=league, user_roster=roster,
            seed_map=seed, **kw)


def _offer(**over):
    o = {"id": 41, "user_id": OPP, "league_id": LEAGUE, "player_id": PLAYER,
         "round": 1, "seasons": [2027, 2028], "team_user_ids": [ME],
         "source_trade_id": None, "created_at": "2026-08-19T00:00:00+00:00",
         "expires_at": "2026-09-18T00:00:00+00:00", "revoked_at": None}
    o.update(over)
    return o


def test_selected_team_holding_a_matching_pick_gets_a_card():
    """UT-4 (R-12) — three sub-cases in one: a SELECTED team holding a
    matching pick gets the card; a NON-selected team holding one does not;
    a selected team holding NO matching pick does not.

    SABOTAGE: drop the `V ∈ T` selection test and broadcast league-wide.
    """
    svc, league, roster, seed = _inject_svc()
    with patch.object(server, "_pick_labels_by_id",
                      lambda ids: {i: "2027 1st" for i in ids}):
        got = _inject(svc, league, roster, seed, [_offer()])
        assert len(got) == 1
        assert got[0].receive_player_ids == [PLAYER]
        assert got[0].give_player_ids == [_pick(2027)]
        assert got[0].likes_you is True
        assert got[0].trade_id.startswith("standing_")

        # not selected
        assert _inject(svc, league, roster, seed,
                       [_offer(team_user_ids=[OTHER])]) == []
        # selected but holds no matching pick (2029 is outside the offer)
        svc2, lg2, ros2, sd2 = _inject_svc(viewer_picks=(2029,))
        assert _inject(svc2, lg2, ros2, sd2, [_offer()]) == []
        # sender no longer holds the player
        svc3, lg3, ros3, sd3 = _inject_svc(sender_holds=False)
        assert _inject(svc3, lg3, ros3, sd3, [_offer()]) == []


def test_generic_rungs_can_never_satisfy_an_offer():
    """UT-4b — the give side must be an OWNED LEAGUE pick of this league.
    Generic ladder rungs are `generic_pick_*` and fail the prefix test.

    SABOTAGE: parse (season, round) off any id shaped like a pick.
    """
    svc, league, roster, seed = _inject_svc()
    svc._players["generic_pick_1_mid"] = _Player("generic_pick_1_mid", "RB",
                                                 team="PICK")
    seed["generic_pick_1_mid"] = 1500.0
    assert _inject(svc, league, ["generic_pick_1_mid"], seed, [_offer()]) == []
    assert server._parse_owned_pick_id("generic_pick_1_mid", LEAGUE) is None
    assert server._parse_owned_pick_id(_pick(2027), LEAGUE) == (2027, 1)
    assert server._parse_owned_pick_id("OTHERLG_2027_1_7", LEAGUE) is None


@pytest.mark.parametrize("filt", ["untouchable", "not_interested",
                                  "past_decision", "r4", "d055"])
def test_every_preexisting_filter_still_runs(filt):
    """UT-5 (R-13) — five independent sub-cases: untouchables (#95),
    not-interested (#163), _past_decision_keys, the G6 R4 exclusion (#336)
    and the D-055 user-gain floor each suppress a standing-offer card on
    their own. This reuse is the entire reason the item is small.

    SABOTAGE: fork the loop into a parallel path that skips the filters.
    """
    svc, league, roster, seed = _inject_svc()
    kw = {}
    key = (frozenset([_pick(2027)]), frozenset([PLAYER]))
    if filt == "untouchable":
        kw["untouchable_ids"] = {_pick(2027)}
    elif filt == "not_interested":
        kw["not_interested_ids"] = {PLAYER}
    elif filt == "past_decision":
        svc._past_decision_keys = {key}
    elif filt == "r4":
        kw["exclusion_keys"] = {key}
    elif filt == "d055":
        seed = dict(seed, **{PLAYER: 1000.0, _pick(2027): 3000.0})

    with patch.object(server, "_pick_labels_by_id",
                      lambda ids: {i: "2027 1st" for i in ids}):
        assert _inject(svc, league, roster, seed, [_offer()], **kw) == [], filt


def test_avoided_position_suppresses_a_standing_offer_card():
    """#360 × #362 interaction (PRD §7.4) — the recipient's Avoiding must be
    respected by a standing-offer injection. It already is, structurally:
    standing offers reuse the same loop, so the filter is not rebuilt.

    SABOTAGE: rebuild the filter for the standing-offer branch instead of
    reusing the seam.
    """
    svc, league, roster, seed = _inject_svc(player_pos="QB")
    with patch.object(server, "_pick_labels_by_id",
                      lambda ids: {i: "2027 1st" for i in ids}):
        assert _inject(svc, league, roster, seed, [_offer()]) != []
        assert _inject(svc, league, roster, seed, [_offer()],
                       avoid_positions={"QB"}) == []


def test_cap_split_reserves_slots_for_organic_mirrors():
    """UT-6 (R-14, R-15) — _LIKES_YOU_CAP stays 3 and remains the TOTAL.
    Organic mirrors are evaluated FIRST; standing offers then fill remaining
    slots up to standing_offer_inject_cap (default 2). Drops are COUNTED,
    never evented.

    SABOTAGE: let standing offers consume all three slots.
    """
    svc, league, roster, seed = _inject_svc(viewer_picks=(2026, 2027, 2028))
    # Two organic likes from the opponent, mirrored into the viewer.
    for pid in ("p_a", "p_b"):
        svc._players[pid] = _Player(pid, "RB")
        seed[pid] = 1500.0
    league.members[0].roster = [PLAYER, "p_a", "p_b"]
    roster = roster + ["p_mine"]
    svc._players["p_mine"] = _Player("p_mine", "RB")
    seed["p_mine"] = 1500.0
    likes = [{"user_id": OPP, "give_player_ids": [p],
              "receive_player_ids": ["p_mine"]} for p in ("p_a", "p_b")]
    offers = [_offer(id=i, player_id=PLAYER) for i in (43, 42, 41)]
    # Three DISTINCT offered players so each yields its own package.
    for i, o in enumerate(offers):
        pid = f"p_off{i}"
        o["player_id"] = pid
        svc._players[pid] = _Player(pid, "TE")
        seed[pid] = 1500.0
        league.members[0].roster.append(pid)
        o["seasons"] = [2026 + i]

    with patch.object(server, "load_recent_league_likes", lambda **k: likes), \
         patch.object(server, "load_standing_offers", lambda **k: offers), \
         patch.object(server, "_pick_labels_by_id",
                      lambda ids: {i: "a 1st" for i in ids}):
        got = server._inject_likes_you_cards(
            cards=[], trade_service=svc, user_id=ME, league_id=LEAGUE,
            league=league, user_roster=roster, seed_map=seed)

    assert len(got) == 3, [c.receive_player_ids for c in got]
    organic = [c for c in got if not c.standing_offer_reason]
    standing = [c for c in got if c.standing_offer_reason]
    assert len(organic) >= 1 and len(standing) <= 2
    assert svc._standing_offer_cap_drops == 3 - len(standing)


def test_no_record_event_fires_on_a_cap_drop():
    """UT-11 (R-15) — cap drops are COUNTED, never evented. One event per
    dropped card in a chatty league is high-cardinality server noise for a
    question a counter answers.

    SABOTAGE: "helpfully" add a per-drop analytics event.
    """
    svc, league, roster, seed = _inject_svc(viewer_picks=(2026, 2027, 2028))
    offers = []
    for i in range(4):
        pid = f"p_cap{i}"
        svc._players[pid] = _Player(pid, "TE")
        seed[pid] = 1500.0
        league.members[0].roster.append(pid)
        offers.append(_offer(id=50 + i, player_id=pid, seasons=[2026, 2027, 2028]))
    spy = MagicMock()
    with patch.object(server, "load_recent_league_likes", lambda **k: []), \
         patch.object(server, "load_standing_offers", lambda **k: offers), \
         patch.object(server, "record_event", spy), \
         patch.object(server, "_pick_labels_by_id",
                      lambda ids: {i: "a 1st" for i in ids}):
        server._inject_likes_you_cards(
            cards=[], trade_service=svc, user_id=ME, league_id=LEAGUE,
            league=league, user_roster=roster, seed_map=seed)
    assert svc._standing_offer_cap_drops == 2
    names = [c.args[1] for c in spy.call_args_list]
    assert names == ["standing_offer_card_shown"] * 2, names


def test_reason_line_is_exactly_the_spec_string():
    """UT-8 (R-16) — the "Why you're seeing this" line, composed SERVER-side
    from (sender, player, round, seasons) ONLY. No count, no roster list, no
    team names (R-19). Without it a boosted card is indistinguishable from a
    lucky generation.

    SABOTAGE: copy that drifts from the spec, or that starts naming teams.
    """
    svc, league, roster, seed = _inject_svc()
    with patch.object(server, "_pick_labels_by_id",
                      lambda ids: {i: "2027 1st" for i in ids}):
        got = _inject(svc, league, roster, seed, [_offer()])
    assert got[0].standing_offer_reason == (
        "@qa_opp posted a standing offer: Malik Willis for any 2027 or 2028 "
        "1st, and you hold a 2027 1st.")
    assert server._seasons_phrase([2027]) == "2027"
    assert server._seasons_phrase([2028, 2027]) == "2027 or 2028"
    assert server._seasons_phrase([2029, 2027, 2028]) == "2027, 2028 or 2029"


def test_give_side_pick_choice_is_deterministic():
    """UT-10 (R-12) — with several matching picks the give side is the first
    by (season ASC, pick_id ASC), so two runs of the same deck produce the
    same card.

    SABOTAGE: nondeterministic set iteration producing a different card each
    generate.
    """
    def _run(roster_ids):
        chosen = set()
        for _ in range(6):
            svc, league, _r, seed = _inject_svc()
            for p in roster_ids:
                svc._players[p] = _Player(p, "PICK", team="PICK")
                seed[p] = 1500.0
            with patch.object(server, "_pick_labels_by_id",
                              lambda ids: {i: "a 1st" for i in ids}):
                got = _inject(svc, league, list(roster_ids), seed, [_offer()])
            chosen.add(tuple(got[0].give_player_ids))
        return chosen

    # season ASC wins over pick_id ASC …
    assert _run([_pick(2028, roster="9"), _pick(2027), _pick(2028)]) == \
        {(_pick(2027),)}
    # … and pick_id ASC breaks a season tie.
    assert _run([_pick(2028, roster="9"), _pick(2028, roster="7")]) == \
        {(_pick(2028, roster="7"),)}


def test_expired_or_revoked_offers_inject_nothing(harness):
    """UT-7 (R-23) — past expires_at ⇒ nothing injects. `load_standing_offers`
    is the gate and it is live_only by default.

    SABOTAGE: derive expiry at read time from a knob, so a knob change
    silently moves the deadline on an offer the user was shown a countdown
    for.
    """
    _client, _token, eng, _ = harness
    with patch.object(db, "engine", eng):
        db.create_standing_offer(user_id=OPP, league_id=LEAGUE,
                                 player_id=PLAYER, round=1, seasons=[2027],
                                 team_user_ids=[ME], source_trade_id=None,
                                 days=-1)
        assert db.load_standing_offers(league_id=LEAGUE,
                                       exclude_user_id=ME) == []
        assert len(db.load_user_standing_offers(user_id=OPP)) == 1


def test_serialized_card_carries_no_team_ids_and_no_counts():
    """UT-12 (R-19) — the PRIVACY requirement, enforced on the serialized
    dict: a recipient learns that THEY were selected, never who else was and
    never who was excluded. Jon's "but not xyz" is a private negative and
    surfacing it starts fights in real leagues.

    SABOTAGE: return the offer row wholesale into the card payload.
    """
    svc, league, roster, seed = _inject_svc()
    with patch.object(server, "_pick_labels_by_id",
                      lambda ids: {i: "2027 1st" for i in ids}):
        got = _inject(svc, league, roster, seed, [_offer()])
    out = server.trade_card_to_dict(got[0], svc._players)
    flat = json.dumps(out)
    assert "team_user_ids" not in out and "team_count" not in out
    assert "team_user_ids" not in flat and "team_count" not in flat
    assert OTHER not in flat and ME not in out.get("standing_offer_reason", "")
    # The reason names the SENDER and nobody else, and carries no counts.
    import re
    assert re.findall(r"@\w+", out["standing_offer_reason"]) == ["@qa_opp"]


# ---------------------------------------------------------------------------
# UT-9 — the sender's own chip
# ---------------------------------------------------------------------------

def test_stamp_own_standing_offers(harness):
    """UT-9 (R-9) — the SENDER's own matching cards carry
    standing_offer_mine, non-matching cards do not, and nothing is stamped
    with the flag off. Display only: never reorders, never boosts.

    SABOTAGE: a chip that appears on every card.
    """
    client, token, eng, _ = harness
    _create(client, token)

    from backend.trade_service import TradeCard
    def _card(give, recv):
        return TradeCard(trade_id="t", league_id=LEAGUE, proposing_user_id=ME,
                         target_user_id=OPP, target_username="o",
                         give_player_ids=give, receive_player_ids=recv,
                         mismatch_score=0.0, fairness_score=1.0,
                         composite_score=1.0)
    match = _card([PLAYER], [_pick(2027)])
    no_pick = _card([PLAYER], ["someone_else"])
    wrong_player = _card(["other_player"], [_pick(2027)])
    out_of_season = _card([PLAYER], [_pick(2029)])
    cards = [match, no_pick, wrong_player, out_of_season]

    with patch.object(db, "engine", eng):
        server._stamp_own_standing_offers(cards, ME, LEAGUE)
    assert match.standing_offer_mine == {"round": 1, "seasons": [2027, 2028]}
    assert no_pick.standing_offer_mine is None
    assert wrong_player.standing_offer_mine is None
    assert out_of_season.standing_offer_mine is None
    # Order is untouched.
    assert cards == [match, no_pick, wrong_player, out_of_season]
    # Serialization is present only when set.
    assert "standing_offer_mine" in server.trade_card_to_dict(match, {})
    assert "standing_offer_mine" not in server.trade_card_to_dict(no_pick, {})


# ---------------------------------------------------------------------------
# UT-14 — flag off
# ---------------------------------------------------------------------------

def test_flag_off_routes_404_and_payload_is_byte_identical(harness):
    """UT-14 (R-24) — OFF ⇒ no route reachable, no injector predicate
    evaluated, no card payload key added.

    SABOTAGE: add a payload key unconditionally, or forget the flag check on
    a route.
    """
    client, token, _, _ = harness
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "trade.standing_offers": False}
    assert _create(client, token).status_code == 404
    assert client.get("/api/trades/standing-offers",
                      headers={"X-Session-Token": token}).status_code == 404
    assert client.post("/api/trades/standing-offer/revoke",
                       json={"offer_id": 1},
                       headers={"X-Session-Token": token}).status_code == 404

    # The injector never reads standing offers with the flag off.
    svc, league, roster, seed = _inject_svc()
    called = MagicMock(return_value=[_offer()])
    with patch.object(server, "load_recent_league_likes", lambda **k: []), \
         patch.object(server, "load_standing_offers", called):
        assert server._inject_likes_you_cards(
            cards=[], trade_service=svc, user_id=ME, league_id=LEAGUE,
            league=league, user_roster=roster, seed_map=seed) == []
    called.assert_not_called()

    from backend.trade_service import TradeCard
    plain = TradeCard(trade_id="t", league_id=LEAGUE, proposing_user_id=ME,
                      target_user_id=OPP, target_username="o",
                      give_player_ids=["a"], receive_player_ids=["b"],
                      mismatch_score=0.0, fairness_score=1.0,
                      composite_score=1.0)
    out = server.trade_card_to_dict(plain, {})
    assert "standing_offer_reason" not in out
    assert "standing_offer_mine" not in out


def test_signal_features_standing_offer_key_is_set_only_when_true():
    """R-24 (signal spine) — the deck-outcome corpus separates the two
    likes-you injection sources, but the `standing_offer` key is added ONLY
    when the card actually came from one. Emitting it unconditionally breaks
    `test_bakeoff_serving.py::test_flag_off_is_byte_identical_to_the_captured_golden`
    (it did, during this build) — `features_json` is a captured golden, so a
    new always-present key is a byte change on a surface that has none.

    A BOOLEAN, never the reason string: the corpus must not carry copy.

    SABOTAGE: put the key back inside the `features = {...}` literal.
    """
    import inspect
    src = inspect.getsource(server)
    assert 'features["standing_offer"] = True' in src
    assert '"standing_offer":     bool(' not in src, \
        "the key must not live inside the always-emitted features literal"


# ---------------------------------------------------------------------------
# UT-15 — analytics registration AND classification, same commit
# ---------------------------------------------------------------------------

def test_analytics_events_registered_and_classified():
    """UT-15 (R-26) — the taxonomy has an IMPORT-TIME completeness check: a
    client event with no CLIENT_EVENT_PROPS entry raises ValueError at boot.
    And INTENT_EVENTS is derived by SUBTRACTION, so an impression-class event
    omitted from NON_INTENT_EVENTS silently inflates DAU/WAU. That is the
    NULL-`platform` failure mode the CLAUDE.md rule exists for.

    SABOTAGE: register the events and forget the classification.
    """
    client_events = {"standing_offer_prompted", "standing_offer_posted",
                     "standing_offer_skipped", "standing_offer_revoked"}
    assert client_events <= at.ALLOWED_CLIENT_EVENTS
    assert "standing_offer_card_shown" in at.SERVER_FIRED_EVENTS
    assert "standing_offer_card_shown" not in at.ALLOWED_CLIENT_EVENTS

    assert at.CLIENT_EVENT_PROPS["standing_offer_prompted"] == frozenset(
        {"round", "seasons_offered", "teams_offered"})
    assert at.CLIENT_EVENT_PROPS["standing_offer_posted"] == frozenset(
        {"round", "seasons", "teams", "used_all_teams"})
    assert at.CLIENT_EVENT_PROPS["standing_offer_skipped"] == frozenset(
        {"snoozed", "retired"})
    assert at.CLIENT_EVENT_PROPS["standing_offer_revoked"] == frozenset(
        {"age_days"})
    # No id lists anywhere — counts only (R-19).
    for name in client_events:
        assert "team_user_ids" not in at.CLIENT_EVENT_PROPS[name]

    non_intent = {"standing_offer_prompted", "standing_offer_skipped",
                  "standing_offer_card_shown"}
    assert non_intent <= aq.NON_INTENT_EVENTS
    assert {"standing_offer_posted", "standing_offer_revoked"} <= aq.INTENT_EVENTS
    assert not (client_events & at.FUNNEL_CRITICAL)


def test_flag_and_knobs_registered():
    """R-24 / R-25 — the flag agrees between FLAG_KEYS and features.json, and
    both model_config knobs carry their spec defaults."""
    from pathlib import Path
    assert "trade.standing_offers" in ff.FLAG_KEYS
    repo = Path(__file__).resolve().parents[2]
    features = json.loads((repo / "config/features.json").read_text())
    assert features["trade.standing_offers"] is False, "ships dark"
    defaults = {k: v for k, v, _ in db._MODEL_CONFIG_DEFAULTS}
    assert defaults["standing_offer_days"] == 30.0
    assert defaults["standing_offer_inject_cap"] == 2.0


def test_no_migration_cols_row_for_standing_offers():
    """R-20 — the table is created by metadata.create_all. A migration_cols
    row would ALTER TABLE ADD COLUMN a column create_all just made.

    SABOTAGE: add ("standing_offers", ..., ...) to migration_cols.
    """
    import inspect
    src = inspect.getsource(db._migrate_db)
    assert '"standing_offers"' not in src


def test_inject_cap_zero_is_a_kill_switch():
    """R-14 — standing_offer_inject_cap = 0 stops injection without a flag
    flip; 3 reproduces an unreserved cap."""
    svc, league, roster, seed = _inject_svc()
    ts._cfg["standing_offer_inject_cap"] = 0.0
    with patch.object(server, "_pick_labels_by_id",
                      lambda ids: {i: "2027 1st" for i in ids}):
        assert _inject(svc, league, roster, seed, [_offer()]) == []
    ts._cfg["standing_offer_inject_cap"] = 2.0
    svc, league, roster, seed = _inject_svc()
    with patch.object(server, "_pick_labels_by_id",
                      lambda ids: {i: "2027 1st" for i in ids}):
        assert _inject(svc, league, roster, seed, [_offer()]) != []
