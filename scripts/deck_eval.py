#!/usr/bin/env python3
"""
deck_eval.py — Offline deck-quality + timing eval (onboarding-conversion GATE)
==============================================================================
Build item 2 of docs/plans/onboarding-conversion/plan.md: before the
trades-first onboarding ships, prove that consensus-seeded first decks are
hook-quality for a brand-new user, and measure the latency budget.

For each league (real Sleeper league IDs), the script fetches rosters/users
from the public Sleeper API (read-only), then for EACH team simulates a
brand-new user's very first session:

  - fresh RankingService per scoring format, consensus seed only
    (no swipes, no tier overrides, no saved preferences, no past decisions)
  - League/TradeService built the same way /api/session/init builds them
    (trade-engine v2 path: opponents carry the consensus seed verbatim)
  - deck generated the same way the /api/trades/generate worker
    (_run_trade_job) does: member-rankings injection for OTHER members,
    roster-seeded outlook, opponent outlook/pick-share assembly, likes-you
    injection, Thompson/diversity ordering — all under the exact
    production config/features.json flags (incl. trade.need_fit fit-led
    ordering).

Implementation: internal import of backend.server (no Flask server needed).
The only deviations from the live worker, all deliberate:
  - user-personal DB state for the SIMULATED user is masked (a brand-new
    user has none): no swipe replay, no league preference, no asset prefs,
    no past trade decisions, and load_trade_decision_shape_counts is
    stubbed to {} for the Thompson prior;
  - log_trade_impressions is NOT called (the eval must not write
    training-data rows).
Nothing in backend/ is modified; DB access is read-only apart from
backend import-time init_db() (idempotent CREATE TABLE IF NOT EXISTS).

Usage:
  python3 scripts/deck_eval.py 1312076055586050048 [more league ids...]
  python3 scripts/deck_eval.py --sample 10
  python3 scripts/deck_eval.py --sleeper-username someuser
Options:
  --max-teams N   cap teams evaluated per league (default: all)
  --report PATH   markdown report path
                  (default docs/plans/onboarding-conversion/deck-eval-report.md)

Outputs:
  feedback-workspace/deck-eval/deck_eval_<UTC ts>.json    (machine-readable)
  docs/plans/onboarding-conversion/deck-eval-report.md    (human scoring)
"""

import argparse
import concurrent.futures
import json
import logging
import pathlib
import statistics
import sys
import time
from datetime import datetime, timezone

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Importing backend.server runs its module-level setup: init_db(), model
# config load, Sleeper player cache + DynastyProcess consensus fetch, demo
# league build. That is exactly the state a warm production process holds.
print("Importing backend.server (warm-process setup: DB, consensus, pools)...")
_t_import = time.perf_counter()
from backend import server as srv                      # noqa: E402
from backend import database as db                     # noqa: E402
from backend.ranking_service import RankingService     # noqa: E402
from backend.trade_service import (                    # noqa: E402
    TradeService, League, LeagueMember, elo_to_value,
)
from backend.feature_flags import FLAGS, is_enabled, flags_dict  # noqa: E402

IMPORT_S = time.perf_counter() - _t_import

# Quiet the backend's DEBUG firehose for the eval run; failures still surface.
logging.getLogger("trade_finder").setLevel(logging.WARNING)

SLEEPER = "https://api.sleeper.app/v1"
FAIRNESS_THRESHOLD_DEFAULT = 0.75   # /api/trades/generate default (no pins)

# Auto red-flag heuristics for the summary (human scoring is the real gate).
# REDFLAG_DELTA catches cards the engine's marginal-value fairness passes but
# whose raw consensus totals are heavily adverse to the first-run user.
REDFLAG_FAIRNESS = 0.70
REDFLAG_DELTA = -1000


# ---------------------------------------------------------------------------
# League selection
# ---------------------------------------------------------------------------

def leagues_from_db(n: int) -> list[str]:
    """Distinct real (numeric) Sleeper league ids from the local DB."""
    from sqlalchemy import text
    with db.engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT DISTINCT sleeper_league_id FROM leagues")).fetchall()
    ids = [r[0] for r in rows if str(r[0]).isdigit()]
    return ids[:n]


