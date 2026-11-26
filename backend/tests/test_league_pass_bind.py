"""League pass bind, re-point, rollover — docs/plans/monetization/league-pass/lld.md
§2.4, §3.3–3.4, §5, §10, §11; prd R16–R23, R36–R39.

Covers:
  * the webhook binds from the buyer's newest usable intent (R18) and
    consumes it; no intent, an expired one or the flag off leave the pass
    unbound while the buyer keeps pro; a renewal changes nothing;
  * the quote: the one product, ftf_league_annual, and
    league_pass_quote_viewed {platform, teams};
  * the one-month free trial (D-281 addendum 2026-11-24): a trial purchase
    binds and covers members like a paid one, converting changes nothing,
    and a cancelled trial's expiry ends coverage; no per-league trial limit;
  * create_intent refusals in order (not_member, league_not_allowed,
    already_covered, already_buyer, refund_blocked);
  * one active pass per league and per buyer (R23), including two buyers
    racing for one league (§10: the first bind wins);
  * the manual bind (R19);
  * the re-point cooldown (R21); a Sleeper rollover moves the pass without
    using it (R22) and needs the buyer in the new league;
  * TRANSFER re-keys the pass to a member, else releases it;
  * expiry / refund end the pass and a refund blocks a new intent (R36);
  * comp and end (R39); account deletion releases and anonymizes (R38);
  * upsert_league stores Sleeper's previous_league_id ("0" = none);
  * existing Pro buyers (operator 2026-11-25): a lifetime / promo / Founder
    grant holder buys, binds and keeps the grant when the pass ends (a grant
    never keeps a lapsed pass alive); an individual subscriber upgrades by
    each handled RevenueCat sequence; a downgrade ends the pass.

In-memory SQLite; flags patched on the league_pass module; billing events go
through the real entitlements projector.
"""

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select

import backend.database as db_module
import backend.entitlements as entl
import backend.league_pass as lp
from backend import accounts
from backend.tests.support import league_pass_world as w

L = "lg_bind"
L2 = "lg_bind_2"
BUYER = "bind_buyer"
MATE = "bind_mate"


@pytest.fixture()
def flag(monkeypatch):
    state = {"on": True}
    monkeypatch.setattr(lp, "is_enabled", lambda k: state["on"] and k == lp.FLAG)
    return state


@pytest.fixture()
def eng(monkeypatch, flag):
    engine = w.make_engine()
    monkeypatch.delenv(lp.ALLOWLIST_ENV, raising=False)
    with engine.begin() as conn:
        for lid in (L, L2):
            w.league(conn, lid, total_rosters=12)
            w.member(conn, lid, BUYER)
            w.member(conn, lid, MATE)
    with patch.object(db_module, "engine", engine):
        yield engine


def _ms(days):
    return (datetime.now(timezone.utc) + timedelta(days=days)).timestamp() * 1000


def _rc(eid, etype, product="ftf_league_annual", user=BUYER, **extra):
    ev = {"id": eid, "type": etype, "app_user_id": user, "product_id": product, **extra}
    if etype in ("INITIAL_PURCHASE", "RENEWAL"):
        ev.setdefault("expiration_at_ms", _ms(365))
    return entl.ingest_billing_event("revenuecat", eid, etype, ev,
                                     user_id=user, product_id=product)


def _active(eng):
    return [p for p in w.passes(eng) if p["status"] == "active"]


# ── webhook bind ────────────────────────────────────────────────────────────

