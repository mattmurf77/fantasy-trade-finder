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

In-memory SQLite via the same patched-engine harness as test_entitlements.py.
No network, no backend.server import.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, insert, select

import backend.database as db_module
import backend.entitlements as entl
from backend.database import metadata, subscription_events_table, users_table

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
