"""Independent, offline incumbent/revision/presentation comparison.

Run the coordinator in the candidate checkout. Every request/model invokes a
fresh interpreter and a private scratch SQLite database. No production imports,
credentials, actions, observed acceptance labels or model-derived quality grades.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import hashlib
import importlib
import itertools
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import sys
import time


VERSION = "bilateral-revision-eval-2"
FIXTURES = Path(__file__).resolve().parents[1] / "tests/fixtures/model-evaluation/revision"
BASELINE_PREFIX = "ecda17d1"
CUTS = (1, 5, 10, 30)


def worker_environment():
    """Stable hash iteration and isolated DB/import selection for every replay."""
    env = {key: value for key, value in os.environ.items()
           if key not in {"DATABASE_URL", "PYTHONPATH"}}
    env.update(PYTHONHASHSEED="0", PYTHONDONTWRITEBYTECODE="1")
    return env


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def private_json(path, value):
    """Generated evidence is private by default, including subprocess errors."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(value, stream, sort_keys=True, allow_nan=False)


def request_records(envelope):
    records = envelope.get("requests")
    if records is None:
        records = [{"owner_request": envelope["owner_request"]}]
    result, seen, repeated = [], set(), 0
    for record in records:
        raw = record.get("owner_request")
        if not isinstance(raw, dict) or not isinstance(raw.get("input"), dict):
            result.append(dict(record, invalid_capture=True))
            continue
        # The content binds equality; an incorrect/reused source hash cannot
        # silently delete a distinct input or create pseudo-replication.
        key = digest(raw["input"])
        if key in seen:
            repeated += 1
        else:
            seen.add(key)
            result.append(record)
    return result, repeated


def context_inventory(records):
    """Identity-free coverage; owner/league clusters are not independent cards."""
    counts, outlooks, formats, clusters = Counter(), Counter(), Counter(), set()
    for record in records:
        raw = record.get("owner_request", {})
        k = raw.get("input")
        if not isinstance(k, dict):
            counts["invalid_captures"] += 1
            continue
        counts["captured_input_contexts"] += 1
        counts["synthetic_contexts"] += raw.get("data_kind") == "synthetic"
        counts["counterfactual_contexts"] += bool(raw.get("counterfactual_of"))
        outlooks[str(k.get("outlook"))] += 1
        formats[str(k.get("scoring_format"))] += 1
        if record.get("league_id") and record.get("user_id"):
            clusters.add((record["league_id"], record["user_id"]))
        for member in k.get("members", []):
            counts["counterparty_occurrences"] += 1
            sources = (k.get("opponent_sources") or {}).get(member["id"], {})
            counts["counterparties_with_personal_source"] += any(
                value in {"explicit", "votes", "legacy", "cross_format"} for value in sources.values())
    return {"counts": dict(counts), "selected_outlooks": dict(outlooks),
            "formats": dict(formats), "known_owner_league_clusters": len(clusters),
            "independent_observed_contexts": None,
            "cluster_limitation": "Captured input contexts may share managers/leagues; synthetic and counterfactual copies are not observations"}


def frozen_split(records):
    """Connected manager/league components, assigned before model outputs.

    A manager appearing as initiator or counterpart joins all their captured
    leagues. Sorting component hashes, every third component is held out. One
    connected component cannot supply an independent development/holdout split.
    """
    parent = {}
    def root(key):
        parent.setdefault(key, key)
        if parent[key] != key:
            parent[key] = root(parent[key])
        return parent[key]
    def join(a, b):
        parent[root(b)] = root(a)
    nodes = {}
    for index, record in enumerate(records):
        raw = record.get("owner_request", {})
        if raw.get("data_kind") == "synthetic":
            continue
        k = raw.get("input", {})
        league = record.get("league_id")
        if not league:
            continue
        node = ("league", str(league))
        root(node)
        nodes[index] = node
        participants = [k.get("user_id"), *[m.get("id") for m in k.get("members", [])]]
        for manager in participants:
            if manager:
                join(node, ("manager", str(manager)))
    groups = {}
    for index, node in nodes.items():
        groups.setdefault(root(node), []).append(index)
    ordered = sorted(groups.values(), key=lambda indices: digest(sorted(
        {str(records[index]["league_id"]) for index in indices})))
    assigned = {}
    for position, indices in enumerate(ordered):
        cohort = "holdout" if len(ordered) > 1 and position % 3 == 0 else "development"
        assigned.update({index: cohort for index in indices})
    for index, record in enumerate(records):
        assigned.setdefault(index, "constructed" if record.get("owner_request", {}).get("data_kind") == "synthetic" else "unassigned")
    return {"assignments": assigned, "connected_components": len(ordered),
            "cohort_counts": dict(Counter(assigned.values())),
            "status": "frozen" if len(ordered) > 1 else "evidence-limited",
            "rule": "Shared initiator/counterparty identities connect leagues; every third component ordered by hash held out"}


def diagnostic_panel(records, split):
    """Input-only panel: smallest full-input hash per outlook/format + holdout."""
    strata, selected = {}, set()
    for index, record in enumerate(records):
        raw = record.get("owner_request", {})
        if raw.get("data_kind") == "synthetic" or split["assignments"][index] == "holdout":
            selected.add(index)
        k = raw.get("input")
        if not isinstance(k, dict) or raw.get("data_kind") == "synthetic":
            continue
        key = (k.get("outlook"), k.get("scoring_format"))
        contender = (digest(k), index)
        if key not in strata or contender < strata[key]:
            strata[key] = contender
    selected.update(index for _, index in strata.values())
    return sorted(selected)


