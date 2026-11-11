"""
backend/sleeper_offer_read.py — the signed-in user's own Sleeper trade offers,
read privately (offer-learnings WS2b, flag `trade.sleeper_offer_import`).

Scope block: docs/plans/offer-learnings/scope-sleeper-offer-read.md
What Sleeper returns: docs/plans/offer-learnings/sleeper-offers-read.md

A leaf: imports `database` and `sleeper_roster` only, never `server` and never
the network. `server.py` owns the flag, the credential, the rosters read and
the one call to `sleeper_write.league_trade_offers`, then hands the answer to
`apply_read`. Throttling lives here (`due` / `note_failure`) so every trigger
shares one rule.

What a read does, for one (user, league):

1. Offers the user SENT THROUGH THE APP (`trade_offer_outcomes` rows with
   source app) move to the status Sleeper shows:
     proposed                          -> sent (unchanged)
     complete                          -> accepted
     rejected (by the other manager)   -> declined
     cancelled, rejecter = the sender  -> withdrawn
     cancelled, no rejecter            -> lapsed
     declined or lapsed, and the other manager's counter is linked -> countered
   The linked counter's own state is kept beside it (`counter_status`:
   pending | accepted | declined | withdrawn | lapsed | countered) with its
   terms from the user's side, so "they countered and I declined the counter"
   is readable.
2. Only with the user's consent (`offer_import_consents`, latest row a grant
   at TERMS_VERSION), every other two-team trade offer the read returns that
   involves the user's roster is stored too, with `source = 'sleeper_import'`
   and `direction` sent | received. Without consent nothing but the app's own
   rows is written.

Counter linking. Sleeper flags a counter (`settings.is_counter`) but does not
say which offer it answers. An offer T is answered by the earliest unclaimed
`is_counter` transaction C between the same two rosters, created by the OTHER
side of T, with C.created in [T.status_updated - 60 s, T.status_updated +
10 min] and T no longer proposed. Each counter answers at most one offer;
offers are matched in order of when they closed. A counter can itself be
countered, by the same rule.

Stored per offer: the transaction id, the league, both roster ids (the other
manager only as a league roster id), asset ids from the user's side, the
status words above and Sleeper's times. Never stored: `metadata`, `settings`,
`player_map` (not requested), any user id from the read, the token.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone

from . import database as db
from .sleeper_roster import co_owner_ids, find_user_roster

log = logging.getLogger(__name__)

FLAG = "trade.sleeper_offer_import"
PROVIDER = "sleeper"
SOURCE_APP = "app"
SOURCE_IMPORT = "sleeper_import"
# The Terms wording the switch stands on (web/terms.html §6 "Trade outcomes",
# approved by the operator 2026-11-10). A new wording is a new version, and a
# grant at an older version is not consent.
TERMS_VERSION = "offer-import-1"
# Settings copy, served so the wording can change with the version.
SWITCH_LABEL = "Use my Sleeper trade offers to improve suggestions"
TERMS_LINE = ("We read the trade offers you send and receive on Sleeper in your linked "
              "leagues, and what happened to each. Never your messages or chats. Turn "
              "this off at any time and we delete the offers we imported.")
WITHDRAWN_NOTICE = "Imported offers deleted."

# Polling: at most one read per (user, league) per READ_MIN_INTERVAL_S, from
# Find a Trade or the daily tick. After an auth failure the user is not read
# again for AUTH_BACKOFF_S; after any other failure that league is not read
# for ERROR_BACKOFF_S. Process-local (one gunicorn worker).
READ_MIN_INTERVAL_S = 30 * 60
AUTH_BACKOFF_S = 24 * 3600
ERROR_BACKOFF_S = 6 * 3600
# The daily tick reads at most TICK_BUDGET (user, league) pairs, for app-sent
# offers sent in the last WATCH_DAYS and the leagues of consenting users.
WATCH_DAYS = 30
TICK_BUDGET = 100
CONSENT_LEAGUE_FRESH_DAYS = 45

COUNTER_LINK_BEFORE_S = 60
COUNTER_LINK_AFTER_S = 600

# App-sent rows the read may still move. `accepted`, `declined`, `withdrawn`
# and `lapsed` are final.
APP_READ_STATUSES = ("sent", "completed_different_terms", "countered")

_lock = threading.Lock()
_last_attempt: dict[tuple[str, str], float] = {}
_league_backoff: dict[tuple[str, str], float] = {}
_user_backoff: dict[str, float] = {}


# ---------------------------------------------------------------------------
# Throttle
# ---------------------------------------------------------------------------

def due(user_id: str, league_id: str, now: float) -> bool:
    """True, and the attempt recorded, when a read of (user, league) may run
    now. A read that is not due does nothing and logs nothing."""
    key = (str(user_id), str(league_id))
    with _lock:
        if _user_backoff.get(key[0], 0) > now or _league_backoff.get(key, 0) > now:
            return False
        last = _last_attempt.get(key)
        if last is not None and now - last < READ_MIN_INTERVAL_S:
            return False
        _last_attempt[key] = now
        return True


def note_failure(user_id: str, league_id: str, *, auth: bool, now: float,
                 detail: str = "") -> None:
    """Back off after a failed read and log it once. Nothing else changes:
    the credential, the consent and every stored row stay as they were."""
    with _lock:
        if auth:
            _user_backoff[str(user_id)] = now + AUTH_BACKOFF_S
        else:
            _league_backoff[(str(user_id), str(league_id))] = now + ERROR_BACKOFF_S
    log.warning("sleeper offers read failed (%s); backing off %ds: %s",
                "auth" if auth else "error", AUTH_BACKOFF_S if auth else ERROR_BACKOFF_S,
                str(detail or "")[:200])


def reset_throttle() -> None:
    """Tests only."""
    with _lock:
        _last_attempt.clear()
        _league_backoff.clear()
        _user_backoff.clear()


# ---------------------------------------------------------------------------
# Consent
# ---------------------------------------------------------------------------

def consented(user_id: str) -> bool:
    row = db.latest_offer_import_consent(user_id)
    return bool(row and row["kind"] == "grant" and row["terms_version"] == TERMS_VERSION)


# ---------------------------------------------------------------------------
# Parsing (pure)
# ---------------------------------------------------------------------------

def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _obj(v) -> dict:
    """`metadata` / `settings` arrive as JSON scalars: an object, or a string
    holding one. Anything else reads as empty."""
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except ValueError:
            return {}
    return v if isinstance(v, dict) else {}


def _iso(ms) -> str | None:
    """Sleeper's millisecond epoch times as ISO-8601 UTC."""
    n = _int(ms)
    if n is None:
        return None
    return datetime.fromtimestamp(n / 1000, tz=timezone.utc).isoformat()


