"""Team overhaul — pure domain rules (no Flask, no DB, no network).

Contract: docs/plans/team-overhaul/BUILD-CONTRACT.md §1–§6. Product rules
R1–R9 and the §5 invariants of PRODUCT-SPEC.md are enforced here so every
piece is unit-testable with fixtures. Persistence lives in
`overhaul_store.py`; HTTP in `overhaul_api.py`.

Offers passed to the assembly / validation functions are plain dicts with at
least: offer_id, give_ids, receive_ids, counterparty_user_id, decision,
availability, is_recovery, score.
"""
from __future__ import annotations

import hashlib
import itertools
import uuid

# §2 — search bounds are module constants; no model_config keys, no env vars.
OVERHAUL_BATCH_SIZE = 24
OVERHAUL_MAX_SUBSETS = 40
OVERHAUL_MAX_ROADMAPS = 5
OVERHAUL_MIN_PACKAGES = 4
OVERHAUL_MAX_PACKAGES = 5
OVERHAUL_MAX_ALTS_PER_PACKAGE = 6
OVERHAUL_GENERATION_BUDGET_S = 20.0

# Internal solver bounds (not wire-visible).
_BEAM_WIDTH = 24
_CAPACITY_COMBINATION_CAP = 200
_COUNTERPARTY_REPEAT_PENALTY = 0.35
_RECOVERY_BONUS = 0.5

GENERIC_PICK_PREFIX = "generic_pick_"

OUTLOOKS = ("push_all_in", "blow_it_up")
OUTLOOK_TO_ENGINE = {"push_all_in": "championship", "blow_it_up": "jets"}
REBUILD_RETURNS = ("picks", "young_players", "mixed")
DECISIONS = ("like", "pass", "undecided")
OVERHAUL_STATUSES = ("setup", "reviewing", "assembled", "executing", "complete", "archived")
RECOVERY_STATES = ("owned", "missing_with_known_holder", "unknown", "unsupported", "not_yet_available")
SHORTFALL_REASONS = ("insufficient_likes", "overlapping_sells", "competing_incoming",
                     "no_return_supply", "recovery_unresolved", "roster_limitation",
                     "stale_ownership", "budget_restriction", "search_exhausted")
VALIDATION_CODES = ("give_overlap", "receive_overlap", "asset_not_owned",
                    "counterparty_asset_not_owned", "pool_violation", "capacity_exceeded",
                    "lineup_illegal", "offer_stale", "offer_not_liked", "recovery_unresolved",
                    "tier_duplicate_counterparty", "asset_reserved", "depth_reduced")

ATTEMPT_STATES = ("queued", "sending", "proposed", "send_failed", "outcome_unknown", "accepted",
                  "declined", "expired", "withdrawn", "invalidated", "resolved_elsewhere", "stale")
LIVE_ATTEMPT_STATES = frozenset(("queued", "sending", "proposed", "outcome_unknown"))
# Allowed transitions. Anything not listed is refused; terminal states never regress.
_ATTEMPT_TRANSITIONS = {
    "queued": frozenset(("sending", "invalidated", "stale")),
    "sending": frozenset(("proposed", "send_failed", "outcome_unknown")),
    "proposed": frozenset(("accepted", "declined", "expired", "withdrawn", "invalidated",
                           "resolved_elsewhere")),
    "outcome_unknown": frozenset(("accepted", "declined", "expired", "withdrawn", "invalidated",
                                  "resolved_elsewhere", "proposed")),
}
USER_REPORTABLE_STATES = frozenset(("declined", "withdrawn", "expired"))
STATE_SOURCES = ("server", "provider", "ownership_refresh", "user_reported")
# A `queued`/`sending` attempt older than this lost its worker (crash mid-batch);
# refresh sweeps it so it stops holding the package and its reservation.
LIVE_STUCK_AFTER_S = 300.0


class ValidationError(ValueError):
    """A structured domain refusal: `code` is the wire error, `detail` optional."""

    def __init__(self, code: str, detail=None):
        super().__init__(code)
        self.code = code
        self.detail = detail


def new_id(prefix: str) -> str:
    return prefix + uuid.uuid4().hex[:12]


def is_generic_pick(asset_id) -> bool:
    return str(asset_id or "").startswith(GENERIC_PICK_PREFIX)


def _ids(values) -> list[str]:
    return [str(v) for v in (values or []) if str(v)]


# ---------------------------------------------------------------------------
# Settings (§5.1)
# ---------------------------------------------------------------------------

def default_settings() -> dict:
    return {"outlook": None, "eligible_asset_ids": [], "preferred_positions": [],
            "rebuild_return": None, "pick_budget": None, "target_package_count": 4}


