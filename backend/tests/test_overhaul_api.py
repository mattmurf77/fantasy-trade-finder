"""Team overhaul — HTTP surface (backend/overhaul_api.py) end to end.

Contract: docs/plans/team-overhaul/BUILD-CONTRACT.md §7/§8. A fresh Flask app
gets `overhaul_api.install` with FAKE generator / roster / Sleeper-propose
seams; the session, read/write gates and identity helpers are the REAL
server ones (pattern: test_avoid_positions.py:117). Covers: create idempotent
on client_key; flag off -> 404 on gated routes, 200 on GET; foreign account
-> 404; settings revision conflict; generate stores offers, enforces the pool
(E01) and never returns evidence; decisions idempotent and Elo-free;
assemble -> roadmaps or shortfall; priorities version conflict; prepare-send
counts (AC12: 4 packages + one tie = 5 offers, max_accepted 4, race named);
send idempotent replay / hash conflict / reserved asset / partial success /
outcome_unknown; refresh accepts from ownership and invalidates the tie;
status assertion only from live states. Review fixes (2026-09-07): refresh
never terminalizes on the stale pick table and accepts a pick return only
from a live traded_picks read; stuck `queued`/`sending` attempts are swept;
a settings change clears exhausted subsets and regeneration re-freshens
stale undecided rows; send gates on `can_propose`; the D6 legality check
excludes tie partners. In-memory SQLite.
"""
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import update

import pytest
from flask import Flask
from sqlalchemy import create_engine

from backend import database as db
from backend import feature_flags as ff
from backend import overhaul_api
from backend import overhaul_store as store
from backend import server

USER, OTHER, LEAGUE = "u1", "u2", "L1"
TOKEN, TOKEN_OTHER = "ovh-sess", "ovh-sess-other"
MY_PLAYERS = ["A", "B", "C", "D", "E", "F"]
OPPONENTS = {"o1": ["X1"], "o2": ["X2"], "o3": ["X3"], "o4": ["X4"], "o5": ["X5"]}


def _player(pid, pos="WR", age=25):
    return SimpleNamespace(id=pid, name=f"P{pid}", position=pos, team="T", age=age, years_experience=3)


class _Ranking:
    def __init__(self, ids):
        self._seed = {pid: 1500.0 + i for i, pid in enumerate(ids)}

    def get_rankings(self, position=None):
        return SimpleNamespace(rankings=[SimpleNamespace(player=_player(p), elo=e) for p, e in self._seed.items()])


class _League:
    league_id = LEAGUE
    name = "T"
    platform = "sleeper"

    def __init__(self):
        self.members = [SimpleNamespace(user_id=u, username=u.upper(), roster=list(r)) for u, r in OPPONENTS.items()]


class World:
    """Mutable fixture world the fakes read from."""

    def __init__(self):
        self.rosters = {USER: list(MY_PLAYERS), **{u: list(r) for u, r in OPPONENTS.items()}}
        # subset -> [(give, receive, counterparty)] the fake generator emits
        self.script = {("A",): [(["A"], ["X1"], "o1"), (["A"], ["X2"], "o2")],
                       ("B",): [(["B"], ["X3"], "o3"), (["B", "F"], ["X3"], "o3")],   # 2nd escapes the pool
                       ("C",): [(["C"], ["X4"], "o4")], ("D",): [(["D"], ["X5"], "o5")]}
        self.propose = []      # queue of ("ok", tx) | ("fail", code, status) | ("raise",)
        self.propose_calls = []
        self.events = []
        self.generate_calls = []
        self.picks = []        # draft_picks rows (the DB table, synced only at session init)
        self.traded = None     # Sleeper traded_picks payload; None = the live read is unavailable
        self.roster_ctx = None # trade_roster context for the legality check; None = unavailable

    def raw_rosters(self):
        return [{"roster_id": i + 1, "owner_id": uid, "players": list(r)} for i, (uid, r) in enumerate(self.rosters.items())]


def _card(give, recv, cp):
    return SimpleNamespace(trade_id="t", league_id=LEAGUE, target_user_id=cp, target_username=cp.upper(),
                           give_player_ids=list(give), receive_player_ids=list(recv), mismatch_score=1.0,
                           fairness_score=0.9, composite_score=1.0, basis="consensus", decision=None,
                           expires_at="x", give_value=100.0, receive_value=95.0,
                           owner_evaluation=SimpleNamespace(as_dict=lambda: {"PRIVATE_BOARD": 1}))


@pytest.fixture()
def world():
    return World()


