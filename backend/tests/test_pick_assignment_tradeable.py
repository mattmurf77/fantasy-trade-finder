"""draft-extensions W3 M-C — asserted picks priced across all seven read sites.

Plan `docs/plans/draft-extensions/plan.md` §6.4 + operator decision 4 (**full
engine parity** — all seven sites light up, including `_roster_eveners` and
generated suggestions; S1→S4 is a BUILD SEQUENCE, not a set of release gates);
LLD §4.5; the delivered M-A contract in
`docs/plans/draft-extensions/build-w3-ma-mb.md`.

M-A shipped the store with the containment being the READ DEFAULT. This wave
is the opt-in, and everything it can break is pinned here:

  * **D10.** `picks.assign_tradeable` OFF ⇒ a fully asserted grid changes
    NOTHING — all seven sites, `/api/league/picks`, `/api/trade/evaluate`,
    power rankings and the ESPN board are byte-identical to a league with no
    assertions at all.
  * **D13.** No user-entered values reach a price, under BOTH `M6b` pricing
    modes (`tier_ladder` and `market_slots`) at the sites that actually price.
  * **D17.** Provenance is inescapable: `source: "platform" | "user"` on every
    payload that prices a pick — and a combo evener inherits it.
  * **INV-5.** Contested/orphaned slots leave the priced union by ROW FILTER,
    never by nulling `pool_value` (`_power_picks_by_owner` re-derives a price
    from a NULL, so nulling would re-price the very row the rule withholds).
  * **The one guard.** `_owned_picks_available` replaced two duplicated
    THREE-clause literals; dropping either of the other two conjuncts would
    silently re-enable picks for the demo league or with
    `trade.picks_in_pool` off.
"""
import json

import pytest
from sqlalchemy import create_engine
from unittest.mock import MagicMock

import backend.database as db
import backend.feature_flags as ff
import backend.server as server
import backend.trade_service as ts
from backend.database import (
    metadata, leagues_table, league_members_table, draft_picks_table,
)
from backend.pick_values import priced_pool_value

LEAGUE = "1088776655443322110"          # numeric — an ESPN-shaped league id
ME = "u1"
MEMBERS = ["u1", "u2", "u3", "u4"]
NAMES = {u: f"Team {u}" for u in MEMBERS}
SEASON = 2026
TOKEN = "test-token-w3-mc"


# ---------------------------------------------------------------------------
# harness — in-memory SQLite throughout; data/trade_finder.db is never opened
# ---------------------------------------------------------------------------

@pytest.fixture()
def mem_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    with engine.begin() as conn:
        conn.execute(leagues_table.insert().values(
            sleeper_league_id=LEAGUE, user_id=ME, name="Sunday Sickos",
            season=str(SEASON), platform="espn", total_rosters=len(MEMBERS)))
        for uid in MEMBERS:
            conn.execute(league_members_table.insert().values(
                league_id=LEAGUE, user_id=uid, username=NAMES[uid],
                display_name=NAMES[uid], roster_data="[]"))
    db.invalidate_pick_assignment_cache(LEAGUE)
    server._invalidate_draft_context_cache()
    yield engine
    db.invalidate_pick_assignment_cache(LEAGUE)
    server._invalidate_draft_context_cache()


class _League:
    league_id = LEAGUE
    platform = "espn"
    members = ()


@pytest.fixture()
def client(mem_db):
    server.app.config["TESTING"] = True
    sess = {
        "user_id": ME, "league": _League(), "players": [],
        "services": {"1qb_ppr": MagicMock()}, "service": MagicMock(),
        "trade_svc": MagicMock(), "active_format": "1qb_ppr",
        "last_active": 0.0,
    }
    with server._sessions_lock:
        server._sessions[TOKEN] = sess
    try:
        yield server.app.test_client()
    finally:
        with server._sessions_lock:
            server._sessions.pop(TOKEN, None)


