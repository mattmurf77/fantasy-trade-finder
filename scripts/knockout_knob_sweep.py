#!/usr/bin/env python3
"""
knockout_knob_sweep.py — read-only knob replay for the consolidation bundle
==========================================================================

Measurement half of docs/plans/knockout-refine/plan.md §6. Replays one real
league through the REAL generation stack under three `model_config`
variants and reports what each one would actually serve:

    baseline        prod as it stands today
    bundle          filler_min_frac 0.15 (asset_floor_abs 450 HELD)
                    + trade_elo_gap_max 0
                    + v3_shape_max_delta 2
    bundle-filler10 the same bundle with filler_min_frac 0.10

The three flips are measured together, never one at a time, because the
knockouts NEST (G-058): the gates are conjunctive and 97.6 % of rejections
are made by two or more rules at once, so moving one knob alone reads as
"no effect" and wrongly exonerates it.

Per variant it reports:

    cards               every card the engine generated, all viewers
    distinct ideas      after the engine's OWN Jaccard dedupe
                        (`v3_diversity_max_overlap`, read live — not a
                        number this script invents)
    viewer-favoured     share of cards whose consensus package value comes
                        back HIGHER than it goes out, for the viewer
    sub-450 bodies      share of multi-asset sides carrying an asset below
                        `asset_floor_abs` — the "did loosening the filler
                        floor let junk back in" question
    shape mix           GxR counts; 3x1 / 1x3 are what C4 unlocks

READ-ONLY, and it proves it rather than promising it
----------------------------------------------------
1. `backend.database.init_db` is stubbed out BEFORE `backend.server` is
   imported. That call is `CREATE TABLE IF NOT EXISTS` + the idempotent
   `model_config` seed — harmless in normal operation, but it is DDL and
   DDL is a write. On a real database the schema already exists, so
   skipping it costs nothing.
2. A `before_cursor_execute` guard is installed on every engine
   `backend.database` owns. Any statement that is not a read raises
   `ReadOnlyViolation` and aborts the run. There is no flag to turn it off.
3. `log_trade_impressions` is never called, and neither is the deck
   ordering / likes-you injection that would need a write to be faithful.

`backend.server`'s import still fetches the Sleeper player cache and the
DynastyProcess consensus over HTTP, exactly as `scripts/deck_eval.py`
does. That is network, not database, and it is read-only too.

What this is NOT
----------------
Not a production serving count. It measures GENERATION under a uniform
`--max-per-opponent` for every variant, deliberately higher than the live
default, so the comparison is about which candidates survive the gates
rather than about which survivors the deck trimmer keeps (G-058 cause 1:
`server._split_exploration_pool` trims to a hardcoded 5 downstream of
every knob here). Absolute card counts are therefore larger than a served
deck; the DIFFERENCES between variants are the product.

Usage
-----
    DATABASE_URL=postgresql://…  python3 scripts/knockout_knob_sweep.py
    DATABASE_URL=sqlite:///data/trade_finder.db \\
        python3 scripts/knockout_knob_sweep.py --league 1312140920132497408

    --league ID             league to replay (default: the §6 league)
    --format FMT            scoring format (default 1qb_ppr)
    --max-per-opponent N    uniform per-pair card cap (default 30)
    --json PATH             also write the machine-readable record
"""

import argparse
import json
import os
import pathlib
import sys
import time
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_LEAGUE = "1312140920132497408"          # plan §6 — 6 boarded members

#: The consolidation bundle and its variants. `None` means "leave alone".
VARIANTS: dict[str, dict[str, float]] = {
    "baseline": {},
    "bundle": {
        "filler_min_frac":    0.15,
        "asset_floor_abs":  450.0,               # HELD, stated for the record
        "trade_elo_gap_max":  0.0,
        "v3_shape_max_delta": 2.0,
    },
    "bundle-raw-r1": {                       # plan §6: C2 both ways — the
        "filler_min_frac":    0.15,          # bundle with overpay back in RAW
        "asset_floor_abs":  450.0,           # sums (adjusted taxes raw-even
        "trade_elo_gap_max":  0.0,           # 3-for-1s; measure, don't guess)
        "v3_shape_max_delta": 2.0,
        "overpay_adjusted":   0.0,
    },
    "bundle-filler10": {
        "filler_min_frac":    0.10,
        "asset_floor_abs":  450.0,
        "trade_elo_gap_max":  0.0,
        "v3_shape_max_delta": 2.0,
    },
}


class ReadOnlyViolation(RuntimeError):
    """A generation path tried to write. The run aborts rather than continue."""


# ---------------------------------------------------------------------------
# 0. Environment gate — fail fast, in words, before anything is imported
# ---------------------------------------------------------------------------

