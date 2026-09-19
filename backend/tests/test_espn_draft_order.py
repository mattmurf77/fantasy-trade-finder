"""draft-extensions — ESPN auto-derived rookie draft order.

Seeds the shipped pick-assignment setup step's round-1 order from ESPN's own
final standings, so a user corrects traded picks instead of drag-ordering 12–14
teams by hand.

Sources (binding):
  * `docs/plans/draft-extensions/espn-auto-draft-order-feasibility.md` — the
    live-verified spike against real league 11896 (2026-08-08).
  * The operator decision recorded in `docs/plans/draft-extensions/plan.md`:
    **non-playoff teams order by INVERSE REGULAR-SEASON standings, NOT by
    `rankCalculatedFinal` and NOT by ESPN's consolation ladder.** Playoff teams
    order by `rankCalculatedFinal` (§6c verified it is exactly the post-playoff
    finish there, champion == 1).

`test_11896_non_playoff_ordering_disagrees_with_rank_calculated_final` is that
operator decision made executable: it pins the five slots where the two methods
disagree in real data. If someone "simplifies" the derivation into a single
whole-league `rankCalculatedFinal` sort, that test is what stops them.

The fixture is REAL: `fixtures/espn_league_11896_standings_2026-08-08.json` is
a trimmed verbatim capture of the public v3 `mTeam`+`mSettings` response (see
its `_provenance` key). Only `primaryOwner` is synthesized — real SWIDs
identify real people.
"""
import json
from pathlib import Path

import pytest

import backend.espn_service as es

FIXTURES = Path(__file__).resolve().parent / "fixtures"
L11896 = FIXTURES / "espn_league_11896_standings_2026-08-08.json"
LEGACY = FIXTURES / "espn_league_snapshot_2026-07-11.json"


def _raw():
    return json.loads(L11896.read_text())


def _league():
    return es.parse_league(_raw())


def _team(team_id=1, name="T", wins=5, losses=5, ties=0, points_for=1000.0,
          playoff_seed=1, rank_calculated_final=1):
    """An EspnTeam with every derivation input populated. Override to break."""
    return es.EspnTeam(
        team_id=team_id, name=name, owner_swid=f"{{SWID-{team_id}}}",
        owner_display="", players=[], wins=wins, losses=losses, ties=ties,
        points_for=points_for, playoff_seed=playoff_seed,
        rank_calculated_final=rank_calculated_final)


def _grid(n=8, playoff=4):
    """`n` well-formed teams, seeds 1..n, records descending with seed."""
    return [
        _team(team_id=i, name=f"T{i}", wins=n - i, losses=i - 1,
              points_for=2000.0 - 10 * i, playoff_seed=i,
              # Playoff teams get a plausible final rank; the rest get their
              # seed, which the derivation never reads for them.
              rank_calculated_final=i)
        for i in range(1, n + 1)
    ]


# ---------------------------------------------------------------------------
# 1. parse_league keeps the standings fields (additive)
# ---------------------------------------------------------------------------

def test_parse_league_keeps_record_seed_and_final_rank():
    league = _league()
    assert league["playoff_team_count"] == 6
    by_name = {t.name: t for t in league["teams"]}

    champ = by_name["Black Lives Matter"]
    assert (champ.wins, champ.losses, champ.ties) == (10, 4, 0)
    assert champ.points_for == pytest.approx(1984.11)
    assert champ.playoff_seed == 3
    assert champ.rank_calculated_final == 1        # §6c: champion is rank 1

    worst = by_name["Tyler's unimpressive Team"]
    assert (worst.wins, worst.losses) == (2, 12)
    assert worst.playoff_seed == 14


def test_parse_league_is_additive_for_a_payload_without_standings():
    """The pre-existing fixture still parses; new fields default to None.

    This is the "nothing existing changes shape" guarantee — a caller that
    never asked for standings sees exactly what it saw before.
    """
    league = es.parse_league(json.loads(LEGACY.read_text()))
    assert league["teams"], "legacy fixture must still parse into teams"
    for t in league["teams"]:
        assert t.playoff_seed is None
        assert t.rank_calculated_final is None
        assert t.wins is None and t.losses is None and t.points_for is None
    # And the keys every existing caller reads are untouched.
    assert set(league) >= {"league_id", "name", "season", "total_teams", "teams"}