def test_the_webhook_binds_from_the_intent_and_consumes_it(eng):
    quote = lp.create_intent(BUYER, L)
    _rc("buy1", "INITIAL_PURCHASE", product=quote["product_id"])
    [p] = _active(eng)
    assert (p["origin"], p["buyer_user_id"], p["league_id"], p["platform"]) == (
        "purchase", BUYER, L, "sleeper")
    assert p["product_id"] == "ftf_league_annual"
    with eng.connect() as conn:
        intent = conn.execute(select(db_module.league_pass_intents_table)).fetchone()
    assert intent.consumed_event_id == "buy1" and intent.consumed_at == p["bound_at"]
    assert w.events(eng, "league_pass_bound") == [
        (BUYER, {"origin": "purchase", "platform": "sleeper", "via": "webhook"}, L)]
    assert lp.covers(MATE, L).role == "member"
    # A renewal changes nothing (lld §3.4 step 1).
    _rc("buy2", "RENEWAL", product=quote["product_id"])
    assert len(w.passes(eng)) == 1


def test_no_intent_leaves_the_pass_unbound_and_the_buyer_pro(eng, caplog):
    with caplog.at_level(logging.WARNING, logger="backend.league_pass"):
        _rc("buy1", "INITIAL_PURCHASE")
    assert w.passes(eng) == []
    assert entl.get_entitlements(BUYER)["pro"] is True
    assert "LEAGUE-PASS-UNBOUND user=bind_buyer reason=no_intent" in caplog.text


def test_an_expired_intent_is_not_used(eng):
    lp.create_intent(BUYER, L)
    with eng.begin() as conn:
        conn.execute(db_module.league_pass_intents_table.update().values(expires_at=w.iso(-0.01)))
    _rc("buy1", "INITIAL_PURCHASE")
    assert w.passes(eng) == []


def test_the_newest_usable_intent_counts(eng):
    lp.create_intent(BUYER, L)
    lp.create_intent(BUYER, L2)
    _rc("buy1", "INITIAL_PURCHASE")
    assert [p["league_id"] for p in _active(eng)] == [L2]


def test_the_quote_is_the_one_product(eng):
    """A paid annual leaguemate changes nothing: there are no price tiers."""
    with eng.begin() as conn:
        w.member(conn, L, "paid_mate")
        w.ent_row(conn, "paid_mate", product="ftf_pro_annual", source="apple_iap",
                  period="NORMAL")
    quote = lp.create_intent(BUYER, L)
    assert set(quote) == {"intent_id", "product_id", "teams", "expires_at"}
    assert (quote["product_id"], quote["teams"]) == ("ftf_league_annual", 12)
    with eng.connect() as conn:
        intent = conn.execute(select(db_module.league_pass_intents_table)).fetchone()
    assert (intent.product_id, intent.league_id, intent.platform) == (
        "ftf_league_annual", L, "sleeper")
    assert w.events(eng, "league_pass_quote_viewed") == [
        (BUYER, {"platform": "sleeper", "teams": 12}, L)]


# ── the one-month free trial ────────────────────────────────────────────────

def _trial(eid, user=BUYER, days=30):
    return _rc(eid, "INITIAL_PURCHASE", user=user, period_type="TRIAL",
               expiration_at_ms=_ms(days))


def test_a_trial_purchase_binds_and_covers_members(eng):
    lp.create_intent(BUYER, L)
    assert _trial("trial1")["projected"] is True
    [p] = _active(eng)
    assert (p["buyer_user_id"], p["league_id"], p["product_id"]) == (
        BUYER, L, "ftf_league_annual")
    ents = entl.get_entitlements(BUYER)
    assert ents["pro"] is True and ents["sources"] == ["league_pass_iap"]
    cov = lp.covers(MATE, L)
    assert cov.role == "member" and cov.covered_until < w.iso(31)
    assert lp.covers(BUYER, L).role == "buyer"
    # Converting to paid is a RENEWAL: the same pass, a later expiry.
    _rc("conv1", "RENEWAL", period_type="NORMAL")
    assert [x["id"] for x in _active(eng)] == [p["id"]]
    assert lp.covers(MATE, L).covered_until > w.iso(300)


