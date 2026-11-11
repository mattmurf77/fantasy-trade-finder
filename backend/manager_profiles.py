"""manager_profiles.py — per-manager revealed-preference profiles (pure leaf).

Design: docs/plans/manager-profiles/design.md. Flag `market.manager_profiles`
(default OFF). One dark reader: revision 4's partner-activity rule reads
`n_trades` (flag `trade.partner_activity`, database.load_manager_trade_counts).
Otherwise CAPTURE ONLY: nothing in trade generation, ordering or any
client response reads a profile yet.

Turns one league's public Sleeper transaction history — completed trades
(the `raw` payloads `sleeper_trades` already keeps) plus waiver and
free-agent moves (`sleeper_waiver_moves`) — into one profile per manager:

  trade_activity  how often / how recently they trade at all (a prior on
                  whether they answer an offer)
  trade_style     picks-for-players vs players-for-picks
  trade_assets    position and age mix of what they acquire and give up
  waiver_bids     winning and losing FAAB bids, in dollars and as a share
                  of the league budget and of their remaining budget
  free_agents     free-agent pickups by position (activity only)

Rookie-draft selections are NOT captured in this version — see design.md §4.5.

Pure: no I/O, no database, no flags. The I/O half (fetch, store, load) is
`sleeper_trades_service.capture_manager_profiles`. Imports only
`sleeper_roster`, the ONE roster→user predicate, for attribution.

IDENTITY. A profile is keyed by the roster's `owner_id` — the manager's
LEAGUE identity (backend/CLAUDE.md "Identity: account vs league"). Moves are
attributed by `roster_id`, so a co-owner's claims land on the owner's
profile and never on a second row. A waiver / free-agent move whose
`creator` neither owns nor co-owns the roster (a commissioner action, or the
previous manager of a roster taken over mid-season) is excluded from the
profile and counted in `excluded.foreign_creator_moves`.
"""

from __future__ import annotations

import json
import statistics
from datetime import date, datetime, timezone

from .sleeper_roster import owns_roster

PROFILE_VERSION = 1

WAIVER_TYPES = ("waiver", "free_agent")
TERMINAL_STATUSES = ("complete", "failed")

# Thinness floors (design.md §4). Below these a signal is still stored —
# the counts are the evidence — but marked `usable: False`.
MIN_TRADES_FOR_STYLE = 3
MIN_TRADED_PLAYERS_FOR_MIX = 6
MIN_FAAB_BIDS = 5

# Sleeper writes this note on a claim that lost to a higher bid. Other
# failure notes (roster full, player locked) are not a valuation signal.
_OUTBID_NOTE = "claimed by another"

AGE_BANDS = ("<=23", "24-26", "27-29", "30+", "unknown")


# ---------------------------------------------------------------------------
# Small parsing helpers
# ---------------------------------------------------------------------------