def merge_settings(current: dict, partial: dict, *, owned_ids) -> dict:
    """Apply a partial settings write. Raises ValidationError on bad input."""
    if not isinstance(partial, dict):
        raise ValidationError("bad_request", "settings must be an object")
    out = dict(default_settings())
    out.update(current or {})
    owned = set(_ids(owned_ids))
    for key, value in partial.items():
        if key == "outlook":
            if value is not None and value not in OUTLOOKS:
                raise ValidationError("bad_request", "invalid outlook")
            out["outlook"] = value
        elif key == "eligible_asset_ids":
            if not isinstance(value, list):
                raise ValidationError("bad_request", "eligible_asset_ids must be a list")
            ids = []
            for raw in value:
                aid = str(raw or "")
                if not aid:
                    raise ValidationError("bad_request", "empty asset id")
                if is_generic_pick(aid):
                    raise ValidationError("generic_pick_not_allowed", aid)
                if aid not in owned:
                    raise ValidationError("asset_not_owned", aid)
                if aid not in ids:
                    ids.append(aid)
            out["eligible_asset_ids"] = ids
        elif key == "preferred_positions":
            if not isinstance(value, list) or any(not isinstance(p, str) for p in value):
                raise ValidationError("bad_request", "preferred_positions must be a list of strings")
            out["preferred_positions"] = [p.upper() for p in value]
        elif key == "rebuild_return":
            if value is not None and value not in REBUILD_RETURNS:
                raise ValidationError("bad_request", "invalid rebuild_return")
            out["rebuild_return"] = value
        elif key == "pick_budget":
            if value is not None:
                if not isinstance(value, dict):
                    raise ValidationError("bad_request", "pick_budget must be an object")
                budget = {}
                for field, lo in (("max_picks", 0), ("max_round", 1)):
                    n = value.get(field)
                    if n is not None and (isinstance(n, bool) or not isinstance(n, int) or n < lo):
                        raise ValidationError("bad_request", f"invalid pick_budget.{field}")
                    budget[field] = n
                seasons = value.get("seasons")
                if seasons is not None and (not isinstance(seasons, list)
                                            or any(isinstance(s, bool) or not isinstance(s, int) for s in seasons)):
                    raise ValidationError("bad_request", "invalid pick_budget.seasons")
                budget["seasons"] = seasons
                if budget["max_round"] is None:
                    budget["max_round"] = 3
                if budget["seasons"] is None:
                    budget["seasons"] = []
                value = budget
            out["pick_budget"] = value
        elif key == "target_package_count":
            if value not in (4, 5) or isinstance(value, bool):
                raise ValidationError("bad_request", "target_package_count must be 4 or 5")
            out["target_package_count"] = value
        else:
            raise ValidationError("bad_request", f"unknown setting {key}")
    return out


def settings_invalidate_offers(before: dict, after: dict) -> bool:
    """Changing outlook or the pool marks undecided offers stale (§7 settings)."""
    return (before.get("outlook") != after.get("outlook")
            or sorted(_ids(before.get("eligible_asset_ids"))) != sorted(_ids(after.get("eligible_asset_ids"))))


# ---------------------------------------------------------------------------
# Recovery identity (§5.3, R3, invariant 7)
# ---------------------------------------------------------------------------

def recovery_requirement(*, outlook, season, picks, my_user_id, my_roster_id=None,
                         picks_supported=True) -> dict:
    """Exact own-first identity: league season + 1, round 1, MY original roster.

    `picks` are draft_picks rows (platform source). An empty table is
    `unknown`, never `missing`; a supported platform that has not published
    that season yet is `not_yet_available`.
    """
    applicable = outlook == "blow_it_up"
    target = int(season) + 1 if isinstance(season, int) else None
    base = {"applicable": applicable, "season": target, "state": "unknown", "pick_id": None,
            "holder_user_id": None, "holder_username": None, "resolved": False,
            "draft_order_rule": "unknown"}
    if not picks_supported:
        base["state"] = "unsupported"
        return base
    rows = list(picks or [])
    if not rows or target is None:
        return base
    seasons = {int(r.get("season")) for r in rows if str(r.get("season") or "").lstrip("-").isdigit()}
    if target not in seasons:
        base["state"] = "not_yet_available"
        return base
    me = str(my_user_id or "")
    rid = str(my_roster_id) if my_roster_id is not None else None
    for r in rows:
        try:
            if int(r.get("season")) != target or int(r.get("round")) != 1:
                continue
        except (TypeError, ValueError):
            continue
        original_user = str(r.get("original_user_id") or "")
        original_roster = str(r.get("original_roster_id") or "")
        if not ((me and original_user == me) or (rid is not None and original_roster == rid)):
            continue
        base["pick_id"] = str(r.get("pick_id"))
        holder = str(r.get("owner_user_id") or "")
        if holder == me:
            base["state"] = "owned"
        elif holder:
            base["state"] = "missing_with_known_holder"
            base["holder_user_id"] = holder
            base["holder_username"] = r.get("owner_username")
        else:
            base["state"] = "unknown"
        return base
    return base