def test_a_cancelled_trial_ends_coverage_at_expiry(eng):
    lp.create_intent(BUYER, L)
    _trial("trial1")
    _rc("cancel1", "CANCELLATION", period_type="TRIAL")   # auto-renew off: no-op
    assert lp.covers(MATE, L) is not None
    assert lp.buyer_view(BUYER)["pass"]["will_renew"] is False
    _rc("exp1", "EXPIRATION", period_type="TRIAL")
    assert lp.covers(MATE, L) is None and lp.covers(BUYER, L) is None
    [p] = w.passes(eng)
    assert (p["status"], p["release_reason"]) == ("ended", "ended")
    assert w.events(eng, "league_pass_ended") == [(BUYER, {"reason": "ended"}, L)]
    assert entl.get_entitlements(BUYER)["pro"] is False


def test_a_lapsed_trial_stops_covering_before_its_expiration_event(eng):
    """The row's expires_at is read-time truth: coverage ends at the trial's
    end even if EXPIRATION is late."""
    lp.create_intent(BUYER, L)
    _trial("trial1")
    with eng.begin() as conn:
        conn.execute(db_module.entitlements_table.update().values(expires_at=w.iso(-0.01)))
    assert lp.covers(MATE, L) is None


def test_trials_chain_with_no_limit(eng):
    """Operator 2026-11-24: no server limit on trials per league. After one
    member's trial expires, another member's trial binds the same league."""
    lp.create_intent(BUYER, L)
    _trial("trial1")
    _rc("exp1", "EXPIRATION", period_type="TRIAL")
    lp.create_intent(MATE, L)
    _trial("trial2", user=MATE)
    [p] = _active(eng)
    assert (p["buyer_user_id"], p["league_id"]) == (MATE, L)
    assert lp.covers(BUYER, L).role == "member"


def test_flag_off_projects_pro_but_never_binds(eng, flag):
    lp.create_intent(BUYER, L)
    flag["on"] = False
    _rc("buy1", "INITIAL_PURCHASE")
    assert w.passes(eng) == []
    assert entl.get_entitlements(BUYER)["sources"] == ["league_pass_iap"]


def test_the_webhook_rechecks_membership(eng, caplog):
    lp.create_intent(BUYER, L)
    with eng.begin() as conn:
        conn.execute(db_module.league_members_table.delete().where(
            db_module.league_members_table.c.user_id == BUYER))
    with caplog.at_level(logging.WARNING, logger="backend.league_pass"):
        _rc("buy1", "INITIAL_PURCHASE")
    assert w.passes(eng) == [] and "reason=not_member" in caplog.text


# ── intent refusals ─────────────────────────────────────────────────────────

def _refused(fn, *args):
    with pytest.raises(lp.Refused) as e:
        fn(*args)
    return e.value.reason


def test_intent_refusals_in_order(eng, monkeypatch):
    with eng.begin() as conn:
        w.user(conn, "outsider")
    assert _refused(lp.create_intent, "outsider", L) == "not_member"
    assert _refused(lp.create_intent, BUYER, "no_such_league") == "not_member"
    monkeypatch.setenv(lp.ALLOWLIST_ENV, L2)
    assert _refused(lp.create_intent, BUYER, L) == "league_not_allowed"
    monkeypatch.delenv(lp.ALLOWLIST_ENV)
    with eng.begin() as conn:
        w.pass_row(conn, L, origin="comp", comp_days=10)
    assert _refused(lp.create_intent, BUYER, L) == "already_covered"


def test_one_pass_per_buyer(eng):
    lp.create_intent(BUYER, L)
    _rc("buy1", "INITIAL_PURCHASE")
    assert _refused(lp.create_intent, BUYER, L2) == "already_buyer"
    assert _refused(lp.create_intent, MATE, L) == "already_covered"