def _ms_to_iso(ms) -> str | None:
    try:
        if ms:
            return datetime.fromtimestamp(int(ms) / 1000.0,
                                          tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        pass
    return None


def _int_or_none(v) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _as_dict(v) -> dict:
    return v if isinstance(v, dict) else {}


def _as_list(v) -> list:
    return v if isinstance(v, list) else []


def waiver_bid_of(txn: dict) -> int | None:
    """settings.waiver_bid — present on every FAAB waiver claim, absent on
    free-agent adds and on non-FAAB (rolling / reverse-standings) claims."""
    return _int_or_none(_as_dict(txn.get("settings")).get("waiver_bid"))


# ---------------------------------------------------------------------------
# Capture: raw transactions -> sleeper_waiver_moves rows
# ---------------------------------------------------------------------------

def parse_waiver_transactions(txns: list, league_id: str,
                              *, now: datetime | None = None) -> list[dict]:
    """Filter a raw `/transactions/<week>` list to terminal waiver and
    free-agent moves and normalize into `sleeper_waiver_moves` rows.

    Pending claims are never stored: only `complete` / `failed` rows are
    terminal, so the transaction_id insert can stay skip-not-upsert.
    """
    now_iso = (now or datetime.now(timezone.utc)).isoformat()
    rows: list[dict] = []
    for t in txns or []:
        if not isinstance(t, dict):
            continue
        if t.get("type") not in WAIVER_TYPES:
            continue
        if t.get("status") not in TERMINAL_STATUSES:
            continue
        txid = t.get("transaction_id")
        if not txid:
            continue
        roster_ids = _as_list(t.get("roster_ids"))
        failed = t.get("status") == "failed"
        rows.append({
            "transaction_id": str(txid),
            "league_id":      str(league_id),
            "week":           _int_or_none(t.get("leg")),
            "type":           t["type"],
            "status":         t["status"],
            "roster_id":      _int_or_none(roster_ids[0]) if roster_ids else None,
            "creator":        str(t["creator"]) if t.get("creator") else None,
            "waiver_bid":     waiver_bid_of(t),
            "adds":           json.dumps(_as_dict(t.get("adds"))),
            "drops":          json.dumps(_as_dict(t.get("drops"))),
            "failure_note":   (str(_as_dict(t.get("metadata")).get("notes") or "")
                               or None) if failed else None,
            "created_at":     _ms_to_iso(t.get("created")),
            "processed_at":   _ms_to_iso(t.get("status_updated")),
            "synced_at":      now_iso,
            "raw":            json.dumps(t),
        })
    return rows


# ---------------------------------------------------------------------------
# Player descriptors
# ---------------------------------------------------------------------------

def position_of(player_id: str, players: dict) -> str:
    """A player's position from the players table; team-defense ids
    (non-numeric, e.g. "TB") read as DEF."""
    meta = players.get(str(player_id)) or {}
    pos = meta.get("position")
    if pos:
        return str(pos)
    return "DEF" if not str(player_id).isdigit() else "unknown"


def age_band_at(player_id: str, players: dict, when_iso: str | None) -> str:
    """Age band on the event date, from birth_date. Unknown when either
    the birth date or the event date is missing."""
    meta = players.get(str(player_id)) or {}
    bd = meta.get("birth_date")
    if not bd or not when_iso:
        return "unknown"
    try:
        born = date.fromisoformat(str(bd)[:10])
        on = datetime.fromisoformat(when_iso).date()
    except ValueError:
        return "unknown"
    age = on.year - born.year - ((on.month, on.day) < (born.month, born.day))
    if age <= 23:
        return "<=23"
    if age <= 26:
        return "24-26"
    if age <= 29:
        return "27-29"
    return "30+"


def _bump(counter: dict, key) -> None:
    counter[key] = counter.get(key, 0) + 1


# ---------------------------------------------------------------------------
# Trades
# ---------------------------------------------------------------------------

def classify_trade_side(players_in: int, players_out: int,
                        picks_in: int, picks_out: int) -> str:
    """One roster's side of a completed trade, by net asset direction."""
    if picks_in == 0 and picks_out == 0:
        return "players_only"
    if players_in == 0 and players_out == 0:
        return "picks_only"
    if picks_out > 0 and picks_in == 0 and players_in > 0:
        return "picks_for_players"
    if picks_in > 0 and picks_out == 0 and players_out > 0:
        return "players_for_picks"
    return "mixed"


def _empty_side() -> dict:
    return {"n_players": 0, "by_position": {}, "by_age_band": {},
            "n_picks": 0, "picks_by_round": {}}


def _trade_sides(trade: dict, players: dict) -> dict[int, dict]:
    """Per roster_id: what it acquired and gave in one trade."""
    when = _ms_to_iso(trade.get("status_updated"))
    sides: dict[int, dict] = {}

    def side(rid) -> dict | None:
        rid = _int_or_none(rid)
        if rid is None:
            return None
        return sides.setdefault(rid, {"acquired": _empty_side(),
                                      "given": _empty_side(),
                                      "faab_net": 0})

    for rid in _as_list(trade.get("roster_ids")):
        side(rid)
    for pid, rid in _as_dict(trade.get("adds")).items():
        s = side(rid)
        if s is not None:
            a = s["acquired"]
            a["n_players"] += 1
            _bump(a["by_position"], position_of(pid, players))
            _bump(a["by_age_band"], age_band_at(pid, players, when))
    for pid, rid in _as_dict(trade.get("drops")).items():
        s = side(rid)
        if s is not None:
            g = s["given"]
            g["n_players"] += 1
            _bump(g["by_position"], position_of(pid, players))
            _bump(g["by_age_band"], age_band_at(pid, players, when))
    for pk in _as_list(trade.get("draft_picks")):
        if not isinstance(pk, dict):
            continue
        rnd = str(pk.get("round") or "?")
        recv, send = side(pk.get("owner_id")), side(pk.get("previous_owner_id"))
        if recv is not None:
            recv["acquired"]["n_picks"] += 1
            _bump(recv["acquired"]["picks_by_round"], rnd)
        if send is not None:
            send["given"]["n_picks"] += 1
            _bump(send["given"]["picks_by_round"], rnd)
    for wb in _as_list(trade.get("waiver_budget")):
        if not isinstance(wb, dict):
            continue
        amt = _int_or_none(wb.get("amount")) or 0
        snd, rcv = side(wb.get("sender")), side(wb.get("receiver"))
        if snd is not None:
            snd["faab_net"] -= amt
        if rcv is not None:
            rcv["faab_net"] += amt
    return sides


def _merge_side(into: dict, src: dict) -> None:
    into["n_players"] += src["n_players"]
    into["n_picks"] += src["n_picks"]
    for k in ("by_position", "by_age_band", "picks_by_round"):
        for key, n in src[k].items():
            into[k][key] = into[k].get(key, 0) + n


# ---------------------------------------------------------------------------
# The profile
# ---------------------------------------------------------------------------

def faab_budget_of(league_meta: dict | None) -> int | None:
    """The league's FAAB budget, or None when the league does not bid
    (Sleeper settings.waiver_type 2 = FAAB)."""
    settings = _as_dict(_as_dict(league_meta).get("settings"))
    if _int_or_none(settings.get("waiver_type")) != 2:
        return None
    budget = _int_or_none(settings.get("waiver_budget"))
    return budget if budget and budget > 0 else None


def build_league_profiles(
    league_id: str,
    *,
    trades: list[dict],
    moves: list[dict],
    rosters: list[dict],
    players: dict,
    league_meta: dict | None,
    now: datetime | None = None,
) -> list[dict]:
    """`manager_profiles` rows for every OWNED roster in the league.

    trades: raw Sleeper trade payloads (sleeper_trades.raw, decoded).
    moves:  raw Sleeper waiver / free-agent payloads (sleeper_waiver_moves.raw).
    rosters: the league's /rosters list — the roster_id → owner_id map and
             the co-owner predicate's input.
    players: {player_id: {"position", "birth_date", ...}} for the ids involved.

    An ownerless roster (owner_id null — nobody to trade with) gets no row.
    A manager with no history gets a row of zeros: absence of trades is
    itself the activity signal.
    """
    now = now or datetime.now(timezone.utc)
    by_rid: dict[int, dict] = {}
    for r in rosters or []:
        if not isinstance(r, dict):
            continue
        rid = _int_or_none(r.get("roster_id"))
        if rid is not None and r.get("owner_id"):
            by_rid[rid] = r
    if not by_rid:
        return []

    budget = faab_budget_of(league_meta)
    acc = {rid: {
        "trades": [], "style": {}, "acquired": _empty_side(),
        "given": _empty_side(), "faab_trade_events": [], "counterparties": set(),
        "bids": [], "fa_adds": 0, "fa_by_position": {}, "foreign": 0,
        "claims_no_bid": 0,
    } for rid in by_rid}

    # ── trades ────────────────────────────────────────────────────────────
    seen_tx: set = set()
    for t in sorted((t for t in trades or [] if isinstance(t, dict)),
                    key=lambda t: (_int_or_none(t.get("status_updated")) or 0,
                                   str(t.get("transaction_id")))):
        if t.get("type") != "trade" or t.get("status") != "complete":
            continue
        txid = t.get("transaction_id")
        if txid in seen_tx:
            continue
        seen_tx.add(txid)
        when = _ms_to_iso(t.get("status_updated"))
        sides = _trade_sides(t, players)
        for rid, s in sides.items():
            a = acc.get(rid)
            if a is None:
                continue
            a["trades"].append(when)
            a["counterparties"].update(o for o in sides if o != rid)
            _bump(a["style"], classify_trade_side(
                s["acquired"]["n_players"], s["given"]["n_players"],
                s["acquired"]["n_picks"], s["given"]["n_picks"]))
            _merge_side(a["acquired"], s["acquired"])
            _merge_side(a["given"], s["given"])
            if s["faab_net"]:
                a["faab_trade_events"].append((when or "", s["faab_net"]))

    # ── waiver / free-agent moves ────────────────────────────────────────
    move_list = sorted((m for m in moves or [] if isinstance(m, dict)),
                       key=lambda m: (_int_or_none(m.get("status_updated")) or 0,
                                      str(m.get("transaction_id"))))
    # The clearing price of a contested claim: the winning bid on the same
    # player in the same waiver run (same leg + processing time).
    clearing: dict[tuple, int] = {}
    for m in move_list:
        if (m.get("type") == "waiver" and m.get("status") == "complete"
                and waiver_bid_of(m) is not None):
            for pid in _as_dict(m.get("adds")):
                key = (m.get("leg"), m.get("status_updated"), str(pid))
                clearing[key] = max(clearing.get(key, 0), waiver_bid_of(m))

    seen_mv: set = set()
    for m in move_list:
        if m.get("type") not in WAIVER_TYPES or m.get("status") not in TERMINAL_STATUSES:
            continue
        txid = m.get("transaction_id")
        if txid in seen_mv:
            continue
        seen_mv.add(txid)
        rids = _as_list(m.get("roster_ids"))
        rid = _int_or_none(rids[0]) if rids else None
        a = acc.get(rid)
        if a is None:
            continue
        if not owns_roster(by_rid[rid], m.get("creator")):
            a["foreign"] += 1
            continue
        adds = list(_as_dict(m.get("adds")))
        if m["type"] == "free_agent":
            if m["status"] == "complete":
                for pid in adds:
                    a["fa_adds"] += 1
                    _bump(a["fa_by_position"], position_of(pid, players))
            continue
        bid = waiver_bid_of(m)
        if bid is None or budget is None:
            a["claims_no_bid"] += 1
            continue
        if m["status"] == "complete":
            outcome = "won"
        elif _OUTBID_NOTE in str(_as_dict(m.get("metadata")).get("notes") or ""):
            outcome = "outbid"
        else:
            outcome = "failed"
        # A Sleeper claim adds one player; count its bid once even if not.
        for pid in adds[:1] or [None]:
            cb = clearing.get((m.get("leg"), m.get("status_updated"), str(pid)))
            a["bids"].append({
                "player_id": str(pid) if pid is not None else None,
                "position": position_of(pid, players) if pid is not None else "unknown",
                "leg": _int_or_none(m.get("leg")),
                "at": _ms_to_iso(m.get("status_updated")),
                "bid": bid,
                "outcome": outcome,
                "clearing_bid": cb if outcome == "outbid" else None,
            })

    # ── assemble ──────────────────────────────────────────────────────────
    league_trade_counts = [len(a["trades"]) for a in acc.values()]
    league_mean = (round(sum(league_trade_counts) / len(league_trade_counts), 2)
                   if league_trade_counts else 0.0)
    computed_at = now.isoformat()
    rows: list[dict] = []
    for rid in sorted(acc):
        a = acc[rid]
        roster = by_rid[rid]
        n_trades = len(a["trades"])
        last_trade = max((w for w in a["trades"] if w), default=None)
        days_since = None
        if last_trade:
            days_since = (now - datetime.fromisoformat(last_trade)).days
        traded_players = a["acquired"]["n_players"] + a["given"]["n_players"]
        bids = _price_bids(a["bids"], a["faab_trade_events"], budget)
        won = [b for b in bids if b["outcome"] == "won"]
        reported_spent = _int_or_none(
            _as_dict(roster.get("settings")).get("waiver_budget_used"))
        profile = {
            "version": PROFILE_VERSION,
            "trade_activity": {
                "n": n_trades,
                "last_trade_at": last_trade,
                "days_since_last_trade": days_since,
                "counterparties": len(a["counterparties"]),
                "league_mean_n": league_mean,
                "usable": True,
            },
            "trade_style": {
                "n": n_trades,
                **{k: a["style"].get(k, 0) for k in (
                    "picks_for_players", "players_for_picks",
                    "players_only", "picks_only", "mixed")},
                "faab_net_in_trades": sum(n for _, n in a["faab_trade_events"]),
                "usable": n_trades >= MIN_TRADES_FOR_STYLE,
            },
            "trade_assets": {
                "acquired": a["acquired"],
                "given": a["given"],
                "usable": traded_players >= MIN_TRADED_PLAYERS_FOR_MIX,
            },
            "waiver_bids": {
                "faab": budget is not None,
                "budget": budget,
                "n": len(bids),
                "won": len(won),
                "outbid": sum(1 for b in bids if b["outcome"] == "outbid"),
                "failed_other": sum(1 for b in bids if b["outcome"] == "failed"),
                "claims_without_bid": a["claims_no_bid"],
                "spent": sum(b["bid"] for b in won),
                "reported_spent": reported_spent,
                "median_won_share": (round(statistics.median(
                    b["share_of_budget"] for b in won), 4) if won else None),
                "max_share": (max(b["share_of_budget"] for b in bids)
                              if bids else None),
                "bids": bids,
                "usable": budget is not None and len(bids) >= MIN_FAAB_BIDS,
            },
            "free_agents": {
                "n": a["fa_adds"],
                "by_position": a["fa_by_position"],
            },
            "rookie_draft": {"captured": False,
                             "reason": "not in profile v1 (design.md §4.5)"},
            "excluded": {"foreign_creator_moves": a["foreign"]},
        }
        rows.append({
            "league_id":         str(league_id),
            "owner_id":          str(roster["owner_id"]),
            "roster_id":         rid,
            "profile_version":   PROFILE_VERSION,
            "computed_at":       computed_at,
            "n_trades":          n_trades,
            "last_trade_at":     last_trade,
            "n_waiver_bids":     len(bids),
            "n_free_agent_adds": a["fa_adds"],
            "profile":           json.dumps(profile, sort_keys=True),
        })
    return rows


def _price_bids(bids: list[dict], faab_trade_events: list[tuple],
                budget: int | None) -> list[dict]:
    """Add share_of_budget and share_of_remaining to each bid, walking the
    manager's season in order: remaining = budget − won bids so far + FAAB
    received in trades so far. Exact only over a fully backfilled season,
    which is what the sweep guarantees before it writes a profile."""
    if budget is None:
        return []
    events = sorted(faab_trade_events)
    out, spent, ei, faab_net = [], 0, 0, 0
    for b in sorted(bids, key=lambda b: (b["at"] or "", b["player_id"] or "")):
        while ei < len(events) and events[ei][0] <= (b["at"] or ""):
            faab_net += events[ei][1]
            ei += 1
        remaining = budget - spent + faab_net
        priced = dict(b)
        priced["share_of_budget"] = round(b["bid"] / budget, 4)
        priced["share_of_remaining"] = (round(b["bid"] / remaining, 4)
                                        if remaining > 0 else None)
        out.append(priced)
        if b["outcome"] == "won":
            spent += b["bid"]
    return out
