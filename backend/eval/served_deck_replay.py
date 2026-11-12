"""Served-deck replay: rules-first construction against today's pipeline (ADR-030).

Operator tooling, unflagged, no server wiring. For every recorded owner request in a
directory (``bakeoff_runs.config_json.owner_request`` captures, one JSON file each, plus
``index.json`` and the ``model_config.json`` capture: the layout of the git-ignored
``data/prod-requests/``), it builds the deck both ways in one process and compares what the
user would be SERVED, after every downstream stage that runs offline:

- today ("old"): the generator's full solve, then significance (discovery, when enforced),
  the bilateral presentment (revision 2), then ``deck_quality.filter_deck``;
- rules-first ("new"): ``trade_fast_deck.serve`` (page search to exhaustion, else the gated
  full solve), then the same downstream stages, which must remove nothing.

Not replayed (database-backed): decline-window suppression and its floor and retest,
dispositions (#419), likes-you and revised-offer injection, owner revalidation (a no-op on
unchanged inputs). Production therefore serves fewer cards than either column here.

Output is aggregate-only (counts, medians, percentiles): no ids, names or rosters.

    PYTHONHASHSEED=0 python -m backend.eval.served_deck_replay --dir data/prod-requests

``--latest`` replays only the newest request of each manager-league pair. Comparisons are
in-process (the incumbent is not repeatable across processes, R0). Run it with nothing
else on the machine for meaningful CPU numbers.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import statistics
import sys
import time
from types import SimpleNamespace

DEFAULT_SLOTS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX"]
ENFORCE = (2, "significance-v1", "second", True)   # production's capture (mode, version, tier, picks)


def _identity(card):
    return card.target_user_id, tuple(card.give_player_ids), tuple(card.receive_player_ids)


def parse_owned_pick(pid, league_id):
    """``server._parse_owned_pick_id``, restated so this tool never imports the server."""
    prefix = f"{league_id}_"
    if not isinstance(pid, str) or not pid.startswith(prefix):
        return None
    parts = pid[len(prefix):].split("_")
    if len(parts) < 3:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except (TypeError, ValueError):
        return None


class Request:
    """One owner request's offline downstream: its inputs, rules and served-deck stand-in."""

    def __init__(self, context, lineup_slots, *, significance=ENFORCE, quality=True):
        from .. import deck_rules, trade_service as ts
        self.context, self.slots, self.capture, self.quality = context, lineup_slots, significance, quality
        self.viewer = str(context["user_id"])
        self.league_id = context["league"].league_id
        self.rosters = {str(m.user_id): list(m.roster or ()) for m in context["league"].members}
        self.rosters[self.viewer] = list(context["user_roster"])
        seed, players = context["seed_elo"], context["players"]
        self.market = lambda pid: ts.elo_to_value(seed[pid]) if pid in seed else None
        self.position = lambda pid: getattr(players.get(pid), "position", None)
        enforce = significance is not None and significance[0] == 2
        self.rules = lambda: deck_rules.DeckRules(
            viewer_id=self.viewer, market=self.market, position=self.position, rosters=self.rosters,
            lineup_slots=lineup_slots, quality=quality,
            significance=(lambda target, give, receive: self.significant(give, receive)) if enforce else None)
        self.enforce = enforce

    def significant(self, give, receive):
        from .. import trade_service as ts, trade_significance
        card = SimpleNamespace(give_player_ids=list(give), receive_player_ids=list(receive),
                               league_id=self.league_id)
        return trade_significance.evaluate_significance(
            card, players=self.context["players"], user_elo=self.context["user_elo"],
            seed_elo=self.context["seed_elo"], user_sources=self.context.get("user_sources"),
            scoring_format=self.context.get("scoring_format", "1qb_ppr"), context="discovery",
            player_min_tier=self.capture[2], allow_first_round_pick=self.capture[3],
            owned_pick_parser=parse_owned_pick, is_pick_asset=ts.is_pick_asset).eligible

    def served(self, cards, *, presentment=True):
        """``(served cards, counts)``: production's downstream order for an organic owner deck,
        minus the database-backed stages (module docstring)."""
        from .. import deck_quality, trade_bilateral_presentment
        kept = [c for c in cards if self.significant(c.give_player_ids, c.receive_player_ids)] \
            if self.enforce else list(cards)
        counts = {"significance": len(cards) - len(kept)}
        if presentment:
            kept, _ = trade_bilateral_presentment.present(kept)
        if self.quality:
            kept, quality = deck_quality.filter_deck(
                kept, viewer_id=self.viewer, market=self.market, position=self.position,
                rosters=self.rosters, lineup_slots=self.slots)
            counts.update(quality)
        return kept, counts


def compare(generate, request, *, presentment=True):
    """Both paths on one request, in this process: a dict of aggregates."""
    from .. import trade_fast_deck
    c0 = time.process_time()
    full, _ = generate(**request.context)
    old_cpu = time.process_time() - c0
    old, old_counts = request.served(full, presentment=presentment)
    c0 = time.process_time()
    built, _, info = trade_fast_deck.serve(generate, request.context, request.rules())
    new_cpu = time.process_time() - c0
    new, new_counts = request.served(built, presentment=presentment)
    gated, _ = trade_fast_deck.gated_full(generate, request.context, request.rules())
    a, b = [_identity(c) for c in old], [_identity(c) for c in new]
    return {"generated": len(full), "admitted": len(built), "served_old": len(a), "served_new": len(b),
            "same_set": len(a) == len(b) and set(a) == set(b), "first_same": a[:1] == b[:1],
            "overlap30": len(set(a[:30]) & set(b[:30])),
            "page_eq_gated": [_identity(c) for c in built] == [_identity(c) for c in gated],
            "guard_removed": sum(v for k, v in new_counts.items() if k != "deferred"),
            "path": info["path"], "fallback": info["fallback"],
            "old_cpu": round(old_cpu, 3), "new_cpu": round(new_cpu, 3)}