def constructed_requests():
    """Expand frozen, explicitly constructed request archetypes, never live data."""
    spec = json.loads((FIXTURES / "archetypes.json").read_text())
    base = spec["base"]
    results = []
    for outlook_a, outlook_b, boards in itertools.product(spec["outlooks"], spec["outlooks"], spec["board_states"]):
        k = copy.deepcopy(base)
        k.update(outlook=outlook_a, opponent_outlooks={"B": outlook_b})
        if boards == "none":
            k["user_elo"] = {}
            k["user_sources"] = {}
        if boards != "full":
            k["members"][0]["elo"] = {}
            k["opponent_sources"] = {}
        if boards == "sparse":
            k["user_elo"] = {"b_wr": k["user_elo"]["b_wr"]}
            k["user_sources"] = {"b_wr": "explicit"}
        name = f"{outlook_a}-{outlook_b}-{boards}"
        results.append({"owner_request": {"version": VERSION, "data_kind": "synthetic",
            "captured_at": spec["captured_at"], "request_hash": name, "input": k}})
    # Each sensitivity pair shares one synthetic context and has a named
    # intervention. No sampling/acceptance denominator is enlarged by copies.
    for change in spec["interventions"]:
        k = copy.deepcopy(base)
        k.update(copy.deepcopy(change.get("replace", {})))
        for pid, elo in change.get("personal_elo", {}).items():
            k["user_elo"][pid] = elo
        results.append({"owner_request": {"version": VERSION, "data_kind": "synthetic",
            "counterfactual_of": "constructed-base", "intervention": change["id"],
            "captured_at": spec["captured_at"], "request_hash": change["id"], "input": k}})
    return results


def card_identity(card):
    return (card.target_user_id, tuple(sorted(card.give_player_ids)), tuple(sorted(card.receive_player_ids)))


def assert_survivor_permutation(before, after):
    # Object identity also protects immutable proof and duplicate multiplicity.
    if Counter(map(id, before)) != Counter(map(id, after)):
        raise AssertionError("survivor_inventory_changed")


def raw_diagnostics(cards, k, market, *, focused_target=None):
    """Independent price/shape/portfolio facts, without reading model scores."""
    from backend.eval.scorecard_replay import _pick
    counts, shapes, heads, partners = Counter(), Counter(), Counter(), Counter()
    returns, seller_returns, prices, focused_prices, first_prices = [], [], {}, {}, {}
    first_target_rank = None
    members = {m["id"]: set(m["roster"]) for m in k["members"]}
    own = set(k["user_roster"])
    seen = set()
    for rank, card in enumerate(cards, 1):
        give, receive = card.give_player_ids, card.receive_player_ids
        identity = card_identity(card)
        counts["exact_duplicate_occurrences"] += identity in seen
        seen.add(identity)
        counts["invalid_ownership_or_duplicate_asset"] += bool(
            len(give) != len(set(give)) or len(receive) != len(set(receive)) or
            set(give) & set(receive) or not set(give) <= own or
            not set(receive) <= members.get(card.target_user_id, set()))
        counts["lost_selected_asset"] += not (set(k.get("pinned_give_players") or ()) <= set(give)
            and set(k.get("pinned_receive_players") or ()) <= set(receive))
        for uid, ids in ((k.get("user_id"), give), (card.target_user_id, receive)):
            pref = ((k.get("manager_preferences") or {}).get(uid) or {})
            next_year = pref.get("next_draft_year")
            selected = set(k.get("pinned_give_players") or ()) if uid == k.get("user_id") else set()
            outlook = k.get("outlook") if uid == k.get("user_id") else (k.get("opponent_outlooks") or {}).get(uid)
            if outlook in ("jets", "tanking"):
                counts["known_unselected_own_next_pick_occurrences"] += len(
                    (set(ids) & set(pref.get("own_next_draft_pick_ids") or ())) - selected)
            for pid in ids:
                pick = _pick(pid, k["players"][pid]["position"])
                if pick is not None:
                    inferred_expired = type(next_year) is int and type(pick.get("pick_year")) is int and pick["pick_year"] < next_year
                    counts["known_expired_pick_occurrences"] += bool(pid in (pref.get("expired_pick_ids") or ()) or inferred_expired)
        shapes[f"{len(give)}x{len(receive)}"] += 1
        counts["small_1x1_1x2_2x1"] += (len(give), len(receive)) in {(1, 1), (1, 2), (2, 1)}
        for side, ids in (("give", give), ("receive", receive)):
            for pos in ("RB", "PICK"):
                counts[f"{side}_contains_{pos.lower()}"] += any(k["players"][p]["position"] == pos for p in ids)
        partners[card.target_user_id] += 1
        if focused_target in receive:
            counts["focused_target_offers"] += 1
            if first_target_rank is None:
                first_target_rank = rank
        if give:
            head = max(give, key=lambda p: (market.get(p, 0), p))
            heads[head] += 1
        if give and receive and all(p in market for p in give + receive):
            sent, received = sum(market[p] for p in give), sum(market[p] for p in receive)
            if sent > 0:
                returns.append((received - sent) / sent)
                target = (card.target_user_id, tuple(sorted(receive)))
                prices[target] = min(prices.get(target, math.inf), sent)
                if focused_target in receive:
                    focused_prices[target] = min(focused_prices.get(target, math.inf), sent)
                    first_prices.setdefault(target, sent)
            best_give, best_receive = max(market[p] for p in give), max(market[p] for p in receive)
            if best_give != best_receive:
                seller_total, buyer_total = (sent, received) if best_give > best_receive else (received, sent)
                if seller_total > 0:
                    seller_returns.append((buyer_total - seller_total) / seller_total)
    def distribution(values):
        return {"known": len(values), "mean": sum(values) / len(values) if values else None,
                "min": min(values) if values else None, "max": max(values) if values else None}
    return {"offers": len(cards), "counts": dict(counts), "shape": dict(shapes),
            "distinct_give_headliners": len(heads), "max_give_headliner_repeats": max(heads.values(), default=0),
            "distinct_partners": len(partners), "raw_market_return": distribution(returns),
            "best_asset_seller_raw_return": distribution(seller_returns),
            "price_limitation": "Raw additive references; not fairness, stud-adjusted price or willingness",
            "first_focused_target_rank": first_target_rank,
            "private_first_exact_target_prices": {digest(key): value for key, value in first_prices.items()},
            "private_focused_target_prices": {digest(key): value for key, value in focused_prices.items()},
            "private_cheapest_exact_target_prices": {digest(key): value for key, value in prices.items()}}


