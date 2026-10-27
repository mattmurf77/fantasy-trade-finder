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
  (f) tip jar
  (g) fallback prices (#393, operator 2026-10-25): $4.99 / $24.99 before
      _PAYWALL_PRICE_RISE_DATE (2027-01-01 UTC), $6.99 / $34.99 from it on,
      through an injected clock; no `trial_days` key on either side (an
      older client renders "N days free" only when trial_days > 0)

Flask client + injected session, flags forced via a patched
server.is_enabled — the two harness patterns from backend/tests/CLAUDE.md.
No DB rows are needed: the route is static config and touches no table.
"""

import pathlib
from datetime import datetime, timedelta, timezone
from decimal import ROUND_CEILING, Decimal

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

UTC = timezone.utc
BEFORE = datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)   # last second of old prices
AT = datetime(2027, 1, 1, 0, 0, 0, tzinfo=UTC)            # the rise itself
AFTER = datetime(2027, 6, 1, 12, 0, 0, tzinfo=UTC)
TODAY = datetime(2026, 10, 27, 12, 0, 0, tzinfo=UTC)


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


def _freeze(monkeypatch, now):
    monkeypatch.setattr(server, "_paywall_now", lambda: now)


def _products(client):
    return {p["product_id"]: p for p in _get(client).get_json()["products"]}


def _get(client, query=""):
    return client.get(f"/api/paywall/config{query}",
                      headers={"X-Session-Token": TOKEN})


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
    assert body["pages"][1]["features"] == [
        "unlimited_leagues", "portfolio", "engine_knobs",
        "extension_overlays", "ad_free"]


def test_products_shape(client, monkeypatch):
    _flags(monkeypatch, "monetize.paywall")
    _freeze(monkeypatch, TODAY)
    products = _products(client)
    assert list(products) == [MONTHLY, ANNUAL]

    assert products[MONTHLY]["period"] == "monthly"
    assert products[MONTHLY]["display_price"] == "$4.99"
    assert products[MONTHLY]["hero"] is False
    assert set(products[MONTHLY]) == {
        "product_id", "period", "display_price", "hero"}

    assert products[ANNUAL]["period"] == "annual"
    assert products[ANNUAL]["display_price"] == "$24.99"
    assert products[ANNUAL]["per_month_equiv"] == "$2.09"
    assert products[ANNUAL]["hero"] is True
    assert products[ANNUAL]["badge"] == "best_value"
    assert set(products[ANNUAL]) == {
        "product_id", "period", "display_price", "per_month_equiv", "hero",
        "badge"}
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
                  "unlimited_leagues", "engine_knobs", "matches_preview"):
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

def test_tips_served_when_on(client, monkeypatch):
    _flags(monkeypatch, "monetize.paywall")
    tips = _get(client).get_json()["tips"]
    assert [t["product_id"] for t in tips] == [
        "ftf_tip_199", "ftf_tip_499", "ftf_tip_999"]
    assert all(t["display_price"].startswith("$") for t in tips)
    # tips never claim entitlement fields — they buy nothing
    assert all("trial_days" not in t and "period" not in t for t in tips)


def test_tip_skus_are_tip_products(client, monkeypatch):
    """Every served tip SKU must hit the projector's no-entitlement guard —
    a tip id drifting out of the ftf_tip_ prefix would grant Pro."""
    from backend import entitlements as entl
    _flags(monkeypatch, "monetize.paywall")
    for t in _get(client).get_json()["tips"]:
        assert entl.is_tip_product(t["product_id"])


def test_flag_off_leaks_no_tips(client, monkeypatch):
    _flags(monkeypatch)
    assert "ftf_tip" not in _get(client).get_data(as_text=True)


# ── (g) fallback prices: dated switch, no trial_days ─────────────────────

@pytest.mark.parametrize("now, monthly, annual, per_month", [
    (TODAY, "$4.99", "$24.99", "$2.09"),
    (BEFORE, "$4.99", "$24.99", "$2.09"),     # last second before the rise
    (AT, "$6.99", "$34.99", "$2.92"),         # the rise date itself: new prices
    (AFTER, "$6.99", "$34.99", "$2.92"),
])
def test_route_prices_switch_on_rise_date(client, monkeypatch, now, monthly,
                                          annual, per_month):
    _flags(monkeypatch, "monetize.paywall")
    _freeze(monkeypatch, now)
    products = _products(client)
    assert products[MONTHLY]["display_price"] == monthly
    assert products[ANNUAL]["display_price"] == annual
    assert products[ANNUAL]["per_month_equiv"] == per_month
    assert "per_month_equiv" not in products[MONTHLY]


@pytest.mark.parametrize("now", [TODAY, BEFORE, AT, AFTER])
def test_no_trial_days_anywhere(client, monkeypatch, now):
    """An older client renders `${trial_days} days free, then …` whenever
    trial_days > 0. The trial is Apple's 1-month intro offer, never a day
    count, so the key must be absent from the whole response on both sides
    of the rise."""
    _flags(monkeypatch, "monetize.paywall")
    _freeze(monkeypatch, now)
    r = _get(client)
    assert "trial_days" not in r.get_data(as_text=True)
    for p in r.get_json()["products"]:
        assert "trial_days" not in p


def test_rise_date_is_2027_01_01_utc():
    assert server._PAYWALL_PRICE_RISE_DATE.isoformat() == "2027-01-01"


@pytest.mark.parametrize("now, risen", [
    # 20:00 on Dec 31 in New York is 01:00 UTC on Jan 1: new prices.
    (datetime(2026, 12, 31, 20, 0, tzinfo=timezone(timedelta(hours=-5))), True),
    # 00:30 on Jan 1 in Paris is 23:30 UTC on Dec 31: old prices.
    (datetime(2027, 1, 1, 0, 30, tzinfo=timezone(timedelta(hours=1))), False),
])
def test_switch_is_judged_in_utc(now, risen):
    annual = {p["product_id"]: p for p in server._paywall_products(now)}[ANNUAL]
    assert annual["display_price"] == ("$34.99" if risen else "$24.99")


def test_paywall_products_is_pure():
    """Same `now`, same answer, and the module-level tables are untouched
    (the route must not mutate shared config per request)."""
    before_tables = repr((server._PAYWALL_PRODUCTS, server._PAYWALL_PRICES))
    assert server._paywall_products(BEFORE) == server._paywall_products(BEFORE)
    assert server._paywall_products(AFTER) == server._paywall_products(AFTER)
    assert server._paywall_products(BEFORE) != server._paywall_products(AFTER)
    assert repr((server._PAYWALL_PRODUCTS, server._PAYWALL_PRICES)) == before_tables
    assert all("display_price" not in p for p in server._PAYWALL_PRODUCTS)


@pytest.mark.parametrize("now", [BEFORE, AFTER])
def test_per_month_equiv_is_annual_over_12_rounded_up(now):
    """Rounded UP to the cent: 24.99 / 12 = 2.0825 → $2.09 (legal's #393
    R28.8 #2 copy); 34.99 / 12 = 2.9158 → $2.92. Rounding down would
    understate what a year costs."""
    annual = {p["product_id"]: p for p in server._paywall_products(now)}[ANNUAL]
    ceil = (Decimal(annual["display_price"].lstrip("$")) / 12).quantize(
        Decimal("0.01"), rounding=ROUND_CEILING)
    assert annual["per_month_equiv"] == f"${ceil}"


def test_route_reads_the_real_clock_by_default():
    """Unfrozen, the clock is the real UTC now (aware), so the switch fires
    on the day without a deploy."""
    now = server._paywall_now()
    assert now.tzinfo is not None
    assert abs((now - datetime.now(timezone.utc)).total_seconds()) < 5