# ---------------------------------------------------------------------------
# 2. THE 11896 MATRIX — the spike's real data, the operator's real decision
# ---------------------------------------------------------------------------

#: Verbatim from the feasibility doc §6d, left-hand column ("Rule from
#: record.overall+playoffSeed only") — the rule the operator chose.
EXPECTED_11896 = [
    "Tyler's unimpressive Team",     # 1.01  2-12
    "Chubby Chasers",                # 4-10, fewest points-for of the 4-10s
    "Barry McAulkener",              # 4-10
    "Conor's Cuddle Muffins",        # 4-10, most points-for of the 4-10s
    "Sneaky  Fingers",               # 6-8
    "Egbukake",                      # 6-8
    "Team VP",                       # 7-7
    "Kaleb's Team",                  # 7-7  — last non-playoff pick
    "Gandhi's Army",                 # playoff, rankCalculatedFinal 6
    "Hail Mary Jane",                # 5
    "The Humongous Melonheads",      # 4
    "Stinky Fingers",                # 3
    "Bucky Charms",                  # 2
    "Black Lives Matter",            # 14th — the CHAMPION picks last
]


def _derived_names():
    league = _league()
    order = es.derive_espn_draft_order(league["teams"],
                                       league["playoff_team_count"])
    assert order is not None
    by_id = {t.team_id: t for t in league["teams"]}
    return [by_id[tid].name for tid in order]


def test_11896_reproduces_the_spikes_published_order_exactly():
    assert _derived_names() == EXPECTED_11896


def test_11896_champion_picks_last_and_worst_record_picks_first():
    names = _derived_names()
    assert names[0] == "Tyler's unimpressive Team"   # 2-12
    assert names[-1] == "Black Lives Matter"         # rankCalculatedFinal 1


def test_11896_non_playoff_ordering_disagrees_with_rank_calculated_final():
    """THE OPERATOR DECISION, made executable.

    Feasibility doc §6d found the two methods disagree on 5 of the 8
    non-playoff slots in this real league, because ESPN's
    `rankCalculatedFinal` folds in a consolation ladder most dynasty leagues
    treat as meaningless for rookie picks (Conor's Cuddle Muffins went 4-10
    and would pick 8th for winning the bottom bracket).

    So this asserts BOTH halves: what we do produce, and that it is NOT what a
    whole-league `rankCalculatedFinal` sort produces.
    """
    league = _league()
    by_id = {t.team_id: t for t in league["teams"]}
    ours = _derived_names()

    # The rejected alternative: one whole-league sort, worst final rank first.
    alternative = [t.name for t in sorted(
        league["teams"], key=lambda t: -t.rank_calculated_final)]

    # Playoff teams (picks 9-14) and the bottom three (picks 1-3) agree…
    assert ours[:3] == alternative[:3]
    assert ours[8:] == alternative[8:]
    # …and picks 4-8 do not. Five slots, exactly as the spike recorded.
    disagreements = [i for i in range(14) if ours[i] != alternative[i]]
    assert disagreements == [3, 4, 5, 6, 7]

    assert ours[3:8] == ["Conor's Cuddle Muffins", "Sneaky  Fingers",
                         "Egbukake", "Team VP", "Kaleb's Team"]
    assert alternative[3:8] == ["Team VP", "Egbukake", "Sneaky  Fingers",
                                "Kaleb's Team", "Conor's Cuddle Muffins"]

    # The load-bearing case in one line: the consolation-ladder winner does
    # NOT get pushed down the rookie order for winning meaningless games.
    conor = next(t for t in by_id.values()
                 if t.name == "Conor's Cuddle Muffins")
    assert conor.rank_calculated_final == 7     # ESPN says 7th overall…
    assert ours.index(conor.name) == 3          # …we still give it pick 1.04


# ---------------------------------------------------------------------------
# 3. Tiebreaks
# ---------------------------------------------------------------------------