def _require_database_url() -> str:
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        sys.stderr.write(
            "\nknockout_knob_sweep: DATABASE_URL is not set.\n\n"
            "This script replays a REAL league out of a REAL database; it has\n"
            "no fixture mode and will not silently fall back to the local\n"
            "default DB, because a sweep run against the wrong data is worse\n"
            "than no sweep at all.\n\n"
            "Set it to the database you mean to read, e.g.\n"
            "    DATABASE_URL='postgresql://…' python3 scripts/knockout_knob_sweep.py\n"
            "    DATABASE_URL='sqlite:///data/trade_finder.db' python3 "
            "scripts/knockout_knob_sweep.py\n\n"
            "The prod URL lives in secrets.local.env as DATABASE_URL_PROD.\n"
            "Every access this script makes is read-only and enforced as such.\n\n")
        raise SystemExit(2)
    return url


# ---------------------------------------------------------------------------
# 1. Read-only enforcement + import
# ---------------------------------------------------------------------------

_READ_PREFIXES = ("select", "with", "pragma", "begin", "commit", "rollback",
                  "set", "show", "explain", "savepoint", "release")


def _install_readonly_guard(engine) -> None:
    from sqlalchemy import event

    @event.listens_for(engine, "before_cursor_execute")
    def _guard(conn, cursor, statement, parameters, context, executemany):
        head = statement.lstrip().lstrip("(").split(None, 1)
        word = head[0].lower() if head else ""
        if word not in _READ_PREFIXES:
            raise ReadOnlyViolation(
                f"blocked a non-read statement on {engine.url.drivername}: "
                f"{statement.strip()[:200]!r}")


def _boot():
    """Import the backend with writes disarmed. Order matters: the guard and
    the init_db stub must both be in place before `backend.server` runs its
    module body."""
    import backend.database as db

    for eng in {id(db.engine): db.engine,
                id(db.ingest_engine): db.ingest_engine,
                id(db.ro_engine): db.ro_engine}.values():
        _install_readonly_guard(eng)

    # DDL is a write. `backend.server` does `from .database import init_db`
    # at ITS import time, so patching the attribute here is what that name
    # resolves to. On a real DB the schema is already there.
    db.init_db = lambda: None

    import logging
    logging.getLogger("trade_finder").setLevel(logging.WARNING)

    t0 = time.perf_counter()
    from backend import server as srv
    import backend.trade_service as ts
    import backend.trade_optimizer as topt
    from backend.feature_flags import FLAGS
    return db, srv, ts, topt, FLAGS, time.perf_counter() - t0


# ---------------------------------------------------------------------------
# 2. Variant application
# ---------------------------------------------------------------------------

@contextmanager
def variant_config(ts, overrides: dict):
    """Apply a variant BOTH ways, and that is not belt-and-braces padding.

    The engine has two config readers and they do not see the same thing.
    `trade_service._c()` consults the `_cfg_override` thread-local before
    the live map, and every knob in `_DEFAULT_CFG` — `filler_min_frac`,
    `trade_elo_gap_max`, `asset_floor_abs`, and C4's `v3_shape_max_delta` —
    is read that way. But `trade_optimizer` also reads keys that are NOT in
    `_DEFAULT_CFG` (`v3_pool_size`, `sweetener_band`, the `cycle_*` family)
    as `_ts._cfg.get(key, default)`, which never looks at the overlay. A
    sweep that used only one of the two mechanisms would silently measure
    the baseline for whichever knobs the other one owns — G-058 cause 3
    wearing a different hat, and the worst possible failure here because it
    reads as "the bundle does nothing".

    So: enter `_cfg_override` AND write the live map, restoring the map
    exactly afterwards, then verify both readers agree before generating a
    single card. Safe because this script is single-threaded; do NOT copy
    the direct-write half into request-serving code, which is precisely
    what `_cfg_override` exists to avoid (#189).
    """
    if not overrides:
        yield
        return
    saved = {k: ts._cfg[k] for k in overrides if k in ts._cfg}
    absent = [k for k in overrides if k not in ts._cfg]
    try:
        ts._cfg.update(overrides)
        with ts._cfg_override(overrides):
            _assert_variant_visible(ts, overrides)
            yield
    finally:
        ts._cfg.update(saved)
        for k in absent:
            ts._cfg.pop(k, None)


def _assert_variant_visible(ts, overrides: dict) -> None:
    """Prove the variant actually landed on BOTH read paths before a single
    card is generated. A sweep that silently measures the baseline three
    times is the worst possible outcome here — it would read as "the bundle
    does nothing" and retire a knob that was never tested."""
    for key, want in overrides.items():
        got_map = ts._cfg.get(key)
        if got_map != want:
            raise RuntimeError(
                f"variant knob {key}={want} did not reach trade_service._cfg "
                f"(saw {got_map!r})")
        try:
            got_c = ts._c(key)
        except KeyError:
            continue            # optimizer-only key: no _c() reader exists
        if got_c != want:
            raise RuntimeError(
                f"variant knob {key}={want} did not reach trade_service._c() "
                f"(saw {got_c!r})")


