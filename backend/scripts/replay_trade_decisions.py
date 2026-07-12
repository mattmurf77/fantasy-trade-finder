"""Offline replay of historical trade decisions — legacy vs trade-engine v2.

Tier 1 "Testing / Offline replay" (docs/plans/trade-engine-tier1-fixes.md):
load historical ``trade_decisions`` (likes/passes) and ``trade_matches``,
regenerate decks for each (user, league) with the legacy engine and with
the v2 engine (``trade_engine_v2`` flag toggled in-process), and compare:

  precision@5   fraction of the engine's top-5 cards whose
                (give, receive) frozenset pair matches a recorded *like*
  like recall   fraction of recorded likes appearing ANYWHERE in the deck
  match@5       fraction of historically *matched* trades ranked in the
                user's top-5
  multi share   fraction of deck cards involving >1 player on either side
  gen time      wall-clock seconds for generate_trades per league

Reconstruction caveats (best effort, read-only — never writes to the DB):
  * Rankings are each member's CURRENT ``member_rankings`` rows, not the
    rankings as of the decision timestamp (no historical snapshots exist).
  * The deck is regenerated WITHOUT the past-decision filter, so liked
    trades can re-surface and be scored.
  * Consensus seed Elo is rebuilt from the live DynastyProcess CSV, the
    same way the server seeds it.

Usage:
    python3 -m backend.scripts.replay_trade_decisions
"""
from __future__ import annotations

import inspect
import json
import time
from collections import defaultdict

from sqlalchemy import select

import backend.feature_flags as feature_flags
from backend.data_loader import _fetch_dynasty_process, normalise_name
from backend.database import (
    engine,
    league_members_table,
    load_players,
    member_rankings_table,
    trade_decisions_table,
    trade_matches_table,
)
from backend.ranking_service import Player
from backend.trade_service import League, LeagueMember, TradeService, reload_config

Pair = tuple[frozenset, frozenset]  # (give_ids, receive_ids) — user's POV

DEFAULT_FORMAT = "1qb_ppr"


# ---------------------------------------------------------------------------
# Feature-flag toggling (in-process, graceful when v2 hasn't landed yet)
# ---------------------------------------------------------------------------

def _find_v2_flag_key() -> str | None:
    """Return the dotted flag key whose attribute form is trade_engine_v2."""
    try:
        for key in feature_flags.DEFAULT_FLAGS:
            if feature_flags._key_to_attr(key) == "trade_engine_v2":
                return key
    except Exception:
        pass
    return None


def _set_v2_flag(key: str, enabled: bool) -> bool:
    """Flip the flag in the live in-process cache. Returns success."""
    try:
        feature_flags.flags_dict()  # force the cache to exist
        with feature_flags._flags_lock:
            if feature_flags._flags_cache is None:
                feature_flags._flags_cache = feature_flags._compute_flags()
            feature_flags._flags_cache[key] = enabled
        # Belt-and-braces: also shadow the proxy attribute (harmless extra).
        try:
            object.__setattr__(feature_flags.FLAGS, "trade_engine_v2", enabled)
        except Exception:
            pass
        return True
    except Exception as e:
        print(f"  could not toggle flag {key!r}: {e}")
        return False


# ---------------------------------------------------------------------------
# Pool + seed Elo (replicates server.build_universal_pool minimally,
# including the generic draft-pick pseudo-players, since member_rankings
# can contain generic_pick_* ids)
# ---------------------------------------------------------------------------

_PICK_SEEDS = {
    (1, "Early"): 1720, (1, "Mid"): 1650, (1, "Late"): 1580,
    (2, "Early"): 1520, (2, "Mid"): 1460, (2, "Late"): 1400,
    (3, "Early"): 1360, (3, "Mid"): 1320, (3, "Late"): 1280,
    (4, "Early"): 1260, (4, "Mid"): 1240, (4, "Late"): 1220,
}
_ORDINALS = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}
_PICK_POS = {1: "RB", 2: "WR", 3: "TE", 4: "QB"}

_pool_cache: dict[str, tuple[dict, dict]] = {}