@pytest.fixture()
def api(world):
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    db.metadata.create_all(eng)
    app = Flask("overhaul_test")
    app.config["TESTING"] = True
    app.register_error_handler(server._SessionNotInitialized, server.handle_session_not_initialized)

    def generate(**ctx):
        world.generate_calls.append(ctx)
        key = tuple(sorted(ctx.get("pinned_give_players") or []))
        if ctx.get("opponent_user_id"):
            return [], None
        return [_card(*spec) for spec in world.script.get(key, [])], None

    def sleeper_propose(sess, **kw):
        world.propose_calls.append(kw)
        step = world.propose.pop(0) if world.propose else ("ok", "tx-default")
        if step[0] == "ok":
            return {"status": "proposed", "transaction_id": step[1]}, 200
        if step[0] == "raise":
            raise TimeoutError("socket timeout")
        return {"error": step[1], "detail": "nope"}, step[2]

    def roster_id_for_owner(rosters, owner):
        return next((r["roster_id"] for r in rosters or [] if r["owner_id"] == owner), None)

    def fetch_json(url):
        if world.traded is None:
            raise OSError("sleeper unavailable")
        return world.traded

    overhaul_api.install(
        app, require_session=server._require_initialized_session, read_denial=server._verified_read_denial,
        write_denial=server._verified_write_denial, active_format=server._active_format,
        league_user_id=server._league_user_id,
        owner_generation_context=lambda **kw: {"players": kw["players"], "user_roster": kw["user_roster"], "outlook": None},
        generate=generate, roster_context=lambda **kw: world.roster_ctx, sleeper_propose=sleeper_propose,
        fetch_rosters=lambda league_id: world.raw_rosters(), roster_id_for_owner=roster_id_for_owner,
        load_picks=lambda league_id, source=None: list(world.picks), pick_source_platform="platform",
        draft_context=lambda league_id: {"season": 2026},
        card_to_dict=lambda card, players: {"trade_id": card.trade_id, "target_user_id": card.target_user_id,
                                            "give": [{"id": p, "name": f"P{p}"} for p in card.give_player_ids],
                                            "receive": [{"id": p, "name": f"P{p}"} for p in card.receive_player_ids],
                                            "fairness_score": card.fairness_score, "composite_score": card.composite_score},
        is_pick_asset=lambda league_id, a: str(a).startswith("L1_") or str(a).startswith("generic_pick_"),
        owned_picks_available=lambda league_id, league: False, inject_owned_picks=None,
        pick_label=lambda row, order: "pick", slot_order=lambda league_id: None,
        priced_pick_value=lambda row, order, fmt: 0.0, elo_to_value=lambda e: e - 1000.0,
        sleeper_credential=lambda uid: {"token_encrypted": "tok", "sleeper_user_id": uid},
        sleeper_write=SimpleNamespace(decrypt_token=lambda t: t, is_expired=lambda t: False),
        record_event=lambda uid, name, **kw: world.events.append((name, kw.get("props"))),
        fetch_json=fetch_json)

    players = [_player(p) for p in MY_PLAYERS] + [_player(x) for r in OPPONENTS.values() for x in r]
    ranking = _Ranking([p.id for p in players])

    def sess(user):
        return {"verified": True, "user_id": user, "league": _League(), "players": players,
                "trade_svc": object(), "service": ranking, "active_format": "1qb_ppr",
                "last_active": 0.0, "user_roster": list(MY_PLAYERS)}

    saved = ff._flags_cache
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "overhaul.enabled": True, "trade.send_in_sleeper": True}
    overhaul_api._PREPARES.clear()
    overhaul_api._REFRESH_AT.clear()
    with patch.object(db, "engine", eng):
        with server._sessions_lock:
            server._sessions[TOKEN] = sess(USER)
            server._sessions[TOKEN_OTHER] = sess(OTHER)
        try:
            yield app.test_client()
        finally:
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)
                server._sessions.pop(TOKEN_OTHER, None)
            ff._flags_cache = saved
            overhaul_api._PREPARES.clear()
            overhaul_api._REFRESH_AT.clear()


def _h(token=TOKEN):
    return {"X-Session-Token": token}


def _create(c, key="ck1"):
    r = c.post("/api/overhauls", json={"league_id": LEAGUE, "client_key": key}, headers=_h())
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def _settings(c, oid, revision, **settings):
    r = c.put(f"/api/overhauls/{oid}/settings", json={"revision": revision, "settings": settings}, headers=_h())
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def _setup(c, pool=("A", "B", "C", "D", "E")):
    """Create + configure + generate; returns (view, offers)."""
    v = _create(c)
    v = _settings(c, v["overhaul_id"], v["revision"], outlook="push_all_in", eligible_asset_ids=list(pool))
    r = c.post(f"/api/overhauls/{v['overhaul_id']}/generate", json={"revision": v["revision"]}, headers=_h())
    assert r.status_code == 200, r.get_json()
    return v, r.get_json()


def _like_all(c, v, offers):
    body = {"revision": v["revision"], "decisions": [{"offer_id": o["offer_id"], "decision": "like", "client_key": "d" + o["offer_id"]} for o in offers]}
    r = c.post(f"/api/overhauls/{v['overhaul_id']}/decisions", json=body, headers=_h())
    assert r.status_code == 200, r.get_json()
    return r.get_json()["progress"]


def _assemble(c, v):
    r = c.post(f"/api/overhauls/{v['overhaul_id']}/assemble", json={"revision": v["revision"]}, headers=_h())
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def _tie_then_prepare(c, world):
    """Shared AC12 fixture: 4 packages, package A tied (two offers in tier 1)."""
    v, gen = _setup(c)
    _like_all(c, v, gen["offers"])
    rm = _assemble(c, v)["roadmaps"][0]
    oid = v["overhaul_id"]
    r = c.put(f"/api/overhauls/{oid}/roadmaps/{rm['roadmap_id']}/select", json={"version": rm["version"]}, headers=_h())
    assert r.status_code == 200 and r.get_json()["selected_roadmap_id"] == rm["roadmap_id"]
    pkg_a = next(p for p in rm["packages"] if p["give_ids"] == ["A"])
    ids = [i for t in pkg_a["tiers"] for i in t["offer_ids"]]
    assert len(ids) == 2
    r = c.put(f"/api/overhauls/{oid}/roadmaps/{rm['roadmap_id']}/priorities",
              json={"version": rm["version"], "package_id": pkg_a["package_id"], "tiers": [{"tier": 1, "offer_ids": ids}]},
              headers=_h())
    assert r.status_code == 200, r.get_json()
    rm2 = r.get_json()
    assert rm2["version"] == rm["version"] + 1
    selected = [i for p in rm2["packages"] for i in p["tiers"][0]["offer_ids"]]
    r = c.post(f"/api/overhauls/{oid}/roadmaps/{rm['roadmap_id']}/prepare-send",
               json={"version": rm2["version"], "offer_ids": selected}, headers=_h())
    assert r.status_code == 200, r.get_json()
    return oid, rm2, r.get_json()