def leagues_from_username(username: str) -> list[str]:
    user = srv._sleeper_get(f"{SLEEPER}/user/{username}")
    if not user or not user.get("user_id"):
        raise SystemExit(f"Sleeper user not found: {username!r}")
    lgs = srv._sleeper_get(
        f"{SLEEPER}/user/{user['user_id']}/leagues/nfl/2026") or []
    return [lg["league_id"] for lg in lgs]


# ---------------------------------------------------------------------------
# Sleeper fetch (read-only, same helper the backend uses)
# ---------------------------------------------------------------------------

def fetch_league(league_id: str) -> dict | None:
    t0 = time.perf_counter()
    meta = srv._sleeper_get(f"{SLEEPER}/league/{league_id}")
    rosters = srv._sleeper_get(f"{SLEEPER}/league/{league_id}/rosters")
    users = srv._sleeper_get(f"{SLEEPER}/league/{league_id}/users")
    fetch_ms = (time.perf_counter() - t0) * 1000
    if not meta or not rosters:
        return None
    username_map = {u["user_id"]: (u.get("display_name") or u.get("username")
                                   or u["user_id"]) for u in (users or [])}
    teams = []
    for r in rosters:
        owner = r.get("owner_id")
        players = [str(p) for p in (r.get("players") or []) if p]
        if owner and players:
            teams.append({
                "user_id": str(owner),
                "username": username_map.get(owner, f"Team {r.get('roster_id')}"),
                "player_ids": players,
            })
    return {
        "league_id": league_id,
        "name": meta.get("name") or league_id,
        "total_rosters": meta.get("total_rosters"),
        "teams": teams,
        "fetch_ms": round(fetch_ms, 1),
    }


# ---------------------------------------------------------------------------
# Per-team first-run simulation
# ---------------------------------------------------------------------------

def build_first_run_session(league_info: dict, team: dict,
                            active_format: str) -> tuple[dict, float]:
    """Build what /api/session/init builds for a brand-new user (no personal
    DB state). Returns (session-like dict, init_ms)."""
    t0 = time.perf_counter()
    user_id = team["user_id"]
    default_pool, _default_seed = srv._get_universal_pool("1qb_ppr")
    players_dict_default = {p.id: p for p in default_pool}

    # Opponent members — trade-engine v2 path: consensus seed verbatim,
    # has_rankings=False (server.py session_init _v2 branch).
    fmt_seed_by_fmt = {}
    for fmt in db.SCORING_FORMATS:
        _, fmt_seed_by_fmt[fmt] = srv._get_universal_pool(fmt)
    ranking_seed = dict(fmt_seed_by_fmt["1qb_ppr"])

    members = []
    for opp in league_info["teams"]:
        if opp["user_id"] == user_id:
            continue
        opp_ids = [pid for pid in opp["player_ids"] if pid in players_dict_default]
        if not opp_ids:
            continue
        members.append(LeagueMember(
            user_id=opp["user_id"],
            username=opp["username"],
            roster=opp_ids,
            elo_ratings={pid: ranking_seed.get(pid, 1500) for pid in opp_ids},
        ))

    # Merge DB-stored league members not sent by the "client" (session_init
    # does the same — covers locally-seeded test users in real leagues).
    try:
        existing = {m.user_id for m in members} | {user_id}
        for dbm in db.load_league_members(league_info["league_id"]):
            if dbm["user_id"] in existing:
                continue
            dbm_ids = [str(x) for x in dbm.get("player_ids", [])
                       if str(x) in players_dict_default]
            if not dbm_ids:
                continue
            members.append(LeagueMember(
                user_id=dbm["user_id"],
                username=dbm.get("username") or dbm.get("display_name") or dbm["user_id"],
                roster=dbm_ids,
                elo_ratings={pid: ranking_seed.get(pid, 1500) for pid in dbm_ids},
            ))
    except Exception:
        pass

    league = League(league_id=league_info["league_id"], name=league_info["name"],
                    platform="sleeper", members=members)
    user_roster = [pid for pid in team["player_ids"] if pid in players_dict_default]

    # Ranking services — one per format, built in parallel exactly like
    # session_init. Brand-new user ⇒ no swipe replay, no tier overrides.
    def _build(fmt: str):
        pool, seed = srv._get_universal_pool(fmt)
        svc = RankingService(players=pool, matchup_generator=srv.matchup_gen,
                             seed_ratings=seed)
        svc._user_id = user_id
        svc._scoring_format = fmt
        return fmt, svc

    services = {}
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=len(db.SCORING_FORMATS)) as pool:
        for fut in concurrent.futures.as_completed(
                [pool.submit(_build, f) for f in db.SCORING_FORMATS]):
            fmt, svc = fut.result()
            services[fmt] = svc

    # Trade services — per format, empty past-decision set (brand-new user).
    trade_svcs = {}
    for fmt in db.SCORING_FORMATS:
        fmt_pool, _ = srv._get_universal_pool(fmt)
        tsvc = TradeService(players={p.id: p for p in fmt_pool},
                            past_decision_keys=set())
        tsvc.add_league(league)
        trade_svcs[fmt] = tsvc

    sess = {
        "user_id": user_id,
        "league": league,
        "players": default_pool,
        "user_roster": user_roster,
        "services": services,
        "trade_svcs": trade_svcs,
        "active_format": active_format,
    }
    return sess, (time.perf_counter() - t0) * 1000


