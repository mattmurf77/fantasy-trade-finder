"""Billing-safety fixes in backend/entitlements.py (merge dark).

Source: docs/plans/org-bringup/monetization-day1-feasibility.md §2 and its
2026-10-24 addendum ("A correction first: the sandbox defect fix"); Product
spec #393.

Covers:
  (1) sandbox cap — RevenueCat SANDBOX events still project (App Review and
      TestFlight purchases unlock) but expires_at = min(payload, now + 24 h);
      a NULL expiry becomes now + 24 h, never perpetual; the renewal and
      BILLING_ISSUE extend paths stay inside the cap; rows are tagged
      `sandbox:<event_id>` in granted_by; production is uncapped
  (2) perpetual-grant guard — a non-founder grant with no expiry is refused
      with process_error `perpetual_grant_refused…` and writes no row (nor
      turns an existing row perpetual); founder lifetime still grants
      perpetually; tips still grant nothing
  (3) enforce = monetize.entitlements ∧ monetize.paywall ∧ knob == 1 — all
      8 combinations; only all three on blocks, every other entitlements-on
      combination observes (logs ENTITLE-OBSERVE, returns True)
  (4) kill knob — model_config `paywall_enforce_enabled` seeded 0, read live
      per call (flip the stored row, the answer changes, no reload); a
      missing row or failed read is 0, not enforcing (G-064)
  (5) GET /api/me/entitlements `enforcing` uses the same is_enforcing() rule
      as check_pro: true only when all three legs are on
  (6) lanes (release-lead P2) — a SANDBOX event never updates, extends,
      shortens, deactivates, re-keys or transfers a PRODUCTION row: per
      event type, against a production founder lifetime (NULL expiry) and a
      production annual, the production row is byte-unchanged and the
      sandbox effect lands only on a sandbox row; production events leave
      sandbox rows alone

In-memory SQLite via the same patched-engine harness as test_entitlements.py;
Flask test client + injected session for the route. No network.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, insert, select

import backend.database as db_module
import backend.entitlements as entl
import backend.server as server
from backend.database import (
    accounts_table, entitlements_table, metadata, model_config_table,
    subscription_events_table, users_table,
)

USER = "safety_user_1"
DAY = timedelta(days=1)


def _iso(days: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def _ms(delta: timedelta) -> float:
    return (datetime.now(timezone.utc) + delta).timestamp() * 1000


@pytest.fixture()
def eng():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(insert(users_table).values(
            sleeper_user_id=USER, username="safetyuser", created_at=_iso(0)))
    with patch.object(db_module, "engine", engine):
        yield engine


def _rc(eid, etype, *, env="PRODUCTION", expires=timedelta(days=30),
        product="ftf_pro_monthly"):
    """A RevenueCat event object, the same shape the webhook stores.
    expires=None → no expiration_at_ms (non-renewing / lifetime)."""
    ev = {"id": eid, "type": etype, "app_user_id": USER,
          "product_id": product, "environment": env,
          "expiration_at_ms": _ms(expires) if expires is not None else None}
    return ev


def _ingest(ev):
    return entl.ingest_billing_event(
        "revenuecat", ev["id"], ev["type"], ev,
        user_id=ev["app_user_id"], product_id=ev["product_id"])


def _rows():
    return entl.list_for_user(USER)


def _process_error(eng, eid):
    with eng.begin() as conn:
        return conn.execute(
            select(subscription_events_table.c.process_error)
            .where(subscription_events_table.c.event_id == eid)).scalar()


class _Window:
    """now + 24 h, bracketed by wall-clock reads taken around the call."""
    def __enter__(self):
        self.lo = datetime.now(timezone.utc) + DAY
        return self

    def __exit__(self, *exc):
        self.hi = datetime.now(timezone.utc) + DAY

    def holds(self, iso: str | None) -> bool:
        return iso is not None and self.lo <= datetime.fromisoformat(iso) <= self.hi


# ── (1) sandbox cap ────────────────────────────────────────────────────────

def test_sandbox_long_expiry_capped_to_24h(eng):
    with _Window() as w:
        r = _ingest(_rc("s1", "INITIAL_PURCHASE", env="SANDBOX",
                        expires=timedelta(days=30)))
    assert r["projected"] is True
    (row,) = _rows()
    assert w.holds(row["expires_at"])
    assert row["granted_by"] == "sandbox:s1"
    assert entl.get_entitlements(USER)["pro"] is True   # App Review unlocks


def test_sandbox_short_expiry_unchanged(eng):
    ev = _rc("s2", "INITIAL_PURCHASE", env="SANDBOX", expires=timedelta(hours=1))
    _ingest(ev)
    (row,) = _rows()
    assert row["expires_at"] == entl._ms_to_iso(ev["expiration_at_ms"])


@pytest.mark.parametrize("drop_key", [False, True])
def test_sandbox_null_expiry_capped_never_perpetual(eng, drop_key):
    ev = _rc("s3", "NON_RENEWING_PURCHASE", env="SANDBOX", expires=None,
             product="ftf_season_pass_2026")
    if drop_key:
        del ev["expiration_at_ms"]
    with _Window() as w:
        r = _ingest(ev)
    assert r["projected"] is True
    (row,) = _rows()
    assert row["expires_at"] is not None and w.holds(row["expires_at"])
    assert row["granted_by"] == "sandbox:s3"


def test_sandbox_founder_lifetime_capped_never_perpetual(eng):
    with _Window() as w:
        _ingest(_rc("s4", "NON_RENEWING_PURCHASE", env="SANDBOX", expires=None,
                    product="ftf_founder"))
    (row,) = _rows()
    assert row["source"] == "founder_iap"
    assert row["expires_at"] is not None and w.holds(row["expires_at"])


def test_sandbox_renewal_stays_within_cap(eng):
    _ingest(_rc("s5", "INITIAL_PURCHASE", env="SANDBOX",
                expires=timedelta(minutes=5)))
    with _Window() as w:
        _ingest(_rc("s6", "RENEWAL", env="SANDBOX", expires=timedelta(days=365)))
    (row,) = _rows()                                    # same row, upserted
    assert w.holds(row["expires_at"])
    assert row["granted_by"] == "sandbox:s6"


def test_sandbox_billing_issue_grace_stays_within_cap(eng):
    _ingest(_rc("s7", "INITIAL_PURCHASE", env="SANDBOX",
                expires=timedelta(hours=1)))
    ev = _rc("s8", "BILLING_ISSUE", env="SANDBOX")
    ev["grace_period_expiration_at_ms"] = _ms(timedelta(days=16))
    with _Window() as w:
        r = _ingest(ev)
    assert r["projected"] is True                       # extended, up to the cap
    (row,) = _rows()
    assert w.holds(row["expires_at"])
    assert row["granted_by"] == "sandbox:s8"


@pytest.mark.parametrize("env", ["PRODUCTION", None])
def test_production_events_uncapped(eng, env):
    ev = _rc("p1", "INITIAL_PURCHASE", env=env, expires=timedelta(days=30))
    if env is None:
        del ev["environment"]
    _ingest(ev)
    (row,) = _rows()
    assert row["expires_at"] == entl._ms_to_iso(ev["expiration_at_ms"])
    assert row["granted_by"] == "p1"

    ev2 = _rc("p2", "BILLING_ISSUE", env=env)
    ev2["grace_period_expiration_at_ms"] = _ms(timedelta(days=46))
    _ingest(ev2)
    assert _rows()[0]["expires_at"] == entl._ms_to_iso(
        ev2["grace_period_expiration_at_ms"])


# ── (2) perpetual-grant guard ──────────────────────────────────────────────

def test_production_non_founder_no_expiry_refused(eng):
    r = _ingest(_rc("g1", "NON_RENEWING_PURCHASE", expires=None,
                    product="ftf_season_pass_2026"))
    assert r == {"stored": True, "projected": False, "duplicate": False}
    assert _process_error(eng, "g1").startswith("perpetual_grant_refused")
    assert _rows() == []
    assert entl.get_entitlements(USER)["pro"] is False


def test_guard_never_turns_existing_row_perpetual(eng):
    ev = _rc("g2", "INITIAL_PURCHASE", expires=timedelta(days=30))
    _ingest(ev)
    r = _ingest(_rc("g3", "RENEWAL", expires=None))
    assert r["projected"] is False
    assert _process_error(eng, "g3").startswith("perpetual_grant_refused")
    (row,) = _rows()
    assert row["expires_at"] == entl._ms_to_iso(ev["expiration_at_ms"])
    assert row["granted_by"] == "g2"


def test_founder_no_expiry_still_perpetual(eng):
    r = _ingest(_rc("g4", "NON_RENEWING_PURCHASE", expires=None,
                    product="ftf_founder"))
    assert r["projected"] is True
    assert _process_error(eng, "g4") is None
    (row,) = _rows()
    assert row["source"] == "founder_iap" and row["expires_at"] is None


@pytest.mark.parametrize("env", ["PRODUCTION", "SANDBOX"])
def test_tip_still_grants_nothing(eng, env):
    r = _ingest(_rc("g5", "NON_RENEWING_PURCHASE", env=env, expires=None,
                    product="ftf_tip_small"))
    assert r["projected"] is False
    assert _process_error(eng, "g5").startswith("tip:")
    assert _rows() == []


# ── (4) kill knob: paywall_enforce_enabled ─────────────────────────────────

KNOB = "paywall_enforce_enabled"


def _set_knob(eng, value):
    """Write the knob row straight to the table (no reload_config call), so
    a changed answer proves the read is live."""
    with eng.begin() as conn:
        conn.execute(model_config_table.delete()
                     .where(model_config_table.c.key == KNOB))
        if value is not None:
            conn.execute(insert(model_config_table).values(key=KNOB, value=value))


def _other_config_row(eng):
    """A non-empty model_config, so get_config() serves DB rows rather than
    falling back to the seed list — a missing knob row then hits the inline
    fallback in entitlements, which is what G-064 is about."""
    with eng.begin() as conn:
        conn.execute(insert(model_config_table).values(key="vet_age", value=27))


def test_knob_seeded_zero():
    seeded = {k: v for k, v, _ in db_module._MODEL_CONFIG_DEFAULTS}
    assert seeded[KNOB] == 0


def test_knob_missing_row_reads_not_enforcing(eng):
    _other_config_row(eng)
    assert KNOB not in db_module.get_config()
    assert entl._enforce_knob_on() is False


def test_knob_failed_read_is_not_enforcing(eng):
    def boom():
        raise RuntimeError("db down")
    with patch.object(db_module, "get_config", boom):
        assert entl._enforce_knob_on() is False


def test_knob_read_live_between_calls(eng):
    _other_config_row(eng)
    _set_knob(eng, 1.0)
    assert entl._enforce_knob_on() is True
    _set_knob(eng, 0.0)
    assert entl._enforce_knob_on() is False
    _set_knob(eng, 1.0)
    assert entl._enforce_knob_on() is True
    _set_knob(eng, 2.0)                                 # exactly 1, not truthy
    assert entl._enforce_knob_on() is False


# ── (3) enforce truth table: entitlements × paywall × knob ─────────────────

class _Cap:
    def __init__(self):
        self.lines = []

    def info(self, msg, *a):
        self.lines.append(msg % a)


def _flags(*on):
    return lambda k: k in on


@pytest.mark.parametrize("ent", [False, True])
@pytest.mark.parametrize("paywall", [False, True])
@pytest.mark.parametrize("knob", [0.0, 1.0])
def test_enforce_truth_table(eng, ent, paywall, knob):
    _set_knob(eng, knob)
    on = [k for k, v in (("monetize.entitlements", ent),
                         ("monetize.paywall", paywall)) if v]
    cap = _Cap()
    with patch.object(entl, "is_enabled", _flags(*on)):
        allowed = entl.check_pro(USER, "/api/x", logger=cap)   # USER has no pro
    enforce = ent and paywall and knob == 1.0
    assert allowed is (not enforce)
    observed = any("ENTITLE-OBSERVE" in l and "would_block=True" in l
                   for l in cap.lines)
    assert observed is (ent and not enforce)


def test_enforce_still_lets_pro_through(eng):
    _set_knob(eng, 1.0)
    both = _flags("monetize.entitlements", "monetize.paywall")
    with patch.object(entl, "is_enabled", both):
        assert entl.check_pro(USER, "/api/x") is False
        entl.grant(USER, "pro", source="manual_grant")
        assert entl.check_pro(USER, "/api/x") is True


def test_check_pro_reads_knob_live(eng):
    _other_config_row(eng)
    both = _flags("monetize.entitlements", "monetize.paywall")
    with patch.object(entl, "is_enabled", both):
        _set_knob(eng, 1.0)
        assert entl.check_pro(USER, "/api/x") is False      # enforcing
        _set_knob(eng, 0.0)
        assert entl.check_pro(USER, "/api/x") is True       # killed, no deploy


def test_check_pro_missing_knob_row_does_not_enforce(eng):
    """G-064: an absent row must read as 0 (observe), not as enforcing."""
    _other_config_row(eng)
    cap = _Cap()
    both = _flags("monetize.entitlements", "monetize.paywall")
    with patch.object(entl, "is_enabled", both):
        assert entl.check_pro(USER, "/api/x", logger=cap) is True
    assert any("ENTITLE-OBSERVE" in l for l in cap.lines)


def test_monetize_pro_is_not_read(eng):
    """monetize.pro is retired: flipping it alone (or with entitlements)
    never changes the gate."""
    _set_knob(eng, 1.0)
    seen = []

    def spy(k):
        seen.append(k)
        return k in ("monetize.entitlements", "monetize.pro")

    with patch.object(entl, "is_enabled", spy):
        assert entl.check_pro(USER, "/api/x") is True
    assert "monetize.pro" not in seen


# ── (5) /api/me/entitlements `enforcing` = the check_pro rule ──────────────

TOKEN = "safety-test-token"


@pytest.fixture()
def client(eng):
    server.app.config["TESTING"] = True
    c = server.app.test_client()
    with server._sessions_lock:
        server._sessions[TOKEN] = {"user_id": USER, "last_active": 0.0}
    try:
        yield c
    finally:
        with server._sessions_lock:
            server._sessions.pop(TOKEN, None)


@pytest.mark.parametrize("ent", [False, True])
@pytest.mark.parametrize("paywall", [False, True])
@pytest.mark.parametrize("knob", [0.0, 1.0])
def test_me_entitlements_enforcing_matches_check_pro(eng, client, ent, paywall, knob):
    """All 8 combinations, which include every single-leg flip off all-on
    and every single leg on alone: enforcing is true only when all three
    are on, and always agrees with check_pro's verdict for a non-pro user."""
    _set_knob(eng, knob)
    on = [k for k, v in (("monetize.entitlements", ent),
                         ("monetize.paywall", paywall)) if v]
    with patch.object(entl, "is_enabled", _flags(*on)):
        r = client.get("/api/me/entitlements",
                       headers={"X-Session-Token": TOKEN})
        blocked = entl.check_pro(USER, "/api/x") is False
    assert r.status_code == 200
    enforcing = r.get_json()["enforcing"]
    assert enforcing is (ent and paywall and knob == 1.0)
    assert enforcing is blocked