# ---------------------------------------------------------------------------
# 3. League bootstrap (all from the DB — no Sleeper roster fetch needed)
# ---------------------------------------------------------------------------

def load_league(db, srv, league_id: str, fmt: str):
    """Return (players_dict, seed_map, rosters, boards, usernames).

    `boards[user_id]` is that member's REAL saved board; only members who
    have one are viewers, because a consensus-seeded viewer has no
    divergence and the divergence path would have nothing to work with.
    """
    pool, seed_map = srv._get_universal_pool(fmt)
    if not pool:
        # `_build_universal_pools_locked` returns early when the Sleeper
        # player cache is missing, and every downstream emptiness then looks
        # like "this league has no data". Name the real cause instead.
        raise SystemExit(
            "\nknockout_knob_sweep: the universal player pool for "
            f"{fmt!r} is EMPTY.\n"
            "That is a missing Sleeper player cache, not a missing league: "
            "backend.server\nbuilds the pool from data/.sleeper_players_cache.json "
            "and returns an empty\npool when that file is absent (a fresh git "
            "worktree has no data/ contents).\n"
            "Copy or symlink the cache from the main checkout, or run this "
            "script from\nthere.\n")
    players = {p.id: p for p in pool}

    rosters, usernames = {}, {}
    for m in db.load_league_members(league_id):
        ids = [str(x) for x in (m.get("player_ids") or []) if str(x) in players]
        if not ids:
            continue
        rosters[m["user_id"]] = ids
        usernames[m["user_id"]] = (m.get("username") or m.get("display_name")
                                   or m["user_id"])

    # exclude_user_id is required by the signature; a sentinel excludes nobody.
    raw = db.load_member_rankings(league_id=league_id,
                                  exclude_user_id="__sweep_excludes_nobody__",
                                  scoring_format=fmt)
    boards = {}
    for uid, rec in raw.items():
        if rec.get("elo_ratings") and uid in rosters:
            boards[uid] = dict(rec["elo_ratings"])
            usernames[uid] = rec.get("username") or usernames.get(uid, uid)
    return players, seed_map, rosters, boards, usernames


def generate_for_viewer(ts_mod, srv, *, viewer, players, seed_map, rosters,
                        boards, usernames, league_id, fmt, max_per_opponent):
    """One viewer's full sweep: the real `generate_trades`, which runs the
    divergence (v3) and consensus generators over every ordered pair."""
    from backend.trade_service import League, LeagueMember, TradeService

    members = []
    for uid, roster in rosters.items():
        if uid == viewer:
            continue
        elo = boards.get(uid) or {p: seed_map.get(p, 1500.0) for p in roster}
        members.append(LeagueMember(user_id=uid, username=usernames.get(uid, uid),
                                    roster=roster, elo_ratings=dict(elo),
                                    has_rankings=uid in boards))
    league = League(league_id=league_id, name=league_id, platform="sleeper",
                    members=members)

    svc = TradeService(players=players, past_decision_keys=set())
    svc.add_league(league)
    return svc.generate_trades(
        user_id=viewer,
        user_elo=dict(boards[viewer]),
        user_roster=rosters[viewer],
        league_id=league_id,
        seed_elo=seed_map,
        max_per_opponent=max_per_opponent,
        fairness_threshold=0.75,
        acquire_positions=[],
        trade_away_positions=[],
        scoring_format=fmt,
    )


# ---------------------------------------------------------------------------
# 4. Metrics
# ---------------------------------------------------------------------------

def _jaccard(a: set, b: set) -> float:
    u = a | b
    return len(a & b) / len(u) if u else 0.0


