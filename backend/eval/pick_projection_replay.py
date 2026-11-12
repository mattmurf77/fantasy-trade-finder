"""Projected slot value replay: recorded owner decks with next-draft firsts re-priced.

Operator tooling, unflagged, no server wiring (docs/plans/pick-value-projected-slot/
design.md §10). For every recorded owner request in a directory (the layout of the
git-ignored ``data/prod-requests/``, as ``served_deck_replay`` reads it), it re-prices the
captured draft-season round-1 pick Elos with a slot projection and builds the served deck
both ways in one process: generic ("old", as recorded) and projected ("new").

Arms:

- ``synthetic``: per request, a random league order drawn around a seeded strength, at
  three concentrations approximating weeks 3, 10 and 14 (``CONCENTRATIONS``).
- ``real`` (``--forecasts FILE``): a JSON object ``{league_id: result_json}`` of the latest
  baseline run per replayed league, pulled read-only by the operator. League ids are used
  only to join; they are never printed.

The projection is applied at full strength (operator ruling 2026-11-11), or with the
weeks-played ramp under ``--season-scaling 1``.

Output is aggregate-only (counts, medians, percentiles): no ids, names, usernames or
league names.

    PYTHONHASHSEED=0 python -m backend.eval.pick_projection_replay --dir data/prod-requests
"""
from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
from pathlib import Path

CONCENTRATIONS = {"week3": 0.45, "week10": 0.25, "week14": 0.08}   # order noise vs strength spread
DEFAULT_DP_PICKS = (Path(__file__).resolve().parents[1] / "tests" / "fixtures"
                    / "dp_values_picks_2026-08-06.csv")


def owned_first(pid, league_id, season):
    """The ORIGINAL roster id of a ``season`` round-1 owned pick id, else None."""
    prefix = f"{league_id}_"
    if not isinstance(pid, str) or not pid.startswith(prefix):
        return None
    parts = pid[len(prefix):].split("_")
    if len(parts) < 3 or parts[0] != str(season) or parts[1] != "1":
        return None
    return parts[2]


def synthetic_result(roster_ids, *, seed, noise, playoff=None, worlds=2000, season=2027):
    """A forecast ``result_json`` built the way the simulation builds one: per world a
    noisy order around fixed strengths; the last ``playoff`` make the playoffs."""
    rng = random.Random(seed)
    n = len(roster_ids)
    playoff = playoff if playoff is not None else n // 2
    strength = {rid: rng.random() for rid in roster_ids}
    picks = {rid: [0] * (n - playoff) for rid in roster_ids}
    made = dict.fromkeys(roster_ids, 0)
    for _ in range(worlds):
        order = sorted(roster_ids, key=lambda r: strength[r] + rng.gauss(0, noise))
        for slot, rid in enumerate(order[:n - playoff]):
            picks[rid][slot] += 1
        for rid in order[n - playoff:]:
            made[rid] += 1
    return {"status": "complete", "model_version": "replay", "completed_weeks": 10,
            "playoff_spots": playoff, "config": {"draft_season": season},
            "teams": [{"roster_id": rid, "pick_probabilities": [c / worlds for c in picks[rid]],
                       "playoff_probability": made[rid] / worlds, "weeks": [{}] * 4}
                      for rid in roster_ids]}


def projection_from(result, *, season_scaling=0.0):
    from datetime import datetime, timezone
    from .. import pick_projection as pp
    summary = pp.compact(result, run_id="replay", created_at=datetime.now(timezone.utc).isoformat())
    if summary is None:
        return None
    return pp.usable(summary, model_version=summary.model_version, now=datetime.now(timezone.utc),
                     weight=1.0, min_weeks=0, max_age_days=1e9, max_round=1,
                     season_scaling=season_scaling)