def build_pool(scoring_format: str) -> tuple[dict[str, Player], dict[str, float]]:
    """Return (players_dict, seed_elo) for a scoring format. Cached."""
    if scoring_format in _pool_cache:
        return _pool_cache[scoring_format]

    elo_map, value_map, pos_map = _fetch_dynasty_process(scoring=scoring_format)
    players: dict[str, Player] = {}
    seeds: dict[str, float] = {}

    if not elo_map:
        print("  WARNING: DynastyProcess fetch failed — pool will be empty "
              "and every league will be skipped.")

    for row in load_players(position=None):
        pos = (row.get("position") or "").upper()
        if pos not in {"QB", "RB", "WR", "TE"}:
            continue
        name = row.get("full_name") or ""
        normed = normalise_name(name)
        if normed not in value_map:
            continue
        if pos_map.get(normed) != pos:
            continue  # #127 — never name-match across positions
        pid = str(row["player_id"])
        players[pid] = Player(
            id=pid,
            name=name,
            position=pos,
            team=row.get("team") or "FA",
            age=row.get("age") or 25,
            years_experience=row.get("years_exp") or 0,
            depth_chart_position=row.get("depth_chart_position"),
            depth_chart_order=row.get("depth_chart_order"),
            injury_status=row.get("injury_status"),
            search_rank=row.get("search_rank"),
            adp=row.get("adp"),
        )
        seeds[pid] = elo_map.get(normed, 1500.0)

    for (rnd, tier), seed_elo in _PICK_SEEDS.items():
        pick_id = f"generic_pick_{rnd}_{tier.lower()}"
        players[pick_id] = Player(
            id=pick_id,
            name=f"{tier} {_ORDINALS[rnd]} Round Pick",
            position=_PICK_POS.get(rnd, "QB"),
            team="PICK",
            age=0,
            pick_value=round(max(0, (seed_elo - 1200) / 6), 1),
            search_rank={1: 10, 2: 50, 3: 100, 4: 200}.get(rnd, 200),
        )
        seeds[pick_id] = float(seed_elo)

    _pool_cache[scoring_format] = (players, seeds)
    return players, seeds


# ---------------------------------------------------------------------------
# DB loads (read-only)
# ---------------------------------------------------------------------------

def load_decisions() -> dict[tuple[str, str], list[dict]]:
    """{(user_id, league_id): [decision rows]} with give/receive decoded."""
    out: dict[tuple[str, str], list[dict]] = defaultdict(list)
    with engine.connect() as conn:
        rows = conn.execute(select(trade_decisions_table)).fetchall()
    for r in rows:
        d = dict(r._mapping)
        try:
            d["give"] = frozenset(json.loads(d["give_player_ids"] or "[]"))
            d["receive"] = frozenset(json.loads(d["receive_player_ids"] or "[]"))
        except (json.JSONDecodeError, TypeError):
            continue
        out[(d["user_id"], d["league_id"])].append(d)
    return out


def load_matches() -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(select(trade_matches_table)).fetchall()
    out = []
    for r in rows:
        d = dict(r._mapping)
        try:
            d["a_give"] = frozenset(json.loads(d["user_a_give"] or "[]"))
            d["a_receive"] = frozenset(json.loads(d["user_a_receive"] or "[]"))
        except (json.JSONDecodeError, TypeError):
            continue
        out.append(d)
    return out


def matched_pairs_for(user_id: str, league_id: str, matches: list[dict]) -> set[Pair]:
    """Historically matched trades from this user's perspective."""
    pairs: set[Pair] = set()
    for m in matches:
        if m["league_id"] != league_id:
            continue
        if m["user_a_id"] == user_id:
            pairs.add((m["a_give"], m["a_receive"]))
        elif m["user_b_id"] == user_id:
            pairs.add((m["a_receive"], m["a_give"]))  # mirrored POV
    return pairs


def load_rankings_by_user(league_id: str, scoring_format: str) -> dict[str, dict[str, float]]:
    """{user_id: {player_id: elo}} for one league + format."""
    with engine.connect() as conn:
        rows = conn.execute(
            select(
                member_rankings_table.c.user_id,
                member_rankings_table.c.player_id,
                member_rankings_table.c.elo,
            ).where(
                member_rankings_table.c.league_id == league_id,
                member_rankings_table.c.scoring_format == scoring_format,
            )
        ).fetchall()
    out: dict[str, dict[str, float]] = defaultdict(dict)
    for user_id, player_id, elo in rows:
        out[user_id][player_id] = float(elo)
    return dict(out)