@pytest.fixture()
def flags():
    """Pin the flag map; `set(**kw)` re-pins mid-test."""
    saved = ff._flags_cache

    def _set(**kw):
        ff._flags_cache = {**ff.DEFAULT_FLAGS, "picks.assign": True,
                           "draft.room": True, "trade.picks_in_pool": True,
                           **kw}
        return ff._flags_cache

    _set()
    try:
        yield _set
    finally:
        ff._flags_cache = saved


def _hdr():
    return {"X-Session-Token": TOKEN, "Content-Type": "application/json"}


def _seed(client, rounds=2, **body):
    return client.post("/api/league/pick-assignments/order", headers=_hdr(),
                       data=json.dumps({"league_id": LEAGUE, "rounds": rounds,
                                        **body}))


def _picks(client):
    return client.get(f"/api/league/picks?league_id={LEAGUE}", headers=_hdr())


#: A slot label no member holds, so a platform row and an asserted row cannot
#: collide on `pick_id` (whose unique key has no provenance dimension).
_PLATFORM_SLOT = "99"


def _platform_rows(n=2, slot=_PLATFORM_SLOT):
    return [{
        "pick_id": db.make_pick_id(LEAGUE, SEASON, r, slot),
        "league_id": LEAGUE, "season": SEASON, "round": r,
        "owner_user_id": ME, "owner_username": NAMES[ME],
        "original_roster_id": slot, "original_user_id": ME,
        "original_username": NAMES[ME], "is_traded": 0,
        "pick_value": 10.0 * r, "pool_value": 100.0 * r,
        "platform": "sleeper", "synced_at": "2026-08-01T00:00:00+00:00",
    } for r in range(1, n + 1)]


def _an_asserted_pick_id():
    """The 2026 1st of the member holding slot label "1"."""
    return db.make_pick_id(LEAGUE, SEASON, 1, "1")


# ---------------------------------------------------------------------------
# D10 — the flag OFF is the whole containment story
# ---------------------------------------------------------------------------

def _snapshot(client):
    """Every read site that can be exercised without a full trade job.

    `_run_trade_job`'s opponent-share block and `_inject_owned_picks` are
    covered through the helpers they call (`load_draft_picks` via
    `_pick_read_source`, `_owned_pick_assets`) plus the AST pin in
    `test_pick_assignment.py`.
    """
    return {
        # the shared loader every site funnels through, both shapes
        "load":      json.dumps(db.load_draft_picks(
            league_id=LEAGUE, source=server._pick_read_source()),
            sort_keys=True, default=str),
        "load_own":  json.dumps(db.load_draft_picks(
            league_id=LEAGUE, owner_user_id=ME,
            source=server._pick_read_source()), sort_keys=True, default=str),
        "share":     server._user_pick_share(ME, LEAGUE),             # S2
        "power":     json.dumps(server._power_picks_by_owner(LEAGUE, "1qb_ppr"),
                                sort_keys=True),                      # S2
        "assets":    sorted(                                          # S3
            (o, p.id, p.name, p.pick_value)
            for o, ps in server._owned_pick_assets(LEAGUE, "1qb_ppr").items()
            for p in ps),
        "eveners":   json.dumps(server._roster_eveners(               # S4
            LEAGUE, ME, 500.0, set(), [], lambda pid: 0.0),
            sort_keys=True),
        "picks":     json.dumps(_picks(client).get_json(), sort_keys=True),  # S1
    }


def test_mc_01_flag_off_is_byte_identical_on_every_read_site(client, flags):
    """D10 — a FULL asserted grid, and with the kill switch off not one byte
    of any read site moves."""
    flags(**{"picks.assign_tradeable": False})
    db.replace_draft_picks(LEAGUE, _platform_rows())

    before = _snapshot(client)
    assert _seed(client, rounds=2).status_code == 200
    assert len(db.load_draft_picks(league_id=LEAGUE,
                                   source=db.PICK_SOURCE_USER)) == \
        2 * len(MEMBERS) * 4
    assert _snapshot(client) == before


