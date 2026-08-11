"""P0-3 — the invite JOIN deep link, server half (mobile UX audit 2026-08-09).

Spec: docs/plans/audit-p0-remediation/lld-p0-3.md §1.5 (T-1…T-13).
Branch: p0-remediation-2026-08-10.

The finding: an invite link dropped the recipient on a generic landing with no
league context and no inviter named. The server half is three additive,
read-only pieces plus one default-OFF flag:

  S1  AASA claims /app/league/join/*        (UNFLAGGED, ahead of the emitter)
  S2  GET /app/league/join/<id> → 302       (Safari/desktop fallback)
  S3  GET /api/league/invite-meta           (public Sleeper name only)
  S4  growth.invite_join_link, default OFF  (EMITTER ONLY)

THE ORDERING HAZARD IS THE POINT. Apple's CDN caches AASA for up to ~24h, so
the claim and the parsers must be live BEFORE any client emits the new URL —
otherwise every invite lands in Safari, which is strictly worse than the legacy
/?league= link. That is why S1/S2/S3 are unflagged and only the emitter is
gated (T-12).
"""
import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine

import backend.database as db_module
import backend.feature_flags as feature_flags
import backend.server as server
from backend.database import metadata, leagues_table

APP_ID = "N5Y4N2Q49A.com.fantasytradefinder.app"


def _client():
    server.app.config["TESTING"] = True
    return server.app.test_client()


def _aasa(monkeypatch):
    monkeypatch.delenv("APPLE_TEAM_ID", raising=False)
    return _client().get("/.well-known/apple-app-site-association").get_json()[
        "applinks"]["details"][0]


# ═══════════════════════════════════════════════════════════════════════════
# S1 — the AASA claim
# ═══════════════════════════════════════════════════════════════════════════

def test_t1_aasa_claims_league_join_path(monkeypatch):
    detail = _aasa(monkeypatch)
    assert {"/": "/app/league/join/*"} in detail["components"]
    assert "/app/league/join/*" in detail["paths"]


def test_t2_aasa_still_claims_the_four_existing_patterns(monkeypatch):
    """Additive means additive: FB #239's contract is untouched."""
    detail = _aasa(monkeypatch)
    for c in ({"/": "/u/*"}, {"/": "/s/*"},
              {"/": "/", "?": {"ref": "?*"}},
              {"/": "/", "?": {"league": "?*"}}):
        assert c in detail["components"], c
    assert "/u/*" in detail["paths"] and "/s/*" in detail["paths"]


def test_t3_aasa_never_claims_bare_root_or_the_whole_app_tree(monkeypatch):
    """The over-broad claim this design refuses. The mobile route table owns a
    dozen /app/… screens the SERVER does not serve; claiming /app/* would turn
    an honest Safari 404 into an app-open with no destination."""
    detail = _aasa(monkeypatch)
    assert {"/": "/"} not in detail["components"]
    assert {"/": "/*"} not in detail["components"]
    assert {"/": "/app/*"} not in detail["components"]
    assert "/" not in detail["paths"]
    assert "/*" not in detail["paths"]
    assert "/app/*" not in detail["paths"]


# ═══════════════════════════════════════════════════════════════════════════
# S2 — the 302 web fallback
# ═══════════════════════════════════════════════════════════════════════════

def test_t4_join_redirect_with_ref():
    r = _client().get("/app/league/join/123?ref=matt")
    assert r.status_code == 302
    assert r.headers["Location"] == "/?league=123&ref=matt"


def test_t5_join_redirect_without_ref():
    r = _client().get("/app/league/join/123")
    assert r.status_code == 302
    assert r.headers["Location"] == "/?league=123"


def test_t6_join_redirect_encodes_hostile_ids():
    """urlencode is the encoder, not string concatenation — which is what makes
    a hostile id ENCODE rather than reflect. The Location is always built from a
    hard-coded "/?" plus a dict we constructed, so it is always relative and
    there is no open-redirect surface.

    Two layers, both asserted. (a) A %2F-bearing traversal id never reaches the
    handler at all: Werkzeug's default `string` converter refuses slashes, so
    the URL is unroutable — a 404, which is STRONGER than "encoded". (b) Every
    hostile id that IS routable comes back percent-encoded.
    """
    c = _client()
    # (a) unroutable — including the two shapes an open redirect would need.
    for hostile in ("..%2F..%2Fetc%2Fpasswd?ref=a b%26c",
                    "https:%2F%2Fevil.com",
                    "%2F%2Fevil.com"):
        assert c.get(f"/app/league/join/{hostile}").status_code == 404, hostile

    # (b) routable hostile input, encoded on the way out.
    r = c.get("/app/league/join/..%252F..%252Fetc%252Fpasswd?ref=a%20b%26c")
    assert r.status_code == 302
    loc = r.headers["Location"]
    assert loc.startswith("/?")
    assert "://" not in loc
    assert "/etc/passwd" not in loc
    assert "%252F" in loc
    assert " " not in loc
    # `&` inside the ref VALUE must not become a parameter separator.
    assert loc == "/?league=..%252F..%252Fetc%252Fpasswd&ref=a+b%26c"

    # A script-ish id and a CRLF-bearing ref are both neutralised.
    loc = c.get("/app/league/join/%3Cscript%3E?ref=%22%3E%3Cimg").headers["Location"]
    assert "<" not in loc and ">" not in loc and '"' not in loc
    loc = c.get("/app/league/join/123?ref=%0d%0aSet-Cookie:%20x").headers["Location"]
    assert "\r" not in loc and "\n" not in loc