# ── (6) lanes: sandbox events never touch production rows ──────────────────
# A user who holds a real (PRODUCTION) row and then buys in sandbox — a
# TestFlight tester, or an App Review account that also has a real grant —
# hits the same (user, product) key. The sandbox event must land on a
# sandbox row of its own; the production row stays byte-identical
# (updated_at included, so even a no-op rewrite would show).

USER2 = "safety_user_2"
ANON = "$RCAnonymousID:5b1d"
ACCT = "acct_safety1"

# kind → (product, production event type, production expiry)
PROD = {
    "founder": ("ftf_founder", "NON_RENEWING_PURCHASE", None),
    "annual": ("ftf_pro_annual", "INITIAL_PURCHASE", timedelta(days=365)),
    # an annual about to lapse: the one a stray sandbox grace would extend
    "annual_ending": ("ftf_pro_annual", "INITIAL_PURCHASE", timedelta(hours=1)),
}


def _row(eng, row_id):
    with eng.begin() as conn:
        return dict(conn.execute(select(entitlements_table).where(
            entitlements_table.c.id == row_id)).fetchone()._mapping)


def _prod_row(eng, kind, user=USER):
    product, etype, exp = PROD[kind]
    ev = _rc(f"prod-{kind}", etype, expires=exp, product=product)
    ev["app_user_id"] = user
    r = _ingest(ev)
    assert r["projected"] is True
    (row,) = [x for x in entl.list_for_user(user) if x["product_id"] == product]
    assert not (row["granted_by"] or "").startswith("sandbox:")
    return product, _row(eng, row["id"])


