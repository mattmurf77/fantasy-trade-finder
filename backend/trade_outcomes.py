"""
backend/trade_outcomes.py — what happened at the provider to a trade the user
sent through the app (offer-learnings WS2 Part A, flag `trade.outcome_tracking`).

Scope block: docs/plans/offer-learnings/scope-trade-outcomes.md

A leaf: imports `database` only, never `server`. `server.py` owns the flag
checks and calls in from three seams: the confirmed Sleeper send
(`record_sent`), session init after the league's trade capture
(`reconcile_league`) and the daily tick (`tick`).

What is observable, and so what is written. The only outcome source the app
holds is Sleeper's PUBLIC completed-trade list, already captured into
`sleeper_trades`. From it:

  * the sent transaction id completed           -> 'accepted'
  * it did not, but the same two rosters completed a different two-team trade
    after the send                              -> 'completed_different_terms',
    with that trade's terms from the sender's side. An observed later trade
    between the same teams, NOT a confirmed counter; not terminal (if the
    original later completes, 'accepted' wins).
  * anything else                               -> stays 'sent'.

Declined, withdrawn, expired and unaccepted counters are visible only on
Sleeper's private GraphQL, which the app does not read; nothing here infers
them from silence.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from . import database as db

log = logging.getLogger(__name__)

PROVIDER_SLEEPER = "sleeper"
# The daily tick re-captures and reconciles leagues with an open offer sent in
# the last OUTCOME_WATCH_DAYS days, at most OUTCOME_SYNC_LEAGUE_BUDGET leagues
# per tick (each costs <=2 public `transactions/{leg}` reads in steady state).
# Older open offers are still reconciled at the league's session init.
OUTCOME_WATCH_DAYS = 30
OUTCOME_SYNC_LEAGUE_BUDGET = 50


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(ts):
    try:
        dt = datetime.fromisoformat(str(ts))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _loads(raw, default):
    try:
        v = json.loads(raw) if raw else default
    except (TypeError, ValueError):
        return default
    return v if isinstance(v, type(default)) else default


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def record_sent(*, user_id: str, league_id: str, transaction_id, my_roster_id,
                their_roster_id, give_asset_ids: list, receive_asset_ids: list,
                proposal_event_id=None, impression_id=None,
                provider: str = PROVIDER_SLEEPER) -> bool:
    """Write the 'sent' row for one confirmed send. Never raises: the send
    already succeeded. A send without a provider transaction id cannot be
    reconciled, so it is not recorded. Returns True when a row was created."""
    if not transaction_id:
        return False
    try:
        return db.save_trade_offer_outcome({
            "user_id":                 str(user_id),
            "league_id":               str(league_id),
            "provider":                provider,
            "provider_transaction_id": str(transaction_id),
            "proposal_event_id":       proposal_event_id,
            "impression_id":           impression_id,
            "my_roster_id":            _int(my_roster_id),
            "their_roster_id":         _int(their_roster_id),
            "give_asset_ids":          json.dumps([str(a) for a in give_asset_ids or []]),
            "receive_asset_ids":       json.dumps([str(a) for a in receive_asset_ids or []]),
            "sent_at":                 _now().isoformat(),
            "status":                  "sent",
            "source":                  "app",
            "direction":               "sent",
        })
    except Exception as err:
        log.warning("trade outcome record failed (non-fatal): %s", err)
        return False


def observed_terms(trade: dict, my_roster_id: int) -> dict:
    """A captured `sleeper_trades` row seen from `my_roster_id`'s side.

    `adds` is {player_id: receiving roster}, `drops` {player_id: giving
    roster}; picks carry `previous_owner_id` (giver) / `owner_id` (receiver)
    and `roster_id` (original owner); FAAB rows `sender` / `receiver`."""
    adds = _loads(trade.get("adds"), {})
    drops = _loads(trade.get("drops"), {})
    picks = _loads(trade.get("draft_picks"), [])
    faab = _loads(trade.get("waiver_budget"), [])

    def pick(p):
        return {"season": str(p.get("season")), "round": _int(p.get("round")),
                "original_roster_id": _int(p.get("roster_id"))}

    return {
        "give_player_ids":    sorted(str(p) for p, r in drops.items() if _int(r) == my_roster_id),
        "receive_player_ids": sorted(str(p) for p, r in adds.items() if _int(r) == my_roster_id),
        "give_picks":    [pick(p) for p in picks if isinstance(p, dict)
                          and _int(p.get("previous_owner_id")) == my_roster_id],
        "receive_picks": [pick(p) for p in picks if isinstance(p, dict)
                          and _int(p.get("owner_id")) == my_roster_id],
        "give_faab":    sum(_int(f.get("amount")) or 0 for f in faab
                            if isinstance(f, dict) and _int(f.get("sender")) == my_roster_id),
        "receive_faab": sum(_int(f.get("amount")) or 0 for f in faab
                            if isinstance(f, dict) and _int(f.get("receiver")) == my_roster_id),
    }


def classify(offer: dict, trades: list[dict]) -> dict | None:
    """The observed state of one open offer against a league's captured
    completed trades, or None when nothing is observed. Pure."""
    txid = str(offer.get("provider_transaction_id"))
    for t in trades:
        if str(t.get("transaction_id")) == txid:
            return {"status": "accepted", "status_at": t.get("traded_at"),
                    "resolved_transaction_id": txid, "observed_terms_json": None}
    if offer.get("status") != "sent":
        return None   # already completed_different_terms: only 'accepted' moves it
    mine, theirs = _int(offer.get("my_roster_id")), _int(offer.get("their_roster_id"))
    sent_at = _parse(offer.get("sent_at"))
    if mine is None or theirs is None or sent_at is None:
        return None
    later = []
    for t in trades:
        at = _parse(t.get("traded_at"))
        rosters = {_int(r) for r in _loads(t.get("roster_ids"), [])}
        if at is not None and at > sent_at and rosters == {mine, theirs}:
            later.append((at, str(t.get("transaction_id")), t))
    if not later:
        return None
    _at, tid, t = min(later, key=lambda x: (x[0], x[1]))
    return {"status": "completed_different_terms", "status_at": t.get("traded_at"),
            "resolved_transaction_id": tid,
            "observed_terms_json": json.dumps(observed_terms(t, mine), sort_keys=True)}


def reconcile_league(league_id: str, now: datetime | None = None) -> dict:
    """Move every open Sleeper offer of one league to its observed state.
    DB-only (reads `sleeper_trades`); idempotent — a re-run against the same
    capture writes the same status and only refreshes `checked_at`."""
    now_iso = (now or _now()).isoformat()
    counts = {"open": 0, "accepted": 0, "completed_different_terms": 0}
    offers = db.load_open_trade_offer_outcomes(league_id, PROVIDER_SLEEPER)
    if not offers:
        return counts
    trades = db.load_sleeper_trades_for_outcomes(league_id)
    for offer in offers:
        counts["open"] += 1
        seen = classify(offer, trades)
        values = {"checked_at": now_iso}
        if seen is not None and (seen["status"], seen["resolved_transaction_id"]) != (
                offer.get("status"), offer.get("resolved_transaction_id")):
            values.update(seen)
            counts[seen["status"]] += 1
        db.update_trade_offer_outcome(offer["id"], values)
    return counts


def tick(now: datetime, *, sync=None) -> dict:
    """Daily-tick body: for leagues with an open offer inside the watch window,
    refresh the public completed-trade capture (`sync(league_id)`, when
    given) and reconcile. One league's failure never stops the rest."""
    since = (now - timedelta(days=OUTCOME_WATCH_DAYS)).isoformat()
    stats = {"leagues": 0, "errors": 0, "accepted": 0, "completed_different_terms": 0}
    for league_id in db.load_trade_offer_outcome_leagues(
            PROVIDER_SLEEPER, since, OUTCOME_SYNC_LEAGUE_BUDGET):
        stats["leagues"] += 1
        try:
            if sync is not None:
                sync(league_id)
            c = reconcile_league(league_id, now)
            stats["accepted"] += c["accepted"]
            stats["completed_different_terms"] += c["completed_different_terms"]
        except Exception as err:
            stats["errors"] += 1
            log.warning("trade outcomes: league %s failed (continuing): %s", league_id, err)
    return stats