def test_two_buyers_racing_for_one_league_first_bind_wins(eng, caplog):
    """§10: both quoted before either purchase; the second stays unbound."""
    lp.create_intent(BUYER, L)
    lp.create_intent(MATE, L)
    _rc("buy1", "INITIAL_PURCHASE")
    with caplog.at_level(logging.WARNING, logger="backend.league_pass"):
        _rc("buy2", "INITIAL_PURCHASE", user=MATE)
    assert [(p["buyer_user_id"], p["league_id"]) for p in _active(eng)] == [(BUYER, L)]
    assert "user=bind_mate reason=already_covered" in caplog.text
    assert entl.get_entitlements(MATE)["pro"] is True


def test_the_partial_unique_indexes_hold(eng):
    from sqlalchemy.exc import IntegrityError
    with eng.begin() as conn:
        w.pass_row(conn, L, buyer=BUYER)
    with pytest.raises(IntegrityError), eng.begin() as conn:
        w.pass_row(conn, L, origin="comp", comp_days=3)
    with pytest.raises(IntegrityError), eng.begin() as conn:
        w.pass_row(conn, L2, buyer=BUYER)
    with eng.begin() as conn:         # released rows never collide
        w.pass_row(conn, L, buyer=BUYER, status="released")
        w.pass_row(conn, L2, origin="comp", comp_days=3)


def test_a_lapsed_pass_never_blocks_its_league(eng):
    with eng.begin() as conn:
        w.ent_row(conn, BUYER, expires_days=-1)
        old = w.pass_row(conn, L, buyer=BUYER)
    assert lp.create_intent(MATE, L)["product_id"] == "ftf_league_annual"
    assert [p["release_reason"] for p in w.passes(eng) if p["id"] == old] == ["ended"]


# ── refund, expiry ──────────────────────────────────────────────────────────

def test_refund_ends_the_pass_and_blocks_a_new_intent(eng):
    lp.create_intent(BUYER, L)
    _rc("buy1", "INITIAL_PURCHASE")
    _rc("ref1", "REFUND")
    [p] = w.passes(eng)
    assert (p["status"], p["release_reason"]) == ("ended", "refund")
    assert w.events(eng, "league_pass_ended") == [(BUYER, {"reason": "refund"}, L)]
    assert _refused(lp.create_intent, BUYER, L2) == "refund_blocked"


def test_expiry_ends_the_pass(eng):
    lp.create_intent(BUYER, L)
    _rc("buy1", "INITIAL_PURCHASE")
    _rc("exp1", "EXPIRATION")
    assert [(p["status"], p["release_reason"]) for p in w.passes(eng)] == [("ended", "ended")]


# ── manual bind ─────────────────────────────────────────────────────────────

def test_manual_bind_for_an_unbound_pass(eng):
    assert _refused(lp.bind, BUYER, L) == "no_purchase"
    _rc("buy1", "INITIAL_PURCHASE")                    # no intent → unbound
    p = lp.bind(BUYER, L)
    assert (p["league_id"], p["status"]) == (L, "active")
    assert w.events(eng, "league_pass_bound")[-1][1]["via"] == "manual"
    assert _refused(lp.bind, BUYER, L2) == "already_buyer"


# ── re-point and rollover ───────────────────────────────────────────────────

def _bound(eng, *, days_ago):
    _rc("buy1", "INITIAL_PURCHASE")
    with eng.begin() as conn:
        return w.pass_row(conn, L, buyer=BUYER, bound_days=-days_ago)


def test_repoint_cooldown(eng):
    _bound(eng, days_ago=1)
    with pytest.raises(lp.Refused) as e:
        lp.repoint(BUYER, L2)
    assert e.value.reason == "cooldown" and e.value.detail["can_repoint_at"] > w.iso(28)
    with eng.begin() as conn:
        conn.execute(db_module.league_passes_table.update().values(bound_at=w.iso(-31)))
    moved = lp.repoint(BUYER, L2)
    old, new = w.passes(eng)
    assert (old["status"], old["release_reason"]) == ("released", "repoint")
    assert (new["id"], new["league_id"], new["status"]) == (moved["id"], L2, "active")
    assert new["bound_at"] == old["released_at"]
    assert lp.covers(MATE, L2) is not None and lp.covers(MATE, L) is None
    assert _refused(lp.repoint, BUYER, L) == "cooldown"


