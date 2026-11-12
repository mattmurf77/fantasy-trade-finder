"""D1 Update 1: MFL free-agent moves (docs/plans/in-app-claims/design.md §4-§5).

Two layers, no network anywhere:

  * the adapter, `mfl_write.build_fa_move_params` / `fa_move`, against MFL's
    DOCUMENTED import types (fcfsWaiver, blindBidWaiverRequest, waiverRequest;
    api_info read 2026-11-11). The parameter names are documentation, not a
    recorded transaction: these tests pin our reading of the docs, so the
    verification run (design.md §8) is a diff against them;
  * the server path, `_fa_move_core_mfl` + `_fa_move_send`, through the real
    move route with test_fa_move_route.py's harness, an injected urllib opener
    standing in for MFL, and the rosters export and crosswalk stubbed.

And the flag-off identity: with `mfl.send_add_drop` off, or on with the shapes
unverified, an MFL league's capability and move route answer exactly what they
answered before Update 1, and nothing reaches the opener.
"""
from __future__ import annotations

import ast
import inspect
import io
import json
import textwrap
import urllib.error
import urllib.parse
import uuid

import pytest

import backend.database as db_module
import backend.mfl_service as mfl_service
import backend.mfl_write as mfl_write
import backend.server as server
import backend.sleeper_write as sleeper_write
from backend import fa_move_copy as copy
from backend.write_outcome import OUTCOME_UNKNOWN
from backend.tests.test_fa_move_route import (  # noqa: F401  (h is a fixture)
    ADD, DROP, KEEP, THEIRS, TOKEN, USER, _ABSENT, _Resp, _err, h,
)

MFL_LEAGUE = "61204"
MY_FID, THEIR_FID = "0003", "0004"
HOST = "www44.myfantasyleague.com"
YEAR = 2026
MFL_USER = "Coach_Matt"
XWALK = {ADD: "15001", DROP: "15002", KEEP: "15003", THEIRS: "15004"}
MV1 = copy.MFL_ROSTER_MOVES_V1
PRE_UPDATE_1 = {"mode": "unsupported", "claims": False, "league_platform": "mfl",
                "connect": "not_linked", "consent_until": None, "copy": {}}


# ---------------------------------------------------------------------------
# A simulated MFL: the import endpoint (opener) and the rosters export (stub)
# ---------------------------------------------------------------------------

class Mfl:
    BEHAVIOURS = {
        "ok": lambda: _Resp(b'{"status": "OK"}'),
        "ok_xml": lambda: _Resp(b"<status>OK</status>"),
        "refused": lambda: _Resp(b"<error>Roster limit exceeded</error>"),
        "empty": lambda: _Resp(b""),
        "auth": "http_401",
        "throttled": "http_429",
        "http_500": "http_500",
        "connect_refused": urllib.error.URLError(ConnectionRefusedError(61, "refused")),
        "read_timeout": TimeoutError("The read operation timed out"),
    }

    def __init__(self):
        self.mode = "ok"
        self.calls: list = []
        self.on_call = None

    def opener(self, request, timeout=None):
        self.calls.append((request, timeout))
        if self.on_call is not None:
            self.on_call(request)
        b = self.BEHAVIOURS[self.mode]
        if isinstance(b, str):
            raise urllib.error.HTTPError(request.full_url, int(b[5:]), "err", {},
                                         io.BytesIO(b"<html>oops</html>"))
        if isinstance(b, BaseException):
            raise b
        return b()

    def params(self, i=0):
        q = urllib.parse.urlsplit(self.calls[i][0].full_url).query
        return dict(urllib.parse.parse_qsl(q, keep_blank_values=True))


def _rosters_export(mine=("15002", "15003")):
    return {"rosters": {"franchise": [
        {"id": MY_FID, "player": [{"id": p} for p in mine]},
        {"id": THEIR_FID, "player": [{"id": "15004"}]}]}}