def _sandbox_rows(user=USER):
    return [r for r in entl.list_for_user(user)
            if (r["granted_by"] or "").startswith("sandbox:")]


def _sb(eid, etype, product, **kw):
    return _rc(eid, etype, env="SANDBOX", product=product, **kw)


def _second_user(eng):
    with eng.begin() as conn:
        conn.execute(insert(users_table).values(
            sleeper_user_id=USER2, username="safetyuser2", created_at=_iso(0)))


def _sb_transfer(eid, product):
    return {"id": eid, "type": "TRANSFER", "environment": "SANDBOX",
            "app_user_id": USER, "product_id": product,
            "transferred_from": [USER], "transferred_to": [USER2]}


def _assert_untouched(eng, prod):
    assert _row(eng, prod["id"]) == prod
    # resolution: the production row is never weakened by sandbox activity
    # (a lifetime stays perpetual; a dated row's expiry is a floor — an
    # unexpired sandbox row may sit later, never earlier)
    out = entl.get_entitlements(prod["user_id"])
    assert out["pro"] is True
    if prod["expires_at"] is None:
        assert out["expires_at"] is None
    else:
        assert (datetime.fromisoformat(out["expires_at"])
                >= datetime.fromisoformat(prod["expires_at"]))


@pytest.mark.parametrize("kind", ["founder", "annual"])
@pytest.mark.parametrize("etype", ["INITIAL_PURCHASE", "RENEWAL",
                                   "PRODUCT_CHANGE", "NON_RENEWING_PURCHASE",
                                   "UNCANCELLATION"])
