"""GET /api/paywall/config — server-driven paywall presentation
(docs/plans/monetization/pro-subscription/lld.md §3; build scope
docs/plans/monetization/iap-enablement/scope.md).

Covers:
  (a) flag gate — `monetize.paywall` off → {"enabled": false} and nothing
      else, so a client shipped ahead of the flag renders no purchase UI
  (b) full shape when on — pages in order, page kinds, product fields
  (c) SKU ids are exactly ftf_pro_monthly / ftf_pro_annual, asserted
      against docs/cross-client-invariants.md (the two must never drift —
      the ids have to match the RevenueCat offering the client purchases)
  (d) session auth — no token → 401 (same layer as /api/me/entitlements)
  (e) ?platform=ios|web|extension accepted; unknown value degrades to ios
  (f) tips — not served at launch (`tips: []`); the kept list stays tip SKUs
  (g) the Founding GMs club (#393 scope §2 item 3, recommendation §(b)):
      `club` open before closes_at and closed from it on, with the clock
      frozen on both sides; founder vs standard `display_price`;
      `trial_period` "1 month" and no `trial_days`; the truthful grid;
      `dismissible` always true

Flask client + injected session, flags forced via a patched
server.is_enabled — the two harness patterns from backend/tests/CLAUDE.md.
The clock is frozen by patching server.datetime (as in
test_trade_disposition_replay.py). No DB rows are needed: the route is
static config and touches no table.
"""

import pathlib
from datetime import datetime

import pytest

import backend.server as server

TOKEN = "paywall-test-token"
USER = "paywall_user_1"
REPO = pathlib.Path(__file__).resolve().parents[2]

# The SKU ids this route is allowed to serve. Mirrored in
# docs/cross-client-invariants.md § Monetization SKU ids and asserted
# against that file below.
MONTHLY = "ftf_pro_monthly"
ANNUAL = "ftf_pro_annual"

CLOSES_AT = "2027-01-01T00:00:00Z"
BEFORE = "2026-12-31T23:59:59+00:00"    # the club's last second
AT = "2027-01-01T00:00:00+00:00"        # closes_at itself: closed
AFTER = "2027-06-01T12:00:00+00:00"
DROPPED_FEATURES = ("engine_knobs", "extension_overlays", "ad_free")


@pytest.fixture()
def client():
    server.app.config["TESTING"] = True
    c = server.app.test_client()
    with server._sessions_lock:
        server._sessions[TOKEN] = {"user_id": USER, "last_active": 0.0}
    try:
        yield c
    finally:
        with server._sessions_lock:
            server._sessions.pop(TOKEN, None)


def _flags(monkeypatch, *on):
    monkeypatch.setattr(server, "is_enabled", lambda k: k in on)


def _get(client, query=""):
    return client.get(f"/api/paywall/config{query}",
                      headers={"X-Session-Token": TOKEN})


def _freeze(monkeypatch, iso):
    """server.datetime.now() returns `iso` (aware, UTC) for this test."""
    fixed = datetime.fromisoformat(iso)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)

    monkeypatch.setattr(server, "datetime", Clock)


# ── (a) flag gate ──────────────────────────────────────────────────────────

def test_flag_off_returns_enabled_false_only(client, monkeypatch):
    _flags(monkeypatch)
    r = _get(client)
    assert r.status_code == 200
    assert r.get_json() == {"enabled": False}


def test_flag_off_leaks_no_products(client, monkeypatch):
    """A dark paywall must not ship prices or SKUs to the client."""
    _flags(monkeypatch)
    payload = _get(client).get_data(as_text=True)
    assert MONTHLY not in payload and ANNUAL not in payload
    assert "$" not in payload


# ── (b) full shape ─────────────────────────────────────────────────────────

def test_flag_on_returns_full_shape(client, monkeypatch):
    _flags(monkeypatch, "monetize.paywall")
    body = _get(client).get_json()

    assert body["enabled"] is True
    assert body["dismissible"] is True
    assert body["trial_eligible"] is True

    assert [p["id"] for p in body["pages"]] == [
        "value_recap", "feature_grid", "plans"]
    assert [p["kind"] for p in body["pages"]] == [
        "trades_found", "features", "purchase"]
    # page 1 tells the client to reuse matches it already has — the route
    # never recomputes trades (LLD §3).
    assert body["pages"][0]["body_ref"] == "matches_preview"
    assert body["pages"][1]["features"] == ["unlimited_leagues", "portfolio"]
    assert body["club"]["name"] == "Founding GMs"
    assert body["tips"] == []