# ── create / read / gates ───────────────────────────────────────────────────

def test_create_idempotent_on_client_key_and_archives_idle_active(api):
    v1 = _create(api)
    r = api.post("/api/overhauls", json={"league_id": LEAGUE, "client_key": "ck1"}, headers=_h())
    assert r.status_code == 200 and r.get_json()["overhaul_id"] == v1["overhaul_id"]
    assert v1["status"] == "setup" and v1["revision"] == 1 and v1["selected_roadmap_id"] is None
    assert v1["capabilities"]["auth_state"] == "linked" and v1["capabilities"]["can_propose"] is True
    assert {a["id"] for a in v1["eligible_assets"]} == set(MY_PLAYERS)
    assert v1["snapshot"] == {"captured_at": v1["snapshot"]["captured_at"], "season": 2026, "picks_supported": True}
    # A new client_key archives the idle active overhaul.
    v2 = _create(api, key="ck2")
    assert v2["overhaul_id"] != v1["overhaul_id"]
    active = api.get(f"/api/overhauls?league_id={LEAGUE}", headers=_h()).get_json()["active"]
    assert active["overhaul_id"] == v2["overhaul_id"]
    assert api.get(f"/api/overhauls/{v1['overhaul_id']}", headers=_h()).get_json()["status"] == "archived"


def test_flag_off_gates_only_the_listed_routes(api):
    v = _create(api)
    oid = v["overhaul_id"]
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "overhaul.enabled": False}
    assert api.post("/api/overhauls", json={"league_id": LEAGUE, "client_key": "x"}, headers=_h()).status_code == 404
    assert api.post(f"/api/overhauls/{oid}/generate", json={"revision": 1}, headers=_h()).status_code == 404
    assert api.post(f"/api/overhauls/{oid}/assemble", json={"revision": 1}, headers=_h()).status_code == 404
    assert api.post(f"/api/overhauls/{oid}/send", json={}, headers=_h()).status_code == 404
    assert api.get(f"/api/overhauls/{oid}", headers=_h()).status_code == 200
    assert api.get(f"/api/overhauls?league_id={LEAGUE}", headers=_h()).status_code == 200
    assert api.put(f"/api/overhauls/{oid}/settings", json={"revision": 1, "settings": {}}, headers=_h()).status_code == 200
    assert api.post(f"/api/overhauls/{oid}/refresh", json={}, headers=_h()).status_code == 200


def test_foreign_account_is_404_never_403(api):
    v = _create(api)
    oid = v["overhaul_id"]
    for method, path, body in (("get", f"/api/overhauls/{oid}", None),
                               ("put", f"/api/overhauls/{oid}/settings", {"revision": 1, "settings": {}}),
                               ("post", f"/api/overhauls/{oid}/generate", {"revision": 1}),
                               ("post", f"/api/overhauls/{oid}/refresh", {})):
        r = getattr(api, method)(path, json=body, headers=_h(TOKEN_OTHER))
        assert r.status_code == 404 and r.get_json()["error"] == "not_found", (path, r.get_json())
    assert api.get(f"/api/overhauls?league_id={LEAGUE}", headers=_h(TOKEN_OTHER)).get_json()["active"] is None


def test_settings_revision_conflict_and_validation(api):
    v = _create(api)
    oid = v["overhaul_id"]
    r = api.put(f"/api/overhauls/{oid}/settings", json={"revision": 99, "settings": {"outlook": "blow_it_up"}}, headers=_h())
    assert r.status_code == 409 and r.get_json()["error"] == "stale_revision"
    r = api.put(f"/api/overhauls/{oid}/settings", json={"revision": 1, "settings": {"eligible_asset_ids": ["ZZ"]}}, headers=_h())
    assert r.status_code == 400 and r.get_json()["error"] == "asset_not_owned"
    r = api.put(f"/api/overhauls/{oid}/settings", json={"revision": 1, "settings": {"eligible_asset_ids": ["generic_pick_1_early"]}}, headers=_h())
    assert r.status_code == 400 and r.get_json()["error"] == "generic_pick_not_allowed"
    v = _settings(api, oid, 1, outlook="blow_it_up", eligible_asset_ids=["A", "B"], rebuild_return="picks")
    assert v["revision"] == 2 and v["settings"]["outlook"] == "blow_it_up"
    assert v["recovery"]["applicable"] is True and v["recovery"]["state"] == "unknown" and v["recovery"]["season"] == 2027


# ── generate / decisions ────────────────────────────────────────────────────