def test_repoint_refusals(eng):
    assert _refused(lp.repoint, BUYER, L2) == "no_pass"
    _bound(eng, days_ago=40)
    with eng.begin() as conn:
        w.league(conn, "lg_not_mine")
        w.league(conn, "lg_taken")
        w.member(conn, "lg_taken", BUYER)
        w.pass_row(conn, "lg_taken", origin="comp", comp_days=5)
    assert _refused(lp.repoint, BUYER, "lg_not_mine") == "not_member"
    assert _refused(lp.repoint, BUYER, "lg_taken") == "already_covered"
    assert _refused(lp.repoint, BUYER, L) == "already_covered"


def test_rollover_moves_the_pass_without_using_the_cooldown(eng):
    _bound(eng, days_ago=40)
    with eng.begin() as conn:
        w.league(conn, "lg_2027")
        w.member(conn, "lg_2027", BUYER)
        w.member(conn, "lg_2027", MATE)
    assert lp.follow_rollover("lg_2027", L) is True
    old, new = w.passes(eng)
    assert (old["status"], old["release_reason"]) == ("released", "rollover")
    assert (new["league_id"], new["status"], new["platform"]) == ("lg_2027", "active", "sleeper")
    assert lp.covers(MATE, "lg_2027") is not None
    assert w.events(eng, "league_pass_bound")[-1][1]["via"] == "rollover"
    # The rollover's bind is not a re-point: the buyer may still move it now.
    assert lp.repoint(BUYER, L2)["league_id"] == L2


def test_a_recent_bind_still_rolls_over(eng):
    _bound(eng, days_ago=1)
    with eng.begin() as conn:
        w.league(conn, "lg_2027")
        w.member(conn, "lg_2027", BUYER)
    assert lp.follow_rollover("lg_2027", L) is True


def test_rollover_needs_the_buyer_in_the_new_league_and_the_flag(eng, flag):
    _bound(eng, days_ago=40)
    with eng.begin() as conn:
        w.league(conn, "lg_2027")
        w.member(conn, "lg_2027", MATE)
    assert lp.follow_rollover("lg_2027", L) is False
    with eng.begin() as conn:
        w.member(conn, "lg_2027", BUYER)
    assert lp.follow_rollover("lg_2027", None) is False
    assert lp.follow_rollover("lg_2027", "0") is False
    flag["on"] = False
    assert lp.follow_rollover("lg_2027", L) is False
    flag["on"] = True
    assert lp.follow_rollover("lg_2027", L) is True
    assert lp.follow_rollover("lg_2027", L) is False      # idempotent


def test_a_comp_pass_rolls_over_with_its_league(eng):
    with eng.begin() as conn:
        w.pass_row(conn, L, origin="comp", comp_days=9)
        w.league(conn, "lg_2027")
    assert lp.follow_rollover("lg_2027", L) is True
    assert [p["league_id"] for p in _active(eng)] == ["lg_2027"]


def test_upsert_league_stores_previous_league_id(eng):
    db_module.upsert_league("lg_new", BUYER, "N", "2027", [], [], platform="sleeper",
                            previous_league_id="lg_old")
    db_module.upsert_league("lg_zero", BUYER, "Z", "2027", [], [], previous_league_id="0")
    db_module.upsert_league("lg_new", MATE, "N", "2027", [], [])   # None keeps it
    with eng.connect() as conn:
        rows = dict(conn.execute(select(db_module.leagues_table.c.sleeper_league_id,
                                        db_module.leagues_table.c.previous_league_id)).all())
    assert rows["lg_new"] == "lg_old" and rows["lg_zero"] is None


# ── transfer ────────────────────────────────────────────────────────────────