def load_rosters(league_id: str) -> dict[str, dict]:
    """{user_id: {username, player_ids}} from league_members."""
    with engine.connect() as conn:
        rows = conn.execute(
            select(league_members_table).where(
                league_members_table.c.league_id == league_id
            )
        ).fetchall()
    out: dict[str, dict] = {}
    for r in rows:
        d = dict(r._mapping)
        try:
            pids = [str(x) for x in json.loads(d.get("roster_data") or "[]")]
        except (json.JSONDecodeError, TypeError):
            pids = []
        out[d["user_id"]] = {
            "username": d.get("username") or d.get("display_name") or d["user_id"],
            "player_ids": pids,
        }
    return out


def league_formats(league_id: str) -> list[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            select(member_rankings_table.c.scoring_format)
            .where(member_rankings_table.c.league_id == league_id)
            .distinct()
        ).fetchall()
    return [r[0] for r in rows if r[0]] or [DEFAULT_FORMAT]


# ---------------------------------------------------------------------------
# Deck generation
# ---------------------------------------------------------------------------

def generate_deck(
    user_id: str,
    league_id: str,
    scoring_format: str,
) -> tuple[list[Pair] | None, float, str]:
    """Regenerate the deck for one (user, league).

    Returns (ordered card pairs | None, gen_seconds, skip_reason)."""
    players, seeds = build_pool(scoring_format)
    if not players:
        return None, 0.0, "player pool unavailable (DP fetch failed)"

    rosters = load_rosters(league_id)
    if user_id not in rosters:
        return None, 0.0, f"no league_members roster row for user {user_id}"
    rankings = load_rankings_by_user(league_id, scoring_format)
    if user_id not in rankings or not rankings[user_id]:
        return None, 0.0, f"no member_rankings for user {user_id} ({scoring_format})"

    user_roster = [p for p in rosters[user_id]["player_ids"] if p in players]
    if not user_roster:
        return None, 0.0, "user roster has no players in the universal pool"

    members: list[LeagueMember] = []
    for uid, info in rosters.items():
        if uid == user_id:
            continue
        roster = [p for p in info["player_ids"] if p in players]
        elo = rankings.get(uid, {})
        member = LeagueMember(
            user_id=uid,
            username=info["username"],
            roster=roster,
            elo_ratings=elo,  # empty dict → engine skips this opponent
        )
        try:  # v2 marks ranked members; harmless extra attr on legacy
            member.has_rankings = bool(elo)
        except Exception:
            pass
        members.append(member)

    if not any(m.elo_ratings and m.roster for m in members):
        return None, 0.0, "no opponent has both a roster and member_rankings"

    svc = TradeService(players=players)  # no past-decision filter on purpose
    svc.add_league(League(
        league_id=league_id, name=league_id, platform="replay", members=members,
    ))

    kwargs = dict(
        user_id=user_id,
        user_elo=rankings[user_id],
        user_roster=user_roster,
        league_id=league_id,
        seed_elo=seeds,
        scoring_format=scoring_format,
    )
    # Pass only kwargs the current signature accepts (v2 may add params,
    # e.g. `confidence`, while this branch is in flight).
    sig_params = inspect.signature(TradeService.generate_trades).parameters
    kwargs = {k: v for k, v in kwargs.items() if k in sig_params}
    if "confidence" in sig_params:
        kwargs["confidence"] = None  # no per-player comparison counts offline

    t0 = time.monotonic()
    cards = svc.generate_trades(**kwargs)
    elapsed = time.monotonic() - t0

    pairs = [
        (frozenset(c.give_player_ids), frozenset(c.receive_player_ids))
        for c in cards
    ]
    return pairs, elapsed, ""


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_metrics(deck: list[Pair], likes: set[Pair], matches: set[Pair]) -> dict:
    top5 = deck[:5]
    deck_set = set(deck)
    return {
        "cards": len(deck),
        "precision_at_5": (sum(1 for p in top5 if p in likes) / len(top5)) if top5 else 0.0,
        "like_recall": (len(likes & deck_set) / len(likes)) if likes else float("nan"),
        "match_at_5": (sum(1 for m in matches if m in top5) / len(matches)) if matches else float("nan"),
        "multi_share": (sum(1 for g, r in deck if len(g) + len(r) > 2) / len(deck)) if deck else 0.0,
    }