@pytest.fixture()
def m(h, monkeypatch):
    """test_fa_move_route's harness plus a linked, consented-ready MFL league."""
    mfl = Mfl()
    h.mfl = mfl
    h.flags = {"mfl.send_add_drop", "trade.send_in_mfl"}
    h.mfl_rosters = _rosters_export()
    monkeypatch.setattr(mfl_write, "FA_MOVE_SHAPES_VERIFIED", True)
    real = mfl_write.fa_move
    monkeypatch.setattr(mfl_write, "fa_move",
                        lambda cookie, host, year, req: real(cookie, host, year, req,
                                                             _opener=mfl.opener))

    def _fetch_rosters(league_id, year, host, cookie=None, raise_auth=False, **_):
        h.roster_reads = getattr(h, "roster_reads", 0) + 1
        if isinstance(h.mfl_rosters, BaseException):
            raise h.mfl_rosters
        return json.loads(json.dumps(h.mfl_rosters))
    monkeypatch.setattr(mfl_service, "fetch_rosters", _fetch_rosters)
    monkeypatch.setattr(mfl_service, "resolve_host",
                        lambda *a, **k: pytest.fail("the stored host must be used"))
    monkeypatch.setattr(server, "_sleeper_to_mfl_map", lambda: dict(XWALK))
    monkeypatch.setitem(copy.CURRENT_CONSENT_VERSION, "mfl", MV1)
    monkeypatch.setattr(copy, "DRAFT_CONSENT_VERSIONS",
                        frozenset({copy.ESPN_ROSTER_MOVES_V1, copy.ESPN_ROSTER_MOVES_V2}))
    with h.engine.begin() as conn:
        conn.execute(db_module.leagues_table.insert().values(
            sleeper_league_id=MFL_LEAGUE, user_id=USER, name="Dynasty MFL", platform="mfl",
            platform_season=YEAR, platform_host=HOST, platform_auth="cookie",
            platform_my_team=MY_FID))
    db_module.upsert_mfl_credential(USER, MFL_USER, sleeper_write.encrypt_token("MFL_USER_ID=abc"),
                                    YEAR)
    db_module.upsert_league_members(MFL_LEAGUE, [
        {"user_id": server._mfl_member_id(MFL_LEAGUE, MY_FID), "username": "me",
         "player_ids": [DROP, KEEP]},
        {"user_id": server._mfl_member_id(MFL_LEAGUE, THEIR_FID), "username": "them",
         "player_ids": [THEIRS]}])
    return h


def post(h, **over):
    over.setdefault("league_id", MFL_LEAGUE)
    over.setdefault("consent", {"copy_version": MV1, "locale": "en-US"})
    return h.post(**over)


def mfl_roster(h):
    rows = db_module.load_league_members(MFL_LEAGUE)
    me = server._mfl_member_id(MFL_LEAGUE, MY_FID)
    return next(json.loads(r["roster_data"]) for r in rows if r["user_id"] == me)


# ---------------------------------------------------------------------------
# The adapter: request builder (documentation-pinned)
# ---------------------------------------------------------------------------

def _req(**over):
    base = dict(league_id=MFL_LEAGUE, add_player_id="15001", drop_player_id="15002",
                move_kind="add", faab_bid=None, waiver_round=None)
    base.update(over)
    return mfl_write.FaMoveRequest(**base)


def test_add_drop_is_one_fcfs_import_with_exact_params():
    op, params = mfl_write.build_fa_move_params(_req())
    assert op == "fcfsWaiver"
    assert params == {"TYPE": "fcfsWaiver", "L": MFL_LEAGUE, "ADD": "15001", "DROP": "15002",
                      "JSON": "1"}


def test_add_into_an_open_slot_sends_no_drop():
    _, params = mfl_write.build_fa_move_params(_req(drop_player_id=None))
    assert params == {"TYPE": "fcfsWaiver", "L": MFL_LEAGUE, "ADD": "15001", "JSON": "1"}


@pytest.mark.parametrize("drop,picks", [("15002", "15001_7_15002"), (None, "15001_7_0000")])
def test_blind_bid_claim_packs_add_bid_drop(drop, picks):
    op, params = mfl_write.build_fa_move_params(_req(move_kind="claim", faab_bid=7,
                                                     drop_player_id=drop))
    assert op == "blindBidWaiverRequest"
    assert params == {"TYPE": "blindBidWaiverRequest", "L": MFL_LEAGUE, "PICKS": picks,
                      "JSON": "1"}


def test_a_typed_zero_bid_is_a_real_bid():
    _, params = mfl_write.build_fa_move_params(_req(move_kind="claim", faab_bid=0))
    assert params["PICKS"] == "15001_0_15002"