def test_generate_stores_offers_enforces_pool_and_hides_evidence(api, world):
    v, gen = _setup(api)
    assert gen["generation"]["state"] == "completed" and gen["generation"]["new_offers"] == 5
    assert gen["generation"]["pool_rejections"] == 1              # the [B, F] sweetener card
    assert all(set(o["give_ids"]) <= {"A", "B", "C", "D", "E"} for o in gen["offers"])
    raw = json.dumps(gen)
    assert "PRIVATE_BOARD" not in raw and "evidence" not in raw
    assert all(o["card"]["offer_id"] == o["offer_id"] and o["decision"] == "undecided" for o in gen["offers"])
    # Outlook rides the ctx dict only (mapped to the engine's utility name).
    assert all(call["outlook"] == "championship" for call in world.generate_calls)
    assert all(call["exact_give"] is True and call["max_cards"] == 3 for call in world.generate_calls)
    # Rerun: same cards dedupe on package_hash, nothing new.
    r = api.post(f"/api/overhauls/{v['overhaul_id']}/generate", json={"revision": v["revision"]}, headers=_h())
    assert r.get_json()["generation"]["new_offers"] == 0 and r.get_json()["generation"]["total_offers"] == 5
    assert world.events[0][0] == "overhaul_generation_completed"
    assert set(world.events[0][1]) == {"overhaul_id", "candidate_count", "compatible_roadmap_count", "shortfall_reason"}
    view = api.get(f"/api/overhauls/{v['overhaul_id']}", headers=_h()).get_json()
    assert view["status"] == "reviewing" and view["progress"] == {"decided": 0, "total": 5, "liked": 0}


def test_generate_requires_outlook_and_rejects_stale_revision(api):
    v = _create(api)
    r = api.post(f"/api/overhauls/{v['overhaul_id']}/generate", json={"revision": 1}, headers=_h())
    assert r.status_code == 400 and r.get_json()["detail"] == "outlook_required"
    v = _settings(api, v["overhaul_id"], 1, outlook="push_all_in", eligible_asset_ids=["A"])
    r = api.post(f"/api/overhauls/{v['overhaul_id']}/generate", json={"revision": 1}, headers=_h())
    assert r.status_code == 409 and r.get_json()["error"] == "stale_revision"


def test_decisions_idempotent_and_pool_change_stales_undecided(api):
    v, gen = _setup(api)
    oid = v["overhaul_id"]
    first = gen["offers"][0]["offer_id"]
    body = {"revision": v["revision"], "decisions": [{"offer_id": first, "decision": "like", "client_key": "c1"}]}
    assert api.post(f"/api/overhauls/{oid}/decisions", json=body, headers=_h()).get_json()["progress"]["liked"] == 1
    assert api.post(f"/api/overhauls/{oid}/decisions", json=body, headers=_h()).get_json()["progress"]["liked"] == 1
    liked = api.get(f"/api/overhauls/{oid}/offers?decision=like", headers=_h()).get_json()
    assert [o["offer_id"] for o in liked["offers"]] == [first] and liked["progress"]["decided"] == 1
    undecided = api.get(f"/api/overhauls/{oid}/offers", headers=_h()).get_json()["offers"]
    assert len(undecided) == 4
    # Changing the pool stales every undecided offer; the like survives.
    v = _settings(api, oid, v["revision"], eligible_asset_ids=["A", "B"])
    assert v["progress"] == {"decided": 1, "total": 1, "liked": 1}
    assert api.get(f"/api/overhauls/{oid}/offers", headers=_h()).get_json()["offers"] == []
    stale = [o for o in api.get(f"/api/overhauls/{oid}/offers?decision=all", headers=_h()).get_json()["offers"]
             if o["availability"] == "stale"]
    assert len(stale) == 4


# ── assemble / select / priorities ──────────────────────────────────────────

def test_assemble_roadmaps_or_shortfall(api):
    v, gen = _setup(api)
    oid = v["overhaul_id"]
    r = api.post(f"/api/overhauls/{oid}/assemble", json={"revision": v["revision"]}, headers=_h()).get_json()
    assert r["roadmaps"] == [] and r["shortfall"]["reason"] == "insufficient_likes"
    _like_all(api, v, gen["offers"])
    r = _assemble(api, v)
    assert r["shortfall"] is None and 1 <= len(r["roadmaps"]) <= 5
    rm = r["roadmaps"][0]
    assert rm["version"] == 1 and rm["rank"] == 1 and len(rm["packages"]) == 4
    assert set(rm["summary"]) == {"outgoing_ids", "incoming_ids", "counterparties", "unused_eligible_ids", "score", "diversity_key"}
    assert rm["summary"]["unused_eligible_ids"] == ["E"]
    assert set(rm["compat"]) == {"ok", "checked_at", "blockers", "warnings", "unknowns", "outgoing_ids", "incoming_ids"}
    assert all(p["status"] == "open" and p["reason"] == "outlook_move" and p["advisory_rank"] == 0 for p in rm["packages"])
    assert set(rm["offers"]) == {i for p in rm["packages"] for t in p["tiers"] for i in t["offer_ids"]}


def test_priorities_version_conflict_and_d4(api):
    v, gen = _setup(api)
    _like_all(api, v, gen["offers"])
    rm = _assemble(api, v)["roadmaps"][0]
    oid = v["overhaul_id"]
    pkg = rm["packages"][0]
    r = api.put(f"/api/overhauls/{oid}/roadmaps/{rm['roadmap_id']}/priorities",
                json={"version": 7, "package_id": pkg["package_id"], "tiers": pkg["tiers"]}, headers=_h())
    assert r.status_code == 409 and r.get_json()["error"] == "stale_version"
    r = api.put(f"/api/overhauls/{oid}/roadmaps/{rm['roadmap_id']}/select", json={"version": 7}, headers=_h())
    assert r.status_code == 409 and r.get_json()["error"] == "stale_version"