def _transfer(eid, to):
    ev = {"id": eid, "type": "TRANSFER", "transferred_from": [BUYER], "transferred_to": [to],
          "product_id": "ftf_league_annual"}
    return entl.ingest_billing_event("revenuecat", eid, "TRANSFER", ev,
                                     user_id=None, product_id="ftf_league_annual")


def test_transfer_rekeys_the_pass_to_a_member(eng):
    lp.create_intent(BUYER, L)
    _rc("buy1", "INITIAL_PURCHASE")
    _transfer("t1", MATE)
    [p] = w.passes(eng)
    assert (p["buyer_user_id"], p["status"]) == (MATE, "active")
    assert lp.covers(MATE, L).role == "buyer"


def test_transfer_to_a_non_member_releases_the_pass(eng):
    lp.create_intent(BUYER, L)
    _rc("buy1", "INITIAL_PURCHASE")
    with eng.begin() as conn:
        w.user(conn, "elsewhere")
    _transfer("t1", "elsewhere")
    [p] = w.passes(eng)
    assert (p["status"], p["release_reason"]) == ("released", "transfer")


# ── comp, end ───────────────────────────────────────────────────────────────

def test_comp_and_end(eng):
    assert _refused(lp.comp, L, 0, None) == "bad_days"
    assert _refused(lp.comp, "no_such_league", 7, None) == "unknown_league"
    p = lp.comp(L, 7, "beta league")
    assert (p["origin"], p["buyer_user_id"], p["note"]) == ("comp", None, "beta league")
    assert lp.covers(MATE, L).covered_until == p["comp_expires_at"]
    assert _refused(lp.comp, L, 7, None) == "already_covered"
    assert _refused(lp.create_intent, BUYER, L) == "already_covered"
    assert lp.end(p["id"], "admin") is True
    assert lp.end(p["id"], "admin") is False
    assert lp.covers(MATE, L) is None
    assert w.events(eng, "league_pass_ended") == [("system:league_pass", {"reason": "admin"}, L)]


# ── account deletion ────────────────────────────────────────────────────────

def test_deleting_the_buyer_releases_and_anonymizes_the_pass(eng):
    lp.create_intent(BUYER, L)
    _rc("buy1", "INITIAL_PURCHASE")
    lp.create_intent(MATE, L2)
    counts = accounts.delete_user_data(BUYER)
    [p] = w.passes(eng)
    assert (p["status"], p["release_reason"]) == ("released", "deleted")
    assert p["buyer_user_id"] is None and p["buyer_account_id"] is None
    assert counts["league_passes_released"] == 1
    with eng.connect() as conn:
        intents = conn.execute(select(db_module.league_pass_intents_table.c.user_id)).scalars().all()
    assert intents == [MATE]
    assert lp.covers(MATE, L) is None
    assert ("system:league_pass", {"reason": "deleted"}, L) in w.events(eng, "league_pass_ended")


def test_export_carries_the_buyers_passes(eng):
    lp.create_intent(BUYER, L)
    _rc("buy1", "INITIAL_PURCHASE")
    tables = accounts.export_user_data(BUYER)["tables"]
    assert [r["league_id"] for r in tables["league_passes"]] == [L]
    assert [r["league_id"] for r in tables["league_pass_intents"]] == [L]


# ── existing Pro buyers (operator 2026-11-25) ───────────────────────────────
# A user who already holds pro can buy: (b) by a non-store grant (lifetime
# grant to existing users at launch, comp, promo, founder lifetime), and (a)
# by an individual subscription, for whom the pass is an App Store upgrade
# within the one subscription group. Coverage follows the league_pass_iap
# row only, never the buyer's other pro.

_GRANTS = {
    "lifetime_grant": dict(source="manual_grant", product=None, expires_days=None),
    "promo": dict(source="promo_referral", product=None, expires_days=30),
    "founder": dict(source="founder_iap", product="ftf_founder_lifetime", expires_days=None),
}