def test_priority_claim_needs_its_round_and_a_drop():
    op, params = mfl_write.build_fa_move_params(_req(move_kind="claim", waiver_round=1))
    assert op == "waiverRequest"
    assert params == {"TYPE": "waiverRequest", "L": MFL_LEAGUE, "ROUND": "1",
                      "PICKS": "15001_15002", "JSON": "1"}
    for bad in (_req(move_kind="claim"), _req(move_kind="claim", waiver_round=1,
                                              drop_player_id=None)):
        with pytest.raises(mfl_write.MflWriteError) as e:
            mfl_write.build_fa_move_params(bad)
        assert e.value.kind == "input"


@pytest.mark.parametrize("req", [
    _req(), _req(drop_player_id=None), _req(move_kind="claim", faab_bid=3),
    _req(move_kind="claim", waiver_round=2)])
def test_never_replace_never_impersonate(req):
    """REPLACE would wipe the user's other claims in that round; FRANCHISE_ID
    is commissioner impersonation. Neither is ever sent."""
    _, params = mfl_write.build_fa_move_params(req)
    assert not {"REPLACE", "FRANCHISE_ID"} & set(params)


@pytest.mark.parametrize("req", [
    _req(league_id="abc"), _req(add_player_id="DROP TABLE"), _req(drop_player_id="15001"),
    _req(add_player_id=""), _req(move_kind="trade"), _req(faab_bid=5),
    _req(move_kind="claim", faab_bid=-1), _req(move_kind="claim", faab_bid=True)])
def test_malformed_moves_are_refused_as_input(req):
    with pytest.raises(mfl_write.MflWriteError) as e:
        mfl_write.build_fa_move_params(req)
    assert e.value.kind == "input"


# ---------------------------------------------------------------------------
# The adapter: the verification gate, the result, the error classification
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind,extra", [("add", {}), ("claim", {"faab_bid": 4})])
def test_unverified_refuses_before_building_or_sending(monkeypatch, kind, extra):
    monkeypatch.setattr(mfl_write, "FA_MOVE_SHAPES_VERIFIED", False)
    monkeypatch.setattr(mfl_write, "build_fa_move_params",
                        lambda req: pytest.fail("built while unverified"))
    mfl = Mfl()
    with pytest.raises(mfl_write.MflWriteError) as e:
        mfl_write.fa_move("c", HOST, YEAR, _req(move_kind=kind, **extra), _opener=mfl.opener)
    assert e.value.kind == "config" and mfl.calls == []


def test_claims_need_their_own_verification(monkeypatch):
    monkeypatch.setattr(mfl_write, "FA_MOVE_SHAPES_VERIFIED", True)
    assert mfl_write.fa_move_verified("add") and not mfl_write.fa_move_verified("claim")


def test_the_shipped_constants_are_off():
    assert mfl_write.FA_MOVE_SHAPES_VERIFIED is False
    assert mfl_write.FA_CLAIM_SHAPE_VERIFIED is False


@pytest.mark.parametrize("mode", ["ok", "ok_xml"])
def test_verified_add_is_complete_and_claim_is_pending(monkeypatch, mode):
    monkeypatch.setattr(mfl_write, "FA_MOVE_SHAPES_VERIFIED", True)
    monkeypatch.setattr(mfl_write, "FA_CLAIM_SHAPE_VERIFIED", True)
    mfl = Mfl()
    mfl.mode = mode
    out = mfl_write.fa_move("MFL_USER_ID=abc", HOST, YEAR, _req(), _opener=mfl.opener)
    assert {k: out[k] for k in ("status", "result", "transaction_id", "added", "dropped")} == {
        "status": "complete", "result": "accepted", "transaction_id": None,
        "added": [], "dropped": []}
    req, timeout = mfl.calls[0]
    assert req.full_url.startswith(f"https://{HOST}/{YEAR}/import?")
    assert req.get_header("Cookie") == "MFL_USER_ID=abc" and req.get_method() == "GET"
    assert timeout == mfl_write.FA_MOVE_WRITE_TIMEOUTS_S[0]
    out = mfl_write.fa_move("c", HOST, YEAR, _req(move_kind="claim", faab_bid=2),
                            _opener=mfl.opener)
    assert out["status"] == "pending" and len(mfl.calls) == 2