# ---------------------------------------------------------------------------
# Candidate subsets (§6 step 2)
# ---------------------------------------------------------------------------

def _pick_within_budget(pick_id, pick_meta, budget) -> bool:
    if not budget:
        return True
    meta = (pick_meta or {}).get(pick_id) or {}
    max_round = budget.get("max_round")
    seasons = budget.get("seasons")
    if max_round is not None and meta.get("round") is not None and int(meta["round"]) > int(max_round):
        return False
    if seasons and meta.get("season") is not None and int(meta["season"]) not in {int(s) for s in seasons}:
        return False
    return True


def enumerate_subsets(pool_ids, *, values, outlook, is_pick, pick_budget=None, pick_meta=None,
                      exhausted=(), max_subsets=OVERHAUL_MAX_SUBSETS) -> list[tuple[str, ...]]:
    """Ordered candidate give-subsets from the eligible pool.

    Order: singles (by value desc); pairs by combined value; for push_all_in
    pick-only subsets within the budget; for blow_it_up top-value player
    pairs are promoted ahead of mixed pairs. Subsets already exhausted by a
    prior run are skipped. Output is bounded and deterministic.
    """
    pool = _ids(pool_ids)
    val = {a: float((values or {}).get(a) or 0.0) for a in pool}
    picks = [a for a in pool if is_pick(a)]
    players = [a for a in pool if not is_pick(a)]
    if outlook == "push_all_in" and pick_budget:
        picks = [p for p in picks if _pick_within_budget(p, pick_meta, pick_budget)]
        pool = players + picks
    done = {tuple(sorted(_ids(s))) for s in exhausted}
    ordered: list[tuple[str, ...]] = []
    seen = set()

    def add(subset):
        key = tuple(sorted(subset))
        if key in seen or key in done or not key:
            return
        seen.add(key)
        ordered.append(key)

    for a in sorted(pool, key=lambda x: (-val[x], x)):
        add((a,))
    pairs = [(a, b) for a, b in itertools.combinations(sorted(pool), 2)]
    pairs.sort(key=lambda p: (-(val[p[0]] + val[p[1]]), p))
    if outlook == "blow_it_up":
        player_pairs = [p for p in pairs if not is_pick(p[0]) and not is_pick(p[1])]
        for p in player_pairs:
            add(p)
    if outlook == "push_all_in":
        pick_only = [p for p in pairs if is_pick(p[0]) and is_pick(p[1])]
        max_picks = (pick_budget or {}).get("max_picks")
        for p in pick_only:
            if max_picks is None or len(p) <= int(max_picks):
                add(p)
    for p in pairs:
        add(p)
    return ordered[:max(0, int(max_subsets))]


# ---------------------------------------------------------------------------
# Pool enforcement + normalization (§6 steps 5–6, E01)
# ---------------------------------------------------------------------------

def card_passes_pool(*, give_ids, receive_ids, counterparty_user_id, seller_user_id, pool) -> bool:
    give, recv = _ids(give_ids), _ids(receive_ids)
    if not give or not recv:
        return False
    if str(counterparty_user_id or "") in ("", str(seller_user_id)):
        return False
    if any(is_generic_pick(a) for a in give + recv):
        return False
    return set(give) <= set(_ids(pool))


def filter_cards(cards, *, pool, seller_user_id):
    """Drop every card whose give set escapes the pool (the E01 guarantee).

    `cards` expose give_player_ids / receive_player_ids / target_user_id.
    Returns (kept, rejected_count).
    """
    kept, rejected = [], 0
    for card in cards:
        if card_passes_pool(give_ids=card.give_player_ids, receive_ids=card.receive_player_ids,
                            counterparty_user_id=card.target_user_id,
                            seller_user_id=seller_user_id, pool=pool):
            kept.append(card)
        else:
            rejected += 1
    return kept, rejected


def package_hash(*, platform, league_id, seller_user_id, counterparty_user_id, give_ids, receive_ids) -> str:
    parts = [str(platform), str(league_id), str(seller_user_id), str(counterparty_user_id),
             ",".join(sorted(_ids(give_ids))), ",".join(sorted(_ids(receive_ids)))]
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


