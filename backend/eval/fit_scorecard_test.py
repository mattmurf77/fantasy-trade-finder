"""Offline test of the two fit approaches against Calibration grades (plan: "Fit Scorecard
Test Plan", 2026-10-09; docs/plans/fit-scorecard/plan.md).

For every answered Calibration card: rebuild its league from prod (read-only; the bench's
own freeze path, so lineup slots and standings come from Sleeper), score the trade with
Approach A and Approach B (backend.fit_engine), and ask three questions:

  Q1  Does the viewer's gain separate would-send (4-5) from no (1-2)?      AUC >= 0.70, and
      >= 0.10 over the best baseline (consensus ratio, best-piece ratio, value-core
      value and outlook scores).
  Q2  Does the partner's gain predict the "they_wont_accept" tag?          AUC >= 0.65.
  Q3  Do the tags agree with the parts? ("overpay" -> viewer gain < 0; "wrong_for_my_window"
      -> a received piece the viewer's window discounts.)                   Reported only.

Round 1 = sessions created before ROUND2_SINCE (value-core-1 decks); round 2 = after.
Writes results.json and cards.csv (no user ids beyond the grader's own key) to --output.

    python -m backend.eval.fit_scorecard_test --secrets secrets.local.env --output <dir>
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

from sqlalchemy import text

from backend import fit_engine as fe
from backend.eval import value_core_bench as bench
from backend.value_core import core, ranking
from backend.value_core.types import CoreConfig, RankConfig, Request

ROUND2_SINCE = "2026-10-09T15:45:45"
WOULD_SEND, WOULD_NOT = 4, 2


def auc(pos: list[float], neg: list[float]) -> float | None:
    """Mann-Whitney AUC: P(score of a positive > score of a negative), ties count half."""
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return round(wins / (len(pos) * len(neg)), 4)


def _league(conn, league_id: str, today: date) -> dict:
    """The bench's frozen-league record; ESPN reads its user-assigned picks too (the grading
    path's rule, blind_grading._league_inputs)."""
    inputs = bench.read_league_inputs(conn, league_id, today)
    if (inputs["league_row"].get("platform") or "sleeper") == "sleeper":
        return bench._freeze_league(conn, league_id, today, bench._fetch_json)
    inputs["picks"] = [dict(r) for r in conn.execute(text(
        "SELECT pick_id, season, round, owner_user_id, pick_value, pool_value, is_traded, "
        "original_username FROM draft_picks WHERE league_id = :l ORDER BY pick_id"),
        {"l": league_id}).mappings()]
    return bench.league_record(**inputs, meta=None, state=None)


def _partner(snapshot, viewer: str, partner_name: str, receive: list[str]) -> str | None:
    by_name = [t for t, team in snapshot.teams.items() if team.name == partner_name and t != viewer]
    if len(by_name) == 1:
        return by_name[0]
    owners = {t for t, team in snapshot.teams.items() if receive and receive[0] in team.asset_ids}
    return next(iter(owners - {viewer}), None)