@pytest.mark.parametrize("mode,kind", [
    ("auth", "auth"), ("throttled", "network"), ("connect_refused", "network"),
    ("refused", "error"), ("http_500", OUTCOME_UNKNOWN), ("read_timeout", OUTCOME_UNKNOWN),
    ("empty", OUTCOME_UNKNOWN)])
def test_errors_are_classified_by_write_outcome_rules(monkeypatch, mode, kind):
    monkeypatch.setattr(mfl_write, "FA_MOVE_SHAPES_VERIFIED", True)
    mfl = Mfl()
    mfl.mode = mode
    with pytest.raises(mfl_write.MflWriteError) as e:
        mfl_write.fa_move("c", HOST, YEAR, _req(), _opener=mfl.opener)
    assert e.value.kind == kind and len(mfl.calls) == 1


def test_write_path_timeouts_fit_the_server_worst_case():
    assert sum(mfl_write.FA_MOVE_WRITE_TIMEOUTS_S) <= server._FA_MOVE_WRITE_PATH_MAX_S


# ---------------------------------------------------------------------------
# Flag-off identity
# ---------------------------------------------------------------------------

def test_flag_off_capability_is_byte_identical(m):
    m.flags = set()
    assert server._fa_move_capability(m.sess, MFL_LEAGUE, None) == (PRE_UPDATE_1, {})


def test_flag_on_but_unverified_capability_is_byte_identical(m, monkeypatch):
    monkeypatch.setattr(mfl_write, "FA_MOVE_SHAPES_VERIFIED", False)
    assert server._fa_move_capability(m.sess, MFL_LEAGUE, None) == (PRE_UPDATE_1, {})


@pytest.mark.parametrize("flags,verified", [(set(), True), ({"mfl.send_add_drop"}, False),
                                            ({"sleeper.send_add_drop"}, True)])
def test_route_404s_and_sends_nothing_unless_live(m, monkeypatch, flags, verified):
    m.flags = flags
    monkeypatch.setattr(mfl_write, "FA_MOVE_SHAPES_VERIFIED", verified)
    r = post(m)
    assert r.status_code == 404 and _err(r)["error"] == "feature_disabled"
    assert m.mfl.calls == [] and getattr(m, "roster_reads", 0) == 0
    assert m.moves() == [] and m.consents() == []


def test_the_shipped_flag_is_off():
    cfg = json.loads(open(server.__file__.replace("backend/server.py",
                                                  "config/features.json")).read())
    assert cfg["mfl.send_add_drop"] is False
    import backend.feature_flags as ff
    assert ff.DEFAULT_FLAGS["mfl.send_add_drop"] is False


def test_espn_has_no_switch_and_stays_unsupported(m):
    assert "espn" not in server._FA_MOVE_FLAGS and not server._fa_move_live("espn")


def test_free_agents_route_mfl_branch_is_gated_first():
    """Structural (the route needs a whole initialized session): the MFL
    claim-context branch's condition starts with `_fa_move_live("mfl")`, which
    reads the kill switch first, so flag off never even reads the league row."""
    src = textwrap.dedent(inspect.getsource(server.league_free_agents_route))
    tests = [n.test for n in ast.walk(ast.parse(src)) if isinstance(n, ast.If)
             and "_fa_move_live" in ast.unparse(n.test)]
    assert len(tests) == 1
    first = tests[0].values[0] if isinstance(tests[0], ast.BoolOp) else tests[0]
    assert ast.unparse(first) == "_fa_move_live('mfl')"
    live = textwrap.dedent(inspect.getsource(server._fa_move_live))
    assert live.index("is_enabled(flag)") < live.index('platform == "mfl"')


# ---------------------------------------------------------------------------
# Capability when live
# ---------------------------------------------------------------------------

def test_live_connected_is_submit_without_claims(m):
    move, rows = server._fa_move_capability(m.sess, MFL_LEAGUE, None)
    assert move == {"mode": "submit", "claims": False, "league_platform": "mfl",
                    "connect": "ok", "consent_until": None, "copy": {}}
    assert rows == {}


