"""Real-trade recall and fairness-band calibration for the value core.

Implements docs/plans/value-core-engine/lld.md section 8.3. Cases come ONLY from
committed fixtures under ``backend/tests/fixtures`` (no network, no DB):

* ``outlook-hypotheses/{label}-{season}.json`` - completed trades by week;
* ``outlook-calibration/{label}-{season}.json`` - league meta and weekly matchups
  (the pre-trade rosters are week ``leg - 1``);
* ``dp-values-history/`` - dated DynastyProcess boards, read offline.

Documented limitations: the fixtures carry no ages (youth weights fall to their
unknown value) and only the traded picks exist as assets.

The engine modules (``pipeline``, ``core``, ``adapter``) are imported lazily
inside ``run_recall``; case construction needs none of them.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from backend.value_core.types import (
    CORE_POSITIONS, Asset, CoreConfig, FairTrade, LeagueSnapshot, RankConfig, Request,
    RosterRules, Team,
)

HYPOTHESES_DIR = "outlook-hypotheses"
CALIBRATION_DIR = "outlook-calibration"
VALUES_DIR = "dp-values-history"
POSITION_FILES = (f"{CALIBRATION_DIR}/players_team_pos.json",
                  f"{HYPOTHESES_DIR}/player-positions.json")
SKIP_REASONS = ("offseason_leg", "multi_team", "roster_mismatch", "no_values", "unpriced_asset")
_LEAGUE_FILE = re.compile(r"^([a-z0-9]+)-(\d{4})\.json$")
_ORDINALS = {1: "1st", 2: "2nd", 3: "3rd"}


@dataclass(frozen=True)
class RecallCase:
    case_id: str                   # f"{label}-{season}-w{leg}-{transaction_id}"
    label: str                     # "ffv3" | "lakeview"
    season: int
    leg: int
    scoring_format: str
    lineup_slots: tuple[str, ...]
    assets: Mapping[str, Asset]
    teams: Mapping[str, tuple[str, ...]]   # roster_id(str) -> pre-trade asset ids (week leg-1)
    a_team: str
    b_team: str
    a_gives: tuple[str, ...]
    b_gives: tuple[str, ...]


def _scoring_format(meta: Mapping) -> str:
    """Mirrors the app's Sleeper-meta format detection: superflex or TE premium -> sf_tep."""
    positions = meta.get("roster_positions") or []
    superflex = "SUPER_FLEX" in positions or sum(1 for p in positions if p == "QB") >= 2
    try:
        tep = float((meta.get("scoring_settings") or {}).get("bonus_rec_te") or 0) > 0
    except (TypeError, ValueError):
        tep = False
    return "sf_tep" if (superflex or tep) else "1qb_ppr"


def _board_key(keys: Sequence[str], status_updated) -> str | None:
    """Latest board key dated on or before the trade's status_updated (epoch ms, UTC)."""
    if not status_updated:
        return None
    day = datetime.fromtimestamp(int(status_updated) / 1000, tz=timezone.utc).date().isoformat()
    eligible = [k for k in keys if k <= day]
    return eligible[-1] if eligible else None


def _load(path: Path):
    with open(path) as f:
        return json.load(f)


