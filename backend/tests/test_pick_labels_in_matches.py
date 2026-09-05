"""B5 — draft picks must render as labels, not raw ids, on every Matches route.

The Matches serializers name assets out of the `players` table. A draft pick
is never a player row — owned picks live in `draft_picks` (keyed
`{league_id}_{season}_{round}_{original_roster_id}`) and generic ladder rungs
are universal-pool pseudo-assets (`generic_pick_<round>_<tier>`) — so every
pick fell through to the raw-id fallback. `/api/trades/matches` was worse: its
`if pid in players_dict` filter DROPPED unknown ids, so a 2-for-1 serialized
as a 1-for-1 with the name array silently shorter than the id array.

Four routes carry the serializer and all four are covered here:
  GET  /api/trades/matches                              (web)
  GET  /api/trades/matches/all                          (mobile Matches tab)
  GET  /api/trades/awaiting                             (the reported bug)
  POST /api/trades/matches/<id>/disposition             (refresh payload)

The parallel-array invariant (`len(*_names) == len(my_give)`) is the assertion
that catches the DROP class, and it only bites on the two routes that could
drop — `/api/trades/matches` and the disposition refresh. The other two always
produced same-length arrays via `get(pid, pid)`; there the invariant is a cheap
belt-and-braces check and the VALUE assertions are what carry the coverage, so
every route asserts exact strings too. Byte-identity for pick-free payloads
guards the digit-only fast path — a payload of real Sleeper player ids must not
change, and must not cost a `draft_picks` query (proven by a connection spy,
not by an exception the helper would swallow).

The two session-scoped routes resolve names off `sess["players"]`, which is the
ranking POOL, not the player DB. A real player who fell out of that pool is a
pool miss and must still render its NAME via the `players_table` fallback —
the resolution ladder is pool → players_table → pick label → raw id.

Routes are exercised through Flask's test client with an injected session
against an isolated in-memory SQLite engine (test_disposition_route.py /
test_awaiting_dismiss.py pattern). No network, no live DB.
"""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, insert, text

import backend.database as db_module
import backend.server as server
from backend.database import metadata, players_table, trade_matches_table

LEAGUE = "league_b5"
OTHER_LEAGUE = "league_b5_other"
ME = "user_me"
PARTNER = "user_partner"

# Real Sleeper player ids are digit-only — the fast-path guard depends on it.
P_GIVE = "4034"
P_RECV = "6790"
NAMES = {P_GIVE: "Christian McCaffrey", P_RECV: "Justin Jefferson"}

# A REAL player that exists in `players_table` but NOT in the session's
# ranking pool — the shape of a player who dropped out of the DP-valued
# universal pool between the like and the view. It must still render by name.
P_OFFPOOL = "5555"
OFFPOOL_NAME = "Gus Edwards"

# Owned picks: `{league_id}_{season}_{round}_{original_roster_id}`.
PICK = f"{LEAGUE}_2026_1_3"
PICK_TRADED = f"{LEAGUE}_2026_2_7"
PICK_OTHER_LEAGUE = f"{OTHER_LEAGUE}_2027_1_2"
GENERIC = "generic_pick_1_early"
UNKNOWN = "not_a_known_asset"


# ---------------------------------------------------------------------------
# seeding helpers
# ---------------------------------------------------------------------------

def _seed_players(conn):
    # NAMES rows are BOTH in players_table and in the session pool;
    # P_OFFPOOL is in players_table ONLY (see the harness).
    for pid, full_name in list(NAMES.items()) + [(P_OFFPOOL, OFFPOOL_NAME)]:
        conn.execute(insert(players_table).values(
            player_id=pid, full_name=full_name, position="RB", team="SF"))


def _seed_pick(conn, pick_id, *, league_id=LEAGUE, season=2026, rnd=1,
               is_traded=0, original_username=None):
    conn.execute(text(
        "INSERT INTO draft_picks "
        "(pick_id, league_id, season, round, owner_user_id, "
        " original_roster_id, is_traded, original_username, platform) "
        "VALUES (:p, :l, :s, :r, :o, '3', :t, :ou, 'sleeper')"
    ), {"p": pick_id, "l": league_id, "s": season, "r": rnd, "o": ME,
        "t": is_traded, "ou": original_username})