# ── prepare-send / send ─────────────────────────────────────────────────────

def test_prepare_send_counts_and_race(api, world):
    """AC12: 4 packages + one tie = 5 offers sent, max 4 accepted, race named on the package."""
    oid, rm, prep = _tie_then_prepare(api, world)
    assert prep["counts"] == {"offers": 5, "packages": 4, "max_accepted": 4}
    pkg_a = next(p for p in rm["packages"] if p["give_ids"] == ["A"])
    assert len(prep["races"]) == 1 and prep["races"][0]["package_id"] == pkg_a["package_id"]
    assert sorted(prep["races"][0]["counterparties"]) == ["o1", "o2"]
    assert prep["receipt"]["ok"] is True and prep["receipt"]["unknowns"] == ["capacity_unknown"]
    assert prep["handoff"] == {"mode": "send"} and prep["capabilities"]["can_propose"] is True
    assert prep["prepare_token"] and prep["summary_hash"] and prep["expires_at"]
    # Default selection (no offer_ids) is tier 1 of every open package.
    r = api.post(f"/api/overhauls/{oid}/roadmaps/{rm['roadmap_id']}/prepare-send", json={"version": rm["version"]}, headers=_h())
    assert r.get_json()["counts"] == {"offers": 5, "packages": 4, "max_accepted": 4}


def test_send_partial_success_replay_and_conflicts(api, world):
    oid, rm, prep = _tie_then_prepare(api, world)
    world.propose = [("ok", "tx1"), ("fail", "sleeper_write_failed", 502), ("raise",), ("ok", "tx4"), ("ok", "tx5")]
    body = {"prepare_token": prep["prepare_token"], "summary_hash": prep["summary_hash"], "version": rm["version"],
            "idempotency_key": "idem1"}
    r = api.post(f"/api/overhauls/{oid}/send", json=body, headers=_h())
    assert r.status_code == 200, r.get_json()
    sent = r.get_json()
    states = [a["state"] for a in sent["attempts"]]
    assert states == ["proposed", "send_failed", "outcome_unknown", "proposed", "proposed"]
    assert sent["attempts"][0]["provider_transaction_id"] == "tx1"
    assert sent["attempts"][1]["error"] == {"code": "sleeper_write_failed", "message": "nope"}
    assert sent["attempts"][2]["error"]["code"] == "transport_error"
    assert len(world.propose_calls) == 5 and world.propose_calls[0]["source"] == "overhaul"
    assert set(sent["attempts"][0]) == {"attempt_id", "batch_id", "package_id", "tier", "offer_id", "state", "state_source",
                                        "provider_transaction_id", "error", "created_at", "updated_at", "observed_at"}
    assert world.events[-1][0] == "overhaul_batch_reconciled"
    assert world.events[-1][1]["sent_count"] == 3 and world.events[-1][1]["failed_count"] == 1 and world.events[-1][1]["unknown_count"] == 1
    # Replay: same key + hash -> the same batch, no new provider calls.
    r = api.post(f"/api/overhauls/{oid}/send", json=body, headers=_h())
    assert r.status_code == 200 and r.get_json()["batch_id"] == sent["batch_id"] and len(world.propose_calls) == 5
    r = api.post(f"/api/overhauls/{oid}/send", json=dict(body, summary_hash="deadbeef"), headers=_h())
    assert r.status_code == 409 and r.get_json()["error"] == "idempotency_conflict"
    # Expired / consumed token.
    r = api.post(f"/api/overhauls/{oid}/send", json=dict(body, idempotency_key="idem2"), headers=_h())
    assert r.status_code == 409 and r.get_json()["error"] == "prepare_expired"
    view = api.get(f"/api/overhauls/{oid}", headers=_h()).get_json()
    assert view["status"] == "executing" and len(view["attempts"]) == 5
    statuses = {p["give_ids"][0]: p["status"] for p in view["roadmaps"][0]["packages"]}
    assert statuses == {"A": "pending", "B": "pending", "C": "pending", "D": "pending"}


def test_send_reserved_asset_conflict_sends_nothing(api, world):
    oid, rm, prep = _tie_then_prepare(api, world)
    store.claim_reservations(league_id=LEAGUE, seller_user_id=USER, claims=[("C", "elsewhere")],
                             overhaul_id="other", batch_id="b0")
    body = {"prepare_token": prep["prepare_token"], "summary_hash": prep["summary_hash"], "version": rm["version"],
            "idempotency_key": "idem1"}
    r = api.post(f"/api/overhauls/{oid}/send", json=body, headers=_h())
    assert r.status_code == 409 and r.get_json()["error"] == "asset_reserved"
    assert world.propose_calls == [] and api.get(f"/api/overhauls/{oid}", headers=_h()).get_json()["attempts"] == []