def _fmt(v: float) -> str:
    return "  n/a" if v != v else f"{v:5.2f}"  # NaN check


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    reload_config()  # use live model_config constants, same as the server

    print("=" * 74)
    print("Offline replay: trade_decisions vs regenerated decks (legacy vs v2)")
    print("=" * 74)

    decisions = load_decisions()
    matches = load_matches()
    n_dec = sum(len(v) for v in decisions.values())
    n_likes = sum(1 for v in decisions.values() for d in v if d["decision"] == "like")
    print(f"Loaded {n_dec} trade decisions ({n_likes} likes) across "
          f"{len(decisions)} (user, league) pairs; {len(matches)} trade matches.")
    print("NOTE: with n≈20 decisions these metrics are DIRECTIONAL ONLY — "
          "not statistically meaningful.")
    print("NOTE: decks are regenerated from CURRENT rankings/rosters (no "
          "historical snapshots exist), without the past-swipe filter.\n")

    if not decisions:
        print("No trade decisions in the DB — nothing to replay.")
        return

    v2_key = _find_v2_flag_key()
    engines = [("legacy", False)]
    if v2_key is None:
        print("trade_engine_v2 flag not found in backend.feature_flags — "
              "v2 not available; replaying with the legacy engine only.\n")
    else:
        engines.append(("v2", True))

    # metrics[engine] = list of per-(user,league) metric dicts
    all_metrics: dict[str, list[dict]] = defaultdict(list)
    rows: list[tuple] = []   # (label, engine, metrics, gen_s)

    for (user_id, league_id), decs in sorted(decisions.items()):
        likes = {(d["give"], d["receive"]) for d in decs if d["decision"] == "like"}
        mpairs = matched_pairs_for(user_id, league_id, matches)
        fmts = league_formats(league_id)
        fmt = fmts[0]
        label = f"{user_id} @ {league_id}"
        print(f"--- {label}  ({len(decs)} decisions, {len(likes)} likes, "
              f"{len(mpairs)} matches, format={fmt}) ---")

        for name, flag_on in engines:
            if v2_key is not None:
                if not _set_v2_flag(v2_key, flag_on):
                    print(f"  [{name}] could not set flag — skipping")
                    continue
            try:
                deck, gen_s, why = generate_deck(user_id, league_id, fmt)
            except Exception as e:  # v2 mid-landing must not crash the replay
                if flag_on and isinstance(e, AttributeError):
                    print(f"  [{name}] v2 not available yet (flag exists but "
                          f"the v2 code path is incomplete): {e}")
                else:
                    print(f"  [{name}] generation failed: {type(e).__name__}: {e}")
                continue
            finally:
                if v2_key is not None:
                    _set_v2_flag(v2_key, False)
            if deck is None:
                print(f"  [{name}] skipped: {why}")
                continue
            m = compute_metrics(deck, likes, mpairs)
            all_metrics[name].append(m)
            rows.append((label, name, m, gen_s))
            print(f"  [{name:6}] cards={m['cards']:<3} "
                  f"p@5={_fmt(m['precision_at_5'])} "
                  f"like-recall={_fmt(m['like_recall'])} "
                  f"match@5={_fmt(m['match_at_5'])} "
                  f"multi-share={_fmt(m['multi_share'])} "
                  f"gen={gen_s:.2f}s")
        print()

    # ── Comparison table (means across replayed (user, league) pairs) ───
    print("=" * 74)
    print("Summary (mean across replayed user-league pairs; n/a = no data)")
    print("=" * 74)
    header = f"{'metric':<22}" + "".join(f"{n:>10}" for n, _ in engines)
    print(header)

    def mean(vals: list[float]) -> float:
        vals = [v for v in vals if v == v]  # drop NaN
        return sum(vals) / len(vals) if vals else float("nan")

    for metric, label in [
        ("precision_at_5", "precision@5 (likes)"),
        ("like_recall", "like recall (deck)"),
        ("match_at_5", "matched-trade top-5"),
        ("multi_share", "multi-player share"),
        ("cards", "cards per league"),
    ]:
        line = f"{label:<22}"
        for name, _ in engines:
            ms = all_metrics.get(name, [])
            line += f"{_fmt(mean([m[metric] for m in ms])):>10}"
        print(line)
    line = f"{'gen wall-clock (s)':<22}"
    for name, _ in engines:
        ts = [g for (_, n, _, g) in rows if n == name]
        line += f"{_fmt(mean(ts)):>10}"
    print(line)

    for name, _ in engines:
        if not all_metrics.get(name):
            print(f"\n({name}: no leagues could be replayed — see per-league "
                  f"skip reasons above)")


if __name__ == "__main__":
    main()