def _seed_members(conn, league_id=LEAGUE):
    """Rosters so load_awaiting_trades can resolve the counterparty by
    receive-player ownership."""
    for uid, roster in ((ME, [P_GIVE]), (PARTNER, [P_RECV])):
        conn.execute(text(
            "INSERT INTO league_members "
            "(league_id, user_id, username, roster_data, updated_at) "
            "VALUES (:l, :u, :u, :r, :t)"
        ), {"l": league_id, "u": uid, "r": json.dumps(roster),
            "t": "2026-08-18T00:00:00"})


def _insert_like(conn, give, receive, *, league_id=LEAGUE, age_days=1):
    created = (datetime.now(timezone.utc).replace(tzinfo=None)
               - timedelta(days=age_days)).isoformat()
    conn.execute(text(
        "INSERT INTO trade_decisions "
        "(user_id, league_id, give_player_ids, receive_player_ids, decision, "
        " created_at, retracted_at) "
        "VALUES (:u, :l, :g, :r, 'like', :c, NULL)"
    ), {"u": ME, "l": league_id, "g": json.dumps(list(give)),
        "r": json.dumps(list(receive)), "c": created})


def _insert_match(conn, give, receive, *, league_id=LEAGUE,
                  b_decision=None):
    """ME is user_a, so my_give == user_a_give."""
    res = conn.execute(insert(trade_matches_table).values(
        league_id       = league_id,
        user_a_id       = ME,
        user_b_id       = PARTNER,
        user_a_give     = json.dumps(list(give)),
        user_a_receive  = json.dumps(list(receive)),
        matched_at      = "2026-08-18T00:00:00",
        status          = "pending",
        user_b_decision = b_decision,
    ))
    return res.inserted_primary_key[0]


# ---------------------------------------------------------------------------
# harness
# ---------------------------------------------------------------------------

@pytest.fixture()
def harness():
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with eng.begin() as conn:
        _seed_players(conn)
        _seed_members(conn)
        _seed_members(conn, OTHER_LEAGUE)

    token = "b5-pick-labels"
    # `/api/trades/matches` needs an INITIALIZED session (league + players +
    # a trade service). The pool is built from NAMES only, so it is a strict
    # SUBSET of players_table — exactly like the live `ranking_pool`, which is
    # the universal DP-valued pool rather than the player DB. Picks are never
    # pool members, and P_OFFPOOL is a real player that is not one either.
    sess = {"verified": True,
        "user_id":       ME,
        "league":        SimpleNamespace(league_id=LEAGUE),
        "players":       [SimpleNamespace(id=pid, name=nm)
                          for pid, nm in NAMES.items()],
        "trade_svcs":    {"1qb_ppr": MagicMock()},
        "active_format": "1qb_ppr",
        "last_active":   0.0,
    }

    server.app.config["TESTING"] = True
    client = server.app.test_client()

    with patch.object(db_module, "engine", eng), \
         patch.object(server, "record_event", MagicMock()), \
         patch.object(server, "save_trade_swipes", MagicMock()), \
         patch.object(server, "create_notification", MagicMock()), \
         patch.object(server, "_send_typed_push", MagicMock()):
        with server._sessions_lock:
            server._sessions[token] = sess
        try:
            yield client, eng, token
        finally:
            with server._sessions_lock:
                server._sessions.pop(token, None)


def _get(client, token, path):
    r = client.get(path, headers={"X-Session-Token": token})
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()


# ---------------------------------------------------------------------------
# 1 — owned pick labels: "2026 1st" / "2026 2nd (from Jared)"
# ---------------------------------------------------------------------------

def test_awaiting_renders_owned_pick_label(harness):
    client, eng, token = harness
    with eng.begin() as conn:
        _seed_pick(conn, PICK)
        _insert_like(conn, [PICK], [P_RECV])

    body = _get(client, token, "/api/trades/awaiting")
    assert len(body) == 1
    assert body[0]["my_give_names"] == ["2026 1st"]
    assert body[0]["my_receive_names"] == [NAMES[P_RECV]]