def test_mc_01b_flag_off_evaluate_is_byte_identical(client, flags, monkeypatch):
    """D10, the site the golden snapshot cannot reach without the pool."""
    flags(**{"picks.assign_tradeable": False})
    monkeypatch.setattr(server, "_ensure_universal_pools", lambda: None)
    monkeypatch.setitem(server.g_universal_by_format, "1qb_ppr",
                        {"players": [], "seed": {"stud": 1800.0}})
    pick_id = _an_asserted_pick_id()

    def _evaluate():
        return client.post("/api/trade/evaluate", headers=_hdr(),
                           data=json.dumps({
                               "give_player_ids": ["stud"],
                               "receive_player_ids": [pick_id],
                               "league_id": LEAGUE})).get_json()

    before = _evaluate()
    _seed(client, rounds=2)
    assert _evaluate() == before
    # …and the asserted pick is still an UNKNOWN id to the calculator.
    assert pick_id in before["dropped_player_ids"]


def test_mc_01c_the_espn_room_is_untouched_by_the_tradeable_flag(client, flags):
    """M-C moves trade math, never the Draft Room. `picks.assign` owns the
    room; flipping the second flag either way must not change it."""
    _seed(client, rounds=2)

    def _board():
        body = client.get(f"/api/draft/board?league_id={LEAGUE}",
                          headers=_hdr()).get_json()
        body.pop("as_of", None)
        return json.dumps(body, sort_keys=True)

    flags(**{"picks.assign_tradeable": False})
    off = _board()
    flags(**{"picks.assign_tradeable": True})
    assert _board() == off


# ---------------------------------------------------------------------------
# S1 → S4, each stage verified on its own (the build sequence)
# ---------------------------------------------------------------------------

def test_mc_02_s1_league_picks_serves_asserted_rows_and_flips_supported(
        client, flags):
    """S1a — and `picks_supported` becomes a DATA test."""
    flags(**{"picks.assign_tradeable": True})
    # ESPN with NOTHING assigned still honestly reports false…
    empty = _picks(client).get_json()
    assert empty["picks_supported"] is False
    assert empty["all_picks"] == []

    _seed(client, rounds=2)
    body = _picks(client).get_json()
    assert body["picks_supported"] is True
    assert len(body["all_picks"]) == 2 * len(MEMBERS) * 4
    assert body["my_picks"] and all(p["owner_user_id"] == ME
                                    for p in body["my_picks"])


def test_mc_02b_supported_stays_a_platform_test_for_demo_and_no_league(
        client, flags):
    """The demo / no-league early return keeps the PLATFORM test — there is no
    league to ask the data question about."""
    flags(**{"picks.assign_tradeable": True})
    body = client.get("/api/league/picks?league_id=league_demo",
                      headers=_hdr()).get_json()
    assert body == {"my_picks": [], "all_picks": [], "picks_supported": False}


def test_mc_03_s1_evaluate_prices_an_asserted_pick(client, flags, monkeypatch):
    """S1b — the calculator resolves an asserted pick_id instead of dropping
    it, and prices it at the shipped function's value."""
    flags(**{"picks.assign_tradeable": True})
    monkeypatch.setattr(server, "_ensure_universal_pools", lambda: None)
    monkeypatch.setitem(server.g_universal_by_format, "1qb_ppr",
                        {"players": [], "seed": {"stud": 1800.0}})
    _seed(client, rounds=2)
    pick_id = _an_asserted_pick_id()
    row = next(r for r in db.load_draft_picks(league_id=LEAGUE,
                                              source=db.PICK_SOURCE_USER)
               if r["pick_id"] == pick_id)

    body = client.post("/api/trade/evaluate", headers=_hdr(), data=json.dumps({
        "give_player_ids": ["stud"], "receive_player_ids": [pick_id],
        "league_id": LEAGUE})).get_json()

    assert pick_id not in body["dropped_player_ids"]
    per = {p["player_id"]: p for p in body["per_player"]}
    assert per[pick_id]["value"] == pytest.approx(
        priced_pool_value(row, scoring_format="1qb_ppr"), abs=0.1)