def preference_price_probe(lower, higher):
    """Known price regressions fail; absent comparable targets stay unknown."""
    lows, highs = lower.get("private_focused_target_prices", {}), higher.get("private_focused_target_prices", {})
    common = set(lows) & set(highs)
    increases = sum(highs[key] > lows[key] + 1e-9 for key in common)
    first_low, first_high = lower.get("private_first_exact_target_prices", {}), higher.get("private_first_exact_target_prices", {})
    first_common = set(first_low) & set(first_high)
    first_increases = sum(first_high[key] > first_low[key] + 1e-9 for key in first_common)
    return {"status": "fail" if increases or first_increases else "pass" if common and first_common else "evidence-limited",
            "cheapest_price_status": "fail" if increases else "pass" if common else "evidence-limited",
            "matched_exact_returns": len(common), "price_increased": increases,
            "first_offer_status": "fail" if first_increases else "pass" if first_common else "evidence-limited",
            "matched_first_exact_returns": len(first_common), "first_offer_price_increased": first_increases,
            "targets_lost": len(set(lows) - set(highs)), "targets_added": len(set(highs) - set(lows)),
            "scope": "Constructed input sensitivity, not observed acceptance or general quality"}


def captured_metadata_overlay(context, raw):
    """Same independent captured-fact transform for incumbent and candidate.

    Own-next-pick metadata establishes original owner when identity is coherent;
    it does not establish a full valid/unexpired ledger. Missing facts stay absent.
    Expired markers are preserved even when incomplete original-owner identity
    prevents the core grader from asserting a full pick-validation judgment.
    """
    result = copy.deepcopy(context)
    result["evidence_transform"] = "captured-manager-pick-metadata-1"
    for manager in result["managers"].values():
        uid = manager["manager_id"]
        pref = (raw["input"].get("manager_preferences") or {}).get(uid) or {}
        own, expired = pref.get("own_next_draft_pick_ids"), pref.get("expired_pick_ids")
        if not isinstance(own, list) and not isinstance(expired, list):
            continue
        own = own if isinstance(own, list) and all(isinstance(x, str) for x in own) else None
        expired = expired if isinstance(expired, list) and all(isinstance(x, str) for x in expired) else None
        provenance = {"source": "frozen_request_manager_preferences", "version": str(raw.get("version", "unknown")),
            "as_of": raw.get("captured_at"), "snapshot_id": result["snapshot_id"],
            "source_request_hash": raw.get("request_hash")}
        manager["captured_pick_metadata"] = {"own_next_draft_pick_ids": own if isinstance(own, list) else None,
            "expired_pick_ids": expired if isinstance(expired, list) else None, "provenance": provenance}
        for pid in set(own or ()) | set(expired or ()):
            asset = result["assets"].get(pid)
            if not asset or asset.get("kind") != "pick" or asset.get("owner_id") != uid:
                continue
            if pid in (own or ()) and type(pref.get("next_draft_year")) is int and asset.get("pick_year") == pref["next_draft_year"]:
                if asset.get("original_owner_id") in (None, uid):
                    asset["original_owner_id"] = uid
                    asset["original_owner_provenance"] = provenance
            if pid in (expired or ()):
                asset["pick_validation"] = {"status": "invalid", "reason": "captured_expired_pick_marker", "provenance": provenance}
    return result


def validate_reused_incumbent(result, *, raw, capture, source, runner_sha):
    """All evidence/source bindings are required; no cache exception by filename."""
    expected = {"variant": "incumbent", "version": "owner-v2-bilateral-1", "benchmark_version": VERSION,
        "input_sha256": digest(raw), "config_sha256": digest(capture),
        "source": source, "benchmark_source_sha256": runner_sha}
    if any(result.get(key) != value for key, value in expected.items()):
        raise ValueError("Reused incumbent evidence/source/version mismatch")
    if result.get("status") not in {"ok", "empty"}:
        raise ValueError("Reused incumbent did not complete successfully")


def source_manifest(repo, variant):
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                          capture_output=True, text=True).stdout.strip()
    if variant == "incumbent" and not head.startswith(BASELINE_PREFIX):
        raise ValueError("Incumbent must be immutable ecda17d1 checkout")
    if variant == "incumbent" and subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "--", "backend", "config"], cwd=repo).returncode:
        raise ValueError("Incumbent backend/config differs from immutable commit")
    paths = ["backend/trade_gen_bilateral.py", "backend/trade_gen_owner.py", "backend/trade_service.py",
             "backend/trade_roster.py", "backend/tier_config.json", "backend/eval/scorecard_dimensions.py",
             "backend/eval/scorecard_replay.py", "backend/eval/scorecard_runner.py"]
    if variant == "candidate":
        paths += ["backend/trade_gen_bilateral_candidate.py", "backend/trade_bilateral_presentment.py"]
    hashes = {}
    for name in paths:
        data = (repo / name).read_bytes()
        if variant == "incumbent":
            original = subprocess.run(["git", "show", f"{head}:{name}"], cwd=repo, check=True,
                                      capture_output=True).stdout
            if original != data:
                raise ValueError("Incumbent source differs from immutable commit")
        hashes[name] = hashlib.sha256(data).hexdigest()
    return {"head": head, "file_sha256": hashes}