def test_points_for_breaks_a_record_tie_fewer_points_picks_earlier():
    teams = _grid(n=6, playoff=2)
    # Two identically 2-8 non-playoff teams, different points-for.
    teams[4] = _team(team_id=5, name="LOW",  wins=2, losses=8,
                     points_for=900.0, playoff_seed=5, rank_calculated_final=5)
    teams[5] = _team(team_id=6, name="HIGH", wins=2, losses=8,
                     points_for=1500.0, playoff_seed=6, rank_calculated_final=6)
    order = es.derive_espn_draft_order(teams, 2)
    assert order is not None
    names = {t.team_id: t.name for t in teams}
    picks = [names[tid] for tid in order]
    assert picks.index("LOW") < picks.index("HIGH"), \
        "fewer points-for must pick earlier"


def test_playoff_seed_breaks_a_record_and_points_for_tie():
    """Same record AND same points-for: ESPN's own seed decides, worse first.

    This is the documented third key, and it is what makes the order total —
    `playoffSeed` is unique 1..N by construction.
    """
    teams = _grid(n=6, playoff=2)
    teams[4] = _team(team_id=5, name="SEED5", wins=2, losses=8,
                     points_for=1000.0, playoff_seed=5, rank_calculated_final=5)
    teams[5] = _team(team_id=6, name="SEED6", wins=2, losses=8,
                     points_for=1000.0, playoff_seed=6, rank_calculated_final=6)
    order = es.derive_espn_draft_order(teams, 2)
    names = {t.team_id: t.name for t in teams}
    picks = [names[tid] for tid in order]
    assert picks.index("SEED6") < picks.index("SEED5")


def test_a_tie_game_counts_as_half_a_win():
    """7-7-0 and 6-6-2 are both .500 and must not be separated by record.

    ESPN computes `record.overall.percentage` the same way; deriving a
    different win pct here would silently reorder any league that ties.
    """
    teams = _grid(n=6, playoff=2)
    teams[4] = _team(team_id=5, name="TIES", wins=6, losses=6, ties=2,
                     points_for=900.0, playoff_seed=5, rank_calculated_final=5)
    teams[5] = _team(team_id=6, name="NOTIES", wins=7, losses=7, ties=0,
                     points_for=1500.0, playoff_seed=6, rank_calculated_final=6)
    order = es.derive_espn_draft_order(teams, 2)
    names = {t.team_id: t.name for t in teams}
    picks = [names[tid] for tid in order]
    # Records are equal, so points-for decides — NOT the raw win count.
    assert picks.index("TIES") < picks.index("NOTIES")


def test_the_order_is_a_permutation_and_is_deterministic():
    league = _league()
    a = es.derive_espn_draft_order(league["teams"], 6)
    b = es.derive_espn_draft_order(list(reversed(league["teams"])), 6)
    assert a == b, "input order must not affect the result"
    assert sorted(a) == sorted(t.team_id for t in league["teams"])


# ---------------------------------------------------------------------------
# 4. Refusals — None, never a fabricated order
# ---------------------------------------------------------------------------

def test_missing_rank_calculated_final_on_a_playoff_team_returns_none():
    teams = _grid(n=8, playoff=4)
    teams[0].rank_calculated_final = None
    assert es.derive_espn_draft_order(teams, 4) is None


def test_zero_rank_calculated_final_returns_none():
    """ESPN leaves `rankCalculatedFinal` at 0 until the playoffs finish.

    Spike §6b saw exactly this on `rankFinal`/`currentProjectedRank`. A
    mid-season read must refuse, not sort every playoff team onto pick 1.
    """
    teams = _grid(n=8, playoff=4)
    for t in teams:
        t.rank_calculated_final = 0
    assert es.derive_espn_draft_order(teams, 4) is None


def test_duplicate_rank_calculated_final_among_playoff_teams_returns_none():
    teams = _grid(n=8, playoff=4)
    teams[1].rank_calculated_final = teams[0].rank_calculated_final
    assert es.derive_espn_draft_order(teams, 4) is None


def test_a_non_playoff_team_without_a_final_rank_is_still_derivable():
    """Only the playoff group's order reads `rankCalculatedFinal`.

    Requiring it league-wide would refuse leagues we can answer correctly.
    """
    teams = _grid(n=8, playoff=4)
    for t in teams:
        if t.playoff_seed > 4:
            t.rank_calculated_final = None
    order = es.derive_espn_draft_order(teams, 4)
    assert order is not None and len(order) == 8