def offer_score(card_json: dict) -> float:
    """Ranking signal for assembly: fairness first, then the generator's order."""
    fairness = float(card_json.get("fairness_score") or 0.0)
    composite = float(card_json.get("composite_score") or 0.0)
    return round(fairness + composite / 10000.0, 6)


def average_age(asset_ids, players_meta) -> float | None:
    ages = []
    for aid in _ids(asset_ids):
        meta = (players_meta or {}).get(aid)
        age = getattr(meta, "age", None) if meta is not None and not isinstance(meta, dict) else (meta or {}).get("age")
        if isinstance(age, (int, float)) and age > 0:
            ages.append(float(age))
    return sum(ages) / len(ages) if ages else None


def receive_side_allowed(receive_ids, *, outlook, rebuild_return, is_pick) -> bool:
    """R4.4 — `picks` return requires at least one pick on the receive side."""
    if outlook == "blow_it_up" and rebuild_return == "picks":
        return any(is_pick(a) for a in _ids(receive_ids))
    return True


# ---------------------------------------------------------------------------
# Roadmap assembly (R6, §5.5, D4)
# ---------------------------------------------------------------------------

def _usable(offer) -> bool:
    return offer.get("decision") == "like" and offer.get("availability", "fresh") == "fresh"


def partition_packages(offers, *, pool) -> list[dict]:
    """Group liked, fresh, in-pool offers by exact give set; rank alternatives."""
    groups: dict[tuple, list] = {}
    pool_set = set(_ids(pool))
    for offer in offers:
        if not _usable(offer):
            continue
        give = tuple(sorted(_ids(offer.get("give_ids"))))
        if not give or not set(give) <= pool_set:
            continue
        groups.setdefault(give, []).append(offer)
    out = []
    for give, alts in groups.items():
        alts = sorted(alts, key=lambda o: (-float(o.get("score") or 0.0), o["offer_id"]))
        alts = alts[:OVERHAUL_MAX_ALTS_PER_PACKAGE]
        out.append({"give": frozenset(give), "alts": alts,
                    "is_recovery": any(o.get("is_recovery") for o in alts),
                    "best": float(alts[0].get("score") or 0.0)})
    out.sort(key=lambda g: (-int(g["is_recovery"]), -g["best"], sorted(g["give"])))
    return out


def _compatible_alts(group, used_receive):
    return [o for o in group["alts"] if not (set(_ids(o["receive_ids"])) & used_receive)]


def _state_score(chosen) -> float:
    score, seen = 0.0, {}
    for g in chosen:
        score += g["best"] + 0.05 * (len(g["alts"]) - 1)
        if g["is_recovery"]:
            score += _RECOVERY_BONUS
        for o in g["alts"]:
            cp = o["counterparty_user_id"]
            seen[cp] = seen.get(cp, 0) + 1
    score -= _COUNTERPARTY_REPEAT_PENALTY * sum(n - 1 for n in seen.values() if n > 1)
    return round(score, 6)


def _beam(groups, *, target, min_packages, check_receive=True):
    """Bounded beam over give-disjoint package sets; returns complete states."""
    complete = []
    beam = [([], 0)]  # (chosen groups, next candidate index)
    for _depth in range(target):
        next_beam = []
        for chosen, start in beam:
            used_give = set().union(*(g["give"] for g in chosen)) if chosen else set()
            used_recv = set()
            for g in chosen:
                for o in g["alts"]:
                    used_recv |= set(_ids(o["receive_ids"]))
            for idx in range(start, len(groups)):
                cand = groups[idx]
                if cand["give"] & used_give:
                    continue
                alts = _compatible_alts(cand, used_recv) if check_receive else list(cand["alts"])
                if not alts:
                    continue
                pruned = dict(cand, alts=alts, best=float(alts[0].get("score") or 0.0),
                              is_recovery=any(o.get("is_recovery") for o in alts))
                state = chosen + [pruned]
                next_beam.append((state, idx + 1))
                if len(state) >= min_packages:
                    complete.append(state)
        next_beam.sort(key=lambda s: -_state_score(s[0]))
        beam = next_beam[:_BEAM_WIDTH]
        if not beam:
            break
    return complete


def diversity_key(package_gives) -> str:
    return "|".join(",".join(sorted(g)) for g in sorted(package_gives, key=lambda g: sorted(g)))


