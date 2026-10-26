"""I-2 (4/4): team overhaul blocks on a failed roster read and refuses readably.

PRD: docs/plans/trade-time-to-suggestion/prd.md §5.3 I-2 (platforms-pm R3, R4,
R8) and AC-6a. Stacked on I-2 PRs 1–3 (#411–#413).

  * R3 at prepare-send: on a send platform, a failed live roster read used to
    fall back to the session roster (`roster_source: session`) and prepare
    anyway. It now refuses with 503 `rosters_unavailable` (`kind: "network"`,
    `detail` == `message` == the shared R3 copy). No token is minted and the
    fallback snapshot is not stored. Copy-handoff platforms are unaffected.
  * R4 copy: the receipt's `asset_not_owned` / `counterparty_asset_not_owned`
    blockers use the shared I-2 copy (`backend/ownership_copy.py`), one per
    offer and side, named from the offer's card. No serial comma, a count when
    a name is missing, never a raw id ("You no longer own 4046." is gone).
  * /send's re-check 409 on an ownership blocker carries `detail` ==
    `message`, which OverhaulSummaryScreen's errorDetail(e) shows.
  * A per-offer core 422 inside a 200 batch reaches `attempts[].error.message`
    on both the /send response and GET /api/overhauls/{id} (OverhaulPlanScreen
    reads the latter).
"""
import pytest

from backend import overhaul_api
from backend import overhaul_service as svc
from backend import overhaul_store as store
from backend.tests import test_i2_sleeper_ownership as sl_t
from backend.tests import test_overhaul_api as ovh_t
from backend.tests import test_overhaul_service as svc_t

TAIL = ", so nothing was sent. Find a new trade."


@pytest.fixture(autouse=True)
def _no_refresh_kick(monkeypatch):
    """The real Sleeper core kicks a background roster refresh on a refusal
    (#413). Stub it, so no refresh thread reaches Sleeper from a test."""
    from backend import server
    monkeypatch.setattr(server._roster_refresh, "maybe_refresh_async", lambda *a, **kw: False)


@pytest.fixture()
def world():
    return ovh_t.World()


@pytest.fixture()
def api(world):
    yield from ovh_t.api.__wrapped__(world)


def _assembled(c):
    v, gen = ovh_t._setup(c)
    ovh_t._like_all(c, v, gen["offers"])
    return v["overhaul_id"], ovh_t._assemble(c, v)["roadmaps"][0]


def _prepare(c, oid, rm):
    return c.post(f"/api/overhauls/{oid}/roadmaps/{rm['roadmap_id']}/prepare-send",
                  json={"version": rm["version"]}, headers=ovh_t._h())


# ---------------------------------------------------------------------------
# R3: prepare-send blocks on a failed live roster read
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("platform,label", [("sleeper", "Sleeper"), ("mfl", "MFL"), ("espn", "ESPN")])
def test_prepare_blocks_on_a_failed_roster_read(api, world, platform, label):
    world.platform = platform
    oid, rm = _assembled(api)
    before = store.get_overhaul(oid)["snapshot"]
    assert before["roster_source"] == "live"
    world.raw_rosters = lambda: None              # the live read now fails (every reader)
    world.platform_read_ok = False
    overhaul_api._PREPARES.clear()
    r = _prepare(api, oid, rm)
    assert r.status_code == 503, r.get_json()
    msg = (f"Couldn’t confirm rosters with {label} right now, so nothing was sent. "
           "Try again in a moment.")
    assert r.get_json() == {"error": "rosters_unavailable", "kind": "network",
                            "detail": msg, "message": msg}
    assert overhaul_api._PREPARES == {}           # no token: nothing can be sent
    assert store.get_overhaul(oid)["snapshot"] == before   # the session fallback is not stored


def test_prepare_proceeds_once_the_read_is_back(api, world):
    oid, rm = _assembled(api)
    real = world.raw_rosters
    world.raw_rosters = lambda: None
    assert _prepare(api, oid, rm).status_code == 503
    world.raw_rosters = real
    r = _prepare(api, oid, rm)
    assert r.status_code == 200, r.get_json()
    assert store.get_overhaul(oid)["snapshot"]["roster_source"] == "live"


def test_copy_handoff_platform_still_prepares_without_a_live_read(api, world):
    world.platform = "fleaflicker"                # copy handoff: nothing is sent
    oid, rm = _assembled(api)
    r = _prepare(api, oid, rm)
    assert r.status_code == 200 and r.get_json()["handoff"]["mode"] == "copy"


# ---------------------------------------------------------------------------
# R4: readable ownership blockers (service, then through the API)
# ---------------------------------------------------------------------------

