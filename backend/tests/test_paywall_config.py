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
  (f) tip jar (tip-jar plan §3 S1) — `tips` is the three ftf_tip_ SKUs
      only while model_config `paywall_tips_enabled` is exactly 1 AND the
      resolved platform is `ios` AND the session is verified and not demo
      (an unverified or demo session gets []); `[]` at the seeded default 0, on web and
      extension, and for any other knob value (2, NaN, garbage, a missing
      row, a failed read); read live per request; flag off still serves
      `{"enabled": false}` alone; the list holds only tip products
  (g) fallback prices (#393, operator 2026-10-25): $4.99 / $24.99 before
      _PAYWALL_PRICE_RISE_AT (2027-01-02 04:00 UTC, App Store Connect's
      US start for a change scheduled for 2027-01-02: an instant, not a
      date), $6.99 / $34.99 from it on,
      through an injected clock; no `trial_days` key on either side (an
      older client renders "N days free" only when trial_days > 0)

Flask client + injected session, flags forced via a patched
server.is_enabled — the two harness patterns from backend/tests/CLAUDE.md.
The route's one table read is the tip knob (model_config), so every test
runs against an isolated in-memory DB (autouse `mem_engine`); an empty
table falls back to the seed list, i.e. the knob's default 0.
"""

import pathlib
from datetime import datetime, timedelta, timezone
from decimal import ROUND_CEILING, Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, insert

import backend.database as db_module
import backend.server as server
from backend.database import metadata, model_config_table

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
BEFORE = datetime(2027, 1, 2, 3, 59, 59, tzinfo=UTC)      # last second of old prices
AT = datetime(2027, 1, 2, 4, 0, 0, tzinfo=UTC)            # the rise itself
UTC_MIDNIGHT = datetime(2027, 1, 1, 0, 0, 0, tzinfo=UTC)  # still Dec 31 in the US
ASC_JAN_1 = datetime(2027, 1, 1, 4, 0, 0, tzinfo=UTC)     # a Jan-1 schedule's US start (11 pm ET Dec 31)
LA_MIDNIGHT = datetime(2027, 1, 1, 8, 0, 0, tzinfo=UTC)   # the previous instant
AFTER = datetime(2027, 6, 1, 12, 0, 0, tzinfo=UTC)
TODAY = datetime(2026, 10, 27, 12, 0, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def mem_engine():
    """Hermetic model_config: the route reads the tip knob live, and must
    never read the local data/trade_finder.db."""
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db_module, "engine", eng):
        yield eng


@pytest.fixture()
def client():
    """A VERIFIED, non-demo session, so the tip tests isolate the knob and
    the platform; the session leg has its own tests in (f)."""
    server.app.config["TESTING"] = True
    c = server.app.test_client()
    with server._sessions_lock:
        server._sessions[TOKEN] = {"user_id": USER, "last_active": 0.0,
                                   "verified": True}
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

TIP_KNOB = "paywall_tips_enabled"
TIPS = [
    {"product_id": "ftf_tip_199", "display_price": "$1.99"},
    {"product_id": "ftf_tip_499", "display_price": "$4.99"},
    {"product_id": "ftf_tip_999", "display_price": "$9.99"},
]


def _set_tip_knob(eng, value):
    """Write the knob row straight to the table (no reload_config), so a
    changed answer proves the read is live. None deletes the row and leaves
    another one, so get_config() serves DB rows rather than the seed list
    and the missing key hits the helper's inline fallback (G-064)."""
    with eng.begin() as conn:
        conn.execute(model_config_table.delete()
                     .where(model_config_table.c.key == TIP_KNOB))
        if value is None:
            conn.execute(model_config_table.delete()
                         .where(model_config_table.c.key == "vet_age"))
            conn.execute(insert(model_config_table).values(key="vet_age", value=27))
        else:
            conn.execute(insert(model_config_table).values(key=TIP_KNOB, value=value))


def test_tips_empty_at_launch(client, monkeypatch):
    """At the seeded default (knob 0) the config serves `tips: []` and no
    tip id or price leaks."""
    _flags(monkeypatch, "monetize.paywall")
    r = _get(client)
    assert r.get_json()["tips"] == []
    assert "ftf_tip" not in r.get_data(as_text=True)


def test_tip_knob_seeded_zero():
    assert [v for k, v, _ in db_module._MODEL_CONFIG_DEFAULTS
            if k == TIP_KNOB] == [0]


@pytest.mark.parametrize("query", ["?platform=ios", "", "?platform=nintendo"])
def test_tips_served_on_ios_when_knob_is_1(client, monkeypatch, mem_engine, query):
    """Knob 1 + the RESOLVED platform ios (explicit, the default, or an
    unknown value degraded to ios) → exactly the three SKUs, in order."""
    _flags(monkeypatch, "monetize.paywall")
    _set_tip_knob(mem_engine, 1.0)
    body = _get(client, query).get_json()
    assert body["platform"] == "ios"
    assert body["tips"] == TIPS


@pytest.mark.parametrize("session, served", [
    ({"verified": True}, True),
    ({}, False),                                    # never verified
    ({"verified": False}, False),
    ({"verified": True, "is_demo": True}, False),   # demo, even if stamped
    ({"is_demo": True}, False),
])
def test_tips_need_a_verified_non_demo_session(client, monkeypatch, mem_engine,
                                               session, served):
    """Defence in depth behind #495's verified-only Settings row: knob 1
    + ios still serves [] to an unverified or demo session (the same
    predicate as _session_verification)."""
    _flags(monkeypatch, "monetize.paywall")
    _set_tip_knob(mem_engine, 1.0)
    with server._sessions_lock:
        server._sessions[TOKEN] = {"user_id": USER, "last_active": 0.0,
                                   **session}
    r = _get(client, "?platform=ios")
    assert r.status_code == 200
    assert r.get_json()["tips"] == (TIPS if served else [])
    if not served:
        assert "ftf_tip" not in r.get_data(as_text=True)


@pytest.mark.parametrize("platform", ["web", "extension"])
def test_no_tips_off_ios_even_when_knob_is_1(client, monkeypatch, mem_engine,
                                             platform):
    """Web and the extension have no in-app purchase (plan §1)."""
    _flags(monkeypatch, "monetize.paywall")
    _set_tip_knob(mem_engine, 1.0)
    r = _get(client, f"?platform={platform}")
    assert r.get_json()["tips"] == []
    assert "ftf_tip" not in r.get_data(as_text=True)


@pytest.mark.parametrize("value", [0.0, 2.0, -1.0, 0.5, 1.0001, None])
def test_no_tips_unless_knob_is_exactly_1(client, monkeypatch, mem_engine, value):
    """0, 2, any other number and a missing row (None) all serve []."""
    _flags(monkeypatch, "monetize.paywall")
    _set_tip_knob(mem_engine, value)
    assert _get(client, "?platform=ios").get_json()["tips"] == []


@pytest.mark.parametrize("value", ["abc", "", None, float("nan"), float("inf")])
def test_no_tips_for_a_garbage_knob(client, monkeypatch, value):
    """Values the Float column can't hold, injected at the read."""
    _flags(monkeypatch, "monetize.paywall")
    monkeypatch.setattr(server, "get_config", lambda: {TIP_KNOB: value})
    assert _get(client, "?platform=ios").get_json()["tips"] == []


def test_no_tips_when_the_knob_read_fails(client, monkeypatch):
    def boom():
        raise RuntimeError("db down")
    _flags(monkeypatch, "monetize.paywall")
    monkeypatch.setattr(server, "get_config", boom)
    r = _get(client, "?platform=ios")
    assert r.status_code == 200
    assert r.get_json()["tips"] == []


def test_tip_knob_read_live_per_request(client, monkeypatch, mem_engine):
    """No cache and no reload: flipping the stored row flips the next
    response, so 0 is a deploy-free kill switch."""
    _flags(monkeypatch, "monetize.paywall")
    for value, expected in [(1.0, TIPS), (0.0, []), (1.0, TIPS), (2.0, [])]:
        _set_tip_knob(mem_engine, value)
        assert _get(client, "?platform=ios").get_json()["tips"] == expected


@pytest.mark.parametrize("query", ["", "?platform=ios", "?platform=web",
                                   "?platform=extension"])
def test_flag_off_ignores_the_tip_knob(client, monkeypatch, mem_engine, query):
    """`monetize.paywall` off → `{"enabled": false}` and nothing else, knob
    or not."""
    _flags(monkeypatch)
    _set_tip_knob(mem_engine, 1.0)
    r = _get(client, query)
    assert r.get_json() == {"enabled": False}
    assert "ftf_tip" not in r.get_data(as_text=True)


def test_restorable_tip_skus_are_tip_products():
    """`_PAYWALL_TIPS` is the list served behind the knob. Every SKU in it
    must hit the projector's no-entitlement guard — a tip id drifting out
    of the ftf_tip_ prefix would grant Pro — and none claims entitlement
    fields: a tip buys nothing."""
    from backend import entitlements as entl
    assert [t["product_id"] for t in server._PAYWALL_TIPS] == [
        "ftf_tip_199", "ftf_tip_499", "ftf_tip_999"]
    for t in server._PAYWALL_TIPS:
        assert entl.is_tip_product(t["product_id"])
        assert "trial_days" not in t and "period" not in t


def test_flag_off_leaks_no_tips(client, monkeypatch):
    _flags(monkeypatch)
    assert "ftf_tip" not in _get(client).get_data(as_text=True)


# ── (g) fallback prices: the rise instant, no trial_days ─────────────────

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