def reprice(context, projection, *, season, scoring_format):
    """A copy of the generator kwargs with every captured ``season`` 1st re-priced
    (seed, the viewer's board and every member board, as ``_inject_owned_picks`` does),
    plus ``{pid: (old value, new value)}``."""
    import copy
    from .. import pick_projection as pp
    from .. import trade_service as ts
    from ..pick_values import projected_slot_curve
    league_id = context["league"].league_id
    seed = context["seed_elo"]
    curve = projected_slot_curve(projection.teams, season, 1, scoring_format)
    if curve is None:
        return context, {}
    new_elo, deltas = {}, {}
    for pid, elo in seed.items():
        rid = owned_first(pid, league_id, season)
        dist = pp.distribution(projection, rid) if rid is not None else None
        if dist is None or len(dist) != len(curve):
            continue
        old = ts.elo_to_value(elo)
        new = round(old * pp.factor(projection, dist, curve), 1)
        new_elo[pid] = ts.value_to_elo(new)
        deltas[pid] = (old, new)
    out = dict(context)
    out["seed_elo"] = {**seed, **new_elo}
    out["user_elo"] = {**context["user_elo"], **{p: e for p, e in new_elo.items()
                                                  if p in context["user_elo"]}}
    league = copy.copy(context["league"])
    league.members = []
    for m in context["league"].members:
        m2 = copy.copy(m)
        m2.elo_ratings = {**(m.elo_ratings or {}), **{p: e for p, e in new_elo.items()
                                                       if p in (m.elo_ratings or {})}}
        league.members.append(m2)
    out["league"] = league
    return out, deltas


def _has_first(card, league_id, season):
    return any(owned_first(p, league_id, season) is not None
               for p in (*card.give_player_ids, *card.receive_player_ids))


def compare(generate, request_cls, context, slots, projection, *, season, scoring_format):
    """One request, both prices, in this process: a dict of aggregates (no ids)."""
    def identity(c):
        return c.target_user_id, tuple(c.give_player_ids), tuple(c.receive_player_ids)
    league_id = context["league"].league_id
    new_context, deltas = reprice(context, projection, season=season, scoring_format=scoring_format)
    old_req, new_req = request_cls(context, slots), request_cls(new_context, slots)
    old_full, _ = generate(**context)
    new_full, _ = generate(**new_context)
    old, old_counts = old_req.served(old_full)
    new, new_counts = new_req.served(new_full)
    a, b = [identity(c) for c in old], [identity(c) for c in new]
    olds = [v[0] for v in deltas.values()]
    news = [v[1] for v in deltas.values()]
    return {"served_old": len(a), "served_new": len(b), "changed": set(a) != set(b),
            "kept_share": (len(set(a) & set(b)) / len(a)) if a else 1.0,
            "first_cards_old": sum(_has_first(c, league_id, season) for c in old),
            "first_cards_new": sum(_has_first(c, league_id, season) for c in new),
            "rule_rejects_old": sum(v for k, v in old_counts.items() if k in ("filler", "breakup", "redundant")),
            "rule_rejects_new": sum(v for k, v in new_counts.items() if k in ("filler", "breakup", "redundant")),
            "pick_delta_pct": [100.0 * (n / o - 1.0) for o, n in deltas.values() if o > 0],
            "complete_league": len(deltas) == projection.teams,
            "conservation": (sum(news) / sum(olds)) if deltas and sum(olds) else None}


def _pct(values, p):
    values = sorted(values)
    return values[min(len(values) - 1, int(p * len(values)))] if values else None