@pytest.mark.parametrize("field", ["wins", "losses", "ties", "points_for",
                                   "playoff_seed"])
def test_a_partial_record_on_any_team_returns_none(field):
    teams = _grid(n=8, playoff=4)
    setattr(teams[3], field, None)
    assert es.derive_espn_draft_order(teams, 4) is None


def test_a_pre_playoff_season_league_returns_none():
    """Every team 0-0-0 — a league linked before its season is played.

    The grid is complete and well-formed, so only this check catches it.
    """
    teams = [_team(team_id=i, name=f"T{i}", wins=0, losses=0, ties=0,
                   points_for=0.0, playoff_seed=i, rank_calculated_final=i)
             for i in range(1, 9)]
    assert es.derive_espn_draft_order(teams, 4) is None


@pytest.mark.parametrize("count", [None, 0, -1, "", "six", 8, 99])
def test_a_missing_or_impossible_playoff_team_count_returns_none(count):
    """No bracket size ⇒ we cannot tell who made the playoffs.

    `8` and `99` are out of range for an 8-team league: a bracket that holds
    everyone leaves no non-playoff group to pick first.
    """
    assert es.derive_espn_draft_order(_grid(n=8, playoff=4), count) is None


def test_duplicate_playoff_seeds_return_none():
    teams = _grid(n=8, playoff=4)
    teams[5].playoff_seed = teams[4].playoff_seed
    assert es.derive_espn_draft_order(teams, 4) is None


def test_non_positive_playoff_seed_returns_none():
    teams = _grid(n=8, playoff=4)
    teams[2].playoff_seed = 0
    assert es.derive_espn_draft_order(teams, 4) is None


@pytest.mark.parametrize("teams", [None, [], [_team()]])
def test_an_empty_or_single_team_league_returns_none(teams):
    assert es.derive_espn_draft_order(teams, 1) is None


def test_a_brand_new_league_with_no_standings_at_all_returns_none():
    """The new-league / auth-degraded read: fields present, all None."""
    teams = [es.EspnTeam(team_id=i, name=f"T{i}", owner_swid="", owner_display="")
             for i in range(1, 13)]
    assert es.derive_espn_draft_order(teams, 6) is None


# ---------------------------------------------------------------------------
# 5. Payload — `GET /api/league/pick-assignments`
#
# No new route and no new flag: this improves the DEFAULT of the shipped,
# already-gated `picks.assign` flow. It writes nothing, and the user confirms
# or edits before `POST .../order` persists anything.
#
# ESPN is never actually contacted here — `fetch_league` is monkeypatched to
# return the real 11896 capture, the same injection seam `test_espn_service.py`
# uses. `espn_no_network` makes an unexpected call a hard failure.
# ---------------------------------------------------------------------------

from unittest.mock import MagicMock                                    # noqa: E402

from sqlalchemy import create_engine                                   # noqa: E402

import backend.database as db                                          # noqa: E402
import backend.feature_flags as ff                                     # noqa: E402
import backend.server as server                                        # noqa: E402
from backend.database import (                                         # noqa: E402
    metadata, leagues_table, league_members_table,
)

ESPN_LEAGUE = "11896"
LINKED_SEASON = 2025
MY_TEAM_ID = 13                    # "Black Lives Matter" — the champion
IMPORTER = "u-importer"
TOKEN = "test-token-espn-order"


def _member_ids():
    """The member ids the ESPN importer would have written for 11896."""
    return [IMPORTER if t.team_id == MY_TEAM_ID else f"espn:{t.owner_swid}"
            for t in _league()["teams"]]


@pytest.fixture()
def mem_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    with engine.begin() as conn:
        conn.execute(leagues_table.insert().values(
            sleeper_league_id=ESPN_LEAGUE, user_id=IMPORTER,
            name="Newton Dynasty League", season=str(LINKED_SEASON),
            platform="espn", espn_season=LINKED_SEASON, espn_auth="public",
            espn_my_team_id=MY_TEAM_ID, total_rosters=14))
        for uid in _member_ids():
            conn.execute(league_members_table.insert().values(
                league_id=ESPN_LEAGUE, user_id=uid, username=uid,
                display_name=uid, roster_data="[]"))
    db.invalidate_pick_assignment_cache(ESPN_LEAGUE)
    server._SUGGESTED_ORDER_CACHE.clear()
    yield engine
    db.invalidate_pick_assignment_cache(ESPN_LEAGUE)
    server._SUGGESTED_ORDER_CACHE.clear()


