"""Offline common-input replay of the three most recently introduced constructors.

Run as a fresh process. Uses an isolated scratch DB, blocks network, never calls
the server or writes production. Retained current source is not an original
historical binary. Replays have no behavioral acceptance labels.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time

from .scorecard_runner import fingerprint, run_manifest, write_report

ARMS = ("owner_v2_bilateral", "owner_v1", "fit")
INTRODUCED = {"owner_v2_bilateral": "4913ad0c", "owner_v1": "0e3d6b70", "fit": "c6e6c3c0"}
PERSONAL_SOURCES = {"explicit", "votes", "legacy", "cross_format"}
NORMALIZATION_VERSION = "owner-request-eval-normalization-1"


def _pick(pid, position):
    if position != "PICK":
        return None
    generic = re.fullmatch(r"generic_pick_([1-4])_(early|mid|late)", pid)
    if generic:
        return {"pick_round": int(generic[1])}
    owned = re.search(r"_(20\d\d)_([1-4])_(.+)$", pid)
    if owned:
        return {"pick_year": int(owned[1]), "pick_round": int(owned[2]),
                "original_roster_id": owned[3]}
    return {}


def normalize_offer(card, raw, *, model_id, market_values, tier_for, tiers, configuration_sha256=None):
    """Frozen input normalization only; never consume a constructor's utility.

    Shared tier identity is permitted. No heuristic inference of projections,
    counterpart conviction, pick slots or age-specific owner intent is added.
    """
    k = raw["input"]
    viewer = k["user_id"]
    partner = card.target_user_id
    members = {m["id"]: m for m in k["members"]}
    rosters = {m["id"]: m["roster"] for m in k["members"]}
    rosters[viewer] = k["user_roster"]
    # Historical request identity alone cannot bind annotations after a value
    # reconstruction/config change. Keep source identity separate from the
    # immutable normalized evidence identity used by the independent grader.
    sid = fingerprint({"source_request_hash": raw.get("request_hash"),
                       "frozen_input": k, "market_values": market_values,
                       "configuration_sha256": configuration_sha256,
                       "normalization_version": NORMALIZATION_VERSION})
    provenance = {"source": "frozen_owner_request_capture", "as_of": raw.get("captured_at"),
                  "version": str(raw.get("version", "unknown")), "snapshot_id": sid,
                  "timestamp_semantics": "capture_not_market_publication",
                  "source_market_as_of": raw.get("market_as_of", "unavailable")}
    provenance["source_request_hash"] = raw.get("request_hash")
    provenance["configuration_sha256"] = configuration_sha256
    provenance["normalization_version"] = NORMALIZATION_VERSION
    universe = fingerprint(sorted(k["seed_elo"]))

    def board_entries(board, sources=None):
        coordinates = {}
        groups = {}
        # Complete the coordinate universe with captured consensus, but preserve
        # explicitness separately. A sparse singleton must not acquire rank 0
        # merely because its peers are absent from the personal board.
        comparison_board = dict(k["seed_elo"])
        comparison_board.update({pid: rating for pid, rating in board.items() if pid in comparison_board})
        for pid, rating in comparison_board.items():
            player = k["players"].get(pid, {})
            pos = player.get("position")
            if pos not in ("QB", "RB", "WR", "TE"):
                continue
            tier_name = tier_for(rating, pos, k["scoring_format"])
            tier = tiers.index(tier_name) if tier_name in tiers else len(tiers)
            groups.setdefault((pos, tier), []).append((pid, rating))
        for (_, tier), values in groups.items():
            # Tied values have tied rank; no asset-id-based preference invented.
            ratings = sorted({rating for _, rating in values}, reverse=True)
            for pid, rating in values:
                coordinates[pid] = {"tier": tier, "order": ratings.index(rating),
                                    "explicit": pid in board and sources is not None and sources.get(pid) in PERSONAL_SOURCES}
        return coordinates

    assets = {}
    for uid in (viewer, partner):
        for pid in rosters[uid]:
            p = k["players"].get(pid, {})
            pos = p.get("position")
            pick = _pick(pid, pos)
            assets[pid] = {"kind": "pick" if pick is not None else "player", "owner_id": uid,
                           "position": pos, "age": p.get("age"), "market_value": market_values.get(pid)}
            if pick:
                assets[pid].update(pick)
                mapped_owner = (k.get("roster_owner_map") or {}).get(pick.get("original_roster_id"))
                if mapped_owner is not None:
                    assets[pid]["original_owner_id"] = mapped_owner
    managers = {}
    for role, uid, give in (("A", viewer, card.give_player_ids), ("B", partner, card.receive_player_ids)):
        prefs = (k.get("manager_preferences") or {}).get(uid, {})
        selected = (k.get("outlook") if uid == viewer else (k.get("opponent_outlooks") or {}).get(uid)) or prefs.get("team_outlook")
        # An absent selected outlook must not silently become an invented declaration.
        manager = {"manager_id": uid, "give": list(give), "roster": rosters[uid],
                   "selected_outlook": selected,
                   "inferred_outlook": (k.get("inferred_outlooks") or {}).get(uid),
                   "explicit_selection": {"give": k.get("pinned_give_players") or []} if role == "A" else {},
                   "source_lineup_status": prefs.get("lineup_source", "unknown")}
        if type(prefs.get("next_draft_year")) is int:
            manager["next_draft_year"] = prefs["next_draft_year"]
        board = k["user_elo"] if role == "A" else members[uid].get("elo", {})
        sources = k.get("user_sources", {}) if role == "A" else (k.get("opponent_sources") or {}).get(uid, {})
        if board and sources:
            # Consensus fills stay non-explicit; all deliberate source types retain equal authority.
            manager["personal_board"] = {"manager_id": uid, "universe_id": universe,
                "second_round_tier": tiers.index("second"), "provenance": provenance,
                "entries": board_entries(board, sources)}
        managers[role] = manager
    concept = fingerprint({"give": sorted(card.give_player_ids), "receive": sorted(card.receive_player_ids),
                           "partner": partner, "viewer": viewer})
    return {"schema_version": 1, "data_kind": "frozen_replay", "offer_id": concept,
            "snapshot_id": sid, "captured_at": raw.get("captured_at"),
            "context": "ordinary_discovery", "assets": assets, "managers": managers,
            "evidence": {"market": {"units": "captured_atomic_consensus_value", "universe_id": universe,
                "provenance": provenance, "second_round_tier": tiers.index("second"),
                "entries": board_entries(k["seed_elo"]) }},
            "source_model_id": model_id}


def _descriptive(cards, k, players, tiers, tier_for, market_values=None):
    seed, board, sources = k["seed_elo"], k["user_elo"], k.get("user_sources", {})
    def qualified(pid):
        p = players.get(pid)
        if p is None:
            return False
        pick = _pick(pid, p.position)
        if pick is not None:
            return pick.get("pick_round") == 1
        if p.position not in ("QB", "RB", "WR", "TE"):
            return False
        values = [seed.get(pid)]
        if sources.get(pid) in PERSONAL_SOURCES:
            values.append(board.get(pid))
        return any((tier := tier_for(v, p.position, k["scoring_format"])) in tiers[:5]
                   for v in values if v is not None)
    counts = Counter()
    head_counts = Counter()
    raw_balance = []
    for c in cards:
        give, receive = c.give_player_ids, c.receive_player_ids
        counts["has_meaningful_centerpiece"] += any(qualified(p) for p in give + receive)
        counts["small_1x1_1x2_2x1"] += (len(give), len(receive)) in ((1, 1), (1, 2), (2, 1))
        counts["incoming_first"] += any((_pick(p, players[p].position) or {}).get("pick_round") == 1 for p in receive)
        counts["incoming_pick"] += any(players[p].position == "PICK" for p in receive)
        counts["incoming_rb"] += any(players[p].position == "RB" for p in receive)
        counts["outgoing_rb"] += any(players[p].position == "RB" for p in give)
        head = max(give, key=lambda p: seed.get(p, 0))
        head_counts[head] += 1
        if market_values and all(p in market_values for p in give + receive):
            sent = sum(market_values[p] for p in give)
            received = sum(market_values[p] for p in receive)
            if sent > 0:
                raw_balance.append((received - sent) / sent)
    return {"offers": len(cards), "counts": dict(counts),
            "rates": {key: value / len(cards) if cards else None for key, value in counts.items()},
            "distinct_sent_headliners": len(head_counts),
            "max_sent_headliner_repeats": max(head_counts.values(), default=0),
            "unadjusted_market_return": {
                "definition": "(incoming additive reference - outgoing additive reference) / outgoing additive reference",
                "known_offers": len(raw_balance),
                "mean_fraction": sum(raw_balance) / len(raw_balance) if raw_balance else None,
                "min_fraction": min(raw_balance) if raw_balance else None,
                "max_fraction": max(raw_balance) if raw_balance else None,
                "limitation": "Not stud-adjusted; neither fairness nor acceptance probability"},
            "shape": dict(sorted(Counter(f"{len(c.give_player_ids)}x{len(c.receive_player_ids)}" for c in cards).items()))}


def replay(snapshot, capture, output, *, source_commit):
    """Fresh-process replay; output directory must not already exist."""
    if "backend.database" in sys.modules or "backend.trade_service" in sys.modules:
        raise RuntimeError("Replay requires a fresh process before runtime imports")
    repo = Path(__file__).resolve().parents[2]
    actual_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo,
                                  check=True, capture_output=True, text=True).stdout.strip()
    if source_commit != actual_commit:
        raise ValueError("source-commit must equal this checkout's full HEAD")
    output = Path(output)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.environ["DATABASE_URL"] = "sqlite:///" + str((output / "isolated.sqlite3").resolve())
    def no_network(*args, **kwargs):
        raise RuntimeError("Offline model evaluation forbids network")
    socket.socket.connect = no_network
    socket.create_connection = no_network
    from backend import database as db, trade_service as ts, trade_gen_owner, trade_gen_bilateral, trade_gen_fit
    from backend import feature_flags as ff
    from backend.ranking_service import Player, RankingService, ORDERED_TIERS
    db.metadata.create_all(db.engine)
    cfg = {row["key"]: row["value"] for row in capture["config"]}
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    ts._cfg.update(cfg)
    ff._flags_cache = capture["flags"]["flags"]
    raw = snapshot["owner_request"]
    frozen = copy.deepcopy(raw["input"])
    k = copy.deepcopy(frozen)
    players = {pid: Player(id=pid, name=pid, **attrs) for pid, attrs in k.pop("players").items()}
    sources = k.get("opponent_sources") or {}
    members = [ts.LeagueMember(m["id"], m["id"], m["roster"], m["elo"],
                               bool(m["elo"]) and any(v in PERSONAL_SOURCES for v in sources.get(m["id"], {}).values()),
                               confidence_sources=sources.get(m["id"], {})) for m in k.pop("members")]
    k.update(players=players, league=ts.League("frozen-replay", "Private replay", "espn", members), config=cfg)
    for field in ("past_decision_keys", "exclusion_keys"):
        k[field] = {(frozenset(a), frozenset(b)) for a, b in k.get(field, [])}
    cval = ts.make_consensus_value_fn(k["seed_elo"], players)
    market = {pid: cval(pid) for pid in players if pid in k["seed_elo"]}
    manifest = {"schema_version": 1, "benchmark_id": "three-recent-models-frozen-v1",
                "evidence_class": "frozen_single_request_replay", "requests": [], "offers": [], "contexts": {}}
    source_files = ("backend/trade_gen_bilateral.py", "backend/trade_gen_owner.py",
                    "backend/trade_gen_fit.py", "backend/trade_service.py", "backend/tier_config.json",
                    "backend/eval/scorecard_dimensions.py", "backend/eval/scorecard_runner.py", "backend/eval/scorecard_replay.py")
    metrics = {"source_commit": source_commit,
               "source_file_sha256": {f: hashlib.sha256((repo / f).read_bytes()).hexdigest() for f in source_files},
               "snapshot_sha256": fingerprint(snapshot),
               "configuration_sha256": fingerprint(capture), "captured_at": raw.get("captured_at"),
               "configuration_checked_at": capture.get("checked_at"), "independent_contexts": 1,
               "market_source_as_of": raw.get("market_as_of", "unavailable"), "models": {},
               "limitations": ["One frozen request; not a representative population or acceptance test",
                   "Counterparty boards/projections remain missing where absent",
                   "First-round eligibility in significance projection is syntactic/captured-universe only; no complete pick-ledger validity proof",
                   "Retained current implementations; original historical binaries not replayed",
                   "Only independently defined significance projection after native output, not complete serving pipeline",
                   "Native search budgets differ; no claim of equal compute or exhaustive recall"]}
    generators = {"owner_v2_bilateral": trade_gen_bilateral.generate_bilateral_trades,
                  "owner_v1": trade_gen_owner.generate_owner_trades, "fit": trade_gen_fit.generate_league_suggestions}
    for arm in ARMS:
        start = time.perf_counter()
        kwargs = dict(k)
        if arm == "fit":
            params = inspect.signature(generators[arm]).parameters
            kwargs = {key: value for key, value in k.items() if key in params}
            kwargs["max_per_opponent"] = None
        cards, report = generators[arm](**kwargs)
        elapsed = time.perf_counter() - start
        version = (trade_gen_fit.SCORER_VERSION if arm == "fit" else
                   trade_gen_bilateral.VERSION if arm == "owner_v2_bilateral" else trade_gen_owner.VERSION)
        manifest["requests"].append({"model_id": arm, "request_id": "frozen-request-1", "status": "ok" if cards else "empty"})
        baseline = _descriptive(cards, frozen, players, ORDERED_TIERS, RankingService.tier_for_elo, market)
        # Independent projection of the documented individual significance rule;
        # never use model utility or the live gate's eligibility as a quality label.
        retained = []
        for rank, card in enumerate(cards, 1):
            context_id = fingerprint(card.target_user_id)
            if context_id not in manifest["contexts"]:
                context = normalize_offer(card, raw, model_id=arm, market_values=market,
                    tier_for=RankingService.tier_for_elo, tiers=ORDERED_TIERS,
                    configuration_sha256=fingerprint(capture))
                context.pop("source_model_id", None)
                manifest["contexts"][context_id] = context
            terms = {"A": list(card.give_player_ids), "B": list(card.receive_player_ids)}
            row = {"model_id": arm, "model_version": version, "request_id": "frozen-request-1",
                   "stage": "native_output", "native_rank": rank, "context_id": context_id,
                   "offer_id": fingerprint({"context": context_id, "terms": {s: sorted(v) for s, v in terms.items()}}),
                   "terms": terms}
            manifest["offers"].append(row)
            if rank <= 30:
                manifest["offers"].append(dict(row, stage="native_first30"))
            single = _descriptive([card], frozen, players, ORDERED_TIERS, RankingService.tier_for_elo)
            if single["counts"].get("has_meaningful_centerpiece"):
                retained.append(card)
                manifest["offers"].append(dict(row, stage="shared_significance_projection"))
                if len(retained) <= 30:
                    manifest["offers"].append(dict(row, stage="post_significance_first30"))
        diagnostics = report.diagnostics() if hasattr(report, "diagnostics") else report.as_dict()
        safe_keys = {"evaluated", "eligible", "emitted", "enumerated", "scored", "opponents", "boarded_opponents",
                     "capped_pairs", "rejections", "killed", "post_filtered", "truncated", "budget_exhausted"}
        safe_diagnostics = {key: value for key, value in diagnostics.items() if key in safe_keys}
        metrics["models"][arm] = {"version": version, "introduced_commit": INTRODUCED[arm],
            "generation_seconds": elapsed, "native": baseline,
            "native_first30": _descriptive(cards[:30], frozen, players, ORDERED_TIERS, RankingService.tier_for_elo, market),
            "post_significance": _descriptive(retained, frozen, players, ORDERED_TIERS, RankingService.tier_for_elo, market),
            "post_significance_first30": _descriptive(retained[:30], frozen, players, ORDERED_TIERS, RankingService.tier_for_elo, market),
            "search_diagnostics": safe_diagnostics}
        print(json.dumps({"arm": arm, "cards": len(cards), "seconds": round(elapsed, 3)}), flush=True)
    result = run_manifest(manifest)
    write_report(result, output / "evaluation")
    for name, value in (("manifest.private.json", manifest), ("comparison.json", metrics)):
        path = output / name
        with path.open("x") as stream:
            json.dump(value, stream, sort_keys=True, allow_nan=False)
        path.chmod(0o600)
    return metrics


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args(argv)
    replay(json.loads(args.snapshot.read_text()), json.loads(args.config.read_text()),
           args.output, source_commit=args.source_commit)


if __name__ == "__main__":
    main()