def worker(repo, request_path, config_path, output, variant):
    """Worker runs only after the coordinator started a fresh interpreter."""
    repo, output = Path(repo).resolve(), Path(output).resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    runner_source_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    sources = source_manifest(repo, variant)
    sys.path.insert(0, str(repo))
    if "backend.trade_service" in sys.modules or "backend.database" in sys.modules:
        raise RuntimeError("Fresh process required")
    os.environ["DATABASE_URL"] = "sqlite:///" + str(output / "isolated.sqlite3")
    def no_network(*args, **kwargs):
        raise RuntimeError("Offline model evaluation forbids network")
    socket.socket.connect = no_network
    socket.socket.connect_ex = no_network
    socket.create_connection = no_network
    socket.socket.sendto = no_network
    from backend import database as db, trade_service as ts, feature_flags as ff
    from backend.ranking_service import Player, RankingService, ORDERED_TIERS
    from backend.eval.scorecard_replay import normalize_offer, _descriptive, PERSONAL_SOURCES
    from backend.eval.scorecard_runner import run_manifest
    db.metadata.create_all(db.engine)
    record = json.loads(Path(request_path).read_text())
    raw = record["owner_request"]
    capture = json.loads(Path(config_path).read_text())
    cfg = {row["key"]: row["value"] for row in capture["config"]}
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    ts._cfg.update(cfg)
    ff._flags_cache = capture["flags"]["flags"]
    k = copy.deepcopy(raw["input"])
    players = {pid: Player(id=pid, name=pid, **attrs) for pid, attrs in k.pop("players").items()}
    members = []
    for member in k.pop("members"):
        sources_map = (k.get("opponent_sources") or {}).get(member["id"], {})
        members.append(ts.LeagueMember(member["id"], member["id"], member["roster"], member["elo"],
            bool(member["elo"]) and any(s in PERSONAL_SOURCES for s in sources_map.values()), confidence_sources=sources_map))
    k.update(players=players, league=ts.League("frozen-revision", "Private offline replay", "espn", members), config=cfg)
    for key in ("past_decision_keys", "exclusion_keys"):
        k[key] = {(frozenset(a), frozenset(b)) for a, b in k.get(key, [])}
    for key in ("roster_owner_map",):
        k.pop(key, None)  # evaluator-only evidence; not a constructor argument
    module = importlib.import_module("backend.trade_gen_bilateral" + ("_candidate" if variant == "candidate" else ""))
    version = module.VERSION
    expected = "owner-v2-bilateral-2" if variant == "candidate" else "owner-v2-bilateral-1"
    if version != expected:
        raise ValueError("Unexpected constructor version")
    before = digest(raw)
    start = time.perf_counter()
    cards, report = module.generate_bilateral_trades(**k)
    generation_seconds = time.perf_counter() - start
    cval = ts.make_consensus_value_fn(k["seed_elo"], players)
    market = {pid: cval(pid) for pid in players if pid in k["seed_elo"]}
    frozen = raw["input"]
    explicit = any(frozen.get(key) for key in ("pinned_give_players", "pinned_receive_players", "opponent_user_id"))
    retained = [c for c in cards if explicit or _descriptive([c], frozen, players, ORDERED_TIERS,
                RankingService.tier_for_elo)["counts"].get("has_meaningful_centerpiece")]
    policy = {"status": "incumbent_no_candidate_policy"}
    ordered = list(retained)
    if variant == "candidate":
        presentment = importlib.import_module("backend.trade_bilateral_presentment")
        ordered, policy = presentment.present(retained,
            selected_give=frozen.get("pinned_give_players") or (),
            selected_receive=frozen.get("pinned_receive_players") or (),
            opponent_user_id=frozen.get("opponent_user_id"))
        assert_survivor_permutation(retained, ordered)
        if explicit and list(map(id, retained)) != list(map(id, ordered)):
            raise AssertionError("Explicit search order changed")
    manifest = {"schema_version": 1, "benchmark_id": VERSION, "evidence_class": raw.get("data_kind", "frozen_replay"),
        "requests": [{"model_id": variant, "request_id": "request", "status": "ok" if cards else "empty"}],
        "offers": [], "contexts": {}}
    stages = {"native": cards, "post_significance": retained, "post_survivor_order": ordered}
    metrics = {}
    for stage, stage_cards in stages.items():
        views = {"full": stage_cards, **{f"first{cut}": stage_cards[:cut] for cut in CUTS}}
        for view, view_cards in views.items():
            name = f"{stage}.{view}"
            metrics[name] = raw_diagnostics(view_cards, frozen, market,
                focused_target="b_wr" if raw.get("intervention", "").startswith("target_preference_") else None)
            for rank, card in enumerate(view_cards, 1):
                cid = digest(card.target_user_id)
                if cid not in manifest["contexts"]:
                    context = normalize_offer(card, raw, model_id=variant, market_values=market,
                        tier_for=RankingService.tier_for_elo, tiers=ORDERED_TIERS,
                        configuration_sha256=digest(capture))
                    if raw.get("data_kind") == "synthetic":
                        context["data_kind"] = "synthetic"
                    if explicit:
                        context["context"] = "selected_search"
                    manifest["contexts"][cid] = captured_metadata_overlay(context, raw)
                manifest["offers"].append({"model_id": variant, "model_version": version, "request_id": "request",
                    "stage": name, "native_rank": rank, "context_id": cid, "offer_id": digest(card_identity(card)),
                    "terms": {"A": card.give_player_ids, "B": card.receive_player_ids}})
    independent = run_manifest(manifest)
    if digest(raw) != before:
        raise AssertionError("Frozen request mutated")
    diagnostics = report.diagnostics() if hasattr(report, "diagnostics") else report.as_dict()
    safe_keys = {"evaluated", "eligible", "emitted", "enumerated", "scored", "opponents", "boarded_opponents",
                 "capped_pairs", "rejections", "killed", "post_filtered", "truncated", "budget_exhausted"}
    result = {"variant": variant, "version": version, "benchmark_version": VERSION,
        "status": "ok" if cards else "empty", "source": sources,
        "benchmark_source_sha256": runner_source_hash,
        "input_sha256": digest(raw), "config_sha256": digest(capture), "generation_seconds": generation_seconds,
        "request_captured_at": raw.get("captured_at"), "common_configuration_checked_at": capture.get("checked_at"),
        "historical_input_config_sha256": digest(raw["input"].get("config")),
        "replay_context": "Common-config cross-sectional constructor diagnostic; fixed ESPN league wrapper, no platform-adapter claim",
        "stages": metrics, "policy": policy, "scorecard": independent,
        "search_diagnostics": {key: value for key, value in diagnostics.items() if key in safe_keys}}
    if source_manifest(repo, variant) != sources or hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != runner_source_hash:
        raise RuntimeError("Source changed during worker; discard mixed-version result")
    private_json(output / "manifest.private.json", manifest)
    private_json(output / "result.private.json", result)
    return result