@pytest.mark.parametrize("grant", sorted(_GRANTS))
def test_a_granted_pro_user_buys_binds_and_keeps_the_grant_after_expiry(eng, grant):
    with eng.begin() as conn:
        w.ent_row(conn, BUYER, **_GRANTS[grant])
    assert entl.get_entitlements(BUYER)["pro"] is True
    lp.create_intent(BUYER, L)                       # pro is no refusal
    _rc("buy1", "INITIAL_PURCHASE")
    [p] = _active(eng)
    assert (p["buyer_user_id"], p["league_id"]) == (BUYER, L)
    assert lp.covers(MATE, L).role == "member"
    assert lp.covers(BUYER, L).role == "buyer"
    assert "league_pass_iap" in entl.get_entitlements(BUYER)["sources"]
    _rc("exp1", "EXPIRATION")
    assert lp.covers(MATE, L) is None and lp.covers(BUYER, L) is None
    [p] = w.passes(eng)
    assert (p["status"], p["release_reason"]) == ("ended", "ended")
    ents = entl.get_entitlements(BUYER)
    assert ents["pro"] is True and ents["sources"] == [_GRANTS[grant]["source"]]
    assert lp.buyer_view(BUYER) == {"pass": None, "unbound": False}


def test_a_lifetime_grant_never_keeps_a_lapsed_pass_alive(eng):
    """No EXPIRATION at all: the league row's expiry alone ends coverage."""
    with eng.begin() as conn:
        w.ent_row(conn, BUYER, source="manual_grant", product=None, expires_days=None)
    lp.create_intent(BUYER, L)
    _rc("buy1", "INITIAL_PURCHASE")
    with eng.begin() as conn:
        conn.execute(db_module.entitlements_table.update()
                     .where(db_module.entitlements_table.c.source == "league_pass_iap")
                     .values(expires_at=w.iso(-0.01)))
    assert lp.covers(MATE, L) is None and lp.covers(BUYER, L) is None
    assert lp.passes_for(MATE) == []
    assert entl.get_entitlements(BUYER)["pro"] is True
    # A grant is no purchase: the manual bind still wants a league row, and
    # the lapsed pass no longer blocks the league.
    assert _refused(lp.bind, BUYER, L2) == "no_purchase"
    assert lp.create_intent(MATE, L)["product_id"] == "ftf_league_annual"


def test_a_lifetime_grant_holders_refund_ends_the_pass_not_the_grant(eng):
    with eng.begin() as conn:
        w.ent_row(conn, BUYER, source="manual_grant", product=None, expires_days=None)
    lp.create_intent(BUYER, L)
    _rc("buy1", "INITIAL_PURCHASE")
    _rc("ref1", "REFUND")
    assert lp.covers(MATE, L) is None
    assert entl.get_entitlements(BUYER)["sources"] == ["manual_grant"]
    assert _refused(lp.create_intent, BUYER, L2) == "refund_blocked"


CHAIN = "otx-upgrade"


def _subscribe(product="ftf_pro_annual", **extra):
    _rc("sub1", "INITIAL_PURCHASE", product=product, original_transaction_id=CHAIN, **extra)


def _upgrade_pc(eid="pc1", old="ftf_pro_annual", **extra):
    extra.setdefault("expiration_at_ms", _ms(365))
    return _rc(eid, "PRODUCT_CHANGE", product=old, new_product_id="ftf_league_annual",
               original_transaction_id=CHAIN, **extra)


def _league(eid, etype):
    return _rc(eid, etype, original_transaction_id=CHAIN)