def test_mc_04_s2_power_rankings_and_pick_share_see_asserted_capital(
        client, flags):
    """S2 — draft capital shows up in standings and in the user's own outlook
    seed instead of reading as zero."""
    flags(**{"picks.assign_tradeable": True})
    assert server._user_pick_share(ME, LEAGUE) == 0.0
    _seed(client, rounds=2)

    powered = server._power_picks_by_owner(LEAGUE, "1qb_ppr")
    assert set(powered) == set(MEMBERS)
    assert all(item["value"] > 0 for items in powered.values() for item in items)
    # A pristine grid is an equal split, which is also the conservation bound
    # showing through: four teams, one quarter each.
    assert server._user_pick_share(ME, LEAGUE) == pytest.approx(0.25, abs=1e-6)


def test_mc_05_s3_owned_pick_assets_injects_asserted_picks(client, flags):
    """S3a — asserted picks become candidate assets for GENERATED suggestions
    (operator decision 4 overrode both lenses' hold here)."""
    flags(**{"picks.assign_tradeable": True})
    assert server._owned_pick_assets(LEAGUE, "1qb_ppr") == {}
    _seed(client, rounds=2)

    assets = server._owned_pick_assets(LEAGUE, "1qb_ppr")
    assert set(assets) == set(MEMBERS)
    for owner_assets in assets.values():
        assert owner_assets and all(a.position == "PICK" for a in owner_assets)
        assert len(owner_assets) <= server._picks_pool_cap()


def test_mc_06_s3b_opponent_pick_shares_read_the_same_union(client, flags):
    """S3b — the trade job's opponent-share block is an inline read through
    the same helper (the AST test pins the wiring; this pins the behaviour)."""
    _seed(client, rounds=2)
    flags(**{"picks.assign_tradeable": False})
    assert db.load_draft_picks(league_id=LEAGUE,
                               source=server._pick_read_source()) == []
    flags(**{"picks.assign_tradeable": True})
    rows = db.load_draft_picks(league_id=LEAGUE,
                               source=server._pick_read_source())
    owners = {r["owner_user_id"] for r in rows}
    assert owners == set(MEMBERS)          # every opponent has a share now


def test_mc_07_s4_eveners_offer_an_asserted_pick(client, flags):
    """S4 — the highest-blast-radius site: a one-tap sweetener may name an
    asserted pick."""
    flags(**{"picks.assign_tradeable": True})
    _seed(client, rounds=2)
    row = next(r for r in db.load_draft_picks(league_id=LEAGUE,
                                              source=db.PICK_SOURCE_USER)
               if r["owner_user_id"] == ME)
    gap = float(row["pool_value"])

    out = server._roster_eveners(LEAGUE, ME, gap, set(), [], lambda pid: 0.0)
    picks = [e for e in out if e.get("is_pick")]
    assert picks, "no asserted pick reached the evener list"
    assert all(e["source"] in ("user", "platform") for e in picks)


# ---------------------------------------------------------------------------
# D13 — no user-entered values, under BOTH pricing modes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode", ["tier_ladder", "market_slots"])
def test_mc_08_asserted_prices_are_the_shipped_function_at_the_read_sites(
        client, flags, monkeypatch, mode):
    """D13 restated against the code that actually prices (LLD §4.5.4).

    Two of the seven price through `priced_pool_value`, which is mode-aware.
    Both modes are named, and every price must be reproducible from the
    pick's COORDINATES alone — never from anything a user typed.
    """
    flags(**{"picks.assign_tradeable": True, "trade.slot_pricing": True})
    monkeypatch.setattr(server, "_ensure_universal_pools", lambda: None)
    monkeypatch.setitem(server.g_universal_by_format, "1qb_ppr",
                        {"players": [], "seed": {"stud": 1800.0}})
    _seed(client, rounds=2)
    rows = {r["pick_id"]: r for r in
            db.load_draft_picks(league_id=LEAGUE, source=db.PICK_SOURCE_USER)}
    assert rows

    with ts.pick_pricing_override(mode):
        assets = server._owned_pick_assets(LEAGUE, "1qb_ppr")
        pick_id = _an_asserted_pick_id()
        body = client.post("/api/trade/evaluate", headers=_hdr(),
                           data=json.dumps({
                               "give_player_ids": ["stud"],
                               "receive_player_ids": [pick_id],
                               "league_id": LEAGUE})).get_json()

    expected = {pid: priced_pool_value({"season": r["season"],
                                        "round": r["round"],
                                        "pool_value": r["pool_value"]},
                                       scoring_format="1qb_ppr", mode=mode)
                for pid, r in rows.items()}
    per = {p["player_id"]: p["value"] for p in body["per_player"]}
    assert per[pick_id] == pytest.approx(expected[pick_id], abs=0.1)
    for owner_assets in assets.values():
        for a in owner_assets:
            round_trip = ts.elo_to_value(1200.0 + 6.0 * float(a.pick_value))
            assert round_trip == pytest.approx(expected[a.id], abs=1.0)