def test_awaiting_renders_traded_pick_provenance_suffix(harness):
    client, eng, token = harness
    with eng.begin() as conn:
        _seed_pick(conn, PICK_TRADED, season=2026, rnd=2,
                   is_traded=1, original_username="Jared")
        _insert_like(conn, [PICK_TRADED], [P_RECV])

    body = _get(client, token, "/api/trades/awaiting")
    assert body[0]["my_give_names"] == ["2026 2nd (from Jared)"]


def test_matches_all_renders_owned_pick_label(harness):
    client, eng, token = harness
    with eng.begin() as conn:
        _seed_pick(conn, PICK)
        _insert_match(conn, [PICK], [P_RECV])

    body = _get(client, token, "/api/trades/matches/all")
    assert len(body) == 1
    assert body[0]["my_give_names"] == ["2026 1st"]
    assert body[0]["my_receive_names"] == [NAMES[P_RECV]]


def test_matches_all_renders_traded_pick_provenance_suffix(harness):
    client, eng, token = harness
    with eng.begin() as conn:
        _seed_pick(conn, PICK_TRADED, season=2026, rnd=2,
                   is_traded=1, original_username="Jared")
        _insert_match(conn, [PICK_TRADED], [P_RECV])

    body = _get(client, token, "/api/trades/matches/all")
    assert body[0]["my_give_names"] == ["2026 2nd (from Jared)"]


def test_matches_renders_owned_pick_label(harness):
    """The web route — the one that used to DROP the pick entirely."""
    client, eng, token = harness
    with eng.begin() as conn:
        _seed_pick(conn, PICK)
        _insert_match(conn, [P_GIVE, PICK], [P_RECV])

    body = _get(client, token, "/api/trades/matches")
    assert body[0]["my_give_names"] == [NAMES[P_GIVE], "2026 1st"]


# ---------------------------------------------------------------------------
# 2 — the parallel-array invariant, on all four routes
# ---------------------------------------------------------------------------

MIXED_GIVE = [P_GIVE, PICK, GENERIC, UNKNOWN]
MIXED_RECEIVE = [P_RECV, PICK_TRADED]


def _assert_parallel(row):
    assert len(row["my_give_names"]) == len(row["my_give"]), row
    assert len(row["my_receive_names"]) == len(row["my_receive"]), row


def _seed_mixed(eng):
    with eng.begin() as conn:
        _seed_pick(conn, PICK)
        _seed_pick(conn, PICK_TRADED, season=2026, rnd=2,
                   is_traded=1, original_username="Jared")


def test_awaiting_names_stay_index_parallel(harness):
    client, eng, token = harness
    _seed_mixed(eng)
    with eng.begin() as conn:
        _insert_like(conn, MIXED_GIVE, MIXED_RECEIVE)

    row = _get(client, token, "/api/trades/awaiting")[0]
    _assert_parallel(row)
    # An id we cannot resolve still occupies its slot as the raw id.
    assert row["my_give_names"][MIXED_GIVE.index(UNKNOWN)] == UNKNOWN


def test_matches_all_names_stay_index_parallel(harness):
    client, eng, token = harness
    _seed_mixed(eng)
    with eng.begin() as conn:
        _insert_match(conn, MIXED_GIVE, MIXED_RECEIVE)

    row = _get(client, token, "/api/trades/matches/all")[0]
    _assert_parallel(row)
    # Exact values, matching the /api/trades/matches twin — a length-only
    # assertion would pass on a route that emitted the wrong strings.
    assert row["my_give_names"] == [NAMES[P_GIVE], "2026 1st",
                                    "Early 1st Round Pick", UNKNOWN]
    assert row["my_receive_names"] == [NAMES[P_RECV], "2026 2nd (from Jared)"]


def test_matches_names_stay_index_parallel(harness):
    """Regression for the silent 2-for-1 → 1-for-1 shortening."""
    client, eng, token = harness
    _seed_mixed(eng)
    with eng.begin() as conn:
        _insert_match(conn, MIXED_GIVE, MIXED_RECEIVE)

    row = _get(client, token, "/api/trades/matches")[0]
    _assert_parallel(row)
    assert row["my_give_names"] == [NAMES[P_GIVE], "2026 1st",
                                    "Early 1st Round Pick", UNKNOWN]
    assert row["my_receive_names"] == [NAMES[P_RECV], "2026 2nd (from Jared)"]