def test_t7_join_redirect_drops_unknown_params():
    r = _client().get("/app/league/join/123?ref=matt&utm_source=x")
    loc = r.headers["Location"]
    assert "utm_source" not in loc
    assert loc == "/?league=123&ref=matt"


# ═══════════════════════════════════════════════════════════════════════════
# S3 — GET /api/league/invite-meta
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def meta_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)
    return engine


def test_t8_invite_meta_resolves_sleeper_name(meta_db):
    """No session header is sent — the route is deliberately unauthenticated."""
    with patch.object(server, "_fetch_sleeper_league_meta",
                      lambda lid: {"name": "Lakeview Dynasty"}):
        body = _client().get(
            "/api/league/invite-meta?league_id=990000000000000001").get_json()
    assert body == {"league_id": "990000000000000001",
                    "league_name": "Lakeview Dynasty",
                    "platform": "sleeper"}


def test_t9_invite_meta_degrades_on_failure(meta_db):
    """Degrades, never fails: the banner falls back to 'their league'."""
    def _boom(_lid):
        raise RuntimeError("sleeper is down")
    with patch.object(server, "_fetch_sleeper_league_meta", _boom):
        r = _client().get("/api/league/invite-meta?league_id=123")
    assert r.status_code == 200
    body = r.get_json()
    assert body["league_name"] is None
    assert body["platform"] is None


def test_t10_invite_meta_never_leaks_a_name_from_our_db(meta_db):
    """THE PRIVACY TEST. An imported ESPN league's name lives only in OUR
    table, and this endpoint is unauthenticated — serving it would make every
    imported league name enumerable by id. `_fetch_sleeper_league_meta`'s
    is_linked_platform_league guard is what enforces that; the invariant here
    is that the name never REACHES the response."""
    secret = "Matt's Private ESPN Money League"
    with meta_db.begin() as conn:
        conn.execute(leagues_table.insert().values(
            sleeper_league_id="424242", user_id="u_x", name=secret,
            season="2026", total_rosters=12, platform="espn"))

    r = _client().get("/api/league/invite-meta?league_id=424242")
    assert r.status_code == 200
    assert secret not in r.get_data(as_text=True)
    assert r.get_json()["league_name"] is None
    assert r.get_json()["platform"] is None

    # …and a non-numeric id resolves to null the same way.
    body = _client().get("/api/league/invite-meta?league_id=not-an-id").get_json()
    assert body["league_name"] is None and body["platform"] is None


def test_t11_invite_meta_requires_league_id():
    r = _client().get("/api/league/invite-meta")
    assert r.status_code == 400
    assert r.get_json()["error"] == "missing_league_id"
    assert _client().get("/api/league/invite-meta?league_id=%20%20").status_code == 400


# ═══════════════════════════════════════════════════════════════════════════
# S4 — the flag
# ═══════════════════════════════════════════════════════════════════════════

def test_t12_invite_join_flag_registered_and_off():
    """EMITTER ONLY, default OFF. The AASA claim, the 302 and invite-meta are
    all unflagged — flipping this early is what would send invites to Safari."""
    assert "growth.invite_join_link" in feature_flags.FLAG_KEYS
    assert feature_flags.is_enabled("growth.invite_join_link") is False

    root = __import__("pathlib").Path(__file__).resolve().parents[2]
    with open(root / "config" / "features.json") as f:
        assert json.load(f)["growth.invite_join_link"] is False
    with open(root / "backend" / "tests" / "fixtures" / "flags"
              / "release.json") as f:
        # A Maestro flow declaring `# flags: release` resolves against this
        # file; an absent key would silently fall back to a default the flow
        # never declared.
        assert json.load(f)["growth.invite_join_link"] is False


# ═══════════════════════════════════════════════════════════════════════════
# T-13 — the silent-drop regression guard
# ═══════════════════════════════════════════════════════════════════════════

def test_t13_invite_event_names_are_registered(tmp_path):
    """Depends on commit 1 (taxonomy registration). If the four invite names
    are not in the allowlist, /api/events accepts-and-DROPS them and the loop
    ships blind — the exact failure class this batch exists to stop. A red here
    is the intent, not a flake."""
    import backend.analytics_ingest as ingest

    engine = create_engine(f"sqlite:///{tmp_path / 'invite.db'}",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    names = ["invite_shared", "invite_link_opened",
             "invite_league_pinned", "invite_pin_failed"]
    payload = {"events": [
        # event_id/session_id must be 8+ chars (P1 envelope rules).
        {"event_id": f"invite-evt-{i:02d}", "event_type": n,
         "session_id": "sess-invite-1", "seq": i + 1}
        for i, n in enumerate(names)
    ]}

    with patch.object(db_module, "engine", engine), \
         patch.object(db_module, "ingest_engine", engine), \
         patch.object(ingest, "is_enabled", lambda k: k == "analytics.ingest"):
        with ingest._rate_lock:
            ingest._events_rate.clear()
        r = _client().post("/api/events",
                           headers={"Content-Type": "application/json",
                                    "X-Device-Id": "dev_invite"},
                           data=json.dumps(payload))

    assert r.status_code == 200
    body = r.get_json()
    assert body["dropped"] == 0, body
    assert body["accepted"] == len(names), body
    assert body["rejected"] == [] or len(body["rejected"]) == 0, body