def run(secrets: Path, output: Path) -> dict:
    from backend.tools import prod_analytics

    prod_analytics.SECRETS = Path(secrets)
    eng = prod_analytics._connect_readonly(prod_analytics._load_prod_url(), 30000)
    today = date.today()
    ros_cache: dict[str, dict] = {}
    rows: list[dict] = []
    try:
        with eng.connect() as conn:
            bench.assert_read_only(conn)
            cards = conn.execute(text(
                "SELECT k.card_id, k.user_id, k.grade, k.skipped, k.tags_json, k.trade_json, "
                "k.arms_json, g.league_id, g.created_at FROM grading_cards k "
                "JOIN grading_sessions g ON g.session_id = k.session_id "
                "WHERE k.grade IS NOT NULL ORDER BY g.league_id, k.card_id")).mappings().all()
            leagues: dict[tuple, tuple] = {}
            for c in cards:
                key = (c["league_id"], c["user_id"])
                if key not in leagues:
                    record = _league(conn, c["league_id"], today)
                    snapshot, board = bench.snapshot_for_seat(
                        record, c["user_id"], standings_weight=bench.DEFAULT_STANDINGS_WEIGHT)
                    fmt = snapshot.scoring_format
                    if fmt not in ros_cache:
                        ros_cache[fmt] = fe.fetch_ros_points(bench._fetch_json, fmt)
                    league = fe.build_league(snapshot)
                    grades = fe.build_grades(league, ros_cache[fmt]["points"], fmt)
                    request = Request(viewer_team_id=c["user_id"], board=board)
                    leagues[key] = (snapshot, league, request,
                                    fe.Scorer("fit_a", league, request),
                                    fe.Scorer("fit_b", league, request, grades), grades)
                snapshot, league, request, sa, sb, grades = leagues[key]
                rows.append(_score_card(c, snapshot, league, request, sa, sb, grades))
    finally:
        eng.dispose()
    results = _summarize([r for r in rows if r is not None])
    results["ros"] = {fmt: {k: v for k, v in r.items() if k != "points"} | {"players": len(r["points"])}
                      for fmt, r in ros_cache.items()}
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(json.dumps(results, indent=2, sort_keys=True))
    kept = [r for r in rows if r is not None]
    if kept:
        with open(output / "cards.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(kept[0]))
            w.writeheader()
            w.writerows(kept)
    return results


def _score_card(c, snapshot, league, request, sa, sb, grades) -> dict | None:
    trade = json.loads(c["trade_json"])
    give = [a["id"] for a in trade["give"]]
    receive = [a["id"] for a in trade["receive"]]
    if any(a not in snapshot.assets for a in give + receive):
        return None                      # an asset left the league since grading
    viewer = request.viewer_team_id
    partner = _partner(snapshot, viewer, trade.get("partner_name"), receive)
    if partner is None:
        return None
    mk = snapshot.assets
    a_v, a_p = sa.gains(partner, give, receive)
    b_v, b_p = sb.gains(partner, give, receive)
    vc_value = vc_outlook = None
    try:
        verdict = core.evaluate_trade(snapshot, request, CoreConfig(), partner_team_id=partner,
                                      give=give, receive=receive)
        if verdict.trade is not None:
            s = ranking.score_trades(snapshot, request, [verdict.trade], RankConfig())[0].scores
            vc_value, vc_outlook = s.value, s.outlook
    except ValueError:
        pass                             # ownership moved since grading: no value-core baseline
    window = league.window(viewer)
    a_window_discount = any(
        mk[r].kind == "pick" and fe.A_WINDOW[window]["pick"] < 1
        or mk[r].kind == "player" and mk[r].age is not None and (
            (mk[r].age >= fe.OLD_AGE and fe.A_WINDOW[window]["old"] < 1)
            or (not league.would_start(viewer, r) and fe.A_WINDOW[window]["depth"] < 1))
        for r in receive)
    b_clash = any((window == "rebuilder" and grades.profile.get(r) == "win_now")
                  or (window == "contender" and grades.profile.get(r) == "future") for r in receive)
    tags = json.loads(c["tags_json"] or "[]")
    arms = sorted(json.loads(c["arms_json"]))
    g_total, r_total = sum(mk[a].market for a in give), sum(mk[a].market for a in receive)
    return {
        "round": 2 if str(c["created_at"]) >= ROUND2_SINCE else 1,
        "grader": c["user_id"], "league_id": c["league_id"], "arms": "+".join(arms),
        "grade": int(c["grade"]), "tags": "|".join(tags),
        "they_wont_accept": int("they_wont_accept" in tags), "overpay": int("overpay" in tags),
        "wrong_for_my_window": int("wrong_for_my_window" in tags), "window": window,
        "a_you": round(a_v, 4), "a_partner": round(a_p, 4),
        "b_you": round(b_v, 4), "b_partner": round(b_p, 4),
        "consensus_ratio": round(r_total / g_total, 4) if g_total else None,
        "best_piece_ratio": round(max(mk[a].market for a in receive)
                                  / max(mk[a].market for a in give), 4),
        "vc_value": vc_value, "vc_outlook": vc_outlook,
        "a_window_discount": int(a_window_discount), "b_profile_clash": int(b_clash),
    }


def _q1(rows: list[dict], col: str) -> float | None:
    vals = [r for r in rows if r[col] is not None]
    return auc([r[col] for r in vals if r["grade"] >= WOULD_SEND],
               [r[col] for r in vals if r["grade"] <= WOULD_NOT])


def _q2(rows: list[dict], col: str) -> float | None:
    """Higher partner gain should mean LESS 'they won't accept': AUC of the negated score."""
    return auc([-r[col] for r in rows if r["they_wont_accept"]],
               [-r[col] for r in rows if not r["they_wont_accept"]])


def _summarize(rows: list[dict]) -> dict:
    out: dict = {"cards": len(rows), "by_round": {}}
    for rnd in sorted({r["round"] for r in rows} | {"all"}, key=str):
        rs = rows if rnd == "all" else [r for r in rows if r["round"] == rnd]
        baselines = {b: _q1(rs, b) for b in ("consensus_ratio", "best_piece_ratio", "vc_value", "vc_outlook")}
        best_base = max((v for v in baselines.values() if v is not None), default=None)
        approaches = {}
        for name, you, partner, discount in (("A", "a_you", "a_partner", "a_window_discount"),
                                             ("B", "b_you", "b_partner", "b_profile_clash")):
            q1, q2 = _q1(rs, you), _q2(rs, partner)
            over = [r for r in rs if r["overpay"]]
            win = [r for r in rs if r["wrong_for_my_window"]]
            approaches[name] = {
                "q1_auc_you": q1, "q2_auc_partner": q2,
                "q1_pass": bool(q1 is not None and q1 >= 0.70
                                and (best_base is None or q1 >= best_base + 0.10)),
                "q2_pass": bool(q2 is not None and q2 >= 0.65),
                "q3_overpay_with_negative_gain": (round(sum(r[you] < 0 for r in over) / len(over), 3)
                                                  if over else None),
                "q3_window_tag_with_discount": (round(sum(r[discount] for r in win) / len(win), 3)
                                                if win else None)}
        by_grader = defaultdict(list)
        for r in rs:
            by_grader[r["grader"]].append(r)
        out["by_round"][str(rnd)] = {
            "cards": len(rs), "would_send": sum(r["grade"] >= WOULD_SEND for r in rs),
            "would_not": sum(r["grade"] <= WOULD_NOT for r in rs),
            "they_wont_accept": sum(r["they_wont_accept"] for r in rs),
            "baselines_q1": baselines, "best_baseline_q1": best_base, "approaches": approaches,
            "graders": {g: {"cards": len(v), "A_q1": _q1(v, "a_you"), "B_q1": _q1(v, "b_you")}
                        for g, v in sorted(by_grader.items())}}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--secrets", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args(argv)
    res = run(args.secrets, args.output)
    print(json.dumps({k: v for k, v in res.items() if k != "ros"} | {"ros": res.get("ros")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