def assemble_roadmaps(offers, *, pool, target_package_count=4, recovery=None,
                      max_roadmaps=OVERHAUL_MAX_ROADMAPS, min_packages=OVERHAUL_MIN_PACKAGES):
    """Return (roadmaps, shortfall). Each roadmap: {packages, summary, rank}.

    Packages carry one alternative per tier in server rank order (§5.5). A
    roadmap needs ≥ `min_packages` give-disjoint, receive-disjoint packages
    built only from liked, fresh, in-pool offers (invariants 3, 4, 10).
    """
    target = max(min_packages, min(OVERHAUL_MAX_PACKAGES, int(target_package_count or min_packages)))
    groups = partition_packages(offers, pool=pool)
    liked = [o for o in offers if o.get("decision") == "like"]
    if not liked:
        return [], {"reason": "insufficient_likes", "detail": "No liked offers yet."}
    if not groups:
        stale = [o for o in liked if o.get("availability") != "fresh"]
        if stale and len(stale) == len(liked):
            return [], {"reason": "stale_ownership", "detail": "Every liked offer is stale."}
        return [], {"reason": "insufficient_likes", "detail": "No liked offers inside the pool."}
    states = _beam(groups, target=target, min_packages=min_packages)
    if not states:
        give_only = _beam(groups, target=target, min_packages=min_packages, check_receive=False)
        if give_only:
            reason, detail = "competing_incoming", "Liked offers compete for the same incoming assets."
        elif len(groups) < min_packages:
            reason = "insufficient_likes" if len(liked) < min_packages else "overlapping_sells"
            detail = f"Only {len(groups)} distinct outgoing package(s) among liked offers."
        else:
            reason, detail = "overlapping_sells", "Liked packages share outgoing assets."
        return [], {"reason": reason, "detail": detail}
    ranked = sorted(states, key=lambda s: (-_state_score(s), -len(s), diversity_key([g["give"] for g in s])))
    roadmaps, seen = [], set()
    for state in ranked:
        key = diversity_key([g["give"] for g in state])
        if key in seen:
            continue
        seen.add(key)
        roadmaps.append(_roadmap_from_state(state, pool=pool, recovery=recovery, rank=len(roadmaps) + 1, key=key))
        if len(roadmaps) >= max_roadmaps:
            break
    return roadmaps, None


def _roadmap_from_state(state, *, pool, recovery, rank, key):
    packages, outgoing, incoming, counterparties = [], [], [], []
    for g in state:
        tiers = [{"tier": i + 1, "offer_ids": [o["offer_id"]]} for i, o in enumerate(g["alts"])]
        reason = "recover_own_first" if g["is_recovery"] else "outlook_move"
        packages.append({"package_id": new_id("pk_"), "give_ids": sorted(g["give"]), "reason": reason,
                         "advisory_rank": 1 if reason == "recover_own_first" else 0,
                         "tiers": tiers, "status": "open"})
        outgoing.extend(sorted(g["give"]))
        for o in g["alts"]:
            for a in _ids(o["receive_ids"]):
                if a not in incoming:
                    incoming.append(a)
            if o["counterparty_user_id"] not in counterparties:
                counterparties.append(o["counterparty_user_id"])
    unused = [a for a in _ids(pool) if a not in set(outgoing)]
    resolved = bool(recovery and recovery.get("applicable")
                    and any(p["reason"] == "recover_own_first" for p in packages))
    summary = {"outgoing_ids": outgoing, "incoming_ids": incoming, "counterparties": counterparties,
               "unused_eligible_ids": unused, "score": _state_score(state), "diversity_key": key,
               "recovery_resolved": resolved}
    return {"packages": packages, "summary": summary, "rank": rank,
            "offer_ids": [o["offer_id"] for g in state for o in g["alts"]]}


# ---------------------------------------------------------------------------
# Priorities (R7, D4)
# ---------------------------------------------------------------------------

def validate_priorities(package: dict, tiers, offers_by_id: dict) -> list[dict]:
    """Return normalized tiers or raise ValidationError.

    Offer ids must belong to the package; every fresh liked alternative
    appears exactly once (stale ones may be omitted); tiers are contiguous
    from 1; no two offers in one tier share a counterparty (D4).
    """
    if not isinstance(tiers, list) or not tiers:
        raise ValidationError("bad_request", "tiers must be a non-empty list")
    universe = [oid for t in package.get("tiers", []) for oid in t.get("offer_ids", [])]
    required = {oid for oid in universe
                if offers_by_id.get(oid) and _usable(offers_by_id[oid])}
    seen, out = [], []
    for i, tier in enumerate(tiers, start=1):
        if not isinstance(tier, dict) or tier.get("tier") != i:
            raise ValidationError("bad_request", "tiers must be contiguous from 1")
        ids = tier.get("offer_ids")
        if not isinstance(ids, list) or not ids:
            raise ValidationError("bad_request", f"tier {i} is empty")
        ids = _ids(ids)
        counterparties = set()
        for oid in ids:
            if oid not in universe:
                raise ValidationError("bad_request", f"{oid} is not in this package")
            if oid in seen:
                raise ValidationError("bad_request", f"{oid} appears twice")
            seen.append(oid)
            cp = (offers_by_id.get(oid) or {}).get("counterparty_user_id")
            if cp in counterparties:
                raise ValidationError("tier_duplicate_counterparty", {"tier": i, "offer_id": oid})
            counterparties.add(cp)
        out.append({"tier": i, "offer_ids": ids})
    missing = required - set(seen)
    if missing:
        raise ValidationError("bad_request", {"missing_offer_ids": sorted(missing)})
    return out