def summarize(rows_by_arm):
    lines = []
    for arm, rows in rows_by_arm.items():
        n = len(rows)
        lines.append(f"[{arm}] requests replayed: {n}")
        if not n:
            continue
        lines.append(f"[{arm}] decks whose served set changed: {sum(r['changed'] for r in rows)} of {n}")
        kept = [r["kept_share"] for r in rows]
        lines.append(f"[{arm}] share of old cards still served: median {statistics.median(kept):.3f} "
                     f"p10 {_pct(kept, .1):.3f} min {min(kept):.3f}")
        lost = [1 - r["served_new"] / r["served_old"] for r in rows if r["served_old"]]
        if lost:
            lines.append(f"[{arm}] deck size lost: median {statistics.median(lost):.3f} "
                         f"max {max(lost):.3f} (bar: <= 0.20; over the bar: "
                         f"{sum(1 for x in lost if x > 0.20)} of {len(lost)}; "
                         f"smallest new deck: {min(r['served_new'] for r in rows if r['served_old'])} cards)")
        for key in ("first_cards_old", "first_cards_new", "rule_rejects_old", "rule_rejects_new"):
            lines.append(f"[{arm}] {key}: total {sum(r[key] for r in rows)}")
        deltas = [d for r in rows for d in r["pick_delta_pct"]]
        if deltas:
            lines.append(f"[{arm}] pick value change %: min {min(deltas):.1f} p10 {_pct(deltas, .1):.1f} "
                         f"median {statistics.median(deltas):.1f} p90 {_pct(deltas, .9):.1f} "
                         f"max {max(deltas):.1f} (n={len(deltas)})")
        cons = [abs(r["conservation"] - 1) for r in rows if r["complete_league"] and r["conservation"]]
        lines.append(f"[{arm}] conservation |sum new / sum old - 1| over complete leagues: "
                     + (f"max {max(cons):.4f} (n={len(cons)})" if cons else "none complete"))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dir", required=True, help="recorded requests (index.json, model_config.json)")
    parser.add_argument("--forecasts", help="JSON {league_id: result_json} for the real arm")
    parser.add_argument("--dp-picks", default=str(DEFAULT_DP_PICKS),
                        help="DynastyProcess values.csv to price picks with (offline)")
    parser.add_argument("--season", type=int, default=2027, help="the draft season priced")
    parser.add_argument("--season-scaling", type=float, default=0.0)
    parser.add_argument("--arms", default="synthetic,real")
    parser.add_argument("--latest", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    os.environ.setdefault("DATABASE_URL", "sqlite://")   # never the app database
    os.environ["FTF_DP_PICK_VALUES_FILE"] = args.dp_picks
    import socket

    def _no_network(*_args, **_kwargs):
        raise RuntimeError("pick_projection_replay is offline")
    socket.socket.connect = socket.socket.connect_ex = socket.create_connection = _no_network
    from .. import database, feature_flags, trade_service as ts
    from .. import trade_gen_bilateral_candidate as candidate
    from .served_deck_replay import Request, load_request
    database.metadata.create_all(database.engine)
    feature_flags._flags_cache = feature_flags._load_from_json(
        Path(__file__).resolve().parents[2] / "config" / "features.json")
    index = json.load(open(os.path.join(args.dir, "index.json")))
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    model_config = os.path.join(args.dir, "model_config.json")
    if os.path.exists(model_config):
        ts._cfg.update(json.load(open(model_config)))
    if args.latest:
        latest = {}
        for r in index:
            if r["pair"] not in latest or r["created_at"] > latest[r["pair"]]["created_at"]:
                latest[r["pair"]] = r
        index = list(latest.values())
    records = [json.load(open(os.path.join(args.dir, r["file"]))) for r in index[:args.limit]]
    forecasts = json.load(open(args.forecasts)) if args.forecasts else {}
    arms = [a for a in args.arms.split(",") if a]
    rows = {f"synthetic-{k}": [] for k in CONCENTRATIONS} if "synthetic" in arms else {}
    if "real" in arms and forecasts:
        rows["real"] = []
    failed = skipped = 0
    for i, rec in enumerate(records):
        try:
            context, slots = load_request(rec, {})
            league_id = context["league"].league_id
            fmt = context.get("scoring_format", "1qb_ppr")
            rids = sorted({rid for pid in context["seed_elo"]
                           if (rid := owned_first(pid, league_id, args.season)) is not None},
                          key=lambda r: (len(r), r))
            n_teams = len(context["league"].members) + (0 if any(
                str(m.user_id) == str(context["user_id"]) for m in context["league"].members) else 1)
            if not rids:
                skipped += 1
                continue
            ids = rids + [f"absent{k}" for k in range(max(0, n_teams - len(rids)))]
            if "synthetic" in arms:
                for k, noise in CONCENTRATIONS.items():
                    proj = projection_from(synthetic_result(ids, seed=i, noise=noise, season=args.season),
                                           season_scaling=args.season_scaling)
                    rows[f"synthetic-{k}"].append(compare(
                        candidate.generate_bilateral_trades, Request, context, slots, proj,
                        season=args.season, scoring_format=fmt))
            if "real" in rows and league_id in forecasts:
                proj = projection_from(forecasts[league_id], season_scaling=args.season_scaling)
                if proj is not None:
                    rows["real"].append(compare(candidate.generate_bilateral_trades, Request, context,
                                                slots, proj, season=args.season, scoring_format=fmt))
        except Exception as error:  # noqa: BLE001 - counted, never printed with data
            failed += 1
            print(f"request failed: {type(error).__name__}", file=sys.stderr)
    print(summarize(rows))
    print(f"requests without a {args.season} 1st in the pool: {skipped}")
    if failed:
        print(f"failed requests: {failed}")
    return 0 if any(rows.values()) and not failed else 1


if __name__ == "__main__":
    sys.exit(main())