def _rosters(tx) -> list[int]:
    return [r for r in (_int(x) for x in (tx.get("roster_ids") or [])) if r is not None]


def rejecter_id(tx) -> str | None:
    rid = _obj(tx.get("metadata")).get("rejecter_id")
    return str(rid) if rid not in (None, "") else None


def is_counter(tx) -> bool:
    return bool(_obj(tx.get("settings")).get("is_counter"))


def status_of(tx, creator_is_me: bool, is_me) -> str | None:
    """Sleeper's status for one offer, in this app's words, without counter
    linking. None for a status word the capture never showed."""
    s = tx.get("status")
    if s == "proposed":
        return "sent"
    if s == "complete":
        return "accepted"
    rej = rejecter_id(tx)
    rejecter_is_creator_side = rej is not None and is_me(rej) == creator_is_me
    if s == "rejected":
        return "withdrawn" if rejecter_is_creator_side else "declined"
    if s == "cancelled":
        return "withdrawn" if rejecter_is_creator_side else "lapsed"
    return None


def side_assets(tx, my_roster_id: int, league_id: str) -> tuple[list, list, dict]:
    """(give asset ids, receive asset ids, extras) from `my_roster_id`'s side.
    Players are Sleeper ids; a pick is this league's owned-pick id
    (`db.make_pick_id`). Picks are read in either shape Sleeper uses: the
    REST object {season, round, roster_id (original), owner_id (receives),
    previous_owner_id (gives)} or the propose string "orig,season,round,
    from,to". A pick in neither shape is counted in extras['unparsed_picks']
    and left out; FAAB is counted in extras, never as an asset (a FAAB entry
    in the private read's string form is counted in extras['unparsed_faab'])."""
    adds = tx.get("adds") if isinstance(tx.get("adds"), dict) else {}
    drops = tx.get("drops") if isinstance(tx.get("drops"), dict) else {}
    give = sorted(str(p) for p, r in drops.items() if _int(r) == my_roster_id)
    receive = sorted(str(p) for p, r in adds.items() if _int(r) == my_roster_id)
    extras = {}
    unparsed = 0
    for p in tx.get("draft_picks") or []:
        season = rnd = orig = giver = taker = None
        if isinstance(p, dict):
            season, rnd, orig = _int(p.get("season")), _int(p.get("round")), _int(p.get("roster_id"))
            giver, taker = _int(p.get("previous_owner_id")), _int(p.get("owner_id"))
        elif isinstance(p, str) and len(p.split(",")) == 5:
            orig, season, rnd, giver, taker = (_int(x) for x in p.split(","))
        if None in (season, rnd, orig, giver, taker):
            unparsed += 1
            continue
        pid = db.make_pick_id(str(league_id), season, rnd, str(orig))
        if giver == my_roster_id:
            give.append(pid)
        elif taker == my_roster_id:
            receive.append(pid)
    if unparsed:
        extras["unparsed_picks"] = unparsed
    for f in tx.get("waiver_budget") or []:
        if not isinstance(f, dict):
            # Sleeper's private read returns FAAB as a "n,n,n" string (seen
            # live, 2026-11-10); its field order is not established, so the
            # offer is only marked as carrying FAAB. Any extras keep an offer
            # out of revised-offer cards.
            extras["unparsed_faab"] = extras.get("unparsed_faab", 0) + 1
            continue
        amt = _int(f.get("amount")) or 0
        if _int(f.get("sender")) == my_roster_id:
            extras["give_faab"] = extras.get("give_faab", 0) + amt
        elif _int(f.get("receiver")) == my_roster_id:
            extras["receive_faab"] = extras.get("receive_faab", 0) + amt
    return give, receive, extras