# ---------------------------------------------------------------------------
# Union checks (§5.4, D6) and prepare-send validation
# ---------------------------------------------------------------------------

def union_capacity_worst_case(my_player_count: int, packages_alternatives, *, is_pick,
                              cap=_CAPACITY_COMBINATION_CAP) -> int:
    """Arithmetic worst case over one alternative per package.

    `packages_alternatives` is a list (per package) of alternatives, each a
    (give_ids, receive_ids) pair. Picks cost no roster slot. Beyond `cap`
    combinations the per-package max net gain is used (more conservative).
    """
    nets = []
    for alts in packages_alternatives:
        row = []
        for give, recv in alts:
            g = sum(1 for a in _ids(give) if not is_pick(a))
            r = sum(1 for a in _ids(recv) if not is_pick(a))
            row.append(max(0, r - g))
        nets.append(row or [0])
    combos = 1
    for row in nets:
        combos *= max(1, len(row))
    if combos > cap:
        return int(my_player_count) + sum(max(row) for row in nets)
    worst = 0
    for combo in itertools.product(*nets):
        worst = max(worst, sum(combo))
    return int(my_player_count) + worst


def _item(code, message, package_id=None, offer_id=None):
    item = {"code": code, "message": message}
    if package_id:
        item["package_id"] = package_id
    if offer_id:
        item["offer_id"] = offer_id
    return item