def test_live_but_not_connectable_is_never_submit(m):
    """Contract §6: the binary has no MFL connect screen."""
    m.sess["verified"] = False
    assert server._fa_move_capability(m.sess, MFL_LEAGUE, None)[0]["mode"] == "unsupported"
    m.sess["verified"] = True
    with m.engine.begin() as conn:
        conn.execute(db_module.leagues_table.update().values(user_id="someone_else"))
    move = server._fa_move_capability(m.sess, MFL_LEAGUE, None)[0]
    assert (move["mode"], move["connect"]) == ("unsupported", "other_account")
    db_module.delete_mfl_credential(USER)
    move = server._fa_move_capability(m.sess, MFL_LEAGUE, None)[0]
    assert (move["mode"], move["connect"]) == ("unsupported", "not_linked")


# ---------------------------------------------------------------------------
# The move route, live
# ---------------------------------------------------------------------------

def test_add_drop_completes_crosswalked_and_saves_the_roster(m):
    r = post(m)
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["status"] == "complete" and body["league_platform"] == "mfl"
    assert body["lines"] == ["Aaron Add added, Drew Drop dropped in Dynasty MFL."]
    assert "platform_transaction_id" not in body
    assert len(m.mfl.calls) == 1
    assert m.mfl.params() == {"TYPE": "fcfsWaiver", "L": MFL_LEAGUE, "ADD": "15001",
                              "DROP": "15002", "JSON": "1"}
    (grant,) = m.consents()
    assert (grant["platform"], grant["platform_user_id"], grant["copy_version"]) == (
        "mfl", MFL_USER.lower(), MV1)
    sent, result = sorted(m.moves(body["attempt_id"]), key=lambda x: x["phase"] != "sent")
    assert sent["platform"] == "mfl" and json.loads(sent["add_player_ids"]) == [ADD]
    assert result["result"] == "accepted" and result["status"] == "complete"
    assert mfl_roster(m) == [KEEP, ADD]
    assert [e[2]["props"]["league_platform"] for e in m.events_named("fa_move_write_succeeded")] == ["mfl"]


def test_grant_and_sent_row_exist_when_mfl_is_called(m):
    """R15.8: consent is committed before any platform call, and the `sent`
    row exists before the write (the double-move block's anchor)."""
    seen = {}

    def _inspect(request):
        seen["grants"] = [c for c in m.consents() if c["kind"] == "grant"]
        seen["sent"] = [x for x in m.moves() if x["phase"] == "sent"]
        seen["active"] = server._fa_move_grant(USER, "mfl", MFL_USER.lower(), m.now)
    m.mfl.on_call = _inspect
    assert post(m).status_code == 200
    assert len(seen["grants"]) == 1 and len(seen["sent"]) == 1
    assert seen["active"] is not None, "the grant was not in force when MFL was called"
    assert seen["sent"][0]["consent_id"] == seen["grants"][0]["consent_id"]


def test_a_repeat_attempt_replays_and_never_sends_twice(m):
    attempt = str(uuid.uuid4())
    first = post(m, attempt_id=attempt)
    again = post(m, attempt_id=attempt)
    assert first.status_code == again.status_code == 200
    assert again.get_json() == first.get_json() and len(m.mfl.calls) == 1


def test_outcome_unknown_is_never_retried_and_blocks_a_new_tap(m):
    m.mfl.mode = "read_timeout"
    r = post(m)
    assert r.status_code == 502 and _err(r)["error"] == "mfl_outcome_unknown"
    (result,) = [x for x in m.moves() if x["phase"] == "result"]
    assert result["result"] == "unknown"
    m.mfl.mode = "ok"
    r2 = post(m, consent=_ABSENT)
    assert r2.status_code == 409 and _err(r2)["error"] == "move_in_progress"
    assert len(m.mfl.calls) == 1


@pytest.mark.parametrize("mode,status,code,kind", [
    ("throttled", 502, "mfl_write_failed", "network"),
    ("connect_refused", 502, "mfl_write_failed", "network"),
    ("refused", 502, "mfl_write_failed", None),
    ("http_500", 502, "mfl_outcome_unknown", None)])