def test_sandbox_activation_lands_on_own_row(eng, kind, etype):
    product, prod = _prod_row(eng, kind)
    with _Window() as w:
        r = _ingest(_sb("sb1", etype, product, expires=timedelta(days=30)))
    assert r["projected"] is True
    _assert_untouched(eng, prod)
    (sb,) = _sandbox_rows()
    assert sb["id"] != prod["id"] and sb["product_id"] == product
    assert sb["granted_by"] == "sandbox:sb1" and sb["status"] == "active"
    assert w.holds(sb["expires_at"])


@pytest.mark.parametrize("kind", ["founder", "annual"])
def test_sandbox_renewal_upserts_only_the_sandbox_row(eng, kind):
    product, prod = _prod_row(eng, kind)
    _ingest(_sb("sb1", "INITIAL_PURCHASE", product, expires=timedelta(minutes=5)))
    _ingest(_sb("sb2", "RENEWAL", product, expires=timedelta(minutes=10)))
    _assert_untouched(eng, prod)
    (sb,) = _sandbox_rows()                       # one sandbox row, upserted
    assert sb["granted_by"] == "sandbox:sb2"


@pytest.mark.parametrize("kind", ["founder", "annual"])
@pytest.mark.parametrize("etype, status", [("EXPIRATION", "expired"),
                                           ("REFUND", "refunded")])