def validate_prepare(*, selected, packages, offers_by_id, my_roster_ids, my_pick_ids, pool,
                     rosters, reserved_asset_ids, capacity, recovery, package_states,
                     legality=None, checked_at, is_pick) -> dict:
    """Build the ValidationReceipt (§5.6) for a chosen set of offers.

    `selected` are offer ids; `packages` the roadmap's Package[]; `rosters`
    maps user_id -> asset ids (players + picks) from the snapshot;
    `package_states` maps package_id -> 'open'|'pending'|'complete'|'blocked';
    `legality(counterparty_id, give, receive)` optionally returns
    {"blockers": [...], "unknowns": [...]} from trade_roster.
    """
    blockers, warnings, unknowns = [], [], []
    owned = set(_ids(my_roster_ids)) | set(_ids(my_pick_ids))
    pool_set = set(_ids(pool))
    reserved = set(_ids(reserved_asset_ids))
    by_package = {}
    package_of = {}
    for pkg in packages:
        for tier in pkg.get("tiers", []):
            for oid in tier.get("offer_ids", []):
                package_of[oid] = pkg["package_id"]
    chosen = []
    for oid in _ids(selected):
        offer = offers_by_id.get(oid)
        pkg_id = package_of.get(oid)
        if offer is None or pkg_id is None:
            blockers.append(_item("offer_not_liked", "This offer is not part of the roadmap.", offer_id=oid))
            continue
        if offer.get("decision") != "like":
            blockers.append(_item("offer_not_liked", "Only liked offers can be sent.", pkg_id, oid))
        if offer.get("availability") != "fresh":
            blockers.append(_item("offer_stale", "This offer needs regeneration before sending.", pkg_id, oid))
        state = package_states.get(pkg_id, "open")
        if state == "complete":
            blockers.append(_item("asset_not_owned", "This package already completed.", pkg_id, oid))
        elif state == "pending":
            blockers.append(_item("asset_reserved", "An offer from this package is still pending.", pkg_id, oid))
        by_package.setdefault(pkg_id, []).append(offer)
        chosen.append((pkg_id, offer))
    outgoing, incoming = [], []
    give_owner, recv_owner = {}, {}
    for pkg_id, offer in chosen:
        give, recv = _ids(offer["give_ids"]), _ids(offer["receive_ids"])
        for a in give:
            if a not in owned:
                blockers.append(_item("asset_not_owned", f"You no longer own {a}.", pkg_id, offer["offer_id"]))
            if a not in pool_set:
                blockers.append(_item("pool_violation", f"{a} is outside your eligible pool.", pkg_id, offer["offer_id"]))
            if a in reserved:
                blockers.append(_item("asset_reserved", f"{a} is reserved by a live offer.", pkg_id, offer["offer_id"]))
            prior = give_owner.get(a)
            if prior is not None and prior != pkg_id:
                blockers.append(_item("give_overlap", f"{a} is in two packages.", pkg_id, offer["offer_id"]))
            give_owner.setdefault(a, pkg_id)
            if a not in outgoing:
                outgoing.append(a)
        cp = str(offer.get("counterparty_user_id") or "")
        cp_roster = rosters.get(cp) if isinstance(rosters, dict) else None
        for a in recv:
            if cp_roster is None:
                if "counterparty_roster_unknown" not in unknowns:
                    unknowns.append("counterparty_roster_unknown")
            elif a not in set(_ids(cp_roster)):
                blockers.append(_item("counterparty_asset_not_owned", f"{cp} no longer owns {a}.", pkg_id, offer["offer_id"]))
            prior = recv_owner.get(a)
            if prior is not None and prior != pkg_id:
                blockers.append(_item("receive_overlap", f"{a} is requested by two packages.", pkg_id, offer["offer_id"]))
            recv_owner.setdefault(a, pkg_id)
            if a not in incoming:
                incoming.append(a)
    for pkg_id, offers in by_package.items():
        seen = set()
        for o in offers:
            cp = o.get("counterparty_user_id")
            if cp in seen:
                blockers.append(_item("tier_duplicate_counterparty",
                                      "Two offers in one tier target the same manager.", pkg_id, o["offer_id"]))
            seen.add(cp)
    # Capacity (arithmetic worst case; picks cost nothing).
    my_players = [a for a in _ids(my_roster_ids) if not is_pick(a)]
    alts = [[(o["give_ids"], o["receive_ids"]) for o in offers] for offers in by_package.values()]
    if capacity is None:
        unknowns.append("capacity_unknown")
    elif alts:
        worst = union_capacity_worst_case(len(my_players), alts, is_pick=is_pick)
        if worst > int(capacity):
            blockers.append(_item("capacity_exceeded",
                                  f"Worst case {worst} players exceeds the {capacity}-player roster limit."))
    # Legality on the final union per counterparty (featured = first chosen per package).
    if legality is not None and chosen:
        by_cp = {}
        for pkg_id, offer in chosen:
            by_cp.setdefault(str(offer["counterparty_user_id"]), []).append((pkg_id, offer))
        for cp, items in by_cp.items():
            give = [a for _, o in items for a in _ids(o["give_ids"])]
            recv = [a for _, o in items for a in _ids(o["receive_ids"])]
            try:
                verdict = legality(cp, give, recv) or {}
            except Exception:  # pragma: no cover — never let a checker crash prepare
                verdict = {"unknowns": ["legality_unavailable"]}
            for code in verdict.get("blockers") or []:
                code = str(code)
                if code.startswith("legal_deficits:") or code == "cuts_required":
                    blockers.append(_item("lineup_illegal", f"Lineup would be illegal ({code}).", items[0][0]))
                elif code.startswith("backup_depth:") or code.startswith("deficits:"):
                    warnings.append(_item("depth_reduced", f"Depth is reduced ({code}).", items[0][0]))
            for u in verdict.get("unknowns") or []:
                if u not in unknowns:
                    unknowns.append(str(u))
    if recovery and recovery.get("applicable") and recovery.get("state") == "missing_with_known_holder":
        if not any(o.get("is_recovery") for _, o in chosen):
            warnings.append(_item("recovery_unresolved",
                                  "Priority 1: Recover your first is not in this batch. Sending is still allowed."))
    return {"ok": not blockers, "checked_at": checked_at, "blockers": blockers, "warnings": warnings,
            "unknowns": unknowns, "outgoing_ids": outgoing, "incoming_ids": incoming}


def races(selected, packages) -> list[dict]:
    package_of = {oid: pkg["package_id"] for pkg in packages for t in pkg.get("tiers", []) for oid in t.get("offer_ids", [])}
    groups = {}
    for oid in _ids(selected):
        pid = package_of.get(oid)
        if pid:
            groups.setdefault(pid, []).append(oid)
    return [{"package_id": pid, "offer_ids": ids} for pid, ids in groups.items() if len(ids) > 1]