def test_send_refuses_mismatch_and_stale_version(api, world):
    oid, rm, prep = _tie_then_prepare(api, world)
    base = {"prepare_token": prep["prepare_token"], "summary_hash": prep["summary_hash"], "version": rm["version"],
            "idempotency_key": "k"}
    r = api.post(f"/api/overhauls/{oid}/send", json=dict(base, summary_hash="x"), headers=_h())
    assert r.status_code == 409 and r.get_json()["error"] == "summary_mismatch"
    r = api.post(f"/api/overhauls/{oid}/send", json=dict(base, version=1), headers=_h())
    assert r.status_code == 409 and r.get_json()["error"] == "stale_version"
    r = api.post(f"/api/overhauls/{oid}/send", json=dict(base, prepare_token="nope"), headers=_h())
    assert r.status_code == 409 and r.get_json()["error"] == "prepare_expired"
    assert world.propose_calls == []


# ── refresh / status assertion ──────────────────────────────────────────────

def test_refresh_accepts_from_ownership_and_invalidates_the_tie(api, world):
    oid, rm, prep = _tie_then_prepare(api, world)
    body = {"prepare_token": prep["prepare_token"], "summary_hash": prep["summary_hash"], "version": rm["version"],
            "idempotency_key": "idem1"}
    sent = api.post(f"/api/overhauls/{oid}/send", json=body, headers=_h()).get_json()
    by_offer = {a["offer_id"]: a for a in sent["attempts"]}
    view = api.get(f"/api/overhauls/{oid}", headers=_h()).get_json()
    offers = view["roadmaps"][0]["offers"]
    a_to_o1 = next(o for o in offers.values() if o["give_ids"] == ["A"] and o["counterparty_user_id"] == "o1")
    a_to_o2 = next(o for o in offers.values() if o["give_ids"] == ["A"] and o["counterparty_user_id"] == "o2")
    # Rate limit: a second refresh inside 15 s is refused.
    assert api.post(f"/api/overhauls/{oid}/refresh", json={}, headers=_h()).status_code == 200
    assert api.post(f"/api/overhauls/{oid}/refresh", json={}, headers=_h()).status_code == 429
    overhaul_api._REFRESH_AT.clear()
    # Ownership moves: A left, X1 arrived -> the o1 offer was accepted.
    world.rosters[USER] = [p for p in world.rosters[USER] if p != "A"] + ["X1"]
    world.rosters["o1"] = ["A"]
    view = api.post(f"/api/overhauls/{oid}/refresh", json={}, headers=_h()).get_json()
    states = {a["offer_id"]: (a["state"], a["state_source"]) for a in view["attempts"]}
    assert states[a_to_o1["offer_id"]] == ("accepted", "ownership_refresh")
    assert states[a_to_o2["offer_id"]] == ("invalidated", "ownership_refresh")
    pkg_a = next(p for p in view["roadmaps"][0]["packages"] if p["give_ids"] == ["A"])
    assert pkg_a["status"] == "complete"
    assert view["status"] == "executing"                     # other packages still pending
    assert all(o["availability"] == "stale" for o in view["roadmaps"][0]["offers"].values() if o["give_ids"] == ["A"])
    assert store.active_reservations(LEAGUE, USER) and all(r["asset_id"] != "A" for r in store.active_reservations(LEAGUE, USER))
    assert len(world.propose_calls) == 5                     # refresh never sends
    assert by_offer[a_to_o1["offer_id"]]["state"] == "proposed"


def test_status_assertion_only_from_live_states(api, world):
    oid, rm, prep = _tie_then_prepare(api, world)
    # Selection order is package order: A(o1), A(o2) tie, then B, C, D — so
    # the third provider call is package B's only offer.
    world.propose = [("ok", "tx1"), ("ok", "tx2"), ("fail", "sleeper_write_failed", 502)]
    body = {"prepare_token": prep["prepare_token"], "summary_hash": prep["summary_hash"], "version": rm["version"],
            "idempotency_key": "idem1"}
    sent = api.post(f"/api/overhauls/{oid}/send", json=body, headers=_h()).get_json()
    proposed, failed = sent["attempts"][0], sent["attempts"][2]
    assert failed["state"] == "send_failed" and proposed["state"] == "proposed"
    r = api.post(f"/api/overhauls/{oid}/attempts/{failed['attempt_id']}/status", json={"state": "declined"}, headers=_h())
    assert r.status_code == 400 and r.get_json()["error"] == "bad_request"
    r = api.post(f"/api/overhauls/{oid}/attempts/{proposed['attempt_id']}/status", json={"state": "accepted"}, headers=_h())
    assert r.status_code == 400                               # accepted is ownership-derived, never asserted
    r = api.post(f"/api/overhauls/{oid}/attempts/{proposed['attempt_id']}/status",
                 json={"state": "declined", "note": "countered in app"}, headers=_h())
    assert r.status_code == 200 and r.get_json()["state"] == "declined" and r.get_json()["state_source"] == "user_reported"
    # Declined again: no longer live.
    r = api.post(f"/api/overhauls/{oid}/attempts/{proposed['attempt_id']}/status", json={"state": "expired"}, headers=_h())
    assert r.status_code == 400 and r.get_json()["error"] == "bad_request"
    # The tie partner (still proposed) keeps package A reserved; package B (failed) released.
    active = {r["asset_id"] for r in store.active_reservations(LEAGUE, USER)}
    assert "A" in active and "B" not in active


# ── review fixes (2026-09-07) ───────────────────────────────────────────────

PICK = "L1_2027_1_2"   # o1's original 2027 first; o1 is Sleeper roster 2 (raw_rosters order)