def test_sandbox_deactivation_hits_only_the_sandbox_row(eng, kind, etype, status):
    product, prod = _prod_row(eng, kind)
    _ingest(_sb("sb1", "INITIAL_PURCHASE", product))
    r = _ingest(_sb("sb2", etype, product))
    assert r["projected"] is True
    _assert_untouched(eng, prod)
    (sb,) = _sandbox_rows()
    assert sb["status"] == status and sb["granted_by"] == "sandbox:sb2"


@pytest.mark.parametrize("kind", ["founder", "annual"])
@pytest.mark.parametrize("etype", ["EXPIRATION", "REFUND"])
def test_sandbox_deactivation_without_sandbox_row_is_inert(eng, kind, etype):
    product, prod = _prod_row(eng, kind)
    _ingest(_sb("sb1", etype, product))
    _assert_untouched(eng, prod)
    assert _sandbox_rows() == []


@pytest.mark.parametrize("kind", ["founder", "annual"])
@pytest.mark.parametrize("etype", ["CANCELLATION", "SUBSCRIBER_ALIAS", "TEST"])
def test_sandbox_noop_events_touch_nothing(eng, kind, etype):
    product, prod = _prod_row(eng, kind)
    r = _ingest(_sb("sb1", etype, product))
    assert r["projected"] is False
    _assert_untouched(eng, prod)
    assert _sandbox_rows() == []