def link_counters(txs: list[dict], is_me) -> dict[str, dict]:
    """{offer transaction id: the counter transaction answering it}. See the
    module docstring for the rule. `txs` are two-team trades of one league."""
    closed = sorted((t for t in txs if t.get("status") != "proposed"
                     and _int(t.get("status_updated")) is not None),
                    key=lambda t: (_int(t["status_updated"]), str(t.get("transaction_id"))))
    counters = [c for c in txs if is_counter(c) and _int(c.get("created")) is not None]
    claimed: set[str] = set()
    out: dict[str, dict] = {}
    for t in closed:
        tid = str(t.get("transaction_id"))
        pair = frozenset(_rosters(t))
        mine = is_me(str(t.get("creator")))
        closed_at = _int(t["status_updated"])
        best = None
        for c in counters:
            cid = str(c.get("transaction_id"))
            if cid == tid or cid in claimed or frozenset(_rosters(c)) != pair:
                continue
            if is_me(str(c.get("creator"))) == mine:
                continue          # a counter comes from the other side
            created = _int(c["created"])
            if not (closed_at - COUNTER_LINK_BEFORE_S * 1000 <= created
                    <= closed_at + COUNTER_LINK_AFTER_S * 1000):
                continue
            key = (created, cid)
            if best is None or key < best[0]:
                best = (key, c)
        if best is not None:
            claimed.add(str(best[1].get("transaction_id")))
            out[tid] = best[1]
    return out


def classify(tx, links: dict, is_me) -> dict:
    """The stored state of one offer: status, status_at and the counter
    fields, from the user's side."""
    creator_me = is_me(str(tx.get("creator")))
    status = status_of(tx, creator_me, is_me)
    out = {"status": status, "status_at": _iso(tx.get("status_updated")),
           "counter_transaction_id": None, "counter_status": None,
           "counter_status_at": None, "counter": None}
    counter = links.get(str(tx.get("transaction_id")))
    if counter is not None and status in ("declined", "lapsed"):
        out["status"] = "countered"
        c_status = status_of(counter, not creator_me, is_me)
        if c_status == "sent":
            c_status = "pending"
        if c_status in ("declined", "lapsed") and str(counter.get("transaction_id")) in links:
            c_status = "countered"
        out.update(counter_transaction_id=str(counter.get("transaction_id")),
                   counter_status=c_status,
                   counter_status_at=_iso(counter.get("status_updated")),
                   counter=counter)
    return out