def _send_all(c, oid, rm, prep, key="idem1"):
    body = {"prepare_token": prep["prepare_token"], "summary_hash": prep["summary_hash"], "version": rm["version"],
            "idempotency_key": key}
    r = c.post(f"/api/overhauls/{oid}/send", json=body, headers=_h())
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def _select_and_prepare(c, v):
    rm = _assemble(c, v)["roadmaps"][0]
    oid = v["overhaul_id"]
    r = c.put(f"/api/overhauls/{oid}/roadmaps/{rm['roadmap_id']}/select", json={"version": rm["version"]}, headers=_h())
    assert r.status_code == 200, r.get_json()
    r = c.post(f"/api/overhauls/{oid}/roadmaps/{rm['roadmap_id']}/prepare-send", json={"version": rm["version"]}, headers=_h())
    assert r.status_code == 200, r.get_json()
    return oid, rm, r.get_json()


def test_refresh_never_terminalizes_on_stale_pick_table_and_accepts_on_live_read(api, world):
    """Finding 1: players come live from rosters but picks from the DB table
    (synced at session init). Give gone + receive pick not yet in the table
    must NOT become `resolved_elsewhere`; a live traded_picks read that puts
    the pick on the user's roster is what earns `accepted`.
    SABOTAGE: drop the is_pick / live_pick_holder branch in reconcile_attempt."""
    world.script[("A",)] = [(["A"], [PICK], "o1")]
    world.picks = [{"pick_id": PICK, "season": 2027, "round": 1, "original_roster_id": "2",
                    "original_user_id": "o1", "owner_user_id": "o1", "owner_username": "O1"}]
    world.traded = []                                  # live read available: nothing traded yet
    v, gen = _setup(api)
    _like_all(api, v, gen["offers"])
    oid, rm, prep = _select_and_prepare(api, v)
    assert prep["receipt"]["ok"], prep["receipt"]
    sent = _send_all(api, oid, rm, prep)
    pick_attempt = next(a for a in sent["attempts"] if store.list_offers(oid) and
                        next(o for o in store.list_offers(oid) if o["offer_id"] == a["offer_id"])["receive_ids"] == [PICK])
    # o1 accepted in Sleeper: A left my roster; the pick table still says o1 holds the pick.
    world.rosters[USER] = [p for p in MY_PLAYERS if p != "A"]
    world.rosters["o1"] = ["X1", "A"]
    world.traded = None                                # live read unavailable -> DB table only
    view = api.post(f"/api/overhauls/{oid}/refresh", json={}, headers=_h()).get_json()
    states = {a["attempt_id"]: a["state"] for a in view["attempts"]}
    assert states[pick_attempt["attempt_id"]] == "proposed"          # not resolved_elsewhere
    assert store.get_overhaul(oid)["snapshot"]["pick_ownership_source"] == "db"
    assert {r["asset_id"] for r in store.active_reservations(LEAGUE, USER)} >= {"A"}
    # A live read confirms the pick moved to my roster (roster 1) -> accepted.
    overhaul_api._REFRESH_AT.clear()
    world.traded = [{"season": "2027", "round": 1, "roster_id": 2, "owner_id": 1, "previous_owner_id": 2}]
    view = api.post(f"/api/overhauls/{oid}/refresh", json={}, headers=_h()).get_json()
    a = next(a for a in view["attempts"] if a["attempt_id"] == pick_attempt["attempt_id"])
    assert (a["state"], a["state_source"]) == ("accepted", "ownership_refresh")
    assert store.get_overhaul(oid)["snapshot"]["pick_ownership_source"] == "live"
    assert store.get_overhaul(oid)["snapshot"]["my_pick_ids"] == [PICK]
    assert next(p for p in view["roadmaps"][0]["packages"] if p["give_ids"] == ["A"])["status"] == "complete"
    assert all(r["asset_id"] != "A" for r in store.active_reservations(LEAGUE, USER))


def test_refresh_sweeps_stuck_queued_and_sending_attempts(api, world):
    """Finding 2: a crash mid-batch leaves `queued`/`sending` rows that nothing
    reconciles. Older than 5 min: sending -> outcome_unknown (worker_lost),
    queued -> stale (terminal, reservation released). Fresh ones are untouched.
    SABOTAGE: remove the stuck sweep from the refresh route."""
    oid, rm, prep = _tie_then_prepare(api, world)
    pkg_b = next(p for p in rm["packages"] if p["give_ids"] == ["B"])
    pkg_c = next(p for p in rm["packages"] if p["give_ids"] == ["C"])
    pkg_d = next(p for p in rm["packages"] if p["give_ids"] == ["D"])
    row = lambda aid, pkg, state: {"attempt_id": aid, "batch_id": "bt_x", "overhaul_id": oid, "roadmap_id": rm["roadmap_id"],
                                   "roadmap_version": rm["version"], "package_id": pkg["package_id"], "tier": 1,
                                   "offer_id": pkg["tiers"][0]["offer_ids"][0], "idempotency_key": "kx",
                                   "request_hash": "hx", "state": state}
    store.insert_attempts([row("at_q", pkg_b, "queued"), row("at_s", pkg_c, "sending"), row("at_new", pkg_d, "queued")])
    store.claim_reservations(league_id=LEAGUE, seller_user_id=USER, overhaul_id=oid, batch_id="bt_x",
                             claims=[("B", pkg_b["package_id"]), ("C", pkg_c["package_id"]), ("D", pkg_d["package_id"])])
    old = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    with db.engine.begin() as conn:
        conn.execute(update(store.T_ATTEMPTS).where(store.T_ATTEMPTS.c.attempt_id.in_(["at_q", "at_s"])).values(updated_at=old))
    view = api.post(f"/api/overhauls/{oid}/refresh", json={}, headers=_h()).get_json()
    by_id = {a["attempt_id"]: a for a in view["attempts"]}
    assert (by_id["at_q"]["state"], by_id["at_q"]["state_source"]) == ("stale", "server")
    assert (by_id["at_s"]["state"], by_id["at_s"]["state_source"]) == ("outcome_unknown", "server")
    assert by_id["at_s"]["error"]["code"] == "worker_lost"
    assert by_id["at_new"]["state"] == "queued"                      # not old enough
    active = {r["asset_id"] for r in store.active_reservations(LEAGUE, USER)}
    assert "B" not in active and {"C", "D"} <= active               # stale is terminal; outcome_unknown is live