def _offer(oid, give, recv, cp, names, username=None):
    o = svc_t._offer(oid, give, recv, cp)
    o["card"] = {"give": [{"id": p, "name": names.get(p, "Unknown")} for p in give],
                 "receive": [{"id": p, "name": names.get(p, "Unknown")} for p in recv]}
    o["counterparty_username"] = username
    return o


def _receipt(offers, *, mine, rosters, pool=None):
    by_id = {o["offer_id"]: o for o in offers}
    packages = [{"package_id": f"p{o['offer_id']}", "give_ids": o["give_ids"],
                 "tiers": [{"tier": 1, "offer_ids": [o["offer_id"]]}]} for o in offers]
    return svc.validate_prepare(
        selected=list(by_id), packages=packages, offers_by_id=by_id, my_roster_ids=mine,
        my_pick_ids=[], pool=pool if pool is not None else [a for o in offers for a in o["give_ids"]],
        rosters=rosters, reserved_asset_ids=[], capacity=None, recovery={}, package_states={},
        checked_at="t", is_pick=svc_t._is_pick)


def _no_raw_ids(message, ids):
    assert not any(i in message for i in ids), message


def test_give_blocker_names_every_moved_player_without_a_serial_comma():
    names = {"4046": "Josh Allen", "9509": "Bijan Robinson", "6794": "CeeDee Lamb"}
    o = _offer("o_a", ["4046", "9509", "6794"], ["X1"], "o1", names)
    receipt = _receipt([o], mine=[], rosters={"o1": ["X1"]})
    blockers = [b for b in receipt["blockers"] if b["code"] == "asset_not_owned"]
    assert blockers == [{"code": "asset_not_owned", "package_id": "po_a", "offer_id": "o_a",
                         "assets": ["4046", "9509", "6794"], "message":
                         "Josh Allen, Bijan Robinson and CeeDee Lamb are no longer on your roster" + TAIL}]
    _no_raw_ids(blockers[0]["message"], ["4046", "9509", "6794"])


def test_a_missing_name_switches_the_blocker_to_a_count():
    o = _offer("o_a", ["4046", "9999"], ["X1"], "o1", {"4046": "Josh Allen"})   # 9999 -> "Unknown"
    receipt = _receipt([o], mine=[], rosters={"o1": ["X1"]})
    (b,) = [b for b in receipt["blockers"] if b["code"] == "asset_not_owned"]
    assert b["message"] == "2 players in this trade are no longer on your roster" + TAIL
    _no_raw_ids(b["message"], ["4046", "9999"])


def test_receive_blocker_names_the_team_or_the_other_manager():
    names = {"A": "Al", "8136": "Rachaad White"}
    named = _offer("o_a", ["A"], ["8136"], "o1", names, username="Dolphins Den")
    unnamed = _offer("o_b", ["A2"], ["8137"], "o2", {"A2": "Al Two"})
    receipt = _receipt([named, unnamed], mine=["A", "A2"], rosters={"o1": [], "o2": []})
    msgs = {b["offer_id"]: b["message"] for b in receipt["blockers"]
            if b["code"] == "counterparty_asset_not_owned"}
    assert msgs == {
        "o_a": "Rachaad White is no longer on Dolphins Den’s roster" + TAIL,
        "o_b": "A player in this trade is no longer on the other manager’s roster" + TAIL}
    _no_raw_ids(msgs["o_b"], ["8137", "o2"])


def test_ownership_blocker_keeps_its_place_before_the_same_assets_pool_blocker():
    o = _offer("o_a", ["4046"], ["X1"], "o1", {"4046": "Josh Allen"})
    receipt = _receipt([o], mine=[], rosters={"o1": ["X1"]}, pool=[])
    assert [b["code"] for b in receipt["blockers"]] == ["asset_not_owned", "pool_violation"]


def test_prepare_receipt_shows_the_readable_blocker(api, world):
    oid, rm = _assembled(api)
    world.rosters[ovh_t.USER].remove("A")         # moved before prepare
    r = _prepare(api, oid, rm)
    assert r.status_code == 200, r.get_json()
    receipt = r.get_json()["receipt"]
    assert receipt["ok"] is False
    msgs = {b["message"] for b in receipt["blockers"] if b["code"] == "asset_not_owned"}
    assert msgs == {"PA is no longer on your roster" + TAIL}   # the harness card names "A" as "PA"


# ---------------------------------------------------------------------------
# /send re-check 409 carries a readable detail
# ---------------------------------------------------------------------------