# ---------------------------------------------------------------------------
# D17 — provenance is inescapable
# ---------------------------------------------------------------------------

def test_mc_09_provenance_on_all_four_priced_payloads(client, flags,
                                                      monkeypatch):
    """D17 — `source` on `/api/league/picks` rows, `/api/trade/evaluate`
    per-player entries, `_roster_eveners` items and power-rankings items.

    A NULL column reads as `"platform"` on the wire: the enum has exactly two
    members and no null, so a client can switch on it exhaustively.
    """
    flags(**{"picks.assign_tradeable": True})
    monkeypatch.setattr(server, "_ensure_universal_pools", lambda: None)
    monkeypatch.setitem(server.g_universal_by_format, "1qb_ppr",
                        {"players": [], "seed": {"stud": 1800.0}})
    db.replace_draft_picks(LEAGUE, _platform_rows())
    _seed(client, rounds=2)
    pick_id = _an_asserted_pick_id()
    platform_pick_id = db.make_pick_id(LEAGUE, SEASON, 1, _PLATFORM_SLOT)

    # 1 — /api/league/picks
    rows = {p["pick_id"]: p for p in _picks(client).get_json()["all_picks"]}
    assert rows[pick_id]["source"] == "user"
    assert rows[platform_pick_id]["source"] == "platform"   # NULL → platform
    assert all(r["source"] in ("user", "platform") for r in rows.values())

    # 2 — /api/trade/evaluate per-player entries
    body = client.post("/api/trade/evaluate", headers=_hdr(), data=json.dumps({
        "give_player_ids": ["stud"],
        "receive_player_ids": [pick_id, platform_pick_id],
        "league_id": LEAGUE})).get_json()
    per = {p["player_id"]: p for p in body["per_player"]}
    assert per[pick_id]["source"] == "user"
    assert per[platform_pick_id]["source"] == "platform"
    # the correction deep link is {leagueId, season, focusPickId} — season
    # rides along or the badge is a dead end
    assert per[pick_id]["season"] == SEASON
    # a PLAYER is not a pick and carries no provenance at all
    assert "source" not in per["stud"]

    # 3 — _roster_eveners items
    row = next(r for r in db.load_draft_picks(league_id=LEAGUE,
                                              source=db.PICK_SOURCE_USER)
               if r["owner_user_id"] == ME)
    eveners = server._roster_eveners(LEAGUE, ME, float(row["pool_value"]),
                                     set(), [], lambda pid: 0.0)
    for e in (e for e in eveners if e.get("is_pick")):
        assert e["source"] in ("user", "platform") and "season" in e

    # 4 — power-rankings pick items
    powered = server._power_picks_by_owner(LEAGUE, "1qb_ppr")
    items = [i for its in powered.values() for i in its]
    assert items and all(i["source"] in ("user", "platform") for i in items)
    assert all(i["pick_id"] and i["season"] for i in items)