def compare_pair(incumbent, candidate):
    if incumbent.get("status") == "error" or candidate.get("status") == "error":
        return {"status": "error", "reason": "request_retained_without_comparable_output"}
    changes = {}
    for stage in candidate["stages"]:
        a, b = incumbent["stages"][stage], candidate["stages"][stage]
        delta = {key: b[key] - a[key] for key in ("offers", "distinct_give_headliners", "max_give_headliner_repeats", "distinct_partners")}
        for key in ("raw_market_return", "best_asset_seller_raw_return"):
            av, bv = a[key]["mean"], b[key]["mean"]
            delta[key + "_mean_delta"] = bv - av if av is not None and bv is not None else None
        changes[stage] = delta
    return {"status": "descriptive", "changes": changes,
            "generation_seconds_delta": candidate["generation_seconds"] - incumbent["generation_seconds"]}


def validate_retained_manifest(manifest, result):
    """Reject incomplete/stale stage bridges before rebuilding private proofs."""
    if result.get("status") not in {"ok", "empty"}:
        raise ValueError("Retained candidate did not complete")
    expected_stages = {f"{stage}.{view}" for stage in ("native", "post_significance", "post_survivor_order")
        for view in ("full", *(f"first{cut}" for cut in CUTS))}
    if set(result["stages"]) != expected_stages:
        raise ValueError("Incomplete retained stage metrics")
    grouped = {stage: [] for stage in expected_stages}
    for row in manifest["offers"]:
        if row["stage"] not in grouped or row["model_id"] != "candidate" or row["model_version"] != "owner-v2-bilateral-2":
            raise ValueError("Incompatible retained stage row")
        context = manifest["contexts"][row["context_id"]]
        identity = (context["managers"]["B"]["manager_id"], tuple(sorted(row["terms"]["A"])), tuple(sorted(row["terms"]["B"])))
        if row["offer_id"] != digest(identity):
            raise ValueError("Retained terms/identity mismatch")
        grouped[row["stage"]].append(row)
    for stage, rows in grouped.items():
        if len(rows) != result["stages"][stage]["offers"] or [row["native_rank"] for row in rows] != list(range(1, len(rows) + 1)):
            raise ValueError("Incomplete retained stage rows")
    identities = lambda rows: [row["offer_id"] for row in rows]
    native = identities(grouped["native.full"])
    if len(set(native)) != len(native):
        raise ValueError("Retained duplicate identity cannot use unique-term bridge")
    significance = identities(grouped["post_significance.full"])
    ordered = identities(grouped["post_survivor_order.full"])
    if (not set(significance) <= set(native) or len(set(significance)) != len(significance)
            or Counter(significance) != Counter(ordered)):
        raise ValueError("Retained stage inventory mismatch")
    for stage in ("native", "post_significance", "post_survivor_order"):
        full = identities(grouped[stage + ".full"])
        for cut in CUTS:
            if identities(grouped[f"{stage}.first{cut}"]) != full[:cut]:
                raise ValueError("Retained prefix/order mismatch")
    return grouped