def _presentment_audit(cards, *, trade_service, user_roster, seed_map,
                       outlook, fmt) -> dict:
    """G6 (DB-1/DB-2) — per-card presentment predicate replay with the SAME
    context the construction hooks see: {trade_id: {r1,r2,r3,r5}} where True
    = that rule's predicate would KILL the card. Computed on every run
    (flag-on or off) so a flag-OFF corpus carries would-be kill rates and a
    flag-ON corpus proves served-card violation == 0."""
    import backend.trade_service as ts_mod
    players = trade_service._players

    def sv(pid):
        return ts_mod.elo_to_value(seed_map.get(pid, 1500.0))

    prof = ts_mod.analyze_roster_strengths(user_roster, players, fmt)
    upv: dict = {}
    for pid in user_roster:
        p = players.get(pid)
        if p is None or ts_mod.is_pick_asset(p):
            continue
        pos = getattr(p, "position", None)
        if pos in ts_mod._PRESENTMENT_POSITIONS:
            upv.setdefault(pos, []).append((pid, sv(pid)))
    out = {}
    for c in cards:
        g, r = c.give_player_ids, c.receive_player_ids
        out[c.trade_id] = {
            "r1": not ts_mod.overpay_ok(g, r, sv),
            "r2": not ts_mod.pos_net_ok(g, r, players),
            "r3": not ts_mod.pick_gap_ok(g, r, sv, players),
            "r5": not ts_mod.need_gate_ok(
                g, r, seed_value=sv, players=players, user_pos_values=upv,
                outlook=outlook, position_needs=prof["position_needs"],
                position_surplus=prof["position_surplus"],
                scoring_format=fmt),
        }
    return out