def test_mc_09b_a_combo_evener_inherits_user_provenance(client, flags):
    """A member-entered pick riding inside a 2-piece combo must not lose its
    badge — otherwise the label the user sees on the single row silently
    disappears when the same asset is bundled."""
    flags(**{"picks.assign_tradeable": True})
    _seed(client, rounds=2)
    mine = [r for r in db.load_draft_picks(league_id=LEAGUE,
                                           source=db.PICK_SOURCE_USER)
            if r["owner_user_id"] == ME]
    # A gap just above the two best picks combined forces the pair branch.
    top = sorted((float(r["pool_value"]) for r in mine), reverse=True)[:2]
    out = server._roster_eveners(LEAGUE, ME, sum(top), set(), [],
                                 lambda pid: 0.0)
    combos = [e for e in out if e.get("is_package")]
    assert combos, "the pair branch did not fire — the fixture needs a re-think"
    assert all(c["source"] == "user" for c in combos)


def test_mc_09c_provenance_disappears_entirely_with_the_flag_off(
        client, flags, monkeypatch):
    """The kill switch removes the FIELDS too, on all four payloads.

    The golden test compares one build against itself, so it cannot see a key
    that is added unconditionally — this is the assertion that does. A payload
    that gained a key with the flag off would not be byte-identical to the
    pre-M-C tree, and D10 is the whole containment claim.
    """
    _seed(client, rounds=2)
    flags(**{"picks.assign_tradeable": False})
    monkeypatch.setattr(server, "_ensure_universal_pools", lambda: None)
    monkeypatch.setitem(server.g_universal_by_format, "1qb_ppr",
                        {"players": [], "seed": {"stud": 1800.0}})
    db.replace_draft_picks(LEAGUE, _platform_rows())
    platform_pick_id = db.make_pick_id(LEAGUE, SEASON, 1, _PLATFORM_SLOT)

    # 1 — /api/league/picks carries the RAW column (NULL), not the wire enum
    rows = _picks(client).get_json()["all_picks"]
    assert rows and all(r["source"] is None for r in rows)

    # 2 — evaluate per-player entries keep their three keys
    body = client.post("/api/trade/evaluate", headers=_hdr(), data=json.dumps({
        "give_player_ids": ["stud"], "receive_player_ids": [platform_pick_id],
        "league_id": LEAGUE})).get_json()
    for entry in body["per_player"]:
        assert set(entry) == {"player_id", "side", "value"}

    # 3 — evener items
    eveners = server._roster_eveners(LEAGUE, ME, 100.0, set(), [],
                                     lambda pid: 0.0)
    for e in eveners:
        assert "source" not in e and "season" not in e

    # 4 — power-rankings items
    powered = server._power_picks_by_owner(LEAGUE, "1qb_ppr")
    for item in (i for its in powered.values() for i in its):
        assert set(item) == {"label", "value"}


# ---------------------------------------------------------------------------
# INV-5 — contested leaves the priced union by ROW FILTER
# ---------------------------------------------------------------------------

def _make_contested(client, pick_id):
    """Two DIFFERENT actors assign the SAME slot to two DIFFERENT owners."""
    body = client.get(f"/api/league/pick-assignments?league_id={LEAGUE}",
                      headers=_hdr()).get_json()
    slot = next(s for season in body["seasons"] for s in season["slots"]
                if s["pick_id"] == pick_id)
    assert client.put(f"/api/league/pick-assignments/{pick_id}", headers=_hdr(),
                      data=json.dumps({"league_id": LEAGUE,
                                       "owner_user_id": "u2",
                                       "if_assigned_at": slot["assigned_at"]})
                      ).status_code == 200
    fresh = next(s for season in
                 client.get(f"/api/league/pick-assignments?league_id={LEAGUE}",
                            headers=_hdr()).get_json()["seasons"]
                 for s in season["slots"] if s["pick_id"] == pick_id)
    db.assign_draft_pick(LEAGUE, pick_id, "u3", "Team u3", "u4",
                         fresh["assigned_at"])
    db.record_event("u4", "pick_assignment_changed", league_id=LEAGUE, props={
        "pick_id": pick_id, "actor": "u4", "new_owner": "u3"})
    db.invalidate_pick_assignment_cache(LEAGUE)
    assert pick_id in db.contested_pick_ids(LEAGUE)


