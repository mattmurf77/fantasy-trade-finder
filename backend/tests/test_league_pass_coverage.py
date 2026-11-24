"""League pass coverage — docs/plans/monetization/league-pass/lld.md §3.1–3.2, §11.

Covers `league_pass.covers` / `covered_members` / `is_member` / `passes_for`:
  * each of the four conditions alone turns coverage off: no active pass for
    the league, a league outside the allow-list, a pass that is not live, a
    user who is not a covered member;
  * expiry, refund and billing grace follow the buyer's entitlements row,
    driven through the real billing projector (coverage is derived, never
    stored: no per-member row is written);
  * the seat cap (total_rosters + league_pass_seat_allowance, R7);
  * the allow-list env var (unset/empty = every league, R41);
  * comp passes live until comp_expires_at;
  * membership: Sleeper league_members (acct_* resolves to its Sleeper id),
    ESPN / MFL platform_league_bindings (league_members' synthetic team rows
    never count), a member of another league is not covered (R2).

In-memory SQLite (patched backend.database.engine); flags patched on the
league_pass module.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

import backend.database as db_module
import backend.entitlements as entl
import backend.league_pass as lp
from backend.tests.support import league_pass_world as w

L = "lg_cov"
BUYER = "buyer_1"
MATE = "mate_1"


@pytest.fixture()
def eng(monkeypatch):
    engine = w.make_engine()
    monkeypatch.delenv(lp.ALLOWLIST_ENV, raising=False)
    monkeypatch.setattr(lp, "is_enabled", lambda k: k == lp.FLAG)
    with engine.begin() as conn:
        w.league(conn, L, total_rosters=12)
        w.member(conn, L, BUYER)
        w.member(conn, L, MATE)
    with patch.object(db_module, "engine", engine):
        yield engine


def _paid_pass(eng, *, expires_days=365.0, status="active"):
    with eng.begin() as conn:
        w.ent_row(conn, BUYER, expires_days=expires_days, status=status)
        return w.pass_row(conn, L, buyer=BUYER)


def test_member_and_buyer_are_covered_until_the_buyers_expiry(eng):
    pass_id = _paid_pass(eng)
    expires = entl.list_for_user(BUYER)[0]["expires_at"]
    assert lp.covers(MATE, L) == lp.Coverage(pass_id, L, expires, "member")
    assert lp.covers(BUYER, L) == lp.Coverage(pass_id, L, expires, "buyer")
    # Derived, never stored: the member holds no entitlement row and no pro.
    assert entl.list_for_user(MATE) == []
    assert entl.get_entitlements(MATE)["pro"] is False


def test_no_active_pass_is_not_covered(eng):
    with eng.begin() as conn:
        w.ent_row(conn, BUYER)
        w.pass_row(conn, L, buyer=BUYER, status="released")
    assert lp.covers(MATE, L) is None


def test_allow_list(eng, monkeypatch):
    _paid_pass(eng)
    monkeypatch.setenv(lp.ALLOWLIST_ENV, "other_league, another")
    assert lp.covers(MATE, L) is None
    monkeypatch.setenv(lp.ALLOWLIST_ENV, f"other_league,{L}")
    assert lp.covers(MATE, L) is not None
    monkeypatch.setenv(lp.ALLOWLIST_ENV, " , ")
    assert lp.covers(MATE, L) is not None


@pytest.mark.parametrize("expires_days,status", [
    (-1.0, "active"),        # expires_at is read-time truth
    (365.0, "expired"),
    (365.0, "refunded"),
    (365.0, "revoked"),
])
def test_a_pass_whose_buyer_row_is_not_live_covers_no_one(eng, expires_days, status):
    _paid_pass(eng, expires_days=expires_days, status=status)
    assert lp.covers(MATE, L) is None
    assert lp.covers(BUYER, L) is None


def test_a_pass_whose_buyer_has_only_another_product_covers_no_one(eng):
    """Liveness reads the league_pass_iap row only: an individual plan of the
    buyer's does not keep the pass alive."""
    with eng.begin() as conn:
        w.ent_row(conn, BUYER, product="ftf_pro_annual", source="apple_iap")
        w.pass_row(conn, L, buyer=BUYER)
    assert lp.covers(MATE, L) is None


def test_not_a_member_and_another_league_are_not_covered(eng):
    _paid_pass(eng)
    with eng.begin() as conn:
        w.user(conn, "stranger")
        w.league(conn, "lg_other")
        w.member(conn, "lg_other", MATE)
    assert lp.covers("stranger", L) is None
    assert lp.covers(MATE, "lg_other") is None       # R2


def _rc(eid, etype, product="ftf_league_annual", **extra):
    ev = {"id": eid, "type": etype, "app_user_id": BUYER, "product_id": product, **extra}
    return entl.ingest_billing_event("revenuecat", eid, etype, ev,
                                     user_id=BUYER, product_id=product)


def _ms(days):
    return (datetime.now(timezone.utc) + timedelta(days=days)).timestamp() * 1000


def test_expiry_and_grace_follow_the_buyers_row_through_the_projector(eng):
    _rc("e1", "INITIAL_PURCHASE", expiration_at_ms=_ms(2))
    with eng.begin() as conn:
        w.pass_row(conn, L, buyer=BUYER)
    first = lp.covers(MATE, L).covered_until
    # Billing issue: the grace date extends the row, and coverage with it (R34).
    _rc("e2", "BILLING_ISSUE", grace_period_expiration_at_ms=_ms(16))
    assert lp.covers(MATE, L).covered_until > first
    _rc("e3", "EXPIRATION")
    assert lp.covers(MATE, L) is None                  # R33