def generate_first_deck(sess: dict, with_picks: bool = False) -> tuple[list, float, dict]:
    """Replicate the _run_trade_job worker path for a brand-new user.
    Returns (cards, gen_ms, extras)."""
    t0 = time.perf_counter()
    fmt = sess["active_format"]
    service = sess["services"][fmt]
    trade_service = sess["trade_svcs"][fmt]
    league = sess["league"]
    league_id = league.league_id
    user_id = sess["user_id"]

    user_elo = {rp.player.id: rp.elo
                for rp in service.get_rankings(position=None).rankings}
    seed_map = service._seed or {}

    # Inject real leaguemate ELOs (OTHER members who have saved rankings) —
    # same as the worker. The simulated user is excluded, which is exactly
    # the brand-new-user condition.
    real_user_ids: set = set()
    try:
        real_rankings = db.load_member_rankings(
            league_id=league_id, exclude_user_id=user_id, scoring_format=fmt)
        for member in league.members:
            rd = real_rankings.get(member.user_id)
            if rd and rd["elo_ratings"]:
                member.elo_ratings = dict(rd["elo_ratings"])
                member.username = rd["username"] or member.username
                member.has_rankings = True
                real_user_ids.add(member.user_id)
    except Exception:
        pass

    # Brand-new user: no declared outlook / prefs — the roster-seeded
    # inference (flag trade.outlook_seed) is all they get, same as prod.
    outlook_value, _sig = srv._infer_user_outlook(user_id, league_id, sess, league)

    # Opponent outlooks + pick shares (flag trade.outlook_infer) — worker logic.
    opponent_outlooks: dict[str, str] = {}
    opponent_pick_shares: dict[str, float] = {}
    if FLAGS.trade_outlook_infer:
        try:
            for m in league.members:
                if m.user_id == user_id:
                    continue
                mp = db.load_league_preference(user_id=m.user_id, league_id=league_id)
                if mp and mp.get("team_outlook"):
                    opponent_outlooks[m.user_id] = mp["team_outlook"]
            picks = db.load_draft_picks(league_id=league_id)
            totals: dict[str, float] = {}
            grand = 0.0
            for pk in picks:
                owner = pk.get("owner_user_id")
                pv = pk.get("pick_value") or 0.0
                if owner:
                    totals[owner] = totals.get(owner, 0.0) + pv
                grand += pv
            if grand > 0:
                opponent_pick_shares = {u: t / grand for u, t in totals.items()}
        except Exception:
            pass

    confidence = service.comparison_counts()

    # G6 R-12 / DB-4 — owned-pick injection, mirroring _run_trade_job, so a
    # pick-synced league's replay produces pick-carrying cards. Opt-in
    # (--with-picks): the D-055 baseline corpus was captured without it.
    n_injected_picks = 0
    if with_picks and srv._owned_picks_available(league_id, league):
        try:
            seed_map, new_roster, n_injected_picks = srv._inject_owned_picks(
                league_id      = league_id,
                scoring_format = fmt,
                trade_service  = trade_service,
                players_dict   = {p.id: p for p in sess["players"]},
                seed_map       = seed_map,
                user_elo       = user_elo,
                user_id        = user_id,
                user_roster    = sess["user_roster"],
                league         = league,
            )
            sess["user_roster"] = new_roster
        except Exception as pick_err:
            print(f"  !! pick injection failed (continuing): {pick_err}")

    cards = trade_service.generate_trades(
        user_id=user_id,
        user_elo=user_elo,
        user_roster=sess["user_roster"],
        league_id=league_id,
        seed_elo=seed_map,
        confidence=confidence,
        outlook=outlook_value,
        fairness_threshold=FAIRNESS_THRESHOLD_DEFAULT,
        acquire_positions=[],
        trade_away_positions=[],
        scoring_format=fmt,
        opponent_outlooks=opponent_outlooks or None,
        opponent_pick_shares=opponent_pick_shares or None,
        untouchable_ids=None,      # brand-new user has none
        target_ids=None,
    )

    # Likes-you injection (flag trade.likes_you) — league-level, faithful.
    if srv._likes_you_enabled():
        try:
            cards = srv._inject_likes_you_cards(
                cards=cards, trade_service=trade_service, user_id=user_id,
                league_id=league_id, league=league,
                user_roster=sess["user_roster"], seed_map=seed_map,
                untouchable_ids=None)
        except Exception:
            pass

    # Thompson ordering + deck diversity (A5/A6). The shape-count read for
    # the SIMULATED user is stubbed to {} in main() — a brand-new user has
    # no decision history.
    if srv._thompson_deck_enabled() or srv._deck_diversity_enabled():
        try:
            cards = srv._order_deck(cards, user_id=user_id, league_id=league_id,
                                    job_id=f"deckeval_{user_id}", seed_map=seed_map)
        except Exception:
            pass

    # NOTE: log_trade_impressions deliberately NOT called (eval is read-only).
    gen_ms = (time.perf_counter() - t0) * 1000

    # G6 (DB-1..DB-4) — per-rule kill counters from the job + per-card
    # predicate replay over the served deck.
    try:
        presentment_kills = trade_service.presentment_kill_counts()
    except Exception:
        presentment_kills = {}
    try:
        audit = _presentment_audit(
            cards, trade_service=trade_service,
            user_roster=sess["user_roster"], seed_map=seed_map,
            outlook=outlook_value, fmt=fmt)
    except Exception as audit_err:
        print(f"  !! presentment audit failed: {audit_err}")
        audit = {}

    return cards, gen_ms, {"outlook": outlook_value,
                           "real_ranked_opponents": len(real_user_ids),
                           "presentment_kills": presentment_kills,
                           "presentment_audit": audit,
                           "n_injected_picks": n_injected_picks}