def measure(cards_by_viewer, ts, topt, seed_map, players) -> dict:
    """Every number here is derived with the engine's own definitions and
    the engine's own live knobs, so a knob change cannot make the metric
    and the behaviour it measures drift apart."""
    from backend.trade_service import elo_to_value

    def sv(pid):
        return elo_to_value(seed_map.get(pid, 1500.0))

    max_overlap = float(ts._cfg.get("v3_diversity_max_overlap", 0.4))
    floor_abs = float(ts._c("asset_floor_abs"))

    n_cards = 0
    n_ideas = 0
    viewer_favoured = 0
    multi_sides = 0
    multi_sides_sub_floor = 0
    shapes = Counter()

    for viewer, cards in cards_by_viewer.items():
        # Distinct ideas — the engine's own diversity rule, applied per
        # (viewer, partner) exactly as `generate_pair_trades_v3` applies it,
        # greedy over the composite ranking so the best card anchors.
        kept: dict[str, list[set]] = {}
        for card in sorted(cards, key=lambda c: -getattr(c, "composite_score", 0.0)):
            n_cards += 1
            give = list(card.give_player_ids)
            recv = list(card.receive_player_ids)
            shapes[f"{len(give)}x{len(recv)}"] += 1

            gv, rv = topt._consensus_packages(give, recv, sv)
            if rv > gv:
                viewer_favoured += 1

            for side in (give, recv):
                if len(side) >= 2:
                    multi_sides += 1
                    if any(sv(p) < floor_abs for p in side):
                        multi_sides_sub_floor += 1

            partner = getattr(card, "target_user_id", None) or \
                getattr(card, "target_username", "?")
            assets = set(give) | set(recv)
            prior = kept.setdefault(partner, [])
            if all(_jaccard(assets, k) < max_overlap for k in prior):
                prior.append(assets)
                n_ideas += 1

    def pct(num, den):
        return round(100.0 * num / den, 1) if den else None

    return {
        "cards": n_cards,
        "distinct_ideas": n_ideas,
        "viewer_favoured_pct": pct(viewer_favoured, n_cards),
        "multi_asset_sides": multi_sides,
        "sub_floor_body_pct": pct(multi_sides_sub_floor, multi_sides),
        "asset_floor_abs": floor_abs,
        "diversity_max_overlap": max_overlap,
        "shape_mix": dict(sorted(shapes.items(),
                                 key=lambda kv: (-kv[1], kv[0]))),
    }


# ---------------------------------------------------------------------------
# 5. Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--league", default=DEFAULT_LEAGUE)
    ap.add_argument("--format", default="1qb_ppr", dest="fmt")
    ap.add_argument("--max-per-opponent", type=int, default=30)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    url = _require_database_url()
    print(f"knockout_knob_sweep — league {args.league} · {args.fmt} · "
          f"max_per_opponent={args.max_per_opponent}")
    print(f"  DATABASE_URL scheme: {url.split(':', 1)[0]} (reads only, enforced)")

    db, srv, ts, topt, FLAGS, import_s = _boot()
    print(f"  backend imported in {import_s:.1f}s")

    players, seed_map, rosters, boards, usernames = load_league(
        db, srv, args.league, args.fmt)
    if not boards:
        sys.stderr.write(
            f"\nknockout_knob_sweep: league {args.league} has no saved member "
            f"boards in {args.fmt}.\nThere is nothing to replay — the "
            f"divergence path needs at least two real boards.\n\n")
        return 3
    print(f"  {len(rosters)} rostered members, {len(boards)} with real boards: "
          + ", ".join(sorted(usernames.get(u, u) for u in boards)))

    results = {}
    for name, overrides in VARIANTS.items():
        t0 = time.perf_counter()
        cards_by_viewer = {}
        with variant_config(ts, overrides):
            for viewer in sorted(boards):
                cards_by_viewer[viewer] = generate_for_viewer(
                    ts, srv, viewer=viewer, players=players, seed_map=seed_map,
                    rosters=rosters, boards=boards, usernames=usernames,
                    league_id=args.league, fmt=args.fmt,
                    max_per_opponent=args.max_per_opponent)
            m = measure(cards_by_viewer, ts, topt, seed_map, players)
        m["overrides"] = overrides
        m["seconds"] = round(time.perf_counter() - t0, 1)
        results[name] = m
        print(f"\n=== {name} ({m['seconds']}s) ===")
        print(f"  overrides           {overrides or '(none — prod as-is)'}")
        print(f"  cards               {m['cards']}")
        print(f"  distinct ideas      {m['distinct_ideas']}")
        print(f"  viewer-favoured     {m['viewer_favoured_pct']}%")
        print(f"  multi-asset sides   {m['multi_asset_sides']}"
              f"  (sub-{int(m['asset_floor_abs'])} body: "
              f"{m['sub_floor_body_pct']}%)")
        print(f"  shape mix           {m['shape_mix']}")

    print("\n=== deltas vs baseline ===")
    base = results["baseline"]
    for name, m in results.items():
        if name == "baseline":
            continue
        print(f"  {name:<18} cards {m['cards'] - base['cards']:+d} · "
              f"ideas {m['distinct_ideas'] - base['distinct_ideas']:+d} · "
              f"3x1/1x3 "
              f"{m['shape_mix'].get('3x1', 0) + m['shape_mix'].get('1x3', 0)} "
              f"(baseline "
              f"{base['shape_mix'].get('3x1', 0) + base['shape_mix'].get('1x3', 0)})")

    if args.json:
        payload = {"captured_at": datetime.now(timezone.utc).isoformat(),
                   "league": args.league, "format": args.fmt,
                   "max_per_opponent": args.max_per_opponent,
                   "variants": results}
        pathlib.Path(args.json).write_text(json.dumps(payload, indent=2))
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