def test_disposition_refresh_names_stay_index_parallel(harness):
    client, eng, token = harness
    # Cross-league match (session league is LEAGUE) so the in-memory ELO
    # apply is skipped — this test is about the refresh payload only, and it
    # also proves ONE pick query spans leagues.
    with eng.begin() as conn:
        _seed_pick(conn, PICK_OTHER_LEAGUE, league_id=OTHER_LEAGUE,
                   season=2027, rnd=1)
        match_id = _insert_match(
            conn, [P_GIVE, PICK_OTHER_LEAGUE, GENERIC], [P_RECV],
            league_id=OTHER_LEAGUE, b_decision="accept")

    r = client.post(
        f"/api/trades/matches/{match_id}/disposition",
        headers={"X-Session-Token": token, "Content-Type": "application/json"},
        data=json.dumps({"decision": "accept"}),
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["ok"] is True
    row = body["matches"][0]
    _assert_parallel(row)
    assert row["my_give_names"] == [NAMES[P_GIVE], "2027 1st",
                                    "Early 1st Round Pick"]


# ---------------------------------------------------------------------------
# 3 — pick-free payloads are unchanged, and never touch draft_picks
# ---------------------------------------------------------------------------

def test_player_only_payloads_are_unchanged(harness):
    client, eng, token = harness
    with eng.begin() as conn:
        # A pick row EXISTS in the table; a player-only payload must still
        # resolve exactly as before.
        _seed_pick(conn, PICK)
        _insert_like(conn, [P_GIVE], [P_RECV])
        # Deliberately the MIRROR package — a match with the like's own key
        # would mature it out of the Awaiting list.
        _insert_match(conn, [P_RECV], [P_GIVE])

    awaiting = _get(client, token, "/api/trades/awaiting")[0]
    assert awaiting["my_give_names"] == [NAMES[P_GIVE]]
    assert awaiting["my_receive_names"] == [NAMES[P_RECV]]

    m_all = _get(client, token, "/api/trades/matches/all")[0]
    assert m_all["my_give_names"] == [NAMES[P_RECV]]
    assert m_all["my_receive_names"] == [NAMES[P_GIVE]]
    # Team / position enrichment is untouched by this change.
    assert m_all["my_give_teams"] == ["SF"]
    assert m_all["my_give_positions"] == ["RB"]

    m = _get(client, token, "/api/trades/matches")[0]
    assert m["my_give_names"] == [NAMES[P_RECV]]
    assert m["my_receive_names"] == [NAMES[P_GIVE]]


class _ConnectSpy:
    """Engine proxy that COUNTS `connect()` calls.

    The count is the only honest observable here. `_pick_labels_by_id` wraps
    its whole lookup in `except Exception` — so a probe that raises from
    inside the query (patching `Select.where`, say) gets SWALLOWED, the helper
    still returns `{}`, and the assertion passes whether or not the guard
    fired. A counter lives outside the try block and cannot be swallowed.
    """

    def __init__(self, eng):
        self._eng = eng
        self.connects = 0

    def connect(self, *a, **kw):
        self.connects += 1
        return self._eng.connect(*a, **kw)

    def __getattr__(self, name):
        return getattr(self._eng, name)


def test_digit_only_ids_skip_the_pick_query(harness):
    """The hot-path guard: real Sleeper ids are digit-only, so a pick-free
    payload must cost zero draft_picks reads."""
    client, eng, token = harness
    with eng.begin() as conn:
        _seed_pick(conn, PICK)

    spy = _ConnectSpy(eng)
    with patch.object(db_module, "engine", spy):
        assert server._pick_labels_by_id([P_GIVE, P_RECV, "12345"]) == {}
        assert server._pick_labels_by_id([]) == {}
        assert server._pick_labels_by_id(None) == {}
        assert spy.connects == 0, (
            f"digit-only payload opened {spy.connects} connection(s) — the "
            "isdigit() guard at _pick_labels_by_id regressed")

        # Positive control: the spy DOES observe a real lookup, so the zero
        # above is the guard working, not a spy that never sees anything.
        assert server._pick_labels_by_id([PICK]) == {PICK: "2026 1st"}
        assert spy.connects == 1

        # Generic rungs are non-digit but resolve in-process — still no query.
        assert server._pick_labels_by_id([GENERIC]) == {
            GENERIC: "Early 1st Round Pick"}
        assert spy.connects == 1


# ---------------------------------------------------------------------------
# 4 — generic ladder rungs resolve through the shared pool label
# ---------------------------------------------------------------------------

def test_generic_rung_renders_ladder_label(harness):
    client, eng, token = harness
    with eng.begin() as conn:
        _insert_like(conn, [GENERIC], [P_RECV])

    row = _get(client, token, "/api/trades/awaiting")[0]
    assert row["my_give_names"] == ["Early 1st Round Pick"]


def test_helper_resolves_rungs_without_a_db_row(harness):
    client, eng, token = harness
    labels = server._pick_labels_by_id([GENERIC, "generic_pick_2_late"])
    assert labels == {GENERIC: "Early 1st Round Pick",
                      "generic_pick_2_late": "Late 2nd Round Pick"}


# ---------------------------------------------------------------------------
# 5 — pool misses: a real player absent from sess["players"] renders its NAME
#
# `sess["players"]` is the ranking pool (universal DP-valued pool + generic
# rungs), NOT the player DB. A player who drops out of it between the like and
# the view must fall through to players_table, never to the raw id — emitting
# `5555` on the tile is the same bug class B5 exists to remove.
# ---------------------------------------------------------------------------

def test_matches_resolves_pool_miss_player_by_name(harness):
    client, eng, token = harness
    with eng.begin() as conn:
        _seed_pick(conn, PICK)
        _insert_match(conn, [P_GIVE, P_OFFPOOL, PICK], [P_OFFPOOL])

    row = _get(client, token, "/api/trades/matches")[0]
    _assert_parallel(row)
    assert row["my_give_names"] == [NAMES[P_GIVE], OFFPOOL_NAME, "2026 1st"]
    assert row["my_receive_names"] == [OFFPOOL_NAME]


def test_disposition_refresh_resolves_pool_miss_player_by_name(harness):
    client, eng, token = harness
    # Cross-league on purpose: `players_dict` is the ACTIVE session's pool
    # while `matches` is loaded for the MATCH's league, so essentially every
    # id is a pool miss — the worst case for raw-id leakage.
    with eng.begin() as conn:
        _seed_pick(conn, PICK_OTHER_LEAGUE, league_id=OTHER_LEAGUE,
                   season=2027, rnd=1)
        match_id = _insert_match(
            conn, [P_OFFPOOL, PICK_OTHER_LEAGUE], [P_RECV],
            league_id=OTHER_LEAGUE, b_decision="accept")

    r = client.post(
        f"/api/trades/matches/{match_id}/disposition",
        headers={"X-Session-Token": token, "Content-Type": "application/json"},
        data=json.dumps({"decision": "accept"}),
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    row = r.get_json()["matches"][0]
    _assert_parallel(row)
    assert row["my_give_names"] == [OFFPOOL_NAME, "2027 1st"]
    assert row["my_receive_names"] == [NAMES[P_RECV]]


def test_pooled_players_never_hit_the_fallback_lookups(harness):
    """The pool is still the first rung: a fully-pooled payload hands BOTH
    fallback helpers an empty miss set, so neither can cost a query."""
    client, eng, token = harness
    with eng.begin() as conn:
        _insert_match(conn, [P_GIVE], [P_RECV])

    names_spy = MagicMock(wraps=server._player_names_by_id)
    picks_spy = MagicMock(wraps=server._pick_labels_by_id)
    with patch.object(server, "_player_names_by_id", names_spy), \
         patch.object(server, "_pick_labels_by_id", picks_spy):
        row = _get(client, token, "/api/trades/matches")[0]

    assert row["my_give_names"] == [NAMES[P_GIVE]]
    assert row["my_receive_names"] == [NAMES[P_RECV]]
    for spy in (names_spy, picks_spy):
        assert spy.call_count == 1
        assert spy.call_args[0][0] == set(), (
            f"{spy} was handed {spy.call_args[0][0]!r} — pooled players must "
            "short-circuit before the fallback lookups")