def summary_hash(offer_ids, *, roadmap_version, revision) -> str:
    raw = "|".join(sorted(_ids(offer_ids))) + f"|v{int(roadmap_version)}|r{int(revision)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def request_hash(offer_ids, *, roadmap_version) -> str:
    raw = "|".join(sorted(_ids(offer_ids))) + f"|v{int(roadmap_version)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def package_status(package, offers_by_id, attempts) -> str:
    pid = package["package_id"]
    mine = [a for a in attempts if a.get("package_id") == pid]
    if any(a.get("state") == "accepted" for a in mine):
        return "complete"
    if any(a.get("state") in LIVE_ATTEMPT_STATES for a in mine):
        return "pending"
    ids = [oid for t in package.get("tiers", []) for oid in t.get("offer_ids", [])]
    if not any(offers_by_id.get(oid) and _usable(offers_by_id[oid]) for oid in ids):
        return "blocked"
    return "open"


def default_send_selection(packages, offers_by_id, attempts) -> list[str]:
    """Tier 1 of every open package (the prepare-send default)."""
    out = []
    for pkg in packages:
        if package_status(pkg, offers_by_id, attempts) != "open":
            continue
        for tier in pkg.get("tiers", []):
            ids = [oid for oid in tier.get("offer_ids", []) if offers_by_id.get(oid) and _usable(offers_by_id[oid])]
            if ids:
                out.extend(ids)
                break
    return out


# ---------------------------------------------------------------------------
# Attempt state machine (§7)
# ---------------------------------------------------------------------------

def can_transition(current: str, new: str) -> bool:
    return new in _ATTEMPT_TRANSITIONS.get(current, frozenset())


def reconcile_attempt(offer, *, my_assets, is_pick=None, live_pick_holder=None) -> str | None:
    """Ownership-derived outcome for one live attempt (refresh, D8).

    Every give asset gone AND every receive asset arrived -> 'accepted'.
    A give asset gone but the receive side did not arrive -> 'resolved_elsewhere'.
    Otherwise None (unchanged).

    Picks are the exception: players in `my_assets` are read live, but the
    pick table can lag the platform, so an un-arrived receive side made ONLY
    of picks is never evidence. It earns 'accepted' when `live_pick_holder`
    (a live traded-picks read) confirms every one of them is now the user's;
    otherwise the attempt is left unchanged rather than terminalized.
    """
    mine = set(_ids(my_assets))
    is_pick = is_pick or (lambda _a: False)
    give, recv = _ids(offer["give_ids"]), _ids(offer["receive_ids"])
    gone = [a for a in give if a not in mine]
    if not gone:
        return None
    pending = [a for a in recv if a not in mine]
    picks_pending = [a for a in pending if is_pick(a)]
    if picks_pending and live_pick_holder is not None and all(live_pick_holder(a) for a in picks_pending):
        pending = [a for a in pending if not is_pick(a)]
    if not pending:
        return "accepted" if len(gone) == len(give) else None
    if all(is_pick(a) for a in pending):
        return None
    return "resolved_elsewhere"


def stuck_outcome(state: str, age_s: float) -> str | None:
    """Refresh sweep for live states nothing else reconciles (crash mid-batch).

    `sending` older than LIVE_STUCK_AFTER_S -> 'outcome_unknown' (the provider
    call may or may not have landed); `queued` -> 'stale' (never dispatched).
    """
    if age_s < LIVE_STUCK_AFTER_S:
        return None
    return {"sending": "outcome_unknown", "queued": "stale"}.get(state)


# ---------------------------------------------------------------------------
# Asset recommendations (§7 Views)
# ---------------------------------------------------------------------------

_STARTERS = {"QB": 1, "RB": 2, "WR": 3, "TE": 1}


def recommend_assets(assets, *, outlook, pick_budget=None, pick_meta=None, scoring_format="1qb_ppr"):
    """Stamp `recommended` + `reason` on AssetView dicts (advisory only)."""
    starts = dict(_STARTERS)
    if str(scoring_format or "").startswith(("sf", "2qb")):
        starts["QB"] = 2
    by_pos = {}
    for a in assets:
        if a["kind"] == "player":
            by_pos.setdefault(a.get("position"), []).append(a)
    starters = set()
    for pos, rows in by_pos.items():
        rows = sorted(rows, key=lambda r: -float(r.get("value") or 0.0))
        for r in rows[:starts.get(pos, 1)]:
            starters.add(r["id"])
    for a in assets:
        a["recommended"], a["reason"] = False, None
        if outlook == "push_all_in":
            if a["kind"] == "pick" and _pick_within_budget(a["id"], pick_meta, pick_budget):
                a["recommended"], a["reason"] = True, "pick_budget"
            elif a["kind"] == "player" and a["id"] not in starters:
                a["recommended"], a["reason"] = True, "bench_depth"
        elif outlook == "blow_it_up":
            age = a.get("age")
            if a["kind"] == "player" and a["id"] in starters and isinstance(age, (int, float)) and age >= 27:
                a["recommended"], a["reason"] = True, "aging_starter"
    return assets