def test_mc_10_contested_is_row_filtered_out_of_every_priced_read(client,
                                                                  flags):
    """INV-5, stated as the failure it prevents.

    The rule is "excluded from the priced union", and the ONLY correct
    implementation is a row filter: `_power_picks_by_owner` re-derives a price
    when `pool_value` is NULL, so the naive "unprice it by nulling the column"
    version would price the exact row the rule withholds. Both halves are
    asserted — the filter removes it, and nulling demonstrably does not.
    """
    flags(**{"picks.assign_tradeable": True})
    _seed(client, rounds=2)
    pick_id = _an_asserted_pick_id()
    _make_contested(client, pick_id)

    def _priced_ids():
        powered = server._power_picks_by_owner(LEAGUE, "1qb_ppr")
        return {i["pick_id"] for its in powered.values() for i in its}

    assert pick_id not in _priced_ids()
    assert pick_id not in {p["pick_id"]
                           for p in _picks(client).get_json()["all_picks"]}
    assert pick_id not in {a.id for assets in
                           server._owned_pick_assets(LEAGUE, "1qb_ppr").values()
                           for a in assets}
    # …but the stored price is untouched, which is what makes the exclusion
    # reversible the moment somebody resolves the disagreement.
    still = db.load_draft_picks(league_id=LEAGUE, source=db.PICK_SOURCE_USER,
                                include_contested=True)
    assert next(r for r in still
                if r["pick_id"] == pick_id)["pool_value"] is not None

    # The forbidden implementation, demonstrated failing.
    with db.engine.begin() as conn:
        conn.execute(draft_picks_table.update()
                     .where(draft_picks_table.c.pick_id == pick_id)
                     .values(pool_value=None))
    db.invalidate_pick_assignment_cache(LEAGUE)
    with_nulled = server._power_picks_by_owner(LEAGUE, "1qb_ppr")
    nulled_rows = [i for its in with_nulled.values() for i in its
                   if i["pick_id"] == pick_id]
    assert not nulled_rows, (
        "the row filter must still hold with pool_value NULL — and note that "
        "if the filter were REPLACED by nulling, this row would be re-priced "
        "by the NULL branch of _power_picks_by_owner (INV-5)")


def test_mc_10b_the_null_branch_that_makes_nulling_unsafe_still_exists(client,
                                                                      flags):
    """The mutation the rule guards against, run directly: a `source='user'`
    row that is NOT contested but HAS a NULL price is silently re-priced. That
    is the behaviour INV-5 exists for, so it is pinned rather than assumed."""
    flags(**{"picks.assign_tradeable": True})
    _seed(client, rounds=2)
    pick_id = _an_asserted_pick_id()
    with db.engine.begin() as conn:
        conn.execute(draft_picks_table.update()
                     .where(draft_picks_table.c.pick_id == pick_id)
                     .values(pool_value=None))
    priced = [i for its in server._power_picks_by_owner(LEAGUE, "1qb_ppr").values()
              for i in its if i["pick_id"] == pick_id]
    assert priced and priced[0]["value"] > 0


# ---------------------------------------------------------------------------
# The one guard — all THREE clauses preserved
# ---------------------------------------------------------------------------

class _Lg:
    def __init__(self, platform):
        self.platform = platform
        self.league_id = LEAGUE


def _old_literal(league_id, league):
    """The expression the two duplicated literals evaluated before M-C."""
    return (ff.FLAGS.trade_picks_in_pool
            and getattr(league, "platform", None) != "espn"
            and league_id != "league_demo")


@pytest.mark.parametrize("platform", ["sleeper", "mfl", "espn", None])
@pytest.mark.parametrize("league_id", [LEAGUE, "league_demo"])
@pytest.mark.parametrize("picks_in_pool", [True, False])
def test_mc_11_guard_is_the_old_literal_exactly_when_the_flag_is_off(
        mem_db, flags, platform, league_id, picks_in_pool):
    """Flag off ⇒ the helper returns EXACTLY what the literals returned, for
    every combination of the three clauses. This is what makes D10's golden
    diff green, and it is why the helper could not be "just the platform
    test" — the demo and `trade.picks_in_pool` conjuncts do real work."""
    flags(**{"picks.assign_tradeable": False,
             "trade.picks_in_pool": picks_in_pool})
    assert server._owned_picks_available(league_id, _Lg(platform)) == \
        bool(_old_literal(league_id, _Lg(platform)))