class _League:
    league_id = ESPN_LEAGUE
    platform = "espn"
    members = ()


@pytest.fixture()
def client(mem_db):
    server.app.config["TESTING"] = True
    with server._sessions_lock:
        server._sessions[TOKEN] = {
            "verified": True,
            "user_id": IMPORTER, "league": _League(), "players": [],
            "services": {"1qb_ppr": MagicMock()}, "service": MagicMock(),
            "trade_svc": MagicMock(), "active_format": "1qb_ppr",
            "last_active": 0.0,
        }
    try:
        yield server.app.test_client()
    finally:
        with server._sessions_lock:
            server._sessions.pop(TOKEN, None)


@pytest.fixture()
def flag_on():
    saved = ff._flags_cache
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "picks.assign": True}
    try:
        yield
    finally:
        ff._flags_cache = saved


@pytest.fixture()
def espn_ok(monkeypatch):
    """ESPN answers with the real 11896 capture. Records the calls made."""
    calls = []

    def _fetch(league_id, season, **kw):
        calls.append((str(league_id), int(season)))
        return _raw()

    monkeypatch.setattr(es, "fetch_league", _fetch)
    return calls


@pytest.fixture()
def espn_no_network(monkeypatch):
    """Any ESPN read is a test failure — proves a path makes no request."""
    def _boom(*a, **kw):
        raise AssertionError("ESPN must not be contacted on this path")
    monkeypatch.setattr(es, "fetch_league", _boom)


def _hdr():
    return {"X-Session-Token": TOKEN, "Content-Type": "application/json"}


def _get(client):
    return client.get(
        f"/api/league/pick-assignments?league_id={ESPN_LEAGUE}", headers=_hdr())


def test_payload_carries_the_suggested_order_for_an_espn_league(
        client, flag_on, espn_ok):
    body = _get(client).get_json()

    assert body["suggested_order_source"] == "espn_standings"
    assert body["suggested_order_season"] == LINKED_SEASON

    # Member ids in pick order — drops straight into `settings.order`.
    order = body["suggested_order"]
    assert sorted(order) == sorted(_member_ids())
    by_id = {t.team_id: t for t in _league()["teams"]}
    expected = [IMPORTER if tid == MY_TEAM_ID else f"espn:{by_id[tid].owner_swid}"
                for tid in es.derive_espn_draft_order(_league()["teams"], 6)]
    assert order == expected
    # The champion is the caller's own team, and it picks last.
    assert order[-1] == IMPORTER


def test_the_breakdown_explains_every_pick(client, flag_on, espn_ok):
    body = _get(client).get_json()
    detail = body["suggested_order_detail"]
    assert len(detail) == 14
    assert [d["pick"] for d in detail] == list(range(1, 15))
    assert [d["user_id"] for d in detail] == body["suggested_order"]

    first, last = detail[0], detail[-1]
    assert first["team_name"] == "Tyler's unimpressive Team"
    assert (first["wins"], first["losses"]) == (2, 12)
    assert first["made_playoffs"] is False
    assert last["team_name"] == "Black Lives Matter"
    assert last["made_playoffs"] is True
    assert last["final_rank"] == 1
    # Exactly the bracket size ESPN reported.
    assert sum(1 for d in detail if d["made_playoffs"]) == 6
    # D13 holds here too — a caption is not a price.
    assert not any(k in first for k in
                   ("value", "pool_value", "pick_value", "elo", "price"))


def test_a_saved_order_is_never_overwritten_and_costs_no_espn_read(
        client, flag_on, espn_no_network):
    """Once the league has an order of its own, the keys never appear again.

    `espn_no_network` is the assertion that matters: the suggestion is not
    computed-then-hidden, it is not computed at all.
    """
    db.save_pick_assignment_settings(ESPN_LEAGUE, {
        "rounds": 4, "order_type": "linear", "order": _member_ids()})
    body = _get(client).get_json()
    assert "suggested_order" not in body
    assert body["settings"]["order"] == _member_ids()