def card_record(card, players_dict: dict, seed_map: dict) -> dict:
    """Compact record of one card, with consensus values for human scoring."""
    d = srv.trade_card_to_dict(card, players_dict)

    def side(ids):
        out = []
        for pid in ids:
            p = players_dict.get(pid)
            out.append({
                "id": pid,
                "name": p.name if p else pid,
                "pos": p.position if p else "?",
                "age": getattr(p, "age", None) if p else None,
                "value": round(elo_to_value(seed_map.get(pid, 1500.0))),
            })
        return out

    give = side(card.give_player_ids)
    recv = side(card.receive_player_ids)
    return {
        "trade_id": card.trade_id,
        "opponent": card.target_username,
        "give": give,
        "receive": recv,
        "give_value": sum(x["value"] for x in give),
        "receive_value": sum(x["value"] for x in recv),
        "fairness": round(card.fairness_score, 3),
        "composite": round(card.composite_score, 3),
        "basis": getattr(card, "basis", None),
        "lane": d.get("lane"),
        "need_fit": d.get("need_fit"),
        "likes_you": d.get("likes_you", False),
        "narrative": d.get("narrative"),
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def pctl(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    vs = sorted(values)
    k = max(0, min(len(vs) - 1, round(p / 100 * (len(vs) - 1))))
    return vs[k]


def fmt_side(side: list[dict]) -> str:
    return " + ".join(f"{a['name']} ({a['pos']}, {a['value']})" for a in side)


def write_report(path: pathlib.Path, run: dict) -> None:
    s = run["summary"]
    lines = []
    a = lines.append
    a("# Offline deck-quality + timing eval — first-run consensus decks")
    a("")
    a(f"*Generated {run['generated_at']} by `scripts/deck_eval.py` "
      f"(onboarding-conversion plan, build item 2 — the GATE).*")
    a("")
    a("Each row below is one league team simulated as a **brand-new user**: "
      "consensus-seeded board only, zero swipes/preferences, production "
      "`config/features.json` flags (incl. `trade.need_fit` fit-led decks, "
      "trade-engine v2/v3). The first 5 cards of each first-run deck are "
      "shown for human scoring.")
    a("")
    a("## Thresholds (from the plan)")
    a("")
    a("| Metric | Target | This run |")
    a("|---|---|---|")
    a(f"| Empty-deck rate | **< 5%** | {s['empty_deck_rate_pct']}% "
      f"({s['empty_decks']}/{s['teams']}) |")
    a("| Insult rate (human-scored 'insulting? y' ÷ scored cards) | **< 3%** "
      "| _score below, then compute_ |")
    a(f"| First-deck gen latency (server-side) | informs <60s TTFT budget | "
      f"mean {s['gen_ms_mean']} ms · p95 {s['gen_ms_p95']} ms |")
    a("")
    a("**Passing** = empty-deck < 5% AND human-scored insult rate < 3% AND "
      "latency compatible with the <60s warm TTFT budget → the trades-first "
      "hook screen (build item 4) may proceed. **Failing** any of these → "
      "engine cold-start / deck-quality work jumps the build queue; the "
      "funnel does not ship showcasing a deck that insults strangers.")
    a("")
    a("## How to score")
    a("")
    a("For each card, fill the two blank columns:")
    a("- **insulting? y/n** — would the OWNER of this team feel lowballed or "
      "mocked by this offer landing as their first impression of the app?")
    a("- **would consider? y/n** — is it plausible enough to swipe on "
      "(not obviously dead on arrival)?")
    a("")
    a("Values shown are consensus (DynastyProcess-seeded) trade values — the "
      "exact numbers a first-run user's cards are built from. Δ = receive − "
      "give from the simulated user's perspective.")
    a("")
    a("## Summary")
    a("")
    a(f"- Leagues evaluated: **{s['leagues']}** — teams (first-run sims): "
      f"**{s['teams']}**")
    a(f"- Empty decks: **{s['empty_decks']}** ({s['empty_deck_rate_pct']}%)")
    a(f"- League-init time (build ranking+trade services, per team): "
      f"mean **{s['init_ms_mean']} ms**, p95 **{s['init_ms_p95']} ms**")
    a(f"- First-deck generation time: mean **{s['gen_ms_mean']} ms**, "
      f"p95 **{s['gen_ms_p95']} ms**")
    a(f"- Sleeper league fetch (client-side leg, per league): "
      f"mean **{s['fetch_ms_mean']} ms**")
    a(f"- One-time warm-process setup (import: DB + consensus + demo pool): "
      f"**{s['import_s']} s**; universal-pool build: **{s['pool_build_ms']} ms** "
      "(paid once per server process — this is the cold-start component the "
      "keep-warm ping, build item 3, exists to hide)")
    a(f"- Deck size: min {s['deck_min']} · median {s['deck_median']} · "
      f"mean {s['deck_mean']} · max {s['deck_max']}")
    dist = s["deck_size_dist"]
    a(f"- Deck-size distribution: 0 cards ×{dist['0']}, 1–4 ×{dist['1-4']}, "
      f"5–9 ×{dist['5-9']}, 10+ ×{dist['10+']}")
    if run.get("auto_red_flags"):
        a("")
        a(f"### Auto-flagged cards (fairness < {REDFLAG_FAIRNESS} or "
          f"consensus Δ ≤ {REDFLAG_DELTA} — check these first)")
        a("")
        for rf in run["auto_red_flags"]:
            a(f"- {rf}")
    a("")
    a("---")
    for lg in run["leagues"]:
        a("")
        a(f"## {lg['name']} (`{lg['league_id']}`) — {len(lg['teams'])} teams, "
          f"format `{lg['scoring_format']}`, fetch {lg['fetch_ms']} ms")
        for tm in lg["teams"]:
            a("")
            a(f"### @{tm['username']} — deck {tm['deck_size']} cards · "
              f"init {tm['init_ms']} ms · gen {tm['gen_ms']} ms · "
              f"outlook `{tm['outlook']}`")
            if not tm["cards"]:
                a("")
                a("**EMPTY DECK** — first-run user sees no trades.")
                continue
            a("")
            a("| # | Trade (give → receive) | Δ | Fair | Lane | Fit | "
              "insulting? y/n | would consider? y/n |")
            a("|---|---|---|---|---|---|---|---|")
            for i, c in enumerate(tm["cards"], 1):
                delta = c["receive_value"] - c["give_value"]
                trade = (f"{fmt_side(c['give'])} → **{fmt_side(c['receive'])}** "
                         f"(w/ {c['opponent']})")
                fit = "—" if c["need_fit"] is None else f"{c['need_fit']:.2f}"
                lane = c["lane"] or "—"
                extra = " · likes-you" if c["likes_you"] else ""
                a(f"| {i} | {trade}{extra} | {delta:+d} | "
                  f"{round(c['fairness'] * 100)}% | {lane} | {fit} |  |  |")
    a("")
    a("---")
    a("")
    a("## Method + fidelity notes")
    a("")
    a("- Built by internal import of `backend.server` (no Flask server): the "
      "same session-construction and trade-job code paths as "
      "`/api/session/init` + `/api/trades/generate`, with the production "
      "flag file.")
    a("- Brand-new-user masking: the simulated user's own swipes, tier "
      "overrides, league preference, asset prefs, past trade decisions and "
      "Thompson shape counts are excluded. League-level state (other "
      "members' saved rankings, league likes, draft picks, impressions) is "
      "used exactly as production would.")
    a("- `log_trade_impressions` is not called — the eval writes nothing "
      "user-visible to the DB.")
    a("- Latency numbers are local-machine; Render dyno numbers will differ "
      "(esp. cold start). The one-time setup line above is the piece the "
      "keep-warm ping hides.")
    a(f"- Flags snapshot: see the JSON artifact (`{run['json_artifact']}`).")
    a("")
    path.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    ap.add_argument("league_ids", nargs="*", help="Sleeper league IDs")
    ap.add_argument("--sample", type=int, default=0,
                    help="pull N distinct real league ids from the local DB")
    ap.add_argument("--sleeper-username",
                    help="resolve a Sleeper user's 2026 leagues")
    ap.add_argument("--max-teams", type=int, default=0,
                    help="cap teams per league (0 = all)")
    ap.add_argument("--with-picks", action="store_true",
                    help="G6 R-12/DB-4: inject owned picks like the trade "
                         "job (pick-synced leagues only)")
    ap.add_argument("--report", default=str(
        PROJECT_ROOT / "docs/plans/onboarding-conversion/deck-eval-report.md"))
    args = ap.parse_args()

    # The eval is only meaningful under the exact production flag config.
    if not (FLAGS.trade_engine_v2 and is_enabled("trade.need_fit")):
        raise SystemExit("config/features.json is not the production config "
                         "(trade_engine.v2 + trade.need_fit must be true).")

    league_ids: list[str] = list(dict.fromkeys(args.league_ids))
    if args.sleeper_username:
        league_ids += [l for l in leagues_from_username(args.sleeper_username)
                       if l not in league_ids]
    if args.sample:
        league_ids += [l for l in leagues_from_db(args.sample)
                       if l not in league_ids]
    league_ids = league_ids[:15]
    if not league_ids:
        raise SystemExit("No leagues given. Pass league ids, --sample N, "
                         "or --sleeper-username.")

    # Warm the universal pools once (a warm server already holds these).
    t0 = time.perf_counter()
    if srv._load_sleeper_cache() is None:
        raise SystemExit("data/.sleeper_players_cache.json missing — start "
                         "the dev server once or fetch /api/sleeper/players.")
    srv._ensure_universal_pools()
    pool_build_ms = (time.perf_counter() - t0) * 1000
    if not srv.g_universal_by_format.get("1qb_ppr", {}).get("players"):
        raise SystemExit("Universal pool build failed (DynastyProcess fetch?)")

    # Brand-new-user mask for the Thompson prior: a first-run user has no
    # trade-decision history. Eval-scoped stub on the server module only —
    # backend code on disk is untouched.
    srv.load_trade_decision_shape_counts = lambda *a, **k: {}

    default_pool, _ = srv._get_universal_pool("1qb_ppr")
    ts = datetime.now(timezone.utc)
    run: dict = {
        "generated_at": ts.strftime("%Y-%m-%d %H:%M UTC"),
        "flags": flags_dict(),
        "fairness_threshold": FAIRNESS_THRESHOLD_DEFAULT,
        "leagues": [],
        "auto_red_flags": [],
    }

    init_times, gen_times, deck_sizes, fetch_times = [], [], [], []

    for lid in league_ids:
        print(f"\n=== League {lid}")
        try:
            info = fetch_league(lid)
        except Exception as e:
            print(f"  !! Sleeper fetch failed: {e}")
            info = None
        if not info or len(info["teams"]) < 2:
            print("  skipped (unreachable or <2 rostered teams)")
            continue
        if len(info["teams"]) < 8:
            print(f"  note: only {len(info['teams'])} rostered teams "
                  "(prefer 8+; evaluating anyway)")
        active_format = db.get_league_scoring(lid)
        fetch_times.append(info["fetch_ms"])
        lg_out = {"league_id": lid, "name": info["name"],
                  "scoring_format": active_format,
                  "fetch_ms": info["fetch_ms"], "teams": []}

        teams = info["teams"][:args.max_teams] if args.max_teams else info["teams"]
        fmt_pool, fmt_seed = srv._get_universal_pool(active_format)
        fmt_players_dict = {p.id: p for p in fmt_pool}

        for team in teams:
            sess, init_ms = build_first_run_session(info, team, active_format)
            cards, gen_ms, extras = generate_first_deck(
                sess, with_picks=args.with_picks)
            _tsvc_players = sess["trade_svcs"][active_format]._players
            first5 = [card_record(c, {**fmt_players_dict, **_tsvc_players},
                                  fmt_seed)
                      for c in cards[:5]]
            for rec, c in zip(first5, cards[:5]):
                rec["presentment_audit"] = (
                    extras["presentment_audit"].get(c.trade_id))
            init_times.append(init_ms)
            gen_times.append(gen_ms)
            deck_sizes.append(len(cards))
            for c in first5:
                delta = c["receive_value"] - c["give_value"]
                if c["fairness"] < REDFLAG_FAIRNESS or delta <= REDFLAG_DELTA:
                    run["auto_red_flags"].append(
                        f"{info['name']} / @{team['username']}: "
                        f"{fmt_side(c['give'])} → {fmt_side(c['receive'])} "
                        f"(fairness {round(c['fairness'] * 100)}%, "
                        f"consensus Δ {delta:+d})")
            lg_out["teams"].append({
                "user_id": team["user_id"],
                "username": team["username"],
                "roster_size": len(team["player_ids"]),
                "init_ms": round(init_ms, 1),
                "gen_ms": round(gen_ms, 1),
                "deck_size": len(cards),
                "outlook": extras["outlook"],
                "real_ranked_opponents": extras["real_ranked_opponents"],
                "presentment_kills": extras["presentment_kills"],
                "n_injected_picks": extras["n_injected_picks"],
                "cards": first5,
            })
            print(f"  @{team['username']:<22} deck={len(cards):>3}  "
                  f"init={init_ms:6.0f}ms  gen={gen_ms:7.0f}ms  "
                  f"outlook={extras['outlook']}")
        run["leagues"].append(lg_out)

    teams_n = len(deck_sizes)
    if teams_n == 0:
        raise SystemExit("No teams evaluated — nothing reachable.")
    empty = sum(1 for d in deck_sizes if d == 0)
    run["summary"] = {
        "leagues": len(run["leagues"]),
        "teams": teams_n,
        "empty_decks": empty,
        "empty_deck_rate_pct": round(100 * empty / teams_n, 1),
        "init_ms_mean": round(statistics.mean(init_times), 1),
        "init_ms_p95": round(pctl(init_times, 95), 1),
        "gen_ms_mean": round(statistics.mean(gen_times), 1),
        "gen_ms_p95": round(pctl(gen_times, 95), 1),
        "fetch_ms_mean": round(statistics.mean(fetch_times), 1) if fetch_times else 0,
        "import_s": round(IMPORT_S, 1),
        "pool_build_ms": round(pool_build_ms, 1),
        "deck_min": min(deck_sizes),
        "deck_median": statistics.median(deck_sizes),
        "deck_mean": round(statistics.mean(deck_sizes), 1),
        "deck_max": max(deck_sizes),
        "deck_size_dist": {
            "0": empty,
            "1-4": sum(1 for d in deck_sizes if 1 <= d <= 4),
            "5-9": sum(1 for d in deck_sizes if 5 <= d <= 9),
            "10+": sum(1 for d in deck_sizes if d >= 10),
        },
    }

    out_dir = PROJECT_ROOT / "feedback-workspace" / "deck-eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"deck_eval_{ts.strftime('%Y%m%dT%H%M%SZ')}.json"
    run["json_artifact"] = str(json_path.relative_to(PROJECT_ROOT))
    json_path.write_text(json.dumps(run, indent=1))

    report_path = pathlib.Path(args.report)
    write_report(report_path, run)

    s = run["summary"]
    print(f"\n== Done: {s['leagues']} leagues, {s['teams']} teams")
    print(f"   empty-deck rate {s['empty_deck_rate_pct']}% (target <5%)")
    print(f"   init  mean {s['init_ms_mean']}ms  p95 {s['init_ms_p95']}ms")
    print(f"   gen   mean {s['gen_ms_mean']}ms  p95 {s['gen_ms_p95']}ms")
    print(f"   JSON:   {json_path}")
    print(f"   Report: {report_path}")


if __name__ == "__main__":
    main()