def test_send_recheck_409_has_a_readable_detail(api, world):
    """A receive-side move between prepare and send: refresh stores the new
    snapshot (it stales offers only for GIVE-side moves), so /send's re-check
    refuses on ownership."""
    oid, rm, prep = ovh_t._tie_then_prepare(api, world)
    world.rosters["o3"].remove("X3")              # moved after prepare...
    overhaul_api._REFRESH_AT.clear()
    assert api.post(f"/api/overhauls/{oid}/refresh", json={}, headers=ovh_t._h()).status_code == 200
    r = api.post(f"/api/overhauls/{oid}/send", headers=ovh_t._h(), json={   # ...so /send re-checks
        "prepare_token": prep["prepare_token"], "summary_hash": prep["summary_hash"],
        "version": rm["version"], "idempotency_key": "i2-409"})
    assert r.status_code == 409, r.get_json()
    body = r.get_json()
    assert body["error"] == "counterparty_asset_not_owned"
    # The harness card names X3 "PX3" and its manager's username is "O3".
    assert body["detail"] == body["message"] == "PX3 is no longer on O3’s roster" + TAIL
    assert body["receipt"]["ok"] is False
    assert world.propose_calls == []              # nothing reached a core


def test_send_409_for_a_refresh_staled_offer_has_the_ownership_detail(api, world):
    """A GIVE-side move after prepare: /refresh stales the offer, so /send's
    first blocker is `offer_stale`. The 409 still carries the readable
    ownership sentence for that offer (Product: a readable reason on every
    path), named from the card, never a raw id."""
    oid, rm, prep = ovh_t._tie_then_prepare(api, world)
    world.rosters[ovh_t.USER].remove("A")         # moved after prepare...
    overhaul_api._REFRESH_AT.clear()
    assert api.post(f"/api/overhauls/{oid}/refresh", json={}, headers=ovh_t._h()).status_code == 200
    stale = {o["offer_id"] for o in store.list_offers(oid) if o["availability"] == "stale"}
    assert stale                                  # refresh staled the A offers
    r = api.post(f"/api/overhauls/{oid}/send", headers=ovh_t._h(), json={   # ...so /send re-checks
        "prepare_token": prep["prepare_token"], "summary_hash": prep["summary_hash"],
        "version": rm["version"], "idempotency_key": "i2-stale"})
    assert r.status_code == 409, r.get_json()
    body = r.get_json()
    assert body["error"] == "offer_stale"
    # The harness card names A "PA".
    assert body["detail"] == body["message"] == "PA is no longer on your roster" + TAIL
    assert world.propose_calls == []


def test_send_409_for_a_stale_offer_whose_assets_came_back_stays_as_before(api, world):
    """Stale but owned again (no ownership blocker): not an ownership reason
    any more, so the 409 keeps today's shape with no `detail`."""
    oid, rm, prep = ovh_t._tie_then_prepare(api, world)
    world.rosters[ovh_t.USER].remove("A")
    overhaul_api._REFRESH_AT.clear()
    api.post(f"/api/overhauls/{oid}/refresh", json={}, headers=ovh_t._h())
    world.rosters[ovh_t.USER].append("A")         # back before the send
    overhaul_api._REFRESH_AT.clear()
    api.post(f"/api/overhauls/{oid}/refresh", json={}, headers=ovh_t._h())
    r = api.post(f"/api/overhauls/{oid}/send", headers=ovh_t._h(), json={
        "prepare_token": prep["prepare_token"], "summary_hash": prep["summary_hash"],
        "version": rm["version"], "idempotency_key": "i2-stale-back"})
    assert r.status_code == 409 and r.get_json()["error"] == "offer_stale"
    assert "detail" not in r.get_json() and "message" not in r.get_json()


# ---------------------------------------------------------------------------
# Per-offer core 422 → attempts[].error.message, on /send AND the GET view
# ---------------------------------------------------------------------------

@pytest.fixture()
def real_core(monkeypatch):
    yield from sl_t.overhaul.__wrapped__(monkeypatch)


def test_per_offer_core_refusal_reaches_the_plan_view(real_core):
    c, world, live, fake = real_core
    oid, rm, prep = ovh_t._tie_then_prepare(c, world)
    rosters = world.raw_rosters()
    for r in rosters:
        if r["owner_id"] == ovh_t.USER:
            r["players"].remove("A")
    live["rosters"] = rosters
    sent = c.post(f"/api/overhauls/{oid}/send", headers=ovh_t._h(), json={
        "prepare_token": prep["prepare_token"], "summary_hash": prep["summary_hash"],
        "version": rm["version"], "idempotency_key": "i2-plan"})
    assert sent.status_code == 200, sent.get_json()
    expected = {"code": "asset_not_owned",
                "message": "A player in this trade is no longer on your roster" + TAIL}
    failed = [a for a in sent.get_json()["attempts"] if a["state"] == "send_failed"]
    assert [a["error"] for a in failed] == [expected, expected]
    # OverhaulPlanScreen renders `a.error.message` for send_failed attempts
    # from GET /api/overhauls/{id}.
    view = c.get(f"/api/overhauls/{oid}", headers=ovh_t._h()).get_json()
    shown = [a["error"] for a in view["attempts"] if a["state"] == "send_failed"]
    assert shown == [expected, expected]