def cases_from_fixtures(fixture_root: Path, *, only: Iterable[tuple[str, int]] | None = None
                        ) -> tuple[list[RecallCase], dict[str, int]]:
    """Every in-season two-team trade reconstructable from the fixtures, plus skip counts.

    `only` restricts to (label, season) pairs, e.g. {("ffv3", 2024)}; None means every
    pair present in both the hypotheses and the calibration fixture dirs."""
    from backend import dp_values_history
    from backend.data_loader import seed_elo_for_value
    from backend.pick_values import pick_pool_value
    from backend.trade_service import elo_to_value

    root = Path(fixture_root)
    hyp_dir, cal_dir, values_dir = root / HYPOTHESES_DIR, root / CALIBRATION_DIR, root / VALUES_DIR
    pairs = []
    for path in sorted(hyp_dir.glob("*.json")):
        match = _LEAGUE_FILE.match(path.name)
        if match and (cal_dir / path.name).exists():
            pairs.append((match.group(1), int(match.group(2))))
    if only is not None:
        wanted = {(str(label), int(season)) for label, season in only}
        pairs = [p for p in pairs if p in wanted]

    positions: dict[str, dict] = {}
    for rel in POSITION_FILES:
        positions.update(_load(root / rel))
    index_path = values_dir / "index.json"
    keys = sorted(dp_values_history.load_index(str(index_path)).get("snapshots") or {})
    crosswalk = dp_values_history.default_crosswalk() if pairs else None
    boards: dict[tuple[str, str], dict[str, float]] = {}

    skipped = {reason: 0 for reason in SKIP_REASONS}
    cases: list[RecallCase] = []
    for label, season in pairs:
        hyp = _load(hyp_dir / f"{label}-{season}.json")
        cal = _load(cal_dir / f"{label}-{season}.json")
        meta = cal.get("league") or {}
        slots = tuple(meta.get("roster_positions") or ())
        fmt = _scoring_format(meta)
        scoring = "2qb" if fmt == "sf_tep" else "1qb"
        weeks = cal.get("matchups") or {}
        trades = sorted((t for week in (hyp.get("transactions_trades") or {}).values() for t in week),
                        key=lambda t: (int(t.get("leg") or 0), int(t.get("status_updated") or 0),
                                       str(t.get("transaction_id"))))
        for trade in trades:
            leg = int(trade.get("leg") or 0)
            if leg < 2:
                skipped["offseason_leg"] += 1
                continue
            roster_ids = [str(r) for r in trade.get("roster_ids") or []]
            if len(roster_ids) != 2 or len(set(roster_ids)) != 2:
                skipped["multi_team"] += 1
                continue
            a_team, b_team = roster_ids
            rosters = {str(m["roster_id"]): [str(p) for p in (m.get("players") or [])]
                       for m in weeks.get(str(leg - 1)) or []}
            drops = {str(p): str(r) for p, r in (trade.get("drops") or {}).items()}
            picks = trade.get("draft_picks") or []
            if (a_team not in rosters or b_team not in rosters
                    or any(r not in (a_team, b_team) or p not in rosters[r]
                           for p, r in drops.items())
                    or any(str(dp.get("previous_owner_id")) not in (a_team, b_team)
                           for dp in picks)):
                skipped["roster_mismatch"] += 1
                continue
            key = _board_key(keys, trade.get("status_updated"))
            if key is None:
                skipped["no_values"] += 1
                continue
            if (key, scoring) not in boards:
                boards[(key, scoring)] = dp_values_history.values_as_of(
                    key, scoring=scoring, crosswalk=crosswalk,
                    snapshot_dir=str(values_dir), index_path=str(index_path))[0]
            values = boards[(key, scoring)]

            assets: dict[str, Asset] = {}
            teams: dict[str, list[str]] = {}
            for rid in sorted(rosters):
                ids = []
                for pid in rosters[rid]:
                    info = positions.get(pid) or {}
                    if info.get("position") not in CORE_POSITIONS or pid in assets:
                        continue
                    market = elo_to_value(seed_elo_for_value(values[pid])) if pid in values else 0.0
                    assets[pid] = Asset(pid, "player", info["position"],
                                        info.get("full_name") or pid, None, market)
                    ids.append(pid)
                teams[rid] = ids
            gives: dict[str, list[str]] = {a_team: [], b_team: []}
            priced = True
            for pid, rid in drops.items():
                priced = priced and pid in assets and pid in values
                gives[rid].append(pid)
            for dp in picks:
                sender, rnd = str(dp["previous_owner_id"]), int(dp["round"])
                aid = f"hist_{dp['season']}_{rnd}_{dp['roster_id']}"
                assets[aid] = Asset(aid, "pick", "PICK",
                                    f"{dp['season']} {_ORDINALS.get(rnd, f'{rnd}th')}", None,
                                    pick_pool_value(rnd, int(dp["season"]) - season, fmt))
                teams[sender].append(aid)
                gives[sender].append(aid)
            if not priced or not gives[a_team] or not gives[b_team]:
                skipped["unpriced_asset"] += 1   # includes a side that gave only FAAB
                continue

            def ordered(ids):
                return tuple(sorted(ids, key=lambda a: (-assets[a].market, a)))
            cases.append(RecallCase(
                case_id=f"{label}-{season}-w{leg}-{trade.get('transaction_id')}",
                label=label, season=season, leg=leg, scoring_format=fmt, lineup_slots=slots,
                assets=assets, teams={rid: tuple(ids) for rid, ids in teams.items()},
                a_team=a_team, b_team=b_team,
                a_gives=ordered(gives[a_team]), b_gives=ordered(gives[b_team])))
    return cases, skipped


def is_close(trade: FairTrade, real_give: Sequence[str], real_receive: Sequence[str],
             assets: Mapping[str, Asset]) -> bool:
    """The card carries the real trade's headliner (its max-market asset, ties: id asc) on
    the same viewer side, and at least 50% of the real trade's asset ids."""
    real = list(real_give) + list(real_receive)
    if not real:
        return False
    headliner = min(real, key=lambda a: (-assets[a].market, a))
    same_side = headliner in (trade.give if headliner in real_give else trade.receive)
    shared = len(set(trade.give) & set(real_give)) + len(set(trade.receive) & set(real_receive))
    return same_side and shared >= 0.5 * len(real)


def _nearest_rank(values: Sequence[float], q: float) -> float:
    return values[max(0, math.ceil(q * len(values) - 1e-9) - 1)]


def band_calibration(log_ratios: Sequence[float]) -> dict:
    """{n, p50, p80, p90, recommended_band}: nearest-rank percentiles v[ceil(q*n) - 1] on the
    sorted values; the recommended band round(exp(p80) - 1, 2) admits 80% of them."""
    values = sorted(log_ratios)
    if not values:
        return {"n": 0, "p50": None, "p80": None, "p90": None, "recommended_band": None}
    p80 = _nearest_rank(values, 0.80)
    return {"n": len(values), "p50": _nearest_rank(values, 0.50), "p80": p80,
            "p90": _nearest_rank(values, 0.90), "recommended_band": round(math.exp(p80) - 1, 2)}