def load_request(record, slots_by_league):
    """A recorded owner request as generator keyword arguments, plus its lineup slots."""
    from .. import trade_service as ts
    from ..ranking_service import Player
    from .scorecard_replay import PERSONAL_SOURCES
    raw = record["owner_request"]
    k = copy.deepcopy(raw["input"])
    players = {pid: Player(id=pid, name=pid, **attrs) for pid, attrs in k.pop("players").items()}
    members = []
    for m in k.pop("members"):
        src = (k.get("opponent_sources") or {}).get(m["id"], {})
        members.append(ts.LeagueMember(m["id"], m["id"], m["roster"], m["elo"],
                                       bool(m["elo"]) and any(s in PERSONAL_SOURCES for s in src.values()),
                                       confidence_sources=src))
    league_id = record.get("league_id") or "x"
    k.update(players=players, league=ts.League(league_id, "offline", "sleeper", members),
             config=dict(ts._cfg))
    for key in ("past_decision_keys", "exclusion_keys"):
        k[key] = {(frozenset(a), frozenset(b)) for a, b in k.get(key, [])}
    k.pop("roster_owner_map", None)
    pref = (raw["input"].get("manager_preferences") or {}).get(raw["input"]["user_id"]) or {}
    slots = pref.get("starter_slots") or slots_by_league.get(league_id)
    if not slots:
        slots = DEFAULT_SLOTS + (["SUPER_FLEX"] if raw["input"]["scoring_format"] == "sf_tep" else [])
    return k, slots


def _pct(values, p):
    values = sorted(values)
    return values[min(len(values) - 1, int(p * len(values)))] if values else None


def summarize(rows):
    n = len(rows)
    lines = [f"requests replayed: {n}"]
    if not n:
        return "\n".join(lines)
    for label, key in (("served set equal (old vs new)", "same_set"), ("first card the same", "first_same"),
                       ("page deck == gated full solve", "page_eq_gated")):
        lines.append(f"{label}: {sum(r[key] for r in rows)} of {n}")
    overlap = [r["overlap30"] for r in rows]
    lines.append(f"cards shared in the first 30: median {statistics.median(overlap)} p10 {_pct(overlap, .1)} min {min(overlap)}")
    for key in ("served_old", "served_new", "admitted", "generated"):
        xs = [r[key] for r in rows]
        lines.append(f"{key}: min {min(xs)} median {statistics.median(xs)} max {max(xs)}")
    for key in ("old_cpu", "new_cpu"):
        xs = [r[key] for r in rows]
        lines.append(f"{key} s per search: median {statistics.median(xs)} p95 {_pct(xs, .95)} max {max(xs)}")
    lines.append(f"downstream guard removals (must be 0): {sum(r['guard_removed'] for r in rows)}")
    fallbacks = [r["fallback"] for r in rows if r["fallback"]]
    lines.append(f"gated fallbacks: {len(fallbacks)}" + (f" {sorted(set(fallbacks))}" if fallbacks else ""))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dir", required=True, help="recorded requests (index.json, model_config.json)")
    parser.add_argument("--latest", action="store_true", help="newest request per manager-league pair only")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    os.environ.setdefault("DATABASE_URL", "sqlite://")   # never the app database
    import socket

    def _no_network(*_args, **_kwargs):
        raise RuntimeError("served_deck_replay is offline")
    socket.socket.connect = socket.socket.connect_ex = socket.create_connection = _no_network
    from pathlib import Path
    from .. import database, feature_flags, trade_service as ts
    from .. import trade_gen_bilateral_candidate as candidate
    database.metadata.create_all(database.engine)
    feature_flags._flags_cache = feature_flags._load_from_json(
        Path(__file__).resolve().parents[2] / "config" / "features.json")
    index = json.load(open(os.path.join(args.dir, "index.json")))
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    ts._cfg.update(json.load(open(os.path.join(args.dir, "model_config.json"))))
    if args.latest:
        latest = {}
        for r in index:
            if r["pair"] not in latest or r["created_at"] > latest[r["pair"]]["created_at"]:
                latest[r["pair"]] = r
        index = list(latest.values())
    records = [json.load(open(os.path.join(args.dir, r["file"]))) for r in index[:args.limit]]
    slots_by_league = {}
    for rec in records:
        inp = rec["owner_request"]["input"]
        pref = (inp.get("manager_preferences") or {}).get(inp["user_id"]) or {}
        if pref.get("starter_slots"):
            slots_by_league.setdefault(rec.get("league_id"), pref["starter_slots"])
    rows, failed = [], 0
    for rec in records:
        try:
            context, slots = load_request(rec, slots_by_league)
            rows.append(compare(candidate.generate_bilateral_trades, Request(context, slots)))
        except Exception as error:  # noqa: BLE001 - counted, never printed with data
            failed += 1
            print(f"request failed: {type(error).__name__}", file=sys.stderr)
    print(summarize(rows))
    if failed:
        print(f"failed requests: {failed}")
    return 0 if rows and all(r["same_set"] and r["page_eq_gated"] for r in rows) and not failed else 1


if __name__ == "__main__":
    sys.exit(main())
