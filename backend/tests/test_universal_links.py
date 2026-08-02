"""FB #239 — Universal Links AASA contract for invite/share links.

The iOS app's associated-domains entitlement (mobile/app.json +
mobile/ios/DTFDynastyTradeFinder/DTFDynastyTradeFinder.entitlements) points
Apple's CDN at /.well-known/apple-app-site-association. Apple requires:
HTTP 200 with no redirect, Content-Type application/json, and an `applinks`
block whose appID matches <TeamID>.<bundle id>.

Scope matters: the components must claim ONLY the shared surfaces (profiles,
share landings, invite/referral roots) — never "/" unqualified — so the rest
of the web app keeps opening in the browser.

Broader account-surface coverage lives in test_account_data_rights.py; this
file pins the invite-link matchers specifically.
"""
import backend.server as server

APP_ID = "N5Y4N2Q49A.com.fantasytradefinder.app"


def _get_aasa(monkeypatch):
    monkeypatch.delenv("APPLE_TEAM_ID", raising=False)
    server.app.config["TESTING"] = True
    c = server.app.test_client()
    return c.get("/.well-known/apple-app-site-association")


def test_aasa_headers_and_shape(monkeypatch):
    r = _get_aasa(monkeypatch)
    assert r.status_code == 200                       # direct 200, no redirect
    assert r.content_type.startswith("application/json")
    body = r.get_json()
    details = body["applinks"]["details"]
    assert body["applinks"]["apps"] == []
    assert len(details) == 1
    assert details[0]["appID"] == APP_ID
    assert details[0]["appIDs"] == [APP_ID]


def test_aasa_claims_invite_and_share_surfaces_only(monkeypatch):
    r = _get_aasa(monkeypatch)
    detail = r.get_json()["applinks"]["details"][0]
    components = detail["components"]
    # Invite links: /?league=<id>&ref=<username> — mobile's buildInviteUrl
    # omits `ref` when the username is unknown, so each param must match on
    # its own.
    assert {"/": "/", "?": {"ref": "?*"}} in components
    assert {"/": "/", "?": {"league": "?*"}} in components
    # Share landings (/s/trade/<match_id>, /s/p/<short_id>) and profiles.
    assert {"/": "/s/*"} in components
    assert {"/": "/u/*"} in components
    # Never claim the bare web app — browser pages must stay in the browser.
    assert {"/": "/"} not in components
    assert {"/": "/*"} not in components
    assert "/" not in detail["paths"] and "/*" not in detail["paths"]


def test_aasa_route_is_not_flag_gated(monkeypatch):
    # Apple's CDN fetches this unauthenticated and outside any feature-flag
    # context; a dark flag must never 404 it.
    monkeypatch.setattr(server, "is_enabled", lambda k: False)
    r = _get_aasa(monkeypatch)
    assert r.status_code == 200
    assert r.get_json()["applinks"]["details"][0]["appID"] == APP_ID