def test_failures_map_to_the_contract_codes(m, mode, status, code, kind):
    m.mfl.mode = mode
    r = post(m)
    body = _err(r)
    assert (r.status_code, body["error"], body.get("kind")) == (status, code, kind)
    assert len(m.mfl.calls) == 1 and mfl_roster(m) == [DROP, KEEP]


def test_a_rejected_cookie_drops_the_credential_and_the_grant(m):
    m.mfl.mode = "auth"
    r = post(m)
    assert r.status_code == 409 and _err(r)["error"] == "mfl_rejected"
    assert db_module.get_mfl_credential(USER) is None
    kinds = sorted(c["kind"] for c in m.consents())
    assert kinds == ["grant", "withdrawal"]
    (w,) = [c for c in m.consents() if c["kind"] == "withdrawal"]
    assert w["withdrawn_via"] == "credential_rejected"
    assert m.events_named("fa_move_consent_withdrawn")


def test_an_expired_cookie_on_the_rosters_read_sends_nothing(m):
    m.mfl_rosters = mfl_service.MflAuthError("expired")
    r = post(m)
    assert r.status_code == 409 and _err(r)["error"] == "mfl_expired"
    assert m.mfl.calls == [] and db_module.get_mfl_credential(USER) is None
    assert [x for x in m.moves()] == []


@pytest.mark.parametrize("setup,status,code", [
    (lambda h: setattr(h, "mfl_rosters", {"oops": 1}), 502, "mfl_write_failed"),
    (lambda h: setattr(h, "mfl_rosters", _rosters_export(mine=("15002", "15003", "15001"))),
     422, "player_unavailable"),
    (lambda h: h.mfl_rosters["rosters"]["franchise"][1]["player"].append({"id": "15001"}),
     422, "player_unavailable"),
    (lambda h: setattr(h, "mfl_rosters", _rosters_export(mine=("15003",))),
     422, "asset_not_owned"),
])
def test_pre_write_refusals_send_nothing(m, setup, status, code):
    setup(m)
    r = post(m)
    assert (r.status_code, _err(r)["error"]) == (status, code)
    assert m.mfl.calls == [] and [x for x in m.moves()] == []


def test_an_unmapped_player_is_refused_before_any_mfl_call(m, monkeypatch):
    monkeypatch.setattr(server, "_sleeper_to_mfl_map", lambda: {DROP: "15002"})
    r = post(m)
    body = _err(r)
    assert r.status_code == 422 and body["error"] == "player_unavailable"
    assert "couldn't match" in body["message"] and "MFL" in body["message"]
    assert m.mfl.calls == [] and getattr(m, "roster_reads", 0) == 0


def test_claims_stay_off_on_mfl(m):
    r = post(m, move_kind="claim", faab_bid=5)
    assert r.status_code == 422 and _err(r)["error"] == "waiver_claim_unsupported"
    assert m.mfl.calls == [] and m.moves() == []


def test_no_consent_text_means_no_move(m, monkeypatch):
    """Today's real state: MFL has no CURRENT consent version (legal), so
    even live the route can only ask for consent it can't show."""
    monkeypatch.delitem(copy.CURRENT_CONSENT_VERSION, "mfl")
    r = post(m)
    body = _err(r)
    assert r.status_code == 409 and body["error"] == "consent_required"
    assert body.get("consent") is None and m.mfl.calls == [] and m.consents() == []


def test_without_consent_in_the_body_it_asks_first(m):
    r = post(m, consent=_ABSENT)
    body = _err(r)
    assert r.status_code == 409 and body["error"] == "consent_required"
    assert body["consent"]["copy_version"] == MV1 and m.mfl.calls == []


def test_another_users_league_row_is_not_linked(m):
    with m.engine.begin() as conn:
        conn.execute(db_module.leagues_table.update().values(user_id="someone_else"))
    r = post(m)
    assert r.status_code == 409 and _err(r)["error"] == "mfl_not_linked"
    assert m.mfl.calls == [] and m.consents() == []


def test_the_cookie_is_never_logged_or_returned(m, caplog):
    m.mfl.mode = "refused"
    with caplog.at_level("DEBUG"):
        r = post(m)
    assert "MFL_USER_ID" not in r.get_data(as_text=True)
    assert "MFL_USER_ID" not in caplog.text
    assert all("MFL_USER_ID" not in json.dumps(e, default=str) for e in m.events)