def test_products_shape(client, monkeypatch):
    _flags(monkeypatch, "monetize.paywall")
    _freeze(monkeypatch, BEFORE)
    products = {p["product_id"]: p for p in _get(client).get_json()["products"]}
    assert list(products) == [MONTHLY, ANNUAL]

    assert products[MONTHLY]["period"] == "monthly"
    assert products[MONTHLY]["display_price"] == "$4.99"
    assert products[MONTHLY]["trial_period"] == "1 month"
    assert products[MONTHLY]["hero"] is False
    assert "per_month_equiv" not in products[MONTHLY]

    assert products[ANNUAL]["period"] == "annual"
    assert products[ANNUAL]["display_price"] == "$24.99"
    assert products[ANNUAL]["per_month_equiv"] == "$2.08"
    assert products[ANNUAL]["trial_period"] == "1 month"
    assert products[ANNUAL]["hero"] is True
    assert products[ANNUAL]["badge"] == "best_value"
    # exactly one hero — two would give the client no default selection
    assert sum(1 for p in products.values() if p["hero"]) == 1


# ── (c) SKU ids vs the cross-client contract ───────────────────────────────

def test_sku_ids_match_cross_client_invariants(client, monkeypatch):
    doc = (REPO / "docs" / "cross-client-invariants.md").read_text()
    _flags(monkeypatch, "monetize.paywall")
    served = [p["product_id"] for p in _get(client).get_json()["products"]]
    assert served == [MONTHLY, ANNUAL]
    for sku in served:
        assert f"`{sku}`" in doc, f"{sku} missing from cross-client-invariants"


def test_paywall_enums_documented():
    """`kind`, `badge` and the feature keys are a client contract."""
    doc = (REPO / "docs" / "cross-client-invariants.md").read_text()
    for token in ("trades_found", "features", "purchase", "best_value",
                  "unlimited_leagues", "portfolio", "matches_preview",
                  "`trial_period`", "`club`", "`closes_at`", "Founding GMs"):
        assert token in doc, f"paywall enum {token!r} undocumented"


# ── (d) auth ───────────────────────────────────────────────────────────────

def test_unauthenticated_401(client, monkeypatch):
    _flags(monkeypatch, "monetize.paywall")
    assert client.get("/api/paywall/config").status_code == 401
    assert client.get("/api/paywall/config",
                      headers={"X-Session-Token": "bogus"}).status_code == 401


def test_unauthenticated_401_even_while_dark(client, monkeypatch):
    """Auth is checked before the flag — a dark route must not become an
    open one."""
    _flags(monkeypatch)
    assert client.get("/api/paywall/config").status_code == 401


# ── (e) platform param ─────────────────────────────────────────────────────

@pytest.mark.parametrize("platform", ["ios", "web", "extension"])
def test_platform_param_accepted(client, monkeypatch, platform):
    _flags(monkeypatch, "monetize.paywall")
    body = _get(client, f"?platform={platform}").get_json()
    assert body["platform"] == platform
    assert len(body["products"]) == 2   # no per-platform variation yet


def test_unknown_platform_degrades_to_ios(client, monkeypatch):
    _flags(monkeypatch, "monetize.paywall")
    assert _get(client, "?platform=nintendo").get_json()["platform"] == "ios"
    assert _get(client).get_json()["platform"] == "ios"


# ── (f) tip jar ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("now", [BEFORE, AFTER])
def test_tips_empty_at_launch(client, monkeypatch, now):
    """#393: tips are not served at launch, in or after the club window."""
    _flags(monkeypatch, "monetize.paywall")
    _freeze(monkeypatch, now)
    r = _get(client)
    assert r.get_json()["tips"] == []
    assert "ftf_tip" not in r.get_data(as_text=True)