# ---------------------------------------------------------------------------
# Applying one read
# ---------------------------------------------------------------------------

def my_user_ids(rosters, sleeper_user_id) -> tuple[int | None, set[str]]:
    """(the user's roster id, every user id that owns or co-owns it)."""
    roster = find_user_roster(rosters, sleeper_user_id)
    if roster is None:
        return None, set()
    ids = {str(roster.get("owner_id"))} | set(co_owner_ids(roster))
    ids.add(str(sleeper_user_id))
    return _int(roster.get("roster_id")), {i for i in ids if i and i != "None"}


def apply_read(*, user_id: str, league_id: str, txs: list[dict], my_roster_id: int,
               me: set[str], import_on: bool, now: datetime) -> dict:
    """Write what one read shows. Idempotent: a repeat of the same answer
    writes the same values and only refreshes `checked_at`."""
    is_me = lambda uid: str(uid) in me                      # noqa: E731
    now_iso = now.isoformat()
    stats = {"read": len(txs), "two_team": 0, "app_updated": 0, "imported": 0,
             "import_updated": 0, "skipped_multi_team": 0}
    trades = []
    for t in txs:
        if t.get("type") not in (None, "trade") or not t.get("transaction_id"):
            continue
        rosters = _rosters(t)
        if my_roster_id not in rosters:
            continue
        if len(set(rosters)) != 2:
            stats["skipped_multi_team"] += 1
            continue
        trades.append(t)
    stats["two_team"] = len(trades)
    links = link_counters(trades, is_me)
    existing = {str(r["provider_transaction_id"]): r
                for r in db.load_user_trade_offer_outcomes(user_id, league_id, PROVIDER)}

    def counter_terms(counter):
        if counter is None:
            return None
        g, r, extras = side_assets(counter, my_roster_id, league_id)
        return json.dumps({"give_asset_ids": g, "receive_asset_ids": r, **extras}, sort_keys=True)

    for t in trades:
        tid = str(t["transaction_id"])
        seen = classify(t, links, is_me)
        if seen["status"] is None:
            continue
        values = {k: seen[k] for k in ("status", "status_at", "counter_transaction_id",
                                       "counter_status", "counter_status_at")}
        values["counter_terms_json"] = counter_terms(seen["counter"])
        values["checked_at"] = now_iso
        if seen["status"] == "accepted":
            values.update(resolved_transaction_id=tid, observed_terms_json=None)
        row = existing.get(tid)
        if row is not None and (row.get("source") or SOURCE_APP) == SOURCE_APP:
            if row["status"] not in APP_READ_STATUSES:
                continue
            if seen["status"] == "sent":
                # Still pending at Sleeper: nothing to move.
                db.update_trade_offer_outcome(row["id"], {"checked_at": now_iso})
                continue
            db.update_trade_offer_outcome(row["id"], values)
            stats["app_updated"] += 1
            continue
        if not import_on:
            continue
        if row is not None:
            db.update_trade_offer_outcome(row["id"], values)
            stats["import_updated"] += 1
            continue
        theirs = next(r for r in _rosters(t) if r != my_roster_id)
        give, receive, extras = side_assets(t, my_roster_id, league_id)
        inserted = db.save_trade_offer_outcome({
            "user_id": str(user_id), "league_id": str(league_id), "provider": PROVIDER,
            "provider_transaction_id": tid, "my_roster_id": my_roster_id,
            "their_roster_id": theirs,
            "give_asset_ids": json.dumps(give), "receive_asset_ids": json.dumps(receive),
            "sent_at": _iso(t.get("created")) or now_iso,
            "source": SOURCE_IMPORT,
            "direction": "sent" if is_me(str(t.get("creator"))) else "received",
            "extras_json": json.dumps(extras, sort_keys=True) if extras else None,
            **values,
        })
        stats["imported"] += int(bool(inserted))
    return stats
