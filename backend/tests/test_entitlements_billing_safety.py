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

In-memory SQLite via the same patched-engine harness as test_entitlements.py.
No network, no backend.server import.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, insert, select

import backend.database as db_module
import backend.entitlements as entl
from backend.database import (
    metadata, model_config_table, subscription_events_table, users_table,
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
