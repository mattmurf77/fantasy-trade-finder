"""Revised-offer cards (offer-learnings WS8, R2 treatment A plus the operator's twist).

Behind flag ``trade.next_move`` (default off). Off, ``build`` returns ``[]``
before reading anything.

Scope block: docs/plans/offer-learnings/scope-revised-offer-cards.md

When the user SENT a trade (through the app, or in Sleeper directly with the
import consent on) and Sleeper shows it

  * declined by the other manager (``trade_offer_outcomes.status ==
    'declined'``)                                     -> a REVISION: the same
    asked-for pieces, the same size, one offered piece swapped for a slightly
    more valuable one from the user's roster (``trade_next_move``'s
    ``swap_in_give``, 5-15% of the trade's market value);
  * countered, and the user declined that counter (``status == 'countered'``
    and ``counter_status == 'declined'``)          -> a MIDDLE GROUND
    (``trade_next_move.propose_middle_ground``),

this module builds at most one card for it, proven by the engine's evaluator in
force, or nothing. Nothing is built for an offer that is pending, withdrawn,
lapsed, accepted, or whose counter is pending, accepted, withdrawn, lapsed or
countered back.

Once only. Each source offer gets one ``revised_offer_cards`` row the first
time a deck looks at it: ``active`` with the card's terms, or ``none`` when no
proven card exists. A row is never rebuilt, so the price never climbs. An
active card is re-proven by the evaluator on every deck build (same terms) and
served until the user acts on it: a pass or a like is a past decision, the
evaluator then answers ``previous_disposition`` and the row is retired
(``acted``); a card that no longer passes (a player moved) is retired
(``unavailable``). An offer whose terms are a revised card's terms is never
revised again (no revision of a revision). Only the sender's own rows are
read (``direction == 'sent'``); received offers never make a card.

Order: most recent decline first; at most ``CAP`` per deck; at most
``MAX_BUILDS`` new builds per deck (the rest wait for the next deck).

A leaf: database, flags, the evaluator and the next-move generator. Never
``server``. ``server._inject_revised_offer_cards`` calls ``build`` from the
deck worker.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from . import bakeoff_runner, database as db, feature_flags, trade_next_move as nm
from . import trade_service as ts
from .trade_narrative import revised_offer_line

FLAG = nm.FLAG
VERSION = "revised-offer-1"
CAP = 3
MAX_BUILDS = 6
SOURCE_WINDOW_DAYS = 30
TRADE_ID_PREFIX = "revised_"


def _parse(ts_):
    try:
        dt = datetime.fromisoformat(str(ts_))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _ids(raw) -> list[str]:
    try:
        v = json.loads(raw) if raw else []
    except (TypeError, ValueError):
        return []
    return [str(x) for x in v] if isinstance(v, list) else []


def _terms(raw) -> dict | None:
    try:
        v = json.loads(raw) if raw else None
    except (TypeError, ValueError):
        return None
    return v if isinstance(v, dict) else None


def sources(user_id: str, league_id: str, now: datetime) -> list[dict]:
    """The user's own sent offers that call for a card, newest decline first.
    Each: the outcome row plus ``kind`` (revision | middle_ground),
    ``declined_at``, ``give``, ``receive`` and, for a middle ground,
    ``counter_give`` / ``counter_receive``."""
    oldest = now - timedelta(days=SOURCE_WINDOW_DAYS)
    out = []
    for r in db.load_user_trade_offer_outcomes(user_id, league_id, "sleeper"):
        if (r.get("direction") or "sent") != "sent":
            continue
        if r["status"] == "declined":
            kind, at = "revision", _parse(r.get("status_at"))
        elif r["status"] == "countered" and r.get("counter_status") == "declined":
            kind, at = "middle_ground", _parse(r.get("counter_status_at"))
        else:
            continue
        if at is None or at < oldest:
            continue
        if _terms(r.get("extras_json")):
            continue                       # FAAB or a pick in an unknown shape
        give, receive = _ids(r.get("give_asset_ids")), _ids(r.get("receive_asset_ids"))
        if not give or not receive:
            continue
        item = {**r, "kind": kind, "declined_at": at, "give": give, "receive": receive}
        if kind == "middle_ground":
            terms = _terms(r.get("counter_terms_json")) or {}
            if set(terms) - {"give_asset_ids", "receive_asset_ids"}:
                continue                   # the counter carried FAAB or an unread pick
            item["counter_give"] = [str(x) for x in terms.get("give_asset_ids") or []]
            item["counter_receive"] = [str(x) for x in terms.get("receive_asset_ids") or []]
            if not item["counter_give"] or not item["counter_receive"]:
                continue
        out.append(item)
    out.sort(key=lambda s: (s["declined_at"], s["id"]), reverse=True)
    return out


def _target(context, receive_ids):
    """The league-mate holding every asked-for asset now, or None."""
    want = set(receive_ids)
    hits = [m for m in (getattr(context.get("league"), "members", None) or [])
            if m.user_id != context["user_id"] and want <= set(m.roster or ())]
    return hits[0] if len(hits) == 1 else None


def _card(league_id, context, member, give, receive):
    return ts.TradeCard("", str(league_id), context["user_id"], member.user_id,
                        member.username, list(give), list(receive), 0, 0, 0)


def _key(give, receive):
    return frozenset(give), frozenset(receive)


@dataclass
class _Built:
    card: object
    proof: object
    change: dict
    step_fraction: float


def _build_move(league_id, src, context, member) -> _Built | None:
    offer = _card(league_id, context, member, src["give"], src["receive"])
    if src["kind"] == "revision":
        move = nm.propose_revision(offer, context, step_min=nm.SWAP_STEP_MIN,
                                   step_max=nm.SWAP_STEP_MAX, kinds=(nm.SWAP,))
    else:
        counter = _card(league_id, context, member, src["counter_give"], src["counter_receive"])
        move = nm.propose_middle_ground(offer, counter, context)
    if move is None:
        return None
    return _Built(move.card, move.proof, dict(move.change), move.step_fraction)


def _reprove(league_id, row, context, member) -> tuple[object, object] | None | str:
    card = _card(league_id, context, member, _ids(row["give_asset_ids"]), _ids(row["receive_asset_ids"]))
    evaluate = bakeoff_runner.owner_evaluator(dict(context.get("config") or {}))
    proof = evaluate([card], **{**context, **nm._ORGANIC})[0]
    if proof.eligible:
        return card, proof
    return "acted" if proof.reason == "previous_disposition" else "unavailable"


def build(*, user_id: str, league_id: str, context: dict, name, now: datetime | None = None,
          cap: int = CAP) -> list:
    """Up to ``cap`` revised-offer cards for the deck, most recent decline
    first, each bound to its evaluator proof. ``name(asset_id)`` gives the
    display name of a player or pick for the card's line."""
    if not feature_flags.is_enabled(FLAG):
        return []
    now = now or datetime.now(timezone.utc)
    srcs = sources(user_id, league_id, now)
    if not srcs:
        return []
    rows = db.load_revised_offer_cards(user_id, league_id)
    by_outcome = {r["outcome_id"]: r for r in rows}
    revised_terms = {_key(_ids(r["give_asset_ids"]), _ids(r["receive_asset_ids"]))
                     for r in rows if r["status"] != "none"}
    now_iso = now.isoformat()
    shown, builds, shown_keys = [], 0, set()
    for src in srcs:
        if len(shown) >= cap:
            break
        if _key(src["give"], src["receive"]) in revised_terms:
            continue                        # never a revision of a revision
        member = _target(context, src["receive"])
        row = by_outcome.get(src["id"])
        if row is not None and row["status"] != "active":
            continue
        if member is None:
            if row is not None:
                db.retire_revised_offer_card(row["id"], "unavailable", now_iso)
            continue
        if row is None:
            if builds >= MAX_BUILDS:
                continue
            builds += 1
            built = _build_move(league_id, src, context, member)
            row = db.save_revised_offer_card({
                "user_id": str(user_id), "league_id": str(league_id), "outcome_id": src["id"],
                "kind": src["kind"], "status": "active" if built else "none",
                "give_asset_ids": json.dumps(built.card.give_player_ids) if built else None,
                "receive_asset_ids": json.dumps(built.card.receive_player_ids) if built else None,
                "change_json": json.dumps(built.change, sort_keys=True) if built else None,
                "step_fraction": built.step_fraction if built else None,
                "version": VERSION, "created_at": now_iso,
            })
            if built is None or row is None or row["status"] != "active":
                continue
            card, proof, change, fraction = built.card, built.proof, built.change, built.step_fraction
        else:
            again = _reprove(league_id, row, context, member)
            if isinstance(again, str):
                db.retire_revised_offer_card(row["id"], again, now_iso)
                continue
            card, proof = again
            terms = proof.as_dict()["market"]
            card.give_value, card.receive_value = terms["give"], terms["receive"]
            card.fairness_score = terms["ratio"]
            card.owner_evaluation = proof
            change, fraction = json.loads(row["change_json"] or "{}"), row["step_fraction"]
        shown_key = (_key(card.give_player_ids, card.receive_player_ids), card.target_user_id)
        if shown_key in shown_keys:
            continue                        # two declined offers, one card: shown once
        shown_keys.add(shown_key)
        card.trade_id = f"{TRADE_ID_PREFIX}{row['id']}"
        card.injected = True
        card.revised_offer = {
            "kind": src["kind"], "version": VERSION, "card_id": row["id"],
            "outcome_id": src["id"], "source": src.get("source") or "app",
            "step_fraction": round(float(fraction or 0), 4),
            "line": revised_offer_line(src["kind"], original_give=src["give"],
                                       original_receive=src["receive"],
                                       give=card.give_player_ids,
                                       receive=card.receive_player_ids, name=name),
        }
        shown.append(card)
    return shown