def test_mc_11b_all_three_clauses_still_gate_with_the_flag_on(client, flags):
    """…and with the flag ON, the other two conjuncts are untouched: only the
    ESPN clause changed, from a platform test to a data test."""
    _seed(client, rounds=2)
    flags(**{"picks.assign_tradeable": True})
    assert server._owned_picks_available(LEAGUE, _Lg("espn")) is True
    # clause 1 — the master pick switch still wins over everything
    flags(**{"picks.assign_tradeable": True, "trade.picks_in_pool": False})
    assert server._owned_picks_available(LEAGUE, _Lg("espn")) is False
    assert server._owned_picks_available(LEAGUE, _Lg("sleeper")) is False
    # clause 2 — the demo league never prices picks, on any flag
    flags(**{"picks.assign_tradeable": True})
    assert server._owned_picks_available("league_demo", _Lg("sleeper")) is False
    assert server._owned_picks_available("league_demo", _Lg("espn")) is False


def test_mc_11c_espn_is_a_data_test_not_a_platform_test(client, flags):
    """An ESPN league with NO assignments does not qualify; the same league
    qualifies the moment a grid exists; and the switch takes it away again
    without touching a single stored row."""
    flags(**{"picks.assign_tradeable": True})
    assert server._owned_picks_available(LEAGUE, _Lg("espn")) is False

    _seed(client, rounds=2)
    assert server._owned_picks_available(LEAGUE, _Lg("espn")) is True

    flags(**{"picks.assign_tradeable": False})
    assert server._owned_picks_available(LEAGUE, _Lg("espn")) is False
    assert len(db.load_draft_picks(league_id=LEAGUE,
                                   source=db.PICK_SOURCE_USER)) == \
        2 * len(MEMBERS) * 4          # the kill switch destroys nothing


def test_mc_11d_the_duplicated_platform_literals_are_gone(client, flags):
    """The two three-clause literals were duplicated, and the design pass
    found they drift the moment one is relaxed. Exactly one function may hold
    the ESPN platform comparison for engine gating."""
    import ast
    from pathlib import Path
    src = Path(server.__file__).read_text()
    tree = ast.parse(src)
    holders = []
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef):
            continue
        for node in ast.walk(fn):
            if (isinstance(node, ast.Compare)
                    and any(isinstance(c, ast.Constant) and c.value == "espn"
                            for c in node.comparators)
                    and any(isinstance(o, ast.NotEq) for o in node.ops)):
                holders.append(fn.name)
    # `_owned_picks_available` is the engine guard; `get_league_picks` holds
    # the DISPLAY label's platform half (and its demo early return).
    assert set(holders) == {"_owned_picks_available", "get_league_picks"}, (
        f"a platform literal reappeared outside the one helper: {sorted(set(holders))}")


# ---------------------------------------------------------------------------
# The flag itself — 4-touch, lands OFF
# ---------------------------------------------------------------------------

def test_mc_12_flag_is_registered_lands_off_and_is_mirrored():
    from pathlib import Path
    repo = Path(server.__file__).resolve().parents[1]
    assert "picks.assign_tradeable" in ff.FLAG_KEYS
    assert ff.DEFAULT_FLAGS["picks.assign_tradeable"] is False
    features = json.loads((repo / "config/features.json").read_text())
    release = json.loads(
        (repo / "backend/tests/fixtures/flags/release.json").read_text())
    # Operator flipped this ON 2026-08-06 ("Do 1 now. I don't like that
    # decision" — assigned picks were visible but not pricing). The property
    # that must hold is the 4-touch MIRROR, not a particular value: if the two
    # files ever disagree, `is_enabled` and the release fixture diverge.
    assert features["picks.assign_tradeable"] == release["picks.assign_tradeable"]
    # the two flags are SEPARATE on purpose: pick math dies without taking the
    # rows a league typed in with it
    assert features["picks.assign"] is True