@pytest.mark.parametrize("kind", ["founder", "annual", "annual_ending"])
def test_sandbox_billing_issue_never_extends_production(eng, kind):
    product, prod = _prod_row(eng, kind)
    ev = _sb("sb1", "BILLING_ISSUE", product)
    ev["grace_period_expiration_at_ms"] = _ms(timedelta(days=16))
    assert _ingest(ev)["projected"] is False
    assert _process_error(eng, "sb1").startswith("ignored: BILLING_ISSUE")
    _assert_untouched(eng, prod)
    # with a sandbox row present, grace extends that row (inside the cap)
    _ingest(_sb("sb2", "INITIAL_PURCHASE", product, expires=timedelta(minutes=5)))
    ev = _sb("sb3", "BILLING_ISSUE", product)
    ev["grace_period_expiration_at_ms"] = _ms(timedelta(days=16))
    with _Window() as w:
        assert _ingest(ev)["projected"] is True
    _assert_untouched(eng, prod)
    (sb,) = _sandbox_rows()
    assert w.holds(sb["expires_at"]) and sb["granted_by"] == "sandbox:sb3"


@pytest.mark.parametrize("kind", ["founder", "annual"])
def test_sandbox_transfer_moves_only_sandbox_rows(eng, kind):
    _second_user(eng)
    product, prod = _prod_row(eng, kind)
    _ingest(_sb("sb1", "INITIAL_PURCHASE", product))
    assert _ingest(_sb_transfer("sb2", product))["projected"] is True
    _assert_untouched(eng, prod)                  # still USER's, unchanged
    assert _sandbox_rows(USER) == []
    (moved,) = entl.list_for_user(USER2)
    assert moved["granted_by"] == "sandbox:sb2"


@pytest.mark.parametrize("kind", ["founder", "annual"])
def test_sandbox_transfer_with_only_production_rows_is_inert(eng, kind):
    _second_user(eng)
    product, prod = _prod_row(eng, kind)
    assert _ingest(_sb_transfer("sb1", product))["projected"] is False
    _assert_untouched(eng, prod)
    assert entl.list_for_user(USER2) == []


@pytest.mark.parametrize("kind", ["founder", "annual"])
def test_sandbox_alias_reconciliation_never_rekeys_production(eng, kind):
    """A production row stranded under an anon id is not swept onto the
    account by sandbox traffic; the next production event moves it."""
    with eng.begin() as conn:
        conn.execute(insert(accounts_table).values(
            account_id=ACCT[len("acct_"):], sleeper_user_id=USER,
            created_at=_iso(0)))
    product, prod = _prod_row(eng, kind, user=ANON)
    ev = _sb("sb1", "INITIAL_PURCHASE", product)
    entl.ingest_billing_event("revenuecat", "sb1", ev["type"], ev,
                              user_id=ACCT, product_id=product,
                              aliases=[ACCT, ANON])
    assert _row(eng, prod["id"]) == prod          # still under ANON, unchanged
    (sb,) = _sandbox_rows(ACCT)
    assert sb["user_id"] == ACCT


def test_production_events_leave_sandbox_rows_alone(eng):
    """The other direction: sandbox rows are their own lane."""
    _ingest(_sb("sb1", "INITIAL_PURCHASE", "ftf_pro_annual"))
    (sb,) = _sandbox_rows()
    sb = _row(eng, sb["id"])
    _ingest(_rc("p1", "INITIAL_PURCHASE", product="ftf_pro_annual",
                expires=timedelta(days=365)))
    assert _row(eng, sb["id"]) == sb              # a new production row instead
    prod = [r for r in _rows() if r["id"] != sb["id"]]
    assert len(prod) == 1 and prod[0]["granted_by"] == "p1"
    _ingest(_rc("p2", "EXPIRATION", product="ftf_pro_annual"))
    assert _row(eng, sb["id"]) == sb
    assert _row(eng, prod[0]["id"])["status"] == "expired"
    assert entl.get_entitlements(USER)["pro"] is True   # sandbox still unlocks


def test_production_flow_unchanged(eng):
    """Production purchase → renewal → expiration upserts one row, as before."""
    _ingest(_rc("p1", "INITIAL_PURCHASE", expires=timedelta(days=30)))
    _ingest(_rc("p2", "RENEWAL", expires=timedelta(days=60)))
    (row,) = _rows()
    assert row["granted_by"] == "p2" and row["status"] == "active"
    _ingest(_rc("p3", "EXPIRATION"))
    (row,) = _rows()
    assert row["status"] == "expired"