def test_settings_change_clears_exhausted_subsets_and_regenerate_refreshes_stale_rows(api, world):
    """Finding 3: exhausted_subsets persisted across revisions, so /generate
    after an outlook or pool change was permanently dry; and a package_hash
    collision with a stale undecided row dropped the card instead of
    re-freshening it under the new revision.
    SABOTAGE: keep exhausted_subsets on invalidation, or `continue` on every hash hit."""
    v, gen = _setup(api)
    oid = v["overhaul_id"]
    assert gen["generation"]["exhausted_subsets"]
    v = _settings(api, oid, v["revision"], eligible_asset_ids=["A", "B", "C", "D"])
    assert v["generation"]["exhausted_subsets"] == []
    assert api.get(f"/api/overhauls/{oid}/offers", headers=_h()).get_json()["offers"] == []   # all stale
    r = api.post(f"/api/overhauls/{oid}/generate", json={"revision": v["revision"]}, headers=_h())
    assert r.status_code == 200, r.get_json()
    gen2 = r.get_json()
    assert gen2["generation"]["new_offers"] == 5 and gen2["generation"]["total_offers"] == 5
    assert gen2["generation"]["shortfall_reason"] is None
    assert len(gen2["offers"]) == 5 and all(o["availability"] == "fresh" for o in gen2["offers"])
    assert all(o["revision"] == v["revision"] for o in store.list_offers(oid))
    assert len(api.get(f"/api/overhauls/{oid}/offers", headers=_h()).get_json()["offers"]) == 5


def test_send_refuses_when_can_propose_is_false(api, world):
    """Finding 4: send must gate on capabilities.can_propose (the
    trade.send_in_sleeper flag), before any reservation or attempt exists.
    SABOTAGE: remove the can_propose check in the send route."""
    oid, rm, prep = _tie_then_prepare(api, world)
    ff._flags_cache = {**ff._flags_cache, "trade.send_in_sleeper": False}
    body = {"prepare_token": prep["prepare_token"], "summary_hash": prep["summary_hash"], "version": rm["version"],
            "idempotency_key": "idem1"}
    r = api.post(f"/api/overhauls/{oid}/send", json=body, headers=_h())
    assert r.status_code == 409 and r.get_json()["error"] == "capability_unavailable"
    assert store.active_reservations(LEAGUE, USER) == [] and store.list_attempts(oid) == []
    assert world.propose_calls == []


@dataclass(frozen=True)
class _Team:
    id: str
    roster: tuple


def test_legality_check_excludes_tie_partners_and_counts_one_alternative_per_package(api, world):
    """Finding 5 (D6): the per-counterparty legality union subtracted every
    other selected offer's gives, tie partners included, so the AC12 race
    degraded to `outgoing_asset_not_owned`; capacity must count one
    alternative per package. Package A nets +1 per alternative, B/C/D net 0:
    6 + 1 = 7 fits a 7-cap; counting both tied offers (8) would not.
    SABOTAGE: drop the same-package exclusion from others_out/others_in."""
    world.script[("A",)] = [(["A"], ["X1", "Y1"], "o1"), (["A"], ["X2", "Y2"], "o2")]
    world.rosters["o1"], world.rosters["o2"] = ["X1", "Y1"], ["X2", "Y2"]
    teams = {USER: _Team(USER, tuple(MY_PLAYERS)), **{u: _Team(u, tuple(r)) for u, r in world.rosters.items() if u != USER}}
    world.roster_ctx = SimpleNamespace(teams=teams, viewer_id=USER, assets={}, rules=SimpleNamespace(capacity=7))
    calls = []

    def fake_evaluate(*, viewer, partner, give, receive, assets, rules):
        calls.append((partner.id, tuple(viewer.roster)))
        return {"unknowns": [] if set(give) <= set(viewer.roster) else ["outgoing_asset_not_owned"], "teams": {}}

    with patch("backend.trade_roster.evaluate", fake_evaluate):
        oid, rm, prep = _tie_then_prepare(api, world)
    receipt = prep["receipt"]
    assert "outgoing_asset_not_owned" not in receipt["unknowns"] and "capacity_unknown" not in receipt["unknowns"]
    assert receipt["ok"] is True and receipt["blockers"] == [], receipt
    seen = dict(calls)
    assert "A" in seen["o1"] and "A" in seen["o2"]          # the tie partner is an alternative, not a trade
    assert "B" not in seen["o1"] and "X3" in seen["o1"]     # other packages' gives out, receives in
