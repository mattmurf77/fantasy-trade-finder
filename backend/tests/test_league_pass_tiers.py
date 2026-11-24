"""League pass price tiers — docs/plans/monetization/league-pass/lld.md §3.3, §11; prd R10–R11.

Covers `league_pass.tier_for`, `paid_annual_leaguemates` and the quote in
`create_intent`:
  * only a live, paid, production-lane `ftf_pro_annual` apple_iap row whose
    ledger shows a NORMAL period counts;
  * trial-only and intro-only ledgers, monthly plans, comps / manual / promo
    grants, sandbox rows, expired rows and members past the seat cap do not;
  * the buyer never counts themselves (any of their working keys);
  * the quote returns the tier's product, writes the intent snapshot and
    fires league_pass_quote_viewed {tier, platform, teams}.

In-memory SQLite; flags patched on the league_pass module.
"""

from unittest.mock import patch

import pytest
from sqlalchemy import select

import backend.database as db_module
import backend.league_pass as lp
from backend.tests.support import league_pass_world as w

L = "lg_tier"
BUYER = "tier_buyer"


@pytest.fixture()
def eng(monkeypatch):
    engine = w.make_engine()
    monkeypatch.delenv(lp.ALLOWLIST_ENV, raising=False)
    monkeypatch.setattr(lp, "is_enabled", lambda k: k == lp.FLAG)
    with engine.begin() as conn:
        w.league(conn, L, total_rosters=12)
        w.member(conn, L, BUYER)
    with patch.object(db_module, "engine", engine):
        yield engine


def _mate(eng, uid, **row):
    with eng.begin() as conn:
        w.member(conn, L, uid)
        if row:
            w.ent_row(conn, uid, **row)


PAID = dict(product="ftf_pro_annual", source="apple_iap", period="NORMAL")


@pytest.mark.parametrize("count,tier", [(0, 0), (1, 1), (2, 1), (3, 2), (11, 2)])
def test_tier_for(count, tier):
    assert lp.tier_for(count) == tier


def test_a_paid_annual_normal_period_counts(eng):
    _mate(eng, "m1", **PAID)
    assert lp.paid_annual_leaguemates(BUYER, L, "sleeper") == 1


def test_a_trial_then_normal_ledger_counts(eng):
    """A converted trial: the ledger shows a NORMAL period."""
    _mate(eng, "m1", **PAID)
    with eng.begin() as conn:
        conn.execute(db_module.subscription_events_table.insert().values(
            source="revenuecat", event_type="RENEWAL", user_id="m1",
            product_id="ftf_pro_annual", event_id="trial-start",
            payload='{"period_type": "TRIAL"}', occurred_at=w.iso(-60)))
    assert lp.paid_annual_leaguemates(BUYER, L, "sleeper") == 1


@pytest.mark.parametrize("row", [
    dict(PAID, period="TRIAL"),                                  # still in the free trial
    dict(PAID, period="INTRO"),                                  # intro price, not NORMAL
    dict(PAID, period=None),                                     # no ledger at all
    dict(PAID, product="ftf_pro_monthly"),                       # monthly plan
    dict(PAID, source="manual_grant"),                           # comp / manual grant
    dict(PAID, source="promo_referral"),                         # promo grant
    dict(PAID, source="trial"),
    dict(PAID, granted_by="sandbox:sb-1"),                       # sandbox lane
    dict(PAID, expires_days=-1.0),                               # lapsed
    dict(PAID, status="refunded"),
])
def test_rows_that_do_not_count(eng, row):
    _mate(eng, "m1", **row)
    assert lp.paid_annual_leaguemates(BUYER, L, "sleeper") == 0


def test_the_buyer_does_not_count_themselves(eng):
    with eng.begin() as conn:
        w.account(conn, "buyacct", sleeper_user_id=BUYER)
        w.ent_row(conn, BUYER, **PAID)
        # The same person's account key, as a second working key.
        w.ent_row(conn, "acct_buyacct", **PAID)
    assert lp.paid_annual_leaguemates(BUYER, L, "sleeper") == 0
    assert lp.paid_annual_leaguemates("acct_buyacct", L, "sleeper") == 0


def test_a_member_with_two_paid_rows_counts_once(eng):
    _mate(eng, "m1", **PAID)
    with eng.begin() as conn:
        w.ent_row(conn, "m1", **PAID)
    assert lp.paid_annual_leaguemates(BUYER, L, "sleeper") == 1


def test_espn_leaguemates_count_through_bindings(eng):
    with eng.begin() as conn:
        w.league(conn, "lg_espn", platform="espn", total_rosters=10)
        w.binding(conn, BUYER, "lg_espn", "espn")
        w.user(conn, "e1")
        w.binding(conn, "e1", "lg_espn", "espn")
        w.ent_row(conn, "e1", **PAID)
    assert lp.paid_annual_leaguemates(BUYER, "lg_espn", "espn") == 1


@pytest.mark.parametrize("paid,tier,product", [
    (0, 0, "ftf_league_annual"),
    (2, 1, "ftf_league_annual_t1"),
    (3, 2, "ftf_league_annual_t2"),
])
def test_quote_returns_the_tiers_product_and_snapshots_the_count(eng, paid, tier, product):
    for i in range(paid):
        _mate(eng, f"m{i}", **PAID)
    _mate(eng, "unpaid")
    quote = lp.create_intent(BUYER, L)
    assert quote["tier"] == tier and quote["product_id"] == product
    assert quote["teams"] == 12
    with eng.connect() as conn:
        intent = conn.execute(select(db_module.league_pass_intents_table)).fetchone()
    assert (intent.user_id, intent.league_id, intent.platform) == (BUYER, L, "sleeper")
    assert (intent.tier, intent.product_id, intent.paid_annual_count) == (tier, product, paid)
    assert intent.id == quote["intent_id"] and intent.expires_at == quote["expires_at"]
    assert intent.consumed_at is None
    assert w.events(eng, "league_pass_quote_viewed") == [
        (BUYER, {"tier": tier, "platform": "sleeper", "teams": 12}, L)]