def test_a_non_espn_league_never_carries_a_suggested_order(
        client, flag_on, espn_no_network, mem_db):
    with mem_db.begin() as conn:
        conn.execute(leagues_table.update()
                     .where(leagues_table.c.sleeper_league_id == ESPN_LEAGUE)
                     .values(platform="sleeper"))
    body = _get(client).get_json()
    assert "suggested_order" not in body
    assert "suggested_order_source" not in body


def test_an_espn_league_that_was_never_linked_makes_no_request(
        client, flag_on, espn_no_network, mem_db):
    """No `espn_season` ⇒ no season to read, and we do not guess one."""
    with mem_db.begin() as conn:
        conn.execute(leagues_table.update()
                     .where(leagues_table.c.sleeper_league_id == ESPN_LEAGUE)
                     .values(espn_season=None))
    assert "suggested_order" not in _get(client).get_json()


def test_espn_being_down_leaves_the_board_working(client, flag_on, monkeypatch):
    """Fail soft: the suggestion vanishes, the payload is otherwise intact."""
    monkeypatch.setattr(es, "fetch_league", MagicMock(
        side_effect=es.EspnError("boom", kind="http")))
    resp = _get(client)
    assert resp.status_code == 200
    body = resp.get_json()
    assert "suggested_order" not in body
    assert set(body) == {"league_id", "settings", "seasons", "progress", "seeded"}


def test_a_pre_season_snapshot_falls_back_one_season(client, flag_on,
                                                     monkeypatch, mem_db):
    """A league linked pre-season reads 0-0-0 for the linked year.

    The derivation refuses that (correctly), so the route tries exactly one
    season back — which is the season a rookie draft actually orders off.
    """
    blank = _raw()
    for t in blank["teams"]:
        t["record"]["overall"].update(wins=0, losses=0, ties=0, pointsFor=0.0)
        t["rankCalculatedFinal"] = 0

    with mem_db.begin() as conn:
        conn.execute(leagues_table.update()
                     .where(leagues_table.c.sleeper_league_id == ESPN_LEAGUE)
                     .values(espn_season=LINKED_SEASON + 1))

    seen = []

    def _fetch(league_id, season, **kw):
        seen.append(int(season))
        return blank if int(season) == LINKED_SEASON + 1 else _raw()

    monkeypatch.setattr(es, "fetch_league", _fetch)
    body = _get(client).get_json()
    assert seen == [LINKED_SEASON + 1, LINKED_SEASON]
    assert body["suggested_order_season"] == LINKED_SEASON
    assert body["suggested_order"][0] == "espn:{SWID-10}"      # Tyler, 2-12


def test_a_membership_mismatch_suppresses_the_suggestion(
        client, flag_on, espn_ok, mem_db):
    """A team that left ⇒ the derived order is not this league's order.

    Half-right is worse than absent: the client already orders manually.
    """
    with mem_db.begin() as conn:
        conn.execute(league_members_table.delete().where(
            league_members_table.c.user_id == "espn:{SWID-10}"))
    assert "suggested_order" not in _get(client).get_json()


def test_the_existing_payload_is_unchanged_apart_from_the_new_keys(
        client, flag_on, espn_ok):
    """The four shipped data keys keep their exact shipped values."""
    with_suggestion = _get(client).get_json()
    server._SUGGESTED_ORDER_CACHE.clear()
    db.save_pick_assignment_settings(ESPN_LEAGUE, {
        "rounds": 4, "order_type": "linear", "order": _member_ids()})
    without = _get(client).get_json()

    for key in ("league_id", "seasons", "progress", "seeded"):
        assert with_suggestion[key] == without[key]
    # The suggestion NEVER edits `settings` — it is a proposal the client
    # renders, not state the server has adopted.
    assert with_suggestion["settings"]["order"] != with_suggestion["suggested_order"]


def test_the_derivation_is_cached_so_repeat_loads_do_not_hammer_espn(
        client, flag_on, espn_ok):
    for _ in range(4):
        assert "suggested_order" in _get(client).get_json()
    assert espn_ok == [(ESPN_LEAGUE, LINKED_SEASON)], \
        "four screen loads must cost exactly one ESPN read"
