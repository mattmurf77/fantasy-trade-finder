"""League pass bind, re-point, rollover — docs/plans/monetization/league-pass/lld.md
§2.4, §3.3–3.4, §5, §10, §11; prd R16–R23, R36–R39.

Covers:
  * the webhook binds from the buyer's newest usable intent (R18) and
    consumes it; no intent, an expired one, a cheaper product than the
    snapshot (R20) or the flag off leave the pass unbound while the buyer
    keeps pro; a renewal changes nothing;
  * create_intent refusals in order (not_member, league_not_allowed,
    already_covered, already_buyer, refund_blocked);
  * one active pass per league and per buyer (R23), including two buyers
    racing for one league (§10: the first bind wins);
  * the manual bind (R19) with a fresh tier (tier_mismatch);
  * the re-point cooldown (R21); a Sleeper rollover moves the pass without
    using it (R22) and needs the buyer in the new league;
  * TRANSFER re-keys the pass to a member, else releases it;
  * expiry / refund end the pass and a refund blocks a new intent (R36);
  * comp and end (R39); account deletion releases and anonymizes (R38);
  * upsert_league stores Sleeper's previous_league_id ("0" = none).

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


def _paid_mates(eng, n, league=L):
    with eng.begin() as conn:
        for i in range(n):
            uid = f"paid_{league}_{i}"
            w.member(conn, league, uid)
            w.ent_row(conn, uid, product="ftf_pro_annual", source="apple_iap", period="NORMAL")


# ── webhook bind ────────────────────────────────────────────────────────────

def test_the_webhook_binds_from_the_intent_and_consumes_it(eng):
    quote = lp.create_intent(BUYER, L)
    _rc("buy1", "INITIAL_PURCHASE", product=quote["product_id"])
    [p] = _active(eng)
    assert (p["origin"], p["buyer_user_id"], p["league_id"], p["platform"], p["tier"]) == (
        "purchase", BUYER, L, "sleeper", 0)
    assert p["product_id"] == "ftf_league_annual"
    with eng.connect() as conn:
        intent = conn.execute(select(db_module.league_pass_intents_table)).fetchone()
    assert intent.consumed_event_id == "buy1" and intent.consumed_at == p["bound_at"]
    assert w.events(eng, "league_pass_bound") == [
        (BUYER, {"origin": "purchase", "tier": 0, "platform": "sleeper", "via": "webhook"}, L)]
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


def test_a_cheaper_product_than_the_snapshot_is_not_bound(eng, caplog):
    """R20: the quote was full price (no paid leaguemates); a t2 purchase
    cannot bind there."""
    assert lp.create_intent(BUYER, L)["tier"] == 0
    with caplog.at_level(logging.WARNING, logger="backend.league_pass"):
        _rc("buy1", "INITIAL_PURCHASE", product="ftf_league_annual_t2")
    assert w.passes(eng) == []
    assert "reason=tier_mismatch" in caplog.text
    assert entl.get_entitlements(BUYER)["pro"] is True


def test_a_dearer_product_than_the_snapshot_binds(eng):
    _paid_mates(eng, 3)
    assert lp.create_intent(BUYER, L)["tier"] == 2
    _rc("buy1", "INITIAL_PURCHASE", product="ftf_league_annual_t1")
    [p] = _active(eng)
    assert p["tier"] == 1


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
    assert lp.create_intent(MATE, L)["tier"] == 0
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
    assert (p["league_id"], p["status"], p["tier"]) == (L, "active", 0)
    assert w.events(eng, "league_pass_bound")[-1][1]["via"] == "manual"
    assert _refused(lp.bind, BUYER, L2) == "already_buyer"


def test_manual_bind_recomputes_the_tier(eng):
    """§10: a discounted product bought with no intent; a league that no
    longer qualifies is refused with tier_mismatch."""
    _rc("buy1", "INITIAL_PURCHASE", product="ftf_league_annual_t2")
    assert _refused(lp.bind, BUYER, L) == "tier_mismatch"
    _paid_mates(eng, 3, league=L2)
    assert lp.bind(BUYER, L2)["tier"] == 2


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
    assert (p["origin"], p["buyer_user_id"], p["note"], p["tier"]) == ("comp", None, "beta league", None)
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
