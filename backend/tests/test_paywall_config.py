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
  (f) tips — not served at launch (`tips: []`; the SKUs are not submitted
      to App Store Connect); the restorable list holds only tip products
  (g) the Founding GMs club (#393 scope §2 item 3, recommendation §(b)):
      `club` open before closes_at and closed from it on, with the clock
      frozen on both sides; founder vs standard `display_price`;
      `trial_period` "1 month" and no `trial_days`; the truthful grid;
      `dismissible` always true
  (h) fallback prices (#393, operator 2026-10-25; #494, #522): $4.99 /
      $24.99 before _PAYWALL_PRICE_RISE_AT (2027-01-02 04:00 UTC, App Store
      Connect's US start for a change scheduled for 2027-01-02: an instant,
      not a date), $6.99 / $34.99 from it on; a naive now raises;
      _paywall_products is pure; no `trial_days` key on either side (an
      older client renders "N days free" only when trial_days > 0);
      per_month_equiv rounded up
  (i) one instant (head-eng 2026-10-27): `club.closes_at` is the rise
      instant, `club.open` and the prices flip at the same instant from one
      clock read, and moving the constant moves both

Flask client + injected session, flags forced via a patched
server.is_enabled — the two harness patterns from backend/tests/CLAUDE.md.
The clock is frozen by patching server._paywall_now, the one clock the
route reads. No DB rows are needed: the route is static config and
touches no table.
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
# The rise is 2027-01-02 04:00 UTC (11 pm ET / 8 pm PT on Jan 1): App Store
# Connect's US start time for a price change scheduled for 2027-01-02.
CLOSES_AT = "2027-01-02T04:00:00Z"   # club.closes_at as served: the rise instant
BEFORE = datetime(2027, 1, 2, 3, 59, 59, tzinfo=UTC)      # last second of old prices
AT = datetime(2027, 1, 2, 4, 0, 0, tzinfo=UTC)            # the rise itself
UTC_MIDNIGHT = datetime(2027, 1, 1, 0, 0, 0, tzinfo=UTC)  # still Dec 31 in the US
ASC_JAN_1 = datetime(2027, 1, 1, 4, 0, 0, tzinfo=UTC)     # a Jan-1 schedule's US start (11 pm ET Dec 31)
LA_MIDNIGHT = datetime(2027, 1, 1, 8, 0, 0, tzinfo=UTC)   # the previous instant
AFTER = datetime(2027, 6, 1, 12, 0, 0, tzinfo=UTC)
TODAY = datetime(2026, 10, 27, 12, 0, 0, tzinfo=UTC)
TICK = timedelta(microseconds=1)
FOUNDER_PRICES = {MONTHLY: "$4.99", ANNUAL: "$24.99"}
STANDARD_PRICES = {MONTHLY: "$6.99", ANNUAL: "$34.99"}
# The undelivered kinds (5c) and the keys that name no gated feature.
DROPPED_FEATURES = ("engine_knobs", "extension_overlays", "ad_free",
                    "unlimited_leagues", "portfolio")


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
    assert body["pages"][1]["features"] == []
    assert body["club"]["name"] == "Founding GMs"
    assert body["tips"] == []


def test_products_shape(client, monkeypatch):
    _flags(monkeypatch, "monetize.paywall")
    _freeze(monkeypatch, TODAY)
    products = _products(client)
    assert list(products) == [MONTHLY, ANNUAL]

    assert products[MONTHLY]["period"] == "monthly"
    assert products[MONTHLY]["display_price"] == "$4.99"
    assert products[MONTHLY]["trial_period"] == "1 month"
    assert products[MONTHLY]["hero"] is False
    assert set(products[MONTHLY]) == {
        "product_id", "period", "display_price", "trial_period", "hero"}

    assert products[ANNUAL]["period"] == "annual"
    assert products[ANNUAL]["display_price"] == "$24.99"
    assert products[ANNUAL]["per_month_equiv"] == "$2.09"
    assert products[ANNUAL]["trial_period"] == "1 month"
    assert products[ANNUAL]["hero"] is True
    assert products[ANNUAL]["badge"] == "best_value"
    assert set(products[ANNUAL]) == {
        "product_id", "period", "display_price", "per_month_equiv",
        "trial_period", "hero", "badge"}
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
                  "matches_preview", "`trial_period`", "`club`",
                  "`closes_at`", "Founding GMs"):
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
    """#393: the tip SKUs are not submitted to App Store Connect, so the
    config serves `tips: []`, in or after the club window, and no tip id or
    price leaks."""
    _flags(monkeypatch, "monetize.paywall")
    _freeze(monkeypatch, now)
    r = _get(client)
    assert r.get_json()["tips"] == []
    assert "ftf_tip" not in r.get_data(as_text=True)


def test_restorable_tip_skus_are_tip_products():
    """`_PAYWALL_TIPS` is the list to restore if tips come back (only by a
    reviewed change). Every SKU in it must hit the projector's
    no-entitlement guard — a tip id drifting out of the ftf_tip_ prefix
    would grant Pro — and none claims entitlement fields: a tip buys
    nothing."""
    from backend import entitlements as entl
    assert [t["product_id"] for t in server._PAYWALL_TIPS] == [
        "ftf_tip_199", "ftf_tip_499", "ftf_tip_999"]
    for t in server._PAYWALL_TIPS:
        assert entl.is_tip_product(t["product_id"])
        assert not {"trial_days", "trial_period", "period"} & set(t)


def test_flag_off_leaks_no_tips(client, monkeypatch):
    _flags(monkeypatch)
    assert "ftf_tip" not in _get(client).get_data(as_text=True)


# ── (g) the Founding GMs club ──────────────────────────────────────────────

@pytest.mark.parametrize("now, is_open", [
    (TODAY, True),
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
    (BEFORE, "$4.99", "$24.99", "$2.09"),     # founder prices while open
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


@pytest.mark.parametrize("now, expected", [(BEFORE, "$2.09"), (AFTER, "$2.92")])
def test_per_month_equiv_rounds_up_to_the_cent(client, monkeypatch, now, expected):
    """Legal's approved copy says $2.09/month: the annual price / 12, rounded
    UP (24.99 / 12 = 2.0825 → $2.09; 34.99 / 12 = 2.9158 → $2.92)."""
    _flags(monkeypatch, "monetize.paywall")
    _freeze(monkeypatch, now)
    annual = [p for p in _get(client).get_json()["products"]
              if p["product_id"] == ANNUAL][0]
    ceil = (Decimal(annual["display_price"].lstrip("$")) / 12).quantize(
        Decimal("0.01"), rounding=ROUND_CEILING)
    assert annual["per_month_equiv"] == expected == f"${ceil}"


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
    """5c: the grid is empty at launch (1.21.x renders it only when the list
    is non-empty), and no dropped or false key appears anywhere."""
    _flags(monkeypatch, "monetize.paywall")
    _freeze(monkeypatch, now)
    r = _get(client)
    grid = [p for p in r.get_json()["pages"] if p["kind"] == "features"]
    assert len(grid) == 1 and grid[0]["id"] == "feature_grid"
    assert grid[0]["features"] == []
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


# ── (h) fallback prices: the rise instant, no trial_days ─────────────────

@pytest.mark.parametrize("now, monthly, annual, per_month", [
    (TODAY, "$4.99", "$24.99", "$2.09"),
    (UTC_MIDNIGHT, "$4.99", "$24.99", "$2.09"),  # 4 pm Dec 31 in LA: old prices
    (ASC_JAN_1, "$4.99", "$24.99", "$2.09"),  # 11 pm ET Dec 31: still the Founder price
    (LA_MIDNIGHT, "$4.99", "$24.99", "$2.09"),  # the old 01-01 08:00Z instant: no longer the switch
    (BEFORE, "$4.99", "$24.99", "$2.09"),     # 01-02 03:59:59Z, last second before the rise
    (AT, "$6.99", "$34.99", "$2.92"),         # 01-02 04:00:00Z, the rise itself: new prices
    (AFTER, "$6.99", "$34.99", "$2.92"),
])
def test_route_prices_switch_at_rise_instant(client, monkeypatch, now, monthly,
                                             annual, per_month):
    _flags(monkeypatch, "monetize.paywall")
    _freeze(monkeypatch, now)
    products = _products(client)
    assert products[MONTHLY]["display_price"] == monthly
    assert products[ANNUAL]["display_price"] == annual
    assert products[ANNUAL]["per_month_equiv"] == per_month
    assert "per_month_equiv" not in products[MONTHLY]


@pytest.mark.parametrize("now", [TODAY, UTC_MIDNIGHT, ASC_JAN_1, LA_MIDNIGHT, BEFORE, AT, AFTER])
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


def test_rise_is_app_store_us_start_for_2027_01_02():
    """The rise matches App Store Connect's US start time for a price change
    scheduled for 2027-01-02: 04:00 UTC, i.e. 11 pm on Jan 1 in New York
    and 8 pm in Los Angeles, held as an aware UTC instant. Terms §14.8 (the
    Founder price "by December 31, 2026") then holds everywhere in the US."""
    rise = server._PAYWALL_PRICE_RISE_AT
    assert rise == datetime(2027, 1, 2, 4, 0, 0, tzinfo=UTC)
    assert rise.utcoffset() == timedelta(0)
    try:
        from zoneinfo import ZoneInfo
        ny = ZoneInfo("America/New_York")
        la = ZoneInfo("America/Los_Angeles")
        hnl = ZoneInfo("Pacific/Honolulu")
    except Exception:   # no tz database on this host; the UTC pin stands
        return
    assert rise == datetime(2027, 1, 1, 23, 0, 0, tzinfo=ny)
    assert rise == datetime(2027, 1, 1, 20, 0, 0, tzinfo=la)
    # The last second of Dec 31 in Hawaii, the latest US zone, is before it.
    assert datetime(2026, 12, 31, 23, 59, 59, tzinfo=hnl) < rise


ET = timezone(timedelta(hours=-5))
PT = timezone(timedelta(hours=-8))


@pytest.mark.parametrize("now, risen", [
    # 20:00 on Dec 31 in New York is 01:00 UTC on Jan 1, but still Dec 31
    # for the subscriber: old prices (a UTC date flipped here).
    (datetime(2026, 12, 31, 20, 0, tzinfo=ET), False),
    # 23:00 on Dec 31 in New York (a Jan-1 schedule's US start): old prices.
    (datetime(2026, 12, 31, 23, 0, 0, tzinfo=ET), False),
    # The last second of Dec 31 in LA, and midnight in LA: old prices.
    (datetime(2026, 12, 31, 23, 59, 59, tzinfo=PT), False),
    (datetime(2027, 1, 1, 0, 0, 0, tzinfo=PT), False),
    # 22:59:59 on Jan 1 in New York, one second before the rise: old prices.
    (datetime(2027, 1, 1, 22, 59, 59, tzinfo=ET), False),
    # 23:00 on Jan 1 in New York is the rise: new prices.
    (datetime(2027, 1, 1, 23, 0, 0, tzinfo=ET), True),
    # 20:00 on Jan 1 in LA is the same instant: new prices.
    (datetime(2027, 1, 1, 20, 0, 0, tzinfo=PT), True),
    # 00:30 on Jan 1 in Paris is 23:30 UTC on Dec 31: old prices.
    (datetime(2027, 1, 1, 0, 30, tzinfo=timezone(timedelta(hours=1))), False),
])
def test_switch_is_an_instant_not_a_date(now, risen):
    annual = {p["product_id"]: p for p in server._paywall_products(now)}[ANNUAL]
    assert annual["display_price"] == ("$34.99" if risen else "$24.99")


def test_naive_now_raises():
    """A naive datetime names no instant; comparing it must fail loudly
    rather than silently pick a timezone."""
    with pytest.raises(TypeError):
        server._paywall_products(datetime(2027, 1, 1, 12, 0))


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


# ── (i) one instant: the club closes at the price rise ─────────────────────

def test_closes_at_is_the_rise_instant(client, monkeypatch):
    """`club.closes_at` is _PAYWALL_PRICE_RISE_AT (App Store Connect's US
    start for the Jan-2 change, 04:00 UTC), served as an ISO-8601 UTC string
    with a Z suffix (the shape is unchanged)."""
    _flags(monkeypatch, "monetize.paywall")
    _freeze(monkeypatch, TODAY)
    closes_at = _get(client).get_json()["club"]["closes_at"]
    assert closes_at == CLOSES_AT == server._paywall_club_closes_at()
    assert datetime.fromisoformat(closes_at) == server._PAYWALL_PRICE_RISE_AT == AT


@pytest.mark.parametrize("now", [TODAY, UTC_MIDNIGHT, BEFORE, AT - TICK, AT,
                                 AT + TICK, AFTER])
def test_club_open_flips_with_the_prices(client, monkeypatch, now):
    """`club.open` and the price window flip at exactly the same instant:
    open ⇔ founder prices, closed ⇔ standard prices, down to the
    microsecond either side of the rise."""
    _flags(monkeypatch, "monetize.paywall")
    _freeze(monkeypatch, now)
    body = _get(client).get_json()
    prices = {p["product_id"]: p["display_price"] for p in body["products"]}
    assert body["club"]["open"] is (now < AT)
    assert prices == (FOUNDER_PRICES if body["club"]["open"] else STANDARD_PRICES)


def test_one_clock_read_per_request(client, monkeypatch):
    """The route reads _paywall_now() once. A second read here would land
    past the rise, splitting `club.open` from the prices."""
    _flags(monkeypatch, "monetize.paywall")
    reads = iter([AT - TICK, AT])
    calls = []

    def clock():
        calls.append(1)
        return next(reads)

    monkeypatch.setattr(server, "_paywall_now", clock)
    body = _get(client).get_json()
    assert len(calls) == 1
    assert body["club"]["open"] is True
    assert {p["product_id"]: p["display_price"]
            for p in body["products"]} == FOUNDER_PRICES


def test_moving_the_rise_moves_the_club_and_the_prices(client, monkeypatch):
    """Nothing holds a second copy of the date: move the one constant and
    `club.closes_at`, `club.open` and the prices all move with it (founder
    on /api/me/entitlements is pinned the same way in
    test_me_entitlements.py)."""
    rise = server._PAYWALL_PRICE_RISE_AT
    moved = rise - timedelta(days=32)          # a month earlier, same time of day
    _flags(monkeypatch, "monetize.paywall")
    _freeze(monkeypatch, rise - timedelta(days=18))   # between the two
    assert _get(client).get_json()["club"]["open"] is True
    monkeypatch.setattr(server, "_PAYWALL_PRICE_RISE_AT", moved)
    body = _get(client).get_json()
    assert body["club"]["closes_at"] == moved.isoformat().replace("+00:00", "Z")
    assert body["club"]["open"] is False
    assert {p["product_id"]: p["display_price"]
            for p in body["products"]} == STANDARD_PRICES
