"""Team overhaul — persistence (backend/overhaul_store.py).

Contract: docs/plans/team-overhaul/BUILD-CONTRACT.md §8. Covers: reservation
uniqueness across two overhauls (all-or-nothing, conflict lists the reserved
asset ids, release re-opens the asset); attempt compare-and-swap refuses
regressing `accepted` -> `proposed` and refuses a stale expected state; the
(overhaul_id, package_hash) uniqueness keeps a passed exact offer from being
resurrected by regeneration. Isolated in-memory SQLite engine.
"""
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine

from backend import database as db
from backend import overhaul_store as store


@pytest.fixture()
def eng():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    db.metadata.create_all(engine)
    with patch.object(db, "engine", engine):
        yield engine


def _overhaul(user="u1", league="L1", key="k1"):
    return store.create_overhaul(account_user_id=user, league_user_id=user, league_id=league, platform="sleeper",
                                 scoring_format="1qb_ppr", client_key=key, settings={"outlook": None},
                                 snapshot=None, recovery=None)


def test_reservation_uniqueness_across_two_overhauls(eng):
    """SABOTAGE: drop the pre-insert SELECT and the unique constraint."""
    one, two = _overhaul(key="k1"), _overhaul(key="k2")
    store.claim_reservations(league_id="L1", seller_user_id="u1", claims=[("A", "p1"), ("B", "p1")],
                             overhaul_id=one["overhaul_id"], batch_id="bt1")
    with pytest.raises(store.ReservationConflict) as exc:
        store.claim_reservations(league_id="L1", seller_user_id="u1", claims=[("B", "p2"), ("C", "p2")],
                                 overhaul_id=two["overhaul_id"], batch_id="bt2")
    assert exc.value.asset_ids == ["B"]
    # All-or-nothing: C was not written either.
    assert {r["asset_id"] for r in store.active_reservations("L1", "u1")} == {"A", "B"}
    # A different seller or league is independent.
    store.claim_reservations(league_id="L1", seller_user_id="u9", claims=[("B", "p")], overhaul_id="x", batch_id="b")
    store.claim_reservations(league_id="L2", seller_user_id="u1", claims=[("B", "p")], overhaul_id="x", batch_id="b")
    # Release re-opens the asset; released rows keep their history (active NULL).
    assert store.release_reservations(overhaul_id=one["overhaul_id"], package_id="p1") == 2
    assert store.active_reservations("L1", "u1") == []
    store.claim_reservations(league_id="L1", seller_user_id="u1", claims=[("B", "p2"), ("C", "p2")],
                             overhaul_id=two["overhaul_id"], batch_id="bt2")
    assert {r["asset_id"] for r in store.active_reservations("L1", "u1")} == {"B", "C"}


def test_attempt_cas_refuses_regression(eng):
    """SABOTAGE: remove the `state == expected` predicate or the can_transition guard."""
    row = _overhaul()
    store.insert_attempts([{"attempt_id": "at1", "batch_id": "bt1", "overhaul_id": row["overhaul_id"],
                            "roadmap_id": "rm1", "roadmap_version": 1, "package_id": "p1", "tier": 1,
                            "offer_id": "o1", "idempotency_key": "k", "request_hash": "h"}])
    assert store.transition_attempt("at1", "queued", "sending", source="server")
    assert store.transition_attempt("at1", "sending", "proposed", source="provider", provider_transaction_id="tx9", observed=True)
    # Stale expectation: the row already moved on.
    assert not store.transition_attempt("at1", "sending", "send_failed", source="provider")
    assert store.transition_attempt("at1", "proposed", "accepted", source="ownership_refresh", observed=True)
    # Terminal never regresses, even with the right expected state.
    assert not store.transition_attempt("at1", "accepted", "proposed", source="provider")
    got = store.get_attempt(row["overhaul_id"], "at1")
    assert got["state"] == "accepted" and got["provider_transaction_id"] == "tx9" and got["observed_at"]
    assert store.batch_by_key(row["overhaul_id"], "k")[0]["attempt_id"] == "at1"


def test_offer_hash_uniqueness_keeps_decisions(eng):
    row = _overhaul()
    kwargs = dict(overhaul_id=row["overhaul_id"], revision=1, package_hash="h1", counterparty_user_id="o1",
                  counterparty_username="One", give_ids=["A"], receive_ids=["X"], card={"trade_id": "t"},
                  evidence={"private": True}, is_recovery=False)
    first = store.insert_offer(**kwargs)
    assert first["card"]["offer_id"] == first["offer_id"]
    store.set_decision(first["offer_id"], "pass", "ck1")
    assert store.insert_offer(**dict(kwargs, revision=2)) is None      # regeneration cannot resurrect it
    offers = store.list_offers(row["overhaul_id"])
    assert len(offers) == 1 and offers[0]["decision"] == "pass" and "evidence" not in offers[0]
    store.mark_undecided_stale(row["overhaul_id"])
    assert store.list_offers(row["overhaul_id"])[0]["availability"] == "fresh"   # decided rows keep availability


def test_roadmap_versions_and_active_lookup(eng):
    row = _overhaul()
    v1 = store.insert_roadmap(overhaul_id=row["overhaul_id"], roadmap_id="rm1", version=1, revision=1,
                              packages=[], compat={}, summary={})
    v2 = store.insert_roadmap(overhaul_id=row["overhaul_id"], roadmap_id="rm1", version=2, revision=1,
                              packages=[{"package_id": "p"}], compat={}, summary={})
    assert store.get_roadmap(row["overhaul_id"], "rm1")["version"] == 2
    assert [r["version"] for r in store.current_roadmaps(row["overhaul_id"])] == [2]
    assert v1["version"] == 1 and v2["packages"] == [{"package_id": "p"}]
    assert store.find_active("u1", "L1")["overhaul_id"] == row["overhaul_id"]
    store.update_overhaul(row["overhaul_id"], status="archived")
    assert store.find_active("u1", "L1") is None
    assert store.find_by_client_key("u1", "L1", "k1")["overhaul_id"] == row["overhaul_id"]