# Each plausible RevenueCat sequence for an App Store upgrade into the pass
# (none verified against the store).
_UPGRADES = {
    "product_change_only": lambda old: _upgrade_pc(old=old),
    "product_change_then_renewal": lambda old: (_upgrade_pc(old=old), _league("up2", "RENEWAL")),
    "product_change_then_initial": lambda old: (_upgrade_pc(old=old),
                                                _league("up2", "INITIAL_PURCHASE")),
    "renewal_only": lambda old: _league("up1", "RENEWAL"),
    "initial_purchase_only": lambda old: _league("up1", "INITIAL_PURCHASE"),
    "product_change_without_expiry_then_renewal": lambda old: (
        _upgrade_pc(old=old, expiration_at_ms=None), _league("up2", "RENEWAL")),
}


@pytest.mark.parametrize("old", ["ftf_pro_annual", "ftf_pro_monthly"])
@pytest.mark.parametrize("sequence", sorted(_UPGRADES))
def test_an_individual_subscriber_upgrades_into_a_bound_pass(eng, sequence, old):
    _subscribe(old, period_type="TRIAL" if old == "ftf_pro_monthly" else "NORMAL")
    lp.create_intent(BUYER, L)                       # a subscriber is no refusal
    _UPGRADES[sequence](old)
    [p] = _active(eng)
    assert (p["buyer_user_id"], p["league_id"], p["product_id"]) == (
        BUYER, L, "ftf_league_annual")
    assert w.events(eng, "league_pass_bound") == [
        (BUYER, {"origin": "purchase", "platform": "sleeper", "via": "webhook"}, L)]
    rows = {r["product_id"]: (r["source"], r["status"]) for r in entl.list_for_user(BUYER)}
    assert rows == {old: ("apple_iap", "expired"),
                    "ftf_league_annual": ("league_pass_iap", "active")}
    assert entl.get_entitlements(BUYER)["sources"] == ["league_pass_iap"]
    assert lp.covers(MATE, L).role == "member"
    assert lp.buyer_view(BUYER)["pass"]["league_id"] == L


def test_an_upgrade_without_an_intent_is_unbound_then_binds_manually(eng):
    _subscribe()
    _upgrade_pc()
    assert w.passes(eng) == [] and lp.buyer_view(BUYER)["unbound"] is True
    assert lp.bind(BUYER, L)["league_id"] == L


def test_a_downgrade_ends_the_pass_when_it_takes_effect(eng):
    _subscribe("ftf_league_annual")                  # a league buyer on CHAIN
    with eng.begin() as conn:                        # bound before the change
        w.pass_row(conn, L, buyer=BUYER)
    # Requesting the downgrade changes nothing: it waits for the renewal.
    _rc("pc1", "PRODUCT_CHANGE", product="ftf_league_annual",
        new_product_id="ftf_pro_annual", original_transaction_id=CHAIN,
        expiration_at_ms=_ms(200))
    assert lp.covers(MATE, L) is not None
    # The renewal into the individual plan ends the league row and the pass.
    _rc("dn1", "RENEWAL", product="ftf_pro_annual", original_transaction_id=CHAIN)
    assert lp.covers(MATE, L) is None and lp.covers(BUYER, L) is None
    [p] = w.passes(eng)
    assert (p["status"], p["release_reason"]) == ("ended", "ended")
    assert w.events(eng, "league_pass_ended") == [(BUYER, {"reason": "ended"}, L)]
    assert entl.get_entitlements(BUYER)["sources"] == ["apple_iap"]


def test_a_downgrade_with_no_chain_id_still_lapses_at_the_league_expiry(eng):
    _rc("sub1", "INITIAL_PURCHASE", expiration_at_ms=_ms(0.0001))
    with eng.begin() as conn:
        w.pass_row(conn, L, buyer=BUYER)
    _rc("dn1", "RENEWAL", product="ftf_pro_annual")
    with eng.begin() as conn:
        conn.execute(db_module.entitlements_table.update()
                     .where(db_module.entitlements_table.c.source == "league_pass_iap")
                     .values(expires_at=w.iso(-0.01)))
    assert lp.covers(MATE, L) is None
    assert entl.get_entitlements(BUYER)["sources"] == ["apple_iap"]
