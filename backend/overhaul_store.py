"""Team overhaul persistence — SQLAlchemy Core over the five §4 tables.

JSON columns are json.dumps'd Text; timestamps ISO UTC via database._now().
`database.engine` is read at call time so tests can patch it. Reservation
claims are all-or-nothing; attempt transitions are compare-and-swap on
`state` and never regress a terminal state (overhaul_service.can_transition).
"""
from __future__ import annotations

import json

from sqlalchemy import and_, select, update, insert
from sqlalchemy.exc import IntegrityError

from . import database as db
from . import overhaul_service as service

T_OVERHAULS = db.overhauls_table
T_OFFERS = db.overhaul_offers_table
T_ROADMAPS = db.overhaul_roadmaps_table
T_ATTEMPTS = db.overhaul_attempts_table
T_RESERVATIONS = db.overhaul_reservations_table


class ReservationConflict(Exception):
    def __init__(self, asset_ids):
        super().__init__("asset_reserved")
        self.asset_ids = sorted(set(asset_ids))


def _dumps(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _loads(text, default=None):
    if text is None:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default


def _rows(result) -> list[dict]:
    return [dict(r._mapping) for r in result]


# ---------------------------------------------------------------------------
# overhauls
# ---------------------------------------------------------------------------

def _overhaul(row: dict | None) -> dict | None:
    if row is None:
        return None
    out = dict(row)
    out["settings"] = _loads(row.get("settings_json"), service.default_settings())
    out["snapshot"] = _loads(row.get("snapshot_json"))
    out["recovery"] = _loads(row.get("recovery_json"))
    out["generation"] = _loads(row.get("generation_json"))
    return out


def create_overhaul(*, account_user_id, league_user_id, league_id, platform, scoring_format,
                    client_key, settings, snapshot, recovery) -> dict:
    now = db._now()
    row = {"overhaul_id": service.new_id("ovh_"), "account_user_id": str(account_user_id),
           "league_user_id": str(league_user_id), "league_id": str(league_id),
           "platform": str(platform), "scoring_format": str(scoring_format), "status": "setup",
           "revision": 1, "client_key": client_key, "settings_json": _dumps(settings),
           "snapshot_json": _dumps(snapshot) if snapshot is not None else None,
           "recovery_json": _dumps(recovery) if recovery is not None else None,
           "generation_json": None, "selected_roadmap_id": None,
           "created_at": now, "updated_at": now}
    with db.engine.begin() as conn:
        conn.execute(insert(T_OVERHAULS).values(**row))
    return _overhaul(row)


def get_overhaul(overhaul_id: str) -> dict | None:
    with db.engine.connect() as conn:
        row = conn.execute(select(T_OVERHAULS).where(T_OVERHAULS.c.overhaul_id == str(overhaul_id))).fetchone()
    return _overhaul(dict(row._mapping)) if row else None


def find_active(account_user_id: str, league_id: str) -> dict | None:
    with db.engine.connect() as conn:
        row = conn.execute(select(T_OVERHAULS)
                           .where(T_OVERHAULS.c.account_user_id == str(account_user_id),
                                  T_OVERHAULS.c.league_id == str(league_id),
                                  T_OVERHAULS.c.status != "archived")
                           .order_by(T_OVERHAULS.c.id.desc()).limit(1)).fetchone()
    return _overhaul(dict(row._mapping)) if row else None


def find_by_client_key(account_user_id: str, league_id: str, client_key: str) -> dict | None:
    with db.engine.connect() as conn:
        row = conn.execute(select(T_OVERHAULS)
                           .where(T_OVERHAULS.c.account_user_id == str(account_user_id),
                                  T_OVERHAULS.c.league_id == str(league_id),
                                  T_OVERHAULS.c.client_key == str(client_key))
                           .order_by(T_OVERHAULS.c.id.desc()).limit(1)).fetchone()
    return _overhaul(dict(row._mapping)) if row else None


def update_overhaul(overhaul_id: str, **fields) -> None:
    values = {}
    for key, value in fields.items():
        if key in ("settings", "snapshot", "recovery", "generation"):
            values[key + "_json"] = _dumps(value) if value is not None else None
        else:
            values[key] = value
    values["updated_at"] = db._now()
    with db.engine.begin() as conn:
        conn.execute(update(T_OVERHAULS).where(T_OVERHAULS.c.overhaul_id == str(overhaul_id)).values(**values))


# ---------------------------------------------------------------------------
# offers
# ---------------------------------------------------------------------------

def _offer(row: dict, *, include_evidence=False) -> dict:
    card = _loads(row.get("card_json"), {})
    out = {"offer_id": row["offer_id"], "overhaul_id": row["overhaul_id"], "revision": row["revision"],
           "package_hash": row["package_hash"], "is_recovery": bool(row.get("is_recovery")),
           "decision": row.get("decision") or "undecided", "availability": row.get("availability") or "fresh",
           "counterparty_user_id": row["counterparty_user_id"],
           "counterparty_username": row.get("counterparty_username"),
           "give_ids": _loads(row.get("give_ids_json"), []), "receive_ids": _loads(row.get("receive_ids_json"), []),
           "card": card, "score": service.offer_score(card), "decided_at": row.get("decided_at"),
           "decision_client_key": row.get("decision_client_key"), "created_at": row.get("created_at")}
    if include_evidence:
        out["evidence"] = _loads(row.get("evidence_json"))
    return out


def list_offers(overhaul_id: str) -> list[dict]:
    with db.engine.connect() as conn:
        rows = _rows(conn.execute(select(T_OFFERS).where(T_OFFERS.c.overhaul_id == str(overhaul_id))
                                  .order_by(T_OFFERS.c.id.asc())))
    return [_offer(r) for r in rows]


def insert_offer(*, overhaul_id, revision, package_hash, counterparty_user_id, counterparty_username,
                 give_ids, receive_ids, card, evidence, is_recovery) -> dict | None:
    """Insert one offer; None when (overhaul_id, package_hash) already exists."""
    offer_id = service.new_id("ovh_")
    card = dict(card, offer_id=offer_id)
    row = {"offer_id": offer_id, "overhaul_id": str(overhaul_id), "revision": int(revision),
           "package_hash": package_hash, "counterparty_user_id": str(counterparty_user_id),
           "counterparty_username": counterparty_username,
           "give_ids_json": _dumps([str(a) for a in give_ids]),
           "receive_ids_json": _dumps([str(a) for a in receive_ids]),
           "card_json": _dumps(card), "evidence_json": _dumps(evidence) if evidence is not None else None,
           "is_recovery": 1 if is_recovery else 0, "decision": "undecided", "decided_at": None,
           "decision_client_key": None, "availability": "fresh", "created_at": db._now()}
    try:
        with db.engine.begin() as conn:
            conn.execute(insert(T_OFFERS).values(**row))
    except IntegrityError:
        return None
    return _offer(row)


def set_decision(offer_id: str, decision: str, client_key: str | None) -> None:
    with db.engine.begin() as conn:
        conn.execute(update(T_OFFERS).where(T_OFFERS.c.offer_id == str(offer_id))
                     .values(decision=decision, decided_at=db._now(), decision_client_key=client_key))


def mark_stale(overhaul_id: str, offer_ids) -> None:
    ids = [str(o) for o in offer_ids]
    if not ids:
        return
    with db.engine.begin() as conn:
        conn.execute(update(T_OFFERS).where(T_OFFERS.c.overhaul_id == str(overhaul_id),
                                            T_OFFERS.c.offer_id.in_(ids)).values(availability="stale"))


def refresh_offer(offer_id: str, revision: int) -> None:
    """A regenerated card collided with this stale undecided row: re-surface it."""
    with db.engine.begin() as conn:
        conn.execute(update(T_OFFERS).where(T_OFFERS.c.offer_id == str(offer_id))
                     .values(availability="fresh", revision=int(revision)))


def mark_undecided_stale(overhaul_id: str) -> None:
    with db.engine.begin() as conn:
        conn.execute(update(T_OFFERS).where(T_OFFERS.c.overhaul_id == str(overhaul_id),
                                            T_OFFERS.c.decision == "undecided").values(availability="stale"))


# ---------------------------------------------------------------------------
# roadmaps
# ---------------------------------------------------------------------------

def _roadmap(row: dict) -> dict:
    return {"roadmap_id": row["roadmap_id"], "overhaul_id": row["overhaul_id"], "version": row["version"],
            "revision": row["revision"], "packages": _loads(row.get("packages_json"), []),
            "compat": _loads(row.get("compat_json"), {}), "summary": _loads(row.get("summary_json"), {}),
            "is_current": bool(row.get("is_current")), "created_at": row.get("created_at")}


def insert_roadmap(*, overhaul_id, roadmap_id, version, revision, packages, compat, summary) -> dict:
    row = {"roadmap_id": roadmap_id, "overhaul_id": str(overhaul_id), "version": int(version),
           "revision": int(revision), "packages_json": _dumps(packages), "compat_json": _dumps(compat),
           "summary_json": _dumps(summary), "is_current": 1, "created_at": db._now()}
    with db.engine.begin() as conn:
        if version > 1:
            conn.execute(update(T_ROADMAPS).where(T_ROADMAPS.c.roadmap_id == roadmap_id).values(is_current=0))
        conn.execute(insert(T_ROADMAPS).values(**row))
    return _roadmap(row)


def retire_roadmaps(overhaul_id: str) -> None:
    with db.engine.begin() as conn:
        conn.execute(update(T_ROADMAPS).where(T_ROADMAPS.c.overhaul_id == str(overhaul_id)).values(is_current=0))


def current_roadmaps(overhaul_id: str) -> list[dict]:
    with db.engine.connect() as conn:
        rows = _rows(conn.execute(select(T_ROADMAPS).where(T_ROADMAPS.c.overhaul_id == str(overhaul_id),
                                                            T_ROADMAPS.c.is_current == 1)
                                  .order_by(T_ROADMAPS.c.id.asc())))
    return [_roadmap(r) for r in rows]


def get_roadmap(overhaul_id: str, roadmap_id: str) -> dict | None:
    with db.engine.connect() as conn:
        row = conn.execute(select(T_ROADMAPS).where(T_ROADMAPS.c.overhaul_id == str(overhaul_id),
                                                    T_ROADMAPS.c.roadmap_id == str(roadmap_id),
                                                    T_ROADMAPS.c.is_current == 1)
                           .order_by(T_ROADMAPS.c.version.desc()).limit(1)).fetchone()
    return _roadmap(dict(row._mapping)) if row else None


# ---------------------------------------------------------------------------
# attempts
# ---------------------------------------------------------------------------

def _attempt(row: dict) -> dict:
    out = dict(row)
    out["error"] = _loads(row.get("error_json"))
    out.pop("error_json", None)
    out.pop("id", None)
    return out


def insert_attempts(rows: list[dict]) -> None:
    if not rows:
        return
    now = db._now()
    with db.engine.begin() as conn:
        for row in rows:
            conn.execute(insert(T_ATTEMPTS).values(
                attempt_id=row["attempt_id"], batch_id=row["batch_id"], overhaul_id=row["overhaul_id"],
                roadmap_id=row["roadmap_id"], roadmap_version=int(row["roadmap_version"]),
                package_id=row["package_id"], tier=int(row["tier"]), offer_id=row["offer_id"],
                idempotency_key=row["idempotency_key"], request_hash=row["request_hash"],
                state=row.get("state", "queued"), state_source=row.get("state_source", "server"),
                provider_transaction_id=None, proposal_event_id=row.get("proposal_event_id"),
                error_json=None, created_at=now, updated_at=now, observed_at=None))


def list_attempts(overhaul_id: str) -> list[dict]:
    with db.engine.connect() as conn:
        rows = _rows(conn.execute(select(T_ATTEMPTS).where(T_ATTEMPTS.c.overhaul_id == str(overhaul_id))
                                  .order_by(T_ATTEMPTS.c.id.asc())))
    return [_attempt(r) for r in rows]


def get_attempt(overhaul_id: str, attempt_id: str) -> dict | None:
    with db.engine.connect() as conn:
        row = conn.execute(select(T_ATTEMPTS).where(T_ATTEMPTS.c.overhaul_id == str(overhaul_id),
                                                    T_ATTEMPTS.c.attempt_id == str(attempt_id))).fetchone()
    return _attempt(dict(row._mapping)) if row else None


def batch_by_key(overhaul_id: str, idempotency_key: str) -> list[dict]:
    with db.engine.connect() as conn:
        rows = _rows(conn.execute(select(T_ATTEMPTS).where(T_ATTEMPTS.c.overhaul_id == str(overhaul_id),
                                                            T_ATTEMPTS.c.idempotency_key == str(idempotency_key))
                                  .order_by(T_ATTEMPTS.c.id.asc())))
    return [_attempt(r) for r in rows]


def transition_attempt(attempt_id: str, expected: str, new_state: str, *, source: str,
                       error=None, provider_transaction_id=None, observed=False) -> bool:
    """Compare-and-swap `state`; False when the row moved or the move is illegal."""
    if not service.can_transition(expected, new_state):
        return False
    now = db._now()
    values = {"state": new_state, "state_source": source, "updated_at": now}
    if error is not None:
        values["error_json"] = _dumps(error)
    if provider_transaction_id is not None:
        values["provider_transaction_id"] = str(provider_transaction_id)
    if observed:
        values["observed_at"] = now
    with db.engine.begin() as conn:
        result = conn.execute(update(T_ATTEMPTS)
                              .where(T_ATTEMPTS.c.attempt_id == str(attempt_id), T_ATTEMPTS.c.state == expected)
                              .values(**values))
    return result.rowcount == 1


# ---------------------------------------------------------------------------
# reservations
# ---------------------------------------------------------------------------

def active_reservations(league_id: str, seller_user_id: str) -> list[dict]:
    with db.engine.connect() as conn:
        rows = _rows(conn.execute(select(T_RESERVATIONS).where(T_RESERVATIONS.c.league_id == str(league_id),
                                                                T_RESERVATIONS.c.seller_user_id == str(seller_user_id),
                                                                T_RESERVATIONS.c.active == 1)))
    return rows


def claim_reservations(*, league_id, seller_user_id, claims, overhaul_id, batch_id) -> None:
    """All-or-nothing claim. `claims` = [(asset_id, package_id), ...].

    Raises ReservationConflict listing every asset already actively reserved
    (by any overhaul in this league for this seller); nothing is written.
    """
    wanted = {str(a): str(p) for a, p in claims}
    if not wanted:
        return
    now = db._now()
    with db.engine.begin() as conn:
        taken = conn.execute(select(T_RESERVATIONS.c.asset_id)
                             .where(T_RESERVATIONS.c.league_id == str(league_id),
                                    T_RESERVATIONS.c.seller_user_id == str(seller_user_id),
                                    T_RESERVATIONS.c.active == 1,
                                    T_RESERVATIONS.c.asset_id.in_(list(wanted)))).fetchall()
        if taken:
            raise ReservationConflict([r[0] for r in taken])
        try:
            for asset_id, package_id in wanted.items():
                conn.execute(insert(T_RESERVATIONS).values(
                    league_id=str(league_id), seller_user_id=str(seller_user_id), asset_id=asset_id,
                    overhaul_id=str(overhaul_id), package_id=package_id, batch_id=str(batch_id),
                    active=1, created_at=now, released_at=None))
        except IntegrityError as exc:
            # The unique constraint is the backstop for a concurrent claim.
            raise ReservationConflict(list(wanted)) from exc


def release_reservations(*, overhaul_id, package_id=None) -> int:
    cond = [T_RESERVATIONS.c.overhaul_id == str(overhaul_id), T_RESERVATIONS.c.active == 1]
    if package_id is not None:
        cond.append(T_RESERVATIONS.c.package_id == str(package_id))
    with db.engine.begin() as conn:
        result = conn.execute(update(T_RESERVATIONS).where(and_(*cond))
                              .values(active=None, released_at=db._now()))
    return result.rowcount