def test_refund_ends_coverage_at_once(eng):
    _rc("r1", "INITIAL_PURCHASE", expiration_at_ms=_ms(365))
    with eng.begin() as conn:
        w.pass_row(conn, L, buyer=BUYER)
    assert lp.covers(MATE, L) is not None
    _rc("r2", "REFUND")
    assert lp.covers(MATE, L) is None


def test_seat_cap_is_total_rosters_plus_the_allowance(eng):
    """R7: the oldest members are covered; the newest past the cap are not."""
    with eng.begin() as conn:
        w.league(conn, "lg_small", total_rosters=2)
        for uid in ("s1", "s2", "s3", "s4", "s5"):
            w.member(conn, "lg_small", uid)
        w.ent_row(conn, BUYER)
        w.pass_row(conn, "lg_small", buyer=BUYER)
    assert lp.covered_members("lg_small", "sleeper") == ["s1", "s2", "s3", "s4"]
    assert lp.covers("s4", "lg_small") is not None
    assert lp.covers("s5", "lg_small") is None
    with eng.begin() as conn:
        w.knob(conn, "league_pass_seat_allowance", 0)
    assert lp.covered_members("lg_small", "sleeper") == ["s1", "s2"]
    assert lp.covers("s3", "lg_small") is None


def test_non_app_sleeper_managers_take_no_seat(eng):
    with eng.begin() as conn:
        w.league(conn, "lg_mixed", total_rosters=1)
        w.member(conn, "lg_mixed", "ghost", app_user=False)
        w.member(conn, "lg_mixed", "real")
    with eng.begin() as conn:
        w.knob(conn, "league_pass_seat_allowance", 0)
    assert lp.covered_members("lg_mixed", "sleeper") == ["real"]


def test_comp_pass_lives_until_its_own_expiry(eng):
    with eng.begin() as conn:
        live = w.pass_row(conn, L, origin="comp", comp_days=5)
    cov = lp.covers(MATE, L)
    assert cov.pass_id == live and cov.role == "member"
    with eng.begin() as conn:
        conn.execute(db_module.league_passes_table.update().values(comp_expires_at=w.iso(-1)))
    assert lp.covers(MATE, L) is None


@pytest.mark.parametrize("platform", ["espn", "mfl"])
def test_espn_and_mfl_membership_is_a_platform_binding(eng, platform):
    """lld §3.1 + §13 item 2: a binding (proven or not) is membership; the
    league_members rows those platforms write for unbound teams never are."""
    lid = f"lg_{platform}"
    with eng.begin() as conn:
        w.league(conn, lid, platform=platform, total_rosters=10)
        w.user(conn, "bound_user")
        w.user(conn, "synthetic_only")
        w.binding(conn, "bound_user", lid, platform)
        w.member(conn, lid, "synthetic_only")
        w.ent_row(conn, BUYER)
        w.pass_row(conn, lid, buyer=BUYER, platform=platform)
    assert lp.is_member("bound_user", lid, platform) is True
    assert lp.is_member("synthetic_only", lid, platform) is False
    assert lp.covers("bound_user", lid).role == "member"
    assert lp.covers("synthetic_only", lid) is None


def test_binding_seat_order_is_oldest_first(eng):
    with eng.begin() as conn:
        w.league(conn, "lg_e", platform="espn", total_rosters=1)
        w.binding(conn, "newer", "lg_e", "espn", created_days=-1)
        w.binding(conn, "older", "lg_e", "espn", created_days=-5)
        w.knob(conn, "league_pass_seat_allowance", 0)
    assert lp.covered_members("lg_e", "espn") == ["older"]


def test_an_account_key_resolves_to_its_sleeper_membership(eng):
    _paid_pass(eng)
    with eng.begin() as conn:
        w.account(conn, "abc123", sleeper_user_id=MATE)
    assert lp.is_member("acct_abc123", L, "sleeper") is True
    assert lp.covers("acct_abc123", L).role == "member"


def test_the_buyers_account_key_reads_as_the_buyer(eng):
    with eng.begin() as conn:
        w.account(conn, "buyacct", sleeper_user_id=BUYER)
    _paid_pass(eng)
    assert lp.covers("acct_buyacct", L).role == "buyer"


def test_passes_for_lists_live_passes_from_the_users_leagues(eng):
    pass_id = _paid_pass(eng)
    with eng.begin() as conn:
        w.league(conn, "lg_dead")
        w.member(conn, "lg_dead", MATE)
        w.pass_row(conn, "lg_dead", origin="comp", comp_days=-1)
    [entry] = lp.passes_for(MATE)
    assert entry["pass_id"] == pass_id and entry["role"] == "member"
    assert entry["platform"] == "sleeper" and entry["buyer_display"] is None
    with eng.begin() as conn:
        conn.execute(db_module.users_table.update()
                     .where(db_module.users_table.c.sleeper_user_id == BUYER)
                     .values(display_name="Buyer B"))
        conn.execute(db_module.league_passes_table.update()
                     .where(db_module.league_passes_table.c.id == pass_id)
                     .values(show_buyer=1))
    assert lp.passes_for(MATE)[0]["buyer_display"] == "Buyer B"
    assert lp.passes_for(BUYER)[0]["role"] == "buyer"
    assert lp.passes_for("nobody") == []


def test_the_four_events_are_registered_server_fired_and_non_intent():
    """lld §9: registered in the same change as the emitters; the client
    can never send them."""
    import backend.analytics_queries as q
    import backend.analytics_taxonomy as tax
    for name in ("league_pass_quote_viewed", "league_pass_bound", "league_pass_ended",
                 "league_pass_coverage_used"):
        assert name in tax.SERVER_FIRED_EVENTS
        assert name not in tax.ALLOWED_CLIENT_EVENTS
        assert name in q.NON_INTENT_EVENTS and name not in q.INTENT_EVENTS