def test_kept_tip_skus_are_tip_products():
    """The kept tip list (served again only by a reviewed change) must hit
    the projector's no-entitlement guard — a tip id drifting out of the
    ftf_tip_ prefix would grant Pro."""
    from backend import entitlements as entl
    assert [t["product_id"] for t in server._PAYWALL_TIPS] == [
        "ftf_tip_199", "ftf_tip_499", "ftf_tip_999"]
    for t in server._PAYWALL_TIPS:
        assert entl.is_tip_product(t["product_id"])
        # tips never claim entitlement fields — they buy nothing
        assert "trial_period" not in t and "period" not in t


def test_flag_off_leaks_no_tips(client, monkeypatch):
    _flags(monkeypatch)
    assert "ftf_tip" not in _get(client).get_data(as_text=True)


# ── (g) the Founding GMs club ──────────────────────────────────────────────

def test_closes_at_is_the_one_constant():
    """2027-01-01, the App Store Connect scheduled price change. One server
    constant: a change here is a reviewed deploy, never a knob."""
    assert server._PAYWALL_CLUB_CLOSES_AT == CLOSES_AT


@pytest.mark.parametrize("now, is_open", [
    ("2026-10-27T09:00:00+00:00", True),
    (BEFORE, True),
    (AT, False),
    (AFTER, False),
])
def test_club_open_around_closes_at(client, monkeypatch, now, is_open):
    _flags(monkeypatch, "monetize.paywall")
    _freeze(monkeypatch, now)
    assert _get(client).get_json()["club"] == {
        "name": "Founding GMs", "closes_at": CLOSES_AT, "open": is_open}


@pytest.mark.parametrize("now, monthly, annual, per_month", [
    (BEFORE, "$4.99", "$24.99", "$2.08"),     # founder prices while open
    (AT, "$6.99", "$34.99", "$2.92"),         # standard from closes_at on
    (AFTER, "$6.99", "$34.99", "$2.92"),
])
def test_display_price_founder_then_standard(client, monkeypatch, now, monthly,
                                             annual, per_month):
    _flags(monkeypatch, "monetize.paywall")
    _freeze(monkeypatch, now)
    products = {p["product_id"]: p for p in _get(client).get_json()["products"]}
    assert products[MONTHLY]["display_price"] == monthly
    assert products[ANNUAL]["display_price"] == annual
    assert products[ANNUAL]["per_month_equiv"] == per_month


def test_annual_founder_price_is_24_99(client, monkeypatch):
    """D14 (2): the annual fallback said $34.99 while the club is open."""
    _flags(monkeypatch, "monetize.paywall")
    _freeze(monkeypatch, BEFORE)
    annual = [p for p in _get(client).get_json()["products"]
              if p["product_id"] == ANNUAL]
    assert annual[0]["display_price"] == "$24.99"


@pytest.mark.parametrize("now", [BEFORE, AFTER])
def test_trial_period_one_month_and_no_trial_days(client, monkeypatch, now):
    """`trial_days` is gone: a 1.21.x client shows "N days free" only when
    trial_days > 0, so absent means no wrong trial line."""
    _flags(monkeypatch, "monetize.paywall")
    _freeze(monkeypatch, now)
    r = _get(client)
    for p in r.get_json()["products"]:
        assert p["trial_period"] == "1 month"
        assert "trial_days" not in p
    assert "trial_days" not in r.get_data(as_text=True)


@pytest.mark.parametrize("now", [BEFORE, AFTER])
def test_feature_grid_is_truthful(client, monkeypatch, now):
    """5c: the undelivered kinds are dropped from the grid and from the
    whole response."""
    _flags(monkeypatch, "monetize.paywall")
    _freeze(monkeypatch, now)
    r = _get(client)
    grid = [p for p in r.get_json()["pages"] if p["kind"] == "features"]
    assert grid[0]["features"] == ["unlimited_leagues", "portfolio"]
    for kind in DROPPED_FEATURES:
        assert kind not in r.get_data(as_text=True), kind


@pytest.mark.parametrize("now", [BEFORE, AT, AFTER])
def test_dismissible_always_true(client, monkeypatch, now):
    _flags(monkeypatch, "monetize.paywall")
    _freeze(monkeypatch, now)
    assert _get(client).get_json()["dismissible"] is True


def test_flag_off_leaks_no_club(client, monkeypatch):
    _flags(monkeypatch)
    _freeze(monkeypatch, BEFORE)
    payload = _get(client).get_data(as_text=True)
    assert "club" not in payload and "Founding" not in payload