def _share(hits: int, total: int) -> float | None:
    return round(hits / total, 4) if total else None


def run_recall(cases: Sequence[RecallCase], core_cfg: CoreConfig, rank_cfg: RankConfig, *,
               top: int = 10) -> dict:
    """Both orientations of every case through pipeline.run (neutral windows, no board,
    partner scoped to the other side), plus core.evaluate_trade on the real trade."""
    from backend.value_core import adapter, core, pipeline

    tiers: dict[str, tuple[float, float]] = {}
    per_case: list[dict] = []
    reject_reasons: Counter = Counter()
    band_values: list[float] = []
    for case in cases:
        if case.scoring_format not in tiers:
            tiers[case.scoring_format] = adapter.tier_values(case.scoring_format)
        first_round_value, elite_value = tiers[case.scoring_format]
        snapshot = LeagueSnapshot(
            case.case_id, case.scoring_format, case.assets,
            {rid: Team(rid, f"Roster {rid}", tuple(ids)) for rid, ids in case.teams.items()},
            RosterRules(tuple(case.lineup_slots), None), first_round_value, elite_value)
        for orientation, viewer, partner, give, receive in (
                ("A", case.a_team, case.b_team, case.a_gives, case.b_gives),
                ("B", case.b_team, case.a_team, case.b_gives, case.a_gives)):
            request = Request(viewer_team_id=viewer, partner_team_id=partner)
            result = pipeline.run(snapshot, request, core_cfg, rank_cfg)
            rank_exact = rank_close = None
            for rank, entry in enumerate(result.entries, 1):
                trade = entry.scored.trade
                if rank_exact is None and set(trade.give) == set(give) \
                        and set(trade.receive) == set(receive):
                    rank_exact = rank
                if rank_close is None and is_close(trade, give, receive, case.assets):
                    rank_close = rank
                if rank_exact is not None and rank_close is not None:
                    break
            verdict = core.evaluate_trade(snapshot, request, core_cfg, partner_team_id=partner,
                                          give=give, receive=receive)
            log_ratio = (math.log(verdict.trade.adjusted_ratio)
                         if verdict.trade is not None and verdict.trade.adjusted_ratio > 0 else None)
            if not verdict.ok:
                reject_reasons[verdict.reason] += 1
            if orientation == "A" and log_ratio is not None:
                band_values.append(abs(log_ratio))
            per_case.append({"case_id": case.case_id, "orientation": orientation,
                             "rank_exact": rank_exact, "rank_close": rank_close,
                             "ok": verdict.ok, "reason": verdict.reason,
                             "log_ratio": None if log_ratio is None else round(log_ratio, 4)})
    n = len(per_case)
    return {"cases": len(cases), "orientations": n,
            "exact_at_k": _share(sum(1 for r in per_case
                                     if r["rank_exact"] is not None and r["rank_exact"] <= top), n),
            "close_at_k": _share(sum(1 for r in per_case
                                     if r["rank_close"] is not None and r["rank_close"] <= top), n),
            "in_pool_rate": _share(sum(1 for r in per_case if r["rank_exact"] is not None), n),
            "reject_reasons": dict(sorted(reject_reasons.items())),
            "band": band_calibration(band_values),
            "per_case": per_case}


def main(argv: Sequence[str] | None = None) -> int:
    from backend.eval.value_core_bench import fresh_dir, parse_variants, write_private_json

    parser = argparse.ArgumentParser(prog="python -m backend.eval.value_core_recall",
                                     description=__doc__.splitlines()[0])
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--variant", action="append", default=[])
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise SystemExit(f"{args.output} already exists; recall never overwrites")

    cases, skipped = cases_from_fixtures(args.fixtures)
    results = {}
    for name, overrides in parse_variants(args.variant).items():
        core_cfg = dataclasses.replace(CoreConfig(), **(overrides.get("core") or {}))
        rank_cfg = dataclasses.replace(RankConfig(), **(overrides.get("rank") or {}))
        results[name] = run_recall(cases, core_cfg, rank_cfg, top=args.top)
    fresh_dir(args.output)
    write_private_json(args.output / "results.json",
                       {"top": args.top, "skipped": skipped, "variants": results})

    print(f"cases: {len(cases)}  skipped: {json.dumps(skipped, sort_keys=True)}")
    print(f"| variant | orientations | exact@{args.top} | close@{args.top} | in pool "
          "| band n | band p80 | recommended band |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|")
    for name, r in results.items():
        band = r["band"]
        print(f"| {name} | {r['orientations']} | {r['exact_at_k']} | {r['close_at_k']} "
              f"| {r['in_pool_rate']} | {band['n']} | {band['p80']} | {band['recommended_band']} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