def policy_replay_worker(repo, retained, index, policy_two, output):
    """Rebuild proofs for retained exact terms; forbid constructor enumeration.

    First reproduce the exact saved policy2 order. Only then compare the new
    policy on that unchanged inventory. This is a disclosed regression panel.
    """
    repo, retained, output = Path(repo).resolve(), Path(retained).resolve(), Path(output).resolve()
    previous = json.loads((retained / f"request-{index}-candidate/result.private.json").read_text())
    old_manifest = json.loads((retained / f"request-{index}-candidate/manifest.private.json").read_text())
    record = json.loads((retained / f"request-{index}.private.json").read_text())
    capture = json.loads((retained / "config.private.json").read_text())
    if previous["variant"] != "candidate" or previous["version"] != "owner-v2-bilateral-2":
        raise ValueError("Retained candidate version required")
    if previous["input_sha256"] != digest(record["owner_request"]) or previous["config_sha256"] != digest(capture):
        raise ValueError("Retained input/config mismatch")
    stage_rows = validate_retained_manifest(old_manifest, previous)
    policy_path = "backend/trade_bilateral_presentment.py"
    for name, expected in previous["source"]["file_sha256"].items():
        if name != policy_path and hashlib.sha256((repo / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Constructor or independent evaluator changed; policy-only replay refused")
    if hashlib.sha256(Path(policy_two).read_bytes()).hexdigest() != previous["source"]["file_sha256"][policy_path]:
        raise ValueError("Saved policy2 source mismatch")
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.environ["DATABASE_URL"] = "sqlite:///" + str(output / "isolated.sqlite3")
    def forbidden(*args, **kwargs):
        raise RuntimeError("Retained policy replay forbids network and constructor enumeration")
    socket.socket.connect = socket.socket.connect_ex = socket.create_connection = socket.socket.sendto = forbidden
    sys.path.insert(0, str(repo))
    from backend import database as db, trade_service as ts, feature_flags as ff
    from backend import trade_gen_bilateral_candidate as candidate, trade_bilateral_presentment as policy
    from backend.ranking_service import Player
    from backend.eval.scorecard_runner import run_manifest
    from backend.eval.scorecard_replay import PERSONAL_SOURCES
    if policy.VERSION == "bilateral-survivors-2":
        raise ValueError("New separately versioned policy required")
    policy_sha = hashlib.sha256((repo / policy_path).read_bytes()).hexdigest()
    db.metadata.create_all(db.engine)
    cfg = {row["key"]: row["value"] for row in capture["config"]}
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    ts._cfg.update(cfg)
    ff._flags_cache = capture["flags"]["flags"]
    raw = record["owner_request"]
    frozen, k = raw["input"], copy.deepcopy(raw["input"])
    players = {pid: Player(id=pid, name=pid, **attrs) for pid, attrs in k.pop("players").items()}
    members = []
    for member in k.pop("members"):
        sources = (k.get("opponent_sources") or {}).get(member["id"], {})
        members.append(ts.LeagueMember(member["id"], member["id"], member["roster"], member["elo"],
            bool(member["elo"]) and any(source in PERSONAL_SOURCES for source in sources.values()), confidence_sources=sources))
    k.update(players=players, league=ts.League("frozen-revision", "Private offline replay", "espn", members), config=cfg)
    for key in ("past_decision_keys", "exclusion_keys"):
        k[key] = {(frozenset(a), frozenset(b)) for a, b in k.get(key, [])}
    k.pop("roster_owner_map", None)
    candidate.generate_bilateral_trades = candidate._Search.candidates = forbidden
    rows = stage_rows["native.full"]
    cards = [ts.TradeCard("retained-" + row["offer_id"], "frozen-revision", frozen["user_id"],
        old_manifest["contexts"][row["context_id"]]["managers"]["B"]["manager_id"], "Private",
        list(row["terms"]["A"]), list(row["terms"]["B"]), 0, 0, 0) for row in rows]
    proofs = candidate.evaluate_bilateral_trades(cards, **k) if cards else []
    if len(proofs) != len(cards):
        raise AssertionError("Proof rebuild did not cover every retained occurrence")
    for rank, (card, proof) in enumerate(zip(cards, proofs)):
        if not proof.eligible:
            raise AssertionError("Retained constructor eligibility changed")
        data = proof.as_dict()
        card.owner_evaluation = proof
        card.give_value, card.receive_value, card.fairness_score = data["market"]["give"], data["market"]["receive"], data["market"]["ratio"]
        card.basis = "consensus" if data["viewer"]["preference_evidence"]["state"] == "unknown" else "divergence"
        card.lane = "window" if data["viewer"]["team_plan_gain"] > .01 else "value"
        card.owner_group, card.owner_groups = data["direction"], tuple(data["compatible_groups"])
        card.composite_score = card.mismatch_score = float(len(cards) - rank)
        if not proof.matches(card):
            raise AssertionError("Rebuilt proof does not bind retained terms")
    by_id = {digest(card_identity(card)): card for card in cards}
    retained_rows = stage_rows["post_significance.full"]
    survivors = [by_id[row["offer_id"]] for row in retained_rows]
    import importlib.util
    spec = importlib.util.spec_from_file_location("backend._retained_bilateral_policy2", policy_two)
    old_policy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old_policy)
    arguments = {"selected_give": frozen.get("pinned_give_players") or (),
        "selected_receive": frozen.get("pinned_receive_players") or (), "opponent_user_id": frozen.get("opponent_user_id")}
    reconstructed_old, _ = old_policy.present(survivors, **arguments)
    expected_order = [row["offer_id"] for row in stage_rows["post_survivor_order.full"]]
    if [digest(card_identity(card)) for card in reconstructed_old] != expected_order:
        raise AssertionError("Proof rebuild did not reproduce exact retained policy2 order")
    new_order, diagnostics = policy.present(survivors, **arguments)
    assert_survivor_permutation(survivors, new_order)
    row_by_id = {row["offer_id"]: row for row in rows}
    manifest = {"schema_version": 1, "benchmark_id": VERSION + "-policy-regression",
        "evidence_class": "disclosed_retained_inventory_policy_regression", "contexts": old_manifest["contexts"],
        "requests": [{"model_id": "candidate_policy_repair", "request_id": "request", "status": "ok" if cards else "empty"}], "offers": []}
    metrics = {}
    market_fn = ts.make_consensus_value_fn(k["seed_elo"], players)
    market = {pid: market_fn(pid) for pid in players if pid in k["seed_elo"]}
    for view, view_cards in {"full": new_order, **{f"first{cut}": new_order[:cut] for cut in CUTS}}.items():
        stage = "post_survivor_order." + view
        metrics[stage] = raw_diagnostics(view_cards, frozen, market,
            focused_target="b_wr" if raw.get("intervention", "").startswith("target_preference_") else None)
        for rank, card in enumerate(view_cards, 1):
            row = dict(row_by_id[digest(card_identity(card))], model_id="candidate_policy_repair", stage=stage, native_rank=rank)
            manifest["offers"].append(row)
    result = {"request_index": index, "model_version": candidate.VERSION, "policy_version": policy.VERSION,
        "status": "ok" if cards else "empty", "input_sha256": digest(raw), "config_sha256": digest(capture),
        "retained_manifest_sha256": digest(old_manifest), "constructor_source": previous["source"],
        "policy_source_sha256": policy_sha, "benchmark_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "constructor_enumeration": "forbidden", "proof_rebuild": "exact_retained_terms_only",
        "policy2_exact_order_reproduced": True, "inventory_count": len(cards), "survivor_count": len(survivors),
        "inherited_native_and_significance": {key: value for key, value in previous["stages"].items() if not key.startswith("post_survivor_order.")},
        "previous_policy_stages": {key: value for key, value in previous["stages"].items() if key.startswith("post_survivor_order.")},
        "stages": metrics, "scorecard": run_manifest(manifest), "policy_diagnostics": diagnostics,
        "release_status": "evidence-limited; disclosed regression panel, not blind release test"}
    if hashlib.sha256((repo / policy_path).read_bytes()).hexdigest() != policy_sha:
        raise RuntimeError("Policy changed during replay")
    for name, expected in previous["source"]["file_sha256"].items():
        if name != policy_path and hashlib.sha256((repo / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError("Constructor/evaluator source changed during policy replay")
    private_json(output / "manifest.private.json", manifest)
    private_json(output / "result.private.json", result)
    return result


def replay_policy(args):
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    original = json.loads((args.policy_replay / "summary.json").read_text())
    results = []
    for previous in original["results"]:
        if previous["variant"] != "candidate":
            continue
        index = previous["request_index"]
        folder = args.output / f"request-{index}"
        command = [sys.executable, str(Path(__file__).resolve()), "--policy-worker", "--repo", str(args.candidate_repo.resolve()),
            "--policy-replay", str(args.policy_replay.resolve()), "--request-index", str(index),
            "--policy-two", str(args.policy_two.resolve()), "--output", str(folder.resolve())]
        process = subprocess.run(command, cwd=args.candidate_repo, env=worker_environment(),
                                 capture_output=True, text=True, timeout=args.timeout)
        if process.returncode:
            private_json(args.output / f"error-{index}.private.json", {"stdout": process.stdout, "stderr": process.stderr})
            raise RuntimeError(f"Policy replay failed at retained request {index}; incomplete run is not a pass")
        result = json.loads((folder / "result.private.json").read_text())
        safe = copy.deepcopy(result)
        for group in ("stages", "inherited_native_and_significance", "previous_policy_stages"):
            for metric in safe[group].values():
                for key in list(metric):
                    if key.startswith("private_"):
                        metric.pop(key)
        safe["policy_diagnostics"].pop("occurrence_original_indices", None)
        results.append(dict(safe, cohort=previous["cohort"]))
        print(json.dumps({"request_index": index, "status": result["status"], "policy_version": result["policy_version"]}), flush=True)
    private_json(args.output / "summary.json", {"benchmark_version": VERSION + "-policy-regression",
        "previous_summary_sha256": digest(original), "results": results,
        "release_status": "evidence-limited", "limitations": ["Disclosed regression panel, not blind release evidence",
            "Proofs rebuilt from retained exact terms; no constructor enumeration", "Previous latency and observed-coverage limitations remain"]})


def run(args):
    output = args.output.resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    envelope = json.loads(args.snapshot.read_text()) if args.snapshot else {"requests": []}
    capture = json.loads(args.config.read_text()) if args.config else envelope["config"]
    records, repeated = request_records(envelope)
    if args.synthetic:
        records.extend(constructed_requests())
    split = frozen_split(records)
    private_json(output / "split.private.json", split)
    panel = set(diagnostic_panel(records, split)) if args.diagnostic_panel else set(range(len(records)))
    selection_manifest = None
    if args.selection_manifest:
        selection_manifest = json.loads(args.selection_manifest.read_text())
        if selection_manifest.get("capture_sha256") != digest(envelope):
            raise ValueError("Locked selection does not bind this capture")
        selected_hashes = set(selection_manifest["selected_input_sha256"])
        known_hashes = {digest(record["owner_request"]["input"]) for record in records if isinstance(record.get("owner_request", {}).get("input"), dict)}
        if not selected_hashes <= known_hashes:
            raise ValueError("Locked panel input missing from capture")
        panel = {index for index, record in enumerate(records) if record.get("owner_request", {}).get("data_kind") == "synthetic"
            or digest(record.get("owner_request", {}).get("input")) in selected_hashes}
    private_json(output / "selected-indices.private.json", sorted(panel))
    gate = json.loads((FIXTURES / "gates.json").read_text())
    corpus_hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in FIXTURES.glob("*.json")}
    config_path = output / "config.private.json"
    private_json(config_path, capture)
    results, pairs, interventions = [], [], {}
    attempted = 0
    for index, record in enumerate(records):
        if index not in panel:
            continue
        cohort = split["assignments"][index]
        if args.cohort != "all" and cohort != args.cohort and cohort != "constructed":
            continue
        attempted += 1
        request_path = output / f"request-{index}.private.json"
        private_json(request_path, record)
        pair = {}
        for variant, repo in (("incumbent", args.baseline_repo), ("candidate", args.candidate_repo)):
            if args.variant and args.variant != variant:
                continue
            folder = output / f"request-{index}-{variant}"
            command = [sys.executable, str(Path(__file__).resolve()), "--worker", "--repo", str(repo.resolve()),
                "--request", str(request_path), "--config", str(config_path), "--output", str(folder), "--variant", variant]
            env = worker_environment()
            proc = None
            try:
                reusable = args.reuse_incumbent / f"request-{index}-incumbent/result.private.json" if args.reuse_incumbent and variant == "incumbent" else None
                if reusable and reusable.exists():
                    result = json.loads(reusable.read_text())
                    validate_reused_incumbent(result, raw=record.get("owner_request"), capture=capture,
                        source=source_manifest(repo.resolve(), "incumbent"),
                        runner_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
                else:
                    proc = subprocess.run(command, cwd=repo, env=env, capture_output=True, text=True, timeout=args.timeout)
                    if proc.returncode:
                        raise RuntimeError("worker_failed")
                    result = json.loads((folder / "result.private.json").read_text())
            except (subprocess.TimeoutExpired, RuntimeError) as exc:
                result = {"variant": variant, "status": "error", "error_type": type(exc).__name__}
                private_json(output / f"error-{index}-{variant}.private.json",
                    {"error": str(exc), "stdout": getattr(proc, "stdout", ""),
                     "stderr": getattr(proc, "stderr", "")})
            pair[variant] = result
            intervention = record.get("owner_request", {}).get("intervention")
            if intervention:
                interventions[variant, intervention] = result
            # The retained per-request manifest is private; aggregate summaries
            # remove target-price keys even though those keys are hashed.
            safe = copy.deepcopy(result)
            for metric in safe.get("stages", {}).values():
                metric.pop("private_cheapest_exact_target_prices", None)
                metric.pop("private_focused_target_prices", None)
                metric.pop("private_first_exact_target_prices", None)
            safe.get("policy", {}).pop("occurrence_original_indices", None)
            results.append(dict(safe, request_index=index, cohort=cohort))
            print(json.dumps({"request_index": index, "variant": variant, "status": result["status"],
                              "native_offers": result.get("stages", {}).get("native.full", {}).get("offers")}), flush=True)
        if "incumbent" in pair and "candidate" in pair:
            pairs.append(dict(compare_pair(pair["incumbent"], pair["candidate"]), request_index=index, cohort=cohort))
    sensitivity = {}
    for variant in ("incumbent", "candidate"):
        sensitivity[variant] = {}
        for stage in ("native.full", "post_survivor_order.full"):
            low = interventions.get((variant, "target_preference_lower"), {}).get("stages", {}).get(stage, {})
            high = interventions.get((variant, "target_preference_higher"), {}).get("stages", {}).get(stage, {})
            sensitivity[variant][stage] = preference_price_probe(low, high)
    summary = {"benchmark_version": VERSION, "gate_sha256": digest(gate), "gates": gate,
        "corpus_file_sha256": corpus_hashes,
        "selection_frame": envelope.get("selection_frame", envelope.get("selection", "caller-supplied frozen captures")),
        "inventory": context_inventory(records), "duplicate_frozen_inputs_removed": repeated,
        "split": {key: value for key, value in split.items() if key != "assignments"},
        "requested_cohort": args.cohort, "requested_variant": args.variant or "paired",
        "panel_selection": selection_manifest.get("rule") if selection_manifest else "Input hash minimum per selected outlook/format plus every holdout and constructed case" if args.diagnostic_panel else "all captured contexts",
        "selection_manifest_sha256": digest(selection_manifest) if selection_manifest else None,
        "selected_context_count": len(panel), "unselected_context_count": len(records) - len(panel),
        "attempted_requests_per_variant": attempted, "run_status_counts": dict(Counter(r["status"] for r in results)),
        "results": results, "comparisons": pairs, "preference_price_sensitivity": sensitivity,
        "release_status": "evidence-limited",
        "observed_outcomes": {"status": "unknown", "mature_eligible_cohort_count": 0},
        "limitations": ["Common significance projection is not complete live serving validation",
            "Fixed ESPN league wrapper is not platform-adapter validation; common configuration is not historical served configuration",
            "Bakeoff capture frame excludes uncaptured/oversized/no-request cases; replay errors are not observed production error rates",
            "No market freshness, pick-ledger, board or projection evidence is invented",
            "Counterfactual/synthetic copies are not independent observed contexts",
            "Native constructor latency excludes preparation, persistence, network and device rendering",
            "Unratified empirical margins and absent observed eligible outcome cohort prevent promotion"]}
    private_json(output / "summary.json", summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-repo", type=Path)
    parser.add_argument("--candidate-repo", type=Path, default=Path.cwd())
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--cohort", choices=("all", "development", "holdout"), default="all")
    parser.add_argument("--reuse-incumbent", type=Path)
    parser.add_argument("--diagnostic-panel", action="store_true")
    parser.add_argument("--selection-manifest", type=Path)
    parser.add_argument("--policy-replay", type=Path)
    parser.add_argument("--policy-two", type=Path)
    parser.add_argument("--policy-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--request-index", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--repo", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--request", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--variant", choices=("incumbent", "candidate"), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.policy_worker:
        policy_replay_worker(args.repo, args.policy_replay, args.request_index, args.policy_two, args.output)
    elif args.policy_replay:
        if not args.policy_two:
            parser.error("--policy-two source required for exact retained-order bridge")
        replay_policy(args)
    elif args.worker:
        worker(args.repo, args.request, args.config, args.output, args.variant)
    else:
        if not args.baseline_repo or not (args.snapshot or args.synthetic):
            parser.error("--baseline-repo and at least one of --snapshot/--synthetic required")
        run(args)


if __name__ == "__main__":
    main()
